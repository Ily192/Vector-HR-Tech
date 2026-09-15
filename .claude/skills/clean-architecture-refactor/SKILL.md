---
name: clean-architecture-refactor
description: "Identifica código legacy donde la lógica de infraestructura está mezclada con la de negocio y propone o ejecuta un refactor hacia Clean Architecture: Domain (entidades e interfaces), Application (casos de uso) e Infrastructure (adaptadores). Úsala al diseñar la estructura de carpetas y clases de una funcionalidad nueva, al refactorizar un worker, endpoint o componente que mezcle acceso a datos, llamadas a proveedores y reglas de negocio, o cuando se pida separar capas, desacoplar o limpiar código obsoleto."
metadata:
  author: "Ilyra Rivas"
  source: "skills/clean-architecture-refactor"
---

# Refactor hacia Clean Architecture

Identifica código legacy y propone una estructura de carpetas y clases basada en Clean Architecture, tanto para refactorizar lo existente como para diseñar funcionalidades nuevas.

## Qué hace

Analiza el archivo o módulo seleccionado. Si detectas lógica de infraestructura mezclada con lógica de negocio, propón un refactor dividido en:

- **Domain** — entidades e interfaces (puertos). Reglas de negocio puras, sin imports de frameworks, ORM, SDKs ni colas.
- **Application** — casos de uso. Orquestan el dominio a través de los puertos; no saben qué base de datos ni qué proveedor hay detrás.
- **Infrastructure** — adaptadores. Implementan los puertos: repositorios SQL, clientes de LLM, colas, HTTP y los frameworks de entrada (endpoints, tareas).

Asegúrate de que no queden referencias rotas y elimina cualquier código marcado como obsoleto o redundante durante el proceso.

## Regla de dependencias

Las dependencias apuntan hacia adentro: Infrastructure → Application → Domain. Domain no importa nada de las otras dos. Un import que va en sentido contrario es el primer candidato a mover.

## Cómo se ejecuta

1. **Mapea las dependencias** del módulo: qué importa y quién lo importa.
2. **Clasifica cada responsabilidad** en una capa. Señales de mezcla: SQL crudo junto a reglas de negocio, llamadas a un SDK dentro de un caso de uso, decisiones de negocio dentro de un endpoint o de una tarea.
3. **Propón la estructura** de carpetas y clases antes de mover código, y espera confirmación si el cambio es grande.
4. **Refactoriza en pasos pequeños**, con los tests en verde después de cada paso. Los casos de uso se prueban con adaptadores falsos.
5. **Verifica** tests, typecheck y lint, y que no queden imports rotos ni código muerto.

## Reglas

- **Una regla de negocio vive en Domain, no en un prompt.** Si un umbral o una política decide algo sobre una persona o un cliente, tiene que ser código determinista y testeado; el modelo puede aportar el insumo, no la regla.
- **Los adaptadores de entrada son finos.** Un endpoint o una tarea de Celery traduce la petición, llama al caso de uso y traduce la respuesta. Nada más.
- **No se refactoriza todo a la vez.** Se empieza por el caso de uso más valioso y se usa como plantilla para los demás.
- **No se crea una abstracción sin un segundo uso previsible.**

## Mapa de referencia para este repo (Vortex Ops)

```
services/hr-engine/app/
├── domain/          entidades (Candidato, Vacante), políticas (NextStepPolicy), puertos
├── application/     casos de uso (EvaluateCandidate, SourceCandidates)
├── infrastructure/  repositorios SQLAlchemy, adaptadores Gemini/OpenAI, tareas Celery
└── api/             FastAPI como adaptador de entrada
```
