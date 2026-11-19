#!/usr/bin/env python3
"""Build the three experience pages from preserved, editable trip content."""
from pathlib import Path
from html import escape as e
from urllib.parse import urlencode
import json
from site_chrome import SITE_FOOTER
from build_whatsapp_catalogue import atomic_write
R=Path(__file__).resolve().parents[1]
MARKER='<!-- PWANISTAYS_EXPERIENCE_TRIPS_V1 -->'
def wa(text):return 'https://wa.me/254738544784?'+urlencode({'text':text})

def render_photo(image, *, hero=False):
 """Reserve image space and defer card downloads until guests approach them."""
 src=e(image['src'],quote=True)
 attributes='loading="eager" fetchpriority="high"' if hero else 'loading="lazy"'
 responsive=''
 if image.get('srcset'):
  responsive=f' srcset="{e(image["srcset"],quote=True)}" sizes="{e(image["sizes"],quote=True)}"'
 caption='<figcaption>'+e(image['caption'])+'</figcaption>' if image.get('caption') else ''
 return f'<figure class="{"exp-hero-photo" if hero else "trip-card-photo"}"><img src="{src}"{responsive} width="{image["width"]}" height="{image["height"]}" {attributes} decoding="async" alt="{e(image["alt"],quote=True)}">{caption}</figure>'
configs=[('coastal-cultural','package','Coastal & Cultural','Sea air, local stories and time to explore.','Explore coastal heritage, marine outings and days by the sea. Start with an idea, then talk to our team about your dates and departure point.','all-packages','/images/Old_Town_Mombasa_2025_PwaniStays.jpg','Old Town, Mombasa'),('safari','safari','Safari Adventures','Make room for the wild.','Compare Kenya safari ideas by route, time and the kind of trip you have in mind. Our team will help you check travel arrangements and a current quotation.','safari-packages',None,None),('nairobi','experience','Nairobi & Inland','A different side of Kenya.','City discoveries, cultural visits and time in nature. Explore Nairobi and inland trip ideas, then ask us what can fit your schedule.','inland-packages',None,None)]

def render_pages(document):
 if document.get('version')!=1:raise ValueError('Unknown experience source version')
 catalog={page['slug']:page for page in document['categories']}
 pages={}
 for slug,prefix,title,headline,intro,anchor,photo,caption in configs:
  items=catalog[slug]['items']
  hero=catalog[slug].get('hero_image')
  if hero:photo=hero['src']
  if not items or len({i['title'] for i in items})!=len(items):raise ValueError('Empty or duplicate trip source')
  footer=SITE_FOOTER
  categories=sorted({c for i in items for c in i['category']})
  general=wa('Hello PwaniStays! I would like help planning '+title+'. Please confirm options, arrangements and a quotation for my dates and group.')
  cards=''
  for k,i in enumerate(items,1):
   details=''.join('<h4>'+e(label)+'</h4><ul>'+''.join('<li>'+e(x)+'</li>' for x in lines)+'</ul>' for label,lines in i['details'] if lines)
   quote=wa('Hello PwaniStays! I would like a quotation for "'+i['title']+'". Please confirm availability, itinerary, inclusions and total charges for my dates and group size.')
   cards+=f'''<article class="trip-card" data-categories="{e(' '.join(i['category']))}">{render_photo(i['image']) if i.get('image') else ''}<span class="exp-eyebrow">{k:02d} / {e(i['location'] or title)}</span><h3>{e(i['title'])}</h3><p>{e(i['description'])}</p><details><summary>Explore the trip details</summary>{('<p class="trip-duration">Timing to discuss: '+e(i['duration'])+'. Confirm timing for your dates.</p>') if i['duration'] else ''}{details}<p class="trip-note">These are proposed trip details. Confirm the final route, access, inclusions, any additional charges and booking terms in your written quotation. Sightings and conditions vary.</p></details><a class="exp-button" href="{e(quote,quote=True)}" target="_blank" rel="noopener noreferrer" aria-label="Request a quotation for {e(i['title'],quote=True)}">Request a quotation <span aria-hidden="true">↗</span></a></article>'''
  if hero:
   visual=render_photo(hero,hero=True)
  elif photo:
   visual=f'<figure class="exp-hero-photo"><img src="{photo}" width="960" height="640" fetchpriority="high" decoding="async" alt="Historic buildings and a street in Mombasa Old Town"><figcaption>{caption}</figcaption></figure>'
  else:
   visual='<aside class="trip-hero-index" aria-label="Trip inspiration"><span class="exp-eyebrow">Find your own route</span><p class="trip-index-heading">'+('Wild landscapes.<br>Your kind of safari.' if slug=='safari' else 'City life.<br>Open spaces.')+'</p><ul>'+''.join('<li>'+e(i['location'] or i['title'])+'</li>' for i in items[:3])+'</ul><p>Choose an idea. We’ll help you work through the details.</p></aside>'
  schema={'@context':'https://schema.org','@type':'CollectionPage','name':title+' | PwaniStays','url':'https://pwanistays.com/'+slug+'.html','mainEntity':{'@type':'ItemList','numberOfItems':len(items),'itemListElement':[{'@type':'ListItem','position':k+1,'name':i['title']} for k,i in enumerate(items)]}}
  sibling=''.join('<a href="/'+s+'.html">'+e(t)+'</a>' for s,_,t,*_ in configs if s!=slug)
  html=f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(title)} | Trip Ideas &amp; Personal Quotes | PwaniStays</title><meta name="description" content="{e(intro,quote=True)}"><meta name="robots" content="index,follow,max-image-preview:large"><meta name="theme-color" content="#0d7a5f"><link rel="canonical" href="https://pwanistays.com/{slug}.html"><link rel="icon" href="/favicon-32x32.png"><meta property="og:type" content="website"><meta property="og:url" content="https://pwanistays.com/{slug}.html"><meta property="og:title" content="{e(title,quote=True)} | PwaniStays"><meta property="og:description" content="{e(intro,quote=True)}"><meta property="og:image" content="https://pwanistays.com{photo or '/logo-mobile.png'}"><meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="{e(title,quote=True)} | PwaniStays"><meta name="twitter:description" content="{e(intro,quote=True)}"><meta name="twitter:image" content="https://pwanistays.com{photo or '/logo-mobile.png'}"><link rel="stylesheet" href="/header.css"><link rel="stylesheet" href="/experiences.css?v=2"><link rel="stylesheet" href="/experience-trips.css?v=2">{('<link rel="preload" as="image" href="'+photo+'" fetchpriority="high">') if photo else ''}<script src="/i18n.js?v=home-1" defer></script><script src="/header-loader.js" defer></script><script src="/experience-trips.js?v=1" defer></script><script type="application/ld+json">{json.dumps(schema,ensure_ascii=False).replace('<',chr(92)+'u003c')}</script></head><body class="experiences-page"><a class="exp-skip" href="#main-content">Skip to content</a><div id="site-header"><header class="exp-fallback-header"><nav class="exp-wrap exp-fallback-nav" aria-label="Main navigation"><a href="/">PwaniStays</a><a href="/experiences.html">All experiences</a></nav></header></div><main id="main-content" class="experiences-main" tabindex="-1"><section class="exp-hero"><div class="exp-wrap exp-hero-grid"><div class="exp-hero-copy"><nav class="exp-breadcrumb" aria-label="Breadcrumb"><a href="/">Home</a> / <a href="/experiences.html">Experiences</a></nav><span class="exp-eyebrow">{e(title)}</span><h1>{e(headline)}</h1><p>{e(intro)}</p><div class="exp-actions"><a class="exp-button" href="#{anchor}">Explore the options <span aria-hidden="true">↓</span></a><a class="exp-text-link" href="{e(general,quote=True)}" target="_blank" rel="noopener noreferrer">Ask our team</a></div></div>{visual}</div></section><section class="exp-section" id="{anchor}"><div class="exp-wrap"><div class="exp-section-heading"><div><span class="exp-eyebrow">Your next adventure</span><h2>Start with what<br>interests you.</h2></div><p>Open the details, shortlist an idea and ask for a quotation. Routes, entry arrangements and current prices are confirmed individually.</p></div><div class="trip-filters" hidden role="group" aria-label="Filter trip ideas"><button type="button" data-filter="all" aria-pressed="true">All experiences</button>{''.join('<button type="button" data-filter="'+c+'" aria-pressed="false">'+e(c.replace('midrange','mid-range').title())+'</button>' for c in categories)}</div><p class="trip-count" role="status" aria-live="polite">{len(items)} trip ideas to explore</p><div class="trip-grid">{cards}</div></div></section><section class="exp-section exp-planning" id="custom-experiences"><div class="exp-wrap trip-planning-grid"><div><span class="exp-eyebrow">A plan that fits</span><h2>Your dates.<br>Your group.<br>A clearer itinerary.</h2></div><div><p>Share your departure point, travel dates, group size and any practical needs. We’ll help you compare the route, transport and activities before confirming a quotation.</p><p>Ask what is included, what may change with weather or access, and how cancellation terms apply. Review the full written arrangements before paying.</p><a class="exp-button trip-light-button" href="{e(general,quote=True)}" target="_blank" rel="noopener noreferrer">Plan my experience</a><a class="exp-text-link exp-light-link" href="/how-it-works.html">How booking works</a></div></div></section><section class="exp-section"><div class="exp-wrap"><span class="exp-eyebrow">Keep exploring</span><h2>There’s more to Kenya.</h2><nav class="trip-related" aria-label="Other experience categories"><a href="/experiences.html">All experiences</a>{sibling}<a href="/stays.html">Find a coastal stay</a></nav></div></section></main>{footer}<script>document.getElementById('currentYear').textContent=new Date().getFullYear();</script></body></html>'''
  if hero and hero.get('srcset'):
   old='<link rel="preload" as="image" href="'+photo+'" fetchpriority="high">'
   preload='<link rel="preload" as="image" href="'+e(photo,quote=True)+'" imagesrcset="'+e(hero['srcset'],quote=True)+'" imagesizes="'+e(hero['sizes'],quote=True)+'" fetchpriority="high">'
   html=html.replace(old,preload)
  html=html.replace('<span aria-hidden="true">↗</span>','<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M6 18 18 6M6 6h12v12"/></svg>')
  pages[slug+'.html']=html.replace('<html lang="en">','<html lang="en">'+MARKER)
 return pages

def main():
 document=json.loads((R/'content/experience-trips.json').read_text())
 pages=render_pages(document)
 for name in pages:
  target=R/name
  if target.is_symlink() or (target.exists() and MARKER not in target.read_text()):raise ValueError('Refusing an unowned experience page')
 for name,html in pages.items():
  target=R/name;data=html.encode()
  if not target.exists() or target.read_bytes()!=data:atomic_write(target,data)
 print('Generated 3 experience pages from preserved trip content')
if __name__=='__main__':main()
