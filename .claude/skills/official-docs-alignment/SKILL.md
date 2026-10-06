---
name: official-docs-alignment
description: "Antes de refactorizar o implementar, consulta la documentación oficial vigente de la tecnología afectada, valida mejores prácticas y cambios de API, y justifica el código citando la sección oficial. Úsala siempre antes de escribir o modificar código en una refactorización o funcionalidad nueva, al actualizar dependencias o versiones, al elegir o cambiar un modelo de IA, o cuando haya dudas sobre la forma correcta de usar una librería del stack (Next.js, React, Vite, Tailwind, FastAPI, SQLAlchemy, Celery, Supabase, pgvector, Gemini, OpenAI, Vercel, Turborepo)."
metadata:
  author: "Ilyra Rivas"
  source: "skills/official-docs-alignment.md"
---

# Alineación con la documentación oficial

Actúa como un **Investigador Técnico**. Antes de escribir o modificar una sola línea de código en una refactorización o una funcionalidad nueva, completa estos cinco pasos y deja constancia de ellos en tu respuesta.

## 1. Identificar la tecnología

Detecta qué parte del stack técnico toca el cambio. En este repo (Vortex Ops) lo habitual es:

- **Frontends:** Next.js (App Router), React, Vite, Tailwind CSS, TanStack Query.
- **Backend:** FastAPI, SQLAlchemy async + asyncpg, Celery + Redis, Pydantic.
- **Datos:** Supabase (Postgres, RLS, Storage, Auth), pgvector.
- **IA:** SDK `google-genai` (Gemini) y `openai` (embeddings).
- **Plataforma:** Vercel, Turborepo, pnpm, GitHub Actions.

Mira la versión **instalada** en el lockfile (`pnpm-lock.yaml`, `uv.lock`) o en el manifiesto antes de buscar: la documentación que importa es la de esa versión, no la de la última.

## 2. Búsqueda activa

Localiza la documentación oficial más reciente con las herramientas de búsqueda. Solo cuentan fuentes oficiales: el sitio del proyecto, su repositorio, su changelog o sus guías de migración. No valen tutoriales de terceros ni blogs.

Si el paquete trae su propia documentación versionada (por ejemplo, Next.js 16.2+ la incluye en `node_modules/next/dist/docs/`), esa gana sobre la web porque coincide exactamente con lo instalado.

## 3. Validar mejores prácticas

Comprueba si hay patrones nuevos, optimizaciones, deprecaciones o cambios de API que afecten al cambio: breaking changes entre versiones mayores, fechas de fin de soporte, modelos de IA retirados, límites de la plataforma.

## 4. Justificar

Al proponer el código, cita en una línea qué parte de la documentación oficial lo respalda (URL y sección). Si no encontraste respaldo oficial, dilo; no lo rellenes con memoria.

## 5. Encajar en Clean Architecture

Asegúrate de que la implementación "oficial" se adapte a las capas Domain, Application e Infrastructure manteniendo el desacoplamiento. La librería vive en Infrastructure; el dominio no la conoce. Ver la skill `clean-architecture-refactor`.

## Reglas

- **La versión manda.** No cites documentación de una versión mayor distinta a la instalada sin decirlo.
- **Sin acceso, sin afirmación.** Si la página oficial no carga (403, muro de pago), dilo y marca la conclusión como no verificada.
- **Las noticias no son documentación.** Sirven para saber qué buscar en la fuente oficial, no como fuente.

## Por qué existe: casos reales de este repo

- Un motor async de SQLAlchemy compartido entre llamadas a `asyncio.run()` en tareas de Celery hacía fallar una de cada dos tareas. La documentación oficial lo advierte: `NullPool`, o `dispose()` antes de reutilizar el motor en otro event loop.
- La documentación del proyecto citaba `gemini-1.5-flash`, un modelo ya retirado, mientras el código usaba otro.
- Las noticias sobre la retirada de GPT-4o mezclaban modelos distintos; el aviso oficial solo retiraba un snapshot concreto.
