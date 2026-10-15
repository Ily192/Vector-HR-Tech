import type * as React from "react";
import { cn } from "./utils";

interface WordmarkProps extends React.HTMLAttributes<HTMLDivElement> {
  brand?: "vector" | "vortex";
  size?: "sm" | "md" | "lg" | "xl";
  /** Fondo sobre el que va: el acento cambia de tono para mantener el contraste. */
  tone?: "light" | "dark";
  /** Antepone el monograma (la V en aqua sobre tinta). */
  withMark?: boolean;
}

/**
 * Wordmark de la marca v2 (docs/brand/branding-v2.md)
 *   "VORTEX" en Figtree 900 + "OPS" en Figtree 800 cursiva aqua
 *   "VECTOR" en Figtree 900 + "HR TECH" en Figtree 800 cursiva flame
 * Sobre tinta el acento va en aqua-300 / flame-500; sobre claro, en aqua-600 / flame-700.
 */
export function Wordmark({
  brand = "vortex",
  size = "md",
  tone,
  withMark = false,
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
  const accent = isVector
    ? tone === "dark"
      ? "text-flame-500"
      : tone === "light"
        ? "text-flame-700"
        : "text-flame-700 dark:text-flame-500"
    : tone === "dark"
      ? "text-aqua-300"
      : tone === "light"
        ? "text-aqua-600"
        : "text-aqua-600 dark:text-aqua-300";
  const primary = isVector ? "VECTOR" : "VORTEX";
  const secondary = isVector ? "HR TECH" : "OPS";

  return (
    <div
      className={cn(
        "inline-flex items-baseline gap-1 font-display font-black leading-none tracking-tighter",
        sizes[size],
        className,
      )}
      aria-label={`${primary} ${secondary}`}
      {...props}
    >
      {withMark ? (
        <svg
          aria-hidden="true"
          viewBox="0 0 30 30"
          className={cn(
            "mr-1.5 h-[1.5em] w-[1.5em] shrink-0 self-center rounded-[0.3em] bg-ink-900",
            tone === "dark" && "ring-1 ring-white/20",
          )}
        >
          <path
            d="M9 9l6 12 6-12"
            fill="none"
            stroke="#3EECEB"
            strokeWidth="3.4"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      ) : null}
      <span>{primary}</span>
      <span className={cn("italic font-extrabold tracking-tight", accent)}>{secondary}</span>
    </div>
  );
}
