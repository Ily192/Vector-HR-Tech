import { ETIQUETA_ESTADO_VACANTE, ETIQUETA_MODALIDAD } from "@vortex/types/etiquetas";
import { Badge, Button, Card, CardContent, CardHeader, CardTitle } from "@vortex/ui";
import { ArrowLeft, Upload } from "lucide-react";
import Link from "next/link";
import { notFound } from "next/navigation";

import { obtenerVacante } from "../../../lib/vacantes";

// Desde Next 15 `params` llega como Promise, y Next 16 retiró el acceso síncrono.
export default async function VacanteDetail({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const v = await obtenerVacante(slug);
  if (!v) notFound();

  return (
    <main className="container mx-auto max-w-3xl px-4 py-12 md:px-6 md:py-16">
      <Link
        href="/vacantes"
        className="mb-8 inline-flex items-center gap-2 rounded-full text-sm font-semibold text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" /> Volver a vacantes
      </Link>

      <header className="mb-8">
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <Badge variant="ai">{ETIQUETA_ESTADO_VACANTE.open}</Badge>
          <Badge variant="outline">{ETIQUETA_MODALIDAD[v.modality]}</Badge>
          {v.location && <Badge variant="outline">{v.location}</Badge>}
        </div>
        <h1 className="text-4xl font-extrabold tracking-[-0.035em] md:text-5xl">{v.title}</h1>
      </header>

      <Card className="mb-6">
        <CardHeader>
          <CardTitle className="text-lg">Sobre el rol</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-[15.5px] leading-relaxed text-mist-700">{v.jd}</p>
        </CardContent>
      </Card>

      <Card className="border-ink-100 bg-[linear-gradient(180deg,theme(colors.ink.50),#fff_70%)]">
        <CardHeader>
          <CardTitle className="text-lg">Aplicar</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="mb-4 text-sm text-muted-foreground">
            Sube tu CV. Lo evaluamos sin usar tu nombre y te avisamos por correo del siguiente paso:
            una entrevista, un test psicométrico breve o una respuesta clara si no encaja.
          </p>
          <Button size="lg" disabled>
            <Upload className="h-4 w-4" /> Subir CV (próximamente)
          </Button>
        </CardContent>
      </Card>
    </main>
  );
}
