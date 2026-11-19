#!/usr/bin/env python3
"""Check deployed sitemap pages/assets and real 404s without modifying the site.

Checks actual HTTP responses, initial-HTML canonicals and visible headings.
This does not establish Google indexing, uptime history or real-user performance.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SITE = "https://pwanistays.com"
MAX_BYTES = 2 * 1024 * 1024
ESSENTIAL = ["/robots.txt", "/sitemap.xml", "/property-sitemap.xml", "/stays.html",
             "/header.html", "/header.css", "/i18n.js", "/listing-utils.js",
             "/property.js", "/property-sharing.js", "/property-routes.js",
             "/catalogue/property-slugs.json", "/favicon.ico"]
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}


class Page(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.stack, self.canonicals, self.headings, self.robots = [], [], [], []
        self.heading = None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        hidden = (bool(self.stack and self.stack[-1][1]) or "hidden" in attrs
                  or attrs.get("aria-hidden") == "true"
                  or bool(re.search(r"(?:display\s*:\s*none|visibility\s*:\s*hidden)", attrs.get("style", ""), re.I)))
        if tag == "link" and "canonical" in attrs.get("rel", "").lower().split():
            self.canonicals.append(attrs.get("href", ""))
        if tag == "meta" and attrs.get("name", "").lower() in {"robots", "googlebot"}:
            self.robots.append(attrs.get("content", "").lower())
        if tag == "h1" and not hidden:
            self.heading = []
        if tag not in VOID:
            self.stack.append((tag, hidden))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag == "h1" and self.heading is not None:
            text = " ".join("".join(self.heading).split())
            if text:
                self.headings.append(text)
            self.heading = None
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        if self.heading is not None and not (self.stack and self.stack[-1][1]):
            self.heading.append(data)


class SameSiteRedirect(HTTPRedirectHandler):
    def __init__(self, preferred):
        super().__init__()
        self.origin = urlsplit(preferred)

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urlsplit(newurl)
        if target.scheme != "https" or target.netloc != self.origin.netloc:
            raise ValueError("Cross-origin or insecure redirect refused")
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is not None and req.get_method() == "HEAD":
            redirected.method = "HEAD"
        return redirected


def read_url(url, preferred, method="GET"):
    req = Request(url, method=method, headers={"User-Agent": "PwaniStays-Site-Health/1.0",
                  "Accept": "image/*,*/*" if method == "HEAD" else "text/html,application/xml,text/plain,*/*"})
    try:
        response = build_opener(SameSiteRedirect(preferred)).open(req, timeout=15)
    except HTTPError as error:
        response = error
    except (URLError, OSError, ValueError):
        return {"status": 0, "final_url": url, "headers": {}, "body": b"", "error": "Network, TLS or redirect-policy failure"}
    try:
        with response:
            data = b"" if method == "HEAD" else response.read(MAX_BYTES + 1)
            return {"status": response.getcode(), "final_url": response.geturl(),
                    "headers": {key.lower(): value for key, value in response.headers.items()},
                    "body": data[:MAX_BYTES],
                    "error": "Response exceeds inspection limit" if len(data) > MAX_BYTES else None}
    except (OSError, ValueError):
        return {"status": 0, "final_url": url, "headers": {}, "body": b"", "error": "Response could not be read"}


def fetch(url, preferred, method="GET"):
    result = read_url(url, preferred, method)
    result["attempts"] = 1
    # One retry for transient server errors; never loop on denied access or 404s.
    if 500 <= result["status"] <= 599:
        time.sleep(0.25)
        result = read_url(url, preferred, method)
        result["attempts"] = 2
    return result


def cover_targets(root):
    source = json.loads((root / "catalogue/properties.json").read_text(encoding="utf-8"))
    rows = source.get("properties") if isinstance(source, dict) else None
    if not isinstance(source, dict) or type(source.get("version")) is not int or source["version"] != 1 or not isinstance(rows, list) or not rows:
        raise ValueError("Active property source is missing or invalid")
    manifest = root / "catalogue/cover-images.json"
    if manifest.exists() or manifest.is_symlink():
        # Never silently fall back to source images after owned covers are configured.
        from build_property_previews import PreviewError, load_cover_images
        try:
            enriched = load_cover_images(source, manifest, root=root)
        except (PreviewError, OSError, ValueError):
            raise ValueError("Website-owned cover manifest is stale, incomplete or invalid") from None
        results, seen = [], set()
        for row in enriched["properties"]:
            url = row["seo_image"]
            if url in seen:
                continue
            seen.add(url)
            origin = urlsplit(url)
            results.append({"url": url, "kind": "cover", "expected": url,
                            "origin": f"{origin.scheme}://{origin.netloc}"})
        return results
    config = (root / "listing-utils.js").read_text(encoding="utf-8")
    match = re.search(r"const\s+SUPABASE_URL\s*=\s*['\"](https://[^'\"]+)['\"]", config)
    if not match:
        raise ValueError("Configured public photo project is missing")
    project = urlsplit(match.group(1))
    if (project.scheme != "https" or not project.hostname or not project.hostname.endswith(".supabase.co")
            or project.username or project.password or project.port or project.path not in {"", "/"}
            or project.query or project.fragment):
        raise ValueError("Configured public photo project is invalid")
    results, seen = [], set()
    sensitive = {"token", "access_token", "apikey", "api_key", "authorization", "client_secret", "appsecret_proof"}
    for row in rows:
        images = row.get("images") if isinstance(row, dict) else None
        if not isinstance(images, list) or not images or not isinstance(images[0], str):
            raise ValueError("An active property has no inspectable cover URL")
        url = images[0]
        if url in seen:
            continue
        seen.add(url)
        parsed = urlsplit(url)
        public_path = parsed.path.startswith(("/storage/v1/object/public/property_images/",
                                             "/storage/v1/render/image/public/property_images/"))
        if (parsed.scheme != "https" or parsed.netloc != project.netloc or parsed.username
                or parsed.password or parsed.fragment or not public_path
                or any(key.lower() in sensitive for key, _ in parse_qsl(parsed.query))):
            # Do not request unknown origins, signed/private objects, or expose URL credentials.
            safe_url = urlunsplit((parsed.scheme, parsed.hostname or "", parsed.path, "", ""))
            results.append({"url": safe_url, "kind": "cover_unverified", "expected": None,
                            "reason": "Cover is outside the configured public photo project or uses an unsupported URL; not fetched"})
        else:
            results.append({"url": url, "kind": "cover", "expected": url,
                            "origin": f"https://{project.netloc}"})
    return results


def targets(root, base, redirects=False, covers=False):
    pages = set()
    for filename in ["sitemap.xml", "property-sitemap.xml"]:
        tree = ET.fromstring((root / filename).read_bytes())
        for loc in tree.findall("{*}url/{*}loc"):
            parsed = urlsplit(loc.text or "")
            if parsed.scheme != "https" or parsed.netloc != urlsplit(SITE).netloc or parsed.query or parsed.fragment:
                raise ValueError("Sitemap contains a noncanonical target")
            pages.add(base.rstrip("/") + parsed.path)
    if not pages:
        raise ValueError("No sitemap pages to check")
    result = [{"url": url, "kind": "page", "expected": url} for url in sorted(pages)]
    for path in ESSENTIAL:
        url = base.rstrip("/") + path
        if url not in pages:
            result.append({"url": url, "kind": "asset", "expected": url})
    result.append({"url": base.rstrip("/") + "/_pwani_site_health_missing_8f65d4b1/", "kind": "missing", "expected": None})
    if redirects:
        primary = urlsplit(base)
        alternate = primary.hostname[4:] if primary.hostname.startswith("www.") else "www." + primary.hostname
        for url in [f"http://{primary.netloc}/", f"https://{alternate}/", f"http://{alternate}/"]:
            result.append({"url": url, "kind": "redirect", "expected": base.rstrip("/") + "/"})
    if covers:
        result.extend(cover_targets(root))
    return result


def indexing_blocked(directives):
    return any(re.search(r"\bnoindex\b", item) or any(
        re.fullmatch(r"(?:(?:googlebot|googlebot-image)\s*:\s*)?none", part.strip())
        for part in item.split(",")) for item in directives)


def check(target, base):
    if target["kind"] == "cover_unverified":
        return {"url": target["url"], "kind": target["kind"], "status": None,
                "final_url": None, "attempts": 0, "issues": [], "unverified": target["reason"]}
    response = (fetch(target["url"], target["origin"], method="HEAD")
                if target["kind"] == "cover" else fetch(target["url"], base))
    issues = []
    if response.get("error"):
        issues.append(response["error"])
    expected_status = 404 if target["kind"] == "missing" else 200
    if response["status"] != expected_status:
        issues.append(f"Expected HTTP {expected_status}, received {response['status']}")
    if target["kind"] in {"page", "redirect"} and response["final_url"] != target["expected"]:
        issues.append("Final URL differs from the preferred canonical target")
    if target["kind"] == "cover" and response["status"] == 200:
        if not response["headers"].get("content-type", "").lower().startswith("image/"):
            issues.append("Cover URL did not return an image Content-Type")
        if indexing_blocked([response["headers"].get("x-robots-tag", "").lower()]):
            issues.append("Cover image is marked noindex by X-Robots-Tag")
    if target["kind"] == "asset" and response["status"] == 200:
        content_type = response["headers"].get("content-type", "").lower()
        path = urlsplit(target["url"]).path
        if path.endswith(".js") and not any(kind in content_type for kind in ["javascript", "ecmascript"]):
            issues.append("Script asset returned an unexpected Content-Type")
        if path.endswith(".css") and "text/css" not in content_type:
            issues.append("Stylesheet asset returned an unexpected Content-Type")
        if path.endswith(".xml") and not any(kind in content_type for kind in ["application/xml", "text/xml"]):
            issues.append("Sitemap asset returned an unexpected Content-Type")
        if path.endswith(".json") and "application/json" not in content_type:
            issues.append("JSON asset returned an unexpected Content-Type")
    if target["kind"] == "page" and response["status"] == 200:
        if "text/html" not in response["headers"].get("content-type", "").lower():
            issues.append("Indexable page did not return HTML")
        else:
            try:
                page = Page(response["body"].decode("utf-8"))
                if page.canonicals != [target["expected"]]:
                    issues.append("Expected exactly one matching canonical in initial HTML")
                if not page.headings:
                    issues.append("No nonempty visible H1 in initial HTML")
                directives = page.robots + [response["headers"].get("x-robots-tag", "").lower()]
                if indexing_blocked(directives):
                    issues.append("Indexable sitemap page is marked noindex")
            except (UnicodeError, ValueError):
                issues.append("HTML could not be inspected")
    return {"url": target["url"], "kind": target["kind"], "status": response["status"],
            "final_url": response["final_url"], "attempts": response["attempts"], "issues": issues}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=SITE)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--check-redirects", action="store_true")
    parser.add_argument("--check-cover-images", action="store_true", help="HEAD-check distinct active covers on the configured public Supabase project")
    parser.add_argument("--workers", type=int, choices=range(1, 9), default=4)
    args = parser.parse_args(argv)
    parsed = urlsplit(args.base_url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        parser.error("base-url must be an HTTPS site origin without credentials, query or path")
    if args.report and args.report.resolve().is_relative_to(ROOT):
        parser.error("Keep diagnostic reports outside the website checkout")
    try:
        base = args.base_url.rstrip("/")
        planned = targets(args.root, base, args.check_redirects, args.check_cover_images)
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            checks = list(pool.map(lambda target: check(target, base), planned))
        failed = sum(bool(result["issues"]) for result in checks)
        unverified = sum(bool(result.get("unverified")) for result in checks)
        report = {"checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                  "base_url": base, "checked": len(checks) - unverified, "passed": len(checks) - failed - unverified,
                  "failed": failed, "unverified": unverified, "checks": checks}
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"Live HTTP checks: {report['checked']}; passed: {report['passed']}; failed: {failed}; unverified: {unverified}")
        for result in [row for row in checks if row["issues"]][:20]:
            print(result["url"] + ": " + "; ".join(result["issues"]))
        for result in [row for row in checks if row.get("unverified")][:20]:
            print(result["url"] + ": UNVERIFIED: " + result["unverified"])
        return 1 if failed or unverified else 0
    except (OSError, ValueError, ET.ParseError) as error:
        print(f"LIVE CHECK ERROR: {type(error).__name__}; site health could not be established", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
