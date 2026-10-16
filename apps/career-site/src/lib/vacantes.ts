/**
 * Acceso a las vacantes públicas del career-site.
 *
 * Las páginas solo llaman a estas funciones: no saben de dónde salen los datos
 * ni qué hace pública a una vacante. Esa regla (`status = 'open'`, sin
 * `empresa_id`) es de la vista `vacantes_publicas` en Supabase.
 *
 * Hasta que el career-site lea Supabase, los datos salen de `VACANTES_DE_EJEMPLO`,
 * con la misma forma que una fila de la vista. Cambiar a la consulta real toca
 * solo este fichero.
 */
import { type VacantePublica, VacantePublicaSchema } from "@vortex/types/hr";

const VACANTES_DE_EJEMPLO: VacantePublica[] = VacantePublicaSchema.array().parse([
  {
    id: "00000000-0000-4000-8000-0000000000a1",
    slug: "senior-software-engineer",
    title: "Senior Software Engineer",
    jd: "Liderarás el diseño e implementación de servicios Python/FastAPI multi-tenant. Trabajarás en pair con Claude/Cursor en código que se despliega varias veces al día. Stack: FastAPI, SQLAlchemy 2 async, Celery, Supabase, OpenTelemetry.",
    seniority: "senior",
    modality: "remote",
    location: "LATAM",
    created_at: "2026-10-01T15:00:00Z",
  },
  {
    id: "00000000-0000-4000-8000-0000000000a2",
    slug: "hr-business-partner",
    title: "HR Business Partner",
    jd: "Serás el puente entre los líderes técnicos y el ciclo de talento. Operarás Vortex Ops como producto interno, definiendo ICPs, validando a los candidatos que preseleccionan los agentes y cerrando contrataciones.",
    seniority: "semi-senior",
    modality: "hybrid",
    location: "CDMX",
    created_at: "2026-10-03T15:00:00Z",
  },
]);

/** Vacantes abiertas, de la más reciente a la más antigua. */
export async function listarVacantes(): Promise<VacantePublica[]> {
  return [...VACANTES_DE_EJEMPLO].sort((a, b) => b.created_at.localeCompare(a.created_at));
}

/** La vacante abierta con ese slug (exacto, sensible a mayúsculas), o `null`. */
export async function obtenerVacante(slug: string): Promise<VacantePublica | null> {
  return VACANTES_DE_EJEMPLO.find((v) => v.slug === slug) ?? null;
}
