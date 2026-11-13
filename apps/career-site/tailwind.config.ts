import fluvePreset from "@fluveai/design-tokens/tailwind.preset";
import type { Config } from "tailwindcss";

const config: Config = {
  presets: [fluvePreset],
  content: ["./src/**/*.{ts,tsx}", "../../packages/ui/src/**/*.{ts,tsx}"],
};

export default config;
