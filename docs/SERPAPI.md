# SerpApi integration

Every request goes through **`app/serpapi/gateway.py` → `SerpApiGateway`**, called only from the Python backend
(`GET https://serpapi.com/search.json`). The browser never talks to SerpApi and never sees a key.

## Engines and how each is used

| Engine | Adapter | Used by | Purpose | Key fields parsed (all optional) |
|---|---|---|---|---|
| `google_shopping` | `adapters/shopping.py` | Competitor Discovery (online; physical as price benchmark) | Advertised listings, merchants, prices | `shopping_results[].title, source, price, extracted_price, old_price, product_id, product_link, rating, reviews, delivery, extensions, immersive_product_page_token` |
| `google_product` | `adapters/product.py` | Pricing Intelligence | Offers/specs/reviews for the most-reviewed listing per focus (`product_id` from Shopping, `offer_view=true`) | `product_results`, `sellers_results.online_sellers`, `specs_results`, `reviews_results` |
| `google_immersive_product` | `adapters/product.py` | Pricing Intelligence (fallback) | Same, when Shopping returns a page token instead of a `product_id` | `product_results.stores[]` |
| `google_trends` | `adapters/trends.py` | Demand & Trends | `TIMESERIES` (all focus terms in one request so they share a scale), `RELATED_QUERIES` (dependent on the top-mean term), `GEO_MAP_0` (physical) | `interest_over_time.timeline_data[]`, `related_queries.top/rising`, `interest_by_region[]` |
| `google` | `adapters/search.py` | Competitor Discovery | Competitor websites and context | `organic_results[].title, link, snippet, source, position` |
| `google_news` | `adapters/news.py` | News & Risk | Dated developments with links | `news_results[]` incl. nested `stories[]`; `source` as object or string; `date`/`iso_date` |
| `google_maps` | `adapters/maps.py` | Competitor Discovery (physical) | Local competitors (`type=search`, `q="<store term> in <locality>, <city>"`) | `local_results[]` / `place_results`: `title, rating, reviews, address, website, place_id, gps_coordinates` |
| `amazon` | `adapters/amazon.py` | Competitor Discovery (marketplace channels) | Marketplace listings | `organic_results[].title, brand, asin, price, extracted_price, rating, reviews, delivery` |
| `google_autocomplete` | `adapters/autocomplete.py` | Demand & Trends (lowest priority) | Keyword expansion – suggestions, never volumes | `suggestions[].value` |

The demo plan for the required profile (India, 3 focuses, website + marketplaces) is:

```
T01-T03 google_shopping ×3   (P1)   T04 google_trends TIMESERIES (P1)
T05-T07 google ×3            (P2)   T08 google_news               (P2)
T09-T10 google_product ×2    (P3)   T11 amazon                    (P3)   T12 google_trends RELATED_QUERIES (P3)
google_autocomplete          (P4) → skipped: budget of 12 reached
```

## Gateway guarantees

| Concern | Implementation |
|---|---|
| Engine allowlist | `ENGINE_ALLOWLIST`; anything else returns status `blocked` without a network call. |
| Parameter validation | Per-engine required + allowed parameter sets; values must be 1–256 chars with no control characters. |
| Budget | Default 12 per analysis (`MAX_SERPAPI_REQUESTS_PER_ANALYSIS`). Excess calls return `skipped_budget`. The planner also allocates the budget by priority up front. |
| De-duplication | Identical (engine, canonical params) searches in one run share one request – concurrent callers wait for the first. |
| Cache | Persistent SQLite cache (live mode) with `SERPAPI_CACHE_TTL_SECONDS`; cache hits don't consume budget. |
| Retries | Exponential backoff with jitter for 429, 5xx, timeouts and transport errors (`SERPAPI_MAX_RETRIES`); 400/401/403 are not retried. |
| Concurrency | `BoundedSemaphore(SERPAPI_MAX_CONCURRENCY)` plus a bounded thread pool per node. |
| Empty results | SerpApi's `"Google hasn't returned any results"` payload → status `empty`, not `failed`. |
| Honest failure | Failures produce `failed` outcomes, `tool_failed` events and warnings; analyses finish as `partial`. Demo data is never substituted in live mode. |
| Secrets | Key only added to the outgoing query; scrubbed from error text; excluded from cache keys, stored params, events and logs. `httpx`/`httpcore` request logging is forced to WARNING because it would print URLs. |

## Normalised observations

Each parsed item becomes an `Observation` (`EvidenceSource` row) with: evidence ref (`SHOP-001`, `NEWS-004`, …),
engine, original query, target country, retrieved timestamp, source URL, source identifier, normalised values,
trimmed original payload, classification (`advertised_listing`, `search_snippet`, `map_listing`,
`relative_search_interest`, `reported_news`, `product_page_data`, `search_suggestion`), freshness (`current`,
`recent`, `stale`, `unknown`, `demo_fixture`) and data origin (`live`, `cache`, `demo_fixture`).

Search snippets are classified as `search_snippet` – they do not prove claims on the destination website, and
interpretive competitor tags (e.g. *likely D2C brand*) are labelled `interpretation`.

## Pricing rules

- Currency is detected from the price string (`₹`, `Rs.`, `£`, `AED`, `€`, `USD`). A bare `$` is accepted only in a
  USD market. Missing or mismatched currencies are flagged and **excluded** from statistics – no FX conversion.
- Pack sizes are parsed from titles (`250g`, `1 kg`, `4 x 30g`, `Pack of 3 (200g each)`, `6 Bars`). Ambiguous
  (`80g & 120g`) or missing sizes are flagged *unverified* and excluded from unit-price comparisons.
- Unit prices are only compared within one basis per group (per 100 g / per 100 ml / per unit).
- Strategy price anchors use pack-normalised unit-price quartiles × the typical pack when ≥4 verified sizes exist;
  otherwise absolute quartiles, explicitly labelled as not normalised.
- Statistics are labelled as describing *sampled listings only*; outliers (1.5×IQR) and promotions are flagged.

## Recording genuine fixtures

```bash
cd backend
# needs SERPAPI_API_KEY; uses at most the configured request budget
.venv/bin/python scripts/record_fixtures.py
# replay offline
FIXTURE_VERSION=recorded-YYYY-MM-DD DEMO_MODE=true .venv/bin/python -m uvicorn app.main:app --port 8000
```

Recorded fixture sets carry `"synthetic": false`, and the UI and report label them as *recorded, not real-time*.
