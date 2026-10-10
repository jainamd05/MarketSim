"""Builds three distinct, simulatable strategies from evidence + explicit assumptions.

Every numeric input is an :class:`Assumption` labelled with its source:
``user_input`` (from the profile), ``market_evidence`` (computed from sampled
listings, with evidence refs), ``scenario_assumption`` (an editable modelling
default, never presented as market data) or ``llm_proposed``.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from app.schemas.analysis import (
    Assumption, Claim, CompetitorEntry, FocusSpec, Listing, LLMStrategyDraft, NewsResult, OnlineSimInputs,
    PhysicalSimInputs, PriceGroupStats, ProductMixItem, Strategy, TrendsResult,
)
from app.schemas.profile import BusinessProfileIn
from app.simulation.finance import simulate

# Illustrative modelling defaults – shown to users as editable scenario assumptions, never as market data.
SCENARIO_DEFAULTS: dict[str, dict[str, Any]] = {
    "INR": {"cac": {"own_website": 450.0, "marketplaces": 300.0}, "shipping": 70.0, "packaging": 25.0,
            "fee_pct": {"own_website": 2.5, "marketplaces": 15.0}, "platform_monthly": 3000.0, "misc_fixed": 5000.0,
            "setup": 75000.0, "ad_budget": 20000.0, "placeholder_price": 500.0,
            "physical": {"rent": 60000.0, "staff": 30000.0, "utilities": 8000.0, "marketing": 10000.0, "atv": 450.0}},
    "USD": {"cac": {"own_website": 30.0, "marketplaces": 20.0}, "shipping": 6.0, "packaging": 1.5,
            "fee_pct": {"own_website": 3.0, "marketplaces": 15.0}, "platform_monthly": 39.0, "misc_fixed": 300.0,
            "setup": 2500.0, "ad_budget": 1000.0, "placeholder_price": 25.0,
            "physical": {"rent": 4000.0, "staff": 6000.0, "utilities": 500.0, "marketing": 500.0, "atv": 25.0}},
    "GBP": {"cac": {"own_website": 25.0, "marketplaces": 18.0}, "shipping": 4.5, "packaging": 1.2,
            "fee_pct": {"own_website": 2.5, "marketplaces": 15.0}, "platform_monthly": 30.0, "misc_fixed": 250.0,
            "setup": 2000.0, "ad_budget": 800.0, "placeholder_price": 20.0,
            "physical": {"rent": 3000.0, "staff": 5000.0, "utilities": 400.0, "marketing": 400.0, "atv": 20.0}},
    "AED": {"cac": {"own_website": 110.0, "marketplaces": 75.0}, "shipping": 20.0, "packaging": 5.0,
            "fee_pct": {"own_website": 2.5, "marketplaces": 15.0}, "platform_monthly": 150.0, "misc_fixed": 1000.0,
            "setup": 9000.0, "ad_budget": 3500.0, "placeholder_price": 90.0,
            "physical": {"rent": 15000.0, "staff": 12000.0, "utilities": 1500.0, "marketing": 1500.0, "atv": 90.0}},
}
RETURN_RATE_DEFAULT = {"food_beverages": 3.0, "clothing_fashion": 20.0, "electronics_gaming": 8.0,
                       "beauty_personal_care": 5.0, "home_lifestyle": 6.0, "health_wellness": 4.0}
COST_RATIO = {"competitive_pricing": 0.45, "premium_differentiation": 0.55, "bundles_repeat": 0.45}
ARCHETYPES = ("competitive_pricing", "premium_differentiation", "bundles_repeat")
ARCHETYPE_NAMES = {"competitive_pricing": "Competitive Pricing", "premium_differentiation": "Premium Differentiation",
                   "bundles_repeat": "Bundles & Repeat Purchase"}


def defaults_for(currency: str) -> dict[str, Any]:
    return SCENARIO_DEFAULTS.get(currency, SCENARIO_DEFAULTS["INR"])


@dataclass
class StrategyContext:
    profile: BusinessProfileIn
    focuses: list[FocusSpec]
    country: str
    market_currency: str | None
    price_groups: dict[str, PriceGroupStats]
    listings: list[Listing]
    trends: TrendsResult | None
    competitors: list[CompetitorEntry]
    news: NewsResult | None
    evidence_refs: set[str] = field(default_factory=set)

    @property
    def currency(self) -> str:
        return self.profile.currency

    def group(self, focus: str) -> PriceGroupStats | None:
        g = self.price_groups.get(focus)
        return g if g and g.median is not None else None

    def trend_for(self, focus: str):
        if not self.trends:
            return None, None
        term = next((q for q, f in self.trends.query_focus.items() if f == focus), None)
        summary = next((s for s in self.trends.summaries if s.query == term), None)
        return term, summary


# ----------------------------------------------------------------- selection
def assign_focuses(ctx: StrategyContext) -> dict[str, str]:
    """Distinct focus per archetype when several focuses are compared."""
    values = [f.value for f in ctx.focuses] or ["custom"]
    if len(values) == 1:
        return {a: values[0] for a in ARCHETYPES}
    remaining = list(values)

    def dispersion(v: str) -> float:
        """Premium headroom: spread of pack-normalised unit prices (absolute quartiles as fallback)."""
        g = ctx.group(v)
        if g and g.unit_max and g.unit_median and g.unit_sample_size >= 4:
            return g.unit_max / g.unit_median
        return (g.p75 / g.p25) if g and g.p25 and g.p75 else 0.0

    def interest(v: str) -> float:
        _, s = ctx.trend_for(v)
        return s.mean if s and s.mean is not None else -1.0

    def momentum(v: str) -> float:
        _, s = ctx.trend_for(v)
        return s.change_pct if s and s.change_pct is not None else -1e9

    out: dict[str, str] = {}
    out["premium_differentiation"] = max(remaining, key=lambda v: (dispersion(v), -values.index(v)))
    remaining.remove(out["premium_differentiation"])
    out["competitive_pricing"] = max(remaining, key=lambda v: (interest(v), -values.index(v)))
    remaining.remove(out["competitive_pricing"])
    out["bundles_repeat"] = max(remaining, key=lambda v: (momentum(v), -values.index(v))) if remaining else out["competitive_pricing"]
    return out


def _channel_for(archetype: str, sales_channel: str) -> str:
    if sales_channel == "own_website":
        return "own_website"
    if sales_channel == "marketplaces":
        return "marketplaces"
    return "marketplaces" if archetype == "competitive_pricing" else "own_website"


_BASIS_UNIT = {"per_100g": "g", "per_100ml": "ml", "per_unit": "count"}


def _typical_pack(ctx: StrategyContext, focus: str) -> tuple[str, float, str] | None:
    """Median single-pack size among verified listings, in the group's unit-price basis."""
    g = ctx.group(focus)
    unit = _BASIS_UNIT.get(g.unit_basis) if g and g.unit_basis else None
    if unit is None:
        return None
    sizes = sorted(l.quantity.amount for l in ctx.listings
                   if l.focus == focus and l.included_in_stats and l.quantity.status == "parsed"
                   and l.quantity.pack_count == 1 and l.quantity.base_unit == unit and l.quantity.amount)
    if not sizes:
        return None
    amount = sizes[len(sizes) // 2]
    return (f"{amount:g} {unit}" if unit != "count" else f"{amount:g} units"), amount, unit


def price_anchors(ctx: StrategyContext, focus: str) -> dict[str, Any] | None:
    """Price anchors for the typical pack. Uses pack-normalised unit-price quartiles when at least four
    listings have verified sizes; otherwise falls back to absolute advertised-price quartiles (flagged)."""
    g = ctx.group(focus)
    if g is None:
        return None
    pack = _typical_pack(ctx, focus)
    if pack and g.unit_sample_size >= 4 and g.unit_p25 and g.unit_p75 and g.unit_median:
        label, amount, unit = pack
        factor = amount / 100 if unit in {"g", "ml"} else amount
        return {"p25": g.unit_p25 * factor, "median": g.unit_median * factor, "p75": g.unit_p75 * factor,
                "normalised": True, "pack": label,
                "basis": f"pack-normalised: sampled unit prices ({g.unit_basis.replace('_', ' ')}, n={g.unit_sample_size}) × {label}"}
    return {"p25": g.p25, "median": g.median, "p75": g.p75, "normalised": False, "pack": pack[0] if pack else None,
            "basis": f"absolute advertised prices (n={g.included_count}); pack sizes NOT normalised"}


def _refs(group: PriceGroupStats | None, ctx: StrategyContext, focus: str, n: int = 6) -> list[str]:
    if group is None:
        return []
    return [l.evidence_ref for l in ctx.listings if l.focus == focus and l.included_in_stats][:n]


# ------------------------------------------------------------------- builder
def build_strategy(ctx: StrategyContext, archetype: str, focus: str, key: str,
                   draft: LLMStrategyDraft | None = None) -> Strategy:
    p = ctx.profile
    cur = ctx.currency
    d = defaults_for(cur)
    focus_spec = next((f for f in ctx.focuses if f.value == focus), None)
    focus_label = focus_spec.label if focus_spec else focus
    g = ctx.group(focus)
    price_refs = _refs(g, ctx, focus)
    currency_ok = g is not None and (g.currency == cur)
    assumptions: list[Assumption] = []
    claims: list[Claim] = []

    def A(key_: str, label: str, value: Any, unit: str, source: str, rationale: str, refs: list[str] | None = None) -> Any:
        assumptions.append(Assumption(key=key_, label=label, value=value, unit=unit, source=source,
                                      rationale=rationale, evidence_refs=refs or []))
        return value

    position = draft.price_position if draft else {"competitive_pricing": "below_median",
                                                     "premium_differentiation": "above_median",
                                                     "bundles_repeat": "at_median"}[archetype]
    multiplier = {"below_median": "p25", "at_median": "median", "above_median": "p75x1.1"}[position]

    # ----- price basis
    anchors = price_anchors(ctx, focus) if currency_ok else None
    if anchors:
        A("market_median_price", "Sampled median price for the typical pack", round(anchors["median"], 0), f"{cur} / pack",
          "market_evidence", f"Reference price from {anchors['basis']}.", price_refs)

    if p.business_type == "online":
        base_price: float
        if anchors:
            anchor = {"p25": anchors["p25"], "median": anchors["median"], "p75x1.1": anchors["p75"] * 1.10}[multiplier]
            base_price = round(float(anchor), 0)
            position_text = {"p25": "Sampled 25th-percentile", "median": "Sampled median",
                             "p75x1.1": "10% above the sampled 75th-percentile"}[multiplier]
            src, why, refs = "market_evidence", (
                f"{position_text} price for {focus_label} in {ctx.country}; {anchors['basis']}."), price_refs
        elif p.selling_price:
            ratio = {"p25": 0.85, "median": 1.0, "p75x1.1": 1.30}[multiplier]
            base_price = round(p.selling_price * ratio, 0)
            src, why, refs = "user_input", f"Your stated selling price scaled ×{ratio} for this positioning.", []
        else:
            base_price = d["placeholder_price"]
            src, why, refs = "scenario_assumption", (
                "PLACEHOLDER: no comparable market price in the profile currency and no selling price provided. "
                "Edit in the What-If simulator."), []
        units = 2.0 if archetype == "bundles_repeat" else 1.0
        if draft and draft.proposed_units_per_order:
            units = draft.proposed_units_per_order
        unit_price = round(base_price * (0.92 if archetype == "bundles_repeat" else 1.0), 0)
        A("selling_price", "Selling price per unit", unit_price, f"{cur} / unit", src,
          why + (" Includes an 8% bundle discount." if archetype == "bundles_repeat" else ""), refs)
        A("units_per_order", "Units per order", units, "units / order",
          "llm_proposed" if draft and draft.proposed_units_per_order else "scenario_assumption",
          "Bundle of two units per order." if units == 2 else "Single-unit orders.")

        if p.product_unit_cost is not None:
            unit_cost = A("unit_cost", "Landed unit cost", p.product_unit_cost, f"{cur} / unit", "user_input",
                          "From your profile.")
        else:
            reference = anchors["median"] if anchors else unit_price
            unit_cost = A("unit_cost", "Landed unit cost", round(reference * COST_RATIO[archetype], 0), f"{cur} / unit",
                          "scenario_assumption",
                          f"Assumed at {COST_RATIO[archetype]:.0%} of the {'sampled median' if anchors else 'selling'} "
                          "price. Replace with supplier quotes.")
        channel = _channel_for(archetype, p.sales_channel)
        packaging = A("packaging_cost_per_order", "Packaging per order",
                      d["packaging"] * (1.4 if units >= 2 else 1.0) * (1.5 if archetype == "premium_differentiation" else 1.0),
                      f"{cur} / order", "scenario_assumption", "Illustrative packaging cost; premium packaging costs more.")
        shipping = (A("shipping_cost_per_order", "Shipping per order", p.shipping_cost, f"{cur} / order", "user_input", "From your profile.")
                    if p.shipping_cost is not None else
                    A("shipping_cost_per_order", "Shipping per order", d["shipping"], f"{cur} / order", "scenario_assumption",
                      "Illustrative domestic shipping cost per order."))
        fee = (A("platform_fee_pct", "Platform / payment fees", p.payment_or_platform_fees, "% of order value", "user_input", "From your profile.")
               if p.payment_or_platform_fees is not None else
               A("platform_fee_pct", "Platform / payment fees", d["fee_pct"][channel], "% of order value", "scenario_assumption",
                 "Marketplace commission + fees (illustrative)." if channel == "marketplaces" else "Payment-gateway fee (illustrative)."))
        ret = (A("return_rate_pct", "Return / refund allowance", p.expected_return_cost, "% of order value", "user_input", "From your profile.")
               if p.expected_return_cost is not None else
               A("return_rate_pct", "Return / refund allowance", RETURN_RATE_DEFAULT.get(p.category, 5.0), "% of order value",
                 "scenario_assumption", "Category-level illustrative return allowance."))
        ad_budget = (A("monthly_ad_budget", "Monthly advertising budget", p.monthly_ad_budget_inr, f"{cur} / month", "user_input", "From your profile.")
                     if p.monthly_ad_budget_inr is not None else
                     A("monthly_ad_budget", "Monthly advertising budget", d["ad_budget"], f"{cur} / month", "scenario_assumption",
                       "No ad budget provided; illustrative budget used."))
        if draft and draft.proposed_cac:
            cac = A("cac", "Advertising cost per ad-acquired order (CAC)", draft.proposed_cac, f"{cur} / order", "llm_proposed",
                    "Proposed by the LLM strategist; checked by the critic against conservative defaults.")
        else:
            cac = A("cac", "Advertising cost per ad-acquired order (CAC)", d["cac"][channel], f"{cur} / order", "scenario_assumption",
                    f"Illustrative {channel.replace('_', ' ')} acquisition cost. NOT derived from Google Trends or market data; "
                    "replace with your campaign results.")
        ad_orders = ad_budget / cac if cac else 0.0
        organic_share = {"competitive_pricing": 0.20, "premium_differentiation": 0.10, "bundles_repeat": 0.10}[archetype]
        organic = A("organic_orders", "Organic orders per month", round(ad_orders * organic_share, 1), "orders / month",
                    "scenario_assumption", f"{organic_share:.0%} of modelled ad-acquired orders (steady-state month).")
        repeat = A("repeat_orders", "Repeat orders per month", round(ad_orders * (0.15 if archetype == "bundles_repeat" else 0.0), 1),
                   "orders / month", "scenario_assumption",
                   "15% of ad-acquired customers reorder monthly (subscription/bundle positioning)." if archetype == "bundles_repeat"
                   else "No repeat orders assumed for this strategy.")
        fixed_parts = []
        if p.monthly_fixed_costs is not None:
            fixed_parts.append(p.monthly_fixed_costs)
        if p.website_platform_cost_inr is not None:
            fixed_parts.append(p.website_platform_cost_inr)
        if fixed_parts:
            fixed = A("fixed_costs_monthly", "Fixed operating costs", sum(fixed_parts), f"{cur} / month", "user_input", "From your profile.")
        else:
            fixed = A("fixed_costs_monthly", "Fixed operating costs", d["platform_monthly"] + d["misc_fixed"], f"{cur} / month",
                      "scenario_assumption", "Website/platform subscription + miscellaneous (owner-operated, no salaries).")
        monthly_units = (ad_orders + organic + repeat) * units
        inventory = math.ceil(monthly_units * 2) * unit_cost
        investment = A("initial_investment", "Initial investment (2 months inventory + setup)", round(inventory + d["setup"], 0),
                       cur, "scenario_assumption", "Two months of modelled units at unit cost plus illustrative setup cost "
                       "(branding, packaging design, registrations, website).")
        capital = p.exact_capital_inr if cur == "INR" else None
        A("available_capital", "Available capital", capital, cur, "user_input" if capital is not None else "scenario_assumption",
          "From your profile." if capital is not None else "UNKNOWN – the budget band is not treated as an exact amount.")
        sim_inputs = OnlineSimInputs(currency=cur, selling_price=unit_price, units_per_order=units, unit_cost=unit_cost,
                                     packaging_cost_per_order=round(packaging, 2), shipping_cost_per_order=shipping,
                                     platform_fee_pct=fee, return_rate_pct=ret, monthly_ad_budget=ad_budget, cac=cac,
                                     organic_orders=organic, repeat_orders=repeat, fixed_costs_monthly=fixed,
                                     initial_investment=investment, available_capital=capital)
    else:
        sim_inputs, unit_price, unit_cost, channel = _physical_inputs(ctx, archetype, g, currency_ok, price_refs, A)
        units = 1.0

    # ----- product mix
    typical = _typical_pack(ctx, focus)
    pack = typical[0] if typical else "standard pack"
    mix_templates = {
        "competitive_pricing": [(f"Core {pack} (value-priced)", pack, 1.0, 1.0, 70), (f"Twin pack 2 × {pack}", f"2 × {pack}", 1.9, 2.0, 30)],
        "premium_differentiation": [(f"Premium {pack}", pack, 1.0, 1.0, 60), ("Gift / sampler box", "assorted", 1.8, 1.9, 40)],
        "bundles_repeat": [(f"Bundle 2 × {pack}", f"2 × {pack}", 2.0, 2.0, 60), (f"Monthly refill 3 × {pack}", f"3 × {pack}", 2.7, 3.0, 40)],
    }[archetype]
    modelled = simulate(sim_inputs)
    total_units = modelled.orders.get("total", 0.0) * units
    product_mix = [ProductMixItem(name=n, focus=focus, pack_size=ps, target_price=round(unit_price * pm, 0),
                                  unit_cost=round(unit_cost * cm, 0), share_pct=share,
                                  max_monthly_units=max(1, math.ceil(total_units * share / 100 * 2)),
                                  evidence_refs=price_refs[:3]) for n, ps, pm, cm, share in mix_templates]
    A("stocking_cap", "Stocking cap per SKU", "2 months of modelled units", "units", "scenario_assumption",
      "Upper bound used by the inventory optimiser.")

    # ----- claims (facts need evidence refs; interpretations are labelled)
    if g and price_refs:
        claims.append(Claim(kind="market_fact", evidence_refs=price_refs,
                            text=f"Sampled {focus_label} listings in {ctx.country} (n={g.included_count}) show a median advertised "
                                 f"price of {g.currency} {g.median:,.0f} (sampled range {g.min:,.0f}–{g.max:,.0f})."))
        if g.unit_median is not None:
            claims.append(Claim(kind="market_fact", evidence_refs=price_refs,
                                text=f"Median unit price across {g.unit_sample_size} listings with verified pack sizes is "
                                     f"{g.currency} {g.unit_median:,.2f} {g.unit_basis.replace('_', ' ')}."))
    term, ts = ctx.trend_for(focus)
    if ts and ts.direction != "insufficient_data":
        trend_refs = [r for r in (ctx.trends.evidence_refs if ctx.trends else []) if r.startswith("TRD")][:2]
        claims.append(Claim(kind="market_fact", evidence_refs=trend_refs,
                            text=f"Google Trends relative interest for '{term}' in {ctx.country} is described as {ts.direction} "
                                 f"({'n/a' if ts.change_pct is None else f'{ts.change_pct:+.0f}%'} last vs first quarter of 12 months; "
                                 "relative index, not volume)."))
    direct = [c for c in ctx.competitors if c.relation == "direct" and focus in c.focuses]
    if direct:
        claims.append(Claim(kind="market_fact", evidence_refs=[r for c in direct[:3] for r in c.evidence_refs[:1]],
                            text=f"{len(direct)} direct competitor(s) appear in the sampled results for {focus_label}, e.g. "
                                 f"{', '.join(c.name for c in direct[:3])}."))
    interp = {
        "competitive_pricing": "Interpretation: pricing near the lower quartile can win price-sensitive shoppers, but only if "
                               "unit costs stay low enough to keep a positive contribution.",
        "premium_differentiation": "Interpretation: the spread between sampled lower and upper-quartile prices suggests room "
                                   "for a differentiated premium tier; this does not prove demand at that price.",
        "bundles_repeat": "Interpretation: consumable products suit bundles and refills that raise order value and repeat "
                          "purchases; repeat rates here are assumptions, not observations.",
    }[archetype]
    claims.append(Claim(kind="interpretation", text=interp, evidence_refs=price_refs[:2]))
    if draft:
        claims.extend(draft.claims)

    narrative = _narrative(archetype, focus_label, ctx, channel, unit_price, units, cur,
                           anchors["median"] if anchors else None, anchors["pack"] if anchors else None)
    if draft:
        narrative.update({k: getattr(draft, k) for k in ("summary", "positioning", "price_logic", "channel_choice",
                                                          "operating_tradeoffs", "advantages", "disadvantages")})
    if p.category in {"food_beverages"} and not any("shelf" in t.lower() or "fssai" in t.lower() for t in narrative["operating_tradeoffs"]):
        narrative["operating_tradeoffs"].append("Food compliance: FSSAI registration/licence, labelling and shelf-life planning are required before launch.")

    evidence = sorted({r for c in claims for r in c.evidence_refs} | {r for a in assumptions for r in a.evidence_refs})
    return Strategy(key=key, archetype=archetype, name=(draft.name if draft else ARCHETYPE_NAMES[archetype]) + f" · {focus_label}",
                    focus=focus, focus_label=focus_label, product_mix=product_mix, assumptions=assumptions, claims=claims,
                    evidence_refs=evidence, sim_inputs=sim_inputs, generated_by="llm" if draft else "deterministic",
                    **narrative)


def _physical_inputs(ctx: StrategyContext, archetype: str, g: PriceGroupStats | None, currency_ok: bool,
                     price_refs: list[str], A) -> tuple[PhysicalSimInputs, float, float, str]:
    p = ctx.profile
    cur = ctx.currency
    d = defaults_for(cur)["physical"]
    atv_mult = {"competitive_pricing": 0.9, "premium_differentiation": 1.35, "bundles_repeat": 1.15}[archetype]
    if p.average_transaction_value is not None:
        atv = A("average_transaction_value", "Average transaction value", round(p.average_transaction_value * atv_mult, 0),
                f"{cur} / transaction", "user_input", f"Your stated value ×{atv_mult} for this positioning.")
    elif currency_ok and g:
        atv = A("average_transaction_value", "Average transaction value", round(g.median * 1.5 * atv_mult, 0), f"{cur} / transaction",
                "market_evidence", f"1.5 items × sampled online median price ×{atv_mult} (online prices used as a benchmark only).",
                price_refs)
    else:
        atv = A("average_transaction_value", "Average transaction value", d["atv"] * atv_mult, f"{cur} / transaction",
                "scenario_assumption", "Illustrative placeholder – edit in What-If.")
    footfall = A("daily_footfall", "Daily footfall", p.expected_daily_footfall if p.expected_daily_footfall is not None else
                 {"shopping_mall": 220.0, "high_street": 160.0, "residential": 90.0}.get(p.sales_channel, 120.0), "visitors / day",
                 "user_input" if p.expected_daily_footfall is not None else "scenario_assumption",
                 "From your profile." if p.expected_daily_footfall is not None else
                 "Illustrative footfall by location type; NOT inferred from Maps or Trends data.")
    conv = A("conversion_rate_pct", "Conversion rate", {"competitive_pricing": 22.0, "premium_differentiation": 14.0,
                                                         "bundles_repeat": 18.0}[archetype], "% of visitors", "scenario_assumption",
             "Illustrative conversion assumption.")
    if p.product_unit_cost and p.selling_price:
        cogs = A("cogs_pct", "Cost of goods", round(min(100.0, p.product_unit_cost / p.selling_price * 100), 1), "% of sales",
                 "user_input", "Unit cost ÷ selling price from your profile.")
    else:
        cogs = A("cogs_pct", "Cost of goods", {"competitive_pricing": 62.0, "premium_differentiation": 50.0,
                                               "bundles_repeat": 58.0}[archetype],
                 "% of sales", "scenario_assumption", "Illustrative cost-of-goods ratio by positioning.")
    rent = A("rent", "Monthly rent", p.monthly_rent_inr if p.monthly_rent_inr is not None else d["rent"], f"{cur} / month",
             "user_input" if p.monthly_rent_inr is not None else "scenario_assumption", "From your profile." if p.monthly_rent_inr is not None else "Illustrative rent.")
    staff = A("staff", "Staff", p.monthly_staff_cost_inr if p.monthly_staff_cost_inr is not None else d["staff"], f"{cur} / month",
              "user_input" if p.monthly_staff_cost_inr is not None else "scenario_assumption", "Staff expenses.")
    util = A("utilities", "Utilities", p.monthly_utilities_inr if p.monthly_utilities_inr is not None else d["utilities"], f"{cur} / month",
             "user_input" if p.monthly_utilities_inr is not None else "scenario_assumption", "Utilities.")
    mkt = A("marketing", "Marketing", p.monthly_marketing_budget_inr if p.monthly_marketing_budget_inr is not None else d["marketing"],
            f"{cur} / month", "user_input" if p.monthly_marketing_budget_inr is not None else "scenario_assumption", "Local marketing.")
    capital = p.exact_capital_inr if cur == "INR" else None
    setup = defaults_for(cur)["setup"] * 4
    inv = A("initial_investment", "Initial investment (fit-out + opening stock)", setup, cur, "scenario_assumption",
            "Illustrative shop fit-out, deposit and opening inventory.")
    A("available_capital", "Available capital", capital, cur, "user_input" if capital is not None else "scenario_assumption",
      "From your profile." if capital is not None else "UNKNOWN – the budget band is not treated as an exact amount.")
    sim = PhysicalSimInputs(currency=cur, daily_footfall=footfall, conversion_rate_pct=conv, opening_days_per_month=26,
                            average_transaction_value=atv, cogs_pct=cogs, card_fee_pct=1.5, shrinkage_pct=1.5, rent=rent,
                            staff=staff, utilities=util, marketing=mkt, other_fixed=0.0, initial_investment=inv,
                            available_capital=capital)
    return sim, atv, round(atv * cogs / 100, 0), {"shopping_mall": "mall store", "high_street": "high-street store",
                                                    "residential": "neighbourhood store"}.get(p.sales_channel, "store")


def _narrative(archetype: str, focus_label: str, ctx: StrategyContext, channel: str, price: float, units: float,
               cur: str, median: float | None, pack: str | None) -> dict[str, Any]:
    ch = channel.replace("_", " ")
    stats = f" (sampled median {cur} {median:,.0f}{' for ' + pack if pack else ''})" if median else ""
    if archetype == "competitive_pricing":
        return dict(
            summary=f"Enter {focus_label.lower()} at a price near the sampled lower quartile, sold primarily via {ch}, to compete on value.",
            positioning="Value-for-money alternative to established brands with comparable pack sizes.",
            price_logic=f"Price per unit {cur} {price:,.0f}, anchored to the sampled 25th percentile{stats}.",
            channel_choice=f"{ch.capitalize()} first: existing shopper traffic and price comparison favour value offers.",
            operating_tradeoffs=["Thin unit margins leave little room for shipping or fee increases.",
                                 "Marketplace commissions and ad auctions can erode contribution quickly."],
            advantages=["Lower price barrier for first purchase.", "Easy to communicate value against visible competitors."],
            disadvantages=["Vulnerable to price wars and promotions by incumbents.", "Low contribution per order lengthens break-even."],
        )
    if archetype == "premium_differentiation":
        return dict(
            summary=f"Launch a differentiated {focus_label.lower()} range priced above the sampled upper quartile, sold via {ch}.",
            positioning="Quality-led brand: provenance, freshness and design justify a price premium.",
            price_logic=f"Price per unit {cur} {price:,.0f}, about 10% above the sampled 75th percentile{stats}.",
            channel_choice=f"{ch.capitalize()} first to control brand story, pricing and customer data.",
            operating_tradeoffs=["Higher product and packaging cost per unit.", "Requires content and brand-building investment."],
            advantages=["Higher contribution per order absorbs acquisition cost better.", "Less exposed to price competition."],
            disadvantages=["Smaller addressable segment at premium prices.", "Premium demand is not proven by search listings."],
        )
    return dict(
        summary=f"Sell {focus_label.lower()} as bundles and monthly refills to raise order value and build repeat purchases via {ch}.",
        positioning="Convenience and value through multi-pack bundles and subscriptions.",
        price_logic=f"{units:g} units per order at {cur} {price:,.0f} per unit (8% bundle discount vs the sampled median){stats}.",
        channel_choice=f"{ch.capitalize()} for subscriptions and customer relationships; marketplaces optional for discovery.",
        operating_tradeoffs=["Needs reliable inventory to fulfil recurring orders.", "Subscription churn must be monitored."],
        advantages=["Shipping and packaging are spread over more units.", "Repeat orders reduce reliance on paid acquisition."],
        disadvantages=["Higher upfront order value can reduce first-purchase conversion.", "Repeat-rate assumption is unverified."],
    )


def build_strategy_set(ctx: StrategyContext, drafts: dict[str, LLMStrategyDraft] | None = None) -> list[Strategy]:
    focus_map = assign_focuses(ctx)
    strategies = []
    for i, archetype in enumerate(ARCHETYPES, start=1):
        draft = (drafts or {}).get(archetype)
        focus = focus_map[archetype]
        if draft and draft.focus in {f.value for f in ctx.focuses}:
            focus = draft.focus
        strategies.append(build_strategy(ctx, archetype, focus, f"S{i}", draft))
    return strategies
