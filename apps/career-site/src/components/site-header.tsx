import { Wordmark } from "@vortex/ui";
import Link from "next/link";

// "Cómo aplicar" se oculta en móvil: no cabe junto al logo y la sección está en el inicio.
const NAV = [
  { href: "/vacantes", label: "Vacantes", soloEscritorio: false },
  { href: "/#como-aplicar", label: "Cómo aplicar", soloEscritorio: true },
] as const;

/** Cabecera del sitio de candidatos. Sin CTAs de venta (ADR-017). */
export function SiteHeader() {
  return (
    <header className="bg-ink-900 text-white">
      <div className="container mx-auto flex h-[68px] items-center gap-6 px-4 md:px-6">
        <Link
          href="/"
          aria-label="Vortex Empleos, inicio"
          className="flex items-center gap-2.5 rounded-lg"
        >
          <Wordmark brand="vortex" size="sm" tone="dark" withMark />
          <span className="font-mono text-[11px] font-semibold uppercase tracking-[0.08em] text-aqua-300">
            Empleos
          </span>
        </Link>
        <nav aria-label="Principal" className="ml-auto flex items-center gap-1">
          {NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={`${item.soloEscritorio ? "hidden sm:inline-flex" : "inline-flex"} rounded-full px-3 py-2 text-sm font-bold text-mist-300 transition-colors hover:bg-ink-800 hover:text-white sm:px-4`}
            >
              {item.label}
            </Link>
          ))}
        </nav>
      </div>
    </header>
  );
}
