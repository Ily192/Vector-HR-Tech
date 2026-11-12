/**
 * "Reportar vacante" (ADR-022): valida el formulario y llama a `reportar_vacante`
 * (migración 0019) con el rol del career site.
 *
 * La lógica no sabe de Supabase ni de Turnstile: los recibe como puertos. Las reglas
 * de fondo son de la base: un reporte por IP y vacante, diez por IP al día, y con dos
 * personas distintas la vacante se oculta y pasa a revisión de Vector HR. La IP
 * llega a la base y ahí se guarda como hash con sal; aquí no se guarda.
 */
import "server-only";

import {
  MAX_DETALLE_DEL_REPORTE,
  MOTIVOS_DE_REPORTE,
  type MotivoDeReporte,
  type ResultadoDeReportar,
} from "./tipos-de-reporte";

export type RespuestaDeReportar = "recibido" | "oculta" | "no-disponible" | "limite" | "invalido";

export interface PuertosDeReporte {
  /** Verifica el token de Turnstile. Sin Turnstile configurado, deja pasar. */
  verificarHumano(token: string | null): Promise<boolean>;
  reportar(slug: string, motivo: string): Promise<RespuestaDeReportar>;
}

const texto = (valor: FormDataEntryValue | null) => (typeof valor === "string" ? valor : "");

const esMotivo = (valor: string): valor is MotivoDeReporte =>
  Object.hasOwn(MOTIVOS_DE_REPORTE, valor);

const MENSAJES: Record<Exclude<RespuestaDeReportar, "recibido" | "oculta">, string> = {
  "no-disponible": "Esta vacante ya no está publicada.",
  limite: "Ya enviaste varios reportes hoy. Si es urgente, escríbenos a hola@vectorhrtech.com.",
  invalido: "Elige un motivo e intenta de nuevo.",
};

export async function procesarReporte(
  slug: string,
  formulario: FormData,
  puertos: PuertosDeReporte,
): Promise<ResultadoDeReportar> {
  // El campo trampa: una persona no lo ve. Al bot se le dice que sí.
  if (texto(formulario.get("sitio_web"))) return { estado: "ok" };

  if (!(await puertos.verificarHumano(texto(formulario.get("cf-turnstile-response")) || null))) {
    return {
      estado: "error",
      mensaje: "No pudimos verificar que no eres un robot. Recarga la página e intenta de nuevo.",
    };
  }

  const clave = texto(formulario.get("motivo"));
  if (!esMotivo(clave)) return { estado: "error", mensaje: MENSAJES.invalido };
  const detalle = texto(formulario.get("detalle"))
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, MAX_DETALLE_DEL_REPORTE);
  const motivo = detalle ? `${MOTIVOS_DE_REPORTE[clave]}: ${detalle}` : MOTIVOS_DE_REPORTE[clave];

  const respuesta = await puertos.reportar(slug, motivo);
  if (respuesta === "recibido" || respuesta === "oculta") return { estado: "ok" };
  return { estado: "error", mensaje: MENSAJES[respuesta] };
}
