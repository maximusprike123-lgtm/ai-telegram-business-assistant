# Phase 12 completion traceability

| Phase 12 contract | Implementation and verification anchor |
|---|---|
| Tenant lifecycle and recovery | `domain.tenants`, administration service/store, protected admin API |
| Atomic idempotent provisioning | `TenantAdministration.provision`, `tenant_provisioning_records`, PostgreSQL tests |
| Tenant members and owner protection | `tenant_members`, existing typed roles/permissions, last-owner tests |
| Secure credentials | PBKDF2 issuer, database authenticator, rotate/revoke/expire/last-used tests |
| Capability controls | `tenant_entitlements`, retention-policy mapping, HTTP/Telegram/worker access policies |
| Tenant isolation and audit safety | composite constraints, tenant-filtered queries, `audit_events.safe_diff` assertions |
| Migration and backfill | revision `0011_phase12`, upgrade/downgrade/drift and seed-idempotency validation |
| Typed API and documentation | `/api/v1/admin/*`, OpenAPI test, ADR 0015, Phase 12 runbook |

Deferred: public signup, invitations, billing/subscriptions, dashboards, global operator identity,
new AI capabilities, agents, MCP, LangGraph, CRM, and frontend work.
