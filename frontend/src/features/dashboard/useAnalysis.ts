import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import type {
  AgentEvent, AnalysisStatus, CompetitorsResponse, EvidenceResponse, ReportResponse, StrategiesResponse, TrendsResponse,
} from "@/lib/types";

const TERMINAL = new Set(["completed", "partial", "failed"]);

/** Polls status + incremental events until the analysis reaches a terminal state. */
export function useAnalysisProgress(id: string, intervalMs = 900) {
  const [status, setStatus] = useState<AnalysisStatus | null>(null);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const lastSeq = useRef(0);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    lastSeq.current = 0;
    setEvents([]);
    const tick = async () => {
      try {
        const [s, ev] = await Promise.all([api.analysis(id), api.events(id, lastSeq.current)]);
        if (cancelled) return;
        if (ev.events.length) {
          lastSeq.current = ev.last_seq;
          setEvents((prev) => [...prev, ...ev.events]);
        }
        setStatus(s);
        setError(null);
        if (!TERMINAL.has(s.status)) timer = setTimeout(tick, intervalMs);
      } catch (e) {
        if (cancelled) return;
        setError((e as Error).message);
        timer = setTimeout(tick, intervalMs * 3);
      }
    };
    void tick();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [id, intervalMs]);

  return { status, events, error, done: status ? TERMINAL.has(status.status) : false };
}

export interface DashboardData {
  status: AnalysisStatus;
  events: AgentEvent[];
  competitors: CompetitorsResponse | null;
  trends: TrendsResponse | null;
  strategies: StrategiesResponse | null;
  report: ReportResponse | null;
  evidence: EvidenceResponse | null;
  errors: Record<string, string>;
}

/** Loads every dashboard resource in parallel; individual failures become partial-result states. */
export function useDashboardData(id: string) {
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const status = await api.analysis(id);
        if (["queued", "running"].includes(status.status)) {
          if (!cancelled) setData({ status, events: [], competitors: null, trends: null, strategies: null, report: null, evidence: null, errors: {} });
          return;
        }
        const calls = {
          events: api.events(id, 0).then((r) => r.events),
          competitors: api.competitors(id),
          trends: api.trends(id),
          strategies: api.strategies(id),
          report: api.report(id),
          evidence: api.evidence(id),
        };
        const keys = Object.keys(calls) as (keyof typeof calls)[];
        const settled = await Promise.allSettled(keys.map((k) => calls[k]));
        const errors: Record<string, string> = {};
        const out: Record<string, unknown> = {};
        settled.forEach((r, i) => {
          if (r.status === "fulfilled") out[keys[i]] = r.value;
          else {
            out[keys[i]] = keys[i] === "events" ? [] : null;
            errors[keys[i]] = (r.reason as Error).message;
          }
        });
        if (!cancelled) setData({ status, ...(out as Omit<DashboardData, "status" | "errors">), errors });
      } catch (e) {
        if (!cancelled) setError((e as Error).message);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id]);

  return { data, error, setData };
}
