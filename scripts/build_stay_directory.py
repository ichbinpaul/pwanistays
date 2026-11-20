#!/usr/bin/env python3
"""Build a crawlable accommodation directory from the validated public snapshot."""
import argparse
from collections import defaultdict
from hashlib import sha256
from html import escape
from io import BytesIO
import json
from pathlib import Path
import sys

from build_property_previews import ROOT, SITE, cover_path, validate_source, load_cover_images
from build_whatsapp_catalogue import atomic_write
from property_routes import canonical_url
from site_chrome import SITE_FOOTER

MARKER = "<!-- PWANISTAYS_STAY_DIRECTORY_V1 -->"
TYPES = {"studio": "Studio", "villa": "Villa", **{
    f"{number}br": f"{number} bedroom" + ("s" if number > 1 else "") for number in range(1, 6)}}


THUMBNAIL_WIDTHS = (360, 720)
SOCIAL_IMAGE = SITE + "/images/experiences/watamu-turtle-bay-coast-960.webp"


def build_thumbnails(snapshot):
    """Build public directory thumbnails from the verified, local original covers."""
    from PIL import Image, ImageOps

    result = {}
    output = ROOT / "images/stay-thumbnails"
    if output.is_symlink():
        raise ValueError("Refusing a symbolic thumbnail directory")
    for row in snapshot["properties"]:
        relative, _ = cover_path(row["seo_image"], row["id"])
        source = ROOT / relative
        variants = [output / f"{source.stem}-{width}.webp" for width in THUMBNAIL_WIDTHS]
        if any(path.is_symlink() for path in variants):
            raise ValueError("Refusing a symbolic thumbnail")
        if not all(path.is_file() for path in variants):
            try:
                with Image.open(source) as image:
                    cover = ImageOps.exif_transpose(image).convert("RGB")
                    for width, path in zip(THUMBNAIL_WIDTHS, variants):
                        if path.is_file():
                            continue
                        resized = ImageOps.fit(cover, (width, width * 2 // 3), Image.Resampling.LANCZOS)
                        buffer = BytesIO()
                        resized.save(buffer, "WEBP", quality=72, method=4)
                        atomic_write(path, buffer.getvalue())
            except (OSError, Image.DecompressionBombError):
                print(f"Using original cover for {row['id']}; thumbnail generation failed.", file=sys.stderr)
                continue
        result[row["id"]] = tuple("/" + path.relative_to(ROOT).as_posix() for path in variants)
    return result


def render(snapshot, thumbnails=None):
    thumbnails = thumbnails or {}
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
            image_url = row.get("seo_image") or row["images"][0]
            responsive = ""
            if row["id"] in thumbnails:
                small, large = thumbnails[row["id"]]
                image_url = small
                responsive = (f' srcset="{small} 360w, {large} 720w"'
                              ' sizes="(max-width: 580px) calc(100vw - 40px), '
                              '(max-width: 900px) calc(50vw - 42px), '
                              '(max-width: 1312px) calc(33vw - 52px), 386px"')
            cards.append(f'''<article class="directory-card">
  <a href="{url}" tabindex="-1" aria-hidden="true"><img src="{escape(image_url, quote=True)}"{responsive} alt="{escape(row['title'], quote=True)} — property photo" loading="lazy" decoding="async" width="640" height="426"></a>
  <div class="directory-card-copy"><h3><a href="{url}">{escape(row['title'])}</a></h3>
  <p>{escape(location)} · {escape(TYPES.get(row.get('unit_type'), row.get('unit_type') or 'Holiday accommodation'))}</p></div>
</article>''')
        sections.append(f'<section id="{anchor}" class="directory-section"><h2>Stays in {escape(location)}</h2><div class="directory-grid">' + "\n".join(cards) + '</div></section>')
    schema = {"@context": "https://schema.org", "@type": "CollectionPage",
              "@id": SITE + "/stays", "url": SITE + "/stays",
              "name": "Coastal apartments, villas and holiday stays | PwaniStays",
              "breadcrumb": {"@type": "BreadcrumbList", "itemListElement": [
                  {"@type": "ListItem", "position": 1, "name": "Home", "item": SITE + "/"},
                  {"@type": "ListItem", "position": 2, "name": "Accommodation", "item": SITE + "/stays"}]},
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
  <link rel="canonical" href="{SITE}/stays">
  <meta property="og:type" content="website"><meta property="og:url" content="{SITE}/stays">
  <meta property="og:title" content="Coastal Apartments, Villas &amp; Holiday Stays | PwaniStays">
  <meta property="og:description" content="Browse coastal accommodation by location and view each unit’s photos and amenities.">
  <meta property="og:site_name" content="PwaniStays"><meta property="og:locale" content="en_KE">
  <meta property="og:image" content="{SOCIAL_IMAGE}">
  <meta property="og:image:width" content="960"><meta property="og:image:height" content="720">
  <meta property="og:image:alt" content="The coastline at Turtle Bay in Watamu, Kenya">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="Coastal Apartments, Villas &amp; Holiday Stays | PwaniStays">
  <meta name="twitter:description" content="Explore apartments, villas and holiday stays by location on Kenya’s coast.">
  <meta name="twitter:image" content="{SOCIAL_IMAGE}">
  <meta name="twitter:image:alt" content="The coastline at Turtle Bay in Watamu, Kenya">
  <meta name="theme-color" content="#0d7a5f">
  <link rel="icon" href="/favicon-32x32.png"><link rel="stylesheet" href="/header.css">
  <link rel="stylesheet" href="/about.css?v=1"><link rel="stylesheet" href="/stay-directory.css?v=3">
  <script src="/i18n.js" defer></script><script src="/header-loader.js" defer></script>
  <script type="application/ld+json">{structured}</script>
</head>
<body class="about-page directory-page">
  <a class="about-skip" href="#main-content">Skip to content</a>
  <div id="site-header"></div>
  <main id="main-content" class="about-main" tabindex="-1">
    <div class="directory-intro">
      <div class="about-wrap">
        <nav class="directory-breadcrumb" aria-label="Breadcrumb"><a href="/">Home</a> / <span aria-current="page">Accommodation</span></nav>
        <h1>Find a stay on <em>Kenya’s coast.</em></h1>
        <p>Browse {len(rows)} apartments, villas and holiday stays. Open a listing to see photos and amenities, then request a quote for your dates.</p>
        <a class="about-text-link" href="/guides/">Compare coastal areas <span aria-hidden="true">→</span></a>
      </div>
    </div>
    <div class="about-wrap directory-list">
      <nav class="directory-locations" aria-label="Browse accommodation by location">{' '.join(links)}</nav>
      {''.join(sections)}
      <p class="directory-next"><a href="/how-it-works">How booking works</a> · <a href="/experiences">Explore experiences</a> · <a href="/#contact">Contact PwaniStays</a></p>
    </div>
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
        thumbnails = None
        if args.covers or covers.exists():
            snapshot = load_cover_images(snapshot, covers)
            thumbnails = build_thumbnails(snapshot)
        result = render(snapshot, thumbnails)
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
