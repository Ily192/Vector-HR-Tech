import {
  ETIQUETA_ESTADO_VACANTE,
  ETIQUETA_MODALIDAD,
  ETIQUETA_SENIORITY,
} from "@vortex/types/etiquetas";
import { Badge, Card, CardContent, CardHeader, CardTitle } from "@vortex/ui";
import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { notFound } from "next/navigation";

import { FormularioDeAplicacion } from "../../../components/formulario-de-aplicacion";
import { formatearSalario } from "../../../lib/formato";
import { obtenerVacante, recibeAplicaciones } from "../../../lib/vacantes";
import { aplicarAVacante } from "./acciones";

type Props = { params: Promise<{ slug: string }> };

/** Título de la pestaña con el puesto y la empresa; comparte la lectura con la página. */
export async function generateMetadata({ params }: Props) {
  const v = await obtenerVacante((await params).slug);
  return v ? { title: `${v.title} · ${v.empresa_nombre}` } : {};
}

// Desde Next 15 `params` llega como Promise, y Next 16 retiró el acceso síncrono.
export default async function VacanteDetail({ params }: Props) {
  const { slug } = await params;
  const v = await obtenerVacante(slug);
  if (!v) notFound();
  const salario = formatearSalario(v);

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
          {v.seniority && <Badge variant="outline">{ETIQUETA_SENIORITY[v.seniority]}</Badge>}
        </div>
        <h1 className="text-4xl font-extrabold tracking-[-0.035em] md:text-5xl">{v.title}</h1>
        <p className="mt-2 text-lg font-semibold text-mist-700">{v.empresa_nombre}</p>
        <p className="mt-3 text-lg font-extrabold tabular-nums">
          {salario ? (
            <>
              {salario}{" "}
              <span className="text-sm font-semibold text-mist-600">{v.moneda} / mes</span>
            </>
          ) : (
            <span className="text-base font-bold text-mist-600">Salario a convenir</span>
          )}
        </p>
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
          {v.cupo_completo ? (
            <p className="text-sm text-muted-foreground">
              <b className="text-ink-900">Esta vacante ya no recibe aplicaciones.</b> Llegó al
              máximo que la empresa puede recibir. Mira otras vacantes abiertas.
            </p>
          ) : recibeAplicaciones() ? (
            <>
              <p className="mb-4 text-sm text-muted-foreground">
                Envía tu CV a {v.empresa_nombre}. Si avanzas en el proceso, te escriben al correo
                que dejes.
              </p>
              <FormularioDeAplicacion
                accion={aplicarAVacante.bind(null, v.slug)}
                empresa={v.empresa_nombre}
                conIa={v.evalua_con_ia}
                sitekey={process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY || null}
              />
            </>
          ) : (
            <p className="text-sm text-muted-foreground">
              Las aplicaciones a esta vacante se abren pronto.
            </p>
          )}
        </CardContent>
      </Card>
    </main>
  );
}
