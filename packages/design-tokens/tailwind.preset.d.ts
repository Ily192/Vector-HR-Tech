import type { Config } from "tailwindcss";

/**
 * El preset se consume desde `tailwind.config.ts` de cada app:
 *
 *   import fluvePreset from "@fluveai/design-tokens/tailwind.preset";
 *   export default { presets: [fluvePreset], content: [...] } satisfies Config;
 *
 * Se tipa como `Partial<Config>` porque un preset no necesita declarar `content`.
 */
declare const preset: Partial<Config>;
export = preset;
