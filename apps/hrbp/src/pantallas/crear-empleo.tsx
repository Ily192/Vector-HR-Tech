import { ETIQUETA_MODALIDAD, ETIQUETA_SENIORITY } from "@vortex/types/etiquetas";
import type { Modality, Seniority } from "@vortex/types/hr";
import { MAX_LARGO_DE_SKILL, MAX_SKILLS_POR_VACANTE } from "@vortex/types/reglas";
import { Button, buttonVariants, formatearSalario, iniciales } from "@vortex/ui";
import { FileCheck2, ScanSearch, SquareCheckBig, X } from "lucide-react";
import { type FormEvent, type KeyboardEvent, type ReactNode, useState } from "react";

import {
  useMisVacantes,
  usePublicarVacante,
  useRegistrarInteres,
  useSesion,
} from "../datos/consultas";
import type { BorradorDeVacante, MotivoDeRechazo } from "../datos/tipos";
import { Encabezado } from "../marco/marco";
import { Enlace, navegar } from "../navegacion/ruta";

const MODALIDADES = Object.keys(ETIQUETA_MODALIDAD) as Modality[];
const NIVELES = Object.keys(ETIQUETA_SENIORITY) as Seniority[];

const BORRADOR_VACIO: BorradorDeVacante = {
  titulo: "",
  seniority: "semi-senior",
  modalidad: "hybrid",
  ubicacion: "",
  descripcion: "",
  salarioMin: null,
  salarioMax: null,
  moneda: "MXN",
  salarioPublico: true,
  skills: [],
};

const MENSAJE_DE_RECHAZO: Record<MotivoDeRechazo, string> = {
  "sin-cupo": "Ya tienes todas las vacantes de tu plan activas. Elimina una para publicar esta.",
  "sin-publicaciones":
    "Ya publicaste las vacantes nuevas que tu plan permite en 30 días. Eliminar una no te devuelve la publicación.",
  "datos-invalidos": "Revisa el puesto y la descripción: los dos son obligatorios.",
};

const CLASE_CAMPO =
  "mt-1.5 block w-full rounded-xl border-[1.5px] border-mist-200 bg-white px-3.5 py-2.5 text-[15px] font-normal text-ink-900 placeholder:text-mist-500 focus:border-aqua-500 focus:outline-none focus:ring-2 focus:ring-aqua-500/30";

function Campo({
  etiqueta,
  ayuda,
  children,
}: { etiqueta: string; ayuda?: string; children: ReactNode }) {
  return (
    // biome-ignore lint/a11y/noLabelWithoutControl: el control llega en `children`, dentro del label.
    <label className="block text-sm font-bold">
      {etiqueta}
      {ayuda && <span className="ml-1.5 font-normal text-mist-600">{ayuda}</span>}
      {children}
    </label>
  );
}

const aNumero = (texto: string) => (texto === "" ? null : Number(texto));

const formatoDia = new Intl.DateTimeFormat("es-MX", { day: "numeric", month: "long" });

/**
 * Las skills que pide la vacante, como etiquetas: Enter o coma agrega, la × quita.
 * Al salir del campo se agrega lo escrito, para no perderlo al publicar.
 */
function CampoDeSkills({
  skills,
  alCambiar,
}: { skills: string[]; alCambiar: (skills: string[]) => void }) {
  const [texto, setTexto] = useState("");
  const llenas = skills.length >= MAX_SKILLS_POR_VACANTE;

  function agregar() {
    const nuevas = [...skills];
    for (const parte of texto.split(",")) {
      const skill = parte.trim().slice(0, MAX_LARGO_DE_SKILL).trim();
      const repetida = nuevas.some((s) => s.toLowerCase() === skill.toLowerCase());
      if (skill && !repetida && nuevas.length < MAX_SKILLS_POR_VACANTE) nuevas.push(skill);
    }
    if (nuevas.length !== skills.length) alCambiar(nuevas);
    setTexto("");
  }

  function alTeclear(evento: KeyboardEvent<HTMLInputElement>) {
    if (evento.key === "Enter" || evento.key === ",") {
      evento.preventDefault();
      agregar();
    } else if (evento.key === "Backspace" && texto === "" && skills.length > 0) {
      alCambiar(skills.slice(0, -1));
    }
  }

  return (
    <fieldset>
      <legend className="text-sm font-bold">
        Skills que pide la vacante
        <span className="ml-1.5 font-normal text-mist-600">
          Hasta {MAX_SKILLS_POR_VACANTE}. Te decimos cuántos CVs las mencionan.
        </span>
      </legend>
      <div className="mt-1.5 flex flex-wrap items-center gap-2 rounded-xl border-[1.5px] border-mist-200 bg-white px-3 py-2 focus-within:border-aqua-500 focus-within:ring-2 focus-within:ring-aqua-500/30">
        {skills.map((s) => (
          <span
            key={s}
            className="inline-flex items-center gap-1 rounded-full bg-aqua-50 py-1 pl-3 pr-1.5 text-sm font-bold text-aqua-700"
          >
            {s}
            <button
              type="button"
              aria-label={`Quitar ${s}`}
              onClick={() => alCambiar(skills.filter((x) => x !== s))}
              className="grid h-5 w-5 place-items-center rounded-full hover:bg-aqua-100"
            >
              <X aria-hidden="true" className="h-3.5 w-3.5" />
            </button>
          </span>
        ))}
        <input
          aria-label="Agregar skill"
          value={texto}
          disabled={llenas}
          onChange={(e) => setTexto(e.target.value)}
          onKeyDown={alTeclear}
          onBlur={agregar}
          placeholder={
            llenas
              ? `Llegaste a ${MAX_SKILLS_POR_VACANTE} skills`
              : skills.length === 0
                ? "Excel, montacargas, inglés…"
                : "Agrega otra"
          }
          className="min-w-[10rem] flex-1 border-0 bg-transparent py-1 text-[15px] text-ink-900 placeholder:text-mist-500 focus:outline-none"
        />
      </div>
      <p className="mt-1.5 text-[13px] text-mist-600">
        Escríbelas como aparecerían en un CV. Contamos menciones, no juzgamos experiencia.
      </p>
    </fieldset>
  );
}

/** Así verán la vacante los candidatos: misma tarjeta que el career site. */
function VistaPrevia({ borrador, empresa }: { borrador: BorradorDeVacante; empresa: string }) {
  const salario = borrador.salarioPublico
    ? formatearSalario({
        salario_min: borrador.salarioMin,
        salario_max: borrador.salarioMax,
        moneda: borrador.moneda,
      })
    : null;
  return (
    <article
      aria-label="Vista previa de la vacante"
      className="flex flex-col gap-3 rounded-[22px] border border-mist-200 bg-white p-5 shadow-sm"
    >
      <div className="flex items-center gap-3">
        <span
          aria-hidden="true"
          className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-ink-900 font-mono text-sm font-semibold text-aqua-300"
        >
          {iniciales(empresa)}
        </span>
        <div className="min-w-0">
          <p className="truncate text-lg font-extrabold">
            {borrador.titulo || "Puesto de la vacante"}
          </p>
          <p className="text-sm font-semibold text-mist-700">{empresa}</p>
        </div>
        <span className="ml-auto rounded-full bg-aqua-50 px-2.5 py-0.5 text-xs font-bold text-aqua-700">
          Nueva
        </span>
      </div>
      <p className="flex flex-wrap gap-x-3 gap-y-1 text-sm font-semibold text-mist-700">
        <span>{borrador.ubicacion || "Ubicación"}</span>
        <span>{ETIQUETA_MODALIDAD[borrador.modalidad]}</span>
        <span>{ETIQUETA_SENIORITY[borrador.seniority]}</span>
      </p>
      <p className="text-base font-extrabold">
        {salario ? (
          <>
            {salario}{" "}
            <span className="text-sm font-semibold text-mist-600">{borrador.moneda} / mes</span>
          </>
        ) : (
          <span className="text-mist-600">Salario a convenir</span>
        )}
      </p>
      {borrador.descripcion && (
        <p className="line-clamp-3 text-[14.5px] leading-normal text-mist-700">
          {borrador.descripcion}
        </p>
      )}
    </article>
  );
}

const CLAVE_BROCHURE_OCULTO = "vortex:brochure-oculto";

function leerOculto() {
  try {
    return localStorage.getItem(CLAVE_BROCHURE_OCULTO) === "1";
  } catch {
    return false;
  }
}

const SERVICIOS = [
  {
    icono: SquareCheckBig,
    titulo: "Evaluación a ciegas",
    texto: "Cada CV llega con score y su porqué. El nombre no se usa.",
  },
  {
    icono: ScanSearch,
    titulo: "Búsqueda de perfiles",
    texto: "Si llegan pocos, un agente busca candidatos fuera del sitio.",
  },
  {
    icono: FileCheck2,
    titulo: "Expediente de cada decisión",
    texto: "Quién decidió qué y cuándo, listo para auditoría.",
  },
];

/** La única venta del plan gratis: un brochure breve, que se puede ocultar (ADR-017). */
function Brochure() {
  const [oculto, setOculto] = useState(leerOculto);
  const interes = useRegistrarInteres();
  if (oculto) return null;

  function ocultar() {
    setOculto(true);
    try {
      localStorage.setItem(CLAVE_BROCHURE_OCULTO, "1");
    } catch {
      // Sin almacenamiento, se vuelve a mostrar en la próxima visita.
    }
  }

  return (
    <section
      aria-label="Servicios de Vector HR"
      className="flex flex-col gap-3.5 rounded-[22px] bg-ink-900 p-5 text-white"
    >
      <div className="flex items-center">
        <span className="font-mono text-[11px] font-semibold uppercase tracking-[0.08em] text-aqua-300">
          Cuando lleguen las aplicaciones
        </span>
        <button
          type="button"
          onClick={ocultar}
          className="ml-auto rounded-lg px-2 py-1 text-xs font-bold text-mist-300 hover:text-white"
        >
          Ocultar
        </button>
      </div>
      <h2 className="text-[21px] leading-tight tracking-[-0.02em]">
        Vector HR puede leer los CVs por ti
      </h2>
      <ul className="flex flex-col gap-3">
        {SERVICIOS.map((s) => (
          <li key={s.titulo} className="flex gap-3">
            <span
              aria-hidden="true"
              className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-ink-800 text-aqua-300"
            >
              <s.icono className="h-[18px] w-[18px]" />
            </span>
            <div className="text-sm">
              <b className="block">{s.titulo}</b>
              <span className="text-ink-200">{s.texto}</span>
            </div>
          </li>
        ))}
      </ul>
      {interes.isSuccess ? (
        <output className="block text-sm font-bold text-aqua-300">
          Listo. Tu contacto en Vector HR te escribe pronto.
        </output>
      ) : (
        <Button
          size="sm"
          className="self-start bg-aqua-300 shadow-none hover:bg-aqua-200"
          disabled={interes.isPending}
          onClick={() => interes.mutate("crear-empleo")}
        >
          Quiero saber más
        </Button>
      )}
      {interes.isError && (
        <p role="alert" className="text-sm font-bold text-flame-300">
          No pudimos avisar a Vector HR. Inténtalo de nuevo.
        </p>
      )}
      <span className="text-xs text-ink-300">
        Te escribe tu contacto en Vector HR. Tu plan gratis no cambia.
      </span>
    </section>
  );
}

/** Formulario para publicar una vacante en el career site, con su vista previa. */
export function CrearEmpleo() {
  const { data: sesion } = useSesion();
  const { data: mis } = useMisVacantes();
  const publicar = usePublicarVacante();
  const [borrador, setBorrador] = useState(BORRADOR_VACIO);

  if (!sesion || !mis) return null;
  const { cupo } = mis;
  const editar = (cambio: Partial<BorradorDeVacante>) => setBorrador((b) => ({ ...b, ...cambio }));

  function alPublicar(evento: FormEvent) {
    evento.preventDefault();
    publicar.mutate(borrador, {
      onSuccess: (resultado) => {
        if (resultado.ok) navegar(`/vacantes/${resultado.vacanteId}`);
      },
    });
  }

  const rechazo = publicar.data && !publicar.data.ok ? publicar.data.motivo : null;
  const titulo = (
    <>
      Crear <i>empleo</i>
    </>
  );

  // Primero las publicaciones: si se acabaron, eliminar una vacante no ayuda.
  if (cupo.publicacionesLibres === 0) {
    return (
      <>
        <Encabezado etiqueta="Career site" titulo={titulo} />
        <section className="max-w-xl rounded-[22px] border border-mist-200 bg-white p-6">
          <h2 className="text-xl">Ya publicaste {cupo.limite} vacantes en 30 días</h2>
          <p className="mt-2 text-[15px] text-mist-700">
            Tu plan publica hasta {cupo.limite} vacantes nuevas cada 30 días, aunque elimines
            alguna.
            {cupo.proximaPublicacion &&
              ` Podrás publicar otra el ${formatoDia.format(new Date(cupo.proximaPublicacion))}.`}
          </p>
          <Enlace href="/vacantes" className={`${buttonVariants({ variant: "ink" })} mt-5`}>
            Ir a Mis vacantes
          </Enlace>
        </section>
      </>
    );
  }

  if (cupo.libres === 0) {
    return (
      <>
        <Encabezado etiqueta="Career site" titulo={titulo} />
        <section className="max-w-xl rounded-[22px] border border-mist-200 bg-white p-6">
          <h2 className="text-xl">Tus {cupo.limite} vacantes están activas</h2>
          <p className="mt-2 text-[15px] text-mist-700">
            Tu plan permite {cupo.limite} vacantes a la vez. Elimina una de las activas para
            publicar otra.
          </p>
          <Enlace href="/vacantes" className={`${buttonVariants({ variant: "ink" })} mt-5`}>
            Ir a Mis vacantes
          </Enlace>
        </section>
      </>
    );
  }

  return (
    <>
      <Encabezado
        etiqueta={
          cupo.libres === null
            ? "Career site"
            : cupo.publicacionesLibres !== null && cupo.publicacionesLibres < cupo.libres
              ? `Puedes publicar ${cupo.publicacionesLibres} ${cupo.publicacionesLibres === 1 ? "vacante" : "vacantes"} más en estos 30 días`
              : `Te quedan ${cupo.libres} de ${cupo.limite} vacantes`
        }
        titulo={titulo}
      />
      <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_380px]">
        <form
          onSubmit={alPublicar}
          aria-label="Datos de la vacante"
          className="flex flex-col gap-4"
        >
          <div className="flex flex-col gap-4 rounded-[22px] border border-mist-200 bg-white p-5 md:p-6">
            <Campo etiqueta="Puesto">
              <input
                required
                maxLength={120}
                value={borrador.titulo}
                onChange={(e) => editar({ titulo: e.target.value })}
                placeholder="Coordinador de almacén"
                className={CLASE_CAMPO}
              />
            </Campo>
            <div className="grid gap-4 sm:grid-cols-2">
              <Campo etiqueta="Nivel">
                <select
                  value={borrador.seniority}
                  onChange={(e) => editar({ seniority: e.target.value as Seniority })}
                  className={CLASE_CAMPO}
                >
                  {NIVELES.map((n) => (
                    <option key={n} value={n}>
                      {ETIQUETA_SENIORITY[n]}
                    </option>
                  ))}
                </select>
              </Campo>
              <Campo etiqueta="Ubicación">
                <input
                  required
                  value={borrador.ubicacion}
                  onChange={(e) => editar({ ubicacion: e.target.value })}
                  placeholder="Monterrey, NL"
                  className={CLASE_CAMPO}
                />
              </Campo>
            </div>
            <fieldset>
              <legend className="text-sm font-bold">Modalidad</legend>
              <div className="mt-1.5 inline-flex rounded-xl bg-mist-100 p-1">
                {MODALIDADES.map((m) => (
                  <label
                    key={m}
                    className={`cursor-pointer rounded-lg px-4 py-2 text-sm font-bold has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-aqua-500 ${
                      borrador.modalidad === m ? "bg-white text-ink-900 shadow-sm" : "text-mist-700"
                    }`}
                  >
                    <input
                      type="radio"
                      name="modalidad"
                      value={m}
                      checked={borrador.modalidad === m}
                      onChange={() => editar({ modalidad: m })}
                      className="sr-only"
                    />
                    {ETIQUETA_MODALIDAD[m]}
                  </label>
                ))}
              </div>
            </fieldset>
            <fieldset className="flex flex-col gap-2">
              <legend className="text-sm font-bold">
                Rango salarial mensual ({borrador.moneda})
                <span className="ml-1.5 font-normal text-mist-600">
                  Las vacantes con salario reciben más aplicaciones.
                </span>
              </legend>
              <div className="grid grid-cols-2 gap-4">
                <Campo etiqueta="Desde">
                  <input
                    type="number"
                    min={0}
                    step={500}
                    inputMode="numeric"
                    value={borrador.salarioMin ?? ""}
                    onChange={(e) => editar({ salarioMin: aNumero(e.target.value) })}
                    className={CLASE_CAMPO}
                  />
                </Campo>
                <Campo etiqueta="Hasta">
                  <input
                    type="number"
                    min={borrador.salarioMin ?? 0}
                    step={500}
                    inputMode="numeric"
                    value={borrador.salarioMax ?? ""}
                    onChange={(e) => editar({ salarioMax: aNumero(e.target.value) })}
                    className={CLASE_CAMPO}
                  />
                </Campo>
              </div>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={borrador.salarioPublico}
                  onChange={(e) => editar({ salarioPublico: e.target.checked })}
                  className="h-4 w-4 accent-aqua-600"
                />
                Mostrar el salario en el career site
              </label>
            </fieldset>
            <CampoDeSkills skills={borrador.skills} alCambiar={(skills) => editar({ skills })} />
            <Campo
              etiqueta="Descripción"
              ayuda="Qué hará la persona, a quién reporta y qué necesitas."
            >
              <textarea
                required
                rows={6}
                value={borrador.descripcion}
                onChange={(e) => editar({ descripcion: e.target.value })}
                className={CLASE_CAMPO}
              />
            </Campo>
          </div>
          {rechazo && (
            <p
              role="alert"
              className="rounded-2xl bg-danger-50 p-4 text-sm font-bold text-danger-700"
            >
              {MENSAJE_DE_RECHAZO[rechazo]}
            </p>
          )}
          {publicar.isError && (
            <p
              role="alert"
              className="rounded-2xl bg-danger-50 p-4 text-sm font-bold text-danger-700"
            >
              No pudimos publicar la vacante. Revisa tu conexión e inténtalo de nuevo.
            </p>
          )}
          <div className="flex flex-wrap items-center justify-end gap-3">
            {/* Si las dos son la última, manda la publicación: eliminar no la devuelve. */}
            {cupo.publicacionesLibres === 1 ? (
              <span className="mr-auto max-w-sm text-[13.5px] text-mist-600">
                Es tu última vacante nueva de estos 30 días: eliminar una no te devuelve la
                publicación.
              </span>
            ) : (
              cupo.libres === 1 && (
                <span className="mr-auto max-w-sm text-[13.5px] text-mist-600">
                  Al publicarla usas tu última vacante libre. Para publicar otra después, elimina
                  una de las activas.
                </span>
              )
            )}
            <Button type="submit" disabled={publicar.isPending}>
              Publicar en el career site
            </Button>
          </div>
        </form>

        <div className="flex flex-col gap-4 xl:sticky xl:top-24">
          <span className="font-mono text-[11px] font-semibold uppercase tracking-[0.08em] text-mist-600">
            Vista previa · así la ven los candidatos
          </span>
          <VistaPrevia borrador={borrador} empresa={sesion.empresa.nombre} />
          {!sesion.modulos.includes("cockpit") && <Brochure />}
        </div>
      </div>
    </>
  );
}
