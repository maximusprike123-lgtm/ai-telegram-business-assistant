# ADR 0006: Phase 3 query, schedule, and internal API boundary

Status: Accepted

## Context

Phase 3 needs customer-safe configuration reads before Telegram or a complete identity provider
exists. The Phase 2 schema stores catalog and schedules but lacks a tenant-owned public profile
and a durable link from that profile to the schedule exposed to customers.

## Decision

- Add `tenant_public_profiles` in revision `0002`, with a tenant primary key, localized public
  fields, and a composite tenant/schedule foreign key. Existing Phase 1/2 tables and behavior are
  unchanged.
- Keep query DTOs and deterministic locale, money, duration, hours, status, and next-open policy
  in the application layer. Use cases depend on a tenant-scoped UoW and `Clock`, never ORM or
  FastAPI types. Read-only use cases do not commit.
- Resolve locale in this order: requested supported locale, tenant default, English, then the
  lexically first supported locale. Missing content advances through the same list; no translation
  is synthesized. No content produces `locale.unresolved`.
- Treat weekly intervals as tenant-local wall time. Overrides replace the weekly day; a closure
  produces no intervals. Search for an opening is bounded to 370 local calendar days.
- A nonexistent DST boundary is invalid. For an ambiguous boundary, an opening uses the earlier
  instant and a closing uses the later instant, preserving the full advertised wall-time window.
- Expose read-only `/api/v1` endpoints through thin FastAPI handlers with explicit schemas and
  stable safe errors. A replaceable static-key adapter uses constant-time comparison and binds one
  credential to one tenant and role. A client tenant header is only a matching assertion, never
  the source of authority.
- Load and validate immutable runtime configuration only in the composition root. Credentials for
  disabled later integrations are not required.

## Consequences

Phase 3 can demonstrate deterministic customer-safe reads without Telegram, AI, booking, Redis,
Celery, or a user-management platform. Static authentication has no rotation, per-user lifecycle,
or audit administration and must be replaced before a multi-operator SaaS deployment. Schedule
queries do not calculate staff/resource availability or appointment slots; Phase 5 owns those.
