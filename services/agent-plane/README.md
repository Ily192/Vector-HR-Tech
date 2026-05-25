# agent-plane

> **Cycle 1 · tarea 1.2 — OpenClaw runtime + adapter Google Chat.**
> TypeScript ESM strict. Vendored (no submódulo) — ver ADR-009.

Scaffold pendiente. El plan:

1. Copiar `openclaw-main` del Portafolio como base.
2. Reescribir adapters a TS ESM con tipos compartidos de `@vortex/types`.
3. Wire run-token (JWT 5 min de Paperclip) → toolgateway → `hr-engine`.
4. Adapter Google Chat primero (gratis), WhatsApp/Telegram en Cycle 2.

Por qué TS y no Python: el agent-plane es 90% I/O conversacional y necesita SDKs maduros de los proveedores de chat (Google Chat, WhatsApp Business via 360dialog/Twilio, Slack, Teams).

Hosting: **Fly.io** o **Railway** (no Vercel — necesita websockets persistentes y workers long-running). Ver ADR-012.

```
agent-plane/
  src/
    adapters/         google-chat, whatsapp, telegram, slack
    skills/           runner SKILL.md → tool calls
    run-tokens/       verify JWT emitidos por paperclip
    server.ts         Hono + WS endpoint
  package.json
  tsconfig.json
```
