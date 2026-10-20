/**
 * Los puertos de la aplicación sobre Supabase y Cloudflare Turnstile.
 *
 * - El CV lo sube el servidor con la clave secreta: el bucket `cvs` no deja
 *   escribir ni a `anon` ni a `authenticated` (0005), para no ser un dropbox público.
 * - La aplicación la registra `aplicar_a_vacante` con la clave pública: es una RPC
 *   de superficie mínima que `anon` puede ejecutar.
 * - La vacante se busca con la clave secreta porque la vista pública no expone el
 *   `empresa_id`, y la ruta del CV tiene que empezar por él.
 */
import "server-only";

import { createPublicClient, createServiceRoleClient } from "@vortex/supabase-client";

import type { PuertosDeAplicacion, RespuestaDeAplicar } from "./aplicacion";

const VERIFICAR_TURNSTILE = "https://challenges.cloudflare.com/turnstile/v0/siteverify";

/**
 * Turnstile: "POST https://challenges.cloudflare.com/turnstile/v0/siteverify" con
 * `secret`, `response` y `remoteip`. El token dura 5 minutos y vale una sola vez.
 * Sin `TURNSTILE_SECRET_KEY` no se verifica: queda el campo trampa, y el despliegue
 * tiene que configurarlo antes de abrir el formulario (runbook).
 */
async function verificarHumano(token: string | null, ip: string | null): Promise<boolean> {
  const secreto = process.env.TURNSTILE_SECRET_KEY;
  if (!secreto) {
    console.warn(
      "career-site: TURNSTILE_SECRET_KEY no está configurada; no se verifica el formulario",
    );
    return true;
  }
  if (!token) return false;
  const cuerpo = new URLSearchParams({ secret: secreto, response: token });
  if (ip) cuerpo.set("remoteip", ip);
  try {
    const respuesta = await fetch(VERIFICAR_TURNSTILE, { method: "POST", body: cuerpo });
    const datos = (await respuesta.json()) as { success?: boolean };
    return datos.success === true;
  } catch {
    return false;
  }
}

/** SQLSTATE de `aplicar_a_vacante` → lo que el formulario sabe decir. */
function traducir(error: { code?: string; message?: string }): RespuestaDeAplicar {
  if (error.code === "PT409") return "sin-cupo";
  if (error.code === "22023" && error.message === "vacante no disponible") return "no-disponible";
  return "invalida";
}

export function puertosDeSupabase(ip: string | null): PuertosDeAplicacion {
  const secreto = createServiceRoleClient();
  const publico = createPublicClient();
  return {
    async vacante(slug) {
      const { data, error } = await secreto
        .from("vacantes")
        .select("id, empresa_id")
        .eq("slug", slug)
        .eq("status", "open")
        .maybeSingle();
      if (error)
        throw new Error(`career-site: no se pudo leer la vacante ${slug}: ${error.message}`);
      return data ? { id: data.id, empresaId: data.empresa_id } : null;
    },
    verificarHumano: (token) => verificarHumano(token, ip),
    async subirCv(ruta, contenido, contentType) {
      const { error } = await secreto.storage
        .from("cvs")
        .upload(ruta, contenido, { contentType, upsert: false });
      if (error) throw new Error(`career-site: no se pudo subir el CV: ${error.message}`);
    },
    async borrarCv(ruta) {
      await secreto.storage.from("cvs").remove([ruta]);
    },
    async aplicar(d) {
      const { error } = await publico.rpc("aplicar_a_vacante", {
        p_vacante_id: d.vacanteId,
        p_full_name: d.nombre,
        p_email: d.correo,
        p_cv_path: d.rutaDelCv,
        p_headline: d.titular,
        p_linkedin: d.linkedin,
        p_sin_ia: d.sinIa,
      });
      return error ? traducir(error) : "ok";
    },
    nuevoId: () => crypto.randomUUID(),
  };
}
