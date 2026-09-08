# Runbook · Deploy

> **⚠️ ESTADO REAL (2026-09-07): este runbook describe un sistema que todavia
> no existe.** Leelo como el diseño objetivo, no como instrucciones ejecutables.
>
> Lo que si funciona hoy:
> - Frontends: se despliegan por la integracion Git de Vercel, con la config de
>   `apps/*/vercel.json`. Los proyectos aun no estan provisionados.
>
> Lo que NO existe:
> - **No hay entorno de staging.** `staging.vortex-ops.com` y
>   `api.vortex-ops.com` no estan provisionados.
> - **No hay destino de deploy para el backend.** Los comandos de Coolify de
>   abajo apuntan a una plataforma que ADR-012 descarto en favor de Fly.io; los
>   secrets `COOLIFY_*` no existen y no se van a crear. No hay `fly.toml` ni
>   step de `flyctl` en ningun workflow.
> - **`release.yml` esta desactivado** (solo `workflow_dispatch`) justamente
>   porque intentaba ejecutar esto en cada push a `main`.
> - **El canary no existe.** Los `curl` con `canary_pct` son un JSON inventado:
>   Coolify no tiene traffic-splitting, y no hay balanceador ni service mesh en
>   ninguna parte del repo.
> - **Alembic no esta configurado**: no hay `alembic.ini` ni directorio de
>   migraciones. El esquema real son los `.sql` de `infra/supabase/migrations/`,
>   aplicados con `supabase db push`. Cualquier `alembic upgrade head` de aqui
>   abajo es aspiracional.
>
> Antes de un primer deploy real hay que cerrar esto; ver
> `docs/runbooks/next-steps.md`.

## Staging (automático)

Cualquier merge a `main` dispara `release.yml`:

```
build-images → deploy-staging → smoke-staging → promote-canary 5% → monitor 10min → promote-full
```

Si cualquier paso falla, no avanza. Sentry registra release SHA automáticamente.

## Producción (canary 5% → 100%)

Configurado en `release.yml`. Manual override si necesario:

```bash
# Promote 100% inmediato (usar con cuidado)
curl -X POST $COOLIFY_WEBHOOK_PROD \
  -H "Authorization: Bearer $COOLIFY_TOKEN" \
  -d '{"sha":"<sha>","canary_pct":100}'
```

## Migrations DB

**Patrón expand/contract obligatorio** para zero-downtime:

1. PR 1: Migration **expand** (agrega columnas/tablas, no rompe).
2. PR 1 deploy: app escribe a viejo + nuevo.
3. PR 2: Backfill data (si aplica).
4. PR 3: Migration que cambia reads a nuevo path.
5. PR 4: Migration **contract** (drop viejo).

Antes de mergear migration:

```bash
# Dry-run en staging
DATABASE_URL=$STAGING_DATABASE_URL alembic upgrade head --sql > /tmp/migration.sql
# Revisar /tmp/migration.sql humano

# Aplicar staging
DATABASE_URL=$STAGING_DATABASE_URL alembic upgrade head

# Verificar smoke staging verde
gh run watch
```

## Rollback

| Tipo | Cómo |
|---|---|
| Frontend Vercel | Promote previous deployment desde dashboard Vercel (~1 min) |
| Backend Coolify | `coolify rollback <service> --to <sha>` (~5 min) |
| Migration buena → app mala | Solo rollback del service. Migration queda. |
| Migration mala | Re-run down-migration (dry-run primero). Si imposible: PITR. |
| Datos corruptos | Supabase PITR — Settings → Database → PITR (≤ 30 min RTO) |

## Post-deploy checklist

- [ ] Sentry sin spike de errors en 10 min post-deploy.
- [ ] OTel p95 latency dentro de baseline +30%.
- [ ] Synthetic monitors verdes.
- [ ] DORA dashboard actualizado (auto via nightly).

## Si todo falla (Sev-1)

1. Pause deploys nuevos: label `deploy-frozen` en repo.
2. Rollback servicio afectado.
3. Comunicar en `/status` page.
4. Postmortem en ≤ 14 días en `docs/runbooks/postmortems/`.
