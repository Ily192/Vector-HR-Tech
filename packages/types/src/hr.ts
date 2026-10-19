import { z } from "zod";

export const VacanteStatusSchema = z.enum(["draft", "open", "paused", "closed", "filled"]);
export type VacanteStatus = z.infer<typeof VacanteStatusSchema>;

export const SenioritySchema = z.enum([
  "junior",
  "semi-senior",
  "senior",
  "lead",
  "manager",
  "director",
]);
export type Seniority = z.infer<typeof SenioritySchema>;

export const ModalitySchema = z.enum(["onsite", "hybrid", "remote"]);
export type Modality = z.infer<typeof ModalitySchema>;

export const VacanteSchema = z.object({
  id: z.string().uuid(),
  empresa_id: z.string().uuid(),
  slug: z.string().min(1),
  title: z.string().min(1),
  jd: z.string().min(1),
  icp_text: z.string().nullable(),
  seniority: SenioritySchema.nullable(),
  modality: ModalitySchema,
  location: z.string().nullable(),
  salary_min: z.number().nonnegative().nullable(),
  salary_max: z.number().nonnegative().nullable(),
  currency: z.string().length(3).default("USD"),
  status: VacanteStatusSchema,
  /** Si el salario se muestra en el career site (0007). */
  salario_publico: z.boolean().default(false),
  created_at: z.string().datetime(),
  closed_at: z.string().datetime().nullable(),
  /** Borrado lógico al eliminarla desde el panel (0008). */
  deleted_at: z.string().datetime().nullable().default(null),
  /** La empresa pide la preselección a ciegas con IA (0009, ADR-018). */
  preseleccion_ia: z.boolean().default(true),
});
export type Vacante = z.infer<typeof VacanteSchema>;

/**
 * Fila de la vista `vacantes_publicas` (infra/supabase/migrations/0004 y 0007), lo
 * único que el career-site puede leer. La vista ya filtra `status = 'open'`, no
 * expone `empresa_id` y solo trae salario si la empresa lo marcó como público
 * (`salario_publico`): el career-site no decide qué es público. `cupo_completo`
 * (0008) dice si la vacante llegó al tope de aplicaciones de su plan.
 */
export const VacantePublicaSchema = VacanteSchema.pick({
  id: true,
  slug: true,
  title: true,
  jd: true,
  seniority: true,
  modality: true,
  location: true,
  created_at: true,
}).extend({
  empresa_nombre: z.string().min(1),
  empresa_slug: z.string().min(1),
  salario_min: z.number().nonnegative().nullable(),
  salario_max: z.number().nonnegative().nullable(),
  moneda: z.string().length(3).nullable(),
  cupo_completo: z.boolean(),
});
export type VacantePublica = z.infer<typeof VacantePublicaSchema>;

export const CandidatoSchema = z.object({
  id: z.string().uuid(),
  empresa_id: z.string().uuid(),
  full_name: z.string().min(1),
  email: z.string().email().nullable(),
  phone: z.string().nullable(),
  cv_url: z.string().url().nullable(),
  linkedin_url: z.string().url().nullable(),
  headline: z.string().nullable(),
  summary: z.string().nullable(),
  source: z.enum(["career-site", "linkedin", "bumeran", "computrabajo", "referral", "manual"]),
  created_at: z.string().datetime(),
});
export type Candidato = z.infer<typeof CandidatoSchema>;

export const ApplicationStatusSchema = z.enum([
  "applied",
  "evaluated",
  "shortlisted",
  "interviewed",
  "offered",
  "hired",
  "rejected",
  "withdrawn",
]);
export type ApplicationStatus = z.infer<typeof ApplicationStatusSchema>;

export const ApplicationSchema = z.object({
  id: z.string().uuid(),
  empresa_id: z.string().uuid(),
  vacante_id: z.string().uuid(),
  candidato_id: z.string().uuid(),
  status: ApplicationStatusSchema,
  fit_score: z.number().min(0).max(10).nullable(),
  fit_rationale: z.string().nullable(),
  fit_gaps: z.array(z.string()).default([]),
  applied_at: z.string().datetime(),
  decided_at: z.string().datetime().nullable(),
  /** El candidato se opuso a la evaluación con IA (0009, ADR-018). */
  sin_ia: z.boolean().default(false),
});
export type Application = z.infer<typeof ApplicationSchema>;

/**
 * Salida del skill `cv-evaluator`. Su espejo en Pydantic es
 * `services/hr-engine/app/clients/scoring.py::CvEvaluation`; los dos se prueban
 * contra `contracts/cv-evaluation.json`.
 */
export const CvEvaluationSchema = z.object({
  candidato_id: z.string().uuid(),
  vacante_id: z.string().uuid(),
  score: z.number().min(0).max(10),
  rationale: z.string().min(10),
  gaps: z.array(z.string()),
  strengths: z.array(z.string()),
  recommended_next_step: z.enum(["psicometrico", "entrevista", "rechazar"]),
});
export type SiguientePaso = CvEvaluation["recommended_next_step"];
export type CvEvaluation = z.infer<typeof CvEvaluationSchema>;
