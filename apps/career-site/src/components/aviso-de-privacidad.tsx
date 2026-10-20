/**
 * El aviso al candidato antes de aplicar. Hay dos, según la empresa evalúe o no con
 * IA (`vacantes_publicas.evalua_con_ia`):
 * - sin IA, el del plan gratis (ADR-019, "Condiciones antes de producción");
 * - con IA, el del plan de pago (ADR-018, "Condiciones", y ADR-021 §7).
 * Es el texto base: antes de abrir el formulario a candidatos reales lo revisa un
 * abogado (tarjeta legal del tablero).
 */
export function AvisoDePrivacidad({ empresa, conIa }: { empresa: string; conIa: boolean }) {
  return (
    <details className="rounded-xl border border-mist-200 bg-white px-4 py-3 text-[13.5px] leading-relaxed text-mist-700">
      <summary className="cursor-pointer font-bold text-ink-900">Aviso de privacidad</summary>
      <div className="mt-2 space-y-2">
        <p>
          {empresa} (responsable) usa Vortex, de Vector HR Tech (encargado), para recibir tu
          aplicación. Tu CV y tus datos llegan a {empresa} y solo se usan para este proceso.
        </p>
        {conIa ? (
          <p>
            Un sistema de IA compara tu CV con los requisitos de la vacante sin recibir tu nombre ni
            tus datos de contacto. La IA no descarta a nadie: decide una persona de {empresa}. El
            resultado es un dato tuyo: puedes acceder a él, corregirlo, oponerte a la evaluación con
            IA y pedir que lo revise una persona.
          </p>
        ) : (
          <p>
            Vortex compara las palabras de tu CV con las skills que pide la vacante y le da a{" "}
            {empresa} solo un conteo de cuántos CVs las mencionan, sin decirle cuáles. Eso no usa IA
            ni decide nada. Si {empresa} contrata los servicios de IA, tu CV se evalúa con IA y una
            persona decide.
          </p>
        )}
        <p>
          Puedes oponerte marcando «Evaluar mi CV sin procesos automatizados». Para acceder a tus
          datos, corregirlos o pedir que se borren, escribe a{" "}
          <a className="font-bold text-aqua-700 underline" href="mailto:hola@vectorhr.tech">
            hola@vectorhr.tech
          </a>
          .
        </p>
      </div>
    </details>
  );
}
