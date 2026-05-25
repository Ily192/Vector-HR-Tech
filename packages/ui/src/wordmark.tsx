import * as React from "react";
import { cn } from "./utils";

interface WordmarkProps extends React.HTMLAttributes<HTMLDivElement> {
  brand?: "vector" | "vortex";
  size?: "sm" | "md" | "lg" | "xl";
}

/**
 * Wordmark Vector HR Tech / Vortex Ops
 *   "VECTOR" en Proxima Nova Black + "HR TECH" en Lato Bold Italic naranja
 *   "VORTEX"  en Proxima Nova Black + "OPS" en Lato Bold Italic cian electric
 */
export function Wordmark({
  brand = "vortex",
  size = "md",
  className,
  ...props
}: WordmarkProps) {
  const sizes = {
    sm: "text-lg",
    md: "text-2xl",
    lg: "text-4xl",
    xl: "text-6xl",
  } as const;

  const isVector = brand === "vector";
  const accentColor = isVector ? "text-vector-orange-500" : "text-vector-cian-electric-500";
  const primary = isVector ? "VECTOR" : "VORTEX";
  const secondary = isVector ? "HR TECH" : "OPS";

  return (
    <div
      className={cn(
        "inline-flex items-baseline gap-1.5 font-display font-black tracking-tighter",
        sizes[size],
        className,
      )}
      aria-label={`${primary} ${secondary}`}
      {...props}
    >
      <span>{primary}</span>
      <span className={cn("font-body italic font-bold tracking-tight", accentColor)}>
        {secondary}
      </span>
    </div>
  );
}
