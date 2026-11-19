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

`experience-photo-sources.json` restores the distinct photographs from the
earlier trip pages. Do not substitute generic forests, city photos or animals
for a named attraction. Every trip must have a different, destination-specific
photograph. Confirm that downloaded photos actually show the intended subject
before publishing. A missing source must be repaired rather than silently
substituted with unrelated stock.

`build_experience_images.py --download` downloads the original photos, retains
Wikimedia authorship/licence metadata, and creates local WebP copies with
lowercase, hyphenated descriptive filenames. Original downloads stay in a
temporary cache outside Git. Only the smaller web assets are committed. It
prepares all sources and checks for duplicate trip-photo hashes before changing
page metadata, so failed downloads cannot replace the pages with a partial set.
Card widths are 360 and 720 pixels; covers use up to 1200 pixels. Smaller source
images are never enlarged. The encoder strips metadata and tries quality levels
76 down to 60, targeting 24 KB for small cards, 75 KB for large cards and 150 KB
for covers. Complex images can exceed those targets to retain usable detail.

Then run `python3 scripts/build_experience_pages.py` to regenerate all three
pages and synchronize the overview's image links. Check all photos visually,
inspect the generated `experience-image-report.json`, and verify local links
before committing the content, generated pages and WebP assets together. Card
photos load lazily; covers load immediately. The published pages use local
files and need no image-source network access. To prepare only the available
local originals while a remote source is blocked, use
`python3 scripts/build_experience_images.py --only-local`; this leaves page
metadata untouched. Pillow is needed only for this manual image-preparation
step, not the ordinary site refresh.

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
