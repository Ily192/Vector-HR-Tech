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
    Object.entries(group)
      .filter(([k]) => !k.startsWith("$"))
      .map(([k, v]) => (typeof v.value === "string" ? [k, v.value] : [k, flatColor(v)])),
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
        // Marca v2 (docs/brand/branding-v2.md)
        ink: flatColor(tokens.color.ink),
        aqua: flatColor(tokens.color.aqua),
        flame: flatColor(tokens.color.flame),
        mist: flatColor(tokens.color.mist),
        risk: flatColor(tokens.color.risk),
        // Marca v1, en desuso
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
      // Marca v2: Figtree y JetBrains Mono vía variables CSS (next/font las sobrescribe
      // con su familia autoalojada; theme.css da el valor por defecto).
      fontFamily: {
        display: ["var(--font-sans)", "system-ui", "sans-serif"],
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        body: ["var(--font-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
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
      boxShadow: {
        ...Object.fromEntries(Object.entries(tokens.shadow).map(([k, v]) => [k, v.value])),
        // Sombras de la marca v2: suaves y teñidas de tinta.
        soft: "0 1px 2px rgb(24 24 84 / 0.06), 0 1px 1px rgb(24 24 84 / 0.04)",
        lift: "0 10px 30px -12px rgb(24 24 84 / 0.18), 0 2px 6px rgb(24 24 84 / 0.05)",
        float: "0 40px 80px -30px rgb(12 12 54 / 0.45), 0 12px 30px -12px rgb(12 12 54 / 0.25)",
        cta: "0 6px 18px -8px rgb(254 120 2 / 0.7)",
      },
      backgroundImage: {
        "brand-gradient": "linear-gradient(90deg, #FE7802, #FFC252 48%, #3EECEB)",
      },
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
          "0%, 100%": { boxShadow: "0 0 0 0 rgba(62, 236, 235, 0.4)" },
          "50%": { boxShadow: "0 0 24px 8px rgba(62, 236, 235, 0.15)" },
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
