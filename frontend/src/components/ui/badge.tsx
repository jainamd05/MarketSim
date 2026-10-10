import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[11px] font-medium leading-4 whitespace-nowrap [&_svg]:size-3",
  {
    variants: {
      variant: {
        default: "border-border bg-white/[0.04] text-ink-2",
        accent: "border-accent/30 bg-accent-soft text-[#9cc3f3]",
        good: "border-good/30 bg-good/10 text-[#5fd35f]",
        warning: "border-warning/30 bg-warning/10 text-warning",
        serious: "border-serious/30 bg-serious/10 text-serious",
        critical: "border-critical/40 bg-critical/10 text-[#f08a8a]",
        outline: "border-border-strong text-ink-2",
      },
    },
    defaultVariants: { variant: "default" },
  },
);

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement>, VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}
