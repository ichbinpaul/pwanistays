"""Unit tests that do not need Supabase credentials or internet."""
import importlib.util
import unittest
import json
import tempfile
import contextlib
import io
import sys
from unittest.mock import patch
from pathlib import Path
from xml.etree import ElementTree as ET

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "build_property_sitemap.py"
sys.path.insert(0, str(SCRIPT.parent))
spec = importlib.util.spec_from_file_location("pwani_sitemap", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class SitemapTests(unittest.TestCase):
    def test_xml_contains_indexable_canonical_urls(self):
        a = "2f4578c5-e189-47dc-ad03-4a21e7c347b3"
        b = "711cc2b2-ed9d-4286-82cd-a28381ccd8b9"
        root = ET.fromstring(mod.render_sitemap([a, b]))
        ns = {"s": mod.NS}
        urls = [x.text for x in root.findall("s:url/s:loc", ns)]
        self.assertEqual(urls, [
            "https://pwanistays.com/stays/" + a + "/",
            "https://pwanistays.com/stays/" + b + "/"
        ])

    def test_public_config(self):
        base_url, key = mod.public_config()
        self.assertTrue(base_url.endswith(".supabase.co"))
        self.assertTrue(key.startswith("sb_publishable_"))

    def test_crawlable_owned_image_is_associated_with_its_property(self):
        property_id = "2f4578c5-e189-47dc-ad03-4a21e7c347b3"
        photo = "https://pwanistays.com/images/property-covers/" + property_id + "-0123456789abcdef.jpg"
        root = ET.fromstring(mod.render_sitemap([property_id], {property_id: photo}))
        ns = {"s": mod.NS, "image": mod.IMAGE_NS}
        self.assertEqual(root.find("s:url/image:image/image:loc", ns).text, photo)

    def test_snapshot_keeps_sitemap_in_step_with_generated_pages(self):
        property_id = "2f4578c5-e189-47dc-ad03-4a21e7c347b3"
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, output, robots = root / "source.json", root / "sitemap.xml", root / "robots.txt"
            source.write_text(json.dumps({"version": 1, "properties": [{"id": property_id}]}))
            robots.write_text("User-agent: *\nAllow: /\n")
            with patch.object(mod, "OUTPUT", output), patch.object(mod, "ROBOTS", robots), \
                    patch.object(mod, "fetch_active_ids") as live:
                self.assertEqual(mod.main(["--source", str(source)]), 0)
                live.assert_not_called()
                before = output.read_bytes()
                self.assertIn(("/stays/" + property_id + "/").encode(), before)
                source.write_text(json.dumps({"version": 1, "properties": []}))
                self.assertEqual(mod.main(["--source", str(source)]), 1)
                self.assertEqual(output.read_bytes(), before)

    def test_explicit_url_mapping_uses_friendly_canonical_and_keeps_uuid_image_path(self):
        property_id = "2f4578c5-e189-47dc-ad03-4a21e7c347b3"
        photo = "https://pwanistays.com/images/property-covers/" + property_id + "-0123456789abcdef.jpg"
        canonical = "https://pwanistays.com/stays/nyali-studio/"
        root = ET.fromstring(mod.render_sitemap([property_id], {property_id: photo}, {property_id: canonical}))
        ns = {"s": mod.NS, "image": mod.IMAGE_NS}
        self.assertEqual(root.find("s:url/s:loc", ns).text, canonical)
        self.assertEqual(root.find("s:url/image:image/image:loc", ns).text, photo)

    def test_duplicate_canonical_mapping_is_rejected(self):
        first = "2f4578c5-e189-47dc-ad03-4a21e7c347b3"
        second = "711cc2b2-ed9d-4286-82cd-a28381ccd8b9"
        with self.assertRaises(ValueError):
            mod.render_sitemap([first, second], urls={
                first: "https://pwanistays.com/stays/same-studio/",
                second: "https://pwanistays.com/stays/same-studio/"})

    def test_snapshot_honors_friendly_or_staged_uuid_urls_and_normalizes_legacy(self):
        property_id = "2f4578c5-e189-47dc-ad03-4a21e7c347b3"
        uuid_url = "https://pwanistays.com/stays/" + property_id + "/"
        cases = [
            ({"id": property_id, "slug": "nyali-studio", "url": "https://pwanistays.com/stays/nyali-studio/"},
             "https://pwanistays.com/stays/nyali-studio/"),
            ({"id": property_id, "slug": "nyali-studio", "url": uuid_url}, uuid_url),
            ({"id": property_id, "url": "https://pwanistays.com/property.html?id=" + property_id}, uuid_url),
        ]
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, output, robots = root / "source.json", root / "sitemap.xml", root / "robots.txt"
            robots.write_text("User-agent: *\nAllow: /\n")
            for row, expected in cases:
                source.write_text(json.dumps({"version": 1, "properties": [row]}))
                with self.subTest(row=row), patch.object(mod, "OUTPUT", output), patch.object(mod, "ROBOTS", robots), \
                        contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(mod.main(["--source", str(source)]), 0)
                    xml = ET.fromstring(output.read_bytes())
                    self.assertEqual(xml.find("s:url/s:loc", {"s": mod.NS}).text, expected)

    def test_invalid_source_url_preserves_last_sitemap(self):
        property_id = "2f4578c5-e189-47dc-ad03-4a21e7c347b3"
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, output, robots = root / "source.json", root / "sitemap.xml", root / "robots.txt"
            output.write_bytes(b"previous sitemap")
            robots.write_text("User-agent: *\n")
            source.write_text(json.dumps({"version": 1, "properties": [{
                "id": property_id, "slug": "nyali-studio", "url": "https://pwanistays.com/stays/other-studio/"}]}))
            with patch.object(mod, "OUTPUT", output), patch.object(mod, "ROBOTS", robots), \
                    contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(mod.main(["--source", str(source)]), 1)
            self.assertEqual(output.read_bytes(), b"previous sitemap")


if __name__ == "__main__":
    unittest.main()
