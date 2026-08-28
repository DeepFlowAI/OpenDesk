"""
Platform SMS service: signature/template management and tenant grants.

These APIs are consumed by the external tenant-management system and are
platform-scoped (no tenant_id on signatures/templates).
"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models.sms import (
    SMS_STATUS_ENABLED,
    SmsSignature,
    SmsTemplate,
)
from app.repositories.sms_repository import (
    SmsSignatureRepository,
    SmsTemplateGrantRepository,
    SmsTemplateRepository,
)
from app.repositories.tenant_repository import TenantRepository
from app.schemas.sms import (
    SmsSignatureCreate,
    SmsSignatureUpdate,
    SmsTemplateCreate,
    SmsTemplateUpdate,
)


def _validate_provider(provider: str) -> None:
    if not provider or not provider.strip():
        raise ValidationError("provider is required")


def _validate_status(status: str) -> None:
    if status not in {"enabled", "disabled"}:
        raise ValidationError("status must be enabled or disabled")


def _validate_template_type(type_: str) -> None:
    if type_ not in {"notify", "promo"}:
        raise ValidationError("type must be notify or promo")


def _validate_variables(variables: list[dict]) -> None:
    keys = [item.get("key") for item in variables]
    if any(not key for key in keys):
        raise ValidationError("variable key is required")
    if len(keys) != len(set(keys)):
        raise ValidationError("variable keys must be unique within a template")


def _paginate(total: int, page: int, per_page: int) -> dict:
    return {"total": total, "page": page, "per_page": per_page, "pages": (total + per_page - 1) // per_page}


def _template_to_dict(template: SmsTemplate, signature: SmsSignature | None) -> dict:
    return {
        "id": template.id,
        "name": template.name,
        "type": template.type,
        "signature_id": template.signature_id,
        "signature_name": signature.name if signature else None,
        "body": template.body,
        "variables": template.variables or [],
        "provider": template.provider,
        "provider_template_code": template.provider_template_code,
        "status": template.status,
        "created_at": template.created_at,
        "updated_at": template.updated_at,
    }


class SmsSignatureService:

    @staticmethod
    async def list_paginated(
        db: AsyncSession, *, page: int, per_page: int, q: str | None, status: str | None
    ) -> dict:
        items, total = await SmsSignatureRepository.get_paginated(
            db, page=page, per_page=per_page, q=q, status=status
        )
        return {"items": items, **_paginate(total, page, per_page)}

    @staticmethod
    async def get_by_id(db: AsyncSession, signature_id: int) -> SmsSignature:
        item = await SmsSignatureRepository.get_by_id(db, signature_id)
        if item is None:
            raise NotFoundError("Signature not found")
        return item

    @staticmethod
    async def _assert_no_conflict(
        db: AsyncSession, *, provider: str, provider_sign_name: str, exclude_id: int | None = None
    ) -> None:
        existing = await SmsSignatureRepository.get_enabled_by_provider_sign(
            db, provider, provider_sign_name
        )
        if existing is not None and existing.id != exclude_id:
            raise ConflictError("An enabled signature already binds this provider sign name")

    @staticmethod
    async def create(db: AsyncSession, data: SmsSignatureCreate) -> SmsSignature:
        _validate_provider(data.provider)
        _validate_status(data.status)
        if data.status == SMS_STATUS_ENABLED:
            await SmsSignatureService._assert_no_conflict(
                db, provider=data.provider, provider_sign_name=data.provider_sign_name
            )
        return await SmsSignatureRepository.create(db, data.model_dump())

    @staticmethod
    async def update(db: AsyncSession, signature_id: int, data: SmsSignatureUpdate) -> SmsSignature:
        item = await SmsSignatureService.get_by_id(db, signature_id)
        updates = data.model_dump(exclude_unset=True)
        if "status" in updates:
            _validate_status(updates["status"])
        effective_status = updates.get("status", item.status)
        effective_sign = updates.get("provider_sign_name", item.provider_sign_name)
        if effective_status == SMS_STATUS_ENABLED:
            await SmsSignatureService._assert_no_conflict(
                db, provider=item.provider, provider_sign_name=effective_sign, exclude_id=item.id
            )
        return await SmsSignatureRepository.update(db, item, updates)


class SmsTemplateService:

    @staticmethod
    async def list_paginated(
        db: AsyncSession,
        *,
        page: int,
        per_page: int,
        q: str | None,
        status: str | None,
        type_: str | None,
    ) -> dict:
        items, total = await SmsTemplateRepository.get_paginated(
            db, page=page, per_page=per_page, q=q, status=status, type_=type_
        )
        signature_ids = {item.signature_id for item in items}
        signatures = {
            sig.id: sig
            for sig in [
                await SmsSignatureRepository.get_by_id(db, signature_id)
                for signature_id in signature_ids
            ]
            if sig is not None
        }
        return {
            "items": [_template_to_dict(item, signatures.get(item.signature_id)) for item in items],
            **_paginate(total, page, per_page),
        }

    @staticmethod
    async def get_detail(db: AsyncSession, template_id: int) -> dict:
        item = await SmsTemplateRepository.get_by_id(db, template_id)
        if item is None:
            raise NotFoundError("Template not found")
        signature = await SmsSignatureRepository.get_by_id(db, item.signature_id)
        return _template_to_dict(item, signature)

    @staticmethod
    async def _assert_enable_ready(
        db: AsyncSession,
        *,
        signature_id: int,
        provider: str | None,
        provider_template_code: str | None,
    ) -> SmsSignature:
        signature = await SmsSignatureRepository.get_by_id(db, signature_id)
        if signature is None:
            raise NotFoundError("Signature not found")
        if signature.status != SMS_STATUS_ENABLED:
            raise ValidationError("Bound signature is disabled")
        if not provider or not provider_template_code:
            raise ValidationError("Channel binding is required before enabling a template")
        return signature

    @staticmethod
    async def _assert_code_available(
        db: AsyncSession, *, provider: str, provider_template_code: str, exclude_id: int | None = None
    ) -> None:
        existing = await SmsTemplateRepository.get_by_provider_code(db, provider, provider_template_code)
        if existing is not None and existing.id != exclude_id:
            raise ConflictError("Provider template code already in use")

    @staticmethod
    async def create(db: AsyncSession, data: SmsTemplateCreate) -> dict:
        _validate_provider(data.provider)
        _validate_status(data.status)
        _validate_template_type(data.type)
        variables = [item.model_dump(exclude_none=True) for item in data.variables]
        _validate_variables(variables)
        signature = await SmsSignatureRepository.get_by_id(db, data.signature_id)
        if signature is None:
            raise NotFoundError("Signature not found")
        if data.status == SMS_STATUS_ENABLED:
            await SmsTemplateService._assert_enable_ready(
                db,
                signature_id=data.signature_id,
                provider=data.provider,
                provider_template_code=data.provider_template_code,
            )
        await SmsTemplateService._assert_code_available(
            db, provider=data.provider, provider_template_code=data.provider_template_code
        )
        payload = data.model_dump()
        payload["variables"] = variables
        item = await SmsTemplateRepository.create(db, payload)
        return _template_to_dict(item, signature)

    @staticmethod
    async def update(db: AsyncSession, template_id: int, data: SmsTemplateUpdate) -> dict:
        item = await SmsTemplateRepository.get_by_id(db, template_id)
        if item is None:
            raise NotFoundError("Template not found")
        updates = data.model_dump(exclude_unset=True)
        if "status" in updates:
            _validate_status(updates["status"])
        if "type" in updates:
            _validate_template_type(updates["type"])
        if "variables" in updates:
            updates["variables"] = [v.model_dump(exclude_none=True) if hasattr(v, "model_dump") else v for v in updates["variables"]]
            _validate_variables(updates["variables"])

        effective_signature_id = updates.get("signature_id", item.signature_id)
        effective_provider = updates.get("provider", item.provider)
        effective_code = updates.get("provider_template_code", item.provider_template_code)
        effective_status = updates.get("status", item.status)

        if "signature_id" in updates:
            signature = await SmsSignatureRepository.get_by_id(db, effective_signature_id)
            if signature is None:
                raise NotFoundError("Signature not found")
        if effective_status == SMS_STATUS_ENABLED:
            await SmsTemplateService._assert_enable_ready(
                db,
                signature_id=effective_signature_id,
                provider=effective_provider,
                provider_template_code=effective_code,
            )
        if "provider" in updates or "provider_template_code" in updates:
            await SmsTemplateService._assert_code_available(
                db, provider=effective_provider, provider_template_code=effective_code, exclude_id=item.id
            )

        updated = await SmsTemplateRepository.update(db, item, updates)
        signature = await SmsSignatureRepository.get_by_id(db, updated.signature_id)
        return _template_to_dict(updated, signature)


class SmsTemplateGrantService:

    @staticmethod
    async def _resolve_tenant(db: AsyncSession, tenant_id: str):
        # The platform API identifies tenants by their business tenant_id
        # (same identifier as /api/v1/tenants and phone-number bindings);
        # grants are stored against the internal primary key.
        tenant = await TenantRepository.get_by_tenant_id(db, tenant_id)
        if tenant is None:
            raise NotFoundError("Tenant not found")
        return tenant

    @staticmethod
    async def grant(db: AsyncSession, *, tenant_id: str, template_ids: list[int]) -> dict:
        tenant = await SmsTemplateGrantService._resolve_tenant(db, tenant_id)
        tenant_pk = tenant.id
        templates = await SmsTemplateRepository.get_by_ids(db, template_ids)
        enabled_ids = {item.id for item in templates if item.status == SMS_STATUS_ENABLED}
        existing_ids = set(await SmsTemplateGrantRepository.list_template_ids_for_tenant(db, tenant_pk))

        granted: list[int] = []
        skipped: list[int] = []
        for template_id in dict.fromkeys(template_ids):
            if template_id not in enabled_ids or template_id in existing_ids:
                skipped.append(template_id)
                continue
            await SmsTemplateGrantRepository.create(db, tenant_pk, template_id)
            existing_ids.add(template_id)
            granted.append(template_id)
        await SmsTemplateGrantRepository.commit(db)
        return {"granted": granted, "skipped": skipped}

    @staticmethod
    async def revoke(db: AsyncSession, *, tenant_id: str, template_ids: list[int]) -> dict:
        tenant = await SmsTemplateGrantService._resolve_tenant(db, tenant_id)
        tenant_pk = tenant.id
        revoked: list[int] = []
        for template_id in dict.fromkeys(template_ids):
            if await SmsTemplateGrantRepository.delete(db, tenant_pk, template_id):
                revoked.append(template_id)
        await SmsTemplateGrantRepository.commit(db)
        return {"revoked": revoked}

    @staticmethod
    async def list_granted_templates(db: AsyncSession, *, tenant_id: str) -> dict:
        tenant = await SmsTemplateGrantService._resolve_tenant(db, tenant_id)
        grants = await SmsTemplateGrantRepository.list_grants_for_tenant(db, tenant.id)
        if not grants:
            return {"items": []}
        templates = {
            item.id: item
            for item in await SmsTemplateRepository.get_by_ids(db, [g.template_id for g in grants])
        }
        signature_cache: dict[int, SmsSignature | None] = {}
        items = []
        for grant in grants:
            template = templates.get(grant.template_id)
            if template is None:
                continue
            if template.signature_id not in signature_cache:
                signature_cache[template.signature_id] = await SmsSignatureRepository.get_by_id(
                    db, template.signature_id
                )
            signature = signature_cache[template.signature_id]
            items.append(
                {
                    "template_id": template.id,
                    "name": template.name,
                    "type": template.type,
                    "sign_name": signature.name if signature else "",
                    "body": template.body,
                    "variables": template.variables or [],
                    "availability": "available" if template.status == SMS_STATUS_ENABLED else "template_disabled",
                    "granted_at": grant.created_at,
                    "updated_at": max(grant.updated_at, template.updated_at),
                }
            )
        return {"items": items}
