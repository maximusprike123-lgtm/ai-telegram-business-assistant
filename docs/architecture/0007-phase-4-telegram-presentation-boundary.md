# ADR 0007: Phase 4 Telegram presentation and update boundary

- Status: Accepted
- Date: 2026-08-03

## Context

Phase 4 exposes the existing deterministic profile, catalog, and schedule queries through
Telegram. Telegram updates are untrusted, may be delivered more than once or concurrently, and
contain customer-controlled text. The Phase 2 `messages` table cannot reserve an update before a
conversation exists and does not model processing ownership, failure, or stale-claim recovery.

## Decision

- aiogram is confined to `presentation/telegram` and the Phase 4 composition root. Handlers call
  presentation orchestration over existing application use cases; they never access SQLAlchemy,
  repositories, or ORM rows.
- One bot credential is bound at startup to one server-configured tenant UUID and bot ID. The bot
  ID must match the token. Clients cannot select tenant scope. Webhooks require both a constant-time
  compared secret header and configured opaque path; an authenticated unknown path is distinct
  from failed authentication.
- Add `telegram_updates` as a metadata-only durable processing ledger, unique by tenant, bot, and
  update ID. Claims are first, active duplicate, completed duplicate, failed retry, or stale retry.
  Failed processing remains retryable. Terminal rows have a seven-day default retention and an
  explicit manual cleanup operation until a later worker phase owns scheduling.
- Telegram identity resolution uses a PostgreSQL transaction and per-identity advisory lock. It
  stores only numeric external user/chat identifiers and opaque internal customer/conversation
  IDs. Names, usernames, message bodies, and raw update payloads are not copied or logged.
- Callback data is a bounded, versioned, tenant-bound HMAC token containing only an allowlisted
  action, optional opaque UUID, and expiry. Read navigation is safe when repeated. Expired,
  malformed, cross-tenant, inactive-entity, and unsupported actions recover to a fresh menu.
- Northstar Telegram output is English only. Unsupported Telegram locale hints resolve through the
  existing generic locale policy to English. There is no language selector or `/language` route.
- Production uses webhook delivery. Polling is an explicit local-development command, deletes any
  registered webhook without dropping pending updates, and cannot run in production. Imports and
  ordinary application construction do not start polling or call Telegram.
- Structured Telegram logs use an allowlist of correlation, tenant, bot, update, event type,
  result, and safe error code/type fields. Exception text, messages, payloads, profiles, and
  credentials are never formatted into these records.

## Consequences

The API can acknowledge completed or duplicate updates and return a retryable 503 after a failed
processing attempt. A crash after Telegram accepts an outbound message but before the ledger is
marked complete can still cause a repeated informational response; Telegram offers no idempotency
key for `sendMessage`. Transactional outbound intents and delivery reconciliation belong to the
Phase 10 outbox, not this baseline. No booking, lead, handoff case, AI, Redis, Celery, or appointment
state is introduced.
