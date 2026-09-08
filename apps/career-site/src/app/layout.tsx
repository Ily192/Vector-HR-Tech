import type { Metadata } from "next";
import { Inter, Lato } from "next/font/google";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-display",
  weight: ["400", "600", "700", "900"],
});

const lato = Lato({
  subsets: ["latin"],
  variable: "--font-body",
  weight: ["400", "700", "900"],
  style: ["normal", "italic"],
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

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="es" className={`${inter.variable} ${lato.variable}`}>
      <body className="min-h-screen bg-background font-body text-foreground antialiased">
        {children}
      </body>
    </html>
  );
}
