"""add Phase 5 availability and booking lifecycle persistence

Revision ID: 0004_phase5
Revises: 0003_phase4
Create Date: 2026-08-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_phase5"
down_revision: str | None = "0003_phase4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "booking_policies",
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("slot_interval_minutes", sa.Integer(), nullable=False),
        sa.Column("booking_horizon_days", sa.Integer(), nullable=False),
        sa.Column("minimum_notice_minutes", sa.Integer(), nullable=False),
        sa.Column("hold_duration_minutes", sa.Integer(), nullable=False),
        sa.Column("draft_expiry_minutes", sa.Integer(), nullable=False),
        sa.Column("change_cutoff_minutes", sa.Integer(), nullable=False),
        sa.Column("customer_name_max_length", sa.Integer(), nullable=False),
        sa.Column("customer_phone_max_length", sa.Integer(), nullable=False),
        sa.Column("customer_note_max_length", sa.Integer(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "booking_horizon_days BETWEEN 1 AND 365",
            name=op.f("ck_booking_policies_horizon_valid"),
        ),
        sa.CheckConstraint(
            "change_cutoff_minutes BETWEEN 0 AND 43200",
            name=op.f("ck_booking_policies_cutoff_valid"),
        ),
        sa.CheckConstraint(
            "customer_name_max_length BETWEEN 1 AND 200",
            name=op.f("ck_booking_policies_name_limit_valid"),
        ),
        sa.CheckConstraint(
            "customer_note_max_length BETWEEN 0 AND 2000",
            name=op.f("ck_booking_policies_note_limit_valid"),
        ),
        sa.CheckConstraint(
            "customer_phone_max_length BETWEEN 8 AND 32",
            name=op.f("ck_booking_policies_phone_limit_valid"),
        ),
        sa.CheckConstraint(
            "draft_expiry_minutes BETWEEN 5 AND 1440",
            name=op.f("ck_booking_policies_draft_expiry_valid"),
        ),
        sa.CheckConstraint(
            "hold_duration_minutes BETWEEN 1 AND 60",
            name=op.f("ck_booking_policies_hold_duration_valid"),
        ),
        sa.CheckConstraint(
            "minimum_notice_minutes BETWEEN 0 AND 43200",
            name=op.f("ck_booking_policies_notice_valid"),
        ),
        sa.CheckConstraint(
            "slot_interval_minutes BETWEEN 5 AND 240",
            name=op.f("ck_booking_policies_slot_interval_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_booking_policies_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("tenant_id", name=op.f("pk_booking_policies")),
    )
    op.create_table(
        "service_resources",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("service_id", sa.UUID(), nullable=False),
        sa.Column("resource_id", sa.UUID(), nullable=False),
        sa.Column("required_capacity", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "required_capacity > 0",
            name=op.f("ck_service_resources_required_capacity_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "resource_id"],
            ["resources.tenant_id", "resources.id"],
            name=op.f("fk_service_resources_tenant_id_resource_id_resources"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "service_id"],
            ["services.tenant_id", "services.id"],
            name=op.f("fk_service_resources_tenant_id_service_id_services"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_service_resources_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_service_resources")),
        sa.UniqueConstraint(
            "tenant_id",
            "service_id",
            "resource_id",
            name=op.f("uq_service_resources_tenant_id_service_id_resource_id"),
        ),
    )
    op.create_index(
        "ix_service_resources_tenant_service",
        "service_resources",
        ["tenant_id", "service_id", "active"],
        unique=False,
    )
    op.create_table(
        "resource_unavailability",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("resource_id", sa.UUID(), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.String(length=200), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "start_at < end_at",
            name=op.f("ck_resource_unavailability_time_order_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "resource_id"],
            ["resources.tenant_id", "resources.id"],
            name=op.f("fk_resource_unavailability_tenant_id_resource_id_resources"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_resource_unavailability_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_resource_unavailability")),
    )
    op.create_index(
        "ix_resource_unavailability_tenant_resource_time",
        "resource_unavailability",
        ["tenant_id", "resource_id", "start_at", "end_at"],
        unique=False,
    )
    op.create_table(
        "booking_drafts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("customer_id", sa.UUID(), nullable=False),
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column("service_id", sa.UUID(), nullable=False),
        sa.Column("selected_date", sa.Date(), nullable=True),
        sa.Column("hold_id", sa.UUID(), nullable=True),
        sa.Column("customer_name", sa.String(length=200), nullable=True),
        sa.Column("customer_phone", sa.String(length=32), nullable=True),
        sa.Column("customer_note", sa.String(length=2000), nullable=True),
        sa.Column("reschedule_booking_id", sa.UUID(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
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
            "status IN ('active','cancelled','expired','confirmed')",
            name=op.f("ck_booking_drafts_status_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "conversation_id"],
            ["conversations.tenant_id", "conversations.id"],
            name=op.f("fk_booking_drafts_tenant_id_conversation_id_conversations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "customer_id"],
            ["customers.tenant_id", "customers.id"],
            name=op.f("fk_booking_drafts_tenant_id_customer_id_customers"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "service_id"],
            ["services.tenant_id", "services.id"],
            name=op.f("fk_booking_drafts_tenant_id_service_id_services"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_booking_drafts_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_booking_drafts")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_booking_drafts_tenant_id_id")),
    )
    op.create_index(
        "ix_booking_drafts_active_expiry",
        "booking_drafts",
        ["status", "expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_booking_drafts_tenant_identity_status",
        "booking_drafts",
        ["tenant_id", "customer_id", "conversation_id", "status"],
        unique=False,
    )
    op.create_table(
        "slot_holds",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("customer_id", sa.UUID(), nullable=False),
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column("draft_id", sa.UUID(), nullable=False),
        sa.Column("service_id", sa.UUID(), nullable=False),
        sa.Column("resource_id", sa.UUID(), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("timezone", sa.String(length=100), nullable=False),
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
        sa.CheckConstraint("start_at < end_at", name=op.f("ck_slot_holds_time_order_valid")),
        sa.CheckConstraint(
            "status IN ('active','released','expired','consumed')",
            name=op.f("ck_slot_holds_status_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "conversation_id"],
            ["conversations.tenant_id", "conversations.id"],
            name=op.f("fk_slot_holds_tenant_id_conversation_id_conversations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "customer_id"],
            ["customers.tenant_id", "customers.id"],
            name=op.f("fk_slot_holds_tenant_id_customer_id_customers"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "draft_id"],
            ["booking_drafts.tenant_id", "booking_drafts.id"],
            name=op.f("fk_slot_holds_tenant_id_draft_id_booking_drafts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "resource_id"],
            ["resources.tenant_id", "resources.id"],
            name=op.f("fk_slot_holds_tenant_id_resource_id_resources"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "service_id"],
            ["services.tenant_id", "services.id"],
            name=op.f("fk_slot_holds_tenant_id_service_id_services"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_slot_holds_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_slot_holds")),
        sa.UniqueConstraint(
            "tenant_id",
            "idempotency_key",
            name=op.f("uq_slot_holds_tenant_id_idempotency_key"),
        ),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_slot_holds_tenant_id_id")),
    )
    op.create_index(
        "ix_slot_holds_active_expiry",
        "slot_holds",
        ["status", "expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_slot_holds_tenant_resource_status_time",
        "slot_holds",
        ["tenant_id", "resource_id", "status", "start_at", "end_at"],
        unique=False,
    )
    op.add_column("bookings", sa.Column("conversation_id", sa.UUID(), nullable=True))
    op.add_column("bookings", sa.Column("hold_id", sa.UUID(), nullable=True))
    op.add_column("bookings", sa.Column("public_reference", sa.String(length=24), nullable=True))
    op.create_foreign_key(
        op.f("fk_bookings_tenant_id_conversation_id_conversations"),
        "bookings",
        "conversations",
        ["tenant_id", "conversation_id"],
        ["tenant_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        op.f("fk_bookings_tenant_id_hold_id_slot_holds"),
        "bookings",
        "slot_holds",
        ["tenant_id", "hold_id"],
        ["tenant_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        op.f("uq_bookings_tenant_id_hold_id"), "bookings", ["tenant_id", "hold_id"]
    )
    op.create_unique_constraint(
        op.f("uq_bookings_tenant_id_public_reference"),
        "bookings",
        ["tenant_id", "public_reference"],
    )


def downgrade() -> None:
    op.drop_constraint(op.f("uq_bookings_tenant_id_public_reference"), "bookings", type_="unique")
    op.drop_constraint(op.f("uq_bookings_tenant_id_hold_id"), "bookings", type_="unique")
    op.drop_constraint(
        op.f("fk_bookings_tenant_id_hold_id_slot_holds"), "bookings", type_="foreignkey"
    )
    op.drop_constraint(
        op.f("fk_bookings_tenant_id_conversation_id_conversations"),
        "bookings",
        type_="foreignkey",
    )
    op.drop_column("bookings", "public_reference")
    op.drop_column("bookings", "hold_id")
    op.drop_column("bookings", "conversation_id")
    op.execute(
        "ALTER TABLE booking_drafts DROP CONSTRAINT IF EXISTS "
        "fk_booking_drafts_tenant_id_hold_id_slot_holds"
    )
    op.drop_index("ix_slot_holds_tenant_resource_status_time", table_name="slot_holds")
    op.drop_index("ix_slot_holds_active_expiry", table_name="slot_holds")
    op.drop_table("slot_holds")
    op.drop_index("ix_booking_drafts_tenant_identity_status", table_name="booking_drafts")
    op.drop_index("ix_booking_drafts_active_expiry", table_name="booking_drafts")
    op.drop_table("booking_drafts")
    op.drop_index(
        "ix_resource_unavailability_tenant_resource_time", table_name="resource_unavailability"
    )
    op.drop_table("resource_unavailability")
    op.drop_index("ix_service_resources_tenant_service", table_name="service_resources")
    op.drop_table("service_resources")
    op.drop_table("booking_policies")
