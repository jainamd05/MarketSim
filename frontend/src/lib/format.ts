const SYMBOLS: Record<string, string> = { INR: "₹", USD: "$", GBP: "£", AED: "AED " };

export function money(value: number | null | undefined, currency = "INR", opts: { compact?: boolean; decimals?: number } = {}): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "Unknown";
  const sym = SYMBOLS[currency] ?? `${currency} `;
  const sign = value < 0 ? "−" : "";
  const abs = Math.abs(value);
  if (opts.compact && currency === "INR" && abs >= 100_000) {
    return `${sign}${sym}${(abs / 100_000).toFixed(abs >= 1_000_000 ? 1 : 2)}L`;
  }
  if (opts.compact && abs >= 10_000) {
    return `${sign}${sym}${new Intl.NumberFormat("en-IN", { notation: "compact", maximumFractionDigits: 1 }).format(abs)}`;
  }
  const locale = currency === "INR" ? "en-IN" : "en-US";
  return `${sign}${sym}${new Intl.NumberFormat(locale, { maximumFractionDigits: opts.decimals ?? 0 }).format(abs)}`;
}

export function num(value: number | null | undefined, decimals = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat("en-IN", { maximumFractionDigits: decimals }).format(value);
}

export function pct(value: number | null | undefined, decimals = 0): string {
  if (value === null || value === undefined) return "—";
  return `${(value * 100).toFixed(decimals)}%`;
}

export function signedPct(value: number | null | undefined): string {
  if (value === null || value === undefined) return "n/a";
  return `${value > 0 ? "+" : ""}${value.toFixed(0)}%`;
}

export function dateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString(undefined, { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function dateOnly(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

export function humanize(s: string): string {
  return s.replace(/_/g, " ").replace(/\b\w/, (c) => c.toUpperCase());
}

export function basisLabel(basis: string | null | undefined): string {
  return { per_100g: "per 100 g", per_100ml: "per 100 ml", per_unit: "per unit" }[basis ?? ""] ?? "";
}
