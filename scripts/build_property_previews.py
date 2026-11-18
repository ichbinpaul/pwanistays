#!/usr/bin/env python3
"""Build unit-specific HTML/preview metadata for static hosting and chat crawlers.

Reads the existing public catalogue export. It does not fetch private data or
modify Meta, WhatsApp, Supabase, or unrelated website pages.
"""
from __future__ import annotations

import argparse
from html import escape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
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
        if row.get("url") not in {property_url(property_id), f"{SITE}/property.html?id={property_id}"}:
            raise PreviewError("Property URL is not a recognised public property link")
        images = row.get("images")
        if (not isinstance(images, list) or not 1 <= len(images) <= 10 or
                any(not isinstance(url, str) or not valid_photo(url) for url in images) or
                len(set(images)) != len(images)):
            raise PreviewError("Each property needs one to ten distinct public HTTPS image URLs")
    return sorted(rows, key=lambda row: row["id"])


class TemplateHead(HTMLParser):
    """Record edit spans without reserializing the site's booking-page markup."""

    def __init__(self, template):
        super().__init__(convert_charrefs=False)
        self.template = template
        self.lines = [0] + [match.end() for match in re.finditer("\n", template)]
        self.in_head, self.head_count = False, 0
        self.head_close, self.html_span, self.html_attrs = None, None, None
        self.title_start, self.edits = None, []
        self.feed(template)
        self.close()
        if self.head_count != 1 or self.in_head or self.head_close is None or self.html_span is None or self.title_start is not None:
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
        if tag == "head":
            self.in_head, self.head_close = False, start


def render_property(template, row):
    # A standalone rendering call receives the same validation as a full run.
    validate_source({"version": 1, "properties": [row]})
    parsed = TemplateHead(template)
    title = row["title"].strip() + " | PwaniStays"
    description = row["description"].strip()
    url, image = property_url(row["id"]), row["images"][0]
    values = [
        ("name", "description", description), ("name", "robots", "index,follow"),
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
    return re.sub(r"(?m)^[ \t]+$", "", result[:head_end]) + result[head_end:]


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
  <p><a href="/#stays">Browse current accommodation</a></p>
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
    parser.add_argument("--check", action="store_true", help="validate and render without changing files")
    args = parser.parse_args(argv)
    try:
        snapshot = json.loads(args.source.read_text(encoding="utf-8"))
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
