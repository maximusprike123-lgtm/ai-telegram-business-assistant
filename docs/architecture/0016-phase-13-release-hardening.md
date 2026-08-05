# ADR 0016: Phase 13 release hardening and certification

Status: Accepted — 2026-08-05

## Context

The modular monolith already has application-owned workflows and infrastructure adapters, but a
release candidate also needs bounded execution, deterministic packaging, operational recovery,
and repeatable evidence. These concerns must not migrate product decisions into delivery code.

## Decision

- Keep PostgreSQL/pgvector authoritative. Redis remains disposable broker state.
- Enforce request size and processing-time limits at the HTTP presentation boundary. Cancellation
  propagates into application units of work so unfinished transactions roll back.
- Bound Celery tasks with soft/hard time limits and retain database leases, attempts, and dead
  letters as the recovery source of truth.
- Add partial indexes matching global due/stale worker scans; retain tenant-leading indexes for
  tenant diagnostics.
- Ship one immutable, non-root image used by API, migration, worker, and beat processes. Migrations
  execute as an explicit one-shot deployment step before runtime services.
- Certify a release with locked dependencies, full tests, a representative smoke matrix, container
  build/config checks, secret/dependency/hygiene scans, and a recorded backup/restore exercise.

## Consequences

The baseline is production-like but provider-neutral. TLS termination, secret injection, managed
database backups, alert routing, and capacity targets remain deployment-owner responsibilities.
The included Compose topology is a validation/reference environment, not an HA control plane.
