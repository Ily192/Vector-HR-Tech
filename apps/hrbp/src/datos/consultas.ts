/**
 * Las pantallas piden datos solo por aquí: TanStack Query guarda en caché lo que
 * devuelve `panel.ts` y, tras publicar o eliminar, invalida lo que cambió.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { obtenerResumenCockpit } from "../cockpit/resumen";
import {
  eliminarVacante,
  listarMisVacantes,
  obtenerPipeline,
  obtenerSesion,
  publicarVacante,
  registrarInteres,
  solicitarDescargaDeCvs,
} from "./panel";

const CLAVES = {
  sesion: ["sesion"],
  misVacantes: ["mis-vacantes"],
  pipeline: (id: string) => ["pipeline", id],
  cockpit: ["cockpit"],
} as const;

export const useSesion = () => useQuery({ queryKey: CLAVES.sesion, queryFn: obtenerSesion });

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

export const useDescargarCvs = () => useMutation({ mutationFn: solicitarDescargaDeCvs });

export const useRegistrarInteres = () => useMutation({ mutationFn: registrarInteres });
