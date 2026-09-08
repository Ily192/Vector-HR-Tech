import { z } from "zod";

export const IcpSchema = z.object({
  id: z.string().uuid(),
  empresa_id: z.string().uuid(),
  name: z.string().min(1),
  industries: z.array(z.string()),
  countries: z.array(z.string().length(2)),
  employees_min: z.number().int().nonnegative().nullable(),
  employees_max: z.number().int().nonnegative().nullable(),
  job_titles: z.array(z.string()),
  seniorities: z.array(z.string()),
  departments: z.array(z.string()),
  created_at: z.string().datetime(),
});
export type Icp = z.infer<typeof IcpSchema>;

export const CampaignStatusSchema = z.enum(["draft", "running", "paused", "completed", "failed"]);
export type CampaignStatus = z.infer<typeof CampaignStatusSchema>;

export const CampaignSchema = z.object({
  id: z.string().uuid(),
  empresa_id: z.string().uuid(),
  icp_id: z.string().uuid(),
  name: z.string().min(1),
  prospect_quantity: z.number().int().positive(),
  max_contacts_per_company: z.number().int().positive().default(3),
  prospect_frequency_days: z.number().int().positive().default(7),
  status: CampaignStatusSchema,
  reply_io_sequence_id: z.string().nullable(),
  created_at: z.string().datetime(),
});
export type Campaign = z.infer<typeof CampaignSchema>;
