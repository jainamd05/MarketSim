"""Defensive adapter parsing, unit normalisation, currency detection, merchant de-duplication
and sampled price statistics."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.intelligence.competitors import brand_key, build_competitors, build_listings, price_stats
from app.intelligence.news import classify_news
from app.intelligence.trends import summarize_series
from app.intelligence.units import parse_quantity, unit_price
from app.schemas.analysis import SearchOutcome
from app.serpapi.adapters import amazon, maps, news, product, search, shopping, trends
from app.serpapi.normalize import EvidenceRegistry, as_int, detect_currency


def outcome(engine: str, data, params=None) -> SearchOutcome:
    return SearchOutcome(engine=engine, params=params or {"q": "test"}, status="ok", data_origin="live", data=data,
                         retrieved_at=datetime(2026, 10, 1, tzinfo=timezone.utc))


# ---------------------------------------------------------------- adapters
def test_shopping_parser_tolerates_missing_fields():
    data = {"shopping_results": [
        {"title": "Coffee 250g"},                                    # no price, merchant, rating
        {"price": "₹100"},                                           # no title -> skipped
        "not-a-dict",
        {"title": "Honey 500g", "price": "₹450.00", "extracted_price": 450, "source": "Bee Co", "reviews": "1.2K",
         "rating": "4.5", "extensions": ["20% off", None]},
    ]}
    obs = shopping.parse(outcome("google_shopping", data), EvidenceRegistry(), country="IN", focus="coffee_tea")
    assert [o.title for o in obs] == ["Coffee 250g", "Honey 500g"]
    assert obs[0].normalized.get("extracted_price") is None and obs[0].source_url is None
    assert obs[1].normalized["reviews"] == 1200 and obs[1].normalized["rating"] == 4.5
    assert obs[1].ref == "SHOP-002" and obs[1].classification == "advertised_listing"


def test_parsers_return_empty_for_missing_result_keys():
    reg = EvidenceRegistry()
    for mod, engine in ((shopping, "google_shopping"), (search, "google"), (maps, "google_maps"), (news, "google_news")):
        kwargs = {"country": "IN", "focus": "x"}
        assert mod.parse(outcome(engine, {}), reg, **kwargs) == []
    assert product.parse(outcome("google_product", {"product_results": "oops"}), reg, country="IN", focus="x") == []
    points, obs = trends.parse_timeseries(outcome("google_trends", {"interest_over_time": None}, {"q": "a,b"}), reg,
                                          country="IN", query_focus={})
    assert points == [] and len(obs) == 2 and obs[0].normalized["points"] == 0


def test_news_source_as_string_or_object_and_relative_dates():
    data = {"news_results": [
        {"title": "A launches", "link": "https://x.example/1", "source": {"name": "Wire"}, "date": "09/30/2026, 07:00 AM, +0000 UTC"},
        {"title": "B story", "link": "https://x.example/2", "source": "Paper", "date": "2 days ago"},
        {"title": "Cluster", "stories": [{"title": "C nested", "link": "https://x.example/3"}]},
    ]}
    obs = news.parse(outcome("google_news", data), EvidenceRegistry(), country="IN", focus=None)
    assert [o.normalized.get("source") for o in obs[:2]] == ["Wire", "Paper"]
    assert obs[0].normalized["age_days"] == 1 and obs[0].freshness == "current"
    assert obs[1].normalized["age_days"] == 2
    assert any(o.title == "C nested" for o in obs)
    assert next(o for o in obs if o.title == "C nested").freshness == "unknown"


def test_maps_place_results_fallback_and_trends_missing_values():
    obs = maps.parse(outcome("google_maps", {"place_results": {"title": "Bean Shop", "rating": 4.6, "reviews": "312"}}),
                     EvidenceRegistry(), country="IN", focus="coffee_tea")
    assert obs[0].normalized["reviews"] == 312 and obs[0].normalized.get("website") is None
    data = {"interest_over_time": {"timeline_data": [
        {"date": "Jan 1", "values": [{"query": "a", "extracted_value": 10}]},  # 'b' missing in this row
        {"date": "Jan 8", "values": [{"query": "a", "value": "20"}, {"query": "b", "extracted_value": 5}], "partial_data": True},
    ]}}
    points, _ = trends.parse_timeseries(outcome("google_trends", data, {"q": "a,b"}), EvidenceRegistry(), country="IN",
                                        query_focus={})
    assert points[0]["b"] is None and points[1]["a"] == 20.0 and points[1]["partial"] is True


def test_immersive_product_stores_are_parsed_as_offers():
    data = {"product_results": {"title": "Honey", "stores": [{"name": "Shop A", "price": "₹499", "extracted_price": 499}]}}
    obs = product.parse(outcome("google_immersive_product", data, {"page_token": "tok"}), EvidenceRegistry(), country="IN", focus="x")
    assert obs[0].normalized["offers"][0]["merchant"] == "Shop A"


def test_amazon_parser_handles_delivery_lists():
    data = {"organic_results": [{"title": "Snack 100g", "price": "₹99", "extracted_price": 99, "delivery": ["FREE", "Tue"]}]}
    obs = amazon.parse(outcome("amazon", data, {"k": "snack"}), EvidenceRegistry(), country="IN", focus="s")
    assert obs[0].kind == "marketplace_listing" and obs[0].normalized["delivery"] == "FREE; Tue"


# ------------------------------------------------------------ normalisation
@pytest.mark.parametrize("title, amount, unit, status", [
    ("Coffee Beans 250g", 250, "g", "parsed"),
    ("Coffee 1 kg", 1000, "g", "parsed"),
    ("Makhana 4 x 30g", 120, "g", "parsed"),
    ("Trail Mix Pack of 3 (200g each)", 600, "g", "parsed"),
    ("Honey 500g x 2", 1000, "g", "parsed"),
    ("Cold brew 1.5 L", 1500, "ml", "parsed"),
    ("Protein Bars 6 Bars", 6, "count", "parsed"),
    ("Combo 80g & 120g", None, None, "ambiguous"),
    ("Assorted Snack Box", None, None, "missing"),
])
def test_pack_size_parsing(title, amount, unit, status):
    q = parse_quantity(title)
    assert q.status == status
    if status == "parsed":
        assert q.amount == pytest.approx(amount) and q.base_unit == unit


def test_unit_price_only_for_verified_sizes():
    assert unit_price(500, parse_quantity("Coffee 250g")) == (200.0, "per_100g")
    assert unit_price(120, parse_quantity("Bars 6 Bars")) == (20.0, "per_unit")
    assert unit_price(299, parse_quantity("Combo 80g & 120g")) == (None, None)


@pytest.mark.parametrize("text, market, expected", [
    ("₹1,299.00", "INR", ("INR", "detected")),
    ("Rs. 499", "INR", ("INR", "detected")),
    ("$24.99", "INR", ("USD?", "mismatch")),
    ("$24.99", "USD", ("USD", "inferred_from_market")),
    ("£12", "INR", ("GBP", "mismatch")),
    ("1,050", "INR", (None, "missing")),
    (None, "INR", (None, "missing")),
])
def test_currency_detection(text, market, expected):
    assert detect_currency(text, market) == expected


def test_as_int_handles_serpapi_review_formats():
    assert as_int("1.2K") == 1200 and as_int("(512)") == 512 and as_int("3,456") == 3456 and as_int(None) is None


# --------------------------------------------------------------- competitors
@pytest.mark.parametrize("a, b", [
    ("Kaapi Trail", "https://www.kaapitrail.example/products"),
    ("Kaapi Trail Official Store", "kaapitrail.example"),
    ("GoodGrain Co.", "GoodGrain Pvt Ltd"),
    ("Amazon.in - Seller", "amazon.in"),
])
def test_brand_normalisation_merges_variants(a, b):
    assert brand_key(a) == brand_key(b)


def _shop(title, merchant, price_text, price, focus="coffee_tea"):
    return {"title": title, "source": merchant, "price": price_text, "extracted_price": price}


def test_listing_normalisation_excludes_currency_problems_from_stats():
    data = {"shopping_results": [
        _shop("Coffee 250g", "Kaapi Trail", "₹500", 500), _shop("Coffee 250g", "Blue Hills", "₹700", 700),
        _shop("Coffee 500g", "Roast Co", "₹900", 900), _shop("Import Coffee 250g", "Global", "$20", 20),
        _shop("Coffee 250g", "NoSymbol", "650", 650),
    ]}
    reg = EvidenceRegistry()
    obs = shopping.parse(outcome("google_shopping", data), reg, country="IN", focus="coffee_tea")
    listings = build_listings(obs, "INR")
    flags = {l.merchant: l.flags for l in listings}
    assert "currency_mismatch" in flags["Global"] and "missing_currency" in flags["NoSymbol"]
    stats = price_stats(listings, "coffee_tea", "Coffee", "IN", "INR")
    assert stats.sample_size == 5 and stats.included_count == 3
    assert stats.min == 500 and stats.max == 900 and stats.median == 700 and stats.currency == "INR"
    assert stats.unit_basis == "per_100g" and stats.unit_median == 200.0  # 500/250g, 700/250g=280, 900/500g=180
    assert {e["ref"] for e in stats.excluded} == {l.evidence_ref for l in listings if not l.included_in_stats}
    assert any("Small sample" in w for w in stats.warnings)


def test_mixed_unit_bases_are_never_combined():
    data = {"shopping_results": [_shop("Bars 6 Bars", "A", "₹300", 300), _shop("Chips 100g", "B", "₹100", 100),
                                 _shop("Chips 200g", "C", "₹150", 150)]}
    listings = build_listings(shopping.parse(outcome("google_shopping", data), EvidenceRegistry(), country="IN", focus="s"), "INR")
    stats = price_stats(listings, "s", "Snacks", "IN", "INR")
    assert stats.unit_basis == "per_100g" and stats.unit_sample_size == 2
    assert any("different unit basis" in w for w in stats.warnings)


def test_merchants_deduplicated_across_shopping_and_web():
    reg = EvidenceRegistry()
    shop_obs = shopping.parse(outcome("google_shopping", {"shopping_results": [
        _shop("Kaapi Trail Beans 250g", "Kaapi Trail", "₹600", 600),
        _shop("Kaapi Trail Beans 500g", "Kaapi Trail Official Store", "₹1100", 1100),
        _shop("Beans 250g", "Amazon.in", "₹550", 550)]}), reg, country="IN", focus="coffee_tea")
    web_obs = search.parse(outcome("google", {"organic_results": [
        {"title": "Kaapi Trail – Specialty Coffee", "link": "https://kaapitrail.example/", "snippet": "Fresh coffee beans"},
        {"title": "Top 10 coffee brands", "link": "https://journal.example/top", "snippet": "coffee"}]}),
        reg, country="IN", focus="coffee_tea")
    listings = build_listings(shop_obs, "INR")
    comps = build_competitors(listings, shop_obs + web_obs, {"coffee_tea": ["coffee"]}, {})
    by_key = {c.key: c for c in comps}
    kaapi = by_key["kaapitrail"]
    assert kaapi.relation == "direct" and len(kaapi.listing_refs) == 2
    assert kaapi.websites == ["https://kaapitrail.example/"] and set(kaapi.engines) == {"google_shopping", "google"}
    assert by_key["amazon"].relation == "marketplace"
    assert by_key["journal"].relation == "reference"
    assert kaapi.price_min == 600 and kaapi.price_max == 1100


def test_news_classification_separates_reported_and_forward_looking():
    data = {"news_results": [
        {"title": "Kaapi Trail launches cold brew range", "link": "https://n.example/1", "date": "09/20/2026, 07:00 AM, +0000 UTC"},
        {"title": "Coffee prices could rise next year, analysts say", "link": "https://n.example/2", "date": "09/21/2026, 07:00 AM, +0000 UTC"},
    ]}
    obs = news.parse(outcome("google_news", data), EvidenceRegistry(), country="IN", focus=None)
    items = {i.title: i for i in classify_news(obs, {"kaapitrail": "Kaapi Trail"})}
    assert items["Kaapi Trail launches cold brew range"].nature == "reported_development"
    assert items["Kaapi Trail launches cold brew range"].topic == "product_launch"
    assert items["Kaapi Trail launches cold brew range"].related_competitors == ["Kaapi Trail"]
    assert items["Coffee prices could rise next year, analysts say"].nature == "forward_looking"


def test_trend_summary_is_relative_and_excludes_partial_points():
    points = [{"date": f"w{i}", "x": 40 + i, "partial": False} for i in range(12)] + [{"date": "p", "x": 1, "partial": True}]
    s = summarize_series("x", points)
    assert s.direction == "rising" and s.points == 12 and s.change_pct > 10
    assert summarize_series("x", points[:3]).direction == "insufficient_data"
