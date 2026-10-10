import { Link, useParams } from "react-router-dom";
import { ArrowRight, Gauge, Loader2 } from "lucide-react";
import { useViewMode } from "@/components/AppContext";
import { ErrorState, PageShell } from "@/components/Layout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { useAnalysisProgress } from "@/features/dashboard/useAnalysis";
import { WarRoom } from "@/features/dashboard/WarRoom";

export function RunPage() {
  const { id = "" } = useParams();
  const { status, events, error, done } = useAnalysisProgress(id);
  useViewMode(status?.mode);

  if (error && !status) {
    return <PageShell><ErrorState title="Could not load the analysis" message={error} /></PageShell>;
  }
  const percent = status?.progress.percent ?? 0;
  const failed = status?.status === "failed";

  return (
    <PageShell>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm font-medium text-accent">Agent execution</p>
          <h1 className="mt-1 text-3xl font-semibold tracking-tight">
            {done ? (failed ? "Analysis failed" : "Analysis finished") : "Agents are researching your market"}
          </h1>
          <p className="mt-2 text-ink-3">
            {status ? <>Mode <Badge variant={status.mode === "demo" ? "warning" : "good"}>{status.mode.toUpperCase()}</Badge> · {status.llm_mode}</> : "Connecting…"}
          </p>
        </div>
        {done && !failed && (
          <Button size="lg" asChild><Link to={`/analysis/${id}`}>Open dashboard <ArrowRight /></Link></Button>
        )}
      </div>

      <div className="mt-6 grid gap-4 md:grid-cols-3">
        <Card className="p-5 md:col-span-2">
          <div className="flex items-center justify-between text-sm">
            <span className="flex items-center gap-2 font-medium">
              {!done && <Loader2 className="h-4 w-4 animate-spin text-accent" />}
              {status?.current_agent ? `Running: ${status.current_agent.replace(/_/g, " ")}` : done ? `Status: ${status?.status}` : "Queued"}
            </span>
            <span className="tabular text-ink-3">{percent}%</span>
          </div>
          <Progress className="mt-3" value={percent} aria-label="Analysis progress" />
          {status?.status === "partial" && (
            <p className="mt-3 text-sm text-warning">Finished with partial results – some searches or checks failed and are reported, not hidden.</p>
          )}
          {failed && <p className="mt-3 text-sm text-[#f08a8a]">{status?.error}</p>}
        </Card>
        <Card className="p-5" data-testid="request-counter">
          <p className="flex items-center gap-2 text-sm text-ink-3"><Gauge className="h-4 w-4" /> SerpApi requests</p>
          <p className="mt-2 text-3xl font-semibold tabular">
            {status?.requests_used ?? 0}<span className="text-lg text-ink-3"> / {status?.request_budget ?? "–"}</span>
          </p>
          <p className="mt-1 text-xs text-ink-3">
            {status?.mode === "demo" ? "Fixture loads counted against the budget; no API credits used." : `${status?.cache_hits ?? 0} cache hit(s) – cached results cost nothing.`}
          </p>
        </Card>
      </div>

      <div className="mt-6">
        <WarRoom events={events} status={status} live={!done} />
      </div>
    </PageShell>
  );
}
