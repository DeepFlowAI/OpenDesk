"""Unit tests for personal auto-outbound persistence invariants."""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.repositories.personal_auto_outbound_repository import PersonalAutoOutboundRepository


class _ScalarResult:
    def __init__(self, values) -> None:
        self._values = values

    def scalars(self):
        return self

    def all(self):
        return self._values


@pytest.mark.asyncio
async def test_claim_calls_requires_active_task() -> None:
    db = AsyncMock()
    db.execute.return_value = _ScalarResult([])
    session = SimpleNamespace(id=5, tenant_id=3, task_id=8, primary_agent_id=7)

    await PersonalAutoOutboundRepository.claim_calls(db, session, 2)

    statement = db.execute.await_args.args[0]
    compiled = statement.compile()
    assert "outbound_tasks.status" in str(compiled)
    assert "active" in compiled.params.values()


@pytest.mark.asyncio
async def test_terminal_call_and_target_settle_in_one_commit() -> None:
    target = SimpleNamespace(
        status="calling",
        call_count=0,
        answered_count=0,
        last_called_at=None,
        last_call_result=None,
    )
    target_result = SimpleNamespace(scalar_one_or_none=lambda: target)
    db = AsyncMock()
    db.execute.return_value = target_result
    row = SimpleNamespace(
        target_id=9,
        started_at=datetime.now(timezone.utc),
        stage="ringing",
    )

    await PersonalAutoOutboundRepository.update_call_and_settle_target(
        db,
        row,
        {"stage": "ended"},
        target_status="completed",
        result="custom_rejection",
        answered=True,
    )

    assert row.stage == "ended"
    assert target.status == "completed"
    assert target.call_count == 1
    assert target.answered_count == 1
    assert target.last_call_result == "custom_rejection"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_filtered_metric_counts_custom_intents() -> None:
    metrics = {
        "ringing_current": 0,
        "screening_current": 0,
        "human_current": 0,
        "filtered_current": 0,
        "ringing_total": 0,
        "screening_total": 0,
        "human_total": 0,
        "filtered_total": 0,
        "primary_human_current": 0,
    }
    row = SimpleNamespace(_fields=tuple(metrics), **metrics)
    result = SimpleNamespace(one=lambda: row)
    db = AsyncMock()
    db.execute.return_value = result

    await PersonalAutoOutboundRepository.counts(db, 5)

    compiled = db.execute.await_args.args[0].compile()
    excluded = next(
        value
        for value in compiled.params.values()
        if isinstance(value, (list, tuple)) and "uncertain" in value
    )
    assert set(excluded) == {"uncertain", "non_rejection", "human_completed"}
    assert "custom_rejection" not in excluded


def _db_returning(row):
    result = SimpleNamespace(scalar_one_or_none=lambda: row)
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result)
    return db


class TestReplaceRecording:
    @pytest.mark.asyncio
    async def test_reactivates_inactive_row_instead_of_inserting(self) -> None:
        """A previously-removed (is_active=False) row still occupies the
        unique (tenant, employee, recording_type) key, so replace must update
        it — inserting would violate the constraint."""
        inactive = SimpleNamespace(
            id=9, is_active=False, audio_asset_id=1,
        )
        db = _db_returning(inactive)

        with patch.object(
            PersonalAutoOutboundRepository,
            "get_recording",
            new=AsyncMock(return_value=inactive),
        ) as get:
            row = await PersonalAutoOutboundRepository.replace_recording(
                db, 3, 7, "closing", 42
            )

        get.assert_awaited_once_with(db, 3, 7, "closing", include_inactive=True)
        assert row is inactive
        assert row.audio_asset_id == 42
        assert row.is_active is True
        db.add.assert_not_called()
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_inserts_when_no_row_exists(self) -> None:
        db = _db_returning(None)

        with patch.object(
            PersonalAutoOutboundRepository,
            "get_recording",
            new=AsyncMock(return_value=None),
        ):
            await PersonalAutoOutboundRepository.replace_recording(
                db, 3, 7, "closing", 42
            )

        db.add.assert_called_once()
        added = db.add.call_args.args[0]
        assert (added.tenant_id, added.employee_id) == (3, 7)
        assert added.recording_type == "closing"
        assert added.audio_asset_id == 42
        db.commit.assert_awaited_once()
