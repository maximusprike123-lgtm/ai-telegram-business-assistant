# ADR 0015: Tenant administration control plane

Status: Accepted

## Context

Tenant lifecycle, access, credentials, and product capabilities must be administered without
putting SaaS policy in Telegram handlers, AI adapters, environment flags, or billing state.
Suspension must stop customer work while preserving a narrow tenant-scoped recovery path.

## Decision

- Model lifecycle as `active`, `suspended`, and terminal `archived`; there is no tenant delete.
- Keep members, credentials, entitlements, provisioning records, and audit events tenant-scoped in
  PostgreSQL. Preserve the existing roles and permission model.
- Provision a suspended tenant atomically with safe profile/schedule defaults, one owner, one
  one-time credential, retention defaults, and explicit disabled-by-default entitlements.
- Store only PBKDF2 credential hashes plus a random lookup prefix. Authentication performs
  constant-time verification and enforces member status, role, revocation, and expiration.
- Permit suspended/archived credentials to authenticate only to `/api/v1/admin/*`; customer HTTP,
  Telegram, booking, qualification, knowledge, AI entry, notifications, and scheduled work require
  an active tenant and the relevant entitlement.
- Treat automatic retention as an entitlement view over the existing retention-policy opt-in so
  there is one authority. Entitlements are operational controls, not billing or subscription data.
- Retain the local bootstrap token only for initial provisioning. Production rejects it; a real
  deployment must place provisioning behind an approved operator identity boundary.

## Consequences

Provisioning is retry-safe and returns credential plaintext only on the creating response. Archive
is intentionally irreversible through the application API. Existing tenants are backfilled with
an owner placeholder and enabled capabilities to preserve behavior. Northstar creates deterministic
demo membership and entitlements but no administrative secret.

This phase does not implement signup, invitations, billing, subscriptions, a global administrator,
or an operator UI.
