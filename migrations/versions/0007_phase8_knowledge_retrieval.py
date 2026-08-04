"""add Phase 8 knowledge source and embedding metadata

Revision ID: 0007_phase8
Revises: 0006_phase7
Create Date: 2026-08-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_phase8"
down_revision: str | None = "0006_phase7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "knowledge_documents",
        sa.Column("source_text", sa.Text(), server_default="", nullable=False),
    )
    op.add_column("knowledge_chunks", sa.Column("embedding_model", sa.String(200), nullable=True))
    op.add_column(
        "knowledge_chunks", sa.Column("embedding_dimensions", sa.Integer(), nullable=True)
    )
    op.add_column(
        "knowledge_chunks",
        sa.Column("instruction_risk", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.alter_column("knowledge_documents", "source_text", server_default=None)
    op.alter_column("knowledge_chunks", "instruction_risk", server_default=None)
    op.create_check_constraint(
        op.f("ck_knowledge_chunks_embedding_metadata_consistent"),
        "knowledge_chunks",
        "(embedding IS NULL AND embedding_model IS NULL AND embedding_dimensions IS NULL) "
        "OR (embedding IS NOT NULL AND embedding_model IS NOT NULL "
        "AND embedding_dimensions = vector_dims(embedding))",
    )
    op.create_index(
        "ix_knowledge_chunks_tenant_embedding",
        "knowledge_chunks",
        ["tenant_id", "embedding_model", "embedding_dimensions"],
    )


def downgrade() -> None:
    op.drop_index("ix_knowledge_chunks_tenant_embedding", table_name="knowledge_chunks")
    op.drop_constraint(
        op.f("ck_knowledge_chunks_embedding_metadata_consistent"),
        "knowledge_chunks",
        type_="check",
    )
    op.drop_column("knowledge_chunks", "instruction_risk")
    op.drop_column("knowledge_chunks", "embedding_dimensions")
    op.drop_column("knowledge_chunks", "embedding_model")
    op.drop_column("knowledge_documents", "source_text")
