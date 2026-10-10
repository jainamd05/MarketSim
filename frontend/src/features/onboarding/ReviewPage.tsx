import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AlertTriangle, CheckCircle2, FlaskConical, Loader2, Pencil, Play, Radio, Save } from "lucide-react";
import { useApp } from "@/components/AppContext";
import { ErrorState, PageShell } from "@/components/Layout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api, ApiError } from "@/lib/api";
import { money } from "@/lib/format";
import type { DataMode } from "@/lib/types";
import { cn } from "@/lib/utils";
import {
  STEP_TITLES, advancedFields, categoryOf, firstInvalidStep, isPercentField, loadStoredDraft, operatingFields,
  registry, storeDraft, toProfilePayload, type Draft, type StepId,
} from "./flow";

function label(options: { value: string; label: string }[] | undefined, v: string) {
  return options?.find((o) => o.value === v)?.label ?? (v || "—");
}
function marketName(code: string) {
  return registry.markets.find((m) => m.code === code)?.label ?? code;
}

type Row = { k: string; v: React.ReactNode; unknown?: boolean };

function sections(d: Draft): { step: StepId; rows: Row[] }[] {
  const cat = categoryOf(d.category);
  const type = d.business_type || "online";
  const numRow = (key: string, title: string, unit: string): Row => {
    const v = d[key as keyof Draft] as number | null;
    const shown = v === null ? "Unknown" : isPercentField(key) ? `${v}%` : unit.includes("INR") || unit.includes("per") ? money(v, "INR") : String(v);
    return { k: `${title} (${unit})`, v: shown, unknown: v === null };
  };
  const focusRows: Row[] = d.category === "undecided"
    ? [{ k: "Compare categories", v: d.compare_categories.map((c) => categoryOf(c)?.label).join(", ") }]
    : d.category === "other"
      ? [{ k: "Custom category", v: d.custom_category }]
      : [{ k: "Product focus", v: d.subcategory === "undecided"
        ? `Undecided – comparing ${d.compare_focuses.map((f) => cat?.subcategories.find((s) => s.value === f)?.label).join(", ")}`
        : d.subcategory === "other" ? d.product_focus : label(cat?.subcategories, d.subcategory) }];
  return [
    { step: "business_type", rows: [{ k: "Business type", v: label(registry.business_types, d.business_type) }] },
    { step: "stage", rows: [{ k: "Stage", v: label(registry.business_stages, d.business_stage) }] },
    { step: "category", rows: [{ k: "Category", v: label([...registry.categories, ...registry.category_special_options], d.category) }] },
    ...(["other", "undecided"].includes(d.category) ? [] : [{ step: "focus" as StepId, rows: focusRows }]),
    ...(["other", "undecided"].includes(d.category) ? [{ step: "category" as StepId, rows: focusRows }] : []),
    {
      step: "market", rows: type === "physical"
        ? [{ k: "Country", v: marketName(d.pilot_country) }, { k: "City", v: d.city || "—" }, { k: "Locality", v: d.locality || "Not specified", unknown: !d.locality }]
        : [
          { k: "Pilot market", v: marketName(d.pilot_country) },
          ...(d.market_mode === "compare" ? [{ k: "Compared markets", v: d.target_countries.map(marketName).join(" vs ") }] : []),
          { k: "Worldwide ambition", v: d.worldwide_ambition ? "Yes – recorded; research scoped to the pilot" : "No" },
        ],
    },
    { step: "channel", rows: [{ k: "Sales channel", v: label(d.business_type ? registry.sales_channels[d.business_type] : [], d.sales_channel) }] },
    { step: "capital", rows: [{ k: "Budget band", v: label(registry.budget_bands, d.budget_band) }, numRow("exact_capital_inr", "Exact capital", "INR, one-off")] },
    { step: "operating", rows: operatingFields(d.business_type).map((f) => numRow(f.key, f.label, f.unit)) },
    { step: "sourcing", rows: [{ k: "Sourcing", v: label(registry.sourcing_models, d.sourcing_model) }] },
    { step: "goal", rows: [{ k: "Main goal", v: label(d.business_stage ? registry.goals[d.business_stage] : [], d.primary_goal) }] },
    { step: "advanced", rows: advancedFields(d).map((f) => numRow(f.key, f.label, isPercentField(f.key) ? f.unit : `${d.currency} ${f.unit}`)) },
  ];
}

export function ReviewPage() {
  const navigate = useNavigate();
  const { config } = useApp();
  const stored = useMemo(() => loadStoredDraft(), []);
  const [profileId, setProfileId] = useState<string | null>(stored?.profileId ?? null);
  const [busy, setBusy] = useState<"save" | "run" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [mode, setMode] = useState<DataMode | null>(null);

  if (!stored) {
    return (
      <PageShell className="max-w-3xl">
        <ErrorState title="No profile in progress" message="Start the questionnaire or load the demonstration profile first."
          action={<Button asChild><Link to="/onboarding">Start questionnaire</Link></Button>} />
      </PageShell>
    );
  }
  const d = stored.draft;
  const invalid = firstInvalidStep(d);
  const unknownCount = sections(d).flatMap((s) => s.rows).filter((r) => r.unknown).length;
  const effectiveMode: DataMode = mode ?? config?.default_data_mode ?? "demo";

  const persist = async (status: "draft" | "confirmed") => {
    const payload = toProfilePayload(d);
    const res = profileId ? await api.updateProfile(profileId, payload, status) : await api.createProfile(payload, status);
    setProfileId(res.profile.id);
    storeDraft({ draft: d, step: stored.step, profileId: res.profile.id });
    return res.profile.id;
  };
  const onSave = async () => {
    setBusy("save"); setError(null);
    try { await persist("draft"); setSaved(true); } catch (e) { setError((e as Error).message); } finally { setBusy(null); }
  };
  const onRun = async () => {
    setBusy("run"); setError(null);
    try {
      const id = await persist("confirmed");
      const res = await api.createAnalysis(id, effectiveMode);
      navigate(`/analysis/${res.analysis_id}/run`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : (e as Error).message);
      setBusy(null);
    }
  };

  return (
    <PageShell className="max-w-5xl">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm font-medium text-accent">Review & confirm</p>
          <h1 className="mt-1 text-3xl font-semibold tracking-tight">Your business profile</h1>
          <p className="mt-2 max-w-2xl text-ink-3">
            Check every answer. Unknown inputs are kept as unknown – agents will use explicitly labelled, editable scenario assumptions instead of inventing numbers.
          </p>
        </div>
        <Badge variant={unknownCount ? "warning" : "good"}>
          {unknownCount ? <AlertTriangle /> : <CheckCircle2 />} {unknownCount} unknown input{unknownCount === 1 ? "" : "s"}
        </Badge>
      </div>

      {invalid && (
        <div className="mt-6">
          <ErrorState title="Profile incomplete" message={`The "${STEP_TITLES[invalid]}" step needs an answer before analysis.`}
            action={<Button asChild variant="secondary"><Link to={`/onboarding?step=${invalid}`}>Fix {STEP_TITLES[invalid]}</Link></Button>} />
        </div>
      )}

      <div className="mt-8 grid gap-4 md:grid-cols-2">
        {sections(d).filter((s) => s.rows.length).map((s, i) => (
          <Card key={`${s.step}-${i}`}>
            <CardHeader className="flex-row items-center justify-between pb-2">
              <CardTitle>{STEP_TITLES[s.step]}</CardTitle>
              <Button variant="ghost" size="sm" asChild>
                <Link to={`/onboarding?step=${s.step}`} aria-label={`Edit ${STEP_TITLES[s.step]}`}><Pencil /> Edit</Link>
              </Button>
            </CardHeader>
            <CardContent>
              <dl className="divide-y divide-border">
                {s.rows.map((r) => (
                  <div key={r.k} className="flex items-baseline justify-between gap-4 py-2 text-sm">
                    <dt className="text-ink-3">{r.k}</dt>
                    <dd className={cn("text-right font-medium tabular", r.unknown && "text-warning")}>
                      {r.unknown ? <Badge variant="warning">Unknown</Badge> : r.v}
                    </dd>
                  </div>
                ))}
              </dl>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card className="mt-8">
        <CardContent className="flex flex-col gap-5 pt-5 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p className="font-medium">Data source for this run</p>
            <div className="mt-3 inline-flex rounded-lg border border-border p-1" role="radiogroup" aria-label="Data mode">
              {(["demo", "live"] as DataMode[]).map((m) => {
                const disabled = m === "live" && !config?.live_available;
                return (
                  <button key={m} type="button" role="radio" aria-checked={effectiveMode === m} disabled={disabled}
                    onClick={() => setMode(m)}
                    className={cn("inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm cursor-pointer disabled:cursor-not-allowed disabled:opacity-40",
                      effectiveMode === m ? "bg-card-raised text-ink" : "text-ink-3")}>
                    {m === "demo" ? <FlaskConical className="h-3.5 w-3.5" /> : <Radio className="h-3.5 w-3.5" />}
                    {m === "demo" ? "Demo fixtures" : "Live SerpApi"}
                  </button>
                );
              })}
            </div>
            <p className="mt-2 text-xs text-ink-3">
              {effectiveMode === "demo"
                ? "Uses saved synthetic fixtures – no API keys or credits. Fixtures cover the demonstration profile; other profiles complete in a clearly degraded state."
                : `Makes up to ${config?.max_serpapi_requests_per_analysis ?? 12} genuine SerpApi requests and reports any failure honestly.`}
              {!config?.live_available && " Live mode needs SERPAPI_API_KEY in backend/.env."}
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <Button variant="secondary" asChild><Link to="/onboarding"><Pencil /> Edit profile</Link></Button>
            <Button variant="secondary" onClick={onSave} disabled={!!busy || !!invalid}>
              {busy === "save" ? <Loader2 className="animate-spin" /> : <Save />} {saved ? "Draft saved" : "Save draft"}
            </Button>
            <Button onClick={onRun} disabled={!!busy || !!invalid}>
              {busy === "run" ? <Loader2 className="animate-spin" /> : <Play />} Run market analysis
            </Button>
          </div>
        </CardContent>
      </Card>
      {error && <div className="mt-4"><ErrorState title="Could not continue" message={error} /></div>}
    </PageShell>
  );
}
