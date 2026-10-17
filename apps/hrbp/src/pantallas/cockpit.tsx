import { ETIQUETA_ESTADO_APLICACION, ETIQUETA_SIGUIENTE_PASO } from "@vortex/types/etiquetas";
import { ETAPAS_DEL_PIPELINE, type EtapaDelPipeline } from "@vortex/types/reglas";
import { Badge, buttonVariants } from "@vortex/ui";
import { Plus } from "lucide-react";

import { anchoRelativo, conversion } from "../cockpit/embudo";
import type { Indicador } from "../cockpit/resumen";
import { useResumenCockpit } from "../datos/consultas";
import { Encabezado } from "../marco/marco";
import { Enlace } from "../navegacion/ruta";

// Del interés (aqua) a la decisión (flame), como en el tablero B.
const BARRA_DE_ETAPA: Record<EtapaDelPipeline, string> = {
  applied: "bg-aqua-100",
  evaluated: "bg-aqua-300",
  shortlisted: "bg-aqua-600",
  interviewed: "bg-flame-400",
  offered: "bg-flame-500",
};

const formatoFecha = new Intl.DateTimeFormat("es-MX", {
  weekday: "long",
  day: "numeric",
  month: "long",
});
const formatoUsd = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
});

function Kpi({
  etiqueta,
  indicador,
  tono,
}: { etiqueta: string; indicador: Indicador; tono?: "aqua" | "flame" }) {
  const fondo =
    tono === "aqua"
      ? "border-aqua-100 bg-aqua-50"
      : tono === "flame"
        ? "border-flame-100 bg-flame-50"
        : "border-mist-200 bg-white";
  const texto = tono === "flame" ? "text-flame-700" : "text-aqua-700";
  return (
    <div className={`flex flex-col gap-1 rounded-[22px] border p-5 ${fondo}`}>
      <span className={`text-[13.5px] font-bold ${tono ? texto : "text-mist-600"}`}>
        {etiqueta}
      </span>
      <span className="text-[2.4rem] font-extrabold leading-none tracking-[-0.04em] tabular-nums">
        {indicador.valor}
      </span>
      <span className={`text-[13px] font-bold ${texto}`}>{indicador.variacion}</span>
    </div>
  );
}

/** "Hoy" del plan con servicios de IA: qué decidir, cómo va el pipeline y qué hicieron los agentes. */
export function Cockpit() {
  const { data: r } = useResumenCockpit();
  if (!r) return null;

  const fecha = formatoFecha.format(new Date());
  const conteos = ETAPAS_DEL_PIPELINE.map((e) => r.pipeline.conteos[e]);

  return (
    <>
      <Encabezado
        etiqueta={fecha.charAt(0).toUpperCase() + fecha.slice(1)}
        titulo={
          <>
            Tu día, <i>ya ordenado</i>
          </>
        }
        accion={
          <Enlace href="/vacantes/nueva" className={buttonVariants()}>
            <Plus aria-hidden="true" className="h-4 w-4" />
            Crear empleo
          </Enlace>
        }
      />

      <div className="grid gap-3.5 sm:grid-cols-2 xl:grid-cols-4">
        <section
          aria-label="Decisión del día"
          className="flex flex-col gap-3 rounded-[22px] bg-ink-900 p-6 text-white sm:col-span-2 xl:row-span-2"
        >
          <span className="font-mono text-[11px] font-semibold uppercase tracking-[0.08em] text-aqua-300">
            Decisión del día · {r.decision.posicion} de {r.decision.total}
          </span>
          <h2 className="text-[1.75rem] leading-tight tracking-[-0.03em]">{r.decision.titulo}</h2>
          <p className="text-[15px] text-ink-200">{r.decision.detalle}</p>
        </section>
        <Kpi etiqueta="Candidatos en proceso" indicador={r.candidatosEnProceso} />
        <Kpi etiqueta="Vacantes publicadas" indicador={r.vacantesPublicadas} />
        <Kpi etiqueta="Evaluaciones IA (24 h)" indicador={r.evaluacionesIa24h} tono="aqua" />
        <Kpi etiqueta="En espera del modelo" indicador={r.enEsperaDelModelo} tono="flame" />
      </div>

      <div className="grid items-start gap-3.5 xl:grid-cols-[minmax(0,1.7fr)_minmax(300px,1fr)]">
        <section
          aria-label="Mejores evaluados"
          className="min-w-0 rounded-[22px] border border-mist-200 bg-white p-5"
        >
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-[19px]">{r.mejoresEvaluados.vacante} · mejores evaluados</h2>
            <Badge variant="success">A ciegas</Badge>
          </div>
          <div className="overflow-x-auto">
            <table className="mt-2 w-full min-w-[520px] border-collapse text-[14.5px]">
              <thead>
                <tr className="text-left text-[12.5px] text-mist-600">
                  <th scope="col" className="py-2 font-bold">
                    Candidato
                  </th>
                  <th scope="col" className="py-2 font-bold">
                    Score
                  </th>
                  <th scope="col" className="py-2 font-bold">
                    Razonamiento
                  </th>
                  <th scope="col" className="py-2 font-bold">
                    Siguiente paso
                  </th>
                </tr>
              </thead>
              <tbody>
                {r.mejoresEvaluados.filas.map((f) => (
                  <tr key={f.candidato} className="border-t border-mist-150">
                    <td className="py-3 font-bold">{f.candidato}</td>
                    <td className="py-3 font-extrabold tabular-nums">{f.score.toFixed(1)}</td>
                    <td className="py-3 text-mist-700">{f.razonamiento}</td>
                    <td className="py-3">
                      <Badge variant={f.siguientePaso === "entrevista" ? "default" : "manual"}>
                        {ETIQUETA_SIGUIENTE_PASO[f.siguientePaso]}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-2 text-sm text-mist-600">
            {r.mejoresEvaluados.total} evaluados en total.
          </p>
        </section>

        <section
          aria-label="Pipeline"
          className="flex flex-col gap-3.5 rounded-[22px] border border-mist-200 bg-white p-5"
        >
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-[19px]">Pipeline</h2>
            <span className="font-mono text-[11px] font-semibold text-mist-600">
              conversión vs. paso anterior
            </span>
          </div>
          {ETAPAS_DEL_PIPELINE.map((etapa, i) => {
            const conteo = r.pipeline.conteos[etapa];
            const pct = conversion(conteo, conteos[i - 1]);
            return (
              <div
                key={etapa}
                data-etapa={ETIQUETA_ESTADO_APLICACION[etapa]}
                className="flex flex-col gap-1.5"
              >
                <div className="flex justify-between text-sm font-semibold">
                  <span>
                    {ETIQUETA_ESTADO_APLICACION[etapa]}
                    {pct !== null && (
                      <span className="ml-1.5 font-mono text-[11px] text-mist-600">{pct} %</span>
                    )}
                  </span>
                  <b className="tabular-nums">{conteo}</b>
                </div>
                <div className="h-2.5 rounded-full bg-mist-100" aria-hidden="true">
                  <div
                    className={`h-full rounded-full ${BARRA_DE_ETAPA[etapa]}`}
                    style={{ width: `${Math.max(2, anchoRelativo(conteo, conteos))}%` }}
                  />
                </div>
              </div>
            );
          })}
        </section>
      </div>

      <div className="grid items-start gap-3.5 xl:grid-cols-[minmax(0,1.7fr)_minmax(300px,1fr)]">
        <section
          aria-label="Registro de los agentes"
          className="rounded-[22px] border border-mist-200 bg-white px-5 py-4"
        >
          <h2 className="pb-1.5 text-[19px]">Registro de los agentes</h2>
          {r.registro.map((e) => (
            <div
              key={`${e.hora}-${e.agente}`}
              className="grid grid-cols-[48px_minmax(0,1fr)_72px] items-center gap-3 border-t border-mist-150 py-2.5 font-mono text-[12.5px] text-mist-600 sm:grid-cols-[56px_120px_minmax(0,1fr)_84px]"
            >
              <span>{e.hora}</span>
              <span
                className={`hidden sm:inline ${e.costoUsd === null ? "text-flame-700" : "text-aqua-700"}`}
              >
                {e.agente}
              </span>
              <span className="font-sans text-sm text-ink-900">{e.detalle}</span>
              <span className="text-right">
                {e.costoUsd === null ? "reintento" : `$${e.costoUsd.toFixed(4)}`}
              </span>
            </div>
          ))}
        </section>
        <section
          aria-label="Gasto de IA"
          className="flex flex-col gap-2 rounded-[22px] bg-ink-900 p-5 text-white"
        >
          <span className="font-mono text-[11px] font-semibold uppercase tracking-[0.08em] text-aqua-300">
            Gasto de IA del mes
          </span>
          <span className="text-2xl font-extrabold">{formatoUsd.format(r.gastoIaDelMes.usd)}</span>
          <div className="h-1.5 rounded-full bg-ink-800" aria-hidden="true">
            <div
              className="h-full rounded-full bg-aqua-300"
              style={{ width: `${r.gastoIaDelMes.porcentajeDelTope}%` }}
            />
          </div>
          <span className="text-[12.5px] text-mist-300">
            {r.gastoIaDelMes.porcentajeDelTope} % del tope mensual
          </span>
        </section>
      </div>
    </>
  );
}
