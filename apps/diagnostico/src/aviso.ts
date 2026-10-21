/**
 * Aviso de privacidad simplificado que se muestra al pedir los datos (LFPDPPP de
 * 2025, art. 16 fr. II: lo de las fracciones I a IV del art. 15 y dónde se consulta
 * el integral). Tiene que cuadrar con el integral de vectorhrtech.com.
 *
 * PENDIENTE DE ILYRA antes de publicar: el nombre legal y el domicilio del
 * responsable, los mismos del aviso integral. Mientras falten, la página muestra los
 * marcadores resaltados, para que no salga a producción sin ellos.
 */
export const RESPONSABLE = "[NOMBRE LEGAL del responsable]";
export const DOMICILIO = "[DOMICILIO del responsable]";
export const CONTACTO_PRIVACIDAD = "hola@vectorhrtech.com";
export const ASUNTO_NEGATIVA = "No usar mis datos para fines adicionales";
export const URL_AVISO_INTEGRAL = "https://vectorhrtech.com/aviso-de-privacidad";

export const AVISO_COMPLETO = !RESPONSABLE.startsWith("[") && !DOMICILIO.startsWith("[");
