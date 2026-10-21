import { useEffect, useRef } from "react";

declare global {
  interface Window {
    turnstile?: {
      render: (
        el: HTMLElement,
        opciones: {
          sitekey: string;
          theme?: "dark" | "light" | "auto";
          language?: string;
          callback: (token: string) => void;
          "expired-callback"?: () => void;
          "error-callback"?: () => void;
        },
      ) => string;
      remove: (id: string) => void;
    };
  }
}

const SCRIPT = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";

let cargando: Promise<void> | null = null;

function cargarScript(): Promise<void> {
  if (window.turnstile) return Promise.resolve();
  cargando ??= new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = SCRIPT;
    s.async = true;
    s.onload = () => resolve();
    s.onerror = () => {
      cargando = null;
      reject(new Error("no cargó Turnstile"));
    };
    document.head.appendChild(s);
  });
  return cargando;
}

/**
 * El captcha de Cloudflare, el mismo del career site. El token lo verifica el worker
 * del hr-engine antes de avisar; sin site key (local, tests) no se pinta nada.
 */
export function Turnstile({
  siteKey,
  onToken,
}: {
  siteKey: string;
  onToken: (token: string | null) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let id: string | null = null;
    let vivo = true;
    cargarScript()
      .then(() => {
        if (!vivo || !ref.current || !window.turnstile) return;
        id = window.turnstile.render(ref.current, {
          sitekey: siteKey,
          theme: "dark",
          language: "es",
          callback: (token) => onToken(token),
          "expired-callback": () => onToken(null),
          "error-callback": () => onToken(null),
        });
      })
      .catch(() => onToken(null));
    return () => {
      vivo = false;
      if (id && window.turnstile) window.turnstile.remove(id);
    };
  }, [siteKey, onToken]);

  return <div ref={ref} className="min-h-[65px]" />;
}
