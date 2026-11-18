/**
 * El área de admin (`/admin`; ADR-022, enmienda del 2026-11-17) contra un `fetch` falso:
 * el hr-engine (`/admin/*`) y las métricas de la web contestan como lo harían. Quién es
 * admin lo prueba el hr-engine (tests/unit/test_api_admin.py); aquí, que el panel pinte
 * lo que le dicen y mande lo que debe.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { URL_DE_METRICAS_WEB } from "../datos/admin";
import { navegar } from "../navegacion/ruta";
import { Admin } from "../pantallas/admin";
import { montarPanel } from "../test/montar";

// La sesión del panel, sin Supabase: cada test decide si hay token.
const panel = vi.hoisted(() => ({ tokenDeAcceso: vi.fn() }));
vi.mock("../datos/panel", async (original) => ({
  ...(await original<typeof import("../datos/panel")>()),
  ES_DE_EJEMPLO: false,
  ...panel,
}));

type Respuesta = { estado?: number; json?: unknown; texto?: string };

interface Pedido {
  metodo: string;
  url: string;
  cuerpo: unknown;
  autorizacion: string | null;
}

let respuestas: Record<string, Respuesta>;
let pedidos: Pedido[];

const fetchFalso = vi.fn(async (entrada: RequestInfo | URL, init: RequestInit = {}) => {
  const url = String(entrada);
  const metodo = init.method ?? "GET";
  pedidos.push({
    metodo,
    url,
    cuerpo: init.body ? JSON.parse(String(init.body)) : null,
    autorizacion: new Headers(init.headers).get("Authorization"),
  });
  const r = respuestas[`${metodo} ${url}`];
  if (!r) return new Response("no existe", { status: 404 });
  return new Response(r.texto ?? JSON.stringify(r.json ?? {}), {
    status: r.estado ?? 200,
    headers: { "Content-Type": "application/json" },
  });
});

const RESUMEN = {
  empresas: { total: 12, altas_web_confirmadas: 7, verificadas: 4 },
  vacantes: {
    por_moderacion: { pendiente: 1, en_revision: 2, publicada: 9, rechazada: 1, oculta: 1 },
    abiertas: 14,
    cerradas: 5,
  },
  aplicaciones: { total: 80, ultimos_7_dias: 21 },
  altas: { ultimos_7_dias: 3 },
};

const WEB = {
  registros: {
    total: 40,
    ultimos7: 6,
    altaFallida: 2,
    porCampana: [{ origen: "linkedin", medio: "paid", campana: "lanzamiento", n: 9 }],
  },
  diagnosticos: { total: 15, ultimos7: 4 },
  listaEspera: { total: 8, ultimos7: 1 },
};

const VACANTE = "0b9c8d7e-6f5a-4b3c-8d2e-1f0a9b8c7d6e";

const EN_COLA = {
  id: VACANTE,
  titulo: "Promotor de ventas",
  empresa: "Andes & Cía",
  publica_para: "clientes",
  empresa_verificada: false,
  web: "https://andes.mx",
  // La base solo guarda https (0019); si algo raro llega, no se vuelve enlace.
  linkedin: "javascript:alert(1)",
  estado: "en_revision",
  motivos: [
    {
      regla: "contacto_externo",
      senal: "Manda a WhatsApp",
      gravedad: "media",
      cita: "WhatsApp",
      corregir: "Deja que apliquen en la bolsa de empleo.",
    },
  ],
  descripcion: "Escríbenos por WhatsApp al 55 1234 5678.",
  creada_en: "2026-11-16T14:30:00Z",
};

const OTRA = {
  ...EN_COLA,
  id: "6f1c2a9e-3b7d-4c8a-9e1f-2a3b4c5d6e7f",
  titulo: "Analista de inventarios",
  empresa: "Distribuidora Norte",
  publica_para: "propia",
  empresa_verificada: true,
  linkedin: null,
  estado: "oculta",
  motivos: [],
};

const APROBAR = `POST /admin/vacantes/${VACANTE}/aprobar`;
const RECHAZAR = `POST /admin/vacantes/${VACANTE}/rechazar`;

function comoAdmin(extra: Record<string, Respuesta> = {}) {
  respuestas = {
    "GET /admin/yo": { json: { correo: "hola@vectorhrtech.com" } },
    "GET /admin/resumen": { json: RESUMEN },
    "GET /admin/cola": { json: { vacantes: [EN_COLA, OTRA] } },
    [`GET ${URL_DE_METRICAS_WEB}`]: { json: WEB },
    ...extra,
  };
}

function montar() {
  const cliente = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={cliente}>
      <Admin />
    </QueryClientProvider>,
  );
}

const pedidosA = (clave: string) => pedidos.filter((p) => `${p.metodo} ${p.url}` === clave);

/** La tarjeta de una cifra: la etiqueta, el número y el detalle. */
const cifra = (region: HTMLElement, etiqueta: string) =>
  within(region).getByText(etiqueta).parentElement as HTMLElement;

const tarjeta = (titulo: string) => screen.getByRole("article", { name: titulo });

beforeEach(() => {
  pedidos = [];
  respuestas = {};
  panel.tokenDeAcceso.mockReset().mockResolvedValue("token-de-prueba");
  fetchFalso.mockClear();
  vi.stubGlobal("fetch", fetchFalso);
  window.history.replaceState(null, "", "/admin");
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("quién entra", () => {
  it("con 403 dice que no tiene acceso y no pide nada más", async () => {
    respuestas = {
      "GET /admin/yo": { estado: 403, json: { detail: "esta cuenta no es de admin" } },
    };
    montar();
    await screen.findByRole("heading", { level: 1, name: "No tienes acceso" });
    expect(pedidos.map((p) => p.url)).toEqual(["/admin/yo"]);
    expect(pedidos[0]?.autorizacion).toBe("Bearer token-de-prueba");
  });

  it("con 401 pide volver a entrar", async () => {
    respuestas = { "GET /admin/yo": { estado: 401, json: {} } };
    montar();
    await screen.findByRole("heading", { level: 1, name: "Tu sesión venció" });
  });

  it("sin sesión no llama al hr-engine", async () => {
    panel.tokenDeAcceso.mockResolvedValue(null);
    montar();
    await screen.findByRole("heading", { level: 1, name: "Tu sesión venció" });
    expect(pedidos).toEqual([]);
  });

  it("un 200 que no es el JSON del hr-engine no da acceso", async () => {
    // Por ejemplo, la SPA del panel contestando en vez del hr-engine.
    respuestas = { "GET /admin/yo": { texto: "<!doctype html><html></html>" } };
    montar();
    await screen.findByRole("heading", { level: 1, name: "No pudimos revisar tu acceso" });
    expect(screen.getByRole("button", { name: "Reintentar" })).toBeInTheDocument();
  });
});

describe("el tablero", () => {
  it("pinta las métricas del panel y de la web, con la sesión como Bearer", async () => {
    comoAdmin();
    montar();
    await screen.findByRole("heading", { level: 1, name: "La plataforma hoy" });
    const delPanel = await screen.findByRole("region", { name: "Panel" });
    await within(delPanel).findByText("Empresas");
    expect(cifra(delPanel, "Empresas")).toHaveTextContent("124 verificadas");
    expect(cifra(delPanel, "Altas web confirmadas")).toHaveTextContent("73 altas en 7 días");
    expect(cifra(delPanel, "Vacantes abiertas")).toHaveTextContent("145 cerradas");
    // En revisión más ocultas por reportes.
    expect(cifra(delPanel, "Por revisar")).toHaveTextContent("31 ocultas por reportes");
    expect(cifra(delPanel, "Aplicaciones")).toHaveTextContent("8021 en 7 días");
    expect(within(delPanel).getByRole("row", { name: "Publicada 9" })).toBeInTheDocument();

    const deLaWeb = screen.getByRole("region", { name: "Web" });
    await within(deLaWeb).findByText("Registros");
    expect(cifra(deLaWeb, "Registros")).toHaveTextContent("406 en 7 días");
    expect(cifra(deLaWeb, "Alta fallida")).toHaveTextContent("2");
    expect(cifra(deLaWeb, "Diagnósticos")).toHaveTextContent("154 en 7 días");
    expect(cifra(deLaWeb, "Lista de espera")).toHaveTextContent("81 en 7 días");
    expect(within(deLaWeb).getByRole("row", { name: "linkedin paid lanzamiento 9" })).toBeVisible();

    expect(pedidos.length).toBeGreaterThanOrEqual(4);
    for (const p of pedidos) expect(p.autorizacion).toBe("Bearer token-de-prueba");
    expect(pedidosA(`GET ${URL_DE_METRICAS_WEB}`)).toHaveLength(1);
  });

  it("si la web falla, quedan las métricas del panel con una nota", async () => {
    comoAdmin({ [`GET ${URL_DE_METRICAS_WEB}`]: { estado: 500, json: {} } });
    montar();
    await screen.findByText(/No pudimos leer las métricas de la web/);
    const delPanel = screen.getByRole("region", { name: "Panel" });
    await within(delPanel).findByText("Empresas");
    expect(cifra(delPanel, "Empresas")).toHaveTextContent("12");
  });
});

describe("la cola de revisión", () => {
  it("cada tarjeta trae insignias, motivos, enlaces seguros y la descripción plegada", async () => {
    comoAdmin();
    montar();
    await screen.findByRole("heading", { level: 2, name: "Cola de revisión (2)" });

    const promotor = tarjeta("Promotor de ventas");
    expect(promotor).toHaveTextContent("Andes & Cía");
    expect(within(promotor).getByText("En revisión")).toBeInTheDocument();
    expect(within(promotor).getByText("Reclutador(a) independiente")).toBeInTheDocument();
    expect(within(promotor).getByRole("link", { name: "Web" })).toHaveAttribute(
      "href",
      "https://andes.mx",
    );
    expect(within(promotor).queryByRole("link", { name: "LinkedIn" })).toBeNull();
    expect(promotor).toHaveTextContent("Manda a WhatsApp «WhatsApp»");
    expect(promotor).toHaveTextContent("Qué corregir: Deja que apliquen en la bolsa de empleo.");
    expect(within(promotor).getByText("Sospechosa")).toBeInTheDocument();
    const descripcion = promotor.querySelector("details");
    expect(descripcion).not.toHaveAttribute("open");
    expect(descripcion).toHaveTextContent("Escríbenos por WhatsApp al 55 1234 5678.");

    const analista = tarjeta("Analista de inventarios");
    expect(within(analista).getByText("Oculta por reportes")).toBeInTheDocument();
    expect(within(analista).getByText("Empresa verificada")).toBeInTheDocument();
  });

  it("aprobar la quita de la lista, avisa y vuelve a pedir los conteos", async () => {
    comoAdmin({ [APROBAR]: { json: { estado: "publicada" } } });
    montar();
    await screen.findByRole("article", { name: "Promotor de ventas" });
    await waitFor(() => expect(pedidosA("GET /admin/resumen")).toHaveLength(1));

    fireEvent.click(within(tarjeta("Promotor de ventas")).getByRole("button", { name: "Aprobar" }));

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Aprobaste «Promotor de ventas»: ya está en la bolsa de empleo.",
    );
    expect(screen.queryByRole("article", { name: "Promotor de ventas" })).toBeNull();
    expect(screen.getByRole("article", { name: "Analista de inventarios" })).toBeInTheDocument();
    expect(pedidosA(APROBAR)).toHaveLength(1);
    expect(pedidosA(APROBAR)[0]?.autorizacion).toBe("Bearer token-de-prueba");
    await waitFor(() => expect(pedidosA("GET /admin/resumen")).toHaveLength(2));
    // La cola no se volvió a pedir: la tarjeta salió sola.
    expect(pedidosA("GET /admin/cola")).toHaveLength(1);
  });

  it("rechazar pide un motivo y lo manda", async () => {
    comoAdmin({ [RECHAZAR]: { json: { estado: "rechazada" } } });
    montar();
    await screen.findByRole("article", { name: "Promotor de ventas" });

    fireEvent.click(
      within(tarjeta("Promotor de ventas")).getByRole("button", { name: "Rechazar" }),
    );
    const formulario = screen.getByRole("form", { name: "Rechazar Promotor de ventas" });
    const motivo = within(formulario).getByLabelText(
      "Motivo del rechazo (la empresa lo ve en su panel)",
    );
    const enviar = within(formulario).getByRole("button", { name: "Rechazar vacante" });
    expect(motivo).toBeRequired();
    expect(enviar).toBeDisabled();
    fireEvent.change(motivo, { target: { value: "   " } });
    expect(enviar).toBeDisabled();
    fireEvent.change(motivo, { target: { value: " Pide un depósito para el kit " } });
    fireEvent.click(enviar);

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Rechazaste «Promotor de ventas»: la empresa ve el motivo en su panel.",
    );
    expect(pedidosA(RECHAZAR).map((p) => p.cuerpo)).toEqual([
      { motivo: "Pide un depósito para el kit" },
    ]);
    expect(screen.queryByRole("article", { name: "Promotor de ventas" })).toBeNull();
  });

  it("con 409 avisa en qué estado quedó y la quita", async () => {
    comoAdmin({
      [APROBAR]: {
        estado: 409,
        json: {
          error: "http_error",
          detail: { mensaje: "no se cambió nada", estado: "publicada" },
        },
      },
    });
    montar();
    await screen.findByRole("article", { name: "Promotor de ventas" });
    fireEvent.click(within(tarjeta("Promotor de ventas")).getByRole("button", { name: "Aprobar" }));
    expect(await screen.findByRole("status")).toHaveTextContent(
      "«Promotor de ventas» ya no estaba en la cola: está en «Publicada».",
    );
    expect(screen.queryByRole("article", { name: "Promotor de ventas" })).toBeNull();
  });

  it.each([
    [401, "Tu sesión venció. Sal y vuelve a entrar."],
    [403, "Tu cuenta ya no tiene acceso de admin."],
    [500, "No se pudo guardar. Inténtalo de nuevo."],
  ])("con %i al decidir, la tarjeta se queda y dice por qué", async (estado, mensaje) => {
    comoAdmin({ [APROBAR]: { estado, json: {} } });
    montar();
    await screen.findByRole("article", { name: "Promotor de ventas" });
    fireEvent.click(within(tarjeta("Promotor de ventas")).getByRole("button", { name: "Aprobar" }));
    expect(await within(tarjeta("Promotor de ventas")).findByRole("alert")).toHaveTextContent(
      mensaje,
    );
  });

  it("sin nada en la cola lo dice", async () => {
    comoAdmin({ "GET /admin/cola": { json: { vacantes: [] } } });
    montar();
    expect(await screen.findByText("No hay vacantes esperando revisión.")).toBeInTheDocument();
  });
});

describe("dentro del panel", () => {
  it("el enlace «Admin» del menú sale solo si /admin/yo responde 200", async () => {
    comoAdmin();
    montarPanel("/vacantes");
    const enlaces = await screen.findAllByRole("link", { name: "Admin" });
    for (const enlace of enlaces) expect(enlace).toHaveAttribute("href", "/admin");
  });

  it("con 403 no hay enlace «Admin»", async () => {
    respuestas = { "GET /admin/yo": { estado: 403, json: {} } };
    montarPanel("/vacantes");
    await screen.findByRole("heading", { level: 1 });
    await waitFor(() => expect(pedidosA("GET /admin/yo")).toHaveLength(1));
    await act(async () => {});
    expect(screen.queryByRole("link", { name: "Admin" })).toBeNull();
  });

  it("/admin pinta el admin con su propio manifiesto, y el panel vuelve al suyo", async () => {
    const manifiesto = document.createElement("link");
    manifiesto.rel = "manifest";
    manifiesto.href = "/manifest.webmanifest";
    const icono = document.createElement("link");
    icono.rel = "apple-touch-icon";
    icono.href = "/iconos/panel-apple-touch-icon.png";
    const titulo = document.createElement("meta");
    titulo.name = "apple-mobile-web-app-title";
    titulo.content = "Vector HR";
    document.head.append(manifiesto, icono, titulo);
    try {
      comoAdmin();
      montarPanel("/admin");
      await screen.findByRole("heading", { level: 1, name: "La plataforma hoy" });
      expect(manifiesto.getAttribute("href")).toBe("/admin.webmanifest");
      expect(icono.getAttribute("href")).toBe("/iconos/admin-apple-touch-icon.png");
      expect(titulo.content).toBe("VHR Admin");
      expect(document.title).toBe("Admin · Vector HR Tech");

      act(() => navegar("/vacantes"));
      await screen.findByRole("heading", { level: 1, name: "Mis vacantes" });
      expect(manifiesto.getAttribute("href")).toBe("/manifest.webmanifest");
      expect(icono.getAttribute("href")).toBe("/iconos/panel-apple-touch-icon.png");
      expect(titulo.content).toBe("Vector HR");
    } finally {
      manifiesto.remove();
      icono.remove();
      titulo.remove();
    }
  });
});
