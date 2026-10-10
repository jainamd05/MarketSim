"""Strategy critic: structured rejections and targeted revisions."""
from __future__ import annotations

from datetime import datetime, timezone

from app.agents import critic
from app.schemas.analysis import (
    Assumption, Claim, Observation, OnlineSimInputs, PriceGroupStats, ProductMixItem, Strategy,
)
from app.schemas.profile import demo_profile
from app.simulation.engine import run_simulation


def obs(ref: str) -> Observation:
    return Observation(ref=ref, kind="product_listing", engine="google_shopping", query="q", country="IN",
                       retrieved_at=datetime(2026, 10, 1, tzinfo=timezone.utc), title="t",
                       classification="advertised_listing", freshness="current", data_origin="live")


def strategy(**sim_kw) -> Strategy:
    sim = dict(currency="INR", selling_price=600, units_per_order=1, unit_cost=250, packaging_cost_per_order=25,
               shipping_cost_per_order=70, platform_fee_pct=2.5, return_rate_pct=3, monthly_ad_budget=40_000, cac=450,
               fixed_costs_monthly=8000, initial_investment=200_000)
    sim.update(sim_kw)
    return Strategy(
        key="S1", archetype="competitive_pricing", name="Test", focus="coffee_tea", focus_label="Coffee", summary="s",
        positioning="p", product_mix=[ProductMixItem(name="x", focus="coffee_tea", target_price=600, unit_cost=250,
                                                     share_pct=100, max_monthly_units=100)],
        price_logic="pl", channel_choice="c", operating_tradeoffs=["FSSAI compliance and shelf life"], advantages=["a"],
        disadvantages=["d"],
        assumptions=[Assumption(key="selling_price", label="Price", value=sim["selling_price"], unit="INR", source="market_evidence",
                                rationale="r", evidence_refs=["SHOP-001"]),
                     Assumption(key="market_median_price", label="Median", value=700, unit="INR", source="market_evidence",
                                rationale="pack-normalised: x", evidence_refs=["SHOP-001"]),
                     Assumption(key="cac", label="CAC", value=sim["cac"], unit="INR", source="scenario_assumption", rationale="r")],
        claims=[Claim(text="Median price is 700", kind="market_fact", evidence_refs=["SHOP-001"])],
        evidence_refs=["SHOP-001"], sim_inputs=OnlineSimInputs(**sim),
    )


def ctx(currency="INR") -> critic.CriticContext:
    return critic.CriticContext(profile=demo_profile(), evidence={"SHOP-001": obs("SHOP-001")},
                                price_groups={"coffee_tea": PriceGroupStats(focus="coffee_tea", focus_label="Coffee", country="IN",
                                                                            currency=currency, sample_size=10, included_count=10,
                                                                            median=700, unit_sample_size=8, unit_basis="per_100g")},
                                mode="live")


def evaluate(s: Strategy, c=None):
    sim = run_simulation(s.key, s.revision, s.sim_inputs, s.product_mix, iterations=1000, seed=1)
    return critic.evaluate(s, sim, c or ctx(), 1, [s])


def check(result, check_id):
    return next(c for c in result.checks if c.id == check_id)


def test_sound_strategy_passes_with_structured_checks():
    r = evaluate(strategy())
    assert r.passed and r.revision_requests == []
    assert {c.status for c in r.checks} <= {"pass", "warn", "not_applicable", "fail"}
    assert all(c.reason for c in r.checks), "every check carries a reason"
    assert check(r, "capital_fit").status == "warn"  # capital unknown in demo profile


def test_negative_margin_is_rejected_and_revised():
    s = strategy(selling_price=300)
    r = evaluate(s)
    assert not r.passed and check(r, "contribution_margin").status == "fail"
    revised, notes = critic.revise(s, r.revision_requests, ctx())
    assert revised.revision == 1 and revised.sim_inputs.units_per_order == 2 and "multi-pack" in notes[0]
    revised2, notes2 = critic.revise(revised, r.revision_requests, ctx())
    assert revised2.sim_inputs.selling_price == 700 and "median" in notes2[0]
    assert evaluate(revised2).passed


def test_unsupported_claim_is_rejected_then_relabelled():
    s = strategy()
    s.claims.append(Claim(text="Market is worth ₹500 crore", kind="market_fact", evidence_refs=[]))
    s.claims.append(Claim(text="Brand X leads", kind="market_fact", evidence_refs=["WEB-999"]))
    r = evaluate(s)
    assert not r.passed and check(r, "evidence_support").status == "fail"
    revised, _ = critic.revise(s, r.revision_requests, ctx())
    assert all(c.kind == "interpretation" for c in revised.claims if c.text.startswith("Unverified"))
    assert check(evaluate(revised), "evidence_support").status == "pass"


def test_currency_mismatch_is_rejected_and_left_unresolved():
    r = evaluate(strategy(), ctx(currency="USD"))
    assert not r.passed and check(r, "currency_consistency").status == "fail"
    _, notes = critic.revise(strategy(), r.revision_requests, ctx(currency="USD"))
    assert any("UNRESOLVED" in n and "FX" in n for n in notes)


def test_optimistic_llm_cac_is_rejected_and_replaced():
    s = strategy(cac=60)
    s.assumptions = [a if a.key != "cac" else a.model_copy(update={"source": "llm_proposed", "value": 60}) for a in s.assumptions]
    r = evaluate(s)
    assert check(r, "cac_plausibility").status == "fail"
    revised, _ = critic.revise(s, r.revision_requests, ctx())
    assert revised.sim_inputs.cac == 450  # conservative own-website default


def test_known_capital_exceeded_is_rejected_and_inventory_scaled():
    s = strategy(available_capital=100_000, initial_investment=300_000)
    r = evaluate(s)
    assert check(r, "capital_fit").status == "fail"
    revised, _ = critic.revise(s, r.revision_requests, ctx())
    assert revised.sim_inputs.initial_investment <= 100_000
    assert evaluate(revised).passed
