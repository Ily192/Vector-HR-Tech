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

## Alternatives considered

- **API key estática del engine:** no atribuye, no caduca, no aplica cost cap.
- **OAuth2 client credentials:** overkill, latencia mayor.
