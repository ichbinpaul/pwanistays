"""Offline original-cover caching tests; no public image requests are made."""
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import Request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import cache_property_covers as mod

PROJECT = "https://example.supabase.co"
ID = "12345678-abcd-4321-9876-123456789012"
OTHER = "12345678-abcd-4321-9876-123456789013"
URL = PROJECT + mod.PUBLIC_PATH + ID + "/01.png"
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a2p8AAAAASUVORK5CYII=")


def source(*ids):
    return {"version": 1, "properties": [{"id": identity, "images": [
        PROJECT + mod.PUBLIC_PATH + identity + "/01.png"]} for identity in ids or [ID]]}


def head(etag='"cover-1"'):
    return {"status": 200, "headers": {} if etag is None else {"etag": etag}, "data": b""}


def body(data=PNG, mime="image/png", etag='"cover-1"'):
    return {"status": 200, "headers": {"content-type": mime, **({"etag": etag} if etag else {})}, "data": data}


class SourceTests(unittest.TestCase):
    def test_only_same_project_same_unit_public_images_are_accepted(self):
        self.assertEqual(mod.source_covers(source(), PROJECT), {ID: URL})
        invalid = [URL.replace(PROJECT, "https://elsewhere.example"),
                   URL.replace(ID, OTHER), URL.replace("https:", "http:"),
                   URL.replace("/public/", "/sign/"), URL + "?token=private",
                   URL.replace("/01.png", "/../" + OTHER + "/01.png"),
                   URL.replace("/01.png", "/%2e%2e/" + OTHER + "/01.png")]
        for url in invalid:
            with self.subTest(url=url), self.assertRaises(mod.CoverError):
                mod.validate_url(url, PROJECT, ID)
        for value in [{}, {"version": 1, "properties": []}, source(ID, ID)]:
            with self.subTest(value=value), self.assertRaises((mod.CoverError, ValueError)):
                mod.source_covers(value, PROJECT)

    def test_mime_and_magic_header_must_agree(self):
        self.assertEqual(mod.image_extension(PNG, "image/png"), "png")
        for data, mime in [(PNG, "image/jpeg"), (b"<html>not an image</html>", "image/png"),
                           (PNG, "text/html"), (PNG, "image/svg+xml")]:
            with self.subTest(mime=mime), self.assertRaises(mod.CoverError):
                mod.image_extension(data, mime)


class CacheTests(unittest.TestCase):
    def run_cache(self, folder, replies):
        output, manifest = Path(folder) / "covers", Path(folder) / "manifest.json"
        with patch.object(mod, "request_image", side_effect=replies) as request:
            result = mod.cache(source(), output, manifest, PROJECT)
        return result, output, manifest, request

    def test_original_bytes_are_preserved_at_immutable_hash_url(self):
        with tempfile.TemporaryDirectory() as folder:
            result, output, manifest, request = self.run_cache(folder, [head(), body()])
            digest = hashlib.sha256(PNG).hexdigest()
            entry = result["covers"][ID]
            name = ID + "-" + digest[:16] + ".png"
            self.assertEqual((output / name).read_bytes(), PNG)
            self.assertEqual(entry, {"source_url": URL,
                "image_url": mod.SITE + "/images/property-covers/" + name,
                "sha256": digest, "bytes": len(PNG), "etag": '"cover-1"'})
            self.assertEqual(json.loads(manifest.read_text()), result)
            self.assertEqual([call.args[3] for call in request.call_args_list], ["HEAD", "GET"])

    def test_validated_cached_etag_avoids_body_download_and_manifest_churn(self):
        with tempfile.TemporaryDirectory() as folder:
            result, output, manifest, _ = self.run_cache(folder, [head(), body()])
            before = manifest.stat().st_mtime_ns
            for reply in [head(), {"status": 304, "headers": {}, "data": b""}]:
                with patch.object(mod, "request_image", return_value=reply) as request:
                    self.assertEqual(mod.cache(source(), output, manifest, PROJECT), result)
                self.assertEqual(request.call_count, 1)
                self.assertEqual(request.call_args.args[3:], ("HEAD", '"cover-1"'))
                self.assertEqual(manifest.stat().st_mtime_ns, before)

    def test_missing_head_etag_forces_get_and_corrupt_owned_file_is_repaired(self):
        with tempfile.TemporaryDirectory() as folder:
            _, output, manifest, _ = self.run_cache(folder, [head(), body()])
            page = next(output.iterdir())
            page.write_bytes(b"corrupt")
            with patch.object(mod, "request_image", side_effect=[head(None), body()]) as request:
                mod.cache(source(), output, manifest, PROJECT)
            self.assertEqual([call.args[3] for call in request.call_args_list], ["HEAD", "GET"])
            self.assertIsNone(request.call_args_list[0].args[4])
            self.assertEqual(page.read_bytes(), PNG)
            with patch.object(mod, "request_image", side_effect=[head(None), body()]) as request:
                mod.cache(source(), output, manifest, PROJECT)
            self.assertEqual(request.call_count, 2)

    def test_failed_download_preserves_manifest_and_unknown_files(self):
        with tempfile.TemporaryDirectory() as folder:
            _, output, manifest, _ = self.run_cache(folder, [head(), body()])
            before = manifest.read_bytes()
            unknown = output / "user-note.txt"
            unknown.write_text("Keep this")
            with patch.object(mod, "request_image", side_effect=[head('"new"'), body(b"bad", "image/png")]):
                with self.assertRaises(mod.CoverError):
                    mod.cache(source(), output, manifest, PROJECT)
            self.assertEqual(manifest.read_bytes(), before)
            self.assertEqual(unknown.read_text(), "Keep this")

    def test_complete_batch_is_required_before_manifest_swap(self):
        with tempfile.TemporaryDirectory() as folder:
            _, output, manifest, _ = self.run_cache(folder, [head(), body()])
            before = manifest.read_bytes()
            def request(url, project, identity, method, etag=None):
                if identity == OTHER:
                    raise mod.CoverError("Source denied")
                return head() if method == "HEAD" else body()
            with patch.object(mod, "request_image", side_effect=request), self.assertRaises(mod.CoverError):
                mod.cache(source(ID, OTHER), output, manifest, PROJECT)
            self.assertEqual(manifest.read_bytes(), before)

    def test_unknown_hash_collision_and_symbolic_paths_are_never_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            output, manifest = root / "covers", root / "manifest.json"
            output.mkdir()
            name = ID + "-" + hashlib.sha256(PNG).hexdigest()[:16] + ".png"
            path = output / name
            path.write_bytes(b"unknown file")
            with patch.object(mod, "request_image", side_effect=[head(), body()]), self.assertRaises(mod.CoverError):
                mod.cache(source(), output, manifest, PROJECT)
            self.assertEqual(path.read_bytes(), b"unknown file")
            self.assertFalse(manifest.exists())
            link = root / "symbolic-output"
            link.symlink_to(output, target_is_directory=True)
            with self.assertRaises(mod.CoverError):
                mod.cache(source(), link, manifest, PROJECT)


class RequestTests(unittest.TestCase):
    def test_requests_have_no_credentials_and_head_redirect_stays_head(self):
        fake = Mock()
        fake.__enter__ = Mock(return_value=fake)
        fake.__exit__ = Mock(return_value=False)
        fake.getcode.return_value = 200
        fake.headers = {"Content-Type": "image/png", "ETag": '"abc"'}
        with patch.object(mod, "build_opener") as opener:
            opener.return_value.open.return_value = fake
            mod.request_image(URL, PROJECT, ID, "HEAD", '"abc"')
            req = opener.return_value.open.call_args.args[0]
        fake.read.assert_not_called()
        self.assertEqual(req.get_method(), "HEAD")
        headers = {key.lower(): value for key, value in req.header_items()}
        self.assertNotIn("authorization", headers)
        self.assertNotIn("apikey", headers)
        self.assertEqual(headers["if-none-match"], '"abc"')
        handler = mod.PublicRedirect(PROJECT, ID)
        redirected = handler.redirect_request(Request(URL, method="HEAD"), None, 301, "", {}, URL + "?v=2")
        self.assertEqual(redirected.get_method(), "HEAD")
        with self.assertRaises(mod.CoverError):
            handler.redirect_request(Request(URL), None, 301, "", {}, URL.replace(ID, OTHER))

    def test_oversized_response_and_http_errors_are_rejected_without_raw_body(self):
        fake = Mock()
        fake.__enter__ = Mock(return_value=fake)
        fake.__exit__ = Mock(return_value=False)
        fake.getcode.return_value = 200
        fake.headers = {"Content-Type": "image/png", "Content-Length": "99"}
        with patch.object(mod, "MAX_BYTES", 8), patch.object(mod, "build_opener") as opener:
            opener.return_value.open.return_value = fake
            with self.assertRaises(mod.CoverError):
                mod.request_image(URL, PROJECT, ID, "GET")
        fake.read.assert_not_called()
        with patch.object(mod, "build_opener") as opener:
            opener.return_value.open.side_effect = HTTPError(URL, 403, "private debug info", {}, io.BytesIO(b"private raw response"))
            with self.assertRaises(mod.CoverError) as caught:
                mod.request_image(URL, PROJECT, ID, "GET")
        self.assertNotIn("private", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
