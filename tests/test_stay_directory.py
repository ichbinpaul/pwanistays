"""Ensure all property links are discoverable without running JavaScript."""
from html.parser import HTMLParser
import json
from pathlib import Path
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


if __name__ == "__main__":
    unittest.main()
