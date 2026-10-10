import { useMemo, useState } from "react";
import { ArrowUpDown, ExternalLink, Info } from "lucide-react";
import {
  CartesianGrid, Legend, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis,
} from "recharts";
import { EmptyState } from "@/components/Layout";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { basisLabel, dateTime, money, num } from "@/lib/format";
import type { Competitor, CompetitorsResponse, Listing } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Refs, SectionNote } from "./shared";

type SortDir = 1 | -1;

function useSort<T>(rows: T[], initial: keyof T) {
  const [key, setKey] = useState<keyof T>(initial);
  const [dir, setDir] = useState<SortDir>(1);
  const sorted = useMemo(() => [...rows].sort((a, b) => {
    const x = a[key] as unknown, y = b[key] as unknown;
    if (x == null && y == null) return 0;
    if (x == null) return 1;
    if (y == null) return -1;
    return (typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y))) * dir;
  }), [rows, key, dir]);
  const toggle = (k: keyof T) => { if (k === key) setDir((d) => (d === 1 ? -1 : 1)); else { setKey(k); setDir(1); } };
  return { sorted, toggle, key, dir };
}

function Th({ label, onClick, active, className }: { label: string; onClick?: () => void; active?: boolean; className?: string }) {
  return (
    <th scope="col" className={cn("px-3 py-2.5 text-left text-xs font-medium text-ink-3 whitespace-nowrap", className)}>
      {onClick ? (
        <button onClick={onClick} className={cn("inline-flex items-center gap-1 hover:text-ink cursor-pointer", active && "text-ink")}>
          {label}<ArrowUpDown className="h-3 w-3" />
        </button>
      ) : label}
    </th>
  );
}

const FLAG_LABEL: Record<string, { text: string; variant: "warning" | "critical" | "default" | "serious" }> = {
  currency_mismatch: { text: "Currency mismatch", variant: "critical" },
  missing_currency: { text: "No currency", variant: "critical" },
  missing_price: { text: "No price", variant: "critical" },
  unverified_size: { text: "Size unverified", variant: "warning" },
  ambiguous_size: { text: "Ambiguous size", variant: "warning" },
  promotion: { text: "Promotion", variant: "serious" },
  second_hand: { text: "Second-hand", variant: "default" },
};

export function CompetitorsTab({ data }: { data: CompetitorsResponse | null }) {
  const [country, setCountry] = useState<string>("all");
  const [focus, setFocus] = useState<string>("all");
  const [relation, setRelation] = useState<string>("all");
  const [unitView, setUnitView] = useState(true);

  if (!data) return <EmptyState title="Competitor data unavailable" message="The competitor endpoint did not return data for this analysis." />;
  const focusLabels = Object.fromEntries(data.price_groups.map((g) => [g.focus, g.focus_label]));
  const focuses = [...new Set([...data.listings.map((l) => l.focus), ...data.competitors.flatMap((c) => c.focuses)])];
  const inScope = (c: string[] | string, f: string[] | string) =>
    (country === "all" || (Array.isArray(c) ? c.includes(country) : c === country)) &&
    (focus === "all" || (Array.isArray(f) ? f.includes(focus) : f === focus));
  const listings = data.listings.filter((l) => inScope(l.country, l.focus));
  const competitors = data.competitors.filter((c) => inScope(c.countries, c.focuses) && (relation === "all" || c.relation === relation));
  const groups = data.price_groups.filter((g) => inScope(g.country, g.focus));

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Filters">
        <Select label="Country" value={country} onChange={setCountry} options={[["all", "All countries"], ...data.countries.map((c) => [c, c] as [string, string])]} />
        <Select label="Focus" value={focus} onChange={setFocus} options={[["all", "All focuses"], ...focuses.map((f) => [f, focusLabels[f] ?? f] as [string, string])]} />
        <Select label="Relation" value={relation} onChange={setRelation} options={[["all", "All relations"], ["direct", "Direct"], ["marketplace", "Marketplace"], ["reference", "Reference"]]} />
      </div>
      <SectionNote><Info className="mr-1 inline h-3 w-3" />{data.note} Prices are advertised prices at retrieval time.</SectionNote>

      <div className="grid gap-4 md:grid-cols-3">
        {groups.map((g) => (
          <Card key={`${g.focus}-${g.country}`} className="p-5">
            <div className="flex items-center justify-between">
              <h4 className="font-semibold">{g.focus_label}</h4>
              <Badge>{g.country}</Badge>
            </div>
            {g.median != null ? (
              <>
                <p className="mt-3 text-2xl font-semibold tabular">{money(g.median, g.currency ?? "INR")}<span className="ml-1 text-sm font-normal text-ink-3">median</span></p>
                <p className="text-sm text-ink-3 tabular">Range {money(g.min, g.currency ?? "INR")} – {money(g.max, g.currency ?? "INR")} · n={g.included_count} of {g.sample_size}</p>
                {g.unit_median != null && (
                  <p className="mt-1 text-sm tabular">Unit median {money(g.unit_median, g.currency ?? "INR", { decimals: 2 })} {basisLabel(g.unit_basis)}
                    <span className="text-ink-3"> (n={g.unit_sample_size})</span></p>
                )}
              </>
            ) : <p className="mt-3 text-sm text-ink-3">No verifiable prices.</p>}
            {g.warnings.length > 0 && (
              <ul className="mt-3 space-y-1 text-xs text-warning">
                {g.warnings.map((w) => <li key={w}>• {w}</li>)}
              </ul>
            )}
          </Card>
        ))}
      </div>

      <PriceStrip listings={listings} focusLabels={focusLabels} unitView={unitView} setUnitView={setUnitView} groups={groups} />
      <CompetitorTable competitors={competitors} focusLabels={focusLabels} />
      <ListingMatrix listings={listings} focusLabels={focusLabels} />
    </div>
  );
}

function Select({ label, value, onChange, options }: { label: string; value: string; onChange: (v: string) => void; options: [string, string][] }) {
  return (
    <label className="inline-flex items-center gap-2 rounded-lg border border-border bg-card px-2.5 py-1.5 text-xs text-ink-3">
      {label}
      <select aria-label={label} value={value} onChange={(e) => onChange(e.target.value)}
        className="bg-transparent text-sm text-ink focus:outline-none [&>option]:bg-card">
        {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select>
    </label>
  );
}

function PriceStrip({ listings, focusLabels, unitView, setUnitView, groups }: {
  listings: Listing[]; focusLabels: Record<string, string>; unitView: boolean; setUnitView: (v: boolean) => void;
  groups: CompetitorsResponse["price_groups"];
}) {
  const included = listings.filter((l) => l.included_in_stats && (unitView ? l.unit_price != null : l.price != null));
  // Only compare unit prices within the dominant basis for each focus (never g vs ml vs count)
  const basisByFocus = Object.fromEntries(groups.map((g) => [g.focus, g.unit_basis]));
  const points = included
    .filter((l) => !unitView || l.unit_price_basis === basisByFocus[l.focus])
    .map((l) => ({ x: unitView ? l.unit_price! : l.price!, y: focusLabels[l.focus] ?? l.focus, title: l.title, merchant: l.merchant, ref: l.evidence_ref }));
  const medians = groups.filter((g) => (unitView ? g.unit_median : g.median) != null)
    .map((g) => ({ x: unitView ? g.unit_median! : g.median!, y: g.focus_label, title: "Sampled median", merchant: null, ref: "" }));
  const bases = [...new Set(groups.map((g) => basisLabel(g.unit_basis)).filter(Boolean))];

  return (
    <Card>
      <CardHeader className="gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <CardTitle>Price distribution by focus</CardTitle>
          <CardDescription>
            Each dot is one sampled listing with a verified price and currency.
            {unitView ? ` Unit prices (${bases.join(", ")}) only include listings with unambiguous pack sizes.` : " Absolute prices are not normalised for pack size."}
          </CardDescription>
        </div>
        <div className="inline-flex rounded-lg border border-border p-1 text-xs" role="radiogroup" aria-label="Price view">
          {[[true, "Unit price"], [false, "Advertised price"]].map(([v, l]) => (
            <button key={String(v)} role="radio" aria-checked={unitView === v} onClick={() => setUnitView(v as boolean)}
              className={cn("rounded-md px-2.5 py-1 cursor-pointer", unitView === v ? "bg-card-raised text-ink" : "text-ink-3")}>{l as string}</button>
          ))}
        </div>
      </CardHeader>
      <CardContent>
        {points.length === 0 ? <p className="py-10 text-center text-sm text-ink-3">No comparable prices for this selection.</p> : (
          <div className="h-[260px]" role="img" aria-label="Strip chart of sampled listing prices by product focus">
            <ResponsiveContainer width="100%" height="100%">
              <ScatterChart margin={{ top: 10, right: 24, bottom: 10, left: 10 }}>
                <CartesianGrid stroke="var(--color-grid)" horizontal={false} />
                <XAxis type="number" dataKey="x" name="Price" tick={{ fill: "var(--color-ink-3)", fontSize: 11 }}
                  stroke="var(--color-axis)" tickFormatter={(v: number) => money(v, "INR", { compact: true })} />
                <YAxis type="category" dataKey="y" width={140} tick={{ fill: "var(--color-ink-2)", fontSize: 12 }}
                  stroke="var(--color-axis)" allowDuplicatedCategory={false} />
                <ZAxis range={[70, 70]} />
                <Tooltip cursor={{ stroke: "var(--color-border-strong)" }} content={({ active, payload }) => {
                  const p = payload?.[0]?.payload as { x: number; title: string; merchant: string | null; ref: string } | undefined;
                  if (!active || !p) return null;
                  return (
                    <div className="max-w-xs rounded-lg border border-border-strong bg-card-raised px-3 py-2 text-xs shadow-xl">
                      <p className="font-medium text-ink">{p.title}</p>
                      {p.merchant && <p className="text-ink-3">{p.merchant} · {p.ref}</p>}
                      <p className="mt-1 tabular text-ink">{money(p.x, "INR", { decimals: unitView ? 2 : 0 })} {unitView ? "per normalised unit" : ""}</p>
                    </div>
                  );
                }} />
                <Legend wrapperStyle={{ fontSize: 12, color: "var(--color-ink-2)" }} />
                <Scatter name="Sampled listing" data={points} fill="var(--color-series-1)" fillOpacity={0.75} isAnimationActive={false}
                  stroke="var(--color-card)" strokeWidth={2} />
                <Scatter name="Sampled median" data={medians} fill="var(--color-ink)" shape="diamond" isAnimationActive={false} />
              </ScatterChart>
            </ResponsiveContainer>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function CompetitorTable({ competitors, focusLabels }: { competitors: Competitor[]; focusLabels: Record<string, string> }) {
  const rows = competitors.map((c) => ({ ...c, evidenceCount: c.evidence_refs.length }));
  const { sorted, toggle, key } = useSort(rows, "relation");
  return (
    <Card>
      <CardHeader>
        <CardTitle>Competitor directory ({competitors.length})</CardTitle>
        <CardDescription>Deduplicated across Shopping, web search, marketplaces and Maps. Tags are labelled as observed or interpretation.</CardDescription>
      </CardHeader>
      <CardContent className="overflow-x-auto">
        <table className="w-full min-w-[860px] text-sm">
          <thead className="border-b border-border">
            <tr>
              <Th label="Brand / merchant" onClick={() => toggle("name")} active={key === "name"} />
              <Th label="Relation" onClick={() => toggle("relation")} active={key === "relation"} />
              <Th label="Focus" />
              <Th label="Sampled prices" onClick={() => toggle("price_min")} active={key === "price_min"} />
              <Th label="Rating" onClick={() => toggle("rating")} active={key === "rating"} />
              <Th label="Positioning tags" />
              <Th label="Evidence" onClick={() => toggle("evidenceCount")} active={key === "evidenceCount"} />
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {sorted.map((c) => (
              <tr key={c.key} className="align-top hover:bg-white/[0.02]">
                <td className="px-3 py-3">
                  <p className="font-medium">{c.name}</p>
                  {c.websites[0] && (
                    <a href={c.websites[0]} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1 text-xs text-accent hover:underline">
                      {new URL(c.websites[0]).hostname}<ExternalLink className="h-3 w-3" />
                    </a>
                  )}
                  {c.address && <p className="text-xs text-ink-3">{c.address}</p>}
                </td>
                <td className="px-3 py-3">
                  <Badge variant={c.relation === "direct" ? "accent" : c.relation === "marketplace" ? "default" : "outline"} title={c.relation_reason}>{c.relation}</Badge>
                  <p className="mt-1 max-w-[220px] text-xs text-ink-3">{c.relation_reason}</p>
                </td>
                <td className="px-3 py-3 text-xs text-ink-2">{c.focuses.map((f) => focusLabels[f] ?? f).join(", ") || "—"}</td>
                <td className="px-3 py-3 tabular text-ink-2">
                  {c.price_min != null ? `${money(c.price_min, c.currency ?? "INR")}${c.price_max !== c.price_min ? ` – ${money(c.price_max, c.currency ?? "INR")}` : ""}` : <span className="text-ink-3">Not observed</span>}
                </td>
                <td className="px-3 py-3 tabular text-ink-2">{c.rating != null ? `${c.rating} (${num(c.reviews)})` : <span className="text-ink-3">—</span>}</td>
                <td className="px-3 py-3">
                  <div className="flex max-w-[240px] flex-wrap gap-1">
                    {c.tags.map((t) => (
                      <Badge key={t.tag} variant={t.basis === "observed" ? "default" : "outline"} title={`${t.basis}: ${t.detail}`}>
                        {t.tag.replace(/_/g, " ")}{t.basis === "interpretation" ? "*" : ""}
                      </Badge>
                    ))}
                  </div>
                </td>
                <td className="px-3 py-3"><Refs refs={c.evidence_refs} max={3} /></td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-3 text-xs text-ink-3">* interpretation – not verified on the destination website.</p>
      </CardContent>
    </Card>
  );
}

function ListingMatrix({ listings, focusLabels }: { listings: Listing[]; focusLabels: Record<string, string> }) {
  const [q, setQ] = useState("");
  const rows = listings
    .filter((l) => !q || `${l.title} ${l.merchant}`.toLowerCase().includes(q.toLowerCase()))
    .map((l) => ({ ...l, qty: l.quantity.amount }));
  const { sorted, toggle, key } = useSort(rows, "unit_price");
  return (
    <Card>
      <CardHeader className="gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <CardTitle>Competitor intelligence matrix ({listings.length} listings)</CardTitle>
          <CardDescription>Every sampled listing with its source, timestamp and data-quality flags.</CardDescription>
        </div>
        <input aria-label="Search listings" placeholder="Search product or seller…" value={q} onChange={(e) => setQ(e.target.value)}
          className="h-9 w-full rounded-lg border border-border-strong bg-page px-3 text-sm sm:w-64 focus:border-accent focus:outline-none" />
      </CardHeader>
      <CardContent className="overflow-x-auto">
        <table className="w-full min-w-[1100px] text-sm" data-testid="listing-matrix">
          <thead className="border-b border-border">
            <tr>
              <Th label="Brand / product" onClick={() => toggle("title")} active={key === "title"} />
              <Th label="Seller" onClick={() => toggle("merchant")} active={key === "merchant"} />
              <Th label="Country" />
              <Th label="Price" onClick={() => toggle("price")} active={key === "price"} />
              <Th label="Currency" />
              <Th label="Qty" onClick={() => toggle("qty")} active={key === "qty"} />
              <Th label="Unit price" onClick={() => toggle("unit_price")} active={key === "unit_price"} />
              <Th label="Rating" onClick={() => toggle("rating")} active={key === "rating"} />
              <Th label="Source" />
              <Th label="Retrieved" />
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {sorted.map((l) => (
              <tr key={l.evidence_ref} className={cn("align-top hover:bg-white/[0.02]", !l.included_in_stats && "opacity-70")}>
                <td className="max-w-[300px] px-3 py-2.5">
                  <p className="text-ink">{l.title}</p>
                  <p className="text-xs text-ink-3">{focusLabels[l.focus] ?? l.focus} · {l.engine}</p>
                  {l.flags.length > 0 && (
                    <div className="mt-1 flex flex-wrap gap-1">
                      {l.flags.map((f) => <Badge key={f} variant={FLAG_LABEL[f]?.variant ?? "default"}>{FLAG_LABEL[f]?.text ?? f}</Badge>)}
                    </div>
                  )}
                </td>
                <td className="px-3 py-2.5 text-ink-2">{l.merchant ?? <span className="text-ink-3">Unknown</span>}{l.is_marketplace && <Badge className="ml-1">marketplace</Badge>}</td>
                <td className="px-3 py-2.5 text-ink-2">{l.country}</td>
                <td className="px-3 py-2.5 tabular">{l.price_text ?? "—"}</td>
                <td className="px-3 py-2.5 text-xs">{l.currency ?? <span className="text-[#f08a8a]">missing</span>}</td>
                <td className="px-3 py-2.5 text-xs text-ink-2">{l.quantity.status === "parsed" ? `${num(l.quantity.amount)} ${l.quantity.base_unit === "count" ? "units" : l.quantity.base_unit}` : <span className="text-warning">{l.quantity.status}</span>}</td>
                <td className="px-3 py-2.5 tabular">{l.unit_price != null ? <>{money(l.unit_price, l.currency ?? "INR", { decimals: 2 })} <span className="text-xs text-ink-3">{basisLabel(l.unit_price_basis)}</span></> : <span className="text-ink-3">not computable</span>}</td>
                <td className="px-3 py-2.5 tabular text-ink-2">{l.rating != null ? `${l.rating} (${num(l.reviews)})` : "—"}</td>
                <td className="px-3 py-2.5"><Refs refs={[l.evidence_ref]} /></td>
                <td className="px-3 py-2.5 text-xs text-ink-3 whitespace-nowrap">{dateTime(l.retrieved_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}
