# Deploy clean URLs and property redirects in Cloudflare

GitHub Pages continues to serve the existing HTML files. The Cloudflare route
serves their clean URLs and issues permanent redirects for legacy URLs. A GitHub
push does not update the Worker. The hourly site build maintains the property
slug registry.

## Release the clean URLs

1. Update the Worker on the existing `pwanistays.com/*` route using the complete
   `property-redirects.mjs` module. Preserve the current
   `PROPERTY_URLS_ENABLED` setting. Leave `SITE_HTML_REDIRECTS_ENABLED` unset
   until step 3. Clean routes become available immediately, including
   `/stays` for the directory page and `/header` for shared navigation.
2. Verify the clean routes return 200 before publishing the GitHub change.
   Publish the site and verify that the new canonicals and navigation are live.
3. Set `SITE_HTML_REDIRECTS_ENABLED=true` on the Worker. Verify that, for
   example, `/how-it-works.html?utm_source=qa&tag=a&tag=b` returns 301 to
   `/how-it-works?utm_source=qa&tag=a&tag=b`, which returns 200. Also verify
   `/index.html`, `/guides/diani/index.html` and an existing property link.

If you disable `SITE_HTML_REDIRECTS_ENABLED`, keep the Worker deployed so
clean links and any cached permanent redirects still resolve.

## Stage the Worker

1. In Cloudflare, open **Workers & Pages → Create application → Create Worker**.
   Name it `pwanistays-property-redirects`. If the dashboard starts with a sample
   Worker, deploy that sample on its workers.dev address, then open **Edit code**.
2. Replace the sample code with the complete contents of
   [`property-redirects.mjs`](property-redirects.mjs), and deploy the updated code.
3. Under the Worker's **Settings → Variables and Secrets**, add a plain text
   variable named `PROPERTY_URLS_ENABLED` with value `false`. Save/deploy.
4. Under **Settings → Domains & Routes → Add → Route**, select the
   `pwanistays.com` zone and enter `pwanistays.com/*`. Use a **Route**, keeping the
   existing website origin. Verify the site's existing DNS record is proxied
   (orange cloud), since a DNS-only record cannot execute a Worker route.
   If that route is already owned by another Worker, integrate this handler into
   that Worker instead of replacing its route.
5. Open the homepage and the existing UUID unit link. They should keep working
   normally. At this stage the Worker is installed but redirects are disabled.

Dashboard labels can vary slightly. Keep existing DNS destinations and TLS
settings. The Worker passes assets and ordinary directory URLs through to the existing website.

## Activate after the canonical release

The site maintainer first publishes the friendly canonical release described in
[`URL-MIGRATION-PLAN.md`](../URL-MIGRATION-PLAN.md) and verifies its destination
pages. It sets `ready_for_redirects:true` in the public registry as part of that
release. After the live release is confirmed, change the Worker's plain text
`PROPERTY_URLS_ENABLED` variable to `true` and save/deploy it.

Check a representative old link in the browser's Network panel: its response
must be **301**, its `Location` the correct friendly unit URL, and its destination
**200**. Test old UUID paths both with and without a trailing slash, plus
`/property.html?id=UUID` and `/?property=UUID`. Dates, guests and UTM fields must
survive; identity fields are removed. The Worker caches the registry for up to
five minutes, so allow that interval after publication before retrying.

Example target after activation:

`https://pwanistays.com/stays/cozy-studio-bamburi/`

Then resubmit `property-sitemap.xml` once in GSC and inspect a few new friendly
URLs. Old URLs becoming **Page with redirect** is expected. Keep the old routes
and registry entries indefinitely so existing messages and search results work.

To stop Worker redirects, set `PROPERTY_URLS_ENABLED=false`. This does not undo
301s already cached by browsers; both full property pages remain available.
