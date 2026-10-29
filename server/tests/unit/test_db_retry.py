from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import OperationalError

from app.db.retry import is_deadlock_error, run_db_op_with_deadlock_retry


class _DeadlockDetectedError(Exception):
    sqlstate = "40P01"


def test_is_deadlock_error_detects_asyncpg_sqlstate():
    assert is_deadlock_error(_DeadlockDetectedError("deadlock detected"))


def test_is_deadlock_error_unwraps_sqlalchemy_orig():
    wrapped = OperationalError("UPDATE", {}, _DeadlockDetectedError("deadlock detected"))
    assert is_deadlock_error(wrapped)


def test_is_deadlock_error_ignores_unrelated():
    assert is_deadlock_error(RuntimeError("boom")) is False


@pytest.mark.asyncio
async def test_run_db_op_retries_deadlock_then_succeeds(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr("app.db.retry.asyncio.sleep", AsyncMock(side_effect=sleeps.append))
    calls = {"n": 0}

    async def op():
        calls["n"] += 1
        if calls["n"] == 1:
            raise _DeadlockDetectedError("deadlock detected")
        return "ok"

    assert await run_db_op_with_deadlock_retry(op, log_label="test_op") == "ok"
    assert calls["n"] == 2
    assert sleeps == [0.05]


@pytest.mark.asyncio
async def test_run_db_op_gives_up_after_deadlock_attempts(monkeypatch):
    monkeypatch.setattr("app.db.retry.asyncio.sleep", AsyncMock())

    async def op():
        raise _DeadlockDetectedError("deadlock detected")

    with pytest.raises(_DeadlockDetectedError):
        await run_db_op_with_deadlock_retry(op, attempts=2, log_label="test_op")
