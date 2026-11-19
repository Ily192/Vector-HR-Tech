import { ETIQUETA_ESTADO_APLICACION, ETIQUETA_SIGUIENTE_PASO } from "@fluveai/types/etiquetas";
import type { ApplicationStatus } from "@fluveai/types/hr";
import { ETAPAS_DEL_PIPELINE } from "@fluveai/types/reglas";
import { Button, buttonVariants, cn, haceCuanto } from "@fluveai/ui";
import { Download } from "lucide-react";
import { type FormEvent, useState } from "react";

import { anchoRelativo } from "../cockpit/embudo";
import {
  useDescargarCvs,
  useDescartar,
  useMarcarPostulacionesVistas,
  useMoverDeEtapa,
  usePipeline,
} from "../datos/consultas";
import type {
  Aplicado,
  DescargaDeCvs,
  EvaluacionConIa,
  GanchoDelPipeline,
  PipelineDeVacante,
  ResumenDeEvaluaciones,
} from "../datos/tipos";
import { Encabezado } from "../marco/marco";
import { Enlace } from "../navegacion/ruta";
import {
  BARRA_DE_ETAPA,
  TODAS_LAS_ETAPAS,
  contarPorEtapa,
  deLaEtapa,
  salidasVisibles,
} from "../pipeline/etapas";
import { EscribenosParaMas } from "./mas-del-plan";
import { AvisoDeModeracion, sinAplicaciones } from "./moderacion";

/** Cuántos candidatos se listan antes de "Ver los N". */
const CANDIDATOS_VISIBLES = 10;

const formatoHora = new Intl.DateTimeFormat("es-MX", { hour: "2-digit", minute: "2-digit" });

/** Ofrece al navegador el .zip ya armado y suelta la memoria después. */
function bajarArchivo(url: string, nombre: string) {
  const enlace = document.createElement("a");
  enlace.href = url;
  enlace.download = nombre;
  enlace.click();
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

function mensajeDeLaDescarga(descarga: DescargaDeCvs): string {
  if (descarga.url === null) {
    return descarga.motivo === "ejemplo"
      ? "Con datos de ejemplo no hay CVs que bajar."
      : "Ninguna aplicación de esta vacante trae CV.";
  }
  if (descarga.omitidos === 0) return "Listo: el .zip está en tus descargas.";
  return descarga.omitidos === 1
    ? "Listo. Un CV no se pudo bajar y no va en el .zip."
    : `Listo. ${descarga.omitidos} CVs no se pudieron bajar y no van en el .zip.`;
}

/** "Hoy, 09:12", "Ayer, 19:30" o "Hace 3 días". */
function cuandoAplico(fechaIso: string) {
  const dia = haceCuanto(fechaIso);
  return dia === "Hoy" || dia === "Ayer"
    ? `${dia}, ${formatoHora.format(new Date(fechaIso))}`
    : dia;
}

/**
 * El gancho del plan gratis, al estilo de "quién vio tu perfil": cuántos CVs
 * mencionan las skills de la vacante, sin decir cuáles. No es IA y lo dice: cuenta
 * menciones, no juzga experiencia (ADR-019). Dice "comparamos" y no "revisamos" para no
 * sonar a una persona, y no ofrece la IA hasta que Fluve AI esté lista (ADR-024).
 */
function Gancho({ gancho }: { gancho: GanchoDelPipeline }) {
  if (gancho.skills === 0 || gancho.revisados === 0) {
    return (
      <section
        aria-label="Coincidencia de skills"
        className="rounded-[22px] border border-mist-200 bg-white p-5 text-[14.5px] text-mist-700"
      >
        {gancho.skills === 0
          ? "Esta vacante no pide skills, así que no hay CVs que contar. Agrégalas al crear la próxima y te decimos cuántos CVs las mencionan."
          : `Comparamos los CVs de 5 en 5 con las ${gancho.skills} skills de la vacante. Con los primeros 5 te decimos cuántos las mencionan.`}
      </section>
    );
  }
  const notas = [
    gancho.enEspera > 0 &&
      (gancho.enEspera === 1 ? "Falta 1 por comparar." : `Faltan ${gancho.enEspera} por comparar.`),
    gancho.ilegibles > 0 &&
      (gancho.ilegibles === 1
        ? "Un CV no se pudo leer (escaneado o protegido)."
        : `${gancho.ilegibles} CVs no se pudieron leer (escaneados o protegidos).`),
  ].filter(Boolean);
  return (
    <section
      aria-label="Coincidencia de skills"
      className="flex flex-wrap items-center gap-5 rounded-[22px] bg-ink-900 p-6 text-white"
    >
      <div className="flex flex-[1_1_300px] flex-col gap-2">
        <span className="font-mono text-[11px] font-semibold uppercase tracking-[0.08em] text-aqua-300">
          Coincidencia de skills · sin IA
        </span>
        <h2 className="text-2xl leading-tight tracking-[-0.02em]">
          Comparamos {gancho.revisados} de tus CVs con las {gancho.skills} skills de la vacante.
        </h2>
        <p className="text-[14.5px] text-ink-200">
          Contamos menciones, no juzgamos experiencia.
          {notas.length > 0 && ` ${notas.join(" ")}`}
        </p>
      </div>
      <p className="flex flex-col">
        <b className="text-[2.6rem] font-extrabold leading-none tabular-nums">
          {gancho.conLaMayoria}
        </b>
        <span className="text-sm text-ink-200">mencionan la mayoría de tus skills</span>
      </p>
      <p className="flex flex-col">
        <b className="text-[2.6rem] font-extrabold leading-none text-aqua-300 tabular-nums">
          {gancho.conTodas}
        </b>
        <span className="text-sm text-ink-200">las mencionan todas</span>
      </p>
    </section>
  );
}

const plural = (n: number, uno: string, varios: string) => (n === 1 ? uno : `${n} ${varios}`);

/**
 * Cómo va la evaluación con IA de la vacante (plan de pago, ADR-021). Dice lo que
 * espera y lo que hay que revisar a mano: nada se pierde en silencio.
 */
function ResumenDeLaEvaluacion({ resumen }: { resumen: ResumenDeEvaluaciones }) {
  const notas = [
    resumen.enEspera > 0 &&
      plural(resumen.enEspera, "Una espera su evaluación.", "esperan su evaluación."),
    resumen.sinEvaluar > 0 &&
      plural(
        resumen.sinEvaluar,
        "Una no se pudo evaluar: revísala a mano.",
        "no se pudieron evaluar: revísalas a mano.",
      ),
    resumen.ilegibles > 0 &&
      plural(resumen.ilegibles, "Un CV no se pudo leer.", "CVs no se pudieron leer."),
    resumen.sinIa > 0 &&
      plural(
        resumen.sinIa,
        "Un candidato pidió no ser evaluado con IA.",
        "candidatos pidieron no ser evaluados con IA.",
      ),
  ].filter(Boolean);
  return (
    <section
      aria-label="Evaluación con IA"
      className="flex flex-col gap-2 rounded-[22px] bg-ink-900 p-6 text-white"
    >
      <span className="font-mono text-[11px] font-semibold uppercase tracking-[0.08em] text-aqua-300">
        Evaluación con IA · a ciegas
      </span>
      <h2 className="text-2xl leading-tight tracking-[-0.02em]">
        Evaluamos {resumen.evaluadas} de {resumen.aplicaciones} aplicaciones.
      </h2>
      <p className="text-[14.5px] text-ink-200">
        La IA no vio nombres ni datos de contacto. Sugiere un siguiente paso; la decisión es tuya.
        {notas.length > 0 && ` ${notas.join(" ")}`}
      </p>
    </section>
  );
}

/**
 * Descartar con motivo, el mismo formulario en los dos planes. Si la evaluó la IA,
 * la base pide el motivo (0015); si no, es opcional (0021). Al candidato no le sale
 * ningún correo.
 */
function FormularioDeDescarte({
  vacanteId,
  aplicado,
  alCerrar,
}: {
  vacanteId: string;
  aplicado: Aplicado;
  alCerrar: () => void;
}) {
  const [motivo, setMotivo] = useState("");
  const descartar = useDescartar(vacanteId);
  const sinMotivo = descartar.data?.ok === false;
  const conIa = aplicado.evaluacion !== null;

  function alDescartar(evento: FormEvent) {
    evento.preventDefault();
    descartar.mutate(
      { aplicacionId: aplicado.id, motivo },
      { onSuccess: (resultado) => resultado.ok && alCerrar() },
    );
  }

  return (
    <form
      onSubmit={alDescartar}
      aria-label={`Descartar a ${aplicado.nombre}`}
      className="mt-3 flex flex-col gap-3 rounded-2xl bg-danger-50 p-4 text-sm"
    >
      <label className="flex flex-col gap-1.5 font-bold text-danger-700">
        {conIa ? "Motivo del descarte" : "Motivo del descarte (opcional)"}
        <textarea
          required={conIa}
          minLength={10}
          maxLength={500}
          rows={3}
          value={motivo}
          onChange={(e) => setMotivo(e.target.value)}
          className="rounded-xl border-[1.5px] border-mist-200 bg-white px-3 py-2 font-normal text-ink-900"
        />
      </label>
      <span className="text-mist-700">
        {conIa
          ? "La IA solo sugiere: el descarte lo decides tú y queda con tu motivo."
          : "El motivo queda en tu panel. Al candidato no le mandamos ningún correo."}
      </span>
      {(sinMotivo || descartar.isError) && (
        <p role="alert" className="font-bold text-danger-700">
          {!sinMotivo
            ? "No pudimos guardar el descarte. Inténtalo de nuevo."
            : conIa
              ? "Escribe el motivo, de 10 a 500 caracteres."
              : "Si escribes un motivo, que tenga de 10 a 500 caracteres."}
        </p>
      )}
      <div className="flex justify-end gap-2">
        <Button type="button" variant="secondary" size="sm" onClick={alCerrar}>
          Cancelar
        </Button>
        <Button type="submit" variant="destructive" size="sm" disabled={descartar.isPending}>
          Sí, descartar
        </Button>
      </div>
    </form>
  );
}

/** Un evaluado: su score, la sugerencia, el porqué y descartar con motivo. */
function FilaEvaluada({
  vacanteId,
  aplicado,
  evaluacion,
}: {
  vacanteId: string;
  aplicado: Aplicado;
  evaluacion: EvaluacionConIa;
}) {
  const [descartando, setDescartando] = useState(false);

  return (
    <li data-aplicacion={aplicado.id} className="py-4">
      <div className="flex flex-wrap items-start gap-x-4 gap-y-2">
        <b className="text-[1.9rem] font-extrabold leading-none tabular-nums">
          {evaluacion.score.toFixed(1)}
        </b>
        <div className="min-w-0 flex-1 basis-48">
          <p className="font-bold">{aplicado.nombre}</p>
          <p className="text-sm text-mist-600">
            Sugerencia: {ETIQUETA_SIGUIENTE_PASO[evaluacion.siguientePaso]}
          </p>
        </div>
        {aplicado.cvUrl && (
          <a
            href={aplicado.cvUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm font-bold text-aqua-700 hover:underline"
          >
            CV.{aplicado.cvFormato}
          </a>
        )}
        {!descartando && (
          <Button variant="ghost" size="sm" onClick={() => setDescartando(true)}>
            Descartar
          </Button>
        )}
      </div>
      <details className="mt-2 text-[14.5px]">
        <summary className="cursor-pointer font-bold text-aqua-700">Por qué</summary>
        <p className="mt-2 text-mist-700">{evaluacion.razonamiento}</p>
        {evaluacion.fortalezas.length > 0 && (
          <p className="mt-1.5 text-mist-700">
            <b className="text-ink-900">Fortalezas:</b> {evaluacion.fortalezas.join(", ")}
          </p>
        )}
        {evaluacion.brechas.length > 0 && (
          <p className="mt-1 text-mist-700">
            <b className="text-ink-900">Le falta:</b> {evaluacion.brechas.join(", ")}
          </p>
        )}
      </details>
      {descartando && (
        <FormularioDeDescarte
          vacanteId={vacanteId}
          aplicado={aplicado}
          alCerrar={() => setDescartando(false)}
        />
      )}
    </li>
  );
}

/** Cuántos evaluados se ven antes de "Ver todos". */
const EVALUADOS_VISIBLES = 10;

/** Lo que evaluó la IA, del mejor encaje al menor. Los descartados ya no aparecen. */
function Evaluados({ vacanteId, aplicados }: { vacanteId: string; aplicados: Aplicado[] }) {
  const [todos, setTodos] = useState(false);
  const evaluados = aplicados
    .flatMap((a) => (a.evaluacion && a.estado !== "rejected" ? [{ a, e: a.evaluacion }] : []))
    .sort((x, y) => y.e.score - x.e.score);
  if (evaluados.length === 0) return null;
  const visibles = todos ? evaluados : evaluados.slice(0, EVALUADOS_VISIBLES);
  return (
    <section aria-label="Evaluados" className="rounded-[22px] border border-mist-200 bg-white p-5">
      <div className="flex items-center justify-between">
        <h2 className="text-[19px]">Evaluados</h2>
        <span className="text-[13.5px] text-mist-600">Del mejor encaje al menor</span>
      </div>
      <ul className="mt-1 flex flex-col divide-y divide-mist-150">
        {visibles.map(({ a, e }) => (
          <FilaEvaluada key={a.id} vacanteId={vacanteId} aplicado={a} evaluacion={e} />
        ))}
      </ul>
      {!todos && evaluados.length > EVALUADOS_VISIBLES && (
        <Button variant="secondary" size="sm" className="mt-3" onClick={() => setTodos(true)}>
          Ver los {evaluados.length} evaluados
        </Button>
      )}
    </section>
  );
}

/** Cómo se ve cada cierre en el pipeline. */
const ESTILO_DE_SALIDA: Partial<Record<ApplicationStatus, string>> = {
  hired: "bg-success-50 text-success-700",
  rejected: "bg-danger-50 text-danger-700",
  withdrawn: "bg-mist-100 text-mist-700",
};

type Filtro = ApplicationStatus | null;

/**
 * Cuántos candidatos hay ahora en cada etapa, y el filtro de la lista: al pulsar una
 * etapa se ven solo los suyos. Todas abiertas en los dos planes (ADR-024).
 */
function Etapas({
  pipeline,
  filtro,
  alFiltrar,
}: {
  pipeline: PipelineDeVacante;
  filtro: Filtro;
  alFiltrar: (etapa: Filtro) => void;
}) {
  const conteo = contarPorEtapa(pipeline.aplicados);
  const enProceso = ETAPAS_DEL_PIPELINE.map((e) => conteo[e]);
  const { maxAplicaciones } = pipeline;
  const filtrar = (etapa: ApplicationStatus) => alFiltrar(filtro === etapa ? null : etapa);

  return (
    <section
      aria-label="Pipeline"
      className="flex flex-col gap-2 rounded-[22px] border border-mist-200 bg-white p-5"
    >
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-[19px]">Pipeline</h2>
        <span className="text-[12.5px] text-mist-600">Pulsa una etapa para filtrar</span>
      </div>
      {ETAPAS_DEL_PIPELINE.map((etapa) => (
        <button
          key={etapa}
          type="button"
          data-etapa={etapa}
          aria-pressed={filtro === etapa}
          onClick={() => filtrar(etapa)}
          className={cn(
            "-mx-2 flex flex-col gap-1.5 rounded-xl px-2 py-1.5 text-left transition-colors hover:bg-mist-50",
            filtro === etapa && "bg-aqua-50 ring-1 ring-inset ring-aqua-200",
          )}
        >
          <span className="flex w-full justify-between text-sm font-semibold">
            <span>{ETIQUETA_ESTADO_APLICACION[etapa]}</span>
            <b className="tabular-nums">{conteo[etapa]}</b>
          </span>
          <span className="block h-2.5 w-full rounded-full bg-mist-100" aria-hidden="true">
            <span
              className={`block h-full rounded-full ${BARRA_DE_ETAPA[etapa]}`}
              style={{ width: `${anchoRelativo(conteo[etapa], enProceso)}%` }}
            />
          </span>
        </button>
      ))}
      <div className="mt-1 flex flex-wrap gap-2 border-t border-mist-150 pt-3">
        {salidasVisibles(conteo).map((etapa) => (
          <button
            key={etapa}
            type="button"
            data-etapa={etapa}
            aria-pressed={filtro === etapa}
            onClick={() => filtrar(etapa)}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-sm font-bold",
              ESTILO_DE_SALIDA[etapa],
              filtro === etapa && "ring-2 ring-ink-900",
            )}
          >
            {ETIQUETA_ESTADO_APLICACION[etapa]}
            <span className="tabular-nums">{conteo[etapa]}</span>
          </button>
        ))}
      </div>
      {maxAplicaciones && (
        <>
          <p className="text-[12.5px] text-mist-600">
            Recibidas: {pipeline.vacante.aplicaciones} de {maxAplicaciones}. Al llegar a{" "}
            {maxAplicaciones}, la vacante deja de recibir aplicaciones; mover o descartar no libera
            lugares.
          </p>
          <EscribenosParaMas
            pregunta={`¿Necesitas recibir más de ${maxAplicaciones} CVs o hacer un reclutamiento masivo?`}
            asunto={`Quiero recibir más de ${maxAplicaciones} CVs: ${pipeline.vacante.titulo}`}
            className="text-[12.5px]"
          />
        </>
      )}
    </section>
  );
}

/**
 * Un candidato con su CV y su etapa, que la empresa cambia a mano (ADR-024). Pasar a
 * "Descartados" abre el formulario del motivo; las demás etapas se guardan al elegirlas.
 */
function FilaDeCandidato({ vacanteId, aplicado }: { vacanteId: string; aplicado: Aplicado }) {
  const [descartando, setDescartando] = useState(false);
  const mover = useMoverDeEtapa(vacanteId);

  function alElegir(etapa: ApplicationStatus) {
    if (etapa === "rejected") {
      setDescartando(true);
      return;
    }
    setDescartando(false);
    mover.mutate({ aplicacionId: aplicado.id, etapa });
  }

  return (
    <li data-aplicacion={aplicado.id} data-etapa={aplicado.estado} className="py-3">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <div className="min-w-0 flex-1 basis-44">
          <p className="font-bold">{aplicado.nombre}</p>
          <p className="text-[13.5px] text-mist-600">
            {cuandoAplico(aplicado.aplicoEn)} ·{" "}
            {aplicado.cvFormato === null ? (
              <span className="text-mist-500">Sin CV</span>
            ) : aplicado.cvUrl ? (
              <a
                href={aplicado.cvUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="font-bold text-aqua-700 hover:underline"
              >
                CV.{aplicado.cvFormato}
              </a>
            ) : (
              <span className="text-mist-500">CV.{aplicado.cvFormato}</span>
            )}
          </p>
        </div>
        <select
          aria-label={`Etapa de ${aplicado.nombre}`}
          value={aplicado.estado}
          onChange={(e) => alElegir(e.target.value as ApplicationStatus)}
          className="h-9 w-[12rem] max-w-full rounded-full border-[1.5px] border-mist-200 bg-white py-0 pl-3 pr-9 text-sm font-bold text-ink-900"
        >
          {TODAS_LAS_ETAPAS.map((etapa) => (
            <option key={etapa} value={etapa}>
              {ETIQUETA_ESTADO_APLICACION[etapa]}
            </option>
          ))}
        </select>
      </div>
      {mover.isError && (
        <p role="alert" className="mt-2 text-sm font-bold text-danger-700">
          No pudimos cambiarle la etapa. Inténtalo de nuevo.
        </p>
      )}
      {descartando && (
        <FormularioDeDescarte
          vacanteId={vacanteId}
          aplicado={aplicado}
          alCerrar={() => setDescartando(false)}
        />
      )}
    </li>
  );
}

/** Los candidatos de la vacante, todos o los de una etapa, los más recientes primero. */
function Candidatos({
  pipeline,
  filtro,
  alFiltrar,
}: {
  pipeline: PipelineDeVacante;
  filtro: Filtro;
  alFiltrar: (etapa: Filtro) => void;
}) {
  const [todos, setTodos] = useState(false);
  const { vacante, aplicados } = pipeline;
  const lista = deLaEtapa(aplicados, filtro);
  const visibles = todos ? lista : lista.slice(0, CANDIDATOS_VISIBLES);

  return (
    <section aria-label="Candidatos" className="rounded-[22px] border border-mist-200 bg-white p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-[19px]">
          {filtro ? ETIQUETA_ESTADO_APLICACION[filtro] : "Candidatos"}
          <span className="ml-2 text-[15px] font-semibold text-mist-600 tabular-nums">
            {lista.length}
          </span>
        </h2>
        {filtro ? (
          <Button variant="link" size="sm" onClick={() => alFiltrar(null)}>
            Ver todos
          </Button>
        ) : (
          <span className="text-[13.5px] text-mist-600">Más recientes primero</span>
        )}
      </div>
      {aplicados.length === 0 ? (
        <p className="py-6 text-sm text-mist-600">{sinAplicaciones(vacante.moderacion)}</p>
      ) : lista.length === 0 ? (
        <p className="py-6 text-sm text-mist-600">Nadie en esta etapa por ahora.</p>
      ) : (
        <ul className="mt-1 flex flex-col divide-y divide-mist-150">
          {visibles.map((a) => (
            <FilaDeCandidato key={a.id} vacanteId={vacante.id} aplicado={a} />
          ))}
        </ul>
      )}
      {!todos && lista.length > CANDIDATOS_VISIBLES && (
        <Button variant="secondary" size="sm" className="mt-3" onClick={() => setTodos(true)}>
          Ver los {lista.length}
        </Button>
      )}
    </section>
  );
}

/**
 * Los candidatos de una vacante por etapa, con la descarga de todos sus CVs. En los
 * dos planes la empresa los mueve a mano entre todas las etapas (ADR-024).
 */
export function Pipeline({ vacanteId }: { vacanteId: string }) {
  const { data: pipeline, isPending, dataUpdatedAt } = usePipeline(vacanteId);
  useMarcarPostulacionesVistas(vacanteId, pipeline ? dataUpdatedAt : 0);
  const descarga = useDescargarCvs();
  const [filtro, setFiltro] = useState<Filtro>(null);

  if (isPending) return null;
  if (!pipeline) {
    return (
      <section className="max-w-xl rounded-[22px] border border-mist-200 bg-white p-6">
        <h1 className="text-2xl">No encontramos esta vacante</h1>
        <p className="mt-2 text-mist-700">Puede que se haya eliminado.</p>
        <Enlace href="/vacantes" className={`${buttonVariants({ variant: "ink" })} mt-5`}>
          Ir a Mis vacantes
        </Enlace>
      </section>
    );
  }

  const { vacante, aplicados } = pipeline;
  const tope = pipeline.maxAplicaciones ? ` de ${pipeline.maxAplicaciones}` : "";
  const conCv = aplicados.filter((a) => a.cvFormato !== null).length;

  function descargar() {
    descarga.mutate(vacante.id, {
      onSuccess: (resultado) => {
        if (resultado.url) bajarArchivo(resultado.url, resultado.nombre);
      },
    });
  }

  return (
    <>
      <Encabezado
        etiqueta={`Publicada ${haceCuanto(vacante.publicadaEn).toLowerCase()} · ${vacante.aplicaciones}${tope} aplicaciones`}
        titulo={vacante.titulo}
        accion={
          conCv > 0 && (
            <Button variant="secondary" disabled={descarga.isPending} onClick={descargar}>
              <Download aria-hidden="true" className="h-4 w-4" />
              {descarga.isPending
                ? "Armando el .zip…"
                : `Descargar ${conCv === 1 ? "el CV" : `los ${conCv} CVs`} (.zip)`}
            </Button>
          )
        }
      />
      <AvisoDeModeracion moderacion={vacante.moderacion} motivos={vacante.motivos} />
      <p aria-live="polite" className="text-sm text-mist-600 empty:hidden">
        {descarga.isError
          ? "No pudimos armar el .zip. Inténtalo de nuevo."
          : descarga.data && !descarga.isPending
            ? mensajeDeLaDescarga(descarga.data)
            : ""}
      </p>
      {pipeline.gancho && <Gancho gancho={pipeline.gancho} />}
      {pipeline.evaluaciones && <ResumenDeLaEvaluacion resumen={pipeline.evaluaciones} />}
      {pipeline.evaluaciones && <Evaluados vacanteId={vacante.id} aplicados={aplicados} />}
      <div className="grid items-start gap-5 lg:grid-cols-[minmax(280px,1fr)_minmax(0,1.6fr)]">
        <Etapas pipeline={pipeline} filtro={filtro} alFiltrar={setFiltro} />
        <Candidatos pipeline={pipeline} filtro={filtro} alFiltrar={setFiltro} />
      </div>
    </>
  );
}
