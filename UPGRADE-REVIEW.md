# PwaniStays upgrade review

Prepared 17 November 2026 for `pwanistays-website-upgrade` → `main`.

## Source comparison and scope

The user confirmed `ichbinpaul/pwanistays` after the initially supplied
`itsbeenpaul/PwaniStays` could not be accessed. Compared the repository's only
existing branch, `main` at `7bee134638dd6a2ea570e3ed370c6b9b6b5cdb54`, with
`PwaniStays_GitHub_Ready_Upgrade_v2.zip` before integrating changes. All original
pages and branding assets remain. `CNAME`, `CNAME.txt`, `.nojekyll`, and
`netlify.toml` are byte-for-byte unchanged. No deployment workflow was added.
The repository's production/default branch was not edited.

## Changes

- Accommodation cards show quotation requests instead of nightly prices. All
  public property queries explicitly select display fields and omit `price` and
  `commission_rate`. Internal database pricing and commission data are untouched.
  Existing experience/safari service prices remain.
- Added `property.html?id=UUID` with active-property lookup, gallery thumbnails,
  description, email inquiries, and WhatsApp quotations to +254 738 544 784.
- Check-in, check-out, nights, guest count, property title/location and shareable
  property URL accompany WhatsApp requests. Invalid/past/reversed/same-day dates,
  stays over a year, and guest counts outside 1–16 are rejected. Date choices are
  requests; they do not indicate verified availability or reserve inventory.
- Homepage date and guest selections pass to property links. Legacy
  `/?property=UUID` links redirect to the new detail page. Restored homepage
  `?search=` and `?location=` handling for navigation from other pages.
- Integrated Privacy, Booking Terms, Cancellation, and List Your Property pages;
  retained the 50% confirmation deposit/50% check-in balance, non-refundable
  guest-cancellation deposits and mandatory legal/provider-failure exceptions.
- Added policy/owner navigation and sitemap entries; used explicit `.html`
  navigation for static hosting, and fixed three broken experience footer anchors.
- Retained booking dashboard authentication, calculations, data access and editing
  flow. Added noindex and escaped booking fields rendered into HTML.
- Escaped listing/review/search text; quoted keyword filter values; added safe
  external-link attributes and image fallbacks; shared image filtering with the
  detail page; fixed long-title overflow on mobile.
- Integrated the ZIP's clearer homepage/support copy, local hero images, revised
  translation labels and accurate contact delivery feedback.
- Included the ZIP's four SQL scripts unchanged as review material only. Added a
  prominent README note separating this PR from future deployment/database work.

## Validation performed

- Node syntax checks: all 16 inline/external JavaScript blocks/files passed.
- Static HTML inspection: 345 internal link/asset references, including fragments,
  passed; no missing local targets.
- Headless Chromium against a local static server and simulated Supabase responses:
  active property rendering, literal HTML-like titles (no script execution),
  gallery selection, date prefilling, nights calculation, invalid date/guest
  rejection, correct WhatsApp recipient/payload, invalid/missing/error property
  states, homepage listing/search, legacy property redirects, search/location
  query links, legal/owner pages and dashboard login rendering passed.
- Property layout checked at widths 360, 390, 768 and 1440 pixels; homepage and
  non-admin supporting pages checked at 390 pixels. No horizontal page overflow.
  Desktop/mobile property screenshots inspected with deliberately long text.
- Browser property queries verified to exclude private price/commission columns;
  no live writes and no uncaught page errors in the completed browser run.
- Hosting/domain preservation, unchanged SQL files, basic private-key/secret-pattern
  scan, and `git diff --check` passed. Publishable Supabase/Web3Forms keys remain
  public as in the existing client-side integration.

These are local integration checks, not a live production acceptance test.
Third-party assets were substituted/cached where needed for repeatable tests;
WhatsApp navigation was intercepted and no message was sent.

## Remaining release checks

- **Database permissions remain unchanged.** Hiding accommodation rates in the UI
  and omitting them from website queries does not prevent direct API access if
  current Supabase grants allow it. RLS, storage visibility, private bookings,
  moderation, and price/commission access must be reviewed separately. No SQL,
  database export, migration, or live booking/inquiry/review write was performed.
- Confirm production listing/schema/storage compatibility, staff login and booking
  operations, email delivery to the intended inbox, and third-party availability
  in a separately approved acceptance check. No test email was sent.
- Review policy wording and consistency with host agreements before publication,
  including deposit handling and the stated refund processing target. Policies
  remain drafts for owner/legal review in this PR.
- Property pages render in the browser: shareable URLs work, but unique social
  preview/SEO metadata for each property requires a future build/backend. New
  property/legal pages are initially English; existing translations remain.
- GitHub Pages does not apply `netlify.toml` headers. Any delivery-layer security
  headers and anti-spam controls need a separate reviewed change.

No merge, production deployment, hosting setting change, or live database change
is part of this upgrade.
