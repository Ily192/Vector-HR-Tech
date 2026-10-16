/**
 * Textos en español de los enums del dominio.
 *
 * Los enums viajan en inglés entre la base de datos, el backend y la UI; la UI
 * nunca los pinta crudos. Tenerlos aquí evita que cada app traduzca a su manera
 * (y que un enum nuevo se quede sin texto: el tipo `Record` obliga a cubrirlos).
 */
import type { ApplicationStatus, Modality, Seniority, SiguientePaso, VacanteStatus } from "./hr";

export const ETIQUETA_ESTADO_VACANTE: Record<VacanteStatus, string> = {
  draft: "Borrador",
  open: "Abierta",
  paused: "En pausa",
  closed: "Cerrada",
  filled: "Cubierta",
};

export const ETIQUETA_ESTADO_APLICACION: Record<ApplicationStatus, string> = {
  applied: "Aplicados",
  evaluated: "Evaluados",
  shortlisted: "Shortlist",
  interviewed: "Entrevista",
  offered: "Oferta",
  hired: "Contratados",
  rejected: "Descartados",
  withdrawn: "Se retiraron",
};

export const ETIQUETA_SENIORITY: Record<Seniority, string> = {
  junior: "Junior",
  "semi-senior": "Semi-senior",
  senior: "Senior",
  lead: "Lead",
  manager: "Gerencia",
  director: "Dirección",
};

export const ETIQUETA_MODALIDAD: Record<Modality, string> = {
  onsite: "Presencial",
  hybrid: "Híbrido",
  remote: "Remoto",
};

export const ETIQUETA_SIGUIENTE_PASO: Record<SiguientePaso, string> = {
  rechazar: "Descartar",
  psicometrico: "Psicométrico",
  entrevista: "Entrevista",
};
