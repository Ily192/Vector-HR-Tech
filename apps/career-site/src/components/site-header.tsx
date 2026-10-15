import { Button, Wordmark } from "@vortex/ui";
import Link from "next/link";

const NAV = [
  { href: "/vacantes", label: "Vacantes" },
  { href: "/contacto", label: "Contacto" },
] as const;

export function SiteHeader() {
  return (
    <header className="sticky top-0 z-40 border-b border-border bg-white/85 backdrop-blur-xl backdrop-saturate-150">
      <div className="container mx-auto flex h-[68px] items-center gap-6 px-4 md:px-6">
        <Link href="/" aria-label="Vortex Ops, inicio" className="rounded-lg text-ink-900">
          <Wordmark brand="vortex" size="sm" tone="light" withMark />
        </Link>
        <nav aria-label="Principal" className="ml-auto hidden items-center gap-1 sm:flex">
          {NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="rounded-full px-4 py-2 text-sm font-bold text-mist-700 transition-colors hover:bg-mist-100 hover:text-ink-900"
            >
              {item.label}
            </Link>
          ))}
        </nav>
        <Button size="sm" asChild className="ml-auto sm:ml-0">
          <Link href="/contacto">Agendar demo</Link>
        </Button>
      </div>
    </header>
  );
}
