import { useMemo, useState } from "react";
import {
  AlertTriangle, CheckCircle2, CircleDashed, CircleSlash, Cpu, FileSearch, GitBranch, Loader2, Play, RefreshCw,
  Search, ShieldCheck, ShieldX, Sparkles, XCircle,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { AgentEvent, AnalysisStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

export const PIPELINE = [
  { id: "supervisor", label: "Supervisor & Planning" },
  { id: "competitor_discovery", label: "Competitor Discovery" },
  { id: "pricing_intelligence", label: "Pricing Intelligence" },
  { id: "demand_trends", label: "Demand & Trends" },
  { id: "market_news", label: "News & Risk" },
  { id: "strategy_generation", label: "Strategy Generation" },
  { id: "quantitative_simulation", label: "Quantitative Simulation" },
  { id: "strategy_critic", label: "Critic & Validation" },
  { id: "report_composer", label: "Report Composer" },
];

const EVENT_STYLE: Record<string, { icon: typeof Play; tone: string; label: string }> = {
  agent_started: { icon: Play, tone: "text-ink-3", label: "Agent started" },
  agent_completed: { icon: CheckCircle2, tone: "text-[#5fd35f]", label: "Agent completed" },
  agent_failed: { icon: XCircle, tone: "text-[#f08a8a]", label: "Agent failed" },
  tool_requested: { icon: Search, tone: "text-[#9cc3f3]", label: "Tool requested" },
  tool_completed: { icon: CheckCircle2, tone: "text-[#9cc3f3]", label: "Tool completed" },
  tool_failed: { icon: XCircle, tone: "text-[#f08a8a]", label: "Tool failed" },
  tool_skipped: { icon: CircleSlash, tone: "text-warning", label: "Tool skipped" },
  evidence_extracted: { icon: FileSearch, tone: "text-ink-2", label: "Evidence extracted" },
  competitors_identified: { icon: FileSearch, tone: "text-ink-2", label: "Competitors identified" },
  plan_created: { icon: GitBranch, tone: "text-ink-2", label: "Plan created" },
  route_selected: { icon: GitBranch, tone: "text-ink-2", label: "Route selected" },
  missing_input: { icon: AlertTriangle, tone: "text-warning", label: "Missing input" },
  analysis_gated: { icon: CircleSlash, tone: "text-warning", label: "Analysis gated" },
  risk_identified: { icon: AlertTriangle, tone: "text-serious", label: "Risk identified" },
  strategy_proposed: { icon: Sparkles, tone: "text-ink", label: "Strategy proposed" },
  llm_requested: { icon: Cpu, tone: "text-ink-2", label: "LLM requested" },
  llm_completed: { icon: Cpu, tone: "text-ink-2", label: "LLM validated" },
  simulation_completed: { icon: Cpu, tone: "text-ink", label: "Simulation completed" },
  critic_accepted: { icon: ShieldCheck, tone: "text-[#5fd35f]", label: "Critic accepted" },
  critic_rejected: { icon: ShieldX, tone: "text-[#f08a8a]", label: "Critic rejected" },
  revision_performed: { icon: RefreshCw, tone: "text-warning", label: "Revision performed" },
  report_composed: { icon: FileSearch, tone: "text-ink-2", label: "Report composed" },
  warning: { icon: AlertTriangle, tone: "text-warning", label: "Warning" },
  analysis_started: { icon: Play, tone: "text-ink-2", label: "Analysis started" },
  analysis_completed: { icon: CheckCircle2, tone: "text-[#5fd35f]", label: "Analysis finished" },
  analysis_failed: { icon: XCircle, tone: "text-[#f08a8a]", label: "Analysis failed" },
};

type AgentState = "pending" | "running" | "done" | "failed";

export function agentStates(events: AgentEvent[], status?: AnalysisStatus | null): Record<string, AgentState> {
  const out: Record<string, AgentState> = Object.fromEntries(PIPELINE.map((p) => [p.id, "pending"]));
  for (const e of events) {
    if (!(e.agent in out)) continue;
    if (e.event_type === "agent_started") out[e.agent] = "running";
    if (e.event_type === "agent_completed") out[e.agent] = "done";
    if (e.event_type === "agent_failed") out[e.agent] = "failed";
  }
  if (status && ["completed", "partial"].includes(status.status)) {
    for (const k of Object.keys(out)) if (out[k] === "running") out[k] = "done";
  }
  return out;
}

export function PipelineStrip({ events, status }: { events: AgentEvent[]; status?: AnalysisStatus | null }) {
  const states = agentStates(events, status);
  const revisions = events.filter((e) => e.event_type === "revision_performed").length;
  return (
    <ol className="grid gap-2 sm:grid-cols-3 lg:grid-cols-9" aria-label="Agent pipeline">
      {PIPELINE.map((p, i) => {
        const s = states[p.id];
        const Icon = s === "done" ? CheckCircle2 : s === "running" ? Loader2 : s === "failed" ? XCircle : CircleDashed;
        return (
          <li key={p.id} data-state={s}
            className={cn("rounded-lg border px-3 py-2.5 text-xs transition-colors",
              s === "running" ? "border-accent bg-accent-soft" : s === "done" ? "border-border bg-card" : s === "failed" ? "border-critical/40 bg-critical/10" : "border-border/60 bg-card/50 text-ink-3")}>
            <span className="flex items-center gap-1.5 font-medium">
              <Icon className={cn("h-3.5 w-3.5 shrink-0", s === "running" && "animate-spin text-accent", s === "done" && "text-good", s === "failed" && "text-critical")} />
              <span className="tabular text-ink-3">{i + 1}</span>
            </span>
            <span className="mt-1 block leading-tight">{p.label}</span>
            {p.id === "strategy_critic" && revisions > 0 && (
              <span className="mt-1 block text-[10px] text-warning">{revisions} revision{revisions > 1 ? "s" : ""}</span>
            )}
          </li>
        );
      })}
    </ol>
  );
}

function MetaChips({ meta }: { meta: Record<string, unknown> }) {
  const chips: [string, string][] = [];
  if (meta.engine) chips.push(["engine", String(meta.engine)]);
  if (meta.query) chips.push(["query", String(meta.query)]);
  if (meta.result_count !== undefined) chips.push(["results", String(meta.result_count)]);
  if (meta.duration_ms !== undefined) chips.push(["ms", String(meta.duration_ms)]);
  if (meta.data_origin && meta.data_origin !== "none") chips.push(["origin", String(meta.data_origin)]);
  if (meta.status && !["ok"].includes(String(meta.status))) chips.push(["status", String(meta.status)]);
  if (meta.attempts && Number(meta.attempts) > 1) chips.push(["attempts", String(meta.attempts)]);
  if (Array.isArray(meta.failed_checks)) chips.push(["failed", (meta.failed_checks as string[]).join(", ")]);
  if (Array.isArray(meta.refs) && meta.refs.length) chips.push(["refs", (meta.refs as string[]).slice(0, 4).join(" ")]);
  if (!chips.length) return null;
  return (
    <div className="mt-1.5 flex flex-wrap gap-1">
      {chips.map(([k, v]) => (
        <span key={k} className="rounded border border-border bg-page px-1.5 py-0.5 font-mono text-[10.5px] text-ink-3">
          <span className="text-ink-3/70">{k}:</span> <span className="text-ink-2">{v}</span>
        </span>
      ))}
    </div>
  );
}

const FILTERS: { id: string; label: string; match: (e: AgentEvent) => boolean }[] = [
  { id: "all", label: "All events", match: () => true },
  { id: "tools", label: "Tool calls", match: (e) => e.event_type.startsWith("tool_") },
  { id: "decisions", label: "Strategy & critic", match: (e) => /strategy|critic|revision|simulation/.test(e.event_type) },
  { id: "issues", label: "Warnings & failures", match: (e) => /failed|skipped|warning|missing|gated|rejected/.test(e.event_type) },
];

export function WarRoom({ events, status, live = false }: { events: AgentEvent[]; status?: AnalysisStatus | null; live?: boolean }) {
  const [filter, setFilter] = useState("all");
  const shown = useMemo(() => {
    const f = FILTERS.find((x) => x.id === filter) ?? FILTERS[0];
    return events.filter(f.match);
  }, [events, filter]);
  const toolCalls = events.filter((e) => e.event_type === "tool_requested").length;

  return (
    <Card>
      <CardHeader className="gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <CardTitle className="flex items-center gap-2">
            AI Agent War Room {live && <span className="h-2 w-2 animate-pulse rounded-full bg-good" aria-label="live" />}
          </CardTitle>
          <p className="mt-1 text-sm text-ink-3">
            {events.length} recorded graph events · {toolCalls} tool requests. These are real execution events, not generated dialogue.
          </p>
        </div>
        <div className="flex flex-wrap gap-1" role="tablist" aria-label="Filter events">
          {FILTERS.map((f) => (
            <button key={f.id} role="tab" aria-selected={filter === f.id} onClick={() => setFilter(f.id)}
              className={cn("rounded-md px-2.5 py-1 text-xs cursor-pointer", filter === f.id ? "bg-card-raised text-ink" : "text-ink-3 hover:text-ink")}>
              {f.label}
            </button>
          ))}
        </div>
      </CardHeader>
      <CardContent>
        <PipelineStrip events={events} status={status} />
        <ol className="mt-5 max-h-[560px] space-y-0 overflow-y-auto rounded-lg border border-border bg-page/60" aria-label="Execution events" data-testid="event-feed">
          {shown.length === 0 && <li className="p-6 text-center text-sm text-ink-3">Waiting for the first event…</li>}
          {shown.map((e) => {
            const style = EVENT_STYLE[e.event_type] ?? { icon: CircleDashed, tone: "text-ink-3", label: e.event_type };
            const Icon = style.icon;
            return (
              <li key={e.seq} className="flex gap-3 border-b border-border/60 px-4 py-2.5 last:border-0 animate-fade-up">
                <Icon className={cn("mt-0.5 h-4 w-4 shrink-0", style.tone)} aria-hidden />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-ink-3">
                    <span className="tabular">#{e.seq}</span>
                    <span className="font-medium text-ink-2">{e.agent_label}</span>
                    <Badge variant="outline" className="py-0">{style.label}</Badge>
                    <span className="tabular">{new Date(e.ts).toLocaleTimeString()}</span>
                  </div>
                  <p className="mt-0.5 text-sm text-ink break-words">{e.message}</p>
                  <MetaChips meta={e.meta} />
                </div>
              </li>
            );
          })}
        </ol>
      </CardContent>
    </Card>
  );
}
