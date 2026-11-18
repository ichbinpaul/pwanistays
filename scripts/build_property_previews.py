#!/usr/bin/env python3
"""Build unit-specific HTML/preview metadata for static hosting and chat crawlers.

Reads the existing public catalogue export. It does not fetch private data or
modify Meta, WhatsApp, Supabase, or unrelated website pages.
"""
from __future__ import annotations

import argparse
import hashlib
from html import escape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlencode, urlsplit
import uuid

from build_whatsapp_catalogue import atomic_write, valid_photo

ROOT = Path(__file__).resolve().parents[1]
MARKER = "<!-- PWANISTAYS_PROPERTY_PREVIEW_V1 -->"
SITE = "https://pwanistays.com"


class PreviewError(RuntimeError):
    """The export cannot be safely regenerated."""


def canonical_uuid(value):
    try:
        if not isinstance(value, str) or str(uuid.UUID(value)) != value:
            raise ValueError
    except (ValueError, AttributeError):
        raise PreviewError("Property IDs must be canonical UUIDs") from None
    return value


def property_url(property_id):
    return f"{SITE}/stays/{property_id}/"


def cover_path(image_url, property_id):
    if not isinstance(image_url, str):
        raise PreviewError("Cached cover URL must be text")
    parsed = urlsplit(image_url)
    pattern = rf"/images/property-covers/{re.escape(property_id)}-([a-f0-9]{{16}})\.(?:jpe?g|png|webp|avif|gif)"
    match = re.fullmatch(pattern, parsed.path)
    if not match or image_url != SITE + parsed.path:
        raise PreviewError("Cached cover URL must use the same property's canonical website image path")
    return parsed.path.lstrip("/"), match.group(1)


def validate_source(snapshot):
    if not isinstance(snapshot, dict) or type(snapshot.get("version")) is not int or snapshot["version"] != 1:
        raise PreviewError("Unsupported public catalogue snapshot version")
    rows = snapshot.get("properties")
    if not isinstance(rows, list) or not rows:
        raise PreviewError("No active properties; refusing to replace existing previews")
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            raise PreviewError("Malformed public property record")
        property_id = canonical_uuid(row.get("id"))
        if property_id in seen:
            raise PreviewError("Duplicate public property UUID")
        seen.add(property_id)
        if row.get("is_active", True) is not True:
            raise PreviewError("Public catalogue contains an inactive property")
        for field in ("title", "description"):
            if not isinstance(row.get(field), str) or not row[field].strip():
                raise PreviewError("Public title and description are required")
        for field in ("location", "unit_type"):
            if row.get(field) is not None and not isinstance(row[field], str):
                raise PreviewError("Public location and accommodation type must be text")
        beds = row.get("beds")
        if beds is not None and (type(beds) is not int or beds < 0):
            raise PreviewError("Public bed count must be a nonnegative integer or null")
        amenities = row.get("amenities", [])
        if not isinstance(amenities, list) or any(not isinstance(item, str) or not item.strip() for item in amenities):
            raise PreviewError("Public amenities must be a list of nonempty text values")
        if row.get("url") not in {property_url(property_id), f"{SITE}/property.html?id={property_id}"}:
            raise PreviewError("Property URL is not a recognised public property link")
        images = row.get("images")
        if (not isinstance(images, list) or not 1 <= len(images) <= 10 or
                any(not isinstance(url, str) or not valid_photo(url) for url in images) or
                len(set(images)) != len(images)):
            raise PreviewError("Each property needs one to ten distinct public HTTPS image URLs")
        if "seo_image" in row or "seo_source" in row:
            cover_path(row.get("seo_image"), property_id)
            if row.get("seo_source") != images[0]:
                raise PreviewError("Cached cover source must match the designated original cover URL")
    return sorted(rows, key=lambda row: row["id"])


def load_cover_images(snapshot, manifest, root=ROOT):
    """Return a copy with validated local SEO covers; never change source photos.

    manifest may be a parsed object or a path. Once supplied, every active unit
    needs a matching, hash-verified original-byte image in the website checkout.
    """
    rows = validate_source(snapshot)
    if isinstance(manifest, (str, Path)):
        manifest = json.loads(Path(manifest).read_text(encoding="utf-8"))
    if (not isinstance(manifest, dict) or type(manifest.get("version")) is not int
            or manifest["version"] != 1 or not isinstance(manifest.get("covers"), dict)):
        raise PreviewError("Unsupported property cover manifest")
    updated = []
    root = Path(root)
    for row in rows:
        cover = manifest["covers"].get(row["id"])
        if not isinstance(cover, dict) or cover.get("source_url") != row["images"][0]:
            raise PreviewError("Cached cover manifest is missing or stale for an active property")
        relative_path, short_hash = cover_path(cover.get("image_url"), row["id"])
        digest, size = cover.get("sha256"), cover.get("bytes")
        if (not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest)
                or not digest.startswith(short_hash) or type(size) is not int or size <= 0):
            raise PreviewError("Cached cover manifest has an invalid image hash or size")
        path = root / relative_path
        if any(part.is_symlink() for part in (path, *path.absolute().parents)) or not path.is_file():
            raise PreviewError("Cached cover must be an existing regular website image without symbolic paths")
        with path.open("rb") as image:
            actual_hash = hashlib.file_digest(image, "sha256").hexdigest()
        if path.stat().st_size != size or actual_hash != digest:
            raise PreviewError("Cached cover bytes do not match the approved manifest")
        updated.append({**row, "seo_image": cover["image_url"], "seo_source": cover["source_url"]})
    return {**snapshot, "properties": updated}


class TemplateHead(HTMLParser):
    """Record edit spans without reserializing the site's booking-page markup."""

    def __init__(self, template):
        super().__init__(convert_charrefs=False)
        self.template = template
        self.lines = [0] + [match.end() for match in re.finditer("\n", template)]
        self.in_head, self.head_count = False, 0
        self.head_close, self.html_span, self.html_attrs = None, None, None
        self.title_start, self.structured_start, self.edits = None, None, []
        self.feed(template)
        self.close()
        if (self.head_count != 1 or self.in_head or self.head_close is None or self.html_span is None
                or self.title_start is not None or self.structured_start is not None):
            raise PreviewError("Property template must have one complete HTML/head element")

    def position(self):
        line, column = self.getpos()
        return self.lines[line - 1] + column

    def handle_starttag(self, tag, attrs):
        start = self.position()
        end = start + len(self.get_starttag_text())
        values = {key.lower(): value for key, value in attrs}
        if tag == "html":
            if self.html_span is not None:
                raise PreviewError("Property template has multiple HTML root elements")
            self.html_span, self.html_attrs = (start, end), attrs
        if tag == "head":
            self.in_head, self.head_count = True, self.head_count + 1
        if not self.in_head:
            return
        if tag == "title":
            if self.title_start is not None:
                raise PreviewError("Nested title in property template")
            self.title_start = start
        if tag == "script" and (values.get("type") or "").lower() == "application/ld+json":
            self.structured_start = start
        if tag == "meta":
            names = [(values.get(key) or "").lower() for key in ("name", "property")]
            if any(name in {"description", "robots"} or name.startswith(("og:", "twitter:")) for name in names):
                self.edits.append((start, end, ""))
        if tag == "link" and "canonical" in (values.get("rel") or "").lower().split():
            self.edits.append((start, end, ""))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if not self.in_head:
            return
        start = self.position()
        if tag == "title" and self.title_start is not None:
            end = self.template.find(">", start)
            if end == -1:
                raise PreviewError("Incomplete title in property template")
            self.edits.append((self.title_start, end + 1, ""))
            self.title_start = None
        if tag == "script" and self.structured_start is not None:
            end = self.template.find(">", start)
            if end == -1:
                raise PreviewError("Incomplete structured data script in property template")
            self.edits.append((self.structured_start, end + 1, ""))
            self.structured_start = None
        if tag == "head":
            self.in_head, self.head_close = False, start


class TemplateElements(HTMLParser):
    """Locate body elements while preserving the template's booking form markup."""

    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self, template):
        super().__init__(convert_charrefs=False)
        self.template, self.elements, self.stack = template, {}, []
        self.lines = [0] + [match.end() for match in re.finditer("\n", template)]
        self.feed(template)
        self.close()

    def position(self):
        line, column = self.getpos()
        return self.lines[line - 1] + column

    def handle_starttag(self, tag, attrs):
        start = self.position()
        node = {"tag": tag, "attrs": attrs, "start": start,
                "open_end": start + len(self.get_starttag_text())}
        element_id = dict(attrs).get("id")
        if element_id:
            if element_id in self.elements:
                raise PreviewError("Duplicate element ID in property template")
            self.elements[element_id] = node
        if tag not in self.VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            node = self.stack.pop()
            node["close_start"] = node["end"] = node["open_end"]

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index]["tag"] == tag:
                node = self.stack[index]
                node["close_start"] = self.position()
                node["end"] = self.template.find(">", self.position()) + 1
                del self.stack[index:]
                break


def opening_tag(node, changes=None, remove=()):
    changes = changes or {}
    attrs = [(key, value) for key, value in node["attrs"] if key not in changes and key not in remove]
    attrs.extend(changes.items())
    return "<" + node["tag"] + "".join(" " + key + ("" if value is None else f'="{escape(value, quote=True)}"')
                                          for key, value in attrs) + ">"


def prerender_body(template, row):
    parsed, edits = TemplateElements(template), []

    def element(element_id):
        try:
            return parsed.elements[element_id]
        except KeyError:
            raise PreviewError("Property template is missing a required booking-page element") from None

    def content(element_id, html):
        node = element(element_id)
        if "close_start" not in node:
            raise PreviewError("Property template has an incomplete body element")
        edits.append((node["open_end"], node["close_start"], html))

    title = row["title"].strip()
    content("propertyTitle", escape(title))
    content("breadcrumbTitle", escape(title))
    content("propertyLocation", escape((row.get("location") or "").strip() or "Location to be confirmed"))
    types = {"studio": "Studio", "villa": "Villa", **{f"{number}br": f"{number} bedroom" + ("s" if number > 1 else "") for number in range(1, 6)}}
    accommodation_type = (row.get("unit_type") or "").strip()
    content("propertyType", escape(types.get(accommodation_type, accommodation_type or "Holiday accommodation")))
    beds = row.get("beds") or 0
    content("propertyBeds", f"{beds} bed" + ("s" if beds != 1 else "") if beds else "")
    amenities = row.get("amenities") or ["Please contact PwaniStays to confirm the property amenities."]
    content("propertyAmenities", "".join(f"<li>{escape(item.strip())}</li>" for item in amenities))
    cover = {"src": row.get("seo_image") or row["images"][0], "alt": title + " — main property photo"}
    if row.get("seo_image"):
        cover.update({"data-seo-image": row["seo_image"], "data-seo-source": row["seo_source"]})
    for element_id, changes, remove in [("propertyContent", {}, ("hidden",)),
                                         ("propertyStatus", {"hidden": None}, ()),
                                         ("pwMainImage", cover, ("hidden", "data-seo-image", "data-seo-source"))]:
        node = element(element_id)
        edits.append((node["start"], node["open_end"], opening_tag(node, changes, remove)))
    summary = '<p class="pw-muted" id="propertySummary">' + escape(row["description"].strip()) + "</p>"
    if "propertySummary" in parsed.elements:
        node = element("propertySummary")
        edits.append((node["start"], node["end"], summary))
    else:
        position = element("propertyTitle")["end"]
        edits.append((position, position, "\n      " + summary))
    contact = "https://wa.me/254738544784?" + urlencode({"text": "Hello PwaniStays! Please confirm current rates and availability for " + title + ".\n" + property_url(row["id"])})
    fallback = ('<noscript id="propertyNoScript"><p>To request current rates and availability without JavaScript, '
                f'<a href="{escape(contact, quote=True)}">contact PwaniStays on WhatsApp about this property</a>.</p></noscript>')
    if "propertyNoScript" in parsed.elements:
        node = element("propertyNoScript")
        edits.append((node["start"], node["end"], fallback))
    else:
        position = element("quoteForm")["end"]
        edits.append((position, position, "\n          " + fallback))
    result = template
    for start, end, replacement in sorted(edits, reverse=True):
        result = result[:start] + replacement + result[end:]
    return result.replace('href="/#stays"', 'href="/stays.html"')


def structured_data(row):
    url, title = property_url(row["id"]), row["title"].strip()
    data = {"@context": "https://schema.org", "@graph": [
        {"@type": "WebPage", "@id": url + "#webpage", "name": title + " | PwaniStays",
         "description": row["description"].strip(), "url": url, "image": row.get("seo_image") or row["images"][0],
         "isPartOf": {"@type": "WebSite", "name": "PwaniStays", "url": SITE + "/"},
         "breadcrumb": {"@id": url + "#breadcrumbs"}},
        {"@type": "BreadcrumbList", "@id": url + "#breadcrumbs", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": SITE + "/"},
            {"@type": "ListItem", "position": 2, "name": "Accommodation", "item": SITE + "/stays.html"},
            {"@type": "ListItem", "position": 3, "name": title, "item": url}]}]}
    # JSON-LD is script raw text: HTML entities do not prevent a </script> breakout.
    encoded = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    for character, replacement in [("<", "\\u003c"), (">", "\\u003e"), ("&", "\\u0026"),
                                    ("\u2028", "\\u2028"), ("\u2029", "\\u2029")]:
        encoded = encoded.replace(character, replacement)
    return '<script id="property-structured-data" type="application/ld+json">' + encoded + "</script>\n"


def render_property(template, row):
    # A standalone rendering call receives the same validation as a full run.
    validate_source({"version": 1, "properties": [row]})
    parsed = TemplateHead(template)
    title = row["title"].strip() + " | PwaniStays"
    description = row["description"].strip()
    url, image = property_url(row["id"]), row.get("seo_image") or row["images"][0]
    values = [
        ("name", "description", description), ("name", "robots", "index,follow,max-image-preview:large"),
        ("property", "og:type", "website"), ("property", "og:site_name", "PwaniStays"),
        ("property", "og:title", title), ("property", "og:description", description),
        ("property", "og:url", url), ("property", "og:image", image),
        ("property", "og:image:secure_url", image),
        ("property", "og:image:alt", row["title"].strip() + " — property photo"),
        ("name", "twitter:card", "summary_large_image"),
        ("name", "twitter:title", title), ("name", "twitter:description", description),
        ("name", "twitter:image", image),
        ("name", "twitter:image:alt", row["title"].strip() + " — property photo"),
    ]
    metadata = "  <title>" + escape(title) + "</title>\n"
    metadata += f'  <link rel="canonical" href="{escape(url, quote=True)}">\n'
    metadata += "".join(f'  <meta {kind}="{name}" content="{escape(value, quote=True)}">\n'
                        for kind, name, value in values)
    metadata += "  " + structured_data(row)
    attrs = [(key, value) for key, value in parsed.html_attrs if key.lower() != "data-property-id"]
    attrs.append(("data-property-id", row["id"]))
    html_open = "<html" + "".join(" " + key + ("" if value is None else f'="{escape(value, quote=True)}"')
                                  for key, value in attrs) + ">\n" + MARKER
    edits = parsed.edits + [(*parsed.html_span, html_open), (parsed.head_close, parsed.head_close, metadata)]
    result = template
    for start, end, replacement in sorted(edits, reverse=True):
        result = result[:start] + replacement + result[end:]
    # Removing inherited tags can leave indentation-only lines in the head.
    head_end = result.lower().index("</head")
    result = re.sub(r"(?m)^[ \t]+$", "", result[:head_end]) + result[head_end:]
    return prerender_body(result, row)


def render_tombstone(property_id):
    canonical_uuid(property_id)
    url = property_url(property_id)
    return f'''<!DOCTYPE html>
<html lang="en" data-property-id="{property_id}" data-property-unavailable="true">
{MARKER}
<head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Property no longer listed | PwaniStays</title>
  <meta name="robots" content="noindex,nofollow">
  <meta name="description" content="This property is no longer listed. Browse current PwaniStays accommodation.">
  <meta property="og:type" content="website">
  <meta property="og:title" content="Property no longer listed | PwaniStays">
  <meta property="og:description" content="Browse current PwaniStays accommodation instead.">
  <meta property="og:url" content="{url}">
  <link rel="canonical" href="{url}">
  <link rel="stylesheet" href="/new-pages.css">
</head>
<body><main class="pw-main pw-container">
  <h1>This property is no longer listed</h1>
  <p>Explore our current accommodation or contact PwaniStays for help choosing a stay.</p>
  <p><a href="/stays.html">Browse current accommodation</a></p>
</main></body>
</html>
'''


def owned_pages(output_dir):
    # Refuse symbolic paths, unknown files and unowned collisions before writing.
    path = output_dir.absolute()
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise PreviewError("Preview output paths must not contain symbolic links")
    if not path.exists():
        return {}
    if not path.is_dir():
        raise PreviewError("Preview output is not a directory")
    result = {}
    for directory in path.iterdir():
        if directory.is_symlink() or not directory.is_dir():
            raise PreviewError("Unexpected file or link in preview output")
        canonical_uuid(directory.name)
        children = list(directory.iterdir())
        if len(children) != 1 or children[0].name != "index.html":
            raise PreviewError("Preview directory contains unknown files or an unowned collision")
        page = children[0]
        if page.is_symlink() or not page.is_file():
            raise PreviewError("Preview page is not an owned regular file")
        content = page.read_text(encoding="utf-8")
        if MARKER not in content:
            raise PreviewError("Refusing to overwrite a page without the preview ownership marker")
        result[directory.name] = content
    return result


def generate(snapshot, template, output_dir, check=False):
    rows = validate_source(snapshot)
    # Render all content and inspect all existing output before modifying anything.
    rendered = {row["id"]: render_property(template, row) for row in rows}
    directory = Path(output_dir)
    previous = owned_pages(directory)
    withdrawn = set(previous) - set(rendered)
    rendered.update({property_id: render_tombstone(property_id) for property_id in withdrawn})
    changes = {property_id: content for property_id, content in rendered.items()
               if previous.get(property_id) != content}
    if not check:
        for property_id, content in sorted(changes.items()):
            atomic_write(directory / property_id / "index.html", content.encode("utf-8"))
    return {"active": len(rows), "withdrawn": len(withdrawn), "changed": len(changes)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "catalogue/properties.json")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "stays")
    parser.add_argument("--covers", type=Path, help="validated local-cover manifest; defaults to catalogue/cover-images.json when present")
    parser.add_argument("--check", action="store_true", help="validate and render without changing files")
    args = parser.parse_args(argv)
    try:
        snapshot = json.loads(args.source.read_text(encoding="utf-8"))
        covers = args.covers if args.covers is not None else ROOT / "catalogue/cover-images.json"
        if args.covers is not None or covers.exists() or covers.is_symlink():
            snapshot = load_cover_images(snapshot, covers, root=ROOT)
        template = (ROOT / "property.html").read_text(encoding="utf-8")
        counts = generate(snapshot, template, args.output_dir, args.check)
        print(json.dumps({"mode": "check" if args.check else "generated", **counts}))
        return 0
    except PreviewError as exc:
        print(f"PROPERTY PREVIEW ERROR: {exc}", file=sys.stderr)
        return 1
    except (OSError, ValueError):
        print("PROPERTY PREVIEW ERROR: Source, template or output could not be read/written safely", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
