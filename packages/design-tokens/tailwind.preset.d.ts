import type { Config } from "tailwindcss";

/**
 * El preset se consume desde `tailwind.config.ts` de cada app:
 *
 *   import vortexPreset from "@vortex/design-tokens/tailwind.preset";
 *   export default { presets: [vortexPreset], content: [...] } satisfies Config;
 *
 * Se tipa como `Partial<Config>` porque un preset no necesita declarar `content`.
 */
declare const preset: Partial<Config>;
export = preset;
