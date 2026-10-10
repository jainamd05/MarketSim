"""End-to-end LangGraph runs: demo profile with fixtures, reproducibility, persistence,
physical routing, bounded retries and honest degraded LIVE runs."""
from __future__ import annotations

import httpx
from sqlalchemy import func, select

from app import models
from app.config import Settings
from app.db import Database
from app.main import create_app
from app.schemas.profile import demo_profile
from fastapi.testclient import TestClient
from tests.conftest import make_settings, run_demo


def events(client, aid):
    return client.get(f"/api/analyses/{aid}/events").json()["events"]


def test_demo_profile_runs_through_full_graph(client, db):
    aid = run_demo(client)
    status = client.get(f"/api/analyses/{aid}").json()
    assert status["status"] == "completed" and status["mode"] == "demo"
    assert status["requests_used"] == 12 and status["request_budget"] == 12
    assert status["progress"]["percent"] == 100

    ev = events(client, aid)
    types = {e["event_type"] for e in ev}
    assert {"agent_started", "agent_completed", "tool_requested", "tool_completed", "tool_skipped", "evidence_extracted",
            "strategy_proposed", "simulation_completed", "critic_rejected", "critic_accepted",
            "revision_performed", "analysis_completed"} <= types
    agents = [e["agent"] for e in ev if e["event_type"] == "agent_started"]
    assert agents[:6] == ["supervisor", "competitor_discovery", "pricing_intelligence", "demand_trends",
                          "market_news", "strategy_generation"]
    assert agents[-1] == "report_composer"
    assert any(e["event_type"] == "route_selected" and e["meta"]["branch"] == "online" for e in ev)
    assert not any(e["meta"].get("engine") == "google_maps" for e in ev)
    tool = next(e for e in ev if e["event_type"] == "tool_completed")
    assert {"engine", "result_count", "duration_ms", "data_origin"} <= set(tool["meta"])
    assert all(e["meta"].get("data_origin") in (None, "demo_fixture", "none") for e in ev)

    strategies = client.get(f"/api/analyses/{aid}/strategies").json()
    finals = strategies["strategies"]
    assert len(finals) == 3 and len({s["archetype"] for s in finals}) == 3
    assert len({s["focus"] for s in finals}) == 3, "undecided focus: each strategy explores a different focus"
    rounds = strategies["critic_rounds"]
    assert 1 <= len(rounds) <= 3 and rounds[-1]["decision"] in {"accept", "accept_with_unresolved"}
    assert any(not e["passed"] for e in rounds[0]["evaluations"]), "critic rejects at least one demo strategy"
    assert max(s["revision"] for s in finals) <= 2
    for s in finals:
        sim = strategies["simulations"][s["key"]]
        assert sim["revision"] == s["revision"] and sim["monte_carlo"]["iterations"] >= 1000
        assert sim["optimization"]["status"] == "disabled_capital_unknown"
        assert all(a["source"] in {"user_input", "market_evidence", "scenario_assumption", "llm_proposed"} for a in s["assumptions"])
        ad_budget = next(a for a in s["assumptions"] if a["key"] == "monthly_ad_budget")
        assert ad_budget["source"] == "user_input" and ad_budget["value"] == 40_000

    report = client.get(f"/api/analyses/{aid}/report").json()["report"]
    assert report["mode"] == "demo" and "DEMO MODE" in report["limitations"][0]
    assert report["observed_facts"] and report["modeled_scenarios"] and report["citations"]
    cited = {c["ref"] for c in report["citations"]}
    for s in finals:
        for claim in s["claims"]:
            if claim["kind"] == "market_fact":
                assert set(claim["evidence_refs"]) <= cited | {r for r in claim["evidence_refs"]}
    assert all(c["data_origin"] == "demo_fixture" and c["freshness"] == "demo_fixture" for c in report["citations"])


def test_results_are_persisted_in_sqlite(client, db):
    aid = run_demo(client)
    with db.session() as s:
        def count(model):
            return s.scalar(select(func.count()).select_from(model).where(model.analysis_id == aid))
        assert count(models.SearchRequest) == 12
        assert count(models.EvidenceSource) > 50
        assert count(models.Competitor) > 10
        assert count(models.ProductListing) == 41
        assert count(models.TrendObservation) == 53 * 3
        assert count(models.BusinessStrategy) >= 3
        assert count(models.SimulationScenario) >= 3
        assert count(models.CriticEvaluation) >= 3
        assert count(models.AnalysisReport) == 1
        assert count(models.AgentEvent) > 50
        req = s.scalars(select(models.SearchRequest).where(models.SearchRequest.analysis_id == aid)).first()
        assert "api_key" not in req.params and req.response is not None


def test_report_is_reproducible_from_stored_inputs(client):
    a, b = run_demo(client), run_demo(client)
    ra = client.get(f"/api/analyses/{a}/report").json()
    rb = client.get(f"/api/analyses/{b}/report").json()
    assert ra["inputs_hash"] == rb["inputs_hash"]
    assert ra["content_hash"] == rb["content_hash"]


def test_physical_profile_routes_to_maps_with_synthetic_demo_data(client):
    profile = dict(business_type="physical", business_stage="new", category="food_beverages", subcategory="coffee_tea",
                   pilot_country="IN", city="Mumbai", sales_channel="high_street", sourcing_model="resell",
                   budget_band="5l_10l", primary_goal="competitor_intelligence", exact_capital_inr=800_000)
    aid = run_demo(client, profile)
    st = client.get(f"/api/analyses/{aid}").json()
    assert st["status"] == "completed", "DEMO mode now synthesises data for any profile"
    ev = events(client, aid)
    assert any(e["event_type"] == "route_selected" and e["meta"]["branch"] == "physical" for e in ev)
    strategies = client.get(f"/api/analyses/{aid}/strategies").json()["strategies"]
    assert len(strategies) == 3 and all(s["sim_inputs"]["model"] == "physical" for s in strategies)
    report = client.get(f"/api/analyses/{aid}/report").json()["report"]
    assert report["status"] == "completed"
    engines = {c["engine"] for c in report["citations"]}
    assert "google_maps" in engines, "synthetic Maps data must back local competitors"
    assert report["citations"] and all(c["data_origin"] == "demo_fixture" for c in report["citations"])


def test_physical_profile_degrades_honestly_when_synthetic_fallback_disabled(tmp_path):
    settings = make_settings(tmp_path, demo_synthetic_fallback=False)
    database = Database(settings.resolved_database_url)
    database.create_all()
    app = create_app(settings, db=database)
    profile = dict(business_type="physical", business_stage="new", category="food_beverages", subcategory="coffee_tea",
                   pilot_country="IN", city="Mumbai", sales_channel="high_street", sourcing_model="resell",
                   budget_band="5l_10l", primary_goal="competitor_intelligence", exact_capital_inr=800_000)
    try:
        with TestClient(app) as c:
            aid = run_demo(c, profile)
            st = c.get(f"/api/analyses/{aid}").json()
            assert st["status"] == "partial", "with synthesis off, missing fixtures must not pretend success"
            ev = events(c, aid)
            maps_events = [e for e in ev if e["meta"].get("engine") == "google_maps" and e["event_type"] == "tool_failed"]
            assert maps_events and maps_events[0]["meta"]["status"] == "fixture_missing"
            report = c.get(f"/api/analyses/{aid}/report").json()["report"]
            assert report["status"] == "partial"
            engines = {x["engine"] for x in report["citations"]}
            assert "google_maps" not in engines, "missing Maps fixtures must not produce cited local competitors"
    finally:
        database.dispose()


def test_bounded_retries_stop_after_two_revisions(client):
    profile = demo_profile().model_dump(mode="json")
    profile["product_unit_cost"] = 5_000  # user cost far above every market price: unfixable
    aid = run_demo(client, profile)
    data = client.get(f"/api/analyses/{aid}/strategies").json()
    rounds = data["critic_rounds"]
    assert len(rounds) == 3 and rounds[-1]["decision"] == "accept_with_unresolved"
    assert max(s["revision"] for s in data["strategies"]) == 2
    assert sum(e["event_type"] == "revision_performed" for e in events(client, aid)) >= 2
    report = client.get(f"/api/analyses/{aid}/report").json()["report"]
    assert report["status"] == "partial" and report["critic_summary"]["unresolved_failures"]


def test_live_mode_partial_failures_are_reported_without_fixture_substitution(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        engine = request.url.params["engine"]
        if engine == "google_shopping":
            return httpx.Response(200, json={"search_metadata": {"id": "x"}, "shopping_results": [
                {"title": "Live Snack 100g", "source": "Live Brand", "price": "₹150", "extracted_price": 150}]})
        if engine == "google_news":
            return httpx.Response(500, json={"error": "upstream"})
        return httpx.Response(200, json={"error": "Google hasn't returned any results for this query."})

    settings = make_settings(tmp_path, serpapi_api_key="live-test-key", demo_mode="auto", serpapi_max_retries=1)
    db = Database(settings.resolved_database_url)
    with TestClient(create_app(settings, db=db, serpapi_transport=httpx.MockTransport(handler))) as client:
        aid = run_demo(client, mode="live")
        st = client.get(f"/api/analyses/{aid}").json()
        assert st["mode"] == "live" and st["status"] == "partial"
        ev = events(client, aid)
        assert any(e["event_type"] == "tool_failed" and e["meta"]["engine"] == "google_news" for e in ev)
        assert not any(e["meta"].get("data_origin") == "demo_fixture" for e in ev)
        comps = client.get(f"/api/analyses/{aid}/competitors").json()
        assert {l["title"] for l in comps["listings"]} == {"Live Snack 100g"}
        report = client.get(f"/api/analyses/{aid}/report").json()["report"]
        assert all(c["data_origin"] == "live" for c in report["citations"])
        assert "live-test-key" not in str(report) and "live-test-key" not in str(ev)
    db.dispose()
