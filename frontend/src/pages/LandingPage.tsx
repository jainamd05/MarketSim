import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  ArrowRight, BarChart3, Brain, Calculator, ClipboardList, FileText, Loader2, Newspaper, Play, Scale, Search,
  ShieldCheck, ShoppingBag, Sparkles, TrendingUp,
} from "lucide-react";
import { useApp } from "@/components/AppContext";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { api } from "@/lib/api";
import { dateTime } from "@/lib/format";
import { fromProfile, storeDraft } from "@/features/onboarding/flow";

const AGENTS = [
  { icon: ClipboardList, name: "Supervisor & Planner", body: "Validates the profile, routes online vs physical research, flags unknown inputs and allocates a bounded SerpApi budget." },
  { icon: Search, name: "Competitor Discovery", body: "Google Shopping, Google Search, Amazon and – for shops – Google Maps. Deduplicates merchants and keeps every link." },
  { icon: ShoppingBag, name: "Pricing Intelligence", body: "Google Product offers, pack-size normalisation, sampled min/median/max, currency and outlier flags." },
  { icon: TrendingUp, name: "Demand & Trends", body: "Google Trends interest over time and related queries – relative interest, never presented as sales demand." },
  { icon: Newspaper, name: "News & Risk", body: "Google News developments with dates and links; reported facts kept apart from speculation." },
  { icon: Sparkles, name: "Strategy Generation", body: "Three distinct, simulatable strategies with evidence references and explicitly labelled assumptions." },
  { icon: Calculator, name: "Quantitative Simulation", body: "Deterministic NumPy/SciPy unit economics, bear/base/bull, seeded Monte Carlo and a MILP inventory optimiser." },
  { icon: Scale, name: "Critic & Validation", body: "Structured pass/fail checks – evidence, currency, margins, CAC, capital – with up to two targeted revisions." },
  { icon: FileText, name: "Report Composer", body: "Observed facts, modelled scenarios, citations, unresolved questions and limitations – reproducible from stored inputs." },
];

const DEMO_ROWS: [string, string][] = [
  ["Business model", "Online business, new"],
  ["Category", "Food & Beverages – focus undecided"],
  ["Comparing", "Packaged snacks · Coffee and tea · Premium pantry"],
  ["Markets", "Worldwide ambition · pilot: India"],
  ["Sales channel", "Own website + marketplaces"],
  ["Capital", "Above ₹10 lakh · exact amount unknown"],
  ["Digital advertising", "₹40,000 / month"],
  ["Sourcing / goal", "Undecided · competitor intelligence"],
];

export function LandingPage() {
  const navigate = useNavigate();
  const { config } = useApp();
  const [busy, setBusy] = useState<"load" | "run" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [recent, setRecent] = useState<Awaited<ReturnType<typeof api.listAnalyses>>>([]);

  useEffect(() => {
    api.listAnalyses().then(setRecent).catch(() => setRecent([]));
  }, []);

  const loadDemo = async (run: boolean) => {
    setBusy(run ? "run" : "load");
    setError(null);
    try {
      const profile = await api.demoProfile();
      if (!run) {
        storeDraft({ draft: fromProfile(profile), step: "advanced", profileId: null });
        navigate("/onboarding/review");
        return;
      }
      const created = await api.createProfile(profile, "confirmed");
      storeDraft({ draft: fromProfile(profile), step: "advanced", profileId: created.profile.id });
      const res = await api.createAnalysis(created.profile.id, "demo");
      navigate(`/analysis/${res.analysis_id}/run`);
    } catch (e) {
      setError((e as Error).message);
      setBusy(null);
    }
  };

  return (
    <div>
      <section className="relative overflow-hidden border-b border-border">
        <div className="bg-grid pointer-events-none absolute inset-0" />
        <div className="pointer-events-none absolute -top-40 left-1/2 h-80 w-[48rem] -translate-x-1/2 rounded-full bg-accent/15 blur-3xl" />
        <div className="relative mx-auto grid max-w-7xl gap-12 px-4 py-16 sm:px-6 lg:grid-cols-[1.15fr_1fr] lg:py-24">
          <div className="animate-fade-up">
            <Badge variant="accent" className="mb-5"><Brain /> Multi-agent research · deterministic simulation</Badge>
            <h1 className="text-4xl font-semibold leading-[1.08] tracking-tight sm:text-5xl lg:text-[3.6rem]">
              Test your business idea against the market <span className="text-accent">before</span> you spend capital.
            </h1>
            <p className="mt-6 max-w-xl text-lg text-ink-2">
              Nine specialised AI agents research real competitors, prices, search trends and news through SerpApi,
              build three concrete strategies, simulate them with auditable maths, and let a critic reject weak assumptions.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Button size="lg" asChild><Link to="/onboarding">Start analysis <ArrowRight /></Link></Button>
              <Button size="lg" variant="secondary" onClick={() => loadDemo(true)} disabled={!!busy}>
                {busy === "run" ? <Loader2 className="animate-spin" /> : <Play />} Run the demo profile
              </Button>
            </div>
            {error && <p role="alert" className="mt-4 text-sm text-[#f08a8a]">{error}</p>}
            <ul className="mt-8 grid gap-2 text-sm text-ink-3 sm:grid-cols-2">
              {["Every market claim links to its source", "Unknown inputs stay unknown – never zero",
                "Profit figures are modelled scenarios, not promises", "Search budget capped per analysis"].map((t) => (
                <li key={t} className="flex items-center gap-2"><ShieldCheck className="h-4 w-4 text-good" /> {t}</li>
              ))}
            </ul>
          </div>

          <Card className="animate-fade-up self-start p-6 [animation-delay:120ms]">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-medium uppercase tracking-wider text-ink-3">Demonstration profile</p>
                <p className="mt-1 font-semibold">D2C food brand, India pilot</p>
              </div>
              <Badge variant="warning">Uses demo fixtures</Badge>
            </div>
            <dl className="mt-5 divide-y divide-border text-sm">
              {DEMO_ROWS.map(([k, v]) => (
                <div key={k} className="flex justify-between gap-4 py-2.5">
                  <dt className="text-ink-3">{k}</dt>
                  <dd className="text-right font-medium">{v}</dd>
                </div>
              ))}
            </dl>
            <div className="mt-5 flex flex-wrap gap-2">
              <Button className="flex-1" onClick={() => loadDemo(true)} disabled={!!busy}>
                {busy === "run" ? <Loader2 className="animate-spin" /> : <Play />} Run demo analysis
              </Button>
              <Button variant="secondary" className="flex-1" onClick={() => loadDemo(false)} disabled={!!busy}>
                {busy === "load" && <Loader2 className="animate-spin" />} Review & edit first
              </Button>
            </div>
            <p className="mt-3 text-xs text-ink-3">
              Demo mode replays saved SerpApi-format fixtures for the demonstration profile and fills any other profile with deterministic synthetic responses – fictional brands, never real-time data. {config?.live_available
                ? "A SerpApi key is configured, so you can switch to live data on the review screen."
                : "Add SERPAPI_API_KEY to run the same workflow on live data."}
            </p>
          </Card>
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-4 py-16 sm:px-6">
        <div className="max-w-2xl">
          <p className="text-sm font-medium text-accent">How it works</p>
          <h2 className="mt-2 text-3xl font-semibold tracking-tight">A LangGraph workflow, not a chatbot</h2>
          <p className="mt-3 text-ink-3">
            Each agent is a named node in a stateful graph with conditional routing and a bounded critique loop.
            The War Room shows every real execution event: which tool ran, how many results came back and how long it took.
          </p>
        </div>
        <ol className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {AGENTS.map((a, i) => (
            <li key={a.name}>
              <Card className="group h-full p-5 transition-colors hover:border-border-strong">
                <div className="flex items-center gap-3">
                  <span className="flex h-9 w-9 items-center justify-center rounded-lg border border-border bg-card-raised text-accent">
                    <a.icon className="h-4 w-4" />
                  </span>
                  <span className="text-xs font-medium text-ink-3 tabular">Agent {i + 1}</span>
                </div>
                <h3 className="mt-4 font-semibold">{a.name}</h3>
                <p className="mt-1.5 text-sm text-ink-3">{a.body}</p>
              </Card>
            </li>
          ))}
        </ol>
        <div className="mt-8 grid gap-4 lg:grid-cols-2">
          <Card className="p-5">
            <h3 className="flex items-center gap-2 font-semibold"><BarChart3 className="h-4 w-4 text-accent" /> SerpApi engines used</h3>
            <div className="mt-3 flex flex-wrap gap-2">
              {(config?.engines ?? ["amazon", "google", "google_autocomplete", "google_immersive_product", "google_maps", "google_news", "google_product", "google_shopping", "google_trends"]).map((e) => (
                <code key={e} className="rounded-md border border-border bg-page px-2 py-1 text-xs text-ink-2">{e}</code>
              ))}
            </div>
            <p className="mt-3 text-xs text-ink-3">All requests originate from the Python backend through one gateway with an engine allowlist, caching, de-duplication, retries and a request budget.</p>
          </Card>
          <Card className="p-5">
            <h3 className="font-semibold">Recent analyses on this machine</h3>
            {recent.length === 0 ? (
              <p className="mt-3 text-sm text-ink-3">None yet. Run the demo profile to create the first one.</p>
            ) : (
              <ul className="mt-3 divide-y divide-border text-sm">
                {recent.map((r) => (
                  <li key={r.id} className="flex items-center justify-between gap-3 py-2">
                    <Link to={`/analysis/${r.id}`} className="truncate text-ink-2 hover:text-ink">
                      {r.category.replace(/_/g, " ")} · {r.business_type}
                    </Link>
                    <span className="flex shrink-0 items-center gap-2 text-xs text-ink-3">
                      <Badge variant={r.mode === "demo" ? "warning" : "good"}>{r.mode}</Badge>
                      {r.status} · {dateTime(r.created_at)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </section>
    </div>
  );
}
