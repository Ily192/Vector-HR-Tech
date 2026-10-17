import { Badge } from "@vortex/ui";
import { Briefcase, LayoutGrid, type LucideIcon, Plus } from "lucide-react";
import type { ReactNode } from "react";

import { useMisVacantes, useSesion } from "../datos/consultas";
import { ES_DE_EJEMPLO } from "../datos/panel";
import type { CupoDeVacantes, Modulo } from "../datos/tipos";
import { Enlace } from "../navegacion/ruta";

/** Entradas del menú lateral. Cuáles se ven lo decide el plan, vía `sesion.modulos`. */
export type Seccion = "hoy" | "mis-vacantes" | "crear-empleo";

interface EntradaDelMenu {
  seccion: Seccion;
  href: string;
  texto: string;
  icono: LucideIcon;
}

const GRUPOS: { modulo: Modulo; titulo: string; entradas: EntradaDelMenu[] }[] = [
  {
    modulo: "cockpit",
    titulo: "Operación",
    entradas: [{ seccion: "hoy", href: "/", texto: "Hoy", icono: LayoutGrid }],
  },
  {
    modulo: "career-site",
    titulo: "Career site",
    entradas: [
      { seccion: "mis-vacantes", href: "/vacantes", texto: "Mis vacantes", icono: Briefcase },
      { seccion: "crear-empleo", href: "/vacantes/nueva", texto: "Crear empleo", icono: Plus },
    ],
  },
];

function Logo() {
  return (
    <svg aria-hidden="true" width="30" height="30" viewBox="0 0 30 30" className="shrink-0">
      <rect x=".5" y=".5" width="29" height="29" rx="9" className="fill-ink-950 stroke-ink-800" />
      <path
        d="M9 9l6 12 6-12"
        fill="none"
        className="stroke-aqua-300"
        strokeWidth="3.2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function TuPlan({ plan, cupo }: { plan: string; cupo: CupoDeVacantes }) {
  return (
    <div className="mt-auto flex flex-col gap-2 rounded-2xl bg-ink-950 p-3.5">
      <span className="font-mono text-[11px] font-semibold uppercase tracking-[0.08em] text-aqua-300">
        Tu plan
      </span>
      <span className="text-base font-extrabold">{plan}</span>
      <div className="mt-1 flex justify-between text-[13px] text-mist-300">
        <span>Vacantes activas</span>
        <b className="text-white">
          {cupo.activas} de {cupo.limite}
        </b>
      </div>
      <div className="h-1.5 rounded-full bg-ink-800" aria-hidden="true">
        <div
          className="h-full rounded-full bg-aqua-300"
          style={{ width: `${(cupo.activas / cupo.limite) * 100}%` }}
        />
      </div>
      <span className="text-xs text-mist-300">
        Hasta {cupo.maxAplicacionesPorVacante} aplicaciones por vacante.
      </span>
    </div>
  );
}

/**
 * El marco de todas las pantallas: menú lateral en tinta (escritorio), barra
 * superior con la ruta y la empresa, y en móvil el menú como fila de pestañas.
 */
export function Marco({
  seccion,
  migas,
  children,
}: {
  seccion: Seccion | null;
  migas: ReactNode;
  children: ReactNode;
}) {
  const { data: sesion } = useSesion();
  const { data: mis } = useMisVacantes();
  const grupos = GRUPOS.filter((g) => sesion?.modulos.includes(g.modulo));

  const contador = (s: Seccion) =>
    s === "mis-vacantes" && mis ? `${mis.cupo.activas}/${mis.cupo.limite}` : null;

  return (
    <div className="flex min-h-screen bg-mist-50 text-ink-900">
      <aside
        aria-label="Navegación"
        className="sticky top-0 hidden h-screen w-[248px] shrink-0 flex-col gap-6 bg-ink-900 px-3.5 py-5 text-white lg:flex"
      >
        <Enlace
          href="/"
          className="flex items-center gap-2.5 rounded-xl px-2"
          aria-label="Vortex Ops, inicio"
        >
          <Logo />
          <span className="text-lg font-black tracking-[-0.03em]">
            VORTEX <i className="font-extrabold text-aqua-300">OPS</i>
          </span>
        </Enlace>
        {grupos.map((grupo) => (
          <nav key={grupo.modulo} aria-label={grupo.titulo} className="flex flex-col gap-0.5">
            <span className="px-3 pb-1.5 font-mono text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-400">
              {grupo.titulo}
            </span>
            {grupo.entradas.map((e) => {
              const activa = e.seccion === seccion;
              return (
                <Enlace
                  key={e.seccion}
                  href={e.href}
                  aria-current={activa ? "page" : undefined}
                  className={`relative flex min-h-[42px] items-center gap-2.5 rounded-xl px-3 text-[14.5px] font-bold transition-colors ${
                    activa
                      ? "bg-ink-800 text-white before:absolute before:-left-3.5 before:bottom-2 before:top-2 before:w-1 before:rounded-r before:bg-aqua-300"
                      : "text-mist-300 hover:bg-ink-800/60 hover:text-white"
                  }`}
                >
                  <e.icono aria-hidden="true" className="h-[18px] w-[18px] shrink-0" />
                  {e.texto}
                  {contador(e.seccion) && (
                    <span className="ml-auto font-mono text-xs font-semibold">
                      {contador(e.seccion)}
                    </span>
                  )}
                </Enlace>
              );
            })}
          </nav>
        ))}
        {sesion && mis && <TuPlan plan={sesion.plan} cupo={mis.cupo} />}
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 border-b border-mist-200 bg-white">
          <div className="flex h-16 items-center gap-3.5 px-4 md:px-8">
            <span className="min-w-0 truncate text-sm text-mist-600">{migas}</span>
            {ES_DE_EJEMPLO && (
              <Badge variant="brand" className="hidden sm:inline-flex">
                Datos de ejemplo
              </Badge>
            )}
            {sesion && (
              <div className="ml-auto flex shrink-0 items-center gap-2.5 text-sm font-bold">
                <span className="hidden sm:inline">{sesion.empresa.nombre}</span>
                <span
                  role="img"
                  aria-label={`Tu cuenta: ${sesion.usuario.nombre}`}
                  className="grid h-9 w-9 place-items-center rounded-full bg-ink-900 font-mono text-xs font-semibold text-aqua-300"
                >
                  {sesion.usuario.iniciales}
                </span>
              </div>
            )}
          </div>
          <nav aria-label="Secciones" className="flex gap-1 overflow-x-auto px-3 pb-2 lg:hidden">
            {grupos
              .flatMap((g) => g.entradas)
              .map((e) => (
                <Enlace
                  key={e.seccion}
                  href={e.href}
                  aria-current={e.seccion === seccion ? "page" : undefined}
                  className={`shrink-0 rounded-full px-3.5 py-1.5 text-sm font-bold ${
                    e.seccion === seccion
                      ? "bg-ink-900 text-white"
                      : "text-mist-700 hover:bg-mist-100"
                  }`}
                >
                  {e.texto}
                  {contador(e.seccion) && (
                    <span className="ml-1.5 font-mono text-xs">{contador(e.seccion)}</span>
                  )}
                </Enlace>
              ))}
          </nav>
        </header>
        <main className="flex flex-col gap-5 px-4 pb-14 pt-7 md:px-8">{children}</main>
      </div>
    </div>
  );
}

/** Encabezado de pantalla: etiqueta en mono, título grande y acción opcional. */
export function Encabezado({
  etiqueta,
  titulo,
  accion,
}: {
  etiqueta: ReactNode;
  titulo: ReactNode;
  accion?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div>
        <span className="font-mono text-[11px] font-semibold uppercase tracking-[0.08em] text-aqua-700">
          {etiqueta}
        </span>
        <h1 className="mt-2 text-[2.1rem] font-extrabold leading-none tracking-[-0.04em] md:text-[2.75rem]">
          {titulo}
        </h1>
      </div>
      {accion}
    </div>
  );
}
