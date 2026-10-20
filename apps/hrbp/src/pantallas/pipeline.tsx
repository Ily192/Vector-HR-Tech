import { ETIQUETA_ESTADO_APLICACION } from "@vortex/types/etiquetas";
import { Button, buttonVariants, haceCuanto } from "@vortex/ui";
import { Download, Lock } from "lucide-react";

import { anchoRelativo } from "../cockpit/embudo";
import { useDescargarCvs, usePipeline, useRegistrarInteres } from "../datos/consultas";
import type { DescargaDeCvs, GanchoDelPipeline, PipelineDeVacante } from "../datos/tipos";
import { Encabezado } from "../marco/marco";
import { Enlace } from "../navegacion/ruta";

/** Cuántos aplicados se listan antes de "Ver todos". */
const APLICADOS_VISIBLES = 8;

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
 * menciones, no juzga experiencia (ADR-019).
 */
function Gancho({ gancho }: { gancho: GanchoDelPipeline }) {
  const interes = useRegistrarInteres();
  if (gancho.skills === 0 || gancho.revisados === 0) {
    return (
      <section
        aria-label="Coincidencia de skills"
        className="rounded-[22px] border border-mist-200 bg-white p-5 text-[14.5px] text-mist-700"
      >
        {gancho.skills === 0
          ? "Esta vacante no pide skills, así que no hay CVs que contar. Agrégalas al crear la próxima y te decimos cuántos CVs las mencionan."
          : `Revisamos los CVs de 5 en 5 contra las ${gancho.skills} skills de la vacante. Con los primeros 5 te decimos cuántos las mencionan.`}
      </section>
    );
  }
  const notas = [
    gancho.enEspera > 0 &&
      (gancho.enEspera === 1 ? "Falta 1 por revisar." : `Faltan ${gancho.enEspera} por revisar.`),
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
          Revisamos {gancho.revisados} de tus CVs contra las {gancho.skills} skills de la vacante.
        </h2>
        <p className="text-[14.5px] text-ink-200">
          Contamos menciones, no juzgamos experiencia. Con los servicios de IA ves quiénes son,
          ordenados por encaje y con el porqué de cada uno.
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
      {interes.isSuccess ? (
        <output className="block text-sm font-bold text-aqua-300">
          Listo. Tu contacto en Vector HR te escribe pronto.
        </output>
      ) : (
        <div className="flex flex-col gap-2">
          <Button disabled={interes.isPending} onClick={() => interes.mutate("pipeline")}>
            Evaluarlos con IA
          </Button>
          {interes.isError && (
            <p role="alert" className="text-sm font-bold text-flame-300">
              No pudimos avisar a Vector HR. Inténtalo de nuevo.
            </p>
          )}
        </div>
      )}
    </section>
  );
}

function Etapas({ pipeline }: { pipeline: PipelineDeVacante }) {
  const habilitadas = pipeline.etapas.flatMap((e) => (e.conteo === null ? [] : [e.conteo]));
  return (
    <section
      aria-label="Pipeline"
      className="flex flex-col gap-3.5 rounded-[22px] border border-mist-200 bg-white p-5"
    >
      <h2 className="text-[19px]">Pipeline</h2>
      {pipeline.etapas.map(({ etapa, conteo }) => (
        <div
          key={etapa}
          data-etapa={etapa}
          className={`flex flex-col gap-1.5 ${conteo === null ? "opacity-60" : ""}`}
        >
          <div className="flex justify-between text-sm font-semibold">
            <span>{ETIQUETA_ESTADO_APLICACION[etapa]}</span>
            {conteo === null ? (
              <span className="inline-flex items-center gap-1 text-xs font-bold text-mist-600">
                <Lock aria-hidden="true" className="h-3 w-3" />
                Servicios IA
              </span>
            ) : (
              <b className="tabular-nums">{conteo}</b>
            )}
          </div>
          <div className="h-2.5 rounded-full bg-mist-100" aria-hidden="true">
            {conteo !== null && (
              <div
                className="h-full rounded-full bg-aqua-300"
                style={{
                  width: `${
                    pipeline.maxAplicaciones && etapa === "applied"
                      ? (conteo / pipeline.maxAplicaciones) * 100
                      : anchoRelativo(conteo, habilitadas)
                  }%`,
                }}
              />
            )}
          </div>
          {etapa === "applied" && pipeline.maxAplicaciones && (
            <span className="text-[12.5px] text-mist-600">
              Al llegar a {pipeline.maxAplicaciones}, la vacante deja de recibir aplicaciones.
            </span>
          )}
        </div>
      ))}
    </section>
  );
}

/** Los aplicados de una vacante, con la descarga de todos sus CVs. */
export function Pipeline({ vacanteId }: { vacanteId: string }) {
  const { data: pipeline, isPending } = usePipeline(vacanteId);
  const descarga = useDescargarCvs();

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
      <p aria-live="polite" className="text-sm text-mist-600 empty:hidden">
        {descarga.isError
          ? "No pudimos armar el .zip. Inténtalo de nuevo."
          : descarga.data && !descarga.isPending
            ? mensajeDeLaDescarga(descarga.data)
            : ""}
      </p>
      {pipeline.gancho && <Gancho gancho={pipeline.gancho} />}
      <div className="grid items-start gap-5 lg:grid-cols-[minmax(280px,1fr)_minmax(0,1.6fr)]">
        <Etapas pipeline={pipeline} />
        <section
          aria-label="Aplicados"
          className="rounded-[22px] border border-mist-200 bg-white p-5"
        >
          <div className="flex items-center justify-between">
            <h2 className="text-[19px]">Aplicados</h2>
            <span className="text-[13.5px] text-mist-600">Más recientes primero</span>
          </div>
          {aplicados.length === 0 ? (
            <p className="py-6 text-sm text-mist-600">
              Todavía no hay aplicaciones. La vacante ya está en el career site.
            </p>
          ) : (
            <table className="mt-2 w-full border-collapse text-[14.5px]">
              <thead>
                <tr className="text-left text-[12.5px] text-mist-600">
                  <th scope="col" className="py-2 font-bold">
                    Candidato
                  </th>
                  <th scope="col" className="py-2 font-bold">
                    Aplicó
                  </th>
                  <th scope="col" className="py-2 font-bold">
                    CV
                  </th>
                </tr>
              </thead>
              <tbody>
                {aplicados.slice(0, APLICADOS_VISIBLES).map((a) => (
                  <tr key={a.id} className="border-t border-mist-150">
                    <td className="py-3 font-bold">{a.nombre}</td>
                    <td className="py-3 text-mist-600">{cuandoAplico(a.aplicoEn)}</td>
                    <td className="py-3">
                      {a.cvFormato === null ? (
                        <span className="text-mist-500">Sin CV</span>
                      ) : a.cvUrl ? (
                        <a
                          href={a.cvUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="font-bold text-aqua-700 hover:underline"
                        >
                          CV.{a.cvFormato}
                        </a>
                      ) : (
                        <span className="text-mist-500">CV.{a.cvFormato}</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {aplicados.length > APLICADOS_VISIBLES && (
            <p className="mt-3 text-sm text-mist-600">
              Y {aplicados.length - APLICADOS_VISIBLES} más en el .zip.
            </p>
          )}
        </section>
      </div>
    </>
  );
}
