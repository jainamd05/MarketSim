import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useForm, type Resolver } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { ArrowLeft, ArrowRight, Globe2, RotateCcw, Save } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";
import { FieldError, MultiOptionGrid, NumberField, OptionGrid, TextField } from "./fields";
import {
  STEP_TITLES, advancedFields, categoryOf, clearStoredDraft, emptyDraft, isPercentField, loadStoredDraft,
  operatingFields, reconcile, registry, sourcingOptions, stepSchema, storeDraft, visibleSteps, type Draft, type StepId,
} from "./flow";

const STEP_QUESTIONS: Record<StepId, { q: string; sub: string }> = {
  business_type: { q: "What kind of business is this?", sub: "Your answer decides which questions and research tools follow." },
  stage: { q: "Where are you today?", sub: "We tailor goals and benchmarks to your stage." },
  category: { q: "Which category are you in?", sub: "Undecided is fine – we will compare category-level signals instead of guessing." },
  focus: { q: "What will you sell?", sub: "Options adapt to the category you picked." },
  market: { q: "Where will you sell?", sub: "Research needs at least one concrete pilot market." },
  channel: { q: "How will customers buy from you?", sub: "Channel drives fees, acquisition and fulfilment assumptions." },
  capital: { q: "What can you invest up front?", sub: "A band is not an exact amount – add the exact figure only if you know it." },
  operating: { q: "What are your recurring costs?", sub: "All optional. Blank means unknown; we will label any assumption we use." },
  sourcing: { q: "How will you source products?", sub: "This shapes cost and inventory assumptions." },
  goal: { q: "What do you want from this analysis?", sub: "We prioritise research around your goal." },
  advanced: { q: "Any numbers you already know?", sub: "Optional. Every field shows its unit and currency." },
};

export function OnboardingWizard() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const stored = useMemo(() => loadStoredDraft(), []);
  const [step, setStep] = useState<StepId>(() => (params.get("step") as StepId) || stored?.step || "business_type");
  const stepRef = useRef(step);
  stepRef.current = step;

  const resolver: Resolver<Draft> = (values, ctx, opts) => zodResolver(stepSchema(stepRef.current, values))(values, ctx, opts);
  const form = useForm<Draft>({ defaultValues: stored?.draft ?? emptyDraft(), resolver, mode: "onSubmit" });
  const { watch, setValue, trigger, clearErrors, formState: { errors } } = form;
  const draft = watch();

  const steps = visibleSteps(draft);
  const index = Math.max(0, steps.indexOf(step));
  const isLast = index === steps.length - 1;

  useEffect(() => {
    if (!steps.includes(step)) setStep(steps[Math.min(index, steps.length - 1)]);
  }, [steps, step, index]);

  useEffect(() => {
    storeDraft({ draft, step, profileId: stored?.profileId ?? null });
  }, [draft, step, stored?.profileId]);

  const set = <K extends keyof Draft>(key: K, value: Draft[K]) => {
    setValue(key, value as never, { shouldDirty: true });
    const reconciled = reconcile({ ...form.getValues(), [key]: value });
    (Object.keys(reconciled) as (keyof Draft)[]).forEach((k) => {
      if (JSON.stringify(reconciled[k]) !== JSON.stringify(form.getValues(k))) setValue(k, reconciled[k] as never);
    });
    clearErrors();
  };
  const err = (k: string) => (errors as Record<string, { message?: string } | undefined>)[k]?.message;

  const goTo = (s: StepId) => {
    setStep(s);
    setParams({ step: s }, { replace: true });
    clearErrors();
    window.scrollTo?.({ top: 0 });
  };
  const next = async () => {
    const ok = await trigger();
    if (!ok) return;
    if (isLast) navigate("/onboarding/review");
    else goTo(steps[index + 1]);
  };

  return (
    <div className="mx-auto max-w-3xl px-4 py-10 sm:px-6">
      <div className="mb-8">
        <div className="mb-3 flex items-center justify-between text-xs text-ink-3">
          <span>Step {index + 1} of {steps.length} · {STEP_TITLES[step]}</span>
          <button type="button" onClick={() => { clearStoredDraft(); form.reset(emptyDraft()); goTo("business_type"); }}
            className="inline-flex items-center gap-1 hover:text-ink cursor-pointer">
            <RotateCcw className="h-3 w-3" /> Start over
          </button>
        </div>
        <Progress value={((index + 1) / steps.length) * 100} aria-label="Onboarding progress" />
        <ol className="mt-4 hidden flex-wrap gap-1.5 md:flex" aria-label="Steps">
          {steps.map((s, i) => (
            <li key={s}>
              <button type="button" disabled={i > index} onClick={() => goTo(s)}
                className={cn("rounded-md px-2 py-1 text-[11px] font-medium transition-colors cursor-pointer disabled:cursor-default",
                  s === step ? "bg-accent-soft text-[#9cc3f3]" : i < index ? "text-ink-2 hover:bg-white/5" : "text-ink-3/60")}>
                {i + 1}. {STEP_TITLES[s]}
              </button>
            </li>
          ))}
        </ol>
      </div>

      <form onSubmit={(e) => { e.preventDefault(); void next(); }} noValidate>
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">{STEP_QUESTIONS[step].q}</h1>
        <p className="mt-2 text-ink-3">{STEP_QUESTIONS[step].sub}</p>
        <div key={step} className="mt-8 animate-fade-up">
          <StepBody step={step} d={draft} set={set} err={err} />
        </div>

        <div className="mt-10 flex items-center justify-between gap-3 border-t border-border pt-6">
          <Button type="button" variant="ghost" disabled={index === 0} onClick={() => goTo(steps[index - 1])}>
            <ArrowLeft /> Back
          </Button>
          <div className="flex items-center gap-3">
            <span className="hidden items-center gap-1 text-xs text-ink-3 sm:inline-flex"><Save className="h-3 w-3" /> Draft saved on this device</span>
            <Button type="submit">{isLast ? "Review profile" : "Next"} <ArrowRight /></Button>
          </div>
        </div>
      </form>
    </div>
  );
}

interface StepProps {
  step: StepId;
  d: Draft;
  set: <K extends keyof Draft>(key: K, value: Draft[K]) => void;
  err: (k: string) => string | undefined;
}

function StepBody({ step, d, set, err }: StepProps) {
  switch (step) {
    case "business_type":
      return (
        <OptionGrid name="business_type" label="Business type" value={d.business_type} error={err("business_type")}
          onChange={(v) => set("business_type", v as Draft["business_type"])}
          options={registry.business_types.map((b) => ({ ...b, disabled: !b.enabled, description: b.enabled ? b.description : `${b.description}` }))} />
      );
    case "stage":
      return <OptionGrid name="stage" label="Business stage" value={d.business_stage} error={err("business_stage")}
        onChange={(v) => set("business_stage", v as Draft["business_stage"])} options={registry.business_stages} />;
    case "category":
      return (
        <div className="space-y-6">
          <OptionGrid name="category" label="Category" columns={3} value={d.category} error={err("category")}
            onChange={(v) => set("category", v)}
            options={[...registry.categories.map(({ value, label }) => ({ value, label })), ...registry.category_special_options]} />
          {d.category === "other" && (
            <TextField id="custom_category" label="Describe your category" value={d.custom_category}
              placeholder="e.g. Handmade stationery" error={err("custom_category")} onChange={(v) => set("custom_category", v)} />
          )}
          {d.category === "undecided" && (
            <MultiOptionGrid label="Compare category-level opportunity for" max={registry.limits.max_compare_categories}
              values={d.compare_categories} error={err("compare_categories")} onChange={(v) => set("compare_categories", v)}
              options={registry.categories.map(({ value, label }) => ({ value, label }))} />
          )}
        </div>
      );
    case "focus": {
      const cat = categoryOf(d.category);
      const subs = cat?.subcategories.map(({ value, label }) => ({ value, label })) ?? [];
      return (
        <div className="space-y-6">
          <OptionGrid name="subcategory" label="Product focus" columns={3} value={d.subcategory} error={err("subcategory")}
            onChange={(v) => set("subcategory", v)} options={[...subs, ...registry.focus_special_options]} />
          {d.subcategory === "other" && (
            <TextField id="product_focus" label="Describe your product focus" value={d.product_focus}
              error={err("product_focus")} onChange={(v) => set("product_focus", v)} />
          )}
          {d.subcategory === "undecided" && (
            <MultiOptionGrid label="Compare these focuses" max={registry.limits.max_compare_focuses} options={subs}
              values={d.compare_focuses} error={err("compare_focuses")} onChange={(v) => set("compare_focuses", v)} />
          )}
        </div>
      );
    }
    case "market":
      return d.business_type === "physical" ? <PhysicalMarket d={d} set={set} err={err} /> : <OnlineMarket d={d} set={set} err={err} />;
    case "channel":
      return <OptionGrid name="sales_channel" label="Sales channel" value={d.sales_channel} error={err("sales_channel")}
        onChange={(v) => set("sales_channel", v)} options={d.business_type ? registry.sales_channels[d.business_type] : []} />;
    case "capital":
      return (
        <div className="space-y-6">
          <OptionGrid name="budget_band" label="Investment budget" columns={3} value={d.budget_band} error={err("budget_band")}
            onChange={(v) => set("budget_band", v)} options={registry.budget_bands} />
          <NumberField id="exact_capital_inr" label="Exact capital available (optional)" unit="INR, one-off"
            value={d.exact_capital_inr} error={err("exact_capital_inr")} onChange={(v) => set("exact_capital_inr", v)}
            hint="Leave blank if unknown – capital-fit checks and inventory optimisation stay disabled until you provide it." />
        </div>
      );
    case "operating":
      return (
        <div className="grid gap-5 sm:grid-cols-2">
          {operatingFields(d.business_type).map((f) => (
            <NumberField key={f.key} id={f.key} label={f.label} unit={f.unit} value={d[f.key as keyof Draft] as number | null}
              error={err(f.key)} onChange={(v) => set(f.key as keyof Draft, v as never)} />
          ))}
        </div>
      );
    case "sourcing":
      return <OptionGrid name="sourcing_model" label="Sourcing model" value={d.sourcing_model} error={err("sourcing_model")}
        onChange={(v) => set("sourcing_model", v)} options={sourcingOptions(d.business_type)} />;
    case "goal":
      return <OptionGrid name="primary_goal" label="Main goal" value={d.primary_goal} error={err("primary_goal")}
        onChange={(v) => set("primary_goal", v)} options={d.business_stage ? registry.goals[d.business_stage] : []} />;
    case "advanced":
      return (
        <div className="grid gap-5 sm:grid-cols-2">
          {advancedFields(d).map((f) => (
            <NumberField key={f.key} id={f.key} label={f.label}
              unit={isPercentField(f.key) ? f.unit : f.unit.startsWith("orders") || f.unit.startsWith("visitors") ? f.unit : `${d.currency} ${f.unit}`}
              value={d[f.key as keyof Draft] as number | null} error={err(f.key)} onChange={(v) => set(f.key as keyof Draft, v as never)} />
          ))}
        </div>
      );
  }
}

function OnlineMarket({ d, set, err }: Omit<StepProps, "step">) {
  const markets = registry.markets.map((m) => ({ value: m.code, label: m.label, description: `Currency ${m.currency}` }));
  return (
    <div className="space-y-6">
      <OptionGrid name="market_mode" label="Market targeting" columns={3} value={d.market_mode} error={err("market_mode")}
        onChange={(v) => { set("market_mode", v as Draft["market_mode"]); set("target_countries", []); set("pilot_country", ""); }}
        options={registry.market_modes.online} />
      {d.market_mode === "single" && (
        <OptionGrid name="pilot_country" label="Country" value={d.pilot_country} error={err("pilot_country")}
          onChange={(v) => set("pilot_country", v)} options={markets} />
      )}
      {d.market_mode === "compare" && (
        <div className="space-y-5">
          <MultiOptionGrid label="Pilot markets to compare" max={registry.limits.max_pilot_markets} values={d.target_countries}
            error={err("target_countries")} onChange={(v) => { set("target_countries", v); if (!v.includes(d.pilot_country)) set("pilot_country", v[0] ?? ""); }}
            options={markets} />
          {d.target_countries.length === 2 && (
            <OptionGrid name="pilot_country" label="Primary pilot market" value={d.pilot_country} error={err("pilot_country")}
              onChange={(v) => set("pilot_country", v)} options={markets.filter((m) => d.target_countries.includes(m.value))} />
          )}
        </div>
      )}
      {d.market_mode === "other" && (
        <TextField id="pilot_country" label="ISO country code (2 letters)" value={d.pilot_country} maxLength={2}
          placeholder="e.g. SG" error={err("pilot_country")} onChange={(v) => set("pilot_country", v.toUpperCase())} />
      )}
      <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-border bg-card p-4">
        <input type="checkbox" className="mt-1 h-4 w-4 accent-[#3987e5]" checked={d.worldwide_ambition}
          onChange={(e) => set("worldwide_ambition", e.target.checked)} />
        <span>
          <span className="flex items-center gap-2 font-medium"><Globe2 className="h-4 w-4 text-ink-3" /> I want to sell worldwide eventually</span>
          <span className="mt-0.5 block text-sm text-ink-3">We record the ambition, but research still needs a concrete pilot country above.</span>
        </span>
      </label>
    </div>
  );
}

function PhysicalMarket({ d, set, err }: Omit<StepProps, "step">) {
  return (
    <div className="space-y-6">
      <OptionGrid name="pilot_country" label="Country" value={d.pilot_country} error={err("pilot_country")}
        onChange={(v) => set("pilot_country", v)} options={registry.markets.map((m) => ({ value: m.code, label: m.label }))} />
      <div className="grid gap-5 sm:grid-cols-2">
        <TextField id="city" label="City" value={d.city} placeholder="e.g. Mumbai" error={err("city")} onChange={(v) => set("city", v)} />
        <TextField id="locality" label="Neighbourhood / locality (optional)" value={d.locality} placeholder="e.g. Bandra West"
          onChange={(v) => set("locality", v)} />
      </div>
      <FieldError message={undefined} />
    </div>
  );
}
