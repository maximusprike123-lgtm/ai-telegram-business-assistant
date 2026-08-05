"""add durable Phase 11 correlation metadata

Revision ID: 0010_phase11
Revises: 0009_phase10
Create Date: 2026-08-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_phase11"
down_revision: str | None = "0009_phase10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table in ("outbox_events", "notification_deliveries", "worker_runs"):
        op.add_column(table, sa.Column("correlation_id", sa.String(length=128)))
    op.execute("UPDATE outbox_events SET correlation_id = event_id::text")
    op.execute("UPDATE notification_deliveries SET correlation_id = event_id::text")
    op.execute("UPDATE worker_runs SET correlation_id = id::text")
    for table in ("outbox_events", "notification_deliveries", "worker_runs"):
        op.alter_column(table, "correlation_id", nullable=False)


def downgrade() -> None:
    for table in ("worker_runs", "notification_deliveries", "outbox_events"):
        op.drop_column(table, "correlation_id")
