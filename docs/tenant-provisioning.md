# Tenant provisioning guide

1. In a local, development, or test environment, configure a strong `ADMIN_BOOTSTRAP_TOKEN`.
2. Generate a tenant UUID and unique caller-owned idempotency key.
3. Call `POST /api/v1/admin/provisioning/tenants` with English locale, owner subject, credential
   name, and the capabilities that should start enabled.
4. Move the returned credential immediately to an approved secret manager. It is shown once.
5. Complete and verify the tenant's business profile, schedule, catalog, booking, qualification,
   knowledge, AI, notification, and retention settings through their existing authorities.
6. Activate through `POST /api/v1/admin/tenant/lifecycle/active` only after review.

Provisioning is one PostgreSQL transaction and serializes concurrent attempts by idempotency key.
It creates a suspended tenant, inactive default schedule, safe pending profile, owner member,
initial hashed credential, retention defaults, explicit entitlements, provisioning record, and
safe audit event. Replaying the same key and tenant returns the created identities without the
secret; reusing it for another tenant is a conflict.

Production intentionally has no bootstrap endpoint authority. Place provisioning behind an
approved operator identity/process before deployment; Phase 12 does not implement signup,
invitations, billing, subscriptions, or a global administrator.
