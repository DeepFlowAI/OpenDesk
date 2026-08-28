"""Unit tests for manual outbound task repository helpers."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.repositories.outbound_task_repository import OutboundTaskRepository


class _CountResult:
    def __init__(self, total: int) -> None:
        self._total = total

    def scalar_one(self) -> int:
        return self._total


class _RowsResult:
    def __init__(self, rows) -> None:
        self._rows = rows

    def all(self):
        return self._rows


@pytest.mark.asyncio
async def test_list_my_targets_attaches_user_name() -> None:
    target_with_user = SimpleNamespace(id=1, user_id=100)
    target_without_user = SimpleNamespace(id=2, user_id=None)
    db = AsyncMock()
    db.execute.side_effect = [
        _CountResult(2),
        _RowsResult([(target_with_user, "Alice"), (target_without_user, None)]),
    ]

    items, total = await OutboundTaskRepository.list_my_targets(db, 1, 10, 1, 20)

    assert total == 2
    assert items[0].user_name == "Alice"
    assert items[1].user_name is None
    statement = db.execute.await_args_list[1].args[0]
    assert "users" in str(statement.compile())
