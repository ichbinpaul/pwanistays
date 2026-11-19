"""Offline preparation checks; existing public URLs and redirects are unchanged."""
import contextlib
import copy
import csv
import io
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import plan_property_urls as mod

ID = "aaaaaaaa-0000-4000-8000-000000000001"
OTHER = "aaaaaaaa-0000-4000-8000-000000000002"
THIRD = "aaaaaaaa-0000-4000-8000-000000000003"


def row(property_id=ID, title="Cozy Studio Apartment – Bamburi, Mombasa"):
    return {"id": property_id, "title": title, "location": "Bamburi", "unit_type": "studio"}


def source(*rows):
    return {"version": 1, "properties": list(rows or [row()])}


class SlugTests(unittest.TestCase):
    def test_user_example_and_known_type_remove_filler_and_generic_city(self):
        self.assertEqual(mod.slugify(row()["title"], "Bamburi", "studio"), "cozy-studio-bamburi")
        self.assertEqual(mod.slugify("Cozy 2 Bedrooms Fully Furnished Airbnb Apartment – Bamburi, Mombasa",
                                     "Bamburi", "2br"), "cozy-2br-bamburi")
        self.assertEqual(mod.slugify("Airbnb Fully Furnished Apartment", "Nyali", "1br"), "1br-nyali")
        self.assertEqual(mod.slugify("Cozy Studio Apartment, Mombasa", "Mombasa", "studio"), "cozy-studio-mombasa")

    def test_punctuation_accents_and_long_names_are_safe_short_and_location_retained(self):
        self.assertEqual(mod.slugify("Café Studio–Bamburi", "Bamburi", "studio"), "cafe-studio-bamburi")
        for title in ["<script>alert(1)</script> Studio", "🌊 海景 Studio", "A" * 300 + " Studio"]:
            slug = mod.slugify(title, "Bamburi", "studio")
            self.assertLessEqual(len(slug), 32)
            self.assertRegex(slug, r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
            self.assertTrue(slug.endswith("studio-bamburi"))
        for invalid in [0, 33, True, "32"]:
            with self.subTest(invalid=invalid), self.assertRaises(mod.PlanError):
                mod.slugify("Cozy studio", "Bamburi", "studio", invalid)


class RegistryTests(unittest.TestCase):
    def test_title_only_properties_have_stable_urls_without_optional_facts(self):
        minimal = {"id": ID, "title": "Cozy Studio"}
        first = mod.allocate([minimal])
        self.assertEqual(first["slugs"][ID], "cozy-studio")
        for value in [{**minimal, "location": None, "unit_type": None},
                      {**minimal, "location": "", "unit_type": ""},
                      {**minimal, "title": "Renamed stay", "location": "Nyali", "unit_type": "villa"}]:
            self.assertEqual(mod.allocate([value], first), first)
        self.assertEqual(mod.slugify("Cozy Studio", None, None), "cozy-studio")
        for key, value in [("location", []), ("unit_type", {}), ("location", False)]:
            with self.subTest(key=key, value=value), self.assertRaises(mod.PlanError):
                mod.allocate([{**minimal, key: value}])

    def test_collision_suffix_only_and_prefix_collision_adapts_without_renaming(self):
        first = mod.allocate([row()])
        second = mod.allocate([row(), row(OTHER)], first)
        third = mod.allocate([row(), row(OTHER), row(THIRD)], second)
        self.assertEqual(first["slugs"][ID], "cozy-studio-bamburi")
        self.assertEqual(second["slugs"][OTHER], "cozy-studio-bamburi-aaaaaa")
        self.assertEqual(third["slugs"][THIRD], "cozy-studio-bamburi-aaaaaaa")
        self.assertEqual(third["slugs"][OTHER], second["slugs"][OTHER])
        self.assertEqual(third["slugs"][ID], first["slugs"][ID])

    def test_initial_allocation_and_updates_ignore_source_order(self):
        rows = [row(), row(OTHER), row(THIRD)]
        self.assertEqual(mod.allocate(rows), mod.allocate(list(reversed(rows))))
        existing = mod.allocate(rows)
        self.assertEqual(mod.allocate(rows, existing), mod.allocate(list(reversed(rows)), existing))

    def test_title_change_withdrawal_reactivation_and_new_collision_preserve_registry(self):
        first = mod.allocate([row()])
        retained = mod.allocate([row(OTHER)], first)
        changed = row(title="Renamed luxury villa")
        changed["unit_type"] = "villa"
        returned = mod.allocate([changed, row(OTHER)], retained)
        self.assertEqual(returned["slugs"][ID], first["slugs"][ID])
        self.assertNotEqual(returned["slugs"][OTHER], first["slugs"][ID])
        self.assertEqual(mod.plan(source(row(OTHER)), first)["summary"]["retained_inactive_assignments"], 1)

    def test_registry_is_not_mutated_and_existing_reserved_names_are_rejected(self):
        existing = {"version": 1, "slugs": {ID: "cozy-studio-bamburi"}}
        original = copy.deepcopy(existing)
        mod.allocate([row(), row(OTHER)], existing)
        self.assertEqual(existing, original)
        bad = [{}, {"version": True, "slugs": {}}, {"version": 2, "slugs": {}},
               {"version": 1, "slugs": {"../unsafe": "name"}}]
        for slug in ["../unsafe", "Uppercase", "two words", "a" * 33, "index", ID, "name?token=x", ""]:
            bad.append({"version": 1, "slugs": {ID: slug}})
        bad.append({"version": 1, "slugs": {ID: "same", OTHER: "same"}})
        for registry in bad:
            with self.subTest(registry=registry), self.assertRaises(mod.PlanError):
                mod.allocate([row()], registry)

    def test_long_collisions_stay_within_limit(self):
        long = "Extremely luxurious panoramic magnificent spacious studio apartment"
        registry = mod.allocate([row(title=long), row(OTHER, title=long), row(THIRD, title=long)])
        self.assertTrue(all("bamburi" in slug for slug in registry["slugs"].values()))
        self.assertEqual(len(set(registry["slugs"].values())), 3)
        self.assertTrue(all(len(slug) <= 32 for slug in registry["slugs"].values()))


class PlanTests(unittest.TestCase):
    def test_plan_contains_proposed_301_not_a_live_migration(self):
        result = mod.plan(source())
        self.assertEqual(result["rows"][0]["old_url"], f"https://pwanistays.com/stays/{ID}/")
        self.assertEqual(result["rows"][0]["new_url"], "https://pwanistays.com/stays/cozy-studio-bamburi/")
        self.assertEqual(result["rows"][0]["status_code"], 301)
        self.assertFalse(result["summary"]["active_urls_changed"])
        self.assertFalse(result["summary"]["redirects_deployed"])

    def test_review_summary_counts_uuid_suffixes_and_slug_length(self):
        result = mod.plan(source(row(), row(OTHER), row(THIRD)))
        self.assertEqual(result["summary"]["collision_suffixes"], 2)
        self.assertEqual(result["summary"]["max_slug_length"],
                         max(map(len, result["registry"]["slugs"].values())))

    def test_invalid_source_cannot_reset_history(self):
        bad = [{}, {"version": 1, "properties": []}, source(row(), row())]
        for changes in [{"id": "bad"}, {"title": ""}, {"location": []}, {"unit_type": []}, {"is_active": False}]:
            value = row()
            value.update(changes)
            bad.append(source(value))
        for value in bad:
            with self.subTest(value=value), self.assertRaises(mod.PlanError):
                mod.plan(value)

    def test_cli_artifacts_only_new_external_directory_and_no_overwrites(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source_path = root / "source.json"
            source_path.write_text(json.dumps(source()))
            output = root / "review"
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(mod.main(["--source", str(source_path), "--output-dir", str(output)]), 0)
            self.assertEqual({path.name for path in output.iterdir()},
                             {"property-slugs.json", "url-migration.csv", "summary.json"})
            saved = {path.name: path.read_bytes() for path in output.iterdir()}
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(mod.main(["--source", str(source_path), "--output-dir", str(output)]), 1)
            self.assertEqual(saved, {path.name: path.read_bytes() for path in output.iterdir()})
            unsafe = mod.ROOT / "url-plan-test-must-not-be-created"
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(mod.main(["--source", str(source_path), "--output-dir", str(unsafe)]), 1)
            self.assertFalse(unsafe.exists())

    def test_cli_consumes_existing_registry_and_csv_titles_are_plain_text(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source_path, registry_path = root / "source.json", root / "registry.json"
            source_path.write_text(json.dumps(source(row(title="=IMPORTXML malicious title"))))
            registry_path.write_text(json.dumps({"version": 1, "slugs": {ID: "original-title-bamburi"}}))
            output = root / "review"
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(mod.main(["--source", str(source_path), "--registry", str(registry_path),
                                           "--output-dir", str(output)]), 0)
            registry = json.loads((output / "property-slugs.json").read_text())
            self.assertEqual(registry["slugs"][ID], "original-title-bamburi")
            rows = list(csv.DictReader(io.StringIO((output / "url-migration.csv").read_text())))
            self.assertTrue(rows[0]["title"].startswith("'="))


if __name__ == "__main__":
    unittest.main()
