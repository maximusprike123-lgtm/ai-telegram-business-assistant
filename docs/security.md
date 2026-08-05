# Security notes

- Tenant IDs come from authenticated credentials or trusted Telegram bot bindings, never customer
  payloads. Composite constraints and tenant-filtered queries reinforce application checks.
- Tenant lifecycle and operational entitlements fail closed at HTTP, Telegram, AI/knowledge, and
  scheduled/background entry points. Administration recovery is explicitly path-limited.
- Credentials are random, one-way hashed, constant-time verified, expirable, revocable, rotatable,
  and never written to logs or audit diffs. Prefixes are identifiers, not authenticators.
- The final active owner cannot be removed or demoted. Existing roles and least-privilege grants are
  reused; Phase 12 adds no global role.
- Audit events record fixed actions, bounded actor/target identifiers, safe diffs, timestamps, and
  correlation IDs. They exclude request bodies, customer content, secrets, and hashes.
- Operational entitlements are kill switches, not proof of payment, subscription state, legal
  approval, or business readiness. Automatic retention remains controlled by its existing policy.
- The local bootstrap token is forbidden in production. A real deployment needs an approved
  operator identity boundary, secret manager, rotation procedure, and incident response process.
