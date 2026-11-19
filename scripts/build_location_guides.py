#!/usr/bin/env python3
"""Build reviewed area guides with current, crawlable inventory links."""
import json
from html import escape
from pathlib import Path
from collections import Counter
from urllib.parse import urlsplit
from build_property_previews import validate_source
from build_whatsapp_catalogue import atomic_write
from property_routes import canonical_url
from content_copy import AREA_GUIDES

ROOT = Path(__file__).resolve().parents[1]
SITE = 'https://pwanistays.com'
MARKER = '<!-- PWANISTAYS_LOCATION_GUIDE_V1 -->'


def shell(title, summary, path, body, schema, image="/logo-mobile.png"):
    structured = json.dumps(schema, ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    return f'''<!doctype html><html lang="en">{MARKER}<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)} | PwaniStays</title><meta name="description" content="{escape(summary, quote=True)}">
<meta name="robots" content="index,follow"><link rel="canonical" href="{SITE}{path}">
<meta property="og:type" content="website"><meta property="og:url" content="{SITE}{path}">
<meta property="og:title" content="{escape(title, quote=True)}"><meta property="og:description" content="{escape(summary, quote=True)}">
<meta property="og:image" content="{SITE}{image}">
<link rel="icon" href="/favicon-32x32.png"><link rel="stylesheet" href="/header.css"><link rel="stylesheet" href="/new-pages.css"><link rel="stylesheet" href="/location-guides.css">
<script src="/header-loader.js" defer></script><script type="application/ld+json">{structured}</script>
</head><body><div id="site-header"></div><main class="pw-main pw-container">
<nav class="pw-breadcrumbs" aria-label="Breadcrumb"><a href="/">Home</a> / <a href="/stays.html">Accommodation</a> / <a href="/guides/">Area guides</a></nav>
<h1 class="pw-title">{escape(title)}</h1>{body}
</main><footer class="pw-footer"><div class="pw-container">PwaniStays · <a href="/how-it-works.html">How booking works</a> · <a href="/terms.html">Booking terms</a> · <a href="/cancellation.html">Cancellations</a></div></footer></body></html>'''


def render_guides(snapshot, document):
    rows = validate_source(snapshot)
    guides = document.get('guides')
    if document.get('version') != 1 or not isinstance(guides, list) or len(guides) != len(AREA_GUIDES):
        raise ValueError('Expected the reviewed area guides')
    if {(g['location'], g['slug']) for g in guides} != set(AREA_GUIDES.items()):
        raise ValueError('Unknown or duplicate guide location')
    output = {}
    for guide in guides:
        location, slug = guide['location'], guide['slug']
        items = sorted([r for r in rows if r.get('location') == location], key=lambda r: (r['title'].casefold(),r['id']))
        path = '/guides/' + slug + '/'
        prose = '<div class="guide-prose"><p class="pw-lead">' + escape(guide['intro']) + '</p><p><a href="#listed-stays">Browse current '+escape(location)+' stays</a></p>'
        for heading, *paragraphs in guide['sections']:
            prose += '<section><h2>'+escape(heading)+'</h2>'+''.join('<p>'+escape(p)+'</p>' for p in paragraphs)+'</section>'
        prose += '<section><h2>Questions before booking</h2>'+''.join('<h3>'+escape(q)+'</h3><p>'+escape(a)+'</p>' for q,a in guide['faq'])+'</section></div>'
        counts = Counter(r.get('unit_type') or 'other' for r in items)
        kinds = {'studio':'studios','villa':'villas',**{f'{n}br':f'{n}-bedroom units' for n in range(1,6)}}
        mix = ', '.join(f'{count} {kinds.get(kind, "other units")}' for kind,count in sorted(counts.items()))
        listings = f'<section id="listed-stays"><h2>Current stays in {escape(location)}</h2><p>{len(items)} listed units'+(f': {escape(mix)}.' if mix else '.')+' Listing status is updated regularly; availability for your dates is confirmed individually.</p>'
        listings += '<ul class="guide-listings">'+''.join('<li><a href="'+escape(urlsplit(canonical_url(r)).path, quote=True)+'">'+escape(r['title'])+'</a></li>' for r in items)+'</ul>'
        listings += '<p>Open a unit, select your dates and guest count, and send a quotation request. Confirm the sleeping arrangement, facilities and full charges before paying.</p></section>'
        related = '<nav class="directory-locations" aria-label="More area guides">'+''.join(f'<a href="/guides/{s}/">{escape(loc)} guide</a>' for loc,s in AREA_GUIDES.items() if loc!=location)+'</nav>'
        schema = {'@context':'https://schema.org','@graph':[
            {'@type':'CollectionPage','name':guide['title'],'description':guide['summary'],'url':SITE+path,'mainEntity':{'@type':'ItemList','numberOfItems':len(items),'itemListElement':[{'@type':'ListItem','position':i+1,'name':r['title'],'url':canonical_url(r)} for i,r in enumerate(items)]}},
            {'@type':'BreadcrumbList','itemListElement':[{'@type':'ListItem','position':1,'name':'Home','item':SITE+'/'},{'@type':'ListItem','position':2,'name':'Area guides','item':SITE+'/guides/'},{'@type':'ListItem','position':3,'name':location,'item':SITE+path}]}]}
        output[slug+'/index.html'] = shell(guide['title'],guide['summary'],path,prose+listings+related,schema, '/images/'+{'Nyali':'Nyali_beach_PwaniStays.jpg','Diani':'Diani_Beach_PwaniStays.jpg','Shanzu':'Shanzu_Mombasa_PwaniStays.jpg'}[location])
    title='Kenya coast accommodation guides: Nyali, Diani and Shanzu'
    body='<div class="guide-prose"><p class="pw-lead">Choose an area by the kind of stay you need, then compare individual properties. These guides cover layouts, facilities and the questions to ask before booking.</p>'+''.join('<section><h2><a href="/guides/'+g['slug']+'/">'+escape(g['title'])+'</a></h2><p>'+escape(g['summary'])+'</p></section>' for g in guides)+'<p><a href="/stays.html">Browse accommodation across all locations</a></p></div>'
    output['index.html'] = shell(title,'Practical guides to choosing accommodation in Nyali, Diani and Shanzu, with current unit links and questions to ask before booking.','/guides/',body,{'@context':'https://schema.org','@type':'CollectionPage','name':title,'url':SITE+'/guides/'})
    return output


def main():
    snapshot=json.loads((ROOT/'catalogue/properties.json').read_text())
    document=json.loads((ROOT/'content/location-guides.json').read_text())
    output=render_guides(snapshot,document)
    # Preflight every page before replacing any owned output.
    for name in output:
        path=ROOT/'guides'/name
        if any(p.is_symlink() for p in (path,*path.parents)) or (path.exists() and MARKER not in path.read_text()):
            raise ValueError('Refusing to overwrite an unowned guide')
    for name,html in output.items():
        path=ROOT/'guides'/name
        data=(html+'\n').encode()
        if not path.exists() or path.read_bytes()!=data:
            atomic_write(path,data)
    print('Generated 3 reviewed area guides and their index')

if __name__=='__main__':
    main()
