/**
 * Cálculos de presentación del embudo. No son reglas de negocio: solo dicen
 * cómo dibujar los conteos que ya llegan calculados.
 */

/** Ancho de la barra en %, relativo a la etapa más grande (0 si no hay datos). */
export function anchoRelativo(conteo: number, conteos: readonly number[]): number {
  const max = Math.max(0, ...conteos);
  return max === 0 ? 0 : (conteo / max) * 100;
}
