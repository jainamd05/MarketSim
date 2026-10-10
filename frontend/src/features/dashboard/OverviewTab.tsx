import { AlertTriangle, ArrowRight, CheckCircle2, ShieldAlert, Target } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { humanize, money, pct } from "@/lib/format";
import type { DashboardData } from "./useAnalysis";
import { KindBadge, Refs, STRATEGY_COLORS, StatTile } from "./shared";

export function OverviewTab({ data, onOpenStrategy }: { data: DashboardData; onOpenStrategy: (key: string) => void }) {
  const report = data.report?.report;
  const strategies = data.strategies?.strategies ?? [];
  const sims = data.strategies?.simulations ?? {};
  const ps = report?.profile_summary;
  const usage = report?.search_usage;
  const warnings = [
    ...(data.status.plan?.missing_inputs ?? []).map((m) => `${m.label} unknown – ${m.impact}`),
    ...(data.status.warnings ?? []),
    ...Object.entries(data.errors).map(([k, v]) => `Could not load ${k}: ${v}`),
  ];

  return (
    <div className="grid gap-5 lg:grid-cols-3">
      <div className="space-y-5 lg:col-span-2">
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <StatTile label="Analysis status" value={humanize(data.status.status)} sub={`${data.status.mode.toUpperCase()} · ${data.status.llm_mode}`} />
          <StatTile label="SerpApi requests" value={`${usage?.used ?? data.status.requests_used} / ${usage?.budget ?? data.status.request_budget}`}
            sub={usage ? `${usage.cache_hits} cache hits · ${usage.deduplicated} de-duplicated` : undefined} />
          <StatTile label="Evidence items" value={data.evidence?.evidence.length ?? "—"} sub={`${report?.citations.length ?? 0} cited in report`} />
          <StatTile label="Critic decision" value={humanize(report?.critic_summary.final_decision ?? "—")}
            sub={`${report?.critic_summary.revisions_performed ?? 0} revision(s)`} />
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Major findings</CardTitle>
            <CardDescription>Observed facts come from sampled search results; modelled figures depend on labelled assumptions.</CardDescription>
          </CardHeader>
          <CardContent>
            {!report ? <p className="text-sm text-ink-3">No report available.</p> : (
              <ul className="space-y-3">
                {report.headline_findings.map((h, i) => (
                  <li key={i} className="flex gap-3 rounded-lg border border-border bg-page/50 p-3">
                    <span className="pt-0.5"><KindBadge kind={h.kind === "critic" ? "critic" : h.kind} /></span>
                    <div className="min-w-0 text-sm">
                      <p className="text-ink">{h.text}</p>
                      <Refs refs={h.refs} className="mt-1.5" />
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <div>
          <h3 className="mb-3 font-semibold">Candidate strategies</h3>
          <div className="grid gap-4 md:grid-cols-3">
            {strategies.map((s) => {
              const sim = sims[s.key];
              const op = sim?.base.operating_result ?? 0;
              const lastRound = data.strategies?.critic_rounds.at(-1)?.evaluations.find((e) => e.strategy_key === s.key);
              return (
                <Card key={s.key} className="flex flex-col p-5" style={{ borderTopColor: STRATEGY_COLORS[s.key], borderTopWidth: 3 }}>
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-xs font-medium text-ink-3">{s.key} · {s.focus_label}</span>
                    {s.revision > 0 && <Badge variant="warning">rev {s.revision}</Badge>}
                  </div>
                  <h4 className="mt-2 font-semibold leading-snug">{s.name.split(" · ")[0]}</h4>
                  <p className="mt-1.5 line-clamp-3 text-sm text-ink-3">{s.summary}</p>
                  {sim && (
                    <dl className="mt-4 space-y-1.5 text-sm">
                      <div className="flex justify-between"><dt className="text-ink-3">Base operating result</dt>
                        <dd className={op < 0 ? "text-[#f08a8a] tabular" : "tabular"}>{money(op, sim.base.currency)}/mo</dd></div>
                      <div className="flex justify-between"><dt className="text-ink-3">Contribution / order</dt>
                        <dd className="tabular">{money(sim.base.contribution_per_order, sim.base.currency)}</dd></div>
                      <div className="flex justify-between"><dt className="text-ink-3">MC runs negative</dt>
                        <dd className="tabular">{pct(sim.monte_carlo.prob_negative)}</dd></div>
                    </dl>
                  )}
                  <div className="mt-4 flex items-center justify-between gap-2 pt-1">
                    {lastRound && (lastRound.passed
                      ? <Badge variant="good"><CheckCircle2 /> Critic passed</Badge>
                      : <Badge variant="critical"><ShieldAlert /> Unresolved</Badge>)}
                    <Button variant="link" size="sm" onClick={() => onOpenStrategy(s.key)}>Details <ArrowRight /></Button>
                  </div>
                </Card>
              );
            })}
          </div>
          <p className="mt-2 text-xs text-ink-3">Modelled monthly results for a steady-state month – scenarios, not forecasts or guarantees.</p>
        </div>
      </div>

      <div className="space-y-5">
        <Card>
          <CardHeader><CardTitle>Business profile</CardTitle></CardHeader>
          <CardContent>
            {ps && (
              <dl className="divide-y divide-border text-sm">
                {([
                  ["Type", `${humanize(String(ps.business_type))} · ${humanize(String(ps.business_stage))}`],
                  ["Category", String(ps.category)],
                  ["Focus", (ps.focuses as string[]).join(", ") || "—"],
                  ["Pilot market", String(ps.pilot_country) + (ps.worldwide_ambition ? " (worldwide ambition)" : "")],
                  ["Channel", String(ps.sales_channel ?? "—")],
                  ["Budget band", String(ps.budget_band ?? "—")],
                  ["Exact capital", ps.exact_capital_inr == null ? "Unknown" : money(ps.exact_capital_inr as number)],
                  ["Ad budget", ps.monthly_ad_budget_inr == null ? "Unknown" : `${money(ps.monthly_ad_budget_inr as number)}/mo`],
                ] as [string, string][]).map(([k, v]) => (
                  <div key={k} className="flex justify-between gap-3 py-2">
                    <dt className="text-ink-3">{k}</dt>
                    <dd className={v === "Unknown" ? "text-warning" : "text-right"}>{v}</dd>
                  </div>
                ))}
              </dl>
            )}
            <div className="mt-4 flex items-start gap-2 rounded-lg bg-accent-soft p-3 text-sm">
              <Target className="mt-0.5 h-4 w-4 shrink-0 text-accent" />
              <span><span className="text-ink-3">Main objective: </span>{String(ps?.primary_goal ?? "—")}</span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><AlertTriangle className="h-4 w-4 text-warning" /> Evidence & missing-information warnings</CardTitle>
          </CardHeader>
          <CardContent>
            {warnings.length === 0 ? <p className="text-sm text-ink-3">No warnings.</p> : (
              <ul className="space-y-2 text-sm text-ink-2">
                {warnings.map((w, i) => <li key={i} className="flex gap-2"><span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-warning" />{w}</li>)}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
