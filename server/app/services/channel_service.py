"""
Channel service — business logic layer
"""
from datetime import datetime, time, timezone
from typing import Any
import re
import secrets

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.configs.settings import settings
from app.core.exceptions import NotFoundError, UnauthorizedError, ValidationError
from app.core.security import (
    create_visitor_identity_secret,
    create_visitor_session_token,
    decode_visitor_session_token,
    verify_visitor_identity_secret,
)
from app.repositories.channel_repository import ChannelRepository
from app.repositories.service_hours_repository import ServiceHoursRepository
from app.models.service_hours import ServiceHours
from app.schemas.channel import ChannelCreate, ChannelUpdate
from app.schemas.channel import ChannelConfig, DEFAULT_OFFLINE_MESSAGE, DEFAULT_OFFLINE_TITLE
from app.schemas.visitor_session import VisitorSessionRequest
from app.services.agent_status_service import AgentStatusService

CHANNEL_KEY_RE = re.compile(r"^ch_[A-Za-z0-9_-]{24,}$")
VISITOR_EXTERNAL_ID_PREFIX = "v_"
VISITOR_EXTERNAL_ID_RANDOM_BYTES = 24


class ChannelService:
    @staticmethod
    def generate_visitor_external_id() -> str:
        """Generate a high-entropy anonymous visitor identifier."""
        return f"{VISITOR_EXTERNAL_ID_PREFIX}{secrets.token_urlsafe(VISITOR_EXTERNAL_ID_RANDOM_BYTES)}"

    @staticmethod
    def _parse_datetime(value: str) -> datetime | None:
        try:
            normalized = value.replace("Z", "+00:00")
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=datetime.now().astimezone().tzinfo)
        return parsed

    @staticmethod
    def _parse_time(value: str) -> time | None:
        try:
            hour, minute = value.split(":")
            return time(hour=int(hour), minute=int(minute))
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _is_in_datetime_range(now: datetime, item: dict[str, Any]) -> bool:
        start = ChannelService._parse_datetime(str(item.get("start", "")))
        end = ChannelService._parse_datetime(str(item.get("end", "")))
        if not start or not end:
            return False
        comparable_now = now.astimezone(start.tzinfo)
        comparable_end = end.astimezone(start.tzinfo)
        return start <= comparable_now <= comparable_end

    @staticmethod
    def _is_in_time_slot(now_time: time, slot: dict[str, Any]) -> bool:
        start = ChannelService._parse_time(str(slot.get("start", "")))
        end = ChannelService._parse_time(str(slot.get("end", "")))
        if not start or not end:
            return False
        if start <= end:
            return start <= now_time <= end
        return now_time >= start or now_time <= end

    @staticmethod
    def is_within_service_hours(service_hours: ServiceHours, now: datetime | None = None) -> bool:
        """Evaluate service hours by makeup days, holidays, then weekly schedule."""
        current = now or datetime.now(timezone.utc).astimezone()

        if any(ChannelService._is_in_datetime_range(current, item) for item in service_hours.makeup_days):
            return True

        if any(ChannelService._is_in_datetime_range(current, item) for item in service_hours.holidays):
            return False

        day_of_week = current.isoweekday()
        now_time = current.time().replace(second=0, microsecond=0)
        for schedule in service_hours.weekly_schedules:
            if schedule.get("day_of_week") != day_of_week:
                continue
            if any(ChannelService._is_in_time_slot(now_time, slot) for slot in schedule.get("slots", [])):
                return True
        return False

    @staticmethod
    async def _normalize_config(
        db: AsyncSession,
        tenant_id: int,
        config: ChannelConfig,
    ) -> dict:
        payload = config.model_dump()
        payload["offline_title"] = (payload.get("offline_title") or DEFAULT_OFFLINE_TITLE).strip()
        payload["offline_message"] = payload.get("offline_message") or DEFAULT_OFFLINE_MESSAGE

        if not payload.get("service_hours_enabled"):
            payload["service_hours_enabled"] = False
            payload["service_hours_id"] = None
            return payload

        service_hours_id = payload.get("service_hours_id")
        if not service_hours_id:
            raise ValidationError("Service hours is required when enabled")

        service_hours = await ServiceHoursRepository.get_by_id(db, int(service_hours_id))
        if not service_hours or service_hours.tenant_id != tenant_id:
            raise ValidationError("Service hours not found for current tenant")

        return payload

    @staticmethod
    async def list_by_tenant(db: AsyncSession, tenant_id: int):
        return await ChannelRepository.get_by_tenant(db, tenant_id)

    @staticmethod
    async def get_by_id(db: AsyncSession, channel_id: int, tenant_id: int):
        item = await ChannelRepository.get_by_id(db, channel_id)
        if not item or item.tenant_id != tenant_id:
            raise NotFoundError("Channel not found")
        return item

    @staticmethod
    async def create(db: AsyncSession, tenant_id: int, data: ChannelCreate):
        payload = data.model_dump()
        payload["tenant_id"] = tenant_id
        payload["channel_key"] = await ChannelRepository.generate_unique_channel_key(db)
        payload["config"] = await ChannelService._normalize_config(db, tenant_id, data.config)
        return await ChannelRepository.create(db, payload)

    @staticmethod
    async def update(db: AsyncSession, channel_id: int, tenant_id: int, data: ChannelUpdate):
        item = await ChannelRepository.get_by_id(db, channel_id)
        if not item or item.tenant_id != tenant_id:
            raise NotFoundError("Channel not found")
        payload = data.model_dump()
        payload["config"] = await ChannelService._normalize_config(db, tenant_id, data.config)
        return await ChannelRepository.update(db, item, payload)

    @staticmethod
    async def rotate_key(db: AsyncSession, channel_id: int, tenant_id: int):
        item = await ChannelRepository.get_by_id(db, channel_id)
        if not item or item.tenant_id != tenant_id:
            raise NotFoundError("Channel not found")
        channel_key = await ChannelRepository.generate_unique_channel_key(db)
        return await ChannelRepository.rotate_channel_key(db, item, channel_key)

    @staticmethod
    async def delete(db: AsyncSession, channel_id: int, tenant_id: int) -> None:
        item = await ChannelRepository.get_by_id(db, channel_id)
        if not item or item.tenant_id != tenant_id:
            raise NotFoundError("Channel not found")
        await ChannelRepository.delete(db, item)

    @staticmethod
    async def get_public_config(db: AsyncSession, channel_id: int):
        """Get channel config for public visitor-facing widget (no tenant check)."""
        item = await ChannelRepository.get_by_id(db, channel_id)
        if not item:
            raise NotFoundError("Channel not found")
        return item

    @staticmethod
    async def get_public_channel_by_key(db: AsyncSession, channel_key: str):
        """Get a public channel by key and hide disabled/missing channels behind 404."""
        if not CHANNEL_KEY_RE.fullmatch(channel_key):
            raise NotFoundError("Channel not found")
        item = await ChannelRepository.get_by_key(db, channel_key)
        if not item or not item.public_access_enabled:
            raise NotFoundError("Channel not found")
        return item

    @staticmethod
    async def check_channel_availability(
        db: AsyncSession,
        r: aioredis.Redis,
        channel_id: int,
    ) -> dict:
        """Check whether a visitor may start a new conversation for this channel."""
        item = await ChannelRepository.get_by_id(db, channel_id)
        if not item:
            raise NotFoundError("Channel not found")

        config = ChannelConfig.model_validate(item.config or {})
        offline_title = config.offline_title or DEFAULT_OFFLINE_TITLE
        offline_message = config.offline_message or DEFAULT_OFFLINE_MESSAGE
        checked_at = datetime.now(timezone.utc)

        if config.service_hours_enabled:
            if not config.service_hours_id:
                return {
                    "can_start_conversation": False,
                    "reason": "outside_service_hours",
                    "offline_title": offline_title,
                    "offline_message": offline_message,
                    "checked_at": checked_at,
                }
            service_hours = await ServiceHoursRepository.get_by_id(db, config.service_hours_id)
            if (
                not service_hours
                or service_hours.tenant_id != item.tenant_id
                or not ChannelService.is_within_service_hours(service_hours, checked_at)
            ):
                return {
                    "can_start_conversation": False,
                    "reason": "outside_service_hours",
                    "offline_title": offline_title,
                    "offline_message": offline_message,
                    "checked_at": checked_at,
                }

        # Lazy import to avoid circular dependency with routing_service
        from app.services.routing_service import RoutingService

        _, group_member_ids, max_concurrent_map = await RoutingService.route_conversation(
            db, item.tenant_id, item.id
        )
        has_available_agent = False
        for user_id in group_member_ids:
            status_data = await AgentStatusService.get_status(
                r,
                item.tenant_id,
                user_id,
                max_concurrent_map.get(user_id, 10),
            )
            if status_data["status"] == "online" and status_data["current_count"] < status_data["max_concurrent"]:
                has_available_agent = True
                break

        if not has_available_agent:
            return {
                "can_start_conversation": False,
                "reason": "no_available_agent",
                "offline_title": offline_title,
                "offline_message": offline_message,
                "checked_at": checked_at,
            }

        return {
            "can_start_conversation": True,
            "reason": "available",
            "offline_title": offline_title,
            "offline_message": offline_message,
            "checked_at": checked_at,
        }

    @staticmethod
    async def get_public_config_with_availability(
        db: AsyncSession,
        r: aioredis.Redis,
        channel_id: int,
        visitor_external_id: str | None = None,
        current_conversation_id: int | None = None,
    ) -> dict:
        """Get public channel config plus server-side availability decision."""
        item = await ChannelRepository.get_by_id(db, channel_id)
        if not item:
            raise NotFoundError("Channel not found")
        availability = await ChannelService.check_channel_availability(db, r, channel_id)
        config = ChannelConfig.model_validate(item.config or {}).model_dump()
        has_conversation_history = False
        if visitor_external_id:
            from app.services.conversation_service import ConversationService
            has_conversation_history = await ConversationService.has_visitor_history(
                db,
                channel_id=channel_id,
                visitor_external_id=visitor_external_id,
                current_conversation_id=current_conversation_id,
            )
        from app.services.welcome_message_rule_service import WelcomeMessageRuleService
        welcome_message = await WelcomeMessageRuleService.match_public_welcome_message(db, item)
        return {
            "id": item.id,
            "tenant_id": item.tenant_id,
            "name": item.name,
            "channel_type": item.channel_type,
            "access_mode": item.access_mode,
            "logo_url": item.logo_url,
            "favicon_url": item.favicon_url,
            "config": config,
            "availability": availability,
            "has_conversation_history": has_conversation_history,
            "welcome_message": welcome_message,
        }

    @staticmethod
    async def get_public_config_with_availability_by_key(
        db: AsyncSession,
        r: aioredis.Redis,
        channel_key: str,
        visitor_external_id: str | None = None,
        current_conversation_public_id: str | None = None,
    ) -> dict:
        """Get public channel config using the high-entropy public key."""
        item = await ChannelService.get_public_channel_by_key(db, channel_key)
        availability = await ChannelService.check_channel_availability(db, r, item.id)
        config = ChannelConfig.model_validate(item.config or {}).model_dump()
        has_conversation_history = False
        if visitor_external_id:
            from app.services.conversation_service import ConversationService

            has_conversation_history = await ConversationService.has_visitor_history(
                db,
                channel_id=item.id,
                visitor_external_id=visitor_external_id,
                current_conversation_public_id=current_conversation_public_id,
            )
        from app.services.welcome_message_rule_service import WelcomeMessageRuleService
        welcome_message = await WelcomeMessageRuleService.match_public_welcome_message(db, item)
        return {
            "channel_key": item.channel_key,
            "name": item.name,
            "channel_type": item.channel_type,
            "access_mode": item.access_mode,
            "logo_url": item.logo_url,
            "favicon_url": item.favicon_url,
            "config": config,
            "availability": availability,
            "has_conversation_history": has_conversation_history,
            "welcome_message": welcome_message,
        }

    @staticmethod
    async def create_visitor_session(
        db: AsyncSession,
        channel_key: str,
        data: VisitorSessionRequest,
    ) -> dict:
        """Create a short-lived signed visitor session bound to a channel key."""
        channel = await ChannelService.get_public_channel_by_key(db, channel_key)
        issued_visitor_secret = None

        if data.visitor_external_id:
            if not data.visitor_secret:
                raise UnauthorizedError("Missing visitor secret")
            if not verify_visitor_identity_secret(
                tenant_id=channel.tenant_id,
                channel_id=channel.id,
                channel_key_version=channel.channel_key_version,
                visitor_external_id=data.visitor_external_id,
                visitor_secret=data.visitor_secret,
            ):
                raise UnauthorizedError("Invalid visitor secret")
            visitor_external_id = data.visitor_external_id
        else:
            if data.visitor_secret:
                raise ValidationError("visitor_external_id is required when visitor_secret is provided")
            visitor_external_id = ChannelService.generate_visitor_external_id()
            issued_visitor_secret = create_visitor_identity_secret(
                tenant_id=channel.tenant_id,
                channel_id=channel.id,
                channel_key_version=channel.channel_key_version,
                visitor_external_id=visitor_external_id,
            )

        payload = {
            "tenant_id": channel.tenant_id,
            "channel_id": channel.id,
            "channel_key": channel.channel_key,
            "channel_key_version": channel.channel_key_version,
            "visitor_external_id": visitor_external_id,
        }
        if data.visitor_name:
            payload["visitor_name"] = data.visitor_name
        if data.metadata:
            payload["metadata"] = data.metadata

        token = create_visitor_session_token(
            payload,
            expires_seconds=settings.VISITOR_SESSION_EXPIRE_SECONDS,
        )
        return {
            "visitor_session_token": token,
            "visitor_external_id": visitor_external_id,
            "visitor_secret": issued_visitor_secret,
            "expires_in": settings.VISITOR_SESSION_EXPIRE_SECONDS,
        }

    @staticmethod
    async def validate_visitor_session_token(db: AsyncSession, token: str) -> dict:
        """Validate a visitor token and return trusted visitor context."""
        payload = decode_visitor_session_token(token)
        if not payload:
            raise UnauthorizedError("Invalid or expired visitor session")

        try:
            tenant_id = int(payload["tenant_id"])
            channel_id = int(payload["channel_id"])
            channel_key_version = int(payload.get("channel_key_version", 1))
        except (KeyError, TypeError, ValueError):
            raise UnauthorizedError("Invalid visitor session")

        channel_key = str(payload.get("channel_key") or "")
        visitor_external_id = str(payload.get("visitor_external_id") or "")
        if not channel_key or not visitor_external_id:
            raise UnauthorizedError("Invalid visitor session")

        channel = await ChannelRepository.get_by_id(db, channel_id)
        if (
            not channel
            or not channel.public_access_enabled
            or channel.tenant_id != tenant_id
            or channel.channel_key != channel_key
            or channel.channel_key_version != channel_key_version
        ):
            raise UnauthorizedError("Invalid visitor session")

        return {
            "tenant_id": tenant_id,
            "channel_id": channel_id,
            "channel_key": channel_key,
            "channel_key_version": channel_key_version,
            "visitor_external_id": visitor_external_id,
            "visitor_name": payload.get("visitor_name"),
            "metadata": payload.get("metadata") if isinstance(payload.get("metadata"), dict) else None,
        }
