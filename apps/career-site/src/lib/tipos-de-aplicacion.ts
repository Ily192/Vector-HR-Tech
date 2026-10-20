/**
 * Lo que comparten el formulario de aplicación y su Server Action. No lleva
 * `server-only`: el formulario, que corre en el navegador, también lo importa.
 */

/**
 * Tope del CV. Viaja dentro del formulario, y Vercel no deja pasar más de 4.5 MB
 * por función ("FUNCTION_PAYLOAD_TOO_LARGE"). Un CV en PDF suele pesar menos de 1 MB.
 */
export const MAX_BYTES_DEL_CV = 4 * 1024 * 1024;

export type CampoDelFormulario = "nombre" | "correo" | "linkedin" | "cv" | "acepta";

export type ResultadoDeAplicar =
  | { estado: "ok" }
  | {
      estado: "error";
      mensaje: string;
      campos?: Partial<Record<CampoDelFormulario, string>>;
    };
