import matter from "gray-matter";
import { z } from "zod";

/**
 * Vortex SKILL.md schema — formato gstack (ver ADR-006).
 *
 * Cada agente vive como `.agents/skills/<slug>/SKILL.md` + un manifest opcional
 * por proveedor (`agents/openai.yaml`, `agents/anthropic.yaml`, etc.). Este SDK
 * solo se encarga de parsear y validar el frontmatter — los engines y el
 * control plane consumen el resultado para ejecutar el skill.
 */
export const SkillFrontmatterSchema = z.object({
  name: z
    .string()
    .min(1)
    .regex(/^[a-z0-9-]+$/, "name debe ser kebab-case"),
  version: z.string().regex(/^\d+\.\d+\.\d+$/, "semver requerido"),
  description: z.string().min(10),
  owner: z.string().min(1),
  domain: z.enum(["hr", "sales", "cross", "platform"]),
  inputs: z.array(z.string()).default([]),
  outputs: z.array(z.string()).default([]),
  tools: z.array(z.string()).default([]),
  models: z
    .object({
      default: z.string(),
      fallback: z.string().optional(),
    })
    .optional(),
  cost_cap_usd: z.number().positive().default(0.05),
  rate_limit_per_minute: z.number().int().positive().default(10),
  tags: z.array(z.string()).default([]),
});
export type SkillFrontmatter = z.infer<typeof SkillFrontmatterSchema>;

export const SkillManifestSchema = z.object({
  frontmatter: SkillFrontmatterSchema,
  prompt: z.string().min(1),
});
export type SkillManifest = z.infer<typeof SkillManifestSchema>;

/** Parsea un SKILL.md crudo y devuelve frontmatter validado + prompt body. */
export function parseSkillMarkdown(raw: string): SkillManifest {
  const parsed = matter(raw);
  const frontmatter = SkillFrontmatterSchema.parse(parsed.data);
  const prompt = parsed.content.trim();
  if (!prompt) {
    throw new Error("SKILL.md body (prompt) no puede estar vacío");
  }
  return { frontmatter, prompt };
}
