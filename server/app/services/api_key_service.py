"""
API Key service.
"""
import hashlib
import hmac
import secrets
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.configs.settings import ENV, settings
from app.core.exceptions import ForbiddenError, NotFoundError, UnauthorizedError, ValidationError
from app.core.security import create_context_token
from app.models.api_key import ApiKey
from app.repositories.api_key_repository import ApiKeyRepository
from app.repositories.channel_repository import ChannelRepository
from app.schemas.api_key import ApiKeyCreate, ContextTokenRequest, ContextTokenResponse
from app.schemas.open_api import OpenApiContext
from app.schemas.permission import EffectivePrincipal

API_KEY_RANDOM_BYTES = 36
API_KEY_VISIBLE_CHARS = 16
MAX_KEY_GENERATION_ATTEMPTS = 10
PRODUCTION_ENVS = {"prod", "production", "staging"}


class ApiKeyService:
    @staticmethod
    def ensure_super_admin(principal: EffectivePrincipal) -> None:
        if not principal.is_super_admin:
            raise ForbiddenError("Super admin required")

    @staticmethod
    def key_prefix() -> str:
        suffix = "live" if ENV.lower() in PRODUCTION_ENVS else "test"
        return f"sk-odk-{suffix}-"

    @staticmethod
    def generate_api_key() -> str:
        return f"{ApiKeyService.key_prefix()}{secrets.token_urlsafe(API_KEY_RANDOM_BYTES)}"

    @staticmethod
    def hash_api_key(api_key: str) -> str:
        return hmac.new(
            settings.SECRET_KEY.encode("utf-8"),
            api_key.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def mask_api_key(api_key: str) -> str:
        return f"{api_key[:API_KEY_VISIBLE_CHARS]}********"

    @staticmethod
    async def generate_unique_key(db: AsyncSession) -> tuple[str, str, str]:
        for _ in range(MAX_KEY_GENERATION_ATTEMPTS):
            api_key = ApiKeyService.generate_api_key()
            key_hash = ApiKeyService.hash_api_key(api_key)
            if not await ApiKeyRepository.get_by_hash(db, key_hash):
                return api_key, key_hash, ApiKeyService.mask_api_key(api_key)
        raise RuntimeError("Failed to generate a unique API key")

    @staticmethod
    async def list_by_tenant(db: AsyncSession, principal: EffectivePrincipal) -> list[ApiKey]:
        ApiKeyService.ensure_super_admin(principal)
        return await ApiKeyRepository.get_by_tenant(db, principal.tenant_id)

    @staticmethod
    async def create(db: AsyncSession, principal: EffectivePrincipal, data: ApiKeyCreate) -> dict:
        ApiKeyService.ensure_super_admin(principal)
        api_key, key_hash, masked_key = await ApiKeyService.generate_unique_key(db)
        record = await ApiKeyRepository.create(
            db,
            {
                "tenant_id": principal.tenant_id,
                "name": data.name,
                "key_hash": key_hash,
                "masked_key": masked_key,
                "created_by_employee_id": principal.user_id,
            },
        )
        return {"record": record, "api_key": api_key}

    @staticmethod
    async def get_scoped(db: AsyncSession, principal: EffectivePrincipal, api_key_id: int) -> ApiKey:
        ApiKeyService.ensure_super_admin(principal)
        item = await ApiKeyRepository.get_by_id(db, api_key_id)
        if not item or item.tenant_id != principal.tenant_id:
            raise NotFoundError("API key not found")
        return item

    @staticmethod
    async def disable(db: AsyncSession, principal: EffectivePrincipal, api_key_id: int) -> ApiKey:
        item = await ApiKeyService.get_scoped(db, principal, api_key_id)
        if not item.is_active:
            return item
        return await ApiKeyRepository.update(
            db,
            item,
            {
                "is_active": False,
                "disabled_at": datetime.now(timezone.utc),
            },
        )

    @staticmethod
    async def enable(db: AsyncSession, principal: EffectivePrincipal, api_key_id: int) -> ApiKey:
        item = await ApiKeyService.get_scoped(db, principal, api_key_id)
        if item.is_active:
            return item
        return await ApiKeyRepository.update(
            db,
            item,
            {
                "is_active": True,
                "disabled_at": None,
            },
        )

    @staticmethod
    async def rotate(db: AsyncSession, principal: EffectivePrincipal, api_key_id: int) -> dict:
        item = await ApiKeyService.get_scoped(db, principal, api_key_id)
        api_key, key_hash, masked_key = await ApiKeyService.generate_unique_key(db)
        record = await ApiKeyRepository.update(
            db,
            item,
            {
                "key_hash": key_hash,
                "masked_key": masked_key,
                "key_version": item.key_version + 1,
            },
        )
        return {"record": record, "api_key": api_key}

    @staticmethod
    async def delete(db: AsyncSession, principal: EffectivePrincipal, api_key_id: int) -> None:
        item = await ApiKeyService.get_scoped(db, principal, api_key_id)
        if item.is_active:
            raise ValidationError("Disable the API key before deleting it")
        await ApiKeyRepository.delete(db, item)

    @staticmethod
    async def authenticate(db: AsyncSession, api_key: str) -> ApiKey:
        if not api_key.startswith("sk-odk-"):
            raise UnauthorizedError("Invalid API key")
        item = await ApiKeyRepository.get_by_hash(db, ApiKeyService.hash_api_key(api_key))
        if not item:
            raise UnauthorizedError("Invalid API key")
        if not item.is_active:
            raise ForbiddenError("API key disabled")
        return item

    @staticmethod
    async def authenticate_open_api_context(db: AsyncSession, api_key: str) -> OpenApiContext:
        item = await ApiKeyService.authenticate(db, api_key)
        updated = await ApiKeyRepository.update_last_used(db, item, datetime.now(timezone.utc))
        return OpenApiContext(
            tenant_id=updated.tenant_id,
            api_key_id=updated.id,
            api_key_name=updated.name,
            api_key_version=updated.key_version,
            is_active=updated.is_active,
        )

    @staticmethod
    async def issue_context_token(
        db: AsyncSession,
        context: OpenApiContext,
        data: ContextTokenRequest,
    ) -> ContextTokenResponse:
        channel = await ChannelRepository.get_by_key(db, data.channel_key)
        if not channel or not channel.public_access_enabled or channel.tenant_id != context.tenant_id:
            raise NotFoundError("Channel not found")

        expires_seconds = data.expires_seconds or settings.API_CONTEXT_TOKEN_EXPIRE_SECONDS
        payload = {
            "tenant_id": context.tenant_id,
            "channel_key": channel.channel_key,
            "api_key_id": context.api_key_id,
            "api_key_version": context.api_key_version,
            "nonce": secrets.token_urlsafe(18),
        }
        if data.customer is not None:
            payload["customer"] = data.customer
        if data.session_summary is not None:
            payload["session_summary"] = data.session_summary

        token = create_context_token(payload, expires_seconds=expires_seconds)
        return ContextTokenResponse(contextToken=token, expiresIn=expires_seconds)
