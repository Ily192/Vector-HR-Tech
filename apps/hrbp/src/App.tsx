import { type ReactNode, Suspense, lazy, useEffect } from "react";

import { useSesion, useSesionEnVivo } from "./datos/consultas";
import { SinAccesoAlPanel } from "./datos/tipos";
import { Marco, type Seccion } from "./marco/marco";
import {
  Enlace,
  RUTA_DE_VERIFICAR,
  type Ruta,
  manifiestoDe,
  navegar,
  resolverRuta,
  useRuta,
} from "./navegacion/ruta";

// Cada pantalla es su propio chunk: el bundle principal solo lleva el marco (tope de 90 KB).
const Cockpit = lazy(() => import("./pantallas/cockpit").then((m) => ({ default: m.Cockpit })));
const MisVacantes = lazy(() =>
  import("./pantallas/mis-vacantes").then((m) => ({ default: m.MisVacantes })),
);
const CrearEmpleo = lazy(() =>
  import("./pantallas/crear-empleo").then((m) => ({ default: m.CrearEmpleo })),
);
const Pipeline = lazy(() => import("./pantallas/pipeline").then((m) => ({ default: m.Pipeline })));
const Entrar = lazy(() => import("./pantallas/entrar").then((m) => ({ default: m.Entrar })));
const ErrorDeSesion = lazy(() =>
  import("./pantallas/entrar").then((m) => ({ default: m.ErrorDeSesion })),
);
const Admin = lazy(() => import("./pantallas/admin").then((m) => ({ default: m.Admin })));

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
            Bolsa de empleo / <b className="text-ink-900">Mis vacantes</b>
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
            Bolsa de empleo / <b className="text-ink-900">Crear empleo</b>
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
            Bolsa de empleo / {raiz("Mis vacantes")} / <b className="text-ink-900">Aplicados</b>
          </>
        ),
        contenido: <Pipeline vacanteId={ruta.vacanteId} />,
      };
    // Con su propio marco, para el teléfono: `App` lo pinta sin el del panel.
    case "admin":
      return { seccion: "admin", titulo: "Admin", migas: "Admin", contenido: <Admin /> };
    case "no-encontrada":
      return {
        seccion: null,
        titulo: "Página no encontrada",
        migas: "Vector HR Tech",
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

/**
 * El panel de la empresa: sin sesión pide entrar; con ella elige la pantalla
 * según la URL y los módulos del plan.
 */
export function App() {
  useSesionEnVivo();
  const { data: sesion, error, refetch } = useSesion();
  const pathname = useRuta();
  const ruta = resolverRuta(pathname);
  const vista = vistaDe(ruta, sesion?.modulos.includes("cockpit") ?? false);
  const titulo = sesion === null ? "Entrar" : vista.titulo;
  const esAdmin = ruta.pantalla === "admin";

  useEffect(() => {
    document.title = `${titulo} · Vector HR Tech`;
  }, [titulo]);

  // Instalada desde /admin, la app abre en /admin (public/admin.webmanifest); desde el
  // resto, el panel. Chrome y Safari leen el manifiesto, el ícono y el título que haya
  // en la página al instalar.
  useEffect(() => {
    document.querySelector('link[rel="manifest"]')?.setAttribute("href", manifiestoDe(pathname));
    document
      .querySelector('link[rel="apple-touch-icon"]')
      ?.setAttribute("href", `/iconos/${esAdmin ? "admin" : "panel"}-apple-touch-icon.png`);
    document
      .querySelector('meta[name="apple-mobile-web-app-title"]')
      ?.setAttribute("content", esAdmin ? "VHR Admin" : "Vector HR");
  }, [pathname, esAdmin]);

  // Con la sesión abierta, `/verificar#correo=…` (el registro desde la web) es el inicio.
  useEffect(() => {
    if (sesion && window.location.pathname === RUTA_DE_VERIFICAR) {
      navegar("/", { reemplazar: true });
    }
  }, [sesion]);

  // Un enlace ya usado vuelve con `#error_code=…` aunque la sesión siga viva: se limpia.
  useEffect(() => {
    if (sesion && new URLSearchParams(window.location.hash.slice(1)).has("error_code")) {
      window.history.replaceState(
        window.history.state,
        "",
        window.location.pathname + window.location.search,
      );
    }
  }, [sesion]);

  // El área de admin no pide acceso al panel: lo decide el hr-engine con la sesión.
  if (esAdmin && sesion !== null && (sesion || error instanceof SinAccesoAlPanel)) {
    return <Suspense fallback={null}>{vista.contenido}</Suspense>;
  }
  if (error) {
    return (
      <Suspense fallback={null}>
        <ErrorDeSesion error={error} reintentar={() => void refetch()} />
      </Suspense>
    );
  }
  if (sesion === null) {
    return (
      <Suspense fallback={null}>
        <Entrar />
      </Suspense>
    );
  }
  if (!sesion) return null;
  return (
    <Marco seccion={vista.seccion} migas={vista.migas}>
      <Suspense fallback={null}>{vista.contenido}</Suspense>
    </Marco>
  );
}
