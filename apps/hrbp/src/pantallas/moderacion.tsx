/**
 * Lo que la empresa ve de la moderación de sus vacantes (0019, ADR-022).
 *
 * La decide el hr-engine; el panel solo la pinta. Una vacante 'pendiente' sale al
 * career site en el siguiente barrido (un minuto) si no tiene señales de riesgo; una
 * 'en_revision' la mira una persona de Vector HR; una 'rechazada' trae qué corregir.
 */
import { ETIQUETA_MODERACION } from "@vortex/types/etiquetas";
import type { Moderacion, MotivoDeModeracion } from "@vortex/types/hr";
import { Badge } from "@vortex/ui";

const VARIANTE = {
  pendiente: "manual",
  en_revision: "warning",
  rechazada: "danger",
  oculta: "danger",
} as const;

/** La insignia junto al título. Una publicada no lleva ninguna. */
export function InsigniaDeModeracion({ moderacion }: { moderacion: Moderacion }) {
  if (moderacion === "publicada") return null;
  return <Badge variant={VARIANTE[moderacion]}>{ETIQUETA_MODERACION[moderacion]}</Badge>;
}

const EXPLICACION: Record<Exclude<Moderacion, "publicada">, string> = {
  pendiente:
    "La estamos revisando. Si no tiene señales de riesgo, aparece en la bolsa de empleo en un minuto.",
  en_revision:
    "Una persona de Vector HR la revisa antes de publicarla. Mientras tanto no aparece en la bolsa de empleo.",
  rechazada:
    "No la publicamos. Elimínala y publícala de nuevo con los cambios: una vacante rechazada no cuenta en tu cupo.",
  oculta:
    "La ocultamos porque varias personas la reportaron desde la bolsa de empleo. Vector HR la revisa.",
};

/** Por qué no está en el career site y, si se rechazó, qué corregir. */
export function AvisoDeModeracion({
  moderacion,
  motivos,
}: {
  moderacion: Moderacion;
  motivos: readonly MotivoDeModeracion[];
}) {
  if (moderacion === "publicada") return null;
  const peligro = moderacion === "rechazada" || moderacion === "oculta";
  return (
    <output
      className={`mt-3 block rounded-2xl p-4 text-sm ${
        peligro ? "bg-danger-50 text-danger-700" : "bg-mist-100 text-mist-700"
      }`}
    >
      <p>{EXPLICACION[moderacion]}</p>
      {motivos.length > 0 && (
        <ul className="mt-2 list-disc space-y-1 pl-5">
          {motivos.map((m) => (
            <li key={`${m.regla}-${m.senal}`}>
              {m.senal}
              {m.cita && <> «{m.cita}»</>}
              {moderacion === "rechazada" && m.corregir && (
                <>
                  {" "}
                  <b>Qué corregir:</b> {m.corregir}
                </>
              )}
            </li>
          ))}
        </ul>
      )}
    </output>
  );
}

/** Para un reclutador(a) independiente: sus vacantes siempre pasan por revisión. */
export function AvisoDeReclutador() {
  return (
    <output className="block rounded-2xl bg-aqua-50 p-4 text-sm text-aqua-700">
      Como reclutador(a) independiente, Vector HR revisa cada vacante antes de publicarla. En la
      bolsa de empleo sale a tu nombre, con tu LinkedIn.
    </output>
  );
}

/** El texto de la lista vacía de aplicados, según si la vacante ya está publicada. */
export function sinAplicaciones(moderacion: Moderacion): string {
  return moderacion === "publicada"
    ? "Todavía no hay aplicaciones. La vacante ya está en la bolsa de empleo."
    : "Todavía no hay aplicaciones: la vacante aún no está en la bolsa de empleo.";
}
