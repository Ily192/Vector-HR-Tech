import { cn } from "@fluveai/ui";

export const CORREO_DE_VECTOR = "hola@vectorhrtech.com";

/**
 * Lo único que vende hoy el panel gratis (ADR-024; decisión de Ilyra, 2026-11-19): más
 * vacantes, un reclutamiento masivo o más CVs por vacante. Se pide por correo, y el asunto
 * ya dice qué necesita la empresa. Fluve AI se ofrecerá aquí cuando esté lista.
 */
export function EscribenosParaMas({
  pregunta,
  asunto,
  className,
}: {
  pregunta: string;
  asunto: string;
  className?: string;
}) {
  return (
    <p className={cn("text-[13.5px] text-mist-600", className)}>
      {pregunta} Escríbenos a{" "}
      <a
        href={`mailto:${CORREO_DE_VECTOR}?subject=${encodeURIComponent(asunto)}`}
        className="font-bold text-aqua-700 hover:underline"
      >
        {CORREO_DE_VECTOR}
      </a>
      .
    </p>
  );
}

/** Para "Mis vacantes" y "Crear empleo", donde el tope es de vacantes. */
export const MAS_VACANTES = {
  pregunta: "¿Necesitas publicar más vacantes o hacer un reclutamiento masivo?",
  asunto: "Quiero publicar más vacantes",
} as const;
