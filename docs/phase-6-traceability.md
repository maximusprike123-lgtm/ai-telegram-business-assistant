# Phase 6 completion traceability

| Phase 6 contract | Implementation and verification anchor |
|---|---|
| Versioned tenant schemas | Typed application models, protected draft/publish API, migration 0005, seeded Northstar v1 schema |
| Ten field types and validation | Pure qualification engine; valid/invalid parameterized unit tests |
| Consent accepted/declined | Durable decision, version, purpose, timestamp; decline-without-lead PostgreSQL test |
| Resumable session | PostgreSQL current field/answers/status/expiry, active-session uniqueness, persisted update keys |
| Review and individual correction | Telegram review with masked sensitive phone and per-field signed edit callbacks |
| Lead creation/update | Application completion use case, eligible-open-lead update, schema/version snapshot and timestamp |
| Deterministic score | Configured match rules, bounded score, grade, and matched-rule explanation |
| Automatic escalation | Unsafe vehicle, accident, fire, and fuel-leak rules create linked urgent handoffs atomically |
| Explicit/unsupported handoff | English Telegram routes create or reuse an open case without AI |
| Business-hours due time | Pure effective-schedule duration calculator with cross-day unit test |
| Staff lifecycle and bot pause | Protected list/claim/resolve/reopen/return API, audit events, paused Telegram routing |
| Notification idempotency boundary | Deterministic unique outbox IDs for qualified-lead and queued-handoff intents |
| Tenant isolation | Composite foreign keys, tenant predicates, identity scope, RBAC, and PostgreSQL tests |

Deferred: notification delivery/workers and recipient configuration (Phase 10), AI classification
and extraction (Phase 7), retrieval-grounded risk handling (Phase 8), and retention/anonymization
(Phase 9/11).
