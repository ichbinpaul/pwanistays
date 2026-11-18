"""Static crawler-visible metadata and safe generation of property share pages."""
import contextlib
import copy
import hashlib
from html import escape, unescape
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

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
        executable = lambda scripts: [script for script in scripts if script.get("type") != "application/ld+json"]
        self.assertEqual(executable(parsed.scripts), executable(original.scripts))
        self.assertEqual(sum(script.get("id") == "property-structured-data" for script in parsed.scripts), 1)
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertNotIn('<img src=x>', html)
        self.assertTrue(all("onload" not in item for item in parsed.metas))

    def test_real_property_body_is_visible_without_javascript(self):
        row = property_row()
        row.update(beds=2, amenities=["Pool & sea view", "Fast Wi-Fi"])
        html = mod.render_property(self.template, row)
        elements = mod.TemplateElements(html).elements

        def content(element_id):
            element = elements[element_id]
            return html[element["open_end"]:element["close_start"]]

        self.assertEqual(unescape(content("propertyTitle")), row["title"])
        self.assertEqual(unescape(content("breadcrumbTitle")), row["title"])
        self.assertEqual(unescape(content("propertySummary")), row["description"])
        self.assertEqual(content("propertyLocation"), "Nyali")
        self.assertEqual(content("propertyType"), "Villa")
        self.assertEqual(content("propertyBeds"), "2 beds")
        self.assertEqual(content("propertyAmenities"), "<li>Pool &amp; sea view</li><li>Fast Wi-Fi</li>")
        self.assertNotIn("hidden", dict(elements["propertyContent"]["attrs"]))
        self.assertIn("hidden", dict(elements["propertyStatus"]["attrs"]))
        photo = dict(elements["pwMainImage"]["attrs"])
        self.assertEqual(photo["src"], row["images"][0])
        self.assertIn(row["title"], photo["alt"])
        self.assertNotIn("hidden", photo)
        self.assertIn("https://wa.me/254738544784?", content("propertyNoScript"))
        self.assertIn('href="/stays.html"', html)
        original = mod.TemplateElements(self.template).elements["quoteForm"]
        self.assertEqual(content("quoteForm"), self.template[original["open_end"]:original["close_start"]])

    def test_optional_public_metadata_defaults_and_invalid_values(self):
        default = mod.render_property(self.template, property_row())
        self.assertIn("Please contact PwaniStays to confirm the property amenities.", default)
        for field, value in [("amenities", "Pool"), ("amenities", [""]),
                             ("amenities", [{"price": 123}]), ("beds", -1),
                             ("beds", True), ("beds", 1.5), ("location", {}),
                             ("unit_type", ["villa"])]:
            row = property_row()
            row[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(mod.PreviewError):
                mod.render_property(self.template, row)

    def test_amenities_and_body_text_are_escaped(self):
        attack = '</li><script>alert("bad")</script><li>'
        row = property_row(title='Villa <b>near sea</b>')
        row.update(amenities=[attack], location='Nyali <img src=x onerror="bad">')
        html = mod.render_property(self.template, row)
        elements = mod.TemplateElements(html).elements
        self.assertIn("<li>" + escape(attack) + "</li>", html)
        self.assertNotIn('<img src=x onerror="bad">', html)
        self.assertEqual(sum(script.get("id") == "property-structured-data" for script in Metadata(html).scripts), 1)
        self.assertEqual(len(elements), len(set(elements)))

    def test_structured_data_is_real_unit_webpage_and_breadcrumb_graph(self):
        title = 'Sea </script><script>alert(9)</script> & sky'
        row = property_row(title=title)
        inherited = '<script type="application/ld+json">{"@type":"WebPage","name":"Generic page"}</script>'
        html = mod.render_property(self.template.replace("</head>", inherited + "</head>"), row)
        structured = mod.TemplateElements(html).elements["property-structured-data"]
        raw = html[structured["open_end"]:structured["close_start"]]
        data = json.loads(raw)
        self.assertNotIn("</script>", raw)
        self.assertNotIn("<", raw)
        self.assertEqual(sum(script.get("type") == "application/ld+json" for script in Metadata(html).scripts), 1)
        graph = {item["@type"]: item for item in data["@graph"]}
        self.assertEqual(set(graph), {"WebPage", "BreadcrumbList"})
        self.assertEqual(graph["WebPage"]["name"], title + " | PwaniStays")
        self.assertEqual(graph["WebPage"]["image"], row["images"][0])
        self.assertEqual(graph["WebPage"]["url"], f"https://pwanistays.com/stays/{ID}/")
        crumbs = graph["BreadcrumbList"]["itemListElement"]
        self.assertEqual([item["position"] for item in crumbs], [1, 2, 3])
        self.assertEqual(crumbs[1]["item"], "https://pwanistays.com/stays.html")
        self.assertEqual(crumbs[2]["name"], title)
        for forbidden in ["price", "ratingValue", "offers", "aggregateRating", "latitude", "availability"]:
            self.assertNotIn('"' + forbidden + '"', raw)

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
            (Path(folder) / "property.html").write_text(self.template, encoding="utf-8")
            with patch.object(mod, "ROOT", Path(folder)), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(mod.main(["--source", str(source), "--output-dir", str(output), "--check"]), 0)
            self.assertFalse(output.exists())


class CoverManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = (ROOT / "property.html").read_text(encoding="utf-8")

    def cached_cover(self, root):
        data = b"\xff\xd8\xffpublic unit image bytes"
        digest = hashlib.sha256(data).hexdigest()
        path = root / f"images/property-covers/{ID}-{digest[:16]}.jpeg"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        cover = {"source_url": property_row()["images"][0],
                 "image_url": "https://pwanistays.com/" + path.relative_to(root).as_posix(),
                 "sha256": digest, "etag": '"source-etag"', "bytes": len(data)}
        return {"version": 1, "covers": {ID: cover}}, path

    def test_verified_cached_cover_replaces_all_static_images_without_mutating_source(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            manifest, _ = self.cached_cover(root)
            source = snapshot()
            original = copy.deepcopy(source)
            loaded = mod.load_cover_images(source, manifest, root=root)
            self.assertEqual(source, original)
            row = loaded["properties"][0]
            local = manifest["covers"][ID]["image_url"]
            self.assertEqual(row["seo_image"], local)
            self.assertEqual(row["seo_source"], row["images"][0])
            html = mod.render_property(self.template, row)
            parsed = Metadata(html)
            self.assertEqual(parsed.content("og:image"), [local])
            self.assertEqual(parsed.content("og:image:secure_url"), [local])
            self.assertEqual(parsed.content("twitter:image"), [local])
            elements = mod.TemplateElements(html).elements
            photo = dict(elements["pwMainImage"]["attrs"])
            self.assertEqual(photo["src"], local)
            self.assertEqual(photo["data-seo-image"], local)
            self.assertEqual(photo["data-seo-source"], row["images"][0])
            structured = elements["property-structured-data"]
            graph = json.loads(html[structured["open_end"]:structured["close_start"]])["@graph"]
            self.assertEqual(next(node for node in graph if node["@type"] == "WebPage")["image"], local)

    def test_missing_stale_foreign_or_wrong_hash_manifest_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            manifest, _ = self.cached_cover(root)
            broken = [{"version": 1, "covers": {}}]
            for key, value in [("source_url", "https://example.com/old.jpg"),
                               ("image_url", manifest["covers"][ID]["image_url"].replace(ID, OTHER)),
                               ("image_url", manifest["covers"][ID]["image_url"].replace("pwanistays.com", "foreign.example")),
                               ("image_url", manifest["covers"][ID]["image_url"] + "?token=example"),
                               ("sha256", "a" * 64), ("bytes", True), ("bytes", 999999)]:
                item = copy.deepcopy(manifest)
                item["covers"][ID][key] = value
                broken.append(item)
            for item in broken:
                with self.subTest(item=item), self.assertRaises(mod.PreviewError):
                    mod.load_cover_images(snapshot(), item, root=root)

    def test_cover_file_bytes_and_symlink_paths_are_verified(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            manifest, path = self.cached_cover(root)
            path.write_bytes(b"changed image")
            with self.assertRaises(mod.PreviewError):
                mod.load_cover_images(snapshot(), manifest, root=root)
            manifest, path = self.cached_cover(root)
            actual = root / "other-image.jpeg"
            path.rename(actual)
            path.symlink_to(actual)
            with self.assertRaises(mod.PreviewError):
                mod.load_cover_images(snapshot(), manifest, root=root)

    def test_supplied_manifest_must_cover_every_active_unit(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            manifest, _ = self.cached_cover(root)
            with self.assertRaises(mod.PreviewError):
                mod.load_cover_images(snapshot(property_row(), property_row(OTHER)), manifest, root=root)

    def test_optional_seo_fields_are_scoped_to_correct_source_and_property(self):
        row = property_row()
        for additions in [{"seo_image": "https://foreign.example/a.jpeg", "seo_source": row["images"][0]},
                          {"seo_image": f"https://pwanistays.com/images/property-covers/{OTHER}-0123456789abcdef.jpeg",
                           "seo_source": row["images"][0]},
                          {"seo_image": f"https://pwanistays.com/images/property-covers/{ID}-0123456789abcdef.jpeg",
                           "seo_source": "https://example.com/old.jpeg"}]:
            with self.subTest(additions=additions), self.assertRaises(mod.PreviewError):
                mod.render_property(self.template, {**row, **additions})

    def test_cli_uses_present_manifest_and_refuses_stale_copy_before_page_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            manifest, _ = self.cached_cover(root)
            source = root / "catalogue/properties.json"
            source.parent.mkdir()
            source.write_text(json.dumps(snapshot()))
            covers = root / "catalogue/cover-images.json"
            covers.write_text(json.dumps(manifest))
            (root / "property.html").write_text(self.template)
            output = root / "stays"
            with patch.object(mod, "ROOT", root), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(mod.main([]), 0)
            index = output / ID / "index.html"
            before = index.read_bytes()
            manifest["covers"][ID]["source_url"] = "https://example.com/stale.jpeg"
            covers.write_text(json.dumps(manifest))
            with patch.object(mod, "ROOT", root), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(mod.main([]), 1)
            self.assertEqual(index.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
