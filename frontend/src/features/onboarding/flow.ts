/**
 * Branching onboarding flow – pure functions, no React.
 *
 * The question registry (shared/questionnaire.json) drives every option; this module
 * only decides which steps are visible, validates a step with Zod, and converts the
 * draft into the backend BusinessProfile payload. Unanswered numbers stay `null`
 * (unknown) – they are never coerced to zero.
 */
import { z } from "zod";
import registryJson from "@shared/questionnaire.json";
import {
  NUMERIC_FIELDS, type BusinessProfileInput, type BusinessType, type FieldSpec, type NumericField, type Registry,
} from "@/lib/types";

export const registry = registryJson as unknown as Registry;

export type StepId =
  | "business_type" | "stage" | "category" | "focus" | "market" | "channel"
  | "capital" | "operating" | "sourcing" | "goal" | "advanced";

export const STEP_TITLES: Record<StepId, string> = {
  business_type: "Business type",
  stage: "Business stage",
  category: "Category",
  focus: "Product focus",
  market: "Geographic market",
  channel: "Sales channel",
  capital: "Investment budget",
  operating: "Operating budget",
  sourcing: "Sourcing model",
  goal: "Main goal",
  advanced: "Advanced financials",
};

const ALL_STEPS: StepId[] = ["business_type", "stage", "category", "focus", "market", "channel", "capital",
  "operating", "sourcing", "goal", "advanced"];

type NumericDraft = { [K in NumericField]: number | null };

export interface Draft extends NumericDraft {
  business_type: BusinessType | "";
  business_stage: "new" | "existing" | "";
  category: string;
  custom_category: string;
  compare_categories: string[];
  subcategory: string;
  product_focus: string;
  compare_focuses: string[];
  market_mode: "single" | "compare" | "other" | "";
  worldwide_ambition: boolean;
  target_countries: string[];
  pilot_country: string;
  city: string;
  locality: string;
  sales_channel: string;
  sourcing_model: string;
  budget_band: string;
  primary_goal: string;
  currency: string;
}

export function emptyDraft(): Draft {
  const numbers = Object.fromEntries(NUMERIC_FIELDS.map((k) => [k, null])) as NumericDraft;
  return {
    ...numbers,
    business_type: "", business_stage: "", category: "", custom_category: "", compare_categories: [],
    subcategory: "", product_focus: "", compare_focuses: [], market_mode: "", worldwide_ambition: false,
    target_countries: [], pilot_country: "", city: "", locality: "", sales_channel: "", sourcing_model: "",
    budget_band: "", primary_goal: "", currency: "INR",
  };
}

export function categoryOf(value: string) {
  return registry.categories.find((c) => c.value === value);
}

/** The first answer (business type) and later answers decide which steps exist. */
export function visibleSteps(d: Pick<Draft, "category">): StepId[] {
  const hasFocusStep = !["other", "undecided"].includes(d.category);
  return ALL_STEPS.filter((s) => s !== "focus" || hasFocusStep);
}

export function operatingFields(type: BusinessType | ""): FieldSpec[] {
  return type ? registry.operating_fields[type] : [];
}

/** Advanced inputs relevant to this business type & stage, minus anything already asked. */
export function advancedFields(d: Pick<Draft, "business_type" | "business_stage">): FieldSpec[] {
  if (!d.business_type) return [];
  const asked = new Set(operatingFields(d.business_type).map((f) => f.key));
  return registry.advanced_fields.filter((f) =>
    (f.applies_to ?? []).includes(d.business_type as BusinessType) &&
    (!d.business_stage || (f.stages ?? []).includes(d.business_stage)) &&
    !asked.has(f.key));
}

export function sourcingOptions(type: BusinessType | "") {
  return registry.sourcing_models.filter((s) => !type || s.applies_to.includes(type));
}

export function isPercentField(key: string): boolean {
  return key === "payment_or_platform_fees" || key === "expected_return_cost";
}

const ISO2 = /^[A-Z]{2}$/;
const optionalMoney = z.number({ invalid_type_error: "Enter a number" }).min(0, "Cannot be negative").nullable();

function schemaFor(step: StepId, d: Draft) {
  const base = z.object({}).passthrough();
  switch (step) {
    case "business_type":
      return base.extend({
        business_type: z.enum(["online", "physical"], { errorMap: () => ({ message: "Choose a business type" }) }),
      });
    case "stage":
      return base.extend({
        business_stage: z.enum(["new", "existing"], { errorMap: () => ({ message: "Choose your business stage" }) }),
      });
    case "category": {
      const values = [...registry.categories.map((c) => c.value), "other", "undecided"] as unknown as [string, ...string[]];
      return base.extend({ category: z.enum(values, { errorMap: () => ({ message: "Choose a category" }) }) })
        .superRefine((v, ctx) => {
          if (v.category === "other" && (d.custom_category ?? "").trim().length < 2)
            ctx.addIssue({ code: "custom", path: ["custom_category"], message: "Describe your category" });
          if (v.category === "undecided" && (d.compare_categories.length < 2 || d.compare_categories.length > registry.limits.max_compare_categories))
            ctx.addIssue({ code: "custom", path: ["compare_categories"], message: "Pick 2–3 categories to compare" });
        });
    }
    case "focus": {
      const cat = categoryOf(d.category);
      const values = [...(cat?.subcategories.map((s) => s.value) ?? []), "other", "undecided"] as unknown as [string, ...string[]];
      return base.extend({ subcategory: z.enum(values, { errorMap: () => ({ message: "Choose a product focus" }) }) })
        .superRefine((v, ctx) => {
          if (v.subcategory === "other" && d.product_focus.trim().length < 2)
            ctx.addIssue({ code: "custom", path: ["product_focus"], message: "Describe your product focus" });
          if (v.subcategory === "undecided" && (d.compare_focuses.length < 2 || d.compare_focuses.length > registry.limits.max_compare_focuses))
            ctx.addIssue({ code: "custom", path: ["compare_focuses"], message: "Pick 2–3 focuses to compare" });
        });
    }
    case "market":
      return base.superRefine((_v, ctx) => {
        const known = registry.markets.map((m) => m.code);
        if (d.business_type === "physical") {
          if (!ISO2.test(d.pilot_country)) ctx.addIssue({ code: "custom", path: ["pilot_country"], message: "Choose the shop's country" });
          if (d.city.trim().length < 2) ctx.addIssue({ code: "custom", path: ["city"], message: "City is required for a physical shop" });
          return;
        }
        if (!d.market_mode) {
          ctx.addIssue({ code: "custom", path: ["market_mode"], message: "Choose how you want to target markets" });
          return;
        }
        if (d.market_mode === "single" && !known.includes(d.pilot_country))
          ctx.addIssue({ code: "custom", path: ["pilot_country"], message: "Choose a country" });
        if (d.market_mode === "other" && !ISO2.test(d.pilot_country))
          ctx.addIssue({ code: "custom", path: ["pilot_country"], message: "Enter a 2-letter ISO country code, e.g. SG" });
        if (d.market_mode === "compare") {
          if (d.target_countries.length !== registry.limits.max_pilot_markets)
            ctx.addIssue({ code: "custom", path: ["target_countries"], message: "Pick exactly two pilot markets to compare" });
          else if (!d.target_countries.includes(d.pilot_country))
            ctx.addIssue({ code: "custom", path: ["pilot_country"], message: "Choose which of the two is your primary pilot" });
        }
        if (d.worldwide_ambition && !d.pilot_country)
          ctx.addIssue({ code: "custom", path: ["pilot_country"], message: "Worldwide selling still needs a pilot country" });
      });
    case "channel": {
      const values = d.business_type ? registry.sales_channels[d.business_type].map((c) => c.value) : [];
      return base.extend({
        sales_channel: z.string().refine((v) => values.includes(v), { message: "Choose a sales channel" }),
      });
    }
    case "capital":
      return base.extend({
        budget_band: z.string().refine((v) => registry.budget_bands.some((b) => b.value === v), { message: "Choose a budget band" }),
        exact_capital_inr: optionalMoney,
      });
    case "operating":
      return base.extend(Object.fromEntries(operatingFields(d.business_type).map((f) => [f.key, optionalMoney])));
    case "sourcing":
      return base.extend({
        sourcing_model: z.string().refine((v) => sourcingOptions(d.business_type).some((s) => s.value === v),
          { message: "Choose a sourcing model" }),
      });
    case "goal": {
      const values = d.business_stage ? registry.goals[d.business_stage].map((g) => g.value) : [];
      return base.extend({ primary_goal: z.string().refine((v) => values.includes(v), { message: "Choose your main goal" }) });
    }
    case "advanced":
      return base.extend(Object.fromEntries(advancedFields(d).map((f) => [
        f.key, isPercentField(f.key) ? optionalMoney.refine((v) => v === null || v <= 100, "Must be 0–100%") : optionalMoney,
      ])));
  }
}

export function stepSchema(step: StepId, d: Draft) {
  return schemaFor(step, d);
}

/** Returns a map of field -> message. Empty means the step is valid. */
export function validateStep(step: StepId, d: Draft): Record<string, string> {
  const result = schemaFor(step, d).safeParse(d);
  if (result.success) return {};
  const errors: Record<string, string> = {};
  for (const issue of result.error.issues) {
    const key = String(issue.path[0] ?? step);
    errors[key] ??= issue.message;
  }
  return errors;
}

export function firstInvalidStep(d: Draft): StepId | null {
  return visibleSteps(d).find((s) => Object.keys(validateStep(s, d)).length > 0) ?? null;
}

/** Draft -> backend payload. Irrelevant answers are dropped; blanks become null (unknown). */
export function toProfilePayload(d: Draft): BusinessProfileInput {
  const type = d.business_type as BusinessType;
  const relevant = new Set<string>([
    ...operatingFields(type).map((f) => f.key), ...advancedFields(d).map((f) => f.key), "exact_capital_inr",
  ]);
  const numbers = Object.fromEntries(NUMERIC_FIELDS.map((k) => [k, relevant.has(k) ? d[k] ?? null : null]));
  const pilot = d.pilot_country.trim().toUpperCase();
  let targets = [pilot];
  if (type === "online" && d.market_mode === "compare") targets = [pilot, ...d.target_countries.filter((c) => c !== pilot)];
  const cat = d.category;
  return {
    ...numbers,
    business_type: type,
    business_stage: d.business_stage as "new" | "existing",
    category: cat,
    custom_category: cat === "other" ? d.custom_category.trim() : null,
    compare_categories: cat === "undecided" ? d.compare_categories : [],
    subcategory: ["other", "undecided"].includes(cat) ? null : d.subcategory || null,
    product_focus: cat === "other" ? d.custom_category.trim() : d.subcategory === "other" ? d.product_focus.trim() : null,
    compare_focuses: d.subcategory === "undecided" && !["other", "undecided"].includes(cat) ? d.compare_focuses : [],
    market_mode: type === "online" ? (d.market_mode || null) : null,
    worldwide_ambition: d.worldwide_ambition,
    target_countries: targets.filter(Boolean),
    pilot_country: pilot || null,
    city: type === "physical" ? d.city.trim() || null : null,
    locality: type === "physical" ? d.locality.trim() || null : null,
    sales_channel: d.sales_channel,
    sourcing_model: d.sourcing_model,
    budget_band: d.budget_band,
    primary_goal: d.primary_goal,
    assumptions: [],
    currency: d.currency || "INR",
  } as BusinessProfileInput;
}

/** Backend profile -> draft (used for the demo profile and when editing a saved profile). */
export function fromProfile(p: BusinessProfileInput): Draft {
  const d = emptyDraft();
  for (const k of NUMERIC_FIELDS) d[k] = (p[k] as number | null | undefined) ?? null;
  const known = registry.markets.map((m) => m.code);
  const pilot = p.pilot_country ?? "";
  return {
    ...d,
    business_type: p.business_type,
    business_stage: p.business_stage,
    category: p.category,
    custom_category: p.custom_category ?? (p.category === "other" ? p.product_focus ?? "" : ""),
    compare_categories: p.compare_categories ?? [],
    subcategory: p.subcategory ?? "",
    product_focus: p.product_focus ?? "",
    compare_focuses: p.compare_focuses ?? [],
    market_mode: p.business_type === "online"
      ? (p.market_mode ?? ((p.target_countries?.length ?? 0) > 1 ? "compare" : known.includes(pilot) ? "single" : "other"))
      : "",
    worldwide_ambition: p.worldwide_ambition,
    target_countries: p.target_countries ?? [],
    pilot_country: pilot,
    city: p.city ?? "",
    locality: p.locality ?? "",
    sales_channel: p.sales_channel,
    sourcing_model: p.sourcing_model,
    budget_band: p.budget_band,
    primary_goal: p.primary_goal,
    currency: p.currency ?? "INR",
  };
}

/** When an earlier answer changes, clear later answers that are no longer valid for it. */
export function reconcile(d: Draft): Draft {
  const next = { ...d };
  if (next.business_type) {
    if (!registry.sales_channels[next.business_type].some((c) => c.value === next.sales_channel)) next.sales_channel = "";
    if (!sourcingOptions(next.business_type).some((s) => s.value === next.sourcing_model)) next.sourcing_model = "";
    if (next.business_type === "physical") next.market_mode = "";
  }
  if (next.business_stage && !registry.goals[next.business_stage].some((g) => g.value === next.primary_goal)) next.primary_goal = "";
  const cat = categoryOf(next.category);
  if (cat && next.subcategory && !["other", "undecided"].includes(next.subcategory) &&
      !cat.subcategories.some((s) => s.value === next.subcategory)) {
    next.subcategory = "";
    next.compare_focuses = [];
  }
  if (cat) next.compare_focuses = next.compare_focuses.filter((f) => cat.subcategories.some((s) => s.value === f));
  return next;
}

export const DRAFT_STORAGE_KEY = "marketsim.onboarding.draft.v1";

export interface StoredDraft {
  draft: Draft;
  step: StepId;
  profileId?: string | null;
  savedAt: string;
}

export function loadStoredDraft(): StoredDraft | null {
  try {
    const raw = localStorage.getItem(DRAFT_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as StoredDraft;
    return { ...parsed, draft: { ...emptyDraft(), ...parsed.draft } };
  } catch {
    return null;
  }
}

export function storeDraft(value: Omit<StoredDraft, "savedAt">): void {
  try {
    localStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify({ ...value, savedAt: new Date().toISOString() }));
  } catch {
    /* storage unavailable (private mode) – the in-memory draft still works */
  }
}

export function clearStoredDraft(): void {
  try {
    localStorage.removeItem(DRAFT_STORAGE_KEY);
  } catch {
    /* ignore */
  }
}
