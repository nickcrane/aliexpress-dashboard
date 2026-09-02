# AliExpress Product Research Dashboard

A local tool for evaluating AliExpress products to stock in a dropshipping sales
channel: a **collector** that runs a set of saved searches against the AliExpress
Open Platform's Drop Shipping API (`aliexpress.ds.*`) and writes results to
SQLite, and a **Streamlit dashboard** for filtering, ranking, and shortlisting
what it finds.

The point of storing history (the `observations` table) rather than just the
latest snapshot is the momentum view: seeing that a product's sales volume moved
40% in the last two weeks is far more useful than its absolute number, and it's
the thing no off-the-shelf AliExpress tool gives you.

## A note on which API this uses

This started out built against `aliexpress.affiliate.*` (via the
`python-aliexpress-api` library), the obvious choice from the outside. Once a
real AliExpress Open Platform app existed, its granted permission groups
turned out to be **"Drop Shipping" and "System Tool" only — no affiliate
access at all**. So this is built against `aliexpress.ds.*` instead, which
`python-aliexpress-api` has no SDK support for; the request classes in
`aliexpress_dashboard/client/ali_client.py` are hand-built, reusing the same
signing/gateway mechanics the library uses for its own affiliate classes,
against endpoints the library never implemented. If your own AliExpress
account has different permissions, check what your app's permission page
actually lists before assuming this codebase applies as-is.

## Before you start: what this tool can, and can't, tell you

Unlike the affiliate API, `aliexpress.ds.product.get` (the per-product detail
lookup) *does* return a real review count (`evaluation_count`) and a 1-5 star
average (`avg_evaluation_rating`) — genuinely new information, not available
anywhere in the affiliate API this project first assumed it'd use. Confirmed
against a live account. The catch: those two fields only exist on that
per-product detail call, not in bulk search results, so getting them for a
product costs one extra API call. The collector doesn't make that call
automatically for every search result (see
[Known gaps and modeling choices](#known-gaps-and-modeling-choices)), so in
practice review count and star rating stay blank for most collected products
unless you look a specific one up.

`evaluate_rate` (a positive-feedback %, present on search results) and
`sales_volume` (the API's own `orders`/`sales_count` field, which can be a
bucketed string like `"1000+"` rather than an exact number) are the two
figures you'll actually see for everything you collect. Rankings and the
composite score are built entirely from what the API actually returns —
nothing here is a fabricated substitute for missing data.

**A methodology note.** Everything in this README was originally written from
the AliExpress Open Platform's own documentation, before this project had
real credentials to test against. Once a live account was available, several
of those documented assumptions turned out to be wrong — a different field
casing, an undocumented extra layer of response nesting, a locale parameter
that needed a different format than the docs' own example, a "success" code
that wasn't the code the docs implied. Those are all fixed and confirmed now
(see the gaps section), but it's worth knowing the pattern: this API's
documentation and its actual behavior disagree often enough that "the docs
say X" was never treated as good enough on its own here — everything load-bearing
went through a live call before being trusted.

## Requirements

- Python 3.11+
- An AliExpress Open Platform app with the **Drop Shipping** and **System
  Tool** permission groups, for live mode (see [Getting API credentials](#getting-api-credentials)).
  You do **not** need this to try the tool — everything works against recorded
  fixtures with zero credentials.

## Quick start (fixture mode, no credentials needed)

```bash
git clone <this-repo>
cd aliexpress-dashboard
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

`.env`'s defaults are already fixture mode. Define a couple of searches and run
the collector:

```bash
python -m aliexpress_dashboard.collector.cli add-search --name home-gadgets-under-15-gbp
python -m aliexpress_dashboard.collector.cli add-search --name trending-kitchen
python -m aliexpress_dashboard.collector.cli run
```

Then launch the dashboard:

```bash
streamlit run run_dashboard.py
```

That's the whole loop. Everything — collector, storage, dashboard — runs
end-to-end against the bundled fixtures in `tests/fixtures/`, which cover a
handful of realistic products and some deliberate edge cases (a missing
rating, a zero-volume product, a bucketed sales count like `"1000+"`, an
empty result set, a multi-page search).

## Project structure

```
aliexpress_dashboard/
  config.py              Settings: reads .env, validates AE_MODE + credentials
  client/                 AliClient: talks to the API (or fixtures), normalizes responses
    ali_client.py           Hand-built aliexpress.ds.* request classes + calls
    auth.py, tokens.py      OAuth authorize URL + local access/refresh token storage
    normalize.py             Defensive field parsing, incl. bucketed sales counts
  collector/               CLI + the SQLite write path (searches, runs, products, observations)
  dashboard/               Streamlit app: filters, momentum, scoring, shortlists
  db/                       Connection helper + migrations (plain SQL, no ORM)
run_dashboard.py            Launcher -- run this with `streamlit run`, not app.py directly
tests/fixtures/              Recorded API responses used in AE_MODE=fixture
data/                         SQLite database + cached OAuth token live here (gitignored)
```

## Configuration

All configuration is environment variables, loaded from `.env` (see
`.env.example` for the full list with defaults):

| Variable | Purpose |
|---|---|
| `AE_MODE` | `fixture` (default, no credentials needed) or `live` |
| `AE_APP_KEY`, `AE_APP_SECRET` | Required when `AE_MODE=live` |
| `AE_CALLBACK_URL` | Where the one-time OAuth authorize step redirects to. Must be HTTPS. Defaults to `https://example.com/callback` — see [Getting API credentials](#getting-api-credentials) |
| `AE_TARGET_CURRENCY`, `AE_TARGET_LANGUAGE` | Defaults `GBP` / `en` — currency/language every `ds.*` call is made with |
| `AE_SHIP_TO_COUNTRY` | Default destination country for `ds.text.search`'s required `countryCode` param; a saved search can override it |
| `AE_DB_PATH` | Defaults to `./data/aliexpress_dashboard.db` |
| `AE_TOKEN_PATH` | Defaults to `./data/token.json` — where the OAuth access/refresh token is cached after authorizing. Written programmatically, not hand-edited |
| `AE_FIXTURES_DIR` | Defaults to `./tests/fixtures`; only used in fixture mode |
| `AE_MIN_REQUEST_INTERVAL_SECONDS`, `AE_MAX_RETRIES`, `AE_BACKOFF_BASE_SECONDS`, `AE_BACKOFF_MAX_SECONDS` | Rate limiting / exponential backoff, live mode only |

Never commit `.env` — it's gitignored. Only `.env.example` (with blank
credential fields) is tracked. `data/token.json` is also gitignored.

## Getting API credentials

1. Apply for AliExpress Open Platform developer access and create a **Drop
   Shipping**-category app for your own store (not the commercial/ISV
   category — that's for building software you sell to other sellers).
2. Get your `app_key` and `app_secret` from the app's overview page.
3. On the app's permissions page, apply for both the **Drop Shipping** and
   **System Tool** permission groups (the latter is what the OAuth token
   endpoints live under). Check what's actually listed there for your
   account — if it differs from this, the client in this repo won't
   necessarily apply as-is (see [A note on which API this uses](#a-note-on-which-api-this-uses)).
4. The app creation form asks for a callback URL, which must be HTTPS. This
   tool has no public server, so use a neutral real domain you don't need to
   run anything on:
   ```
   AE_CALLBACK_URL=https://example.com/callback
   ```
   AliExpress's OAuth flow puts an authorization `code` in the browser's
   address bar after you approve — it's readable there whether or not the
   destination page itself loads.
5. Put your key/secret in `.env` and switch to live mode:
   ```
   AE_APP_KEY=your-app-key
   AE_APP_SECRET=your-app-secret
   AE_MODE=live
   ```
6. Run the one-time authorize step:
   ```bash
   python -m aliexpress_dashboard.collector.cli authorize
   ```
   Open the printed URL, log in, click Authorize, copy the `code` from your
   browser's address bar, then:
   ```bash
   python -m aliexpress_dashboard.collector.cli authorize --code <code>
   ```
   AliExpress's own docs claim a self-developed app's access token is valid
   ~365 days (refresh ~730) — **confirmed live that this is wrong, or at
   least doesn't apply the way the docs suggest**: the actual access token
   lasts **24 hours**, refresh token **48 hours**. Refresh before that window
   closes:
   ```bash
   python -m aliexpress_dashboard.collector.cli refresh-token
   ```
   This needs to run roughly daily to keep live mode working — put it on the
   same schedule as the collector (see [Scheduling](#scheduling)), before the
   collection run, rather than treating authorization as a one-time setup step.

No further code changes are needed to go from fixture to live — the collector
and dashboard run the exact same code either way; only where the data comes
from changes.

## Running the collector

```bash
# Define a search
python -m aliexpress_dashboard.collector.cli add-search \
    --name budget-electronics \
    --keywords "wireless charger" \
    --min-price 5 --max-price 20 --currency GBP \
    --sort orders,desc \
    --ship-to GB

# See what's defined
python -m aliexpress_dashboard.collector.cli list-searches

# Run every active search
python -m aliexpress_dashboard.collector.cli run

# Run just one (active or not -- useful for testing a search you just added)
python -m aliexpress_dashboard.collector.cli run --search budget-electronics
```

`--sort` accepts one of `min_price,asc` `min_price,desc` `orders,asc`
`orders,desc` `comments,asc` `comments,desc` (the API's fixed set — there's no
dedicated "trending" endpoint in this family, `orders,desc` is the closest
equivalent). `add-search` upserts by name — running it again with the same
`--name` updates that search in place rather than creating a duplicate. Pass
`--inactive` to save a search without including it in a plain `run`.

Each `run` invocation is one row in the `runs` table (start/finish time,
searches executed, records written, any errors) and writes one `observations`
row per product per search, upserted so re-running never creates duplicates
within that run. Running the whole collector again later is expected to add a
fresh, legitimate observation per product — that's the history the momentum
view is built from, not something to be deduplicated away.

One search failing (a bad fixture name, a transient API error) is logged to
that run's error list and does not stop the other searches from running; the
CLI exits `1` if any search failed and `0` if the run was clean, so a cron job
can alert on nonzero exit without the run itself having aborted early.

## Scheduling

The collector is a plain CLI command, safe to invoke repeatedly — point cron
or launchd at it, or wrap it in APScheduler if you'd rather keep the scheduler
in-process. In live mode, refresh the access token first (it's only good for
24 hours — see [Getting API credentials](#getting-api-credentials)):

```cron
0 7 * * * cd /path/to/aliexpress-dashboard && .venv/bin/python -m aliexpress_dashboard.collector.cli refresh-token && .venv/bin/python -m aliexpress_dashboard.collector.cli run >> collector.log 2>&1
```

Rate limiting and retry/backoff are handled inside the client (`AE_MIN_REQUEST_INTERVAL_SECONDS`,
`AE_MAX_RETRIES`, etc.) — you don't need to add your own throttling around the
CLI call itself.

## The dashboard

```bash
streamlit run run_dashboard.py
```

(Run the launcher, not `aliexpress_dashboard/dashboard/app.py` directly —
Streamlit executes its target as a top-level script, which would break that
file's package-relative imports.)

Three tabs, sharing the sidebar's filters (category, price band, minimum
rating, minimum sales volume, ship-to country) and composite-score weights:

- **Products** — the sortable results table (image, title, price, rating,
  star rating, review count, volume, discount, composite score,
  price-history sparkline, link to the listing). Tick rows and save them as a
  named shortlist; export the current filtered view to CSV or XLSX.
- **Momentum** — products ranked by change in sales volume, both since the
  last collection run and over a configurable rolling window (default 14
  days). Empty until a product has at least two observations, i.e. the
  collector has run at least twice.
- **Shortlists** — view, export, and manage the sets you've saved from the
  Products tab.

The composite score blends sales volume, rating, review count, and
price-band fit, each ranked relative to whatever's currently filtered (not
against the whole database) — the weights are sliders in the sidebar, so
"suitable" is whatever blend you dial in. Review count will mostly show as
neutral (0.5) since it's usually blank — see the gaps section below. Price-band
fit is modeled as *cheaper within your filtered band scores higher*; if you
want "fit" to mean something else (e.g. closest to the middle of the band),
that's a one-function change in `aliexpress_dashboard/dashboard/scoring.py`.

## Known gaps and modeling choices

Things worth knowing before you trust a number this tool shows you. Each is
marked confirmed (checked against a real live account) or a still-open
assumption.

**Confirmed live:**

- **The response envelope is genuinely inconsistent across this API family** —
  not a single convention, three different ones:
  - `aliexpress.ds.product.get`: no wrapping, `{result, rsp_code, rsp_msg}` directly.
  - `aliexpress.ds.text.search`, `/auth/token/*`: one layer, `{"<api_name>_response": {...}}`.
  - `aliexpress.ds.category.get`: two layers — the same wrapper, then a
    `resp_result` key (with sibling metadata like `request_id`, not itself
    single-keyed) holding `{result, resp_code, resp_msg}`.

  And "success" is signaled under three different field names depending on
  endpoint — `code` (`"00"`, not `"0"`), `rsp_code` (`"200"`), `resp_code`
  (`200`, an int) — none matching what the docs' own example JSON implied.
  The client auto-detects and unwraps rather than hardcoding any one of
  these per endpoint (`AliClient._unwrap_envelope`).
- **`local` needs a full locale, not a bare language code.** `"en"` fails
  the search call outright with an opaque `EXCEPTION_TEXT_SEARCH_FOR_DS`
  error and no other detail — despite the docs' own example using `"en"`.
  `"en_US"` works. Defaults have been fixed; if you're passing your own
  locale, use the full form.
- **`cateId` on search results is a comma-separated category *path***
  (`"66,200001147,201674401,200001313"`, root to leaf), not a single id as
  documented. The client takes the last (most specific) segment, which
  matches the `category_id` the detail endpoint reports for the same product.
- **`itemUrl` is protocol-relative** (`//www.aliexpress.com/...`) — works
  inside a browser page, not as a standalone link (a CSV cell, a fresh tab).
  The client prepends `https:`.
- **Price-band filtering does not work.** `ds.text.search` takes price
  bounds through a generic `searchExtend` array of filter objects rather
  than dedicated min/max params. Tried two different plausible structures
  live (a `{searchKey: "price", min, max}` object, and a bare `{min, max}`
  in both major and minor currency units) — neither changed the result
  count or price spread at all. `--min-price`/`--max-price` are still
  accepted and sent (harmless), but don't rely on them to narrow what the
  collector fetches from AliExpress. This doesn't affect the *dashboard's*
  price filter, which runs as a SQL `WHERE` clause over already-collected
  local data, not a live API call.
- **A self-developed app's OAuth token lasts 24 hours, not ~365 days** as
  AliExpress's own authorization-strategy docs claim. Refresh token is valid
  48 hours. See [Getting API credentials](#getting-api-credentials) and
  [Scheduling](#scheduling) — this needs a near-daily `refresh-token` call,
  not a once-a-year one.
- **Category names are genuinely available** — `aliexpress.ds.category.get`
  returns id, name, and parent id for the full tree (548 categories on the
  live account this was tested against), matching the shape always assumed.
  It just isn't joined onto each product automatically (see below).
- **Search-result pricing (`sale_price`/`original_price`) stays in the
  seller's native currency (typically CNY) regardless of the `currency`
  requested** — only `target_sale_price` honors it. On the detail endpoint,
  by contrast, both `sku_price` (list price) and `offer_sale_price` (actual
  buy price) come back already in the requested currency.
- **The signature is MD5**, not HMAC-SHA256 — confirmed by reading
  `python-aliexpress-api`'s source, since the affiliate-family signing code
  is the part of the library still worth reusing even though its endpoints
  aren't. `ds.*` and the OAuth token endpoints use the same TOP gateway and
  signing scheme.

**Design/modeling choices, not API surprises:**

- **Review count and star rating are usually blank.** They're real fields
  (`evaluation_count`, `avg_evaluation_rating`, confirmed live) but only on
  the per-product detail lookup, which the collector doesn't call
  automatically for every search result — that would be one extra API call
  per product on every run. Enriching a smaller set (e.g. a shortlist) with
  detail data is a natural next feature, not built yet.
- **A missing rating or review count scores as 0** (worst) in the composite
  score, not dropped or averaged in — an unproven product should rank behind
  one with a track record.
- **Sales volume can be a bucketed string** (`"1000+"`) rather than an exact
  number. It's parsed to a best-effort floor number for sorting/filtering,
  with the original text kept alongside (`sales_volume_display`) rather than
  discarded.
- **`ship_to_country` isn't a per-product field.** AliExpress doesn't return
  it on a product; it's a *search* parameter (`countryCode`, required on
  every search). The dashboard's ship-to filter works by attaching each
  product to the search that most recently collected it.
- **HTTPS is forced** (`port=443`) for every call this client makes.
- **Pagination is capped at 20 pages (1000 products) per search per run** —
  a safety ceiling, not an expected size (confirmed hit live on a broad
  keyword search). If a later page fails after earlier pages already
  succeeded, what was already collected is kept rather than discarded.
- **Currency is never mixed.** Every price is stored alongside its own
  currency; `target_sale_price`/`target_sale_price_currency` (normalized to
  `AE_TARGET_CURRENCY`) is the field every comparison, filter, and score uses
  — not the seller's/SKU's native `sale_price`, which can be in a different
  currency per listing.
- **One price per product, no variant handling.** A product's detail lookup
  can return many SKUs (colour, size, etc.) with different prices; this
  takes the first SKU as representative. A multi-variant product's real price
  range isn't fully captured by that single value.
- **No category name attached per product**, only `category_id` — even
  though `get_categories()` can resolve names, the collector doesn't do that
  join automatically. Building an id→name lookup for display is a natural
  small addition, not built yet.

## Testing

```bash
python -m pytest
```

Runs entirely offline against fixtures — no credentials, no network. Fixtures
are shaped to match confirmed live responses (the wrapped envelopes, the
nested SKU/video lists, a comma-separated category path, a protocol-relative
URL), not the simpler shapes the API docs showed, so the test suite actually
exercises the parsing this needed once real data arrived. Covers field
parsing (including the edge cases above), envelope unwrapping across all
three confirmed shapes, idempotent collection, pagination, momentum
calculation, score weighting, and the OAuth token exchange/refresh flow,
plus a Streamlit `AppTest` smoke test that boots the actual dashboard against
a seeded database.
