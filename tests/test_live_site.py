"""Offline deployed-site checker tests. No HTTP requests are performed."""
import contextlib
import base64
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
import check_live_site as mod

URL = "https://pwanistays.com/stays/example/"
HTML = f'''<!doctype html><html><head>
<link rel="canonical" href="{URL}"><meta name="robots" content="index,follow">
</head><body><h1>Beach <span>Villa</span></h1><script>PRIVATE_BODY_CANARY</script></body></html>'''


def response(status=200, url=URL, body=HTML, headers=None):
    return {"status": status, "final_url": url, "body": body.encode(), "attempts": 1,
            "headers": {"content-type": "text/html; charset=utf-8", **(headers or {})}, "error": None}


class HtmlTests(unittest.TestCase):
    def test_visibility_uses_real_ancestors_and_nonempty_headings(self):
        page = mod.Page('<main hidden><h1>Hidden</h1></main><div style="display: none"><h1>Also hidden</h1></div>'
                        '<h1><span hidden>Hidden child</span>Visible heading</h1><h1> </h1>')
        self.assertEqual(page.headings, ["Visible heading"])

    def test_indexable_page_requires_static_heading_and_unique_matching_canonical(self):
        target = {"url": URL, "kind": "page", "expected": URL}
        with patch.object(mod, "fetch", return_value=response()):
            result = mod.check(target, mod.SITE)
        self.assertEqual(result["issues"], [])
        self.assertNotIn("body", result)
        self.assertNotIn("PRIVATE_BODY_CANARY", json.dumps(result))
        html = HTML.replace('<h1>Beach <span>Villa</span></h1>', '<main hidden><h1></h1></main>')
        html = html.replace("index,follow", "noindex,follow")
        html = html.replace('</head>', f'<link rel="canonical" href="{URL}"></head>')
        with patch.object(mod, "fetch", return_value=response(body=html)):
            result = mod.check(target, mod.SITE)
        self.assertEqual(len(result["issues"]), 3)

    def test_http_noindex_and_non_html_responses_are_failures(self):
        target = {"url": URL, "kind": "page", "expected": URL}
        for headers in [{"x-robots-tag": "googlebot: noindex"}, {"content-type": "application/json"}]:
            with self.subTest(headers=headers), patch.object(mod, "fetch", return_value=response(headers=headers)):
                self.assertTrue(mod.check(target, mod.SITE)["issues"])
        with patch.object(mod, "fetch", return_value=response(headers={"x-robots-tag": "max-image-preview:none"})):
            self.assertEqual(mod.check(target, mod.SITE)["issues"], [])


class HttpTests(unittest.TestCase):
    def test_real_404_passes_and_soft_404_fails(self):
        target = {"url": URL, "kind": "missing", "expected": None}
        with patch.object(mod, "fetch", return_value=response(status=404)):
            self.assertEqual(mod.check(target, mod.SITE)["issues"], [])
        with patch.object(mod, "fetch", return_value=response(status=200)):
            self.assertIn("Expected HTTP 404", mod.check(target, mod.SITE)["issues"][0])

    def test_redirect_probe_requires_preferred_final_url(self):
        target = {"url": "http://www.pwanistays.com/", "kind": "redirect", "expected": mod.SITE + "/"}
        with patch.object(mod, "fetch", return_value=response(url=mod.SITE + "/")):
            self.assertEqual(mod.check(target, mod.SITE)["issues"], [])
        with patch.object(mod, "fetch", return_value=response(url="https://elsewhere.example/")):
            self.assertTrue(mod.check(target, mod.SITE)["issues"])
        handler = mod.SameSiteRedirect(mod.SITE)
        for url in ["https://elsewhere.example/", "http://pwanistays.com/"]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                handler.redirect_request(None, None, 301, "", {}, url)

    def test_asset_redirect_can_work_but_html_in_place_of_script_fails(self):
        target = {"url": mod.SITE + "/property.js", "kind": "asset", "expected": mod.SITE + "/property.js"}
        with patch.object(mod, "fetch", return_value=response(url=mod.SITE + "/property-v2.js", headers={"content-type": "text/javascript"})):
            self.assertEqual(mod.check(target, mod.SITE)["issues"], [])
        with patch.object(mod, "fetch", return_value=response(url=target["url"])):
            self.assertIn("Script asset", mod.check(target, mod.SITE)["issues"][0])
        target = {"url": mod.SITE + "/catalogue/property-slugs.json", "kind": "asset", "expected": None}
        with patch.object(mod, "fetch", return_value=response(url=target["url"])):
            self.assertIn("JSON asset", mod.check(target, mod.SITE)["issues"][0])
        with patch.object(mod, "fetch", return_value=response(url=target["url"], headers={"content-type": "application/json"})):
            self.assertEqual(mod.check(target, mod.SITE)["issues"], [])

    def test_only_server_errors_are_retried_once(self):
        with patch.object(mod, "read_url", side_effect=[response(status=503), response()]) as read, patch.object(mod.time, "sleep"):
            self.assertEqual(mod.fetch(URL, mod.SITE)["attempts"], 2)
            self.assertEqual(read.call_count, 2)
        for status in [0, 403, 404]:
            with self.subTest(status=status), patch.object(mod, "read_url", return_value=response(status=status)) as read:
                self.assertEqual(mod.fetch(URL, mod.SITE)["attempts"], 1)
                read.assert_called_once()

    def test_transport_records_http_errors_and_bounds_response_bodies(self):
        error = HTTPError(URL, 404, "Not found", {"Content-Type": "text/html"}, io.BytesIO(b"Not found"))
        with patch.object(mod, "build_opener") as opener:
            opener.return_value.open.side_effect = error
            result = mod.read_url(URL, mod.SITE)
        self.assertEqual(result["status"], 404)
        self.assertEqual(result["body"], b"Not found")
        fake = Mock()
        fake.__enter__ = Mock(return_value=fake)
        fake.__exit__ = Mock(return_value=False)
        fake.read.return_value = b"1234567"
        fake.getcode.return_value = 200
        fake.geturl.return_value = URL
        fake.headers = {"Content-Type": "text/html"}
        with patch.object(mod, "MAX_BYTES", 6), patch.object(mod, "build_opener") as opener:
            opener.return_value.open.return_value = fake
            result = mod.read_url(URL, mod.SITE)
        self.assertEqual(result["status"], 200)
        self.assertEqual(result["body"], b"123456")
        self.assertIn("inspection limit", result["error"])

    def test_body_timeout_is_reported_without_aborting_other_checks(self):
        fake = Mock()
        fake.__enter__ = Mock(return_value=fake)
        fake.__exit__ = Mock(return_value=False)
        fake.read.side_effect = TimeoutError("private network details")
        with patch.object(mod, "build_opener") as opener:
            opener.return_value.open.return_value = fake
            result = mod.read_url(URL, mod.SITE)
        self.assertEqual(result["status"], 0)
        self.assertEqual(result["error"], "Response could not be read")
        self.assertNotIn("private network details", json.dumps(result, default=str))


class TargetTests(unittest.TestCase):
    def write_maps(self, root, url=URL):
        xml = '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>' + url + '</loc></url></urlset>'
        for name in ["sitemap.xml", "property-sitemap.xml"]:
            (root / name).write_text(xml)

    def test_targets_are_deduplicated_and_include_assets_missing_and_redirect_checks(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.write_maps(root)
            rows = mod.targets(root, mod.SITE, redirects=True)
        self.assertEqual(sum(row["url"] == URL for row in rows), 1)
        self.assertEqual(sum(row["kind"] == "missing" for row in rows), 1)
        self.assertEqual(sum(row["kind"] == "redirect" for row in rows), 3)
        self.assertTrue(any(row["url"].endswith("/robots.txt") for row in rows))

    def test_sitemap_cannot_redirect_checker_to_unknown_host_or_query(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for url in ["https://elsewhere.example/", "https://pwanistays.com/?secret=value", "http://pwanistays.com/"]:
                self.write_maps(root, url)
                with self.subTest(url=url), self.assertRaises(ValueError):
                    mod.targets(root, mod.SITE)

    def test_failed_live_requests_still_write_explicit_failure_report(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.write_maps(root)
            report = root / "health.json"
            with patch.object(mod, "fetch", side_effect=lambda url, preferred: response(status=0, url=url)), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(mod.main(["--root", str(root), "--report", str(report)]), 1)
            value = json.loads(report.read_text())
            self.assertGreater(value["checked"], 0)
            self.assertEqual(value["passed"], 0)
            self.assertEqual(value["failed"], value["checked"])
            self.assertNotIn("PRIVATE_BODY_CANARY", json.dumps(value))


class CoverTests(unittest.TestCase):
    BASE = "https://example.supabase.co"
    COVER = BASE + "/storage/v1/object/public/property_images/property/01.jpeg"

    def write_source(self, root, covers):
        (root / "listing-utils.js").write_text("const SUPABASE_URL = '" + self.BASE + "';")
        (root / "catalogue").mkdir()
        (root / "catalogue/properties.json").write_text(json.dumps({"version": 1, "properties": [
            {"images": [cover, self.BASE + "/unused-second-image.jpeg"]} for cover in covers]}))

    def test_only_distinct_current_covers_on_configured_project_are_planned(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            other = self.BASE + "/storage/v1/object/public/property_images/property/02.jpeg"
            self.write_source(root, [self.COVER, self.COVER, other])
            rows = mod.cover_targets(root)
        self.assertEqual([row["url"] for row in rows], [self.COVER, other])
        self.assertTrue(all(row["kind"] == "cover" and row["origin"] == self.BASE for row in rows))

    def test_other_hosts_and_signed_or_credential_urls_are_unverified_and_not_fetched(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_source(root, ["https://elsewhere.example/cover.jpg", self.COVER + "?access_token=private-value"])
            rows = mod.cover_targets(root)
            with patch.object(mod, "fetch") as fetch:
                outcomes = [mod.check(row, mod.SITE) for row in rows]
            fetch.assert_not_called()
        self.assertTrue(all(row.get("unverified") and row["status"] is None for row in outcomes))
        self.assertNotIn("private-value", json.dumps(outcomes))

    def test_cover_requests_use_head_and_never_read_an_image_body_or_add_credentials(self):
        fake = Mock()
        fake.__enter__ = Mock(return_value=fake)
        fake.__exit__ = Mock(return_value=False)
        fake.getcode.return_value = 200
        fake.geturl.return_value = self.COVER
        fake.headers = {"Content-Type": "image/jpeg"}
        with patch.object(mod, "build_opener") as opener:
            opener.return_value.open.return_value = fake
            result = mod.read_url(self.COVER, self.BASE, method="HEAD")
            req = opener.return_value.open.call_args.args[0]
        self.assertEqual(req.get_method(), "HEAD")
        self.assertNotIn("apikey", {name.lower() for name, _ in req.header_items()})
        self.assertNotIn("authorization", {name.lower() for name, _ in req.header_items()})
        fake.read.assert_not_called()
        self.assertEqual(result["body"], b"")
        redirected = mod.SameSiteRedirect(self.BASE).redirect_request(
            Request(self.COVER, method="HEAD"), None, 301, "Moved", {}, self.COVER + "?v=2")
        self.assertEqual(redirected.get_method(), "HEAD")

    def test_cover_status_and_content_type_are_checked(self):
        target = {"url": self.COVER, "kind": "cover", "expected": self.COVER, "origin": self.BASE}
        with patch.object(mod, "fetch", return_value=response(url=self.COVER, headers={"content-type": "image/webp"})) as fetch:
            self.assertEqual(mod.check(target, mod.SITE)["issues"], [])
            fetch.assert_called_once_with(self.COVER, self.BASE, method="HEAD")
        for value in [response(url=self.COVER), response(status=404, url=self.COVER, headers={"content-type": "image/jpeg"}),
                      response(url=self.COVER, headers={"content-type": "image/jpeg", "x-robots-tag": "none"}),
                      response(url=self.COVER, headers={"content-type": "image/jpeg", "x-robots-tag": "googlebot-image: noindex"})]:
            with self.subTest(value=value), patch.object(mod, "fetch", return_value=value):
                self.assertTrue(mod.check(target, mod.SITE)["issues"])
        with patch.object(mod, "fetch", return_value=response(url=self.COVER, headers={"content-type": "image/jpeg", "x-robots-tag": "max-image-preview:none"})):
            self.assertEqual(mod.check(target, mod.SITE)["issues"], [])

    def owned_fixture(self, root):
        property_id = "12345678-abcd-4321-9876-123456789012"
        source_url = self.BASE + "/storage/v1/object/public/property_images/" + property_id + "/01.png"
        self.write_source(root, [source_url])
        source = {"version": 1, "properties": [{"id": property_id, "title": "Beach villa",
                  "description": "View this property's photos.", "images": [source_url],
                  "url": mod.SITE + "/stays/" + property_id + "/"}]}
        (root / "catalogue/properties.json").write_text(json.dumps(source))
        photo = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aN5kAAAAASUVORK5CYII=")
        digest = hashlib.sha256(photo).hexdigest()
        relative = "images/property-covers/" + property_id + "-" + digest[:16] + ".png"
        path = root / relative
        path.parent.mkdir(parents=True)
        path.write_bytes(photo)
        manifest = {"version": 1, "covers": {property_id: {"source_url": source_url,
                    "image_url": mod.SITE + "/" + relative, "sha256": digest, "bytes": len(photo)}}}
        (root / "catalogue/cover-images.json").write_text(json.dumps(manifest))
        return source, manifest

    def test_owned_cover_manifest_takes_precedence_and_is_head_checked_on_the_site(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, manifest = self.owned_fixture(root)
            expected = next(iter(manifest["covers"].values()))["image_url"]
            rows = mod.cover_targets(root)
            self.assertEqual([row["url"] for row in rows], [expected])
            self.assertEqual(rows[0]["origin"], mod.SITE)
            with patch.object(mod, "fetch", return_value=response(url=expected, headers={"content-type": "image/png"})) as fetch:
                self.assertEqual(mod.check(rows[0], mod.SITE)["issues"], [])
                fetch.assert_called_once_with(expected, mod.SITE, method="HEAD")
            self.assertNotEqual(expected, source["properties"][0]["images"][0])

    def test_stale_or_incomplete_owned_cover_manifest_never_falls_back(self):
        for mode in ["stale", "incomplete", "corrupt_file"]:
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source, manifest = self.owned_fixture(root)
                if mode == "stale":
                    source["properties"][0]["images"][0] = source["properties"][0]["images"][0].replace("01.png", "02.png")
                    (root / "catalogue/properties.json").write_text(json.dumps(source))
                elif mode == "incomplete":
                    (root / "catalogue/cover-images.json").write_text(json.dumps({"version": 1, "covers": {}}))
                else:
                    image = next(iter(manifest["covers"].values()))["image_url"]
                    (root / image.removeprefix(mod.SITE + "/")).write_bytes(b"modified")
                with self.assertRaises(ValueError), patch.object(mod, "fetch") as fetch:
                    mod.cover_targets(root)
                fetch.assert_not_called()

    def test_unverified_covers_are_not_counted_as_checked_or_passed(self):
        target = {"url": "https://elsewhere.example/photo.jpg", "kind": "cover_unverified",
                  "expected": None, "reason": "Unknown image host; not fetched"}
        with tempfile.TemporaryDirectory() as directory, patch.object(mod, "targets", return_value=[target]), \
                patch.object(mod, "fetch") as fetch, contextlib.redirect_stdout(io.StringIO()):
            report = Path(directory) / "health.json"
            self.assertEqual(mod.main(["--check-cover-images", "--report", str(report)]), 1)
            value = json.loads(report.read_text())
            self.assertEqual((value["checked"], value["passed"], value["failed"], value["unverified"]), (0, 0, 0, 1))
            fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
