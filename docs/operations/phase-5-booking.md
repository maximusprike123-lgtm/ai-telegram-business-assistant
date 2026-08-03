# Phase 5 availability and booking runbook

## Northstar demo policy

Northstar Auto Care is fictional and creates no real appointments. Its tenant-owned demo policy
uses Europe/Moscow local time, a 30-minute slot grid, 30-day horizon, two-hour minimum notice,
five-minute hold, 30-minute draft expiry, and 24-hour cancellation/rescheduling cutoff. Service
duration plus cleanup buffer must fit wholly inside one effective opening interval. Closed days,
breaks, replacing date overrides, DST gaps/overlaps, inactive records, resource blackout periods,
confirmed appointments, and unexpired holds remove capacity.

Two fictional service bays are eligible for all seeded services. Each bay is an independent
capacity unit. Slots are ordered by UTC instant and stable resource UUID; only one customer choice
is shown for an equivalent start instant.

## Lifecycle and guarantees

The Telegram flow is Book appointment -> service -> date -> time -> name -> phone -> review ->
explicit confirmation. A displayed time is not reserved. Selecting it creates a durable,
identity-scoped hold. `/cancel` releases only the active draft/hold and never cancels a confirmed
appointment. Confirmed cancellation has a separate confirmation screen. My appointment is scoped
to the resolved tenant/customer identity.

Hold creation and appointment confirmation use PostgreSQL advisory transaction locks and re-check
availability. Confirmation consumes one unexpired hold, persists a non-sequential `NSA-XXXXXXXX`
reference, immutable service/contact facts, and ordered status history in one commit. Retries return
the same appointment. Rescheduling consumes a new hold and updates the existing appointment
atomically; the old time remains valid if the transaction fails.

The protected internal API exposes `GET /api/v1/availability`. Identity-owned mutations remain
application use cases used by Telegram because the current internal operator API has no
customer-authentication credential; accepting a caller-supplied customer ID would violate the
identity boundary.

## Manual expiry

Background workers are excluded from this phase. Operators can run
`business-assistant-expire-holds` with the normal validated environment and database settings.
The command expires at most 500 rows per run with `FOR UPDATE SKIP LOCKED`; the application store
also exposes a bounded operation for controlled maintenance. Read and confirmation paths enforce
expiry even if cleanup has not run. Expired and released holds never block availability.

## Privacy and retention

Drafts store only service/date/hold linkage, a validated name, phone, and optional bounded note.
Telegram message bodies and raw updates are not stored. Logs must never include these contact
fields. Draft/hold retention cleanup and customer export/anonymization are Phase 9/11 work; until
then records remain audit-supporting database data. A real operator must approve lawful basis,
retention periods, privacy notice, and deletion policy before deployment.

## Known limits

- No pooled multi-unit allocation, employee rostering, external calendar, or overnight intervals.
- No background expiry, outbox delivery, customer/staff notification, or manager handoff.
- The static internal API is tenant-bound but not customer-authenticated, so mutations are not
  exposed there.
- Telegram supports one bot-to-tenant binding per process and English only.
