# Phase 5 completion traceability

| Phase 5 contract | Implementation and verification anchor |
|---|---|
| Tenant-local availability | pure `application/bookings/engine.py`; hours, notice, horizon, duration/buffer, DST, deterministic-order unit tests |
| Resource eligibility/capacity | tenant-scoped resources, `service_resources`, blackout table, seeded one-capacity bays |
| Durable holds and drafts | migration 0004, identity/conversation FKs, expiry/status/index constraints, PostgreSQL adapter |
| Concurrent last slot | advisory resource transaction lock, availability re-read, real two-client PostgreSQL race test |
| Atomic/idempotent confirmation | locked hold/draft, unique idempotency/hold/reference constraints, one transaction, repeat test |
| Immutable facts and history | service/customer snapshots and ordered `draft -> held -> confirmed` history |
| Cancellation/rescheduling | cutoff policy, repeated cancellation, new-hold atomic reschedule, history and rollback semantics |
| Telegram flow | signed tenant-bound callbacks, persisted workflow, name/phone collection, review/confirm, distinct cancellation |
| Internal API | authenticated `/api/v1/availability`; identity mutations remain internal use cases rather than unsafe caller-supplied IDs |
| Manual expiry | bounded skip-locked cleanup plus read/confirm-time expiry enforcement |
| Privacy | no raw updates/message bodies, bounded minimum contact fields, masked phone review, retention limits documented |
| Architecture | application/domain framework independence and thin presentation tests remain green |

Deliberately deferred: pooled multi-unit allocation, full workforce scheduling, automatic cleanup,
outbox delivery and notifications, external calendars, AI, leads/handoff, Redis, Celery, payments,
admin UI, analytics, and Phase 6+ behavior.
