import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import sync_property_galleries as mod


ID = "12345678-abcd-4321-9876-123456789012"
ROW = {"id": ID, "title": "Example", "folder_path": "villa", "image_url": None}


def image(path, payload):
    path.write_bytes(b"\xff\xd8\xff" + payload)


class GallerySyncTests(unittest.TestCase):
    def test_keeps_all_unique_photos_and_nested_amenities(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for index in range(105):
                image(root / f"{index + 1}.jpeg", str(index).encode())
            (root / "pool").mkdir()
            image(root / "pool" / "view.jpeg", b"pool")
            image(root / "copy.jpg", b"0")
            photos = mod.collect(root, mod.snapshot(root))
            self.assertEqual(len(photos), 106)
            self.assertEqual(photos[0].path.name, "1.jpeg")
            self.assertEqual(photos[-1].path.parent.name, "pool")

    def test_rejects_empty_or_unsupported_photo_sets(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with self.assertRaisesRegex(mod.GalleryError, "No eligible"):
                mod.snapshot(root)
            (root / "pool.HEIC").touch()
            with self.assertRaisesRegex(mod.GalleryError, "needs conversion"):
                mod.snapshot(root)

    def test_watch_waits_for_stable_files_and_publishes_each_change_once(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            folder = root / "villa"
            folder.mkdir()
            image(folder / "cover.jpg", b"cover")
            publisher = Mock(return_value="https://example.com/cover.jpg")
            with patch.object(mod, "list_properties", return_value=[ROW]), \
                    patch.object(mod, "publish", publisher), contextlib.redirect_stdout(io.StringIO()):
                args = (root, set(), {}, True, {}, {}, True, {})
                mod.run_scan(*args)
                publisher.assert_not_called()
                mod.run_scan(*args)
                mod.run_scan(*args)
                self.assertEqual(publisher.call_count, 1)
                image(folder / "gym.jpg", b"gym")
                mod.run_scan(*args)
                publisher.assert_called_once()
                mod.run_scan(*args)
                self.assertEqual(publisher.call_count, 2)
                self.assertEqual(len(publisher.call_args.args[3]), 2)

    def test_activates_only_after_every_file_is_verified(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            image(root / "1.jpeg", b"cover")
            image(root / "2.jpeg", b"pool")
            files = mod.snapshot(root)
            photos = mod.collect(root, files)

            def activate(method, path, **params):
                self.assertEqual(method, "PATCH")
                self.assertIn("image_url=is.null", path)
                self.assertEqual(upload.call_count, 2)
                cover = json.loads(params["data"])["image_url"]
                return 200, json.dumps([{"id": ID, "image_url": cover}])

            with patch.object(mod, "ensure_uploaded") as upload, \
                    patch.object(mod, "request", side_effect=activate) as request, \
                    contextlib.redirect_stdout(io.StringIO()):
                cover = mod.publish(ROW, root, files, photos, {})
                self.assertTrue(cover.endswith("/001.jpg"))
                upload.side_effect = mod.GalleryError("Upload failed")
                request.reset_mock()
                with self.assertRaisesRegex(mod.GalleryError, "Upload failed"):
                    mod.publish(ROW, root, files, photos, {})
                request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
