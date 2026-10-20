import { ETIQUETA_ESTADO_APLICACION, ETIQUETA_SIGUIENTE_PASO } from "@vortex/types/etiquetas";
import { ETAPAS_DEL_PIPELINE, type EtapaDelPipeline } from "@vortex/types/reglas";
import { Badge, buttonVariants } from "@vortex/ui";
import { Plus } from "lucide-react";

import { anchoRelativo, conversion } from "../cockpit/embudo";
import {
  detalleDelRegistro,
  textoDeLaDecision,
  variacionDeCandidatos,
  variacionDeEnEspera,
  variacionDeEvaluaciones,
  variacionDeVacantes,
} from "../cockpit/textos";
import { useResumenCockpit } from "../datos/consultas";
import type { DecisionDelDia, ResumenCockpit, VacanteDelDia } from "../datos/tipos";
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
// En 24 h: "16:42" cabe en la columna del registro; "04:42 p.m.", no.
const formatoHora = new Intl.DateTimeFormat("es-MX", {
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});
const formatoNumero = new Intl.NumberFormat("es-MX");

const hrefDe = (vacante: VacanteDelDia) => `/vacantes/${encodeURIComponent(vacante.id)}`;

function Kpi({
  etiqueta,
  valor,
  variacion,
  tono,
}: {
  etiqueta: string;
  valor: number;
  variacion: string;
  tono?: "aqua" | "flame";
}) {
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
        {formatoNumero.format(valor)}
      </span>
      <span className={`text-[13px] font-bold ${texto}`}>{variacion}</span>
    </div>
  );
}

function Decision({
  decision,
  pendientes,
}: { decision: DecisionDelDia | null; pendientes: number }) {
  const texto = decision && textoDeLaDecision(decision);
  return (
    <section
      aria-label="Decisión del día"
      className="flex flex-col gap-3 rounded-[22px] bg-ink-900 p-6 text-white sm:col-span-2 xl:row-span-2"
    >
      <span className="font-mono text-[11px] font-semibold uppercase tracking-[0.08em] text-aqua-300">
        Decisión del día{pendientes > 1 && ` · 1 de ${pendientes}`}
      </span>
      <h2 className="text-[1.75rem] leading-tight tracking-[-0.03em]">
        {texto ? texto.titulo : "Nada que decidir por ahora"}
      </h2>
      <p className="text-[15px] text-ink-200">
        {texto
          ? texto.detalle
          : "Cuando la IA evalúe aplicaciones nuevas, aquí verás a quién entrevistar primero."}
      </p>
      {decision && (
        <Enlace
          href={hrefDe(decision.vacante)}
          className="mt-auto self-start text-sm font-bold text-aqua-300 hover:underline"
        >
          Ir a {decision.vacante.titulo}
        </Enlace>
      )}
    </section>
  );
}

function MejoresEvaluados({ r }: { r: ResumenCockpit }) {
  const { vacante, mejoresEvaluados } = r;
  return (
    <section
      aria-label="Mejores evaluados"
      className="min-w-0 rounded-[22px] border border-mist-200 bg-white p-5"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-[19px]">
          {vacante ? `${vacante.titulo} · mejores evaluados` : "Mejores evaluados"}
        </h2>
        <Badge variant="success">Evaluación a ciegas</Badge>
      </div>
      {mejoresEvaluados.filas.length === 0 ? (
        <p className="mt-3 text-sm text-mist-600">
          Cuando la IA evalúe las aplicaciones, aquí verás a las de mejor encaje.
        </p>
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="mt-2 w-full min-w-[520px] border-collapse text-[14.5px]">
              <thead>
                <tr className="text-left text-[12.5px] text-mist-600">
                  <th scope="col" className="py-2 pr-3 font-bold">
                    Candidato
                  </th>
                  <th scope="col" className="py-2 pr-3 font-bold">
                    Score
                  </th>
                  <th scope="col" className="py-2 pr-3 font-bold">
                    Razonamiento
                  </th>
                  <th scope="col" className="whitespace-nowrap py-2 font-bold">
                    Siguiente paso
                  </th>
                </tr>
              </thead>
              <tbody>
                {mejoresEvaluados.filas.map((f) => (
                  <tr key={f.id} className="border-t border-mist-150 align-top">
                    <td className="py-3 pr-3 font-bold">{f.candidato}</td>
                    <td className="py-3 pr-3 font-extrabold tabular-nums">{f.score.toFixed(1)}</td>
                    <td className="py-3 pr-3 text-mist-700">
                      <span className="line-clamp-2">{f.razonamiento}</span>
                    </td>
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
            {mejoresEvaluados.total === 1
              ? "Un evaluado en proceso."
              : `${formatoNumero.format(mejoresEvaluados.total)} evaluados en proceso.`}{" "}
            {vacante && (
              <Enlace href={hrefDe(vacante)} className="font-bold text-aqua-700 hover:underline">
                Ver todos
              </Enlace>
            )}
          </p>
        </>
      )}
    </section>
  );
}

function Embudo({ r }: { r: ResumenCockpit }) {
  const conteos = ETAPAS_DEL_PIPELINE.map((e) => r.embudo[e]);
  return (
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
      {!r.vacante ? (
        <p className="text-sm text-mist-600">Publica una vacante y aquí verás su embudo.</p>
      ) : (
        ETAPAS_DEL_PIPELINE.map((etapa, i) => {
          const conteo = r.embudo[etapa];
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
                <b className="tabular-nums">{formatoNumero.format(conteo)}</b>
              </div>
              <div className="h-2.5 rounded-full bg-mist-100" aria-hidden="true">
                <div
                  className={`h-full rounded-full ${BARRA_DE_ETAPA[etapa]}`}
                  style={{ width: `${Math.max(2, anchoRelativo(conteo, conteos))}%` }}
                />
              </div>
            </div>
          );
        })
      )}
    </section>
  );
}

function Registro({ r }: { r: ResumenCockpit }) {
  return (
    <section
      aria-label="Registro de los agentes"
      className="rounded-[22px] border border-mist-200 bg-white px-5 py-4"
    >
      <h2 className="pb-1.5 text-[19px]">Registro de los agentes</h2>
      {r.registro.length === 0 && (
        <p className="border-t border-mist-150 py-2.5 text-sm text-mist-600">
          Sin actividad de los agentes en las últimas 24 h.
        </p>
      )}
      {r.registro.map((e) => (
        <div
          key={e.id}
          className="grid grid-cols-[48px_minmax(0,1fr)_72px] items-center gap-3 border-t border-mist-150 py-2.5 font-mono text-[12.5px] text-mist-600 sm:grid-cols-[56px_120px_minmax(0,1fr)_84px]"
        >
          <span>{formatoHora.format(new Date(e.en))}</span>
          <span className={`hidden sm:inline ${e.aplazada ? "text-flame-700" : "text-aqua-700"}`}>
            {e.agente}
          </span>
          <span className="font-sans text-sm text-ink-900">{detalleDelRegistro(e)}</span>
          <span className={`text-right ${e.aplazada ? "text-flame-700" : ""}`}>
            {e.aplazada ? "reintento" : "listo"}
          </span>
        </div>
      ))}
    </section>
  );
}

/** "Hoy" del plan con servicios de IA: qué decidir, cómo va el pipeline y qué hicieron los agentes. */
export function Cockpit() {
  const { data: r } = useResumenCockpit();
  if (!r) return null;

  const fecha = formatoFecha.format(new Date());
  const { cvsDelMes } = r;

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
        <Decision decision={r.decision} pendientes={r.decisionesPendientes} />
        <Kpi
          etiqueta="Candidatos en proceso"
          valor={r.candidatosEnProceso.total}
          variacion={variacionDeCandidatos(r.candidatosEnProceso.nuevos24h)}
        />
        <Kpi
          etiqueta="Vacantes publicadas"
          valor={r.vacantesPublicadas.total}
          variacion={variacionDeVacantes(r.vacantesPublicadas.nuevas7d)}
        />
        <Kpi
          etiqueta="Evaluaciones IA (24 h)"
          valor={r.evaluaciones24h.total}
          variacion={variacionDeEvaluaciones(r.evaluaciones24h.porcentajeSinError)}
          tono="aqua"
        />
        <Kpi
          etiqueta="En espera del modelo"
          valor={r.enEspera.total}
          variacion={variacionDeEnEspera(r.enEspera)}
          tono="flame"
        />
      </div>

      <div className="grid items-start gap-3.5 xl:grid-cols-[minmax(0,1.7fr)_minmax(300px,1fr)]">
        <MejoresEvaluados r={r} />
        <Embudo r={r} />
      </div>

      <div className="grid items-start gap-3.5 xl:grid-cols-[minmax(0,1.7fr)_minmax(300px,1fr)]">
        <Registro r={r} />
        <section
          aria-label="CV evaluados del mes"
          className="flex flex-col gap-2 rounded-[22px] bg-ink-900 p-5 text-white"
        >
          <span className="font-mono text-[11px] font-semibold uppercase tracking-[0.08em] text-aqua-300">
            CV evaluados del mes
          </span>
          <span className="text-2xl font-extrabold tabular-nums">
            {formatoNumero.format(cvsDelMes.evaluados)}{" "}
            <span className="text-base font-bold text-mist-300">
              de {formatoNumero.format(cvsDelMes.tope)}
            </span>
          </span>
          <div className="h-1.5 rounded-full bg-ink-800" aria-hidden="true">
            <div
              className="h-full rounded-full bg-aqua-300"
              style={{ width: `${cvsDelMes.porcentajeDelTope}%` }}
            />
          </div>
          <span className="text-[12.5px] text-mist-300">
            {cvsDelMes.porcentajeDelTope} % del tope mensual
          </span>
        </section>
      </div>
    </>
  );
}
