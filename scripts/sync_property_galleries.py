#!/usr/bin/env python3
"""Preview, backfill or watch the local photos for active PwaniStays properties."""
import argparse
from base64 import urlsafe_b64decode
from binascii import Error as Base64Error
from dataclasses import dataclass
from getpass import GetPassWarning, getpass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import warnings
from uuid import UUID

PROJECT = "https://aanyrtsfeeynykskwxen.supabase.co"
PUBLISHABLE_KEY = "sb_publishable_jda30uQX9ZzR_V8CzkeERw_nfx-QWkD"
BUCKET = "property_images"
REPO = "ichbinpaul/pwanistays"
WORKFLOW = "refresh-whatsapp-catalogue.yml"
MAX_BYTES = 50 * 1024 * 1024
PAGE_SIZE = 100
FIELDS = "id,title,folder_path,image_url,is_active"
UNSUPPORTED = {".heic", ".heif", ".tif", ".tiff", ".bmp", ".svg", ".dng", ".raw", ".jxl"}
FORMATS = {
    ".jpg": (".jpg", "image/jpeg"),
    ".jpeg": (".jpg", "image/jpeg"),
    ".png": (".png", "image/png"),
    ".webp": (".webp", "image/webp"),
    ".avif": (".avif", "image/avif"),
    ".gif": (".gif", "image/gif"),
}


class GalleryError(Exception):
    pass


@dataclass(frozen=True)
class Photo:
    path: Path
    extension: str
    mime: str
    digest: str


def read_photo(path):
    if path.is_symlink() or not 0 < path.stat().st_size <= MAX_BYTES:
        raise GalleryError(f"{path.name}: provide a regular image file up to 50 MiB.")
    data = path.read_bytes()
    if not 0 < len(data) <= MAX_BYTES:
        raise GalleryError(f"{path.name}: image exceeds 50 MiB.")
    return data


def inspect(path):
    extension, mime = FORMATS[path.suffix.lower()]
    data = read_photo(path)
    signature_matches = {
        ".jpg": data.startswith(b"\xff\xd8\xff"),
        ".png": data.startswith(b"\x89PNG\r\n\x1a\n"),
        ".webp": data.startswith(b"RIFF") and data[8:12] == b"WEBP",
        ".avif": data[4:8] == b"ftyp" and (b"avif" in data[8:40] or b"avis" in data[8:40]),
        ".gif": data.startswith((b"GIF87a", b"GIF89a")),
    }
    if not signature_matches[extension]:
        raise GalleryError(f"{path.name}: its file type does not match the filename.")
    return Photo(path, extension, mime, hashlib.sha256(data).hexdigest())


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request(method, path, *, headers=None, data=None, maximum=MAX_BYTES):
    req = Request(PROJECT + path, method=method, data=data, headers=headers or {})
    try:
        with build_opener(NoRedirect()).open(req, timeout=45) as response:
            body = response.read(maximum + 1)
            if len(body) > maximum:
                raise GalleryError("Supabase returned a response exceeding the expected size.")
            return response.status, body
    except HTTPError as error:
        with error:
            details = error.read(4096) if error.code in (401, 403) else b""
        return error.code, details
    except URLError as error:
        raise GalleryError(f"Could not reach the Supabase project ({type(error.reason).__name__}).") from None


def credentials():
    key = os.getenv("SUPABASE_SECRET_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not key:
        with warnings.catch_warnings():
            warnings.simplefilter("error", GetPassWarning)
            key = getpass("Supabase project secret key (hidden): ").strip()
    key = key.strip()
    if re.fullmatch(r"sb_secret_[A-Za-z0-9_-]+", key):
        return {"apikey": key}
    if re.fullmatch(r"[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", key):
        payload = key.split(".")[1]
        try:
            claims = json.loads(urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        except (ValueError, Base64Error):
            claims = None
        if isinstance(claims, dict) and claims.get("role") == "service_role":
            if claims.get("ref") not in (None, "aanyrtsfeeynykskwxen"):
                raise GalleryError("That legacy key belongs to a different Supabase project.")
            return {"apikey": key, "Authorization": "Bearer " + key}
    raise GalleryError("Use the complete sb_secret_ key or the legacy service_role key from the PwaniStays project.")


def access_hint(status, body):
    if status not in (401, 403):
        return ""
    response = body.decode("utf-8", errors="replace").lower()
    if "expired" in response and "jwt" in response:
        return " Supabase reported an expired legacy token. Use the current project secret key."
    if "browser" in response and "secret" in response:
        return " Supabase rejected the secret as a browser request. Run the script in PowerShell."
    if "permission denied" in response:
        return " Supabase reported a permission denial. Check the project key with the project owner."
    if status == 401:
        return " Supabase rejected the credential. Copy the revealed key from this project's API Keys settings."
    return " Check that the key has permission to read this project."


def ensure_uploaded(object_path, photo, headers):
    public_path = f"/storage/v1/object/public/{BUCKET}/{object_path}"
    status, content = request("GET", public_path)
    if status == 200:
        if hashlib.sha256(content).hexdigest() == photo.digest:
            return
        raise GalleryError("An existing gallery file differs from the local photo.")
    if status != 404 and status != 400:
        raise GalleryError(f"Could not check the gallery file (HTTP {status}).")
    data = read_photo(photo.path)
    if hashlib.sha256(data).hexdigest() != photo.digest:
        raise GalleryError(f"{photo.path.name} changed during the update. Run the script again.")
    status, _ = request("POST", f"/storage/v1/object/{BUCKET}/{object_path}",
                        headers={**headers, "Content-Type": photo.mime, "x-upsert": "false"}, data=data)
    if status not in {200, 201, 400, 409}:
        raise GalleryError(f"Could not upload {photo.path.name} (HTTP {status}).")
    upload_status = status
    for attempt in range(4):
        status, content = request("GET", public_path)
        if status == 200:
            if hashlib.sha256(content).hexdigest() == photo.digest:
                return
            raise GalleryError(f"Supabase returned different bytes for {photo.path.name}.")
        if attempt < 3:
            time.sleep(2)
    raise GalleryError(f"Could not verify {photo.path.name} (upload HTTP {upload_status}, read HTTP {status}).")


def refresh_website():
    gh = shutil.which("gh")
    if gh:
        run = subprocess.run([gh, "workflow", "run", WORKFLOW, "--repo", REPO,
                              "--ref", "main", "-f", "operation=source_only"], check=False)
        if run.returncode == 0:
            print("Website catalogue refresh requested. Check the workflow run for deployment status.")
            return
    print("The scheduled website catalogue refresh will pick up these changes. To request it now:")
    print(f"https://github.com/{REPO}/actions/workflows/{WORKFLOW}")


def relative_folder(value):
    if not isinstance(value, str) or not value.strip():
        raise GalleryError("This listing has no registered photo folder.")
    parts = value.strip().replace("\\", "/").split("/")
    if any(part in ("", ".", "..") or ":" in part for part in parts):
        raise GalleryError("The registered photo folder must be relative to the photos root.")
    return Path(*parts)


def list_properties(headers):
    rows = []
    seen = set()
    for offset in range(0, 100_000, PAGE_SIZE):
        query = urlencode({"select": FIELDS, "is_active": "eq.true", "order": "id.asc",
                           "offset": offset, "limit": PAGE_SIZE})
        status, body = request("GET", "/rest/v1/properties?" + query, headers=headers)
        if status != 200:
            raise GalleryError(f"Could not read active listings (HTTP {status})." + access_hint(status, body))
        batch = json.loads(body)
        if not isinstance(batch, list):
            raise GalleryError("Unexpected response while reading active listings.")
        for row in batch:
            identity = row["id"]
            if str(UUID(identity)) != identity or identity in seen or row["is_active"] is not True:
                raise GalleryError("The active listing list is incomplete or contains invalid IDs.")
            rows.append(row)
            seen.add(identity)
        if len(batch) < PAGE_SIZE:
            if not rows:
                raise GalleryError("No active listings were returned.")
            return rows
    raise GalleryError("Could not finish reading all active listing pages.")


def mapped_folders(root, rows):
    folders = {}
    problems = {}
    for row in rows:
        identity = row["id"]
        try:
            relative = relative_folder(row.get("folder_path"))
            folder = root.joinpath(relative)
            resolved = folder.resolve()
            if not resolved.is_relative_to(root) or resolved == root:
                raise GalleryError("The registered folder points outside the photos root.")
            folders[identity] = (resolved, relative)
        except (GalleryError, OSError, ValueError, RuntimeError) as error:
            problems[identity] = str(error)

    for identity, (folder, _) in folders.items():
        for other, (other_folder, _) in folders.items():
            if identity != other and (folder.is_relative_to(other_folder) or other_folder.is_relative_to(folder)):
                problems[identity] = "Its photo folder overlaps another active listing's folder."
                break
    return folders, problems


def snapshot(folder):
    if not folder.is_dir():
        raise GalleryError("Registered photo folder is missing.")
    entries = []

    def scan(directory):
        for file in directory.iterdir():
            if file.name.startswith("."):
                continue
            if file.is_symlink() or file.resolve() != file:
                raise GalleryError(f"{file.relative_to(folder)} is a link. Use photos inside the mapped folder.")
            if file.is_dir():
                scan(file)
                continue
            if not file.is_file():
                continue
            extension = file.suffix.lower()
            if extension in UNSUPPORTED:
                raise GalleryError(f"{file.relative_to(folder)} needs conversion to JPEG, PNG, WebP, AVIF or GIF.")
            if extension in FORMATS:
                info = file.stat()
                entries.append((file.relative_to(folder).as_posix(), info.st_size, info.st_mtime_ns, info.st_ctime_ns))

    scan(folder)
    if not entries:
        raise GalleryError("No eligible photos found. The live gallery stays in place.")
    return tuple(sorted(entries))


def natural_key(filename):
    return tuple((0, int(part)) if part.isdigit() else (1, part.casefold())
                 for part in re.split(r"(\d+)", filename)) + ((2, filename),)


def collect(folder, files):
    unique = {}
    for filename, *_ in sorted(files, key=lambda entry: natural_key(entry[0])):
        photo = inspect(folder / filename)
        unique.setdefault(photo.digest, photo)
    return list(unique.values())


def order_cover(row, photos):
    current = row.get("image_url") or ""
    root = f"/storage/v1/object/public/{BUCKET}/{row['id']}/"
    parsed = urlsplit(current)
    if parsed.scheme == "https" and parsed.netloc == urlsplit(PROJECT).netloc and parsed.path.startswith(root):
        status, content = request("GET", parsed.path)
        if status == 200:
            digest = hashlib.sha256(content).hexdigest()
            for index, photo in enumerate(photos):
                if photo.digest == digest:
                    photos.insert(0, photos.pop(index))
                    break
        elif status not in (400, 404):
            raise GalleryError(f"Could not check the current cover (HTTP {status}).")


def publish(row, folder, files, photos, headers):
    order_cover(row, photos)
    identity = row["id"]
    contents = "full-gallery-1:" + "".join(photo.digest for photo in photos)
    checksum = hashlib.sha256(contents.encode("ascii")).hexdigest()[:16]
    prefix = f"{identity}/_pwani_v6_{checksum}"
    objects = [f"{prefix}/{index:03d}{photo.extension}" for index, photo in enumerate(photos, 1)]
    cover = f"{PROJECT}/storage/v1/object/public/{BUCKET}/{objects[0]}"
    if row.get("image_url") == cover:
        return cover
    for index, (object_path, photo) in enumerate(zip(objects, photos), 1):
        ensure_uploaded(object_path, photo, headers)
        if index == len(objects) or index % 20 == 0:
            print(f"  Verified {index}/{len(objects)} photos", flush=True)
    if snapshot(folder) != files:
        raise GalleryError("The folder changed during upload. Retry after the edits finish.")

    previous_cover = row.get("image_url")
    path = "/rest/v1/properties?" + urlencode({
        "id": "eq." + identity, "is_active": "eq.true", "folder_path": "eq." + row["folder_path"],
        "image_url": "is.null" if previous_cover is None else "eq." + previous_cover,
        "select": "id,image_url",
    })
    status, body = request("PATCH", path, data=json.dumps({"image_url": cover}).encode("utf-8"),
                           headers={**headers, "Content-Type": "application/json", "Prefer": "return=representation"})
    if status != 200:
        raise GalleryError(f"Could not activate the gallery (HTTP {status})." + access_hint(status, body))
    if json.loads(body) != [{"id": identity, "image_url": cover}]:
        raise GalleryError("The property changed during the upload. Retry after reviewing the listing.")
    return cover


def run_scan(root, selected, headers, apply, last_seen, completed, watch, report):
    rows = list_properties(headers)
    folders, problems = mapped_folders(root, rows)
    matched = set()
    failures = changes = checked = 0
    for row in rows:
        identity = row["id"]
        folder, registered = folders.get(identity, (None, None))
        if selected and registered not in selected:
            continue
        matched.add(registered)
        try:
            if identity in problems:
                raise GalleryError(problems[identity])
            files = snapshot(folder)
            fingerprint = (folder, files)
            previous = last_seen.get(identity)
            last_seen[identity] = fingerprint
            if watch and previous != fingerprint:
                report.pop(identity, None)
                continue
            if completed.get(identity) == fingerprint:
                continue
            photos = collect(folder, files)
            if snapshot(folder) != files:
                raise GalleryError("The folder changed while checking its photos. Retry when the copy finishes.")
            print(f"{row['title']} [{registered}]: {len(photos)} unique photos"
                  f" ({len(files) - len(photos)} identical copies)", flush=True)
            if apply:
                cover = publish(row, folder, files, photos, headers)
                changes += int(cover != row.get("image_url"))
            completed[identity] = fingerprint
            checked += 1
            report.pop(identity, None)
        except (GalleryError, OSError, ValueError) as error:
            last_seen.pop(identity, None)
            failures += 1
            if report.get(identity) != str(error):
                print(f"{row['title']} [{registered or identity}]: {error}", file=sys.stderr, flush=True)
                report[identity] = str(error)
    if selected - matched:
        raise GalleryError("No active listing matched: " + ", ".join(str(folder) for folder in sorted(selected - matched)))
    if not watch or checked or changes:
        print(f"Checked {checked} galleries, activated {changes}, {failures} need attention.", flush=True)
    return changes, failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="The folder containing the registered property folders.")
    parser.add_argument("--folder", action="append", default=[], metavar="RELATIVE_PATH",
                        help="Limit a run to this registered folder. Repeat to choose multiple folders.")
    parser.add_argument("--apply", action="store_true", help="Upload and activate complete gallery revisions.")
    parser.add_argument("--watch", action="store_true", help="Scan for changed folders until Ctrl+C.")
    parser.add_argument("--interval", type=int, default=60, help="Seconds between watch scans (default 60).")
    args = parser.parse_args()
    if args.interval < 10:
        parser.error("--interval must be at least 10 seconds")
    try:
        root = args.root.resolve(strict=True)
        if not root.is_dir():
            raise GalleryError("Provide the property media root directory.")
        selected = {relative_folder(folder) for folder in args.folder}
        headers = credentials() if args.apply else {"apikey": PUBLISHABLE_KEY}
        last_seen, completed, report = {}, {}, {}
        if args.watch:
            print(f"Watching {root} every {args.interval} seconds. Press Ctrl+C to stop.", flush=True)
        while True:
            try:
                changes, failures = run_scan(root, selected, headers, args.apply, last_seen, completed, args.watch, report)
                if changes:
                    refresh_website()
                if not args.watch:
                    return int(bool(failures))
            except (GalleryError, OSError, ValueError, KeyError, TypeError) as error:
                if not args.watch or selected:
                    raise
                print(f"Scan failed; will retry: {error}", file=sys.stderr, flush=True)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("Gallery sync stopped.")
        return 0
    except (GalleryError, OSError, ValueError, KeyError, TypeError, GetPassWarning) as error:
        print(f"Gallery sync stopped: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
