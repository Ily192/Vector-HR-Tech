import type { Config } from "tailwindcss";
import vortexPreset from "@vortex/design-tokens/tailwind.preset";

const config: Config = {
  presets: [vortexPreset],
  content: [
    "./index.html",
    "./src/**/*.{ts,tsx}",
    "../../packages/ui/src/**/*.{ts,tsx}",
  ],
};

export default config;
