"""Unit tests for auto outbound task schemas."""

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.auto_outbound import (
    AutoOutboundTargetResponse,
    AutoOutboundTargetUpdate,
    AutoOutboundTaskCreate,
    AutoOutboundTaskListItem,
    AutoOutboundTaskResponse,
    AutoOutboundTaskStats,
    AutoOutboundTaskUpdate,
)


def _base_kwargs(**overrides):
    payload = {
        "name": "满意度回访",
        "template_id": 1,
        "execution_mode": "ivr",
        "voice_flow_id": 10,
        "voice_flow_name": "回访流程",
        "start_date": date(2026, 8, 1),
        "end_date": date(2026, 8, 31),
        "daily_time_windows": [{"start": "09:00", "end": "12:00"}],
        "caller_number_id": "pn_1",
    }
    payload.update(overrides)
    return payload


class TestAutoOutboundTaskCreateSchema:
    def test_auto_resume_on_target_append_defaults_false(self):
        data = AutoOutboundTaskCreate(**_base_kwargs())
        assert data.auto_resume_on_target_append is False
        with pytest.raises(ValidationError):
            AutoOutboundTaskUpdate(auto_resume_on_target_append=None)

    def test_ivr_requires_voice_flow(self):
        with pytest.raises(ValidationError):
            AutoOutboundTaskCreate(**_base_kwargs(voice_flow_id=None))

    def test_bot_requires_agent_and_transfer_queue(self):
        with pytest.raises(ValidationError):
            AutoOutboundTaskCreate(
                **_base_kwargs(
                    execution_mode="bot",
                    voice_flow_id=None,
                    voicespeed_agent_id="agent-1",
                    transfer_queue_id=None,
                )
            )

        ok = AutoOutboundTaskCreate(
            **_base_kwargs(
                execution_mode="bot",
                voice_flow_id=None,
                voicespeed_agent_id="agent-1",
                voicespeed_agent_name="Bot A",
                transfer_queue_id=3,
            )
        )
        assert ok.voicespeed_agent_id == "agent-1"

    def test_agent_requires_queue_and_pacing(self):
        with pytest.raises(ValidationError):
            AutoOutboundTaskCreate(
                **_base_kwargs(
                    execution_mode="agent",
                    voice_flow_id=None,
                    queue_id=5,
                    pacing_mode=None,
                )
            )

    def test_ratio_requires_dial_ratio_and_abandon_prompt(self):
        with pytest.raises(ValidationError):
            AutoOutboundTaskCreate(
                **_base_kwargs(
                    execution_mode="agent",
                    voice_flow_id=None,
                    queue_id=5,
                    pacing_mode="ratio",
                    dial_ratio=2,
                    abandon_prompt=None,
                )
            )

        with pytest.raises(ValidationError):
            AutoOutboundTaskCreate(
                **_base_kwargs(
                    execution_mode="agent",
                    voice_flow_id=None,
                    queue_id=5,
                    pacing_mode="ratio",
                    dial_ratio=1,
                    abandon_prompt="hangup",
                )
            )

        ok = AutoOutboundTaskCreate(
            **_base_kwargs(
                execution_mode="agent",
                voice_flow_id=None,
                queue_id=5,
                pacing_mode="ratio",
                dial_ratio=3,
                abandon_prompt="play_wait",
            )
        )
        assert ok.dial_ratio == 3

    def test_predictive_requires_intensity_limit_and_prompt(self):
        with pytest.raises(ValidationError):
            AutoOutboundTaskCreate(
                **_base_kwargs(
                    execution_mode="agent",
                    voice_flow_id=None,
                    queue_id=5,
                    pacing_mode="predictive",
                    dial_intensity=Decimal("1.5"),
                    abandon_rate_limit=None,
                    abandon_prompt="hangup",
                )
            )

        with pytest.raises(ValidationError):
            AutoOutboundTaskCreate(
                **_base_kwargs(
                    execution_mode="agent",
                    voice_flow_id=None,
                    queue_id=5,
                    pacing_mode="predictive",
                    dial_intensity=Decimal("3.5"),
                    abandon_rate_limit=Decimal("0.03"),
                    abandon_prompt="hangup",
                )
            )

        ok = AutoOutboundTaskCreate(
            **_base_kwargs(
                execution_mode="agent",
                voice_flow_id=None,
                queue_id=5,
                pacing_mode="predictive",
                dial_intensity=Decimal("1.5"),
                abandon_rate_limit=Decimal("0.03"),
                abandon_prompt="hangup",
            )
        )
        assert ok.dial_intensity == Decimal("1.5")

    def test_end_date_cannot_precede_start_date(self):
        with pytest.raises(ValidationError):
            AutoOutboundTaskCreate(**_base_kwargs(end_date=date(2026, 7, 1)))

    def test_daily_time_windows_required(self):
        with pytest.raises(ValidationError):
            AutoOutboundTaskCreate(**_base_kwargs(daily_time_windows=[]))

    def test_name_required_and_max_length(self):
        with pytest.raises(ValidationError):
            AutoOutboundTaskCreate(**_base_kwargs(name="  "))
        with pytest.raises(ValidationError):
            AutoOutboundTaskCreate(**_base_kwargs(name="x" * 81))

    def test_concurrency_and_daily_limit_ranges(self):
        with pytest.raises(ValidationError):
            AutoOutboundTaskCreate(**_base_kwargs(max_concurrency=0))
        with pytest.raises(ValidationError):
            AutoOutboundTaskCreate(**_base_kwargs(daily_per_number_limit=11))

    def test_retry_policy_retry_bounds(self):
        with pytest.raises(ValidationError):
            AutoOutboundTaskCreate(
                **_base_kwargs(
                    retry_policy={"no_answer": {"max_retries": 6, "interval_minutes": 30}}
                )
            )

    def test_wrapup_seconds_bounds_for_agent(self):
        with pytest.raises(ValidationError):
            AutoOutboundTaskCreate(
                **_base_kwargs(
                    execution_mode="agent",
                    voice_flow_id=None,
                    queue_id=5,
                    pacing_mode="progressive",
                    wrapup_seconds=10,
                )
            )

    def test_update_rejects_empty_windows_and_bad_dates(self):
        with pytest.raises(ValidationError):
            AutoOutboundTaskUpdate(daily_time_windows=[])
        with pytest.raises(ValidationError):
            AutoOutboundTaskUpdate(start_date=date(2026, 8, 10), end_date=date(2026, 8, 1))


class TestAutoOutboundTargetAndStatsSchemas:
    def test_target_update_status_whitelist(self):
        ok = AutoOutboundTargetUpdate(status="pending")
        assert ok.status == "pending"
        with pytest.raises(ValidationError):
            AutoOutboundTargetUpdate(status="calling")

    def test_target_update_rejects_naive_next_call_at(self):
        with pytest.raises(ValidationError, match="timezone-aware"):
            AutoOutboundTargetUpdate(next_call_at=datetime(2026, 8, 7, 10, 0))

        ok = AutoOutboundTargetUpdate(
            next_call_at=datetime(2026, 8, 7, 10, 0, tzinfo=timezone.utc)
        )
        assert ok.next_call_at is not None

    def test_task_stats_extended_fields(self):
        stats = AutoOutboundTaskStats(
            total_targets=10,
            finished_targets=2,
            call_count=8,
            answered_count=4,
            answer_rate=0.5,
            transfer_count=1,
            abandon_count=1,
            abandon_rate=0.25,
            current_concurrency=3,
        )
        assert stats.current_concurrency == 3

    def test_target_response_reads_ephemeral_attrs(self):
        row = type(
            "T",
            (),
            {
                "id": 1,
                "tenant_id": 1,
                "task_id": 1,
                "phone_number": "13800138000",
                "user_id": 9,
                "user_name": "用户甲",
                "status": "pending",
                "field_values": {},
                "call_count": 0,
                "answered_count": 0,
                "retry_counts": {},
                "remaining_retries": 2,
                "last_called_at": None,
                "last_call_result": None,
                "next_call_at": None,
                "created_at": None,
                "updated_at": None,
            },
        )()
        resp = AutoOutboundTargetResponse.model_validate(row)
        assert resp.user_name == "用户甲"
        assert resp.remaining_retries == 2

    def test_task_response_includes_auto_pause_reason(self):
        fields = AutoOutboundTaskResponse.model_fields
        assert "auto_pause_reason" in fields
        assert "auto_resume_on_target_append" in fields

    def test_task_list_item_includes_auto_pause_reason(self):
        fields = AutoOutboundTaskListItem.model_fields
        assert "auto_pause_reason" in fields
        item = AutoOutboundTaskListItem(
            id=1,
            name="t",
            execution_mode="ivr",
            status="paused",
            auto_pause_reason="queue_finished",
        )
        assert item.auto_pause_reason == "queue_finished"

    def test_target_responses_expose_auto_resume_result(self):
        assert AutoOutboundTargetResponse.model_fields["task_auto_resumed"].default is False
