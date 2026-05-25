# Runbook · Deploy

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
