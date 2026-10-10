"""LangGraph StateGraph wiring the nine MarketSim agents.

    START → supervisor ─┬─(online)──→ competitor_discovery_online ──┐
                        ├─(physical)→ competitor_discovery_physical ┤
                        └─(abort)───────────────────────────────────┼──────────────→ report_composer → END
                                                                    ↓                      ↑
          pricing_intelligence → demand_trends → market_news → strategy_generation          │
                                                                    ↓                      │
                         ┌──────────→ quantitative_simulation → strategy_critic ─(done)────┘
                         │                                              │
                         └──────────── strategy_revision ←──(revise, ≤2)┘
"""
from __future__ import annotations

import logging
import operator
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Annotated, Any, Callable, TypedDict

from langgraph.graph import END, START, StateGraph

from app.agents import critic as critic_mod
from app.agents.llm_strategy import draft_strategies
from app.agents.planner import build_plan
from app.agents.report import compose_report
from app.agents.runtime import AGENT_LABELS, AnalysisRuntime
from app.agents.strategy_builder import StrategyContext, build_strategy_set
from app.intelligence.competitors import build_competitors, build_listings, price_stats
from app.intelligence.news import build_risks, classify_news
from app.intelligence.trends import summarize_series
from app.llm.adapter import LLMError
from app.onboarding import registry
from app.schemas.analysis import (
    CompetitorEntry, CriticEvaluationResult, Listing, NewsResult, Observation, PlannedSearch, PriceGroupStats,
    ResearchPlan, SearchOutcome, Strategy, StrategySimulation, TrendsResult,
)
from app.schemas.profile import BusinessProfileIn
from app.serpapi.adapters import amazon, autocomplete, maps, news, product, search, shopping, trends
from app.simulation.engine import run_simulation

log = logging.getLogger("marketsim.graph")


def _merge_dict(a: dict | None, b: dict | None) -> dict:
    return {**(a or {}), **(b or {})}


class GraphState(TypedDict, total=False):
    analysis_id: str
    mode: str
    profile: dict[str, Any]
    status: str
    plan: dict[str, Any]
    branch: str
    observations: Annotated[list[dict[str, Any]], operator.add]
    listings: list[dict[str, Any]]
    price_groups: dict[str, dict[str, Any]]
    competitors: list[dict[str, Any]]
    trends: Annotated[dict[str, dict[str, Any]], _merge_dict]
    news: dict[str, Any]
    strategies: list[dict[str, Any]]
    simulations: Annotated[dict[str, dict[str, Any]], _merge_dict]
    revision_count: int
    critic_rounds: Annotated[list[dict[str, Any]], operator.add]
    strategy_history: Annotated[list[dict[str, Any]], operator.add]
    simulation_history: Annotated[list[dict[str, Any]], operator.add]
    warnings: Annotated[list[str], operator.add]
    failed_agents: Annotated[list[str], operator.add]
    node_trace: Annotated[list[dict[str, Any]], operator.add]
    report: dict[str, Any]


def _dump(models: list) -> list[dict[str, Any]]:
    return [m.model_dump(mode="json") for m in models]


def build_graph(rt: AnalysisRuntime):
    emit = rt.emitter.emit
    settings = rt.settings

    # ------------------------------------------------------------ helpers
    def agent_node(name: str, graph_node: str | None = None) -> Callable:
        def deco(fn: Callable[[GraphState], dict[str, Any]]):
            def wrapper(state: GraphState) -> dict[str, Any]:
                emit(name, "agent_started", f"{AGENT_LABELS[name]} started", node=graph_node or name)
                if rt.on_agent_change:
                    rt.on_agent_change(name)
                t0 = time.perf_counter()
                status = "completed"
                try:
                    update = fn(state) or {}
                except Exception as exc:  # degrade, never crash the whole analysis
                    log.exception("node %s failed", name)
                    status = "failed"
                    msg = f"{type(exc).__name__}: {str(exc)[:300]}"
                    emit(name, "agent_failed", f"{AGENT_LABELS[name]} failed – {msg}")
                    update = {"warnings": [f"{AGENT_LABELS[name]} failed: {msg}"], "failed_agents": [name]}
                    if name == "supervisor":
                        update["status"] = "aborted"
                summary = update.pop("_summary", "completed")
                ms = round((time.perf_counter() - t0) * 1000, 1)
                if status == "completed":
                    emit(name, "agent_completed", summary, duration_ms=ms, node=graph_node or name)
                update["node_trace"] = [{"node": graph_node or name, "agent": name, "status": status, "duration_ms": ms}]
                return update
            wrapper.__name__ = graph_node or name
            return wrapper
        return deco

    def plan_of(state: GraphState) -> ResearchPlan:
        return ResearchPlan.model_validate(state["plan"])

    def profile_of(state: GraphState) -> BusinessProfileIn:
        return BusinessProfileIn.model_validate(state["profile"])

    def execute(tasks: list[PlannedSearch]) -> list[SearchOutcome]:
        if not tasks:
            return []
        with ThreadPoolExecutor(max_workers=settings.serpapi_max_concurrency) as pool:
            futures = [pool.submit(rt.gateway.search, t.engine, t.params, agent=t.agent, purpose=t.purpose) for t in tasks]
            return [f.result() for f in futures]

    def failure_warning(task: PlannedSearch, outcome: SearchOutcome) -> str | None:
        if outcome.status in {"ok", "deduplicated"}:
            return None
        if outcome.status == "empty":
            return f"{task.engine} returned no results for '{task.purpose}'."
        return f"{task.engine} search unavailable ({outcome.status}): {outcome.error or 'no detail'} – {task.purpose}."

    def market_currency(code: str | None) -> str | None:
        return registry.market_currency(code)

    def observations_of(state: GraphState) -> list[Observation]:
        return [Observation.model_validate(o) for o in state.get("observations", [])]

    def focus_terms(plan: ResearchPlan) -> dict[str, list[str]]:
        out = {}
        for f in plan.focuses:
            words = {w for t in f.terms.values() for w in t.lower().split() if len(w) > 3 and w not in {"brands", "store", "shop", "pack"}}
            out[f.value] = sorted(words)
        return out

    # ------------------------------------------------------------- nodes
    @agent_node("supervisor")
    def supervisor(state: GraphState) -> dict[str, Any]:
        profile = profile_of(state)
        plan = build_plan(profile, rt.gateway.budget)
        engines: dict[str, int] = {}
        for t in plan.planned:
            engines[t.engine] = engines.get(t.engine, 0) + 1
        emit("supervisor", "plan_created",
             f"Research plan: {plan.allocated} SerpApi request(s) within a budget of {plan.budget}; "
             f"{len(plan.focuses)} focus(es) × {len(plan.countries)} market(s).",
             branch=plan.branch, engines=engines, focuses=[f.label for f in plan.focuses], countries=plan.countries)
        for t in plan.skipped:
            emit("supervisor", "tool_skipped", f"Planner skipped {t.engine} ({t.purpose}) – request budget reached.",
                 engine=t.engine, status="skipped_budget")
        for m in plan.missing_inputs:
            emit("supervisor", "missing_input", f"Unknown input: {m.label}. {m.impact}", field=m.field)
        for key, decision in plan.analyses.items():
            if not decision["proceed"]:
                emit("supervisor", "analysis_gated", f"{key.replace('_', ' ').capitalize()} will not run: {decision['reason']}")
        emit("supervisor", "route_selected", f"Routing to the {plan.branch} research branch.", branch=plan.branch)
        return {"plan": plan.model_dump(mode="json"), "branch": plan.branch, "status": "running",
                "warnings": plan.notes, "_summary": f"Planned {plan.allocated} searches; branch={plan.branch}."}

    def discovery(state: GraphState) -> dict[str, Any]:
        plan = plan_of(state)
        tasks = [t for t in plan.planned if t.agent == "competitor_discovery"]
        outcomes = execute(tasks)
        obs: list[Observation] = []
        warnings: list[str] = []
        for task, outcome in zip(tasks, outcomes):
            if (w := failure_warning(task, outcome)):
                warnings.append(w)
            if not outcome.usable:
                continue
            if task.engine == shopping.ENGINE:
                new = shopping.parse(outcome, rt.evidence, country=task.country, focus=task.focus)
            elif task.engine == amazon.ENGINE:
                new = amazon.parse(outcome, rt.evidence, country=task.country, focus=task.focus)
            elif task.engine == search.ENGINE:
                new = search.parse(outcome, rt.evidence, country=task.country, focus=task.focus)
            elif task.engine == maps.ENGINE:
                new = maps.parse(outcome, rt.evidence, country=task.country, focus=task.focus)
            else:
                new = []
            obs.extend(new)
            emit("competitor_discovery", "evidence_extracted",
                 f"Extracted {len(new)} observation(s) from {task.engine} ({task.purpose}).",
                 engine=task.engine, count=len(new), refs=[o.ref for o in new[:5]])
        listings = []
        for c in plan.countries:
            listings += build_listings([o for o in obs if o.country == c], market_currency(c))
        comps = build_competitors(listings, obs, focus_terms(plan), {})
        counts = {r: sum(1 for c in comps if c.relation == r) for r in ("direct", "marketplace", "reference")}
        emit("competitor_discovery", "competitors_identified",
             f"Competitor directory: {counts['direct']} direct, {counts['marketplace']} marketplace, "
             f"{counts['reference']} reference (deduplicated).", **counts)
        return {"observations": _dump(obs), "competitors": _dump(comps), "warnings": warnings,
                "_summary": f"{len(obs)} observations; {counts['direct']} direct competitors."}

    competitor_discovery_online = agent_node("competitor_discovery", "competitor_discovery_online")(discovery)
    competitor_discovery_physical = agent_node("competitor_discovery", "competitor_discovery_physical")(discovery)

    @agent_node("pricing_intelligence")
    def pricing_intelligence(state: GraphState) -> dict[str, Any]:
        plan = plan_of(state)
        obs = observations_of(state)
        listings: list[Listing] = []
        for c in plan.countries:
            listings += build_listings([o for o in obs if o.country == c], market_currency(c))
        groups: dict[str, PriceGroupStats] = {}
        for c in plan.countries:
            for f in plan.focuses:
                if any(l.focus == f.value and l.country == c for l in listings):
                    groups[f"{f.value}|{c}"] = price_stats(listings, f.value, f.label, c, market_currency(c))
        flagged = {flag: sum(1 for l in listings if flag in l.flags)
                   for flag in ("currency_mismatch", "missing_currency", "unverified_size", "ambiguous_size", "promotion")}
        emit("pricing_intelligence", "evidence_extracted",
             f"Normalised {len(listings)} listing(s); {sum(1 for l in listings if l.unit_price is not None)} with a "
             f"comparable unit price.", **flagged)
        for flag in ("currency_mismatch", "missing_currency"):
            if flagged[flag]:
                emit("pricing_intelligence", "warning", f"{flagged[flag]} listing(s) excluded from price statistics: {flag.replace('_', ' ')}.")

        # Product details for the most-reviewed listing per focus (resolved from Shopping results)
        detail_tasks: list[PlannedSearch] = []
        resolved_from: list[str] = []
        for t in [t for t in plan.planned if t.agent == "pricing_intelligence"]:
            candidates = sorted([o for o in obs if o.kind == "product_listing" and o.focus == t.focus and o.country == t.country
                                 and (o.normalized.get("product_id") or o.normalized.get("page_token"))],
                                key=lambda o: (-(o.normalized.get("reviews") or 0), o.ref))
            if not candidates:
                emit("pricing_intelligence", "tool_skipped",
                     f"google_product skipped for {t.focus}: no product_id in Shopping results (dependency unavailable).",
                     engine=product.ENGINE, status="dependency_unavailable")
                continue
            top = candidates[0]
            m = registry.market(t.country) or {"gl": (t.country or "us").lower(), "hl": "en"}
            if top.normalized.get("product_id"):
                detail_tasks.append(t.model_copy(update={"params": product.build_params(top.normalized["product_id"], m)}))
            else:
                detail_tasks.append(t.model_copy(update={"engine": product.IMMERSIVE_ENGINE,
                                                         "params": product.build_immersive_params(top.normalized["page_token"])}))
            resolved_from.append(top.ref)
        details: list[Observation] = []
        warnings: list[str] = []
        for task, outcome, parent in zip(detail_tasks, execute(detail_tasks), resolved_from):
            if (w := failure_warning(task, outcome)):
                warnings.append(w)
            if outcome.usable:
                new = product.parse(outcome, rt.evidence, country=task.country, focus=task.focus, parent_ref=parent)
                details.extend(new)
                emit("pricing_intelligence", "evidence_extracted",
                     f"Product detail for {parent}: {len(new[0].normalized.get('offers') or []) if new else 0} offer(s).",
                     engine=task.engine, refs=[o.ref for o in new])
        comps = build_competitors(listings, obs, focus_terms(plan), {k.split("|")[0]: v for k, v in groups.items()
                                                                     if k.endswith("|" + (plan.countries[0] if plan.countries else ""))})
        summary = "; ".join(f"{g.focus_label} ({g.country}): median {g.currency} {g.median:,.0f}, n={g.included_count}"
                            for g in groups.values() if g.median is not None) or "No comparable price data."
        return {"observations": _dump(details), "listings": _dump(listings),
                "price_groups": {k: v.model_dump(mode="json") for k, v in groups.items()},
                "competitors": _dump(comps), "warnings": warnings, "_summary": summary}

    @agent_node("demand_trends")
    def demand_trends(state: GraphState) -> dict[str, Any]:
        plan = plan_of(state)
        tasks = [t for t in plan.planned if t.agent == "demand_trends"]
        query_focus = {f.terms["trend"]: f.value for f in plan.focuses}
        results: dict[str, TrendsResult] = {}
        obs: list[Observation] = []
        warnings: list[str] = []
        for country in plan.countries:
            ts_tasks = [t for t in tasks if t.country == country and t.params.get("data_type") == "TIMESERIES"]
            res = TrendsResult(status="unavailable", geo=(registry.market(country) or {}).get("trends_geo", country),
                               query_focus=query_focus)
            for task, outcome in zip(ts_tasks, execute(ts_tasks)):
                if (w := failure_warning(task, outcome)):
                    warnings.append(w)
                if outcome.usable:
                    points, new = trends.parse_timeseries(outcome, rt.evidence, country=country, query_focus=query_focus)
                    obs.extend(new)
                    res.points, res.queries = points, [q for q in outcome.params["q"].split(",")]
                    res.date_range, res.retrieved_at, res.data_origin = outcome.params.get("date"), outcome.retrieved_at, outcome.data_origin
                    res.summaries = [summarize_series(q, points) for q in res.queries]
                    res.evidence_refs += [o.ref for o in new]
                    res.status = "ok" if points else "unavailable"
                    for s in res.summaries:
                        emit("demand_trends", "evidence_extracted", s.description, engine=trends.ENGINE, query=s.query,
                             direction=s.direction)
            # Related queries for the term with the highest mean interest (dependent search)
            for task in [t for t in tasks if t.country == country and t.params.get("data_type") == "RELATED_QUERIES"]:
                ranked = sorted([s for s in res.summaries if s.mean is not None], key=lambda s: -s.mean)
                if not ranked:
                    emit("demand_trends", "tool_skipped", "Related-queries search skipped: no time series to rank terms.",
                         engine=trends.ENGINE, status="dependency_unavailable")
                    continue
                task = task.model_copy(update={"params": {**task.params, "q": ranked[0].query}})
                outcome = execute([task])[0]
                if (w := failure_warning(task, outcome)):
                    warnings.append(w)
                if outcome.usable:
                    related, new = trends.parse_related(outcome, rt.evidence, country=country, focus=query_focus.get(ranked[0].query))
                    res.related_queries = related
                    res.evidence_refs += [o.ref for o in new]
                    obs.extend(new)
                    emit("demand_trends", "evidence_extracted",
                         f"Related queries for '{ranked[0].query}': {len(related['top'])} top, {len(related['rising'])} rising.",
                         engine=trends.ENGINE)
            for task in [t for t in tasks if t.country == country and t.params.get("data_type") == "GEO_MAP_0"]:
                outcome = execute([task])[0]
                if (w := failure_warning(task, outcome)):
                    warnings.append(w)
                if outcome.usable:
                    regions, new = trends.parse_regions(outcome, rt.evidence, country=country, focus=task.focus)
                    res.regional_interest = regions
                    res.evidence_refs += [o.ref for o in new]
                    obs.extend(new)
            for task in [t for t in tasks if t.country == country and t.engine == autocomplete.ENGINE]:
                outcome = execute([task])[0]
                if (w := failure_warning(task, outcome)):
                    warnings.append(w)
                if outcome.usable:
                    suggestions, new = autocomplete.parse(outcome, rt.evidence, country=country, focus=task.focus)
                    res.keyword_suggestions = suggestions
                    res.evidence_refs += [o.ref for o in new]
                    obs.extend(new)
            if res.status == "ok" and warnings:
                res.status = "partial"
            if res.status == "unavailable":
                res.note = "Google Trends data unavailable for this market; no demand signal is inferred."
            results[country] = res
        ok = [c for c, r in results.items() if r.status != "unavailable"]
        return {"observations": _dump(obs), "trends": {c: r.model_dump(mode="json") for c, r in results.items()},
                "warnings": warnings, "_summary": f"Trends available for {len(ok)}/{len(results)} market(s)."}

    @agent_node("market_news")
    def market_news(state: GraphState) -> dict[str, Any]:
        plan = plan_of(state)
        profile = profile_of(state)
        tasks = [t for t in plan.planned if t.agent == "market_news"]
        obs: list[Observation] = []
        warnings: list[str] = []
        for task, outcome in zip(tasks, execute(tasks)):
            if (w := failure_warning(task, outcome)):
                warnings.append(w)
            if outcome.usable:
                new = news.parse(outcome, rt.evidence, country=task.country, focus=task.focus)
                obs.extend(new)
                emit("market_news", "evidence_extracted", f"Extracted {len(new)} dated news article(s).",
                     engine=news.ENGINE, count=len(new))
        comps = [CompetitorEntry.model_validate(c) for c in state.get("competitors", [])]
        items = classify_news(obs, {c.key: c.name for c in comps if c.relation == "direct"})
        flags = (registry.category(profile.category) or {}).get("risk_flags", [])
        missing = [m.field for m in plan.missing_inputs if m.field in {"exact_capital_inr", "product_unit_cost"}]
        risks = build_risks(items, flags, missing, live=rt.mode == "live")
        insufficient = len(items) < 2
        result = NewsResult(status="ok" if items else "unavailable", items=items, risks=risks,
                            insufficient_evidence=insufficient,
                            note="Insufficient current news evidence; no market developments are asserted." if insufficient else None)
        for r in risks[:6]:
            emit("market_news", "risk_identified", f"[{r.severity}] {r.title} ({r.basis.replace('_', ' ')})",
                 refs=r.evidence_refs[:3])
        return {"observations": _dump(obs), "news": result.model_dump(mode="json"), "warnings": warnings,
                "_summary": f"{len(items)} article(s) classified; {len(risks)} risk(s) registered."}

    def strategy_context(state: GraphState) -> StrategyContext:
        plan = plan_of(state)
        profile = profile_of(state)
        country = profile.pilot_country or (plan.countries[0] if plan.countries else "")
        groups = {k.split("|")[0]: PriceGroupStats.model_validate(v) for k, v in state.get("price_groups", {}).items()
                  if k.endswith(f"|{country}")}
        trends_state = state.get("trends", {}).get(country)
        news_state = state.get("news")
        return StrategyContext(
            profile=profile, focuses=plan.focuses, country=country, market_currency=market_currency(country),
            price_groups=groups, listings=[Listing.model_validate(l) for l in state.get("listings", [])],
            trends=TrendsResult.model_validate(trends_state) if trends_state else None,
            competitors=[CompetitorEntry.model_validate(c) for c in state.get("competitors", [])],
            news=NewsResult.model_validate(news_state) if news_state else None,
            evidence_refs=set(rt.evidence.items.keys()),
        )

    @agent_node("strategy_generation")
    def strategy_generation(state: GraphState) -> dict[str, Any]:
        ctx = strategy_context(state)
        drafts = None
        warnings = []
        if rt.llm:
            emit("strategy_generation", "llm_requested", f"Requesting structured strategy drafts from {rt.llm.label}.")
            try:
                drafts = draft_strategies(rt.llm, ctx)
                emit("strategy_generation", "llm_completed", "LLM drafts passed Pydantic schema validation.")
            except LLMError as exc:
                warnings.append(f"LLM strategy drafting failed ({exc}); deterministic generator used instead.")
                emit("strategy_generation", "warning", f"LLM output unusable ({exc}); falling back to the deterministic generator.")
        strategies = build_strategy_set(ctx, drafts)
        for s in strategies:
            emit("strategy_generation", "strategy_proposed",
                 f"{s.key} {s.name}: {s.sim_inputs.currency} {getattr(s.sim_inputs, 'selling_price', getattr(s.sim_inputs, 'average_transaction_value', 0)):,.0f} "
                 f"price basis, {sum(1 for c in s.claims if c.kind == 'market_fact')} evidence-backed claim(s), "
                 f"{len(s.assumptions)} labelled assumption(s).", strategy=s.key, archetype=s.archetype, focus=s.focus,
                 generated_by=s.generated_by)
        return {"strategies": _dump(strategies), "strategy_history": _dump(strategies), "revision_count": 0,
                "warnings": warnings, "_summary": f"Proposed {len(strategies)} distinct strategies ({strategies[0].generated_by})."}

    @agent_node("quantitative_simulation")
    def quantitative_simulation(state: GraphState) -> dict[str, Any]:
        strategies = [Strategy.model_validate(s) for s in state["strategies"]]
        existing = state.get("simulations", {})
        sims: dict[str, dict[str, Any]] = {}
        for s in strategies:
            prev = existing.get(s.key)
            if prev and prev.get("revision") == s.revision:
                continue  # unchanged strategy: results already computed
            sim = run_simulation(s.key, s.revision, s.sim_inputs, s.product_mix,
                                 iterations=settings.monte_carlo_iterations, seed=settings.monte_carlo_seed)
            sims[s.key] = sim.model_dump(mode="json")
            b = sim.base
            emit("quantitative_simulation", "simulation_completed",
                 f"{s.key} rev{s.revision}: base operating result {b.currency} {b.operating_result:,.0f}/month, contribution "
                 f"{b.contribution_per_order:,.0f}/order, break-even {b.break_even_orders if b.break_even_orders is not None else 'n/a'} "
                 f"orders; {sim.monte_carlo.prob_negative:.0%} of {sim.monte_carlo.iterations} Monte Carlo runs negative.",
                 strategy=s.key, revision=s.revision, operating_result=b.operating_result,
                 contribution_per_order=b.contribution_per_order, break_even_orders=b.break_even_orders,
                 prob_negative=sim.monte_carlo.prob_negative, optimisation=sim.optimization.status)
        return {"simulations": sims, "simulation_history": list(sims.values()),
                "_summary": f"Simulated {len(sims)} strategy version(s) with NumPy/SciPy (seed {settings.monte_carlo_seed})."}

    def critic_context(state: GraphState) -> critic_mod.CriticContext:
        ctx = strategy_context(state)
        return critic_mod.CriticContext(profile=ctx.profile, evidence=dict(rt.evidence.items),
                                        price_groups=ctx.price_groups, mode=rt.mode)

    @agent_node("strategy_critic")
    def strategy_critic(state: GraphState) -> dict[str, Any]:
        cctx = critic_context(state)
        strategies = [Strategy.model_validate(s) for s in state["strategies"]]
        round_no = len(state.get("critic_rounds", [])) + 1
        evaluations = []
        for s in strategies:
            sim = StrategySimulation.model_validate(state["simulations"][s.key])
            ev = critic_mod.evaluate(s, sim, cctx, round_no, strategies)
            evaluations.append(ev)
            fails = [c.id for c in ev.checks if c.status == "fail" and c.severity == "blocking"]
            warns = [c.id for c in ev.checks if c.status == "warn"]
            if ev.passed:
                emit("strategy_critic", "critic_accepted", f"{s.key} rev{s.revision} accepted"
                     + (f" with advisories: {', '.join(warns)}." if warns else "."), strategy=s.key, warnings=warns)
            else:
                emit("strategy_critic", "critic_rejected", f"{s.key} rev{s.revision} rejected: {', '.join(fails)}.",
                     strategy=s.key, failed_checks=fails, reasons=[c.reason for c in ev.checks if c.id in fails])
        all_passed = all(e.passed for e in evaluations)
        revisions = state.get("revision_count", 0)
        decision = "accept" if all_passed else ("revise" if revisions < critic_mod.MAX_REVISIONS else "accept_with_unresolved")
        if decision == "accept_with_unresolved":
            emit("strategy_critic", "warning",
                 f"Maximum of {critic_mod.MAX_REVISIONS} revisions reached; unresolved failures are reported, not hidden.")
        return {"critic_rounds": [{"round": round_no, "decision": decision,
                                   "evaluations": _dump(evaluations)}],
                "_summary": f"Round {round_no}: {sum(e.passed for e in evaluations)}/{len(evaluations)} passed → {decision}."}

    @agent_node("strategy_revision")
    def strategy_revision(state: GraphState) -> dict[str, Any]:
        cctx = critic_context(state)
        last = state["critic_rounds"][-1]
        evaluations = {e["strategy_key"]: CriticEvaluationResult.model_validate(e) for e in last["evaluations"]}
        updated, revised = [], []
        for raw in state["strategies"]:
            s = Strategy.model_validate(raw)
            ev = evaluations.get(s.key)
            if ev and not ev.passed:
                new, notes = critic_mod.revise(s, ev.revision_requests, cctx)
                emit("strategy_revision", "revision_performed", f"{s.key} → rev{new.revision}: " + " ".join(notes),
                     strategy=s.key, revision=new.revision, checks=[r.check_id for r in ev.revision_requests])
                updated.append(new)
                revised.append(new)
            else:
                updated.append(s)
        count = state.get("revision_count", 0) + 1
        return {"strategies": _dump(updated), "strategy_history": _dump(revised), "revision_count": count,
                "_summary": f"Revision {count}: revised {', '.join(s.key for s in revised)}."}

    @agent_node("report_composer")
    def report_composer(state: GraphState) -> dict[str, Any]:
        report = compose_report(state, rt)
        emit("report_composer", "report_composed",
             f"Report composed with {len(report['citations'])} citation(s); status {report['status']}.")
        return {"report": report, "status": report["status"], "_summary": "Report ready."}

    # ------------------------------------------------------------- routing
    def route_after_supervisor(state: GraphState) -> str:
        if state.get("status") == "aborted" or not state.get("plan"):
            return "abort"
        return state["branch"]

    def route_after_critic(state: GraphState) -> str:
        return "revise" if state["critic_rounds"][-1]["decision"] == "revise" else "done"

    g = StateGraph(GraphState)
    g.add_node("supervisor", supervisor)
    g.add_node("competitor_discovery_online", competitor_discovery_online)
    g.add_node("competitor_discovery_physical", competitor_discovery_physical)
    g.add_node("pricing_intelligence", pricing_intelligence)
    g.add_node("demand_trends", demand_trends)
    g.add_node("market_news", market_news)
    g.add_node("strategy_generation", strategy_generation)
    g.add_node("quantitative_simulation", quantitative_simulation)
    g.add_node("strategy_critic", strategy_critic)
    g.add_node("strategy_revision", strategy_revision)
    g.add_node("report_composer", report_composer)

    g.add_edge(START, "supervisor")
    g.add_conditional_edges("supervisor", route_after_supervisor, {
        "online": "competitor_discovery_online", "physical": "competitor_discovery_physical", "abort": "report_composer"})
    g.add_edge("competitor_discovery_online", "pricing_intelligence")
    g.add_edge("competitor_discovery_physical", "pricing_intelligence")
    g.add_edge("pricing_intelligence", "demand_trends")
    g.add_edge("demand_trends", "market_news")
    g.add_edge("market_news", "strategy_generation")
    g.add_edge("strategy_generation", "quantitative_simulation")
    g.add_edge("quantitative_simulation", "strategy_critic")
    g.add_conditional_edges("strategy_critic", route_after_critic, {"revise": "strategy_revision", "done": "report_composer"})
    g.add_edge("strategy_revision", "quantitative_simulation")
    g.add_edge("report_composer", END)
    return g.compile()


GRAPH_RECURSION_LIMIT = 40
