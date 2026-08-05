# Architecture overview

## System shape

The system is a modular monolith with Clean Architecture boundaries. Telegram and HTTP are
presentation adapters. PostgreSQL, Redis, Celery, OpenAI, and notification providers are
infrastructure adapters. Application use cases coordinate work through ports. Domain models own
business invariants and do not know about frameworks or providers.

```text
Telegram / HTTP
       |
 presentation
       |
 application <---- infrastructure adapters
       |
    domain
```

The deployment may scale stateless API and worker processes independently without changing the
domain model. Cross-module work goes through application use cases and ports; there is no generic
`utils` layer and no adapter-to-adapter business coupling.

## Consequential operation path

Future booking, consent, contact, lead, and handoff operations follow this boundary:

```text
untrusted input or AI output
  -> validated presentation schema
  -> authorized application use case
  -> domain policy/state transition
  -> atomic database transaction + outbox
  -> post-commit delivery worker
```

No generated AI text is an authoritative operation result. Customer-facing claims will be
assembled only from successful application results and validated evidence.

Phase 6 qualification and handoff follow the same path without an AI adapter: versioned schema
input is deterministically validated and scored, consequential state is committed atomically, and
Telegram renders only the resulting application state. Active handoff state is checked before bot
workflow routing.

Phase 7 adds an optional provider-neutral runtime behind application ports. Its pipeline is strict
provider schema validation, application allowlists, a task business validator, confidence policy,
and only then an advisory result. Telegram accepts four read-only advisory routes; every failure
or other intent returns to deterministic behavior. AI operation telemetry is metadata-only, and
no tool-calling surface exists in this phase.

Phase 8 adds `application.knowledge` policies and ports. Infrastructure performs embedding and
tenant-filtered PostgreSQL lexical/vector search, while the application owns deterministic
chunking, evidence thresholds, citations, extractive answers, and fallback. Retrieved content is
untrusted and cannot mutate workflows or bypass publication and tenant filters.

Phase 9 adds `application.privacy` classifications, authorization, confirmation, retention policy,
and idempotency boundaries. PostgreSQL performs tenant-filtered anonymization and deletion behind a
port. Booking/audit history and active records are preserved according to policy; the API never
accepts tenant scope or deletion targets outside the authenticated application command.

Phase 10 adds `application.background` delivery policy and ports. Celery schedules work, while
PostgreSQL remains authoritative for outbox projection, notification leases/retries/dead letters,
and operational status. Scheduled jobs reuse existing booking, privacy, knowledge, and provider
boundaries rather than moving business rules into tasks.

## Decision records

The [ADR index](decisions.md) records binding baseline choices. Later phases may supersede an ADR
with another explicit record; they must not silently weaken tenant isolation, booking
correctness, consent, authorization, grounding, idempotency, auditability, or human control.
