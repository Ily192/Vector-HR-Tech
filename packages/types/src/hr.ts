import { z } from "zod";

export const VacanteStatusSchema = z.enum([
  "draft",
  "open",
  "paused",
  "closed",
  "filled",
]);
export type VacanteStatus = z.infer<typeof VacanteStatusSchema>;

export const VacanteSchema = z.object({
  id: z.string().uuid(),
  empresa_id: z.string().uuid(),
  slug: z.string().min(1),
  title: z.string().min(1),
  jd: z.string().min(1),
  icp_text: z.string().nullable(),
  seniority: z
    .enum(["junior", "semi-senior", "senior", "lead", "manager", "director"])
    .nullable(),
  modality: z.enum(["onsite", "hybrid", "remote"]),
  location: z.string().nullable(),
  salary_min: z.number().nonnegative().nullable(),
  salary_max: z.number().nonnegative().nullable(),
  currency: z.string().length(3).default("USD"),
  status: VacanteStatusSchema,
  created_at: z.string().datetime(),
  closed_at: z.string().datetime().nullable(),
});
export type Vacante = z.infer<typeof VacanteSchema>;

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
});
export type Application = z.infer<typeof ApplicationSchema>;

/** Output of `cv-evaluator` skill — strict schema for Pydantic mirror */
export const CvEvaluationSchema = z.object({
  candidate_id: z.string().uuid(),
  vacante_id: z.string().uuid(),
  score: z.number().min(0).max(10),
  rationale: z.string().min(1),
  gaps: z.array(z.string()),
  strengths: z.array(z.string()),
  recommended_next_step: z.enum(["psicometrico", "entrevista", "rechazar"]),
});
export type CvEvaluation = z.infer<typeof CvEvaluationSchema>;
