#!/usr/bin/env python3
"""Generate a public property sitemap from active PwaniStays Supabase listings.

Only reads public UUIDs via the same publishable client configuration as the
website. No service-role key is used, and no database records are modified.

Usage: python3 scripts/build_property_sitemap.py
Returns nonzero on API errors, leaving the existing sitemap intact.
"""
from __future__ import annotations

import json
import argparse
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from xml.etree import ElementTree as ET
from property_routes import canonical_url

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "listing-utils.js"
OUTPUT = ROOT / "property-sitemap.xml"
ROBOTS = ROOT / "robots.txt"
SITE_BASE = "https://pwanistays.com"
SITEMAP_URL = SITE_BASE + "/property-sitemap.xml"
NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
IMAGE_NS = "http://www.google.com/schemas/sitemap-image/1.1"
MAX_ITEMS = 1000
MAX_PAGES = 1000


def public_config() -> tuple[str, str]:
    source = CONFIG.read_text(encoding="utf-8")
    url_match = re.search(r"const\s+SUPABASE_URL\s*=\s*['\"](https://[^'\"]+)['\"]", source)
    key_match = re.search(r"const\s+PUBLISHABLE_KEY\s*=\s*['\"]([^'\"]+)['\"]", source)
    if not url_match or not key_match:
        raise ValueError("Missing public Supabase URL/key in listing-utils.js")
    url = url_match.group(1).rstrip("/")
    if not url.endswith(".supabase.co"):
        raise ValueError("Unexpected Supabase host; refusing to fetch")
    return url, key_match.group(1)


def fetch_active_ids(base_url: str, public_key: str) -> list[str]:
    ids: set[str] = set()
    for page in range(MAX_PAGES):
        params = urllib.parse.urlencode({
            "select": "id", "is_active": "eq.true", "order": "id.asc",
            "limit": MAX_ITEMS, "offset": page * MAX_ITEMS
        })
        req = urllib.request.Request(
            f"{base_url}/rest/v1/properties?{params}",
            headers={"apikey": public_key, "Accept": "application/json",
                     "User-Agent": "PwaniStays-Sitemap-Bot/1.0"}
        )
        with urllib.request.urlopen(req, timeout=35) as response:
            if response.status not in (200, 206):
                raise RuntimeError(f"Unexpected Supabase HTTP status {response.status}")
            rows = json.load(response)
        if not isinstance(rows, list):
            raise ValueError("Supabase response was not a JSON list")
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("Malformed listing row")
            property_id = str(uuid.UUID(str(row["id"])))
            if property_id in ids:
                raise ValueError("Duplicate property UUID across API pages")
            ids.add(property_id)
        if len(rows) < MAX_ITEMS:
            return sorted(ids)
    raise RuntimeError("Too many listing pages; refusing incomplete sitemap")


def render_sitemap(ids: list[str], images: dict[str, str] | None = None,
                   urls: dict[str, str] | None = None) -> bytes:
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate property UUID in sitemap")
    if urls is not None and (not isinstance(urls, dict) or set(urls) - set(ids)):
        raise ValueError("Sitemap URL mapping contains unknown property IDs")
    canonical_urls = {}
    for property_id in ids:
        row = {"id": property_id}
        if urls and property_id in urls:
            candidate = urls[property_id]
            if not isinstance(candidate, str):
                raise ValueError("Invalid sitemap URL")
            row["url"] = candidate
            prefix = SITE_BASE + "/stays/"
            if candidate.startswith(prefix) and candidate.endswith("/"):
                # The mapping already associates each canonical URL with its ID.
                # Reuse the shared route validator for its URL/slug syntax.
                segment = candidate[len(prefix):-1]
                if segment != property_id:
                    row["slug"] = segment
        canonical_urls[property_id] = canonical_url(row)
    if len(set(canonical_urls.values())) != len(ids):
        raise ValueError("Multiple properties resolve to the same sitemap URL")
    ET.register_namespace("", NS)
    ET.register_namespace("image", IMAGE_NS)
    urlset = ET.Element(f"{{{NS}}}urlset")
    for property_id in ids:
        node = ET.SubElement(urlset, f"{{{NS}}}url")
        ET.SubElement(node, f"{{{NS}}}loc").text = canonical_urls[property_id]
        if images and property_id in images:
            image = ET.SubElement(node, f"{{{IMAGE_NS}}}image")
            ET.SubElement(image, f"{{{IMAGE_NS}}}loc").text = images[property_id]
    ET.indent(urlset, space="  ")
    return ET.tostring(urlset, encoding="utf-8", xml_declaration=True) + b"\n"


def update_robots() -> None:
    current = ROBOTS.read_text(encoding="utf-8")
    directive = f"Sitemap: {SITEMAP_URL}"
    if directive not in current:
        ROBOTS.write_text(current.rstrip() + "\n" + directive + "\n", encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, help="Use the same public snapshot as generated property pages")
    parser.add_argument("--covers", type=Path, help="Include validated website-owned cover image URLs")
    args = parser.parse_args(argv)
    try:
        images, urls = None, None
        if args.source:
            snapshot = json.loads(args.source.read_text(encoding="utf-8"))
            rows = snapshot.get("properties")
            if snapshot.get("version") != 1 or not isinstance(rows, list):
                raise ValueError("Invalid public property snapshot")
            urls = {row["id"]: canonical_url(row) for row in rows}
            ids = [row["id"] for row in rows]
            if len(set(ids)) != len(ids):
                raise ValueError("Duplicate property UUID in snapshot")
            if len(set(urls.values())) != len(ids):
                raise ValueError("Multiple properties resolve to the same canonical URL")
            ids.sort()
            if args.covers:
                from build_property_previews import load_cover_images
                enriched = load_cover_images(snapshot, args.covers)
                images = {row["id"]: row["seo_image"] for row in enriched["properties"]}
        else:
            if args.covers:
                raise ValueError("A cover image sitemap requires its complete public source snapshot")
            base_url, key = public_config()
            ids = fetch_active_ids(base_url, key)
        # An empty response could reflect a broken policy or a transient
        # configuration issue. Do not erase a previously working sitemap.
        if not ids:
            raise RuntimeError("No active listings returned; refusing empty sitemap")
        xml = render_sitemap(ids, images, urls)
        if not OUTPUT.exists() or OUTPUT.read_bytes() != xml:
            OUTPUT.write_bytes(xml)
        update_robots()
        print(f"Generated sitemap for {len(ids)} active property IDs")
        return 0
    except Exception as exc:
        print(f"SITEMAP ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
