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
