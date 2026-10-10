"""BusinessProfile validation and supervisor routing / research planning."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.agents.planner import build_plan
from app.schemas.profile import BusinessProfileIn, demo_profile


def physical(**kw) -> BusinessProfileIn:
    base = dict(business_type="physical", business_stage="new", category="food_beverages", subcategory="coffee_tea",
                pilot_country="IN", city="Mumbai", locality="Bandra", sales_channel="high_street",
                sourcing_model="resell", budget_band="5l_10l", primary_goal="competitor_intelligence")
    base.update(kw)
    return BusinessProfileIn(**base)


def test_demo_profile_matches_brief():
    p = demo_profile()
    assert p.business_type == "online" and p.business_stage == "new"
    assert p.worldwide_ambition and p.pilot_country == "IN"
    assert p.exact_capital_inr is None, "Above ₹10 lakh must not be turned into an exact amount"
    assert p.monthly_ad_budget_inr == 40_000
    assert p.focus_values == ["packaged_snacks", "coffee_tea", "premium_pantry"]


def test_missing_financial_inputs_stay_unknown_not_zero():
    p = demo_profile()
    unknown = p.unknown_financial_fields()
    assert "exact_capital_inr" in unknown and "product_unit_cost" in unknown
    assert p.product_unit_cost is None and p.shipping_cost is None


@pytest.mark.parametrize("overrides, message", [
    (dict(city=None), "City is required"),
    (dict(sourcing_model="dropshipping"), "not valid for physical"),
    (dict(sales_channel="own_website"), "not valid for physical"),
    (dict(primary_goal="improve_profitability"), "not valid for a new business"),
    (dict(category="other", subcategory=None), "custom_category is required"),
    (dict(subcategory="other"), "product_focus is required"),
    (dict(pilot_country="India"), "ISO-3166"),
    (dict(budget_band="huge"), "Unknown budget band"),
])
def test_profile_cross_field_validation(overrides, message):
    with pytest.raises(ValidationError) as exc:
        physical(**overrides)
    assert message in str(exc.value)


def test_worldwide_ambition_requires_pilot_country():
    data = demo_profile().model_dump()
    data.update(pilot_country=None, target_countries=[])
    with pytest.raises(ValidationError, match="pilot country is required"):
        BusinessProfileIn(**data)


def test_at_most_two_pilot_markets():
    data = demo_profile().model_dump()
    data.update(target_countries=["IN", "US", "GB"])
    with pytest.raises(ValidationError, match="At most two pilot markets"):
        BusinessProfileIn(**data)


def test_negative_money_rejected():
    with pytest.raises(ValidationError):
        physical(monthly_rent_inr=-1)


def test_online_branch_routes_to_online_engines():
    plan = build_plan(demo_profile(), budget=12)
    engines = {t.engine for t in plan.planned}
    assert plan.branch == "online"
    assert {"google_shopping", "google_product", "google_trends", "google", "google_news"} <= engines
    assert "google_maps" not in engines
    assert plan.allocated == 12 and len(plan.planned) == 12
    assert [t.engine for t in plan.skipped] == ["google_autocomplete"]  # lowest priority dropped by budget
    assert plan.analyses["capital_optimisation"]["proceed"] is False


def test_physical_branch_routes_to_maps():
    plan = build_plan(physical(), budget=12)
    engines = [t.engine for t in plan.planned]
    assert plan.branch == "physical"
    assert "google_maps" in engines and "google_trends" in engines
    assert "google_product" not in engines and "amazon" not in engines
    maps_task = next(t for t in plan.planned if t.engine == "google_maps")
    assert maps_task.params["q"] == "coffee roaster in Bandra, Mumbai" and maps_task.params["type"] == "search"


def test_budget_is_never_exceeded_by_plan():
    for budget in (1, 3, 5, 12):
        plan = build_plan(demo_profile(), budget=budget)
        assert len(plan.planned) == budget
        assert min(t.priority for t in plan.skipped) >= max(t.priority for t in plan.planned)


def test_undecided_category_compares_category_level_terms():
    p = BusinessProfileIn(business_type="online", business_stage="new", category="undecided",
                          compare_categories=["food_beverages", "beauty_personal_care"], pilot_country="IN",
                          sales_channel="own_website", sourcing_model="undecided", budget_band="undecided",
                          primary_goal="find_products")
    plan = build_plan(p, budget=12)
    assert [f.level for f in plan.focuses] == ["category", "category"]
    assert any("not recommending a 'best' business" in n for n in plan.notes)
