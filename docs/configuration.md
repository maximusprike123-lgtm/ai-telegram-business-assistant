# Environment and configuration baseline

`.env.example` is a safe inventory, not a committed runtime configuration. The composition root loads an
immutable `RuntimeSettings` object once at the composition boundary. Domain entities and
application use cases never read process environment variables. Phase 2 Alembic and seed commands
read `DATABASE_URL`; integration tests read `TEST_DATABASE_URL`.

## Configuration layers

The specification defines four layers, in precedence order:

1. Safe static application defaults.
2. Environment-specific runtime variables.
3. Versioned tenant configuration in PostgreSQL.
4. Feature flags with explicit defaults.

Tenant business policy does not belong in environment variables. Runtime connectivity and
secrets do not belong in tenant configuration.

## Variable ownership

| Group | Examples | Intended owner |
|---|---|---|
| Application | `APP_ENV`, `PUBLIC_BASE_URL` | deployment configuration |
| Demo defaults | tenant slug, timezone, locales | local bootstrap only |
| Telegram | bot and webhook secrets | secret manager/runtime |
| Data services | database, Redis, Celery URLs | deployment/secret manager |
| AI policy | provider key, task models, budgets | secret manager + versioned policy |
| Cryptography | signing and encryption keys | secret manager only |
| Telemetry | log format, OTLP endpoint | deployment configuration |
| Controls | upload, retention, rate limits | environment defaults, then tenant policy |
| Admin bootstrap | local operator token | local demo only |

## Implemented groups through Phase 12

The loader validates application identity and public URL, PostgreSQL connectivity and bounded
pool settings, internal API bind/timeout settings, tenant-bound API credentials, Telegram,
Redis, Celery and OpenAI enablement, observability, and feature switches. An integration's
credential or URL is required only when that integration is enabled. Telegram and the optional AI
runtime, Phase 8 retrieval, Celery, and notification delivery are implemented but disabled by
default. Redis is used only as non-authoritative broker transport when selected.

Enabled Telegram requires a token, matching numeric bot ID, tenant UUID, callback signing key, and
one delivery mode. Webhook mode additionally requires a public base URL plus independent header and
path secrets limited to Telegram-safe ASCII characters. Polling mode is local-development only.
Payload size, callback version/expiry, terminal-row retention, and stale-processing reclaim time are
bounded. `TELEGRAM_POLLING_ENABLED` is accepted only as a deprecated compatibility input; new
configuration must use `TELEGRAM_DELIVERY_MODE` and cannot select both modes.

Signing/encryption/metrics/admin secrets are optional until their owning feature is used but are
still checked for production strength when supplied. Celery results have an independent switch;
an enabled result policy requires its backend. Enabled AI requires an installed provider, explicit
router and response models, and that provider's credentials. Enabled RAG additionally requires an
embedding model and bounded dimensions. Upload, retention, rate, AI retry/output, logging, and
database limits are bounded at startup.
Production rejects message-text logging and the local-only admin bootstrap token.

Phase 5 booking policy is tenant-owned PostgreSQL data, not environment configuration. Northstar's
fictional defaults are a 30-minute slot interval, 30-day horizon, two-hour minimum notice,
five-minute hold, 30-minute draft expiry, and 24-hour cancellation/rescheduling cutoff. Customer
name, phone, and optional-note lengths are also bounded in that record. Real deployments must
replace and approve these values; `.env.example` does not duplicate them.

The protected API requires `INTERNAL_API_ENABLED=true`, a non-empty compatibility
`INTERNAL_API_KEY`, a UUID
`INTERNAL_API_TENANT_ID`, and a supported `INTERNAL_API_ROLE`. The credential resolves exactly
one trusted principal and tenant; `X-Tenant-ID`, when sent as a defense-in-depth assertion, must
match that tenant. This static adapter is intentionally replaceable and is not a user directory,
OAuth server or complete SaaS identity provider. Phase 12 additionally accepts database-backed
tenant credentials issued through the administration API; the static credential remains a
deployment compatibility fallback and must not be used as a global tenant selector.

## Phase 12 tenant administration

`ADMIN_BOOTSTRAP_TOKEN` enables only the initial provisioning endpoint in local, development, and
test environments and is rejected in production. Normal administration uses database-backed,
tenant-bound credentials. Tenant lifecycle, member roles, entitlements, and retention automation
are PostgreSQL-owned configuration; environment values cannot override them.

New tenants begin suspended. Provisioning creates safe English-only profile/schedule defaults and
disabled capabilities unless explicitly enabled. `automatic_retention` maps to the existing
retention policy rather than creating a second authority. Northstar creates demo membership and
enabled product capabilities without creating or committing a credential.

## Phase 7 AI runtime

`AI_ENABLED=false` is the authoritative global kill switch. When enabled, `AI_PROVIDER` selects an
installed infrastructure adapter; Phase 7 ships `openai`. `AI_ROUTER_MODEL` owns intent,
extraction, and classification tasks, while `AI_RESPONSE_MODEL` owns rewrite and summary tasks.
Model names are deployment policy and have no application-layer defaults.

`AI_TIMEOUT_SECONDS`, `AI_MAX_RETRIES`, `AI_CONFIDENCE_THRESHOLD`, `AI_MAX_OUTPUT_TOKENS`, and
`AI_STRUCTURED_OUTPUT_MODE=strict_json_schema` bound execution. Per-million-token input/output
rates are optional operator-supplied cost estimates; zero means cost is not estimated. The OpenAI
adapter additionally requires `OPENAI_API_KEY` and accepts an HTTPS `OPENAI_BASE_URL`. The adapter
uses strict structured responses and does not enable provider tools.

`FEATURE_AI_ENABLED`, `OPENAI_ROUTER_MODEL`, and `OPENAI_RESPONSE_MODEL` remain deprecated input
aliases. Conflicting kill-switch values fail startup. `AI_MAX_TOOL_ITERATIONS` is retained only as
an unused compatibility setting; Phase 7 deliberately implements no tool calling or agent loop.

Supported Phase 3 roles are `owner`, `manager`, `agent`, `viewer`, and `knowledge_editor`.
Owner/manager/agent/viewer can read profile, catalog, and schedules. `knowledge_editor` has no
Phase 3 profile/catalog/schedule grant. Phase 8 adds knowledge read access for all supported roles
and knowledge writes only for owner, manager, and knowledge-editor roles.

## Database variables

Both database variables must use `postgresql+asyncpg://`; SQLite is rejected. `APP_ENV` must be
`local`, `development`, or `test` for the fictional Northstar seed. The Phase 3 composition root
applies bounded pool size, overflow, and connection timeout values. Migration commands continue
to own their connection separately.

## Validation policy

Startup fails safely for invalid environment names, schemes/hosts/ports, production HTTP,
weak production credentials, non-IANA timezones, unsupported locales, inconsistent feature
switches, bad roles, bot/token mismatch at composition, and out-of-range numeric settings.
Telegram polling is rejected in production and Telegram webhook URLs must use HTTPS there. Errors
name the setting and a safe reason without echoing its value. The Phase 7 policy catalog validates
task, prompt, schema, provider, and model compatibility before a provider call. Phase 3 already
requires and bounds embedding dimensions when RAG is enabled. Phase 8 also validates chunk size
and overlap, candidate/result limits, a minimum relevance floor, and customer answer length.

## Phase 8 knowledge retrieval

`FEATURE_RAG_ENABLED=true` requires AI, OpenAI credentials, `OPENAI_EMBEDDING_MODEL`, and
`EMBEDDING_DIMENSIONS`. `KNOWLEDGE_CHUNK_MAX_TOKENS` and
`KNOWLEDGE_CHUNK_OVERLAP_TOKENS` control deterministic ingestion. `RAG_CANDIDATE_LIMIT`,
`RAG_RESULT_LIMIT`, `RAG_MIN_RELEVANCE`, and `RAG_MAX_ANSWER_CHARACTERS` bound retrieval and
evidence presentation. Model names and dimensions remain deployment policy; changing either does
not silently reuse incompatible vectors.

## Phase 9 privacy and retention

`OPERATIONAL_METADATA_RETENTION_DAYS`, `MESSAGE_RETENTION_DAYS`,
`CUSTOMER_CONTACT_RETENTION_DAYS`, `WORKFLOW_RETENTION_DAYS`,
`KNOWLEDGE_ARCHIVE_RETENTION_DAYS`, and `AI_TELEMETRY_RETENTION_DAYS` are bounded provisioning
defaults. Each accepts 1–3650 days. The versioned tenant `retention_policies` row is authoritative
for execution and can be changed only through the owner-authorized API with optimistic concurrency.

The Northstar values are fictional examples, not legal policy. Audit/security records are excluded
from automated Phase 9 deletion. Real deployments must approve legal holds, backup lifecycle,
exports, jurisdiction, and retention periods before enabling a schedule.

## Phase 10 background delivery

`CELERY_ENABLED` requires `CELERY_BROKER_URL`; results remain independently optional.
`NOTIFICATION_DELIVERY_ENABLED=true` additionally requires the existing complete Telegram
configuration. `WORKER_BATCH_SIZE`, `WORKER_LEASE_SECONDS`, `NOTIFICATION_MAX_ATTEMPTS`, and the
retry base/maximum settings are bounded. The base retry delay cannot exceed the maximum.

Tenant `automatic_execution_enabled` is the authoritative retention-schedule opt-in and defaults
to false, including Northstar. Environment configuration cannot override that tenant decision.

## Phase 11 observability

`METRICS_ENABLED=false` keeps `/metrics` absent by default. Enabling it requires a dedicated
`METRICS_AUTH_TOKEN`; production validation rejects weak placeholders. `SLOW_OPERATION_SECONDS`
controls the safe slow-operation flag and is bounded from 0.01 to 300 seconds.
`DEPENDENCY_HEALTH_TIMEOUT_SECONDS` bounds each live dependency check from 0.1 to 30 seconds.

PostgreSQL and pgvector are always readiness requirements. Redis, Telegram, and AI are checked as
required only when their existing feature configuration is enabled. `OTEL_EXPORTER_OTLP_ENDPOINT`
remains reserved configuration; Phase 11 does not install or activate a trace exporter. Metrics
tokens, correlation values, IDs, exception values, and customer/model content are never metric
labels.

## Secret handling

- Keep local values in `.env`, which Git ignores.
- Keep staging/production values in the deployment platform's secret manager.
- Never reuse secrets across environments or store them in tenant records, logs, fixtures, CI
  output, screenshots, or model prompts.
- Empty secret values in `.env.example` are deliberate safe placeholders and must never be used
  as production credentials. The Northstar tenant UUID is public fictional seed identity, not a
  credential.
- Rotate any value immediately if it enters Git history; deleting the current file is not enough.

The fictional demo defaults are not approved legal, privacy, or operational policy for a real
business. A human owner must approve the decisions listed in specification section 29.
