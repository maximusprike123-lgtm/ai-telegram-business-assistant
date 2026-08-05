# Phase 10 background delivery runbook

## Enable and run

Migrate first. Configure `CELERY_ENABLED=true` and `CELERY_BROKER_URL`; result storage is optional
and disabled by default. Start independent worker and scheduler processes:

```bash
business-assistant-worker
business-assistant-beat
```

Queues are `default`, `notifications`, `maintenance`, and `knowledge`. Outbox dispatch, hold
expiration, and opted-in retention require no Telegram provider. External notifications require
`NOTIFICATION_DELIVERY_ENABLED=true` plus the existing complete Telegram configuration. Knowledge
re-indexing runs only when RAG and its embedding provider are enabled.

## Subscription and monitoring API

Owner and manager roles may use:

- `POST /api/v1/notifications/subscriptions`
- `GET /api/v1/notifications/subscriptions`
- `GET /api/v1/workers/health`

Subscriptions accept a numeric Telegram staff chat ID and one or more supported event types:
`booking.confirmed`, `booking.cancelled`, `booking.rescheduled`, `lead.qualified`, and
`handoff.queued`. Northstar seeds no recipient. Never place customer contact data in recipient
identifiers or operational tickets.

Worker health reports tenant-scoped pending outbox, pending/processing notifications, dead-letter
count, oldest due item, and last successful delivery. `worker_runs` contains global metadata only:
task name, status, count, safe code, and timestamps.

## Failure handling

Retryable network/rate failures are rescheduled with bounded deterministic backoff. Forbidden or
bad requests, invalid event payloads, and exhausted attempts become dead letters. Investigate bot
access, recipient validity, and the event producer before replay. Phase 10 intentionally exposes no
bulk or automatic replay command.

Telegram delivery is at-least-once. A crash after Telegram accepts a message but before PostgreSQL
records success can cause a duplicate. The durable outbox favors recovery over silent loss.

## Scheduled privacy and knowledge work

Retention stays disabled until an owner sets `automatic_execution_enabled=true` on the tenant
retention policy. The worker uses one idempotency key per policy version and UTC date. Legal holds,
backups, and approved real-business policy remain human responsibilities.

Changing the configured embedding model or dimensions makes mismatched safe chunks eligible for
re-index. Updates require the same tenant, chunk ID, and checksum, preventing stale replacement.
