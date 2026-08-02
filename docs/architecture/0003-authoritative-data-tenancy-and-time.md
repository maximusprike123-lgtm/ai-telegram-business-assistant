# ADR 0003: Authoritative data, tenancy, and time

- Status: Accepted
- Date: 2026-08-02

## Context

Bookings, customer data, knowledge lineage, and handoffs require durable correctness. The MVP is
a single fictional business but must grow to multiple tenants without a domain redesign.

## Decision

- PostgreSQL is authoritative for business records, audit records, and transactional events.
- Use pgvector behind a vector-search port so vectors, source metadata, publication state, and
  tenant scope remain transactionally close for MVP.
- Redis is never authoritative. It may accelerate sessions, rate limits, callback tokens, cache,
  and coordination.
- Persist a transactional outbox in the same database transaction as consequential domain
  changes. Workers deliver notifications and analytics with retry and idempotency after commit.
- Every business-owned record, repository query, cache key, task payload, vector metadata, event,
  audit record, and metric carries tenant context. Tenant scope is derived from authenticated or
  channel context, never trusted from an arbitrary request body.
- Use UUID identifiers internally and separate human-facing references.
- Store instants as timezone-aware UTC. Apply IANA tenant timezones at input, scheduling, policy,
  and presentation boundaries; never expose raw UTC appointment times to customers.
- Database constraints and transactions enforce booking conflicts and idempotency. Cache locks
  may reduce contention but cannot establish correctness.

## Consequences

- Phase 2 repositories must require explicit `tenant_id` and prove cross-tenant isolation.
- PostgreSQL migrations must include deliberate foreign-key, uniqueness, and delete behavior.
- Outbox and pgvector implementation details can change behind application ports.
- DST and local-date ambiguity are boundary test obligations, not reasons to store local naive
  timestamps.
