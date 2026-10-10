"""News classification and risk register.

Reported developments are kept separate from forward-looking statements. Category
guidance is labelled as guidance – it is not evidence and not a compliance check.
"""
from __future__ import annotations

import re
from typing import Iterable

from app.schemas.analysis import NewsItem, Observation, RiskItem

_TOPICS: list[tuple[str, re.Pattern[str]]] = [
    ("regulatory", re.compile(r"\b(fssai|regulat\w*|label\w*|ban\w*|gst|tax\w*|duty|compliance|recall\w*|standard\w*)\b", re.I)),
    ("supply", re.compile(r"\b(suppl\w*|shortage\w*|harvest\w*|crop\w*|monsoon|prices? (rise|surge|jump)|cost\w* (rise|surge)|import\w*|export\w*|freight|logistic\w*|inflation)\b", re.I)),
    ("funding", re.compile(r"\b(rais\w*|funding|series [a-e]|investment|investor\w*|valuation|acqui\w*)\b", re.I)),
    ("product_launch", re.compile(r"\b(launch\w*|unveil\w*|introduc\w*|debut\w*|new range|rolls? out)\b", re.I)),
]
_FORWARD = re.compile(r"\b(could|may|might|expected to|expects?|likely|forecast\w*|project\w*|plans? to|aims? to|set to|will)\b", re.I)

CATEGORY_GUIDANCE: dict[str, tuple[str, str, str]] = {
    "perishability": ("Perishability", "Food products degrade over time; inventory turns, storage conditions and dispatch speed must be planned around shelf life.", "high"),
    "packaging": ("Packaging for transit", "Packaging must protect product quality in transit and carry mandatory information; budget packaging cost per order.", "medium"),
    "shelf_life": ("Shelf life and stock rotation", "Short shelf life raises write-off risk when demand is uncertain; start with smaller batches.", "medium"),
    "import_export": ("Import / export restrictions", "Cross-border food sales are governed by destination-country import rules; any worldwide expansion needs per-country checks.", "high"),
    "labeling": ("Product labelling", "Food labels must meet local labelling rules (in India, FSSAI labelling and display requirements). Verify with the regulator or a qualified adviser.", "high"),
    "food_safety_licence": ("Food business registration", "Food businesses in India generally require FSSAI registration or a licence before selling. MarketSim does not verify or certify compliance.", "high"),
    "product_certification": ("Product certification", "Electronics may require safety/standards certification in the target market (e.g. BIS in India). Verify before importing.", "high"),
    "warranty_returns": ("Warranty and returns", "Electronics carry warranty obligations and higher return handling costs.", "medium"),
    "battery_shipping": ("Battery shipping restrictions", "Products with lithium batteries face carrier and air-freight restrictions.", "medium"),
    "sizing_returns": ("Size-related returns", "Apparel return rates are often high due to sizing; model the return allowance carefully.", "high"),
    "seasonality": ("Seasonality", "Fashion demand is seasonal; inventory bought for one season may need markdowns.", "medium"),
    "inventory_obsolescence": ("Inventory obsolescence", "Trend-driven products can become unsellable; avoid deep inventory early.", "medium"),
    "ingredient_labeling": ("Ingredient labelling", "Cosmetics require ingredient disclosure under local rules.", "high"),
    "cosmetics_regulation": ("Cosmetics regulation", "Cosmetic imports/manufacture may need registration with the national regulator.", "high"),
    "claims_substantiation": ("Claims substantiation", "Efficacy claims (e.g. 'anti-ageing') need substantiation; avoid unsupported claims.", "medium"),
    "health_claims": ("Health claims", "Health and nutrition claims are regulated; unsupported claims create legal risk.", "high"),
    "supplement_regulation": ("Supplement regulation", "Nutraceuticals/supplements have specific approval and labelling regimes.", "high"),
    "breakage_in_transit": ("Breakage in transit", "Fragile goods raise packaging cost and damage-related refunds.", "medium"),
    "bulky_shipping": ("Bulky shipping", "Large items have higher volumetric shipping charges.", "medium"),
}


def classify_news(observations: Iterable[Observation], competitor_names: dict[str, str]) -> list[NewsItem]:
    items: list[NewsItem] = []
    for obs in observations:
        if obs.kind != "news_article":
            continue
        n = obs.normalized
        text = f"{obs.title} {n.get('snippet') or ''}"
        lowered = text.lower()
        related = sorted({name for key, name in competitor_names.items()
                          if len(key) > 3 and (name.lower() in lowered or key in lowered.replace(" ", ""))})
        topic = "competitor" if related else "market"
        for name, pattern in _TOPICS:
            if pattern.search(text):
                topic = name
                break
        nature = "forward_looking" if _FORWARD.search(obs.title) else "reported_development"
        items.append(NewsItem(
            ref=obs.ref, title=obs.title, link=obs.source_url, source=n.get("source"),
            published_at=n.get("published_at"), date_text=n.get("date_text"), age_days=n.get("age_days"),
            freshness=obs.freshness, topic=topic, nature=nature, related_competitors=related, snippet=n.get("snippet"),
        ))
    items.sort(key=lambda i: (i.age_days is None, i.age_days or 0))
    return items


def build_risks(items: list[NewsItem], category_flags: list[str], missing_inputs: list[str],
                live: bool) -> list[RiskItem]:
    risks: list[RiskItem] = []
    supply = [i for i in items if i.topic == "supply"]
    if supply:
        risks.append(RiskItem(id="news-supply", title="Supply / input-cost developments reported",
                              detail=f"{len(supply)} article(s) report supply or cost developments. "
                                     "Review them before fixing unit-cost assumptions.",
                              severity="medium", basis="evidence", evidence_refs=[i.ref for i in supply[:4]]))
    regulatory = [i for i in items if i.topic == "regulatory"]
    if regulatory:
        risks.append(RiskItem(id="news-regulatory", title="Regulatory developments reported",
                              detail=f"{len(regulatory)} article(s) mention regulation, labelling or tax changes.",
                              severity="high", basis="evidence", evidence_refs=[i.ref for i in regulatory[:4]]))
    launches = [i for i in items if i.topic in {"product_launch", "funding", "competitor"}]
    if launches:
        risks.append(RiskItem(id="news-competition", title="Active competitor activity",
                              detail=f"{len(launches)} article(s) report launches, funding or competitor moves.",
                              severity="medium", basis="evidence", evidence_refs=[i.ref for i in launches[:4]]))
    stale = [i for i in items if i.freshness == "stale"]
    if live and items and len(stale) == len(items):
        risks.append(RiskItem(id="news-stale", title="News evidence is stale",
                              detail="All retrieved articles are older than 180 days; current conditions may differ.",
                              severity="low", basis="evidence", evidence_refs=[i.ref for i in stale[:3]]))
    for flag in category_flags:
        if flag in CATEGORY_GUIDANCE:
            title, detail, severity = CATEGORY_GUIDANCE[flag]
            risks.append(RiskItem(id=f"guidance-{flag}", title=title, detail=detail, severity=severity,
                                  basis="category_guidance"))
    for field in missing_inputs:
        risks.append(RiskItem(id=f"missing-{field}", title=f"Unknown input: {field.replace('_', ' ')}",
                              detail="This input is unknown; dependent results use labelled scenario assumptions.",
                              severity="medium", basis="missing_input"))
    return risks
