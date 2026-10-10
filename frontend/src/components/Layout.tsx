import { Link, NavLink, Outlet } from "react-router-dom";
import { FlaskConical, Radio, ServerCrash } from "lucide-react";
import { useApp } from "./AppContext";
import { cn } from "@/lib/utils";

export function Logo({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <svg viewBox="0 0 32 32" className="h-8 w-8" aria-hidden>
        <rect width="32" height="32" rx="8" fill="#1e1e22" stroke="rgba(255,255,255,0.12)" />
        <path d="M7 22l5-6 4 3 4-7 5 4" fill="none" stroke="#3987e5" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
        <circle cx="25" cy="16" r="2.2" fill="#d95926" />
      </svg>
      <span className="text-[17px] font-semibold tracking-tight">
        MarketSim <span className="text-ink-3 font-medium">AI</span>
      </span>
    </span>
  );
}

export function DataModeBanner() {
  const { config, configError, viewMode } = useApp();
  if (configError) {
    return (
      <div role="alert" className="flex items-center justify-center gap-2 border-b border-critical/30 bg-critical/10 px-4 py-2 text-xs text-[#f08a8a]">
        <ServerCrash className="h-3.5 w-3.5" /> Backend unreachable: {configError}
      </div>
    );
  }
  const mode = viewMode ?? config?.default_data_mode;
  if (!mode) return null;
  if (mode === "demo") {
    return (
      <div data-testid="demo-banner" className="flex flex-wrap items-center justify-center gap-x-2 gap-y-0.5 border-b border-warning/25 bg-warning/[0.08] px-4 py-2 text-center text-xs text-warning">
        <FlaskConical className="h-3.5 w-3.5" />
        <strong className="font-semibold tracking-wide">DEMO DATA</strong>
        <span className="text-warning/85">
          {config?.fixtures_synthetic === false
            ? "Replaying previously recorded SerpApi responses — not real-time market intelligence."
            : "Saved synthetic SerpApi-format fixtures with fictional brands — not real-time market intelligence."}
        </span>
      </div>
    );
  }
  return (
    <div data-testid="live-banner" className="flex items-center justify-center gap-2 border-b border-good/25 bg-good/[0.07] px-4 py-2 text-xs text-[#5fd35f]">
      <Radio className="h-3.5 w-3.5" />
      <strong className="font-semibold tracking-wide">LIVE</strong>
      <span className="opacity-85">Genuine SerpApi requests; every observation carries its source and retrieval time.</span>
    </div>
  );
}

export function Layout() {
  const { config } = useApp();
  return (
    <div className="flex min-h-screen flex-col">
      <DataModeBanner />
      <header className="sticky top-0 z-30 border-b border-border bg-page/85 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-7xl items-center justify-between gap-4 px-4 sm:px-6">
          <Link to="/" aria-label="MarketSim home"><Logo /></Link>
          <nav className="flex items-center gap-1 text-sm">
            <NavLink to="/onboarding" className={({ isActive }) => cn("rounded-lg px-3 py-1.5 text-ink-2 hover:text-ink", isActive && "text-ink bg-white/[0.06]")}>
              New analysis
            </NavLink>
            {config && (
              <span className="hidden items-center gap-1.5 rounded-lg border border-border px-2.5 py-1 text-xs text-ink-3 md:inline-flex">
                <span className={cn("h-1.5 w-1.5 rounded-full", config.serpapi_configured ? "bg-good" : "bg-warning")} />
                SerpApi {config.serpapi_configured ? "key configured" : "not configured"} · LLM {config.llm_enabled ? config.llm_model : "off (deterministic)"}
              </span>
            )}
          </nav>
        </div>
      </header>
      <main className="flex-1">
        <Outlet />
      </main>
      <footer className="border-t border-border py-6 text-center text-xs text-ink-3">
        MarketSim AI provides decision support, not financial, legal or tax advice. Modelled results are scenarios, not forecasts.
      </footer>
    </div>
  );
}

export function PageShell({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn("mx-auto w-full max-w-7xl px-4 py-8 sm:px-6", className)}>{children}</div>;
}

export function ErrorState({ title = "Something went wrong", message, action }: { title?: string; message: string; action?: React.ReactNode }) {
  return (
    <div role="alert" className="rounded-xl border border-critical/30 bg-critical/[0.06] p-6">
      <h3 className="font-semibold text-[#f08a8a]">{title}</h3>
      <p className="mt-1 text-sm text-ink-2">{message}</p>
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function EmptyState({ title, message, icon }: { title: string; message: string; icon?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border-strong p-10 text-center">
      {icon && <div className="mb-3 text-ink-3">{icon}</div>}
      <h3 className="font-medium text-ink-2">{title}</h3>
      <p className="mt-1 max-w-md text-sm text-ink-3">{message}</p>
    </div>
  );
}

export function LoadingBlock({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex flex-col gap-3" aria-busy="true" aria-label={label}>
      {[0, 1, 2].map((i) => (
        <div key={i} className="h-24 animate-pulse rounded-xl border border-border bg-card" style={{ animationDelay: `${i * 120}ms` }} />
      ))}
    </div>
  );
}
