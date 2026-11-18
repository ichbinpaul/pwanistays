"""Static crawler-visible metadata and safe generation of property share pages."""
import contextlib
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_property_previews as mod

ROOT = Path(__file__).resolve().parents[1]
ID = "12345678-abcd-4321-9876-123456789012"
OTHER = "12345678-abcd-4321-9876-123456789013"


def property_row(property_id=ID, title="Beach & Villa", image="https://example.com/beach.jpg"):
    return {"id": property_id, "title": title, "description": "Explore photos & request a quotation.",
            "url": "https://pwanistays.com/property.html?id=" + property_id,
            "location": "Nyali", "unit_type": "villa", "images": [image]}


def snapshot(*rows):
    return {"version": 1, "status": "source_export_only", "meta_connected": False,
            "generated_at": "2026-11-18T00:00:00+00:00", "properties": list(rows or [property_row()])}


class Metadata(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.metas, self.links, self.html_attrs, self.scripts = [], [], {}, []
        self.title_parts = []
        self.in_title = False
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "meta":
            self.metas.append(attrs)
        elif tag == "link":
            self.links.append(attrs)
        elif tag == "html":
            self.html_attrs = attrs
        elif tag == "title":
            self.in_title = True
        elif tag == "script":
            self.scripts.append(attrs)

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title_parts.append(data)

    def content(self, key):
        return [m.get("content") for m in self.metas if m.get("property") == key or m.get("name") == key]

    def canonical(self):
        return [link.get("href") for link in self.links if link.get("rel") == "canonical"]


class RenderingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = (ROOT / "property.html").read_text(encoding="utf-8")

    def test_two_units_have_distinct_crawler_visible_titles_images_and_links(self):
        rows = [property_row(), property_row(OTHER, "Pool apartment", "https://example.com/pool.jpg")]
        for row in rows:
            with self.subTest(property_id=row["id"]):
                html = mod.render_property(self.template, row)
                parsed = Metadata(html)
                expected = f"https://pwanistays.com/stays/{row['id']}/"
                self.assertEqual(parsed.content("og:image"), [row["images"][0]])
                self.assertEqual(parsed.content("og:url"), [expected])
                self.assertEqual(parsed.canonical(), [expected])
                self.assertIn(row["title"], "".join(parsed.title_parts))
                self.assertIn(row["title"], parsed.content("og:title")[0])
                self.assertEqual(parsed.html_attrs.get("data-property-id"), row["id"])
                self.assertNotIn("logo-mobile.png", parsed.content("og:image")[0])
                self.assertIn(mod.MARKER, html)

    def test_metadata_is_escaped_without_creating_injected_tags(self):
        attack = 'Ocean "</title><script>alert(1)</script><img src=x> & sea'
        row = property_row(title=attack)
        row["description"] = '\" onload="alert(2)" <script> & beautiful'
        html = mod.render_property(self.template, row)
        parsed = Metadata(html)
        original = Metadata(self.template)
        self.assertIn(attack, "".join(parsed.title_parts))
        self.assertIn(attack, parsed.content("og:title")[0])
        self.assertEqual(parsed.content("description"), [row["description"]])
        self.assertEqual(len(parsed.scripts), len(original.scripts))
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertNotIn('<img src=x>', html)
        self.assertTrue(all("onload" not in item for item in parsed.metas))

    def test_new_source_url_is_accepted(self):
        row = property_row()
        row["url"] = f"https://pwanistays.com/stays/{ID}/"
        self.assertEqual(len(mod.validate_source(snapshot(row))), 1)

    def test_removes_all_inherited_social_images_and_canonical_tags(self):
        inherited = ('<meta property="og:image" content="https://example.com/old.jpg">'
                     '<meta name="twitter:image" content="https://example.com/old.jpg">'
                     '<link rel="canonical" href="https://example.com/old">')
        template = self.template.replace("</head>", inherited + "</head>")
        row = property_row()
        parsed = Metadata(mod.render_property(template, row))
        self.assertEqual(parsed.content("og:image"), row["images"])
        self.assertEqual(parsed.content("twitter:image"), row["images"])
        self.assertEqual(parsed.canonical(), [f"https://pwanistays.com/stays/{ID}/"])


class GenerationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = (ROOT / "property.html").read_text(encoding="utf-8")

    def test_repeatability_and_check_mode_do_not_touch_outputs(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "stays"
            result = mod.generate(snapshot(), self.template, output)
            self.assertEqual(result["active"], 1)
            index = output / ID / "index.html"
            original = index.read_bytes()
            modified = index.stat().st_mtime_ns
            self.assertEqual(mod.generate(snapshot(), self.template, output)["changed"], 0)
            self.assertEqual(index.stat().st_mtime_ns, modified)
            updated = snapshot(property_row(title="Updated unit"))
            self.assertGreater(mod.generate(updated, self.template, output, check=True)["changed"], 0)
            self.assertEqual(index.read_bytes(), original)
            fresh = Path(folder) / "check-only"
            mod.generate(snapshot(), self.template, fresh, check=True)
            self.assertFalse(fresh.exists())

    def test_invalid_or_empty_source_preserves_existing_files(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "stays"
            mod.generate(snapshot(), self.template, output)
            index = output / ID / "index.html"
            before = index.read_bytes()
            invalid = [{}, {"version": 1, "properties": []}]
            for changes in [{"id": "../escape"}, {"images": []},
                            {"images": ["javascript:alert(1)"]},
                            {"url": "https://other.example/"}]:
                row = property_row()
                row.update(changes)
                invalid.append(snapshot(row))
            invalid.append(snapshot(property_row(), property_row()))
            for source in invalid:
                with self.subTest(source=source), self.assertRaises((ValueError, RuntimeError)):
                    mod.generate(source, self.template, output)
                self.assertEqual(index.read_bytes(), before)

    def test_unowned_index_collision_never_overwrites_existing_work(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "stays"
            unit = output / ID
            unit.mkdir(parents=True)
            index = unit / "index.html"
            index.write_text("User-authored page", encoding="utf-8")
            with self.assertRaises((ValueError, RuntimeError)):
                mod.generate(snapshot(), self.template, output)
            self.assertEqual(index.read_text(), "User-authored page")

    def test_all_paths_are_checked_before_any_page_is_changed(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "stays"
            mod.generate(snapshot(), self.template, output)
            first = output / ID / "index.html"
            before = first.read_bytes()
            other = output / OTHER
            other.mkdir()
            (other / "index.html").write_text("Unowned collision")
            with self.assertRaises((ValueError, RuntimeError)):
                mod.generate(snapshot(property_row(title="New title"), property_row(OTHER)), self.template, output)
            self.assertEqual(first.read_bytes(), before)

    def test_withdrawn_owned_unit_has_tombstone_without_stale_image(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "stays"
            mod.generate(snapshot(property_row(), property_row(OTHER)), self.template, output)
            result = mod.generate(snapshot(property_row(OTHER)), self.template, output)
            self.assertEqual(result["withdrawn"], 1)
            tombstone = (output / ID / "index.html").read_text()
            parsed = Metadata(tombstone)
            self.assertIn(mod.MARKER, tombstone)
            self.assertTrue(any("noindex" in value for value in parsed.content("robots")))
            self.assertNotIn("https://example.com/beach.jpg", tombstone)
            self.assertEqual(parsed.content("og:image"), [])
            self.assertTrue((output / OTHER / "index.html").is_file())

    def test_unknown_files_directories_and_symlinks_are_not_touched(self):
        with tempfile.TemporaryDirectory() as folder:
            parent = Path(folder)
            for kind in ("file", "directory", "symlink"):
                with self.subTest(kind=kind):
                    output = parent / kind
                    output.mkdir()
                    unexpected = output / "unrelated"
                    if kind == "file":
                        unexpected.write_text("keep")
                    elif kind == "directory":
                        unexpected.mkdir()
                    else:
                        outside = parent / "outside"
                        outside.mkdir(exist_ok=True)
                        unexpected.symlink_to(outside, target_is_directory=True)
                    with self.assertRaises((ValueError, RuntimeError)):
                        mod.generate(snapshot(), self.template, output)
                    self.assertTrue(unexpected.exists())
                    self.assertFalse((output / ID).exists())

    def test_cli_check_validates_without_creating_output(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "source.json"
            source.write_text(json.dumps(snapshot()), encoding="utf-8")
            output = Path(folder) / "stays"
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(mod.main(["--source", str(source), "--output-dir", str(output), "--check"]), 0)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
