"""google_product adapter (and google_immersive_product fallback) – details for selected products.

Shopping results may expose either a ``product_id`` (google_product) or an
``immersive_product_page_token`` (google_immersive_product). Both are supported.
"""
from __future__ import annotations

from typing import Any

from app.schemas.analysis import Observation, SearchOutcome
from app.serpapi.normalize import EvidenceRegistry, as_float, as_int, as_list, as_str, get, make_observation

ENGINE = "google_product"
IMMERSIVE_ENGINE = "google_immersive_product"


def build_params(product_id: str, market: dict[str, Any]) -> dict[str, Any]:
    return {"product_id": product_id, "offer_view": "true", "gl": market["gl"], "hl": market.get("hl", "en")}


def build_immersive_params(page_token: str) -> dict[str, Any]:
    return {"page_token": page_token}


def _offers(data: dict[str, Any]) -> list[dict[str, Any]]:
    raw_offers = (
        as_list(get(data, "sellers_results", "online_sellers"))
        or as_list(data.get("offers"))
        or as_list(get(data, "product_results", "stores"))
    )
    offers = []
    for o in raw_offers:
        if not isinstance(o, dict):
            continue
        price_text = as_str(o.get("base_price")) or as_str(o.get("price")) or as_str(o.get("total_price"))
        offers.append({
            "merchant": as_str(o.get("name")) or as_str(o.get("source")),
            "price_text": price_text,
            "extracted_price": as_float(o.get("extracted_price")) if o.get("extracted_price") is not None else as_float(price_text),
            "total_price_text": as_str(o.get("total_price")),
            "link": as_str(o.get("link"), 2000),
            "rating": as_float(o.get("rating")),
            "reviews": as_int(o.get("reviews")),
            "delivery": as_str(o.get("shipping")) or as_str(get(o, "additional_price", "shipping")),
        })
    return offers[:10]


def parse(outcome: SearchOutcome, registry: EvidenceRegistry, *, country: str, focus: str,
          parent_ref: str | None = None) -> list[Observation]:
    data = outcome.data or {}
    pr = data.get("product_results")
    if not isinstance(pr, dict):
        return []
    title = as_str(pr.get("title")) or "(product)"
    specs = data.get("specs_results") if isinstance(data.get("specs_results"), dict) else {}
    normalized = {
        "title": title,
        "brand": as_str(pr.get("brand")),
        "rating": as_float(pr.get("rating")),
        "reviews": as_int(pr.get("reviews")),
        "typical_price_low": as_str(get(pr, "typical_prices", "low")),
        "typical_price_high": as_str(get(pr, "typical_prices", "high")),
        "description": as_str(pr.get("description"), 600) or as_str(get(pr, "about_the_product", "description"), 600),
        "extensions": [e for e in (as_str(x) for x in as_list(pr.get("extensions"))) if e] or None,
        "offers": _offers(data) or None,
        "spec_keys": list(specs.keys())[:12] or None,
        "user_review_count": len(as_list(get(data, "reviews_results", "reviews"))) or None,
        "parent_listing_ref": parent_ref,
    }
    product_id = as_str(pr.get("product_id")) or outcome.params.get("product_id")
    link = as_str(get(data, "search_metadata", "google_product_url"), 2000) or as_str(pr.get("link"), 2000)
    original = {k: pr.get(k) for k in ("title", "brand", "rating", "reviews", "typical_prices", "extensions") if k in pr}
    return [make_observation(
        registry, outcome, kind="product_detail", classification="product_page_data",
        query=outcome.params.get("product_id") or outcome.params.get("page_token", "")[:40], country=country,
        title=title, normalized=normalized, original=original, source_url=link, source_id=product_id, focus=focus,
    )]
