"""Integration tests for /api/v1/reports/online-monitor (SR3)."""
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text

import app.extensions  # triggers private overlay
from app.core.security import create_access_token, hash_password
from app.db.session import AsyncSessionLocal, engine
from app.enums import AgentOnlineStatus
from app.main import _fastapi_app

TZ = ZoneInfo("Asia/Shanghai")
_TENANT_SLUG = "test-reports-mon-corp"

_SEEDED = False
_TOKEN = ""
_TENANT_PK = 0
_AGENT_A_ID = 0
_AGENT_B_ID = 0


@pytest_asyncio.fixture(autouse=True)
async def seed():
    global _SEEDED, _TOKEN, _TENANT_PK, _AGENT_A_ID, _AGENT_B_ID

    if not any(r.path.startswith("/api/v1/reports/online-monitor") for r in _fastapi_app.routes):
        from app.extensions.reports import register as _reg
        _reg(_fastapi_app)

    if _SEEDED:
        yield
        await engine.dispose()
        return

    async with AsyncSessionLocal() as db:
        await db.execute(text("""
            INSERT INTO tenants (tenant_id, name, is_active)
            VALUES (:slug, 'Online Monitor Test Corp', true)
            ON CONFLICT (tenant_id) DO NOTHING
        """), {"slug": _TENANT_SLUG})
        await db.commit()
        t = await db.execute(text("SELECT id FROM tenants WHERE tenant_id = :slug"), {"slug": _TENANT_SLUG})
        _TENANT_PK = t.scalar_one()

        await db.execute(text("DELETE FROM conversations WHERE tenant_id = :tid"), {"tid": _TENANT_PK})
        await db.execute(text("DELETE FROM employees WHERE tenant_id = :tid"), {"tid": _TENANT_PK})
        await db.commit()

        pw = hash_password("Test1234")
        await db.execute(text("""
            INSERT INTO employees (tenant_id, username, email, password_hash, display_name, name, roles, is_active, max_concurrent)
            VALUES
              (:tid, 'mon_agent_a', 'a@mon.test', :pw, 'Mon Agent A', 'Mon Agent A', '["agent","admin"]'::jsonb, true, 5),
              (:tid, 'mon_agent_b', 'b@mon.test', :pw, 'Mon Agent B', 'Mon Agent B', '["agent"]'::jsonb, true, 3),
              (:tid, 'mon_agent_c', 'c@mon.test', :pw, 'Mon Agent C (inactive)', 'Mon Agent C', '["agent"]'::jsonb, false, 5)
        """), {"tid": _TENANT_PK, "pw": pw})
        await db.commit()
        a = await db.execute(text("SELECT id FROM employees WHERE username='mon_agent_a' AND tenant_id=:tid"), {"tid": _TENANT_PK})
        _AGENT_A_ID = a.scalar_one()
        b = await db.execute(text("SELECT id FROM employees WHERE username='mon_agent_b' AND tenant_id=:tid"), {"tid": _TENANT_PK})
        _AGENT_B_ID = b.scalar_one()

        # One session today for agent A
        await db.execute(text("""
            INSERT INTO users (tenant_id, external_id, name)
            VALUES (:tid, 'mon_v', 'Mon Visitor')
            ON CONFLICT ON CONSTRAINT uq_users_tenant_external DO NOTHING
        """), {"tid": _TENANT_PK})
        await db.commit()
        v = await db.execute(text("SELECT id FROM users WHERE external_id='mon_v' AND tenant_id=:tid"), {"tid": _TENANT_PK})
        visitor_id = v.scalar_one()

        today_str = date.today().isoformat()
        await db.execute(text("""
            INSERT INTO conversations (public_id, share_code, tenant_id, visitor_id, agent_id, status, started_at, ended_at, ended_by)
            VALUES
              ('cv_mon_' || substr(md5(random()::text || clock_timestamp()::text), 1, 24), 'CV-' || upper(substr(md5(random()::text || clock_timestamp()::text), 1, 8)), :tid, :vid, :a, 'closed',
               ((:today)::date + TIME '08:00')::timestamp AT TIME ZONE 'Asia/Shanghai',
               ((:today)::date + TIME '08:10')::timestamp AT TIME ZONE 'Asia/Shanghai', 'agent')
        """), {"tid": _TENANT_PK, "vid": visitor_id, "a": _AGENT_A_ID, "today": date.fromisoformat(today_str)})
        await db.commit()

        _TOKEN = create_access_token(
            {"sub": str(_AGENT_A_ID), "tenant_id": _TENANT_PK, "roles": ["admin"]}
        )

    _SEEDED = True
    yield
    await engine.dispose()


def _auth():
    return {"Authorization": f"Bearer {_TOKEN}"}


class TestOnlineMonitorAPI:

    @pytest.mark.asyncio
    async def test_returns_200_with_today_and_employees(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/reports/online-monitor",
            headers=_auth(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "today" in data
        assert "employees" in data
        assert "as_of" in data
        assert data["today"]["session_count"] >= 1

    @pytest.mark.asyncio
    async def test_inactive_employees_not_listed(self, client: AsyncClient):
        resp = await client.get("/api/v1/reports/online-monitor", headers=_auth())
        emps = resp.json()["employees"]
        names = [e["employee"]["name"] for e in emps]
        assert "Mon Agent A" in names
        assert "Mon Agent B" in names
        # Inactive Mon Agent C must NOT appear (SR3 §1.2 excludes inactive)
        assert "Mon Agent C" not in names

    @pytest.mark.asyncio
    async def test_employee_row_carries_status_and_max_concurrent(self, client: AsyncClient):
        resp = await client.get("/api/v1/reports/online-monitor", headers=_auth())
        a_row = next(e for e in resp.json()["employees"] if e["employee"]["name"] == "Mon Agent A")
        assert a_row["max_concurrent"] == 5
        # Status comes from Redis — with fakeredis empty, status is offline
        assert a_row["status"] in {"online", "busy", "offline", "unknown"}
        assert "current_count" in a_row
        assert "session_count" in a_row
        assert "avg_duration_seconds" in a_row

    @pytest.mark.asyncio
    async def test_unauth_returns_401(self, client: AsyncClient):
        resp = await client.get("/api/v1/reports/online-monitor")
        assert resp.status_code == 401
