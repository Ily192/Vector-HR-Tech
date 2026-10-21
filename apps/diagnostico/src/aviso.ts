/**
 * Aviso de privacidad simplificado que se muestra al pedir los datos (LFPDPPP de
 * 2025, art. 16 fr. II: lo de las fracciones I a IV del art. 15 y dónde se consulta
 * el integral). Tiene que cuadrar con el integral de vectorhrtech.com.
 *
 * El responsable y el domicilio son los mismos del integral (Ilyra, 2026-10-21):
 * Vector HR Tech no está constituida y la opera ella como persona física, con un
 * domicilio general mientras no tenga uno comercial. Si alguno vuelve a ser un
 * marcador entre corchetes, la página lo resalta para que no salga así a producción.
 */
export const RESPONSABLE = "Ilyra Rivas";
export const DOMICILIO = "Mérida, Venezuela, código postal 5111";
export const CONTACTO_PRIVACIDAD = "hola@vectorhrtech.com";
export const ASUNTO_NEGATIVA = "No usar mis datos para fines adicionales";
export const URL_AVISO_INTEGRAL = "https://vectorhrtech.com/aviso-de-privacidad";

export const AVISO_COMPLETO = !RESPONSABLE.startsWith("[") && !DOMICILIO.startsWith("[");
