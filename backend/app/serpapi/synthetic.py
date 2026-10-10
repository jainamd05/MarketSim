"""Deterministic synthetic SerpApi-format payloads for DEMO mode.

DEMO mode normally replays the saved fixtures under ``fixtures/serpapi/<version>/``.
Those fixtures only cover the demonstration profile, so any other questionnaire
answer used to complete in a clearly degraded, empty state.

To make DEMO mode respond to *any* form answer (while remaining clearly labelled
DEMO data), this module fabricates plausible SerpApi-shaped payloads on demand for
requests that have no recorded fixture. Everything here is:

* fictional – brands and URLs use ``.example`` and do not exist;
* illustrative – prices are plausible ranges, never real market data;
* deterministic – the same request always yields the same payload, so demo runs and
  reports stay reproducible;
* labelled as demo data – the gateway keeps ``data_origin="demo_fixture"`` and the
  whole analysis runs in DEMO mode.
"""
from __future__ import annotations

import hashlib
import random
from datetime import datetime, timedelta, timezone
from typing import Any

from app.serpapi.gateway import ENGINE_ALLOWLIST

# Fixed authored timestamp so synthetic demo runs are byte-for-byte reproducible.
CREATED_AT = "2026-01-15 12:00:00 UTC"
_NOW = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

CURRENCY_BY_GL = {"in": "INR", "us": "USD", "uk": "GBP", "ae": "AED"}
CURRENCY_BY_AMAZON = {"amazon.in": "INR", "amazon.com": "USD", "amazon.co.uk": "GBP", "amazon.ae": "AED"}
SYMBOL = {"INR": "₹", "USD": "$", "GBP": "£", "AED": "AED "}
PRICE_RANGE = {"INR": (129, 899), "USD": (7, 79), "GBP": (6, 69), "AED": (25, 299)}

_BRANDS = [
    "Northwind", "Bluepeak", "Cedarline", "Brightloom", "Kestrel", "Ironbark", "Silverfern", "Maplecrest",
    "Riverstone", "Amberfield", "Copperleaf", "Larkspur", "Willowgrove", "Sablewood", "Harborlight",
]
_SIZES = ["100g", "150g", "200g", "250g", "500g", "1kg", "100ml", "200ml", "250ml", "500ml",
          "2 x 100g", "3 x 100g", "pack of 6", "12 count"]
_NEWS_FRAGMENTS = [
    "reports quarterly growth", "announces a new regional launch", "raises seed funding",
    "expands into new markets", "faces rising input costs", "launches a flagship product",
    "appoints a new chief executive", "sees a shift in consumer demand",
]


def _rng(*parts: str) -> random.Random:
    seed = int(hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16], 16)
    return random.Random(seed)


def _brand(rng: random.Random) -> str:
    return f"{rng.choice(_BRANDS)} {rng.choice(['Co', 'Brands', 'Goods', 'Foods', 'Works', 'Labs', 'Retail'])}"


def _slug(name: str, rng: random.Random) -> str:
    base = "".join(ch for ch in name.lower() if ch.isalnum())
    return f"{base or 'brand'}{rng.randint(2, 99)}"


def _currency(params: dict[str, str]) -> str:
    if "amazon_domain" in params:
        return CURRENCY_BY_AMAZON.get(params["amazon_domain"], "USD")
    return CURRENCY_BY_GL.get(str(params.get("gl", "")).lower(), "USD")


def _price(rng: random.Random, currency: str) -> float:
    low, high = PRICE_RANGE.get(currency, (10, 99))
    return round(rng.uniform(low, high), 2)


def _price_text(value: float, currency: str) -> str:
    return f"{SYMBOL.get(currency, '')}{value:,.2f}"


def _meta(engine: str, params: dict[str, str]) -> dict[str, Any]:
    return {
        "id": "demo-synthetic-" + hashlib.sha256(f"{engine}{sorted(params.items())}".encode()).hexdigest()[:12],
        "status": "Success",
        "created_at": CREATED_AT,
        "processed_at": CREATED_AT,
        "total_time_taken": 0.42,
        "synthetic_generated": True,
        "fixture_note": "SYNTHETIC DEMO DATA – generated for a request with no recorded fixture. "
                        "Fictional brands, illustrative values. Not real market data.",
    }


def _query(params: dict[str, str]) -> str:
    return params.get("q") or params.get("k") or params.get("product_id") or "market"


# ------------------------------------------------------------------ generators
def _google_shopping(params: dict[str, str]) -> dict[str, Any]:
    query = _query(params)
    currency = _currency(params)
    rng = _rng("shopping", query, currency)
    results = []
    for i in range(1, 13):
        brand = _brand(rng)
        size = rng.choice(_SIZES)
        price = _price(rng, currency)
        title = f"{brand} {query.title()} {size}"
        item: dict[str, Any] = {
            "position": i,
            "title": title,
            "source": brand,
            "price": _price_text(price, currency),
            "extracted_price": price,
            "rating": round(rng.uniform(3.6, 4.9), 1),
            "reviews": rng.randint(20, 4200),
            "delivery": "Free delivery",
            "product_link": f"https://{_slug(brand, rng)}.example/p/{i}",
            "thumbnail": "https://images.example/thumb.png",
        }
        if i <= 6:
            item["product_id"] = f"9900{i:02d}{rng.randint(1000000, 9999999)}"
        if i % 4 == 0:
            old = round(price * 1.18, 2)
            item["old_price"] = _price_text(old, currency)
            item["extracted_old_price"] = old
            item["extensions"] = [f"{round((1 - price / old) * 100)}% off"]
        results.append(item)
    return {"search_metadata": _meta("google_shopping", params), "shopping_results": results}


def _google(params: dict[str, str]) -> dict[str, Any]:
    query = _query(params)
    rng = _rng("google", query)
    results = []
    for i in range(1, 9):
        brand = _brand(rng)
        slug = _slug(brand, rng)
        results.append({
            "position": i,
            "title": f"{brand} – {query.title()}",
            "link": f"https://{slug}.example/",
            "displayed_link": f"{slug}.example",
            "snippet": f"{brand} sells {query} online with nationwide delivery. "
                       "Illustrative demo listing, not a real company.",
        })
    return {"search_metadata": _meta("google", params), "organic_results": results}


def _google_news(params: dict[str, str]) -> dict[str, Any]:
    query = _query(params)
    rng = _rng("news", query)
    results = []
    for i in range(1, 11):
        brand = _brand(rng)
        days = rng.randint(1, 150)
        published = _NOW - timedelta(days=days)
        results.append({
            "position": i,
            "title": f"{brand} {rng.choice(_NEWS_FRAGMENTS)}",
            "link": f"https://news.example/{_slug(brand, rng)}/{i}",
            "snippet": f"Demo news item about {query}. Synthetic content for the demo dataset only.",
            "date": f"{days} days ago",
            "iso_date": published.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source": {"name": f"{brand} Newsroom"},
        })
    return {"search_metadata": _meta("google_news", params), "news_results": results}


def _google_trends(params: dict[str, str]) -> dict[str, Any]:
    data_type = params.get("data_type", "TIMESERIES")
    queries = [q.strip() for q in params.get("q", "").split(",") if q.strip()]
    if data_type == "RELATED_QUERIES":
        return _trends_related(params, queries)
    if data_type == "GEO_MAP_0":
        return _trends_regions(params, queries)
    rng = _rng("trends-ts", ",".join(queries), params.get("geo", ""))
    levels = {q: rng.uniform(30, 80) for q in queries}
    directions = {q: rng.uniform(-0.6, 1.6) for q in queries}
    timeline = []
    for i in range(53):
        row: dict[str, Any] = {
            "date": (_NOW - timedelta(weeks=52 - i)).strftime("%b %d, %Y"),
            "timestamp": int((_NOW - timedelta(weeks=52 - i)).timestamp()),
            "partial_data": i == 52,
            "values": [],
        }
        for q in queries:
            value = max(0, min(100, levels[q] + directions[q] * i + rng.uniform(-6, 6)))
            value = int(round(value))
            row["values"].append({"query": q, "value": str(value), "extracted_value": value})
        timeline.append(row)
    return {"search_metadata": _meta("google_trends", params), "interest_over_time": {"timeline_data": timeline}}


def _trends_related(params: dict[str, str], queries: list[str]) -> dict[str, Any]:
    query = queries[0] if queries else _query(params)
    rng = _rng("trends-related", query)
    top = [{"query": f"{query} {w}", "value": f"{rng.randint(40, 100)}", "extracted_value": rng.randint(40, 100)}
           for w in ("price", "online", "brand", "buy", "best")]
    rising = [{"query": f"{query} {w}", "value": f"+{rng.randint(50, 400)}%", "extracted_value": rng.randint(50, 400)}
              for w in ("near me", "bulk", "subscription")]
    return {"search_metadata": _meta("google_trends", params),
            "related_queries": {"top": top, "rising": rising}}


def _trends_regions(params: dict[str, str], queries: list[str]) -> dict[str, Any]:
    query = queries[0] if queries else _query(params)
    rng = _rng("trends-region", query, params.get("geo", ""))
    regions = [{"location": name, "value": str(rng.randint(30, 100)), "extracted_value": rng.randint(30, 100)}
               for name in ("Capital Region", "Northern Province", "Southern Province", "Eastern Region", "Western Region")]
    return {"search_metadata": _meta("google_trends", params), "interest_by_region": regions}


def _amazon(params: dict[str, str]) -> dict[str, Any]:
    query = _query(params)
    currency = _currency(params)
    rng = _rng("amazon", query, currency)
    results = []
    for i in range(1, 13):
        brand = _brand(rng)
        price = _price(rng, currency)
        results.append({
            "position": i,
            "title": f"{brand} {query.title()} {rng.choice(_SIZES)}",
            "brand": brand,
            "asin": f"B0{hashlib.sha256(f'{query}{i}'.encode()).hexdigest()[:8].upper()}",
            "price": _price_text(price, currency),
            "extracted_price": price,
            "rating": round(rng.uniform(3.6, 4.9), 1),
            "reviews": rng.randint(15, 5200),
            "sponsored": i <= 2,
            "link": f"https://amazon.example/dp/B0{i:08d}",
        })
    return {"search_metadata": _meta("amazon", params), "organic_results": results}


def _google_maps(params: dict[str, str]) -> dict[str, Any]:
    query = _query(params)
    rng = _rng("maps", query)
    results = []
    for i in range(1, 13):
        brand = _brand(rng)
        slug = _slug(brand, rng)
        results.append({
            "position": i,
            "title": f"{brand} Store",
            "rating": round(rng.uniform(3.4, 4.9), 1),
            "reviews": rng.randint(8, 1800),
            "address": f"{rng.randint(1, 240)} Demo Street, {query.title()}",
            "website": f"https://{slug}.example/",
            "place_id": f"demo-place-{i:03d}",
            "type": "store",
            "types": ["Store", "Point of interest"],
            "gps_coordinates": {"latitude": round(rng.uniform(-90, 90), 5), "longitude": round(rng.uniform(-180, 180), 5)},
            "open_state": "Open",
        })
    return {"search_metadata": _meta("google_maps", params), "local_results": results}


def _google_autocomplete(params: dict[str, str]) -> dict[str, Any]:
    query = _query(params)
    rng = _rng("autocomplete", query)
    words = ["price", "online", "best", "near me", "brands", "buy", "store", "offers"]
    rng.shuffle(words)
    suggestions = [{"value": f"{query} {w}"} for w in words[:8]]
    return {"search_metadata": _meta("google_autocomplete", params), "suggestions": suggestions}


def _google_product(params: dict[str, str]) -> dict[str, Any]:
    product_id = params.get("product_id", "demo-product")
    currency = _currency(params)
    rng = _rng("product", product_id, currency)
    brand = _brand(rng)
    low = _price(rng, currency)
    high = round(low * rng.uniform(1.2, 1.8), 2)
    offers = [{
        "name": _brand(rng),
        "base_price": _price_text(_price(rng, currency), currency),
        "extracted_price": _price(rng, currency),
        "link": f"https://offers.example/{product_id[:8]}",
        "rating": round(rng.uniform(3.5, 4.9), 1),
        "reviews": rng.randint(10, 2000),
    } for _ in range(5)]
    return {
        "search_metadata": _meta("google_product", params),
        "product_results": {
            "product_id": product_id,
            "title": f"{brand} {rng.choice(_SIZES)} Pack",
            "brand": brand,
            "rating": round(rng.uniform(3.6, 4.9), 1),
            "reviews": rng.randint(20, 3500),
            "description": "Illustrative product description generated for the demo dataset.",
            "extensions": [rng.choice(["Popular pick", "Best seller", "New arrival"])],
            "typical_prices": {"low": _price_text(low, currency), "high": _price_text(high, currency)},
            "link": f"https://products.example/{product_id[:8]}",
        },
        "sellers_results": {"online_sellers": offers},
        "specs_results": {"Brand": brand, "Pack type": rng.choice(_SIZES)},
        "reviews_results": {"reviews": []},
    }


_GENERATORS = {
    "google_shopping": _google_shopping,
    "google_product": _google_product,
    "google_immersive_product": _google_product,
    "google_trends": _google_trends,
    "google": _google,
    "google_news": _google_news,
    "google_maps": _google_maps,
    "google_autocomplete": _google_autocomplete,
    "amazon": _amazon,
}


def synthesize(engine: str, params: dict[str, Any]) -> dict[str, Any] | None:
    """Returns a synthetic SerpApi-shaped payload, or None if the engine is not supported."""
    gen = _GENERATORS.get(engine)
    if gen is None or engine not in ENGINE_ALLOWLIST:
        return None
    canon = {k: str(v) for k, v in params.items() if v is not None}
    try:
        return gen(canon)
    except Exception:
        return None
