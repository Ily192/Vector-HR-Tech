/**
 * Variables que lee el panel. Vite solo las reemplaza escritas completas
 * (`import.meta.env.VITE_…`): con una clave dinámica llegan vacías.
 */
interface ImportMetaEnv {
  /** URL del proyecto de Supabase. Sin ella el panel usa datos de ejemplo. */
  readonly VITE_SUPABASE_URL?: string;
  /** Clave publishable (sb_publishable_…). La legada `anon` también sirve. */
  readonly VITE_SUPABASE_PUBLISHABLE_KEY?: string;
  readonly VITE_SUPABASE_ANON_KEY?: string;
}
