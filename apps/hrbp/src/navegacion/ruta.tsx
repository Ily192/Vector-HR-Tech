/**
 * Navegación del panel: un router mínimo sobre la History API.
 *
 * El panel tiene cuatro pantallas y un tope de 90 KB (brotli) para el bundle
 * principal, que ya gasta 76 KB en React y TanStack Query. Un router completo
 * se comería casi todo el margen, así que basta con esto: leer la ruta con
 * `useSyncExternalStore`, cambiarla con `pushState` y resolverla en una función
 * pura. Vercel ya reescribe toda ruta a `index.html` (vercel.json).
 */
import { type AnchorHTMLAttributes, type MouseEvent, useSyncExternalStore } from "react";

/** Pantallas del panel y sus parámetros. */
export type Ruta =
  | { pantalla: "inicio" }
  | { pantalla: "mis-vacantes" }
  | { pantalla: "crear-empleo" }
  | { pantalla: "pipeline"; vacanteId: string }
  | { pantalla: "no-encontrada" };

/** Traduce una ruta de la URL a la pantalla que le toca. */
export function resolverRuta(pathname: string): Ruta {
  const partes = pathname.split("/").filter(Boolean);
  if (partes.length === 0) return { pantalla: "inicio" };
  if (partes[0] !== "vacantes" || partes.length > 2) return { pantalla: "no-encontrada" };
  if (partes.length === 1) return { pantalla: "mis-vacantes" };
  const [, segunda = ""] = partes;
  return segunda === "nueva"
    ? { pantalla: "crear-empleo" }
    : { pantalla: "pipeline", vacanteId: decodeURIComponent(segunda) };
}

const EVENTO_NAVEGAR = "vortex:navegar";

function suscribir(avisar: () => void) {
  window.addEventListener("popstate", avisar);
  window.addEventListener(EVENTO_NAVEGAR, avisar);
  return () => {
    window.removeEventListener("popstate", avisar);
    window.removeEventListener(EVENTO_NAVEGAR, avisar);
  };
}

/** La ruta actual; el componente se vuelve a pintar cuando cambia. */
export function useRuta(): string {
  return useSyncExternalStore(suscribir, () => window.location.pathname);
}

/** Cambia de pantalla sin recargar. */
export function navegar(destino: string) {
  window.history.pushState(null, "", destino);
  window.dispatchEvent(new Event(EVENTO_NAVEGAR));
  window.scrollTo({ top: 0 });
}

type EnlaceProps = AnchorHTMLAttributes<HTMLAnchorElement> & { href: string };

/**
 * Un `<a>` de verdad (se puede abrir en otra pestaña o copiar) que, con un clic
 * normal, navega sin recargar.
 */
export function Enlace({ href, onClick, ...props }: EnlaceProps) {
  function alHacerClic(evento: MouseEvent<HTMLAnchorElement>) {
    onClick?.(evento);
    const conModificador = evento.metaKey || evento.ctrlKey || evento.shiftKey || evento.altKey;
    if (evento.defaultPrevented || evento.button !== 0 || conModificador) return;
    evento.preventDefault();
    navegar(href);
  }
  return <a href={href} onClick={alHacerClic} {...props} />;
}
