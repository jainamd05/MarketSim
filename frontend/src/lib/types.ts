/** Types mirroring the backend Pydantic schemas (only the fields the UI reads). */

export type BusinessType = "online" | "physical";
export type BusinessStage = "new" | "existing";
export type DataMode = "live" | "demo";

export interface Option {
  value: string;
  label: string;
  description?: string;
}

export interface Subcategory extends Option {
  unit_basis: "g" | "ml" | "count";
  terms: Record<string, string>;
}

export interface Category extends Option {
  terms: Record<string, string>;
  risk_flags: string[];
  shopping_meaningful_for_physical: boolean;
  subcategories: Subcategory[];
}

export interface Market {
  code: string;
  label: string;
  currency: string;
}

export interface FieldSpec {
  key: string;
  label: string;
  unit: string;
  required?: boolean;
  primary?: boolean;
  applies_to?: BusinessType[];
  stages?: BusinessStage[];
}

export interface Registry {
  version: string;
  business_types: (Option & { enabled: boolean })[];
  business_stages: Option[];
  categories: Category[];
  category_special_options: Option[];
  focus_special_options: Option[];
  limits: { max_compare_focuses: number; max_compare_categories: number; max_pilot_markets: number };
  markets: Market[];
  market_modes: { online: Option[] };
  sales_channels: Record<BusinessType, Option[]>;
  budget_bands: (Option & { min_inr: number | null; max_inr: number | null })[];
  operating_fields: Record<BusinessType, FieldSpec[]>;
  sourcing_models: (Option & { applies_to: BusinessType[] })[];
  goals: Record<BusinessStage, Option[]>;
  advanced_fields: FieldSpec[];
  currencies: { code: string; symbol: string; label: string }[];
}

/** Money/number fields of the profile. `null` means UNKNOWN – never zero. */
export const NUMERIC_FIELDS = [
  "exact_capital_inr", "monthly_ad_budget_inr", "monthly_rent_inr", "monthly_staff_cost_inr",
  "monthly_utilities_inr", "monthly_marketing_budget_inr", "website_platform_cost_inr", "monthly_fixed_costs",
  "product_unit_cost", "selling_price", "average_order_value", "average_transaction_value", "shipping_cost",
  "fulfilment_cost", "payment_or_platform_fees", "expected_return_cost", "expected_monthly_orders",
  "current_monthly_orders", "current_monthly_revenue", "expected_daily_footfall",
] as const;
export type NumericField = (typeof NUMERIC_FIELDS)[number];

export interface BusinessProfileInput extends Partial<Record<NumericField, number | null>> {
  business_type: BusinessType;
  business_stage: BusinessStage;
  category: string;
  custom_category?: string | null;
  compare_categories: string[];
  subcategory?: string | null;
  product_focus?: string | null;
  compare_focuses: string[];
  market_mode?: "single" | "compare" | "other" | null;
  worldwide_ambition: boolean;
  target_countries: string[];
  pilot_country?: string | null;
  city?: string | null;
  locality?: string | null;
  sales_channel: string;
  sourcing_model: string;
  budget_band: string;
  primary_goal: string;
  assumptions: string[];
  currency: string;
}

export interface BusinessProfile extends BusinessProfileInput {
  id: string;
  status: "draft" | "confirmed";
  created_at: string;
  updated_at: string;
}

export interface AppConfig {
  default_data_mode: DataMode;
  demo_mode_setting: string;
  serpapi_configured: boolean;
  live_available: boolean;
  llm_provider: string;
  llm_enabled: boolean;
  llm_model: string | null;
  max_serpapi_requests_per_analysis: number;
  serpapi_cache_ttl_seconds: number;
  fixture_version: string;
  fixtures_synthetic: boolean;
  engines: string[];
}

export interface AnalysisStatus {
  id: string;
  profile_id: string;
  mode: DataMode;
  status: "queued" | "running" | "completed" | "partial" | "failed";
  llm_mode: string;
  current_agent: string | null;
  request_budget: number;
  requests_used: number;
  cache_hits: number;
  fixture_version: string | null;
  progress: { completed_agents: string[]; total_agents: number; percent: number; agents: { id: string; label: string }[] };
  warnings: string[];
  error: string | null;
  profile: BusinessProfileInput;
  plan: ResearchPlan | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface ResearchPlan {
  branch: BusinessType;
  focuses: { value: string; label: string }[];
  countries: string[];
  budget: number;
  allocated: number;
  planned: { task_id: string; engine: string; purpose: string; priority: number }[];
  skipped: { task_id: string; engine: string; purpose: string; priority: number }[];
  missing_inputs: { field: string; label: string; impact: string }[];
  analyses: Record<string, { proceed: boolean; reason: string }>;
  notes: string[];
}

export interface AgentEvent {
  seq: number;
  ts: string;
  agent: string;
  agent_label: string;
  event_type: string;
  message: string;
  meta: Record<string, unknown>;
}

export interface Quantity {
  status: "parsed" | "ambiguous" | "missing";
  amount: number | null;
  base_unit: "g" | "ml" | "count" | null;
  pack_count: number;
  raw: string | null;
}

export interface Listing {
  evidence_ref: string;
  focus: string;
  country: string;
  engine: string;
  title: string;
  merchant: string | null;
  price_text: string | null;
  price: number | null;
  currency: string | null;
  currency_status: string;
  promotion: boolean;
  quantity: Quantity;
  unit_price: number | null;
  unit_price_basis: string | null;
  rating: number | null;
  reviews: number | null;
  source_url: string | null;
  retrieved_at: string;
  flags: string[];
  is_marketplace: boolean;
  included_in_stats: boolean;
}

export interface PriceGroup {
  focus: string;
  focus_label: string;
  country: string;
  currency: string | null;
  sample_size: number;
  included_count: number;
  min: number | null;
  p25: number | null;
  median: number | null;
  p75: number | null;
  max: number | null;
  unit_basis: string | null;
  unit_sample_size: number;
  unit_min: number | null;
  unit_p25: number | null;
  unit_median: number | null;
  unit_p75: number | null;
  unit_max: number | null;
  outlier_refs: string[];
  excluded: { ref: string; reason: string }[];
  promotion_count: number;
  warnings: string[];
}

export interface Competitor {
  key: string;
  name: string;
  relation: "direct" | "marketplace" | "reference";
  relation_reason: string;
  websites: string[];
  countries: string[];
  focuses: string[];
  engines: string[];
  evidence_refs: string[];
  listing_refs: string[];
  product_examples: string[];
  price_min: number | null;
  price_max: number | null;
  currency: string | null;
  rating: number | null;
  reviews: number | null;
  address: string | null;
  snippet: string | null;
  tags: { tag: string; basis: "observed" | "interpretation"; detail: string; evidence_refs: string[] }[];
}

export interface CompetitorsResponse {
  analysis_id: string;
  mode: DataMode;
  countries: string[];
  competitors: Competitor[];
  listings: Listing[];
  price_groups: PriceGroup[];
  product_details: Record<string, unknown>[];
  note: string;
}

export interface TrendSummary {
  query: string;
  points: number;
  mean: number | null;
  change_pct: number | null;
  peak_value: number | null;
  peak_date: string | null;
  direction: "rising" | "declining" | "flat" | "insufficient_data";
  description: string;
}

export interface TrendsResult {
  status: "ok" | "partial" | "unavailable";
  geo: string | null;
  date_range: string | null;
  queries: string[];
  query_focus: Record<string, string>;
  points: Record<string, number | string | boolean | null>[];
  summaries: TrendSummary[];
  related_queries: { query: string; top: { query: string; value: number | null; value_text: string | null }[]; rising: { query: string; value: number | null; value_text: string | null }[] } | null;
  regional_interest: { location: string; value: number | null }[];
  keyword_suggestions: string[];
  evidence_refs: string[];
  normalization_note: string;
  demand_caveat: string;
  retrieved_at: string | null;
  data_origin: string;
  note: string | null;
}

export interface TrendsResponse {
  analysis_id: string;
  mode: DataMode;
  by_country: Record<string, TrendsResult>;
  countries: string[];
}

export interface Assumption {
  key: string;
  label: string;
  value: number | string | null;
  unit: string;
  source: "user_input" | "market_evidence" | "scenario_assumption" | "llm_proposed";
  rationale: string;
  evidence_refs: string[];
}

export interface OnlineSimInputs {
  model: "online";
  currency: string;
  selling_price: number;
  units_per_order: number;
  unit_cost: number;
  packaging_cost_per_order: number;
  shipping_cost_per_order: number;
  platform_fee_pct: number;
  return_rate_pct: number;
  monthly_ad_budget: number;
  cac: number;
  organic_orders: number;
  repeat_orders: number;
  fixed_costs_monthly: number;
  initial_investment: number | null;
  available_capital: number | null;
}

export interface PhysicalSimInputs {
  model: "physical";
  currency: string;
  daily_footfall: number;
  conversion_rate_pct: number;
  opening_days_per_month: number;
  average_transaction_value: number;
  cogs_pct: number;
  card_fee_pct: number;
  shrinkage_pct: number;
  rent: number;
  staff: number;
  utilities: number;
  marketing: number;
  other_fixed: number;
  initial_investment: number | null;
  available_capital: number | null;
}

export type SimInputs = OnlineSimInputs | PhysicalSimInputs;

export interface Strategy {
  key: string;
  archetype: "competitive_pricing" | "premium_differentiation" | "bundles_repeat";
  name: string;
  focus: string;
  focus_label: string;
  summary: string;
  positioning: string;
  product_mix: { name: string; pack_size: string | null; target_price: number | null; unit_cost: number | null; share_pct: number; max_monthly_units: number | null }[];
  price_logic: string;
  channel_choice: string;
  operating_tradeoffs: string[];
  advantages: string[];
  disadvantages: string[];
  assumptions: Assumption[];
  claims: { text: string; kind: "market_fact" | "interpretation"; evidence_refs: string[] }[];
  evidence_refs: string[];
  sim_inputs: SimInputs;
  revision: number;
  revision_notes: string[];
  generated_by: "deterministic" | "llm";
}

export interface FinancialResult {
  model: "online" | "physical";
  currency: string;
  orders: Record<string, number>;
  average_order_value: number;
  revenue: number;
  cost_breakdown: Record<string, number>;
  variable_cost_per_order: number;
  contribution_per_order: number;
  contribution_margin_pct: number;
  total_contribution: number;
  operating_result: number;
  break_even_orders: number | null;
  break_even_status: "achievable" | "already_met" | "not_achievable_negative_contribution";
  break_even_note: string;
  runway_months: number | null;
  runway_note: string;
  capital_check: { status: "within" | "exceeds" | "unknown"; available: number | null; required: number | null; note: string };
  warnings: string[];
}

export interface StrategySimulation {
  strategy_key: string;
  revision: number;
  inputs: SimInputs;
  base: FinancialResult;
  scenarios: { scenario: "bear" | "base" | "bull"; adjustments: Record<string, string>; result: FinancialResult }[];
  monte_carlo: {
    iterations: number;
    seed: number;
    distributions: { parameter: string; distribution: string; parameters: Record<string, number>; description: string }[];
    percentiles: Record<string, number>;
    mean: number;
    prob_negative: number;
    histogram: { bin_start: number; bin_end: number; count: number }[];
    note: string;
  };
  optimization: {
    status: "optimal" | "infeasible" | "disabled_capital_unknown" | "not_applicable";
    message: string;
    budget: number | null;
    method: string | null;
    allocations: { name: string; units: number; cost: number; expected_contribution: number; cap: number }[];
    total_cost: number | null;
    total_expected_contribution: number | null;
  };
}

export interface CriticCheck {
  id: string;
  label: string;
  status: "pass" | "fail" | "warn" | "not_applicable";
  severity: "blocking" | "advisory";
  reason: string;
  evidence_refs: string[];
}

export interface CriticRound {
  round: number;
  decision: "accept" | "revise" | "accept_with_unresolved";
  evaluations: { strategy_key: string; revision: number; passed: boolean; checks: CriticCheck[]; revision_requests: { check_id: string; instruction: string }[] }[];
}

export interface StrategiesResponse {
  analysis_id: string;
  mode: DataMode;
  strategies: Strategy[];
  simulations: Record<string, StrategySimulation>;
  history: Strategy[];
  critic_rounds: CriticRound[];
}

export interface Citation {
  ref: string;
  title: string;
  url: string | null;
  engine: string;
  query: string;
  country: string | null;
  retrieved_at: string;
  freshness: string;
  data_origin: string;
  classification: string;
  published_at: string | null;
}

export interface Risk {
  id: string;
  title: string;
  detail: string;
  severity: "low" | "medium" | "high";
  basis: "evidence" | "category_guidance" | "model_assumption" | "missing_input";
  evidence_refs: string[];
}

export interface Report {
  analysis_id: string;
  mode: DataMode;
  llm_mode: string;
  generated_at: string;
  status: "completed" | "partial";
  disclaimer: string;
  profile_summary: Record<string, unknown> & { unknown_inputs: string[] };
  headline_findings: { kind: "observed" | "modeled" | "critic"; text: string; refs: string[] }[];
  observed_facts: { type: string; text: string; refs: string[]; warnings?: string[]; nature?: string; topic?: string }[];
  modeled_scenarios: {
    strategy: string; name: string; revision: number; currency: string;
    operating_result: { bear: number; base: number; bull: number };
    contribution_per_order: number; break_even_orders: number | null; share_negative: number; label: string;
  }[];
  strategies: { key: string; name: string; revision: number; revision_notes: string[] }[];
  critic_summary: { revisions_performed: number; final_decision: string; unresolved_failures: { strategy: string; check: string; reason: string }[] };
  assumptions: (Assumption & { strategy: string })[];
  risks: Risk[];
  unresolved_questions: string[];
  limitations: string[];
  citations: Citation[];
  search_usage: { mode: string; budget: number; used: number; remaining: number; cache_hits: number; deduplicated: number; by_status: Record<string, number>; billable_note: string };
  inputs_hash: string;
}

export interface ReportResponse {
  analysis_id: string;
  inputs_hash: string;
  content_hash: string;
  report: Report;
}

export interface EvidenceItem {
  ref: string;
  kind: string;
  engine: string;
  query: string;
  country: string | null;
  title: string;
  source_url: string | null;
  classification: string;
  freshness: string;
  data_origin: string;
  published_at: string | null;
  retrieved_at: string;
  normalized: Record<string, unknown>;
}

export interface SearchRecord {
  engine: string;
  params: Record<string, string>;
  agent: string;
  purpose: string;
  status: string;
  data_origin: string;
  result_count: number;
  duration_ms: number;
  attempts: number;
  error: string | null;
  requested_at: string;
}

export interface EvidenceResponse {
  analysis_id: string;
  mode: DataMode;
  evidence: EvidenceItem[];
  searches: SearchRecord[];
}
