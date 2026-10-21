/**
 * Aviso de privacidad simplificado que se muestra al pedir los datos (LFPDPPP).
 *
 * PENDIENTE DE ILYRA antes de publicar: el responsable (razón social o nombre) y la URL
 * del aviso integral, que vectorhrtech.com todavía no tiene. Mientras falten, la página
 * muestra los marcadores tal cual, para que no salga a producción sin ellos.
 */
export const RESPONSABLE = "[RESPONSABLE: razón social o nombre de Vector HR Tech]";
export const CONTACTO_PRIVACIDAD = "hola@vectorhrtech.com";
export const URL_AVISO_INTEGRAL = "[URL del aviso de privacidad integral]";

export const AVISO_COMPLETO = !RESPONSABLE.startsWith("[") && !URL_AVISO_INTEGRAL.startsWith("[");
