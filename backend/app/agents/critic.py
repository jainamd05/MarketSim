"""Strategy Critic & Validation: structured pass/fail checks and targeted revisions.

The critic never writes prose praise. Each check returns pass / fail / warn /
not_applicable with a reason. Blocking failures produce RevisionRequests that the
revision node applies, after which the strategy is re-simulated (max 2 revisions).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.agents.strategy_builder import defaults_for
from app.onboarding import registry
from app.schemas.analysis import (
    Assumption, Claim, CriticCheck, CriticEvaluationResult, Observation, OnlineSimInputs, PriceGroupStats,
    RevisionRequest, Strategy, StrategySimulation,
)
from app.schemas.profile import BusinessProfileIn

MAX_REVISIONS = 2
OPTIMISTIC_CAC_TO_AOV = 0.15
LLM_CAC_FLOOR_RATIO = 0.5


@dataclass
class CriticContext:
    profile: BusinessProfileIn
    evidence: dict[str, Observation]
    price_groups: dict[str, PriceGroupStats]
    mode: str


def _check(id_: str, label: str, status: str, severity: str, reason: str, refs: list[str] | None = None) -> CriticCheck:
    return CriticCheck(id=id_, label=label, status=status, severity=severity, reason=reason, evidence_refs=refs or [])


def evaluate(strategy: Strategy, sim: StrategySimulation, ctx: CriticContext, round_no: int,
             all_strategies: list[Strategy]) -> CriticEvaluationResult:
    checks: list[CriticCheck] = []
    requests: list[RevisionRequest] = []
    inp = strategy.sim_inputs
    base = sim.base

    def fail(check: CriticCheck, instruction: str, target: str) -> None:
        checks.append(check)
        requests.append(RevisionRequest(strategy_key=strategy.key, check_id=check.id, instruction=instruction, target_field=target))

    # 1) Every factual market claim is supported by existing evidence
    unsupported = [c for c in strategy.claims if c.kind == "market_fact" and
                   (not c.evidence_refs or any(r not in ctx.evidence for r in c.evidence_refs))]
    if unsupported:
        fail(_check("evidence_support", "Market claims cite existing evidence", "fail", "blocking",
                    f"{len(unsupported)} market claim(s) lack valid evidence references: "
                    + "; ".join(c.text[:80] for c in unsupported[:3])),
             "Remove unsupported market claims or relabel them as interpretation.", "claims")
    else:
        n = sum(1 for c in strategy.claims if c.kind == "market_fact")
        checks.append(_check("evidence_support", "Market claims cite existing evidence", "pass", "blocking",
                             f"All {n} market claim(s) reference stored evidence.",
                             sorted({r for c in strategy.claims for r in c.evidence_refs})[:6]))

    # 2) Freshness of the evidence for its purpose
    refs = [ctx.evidence[r] for r in strategy.evidence_refs if r in ctx.evidence]
    if not refs:
        checks.append(_check("data_freshness", "Evidence is current enough", "warn", "advisory",
                             "No market evidence is referenced; strategy relies on assumptions only."))
    elif any(o.freshness == "demo_fixture" for o in refs):
        checks.append(_check("data_freshness", "Evidence is current enough", "warn", "advisory",
                             "Evidence comes from saved DEMO fixtures, not current market data. Re-run in LIVE mode before deciding."))
    elif any(o.freshness == "stale" for o in refs):
        checks.append(_check("data_freshness", "Evidence is current enough", "warn", "advisory",
                             "Some referenced evidence is older than 180 days."))
    else:
        checks.append(_check("data_freshness", "Evidence is current enough", "pass", "advisory",
                             "Referenced evidence was retrieved in this analysis (live or within cache TTL)."))

    # 3) Currency consistency
    group = ctx.price_groups.get(strategy.focus)
    market_price_used = any(a.source == "market_evidence" and a.key in {"selling_price", "average_transaction_value"}
                            for a in strategy.assumptions)
    if inp.currency != ctx.profile.currency:
        fail(_check("currency_consistency", "Single, consistent currency", "fail", "blocking",
                    f"Simulation currency {inp.currency} differs from profile currency {ctx.profile.currency}."),
             "Express all simulation inputs in the profile currency.", "sim_inputs.currency")
    elif market_price_used and (group is None or group.currency != inp.currency):
        fail(_check("currency_consistency", "Single, consistent currency", "fail", "blocking",
                    f"Price evidence currency {group.currency if group else 'unknown'} does not match simulation currency "
                    f"{inp.currency}; no FX conversion is applied."),
             "Replace market-derived prices with prices in the profile currency.", "selling_price")
    else:
        checks.append(_check("currency_consistency", "Single, consistent currency", "pass", "blocking",
                             f"All inputs are in {inp.currency}; mismatched-currency listings were excluded from statistics."))

    # 4) Unit / pack-size normalisation
    normalised = any(a.key == "market_median_price" and "pack-normalised" in a.rationale for a in strategy.assumptions)
    if group and market_price_used:
        if normalised:
            checks.append(_check("unit_consistency", "Prices compared on normalised pack sizes", "pass", "advisory",
                                 f"Price anchors use {group.unit_sample_size} listings normalised {group.unit_basis.replace('_', ' ')} "
                                 "and scaled to the typical pack; ambiguous sizes excluded."))
        else:
            checks.append(_check("unit_consistency", "Prices compared on normalised pack sizes", "warn", "advisory",
                                 "Too few listings with verified pack sizes; price anchors are not normalised per unit."))
    else:
        checks.append(_check("unit_consistency", "Prices compared on normalised pack sizes", "not_applicable", "advisory",
                             "No market-derived price is used."))

    # 5) Financial model constraints
    if isinstance(inp, OnlineSimInputs):
        invalid = []
        if inp.unit_cost >= inp.selling_price:
            invalid.append("unit cost ≥ selling price")
        if inp.return_rate_pct > 40:
            invalid.append("return allowance above 40%")
        if inp.platform_fee_pct > 50:
            invalid.append("platform fees above 50%")
        if invalid:
            fail(_check("input_validity", "Inputs within model constraints", "fail", "blocking", "; ".join(invalid) + "."),
                 "Bring inputs within valid ranges.", "sim_inputs")
        else:
            checks.append(_check("input_validity", "Inputs within model constraints", "pass", "blocking",
                                 "Unit cost below price; fees and return allowance within bounds."))
    if base.contribution_per_order <= 0:
        fail(_check("contribution_margin", "Positive contribution per order (base case)", "fail", "blocking",
                    f"Base-case contribution is {inp.currency} {base.contribution_per_order:,.2f} per order: variable costs "
                    f"({base.variable_cost_per_order:,.2f}) exceed order value ({base.average_order_value:,.2f})."),
             "Raise order value (multi-pack or price toward the sampled median) so contribution is positive.",
             "units_per_order/selling_price")
    else:
        checks.append(_check("contribution_margin", "Positive contribution per order (base case)", "pass", "blocking",
                             f"Contribution {inp.currency} {base.contribution_per_order:,.2f} per order "
                             f"({base.contribution_margin_pct:.1f}% of order value)."))

    # 6) Acquisition-cost plausibility
    if isinstance(inp, OnlineSimInputs) and inp.monthly_ad_budget > 0:
        aov = inp.selling_price * inp.units_per_order
        cac_a = next((a for a in strategy.assumptions if a.key == "cac"), None)
        default_cac = defaults_for(inp.currency)["cac"]["marketplaces"]
        if cac_a and cac_a.source == "llm_proposed" and inp.cac < LLM_CAC_FLOOR_RATIO * default_cac:
            fail(_check("cac_plausibility", "Acquisition cost is not unusually optimistic", "fail", "blocking",
                        f"LLM-proposed CAC {inp.currency} {inp.cac:,.0f} is below {LLM_CAC_FLOOR_RATIO:.0%} of the conservative "
                        f"default ({default_cac:,.0f}). Unsupported by evidence."),
                 "Replace the proposed CAC with the conservative channel default.", "cac")
        elif inp.cac / aov < OPTIMISTIC_CAC_TO_AOV:
            checks.append(_check("cac_plausibility", "Acquisition cost is not unusually optimistic", "warn", "advisory",
                                 f"CAC is only {inp.cac / aov:.0%} of order value – optimistic for a new brand (review heuristic)."))
        else:
            checks.append(_check("cac_plausibility", "Acquisition cost is not unusually optimistic", "pass", "advisory",
                                 f"CAC {inp.currency} {inp.cac:,.0f} = {inp.cac / aov:.0%} of order value; labelled as an assumption."))
    else:
        checks.append(_check("cac_plausibility", "Acquisition cost is not unusually optimistic", "not_applicable", "advisory",
                             "No paid acquisition modelled."))

    # 7) Capital fit (known capital only) and 8) budget band
    cap = base.capital_check
    if cap.status == "exceeds":
        fail(_check("capital_fit", "Investment within known capital", "fail", "blocking", cap.note),
             "Reduce initial inventory so total investment fits within known capital.", "initial_investment")
    elif cap.status == "within":
        checks.append(_check("capital_fit", "Investment within known capital", "pass", "blocking", cap.note))
    else:
        checks.append(_check("capital_fit", "Investment within known capital", "warn", "advisory",
                             "Exact capital is unknown, so the investment cannot be verified against it."))
    band = registry.budget_band(ctx.profile.budget_band) or {}
    investment = inp.initial_investment
    if investment is not None and inp.currency == "INR" and band.get("max_inr") is not None and investment > band["max_inr"]:
        fail(_check("budget_band_fit", "Investment consistent with stated budget band", "fail", "blocking",
                    f"Initial investment ₹{investment:,.0f} exceeds the top of the '{band['label']}' band."),
             "Reduce initial inventory to fit within the stated budget band.", "initial_investment")
    elif investment is not None and inp.currency == "INR" and band.get("min_inr"):
        checks.append(_check("budget_band_fit", "Investment consistent with stated budget band", "pass", "advisory",
                             f"Initial investment ₹{investment:,.0f} vs band '{band['label']}' (lower bound ₹{band['min_inr']:,.0f}); "
                             "the band is not treated as an exact amount."))
    else:
        checks.append(_check("budget_band_fit", "Investment consistent with stated budget band", "not_applicable", "advisory",
                             "Budget band undecided or currency is not INR."))

    # 9) Break-even feasibility and 10) downside risk (advisory)
    total = base.orders.get("total", 0.0)
    if base.break_even_orders is not None and total > 0 and base.break_even_orders > 3 * total:
        checks.append(_check("break_even_feasibility", "Break-even within reach of modelled volume", "warn", "advisory",
                             f"Break-even needs {base.break_even_orders:,} orders/month vs {total:,.0f} modelled."))
    elif base.break_even_orders is not None:
        checks.append(_check("break_even_feasibility", "Break-even within reach of modelled volume", "pass", "advisory",
                             f"Break-even {base.break_even_orders:,} vs {total:,.0f} modelled per month."))
    else:
        checks.append(_check("break_even_feasibility", "Break-even within reach of modelled volume", "fail" if base.contribution_per_order <= 0 else "warn",
                             "advisory", base.break_even_note))
    mc = sim.monte_carlo
    checks.append(_check("downside_risk", "Downside risk acknowledged", "warn" if mc.prob_negative > 0.5 else "pass", "advisory",
                         f"{mc.prob_negative:.0%} of {mc.iterations} simulated scenarios have a negative operating result "
                         "(from assumed distributions, not calibrated probabilities)."))

    # 11) Regulatory / fulfilment / inventory considerations
    flags = (registry.category(ctx.profile.category) or {}).get("risk_flags", [])
    text = " ".join(strategy.operating_tradeoffs + strategy.disadvantages).lower()
    missing = []
    if flags and not any(k in text for k in ("compliance", "fssai", "regulat", "label", "shelf", "certif", "warranty", "return")):
        missing.append("category regulatory/handling risks")
    if isinstance(inp, OnlineSimInputs) and inp.shipping_cost_per_order <= 0:
        missing.append("fulfilment cost")
    if inp.initial_investment is None:
        missing.append("inventory investment")
    if missing:
        checks.append(_check("operational_considerations", "Regulatory, fulfilment and inventory considered", "warn", "advisory",
                             "Missing: " + ", ".join(missing) + "."))
    else:
        checks.append(_check("operational_considerations", "Regulatory, fulfilment and inventory considered", "pass", "advisory",
                             "Strategy accounts for category risks, fulfilment cost and inventory investment."))

    # 12) Distinctness of the strategy set
    same = [s.key for s in all_strategies if s.key != strategy.key and s.archetype == strategy.archetype]
    checks.append(_check("distinctness", "Distinct from other strategies", "fail" if same else "pass", "advisory",
                         f"Duplicates archetype of {same}." if same else f"Unique archetype '{strategy.archetype}'."))

    passed = not any(c.status == "fail" and c.severity == "blocking" for c in checks)
    return CriticEvaluationResult(round=round_no, strategy_key=strategy.key, revision=strategy.revision, passed=passed,
                                  checks=checks, revision_requests=requests if not passed else [])


# ----------------------------------------------------------------- revisions
def _set_assumption(strategy: Strategy, key: str, value: Any, note: str, source: str = "scenario_assumption") -> None:
    for a in strategy.assumptions:
        if a.key == key:
            a.value = value
            a.source = source
            a.rationale = f"{a.rationale} REVISED: {note}"
            return
    strategy.assumptions.append(Assumption(key=key, label=key.replace("_", " "), value=value, unit="", source=source,
                                           rationale=f"REVISED: {note}"))


def revise(strategy: Strategy, requests: list[RevisionRequest], ctx: CriticContext) -> tuple[Strategy, list[str]]:
    s = strategy.model_copy(deep=True)
    s.revision += 1
    notes: list[str] = []
    data = s.sim_inputs.model_dump()
    median_a = next((a for a in s.assumptions if a.key == "market_median_price"), None)
    median_ref = float(median_a.value) if median_a and isinstance(median_a.value, (int, float)) else None
    for req in requests:
        if req.check_id == "contribution_margin" and s.sim_inputs.model == "online":
            if data["units_per_order"] < 2:
                data["units_per_order"] = 2.0
                data["packaging_cost_per_order"] = round(data["packaging_cost_per_order"] * 1.4, 2)
                _set_assumption(s, "units_per_order", 2.0, "Moved to 2-unit multi-packs so shipping and packaging are spread over more units.")
                _set_assumption(s, "packaging_cost_per_order", data["packaging_cost_per_order"], "Multi-pack packaging (+40%).")
                notes.append("Contribution was negative: switched to 2-unit multi-packs to raise order value.")
            elif median_ref is not None and data["selling_price"] < median_ref:
                data["selling_price"] = median_ref
                _set_assumption(s, "selling_price", median_ref, "Raised to the sampled median price for the typical pack.",
                                "market_evidence")
                notes.append(f"Contribution still negative: price raised to the sampled median ({median_ref:,.0f}).")
            else:
                notes.append("UNRESOLVED: contribution negative even at median price; requires lower unit cost (supplier quotes).")
        elif req.check_id == "contribution_margin":
            data["cogs_pct"] = max(0.0, min(data["cogs_pct"], 100 - data["card_fee_pct"] - data["shrinkage_pct"] - 10))
            _set_assumption(s, "cogs_pct", data["cogs_pct"], "Cost-of-goods ratio capped to leave a 10% contribution.")
            notes.append("Capped cost-of-goods ratio to restore positive contribution.")
        elif req.check_id == "evidence_support":
            fixed: list[Claim] = []
            for c in s.claims:
                if c.kind == "market_fact" and (not c.evidence_refs or any(r not in ctx.evidence for r in c.evidence_refs)):
                    fixed.append(Claim(kind="interpretation", text=f"Unverified (no supporting evidence): {c.text}",
                                       evidence_refs=[r for r in c.evidence_refs if r in ctx.evidence]))
                else:
                    fixed.append(c)
            s.claims = fixed
            notes.append("Relabelled unsupported market claims as unverified interpretation.")
        elif req.check_id == "cac_plausibility":
            channel = "marketplaces" if data.get("platform_fee_pct", 0) >= 10 else "own_website"
            data["cac"] = defaults_for(data["currency"])["cac"][channel]
            _set_assumption(s, "cac", data["cac"], "Replaced optimistic CAC with the conservative channel default.")
            notes.append(f"Replaced optimistic CAC with conservative default {data['cac']:,.0f}.")
        elif req.check_id in {"capital_fit", "budget_band_fit"}:
            limit = data.get("available_capital")
            band = registry.budget_band(ctx.profile.budget_band) or {}
            if req.check_id == "budget_band_fit" and band.get("max_inr"):
                limit = band["max_inr"] if limit is None else min(limit, band["max_inr"])
            if limit is not None and data.get("initial_investment"):
                factor = (0.95 * limit) / data["initial_investment"]
                data["initial_investment"] = round(0.95 * limit, 0)
                for item in s.product_mix:
                    if item.max_monthly_units:
                        item.max_monthly_units = max(1, int(item.max_monthly_units * factor))
                _set_assumption(s, "initial_investment", data["initial_investment"], "Inventory scaled down to fit the capital limit.")
                notes.append("Scaled initial inventory down to fit within the capital limit.")
        elif req.check_id == "input_validity" and s.sim_inputs.model == "online":
            data["return_rate_pct"] = min(data["return_rate_pct"], 40.0)
            data["platform_fee_pct"] = min(data["platform_fee_pct"], 50.0)
            if data["unit_cost"] >= data["selling_price"]:
                notes.append("UNRESOLVED: unit cost is not below selling price; needs real supplier costs.")
            notes.append("Clamped out-of-range inputs.")
        elif req.check_id == "currency_consistency":
            notes.append("UNRESOLVED: prices must be provided in the profile currency; no FX conversion is invented.")
    s.sim_inputs = type(s.sim_inputs)(**data)
    if s.sim_inputs.model == "online":
        price, units = s.sim_inputs.selling_price, s.sim_inputs.units_per_order
        for item in s.product_mix:
            if item.target_price and strategy.sim_inputs.model == "online" and strategy.sim_inputs.selling_price:
                item.target_price = round(item.target_price * price / strategy.sim_inputs.selling_price, 0)
        s.price_logic = f"{s.price_logic} Revised: {units:g} unit(s) per order at {s.sim_inputs.currency} {price:,.0f} per unit."
    s.revision_notes = [*s.revision_notes, *notes]
    return s, notes
