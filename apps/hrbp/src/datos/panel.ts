/**
 * Datos del panel de la empresa. Las pantallas piden todo por aquí, vía
 * `consultas.ts`, y no saben de dónde viene.
 *
 * Con `VITE_SUPABASE_URL` y `VITE_SUPABASE_PUBLISHABLE_KEY` el panel lee Supabase
 * (`panel-supabase.ts`), y las reglas del plan las aplica la base (ADR-017,
 * ADR-019). Sin ellas usa el ejemplo en memoria (`panel-ejemplo.ts`), que es lo
 * que ven la demo y los tests; las pantallas lo avisan con `ES_DE_EJEMPLO`.
 *
 * Los dos adaptadores se cargan aparte: supabase-js pesa más que todo el marco y
 * el bundle principal tiene tope de 90 KB.
 */
import type { AdaptadorDelPanel, BorradorDeVacante, OrigenDelInteres } from "./tipos";

const URL_DE_SUPABASE = import.meta.env.VITE_SUPABASE_URL;
const CLAVE_PUBLICA =
  import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY || import.meta.env.VITE_SUPABASE_ANON_KEY;

/** `true` mientras los datos sean de ejemplo; las pantallas lo avisan. */
export const ES_DE_EJEMPLO = !(URL_DE_SUPABASE && CLAVE_PUBLICA);

let cargado: Promise<AdaptadorDelPanel> | undefined;

function adaptador(): Promise<AdaptadorDelPanel> {
  cargado ??=
    URL_DE_SUPABASE && CLAVE_PUBLICA
      ? import("./panel-supabase").then((m) =>
          m.crearAdaptadorDeSupabase(URL_DE_SUPABASE, CLAVE_PUBLICA),
        )
      : import("./panel-ejemplo").then((m) => m.adaptadorDeEjemplo);
  return cargado;
}

export const obtenerSesion = async () => (await adaptador()).obtenerSesion();

export const listarMisVacantes = async () => (await adaptador()).listarMisVacantes();

export const publicarVacante = async (borrador: BorradorDeVacante) =>
  (await adaptador()).publicarVacante(borrador);

export const eliminarVacante = async (vacanteId: string) =>
  (await adaptador()).eliminarVacante(vacanteId);

export const obtenerPipeline = async (vacanteId: string) =>
  (await adaptador()).obtenerPipeline(vacanteId);

export const solicitarDescargaDeCvs = async (vacanteId: string) =>
  (await adaptador()).solicitarDescargaDeCvs(vacanteId);

export const registrarInteres = async (origen: OrigenDelInteres) =>
  (await adaptador()).registrarInteres(origen);

export const entrar = async (correo: string) => (await adaptador()).entrar(correo);

export const salir = async () => (await adaptador()).salir();

/** Avisa cuando entra o sale alguien. Devuelve cómo dejar de escuchar. */
export function alCambiarLaSesion(avisar: () => void): () => void {
  let dejarDeEscuchar: (() => void) | undefined;
  let cancelado = false;
  void adaptador().then((a) => {
    if (!cancelado) dejarDeEscuchar = a.alCambiarLaSesion(avisar);
  });
  return () => {
    cancelado = true;
    dejarDeEscuchar?.();
  };
}
