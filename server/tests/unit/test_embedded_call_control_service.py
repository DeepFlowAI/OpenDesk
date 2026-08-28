"""Unit tests for embedded call control ownership leases."""
import json

import pytest

from app.core.exceptions import BusinessError
from app.services.embedded_call_control_service import EmbeddedCallControlService


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def set(
        self, key: str, value: str, *, ex: int | None = None, nx: bool = False
    ) -> bool:
        del ex
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def eval(self, script: str, count: int, key: str, *args: object) -> int:
        del count
        current = json.loads(self.values[key]) if key in self.values else None
        if current is None or current.get("lease_token") != args[0]:
            return 0
        if "DEL" in script:
            del self.values[key]
        return 1


def session(instance_id: str) -> dict:
    return {
        "typ": "embedded_call_session",
        "tenant_id": 7,
        "user_id": 19,
        "integration_id": 41,
        "instance_id": instance_id,
    }


@pytest.mark.asyncio
async def test_only_first_instance_acquires_control() -> None:
    redis = FakeRedis()
    first = await EmbeddedCallControlService.acquire(
        redis,
        session=session("instance-one"),
        instance_id="instance-one",
        surface="embedded_call",
    )
    second = await EmbeddedCallControlService.acquire(
        redis,
        session=session("instance-two"),
        instance_id="instance-two",
        surface="embedded_call",
    )
    assert first.is_owner is True
    assert first.owner_surface == "embedded_call"
    assert second.is_owner is False
    assert second.owner_instance_id == "instance-one"
    assert second.owner_surface == "embedded_call"


@pytest.mark.asyncio
async def test_takeover_invalidates_old_lease() -> None:
    redis = FakeRedis()
    first = await EmbeddedCallControlService.acquire(
        redis,
        session=session("instance-one"),
        instance_id="instance-one",
        surface="embedded_call",
    )
    second = await EmbeddedCallControlService.takeover(
        redis,
        session=session("instance-two"),
        instance_id="instance-two",
        surface="embedded_call",
    )
    old_heartbeat = await EmbeddedCallControlService.heartbeat(
        redis,
        session=session("instance-one"),
        instance_id="instance-one",
        lease_token=first.lease_token or "",
    )
    assert second.is_owner is True
    assert second.owner_surface == "embedded_call"
    assert old_heartbeat.is_owner is False
    await EmbeddedCallControlService.assert_owner(redis, session=session("instance-two"))
    with pytest.raises(BusinessError) as exc_info:
        await EmbeddedCallControlService.assert_owner(
            redis, session=session("instance-one")
        )
    assert exc_info.value.code == "EMBED_CONTROL_NOT_OWNER"


@pytest.mark.asyncio
async def test_workspace_acquire_reports_workspace_surface() -> None:
    redis = FakeRedis()
    first = await EmbeddedCallControlService.acquire(
        redis,
        session={
            "typ": "access",
            "tenant_id": 7,
            "user_id": 19,
        },
        instance_id="workspace-one",
        surface="opendesk_workspace",
    )
    second = await EmbeddedCallControlService.acquire(
        redis,
        session={
            "typ": "access",
            "tenant_id": 7,
            "user_id": 19,
        },
        instance_id="workspace-two",
        surface="opendesk_workspace",
    )
    assert first.is_owner is True
    assert first.owner_surface == "opendesk_workspace"
    assert second.is_owner is False
    assert second.owner_instance_id == "workspace-one"
    assert second.owner_surface == "opendesk_workspace"
