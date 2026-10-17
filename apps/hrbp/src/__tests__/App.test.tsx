import { fireEvent, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { montarPanel } from "../test/montar";

const encabezado = () => screen.findByRole("heading", { level: 1 });

describe("panel de empresa · plan gratis (ADR-017)", () => {
  it("entra a Mis vacantes con el cupo del plan y solo el módulo Career site", async () => {
    montarPanel("/");

    expect(await encabezado()).toHaveTextContent("Mis vacantes");
    expect(screen.getByText("3 de 4 vacantes activas")).toBeInTheDocument();
    expect(document.querySelectorAll("[data-vacante]")).toHaveLength(3);
    expect(screen.getByText("Datos de ejemplo")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Tu cuenta: Mariana" })).toBeInTheDocument();

    const menu = screen.getByRole("complementary", { name: "Navegación" });
    expect(within(menu).getByRole("navigation", { name: "Career site" })).toBeInTheDocument();
    expect(within(menu).queryByRole("navigation", { name: "Operación" })).toBeNull();
    expect(within(menu).getByRole("link", { name: /Mis vacantes/ })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(within(menu).getByText("Career site · gratis")).toBeInTheDocument();
  });

  it("marca la vacante que llegó a 50 aplicaciones como cupo completo", async () => {
    montarPanel("/vacantes");
    const fila = (await screen.findByText("Analista de inventarios")).closest("[data-vacante]");
    expect(within(fila as HTMLElement).getByText("Cupo completo")).toBeInTheDocument();
    expect(within(fila as HTMLElement).getByText("50 de 50 aplicaciones")).toBeInTheDocument();
  });

  it("eliminar pide confirmación y libera un cupo", async () => {
    montarPanel("/vacantes");
    const fila = (await screen.findByText("Chofer repartidor")).closest(
      "[data-vacante]",
    ) as HTMLElement;

    fireEvent.click(within(fila).getByRole("button", { name: "Eliminar" }));
    const confirmacion = within(fila).getByRole("alertdialog", {
      name: "Eliminar Chofer repartidor",
    });
    fireEvent.click(within(confirmacion).getByRole("button", { name: "Sí, eliminar" }));

    expect(await screen.findByText("2 de 4 vacantes activas")).toBeInTheDocument();
    expect(screen.queryByText("Chofer repartidor")).toBeNull();
  });

  it("crear empleo muestra la vista previa en vivo, el brochure y publica", async () => {
    montarPanel("/vacantes/nueva");

    expect(await encabezado()).toHaveTextContent("Crear empleo");
    expect(screen.getByText("Te quedan 1 de 4 vacantes")).toBeInTheDocument();
    expect(screen.getByText(/usas tu última vacante libre/)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Puesto"), { target: { value: "Supervisor de turno" } });
    fireEvent.change(screen.getByLabelText("Ubicación"), { target: { value: "Saltillo, Coah." } });
    fireEvent.change(screen.getByLabelText("Desde"), { target: { value: "18000" } });
    fireEvent.change(screen.getByLabelText("Hasta"), { target: { value: "22000" } });
    fireEvent.click(screen.getByLabelText("Presencial"));
    fireEvent.change(screen.getByLabelText(/Descripción/), {
      target: { value: "Supervisarás el turno nocturno." },
    });

    const previa = screen.getByRole("article", { name: "Vista previa de la vacante" });
    expect(within(previa).getByText("Supervisor de turno")).toBeInTheDocument();
    expect(within(previa).getByText("Andes Logística")).toBeInTheDocument();
    expect(within(previa).getByText("Presencial")).toBeInTheDocument();
    expect(within(previa).getByText(/\$18,000 – \$22,000/)).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText("Mostrar el salario en el career site"));
    expect(within(previa).getByText("Salario a convenir")).toBeInTheDocument();

    const brochure = screen.getByRole("region", { name: "Servicios de Vector HR" });
    fireEvent.click(within(brochure).getByRole("button", { name: "Quiero saber más" }));
    expect(await within(brochure).findByRole("status")).toHaveTextContent(/te escribe pronto/);

    fireEvent.click(screen.getByRole("button", { name: "Publicar en el career site" }));
    expect(
      await screen.findByRole("heading", { level: 1, name: "Supervisor de turno" }),
    ).toBeInTheDocument();
    expect(window.location.pathname).toMatch(/^\/vacantes\/supervisor-de-turno-/);
    expect(screen.getByText(/Todavía no hay aplicaciones/)).toBeInTheDocument();
  });

  it("con el cupo lleno, crear empleo explica cómo liberar uno en vez del formulario", async () => {
    montarPanel("/vacantes/nueva");
    fireEvent.change(await screen.findByLabelText("Puesto"), {
      target: { value: "Montacarguista" },
    });
    fireEvent.change(screen.getByLabelText("Ubicación"), { target: { value: "Apodaca, NL" } });
    fireEvent.change(screen.getByLabelText(/Descripción/), {
      target: { value: "Opera montacargas." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Publicar en el career site" }));
    await screen.findByRole("heading", { level: 1, name: "Montacarguista" });

    fireEvent.click(screen.getAllByRole("link", { name: /Crear empleo/ })[0] as HTMLElement);
    expect(await screen.findByText("Tus 4 vacantes están activas")).toBeInTheDocument();
    expect(screen.queryByRole("form", { name: "Datos de la vacante" })).toBeNull();

    fireEvent.click(screen.getByRole("link", { name: "Ir a Mis vacantes" }));
    expect(await screen.findByText(/Para publicar otra, elimina una/)).toBeInTheDocument();
  });

  it("el pipeline gratis solo abre Aplicados, con el gancho y la descarga masiva", async () => {
    montarPanel("/vacantes/coordinador-de-almacen");

    expect(await encabezado()).toHaveTextContent("Coordinador de almacén");
    expect(screen.getByText(/47 de 50 aplicaciones/)).toBeInTheDocument();

    const gancho = screen.getByRole("region", { name: "Resultado de la evaluación" });
    expect(gancho).toHaveTextContent("Evaluamos los 47 CVs en 38 segundos, a ciegas.");
    expect(within(gancho).getByText("13")).toBeInTheDocument();
    expect(within(gancho).getByText("6")).toBeInTheDocument();

    const etapas = screen.getByRole("region", { name: "Pipeline" });
    expect(within(etapas).getAllByText("Servicios IA")).toHaveLength(4);
    expect(etapas.querySelector('[data-etapa="applied"]')).toHaveTextContent("47");

    const aplicados = screen.getByRole("region", { name: "Aplicados" });
    expect(within(aplicados).getAllByRole("row")).toHaveLength(9);
    expect(within(aplicados).getByText("Y 39 más en el .zip.")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Descargar los 47 CVs (.zip)" }));
    expect(await screen.findByText(/se activa cuando el panel se conecte/)).toBeInTheDocument();
  });

  it("una vacante que no existe muestra cómo volver", async () => {
    montarPanel("/vacantes/no-existe");
    expect(await encabezado()).toHaveTextContent("No encontramos esta vacante");
    expect(screen.getByRole("link", { name: "Ir a Mis vacantes" })).toHaveAttribute(
      "href",
      "/vacantes",
    );
  });

  it("una ruta desconocida muestra la página no encontrada", async () => {
    montarPanel("/configuracion");
    expect(await encabezado()).toHaveTextContent("No encontramos esta página");
  });
});

describe("panel de empresa · plan con servicios de IA", () => {
  it("entra al cockpit con la decisión del día, los KPIs y el embudo con conversión", async () => {
    montarPanel("/?plan=ia");

    expect(await encabezado()).toHaveTextContent("Tu día, ya ordenado");
    expect(screen.getByRole("navigation", { name: "Operación" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Decisión del día" })).toHaveTextContent(
      "3 candidatas listas para entrevista",
    );

    for (const [etiqueta, valor] of [
      ["Candidatos en proceso", "142"],
      ["Vacantes publicadas", "8"],
      ["Evaluaciones IA (24 h)", "327"],
      ["En espera del modelo", "2"],
    ]) {
      expect(screen.getByText(etiqueta as string).parentElement).toHaveTextContent(valor as string);
    }

    const embudo = screen.getByRole("region", { name: "Pipeline" });
    expect(within(embudo).getByText("Aplicados").closest("[data-etapa]")).toHaveTextContent("84");
    expect(within(embudo).getByText("Evaluados").closest("[data-etapa]")).toHaveTextContent("49 %");

    const evaluados = screen.getByRole("region", { name: "Mejores evaluados" });
    expect(within(evaluados).getAllByText("Entrevista")).toHaveLength(2);
    expect(within(evaluados).getByText("Psicométrico")).toBeInTheDocument();
  });

  it("no muestra el brochure en crear empleo", async () => {
    montarPanel("/vacantes/nueva?plan=ia");
    expect(await encabezado()).toHaveTextContent("Crear empleo");
    expect(screen.queryByRole("region", { name: "Servicios de Vector HR" })).toBeNull();
  });

  it("su pipeline muestra todas las etapas, sin candados ni gancho", async () => {
    montarPanel("/vacantes/senior-software-engineer?plan=ia");
    await encabezado();
    expect(screen.queryByText("Servicios IA")).toBeNull();
    expect(screen.queryByRole("region", { name: "Resultado de la evaluación" })).toBeNull();
  });
});

describe("panel de empresa · accesibilidad", () => {
  it.each(["/", "/vacantes/nueva", "/vacantes/coordinador-de-almacen", "/?plan=ia"])(
    "%s tiene un solo h1 y solo el formulario tiene un submit",
    async (url) => {
      montarPanel(url);
      await encabezado();
      expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
      const submits = screen
        .queryAllByRole("button")
        .filter((b) => b.getAttribute("type") === "submit");
      expect(submits.map((b) => b.textContent)).toEqual(
        url === "/vacantes/nueva" ? ["Publicar en el career site"] : [],
      );
    },
  );
});
