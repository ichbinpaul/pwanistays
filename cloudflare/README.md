# Install property redirects in Cloudflare

This is the remaining dashboard setup for the shorter property URLs. The Worker
is not deployed by a GitHub push. No per-property Cloudflare rules are needed:
the hourly site build maintains the permanent public registry automatically.

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
settings. The code only redirects recognised old GET/HEAD property links;
ordinary pages, friendly paths, unknown units and failed registry requests pass
through to the current website.

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
