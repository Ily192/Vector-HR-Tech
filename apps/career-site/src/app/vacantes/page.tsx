import Link from "next/link";

import { Buscador } from "../../components/buscador";
import { FiltrosRapidos } from "../../components/filtros-rapidos";
import { TarjetaVacante } from "../../components/tarjeta-vacante";
import { leerFiltros } from "../../lib/filtros";
import { listarVacantes } from "../../lib/vacantes";

export const metadata = { title: "Vacantes abiertas" };

/** Listado con búsqueda y filtros. Los filtros viajan en la URL (`lib/filtros.ts`). */
export default async function VacantesPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const filtros = leerFiltros(await searchParams);
  const vacantes = await listarVacantes(filtros);
  const hayFiltros = Object.values(filtros).some(Boolean);

  return (
    <main>
      <section className="bg-ink-900 text-white">
        <div className="container mx-auto flex flex-col gap-5 px-4 pb-10 pt-8 md:px-6">
          <h1 className="text-4xl font-extrabold tracking-[-0.035em] md:text-5xl">
            Vacantes abiertas
          </h1>
          <Buscador filtros={filtros} />
        </div>
      </section>

      <section
        aria-label="Resultados"
        className="container mx-auto flex flex-col gap-5 px-4 py-8 md:px-6"
      >
        <div className="flex flex-wrap items-center gap-3">
          <FiltrosRapidos filtros={filtros} />
          <p className="ml-auto text-sm font-semibold text-mist-600" aria-live="polite">
            {vacantes.length === 1 ? "1 vacante" : `${vacantes.length} vacantes`}
          </p>
        </div>

        {vacantes.length > 0 ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {vacantes.map((v) => (
              <TarjetaVacante key={v.id} vacante={v} />
            ))}
          </div>
        ) : (
          <div className="rounded-[22px] border border-dashed border-mist-300 bg-white p-10 text-center">
            <h2 className="text-xl font-extrabold">No hay vacantes con esos filtros</h2>
            <p className="mt-2 text-mist-600">Prueba con otra palabra o quita algún filtro.</p>
            {hayFiltros && (
              <Link
                href="/vacantes"
                className="mt-4 inline-block font-bold text-aqua-700 hover:underline"
              >
                Ver todas las vacantes
              </Link>
            )}
          </div>
        )}
      </section>
    </main>
  );
}
