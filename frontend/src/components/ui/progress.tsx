import * as React from "react";
import * as ProgressPrimitive from "@radix-ui/react-progress";
import { cn } from "@/lib/utils";

export function Progress({ className, value, ...props }: React.ComponentPropsWithoutRef<typeof ProgressPrimitive.Root>) {
  return (
    <ProgressPrimitive.Root
      className={cn("relative h-1.5 w-full overflow-hidden rounded-full bg-white/10", className)}
      value={value}
      {...props}
    >
      <ProgressPrimitive.Indicator
        className="h-full bg-accent transition-transform duration-500"
        style={{ transform: `translateX(-${100 - (value ?? 0)}%)` }}
      />
    </ProgressPrimitive.Root>
  );
}
