# Automated catalogue source

This prepares public property data and existing photo URLs, plus an optional
Meta Hotels API adapter. No photos need to be uploaded again. The source JSON is
**not a Meta CSV import feed, and no live WhatsApp connection has been activated**.
Accommodation eligibility and support for connecting a Hotels and rentals
catalogue to WhatsApp are assumed for development and remain unverified.

## What is implemented

`scripts/build_whatsapp_catalogue.py` reads active public properties using the
same publishable Supabase configuration as the website. It resolves existing
public galleries, including the website's `_pwani_v6_...` gallery revisions, and
writes:

- `catalogue/properties.json`: versioned public property records and a UTC
  `generated_at` timestamp.
- `catalogue/status.json`: export status, counts, and pending integration work.
  The status is `source_export_only`, not a claim that Meta accepted an import.

Each property contains `id`, `title`, `location`, `unit_type`, public `beds`,
selected `amenities`, `url`, `description`, and `images`. Legacy caption prose,
rate/contact lines and internal price/commission columns are excluded from the
published source. IDs remain stable across refreshes. The property URL
opens its existing website details and gallery. The image list contains at most
ten HTTPS URLs: the designated cover first, then the numbered gallery order with
duplicates removed. This is deterministic selection, not AI analysis of room
coverage, sharpness, or photographic quality. A property with fewer than ten
photos uses the available photos; it does not receive unrelated filler images.

The source deliberately excludes internal rates, commissions, booking records,
guest information, and raw legacy promotional captions. It does not invent free
or placeholder prices, precise addresses, coordinates, star ratings, or live
availability. Active listings are not a guarantee of availability on requested
dates. Descriptions direct customers to request current rates and availability.

## Run and verify

Use the existing checkout; no new Git worktree or package installation is needed.
Python 3.12 and its standard library are sufficient.

```bash
cd /workspace/pwanistays
python3 -m unittest discover -s tests -v
python3 scripts/build_whatsapp_catalogue.py --check
python3 scripts/build_whatsapp_catalogue.py
```

`--check` fetches and validates the source without writing output files. A normal
run refreshes the generated files. Unchanged property content retains the prior
timestamp so the schedule does not create timestamp-only commits. A failed
refresh must return nonzero and retain the last successful files; do not publish
an incomplete response as a replacement catalogue. Check command output and the
workflow result rather than treating an existing file as proof of a fresh run.

No Meta token, Supabase service-role key, ad account, or database write access is
needed for this export. The publishable source configuration already exists in
`listing-utils.js`. Do not add private credentials to generated files or Git.

## Scheduled refresh

`.github/workflows/refresh-whatsapp-catalogue.yml` refreshes source and property
preview pages hourly at minute 15 and supports **Run workflow** in GitHub Actions. The
workflow runs the catalogue tests before generating output, then commits only
catalogue JSON files, validated website-owned covers, generated property preview
pages, the HTML directory, and their matching sitemap
to `main` when their content changes. It uses a
normal push and fails on conflicting branch updates; it never force-pushes or
overwrites unrelated work. Inspect failed Actions runs before retrying.

The schedule starts only after this workflow is present on the repository's
default branch and GitHub Actions is enabled. Repository contents and Pages write
permissions for the workflow's `GITHUB_TOKEN` are required. The existing sitemap workflow is
independent and unchanged.

Committing source files is distinct from publishing them on the website. In
particular, commits made with `GITHUB_TOKEN` do not themselves guarantee a
GitHub Pages build. After checking for source changes, the workflow reads the site's
Pages build type and explicitly requests a build for branch-based (`legacy`)
Pages hosting when the current commit has no successful Pages build. That request queues publication; it does not establish that the
build completed successfully. Check the Pages build result and verify the actual
served JSON content and freshness before relying on the hosted export.

For workflow-based Pages deployment, unknown deployment types, or API access
failures, the job fails with publication unresolved rather than claiming a
hosted refresh. A workflow-based site needs a separately configured explicit
Pages deployment workflow that publishes the refreshed source. If publication
fails after the source commit succeeded, rerun the source workflow for branch-based
Pages: it also checks publication when source content is unchanged. For workflow-based
hosting, trigger the appropriate deployment explicitly.
Neither publishing these JSON files nor completing this workflow imports them
into Meta unless the separately gated API-sync step is enabled and succeeds.

## Optional Meta Hotels API adapter

`scripts/sync_meta_hotels.py` maps the public snapshot to Meta's hotel API.
Its default mode is entirely offline: it validates source data and prints counts,
missing-address counts, and the unvalidated-compatibility warning without reading
credentials or contacting Meta. To inspect complete payloads, save an optional
plan **outside the website checkout**, because it may contain approved addresses:

```bash
python3 scripts/sync_meta_hotels.py --source catalogue/properties.json
python3 scripts/sync_meta_hotels.py --source catalogue/properties.json --plan /tmp/pwanistays-hotel-plan.json
```

Hotel identities use the stable namespace `pwanistays:<property-UUID>`. Payloads
contain the name, public description, brand, canonical website URL, and up to ten
`images` objects with `image_url` values. No image files are uploaded. The adapter
uses `GET/POST /<catalogue-ID>/hotels` to list/create hotels and `POST /<hotel-Graph-ID>`
to update existing items. It does not confuse our UUID with Meta's returned Graph
node ID. These endpoints and nested image keys follow Meta's
[official Python SDK](https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/productcatalog.py)
and its
[hotel creation example](https://github.com/facebook/facebook-python-business-sdk/blob/main/examples/ProductCatalogHotelsPost.py).
Those sources establish request structure, not accommodation eligibility or
which address fields Meta will require for this account.

For representative validation, `--only PROPERTY_UUID` limits the plan to an
existing source property; repeat it to select multiple properties. The complete
source is still validated first. After secure activation configuration is in
place, validate one real property before bulk application:

```bash
python3 scripts/sync_meta_hotels.py --apply --only YOUR_PROPERTY_UUID
```

Replace `YOUR_PROPERTY_UUID` with the actual UUID from the source. This command
performs a real upsert only when explicitly run with credentials; it was not
executed during implementation. The target must already be linked unless the
separate `--connect` option is supplied. `--prune` is prohibited with any `--only`
selection, so a representative test cannot remove the remaining catalogue.

The source does not provide exact hotel addresses. By default `address` is
omitted, and the plan counts items lacking approved address metadata. Optional
`--details /secure/path/hotel-details.json` accepts an object keyed by property
UUID, each containing only an `address` object with approved `street_address`,
`city`, `region`, `country`, `postal_code`, `neighborhoods`, and/or paired
`latitude`/`longitude` fields. Do not use approximate or invented coordinates.
Actual address requirements and API acceptance still need destination validation.
Keep details files and complete plans outside the website checkout.

### Explicit activation configuration

`--apply` is required for any Meta request. Supply these through a secure runtime
configuration; do not paste credentials in chat or put them in Git:

- `META_ACCESS_TOKEN`: a token authorized to manage the target catalogue and
  WhatsApp Business account.
- `META_CATALOGUE_ID`: the target **Hotels** catalogue ID; the app-created catalogue
  is not assumed to have this type or support these APIs.
- `META_WHATSAPP_BUSINESS_ACCOUNT_ID`: the actual Meta WhatsApp Business account
  ID, not the telephone number, Facebook profile ID, or ad account ID.
- `META_GRAPH_VERSION`: an explicit supported version such as `v26.0`.

The adapter first checks the target's ID and `hotels` vertical, reads the
WhatsApp account's linked catalogues, and lists existing hotel identities. It
refuses incomplete pagination, duplicate identities, an empty source, invalid
images, and unsupported targets before hotel writes. Tokens use a bearer header;
redirects are disabled, pagination follows validated cursors on Meta's own host,
and errors omit raw response bodies, request headers, and credentials. Failed
requests report the operation/object ID, HTTP status, and selected Meta error
code, subcode, type and message with token/URL redaction. This distinguishes
missing permissions, invalid identifiers, and hotel schema rejections without
requiring another token or exposing the credential.

`--apply` alone requires the intended catalogue to be linked already. Optional
`--apply --connect` can link it through `POST /<WhatsApp-account-ID>/product_catalogs`
only if there is no different linked catalogue, and re-reads the connection before
writing hotels. It will not replace an existing connection or delete the current
app-managed catalogue. A successful link is still distinct from observing the
resulting items in the WhatsApp app.

No items are deleted by default. Optional `--apply --prune` deletes only valid
`pwanistays:<UUID>` hotel identities absent from the active source, after every
create/update succeeds. Unrelated items remain untouched. Any upsert failure
stops the run before pruning; earlier successful writes may remain. A retry
re-lists the destination and updates the same identities rather than creating
new IDs. This is an upsert identity guarantee, not an all-or-nothing Meta transaction.

### Scheduled API activation

The hourly workflow always validates the payload plan offline. Scheduled live API
sync is disabled unless the repository variable `META_CATALOGUE_SYNC_ENABLED`
is exactly `true`, and still runs only at 04:15 UTC (07:15 East Africa Time).
Manual runs default to `source_only`, even if the schedule is
enabled. Select `test_one_property` to upsert just the first active property,
or `sync` to explicitly apply the full snapshot. Single-property tests never prune.

The workflow is prefilled with the supplied target identifiers:

- New hotel catalogue: `1686254389800444`.
- Business portfolio: `588596394915147` (context only, not an API credential).
- WhatsApp asset/account candidate: `470793059453050`, from the manager URL;
  the API preflight must still verify that it is an accessible WhatsApp account.
- Explicit Graph version: `v26.0`.

The `META_CATALOGUE_ID`, `META_WHATSAPP_BUSINESS_ACCOUNT_ID`, and
`META_GRAPH_VERSION` Actions variables can override these defaults. Local CLI
runs still need the environment variables listed above.

Configure `META_ACCESS_TOKEN` as a repository Actions secret. In Meta Business
Settings for the intended portfolio, use **Users → System users** to assign a
system user the intended catalogue, WhatsApp account, and business-owned developer
app. Generate a token for that app with the applicable `catalog_management` and
`whatsapp_business_management` permissions. If no app is available, a suitable
business-owned Meta developer app must first be created/associated; Business Suite
access alone does not supply API authorization. Enter the token directly at
GitHub **Settings → Secrets and variables → Actions → New repository secret**,
named `META_ACCESS_TOKEN`. Do not put it in chat, source files, or URLs.

After adding the secret, open the **Refresh WhatsApp catalogue source** workflow,
choose **Run workflow → operation: test_one_property**, and request the connection
checkbox only if this is the intended new catalogue. The adapter refuses to replace
a different existing link. Only after one property is accepted and visible should
you run the `sync` operation and enable the daily variable. Token permissions,
business/app access, and account-specific required hotel address fields still need
real API validation; prefilled IDs do not establish a successful connection.

If approved hotel address data is needed, put its JSON in the
`META_HOTEL_DETAILS_JSON` Actions secret; the workflow writes it to a restricted
temporary file and passes `--details`.

`META_CATALOGUE_CONNECT_ENABLED=true` (or the manual connection checkbox) adds the explicit connection option.
`META_CATALOGUE_PRUNE_ENABLED=true` enables managed-item removal. Both are off by
default. Enable these only for the intended target and after validating a
representative import. No Meta credentials or activation variables were supplied
or enabled during implementation, and no live API sync or account linking was
executed. The exported `source_export_only` status is deliberately not rewritten
as a live Meta connection claim by a hypothetical plan.

## Remaining activation work

1. Confirm the accepted Meta catalogue type and its WhatsApp compatibility. The
   current app-created catalogue can only be managed in WhatsApp; this script
   does not modify, delete, or replace it.
2. Validate the Hotels API payload and account-specific required fields using
   the adapter; do not upload the neutral JSON as though it were a Meta CSV.
   A retail product schema requiring public prices cannot be completed
   from confidential accommodation rates or fabricated `0 KES` values. If a hotel
   schema requires exact location metadata, obtain approved property data rather
   than guessing coordinates or street addresses.
3. Validate a representative item in the destination before activating a full
   import. Confirm gallery limits, accepted image URLs, property links, handling
   of inactive/removed listings, and any required public price information.
4. Securely configure the API connection and enable its scheduled step only after
   validation. Use the platform's secure secret store, never source code, URLs,
   or chat, for credentials.
5. Link the accepted catalogue to the intended WhatsApp Business account using
   Meta's supported flow. Verify that actual items and links appear correctly on
   the business number before considering retirement of the original catalogue.

An ad account is not needed for this integration. No existing catalogue needs to
be deleted to build or test this preparation. No automatic messages, bookings,
payments, or WhatsApp account migration are implemented. Meta writes occur only
through the explicitly enabled adapter; offline validation performs none.
