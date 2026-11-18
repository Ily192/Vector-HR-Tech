/**
 * El área de admin de Vector HR (`/admin`; ADR-022, enmienda del 2026-11-17): las
 * métricas de la plataforma y la cola de revisión, pensada para el teléfono (se instala
 * con `public/admin.webmanifest`).
 *
 * Quién entra lo decide el hr-engine (`/admin/yo` y `ADMIN_CORREOS`); la pantalla solo
 * pinta lo que le dice. Aprobar o rechazar es lo mismo que el enlace firmado del resumen
 * a hola@ y la CLI: `ResolverRevision` en el hr-engine.
 */
import { ETIQUETA_MODERACION } from "@fluveai/types/etiquetas";
import type { Moderacion, MotivoDeModeracion } from "@fluveai/types/hr";
import { Badge, Button } from "@fluveai/ui";
import { type FormEvent, type ReactNode, useState } from "react";

import type {
  MetricasWeb,
  ResultadoDeRevision,
  ResumenAdmin,
  VacanteEnRevision,
} from "../datos/admin";
import {
  useAccesoAdmin,
  useColaAdmin,
  useMetricasWeb,
  useResolverVacante,
  useResumenAdmin,
  useSalir,
  useSesion,
} from "../datos/consultas";
import { ES_DE_EJEMPLO } from "../datos/panel";
import { Logo } from "../marco/marco";
import { Enlace } from "../navegacion/ruta";

const formatoNumero = new Intl.NumberFormat("es-MX");
const formatoFecha = new Intl.DateTimeFormat("es-MX", {
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

/** Lo que `ResolverRevision` guarda como mucho (hr-engine, MAX_MOTIVO). */
const MAX_MOTIVO = 300;

const CAMPO =
  "mt-1.5 block w-full rounded-xl border-[1.5px] border-mist-200 bg-white px-3.5 py-2.5 text-[15px] font-normal text-ink-900 placeholder:text-mist-500 focus:border-aqua-500 focus:outline-none focus:ring-2 focus:ring-aqua-500/30";

function Salir() {
  const salir = useSalir();
  return (
    <button
      type="button"
      onClick={() => salir.mutate()}
      disabled={salir.isPending}
      className="rounded-lg px-2 py-1 text-[13px] font-bold text-mist-600 hover:text-ink-900"
    >
      Salir
    </button>
  );
}

/** El marco del admin: una barra arriba y una sola columna, cómoda en el teléfono. */
function MarcoAdmin({ children }: { children: ReactNode }) {
  const { data: sesion } = useSesion();
  return (
    <div className="min-h-screen bg-mist-50 text-ink-900">
      <header className="sticky top-0 z-30 border-b border-mist-200 bg-white">
        <div className="mx-auto flex h-14 max-w-3xl items-center gap-3 px-4">
          <Logo />
          <span className="font-mono text-[11px] font-semibold uppercase tracking-[0.08em] text-aqua-700">
            Vector HR · Admin
          </span>
          <div className="ml-auto flex items-center gap-1">
            {sesion && (
              <Enlace
                href="/"
                className="rounded-lg px-2 py-1 text-[13px] font-bold text-mist-600 hover:text-ink-900"
              >
                Panel
              </Enlace>
            )}
            {!ES_DE_EJEMPLO && <Salir />}
          </div>
        </div>
      </header>
      <main className="mx-auto flex max-w-3xl flex-col gap-6 px-4 pb-16 pt-6">{children}</main>
    </div>
  );
}

function Aviso({ titulo, children }: { titulo: string; children: ReactNode }) {
  return (
    <section className="rounded-[22px] border border-mist-200 bg-white p-6">
      <h1 className="text-2xl font-extrabold tracking-[-0.02em]">{titulo}</h1>
      <div className="mt-2 flex flex-col gap-4 text-[15px] text-mist-700">{children}</div>
    </section>
  );
}

/**
 * La pantalla. Primero pregunta al hr-engine si la sesión es de admin; sin eso no pide
 * ni métricas ni cola.
 */
export function Admin() {
  const acceso = useAccesoAdmin();

  let contenido: ReactNode;
  if (ES_DE_EJEMPLO) {
    contenido = (
      <Aviso titulo="El admin necesita el panel conectado">
        <p>Con datos de ejemplo no hay sesión que mandarle al hr-engine.</p>
      </Aviso>
    );
  } else if (acceso.isPending) {
    contenido = <p className="text-mist-600">Revisando tu acceso…</p>;
  } else if (acceso.isError) {
    contenido = (
      <Aviso titulo="No pudimos revisar tu acceso">
        <p>Revisa tu conexión y vuelve a intentarlo.</p>
        <div>
          <Button variant="secondary" onClick={() => void acceso.refetch()}>
            Reintentar
          </Button>
        </div>
      </Aviso>
    );
  } else if (acceso.data.estado === "sin-acceso") {
    contenido = (
      <Aviso titulo="No tienes acceso">
        <p>El área de admin es para el equipo de Vector HR Tech.</p>
      </Aviso>
    );
  } else if (acceso.data.estado === "sin-sesion") {
    contenido = (
      <Aviso titulo="Tu sesión venció">
        <p>Sal y vuelve a entrar con un código nuevo.</p>
      </Aviso>
    );
  } else {
    contenido = <Tablero />;
  }

  return <MarcoAdmin>{contenido}</MarcoAdmin>;
}

function Tablero() {
  const resumen = useResumenAdmin();
  const web = useMetricasWeb();
  const cola = useColaAdmin();
  const [aviso, setAviso] = useState<string | null>(null);

  return (
    <>
      <div>
        <span className="font-mono text-[11px] font-semibold uppercase tracking-[0.08em] text-aqua-700">
          Admin
        </span>
        <h1 className="mt-1 text-[2rem] font-extrabold leading-none tracking-[-0.04em]">
          La plataforma hoy
        </h1>
      </div>

      <section aria-labelledby="metricas-panel" className="flex flex-col gap-3">
        <h2 id="metricas-panel" className="text-lg font-extrabold">
          Panel
        </h2>
        {resumen.isPending ? (
          <p className="text-sm text-mist-600">Cargando las métricas…</p>
        ) : resumen.isError ? (
          <p role="alert" className="text-sm font-bold text-danger-700">
            No pudimos leer las métricas del panel.
          </p>
        ) : (
          <MetricasDelPanel resumen={resumen.data} />
        )}
      </section>

      <section aria-labelledby="metricas-web" className="flex flex-col gap-3">
        <h2 id="metricas-web" className="text-lg font-extrabold">
          Web
        </h2>
        {web.isPending ? (
          <p className="text-sm text-mist-600">Cargando las métricas de la web…</p>
        ) : web.isError ? (
          <p className="rounded-2xl bg-mist-100 p-4 text-sm text-mist-700">
            No pudimos leer las métricas de la web. Las del panel siguen al día.
          </p>
        ) : (
          <MetricasDeLaWeb web={web.data} />
        )}
      </section>

      <section aria-labelledby="cola" className="flex flex-col gap-3">
        <h2 id="cola" className="text-lg font-extrabold">
          Cola de revisión{cola.data ? ` (${cola.data.length})` : ""}
        </h2>
        {aviso && (
          <output className="block rounded-2xl bg-aqua-50 p-4 text-sm text-aqua-700">
            {aviso}
          </output>
        )}
        {cola.isPending ? (
          <p className="text-sm text-mist-600">Cargando la cola…</p>
        ) : cola.isError ? (
          <div role="alert" className="flex flex-col items-start gap-3 text-sm">
            <p className="font-bold text-danger-700">No pudimos leer la cola de revisión.</p>
            <Button variant="secondary" size="sm" onClick={() => void cola.refetch()}>
              Reintentar
            </Button>
          </div>
        ) : cola.data.length === 0 ? (
          <p className="rounded-2xl bg-white p-4 text-sm text-mist-700">
            No hay vacantes esperando revisión.
          </p>
        ) : (
          <ul className="flex flex-col gap-4">
            {cola.data.map((v) => (
              <li key={v.id}>
                <TarjetaDeRevision vacante={v} alResolver={setAviso} />
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}

function Cifra({
  etiqueta,
  valor,
  detalle,
  tono,
}: {
  etiqueta: string;
  valor: number;
  detalle?: string;
  tono?: "aqua" | "flame" | undefined;
}) {
  const fondo =
    tono === "aqua"
      ? "border-aqua-100 bg-aqua-50"
      : tono === "flame"
        ? "border-flame-100 bg-flame-50"
        : "border-mist-200 bg-white";
  return (
    <div className={`flex flex-col gap-0.5 rounded-[18px] border p-4 ${fondo}`}>
      <span className="text-[13px] font-bold text-mist-600">{etiqueta}</span>
      <span className="text-[1.9rem] font-extrabold leading-none tracking-[-0.04em] tabular-nums">
        {formatoNumero.format(valor)}
      </span>
      {detalle && <span className="text-xs font-bold text-mist-600">{detalle}</span>}
    </div>
  );
}

const ESTADOS_DE_LA_TABLA: Moderacion[] = [
  "pendiente",
  "en_revision",
  "oculta",
  "publicada",
  "rechazada",
];

function MetricasDelPanel({ resumen }: { resumen: ResumenAdmin }) {
  const { empresas, vacantes, aplicaciones, altas } = resumen;
  const enRevision = vacantes.porModeracion.en_revision + vacantes.porModeracion.oculta;
  return (
    <>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Cifra
          etiqueta="Empresas"
          valor={empresas.total}
          detalle={`${formatoNumero.format(empresas.verificadas)} verificadas`}
        />
        <Cifra
          etiqueta="Altas web confirmadas"
          valor={empresas.altasWebConfirmadas}
          detalle={`${formatoNumero.format(altas.ultimos7)} altas en 7 días`}
          tono="aqua"
        />
        <Cifra
          etiqueta="Vacantes abiertas"
          valor={vacantes.abiertas}
          detalle={`${formatoNumero.format(vacantes.cerradas)} cerradas`}
        />
        <Cifra
          etiqueta="Por revisar"
          valor={enRevision}
          detalle={`${formatoNumero.format(vacantes.porModeracion.oculta)} ocultas por reportes`}
          tono={enRevision > 0 ? "flame" : undefined}
        />
        <Cifra
          etiqueta="Aplicaciones"
          valor={aplicaciones.total}
          detalle={`${formatoNumero.format(aplicaciones.ultimos7)} en 7 días`}
        />
      </div>
      <table className="w-full overflow-hidden rounded-[18px] bg-white text-sm">
        <caption className="sr-only">Vacantes abiertas por estado de la moderación</caption>
        <tbody>
          {ESTADOS_DE_LA_TABLA.map((estado) => (
            <tr key={estado} className="border-b border-mist-100 last:border-0">
              <th scope="row" className="px-4 py-2 text-left font-bold text-mist-700">
                {ETIQUETA_MODERACION[estado]}
              </th>
              <td className="px-4 py-2 text-right font-mono tabular-nums">
                {formatoNumero.format(vacantes.porModeracion[estado])}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

const sinValor = (valor: string | null) => valor || "—";

function MetricasDeLaWeb({ web }: { web: MetricasWeb }) {
  const { registros, diagnosticos, listaEspera } = web;
  return (
    <>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Cifra
          etiqueta="Registros"
          valor={registros.total}
          detalle={`${formatoNumero.format(registros.ultimos7)} en 7 días`}
          tono="aqua"
        />
        <Cifra
          etiqueta="Alta fallida"
          valor={registros.altaFallida}
          detalle="se registraron sin cuenta"
          tono={registros.altaFallida > 0 ? "flame" : undefined}
        />
        <Cifra
          etiqueta="Diagnósticos"
          valor={diagnosticos.total}
          detalle={`${formatoNumero.format(diagnosticos.ultimos7)} en 7 días`}
        />
        <Cifra
          etiqueta="Lista de espera"
          valor={listaEspera.total}
          detalle={`${formatoNumero.format(listaEspera.ultimos7)} en 7 días`}
        />
      </div>
      {registros.porCampana.length > 0 && (
        <div className="overflow-x-auto rounded-[18px] bg-white">
          <table className="w-full text-sm">
            <caption className="px-4 pt-3 text-left text-[13px] font-bold text-mist-600">
              Registros por campaña
            </caption>
            <thead>
              <tr className="text-left text-xs text-mist-600">
                <th scope="col" className="px-4 py-2">
                  Origen
                </th>
                <th scope="col" className="px-4 py-2">
                  Medio
                </th>
                <th scope="col" className="px-4 py-2">
                  Campaña
                </th>
                <th scope="col" className="px-4 py-2 text-right">
                  Total
                </th>
              </tr>
            </thead>
            <tbody>
              {registros.porCampana.map((c) => (
                <tr
                  key={`${c.origen}|${c.medio}|${c.campana}`}
                  className="border-t border-mist-100"
                >
                  <td className="px-4 py-2">{sinValor(c.origen)}</td>
                  <td className="px-4 py-2">{sinValor(c.medio)}</td>
                  <td className="px-4 py-2">{sinValor(c.campana)}</td>
                  <td className="px-4 py-2 text-right font-mono tabular-nums">
                    {formatoNumero.format(c.n)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

const GRAVEDAD = {
  alta: { texto: "Grave", variante: "danger" },
  media: { texto: "Sospechosa", variante: "warning" },
  baja: { texto: "Contexto", variante: "manual" },
} as const;

function Motivos({ motivos }: { motivos: readonly MotivoDeModeracion[] }) {
  if (motivos.length === 0) return null;
  return (
    <ul className="flex flex-col gap-2 text-sm">
      {motivos.map((m) => (
        <li key={`${m.regla}-${m.senal}`} className="rounded-2xl bg-mist-50 p-3">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={GRAVEDAD[m.gravedad].variante}>{GRAVEDAD[m.gravedad].texto}</Badge>
            <span className="font-mono text-[11px] text-mist-600">{m.regla}</span>
          </div>
          <p className="mt-1.5 text-ink-900">
            {m.senal}
            {m.cita && <> «{m.cita}»</>}
          </p>
          {m.corregir && (
            <p className="mt-1 text-mist-700">
              <b>Qué corregir:</b> {m.corregir}
            </p>
          )}
        </li>
      ))}
    </ul>
  );
}

const ERROR_DE_REVISION = {
  "sin-sesion": "Tu sesión venció. Sal y vuelve a entrar.",
  "sin-acceso": "Tu cuenta ya no tiene acceso de admin.",
  "falta-motivo": "Escribe el motivo: la empresa lo ve en su panel.",
  error: "No se pudo guardar. Inténtalo de nuevo.",
} as const;

function TarjetaDeRevision({
  vacante,
  alResolver,
}: {
  vacante: VacanteEnRevision;
  alResolver: (aviso: string) => void;
}) {
  const resolver = useResolverVacante();
  const [rechazando, setRechazando] = useState(false);
  const [motivo, setMotivo] = useState("");
  const [fallo, setFallo] = useState<string | null>(null);
  const idDelMotivo = `motivo-${vacante.id}`;

  // `mutateAsync` y no los callbacks de `mutate`: si salió bien, la tarjeta deja la lista
  // (y se desmonta) antes de que termine, y el aviso va al tablero, que sigue montado.
  async function decidir(pedido: { accion: "aprobar" } | { accion: "rechazar"; motivo: string }) {
    setFallo(null);
    let r: ResultadoDeRevision;
    try {
      r = await resolver.mutateAsync({ vacanteId: vacante.id, ...pedido });
    } catch {
      setFallo(ERROR_DE_REVISION.error);
      return;
    }
    if (r.ok) {
      alResolver(
        pedido.accion === "aprobar"
          ? `Aprobaste «${vacante.titulo}»: ya está en la bolsa de empleo.`
          : `Rechazaste «${vacante.titulo}»: la empresa ve el motivo en su panel.`,
      );
    } else if (r.motivo === "ya-resuelta") {
      alResolver(
        r.estado
          ? `«${vacante.titulo}» ya no estaba en la cola: está en «${ETIQUETA_MODERACION[r.estado]}».`
          : `«${vacante.titulo}» ya no existe.`,
      );
    } else {
      setFallo(ERROR_DE_REVISION[r.motivo]);
    }
  }

  function alRechazar(evento: FormEvent) {
    evento.preventDefault();
    if (motivo.trim()) void decidir({ accion: "rechazar", motivo: motivo.trim() });
  }

  return (
    <article
      aria-labelledby={`titulo-${vacante.id}`}
      className="flex flex-col gap-3 rounded-[22px] border border-mist-200 bg-white p-5"
    >
      <div className="flex flex-col gap-1">
        <h3 id={`titulo-${vacante.id}`} className="text-lg font-extrabold leading-snug">
          {vacante.titulo}
        </h3>
        <p className="text-sm text-mist-700">
          {vacante.empresa}
          {vacante.creadaEn && <> · {formatoFecha.format(new Date(vacante.creadaEn))}</>}
        </p>
      </div>
      <div className="flex flex-wrap gap-2">
        <Badge variant={vacante.estado === "oculta" ? "danger" : "warning"}>
          {ETIQUETA_MODERACION[vacante.estado]}
        </Badge>
        {vacante.publicaParaClientes ? (
          <Badge variant="ai">Reclutador(a) independiente</Badge>
        ) : vacante.verificada ? (
          <Badge variant="success">Empresa verificada</Badge>
        ) : (
          <Badge variant="manual">Sin verificar</Badge>
        )}
      </div>
      {(vacante.web || vacante.linkedin) && (
        <p className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
          {vacante.web && (
            <a
              href={vacante.web}
              target="_blank"
              rel="noopener noreferrer nofollow"
              className="font-bold text-aqua-700 hover:underline"
            >
              Web
            </a>
          )}
          {vacante.linkedin && (
            <a
              href={vacante.linkedin}
              target="_blank"
              rel="noopener noreferrer nofollow"
              className="font-bold text-aqua-700 hover:underline"
            >
              LinkedIn
            </a>
          )}
        </p>
      )}
      <Motivos motivos={vacante.motivos} />
      <details className="rounded-2xl bg-mist-50 p-3 text-sm">
        <summary className="cursor-pointer font-bold">Ver la descripción</summary>
        <p className="mt-2 whitespace-pre-wrap break-words text-ink-900">{vacante.descripcion}</p>
      </details>

      {fallo && (
        <p role="alert" className="text-sm font-bold text-danger-700">
          {fallo}
        </p>
      )}

      {rechazando ? (
        <form
          onSubmit={alRechazar}
          aria-label={`Rechazar ${vacante.titulo}`}
          className="flex flex-col gap-3"
        >
          <label htmlFor={idDelMotivo} className="text-sm font-bold">
            Motivo del rechazo (la empresa lo ve en su panel)
          </label>
          <textarea
            id={idDelMotivo}
            required
            rows={3}
            maxLength={MAX_MOTIVO}
            value={motivo}
            onChange={(e) => setMotivo(e.target.value)}
            className={CAMPO}
          />
          <div className="flex flex-wrap gap-2">
            <Button
              type="submit"
              variant="destructive"
              disabled={resolver.isPending || !motivo.trim()}
            >
              Rechazar vacante
            </Button>
            <Button
              variant="ghost"
              disabled={resolver.isPending}
              onClick={() => {
                setRechazando(false);
                setFallo(null);
              }}
            >
              Cancelar
            </Button>
          </div>
        </form>
      ) : (
        <div className="flex flex-wrap gap-2">
          <Button
            variant="ink"
            disabled={resolver.isPending}
            onClick={() => void decidir({ accion: "aprobar" })}
          >
            Aprobar
          </Button>
          <Button
            variant="secondary"
            disabled={resolver.isPending}
            onClick={() => {
              setRechazando(true);
              setFallo(null);
            }}
          >
            Rechazar
          </Button>
        </div>
      )}
    </article>
  );
}
