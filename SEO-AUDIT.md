# PwaniStays SEO audit and implementation

Assessment: 19 November 2026. This records repository/local checks, not a claim
that Google has indexed the site or that production performance has been measured.

## Changes prepared

- All 132 active unit pages now include visible property titles, locations,
  accommodation type, public bed information, selected amenities and actual cover
  photos in their initial HTML. They no longer depend on JavaScript for the main
  unit content. Browser hydration preserves the booking flow and avoids duplicate
  amenities or structured data.
- `/stays.html` is a crawlable directory of all 132 units, grouped by the actual
  11 locations in the current inventory. Homepage and navigation link to it;
  unit pages link back to it.
- Per-unit canonical URLs, Open Graph metadata, WebPage/BreadcrumbList JSON-LD
  and the directory's CollectionPage/ItemList describe real visible data.
  No prices, ratings, capacity limits or coordinates were invented.
- `property-sitemap.xml` lists the 132 canonical units and 132 owned cover-image
  URLs. `sitemap.xml` lists the 12 main pages including the new directory.
  `robots.txt` advertises both. Admin/template/withdrawn pages remain excluded.
- Four missing Windows tile references in `browserconfig.xml` were replaced
  with existing brand assets.
- Source image HEAD checks found `X-Robots-Tag: none` on all 132 Supabase covers.
  Original-byte, checksum-verified copies are now prepared at immutable
  `/images/property-covers/` URLs for page images, previews and image-sitemap
  entries. Source galleries remain untouched. The actual hosted copies' response
  headers must still be verified after publication.
- The hourly refresh regenerates source, cover copies, directory, unit pages
  and sitemap together. ETag/hash checks reuse unchanged image files.
- A read-only `Check live site health` workflow checks deployed page/asset/cover
  responses, canonicals, indexability, preferred-host redirects and a real 404.
  It retains a JSON report and runs daily, manually, or after the standard Pages
  deployment workflow succeeds.

## Evidence

| Check | Result |
| --- | --- |
| Static link audit | 150 HTML documents; 6,441 references; 4,240 local targets checked; zero broken local references. |
| Template/external scope | Two unrendered template placeholders and nine external hosts explicitly remain unverified by the offline audit. |
| Sitemap source checks | All 144 listed pages have matching canonicals, visible nonempty H1 content and indexable directives in source HTML. |
| Automated checks | 103 Python tests and five Node tests passed, covering extraction/privacy, generation, routing, immutable image caching, link auditing and health-check behavior. |
| Browser checks | Unit content and all 132 directory links work without JavaScript; tested mobile layouts fit. Booking dates/guests and WhatsApp quotation links remain functional. API outages retain useful static content; inactive units hide content and become noindex in the browser. |
| Image checks | 132 source covers returned HEAD 200, were copied and SHA-256 validated; repeat cache refresh succeeded. |

Live website requests from the cloud environment are blocked by its egress proxy.
That is not evidence that visitors or Google receive a production 403. Production
health results must come from the live-check workflow and GSC URL Inspection.
No Search Console sitemap submission, indexing request or account setting was
performed through the assistant; the verified Domain property was confirmed by
the owner.

## Remaining priorities

1. After publication, submit both sitemaps in the existing GSC Domain property,
   inspect representative URLs and check Google's indexing reports. Follow
   [SEO-SEARCH-CONSOLE.md](SEO-SEARCH-CONSOLE.md).
2. Review real mobile Core Web Vitals/PageSpeed data. The 132 original covers
   total about 29.4 MiB, with one approximately 8.6 MiB. Copying images does not
   compress them; web-sized derivatives are a performance priority.
3. One unit has no selected publishable amenity lines and needs source-content
   review: [Elegant 3 Bedroom Airbnb – Nyali](https://pwanistays.com/stays/9c6ce896-bb44-4ad3-bd04-7830860e1c24/).
   Its source description exists, but no amenity section/bullets were selected;
   this is not a claim that the accommodation has no amenities.
4. Add useful original area guides and verified unit distinctions, maintain an
   eligible accurate Google Business Profile and genuine reviews, and use GSC
   query/click data plus enquiry outcomes to prioritize future content.

Google decides which pages to index and rank. Technical readiness and sitemap
submission cannot guarantee inclusion of all 132 units or a traffic increase.
