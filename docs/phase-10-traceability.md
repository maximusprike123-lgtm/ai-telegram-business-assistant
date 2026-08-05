# Phase 10 completion traceability

| Phase 10 contract | Implementation and verification anchor |
|---|---|
| Background workers | Celery worker/beat composition with explicit queues, UTC, late acknowledgement, and prefetch one |
| Transactional outbox | Locked bounded projection transaction; unique tenant/event/subscription delivery key |
| Retry policy | Deterministic bounded exponential delay and safe retryable/permanent failure classification |
| Dead letters | Durable terminal state and safe error code for invalid payloads, permanent failures, and exhaustion |
| Scheduled jobs | Beat entries for outbox, notifications, hold expiry, retention, and knowledge re-indexing |
| Notifications | Tenant-owned Telegram staff subscriptions and allowlisted booking/lead/handoff templates |
| Hold expiration | Existing Phase 5 `SKIP LOCKED` expiry transaction invoked by maintenance queue |
| Retention scheduling | Existing idempotent Phase 9 execution; tenant policy must explicitly opt in |
| Re-index scheduling | Existing embedding provider abstraction; tenant/checksum-guarded vector replacement |
| Monitoring | Tenant-scoped backlog/dead-letter/oldest-due/last-success API plus metadata-only worker runs |
| Tenant isolation | Principal-derived subscription/health scope, tenant predicates, composite FK, integration tests |
| Migration | Reversible `0009_phase10` delivery tables, outbox lease metadata, and retention opt-in |

Explicitly deferred: analytics projections, dead-letter replay API, quiet hours, alternative
notification providers, background ingestion, agents, MCP, LangGraph,
billing, dashboards, and CRM.
