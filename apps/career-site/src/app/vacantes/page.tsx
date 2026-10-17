import {
  ETIQUETA_ESTADO_VACANTE,
  ETIQUETA_MODALIDAD,
  ETIQUETA_SENIORITY,
} from "@vortex/types/etiquetas";
import { Badge, Card, CardContent, CardDescription, CardHeader, CardTitle } from "@vortex/ui";
import { ArrowRight, Briefcase, Clock, MapPin } from "lucide-react";
import Link from "next/link";

import { listarVacantes } from "../../lib/vacantes";

export const metadata = { title: "Vacantes abiertas" };

export default async function VacantesPage() {
  const vacantes = await listarVacantes();

  return (
    <main className="container mx-auto max-w-4xl px-4 py-14 md:px-6 md:py-20">
      <header className="mb-10">
        <span className="eyebrow">{vacantes.length} vacantes abiertas</span>
        <h1 className="mt-3 text-4xl font-extrabold tracking-[-0.035em] md:text-5xl">
          Vacantes abiertas
        </h1>
        <p className="mt-3 max-w-xl text-lg text-muted-foreground">
          Buscamos rebeldes que quieran liberar talento, no domesticarlo.
        </p>
      </header>

      <div className="grid gap-4">
        {vacantes.map((v) => (
          <Link
            key={v.slug}
            href={`/vacantes/${v.slug}`}
            className="group block rounded-[20px] focus-visible:outline-none"
          >
            <Card className="transition-[box-shadow,border-color,transform] duration-normal group-hover:-translate-y-0.5 group-hover:border-ink-200 group-hover:shadow-lift">
              <CardHeader>
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <CardTitle className="text-xl">{v.title}</CardTitle>
                    <CardDescription className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5 text-[13px] font-semibold">
                      {v.seniority && (
                        <span className="flex items-center gap-1.5">
                          <Briefcase className="h-3.5 w-3.5" /> {ETIQUETA_SENIORITY[v.seniority]}
                        </span>
                      )}
                      {v.location && (
                        <span className="flex items-center gap-1.5">
                          <MapPin className="h-3.5 w-3.5" /> {v.location}
                        </span>
                      )}
                      <span className="flex items-center gap-1.5">
                        <Clock className="h-3.5 w-3.5" /> {ETIQUETA_MODALIDAD[v.modality]}
                      </span>
                    </CardDescription>
                  </div>
                  <Badge variant="ai">{ETIQUETA_ESTADO_VACANTE.open}</Badge>
                </div>
              </CardHeader>
              <CardContent className="flex items-end justify-between gap-4">
                <p className="line-clamp-2 text-[15px] text-muted-foreground">{v.jd}</p>
                <ArrowRight className="h-5 w-5 shrink-0 text-mist-500 transition-transform group-hover:translate-x-1 group-hover:text-ink-900" />
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </main>
  );
}
