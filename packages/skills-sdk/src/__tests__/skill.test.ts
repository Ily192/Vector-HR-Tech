import { existsSync, readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";
import { ZodError } from "zod";

import { SkillFrontmatterSchema, SkillManifestSchema, parseSkillMarkdown } from "../skill";

/** Construye un SKILL.md a partir de líneas de frontmatter + body. */
function skillMd(
  frontmatter: string,
  body = "Sos un evaluador HR senior.\n\n## Reglas\n\n1. No inventes.",
) {
  return `---\n${frontmatter.trim()}\n---\n\n${body}\n`;
}

const FRONTMATTER_VALIDO = `
name: cv-evaluator
version: 0.1.0
description: Evalúa el fit candidato/vacante y devuelve JSON estricto.
owner: Vector HR Tech
domain: hr
`;

describe("parseSkillMarkdown — camino feliz", () => {
  it("devuelve frontmatter validado y prompt body", () => {
    const manifest = parseSkillMarkdown(
      skillMd(`
${FRONTMATTER_VALIDO.trim()}
inputs:
  - candidato
  - vacante
outputs:
  - score
tools:
  - none
models:
  default: gemini-1.5-flash
  fallback: gpt-4o-mini
cost_cap_usd: 0.02
rate_limit_per_minute: 30
tags:
  - hr
  - scoring
`),
    );

    expect(manifest.frontmatter.name).toBe("cv-evaluator");
    expect(manifest.frontmatter.version).toBe("0.1.0");
    expect(manifest.frontmatter.domain).toBe("hr");
    expect(manifest.frontmatter.inputs).toEqual(["candidato", "vacante"]);
    expect(manifest.frontmatter.models).toEqual({
      default: "gemini-1.5-flash",
      fallback: "gpt-4o-mini",
    });
    expect(manifest.frontmatter.cost_cap_usd).toBe(0.02);
    expect(manifest.frontmatter.rate_limit_per_minute).toBe(30);
    expect(manifest.frontmatter.tags).toEqual(["hr", "scoring"]);
    expect(manifest.prompt.startsWith("Sos un evaluador HR senior.")).toBe(true);
    // El manifest resultante satisface su propio schema.
    expect(SkillManifestSchema.safeParse(manifest).success).toBe(true);
  });

  it("aplica los defaults de governance cuando el frontmatter es mínimo", () => {
    const { frontmatter } = parseSkillMarkdown(skillMd(FRONTMATTER_VALIDO));

    expect(frontmatter.inputs).toEqual([]);
    expect(frontmatter.outputs).toEqual([]);
    expect(frontmatter.tools).toEqual([]);
    expect(frontmatter.tags).toEqual([]);
    expect(frontmatter.cost_cap_usd).toBe(0.05);
    expect(frontmatter.rate_limit_per_minute).toBe(10);
    expect(frontmatter.models).toBeUndefined();
  });

  it("recorta el whitespace alrededor del prompt", () => {
    const manifest = parseSkillMarkdown(
      `---\n${FRONTMATTER_VALIDO.trim()}\n---\n\n\n   Contenido del prompt.   \n\n\n`,
    );
    expect(manifest.prompt).toBe("Contenido del prompt.");
  });

  it("preserva el markdown del body (headings, listas, code fences)", () => {
    const body = '# Título\n\n- item 1\n- item 2\n\n```json\n{ "score": 8 }\n```';
    const manifest = parseSkillMarkdown(skillMd(FRONTMATTER_VALIDO, body));
    expect(manifest.prompt).toContain("```json");
    expect(manifest.prompt).toContain("- item 2");
  });
});

describe("parseSkillMarkdown — frontmatter inválido", () => {
  it("lanza ZodError si name no es kebab-case", () => {
    const raw = skillMd(FRONTMATTER_VALIDO.replace("cv-evaluator", "CV Evaluator"));
    expect(() => parseSkillMarkdown(raw)).toThrow(ZodError);
    try {
      parseSkillMarkdown(raw);
      expect.unreachable("debería haber lanzado");
    } catch (error) {
      expect(error).toBeInstanceOf(ZodError);
      expect((error as ZodError).issues[0]?.message).toBe("name debe ser kebab-case");
      expect((error as ZodError).issues[0]?.path).toEqual(["name"]);
    }
  });

  it("lanza si version no es semver", () => {
    for (const version of ["1", "1.0", "v1.0.0", "0.1.0-beta"]) {
      const raw = skillMd(FRONTMATTER_VALIDO.replace("0.1.0", version));
      expect(() => parseSkillMarkdown(raw), `version "${version}"`).toThrow(ZodError);
    }
  });

  it("lanza si description es demasiado corta (< 10 chars)", () => {
    const raw = skillMd(`
name: cv-evaluator
version: 0.1.0
description: corta
owner: Vector HR Tech
domain: hr
`);
    expect(() => parseSkillMarkdown(raw)).toThrow(ZodError);
  });

  it("lanza si falta cualquiera de los campos requeridos", () => {
    for (const campo of ["name", "version", "description", "owner", "domain"]) {
      const frontmatter = FRONTMATTER_VALIDO.trim()
        .split("\n")
        .filter((line) => !line.startsWith(`${campo}:`))
        .join("\n");
      expect(() => parseSkillMarkdown(skillMd(frontmatter)), `faltando "${campo}"`).toThrow(
        ZodError,
      );
    }
  });

  it("reporta todos los campos faltantes de una sola pasada", () => {
    const result = SkillFrontmatterSchema.safeParse({ name: "sourcer" });
    expect(result.success).toBe(false);
    if (!result.success) {
      const paths = result.error.issues.map((issue) => issue.path.join("."));
      expect(paths).toEqual(expect.arrayContaining(["version", "description", "owner", "domain"]));
    }
  });

  it("lanza si domain no está en el enum hr/sales/cross/platform", () => {
    const raw = skillMd(FRONTMATTER_VALIDO.replace("domain: hr", "domain: marketing"));
    expect(() => parseSkillMarkdown(raw)).toThrow(ZodError);
  });

  it("lanza si el SKILL.md no tiene frontmatter", () => {
    expect(() => parseSkillMarkdown("Solo un prompt sin frontmatter.")).toThrow(ZodError);
  });

  it("lanza si cost_cap_usd no es positivo", () => {
    expect(() =>
      parseSkillMarkdown(skillMd(`${FRONTMATTER_VALIDO.trim()}\ncost_cap_usd: 0`)),
    ).toThrow(ZodError);
    expect(() =>
      parseSkillMarkdown(skillMd(`${FRONTMATTER_VALIDO.trim()}\ncost_cap_usd: -0.1`)),
    ).toThrow(ZodError);
  });

  it("lanza si rate_limit_per_minute no es entero positivo", () => {
    expect(() =>
      parseSkillMarkdown(skillMd(`${FRONTMATTER_VALIDO.trim()}\nrate_limit_per_minute: 2.5`)),
    ).toThrow(ZodError);
  });

  it("lanza si models viene sin la clave default", () => {
    expect(() =>
      parseSkillMarkdown(skillMd(`${FRONTMATTER_VALIDO.trim()}\nmodels:\n  fallback: gpt-4o-mini`)),
    ).toThrow(ZodError);
  });

  it("lanza si tools/inputs no son listas de strings", () => {
    expect(() => parseSkillMarkdown(skillMd(`${FRONTMATTER_VALIDO.trim()}\ntools: none`))).toThrow(
      ZodError,
    );
  });
});

describe("parseSkillMarkdown — body vacío", () => {
  it("lanza un Error explícito si no hay prompt", () => {
    expect(() => parseSkillMarkdown(`---\n${FRONTMATTER_VALIDO.trim()}\n---\n`)).toThrow(
      /body \(prompt\) no puede estar vacío/,
    );
  });

  it("trata un body de solo whitespace como vacío", () => {
    expect(() => parseSkillMarkdown(`---\n${FRONTMATTER_VALIDO.trim()}\n---\n\n   \n\t\n`)).toThrow(
      /no puede estar vacío/,
    );
  });

  it("no lanza ZodError sino Error genérico para el body vacío", () => {
    try {
      parseSkillMarkdown(`---\n${FRONTMATTER_VALIDO.trim()}\n---\n`);
      expect.unreachable("debería haber lanzado");
    } catch (error) {
      expect(error).toBeInstanceOf(Error);
      expect(error).not.toBeInstanceOf(ZodError);
    }
  });
});

describe("SKILL.md reales del repo", () => {
  const skillsDir = fileURLToPath(new URL("../../../../.agents/skills", import.meta.url));

  it("todos los SKILL.md versionados parsean sin errores", () => {
    expect(existsSync(skillsDir), `no existe ${skillsDir}`).toBe(true);

    const slugs = readdirSync(skillsDir, { withFileTypes: true })
      .filter((entry) => entry.isDirectory())
      .map((entry) => entry.name);

    expect(slugs.length).toBeGreaterThan(0);

    for (const slug of slugs) {
      const raw = readFileSync(`${skillsDir}/${slug}/SKILL.md`, "utf8");
      const manifest = parseSkillMarkdown(raw);
      // El slug del directorio debe coincidir con el `name` del frontmatter.
      expect(manifest.frontmatter.name, `${slug}/SKILL.md`).toBe(slug);
      expect(manifest.prompt.length).toBeGreaterThan(0);
    }
  });
});
