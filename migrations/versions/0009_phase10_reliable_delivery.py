"""add Phase 10 reliable background delivery records

Revision ID: 0009_phase10
Revises: 0008_phase9
Create Date: 2026-08-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_phase10"
down_revision: str | None = "0008_phase9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "retention_policies",
        sa.Column(
            "automatic_execution_enabled",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )
    op.drop_constraint(op.f("ck_outbox_events_status_allowed"), "outbox_events", type_="check")
    op.create_check_constraint(
        op.f("ck_outbox_events_status_allowed"),
        "outbox_events",
        "status IN ('pending','processing','published','dead_letter')",
    )
    op.add_column("outbox_events", sa.Column("published_at", sa.DateTime(timezone=True)))
    op.add_column("outbox_events", sa.Column("last_error_code", sa.String(length=64)))
    op.create_table(
        "notification_subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("recipient_id", sa.String(length=100), nullable=False),
        sa.Column("event_types", postgresql.JSONB(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "channel = 'telegram'", name=op.f("ck_notification_subscriptions_channel_allowed")
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id"),
        sa.UniqueConstraint("tenant_id", "channel", "recipient_id"),
    )
    op.create_index(
        "ix_notification_subscriptions_tenant_enabled",
        "notification_subscriptions",
        ["tenant_id", "enabled"],
    )
    op.create_table(
        "notification_deliveries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subscription_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("recipient_id", sa.String(length=100), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True)),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("last_error_code", sa.String(length=64)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "attempts >= 0", name=op.f("ck_notification_deliveries_attempts_nonnegative")
        ),
        sa.CheckConstraint(
            "status IN ('pending','processing','sent','dead_letter')",
            name=op.f("ck_notification_deliveries_status_allowed"),
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "subscription_id"],
            ["notification_subscriptions.tenant_id", "notification_subscriptions.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "event_id", "subscription_id"),
    )
    op.create_index(
        "ix_notification_deliveries_due",
        "notification_deliveries",
        ["available_at"],
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index(
        "ix_notification_deliveries_tenant_status",
        "notification_deliveries",
        ["tenant_id", "status"],
    )
    op.create_table(
        "worker_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True)),
        sa.Column("task_name", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("processed_count", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=64)),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('success','failed')", name=op.f("ck_worker_runs_status_allowed")
        ),
        sa.CheckConstraint(
            "processed_count >= 0", name=op.f("ck_worker_runs_processed_count_nonnegative")
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_worker_runs_tenant_task_finished",
        "worker_runs",
        ["tenant_id", "task_name", "finished_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_worker_runs_tenant_task_finished", table_name="worker_runs")
    op.drop_table("worker_runs")
    op.drop_index("ix_notification_deliveries_tenant_status", table_name="notification_deliveries")
    op.drop_index("ix_notification_deliveries_due", table_name="notification_deliveries")
    op.drop_table("notification_deliveries")
    op.drop_index(
        "ix_notification_subscriptions_tenant_enabled", table_name="notification_subscriptions"
    )
    op.drop_table("notification_subscriptions")
    op.drop_column("retention_policies", "automatic_execution_enabled")
    op.drop_column("outbox_events", "last_error_code")
    op.drop_column("outbox_events", "published_at")
    op.drop_constraint(op.f("ck_outbox_events_status_allowed"), "outbox_events", type_="check")
    op.create_check_constraint(
        op.f("ck_outbox_events_status_allowed"),
        "outbox_events",
        "status IN ('pending','processing','published','failed')",
    )
