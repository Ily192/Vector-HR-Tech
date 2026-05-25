/**
 * Generated types placeholder.
 *
 * Cuando exista el Supabase Cloud project, regenerar con:
 *   pnpm --filter @vortex/supabase-client gen:types
 *
 * (requiere `supabase` CLI + `SUPABASE_PROJECT_REF` env).
 *
 * Por ahora exporto un schema minimal handcrafted a partir de
 * `infra/supabase/migrations/0001_initial_schema.sql` para que los apps
 * tengan tipos básicos en consultas. Es **manual y puede divergir** —
 * cualquier query que falle en runtime indica que hay que regenerar.
 */

import type {
  Application,
  ApplicationStatus,
  Candidato,
  CvEvaluation,
  Empresa,
  Profile,
  Vacante,
  VacanteStatus,
} from "@vortex/types";

type WithTimestamps<T> = T;
type Insert<T extends { id: string; created_at: string }> = Omit<T, "id" | "created_at"> & {
  id?: string;
  created_at?: string;
};
type Update<T> = Partial<T>;

export interface Database {
  public: {
    Tables: {
      empresas: {
        Row: WithTimestamps<Empresa>;
        Insert: Insert<Empresa>;
        Update: Update<Empresa>;
      };
      profiles: {
        Row: WithTimestamps<Profile>;
        Insert: Insert<Profile>;
        Update: Update<Profile>;
      };
      vacantes: {
        Row: WithTimestamps<Vacante>;
        Insert: Insert<Vacante>;
        Update: Update<Vacante>;
      };
      candidatos: {
        Row: WithTimestamps<Candidato>;
        Insert: Insert<Candidato>;
        Update: Update<Candidato>;
      };
      applications: {
        Row: WithTimestamps<Application>;
        Insert: Insert<Application>;
        Update: Update<Application>;
      };
    };
    Views: Record<string, never>;
    Functions: Record<string, never>;
    Enums: {
      vacante_status: VacanteStatus;
      application_status: ApplicationStatus;
      role_type: "Colaborador" | "HR" | "Director" | "SuperAdmin" | "cliente";
    };
    CompositeTypes: Record<string, never>;
  };
}

export type CvEvaluationRow = CvEvaluation;
