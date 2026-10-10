import { useState } from "react";
import { AlertTriangle, CheckCircle2, CircleSlash, Minus, Plus, RefreshCw, XCircle } from "lucide-react";
import { EmptyState } from "@/components/Layout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { money, num, pct } from "@/lib/format";
import type { CriticCheck, StrategiesResponse, Strategy, StrategySimulation } from "@/lib/types";
import { cn } from "@/lib/utils";
import { KindBadge, Refs, STRATEGY_COLORS, SourceBadge } from "./shared";

/** Horizontal bear–base–bull range per strategy on one shared axis (one axis, colour = strategy identity). */
function ScenarioRangeChart({ strategies, sims }: { strategies: Strategy[]; sims: Record<string, StrategySimulation> }) {
  const [hover, setHover] = useState<string | null>(null);
  const rows = strategies.map((s) => {
    const sc = Object.fromEntries((sims[s.key]?.scenarios ?? []).map((x) => [x.scenario, x.result.operating_result]));
    return { s, bear: sc.bear ?? 0, base: sc.base ?? 0, bull: sc.bull ?? 0, currency: sims[s.key]?.base.currency ?? "INR" };
  });
  const values = rows.flatMap((r) => [r.bear, r.base, r.bull, 0]);
  const min = Math.min(...values), max = Math.max(...values);
  const pad = (max - min) * 0.08 || 1;
  const lo = min - pad, hi = max + pad;
  const W = 640, rowH = 46, left = 150, right = 20, top = 16;
  const H = top + rows.length * rowH + 28;
  const x = (v: number) => left + ((v - lo) / (hi - lo)) * (W - left - right);
  const ticks = Array.from({ length: 5 }, (_, i) => lo + ((hi - lo) * i) / 4);

  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Modelled monthly operating result: bear, base and bull scenarios per strategy">
        {ticks.map((t) => (
          <g key={t}>
            <line x1={x(t)} x2={x(t)} y1={top - 6} y2={H - 26} stroke="var(--color-grid)" />
            <text x={x(t)} y={H - 10} textAnchor="middle" fontSize={11} fill="var(--color-ink-3)">{money(t, rows[0]?.currency, { compact: true })}</text>
          </g>
        ))}
        <line x1={x(0)} x2={x(0)} y1={top - 6} y2={H - 26} stroke="var(--color-axis)" strokeWidth={1.5} />
        {rows.map((r, i) => {
          const y = top + i * rowH + rowH / 2;
          const color = STRATEGY_COLORS[r.s.key];
          return (
            <g key={r.s.key} onMouseEnter={() => setHover(r.s.key)} onMouseLeave={() => setHover(null)} className="cursor-default">
              <rect x={0} y={y - rowH / 2} width={W} height={rowH} fill={hover === r.s.key ? "rgba(255,255,255,0.03)" : "transparent"} />
              <text x={8} y={y - 4} fontSize={12} fill="var(--color-ink)">{r.s.key} · {r.s.archetype.replace(/_/g, " ")}</text>
              <text x={8} y={y + 11} fontSize={10.5} fill="var(--color-ink-3)">{r.s.focus_label}</text>
              <line x1={x(r.bear)} x2={x(r.bull)} y1={y} y2={y} stroke={color} strokeWidth={4} strokeLinecap="round" opacity={0.55} />
              <circle cx={x(r.bear)} cy={y} r={4} fill="var(--color-card)" stroke={color} strokeWidth={2} />
              <circle cx={x(r.bull)} cy={y} r={4} fill="var(--color-card)" stroke={color} strokeWidth={2} />
              <circle cx={x(r.base)} cy={y} r={6.5} fill={color} stroke="var(--color-card)" strokeWidth={2} />
            </g>
          );
        })}
      </svg>
      {hover && (() => {
        const r = rows.find((x) => x.s.key === hover)!;
        return (
          <div className="pointer-events-none absolute right-2 top-2 rounded-lg border border-border-strong bg-card-raised px-3 py-2 text-xs shadow-xl">
            <p className="mb-1 font-medium">{r.s.name}</p>
            {(["bear", "base", "bull"] as const).map((k) => (
              <p key={k} className="flex justify-between gap-6 text-ink-2"><span className="capitalize">{k}</span><span className="tabular text-ink">{money(r[k], r.currency)}/mo</span></p>
            ))}
          </div>
        );
      })()}
      <div className="mt-1 flex flex-wrap gap-4 text-xs text-ink-3">
        <span className="flex items-center gap-1.5"><span className="h-3 w-3 rounded-full bg-ink-2" /> Base case</span>
        <span className="flex items-center gap-1.5"><span className="h-3 w-3 rounded-full border-2 border-ink-2" /> Bear (left) / bull (right)</span>
        {strategies.map((s) => (
          <span key={s.key} className="flex items-center gap-1.5"><span className="h-2 w-4 rounded" style={{ background: STRATEGY_COLORS[s.key] }} />{s.key}</span>
        ))}
      </div>
    </div>
  );
}

const CHECK_ICON: Record<CriticCheck["status"], { icon: typeof CheckCircle2; cls: string; label: string }> = {
  pass: { icon: CheckCircle2, cls: "text-good", label: "Pass" },
  fail: { icon: XCircle, cls: "text-critical", label: "Fail" },
  warn: { icon: AlertTriangle, cls: "text-warning", label: "Warning" },
  not_applicable: { icon: CircleSlash, cls: "text-ink-3", label: "N/A" },
};

export function StrategyLabTab({ data, selected, onSelect, onWhatIf }: {
  data: StrategiesResponse | null; selected: string; onSelect: (k: string) => void; onWhatIf: (k: string) => void;
}) {
  if (!data || data.strategies.length === 0) return <EmptyState title="No strategies" message="Strategy generation did not produce results for this analysis." />;
  const s = data.strategies.find((x) => x.key === selected) ?? data.strategies[0];
  const sim = data.simulations[s.key];
  const rounds = data.critic_rounds.map((r) => ({ ...r, ev: r.evaluations.find((e) => e.strategy_key === s.key) })).filter((r) => r.ev);
  const cur = sim?.base.currency ?? "INR";

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <CardTitle>Modelled monthly operating result by scenario</CardTitle>
          <CardDescription>Bear and bull apply the stated, bounded adjustments to each strategy's base assumptions. Modelled – not forecasts.</CardDescription>
        </CardHeader>
        <CardContent><ScenarioRangeChart strategies={data.strategies} sims={data.simulations} /></CardContent>
      </Card>

      <div className="grid gap-3 md:grid-cols-3" role="radiogroup" aria-label="Select strategy">
        {data.strategies.map((x) => (
          <button key={x.key} role="radio" aria-checked={x.key === s.key} onClick={() => onSelect(x.key)}
            className={cn("rounded-xl border bg-card p-4 text-left transition-colors cursor-pointer", x.key === s.key ? "border-accent ring-1 ring-accent/40" : "border-border hover:border-border-strong")}>
            <span className="flex items-center gap-2 text-xs text-ink-3">
              <span className="h-2.5 w-2.5 rounded-full" style={{ background: STRATEGY_COLORS[x.key] }} />{x.key} · {x.generated_by === "llm" ? "LLM-drafted" : "rule-based"}
              {x.revision > 0 && <Badge variant="warning">revised ×{x.revision}</Badge>}
            </span>
            <span className="mt-1.5 block font-semibold">{x.name}</span>
          </button>
        ))}
      </div>

      <div className="grid gap-5 lg:grid-cols-3">
        <div className="space-y-5 lg:col-span-2">
          <Card>
            <CardHeader className="sm:flex-row sm:items-start sm:justify-between">
              <div>
                <CardTitle>{s.name}</CardTitle>
                <CardDescription className="mt-1">{s.summary}</CardDescription>
              </div>
              <Button size="sm" variant="secondary" onClick={() => onWhatIf(s.key)}>Open in What-If</Button>
            </CardHeader>
            <CardContent className="space-y-4 text-sm">
              {([["Positioning", s.positioning], ["Price logic", s.price_logic], ["Channel choice", s.channel_choice]] as const).map(([k, v]) => (
                <div key={k}><p className="text-xs font-medium uppercase tracking-wide text-ink-3">{k}</p><p className="mt-1 text-ink-2">{v}</p></div>
              ))}
              <div className="grid gap-4 sm:grid-cols-3">
                {([["Advantages", s.advantages, Plus, "text-good"], ["Disadvantages", s.disadvantages, Minus, "text-critical"],
                  ["Operating trade-offs", s.operating_tradeoffs, AlertTriangle, "text-warning"]] as const).map(([title, items, Icon, cls]) => (
                  <div key={title}>
                    <p className="text-xs font-medium uppercase tracking-wide text-ink-3">{title}</p>
                    <ul className="mt-1.5 space-y-1.5">
                      {items.map((t) => <li key={t} className="flex gap-1.5 text-ink-2"><Icon className={cn("mt-0.5 h-3.5 w-3.5 shrink-0", cls)} />{t}</li>)}
                    </ul>
                  </div>
                ))}
              </div>
              {s.revision_notes.length > 0 && (
                <div className="rounded-lg border border-warning/25 bg-warning/[0.06] p-3">
                  <p className="flex items-center gap-1.5 text-xs font-medium text-warning"><RefreshCw className="h-3.5 w-3.5" /> Critic-driven revisions</p>
                  <ul className="mt-1 list-disc pl-5 text-ink-2">{s.revision_notes.map((n) => <li key={n}>{n}</li>)}</ul>
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle>Product mix</CardTitle><CardDescription>Target prices and unit costs are inputs to the inventory optimiser.</CardDescription></CardHeader>
            <CardContent className="overflow-x-auto">
              <table className="w-full min-w-[520px] text-sm">
                <thead className="border-b border-border text-xs text-ink-3"><tr>
                  <th className="py-2 text-left font-medium">SKU</th><th className="text-right font-medium">Price</th>
                  <th className="text-right font-medium">Unit cost</th><th className="text-right font-medium">Share</th><th className="text-right font-medium">Stocking cap</th>
                </tr></thead>
                <tbody className="divide-y divide-border">
                  {s.product_mix.map((m) => (
                    <tr key={m.name}><td className="py-2">{m.name}</td><td className="text-right tabular">{money(m.target_price, cur)}</td>
                      <td className="text-right tabular">{money(m.unit_cost, cur)}</td><td className="text-right tabular">{m.share_pct}%</td>
                      <td className="text-right tabular">{num(m.max_monthly_units)}</td></tr>
                  ))}
                </tbody>
              </table>
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle>Required assumptions</CardTitle><CardDescription>Every simulator input with its source. Scenario assumptions are editable in What-If.</CardDescription></CardHeader>
            <CardContent className="overflow-x-auto">
              <table className="w-full min-w-[640px] text-sm">
                <tbody className="divide-y divide-border">
                  {s.assumptions.map((a) => (
                    <tr key={a.key} className="align-top">
                      <td className="py-2.5 pr-3 font-medium">{a.label}</td>
                      <td className="py-2.5 pr-3 tabular whitespace-nowrap">{a.value === null ? <Badge variant="warning">Unknown</Badge> : typeof a.value === "number" ? `${num(a.value, 2)} ` : a.value}<span className="text-xs text-ink-3">{a.value !== null ? a.unit : ""}</span></td>
                      <td className="py-2.5 pr-3"><SourceBadge source={a.source} /></td>
                      <td className="py-2.5 text-xs text-ink-3">{a.rationale} <Refs refs={a.evidence_refs} max={3} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle>Claims and evidence</CardTitle></CardHeader>
            <CardContent>
              <ul className="space-y-2.5 text-sm">
                {s.claims.map((c, i) => (
                  <li key={i} className="flex gap-3"><span className="pt-0.5"><KindBadge kind={c.kind} /></span>
                    <span className="text-ink-2">{c.text} <Refs refs={c.evidence_refs} max={4} /></span></li>
                ))}
              </ul>
            </CardContent>
          </Card>
        </div>

        <div className="space-y-5">
          {sim && (
            <Card>
              <CardHeader><CardTitle>Modelled outcome (base)</CardTitle></CardHeader>
              <CardContent>
                <dl className="space-y-2 text-sm">
                  {([
                    ["Orders / month", `${num(sim.base.orders.total, 1)}`],
                    ["Order value", money(sim.base.average_order_value, cur)],
                    ["Revenue / month", money(sim.base.revenue, cur)],
                    ["Contribution / order", money(sim.base.contribution_per_order, cur)],
                    ["Operating result", money(sim.base.operating_result, cur)],
                    ["Break-even orders", sim.base.break_even_orders != null ? num(sim.base.break_even_orders) : "Not achievable"],
                    ["Monte Carlo P5 / P50 / P95", `${money(sim.monte_carlo.percentiles.p5, cur, { compact: true })} / ${money(sim.monte_carlo.percentiles.p50, cur, { compact: true })} / ${money(sim.monte_carlo.percentiles.p95, cur, { compact: true })}`],
                    ["Runs with a loss", pct(sim.monte_carlo.prob_negative)],
                  ] as [string, string][]).map(([k, v]) => (
                    <div key={k} className="flex justify-between gap-3"><dt className="text-ink-3">{k}</dt><dd className="text-right tabular">{v}</dd></div>
                  ))}
                </dl>
                {sim.base.warnings.map((w) => <p key={w} className="mt-3 text-xs text-warning">⚠ {w}</p>)}
              </CardContent>
            </Card>
          )}
          <Card>
            <CardHeader><CardTitle>Critic checks</CardTitle><CardDescription>Structured pass/fail per round – no prose praise.</CardDescription></CardHeader>
            <CardContent className="space-y-4">
              {rounds.map((r) => (
                <div key={r.round}>
                  <p className="mb-2 flex items-center justify-between text-xs text-ink-3">
                    <span>Round {r.round} · revision {r.ev!.revision}</span>
                    {r.ev!.passed ? <Badge variant="good">accepted</Badge> : <Badge variant="critical">rejected</Badge>}
                  </p>
                  <ul className="space-y-1.5">
                    {r.ev!.checks.map((c) => {
                      const st = CHECK_ICON[c.status];
                      return (
                        <li key={c.id} className="flex gap-2 text-xs" title={c.reason}>
                          <st.icon className={cn("mt-0.5 h-3.5 w-3.5 shrink-0", st.cls)} aria-label={st.label} />
                          <span><span className="text-ink">{c.label}</span>{c.severity === "blocking" && <span className="text-ink-3"> · blocking</span>}
                            {(c.status === "fail" || c.status === "warn") && <span className="block text-ink-3">{c.reason}</span>}</span>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
