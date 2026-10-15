import { type VariantProps, cva } from "class-variance-authority";
import type * as React from "react";
import { cn } from "./utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-bold transition-colors",
  {
    variants: {
      variant: {
        default: "bg-ink-900 text-white dark:bg-ink-50 dark:text-ink-900",
        // IA / estado vivo: aqua tranquilo, sin el brillo neón de la v1.
        ai: "bg-aqua-50 text-aqua-700 ring-1 ring-inset ring-aqua-200 dark:bg-aqua-300/15 dark:text-aqua-300 dark:ring-aqua-300/30",
        // Aviso de marca (p. ej. "datos ficticios"): flame suave.
        brand: "bg-flame-50 text-flame-700 ring-1 ring-inset ring-flame-100",
        manual: "bg-mist-100 text-mist-700 dark:bg-white/10 dark:text-mist-200",
        success: "bg-success-50 text-success-700 dark:bg-success-700/20 dark:text-success-50",
        warning: "bg-warning-50 text-warning-700 dark:bg-warning-700/20 dark:text-warning-50",
        danger: "bg-danger-50 text-danger-700 dark:bg-danger-700/20 dark:text-danger-50",
        outline: "border border-border bg-card text-foreground",
      },
    },
    defaultVariants: { variant: "default" },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };
