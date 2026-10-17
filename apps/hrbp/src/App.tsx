import { type ReactNode, Suspense, lazy, useEffect } from "react";

import { useSesion } from "./datos/consultas";
import { Marco, type Seccion } from "./marco/marco";
import { Enlace, type Ruta, resolverRuta, useRuta } from "./navegacion/ruta";

// Cada pantalla es su propio chunk: el bundle principal solo lleva el marco (tope de 90 KB).
const Cockpit = lazy(() => import("./pantallas/cockpit").then((m) => ({ default: m.Cockpit })));
const MisVacantes = lazy(() =>
  import("./pantallas/mis-vacantes").then((m) => ({ default: m.MisVacantes })),
);
const CrearEmpleo = lazy(() =>
  import("./pantallas/crear-empleo").then((m) => ({ default: m.CrearEmpleo })),
);
const Pipeline = lazy(() => import("./pantallas/pipeline").then((m) => ({ default: m.Pipeline })));

interface Vista {
  seccion: Seccion | null;
  titulo: string;
  migas: ReactNode;
  contenido: ReactNode;
}

const raiz = (texto: string) => (
  <Enlace href="/vacantes" className="hover:text-ink-900">
    {texto}
  </Enlace>
);

function vistaDe(ruta: Ruta, conCockpit: boolean): Vista {
  switch (ruta.pantalla) {
    case "inicio":
      return conCockpit
        ? {
            seccion: "hoy",
            titulo: "Hoy",
            migas: <b className="text-ink-900">Hoy</b>,
            contenido: <Cockpit />,
          }
        : vistaDe({ pantalla: "mis-vacantes" }, conCockpit);
    case "mis-vacantes":
      return {
        seccion: "mis-vacantes",
        titulo: "Mis vacantes",
        migas: (
          <>
            Career site / <b className="text-ink-900">Mis vacantes</b>
          </>
        ),
        contenido: <MisVacantes />,
      };
    case "crear-empleo":
      return {
        seccion: "crear-empleo",
        titulo: "Crear empleo",
        migas: (
          <>
            Career site / <b className="text-ink-900">Crear empleo</b>
          </>
        ),
        contenido: <CrearEmpleo />,
      };
    case "pipeline":
      return {
        seccion: "mis-vacantes",
        titulo: "Aplicados",
        migas: (
          <>
            Career site / {raiz("Mis vacantes")} / <b className="text-ink-900">Aplicados</b>
          </>
        ),
        contenido: <Pipeline vacanteId={ruta.vacanteId} />,
      };
    case "no-encontrada":
      return {
        seccion: null,
        titulo: "Página no encontrada",
        migas: "Vortex Ops",
        contenido: (
          <section className="max-w-xl rounded-[22px] border border-mist-200 bg-white p-6">
            <h1 className="text-2xl">No encontramos esta página</h1>
            <p className="mt-2 text-mist-700">Revisa la dirección o vuelve al inicio.</p>
            <Enlace href="/" className="mt-4 inline-block font-bold text-aqua-700 hover:underline">
              Ir al inicio
            </Enlace>
          </section>
        ),
      };
  }
}

/** El panel de la empresa: elige la pantalla según la URL y los módulos del plan. */
export function App() {
  const { data: sesion } = useSesion();
  const ruta = resolverRuta(useRuta());
  const vista = vistaDe(ruta, sesion?.modulos.includes("cockpit") ?? false);

  useEffect(() => {
    document.title = `${vista.titulo} · Vortex Ops`;
  }, [vista.titulo]);

  if (!sesion) return null;
  return (
    <Marco seccion={vista.seccion} migas={vista.migas}>
      <Suspense fallback={null}>{vista.contenido}</Suspense>
    </Marco>
  );
}
