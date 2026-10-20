import { entorno } from "./entorno";

/** Las claves nuevas (`sb_secret_…`) van solo en `apikey`; la `service_role` legada, también como Bearer. */
function cabeceras(clave: string): Record<string, string> {
  return clave.startsWith("sb_")
    ? { apikey: clave, "Content-Type": "application/json" }
    : { apikey: clave, Authorization: `Bearer ${clave}`, "Content-Type": "application/json" };
}

/**
 * Un enlace para entrar al panel sin pasar por el correo (`POST /auth/v1/admin/generate_link`).
 * Es para el humo contra un despliegue, donde los correos salen por Resend y no se pueden leer.
 */
export async function enlaceParaEntrar(correo: string): Promise<string> {
  const e = entorno();
  const respuesta = await fetch(`${e.supabaseUrl}/auth/v1/admin/generate_link`, {
    method: "POST",
    headers: cabeceras(e.claveSecreta),
    body: JSON.stringify({ type: "magiclink", email: correo, redirect_to: e.panel }),
  });
  if (!respuesta.ok) {
    throw new Error(`generate_link respondió ${respuesta.status}: ${await respuesta.text()}`);
  }
  const cuerpo = (await respuesta.json()) as {
    action_link?: string;
    properties?: { action_link?: string };
  };
  const enlace = cuerpo.action_link ?? cuerpo.properties?.action_link;
  if (!enlace) throw new Error("generate_link no devolvió el enlace.");
  return enlace;
}
