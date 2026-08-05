# Phase 12 tenant administration runbook

## Provisioning

Initial provisioning is available only when `ADMIN_BOOTSTRAP_TOKEN` is configured and supplied as
`X-Admin-Bootstrap-Token`. The configuration loader forbids this local bootstrap mechanism in
production. Send a caller-generated tenant UUID and idempotency key to
`POST /api/v1/admin/provisioning/tenants`. A new tenant is suspended and all capabilities not
explicitly listed are disabled.

The response contains the initial credential once. Store it in an approved secret manager; it
cannot be recovered or listed later. A replay returns the same resource identities with no secret.

## Tenant-scoped administration

Use the issued value as `X-Internal-API-Key`. Owner credentials can update the English-only tenant
profile, activate/suspend/archive, manage members, manage credentials, and change entitlements.
Managers retain the existing profile/read permissions but cannot change lifecycle, ownership,
credentials, or entitlements. The final active owner cannot be demoted or revoked.

Credential listing exposes prefix and metadata only. Rotation atomically revokes the old key and
returns a new secret once. Revocation and member removal immediately invalidate affected keys.
Expiration and last-use are enforced by database-backed authentication.

## Suspension and recovery

Suspension blocks customer APIs, Telegram updates, booking/qualification/knowledge entry points,
notification delivery, hold-expiration work, and automatic retention. Tenant-scoped admin routes
remain available so an owner can inspect and reactivate the tenant. Archive is terminal and has no
delete endpoint. Existing durable records and audits are preserved.

## Operational checks

After migration, run `alembic check`, generate OpenAPI, provision twice with the same key, verify the
second response contains no secret, rotate/revoke a test credential, and verify disabled/suspended
paths fail closed. Never place credentials, bootstrap tokens, customer text, or raw request bodies
in audit diffs or logs.

Phase 12 does not supply a production operator identity system. Deployments must keep provisioning
disabled until an approved external operator boundary is available.
