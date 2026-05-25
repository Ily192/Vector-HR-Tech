# ADR-007: pgvector en Supabase, no Pinecone

- **Status:** Accepted
- **Date:** 2026-05-08
- **Tags:** infrastructure, cost, vector-search

## Context

Necesitamos vector search para matching CV ↔ vacante e ICP ↔ contactos.

## Decision

Usar **pgvector** dentro del Postgres de Supabase. Índice HNSW.

## Consequences

**Positivas:**
- Cero infraestructura adicional (ya tenemos Postgres).
- Joins SQL nativos entre vectors + metadata + RLS — Pinecone obliga 2 round trips.
- Costo $0 marginal hasta ~10M vectores.
- Self-hostable trivialmente.
- pgvector 0.7+ con HNSW está al nivel de performance de Pinecone para nuestra escala.

**Negativas:**
- A escala extrema (>50M vectores) Pinecone gana en latencia. Para entonces, ya tenemos revenue para reconsiderar.

## Alternatives considered

| Alternativa | Por qué descartada |
|---|---|
| Pinecone | $70/mes mínimo, lock-in, no joins con metadata |
| Weaviate | Operacionalmente más complejo |
| Qdrant self-host | Otro servicio que mantener |
| Milvus | Overkill para nuestra escala |
