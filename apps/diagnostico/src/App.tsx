import { type FormEvent, useCallback, useMemo, useState } from "react";

import { Constellation } from "./Constelacion";
import {
  ASUNTO_NEGATIVA,
  AVISO_COMPLETO,
  CONTACTO_PRIVACIDAD,
  DOMICILIO,
  RESPONSABLE,
  URL_AVISO_INTEGRAL,
} from "./aviso";
import {
  type Etapa,
  PORCENTAJE_RECUPERABLE,
  PREGUNTAS,
  type Pregunta,
  QUE_SIGNIFICA,
  type Respuestas,
  type Resultado,
  SEMANAS_POR_MES,
  TOP,
  calcular,
  estaRespondida,
  formatoHoras,
} from "./diagnostico";
import { ErrorDeEnvio, correoValido, enviarDiagnostico, leerOrigen } from "./envio";
import { Turnstile } from "./turnstile";

const SITIO = "https://vectorhrtech.com";
const CORREO = "hola@vectorhrtech.com";
const SITE_KEY = import.meta.env.VITE_TURNSTILE_SITE_KEY ?? "";

type Pantalla =
  | { tipo: "inicio" }
  | { tipo: "pregunta"; indice: number }
  | { tipo: "datos" }
  | { tipo: "resultado" };

const btnCta =
  "inline-flex min-h-12 items-center justify-center gap-2 rounded-full bg-flame-500 px-6 font-bold text-white shadow-cta transition hover:bg-flame-400 disabled:cursor-not-allowed disabled:opacity-50";
const btnGhost =
  "inline-flex min-h-12 items-center justify-center gap-2 rounded-full border border-white/15 px-6 font-semibold text-ink-200 transition hover:border-aqua-300 hover:text-white";

export function App() {
  const [pantalla, setPantalla] = useState<Pantalla>({ tipo: "inicio" });
  const [respuestas, setRespuestas] = useState<Respuestas>({});
  const resultado = useMemo(() => calcular(respuestas), [respuestas]);

  const irA = (siguiente: Pantalla) => {
    setPantalla(siguiente);
    window.scrollTo({ top: 0 });
  };

  const avanzar = (indice: number) =>
    irA(
      indice + 1 < PREGUNTAS.length ? { tipo: "pregunta", indice: indice + 1 } : { tipo: "datos" },
    );

  return (
    <div className="relative min-h-dvh overflow-hidden bg-aurora">
      <Constellation className="absolute inset-0 h-full w-full opacity-60" />
      <div className="relative mx-auto flex min-h-dvh max-w-2xl flex-col px-4 py-6 sm:px-6">
        <header className="flex items-center justify-between">
          <a
            href={SITIO}
            className="flex items-center gap-2 font-extrabold text-white no-underline"
          >
            <img src="/favicon.svg" alt="" className="h-8 w-8" />
            Vector HR Tech
          </a>
          <span className="text-sm text-ink-300">Diagnóstico gratuito</span>
        </header>

        <main className="flex flex-1 flex-col justify-center py-8">
          {pantalla.tipo === "inicio" && (
            <Inicio onEmpezar={() => irA({ tipo: "pregunta", indice: 0 })} />
          )}
          {pantalla.tipo === "pregunta" && (
            <PasoPregunta
              key={pantalla.indice}
              indice={pantalla.indice}
              respuestas={respuestas}
              onResponder={(id, valor) => setRespuestas((r) => ({ ...r, [id]: valor }))}
              onSiguiente={() => avanzar(pantalla.indice)}
              onAtras={() =>
                irA(
                  pantalla.indice === 0
                    ? { tipo: "inicio" }
                    : { tipo: "pregunta", indice: pantalla.indice - 1 },
                )
              }
            />
          )}
          {pantalla.tipo === "datos" && (
            <Datos
              resultado={resultado}
              respuestas={respuestas}
              onListo={() => irA({ tipo: "resultado" })}
              onAtras={() => irA({ tipo: "pregunta", indice: PREGUNTAS.length - 1 })}
            />
          )}
          {pantalla.tipo === "resultado" && (
            <ResultadoCompleto resultado={resultado} respuestas={respuestas} />
          )}
        </main>

        <footer className="text-center text-xs text-ink-400">
          Vector HR Tech · Hackeamos la rutina ·{" "}
          <a href={`mailto:${CORREO}`} className="underline hover:text-white">
            {CORREO}
          </a>
        </footer>
      </div>
    </div>
  );
}

function Inicio({ onEmpezar }: { onEmpezar: () => void }) {
  return (
    <section className="space-y-6">
      <p className="text-sm font-semibold uppercase tracking-widest text-aqua-300">
        Diagnóstico gratuito
      </p>
      <h1 className="text-4xl sm:text-5xl">
        ¿Qué proceso le quita <span className="text-brand-gradient">más tiempo</span> a tu equipo?
      </h1>
      <p className="text-lg text-ink-200">
        Responde {PREGUNTAS.length} preguntas sobre cómo trabaja tu equipo hoy. Te decimos cuáles
        son los 3 procesos de HR y operaciones que conviene atacar primero, si toca digitalizarlos,
        optimizarlos o automatizarlos, y cuántas horas al mes podrías recuperar.
      </p>
      <ul className="flex flex-wrap gap-x-6 gap-y-2 text-sm text-ink-300">
        <li>⏱ 3 minutos</li>
        <li>✓ Sin costo</li>
        <li>✓ Te mostramos cómo calculamos todo</li>
      </ul>
      <button type="button" className={btnCta} onClick={onEmpezar}>
        Empezar el diagnóstico →
      </button>
    </section>
  );
}

function Progreso({ indice }: { indice: number }) {
  const total = PREGUNTAS.length;
  return (
    <div className="space-y-2">
      <p className="text-sm text-ink-300">
        Pregunta {indice + 1} de {total}
      </p>
      <div className="h-1.5 overflow-hidden rounded-full bg-white/10" aria-hidden="true">
        <div
          className="h-full rounded-full bg-gradient-to-r from-flame-500 via-gold to-aqua-300 transition-all"
          style={{ width: `${((indice + 1) / total) * 100}%` }}
        />
      </div>
    </div>
  );
}

function PasoPregunta({
  indice,
  respuestas,
  onResponder,
  onSiguiente,
  onAtras,
}: {
  indice: number;
  respuestas: Respuestas;
  onResponder: (id: string, valor: string | string[]) => void;
  onSiguiente: () => void;
  onAtras: () => void;
}) {
  const pregunta = PREGUNTAS[indice] as Pregunta;
  const valor = respuestas[pregunta.id];
  const marcadas = Array.isArray(valor) ? valor : [];

  return (
    <section className="space-y-6">
      <Progreso indice={indice} />
      <fieldset className="space-y-4">
        <legend className="text-2xl font-extrabold text-white sm:text-3xl">
          {pregunta.titulo}
        </legend>
        {pregunta.ayuda && <p className="text-ink-300">{pregunta.ayuda}</p>}
        <div className="grid gap-3 pt-2">
          {pregunta.tipo === "una"
            ? pregunta.opciones.map((o) => {
                const elegida = valor === o.valor;
                return (
                  <button
                    key={o.valor}
                    type="button"
                    aria-pressed={elegida}
                    onClick={() => {
                      onResponder(pregunta.id, o.valor);
                      onSiguiente();
                    }}
                    className={`glass min-h-12 rounded-2xl px-5 py-3 text-left font-semibold transition hover:border-aqua-300 ${
                      elegida ? "!border-aqua-300 text-white" : "text-ink-200"
                    }`}
                  >
                    {o.etiqueta}
                  </button>
                );
              })
            : pregunta.opciones.map((o) => {
                const elegida = marcadas.includes(o.valor);
                return (
                  <label
                    key={o.valor}
                    className={`glass flex min-h-12 cursor-pointer items-center gap-3 rounded-2xl px-5 py-3 font-semibold transition hover:border-aqua-300 ${
                      elegida ? "!border-aqua-300 text-white" : "text-ink-200"
                    }`}
                  >
                    <input
                      type="checkbox"
                      className="h-5 w-5 accent-aqua-500"
                      checked={elegida}
                      onChange={() =>
                        onResponder(
                          pregunta.id,
                          elegida ? marcadas.filter((v) => v !== o.valor) : [...marcadas, o.valor],
                        )
                      }
                    />
                    {o.etiqueta}
                  </label>
                );
              })}
        </div>
      </fieldset>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <button type="button" className="text-ink-300 underline hover:text-white" onClick={onAtras}>
          ← Atrás
        </button>
        {pregunta.tipo === "varias" && (
          <button
            type="button"
            className={btnCta}
            onClick={() => {
              // Sin nada marcado también es una respuesta: ninguno.
              if (!estaRespondida(pregunta, respuestas)) onResponder(pregunta.id, []);
              onSiguiente();
            }}
          >
            {marcadas.length === 0 ? "Ninguno, siguiente →" : "Siguiente →"}
          </button>
        )}
      </div>
    </section>
  );
}

function Datos({
  resultado,
  respuestas,
  onListo,
  onAtras,
}: {
  resultado: Resultado;
  respuestas: Respuestas;
  onListo: () => void;
  onAtras: () => void;
}) {
  const [nombre, setNombre] = useState("");
  const [empresa, setEmpresa] = useState("");
  const [correo, setCorreo] = useState("");
  const [token, setToken] = useState<string | null>(null);
  const [sinFinesComerciales, setSinFinesComerciales] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const onToken = useCallback((t: string | null) => setToken(t), []);

  const correoOk = correoValido(correo.trim());
  const completo =
    nombre.trim() !== "" && empresa.trim() !== "" && correoOk && (!SITE_KEY || token !== null);

  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    if (!completo || enviando) return;
    setEnviando(true);
    setError(null);
    try {
      await enviarDiagnostico(
        { nombre, empresa, correo },
        leerOrigen(window.location.search),
        respuestas,
        resultado,
        token,
        sinFinesComerciales,
      );
      onListo();
    } catch (err) {
      setError(
        err instanceof ErrorDeEnvio && err.status === 429
          ? `Ya recibimos varios diagnósticos desde este correo o esta red. Intenta más tarde o escríbenos a ${CORREO}.`
          : `No pudimos guardar tu diagnóstico. Intenta de nuevo en un momento o escríbenos a ${CORREO}.`,
      );
      setEnviando(false);
    }
  };

  return (
    <section className="space-y-6">
      <p className="text-sm font-semibold uppercase tracking-widest text-aqua-300">
        Tu diagnóstico está listo
      </p>
      <h2 className="text-3xl">Estos son los 3 procesos que conviene atacar primero</h2>
      <ol className="space-y-2">
        {resultado.procesos.slice(0, TOP).map((p, i) => (
          <li
            key={p.id}
            className="glass flex items-center gap-3 rounded-2xl px-5 py-3 font-semibold text-white"
          >
            <span className="text-brand-gradient text-xl font-extrabold">{i + 1}</span>
            {p.nombre}
          </li>
        ))}
      </ol>
      <p className="text-ink-200">
        Déjanos tus datos para ver el detalle: qué toca hacer con cada uno, cuántas horas al mes
        podrías recuperar y cómo lo calculamos.
      </p>

      <form onSubmit={enviar} className="glass space-y-4 rounded-3xl p-5 sm:p-6" noValidate>
        <Campo
          etiqueta="Tu nombre"
          valor={nombre}
          onCambio={setNombre}
          autoComplete="name"
          max={120}
        />
        <Campo
          etiqueta="Empresa"
          valor={empresa}
          onCambio={setEmpresa}
          autoComplete="organization"
          max={160}
        />
        <Campo
          etiqueta="Correo de trabajo"
          tipo="email"
          valor={correo}
          onCambio={setCorreo}
          autoComplete="email"
          max={254}
          error={correo.trim() !== "" && !correoOk ? "Revisa el correo." : undefined}
        />
        {SITE_KEY && <Turnstile siteKey={SITE_KEY} onToken={onToken} />}
        <label className="flex items-start gap-3 text-sm text-ink-200">
          <input
            type="checkbox"
            className="mt-0.5 h-5 w-5 shrink-0 accent-aqua-500"
            checked={sinFinesComerciales}
            onChange={(e) => setSinFinesComerciales(e.target.checked)}
          />
          No quiero que me contacten con fines comerciales.
        </label>
        <p
          className={`text-xs leading-relaxed ${AVISO_COMPLETO ? "text-ink-400" : "rounded-lg bg-flame-500/20 p-2 text-flame-300"}`}
        >
          <strong>Aviso de privacidad simplificado.</strong> {RESPONSABLE}, con domicilio en{" "}
          {DOMICILIO}, es responsable de tus datos: nombre, empresa y correo; tus respuestas; la IP
          y datos del navegador, y el canal o campaña por el que llegaste. No recabamos datos
          sensibles ni financieros. Los usamos para generar y mostrarte el diagnóstico y comprobar
          que eres una persona (protección contra spam). Además, para contactarte sobre el
          diagnóstico y ofrecerte servicios, enviarte información y contenidos, y medir por qué
          canal llegaste. Si no quieres estos usos adicionales, marca la casilla o escribe a{" "}
          {CONTACTO_PRIVACIDAD} con el asunto “{ASUNTO_NEGATIVA}”. Consulta el aviso de privacidad
          integral en{" "}
          <a
            href={URL_AVISO_INTEGRAL}
            target="_blank"
            rel="noreferrer noopener"
            className="underline"
          >
            vectorhrtech.com/aviso-de-privacidad
          </a>
          .
        </p>
        {error && (
          <p role="alert" className="text-sm text-flame-300">
            {error}
          </p>
        )}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <button
            type="button"
            className="text-ink-300 underline hover:text-white"
            onClick={onAtras}
          >
            ← Atrás
          </button>
          <button type="submit" className={btnCta} disabled={!completo || enviando}>
            {enviando ? "Guardando…" : "Ver mi diagnóstico completo →"}
          </button>
        </div>
      </form>
    </section>
  );
}

function Campo({
  etiqueta,
  valor,
  onCambio,
  tipo = "text",
  autoComplete,
  max,
  error,
}: {
  etiqueta: string;
  valor: string;
  onCambio: (v: string) => void;
  tipo?: string;
  autoComplete: string;
  max: number;
  error?: string | undefined;
}) {
  return (
    <label className="block space-y-1">
      <span className="text-sm font-semibold text-ink-200">{etiqueta}</span>
      <input
        type={tipo}
        value={valor}
        maxLength={max}
        required
        autoComplete={autoComplete}
        aria-invalid={error ? true : undefined}
        onChange={(e) => onCambio(e.target.value)}
        className="block min-h-12 w-full rounded-xl border border-white/15 bg-ink-950/60 px-4 text-white placeholder:text-ink-400 focus:border-aqua-300 focus:outline-none"
      />
      {error && <span className="text-sm text-flame-300">{error}</span>}
    </label>
  );
}

const COLOR_ETAPA: Record<Etapa, string> = {
  Digitalizar: "bg-ink-500/30 text-ink-200",
  Optimizar: "bg-gold/20 text-gold",
  Automatizar: "bg-aqua-300/15 text-aqua-300",
};

const TEXTO_CANAL: Record<string, string> = {
  whatsapp: "Nuestros agentes conversan por WhatsApp, donde ya te piden las cosas.",
  correo: "Nuestros agentes pueden atender las solicitudes que hoy te llegan por correo.",
  chat: "Nuestros agentes conversan en Teams, Slack o Google Chat, donde ya está tu equipo.",
  presencial:
    "Un buen primer paso es que las solicitudes dejen rastro: un canal único donde un agente las atiende.",
};

function ResultadoCompleto({
  resultado,
  respuestas,
}: { resultado: Resultado; respuestas: Respuestas }) {
  const top = resultado.procesos.slice(0, TOP);
  const resto = resultado.procesos.slice(TOP);
  const canal = typeof respuestas.canal === "string" ? TEXTO_CANAL[respuestas.canal] : undefined;
  const asunto = encodeURIComponent("Quiero revisar mi diagnóstico de procesos");

  return (
    <section className="space-y-8">
      <div className="space-y-3">
        <p className="text-sm font-semibold uppercase tracking-widest text-aqua-300">
          Tu diagnóstico
        </p>
        <h2 className="text-3xl sm:text-4xl">
          Podrías recuperar unas{" "}
          <span className="text-brand-gradient">
            {formatoHoras(resultado.horasRecuperablesMes)} al mes
          </span>
        </h2>
        <p className="text-ink-200">
          Atacando los 3 procesos de abajo. Son unas{" "}
          {resultado.horasRecuperablesAnio.toLocaleString("es-MX")} horas al año de tu equipo que
          hoy se van en rutina.
        </p>
      </div>

      <ol className="space-y-4">
        {top.map((p, i) => (
          <li key={p.id} className="glass space-y-3 rounded-3xl p-5">
            <div className="flex flex-wrap items-center gap-3">
              <span className="text-brand-gradient text-2xl font-extrabold">{i + 1}</span>
              <h3 className="text-xl">{p.nombre}</h3>
              <span className={`rounded-full px-3 py-1 text-xs font-bold ${COLOR_ETAPA[p.etapa]}`}>
                {p.etapa}
              </span>
            </div>
            <p className="text-ink-200">{QUE_SIGNIFICA[p.etapa]}</p>
            <dl className="grid grid-cols-2 gap-3 text-sm">
              <div>
                <dt className="text-ink-400">Hoy le dedican</dt>
                <dd className="font-bold text-white">{formatoHoras(p.horasSemana)} a la semana</dd>
              </div>
              <div>
                <dt className="text-ink-400">Recuperables</dt>
                <dd className="font-bold text-white">
                  {formatoHoras(p.horasRecuperablesMes)} al mes
                </dd>
              </div>
            </dl>
          </li>
        ))}
      </ol>

      {resto.length > 0 && (
        <details className="glass rounded-3xl p-5">
          <summary className="cursor-pointer font-semibold text-white">
            Los otros procesos que revisamos
          </summary>
          <ul className="mt-3 space-y-2 text-sm">
            {resto.map((p) => (
              <li key={p.id} className="flex flex-wrap justify-between gap-2">
                <span>{p.nombre}</span>
                <span className="text-ink-300">
                  {p.etapa} · {formatoHoras(p.horasRecuperablesMes)} al mes
                </span>
              </li>
            ))}
          </ul>
        </details>
      )}

      <section className="glass space-y-3 rounded-3xl p-5 text-sm">
        <h3 className="text-lg">Cómo lo calculamos</h3>
        <p>
          Para cada proceso: <strong className="text-white">horas por semana</strong> (el punto
          medio del rango que elegiste) ×{" "}
          <strong className="text-white">porcentaje recuperable</strong> de su etapa ×{" "}
          {SEMANAS_POR_MES.toLocaleString("es-MX", { maximumFractionDigits: 2 })} semanas por mes,
          redondeado a media hora. El total suma solo los 3 primeros.
        </p>
        <ul className="space-y-1">
          {(Object.keys(PORCENTAJE_RECUPERABLE) as Etapa[]).map((etapa) => (
            <li key={etapa}>
              <strong className="text-white">{etapa}:</strong>{" "}
              {Math.round(PORCENTAJE_RECUPERABLE[etapa] * 100)} %
            </li>
          ))}
        </ul>
        <p className="text-ink-300">
          La etapa sale de tus respuestas: si el proceso no está en un sistema, toca digitalizarlo;
          si está pero sin pasos definidos, optimizarlo; si tiene ambos, automatizarlo. Los
          porcentajes son supuestos conservadores nuestros para dimensionar, no resultados medidos
          en clientes. En una llamada los afinamos con tus números reales.
        </p>
      </section>

      <section className="space-y-4">
        <h3 className="text-2xl">¿Lo revisamos juntos?</h3>
        <p>
          En 30 minutos te decimos por dónde empezar y qué se puede automatizar con agentes de IA
          que operan con tu equipo, bajo tus reglas y aprobaciones.{canal ? ` ${canal}` : ""}
        </p>
        <div className="flex flex-wrap gap-3">
          <a href={`mailto:${CORREO}?subject=${asunto}`} className={btnCta}>
            Agenda una llamada →
          </a>
          <a href={SITIO} className={btnGhost}>
            Conoce Vector HR Tech
          </a>
        </div>
      </section>
    </section>
  );
}
