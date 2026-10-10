"""Deterministic finance formulas, scenarios, Monte Carlo and optimisation (no LLM involved)."""
from __future__ import annotations

import math

import pytest

from app.schemas.analysis import OnlineSimInputs, PhysicalSimInputs, ProductMixItem
from app.simulation.engine import run_simulation
from app.simulation.finance import simulate_online, simulate_physical
from app.simulation.montecarlo import monte_carlo_online
from app.simulation.optimizer import optimize_mix
from app.simulation.scenarios import run_scenarios


def online(**kw) -> OnlineSimInputs:
    base = dict(selling_price=500, units_per_order=1, unit_cost=200, packaging_cost_per_order=20,
                shipping_cost_per_order=60, platform_fee_pct=2, return_rate_pct=4, monthly_ad_budget=40_000,
                cac=400, organic_orders=20, repeat_orders=10, fixed_costs_monthly=10_000)
    base.update(kw)
    return OnlineSimInputs(**base)


def test_online_formulas_match_specification():
    r = simulate_online(online())
    aov = 500
    variable = 200 + 20 + 60 + 0.02 * aov + 0.04 * aov  # = 310
    contribution = aov - variable                         # = 190
    ad_orders = 40_000 / 400                              # = 100
    total = ad_orders + 20 + 10
    assert r.orders == {"ad_acquired": 100.0, "organic": 20.0, "repeat": 10.0, "total": 130.0}
    assert r.revenue == pytest.approx(total * aov)
    assert r.variable_cost_per_order == pytest.approx(variable)
    assert r.contribution_per_order == pytest.approx(contribution)
    assert r.operating_result == pytest.approx(total * contribution - 40_000 - 10_000)
    assert r.break_even_orders == math.ceil((40_000 + 10_000) / contribution)
    assert r.cost_breakdown["advertising"] == 40_000


def test_cac_is_not_double_counted():
    """Doubling CAC halves ad-acquired orders; the ad budget is subtracted exactly once."""
    r1 = simulate_online(online(organic_orders=0, repeat_orders=0, fixed_costs_monthly=0))
    r2 = simulate_online(online(organic_orders=0, repeat_orders=0, fixed_costs_monthly=0, cac=800))
    assert r1.operating_result == pytest.approx(100 * 190 - 40_000)
    assert r2.operating_result == pytest.approx(50 * 190 - 40_000)
    wrong = 100 * (190 - 400) - 40_000  # what double counting would give
    assert r1.operating_result != pytest.approx(wrong)
    assert sum(v for k, v in r1.cost_breakdown.items() if k != "advertising") + 40_000 == pytest.approx(
        r1.revenue - r1.operating_result)


def test_negative_margin_has_no_break_even():
    r = simulate_online(online(selling_price=250, unit_cost=200))
    assert r.contribution_per_order < 0
    assert r.break_even_orders is None and r.break_even_status == "not_achievable_negative_contribution"
    assert any("Negative contribution" in w for w in r.warnings)


def test_units_per_order_spreads_shipping():
    one = simulate_online(online(units_per_order=1))
    two = simulate_online(online(units_per_order=2))
    assert two.average_order_value == 1000
    assert two.contribution_per_order > 2 * one.contribution_per_order - 1e-9  # shipping/packaging per order, not per unit


def test_unknown_capital_and_runway():
    r = simulate_online(online(cac=2000, initial_investment=200_000))
    assert r.operating_result < 0
    assert r.capital_check.status == "unknown" and r.runway_months is None and "unknown" in r.runway_note
    known = simulate_online(online(cac=2000, initial_investment=200_000, available_capital=500_000))
    assert known.capital_check.status == "within"
    assert known.runway_months == pytest.approx(round(300_000 / -known.operating_result, 1))
    over = simulate_online(online(initial_investment=900_000, available_capital=500_000))
    assert over.capital_check.status == "exceeds"


def test_physical_model():
    r = simulate_physical(PhysicalSimInputs(daily_footfall=100, conversion_rate_pct=20, opening_days_per_month=25,
                                            average_transaction_value=400, cogs_pct=55, card_fee_pct=2, shrinkage_pct=1,
                                            rent=50_000, staff=30_000, utilities=5_000, marketing=5_000))
    tx = 100 * 0.2 * 25
    contribution = 400 * (1 - 0.58)
    assert r.orders["transactions"] == tx
    assert r.operating_result == pytest.approx(tx * contribution - 90_000)
    assert r.break_even_orders == math.ceil(90_000 / contribution)
    assert "visitors per opening day" in r.break_even_note


def test_bear_base_bull_are_ordered():
    scen = {s.scenario: s.result.operating_result for s in run_scenarios(online())}
    assert scen["bear"] < scen["base"] < scen["bull"]


def test_monte_carlo_is_seeded_and_reports_distributions():
    a = monte_carlo_online(online(), iterations=1000, seed=42)
    b = monte_carlo_online(online(), iterations=1000, seed=42)
    c = monte_carlo_online(online(), iterations=1000, seed=7)
    assert a.percentiles == b.percentiles and a.prob_negative == b.prob_negative
    assert a.percentiles != c.percentiles
    assert a.iterations == 1000 and sum(h["count"] for h in a.histogram) == 1000
    assert {d.parameter for d in a.distributions} >= {"cac", "unit_cost", "selling_price"}
    assert a.percentiles["p5"] <= a.percentiles["p50"] <= a.percentiles["p95"]
    assert "not empirically calibrated" in a.note


def mix() -> list[ProductMixItem]:
    return [ProductMixItem(name="A", focus="f", target_price=500, unit_cost=200, share_pct=60, max_monthly_units=100),
            ProductMixItem(name="B", focus="f", target_price=300, unit_cost=250, share_pct=40, max_monthly_units=100)]


def test_optimizer_respects_budget_and_prefers_better_margin():
    res = optimize_mix(mix(), 25_000)
    assert res.status == "optimal" and res.total_cost <= 25_000
    alloc = {a["name"]: a["units"] for a in res.allocations}
    assert alloc["A"] == 100 and alloc["B"] == 20  # A first (300/unit), remaining 5,000 buys 20 of B


def test_optimizer_disabled_when_capital_unknown():
    res = optimize_mix(mix(), None)
    assert res.status == "disabled_capital_unknown" and "Enter the capital" in res.message


def test_run_simulation_never_allocates_beyond_known_capital():
    sim = run_simulation("S1", 0, online(available_capital=10_000), mix(), iterations=1000, seed=1, inventory_budget=50_000)
    assert sim.optimization.budget == 10_000 and sim.optimization.total_cost <= 10_000
