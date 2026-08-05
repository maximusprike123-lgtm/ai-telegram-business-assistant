# Phase 13 deployment and rollback runbook

## Artifact and topology

Build `Dockerfile` once and promote the resulting digest. The image runs as an unprivileged user
and contains runtime dependencies only. `compose.yaml` demonstrates PostgreSQL/pgvector, Redis,
one-shot migrations, API, worker, and beat; bind exposure is loopback-only because TLS and trusted
proxy policy belong at the deployment edge.

```bash
cp .env.production.example .env.production
# Replace every replace-me value using the deployment secret store.
docker compose config --quiet
docker compose build
docker compose run --rm migrate
docker compose up -d postgres redis api worker beat
curl --fail http://127.0.0.1:8000/health/live
curl --fail http://127.0.0.1:8000/health/ready
```

Never commit `.env.production`. Telegram, AI, and notification delivery stay disabled until their
credentials, external dependency checks, policies, and rollback owner are approved. Run exactly
one beat scheduler. Scale workers horizontally; database `SKIP LOCKED` claims and leases prevent
duplicate ownership, while idempotency/unique constraints prevent duplicate effects.

## Safe rollout

1. Back up the authoritative database and record its restore verification.
2. Build, scan, and identify the image by digest; never deploy a mutable tag alone.
3. Run `alembic upgrade head` as a one-shot job. Do not start new application processes if it fails.
4. Start API/workers, verify readiness and backlog/error metrics, then admit traffic gradually.
5. Run `scripts/release_smoke.py` against the same schema and configuration class.

## Rollback

Application rollback is preferred when the migration is backward compatible. Stop new workers,
restore the prior image digest, and verify readiness. Schema downgrade is deliberate only: inspect
the revision, confirm no new data depends on it, stop all writers, back up, run one Alembic step,
and re-run smoke checks. Phase 13's index-only migration is reversible without data transformation.

## Capacity and failure boundaries

Uvicorn concurrency, DB pool size, worker concurrency, batch size, leases, and task limits must be
tuned together. A process may be terminated at the hard task limit; its database lease makes work
reclaimable. Redis loss delays jobs but does not erase authoritative outbox/delivery state. Database
loss stops readiness and all consequential work. Chunked request-body enforcement must also be
configured at the edge; the application rejects oversized declared bodies and specialized streams.
