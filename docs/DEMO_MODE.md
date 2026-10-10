# Demo mode

Demo mode lets anyone run the complete multi-agent workflow offline, without API keys, once dependencies are installed.

## When it is active

| `DEMO_MODE` | `SERPAPI_API_KEY` | Default mode |
|---|---|---|
| `auto` (default) | not set | **demo** |
| `auto` | set | live (demo still selectable per analysis on the review screen) |
| `true` | any | demo only – live analyses are refused |
| `false` | set / not set | live (fails honestly with a clear error if the key is missing) |

The mode is stored on every analysis. Each request in the War Room shows `origin: demo_fixture`, every citation is
labelled **Demo data**, a banner on every screen reads **DEMO DATA**, and the report's first limitation states that
the data is synthetic.

## What the fixtures are

`backend/fixtures/serpapi/v1/` contains 14 JSON responses plus `manifest.json`, generated deterministically by
`backend/scripts/build_demo_fixtures.py`:

- They mirror SerpApi's documented response shapes for `google_shopping`, `google_product`, `google_trends`
  (`TIMESERIES`, `RELATED_QUERIES`), `google`, `google_news`, `amazon` and `google_autocomplete`.
- All brands are **fictional** (e.g. *Kaapi Trail*, *Crunch Theory*, *Wildbloom Honey*); brand and news URLs use the
  reserved `.example` domain. Well-known marketplaces appear only as seller names.
- They deliberately include messy, realistic cases so the pipeline's safeguards are visible: a USD listing in an
  INR market, a price without a currency symbol, ambiguous and missing pack sizes, multipacks, promotions,
  count-based items mixed with weight-based ones, a listicle and an industry report among organic results, a nested
  news story cluster, a forward-looking headline, a stale article and a partial final Trends week.
- `search_metadata.created_at` is the fixture's authored date (28 Sep 2026); it is used as the retrieval time so
  demo runs are reproducible and never appear "current".
- The manifest is marked `"synthetic": true`.

Fixture lookup is keyed by the canonical (engine, parameters) hash. Only the demonstration profile's requests exist,
so any other profile in demo mode reports `fixture_missing` for those searches and finishes as **partial** – it does
not borrow unrelated data.

## Reproducibility

Demo runs are deterministic: the plan, evidence references, strategy builder (with no LLM), simulation seed and
critic are all deterministic. Two runs produce identical `inputs_hash` and `content_hash`
(`test_report_is_reproducible_from_stored_inputs`).

## What the demo shows

- 12 of 12 budgeted requests, autocomplete skipped by the planner.
- Currency-mismatched and currency-less listings excluded from statistics.
- 21 direct competitors, 4 marketplaces and 2 reference pages after de-duplication.
- Three strategies on three different focuses (premium honey/pantry, competitive snacks, coffee bundles).
- The critic rejects the competitive-pricing snacks strategy twice for negative contribution; targeted revisions
  move it to 2-unit multi-packs and then to the sampled median price; it is accepted in round 3 with advisory
  warnings (break-even far above modelled volume, 100% of Monte Carlo runs negative). The dashboard reports this honestly.
- Capital is unknown, so the optimiser is disabled until a capital amount is entered in What-If.

## Regenerating

```bash
cd backend
.venv/bin/python scripts/build_demo_fixtures.py     # rebuild synthetic fixtures
.venv/bin/python scripts/export_demo_analysis.py    # refresh the frontend test's saved analysis
```
