import { describe, expect, it } from "vitest";

import { CampaignSchema, CampaignStatusSchema, IcpSchema } from "../sales";

const UUID_A = "3f1b0e1a-2c4d-4f5e-8a9b-0c1d2e3f4a5b";
const UUID_B = "7d2c9f84-1b6e-4a30-9c11-5f8e2a0b4c6d";
const UUID_C = "0a9b8c7d-6e5f-4a3b-a2c1-9d8e7f6a5b4c";
const NOW = "2025-01-15T10:30:00.000Z";

function sinClaves(obj: Record<string, unknown>, ...keys: string[]): Record<string, unknown> {
  return Object.fromEntries(Object.entries(obj).filter(([key]) => !keys.includes(key)));
}

describe("IcpSchema", () => {
  const base = {
    id: UUID_A,
    empresa_id: UUID_B,
    name: "SaaS B2B LATAM 50-500",
    industries: ["software", "fintech"],
    countries: ["MX", "CO", "AR"],
    employees_min: 50,
    employees_max: 500,
    job_titles: ["Head of People", "HR Director"],
    seniorities: ["director", "head"],
    departments: ["human resources"],
    created_at: NOW,
  };

  it("parsea un ICP válido", () => {
    const parsed = IcpSchema.parse(base);
    expect(parsed.countries).toEqual(["MX", "CO", "AR"]);
  });

  it("exige códigos de país ISO-3166 alpha-2 (exactamente 2 chars)", () => {
    expect(IcpSchema.safeParse({ ...base, countries: ["MEX"] }).success).toBe(false);
    expect(IcpSchema.safeParse({ ...base, countries: ["M"] }).success).toBe(false);
    expect(IcpSchema.safeParse({ ...base, countries: [] }).success).toBe(true);
  });

  it("señala el índice exacto del país inválido", () => {
    const result = IcpSchema.safeParse({ ...base, countries: ["MX", "BRA"] });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0]?.path).toEqual(["countries", 1]);
    }
  });

  it("acepta rangos de headcount nulos pero rechaza negativos o decimales", () => {
    expect(IcpSchema.safeParse({ ...base, employees_min: null, employees_max: null }).success).toBe(
      true,
    );
    expect(IcpSchema.safeParse({ ...base, employees_min: -1 }).success).toBe(false);
    expect(IcpSchema.safeParse({ ...base, employees_min: 10.5 }).success).toBe(false);
    expect(IcpSchema.safeParse({ ...base, employees_min: 0 }).success).toBe(true);
  });

  it("exige name no vacío y arrays presentes (sin defaults)", () => {
    expect(IcpSchema.safeParse({ ...base, name: "" }).success).toBe(false);
    expect(IcpSchema.safeParse(sinClaves(base, "industries")).success).toBe(false);
    expect(IcpSchema.safeParse(sinClaves(base, "job_titles")).success).toBe(false);
  });
});

describe("CampaignStatusSchema", () => {
  it("expone los estados del ciclo de vida de campaña", () => {
    expect(CampaignStatusSchema.options).toEqual([
      "draft",
      "running",
      "paused",
      "completed",
      "failed",
    ]);
  });

  it("rechaza estados inventados", () => {
    expect(CampaignStatusSchema.safeParse("archived").success).toBe(false);
  });
});

describe("CampaignSchema", () => {
  const base = {
    id: UUID_A,
    empresa_id: UUID_B,
    icp_id: UUID_C,
    name: "Outbound Q1 · People Leaders",
    prospect_quantity: 250,
    status: "draft",
    reply_io_sequence_id: null,
    created_at: NOW,
  };

  it("aplica los defaults de ritmo de prospección", () => {
    const parsed = CampaignSchema.parse(base);
    expect(parsed.max_contacts_per_company).toBe(3);
    expect(parsed.prospect_frequency_days).toBe(7);
  });

  it("respeta los valores explícitos por encima de los defaults", () => {
    const parsed = CampaignSchema.parse({
      ...base,
      max_contacts_per_company: 5,
      prospect_frequency_days: 14,
    });
    expect(parsed.max_contacts_per_company).toBe(5);
    expect(parsed.prospect_frequency_days).toBe(14);
  });

  it("exige prospect_quantity entero y positivo", () => {
    expect(CampaignSchema.safeParse({ ...base, prospect_quantity: 0 }).success).toBe(false);
    expect(CampaignSchema.safeParse({ ...base, prospect_quantity: 12.5 }).success).toBe(false);
    expect(CampaignSchema.safeParse({ ...base, prospect_quantity: "250" }).success).toBe(false);
  });

  it("rechaza frecuencias de prospección no positivas", () => {
    expect(CampaignSchema.safeParse({ ...base, prospect_frequency_days: 0 }).success).toBe(false);
    expect(CampaignSchema.safeParse({ ...base, max_contacts_per_company: 0 }).success).toBe(false);
  });

  it("exige que icp_id sea uuid — una campaña sin ICP válido no puede correr", () => {
    expect(CampaignSchema.safeParse({ ...base, icp_id: "icp-1" }).success).toBe(false);
    expect(CampaignSchema.safeParse(sinClaves(base, "icp_id")).success).toBe(false);
  });

  it("acepta reply_io_sequence_id como string o null", () => {
    expect(CampaignSchema.safeParse({ ...base, reply_io_sequence_id: "seq_123" }).success).toBe(
      true,
    );
    expect(CampaignSchema.safeParse({ ...base, reply_io_sequence_id: 123 }).success).toBe(false);
  });
});
