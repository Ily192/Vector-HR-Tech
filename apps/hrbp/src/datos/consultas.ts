/**
 * Las pantallas piden datos solo por aquí: TanStack Query guarda en caché lo que
 * devuelve `panel.ts` y, tras publicar o eliminar, invalida lo que cambió.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";

import { obtenerResumenCockpit } from "../cockpit/resumen";
import {
  alCambiarLaSesion,
  descartar,
  eliminarVacante,
  entrar,
  listarMisVacantes,
  obtenerPipeline,
  obtenerSesion,
  publicarVacante,
  registrarInteres,
  salir,
  solicitarDescargaDeCvs,
} from "./panel";
import { SinAccesoAlPanel } from "./tipos";

const CLAVES = {
  sesion: ["sesion"],
  misVacantes: ["mis-vacantes"],
  pipeline: (id: string) => ["pipeline", id],
  cockpit: ["cockpit"],
} as const;

export const useSesion = () =>
  useQuery({
    queryKey: CLAVES.sesion,
    queryFn: obtenerSesion,
    // Una cuenta sin acceso no lo gana reintentando.
    retry: (fallos, error) => !(error instanceof SinAccesoAlPanel) && fallos < 1,
  });

/**
 * Cuando entra o sale alguien, olvida lo que había en caché: así nunca se ven
 * datos de la cuenta anterior. Se monta una vez, en `App`.
 */
export function useSesionEnVivo() {
  const cliente = useQueryClient();
  useEffect(
    () =>
      alCambiarLaSesion(() => {
        cliente.removeQueries({ predicate: (q) => q.queryKey[0] !== CLAVES.sesion[0] });
        void cliente.resetQueries({ queryKey: CLAVES.sesion });
      }),
    [cliente],
  );
}

export const useMisVacantes = () =>
  useQuery({ queryKey: CLAVES.misVacantes, queryFn: listarMisVacantes });

export const usePipeline = (vacanteId: string) =>
  useQuery({ queryKey: CLAVES.pipeline(vacanteId), queryFn: () => obtenerPipeline(vacanteId) });

export const useResumenCockpit = () =>
  useQuery({ queryKey: CLAVES.cockpit, queryFn: obtenerResumenCockpit });

export function usePublicarVacante() {
  const cliente = useQueryClient();
  return useMutation({
    mutationFn: publicarVacante,
    onSuccess: () => cliente.invalidateQueries({ queryKey: CLAVES.misVacantes }),
  });
}

export function useEliminarVacante() {
  const cliente = useQueryClient();
  return useMutation({
    mutationFn: eliminarVacante,
    onSuccess: () => cliente.invalidateQueries({ queryKey: CLAVES.misVacantes }),
  });
}

/** Descartar con motivo; al guardarse, el pipeline de la vacante se vuelve a pedir. */
export function useDescartar(vacanteId: string) {
  const cliente = useQueryClient();
  return useMutation({
    mutationFn: ({ aplicacionId, motivo }: { aplicacionId: string; motivo: string }) =>
      descartar(aplicacionId, motivo),
    onSuccess: (resultado) => {
      if (resultado.ok) void cliente.invalidateQueries({ queryKey: CLAVES.pipeline(vacanteId) });
    },
  });
}

export const useDescargarCvs = () => useMutation({ mutationFn: solicitarDescargaDeCvs });

export const useRegistrarInteres = () => useMutation({ mutationFn: registrarInteres });

export const useEntrar = () => useMutation({ mutationFn: entrar });

export const useSalir = () => useMutation({ mutationFn: salir });
