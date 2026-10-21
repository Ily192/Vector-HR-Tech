import type { Respuestas, Resultado } from "./diagnostico";

/** De qué campaña llegó el prospecto: los utm de la URL, para medir cuál trae clientes. */
export interface Origen {
  origen: string | null;
  utmMedium: string | null;
  utmCampaign: string | null;
}

function parametro(params: URLSearchParams, nombre: string, max: number): string | null {
  const valor = params.get(nombre)?.trim();
  return valor ? valor.slice(0, max) : null;
}

export function leerOrigen(busqueda: string): Origen {
  const params = new URLSearchParams(busqueda);
  return {
    origen: parametro(params, "utm_source", 64),
    utmMedium: parametro(params, "utm_medium", 64),
    utmCampaign: parametro(params, "utm_campaign", 120),
  };
}

export interface Contacto {
  nombre: string;
  empresa: string;
  correo: string;
}

/** Un correo razonable; la base valida lo mismo (privado.diagnosticos, 0017). */
export function correoValido(correo: string): boolean {
  return correo.length <= 254 && /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(correo);
}

/** 429 es el freno de la base (0017): demasiados diagnósticos desde el mismo correo o red. */
export class ErrorDeEnvio extends Error {
  constructor(readonly status: number) {
    super(`registrar_diagnostico respondió ${status}`);
  }
}

/**
 * Guarda el diagnóstico. Va al mismo dominio: Caddy (o el proxy de Vite en desarrollo)
 * lo reenvía a la RPC `registrar_diagnostico` con la clave anon, así que la página no
 * lleva ninguna clave ni depende del dominio de la API.
 */
export async function enviarDiagnostico(
  contacto: Contacto,
  origen: Origen,
  respuestas: Respuestas,
  resultado: Resultado,
  turnstileToken: string | null,
  sinFinesComerciales: boolean,
  fetcher: typeof fetch = fetch,
): Promise<void> {
  const respuesta = await fetcher("/api/diagnostico", {
    method: "POST",
    headers: { "Content-Type": "application/json", Prefer: "return=minimal" },
    body: JSON.stringify({
      p_nombre: contacto.nombre.trim(),
      p_empresa: contacto.empresa.trim(),
      p_correo: contacto.correo.trim().toLowerCase(),
      p_origen: origen.origen,
      p_utm_medium: origen.utmMedium,
      p_utm_campaign: origen.utmCampaign,
      p_respuestas: respuestas,
      p_resultado: resultado,
      p_horas_recuperables_mes: resultado.horasRecuperablesMes,
      p_turnstile_token: turnstileToken,
      p_sin_fines_comerciales: sinFinesComerciales,
    }),
  });
  if (!respuesta.ok) throw new ErrorDeEnvio(respuesta.status);
}
