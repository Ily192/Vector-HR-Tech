/**
 * Lo que comparten el botón "Reportar vacante" y su Server Action (ADR-022). Sin
 * `server-only`: el formulario, que corre en el navegador, también lo importa.
 */

/** Los motivos que se eligen; el texto es lo que llega a la cola de revisión. */
export const MOTIVOS_DE_REPORTE = {
  dinero: "Pide dinero, un curso o un kit",
  datos: "Pide datos bancarios o documentos",
  falsa: "Parece falsa o engañosa",
  contacto: "Me contactaron por fuera (WhatsApp, Telegram)",
  otro: "Otro",
} as const;

export type MotivoDeReporte = keyof typeof MOTIVOS_DE_REPORTE;

/** Lo que se escribe a mano, además del motivo. */
export const MAX_DETALLE_DEL_REPORTE = 200;

export type ResultadoDeReportar = { estado: "ok" } | { estado: "error"; mensaje: string };
