"""Unit tests for the conversation basic report-field caliber."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.libs.conversation_metrics import (
    bot_flags_for_conversation,
    compute_agent_response_metrics,
    compute_bot_handoff_succeeded,
    compute_bot_handoff_triggered,
    compute_duration_seconds,
    compute_first_human_response_seconds,
    compute_had_bot_session,
)


class TestComputeHadBotSession:

    @pytest.mark.parametrize(
        ("agent_id", "conversation_id", "external_id", "expected"),
        [
            (None, None, None, False),
            (12, None, None, True),
            (None, 34, None, True),
            (None, None, "oa_ext", True),
            (12, 34, "oa_ext", True),
            (0, 0, "", False),
        ],
    )
    def test_or_over_openagent_identity_fields(self, agent_id, conversation_id, external_id, expected):
        assert compute_had_bot_session(agent_id, conversation_id, external_id) is expected


class TestComputeBotHandoffSucceeded:

    @pytest.mark.parametrize(
        ("state", "expected"),
        [
            (None, False),
            ("requested", False),
            ("pending", False),
            ("queued", False),
            ("failed", False),
            ("dismissed", False),
            ("success", True),
        ],
    )
    def test_only_success_state_is_true(self, state, expected):
        assert compute_bot_handoff_succeeded(state) is expected


class TestComputeBotHandoffTriggered:

    @pytest.mark.parametrize(
        ("state", "expected"),
        [
            (None, False),
            ("requested", True),
            ("pending", True),
            ("queued", True),
            ("failed", True),
            ("dismissed", True),
            ("success", True),
        ],
    )
    def test_any_non_null_state_is_triggered(self, state, expected):
        assert compute_bot_handoff_triggered(state) is expected


class TestComputeDurationSeconds:

    def test_none_when_not_started(self):
        ended = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
        assert compute_duration_seconds(None, ended) is None

    def test_none_when_in_progress(self):
        started = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
        assert compute_duration_seconds(started, None) is None

    def test_whole_seconds_for_ended_session(self):
        started = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        ended = started + timedelta(minutes=10, milliseconds=600)
        assert compute_duration_seconds(started, ended) == 600

    def test_negative_clamped_to_zero(self):
        started = datetime(2026, 1, 1, 10, 0, 5, tzinfo=timezone.utc)
        ended = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        assert compute_duration_seconds(started, ended) == 0


class TestComputeFirstHumanResponseSeconds:

    def test_none_without_visitor_message(self):
        agent_reply_at = datetime(2026, 1, 1, 10, 1, tzinfo=timezone.utc)
        assert compute_first_human_response_seconds(None, agent_reply_at) is None

    def test_none_without_agent_reply(self):
        visitor_message_at = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
        assert compute_first_human_response_seconds(visitor_message_at, None) is None

    def test_whole_seconds_between_pending_visitor_and_agent_reply(self):
        visitor_message_at = datetime(2026, 1, 1, 10, 0, 30, tzinfo=timezone.utc)
        agent_reply_at = datetime(2026, 1, 1, 10, 3, 0, tzinfo=timezone.utc)
        assert compute_first_human_response_seconds(visitor_message_at, agent_reply_at) == 150

    def test_negative_clamped_to_zero(self):
        visitor_message_at = datetime(2026, 1, 1, 10, 1, tzinfo=timezone.utc)
        agent_reply_at = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
        assert compute_first_human_response_seconds(visitor_message_at, agent_reply_at) == 0


class TestComputeAgentResponseMetrics:

    _BASE = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)

    def _at(self, seconds: int) -> datetime:
        return self._BASE + timedelta(seconds=seconds)

    def test_empty_conversation(self):
        assert compute_agent_response_metrics([]) == (0, None)

    def test_no_agent_reply(self):
        msgs = [("visitor", self._at(0)), ("visitor", self._at(10))]
        assert compute_agent_response_metrics(msgs) == (0, None)

    def test_agent_reply_without_preceding_visitor(self):
        # Conversation opens with an agent message: not a response.
        msgs = [("agent", self._at(0)), ("agent", self._at(5))]
        assert compute_agent_response_metrics(msgs) == (0, None)

    def test_consecutive_visitor_messages_use_last_as_start(self):
        # Two visitor messages then one agent reply -> one response timed from
        # the last visitor message (at 30s) to the reply (at 150s).
        msgs = [
            ("visitor", self._at(0)),
            ("visitor", self._at(30)),
            ("agent", self._at(150)),
        ]
        assert compute_agent_response_metrics(msgs) == (1, 120)

    def test_consecutive_agent_replies_count_first_only(self):
        msgs = [
            ("visitor", self._at(0)),
            ("agent", self._at(60)),
            ("agent", self._at(90)),
        ]
        assert compute_agent_response_metrics(msgs) == (1, 60)

    def test_multiple_rounds_average(self):
        # Round 1: 60s, round 2: 40s -> count 2, avg 50.
        msgs = [
            ("visitor", self._at(0)),
            ("agent", self._at(60)),
            ("visitor", self._at(100)),
            ("agent", self._at(140)),
        ]
        assert compute_agent_response_metrics(msgs) == (2, 50)

    def test_average_rounds_half_up(self):
        # Durations 2s and 3s -> avg 2.5 -> rounds to 3.
        msgs = [
            ("visitor", self._at(0)),
            ("agent", self._at(2)),
            ("visitor", self._at(10)),
            ("agent", self._at(13)),
        ]
        assert compute_agent_response_metrics(msgs) == (2, 3)

    def test_negative_delta_clamped_to_zero(self):
        msgs = [
            ("visitor", self._at(10)),
            ("agent", self._at(5)),
        ]
        assert compute_agent_response_metrics(msgs) == (1, 0)


class TestBotFlagsForConversation:

    def test_human_conversation(self):
        conv = SimpleNamespace(
            open_agent_agent_id=None,
            open_agent_conversation_id=None,
            open_agent_conversation_external_id=None,
            open_agent_handoff_state=None,
        )
        assert bot_flags_for_conversation(conv) == {
            "had_bot_session": False,
            "bot_handoff_succeeded": False,
            "bot_handoff_triggered": False,
        }

    def test_bot_handoff_success(self):
        conv = SimpleNamespace(
            open_agent_agent_id=12,
            open_agent_conversation_id=None,
            open_agent_conversation_external_id=None,
            open_agent_handoff_state="success",
        )
        assert bot_flags_for_conversation(conv) == {
            "had_bot_session": True,
            "bot_handoff_succeeded": True,
            "bot_handoff_triggered": True,
        }

    def test_bot_handoff_triggered_but_not_succeeded(self):
        conv = SimpleNamespace(
            open_agent_agent_id=12,
            open_agent_conversation_id=None,
            open_agent_conversation_external_id=None,
            open_agent_handoff_state="failed",
        )
        assert bot_flags_for_conversation(conv) == {
            "had_bot_session": True,
            "bot_handoff_succeeded": False,
            "bot_handoff_triggered": True,
        }
