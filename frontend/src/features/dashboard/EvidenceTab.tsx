import { useState } from "react";
import { AlertOctagon, AlertTriangle, ExternalLink, HelpCircle, Info } from "lucide-react";
import { EmptyState } from "@/components/Layout";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { dateOnly, dateTime, num } from "@/lib/format";
import type { EvidenceResponse, ReportResponse } from "@/lib/types";
import { cn } from "@/lib/utils";
import { KindBadge, Refs, SourceBadge } from "./shared";

const SEVERITY = {
  high: { variant: "critical" as const, icon: AlertOctagon },
  medium: { variant: "serious" as const, icon: AlertTriangle },
  low: { variant: "default" as const, icon: Info },
};

export function EvidenceTab({ report, evidence }: { report: ReportResponse | null; evidence: EvidenceResponse | null }) {
  const [engine, setEngine] = useState("all");
  if (!report) return <EmptyState title="Report unavailable" message="No report was produced for this analysis." />;
  const r = report.report;
  const engines = [...new Set(r.citations.map((c) => c.engine))];
  const citations = r.citations.filter((c) => engine === "all" || c.engine === engine);
  const assumptionsBySource = r.assumptions.reduce<Record<string, number>>((acc, a) => ({ ...acc, [a.source]: (acc[a.source] ?? 0) + 1 }), {});

  return (
    <div className="space-y-5">
      <Card className="border-warning/25">
        <CardContent className="pt-5 text-sm text-ink-2">{r.disclaimer}</CardContent>
      </Card>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>Verified observations</CardTitle><CardDescription>Facts observed in retrieved search results, each with references.</CardDescription></CardHeader>
          <CardContent>
            <ul className="space-y-3 text-sm">
              {r.observed_facts.map((o, i) => (
                <li key={i} className="border-l-2 border-accent/40 pl-3">
                  <p className="text-ink-2">{o.text}</p>
                  <div className="mt-1 flex flex-wrap items-center gap-1.5">
                    <Badge>{o.type.replace(/_/g, " ")}</Badge>
                    {o.nature && <Badge variant={o.nature === "forward_looking" ? "warning" : "default"}>{o.nature.replace(/_/g, " ")}</Badge>}
                    <Refs refs={o.refs} max={4} />
                  </div>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>

        <div className="space-y-5">
          <Card>
            <CardHeader><CardTitle>Risks</CardTitle><CardDescription>Evidence-based risks are separated from general category guidance. Not a compliance certification.</CardDescription></CardHeader>
            <CardContent>
              <ul className="space-y-2.5 text-sm">
                {r.risks.map((k) => {
                  const s = SEVERITY[k.severity];
                  return (
                    <li key={k.id} className="flex gap-3">
                      <s.icon className={cn("mt-0.5 h-4 w-4 shrink-0", k.severity === "high" ? "text-critical" : k.severity === "medium" ? "text-serious" : "text-ink-3")} aria-hidden />
                      <div>
                        <p className="flex flex-wrap items-center gap-1.5 font-medium">{k.title}
                          <Badge variant={s.variant}>{k.severity}</Badge><Badge variant="outline">{k.basis.replace(/_/g, " ")}</Badge></p>
                        <p className="text-ink-3">{k.detail} <Refs refs={k.evidence_refs} max={3} /></p>
                      </div>
                    </li>
                  );
                })}
              </ul>
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle className="flex items-center gap-2"><HelpCircle className="h-4 w-4 text-warning" /> Unresolved information</CardTitle></CardHeader>
            <CardContent>
              <ul className="list-disc space-y-1.5 pl-5 text-sm text-ink-2">{r.unresolved_questions.map((q) => <li key={q}>{q}</li>)}</ul>
            </CardContent>
          </Card>
        </div>
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Assumptions</CardTitle>
            <CardDescription>
              {Object.entries(assumptionsBySource).map(([k, v]) => `${v} ${k.replace(/_/g, " ")}`).join(" · ")}
            </CardDescription>
          </CardHeader>
          <CardContent className="max-h-[420px] overflow-y-auto">
            <table className="w-full text-sm">
              <tbody className="divide-y divide-border">
                {r.assumptions.map((a, i) => (
                  <tr key={i} className="align-top">
                    <td className="py-2 pr-2 text-xs text-ink-3">{a.strategy}</td>
                    <td className="py-2 pr-2">{a.label}</td>
                    <td className="py-2 pr-2 tabular whitespace-nowrap">{a.value === null ? "Unknown" : typeof a.value === "number" ? num(a.value, 2) : a.value}</td>
                    <td className="py-2"><SourceBadge source={a.source} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Known limitations</CardTitle></CardHeader>
          <CardContent>
            <ul className="list-disc space-y-1.5 pl-5 text-sm text-ink-2">{r.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
            <div className="mt-4 space-y-1 rounded-lg border border-border bg-page/60 p-3 font-mono text-[11px] text-ink-3">
              <p>inputs_hash  {report.inputs_hash.slice(0, 24)}…</p>
              <p>content_hash {report.content_hash.slice(0, 24)}…</p>
              <p className="font-sans">The report is rebuilt from the stored profile, stored SerpApi responses and a fixed simulation seed.</p>
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader className="gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <CardTitle>Source references ({r.citations.length})</CardTitle>
            <CardDescription>Every cited observation with engine, query, retrieval time, freshness and data origin.</CardDescription>
          </div>
          <select aria-label="Filter citations by engine" value={engine} onChange={(e) => setEngine(e.target.value)}
            className="h-9 rounded-lg border border-border-strong bg-page px-2 text-sm [&>option]:bg-card">
            <option value="all">All engines</option>
            {engines.map((e) => <option key={e} value={e}>{e}</option>)}
          </select>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          <table className="w-full min-w-[900px] text-sm" data-testid="citations">
            <thead className="border-b border-border text-xs text-ink-3">
              <tr>{["Ref", "Title", "Engine · query", "Classification", "Published", "Retrieved", "Data"].map((h) => <th key={h} className="px-2 py-2 text-left font-medium">{h}</th>)}</tr>
            </thead>
            <tbody className="divide-y divide-border">
              {citations.map((c) => (
                <tr key={c.ref} id={`ev-${c.ref}`} className="align-top">
                  <td className="px-2 py-2 font-mono text-xs text-ink-3">{c.ref}</td>
                  <td className="max-w-[320px] px-2 py-2">
                    {c.url ? <a href={c.url} target="_blank" rel="noreferrer noopener" className="inline-flex items-start gap-1 text-ink hover:text-accent">{c.title}<ExternalLink className="mt-1 h-3 w-3 shrink-0" /></a> : c.title}
                  </td>
                  <td className="px-2 py-2 text-xs text-ink-2"><code>{c.engine}</code> · “{c.query}”</td>
                  <td className="px-2 py-2 text-xs text-ink-3">{c.classification.replace(/_/g, " ")}</td>
                  <td className="px-2 py-2 text-xs text-ink-3">{dateOnly(c.published_at)}</td>
                  <td className="px-2 py-2 text-xs text-ink-3 whitespace-nowrap">{dateTime(c.retrieved_at)}</td>
                  <td className="px-2 py-2"><Badge variant={c.data_origin === "demo_fixture" ? "warning" : "good"}>{c.data_origin === "demo_fixture" ? "Demo data" : c.data_origin}</Badge></td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>

      {evidence && (
        <Card>
          <CardHeader>
            <CardTitle>SerpApi request log ({evidence.searches.length})</CardTitle>
            <CardDescription>{r.search_usage.billable_note}</CardDescription>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <table className="w-full min-w-[800px] text-sm">
              <thead className="border-b border-border text-xs text-ink-3">
                <tr>{["Engine", "Parameters", "Agent", "Status", "Results", "Duration", "Origin"].map((h) => <th key={h} className="px-2 py-2 text-left font-medium">{h}</th>)}</tr>
              </thead>
              <tbody className="divide-y divide-border">
                {evidence.searches.map((s, i) => (
                  <tr key={i} className="align-top">
                    <td className="px-2 py-2"><code className="text-xs">{s.engine}</code></td>
                    <td className="max-w-[340px] px-2 py-2 font-mono text-[11px] text-ink-3 break-all">{Object.entries(s.params).map(([k, v]) => `${k}=${v}`).join("&")}</td>
                    <td className="px-2 py-2 text-xs text-ink-2">{s.agent.replace(/_/g, " ")}</td>
                    <td className="px-2 py-2"><Badge variant={s.status === "ok" ? "good" : s.status === "empty" ? "warning" : "critical"}>{s.status}</Badge>
                      {s.error && <p className="mt-1 text-[11px] text-ink-3">{s.error}</p>}</td>
                    <td className="px-2 py-2 tabular">{s.result_count}</td>
                    <td className="px-2 py-2 tabular text-xs text-ink-3">{num(s.duration_ms, 1)} ms</td>
                    <td className="px-2 py-2 text-xs">{s.data_origin}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}
      <p className="text-xs text-ink-3"><KindBadge kind="observed" /> items come from retrieved results; modelled figures live in the Strategy Lab and What-If tabs.</p>
    </div>
  );
}
