import { describe, expect, it } from "vitest";

import {
  ApplicationSchema,
  ApplicationStatusSchema,
  CandidatoSchema,
  CvEvaluationSchema,
  VacanteSchema,
  VacanteStatusSchema,
} from "../hr";

const UUID_A = "3f1b0e1a-2c4d-4f5e-8a9b-0c1d2e3f4a5b";
const UUID_B = "7d2c9f84-1b6e-4a30-9c11-5f8e2a0b4c6d";
const UUID_C = "0a9b8c7d-6e5f-4a3b-a2c1-9d8e7f6a5b4c";
const NOW = "2025-01-15T10:30:00.000Z";

/** Devuelve una copia del objeto sin las claves indicadas (para probar campos ausentes). */
function sinClaves(obj: Record<string, unknown>, ...keys: string[]): Record<string, unknown> {
  return Object.fromEntries(Object.entries(obj).filter(([key]) => !keys.includes(key)));
}

function vacante(overrides: Record<string, unknown> = {}) {
  return {
    id: UUID_A,
    empresa_id: UUID_B,
    slug: "senior-software-engineer",
    title: "Senior Software Engineer",
    jd: "Liderar arquitectura de servicios Python/FastAPI.",
    icp_text: null,
    seniority: "senior",
    modality: "remote",
    location: "Remote · LATAM",
    salary_min: 4000,
    salary_max: 6500,
    currency: "USD",
    status: "open",
    created_at: NOW,
    closed_at: null,
    ...overrides,
  };
}

describe("VacanteStatusSchema", () => {
  it("acepta exactamente los cinco estados del ciclo de vida", () => {
    expect(VacanteStatusSchema.options).toEqual(["draft", "open", "paused", "closed", "filled"]);
  });

  it("rechaza un estado que no existe", () => {
    expect(VacanteStatusSchema.safeParse("archived").success).toBe(false);
  });
});

describe("VacanteSchema", () => {
  it("parsea una vacante completa y válida", () => {
    const result = VacanteSchema.safeParse(vacante());
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.slug).toBe("senior-software-engineer");
      expect(result.data.status).toBe("open");
      expect(result.data.salary_max).toBe(6500);
    }
  });

  it("aplica el default USD cuando falta currency", () => {
    const parsed = VacanteSchema.parse(sinClaves(vacante(), "currency"));
    expect(parsed.currency).toBe("USD");
  });

  it("rechaza currency que no sea código ISO de 3 letras", () => {
    expect(VacanteSchema.safeParse(vacante({ currency: "DOLARES" })).success).toBe(false);
    expect(VacanteSchema.safeParse(vacante({ currency: "US" })).success).toBe(false);
    expect(VacanteSchema.safeParse(vacante({ currency: "MXN" })).success).toBe(true);
  });

  it("rechaza ids que no sean uuid", () => {
    const result = VacanteSchema.safeParse(vacante({ id: "vacante-1" }));
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0]?.path).toEqual(["id"]);
      expect(result.error.issues[0]?.message).toMatch(/uuid/i);
    }
  });

  it("rechaza salarios negativos", () => {
    expect(VacanteSchema.safeParse(vacante({ salary_min: -1 })).success).toBe(false);
  });

  it("acepta null en los campos nullable pero no undefined", () => {
    expect(
      VacanteSchema.safeParse(vacante({ icp_text: null, seniority: null, location: null })).success,
    ).toBe(true);
    expect(VacanteSchema.safeParse(vacante({ location: undefined })).success).toBe(false);
  });

  it("rechaza modality fuera del enum onsite/hybrid/remote", () => {
    expect(VacanteSchema.safeParse(vacante({ modality: "presencial" })).success).toBe(false);
  });

  it("rechaza title y jd vacíos", () => {
    expect(VacanteSchema.safeParse(vacante({ title: "" })).success).toBe(false);
    expect(VacanteSchema.safeParse(vacante({ jd: "" })).success).toBe(false);
  });

  it("exige created_at como ISO-8601 con zona horaria — no coerciona Date ni fechas sueltas", () => {
    expect(VacanteSchema.safeParse(vacante({ created_at: "2025-01-15" })).success).toBe(false);
    expect(VacanteSchema.safeParse(vacante({ created_at: "2025-01-15T10:30:00" })).success).toBe(
      false,
    );
    expect(VacanteSchema.safeParse(vacante({ created_at: new Date(NOW) })).success).toBe(false);
    expect(VacanteSchema.safeParse(vacante({ created_at: "2025-01-15T10:30:00Z" })).success).toBe(
      true,
    );
  });

  it("acumula un issue por cada campo inválido", () => {
    const result = VacanteSchema.safeParse(
      vacante({ id: "nope", status: "archived", currency: "X" }),
    );
    expect(result.success).toBe(false);
    if (!result.success) {
      const paths = result.error.issues.map((i) => i.path.join("."));
      expect(paths).toEqual(expect.arrayContaining(["id", "status", "currency"]));
    }
  });
});

describe("CandidatoSchema", () => {
  const base = {
    id: UUID_A,
    empresa_id: UUID_B,
    full_name: "Ana Pérez",
    email: "ana@example.com",
    phone: null,
    cv_url: "https://cdn.example.com/cv/ana.pdf",
    linkedin_url: null,
    headline: null,
    summary: null,
    source: "career-site",
    created_at: NOW,
  };

  it("parsea un candidato válido", () => {
    expect(CandidatoSchema.safeParse(base).success).toBe(true);
  });

  it("rechaza email con formato inválido pero acepta null", () => {
    expect(CandidatoSchema.safeParse({ ...base, email: "ana(at)example.com" }).success).toBe(false);
    expect(CandidatoSchema.safeParse({ ...base, email: null }).success).toBe(true);
  });

  it("rechaza cv_url que no sea URL absoluta", () => {
    expect(CandidatoSchema.safeParse({ ...base, cv_url: "/uploads/ana.pdf" }).success).toBe(false);
  });

  it("rechaza un source fuera del enum de canales soportados", () => {
    expect(CandidatoSchema.safeParse({ ...base, source: "indeed" }).success).toBe(false);
    expect(CandidatoSchema.safeParse({ ...base, source: "referral" }).success).toBe(true);
  });

  it("exige full_name no vacío", () => {
    expect(CandidatoSchema.safeParse({ ...base, full_name: "" }).success).toBe(false);
  });
});

describe("ApplicationSchema", () => {
  const base = {
    id: UUID_A,
    empresa_id: UUID_B,
    vacante_id: UUID_C,
    candidato_id: UUID_A,
    status: "applied",
    fit_score: 7.5,
    fit_rationale: null,
    applied_at: NOW,
    decided_at: null,
  };

  it("aplica default [] a fit_gaps cuando no viene", () => {
    const parsed = ApplicationSchema.parse(base);
    expect(parsed.fit_gaps).toEqual([]);
  });

  it("acota fit_score al rango 0-10 y permite null", () => {
    expect(ApplicationSchema.safeParse({ ...base, fit_score: 0 }).success).toBe(true);
    expect(ApplicationSchema.safeParse({ ...base, fit_score: 10 }).success).toBe(true);
    expect(ApplicationSchema.safeParse({ ...base, fit_score: 10.1 }).success).toBe(false);
    expect(ApplicationSchema.safeParse({ ...base, fit_score: -0.5 }).success).toBe(false);
    expect(ApplicationSchema.safeParse({ ...base, fit_score: null }).success).toBe(true);
  });

  it("rechaza fit_gaps que no sea array de strings", () => {
    expect(ApplicationSchema.safeParse({ ...base, fit_gaps: "sin Kubernetes" }).success).toBe(
      false,
    );
    expect(ApplicationSchema.safeParse({ ...base, fit_gaps: [1, 2] }).success).toBe(false);
  });

  it("cubre todos los estados del pipeline", () => {
    expect(ApplicationStatusSchema.options).toEqual([
      "applied",
      "evaluated",
      "shortlisted",
      "interviewed",
      "offered",
      "hired",
      "rejected",
      "withdrawn",
    ]);
    for (const status of ApplicationStatusSchema.options) {
      expect(ApplicationSchema.safeParse({ ...base, status }).success).toBe(true);
    }
    expect(ApplicationSchema.safeParse({ ...base, status: "onboarding" }).success).toBe(false);
  });
});

describe("CvEvaluationSchema", () => {
  const base = {
    candidate_id: UUID_A,
    vacante_id: UUID_B,
    score: 8,
    rationale: "Match fuerte en FastAPI y multi-tenant.",
    gaps: ["sin experiencia en Kubernetes"],
    strengths: ["async SQLAlchemy", "observabilidad"],
    recommended_next_step: "entrevista",
  };

  it("parsea la salida esperada del skill cv-evaluator", () => {
    const parsed = CvEvaluationSchema.parse(base);
    expect(parsed.score).toBe(8);
    expect(parsed.recommended_next_step).toBe("entrevista");
  });

  it("exige rationale no vacío", () => {
    expect(CvEvaluationSchema.safeParse({ ...base, rationale: "" }).success).toBe(false);
  });

  it("restringe recommended_next_step al enum del SKILL.md", () => {
    for (const step of ["psicometrico", "entrevista", "rechazar"]) {
      expect(CvEvaluationSchema.safeParse({ ...base, recommended_next_step: step }).success).toBe(
        true,
      );
    }
    expect(CvEvaluationSchema.safeParse({ ...base, recommended_next_step: "hire" }).success).toBe(
      false,
    );
  });

  it("no admite gaps/strengths ausentes — el output del LLM debe ser explícito", () => {
    expect(CvEvaluationSchema.safeParse(sinClaves(base, "gaps")).success).toBe(false);
    expect(CvEvaluationSchema.safeParse(sinClaves(base, "strengths")).success).toBe(false);
  });

  it("rechaza score fuera de 0-10", () => {
    expect(CvEvaluationSchema.safeParse({ ...base, score: 11 }).success).toBe(false);
    expect(CvEvaluationSchema.safeParse({ ...base, score: -1 }).success).toBe(false);
  });
});
