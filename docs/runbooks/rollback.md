# Runbook · Rollback

> Cuando un deploy salió mal y necesitas volver atrás rápido.

## Decisión: rollback vs hotfix

| Situación | Acción |
|---|---|
| Sev-1 / leak datos / sistema down | **Rollback inmediato**, hotfix después |
| Bug visible pero contornable | Hotfix con feature flag kill-switch |
| Performance degradada > 50% | Rollback |
| Bug cosmético | Hotfix en próximo cycle |

## Frontend Vercel (≤ 1 min)

```bash
# Via CLI
vercel rollback <deployment-id> --token $VERCEL_TOKEN
# o desde dashboard: Deployments → seleccionar previa → "Promote to Production"
```

## Backend Coolify (≤ 5 min)

```bash
# Listar deploys recientes del service
coolify deploys list --service hr-engine

# Rollback al SHA anterior
coolify rollback --service hr-engine --to <previous-sha>

# Verificar healthchecks
curl -fs https://api.vortex-ops.com/health
```

## Database (PITR Supabase)

Solo si hay corrupción real. **Antes de hacerlo, contactar al cliente afectado.**

1. Supabase Dashboard → Settings → Database → Point-in-Time Recovery.
2. Seleccionar timestamp anterior al incidente.
3. Confirmar: crea una nueva DB. Cambiar `DATABASE_URL` en Coolify para apuntar al snapshot.
4. Validar datos antes de cutover.
5. Postmortem obligatorio.

## Feature flag kill-switch

Si el problema viene de una feature específica, **no necesitas rollback** completo:

```bash
# Via Unleash CLI o dashboard
unleash flag disable <flag-name>
```

## Checklist post-rollback

- [ ] Service vuelve a verde en Sentry y OTel.
- [ ] Synthetic monitors verdes.
- [ ] Comunicar en status page.
- [ ] Crear issue de hotfix con label `post-rollback`.
- [ ] Identificar gap en CI (¿por qué pasó el bug?).
- [ ] Postmortem si Sev-1 / Sev-2.
