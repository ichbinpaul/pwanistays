#!/usr/bin/env python3
"""Copy original public unit covers to immutable website-owned image URLs.

Only the configured Supabase project's public same-unit image paths are read.
Images are neither edited nor resized. No API key or authorization is sent.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, unquote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import uuid

from build_whatsapp_catalogue import atomic_write

ROOT = Path(__file__).resolve().parents[1]
SITE = "https://pwanistays.com"
PUBLIC_PATH = "/storage/v1/object/public/property_images/"
MAX_BYTES = 16 * 1024 * 1024
MIMES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/avif": "avif", "image/gif": "gif"}


class CoverError(RuntimeError):
    pass


def safe_path(path):
    path = Path(path).absolute()
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise CoverError("Cover paths must not contain symbolic links")
    return path


def property_id(value):
    if not isinstance(value, str) or str(uuid.UUID(value)) != value:
        raise CoverError("Cover source has a noncanonical property UUID")
    return value


def public_project(config=ROOT / "listing-utils.js"):
    match = re.search(r"const\s+SUPABASE_URL\s*=\s*['\"](https://[^'\"]+)['\"]", config.read_text())
    if not match:
        raise CoverError("Missing configured public photo project")
    parsed = urlsplit(match.group(1))
    if (parsed.scheme != "https" or not parsed.hostname or not parsed.hostname.endswith(".supabase.co")
            or parsed.username or parsed.password or parsed.port or parsed.path not in {"", "/"}
            or parsed.query or parsed.fragment):
        raise CoverError("Unexpected public photo project")
    return "https://" + parsed.netloc


def validate_url(url, project, identity):
    if not isinstance(url, str):
        raise CoverError("Cover URL is missing")
    parsed = urlsplit(url)
    decoded = unquote(parsed.path)
    prefix = PUBLIC_PATH + identity + "/"
    if (parsed.scheme != "https" or parsed.netloc != urlsplit(project).netloc or parsed.username
            or parsed.password or parsed.fragment or not parsed.path.startswith(prefix)
            or not decoded.startswith(prefix) or "\\" in decoded
            or any(segment in {".", ".."} for segment in decoded.split("/"))
            or any(key.lower() in {"token", "access_token", "apikey", "api_key", "authorization", "client_secret"}
                   for key, _ in parse_qsl(parsed.query))):
        raise CoverError("Cover URL is not a public image of the same unit on the configured project")


def source_covers(snapshot, project):
    if not isinstance(snapshot, dict) or type(snapshot.get("version")) is not int or snapshot["version"] != 1:
        raise CoverError("Invalid cover source version")
    rows = snapshot.get("properties")
    if not isinstance(rows, list) or not rows:
        raise CoverError("No active covers; refusing an empty manifest")
    result = {}
    for row in rows:
        if not isinstance(row, dict):
            raise CoverError("Invalid property row")
        identity = property_id(row.get("id"))
        photos = row.get("images")
        if identity in result or not isinstance(photos, list) or not photos:
            raise CoverError("Duplicate property or missing cover")
        validate_url(photos[0], project, identity)
        result[identity] = photos[0]
    return result


def old_manifest(path, output, project):
    if not path.exists():
        return {}
    doc = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict) or doc.get("version") != 1 or not isinstance(doc.get("covers"), dict):
        raise CoverError("Existing cover manifest is not recognised")
    for identity, entry in doc["covers"].items():
        property_id(identity)
        if not isinstance(entry, dict):
            raise CoverError("Malformed cached cover entry")
        validate_url(entry.get("source_url"), project, identity)
        cached_path(identity, entry, output)
        if "etag" in entry and (not isinstance(entry["etag"], str) or not entry["etag"]
                                 or len(entry["etag"]) > 1024 or any(c in entry["etag"] for c in "\r\n")):
            raise CoverError("Invalid cached image validator")
    return doc["covers"]


def cached_path(identity, entry, output):
    digest = entry.get("sha256", "")
    size = entry.get("bytes")
    if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest) or type(size) is not int or not 0 < size <= MAX_BYTES:
        raise CoverError("Invalid cached image checksum or length")
    url = entry.get("image_url", "")
    for ext in MIMES.values():
        filename = f"{identity}-{digest[:16]}.{ext}"
        if url == SITE + "/images/property-covers/" + filename:
            return safe_path(output / filename)
    raise CoverError("Cached image path does not match its immutable checksum")


def valid_cached(identity, entry, output):
    if not entry:
        return False
    path = cached_path(identity, entry, output)
    return path.is_file() and path.stat().st_size == entry["bytes"] and hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"]


class PublicRedirect(HTTPRedirectHandler):
    def __init__(self, project, identity):
        self.project, self.identity = project, identity

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl, self.project, self.identity)
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is not None and req.get_method() == "HEAD":
            redirected.method = "HEAD"
        return redirected


def request_image(url, project, identity, method, etag=None):
    headers = {"User-Agent": "PwaniStays-Cover-Cache/1.0", "Accept": ",".join(MIMES)}
    if etag:
        headers["If-None-Match"] = etag
    req = Request(url, method=method, headers=headers)
    try:
        response = build_opener(PublicRedirect(project, identity)).open(req, timeout=45)
    except HTTPError as exc:
        if exc.code == 304 and method == "HEAD" and etag:
            exc.close()
            return {"status": 304, "headers": {}, "data": b""}
        exc.close()
        raise CoverError(f"Public cover request failed (HTTP {exc.code}) for unit {identity}") from None
    except (URLError, OSError, ValueError):
        raise CoverError(f"Public cover connection failed for unit {identity}") from None
    try:
        with response:
            if response.getcode() != 200:
                raise CoverError(f"Unexpected image response for unit {identity}")
            metadata = {key.lower(): value for key, value in response.headers.items()}
            size = metadata.get("content-length")
            if size and int(size) > MAX_BYTES:
                raise CoverError(f"Cover exceeds {MAX_BYTES // 1024 // 1024} MiB limit for unit {identity}")
            data = response.read(MAX_BYTES + 1) if method == "GET" else b""
            if len(data) > MAX_BYTES:
                raise CoverError(f"Cover exceeds download limit for unit {identity}")
            return {"status": 200, "headers": metadata, "data": data}
    except (OSError, ValueError):
        raise CoverError(f"Public image response could not be read for unit {identity}") from None


def image_extension(data, mime):
    if mime not in MIMES:
        raise CoverError("Cover response has an unsupported image MIME type")
    signatures = {
        "image/jpeg": data.startswith(b"\xff\xd8\xff"),
        "image/png": data.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/gif": data.startswith((b"GIF87a", b"GIF89a")),
        "image/webp": len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP",
        "image/avif": len(data) >= 16 and data[4:8] == b"ftyp" and any(brand in data[8:64] for brand in (b"avif", b"avis")),
    }
    if not signatures[mime]:
        raise CoverError("Cover image header does not match its declared MIME type")
    return MIMES[mime]


def cache_one(identity, url, previous, output, project):
    reusable = bool(previous and previous.get("source_url") == url and valid_cached(identity, previous, output))
    head = request_image(url, project, identity, "HEAD", previous.get("etag") if reusable else None)
    etag = head["headers"].get("etag")
    if reusable and (head["status"] == 304 or (etag and etag == previous.get("etag"))):
        return previous
    downloaded = request_image(url, project, identity, "GET")
    data, headers = downloaded["data"], downloaded["headers"]
    ext = image_extension(data, headers.get("content-type", "").split(";", 1)[0].strip().lower())
    digest = hashlib.sha256(data).hexdigest()
    name = f"{identity}-{digest[:16]}.{ext}"
    destination = safe_path(output / name)
    if destination.exists():
        if not destination.is_file():
            raise CoverError("Immutable cover path is not a regular file")
        if hashlib.sha256(destination.read_bytes()).hexdigest() != digest:
            # Repair only a previously owned file with exactly this full checksum.
            if not previous or previous.get("sha256") != digest or cached_path(identity, previous, output) != destination:
                raise CoverError("Refusing to overwrite an unknown immutable cover file")
            atomic_write(destination, data)
    else:
        atomic_write(destination, data)
    entry = {"source_url": url, "image_url": SITE + "/images/property-covers/" + name,
             "sha256": digest, "bytes": len(data)}
    validator = headers.get("etag")
    if validator:
        if len(validator) > 1024 or any(c in validator for c in "\r\n"):
            raise CoverError("Invalid public image validator")
        entry["etag"] = validator
    return entry


def cache(snapshot, output, manifest, project, workers=4):
    output, manifest = safe_path(output), safe_path(manifest)
    if output.exists() and not output.is_dir():
        raise CoverError("Cover output is not a directory")
    covers = source_covers(snapshot, project)
    previous = old_manifest(manifest, output, project)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        entries = list(pool.map(lambda pair: (pair[0], cache_one(pair[0], pair[1], previous.get(pair[0]), output, project)), sorted(covers.items())))
    result = {"version": 1, "covers": dict(entries)}
    data = (json.dumps(result, indent=2, ensure_ascii=False) + "\n").encode()
    if not manifest.exists() or manifest.read_bytes() != data:
        atomic_write(manifest, data)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "catalogue/properties.json")
    parser.add_argument("--manifest", type=Path, default=ROOT / "catalogue/cover-images.json")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "images/property-covers")
    parser.add_argument("--workers", type=int, choices=range(1, 9), default=4)
    args = parser.parse_args(argv)
    try:
        result = cache(json.loads(args.source.read_text(encoding="utf-8")), args.output_dir, args.manifest, public_project(), args.workers)
        print(f"Validated website-owned original covers for {len(result['covers'])} active units")
        return 0
    except CoverError as error:
        print(f"COVER CACHE ERROR: {error}; prior manifest was retained", file=sys.stderr)
        return 1
    except (OSError, ValueError):
        print("COVER CACHE ERROR: Cover source, response or cache failed validation; prior manifest was retained", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
