#!/usr/bin/env python3
"""Prepare immutable title-based property URL assignments for review only.

No active pages, internal links, canonical URLs, hosting rules or remote accounts
are changed. A CSV status_code of 301 describes the proposed redirect, not an
HTTP redirect that this script has installed.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
from pathlib import Path
import re
import sys
import unicodedata
import uuid

from build_whatsapp_catalogue import atomic_write

ROOT = Path(__file__).resolve().parents[1]
SITE = "https://pwanistays.com"
MAX_LENGTH = 32
RESERVED = {"index", "index-html", "new", "search", "feed", "assets", "images", "directory", "stays", "properties", "property"}
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
UUID_NAME = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}")


class PlanError(ValueError):
    """The source or registry cannot safely yield an immutable URL plan."""


def canonical_uuid(value):
    try:
        if not isinstance(value, str) or str(uuid.UUID(value)) != value:
            raise ValueError
    except (ValueError, AttributeError):
        raise PlanError("Property IDs must be canonical UUIDs") from None
    return value


def words(value):
    if not isinstance(value, str):
        raise PlanError("Titles, locations and accommodation types must be text")
    value = unicodedata.normalize("NFKD", value)
    # Separate punctuation before ASCII conversion so Studio–Bamburi cannot merge.
    value = "".join(" " if unicodedata.category(character).startswith(("P", "S")) else character for character in value)
    value = value.encode("ascii", "ignore").decode().lower()
    for name, number in {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5"}.items():
        value = re.sub(rf"\b{name}\s+(?=bed\s*rooms?\b|bedrooms?\b)", number + " ", value)
    value = re.sub(r"\b([0-9]+)\s*(?:bed\s*rooms?|bedrooms?|br)\b", r"\1br", value)
    return re.findall(r"[a-z0-9]+", value)


def clip(value, limit):
    if len(value) <= limit:
        return value
    value = value[:limit].rstrip("-")
    return value.rsplit("-", 1)[0] if "-" in value else value


def slugify(title, location, unit_type, max_length=MAX_LENGTH):
    if type(max_length) is not int or max_length < 8 or max_length > MAX_LENGTH:
        raise PlanError("Slug length must be between 8 and 32")
    tokens = words(title)
    place, kind = words("" if location is None else location), words("" if unit_type is None else unit_type)
    if len(place) > 1:
        place = [word for word in place if word != "mombasa"]
    if place and place != ["mombasa"]:
        tokens = [word for word in tokens if word != "mombasa"]
    place_set = set(place)
    tokens = [word for word in tokens if word not in place_set and word not in {"airbnb", "fully", "furnished", "fullyfurnished"}]
    kind_word = next((word for word in tokens if word in {"studio", "villa"} or re.fullmatch(r"[0-9]+br", word)), None)
    if kind_word is None:
        kind_word = next((word for word in kind if word in {"studio", "villa"} or re.fullmatch(r"[0-9]+br", word)), None)
        if kind_word:
            tokens.append(kind_word)
    if kind_word:
        tokens = [word for word in tokens if word not in {"apartment", "apartments"}]
    # Remove adjacent repeated words without rewriting the property's identity.
    tokens = [word for index, word in enumerate(tokens) if index == 0 or word != tokens[index - 1]]
    result = "-".join(tokens + place)
    if len(result) > max_length:
        # Preserve the known accommodation type and location while shortening descriptors.
        suffix = "-".join(([kind_word] if kind_word else []) + place)
        if len(suffix) >= max_length:
            result = clip(suffix, max_length)
        else:
            descriptors = "-".join(word for word in tokens if word != kind_word)
            leading = clip(descriptors, max_length - len(suffix) - (1 if suffix else 0))
            result = "-".join(part for part in (leading, suffix) if part)
    result = result or "stay"
    if result in RESERVED or UUID_NAME.fullmatch(result):
        result = clip("stay-" + result, max_length)
    if not SLUG.fullmatch(result) or len(result) > max_length:
        raise PlanError("Could not derive a safe property slug")
    return result


def validated_rows(rows):
    if not isinstance(rows, list) or not rows:
        raise PlanError("A nonempty property source is required")
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            raise PlanError("Malformed property record")
        property_id = canonical_uuid(row.get("id"))
        if property_id in seen:
            raise PlanError("Duplicate property ID in source")
        seen.add(property_id)
        if row.get("is_active", True) is not True:
            raise PlanError("Property source must contain active units only")
        if not isinstance(row.get("title"), str) or not row["title"].strip():
            raise PlanError("Each property needs a nonempty title")
        for key in ("location", "unit_type"):
            if row.get(key) is not None and not isinstance(row[key], str):
                raise PlanError("Optional locations and accommodation types must be text or null")
    return sorted(rows, key=lambda row: row["id"])


def allocate(rows, existing_registry=None):
    rows = validated_rows(rows)
    if existing_registry is None:
        existing_registry = {"version": 1, "slugs": {}}
    if (not isinstance(existing_registry, dict) or type(existing_registry.get("version")) is not int
            or existing_registry["version"] != 1 or not isinstance(existing_registry.get("slugs"), dict)):
        raise PlanError("Unsupported immutable slug registry")
    assigned, used = {}, set()
    for property_id, slug in existing_registry["slugs"].items():
        canonical_uuid(property_id)
        if (not isinstance(slug, str) or not SLUG.fullmatch(slug) or len(slug) > MAX_LENGTH
                or slug in RESERVED or UUID_NAME.fullmatch(slug) or slug in used):
            raise PlanError("Registry contains an unsafe, reserved or duplicate slug")
        assigned[property_id] = slug
        used.add(slug)
    for row in rows:
        property_id = row["id"]
        if property_id in assigned:
            continue
        base = slugify(row["title"], row.get("location") or "", row.get("unit_type") or "")
        candidate = base
        if candidate in used:
            compact_id = property_id.replace("-", "")
            for length in range(6, MAX_LENGTH - 1):
                suffix = compact_id[:length]
                budget = MAX_LENGTH - len(suffix) - 1
                # Re-shorten descriptors so a collision does not drop the location.
                shortened = (slugify(row["title"], row.get("location") or "", row.get("unit_type") or "", budget)
                             if budget >= 8 else clip(base, budget))
                candidate = shortened + "-" + suffix
                if candidate not in used:
                    break
            else:
                raise PlanError("Cannot allocate a unique short slug without renaming existing URLs")
        assigned[property_id] = candidate
        used.add(candidate)
    return {"version": 1, "slugs": dict(sorted(assigned.items()))}


def plan(source, registry=None):
    if not isinstance(source, dict) or type(source.get("version")) is not int or source["version"] != 1:
        raise PlanError("Unsupported public source snapshot version")
    rows = validated_rows(source.get("properties"))
    updated = allocate(rows, registry)
    changes = [{"id": row["id"], "title": row["title"],
                "old_url": f"{SITE}/stays/{row['id']}/",
                "new_url": f"{SITE}/stays/{updated['slugs'][row['id']]}/", "status_code": 301}
               for row in rows]
    collision_suffixes = sum(
        bool(re.fullmatch(r"[a-f0-9]{6,30}", slug.rsplit("-", 1)[-1])) and
        property_id.replace("-", "").startswith(slug.rsplit("-", 1)[-1])
        for property_id, slug in updated["slugs"].items())
    return {"registry": updated, "rows": changes,
            "summary": {"mode": "preparation_only", "active_properties": len(rows),
                        "retained_inactive_assignments": len(updated["slugs"]) - len(rows),
                        "registry_assignments": len(updated["slugs"]),
                        "collision_suffixes": collision_suffixes,
                        "max_slug_length": max(map(len, updated["slugs"].values())),
                        "active_urls_changed": False, "redirects_deployed": False,
                        "activation_requirement": "Deploy targets and verify genuine hosting HTTP 301 redirects before migrating canonical URLs"}}


def output_is_safe(directory):
    directory = directory.absolute()
    if directory.resolve().is_relative_to(ROOT.resolve()):
        raise PlanError("Review artifacts must be outside the website checkout")
    if any(path.is_symlink() for path in (directory, *directory.parents)):
        raise PlanError("Output paths must not contain symbolic links")
    if directory.exists() and (not directory.is_dir() or any(directory.iterdir())):
        raise PlanError("Output must be a new or empty directory")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "catalogue/properties.json")
    parser.add_argument("--registry", type=Path, help="previous review registry; retain it to preserve assigned URLs")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        output_is_safe(args.output_dir)
        source = json.loads(args.source.read_text(encoding="utf-8"))
        registry = json.loads(args.registry.read_text(encoding="utf-8")) if args.registry else None
        result = plan(source, registry)
        csv_output = io.StringIO(newline="")
        writer = csv.DictWriter(csv_output, fieldnames=["id", "title", "old_url", "new_url", "status_code"])
        writer.writeheader()
        # Review files may be opened in a spreadsheet; titles are plain text.
        writer.writerows({**row, "title": "'" + row["title"] if
                          row["title"].lstrip().startswith(("=", "+", "-", "@")) or ord(row["title"][0]) < 32
                          else row["title"]} for row in result["rows"])
        contents = {"property-slugs.json": json.dumps(result["registry"], ensure_ascii=False, indent=2) + "\n",
                    "url-migration.csv": csv_output.getvalue(),
                    "summary.json": json.dumps(result["summary"], indent=2) + "\n"}
        for filename, content in contents.items():
            atomic_write(args.output_dir / filename, content.encode("utf-8"))
        print(json.dumps(result["summary"]))
        return 0
    except PlanError as exc:
        print(f"URL PLAN ERROR: {exc}", file=sys.stderr)
        return 1
    except (OSError, ValueError):
        print("URL PLAN ERROR: Review input/output could not be processed safely", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
