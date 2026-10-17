import Link from "next/link";

import { Buscador } from "../components/buscador";
import { FiltrosRapidos } from "../components/filtros-rapidos";
import { TarjetaVacante } from "../components/tarjeta-vacante";
import { listarVacantes } from "../lib/vacantes";

/** Cuántas vacantes recientes se muestran en el inicio. */
const VACANTES_EN_INICIO = 6;

const PASOS = [
  {
    eyebrow: "01 · Aplica",
    titulo: "Sin crear cuenta",
    texto: "Tu CV en PDF y tus datos de contacto. Nada más.",
    clases: "bg-ink-900 text-white",
    eyebrowClase: "text-aqua-300",
    textoClase: "text-[#C9CCF2]",
  },
  {
    eyebrow: "02 · Seguimiento",
    titulo: "Sabes en qué va",
    texto: "Te avisamos por correo cuando tu aplicación cambia de estado.",
    clases: "bg-aqua-50",
    eyebrowClase: "text-aqua-700",
    textoClase: "text-aqua-800",
  },
  {
    eyebrow: "03 · Tus datos",
    titulo: "Solo los ve esa empresa",
    texto: "No compartimos tu CV con otras empresas sin tu permiso.",
    clases: "bg-flame-50",
    eyebrowClase: "text-flame-700",
    textoClase: "text-flame-800",
  },
] as const;

/** Inicio del sitio de candidatos: buscar, ver lo más reciente y cómo se aplica. */
export default async function Home() {
  const vacantes = await listarVacantes();
  const empresas = new Set(vacantes.map((v) => v.empresa_slug)).size;

  return (
    <main>
      <section className="bg-ink-900 text-white">
        <div className="container mx-auto flex flex-col gap-5 px-4 pb-16 pt-10 md:px-6 md:pb-20 md:pt-14">
          <span className="font-mono text-[11px] font-semibold uppercase tracking-[0.08em] text-aqua-300">
            {vacantes.length} vacantes · {empresas} empresas en LATAM
          </span>
          <h1 className="max-w-4xl text-[clamp(2.5rem,6vw,4.25rem)] font-black leading-[0.98] tracking-[-0.05em]">
            Tu siguiente trabajo,{" "}
            <em className="font-extrabold text-aqua-300">con el salario a la vista.</em>
          </h1>
          <p className="max-w-xl text-lg text-[#C9CCF2]">
            Aplica en dos minutos y sigue el estado de cada aplicación desde tu correo.
          </p>
          <div className="mt-2">
            <Buscador />
          </div>
        </div>
      </section>

      <section
        aria-labelledby="recientes"
        className="container mx-auto flex flex-col gap-5 px-4 py-8 md:px-6"
      >
        <div className="flex flex-wrap items-end justify-between gap-3">
          <h2 id="recientes" className="text-2xl font-extrabold tracking-[-0.02em]">
            Vacantes recientes
          </h2>
          <Link href="/vacantes" className="text-[15px] font-bold text-aqua-700 hover:underline">
            Ver todas →
          </Link>
        </div>
        <FiltrosRapidos filtros={{}} />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {vacantes.slice(0, VACANTES_EN_INICIO).map((v) => (
            <TarjetaVacante key={v.id} vacante={v} />
          ))}
        </div>
      </section>

      <section
        id="como-aplicar"
        aria-labelledby="como-aplicar-titulo"
        className="container mx-auto scroll-mt-6 px-4 pb-16 pt-4 md:px-6"
      >
        <h2 id="como-aplicar-titulo" className="sr-only">
          Cómo aplicar
        </h2>
        <div className="grid gap-4 md:grid-cols-3">
          {PASOS.map((p) => (
            <div
              key={p.titulo}
              className={`flex flex-col gap-2 rounded-[22px] p-[22px] ${p.clases}`}
            >
              <span
                className={`font-mono text-[11px] font-semibold uppercase tracking-[0.08em] ${p.eyebrowClase}`}
              >
                {p.eyebrow}
              </span>
              <h3 className="text-[19px] font-extrabold">{p.titulo}</h3>
              <p className={`text-[15px] ${p.textoClase}`}>{p.texto}</p>
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}
