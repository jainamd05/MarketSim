"""Report Composer: combines verified findings, labelled assumptions, numerical results and
critique decisions. Observed facts and modelled scenarios are kept in separate sections."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from app.onboarding import registry
from app.schemas.analysis import AnalysisReportContent

if TYPE_CHECKING:
    from app.agents.runtime import AnalysisRuntime

DISCLAIMER = (
    "MarketSim provides decision support, not financial, legal or tax advice. Market observations are samples of search "
    "results and do not represent the whole market. Financial figures are modelled scenarios built on labelled "
    "assumptions; they are not forecasts and no profit is guaranteed."
)
VOLATILE_KEYS = {"generated_at", "analysis_id"}


def stable_hash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str, ensure_ascii=False).encode("utf-8")).hexdigest()


def inputs_hash(profile: dict[str, Any], rt: "AnalysisRuntime") -> str:
    searches = sorted(
        [{"engine": h.engine, "params": h.params, "status": h.status,
          "response": stable_hash(h.data) if h.data is not None else None} for h in rt.gateway.history
         if h.status != "deduplicated"],
        key=lambda x: json.dumps(x, sort_keys=True),
    )
    return stable_hash({"profile": profile, "searches": searches, "mode": rt.mode, "llm": rt.llm_mode,
                        "seed": rt.settings.monte_carlo_seed, "iterations": rt.settings.monte_carlo_iterations,
                        "budget": rt.gateway.budget, "fixture_version": rt.settings.fixture_version if rt.mode == "demo" else None})


def content_hash(report: dict[str, Any]) -> str:
    return stable_hash({k: v for k, v in report.items() if k not in VOLATILE_KEYS})


def _profile_summary(profile: dict[str, Any]) -> dict[str, Any]:
    reg = registry.load_registry()
    cat = registry.category(profile.get("category", ""))
    focuses = profile.get("compare_focuses") or ([profile.get("subcategory")] if profile.get("subcategory") else [])
    unknown = [k for k in ("exact_capital_inr", "monthly_ad_budget_inr", "product_unit_cost", "average_order_value",
                           "selling_price", "shipping_cost", "monthly_fixed_costs") if profile.get(k) is None]
    return {
        "business_type": profile.get("business_type"),
        "business_stage": profile.get("business_stage"),
        "category": cat["label"] if cat else profile.get("custom_category") or profile.get("category"),
        "focuses": [((registry.subcategory(profile.get("category", ""), f) or {}).get("label") or f) for f in focuses if f],
        "pilot_country": registry.market_name(profile.get("pilot_country")),
        "target_countries": [registry.market_name(c) for c in profile.get("target_countries", [])],
        "worldwide_ambition": profile.get("worldwide_ambition", False),
        "city": profile.get("city"),
        "sales_channel": registry.label_for(reg["sales_channels"].get(profile.get("business_type", "online"), []), profile.get("sales_channel")),
        "budget_band": (registry.budget_band(profile.get("budget_band", "")) or {}).get("label"),
        "exact_capital_inr": profile.get("exact_capital_inr"),
        "monthly_ad_budget_inr": profile.get("monthly_ad_budget_inr"),
        "primary_goal": registry.label_for(reg["goals"].get(profile.get("business_stage", "new"), []), profile.get("primary_goal")),
        "currency": profile.get("currency"),
        "unknown_inputs": unknown,
    }


def compose_report(state: dict[str, Any], rt: "AnalysisRuntime") -> dict[str, Any]:
    profile = state.get("profile", {})
    plan = state.get("plan") or {}
    evidence = rt.evidence.items
    observed: list[dict[str, Any]] = []
    headline: list[dict[str, Any]] = []
    listings = state.get("listings", [])

    for key, g in sorted((state.get("price_groups") or {}).items()):
        refs = [l["evidence_ref"] for l in listings if l["focus"] == g["focus"] and l["country"] == g["country"]
                and l["included_in_stats"]][:8]
        if g.get("median") is not None:
            text = (f"{g['focus_label']} in {registry.market_name(g['country'])}: {g['included_count']} sampled listings; "
                    f"advertised prices {g['currency']} {g['min']:,.0f}–{g['max']:,.0f}, median {g['median']:,.0f}"
                    + (f"; median unit price {g['unit_median']:,.2f} {g['unit_basis'].replace('_', ' ')} (n={g['unit_sample_size']})"
                       if g.get("unit_median") is not None else "") + ".")
            observed.append({"type": "price_statistics", "text": text, "refs": refs, "warnings": g.get("warnings", [])})
            headline.append({"kind": "observed", "text": text, "refs": refs[:4]})
        else:
            observed.append({"type": "price_statistics", "text": f"{g['focus_label']}: no verifiable prices.", "refs": [],
                             "warnings": g.get("warnings", [])})

    comps = state.get("competitors", [])
    direct = [c for c in comps if c["relation"] == "direct"]
    if comps:
        text = (f"{len(direct)} direct competitor(s), {sum(c['relation'] == 'marketplace' for c in comps)} marketplace(s) and "
                f"{sum(c['relation'] == 'reference' for c in comps)} reference page(s) found in sampled results "
                f"(not a complete market census).")
        refs = [r for c in direct[:5] for r in c["evidence_refs"][:1]]
        observed.append({"type": "competitors", "text": text, "refs": refs,
                         "examples": [c["name"] for c in direct[:6]]})
        headline.append({"kind": "observed", "text": text, "refs": refs[:4]})

    for country, t in (state.get("trends") or {}).items():
        for s in t.get("summaries", []):
            if s["direction"] != "insufficient_data":
                refs = [r for r in t.get("evidence_refs", []) if evidence.get(r) and evidence[r].normalized.get("query") == s["query"]]
                observed.append({"type": "trend", "text": s["description"] + " (relative interest, not demand)", "refs": refs})
        if t.get("status") == "unavailable":
            observed.append({"type": "trend", "text": f"Google Trends unavailable for {registry.market_name(country)}.", "refs": []})
    news_state = state.get("news") or {}
    for item in news_state.get("items", [])[:8]:
        observed.append({"type": "news", "text": f"{item['title']} — {item.get('source') or 'unknown source'}"
                         + (f" ({item['published_at'][:10]})" if item.get("published_at") else " (date unknown)"),
                         "refs": [item["ref"]], "nature": item["nature"], "topic": item["topic"]})
    if news_state.get("insufficient_evidence"):
        observed.append({"type": "news", "text": "Insufficient current news evidence was found; no developments are asserted.", "refs": []})

    strategies = state.get("strategies", [])
    sims = state.get("simulations", {})
    modeled, strategy_rows, assumptions = [], [], []
    for s in strategies:
        sim = sims.get(s["key"], {})
        base = sim.get("base", {})
        scen = {sc["scenario"]: sc["result"]["operating_result"] for sc in sim.get("scenarios", [])}
        mc = sim.get("monte_carlo", {})
        modeled.append({
            "strategy": s["key"], "name": s["name"], "revision": s["revision"], "currency": base.get("currency"),
            "operating_result": {"bear": scen.get("bear"), "base": scen.get("base"), "bull": scen.get("bull")},
            "contribution_per_order": base.get("contribution_per_order"), "break_even_orders": base.get("break_even_orders"),
            "modelled_orders": base.get("orders"), "monte_carlo_percentiles": mc.get("percentiles"),
            "share_negative": mc.get("prob_negative"), "optimisation": sim.get("optimization", {}).get("status"),
            "label": "MODELLED SCENARIO – depends on labelled assumptions; not a forecast.",
        })
        strategy_rows.append({"key": s["key"], "name": s["name"], "archetype": s["archetype"], "focus": s["focus_label"],
                              "summary": s["summary"], "revision": s["revision"], "revision_notes": s["revision_notes"],
                              "generated_by": s["generated_by"], "evidence_refs": s["evidence_refs"]})
        for a in s["assumptions"]:
            assumptions.append({"strategy": s["key"], **a})
    if modeled:
        best = max(modeled, key=lambda m: (m["operating_result"]["base"] or float("-inf")))
        headline.append({"kind": "modeled", "refs": [],
                         "text": f"Highest modelled base-case monthly operating result: {best['name']} "
                                 f"({best['currency']} {best['operating_result']['base']:,.0f}); "
                                 f"{(best['share_negative'] or 0):.0%} of its Monte Carlo runs are negative. Modelled, not guaranteed."})

    rounds = state.get("critic_rounds", [])
    unresolved = []
    if rounds:
        for ev in rounds[-1]["evaluations"]:
            for c in ev["checks"]:
                if c["status"] == "fail" and c["severity"] == "blocking":
                    unresolved.append({"strategy": ev["strategy_key"], "check": c["id"], "reason": c["reason"]})
    critic_summary = {
        "rounds": [{"round": r["round"], "decision": r["decision"],
                    "results": [{"strategy": e["strategy_key"], "revision": e["revision"], "passed": e["passed"],
                                 "failed": [c["id"] for c in e["checks"] if c["status"] == "fail"],
                                 "warnings": [c["id"] for c in e["checks"] if c["status"] == "warn"]}
                                for e in r["evaluations"]]} for r in rounds],
        "revisions_performed": state.get("revision_count", 0),
        "final_decision": rounds[-1]["decision"] if rounds else "not_run",
        "unresolved_failures": unresolved,
    }
    if rounds:
        headline.append({"kind": "critic", "refs": [],
                         "text": f"Critic ran {len(rounds)} round(s) with {state.get('revision_count', 0)} revision(s); "
                                 f"final decision: {critic_summary['final_decision'].replace('_', ' ')}."})

    questions = [f"{m['label']}: {m['impact']}" for m in plan.get("missing_inputs", [])]
    questions += [f"Unresolved critic check {u['check']} for {u['strategy']}: {u['reason']}" for u in unresolved]
    questions += [f"Skipped search (budget): {t['purpose']}" for t in plan.get("skipped", [])]
    if profile.get("exact_capital_inr") is None:
        questions.append("How much capital is actually available? Provide it to enable capital-fit checks and inventory optimisation.")

    limitations = [
        "Search results are samples; they do not measure market size, market share or competitor sales.",
        "Google Trends values are relative interest indices, not search or sales volumes.",
        "Search-result snippets do not prove claims made on destination websites.",
        "Acquisition costs, unit costs, repeat rates and footfall are scenario assumptions unless you provided them.",
        "Monte Carlo frequencies come from assumed distributions, not calibrated real-world probabilities.",
        "No currency conversion is applied; listings in other currencies are excluded from statistics.",
    ]
    if rt.mode == "demo":
        synthetic = rt.gateway.fixtures.synthetic if rt.gateway.fixtures else True
        limitations.insert(0, "DEMO MODE: all market data comes from saved, synthetic fixtures with fictional brands – "
                              "not real-time market intelligence." if synthetic else
                              "DEMO MODE: market data is replayed from previously recorded SerpApi responses – "
                              "not real-time market intelligence.")
    if rt.llm is None:
        limitations.append("No LLM configured: strategies were generated by the deterministic rule-based generator.")

    used_refs = sorted({r for o in observed for r in o.get("refs", [])} | {r for s in strategies for r in s["evidence_refs"]})
    citations = []
    for ref in used_refs:
        o = evidence.get(ref)
        if o:
            citations.append({"ref": ref, "title": o.title, "url": o.source_url, "engine": o.engine, "query": o.query,
                              "country": o.country, "retrieved_at": o.retrieved_at.isoformat(), "freshness": o.freshness,
                              "data_origin": o.data_origin, "classification": o.classification,
                              "published_at": o.published_at})

    failed = state.get("failed_agents", [])
    failed_searches = [h for h in rt.gateway.history if h.status in {"failed", "fixture_missing", "blocked"}]
    status = "partial" if (failed or failed_searches or unresolved or state.get("status") == "aborted") else "completed"
    report = AnalysisReportContent(
        analysis_id=rt.analysis_id, mode=rt.mode, llm_mode=rt.llm_mode, generated_at=datetime.now(timezone.utc),
        status=status, disclaimer=DISCLAIMER, profile_summary=_profile_summary(profile), headline_findings=headline,
        observed_facts=observed, modeled_scenarios=modeled, strategies=strategy_rows, critic_summary=critic_summary,
        assumptions=assumptions, risks=news_state.get("risks", []), unresolved_questions=questions,
        limitations=limitations, citations=citations, search_usage=rt.gateway.usage(),
        inputs_hash=inputs_hash(profile, rt),
    ).model_dump(mode="json")
    if failed or state.get("status") == "aborted":
        report["degraded_agents"] = failed
        report["warnings"] = state.get("warnings", [])
    return report
