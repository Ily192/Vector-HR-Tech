import { ETIQUETA_MODALIDAD } from "@vortex/types/etiquetas";
import { Badge, Button, buttonVariants, cn, haceCuanto } from "@vortex/ui";
import { Plus } from "lucide-react";
import { useState } from "react";

import { useEliminarVacante, useMisVacantes } from "../datos/consultas";
import type { CupoDeVacantes, VacanteDeLaEmpresa } from "../datos/tipos";
import { Encabezado } from "../marco/marco";
import { Enlace } from "../navegacion/ruta";

function FilaDeVacante({ v, cupo }: { v: VacanteDeLaEmpresa; cupo: CupoDeVacantes }) {
  const [confirmando, setConfirmando] = useState(false);
  const eliminar = useEliminarVacante();
  const max = cupo.maxAplicacionesPorVacante;

  return (
    <li data-vacante={v.id} className="rounded-[22px] border border-mist-200 bg-white p-5">
      <div className="flex flex-wrap items-start gap-x-5 gap-y-3">
        <div className="min-w-0 flex-1 basis-64">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-lg font-extrabold tracking-[-0.01em]">{v.titulo}</h2>
            {v.cupoCompleto && <Badge variant="warning">Cupo completo</Badge>}
          </div>
          <p className="mt-1 text-sm text-mist-600">
            {v.ubicacion} · {ETIQUETA_MODALIDAD[v.modalidad]} · {haceCuanto(v.publicadaEn)}
          </p>
        </div>
        <div className="w-44">
          <p className="text-sm font-bold tabular-nums">
            {v.aplicaciones} de {max} aplicaciones
          </p>
          <div className="mt-1.5 h-1.5 rounded-full bg-mist-100" aria-hidden="true">
            <div
              className={`h-full rounded-full ${v.cupoCompleto ? "bg-flame-500" : "bg-aqua-300"}`}
              style={{ width: `${Math.min(100, (v.aplicaciones / max) * 100)}%` }}
            />
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Enlace
            href={`/vacantes/${v.id}`}
            className={cn(buttonVariants({ variant: "secondary", size: "sm" }))}
          >
            Ver aplicados
          </Enlace>
          {!confirmando && (
            <Button variant="ghost" size="sm" onClick={() => setConfirmando(true)}>
              Eliminar
            </Button>
          )}
        </div>
      </div>
      {confirmando && (
        <div
          role="alertdialog"
          aria-label={`Eliminar ${v.titulo}`}
          className="mt-4 flex flex-wrap items-center gap-3 rounded-2xl bg-danger-50 p-4 text-sm"
        >
          <p className="flex-1 basis-64 text-danger-700">
            <b>¿Eliminar «{v.titulo}»?</b> Deja de aparecer en el career site y libera un cupo. Las
            aplicaciones que recibió no se recuperan desde el panel.
          </p>
          <Button variant="secondary" size="sm" onClick={() => setConfirmando(false)}>
            Cancelar
          </Button>
          <Button
            variant="destructive"
            size="sm"
            disabled={eliminar.isPending}
            onClick={() => eliminar.mutate(v.id)}
          >
            Sí, eliminar
          </Button>
        </div>
      )}
    </li>
  );
}

/** Las vacantes activas de la empresa y cuántos cupos le quedan. */
export function MisVacantes() {
  const { data } = useMisVacantes();
  if (!data) return null;
  const { vacantes, cupo } = data;

  return (
    <>
      <Encabezado
        etiqueta={`${cupo.activas} de ${cupo.limite} vacantes activas`}
        titulo={
          <>
            Mis <i>vacantes</i>
          </>
        }
        accion={
          cupo.libres > 0 && (
            <Enlace href="/vacantes/nueva" className={buttonVariants()}>
              <Plus aria-hidden="true" className="h-4 w-4" />
              Crear empleo
            </Enlace>
          )
        }
      />
      {cupo.libres === 0 && (
        <output className="block rounded-2xl bg-flame-50 p-4 text-sm text-flame-700">
          Tienes las {cupo.limite} vacantes de tu plan activas. Para publicar otra, elimina una.
        </output>
      )}
      {vacantes.length === 0 ? (
        <div className="rounded-[22px] border border-dashed border-mist-300 bg-white p-10 text-center">
          <h2 className="text-lg font-extrabold">Aún no publicas vacantes</h2>
          <p className="mt-1 text-sm text-mist-600">
            Tu plan incluye {cupo.limite} vacantes activas en el career site, sin costo.
          </p>
        </div>
      ) : (
        <ul className="flex flex-col gap-3">
          {vacantes.map((v) => (
            <FilaDeVacante key={v.id} v={v} cupo={cupo} />
          ))}
        </ul>
      )}
    </>
  );
}
