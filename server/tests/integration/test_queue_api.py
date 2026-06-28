"""
Integration tests for unified queue API.
"""
import time

import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.core.security import create_access_token
from app.db.session import AsyncSessionLocal
from app.models.employee import Employee
from app.models.employee_group import EmployeeGroup, EmployeeGroupMember
from tests.integration.rbac_helpers import auth_headers_for_seeded_admin, ensure_admin_principals


@pytest_asyncio.fixture(autouse=True)
async def seed_admin_principals(monkeypatch):
    async def skip_queue_realtime(*args, **kwargs):
        return None

    monkeypatch.setattr(
        "app.services.queue_realtime_service.QueueRealtimeService.emit_queue_updated",
        skip_queue_realtime,
    )
    await ensure_admin_principals([7])


def _auth_header(tenant_id: int = 7, user_id: int | None = None, role: str = "admin") -> dict:
    if user_id is None:
        return auth_headers_for_seeded_admin(tenant_id)
    token = create_access_token({"sub": str(user_id), "tenant_id": tenant_id, "roles": [role]})
    return {"Authorization": f"Bearer {token}"}


async def _create_agent_and_group(client: AsyncClient, tenant_id: int = 7) -> tuple[int, int]:
    agent_ids, group_id = await _create_agents_and_group(client, max_concurrents=[2], tenant_id=tenant_id)
    return agent_ids[0], group_id


async def _create_agents_and_group(
    _client: AsyncClient,
    *,
    max_concurrents: list[int],
    tenant_id: int = 7,
) -> tuple[list[int], int]:
    ts = time.time_ns()
    employee_ids: list[int] = []
    async with AsyncSessionLocal() as db:
        for index, max_concurrent in enumerate(max_concurrents, start=1):
            employee = Employee(
                tenant_id=tenant_id,
                username=f"qagt{index}_{ts}",
                email=f"queue-agent-{index}-{ts}@example.com",
                password_hash="test-password-hash",
                display_name=f"Queue Agent {index} {ts}",
                name=f"Queue Agent {index} {ts}",
                roles=["agent"],
                max_concurrent=max_concurrent,
                is_active=True,
            )
            db.add(employee)
            await db.flush()
            employee_ids.append(employee.id)

        group = EmployeeGroup(tenant_id=tenant_id, name=f"Queue Group {ts}")
        db.add(group)
        await db.flush()
        for employee_id in employee_ids:
            db.add(EmployeeGroupMember(group_id=group.id, employee_id=employee_id))
        await db.commit()
        return employee_ids, group.id


class TestQueueAPI:
    @pytest.mark.asyncio
    async def test_enqueue_returns_position_and_state(self, client: AsyncClient):
        headers = _auth_header()
        _, group_id = await _create_agent_and_group(client)

        resp = await client.post(
            "/api/v1/queue/tasks/enqueue",
            json={
                "channel": "online_chat",
                "task_type": "manual",
                "task_ref_id": f"manual-{time.time_ns()}",
                "queue_type": "employee_group",
                "queue_id": group_id,
                "priority": 4,
            },
            headers=headers,
        )

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["accepted"] is True
        assert data["position"]["position_in_priority"] == 1
        task_id = data["task"]["id"]

        state_resp = await client.get(
            f"/api/v1/queue/state?channel=online_chat&queue_type=employee_group&queue_id={group_id}&task_id={task_id}",
            headers=headers,
        )
        assert state_resp.status_code == 200, state_resp.text
        state = state_resp.json()
        assert state["waiting_count"] >= 1
        assert state["position_in_priority"] == 1

    @pytest.mark.asyncio
    async def test_policy_max_waiting_count_blocks_enqueue(self, client: AsyncClient):
        headers = _auth_header()
        _, group_id = await _create_agent_and_group(client)

        policy_resp = await client.put(
            "/api/v1/queue/policies",
            json={
                "channel": "online_chat",
                "scope_type": "employee_group",
                "scope_id": group_id,
                "enabled": True,
                "assignment_strategy": "round_robin",
                "max_waiting_count": 1,
            },
            headers=headers,
        )
        assert policy_resp.status_code == 200, policy_resp.text

        first = await client.post(
            "/api/v1/queue/tasks/enqueue",
            json={
                "channel": "online_chat",
                "task_type": "manual",
                "task_ref_id": f"manual-{time.time_ns()}",
                "queue_type": "employee_group",
                "queue_id": group_id,
            },
            headers=headers,
        )
        assert first.status_code == 200, first.text

        blocked = await client.post(
            "/api/v1/queue/tasks/enqueue",
            json={
                "channel": "online_chat",
                "task_type": "manual",
                "task_ref_id": f"manual-{time.time_ns()}",
                "queue_type": "employee_group",
                "queue_id": group_id,
            },
            headers=headers,
        )
        assert blocked.status_code == 409
        assert blocked.json()["code"] == "QUEUE_LIMIT_REACHED"

    @pytest.mark.asyncio
    async def test_policy_rejects_unsupported_channel_strategy(self, client: AsyncClient):
        headers = _auth_header()
        _, group_id = await _create_agent_and_group(client)

        policy_resp = await client.put(
            "/api/v1/queue/policies",
            json={
                "channel": "online_chat",
                "scope_type": "employee_group",
                "scope_id": group_id,
                "enabled": True,
                "assignment_strategy": "today_call_duration_low",
            },
            headers=headers,
        )

        assert policy_resp.status_code == 422, policy_resp.text

    @pytest.mark.asyncio
    async def test_policy_rejects_strategy_without_runtime_metric(self, client: AsyncClient):
        headers = _auth_header()
        _, group_id = await _create_agent_and_group(client)

        policy_resp = await client.put(
            "/api/v1/queue/policies",
            json={
                "channel": "call_center",
                "scope_type": "employee_group",
                "scope_id": group_id,
                "enabled": True,
                "assignment_strategy": "idle_longest",
            },
            headers=headers,
        )

        assert policy_resp.status_code == 422, policy_resp.text

    @pytest.mark.asyncio
    async def test_employee_policy_clears_assignment_strategy(self, client: AsyncClient):
        headers = _auth_header()
        employee_id, _ = await _create_agent_and_group(client)

        policy_resp = await client.put(
            "/api/v1/queue/policies",
            json={
                "channel": "call_center",
                "scope_type": "employee",
                "scope_id": employee_id,
                "enabled": True,
                "assignment_strategy": "round_robin",
                "max_waiting_count": 2,
                "max_wait_seconds": 30,
            },
            headers=headers,
        )

        assert policy_resp.status_code == 200, policy_resp.text
        data = policy_resp.json()
        assert data["assignment_strategy"] is None
        assert data["max_waiting_count"] == 2
        assert data["max_wait_seconds"] == 30

    @pytest.mark.asyncio
    async def test_policy_rejects_queue_limit_out_of_range(self, client: AsyncClient):
        headers = _auth_header()

        policy_resp = await client.put(
            "/api/v1/queue/policies",
            json={
                "channel": "online_chat",
                "scope_type": "global",
                "assignment_strategy": "round_robin",
                "max_waiting_count": 0,
            },
            headers=headers,
        )

        assert policy_resp.status_code == 422, policy_resp.text

    @pytest.mark.asyncio
    async def test_policy_persists_returning_agent_config(self, client: AsyncClient):
        headers = _auth_header()
        _, group_id = await _create_agent_and_group(client)

        policy_resp = await client.put(
            "/api/v1/queue/policies",
            json={
                "channel": "online_chat",
                "scope_type": "employee_group",
                "scope_id": group_id,
                "enabled": True,
                "assignment_strategy": "round_robin",
                "config": {
                    "returning_agent_priority_enabled": True,
                    "returning_agent_window_hours": 48,
                },
            },
            headers=headers,
        )

        assert policy_resp.status_code == 200, policy_resp.text
        data = policy_resp.json()
        assert data["config"]["returning_agent_priority_enabled"] is True
        assert data["config"]["returning_agent_window_hours"] == 48

    @pytest.mark.asyncio
    async def test_dispatch_assigns_online_chat_agent(self, client: AsyncClient):
        headers = _auth_header()
        employee_id, group_id = await _create_agent_and_group(client)
        agent_headers = _auth_header(user_id=employee_id, role="agent")

        status_resp = await client.put("/api/v1/agent/status", json={"status": "online"}, headers=agent_headers)
        assert status_resp.status_code == 200, status_resp.text

        enqueue_resp = await client.post(
            "/api/v1/queue/tasks/enqueue",
            json={
                "channel": "online_chat",
                "task_type": "manual",
                "task_ref_id": f"manual-{time.time_ns()}",
                "queue_type": "employee_group",
                "queue_id": group_id,
            },
            headers=headers,
        )
        assert enqueue_resp.status_code == 200, enqueue_resp.text

        dispatch_resp = await client.post(
            "/api/v1/queue/dispatch",
            json={"channel": "online_chat", "queue_type": "employee_group", "queue_id": group_id},
            headers=headers,
        )
        assert dispatch_resp.status_code == 200, dispatch_resp.text
        data = dispatch_resp.json()
        assert data["dispatched"] is True
        assert data["agent_id"] == employee_id
        assert data["task"]["status"] == "assigned"
