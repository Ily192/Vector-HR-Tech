# ADR-005: Paperclip emite run-tokens JWT 5 min para invocar engines

- **Status:** Accepted
- **Date:** 2026-05-08
- **Tags:** security, control-plane

## Context

Los engines (`hr-engine`, `sales-engine`) son llamados tanto por usuarios autenticados como por OpenClaw (canal conversacional, sin JWT humano). Necesitamos:

- Atribución de cada acción a un agente + tenant + cost cap.
- TTL corto para minimizar daño si se filtra.
- No repartir keys "globales" del engine.

## Decision

**Paperclip control plane es el único emisor de run-tokens.** Cuando un agente OpenClaw arranca una run, Paperclip:

1. Verifica presupuesto del tenant.
2. Verifica permiso del agente para ese skill.
3. Emite JWT firmado con claims:
   ```json
   {
     "empresa_id": "uuid",
     "agent_skill": "sourcer",
     "run_id": "uuid",
     "cost_cap_usd": 0.05,
     "exp": <now + 300>
   }
   ```

Engines validan firma + scope antes de ejecutar.

## Consequences

**Positivas:** todo path agentic pasa por governance. Cost cap aplicado en origen.
**Negativas:** Paperclip se vuelve dependencia crítica (mitigado con cache de keys públicas + circuit breaker en engines).

## Actualización 2026-10-19 · el plan gratis no corre agentes (ADR-019)

- **Todo run exige el plan con IA.** El hr-engine responde 403 al run-token de una
  empresa gratuita antes de crear la fila en `runs`. Así un Paperclip mal configurado, o
  una empresa que dejó de pagar, no gasta LLM.
- **La coincidencia de skills del plan gratis no es una run de agente.** La lanza el
  planificador del hr-engine (Celery beat) y no lleva run-token. No llama a ningún LLM:
  no tiene costo que atribuir en `runs` ni tope de gasto. No tiene endpoint, así que no
  expone ninguna llave.

Todo lo que lanza un agente sigue pasando por Paperclip.

(Esta sección reemplaza la que añadió ADR-018 el mismo día para una preselección con IA
que nunca llegó a construirse.)

## Alternatives considered

- **API key estática del engine:** no atribuye, no caduca, no aplica cost cap.
- **OAuth2 client credentials:** overkill, latencia mayor.
