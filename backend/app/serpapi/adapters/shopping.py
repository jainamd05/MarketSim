"""google_shopping adapter – advertised product listings."""
from __future__ import annotations

from typing import Any

from app.schemas.analysis import Observation, SearchOutcome
from app.serpapi.normalize import EvidenceRegistry, as_float, as_int, as_list, as_str, make_observation

ENGINE = "google_shopping"


def build_params(query: str, market: dict[str, Any]) -> dict[str, Any]:
    return {"q": query, "gl": market["gl"], "hl": market.get("hl", "en")}


def parse(outcome: SearchOutcome, registry: EvidenceRegistry, *, country: str, focus: str,
          limit: int = 20) -> list[Observation]:
    data = outcome.data or {}
    items = as_list(data.get("shopping_results"))
    # Some layouts put results under categorised groups; flatten defensively.
    for group in as_list(data.get("categorized_shopping_results")):
        items.extend(as_list(group.get("shopping_results")) if isinstance(group, dict) else [])
    out: list[Observation] = []
    seen: set[tuple[str | None, str | None]] = set()
    for raw in items:
        if not isinstance(raw, dict):
            continue
        title = as_str(raw.get("title"))
        if not title:
            continue
        merchant = as_str(raw.get("source")) or as_str(raw.get("seller"))
        dedupe_key = (title.lower(), (merchant or "").lower())
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        tags = [t for t in (as_str(x) for x in as_list(raw.get("extensions"))) if t]
        if as_str(raw.get("tag")):
            tags.append(as_str(raw.get("tag")))
        normalized = {
            "title": title,
            "merchant": merchant,
            "price_text": as_str(raw.get("price")),
            "extracted_price": as_float(raw.get("extracted_price")) if raw.get("extracted_price") is not None else as_float(raw.get("price")),
            "old_price_text": as_str(raw.get("old_price")),
            "extracted_old_price": as_float(raw.get("extracted_old_price")),
            "product_id": as_str(raw.get("product_id")),
            "page_token": as_str(raw.get("immersive_product_page_token"), 2000),
            "rating": as_float(raw.get("rating")),
            "reviews": as_int(raw.get("reviews")),
            "delivery": as_str(raw.get("delivery")),
            "tags": tags or None,
            "second_hand": as_str(raw.get("second_hand_condition")),
        }
        link = as_str(raw.get("product_link"), 2000) or as_str(raw.get("link"), 2000)
        out.append(make_observation(
            registry, outcome, kind="product_listing", classification="advertised_listing",
            query=outcome.params.get("q", ""), country=country, title=title, normalized=normalized, original=raw,
            source_url=link, source_id=normalized["product_id"], focus=focus,
        ))
        if len(out) >= limit:
            break
    return out
