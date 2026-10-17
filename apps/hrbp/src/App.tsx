import {
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Wordmark,
} from "@vortex/ui";
import { Activity, Briefcase, Users, Zap } from "lucide-react";

import { ETIQUETA_ESTADO_APLICACION } from "@vortex/types/etiquetas";
import { ETAPAS_DEL_PIPELINE, type EtapaDelPipeline } from "@vortex/types/reglas";

import { anchoRelativo } from "./cockpit/embudo";
import { ES_DE_EJEMPLO, obtenerResumenCockpit } from "./cockpit/resumen";

// Cada etapa con su tono de la marca: del interés (aqua) a la decisión (flame).
const TONO_DE_ETAPA: Record<EtapaDelPipeline, { color: string; barra: string }> = {
  applied: { color: "bg-aqua-300/15 text-aqua-300", barra: "bg-aqua-300" },
  evaluated: { color: "bg-ink-400/25 text-ink-200", barra: "bg-ink-400" },
  shortlisted: { color: "bg-success-500/15 text-success-500", barra: "bg-success-500" },
  interviewed: { color: "bg-flame-400/15 text-flame-400", barra: "bg-flame-400" },
  offered: { color: "bg-flame-500/20 text-flame-500", barra: "bg-flame-500" },
};

export function App() {
  const resumen = obtenerResumenCockpit();
  const { sesion, pipeline } = resumen;
  const kpis = [
    {
      icon: Briefcase,
      burbuja: "bg-flame-500/15 text-flame-400",
      label: "Vacantes activas",
      ...resumen.vacantesActivas,
    },
    {
      icon: Users,
      burbuja: "bg-aqua-300/15 text-aqua-300",
      label: "Candidatos en pipeline",
      ...resumen.candidatosEnPipeline,
    },
    {
      icon: Zap,
      burbuja: "bg-ink-500/25 text-ink-200",
      label: "Runs de agentes (24h)",
      ...resumen.runsDeAgentes24h,
    },
    {
      icon: Activity,
      burbuja: "bg-success-500/15 text-success-500",
      label: "Costo IA hoy (USD)",
      ...resumen.costoIaHoyUsd,
    },
  ];
  const conteos = ETAPAS_DEL_PIPELINE.map((etapa) => pipeline.conteos[etapa]);

  return (
    <div className="min-h-screen bg-[radial-gradient(900px_420px_at_100%_-10%,rgb(62_236_235/0.08),transparent_60%),radial-gradient(700px_380px_at_-10%_110%,rgb(254_120_2/0.07),transparent_60%)]">
      {/* Barra superior */}
      <header className="sticky top-0 z-40 border-b border-border bg-background/80 backdrop-blur-xl">
        <div className="container mx-auto flex h-[68px] items-center justify-between px-4 md:px-6">
          <Wordmark brand="vortex" size="sm" tone="dark" withMark />
          <div className="flex items-center gap-3">
            <Badge variant="ai">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-aqua-300" />
              Live
            </Badge>
            <Button size="sm" variant="ghost" className="gap-2.5">
              <span className="grid h-7 w-7 place-items-center rounded-full bg-ink-600 font-mono text-[11px] font-semibold text-white">
                {sesion.iniciales}
              </span>
              {sesion.nombre} · {sesion.empresa}
            </Button>
          </div>
        </div>
      </header>

      <main className="container mx-auto px-4 py-10 md:px-6">
        {/* Encabezado */}
        <div className="mb-10 flex flex-col gap-6 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="eyebrow">Cockpit HRBP</p>
            <h1 className="mt-3 text-3xl font-extrabold tracking-[-0.03em] md:text-[2.6rem]">
              Hola, {sesion.nombre} <span aria-hidden="true">👋</span>
            </h1>
            <p className="mt-2 text-muted-foreground">
              Esto es lo que tus agentes hicieron mientras dormías.
            </p>
          </div>
          <Button>+ Nueva vacante</Button>
        </div>

        {/* Indicadores */}
        <div className="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {kpis.map((kpi) => (
            <Card key={kpi.label}>
              <CardHeader className="pb-3">
                <span
                  className={`mb-1 grid h-10 w-10 place-items-center rounded-xl ${kpi.burbuja}`}
                >
                  <kpi.icon className="h-5 w-5" />
                </span>
                <CardDescription className="text-[13px] font-semibold">{kpi.label}</CardDescription>
              </CardHeader>
              <CardContent>
                <p className="font-display text-[2.1rem] font-extrabold leading-none tracking-[-0.03em] tabular-nums">
                  {kpi.valor}
                </p>
                <p className="mt-2 text-[13px] text-muted-foreground">{kpi.variacion}</p>
              </CardContent>
            </Card>
          ))}
        </div>

        {/* Pipeline (placeholder) */}
        <Card>
          <CardHeader>
            <CardTitle className="text-xl">Pipeline · {pipeline.vacante}</CardTitle>
            {ES_DE_EJEMPLO && (
              <CardDescription>Mock — el cycle 1 conecta esto a hr-engine</CardDescription>
            )}
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
              {ETAPAS_DEL_PIPELINE.map((etapa) => (
                <div
                  key={etapa}
                  data-etapa={ETIQUETA_ESTADO_APLICACION[etapa]}
                  className="rounded-2xl bg-white/[0.04] p-4 ring-1 ring-border"
                >
                  <div className="mb-3 flex items-center justify-between">
                    <p className="font-mono text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                      {ETIQUETA_ESTADO_APLICACION[etapa]}
                    </p>
                    <span
                      className={`rounded-full px-2.5 py-0.5 text-xs font-bold tabular-nums ${TONO_DE_ETAPA[etapa].color}`}
                    >
                      {pipeline.conteos[etapa]}
                    </span>
                  </div>
                  <div
                    className="mb-3 h-1.5 overflow-hidden rounded-full bg-white/10"
                    aria-hidden="true"
                  >
                    <div
                      className={`h-full rounded-full ${TONO_DE_ETAPA[etapa].barra}`}
                      style={{ width: `${anchoRelativo(pipeline.conteos[etapa], conteos)}%` }}
                    />
                  </div>
                  <div className="space-y-2">
                    <div className="h-12 rounded-xl bg-muted shimmer-cyan" />
                    <div className="h-12 rounded-xl bg-muted shimmer-cyan" />
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </main>
    </div>
  );
}
