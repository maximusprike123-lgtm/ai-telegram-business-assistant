"""add Telegram update processing ledger

Revision ID: 0003_phase4
Revises: 0002_phase3
Create Date: 2026-08-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_phase4"
down_revision: str | None = "0002_phase3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "telegram_updates",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("bot_id", sa.BigInteger(), nullable=False),
        sa.Column("update_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("attempts >= 1", name=op.f("ck_telegram_updates_attempts_positive")),
        sa.CheckConstraint("bot_id > 0", name=op.f("ck_telegram_updates_bot_id_positive")),
        sa.CheckConstraint(
            "status IN ('processing','completed','failed')",
            name=op.f("ck_telegram_updates_status_allowed"),
        ),
        sa.CheckConstraint(
            "update_id >= 0", name=op.f("ck_telegram_updates_update_id_nonnegative")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_telegram_updates_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_telegram_updates")),
        sa.UniqueConstraint(
            "tenant_id",
            "bot_id",
            "update_id",
            name=op.f("uq_telegram_updates_tenant_id_bot_id_update_id"),
        ),
    )
    op.create_index(
        "ix_telegram_updates_terminal_created",
        "telegram_updates",
        ["status", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_telegram_updates_terminal_created", table_name="telegram_updates")
    op.drop_table("telegram_updates")
