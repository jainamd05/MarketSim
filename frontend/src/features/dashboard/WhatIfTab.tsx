import { useEffect, useMemo, useRef, useState } from "react";
import { Loader2, RotateCcw, Wallet } from "lucide-react";
import { Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { EmptyState } from "@/components/Layout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Slider } from "@/components/ui/slider";
import { api } from "@/lib/api";
import { money, num, pct } from "@/lib/format";
import type { SimInputs, StrategiesResponse, StrategySimulation } from "@/lib/types";
import { cn } from "@/lib/utils";
import { STRATEGY_COLORS, StatTile } from "./shared";

interface SliderSpec { key: string; label: string; unit: string; min: number; max: number; step: number }

function slidersFor(base: SimInputs): SliderSpec[] {
  const r = (v: number, f: number, floor = 0) => Math.max(floor, Math.round(v * f));
  if (base.model === "online") {
    return [
      { key: "selling_price", label: "Selling price", unit: `${base.currency} / unit`, min: r(base.selling_price, 0.3, 1), max: r(base.selling_price, 2.5, 10), step: 1 },
      { key: "cac", label: "Customer acquisition cost (CAC)", unit: `${base.currency} / ad-acquired order`, min: r(base.cac, 0.2, 1), max: r(base.cac, 3, 10), step: 5 },
      { key: "organic_orders", label: "Organic orders (demand assumption)", unit: "orders / month", min: 0, max: Math.max(200, r(base.organic_orders, 5)), step: 1 },
      { key: "repeat_orders", label: "Repeat orders (demand assumption)", unit: "orders / month", min: 0, max: Math.max(200, r(base.repeat_orders, 5)), step: 1 },
      { key: "unit_cost", label: "Product unit cost", unit: `${base.currency} / unit`, min: 0, max: r(Math.max(base.unit_cost, base.selling_price), 2, 10), step: 1 },
      { key: "units_per_order", label: "Units per order", unit: "units", min: 1, max: 6, step: 0.5 },
      { key: "monthly_ad_budget", label: "Advertising budget", unit: `${base.currency} / month`, min: 0, max: Math.max(r(base.monthly_ad_budget, 3), 50000), step: 1000 },
      { key: "shipping_cost_per_order", label: "Shipping cost", unit: `${base.currency} / order`, min: 0, max: Math.max(r(base.shipping_cost_per_order, 3), 200), step: 5 },
      { key: "platform_fee_pct", label: "Platform / payment fees", unit: "% of order value", min: 0, max: 40, step: 0.5 },
      { key: "fixed_costs_monthly", label: "Monthly fixed expenses", unit: `${base.currency} / month`, min: 0, max: Math.max(r(base.fixed_costs_monthly, 5), 50000), step: 500 },
    ];
  }
  return [
    { key: "average_transaction_value", label: "Average transaction value", unit: `${base.currency}`, min: r(base.average_transaction_value, 0.3, 1), max: r(base.average_transaction_value, 2.5, 10), step: 5 },
    { key: "daily_footfall", label: "Daily footfall (demand assumption)", unit: "visitors / day", min: 0, max: Math.max(r(base.daily_footfall, 3), 300), step: 5 },
    { key: "conversion_rate_pct", label: "Conversion rate", unit: "% of visitors", min: 0, max: 60, step: 0.5 },
    { key: "cogs_pct", label: "Cost of goods", unit: "% of sales", min: 0, max: 95, step: 1 },
    { key: "marketing", label: "Marketing budget", unit: `${base.currency} / month`, min: 0, max: Math.max(r(base.marketing, 4), 40000), step: 1000 },
    { key: "card_fee_pct", label: "Card / payment fees", unit: "% of sales", min: 0, max: 10, step: 0.1 },
    { key: "rent", label: "Monthly rent", unit: `${base.currency} / month`, min: 0, max: Math.max(r(base.rent, 3), 100000), step: 1000 },
    { key: "staff", label: "Staff", unit: `${base.currency} / month`, min: 0, max: Math.max(r(base.staff, 3), 100000), step: 1000 },
  ];
}

export function WhatIfTab({ analysisId, data, selected, onSelect }: {
  analysisId: string; data: StrategiesResponse | null; selected: string; onSelect: (k: string) => void;
}) {
  const strategy = data?.strategies.find((s) => s.key === selected) ?? data?.strategies[0];
  const [inputs, setInputs] = useState<SimInputs | null>(strategy?.sim_inputs ?? null);
  const [sim, setSim] = useState<StrategySimulation | null>(strategy ? data!.simulations[strategy.key] : null);
  const [capital, setCapital] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const reqId = useRef(0);
  const firstRun = useRef(true);

  useEffect(() => {
    if (!strategy) return;
    setInputs(strategy.sim_inputs);
    setSim(data!.simulations[strategy.key]);
    setCapital(strategy.sim_inputs.available_capital != null ? String(strategy.sim_inputs.available_capital) : "");
    firstRun.current = true;
  }, [strategy?.key]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!inputs || !strategy) return;
    if (firstRun.current) { firstRun.current = false; return; }
    const id = ++reqId.current;
    setLoading(true);
    const t = setTimeout(async () => {
      try {
        const res = await api.simulate(analysisId, strategy.key, inputs);
        if (id === reqId.current) { setSim(res.simulation); setError(null); }
      } catch (e) {
        if (id === reqId.current) setError((e as Error).message);
      } finally {
        if (id === reqId.current) setLoading(false);
      }
    }, 250);
    return () => clearTimeout(t);
  }, [inputs, analysisId, strategy]);

  const sliders = useMemo(() => (strategy ? slidersFor(strategy.sim_inputs) : []), [strategy]);
  if (!data || !strategy || !inputs || !sim) return <EmptyState title="Nothing to simulate" message="No strategies are available for this analysis." />;
  const cur = inputs.currency;
  const b = sim.base;
  const update = (key: string, value: number) => setInputs((prev) => (prev ? ({ ...prev, [key]: value } as SimInputs) : prev));
  const applyCapital = (v: string) => {
    setCapital(v);
    const n = v.trim() === "" ? null : Number(v);
    if (n === null || (!Number.isNaN(n) && n >= 0)) setInputs((prev) => (prev ? ({ ...prev, available_capital: n } as SimInputs) : prev));
  };
  const total = b.orders.total ?? 0;
  const beRatio = b.break_even_orders ? Math.min(1, total / b.break_even_orders) : 0;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-2">
        {data.strategies.map((s) => (
          <button key={s.key} onClick={() => onSelect(s.key)} aria-pressed={s.key === strategy.key}
            className={cn("inline-flex items-center gap-2 rounded-lg border px-3 py-1.5 text-sm cursor-pointer",
              s.key === strategy.key ? "border-accent bg-accent-soft text-ink" : "border-border text-ink-3 hover:text-ink")}>
            <span className="h-2.5 w-2.5 rounded-full" style={{ background: STRATEGY_COLORS[s.key] }} />{s.key} · {s.archetype.replace(/_/g, " ")}
          </button>
        ))}
        <span className="ml-auto flex items-center gap-2 text-xs text-ink-3" aria-live="polite">
          {loading ? <><Loader2 className="h-3.5 w-3.5 animate-spin" /> Recomputing with Python…</> : "Recomputed by deterministic backend functions · 0 SerpApi requests"}
        </span>
      </div>
      {error && <p role="alert" className="text-sm text-[#f08a8a]">{error}</p>}

      <div className="grid gap-5 lg:grid-cols-[380px_1fr]">
        <Card className="h-fit">
          <CardHeader className="flex-row items-center justify-between">
            <CardTitle>Assumptions</CardTitle>
            <Button size="sm" variant="ghost" onClick={() => { setInputs(strategy.sim_inputs); applyCapital(strategy.sim_inputs.available_capital != null ? String(strategy.sim_inputs.available_capital) : ""); }}>
              <RotateCcw /> Reset
            </Button>
          </CardHeader>
          <CardContent className="space-y-4">
            {sliders.map((sp) => {
              const v = Number((inputs as unknown as Record<string, number>)[sp.key] ?? 0);
              return (
                <div key={sp.key}>
                  <div className="flex items-baseline justify-between gap-2 text-sm">
                    <label id={`lbl-${sp.key}`} className="text-ink-2">{sp.label}</label>
                    <span className="tabular font-medium">{num(v, 2)}</span>
                  </div>
                  <Slider aria-labelledby={`lbl-${sp.key}`} aria-label={sp.label} min={sp.min} max={Math.max(sp.max, v)} step={sp.step}
                    value={[v]} onValueChange={([nv]) => update(sp.key, nv)} />
                  <p className="text-[11px] text-ink-3">{sp.unit}</p>
                </div>
              );
            })}
            <div className="border-t border-border pt-4">
              <label htmlFor="capital" className="flex items-center gap-1.5 text-sm text-ink-2"><Wallet className="h-3.5 w-3.5" /> Available capital ({cur})</label>
              <Input id="capital" type="number" min={0} placeholder="Unknown – enter to enable optimisation" className="mt-1.5 tabular"
                value={capital} onChange={(e) => applyCapital(e.target.value)} />
            </div>
          </CardContent>
        </Card>

        <div className="space-y-5">
          <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
            <StatTile label="Revenue / month" value={money(b.revenue, cur, { compact: true })} sub={`${num(total, 1)} orders · AOV ${money(b.average_order_value, cur)}`} />
            <StatTile label="Contribution / order" value={money(b.contribution_per_order, cur)} tone={b.contribution_per_order < 0 ? "bad" : "neutral"} sub={`${b.contribution_margin_pct}% of order value`} />
            <StatTile label="Operating result / month" value={money(b.operating_result, cur, { compact: true })} tone={b.operating_result < 0 ? "bad" : "good"} sub="after advertising & fixed costs" />
            <StatTile label="Runs with a loss" value={pct(sim.monte_carlo.prob_negative)} sub={`${sim.monte_carlo.iterations.toLocaleString()} seeded runs`} />
          </div>

          <Card>
            <CardHeader><CardTitle>Break-even indicator</CardTitle><CardDescription>{b.break_even_note}</CardDescription></CardHeader>
            <CardContent>
              {b.break_even_orders == null ? (
                <Badge variant="critical">Not achievable – contribution per order is not positive</Badge>
              ) : (
                <div>
                  <div className="relative h-3 overflow-hidden rounded-full bg-white/10" role="meter" aria-valuenow={Math.round(beRatio * 100)} aria-valuemin={0} aria-valuemax={100}
                    aria-label="Modelled orders as a share of break-even orders">
                    <div className={cn("h-full rounded-full", beRatio >= 1 ? "bg-profit" : "bg-loss")} style={{ width: `${Math.max(2, beRatio * 100)}%` }} />
                  </div>
                  <p className="mt-2 text-sm text-ink-2 tabular">
                    {num(total, 1)} modelled orders vs {num(b.break_even_orders)} needed ({pct(beRatio)} of break-even)
                    {b.orders.ad_acquired !== undefined && <span className="text-ink-3"> · ad-acquired {num(b.orders.ad_acquired, 1)}, organic {num(b.orders.organic, 1)}, repeat {num(b.orders.repeat, 1)}</span>}
                  </p>
                </div>
              )}
            </CardContent>
          </Card>

          <div className="grid gap-5 xl:grid-cols-2">
            <Card>
              <CardHeader><CardTitle>Bear / base / bull</CardTitle><CardDescription>Explicit, bounded adjustments to your current assumptions.</CardDescription></CardHeader>
              <CardContent className="space-y-3">
                {sim.scenarios.map((sc) => (
                  <div key={sc.scenario} className="rounded-lg border border-border p-3">
                    <div className="flex items-center justify-between text-sm">
                      <span className="font-medium capitalize">{sc.scenario}</span>
                      <span className={cn("tabular font-semibold", sc.result.operating_result < 0 ? "text-[#f08a8a]" : "text-[#7fb4f0]")}>{money(sc.result.operating_result, cur)}/mo</span>
                    </div>
                    <p className="mt-1 text-[11px] text-ink-3">{Object.entries(sc.adjustments).map(([k, v]) => `${k.replace(/_/g, " ")} ${v}`).join(" · ")}</p>
                  </div>
                ))}
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Monthly operating result distribution</CardTitle>
                <CardDescription>Monte Carlo, seed {sim.monte_carlo.seed}. P5 {money(sim.monte_carlo.percentiles.p5, cur, { compact: true })} · P50 {money(sim.monte_carlo.percentiles.p50, cur, { compact: true })} · P95 {money(sim.monte_carlo.percentiles.p95, cur, { compact: true })}</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="h-[200px]" role="img" aria-label="Histogram of simulated monthly operating results">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={sim.monte_carlo.histogram.map((h) => ({ ...h, mid: (h.bin_start + h.bin_end) / 2 }))} barCategoryGap={2} margin={{ left: -18, right: 8 }}>
                      <CartesianGrid stroke="var(--color-grid)" vertical={false} />
                      <XAxis dataKey="mid" tick={{ fill: "var(--color-ink-3)", fontSize: 10 }} stroke="var(--color-axis)" tickFormatter={(v: number) => money(v, cur, { compact: true })} interval={5} />
                      <YAxis tick={{ fill: "var(--color-ink-3)", fontSize: 10 }} stroke="var(--color-axis)" />
                      <ReferenceLine x={sim.monte_carlo.histogram.reduce((best, h) => (Math.abs((h.bin_start + h.bin_end) / 2) < Math.abs(best) ? (h.bin_start + h.bin_end) / 2 : best), Infinity)} stroke="var(--color-ink-3)" strokeDasharray="3 3" />
                      <Tooltip cursor={{ fill: "rgba(255,255,255,0.04)" }} content={({ active, payload }) => {
                        const p = payload?.[0]?.payload as { bin_start: number; bin_end: number; count: number } | undefined;
                        if (!active || !p) return null;
                        return <div className="rounded-lg border border-border-strong bg-card-raised px-3 py-2 text-xs">{money(p.bin_start, cur)} to {money(p.bin_end, cur)}<br /><span className="tabular text-ink">{p.count} runs</span></div>;
                      }} />
                      <Bar dataKey="count" radius={[4, 4, 0, 0]} isAnimationActive={false}>
                        {sim.monte_carlo.histogram.map((h, i) => <Cell key={i} fill={(h.bin_start + h.bin_end) / 2 < 0 ? "var(--color-loss)" : "var(--color-profit)"} />)}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                <div className="mt-2 flex gap-4 text-xs text-ink-3">
                  <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-loss" /> Loss</span>
                  <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-profit" /> Profit</span>
                </div>
                <p className="mt-2 text-[11px] text-ink-3">{sim.monte_carlo.note}</p>
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader><CardTitle>Capital constraints & inventory optimisation</CardTitle><CardDescription>{b.capital_check.note}</CardDescription></CardHeader>
            <CardContent className="space-y-3 text-sm">
              <div className="flex flex-wrap gap-2">
                <Badge variant={b.capital_check.status === "within" ? "good" : b.capital_check.status === "exceeds" ? "critical" : "warning"}>
                  Capital {b.capital_check.status === "unknown" ? "unknown" : b.capital_check.status === "within" ? "sufficient for initial investment" : "below initial investment"}
                </Badge>
                <Badge>Initial investment {money(inputs.initial_investment, cur)}</Badge>
                <Badge>{b.runway_months != null ? `Runway ≈ ${b.runway_months} months` : "Runway n/a"}</Badge>
              </div>
              <p className="text-ink-3">{b.runway_note}</p>
              <p className={cn(sim.optimization.status === "disabled_capital_unknown" ? "text-warning" : "text-ink-2")}>{sim.optimization.message}</p>
              {sim.optimization.status === "optimal" && (
                <table className="w-full text-sm">
                  <thead className="text-xs text-ink-3"><tr><th className="py-1 text-left font-medium">SKU</th><th className="text-right font-medium">Units</th><th className="text-right font-medium">Cost</th><th className="text-right font-medium">Modelled contribution</th></tr></thead>
                  <tbody className="divide-y divide-border">
                    {sim.optimization.allocations.map((a) => (
                      <tr key={a.name}><td className="py-1.5">{a.name}</td><td className="text-right tabular">{num(a.units)} / {num(a.cap)}</td>
                        <td className="text-right tabular">{money(a.cost, cur)}</td><td className="text-right tabular">{money(a.expected_contribution, cur)}</td></tr>
                    ))}
                  </tbody>
                </table>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
