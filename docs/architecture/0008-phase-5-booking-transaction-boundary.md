# ADR 0008: Phase 5 booking transaction boundary

- Status: Accepted
- Date: 2026-08-03

## Context

Displayed availability is inherently stale and Telegram callbacks can be retried. Booking must
remain tenant- and identity-scoped while surviving restarts and concurrent requests. The source
specification permits PostgreSQL exclusion constraints for single-capacity resources and
transaction locks/counting for pooled capacity.

## Decision

Availability is a pure application calculation over a bounded persistence snapshot: active
service duration/buffer, eligible active resources, their schedules/overrides, blackout periods,
confirmed bookings, and unexpired holds. It emits tenant-local presentation fields and UTC
instants in deterministic order.

Drafts and holds are separate durable tenant-owned records. PostgreSQL advisory transaction locks
serialize one identity's active draft and each contended resource. Hold creation re-reads
availability after acquiring the resource lock. Confirmation locks the draft and hold, verifies
expiry/contact/policy, creates or updates the appointment and status history, consumes the hold,
and commits once. The existing GiST exclusion constraint is the final single-capacity confirmed
appointment guard. Idempotency keys and the consumed hold/draft relationship make retries return
the committed result.

Northstar represents capacity as two individually reservable one-capacity service bays. The pure
engine can project pooled counts, but the Phase 5 persistence path deliberately does not claim
general pooled multi-unit allocation or workforce scheduling.

Cancellation is idempotent and cutoff-controlled. Rescheduling first obtains a separate validated
hold; one transaction moves the existing appointment and appends
`confirmed -> reschedule_pending -> confirmed`. Failure rolls the entire change back, leaving the
original appointment valid.

## Consequences

No in-memory lock, Telegram ID, callback payload, or displayed slot is authority. Callbacks remain
signed, expiring, tenant-bound, and free of contact data. Name/phone/note values are never logged;
only the minimum validated fields are stored in draft and immutable booking snapshots. Manual
expiry is available now. Background expiry, outbox delivery, manager notifications, external
calendar sync, pooled capacity allocation, and workforce management remain deferred.
