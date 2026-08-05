"""add Phase 12 tenant control plane

Revision ID: 0011_phase12
Revises: 0010_phase11
Create Date: 2026-08-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_phase12"
down_revision: str | None = "0010_phase11"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CAPABILITIES = (
    "telegram",
    "booking",
    "qualification",
    "ai_routing",
    "knowledge_answers",
    "background_notifications",
)


def upgrade() -> None:
    op.drop_constraint(op.f("ck_tenants_status_allowed"), "tenants", type_="check")
    op.execute("UPDATE tenants SET status = 'suspended' WHERE status = 'inactive'")
    op.add_column(
        "tenants",
        sa.Column(
            "status_changed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.add_column("tenants", sa.Column("archived_at", sa.DateTime(timezone=True)))
    op.create_check_constraint(
        op.f("ck_tenants_status_allowed"),
        "tenants",
        "status IN ('active','suspended','archived')",
    )
    op.create_check_constraint(
        op.f("ck_tenants_archive_time_consistent"),
        "tenants",
        "(status = 'archived') = (archived_at IS NOT NULL)",
    )
    op.create_table(
        "tenant_members",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subject", sa.String(200), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "role IN ('owner','manager','agent','knowledge_editor','viewer')",
            name=op.f("ck_tenant_members_role_allowed"),
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id"),
        sa.UniqueConstraint("tenant_id", "subject"),
    )
    op.create_index("ix_tenant_members_tenant_active", "tenant_members", ["tenant_id", "active"])
    op.create_table(
        "administrative_credentials",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("member_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("key_prefix", sa.String(40), nullable=False),
        sa.Column("secret_hash", sa.String(512), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column("rotated_from_id", postgresql.UUID(as_uuid=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "role IN ('owner','manager','agent','knowledge_editor','viewer')",
            name=op.f("ck_administrative_credentials_role_allowed"),
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "member_id"],
            ["tenant_members.tenant_id", "tenant_members.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id"),
        sa.UniqueConstraint("key_prefix"),
    )
    op.create_index(
        "ix_admin_credentials_tenant_active",
        "administrative_credentials",
        ["tenant_id", "revoked_at", "expires_at"],
    )
    op.create_table(
        "tenant_entitlements",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("capability", sa.String(50), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "capability IN ('telegram','booking','qualification','ai_routing',"
            "'knowledge_answers','background_notifications')",
            name=op.f("ck_tenant_entitlements_capability_allowed"),
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_tenant_entitlements_version_positive")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("tenant_id", "capability"),
    )
    op.create_index(
        "ix_tenant_entitlements_tenant_enabled", "tenant_entitlements", ["tenant_id", "enabled"]
    )
    op.create_table(
        "tenant_provisioning_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("owner_member_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("credential_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "owner_member_id"],
            ["tenant_members.tenant_id", "tenant_members.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "credential_id"],
            ["administrative_credentials.tenant_id", "administrative_credentials.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.execute(
        "INSERT INTO tenant_members (id, tenant_id, subject, role, active) "
        "SELECT gen_random_uuid(), id, 'migration-owner-' || id::text, 'owner', true FROM tenants"
    )
    for capability in _CAPABILITIES:
        op.execute(
            sa.text(
                "INSERT INTO tenant_entitlements (tenant_id, capability, enabled, version) "
                "SELECT id, :capability, :enabled, 1 FROM tenants"
            ).bindparams(capability=capability, enabled=True)
        )


def downgrade() -> None:
    op.drop_table("tenant_provisioning_records")
    op.drop_index("ix_tenant_entitlements_tenant_enabled", table_name="tenant_entitlements")
    op.drop_table("tenant_entitlements")
    op.drop_index("ix_admin_credentials_tenant_active", table_name="administrative_credentials")
    op.drop_table("administrative_credentials")
    op.drop_index("ix_tenant_members_tenant_active", table_name="tenant_members")
    op.drop_table("tenant_members")
    op.drop_constraint(op.f("ck_tenants_archive_time_consistent"), "tenants", type_="check")
    op.drop_constraint(op.f("ck_tenants_status_allowed"), "tenants", type_="check")
    op.execute("UPDATE tenants SET status = 'inactive' WHERE status = 'suspended'")
    op.execute("UPDATE tenants SET status = 'inactive' WHERE status = 'archived'")
    op.drop_column("tenants", "archived_at")
    op.drop_column("tenants", "status_changed_at")
    op.create_check_constraint(
        op.f("ck_tenants_status_allowed"), "tenants", "status IN ('active','inactive')"
    )
