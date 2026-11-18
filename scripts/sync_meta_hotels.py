#!/usr/bin/env python3
"""Plan or explicitly apply a public source snapshot to Meta's Hotels API.

Default mode is fully offline. --apply requires secure environment configuration;
--connect and --prune are separate opt-ins. See CATALOGUE-SYNC.md.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener
import uuid

from build_whatsapp_catalogue import ROOT, valid_photo

PREFIX = "pwanistays:"
MAX_PAGES = 1000
NUMERIC_ID = re.compile(r"^[1-9][0-9]*$")


class SyncError(RuntimeError):
    """An actionable error that contains no credential or remote response body."""


def canonical_uuid(value):
    try:
        if not isinstance(value, str) or str(uuid.UUID(value)) != value:
            raise ValueError
    except (ValueError, AttributeError):
        raise SyncError("A property ID is not a canonical UUID") from None
    return value


def checked_address(value):
    if not isinstance(value, dict) or not value:
        raise SyncError("Approved address must be a nonempty object")
    strings = {"street_address", "city", "region", "country", "postal_code"}
    if set(value) - strings - {"neighborhoods", "latitude", "longitude"}:
        raise SyncError("Unsupported approved address field")
    for key, item in value.items():
        if key in strings and (not isinstance(item, str) or not item.strip()):
            raise SyncError("Address text must be nonempty")
        if key == "neighborhoods" and (not isinstance(item, list) or not all(
                isinstance(x, str) and x.strip() for x in item)):
            raise SyncError("Address neighborhoods must be a list of text values")
        if key in {"latitude", "longitude"} and (isinstance(item, bool) or
                not isinstance(item, (int, float)) or not math.isfinite(item) or
                not -(90 if key == "latitude" else 180) <= item <= (90 if key == "latitude" else 180)):
            raise SyncError("Address coordinates are outside the accepted range")
    if ("latitude" in value) != ("longitude" in value):
        raise SyncError("Provide both approved coordinates or neither")
    return value


def payloads(snapshot, details=None):
    if not isinstance(snapshot, dict) or snapshot.get("version") != 1:
        raise SyncError("Unsupported source snapshot version")
    rows = snapshot.get("properties")
    if not isinstance(rows, list) or not rows:
        raise SyncError("Source must contain a nonempty property list")
    details = {} if details is None else details
    if not isinstance(details, dict):
        raise SyncError("Approved details must be an object keyed by property UUID")
    for property_id, value in details.items():
        canonical_uuid(property_id)
        if not isinstance(value, dict) or set(value) != {"address"}:
            raise SyncError("Approved details may contain only an address object")
        checked_address(value["address"])
    result, seen = [], set()
    for row in rows:
        if not isinstance(row, dict):
            raise SyncError("Malformed source property")
        property_id = canonical_uuid(row.get("id"))
        if property_id in seen:
            raise SyncError("Duplicate source property ID")
        seen.add(property_id)
        if any(not isinstance(row.get(field), str) or not row[field].strip()
               for field in ("title", "description")):
            raise SyncError("Property title and public description are required")
        expected_url = "https://pwanistays.com/stays/" + property_id + "/"
        legacy_url = "https://pwanistays.com/property.html?id=" + property_id
        if row.get("url") not in (expected_url, legacy_url):
            raise SyncError("Property must use its canonical public website link")
        images = row.get("images")
        if (not isinstance(images, list) or not 1 <= len(images) <= 10 or
                any(not isinstance(image, str) or not valid_photo(image) for image in images) or
                len(set(images)) != len(images)):
            raise SyncError("Each property needs one to ten distinct valid HTTPS image URLs")
        item = {"hotel_id": PREFIX + property_id, "name": row["title"].strip(),
                "description": row["description"].strip(), "brand": "PwaniStays",
                "url": expected_url, "images": [{"image_url": image} for image in images]}
        if property_id in details:
            item["address"] = details[property_id]["address"]
        result.append(item)
    if set(details) - seen:
        raise SyncError("Approved details contain IDs absent from the source snapshot")
    return sorted(result, key=lambda item: item["hotel_id"])


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward the bearer token to another destination.


class Graph:
    def __init__(self, token, version):
        if not token or not re.fullmatch(r"v[1-9][0-9]*\.0", version or ""):
            raise SyncError("A token and explicit Graph version such as v26.0 are required")
        self.token, self.base = token, "https://graph.facebook.com/" + version
        self.opener = build_opener(NoRedirect())

    def safe_message(self, value, limit=500):
        # Log only selected error fields, never raw bodies, headers or request URLs.
        text = str(value).replace(self.token, "[REDACTED]")
        text = re.sub(r"https?://[^\s<>\"']+", "[URL REDACTED]", text, flags=re.I)
        text = re.sub(r"\bBearer\s+[^\s,;\"']+", "Bearer [REDACTED]", text, flags=re.I)
        text = re.sub(r"""\b(?:access_token|appsecret_proof|client_secret)["']?\s*[:=]\s*(?:"[^"]*"|'[^']*'|[^\s,;]+)""",
                      "credential=[REDACTED]", text, flags=re.I)
        text = re.sub(r"\bEAA[A-Za-z0-9_-]{12,}\b", "[REDACTED]", text)
        text = re.sub(r"\b[A-Za-z0-9_-]{40,}\b", "[REDACTED]", text)
        text = re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", text)
        return " ".join(text.split())[:limit]

    def failure(self, method, path, status, payload):
        message = f"Meta {method} {self.safe_message(path, 100)} rejected (HTTP {status})"
        error = payload.get("error") if isinstance(payload, dict) else None
        if not isinstance(error, dict):
            return message + "; no structured error details returned"
        parts = []
        for key in ("code", "error_subcode"):
            value = error.get(key)
            if type(value) is int:
                parts.append(f"{key}={value}")
        if isinstance(error.get("type"), str):
            parts.append("type=" + self.safe_message(error["type"], 80))
        if isinstance(error.get("message"), str):
            parts.append(self.safe_message(error["message"]))
        return message + ("; " + "; ".join(parts) if parts else "; no structured error details returned")

    def request(self, method, path, params=None):
        params = params or {}
        encoded = urlencode({key: json.dumps(value) if isinstance(value, (dict, list)) else value
                             for key, value in params.items()}).encode()
        url = self.base + "/" + path
        if method == "GET" and encoded:
            url += "?" + encoded.decode()
        req = Request(url, method=method,
                      data=encoded if method == "POST" else None,
                      headers={"Authorization": "Bearer " + self.token,
                               "Content-Type": "application/x-www-form-urlencoded",
                               "Accept": "application/json"})
        try:
            with self.opener.open(req, timeout=35) as response:
                result = json.load(response)
        except HTTPError as exc:
            try:
                # Bound parsing; an invalid/oversized body is never printed as fallback.
                payload = json.loads(exc.read(32768))
            except (OSError, ValueError, TypeError):
                payload = None
            finally:
                exc.close()
            raise SyncError(self.failure(method, path, exc.code, payload)) from None
        except (URLError, OSError, ValueError):
            raise SyncError("Meta connection failed or returned invalid JSON") from None
        if isinstance(result, dict) and "error" in result:
            raise SyncError(self.failure(method, path, 200, result))
        if not isinstance(result, dict):
            raise SyncError("Meta returned an unsuccessful response")
        return result


def graph_id(value):
    if not isinstance(value, str) or not NUMERIC_ID.fullmatch(value):
        raise SyncError("Meta account, catalogue and object IDs must be numeric")
    return value


def list_edge(graph, path, fields):
    rows, cursors, ids = [], set(), set()
    params = {"fields": fields, "limit": 100}
    for _ in range(MAX_PAGES):
        response = graph.request("GET", path, params)
        data = response.get("data")
        if not isinstance(data, list):
            raise SyncError("Malformed Meta listing response")
        for row in data:
            if not isinstance(row, dict):
                raise SyncError("Malformed Meta object")
            object_id = graph_id(row.get("id"))
            if object_id in ids:
                raise SyncError("Duplicate Meta object across pages")
            ids.add(object_id)
            rows.append(row)
        paging = response.get("paging", {})
        if not isinstance(paging, dict):
            raise SyncError("Malformed Meta pagination")
        if not paging.get("next"):
            return rows
        after = paging.get("cursors", {}).get("after")
        if not isinstance(after, str) or not after or after in cursors:
            raise SyncError("Invalid or repeated Meta pagination cursor")
        cursors.add(after)
        params["after"] = after  # Do not follow remote-provided URLs containing tokens.
    raise SyncError("Meta pagination limit reached; refusing incomplete synchronization")


def linked_catalogues(graph, waba):
    return {row["id"] for row in list_edge(graph, waba + "/product_catalogs", "id")}


def synchronize(graph, catalogue, waba, items, connect=False, prune=False):
    if not isinstance(items, list) or not items:
        raise SyncError("Refusing to synchronize an empty hotel plan")
    identities = set()
    for item in items:
        identity = item.get("hotel_id") if isinstance(item, dict) else None
        if not isinstance(identity, str) or not identity.startswith(PREFIX):
            raise SyncError("Hotel plan contains an unmanaged identity")
        canonical_uuid(identity[len(PREFIX):])
        if identity in identities:
            raise SyncError("Duplicate hotel plan identity")
        identities.add(identity)
    catalogue, waba = graph_id(catalogue), graph_id(waba)
    target = graph.request("GET", catalogue, {"fields": "id,name,vertical"})
    if target.get("id") != catalogue or target.get("vertical") != "hotels":
        raise SyncError("Target must be a verified Hotels catalogue")
    linked = linked_catalogues(graph, waba)
    if linked - {catalogue}:
        raise SyncError("Another catalogue is linked; automatic replacement is prohibited")
    if catalogue not in linked and not connect:
        raise SyncError("Target is not linked to this WhatsApp account; explicit --connect is required")
    remote, hotel_ids = {}, set()
    for row in list_edge(graph, catalogue + "/hotels", "id,hotel_id"):
        external_id = row.get("hotel_id")
        if not isinstance(external_id, str) or not external_id or external_id in hotel_ids:
            raise SyncError("Missing or duplicate remote hotel identity")
        hotel_ids.add(external_id)
        remote[external_id] = row["id"]
    if catalogue not in linked:
        graph.request("POST", waba + "/product_catalogs", {"catalog_id": catalogue})
        if linked_catalogues(graph, waba) != {catalogue}:
            raise SyncError("WhatsApp catalogue link could not be verified; no hotel writes were attempted")
    counts = {"created": 0, "updated": 0, "deleted": 0}
    for item in items:
        existing = remote.get(item["hotel_id"])
        payload = {key: value for key, value in item.items() if not existing or key != "hotel_id"}
        result = graph.request("POST", existing or catalogue + "/hotels", payload)
        if existing:
            if result.get("success") is not True and result.get("id") != existing:
                raise SyncError("Meta did not confirm a hotel update; pruning was not attempted")
        else:
            graph_id(result.get("id"))
        counts["updated" if existing else "created"] += 1
    if prune:
        expected = {item["hotel_id"] for item in items}
        for external_id, object_id in remote.items():
            if external_id.startswith(PREFIX) and external_id not in expected:
                try:
                    canonical_uuid(external_id[len(PREFIX):])
                except SyncError:
                    continue
                if graph.request("DELETE", object_id).get("success") is not True:
                    raise SyncError("Meta did not confirm deletion of a managed item")
                counts["deleted"] += 1
    return counts


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "catalogue/properties.json")
    parser.add_argument("--details", type=Path)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--connect", action="store_true")
    parser.add_argument("--prune", action="store_true")
    parser.add_argument("--only", action="append", default=[], metavar="PROPERTY_UUID",
                        help="limit to an existing source property; repeat for multiple items")
    args = parser.parse_args(argv)
    try:
        if (args.connect or args.prune) and not args.apply:
            raise SyncError("--connect and --prune require --apply")
        if args.prune and args.only:
            raise SyncError("--prune cannot be combined with --only")
        snapshot = json.loads(args.source.read_text(encoding="utf-8"))
        details = json.loads(args.details.read_text(encoding="utf-8")) if args.details else None
        items = payloads(snapshot, details)
        if args.only:
            selected = {PREFIX + canonical_uuid(value) for value in args.only}
            if selected - {item["hotel_id"] for item in items}:
                raise SyncError("--only contains a property absent from the source snapshot")
            items = [item for item in items if item["hotel_id"] in selected]
        plan = {"mode": "offline_dry_run", "property_count": len(items),
                "without_approved_address": sum("address" not in item for item in items),
                "warning": "API acceptance and Hotels-to-WhatsApp compatibility remain unvalidated",
                "hotels": items}
        if args.plan:
            if args.plan.resolve().is_relative_to(ROOT.resolve()):
                raise SyncError("Keep API plans outside the website checkout")
            args.plan.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if args.apply:
            names = ("META_ACCESS_TOKEN", "META_CATALOGUE_ID", "META_WHATSAPP_BUSINESS_ACCOUNT_ID", "META_GRAPH_VERSION")
            config = {name: os.environ.get(name, "").strip() for name in names}
            if not all(config.values()):
                raise SyncError("Missing required Meta environment configuration; supply values securely")
            graph = Graph(config[names[0]], config[names[3]])
            counts = synchronize(graph, config[names[1]], config[names[2]], items, args.connect, args.prune)
            print(json.dumps({"mode": "applied", **counts}))
        else:
            print(json.dumps({key: value for key, value in plan.items() if key != "hotels"},
                             ensure_ascii=False, indent=2))
        return 0
    except SyncError as exc:
        print(f"META SYNC ERROR: {exc}", file=sys.stderr)
        return 1
    except Exception:
        print("META SYNC ERROR: Local input could not be processed; no credential details are logged", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
