import { Button, Wordmark } from "@fluveai/ui";
import { type FormEvent, type ReactNode, useEffect, useState } from "react";

import { useEntrar, useSalir, useVerificarCodigo } from "../datos/consultas";
import { SinAccesoAlPanel } from "../datos/tipos";
import { RUTA_DE_VERIFICAR, navegar } from "../navegacion/ruta";

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

/**
 * Quien se registra en vectorhrtech.com/publicar-vacantes vuelve a `/verificar#correo=…`
 * con el código ya enviado. El correo viaja en el fragmento, que el navegador no manda a
 * ningún servidor; se lee una vez, al cargar, y se quita de la URL.
 */
export function leerCorreoDeLaUrl(): string | null {
  if (window.location.pathname !== RUTA_DE_VERIFICAR) return null;
  const correo = new URLSearchParams(window.location.hash.slice(1)).get("correo")?.trim() ?? "";
  if (window.location.hash) {
    window.history.replaceState(
      window.history.state,
      "",
      window.location.pathname + window.location.search,
    );
  }
  return correo.includes("@") ? correo : null;
}

const ENLACE_CON_ERROR = leerErrorDelEnlace();
/** Se usa una vez: si la persona sale después, vuelve a la pantalla de entrar normal. */
let correoDelRegistro = leerCorreoDeLaUrl();

const CAMPO =
  "mt-1.5 block w-full rounded-xl border-[1.5px] border-mist-200 bg-white px-3.5 py-2.5 text-[15px] font-normal text-ink-900 placeholder:text-mist-500 focus:border-aqua-500 focus:outline-none focus:ring-2 focus:ring-aqua-500/30";

function Tarjeta({ titulo, children }: { titulo: string; children: ReactNode }) {
  return (
    <main className="grid min-h-screen place-items-center bg-mist-50 px-4 py-10 text-ink-900">
      <section className="flex w-full max-w-md flex-col gap-4 rounded-[22px] border border-mist-200 bg-white p-6 md:p-8">
        <Wordmark brand="vector" size="sm" tone="light" />
        <h1 className="text-[28px] leading-tight tracking-[-0.02em]">{titulo}</h1>
        {children}
      </section>
    </main>
  );
}

const CONTACTO = (
  <a href="mailto:hola@vectorhrtech.com" className="font-bold text-aqua-700 hover:underline">
    hola@vectorhrtech.com
  </a>
);

/** El registro gratis para publicar vacantes, en la web de Vector HR Tech. */
const PUBLICAR_VACANTES_URL = "https://vectorhrtech.com/publicar-vacantes";

/** Lo que Auth pide esperar entre dos correos a la misma cuenta (GOTRUE_SMTP_MAX_FREQUENCY). */
export const ESPERA_PARA_REENVIAR_S = 60;

/** Cuenta atrás de segundos; `reiniciar` vuelve a empezar desde `desde`. */
function useCuentaAtras(desde: number) {
  const [restante, setRestante] = useState(desde);
  useEffect(() => {
    if (restante <= 0) return;
    const temporizador = setTimeout(() => setRestante((r) => r - 1), 1000);
    return () => clearTimeout(temporizador);
  }, [restante]);
  return [restante, () => setRestante(desde)] as const;
}

/**
 * Entrar al panel con un código de 6 dígitos que llega al correo, sin contraseña ni
 * enlace. Las cuentas las crea el registro en vectorhrtech.com/publicar-vacantes (que
 * vuelve a `/verificar` con el código ya enviado) o una invitación de Vector HR.
 */
export function Entrar() {
  const [delRegistro] = useState(() => {
    const correo = correoDelRegistro;
    correoDelRegistro = null;
    return correo;
  });
  const [correo, setCorreo] = useState(delRegistro ?? "");
  const [paso, setPaso] = useState<"correo" | "codigo">(delRegistro ? "codigo" : "correo");

  if (paso === "codigo") {
    return (
      <EscribirCodigo
        correo={correo.trim()}
        desdeElRegistro={delRegistro !== null && correo === delRegistro}
        usarOtroCorreo={() => setPaso("correo")}
      />
    );
  }
  return <PedirCodigo correo={correo} setCorreo={setCorreo} alMandar={() => setPaso("codigo")} />;
}

function PedirCodigo({
  correo,
  setCorreo,
  alMandar,
}: {
  correo: string;
  setCorreo: (correo: string) => void;
  alMandar: () => void;
}) {
  const entrar = useEntrar();

  function alEnviar(evento: FormEvent) {
    evento.preventDefault();
    entrar.mutate(correo, { onSuccess: (r) => r.ok && alMandar() });
  }

  const fallo =
    entrar.isError || entrar.data?.ok === false
      ? entrar.data?.ok === false && entrar.data.motivo === "demasiados-intentos"
        ? "Ya te mandamos un código hace poco. Espera un minuto antes de pedir otro."
        : "No pudimos mandar el código. Inténtalo de nuevo en unos minutos."
      : null;

  return (
    <Tarjeta titulo="Entra a tu panel">
      <p className="text-[15px] text-mist-700">
        Te mandamos un código de 6 dígitos a tu correo para entrar, sin contraseña.
      </p>
      {ENLACE_CON_ERROR && (
        <p role="alert" className="rounded-2xl bg-flame-50 p-4 text-sm text-flame-700">
          Ese enlace ya no sirve: dura 15 minutos y se usa una sola vez. Pide un código.
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
            className={CAMPO}
          />
        </label>
        {fallo && (
          <p role="alert" className="text-sm font-bold text-danger-700">
            {fallo}
          </p>
        )}
        <Button type="submit" disabled={entrar.isPending}>
          Mandarme el código
        </Button>
      </form>
      <p className="text-sm text-mist-600">
        ¿Aún no publicas con nosotros?{" "}
        <a href={PUBLICAR_VACANTES_URL} className="font-bold text-aqua-700 hover:underline">
          Regístrate gratis
        </a>
        .
      </p>
    </Tarjeta>
  );
}

const MENSAJE_DE_VERIFICAR = {
  "codigo-invalido": "El código no es correcto o ya venció. Revísalo o pide otro.",
  "demasiados-intentos": "Demasiados intentos. Espera unos minutos y vuelve a probar.",
  error: "No pudimos revisar el código. Inténtalo de nuevo.",
} as const;

function EscribirCodigo({
  correo,
  desdeElRegistro,
  usarOtroCorreo,
}: {
  correo: string;
  desdeElRegistro: boolean;
  usarOtroCorreo: () => void;
}) {
  const verificar = useVerificarCodigo();
  const reenviar = useEntrar();
  const [codigo, setCodigo] = useState("");
  // El código acaba de salir: Auth no manda otro a la misma cuenta antes de un minuto.
  const [restante, reiniciar] = useCuentaAtras(ESPERA_PARA_REENVIAR_S);

  function alEnviar(evento: FormEvent) {
    evento.preventDefault();
    verificar.mutate(
      { correo, codigo },
      {
        onSuccess: (r) => {
          // La sesión llega por `alCambiarLaSesion`; aquí solo se deja la URL limpia.
          if (r.ok && window.location.pathname === RUTA_DE_VERIFICAR) {
            navegar("/", { reemplazar: true });
          }
        },
      },
    );
  }

  function alReenviar() {
    setCodigo("");
    verificar.reset();
    reenviar.mutate(correo, { onSuccess: (r) => r.ok && reiniciar() });
  }

  const fallo = verificar.isError
    ? MENSAJE_DE_VERIFICAR.error
    : verificar.data?.ok === false
      ? MENSAJE_DE_VERIFICAR[verificar.data.motivo]
      : reenviar.isError || reenviar.data?.ok === false
        ? "No pudimos mandar otro código. Espera un minuto y vuelve a probar."
        : null;

  return (
    <Tarjeta titulo="Escribe tu código">
      <p className="text-[15px] text-mist-700">
        {desdeElRegistro ? (
          <>
            Te mandamos un código de 6 dígitos a <b className="text-ink-900">{correo}</b> para
            entrar a tu panel. Dura 15 minutos. Si no lo ves, busca en spam.
          </>
        ) : (
          <>
            Si <b className="text-ink-900">{correo}</b> tiene una cuenta en el panel de Vector HR
            Tech, te llegó un código de 6 dígitos. Dura 15 minutos. Si no lo ves, busca en spam.
          </>
        )}
      </p>
      <form onSubmit={alEnviar} aria-label="Código para entrar" className="flex flex-col gap-4">
        <label className="block text-sm font-bold">
          Código de 6 dígitos
          <input
            type="text"
            required
            inputMode="numeric"
            autoComplete="one-time-code"
            pattern="[0-9]{6}"
            maxLength={6}
            value={codigo}
            onChange={(e) => setCodigo(e.target.value.replace(/\D/g, "").slice(0, 6))}
            placeholder="123456"
            className={`${CAMPO} font-mono tracking-[0.3em]`}
          />
        </label>
        {fallo && (
          <p role="alert" className="text-sm font-bold text-danger-700">
            {fallo}
          </p>
        )}
        {reenviar.data?.ok && restante > 0 && !fallo && (
          <output className="text-sm text-mist-700">Te mandamos otro código.</output>
        )}
        <Button type="submit" disabled={verificar.isPending || codigo.length !== 6}>
          Entrar
        </Button>
      </form>
      <div className="flex flex-wrap gap-x-5 gap-y-2">
        <button
          type="button"
          onClick={alReenviar}
          disabled={restante > 0 || reenviar.isPending}
          className="text-sm font-bold text-aqua-700 hover:underline disabled:cursor-not-allowed disabled:text-mist-500 disabled:no-underline"
        >
          {restante > 0 ? `Reenviar código (${restante} s)` : "Reenviar código"}
        </button>
        <button
          type="button"
          onClick={usarOtroCorreo}
          className="text-sm font-bold text-aqua-700 hover:underline"
        >
          Usar otro correo
        </button>
      </div>
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
            El panel es para HR y Dirección de las empresas que publican con Vector HR Tech. Si
            crees que es un error, escríbenos a {CONTACTO}.
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
