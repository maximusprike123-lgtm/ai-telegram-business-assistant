# Architecture decision index

| ADR | Status | Decision |
|---|---|---|
| [0001](0001-phase-1-domain-foundation.md) | Accepted | Phase 1 domain representation and ports |
| [0002](0002-modular-monolith-and-delivery-boundaries.md) | Accepted | Modular monolith, Clean Architecture, webhook production delivery |
| [0003](0003-authoritative-data-tenancy-and-time.md) | Accepted | PostgreSQL/pgvector, outbox, tenant scope, UTC/timezone rules |
| [0004](0004-privacy-logging-and-secret-policy.md) | Accepted | Data minimization, safe logs, audit separation, runtime secrets |
| [0005](0005-phase-2-persistence-boundary.md) | Accepted | Async persistence mappings, migrations, tenant constraints, and seed scope |
| [0006](0006-phase-3-query-and-internal-api-boundary.md) | Accepted | Public profile, deterministic queries/schedules, protected internal API |
| [0007](0007-phase-4-telegram-presentation-boundary.md) | Accepted | Telegram adapter, trusted binding, durable update lifecycle, identity, callbacks, and delivery modes |
| [0008](0008-phase-5-booking-transaction-boundary.md) | Accepted | Availability inputs, durable holds/drafts, PostgreSQL contention control, and identity-owned lifecycle |
