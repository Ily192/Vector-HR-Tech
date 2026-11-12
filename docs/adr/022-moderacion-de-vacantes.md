# ADR-022: Verificar empresas y moderar vacantes antes del career site

- **Status:** Accepted
- **Date:** 2026-11-12
- **Decider:** Ilyra Rivas
- **Tags:** career-site, seguridad, plan-gratis, hr-engine

## Context

El alta en el plan gratis deja de ser una invitación manual de Vector HR (enmienda de
ADR-017, PR 1): quien se registra en vectorhrtech.com/publicar-vacantes entra al panel
con un código y puede publicar. Eso abre el career site a cualquiera, y las vacantes
falsas de siempre (cobrar un curso o un kit, pedir datos bancarios, mandar a un
WhatsApp, multinivel) dañan a candidatos reales y a la marca.

Ilyra pidió verificar a la empresa y a quien publica, revisar las vacantes de quien no
está verificado y de los reclutadores independientes, y un botón para reportar.

## Decision

1. **Insignia "Empresa verificada".** Se gana sola al confirmar el código si publica
   para su propia empresa, su correo no es de un proveedor gratuito y el dominio del
   correo coincide con el de su web (`insignia_por_dominio`, hr-engine). Vector HR
   también la da a mano tras revisar LinkedIn y la web (`app.cli.moderacion verificar
   --forzar`). Un reclutador independiente (`publica_para = 'clientes'`) nunca la lleva
   y su vacante sale a su nombre, con su LinkedIn.

   **Cómo se entera del código.** Auth pone `email_confirmed_at` cuando la persona
   escribe el código (0018, PR 1). Al principio de cada barrido de la moderación
   (`moderacion.barrer`, cada minuto) y antes de la limpieza diaria (`altas.limpiar`),
   `ConfirmarAltasDeLaWeb` toma las altas de `privado.altas_web` con una cuenta
   confirmada y sin `confirmado_en`, llama a `VerificarEmpresa` con el correo que
   confirmó y lo que la empresa dio al registrarse (cómo publica, web y LinkedIn), y
   pone `confirmado_en`: la misma marca que lee la limpieza de 7 días. Así la primera
   vacante de una empresa que acaba de confirmar ya se modera con su insignia.
2. **Moderación antes de publicar.** `vacantes.moderacion` (0019): la del panel nace
   `pendiente` y no sale al career site (`vacantes_publicas`, `aplicar_a_vacante`, el
   rol `career_site`) hasta que el hr-engine la decide. El panel la lee pero no la
   escribe: lo impide un trigger. Editar lo que el candidato ve la vuelve a `pendiente`.
3. **La decisión** (`app/domain/moderacion.py`), cada minuto con Celery beat:
   - riesgo alto (cobros, datos bancarios, multinivel) → `rechazada`, con la frase
     citada y qué corregir; una rechazada no cuenta en el tope del plan;
   - reclutador independiente → siempre `en_revision`;
   - primera vacante de una empresa sin verificar → `en_revision`;
   - riesgo medio (WhatsApp o Telegram, enlaces acortados, documentos antes de la
     entrevista, cripto, "sé tu propio jefe", sueldo irreal con "sin experiencia" y
     "desde casa", texto copiado de otra cuenta, ráfaga de una cuenta nueva) →
     `en_revision`;
   - lo demás → `publicada`, en el siguiente barrido.
4. **La cola de revisión** llega a hola@ en un resumen (como mucho cada 6 horas, antes si
   hay una vacante oculta por reportes, y un tope en 24 horas por la cuota de Resend).
   Cada vacante trae un enlace firmado con HMAC (`MODERACION_SECRETO`, 7 días) a
   `api./moderacion/revisar`: el GET solo muestra y el POST aprueba o rechaza con motivo.
5. **"Reportar vacante"** en el career site, con Turnstile y campo trampa. Pasa por
   `reportar_vacante()`, que solo ejecuta el rol `career_site`, guarda la IP como hash
   con sal y, con dos personas distintas desde la última moderación, oculta la vacante.
6. **Es moderación interna, no una función de IA para el cliente.** ADR-019 ("plan gratis
   sin IA") sigue en pie para lo que la empresa recibe. El PR 3 suma un modelo por el
   puerto `RevisorDeVacantes`: sus marcas se agregan a las de las reglas y la decisión no
   cambia. Cuando entre, el aviso de privacidad nombra al proveedor.

## Consequences

**Positivas:**
- Una vacante falsa no llega al candidato sin que una persona la vea, y la empresa sabe
  qué corregir.
- La regla vive en la base: ni el panel ni un cliente con la clave pública la saltan.
- La duda va a revisión humana, nunca al rechazo: solo lo grave se rechaza solo.

**Negativas:**
- La primera vacante de una empresa sin verificar espera a Vector HR. Hay que revisar la
  cola a diario.
- Las reglas son frases: se pueden esquivar escribiendo raro. Por eso la revisión humana
  y el modelo del PR 3.

**Neutras:**
- Lo que inserta el rol dueño (seed, CLI) nace publicado: la moderación es para lo que
  llega del panel.

## Fuentes

- Postgres 17, GRANT: "the table-level grant is unaffected by a column-level
  operation". Por eso la moderación la protege un trigger y no un `revoke` de columna:
  https://www.postgresql.org/docs/17/sql-grant.html
- Postgres 17, CREATE VIEW: `create or replace view` exige las mismas columnas y deja
  agregar al final: https://www.postgresql.org/docs/17/sql-createview.html
- Caddy, `request_body`: con `max_size`, un cuerpo más grande se rechaza con 413:
  https://caddyserver.com/docs/caddyfile/directives/request_body. Y `handle` acepta
  cualquier directiva de handler HTTP; `request_body` va antes que `reverse_proxy` en el
  orden de las directivas: https://caddyserver.com/docs/caddyfile/directives/handle y
  https://caddyserver.com/docs/caddyfile/directives#directive-order

## Alternatives considered

| Alternativa | Por qué descartada |
|---|---|
| Publicar todo y moderar después por reportes | La vacante falsa ya llegó a los candidatos |
| Revisar a mano todas las vacantes | No escala, y la empresa verificada espera sin motivo |
| Reportes por un endpoint del hr-engine | Otro secreto en Vercel y otra superficie pública; la RPC con el rol del career site deja la regla en la base |
| Rechazar todo lo dudoso | Un falso positivo le cuesta a una empresa real su vacante; mejor revisión |
