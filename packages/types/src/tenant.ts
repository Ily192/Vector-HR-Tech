import { z } from "zod";

export const RoleSchema = z.enum([
  "Colaborador",
  "HR",
  "Director",
  "SuperAdmin",
  "cliente",
]);
export type Role = z.infer<typeof RoleSchema>;

export const EmpresaSchema = z.object({
  id: z.string().uuid(),
  name: z.string().min(1),
  slug: z
    .string()
    .min(1)
    .regex(/^[a-z0-9-]+$/, "slug debe ser kebab-case"),
  paperclip_company_id: z.string().uuid().nullable(),
  openclaw_workspace_id: z.string().nullable(),
  hr_engine_quota_monthly: z.number().int().positive().default(1000),
  sales_engine_quota_monthly: z.number().int().positive().default(500),
  color_primario: z
    .string()
    .regex(/^#[0-9A-Fa-f]{6}$/)
    .default("#1E1B4B"),
  normativa_interna: z.string().nullable(),
  google_webhook_url: z.string().url().nullable(),
  created_at: z.string().datetime(),
  updated_at: z.string().datetime(),
});
export type Empresa = z.infer<typeof EmpresaSchema>;

export const ProfileSchema = z.object({
  id: z.string().uuid(),
  empresa_id: z.string().uuid(),
  email: z.string().email(),
  full_name: z.string().min(1),
  role: RoleSchema,
  avatar_url: z.string().url().nullable(),
  created_at: z.string().datetime(),
});
export type Profile = z.infer<typeof ProfileSchema>;

/** JWT custom claims emitted by Supabase Auth */
export const JwtClaimsSchema = z.object({
  sub: z.string().uuid(),
  empresa_id: z.string().uuid(),
  role: RoleSchema,
  permissions: z.array(z.string()).optional(),
  exp: z.number(),
});
export type JwtClaims = z.infer<typeof JwtClaimsSchema>;

/** Run token issued by Paperclip control plane (5 min TTL) */
export const RunTokenClaimsSchema = z.object({
  empresa_id: z.string().uuid(),
  agent_skill: z.string(),
  run_id: z.string().uuid(),
  cost_cap_usd: z.number().positive(),
  exp: z.number(),
});
export type RunTokenClaims = z.infer<typeof RunTokenClaimsSchema>;
