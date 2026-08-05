"""Persistence-only ORM rows for the Phase 2 PostgreSQL schema."""

from datetime import date, datetime, time
from decimal import Decimal
from typing import Any
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, ExcludeConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from business_assistant.application.observability import current_correlation_id

from .base import Base


class TenantRow(Base):
    __tablename__ = "tenants"
    __table_args__ = (
        CheckConstraint("settings_version >= 1", name="settings_version_positive"),
        CheckConstraint("status IN ('active','suspended','archived')", name="status_allowed"),
        CheckConstraint(
            "(status = 'archived') = (archived_at IS NOT NULL)",
            name="archive_time_consistent",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    timezone: Mapped[str] = mapped_column(String(100), nullable=False)
    default_locale: Mapped[str] = mapped_column(String(10), nullable=False)
    supported_locales: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    status_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    settings_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    __mapper_args__ = {"version_id_col": settings_version}  # noqa: RUF012


class TenantMemberRow(Base):
    __tablename__ = "tenant_members"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "subject"),
        CheckConstraint(
            "role IN ('owner','manager','agent','knowledge_editor','viewer')",
            name="role_allowed",
        ),
        Index("ix_tenant_members_tenant_active", "tenant_id", "active"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class AdministrativeCredentialRow(Base):
    __tablename__ = "administrative_credentials"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "member_id"],
            ["tenant_members.tenant_id", "tenant_members.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("key_prefix"),
        CheckConstraint(
            "role IN ('owner','manager','agent','knowledge_editor','viewer')",
            name="role_allowed",
        ),
        Index("ix_admin_credentials_tenant_active", "tenant_id", "revoked_at", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    member_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(40), nullable=False)
    secret_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rotated_from_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class TenantEntitlementRow(Base):
    __tablename__ = "tenant_entitlements"
    __table_args__ = (
        CheckConstraint(
            "capability IN ('telegram','booking','qualification','ai_routing',"
            "'knowledge_answers','background_notifications')",
            name="capability_allowed",
        ),
        CheckConstraint("version >= 1", name="version_positive"),
        Index("ix_tenant_entitlements_tenant_enabled", "tenant_id", "enabled"),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), primary_key=True
    )
    capability: Mapped[str] = mapped_column(String(50), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    __mapper_args__ = {"version_id_col": version}  # noqa: RUF012


class TenantProvisioningRow(Base):
    __tablename__ = "tenant_provisioning_records"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "owner_member_id"],
            ["tenant_members.tenant_id", "tenant_members.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "credential_id"],
            ["administrative_credentials.tenant_id", "administrative_credentials.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("idempotency_key"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    owner_member_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    credential_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CustomerRow(Base):
    __tablename__ = "customers"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        CheckConstraint(
            "(privacy_notice_version IS NULL) = (privacy_accepted_at IS NULL)",
            name="privacy_acceptance_pair",
        ),
        CheckConstraint("status IN ('active','blocked','anonymized')", name="status_allowed"),
        Index("ix_customers_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    display_name: Mapped[str | None] = mapped_column(String(200))
    phone_raw: Mapped[str | None] = mapped_column(String(32))
    phone_e164: Mapped[str | None] = mapped_column(String(16))
    phone_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    email: Mapped[str | None] = mapped_column(String(254))
    locale: Mapped[str] = mapped_column(String(10), nullable=False)
    privacy_notice_version: Mapped[str | None] = mapped_column(String(50))
    privacy_accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    contact_consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class ChannelIdentityRow(Base):
    __tablename__ = "channel_identities"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "customer_id"],
            ["customers.tenant_id", "customers.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "channel", "external_user_id"),
        Index("ix_channel_identities_tenant_customer", "tenant_id", "customer_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    customer_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    external_user_id: Mapped[str] = mapped_column(String(100), nullable=False)
    external_chat_id: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ConversationRow(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "customer_id"],
            ["customers.tenant_id", "customers.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "channel_identity_id"],
            ["channel_identities.tenant_id", "channel_identities.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("tenant_id", "id"),
        CheckConstraint("summary_version >= 0", name="summary_version_nonnegative"),
        CheckConstraint(
            "status IN ('active_bot','handoff_queued','human_active','closed')",
            name="status_allowed",
        ),
        Index("ix_conversations_tenant_customer", "tenant_id", "customer_id"),
        Index("ix_conversations_tenant_last_message", "tenant_id", "last_message_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    customer_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    channel_identity_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    locale: Mapped[str] = mapped_column(String(10), nullable=False)
    active_workflow: Mapped[str | None] = mapped_column(String(100))
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    summary_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class MessageRow(Base):
    __tablename__ = "messages"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "conversation_id"],
            ["conversations.tenant_id", "conversations.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("tenant_id", "channel", "channel_account_id", "external_update_id"),
        Index(
            "ix_messages_tenant_conversation_created", "tenant_id", "conversation_id", "created_at"
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    conversation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    channel_account_id: Mapped[str] = mapped_column(String(100), nullable=False)
    external_update_id: Mapped[str | None] = mapped_column(String(100))
    channel_message_id: Mapped[str | None] = mapped_column(String(100))
    content_type: Mapped[str] = mapped_column(String(32), nullable=False)
    redacted_text: Mapped[str | None] = mapped_column(Text)
    raw_payload_reference: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    correlation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class TelegramUpdateRow(Base):
    __tablename__ = "telegram_updates"
    __table_args__ = (
        UniqueConstraint("tenant_id", "bot_id", "update_id"),
        CheckConstraint("bot_id > 0", name="bot_id_positive"),
        CheckConstraint("update_id >= 0", name="update_id_nonnegative"),
        CheckConstraint("attempts >= 1", name="attempts_positive"),
        CheckConstraint("status IN ('processing','completed','failed')", name="status_allowed"),
        Index("ix_telegram_updates_terminal_created", "status", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    bot_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    update_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    claimed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class ServiceCategoryRow(Base):
    __tablename__ = "service_categories"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        CheckConstraint("sort_order >= 0", name="sort_order_nonnegative"),
        Index("ix_service_categories_tenant_active_sort", "tenant_id", "active", "sort_order"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    names: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class ServiceRow(Base):
    __tablename__ = "services"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "category_id"],
            ["service_categories.tenant_id", "service_categories.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "code"),
        CheckConstraint("duration_seconds > 0", name="duration_positive"),
        CheckConstraint("buffer_seconds >= 0", name="buffer_nonnegative"),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint(
            "price_mode IN ('exact','range','starting_from','quote_required','not_displayed')",
            name="price_mode_allowed",
        ),
        CheckConstraint(
            "(price_mode IN ('exact','starting_from') AND price_min_minor IS NOT NULL "
            "AND price_max_minor IS NULL AND currency IS NOT NULL) OR "
            "(price_mode = 'range' AND price_min_minor IS NOT NULL "
            "AND price_max_minor IS NOT NULL AND price_min_minor <= price_max_minor "
            "AND currency IS NOT NULL) OR "
            "(price_mode IN ('quote_required','not_displayed') AND price_min_minor IS NULL "
            "AND price_max_minor IS NULL AND currency IS NULL)",
            name="price_shape_valid",
        ),
        Index("ix_services_tenant_category_active", "tenant_id", "category_id", "active"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    category_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    names: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False)
    descriptions: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    buffer_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    price_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    price_min_minor: Mapped[int | None] = mapped_column(BigInteger)
    price_max_minor: Mapped[int | None] = mapped_column(BigInteger)
    currency: Mapped[str | None] = mapped_column(String(3))
    preparation_notes: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False, default=dict)
    eligibility_notes: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    bookable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    __mapper_args__ = {"version_id_col": version}  # noqa: RUF012


class BusinessScheduleRow(Base):
    __tablename__ = "business_schedules"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "name"),
        Index("ix_business_schedules_tenant_active", "tenant_id", "active"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    timezone: Mapped[str] = mapped_column(String(100), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class TenantPublicProfileRow(Base):
    __tablename__ = "tenant_public_profiles"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "schedule_id"],
            ["business_schedules.tenant_id", "business_schedules.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("version >= 1", name="version_positive"),
        Index("ix_tenant_public_profiles_tenant_schedule", "tenant_id", "schedule_id"),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), primary_key=True
    )
    schedule_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    descriptions: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False)
    public_phone: Mapped[str | None] = mapped_column(String(32))
    public_email: Mapped[str | None] = mapped_column(String(254))
    website_url: Mapped[str | None] = mapped_column(String(500))
    addresses: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False, default=dict)
    service_areas: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False, default=dict)
    parking_guidance: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False, default=dict)
    payment_methods: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    warranty_policy: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False, default=dict)
    appointment_policy: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False, default=dict)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    __mapper_args__ = {"version_id_col": version}  # noqa: RUF012


class ScheduleIntervalRow(Base):
    __tablename__ = "schedule_intervals"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "schedule_id"],
            ["business_schedules.tenant_id", "business_schedules.id"],
            ondelete="CASCADE",
        ),
        CheckConstraint("weekday BETWEEN 0 AND 6", name="weekday_valid"),
        CheckConstraint("start_local < end_local", name="time_order_valid"),
        CheckConstraint("interval_type IN ('open','break')", name="interval_type_allowed"),
        Index("ix_schedule_intervals_tenant_schedule", "tenant_id", "schedule_id", "weekday"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    schedule_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)
    start_local: Mapped[time] = mapped_column(Time(timezone=False), nullable=False)
    end_local: Mapped[time] = mapped_column(Time(timezone=False), nullable=False)
    interval_type: Mapped[str] = mapped_column(String(16), nullable=False)


class ScheduleOverrideRow(Base):
    __tablename__ = "schedule_overrides"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "schedule_id"],
            ["business_schedules.tenant_id", "business_schedules.id"],
            ondelete="CASCADE",
        ),
        CheckConstraint("starts_on <= ends_on", name="date_order_valid"),
        CheckConstraint(
            "(closed AND jsonb_array_length(intervals) = 0) OR "
            "(NOT closed AND jsonb_array_length(intervals) > 0)",
            name="override_intervals_valid",
        ),
        Index(
            "ix_schedule_overrides_tenant_schedule_dates",
            "tenant_id",
            "schedule_id",
            "starts_on",
            "ends_on",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    schedule_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    ends_on: Mapped[date] = mapped_column(Date, nullable=False)
    closed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    intervals: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    reason: Mapped[str | None] = mapped_column(String(500))


class ResourceRow(Base):
    __tablename__ = "resources"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "schedule_id"],
            ["business_schedules.tenant_id", "business_schedules.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("tenant_id", "id"),
        CheckConstraint("capacity > 0", name="capacity_positive"),
        Index("ix_resources_tenant_active", "tenant_id", "active"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    schedule_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class BookingPolicyRow(Base):
    __tablename__ = "booking_policies"
    __table_args__ = (
        CheckConstraint("slot_interval_minutes BETWEEN 5 AND 240", name="slot_interval_valid"),
        CheckConstraint("booking_horizon_days BETWEEN 1 AND 365", name="horizon_valid"),
        CheckConstraint("minimum_notice_minutes BETWEEN 0 AND 43200", name="notice_valid"),
        CheckConstraint("hold_duration_minutes BETWEEN 1 AND 60", name="hold_duration_valid"),
        CheckConstraint("draft_expiry_minutes BETWEEN 5 AND 1440", name="draft_expiry_valid"),
        CheckConstraint("change_cutoff_minutes BETWEEN 0 AND 43200", name="cutoff_valid"),
        CheckConstraint("customer_name_max_length BETWEEN 1 AND 200", name="name_limit_valid"),
        CheckConstraint("customer_phone_max_length BETWEEN 8 AND 32", name="phone_limit_valid"),
        CheckConstraint("customer_note_max_length BETWEEN 0 AND 2000", name="note_limit_valid"),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), primary_key=True
    )
    slot_interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    booking_horizon_days: Mapped[int] = mapped_column(Integer, nullable=False)
    minimum_notice_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    hold_duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    draft_expiry_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    change_cutoff_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    customer_name_max_length: Mapped[int] = mapped_column(Integer, nullable=False)
    customer_phone_max_length: Mapped[int] = mapped_column(Integer, nullable=False)
    customer_note_max_length: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class ServiceResourceRow(Base):
    __tablename__ = "service_resources"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "service_id"],
            ["services.tenant_id", "services.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "resource_id"],
            ["resources.tenant_id", "resources.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("tenant_id", "service_id", "resource_id"),
        CheckConstraint("required_capacity > 0", name="required_capacity_positive"),
        Index("ix_service_resources_tenant_service", "tenant_id", "service_id", "active"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    service_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    resource_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    required_capacity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class ResourceUnavailabilityRow(Base):
    __tablename__ = "resource_unavailability"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "resource_id"],
            ["resources.tenant_id", "resources.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("start_at < end_at", name="time_order_valid"),
        Index(
            "ix_resource_unavailability_tenant_resource_time",
            "tenant_id",
            "resource_id",
            "start_at",
            "end_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    resource_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(200))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class BookingDraftRow(Base):
    __tablename__ = "booking_drafts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "customer_id"],
            ["customers.tenant_id", "customers.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "conversation_id"],
            ["conversations.tenant_id", "conversations.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "service_id"],
            ["services.tenant_id", "services.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("tenant_id", "id"),
        CheckConstraint(
            "status IN ('active','cancelled','expired','confirmed')", name="status_allowed"
        ),
        Index(
            "ix_booking_drafts_tenant_identity_status",
            "tenant_id",
            "customer_id",
            "conversation_id",
            "status",
        ),
        Index("ix_booking_drafts_active_expiry", "status", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    customer_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    conversation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    service_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    selected_date: Mapped[date | None] = mapped_column(Date)
    hold_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    customer_name: Mapped[str | None] = mapped_column(String(200))
    customer_phone: Mapped[str | None] = mapped_column(String(32))
    customer_note: Mapped[str | None] = mapped_column(String(2000))
    reschedule_booking_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class SlotHoldRow(Base):
    __tablename__ = "slot_holds"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "customer_id"],
            ["customers.tenant_id", "customers.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "conversation_id"],
            ["conversations.tenant_id", "conversations.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "draft_id"],
            ["booking_drafts.tenant_id", "booking_drafts.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "service_id"],
            ["services.tenant_id", "services.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "resource_id"],
            ["resources.tenant_id", "resources.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "idempotency_key"),
        CheckConstraint("start_at < end_at", name="time_order_valid"),
        CheckConstraint(
            "status IN ('active','released','expired','consumed')", name="status_allowed"
        ),
        Index(
            "ix_slot_holds_tenant_resource_status_time",
            "tenant_id",
            "resource_id",
            "status",
            "start_at",
            "end_at",
        ),
        Index("ix_slot_holds_active_expiry", "status", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    customer_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    conversation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    draft_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    service_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    resource_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    timezone: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class BookingRow(Base):
    __tablename__ = "bookings"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    customer_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    service_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    resource_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    conversation_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    hold_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    public_reference: Mapped[str | None] = mapped_column(String(24))
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    idempotency_scope: Mapped[str] = mapped_column(String(100), nullable=False)
    idempotency_value: Mapped[str] = mapped_column(String(255), nullable=False)
    idempotency_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    service_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    customer_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="internal")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "conversation_id"],
            ["conversations.tenant_id", "conversations.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "hold_id"],
            ["slot_holds.tenant_id", "slot_holds.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "customer_id"],
            ["customers.tenant_id", "customers.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "service_id"],
            ["services.tenant_id", "services.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "resource_id"],
            ["resources.tenant_id", "resources.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "public_reference"),
        UniqueConstraint("tenant_id", "hold_id"),
        UniqueConstraint("tenant_id", "idempotency_scope", "idempotency_value"),
        CheckConstraint("start_at < end_at", name="time_order_valid"),
        CheckConstraint(
            "status IN ('draft','held','confirmed','completed','cancelled','no_show',"
            "'reschedule_pending','expired')",
            name="status_allowed",
        ),
        ExcludeConstraint(
            ("tenant_id", "="),
            ("resource_id", "="),
            (func.tstzrange(start_at, end_at, "[)"), "&&"),
            where=text(
                "resource_id IS NOT NULL AND status IN ('held','confirmed','reschedule_pending')"
            ),
            using="gist",
            name="ex_bookings_resource_active_overlap",
        ),
        Index("ix_bookings_tenant_customer_start", "tenant_id", "customer_id", "start_at"),
        Index("ix_bookings_tenant_status_start", "tenant_id", "status", "start_at"),
    )


class BookingStatusHistoryRow(Base):
    __tablename__ = "booking_status_history"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "booking_id"],
            ["bookings.tenant_id", "bookings.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("booking_id", "sequence"),
        CheckConstraint("sequence >= 1", name="sequence_positive"),
        Index("ix_booking_history_tenant_booking", "tenant_id", "booking_id", "sequence"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    booking_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    from_status: Mapped[str] = mapped_column(String(32), nullable=False)
    to_status: Mapped[str] = mapped_column(String(32), nullable=False)
    actor: Mapped[str] = mapped_column(String(100), nullable=False, default="domain")
    reason: Mapped[str | None] = mapped_column(String(500))
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class LeadRow(Base):
    __tablename__ = "leads"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "customer_id"],
            ["customers.tenant_id", "customers.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "conversation_id"],
            ["conversations.tenant_id", "conversations.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("tenant_id", "id"),
        CheckConstraint("schema_version >= 1", name="schema_version_positive"),
        CheckConstraint("score IS NULL OR score BETWEEN 0 AND 100", name="score_valid"),
        CheckConstraint(
            "status IN ('new','qualifying','qualified','contacted','converted',"
            "'unqualified','closed')",
            name="status_allowed",
        ),
        Index("ix_leads_tenant_status_priority", "tenant_id", "status", "priority"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    customer_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    conversation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    schema_code: Mapped[str] = mapped_column(String(100), nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    answers: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    score: Mapped[int | None] = mapped_column(Integer)
    priority: Mapped[str | None] = mapped_column(String(16))
    score_explanation: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    qualification_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    qualified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class HandoffCaseRow(Base):
    __tablename__ = "handoff_cases"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "conversation_id"],
            ["conversations.tenant_id", "conversations.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "customer_id"],
            ["customers.tenant_id", "customers.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "lead_id"],
            ["leads.tenant_id", "leads.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "booking_id"],
            ["bookings.tenant_id", "bookings.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "idempotency_key"),
        CheckConstraint(
            "status IN ('queued','claimed','resolved','reopened','cancelled')",
            name="status_allowed",
        ),
        Index(
            "ix_handoff_cases_tenant_open",
            "tenant_id",
            "status",
            postgresql_where=text("status IN ('queued','claimed','reopened')"),
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    conversation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    customer_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    lead_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    booking_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    reason_code: Mapped[str] = mapped_column(String(100), nullable=False)
    priority: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    assignee_id: Mapped[str | None] = mapped_column(String(100))
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    idempotency_key: Mapped[str | None] = mapped_column(String(255))
    response_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class QualificationSchemaRow(Base):
    __tablename__ = "qualification_schemas"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "code", "version"),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint("config_version >= 1", name="config_version_positive"),
        CheckConstraint("session_ttl_minutes BETWEEN 5 AND 10080", name="session_ttl_valid"),
        CheckConstraint(
            "handoff_response_minutes BETWEEN 1 AND 10080",
            name="handoff_response_valid",
        ),
        Index(
            "uq_qualification_schemas_tenant_published_code",
            "tenant_id",
            "code",
            unique=True,
            postgresql_where=text("published AND active"),
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    consent_version: Mapped[str] = mapped_column(String(50), nullable=False)
    consent_purpose: Mapped[str] = mapped_column(String(500), nullable=False)
    definition: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    grade_bands: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    session_ttl_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    handoff_response_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    config_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    __mapper_args__ = {"version_id_col": config_version}  # noqa: RUF012


class QualificationSessionRow(Base):
    __tablename__ = "qualification_sessions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "customer_id"],
            ["customers.tenant_id", "customers.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "conversation_id"],
            ["conversations.tenant_id", "conversations.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "schema_id"],
            ["qualification_schemas.tenant_id", "qualification_schemas.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "lead_id"],
            ["leads.tenant_id", "leads.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("tenant_id", "id"),
        CheckConstraint("schema_version >= 1", name="schema_version_positive"),
        CheckConstraint("revision >= 1", name="revision_positive"),
        CheckConstraint(
            "status IN ('awaiting_consent','in_progress','reviewing','completed',"
            "'declined','cancelled','expired')",
            name="status_allowed",
        ),
        CheckConstraint(
            "consent_decision IS NULL OR consent_decision IN ('accepted','declined')",
            name="consent_decision_allowed",
        ),
        Index(
            "uq_qualification_sessions_tenant_identity_active",
            "tenant_id",
            "customer_id",
            "conversation_id",
            unique=True,
            postgresql_where=text("status IN ('awaiting_consent','in_progress','reviewing')"),
        ),
        Index("ix_qualification_sessions_active_expiry", "status", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    customer_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    conversation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    schema_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    schema_code: Mapped[str] = mapped_column(String(100), nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    answers: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    current_field_key: Mapped[str | None] = mapped_column(String(100))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consent_decision: Mapped[str | None] = mapped_column(String(16))
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lead_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    __mapper_args__ = {"version_id_col": revision}  # noqa: RUF012


class QualificationConsentRow(Base):
    __tablename__ = "qualification_consents"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "session_id"],
            ["qualification_sessions.tenant_id", "qualification_sessions.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "customer_id"],
            ["customers.tenant_id", "customers.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("tenant_id", "session_id"),
        CheckConstraint("decision IN ('accepted','declined')", name="decision_allowed"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    session_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    customer_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    consent_version: Mapped[str] = mapped_column(String(50), nullable=False)
    purpose: Mapped[str] = mapped_column(String(500), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class QualificationSessionUpdateRow(Base):
    __tablename__ = "qualification_session_updates"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "session_id"],
            ["qualification_sessions.tenant_id", "qualification_sessions.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("tenant_id", "update_key"),
        Index("ix_qualification_updates_tenant_session", "tenant_id", "session_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    session_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    update_key: Mapped[str] = mapped_column(String(255), nullable=False)
    operation: Mapped[str] = mapped_column(String(50), nullable=False)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class KnowledgeDocumentRow(Base):
    __tablename__ = "knowledge_documents"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "id", "version"),
        UniqueConstraint("tenant_id", "checksum", "version"),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint(
            "published_at IS NULL OR status = 'ready'", name="publication_requires_ready"
        ),
        CheckConstraint(
            "status IN ('uploaded','parsing','chunking','embedding','ready','failed','archived')",
            name="status_allowed",
        ),
        Index(
            "ix_knowledge_documents_tenant_searchable",
            "tenant_id",
            "locale",
            postgresql_where=text("status = 'ready' AND published_at IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    locale: Mapped[str] = mapped_column(String(10), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    source_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    effective_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class KnowledgeChunkRow(Base):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "document_id", "document_version"],
            [
                "knowledge_documents.tenant_id",
                "knowledge_documents.id",
                "knowledge_documents.version",
            ],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("tenant_id", "document_id", "document_version", "ordinal"),
        CheckConstraint("ordinal >= 0", name="ordinal_nonnegative"),
        CheckConstraint("token_count >= 0", name="token_count_nonnegative"),
        CheckConstraint(
            "(embedding IS NULL AND embedding_model IS NULL AND embedding_dimensions IS NULL) "
            "OR (embedding IS NOT NULL AND embedding_model IS NOT NULL "
            "AND embedding_dimensions = vector_dims(embedding))",
            name="embedding_metadata_consistent",
        ),
        Index(
            "ix_knowledge_chunks_tenant_document", "tenant_id", "document_id", "document_version"
        ),
        Index("ix_knowledge_chunks_search_vector", "search_vector", postgresql_using="gin"),
        Index(
            "ix_knowledge_chunks_tenant_embedding",
            "tenant_id",
            "embedding_model",
            "embedding_dimensions",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    document_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    document_version: Mapped[int] = mapped_column(Integer, nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    search_vector: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('simple', coalesce(chunk_text, ''))", persisted=True),
        nullable=False,
    )
    embedding: Mapped[list[float] | None] = mapped_column(Vector())
    embedding_model: Mapped[str | None] = mapped_column(String(200))
    embedding_dimensions: Mapped[int | None] = mapped_column(Integer)
    instruction_risk: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
    checksum: Mapped[str] = mapped_column(String(128), nullable=False)


class AIOperationRow(Base):
    __tablename__ = "ai_operations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "conversation_id"],
            ["conversations.tenant_id", "conversations.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "task IN ('intent','extraction','classification','rewrite','summary')",
            name="task_allowed",
        ),
        CheckConstraint(
            "status IN ('success','fallback','disabled','cancelled')",
            name="status_allowed",
        ),
        CheckConstraint("attempts >= 0", name="attempts_nonnegative"),
        CheckConstraint("latency_ms >= 0", name="latency_nonnegative"),
        CheckConstraint("input_tokens >= 0 AND output_tokens >= 0", name="tokens_nonnegative"),
        CheckConstraint("estimated_cost >= 0", name="cost_nonnegative"),
        CheckConstraint("prompt_version >= 0", name="prompt_version_nonnegative"),
        Index("ix_ai_operations_tenant_created", "tenant_id", "created_at"),
        Index("ix_ai_operations_tenant_conversation", "tenant_id", "conversation_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    conversation_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    correlation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    task: Mapped[str] = mapped_column(String(32), nullable=False)
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    prompt_id: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[int] = mapped_column(Integer, nullable=False)
    schema_id: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    estimated_cost: Mapped[Decimal] = mapped_column(Numeric(20, 10), nullable=False)
    failure_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RetentionPolicyRow(Base):
    __tablename__ = "retention_policies"
    __table_args__ = (
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint(
            "operational_metadata_days BETWEEN 1 AND 3650 "
            "AND message_content_days BETWEEN 1 AND 3650 "
            "AND customer_contact_days BETWEEN 1 AND 3650 "
            "AND workflow_records_days BETWEEN 1 AND 3650 "
            "AND knowledge_archive_days BETWEEN 1 AND 3650 "
            "AND ai_telemetry_days BETWEEN 1 AND 3650",
            name="periods_valid",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    operational_metadata_days: Mapped[int] = mapped_column(Integer, nullable=False)
    message_content_days: Mapped[int] = mapped_column(Integer, nullable=False)
    customer_contact_days: Mapped[int] = mapped_column(Integer, nullable=False)
    workflow_records_days: Mapped[int] = mapped_column(Integer, nullable=False)
    knowledge_archive_days: Mapped[int] = mapped_column(Integer, nullable=False)
    ai_telemetry_days: Mapped[int] = mapped_column(Integer, nullable=False)
    automatic_execution_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    __mapper_args__ = {"version_id_col": version}  # noqa: RUF012


class PrivacyActionRow(Base):
    __tablename__ = "privacy_actions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "idempotency_key"),
        CheckConstraint(
            "action_type IN ('customer_anonymization','retention_execution')",
            name="action_type_allowed",
        ),
        CheckConstraint("status = 'completed'", name="status_allowed"),
        CheckConstraint("policy_version >= 1", name="policy_version_positive"),
        Index("ix_privacy_actions_tenant_occurred", "tenant_id", "occurred_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    action_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(50))
    target_id: Mapped[str | None] = mapped_column(String(100))
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(100), nullable=False)
    policy_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    result_counts: Mapped[dict[str, int]] = mapped_column(JSONB, nullable=False)
    requested_by: Mapped[str] = mapped_column(String(100), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AuditEventRow(Base):
    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_events_tenant_occurred", "tenant_id", "occurred_at"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    actor_type: Mapped[str] = mapped_column(String(50), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(100))
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    target_type: Mapped[str] = mapped_column(String(100), nullable=False)
    target_id: Mapped[str] = mapped_column(String(100), nullable=False)
    safe_diff: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    correlation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class OutboxEventRow(Base):
    __tablename__ = "outbox_events"
    __table_args__ = (
        UniqueConstraint("tenant_id", "event_id"),
        CheckConstraint("attempts >= 0", name="attempts_nonnegative"),
        CheckConstraint("event_version >= 1", name="event_version_positive"),
        CheckConstraint(
            "status IN ('pending','processing','published','dead_letter')", name="status_allowed"
        ),
        Index(
            "ix_outbox_events_tenant_pending",
            "tenant_id",
            "available_at",
            postgresql_where=text("status = 'pending'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    event_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    correlation_id: Mapped[str] = mapped_column(
        String(128), nullable=False, default=current_correlation_id
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    aggregate_type: Mapped[str] = mapped_column(String(100), nullable=False)
    aggregate_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    event_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(64))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class NotificationSubscriptionRow(Base):
    __tablename__ = "notification_subscriptions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "channel", "recipient_id"),
        CheckConstraint("channel = 'telegram'", name="channel_allowed"),
        Index("ix_notification_subscriptions_tenant_enabled", "tenant_id", "enabled"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    recipient_id: Mapped[str] = mapped_column(String(100), nullable=False)
    event_types: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class NotificationDeliveryRow(Base):
    __tablename__ = "notification_deliveries"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "subscription_id"],
            ["notification_subscriptions.tenant_id", "notification_subscriptions.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("tenant_id", "event_id", "subscription_id"),
        CheckConstraint("attempts >= 0", name="attempts_nonnegative"),
        CheckConstraint(
            "status IN ('pending','processing','sent','dead_letter')", name="status_allowed"
        ),
        Index(
            "ix_notification_deliveries_due",
            "available_at",
            postgresql_where=text("status = 'pending'"),
        ),
        Index("ix_notification_deliveries_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    event_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    correlation_id: Mapped[str] = mapped_column(
        String(128), nullable=False, default=current_correlation_id
    )
    subscription_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    recipient_id: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class WorkerRunRow(Base):
    __tablename__ = "worker_runs"
    __table_args__ = (
        CheckConstraint("status IN ('success','failed')", name="status_allowed"),
        CheckConstraint("processed_count >= 0", name="processed_count_nonnegative"),
        Index("ix_worker_runs_tenant_task_finished", "tenant_id", "task_name", "finished_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    correlation_id: Mapped[str] = mapped_column(
        String(128), nullable=False, default=current_correlation_id
    )
    tenant_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT")
    )
    task_name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    processed_count: Mapped[int] = mapped_column(Integer, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
