"""Per-tenant cache of active call event subscription rules for the call hot path."""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.redis import redis_client
from app.repositories.call_event_subscription_repository import CallEventSubscriptionRepository

logger = logging.getLogger(__name__)

_VERSION_KEY = "call_event_rules:version:{tenant_id}"
_LOCAL_TTL_SECONDS = 30.0
_REDIS_TIMEOUT_SECONDS = 0.2


@dataclass(frozen=True)
class CachedCallEventRule:
    id: int
    event_types: frozenset[str]
    directions: frozenset[str]
    call_sources: frozenset[str]

    def matches(self, *, event_type: str, direction: str | None, call_source: str | None) -> bool:
        return (
            event_type in self.event_types
            and direction in self.directions
            and call_source in self.call_sources
        )


@dataclass
class _Entry:
    version: str | None
    expires_at: float
    rules: tuple[CachedCallEventRule, ...]


class CallEventRuleCache:
    """Process-local rule cache validated by a Redis version counter.

    Saves bump the tenant version so every worker reloads on its next lookup;
    the short local TTL bounds staleness when Redis is unavailable.
    """

    _entries: dict[int, _Entry] = {}

    @staticmethod
    async def _read_version(tenant_id: int) -> str | None:
        try:
            return await asyncio.wait_for(
                redis_client.client.get(_VERSION_KEY.format(tenant_id=tenant_id)),
                timeout=_REDIS_TIMEOUT_SECONDS,
            )
        except Exception:
            return None

    @classmethod
    async def invalidate(cls, tenant_id: int) -> None:
        cls._entries.pop(tenant_id, None)
        try:
            await asyncio.wait_for(
                redis_client.client.incr(_VERSION_KEY.format(tenant_id=tenant_id)),
                timeout=_REDIS_TIMEOUT_SECONDS,
            )
        except Exception:
            logger.warning(
                "call event rule cache invalidation failed tenant_id=%s", tenant_id
            )

    @classmethod
    async def lookup(
        cls, tenant_id: int
    ) -> tuple[str | None, tuple[CachedCallEventRule, ...] | None]:
        """Return ``(version, rules)``; ``rules`` is None when a DB load is needed."""
        version = await cls._read_version(tenant_id)
        entry = cls._entries.get(tenant_id)
        if (
            entry is not None
            and entry.version == version
            and entry.expires_at > time.monotonic()
        ):
            return version, entry.rules
        return version, None

    @classmethod
    async def get_active_rules(
        cls, db: AsyncSession, tenant_id: int
    ) -> tuple[CachedCallEventRule, ...]:
        version, rules = await cls.lookup(tenant_id)
        if rules is not None:
            return rules
        return await cls.load(db, tenant_id, version)

    @classmethod
    async def load(
        cls, db: AsyncSession, tenant_id: int, version: str | None
    ) -> tuple[CachedCallEventRule, ...]:
        now = time.monotonic()
        rows = await CallEventSubscriptionRepository.list_active_rules(db, tenant_id)
        rules = tuple(
            CachedCallEventRule(
                id=row.id,
                event_types=frozenset(row.event_types or []),
                directions=frozenset(row.directions or []),
                call_sources=frozenset(row.call_sources or []),
            )
            for row in rows
        )
        cls._entries[tenant_id] = _Entry(
            version=version, expires_at=now + _LOCAL_TTL_SECONDS, rules=rules
        )
        return rules

    @classmethod
    def clear(cls) -> None:
        cls._entries.clear()
