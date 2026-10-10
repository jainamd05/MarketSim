import { useState } from "react";
import { ArrowDownRight, ArrowRight, ArrowUpRight, Info, Minus } from "lucide-react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { EmptyState } from "@/components/Layout";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { dateTime, signedPct } from "@/lib/format";
import type { TrendsResponse } from "@/lib/types";
import { ChartTooltip, Refs, SERIES, SectionNote } from "./shared";

const DIRECTION = {
  rising: { icon: ArrowUpRight, variant: "good" as const },
  declining: { icon: ArrowDownRight, variant: "critical" as const },
  flat: { icon: Minus, variant: "default" as const },
  insufficient_data: { icon: ArrowRight, variant: "outline" as const },
};

export function TrendsTab({ data }: { data: TrendsResponse | null }) {
  const countries = data?.countries ?? [];
  const [country, setCountry] = useState(countries[0] ?? "");
  const t = data?.by_country[country];
  if (!data || !t) return <EmptyState title="No trend data" message="Google Trends was not requested or returned no data for this analysis." />;
  if (t.status === "unavailable") {
    return <EmptyState title="Google Trends unavailable" message={t.note ?? "No demand signal is inferred when Trends data is missing."} />;
  }
  const rows: Record<string, unknown>[] = t.points.map((p) => ({ ...p, date: String(p.date).replace(/,\s*\d{4}$/, "") }));
  const lastIdx = t.queries.map((q) => rows.length - 1 - [...rows].reverse().findIndex((r) => r[q] != null));

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        {countries.length > 1 && (
          <div className="inline-flex rounded-lg border border-border p-1 text-sm" role="radiogroup" aria-label="Country">
            {countries.map((c) => (
              <button key={c} role="radio" aria-checked={c === country} onClick={() => setCountry(c)}
                className={c === country ? "rounded-md bg-card-raised px-3 py-1 text-ink" : "px-3 py-1 text-ink-3 cursor-pointer"}>{c}</button>
            ))}
          </div>
        )}
        <Badge>{t.geo} · {t.date_range}</Badge>
        <Badge variant={t.data_origin === "demo_fixture" ? "warning" : "good"}>{t.data_origin === "demo_fixture" ? "Demo fixture" : "Live"} · retrieved {dateTime(t.retrieved_at)}</Badge>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Relative search interest over time</CardTitle>
          <CardDescription>{t.normalization_note}</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="h-[320px]" role="img" aria-label={`Google Trends relative interest for ${t.queries.join(", ")}`}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={rows} margin={{ top: 10, right: 110, bottom: 0, left: -10 }}>
                <CartesianGrid stroke="var(--color-grid)" vertical={false} />
                <XAxis dataKey="date" tick={{ fill: "var(--color-ink-3)", fontSize: 11 }} stroke="var(--color-axis)" interval={7} />
                <YAxis domain={[0, 100]} tick={{ fill: "var(--color-ink-3)", fontSize: 11 }} stroke="var(--color-axis)" />
                <Tooltip content={<ChartTooltip format={(v) => `${v}/100`} />} cursor={{ stroke: "var(--color-border-strong)" }} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                {t.queries.map((q, i) => (
                  <Line key={q} dataKey={q} name={q} stroke={SERIES[i % SERIES.length]} strokeWidth={2} dot={false}
                    activeDot={{ r: 5, stroke: "var(--color-card)", strokeWidth: 2 }} connectNulls={false} isAnimationActive={false}
                    label={(props: { index?: number; x?: number; y?: number }) => props.index === lastIdx[i]
                      ? <text x={(props.x ?? 0) + 8} y={(props.y ?? 0) + 4} fill="var(--color-ink-2)" fontSize={11}>{q}</text>
                      : <g />} />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
          <p className="mt-2 text-xs text-ink-3">The final week may be a partial period and is excluded from change calculations.</p>
        </CardContent>
      </Card>

      <SectionNote><Info className="mr-1 inline h-3 w-3" />{t.demand_caveat}</SectionNote>

      <div className="grid gap-4 md:grid-cols-3">
        {t.summaries.map((s, i) => {
          const dir = DIRECTION[s.direction];
          return (
            <Card key={s.query} className="p-5">
              <div className="flex items-center justify-between gap-2">
                <span className="flex items-center gap-2 font-semibold">
                  <span className="h-2.5 w-2.5 rounded-full" style={{ background: SERIES[i % SERIES.length] }} />{s.query}
                </span>
                <Badge variant={dir.variant}><dir.icon /> {s.direction.replace("_", " ")}</Badge>
              </div>
              <p className="mt-3 text-2xl font-semibold tabular">{signedPct(s.change_pct)}</p>
              <p className="text-xs text-ink-3">last vs first quarter of the period · mean {s.mean ?? "—"}/100</p>
              <p className="mt-3 text-sm text-ink-2">{s.description}</p>
            </Card>
          );
        })}
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Related queries {t.related_queries?.query ? `for “${t.related_queries.query}”` : ""}</CardTitle>
            <CardDescription>Top = most associated; rising = fastest growing. Relative values only.</CardDescription>
          </CardHeader>
          <CardContent>
            {!t.related_queries ? <p className="text-sm text-ink-3">Not retrieved in this analysis.</p> : (
              <div className="grid gap-4 sm:grid-cols-2">
                {(["top", "rising"] as const).map((b) => (
                  <div key={b}>
                    <p className="mb-2 text-xs font-medium uppercase tracking-wide text-ink-3">{b}</p>
                    <ul className="space-y-1.5 text-sm">
                      {t.related_queries![b].map((r) => (
                        <li key={r.query} className="flex justify-between gap-2"><span>{r.query}</span><span className="tabular text-ink-3">{r.value_text}</span></li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Search terms & sources</CardTitle>
            <CardDescription>Terms compared in one request so their indices share a scale.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <div className="flex flex-wrap gap-2">{t.queries.map((q) => <code key={q} className="rounded border border-border bg-page px-2 py-0.5 text-xs">{q}</code>)}</div>
            {t.keyword_suggestions.length > 0 && <p className="text-ink-2">Autocomplete: {t.keyword_suggestions.join(", ")}</p>}
            {t.regional_interest.length > 0 && <p className="text-ink-2">Top regions: {t.regional_interest.slice(0, 5).map((r) => `${r.location} (${r.value})`).join(", ")}</p>}
            <Refs refs={t.evidence_refs} max={8} />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
