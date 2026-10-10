import { createContext, useContext } from "react";
import { ExternalLink } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { Assumption, EvidenceItem } from "@/lib/types";
import { cn } from "@/lib/utils";

export const STRATEGY_COLORS: Record<string, string> = {
  S1: "var(--color-series-1)",
  S2: "var(--color-series-2)",
  S3: "var(--color-series-3)",
};
export const SERIES = ["var(--color-series-1)", "var(--color-series-2)", "var(--color-series-3)"];

export const EvidenceContext = createContext<Record<string, EvidenceItem>>({});

export function useEvidence() {
  return useContext(EvidenceContext);
}

/** Evidence reference chips. Each links to its source URL (when available) and shows provenance on hover. */
export function Refs({ refs, max = 6, className }: { refs: string[]; max?: number; className?: string }) {
  const evidence = useEvidence();
  if (!refs?.length) return null;
  const shown = refs.slice(0, max);
  return (
    <span className={cn("inline-flex flex-wrap gap-1 align-middle", className)}>
      {shown.map((r) => {
        const ev = evidence[r];
        const title = ev ? `${ev.title}\n${ev.engine} · “${ev.query}” · ${ev.data_origin} · retrieved ${new Date(ev.retrieved_at).toLocaleString()}` : r;
        const cls = "inline-flex items-center gap-0.5 rounded border border-accent/25 bg-accent-soft px-1.5 py-px font-mono text-[10.5px] text-[#9cc3f3] hover:border-accent";
        return ev?.source_url ? (
          <a key={r} href={ev.source_url} target="_blank" rel="noreferrer noopener" title={title} className={cls}>
            {r}<ExternalLink className="h-2.5 w-2.5" />
          </a>
        ) : (
          <span key={r} title={title} className={cls}>{r}</span>
        );
      })}
      {refs.length > max && <span className="text-[10.5px] text-ink-3">+{refs.length - max}</span>}
    </span>
  );
}

const SOURCE_STYLE: Record<Assumption["source"], { label: string; variant: "accent" | "good" | "warning" | "serious" }> = {
  user_input: { label: "Your input", variant: "good" },
  market_evidence: { label: "Market evidence", variant: "accent" },
  scenario_assumption: { label: "Scenario assumption", variant: "warning" },
  llm_proposed: { label: "LLM proposed", variant: "serious" },
};

export function SourceBadge({ source }: { source: Assumption["source"] }) {
  const s = SOURCE_STYLE[source];
  return <Badge variant={s.variant}>{s.label}</Badge>;
}

export function StatTile({ label, value, sub, tone }: { label: string; value: React.ReactNode; sub?: React.ReactNode; tone?: "good" | "bad" | "neutral" }) {
  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <p className="text-xs text-ink-3">{label}</p>
      <p className={cn("mt-1.5 text-2xl font-semibold tracking-tight", tone === "bad" && "text-[#f08a8a]", tone === "good" && "text-[#7fb4f0]")}>{value}</p>
      {sub && <p className="mt-1 text-xs text-ink-3">{sub}</p>}
    </div>
  );
}

export function KindBadge({ kind }: { kind: string }) {
  if (kind === "observed") return <Badge variant="accent">Observed</Badge>;
  if (kind === "modeled") return <Badge variant="warning">Modelled</Badge>;
  if (kind === "critic") return <Badge variant="outline">Critic</Badge>;
  if (kind === "interpretation") return <Badge variant="outline">Interpretation</Badge>;
  if (kind === "market_fact") return <Badge variant="accent">Market fact</Badge>;
  return <Badge>{kind}</Badge>;
}

export function ChartTooltip({ active, payload, label, format }: {
  active?: boolean;
  payload?: { name?: string; value?: number | string; color?: string; payload?: Record<string, unknown> }[];
  label?: string | number;
  format?: (v: number, name?: string) => string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-border-strong bg-card-raised px-3 py-2 text-xs shadow-xl">
      {label !== undefined && <p className="mb-1 font-medium text-ink">{label}</p>}
      {payload.map((p, i) => (
        <p key={i} className="flex items-center gap-2 text-ink-2">
          {p.color && <span className="h-2 w-2 rounded-full" style={{ background: p.color }} />}
          <span>{p.name}</span>
          <span className="ml-auto pl-3 font-medium text-ink tabular">
            {typeof p.value === "number" ? (format ? format(p.value, p.name) : p.value) : p.value ?? "—"}
          </span>
        </p>
      ))}
    </div>
  );
}

export function SectionNote({ children }: { children: React.ReactNode }) {
  return <p className="rounded-lg border border-border bg-page/60 px-3 py-2 text-xs text-ink-3">{children}</p>;
}
