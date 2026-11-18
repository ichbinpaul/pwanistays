"""Offline checks for catalogue snapshots; no remote accounts are modified."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_whatsapp_catalogue as mod


BASE = "https://example.supabase.co"
KEY = "public-test-key"
ID = "12345678-abcd-4321-9876-123456789012"
OTHER = "12345678-abcd-4321-9876-123456789013"
REV = "_pwani_v6_0123456789abcdef"


def row(property_id=ID, **changes):
    value = {"id": property_id, "title": "Beach & Villa", "location": "Nyali",
             "unit_type": "villa", "is_active": True, "image_url": None}
    value.update(changes)
    return value


def image(name):
    return {"name": name, "metadata": {"mimetype": "image/jpeg"}}


def photo_path(property_id=ID, name="01.jpeg", revision=None):
    folder = property_id + ("/" + revision if revision else "")
    return f"{BASE}/storage/v1/object/public/property_images/{folder}/{name}"


def snapshot(generated_at="2026-11-18T00:00:00+00:00", title="Beach & Villa"):
    return {"version": 1, "status": "source_export_only", "meta_connected": False,
            "generated_at": generated_at, "properties": [{
                "id": ID, "title": title, "location": "Nyali", "unit_type": "villa",
                "url": "https://pwanistays.com/property.html?id=" + ID,
                "description": "Public property", "images": [photo_path()]}]}


class ListingTests(unittest.TestCase):
    def test_paginates_only_active_public_fields(self):
        with patch.object(mod, "PAGE_SIZE", 1), patch.object(mod, "request_json", side_effect=[
                [row()], [row(OTHER)], []]) as request:
            self.assertEqual([r["id"] for r in mod.fetch_properties(BASE, KEY)], [ID, OTHER])
        self.assertEqual(len(request.call_args_list), 3)
        for index, call in enumerate(request.call_args_list):
            params = parse_qs(urlsplit(call.args[2]).query)
            self.assertEqual(params["offset"], [str(index)])
            self.assertEqual(params["is_active"], ["eq.true"])
            self.assertEqual(params["order"], ["id.asc"])
            fields = set(params["select"][0].split(","))
            self.assertNotIn("*", fields)
            self.assertFalse(fields & {"price", "commission_rate"})

    def test_rejects_zero_duplicate_invalid_and_inactive_records(self):
        cases = [[], [row(), row()], [row(property_id="not-a-uuid")],
                 [row(is_active=False)], [row(title=" ")], [row(location={})], {}]
        for batch in cases:
            with self.subTest(batch=batch), patch.object(mod, "request_json", return_value=batch):
                with self.assertRaises((mod.SourceError, ValueError)):
                    mod.fetch_properties(BASE, KEY)

    def test_refuses_incomplete_property_pagination(self):
        with patch.object(mod, "PAGE_SIZE", 1), patch.object(mod, "MAX_PAGES", 1), \
                patch.object(mod, "request_json", return_value=[row()]):
            with self.assertRaisesRegex(mod.SourceError, "pagination"):
                mod.fetch_properties(BASE, KEY)

    def test_partial_page_failure_is_not_swallowed(self):
        with patch.object(mod, "PAGE_SIZE", 1), patch.object(mod, "request_json", side_effect=[
                [row()], OSError("network unavailable")]):
            with self.assertRaises(OSError):
                mod.fetch_properties(BASE, KEY)


class GalleryTests(unittest.TestCase):
    def test_recognises_only_same_project_same_property_valid_revision(self):
        selected = row(image_url=photo_path(revision=REV))
        self.assertEqual(mod.gallery_prefix(BASE, selected), ID + "/" + REV)
        for cover in [photo_path(OTHER, revision=REV),
                      photo_path(revision=REV).replace(BASE, "https://elsewhere.example"),
                      photo_path(revision="../" + REV),
                      photo_path(revision="_pwani_v6_invalid"),
                      photo_path(revision=REV + "/nested"),
                      photo_path(revision=REV).replace("https:", "http:")]:
            with self.subTest(cover=cover):
                self.assertEqual(mod.gallery_prefix(BASE, row(image_url=cover)), ID)

    def test_gallery_filters_folders_and_non_images(self):
        entries = [image("01.jpeg"), image("02.JPG"), image("not-image.txt"),
                   {"name": "folder.jpeg", "metadata": None},
                   {"name": "03.png", "metadata": {"mimetype": "text/plain"}},
                   image("nested/04.jpg")]
        with patch.object(mod, "request_json", return_value=entries):
            self.assertEqual([f["name"] for f in mod.fetch_gallery(BASE, KEY, ID)],
                             ["01.jpeg", "02.JPG"])

    def test_gallery_pagination_and_duplicate_rejection(self):
        with patch.object(mod, "PAGE_SIZE", 1), patch.object(mod, "request_json", side_effect=[
                [image("01.jpeg")], [image("02.jpeg")], []]) as request:
            self.assertEqual(len(mod.fetch_gallery(BASE, KEY, ID)), 2)
            self.assertEqual([c.args[3]["offset"] for c in request.call_args_list], [0, 1, 2])
        with patch.object(mod, "PAGE_SIZE", 1), patch.object(mod, "request_json", side_effect=[
                [image("01.jpeg")], [image("01.jpeg")]]):
            with self.assertRaisesRegex(mod.SourceError, "Duplicate"):
                mod.fetch_gallery(BASE, KEY, ID)

    def test_refuses_incomplete_gallery_pagination(self):
        with patch.object(mod, "PAGE_SIZE", 1), patch.object(mod, "MAX_PAGES", 1), \
                patch.object(mod, "request_json", return_value=[image("01.jpeg")]):
            with self.assertRaisesRegex(mod.SourceError, "pagination"):
                mod.fetch_gallery(BASE, KEY, ID)

    def test_cover_first_deduplicates_and_caps_at_ten(self):
        cover = photo_path(name="05.jpeg") + "?cache=123"
        photos = mod.select_photos(BASE, row(image_url=cover),
                                   [image(f"{i:02}.jpeg") for i in reversed(range(1, 16))])
        self.assertEqual(len(photos), 10)
        self.assertEqual(photos[0], cover)
        self.assertEqual(photos[1:5], [photo_path(name=f"{i:02}.jpeg") for i in range(1, 5)])
        self.assertEqual(sum("05.jpeg" in url for url in photos), 1)

    def test_selected_revision_and_quoted_filenames(self):
        photos = mod.select_photos(BASE, row(image_url=photo_path(revision=REV)),
                                   [image("01.jpeg"), image("02 pool & sea.jpeg")])
        self.assertEqual(photos[0], photo_path(revision=REV))
        self.assertIn("02%20pool%20%26%20sea.jpeg", photos[1])
        self.assertTrue(all("/" + REV + "/" in url for url in photos))

    def test_other_property_cover_is_not_exported(self):
        photos = mod.select_photos(BASE, row(image_url=photo_path(OTHER)), [image("02.jpeg")])
        self.assertEqual(photos, [photo_path(name="02.jpeg")])

    def test_unsafe_cover_urls_are_rejected(self):
        for url in ["http://example.com/a.jpg", "javascript:alert(1)",
                    "https://user:password@example.com/a.jpg", "https://example.com/a.jpg#fragment",
                    "https://example.com/a.html"]:
            with self.subTest(url=url):
                self.assertFalse(mod.valid_photo(url))


class SnapshotTests(unittest.TestCase):
    def test_amenities_are_extracted_without_legacy_prices_or_contact_captions(self):
        caption = "Private promotional intro\nAmenities:\n• WiFi\n• Swimming pool\n• KES 6000 per night\n• Call +254738544784\nRates:\nKES 9000\nContact:\nbookings@example.com"
        self.assertEqual(mod.public_amenities(caption), ["WiFi", "Swimming pool"])
        self.assertEqual(mod.public_amenities("Plain prose\n• WiFi\n• WhatsApp us\n• Ksh 5000\n• WiFi"), ["WiFi"])
        self.assertEqual(mod.public_amenities("• Ksh6500\n• 12,000 per night\n• $100\n• 6000/=\n• Parking"), ["Parking"])
    def test_export_has_canonical_link_and_no_private_fields_or_raw_caption(self):
        data = row(price=87654321, commission_rate=0.2,
                   description="Secret internal price 87654321; book via private contact")
        with patch.object(mod, "fetch_gallery", return_value=[image("01.jpeg")]):
            result = mod.export_property(BASE, KEY, data)
        self.assertEqual(result["url"], "https://pwanistays.com/stays/" + ID + "/")
        self.assertEqual(set(result), {"id", "title", "location", "unit_type", "url", "description", "images", "beds", "amenities"})
        self.assertNotIn("87654321", json.dumps(result))
        self.assertNotIn("Secret", result["description"])

    def test_missing_images_fails_instead_of_publishing_placeholders(self):
        with patch.object(mod, "fetch_gallery", return_value=[]):
            with self.assertRaisesRegex(mod.SourceError, "no usable"):
                mod.export_property(BASE, KEY, row())

    def test_idempotent_save_retains_timestamp_and_updates_real_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            self.assertTrue(mod.save_snapshot(snapshot(), directory))
            initial = {p.name: p.read_bytes() for p in directory.iterdir()}
            self.assertFalse(mod.save_snapshot(snapshot(generated_at="2026-11-19T00:00:00+00:00"), directory))
            self.assertEqual(initial, {p.name: p.read_bytes() for p in directory.iterdir()})
            self.assertTrue(mod.save_snapshot(snapshot(title="Updated villa"), directory))
            status = json.loads((directory / "status.json").read_text())
            self.assertEqual(status["property_count"], 1)
            self.assertEqual(status["image_count"], 1)
            self.assertFalse(status["meta_connected"])

    def test_failed_build_preserves_last_successful_files(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            mod.save_snapshot(snapshot(), directory)
            initial = {p.name: p.read_bytes() for p in directory.iterdir()}
            with patch.object(mod, "public_config", return_value=(BASE, KEY)), \
                    patch.object(mod, "build_snapshot", side_effect=mod.SourceError("gallery unavailable")), \
                    contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(mod.main(["--output-dir", folder]), 1)
            self.assertEqual(initial, {p.name: p.read_bytes() for p in directory.iterdir()})

    def test_check_mode_performs_validation_without_output_files(self):
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(mod, "public_config", return_value=(BASE, KEY)), \
                patch.object(mod, "build_snapshot", return_value=snapshot()), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(mod.main(["--check", "--output-dir", folder]), 0)
            self.assertEqual(list(Path(folder).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
