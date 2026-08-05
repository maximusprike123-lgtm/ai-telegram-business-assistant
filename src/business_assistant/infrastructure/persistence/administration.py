"""PostgreSQL tenant administration, provisioning, and access-policy adapter."""

from datetime import UTC, datetime
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from business_assistant.application.administration import (
    AdministrationError,
    Capability,
    CredentialMaterial,
    CredentialView,
    EntitlementView,
    MemberView,
    ProvisioningResult,
    ProvisionTenant,
    TenantView,
)
from business_assistant.application.common.security import Role
from business_assistant.application.observability import current_correlation_id
from business_assistant.domain.shared import Locale, TenantId
from business_assistant.domain.tenants import Tenant, TenantStatus

from .sqlalchemy.models import (
    AdministrativeCredentialRow,
    AuditEventRow,
    BusinessScheduleRow,
    RetentionPolicyRow,
    TenantEntitlementRow,
    TenantMemberRow,
    TenantProvisioningRow,
    TenantPublicProfileRow,
    TenantRow,
)


class SQLAlchemyTenantAdministrationStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def provision(
        self, request: ProvisionTenant, material: CredentialMaterial
    ) -> ProvisioningResult:
        now = datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            await session.execute(
                select(
                    func.pg_advisory_xact_lock(func.hashtextextended(request.idempotency_key, 0))
                )
            )
            replay = await session.scalar(
                select(TenantProvisioningRow).where(
                    TenantProvisioningRow.idempotency_key == request.idempotency_key
                )
            )
            if replay is not None:
                if replay.tenant_id != request.tenant_id.value:
                    raise AdministrationError(
                        "Provisioning key conflicts with another tenant",
                        code="administration.idempotency_conflict",
                    )
                return await self._provisioning_result(session, replay, secret=None, created=False)
            if await session.get(TenantRow, request.tenant_id.value) is not None:
                raise AdministrationError(
                    "Tenant already exists", code="administration.tenant_conflict"
                )
            if await session.scalar(select(TenantRow.id).where(TenantRow.slug == request.slug)):
                raise AdministrationError(
                    "Tenant slug already exists", code="administration.tenant_conflict"
                )
            tenant = TenantRow(
                id=request.tenant_id.value,
                slug=request.slug,
                name=request.name.strip(),
                timezone=request.timezone,
                default_locale=request.default_locale.value,
                supported_locales=[request.default_locale.value],
                status=TenantStatus.SUSPENDED.value,
                status_changed_at=now,
                archived_at=None,
                settings_version=1,
            )
            schedule_id = uuid5(NAMESPACE_URL, f"business-assistant:{request.tenant_id}:schedule")
            member_id, credential_id = uuid4(), uuid4()
            session.add(tenant)
            await session.flush()
            session.add_all(
                [
                    BusinessScheduleRow(
                        id=schedule_id,
                        tenant_id=request.tenant_id.value,
                        name="Default business hours",
                        timezone=request.timezone,
                        active=False,
                    ),
                    TenantPublicProfileRow(
                        tenant_id=request.tenant_id.value,
                        schedule_id=schedule_id,
                        descriptions={
                            request.default_locale.value: "Business profile pending setup."
                        },
                        addresses={},
                        service_areas={},
                        parking_guidance={},
                        payment_methods=[],
                        warranty_policy={},
                        appointment_policy={},
                        version=1,
                    ),
                    TenantMemberRow(
                        id=member_id,
                        tenant_id=request.tenant_id.value,
                        subject=request.owner_subject,
                        role=Role.OWNER.value,
                        active=True,
                        created_at=now,
                        updated_at=now,
                    ),
                    RetentionPolicyRow(
                        tenant_id=request.tenant_id.value,
                        version=1,
                        operational_metadata_days=30,
                        message_content_days=90,
                        customer_contact_days=365,
                        workflow_records_days=730,
                        knowledge_archive_days=365,
                        ai_telemetry_days=90,
                        automatic_execution_enabled=(
                            Capability.AUTOMATIC_RETENTION in request.entitlements
                        ),
                    ),
                ]
            )
            for capability in Capability:
                if capability is Capability.AUTOMATIC_RETENTION:
                    continue
                session.add(
                    TenantEntitlementRow(
                        tenant_id=request.tenant_id.value,
                        capability=capability.value,
                        enabled=capability in request.entitlements,
                        version=1,
                    )
                )
            await session.flush()
            session.add(
                AdministrativeCredentialRow(
                    id=credential_id,
                    tenant_id=request.tenant_id.value,
                    member_id=member_id,
                    name=request.credential_name,
                    key_prefix=material.prefix,
                    secret_hash=material.secret_hash,
                    role=Role.OWNER.value,
                    created_at=now,
                )
            )
            await session.flush()
            record = TenantProvisioningRow(
                id=uuid4(),
                tenant_id=request.tenant_id.value,
                idempotency_key=request.idempotency_key,
                owner_member_id=member_id,
                credential_id=credential_id,
                created_at=now,
            )
            session.add(record)
            self._audit(
                session,
                request.tenant_id,
                "system_bootstrap",
                "tenant.provisioned",
                "tenant",
                str(request.tenant_id),
                {"status": TenantStatus.SUSPENDED.value},
                now,
            )
            await session.flush()
            return await self._provisioning_result(
                session, record, secret=material.plaintext, created=True
            )

    async def tenant(self, tenant_id: TenantId) -> TenantView | None:
        async with self._session_factory() as session:
            row = await session.get(TenantRow, tenant_id.value)
            return _tenant(row) if row is not None else None

    async def update_tenant(
        self,
        tenant_id: TenantId,
        *,
        name: str,
        timezone: str,
        default_locale: Locale,
        expected_version: int,
        actor: str,
    ) -> TenantView:
        now = datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            row = await self._tenant_for_update(session, tenant_id)
            if row.settings_version != expected_version:
                raise AdministrationError(
                    "Tenant settings changed concurrently", code="administration.version_conflict"
                )
            Tenant(
                tenant_id,
                row.slug,
                name,
                timezone,
                default_locale,
                frozenset({default_locale}),
                TenantStatus(row.status),
                row.settings_version,
            )
            row.name = name.strip()
            row.timezone = timezone
            row.default_locale = default_locale.value
            row.supported_locales = [default_locale.value]
            await session.execute(
                update(BusinessScheduleRow)
                .where(BusinessScheduleRow.tenant_id == tenant_id.value)
                .values(timezone=timezone)
            )
            self._audit(
                session,
                tenant_id,
                actor,
                "tenant.profile_updated",
                "tenant",
                str(tenant_id),
                {"settings_version": expected_version + 1},
                now,
            )
            await session.flush()
            return _tenant(row)

    async def transition_tenant(
        self, tenant_id: TenantId, target: TenantStatus, *, actor: str
    ) -> TenantView:
        now = datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            row = await self._tenant_for_update(session, tenant_id)
            entity = _tenant_entity(row)
            previous = entity.status
            try:
                entity.transition_to(target)
            except Exception as exc:
                raise AdministrationError(
                    "Tenant lifecycle transition is invalid",
                    code="administration.invalid_transition",
                ) from exc
            if target is previous:
                return _tenant(row)
            row.status = target.value
            row.status_changed_at = now
            row.archived_at = now if target is TenantStatus.ARCHIVED else None
            self._audit(
                session,
                tenant_id,
                actor,
                "tenant.lifecycle_changed",
                "tenant",
                str(tenant_id),
                {"from_status": previous.value, "to_status": target.value},
                now,
            )
            await session.flush()
            return _tenant(row)

    async def members(self, tenant_id: TenantId) -> tuple[MemberView, ...]:
        async with self._session_factory() as session:
            rows = (
                await session.scalars(
                    select(TenantMemberRow)
                    .where(TenantMemberRow.tenant_id == tenant_id.value)
                    .order_by(TenantMemberRow.created_at, TenantMemberRow.id)
                )
            ).all()
            return tuple(_member(row) for row in rows)

    async def upsert_member(
        self, tenant_id: TenantId, *, subject: str, role: Role, actor: str
    ) -> MemberView:
        now = datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            await self._tenant_for_update(session, tenant_id)
            row = await session.scalar(
                select(TenantMemberRow)
                .where(
                    TenantMemberRow.tenant_id == tenant_id.value,
                    TenantMemberRow.subject == subject,
                )
                .with_for_update()
            )
            previous_role = row.role if row is not None else None
            if row is not None and row.active and row.role == Role.OWNER and role is not Role.OWNER:
                await self._require_other_owner(session, tenant_id, row.id)
            if row is None:
                row = TenantMemberRow(
                    id=uuid4(),
                    tenant_id=tenant_id.value,
                    subject=subject,
                    role=role.value,
                    active=True,
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
            else:
                row.role, row.active, row.updated_at = role.value, True, now
                await session.execute(
                    update(AdministrativeCredentialRow)
                    .where(
                        AdministrativeCredentialRow.tenant_id == tenant_id.value,
                        AdministrativeCredentialRow.member_id == row.id,
                        AdministrativeCredentialRow.revoked_at.is_(None),
                    )
                    .values(role=role.value)
                )
            self._audit(
                session,
                tenant_id,
                actor,
                "tenant.member_changed",
                "tenant_member",
                str(row.id),
                {"role": role.value, "previous_role": previous_role, "active": True},
                now,
            )
            await session.flush()
            return _member(row)

    async def revoke_member(
        self, tenant_id: TenantId, member_id: UUID, *, actor: str
    ) -> MemberView:
        now = datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            row = await session.scalar(
                select(TenantMemberRow)
                .where(
                    TenantMemberRow.tenant_id == tenant_id.value,
                    TenantMemberRow.id == member_id,
                )
                .with_for_update()
            )
            if row is None:
                raise AdministrationError("Member was not found", code="administration.not_found")
            if not row.active:
                return _member(row)
            if row.role == Role.OWNER:
                await self._require_other_owner(session, tenant_id, row.id)
            row.active, row.updated_at = False, now
            await session.execute(
                update(AdministrativeCredentialRow)
                .where(
                    AdministrativeCredentialRow.tenant_id == tenant_id.value,
                    AdministrativeCredentialRow.member_id == member_id,
                    AdministrativeCredentialRow.revoked_at.is_(None),
                )
                .values(revoked_at=now)
            )
            self._audit(
                session,
                tenant_id,
                actor,
                "tenant.member_revoked",
                "tenant_member",
                str(member_id),
                {"active": False},
                now,
            )
            await session.flush()
            return _member(row)

    async def credentials(self, tenant_id: TenantId) -> tuple[CredentialView, ...]:
        async with self._session_factory() as session:
            rows = (
                await session.scalars(
                    select(AdministrativeCredentialRow)
                    .where(AdministrativeCredentialRow.tenant_id == tenant_id.value)
                    .order_by(AdministrativeCredentialRow.created_at)
                )
            ).all()
            return tuple(_credential(row) for row in rows)

    async def create_credential(
        self,
        tenant_id: TenantId,
        *,
        member_id: UUID,
        name: str,
        expires_at: datetime | None,
        material: CredentialMaterial,
        actor: str,
    ) -> CredentialView:
        now = datetime.now(UTC)
        _validate_expiry(expires_at, now)
        async with self._session_factory() as session, session.begin():
            member = await session.scalar(
                select(TenantMemberRow).where(
                    TenantMemberRow.tenant_id == tenant_id.value,
                    TenantMemberRow.id == member_id,
                    TenantMemberRow.active.is_(True),
                )
            )
            if member is None:
                raise AdministrationError(
                    "Active member was not found", code="administration.not_found"
                )
            row = AdministrativeCredentialRow(
                id=uuid4(),
                tenant_id=tenant_id.value,
                member_id=member.id,
                name=name.strip(),
                key_prefix=material.prefix,
                secret_hash=material.secret_hash,
                role=member.role,
                expires_at=expires_at,
                created_at=now,
            )
            session.add(row)
            self._audit(
                session, tenant_id, actor, "credential.created", "credential", str(row.id), {}, now
            )
            await session.flush()
            return _credential(row)

    async def rotate_credential(
        self,
        tenant_id: TenantId,
        credential_id: UUID,
        *,
        expires_at: datetime | None,
        material: CredentialMaterial,
        actor: str,
    ) -> CredentialView:
        now = datetime.now(UTC)
        _validate_expiry(expires_at, now)
        async with self._session_factory() as session, session.begin():
            previous = await self._credential_for_update(session, tenant_id, credential_id)
            if previous.revoked_at is not None:
                raise AdministrationError(
                    "Revoked credential cannot be rotated", code="administration.credential_revoked"
                )
            previous.revoked_at = now
            row = AdministrativeCredentialRow(
                id=uuid4(),
                tenant_id=tenant_id.value,
                member_id=previous.member_id,
                name=previous.name,
                key_prefix=material.prefix,
                secret_hash=material.secret_hash,
                role=previous.role,
                expires_at=expires_at,
                rotated_from_id=previous.id,
                created_at=now,
            )
            session.add(row)
            self._audit(
                session,
                tenant_id,
                actor,
                "credential.rotated",
                "credential",
                str(row.id),
                {"rotated_from_id": str(previous.id)},
                now,
            )
            await session.flush()
            return _credential(row)

    async def revoke_credential(
        self, tenant_id: TenantId, credential_id: UUID, *, actor: str
    ) -> CredentialView:
        now = datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            row = await self._credential_for_update(session, tenant_id, credential_id)
            if row.revoked_at is None:
                row.revoked_at = now
                self._audit(
                    session,
                    tenant_id,
                    actor,
                    "credential.revoked",
                    "credential",
                    str(row.id),
                    {},
                    now,
                )
            await session.flush()
            return _credential(row)

    async def entitlements(self, tenant_id: TenantId) -> tuple[EntitlementView, ...]:
        async with self._session_factory() as session:
            rows = (
                await session.scalars(
                    select(TenantEntitlementRow)
                    .where(TenantEntitlementRow.tenant_id == tenant_id.value)
                    .order_by(TenantEntitlementRow.capability)
                )
            ).all()
            retention = await session.get(RetentionPolicyRow, tenant_id.value)
            results = [_entitlement(row) for row in rows]
            if retention is not None:
                results.append(
                    EntitlementView(
                        Capability.AUTOMATIC_RETENTION,
                        retention.automatic_execution_enabled,
                        retention.version,
                    )
                )
            return tuple(sorted(results, key=lambda item: item.capability.value))

    async def set_entitlement(
        self,
        tenant_id: TenantId,
        capability: Capability,
        *,
        enabled: bool,
        expected_version: int,
        actor: str,
    ) -> EntitlementView:
        now = datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            if capability is Capability.AUTOMATIC_RETENTION:
                retention_row = await session.get(
                    RetentionPolicyRow, tenant_id.value, with_for_update=True
                )
                if retention_row is None:
                    raise AdministrationError(
                        "Retention policy was not found", code="administration.not_found"
                    )
                if retention_row.version != expected_version:
                    raise AdministrationError(
                        "Entitlement changed concurrently", code="administration.version_conflict"
                    )
                retention_row.automatic_execution_enabled = enabled
                await session.flush()
                result = EntitlementView(capability, enabled, retention_row.version)
            else:
                entitlement_row = await session.get(
                    TenantEntitlementRow,
                    (tenant_id.value, capability.value),
                    with_for_update=True,
                )
                if entitlement_row is None:
                    raise AdministrationError(
                        "Entitlement was not found", code="administration.not_found"
                    )
                if entitlement_row.version != expected_version:
                    raise AdministrationError(
                        "Entitlement changed concurrently", code="administration.version_conflict"
                    )
                entitlement_row.enabled = enabled
                await session.flush()
                result = _entitlement(entitlement_row)
            self._audit(
                session,
                tenant_id,
                actor,
                "tenant.entitlement_changed",
                "tenant_entitlement",
                capability.value,
                {"enabled": enabled, "version": result.version},
                now,
            )
            return result

    async def _provisioning_result(
        self,
        session: AsyncSession,
        record: TenantProvisioningRow,
        *,
        secret: str | None,
        created: bool,
    ) -> ProvisioningResult:
        tenant = await session.get(TenantRow, record.tenant_id)
        owner = await session.get(TenantMemberRow, record.owner_member_id)
        credential = await session.get(AdministrativeCredentialRow, record.credential_id)
        assert tenant is not None and owner is not None and credential is not None
        from business_assistant.application.administration import CredentialIssue

        return ProvisioningResult(
            _tenant(tenant),
            _member(owner),
            CredentialIssue(_credential(credential), secret),
            created,
        )

    async def _tenant_for_update(self, session: AsyncSession, tenant_id: TenantId) -> TenantRow:
        row = await session.scalar(
            select(TenantRow).where(TenantRow.id == tenant_id.value).with_for_update()
        )
        if row is None:
            raise AdministrationError("Tenant was not found", code="administration.not_found")
        return row

    async def _credential_for_update(
        self, session: AsyncSession, tenant_id: TenantId, credential_id: UUID
    ) -> AdministrativeCredentialRow:
        row = await session.scalar(
            select(AdministrativeCredentialRow)
            .where(
                AdministrativeCredentialRow.tenant_id == tenant_id.value,
                AdministrativeCredentialRow.id == credential_id,
            )
            .with_for_update()
        )
        if row is None:
            raise AdministrationError("Credential was not found", code="administration.not_found")
        return row

    async def _require_other_owner(
        self, session: AsyncSession, tenant_id: TenantId, excluded: UUID
    ) -> None:
        owners = await session.scalar(
            select(func.count())
            .select_from(TenantMemberRow)
            .where(
                TenantMemberRow.tenant_id == tenant_id.value,
                TenantMemberRow.role == Role.OWNER.value,
                TenantMemberRow.active.is_(True),
                TenantMemberRow.id != excluded,
            )
        )
        if not owners:
            raise AdministrationError(
                "The last active owner cannot be removed or demoted",
                code="administration.last_owner",
            )

    def _audit(
        self,
        session: AsyncSession,
        tenant_id: TenantId,
        actor: str,
        action: str,
        target_type: str,
        target_id: str,
        safe_diff: dict[str, object],
        at: datetime,
    ) -> None:
        correlation = current_correlation_id()
        try:
            correlation_id = UUID(correlation)
        except ValueError:
            correlation_id = uuid5(NAMESPACE_URL, f"business-assistant:correlation:{correlation}")
        session.add(
            AuditEventRow(
                id=uuid4(),
                tenant_id=tenant_id.value,
                actor_type="administrative_principal",
                actor_id=actor[:100],
                action=action,
                target_type=target_type,
                target_id=target_id[:100],
                safe_diff=safe_diff,
                correlation_id=correlation_id,
                occurred_at=at,
            )
        )


def _tenant(row: TenantRow) -> TenantView:
    return TenantView(
        TenantId(row.id),
        row.slug,
        row.name,
        row.timezone,
        Locale(row.default_locale),
        frozenset(Locale(item) for item in row.supported_locales),
        TenantStatus(row.status),
        row.settings_version,
    )


def _tenant_entity(row: TenantRow) -> Tenant:
    view = _tenant(row)
    return Tenant(
        view.id,
        view.slug,
        view.name,
        view.timezone,
        view.default_locale,
        view.supported_locales,
        view.status,
        view.settings_version,
    )


def _member(row: TenantMemberRow) -> MemberView:
    return MemberView(
        row.id,
        TenantId(row.tenant_id),
        row.subject,
        Role(row.role),
        row.active,
        row.created_at,
        row.updated_at,
    )


def _credential(row: AdministrativeCredentialRow) -> CredentialView:
    return CredentialView(
        row.id,
        TenantId(row.tenant_id),
        row.member_id,
        row.name,
        row.key_prefix,
        Role(row.role),
        row.expires_at,
        row.revoked_at,
        row.last_used_at,
        row.created_at,
    )


def _entitlement(row: TenantEntitlementRow) -> EntitlementView:
    return EntitlementView(Capability(row.capability), row.enabled, row.version)


def _validate_expiry(expires_at: datetime | None, now: datetime) -> None:
    if expires_at is not None and (
        expires_at.tzinfo is None or expires_at.utcoffset() is None or expires_at <= now
    ):
        raise AdministrationError("Credential expiration must be a future aware timestamp")


class SQLAlchemyTenantAccessPolicy:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def require_active(
        self, tenant_id: TenantId, capability: Capability | None = None
    ) -> None:
        async with self._session_factory() as session:
            status = await session.scalar(
                select(TenantRow.status).where(TenantRow.id == tenant_id.value)
            )
            if status != TenantStatus.ACTIVE.value:
                raise AdministrationError("Tenant is unavailable", code="tenant.unavailable")
            if capability is None:
                return
            if capability is Capability.AUTOMATIC_RETENTION:
                enabled = await session.scalar(
                    select(RetentionPolicyRow.automatic_execution_enabled).where(
                        RetentionPolicyRow.tenant_id == tenant_id.value
                    )
                )
            else:
                enabled = await session.scalar(
                    select(TenantEntitlementRow.enabled).where(
                        TenantEntitlementRow.tenant_id == tenant_id.value,
                        TenantEntitlementRow.capability == capability.value,
                    )
                )
            if enabled is not True:
                raise AdministrationError(
                    "Capability is disabled", code="tenant.capability_disabled"
                )
