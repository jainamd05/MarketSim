"""LLM-assisted strategy drafting. The LLM proposes narrative and bounded assumptions only;
all numbers are re-derived/simulated by deterministic Python code and checked by the critic."""
from __future__ import annotations

import json

from app.agents.strategy_builder import ARCHETYPES, StrategyContext
from app.llm.adapter import LLMClient, LLMError
from app.schemas.analysis import LLMStrategyDraft, LLMStrategySet

SYSTEM_PROMPT = """You are the Strategy Generation Agent inside MarketSim, a business-strategy simulator.
Produce exactly three DISTINCT strategies as JSON: {"strategies": [ ... ]}.
Use archetypes exactly once each: competitive_pricing, premium_differentiation, bundles_repeat.
Rules:
- Use only the evidence provided. Every claim with kind "market_fact" MUST list evidence_refs taken from allowed_evidence_refs.
  Anything not directly supported must use kind "interpretation".
- Never state market size, market share, sales volumes, customer counts or conversion rates – they are not observed.
- Google Trends values are relative interest, not demand.
- Do NOT calculate revenue, profit or break-even; a deterministic simulator does that.
- price_position must be one of below_median, at_median, above_median.
- proposed_cac is optional; if given it is an assumption and will be challenged by a critic.
- focus must be one of the provided focus values.
Each strategy object fields: archetype, name, focus, summary, positioning, price_logic, channel_choice,
operating_tradeoffs[], advantages[], disadvantages[], claims[{text, kind, evidence_refs[]}], price_position,
proposed_cac (number or null), proposed_units_per_order (number or null). Return JSON only."""


def build_user_prompt(ctx: StrategyContext) -> str:
    p = ctx.profile
    groups = {}
    for focus, g in ctx.price_groups.items():
        refs = [l.evidence_ref for l in ctx.listings if l.focus == focus and l.included_in_stats][:6]
        groups[focus] = {"currency": g.currency, "n": g.included_count, "min": g.min, "p25": g.p25, "median": g.median,
                         "p75": g.p75, "max": g.max, "unit_median": g.unit_median, "unit_basis": g.unit_basis,
                         "evidence_refs": refs}
    trends = [s.model_dump() | {"focus": ctx.trends.query_focus.get(s.query)} for s in (ctx.trends.summaries if ctx.trends else [])]
    competitors = [{"name": c.name, "relation": c.relation, "focuses": c.focuses, "evidence_refs": c.evidence_refs[:3],
                    "tags": [t.tag for t in c.tags]} for c in ctx.competitors[:10]]
    news = [{"title": n.title, "topic": n.topic, "nature": n.nature, "ref": n.ref} for n in (ctx.news.items[:6] if ctx.news else [])]
    payload = {
        "business": {"type": p.business_type, "stage": p.business_stage, "category": p.category,
                     "country": ctx.country, "currency": p.currency, "sales_channel": p.sales_channel,
                     "goal": p.primary_goal, "monthly_ad_budget": p.monthly_ad_budget_inr,
                     "capital_known": p.exact_capital_inr is not None},
        "focuses": [{"value": f.value, "label": f.label} for f in ctx.focuses],
        "price_statistics_by_focus": groups,
        "trend_summaries": trends,
        "competitors": competitors,
        "news": news,
        "allowed_evidence_refs": sorted(ctx.evidence_refs),
    }
    return json.dumps(payload, ensure_ascii=False, default=str)


def draft_strategies(llm: LLMClient, ctx: StrategyContext) -> dict[str, LLMStrategyDraft]:
    result = llm.structured(SYSTEM_PROMPT, build_user_prompt(ctx), LLMStrategySet, retries=1)
    drafts = {d.archetype: d for d in result.strategies}
    if set(drafts) != set(ARCHETYPES):
        raise LLMError("LLM did not return the three required distinct archetypes.")
    return drafts
