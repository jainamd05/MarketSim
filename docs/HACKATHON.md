# MarketSim AI – SerpApi Hackathon submission

## One-paragraph description

MarketSim AI is an autonomous, multi-agent strategy simulator for people planning or running an e-commerce
store or physical shop. A branching questionnaire captures the business without free-text essays, then a
LangGraph workflow of nine specialised agents researches the market through **eight SerpApi engines** – Google
Shopping, Google Product (with an Immersive Product fallback), Google Trends, Google Search, Google News, Google
Maps, Amazon and Google Autocomplete. Prices are normalised by pack size and currency, competitors are
deduplicated across sources, and every claim keeps its link and timestamp. Three distinct strategies are
simulated with deterministic NumPy/SciPy maths (unit economics, bear/base/bull, seeded Monte Carlo, MILP
inventory optimisation), and a critic agent rejects weak assumptions and forces up to two targeted revisions.
Users then explore what-if scenarios without spending more search credits.

## Why the SerpApi usage is meaningful

- **Each engine answers a different question** – Shopping/Amazon: what competitors charge; Product: who sells the
  top product and at what offers; Search/Maps: who the competitors are online and nearby; Trends: whether interest
  is rising; News: what is changing; Autocomplete: how people phrase demand.
- **Dependent searches**: Product requests use `product_id`s found by Shopping; related-queries targets the
  Trends term with the highest observed interest.
- **Branch-aware routing**: online businesses get Shopping/Product/Amazon; physical shops get Maps-first local discovery.
- **Budget discipline**: a supervisor plans searches by priority within a configurable 12-request budget, with
  caching, de-duplication and retries in one gateway, and a live request counter in the UI.
- **Provenance everywhere**: 70+ normalised observations per run, each with engine, query, URL, retrieval time,
  freshness and data origin, cited from the report and the dashboard.
- **Honesty**: Trends is labelled relative interest (not demand); snippets are not treated as proof; no market
  share, sales or customer counts are fabricated; failures are reported, never papered over with demo data.

## Demo script (under 3 minutes)

Start both servers (see README), open <http://localhost:5173>.

| Time | Action | What to say |
|---|---|---|
| 0:00 | Landing page | "MarketSim tests a business idea against live search data before you spend money. Nine LangGraph agents, eight SerpApi engines, deterministic maths. The yellow banner says this run uses saved demo fixtures – the app never pretends they're live." |
| 0:15 | Click **Review & edit first**, scroll the review cards | "Online food brand, India pilot, worldwide ambition, ₹40k/month ads, capital above ₹10 lakh but exact amount unknown – note the *Unknown* badges. Unknowns stay unknown; they are never zero." Optionally click **Edit** to show the branching wizard (switching to *Physical shop* swaps in city and rent questions). |
| 0:35 | **Run market analysis** | "The supervisor plans 12 requests and skips autocomplete to stay in budget. Watch the War Room: Shopping, Search, Amazon, Product, Trends, News – each event shows engine, result count and duration." |
| 0:55 | Point at critic events | "The critic rejected the competitive-pricing strategy – negative contribution per order. It forced a multi-pack revision, rejected again, then priced to the sampled median. Two revisions max." |
| 1:10 | **Open dashboard → Overview** | "Observed facts vs modelled scenarios are separated; every finding has evidence chips that link to the source." |
| 1:25 | **Competitor Intelligence** | "Prices compared per 100 g only where pack sizes are verified. A dollar-priced listing and a listing without a currency were excluded, not guessed. 21 direct competitors after de-duplication." |
| 1:45 | **Market Trends** | "Coffee interest is rising ~38%, honey declining – relative interest, explicitly not sales demand." |
| 1:55 | **Strategy Lab** | "Three strategies on three focuses. Every assumption is labelled: your input, market evidence, or scenario assumption." |
| 2:15 | **What-If** – drag CAC and selling price; type a capital amount | "Recomputed by Python on the backend – zero SerpApi calls. Entering capital unlocks the inventory optimiser, which never exceeds it." |
| 2:40 | **Evidence & Risks** | "Citations with timestamps, risks split into evidence vs category guidance like FSSAI labelling, unresolved questions, limitations, and a reproducibility hash." |
| 2:55 | Close | "With a SerpApi key, the same workflow runs live." |

## AI tools used in development

- **Claude Code (Anthropic, Claude Opus 5.5)** was used as the development agent: it designed the architecture,
  wrote the backend, frontend, fixtures, tests and documentation, ran the test suites and production build, and
  exercised the running app in a browser pane. All tests in this repository were executed, and their real results
  are reported in the README.
- The application itself optionally uses an LLM (OpenAI, Anthropic, Groq or Gemini) for strategy narrative only;
  the default configuration uses none.

## What is and is not verified

| Verified | Not verified |
|---|---|
| Full demo workflow end to end (API, graph, SQLite, UI) | Real SerpApi responses (no key during development) |
| 97 backend tests, 25 frontend tests, type-checked production build | Real LLM provider calls (mocked transports only) |
| Gateway behaviour against mocked 429/5xx/401/timeouts/empty payloads | Behaviour under SerpApi rate limits at scale |
