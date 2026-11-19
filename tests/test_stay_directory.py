"""Ensure all property links are discoverable without running JavaScript."""
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_stay_directory as mod
from build_property_previews import PreviewError


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self.headings = [], []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "a":
            self.links.append(values.get("href"))
        if tag == "h1":
            self.headings.append(values)


class DirectoryTests(unittest.TestCase):
    def source(self):
        return {"version": 1, "properties": [{
            "id": "12345678-abcd-4321-9876-123456789012", "title": "Nyali Studio",
            "location": "Nyali", "unit_type": "studio", "description": "Public description",
            "url": "https://pwanistays.com/stays/12345678-abcd-4321-9876-123456789012/",
            "images": ["https://example.com/cover.jpg"]}]}

    def test_every_unit_is_linked_in_plain_html_and_text_is_escaped(self):
        first, second = "12345678-abcd-4321-9876-123456789012", "12345678-abcd-4321-9876-123456789013"
        source = {"version": 1, "properties": [{
            "id": value, "title": '<script>alert("x")</script> Villa & sea',
            "location": "Nyali", "unit_type": "villa", "description": "Public description",
            "url": "https://pwanistays.com/property.html?id=" + value,
            "images": ["https://example.com/cover.jpg"]} for value in [first, second]]}
        html = mod.render(source)
        parser = Links()
        parser.feed(html)
        self.assertIn("/stays/" + first + "/", parser.links)
        self.assertIn("/stays/" + second + "/", parser.links)
        self.assertEqual(len(parser.headings), 1)
        self.assertNotIn('<script>alert("x")</script>', html)
        self.assertIn('loading="lazy"', html)
        self.assertIn('"numberOfItems": 2', html)

    def test_empty_source_is_not_published(self):
        with self.assertRaises(PreviewError):
            mod.render({"version": 1, "properties": []})

    def test_friendly_url_is_used_by_html_links_and_itemlist_schema(self):
        source = self.source()
        source["properties"][0].update(slug="nyali-studio", url="https://pwanistays.com/stays/nyali-studio/")
        html = mod.render(source)
        parser = Links()
        parser.feed(html)
        self.assertIn("/stays/nyali-studio/", parser.links)
        self.assertNotIn("/stays/" + source["properties"][0]["id"] + "/", parser.links)
        schema = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S).group(1))
        self.assertEqual(schema["mainEntity"]["itemListElement"][0]["url"],
                         "https://pwanistays.com/stays/nyali-studio/")

    def test_staged_slug_keeps_explicit_uuid_canonical_until_activation(self):
        source = self.source()
        row = source["properties"][0]
        row["slug"] = "nyali-studio"
        parser = Links()
        parser.feed(mod.render(source))
        self.assertIn("/stays/" + row["id"] + "/", parser.links)
        self.assertNotIn("/stays/nyali-studio/", parser.links)

    def test_legacy_url_normalizes_to_uuid_and_url_collisions_are_rejected(self):
        source = self.source()
        row = source["properties"][0]
        row["url"] = "https://pwanistays.com/property.html?id=" + row["id"]
        parser = Links()
        parser.feed(mod.render(source))
        self.assertIn("/stays/" + row["id"] + "/", parser.links)
        other = dict(row, id="12345678-abcd-4321-9876-123456789013")
        for item in (row, other):
            item.update(slug="same-studio", url="https://pwanistays.com/stays/same-studio/")
        source["properties"].append(other)
        with self.assertRaises((ValueError, RuntimeError)):
            mod.render(source)


if __name__ == "__main__":
    unittest.main()
