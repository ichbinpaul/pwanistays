"""Pure, immutable property-route registry helpers.

Friendly pages can be staged while UUID URLs remain public canonicals. Activation
requires an explicit boolean setting; allocation never renames historical routes.
"""
from __future__ import annotations

from copy import deepcopy
import json
import re
import uuid

SITE = "https://pwanistays.com"
BOOTSTRAP_MARKER = "// PWANISTAYS_PROPERTY_ROUTES_V1"
RESERVED = {"index", "index-html", "new", "search", "feed", "assets", "images", "directory", "stays", "properties", "property"}
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


class RoutingError(ValueError):
    pass


def canonical_uuid(value):
    try:
        if not isinstance(value, str) or str(uuid.UUID(value)) != value:
            raise ValueError
    except (ValueError, AttributeError):
        raise RoutingError("Property IDs must be canonical UUIDs") from None
    return value


def checked_slug(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 32 or not SLUG.fullmatch(value) or value in RESERVED:
        raise RoutingError("Property slug is unsafe, reserved or too long")
    return value


def validate_registry(registry):
    if (not isinstance(registry, dict) or type(registry.get("version")) is not int
            or registry["version"] != 1 or not isinstance(registry.get("slugs"), dict)):
        raise RoutingError("Unsupported immutable property route registry")
    if "ready_for_redirects" in registry and type(registry["ready_for_redirects"]) is not bool:
        raise RoutingError("Redirect readiness must be a boolean")
    result, used = {}, set()
    for identity, value in registry["slugs"].items():
        canonical_uuid(identity)
        slug = checked_slug(value)
        if slug in used:
            raise RoutingError("Property slugs must be unique")
        result[identity] = slug
        used.add(slug)
    return dict(sorted(result.items()))


def routing_path(identity, registry, friendly=False):
    canonical_uuid(identity)
    if type(friendly) is not bool:
        raise RoutingError("Friendly route activation must be an explicit boolean")
    slugs = validate_registry(registry)
    if friendly and identity not in slugs:
        raise RoutingError("An active property has no immutable friendly route")
    return "/stays/" + (slugs[identity] if friendly else identity) + "/"


def canonical_url(row):
    if not isinstance(row, dict):
        raise RoutingError("Property row must be an object")
    identity = canonical_uuid(row.get("id"))
    slug = checked_slug(row["slug"]) if "slug" in row else None
    current = SITE + "/stays/" + identity + "/"
    legacy = SITE + "/property.html?id=" + identity
    url = row.get("url", current)
    if url in (current, legacy):
        return current
    if slug and url == SITE + "/stays/" + slug + "/":
        return url
    raise RoutingError("Property URL does not match its UUID or assigned slug")


def prepare_snapshot(snapshot, settings, registry):
    if (not isinstance(snapshot, dict) or type(snapshot.get("version")) is not int
            or snapshot["version"] != 1):
        raise RoutingError("Unsupported property source snapshot")
    if (not isinstance(settings, dict) or type(settings.get("version")) is not int
            or settings["version"] != 1 or type(settings.get("use_friendly_urls")) is not bool):
        raise RoutingError("Routing settings require an explicit version and boolean activation flag")
    validate_registry(registry)
    # Lazy import avoids a module-level cycle with the catalogue builder's CLI.
    from plan_property_urls import allocate
    allocated = allocate(snapshot.get("properties"), registry)
    new_registry = deepcopy(registry)
    new_registry.update(allocated)
    new_registry["ready_for_redirects"] = settings["use_friendly_urls"]
    slugs = validate_registry(new_registry)
    result = deepcopy(snapshot)
    for row in result["properties"]:
        canonical_url(row)  # Reject arbitrary source URLs before assigning routes.
        if "slug" in row and row["slug"] != slugs[row["id"]]:
            raise RoutingError("Property slug conflicts with its immutable registry assignment")
        row["slug"] = slugs[row["id"]]
        row["url"] = SITE + routing_path(row["id"], new_registry, settings["use_friendly_urls"])
    result["properties"].sort(key=lambda row: row["id"])
    routes = {identity: "/stays/" + slug + "/" for identity, slug in slugs.items()}
    bootstrap = BOOTSTRAP_MARKER + "\nwindow.PwaniPropertyRoutes = " + json.dumps(
        {"enabled": settings["use_friendly_urls"], "paths": routes}, ensure_ascii=True,
        separators=(",", ":"), sort_keys=True) + ";\n"
    return result, new_registry, bootstrap
