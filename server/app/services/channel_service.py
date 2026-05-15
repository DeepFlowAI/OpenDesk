"""
Channel service — business logic layer
"""
from datetime import datetime, time, timezone
from typing import Any

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.repositories.channel_repository import ChannelRepository
from app.repositories.service_hours_repository import ServiceHoursRepository
from app.models.service_hours import ServiceHours
from app.schemas.channel import ChannelCreate, ChannelUpdate
from app.schemas.channel import ChannelConfig, DEFAULT_OFFLINE_MESSAGE, DEFAULT_OFFLINE_TITLE
from app.services.agent_status_service import AgentStatusService


class ChannelService:

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
        }
