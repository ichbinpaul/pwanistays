#!/usr/bin/env python3
"""Prepare locally hosted, responsive WebP copies of reviewed trip photographs.

This is a manual asset-preparation command, not a deployment-time downloader.
The published pages depend only on the committed images, never source websites.
"""
from __future__ import annotations
import argparse
from collections import Counter
from io import BytesIO
import hashlib
from html import unescape
import json
from pathlib import Path
import re
from urllib.parse import urlsplit, unquote, urlencode
from urllib.request import Request, urlopen

from PIL import Image, ImageOps
from build_whatsapp_catalogue import atomic_write

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'content/experience-photo-sources.json'
CONTENT = ROOT / 'content/experience-trips.json'
OUTPUT = ROOT / 'images/experiences'
ALLOWED_HOSTS = {'commons.wikimedia.org', 'upload.wikimedia.org', 'thumb.wikimedia.org'}
CARD_SIZES = '(max-width: 760px) calc(100vw - 40px), (max-width: 1050px) 44vw, 384px'
HERO_SIZES = '(max-width: 760px) calc(100vw - 40px), (max-width: 1100px) 48vw, 620px'


def commons_info(row, cache, download):
    """Retain source authorship/licence alongside the locally hosted copy."""
    source = row['source']
    key = hashlib.sha256(source.encode()).hexdigest()
    path = cache / (key + '.metadata.json')
    if path.exists():
        info = json.loads(path.read_text())
    elif download:
        filename = unquote(urlsplit(source).path.rsplit('/', 1)[-1])
        query = urlencode({'action': 'query', 'format': 'json', 'prop': 'imageinfo',
                           'iiprop': 'url|extmetadata', 'iiurlwidth': 1200,
                           'titles': 'File:' + filename})
        request = Request('https://commons.wikimedia.org/w/api.php?' + query,
                          headers={'User-Agent': 'PwaniStays-ImagePreparation/1.0 (https://pwanistays.com/)'})
        with urlopen(request, timeout=30) as response:
            document = json.load(response)
        info = next((p['imageinfo'][0] for p in document['query']['pages'].values()
                     if p.get('imageinfo')), None)
        if not info:
            raise ValueError('Original Commons filename no longer resolves; review this source')
        atomic_write(path, (json.dumps(info, ensure_ascii=False, indent=2) + '\n').encode())
    else:
        raise ValueError('Source attribution not cached; run with --download')
    metadata = info.get('extmetadata', {})
    artist = unescape(re.sub('<[^>]*>', '', metadata.get('Artist', {}).get('value', ''))).strip()
    row.update({'author': artist, 'license': metadata.get('LicenseUrl', {}).get('value', ''),
                'license_name': metadata.get('LicenseShortName', {}).get('value', ''),
                'attribution_url': info['descriptionurl']})
    return info.get('thumburl') or info['url']


def read_original(row, cache, download):
    source = row['source']
    if source.startswith('/images/'):
        path = (ROOT / source.lstrip('/')).resolve()
        if not path.is_relative_to(ROOT / 'images'):
            raise ValueError('Invalid local image path')
        return path.read_bytes()
    parsed = urlsplit(source)
    if parsed.scheme != 'https' or parsed.hostname not in ALLOWED_HOSTS:
        raise ValueError('Only original Wikimedia photo sources can be downloaded')
    resolved = commons_info(row, cache, download) if parsed.hostname == 'commons.wikimedia.org' else source
    if urlsplit(resolved).scheme != 'https' or urlsplit(resolved).hostname not in ALLOWED_HOSTS:
        raise ValueError('Unexpected photo download host')
    path = cache / (hashlib.sha256(source.encode()).hexdigest() + '.image')
    if path.exists():
        return path.read_bytes()
    if not download:
        raise ValueError(f"Original not cached: {row['stem']}; run with --download")
    req = Request(resolved, headers={'User-Agent': 'PwaniStays-photo-preparation/1.0 (https://pwanistays.com)'})
    with urlopen(req, timeout=30) as response:
        if urlsplit(response.geturl()).hostname not in ALLOWED_HOSTS:
            raise ValueError('Unexpected image redirect')
        if not response.headers.get('Content-Type', '').startswith('image/'):
            raise ValueError(f"Source is not an image: {row['stem']}")
        data = response.read(16 * 1024 * 1024 + 1)
    if len(data) > 16 * 1024 * 1024:
        raise ValueError('Image exceeds the download limit')
    # Verify before caching, so error pages cannot become permanent assets.
    with Image.open(BytesIO(data)) as image:
        image.verify()
    atomic_write(path, data)
    return data


def encode_variants(row, data):
    with Image.open(BytesIO(data)) as original:
        image = ImageOps.exif_transpose(original).convert('RGB')
    if image.width < 300 or image.height < 180:
        raise ValueError(f"Source too small: {row['stem']}")
    # Match the display frame, retaining the reviewed subject and natural colour.
    # This avoids downloading a tall portrait only to hide most of it with CSS.
    widths = (640, 1200) if row['role'] == 'hero' else (360, 720)
    ratio = 4 / 3 if row['role'] == 'hero' else 3 / 2
    position = tuple(float(p.rstrip('%')) / 100 for p in row.get('position', '50% 50%').split())
    variants = []
    for requested in widths:
        width = min(requested, image.width, int(image.height * ratio))
        if any(v['width'] == width for v in variants):
            continue
        height = round(width / ratio)
        small = ImageOps.fit(image, (width, height), Image.Resampling.LANCZOS, centering=position)
        budget = 24_000 if width <= 360 else 75_000 if width <= 720 else 150_000
        for quality in (76, 72, 68, 64, 60):
            encoded = BytesIO()
            small.save(encoded, 'WEBP', quality=quality, method=6)
            result = encoded.getvalue()
            if len(result) <= budget:
                break
        filename = f"{row['stem']}-{width}.webp"
        variants.append({'src': '/images/experiences/' + filename, 'width': width,
                         'height': height, 'bytes': len(result), 'quality': quality,
                         'data': result})
    return variants


def prepare(rows, cache, download):
    stems = [r['stem'] for r in rows]
    if len(set(stems)) != len(stems) or any(not re.fullmatch('[a-z0-9]+(?:-[a-z0-9]+)*', s) for s in stems):
        raise ValueError('Photo filenames must be unique lowercase word slugs')
    prepared = []
    trip_hashes = {}
    for row in rows:
        try:
            data = read_original(row, cache, download)
            digest = hashlib.sha256(data).hexdigest()
            if row['role'] == 'trip':
                if digest in trip_hashes:
                    raise ValueError('Duplicate trip photograph: ' + trip_hashes[digest])
                trip_hashes[digest] = row['stem']
            variants = encode_variants(row, data)
            prepared.append((row, digest, variants))
            print(f"Prepared {row['stem']}: " + ', '.join(f"{v['width']}px {v['bytes'] / 1024:.1f} KiB" for v in variants), flush=True)
        except Exception as exc:
            raise ValueError(f"Cannot prepare {row['stem']}: {exc}") from exc
    return prepared


def publish(prepared):
    content = json.loads(CONTENT.read_text())
    catalog = {c['slug']: c for c in content['categories']}
    counts = Counter(row['page'] for row, _, _ in prepared if row['role'] == 'trip')
    if counts != Counter({slug: len(c['items']) for slug, c in catalog.items()}):
        raise ValueError('Photo manifest must cover every trip exactly once')
    expected = {(slug, trip['title']) for slug, group in catalog.items() for trip in group['items']}
    actual = [(row['page'], row['title']) for row, _, _ in prepared if row['role'] == 'trip']
    if len(actual) != len(set(actual)) or set(actual) != expected:
        raise ValueError('Photo assignments must match every trip title exactly once')
    if Counter(row['page'] for row, _, _ in prepared if row['role'] == 'hero') != Counter({slug: 1 for slug in catalog}):
        raise ValueError('Every destination needs exactly one cover photo')
    used = set()
    report = []
    for row, digest, variants in prepared:
        largest = variants[-1]
        image = {k: largest[k] for k in ('src', 'width', 'height')}
        image.update({'srcset': ', '.join(f"{v['src']} {v['width']}w" for v in variants),
                      'sizes': HERO_SIZES if row['role'] == 'hero' else CARD_SIZES,
                      'alt': row['alt'], 'caption': row['caption'],
                      'source': row['source'], 'source_sha256': digest})
        for key in ('author', 'license', 'license_name', 'attribution_url', 'position'):
            if row.get(key):
                image[key] = row[key]
        group = catalog[row['page']]
        if row['role'] == 'hero':
            group['hero_image'] = image
        else:
            trip = next(t for t in group['items'] if t['title'] == row['title'])
            trip['image'] = image
        for variant in variants:
            used.add(variant['src'])
        report.append({'title': row['title'], 'source': row['source'], 'variants': [
            {k: v[k] for k in ('src', 'width', 'height', 'bytes', 'quality')} for v in variants]})
    # Fully prepare all 28 photos before replacing any page metadata.
    for _, _, variants in prepared:
        for variant in variants:
            atomic_write(ROOT / variant['src'].lstrip('/'), variant['data'])
    atomic_write(CONTENT, (json.dumps(content, ensure_ascii=False, indent=2) + '\n').encode())
    atomic_write(ROOT / 'content/experience-image-report.json', (json.dumps(report, ensure_ascii=False, indent=2) + '\n').encode())
    print(f"Published {len(prepared)} local photographs ({len(used)} responsive files)")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--download', action='store_true', help='Download missing originals into the local cache')
    parser.add_argument('--cache', type=Path, default=Path('/tmp/pwanistays-experience-originals'))
    parser.add_argument('--only-local', action='store_true', help='Prepare local originals without changing pages')
    args = parser.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    document = json.loads(SOURCE.read_text())
    if document.get('version') != 1:
        raise ValueError('Unsupported photo manifest version')
    rows = document['photos']
    if args.only_local:
        rows = [row for row in rows if row['source'].startswith('/images/')]
    prepared = prepare(rows, args.cache, args.download)
    if args.only_local:
        for _, _, variants in prepared:
            for variant in variants:
                atomic_write(ROOT / variant['src'].lstrip('/'), variant['data'])
    else:
        publish(prepared)


if __name__ == '__main__':
    main()
