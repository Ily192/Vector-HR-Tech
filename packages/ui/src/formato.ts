/**
 * Cómo se escriben en pantalla los datos de una vacante, igual en el career site
 * y en el panel de la empresa. Solo presentación: no decide qué vacante se
 * muestra ni qué salario es público.
 */

/** Las columnas de salario tal como las expone `vacantes_publicas`. */
export interface SalarioPublicado {
  salario_min: number | null;
  salario_max: number | null;
  moneda: string | null;
}

/** Días durante los que una vacante lleva la etiqueta "Nueva". */
export const DIAS_COMO_NUEVA = 3;

const DIA_MS = 24 * 60 * 60 * 1000;

/** `"$22,000 – $28,000"` en la moneda de la vacante, o `null` si no publica salario. */
export function formatearSalario(v: SalarioPublicado): string | null {
  if (v.salario_min === null || !v.moneda) return null;
  const fmt = new Intl.NumberFormat("es-MX", {
    style: "currency",
    currency: v.moneda,
    currencyDisplay: "narrowSymbol",
    maximumFractionDigits: 0,
  });
  const desde = fmt.format(v.salario_min);
  return v.salario_max !== null && v.salario_max !== v.salario_min
    ? `${desde} – ${fmt.format(v.salario_max)}`
    : desde;
}

/** `"Hoy"`, `"Hace 2 días"`, `"Hace 1 semana"`… a partir de la fecha de publicación. */
export function haceCuanto(fechaIso: string, ahora: Date = new Date()): string {
  const dias = Math.max(0, Math.floor((ahora.getTime() - Date.parse(fechaIso)) / DIA_MS));
  if (dias === 0) return "Hoy";
  if (dias === 1) return "Ayer";
  if (dias < 7) return `Hace ${dias} días`;
  const semanas = Math.floor(dias / 7);
  return semanas === 1 ? "Hace 1 semana" : `Hace ${semanas} semanas`;
}

/** Si la vacante se publicó hace menos de `DIAS_COMO_NUEVA` días. */
export function esNueva(fechaIso: string, ahora: Date = new Date()): boolean {
  return ahora.getTime() - Date.parse(fechaIso) < DIAS_COMO_NUEVA * DIA_MS;
}

/** Dos iniciales para el monograma de la empresa: "Andes Logística" → "AL". */
export function iniciales(nombre: string): string {
  const [primera = "", segunda] = nombre.trim().split(/\s+/);
  return (segunda ? `${primera.charAt(0)}${segunda.charAt(0)}` : primera.slice(0, 2)).toUpperCase();
}
