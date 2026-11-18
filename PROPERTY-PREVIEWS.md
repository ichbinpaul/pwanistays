# Property-specific link previews

Shared property links now use `/stays/<property-UUID>/`. These pages are generated
from the site's existing property-detail template and the public catalogue source.
Each HTML response includes that unit's real designated cover photo, title,
description, canonical URL, Open Graph tags and large-image Twitter card before
JavaScript runs. Chat crawlers can read the photo without running the booking app.

The full property page still loads its current gallery, requested dates and
quotation form through `property.js`. Its HTML root embeds `data-property-id` so
the browser knows which unit to load. Photos remain at their existing public
Supabase URLs; no manual photo uploads or copied stock photos are needed. No image
dimensions are invented in preview metadata.

```bash
cd /workspace/pwanistays
python3 scripts/build_whatsapp_catalogue.py
python3 scripts/build_property_previews.py --check
python3 scripts/build_property_previews.py
python3 scripts/build_property_sitemap.py --source catalogue/properties.json
```

The generator uses `catalogue/properties.json` and writes `stays/<UUID>/index.html`.
`--source` and `--output-dir` select alternate locations. `--check` performs source,
template, rendering and ownership checks without writing files or directories.
Unchanged pages keep the same content, with no timestamp-only changes.

The complete active source is validated before any page is updated. Existing
output must consist only of strict UUID directories containing a marker-owned
`index.html`; unowned pages, extra files, symbolic links and unreadable output
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
