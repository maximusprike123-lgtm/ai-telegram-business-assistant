"""add Phase 6 consent, qualification, and handoff workflows

Revision ID: 0005_phase6
Revises: 0004_phase5
Create Date: 2026-08-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_phase6"
down_revision: str | None = "0004_phase5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("qualification_snapshot", postgresql.JSONB(), nullable=True))
    op.add_column("leads", sa.Column("qualified_at", sa.DateTime(timezone=True), nullable=True))

    op.add_column("handoff_cases", sa.Column("customer_id", sa.UUID(), nullable=True))
    op.add_column("handoff_cases", sa.Column("lead_id", sa.UUID(), nullable=True))
    op.add_column("handoff_cases", sa.Column("booking_id", sa.UUID(), nullable=True))
    op.add_column(
        "handoff_cases",
        sa.Column(
            "context", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
    )
    op.add_column("handoff_cases", sa.Column("idempotency_key", sa.String(255), nullable=True))
    op.create_foreign_key(
        op.f("fk_handoff_cases_tenant_id_customer_id_customers"),
        "handoff_cases",
        "customers",
        ["tenant_id", "customer_id"],
        ["tenant_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        op.f("fk_handoff_cases_tenant_id_lead_id_leads"),
        "handoff_cases",
        "leads",
        ["tenant_id", "lead_id"],
        ["tenant_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        op.f("fk_handoff_cases_tenant_id_booking_id_bookings"),
        "handoff_cases",
        "bookings",
        ["tenant_id", "booking_id"],
        ["tenant_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        op.f("uq_handoff_cases_tenant_id_idempotency_key"),
        "handoff_cases",
        ["tenant_id", "idempotency_key"],
    )

    op.create_table(
        "qualification_schemas",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("consent_version", sa.String(50), nullable=False),
        sa.Column("consent_purpose", sa.String(500), nullable=False),
        sa.Column("definition", postgresql.JSONB(), nullable=False),
        sa.Column("grade_bands", postgresql.JSONB(), nullable=False),
        sa.Column("session_ttl_minutes", sa.Integer(), nullable=False),
        sa.Column("handoff_response_minutes", sa.Integer(), nullable=False),
        sa.Column("published", sa.Boolean(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("config_version", sa.Integer(), nullable=False),
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
        sa.CheckConstraint(
            "config_version >= 1", name=op.f("ck_qualification_schemas_config_version_positive")
        ),
        sa.CheckConstraint(
            "handoff_response_minutes BETWEEN 1 AND 10080",
            name=op.f("ck_qualification_schemas_handoff_response_valid"),
        ),
        sa.CheckConstraint(
            "session_ttl_minutes BETWEEN 5 AND 10080",
            name=op.f("ck_qualification_schemas_session_ttl_valid"),
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_qualification_schemas_version_positive")),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_qualification_schemas_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_qualification_schemas")),
        sa.UniqueConstraint(
            "tenant_id",
            "code",
            "version",
            name=op.f("uq_qualification_schemas_tenant_id_code_version"),
        ),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_qualification_schemas_tenant_id_id")),
    )
    op.create_index(
        "uq_qualification_schemas_tenant_published_code",
        "qualification_schemas",
        ["tenant_id", "code"],
        unique=True,
        postgresql_where=sa.text("published AND active"),
    )

    op.create_table(
        "qualification_sessions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("customer_id", sa.UUID(), nullable=False),
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column("schema_id", sa.UUID(), nullable=False),
        sa.Column("schema_code", sa.String(100), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("answers", postgresql.JSONB(), nullable=False),
        sa.Column("current_field_key", sa.String(100), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consent_decision", sa.String(16), nullable=True),
        sa.Column("consent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lead_id", sa.UUID(), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
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
        sa.CheckConstraint(
            "consent_decision IS NULL OR consent_decision IN ('accepted','declined')",
            name=op.f("ck_qualification_sessions_consent_decision_allowed"),
        ),
        sa.CheckConstraint(
            "revision >= 1", name=op.f("ck_qualification_sessions_revision_positive")
        ),
        sa.CheckConstraint(
            "schema_version >= 1", name=op.f("ck_qualification_sessions_schema_version_positive")
        ),
        sa.CheckConstraint(
            "status IN ('awaiting_consent','in_progress','reviewing','completed',"
            "'declined','cancelled','expired')",
            name=op.f("ck_qualification_sessions_status_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "conversation_id"],
            ["conversations.tenant_id", "conversations.id"],
            name=op.f("fk_qualification_sessions_tenant_id_conversation_id_conversations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "customer_id"],
            ["customers.tenant_id", "customers.id"],
            name=op.f("fk_qualification_sessions_tenant_id_customer_id_customers"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "lead_id"],
            ["leads.tenant_id", "leads.id"],
            name=op.f("fk_qualification_sessions_tenant_id_lead_id_leads"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "schema_id"],
            ["qualification_schemas.tenant_id", "qualification_schemas.id"],
            name=op.f("fk_qualification_sessions_tenant_id_schema_id_qualification_schemas"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_qualification_sessions_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_qualification_sessions")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_qualification_sessions_tenant_id_id")),
    )
    op.create_index(
        "ix_qualification_sessions_active_expiry",
        "qualification_sessions",
        ["status", "expires_at"],
    )
    op.create_index(
        "uq_qualification_sessions_tenant_identity_active",
        "qualification_sessions",
        ["tenant_id", "customer_id", "conversation_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('awaiting_consent','in_progress','reviewing')"),
    )

    op.create_table(
        "qualification_consents",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("customer_id", sa.UUID(), nullable=False),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("consent_version", sa.String(50), nullable=False),
        sa.Column("purpose", sa.String(500), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "decision IN ('accepted','declined')",
            name=op.f("ck_qualification_consents_decision_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "customer_id"],
            ["customers.tenant_id", "customers.id"],
            name=op.f("fk_qualification_consents_tenant_id_customer_id_customers"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "session_id"],
            ["qualification_sessions.tenant_id", "qualification_sessions.id"],
            name=op.f("fk_qualification_consents_tenant_id_session_id_qualification_sessions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_qualification_consents_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_qualification_consents")),
        sa.UniqueConstraint(
            "tenant_id", "session_id", name=op.f("uq_qualification_consents_tenant_id_session_id")
        ),
    )

    op.create_table(
        "qualification_session_updates",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("update_key", sa.String(255), nullable=False),
        sa.Column("operation", sa.String(50), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "session_id"],
            ["qualification_sessions.tenant_id", "qualification_sessions.id"],
            name=op.f(
                "fk_qualification_session_updates_tenant_id_session_id_qualification_sessions"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_qualification_session_updates_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_qualification_session_updates")),
        sa.UniqueConstraint(
            "tenant_id",
            "update_key",
            name=op.f("uq_qualification_session_updates_tenant_id_update_key"),
        ),
    )
    op.create_index(
        "ix_qualification_updates_tenant_session",
        "qualification_session_updates",
        ["tenant_id", "session_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_qualification_updates_tenant_session", table_name="qualification_session_updates"
    )
    op.drop_table("qualification_session_updates")
    op.drop_table("qualification_consents")
    op.drop_index(
        "uq_qualification_sessions_tenant_identity_active", table_name="qualification_sessions"
    )
    op.drop_index("ix_qualification_sessions_active_expiry", table_name="qualification_sessions")
    op.drop_table("qualification_sessions")
    op.drop_index(
        "uq_qualification_schemas_tenant_published_code", table_name="qualification_schemas"
    )
    op.drop_table("qualification_schemas")
    op.drop_constraint(
        op.f("uq_handoff_cases_tenant_id_idempotency_key"), "handoff_cases", type_="unique"
    )
    op.drop_constraint(
        op.f("fk_handoff_cases_tenant_id_booking_id_bookings"), "handoff_cases", type_="foreignkey"
    )
    op.drop_constraint(
        op.f("fk_handoff_cases_tenant_id_lead_id_leads"), "handoff_cases", type_="foreignkey"
    )
    op.drop_constraint(
        op.f("fk_handoff_cases_tenant_id_customer_id_customers"),
        "handoff_cases",
        type_="foreignkey",
    )
    op.drop_column("handoff_cases", "idempotency_key")
    op.drop_column("handoff_cases", "context")
    op.drop_column("handoff_cases", "booking_id")
    op.drop_column("handoff_cases", "lead_id")
    op.drop_column("handoff_cases", "customer_id")
    op.drop_column("leads", "qualified_at")
    op.drop_column("leads", "qualification_snapshot")
