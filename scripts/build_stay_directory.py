#!/usr/bin/env python3
"""Build a crawlable accommodation directory from the validated public snapshot."""
import argparse
from collections import defaultdict
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import sys

from build_property_previews import ROOT, SITE, validate_source, load_cover_images
from build_whatsapp_catalogue import atomic_write
from property_routes import canonical_url
from site_chrome import SITE_FOOTER

MARKER = "<!-- PWANISTAYS_STAY_DIRECTORY_V1 -->"
TYPES = {"studio": "Studio", "villa": "Villa", **{
    f"{number}br": f"{number} bedroom" + ("s" if number > 1 else "") for number in range(1, 6)}}


def render(snapshot):
    rows = validate_source(snapshot)
    urls = {row["id"]: canonical_url(row) for row in rows}
    if len(set(urls.values())) != len(rows):
        raise ValueError("Multiple properties resolve to the same canonical URL")
    groups = defaultdict(list)
    for row in rows:
        groups[row.get("location") or "Other locations"].append(row)
    links, sections, ordered_rows = [], [], []
    for location, items in sorted(groups.items()):
        anchor = "location-" + sha256(location.encode()).hexdigest()[:12]
        links.append(f'<a href="#{anchor}">{escape(location)} ({len(items)})</a>')
        cards = []
        for row in sorted(items, key=lambda item: (item["title"].casefold(), item["id"])):
            ordered_rows.append(row)
            url = urls[row["id"]].removeprefix(SITE)
            cards.append(f'''<article class="pw-card directory-card">
  <a href="{url}" tabindex="-1" aria-hidden="true"><img src="{escape(row.get('seo_image') or row['images'][0], quote=True)}" alt="{escape(row['title'], quote=True)} — property photo" loading="lazy" decoding="async" width="640" height="426"></a>
  <div class="pw-pad"><h3><a href="{url}">{escape(row['title'])}</a></h3>
  <p>{escape(location)} · {escape(TYPES.get(row.get('unit_type'), row.get('unit_type') or 'Holiday accommodation'))}</p>
  <p class="pw-small">View the unit’s photos and amenities, then request rates for your dates.</p></div>
</article>''')
        sections.append(f'<section id="{anchor}" class="directory-section"><h2>Stays in {escape(location)}</h2><div class="directory-grid">' + "\n".join(cards) + '</div></section>')
    schema = {"@context": "https://schema.org", "@type": "CollectionPage",
              "@id": SITE + "/stays.html", "url": SITE + "/stays.html",
              "name": "Coastal apartments, villas and holiday stays | PwaniStays",
              "mainEntity": {"@type": "ItemList", "numberOfItems": len(rows),
                  "itemListElement": [{"@type": "ListItem", "position": index + 1,
                     "url": urls[row["id"]], "name": row["title"]} for index, row in enumerate(ordered_rows)]}}
    structured = json.dumps(schema, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return f'''<!DOCTYPE html>
<html lang="en">
{MARKER}
<head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Coastal Apartments, Villas &amp; Holiday Stays | PwaniStays</title>
  <meta name="description" content="Browse PwaniStays apartments, villas and holiday accommodation by location, including Nyali, Bamburi, Diani, Shanzu, Kilifi and Malindi. View photos and request rates.">
  <meta name="robots" content="index,follow,max-image-preview:large">
  <link rel="canonical" href="{SITE}/stays.html">
  <meta property="og:type" content="website"><meta property="og:url" content="{SITE}/stays.html">
  <meta property="og:title" content="Coastal Apartments, Villas &amp; Holiday Stays | PwaniStays">
  <meta property="og:description" content="Browse coastal accommodation by location and view each unit’s photos and amenities.">
  <meta property="og:image" content="{escape(rows[0].get('seo_image') or rows[0]['images'][0], quote=True)}">
  <link rel="icon" href="/favicon-32x32.png"><link rel="stylesheet" href="/header.css"><link rel="stylesheet" href="/new-pages.css">
  <link rel="stylesheet" href="/stay-directory.css?v=2"><link rel="stylesheet" href="/experiences.css?v=1"><link rel="stylesheet" href="/experience-trips.css?v=1">
  <script src="/i18n.js" defer></script><script src="/header-loader.js" defer></script>
  <script type="application/ld+json">{structured}</script>
</head>
<body class="experiences-page directory-page">
  <div id="site-header"></div>
  <main class="pw-main pw-container">
    <nav class="pw-breadcrumbs" aria-label="Breadcrumb"><a href="/">Home</a> / Accommodation</nav>
    <h1 class="pw-title">Apartments, villas and holiday stays on Kenya’s coast</h1>
    <p class="pw-lead">Browse {len(rows)} listed units by location. Open a property to see its photos and amenities, select your dates and request a personalised quotation.</p>
    <p>Listings describe accommodation offered through PwaniStays. Availability and total rates are confirmed individually for your dates.</p>
    <p><a href="/guides/">Read the Nyali, Diani and Shanzu accommodation guides</a> to compare areas and plan your stay.</p>
    <nav class="directory-locations" aria-label="Browse accommodation by location">{' '.join(links)}</nav>
    {''.join(sections)}
    <p><a href="/how-it-works.html">How booking works</a> · <a href="/experiences.html">Explore experiences</a> · <a href="/#contact">Contact PwaniStays</a></p>
  </main>
  {SITE_FOOTER}
</body></html>
'''


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "catalogue/properties.json")
    parser.add_argument("--output", type=Path, default=ROOT / "stays.html")
    parser.add_argument("--covers", type=Path)
    args = parser.parse_args(argv)
    try:
        snapshot = json.loads(args.source.read_text(encoding="utf-8"))
        covers = args.covers or ROOT / "catalogue/cover-images.json"
        if args.covers or covers.exists():
            snapshot = load_cover_images(snapshot, covers)
        result = render(snapshot)
        if args.output.is_symlink():
            raise ValueError("Refusing a symbolic directory output")
        if args.output.exists() and MARKER not in args.output.read_text(encoding="utf-8"):
            raise ValueError("Refusing to replace an unowned directory page")
        data = result.encode("utf-8")
        if not args.output.exists() or args.output.read_bytes() != data:
            atomic_write(args.output, data)
        print("Generated crawlable accommodation directory")
        return 0
    except Exception:
        print("DIRECTORY ERROR: Could not safely generate accommodation directory", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
