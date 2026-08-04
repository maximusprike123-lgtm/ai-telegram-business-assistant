"""add Phase 7 metadata-only AI operation telemetry

Revision ID: 0006_phase7
Revises: 0005_phase6
Create Date: 2026-08-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_phase7"
down_revision: str | None = "0005_phase6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_operations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("conversation_id", sa.UUID(), nullable=True),
        sa.Column("correlation_id", sa.UUID(), nullable=False),
        sa.Column("task", sa.String(32), nullable=False),
        sa.Column("provider", sa.String(100), nullable=False),
        sa.Column("model", sa.String(200), nullable=False),
        sa.Column("prompt_id", sa.String(100), nullable=False),
        sa.Column("prompt_version", sa.Integer(), nullable=False),
        sa.Column("schema_id", sa.String(100), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("estimated_cost", sa.Numeric(20, 10), nullable=False),
        sa.Column("failure_code", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("attempts >= 0", name=op.f("ck_ai_operations_attempts_nonnegative")),
        sa.CheckConstraint("estimated_cost >= 0", name=op.f("ck_ai_operations_cost_nonnegative")),
        sa.CheckConstraint("latency_ms >= 0", name=op.f("ck_ai_operations_latency_nonnegative")),
        sa.CheckConstraint(
            "prompt_version >= 0", name=op.f("ck_ai_operations_prompt_version_nonnegative")
        ),
        sa.CheckConstraint(
            "status IN ('success','fallback','disabled','cancelled')",
            name=op.f("ck_ai_operations_status_allowed"),
        ),
        sa.CheckConstraint(
            "task IN ('intent','extraction','classification','rewrite','summary')",
            name=op.f("ck_ai_operations_task_allowed"),
        ),
        sa.CheckConstraint(
            "input_tokens >= 0 AND output_tokens >= 0",
            name=op.f("ck_ai_operations_tokens_nonnegative"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "conversation_id"],
            ["conversations.tenant_id", "conversations.id"],
            name=op.f("fk_ai_operations_tenant_id_conversation_id_conversations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_ai_operations_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_operations")),
    )
    op.create_index(
        "ix_ai_operations_tenant_conversation",
        "ai_operations",
        ["tenant_id", "conversation_id"],
    )
    op.create_index("ix_ai_operations_tenant_created", "ai_operations", ["tenant_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_ai_operations_tenant_created", table_name="ai_operations")
    op.drop_index("ix_ai_operations_tenant_conversation", table_name="ai_operations")
    op.drop_table("ai_operations")
