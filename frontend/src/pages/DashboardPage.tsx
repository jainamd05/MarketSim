import { useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { Activity, BarChart3, FileText, FlaskConical, LayoutDashboard, LineChart, Loader2, SlidersHorizontal, Users } from "lucide-react";
import { useViewMode } from "@/components/AppContext";
import { ErrorState, LoadingBlock, PageShell } from "@/components/Layout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { dateTime } from "@/lib/format";
import { CompetitorsTab } from "@/features/dashboard/CompetitorsTab";
import { EvidenceTab } from "@/features/dashboard/EvidenceTab";
import { OverviewTab } from "@/features/dashboard/OverviewTab";
import { EvidenceContext } from "@/features/dashboard/shared";
import { StrategyLabTab } from "@/features/dashboard/StrategyLabTab";
import { TrendsTab } from "@/features/dashboard/TrendsTab";
import { useDashboardData } from "@/features/dashboard/useAnalysis";
import { WarRoom } from "@/features/dashboard/WarRoom";
import { WhatIfTab } from "@/features/dashboard/WhatIfTab";

const TABS = [
  { id: "overview", label: "Overview", icon: LayoutDashboard },
  { id: "competitors", label: "Competitor Intelligence", icon: Users },
  { id: "trends", label: "Market Trends", icon: LineChart },
  { id: "strategy", label: "Strategy Lab", icon: BarChart3 },
  { id: "whatif", label: "What-If Simulator", icon: SlidersHorizontal },
  { id: "warroom", label: "AI Agent War Room", icon: Activity },
  { id: "evidence", label: "Evidence & Risks", icon: FileText },
];

export function DashboardPage() {
  const { id = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") ?? "overview";
  const setTab = (t: string) => setParams({ tab: t }, { replace: true });
  const { data, error } = useDashboardData(id);
  const [strategyKey, setStrategyKey] = useState("S1");
  useViewMode(data?.status.mode);

  const evidenceMap = useMemo(() => Object.fromEntries((data?.evidence?.evidence ?? []).map((e) => [e.ref, e])), [data?.evidence]);

  if (error) return <PageShell><ErrorState title="Could not load this analysis" message={error} action={<Button asChild variant="secondary"><Link to="/">Back home</Link></Button>} /></PageShell>;
  if (!data) return <PageShell><LoadingBlock label="Loading dashboard" /></PageShell>;
  if (["queued", "running"].includes(data.status.status)) {
    return (
      <PageShell>
        <ErrorState title="Analysis still running" message="Results appear when all agents finish."
          action={<Button asChild><Link to={`/analysis/${id}/run`}><Loader2 className="animate-spin" /> Watch progress</Link></Button>} />
      </PageShell>
    );
  }
  if (data.status.status === "failed") {
    return <PageShell><ErrorState title="Analysis failed" message={data.status.error ?? "Unknown error"} /></PageShell>;
  }

  const ps = data.report?.report.profile_summary;
  return (
    <EvidenceContext.Provider value={evidenceMap}>
      <PageShell>
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant={data.status.mode === "demo" ? "warning" : "good"}>
                {data.status.mode === "demo" ? <><FlaskConical /> Demo data</> : "Live data"}
              </Badge>
              <Badge variant={data.status.status === "completed" ? "good" : "warning"}>{data.status.status}</Badge>
              <span className="text-xs text-ink-3">Finished {dateTime(data.status.completed_at)}</span>
            </div>
            <h1 className="mt-2 text-2xl font-semibold tracking-tight sm:text-3xl">
              {ps ? `${String(ps.category)} · ${(ps.focuses as string[]).join(", ") || "custom focus"}` : "Market analysis"}
            </h1>
            <p className="mt-1 text-sm text-ink-3">{ps ? `${String(ps.pilot_country)} pilot · ${String(ps.sales_channel)}` : ""}</p>
          </div>
          <Button variant="secondary" asChild><Link to="/onboarding/review">Edit profile & re-run</Link></Button>
        </div>
        {data.status.status === "partial" && (
          <p className="mt-4 rounded-lg border border-warning/25 bg-warning/[0.06] px-4 py-2.5 text-sm text-warning">
            Partial results: some searches failed, lacked fixtures, or critic checks remain unresolved. Details are in the War Room and Evidence tabs.
          </p>
        )}

        <Tabs value={tab} onValueChange={setTab} className="mt-6">
          <TabsList>
            {TABS.map((t) => <TabsTrigger key={t.id} value={t.id}><t.icon />{t.label}</TabsTrigger>)}
          </TabsList>
          <TabsContent value="overview">
            <OverviewTab data={data} onOpenStrategy={(k) => { setStrategyKey(k); setTab("strategy"); }} />
          </TabsContent>
          <TabsContent value="competitors"><CompetitorsTab data={data.competitors} /></TabsContent>
          <TabsContent value="trends"><TrendsTab data={data.trends} /></TabsContent>
          <TabsContent value="strategy">
            <StrategyLabTab data={data.strategies} selected={strategyKey} onSelect={setStrategyKey}
              onWhatIf={(k) => { setStrategyKey(k); setTab("whatif"); }} />
          </TabsContent>
          <TabsContent value="whatif">
            <WhatIfTab analysisId={id} data={data.strategies} selected={strategyKey} onSelect={setStrategyKey} />
          </TabsContent>
          <TabsContent value="warroom"><WarRoom events={data.events} status={data.status} /></TabsContent>
          <TabsContent value="evidence"><EvidenceTab report={data.report} evidence={data.evidence} /></TabsContent>
        </Tabs>
      </PageShell>
    </EvidenceContext.Provider>
  );
}
