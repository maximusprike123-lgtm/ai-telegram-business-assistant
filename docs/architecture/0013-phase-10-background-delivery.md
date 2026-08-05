# ADR 0013: Database-authoritative background delivery

- Status: Accepted
- Date: 2026-08-05

## Context

Phase 6 commits tenant-scoped, PII-minimized lead and handoff events to the transactional outbox.
Phase 5 provides a concurrency-safe hold-expiry operation, Phase 8 provides an embedding boundary,
and Phase 9 provides idempotent retention execution. Phase 10 must schedule these operations and
deliver staff notifications without making the broker authoritative or weakening tenant scope.

## Decision

Celery with Redis/AMQP-compatible broker URLs is a trigger and queue adapter only. PostgreSQL owns
outbox state, projection uniqueness, notification attempts, due times, processing leases,
dead-letter state, and worker-run telemetry. Workers use bounded batches and `FOR UPDATE SKIP
LOCKED`; stale leases are reclaimable.

Outbox projection and event publication happen in one database transaction. A unique tenant/event/
subscription key makes projection idempotent. External Telegram delivery is at-least-once: success
is recorded after the provider accepts the message, so a worker crash in that interval can produce
a duplicate. This limitation is preferred to silent loss and is exposed operationally.

Only application-owned templates render allowlisted event fields. Arbitrary payload content is
never forwarded. Retryable provider failures use bounded deterministic exponential backoff;
permanent failures and exhausted attempts become dead letters with safe error codes.

Tenant owners and managers configure staff subscriptions and read tenant-scoped worker health.
Automated retention is disabled per tenant until an owner explicitly opts in. Hold expiry reuses
the Phase 5 store, and knowledge re-indexing reuses the Phase 8 embedding port with tenant and
checksum guards.

## Consequences

- Worker processes may scale independently without changing domain/application dependencies.
- Broker loss delays work but does not lose authoritative delivery state.
- Notification delivery requires an enabled Telegram adapter; other scheduled tasks do not.
- There is no automatic dead-letter replay. Operators diagnose and remediate before a deliberate
  database repair or future protected replay use case.
- Phase 10 does not add analytics projections, agents, new AI behavior, billing, dashboards, or
  CRM integration.
