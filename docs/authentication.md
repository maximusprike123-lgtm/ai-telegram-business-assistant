# Authentication and tenant administration

The internal API accepts `X-Internal-API-Key`. Phase 12 supports database-backed tenant
credentials and retains the configured static key only as a compatibility fallback. Every
successful authentication resolves one immutable subject, tenant, and existing role; request data
cannot select or broaden tenant scope. Optional `X-Tenant-ID` is only a matching assertion.

Administrative credentials have a random `atba_` lookup prefix and secret. PostgreSQL stores the
prefix, PBKDF2-SHA256 hash, member/tenant binding, role snapshot, expiration, revocation, rotation
lineage, and last-use timestamp. Verification is constant-time. Member deactivation or role
changes invalidate or update affected credentials. Lists never contain plaintext, and create or
rotate responses expose a secret once.

Suspended and archived tenant credentials may call only tenant-scoped `/api/v1/admin/*` recovery
routes. Other authenticated routes require an active tenant and, where applicable, an enabled
capability. Archived lifecycle state remains terminal.

Initial provisioning is separate: `X-Admin-Bootstrap-Token` is accepted only when configured and
is rejected by production configuration validation. It is not a global product principal or a
substitute for an operator identity provider.
