#!/usr/bin/env python3
"""Audit local static site references without making network requests.

External hosts and known dynamic fragments are reported as unverified, never as
passed. No source files are modified. Use --report outside the site checkout.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import posixpath
import re
import sys
from urllib.parse import unquote, urljoin, urlsplit
from xml.etree import ElementTree as ET

SITE = "https://pwanistays.com"
LOCAL_HOSTS = {"pwanistays.com", "www.pwanistays.com"}
EXCLUDED = {"scripts", "tests", "supabase", "node_modules", "__pycache__", "venv"}
MAX_BYTES = 4 * 1024 * 1024
CSS_URL = re.compile(r"url\(\s*(['\"]?)(.*?)\1\s*\)", re.I | re.S)
CSS_IMPORT = re.compile(r"@import\s+(['\"])(.*?)\1", re.I)
DYNAMIC = re.compile(r"(?:\$\{|\{\{|<%|\[PAGE-[A-Z-]+\]|^#(?:property|main|thumb|desc|toggle)-[0-9a-f-]+$)")


@dataclass
class Reference:
    source: str
    line: int
    url: str
    kind: str = "link"
    base: str | None = None


def css_urls(text):
    clean = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return [match.group(2).strip() for match in CSS_URL.finditer(clean)] + [
        match.group(2).strip() for match in CSS_IMPORT.finditer(clean)]


class Page(HTMLParser):
    def __init__(self, source, text):
        super().__init__(convert_charrefs=True)
        self.source, self.refs, self.ids = source, [], set()
        self.base, self.noindex, self.style = None, False, False
        self.feed(text)
        self.close()

    def add(self, url, kind="link"):
        if url is not None:
            self.refs.append(Reference(self.source, self.getpos()[0], url.strip(), kind, self.base))

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("id"):
            self.ids.add(attrs["id"])
        if tag == "a" and attrs.get("name"):
            self.ids.add(attrs["name"])
        if tag == "base" and attrs.get("href"):
            self.base = attrs["href"]
            return
        for attr in ("src", "poster", "data-src"):
            if attrs.get(attr):
                self.add(attrs[attr], "asset")
        if "href" in attrs and tag != "base":
            self.add(attrs["href"], "link" if tag in {"a", "area"} else "asset")
        if tag == "form" and attrs.get("action"):
            self.add(attrs["action"], "form")
        if attrs.get("srcset") and not attrs["srcset"].lstrip().startswith("data:"):
            for item in attrs["srcset"].split(","):
                if item.strip():
                    self.add(item.strip().split()[0], "asset")
        if tag == "meta":
            key = (attrs.get("name") or attrs.get("property") or "").lower()
            if key == "robots" and "noindex" in attrs.get("content", "").lower():
                self.noindex = True
            if key in {"og:image", "og:image:secure_url", "twitter:image", "msapplication-config", "og:url"}:
                self.add(attrs.get("content"), "metadata")
            if attrs.get("http-equiv", "").lower() == "refresh":
                match = re.search(r"url\s*=\s*['\"]?([^'\"]+)", attrs.get("content", ""), re.I)
                if match:
                    self.add(match.group(1), "redirect")
        for url in css_urls(attrs.get("style", "")):
            self.add(url, "css")
        if tag == "style":
            self.style = True

    handle_startendtag = handle_starttag

    def handle_endtag(self, tag):
        if tag == "style":
            self.style = False

    def handle_data(self, data):
        if self.style:
            for url in css_urls(data):
                self.add(url, "css")


def discover(root, errors):
    for directory, dirs, names in os.walk(root, followlinks=False, onerror=errors.append):
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d not in EXCLUDED
                         and not (Path(directory) / d).is_symlink())
        for name in sorted(names):
            path = Path(directory) / name
            if name.startswith(".") or path.is_symlink():
                continue
            if path.suffix.lower() in {".html", ".css", ".webmanifest", ".xml"} or path.relative_to(root).as_posix() in {"robots.txt", "catalogue/properties.json"}:
                yield path


def audit(root):
    root = Path(root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Site root must be a directory")
    pages, refs, broken, unverified = {}, [], [], []
    external, counts = Counter(), Counter()
    def problem(ref, reason, target=None):
        item = {"source": ref.source, "line": ref.line, "url": ref.url[:500], "reason": reason}
        if target is not None:
            item["target"] = target
        broken.append(item)
    traversal_errors = []
    for path in discover(root, traversal_errors):
        relative = path.relative_to(root).as_posix()
        counts["source_files"] += 1
        try:
            if path.stat().st_size > MAX_BYTES:
                raise ValueError("Source file exceeds bounded audit size")
            text = path.read_text(encoding="utf-8")
            if path.suffix == ".html":
                page = Page(relative, text)
                pages[relative] = page
                refs.extend(page.refs)
                counts["html_pages"] += 1
                if not page.noindex and relative not in {"header.html", "page-template.html", "bookings.html"}:
                    counts["public_entry_pages"] += 1
            elif path.suffix == ".css":
                refs.extend(Reference(relative, 1, url, "css") for url in css_urls(text))
            elif path.suffix == ".webmanifest":
                manifest = json.loads(text)
                refs.extend(Reference(relative, 1, icon["src"], "manifest") for icon in manifest.get("icons", []))
                if manifest.get("start_url"):
                    refs.append(Reference(relative, 1, manifest["start_url"], "manifest"))
            elif path.suffix == ".xml":
                document = ET.fromstring(text)
                for node in document.iter():
                    if node.attrib.get("src"):
                        refs.append(Reference(relative, 1, node.attrib["src"], "xml"))
                    if node.tag.split("}")[-1] == "loc" and node.text:
                        refs.append(Reference(relative, 1, node.text.strip(), "sitemap"))
            elif relative == "robots.txt":
                refs.extend(Reference(relative, i, match.group(1), "sitemap")
                            for i, line in enumerate(text.splitlines(), 1)
                            if (match := re.match(r"\s*Sitemap:\s*(\S+)", line, re.I)))
            elif relative == "catalogue/properties.json":
                for item in json.loads(text).get("properties", []):
                    refs.append(Reference(relative, 1, item["url"], "catalogue"))
                    refs.extend(Reference(relative, 1, url, "catalogue-image") for url in item.get("images", []))
        except (OSError, UnicodeError, ValueError, ET.ParseError, KeyError, TypeError) as exc:
            problem(Reference(relative, 1, ""), "source_unreadable_or_invalid", type(exc).__name__)
    for error in traversal_errors:
        problem(Reference(str(error.filename or "unknown directory"), 1, ""), "directory_not_audited", type(error).__name__)
    injected_ids = pages.get("header.html").ids if "header.html" in pages else set()
    for ref in refs:
        counts["references"] += 1
        if not ref.url or ref.url == "#":
            counts["empty_or_placeholder"] += 1
            continue
        if DYNAMIC.search(ref.url):
            unverified.append({"source": ref.source, "line": ref.line, "url": ref.url[:500], "reason": "dynamic_reference"})
            continue
        try:
            source_url = SITE + "/" + ref.source
            base = urljoin(source_url, ref.base) if ref.base else source_url
            parsed = urlsplit(urljoin(base, ref.url))
            if parsed.scheme not in {"http", "https"}:
                counts["skipped_schemes"] += 1
                continue
            if parsed.hostname not in LOCAL_HOSTS:
                external[parsed.hostname or "unknown"] += 1
                continue
            local = posixpath.normpath(unquote(parsed.path or "/")).lstrip("/")
            target = root / local
            # GitHub Pages serves extensionless page URLs from matching HTML files.
            # A real file or directory index takes precedence over the HTML file.
            if (local and not parsed.path.endswith("/") and not target.suffix
                    and not target.is_symlink() and not target.is_file() and not (target / "index.html").is_file()
                    and local + ".html" in pages):
                target = root / (local + ".html")
            if not target.resolve().is_relative_to(root):
                problem(ref, "target_escapes_site_root")
                continue
            if any(part.is_symlink() for part in (target, *target.parents) if part != root.parent):
                problem(ref, "symbolic_target_not_audited", local)
                continue
            if target.is_dir():
                target = target / "index.html"
            relative = target.relative_to(root).as_posix()
            if not target.is_file():
                problem(ref, "missing_local_target", relative)
                continue
            counts["local_targets_checked"] += 1
            fragment = unquote(parsed.fragment)
            if fragment:
                document = pages.get(relative)
                if document:
                    ids = document.ids | (injected_ids if "site-header" in document.ids else set())
                    if fragment not in ids:
                        if ref.kind == "css" or re.match(r"^(?:property|main|thumb|desc|toggle)-[0-9a-f-]+$", fragment):
                            unverified.append({"source": ref.source, "line": ref.line, "url": ref.url[:500], "reason": "dynamic_fragment"})
                        else:
                            problem(ref, "missing_static_fragment", relative + "#" + fragment)
                    else:
                        counts["fragments_checked"] += 1
                else:
                    unverified.append({"source": ref.source, "line": ref.line, "url": ref.url[:500], "reason": "non_html_fragment_unverified"})
        except (OSError, ValueError) as exc:
            problem(ref, "invalid_or_inaccessible_target", type(exc).__name__)
    return {"mode": "offline_static_audit", "counts": dict(counts),
            "broken_count": len(broken), "broken": broken[:1000],
            "broken_details_truncated": len(broken) > 1000,
            "unverified_count": len(unverified), "unverified": unverified[:1000],
            "unverified_details_truncated": len(unverified) > 1000,
            "external_domains": [{"domain": host, "references": number, "status": "unverified_no_network"}
                                 for host, number in sorted(external.items())]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    try:
        report = audit(args.root)
        if args.report:
            if args.report.resolve().is_relative_to(args.root.resolve()):
                raise ValueError("Keep audit reports outside the website checkout")
            if args.report.exists():
                raise ValueError("Refusing to overwrite an existing report")
            with args.report.open("x", encoding="utf-8") as output:
                json.dump(report, output, indent=2, ensure_ascii=False)
                output.write("\n")
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 1 if report["broken_count"] else 0
    except (OSError, ValueError) as exc:
        print(f"LINK AUDIT ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
