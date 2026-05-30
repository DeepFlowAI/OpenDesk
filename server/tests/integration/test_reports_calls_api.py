"""Integration tests for /api/v1/reports/calls/*."""
from datetime import date

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text

import app.extensions  # noqa: F401 - triggers private overlay
from app.core.security import create_access_token, hash_password
from app.db.session import AsyncSessionLocal, engine
from app.main import _fastapi_app

_ANCHOR_DATE_STR = "2026-05-10"
_TENANT_SLUG = "test-call-reports-corp"

_SEEDED = False
_TOKEN = ""
_AGENT_TOKEN = ""
_TENANT_PK = 0
_ADMIN_ID = 0


@pytest_asyncio.fixture(autouse=True)
async def seed_call_reports_data():
    global _SEEDED, _TOKEN, _AGENT_TOKEN, _TENANT_PK, _ADMIN_ID

    if not any(r.path.startswith("/api/v1/reports/calls") for r in _fastapi_app.routes):
        from app.extensions.reports import register as _reg

        _reg(_fastapi_app)

    if _SEEDED:
        yield
        await engine.dispose()
        return

    async with AsyncSessionLocal() as db:
        await db.execute(
            text(
                """
                INSERT INTO tenants (tenant_id, name, is_active)
                VALUES (:slug, 'Call Reports Test Corp', true)
                ON CONFLICT (tenant_id) DO NOTHING
                """
            ),
            {"slug": _TENANT_SLUG},
        )
        await db.commit()
        tenant_row = await db.execute(
            text("SELECT id FROM tenants WHERE tenant_id = :slug"),
            {"slug": _TENANT_SLUG},
        )
        _TENANT_PK = tenant_row.scalar_one()

        await db.execute(text("DELETE FROM call_records WHERE tenant_id = :tid"), {"tid": _TENANT_PK})
        await db.commit()

        await db.execute(
            text(
                """
                INSERT INTO employees (tenant_id, username, email, password_hash, display_name, name, roles, is_active)
                VALUES
                  (:tid, 'call_report_admin', 'call-report-admin@test.local', :pw, 'Call Admin', 'Call Admin', '["admin"]'::jsonb, true),
                  (:tid, 'call_report_agent', 'call-report-agent@test.local', :pw, 'Call Agent', 'Call Agent', '["agent"]'::jsonb, true)
                ON CONFLICT ON CONSTRAINT uq_employees_tenant_username DO NOTHING
                """
            ),
            {"tid": _TENANT_PK, "pw": hash_password("Test1234")},
        )
        await db.commit()
        admin_row = await db.execute(
            text("SELECT id FROM employees WHERE username='call_report_admin' AND tenant_id=:tid"),
            {"tid": _TENANT_PK},
        )
        _ADMIN_ID = admin_row.scalar_one()
        agent_row = await db.execute(
            text("SELECT id FROM employees WHERE username='call_report_agent' AND tenant_id=:tid"),
            {"tid": _TENANT_PK},
        )
        agent_id = agent_row.scalar_one()

        await db.execute(
            text(
                """
                INSERT INTO call_records (
                    tenant_id, call_id, direction, state, from_number, to_number,
                    agent_id, started_at, answered_at, ended_at, talk_duration_ms, extra_metadata
                )
                VALUES
                  (:tid, 'call_report_in_answered', 'inbound', 'completed', '+1001', '+2001', :admin_id,
                   (:anchor)::date + TIME '10:00',
                   (:anchor)::date + TIME '10:02',
                   (:anchor)::date + TIME '10:05',
                   180000, '{}'::jsonb),
                  (:tid, 'call_report_in_missed', 'inbound', 'missed', '+1002', '+2001', NULL,
                   (:anchor)::date + TIME '10:30',
                   NULL,
                   (:anchor)::date + TIME '10:31',
                   NULL, '{}'::jsonb),
                  (:tid, 'call_report_out_answered', 'outbound', 'completed', '+2001', '+1003', :admin_id,
                   (:anchor)::date + TIME '15:00',
                   (:anchor)::date + TIME '15:01',
                   (:anchor)::date + TIME '15:06',
                   300000, '{}'::jsonb),
                  (:tid, 'call_report_out_failed', 'outbound', 'failed', '+2001', '+1004', :admin_id,
                   (:anchor)::date + TIME '15:30',
                   NULL,
                   (:anchor)::date + TIME '15:31',
                   NULL, '{}'::jsonb)
                """
            ),
            {
                "tid": _TENANT_PK,
                "admin_id": _ADMIN_ID,
                "anchor": date.fromisoformat(_ANCHOR_DATE_STR),
            },
        )
        await db.commit()

        _TOKEN = create_access_token(
            {"sub": str(_ADMIN_ID), "tenant_id": _TENANT_PK, "roles": ["admin"]}
        )
        _AGENT_TOKEN = create_access_token(
            {"sub": str(agent_id), "tenant_id": _TENANT_PK, "roles": ["agent"]}
        )

    _SEEDED = True
    yield
    await engine.dispose()


def _auth(token: str | None = None) -> dict[str, str]:
    return {"Authorization": f"Bearer {token or _TOKEN}"}


class TestCallReportsOverviewAPI:
    @pytest.mark.asyncio
    async def test_overview_returns_call_metrics(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/reports/calls/overview",
            params={"start": _ANCHOR_DATE_STR, "end": _ANCHOR_DATE_STR},
            headers=_auth(),
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_calls"] == 4
        assert data["inbound_calls"] == 2
        assert data["answered_inbound_calls"] == 1
        assert data["outbound_calls"] == 2
        assert data["answered_outbound_calls"] == 1
        assert data["avg_inbound_talk_seconds"] == 180
        assert data["avg_outbound_talk_seconds"] == 300
        assert "as_of" in data

    @pytest.mark.asyncio
    async def test_overview_agent_role_returns_403(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/reports/calls/overview",
            params={"start": _ANCHOR_DATE_STR, "end": _ANCHOR_DATE_STR},
            headers=_auth(_AGENT_TOKEN),
        )

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_overview_start_after_end_returns_400(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/reports/calls/overview",
            params={"start": "2026-05-20", "end": "2026-05-19"},
            headers=_auth(),
        )

        assert resp.status_code == 400


class TestCallReportsTrendAPI:
    @pytest.mark.asyncio
    async def test_trend_hour_returns_24_buckets(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/reports/calls/trend",
            params={"start": _ANCHOR_DATE_STR, "end": _ANCHOR_DATE_STR, "trend": "hour"},
            headers=_auth(),
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["trend"] == "hour"
        assert len(data["buckets"]) == 24
        assert sum(b["metrics"]["total_calls"] for b in data["buckets"]) == 4

    @pytest.mark.asyncio
    async def test_trend_invalid_type_returns_422(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/reports/calls/trend",
            params={"start": _ANCHOR_DATE_STR, "end": _ANCHOR_DATE_STR, "trend": "bad"},
            headers=_auth(),
        )

        assert resp.status_code == 422
