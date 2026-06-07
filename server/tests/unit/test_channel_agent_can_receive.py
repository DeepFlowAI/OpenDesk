"""
Unit tests for ``ChannelService._agent_can_receive``.

Eligibility is driven by the ``chat.workspace.use`` effective permission
(replacing the legacy ``"agent" in roles`` check). Repositories, Redis, and
the agent status service are mocked so the suite stays pure logic.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.enums import AgentOnlineStatus
from app.services import channel_service as cs
from app.services.channel_service import ChannelService


def _employee(*, tenant_id: int = 7, is_active: bool = True, max_concurrent: int = 5):
    return SimpleNamespace(
        id=22,
        tenant_id=tenant_id,
        is_active=is_active,
        max_concurrent=max_concurrent,
    )


def _online_status(max_concurrent: int = 5):
    return {
        "user_id": 22,
        "status": AgentOnlineStatus.ONLINE.value,
        "current_count": 0,
        "max_concurrent": max_concurrent,
    }


class TestAgentCanReceive:

    @pytest.mark.asyncio
    async def test_with_chat_access_and_online_can_receive(self):
        with patch.object(
            cs.EmployeeRepository, "get_by_id", new=AsyncMock(return_value=_employee())
        ), patch.object(
            cs.EmployeeRepository,
            "has_effective_permission",
            new=AsyncMock(return_value=True),
        ), patch.object(
            cs.AgentStatusService,
            "get_status",
            new=AsyncMock(return_value=_online_status()),
        ):
            can_receive, max_concurrent = await ChannelService._agent_can_receive(
                AsyncMock(), AsyncMock(), 7, 22
            )

        assert can_receive is True
        assert max_concurrent == 5

    @pytest.mark.asyncio
    async def test_without_chat_access_cannot_receive(self):
        perm_mock = AsyncMock(return_value=False)
        status_mock = AsyncMock(return_value=_online_status())
        with patch.object(
            cs.EmployeeRepository, "get_by_id", new=AsyncMock(return_value=_employee())
        ), patch.object(
            cs.EmployeeRepository, "has_effective_permission", new=perm_mock
        ), patch.object(
            cs.AgentStatusService, "get_status", new=status_mock
        ):
            can_receive, _ = await ChannelService._agent_can_receive(
                AsyncMock(), AsyncMock(), 7, 22
            )

        assert can_receive is False
        perm_mock.assert_awaited_once()
        # No need to inspect realtime status once eligibility already failed.
        status_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_inactive_employee_cannot_receive(self):
        with patch.object(
            cs.EmployeeRepository,
            "get_by_id",
            new=AsyncMock(return_value=_employee(is_active=False)),
        ):
            can_receive, _ = await ChannelService._agent_can_receive(
                AsyncMock(), AsyncMock(), 7, 22
            )

        assert can_receive is False

    @pytest.mark.asyncio
    async def test_cross_tenant_employee_cannot_receive(self):
        with patch.object(
            cs.EmployeeRepository,
            "get_by_id",
            new=AsyncMock(return_value=_employee(tenant_id=999)),
        ):
            can_receive, _ = await ChannelService._agent_can_receive(
                AsyncMock(), AsyncMock(), 7, 22
            )

        assert can_receive is False
