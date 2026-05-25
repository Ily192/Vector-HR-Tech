# 08 · Security & Compliance

## 1. Modelo de amenazas (resumen STRIDE)

| Amenaza | Vector | Mitigación |
|---|---|---|
| **Spoofing** | JWT robado de un HRBP | Tokens cortos + refresh rotativo + MFA opcional |
| **Tampering** | Modificación de payload entre OpenClaw y hr-engine | mTLS interno + run-token JWT firmado por Paperclip |
| **Repudiation** | Usuario niega haber aprobado contratación | Activity log append-only firmado |
| **Information disclosure** | Cliente A ve datos de cliente B | RLS Supabase + middleware tenant-check + tests dedicados |
| **DoS** | Spam al career-site público | Rate limit por IP + Cloudflare Turnstile + WAF |
| **Elevation of privilege** | Candidato accede a cockpit HRBP | RLS + role check en JWT + tests E2E |

## 2. Identidad y acceso

### 2.1 Autenticación

- **Supabase Auth** como identity provider.
- Métodos: email + magic link (default), Google OAuth (HRBP), SSO SAML (Enterprise tier).
- **MFA opcional** desde el inicio; obligatorio para roles `Director` y `SuperAdmin`.

### 2.2 JWT claims custom

```json
{
  "sub": "<user_uuid>",
  "empresa_id": "<empresa_uuid>",
  "role": "Colaborador|HR|Director|SuperAdmin|cliente",
  "permissions": ["read:candidatos", "write:vacantes", ...],
  "exp": "..."
}
```

- TTL: 1 hora (access token) + refresh token 7 días.
- Custom claim `empresa_id` poblado por trigger Supabase post-login.

### 2.3 Run-tokens (Paperclip → engines)

- Emitidos por control-plane cuando un agente arranca una run.
- TTL: 5 minutos.
- Scope: `empresa_id` + `agent_skill` + `run_id` + `cost_cap_usd`.
- engines validan firma + scope antes de ejecutar.

### 2.4 RBAC

| Rol | Permisos clave |
|---|---|
| `Colaborador` | Ver su perfil, sus tareas, sus candidatos asignados |
| `HR` | + CRUD vacantes/candidatos, mover pipeline, ver psicométricos |
| `Director` | + Aprobaciones, presupuesto, reportes |
| `SuperAdmin` (Vector HR Tech staff) | Soporte cross-tenant con audit log obligatorio |
| `cliente` (candidato externo) | Ver su propia aplicación, completar tests |

ABAC sobre RBAC: row-level via RLS + atributos `empresa_id`.

## 3. Multi-tenancy seguro

- **RLS Supabase obligatoria** en toda tabla con `empresa_id`. Política base:
  ```sql
  create policy tenant_isolation on <tabla>
    using (empresa_id = (auth.jwt() ->> 'empresa_id')::uuid);
  ```
- **Test de RLS** por cada tabla nueva (ver doc 06 §5).
- **Middleware `tenant_guard`** en FastAPI: extrae `empresa_id` del JWT y lo inyecta en cada query — defensa en profundidad por si RLS falla.
- **Compartmentalización opcional** para Enterprise: schema dedicado por tenant (`tenant_<empresa_id>.candidatos`) con conexión separada.

## 4. Secrets management

- **Doppler** (start) o **Vault** (Enterprise).
- Nunca en repo. `.env.example` documentado, `.env` en `.gitignore`.
- `gitleaks` pre-commit + GitHub secret scanning.
- Rotación trimestral con calendario en `docs/runbooks/rotation.md`.
- API keys de IA con cuota por tenant + alerta de uso anómalo.

## 5. Datos y privacidad

### 5.1 Clasificación

| Clase | Ejemplo | Trato |
|---|---|---|
| **Pública** | JD publicada, brochure | CDN OK |
| **Interna** | Lista de vacantes activas | Auth required |
| **Confidencial** | CVs, datos contacto candidatos | Cifrado en reposo + RLS estricto |
| **Sensible (PII)** | Resultado psicométrico, salud, etnia (si capturada) | Cifrado columna + acceso loggeado + retención limitada |

### 5.2 Cifrado

- **En tránsito:** TLS 1.3 obligatorio (HSTS + preload).
- **En reposo:** Postgres native encryption + Supabase storage cifrado.
- **A nivel de columna** para sensibles: `pgcrypto` con clave por tenant en KMS.

### 5.3 Retención

| Dato | Retención |
|---|---|
| Candidatos no contratados | 12 meses (configurable, base legal LATAM) |
| Resultados psicométricos | 6 meses post-decisión |
| Activity log | 365 días |
| Logs de aplicación | 30 días |
| Backups | 30 días |
| Datos de cliente cancelado | 90 días grace period → purga total |

### 5.4 Derechos del titular (LGPD Brasil / Ley 1581 Colombia / equivalentes LATAM)

- Endpoint `/api/me/data-export` (descarga JSON+PDF).
- Endpoint `/api/me/data-erasure` (borrado a request).
- Plazo respuesta: ≤ 15 días hábiles.
- Log de cada request en activity_log.

## 6. PII en LLMs

- **Redacción antes de logs:** `{"email": "<REDACTED>"}` en cualquier output que se loggee.
- **No fine-tuning con datos de cliente** sin opt-in explícito.
- **Provider DPAs (Data Processing Agreements):** Anthropic, OpenAI, Google ya tienen DPA estándar; archivar copia firmada.
- **Local LLM opcional** (Ollama / vLLM) para clientes Enterprise que no aceptan datos en cloud third-party.

## 7. Seguridad aplicación (OWASP Top 10)

| Riesgo | Mitigación |
|---|---|
| A01 Broken access control | RLS + middleware tenant + tests E2E |
| A02 Cryptographic failures | TLS 1.3, cifrado columna, no MD5/SHA1 |
| A03 Injection | SQLAlchemy params, Pydantic, no string interpolation en queries |
| A04 Insecure design | Threat modeling por feature, ADRs |
| A05 Security misconfiguration | Hardened Dockerfiles distroless, secrets fuera del repo |
| A06 Vulnerable components | Dependabot + Snyk + Trivy |
| A07 Identification & auth failures | MFA, rate limit login, lockout exponencial |
| A08 Software & data integrity | Cosign sign images, SBOM con syft |
| A09 Logging failures | Logs estructurados, retención, alertas Sentry |
| A10 SSRF | Allowlist de hosts en providers que aceptan URLs externas |

## 8. Compliance roadmap

| Norma | Aplicabilidad | Plan |
|---|---|---|
| **LGPD (Brasil)** | Si cliente brasileño | DPO + DPA + endpoints titular ya cubiertos |
| **LFPDPPP (México)** | Cliente MX | Aviso de privacidad + ARCO requests |
| **Habeas Data (Colombia, Perú, Argentina)** | Cliente respectivo | Endpoint exportación + borrado |
| **GDPR** | Cliente EU (futuro) | EU representative + base legal explícita |
| **SOC 2 Type I** | Mes 12+ | Vanta o Drata para evidence collection |
| **ISO 27001** | Año 2+ | Solo si Enterprise lo exige |

## 9. Auditoría

- **Activity log append-only** con hash chain (cada entrada incluye hash anterior → tampering detectable).
- **Acceso de soporte (Vector HR Tech staff)** requiere:
  - Justificación escrita.
  - Approval del cliente vía link único.
  - Token temporal (1 hora).
  - Todo loggeado con `actor_role='SuperAdmin'`.

## 10. Disclosure / responsible disclosure

- `SECURITY.md` en root del repo con email `security@vector-hr.tech`.
- Programa de bug bounty cuando alcancemos 100 clientes.
- SLA respuesta: 24h triage, fix crítico ≤ 7 días.

## 11. Incident response

Runbook en `docs/runbooks/incident-data-breach.md`:

1. **Contain** (revoke tokens, freeze tenant si aplica).
2. **Assess** (alcance, datos comprometidos).
3. **Notify**: cliente afectado en ≤ 72 h (LGPD) + autoridad si aplica.
4. **Remediate** (fix root cause + tests).
5. **Postmortem** público (sin PII) ≤ 14 días.

## 12. Auditoría continua de RLS (paranoid mode)

Job nightly que:
1. Crea 2 empresas dummy A, B con datos.
2. Con JWT de A intenta leer B → debe fallar.
3. Repite por cada tabla con `empresa_id`.
4. Si alguna pasa, **alarma Sev-1**.

## 13. Hardening checklist por release

```
[ ] Headers HTTP: HSTS, CSP estricto, X-Frame-Options DENY, Referrer-Policy strict-origin
[ ] CSRF tokens en mutations sensibles (incluso con SameSite=strict)
[ ] CORS: allowlist explícita, no '*'
[ ] Cookies: HttpOnly + Secure + SameSite=Lax/Strict
[ ] Rate limit en /auth/* y /api/* públicos
[ ] WAF / Cloudflare Turnstile en endpoints públicos
[ ] No errores expuestos al cliente con stack traces
[ ] No info de versión/stack en headers
[ ] robots.txt + sitemap correctos (no leak de rutas internas)
```

---

*Siguiente: [09 · Project Plan](09_PROJECT_PLAN.md)*
