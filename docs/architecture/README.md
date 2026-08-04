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

## Decision records

The [ADR index](decisions.md) records binding baseline choices. Later phases may supersede an ADR
with another explicit record; they must not silently weaken tenant isolation, booking
correctness, consent, authorization, grounding, idempotency, auditability, or human control.
