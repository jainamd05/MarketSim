import { describe, expect, it } from "vitest";
import {
  advancedFields, emptyDraft, firstInvalidStep, fromProfile, operatingFields, reconcile, sourcingOptions,
  toProfilePayload, validateStep, visibleSteps, type Draft,
} from "./flow";

const demo: Draft = {
  ...emptyDraft(),
  business_type: "online", business_stage: "new", category: "food_beverages", subcategory: "undecided",
  compare_focuses: ["packaged_snacks", "coffee_tea", "premium_pantry"], market_mode: "single", pilot_country: "IN",
  worldwide_ambition: true, sales_channel: "website_and_marketplaces", budget_band: "above_10l",
  monthly_ad_budget_inr: 40000, sourcing_model: "undecided", primary_goal: "competitor_intelligence",
};

describe("dynamic question routing", () => {
  it("skips the focus step for Other and Undecided categories", () => {
    expect(visibleSteps({ category: "food_beverages" })).toContain("focus");
    expect(visibleSteps({ category: "other" })).not.toContain("focus");
    expect(visibleSteps({ category: "undecided" })).not.toContain("focus");
  });

  it("asks different operating questions for online vs physical", () => {
    expect(operatingFields("online").map((f) => f.key)).toEqual(
      ["monthly_ad_budget_inr", "shipping_cost", "website_platform_cost_inr", "product_unit_cost"]);
    expect(operatingFields("physical").map((f) => f.key)).toEqual(
      ["monthly_rent_inr", "monthly_staff_cost_inr", "monthly_utilities_inr", "monthly_marketing_budget_inr"]);
  });

  it("shows only relevant advanced fields and never repeats an operating question", () => {
    const online = advancedFields({ business_type: "online", business_stage: "new" }).map((f) => f.key);
    expect(online).toContain("average_order_value");
    expect(online).toContain("expected_monthly_orders");
    expect(online).not.toContain("product_unit_cost"); // already asked in operating step
    expect(online).not.toContain("expected_daily_footfall");
    expect(online).not.toContain("current_monthly_revenue");
    const physicalExisting = advancedFields({ business_type: "physical", business_stage: "existing" }).map((f) => f.key);
    expect(physicalExisting).toContain("expected_daily_footfall");
    expect(physicalExisting).toContain("current_monthly_revenue");
    expect(physicalExisting).not.toContain("average_order_value");
  });

  it("offers dropshipping only to online businesses", () => {
    expect(sourcingOptions("online").map((s) => s.value)).toContain("dropshipping");
    expect(sourcingOptions("physical").map((s) => s.value)).not.toContain("dropshipping");
  });

  it("clears answers invalidated by a changed earlier answer", () => {
    const changed = reconcile({ ...demo, business_type: "physical", sourcing_model: "dropshipping" });
    expect(changed.sales_channel).toBe("");
    expect(changed.sourcing_model).toBe("");
    expect(reconcile({ ...demo, business_stage: "existing" }).primary_goal).toBe("");
  });
});

describe("step validation", () => {
  it("requires a business type", () => {
    expect(validateStep("business_type", emptyDraft())).toHaveProperty("business_type");
  });
  it("requires a custom category for Other and 2–3 comparisons for Undecided", () => {
    expect(validateStep("category", { ...emptyDraft(), category: "other" })).toHaveProperty("custom_category");
    expect(validateStep("category", { ...emptyDraft(), category: "undecided", compare_categories: ["food_beverages"] }))
      .toHaveProperty("compare_categories");
    expect(validateStep("category", { ...emptyDraft(), category: "other", custom_category: "Stationery" })).toEqual({});
  });
  it("validates focus options against the selected category", () => {
    expect(validateStep("focus", { ...emptyDraft(), category: "food_beverages", subcategory: "skincare" })).toHaveProperty("subcategory");
    expect(validateStep("focus", { ...emptyDraft(), category: "food_beverages", subcategory: "undecided", compare_focuses: ["coffee_tea"] }))
      .toHaveProperty("compare_focuses");
  });
  it("requires a city for physical shops and a pilot for online/worldwide", () => {
    expect(validateStep("market", { ...emptyDraft(), business_type: "physical", pilot_country: "IN" })).toHaveProperty("city");
    expect(validateStep("market", { ...emptyDraft(), business_type: "online", market_mode: "single" })).toHaveProperty("pilot_country");
    expect(validateStep("market", { ...emptyDraft(), business_type: "online", market_mode: "other", pilot_country: "Singapore" }))
      .toHaveProperty("pilot_country");
    expect(validateStep("market", { ...emptyDraft(), business_type: "online", market_mode: "compare", target_countries: ["IN"] }))
      .toHaveProperty("target_countries");
  });
  it("rejects negative money and percentages above 100", () => {
    expect(validateStep("operating", { ...demo, shipping_cost: -5 })).toHaveProperty("shipping_cost");
    expect(validateStep("advanced", { ...demo, payment_or_platform_fees: 140 })).toHaveProperty("payment_or_platform_fees");
    expect(validateStep("advanced", { ...demo, payment_or_platform_fees: null })).toEqual({});
  });
  it("accepts the demonstration profile end to end", () => {
    expect(firstInvalidStep(demo)).toBeNull();
  });
});

describe("profile payload", () => {
  it("keeps unknown inputs as null and drops irrelevant answers", () => {
    const p = toProfilePayload({ ...demo, monthly_rent_inr: 50000 });
    expect(p.exact_capital_inr).toBeNull();
    expect(p.product_unit_cost).toBeNull();
    expect(p.monthly_rent_inr).toBeNull(); // rent is not asked for online businesses
    expect(p.monthly_ad_budget_inr).toBe(40000);
    expect(p.target_countries).toEqual(["IN"]);
    expect(p.worldwide_ambition).toBe(true);
    expect(p.compare_focuses).toEqual(["packaged_snacks", "coffee_tea", "premium_pantry"]);
    expect(p.city).toBeNull();
  });
  it("round-trips through fromProfile", () => {
    expect(toProfilePayload(fromProfile(toProfilePayload(demo)))).toEqual(toProfilePayload(demo));
  });
  it("puts the primary pilot first when comparing two markets", () => {
    const p = toProfilePayload({ ...demo, market_mode: "compare", target_countries: ["US", "IN"], pilot_country: "IN" });
    expect(p.target_countries).toEqual(["IN", "US"]);
  });
});
