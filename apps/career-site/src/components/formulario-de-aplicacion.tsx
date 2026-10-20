"use client";

import { Button } from "@vortex/ui";
import { Send } from "lucide-react";
import Script from "next/script";
import { type ReactNode, useActionState, useEffect, useId } from "react";

import type { CampoDelFormulario, ResultadoDeAplicar } from "../lib/tipos-de-aplicacion";
import { AvisoDePrivacidad } from "./aviso-de-privacidad";

type Accion = (
  anterior: ResultadoDeAplicar | null,
  formulario: FormData,
) => Promise<ResultadoDeAplicar>;

declare global {
  interface Window {
    turnstile?: { reset: () => void };
  }
}

const CLASE_CAMPO =
  "mt-1.5 block w-full rounded-xl border-[1.5px] border-mist-200 bg-white px-3.5 py-2.5 text-[15px] font-normal text-ink-900 placeholder:text-mist-500 focus:border-aqua-500 focus:outline-none focus:ring-2 focus:ring-aqua-500/30 aria-[invalid=true]:border-red-500";

function Campo({
  etiqueta,
  ayuda,
  error,
  idError,
  children,
}: {
  etiqueta: string;
  ayuda?: string | undefined;
  error?: string | undefined;
  idError?: string | undefined;
  children: ReactNode;
}) {
  return (
    <div>
      {/* biome-ignore lint/a11y/noLabelWithoutControl: el control llega en `children`, dentro del label. */}
      <label className="block text-sm font-bold text-ink-900">
        {etiqueta}
        {ayuda && <span className="ml-1.5 font-normal text-mist-600">{ayuda}</span>}
        {children}
      </label>
      {error && (
        <p id={idError} className="mt-1 text-[13px] font-semibold text-red-600">
          {error}
        </p>
      )}
    </div>
  );
}

/**
 * El formulario para aplicar a una vacante. La validación de verdad es del
 * servidor (`lib/aplicacion.ts`); aquí solo se pinta lo que responde.
 */
export function FormularioDeAplicacion({
  accion,
  empresa,
  sitekey,
}: {
  accion: Accion;
  empresa: string;
  /** La site key de Turnstile; sin ella el widget no se pinta. */
  sitekey: string | null;
}) {
  const [resultado, enviar, enviando] = useActionState(accion, null);
  const id = useId();

  // Un token de Turnstile vale una sola vez: tras un error hace falta otro.
  useEffect(() => {
    if (resultado?.estado === "error") window.turnstile?.reset();
  }, [resultado]);

  if (resultado?.estado === "ok") {
    return (
      <output className="block rounded-xl bg-aqua-50 px-4 py-4 text-[15px] text-ink-900">
        <p className="font-extrabold">Listo, recibimos tu aplicación.</p>
        <p className="mt-1 text-mist-700">
          Tu CV ya está con {empresa}. Si avanzas, te escriben al correo que dejaste.
        </p>
      </output>
    );
  }

  const errores: Partial<Record<CampoDelFormulario, string>> =
    resultado?.estado === "error" ? (resultado.campos ?? {}) : {};
  const idDe = (campo: CampoDelFormulario) => `${id}-${campo}`;
  const invalido = (campo: CampoDelFormulario) =>
    errores[campo] ? { "aria-invalid": true, "aria-describedby": idDe(campo) } : {};

  return (
    <form action={enviar} aria-label="Aplicar a la vacante" className="flex flex-col gap-4">
      <Campo etiqueta="Nombre completo" error={errores.nombre} idError={idDe("nombre")}>
        <input
          name="nombre"
          required
          maxLength={200}
          autoComplete="name"
          className={CLASE_CAMPO}
          {...invalido("nombre")}
        />
      </Campo>
      <Campo etiqueta="Correo" error={errores.correo} idError={idDe("correo")}>
        <input
          name="correo"
          type="email"
          required
          autoComplete="email"
          className={CLASE_CAMPO}
          {...invalido("correo")}
        />
      </Campo>
      <Campo etiqueta="Tu puesto actual" ayuda="(opcional)">
        <input
          name="titular"
          maxLength={140}
          placeholder="Ej.: Analista de datos en Grupo Cobalto"
          className={CLASE_CAMPO}
        />
      </Campo>
      <Campo
        etiqueta="Perfil de LinkedIn"
        ayuda="(opcional)"
        error={errores.linkedin}
        idError={idDe("linkedin")}
      >
        <input
          name="linkedin"
          type="url"
          placeholder="https://www.linkedin.com/in/…"
          className={CLASE_CAMPO}
          {...invalido("linkedin")}
        />
      </Campo>
      <Campo
        etiqueta="Tu CV"
        ayuda="PDF o Word (.docx), hasta 4 MB"
        error={errores.cv}
        idError={idDe("cv")}
      >
        <input
          name="cv"
          type="file"
          required
          accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
          className={`${CLASE_CAMPO} file:mr-3 file:rounded-lg file:border-0 file:bg-ink-900 file:px-3 file:py-1.5 file:text-sm file:font-bold file:text-white`}
          {...invalido("cv")}
        />
      </Campo>

      {/* Trampa para bots: una persona no la ve ni la llena. */}
      <div aria-hidden="true" className="absolute -left-[9999px] h-px w-px overflow-hidden">
        <label>
          Tu sitio web
          <input name="sitio_web" tabIndex={-1} autoComplete="off" />
        </label>
      </div>

      <label className="flex items-start gap-2.5 text-sm text-mist-700">
        <input name="sin_ia" type="checkbox" className="mt-0.5 h-4 w-4 accent-ink-900" />
        <span>Evaluar mi CV sin procesos automatizados</span>
      </label>

      <AvisoDePrivacidad empresa={empresa} />

      <div>
        <label className="flex items-start gap-2.5 text-sm font-semibold text-ink-900">
          <input
            name="acepta"
            type="checkbox"
            required
            className="mt-0.5 h-4 w-4 accent-ink-900"
            {...invalido("acepta")}
          />
          <span>Leí y acepto el aviso de privacidad</span>
        </label>
        {errores.acepta && (
          <p id={idDe("acepta")} className="mt-1 text-[13px] font-semibold text-red-600">
            {errores.acepta}
          </p>
        )}
      </div>

      {sitekey && (
        <>
          <Script src="https://challenges.cloudflare.com/turnstile/v0/api.js" async defer />
          <div className="cf-turnstile" data-sitekey={sitekey} data-language="es" />
        </>
      )}

      {resultado?.estado === "error" && (
        <p role="alert" className="text-sm font-bold text-red-600">
          {resultado.mensaje}
        </p>
      )}

      <Button type="submit" size="lg" disabled={enviando}>
        <Send className="h-4 w-4" />
        {enviando ? "Enviando…" : "Enviar mi aplicación"}
      </Button>
    </form>
  );
}
