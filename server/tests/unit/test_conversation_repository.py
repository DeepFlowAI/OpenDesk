"""
Unit tests for ``ConversationRepository`` helpers that don't need a real DB.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.repositories.conversation_repository import ConversationRepository


class TestIncrementUnread:

    @pytest.mark.asyncio
    async def test_returns_post_increment_value(self):
        db = MagicMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = 3
        db.execute = AsyncMock(return_value=result)
        db.commit = AsyncMock()

        new_value = await ConversationRepository.increment_unread(db, 100)

        assert new_value == 3
        db.execute.assert_awaited_once()
        db.commit.assert_awaited_once()
        # The single UPDATE carries the atomic increment expression.
        statement = str(db.execute.await_args.args[0])
        assert "unread_count" in statement

    @pytest.mark.asyncio
    async def test_missing_row_returns_zero(self):
        db = MagicMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result)
        db.commit = AsyncMock()

        new_value = await ConversationRepository.increment_unread(db, 999)

        assert new_value == 0
