/**
 * La aplicación de un candidato: valida el formulario y el CV, lo sube y lo
 * registra con `aplicar_a_vacante` (migraciones 0005, 0008 y 0010).
 *
 * La lógica no sabe de Supabase ni de Turnstile: los recibe como puertos, así se
 * prueba sin red. Las reglas de fondo (el tope de 50 recibidas, la vacante
 * abierta, la ruta del CV dentro de la carpeta de su empresa) las aplica la base;
 * aquí solo se traduce lo que responde.
 */
import "server-only";

import { z } from "zod";

import {
  type CampoDelFormulario,
  MAX_BYTES_DEL_CV,
  type ResultadoDeAplicar,
} from "./tipos-de-aplicacion";

export type FormatoDeCv = "pdf" | "docx";

const CONTENT_TYPE: Record<FormatoDeCv, string> = {
  pdf: "application/pdf",
  docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
};

/**
 * El formato por los primeros bytes, no por lo que dice el navegador. Un DOCX es
 * un .zip, así que además se exige la extensión. El .doc antiguo no se acepta:
 * el worker de coincidencias no lo puede leer (ADR-019).
 */
export function formatoDeCv(bytes: Uint8Array, nombre: string): FormatoDeCv | null {
  const [a, b, c, d] = bytes;
  if (a === 0x25 && b === 0x50 && c === 0x44 && d === 0x46) return "pdf"; // %PDF
  if (a === 0x50 && b === 0x4b && c === 0x03 && d === 0x04 && /\.docx$/i.test(nombre)) {
    return "docx"; // PK\x03\x04
  }
  return null;
}

const Campos = z.object({
  nombre: z
    .string()
    .trim()
    .min(2, "Escribe tu nombre completo.")
    .max(200, "El nombre es demasiado largo."),
  correo: z.string().trim().email("Revisa tu correo."),
  titular: z.string().trim().max(140),
  linkedin: z.union([
    z.literal(""),
    z
      .string()
      .trim()
      .url("El enlace de LinkedIn no es válido.")
      .max(300, "El enlace es demasiado largo."),
  ]),
  sinIa: z.boolean(),
  acepta: z.literal(true, { error: "Para aplicar, acepta el aviso de privacidad." }),
});

/** Lo que responde la base al registrar la aplicación. */
export type RespuestaDeAplicar = "ok" | "sin-cupo" | "no-disponible" | "invalida";

const MENSAJES: Record<Exclude<RespuestaDeAplicar, "ok">, string> = {
  "sin-cupo":
    "Esta vacante ya no recibe aplicaciones: llegó al máximo que la empresa puede recibir.",
  "no-disponible": "Esta vacante ya no está disponible.",
  invalida: "No pudimos registrar tu aplicación. Revisa tus datos e intenta de nuevo.",
};

export interface PuertosDeAplicacion {
  /** La vacante abierta con ese slug, o `null`. */
  vacante(slug: string): Promise<{ id: string; empresaId: string } | null>;
  /** Verifica el token de Turnstile. Sin Turnstile configurado, deja pasar. */
  verificarHumano(token: string | null): Promise<boolean>;
  subirCv(ruta: string, contenido: Uint8Array, contentType: string): Promise<void>;
  borrarCv(ruta: string): Promise<void>;
  aplicar(datos: {
    vacanteId: string;
    nombre: string;
    correo: string;
    rutaDelCv: string;
    titular: string | null;
    linkedin: string | null;
    sinIa: boolean;
  }): Promise<RespuestaDeAplicar>;
  nuevoId(): string;
}

const texto = (valor: FormDataEntryValue | null) => (typeof valor === "string" ? valor : "");

function conCampos(campos: Partial<Record<CampoDelFormulario, string>>): ResultadoDeAplicar {
  return { estado: "error", mensaje: "Revisa los datos marcados.", campos };
}

export async function procesarAplicacion(
  slug: string,
  formulario: FormData,
  puertos: PuertosDeAplicacion,
): Promise<ResultadoDeAplicar> {
  // Un campo oculto que una persona no ve ni llena. Al bot se le dice que sí.
  if (texto(formulario.get("sitio_web"))) return { estado: "ok" };

  if (!(await puertos.verificarHumano(texto(formulario.get("cf-turnstile-response")) || null))) {
    return {
      estado: "error",
      mensaje: "No pudimos verificar que no eres un robot. Recarga la página e intenta de nuevo.",
    };
  }

  const campos = Campos.safeParse({
    nombre: texto(formulario.get("nombre")),
    correo: texto(formulario.get("correo")),
    titular: texto(formulario.get("titular")),
    linkedin: texto(formulario.get("linkedin")),
    sinIa: formulario.get("sin_ia") === "on",
    acepta: formulario.get("acepta") === "on",
  });
  const cv = formulario.get("cv");
  const errores: Partial<Record<CampoDelFormulario, string>> = {};
  if (!campos.success) {
    for (const problema of campos.error.issues) {
      const campo = problema.path[0] as CampoDelFormulario;
      errores[campo] ??= problema.message;
    }
  }
  if (!(cv instanceof File) || cv.size === 0) {
    errores.cv = "Adjunta tu CV en PDF o Word (.docx).";
  } else if (cv.size > MAX_BYTES_DEL_CV) {
    errores.cv = "Tu CV pesa más de 4 MB. Prueba con una versión en PDF.";
  }
  if (!campos.success || Object.keys(errores).length > 0) return conCampos(errores);

  const archivo = cv as File;
  const bytes = new Uint8Array(await archivo.arrayBuffer());
  const formato = formatoDeCv(bytes, archivo.name);
  if (!formato) return conCampos({ cv: "El CV tiene que ser PDF o Word (.docx)." });

  const vacante = await puertos.vacante(slug);
  if (!vacante) return { estado: "error", mensaje: MENSAJES["no-disponible"] };

  // La base exige que la ruta empiece por la carpeta de la empresa de la vacante.
  const ruta = `${vacante.empresaId}/${puertos.nuevoId()}.${formato}`;
  await puertos.subirCv(ruta, bytes, CONTENT_TYPE[formato]);
  let respuesta: RespuestaDeAplicar = "invalida";
  try {
    const d = campos.data;
    respuesta = await puertos.aplicar({
      vacanteId: vacante.id,
      nombre: d.nombre,
      correo: d.correo,
      rutaDelCv: ruta,
      titular: d.titular || null,
      linkedin: d.linkedin || null,
      sinIa: d.sinIa,
    });
  } finally {
    // Si no quedó registrada, el CV no se queda huérfano en el bucket.
    if (respuesta !== "ok") await puertos.borrarCv(ruta);
  }
  return respuesta === "ok" ? { estado: "ok" } : { estado: "error", mensaje: MENSAJES[respuesta] };
}
