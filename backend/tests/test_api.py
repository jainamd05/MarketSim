"""HTTP API: typed endpoints, consistent errors, what-if recomputation without SerpApi calls,
and the LLM adapter path (mocked)."""
from __future__ import annotations

import json

import httpx
from sqlalchemy import func, select

from app import models
from app.db import Database
from app.main import create_app
from fastapi.testclient import TestClient
from tests.conftest import make_settings, run_demo


def test_health_config_and_questions(client):
    assert client.get("/api/health").json()["status"] == "ok"
    cfg = client.get("/api/config").json()
    assert cfg["default_data_mode"] == "demo" and cfg["serpapi_configured"] is False and cfg["fixtures_synthetic"] is True
    assert "serpapi_api_key" not in json.dumps(cfg).lower()
    q = client.get("/api/onboarding/questions").json()
    food = next(c for c in q["categories"] if c["value"] == "food_beverages")
    assert [s["label"] for s in food["subcategories"]] == ["Packaged snacks", "Coffee and tea", "Beverage mixes",
                                                           "Premium pantry products"]


def test_profile_crud_and_validation_errors(client, demo_profile_json):
    r = client.post("/api/profiles", json={"profile": demo_profile_json})
    assert r.status_code == 201
    prof = r.json()["profile"]
    assert prof["status"] == "draft" and prof["exact_capital_inr"] is None
    pid = prof["id"]
    demo_profile_json["exact_capital_inr"] = 1_500_000
    r = client.put(f"/api/profiles/{pid}", json={"profile": demo_profile_json, "status": "confirmed"})
    assert r.json()["profile"]["exact_capital_inr"] == 1_500_000
    assert client.get(f"/api/profiles/{pid}").json()["profile"]["status"] == "confirmed"

    bad = dict(demo_profile_json, business_type="physical")  # physical without a city / with online channel
    r = client.post("/api/profiles", json={"profile": bad})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"
    assert "City is required" in r.json()["error"]["message"]
    r = client.get("/api/profiles/doesnotexist")
    assert r.status_code == 404 and r.json()["error"]["code"] == "profile_not_found"


def test_live_mode_requires_key(client, demo_profile_json):
    pid = client.post("/api/profiles", json={"profile": demo_profile_json}).json()["profile"]["id"]
    r = client.post("/api/analyses", json={"profile_id": pid, "mode": "live"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "mode_unavailable"
    r = client.post("/api/analyses", json={"profile_id": "0" * 32})
    assert r.status_code == 404


def test_events_pagination_and_dashboard_endpoints(client):
    aid = run_demo(client)
    first = client.get(f"/api/analyses/{aid}/events?after=0").json()
    later = client.get(f"/api/analyses/{aid}/events?after={first['events'][9]['seq']}").json()
    assert later["events"][0]["seq"] == first["events"][10]["seq"]
    comp = client.get(f"/api/analyses/{aid}/competitors").json()
    assert comp["countries"] == ["IN"] and len(comp["price_groups"]) == 3 and comp["product_details"]
    trends = client.get(f"/api/analyses/{aid}/trends").json()
    t = trends["by_country"]["IN"]
    assert t["status"] == "ok" and len(t["points"]) == 53 and "not sales demand" in t["demand_caveat"]
    assert t["related_queries"]["top"]
    ev = client.get(f"/api/analyses/{aid}/evidence").json()
    assert len(ev["searches"]) == 12 and all("api_key" not in s["params"] for s in ev["searches"])
    assert client.get("/api/analyses").json()[0]["id"] == aid
    assert client.get("/api/analyses/nope/report").status_code == 404


def test_what_if_recomputes_without_serpapi_calls(client, db):
    aid = run_demo(client)
    data = client.get(f"/api/analyses/{aid}/strategies").json()
    s = data["strategies"][1]
    base = data["simulations"][s["key"]]["base"]
    with db.session() as sess:
        before = sess.scalar(select(func.count()).select_from(models.SearchRequest))
    inputs = dict(s["sim_inputs"], selling_price=s["sim_inputs"]["selling_price"] + 100)
    r = client.post(f"/api/analyses/{aid}/simulate", json={"strategy_key": s["key"], "inputs": inputs})
    assert r.status_code == 200, r.text
    sim = r.json()["simulation"]
    orders = sim["base"]["orders"]["total"]
    units = inputs["units_per_order"]
    fee_ret = (inputs["platform_fee_pct"] + inputs["return_rate_pct"]) / 100
    expected_delta = orders * 100 * units * (1 - fee_ret)
    # orders are reported rounded to 0.1, so allow 0.05 orders × ₹100 of rounding slack
    assert abs((sim["base"]["operating_result"] - base["operating_result"]) - expected_delta) <= 0.05 * 100 * units
    with db.session() as sess:
        assert sess.scalar(select(func.count()).select_from(models.SearchRequest)) == before
    assert r.json()["serpapi_requests_made"] == 0

    # Entering capital enables the optimiser and never exceeds it
    r = client.post(f"/api/analyses/{aid}/simulate", json={"strategy_key": s["key"], "inputs": dict(inputs, available_capital=50_000)})
    opt = r.json()["simulation"]["optimization"]
    assert opt["status"] == "optimal" and opt["total_cost"] <= 50_000
    # Currency changes are refused rather than silently converted
    r = client.post(f"/api/analyses/{aid}/simulate", json={"strategy_key": s["key"], "inputs": dict(inputs, currency="USD")})
    assert r.status_code == 422 and r.json()["error"]["code"] == "currency_mismatch"
    r = client.post(f"/api/analyses/{aid}/simulate", json={"strategy_key": s["key"], "inputs": dict(inputs, cac=-5)})
    assert r.status_code == 422


def _llm_handler(content: str):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer groq-test-key"
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})
    return handler


def _llm_client(tmp_path, content):
    settings = make_settings(tmp_path, llm_provider="groq", groq_api_key="groq-test-key")
    db = Database(settings.resolved_database_url)
    return TestClient(create_app(settings, db=db, llm_transport=httpx.MockTransport(_llm_handler(content)))), db


def test_llm_strategy_drafts_are_validated_and_used(tmp_path):
    drafts = {"strategies": [
        {"archetype": a, "name": f"LLM {a}", "focus": f, "summary": "s", "positioning": "p", "price_logic": "pl",
         "channel_choice": "c", "operating_tradeoffs": ["FSSAI labelling"], "advantages": ["a"], "disadvantages": ["d"],
         "claims": [{"text": "Unbacked market size claim", "kind": "market_fact", "evidence_refs": []}],
         "price_position": pp, "proposed_cac": cac, "proposed_units_per_order": None}
        for a, f, pp, cac in [("competitive_pricing", "packaged_snacks", "at_median", None),
                              ("premium_differentiation", "premium_pantry", "above_median", 40),
                              ("bundles_repeat", "coffee_tea", "at_median", None)]]}
    client, db = _llm_client(tmp_path, json.dumps(drafts))
    with client:
        aid = run_demo(client)
        data = client.get(f"/api/analyses/{aid}/strategies").json()
        assert all(s["generated_by"] == "llm" for s in data["strategies"])
        first = data["critic_rounds"][0]["evaluations"]
        failed = {c["id"] for e in first for c in e["checks"] if c["status"] == "fail"}
        assert {"evidence_support", "cac_plausibility"} <= failed, "critic challenges the LLM output"
        premium = next(s for s in data["strategies"] if s["archetype"] == "premium_differentiation")
        assert premium["sim_inputs"]["cac"] > 40
        assert client.get(f"/api/analyses/{aid}").json()["llm_mode"].startswith("llm:groq")
    db.dispose()


def test_invalid_llm_output_falls_back_to_deterministic_with_warning(tmp_path):
    client, db = _llm_client(tmp_path, "not json at all")
    with client:
        aid = run_demo(client)
        data = client.get(f"/api/analyses/{aid}/strategies").json()
        assert all(s["generated_by"] == "deterministic" for s in data["strategies"])
        ev = client.get(f"/api/analyses/{aid}/events").json()["events"]
        assert any(e["event_type"] == "warning" and "falling back" in e["message"] for e in ev)
        assert "groq-test-key" not in json.dumps(ev)
    db.dispose()
