import { Wordmark } from "@vortex/ui";
import Link from "next/link";

const CONTACT_EMAIL = process.env.NEXT_PUBLIC_CONTACT_EMAIL ?? "hola@vectorhr.tech";

export function SiteFooter() {
  return (
    <footer className="border-t border-border bg-card">
      <div className="container mx-auto flex flex-col gap-6 px-4 py-10 md:flex-row md:items-center md:justify-between md:px-6">
        <div className="space-y-2">
          <Wordmark brand="vector" size="sm" tone="light" />
          <p className="text-sm text-muted-foreground">
            © {new Date().getFullYear()} Vector HR Tech · Hecho en LATAM
          </p>
        </div>
        <nav
          aria-label="Pie de página"
          className="flex flex-wrap gap-x-6 gap-y-2 text-sm font-semibold"
        >
          <Link className="text-mist-700 hover:text-ink-900" href="/vacantes">
            Vacantes
          </Link>
          <Link className="text-mist-700 hover:text-ink-900" href="/contacto">
            Contacto
          </Link>
          <a className="text-aqua-700 hover:underline" href={`mailto:${CONTACT_EMAIL}`}>
            {CONTACT_EMAIL}
          </a>
        </nav>
      </div>
    </footer>
  );
}
