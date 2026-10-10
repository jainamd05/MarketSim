# MarketSim AI

**Autonomous multi-agent business intelligence and strategy simulator.**

MarketSim helps aspiring and existing entrepreneurs test an e-commerce or physical-retail idea *before*
committing capital. A dynamic questionnaire builds a structured business profile; nine LangGraph agents
research competitors, prices, search trends and news through **SerpApi**; three concrete strategies are
simulated with deterministic NumPy/SciPy code; a critic rejects weak assumptions and forces bounded
revisions; and an interactive dashboard lets you run what-if analysis without spending more search credits.

```
Questionnaire → BusinessProfile → Supervisor (plan + budget) ─┬─ online:   Shopping · Product · Search · Amazon · Trends · News
                                                              └─ physical: Maps · Search · Trends · News · Shopping (benchmarks)
   → Pricing intelligence → Demand & trends → News & risk → 3 strategies → Simulation → Critic ⟲ (≤2 revisions) → Report → Dashboard
```

> **Runs with zero API keys.** Without `SERPAPI_API_KEY` the app starts in clearly-labelled **DEMO** mode. It replays
> saved, synthetic SerpApi-format fixtures for the demonstration profile and fills any other profile with deterministic
> synthetic responses (fictional brands), so the questionnaire is genuinely form-driven. With a key it makes genuine
> requests and reports failures honestly – it never silently substitutes demo data for a live failure.

---

## Contents

- [Quick start](#quick-start) (Windows / macOS / Linux)
- [Configuration](#configuration)
- [Running tests](#running-tests)
- [Using the app](#using-the-app)
- [API](#api)
- [Project layout](#project-layout)
- [Known limitations](#known-limitations)
- Further docs: [Architecture](docs/ARCHITECTURE.md) · [SerpApi integration](docs/SERPAPI.md) ·
  [Demo mode](docs/DEMO_MODE.md) · [Hackathon submission & demo script](docs/HACKATHON.md)

## Quick start

Prerequisites: **Python 3.11+** and **Node.js 20+** (developed with Python 3.11.5 and Node 24).

### 1. Backend (FastAPI, port 8000)

**Windows (PowerShell)**
```powershell
cd backend
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
copy ..\.env.example .env        # optional – no keys needed for demo mode
.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
```

**macOS / Linux**
```bash
cd backend
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp ../.env.example .env          # optional – no keys needed for demo mode
.venv/bin/python -m uvicorn app.main:app --reload --port 8000
```

The SQLite database (`backend/marketsim.db`) is created automatically. API docs: <http://localhost:8000/docs>.

### 2. Frontend (Vite + React, port 5173)

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>. The dev server proxies `/api` to `http://127.0.0.1:8000`.

### 3. Demonstrate

Click **Run the demo profile** on the landing page – or follow the [3-minute demo script](docs/HACKATHON.md#demo-script-under-3-minutes).

## Configuration

All configuration comes from environment variables or `backend/.env` (see [`.env.example`](.env.example)).
Secrets are only read server-side; they are never returned by the API, stored in SQLite, cached, logged or bundled
into the frontend.

| Variable | Default | Purpose |
|---|---|---|
| `SERPAPI_API_KEY` | – | Enables LIVE mode. |
| `DEMO_MODE` | `auto` | `auto` = live when a key exists, else demo · `true` = always fixtures · `false` = always live. |
| `MAX_SERPAPI_REQUESTS_PER_ANALYSIS` | `12` | Hard request budget per analysis. |
| `SERPAPI_CACHE_TTL_SECONDS` | `86400` | Persistent response cache TTL (live mode). |
| `SERPAPI_TIMEOUT_SECONDS` / `SERPAPI_MAX_CONCURRENCY` | `25` / `3` | Per-request timeout and parallelism bound. |
| `LLM_PROVIDER` | `none` | `none` · `openai` · `anthropic` · `groq` · `gemini`. |
| `LLM_MODEL` | provider default | e.g. `gpt-4o-mini`, `claude-sonnet-5-5`, `llama-3.3-70b-versatile`, `gemini-2.5-flash`. |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | – | Paid LLM providers. |
| `GROQ_API_KEY` / `GEMINI_API_KEY` | – | Free-tier-friendly providers (OpenAI-compatible endpoints). |
| `DATABASE_URL` | `sqlite:///./marketsim.db` | Relative paths resolve from `backend/`. |
| `CORS_ORIGINS` | `http://localhost:5173,…` | Allowed browser origins. |

**API keys needed for live mode:** only `SERPAPI_API_KEY`. An LLM key is optional – without one, strategies come
from a transparent rule-based generator (labelled *deterministic* everywhere). With one, the LLM drafts strategy
narrative and bounded assumptions; output is validated against Pydantic schemas, falls back honestly on failure, and
**never** computes financial results.

## Running tests

```bash
# Backend – 101 tests (pytest + FastAPI TestClient; no network: fixtures + httpx.MockTransport)
cd backend
.venv/bin/python -m pytest          # Windows: .venv\Scripts\python -m pytest

# Frontend – 25 tests (Vitest + React Testing Library) and type-checked production build
cd frontend
npm test
npm run build
```

The frontend dashboard test renders `frontend/src/test/fixtures/demo-analysis.json`, a saved analysis produced by
the real backend workflow. Regenerate it after backend changes:

```bash
cd backend && .venv/bin/python scripts/export_demo_analysis.py
```

## Using the app

1. **Landing page** – product overview, the nine agents, the SerpApi engines in use, the demonstration profile and recent analyses.
2. **Onboarding wizard** – 11 branching steps (the first answer – online vs physical – changes later questions;
   categories/focuses/markets/fields come from [`shared/questionnaire.json`](shared/questionnaire.json)). Back/Next,
   validation, progress indicator and a draft auto-saved in the browser.
3. **Review & confirm** – editable cards, *Unknown* shown explicitly, **Save draft**, **Run market analysis** (choose demo or live).
4. **Agent execution** – live progress, request counter and the War Room event feed.
5. **Dashboard** – Overview · Competitor Intelligence · Market Trends · Strategy Lab · What-If Simulator · AI Agent War Room · Evidence & Risks.

## API

| Method | Route | Purpose |
|---|---|---|
| GET | `/api/health` · `/api/config` | Liveness; non-secret configuration (mode, budget, engines, LLM). |
| GET | `/api/onboarding/questions` | The question registry. (`/api/onboarding/demo-profile` returns the demo profile.) |
| POST · GET · PUT | `/api/profiles`, `/api/profiles/{id}` | Create / read / update a validated `BusinessProfile`. |
| POST | `/api/analyses` | Start an analysis (background thread); returns `analysis_id` (202). |
| GET | `/api/analyses/{id}` | Status, progress, request counter, plan, warnings. |
| GET | `/api/analyses/{id}/events?after=N` | Incremental execution events (polling). |
| GET | `/api/analyses/{id}/competitors` · `/trends` · `/strategies` · `/report` · `/evidence` | Results. |
| POST | `/api/analyses/{id}/simulate` | What-if recomputation – deterministic Python, 0 SerpApi requests. |

Errors use one envelope: `{"error": {"code", "message", "details"}}`.

## Project layout

```
backend/
  app/
    config.py · db.py · models.py (12 entities + response cache) · main.py
    schemas/      profile.py (BusinessProfile) · analysis.py · api.py
    onboarding/   registry loader for shared/questionnaire.json
    serpapi/      gateway.py (allowlist, budget, cache, backoff, fixtures) · normalize.py · adapters/<engine>.py
    intelligence/ units.py · competitors.py · trends.py · news.py
    simulation/   finance.py · scenarios.py · montecarlo.py · optimizer.py · engine.py
    llm/          adapter.py (OpenAI · Anthropic · Groq · Gemini)
    agents/       graph.py (LangGraph) · planner.py · strategy_builder.py · llm_strategy.py · critic.py · report.py · runtime.py
    services/     analysis_service.py (background execution + persistence)
    api/          routes.py
  fixtures/serpapi/v1/   versioned demo fixtures + manifest
  scripts/      build_demo_fixtures.py · record_fixtures.py · export_demo_analysis.py
  tests/        97 tests
frontend/
  src/features/onboarding/   flow.ts (branching + Zod) · OnboardingWizard · ReviewPage
  src/features/dashboard/    Overview · Competitors · Trends · StrategyLab · WhatIf · WarRoom · Evidence
  src/pages/ · src/components/ui (shadcn-style) · src/lib (api, types, format) · src/test
shared/questionnaire.json    configuration-driven question registry (used by both sides)
docs/                        architecture, SerpApi, demo mode, hackathon
```

## Known limitations

- **Demo fixtures are synthetic.** The saved fixtures and the on-demand synthetic responses follow SerpApi's response
  shapes but use fictional brands and `.example` URLs; they demonstrate the workflow, not the Indian food market. The
  demonstration profile replays saved fixtures; any other profile is filled in with deterministic synthetic responses
  so the form always produces a populated result (set `DEMO_SYNTHETIC_FALLBACK=false` to restore the older behaviour,
  where profile-specific misses report `fixture_missing` and the run finishes *partial*).
- **Live mode is implemented and tested against mocked transports, but was not verified against the real SerpApi
  service during development** (no key was available). Field names follow SerpApi's documentation and are parsed
  defensively; Google Shopping layouts change, and the `google_immersive_product` fallback exists for results without `product_id`.
- **LLM providers are tested with mocked HTTP only.** Endpoint shapes follow each provider's public API.
- Search results are samples: no market size, market share, sales volume or conversion rate is ever estimated.
- CAC, unit cost, repeat rate, footfall and conversion default to labelled, editable *scenario assumptions*; they are illustrative, not benchmarks.
- No FX conversion: listings in other currencies are excluded from statistics; non-INR capital is not modelled.
- Monte Carlo frequencies come from stated distributions, not calibrated probabilities.
- Hybrid (online + physical) businesses are reserved in the registry but not yet enabled.
- Background work uses an in-process thread pool: analyses in flight are lost if the server restarts.
- Regulatory notes are general guidance, not compliance advice or certification.
