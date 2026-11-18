> **Review branch instructions (17 November 2026):** This upgrade is prepared on
> `pwanistays-website-upgrade` for a pull request to `main`. The deployment and SQL
> steps below describe a future, separately approved release; do not run them as
> part of this pull request. No SQL (including preflight SQL) was executed, and no
> live database export, inquiry, review, or booking was performed. The original
> repository commit and supplied ZIP remain available for rollback/comparison.
> Preserve the existing `CNAME`, `CNAME.txt`, `.nojekyll`, and hosting configuration.
> Review the policy drafts before publishing. See `UPGRADE-REVIEW.md` for validation
> and remaining release checks.

# PwaniStays — upgraded website (GitHub Pages + Supabase)

Property sharing now uses generated `/stays/PROPERTY-UUID/` pages with unit-specific
Open Graph images in the initial HTML. See [PROPERTY-PREVIEWS.md](PROPERTY-PREVIEWS.md)
for generation, refresh scheduling, and the limitations of older query-string links.

## What changed

- Public accommodation cards no longer show nightly pricing. The original `public.properties.price` and `commission_rate` columns are **unchanged** in Supabase.
- Cards open shareable detail URLs such as `https://pwanistays.com/stays/YOUR-PROPERTY-UUID/`.
- New property details show current gallery/description and request check-in, check-out and guest count before generating a WhatsApp quotation inquiry (including nights and a property URL).
- Date selection represents **requested dates**, **not verified live availability**. The system does **not** book instantly or collect payment on the website.
- New owner partnerships, privacy, booking terms and cancellation pages; links in the header/footer and sitemap. The payment/cancellation pages state the standard 50% non-refundable-on-guest-cancellation deposit and 50% check-in balance.
- Clearer claims on the homepage, About and How It Works pages, real coastal hero imagery, safer dynamic HTML rendering for listing/review/bookings table fields, and improved contact form delivery feedback.
- New pages use existing branding. Property tours remain a future enhancement. Existing travel experience package rates are NOT changed, as they are separate from accommodation prices.

## Important before uploading: review the policies

**The policies are drafts, including the 50/50 payment model requested by PwaniStays.** Review and approve `privacy.html`, `terms.html`, and `cancellation.html` before making the ZIP public. In particular, review the proposed 50% deposit upon confirmation (non-refundable for a guest-initiated cancellation regardless of notice period), the remaining 50% due at check-in, the treatment of early departures, supplier-caused cancellations, and the proposed refund processing target. Verify they match owner agreements and financial practices. Consider qualified Kenyan legal review. Never promise a refund or provider guarantee you cannot honour.

## Deployment instructions (read before changing Supabase)

1. **Back up** the existing GitHub repository and export the Supabase database/important bookings information using your normal backup method. Keep a copy of the original ZIP.
2. **Approve the policy drafts.** Review `privacy.html`, `terms.html`, and `cancellation.html`. Do not publish terms that are inconsistent with current host/owner agreements.
3. In Supabase SQL Editor, run **only** `supabase/00_PRECHECK_READ_ONLY.sql` at first. Save the output showing existing RLS policies and grants. Confirm whether other apps, scripts or staff depend on the current permissions. **Do not yet run the change scripts.**
4. Unzip the upgrade and copy **website root contents**, not the containing folder, into your existing GitHub Pages repository (the one publishing `pwanistays.com`). Preserve `CNAME` and `.nojekyll`. Commit and push to the branch configured for GitHub Pages. This deploys the updated public code first; the old listing code may use wildcard property queries and must not remain running when price-column permissions are restricted.
5. Check that the updated site loads and lists properties, opens detail pages, renders photos, and generates correct WhatsApp quotation requests. Check that contact-form notifications actually reach `bookings@pwanistays.com` through Web3Forms. Until the Supabase permission migration is applied, **rates may still be accessible to users querying the old database API directly**, even though the updated UI does not show them.
6. **Review** `supabase/01_PUBLIC_SITE_ACCESS_REVIEW_FIRST.sql` before running it. This script revokes/replaces existing policies on `properties`, `inquiries` and `reviews`. It restricts public property access to safe columns (no price/commission), makes inquiries write-only, and allows only approved reviews to be read. Run only after checking your preflight results, backing up the database, and identifying any other consumers of these tables. **Uploading GitHub files does not execute SQL.**
7. After applying the reviewed public-access migration, run `supabase/03_VERIFY_PERMISSIONS_READ_ONLY.sql`. Verify that anonymous users can still see listings and photos but **cannot** query price, commission, inquiries, private booking information, or unapproved reviews. Submit a test inquiry and review. Resolve any errors before promoting/advertising the updated website.
8. **Admin bookings:** `supabase/02_ADMIN_BOOKINGS_REQUIRES_UID.sql` is an intentionally blocked **optional** security migration. It requires your real Supabase Authentication user UUID (from **Authentication → Users**). It replaces bookings policies and grants access only to listed staff. Review backups and existing staff access first, and test using a separate admin and non-admin account. **Do not run with the placeholder.** The existing `bookings.html` page may stop working if its current permissions aren't compatible. Never share Auth passwords or service-role keys.
9. For the Cloudflare-served domain, allow updated static assets to propagate and refresh the browser cache if the old site still appears. Test desktop and mobile using the checklist below. Keep the earlier repository backup available so website changes can be rolled back separately from database changes.

## Suggested Git workflow (if using Git on your computer)

```bash
# After copying the unpacked site contents into the existing repo root:
git status
git add .
git commit -m "Improve accommodation inquiries and trust pages"
git push origin main
```

## Deployment checklist

- [ ] `https://pwanistays.com/` loads on desktop/mobile and displays actual properties.
- [ ] No accommodation card displays a KES/night rate, and Network requests do not retrieve `price`/`commission_rate` after migration.
- [ ] Clicking **View Details & Enquire** opens `/stays/PROPERTY-UUID/` with the correct title, description and images.
- [ ] Check-in/check-out reject invalid or reversed dates; guests selection and number of nights make it into WhatsApp.
- [ ] WhatsApp quotation uses the expected number +254 738 544 784 and does not suggest availability is confirmed.
- [ ] Existing deep links of the form `/?property=UUID` redirect to the new property page.
- [ ] Footer policy links work: `/privacy.html`, `/terms.html`, `/cancellation.html`.
- [ ] `/partners.html` shows the correct owner collaboration message and WhatsApp/email actions.
- [ ] `/#contact` submits successfully, correctly reports email failures, and you actually receive a test message.
- [ ] Reviews remain moderated and private bookings remain restricted to the intended admin(s).
- [ ] Navigation, page layout and gallery work on both desktop and mobile; check all languages used by your guests.
- [ ] Visit `/sitemap.xml`, `/robots.txt`, and `/404.html`.

## Limitations / next improvements

- **No live access to your Supabase data or RLS policies was provided.** The code and migration were built from the schema and original source, and have not been deployed or tested end-to-end against your live database. Run the preflight and verify access before exposing the changes publicly.
- `bookings` uses a different free-text `unit_name` rather than linking to `properties.id`, so real-time availability cannot be determined reliably without additional inventory/owner synchronization. Do not label the date selector as a live calendar.
- The generated `/stays/PROPERTY-UUID/` pages contain unique preview metadata before JavaScript runs. Page content still reads current Supabase data in the browser. Automated builds refresh metadata hourly; platform preview caching can delay image changes. Older `/property.html?id=...` links remain usable but cannot serve query-specific initial HTML on GitHub Pages. Share the new URLs for property-specific previews.
- Most existing site internationalisation remains in place, but new property/legal pages are initially English. Translate and review legal content with appropriate care before promising all-language coverage.
- Images remain served from the existing `property_images` Supabase storage bucket. Ensure bucket policies permit public reads for intended property photos only.
- Website security headers in `netlify.toml` do not automatically apply to GitHub Pages. Configure compatible security controls through your delivery layer if necessary.
- Direct browser inserts into reviews/inquiries may attract spam. For high-volume traffic, consider CAPTCHA and a validated server/Edge Function endpoint.
- The existing safari/experience package prices remain as-is; evaluate them separately if they change by season.

## File placement

- `index.html` — accommodation listing and inquiry search.
- `property.html`, `property.js`, `listing-utils.js`, `new-pages.css` — dynamic listing detail page and public booking inquiry flow.
- `privacy.html`, `terms.html`, `cancellation.html` — draft legal pages.
- `partners.html` — owner partnerships/management interest.
- `header.html`, `header-loader.js`, `i18n.js`, other HTML files — original site with links/copy adjustments.
- `supabase/` — review-only SQL scripts; these are not run by GitHub Pages.
- `CNAME`, `.nojekyll`, `robots.txt`, `sitemap.xml` — preserve with site root.

**No secrets**: the ZIP includes the publishable Supabase key and the website's existing public Web3Forms access key; it does not include a Supabase service-role key, database password, or authentication credentials.

## Payment and cancellation policy (updated for PwaniStays)

- **Standard:** 50% of quoted accommodation total as a booking deposit, 50% at check-in before property access. Host-specific variants must be agreed in the written quote before payment.
- **Voluntary guest cancellation after confirmed booking:** the 50% deposit is non-refundable regardless of cancellation date. Guest is not ordinarily charged the unpaid 50% if they cancel before check-in. Amounts paid above the deposit are normally refundable under standard terms, subject to agreed charges and the law.
- **No-show / early departure:** no-show forfeits deposit; after check-in, unused booked nights are normally not refunded for guest-driven changes.
- **Unconfirmed / provider-caused failure:** payments are returned if booking cannot be confirmed; remedies, potentially including a full refund, remain available for provider failure, material misdescription or as required by law. **Never tell a guest that all refunds are prohibited under all circumstances.**
- **Copy shown at inquiry:** property.html now advertises the standard payment split so guests can understand terms before reaching out.
- **Legal review:** Kenyan consumer laws apply; have a qualified local professional review the policy before treating the text as finalized legal advice.

## GitHub deployment options

- The GitHub connection in ordinary ChatGPT can help read and review repositories, but **does not itself grant push/PR permission**. To push changes with OpenAI tools use an eligible Codex workflow connected to GitHub, with explicit repo permissions and your approval.
- Alternatively follow this README and commit the extracted website contents into the configured GitHub Pages branch. No private GitHub passwords or tokens are needed here.
- Keep Supabase SQL scripts separate from GitHub deployment: hosting static files does not run database migrations.
