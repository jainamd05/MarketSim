"""Strongly typed BusinessProfile.

Rules encoded here:
* Missing financial inputs are ``None`` (unknown) – never silently coerced to 0.
* Geography (country codes) and currency are separate fields.
* Country codes are ISO-3166 alpha-2 internally; the frontend shows names.
* A budget band is not an exact amount; ``exact_capital_inr`` is only set when the
  user typed a number.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.onboarding import registry

BusinessType = Literal["online", "physical"]  # "hybrid" is reserved in the registry
BusinessStage = Literal["new", "existing"]
MarketMode = Literal["single", "compare", "other"]

Money = Annotated[float, Field(ge=0, le=1e11)]
Percent = Annotated[float, Field(ge=0, le=100)]
Count = Annotated[float, Field(ge=0, le=1e9)]

_ISO2 = re.compile(r"^[A-Z]{2}$")

# Field metadata used by the UI review screen and by the report (unit + currency).
FINANCIAL_FIELD_UNITS: dict[str, str] = {
    "exact_capital_inr": "INR (one-off)",
    "monthly_ad_budget_inr": "INR / month",
    "monthly_rent_inr": "INR / month",
    "monthly_staff_cost_inr": "INR / month",
    "monthly_utilities_inr": "INR / month",
    "monthly_marketing_budget_inr": "INR / month",
    "website_platform_cost_inr": "INR / month",
    "monthly_fixed_costs": "{currency} / month",
    "product_unit_cost": "{currency} / unit",
    "selling_price": "{currency} / unit",
    "average_order_value": "{currency} / order",
    "average_transaction_value": "{currency} / transaction",
    "shipping_cost": "{currency} / order",
    "fulfilment_cost": "{currency} / order",
    "payment_or_platform_fees": "% of order value",
    "expected_return_cost": "% of order value",
    "expected_monthly_orders": "orders / month",
    "current_monthly_orders": "orders / month",
    "current_monthly_revenue": "{currency} / month",
    "expected_daily_footfall": "visitors / day",
}


class BusinessProfileIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    business_type: BusinessType
    business_stage: BusinessStage
    category: str = Field(min_length=1, max_length=64)
    custom_category: str | None = Field(default=None, max_length=120)
    compare_categories: list[str] = Field(default_factory=list)
    subcategory: str | None = Field(default=None, max_length=64)
    product_focus: str | None = Field(default=None, max_length=160)
    compare_focuses: list[str] = Field(default_factory=list)

    market_mode: MarketMode | None = None
    worldwide_ambition: bool = False
    target_countries: list[str] = Field(default_factory=list)
    pilot_country: str | None = None
    city: str | None = Field(default=None, max_length=80)
    locality: str | None = Field(default=None, max_length=120)

    sales_channel: str
    sourcing_model: str
    budget_band: str
    primary_goal: str

    exact_capital_inr: Money | None = None
    monthly_ad_budget_inr: Money | None = None
    monthly_rent_inr: Money | None = None
    monthly_staff_cost_inr: Money | None = None
    monthly_utilities_inr: Money | None = None
    monthly_marketing_budget_inr: Money | None = None
    website_platform_cost_inr: Money | None = None
    monthly_fixed_costs: Money | None = None
    product_unit_cost: Money | None = None
    selling_price: Money | None = None
    average_order_value: Money | None = None
    average_transaction_value: Money | None = None
    shipping_cost: Money | None = None
    fulfilment_cost: Money | None = None
    payment_or_platform_fees: Percent | None = Field(default=None, description="% of order value")
    expected_return_cost: Percent | None = Field(default=None, description="% of order value refunded/returned")
    expected_monthly_orders: Count | None = None
    current_monthly_orders: Count | None = None
    current_monthly_revenue: Money | None = None
    expected_daily_footfall: Count | None = None

    assumptions: list[str] = Field(default_factory=list, max_length=20)
    currency: str = Field(default="INR", pattern=r"^[A-Z]{3}$")

    # ------------------------------------------------------------- validators
    @field_validator("pilot_country", mode="before")
    @classmethod
    def _upper_country(cls, v: object) -> object:
        if isinstance(v, str):
            v = v.strip().upper()
            return v or None
        return v

    @field_validator("target_countries", mode="before")
    @classmethod
    def _upper_countries(cls, v: object) -> object:
        if isinstance(v, list):
            out: list[str] = []
            for item in v:
                code = str(item).strip().upper()
                if code and code not in out:
                    out.append(code)
            return out
        return v

    @field_validator("city", "locality", "custom_category", "product_focus", mode="before")
    @classmethod
    def _strip(cls, v: object) -> object:
        if isinstance(v, str):
            v = v.strip()
            return v or None
        return v

    @model_validator(mode="after")
    def _cross_field_rules(self) -> "BusinessProfileIn":
        reg = registry.load_registry()
        errors: list[str] = []

        # Category / sub-category against the registry
        category_values = {c["value"] for c in reg["categories"]} | {"other", "undecided"}
        if self.category not in category_values:
            errors.append(f"Unknown category '{self.category}'.")
        if self.category == "other" and not self.custom_category:
            errors.append("custom_category is required when category is 'other'.")
        if self.category == "undecided":
            unknown = [c for c in self.compare_categories if registry.category(c) is None]
            if unknown:
                errors.append(f"Unknown compare_categories: {unknown}.")
            if len(self.compare_categories) > reg["limits"]["max_compare_categories"]:
                errors.append("Too many compare_categories.")
        cat = registry.category(self.category)
        if cat is not None:
            sub_values = {s["value"] for s in cat["subcategories"]} | {"other", "undecided"}
            if self.subcategory is None:
                errors.append("subcategory (product focus) is required for this category.")
            elif self.subcategory not in sub_values:
                errors.append(f"Unknown subcategory '{self.subcategory}' for {self.category}.")
            if self.subcategory == "other" and not self.product_focus:
                errors.append("product_focus is required when subcategory is 'other'.")
            if self.subcategory == "undecided":
                bad = [f for f in self.compare_focuses if f not in sub_values - {"other", "undecided"}]
                if bad:
                    errors.append(f"Unknown compare_focuses: {bad}.")
            if len(self.compare_focuses) > reg["limits"]["max_compare_focuses"]:
                errors.append("At most three product focuses can be compared.")

        # Geography
        for code in [*self.target_countries, *([self.pilot_country] if self.pilot_country else [])]:
            if not _ISO2.match(code):
                errors.append(f"Country code '{code}' must be ISO-3166 alpha-2.")
        if not self.pilot_country:
            errors.append(
                "A pilot country is required for an actionable analysis"
                + (" (worldwide ambition is recorded separately)." if self.worldwide_ambition else ".")
            )
        if self.pilot_country and self.pilot_country not in self.target_countries:
            self.target_countries = [self.pilot_country, *self.target_countries]
        if len(self.target_countries) > reg["limits"]["max_pilot_markets"]:
            errors.append("At most two pilot markets can be compared within the normal search budget.")
        if self.business_type == "physical":
            if not self.city:
                errors.append("City is required for a physical shop.")
            if len(self.target_countries) > 1:
                errors.append("A physical shop analysis targets one country.")

        # Channel / sourcing / goal / budget
        channel_values = registry.valid_values(reg["sales_channels"][self.business_type])
        if self.sales_channel not in channel_values:
            errors.append(f"Sales channel '{self.sales_channel}' is not valid for {self.business_type} businesses.")
        sourcing = next((s for s in reg["sourcing_models"] if s["value"] == self.sourcing_model), None)
        if sourcing is None or self.business_type not in sourcing["applies_to"]:
            errors.append(f"Sourcing model '{self.sourcing_model}' is not valid for {self.business_type} businesses.")
        if self.primary_goal not in registry.valid_values(reg["goals"][self.business_stage]):
            errors.append(f"Goal '{self.primary_goal}' is not valid for a {self.business_stage} business.")
        if registry.budget_band(self.budget_band) is None:
            errors.append(f"Unknown budget band '{self.budget_band}'.")

        if errors:
            raise ValueError("; ".join(errors))
        return self

    # ---------------------------------------------------------------- helpers
    @property
    def focus_values(self) -> list[str]:
        """Sub-category values the research should cover (bounded to 3)."""
        if self.subcategory == "undecided":
            return self.compare_focuses[:3]
        if self.subcategory and self.subcategory not in {"other"}:
            return [self.subcategory]
        return []

    def unknown_financial_fields(self) -> list[str]:
        relevant = {
            "online": ["exact_capital_inr", "monthly_ad_budget_inr", "average_order_value", "product_unit_cost",
                       "shipping_cost", "payment_or_platform_fees", "expected_return_cost", "monthly_fixed_costs"],
            "physical": ["exact_capital_inr", "monthly_rent_inr", "monthly_staff_cost_inr", "monthly_utilities_inr",
                         "average_transaction_value", "product_unit_cost", "expected_daily_footfall"],
        }[self.business_type]
        return [f for f in relevant if getattr(self, f) is None]


class BusinessProfile(BusinessProfileIn):
    model_config = ConfigDict(extra="ignore")

    id: str
    status: Literal["draft", "confirmed"] = "draft"
    created_at: datetime
    updated_at: datetime


class ProfileCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile: BusinessProfileIn
    status: Literal["draft", "confirmed"] = "draft"


def demo_profile() -> BusinessProfileIn:
    """Required demonstration profile (section 14 of the brief)."""
    return BusinessProfileIn(
        business_type="online",
        business_stage="new",
        category="food_beverages",
        subcategory="undecided",
        compare_focuses=["packaged_snacks", "coffee_tea", "premium_pantry"],
        market_mode="single",
        worldwide_ambition=True,
        target_countries=["IN"],
        pilot_country="IN",
        sales_channel="website_and_marketplaces",
        sourcing_model="undecided",
        budget_band="above_10l",
        exact_capital_inr=None,
        monthly_ad_budget_inr=40_000,
        primary_goal="competitor_intelligence",
        currency="INR",
    )
