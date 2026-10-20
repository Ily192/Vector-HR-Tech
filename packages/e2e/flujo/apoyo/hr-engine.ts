import { execFile } from "node:child_process";
import path from "node:path";
import { promisify } from "node:util";

import { RAIZ, entorno } from "./entorno";

const ejecutar = promisify(execFile);
const HR_ENGINE = path.join(RAIZ, "services", "hr-engine");
/** El Python que tiene uv. En la máquina de desarrollo uv no está en el PATH: `python -m uv`. */
const PYTHON = process.env.E2E_PYTHON ?? "python";

/** Corre `python …` en el entorno del hr-engine, contra el Supabase local. */
async function enElHrEngine(...argumentos: string[]): Promise<string> {
  const e = entorno();
  if (!e.baseDeDatos) throw new Error("El hr-engine solo se llama en local.");
  const { stdout } = await ejecutar(
    PYTHON,
    ["-m", "uv", "run", "--quiet", "python", ...argumentos],
    {
      cwd: HR_ENGINE,
      env: {
        ...process.env,
        ENV: "development",
        DATABASE_URL: e.baseDeDatos,
        SUPABASE_URL: e.supabaseUrl,
        SUPABASE_SECRET_KEY: e.claveSecreta,
        PANEL_URL: e.panel,
      },
      timeout: 120_000,
    },
  );
  return stdout.trim();
}

/** Vector HR da de alta a la empresa y le manda la invitación, igual que en producción. */
export function darDeAlta(empresa: string, correo: string, nombre: string): Promise<string> {
  return enElHrEngine(
    "-m",
    "app.cli.alta_empresa",
    ...["--empresa", empresa, "--correo", correo, "--nombre", nombre, "--tamano", "20"],
  );
}

/**
 * Un barrido del worker de coincidencias: la misma tarea que Celery beat lanza cada
 * minuto, llamada en el proceso para no esperar al reloj.
 */
export function barrer(): Promise<string> {
  return enElHrEngine("-c", "from app.workers.coincidencias import barrer; print(barrer())");
}
