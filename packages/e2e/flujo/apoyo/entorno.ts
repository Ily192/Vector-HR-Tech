import { execSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

/**
 * Dónde corre el flujo del plan gratis.
 *
 * - **En local** (por defecto): contra el Supabase de `pnpm db:start`. Sus URLs y
 *   sus claves salen de `supabase status`, así que no hay ninguna en el repo. El
 *   alta y el barrido del worker corren con el hr-engine de `services/hr-engine`.
 * - **Contra un despliegue** (`E2E_REMOTO=1`): todo llega por variables (ver el
 *   README del paquete). Ahí no hay Mailpit ni comando de alta: entra una cuenta que
 *   ya existe y el worker del servidor hace sus barridos solo.
 */
export type Entorno = {
  remoto: boolean;
  supabaseUrl: string;
  clavePublica: string;
  claveSecreta: string;
  careerSite: string;
  panel: string;
  /** La cuenta que entra al panel en un despliegue. En local se crea una por corrida. */
  correo: string | null;
  /** Solo en local: la base para el comando de alta y el barrido. */
  baseDeDatos: string | null;
  mailpit: string | null;
};

export const RAIZ = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../..");

function variable(nombre: string): string {
  const valor = process.env[nombre];
  if (!valor) {
    throw new Error(
      `Falta ${nombre} para correr el flujo contra un despliegue (packages/e2e/README.md).`,
    );
  }
  return valor;
}

/** `supabase status -o env` del stack local: `API_URL`, `DB_URL`, `MAILPIT_URL` y las claves. */
function statusLocal(): Record<string, string> {
  let salida: string;
  try {
    // Con shell, porque `pnpm` es un .cmd en Windows; el comando es fijo.
    salida = execSync("pnpm exec supabase status -o env --workdir infra", {
      cwd: RAIZ,
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
    });
  } catch {
    throw new Error("El Supabase local no responde: levántalo con `pnpm db:start`.");
  }
  const variables: Record<string, string> = {};
  for (const linea of salida.split(/\r?\n/)) {
    const par = /^([A-Z0-9_]+)="?(.*?)"?$/.exec(linea.trim());
    if (par?.[1] && par[2] !== undefined) variables[par[1]] = par[2];
  }
  return variables;
}

let enMemoria: Entorno | null = null;

export function entorno(): Entorno {
  if (enMemoria) return enMemoria;
  if (process.env.E2E_REMOTO === "1") {
    enMemoria = {
      remoto: true,
      supabaseUrl: variable("E2E_SUPABASE_URL"),
      clavePublica: variable("E2E_SUPABASE_PUBLISHABLE_KEY"),
      claveSecreta: variable("E2E_SUPABASE_SECRET_KEY"),
      careerSite: variable("E2E_CAREER_SITE_URL"),
      panel: variable("E2E_PANEL_URL"),
      correo: variable("E2E_CORREO"),
      baseDeDatos: null,
      mailpit: null,
    };
    return enMemoria;
  }
  const s = statusLocal();
  const falta = ["API_URL", "DB_URL", "MAILPIT_URL", "PUBLISHABLE_KEY", "SECRET_KEY"].filter(
    (n) => !s[n],
  );
  if (falta.length > 0) {
    throw new Error(`\`supabase status\` no trae ${falta.join(", ")}. ¿Cambió la CLI?`);
  }
  enMemoria = {
    remoto: false,
    supabaseUrl: s.API_URL as string,
    clavePublica: s.PUBLISHABLE_KEY as string,
    claveSecreta: s.SECRET_KEY as string,
    // Los puertos de `pnpm dev`; el del panel es el `site_url` de infra/supabase/config.toml.
    careerSite: "http://localhost:3000",
    panel: "http://localhost:3001",
    correo: null,
    // El hr-engine habla con asyncpg.
    baseDeDatos: (s.DB_URL as string).replace(/^postgresql:/, "postgresql+asyncpg:"),
    mailpit: s.MAILPIT_URL as string,
  };
  return enMemoria;
}
