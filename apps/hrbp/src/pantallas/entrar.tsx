import { Button } from "@vortex/ui";
import { type FormEvent, type ReactNode, useState } from "react";

import { useEntrar, useSalir } from "../datos/consultas";
import { SinAccesoAlPanel } from "../datos/tipos";

/**
 * Un enlace vencido o ya usado vuelve con el error en el hash (`#error_code=…`).
 * Se lee una vez, al cargar la pantalla, y se quita de la URL.
 */
function leerErrorDelEnlace(): boolean {
  const hash = new URLSearchParams(window.location.hash.slice(1));
  if (!hash.has("error") && !hash.has("error_code")) return false;
  window.history.replaceState(
    window.history.state,
    "",
    window.location.pathname + window.location.search,
  );
  return true;
}

const ENLACE_CON_ERROR = leerErrorDelEnlace();

function Tarjeta({ titulo, children }: { titulo: string; children: ReactNode }) {
  return (
    <main className="grid min-h-screen place-items-center bg-mist-50 px-4 py-10 text-ink-900">
      <section className="flex w-full max-w-md flex-col gap-4 rounded-[22px] border border-mist-200 bg-white p-6 md:p-8">
        <span className="text-lg font-black tracking-[-0.03em]">
          VORTEX <i className="font-extrabold text-aqua-600">OPS</i>
        </span>
        <h1 className="text-[28px] leading-tight tracking-[-0.02em]">{titulo}</h1>
        {children}
      </section>
    </main>
  );
}

const CONTACTO = (
  <a href="mailto:hola@vectorhr.tech" className="font-bold text-aqua-700 hover:underline">
    hola@vectorhr.tech
  </a>
);

/**
 * Entrar al panel con un enlace al correo, sin contraseña. Las cuentas las crea
 * la invitación de Vector HR: aquí no hay registro.
 */
export function Entrar() {
  const entrar = useEntrar();
  const [correo, setCorreo] = useState("");

  function alEnviar(evento: FormEvent) {
    evento.preventDefault();
    entrar.mutate(correo);
  }

  if (entrar.data?.ok) {
    return (
      <Tarjeta titulo="Revisa tu correo">
        <output className="block text-[15px] text-mist-700">
          Si <b className="text-ink-900">{correo.trim()}</b> tiene una cuenta en Vortex Ops, te
          llegó un enlace para entrar. Dura una hora y sirve una vez. Si no lo ves, busca en spam.
        </output>
        <button
          type="button"
          onClick={() => entrar.reset()}
          className="self-start text-sm font-bold text-aqua-700 hover:underline"
        >
          Usar otro correo
        </button>
      </Tarjeta>
    );
  }

  const fallo =
    entrar.isError || entrar.data?.ok === false
      ? entrar.data?.ok === false && entrar.data.motivo === "demasiados-intentos"
        ? "Ya te mandamos un enlace hace poco. Espera un minuto antes de pedir otro."
        : "No pudimos mandar el enlace. Inténtalo de nuevo en unos minutos."
      : null;

  return (
    <Tarjeta titulo="Entra a tu panel">
      <p className="text-[15px] text-mist-700">
        Te mandamos un enlace a tu correo para entrar, sin contraseña.
      </p>
      {ENLACE_CON_ERROR && (
        <p role="alert" className="rounded-2xl bg-flame-50 p-4 text-sm text-flame-700">
          Ese enlace ya no sirve: dura una hora y se usa una sola vez. Pide otro.
        </p>
      )}
      <form onSubmit={alEnviar} aria-label="Entrar" className="flex flex-col gap-4">
        <label className="block text-sm font-bold">
          Correo de trabajo
          <input
            type="email"
            required
            autoComplete="email"
            value={correo}
            onChange={(e) => setCorreo(e.target.value)}
            placeholder="tu@empresa.com"
            className="mt-1.5 block w-full rounded-xl border-[1.5px] border-mist-200 bg-white px-3.5 py-2.5 text-[15px] font-normal text-ink-900 placeholder:text-mist-500 focus:border-aqua-500 focus:outline-none focus:ring-2 focus:ring-aqua-500/30"
          />
        </label>
        {fallo && (
          <p role="alert" className="text-sm font-bold text-danger-700">
            {fallo}
          </p>
        )}
        <Button type="submit" disabled={entrar.isPending}>
          Mandarme el enlace
        </Button>
      </form>
      <p className="text-sm text-mist-600">
        ¿Tu empresa aún no usa Vortex Ops? Escríbenos a {CONTACTO}.
      </p>
    </Tarjeta>
  );
}

/** La sesión no cargó: la cuenta no tiene acceso al panel o falló la red. */
export function ErrorDeSesion({ error, reintentar }: { error: Error; reintentar: () => void }) {
  const salir = useSalir();
  const sinAcceso = error instanceof SinAccesoAlPanel;
  return (
    <Tarjeta titulo={sinAcceso ? "Tu cuenta no tiene acceso" : "No pudimos abrir tu panel"}>
      <p className="text-[15px] text-mist-700">
        {sinAcceso ? (
          <>
            El panel es para HR y Dirección de las empresas que usan Vortex Ops. Si crees que es un
            error, escríbenos a {CONTACTO}.
          </>
        ) : (
          "Revisa tu conexión y vuelve a intentarlo."
        )}
      </p>
      <div className="flex flex-wrap gap-3">
        {!sinAcceso && <Button onClick={reintentar}>Reintentar</Button>}
        <Button variant="secondary" disabled={salir.isPending} onClick={() => salir.mutate()}>
          Salir
        </Button>
      </div>
    </Tarjeta>
  );
}
