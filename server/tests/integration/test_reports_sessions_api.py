"""Integration tests for /api/v1/reports/sessions/* (SR1 overall + SR2 employee).

Reuses the same seeded tenant/conversations as test_reports_queries.py via its
own seed (we can't import that module's fixture without conflicts), but seeding
is idempotent.
"""
import json
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text

import app.extensions  # triggers private overlay
from app.core.security import create_access_token
from app.db.session import AsyncSessionLocal, engine
from app.main import _fastapi_app

TZ = ZoneInfo("Asia/Shanghai")
_ANCHOR_DATE_STR = "2026-05-10"
_TENANT_SLUG = "test-reports-corp"

_SEEDED = False
_TOKEN = ""
_TENANT_PK = 0
_AGENT_A_ID = 0


@pytest_asyncio.fixture(autouse=True)
async def seed():
    global _SEEDED, _TOKEN, _TENANT_PK, _AGENT_A_ID

    # Ensure the reports extension is in the route table (loaded by load_extensions
    # at app startup, but a defensive check helps when running this file alone).
    if not any(r.path.startswith("/api/v1/reports/sessions") for r in _fastapi_app.routes):
        from app.extensions.reports import register as _reg
        _reg(_fastapi_app)

    if _SEEDED:
        yield
        await engine.dispose()
        return

    async with AsyncSessionLocal() as db:
        await db.execute(text("""
            INSERT INTO tenants (tenant_id, name, is_active)
            VALUES (:slug, 'Reports Test Corp', true)
            ON CONFLICT (tenant_id) DO NOTHING
        """), {"slug": _TENANT_SLUG})
        await db.commit()
        t = await db.execute(text("SELECT id FROM tenants WHERE tenant_id = :slug"), {"slug": _TENANT_SLUG})
        _TENANT_PK = t.scalar_one()

        await db.execute(text("DELETE FROM conversations WHERE tenant_id = :tid"), {"tid": _TENANT_PK})
        await db.commit()

        from app.core.security import hash_password
        await db.execute(text("""
            INSERT INTO employees (tenant_id, username, email, password_hash, display_name, name, roles, is_active)
            VALUES
              (:tid, 'rep_agent_a', 'a@reports.test', :pw, 'Agent A', 'Agent A', '["admin"]'::jsonb, true)
            ON CONFLICT ON CONSTRAINT uq_employees_tenant_username DO NOTHING
        """), {"tid": _TENANT_PK, "pw": hash_password("Test1234")})
        await db.commit()
        a = await db.execute(text(
            "SELECT id FROM employees WHERE username='rep_agent_a' AND tenant_id=:tid"
        ), {"tid": _TENANT_PK})
        _AGENT_A_ID = a.scalar_one()

        role_id = (await db.execute(text("""
            INSERT INTO roles (
                tenant_id, key, name, description, is_system, is_active,
                permissions, data_scopes
            )
            VALUES (
                :tid, 'reports_sessions_access', 'Reports Sessions Access',
                'Reports Sessions Access', false, true,
                CAST(:permissions AS JSON), CAST(:data_scopes AS JSON)
            )
            ON CONFLICT ON CONSTRAINT uq_roles_tenant_key DO UPDATE SET
                permissions = EXCLUDED.permissions,
                data_scopes = EXCLUDED.data_scopes,
                is_active = true
            RETURNING id
        """), {
            "tid": _TENANT_PK,
            "permissions": json.dumps([
                "chat.workspace.use",
                "chat.session_record.view",
                "chat.session_report.view",
                "chat.session_report.export",
            ]),
            "data_scopes": json.dumps({"session_record": "all"}),
        })).scalar_one()
        await db.execute(text(
            "DELETE FROM employee_roles WHERE employee_id = :employee_id"
        ), {"employee_id": _AGENT_A_ID})
        await db.execute(text("""
            INSERT INTO employee_roles (employee_id, role_id)
            VALUES (:employee_id, :role_id)
            ON CONFLICT ON CONSTRAINT uq_employee_roles_employee_role DO NOTHING
        """), {"employee_id": _AGENT_A_ID, "role_id": role_id})
        await db.commit()

        await db.execute(text("""
            INSERT INTO users (tenant_id, public_id, external_id, name)
            VALUES (:tid, 'rep_visitor_api', 'rep_visitor_api', 'Rep Visitor API')
            ON CONFLICT ON CONSTRAINT uq_users_tenant_external DO NOTHING
        """), {"tid": _TENANT_PK})
        await db.commit()
        v = await db.execute(text(
            "SELECT id FROM users WHERE external_id='rep_visitor_api' AND tenant_id=:tid"
        ), {"tid": _TENANT_PK})
        visitor_id = v.scalar_one()

        await db.execute(text("""
            INSERT INTO conversations (public_id, share_code, tenant_id, visitor_id, agent_id, status, started_at, ended_at, ended_by)
            VALUES
              ('cv_rep_sess_' || substr(md5(random()::text || clock_timestamp()::text), 1, 24), 'CV-' || upper(substr(md5(random()::text || clock_timestamp()::text), 1, 8)), :tid, :vid, :a, 'closed',
               ((:anchor)::date + TIME '10:15')::timestamp AT TIME ZONE 'Asia/Shanghai',
               ((:anchor)::date + TIME '10:25')::timestamp AT TIME ZONE 'Asia/Shanghai', 'agent'),
              ('cv_rep_sess_' || substr(md5(random()::text || clock_timestamp()::text), 1, 24), 'CV-' || upper(substr(md5(random()::text || clock_timestamp()::text), 1, 8)), :tid, :vid, :a, 'closed',
               ((:anchor)::date + TIME '15:00')::timestamp AT TIME ZONE 'Asia/Shanghai',
               ((:anchor)::date + TIME '15:10')::timestamp AT TIME ZONE 'Asia/Shanghai', 'agent')
        """), {"tid": _TENANT_PK, "vid": visitor_id, "a": _AGENT_A_ID, "anchor": date.fromisoformat(_ANCHOR_DATE_STR)})
        await db.commit()

        _TOKEN = create_access_token(
            {"sub": str(_AGENT_A_ID), "tenant_id": _TENANT_PK, "roles": ["admin"]}
        )

    _SEEDED = True
    yield
    await engine.dispose()


def _auth():
    return {"Authorization": f"Bearer {_TOKEN}"}


class TestOverviewAPI:

    @pytest.mark.asyncio
    async def test_overview_returns_200(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/reports/sessions/overview",
            params={"start": _ANCHOR_DATE_STR, "end": _ANCHOR_DATE_STR},
            headers=_auth(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_count"] == 2
        assert "as_of" in data

    @pytest.mark.asyncio
    async def test_overview_with_employee_id(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/reports/sessions/overview",
            params={"start": _ANCHOR_DATE_STR, "end": _ANCHOR_DATE_STR, "employee_id": _AGENT_A_ID},
            headers=_auth(),
        )
        assert resp.status_code == 200
        assert resp.json()["session_count"] == 2

    @pytest.mark.asyncio
    async def test_overview_start_after_end_returns_400(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/reports/sessions/overview",
            params={"start": "2026-05-20", "end": "2026-05-19"},
            headers=_auth(),
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_overview_over_366_days_returns_400(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/reports/sessions/overview",
            params={"start": "2025-01-01", "end": "2026-05-19"},
            headers=_auth(),
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_overview_without_auth_returns_401(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/reports/sessions/overview",
            params={"start": _ANCHOR_DATE_STR, "end": _ANCHOR_DATE_STR},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_overview_bad_date_format_returns_400(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/reports/sessions/overview",
            params={"start": "2026/05/19", "end": _ANCHOR_DATE_STR},
            headers=_auth(),
        )
        assert resp.status_code == 400


class TestTrendAPI:

    @pytest.mark.asyncio
    async def test_trend_hour_returns_24_buckets(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/reports/sessions/trend",
            params={"start": _ANCHOR_DATE_STR, "end": _ANCHOR_DATE_STR, "trend": "hour"},
            headers=_auth(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["trend"] == "hour"
        assert len(data["buckets"]) == 24
        hour_10 = next(b for b in data["buckets"] if b["label"] == "10")
        assert hour_10["metrics"]["session_count"] == 1

    @pytest.mark.asyncio
    async def test_trend_default_is_hour(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/reports/sessions/trend",
            params={"start": _ANCHOR_DATE_STR, "end": _ANCHOR_DATE_STR},
            headers=_auth(),
        )
        assert resp.status_code == 200
        assert resp.json()["trend"] == "hour"

    @pytest.mark.asyncio
    async def test_trend_invalid_type_returns_422(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/reports/sessions/trend",
            params={"start": _ANCHOR_DATE_STR, "end": _ANCHOR_DATE_STR, "trend": "nope"},
            headers=_auth(),
        )
        assert resp.status_code == 422
