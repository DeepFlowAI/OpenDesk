"""Auto-outbound answer must not wait on callee→user phone matching.

Regression: create_for_outbound used to call identify_for_record on the
originate / answer path. When the callee answered in ~2s, that scan still
held handle_call_answered and delayed assign_queue by several seconds.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import fakeredis.aioredis
import pytest

from app.models.auto_outbound import AutoOutboundCallRecord, AutoOutboundTarget, AutoOutboundTask
from app.services.auto_outbound.engine import AutoOutboundDialEngine
from app.services.call_record_service import CallRecordService


class _SessionCM:
    def __init__(self, db=None):
        self.db = db or MagicMock()
        self.db.commit = AsyncMock()

    async def __aenter__(self):
        return self.db

    async def __aexit__(self, *_exc):
        return False


@pytest.fixture
async def redis():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


@pytest.mark.asyncio
async def test_answered_starts_reception_before_slow_user_identify(redis, monkeypatch):
    from app.services.auto_outbound import frequency as freq

    await freq.set_session_mapping(
        "ans-fast",
        {
            "tenant_id": 1,
            "task_id": 1,
            "target_id": 10,
            "record_id": 100,
            "phone_number": "13800138000",
            "answered": False,
        },
        redis=redis,
    )

    record = AutoOutboundCallRecord(
        id=100,
        tenant_id=1,
        task_id=1,
        target_id=10,
        phone_number="13800138000",
        attempt_no=1,
        started_at=datetime(2026, 8, 18, 10, 0, tzinfo=timezone.utc),
        duration_ms=0,
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.get_record",
        AsyncMock(return_value=record),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.set_call_record_id_if_empty",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.mark_answered_once",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.get_task",
        AsyncMock(
            return_value=AutoOutboundTask(
                id=1,
                tenant_id=1,
                name="t",
                template_name="tpl",
                fields=[],
                status="active",
                execution_mode="agent",
                start_date=datetime(2026, 8, 1).date(),
                end_date=datetime(2026, 8, 31).date(),
                daily_time_windows=[],
                max_concurrency=1,
                retry_policy={},
                daily_per_number_limit=1,
                wrapup_seconds=60,
            )
        ),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.get_target",
        AsyncMock(
            return_value=AutoOutboundTarget(
                id=10,
                tenant_id=1,
                task_id=1,
                phone_number="13800138000",
                status="calling",
                field_values={},
                call_count=1,
                answered_count=1,
                retry_counts={},
            )
        ),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundEventService.emit_call_event",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "app.services.call_center.orchestrator.get_orchestrator",
        MagicMock(side_effect=RuntimeError("no orch")),
    )

    create_kwargs: dict = {}

    async def _create(*_args, **kwargs):
        create_kwargs.update(kwargs)
        return {"id": 55}

    identify_finished = asyncio.Event()
    order: list[str] = []

    async def _identify(_tenant_id: int, _call_id: str) -> None:
        order.append("identify_start")
        await asyncio.sleep(0.2)
        order.append("identify_done")
        identify_finished.set()

    async def _on_answered(_ctx) -> None:
        order.append("reception")

    reception = AsyncMock()
    reception.on_answered = _on_answered

    monkeypatch.setattr(CallRecordService, "create_for_outbound", staticmethod(_create))
    monkeypatch.setattr(
        CallRecordService, "identify_user_for_call_managed", staticmethod(_identify)
    )

    engine = AutoOutboundDialEngine(
        redis=redis,
        session_factory=lambda: _SessionCM(),
        reception=reception,
    )
    await engine.handle_call_answered("ans-fast")

    assert create_kwargs.get("identify_user") is False
    assert "reception" in order
    assert not identify_finished.is_set()
    await asyncio.wait_for(identify_finished.wait(), timeout=1.0)
    assert order.index("reception") < order.index("identify_done")
