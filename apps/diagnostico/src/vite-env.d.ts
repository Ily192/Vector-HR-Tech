/**
 * Variables que lee el diagnóstico. Vite solo las reemplaza escritas completas
 * (`import.meta.env.VITE_…`).
 */
interface ImportMetaEnv {
  /** Site key de Cloudflare Turnstile. Vacía (en local y en los tests) = sin captcha. */
  readonly VITE_TURNSTILE_SITE_KEY?: string;
}
