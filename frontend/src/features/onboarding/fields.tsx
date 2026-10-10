import { Check } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import type { Option } from "@/lib/types";

export function FieldError({ message, id }: { message?: string; id?: string }) {
  if (!message) return null;
  return (
    <p id={id} role="alert" className="mt-2 text-sm text-[#f08a8a]">
      {message}
    </p>
  );
}

interface OptionGridProps {
  name: string;
  label: string;
  options: (Option & { disabled?: boolean })[];
  value: string;
  onChange: (value: string) => void;
  columns?: 1 | 2 | 3;
  error?: string;
}

/** Single-select card grid with radio semantics (keyboard + screen-reader friendly). */
export function OptionGrid({ name, label, options, value, onChange, columns = 2, error }: OptionGridProps) {
  return (
    <fieldset>
      <legend className="sr-only">{label}</legend>
      <div role="radiogroup" aria-label={label} aria-invalid={!!error}
        className={cn("grid gap-3", columns === 1 ? "grid-cols-1" : columns === 2 ? "sm:grid-cols-2" : "sm:grid-cols-2 lg:grid-cols-3")}>
        {options.map((o) => {
          const selected = value === o.value;
          return (
            <button
              key={o.value}
              type="button"
              role="radio"
              aria-checked={selected}
              name={name}
              disabled={o.disabled}
              onClick={() => onChange(o.value)}
              className={cn(
                "group relative flex min-h-16 flex-col items-start gap-1 rounded-xl border bg-card p-4 text-left transition-all cursor-pointer",
                "hover:border-border-strong hover:bg-card-raised disabled:cursor-not-allowed disabled:opacity-45",
                selected ? "border-accent bg-accent-soft ring-1 ring-accent/40" : "border-border",
              )}
            >
              <span className="flex w-full items-center justify-between gap-2 font-medium text-ink">
                {o.label}
                <span className={cn("flex h-5 w-5 shrink-0 items-center justify-center rounded-full border",
                  selected ? "border-accent bg-accent text-white" : "border-border-strong")}>
                  {selected && <Check className="h-3 w-3" strokeWidth={3} />}
                </span>
              </span>
              {o.description && <span className="text-sm text-ink-3">{o.description}</span>}
            </button>
          );
        })}
      </div>
      <FieldError message={error} />
    </fieldset>
  );
}

interface MultiProps {
  label: string;
  options: Option[];
  values: string[];
  max: number;
  onChange: (values: string[]) => void;
  error?: string;
}

export function MultiOptionGrid({ label, options, values, max, onChange, error }: MultiProps) {
  const toggle = (v: string) => {
    if (values.includes(v)) onChange(values.filter((x) => x !== v));
    else if (values.length < max) onChange([...values, v]);
  };
  return (
    <fieldset>
      <legend className="mb-3 text-sm font-medium text-ink-2">
        {label} <span className="text-ink-3">({values.length}/{max} selected)</span>
      </legend>
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {options.map((o) => {
          const checked = values.includes(o.value);
          const blocked = !checked && values.length >= max;
          return (
            <button
              key={o.value}
              type="button"
              role="checkbox"
              aria-checked={checked}
              disabled={blocked}
              onClick={() => toggle(o.value)}
              className={cn(
                "flex items-center gap-3 rounded-lg border px-3 py-2.5 text-left text-sm transition-colors cursor-pointer disabled:cursor-not-allowed disabled:opacity-40",
                checked ? "border-accent bg-accent-soft text-ink" : "border-border bg-card text-ink-2 hover:border-border-strong",
              )}
            >
              <span className={cn("flex h-4 w-4 shrink-0 items-center justify-center rounded border",
                checked ? "border-accent bg-accent text-white" : "border-border-strong")}>
                {checked && <Check className="h-3 w-3" strokeWidth={3} />}
              </span>
              {o.label}
            </button>
          );
        })}
      </div>
      <FieldError message={error} />
    </fieldset>
  );
}

interface NumberFieldProps {
  id: string;
  label: string;
  unit: string;
  value: number | null;
  onChange: (v: number | null) => void;
  error?: string;
  hint?: string;
}

/** Numeric input where an empty box means UNKNOWN (null), never zero. */
export function NumberField({ id, label, unit, value, onChange, error, hint }: NumberFieldProps) {
  return (
    <div>
      <div className="flex items-baseline justify-between gap-2">
        <Label htmlFor={id}>{label}</Label>
        <span className="text-xs text-ink-3">{unit}</span>
      </div>
      <Input
        id={id}
        type="number"
        inputMode="decimal"
        min={0}
        step="any"
        placeholder="Unknown – leave blank"
        className="mt-1.5 tabular"
        value={value ?? ""}
        aria-invalid={!!error}
        aria-describedby={error ? `${id}-error` : undefined}
        onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))}
      />
      {hint && !error && <p className="mt-1 text-xs text-ink-3">{hint}</p>}
      <FieldError id={`${id}-error`} message={error} />
    </div>
  );
}

export function TextField({ id, label, value, onChange, error, placeholder, maxLength = 120 }: {
  id: string; label: string; value: string; onChange: (v: string) => void; error?: string; placeholder?: string; maxLength?: number;
}) {
  return (
    <div>
      <Label htmlFor={id}>{label}</Label>
      <Input id={id} className="mt-1.5" value={value} maxLength={maxLength} placeholder={placeholder}
        aria-invalid={!!error} onChange={(e) => onChange(e.target.value)} />
      <FieldError message={error} />
    </div>
  );
}
