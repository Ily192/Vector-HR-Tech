/**
 * Los textos del cockpit. Ponen en palabras lo que ya calculó la base
 * (`resumen_del_cockpit()`, 0016); no deciden ni cuentan nada.
 */
import { ETIQUETA_SIGUIENTE_PASO } from "@vortex/types/etiquetas";
import { siguientePaso } from "@vortex/types/reglas";

import type { DecisionDelDia, EntradaDelRegistro } from "../datos/tipos";

const plural = (n: number, uno: string, varios: string) => (n === 1 ? uno : `${n} ${varios}`);

/** "9.4, 9.3 y 9.1" */
function enumerar(partes: string[]): string {
  return partes.length < 2
    ? (partes[0] ?? "")
    : `${partes.slice(0, -1).join(", ")} y ${partes.at(-1)}`;
}

/** Título y detalle de la decisión del día. */
export function textoDeLaDecision(decision: DecisionDelDia): { titulo: string; detalle: string } {
  const { titulo: vacante } = decision.vacante;
  if (decision.tipo === "entrevistar") {
    const scores = enumerar(decision.scores.map((s) => s.toFixed(1)));
    const cuales =
      decision.listos > decision.scores.length
        ? `Los ${decision.scores.length} mejores: ${scores}.`
        : `${decision.listos === 1 ? "Score" : "Scores"} ${scores}.`;
    return {
      titulo: `${plural(decision.listos, "Un candidato listo", "candidatos listos")} para entrevista en ${vacante}`,
      detalle: `${cuales} Lo sugiere la IA, que evaluó sin ver nombres; la decisión es tuya.`,
    };
  }
  const total = decision.sinEvaluar + decision.ilegibles + decision.sinIa;
  const motivos = [
    decision.sinEvaluar > 0 &&
      plural(decision.sinEvaluar, "una no se pudo evaluar", "no se pudieron evaluar"),
    decision.ilegibles > 0 &&
      plural(decision.ilegibles, "un CV no se pudo leer", "CVs no se pudieron leer"),
    decision.sinIa > 0 &&
      plural(
        decision.sinIa,
        "un candidato pidió no ser evaluado con IA",
        "candidatos pidieron no ser evaluados con IA",
      ),
  ].filter((m): m is string => Boolean(m));
  return {
    titulo: `${plural(total, "Una aplicación", "aplicaciones")} por revisar a mano en ${vacante}`,
    detalle: `La IA no ${total === 1 ? "la" : "las"} evaluó: ${enumerar(motivos)}.`,
  };
}

export const variacionDeCandidatos = (nuevos24h: number) =>
  nuevos24h > 0 ? `+${nuevos24h} en 24 h` : "ninguno nuevo en 24 h";

export const variacionDeVacantes = (nuevas7d: number) =>
  nuevas7d > 0 ? `+${nuevas7d} en 7 días` : "ninguna nueva en 7 días";

export const variacionDeEvaluaciones = (porcentajeSinError: number | null) =>
  porcentajeSinError === null ? "sin evaluaciones" : `${porcentajeSinError} % sin error`;

/** Con el tope del mes alcanzado, lo que espera ya no se evalúa hasta el mes siguiente. */
export function variacionDeEnEspera(enEspera: { total: number; topeAlcanzado: boolean }): string {
  if (enEspera.total === 0) return "nada en espera";
  return enEspera.topeAlcanzado ? "esperan al próximo mes: llegaste al tope" : "se evalúan solas";
}

/** "Senior Software Engineer · 8.5 · Entrevista", sin el nombre del candidato. */
export function detalleDelRegistro(entrada: EntradaDelRegistro): string {
  const { vacante, score } = entrada;
  if (entrada.aplazada) return `${vacante ?? "Una evaluación"} · no se pudo evaluar`;
  if (score === null) return vacante ? `${vacante} · evaluada` : "Ejecución terminada";
  const sugerencia = ETIQUETA_SIGUIENTE_PASO[siguientePaso(score)];
  return `${vacante ?? "Evaluación"} · ${score.toFixed(1)} · ${sugerencia}`;
}
