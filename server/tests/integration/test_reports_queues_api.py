"""Integration tests for queue-dimension session reports."""
from __future__ import annotations

from datetime import date
from io import BytesIO
import zipfile

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text

import app.extensions  # triggers private overlay
from app.core.security import create_access_token, hash_password
from app.db.session import AsyncSessionLocal, engine
from app.main import _fastapi_app

_ANCHOR_DATE_STR = "2026-05-13"
_TENANT_SLUG = "test-reports-queues-corp"

_SEEDED = False
_TOKEN = ""
_TENANT_PK = 0
_GROUP_ID = 0
_AGENT_A_ID = 0
_AGENT_B_ID = 0


@pytest_asyncio.fixture(autouse=True)
async def seed_queue_report_data():
    global _SEEDED, _TOKEN, _TENANT_PK, _GROUP_ID, _AGENT_A_ID, _AGENT_B_ID

    if not any(r.path == "/api/v1/reports/sessions/queues" for r in _fastapi_app.routes):
        from app.extensions.reports import register as _reg
        _reg(_fastapi_app)

    if _SEEDED:
        yield
        await engine.dispose()
        return

    async with AsyncSessionLocal() as db:
        await db.execute(text("""
            INSERT INTO tenants (tenant_id, name, is_active)
            VALUES (:slug, 'Reports Queues Test Corp', true)
            ON CONFLICT (tenant_id) DO NOTHING
        """), {"slug": _TENANT_SLUG})
        await db.commit()
        tenant = await db.execute(
            text("SELECT id FROM tenants WHERE tenant_id = :slug"),
            {"slug": _TENANT_SLUG},
        )
        _TENANT_PK = tenant.scalar_one()

        await db.execute(text("DELETE FROM conversations WHERE tenant_id = :tid"), {"tid": _TENANT_PK})
        await db.execute(text("DELETE FROM employee_groups WHERE tenant_id = :tid"), {"tid": _TENANT_PK})
        await db.execute(text("DELETE FROM employees WHERE tenant_id = :tid"), {"tid": _TENANT_PK})
        await db.commit()

        password_hash = hash_password("Test1234")
        await db.execute(text("""
            INSERT INTO employees (tenant_id, username, email, password_hash, display_name, name, roles, is_active)
            VALUES
              (:tid, 'queue_alpha', 'queue-alpha@reports.test', :pw, 'Queue Alpha', 'Queue Alpha', '["admin"]'::jsonb, true),
              (:tid, 'queue_beta', 'queue-beta@reports.test', :pw, 'Queue Beta', 'Queue Beta', '["agent"]'::jsonb, false)
        """), {"tid": _TENANT_PK, "pw": password_hash})
        await db.commit()
        alpha = await db.execute(
            text("SELECT id FROM employees WHERE username='queue_alpha' AND tenant_id=:tid"),
            {"tid": _TENANT_PK},
        )
        _AGENT_A_ID = alpha.scalar_one()
        beta = await db.execute(
            text("SELECT id FROM employees WHERE username='queue_beta' AND tenant_id=:tid"),
            {"tid": _TENANT_PK},
        )
        _AGENT_B_ID = beta.scalar_one()

        group = await db.execute(text("""
            INSERT INTO employee_groups (tenant_id, name, description)
            VALUES (:tid, 'Support Group', 'Queue report test group')
            RETURNING id
        """), {"tid": _TENANT_PK})
        _GROUP_ID = group.scalar_one()
        await db.execute(text("""
            INSERT INTO employee_group_members (group_id, employee_id)
            VALUES (:gid, :alpha), (:gid, :beta)
            ON CONFLICT ON CONSTRAINT uq_group_members_group_employee DO NOTHING
        """), {"gid": _GROUP_ID, "alpha": _AGENT_A_ID, "beta": _AGENT_B_ID})
        await db.commit()

        await db.execute(text("""
            INSERT INTO users (tenant_id, public_id, external_id, name)
            VALUES (:tid, 'queue_report_visitor', 'queue_report_visitor', 'Queue Visitor')
            ON CONFLICT ON CONSTRAINT uq_users_tenant_external DO NOTHING
        """), {"tid": _TENANT_PK})
        await db.commit()
        visitor = await db.execute(
            text("SELECT id FROM users WHERE external_id='queue_report_visitor' AND tenant_id=:tid"),
            {"tid": _TENANT_PK},
        )
        visitor_id = visitor.scalar_one()

        rows = await db.execute(text("""
            INSERT INTO conversations (
                public_id, share_code, tenant_id, visitor_id, agent_id, group_id, status,
                started_at, ended_at, ended_by,
                last_assigned_queue_type, last_assigned_queue_id, last_assigned_queue_name,
                visitor_message_count, agent_message_count,
                first_human_response_seconds, agent_response_count, agent_avg_response_seconds,
                duration_seconds
            )
            VALUES
              ('cv_qr_' || substr(md5(random()::text || clock_timestamp()::text), 1, 24),
               'QR-' || upper(substr(md5(random()::text || clock_timestamp()::text), 1, 8)),
               :tid, :vid, :alpha, :gid, 'closed',
               ((:anchor)::date + TIME '10:05')::timestamp AT TIME ZONE 'Asia/Shanghai',
               ((:anchor)::date + TIME '10:15')::timestamp AT TIME ZONE 'Asia/Shanghai',
               'agent', 'employee_group', :gid, 'Support Group',
               2, 1, 30, 2, 20, 600),
              ('cv_qr_' || substr(md5(random()::text || clock_timestamp()::text), 1, 24),
               'QR-' || upper(substr(md5(random()::text || clock_timestamp()::text), 1, 8)),
               :tid, :vid, :beta, :gid, 'closed',
               ((:anchor)::date + TIME '11:05')::timestamp AT TIME ZONE 'Asia/Shanghai',
               ((:anchor)::date + TIME '11:13')::timestamp AT TIME ZONE 'Asia/Shanghai',
               'agent', 'employee', :beta, 'Queue Beta',
               3, 0, NULL, NULL, NULL, 480),
              ('cv_qr_' || substr(md5(random()::text || clock_timestamp()::text), 1, 24),
               'QR-' || upper(substr(md5(random()::text || clock_timestamp()::text), 1, 8)),
               :tid, :vid, :beta, :gid, 'closed',
               ((:anchor)::date + TIME '12:05')::timestamp AT TIME ZONE 'Asia/Shanghai',
               ((:anchor)::date + TIME '12:10')::timestamp AT TIME ZONE 'Asia/Shanghai',
               'agent', 'employee', :beta, 'Queue Beta',
               0, 0, NULL, NULL, NULL, 300)
            RETURNING id
        """), {
            "tid": _TENANT_PK,
            "vid": visitor_id,
            "alpha": _AGENT_A_ID,
            "beta": _AGENT_B_ID,
            "gid": _GROUP_ID,
            "anchor": date.fromisoformat(_ANCHOR_DATE_STR),
        })
        c1, c2, c3 = [row.id for row in rows.all()]

        await db.execute(text("""
            INSERT INTO conversation_queue_summaries (
                tenant_id, conversation_id, queue_type, queue_id, queue_name_snapshot,
                wait_duration_seconds, is_last_assigned, queue_result, conversation_started_at
            )
            VALUES
              (:tid, :c1, 'employee_group', :gid, 'Support Group', 60, true, 'assigned',
               ((:anchor)::date + TIME '10:05')::timestamp AT TIME ZONE 'Asia/Shanghai'),
              (:tid, :c2, 'employee_group', :gid, 'Support Group', 120, false, 'canceled',
               ((:anchor)::date + TIME '11:05')::timestamp AT TIME ZONE 'Asia/Shanghai'),
              (:tid, :c3, 'employee', :beta, 'Queue Beta', 45, true, 'assigned',
               ((:anchor)::date + TIME '12:05')::timestamp AT TIME ZONE 'Asia/Shanghai')
        """), {
            "tid": _TENANT_PK,
            "c1": c1,
            "c2": c2,
            "c3": c3,
            "gid": _GROUP_ID,
            "beta": _AGENT_B_ID,
            "anchor": date.fromisoformat(_ANCHOR_DATE_STR),
        })
        await db.commit()

        _TOKEN = create_access_token(
            {"sub": str(_AGENT_A_ID), "tenant_id": _TENANT_PK, "roles": ["admin"]}
        )

    _SEEDED = True
    yield
    await engine.dispose()


def _auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {_TOKEN}"}


def _worksheet_text(content: bytes, sheet: int) -> str:
    with zipfile.ZipFile(BytesIO(content)) as archive:
        return archive.read(f"xl/worksheets/sheet{sheet}.xml").decode("utf-8")


class TestQueueReportsAPI:
    @pytest.mark.asyncio
    async def test_list_queues_returns_current_and_metric_rows(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/reports/sessions/queues",
            params={"start": _ANCHOR_DATE_STR, "end": _ANCHOR_DATE_STR},
            headers=_auth(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3

        group = next(item for item in data["items"] if item["queue"]["queue_type"] == "employee_group")
        assert group["queue"]["name"] == "Support Group"
        assert group["metrics"]["queued_session_count"] == 2
        assert group["metrics"]["assigned_queue_session_count"] == 1
        assert group["metrics"]["unassigned_queue_session_count"] == 1
        assert group["metrics"]["queue_assign_rate"] == pytest.approx(0.5)
        assert group["metrics"]["avg_queue_duration_seconds"] == pytest.approx(90.0)
        assert group["metrics"]["final_session_count"] == 1

    @pytest.mark.asyncio
    async def test_queue_detail_returns_overview_metrics(self, client: AsyncClient):
        resp = await client.get(
            f"/api/v1/reports/sessions/queues/employee_group/{_GROUP_ID}",
            params={"start": _ANCHOR_DATE_STR, "end": _ANCHOR_DATE_STR},
            headers=_auth(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["queue"]["name"] == "Support Group"
        assert data["metrics"]["queued_session_count"] == 2
        assert data["metrics"]["max_queue_duration_seconds"] == 120
        assert data["metrics"]["effective_session_count"] == 1
        assert data["metrics"]["avg_first_human_response_seconds"] == 30
        assert data["metrics"]["avg_agent_response_seconds"] == 20

    @pytest.mark.asyncio
    async def test_queue_trend_groups_by_conversation_start_hour(self, client: AsyncClient):
        resp = await client.get(
            f"/api/v1/reports/sessions/queues/employee_group/{_GROUP_ID}/trend",
            params={"start": _ANCHOR_DATE_STR, "end": _ANCHOR_DATE_STR, "trend": "hour", "group": "queue_access"},
            headers=_auth(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["group"] == "queue_access"
        assert len(data["buckets"]) == 24
        hour_10 = next(bucket for bucket in data["buckets"] if bucket["label"] == "10")
        hour_11 = next(bucket for bucket in data["buckets"] if bucket["label"] == "11")
        values_10 = {metric["key"]: metric["value"] for metric in hour_10["metrics"]}
        values_11 = {metric["key"]: metric["value"] for metric in hour_11["metrics"]}
        assert values_10["queued_session_count"] == 1
        assert values_10["assigned_queue_session_count"] == 1
        assert values_11["queued_session_count"] == 1
        assert values_11["unassigned_queue_session_count"] == 1

    @pytest.mark.asyncio
    async def test_queue_list_export_returns_xlsx(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/reports/sessions/queues/export",
            params={"scope": "list", "start": _ANCHOR_DATE_STR, "end": _ANCHOR_DATE_STR},
            headers=_auth(),
        )
        assert resp.status_code == 200
        assert resp.content.startswith(b"PK")
        sheet = _worksheet_text(resp.content, 1)
        assert "队列指标列表" in sheet
        assert "Support Group" in sheet

    @pytest.mark.asyncio
    async def test_queue_detail_export_returns_xlsx(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/reports/sessions/queues/export",
            params={
                "scope": "detail",
                "start": _ANCHOR_DATE_STR,
                "end": _ANCHOR_DATE_STR,
                "queue_type": "employee_group",
                "queue_id": _GROUP_ID,
                "trend": "hour",
                "group": "queue_access",
            },
            headers=_auth(),
        )
        assert resp.status_code == 200
        assert "排队接入" in _worksheet_text(resp.content, 1)
        assert "趋势明细" in _worksheet_text(resp.content, 2)

    @pytest.mark.asyncio
    async def test_queue_reports_require_auth(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/reports/sessions/queues",
            params={"start": _ANCHOR_DATE_STR, "end": _ANCHOR_DATE_STR},
        )
        assert resp.status_code == 401
