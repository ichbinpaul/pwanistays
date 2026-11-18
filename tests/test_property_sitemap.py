"""Unit tests that do not need Supabase credentials or internet."""
import importlib.util
import unittest
import json
import tempfile
from unittest.mock import patch
from pathlib import Path
from xml.etree import ElementTree as ET

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "build_property_sitemap.py"
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


if __name__ == "__main__":
    unittest.main()
