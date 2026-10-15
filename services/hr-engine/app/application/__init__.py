"""Capa de aplicación: los casos de uso.

Orquestan el dominio a través de sus puertos, sin saber qué base de datos ni qué
proveedor de LLM hay detrás. Solo dependen de la biblioteca estándar y del
dominio; lo comprueba `tests/unit/test_regla_de_dependencias.py`.

La idempotencia, el contexto de tenant, las transacciones y los reintentos no son
de aquí: los ponen los adaptadores de entrada (la tarea de Celery, los endpoints).
"""
