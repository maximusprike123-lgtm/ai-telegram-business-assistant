# ADR 0012: Phase 9 privacy, retention, and anonymization

- Status: Accepted
- Date: 2026-08-05

## Context

The application stores several data classes with different purposes and lifecycle obligations.
Deleting all tenant data uniformly would break booking history, audit accountability, and active
workflows. Retaining everything indefinitely would contradict data minimization. The original
roadmap also associated Phase 9 with conversation memory, but the approved Phase 9 scope is
privacy, retention, and compliance only and explicitly excludes new AI behavior and workers.

## Decision

- Define a stable application-layer classification catalog for operational metadata, message
  content, customer contact, workflow records, knowledge, audit/security records, and AI telemetry.
- Store one versioned retention policy per tenant. Policy changes use optimistic concurrency and
  owner authorization. Environment values are bounded provisioning defaults; tenant policy is the
  runtime authority.
- Execute retention only through an authenticated, tenant-derived application port. The synchronous
  API provides a read-only preview and requires an explicit confirmation plus an idempotency key
  for execution. Scheduling remains deferred because Phase 9 excludes background workers.
- Anonymize customer contact and personal workflow payloads while retaining opaque identifiers,
  booking facts/status history, consent receipts, and audit records. Customer anonymization closes
  active conversations, cancels active drafts/qualification/handoffs, and releases active holds so
  erased contact data is not left in a live workflow.
- Automatic contact anonymization is conservative: a stale customer is eligible only when no open
  conversation, booking, lead, qualification, or handoff remains. Operators use the explicit
  customer workflow for approved erasure requests that must also terminate active work.
- Hard-delete only class-specific records that are safely disposable: expired message records,
  terminal Telegram update metadata, old AI telemetry, and expired archived knowledge with its
  chunks. Published/ready knowledge, audit events, booking lifecycle records, active workflows,
  and pending outbox events are never deleted by this phase.
- Persist completed destructive actions with tenant scope, policy version, reason code, safe counts,
  actor, timestamp, and idempotency key. Append a separate immutable audit event; operational logs
  remain allowlisted and never contain customer fields or deleted values.

## Consequences

Retention execution is deterministic, reviewable, retry-safe, and cannot select another tenant.
Historical business facts and audit accountability survive anonymization without retaining contact
details or free-form customer payloads. The portfolio defaults are examples, not legal advice or a
claim of regulatory compliance. A qualified owner must approve purposes, periods, deletion/export
rights, legal holds, backup handling, and regional requirements before real deployment.

Large deployments still need the Phase 10/11 scheduling, monitoring, legal-hold, export, backup
expiry, and operational approval processes. Creating a new tenant must atomically provision its
retention policy; the current fictional seed does so explicitly.
