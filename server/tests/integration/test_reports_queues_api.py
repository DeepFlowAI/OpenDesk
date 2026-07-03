"""Integration tests for queue-dimension session reports."""
from __future__ import annotations

from datetime import date
from io import BytesIO
import json
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
        await db.execute(text("DELETE FROM satisfaction_survey_configs WHERE tenant_id = :tid"), {"tid": _TENANT_PK})
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

        service_settings = {
            "enabled": True,
            "section_title": "服务满意度",
            "popup_title": "请评价本次服务",
            "rating_mode": "stars",
            "show_resolution": True,
            "rating_options": [
                {"key": "service-good", "enabled": True, "name": "满意", "score": 10},
                {"key": "service-bad", "enabled": True, "name": "不满意", "score": 2},
            ],
        }
        product_settings = {
            "enabled": True,
            "section_title": "产品满意度",
            "popup_title": "请评价本次产品体验",
            "rating_mode": "stars",
            "rating_options": [
                {"key": "product-good", "enabled": True, "name": "好用", "score": 10},
            ],
        }
        snapshot = {
            "name": "队列满意度",
            "enabled": True,
            "triggers": {"agent_invite": True, "user_initiated": True, "session_end_invite": True},
            "service": service_settings,
            "product": product_settings,
        }
        cfg = await db.execute(text("""
            INSERT INTO satisfaction_survey_configs
              (tenant_id, name, enabled, current_version, triggers, service_settings, product_settings)
            VALUES
              (:tid, '队列满意度', true, 2, CAST(:triggers AS jsonb), CAST(:service AS jsonb), CAST(:product AS jsonb))
            RETURNING id
        """), {
            "tid": _TENANT_PK,
            "triggers": json.dumps(snapshot["triggers"]),
            "service": json.dumps(service_settings),
            "product": json.dumps(product_settings),
        })
        config_id = cfg.scalar_one()
        await db.execute(text("""
            INSERT INTO satisfaction_survey_config_versions
              (tenant_id, config_id, version, snapshot, published_at)
            VALUES
              (:tid, :config_id, 2, CAST(:snapshot AS jsonb),
               ((:anchor)::date + TIME '09:00')::timestamp AT TIME ZONE 'Asia/Shanghai')
        """), {
            "tid": _TENANT_PK,
            "config_id": config_id,
            "snapshot": json.dumps(snapshot),
            "anchor": date.fromisoformat(_ANCHOR_DATE_STR),
        })

        service_good = {
            "type": "service",
            "rating_mode": "stars",
            "option_key": "service-good",
            "option_name": "满意",
            "labels": [],
            "remark": "",
            "resolved": True,
            "submitted_at": f"{_ANCHOR_DATE_STR}T10:25:00+08:00",
        }
        product_good = {
            "type": "product",
            "rating_mode": "stars",
            "option_key": "product-good",
            "option_name": "好用",
            "labels": [],
            "remark": "",
            "submitted_at": f"{_ANCHOR_DATE_STR}T10:25:00+08:00",
        }
        await db.execute(text("""
            INSERT INTO satisfaction_survey_records
              (tenant_id, conversation_id, visitor_id, config_version, config_snapshot,
               invitation_source, invited_at, status, survey_types,
               service_result, product_result, submitted_at)
            VALUES
              (:tid, :c1, :vid, 2, CAST(:snapshot AS jsonb),
               'agent', ((:anchor)::date + TIME '10:20')::timestamp AT TIME ZONE 'Asia/Shanghai',
               'submitted', '["service","product"]'::jsonb,
               CAST(:service_good AS jsonb), CAST(:product_good AS jsonb),
               ((:anchor)::date + TIME '10:25')::timestamp AT TIME ZONE 'Asia/Shanghai'),
              (:tid, :c2, :vid, 2, CAST(:snapshot AS jsonb),
               'agent', ((:anchor)::date + TIME '11:20')::timestamp AT TIME ZONE 'Asia/Shanghai',
               'submitted', '["service"]'::jsonb,
               CAST(:service_good AS jsonb), NULL,
               ((:anchor)::date + TIME '11:25')::timestamp AT TIME ZONE 'Asia/Shanghai')
        """), {
            "tid": _TENANT_PK,
            "vid": visitor_id,
            "c1": c1,
            "c2": c2,
            "snapshot": json.dumps(snapshot),
            "service_good": json.dumps(service_good),
            "product_good": json.dumps(product_good),
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


def _distributions_by_key(distributions: list[dict]) -> dict[str, dict]:
    return {item["key"]: item for item in distributions}


def _slice_values(distribution: dict) -> dict[str, int]:
    return {item["key"]: item["value"] for item in distribution["slices"]}


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
        assert data["total"] == 1
        assert all(item["queue"]["queue_type"] == "employee_group" for item in data["items"])

        group = next(item for item in data["items"] if item["queue"]["queue_type"] == "employee_group")
        assert group["queue"]["name"] == "Support Group"
        assert group["metrics"]["queued_session_count"] == 2
        assert group["metrics"]["assigned_queue_session_count"] == 1
        assert group["metrics"]["unassigned_queue_session_count"] == 1
        assert group["metrics"]["queue_assign_rate"] == pytest.approx(0.5)
        assert group["metrics"]["avg_queue_duration_seconds"] == pytest.approx(90.0)
        assert group["metrics"]["final_session_count"] == 1

    @pytest.mark.asyncio
    async def test_list_queues_rejects_personal_queue_filter(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/reports/sessions/queues",
            params={"start": _ANCHOR_DATE_STR, "end": _ANCHOR_DATE_STR, "queue_type": "employee"},
            headers=_auth(),
        )
        assert resp.status_code == 400
        assert "Unsupported queue type" in resp.text

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
        assert data["metrics"]["satisfaction_invitation_count"] == 1
        assert data["metrics"]["satisfaction_submission_count"] == 1
        assert data["metrics"]["satisfaction_participation_rate"] == pytest.approx(1)
        assert data["metrics"]["satisfaction_submission_rate"] == pytest.approx(1)
        assert data["metrics"]["product_satisfaction_count"] == 1
        distributions = _distributions_by_key(data["distributions"])
        assert set(distributions) == {
            "satisfaction_resolution",
            "service_satisfaction_rating",
            "product_satisfaction_rating",
        }
        assert _slice_values(distributions["satisfaction_resolution"]) == {
            "resolved": 1,
            "unresolved": 0,
        }
        assert _slice_values(distributions["service_satisfaction_rating"]) == {
            "service-good": 1,
            "service-bad": 0,
        }
        assert _slice_values(distributions["product_satisfaction_rating"]) == {
            "product-good": 1,
        }

    @pytest.mark.asyncio
    async def test_personal_queue_detail_is_not_available(self, client: AsyncClient):
        resp = await client.get(
            f"/api/v1/reports/sessions/queues/employee/{_AGENT_B_ID}",
            params={"start": _ANCHOR_DATE_STR, "end": _ANCHOR_DATE_STR},
            headers=_auth(),
        )
        assert resp.status_code == 400
        assert "Unsupported queue type" in resp.text

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
    async def test_queue_trend_returns_satisfaction_group(self, client: AsyncClient):
        resp = await client.get(
            f"/api/v1/reports/sessions/queues/employee_group/{_GROUP_ID}/trend",
            params={"start": _ANCHOR_DATE_STR, "end": _ANCHOR_DATE_STR, "trend": "hour", "group": "satisfaction"},
            headers=_auth(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["group"] == "satisfaction"
        assert [metric["key"] for metric in data["metrics"]] == [
            "satisfaction_invitation_count",
            "satisfaction_submission_count",
            "product_satisfaction_count",
            "satisfaction_resolution:resolved",
            "satisfaction_resolution:unresolved",
            "service_satisfaction_rating:service-good",
            "service_satisfaction_rating:service-bad",
            "product_satisfaction_rating:product-good",
        ]
        hour_10 = next(bucket for bucket in data["buckets"] if bucket["label"] == "10")
        hour_11 = next(bucket for bucket in data["buckets"] if bucket["label"] == "11")
        values_10 = {metric["key"]: metric["value"] for metric in hour_10["metrics"]}
        values_11 = {metric["key"]: metric["value"] for metric in hour_11["metrics"]}
        assert values_10["satisfaction_invitation_count"] == 1
        assert values_10["satisfaction_submission_count"] == 1
        assert values_10["product_satisfaction_count"] == 1
        assert values_10["satisfaction_resolution:resolved"] == 1
        assert values_10["satisfaction_resolution:unresolved"] == 0
        assert values_10["service_satisfaction_rating:service-good"] == 1
        assert values_10["service_satisfaction_rating:service-bad"] == 0
        assert values_10["product_satisfaction_rating:product-good"] == 1
        assert values_11["satisfaction_invitation_count"] == 0
        assert values_11["satisfaction_submission_count"] == 0
        assert values_11["product_satisfaction_count"] == 0
        assert values_11["satisfaction_resolution:resolved"] == 0
        assert values_11["satisfaction_resolution:unresolved"] == 0
        assert values_11["service_satisfaction_rating:service-good"] == 0
        assert values_11["service_satisfaction_rating:service-bad"] == 0
        assert values_11["product_satisfaction_rating:product-good"] == 0

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
        assert "Queue Beta" not in sheet

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
                "group": "satisfaction",
            },
            headers=_auth(),
        )
        assert resp.status_code == 200
        assert "排队接入" in _worksheet_text(resp.content, 1)
        trend_sheet = _worksheet_text(resp.content, 2)
        assert "趋势明细" in trend_sheet
        assert "解决情况" in trend_sheet
        assert "服务满意度" in trend_sheet

    @pytest.mark.asyncio
    async def test_queue_reports_require_auth(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/reports/sessions/queues",
            params={"start": _ANCHOR_DATE_STR, "end": _ANCHOR_DATE_STR},
        )
        assert resp.status_code == 401
