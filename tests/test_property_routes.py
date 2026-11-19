"""Offline immutable friendly-route staging and catalogue CLI checks."""
import contextlib
from copy import deepcopy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import property_routes as routes
import build_whatsapp_catalogue as builder

ID = "12345678-abcd-4321-9876-123456789012"
OTHER = "12345678-abcd-4321-9876-123456789013"
NEW = "12345678-abcd-4321-9876-123456789014"


def registry():
    return {"version": 1, "slugs": {ID: "sunny-1br-nyali", OTHER: "retired-studio-shanzu"}}


def row(identity=ID, **changes):
    value = {"id": identity, "title": "Sunny 1 Bedroom Nyali", "location": "Nyali", "unit_type": "1br",
             "description": "Explore this stay", "url": routes.SITE + "/stays/" + identity + "/",
             "images": ["https://example.supabase.co/photo.jpg"]}
    value.update(changes)
    return value


def snapshot(*rows):
    return {"version": 1, "status": "source_export_only", "meta_connected": False,
            "generated_at": "2026-11-19T00:00:00+00:00", "properties": list(rows or [row()])}


class RegistryTests(unittest.TestCase):
    def test_registry_validation_is_strict_and_returns_independent_mapping(self):
        prior = registry()
        checked = routes.validate_registry(prior)
        self.assertEqual(checked, prior["slugs"])
        checked[ID] = "changed"
        self.assertEqual(prior["slugs"][ID], "sunny-1br-nyali")
        invalid = [{"version": True, "slugs": {}}, {"version": 1, "slugs": []},
                   {"version": 1, "slugs": {}, "ready_for_redirects": "false"},
                   {"version": 1, "slugs": {"broken": "sunny"}},
                   {"version": 1, "slugs": {ID: "duplicate", OTHER: "duplicate"}}]
        invalid += [{"version": 1, "slugs": {ID: slug}} for slug in
                    ["", "x" * 33, "../outside", "index", "index-html", "Uppercase", "café", "has space", False]]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                routes.validate_registry(value)

    def test_canonical_url_honors_staging_and_only_known_property_urls(self):
        uuid_url = routes.SITE + "/stays/" + ID + "/"
        friendly_url = routes.SITE + "/stays/sunny-1br-nyali/"
        self.assertEqual(routes.canonical_url({"id": ID}), uuid_url)
        self.assertEqual(routes.canonical_url(row(slug="sunny-1br-nyali")), uuid_url)
        self.assertEqual(routes.canonical_url(row(url=routes.SITE + "/property.html?id=" + ID)), uuid_url)
        self.assertEqual(routes.canonical_url(row(slug="sunny-1br-nyali", url=friendly_url)), friendly_url)
        for url in [friendly_url, uuid_url + "?guests=2", uuid_url.rstrip("/"),
                    routes.SITE + "/property.html?id=" + OTHER, "https://elsewhere.example/", uuid_url + "#other"]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                routes.canonical_url(row(url=url))
        with self.assertRaises(ValueError):
            routes.canonical_url(row(slug="../unsafe"))

    def test_friendly_route_requires_explicit_boolean_and_known_assignment(self):
        self.assertEqual(routes.routing_path(ID, registry()), "/stays/" + ID + "/")
        self.assertEqual(routes.routing_path(ID, registry(), True), "/stays/sunny-1br-nyali/")
        self.assertEqual(routes.routing_path(NEW, registry()), "/stays/" + NEW + "/")
        for identity, enabled in [(NEW, True), (ID, "false"), (ID, 1)]:
            with self.subTest(identity=identity, enabled=enabled), self.assertRaises(ValueError):
                routes.routing_path(identity, registry(), enabled)


class PreparationTests(unittest.TestCase):
    def test_staging_preserves_uuid_canonicals_and_input_metadata(self):
        source, prior = snapshot(), registry()
        source["custom"] = {"preserve": [1, 2]}
        source["properties"][0]["custom_row"] = {"keep": True}
        prior["note"] = "Retain this registry metadata"
        before_source, before_prior = deepcopy(source), deepcopy(prior)
        prepared, updated, bootstrap = routes.prepare_snapshot(source, {"version": 1, "use_friendly_urls": False}, prior)
        self.assertEqual(source, before_source)
        self.assertEqual(prior, before_prior)
        self.assertEqual(prepared["properties"][0]["slug"], prior["slugs"][ID])
        self.assertEqual(prepared["properties"][0]["url"], row()["url"])
        self.assertEqual(prepared["custom"], source["custom"])
        self.assertEqual(prepared["properties"][0]["custom_row"], {"keep": True})
        self.assertEqual(updated["note"], prior["note"])
        self.assertIs(updated["ready_for_redirects"], False)
        self.assertTrue(bootstrap.startswith(routes.BOOTSTRAP_MARKER + "\n"))
        payload = json.loads(bootstrap.split(" = ", 1)[1].removesuffix(";\n"))
        self.assertFalse(payload["enabled"])
        self.assertIn(OTHER, payload["paths"])

    def test_activation_is_opt_in_and_title_changes_never_rename_existing_units(self):
        prepared, updated, _ = routes.prepare_snapshot(snapshot(), {"version": 1, "use_friendly_urls": True}, registry())
        self.assertIs(updated["ready_for_redirects"], True)
        self.assertEqual(prepared["properties"][0]["url"], routes.SITE + "/stays/sunny-1br-nyali/")
        prepared["properties"][0]["title"] = "A completely different title and location"
        again, after, _ = routes.prepare_snapshot(prepared, {"version": 1, "use_friendly_urls": True}, updated)
        self.assertEqual(after, updated)
        self.assertEqual(again["properties"][0]["url"], prepared["properties"][0]["url"])

    def test_new_units_get_unique_stable_slugs_without_reusing_withdrawn_names(self):
        prior = registry()
        source = snapshot(row(NEW), row(ID))
        prepared, updated, first = routes.prepare_snapshot(source, {"version": 1, "use_friendly_urls": False}, prior)
        self.assertEqual(updated["slugs"][ID], prior["slugs"][ID])
        self.assertEqual(updated["slugs"][OTHER], prior["slugs"][OTHER])
        self.assertNotEqual(updated["slugs"][NEW], prior["slugs"][ID])
        self.assertLessEqual(len(updated["slugs"][NEW]), 32)
        again, after, second = routes.prepare_snapshot(prepared, {"version": 1, "use_friendly_urls": False}, updated)
        self.assertEqual((again, after, second), (prepared, updated, first))

    def test_conflicts_invalid_activation_and_empty_sources_are_rejected(self):
        for settings in [{}, {"version": 1, "use_friendly_urls": "false"}, {"version": True, "use_friendly_urls": False}]:
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                routes.prepare_snapshot(snapshot(), settings, registry())
        for source in [snapshot(row(slug="different")), {"version": 1, "properties": []}, snapshot(row(ID), row(ID))]:
            with self.subTest(source=source), self.assertRaises(ValueError):
                routes.prepare_snapshot(source, {"version": 1, "use_friendly_urls": False}, registry())


class CatalogueCliTests(unittest.TestCase):
    def setup_files(self, folder):
        root = Path(folder)
        (root / "catalogue").mkdir()
        (root / "catalogue/property-slugs.json").write_text(json.dumps(registry()))
        settings = root / "settings.json"
        settings.write_text(json.dumps({"version": 1, "use_friendly_urls": False}))
        return root, settings, root / "public-source"

    def invoke(self, root, settings, output, *flags, source=None):
        with patch.object(builder, "ROOT", root), patch.object(builder, "public_config", return_value=("https://example.supabase.co", "public-key")), \
                patch.object(builder, "build_snapshot", return_value=source or snapshot(row(ID), row(NEW))), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return builder.main(["--routing-settings", str(settings), "--output-dir", str(output)] + list(flags))

    def test_check_mode_does_not_create_source_registry_changes_or_bootstrap(self):
        with tempfile.TemporaryDirectory() as folder:
            root, settings, output = self.setup_files(folder)
            before = (root / "catalogue/property-slugs.json").read_bytes()
            self.assertEqual(self.invoke(root, settings, output, "--check"), 0)
            self.assertFalse(output.exists())
            self.assertFalse((root / "property-routes.js").exists())
            self.assertEqual((root / "catalogue/property-slugs.json").read_bytes(), before)

    def test_normal_run_is_repeatable_without_timestamp_only_churn(self):
        with tempfile.TemporaryDirectory() as folder:
            root, settings, output = self.setup_files(folder)
            self.assertEqual(self.invoke(root, settings, output), 0)
            paths = [output / "properties.json", output / "status.json", root / "property-routes.js", root / "catalogue/property-slugs.json"]
            before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in paths}
            later = snapshot(row(ID), row(NEW))
            later["generated_at"] = "2026-11-20T00:00:00+00:00"
            self.assertEqual(self.invoke(root, settings, output, source=later), 0)
            self.assertEqual({path: (path.read_bytes(), path.stat().st_mtime_ns) for path in paths}, before)
            saved = json.loads((output / "properties.json").read_text())
            self.assertTrue(all(row["url"].endswith("/" + row["id"] + "/") and row.get("slug") for row in saved["properties"]))

    def test_unknown_bootstrap_and_symbolic_routing_paths_preserve_user_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root, settings, output = self.setup_files(folder)
            script = root / "property-routes.js"
            script.write_text("window.userScript = true;")
            self.assertEqual(self.invoke(root, settings, output), 1)
            self.assertEqual(script.read_text(), "window.userScript = true;")
            self.assertFalse(output.exists())
            script.unlink()
            original = root / "user-script.js"
            original.write_text("Preserve this")
            script.symlink_to(original)
            self.assertEqual(self.invoke(root, settings, output), 1)
            self.assertEqual(original.read_text(), "Preserve this")
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
