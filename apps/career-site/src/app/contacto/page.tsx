import {
  Badge,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Wordmark,
} from "@vortex/ui";
import { ArrowLeft, Clock, Linkedin, Mail } from "lucide-react";
import Link from "next/link";

export const metadata = {
  title: "Hablar con Vector HR",
  description:
    "Conversemos sobre cómo Vortex Ops puede automatizar tus procesos de HR y Sales end-to-end.",
};

const CONTACT_EMAIL = process.env.NEXT_PUBLIC_CONTACT_EMAIL ?? "hola@vectorhr.tech";

const CANALES = [
  {
    icon: Mail,
    title: "Email",
    description: "La vía más rápida. Respondemos en menos de 24 h hábiles.",
    href: `mailto:${CONTACT_EMAIL}?subject=${encodeURIComponent("Quiero conocer Vortex Ops")}`,
    label: CONTACT_EMAIL,
  },
  {
    icon: Linkedin,
    title: "LinkedIn",
    description: "Escríbenos por mensaje directo si prefieres ese canal.",
    href: "https://www.linkedin.com/company/vector-hr-tech",
    label: "/company/vector-hr-tech",
  },
] as const;

export default function ContactoPage() {
  return (
    <main className="container mx-auto max-w-3xl px-4 py-12">
      <Link
        href="/"
        className="mb-6 inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" /> Volver al inicio
      </Link>

      <header className="mb-10">
        <div className="mb-4">
          <Wordmark brand="vector" size="md" />
        </div>
        <Badge variant="ai" className="mb-4">
          <Clock className="h-3 w-3" />
          Respuesta en 24 h
        </Badge>
        <h1 className="mb-4 text-4xl font-black tracking-tighter md:text-5xl">
          Hablemos de tu operación
        </h1>
        <p className="max-w-2xl text-lg text-muted-foreground">
          Cuéntanos qué proceso te está comiendo el tiempo. Te mostramos en una demo de 20 minutos
          cómo los agentes de Vortex Ops lo ejecutan end-to-end.
        </p>
      </header>

      <div className="grid gap-4 sm:grid-cols-2">
        {CANALES.map((canal) => (
          <Card key={canal.title}>
            <CardHeader>
              <canal.icon className="mb-2 h-6 w-6 text-vector-orange-500" />
              <CardTitle className="text-lg">{canal.title}</CardTitle>
              <CardDescription>{canal.description}</CardDescription>
            </CardHeader>
            <CardContent>
              <a
                className="text-sm font-semibold text-vector-cian-electric-700 underline-offset-4 hover:underline dark:text-vector-cian-electric-500"
                href={canal.href}
                rel="noreferrer noopener"
              >
                {canal.label}
              </a>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card className="mt-8">
        <CardHeader>
          <CardTitle className="text-lg">¿Buscas trabajo, no una demo?</CardTitle>
          <CardDescription>
            Nuestras vacantes abiertas están publicadas y las revisa un agente, no un filtro de
            palabras clave.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Link
            href="/vacantes"
            className="text-sm font-semibold text-vector-cian-electric-700 underline-offset-4 hover:underline dark:text-vector-cian-electric-500"
          >
            Ver vacantes abiertas →
          </Link>
        </CardContent>
      </Card>
    </main>
  );
}
