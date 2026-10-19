/**
 * Tipos de la base — PLACEHOLDER escrito a mano.
 *
 * Cuando exista el Supabase Cloud project, regenerar con:
 *   pnpm --filter @vortex/supabase-client gen:types
 *
 * (requiere `supabase` CLI + `SUPABASE_PROJECT_REF` env).
 *
 * Mientras tanto esto se deriva de `infra/supabase/migrations/` para que las
 * apps tengan tipos básicos en sus consultas. Es **manual y puede divergir** —
 * cualquier query que falle en runtime indica que hay que regenerar.
 *
 * Cobertura actual: las 5 tablas del core HR que `@vortex/types` ya modela,
 * más la vista pública, las funciones del flujo de test psicométrico y el cupo
 * del plan (0008). Las
 * tablas de auditoría y las de 0002/0004 (`runs`, `activity_log`,
 * `psicometricos`, `entrevistas`, `constancias`, `invitations`,
 * `platform_admins`) NO están tipadas aquí a propósito: el cliente de browser
 * no debe tocarlas, y tiparlas a mano invitaría a hacerlo.
 */

import type {
  Application,
  ApplicationStatus,
  Candidato,
  CvEvaluation,
  Empresa,
  Profile,
  Vacante,
  VacantePublica,
  VacanteStatus,
} from "@vortex/types";

/**
 * Columnas que la base rellena sola y que por tanto son opcionales al insertar.
 * `applications` es la única tabla del core cuyo timestamp de alta se llama
 * `applied_at` en vez de `created_at` (ver 0001), así que la restricción no
 * puede exigir `created_at`: hacerlo rompía el typecheck del paquete entero.
 */
type Generated =
  | "id"
  | "created_at"
  | "updated_at"
  | "applied_at"
  // Con default en la base (0007 y 0008).
  | "plan"
  | "tamano_empleados"
  | "limite_vacantes"
  | "salario_publico"
  | "deleted_at";

type Insert<T> = Omit<T, Extract<keyof T, Generated>> &
  Partial<Pick<T, Extract<keyof T, Generated>>>;

/** Nunca se debe reasignar la fila a otro tenant desde el cliente. */
type Update<T> = Partial<Omit<T, "id" | "empresa_id">>;

/**
 * Proyección pública de `vacantes` (0004, 0007 y 0008): sin ICP ni `empresa_id`
 * —publicar los uuids de tenant daba a cualquiera la lista de objetivos a los
 * que apuntar—, con el salario solo si la empresa lo publica y `cupo_completo`.
 * La forma vive en `@vortex/types` (`VacantePublicaSchema`).
 */
export type { VacantePublica };

export interface Database {
  public: {
    Tables: {
      empresas: {
        Row: Empresa;
        Insert: Insert<Empresa>;
        Update: Update<Empresa>;
      };
      profiles: {
        Row: Profile;
        Insert: Insert<Profile>;
        Update: Update<Profile>;
      };
      vacantes: {
        Row: Vacante;
        Insert: Insert<Vacante>;
        Update: Update<Vacante>;
      };
      candidatos: {
        Row: Candidato;
        Insert: Insert<Candidato>;
        Update: Update<Candidato>;
      };
      applications: {
        Row: Application;
        Insert: Insert<Application>;
        Update: Update<Application>;
      };
    };
    Views: {
      /** Lo único que `anon` puede leer de vacantes desde 0004. */
      vacantes_publicas: {
        Row: VacantePublica;
      };
    };
    Functions: {
      /**
       * Flujo público del test psicométrico. Desde 0004 el acceso anónimo a
       * la tabla está revocado y pasa por estas dos funciones.
       */
      get_psicometrico_by_token: {
        Args: { p_token: string };
        Returns: {
          id: string;
          status: "pending" | "in_progress" | "completed" | "expired";
          started_at: string | null;
          expires_at: string;
        }[];
      };
      /** "3 de 4" del panel (0008). `null` en límite = sin tope (plan con IA). */
      mi_cupo_de_vacantes: {
        Args: Record<string, never>;
        Returns: {
          activas: number;
          limite: number | null;
          libres: number | null;
          max_aplicaciones: number | null;
        }[];
      };
      /** El gancho del plan gratis (0009). Sin filas si la vacante no es tuya o tienes el plan con IA. */
      resumen_del_gancho: {
        Args: { p_vacante: string };
        Returns: {
          aplicaciones: number;
          cvs_evaluados: number;
          en_espera: number;
          segundos: number;
          califican: number;
          cumplen_todas_las_skills: number;
        }[];
      };
      submit_psicometrico: {
        Args: {
          p_token: string;
          p_answers: Record<string, unknown>;
          p_big5?: Record<string, number> | null;
          p_finish?: boolean;
        };
        Returns: string;
      };
    };
    Enums: {
      vacante_status: VacanteStatus;
      application_status: ApplicationStatus;
      plan_empresa: "gratis" | "ia";
      role_type: "Colaborador" | "HR" | "Director" | "SuperAdmin" | "cliente";
    };
    CompositeTypes: Record<string, never>;
  };
}

export type CvEvaluationRow = CvEvaluation;
