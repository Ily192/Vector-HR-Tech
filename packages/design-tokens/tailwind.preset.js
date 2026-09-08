/**
 * Vortex Ops · Vector HR Tech — Tailwind preset
 *
 * Importar en cada app:
 *
 *   // tailwind.config.ts
 *   import vortexPreset from "@vortex/design-tokens/tailwind.preset";
 *   export default { presets: [vortexPreset], content: [...] };
 */

const tokens = require("./tokens.json");

const flatColor = (group) =>
  Object.fromEntries(
    Object.entries(group).map(([k, v]) =>
      typeof v.value === "string" ? [k, v.value] : [k, flatColor(v)],
    ),
  );

module.exports = {
  darkMode: ["class"],
  theme: {
    container: {
      center: true,
      padding: "1rem",
      screens: {
        sm: tokens.breakpoint.sm.value,
        md: tokens.breakpoint.md.value,
        lg: tokens.breakpoint.lg.value,
        xl: tokens.breakpoint.xl.value,
        "2xl": tokens.breakpoint["2xl"].value,
      },
    },
    extend: {
      colors: {
        vector: flatColor(tokens.color.vector),
        success: flatColor(tokens.color.semantic.success),
        warning: flatColor(tokens.color.semantic.warning),
        danger: flatColor(tokens.color.semantic.danger),
        info: flatColor(tokens.color.semantic.info),
        neutral: flatColor(tokens.color.neutral),

        // shadcn/ui semantic mapping (mode-aware vía CSS vars)
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
      },
      fontFamily: {
        display: tokens.font.family.display.value.split(",").map((s) => s.trim()),
        sans: tokens.font.family.body.value.split(",").map((s) => s.trim()),
        body: tokens.font.family.body.value.split(",").map((s) => s.trim()),
        mono: tokens.font.family.mono.value.split(",").map((s) => s.trim()),
      },
      fontSize: Object.fromEntries(Object.entries(tokens.font.size).map(([k, v]) => [k, v.value])),
      fontWeight: Object.fromEntries(
        Object.entries(tokens.font.weight).map(([k, v]) => [k, v.value]),
      ),
      lineHeight: Object.fromEntries(
        Object.entries(tokens.font.lineHeight).map(([k, v]) => [k, v.value]),
      ),
      letterSpacing: Object.fromEntries(
        Object.entries(tokens.font.tracking).map(([k, v]) => [k, v.value]),
      ),
      spacing: Object.fromEntries(Object.entries(tokens.space).map(([k, v]) => [k, v.value])),
      borderRadius: {
        ...Object.fromEntries(Object.entries(tokens.radius).map(([k, v]) => [k, v.value])),
        // shadcn/ui uses --radius
        DEFAULT: "var(--radius)",
      },
      boxShadow: Object.fromEntries(Object.entries(tokens.shadow).map(([k, v]) => [k, v.value])),
      transitionDuration: Object.fromEntries(
        Object.entries(tokens.motion.duration).map(([k, v]) => [k, v.value]),
      ),
      transitionTimingFunction: Object.fromEntries(
        Object.entries(tokens.motion.easing).map(([k, v]) => [k, v.value]),
      ),
      zIndex: Object.fromEntries(Object.entries(tokens.z).map(([k, v]) => [k, v.value])),
      keyframes: {
        "accordion-down": {
          from: { height: "0" },
          to: { height: "var(--radix-accordion-content-height)" },
        },
        "accordion-up": {
          from: { height: "var(--radix-accordion-content-height)" },
          to: { height: "0" },
        },
        "shimmer-cyan": {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
        "pulse-glow": {
          "0%, 100%": { boxShadow: "0 0 0 0 rgba(0, 255, 255, 0.4)" },
          "50%": { boxShadow: "0 0 24px 8px rgba(0, 255, 255, 0.15)" },
        },
      },
      animation: {
        "accordion-down": "accordion-down 200ms ease-out-quint",
        "accordion-up": "accordion-up 200ms ease-out-quint",
        "shimmer-cyan": "shimmer-cyan 2s linear infinite",
        "pulse-glow": "pulse-glow 2s ease-in-out infinite",
      },
    },
  },
  plugins: [
    require("tailwindcss-animate"),
    require("@tailwindcss/typography"),
    require("@tailwindcss/forms"),
  ],
};
