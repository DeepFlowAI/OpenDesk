"""
Integration tests for the call-center module:
- agent_status get/set
- agent_webrtc_session open/get/close
- call_records list/get (orchestrator-created CDRs read via API)
"""
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import delete

from app.core.security import create_access_token
from app.db.session import AsyncSessionLocal
from app.models.call_record import CallRecord
from app.models.tenant import Tenant
from app.repositories.user_repository import UserRepository


def _auth(employee_id: int = 1, tenant_id: int = 7) -> dict:
    token = create_access_token(
        {"sub": str(employee_id), "tenant_id": tenant_id, "roles": ["admin"]}
    )
    return {"Authorization": f"Bearer {token}"}


async def _create_tenant() -> int:
    async with AsyncSessionLocal() as db:
        tenant = Tenant(
            tenant_id=f"call_assoc_{uuid.uuid4().hex[:8]}",
            name="Call Association Test Tenant",
            is_active=True,
        )
        db.add(tenant)
        await db.commit()
        await db.refresh(tenant)
        return tenant.id


async def _cleanup_tenant(tenant_id: int) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Tenant).where(Tenant.id == tenant_id))
        await db.commit()


async def _create_user(tenant_id: int, *, name: str, phone: str):
    async with AsyncSessionLocal() as db:
        return await UserRepository.create(
            db,
            {
                "tenant_id": tenant_id,
                "external_id": f"ext_{uuid.uuid4().hex[:12]}",
                "name": name,
                "phone": phone,
            },
        )


async def _create_call_record(
    tenant_id: int,
    *,
    direction: str,
    from_number: str | None,
    to_number: str | None,
    user_id: int | None = None,
) -> int:
    async with AsyncSessionLocal() as db:
        row = CallRecord(
            tenant_id=tenant_id,
            call_id=f"call-{uuid.uuid4().hex}",
            direction=direction,
            state="completed",
            from_number=from_number,
            to_number=to_number,
            user_id=user_id,
            extra_metadata={},
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row.id


class TestAgentStatusAPI:

    @pytest.mark.asyncio
    async def test_get_status_returns_200(self, client: AsyncClient):
        # Dev DB may have residual state from earlier runs — assert structure
        # rather than the exact status value.
        r = await client.get("/api/v1/call-center/agent-status/me", headers=_auth())
        assert r.status_code == 200
        body = r.json()
        assert "status" in body
        assert body["status"] in {"ready", "busy", "break", "after_call_work", "offline"}

    @pytest.mark.asyncio
    async def test_set_status_persists(self, client: AsyncClient):
        # use a unique employee id so re-runs don't collide
        emp = (uuid.uuid4().int % 1_000_000) + 100
        headers = _auth(employee_id=emp)
        # employee row may not exist — call the upsert anyway via the API.
        # The agent_status FK to employees blocks this in a clean DB. We use
        # an existing employee instead.
        # Instead, fall back to employee_id=1 which is seeded.
        headers = _auth(employee_id=1)
        r = await client.put(
            "/api/v1/call-center/agent-status/me",
            headers=headers,
            json={"status": "ready"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "ready"
        assert r.json()["resource_state"] == "idle"

        # Read back
        g = await client.get("/api/v1/call-center/agent-status/me", headers=headers)
        assert g.json()["status"] == "ready"
        assert g.json()["resource_state"] == "idle"


class TestWebRTCSessionAPI:

    @pytest.mark.asyncio
    async def test_open_close_idempotent(self, client: AsyncClient):
        headers = _auth(employee_id=1)
        # Make sure no leftover session from a previous run
        await client.delete("/api/v1/call-center/agents/me/webrtc-session", headers=headers)

        webrtc_call_id = f"webrtc-{uuid.uuid4().hex[:8]}"
        o = await client.post(
            "/api/v1/call-center/agents/me/webrtc-session",
            headers=headers,
            json={"webrtc_call_id": webrtc_call_id},
        )
        assert o.status_code == 201, o.text
        assert o.json()["webrtc_call_id"] == webrtc_call_id

        g = await client.get(
            "/api/v1/call-center/agents/me/webrtc-session", headers=headers,
        )
        assert g.status_code == 200
        assert g.json()["webrtc_call_id"] == webrtc_call_id

        d = await client.delete(
            "/api/v1/call-center/agents/me/webrtc-session", headers=headers,
        )
        assert d.status_code == 200

        # Idempotent
        d2 = await client.delete(
            "/api/v1/call-center/agents/me/webrtc-session", headers=headers,
        )
        assert d2.status_code == 200

    @pytest.mark.asyncio
    async def test_cannot_open_twice(self, client: AsyncClient):
        headers = _auth(employee_id=1)
        await client.delete("/api/v1/call-center/agents/me/webrtc-session", headers=headers)
        await client.post(
            "/api/v1/call-center/agents/me/webrtc-session",
            headers=headers,
            json={"webrtc_call_id": f"webrtc-{uuid.uuid4().hex[:8]}"},
        )
        dup = await client.post(
            "/api/v1/call-center/agents/me/webrtc-session",
            headers=headers,
            json={"webrtc_call_id": f"webrtc-{uuid.uuid4().hex[:8]}"},
        )
        assert dup.status_code == 409
        # Cleanup
        await client.delete("/api/v1/call-center/agents/me/webrtc-session", headers=headers)


class TestCallRecordsAPI:

    @pytest.mark.asyncio
    async def test_list_returns_empty_for_fresh_tenant(self, client: AsyncClient):
        headers = _auth(tenant_id=4242, employee_id=1)
        r = await client.get("/api/v1/call-center/call-records", headers=headers)
        # tenant 4242 has no records; might 422 if tenant doesn't exist for FKs
        # — but list query doesn't validate tenant existence, just returns empty.
        assert r.status_code == 200
        assert r.json()["items"] == []

    @pytest.mark.asyncio
    async def test_get_nonexistent_404(self, client: AsyncClient):
        r = await client.get(
            "/api/v1/call-center/call-records/999999", headers=_auth(),
        )
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_list_filters_by_associated_user(self, client: AsyncClient):
        tenant_id = await _create_tenant()
        try:
            alice = await _create_user(tenant_id, name="Alice", phone="18601123206")
            bob = await _create_user(tenant_id, name="Bob", phone="15500008888")
            alice_record_id = await _create_call_record(
                tenant_id,
                direction="inbound",
                from_number="18601123206",
                to_number="4001681715",
                user_id=alice.id,
            )
            await _create_call_record(
                tenant_id,
                direction="outbound",
                from_number="4001681715",
                to_number="15500008888",
                user_id=bob.id,
            )

            resp = await client.get(
                "/api/v1/call-center/call-records",
                headers=_auth(tenant_id=tenant_id),
                params={"user_id": alice.id},
            )

            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["total"] == 1
            assert body["items"][0]["id"] == alice_record_id
            assert body["items"][0]["user_public_id"] == alice.public_id
        finally:
            await _cleanup_tenant(tenant_id)

    @pytest.mark.asyncio
    async def test_identify_links_existing_user_by_normalized_phone(self, client: AsyncClient):
        tenant_id = await _create_tenant()
        try:
            user = await _create_user(tenant_id, name="Alice", phone="186-0112-3206")
            record_id = await _create_call_record(
                tenant_id,
                direction="inbound",
                from_number="+86 18601123206",
                to_number="4001681715",
            )

            resp = await client.post(
                f"/api/v1/call-center/call-records/{record_id}/identify-user",
                headers=_auth(tenant_id=tenant_id),
            )

            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["status"] == "linked"
            assert body["user"]["id"] == user.id

            detail = await client.get(
                f"/api/v1/call-center/call-records/{record_id}",
                headers=_auth(tenant_id=tenant_id),
            )
            assert detail.status_code == 200
            assert detail.json()["user_public_id"] == user.public_id
            assert detail.json()["user_association_status"] == "linked"
        finally:
            await _cleanup_tenant(tenant_id)

    @pytest.mark.asyncio
    async def test_identify_auto_creates_user_when_no_match(self, client: AsyncClient):
        tenant_id = await _create_tenant()
        try:
            record_id = await _create_call_record(
                tenant_id,
                direction="outbound",
                from_number="4001681715",
                to_number="15500008888",
            )

            resp = await client.post(
                f"/api/v1/call-center/call-records/{record_id}/identify-user",
                headers=_auth(tenant_id=tenant_id),
            )

            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["status"] == "created"
            assert body["user"]["phone"] == "15500008888"
        finally:
            await _cleanup_tenant(tenant_id)

    @pytest.mark.asyncio
    async def test_identify_multiple_then_manual_link(self, client: AsyncClient):
        tenant_id = await _create_tenant()
        try:
            first = await _create_user(tenant_id, name="First", phone="18800001111")
            second = await _create_user(tenant_id, name="Second", phone="18800001111")
            record_id = await _create_call_record(
                tenant_id,
                direction="inbound",
                from_number="18800001111",
                to_number="4001681715",
            )

            resp = await client.post(
                f"/api/v1/call-center/call-records/{record_id}/identify-user",
                headers=_auth(tenant_id=tenant_id),
            )
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["status"] == "multiple"
            assert {item["id"] for item in body["candidates"]} == {first.id, second.id}

            link = await client.put(
                f"/api/v1/call-center/call-records/{record_id}/associated-user",
                headers=_auth(tenant_id=tenant_id),
                json={"user_id": second.id},
            )
            assert link.status_code == 200, link.text
            assert link.json()["status"] == "linked"
            assert link.json()["user"]["id"] == second.id
        finally:
            await _cleanup_tenant(tenant_id)
