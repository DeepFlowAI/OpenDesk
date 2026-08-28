"""
Tenant-side SMS service: read-only granted templates for admin console,
available templates for the workspace send dialog, single-send with
short-session channel calls, delivery receipts and send-record queries.
"""
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.db.session import AsyncSessionLocal
from app.libs.sms import get_sms_client
from app.libs.sms.base import SmsSendResult
from app.models.sms import (
    SMS_SEND_SOURCE_BULK,
    SMS_SEND_SOURCE_SINGLE,
    SMS_SEND_STATUS_FAILED,
    SMS_SEND_STATUS_PENDING,
    SMS_SEND_STATUS_SUBMITTED,
    SMS_STATUS_ENABLED,
    SmsSignature,
    SmsTemplate,
    SmsTemplateGrant,
)
from app.repositories.call_record_repository import CallRecordRepository
from app.repositories.sms_bulk_task_repository import SmsBulkTargetRepository, SmsBulkTaskRepository
from app.repositories.sms_repository import SmsSendRecordRepository, SmsTemplateGrantRepository
from app.schemas.sms import SmsSendRequest, SmsSendResponse

logger = logging.getLogger(__name__)

DEFAULT_VARIABLE_MAX_LENGTH = 30
MAX_FAIL_REASON_LENGTH = 255


def _effective_updated_at(grant: SmsTemplateGrant, template: SmsTemplate) -> datetime | None:
    values = [value for value in (grant.updated_at, template.updated_at) if value is not None]
    return max(values) if values else None


def _to_item(
    grant: SmsTemplateGrant, template: SmsTemplate, signature: SmsSignature
) -> dict:
    return {
        "id": template.id,
        "name": template.name,
        "sign_name": signature.name,
        "type": template.type,
        "variables": template.variables or [],
        "status": "available" if template.status == SMS_STATUS_ENABLED else "unavailable",
        "updated_at": _effective_updated_at(grant, template),
    }


class SmsTenantTemplateService:
    """Read-only template views scoped to the current tenant's grants."""

    @staticmethod
    async def list_for_tenant(
        db: AsyncSession,
        *,
        tenant_id: int,
        page: int = 1,
        per_page: int = 20,
        q: str | None = None,
        only_available: bool = False,
    ) -> dict:
        rows, total = await SmsTemplateGrantRepository.list_granted_detail_for_tenant_paginated(
            db, tenant_id=tenant_id, page=page, per_page=per_page, q=q, only_enabled=only_available
        )
        items = [_to_item(grant, template, signature) for grant, template, signature in rows]
        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": (total + per_page - 1) // per_page,
        }

    @staticmethod
    async def get_for_tenant(db: AsyncSession, *, tenant_id: int, template_id: int) -> dict:
        row = await SmsTemplateGrantRepository.get_granted_template(
            db, tenant_id=tenant_id, template_id=template_id
        )
        if row is None:
            raise NotFoundError("Template not found")
        grant, template, signature = row
        return {**_to_item(grant, template, signature), "body": template.body}


def _validate_variables(defs: list, values: dict[str, str]) -> dict[str, str]:
    """Validate submitted values against variable definitions.

    Returns cleaned channel params containing only filled values.
    """
    def_map = {d["key"]: d for d in defs if isinstance(d, dict) and d.get("key")}
    unknown = sorted(set(values) - set(def_map))
    if unknown:
        raise ValidationError(f"Unknown template variable: {unknown[0]}")
    params: dict[str, str] = {}
    for key, definition in def_map.items():
        value = (values.get(key) or "").strip()
        if definition.get("required") and not value:
            raise ValidationError(f"Variable '{key}' is required", details={"variable": key})
        max_length = definition.get("max_length") or DEFAULT_VARIABLE_MAX_LENGTH
        if value and len(value) > max_length:
            raise ValidationError(
                f"Variable '{key}' exceeds max length {max_length}",
                details={"variable": key},
            )
        if value:
            params[key] = value
    return params


def _render_body_snapshot(body: str, params: dict[str, str]) -> str:
    rendered = body
    for key, value in params.items():
        rendered = rendered.replace("{" + key + "}", value)
    return rendered


def _format_fail_reason(error_code: str | None, error_message: str | None) -> str:
    if error_code and error_message:
        return f"{error_code}: {error_message}"[:MAX_FAIL_REASON_LENGTH]
    return (error_code or error_message or "Unknown channel error")[:MAX_FAIL_REASON_LENGTH]


class SmsWorkspaceService:
    """Workspace single-send: template picker data, submit + delivery receipts."""

    @staticmethod
    async def list_available_for_workspace(db: AsyncSession, *, tenant_id: int) -> dict:
        rows, _ = await SmsTemplateGrantRepository.list_granted_detail_for_tenant_paginated(
            db, tenant_id=tenant_id, page=1, per_page=100, only_enabled=True
        )
        items = [
            {
                "id": template.id,
                "name": template.name,
                "sign_name": signature.name,
                "type": template.type,
                "variables": template.variables or [],
                "body": template.body,
            }
            for _, template, signature in rows
        ]
        return {"items": items}

    @staticmethod
    def _to_send_response(record, error_code: str | None = None) -> SmsSendResponse:
        return SmsSendResponse(
            id=record.id,
            status=record.status,
            fail_reason=record.fail_reason,
            error_code=error_code,
            created_at=record.created_at,
        )

    @staticmethod
    async def send_managed(
        *, tenant_id: int, employee_id: int, payload: SmsSendRequest
    ) -> SmsSendResponse:
        """Submit one SMS. The DB session is closed while the channel call runs."""
        async with AsyncSessionLocal() as db:
            if payload.client_request_id:
                existing = await SmsSendRecordRepository.get_by_client_request_id(
                    db, tenant_id=tenant_id, client_request_id=payload.client_request_id
                )
                if existing is not None:
                    return SmsWorkspaceService._to_send_response(existing)

            row = await SmsTemplateGrantRepository.get_granted_template(
                db, tenant_id=tenant_id, template_id=payload.template_id
            )
            if row is None:
                raise NotFoundError("Template not found")
            _, template, signature = row
            if template.status != SMS_STATUS_ENABLED:
                raise ValidationError("Template is disabled")

            params = _validate_variables(template.variables or [], payload.variables)

            call_record_id = None
            if payload.call_id:
                call_record = await CallRecordRepository.get_by_call_id(
                    db, payload.call_id, tenant_id
                )
                call_record_id = call_record.id if call_record is not None else None

            record = await SmsSendRecordRepository.create(
                db,
                {
                    "tenant_id": tenant_id,
                    "phone": payload.phone,
                    "template_id": template.id,
                    "template_name": template.name,
                    "template_type": template.type,
                    "sign_name": signature.name,
                    "body_snapshot": _render_body_snapshot(template.body, params),
                    "variables_snapshot": params,
                    "status": SMS_SEND_STATUS_PENDING,
                    "employee_id": employee_id,
                    "call_record_id": call_record_id,
                    "provider": template.provider,
                    "client_request_id": payload.client_request_id,
                },
            )
            await db.commit()
            record_id = record.id
            created_at = record.created_at
            provider = template.provider
            provider_sign_name = signature.provider_sign_name
            provider_template_code = template.provider_template_code

        try:
            result = await get_sms_client().send_sms(
                phone=payload.phone,
                sign_name=provider_sign_name,
                template_code=provider_template_code,
                template_params=params,
            )
        except Exception as exc:  # defensive: never leave the record stuck in pending
            logger.exception("SMS channel call raised unexpectedly (record_id=%s)", record_id)
            result = SmsSendResult(success=False, error_code="INTERNAL", error_message=str(exc)[:200])

        async with AsyncSessionLocal() as db:
            if result.success:
                await SmsSendRecordRepository.update_send_result(
                    db, record_id=record_id, status=SMS_SEND_STATUS_SUBMITTED, biz_id=result.biz_id
                )
                status = SMS_SEND_STATUS_SUBMITTED
                fail_reason = None
            else:
                fail_reason = _format_fail_reason(result.error_code, result.error_message)
                await SmsSendRecordRepository.update_send_result(
                    db,
                    record_id=record_id,
                    status=SMS_SEND_STATUS_FAILED,
                    biz_id=result.biz_id,
                    fail_reason=fail_reason,
                )
                status = SMS_SEND_STATUS_FAILED
            await db.commit()

        return SmsSendResponse(
            id=record_id,
            status=status,
            fail_reason=fail_reason,
            error_code=None if result.success else result.error_code,
            created_at=created_at,
        )

    @staticmethod
    async def handle_delivery_receipts(*, provider: str, payload: list[dict[str, Any]]) -> int:
        """Apply provider delivery receipts. Returns the number of records updated.

        One provider account feeds every environment (production mirrors its
        callback to test), so a receipt whose biz_id belongs to another
        environment matches no row here and is ignored on purpose.
        """
        client = get_sms_client()
        receipts = []
        for item in payload:
            try:
                receipt = client.parse_delivery_receipt(item)
            except Exception:
                logger.warning("Unparseable SMS receipt skipped (provider=%s)", provider, exc_info=True)
                continue
            if receipt.biz_id:
                receipts.append(receipt)

        processed = 0
        unmatched: list[str] = []
        now = datetime.now(timezone.utc)
        async with AsyncSessionLocal() as db:
            for receipt in receipts:
                fail_reason = (
                    None
                    if receipt.success
                    else _format_fail_reason(receipt.error_code, receipt.error_message)
                )
                updated = await SmsSendRecordRepository.update_delivery_by_biz_id(
                    db,
                    provider=provider,
                    biz_id=receipt.biz_id,
                    delivered=receipt.success,
                    fail_reason=fail_reason,
                )
                # Bulk targets sharing the biz_id advance in lockstep; when a
                # task has no open targets left it completes here too.
                task_ids = await SmsBulkTargetRepository.update_delivery_by_biz_id(
                    db,
                    biz_id=receipt.biz_id,
                    delivered=receipt.success,
                    fail_reason=fail_reason,
                    now=now,
                )
                if updated == 0 and not task_ids:
                    # Either the other environment's send, or a duplicate /
                    # out-of-order retry of an already terminal record.
                    unmatched.append(receipt.biz_id)
                    continue
                processed += updated
                logger.info(
                    "SMS receipt applied (provider=%s, biz_id=%s, delivered=%s, fail_reason=%s)",
                    provider,
                    receipt.biz_id,
                    receipt.success,
                    fail_reason,
                )
                for task_id in task_ids:
                    await SmsBulkTaskRepository.complete_if_finished(db, task_id, now)
            await db.commit()
        if unmatched:
            preview = ",".join(unmatched[:10]) + ("..." if len(unmatched) > 10 else "")
            logger.info(
                "SMS receipts unmatched, ignored (provider=%s, count=%d, biz_ids=%s)",
                provider,
                len(unmatched),
                preview,
            )
        return processed


VALID_RECORD_STATUS_FILTERS = {SMS_SEND_STATUS_PENDING, SMS_SEND_STATUS_SUBMITTED, "delivered", "failed"}
VALID_RECORD_SOURCE_FILTERS = {SMS_SEND_SOURCE_SINGLE, SMS_SEND_SOURCE_BULK}


def _to_record_item(
    record,
    employee_name: str | None,
    call_id: str | None,
    call_record_public_id,
) -> dict:
    return {
        "id": record.id,
        "phone": record.phone,
        "template_name": record.template_name,
        "template_type": record.template_type,
        "sign_name": record.sign_name,
        "status": record.status,
        "employee_name": employee_name or "",
        "source": record.source,
        "bulk_task_id": record.bulk_task_id,
        "call_record_id": record.call_record_id,
        "call_record_public_id": (
            str(call_record_public_id) if call_record_public_id is not None else None
        ),
        "call_id": call_id,
        "created_at": record.created_at,
    }


class SmsSendRecordService:
    """Tenant-scoped send-record queries for the service-operations page."""

    @staticmethod
    async def list_for_tenant(
        db: AsyncSession,
        *,
        tenant_id: int,
        page: int = 1,
        per_page: int = 20,
        q: str | None = None,
        status: str | None = None,
        source: str | None = None,
    ) -> dict:
        status_filter = status if status in VALID_RECORD_STATUS_FILTERS else None
        source_filter = source if source in VALID_RECORD_SOURCE_FILTERS else None
        rows, total = await SmsSendRecordRepository.list_for_tenant_paginated(
            db,
            tenant_id=tenant_id,
            page=page,
            per_page=per_page,
            phone=q,
            status=status_filter,
            source=source_filter,
        )
        return {
            "items": [
                _to_record_item(record, employee_name, call_id, call_record_public_id)
                for record, employee_name, call_id, call_record_public_id in rows
            ],
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": (total + per_page - 1) // per_page,
        }

    @staticmethod
    async def get_for_tenant(db: AsyncSession, *, tenant_id: int, record_id: int) -> dict:
        row = await SmsSendRecordRepository.get_detail_for_tenant(
            db, tenant_id=tenant_id, record_id=record_id
        )
        if row is None:
            raise NotFoundError("Record not found")
        record, employee_name, call_id, call_record_public_id = row
        return {
            **_to_record_item(record, employee_name, call_id, call_record_public_id),
            "body_snapshot": record.body_snapshot,
            "variables_snapshot": record.variables_snapshot or {},
            "fail_reason": record.fail_reason,
            "provider": record.provider,
            "provider_biz_id": record.provider_biz_id,
        }
