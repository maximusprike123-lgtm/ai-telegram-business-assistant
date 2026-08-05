# Phase 13 release-candidate evidence

Recorded 2026-08-05 on macOS/arm64 with Python 3.13.3, Docker Desktop, and the pinned PostgreSQL
18/pgvector image. Source candidate before this evidence-only record: `3058097c1f0ad7d92e9e1ae23f6821cba818ef93`.
Results describe this disposable local environment only; they are not production SLAs or a formal
penetration, legal-compliance, or license audit.

## Verified gates

| Gate | Result |
|---|---|
| Ruff lint/format; strict mypy | Pass; 151 typed source files, no mypy issues |
| Full PostgreSQL suite | Pass; 269 tests, 87.52% coverage (85% required) |
| Architecture tests | Pass within the full suite |
| Representative smoke matrix | Pass; 54 tests in 24.738 seconds end-to-end (pytest: 22.12 seconds) |
| Migration | Upgrade/downgrade coverage passed; `alembic check` found no drift |
| Seed/OpenAPI | Seeded twice idempotently; OpenAPI generated with 26 paths |
| Packaging | Wheel and sdist `0.2.0rc1` built; `pip check` passed |
| Supply chain | Runtime `pip-audit`: no known vulnerabilities at check time |
| Repository | detect-secrets, path/Cyrillic hygiene, all pre-commit hooks passed |
| Compose/image | Compose config passed; image built; configured user `app`; installed version `0.2.0rc1` |
| Runtime health | Image liveness and PostgreSQL/pgvector readiness returned healthy |
| Recovery | Dump restored to separate database; revision `0012_phase13`, pgvector, 1 tenant, 6 services verified |

The built local image ID was
`sha256:0c2b6462e479f49061fdea4fc033137445b4210419836dbdc1071cf82506d426`.
Promotion must record the registry digest produced by the deployment pipeline; a local image ID is
not a registry attestation.

## Concurrency and query evidence

The suite covers last-slot booking contention, Telegram update/identity claims, provisioning
idempotency under concurrent calls, qualification/handoff idempotency, retention idempotency, and
concurrent notification claims. One authoritative provisioning result and one notification claim
were observed. PostgreSQL `EXPLAIN` with sequential scans disabled used BitmapOr over the new
pending/processing partial indexes for both outbox and notification scans and an index-only scan
for automatic retention policies.

A bounded HTTP sample against the built two-worker image ran 100 authenticated catalog requests at
concurrency 10 with zero failures: 75.10 requests/second, median 119.33 ms, p95 265.87 ms, p99
272.00 ms. This is a smoke-level local measurement; booking-write contention, RAG with a live
provider, sustained worker throughput, soak, saturation, and production-dataset plans remain
deployment-environment benchmarks.

## Security and failure review

Authentication remains tenant-bound, hashed database credentials retain lifecycle enforcement,
RBAC and entitlements remain application-owned, Telegram webhook authentication precedes parsing,
and AI/knowledge answers retain structured evidence validation. Logs remain allowlisted and
content-free by default. Phase 13 adds declared-body rejection, request cancellation deadlines,
task deadlines, dependency audit, secret scan, and non-root runtime packaging.

PostgreSQL remains the single authoritative dependency: its loss fails readiness and consequential
work. Redis loss delays work but database pending/lease/dead-letter state remains recoverable.
Worker termination is reclaimed after leases. Provider timeouts retain deterministic fallbacks.
Migration failure blocks runtime startup in the reference topology.

## Release limitations and required owner actions

- TLS, trusted proxy/host policy, WAF/rate limiting, and chunked-body limits must be enforced at the
  deployment edge. The application rejects oversized declared bodies and specialized streams.
- Compose is a reproducible reference topology, not HA orchestration. It has no multi-AZ database,
  Redis HA, autoscaling, automated certificate management, or off-host backup scheduler.
- The owner must set and validate RPO/RTO, alert routes, capacity/SLO targets, secret rotation,
  infrastructure vulnerability scanning, SBOM/signing/provenance, and recurring restore cadence.
- No live Telegram/OpenAI delivery, external observability backend, penetration test, privacy-law
  assessment, or production load/soak test was performed.
- Dependency licenses require an owner/legal review before distribution; this evidence makes no
  compatibility conclusion.

Release status: technically ready as a `0.2.0rc1` deployment candidate after CI reproduces these
gates. Production promotion remains conditional on the unchecked deployment-owner items in the
release checklist.
