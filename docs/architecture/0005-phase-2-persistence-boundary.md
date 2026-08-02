# ADR 0005: Phase 2 persistence boundary

- Status: Accepted
- Date: 2026-08-02

## Context

Phase 2 must make PostgreSQL authoritative without allowing SQLAlchemy types to cross Clean
Architecture boundaries. Tenant isolation, booking correctness, idempotency, UTC storage, and
outbox atomicity need database enforcement as well as application checks.

## Decision

- Use SQLAlchemy 2.x async sessions with asyncpg. Repositories translate between persistence rows
  and domain aggregates; an ORM row is never a repository result.
- Every owned repository operation requires `TenantId` and adds `tenant_id` to its predicate.
  Composite `(tenant_id, id)` foreign keys prevent cross-tenant relationships.
- A unit of work owns exactly one session and transaction. Repository `add` operations flush but
  never commit; successful application code calls `commit` once, otherwise exit rolls back.
- Alembic owns a static initial revision. It creates `vector` and `btree_gist`, but downgrade
  preserves these shared extensions while removing application tables.
- Assigned-resource booking conflicts are enforced with a partial GiST exclusion constraint over
  `[start_at, end_at)`. Idempotency keys have tenant-scoped unique constraints.
- Knowledge chunks have tenant/document lineage, generated full-text search data, and a nullable,
  dimensionless pgvector column. Embedding dimensions and vector indexes wait for the Phase 8
  embedding contract and benchmarks.
- The initial schema maps Phase 1 aggregates and adds only necessary foundations for channel
  identity/message idempotency, resources, knowledge chunks, audit events, and the outbox.
- Northstar seeding is deterministic and idempotent, allowed only in local/development/test, and
  labels the tenant as fictional. Demo prices and durations are synthetic.

## Deferred

Qualification schema tables, slot holds, memory facts, FAQs, notification subscriptions, AI
operations, analytics projections, admin APIs, and outbox dispatch behavior belong to later
roadmap phases. No vector index is created before retrieval benchmarks establish the operator,
dimension, and workload.

## Consequences

Integration tests require real PostgreSQL with extension-creation permission; SQLite cannot prove
the required behavior. Persistence errors are translated to stable application errors. Domain and
application layers remain free of SQLAlchemy and asyncpg imports.
