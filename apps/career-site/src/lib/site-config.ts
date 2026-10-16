/**
 * Datos de contacto y compromisos públicos del sitio, en un solo lugar para que
 * dos páginas no prometan cosas distintas.
 */

/** Correo público de Vector HR. Se puede cambiar por entorno sin tocar código. */
export const CONTACT_EMAIL = process.env.NEXT_PUBLIC_CONTACT_EMAIL ?? "hola@vectorhr.tech";

export const LINKEDIN_URL = "https://www.linkedin.com/company/vector-hr-tech";

/** Tiempo de respuesta que se promete en la web. */
export const TIEMPO_DE_RESPUESTA = "24 h hábiles";
