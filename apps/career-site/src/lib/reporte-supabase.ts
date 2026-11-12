/**
 * Los puertos del reporte sobre Supabase y Turnstile (ADR-022).
 *
 * `reportar_vacante` (0019) solo la ejecuta el rol `career_site`: ni `anon` ni
 * `authenticated` pueden. Así la clave pública no sirve para ocultar vacantes a
 * golpe de reportes, y la IP (que la función guarda como hash con sal) solo la
 * manda este servidor.
 */
import "server-only";

import { createCareerSiteClient } from "@vortex/supabase-client";

import { verificarHumano } from "./aplicacion-supabase";
import type { PuertosDeReporte, RespuestaDeReportar } from "./reporte";

/** SQLSTATE de `reportar_vacante` → lo que el botón sabe decir. */
function traducir(error: { code?: string; message?: string }): RespuestaDeReportar {
  if (error.code === "PT429") return "limite";
  if (error.code === "22023" && error.message === "vacante no disponible") return "no-disponible";
  if (error.code === "22023") return "invalido";
  throw new Error(`career-site: no se pudo reportar la vacante: ${error.message}`);
}

export function puertosDeReporte(ip: string | null): PuertosDeReporte {
  return {
    verificarHumano: (token) => verificarHumano(token, ip),
    async reportar(slug, motivo) {
      const { data, error } = await createCareerSiteClient().rpc("reportar_vacante", {
        p_slug: slug,
        p_motivo: motivo,
        p_ip: ip,
      });
      if (error) return traducir(error);
      return data === "oculta" ? "oculta" : "recibido";
    },
  };
}
