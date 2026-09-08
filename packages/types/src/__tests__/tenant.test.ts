import { describe, expect, it } from "vitest";

import {
  EmpresaSchema,
  JwtClaimsSchema,
  ProfileSchema,
  RoleSchema,
  RunTokenClaimsSchema,
} from "../tenant";

const UUID_A = "3f1b0e1a-2c4d-4f5e-8a9b-0c1d2e3f4a5b";
const UUID_B = "7d2c9f84-1b6e-4a30-9c11-5f8e2a0b4c6d";
const NOW = "2025-01-15T10:30:00.000Z";

function sinClaves(obj: Record<string, unknown>, ...keys: string[]): Record<string, unknown> {
  return Object.fromEntries(Object.entries(obj).filter(([key]) => !keys.includes(key)));
}

const empresaBase = {
  id: UUID_A,
  name: "Vector HR Tech",
  slug: "vector-hr-tech",
  paperclip_company_id: null,
  openclaw_workspace_id: null,
  hr_engine_quota_monthly: 1000,
  sales_engine_quota_monthly: 500,
  color_primario: "#1E1B4B",
  normativa_interna: null,
  google_webhook_url: null,
  created_at: NOW,
  updated_at: NOW,
};

describe("RoleSchema", () => {
  it("expone exactamente los roles del modelo multi-tenant", () => {
    expect(RoleSchema.options).toEqual(["Colaborador", "HR", "Director", "SuperAdmin", "cliente"]);
  });

  it("es case-sensitive — 'hr' no es 'HR'", () => {
    expect(RoleSchema.safeParse("HR").success).toBe(true);
    expect(RoleSchema.safeParse("hr").success).toBe(false);
    expect(RoleSchema.safeParse("admin").success).toBe(false);
  });
});

describe("EmpresaSchema", () => {
  it("parsea una empresa válida", () => {
    expect(EmpresaSchema.safeParse(empresaBase).success).toBe(true);
  });

  it("exige slug kebab-case", () => {
    expect(EmpresaSchema.safeParse({ ...empresaBase, slug: "vector-hr-2" }).success).toBe(true);
    for (const slug of ["Vector HR", "vector_hr", "VectorHR", "vector.hr", ""]) {
      const result = EmpresaSchema.safeParse({ ...empresaBase, slug });
      expect(result.success, `slug "${slug}" debería ser rechazado`).toBe(false);
    }
  });

  it("devuelve el mensaje de error personalizado del slug", () => {
    const result = EmpresaSchema.safeParse({ ...empresaBase, slug: "Vector HR" });
    expect(result.success).toBe(false);
    if (!result.success) {
      const issue = result.error.issues.find((i) => i.path[0] === "slug");
      expect(issue?.message).toBe("slug debe ser kebab-case");
    }
  });

  it("aplica defaults de cuotas y color corporativo", () => {
    const parsed = EmpresaSchema.parse(
      sinClaves(
        empresaBase,
        "hr_engine_quota_monthly",
        "sales_engine_quota_monthly",
        "color_primario",
      ),
    );
    expect(parsed.hr_engine_quota_monthly).toBe(1000);
    expect(parsed.sales_engine_quota_monthly).toBe(500);
    expect(parsed.color_primario).toBe("#1E1B4B");
  });

  it("exige cuotas enteras y positivas", () => {
    expect(EmpresaSchema.safeParse({ ...empresaBase, hr_engine_quota_monthly: 0 }).success).toBe(
      false,
    );
    expect(EmpresaSchema.safeParse({ ...empresaBase, hr_engine_quota_monthly: -10 }).success).toBe(
      false,
    );
    expect(EmpresaSchema.safeParse({ ...empresaBase, hr_engine_quota_monthly: 10.5 }).success).toBe(
      false,
    );
  });

  it("valida color_primario como hex de 6 dígitos", () => {
    expect(EmpresaSchema.safeParse({ ...empresaBase, color_primario: "#ff8a00" }).success).toBe(
      true,
    );
    expect(EmpresaSchema.safeParse({ ...empresaBase, color_primario: "#FFF" }).success).toBe(false);
    expect(EmpresaSchema.safeParse({ ...empresaBase, color_primario: "1E1B4B" }).success).toBe(
      false,
    );
    expect(EmpresaSchema.safeParse({ ...empresaBase, color_primario: "#GGGGGG" }).success).toBe(
      false,
    );
  });

  it("exige que google_webhook_url sea URL absoluta o null", () => {
    expect(
      EmpresaSchema.safeParse({ ...empresaBase, google_webhook_url: "chat.googleapis.com" })
        .success,
    ).toBe(false);
    expect(
      EmpresaSchema.safeParse({
        ...empresaBase,
        google_webhook_url: "https://chat.googleapis.com/v1/spaces/abc",
      }).success,
    ).toBe(true);
  });

  it("exige paperclip_company_id uuid cuando no es null", () => {
    expect(
      EmpresaSchema.safeParse({ ...empresaBase, paperclip_company_id: "company-1" }).success,
    ).toBe(false);
    expect(EmpresaSchema.safeParse({ ...empresaBase, paperclip_company_id: UUID_B }).success).toBe(
      true,
    );
  });
});

describe("ProfileSchema", () => {
  const base = {
    id: UUID_A,
    empresa_id: UUID_B,
    email: "ilyra@vectorhr.tech",
    full_name: "Ilyra Rivas",
    role: "HR",
    avatar_url: null,
    created_at: NOW,
  };

  it("parsea un profile válido", () => {
    const parsed = ProfileSchema.parse(base);
    expect(parsed.role).toBe("HR");
  });

  it("exige email — a diferencia de Candidato, aquí no puede ser null", () => {
    expect(ProfileSchema.safeParse({ ...base, email: null }).success).toBe(false);
    expect(ProfileSchema.safeParse(sinClaves(base, "email")).success).toBe(false);
    expect(ProfileSchema.safeParse({ ...base, email: "no-es-un-email" }).success).toBe(false);
  });

  it("rechaza un rol arbitrario", () => {
    expect(ProfileSchema.safeParse({ ...base, role: "root" }).success).toBe(false);
  });

  it("acepta avatar_url null o URL válida", () => {
    expect(
      ProfileSchema.safeParse({ ...base, avatar_url: "https://cdn.example.com/a.png" }).success,
    ).toBe(true);
    expect(ProfileSchema.safeParse({ ...base, avatar_url: "a.png" }).success).toBe(false);
  });
});

describe("JwtClaimsSchema", () => {
  const base = {
    sub: UUID_A,
    app_metadata: {
      empresa_id: UUID_B,
      app_role: "Director",
    },
    exp: 1_760_000_000,
  };

  it("permite omitir permissions (es opcional)", () => {
    const parsed = JwtClaimsSchema.parse(base);
    expect(parsed.app_metadata.permissions).toBeUndefined();
  });

  it("valida permissions como array de strings cuando viene", () => {
    const conPermisos = {
      ...base,
      app_metadata: { ...base.app_metadata, permissions: ["hr:read"] },
    };
    const malFormado = { ...base, app_metadata: { ...base.app_metadata, permissions: "hr:read" } };
    expect(JwtClaimsSchema.safeParse(conPermisos).success).toBe(true);
    expect(JwtClaimsSchema.safeParse(malFormado).success).toBe(false);
  });

  it("exige empresa_id — sin tenant no hay claim válido", () => {
    const sinEmpresa = { ...base, app_metadata: sinClaves(base.app_metadata, "empresa_id") };
    const empresaInvalida = { ...base, app_metadata: { ...base.app_metadata, empresa_id: "acme" } };
    expect(JwtClaimsSchema.safeParse(sinEmpresa).success).toBe(false);
    expect(JwtClaimsSchema.safeParse(empresaInvalida).success).toBe(false);
  });

  it("rechaza los claims en la raíz — deben ir bajo app_metadata (ADR-015)", () => {
    const enLaRaiz = { sub: UUID_A, empresa_id: UUID_B, role: "Director", exp: 1_760_000_000 };
    expect(JwtClaimsSchema.safeParse(enLaRaiz).success).toBe(false);
  });

  it("exige exp numérico (epoch), no string", () => {
    expect(JwtClaimsSchema.safeParse({ ...base, exp: "1760000000" }).success).toBe(false);
  });
});

describe("RunTokenClaimsSchema", () => {
  const base = {
    empresa_id: UUID_A,
    agent_skill: "cv-evaluator",
    run_id: UUID_B,
    cost_cap_usd: 0.02,
    exp: 1_760_000_000,
  };

  it("parsea un run-token válido", () => {
    expect(RunTokenClaimsSchema.parse(base).agent_skill).toBe("cv-evaluator");
  });

  it("exige cost_cap_usd estrictamente positivo — 0 desactivaría el cap", () => {
    expect(RunTokenClaimsSchema.safeParse({ ...base, cost_cap_usd: 0 }).success).toBe(false);
    expect(RunTokenClaimsSchema.safeParse({ ...base, cost_cap_usd: -1 }).success).toBe(false);
    expect(RunTokenClaimsSchema.safeParse({ ...base, cost_cap_usd: 0.0001 }).success).toBe(true);
  });

  it("exige run_id uuid", () => {
    expect(RunTokenClaimsSchema.safeParse({ ...base, run_id: "run-42" }).success).toBe(false);
  });
});
