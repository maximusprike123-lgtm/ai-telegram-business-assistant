# Release checklist

- [ ] Release version and changelog match the candidate.
- [ ] Worktree and submodule state are recorded; no machine paths or secrets are tracked.
- [ ] Runtime/build/development locks are regenerated and reviewed.
- [ ] Ruff, format, strict mypy, full PostgreSQL tests, coverage >=85%, architecture tests pass.
- [ ] Alembic upgrade/downgrade/upgrade and metadata drift checks pass.
- [ ] Seed runs twice without changing authoritative demo results; OpenAPI generation passes.
- [ ] Runtime dependency audit and `pip check` pass; exceptions are documented and time-bounded.
- [ ] Wheel/sdist and non-root container build; Compose config validates.
- [ ] Liveness/readiness and representative release smoke matrix pass.
- [ ] Concurrency tests cover booking, Telegram claims, provisioning, qualification/handoff,
  retention, and database-authoritative worker claims.
- [ ] Load results are recorded for the target environment without claiming universal capacity.
- [ ] Backup is restored into a disposable database and its revision/data checks pass.
- [ ] Deployment, observability, failure, rollback, and escalation owners approve the release.
- [ ] Image digest and source commit are recorded before tag/promotion; no automatic push occurs.
