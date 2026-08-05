# ADR 0014: Provider-neutral, privacy-safe operational telemetry

- Status: Accepted
- Date: 2026-08-05

## Context

The API, Telegram adapter, AI runtime, retrieval path, PostgreSQL outbox, notification delivery,
and Celery workers need one diagnostic vocabulary. Telemetry must remain useful without turning
customer content, prompts, knowledge, contact data, identifiers, or credentials into another data
store. Optional integrations must not make a deliberately disabled feature fail readiness.

## Decision

Application-owned observability ports define bounded components, operations, outcomes, dependency
states, and health reports. Prometheus and structured logging are infrastructure adapters. Metric
labels are fixed enums; tenant, customer, conversation, event, task invocation, correlation, route
parameters, exception types, and error messages are never labels.

Correlation accepts an allowlisted caller value or creates one, travels in process-local context,
and is persisted with authoritative outbox, delivery, AI-operation, and worker-run metadata.
Application log events are constant codes with allowlisted scalar context. Arbitrary messages,
exception text, message bodies, prompts, outputs, retrieved chunks, and event payloads are rejected.

`/health/live` proves only that the process serves requests. `/health/ready` checks PostgreSQL and
pgvector plus enabled dependencies, returning only an aggregate state. Redis, Telegram, and AI are
reported as disabled and do not block readiness when their features are disabled. A protected
diagnostic endpoint exposes only bounded dependency status, requirement, latency, and safe code.
Prometheus output is disabled by default and requires a separate bearer token when enabled.

## Consequences

- Monitoring backends can change without entering domain or application policy.
- Operators can connect a request to durable work without logging business content.
- Readiness detects missing required capabilities but does not test external providers with live
  customer-facing calls.
- Prometheus aggregation is process-local; a production scraper must collect every API/worker
  replica. Dashboard provisioning and deployment infrastructure remain outside Phase 11.
