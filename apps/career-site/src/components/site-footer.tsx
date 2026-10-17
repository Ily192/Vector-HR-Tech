import { Wordmark } from "@vortex/ui";

import { PANEL_EMPRESAS_URL } from "../lib/site-config";

/** Pie del sitio de candidatos. La única puerta para empresas es su panel. */
export function SiteFooter() {
  return (
    <footer className="bg-ink-950 text-mist-300">
      <div className="container mx-auto flex flex-col gap-4 px-4 py-8 text-sm md:flex-row md:items-center md:px-6">
        <Wordmark brand="vortex" size="sm" tone="dark" />
        <p>© {new Date().getFullYear()} · Un servicio de Vector HR Tech</p>
        <a className="font-bold text-aqua-300 hover:underline md:ml-auto" href={PANEL_EMPRESAS_URL}>
          ¿Publicas vacantes? Entra a tu panel
        </a>
      </div>
    </footer>
  );
}
