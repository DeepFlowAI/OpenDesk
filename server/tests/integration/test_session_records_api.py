"""
Integration tests for Session Records API
"""
from secrets import choice
from string import ascii_lowercase

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text

from app.core.security import hash_password, create_access_token
from app.db.session import AsyncSessionLocal

_SEEDED = False
_TOKEN = ""
_CONV_ID = 0
_CONV_PUBLIC_ID = "cv_session_records_public_" + "".join(choice(ascii_lowercase) for _ in range(16))
_CONV_SHARE_CODE = "CV-" + "".join(choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(8))


@pytest_asyncio.fixture(autouse=True)
async def seed_data():
    """Seed test tenant, user, visitor, channel, conversation and messages."""
    global _SEEDED, _TOKEN, _CONV_ID
    if _SEEDED:
        return
    async with AsyncSessionLocal() as db:
        await db.execute(text("""
            INSERT INTO tenants (tenant_id, name, is_active)
            VALUES ('test-corp', 'Test Corp', true)
            ON CONFLICT (tenant_id) DO NOTHING
        """))
        await db.commit()

        result = await db.execute(text("SELECT id FROM tenants WHERE tenant_id = 'test-corp'"))
        tenant_pk = result.scalar_one()

        hashed = hash_password("Test1234")
        await db.execute(text("""
            INSERT INTO employees (tenant_id, username, email, password_hash, display_name, roles, is_active)
            VALUES (:tid, 'rec_agent', 'rec_agent@example.com', :pw, 'Record Agent', '["admin"]'::jsonb, true)
            ON CONFLICT ON CONSTRAINT uq_employees_tenant_username DO NOTHING
        """), {"tid": tenant_pk, "pw": hashed})
        await db.commit()

        agent_row = await db.execute(text(
            "SELECT id FROM employees WHERE username = 'rec_agent' AND tenant_id = :tid"
        ), {"tid": tenant_pk})
        agent_id = agent_row.scalar_one()

        _TOKEN = create_access_token(
            {"sub": str(agent_id), "tenant_id": tenant_pk, "roles": ["admin"]}
        )

        await db.execute(text("""
            INSERT INTO users (tenant_id, external_id, name)
            VALUES (:tid, 'v_rec_test', 'Record Visitor')
            ON CONFLICT ON CONSTRAINT uq_users_tenant_external DO NOTHING
        """), {"tid": tenant_pk})
        await db.commit()

        v_row = await db.execute(text(
            "SELECT id FROM users WHERE external_id = 'v_rec_test' AND tenant_id = :tid"
        ), {"tid": tenant_pk})
        visitor_id = v_row.scalar_one()

        await db.execute(text("""
            INSERT INTO conversations (public_id, share_code, tenant_id, visitor_id, agent_id, status, started_at, ended_at, ended_by)
            VALUES (:public_id, :share_code, :tid, :vid, :aid, 'closed', NOW() - interval '1 hour', NOW(), 'agent')
            RETURNING id
        """), {"public_id": _CONV_PUBLIC_ID, "share_code": _CONV_SHARE_CODE, "tid": tenant_pk, "vid": visitor_id, "aid": agent_id})
        await db.commit()

        conv_row = await db.execute(text("""
            SELECT id FROM conversations
            WHERE tenant_id = :tid AND visitor_id = :vid
            ORDER BY id DESC LIMIT 1
        """), {"tid": tenant_pk, "vid": visitor_id})
        _CONV_ID = conv_row.scalar_one()

        await db.execute(text("""
            INSERT INTO messages (tenant_id, conversation_id, sender_type, content_type, content)
            VALUES
                (:tid, :cid, 'system', 'system', 'Session started'),
                (:tid, :cid, 'visitor', 'text', 'Hello'),
                (:tid, :cid, 'agent', 'text', 'Hi, how can I help?'),
                (:tid, :cid, 'system', 'system', 'Session ended')
        """), {"tid": tenant_pk, "cid": _CONV_ID})
        await db.commit()

    _SEEDED = True


class TestSessionRecordsAPI:

    @pytest.mark.asyncio
    async def test_list_returns_200_with_pagination(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/session-records",
            headers={"Authorization": f"Bearer {_TOKEN}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "per_page" in data
        assert "pages" in data
        assert isinstance(data["items"], list)

    @pytest.mark.asyncio
    async def test_list_with_keyword_filter(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/session-records",
            params={"keyword": "Record Visitor"},
            headers={"Authorization": f"Bearer {_TOKEN}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1

    @pytest.mark.asyncio
    async def test_list_with_public_id_keyword_filter(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/session-records",
            params={"keyword": _CONV_PUBLIC_ID},
            headers={"Authorization": f"Bearer {_TOKEN}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1

    @pytest.mark.asyncio
    async def test_list_with_share_code_keyword_filter(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/session-records",
            params={"keyword": _CONV_SHARE_CODE},
            headers={"Authorization": f"Bearer {_TOKEN}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        assert any(item["share_code"] == _CONV_SHARE_CODE for item in data["items"])

    @pytest.mark.asyncio
    async def test_list_with_internal_id_keyword_does_not_match(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/session-records",
            params={"keyword": str(_CONV_ID)},
            headers={"Authorization": f"Bearer {_TOKEN}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []

    @pytest.mark.asyncio
    async def test_list_with_nonexistent_keyword_returns_empty(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/session-records",
            params={"keyword": "NONEXISTENT_VISITOR_9999"},
            headers={"Authorization": f"Bearer {_TOKEN}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []

    @pytest.mark.asyncio
    async def test_get_detail_returns_200(self, client: AsyncClient):
        resp = await client.get(
            f"/api/v1/session-records/{_CONV_ID}",
            headers={"Authorization": f"Bearer {_TOKEN}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == _CONV_ID
        assert data["share_code"] == _CONV_SHARE_CODE
        assert data["status"] == "closed"

    @pytest.mark.asyncio
    async def test_get_detail_not_found_returns_404(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/session-records/999999",
            headers={"Authorization": f"Bearer {_TOKEN}"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_messages_returns_200(self, client: AsyncClient):
        resp = await client.get(
            f"/api/v1/session-records/{_CONV_ID}/messages",
            headers={"Authorization": f"Bearer {_TOKEN}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "has_more" in data
        assert len(data["items"]) >= 1

    @pytest.mark.asyncio
    async def test_get_messages_not_found_returns_404(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/session-records/999999/messages",
            headers={"Authorization": f"Bearer {_TOKEN}"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_list_requires_auth(self, client: AsyncClient):
        resp = await client.get("/api/v1/session-records")
        assert resp.status_code == 422 or resp.status_code == 401
