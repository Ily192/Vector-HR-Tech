# 10 · Risk Register

> Riesgos vivos. Revisar al cierre de cada cycle.

## Escala

- **Probabilidad (P):** 1 (muy baja) – 5 (muy alta)
- **Impacto (I):** 1 (cosmético) – 5 (proyecto en peligro)
- **Score = P × I.** Acción obligatoria si Score ≥ 12.

## Registro

| ID | Riesgo | P | I | Score | Owner | Mitigación | Estado |
|----|---|---|---|---|---|---|---|
| R-01 | Breaking change upstream Paperclip o OpenClaw rompe builds | 3 | 4 | 12 | Ilyra | Pin tag + tests CI + fork si necesario; ADR-009 define vendoring | Activo |
| R-02 | Costo de tokens IA explota con primer cliente activo | 3 | 4 | 12 | Ilyra | Hard-stops en Paperclip por tenant + alerta Sentry > 80% budget | Activo |
| R-03 | RLS mal configurada → leak entre tenants | 2 | 5 | 10 | Ilyra | Tests RLS por tabla + nightly paranoid job + middleware tenant_guard | Activo |
| R-04 | No conseguimos cliente piloto pagado en mes 3 | 3 | 4 | 12 | Ilyra | Siete (consultora propia) sirve como cliente alfa permanente; case study self-served | Activo |
| R-05 | WhatsApp Business API setup más complejo / caro de lo previsto | 3 | 3 | 9 | Ilyra | Empezar con Google Chat + Telegram (gratis); WA solo en Scale+ | Activo |
| R-06 | Dependencia Supabase down → producto down | 2 | 5 | 10 | Ilyra | Status page de Supabase monitoreado; failover plan en runbook (Postgres self-host como Plan B Enterprise) | Activo |
| R-07 | Solo 1 dev → bus factor 1 | 4 | 5 | 20 | Ilyra | Documentación obsesiva; ADRs; vibe coding como "otro dev"; hire en mes 4-6 si MRR lo justifica | **Crítico** |
| R-08 | Eval drift: skills funcionan en dev, fallan en producción con datos reales | 3 | 4 | 12 | Ilyra | Eval suite contra outputs reales semanal + alerta drift detection | Activo |
| R-09 | Competidor LATAM lanza producto similar | 2 | 3 | 6 | Ilyra | Velocidad de iteración + open-core como moat; community building | Monitor |
| R-10 | Regulación LGPD/Habeas Data → multa | 2 | 5 | 10 | Ilyra | Endpoints titular + retención + DPA con providers; abogado mes 6 | Activo |
| R-11 | Cliente alfa cambia de opinión → pierdes feedback loop | 2 | 4 | 8 | Ilyra | Múltiples consultoras HR como advisors; LinkedIn outbound desde cycle 1 | Activo |
| R-12 | Vibe coding produce código sin review humano que rompe en prod | 3 | 4 | 12 | Ilyra | DoD obligatorio (tests + reviewer) + code-review agent gating | Activo |
| R-13 | Pricing demasiado alto/bajo → nadie compra o churn | 3 | 4 | 12 | Ilyra | Pricing piloto $0 → trial 30 días → conversión gradual; A/B en landing | Activo |
| R-14 | OpenAI / Anthropic suben precio o cambian condiciones | 2 | 3 | 6 | Ilyra | Multi-provider (OpenAI + Gemini + Claude); abstraction en `providers/` | Activo |
| R-15 | Burnout (1 dev FT + producto + sales + soporte) | 4 | 4 | 16 | Ilyra | Cooldown semana respetada; soporte automatizado; horario fijo | **Crítico** |
| R-16 | Ataque DDoS al career-site público | 2 | 3 | 6 | Ilyra | Cloudflare proxy + rate limit + Turnstile en forms | Activo |
| R-17 | Costo Coolify/VPS escala mal con tenants | 2 | 3 | 6 | Ilyra | Workers compartidos multi-tenant; aislamiento por queue por tenant Pro+ | Activo |
| R-18 | Tipografía Proxima Nova requiere licencia → costo o conflicto | 2 | 2 | 4 | Ilyra | Fallback Inter / Geist (gratis) listo en design tokens | Activo |
| R-19 | Cliente Enterprise exige on-prem air-gap → 2 meses de dev | 2 | 4 | 8 | Ilyra | Helm chart + air-gap solo si cliente paga setup fee $20k+ | Monitor |
| R-20 | Cambio en Supabase pricing rompe unit economics | 2 | 3 | 6 | Ilyra | Postgres self-host documentado como migration path | Monitor |

## Top 3 a vigilar (Score ≥ 16)

1. **R-07 Bus factor 1** → la mitigación principal es documentar todo y publicar el repo abierto. Si Ilyra desaparece, el repo + docs deben permitir a otra persona continuar.
2. **R-15 Burnout** → respetar cooldown, usar Claude para automatizar soporte tier-1 (FAQ bot), evitar trabajar fines de semana.
3. **R-12 Vibe coding sin review** → Code-review agent gating + DoD estricto. Documentado en doc 11.

## Riesgos cerrados / no aplica

(Ninguno aún. Se mueven aquí cuando expiran.)

## Cadencia de revisión

- **Cada cooldown** (cada 3 semanas).
- **Inmediatamente** si ocurre un evento Sev-1 / Sev-2.
- **Cierre Q1, Q2, Q3, Q4:** review completa.

---

*Siguiente: [11 · Quality Gates](11_QUALITY_GATES.md)*
