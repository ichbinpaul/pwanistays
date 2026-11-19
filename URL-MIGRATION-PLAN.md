# Friendly property URLs and current GSC findings

Prepared 19 November 2026. This is a review plan, not an active URL migration.
Existing public URLs, canonical tags and sitemaps have not been changed by this work.

## Confirmed example

`https://pwanistays.com/stays/3cd03909-1ce9-449d-9efb-71d458a470da/`
is in the property sitemap and belongs to **Cozy Studio Apartment – Bamburi,
Mombasa**. The proposed human-readable URL is:

`https://pwanistays.com/stays/cozy-studio-bamburi/`

That proposed address is not live yet. A readable address improves usability;
it does not by itself make Google index or rank a page.

## Permanent naming policy

- Keep the existing Supabase UUID, photo identity and Meta item identity unchanged.
- Publish `/stays/<name>/` as the public page address, with lowercase ASCII words
  and hyphens. Use the title and location, remove redundant wording, and cap the
  proposed name at 32 characters.
- Store every assignment in a permanent, versioned UUID-to-name registry. Generate
  the name once for a new unit; changing a title must not silently rename a URL.
- Add a short ID suffix only when names collide, expanding it when needed. Never
  change an existing assignment to accommodate a later unit.
- Retain withdrawn assignments. Never reuse one property's old URL for another
  property. Reinstated units retain their original addresses.
- Require an explicit redirect migration for any later deliberate name change.

The current review contains **133 units**, with **nine collision suffixes**.
Four pairs already have exactly identical display titles. Their different cover
photos do not establish duplicate inventory; review their identifying details
instead of deleting or merging records automatically.

## Review artifacts and repeatability

```bash
cd /workspace/pwanistays
python3 scripts/plan_property_urls.py --output-dir /tmp/pwani-friendly-url-review
```

The output directory must be new/empty and outside the published checkout. It
contains `property-slugs.json`, `url-migration.csv` and `summary.json`. The CSV's
301 column is a proposed redirect, not proof of a deployed HTTP response. Its
headers and extra review fields are not Cloudflare's upload format.

When revising an existing review, pass its `property-slugs.json` using `--registry`
and use another empty output directory. That preserves the existing assignments.
After approval, the registry must be promoted into the actual hourly build;
this preparation script does not currently alter that build.

## Deployment sequence

1. Integrate the approved registry into the source exporter, page generator,
   complete directory, share links, enquiry links and strict URL validators.
   Publish real friendly-path HTML containing the correct unit's visible content,
   cover image and embedded UUID. Keep old UUID pages usable during the transition.
2. Set the friendly URL consistently in canonical, OG, structured-data and
   sitemap output, and switch all internal links together. Old aliases should
   point canonically to that same friendly unit while redirects are activated.
3. Verify the new target pages return 200 and work on mobile before enabling
   **real HTTP 301 redirects** in Cloudflare from the old addresses. Preserve
   check-in, check-out, guests and tracking parameters. Unknown IDs must not be
   sent to an unrelated unit or the homepage.
4. Verify actual status/Location headers, correct destination unit, canonical,
   photo preview, dates and enquiry behavior. Check slash/no-slash variants and
   avoid chains or loops. GitHub Pages JavaScript/meta-refresh redirects are not
   equivalent to HTTP 301 responses.
5. Resubmit the updated property sitemap once. Inspect several new canonical
   URLs in GSC. Old URLs becoming "Page with redirect" is an expected migration
   outcome; they do not need to remain indexed independently.

The existing hosting deploys GitHub Pages behind Cloudflare. The owner confirmed
Cloudflare manages DNS/redirects, but proxy/rule configuration and credentials
are not available here. `netlify.toml` does not configure the current host's
redirects. A DNS record must be proxied for Cloudflare rules/Workers to execute;
confirm that in the dashboard without blindly changing DNS or TLS settings.

## Cloudflare options

The prepared `cloudflare/property-redirects.mjs` Worker is the most maintainable
option for UUID paths, `/property.html?id=UUID` and `/?property=UUID`. It reads the
public approved registry at `/catalogue/property-slugs.json`, so future units can
be handled by the hourly registry build without manually adding redirect rows.

The Worker is **disabled by default**. It must not be enabled until the approved
registry and friendly destination pages are published and tested. Only then set
`PROPERTY_URLS_ENABLED=true` and attach the intended proxied-zone routes for
`pwanistays.com/stays/*`, `pwanistays.com/property.html*` and the homepage path.
Known old GET/HEAD links receive a 301; normal/friendly URLs and unknown IDs pass
through. Registry failures also leave the origin route usable. A deployment
must verify Cloudflare route matching and origin behavior in addition to the
offline tests. Existing preferred-host rules must preserve the path and query.

Cloudflare Bulk Redirects are an alternative for a fixed list of old UUID paths.
Official CSV format has **no header** and seven columns in this order:

`SOURCE_URL,TARGET_URL,STATUS_CODE,PRESERVE_QUERY_STRING,INCLUDE_SUBDOMAINS,SUBPATH_MATCHING,PRESERVE_PATH_SUFFIX`

For exact unit paths use `301,TRUE,FALSE,FALSE,FALSE` after the two URLs.
Source URLs cannot contain a query string, so Bulk Redirects alone cannot map
each legacy `?id=` or `?property=` link to its individual unit. Uploading a list
also does not enable it: an applicable Bulk Redirect Rule is required. Prefer
the Worker for the complete query-aware automated flow.

## Interpretation of the supplied GSC screenshots

| Observation | Meaning and next action |
| --- | --- |
| Property sitemap: Success, read 19 Nov, 133 discovered | Google read the sitemap and knows these URLs. This is not the number of indexed units. Keep the successful submission. |
| Main sitemap: Success, read 18 Nov, 11 discovered | The current repository has 12 main URLs including `/stays.html`. Inspect the directory and resubmit the main sitemap once to advertise the update; do not repeatedly resubmit unchanged files. |
| Eight visible indexed examples with older crawl dates | These are a sample of older main pages, not proof that no units are indexed. Inspect exact current unit URLs to establish their actual state. |
| Three alternate pages with proper canonical | `/?location=Malindi`, `Shanzu` and `Vipingo` are filtered homepage variants. Their homepage canonical is intentional. Leave them excluded unless building genuinely separate, useful location landing pages. |
| Robots-blocked `/index.html`, last crawl 15 Nov | This is a homepage alias; `/` is its preferred canonical. Do not force both to index. Verify the current robots response before treating the older report as current. |
| Robots-blocked `/coastal-cultural.html`, last crawl 24 Oct | This important canonical content page needs a GSC **Test live URL**. Current source robots permits crawling, but production/Google fetch has not been verified here. If crawl/fetch/indexing are allowed, request indexing and validate the resolved robots restriction. |
| Crawled – currently not indexed: 0 | No URLs are reported in that category; it does not establish that all 133 have been crawled or indexed. |

In the screenshot's sitemap input, `https://pwanistays.com/` is already displayed;
enter only `sitemap.xml` to resubmit that entry. Keep the verified Domain property
for the overall site view; the cropped screenshot does not show the property
selector, so it does not establish which report scope is selected.

## Highest-priority visibility work

1. GSC live-test `/stays.html`, the exact supplied unit URL and a unit in another
   area. Confirm fetch/indexing are allowed and the declared canonical matches.
   Where already indexed, compare Google's selected canonical. Request indexing
   for representatives after successful tests, not all 133 manually.
2. Resolve the current coastal page crawl status; keep intentional duplicate
   homepage/filter exclusions. Current source `robots.txt` uses `Allow: /` and
   advertises both sitemaps, so there is no confirmed source rule to remove.
3. Complete the single coordinated friendly-URL migration after routing readiness,
   rather than making several unredirected name changes.
4. Improve verified distinguishing details for same-titled units and add genuinely
   useful Nyali/Diani/Shanzu area guides linked to the real inventory. Do not
   generate near-identical location pages just to repeat keywords.
5. Use GSC Performance queries/pages to prioritize content and snippets, and
   measure actual enquiries. Friendly URLs are a usability improvement; unique
   useful content, real links/reviews, mobile performance and business outcomes
   remain important. The original oversized cover noted in `SEO-AUDIT.md` still
   needs a web-sized derivative; original-byte copies are not compression.

Official Cloudflare references:
- <https://developers.cloudflare.com/rules/url-forwarding/bulk-redirects/reference/csv-file-format/>
- <https://developers.cloudflare.com/rules/url-forwarding/bulk-redirects/reference/parameters/>
- <https://developers.cloudflare.com/workers/examples/bulk-redirects/>
- <https://developers.cloudflare.com/workers/configuration/routing/routes/>
