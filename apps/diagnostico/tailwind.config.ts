import vortexPreset from "@vortex/design-tokens/tailwind.preset";
import type { Config } from "tailwindcss";

const config: Config = {
  presets: [vortexPreset],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      // Los de vectorhrtech.com, que no están en el preset.
      colors: { void: "#05051a", gold: "#ffc252" },
    },
  },
};

export default config;
