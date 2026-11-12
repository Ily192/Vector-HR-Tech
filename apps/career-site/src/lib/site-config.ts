/**
 * Enlaces y datos fijos del sitio, en un solo lugar.
 *
 * El career-site es para candidatos (ADR-017): no lleva contacto comercial. Para
 * empresas solo hay dos enlaces: registrarse gratis en la web de Vector HR Tech y
 * entrar a su panel (enmienda de ADR-017 del 2026-11-11).
 */

/** Panel de la empresa (apps/hrbp). Se puede cambiar por entorno sin tocar código. */
export const PANEL_EMPRESAS_URL =
  process.env.NEXT_PUBLIC_PANEL_EMPRESAS_URL ?? "https://panel.vectorhrtech.com";

/** El registro gratis para publicar vacantes, en la web de Vector HR Tech. */
export const PUBLICAR_VACANTES_URL = "https://vectorhrtech.com/publicar-vacantes";
