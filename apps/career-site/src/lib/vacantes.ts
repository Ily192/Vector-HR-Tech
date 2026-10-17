/**
 * Acceso a las vacantes públicas del career-site.
 *
 * Las páginas solo llaman a estas funciones: no saben de dónde salen los datos
 * ni qué hace pública a una vacante. Esa regla (`status = 'open'`, sin
 * `empresa_id`, salario solo si la empresa lo publica) es de la vista
 * `vacantes_publicas` en Supabase (migraciones 0004 y 0007).
 *
 * Hasta que el career-site lea Supabase, los datos salen de `VACANTES_DE_EJEMPLO`,
 * con la misma forma que una fila de la vista, y los filtros se aplican en memoria.
 * Con Supabase serán la consulta (`ilike`, `eq`) y cambiará solo este fichero.
 *
 * Es la Data Access Layer que recomienda Next.js (guía "Data Security"): solo
 * corre en el servidor y devuelve DTOs con lo mínimo que la página pinta.
 */
import "server-only";

import { type VacantePublica, VacantePublicaSchema } from "@vortex/types/hr";
import { cache } from "react";

import type { FiltrosVacantes } from "./filtros";

const VACANTES_DE_EJEMPLO: VacantePublica[] = VacantePublicaSchema.array().parse([
  {
    id: "00000000-0000-4000-8000-0000000000a1",
    slug: "senior-software-engineer",
    title: "Senior Software Engineer",
    jd: "Liderarás el diseño e implementación de servicios Python/FastAPI multi-tenant. Trabajarás en pair con Claude/Cursor en código que se despliega varias veces al día. Stack: FastAPI, SQLAlchemy 2 async, Celery, Supabase, OpenTelemetry.",
    seniority: "senior",
    modality: "remote",
    location: "LATAM",
    created_at: "2026-10-14T15:00:00Z",
    empresa_nombre: "Grupo Cobalto",
    empresa_slug: "grupo-cobalto",
    salario_min: 3800,
    salario_max: 4600,
    moneda: "USD",
  },
  {
    id: "00000000-0000-4000-8000-0000000000a2",
    slug: "coordinador-de-almacen",
    title: "Coordinador de almacén",
    jd: "Coordinarás la recepción, el inventario y los envíos de un almacén de 40 personas. Reportas a la Gerencia de Operaciones.",
    seniority: "semi-senior",
    modality: "hybrid",
    location: "Monterrey, NL",
    created_at: "2026-10-16T13:00:00Z",
    empresa_nombre: "Andes Logística",
    empresa_slug: "andes-logistica",
    salario_min: 22000,
    salario_max: 28000,
    moneda: "MXN",
  },
  {
    id: "00000000-0000-4000-8000-0000000000a3",
    slug: "hr-business-partner",
    title: "HR Business Partner",
    jd: "Serás el puente entre los líderes técnicos y el ciclo de talento. Operarás Vortex Ops como producto interno, definiendo ICPs, validando a los candidatos que preseleccionan los agentes y cerrando contrataciones.",
    seniority: "semi-senior",
    modality: "hybrid",
    location: "CDMX",
    created_at: "2026-10-11T15:00:00Z",
    empresa_nombre: "Nébula Fintech",
    empresa_slug: "nebula-fintech",
    salario_min: null,
    salario_max: null,
    moneda: null,
  },
  {
    id: "00000000-0000-4000-8000-0000000000a4",
    slug: "ejecutiva-de-ventas-b2b",
    title: "Ejecutiva de ventas B2B",
    jd: "Abrirás cuentas de distribuidores en el occidente del país y darás seguimiento a la cartera actual.",
    seniority: "junior",
    modality: "onsite",
    location: "Guadalajara, Jal.",
    created_at: "2026-10-09T15:00:00Z",
    empresa_nombre: "Verde Mar Alimentos",
    empresa_slug: "verde-mar-alimentos",
    salario_min: 15000,
    salario_max: 18000,
    moneda: "MXN",
  },
  {
    id: "00000000-0000-4000-8000-0000000000a5",
    slug: "data-analyst",
    title: "Data Analyst",
    jd: "Construirás los tableros de operación y los modelos de demanda con SQL y Python.",
    seniority: "semi-senior",
    modality: "remote",
    location: "Bogotá",
    created_at: "2026-10-08T15:00:00Z",
    empresa_nombre: "Grupo Cobalto",
    empresa_slug: "grupo-cobalto",
    salario_min: 9500000,
    salario_max: 12000000,
    moneda: "COP",
  },
]);

const normalizar = (texto: string) =>
  texto
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase();

/** Vacantes abiertas que cumplen los filtros, de la más reciente a la más antigua. */
export async function listarVacantes(filtros: FiltrosVacantes = {}): Promise<VacantePublica[]> {
  const q = filtros.q ? normalizar(filtros.q) : null;
  const ubicacion = filtros.ubicacion ? normalizar(filtros.ubicacion) : null;
  return VACANTES_DE_EJEMPLO.filter(
    (v) =>
      (!q || normalizar(`${v.title} ${v.empresa_nombre} ${v.jd}`).includes(q)) &&
      (!ubicacion || normalizar(v.location ?? "").includes(ubicacion)) &&
      (!filtros.modalidad || v.modality === filtros.modalidad) &&
      (!filtros.conSalario || v.salario_min !== null),
  ).sort((a, b) => b.created_at.localeCompare(a.created_at));
}

/**
 * La vacante abierta con ese slug (exacto, sensible a mayúsculas), o `null`.
 * Con `cache`, la página y sus metadatos comparten la misma lectura por request.
 */
export const obtenerVacante = cache(async (slug: string): Promise<VacantePublica | null> => {
  return VACANTES_DE_EJEMPLO.find((v) => v.slug === slug) ?? null;
});
