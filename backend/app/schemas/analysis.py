"""Pydantic schemas for research evidence, strategies, simulations, critique and reports."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

DataOrigin = Literal["live", "cache", "demo_fixture", "none"]
Freshness = Literal["current", "recent", "stale", "unknown", "demo_fixture"]


# --------------------------------------------------------------------- search
class SearchOutcome(BaseModel):
    """Result of one gateway call. ``data`` is the raw SerpApi JSON (never includes the key)."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    engine: str
    params: dict[str, Any]
    purpose: str = ""
    agent: str = ""
    status: Literal["ok", "empty", "failed", "skipped_budget", "fixture_missing", "blocked", "deduplicated"]
    data_origin: DataOrigin = "none"
    data: dict[str, Any] | None = None
    error: str | None = None
    http_status: int | None = None
    attempts: int = 0
    duration_ms: float = 0.0
    result_count: int = 0
    retrieved_at: datetime
    search_id: str | None = None

    @property
    def usable(self) -> bool:
        return self.status in {"ok", "deduplicated"} and self.data is not None

    def summary(self) -> dict[str, Any]:
        return self.model_dump(exclude={"data"}, mode="json")


class Observation(BaseModel):
    """One normalized market observation with full provenance."""

    ref: str
    kind: Literal[
        "product_listing", "marketplace_listing", "product_detail", "competitor_page", "local_business",
        "trend_series", "related_query", "regional_interest", "news_article", "keyword_suggestion",
    ]
    engine: str
    query: str
    country: str | None
    retrieved_at: datetime
    source_url: str | None = None
    source_id: str | None = None
    title: str = ""
    classification: Literal[
        "advertised_listing", "search_snippet", "map_listing", "relative_search_interest",
        "reported_news", "forward_looking_news", "search_suggestion", "product_page_data",
    ]
    freshness: Freshness
    data_origin: DataOrigin
    published_at: str | None = None
    focus: str | None = None
    normalized: dict[str, Any] = Field(default_factory=dict)
    original: dict[str, Any] = Field(default_factory=dict)


# ------------------------------------------------------------------- planning
class FocusSpec(BaseModel):
    value: str
    label: str
    level: Literal["subcategory", "category", "custom"] = "subcategory"
    unit_basis: Literal["g", "ml", "count"] = "count"
    terms: dict[str, str]


class PlannedSearch(BaseModel):
    task_id: str
    agent: str
    engine: str
    params: dict[str, Any]
    purpose: str
    priority: int
    focus: str | None = None
    country: str | None = None
    depends_on: str | None = None  # e.g. product details resolved from shopping results
    status: Literal["planned", "skipped_budget"] = "planned"


class MissingInput(BaseModel):
    field: str
    label: str
    impact: str
    blocking: bool = False


class ResearchPlan(BaseModel):
    branch: Literal["online", "physical"]
    focuses: list[FocusSpec]
    countries: list[str]
    budget: int
    allocated: int
    planned: list[PlannedSearch]
    skipped: list[PlannedSearch]
    missing_inputs: list[MissingInput]
    analyses: dict[str, dict[str, Any]]
    notes: list[str] = Field(default_factory=list)


# ------------------------------------------------------------ competitors/pricing
class Quantity(BaseModel):
    status: Literal["parsed", "ambiguous", "missing"]
    amount: float | None = None  # total amount in base unit (g, ml or count)
    base_unit: Literal["g", "ml", "count"] | None = None
    pack_count: int = 1
    raw: str | None = None


class Listing(BaseModel):
    evidence_ref: str
    focus: str
    country: str
    engine: str
    title: str
    merchant: str | None = None
    merchant_key: str | None = None
    product_id: str | None = None
    price_text: str | None = None
    price: float | None = None
    currency: str | None = None
    currency_status: Literal["detected", "inferred_from_market", "missing", "mismatch"] = "missing"
    old_price: float | None = None
    promotion: bool = False
    quantity: Quantity
    unit_price: float | None = None
    unit_price_basis: Literal["per_100g", "per_100ml", "per_unit"] | None = None
    rating: float | None = None
    reviews: int | None = None
    delivery: str | None = None
    source_url: str | None = None
    retrieved_at: datetime
    flags: list[str] = Field(default_factory=list)
    is_marketplace: bool = False
    included_in_stats: bool = True


class PriceGroupStats(BaseModel):
    focus: str
    focus_label: str
    country: str
    currency: str | None
    sample_size: int
    included_count: int
    min: float | None = None
    p25: float | None = None
    median: float | None = None
    p75: float | None = None
    max: float | None = None
    unit_basis: str | None = None
    unit_sample_size: int = 0
    unit_min: float | None = None
    unit_p25: float | None = None
    unit_median: float | None = None
    unit_p75: float | None = None
    unit_max: float | None = None
    outlier_refs: list[str] = Field(default_factory=list)
    excluded: list[dict[str, str]] = Field(default_factory=list)
    promotion_count: int = 0
    warnings: list[str] = Field(default_factory=list)


class PositioningTag(BaseModel):
    tag: str
    basis: Literal["observed", "interpretation"]
    detail: str
    evidence_refs: list[str] = Field(default_factory=list)


class CompetitorEntry(BaseModel):
    key: str
    name: str
    relation: Literal["direct", "marketplace", "reference"]
    relation_reason: str
    websites: list[str] = Field(default_factory=list)
    countries: list[str] = Field(default_factory=list)
    focuses: list[str] = Field(default_factory=list)
    engines: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    listing_refs: list[str] = Field(default_factory=list)
    product_examples: list[str] = Field(default_factory=list)
    price_min: float | None = None
    price_max: float | None = None
    currency: str | None = None
    rating: float | None = None
    reviews: int | None = None
    address: str | None = None
    snippet: str | None = None
    tags: list[PositioningTag] = Field(default_factory=list)


# --------------------------------------------------------------------- trends
class TrendSeriesSummary(BaseModel):
    query: str
    points: int
    mean: float | None
    first_period_avg: float | None
    last_period_avg: float | None
    change_pct: float | None
    peak_value: float | None
    peak_date: str | None
    direction: Literal["rising", "declining", "flat", "insufficient_data"]
    description: str


class TrendsResult(BaseModel):
    status: Literal["ok", "partial", "unavailable"]
    geo: str | None = None
    date_range: str | None = None
    queries: list[str] = Field(default_factory=list)
    query_focus: dict[str, str] = Field(default_factory=dict)
    points: list[dict[str, Any]] = Field(default_factory=list)  # {date,timestamp,partial,<query>: value}
    summaries: list[TrendSeriesSummary] = Field(default_factory=list)
    related_queries: dict[str, Any] | None = None
    regional_interest: list[dict[str, Any]] = Field(default_factory=list)
    keyword_suggestions: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    normalization_note: str = (
        "Google Trends values are relative search interest indexed 0–100 against the highest point among the "
        "compared terms for the selected region and time range. They are not search volumes."
    )
    demand_caveat: str = (
        "Search interest is not sales demand. No customer counts, market size, conversion rates or sales volumes "
        "are derived from these values."
    )
    retrieved_at: datetime | None = None
    data_origin: DataOrigin = "none"
    note: str | None = None


# ----------------------------------------------------------------------- news
class NewsItem(BaseModel):
    ref: str
    title: str
    link: str | None
    source: str | None
    published_at: str | None
    date_text: str | None
    age_days: int | None
    freshness: Freshness
    topic: Literal["competitor", "product_launch", "supply", "regulatory", "funding", "market", "other"]
    nature: Literal["reported_development", "forward_looking"]
    related_competitors: list[str] = Field(default_factory=list)
    snippet: str | None = None


class RiskItem(BaseModel):
    id: str
    title: str
    detail: str
    severity: Literal["low", "medium", "high"]
    basis: Literal["evidence", "category_guidance", "model_assumption", "missing_input"]
    evidence_refs: list[str] = Field(default_factory=list)


class NewsResult(BaseModel):
    status: Literal["ok", "partial", "unavailable"]
    items: list[NewsItem] = Field(default_factory=list)
    risks: list[RiskItem] = Field(default_factory=list)
    insufficient_evidence: bool = False
    note: str | None = None


# ----------------------------------------------------------------- simulation
class OnlineSimInputs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: Literal["online"] = "online"
    currency: str = "INR"
    selling_price: float = Field(gt=0, description="price per unit")
    units_per_order: float = Field(default=1.0, gt=0, le=50)
    unit_cost: float = Field(ge=0, description="landed product cost per unit")
    packaging_cost_per_order: float = Field(default=0.0, ge=0)
    shipping_cost_per_order: float = Field(default=0.0, ge=0)
    platform_fee_pct: float = Field(default=0.0, ge=0, le=100)
    return_rate_pct: float = Field(default=0.0, ge=0, le=100)
    monthly_ad_budget: float = Field(default=0.0, ge=0)
    cac: float = Field(gt=0, description="assumed advertising cost per ad-acquired order")
    organic_orders: float = Field(default=0.0, ge=0)
    repeat_orders: float = Field(default=0.0, ge=0)
    fixed_costs_monthly: float = Field(default=0.0, ge=0)
    initial_investment: float | None = Field(default=None, ge=0)
    available_capital: float | None = Field(default=None, ge=0)


class PhysicalSimInputs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: Literal["physical"] = "physical"
    currency: str = "INR"
    daily_footfall: float = Field(ge=0)
    conversion_rate_pct: float = Field(ge=0, le=100)
    opening_days_per_month: float = Field(default=26, ge=1, le=31)
    average_transaction_value: float = Field(gt=0)
    cogs_pct: float = Field(ge=0, le=100, description="cost of goods as % of sales")
    card_fee_pct: float = Field(default=0.0, ge=0, le=100)
    shrinkage_pct: float = Field(default=0.0, ge=0, le=100)
    rent: float = Field(default=0.0, ge=0)
    staff: float = Field(default=0.0, ge=0)
    utilities: float = Field(default=0.0, ge=0)
    marketing: float = Field(default=0.0, ge=0)
    other_fixed: float = Field(default=0.0, ge=0)
    initial_investment: float | None = Field(default=None, ge=0)
    available_capital: float | None = Field(default=None, ge=0)


SimInputs = Annotated[Union[OnlineSimInputs, PhysicalSimInputs], Field(discriminator="model")]


class CapitalCheck(BaseModel):
    status: Literal["within", "exceeds", "unknown"]
    available: float | None
    required: float | None
    note: str


class FinancialResult(BaseModel):
    model: Literal["online", "physical"]
    currency: str
    orders: dict[str, float]  # ad_acquired / organic / repeat / total (or transactions)
    average_order_value: float
    revenue: float
    cost_breakdown: dict[str, float]
    variable_cost_per_order: float
    contribution_per_order: float
    contribution_margin_pct: float
    total_contribution: float
    operating_result: float
    break_even_orders: int | None
    break_even_status: Literal["achievable", "already_met", "not_achievable_negative_contribution"]
    break_even_note: str
    runway_months: float | None
    runway_note: str
    capital_check: CapitalCheck
    warnings: list[str] = Field(default_factory=list)


class ScenarioResult(BaseModel):
    scenario: Literal["bear", "base", "bull"]
    adjustments: dict[str, str]
    inputs: dict[str, Any]
    result: FinancialResult


class DistributionSpec(BaseModel):
    parameter: str
    distribution: str
    parameters: dict[str, float]
    description: str


class MonteCarloResult(BaseModel):
    iterations: int
    seed: int
    distributions: list[DistributionSpec]
    percentiles: dict[str, float]
    mean: float
    prob_negative: float
    histogram: list[dict[str, float]]
    note: str = (
        "Scenario frequencies come from the assumed distributions listed here. They are not empirically "
        "calibrated real-world probabilities."
    )


class OptimizationResult(BaseModel):
    status: Literal["optimal", "infeasible", "disabled_capital_unknown", "not_applicable"]
    message: str
    budget: float | None = None
    method: str | None = None
    allocations: list[dict[str, Any]] = Field(default_factory=list)
    total_cost: float | None = None
    total_expected_contribution: float | None = None


class StrategySimulation(BaseModel):
    strategy_key: str
    revision: int
    inputs: dict[str, Any]
    base: FinancialResult
    scenarios: list[ScenarioResult]
    monte_carlo: MonteCarloResult
    optimization: OptimizationResult


# ------------------------------------------------------------------- strategy
class Assumption(BaseModel):
    key: str
    label: str
    value: float | str | None
    unit: str
    source: Literal["user_input", "market_evidence", "scenario_assumption", "llm_proposed"]
    rationale: str
    evidence_refs: list[str] = Field(default_factory=list)
    editable: bool = True


class Claim(BaseModel):
    text: str
    kind: Literal["market_fact", "interpretation"]
    evidence_refs: list[str] = Field(default_factory=list)


class ProductMixItem(BaseModel):
    name: str
    focus: str
    pack_size: str | None = None
    target_price: float | None = None
    unit_cost: float | None = None
    share_pct: float = Field(ge=0, le=100)
    max_monthly_units: int | None = None
    evidence_refs: list[str] = Field(default_factory=list)


Archetype = Literal["competitive_pricing", "premium_differentiation", "bundles_repeat"]


class Strategy(BaseModel):
    key: str
    archetype: Archetype
    name: str
    focus: str
    focus_label: str
    summary: str
    positioning: str
    product_mix: list[ProductMixItem]
    price_logic: str
    channel_choice: str
    operating_tradeoffs: list[str]
    advantages: list[str]
    disadvantages: list[str]
    assumptions: list[Assumption]
    claims: list[Claim]
    evidence_refs: list[str]
    sim_inputs: SimInputs
    revision: int = 0
    revision_notes: list[str] = Field(default_factory=list)
    generated_by: Literal["deterministic", "llm"] = "deterministic"


class LLMStrategyDraft(BaseModel):
    """Shape the LLM must return for one strategy (validated before use)."""

    archetype: Archetype
    name: str = Field(max_length=80)
    focus: str
    summary: str = Field(max_length=600)
    positioning: str = Field(max_length=600)
    price_logic: str = Field(max_length=600)
    channel_choice: str = Field(max_length=400)
    operating_tradeoffs: list[str] = Field(max_length=6)
    advantages: list[str] = Field(max_length=6)
    disadvantages: list[str] = Field(max_length=6)
    claims: list[Claim] = Field(max_length=8)
    price_position: Literal["below_median", "at_median", "above_median"]
    proposed_cac: float | None = Field(default=None, gt=0)
    proposed_units_per_order: float | None = Field(default=None, gt=0, le=10)


class LLMStrategySet(BaseModel):
    strategies: list[LLMStrategyDraft] = Field(min_length=3, max_length=3)


# --------------------------------------------------------------------- critic
class CriticCheck(BaseModel):
    id: str
    label: str
    status: Literal["pass", "fail", "warn", "not_applicable"]
    severity: Literal["blocking", "advisory"]
    reason: str
    evidence_refs: list[str] = Field(default_factory=list)


class RevisionRequest(BaseModel):
    strategy_key: str
    check_id: str
    instruction: str
    target_field: str


class CriticEvaluationResult(BaseModel):
    round: int
    strategy_key: str
    revision: int
    passed: bool
    checks: list[CriticCheck]
    revision_requests: list[RevisionRequest] = Field(default_factory=list)


# --------------------------------------------------------------------- report
class ReportSection(BaseModel):
    title: str
    items: list[dict[str, Any]]


class AnalysisReportContent(BaseModel):
    analysis_id: str
    mode: Literal["live", "demo"]
    llm_mode: str
    generated_at: datetime
    status: Literal["completed", "partial"]
    disclaimer: str
    profile_summary: dict[str, Any]
    headline_findings: list[dict[str, Any]]
    observed_facts: list[dict[str, Any]]
    modeled_scenarios: list[dict[str, Any]]
    strategies: list[dict[str, Any]]
    critic_summary: dict[str, Any]
    assumptions: list[dict[str, Any]]
    risks: list[dict[str, Any]]
    unresolved_questions: list[str]
    limitations: list[str]
    citations: list[dict[str, Any]]
    search_usage: dict[str, Any]
    inputs_hash: str
