/**
 * El adaptador de Supabase contra un `fetch` falso: supabase-js arma las
 * peticiones de verdad (PostgREST, Auth y Storage) y aquí se contestan como lo
 * hace la base. Lo que la base decide (RLS, topes, gancho) lo prueban los tests
 * de seguridad del hr-engine contra Postgres; aquí, que el panel lo traduzca bien.
 */
import { createClient } from "@supabase/supabase-js";
import type { Database } from "@vortex/supabase-client/types";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  adaptadorDeSupabase,
  claimsDelToken,
  motivoDelRechazo,
  nombreEnElZip,
  slugDeVacante,
} from "../datos/panel-supabase";
import { SinAccesoAlPanel } from "../datos/tipos";

const URL_DE_PRUEBA = "http://supabase.prueba";
const EMPRESA = "6f1c2a9e-3b7d-4c8a-9e1f-2a3b4c5d6e7f";
const VACANTE = "0b9c8d7e-6f5a-4b3c-8d2e-1f0a9b8c7d6e";

interface Peticion {
  metodo: string;
  ruta: string;
  url: URL;
  cuerpo: unknown;
  /** Pidió una sola fila (`.single()` / `.maybeSingle()` en una rpc o un insert). */
  objeto: boolean;
}

type Respuesta = { estado?: number; filas?: unknown; texto?: string } | undefined;

const b64url = (texto: string) =>
  btoa(String.fromCharCode(...new TextEncoder().encode(texto)))
    .replace(/=+$/, "")
    .replace(/\+/g, "-")
    .replace(/\//g, "_");

function tokenCon(appMetadata: Record<string, string>) {
  const cuerpo = {
    sub: "usuario-1",
    exp: Math.floor(Date.now() / 1000) + 3600,
    app_metadata: appMetadata,
    user_metadata: { full_name: "Mariana Villarreal" },
  };
  return `${b64url('{"alg":"HS256","typ":"JWT"}')}.${b64url(JSON.stringify(cuerpo))}.firma`;
}

/**
 * Un cliente de supabase-js con la sesión ya guardada y un `fetch` que contesta
 * `responder`. Sin respuesta, la petición es un 404: así se nota si el adaptador
 * pide algo que el test no esperaba.
 */
function clienteDePrueba(
  responder: (p: Peticion) => Respuesta,
  appMetadata: Record<string, string> = { empresa_id: EMPRESA, app_role: "HR" },
) {
  const peticiones: Peticion[] = [];
  const fetchFalso = async (entrada: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(entrada instanceof Request ? entrada.url : entrada.toString());
    const encabezados = new Headers(init?.headers);
    const cuerpo = typeof init?.body === "string" ? JSON.parse(init.body) : undefined;
    const peticion: Peticion = {
      metodo: init?.method ?? "GET",
      ruta: url.pathname,
      url,
      cuerpo,
      objeto: (encabezados.get("accept") ?? "").includes("vnd.pgrst.object"),
    };
    peticiones.push(peticion);
    const r = responder(peticion);
    if (!r) return new Response(JSON.stringify({ message: "sin ruta" }), { status: 404 });
    if (r.texto !== undefined) return new Response(r.texto, { status: r.estado ?? 200 });
    const filas = peticion.objeto && Array.isArray(r.filas) ? r.filas[0] : r.filas;
    return new Response(r.filas === undefined ? null : JSON.stringify(filas), {
      status: r.estado ?? 200,
      // Con esta versión, Auth contesta los errores como `{ code, message }`.
      headers: { "content-type": "application/json", "x-supabase-api-version": "2024-01-01" },
    });
  };
  vi.stubGlobal("fetch", fetchFalso);

  const sesion = {
    access_token: tokenCon(appMetadata),
    refresh_token: "refresco",
    token_type: "bearer",
    expires_in: 3600,
    expires_at: Math.floor(Date.now() / 1000) + 3600,
    user: {
      id: "usuario-1",
      email: "mariana@andes.mx",
      aud: "authenticated",
      app_metadata: {},
      user_metadata: {},
      created_at: "2026-10-01T00:00:00Z",
    },
  };
  const memoria = new Map([["sesion-de-prueba", JSON.stringify(sesion)]]);
  const cliente = createClient<Database>(URL_DE_PRUEBA, "sb_publishable_prueba", {
    global: { fetch: fetchFalso },
    auth: {
      storageKey: "sesion-de-prueba",
      storage: {
        getItem: (clave) => memoria.get(clave) ?? null,
        setItem: (clave, valor) => void memoria.set(clave, valor),
        removeItem: (clave) => void memoria.delete(clave),
      },
      persistSession: true,
      autoRefreshToken: false,
      detectSessionInUrl: false,
    },
  });
  return { adaptador: adaptadorDeSupabase(cliente), peticiones };
}

const BORRADOR = {
  titulo: "Coordinador de almacén",
  seniority: "semi-senior",
  modalidad: "hybrid",
  ubicacion: "Monterrey, NL",
  descripcion: "Coordina el turno.",
  salarioMin: 18000,
  salarioMax: 22000,
  moneda: "MXN",
  salarioPublico: true,
  skills: ["Excel", "Inventarios"],
} as const;

/**
 * El .zip llega como `Blob` de Node o de jsdom según la versión de Node (en CI, de
 * Node). El de jsdom no trae `arrayBuffer()` y el `FileReader` de jsdom no acepta el
 * de Node: se usa lo que haya.
 */
function leer(blob: Blob): Promise<ArrayBuffer> {
  if (typeof blob.arrayBuffer === "function") return blob.arrayBuffer();
  return new Promise((resolve, reject) => {
    const lector = new FileReader();
    lector.onload = () => resolve(lector.result as ArrayBuffer);
    lector.onerror = () => reject(lector.error);
    lector.readAsArrayBuffer(blob);
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("reglas puras del adaptador", () => {
  it("el slug no lleva acentos ni signos y termina en el sufijo", () => {
    expect(slugDeVacante("Coordinador de almacén (turno B)", "3f9a1c")).toBe(
      "coordinador-de-almacen-turno-b-3f9a1c",
    );
    expect(slugDeVacante("¿?", "3f9a1c")).toBe("3f9a1c");
    expect(slugDeVacante("x".repeat(90), "3f9a1c")).toHaveLength(60 + 7);
  });

  it("lee empresa y rol del token, incluso con acentos en otros claims", () => {
    const claims = claimsDelToken(tokenCon({ empresa_id: EMPRESA, app_role: "Director" }));
    expect(claims?.app_metadata).toEqual({ empresa_id: EMPRESA, app_role: "Director" });
    expect(claimsDelToken("no-es-un-jwt")).toBeNull();
  });

  it("traduce los rechazos de la base a motivos del panel", () => {
    const pt409 = (message: string) => motivoDelRechazo({ code: "PT409", message });
    expect(pt409("limite de vacantes del plan alcanzado")).toBe("sin-cupo");
    expect(pt409("limite de publicaciones del plan alcanzado")).toBe("sin-publicaciones");
    expect(
      motivoDelRechazo({
        code: "23505",
        message: 'duplicate key value violates unique constraint "vacantes_slug_unico"',
      }),
    ).toBe("slug-repetido");
    expect(motivoDelRechazo({ code: "23514", message: "vacantes_skills_validas" })).toBe(
      "datos-invalidos",
    );
    expect(motivoDelRechazo({ code: "42501", message: "permission denied" })).toBeNull();
  });

  it("nombra los CVs del .zip por orden de llegada, sin caracteres que rompan el archivo", () => {
    expect(nombreEnElZip(7, "María López", "e/1.pdf")).toBe("07 - María López.pdf");
    expect(nombreEnElZip(12, 'José "Pepe" / Ruiz', "e/2.DOCX")).toBe("12 - José Pepe Ruiz.docx");
    expect(nombreEnElZip(1, "   ", "e/3.pdf")).toBe("01 - Sin nombre.pdf");
  });
});

describe("sesión", () => {
  it("arma la sesión con el nombre del perfil y el plan de la empresa", async () => {
    const { adaptador } = clienteDePrueba((p) => {
      if (p.ruta === "/rest/v1/profiles") return { filas: [{ full_name: "Mariana Villarreal" }] };
      if (p.ruta === "/rest/v1/empresas") {
        return { filas: [{ name: "Andes Logística", plan: "gratis" }] };
      }
      return undefined;
    });
    expect(await adaptador.obtenerSesion()).toEqual({
      usuario: { nombre: "Mariana", iniciales: "MV" },
      empresa: { nombre: "Andes Logística" },
      plan: "Career site · gratis",
      modulos: ["career-site"],
    });
  });

  it.each([
    ["sin empresa", { app_role: "HR" }],
    ["con un rol que no usa el panel", { empresa_id: EMPRESA, app_role: "Colaborador" }],
  ])("una cuenta %s no entra", async (_caso, meta) => {
    const { adaptador, peticiones } = clienteDePrueba(() => undefined, meta);
    await expect(adaptador.obtenerSesion()).rejects.toBeInstanceOf(SinAccesoAlPanel);
    expect(peticiones).toHaveLength(0);
  });

  it("pide el enlace solo para cuentas que existen y no revela cuáles", async () => {
    let respuesta: Respuesta = {
      estado: 422,
      filas: { code: "otp_disabled", message: "Signups not allowed for otp" },
    };
    const { adaptador, peticiones } = clienteDePrueba((p) =>
      p.ruta === "/auth/v1/otp" ? respuesta : undefined,
    );

    expect(await adaptador.entrar(" nadie@ejemplo.com ")).toEqual({ ok: true });
    const [otp] = peticiones;
    expect(otp?.cuerpo).toMatchObject({ email: "nadie@ejemplo.com", create_user: false });
    expect(otp?.url.searchParams.get("redirect_to")).toBe(`${window.location.origin}/`);

    respuesta = { estado: 429, filas: { code: "over_email_send_rate_limit", message: "…" } };
    expect(await adaptador.entrar("mariana@andes.mx")).toEqual({
      ok: false,
      motivo: "demasiados-intentos",
    });
    respuesta = { estado: 500, filas: { code: "unexpected_failure", message: "…" } };
    expect(await adaptador.entrar("mariana@andes.mx")).toEqual({ ok: false, motivo: "error" });
  });

  it("avisa cuando sale la persona", async () => {
    const { adaptador } = clienteDePrueba((p) =>
      p.ruta === "/auth/v1/logout" ? { estado: 204 } : undefined,
    );
    const avisar = vi.fn();
    const dejarDeEscuchar = adaptador.alCambiarLaSesion(avisar);
    await vi.waitFor(() => expect(avisar).not.toHaveBeenCalled());
    await adaptador.salir();
    await vi.waitFor(() => expect(avisar).toHaveBeenCalledOnce());
    dejarDeEscuchar();
  });
});

describe("vacantes", () => {
  it("publica con la empresa del token y reintenta si el slug ya existe (0012)", async () => {
    let intentos = 0;
    const { adaptador, peticiones } = clienteDePrueba((p) => {
      if (p.metodo !== "POST" || p.ruta !== "/rest/v1/vacantes") return;
      intentos++;
      return intentos === 1
        ? {
            estado: 409,
            filas: {
              code: "23505",
              message: 'duplicate key value violates unique constraint "vacantes_slug_unico"',
            },
          }
        : { estado: 201, filas: [{ id: VACANTE }] };
    });

    expect(await adaptador.publicarVacante({ ...BORRADOR, skills: [...BORRADOR.skills] })).toEqual({
      ok: true,
      vacanteId: VACANTE,
    });
    const inserts = peticiones.map((p) => p.cuerpo as Record<string, unknown>);
    expect(inserts).toHaveLength(2);
    expect(inserts[0]).toMatchObject({
      empresa_id: EMPRESA,
      title: "Coordinador de almacén",
      jd: "Coordina el turno.",
      skills: ["Excel", "Inventarios"],
      status: "open",
    });
    expect(inserts[0]?.slug).toMatch(/^coordinador-de-almacen-[0-9a-f]{6}$/);
    expect(inserts[1]?.slug).not.toBe(inserts[0]?.slug);
  });

  it.each([
    ["limite de vacantes del plan alcanzado", "sin-cupo"],
    ["limite de publicaciones del plan alcanzado", "sin-publicaciones"],
  ])("el tope «%s» llega como motivo, no como error", async (message, motivo) => {
    const { adaptador } = clienteDePrueba(() => ({
      estado: 409,
      filas: { code: "PT409", message },
    }));
    expect(await adaptador.publicarVacante({ ...BORRADOR, skills: [...BORRADOR.skills] })).toEqual({
      ok: false,
      motivo,
    });
  });

  it("un error que no es del plan se propaga", async () => {
    const { adaptador } = clienteDePrueba(() => ({
      estado: 403,
      filas: { code: "42501", message: "new row violates row-level security policy" },
    }));
    await expect(
      adaptador.publicarVacante({ ...BORRADOR, skills: [...BORRADOR.skills] }),
    ).rejects.toMatchObject({ code: "42501" });
  });

  it("junta las vacantes activas con sus recibidas y el cupo del plan", async () => {
    const otra = "1a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d";
    const { adaptador, peticiones } = clienteDePrueba((p) => {
      if (p.ruta === "/rest/v1/vacantes") {
        return {
          filas: [
            {
              id: VACANTE,
              title: "Analista",
              status: "open",
              modality: "onsite",
              location: null,
              publicada_en: "2026-10-10T12:00:00+00:00",
              created_at: "2026-10-09T12:00:00+00:00",
            },
            {
              id: otra,
              title: "Chofer",
              status: "open",
              modality: "onsite",
              location: "Apodaca, NL",
              publicada_en: null,
              created_at: "2026-10-12T12:00:00+00:00",
            },
          ],
        };
      }
      if (p.ruta === "/rest/v1/rpc/mi_cupo_de_vacantes") {
        return {
          filas: [
            {
              activas: 2,
              limite: 4,
              libres: 2,
              max_aplicaciones: 50,
              publicaciones_libres: 0,
              proxima_publicacion: "2026-11-09T12:00:00+00:00",
            },
          ],
        };
      }
      if (p.ruta === "/rest/v1/rpc/cupos_de_aplicaciones") {
        return { filas: [{ vacante_id: VACANTE, recibidas: 50, limite: 50, completo: true }] };
      }
      return undefined;
    });

    const { vacantes, cupo } = await adaptador.listarMisVacantes();
    expect(peticiones.find((p) => p.ruta === "/rest/v1/vacantes")?.url.search).toContain(
      "status=eq.open",
    );
    expect(vacantes.map((v) => [v.titulo, v.aplicaciones, v.cupoCompleto, v.ubicacion])).toEqual([
      ["Analista", 50, true, ""],
      ["Chofer", 0, false, "Apodaca, NL"],
    ]);
    expect(vacantes[1]?.publicadaEn).toBe("2026-10-12T12:00:00+00:00");
    expect(cupo).toEqual({
      activas: 2,
      limite: 4,
      libres: 2,
      maxAplicacionesPorVacante: 50,
      publicacionesLibres: 0,
      proximaPublicacion: "2026-11-09T12:00:00+00:00",
    });
  });

  it("eliminar es cerrar la vacante: el borrado lógico lo pone la base", async () => {
    const { adaptador, peticiones } = clienteDePrueba((p) =>
      p.metodo === "PATCH" ? { estado: 204 } : undefined,
    );
    await adaptador.eliminarVacante(VACANTE);
    expect(peticiones[0]?.cuerpo).toEqual({ status: "closed" });
    expect(peticiones[0]?.url.searchParams.get("id")).toBe(`eq.${VACANTE}`);
  });
});

/** Las columnas de la evaluación de una aplicación que la IA no evaluó. */
const SIN_EVALUAR = { fit_score: null, fit_rationale: null, fit_gaps: [], fit_strengths: [] };

describe("pipeline", () => {
  it("una vacante que no es un uuid no se busca", async () => {
    const { adaptador, peticiones } = clienteDePrueba(() => undefined);
    expect(await adaptador.obtenerPipeline("coordinador-de-almacen")).toBeNull();
    expect(peticiones).toHaveLength(0);
  });

  it("en el plan gratis abre solo Aplicados, con el gancho y un enlace por CV", async () => {
    const { adaptador } = clienteDePrueba((p) => {
      switch (p.ruta) {
        case "/rest/v1/vacantes":
          return {
            filas: [
              {
                id: VACANTE,
                title: "Coordinador",
                publicada_en: "2026-10-10T12:00:00+00:00",
                created_at: "2026-10-10T12:00:00+00:00",
              },
            ],
          };
        case "/rest/v1/applications":
          return {
            filas: [
              {
                id: "a2",
                status: "applied",
                applied_at: "2026-10-12T10:00:00+00:00",
                ...SIN_EVALUAR,
                candidatos: { full_name: "José Ruiz", cv_url: `${EMPRESA}/b.docx` },
              },
              {
                id: "a1",
                status: "applied",
                applied_at: "2026-10-11T10:00:00+00:00",
                ...SIN_EVALUAR,
                candidatos: { full_name: "Ana Paz", cv_url: null },
              },
            ],
          };
        case "/rest/v1/rpc/cupos_de_aplicaciones":
          return { filas: [{ vacante_id: VACANTE, recibidas: 3, limite: 50, completo: false }] };
        case "/rest/v1/rpc/resumen_del_gancho":
          return {
            filas: [
              {
                aplicaciones: 3,
                skills: 4,
                revisados: 0,
                en_espera: 2,
                ilegibles: 1,
                con_la_mayoria: 0,
                con_todas: 0,
              },
            ],
          };
        // En el plan gratis no hay evaluación con IA: la rpc no devuelve filas (0014).
        case "/rest/v1/rpc/resumen_de_evaluaciones":
          return { filas: [] };
        case "/rest/v1/empresas":
          return { filas: [{ plan: "gratis" }] };
        case "/storage/v1/object/sign/cvs":
          return {
            filas: [
              {
                path: `${EMPRESA}/b.docx`,
                signedURL: `/object/sign/cvs/${EMPRESA}/b.docx?token=t`,
                error: null,
              },
            ],
          };
      }
      return undefined;
    });

    const pipeline = await adaptador.obtenerPipeline(VACANTE);
    expect(pipeline?.evaluaciones).toBeNull();
    expect(pipeline?.vacante.aplicaciones).toBe(3);
    expect(pipeline?.maxAplicaciones).toBe(50);
    expect(pipeline?.etapas.map((e) => e.conteo)).toEqual([3, null, null, null, null]);
    expect(pipeline?.gancho).toEqual({
      skills: 4,
      revisados: 0,
      enEspera: 2,
      ilegibles: 1,
      conLaMayoria: 0,
      conTodas: 0,
    });
    expect(pipeline?.aplicados).toEqual([
      {
        id: "a2",
        nombre: "José Ruiz",
        aplicoEn: "2026-10-12T10:00:00+00:00",
        estado: "applied",
        cvUrl: `${URL_DE_PRUEBA}/storage/v1/object/sign/cvs/${EMPRESA}/b.docx?token=t`,
        cvFormato: "docx",
        evaluacion: null,
      },
      {
        id: "a1",
        nombre: "Ana Paz",
        aplicoEn: "2026-10-11T10:00:00+00:00",
        estado: "applied",
        cvUrl: null,
        cvFormato: null,
        evaluacion: null,
      },
    ]);
  });

  it("en el plan con IA trae la evaluación de cada aplicación y el resumen (0014)", async () => {
    const { adaptador, peticiones } = clienteDePrueba((p) => {
      switch (p.ruta) {
        case "/rest/v1/vacantes":
          return {
            filas: [
              {
                id: VACANTE,
                title: "Backend",
                publicada_en: "2026-10-10T12:00:00+00:00",
                created_at: "2026-10-10T12:00:00+00:00",
              },
            ],
          };
        case "/rest/v1/applications":
          return {
            filas: [
              {
                id: "a1",
                status: "evaluated",
                applied_at: "2026-10-11T10:00:00+00:00",
                fit_score: 7.5,
                fit_rationale: "Lidera equipos backend con Python.",
                fit_gaps: ["Celery"],
                fit_strengths: ["Python", "FastAPI"],
                candidatos: { full_name: "Ana Paz", cv_url: null },
              },
              {
                id: "a2",
                status: "applied",
                applied_at: "2026-10-12T10:00:00+00:00",
                fit_score: null,
                fit_rationale: null,
                fit_gaps: [],
                fit_strengths: [],
                candidatos: { full_name: "José Ruiz", cv_url: null },
              },
            ],
          };
        case "/rest/v1/rpc/cupos_de_aplicaciones":
          return { filas: [{ vacante_id: VACANTE, recibidas: 2, limite: null, completo: false }] };
        case "/rest/v1/rpc/resumen_del_gancho":
          return { filas: [] };
        case "/rest/v1/rpc/resumen_de_evaluaciones":
          return {
            filas: [
              {
                aplicaciones: 2,
                evaluadas: 1,
                en_espera: 1,
                sin_evaluar: 0,
                ilegibles: 0,
                sin_ia: 0,
              },
            ],
          };
        case "/rest/v1/empresas":
          return { filas: [{ plan: "ia" }] };
      }
      return undefined;
    });

    const pipeline = await adaptador.obtenerPipeline(VACANTE);

    const select = peticiones.find((p) => p.ruta === "/rest/v1/applications")?.url.searchParams;
    expect(select?.get("select")).toContain("fit_strengths");
    expect(pipeline?.gancho).toBeNull();
    expect(pipeline?.evaluaciones).toEqual({
      aplicaciones: 2,
      evaluadas: 1,
      enEspera: 1,
      sinEvaluar: 0,
      ilegibles: 0,
      sinIa: 0,
    });
    expect(pipeline?.aplicados.map((a) => [a.id, a.estado, a.evaluacion])).toEqual([
      [
        "a1",
        "evaluated",
        {
          score: 7.5,
          razonamiento: "Lidera equipos backend con Python.",
          fortalezas: ["Python", "FastAPI"],
          brechas: ["Celery"],
          // La sugiere la política del dominio: ≥ 7 es entrevista.
          siguientePaso: "entrevista",
        },
      ],
      ["a2", "applied", null],
    ]);
  });

  it("descartar manda el motivo y pasa la aplicación a descartada", async () => {
    const { adaptador, peticiones } = clienteDePrueba((p) =>
      p.ruta === "/rest/v1/applications" && p.metodo === "PATCH" ? { estado: 204 } : undefined,
    );
    expect(
      await adaptador.descartar("a1", "  No tiene la experiencia que pide el puesto. "),
    ).toEqual({ ok: true });
    const [patch] = peticiones;
    expect(patch?.url.searchParams.get("id")).toBe("eq.a1");
    expect(patch?.cuerpo).toEqual({
      status: "rejected",
      motivo_de_descarte: "No tiene la experiencia que pide el puesto.",
    });
  });

  it.each([
    ["PT422", "la evaluó la IA y no hay motivo"],
    ["23514", "el motivo no mide de 10 a 500"],
  ])("si la base responde %s (%s), falta el motivo", async (code) => {
    const { adaptador } = clienteDePrueba(() => ({
      estado: code === "PT422" ? 422 : 400,
      filas: { code, message: "rechazado", details: null, hint: null },
    }));
    expect(await adaptador.descartar("a1", "")).toEqual({ ok: false, motivo: "sin-motivo" });
  });

  it("arma el .zip con los CVs por orden de llegada y cuenta los que no bajaron", async () => {
    const ruta = (archivo: string) => `${EMPRESA}/${archivo}`;
    const { adaptador } = clienteDePrueba((p) => {
      if (p.ruta === "/rest/v1/vacantes") return { filas: [{ title: "Coordinador de almacén" }] };
      if (p.ruta === "/rest/v1/applications") {
        expect(p.url.searchParams.get("order")).toBe("applied_at.asc");
        return {
          filas: [
            { applied_at: "1", candidatos: { full_name: "María López", cv_url: ruta("a.pdf") } },
            { applied_at: "2", candidatos: { full_name: "Sin CV", cv_url: null } },
            { applied_at: "3", candidatos: { full_name: "José/Ruiz", cv_url: ruta("b.docx") } },
            { applied_at: "4", candidatos: { full_name: "Ana Paz", cv_url: ruta("c.pdf") } },
          ],
        };
      }
      if (p.ruta === "/storage/v1/object/sign/cvs") {
        return {
          filas: ["a.pdf", "b.docx", "c.pdf"].map((a) => ({
            path: ruta(a),
            signedURL: `/object/sign/cvs/${ruta(a)}?token=t`,
            error: null,
          })),
        };
      }
      if (p.ruta.endsWith("a.pdf")) return { texto: "%PDF-1.7 de María" };
      if (p.ruta.endsWith("b.docx")) return { texto: "PK docx de José" };
      if (p.ruta.endsWith("c.pdf")) return { estado: 400, texto: "token vencido" };
      return undefined;
    });
    let zip: Blob | undefined;
    vi.spyOn(URL, "createObjectURL").mockImplementation((blob) => {
      zip = blob as Blob;
      return "blob:zip";
    });

    const descarga = await adaptador.solicitarDescargaDeCvs(VACANTE);
    expect(descarga).toEqual({
      url: "blob:zip",
      nombre: "CVs - Coordinador de almacén.zip",
      omitidos: 1,
    });
    const contenido = new TextDecoder().decode(await leer(zip as Blob));
    expect(contenido).toContain("01 - María López.pdf");
    expect(contenido).toContain("%PDF-1.7 de María");
    expect(contenido).toContain("02 - José Ruiz.docx");
    expect(contenido).not.toContain("Ana Paz");
  });

  it("sin CVs no hay .zip", async () => {
    const { adaptador } = clienteDePrueba((p) => {
      if (p.ruta === "/rest/v1/vacantes") return { filas: [{ title: "Chofer" }] };
      if (p.ruta === "/rest/v1/applications") return { filas: [] };
      return undefined;
    });
    expect(await adaptador.solicitarDescargaDeCvs(VACANTE)).toEqual({
      url: null,
      motivo: "sin-cvs",
    });
  });

  it("el interés en la IA va a la rpc de 0013", async () => {
    const { adaptador, peticiones } = clienteDePrueba((p) =>
      p.ruta === "/rest/v1/rpc/registrar_interes_en_ia" ? { estado: 204 } : undefined,
    );
    await adaptador.registrarInteres("pipeline");
    expect(peticiones[0]?.cuerpo).toEqual({ p_origen: "pipeline" });
  });
});
