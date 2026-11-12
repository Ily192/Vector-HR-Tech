import { entorno } from "./entorno";

type Resumen = { ID: string };
type Mensaje = { HTML: string };

const esperar = (ms: number) => new Promise((listo) => setTimeout(listo, ms));

/**
 * El enlace de Auth (`/auth/v1/verify`) del último correo que recibió `para` en el
 * Mailpit del Supabase local. Lo espera hasta `ms`: GoTrue lo manda al responder.
 */
export async function enlaceDelCorreo(para: string, ms = 30_000): Promise<string> {
  const { mailpit } = entorno();
  if (!mailpit) throw new Error("El correo solo se lee en local, en Mailpit.");
  const busqueda = `${mailpit}/api/v1/search?query=${encodeURIComponent(`to:"${para}"`)}`;
  const hasta = Date.now() + ms;
  while (Date.now() < hasta) {
    const { messages } = (await (await fetch(busqueda)).json()) as { messages: Resumen[] };
    const ultimo = messages[0];
    if (ultimo) {
      const { HTML } = (await (
        await fetch(`${mailpit}/api/v1/message/${ultimo.ID}`)
      ).json()) as Mensaje;
      const enlace = /href="([^"]*\/auth\/v1\/verify[^"]*)"/.exec(HTML)?.[1];
      if (enlace) return enlace.replaceAll("&amp;", "&");
    }
    await esperar(1_000);
  }
  throw new Error(`No le llegó ningún correo a ${para} en ${ms / 1000} s.`);
}

/**
 * El código de 6 dígitos del último correo que recibió `para` después de `desde` (ms),
 * con la plantilla de infra/supabase/templates (alta o entrada). Lo espera hasta `ms`.
 */
export async function codigoDelCorreo(para: string, desde: number, ms = 60_000): Promise<string> {
  const { mailpit } = entorno();
  if (!mailpit) throw new Error("El código se lee en Mailpit: falta E2E_MAILPIT_URL.");
  const busqueda = `${mailpit}/api/v1/search?query=${encodeURIComponent(`to:"${para}"`)}`;
  const hasta = Date.now() + ms;
  while (Date.now() < hasta) {
    const { messages } = (await (await fetch(busqueda)).json()) as {
      messages: (Resumen & { Created: string })[];
    };
    const ultimo = messages.find((m) => Date.parse(m.Created) >= desde - 2_000);
    if (ultimo) {
      const { HTML } = (await (
        await fetch(`${mailpit}/api/v1/message/${ultimo.ID}`)
      ).json()) as Mensaje;
      // Sin etiquetas (y sin sus atributos, como los colores #181854 del estilo).
      const texto = HTML.replace(/<[^>]*>/g, " ");
      const codigo = /\b(\d{6})\b/.exec(texto)?.[1];
      if (codigo) return codigo;
    }
    await esperar(1_000);
  }
  throw new Error(`No le llegó ningún código a ${para} en ${ms / 1000} s.`);
}
