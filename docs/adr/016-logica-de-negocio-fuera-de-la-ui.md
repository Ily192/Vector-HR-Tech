# ADR-016: La lógica de negocio vive en el backend; la UI solo la presenta

- **Status:** Accepted
- **Date:** 2026-10-16
- **Decider:** Ilyra
- **Tags:** frontend, arquitectura, documentación

## Context

Una auditoría de `apps/hrbp`, `apps/career-site` y los paquetes compartidos
(octubre de 2026) encontró que ninguna pantalla lee datos reales y que las
reglas de negocio estaban escritas dentro de los componentes:

- **Datos de ejemplo como fuente de verdad.** Los KPIs, los conteos del embudo y
  dos copias distintas del catálogo de vacantes eran constantes en el JSX.
- **Reglas implícitas.** Qué estados forman el embudo y en qué orden, qué es una
  vacante "abierta", y el texto que anunciaba el siguiente paso de un candidato.
- **Reglas que ya no coincidían con el backend.** El detalle de vacante decía
  que, si había match, llegaba un test psicométrico. El backend
  (`app/domain/siguiente_paso.py`) manda a entrevista desde 7 y a psicométrico
  de 4 a 7. El cockpit decía "12 % del cap" (diario), y en el backend el tope es
  por run.
- **Enums pintados crudos** ("remote", "semi-senior", "Open") en un sitio en
  español.

Con datos fijos el problema no se nota. Cuando las pantallas lean Supabase y el
hr-engine, cada regla duplicada en la UI puede contradecir al backend sin que
ningún test lo detecte.

## Decision

1. **La dueña de cada regla es el backend**: el dominio del hr-engine, o la
   base de datos (RLS y vistas) para lo que es visibilidad. La UI no decide nada
   que cambie qué le pasa a un candidato, a una vacante o a una empresa.
2. **Si la UI tiene que mostrar o anticipar una regla**, la usa desde
   `@vortex/types`, nunca escrita en el componente:
   - `src/reglas.ts` contiene las reglas espejadas (`siguientePaso`,
     `UMBRALES_SIGUIENTE_PASO`, `ETAPAS_DEL_PIPELINE`);
   - cada regla espejada tiene un contrato JSON en `packages/types/contracts/`
     que prueban los dos lados: Vitest y pytest;
   - `src/etiquetas.ts` tiene los textos en español de cada enum.
3. **Cada app separa datos de presentación:**
   - `apps/<app>/src/lib/` (career-site) o `src/<pantalla>/` (hrbp) concentran
     el acceso a datos. Las páginas solo llaman a funciones como
     `listarVacantes()` u `obtenerResumenCockpit()`.
   - Mientras no haya backend, esas funciones devuelven datos de ejemplo con la
     forma exacta de la respuesta real, validados con el esquema de
     `@vortex/types` cuando existe. Cambiar a datos reales toca un solo fichero.
   - Los cálculos de presentación (por ejemplo, el ancho de una barra) van en
     funciones puras con test, fuera del JSX.
4. **Indicadores agregados** (conteos, variaciones, porcentajes) los calcula el
   backend. La UI no suma ni compara ventanas de tiempo.
5. **Documentación del código:**
   - todo lo que exporta un paquete o un módulo de datos lleva TSDoc
     (`/** … */`) que diga **qué es y de dónde sale**, no cómo está escrito;
   - en Python, docstrings en dominio, aplicación e infraestructura (ya es la
     norma en el hr-engine);
   - cada app y cada paquete tienen un `README.md` con qué es, cómo se corre, su
     estructura y dónde van las reglas;
   - las decisiones que cruzan apps van en un ADR.

## Consequences

**Positivas:**

- Un cambio de umbral en el backend rompe un test en `packages/types` si la UI
  no se actualiza.
- Conectar datos reales es cambiar una función por pantalla, no reescribirla.
- Los tests de pantalla prueban presentación, no números inventados.

**Negativas:**

- Más ficheros para pantallas pequeñas.
- Las reglas espejadas siguen siendo dos copias. El contrato las mantiene
  iguales, pero hay que acordarse de añadirle casos.

**Neutras:**

- `@vortex/types` exporta subrutas (`/reglas`, `/etiquetas`, `/hr`) para que
  hrbp importe solo constantes y tipos, sin arrastrar Zod a su bundle.

## Alternatives considered

| Alternativa | Por qué descartada |
|---|---|
| Que el backend devuelva todos los textos y pasos ya resueltos | Correcto a largo plazo para los pasos, pero hoy no hay endpoints, y las etiquetas son de presentación. |
| Dejar los mocks en las páginas hasta conectar el backend | Es lo que produjo las contradicciones que encontró la auditoría. |
| Generar los tipos de TS desde Pydantic | Se puede hacer más adelante; el contrato JSON resuelve hoy las reglas que importan, con menos maquinaria. |
