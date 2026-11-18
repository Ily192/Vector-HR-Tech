/**
 * El área de admin de Vector HR (`/admin`; ADR-022, enmienda del 2026-11-17): las
 * métricas de la plataforma y la cola de revisión de vacantes, también desde el teléfono.
 *
 * Habla con el hr-engine (`/admin/*`), que en producción está detrás del mismo dominio
 * que Supabase (api.vectorhrtech.com, por Caddy), con la sesión del panel como Bearer.
 * Quién entra lo decide el hr-engine (`ADMIN_CORREOS`): aquí no hay ninguna lista, y un
 * 200 que no sea el JSON esperado no da acceso. Las métricas de la web vienen de
 * vectorhrtech.com con el mismo token; si fallan, el tablero sigue con las del panel.
 */
import type { Moderacion, MotivoDeModeracion } from "@fluveai/types/hr";

import { tokenDeAcceso } from "./panel";

const API = (import.meta.env.VITE_ADMIN_API_URL || import.meta.env.VITE_SUPABASE_URL || "").replace(
  /\/+$/,
  "",
);

/** Lo construye la web (otro repo). `VITE_WEB_METRICAS_URL` lo cambia. */
export const URL_DE_METRICAS_WEB =
  import.meta.env.VITE_WEB_METRICAS_URL || "https://vectorhrtech.com/api/admin/metricas";

/** Lo que dijo el hr-engine de la sesión. */
export type AccesoAdmin =
  | { estado: "admin"; correo: string }
  /** Entró, pero su correo no está en `ADMIN_CORREOS` (403). */
  | { estado: "sin-acceso" }
  /** Sin sesión, o una que el hr-engine no reconoce (401). */
  | { estado: "sin-sesion" };

export interface ConteoConSemana {
  total: number;
  ultimos7: number;
}

export interface ResumenAdmin {
  empresas: { total: number; altasWebConfirmadas: number; verificadas: number };
  /** `porModeracion` cuenta las abiertas: lo que está o no en la bolsa de empleo. */
  vacantes: { porModeracion: Record<Moderacion, number>; abiertas: number; cerradas: number };
  aplicaciones: ConteoConSemana;
  altas: { ultimos7: number };
}

export interface CampanaDeLaWeb {
  origen: string | null;
  medio: string | null;
  campana: string | null;
  n: number;
}

export interface MetricasWeb {
  registros: ConteoConSemana & { altaFallida: number; porCampana: CampanaDeLaWeb[] };
  diagnosticos: ConteoConSemana;
  listaEspera: ConteoConSemana;
}

export interface VacanteEnRevision {
  id: string;
  titulo: string;
  empresa: string;
  /** Reclutador(a) independiente: nunca lleva la insignia (ADR-022). */
  publicaParaClientes: boolean;
  verificada: boolean;
  web: string | null;
  linkedin: string | null;
  estado: Moderacion;
  motivos: MotivoDeModeracion[];
  descripcion: string;
  creadaEn: string | null;
}

export type ResultadoDeRevision =
  | { ok: true }
  | {
      ok: false;
      motivo: "ya-resuelta" | "sin-sesion" | "sin-acceso" | "falta-motivo" | "error";
      /** Con "ya-resuelta": en qué estado quedó, o `null` si ya no existe. */
      estado?: Moderacion | null;
    };

/** Una consulta del admin que no salió: `estado` es el HTTP, o 0 sin respuesta. */
export class ErrorDeAdmin extends Error {
  constructor(readonly estado: number) {
    super(`el área de admin respondió ${estado}`);
    this.name = "ErrorDeAdmin";
  }
}

type Json = Record<string, unknown>;

const esObjeto = (valor: unknown): valor is Json =>
  typeof valor === "object" && valor !== null && !Array.isArray(valor);

function numero(valor: unknown): number {
  if (typeof valor !== "number" || !Number.isFinite(valor)) throw new ErrorDeAdmin(200);
  return valor;
}

function objeto(valor: unknown): Json {
  if (!esObjeto(valor)) throw new ErrorDeAdmin(200);
  return valor;
}

const texto = (valor: unknown): string | null => (typeof valor === "string" ? valor : null);

const conSemana = (valor: unknown, semana = "ultimos7"): ConteoConSemana => {
  const o = objeto(valor);
  return { total: numero(o.total), ultimos7: numero(o[semana]) };
};

async function pedir(url: string, init: RequestInit = {}): Promise<Response> {
  const token = await tokenDeAcceso();
  if (!token) throw new ErrorDeAdmin(401);
  try {
    return await fetch(url, {
      ...init,
      cache: "no-store",
      headers: {
        Authorization: `Bearer ${token}`,
        ...(init.body ? { "Content-Type": "application/json" } : {}),
      },
    });
  } catch {
    throw new ErrorDeAdmin(0);
  }
}

/** El JSON de una respuesta 2xx; cualquier otra cosa es un `ErrorDeAdmin`. */
async function json(respuesta: Response): Promise<unknown> {
  if (!respuesta.ok) throw new ErrorDeAdmin(respuesta.status);
  try {
    return await respuesta.json();
  } catch {
    // Un 200 en HTML (por ejemplo, la SPA en vez del hr-engine) no es una respuesta.
    throw new ErrorDeAdmin(respuesta.status);
  }
}

/** Sin sesión no se llama a nadie. 401 y 403 son respuestas, no errores. */
export async function obtenerAccesoAdmin(): Promise<AccesoAdmin> {
  let respuesta: Response;
  try {
    respuesta = await pedir(`${API}/admin/yo`);
  } catch (error) {
    if (error instanceof ErrorDeAdmin && error.estado === 401) return { estado: "sin-sesion" };
    throw error;
  }
  if (respuesta.status === 401) return { estado: "sin-sesion" };
  if (respuesta.status === 403) return { estado: "sin-acceso" };
  const cuerpo = objeto(await json(respuesta));
  const correo = texto(cuerpo.correo);
  if (!correo) throw new ErrorDeAdmin(respuesta.status);
  return { estado: "admin", correo };
}

export async function obtenerResumenAdmin(): Promise<ResumenAdmin> {
  const r = objeto(await json(await pedir(`${API}/admin/resumen`)));
  const empresas = objeto(r.empresas);
  const vacantes = objeto(r.vacantes);
  const porModeracion = objeto(vacantes.por_moderacion);
  return {
    empresas: {
      total: numero(empresas.total),
      altasWebConfirmadas: numero(empresas.altas_web_confirmadas),
      verificadas: numero(empresas.verificadas),
    },
    vacantes: {
      porModeracion: {
        pendiente: numero(porModeracion.pendiente),
        en_revision: numero(porModeracion.en_revision),
        publicada: numero(porModeracion.publicada),
        rechazada: numero(porModeracion.rechazada),
        oculta: numero(porModeracion.oculta),
      },
      abiertas: numero(vacantes.abiertas),
      cerradas: numero(vacantes.cerradas),
    },
    aplicaciones: conSemana(r.aplicaciones, "ultimos_7_dias"),
    altas: { ultimos7: numero(objeto(r.altas).ultimos_7_dias) },
  };
}

/** De la web (otro repo): `{ registros, diagnosticos, listaEspera }`, en camelCase. */
export async function obtenerMetricasWeb(): Promise<MetricasWeb> {
  const r = objeto(await json(await pedir(URL_DE_METRICAS_WEB)));
  const registros = objeto(r.registros);
  const porCampana = Array.isArray(registros.porCampana) ? registros.porCampana : [];
  return {
    registros: {
      ...conSemana(registros),
      altaFallida: numero(registros.altaFallida),
      porCampana: porCampana.map((c) => {
        const o = objeto(c);
        return {
          origen: texto(o.origen),
          medio: texto(o.medio),
          campana: texto(o.campana),
          n: numero(o.n),
        };
      }),
    },
    diagnosticos: conSemana(r.diagnosticos),
    listaEspera: conSemana(r.listaEspera),
  };
}

const MODERACIONES: readonly Moderacion[] = [
  "pendiente",
  "publicada",
  "en_revision",
  "rechazada",
  "oculta",
];
const GRAVEDADES = ["baja", "media", "alta"] as const;

const moderacion = (valor: unknown): Moderacion =>
  MODERACIONES.find((m) => m === valor) ?? "en_revision";

function motivo(valor: unknown): MotivoDeModeracion {
  const o = objeto(valor);
  return {
    regla: texto(o.regla) ?? "",
    senal: texto(o.senal) ?? "",
    gravedad: GRAVEDADES.find((g) => g === o.gravedad) ?? "baja",
    cita: texto(o.cita),
    corregir: texto(o.corregir),
  };
}

/** Solo enlaces https: lo garantiza la base (0019), y aquí no se confía en nadie más. */
const enlace = (valor: unknown): string | null => {
  const url = texto(valor);
  return url && /^https:\/\//i.test(url) ? url : null;
};

export async function obtenerColaAdmin(): Promise<VacanteEnRevision[]> {
  const r = objeto(await json(await pedir(`${API}/admin/cola`)));
  const vacantes = Array.isArray(r.vacantes) ? r.vacantes : [];
  return vacantes.map((valor) => {
    const v = objeto(valor);
    return {
      id: texto(v.id) ?? "",
      titulo: texto(v.titulo) ?? "",
      empresa: texto(v.empresa) ?? "",
      publicaParaClientes: v.publica_para === "clientes",
      verificada: v.empresa_verificada === true,
      web: enlace(v.web),
      linkedin: enlace(v.linkedin),
      estado: moderacion(v.estado),
      motivos: Array.isArray(v.motivos) ? v.motivos.map(motivo) : [],
      descripcion: texto(v.descripcion) ?? "",
      creadaEn: texto(v.creada_en),
    };
  });
}

async function resolver(ruta: string, cuerpo?: object): Promise<ResultadoDeRevision> {
  let respuesta: Response;
  try {
    respuesta = await pedir(`${API}${ruta}`, {
      method: "POST",
      ...(cuerpo ? { body: JSON.stringify(cuerpo) } : {}),
    });
  } catch (error) {
    if (error instanceof ErrorDeAdmin && error.estado === 401) {
      return { ok: false, motivo: "sin-sesion" };
    }
    return { ok: false, motivo: "error" };
  }
  if (respuesta.ok) return { ok: true };
  switch (respuesta.status) {
    case 401:
      return { ok: false, motivo: "sin-sesion" };
    case 403:
      return { ok: false, motivo: "sin-acceso" };
    case 409: {
      // El 409 trae el estado en que quedó, como /moderacion/revisar.
      const detalle = await respuesta
        .json()
        .then((j: unknown) => (esObjeto(j) && esObjeto(j.detail) ? j.detail.estado : null))
        .catch(() => null);
      return {
        ok: false,
        motivo: "ya-resuelta",
        estado: detalle === null ? null : moderacion(detalle),
      };
    }
    case 422:
      return { ok: false, motivo: cuerpo ? "falta-motivo" : "error" };
    default:
      return { ok: false, motivo: "error" };
  }
}

export const aprobarVacante = (vacanteId: string) =>
  resolver(`/admin/vacantes/${encodeURIComponent(vacanteId)}/aprobar`);

export const rechazarVacante = (vacanteId: string, motivoDelRechazo: string) =>
  resolver(`/admin/vacantes/${encodeURIComponent(vacanteId)}/rechazar`, {
    motivo: motivoDelRechazo,
  });
