import * as React from "react";
import { cn } from "@/lib/utils";

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      className={cn(
        "h-10 w-full rounded-lg border border-border-strong bg-page px-3 text-sm text-ink placeholder:text-ink-3",
        "focus:border-accent focus:outline-none aria-[invalid=true]:border-critical",
        className,
      )}
      {...props}
    />
  ),
);
Input.displayName = "Input";
