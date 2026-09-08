import vortexPreset from "@vortex/design-tokens/tailwind.preset";
import type { Config } from "tailwindcss";

const config: Config = {
  presets: [vortexPreset],
  content: ["./index.html", "./src/**/*.{ts,tsx}", "../../packages/ui/src/**/*.{ts,tsx}"],
};

export default config;
