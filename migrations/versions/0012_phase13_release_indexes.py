"""add Phase 13 worker and retention indexes

Revision ID: 0012_phase13
Revises: 0011_phase12
Create Date: 2026-08-05
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0012_phase13"
down_revision: str | None = "0011_phase12"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_retention_policies_automatic_tenant",
        "retention_policies",
        ["tenant_id"],
        postgresql_where="automatic_execution_enabled IS TRUE",
    )
    op.create_index(
        "ix_outbox_events_global_pending",
        "outbox_events",
        ["available_at", "id"],
        postgresql_where="status = 'pending'",
    )
    op.create_index(
        "ix_outbox_events_global_processing",
        "outbox_events",
        ["locked_at", "id"],
        postgresql_where="status = 'processing'",
    )
    op.drop_index("ix_notification_deliveries_due", table_name="notification_deliveries")
    op.create_index(
        "ix_notification_deliveries_due",
        "notification_deliveries",
        ["available_at", "id"],
        postgresql_where="status = 'pending'",
    )
    op.create_index(
        "ix_notification_deliveries_processing",
        "notification_deliveries",
        ["locked_at", "id"],
        postgresql_where="status = 'processing'",
    )


def downgrade() -> None:
    op.drop_index("ix_notification_deliveries_processing", table_name="notification_deliveries")
    op.drop_index("ix_notification_deliveries_due", table_name="notification_deliveries")
    op.create_index(
        "ix_notification_deliveries_due",
        "notification_deliveries",
        ["available_at"],
        postgresql_where="status = 'pending'",
    )
    op.drop_index("ix_outbox_events_global_processing", table_name="outbox_events")
    op.drop_index("ix_outbox_events_global_pending", table_name="outbox_events")
    op.drop_index("ix_retention_policies_automatic_tenant", table_name="retention_policies")
