/**
 * Las pantallas piden datos solo por aquí: TanStack Query guarda en caché lo que
 * devuelve `panel.ts` y, tras publicar o eliminar, invalida lo que cambió.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";

import {
  type VacanteEnRevision,
  aprobarVacante,
  obtenerAccesoAdmin,
  obtenerColaAdmin,
  obtenerMetricasWeb,
  obtenerResumenAdmin,
  rechazarVacante,
} from "./admin";
import {
  alCambiarLaSesion,
  descartar,
  eliminarVacante,
  entrar,
  listarMisVacantes,
  marcarPostulacionesVistas,
  obtenerPipeline,
  obtenerResumenCockpit,
  obtenerSesion,
  publicarVacante,
  registrarInteres,
  salir,
  solicitarDescargaDeCvs,
  verificarCodigo,
} from "./panel";
import { SinAccesoAlPanel } from "./tipos";

const CLAVES = {
  sesion: ["sesion"],
  misVacantes: ["mis-vacantes"],
  pipeline: (id: string) => ["pipeline", id],
  cockpit: ["cockpit"],
  admin: ["admin", "acceso"],
  resumenAdmin: ["admin", "resumen"],
  metricasWeb: ["admin", "web"],
  colaAdmin: ["admin", "cola"],
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

/**
 * Cada vez que llegan las postulaciones de la vacante a la pantalla, la base anota
 * que la empresa las vio (0020, ADR-023): así el recordatorio de postulados sin
 * revisar no le avisa de lo que ya revisó. `cargadaEn` es el `dataUpdatedAt` de la
 * consulta, o 0 si todavía no hay datos. Si falla, la pantalla sigue igual: lo peor
 * es un recordatorio de más.
 */
export function useMarcarPostulacionesVistas(vacanteId: string, cargadaEn: number) {
  useEffect(() => {
    if (cargadaEn > 0) void marcarPostulacionesVistas(vacanteId).catch(() => {});
  }, [vacanteId, cargadaEn]);
}

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

export const useVerificarCodigo = () =>
  useMutation({
    mutationFn: ({ correo, codigo }: { correo: string; codigo: string }) =>
      verificarCodigo(correo, codigo),
  });

export const useSalir = () => useMutation({ mutationFn: salir });

/**
 * Si la sesión es de admin (ADR-022, 2026-11-17). Una sola vez por sesión: la comparten
 * el enlace "Admin" del menú y la pantalla. Al cambiar la sesión, `useSesionEnVivo` la
 * borra con todo lo demás.
 */
export const useAccesoAdmin = () =>
  useQuery({
    queryKey: CLAVES.admin,
    queryFn: obtenerAccesoAdmin,
    staleTime: Number.POSITIVE_INFINITY,
    retry: false,
  });

// Las tres solo se piden con `useAccesoAdmin` en "admin": las monta el tablero.
export const useResumenAdmin = () =>
  useQuery({ queryKey: CLAVES.resumenAdmin, queryFn: obtenerResumenAdmin });

/** De la web: si falla, el tablero sigue con lo del panel. Sin reintentos. */
export const useMetricasWeb = () =>
  useQuery({ queryKey: CLAVES.metricasWeb, queryFn: obtenerMetricasWeb, retry: false });

export const useColaAdmin = () =>
  useQuery({ queryKey: CLAVES.colaAdmin, queryFn: obtenerColaAdmin });

/**
 * Aprobar o rechazar una vacante de la cola. Si se guardó, o si ya estaba resuelta
 * (409), la tarjeta sale de la lista sin esperar a pedirla de nuevo, y los conteos se
 * vuelven a pedir.
 */
export function useResolverVacante() {
  const cliente = useQueryClient();
  return useMutation({
    mutationFn: (
      pedido:
        | { vacanteId: string; accion: "aprobar" }
        | {
            vacanteId: string;
            accion: "rechazar";
            motivo: string;
          },
    ) =>
      pedido.accion === "aprobar"
        ? aprobarVacante(pedido.vacanteId)
        : rechazarVacante(pedido.vacanteId, pedido.motivo),
    onSuccess: (resultado, { vacanteId }) => {
      if (!resultado.ok && resultado.motivo !== "ya-resuelta") return;
      cliente.setQueryData<VacanteEnRevision[]>(CLAVES.colaAdmin, (cola) =>
        cola?.filter((v) => v.id !== vacanteId),
      );
      void cliente.invalidateQueries({ queryKey: CLAVES.resumenAdmin });
    },
  });
}
