# Phase 11 observability and diagnostics runbook

## Endpoints and access

- `GET /health/live` is an unauthenticated process check. It must not query dependencies.
- `GET /health/ready` returns only `ready` or `not_ready`; HTTP 503 means a required dependency is
  unavailable.
- `GET /api/v1/operations/diagnostics` requires the internal API key and owner/manager permission.
  It returns bounded dependency names, states, required flags, latency, and safe error codes.
- `GET /metrics` is absent unless `METRICS_ENABLED=true`. When enabled, set a dedicated strong
  `METRICS_AUTH_TOKEN` and send `Authorization: Bearer <token>`. Do not reuse provider credentials.

PostgreSQL and pgvector are required. Redis, Telegram, and AI are non-blocking when disabled; once
enabled, incomplete/unavailable configuration is a readiness failure. Readiness does not send a
Telegram message or an AI request.

## Suggested SLIs and initial alerts

Use a rolling window appropriate to traffic; tune thresholds from observed production baselines.

- Availability: successful HTTP operations / all HTTP operations. Investigate sustained 5xx above
  1% for 10 minutes.
- Latency: HTTP and use-case duration histograms. Investigate p95 above the configured slow
  threshold for 15 minutes.
- Delivery reliability: notification successes / claimed deliveries. Alert on any dead letter and
  on retry outcomes sustained for 10 minutes.
- Pipeline freshness: pending outbox/notification backlog and oldest due time. Investigate backlog
  growth across three scrape intervals or work older than two scheduling intervals.
- Worker reliability: Celery failure outcomes. Alert on repeated failures for the same bounded task
  class; use `worker_runs` for safe timestamps and codes.
- AI/retrieval degradation: failure/degraded ratio. Investigate sustained degradation, but keep the
  deterministic fallback available.

Never add IDs, correlation values, exception names, tenant values, model input, or routes containing
IDs as metric labels. Correlation is for targeted metadata lookup, not aggregation.

## Triage

1. Check liveness, then readiness and the protected diagnostic report.
2. If PostgreSQL is unavailable, stop write traffic and restore database connectivity. If pgvector
   is missing, run the reviewed migration/bootstrap procedure; do not silently disable retrieval.
3. If Redis is unavailable while enabled, restore the broker and allow PostgreSQL-authoritative
   outbox work to resume. Do not mutate outbox rows to make a queue appear healthy.
4. For notification retries/dead letters, follow the Phase 10 runbook and inspect safe error codes.
5. Use the correlation value to join request logs to durable metadata. Never paste customer content,
   prompts, knowledge chunks, tokens, or raw Telegram updates into tickets.
6. Rotate the metrics token if exposure is suspected. Credentials never belong in logs or alerts.

Metrics are per process. Scrape every replica and aggregate in the monitoring system. Phase 11 does
not provision a dashboard, collector, alert destination, or deployment platform.
