"""SerpApi gateway: request construction, allowlist, budget, de-duplication, caching,
backoff, honest failures and secret handling. Uses httpx.MockTransport – no network."""
from __future__ import annotations

import httpx
import pytest

from app.db import Database
from app.serpapi.gateway import FixtureStore, ResponseCache, SerpApiGateway, cache_key
from tests.conftest import make_settings

KEY = "test-secret-key-123"


def live_gateway(tmp_path, handler, budget=12, cache=None, **settings_kw):
    settings = make_settings(tmp_path, serpapi_api_key=KEY, demo_mode="false", **settings_kw)
    events = []
    gw = SerpApiGateway(mode="live", settings=settings, budget=budget, cache=cache,
                        transport=httpx.MockTransport(handler), on_event=lambda t, o: events.append((t, o)),
                        sleep=lambda s: None)
    return gw, events


def ok_shopping(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"search_metadata": {"id": "abc", "status": "Success"},
                                     "shopping_results": [{"title": "Coffee 250g", "price": "₹500", "extracted_price": 500}]})


def test_request_construction_and_key_never_leaks(tmp_path):
    seen = []

    def handler(request):
        seen.append(request)
        return ok_shopping(request)

    gw, events = live_gateway(tmp_path, handler)
    out = gw.search("google_shopping", {"q": "premium roasted coffee beans 250g", "gl": "in", "hl": "en"},
                    agent="competitor_discovery", purpose="test")
    url = seen[0].url
    assert url.host == "serpapi.com" and url.path == "/search.json"
    assert url.params["engine"] == "google_shopping"
    assert url.params["q"] == "premium roasted coffee beans 250g"
    assert url.params["gl"] == "in" and url.params["hl"] == "en"
    assert url.params["api_key"] == KEY
    assert out.status == "ok" and out.result_count == 1 and out.data_origin == "live"
    assert "api_key" not in out.params
    assert KEY not in out.model_dump_json()
    assert all(KEY not in o.model_dump_json() for _, o in events)


@pytest.mark.parametrize("engine, params", [
    ("google_trends", {"q": "specialty coffee,coffee beans", "geo": "IN", "date": "today 12-m", "data_type": "TIMESERIES"}),
    ("google_product", {"product_id": "123", "offer_view": "true", "gl": "in"}),
    ("google_maps", {"q": "specialty coffee stores Mumbai", "type": "search"}),
    ("google_news", {"q": "specialty coffee brands India", "gl": "in", "hl": "en"}),
    ("google", {"q": "specialty coffee brands India", "gl": "in", "hl": "en"}),
])
def test_example_requests_from_brief_are_accepted(tmp_path, engine, params):
    seen = []
    gw, _ = live_gateway(tmp_path, lambda r: seen.append(r) or httpx.Response(200, json={"search_metadata": {}}))
    out = gw.search(engine, params, agent="t", purpose="t")
    assert out.status in {"ok", "empty"}
    assert seen[0].url.params["engine"] == engine
    for k, v in params.items():
        assert seen[0].url.params[k] == v


def test_engine_allowlist_and_param_validation_block_requests(tmp_path):
    calls = []
    gw, _ = live_gateway(tmp_path, lambda r: calls.append(r) or ok_shopping(r))
    assert gw.search("bing", {"q": "x"}, agent="t", purpose="t").status == "blocked"
    assert gw.search("google_shopping", {"q": "x", "evil": "1"}, agent="t", purpose="t").status == "blocked"
    assert gw.search("google_shopping", {"gl": "in"}, agent="t", purpose="t").status == "blocked"  # missing q
    assert gw.search("google_shopping", {"q": "a\nb"}, agent="t", purpose="t").status == "blocked"
    assert calls == [] and gw.requests_used == 0


def test_budget_is_enforced(tmp_path):
    gw, events = live_gateway(tmp_path, ok_shopping, budget=2)
    results = [gw.search("google_shopping", {"q": f"item {i}"}, agent="t", purpose="t") for i in range(4)]
    assert [r.status for r in results] == ["ok", "ok", "skipped_budget", "skipped_budget"]
    assert gw.requests_used == 2
    assert any(t == "tool_skipped" for t, _ in events)


def test_identical_searches_are_deduplicated(tmp_path):
    calls = []
    gw, _ = live_gateway(tmp_path, lambda r: calls.append(r) or ok_shopping(r))
    a = gw.search("google_shopping", {"q": "coffee", "gl": "in"}, agent="t", purpose="t")
    b = gw.search("google_shopping", {"gl": "in", "q": "coffee"}, agent="t", purpose="t")
    assert len(calls) == 1 and gw.requests_used == 1
    assert a.status == "ok" and b.status == "deduplicated" and b.data == a.data


def test_persistent_cache_hit_and_ttl(tmp_path):
    db = Database(f"sqlite:///{(tmp_path / 'c.db').as_posix()}")
    db.create_all()
    calls = []
    handler = lambda r: calls.append(r) or ok_shopping(r)  # noqa: E731
    gw1, _ = live_gateway(tmp_path, handler, cache=ResponseCache(db))
    gw1.search("google_shopping", {"q": "coffee"}, agent="t", purpose="t")
    gw2, _ = live_gateway(tmp_path, handler, cache=ResponseCache(db))
    out = gw2.search("google_shopping", {"q": "coffee"}, agent="t", purpose="t")
    assert len(calls) == 1 and out.data_origin == "cache" and gw2.cache_hits == 1 and gw2.requests_used == 0
    gw3, _ = live_gateway(tmp_path, handler, cache=ResponseCache(db), serpapi_cache_ttl_seconds=0)
    gw3.search("google_shopping", {"q": "coffee"}, agent="t", purpose="t")
    assert len(calls) == 2, "TTL 0 disables cache reads"
    with db.session() as s:
        from app.models import SerpApiCacheEntry
        entries = s.query(SerpApiCacheEntry).all()
        assert all(KEY not in str(e.params) and KEY not in str(e.response) for e in entries)
    db.dispose()


def test_transient_errors_retry_with_backoff_then_succeed(tmp_path):
    responses = iter([httpx.Response(429, json={"error": "rate limited"}), httpx.Response(503), None])
    sleeps = []

    def handler(request):
        r = next(responses)
        return r if r is not None else ok_shopping(request)

    settings = make_settings(tmp_path, serpapi_api_key=KEY, serpapi_backoff_base_seconds=0.5)
    gw = SerpApiGateway(mode="live", settings=settings, transport=httpx.MockTransport(handler), sleep=sleeps.append)
    out = gw.search("google_shopping", {"q": "coffee"}, agent="t", purpose="t")
    assert out.status == "ok" and out.attempts == 3
    assert len(sleeps) == 2 and sleeps[1] > sleeps[0], "exponential backoff"


def test_auth_error_is_not_retried_and_is_reported(tmp_path):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(401, json={"error": f"Invalid API key. Your key: {KEY}"})

    gw, _ = live_gateway(tmp_path, handler)
    out = gw.search("google_shopping", {"q": "coffee"}, agent="t", purpose="t")
    assert out.status == "failed" and len(calls) == 1 and out.http_status == 401
    assert KEY not in (out.error or "") and "***" in out.error


def test_timeout_fails_honestly_after_retries(tmp_path):
    def handler(request):
        raise httpx.ReadTimeout("timed out", request=request)

    gw, _ = live_gateway(tmp_path, handler, serpapi_max_retries=2)
    out = gw.search("google_shopping", {"q": "coffee"}, agent="t", purpose="t")
    assert out.status == "failed" and out.attempts == 3 and "ReadTimeout" in out.error and out.data is None


def test_no_results_error_payload_is_empty_not_failure(tmp_path):
    gw, _ = live_gateway(tmp_path, lambda r: httpx.Response(200, json={"error": "Google hasn't returned any results for this query."}))
    out = gw.search("google_shopping", {"q": "zzzz"}, agent="t", purpose="t")
    assert out.status == "empty" and out.result_count == 0


def test_live_mode_without_key_fails_without_fixture_substitution(tmp_path):
    settings = make_settings(tmp_path, serpapi_api_key=None, demo_mode="false")
    gw = SerpApiGateway(mode="live", settings=settings)
    out = gw.search("google_shopping", {"q": "healthy snacks pack", "gl": "in", "hl": "en"}, agent="t", purpose="t")
    assert out.status == "failed" and out.data is None and out.data_origin == "none"


def test_demo_mode_reads_versioned_fixtures(tmp_path):
    settings = make_settings(tmp_path)
    gw = SerpApiGateway(mode="demo", settings=settings, fixtures=FixtureStore("v1"))
    out = gw.search("google_shopping", {"q": "roasted coffee beans 250g", "gl": "in", "hl": "en"}, agent="t", purpose="t")
    assert out.status == "ok" and out.data_origin == "demo_fixture" and out.result_count == 12
    assert out.retrieved_at.year == 2026 and out.retrieved_at.month == 9  # fixture's own timestamp
    missing = gw.search("google_shopping", {"q": "not in fixtures"}, agent="t", purpose="t")
    assert missing.status == "fixture_missing" and missing.data is None


def test_cache_key_ignores_api_key_and_param_order():
    assert cache_key("google", {"q": "a", "gl": "in", "api_key": "x"}) == cache_key("google", {"gl": "in", "q": "a"})
