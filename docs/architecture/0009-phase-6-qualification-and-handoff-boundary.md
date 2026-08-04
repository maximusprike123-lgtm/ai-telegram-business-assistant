# ADR 0009: Phase 6 qualification and human-handoff boundary

- Status: Accepted
- Date: 2026-08-04

## Context

Qualification must survive restarts, validate every answer, preserve an explicit consent decision,
and create a scored lead without depending on Telegram FSM or an LLM. Human escalation must remain
available when AI is absent, pause automated replies, calculate a realistic response deadline, and
support authorized staff lifecycle actions.

## Decision

- Store immutable tenant-owned schema versions with typed field definitions, validation, score
  rules, handoff triggers, consent purpose/version, grade bands, and policy timing. Exactly one
  active published version exists per tenant and schema code; draft creation and publishing use
  protected application use cases.
- Persist qualification sessions, answers, current edit target, expiry, consent decision, and
  processed update keys in PostgreSQL. A partial unique index permits one active session per
  tenant/customer/conversation. Telegram FSM remains disabled.
- Parse and validate all ten supported field types in a pure application policy. Invalid input
  produces deterministic correction copy. Scoring is capped to 0–100 and records the grade and
  matched configured rule codes. No AI score is accepted.
- Completion atomically creates or updates an eligible open lead, stores the schema/version answer
  snapshot and timestamp, closes the session, and enqueues an idempotent outbox event. Configured
  safety triggers create a linked handoff in the same transaction.
- Explicit human and unsupported-request routes create or reuse one open conversation handoff.
  Due time consumes only effective intervals from the existing tenant-local schedule engine.
- A queued, claimed, or reopened handoff pauses bot workflow replies. Claim, resolve, reopen, and
  return-control actions require application-layer RBAC and append durable audit events.
- Phase 6 writes PII-minimized notification intents to the existing outbox. Phase 10 still owns
  recipients, delivery, retries, and worker scheduling.

## Consequences

The complete structured lead and handoff flow works without AI and does not retain Telegram message
bodies. JSONB is limited to versioned schema definitions, typed answers/snapshots, matched-rule
context, and safe event payloads. Real privacy wording, lawful basis, retention periods, escalation
recipients, and emergency language require operator approval before deployment.
