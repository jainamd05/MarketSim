# Architecture

MarketSim is a small monorepo: a FastAPI backend that owns all research, simulation and persistence, and a
React frontend that only renders results and collects inputs. There are no extra services (no Redis, Celery or
queues); long-running analyses run on an in-process thread pool and persist progress to SQLite.

```
┌──────────────┐  /api (JSON)   ┌──────────────────────────────────────────────────────────────────────┐
│ React + Vite │ ─────────────▶ │ FastAPI routes                                                        │
│  wizard      │   polling      │   ├─ ProfileCRUD (Pydantic BusinessProfile)                           │
│  dashboard   │ ◀───────────── │   ├─ AnalysisService ── ThreadPoolExecutor ──▶ LangGraph StateGraph    │
└──────────────┘                │   │                                             │                     │
                                │   │   AnalysisRuntime: SerpApiGateway · EventEmitter · EvidenceRegistry│
                                │   │                    · LLMClient (optional)                          │
                                │   └─ /simulate ──▶ simulation.engine (NumPy / SciPy, no LLM)          │
                                │ SQLAlchemy ─▶ SQLite (profiles, runs, events, searches, evidence, …)  │
                                └──────────────────────────────────────────────────────────────────────┘
```

## The LangGraph workflow

`app/agents/graph.py` builds a `StateGraph(GraphState)` per analysis. Nodes are closures over an
`AnalysisRuntime` (gateway, event emitter, evidence registry, optional LLM) so that non-serialisable services
stay out of the graph state, while every *result* flows through shared state.

```
START → supervisor ─┬─(online)──→ competitor_discovery_online ──┐
                    ├─(physical)→ competitor_discovery_physical ┤
                    └─(abort)──────────────────────────────────────────────→ report_composer → END
                                                                ↓                ↑
      pricing_intelligence → demand_trends → market_news → strategy_generation   │
                                                                ↓                │
                     ┌────────→ quantitative_simulation → strategy_critic ─(done)┘
                     └──────── strategy_revision ←──(revise, at most 2 times)───┘
```

| Node | Agent | What it really does |
|---|---|---|
| `supervisor` | Supervisor & Planning | Validates the profile with Pydantic, resolves focus terms from the registry, lists unknown inputs, builds a prioritised research plan and drops the lowest-priority searches that exceed the budget. Gates capital optimisation when capital is unknown. Never invents financial values. |
| `competitor_discovery_*` | Competitor Discovery | Executes the branch's discovery searches concurrently (bounded), parses them **sequentially** so evidence refs are deterministic, then builds a deduplicated directory (direct / marketplace / reference). |
| `pricing_intelligence` | Pricing Intelligence | Normalises listings (currency detection, pack-size parsing, unit prices), computes sampled price statistics per focus/country, resolves `google_product` (or `google_immersive_product`) requests from the most-reviewed listing, adds evidence-backed positioning tags. |
| `demand_trends` | Demand & Trends | Google Trends time series for all focus terms in one request (shared scale), then a dependent related-queries request for the term with the highest mean interest; regional interest / autocomplete when planned. |
| `market_news` | News & Risk | Google News, classified by topic (launch, supply, regulatory, funding, competitor) and nature (reported vs forward-looking). Builds a risk register that separates evidence from category guidance and missing inputs. |
| `strategy_generation` | Strategy Generation | Exactly three archetypes: competitive pricing, premium differentiation, bundles & repeat. Optional LLM drafts are schema-validated; numbers are always rebuilt by `strategy_builder.py`. |
| `quantitative_simulation` | Quantitative Simulation | `run_simulation()` for every new strategy revision: base, bear/base/bull, seeded Monte Carlo, MILP inventory allocation. |
| `strategy_critic` | Critic & Validation | Twelve structured checks per strategy; blocking failures create `RevisionRequest`s. Decision: `accept`, `revise` (if < 2 revisions so far) or `accept_with_unresolved`. |
| `strategy_revision` | Strategy Generation (targeted) | Applies only the requested fixes (e.g. multi-pack, price to sampled median, conservative CAC, inventory scaled to capital, unsupported claims relabelled). |
| `report_composer` | Report Composer | Separates observed facts from modelled scenarios, lists assumptions, risks, unresolved questions, limitations, citations, search usage and an inputs hash. |

Each node is wrapped by `agent_node()`, which emits `agent_started` / `agent_completed` / `agent_failed` and
converts exceptions into warnings so a single failure degrades the analysis instead of crashing it.

### Shared state

`GraphState` uses LangGraph reducers: list fields (`observations`, `warnings`, `critic_rounds`,
`strategy_history`, `simulation_history`, `node_trace`) append with `operator.add`; dict fields (`trends`,
`simulations`) merge. Strategies are replaced on each revision while every version is kept in `strategy_history`.

## Simulation engine (no LLM arithmetic)

`app/simulation/finance.py` – online model:

```
AOV                    = selling_price × units_per_order
ad-acquired orders     = monthly_ad_budget / CAC
total orders           = ad-acquired + organic + repeat
variable cost / order  = product cost + packaging + shipping + platform fee + refund allowance
contribution / order   = AOV − variable cost / order
operating result       = total orders × contribution − ad budget − fixed costs   (ad budget subtracted once)
break-even orders      = ceil((ad budget + fixed) / contribution)                 (only if contribution > 0)
runway                 = (capital − initial investment) / monthly loss            (only if capital known)
```

The physical model uses footfall × conversion × opening days, average transaction value, COGS %, card fees,
shrinkage, rent, staff, utilities and marketing. Scenarios apply explicit multipliers (e.g. bear: CAC ×1.35,
unit cost ×1.10, returns +3 pp). Monte Carlo uses `numpy.random.default_rng(seed)` with ≥1,000 iterations and
publishes every distribution. The optimiser is `scipy.optimize.milp` with integer units, a hard budget
constraint and per-SKU stocking caps; it is disabled when capital is unknown.

## Persistence

| Entity | Contents |
|---|---|
| `BusinessProfile` | Validated profile JSON + indexed columns, draft/confirmed status. |
| `AnalysisRun` | Profile snapshot, mode, status, budget, requests used, plan, aggregated results. |
| `AgentEvent` | Ordered execution events with metadata (engine, results, duration, origin). |
| `SearchRequest` | Sanitised params (no key), status, attempts, duration, raw response. |
| `EvidenceSource` | Every normalised observation with provenance (engine, query, URL, timestamps, freshness, origin). |
| `Competitor`, `ProductListing`, `TrendObservation` | Normalised research outputs. |
| `BusinessStrategy`, `SimulationScenario`, `CriticEvaluation` | Every revision, every simulation, every critic round. |
| `AnalysisReport` | Final report with `inputs_hash` and `content_hash`. |
| `SerpApiCacheEntry` | Live-mode response cache keyed by a hash of engine + params (never the key). |

**Reproducibility:** the report is a deterministic function of the stored profile, stored SerpApi responses,
the simulation seed and the LLM mode. Two demo runs produce identical `inputs_hash` and `content_hash`
(asserted in `tests/test_integration_graph.py`).

## Frontend

- React 18 + TypeScript + Vite 6, Tailwind CSS v4, shadcn-style components (Radix primitives + CVA), Lucide icons.
- React Router routes: `/`, `/onboarding`, `/onboarding/review`, `/analysis/:id/run`, `/analysis/:id`.
- The onboarding flow is a pure module (`features/onboarding/flow.ts`): step visibility, per-step Zod schemas,
  reconciliation when an earlier answer changes, and draft ⇄ payload conversion. React Hook Form uses a resolver
  that picks the current step's schema.
- Charts use Recharts with a colour-blind-validated categorical palette (strategy identity S1/S2/S3 is consistent
  across tabs) and a custom SVG range chart for scenarios.
- A data-mode banner is visible on every screen; analysis pages set it from the analysis's own mode.
