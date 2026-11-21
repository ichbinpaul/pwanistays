#!/usr/bin/env python3
"""Export public listing links and existing photo URLs for a catalogue integration.

This is a source snapshot, NOT a Meta hotel/product import schema. It performs
read-only requests with the site's publishable key; it never uploads photos or
modifies Supabase/Meta. See CATALOGUE-SYNC.md for activation requirements.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from urllib.parse import quote, unquote, urlencode, urlsplit
from urllib.request import Request, urlopen
import uuid

from build_property_sitemap import public_config

ROOT = Path(__file__).resolve().parents[1]
FIELDS = "id,title,location,unit_type,image_url,is_active,beds,description"
PAGE_SIZE = 100
MAX_PAGES = 1000
MAX_IMAGES = 20
REVISION = re.compile(r"^_pwani_v6_[a-f0-9]{16}$")
IMAGE = re.compile(r"\.(?:jpe?g|png|webp|avif|gif)$", re.I)


class SourceError(RuntimeError):
    """The snapshot cannot safely be refreshed."""


def request_json(base: str, key: str, path: str, body: dict | None = None):
    # The publishable key is sent only to the configured Supabase project.
    req = Request(base + path, headers={
        "apikey": key, "Accept": "application/json",
        "Content-Type": "application/json", "User-Agent": "PwaniStays-Catalogue/1.0",
    }, data=None if body is None else json.dumps(body).encode("utf-8"))
    with urlopen(req, timeout=35) as response:
        if response.status not in (200, 206):
            raise SourceError(f"Unexpected source HTTP status {response.status}")
        return json.load(response)


def fetch_properties(base: str, key: str) -> list[dict]:
    rows, seen = [], set()
    for page in range(MAX_PAGES):
        params = urlencode({"select": FIELDS, "is_active": "eq.true",
                            "order": "id.asc", "limit": PAGE_SIZE,
                            "offset": page * PAGE_SIZE})
        batch = request_json(base, key, "/rest/v1/properties?" + params)
        if not isinstance(batch, list):
            raise SourceError("Property response is not a list")
        for row in batch:
            if not isinstance(row, dict) or row.get("is_active") is not True:
                raise SourceError("Unexpected/inactive property in active listing response")
            property_id = str(uuid.UUID(str(row.get("id", ""))))
            if row.get("id") != property_id or property_id in seen:
                raise SourceError("Invalid or duplicate property ID")
            if not isinstance(row.get("title"), str) or not row["title"].strip():
                raise SourceError(f"Property {property_id} has no title")
            for field in ("location", "unit_type", "image_url"):
                if row.get(field) is not None and not isinstance(row[field], str):
                    raise SourceError(f"Property {property_id} has an invalid {field}")
            if row.get("beds") is not None and (type(row["beds"]) is not int or row["beds"] < 0):
                raise SourceError(f"Property {property_id} has invalid bed information")
            if row.get("description") is not None and not isinstance(row["description"], str):
                raise SourceError(f"Property {property_id} has an invalid description")
            rows.append(row)
            seen.add(property_id)
        if len(batch) < PAGE_SIZE:
            if not rows:
                raise SourceError("No active listings; refusing to replace the last snapshot")
            return rows
    raise SourceError("Property pagination limit reached; refusing a partial export")


def gallery_prefix(base: str, row: dict) -> str:
    property_id = row["id"]
    prefix = property_id
    parsed = urlsplit(row.get("image_url") or "")
    project = urlsplit(base)
    root = f"/storage/v1/object/public/property_images/{property_id}/"
    if parsed.scheme == "https" and parsed.netloc == project.netloc and parsed.path.startswith(root):
        remainder = unquote(parsed.path[len(root):])
        directory, separator, _ = remainder.rpartition("/")
        if separator and REVISION.fullmatch(directory):
            prefix += "/" + directory
    return prefix


def fetch_gallery(base: str, key: str, prefix: str) -> list[dict]:
    files, seen = [], set()
    for page in range(MAX_PAGES):
        batch = request_json(base, key, "/storage/v1/object/list/property_images", {
            "prefix": prefix, "limit": PAGE_SIZE, "offset": page * PAGE_SIZE,
            "sortBy": {"column": "name", "order": "asc"},
        })
        if not isinstance(batch, list):
            raise SourceError("Gallery response is not a list")
        for file in batch:
            if not isinstance(file, dict) or not isinstance(file.get("name"), str):
                raise SourceError("Malformed gallery file")
            name = file["name"]
            if name in seen:
                raise SourceError("Duplicate gallery entry across pages")
            seen.add(name)
            # Storage returns directory entries too. Never treat them as images.
            if "/" not in name and name not in (".", "..") and IMAGE.search(name):
                metadata = file.get("metadata")
                if isinstance(metadata, dict) and str(metadata.get("mimetype", "")).startswith("image/"):
                    files.append(file)
        if len(batch) < PAGE_SIZE:
            return files
    raise SourceError("Gallery pagination limit reached; refusing incomplete photos")


def photo_order(file: dict) -> tuple:
    name = file["name"]
    numbers = re.findall(r"\d+", name)
    return (int(numbers[0]) if numbers else sys.maxsize, name.casefold(), name)


def valid_photo(url: str) -> bool:
    try:
        parsed = urlsplit(url)
        return (parsed.scheme == "https" and bool(parsed.hostname)
                and parsed.username is None and parsed.password is None
                and not parsed.fragment and bool(IMAGE.search(unquote(parsed.path))))
    except ValueError:
        return False


def select_photos(base: str, row: dict, files: list[dict]) -> list[str]:
    prefix = gallery_prefix(base, row)
    urls = []
    cover = (row.get("image_url") or "").strip()
    # Use only the currently selected revision; never reintroduce archived photos.
    local_root = base + "/storage/v1/object/public/property_images/"
    expected = local_root + quote(prefix, safe="/") + "/"
    if valid_photo(cover) and (not cover.startswith(local_root) or cover.startswith(expected)):
        urls.append(cover)
    for file in sorted(files, key=photo_order):
        url = expected + quote(file["name"], safe="")
        # Ignore cache query strings when identifying duplicate URLs.
        identity = urlsplit(url)._replace(query="", fragment="").geturl()
        if any(urlsplit(item)._replace(query="", fragment="").geturl() == identity for item in urls):
            continue
        urls.append(url)
        if len(urls) == MAX_IMAGES:
            break
    return urls[:MAX_IMAGES]


def public_amenities(value: str | None) -> list[str]:
    """Keep host amenity lines, excluding legacy promotional/rate/contact captions."""
    heading = re.compile(r"^(?:(?:key|main|top|apartment|property|house|room|unit)\s+)?"
                         r"(?:amenities|facilities|features|highlights|inclusions|what you(?:'ll| will) (?:love|enjoy))"
                         r"(?:\s*(?:&|and|/)\s*(?:amenities|facilities|features|highlights))?$", re.I)
    stop = re.compile(r"^(?:location|contacts?|bookings?|reservations?|rates?|prices?|payments?|terms?|house rules|"
                      r"check[ -]?in(?:/out)?|check[ -]?out|availability|cancellation|notes?|important|nearby|how to book)$", re.I)
    sensitive = re.compile(r"\b(?:ksh|kes|usd|eur|gbp|commission|prices?|rates?|deposit|payments?|bookings?|contact|whatsapp)\b"
                           r"|\b(?:ksh|kes|usd|eur|gbp)\s*\.?\s*\d|[$€£]|\bper\s+(?:night|day|week|month)\b"
                           r"|/\s*(?:night|day|week|month)\b|\b\d[\d,.]*\s*/="
                           r"|https?://|[\w.+-]+@[\w.-]+|\+?\d[\d\s().-]{7,}", re.I)
    selected, bullets, in_section, found = [], [], False, False
    for raw in (value or "").splitlines():
        text = raw.strip()
        normalized = re.sub(r"^[\W_]+", "", text).rstrip(": ").casefold()
        if heading.fullmatch(normalized):
            in_section, found = True, True
            continue
        if stop.fullmatch(normalized) or re.match(r"^(?:dm|book|call|whatsapp|contact|inbox|message us)\b", normalized):
            in_section = False
            continue
        cleaned = re.sub(r"^(?:[-*•]\s+|\d+[.)]\s+)", "", text).strip()
        if cleaned and not sensitive.search(cleaned):
            if in_section:
                selected.append(cleaned)
            if re.match(r"^\s*•\s+", raw):
                bullets.append(cleaned)
    # dict preserves the source's ordering while avoiding repeated amenity lines.
    return list(dict.fromkeys(selected if found else bullets))[:40]


def export_property(base: str, key: str, row: dict) -> dict:
    files = fetch_gallery(base, key, gallery_prefix(base, row))
    photos = select_photos(base, row, files)
    if not photos:
        raise SourceError(f"Property {row['id']} has no usable public image URL")
    title, location = row["title"].strip(), (row.get("location") or "").strip()
    description = title + (f". Holiday accommodation in {location}." if location else ". Holiday accommodation.")
    description += " View photos and property details; contact PwaniStays for current rates and availability."
    return {"id": row["id"], "title": title, "location": location,
            "unit_type": row.get("unit_type") or "",
            "beds": row.get("beds"), "amenities": public_amenities(row.get("description")),
            "url": "https://pwanistays.com/stays/" + row["id"] + "/",
            "description": description, "images": photos}


def build_snapshot(base: str, key: str, workers: int = 4) -> dict:
    rows = fetch_properties(base, key)
    # map preserves source UUID order; a failure prevents publication of any rows.
    with ThreadPoolExecutor(max_workers=workers) as pool:
        properties = list(pool.map(lambda row: export_property(base, key, row), rows))
    return {"version": 1, "status": "source_export_only", "meta_connected": False,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "properties": properties}


def encode(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temp:
            name = temp.name
            temp.write(data)
        os.replace(name, path)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)


def save_snapshot(snapshot: dict, directory: Path) -> bool:
    output = directory / "properties.json"
    if output.exists():
        old = json.loads(output.read_text(encoding="utf-8"))
        comparable = lambda doc: {k: v for k, v in doc.items() if k != "generated_at"}
        if comparable(old) == comparable(snapshot):
            snapshot = old
    status = {"version": 1, "status": "source_export_only", "meta_connected": False,
              "generated_at": snapshot["generated_at"],
              "property_count": len(snapshot["properties"]),
              "image_count": sum(len(p["images"]) for p in snapshot["properties"]),
              "max_images_per_property": MAX_IMAGES,
              "selection": "existing_cover_then_numbered_gallery",
              "activation": "Pending Meta import schema validation and WhatsApp catalogue connection"}
    changed = False
    for path, data in ((output, encode(snapshot)), (directory / "status.json", encode(status))):
        if not path.exists() or path.read_bytes() != data:
            atomic_write(path, data)
            changed = True
    return changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "catalogue")
    parser.add_argument("--check", action="store_true", help="fetch and validate without writing")
    parser.add_argument("--workers", type=int, choices=range(1, 9), default=4)
    parser.add_argument("--routing-settings", type=Path, help="Prepare staged property routes using the immutable registry")
    args = parser.parse_args(argv)
    try:
        base, key = public_config()
        snapshot = build_snapshot(base, key, args.workers)
        copy_path = ROOT / "content/property-copy.json"
        if copy_path.exists():
            from content_copy import apply_copy
            snapshot, copy_status = apply_copy(snapshot, json.loads(copy_path.read_text(encoding="utf-8")))
            print(f"Reviewed descriptions: {len(copy_status['applied'])}; facts needing review: {len(copy_status['needs_review'])}")
            if copy_status['needs_review']:
                print("Copy skipped after listing facts changed: " + ", ".join(copy_status['needs_review']))
        registry_path = bootstrap_path = registry = bootstrap = None
        if args.routing_settings:
            # Routes stay opt-in for older callers and offline source fixtures.
            from property_routes import BOOTSTRAP_MARKER, prepare_snapshot
            registry_path = ROOT / "catalogue/property-slugs.json"
            bootstrap_path = ROOT / "property-routes.js"
            for path in [args.routing_settings, registry_path, bootstrap_path]:
                absolute = path.absolute()
                if any(part.is_symlink() for part in (absolute, *absolute.parents)):
                    raise SourceError("Routing inputs/outputs must not contain symbolic links")
                if absolute.exists() and not absolute.is_file():
                    raise SourceError("Routing inputs/outputs must be regular files")
            if bootstrap_path.exists() and not bootstrap_path.read_text(encoding="utf-8").startswith(BOOTSTRAP_MARKER + "\n"):
                raise SourceError("Refusing to overwrite an unowned property routing script")
            settings = json.loads(args.routing_settings.read_text(encoding="utf-8"))
            prior_registry = json.loads(registry_path.read_text(encoding="utf-8"))
            snapshot, registry, bootstrap = prepare_snapshot(snapshot, settings, prior_registry)
        if not args.check:
            if registry is not None:
                for path, data in [(registry_path, encode(registry)), (bootstrap_path, bootstrap.encode("utf-8"))]:
                    if not path.exists() or path.read_bytes() != data:
                        atomic_write(path, data)
            save_snapshot(snapshot, args.output_dir)
        count = len(snapshot["properties"])
        print(f"Validated {count} active properties and {sum(len(p['images']) for p in snapshot['properties'])} image URLs.")
        print("Source export only; Meta/WhatsApp connection has not been activated.")
        return 0
    except Exception as exc:
        # Never include raw HTTP response bodies or credentials in logs.
        print(f"CATALOGUE ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
