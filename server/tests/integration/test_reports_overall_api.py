"""Integration tests for the grouped overall session report framework.

Seeds conversations with explicit bot/handoff combinations in a dedicated
tenant, then exercises ``overall_service.get_overall_summary`` /
``get_overall_trend`` against the real Postgres test DB and asserts the
"session_overall" group calibers (§3.1 of the 5.0 metric design).
"""
import importlib
import json
from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy import text

import app.extensions  # triggers private overlay
from app.db.session import AsyncSessionLocal, engine

overall_service = importlib.import_module("app.extensions.reports.services.overall_service")
buckets_mod = importlib.import_module("app.extensions.reports.lib.buckets")

_ANCHOR_DATE_STR = "2026-05-12"
_TENANT_SLUG = "test-reports-overall-corp"

_SEEDED = False
_TENANT_PK = 0


@pytest_asyncio.fixture(autouse=True)
async def seed_overall_data():
    """Seed once per session; dispose engine after each test (fresh loop per test)."""
    global _SEEDED, _TENANT_PK
    if _SEEDED:
        yield
        await engine.dispose()
        return

    async with AsyncSessionLocal() as db:
        await db.execute(text("""
            INSERT INTO tenants (tenant_id, name, is_active)
            VALUES (:slug, 'Reports Overall Test Corp', true)
            ON CONFLICT (tenant_id) DO NOTHING
        """), {"slug": _TENANT_SLUG})
        await db.commit()
        t = await db.execute(text("SELECT id FROM tenants WHERE tenant_id = :slug"), {"slug": _TENANT_SLUG})
        _TENANT_PK = t.scalar_one()

        await db.execute(text("DELETE FROM conversations WHERE tenant_id = :tid"), {"tid": _TENANT_PK})
        await db.execute(text("DELETE FROM satisfaction_survey_configs WHERE tenant_id = :tid"), {"tid": _TENANT_PK})
        await db.commit()

        await db.execute(text("""
            INSERT INTO users (tenant_id, public_id, external_id, name)
            VALUES (:tid, 'usr_overall_visitor', 'overall_visitor', 'Overall Visitor')
            ON CONFLICT ON CONSTRAINT uq_users_tenant_external DO NOTHING
        """), {"tid": _TENANT_PK})
        await db.commit()
        v = await db.execute(text(
            "SELECT id FROM users WHERE external_id='overall_visitor' AND tenant_id=:tid"
        ), {"tid": _TENANT_PK})
        visitor_id = v.scalar_one()

        # 4 sessions on the anchor date in tenant tz. Bot/handoff + message-count
        # + queue + response/duration columns are tuned so each metric group has
        # distinct, checkable values:
        #   s1 pure-human  (had_bot=false, triggered=false, succeeded=false) visitor=5 agent=3 → effective; no queue;
        #                  first_resp=30 agent_count=3 agent_avg=20 duration=600
        #   s2 pure-human  (had_bot=false, triggered=false, succeeded=false) visitor=2 agent=0 → unreplied; queued+assigned 60s;
        #                  no agent reply (response cols NULL) duration=300
        #   s3 pure-bot    (had_bot=true,  triggered=true,  succeeded=false) bot_phase_visitor=3; queued+assigned 120s;
        #                  sentinel response/duration=999 — must be excluded from service_efficiency base
        #   s4 bot+human   (had_bot=true,  triggered=true,  succeeded=true)  bot_phase_visitor=2 visitor=0 agent=0 → silent-visitor;
        #                  queued+canceled 90s; response/duration NULL
        # Two at 10:xx (hour=10), two at 15:xx (hour=15) for trend bucketing.
        await db.execute(text("""
            INSERT INTO conversations
              (public_id, share_code, tenant_id, visitor_id, status, started_at, ended_at,
               had_bot_session, bot_handoff_triggered, bot_handoff_succeeded,
               bot_phase_visitor_message_count, visitor_message_count, agent_message_count,
               total_queue_duration_seconds, queue_result,
               first_human_response_seconds, agent_response_count, agent_avg_response_seconds, duration_seconds)
            VALUES
              ('cv_ov_' || substr(md5(random()::text || clock_timestamp()::text), 1, 22), 'OV-' || upper(substr(md5(random()::text || clock_timestamp()::text), 1, 8)), :tid, :vid, 'closed',
               ((:anchor)::date + TIME '10:05')::timestamp AT TIME ZONE 'Asia/Shanghai',
               ((:anchor)::date + TIME '10:15')::timestamp AT TIME ZONE 'Asia/Shanghai', false, false, false, 0, 5, 3, 0, NULL, 30, 3, 20, 600),
              ('cv_ov_' || substr(md5(random()::text || clock_timestamp()::text), 1, 22), 'OV-' || upper(substr(md5(random()::text || clock_timestamp()::text), 1, 8)), :tid, :vid, 'closed',
               ((:anchor)::date + TIME '10:35')::timestamp AT TIME ZONE 'Asia/Shanghai',
               ((:anchor)::date + TIME '10:45')::timestamp AT TIME ZONE 'Asia/Shanghai', false, false, false, 0, 2, 0, 60, 'assigned', NULL, NULL, NULL, 300),
              ('cv_ov_' || substr(md5(random()::text || clock_timestamp()::text), 1, 22), 'OV-' || upper(substr(md5(random()::text || clock_timestamp()::text), 1, 8)), :tid, :vid, 'closed',
               ((:anchor)::date + TIME '15:05')::timestamp AT TIME ZONE 'Asia/Shanghai',
               ((:anchor)::date + TIME '15:15')::timestamp AT TIME ZONE 'Asia/Shanghai', true, true, false, 3, 4, 1, 120, 'assigned', 999, 5, 999, 999),
              ('cv_ov_' || substr(md5(random()::text || clock_timestamp()::text), 1, 22), 'OV-' || upper(substr(md5(random()::text || clock_timestamp()::text), 1, 8)), :tid, :vid, 'closed',
               ((:anchor)::date + TIME '15:35')::timestamp AT TIME ZONE 'Asia/Shanghai',
               ((:anchor)::date + TIME '15:45')::timestamp AT TIME ZONE 'Asia/Shanghai', true, true, true, 2, 0, 0, 90, 'canceled', NULL, NULL, NULL, NULL)
        """), {"tid": _TENANT_PK, "vid": visitor_id, "anchor": date.fromisoformat(_ANCHOR_DATE_STR)})
        await db.commit()

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
                {"key": "product-bad", "enabled": True, "name": "难用", "score": 2},
            ],
        }
        snapshot = {
            "name": "测试满意度",
            "enabled": True,
            "triggers": {"agent_invite": True, "user_initiated": True, "session_end_invite": True},
            "service": service_settings,
            "product": product_settings,
        }
        cfg = await db.execute(text("""
            INSERT INTO satisfaction_survey_configs
              (tenant_id, name, enabled, current_version, triggers, service_settings, product_settings)
            VALUES
              (:tid, '测试满意度', true, 2, CAST(:triggers AS jsonb), CAST(:service AS jsonb), CAST(:product AS jsonb))
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
              (:tid, :config_id, 1, CAST(:snapshot AS jsonb), ((:anchor)::date + TIME '09:00')::timestamp AT TIME ZONE 'Asia/Shanghai'),
              (:tid, :config_id, 2, CAST(:snapshot AS jsonb), ((:anchor)::date + TIME '09:30')::timestamp AT TIME ZONE 'Asia/Shanghai')
        """), {
            "tid": _TENANT_PK,
            "config_id": config_id,
            "snapshot": json.dumps(snapshot),
            "anchor": date.fromisoformat(_ANCHOR_DATE_STR),
        })

        conv_rows = (await db.execute(text("""
            SELECT id, had_bot_session, bot_handoff_succeeded
            FROM conversations
            WHERE tenant_id = :tid
            ORDER BY started_at
        """), {"tid": _TENANT_PK})).all()
        s1_id, s2_id, s3_id, s4_id = [row.id for row in conv_rows]
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
        service_bad = {
            "type": "service",
            "rating_mode": "stars",
            "option_key": "service-bad",
            "option_name": "不满意",
            "labels": [],
            "remark": "",
            "resolved": False,
            "submitted_at": f"{_ANCHOR_DATE_STR}T15:55:00+08:00",
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
              (:tid, :s1, :vid, 2, CAST(:snapshot AS jsonb),
               'agent', ((:anchor)::date + TIME '10:20')::timestamp AT TIME ZONE 'Asia/Shanghai',
               'submitted', '["service","product"]'::jsonb,
               CAST(:service_good AS jsonb), CAST(:product_good AS jsonb),
               ((:anchor)::date + TIME '10:25')::timestamp AT TIME ZONE 'Asia/Shanghai'),
              (:tid, :s2, :vid, 1, CAST(:snapshot AS jsonb),
               'agent', ((:anchor)::date + TIME '10:50')::timestamp AT TIME ZONE 'Asia/Shanghai',
               'submitted', '["service"]'::jsonb,
               CAST(:service_good AS jsonb), NULL,
               ((:anchor)::date + TIME '10:55')::timestamp AT TIME ZONE 'Asia/Shanghai'),
              (:tid, :s3, :vid, 2, CAST(:snapshot AS jsonb),
               'agent', ((:anchor)::date + TIME '15:20')::timestamp AT TIME ZONE 'Asia/Shanghai',
               'submitted', '["service","product"]'::jsonb,
               CAST(:service_good AS jsonb), CAST(:product_good AS jsonb),
               ((:anchor)::date + TIME '15:25')::timestamp AT TIME ZONE 'Asia/Shanghai'),
              (:tid, :s4, :vid, 2, CAST(:snapshot AS jsonb),
               'agent', ((:anchor)::date + TIME '15:50')::timestamp AT TIME ZONE 'Asia/Shanghai',
               'submitted', '["service"]'::jsonb,
               CAST(:service_bad AS jsonb), NULL,
               ((:anchor)::date + TIME '15:55')::timestamp AT TIME ZONE 'Asia/Shanghai')
        """), {
            "tid": _TENANT_PK,
            "vid": visitor_id,
            "s1": s1_id,
            "s2": s2_id,
            "s3": s3_id,
            "s4": s4_id,
            "snapshot": json.dumps(snapshot),
            "service_good": json.dumps(service_good),
            "service_bad": json.dumps(service_bad),
            "product_good": json.dumps(product_good),
            "anchor": date.fromisoformat(_ANCHOR_DATE_STR),
        })
        await db.commit()

    _SEEDED = True
    yield
    await engine.dispose()


def _values_by_key(metrics: list[dict]) -> dict[str, float | None]:
    return {m["key"]: m["value"] for m in metrics}


@pytest.mark.asyncio
async def test_overall_summary_session_overall_calibers():
    anchor = date.fromisoformat(_ANCHOR_DATE_STR)
    async with AsyncSessionLocal() as db:
        result = await overall_service.get_overall_summary(db, _TENANT_PK, anchor, anchor)

    metrics = result["metrics"]
    # Every metric is self-describing and tagged with its group.
    assert all({"key", "value", "format", "level", "group", "available"} <= set(m) for m in metrics)
    assert any(m["group"] == "session_overall" for m in metrics)

    values = _values_by_key([m for m in metrics if m["group"] == "session_overall"])
    assert values["total_session_count"] == 4
    assert values["pure_bot_session_count"] == 1
    assert values["pure_human_session_count"] == 2
    assert values["bot_human_session_count"] == 1
    # human involved = pure human + bot+human
    assert values["human_involved_session_count"] == 3
    # total = pure bot + pure human + bot+human
    assert (
        values["total_session_count"]
        == values["pure_bot_session_count"]
        + values["pure_human_session_count"]
        + values["bot_human_session_count"]
    )


@pytest.mark.asyncio
async def test_overall_trend_buckets_sum_matches_summary():
    anchor = date.fromisoformat(_ANCHOR_DATE_STR)
    async with AsyncSessionLocal() as db:
        summary = await overall_service.get_overall_summary(db, _TENANT_PK, anchor, anchor)
        trend = await overall_service.get_overall_trend(
            db, _TENANT_PK, anchor, anchor, buckets_mod.TrendType.HOUR, group="session_overall"
        )

    assert trend["group"] == "session_overall"
    # Hourly distribution → 24 buckets, empty buckets present and zero-filled.
    assert len(trend["buckets"]) == 24

    summary_values = _values_by_key(
        [m for m in summary["metrics"] if m["group"] == "session_overall"]
    )
    summed: dict[str, float] = {}
    for bucket in trend["buckets"]:
        for metric in bucket["metrics"]:
            summed[metric["key"]] = summed.get(metric["key"], 0) + (metric["value"] or 0)

    for key, expected in summary_values.items():
        assert summed[key] == expected, key


@pytest.mark.asyncio
async def test_overall_trend_unknown_group_falls_back_to_first():
    anchor = date.fromisoformat(_ANCHOR_DATE_STR)
    async with AsyncSessionLocal() as db:
        trend = await overall_service.get_overall_trend(
            db, _TENANT_PK, anchor, anchor, buckets_mod.TrendType.DAY, group="does_not_exist"
        )
    assert trend["group"] == "session_overall"
    assert len(trend["buckets"]) == 1


def _group_values(metrics: list[dict], group: str) -> dict[str, float | None]:
    return {m["key"]: m["value"] for m in metrics if m["group"] == group}


def _distributions_by_key(distributions: list[dict]) -> dict[str, dict]:
    return {item["key"]: item for item in distributions}


def _slice_values(distribution: dict) -> dict[str, int]:
    return {item["key"]: item["value"] for item in distribution["slices"]}


def _distribution_trend_values(distributions: list[dict], group: str) -> dict[str, int]:
    return {
        f"{distribution['key']}:{item['key']}": item["value"]
        for distribution in distributions
        if distribution["group"] == group
        for item in distribution["slices"]
    }


@pytest.mark.asyncio
async def test_overall_summary_human_messages_calibers():
    anchor = date.fromisoformat(_ANCHOR_DATE_STR)
    async with AsyncSessionLocal() as db:
        result = await overall_service.get_overall_summary(db, _TENANT_PK, anchor, anchor)

    values = _group_values(result["metrics"], "human_messages")
    # Human-involved base = s1, s2, s4; the pure-bot s3 is excluded entirely.
    assert values["effective_session_count"] == 1  # s1 only (both sides > 0)
    assert values["visitor_message_count"] == 7  # 5 + 2 + 0, excludes s3's 4
    assert values["agent_message_count"] == 3  # 3 + 0 + 0, excludes s3's 1
    assert values["unreplied_session_count"] == 1  # s2 (visitor > 0, agent = 0)
    assert values["visitor_silent_session_count"] == 1  # s4 (visitor = 0)


@pytest.mark.asyncio
async def test_overall_summary_queue_access_calibers():
    anchor = date.fromisoformat(_ANCHOR_DATE_STR)
    async with AsyncSessionLocal() as db:
        result = await overall_service.get_overall_summary(db, _TENANT_PK, anchor, anchor)

    values = _group_values(result["metrics"], "queue_access")
    # s2, s3, s4 queued; s1 has total_queue_duration_seconds = 0.
    assert values["queued_session_count"] == 3
    assert values["assigned_queue_session_count"] == 2  # s2 + s3
    assert values["unassigned_queue_session_count"] == 1  # s4 (canceled)
    assert values["avg_queue_duration_seconds"] == pytest.approx(90.0)  # (60+120+90)/3
    assert values["max_queue_duration_seconds"] == pytest.approx(120.0)
    assert values["queue_assign_rate"] == pytest.approx(2 / 3)


@pytest.mark.asyncio
async def test_overall_summary_no_queue_rate_is_none():
    """A range with no queued sessions returns assign rate=None (renders as —)."""
    empty_day = date.fromisoformat("2026-05-01")
    async with AsyncSessionLocal() as db:
        result = await overall_service.get_overall_summary(db, _TENANT_PK, empty_day, empty_day)
    values = _group_values(result["metrics"], "queue_access")
    assert values["queued_session_count"] == 0
    assert values["avg_queue_duration_seconds"] is None
    assert values["max_queue_duration_seconds"] is None
    assert values["queue_assign_rate"] is None


@pytest.mark.asyncio
async def test_overall_summary_service_efficiency_calibers():
    anchor = date.fromisoformat(_ANCHOR_DATE_STR)
    async with AsyncSessionLocal() as db:
        result = await overall_service.get_overall_summary(db, _TENANT_PK, anchor, anchor)

    values = _group_values(result["metrics"], "service_efficiency")
    # Human-involved base = s1, s2, s4; pure-bot s3 (sentinel 999) is excluded.
    # First response: only s1=30 is set (s2/s4 NULL) → avg over set values.
    assert values["avg_first_human_response_seconds"] == pytest.approx(30.0)
    # Weighted agent response: only s1 has counts → (20 * 3) / 3 = 20.
    assert values["avg_agent_response_seconds"] == pytest.approx(20.0)
    # Duration: s1=600, s2=300 set, s4 NULL → (600 + 300) / 2 = 450.
    assert values["avg_human_session_duration_seconds"] == pytest.approx(450.0)


@pytest.mark.asyncio
async def test_overall_summary_no_service_efficiency_is_none():
    """A range with no human-involved sessions returns all averages None (renders as —)."""
    empty_day = date.fromisoformat("2026-05-01")
    async with AsyncSessionLocal() as db:
        result = await overall_service.get_overall_summary(db, _TENANT_PK, empty_day, empty_day)
    values = _group_values(result["metrics"], "service_efficiency")
    assert values["avg_first_human_response_seconds"] is None
    assert values["avg_agent_response_seconds"] is None
    assert values["avg_human_session_duration_seconds"] is None


@pytest.mark.asyncio
async def test_overall_summary_satisfaction_calibers():
    anchor = date.fromisoformat(_ANCHOR_DATE_STR)
    async with AsyncSessionLocal() as db:
        result = await overall_service.get_overall_summary(db, _TENANT_PK, anchor, anchor)

    values = _group_values(result["metrics"], "satisfaction")
    # Current-version, human-involved records only: s1 and s4. s2 is old
    # version; s3 is pure bot, so both are excluded.
    assert values["satisfaction_invitation_count"] == 2
    assert values["satisfaction_submission_count"] == 2
    assert values["satisfaction_participation_rate"] == pytest.approx(2 / 3)
    assert values["satisfaction_submission_rate"] == pytest.approx(1.0)
    assert values["product_satisfaction_count"] == 1
    assert "service_satisfaction_count" not in values
    assert "satisfaction_resolution_rate" not in values

    distributions = _distributions_by_key(result["distributions"])
    assert set(distributions) == {
        "satisfaction_resolution",
        "service_satisfaction_rating",
        "product_satisfaction_rating",
    }
    assert distributions["satisfaction_resolution"]["total"] == 2
    assert _slice_values(distributions["satisfaction_resolution"]) == {
        "resolved": 1,
        "unresolved": 1,
    }
    assert distributions["service_satisfaction_rating"]["total"] == 2
    assert _slice_values(distributions["service_satisfaction_rating"]) == {
        "service-good": 1,
        "service-bad": 1,
    }
    assert distributions["product_satisfaction_rating"]["total"] == 1
    assert _slice_values(distributions["product_satisfaction_rating"]) == {
        "product-good": 1,
        "product-bad": 0,
    }


@pytest.mark.asyncio
async def test_overall_trend_satisfaction_calibers():
    anchor = date.fromisoformat(_ANCHOR_DATE_STR)
    async with AsyncSessionLocal() as db:
        trend = await overall_service.get_overall_trend(
            db, _TENANT_PK, anchor, anchor, buckets_mod.TrendType.HOUR, group="satisfaction"
        )

    assert trend["group"] == "satisfaction"
    assert [m["key"] for m in trend["metrics"]] == [
        "satisfaction_invitation_count",
        "satisfaction_submission_count",
        "product_satisfaction_count",
        "satisfaction_resolution:resolved",
        "satisfaction_resolution:unresolved",
        "service_satisfaction_rating:service-good",
        "service_satisfaction_rating:service-bad",
        "product_satisfaction_rating:product-good",
        "product_satisfaction_rating:product-bad",
    ]
    by_label = {bucket["label"]: _values_by_key(bucket["metrics"]) for bucket in trend["buckets"]}
    assert by_label["10"]["satisfaction_invitation_count"] == 1
    assert by_label["10"]["satisfaction_submission_count"] == 1
    assert by_label["10"]["product_satisfaction_count"] == 1
    assert by_label["10"]["satisfaction_resolution:resolved"] == 1
    assert by_label["10"]["satisfaction_resolution:unresolved"] == 0
    assert by_label["10"]["service_satisfaction_rating:service-good"] == 1
    assert by_label["10"]["service_satisfaction_rating:service-bad"] == 0
    assert by_label["10"]["product_satisfaction_rating:product-good"] == 1
    assert by_label["10"]["product_satisfaction_rating:product-bad"] == 0
    assert by_label["15"]["satisfaction_invitation_count"] == 1
    assert by_label["15"]["satisfaction_submission_count"] == 1
    assert by_label["15"]["product_satisfaction_count"] == 0
    assert by_label["15"]["satisfaction_resolution:resolved"] == 0
    assert by_label["15"]["satisfaction_resolution:unresolved"] == 1
    assert by_label["15"]["service_satisfaction_rating:service-good"] == 0
    assert by_label["15"]["service_satisfaction_rating:service-bad"] == 1
    assert by_label["15"]["product_satisfaction_rating:product-good"] == 0
    assert by_label["15"]["product_satisfaction_rating:product-bad"] == 0


# Integer count metrics sum across buckets; derived ratios and aggregate
# durations do not.
_NON_SUMMABLE_TREND_KEYS: dict[str, set[str]] = {
    "human_messages": set(),
    "queue_access": {"queue_assign_rate", "avg_queue_duration_seconds", "max_queue_duration_seconds"},
    "service_efficiency": {
        "avg_first_human_response_seconds",
        "avg_agent_response_seconds",
        "avg_human_session_duration_seconds",
    },
    "satisfaction": {
        "satisfaction_participation_rate",
        "satisfaction_submission_rate",
    },
}


@pytest.mark.asyncio
@pytest.mark.parametrize("group", ["human_messages", "queue_access", "service_efficiency", "satisfaction"])
async def test_overall_trend_buckets_sum_matches_summary_for_group(group):
    anchor = date.fromisoformat(_ANCHOR_DATE_STR)
    async with AsyncSessionLocal() as db:
        summary = await overall_service.get_overall_summary(db, _TENANT_PK, anchor, anchor)
        trend = await overall_service.get_overall_trend(
            db, _TENANT_PK, anchor, anchor, buckets_mod.TrendType.HOUR, group=group
        )

    assert trend["group"] == group
    assert len(trend["buckets"]) == 24

    summary_values = {
        **_group_values(summary["metrics"], group),
        **_distribution_trend_values(summary["distributions"], group),
    }
    summed: dict[str, float] = {}
    for bucket in trend["buckets"]:
        for metric in bucket["metrics"]:
            summed[metric["key"]] = summed.get(metric["key"], 0) + (metric["value"] or 0)

    # Only summable trend metrics are expected to match; derived ratios and
    # bucket-level averages/maxes are excluded.
    skip = _NON_SUMMABLE_TREND_KEYS.get(group, set())
    for key, total in summed.items():
        if key in skip:
            continue
        assert total == summary_values[key], key
