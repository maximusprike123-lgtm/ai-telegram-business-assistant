# Phase 9 privacy and retention runbook

## Policy and classification

The protected API derives tenant scope from the authenticated key. Owner and manager roles may
read classifications, policy, and retention previews. Only the owner role may replace policy or
execute anonymization/deletion.

- `GET /api/v1/privacy/data-classifications`
- `GET /api/v1/privacy/retention-policy`
- `PUT /api/v1/privacy/retention-policy`
- `GET /api/v1/privacy/retention-preview`
- `POST /api/v1/privacy/retention-executions`
- `POST /api/v1/privacy/customers/{customer_id}/anonymize`

Policy replacement requires `expected_version`; stale updates return a conflict. Every period must
be between 1 and 3650 days. The Northstar defaults are fictional operational examples:

| Data class | Default | Due action |
|---|---:|---|
| Operational metadata | 30 days | Delete terminal Telegram update rows |
| Message content | 90 days | Delete persisted message rows |
| Customer contact | 365 days | Anonymize only inactive, workflow-safe customers |
| Workflow records | 730 days | Remove personal snapshots/answers/notes from terminal records |
| Archived knowledge | 365 days | Delete archived document and chunk lineage |
| AI telemetry | 90 days | Delete metadata-only operation rows |
| Audit/security | Preserved | No Phase 9 retention deletion |

These values are not approved policy for a real business. Configure and document legally approved
periods per tenant.

## Safe execution procedure

1. Confirm database backups and any applicable legal hold with the responsible human owner.
2. Read the current policy and record its version.
3. Call `retention-preview`; verify every class count and tenant credential.
4. Submit a unique opaque idempotency key and `confirmed: true` to `retention-executions`.
5. Record the returned action ID and counts. A retry with the same key returns the original result.
6. Verify the immutable `privacy.retention_executed` audit event.

A customer-specific request also requires a safe reason code and explicit confirmation. It removes
contact fields, replaces external channel identifiers with opaque anonymized values, deletes stored
messages, scrubs personal workflow payloads, closes/cancels live customer workflows, and releases
active holds. It preserves booking/service facts, lifecycle history, consent receipts, opaque
record links, and audit records.

Never put names, phone numbers, emails, request text, or deletion payloads in idempotency keys,
reason codes, logs, or tickets. Safe codes use ASCII letters, digits, dots, underscores, colons,
and hyphens only.

## Recovery and limitations

Committed hard deletion and anonymization are intentionally not reversible through the API.
Recovery, when legally and operationally appropriate, requires an approved backup procedure and
must not silently reintroduce data removed by a customer request. Phase 9 does not automate backup
expiry or storage-provider deletion.

Phase 9 shipped no scheduler. Phase 10 now schedules the same persistence boundary only for tenant
policies with explicit `automatic_execution_enabled=true`; policy does not move into Celery.
Export packages, legal holds, multi-step approval, key destruction, and regional residency remain
future deployment requirements.
