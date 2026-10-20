/**
 * El panel contra Supabase. Las reglas del plan las aplica la base: RLS por
 * empresa, los topes de vacantes activas y de publicaciones (PT409, 0008 y 0010),
 * el de aplicaciones recibidas y el gancho por lotes de 5 (0010). Aquí solo se
 * traduce entre las filas y la forma de `tipos.ts`.
 *
 * Se entra con un enlace al correo y solo con una cuenta que ya existe: la crea la
 * invitación de Vector HR (`inviteUserByEmail`, 0003). Los CVs se bajan con URLs
 * firmadas de Storage y el .zip se arma en el navegador, sin pasar por un
 * servidor nuestro.
 */
import { createClient } from "@supabase/supabase-js";
import type { Database } from "@vortex/supabase-client/types";
import {
  ETAPAS_DEL_PIPELINE,
  type EtapaDelPipeline,
  LIMITES_DEL_PLAN,
  siguientePaso,
} from "@vortex/types/reglas";
import { iniciales } from "@vortex/ui";

import {
  type AdaptadorDelPanel,
  type EvaluacionConIa,
  type MotivoDeRechazo,
  SinAccesoAlPanel,
} from "./tipos";

type Cliente = ReturnType<typeof createClient<Database>>;

/** Quiénes usan el panel: los mismos roles que deja pasar la RLS de vacantes (0001). */
const ROLES_DEL_PANEL = ["HR", "Director", "SuperAdmin"];

const NOMBRE_DEL_PLAN = { gratis: "Career site · gratis", ia: "Servicios de IA" } as const;

/** Lo que dura el enlace a cada CV en la lista de aplicados. */
const SEGUNDOS_DEL_ENLACE_AL_CV = 60 * 60;
/** Para el .zip basta con lo que tarda en bajarse. */
const SEGUNDOS_DE_LA_DESCARGA = 10 * 60;

const ES_UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

interface Claims {
  app_metadata?: { empresa_id?: string; app_role?: string };
}

/**
 * El payload del JWT de la sesión, sin verificar: lo verifica la base en cada
 * consulta. `empresa_id` y `app_role` los pone el hook de 0003 y 0008.
 */
export function claimsDelToken(token: string): Claims | null {
  const [, payload] = token.split(".");
  if (!payload) return null;
  try {
    const binario = atob(payload.replace(/-/g, "+").replace(/_/g, "/"));
    const bytes = Uint8Array.from(binario, (c) => c.charCodeAt(0));
    return JSON.parse(new TextDecoder().decode(bytes)) as Claims;
  } catch {
    return null;
  }
}

/**
 * "Coordinador de almacén" → "coordinador-de-almacen-3f9a1c". El slug es único en
 * todo el career site (0012): el sufijo evita que choquen dos empresas con el
 * mismo puesto y, si aun así chocan, se reintenta con otro.
 */
export function slugDeVacante(titulo: string, sufijo = crypto.randomUUID().slice(0, 6)): string {
  const base = titulo
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .slice(0, 60)
    .replace(/^-+|-+$/g, "");
  return base ? `${base}-${sufijo}` : sufijo;
}

/** Por qué la base no publicó la vacante; `null` si el error no es del plan ni de los datos. */
export function motivoDelRechazo(error: {
  code?: string;
  message?: string;
}): MotivoDeRechazo | "slug-repetido" | null {
  switch (error.code) {
    case "PT409":
      return error.message?.includes("publicaciones") ? "sin-publicaciones" : "sin-cupo";
    case "23505":
      return error.message?.includes("slug") ? "slug-repetido" : null;
    case "22001":
    case "22P02":
    case "23502":
    case "23514":
      return "datos-invalidos";
    default:
      return null;
  }
}

/** Sin lo que Windows y macOS no aceptan en el nombre de un archivo. */
function nombreDeArchivo(texto: string): string {
  const limpio = texto
    .replace(/[\p{Cc}<>:"/\\|?*]+/gu, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 80)
    .trim();
  return limpio || "Sin nombre";
}

export const nombreDelZip = (titulo: string) => `CVs - ${nombreDeArchivo(titulo)}.zip`;

/** Formato del CV según su ruta en Storage (`{empresa}/{id}.pdf|docx`, career site). */
export const formatoDelCv = (ruta: string) =>
  ruta.toLowerCase().endsWith(".docx") ? ("docx" as const) : ("pdf" as const);

/** "07 - María López.pdf": el número es el orden en que llegó la aplicación. */
export function nombreEnElZip(numero: number, candidato: string, ruta: string): string {
  return `${String(numero).padStart(2, "0")} - ${nombreDeArchivo(candidato)}.${formatoDelCv(ruta)}`;
}

/**
 * La evaluación con IA de una fila de `applications`, o `null` si no la hay (ADR-021).
 * El siguiente paso lo pone la política del dominio según el score, no el modelo.
 */
export function evaluacionDe(fila: {
  fit_score: number | null;
  fit_rationale: string | null;
  fit_gaps: string[] | null;
  fit_strengths: string[] | null;
}): EvaluacionConIa | null {
  if (fila.fit_score === null) return null;
  const score = Number(fila.fit_score);
  return {
    score,
    razonamiento: fila.fit_rationale ?? "",
    fortalezas: fila.fit_strengths ?? [],
    brechas: fila.fit_gaps ?? [],
    siguientePaso: siguientePaso(score),
  };
}

export function crearAdaptadorDeSupabase(url: string, clave: string): AdaptadorDelPanel {
  return adaptadorDeSupabase(
    createClient<Database>(url, clave, {
      auth: {
        // La invitación (`inviteUserByEmail`) vuelve con los tokens en el hash, que es
        // el flujo implícito: un cliente PKCE la rechaza ("Not a valid PKCE flow url").
        flowType: "implicit",
        detectSessionInUrl: true,
        persistSession: true,
        autoRefreshToken: true,
      },
    }),
  );
}

export function adaptadorDeSupabase(supabase: Cliente): AdaptadorDelPanel {
  async function sesionActual() {
    const { data, error } = await supabase.auth.getSession();
    if (error) throw error;
    const { session } = data;
    if (!session) return null;
    const meta = claimsDelToken(session.access_token)?.app_metadata;
    return {
      userId: session.user.id,
      correo: session.user.email ?? "",
      empresaId: meta?.empresa_id ?? null,
      rol: meta?.app_role ?? null,
    };
  }

  async function planDeLaEmpresa() {
    const { data, error } = await supabase.from("empresas").select("plan").single();
    if (error) throw error;
    return data.plan;
  }

  /** Las aplicaciones de la vacante con su candidato; RLS deja solo las de la empresa. */
  async function aplicacionesDe(vacanteId: string, { recientesPrimero = true } = {}) {
    const { data, error } = await supabase
      .from("applications")
      .select(
        "id, status, applied_at, fit_score, fit_rationale, fit_gaps, fit_strengths, candidatos(full_name, cv_url)",
      )
      .eq("vacante_id", vacanteId)
      .order("applied_at", { ascending: !recientesPrimero });
    if (error) throw error;
    return data;
  }

  async function urlsFirmadas(rutas: string[], segundos: number) {
    if (rutas.length === 0) return new Map<string, string>();
    const { data, error } = await supabase.storage.from("cvs").createSignedUrls(rutas, segundos);
    if (error) throw error;
    return new Map(data.flatMap((f) => (f.path && f.signedUrl ? [[f.path, f.signedUrl]] : [])));
  }

  return {
    async obtenerSesion() {
      const sesion = await sesionActual();
      if (!sesion) return null;
      if (!sesion.empresaId || !ROLES_DEL_PANEL.includes(sesion.rol ?? "")) {
        throw new SinAccesoAlPanel();
      }
      const [perfil, empresa] = await Promise.all([
        supabase.from("profiles").select("full_name").eq("id", sesion.userId).maybeSingle(),
        supabase.from("empresas").select("name, plan").eq("id", sesion.empresaId).single(),
      ]);
      if (perfil.error) throw perfil.error;
      if (empresa.error) throw empresa.error;
      const nombre = perfil.data?.full_name || sesion.correo;
      return {
        usuario: { nombre: nombre.split(/\s+/)[0] || nombre, iniciales: iniciales(nombre) },
        empresa: { nombre: empresa.data.name },
        plan: NOMBRE_DEL_PLAN[empresa.data.plan],
        modulos: LIMITES_DEL_PLAN[empresa.data.plan].modulos,
      };
    },

    async listarMisVacantes() {
      const [vacantes, cupo, recibidas] = await Promise.all([
        supabase
          .from("vacantes")
          .select("id, title, status, modality, location, publicada_en, created_at")
          .eq("status", "open")
          .order("publicada_en", { ascending: false, nullsFirst: false }),
        supabase.rpc("mi_cupo_de_vacantes").single(),
        supabase.rpc("cupos_de_aplicaciones"),
      ]);
      if (vacantes.error) throw vacantes.error;
      if (cupo.error) throw cupo.error;
      if (recibidas.error) throw recibidas.error;
      const porVacante = new Map(recibidas.data.map((r) => [r.vacante_id, r]));
      return {
        vacantes: vacantes.data.map((v) => ({
          id: v.id,
          titulo: v.title,
          estado: v.status,
          modalidad: v.modality,
          ubicacion: v.location ?? "",
          publicadaEn: v.publicada_en ?? v.created_at,
          aplicaciones: porVacante.get(v.id)?.recibidas ?? 0,
          cupoCompleto: porVacante.get(v.id)?.completo ?? false,
        })),
        cupo: {
          activas: cupo.data.activas,
          limite: cupo.data.limite,
          libres: cupo.data.libres,
          maxAplicacionesPorVacante: cupo.data.max_aplicaciones,
          publicacionesLibres: cupo.data.publicaciones_libres,
          proximaPublicacion: cupo.data.proxima_publicacion,
        },
      };
    },

    async publicarVacante(borrador) {
      const sesion = await sesionActual();
      if (!sesion?.empresaId) throw new SinAccesoAlPanel();
      for (let intento = 0; intento < 3; intento++) {
        const { data, error } = await supabase
          .from("vacantes")
          .insert({
            empresa_id: sesion.empresaId,
            slug: slugDeVacante(borrador.titulo),
            title: borrador.titulo.trim(),
            jd: borrador.descripcion.trim(),
            icp_text: null,
            seniority: borrador.seniority,
            modality: borrador.modalidad,
            location: borrador.ubicacion.trim() || null,
            salary_min: borrador.salarioMin,
            salary_max: borrador.salarioMax,
            currency: borrador.moneda,
            salario_publico: borrador.salarioPublico,
            skills: borrador.skills,
            status: "open",
            closed_at: null,
          })
          .select("id")
          .single();
        if (!error) return { ok: true, vacanteId: data.id };
        const motivo = motivoDelRechazo(error);
        if (motivo === "slug-repetido") continue;
        if (motivo) return { ok: false, motivo };
        throw error;
      }
      throw new Error("no se encontró un slug libre para la vacante");
    },

    /** Cerrarla es el borrado lógico: el trigger de 0008 pone `deleted_at`. */
    async eliminarVacante(vacanteId) {
      const { error } = await supabase
        .from("vacantes")
        .update({ status: "closed" })
        .eq("id", vacanteId);
      if (error) throw error;
    },

    async obtenerPipeline(vacanteId) {
      if (!ES_UUID.test(vacanteId)) return null;
      const [vacante, filas, cupo, gancho, evaluaciones, plan] = await Promise.all([
        supabase
          .from("vacantes")
          .select("id, title, publicada_en, created_at")
          .eq("id", vacanteId)
          .eq("status", "open")
          .maybeSingle(),
        aplicacionesDe(vacanteId),
        supabase.rpc("cupos_de_aplicaciones").eq("vacante_id", vacanteId).maybeSingle(),
        // Sin filas en el plan con IA: ahí no hay gancho.
        supabase
          .rpc("resumen_del_gancho", { p_vacante: vacanteId })
          .maybeSingle(),
        // Y al revés: sin filas en el plan gratis (0014).
        supabase
          .rpc("resumen_de_evaluaciones", { p_vacante: vacanteId })
          .maybeSingle(),
        planDeLaEmpresa(),
      ]);
      if (vacante.error) throw vacante.error;
      if (cupo.error) throw cupo.error;
      if (gancho.error) throw gancho.error;
      if (evaluaciones.error) throw evaluaciones.error;
      if (!vacante.data) return null;

      const rutas = filas.flatMap((a) => (a.candidatos?.cv_url ? [a.candidatos.cv_url] : []));
      // Sin enlaces la lista se sigue viendo; el .zip vuelve a pedirlos.
      const enlaces = await urlsFirmadas(rutas, SEGUNDOS_DEL_ENLACE_AL_CV).catch(
        () => new Map<string, string>(),
      );
      const recibidas = cupo.data?.recibidas ?? filas.length;
      const visibles: readonly EtapaDelPipeline[] = LIMITES_DEL_PLAN[plan].etapasVisibles;
      const g = gancho.data;
      return {
        vacante: {
          id: vacante.data.id,
          titulo: vacante.data.title,
          publicadaEn: vacante.data.publicada_en ?? vacante.data.created_at,
          aplicaciones: recibidas,
        },
        maxAplicaciones: cupo.data?.limite ?? null,
        etapas: ETAPAS_DEL_PIPELINE.map((etapa) => ({
          etapa,
          conteo: !visibles.includes(etapa)
            ? null
            : etapa === "applied"
              ? recibidas
              : filas.filter((a) => a.status === etapa).length,
        })),
        aplicados: filas.map((a) => {
          const ruta = a.candidatos?.cv_url ?? null;
          return {
            id: a.id,
            nombre: a.candidatos?.full_name ?? "Sin nombre",
            aplicoEn: a.applied_at,
            estado: a.status,
            cvUrl: ruta ? (enlaces.get(ruta) ?? null) : null,
            cvFormato: ruta ? formatoDelCv(ruta) : null,
            evaluacion: evaluacionDe(a),
          };
        }),
        evaluaciones: evaluaciones.data
          ? {
              aplicaciones: evaluaciones.data.aplicaciones,
              evaluadas: evaluaciones.data.evaluadas,
              enEspera: evaluaciones.data.en_espera,
              sinEvaluar: evaluaciones.data.sin_evaluar,
              ilegibles: evaluaciones.data.ilegibles,
              sinIa: evaluaciones.data.sin_ia,
            }
          : null,
        gancho: g
          ? {
              skills: g.skills,
              revisados: g.revisados,
              enEspera: g.en_espera,
              ilegibles: g.ilegibles,
              conLaMayoria: g.con_la_mayoria,
              conTodas: g.con_todas,
            }
          : null,
      };
    },

    /**
     * La base pide el motivo si la evaluó la IA (PT422) y que mida de 10 a 500
     * caracteres (23514, 0015): los dos son "falta un motivo que sirva".
     */
    async descartar(aplicacionId, motivo) {
      const { error } = await supabase
        .from("applications")
        .update({ status: "rejected", motivo_de_descarte: motivo.trim() || null })
        .eq("id", aplicacionId);
      if (!error) return { ok: true };
      if (error.code === "PT422" || error.code === "23514")
        return { ok: false, motivo: "sin-motivo" };
      throw error;
    },

    async solicitarDescargaDeCvs(vacanteId) {
      const [vacante, filas] = await Promise.all([
        supabase.from("vacantes").select("title").eq("id", vacanteId).single(),
        aplicacionesDe(vacanteId, { recientesPrimero: false }),
      ]);
      if (vacante.error) throw vacante.error;
      const conCv = filas.flatMap((a) =>
        a.candidatos?.cv_url ? [{ nombre: a.candidatos.full_name, ruta: a.candidatos.cv_url }] : [],
      );
      if (conCv.length === 0) return { url: null, motivo: "sin-cvs" };

      const enlaces = await urlsFirmadas(
        conCv.map((c) => c.ruta),
        SEGUNDOS_DE_LA_DESCARGA,
      );
      const { downloadZip } = await import("client-zip");
      // Se piden todos a la vez y se meten al .zip en orden de llegada.
      const respuestas = conCv.map((c) => {
        const enlace = enlaces.get(c.ruta);
        return enlace ? fetch(enlace).catch(() => null) : Promise.resolve(null);
      });
      let omitidos = 0;
      async function* archivos() {
        for (const [i, c] of conCv.entries()) {
          const respuesta = await respuestas[i];
          if (!respuesta?.ok) {
            omitidos++;
            continue;
          }
          yield { name: nombreEnElZip(i + 1, c.nombre, c.ruta), input: respuesta };
        }
      }
      const zip = await downloadZip(archivos()).blob();
      return { url: URL.createObjectURL(zip), nombre: nombreDelZip(vacante.data.title), omitidos };
    },

    async registrarInteres(origen) {
      const { error } = await supabase.rpc("registrar_interes_en_ia", { p_origen: origen });
      if (error) throw error;
    },

    async entrar(correo) {
      const { error } = await supabase.auth.signInWithOtp({
        email: correo.trim(),
        options: { shouldCreateUser: false, emailRedirectTo: `${window.location.origin}/` },
      });
      // Sin cuenta, GoTrue contesta "Signups not allowed for otp". Se responde igual
      // que con cuenta para no revelar qué correos usan el panel.
      if (!error || error.code === "otp_disabled") return { ok: true };
      return { ok: false, motivo: error.status === 429 ? "demasiados-intentos" : "error" };
    },

    async salir() {
      const { error } = await supabase.auth.signOut({ scope: "local" });
      if (error) throw error;
    },

    alCambiarLaSesion(avisar) {
      let anterior: string | null | undefined;
      const { data } = supabase.auth.onAuthStateChange((_evento, sesion) => {
        const actual = sesion?.user.id ?? null;
        // Supabase pide no llamar al cliente dentro del callback: se avisa después.
        if (anterior !== undefined && actual !== anterior) setTimeout(avisar, 0);
        anterior = actual;
      });
      return () => data.subscription.unsubscribe();
    },
  };
}
