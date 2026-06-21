"""
Web SDK context synchronization service.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, NotFoundError, UnauthorizedError
from app.core.security import decode_context_token
from app.enums import FieldDomain
from app.models.user import User
from app.repositories.api_key_repository import ApiKeyRepository
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.fd_field_definition_repository import FdFieldDefinitionRepository
from app.repositories.user_repository import UserRepository
from app.services.cs_summary_usage_service import CsSummaryUsageService
from app.services.fd_field_definition_service import coerce_slot_value

CUSTOMER_SYSTEM_FIELD_MAP = {
    "nickname": ("name", 64),
    "email": ("email", 254),
    "phone": ("phone", 32),
    "gender": ("gender", 16),
    "level": ("level", 16),
    "address": ("address", 256),
    "remark": ("remark", 2000),
}
VALID_GENDERS = {"male", "female", "unknown"}
VALID_USER_LEVELS = {"normal", "vip"}
FIELD_KEY_PATTERN = re.compile(r"^[a-z_][a-z0-9_]{1,63}$")


@dataclass
class VisitorIdentityResolution:
    visitor_external_id: str | None = None
    visitor_name: str | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class ContextSyncResult:
    ok: bool = True
    warnings: list[str] = field(default_factory=list)
    customer_synced: bool = False
    session_summary_synced: bool = False

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "warnings": self.warnings,
            "customer_synced": self.customer_synced,
            "session_summary_synced": self.session_summary_synced,
        }


def _clean_string(value: Any, max_length: int | None = None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if max_length is not None:
        text = text[:max_length]
    return text


def _normalize_email(value: Any) -> str | None:
    text = _clean_string(value, 254)
    return text.lower() if text else None


def _normalize_phone(value: Any) -> str | None:
    text = _clean_string(value, 32)
    if not text:
        return None
    normalized = re.sub(r"[\s\-().]", "", text)
    return normalized[:32] if normalized else None


class WebSdkContextService:
    @staticmethod
    async def validate_context_token(
        db: AsyncSession,
        *,
        context_token: str,
        tenant_id: int,
        channel_key: str,
        require_active_api_key: bool,
    ) -> dict:
        payload = decode_context_token(context_token)
        if not payload:
            raise UnauthorizedError("Invalid or expired context token")

        try:
            payload_tenant_id = int(payload["tenant_id"])
        except (KeyError, TypeError, ValueError):
            raise UnauthorizedError("Invalid context token")

        if payload_tenant_id != tenant_id or payload.get("channel_key") != channel_key:
            raise UnauthorizedError("Context token does not match channel")

        if require_active_api_key:
            try:
                api_key_id = int(payload["api_key_id"])
                api_key_version = int(payload["api_key_version"])
            except (KeyError, TypeError, ValueError):
                raise UnauthorizedError("Invalid context token")
            api_key = await ApiKeyRepository.get_by_id(db, api_key_id)
            if (
                not api_key
                or api_key.tenant_id != tenant_id
                or not api_key.is_active
                or api_key.key_version != api_key_version
            ):
                raise ForbiddenError("API key disabled")

        return payload

    @staticmethod
    async def resolve_visitor_identity(
        db: AsyncSession,
        *,
        tenant_id: int,
        channel_key: str,
        context_token: str,
    ) -> VisitorIdentityResolution:
        payload = await WebSdkContextService.validate_context_token(
            db,
            context_token=context_token,
            tenant_id=tenant_id,
            channel_key=channel_key,
            require_active_api_key=True,
        )
        customer = payload.get("customer")
        if not isinstance(customer, dict):
            return VisitorIdentityResolution()

        warnings: list[str] = []
        user = await WebSdkContextService._match_customer_user(db, tenant_id, customer, warnings)
        visitor_name = _clean_string(customer.get("nickname"), 64)
        if user:
            return VisitorIdentityResolution(
                visitor_external_id=user.external_id,
                visitor_name=visitor_name or user.name,
                warnings=warnings,
            )

        external_user_id = _clean_string(customer.get("externalUserId"), 128)
        return VisitorIdentityResolution(
            visitor_external_id=external_user_id,
            visitor_name=visitor_name,
            warnings=warnings,
        )

    @staticmethod
    async def sync_for_conversation(
        db: AsyncSession,
        *,
        context_token: str,
        visitor_context: dict,
        conversation_public_id: str,
        require_active_api_key: bool,
    ) -> ContextSyncResult:
        result = ContextSyncResult()
        payload = await WebSdkContextService.validate_context_token(
            db,
            context_token=context_token,
            tenant_id=int(visitor_context["tenant_id"]),
            channel_key=str(visitor_context["channel_key"]),
            require_active_api_key=require_active_api_key,
        )

        conversation = await ConversationRepository.get_by_public_id(db, conversation_public_id)
        if (
            not conversation
            or conversation.tenant_id != int(visitor_context["tenant_id"])
            or conversation.channel_id != int(visitor_context["channel_id"])
            or not conversation.visitor
            or conversation.visitor.external_id != visitor_context["visitor_external_id"]
        ):
            raise NotFoundError("Conversation not found")

        customer = payload.get("customer")
        if isinstance(customer, dict):
            customer_synced = await WebSdkContextService._sync_customer(
                db,
                conversation.visitor,
                customer,
                result.warnings,
            )
            result.customer_synced = customer_synced
        elif customer is not None:
            result.warnings.append("INVALID_CUSTOMER_INFO")

        session_summary = payload.get("session_summary")
        if isinstance(session_summary, dict):
            fields = session_summary.get("fields")
            if isinstance(fields, dict) and fields:
                summary_result = await CsSummaryUsageService.update_fields_by_keys(
                    db,
                    tenant_id=conversation.tenant_id,
                    conversation_id=conversation.id,
                    fields_by_key=fields,
                )
                result.warnings.extend(summary_result["warnings"])
                result.session_summary_synced = summary_result["updated"] > 0
            elif fields is not None:
                result.warnings.append("INVALID_SESSION_SUMMARY")
        elif session_summary is not None:
            result.warnings.append("INVALID_SESSION_SUMMARY")

        return result

    @staticmethod
    async def _match_customer_user(
        db: AsyncSession,
        tenant_id: int,
        customer: dict,
        warnings: list[str],
    ) -> User | None:
        user_public_id = _clean_string(customer.get("userPublicId"), 64)
        if user_public_id:
            user = await UserRepository.get_by_public_id(db, user_public_id)
            if user and user.tenant_id == tenant_id:
                return user

        external_user_id = _clean_string(customer.get("externalUserId"), 128)
        if external_user_id:
            user = await UserRepository.get_by_external_id(db, tenant_id, external_user_id)
            if user:
                return user

        email = _normalize_email(customer.get("email"))
        email_user: User | None = None
        if email:
            email_matches = await UserRepository.list_by_email(db, tenant_id, email)
            if len(email_matches) > 1:
                warnings.append("CUSTOMER_MATCH_AMBIGUOUS:email")
                return None
            if len(email_matches) == 1:
                email_user = email_matches[0]

        phone = _normalize_phone(customer.get("phone"))
        phone_user: User | None = None
        if phone:
            phone_matches = [
                user
                for user in await UserRepository.list_with_phone(db, tenant_id)
                if _normalize_phone(user.phone) == phone
            ]
            if len(phone_matches) > 1:
                warnings.append("CUSTOMER_MATCH_AMBIGUOUS:phone")
                return None
            if len(phone_matches) == 1:
                phone_user = phone_matches[0]

        if email_user and phone_user and email_user.id != phone_user.id:
            warnings.append("CUSTOMER_MATCH_CONFLICT:email_phone")
            return None
        return email_user or phone_user

    @staticmethod
    async def _sync_customer(
        db: AsyncSession,
        user: User,
        customer: dict,
        warnings: list[str],
    ) -> bool:
        update_data: dict[str, Any] = {}

        for source_key, (column, max_length) in CUSTOMER_SYSTEM_FIELD_MAP.items():
            raw_value = customer.get(source_key)
            if raw_value == "":
                continue
            if source_key == "email":
                value = _normalize_email(raw_value)
            elif source_key == "phone":
                value = _normalize_phone(raw_value)
            else:
                value = _clean_string(raw_value, max_length)
            if value is None:
                continue
            if source_key == "gender" and value not in VALID_GENDERS:
                warnings.append("INVALID_CUSTOMER_FIELD:gender")
                continue
            if source_key == "level" and value not in VALID_USER_LEVELS:
                warnings.append("INVALID_CUSTOMER_FIELD:level")
                continue
            update_data[column] = value

        custom_fields = customer.get("fields")
        if isinstance(custom_fields, dict) and custom_fields:
            definitions = await FdFieldDefinitionRepository.list_custom_for_unified_domain(
                db,
                user.tenant_id,
                FieldDomain.USER.value,
            )
            definition_map = {
                item.field_key: item
                for item in definitions
                if item.status == "active" and item.field_key and item.slot_column
            }
            for field_key, raw_value in custom_fields.items():
                if not isinstance(field_key, str) or not FIELD_KEY_PATTERN.fullmatch(field_key):
                    warnings.append("INVALID_CUSTOMER_FIELD_KEY")
                    continue
                definition = definition_map.get(field_key)
                if not definition:
                    warnings.append(f"UNKNOWN_CUSTOMER_FIELD:{field_key}")
                    continue
                if raw_value == "":
                    continue
                value = coerce_slot_value(definition.slot_column, raw_value)
                if value is None:
                    warnings.append(f"INVALID_CUSTOMER_FIELD:{field_key}")
                    continue
                update_data[definition.slot_column] = value
        elif custom_fields is not None:
            warnings.append("INVALID_CUSTOMER_FIELDS")

        if not update_data:
            return False
        await UserRepository.update(db, user, update_data)
        return True
