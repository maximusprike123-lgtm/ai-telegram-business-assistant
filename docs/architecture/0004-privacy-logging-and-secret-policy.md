# ADR 0004: Privacy, logging, and secret policy

- Status: Accepted
- Date: 2026-08-02

## Context

The assistant will eventually handle contact details, conversation text, lead answers, bookings,
provider telemetry, and business documents. Operational visibility must not become uncontrolled
PII duplication, and the fictional demo must not imply universal compliance.

## Decision

- Minimize collection and require the configured notice/consent before contact or lead data is
  stored. Distinguish verified from unverified data and confirmed facts from inference.
- Structured logs contain safe identifiers, tenant/correlation context, component, result code,
  duration, and retry count. Raw messages, phone/email values, document text, full tool arguments,
  prompts, provider bodies, tokens, and secrets are excluded by default.
- Audit records are durable business/security records and are not replaced by operational logs.
  They store actor, action, target, result, correlation, timestamp, and a safe change summary.
- Secrets enter at runtime from local ignored files or an environment secret manager. They are
  never committed, returned in errors, copied to model prompts, or placed in tenant configuration.
- Retention classes and anonymization/export behavior remain configurable. A human/legal owner
  must approve purpose, lawful basis, regional requirements, retention, and high-risk wording
  before real deployment.
- Northstar Auto Care data is synthetic and clearly labeled fictional.

## Consequences

- Future telemetry and repository adapters require redaction and retention tests.
- Staff notifications contain minimal structured context, not transcript dumps.
- `.env.example` contains names and empty safe placeholders only; committed secret scanning runs
  locally and in CI.
- The repository makes no claim of universal regulatory compliance.
