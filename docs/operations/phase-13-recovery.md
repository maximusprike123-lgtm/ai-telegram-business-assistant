# Phase 13 backup and disaster-recovery runbook

## Data ownership

PostgreSQL is authoritative for tenants, credentials (hashed), workflows, bookings, knowledge,
privacy audit, outbox, deliveries, and worker runs. Redis queues are regenerable from scheduled jobs
and database-authoritative pending records. Application images and configuration templates are
rebuildable from the signed source revision and locks; runtime secrets must be restored from the
deployment secret manager, never from a database dump.

The deployment owner must set and approve RPO/RTO from business needs. This repository does not
claim an RPO/RTO: local Compose has a persistent volume but no automated off-host backup or HA.

## Restore exercise

Use client tools compatible with the target PostgreSQL major version. The restore target must be a
disposable, separately named database; the script refuses identical source and target URLs.

```bash
export BACKUP_DATABASE_URL='postgresql://.../business_assistant'
export RESTORE_DATABASE_URL='postgresql://.../business_assistant_restore'
export BACKUP_FILE='/secure/explicit/path/business-assistant.dump'
scripts/backup_restore.sh
```

After the script verifies Alembic revision and pgvector, run `alembic check`, the release smoke
matrix with the restored asyncpg URL, tenant-count checks, and representative booking, knowledge,
audit, and pending-delivery counts. Record timestamps, dump checksum, source/target PostgreSQL
versions, revision, results, operator, and deletion of the disposable copy. Never log URLs.

Test restoration at least before each release and on the deployment owner's recurring schedule.
