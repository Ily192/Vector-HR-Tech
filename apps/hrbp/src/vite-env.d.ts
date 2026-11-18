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
  /**
   * Opcional: dónde está el hr-engine para el área de admin (`/admin/*`). Sin ella, en
   * `VITE_SUPABASE_URL`: en producción Caddy publica los dos en api.vectorhrtech.com.
   */
  readonly VITE_ADMIN_API_URL?: string;
  /** Opcional: las métricas de la web. Sin ella, https://vectorhrtech.com/api/admin/metricas. */
  readonly VITE_WEB_METRICAS_URL?: string;
}
