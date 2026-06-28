"""Unit tests for the materialized message-count caliber."""
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.libs.conversation_metrics import (
    conversation_in_human_phase,
    message_count_increments,
)


class TestMessageCountIncrements:

    def test_visitor_bot_phase(self):
        assert message_count_increments("visitor", in_human_phase=False) == {
            "visitor_message_count": 1,
            "bot_phase_message_count": 1,
            "bot_phase_visitor_message_count": 1,
        }

    def test_visitor_human_phase(self):
        assert message_count_increments("visitor", in_human_phase=True) == {
            "visitor_message_count": 1,
            "human_phase_message_count": 1,
            "human_phase_visitor_message_count": 1,
        }

    @pytest.mark.parametrize("in_human_phase", [True, False])
    def test_agent_always_human_phase(self, in_human_phase):
        assert message_count_increments("agent", in_human_phase=in_human_phase) == {
            "agent_message_count": 1,
            "human_phase_message_count": 1,
            "human_phase_agent_message_count": 1,
        }

    @pytest.mark.parametrize("in_human_phase", [True, False])
    def test_bot_always_bot_phase(self, in_human_phase):
        assert message_count_increments("bot", in_human_phase=in_human_phase) == {
            "bot_phase_message_count": 1,
        }

    @pytest.mark.parametrize("sender_type", ["system", "unknown", ""])
    @pytest.mark.parametrize("in_human_phase", [True, False])
    def test_other_senders_increment_nothing(self, sender_type, in_human_phase):
        assert message_count_increments(sender_type, in_human_phase=in_human_phase) == {}


class TestConversationInHumanPhase:

    def test_non_bot_conversation_is_human_phase(self):
        conv = SimpleNamespace(had_bot_session=False, started_at=None)
        assert conversation_in_human_phase(conv) is True

    def test_bot_conversation_before_takeover_is_bot_phase(self):
        conv = SimpleNamespace(had_bot_session=True, started_at=None)
        assert conversation_in_human_phase(conv) is False

    def test_bot_conversation_after_takeover_is_human_phase(self):
        conv = SimpleNamespace(
            had_bot_session=True, started_at=datetime.now(timezone.utc)
        )
        assert conversation_in_human_phase(conv) is True
