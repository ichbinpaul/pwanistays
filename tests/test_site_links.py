"""Offline fixtures for the public-site link/asset auditor."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import audit_site_links as mod


class AuditTests(unittest.TestCase):
    def put(self, root, name, content=""):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def test_same_site_urls_directory_indexes_encoded_assets_and_queries(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.put(root, "index.html", '''<a href="/stays/unit/?guests=2#photos">Unit</a>
                <a href="https://www.pwanistays.com/index.html?ignored=1#contact">Contact</a>
                <img src="/images/Beach%20%26%20pool.jpg?cache=2"><div id="contact"></div>''')
            self.put(root, "stays/unit/index.html", '<h1 id="photos">Photo gallery</h1>')
            self.put(root, "images/Beach & pool.jpg")
            report = mod.audit(root)
            self.assertEqual(report["broken_count"], 0)
            self.assertEqual(report["counts"]["local_targets_checked"], 3)
            self.assertEqual(report["counts"]["fragments_checked"], 2)

    def test_missing_links_fragments_assets_and_css_imports_are_reported(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.put(root, "index.html", '<a href="#missing">Missing section</a><img src="lost.png"><link href="/site.css">')
            self.put(root, "site.css", '@import "lost.css"; .a {background:url("images/lost.jpg")}')
            report = mod.audit(root)
            self.assertEqual(report["broken_count"], 4)
            self.assertEqual({item["reason"] for item in report["broken"]},
                             {"missing_static_fragment", "missing_local_target"})

    def test_external_domains_remain_unverified_and_schemes_are_skipped(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.put(root, "index.html", '''<a href="https://example.com/property">External</a>
                <script src="//cdn.example.com/lib.js"></script><a href="mailto:a@example.com">Email</a>
                <a href="tel:+254000">Call</a><a href="javascript:void(0)">Action</a>
                <img src="data:image/png;base64,AAAA"><a href="#">Menu</a>''')
            report = mod.audit(root)
            self.assertEqual(report["broken_count"], 0)
            self.assertEqual({item["domain"] for item in report["external_domains"]},
                             {"example.com", "cdn.example.com"})
            self.assertTrue(all(item["status"] == "unverified_no_network" for item in report["external_domains"]))
            self.assertEqual(report["counts"]["skipped_schemes"], 4)

    def test_injected_header_and_known_dynamic_targets_not_false_failures(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.put(root, "header.html", '<input id="headerSearch">')
            self.put(root, "index.html", '''<div id="site-header"></div><a href="#headerSearch">Search</a>
                <a href="#property-12345678">Generated property</a><a href="/stays/${id}/">Dynamic</a>''')
            report = mod.audit(root)
            self.assertEqual(report["broken_count"], 0)
            self.assertEqual(report["counts"]["fragments_checked"], 1)
            self.assertEqual(report["unverified_count"], 2)

    def test_xml_manifest_catalogue_and_robots_references(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.put(root, "index.html", '<h1>Site</h1>')
            self.put(root, "site.webmanifest", json.dumps({"start_url": "/", "icons": [{"src": "/missing-icon.png"}]}))
            self.put(root, "browserconfig.xml", '<browserconfig><logo src="/missing-tile.png"/></browserconfig>')
            self.put(root, "sitemap.xml", '<urlset><url><loc>https://pwanistays.com/</loc></url></urlset>')
            self.put(root, "robots.txt", 'Sitemap: https://pwanistays.com/sitemap.xml\n')
            self.put(root, "catalogue/properties.json", json.dumps({"properties": [{"url": "https://pwanistays.com/", "images": ["https://images.example.com/room.jpg"]}]}))
            report = mod.audit(root)
            self.assertEqual(report["broken_count"], 2)
            self.assertEqual({item["url"] for item in report["broken"]}, {"/missing-icon.png", "/missing-tile.png"})
            self.assertEqual(report["external_domains"][0]["domain"], "images.example.com")

    def test_template_noindex_and_placeholders_are_not_public_entries(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.put(root, "index.html", "<h1>Site</h1>")
            self.put(root, "page-template.html", '<link rel="canonical" href="https://pwanistays.com/[PAGE-SLUG]">')
            self.put(root, "bookings.html", '<meta name="robots" content="noindex,nofollow">')
            report = mod.audit(root)
            self.assertEqual(report["broken_count"], 0)
            self.assertEqual(report["counts"]["public_entry_pages"], 1)
            self.assertEqual(report["unverified_count"], 1)

    def test_symlinks_and_excluded_caches_are_not_scanned(self):
        with tempfile.TemporaryDirectory() as folder, tempfile.TemporaryDirectory() as external:
            root = Path(folder)
            self.put(root, "index.html", '<a href="/linked.html">Linked</a>')
            self.put(root, ".git/cache.html", '<img src="bad.png">')
            self.put(root, "scripts/debug.html", '<img src="bad.png">')
            outside = self.put(Path(external), "page.html", '<img src="bad.png">')
            (root / "linked.html").symlink_to(outside)
            report = mod.audit(root)
            self.assertEqual(report["counts"]["html_pages"], 1)
            self.assertEqual(report["broken_count"], 1)
            self.assertIn(report["broken"][0]["reason"], {"symbolic_target_not_audited", "target_escapes_site_root"})

    def test_cli_exit_and_report_preserve_existing_files(self):
        with tempfile.TemporaryDirectory() as folder, tempfile.TemporaryDirectory() as reports:
            root = Path(folder)
            self.put(root, "index.html", '<img src="missing.png">')
            report_path = Path(reports) / "audit.json"
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(mod.main(["--root", folder, "--report", str(report_path)]), 1)
            original = report_path.read_bytes()
            self.assertEqual(json.loads(original)["broken_count"], 1)
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(mod.main(["--root", folder, "--report", str(report_path)]), 2)
                self.assertEqual(mod.main(["--root", folder, "--report", str(root / "audit.json")]), 2)
            self.assertEqual(report_path.read_bytes(), original)
            self.assertFalse((root / "audit.json").exists())


if __name__ == "__main__":
    unittest.main()
