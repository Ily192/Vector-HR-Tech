import { Wordmark } from "@fluveai/ui";

import { PANEL_EMPRESAS_URL, PUBLICAR_VACANTES_URL } from "../lib/site-config";

/**
 * Pie del sitio de candidatos. Para empresas, dos enlaces y nada más (enmienda de
 * ADR-017 del 2026-11-11): registrarse gratis en la web de Vector HR Tech, o entrar al
 * panel si ya publican.
 */
export function SiteFooter() {
  return (
    <footer className="bg-ink-950 text-mist-300">
      <div className="container mx-auto flex flex-col gap-4 px-4 py-8 text-sm md:flex-row md:items-center md:px-6">
        <Wordmark brand="vector" size="sm" tone="dark" />
        <p>© {new Date().getFullYear()} · Un servicio de Vector HR Tech</p>
        <div className="flex flex-col gap-2 md:ml-auto md:flex-row md:gap-5">
          <a className="font-bold text-aqua-300 hover:underline" href={PUBLICAR_VACANTES_URL}>
            ¿Contratas? Publica tus vacantes gratis
          </a>
          <a className="font-bold text-aqua-300 hover:underline" href={PANEL_EMPRESAS_URL}>
            ¿Ya publicas? Entra a tu panel
          </a>
        </div>
      </div>
    </footer>
  );
}
