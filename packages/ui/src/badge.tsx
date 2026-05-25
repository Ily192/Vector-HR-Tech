import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";
import { cn } from "./utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold transition-colors",
  {
    variants: {
      variant: {
        default:
          "bg-vector-cian-dark-500 text-white",
        ai:
          "bg-vector-cian-electric-500 text-vector-cian-dark-500 shadow-[0_0_8px_rgba(0,255,255,0.4)]",
        manual:
          "bg-neutral-100 text-neutral-700 dark:bg-neutral-800 dark:text-neutral-200",
        success:
          "bg-success-50 text-success-700 dark:bg-success-700/20 dark:text-success-50",
        warning:
          "bg-warning-50 text-warning-700 dark:bg-warning-700/20 dark:text-warning-50",
        danger:
          "bg-danger-50 text-danger-700 dark:bg-danger-700/20 dark:text-danger-50",
        outline: "border border-border text-foreground",
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
