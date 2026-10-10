"""amazon adapter – marketplace listings for businesses selling on online marketplaces."""
from __future__ import annotations

from typing import Any

from app.schemas.analysis import Observation, SearchOutcome
from app.serpapi.normalize import EvidenceRegistry, as_float, as_int, as_list, as_str, make_observation

ENGINE = "amazon"


def build_params(query: str, market: dict[str, Any]) -> dict[str, Any]:
    return {"k": query, "amazon_domain": market["amazon_domain"]}


def parse(outcome: SearchOutcome, registry: EvidenceRegistry, *, country: str, focus: str,
          limit: int = 15) -> list[Observation]:
    data = outcome.data or {}
    out: list[Observation] = []
    for raw in as_list(data.get("organic_results")):
        if not isinstance(raw, dict):
            continue
        title = as_str(raw.get("title"))
        if not title:
            continue
        delivery = raw.get("delivery")
        if isinstance(delivery, list):
            delivery = "; ".join(d for d in (as_str(x) for x in delivery) if d)
        normalized = {
            "title": title,
            "merchant": as_str(raw.get("brand")),
            "marketplace": "Amazon",
            "asin": as_str(raw.get("asin")),
            "price_text": as_str(raw.get("price")),
            "extracted_price": as_float(raw.get("extracted_price")) if raw.get("extracted_price") is not None else as_float(raw.get("price")),
            "old_price_text": as_str(raw.get("old_price")),
            "extracted_old_price": as_float(raw.get("extracted_old_price")),
            "rating": as_float(raw.get("rating")),
            "reviews": as_int(raw.get("reviews")),
            "sponsored": bool(raw.get("sponsored")) if raw.get("sponsored") is not None else None,
            "delivery": as_str(delivery),
        }
        link = as_str(raw.get("link_clean"), 2000) or as_str(raw.get("link"), 2000)
        out.append(make_observation(
            registry, outcome, kind="marketplace_listing", classification="advertised_listing",
            query=outcome.params.get("k", ""), country=country, title=title, normalized=normalized, original=raw,
            source_url=link, source_id=normalized["asin"], focus=focus,
        ))
        if len(out) >= limit:
            break
    return out
