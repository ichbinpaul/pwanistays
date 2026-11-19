# PwaniStays: Google indexing and search growth

The aim is to make every active property discoverable and useful to Google and
visitors. Google decides whether and when to crawl, index and rank a URL. A
successful sitemap submission, `index,follow` tag, or URL Inspection request is
not a promise that all 132 pages will be indexed.

## What can be checked here

The repository supplies a preferred host, `https://pwanistays.com`, and:

- `robots.txt` permits crawling and advertises both sitemap URLs.
- `sitemap.xml` contains the main public pages.
- `property-sitemap.xml` contains the active `/stays/<assigned-slug>/` canonical URLs.
- Its image-sitemap entries also point to validated website-owned cover photos.
- Each generated active property page has its own canonical URL, title,
  description and actual property cover image.
- The refresh workflow regenerates property pages and the matching sitemap
  hourly. Source failures preserve the last successful published files; inspect
  failed Actions runs rather than assuming an old sitemap is fresh.

The audit found that property metadata was present in initial HTML but the main
property heading and details depended on JavaScript. The SEO work addresses this
by rendering the property's public content into generated HTML and supplying a
browsable HTML directory at `/stays.html`. These changes need successful hosting
publication before Google can see them.

Live redirects, production HTTP headers, uptime, mobile field performance, GSC
ownership and actual indexed counts cannot be established from repository files.
The cloud environment's blocked requests to the domain are a network restriction
here, not evidence that customers or Google receive a 403.

### Image-crawling finding

The public Supabase responses for the 132 designated cover photos returned
`X-Robots-Tag: none`. That directive tells crawlers not to index those image URLs;
putting a photo into an otherwise indexable page does not override its own HTTP
indexing directive. This is separate from whether the property page is indexed.

`scripts/cache_property_covers.py` prepares original-byte copies at immutable
website-owned URLs under `/images/property-covers/`, with a validated mapping in
`catalogue/cover-images.json`. It downloads only public same-unit photos from the
configured project, verifies MIME/header/checksum, and leaves unrelated files
untouched. Future runs reuse validated files when the source ETag is unchanged.
Generated preview/body cover references and the directory can use these owned
URLs; the secondary gallery remains served from Supabase. After publication,
check that the actual owned-image response is HTTP 200, has an image content type,
and does not carry `X-Robots-Tag: none/noindex`. The live-health workflow checks
these distinct covers using HEAD requests, without downloading every gallery.

This improves the technical eligibility of the cover URLs for image crawling;
Google still chooses what to index. These copies are **not compressed or resized**.
The current cover set is about 29.4 MiB in total, with the largest original about
8.6 MiB. Proper web-size image variants are a separate performance improvement;
copying them alone does not prove good Core Web Vitals or fast mobile loading.

`Check live site health` in GitHub Actions checks the deployed sitemap pages,
required assets, cover images, preferred-host redirects and a real 404 response.
It runs daily and after a successful standard `pages build and deployment`
workflow, and can also be started manually. Its JSON artifact records actual HTTP
results; a successful code test is separate from a successful live run. If hosting
uses a differently named deployment workflow, use the manual/daily check or
update the deployment trigger. External social/profile destinations remain
outside the automated site check.

## Finish Google Search Console setup

The owner has confirmed that the **Domain property `pwanistays.com` is verified**.
There is no need to repeat DNS verification, add more URL versions, or create
properties for individual units. The remaining setup starts with sitemap
submission and checking Google's reports.

1. Open [Google Search Console](https://search.google.com/search-console/) and
   select the existing **Domain property `pwanistays.com`** at the top left.
2. Retain the DNS ownership verification record. A Domain property includes HTTP,
   HTTPS, www, other subdomains and all URL paths. No additional verification is
   needed for these 132 unit pages.
3. Existing verified URL-prefix properties can remain for focused reporting.
   They do not create extra indexing requests or extra reach; use the Domain
   property for the complete site overview and the sitemap submissions below.
4. Ensure the production site consistently redirects alternate host/protocol
   versions to `https://pwanistays.com/`, preserving paths and query parameters.
   Verify this on the live host. A canonical tag is a signal; it does not perform
   an HTTP redirect. `netlify.toml` rules do not configure GitHub Pages or
   Cloudflare automatically.
5. Under **Sitemaps → Add a new sitemap**, submit:
   - `https://pwanistays.com/sitemap.xml`
   - `https://pwanistays.com/property-sitemap.xml`
6. Check that each submission reaches **Success**, its last-read date is recent,
   and the discovered URL count is plausible. The property sitemap should match
   the current active property count, which can change from the initial 132.
   Discovered URLs are not the same as indexed URLs.
7. Use **URL Inspection** for the homepage, `/stays.html`, and two or three
   representative active unit URLs copied from `property-sitemap.xml`.
   Choose **Test live URL**, confirm Google can fetch the page, then inspect the
   tested HTML and screenshot. Check the unit heading/details, cover photo,
   intended canonical, mobile rendering, and absence of `noindex` or fetch errors.
8. Where a page is eligible and the live test passes, select **Request indexing**
   for those representative URLs. Submitting the property sitemap is the bulk
   discovery mechanism; do not manually request every unit or repeatedly submit
   unchanged pages. Request indexing is quota limited and does not guarantee
   inclusion.
9. Check **Security & Manual Actions → Security issues / Manual actions** for
   account-specific issues. Turn on Search Console email notifications and retain
   ownership verification.

Do not use Google's Indexing API for these ordinary accommodation pages. That
API is intended for supported job-posting and livestream content, not general
property listings. There is no supported command that forces Google to index
every page immediately.

The single most useful setup screenshot is the **GSC Sitemaps page with the
property selector visible**. It shows the selected property, submitted sitemap
URLs and current results. Share no passwords, DNS account access or API tokens.

## Read indexing results correctly

Open **Indexing → Pages** and filter by the property sitemap where available.
Inspect example URLs in a category before changing site-wide settings.

| GSC result | Appropriate response |
| --- | --- |
| Indexed | Check the selected canonical and performance over time. Indexing alone does not establish rankings or enquiries. |
| Discovered – currently not indexed | Confirm internal links, sitemap freshness and useful distinct property content. Google may not have crawled it yet. |
| Crawled – currently not indexed | Inspect the rendered page, duplication, missing details and content usefulness. Improve the page before requesting another crawl. |
| Duplicate / Google chose a different canonical | Compare Google's selected canonical with the declared URL; align internal links, sitemaps and redirects. Do not create more alternate URL versions. |
| Excluded by noindex | Verify whether intentional. Admin/template/withdrawn-property pages should remain excluded; active public units should not. |
| Not found / soft 404 | Fix real broken URLs. Keep withdrawn units out of the active sitemap and provide a clear unavailable page; a generic loading or error page should not masquerade as a useful active listing. |
| Server error / blocked / redirect error | Diagnose the live hosting response and Google fetch. Local file checks cannot prove the production response is healthy. |

Do not remove intentional `noindex` tags from bookings/admin pages, templates or
withdrawn listings just to increase a count. Check the most recent crawl date
before treating an old report as evidence that a new fix failed.

## Improve reach with useful accommodation information

1. **Complete each listing with verified distinctions.** Include its real area,
   accommodation type, bed/guest capacity where confirmed, actual amenities,
   photos, and booking process. Describe what makes that unit different. Avoid
   mass-producing near-identical keyword paragraphs, unsupported proximity
   claims, invented facilities or unverified availability/prices.
2. **Build location pages people can use.** Prioritize areas with genuine
   inventory and search demand, such as Nyali, Bamburi, Shanzu, Diani or Watamu
   when current records support them. Include actual local guidance, transport,
   suitability, and links to relevant properties. Do not publish empty location
   pages or many interchangeable pages solely to target keyword variations.
3. **Use crawlable links.** Keep the homepage and navigation connected to the
   complete HTML accommodation directory. Link unit pages back to the directory
   and relevant useful guides. A search box or button whose results appear only
   after interaction is not a replacement for ordinary HTML links.
4. **Keep trust information accurate.** Maintain business identity, contact
   details, booking terms, cancellation information and authentic reviews.
   Structured data must describe real visible content; never fabricate ratings,
   prices, availability, addresses or location coordinates for rich results.
5. **Use legitimate local visibility.** Maintain a Google Business Profile only
   if the actual business meets Google's eligibility rules. Use accurate contact
   details and permitted service areas. Do not create a profile or fictitious
   address for every rental unit. Seek genuine relevant local partnerships and
   mentions rather than buying bulk links or paying for ranking guarantees.
6. **Optimize the mobile experience.** Keep original large images out of the
   initial critical path where possible, give images a stable layout, lazy-load
   secondary gallery photos, and avoid loading unnecessary third-party scripts.
   Verify the quotation and WhatsApp flows on a phone after changes.

## Monitor site health and outcomes

| Frequency | Check |
| --- | --- |
| After a deployment or new unit | Successful refresh/publication, real page HTTP response, correct unit details/photo, links, and quotation flow. |
| Weekly | Failed GitHub Actions, broken-link audit, GSC sitemap errors, Page indexing changes, Security issues and Manual actions. |
| Weekly | GSC **Performance → Search results**: clicks, impressions, click-through rate and queries/pages. Compare meaningful periods and segment mobile, location and query intent. Average position is contextual, not a fixed site-wide rank. |
| Monthly | Pages with impressions but poor CTR, useful queries lacking relevant content, enquiry conversion and genuine business outcomes. Improve content and snippets where evidence supports it. |
| After layout or image changes | PageSpeed Insights/mobile lab checks and GSC Core Web Vitals. A small site may have insufficient field data; a lab score alone does not prove real-user performance. |

If analytics is added, count intended events such as a quotation request click or
a WhatsApp outbound click. A click is not proof a message was sent, a reservation
was confirmed or revenue was earned. Do not include guest names, telephone
numbers, email addresses, chat text, travel dates or URL query strings in analytics
event payloads. Use any consent and disclosure required for the chosen analytics
configuration. Analytics installation is separate from Search Console verification.

There is no reliable fixed indexing date or traffic guarantee. Confirm technical
readiness first, then use GSC crawl/indexing results and enquiry data to decide
what to improve next.

## Google reference documentation

- [Add a Search Console property](https://support.google.com/webmasters/answer/34592)
- [Build and submit a sitemap](https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap)
- [Ask Google to recrawl URLs](https://developers.google.com/search/docs/crawling-indexing/ask-google-to-recrawl)
- [URL Inspection](https://support.google.com/webmasters/answer/9012289)
- [Page indexing report](https://support.google.com/webmasters/answer/7440203)
- [Google Search essentials](https://developers.google.com/search/docs/essentials)
