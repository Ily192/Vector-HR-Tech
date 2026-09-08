# Runbook · Rollback

> **⚠️ ESTADO REAL (2026-09-07): no existe ningun mecanismo de rollback
> implementado.** Ni job, ni step, ni script. Todo lo de abajo es diseño.
>
> Concretamente, los tres mecanismos que este runbook da por sentados:
> - `coolify rollback --service ... --to <sha>` — ese CLI no esta instalado ni
>   configurado en ninguna parte, y apunta a la plataforma que ADR-012 descarto.
> - `unleash flag disable <flag>` como kill-switch — Unleash no esta integrado.
>   `UNLEASH_URL`/`UNLEASH_API_TOKEN` estan en `.env.example` pero ningun
>   paquete del monorepo tiene el SDK ni lee esas variables.
> - **PITR de Supabase** — es una feature del plan Pro. ADR-012 planifica el
>   free tier, donde PITR no esta disponible. El RTO de 30 min no se sostiene
>   sin cambiar de plan o montar dumps propios.
>
> Lo unico que si se puede hacer hoy es revertir un deploy de frontend desde el
> dashboard de Vercel (Deployments → ... → Promote to Production sobre el
> deployment anterior), y `git revert` del commit.
>
> Cerrar esto es requisito para el primer deploy de backend; ver
> `docs/runbooks/next-steps.md`.

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
