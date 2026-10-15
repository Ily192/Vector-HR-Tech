import type { Metadata, Viewport } from "next";
import { Figtree, JetBrains_Mono } from "next/font/google";
import { SiteFooter } from "../components/site-footer";
import { SiteHeader } from "../components/site-header";
import "./globals.css";

// Marca v2: una sola familia (Figtree, con cursivas para la firma) y mono para etiquetas.
const figtree = Figtree({
  subsets: ["latin", "latin-ext"],
  variable: "--font-figtree",
  style: ["normal", "italic"],
  display: "swap",
});

const jetbrains = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains",
  weight: ["500", "600"],
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "Vortex Ops · Vector HR Tech",
    template: "%s · Vortex Ops",
  },
  description:
    "Hackeando la rutina, liberando el talento. Operations Engine agentic para HR, Sales y Cross-functional ops.",
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL ?? "https://vortex-ops.com"),
  openGraph: {
    siteName: "Vortex Ops",
    locale: "es_LA",
    type: "website",
  },
  robots: { index: true, follow: true },
};

export const viewport: Viewport = {
  themeColor: "#181854",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="es" className={`${figtree.variable} ${jetbrains.variable}`}>
      <body className="flex min-h-screen flex-col bg-background text-foreground antialiased">
        <a
          href="#contenido"
          className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-50 focus:rounded-xl focus:bg-ink-900 focus:px-4 focus:py-2 focus:text-white"
        >
          Saltar al contenido
        </a>
        <SiteHeader />
        <div id="contenido" className="flex-1">
          {children}
        </div>
        <SiteFooter />
      </body>
    </html>
  );
}
