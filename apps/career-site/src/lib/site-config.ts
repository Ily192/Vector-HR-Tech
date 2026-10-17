/**
 * Enlaces y datos fijos del sitio, en un solo lugar.
 *
 * El career-site es para candidatos (ADR-017): no lleva contacto comercial. La
 * única puerta para empresas es su panel en Vortex.
 */

/** Panel de la empresa (apps/hrbp). Se puede cambiar por entorno sin tocar código. */
export const PANEL_EMPRESAS_URL =
  process.env.NEXT_PUBLIC_PANEL_EMPRESAS_URL ?? "https://vortex-hrbp.vercel.app";
