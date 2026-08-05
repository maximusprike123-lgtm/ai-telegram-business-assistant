"""add Phase 9 privacy retention policy and action records

Revision ID: 0008_phase9
Revises: 0007_phase8
Create Date: 2026-08-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_phase9"
down_revision: str | None = "0007_phase8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "retention_policies",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("operational_metadata_days", sa.Integer(), nullable=False),
        sa.Column("message_content_days", sa.Integer(), nullable=False),
        sa.Column("customer_contact_days", sa.Integer(), nullable=False),
        sa.Column("workflow_records_days", sa.Integer(), nullable=False),
        sa.Column("knowledge_archive_days", sa.Integer(), nullable=False),
        sa.Column("ai_telemetry_days", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_retention_policies_version_positive")),
        sa.CheckConstraint(
            "operational_metadata_days BETWEEN 1 AND 3650 "
            "AND message_content_days BETWEEN 1 AND 3650 "
            "AND customer_contact_days BETWEEN 1 AND 3650 "
            "AND workflow_records_days BETWEEN 1 AND 3650 "
            "AND knowledge_archive_days BETWEEN 1 AND 3650 "
            "AND ai_telemetry_days BETWEEN 1 AND 3650",
            name=op.f("ck_retention_policies_periods_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_retention_policies_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("tenant_id", name=op.f("pk_retention_policies")),
    )
    op.execute(
        "INSERT INTO retention_policies "
        "(tenant_id, version, operational_metadata_days, message_content_days, "
        "customer_contact_days, workflow_records_days, knowledge_archive_days, ai_telemetry_days) "
        "SELECT id, 1, 30, 90, 365, 730, 365, 90 FROM tenants"
    )
    op.create_table(
        "privacy_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action_type", sa.String(length=32), nullable=False),
        sa.Column("target_type", sa.String(length=50), nullable=True),
        sa.Column("target_id", sa.String(length=100), nullable=True),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("reason_code", sa.String(length=100), nullable=False),
        sa.Column("policy_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("result_counts", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("requested_by", sa.String(length=100), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "action_type IN ('customer_anonymization','retention_execution')",
            name=op.f("ck_privacy_actions_action_type_allowed"),
        ),
        sa.CheckConstraint("status = 'completed'", name=op.f("ck_privacy_actions_status_allowed")),
        sa.CheckConstraint(
            "policy_version >= 1", name=op.f("ck_privacy_actions_policy_version_positive")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_privacy_actions_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_privacy_actions")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_privacy_actions_tenant_id_id")),
        sa.UniqueConstraint(
            "tenant_id",
            "idempotency_key",
            name=op.f("uq_privacy_actions_tenant_id_idempotency_key"),
        ),
    )
    op.create_index(
        "ix_privacy_actions_tenant_occurred",
        "privacy_actions",
        ["tenant_id", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_privacy_actions_tenant_occurred", table_name="privacy_actions")
    op.drop_table("privacy_actions")
    op.drop_table("retention_policies")
