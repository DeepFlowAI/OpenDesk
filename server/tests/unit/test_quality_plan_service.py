"""Unit tests for online quality plan strategies."""
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.repositories.quality_plan_repository import QualityPlanRepository
from app.schemas.permission import EffectivePrincipal
from app.schemas.quality_plan import QualityPlanPayload
from app.services.quality_plan_service import QualityPlanService


def test_stable_sample_value_is_repeatable_and_bounded() -> None:
    first = QualityPlanService.stable_sample_value(1, 2, 3)
    assert first == QualityPlanService.stable_sample_value(1, 2, 3)
    assert Decimal("0") <= first < Decimal("1")


def test_config_signature_changes_with_scope_boundary() -> None:
    payload = QualityPlanPayload(name="QA", scorecard_version_id=7, reviewer_ids=[9])
    all_scope = EffectivePrincipal(user_id=1, tenant_id=1, permissions=[], data_scopes={"session_record": "all"})
    group_scope = EffectivePrincipal(user_id=1, tenant_id=1, permissions=[], data_scopes={"session_record": "group"}, group_ids=[2])
    assert QualityPlanService.config_signature(payload, all_scope) != QualityPlanService.config_signature(payload, group_scope)


def test_one_time_range_model_accepts_timezone_aware_range() -> None:
    payload = QualityPlanPayload(name="QA", run_mode="one_time", range_start_at=datetime(2026, 1, 1, tzinfo=timezone.utc), range_end_at=datetime(2026, 1, 2, tzinfo=timezone.utc), scorecard_version_id=7, reviewer_ids=[9])
    assert payload.run_mode == "one_time"


@pytest.mark.asyncio
async def test_save_reloads_plan_after_commit(monkeypatch) -> None:
    db = MagicMock()
    db.commit = AsyncMock()
    plan = SimpleNamespace(id=1, tenant_id=1)
    reloaded = SimpleNamespace(id=1, tenant_id=1, updated_at="fresh")

    async def fake_get_by_id(_db, tenant_id: int, plan_id: int):
        assert _db is db
        assert tenant_id == 1
        assert plan_id == 1
        return reloaded

    monkeypatch.setattr(QualityPlanRepository, "get_by_id", fake_get_by_id)

    result = await QualityPlanRepository.save(db, plan)

    db.add.assert_called_once_with(plan)
    db.commit.assert_awaited_once()
    assert result is reloaded


@pytest.mark.asyncio
async def test_replace_candidates_reloads_plan_after_commit(monkeypatch) -> None:
    db = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    plan = SimpleNamespace(id=1, tenant_id=1, candidates=[])
    reloaded = SimpleNamespace(id=1, tenant_id=1, updated_at="fresh")

    async def fake_get_by_id(_db, tenant_id: int, plan_id: int):
        assert plan_id == 1
        return reloaded

    monkeypatch.setattr(QualityPlanRepository, "get_by_id", fake_get_by_id)

    result = await QualityPlanRepository.replace_candidates(db, plan, [])

    db.flush.assert_awaited_once()
    db.commit.assert_awaited_once()
    assert result is reloaded
