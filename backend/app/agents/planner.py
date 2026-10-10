"""Supervisor planning logic: focus resolution, missing inputs and a bounded research plan.

The plan is deterministic for a given profile + budget, which makes DEMO runs
reproducible from fixtures and LIVE runs auditable.
"""
from __future__ import annotations

from typing import Any

from app.onboarding import registry
from app.schemas.analysis import FocusSpec, MissingInput, PlannedSearch, ResearchPlan
from app.schemas.profile import BusinessProfileIn
from app.serpapi.adapters import amazon, autocomplete, maps, news, product, search, shopping, trends

MARKETPLACE_CHANNELS = {"marketplaces", "website_and_marketplaces", "help_me_decide"}

_FIELD_LABELS = {
    "exact_capital_inr": ("Exact available capital", "Capital fit, cash runway and inventory optimisation cannot be computed exactly."),
    "monthly_ad_budget_inr": ("Monthly advertising budget", "Ad-acquired orders cannot be modelled without a budget."),
    "average_order_value": ("Average order value", "Order value is taken from sampled market prices as a labelled assumption."),
    "product_unit_cost": ("Unit cost", "Unit cost is a labelled scenario assumption until supplier quotes exist."),
    "shipping_cost": ("Shipping cost per order", "Shipping uses a labelled scenario assumption."),
    "payment_or_platform_fees": ("Platform / payment fees", "Fees use channel-based scenario assumptions."),
    "expected_return_cost": ("Return / refund allowance", "Returns use a category scenario assumption."),
    "monthly_fixed_costs": ("Monthly fixed costs", "Fixed costs use a labelled scenario assumption."),
    "monthly_rent_inr": ("Monthly rent", "Rent uses a labelled scenario assumption."),
    "monthly_staff_cost_inr": ("Staff expenses", "Staff cost uses a labelled scenario assumption."),
    "monthly_utilities_inr": ("Utilities", "Utilities use a labelled scenario assumption."),
    "average_transaction_value": ("Average transaction value", "Taken from sampled prices or a labelled assumption."),
    "expected_daily_footfall": ("Daily footfall", "Footfall is an editable scenario assumption; it is never inferred from search data."),
}


def resolve_focuses(profile: BusinessProfileIn) -> list[FocusSpec]:
    if profile.category == "undecided":
        specs = []
        for value in profile.compare_categories[:3] or [c["value"] for c in registry.load_registry()["categories"][:3]]:
            cat = registry.category(value)
            if cat:
                t = cat["terms"]
                specs.append(FocusSpec(value=value, label=cat["label"], level="category", unit_basis="count",
                                       terms={"product": t["trend"], "trend": t["trend"], "brand": t["brand"],
                                              "store": t["trend"] + " store", "news": t["brand"]}))
        return specs
    if profile.category == "other" or profile.subcategory == "other":
        text = (profile.product_focus or profile.custom_category or "products").strip()
        return [FocusSpec(value="custom", label=text, level="custom", unit_basis="count",
                          terms={"product": text, "trend": text, "brand": f"{text} brands", "store": f"{text} shop",
                                 "news": text})]
    out = []
    for value in profile.focus_values:
        sub = registry.subcategory(profile.category, value)
        if sub:
            out.append(FocusSpec(value=value, label=sub["label"], unit_basis=sub.get("unit_basis", "count"),
                                 terms=sub["terms"]))
    return out


def missing_inputs(profile: BusinessProfileIn) -> list[MissingInput]:
    out = []
    for f in profile.unknown_financial_fields():
        label, impact = _FIELD_LABELS.get(f, (f.replace("_", " "), "Uses a labelled scenario assumption."))
        out.append(MissingInput(field=f, label=label, impact=impact,
                                blocking=False))
    return out


def build_plan(profile: BusinessProfileIn, budget: int) -> ResearchPlan:
    focuses = resolve_focuses(profile)
    countries = profile.target_countries[:2] or ([profile.pilot_country] if profile.pilot_country else [])
    cat = registry.category(profile.category) or {}
    tasks: list[PlannedSearch] = []
    n = 0

    def add(agent: str, engine: str, params: dict[str, Any], purpose: str, priority: int,
            focus: str | None = None, country: str | None = None, depends_on: str | None = None) -> None:
        nonlocal n
        n += 1
        tasks.append(PlannedSearch(task_id=f"T{n:02d}", agent=agent, engine=engine, params=params, purpose=purpose,
                                   priority=priority, focus=focus, country=country, depends_on=depends_on))

    if profile.business_type == "online":
        for c in countries:
            m = registry.market(c)
            if not m:
                continue
            cname = m["label"]
            for f in focuses:
                add("competitor_discovery", shopping.ENGINE, shopping.build_params(f.terms["product"], m),
                    f"Advertised listings and prices for {f.label} in {cname}", 1, f.value, c)
            add("demand_trends", trends.ENGINE,
                trends.build_timeseries_params([f.terms["trend"] for f in focuses], m["trends_geo"]),
                f"Relative search interest over 12 months in {cname}", 1, None, c)
            for f in focuses:
                add("competitor_discovery", search.ENGINE, search.build_params(f"{f.terms['brand']} {cname}", m),
                    f"Competitor websites for {f.label} in {cname}", 2, f.value, c)
            news_term = focuses[0].terms["news"] if len(focuses) == 1 else cat.get("terms", {}).get("brand", focuses[0].terms["news"])
            add("market_news", news.ENGINE, news.build_params(f"{news_term} {cname}", m),
                f"Recent market developments in {cname}", 2, None, c)
            for f in focuses[:2]:
                add("pricing_intelligence", product.ENGINE, {"product_id": "<resolved from shopping results>"},
                    f"Offers and specifications for a top {f.label} product", 3, f.value, c,
                    depends_on=f"google_shopping:{f.value}:{c}")
            if profile.sales_channel in MARKETPLACE_CHANNELS and focuses:
                add("competitor_discovery", amazon.ENGINE, amazon.build_params(focuses[0].terms["product"], m),
                    f"Marketplace listings for {focuses[0].label} on {m['amazon_domain']}", 3, focuses[0].value, c)
            add("demand_trends", trends.ENGINE, {"q": "<top term by mean interest>", "geo": m["trends_geo"],
                                                 "date": trends.DEFAULT_RANGE, "data_type": "RELATED_QUERIES"},
                f"Related and rising queries in {cname}", 3, None, c, depends_on=f"google_trends:TIMESERIES:{c}")
            if focuses:
                add("demand_trends", autocomplete.ENGINE, autocomplete.build_params(focuses[0].terms["trend"], m),
                    "Keyword expansion (suggestions, not volumes)", 4, focuses[0].value, c)
    else:
        c = profile.pilot_country
        m = registry.market(c) if c else None
        if m is None and c:
            m = {"code": c, "label": c, "gl": c.lower(), "hl": "en", "trends_geo": c, "google_domain": "google.com",
                 "amazon_domain": "amazon.com", "currency": profile.currency}
        if m:
            place = f"{profile.locality}, {profile.city}" if profile.locality else profile.city
            for f in focuses:
                add("competitor_discovery", maps.ENGINE, maps.build_params(f.terms["store"], profile.city or "", profile.locality, m),
                    f"Nearby {f.label} competitors in {place}", 1, f.value, c)
                add("competitor_discovery", search.ENGINE, search.build_params(f"{f.terms['store']} {profile.city}", m),
                    f"Local competitor websites for {f.label}", 2, f.value, c)
            add("demand_trends", trends.ENGINE,
                trends.build_timeseries_params([f.terms["trend"] for f in focuses], m["trends_geo"]),
                f"Relative search interest over 12 months in {m['label']}", 2, None, c)
            add("market_news", news.ENGINE, news.build_params(f"{focuses[0].terms['news'] if focuses else 'retail'} {profile.city}", m),
                f"Local market developments around {profile.city}", 2, None, c)
            if cat.get("shopping_meaningful_for_physical"):
                for f in focuses:
                    add("competitor_discovery", shopping.ENGINE, shopping.build_params(f.terms["product"], m),
                        f"Online price benchmarks for {f.label}", 3, f.value, c)
            if focuses:
                add("demand_trends", trends.ENGINE, trends.build_region_params(focuses[0].terms["trend"], m["trends_geo"]),
                    "Interest by region (where useful for a local shop)", 3, focuses[0].value, c)

    ordered = sorted(tasks, key=lambda t: (t.priority, t.task_id))
    planned, skipped = [], []
    for t in ordered:
        if len(planned) < budget:
            planned.append(t)
        else:
            skipped.append(t.model_copy(update={"status": "skipped_budget"}))
    planned.sort(key=lambda t: t.task_id)

    capital_known = profile.exact_capital_inr is not None
    analyses = {
        "competitor_research": {"proceed": bool(focuses), "reason": "Focus terms resolved." if focuses else "No product focus to research."},
        "pricing_analysis": {"proceed": any(t.engine in {"google_shopping", "amazon"} for t in planned),
                             "reason": "Shopping/marketplace searches planned." if any(t.engine in {"google_shopping", "amazon"} for t in planned) else "No price sources planned for this branch."},
        "trend_analysis": {"proceed": any(t.engine == "google_trends" for t in planned), "reason": "Google Trends planned."},
        "profitability_simulation": {"proceed": True,
                                     "reason": "Runs with user inputs where given and explicitly labelled, editable scenario assumptions elsewhere."},
        "capital_optimisation": {"proceed": capital_known,
                                 "reason": "Exact capital provided." if capital_known else
                                 "Exact capital unknown – optimisation disabled until the amount is provided."},
    }
    notes = []
    if profile.worldwide_ambition:
        notes.append(f"Worldwide ambition recorded; research is scoped to pilot market(s): {', '.join(countries)}.")
    if profile.category == "undecided":
        notes.append("Category undecided: comparing category-level opportunity signals, not recommending a 'best' business.")
    if skipped:
        notes.append(f"{len(skipped)} lower-priority search(es) skipped to stay within the {budget}-request budget.")
    return ResearchPlan(branch=profile.business_type, focuses=focuses, countries=countries, budget=budget,
                        allocated=len(planned), planned=planned, skipped=skipped,
                        missing_inputs=missing_inputs(profile), analyses=analyses, notes=notes)
