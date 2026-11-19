# Property-specific link previews

Shared property links now use `/stays/<property-UUID>/`. These pages are generated
from the site's existing property-detail template and the public catalogue source.
Each HTML response includes that unit's real designated cover photo, title,
description, canonical URL, Open Graph tags and large-image Twitter card before
JavaScript runs. Chat crawlers can read the photo without running the booking app.

The HTML body also contains the real unit title, public description, location,
accommodation type, bed count when provided, designated photo with meaningful alt
text, and privacy-safe amenities. Unit content is visible before JavaScript runs,
so crawlers and visitors with JavaScript disabled can read it. A `noscript`
WhatsApp contact link lets visitors request rates without the scripted form.
Accommodation navigation links to the static `/stays.html` directory.

The full property page still refreshes its current gallery, requested dates and
quotation form through `property.js`. Its HTML root embeds `data-property-id` so
the browser knows which unit to load and `data-property-path` so it retains the
page's declared canonical route even if the shared routing bootstrap is stale.
The same form IDs and booking selectors are
preserved. The generated snapshot is refreshed by automation; the browser's live
property lookup remains responsible for detecting a newly inactive unit.
Gallery photos retain their existing public Supabase URLs. When the validated
cover cache is available, the SEO image and initial main photo use an automatic
original-byte copy on the website's own domain. This avoids depending on a
storage response's restrictive image-indexing headers. No manual uploads, stock
photo replacements, image edits or invented dimensions are involved.

Each active page includes one static JSON-LD graph under
`id="property-structured-data"`, containing `WebPage` and `BreadcrumbList` with
its real title, URL and image. The breadcrumb links through `/stays.html`.
Inherited structured data is replaced to avoid duplicate generic property graphs.
Script content is JSON escaped to prevent a property title or amenity from
closing the script tag. No prices, ratings, reviews, availability promises or
coordinates are fabricated. Structured data helps describe the page; it does not
guarantee Google rich results or indexing.

```bash
cd /workspace/pwanistays
python3 scripts/build_whatsapp_catalogue.py --routing-settings catalogue/property-url-settings.json
python3 scripts/cache_property_covers.py
python3 scripts/build_property_previews.py --check
python3 scripts/build_property_previews.py
python3 scripts/build_property_sitemap.py --source catalogue/properties.json --covers catalogue/cover-images.json
```

The generator uses `catalogue/properties.json` and writes `stays/<UUID>/index.html`.
`--source` and `--output-dir` select alternate locations. `--check` performs source,
template, rendering and ownership checks without writing files or directories.
Unchanged pages keep the same content, with no timestamp-only changes.
Public source records can optionally provide `beds` as a nonnegative integer or
null and `amenities` as a list of nonempty text strings. Older records without
these fields use safe empty/fallback content. Raw imported promotional captions,
private rates, guest information and internal booking data are not used.

## Friendly-path staging

When both `catalogue/property-slugs.json` and
`catalogue/property-url-settings.json` exist, the generator loads their immutable
UUID-to-slug assignments and explicit `use_friendly_urls` boolean. Alternate
configuration paths can be supplied with `--registry` and `--settings`. A partial
or invalid configuration fails before page writes; older fixtures/workflows with
neither file retain the UUID-only behavior.

Configured properties receive **two full pages**, one under `/stays/<UUID>/` and
one under `/stays/<assigned-slug>/`. Both contain the same unit identity, public
content, real cover photo, quotation form and structured data. During staging,
`use_friendly_urls` is `false`: both pages declare the existing UUID URL as their
canonical, OG URL and structured-data URL. Merely creating the friendly-path page
does not change the catalogue source's active URLs or create an HTTP redirect.

The source's `slug` must agree with the registry, and its URL must agree with the
explicit routing setting. This prevents accidental canonical changes from stale
configuration. A future explicitly enabled friendly setting can declare the
friendly route as canonical on both pages, while preserving the old UUID page.
That activation requires a separately reviewed rollout with genuine hosting HTTP
301 redirects. This generator neither deploys a Cloudflare Worker nor enables the
friendly-URL setting.

Registry entries remain reserved when properties are withdrawn or renamed.
Withdrawn registered properties receive non-indexable unavailable pages at both
paths; an old slug is never reassigned to a different unit. Output folder names
must be canonical UUIDs or registered slugs, and each marker-owned page must embed
the exact UUID associated with that folder. Unknown paths, mismatched identities
and unowned files are rejected before any existing page is changed.

## Owned-domain cover images

The cover-cache process writes immutable content-hashed images under
`images/property-covers/` and `catalogue/cover-images.json`. The generator loads
that manifest automatically when present, or accepts an explicit `--covers PATH`.
Legacy workflows without a manifest continue using the original source cover.
Once a manifest is supplied, every active property must have a source-matching
entry and an existing regular image file whose byte count and full SHA-256 match
the manifest. Missing/stale mappings, foreign URLs, wrong-property image paths,
incorrect hashes and symbolic paths stop generation before existing pages change.

Only render-time row copies gain `seo_image` and `seo_source`; source gallery URLs
are not rewritten. The main image carries `data-seo-image` and `data-seo-source`
so browser hydration can keep the cached local cover while the live designated
cover is unchanged. Changed gallery revisions get a new content-hashed URL and
new static metadata on refresh. Verify the delivered website image response and
headers after publication; a cache file alone does not guarantee Google Images
indexing or a particular chat preview.

The complete active source is validated before any page is updated. Existing
output must consist only of strict UUID or registered-slug directories containing
a marker-owned `index.html` with the matching embedded property UUID; unowned
pages, extra files, symbolic links and unreadable output
stop the run rather than being overwritten. A previously generated property no
longer present in a valid nonempty source becomes a `noindex,nofollow` unavailable
page without its previous photo. The generator does not delete arbitrary files.
Each file replacement is atomic; a source or ownership failure leaves the prior
pages intact. A filesystem failure midway through a write can leave a partial
refresh, so inspect failed workflow runs before relying on freshness.

The catalogue refresh workflow regenerates source, pages and the matching sitemap
hourly (at minute 15; GitHub scheduling can be delayed). Its optional Meta API
sync retains its separate daily schedule and is not needed for link previews.
New properties and changed cover photos require a successful refresh/publication
before their static preview metadata is available. Use a manual `source_only`
run for an earlier refresh. Until a new page is generated, the site's 404 handler
opens the existing dynamic detail page for a strict valid property URL, preserving
requested dates and guests. This keeps browsing usable but cannot supply a
unit-specific crawler preview until generation has completed.

The refresh workflow regenerates these pages from the public source and the site
deployment publishes them. Generating or committing HTML alone does not prove the
new response is live: verify a `/stays/<UUID>/` URL and its served `og:image` after
publication. WhatsApp and other services choose whether and how to show previews
and can cache old ones. Newly shared `/stays/` URLs provide unit-specific static
metadata; old `property.html?id=...` or `/?property=...` links may retain generic
cached previews. Existing messages are not rewritten. This feature is independent
of native WhatsApp catalogue eligibility and API activation.
