# Reviewed property copy and area guides

The first release adds nine manually written descriptions across Nyali, Diani
and Shanzu, plus three distinct area guides. Copy uses the current public unit
title, type and host-supplied amenity lines. It does not invent verified stays,
ratings, distances, internet speeds, accessibility, prices or availability.

`property-copy.json` stores permanent UUID keys, a concise search summary,
visible description paragraphs and the source facts used to write them. The
hourly exporter applies a description only while its title, location and type
still match and the recorded amenities remain present. Changed facts skip that
copy and print the affected UUID for review; the public fallback description
remains. Withdrawn units do not appear in the active source or guide inventory.

For another unit, collect its public source facts from
`catalogue/properties.json`, then add a reviewed entry in the same format. Keep
summaries between 40 and 180 characters. Write the body around distinguishing
features and the real travel decisions they support. Do not vary adjectives
merely to make two units appear different.

Host information worth collecting next:
- Beds and sleeping arrangement, permitted adults and children.
- Exact guest-approved location and actual beach access, with a map pin.
- Private versus shared pool use, hours and restrictions.
- Floor, lifts, stairs and access needs.
- Kitchen equipment, laundry, housekeeping and additional charges.
- Work surface, recent internet measurement and backup arrangements.

These are review questions, not facts to publish until confirmed. Keep private
rates, contact details and internal captions out of this content file. A future
change in facts requires reviewing the prose before updating its fact snapshot.

`location-guides.json` contains distinct editorial content for the three areas.
`build_location_guides.py` rebuilds their listings and counts from the active
snapshot. Guides are linked from the homepage, complete directory and relevant
unit pages, and included in the main sitemap. New units in those areas appear
on the guide automatically. Other areas should receive a guide only when there
is useful, specific content to publish.

Refresh using the source/routing command documented in `PROPERTY-PREVIEWS.md`,
then run previews, the directory, location guides and sitemap generators. The
hourly workflow already performs all these steps and commits guide changes.

## Experience trip pages

`experience-trips.json` retains the 25 trip options across Coastal & Cultural,
Safari Adventures and Nairobi & Inland. Edit this source to update a trip's
description, categories, timing or proposed arrangements, then run
`python3 scripts/build_experience_pages.py` from the repository root. The three
generated pages share their footer with the accommodation directory through
`scripts/site_chrome.py`. The hourly directory build preserves that footer.

Quotation links include the selected trip's title. Proposed activities and
inclusions still require confirmation for the guest's dates; do not publish
guaranteed sightings, availability or prices without current confirmation.

Trip photographs and hero images are also recorded in `experience-trips.json`,
including their original source, descriptive alt text and any licence link.
New stock photos are served as local WebP files in `images/experiences/`, with
360/720-pixel card variants and larger hero variants. Keep the responsive image
metadata and actual file dimensions in sync when replacing a photo. Recognisable
destinations can be named; thematic stock uses an “inspiration” caption rather
than claiming to show a particular attraction. Card photos load lazily; hero
photos load immediately. The overview reuses these photos to avoid extra assets.

## Search Console measurement

The supplied seven-day screenshot has a Page filter: 3 clicks, 132 impressions,
2.3% CTR and average position 8.1 describe the selected page, not the whole site.
They precede this content release and cannot measure its effect. Average position
is an aggregate of impressions, not a fixed rank for every query.

Remove the Page filter for a site-wide baseline. Save Queries and Pages reports,
then track the guide URLs and edited unit URLs separately. Compare full 28-day
periods when enough data exists; also inspect query relevance and enquiries.
The URL migration can temporarily split reporting between old and new URLs.
Inspect a representative guide after publication, submit the updated main
`sitemap.xml` once, and monitor discovery/indexing without repeated requests.
