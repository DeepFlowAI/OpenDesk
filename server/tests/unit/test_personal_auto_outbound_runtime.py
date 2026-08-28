"""Unit tests for the personal auto-outbound R/S/H runtime."""
import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.libs.telephony import CallEvent
from app.services.personal_auto_outbound_runtime import PersonalAutoOutboundRuntime


class _SessionContext:
    def __init__(self, state: dict | None = None) -> None:
        self.db = AsyncMock()
        self.state = state

    async def __aenter__(self):
        if self.state is not None:
            self.state["active"] += 1
        return self.db

    async def __aexit__(self, exc_type, exc, tb):
        if self.state is not None:
            self.state["active"] -= 1


def _runtime():
    telephony = SimpleNamespace(on_event=Mock(), call_hangup=AsyncMock())
    orchestrator = SimpleNamespace(
        _workflows={},
        _personal_outbound_extensions=set(),
        _claim_call=AsyncMock(return_value=True),
        finalize_outbound_cdr_if_already_ended=AsyncMock(return_value=None),
    )
    return PersonalAutoOutboundRuntime(telephony, orchestrator), telephony


class TestPersonalAutoOutboundRuntime:
    def test_registers_barge_in_and_terminal_events_once(self) -> None:
        runtime, telephony = _runtime()

        runtime.register_events()
        runtime.register_events()

        methods = [call.args[0] for call in telephony.on_event.call_args_list]
        assert methods == [
            "call.ringing",
            "call.answered",
            "call.speech_start",
            "call.speech_end",
            "call.speech_discard",
            "call.play_end",
            "call.hangup",
        ]

    @pytest.mark.asyncio
    async def test_silence_timer_starts_only_after_opening_play_ends(self) -> None:
        runtime, telephony = _runtime()
        call = SimpleNamespace(id=12, stage="ringing")
        session = SimpleNamespace(id=5, opening_audio_asset_id=8, tenant_id=3)
        telephony.call_play = AsyncMock(return_value={"play_id": "play-opening"})
        telephony.call_listen = AsyncMock()

        with (
            patch(
                "app.services.personal_auto_outbound_runtime.AsyncSessionLocal",
                side_effect=lambda: _SessionContext(),
            ),
            patch(
                "app.services.personal_auto_outbound_runtime.PersonalAutoOutboundRepository.get_call_for_update",
                new=AsyncMock(return_value=call),
            ),
            patch(
                "app.services.personal_auto_outbound_runtime.PersonalAutoOutboundRepository.get_session",
                new=AsyncMock(return_value=session),
            ),
            patch(
                "app.services.personal_auto_outbound_runtime.PersonalAutoOutboundRepository.update_call",
                new=AsyncMock(),
            ),
            patch(
                "app.services.personal_auto_outbound_runtime.AudioAssetService.get_managed",
                new=AsyncMock(return_value={"preview_url": "https://audio/opening.wav"}),
            ),
            patch.object(runtime, "_replace_silence_timer") as replace_timer,
        ):
            await runtime._begin_screening("call-a", {"id": 12, "session_id": 5})

            replace_timer.assert_not_called()
            telephony.call_listen.assert_awaited_once_with(
                "call-a",
                adaptive_barge_in=True,
                performance={
                    "turn_detection_enabled": False,
                    "endpoint_silence_ms": 1000,
                    "barge_sensitivity": "sensitive",
                },
            )

            await runtime._on_play_end(
                CallEvent(
                    method="call.play_end",
                    data={"call_id": "call-a", "play_id": "play-opening", "reason": "completed"},
                )
            )
            await asyncio.sleep(0)

            replace_timer.assert_called_once_with("call-a")

    @pytest.mark.asyncio
    async def test_discarded_speech_keeps_playing_and_restarts_silence_timer(self) -> None:
        runtime, telephony = _runtime()
        runtime._opening_ended.add("call-a")
        telephony.call_stop = AsyncMock()
        context = {"id": 12, "session_id": 5, "stage": "screening"}

        with (
            patch.object(runtime, "_lookup", new=AsyncMock(return_value=context)),
            patch.object(runtime, "_replace_silence_timer") as replace_timer,
        ):
            await runtime._on_speech_start(
                CallEvent(method="call.speech_start", data={"call_id": "call-a"})
            )
            replace_timer.assert_not_called()

            await runtime._on_speech_discard(
                CallEvent(method="call.speech_discard", data={"call_id": "call-a"})
            )

            replace_timer.assert_called_once_with("call-a")
            telephony.call_stop.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_adaptive_barge_does_not_stop_on_raw_speech_start(self) -> None:
        runtime, telephony = _runtime()
        telephony.call_stop = AsyncMock()
        context = {"id": 12, "session_id": 5, "stage": "screening"}

        with patch.object(runtime, "_lookup", new=AsyncMock(return_value=context)):
            await runtime._on_speech_start(
                CallEvent(method="call.speech_start", data={"call_id": "call-a"})
            )
            telephony.call_stop.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_closing_audio_accepts_flowkit_interrupted_play_end(self) -> None:
        runtime, telephony = _runtime()
        telephony.call_stop = AsyncMock()
        waiter = asyncio.get_running_loop().create_future()
        runtime._closing_waiters["call-a"] = waiter

        await runtime._on_play_end(
            CallEvent(
                method="call.play_end",
                data={"call_id": "call-a", "reason": "interrupted"},
            )
        )

        telephony.call_stop.assert_not_awaited()
        assert waiter.result() == {"call_id": "call-a", "reason": "interrupted"}

    @pytest.mark.asyncio
    async def test_end_intent_plays_closing_audio_before_hangup(self) -> None:
        runtime, telephony = _runtime()
        telephony.call_play = AsyncMock(return_value={"play_id": "closing-play"})
        decision = SimpleNamespace(
            intent_key="explicit_rejection",
            similarity=0.93,
        )
        call = SimpleNamespace(id=12, stage="screening")
        session = SimpleNamespace(id=5, tenant_id=3, closing_audio_asset_id=9)
        settle = AsyncMock()
        safe_hangup = AsyncMock()
        call_order: list[str] = []

        async def record_stop(call_id: str, *, target: str = "all"):
            call_order.append(f"stop:{target}")

        async def finish_play(call_id: str, *, audio_url: str):
            call_order.append("play")
            asyncio.get_running_loop().call_soon(
                lambda: runtime._closing_waiters[call_id].set_result(
                    {"reason": "completed"}
                )
            )
            return {"play_id": "closing-play"}

        telephony.call_stop = AsyncMock(side_effect=record_stop)
        telephony.call_play = AsyncMock(side_effect=finish_play)
        with (
            patch.object(
                runtime,
                "_lookup",
                new=AsyncMock(return_value={"id": 12, "session_id": 5}),
            ),
            patch(
                "app.services.personal_auto_outbound_runtime.AsyncSessionLocal",
                side_effect=lambda: _SessionContext(),
            ),
            patch(
                "app.services.personal_auto_outbound_runtime.PersonalAutoOutboundRepository.get_call_for_update",
                new=AsyncMock(return_value=call),
            ),
            patch(
                "app.services.personal_auto_outbound_runtime.PersonalAutoOutboundRepository.get_session",
                new=AsyncMock(return_value=session),
            ),
            patch(
                "app.services.personal_auto_outbound_runtime.PersonalAutoOutboundRepository.update_call_and_settle_target",
                new=settle,
            ),
            patch(
                "app.services.personal_auto_outbound_runtime.AudioAssetService.get_managed",
                new=AsyncMock(return_value={"preview_url": "https://audio/closing.wav"}),
            ),
            patch.object(runtime, "_safe_hangup", new=safe_hangup),
        ):
            await runtime._filter_call("call-a", decision)

        settle.assert_awaited_once()
        telephony.call_stop.assert_awaited_once_with("call-a", target="listen")
        telephony.call_play.assert_awaited_once_with(
            "call-a", audio_url="https://audio/closing.wav"
        )
        assert call_order == ["stop:listen", "play"]
        safe_hangup.assert_awaited_once_with(
            "call-a", "personal_prescreen_filtered"
        )

    @pytest.mark.asyncio
    async def test_closing_audio_still_plays_when_stop_listen_fails(self) -> None:
        runtime, telephony = _runtime()
        decision = SimpleNamespace(
            intent_key="explicit_rejection",
            similarity=0.93,
        )
        call = SimpleNamespace(id=12, stage="screening")
        session = SimpleNamespace(id=5, tenant_id=3, closing_audio_asset_id=9)
        settle = AsyncMock()
        safe_hangup = AsyncMock()
        telephony.call_stop = AsyncMock(side_effect=RuntimeError("rpc down"))

        async def finish_play(call_id: str, *, audio_url: str):
            asyncio.get_running_loop().call_soon(
                lambda: runtime._closing_waiters[call_id].set_result(
                    {"reason": "completed"}
                )
            )
            return {"play_id": "closing-play"}

        telephony.call_play = AsyncMock(side_effect=finish_play)
        with (
            patch.object(
                runtime,
                "_lookup",
                new=AsyncMock(return_value={"id": 12, "session_id": 5}),
            ),
            patch(
                "app.services.personal_auto_outbound_runtime.AsyncSessionLocal",
                side_effect=lambda: _SessionContext(),
            ),
            patch(
                "app.services.personal_auto_outbound_runtime.PersonalAutoOutboundRepository.get_call_for_update",
                new=AsyncMock(return_value=call),
            ),
            patch(
                "app.services.personal_auto_outbound_runtime.PersonalAutoOutboundRepository.get_session",
                new=AsyncMock(return_value=session),
            ),
            patch(
                "app.services.personal_auto_outbound_runtime.PersonalAutoOutboundRepository.update_call_and_settle_target",
                new=settle,
            ),
            patch(
                "app.services.personal_auto_outbound_runtime.AudioAssetService.get_managed",
                new=AsyncMock(return_value={"preview_url": "https://audio/closing.wav"}),
            ),
            patch.object(runtime, "_safe_hangup", new=safe_hangup),
        ):
            await runtime._filter_call("call-a", decision)

        telephony.call_play.assert_awaited_once_with(
            "call-a", audio_url="https://audio/closing.wav"
        )
        safe_hangup.assert_awaited_once_with(
            "call-a", "personal_prescreen_filtered"
        )

    @pytest.mark.asyncio
    async def test_successful_hangup_command_finalizes_without_event(self) -> None:
        runtime, telephony = _runtime()
        telephony.call_hangup = AsyncMock()
        finalize = AsyncMock()

        with patch.object(runtime, "_finalize_hangup", new=finalize):
            await runtime._safe_hangup("call-a", "personal_prescreen_filtered")

        telephony.call_hangup.assert_awaited_once_with(
            "call-a", reason="personal_prescreen_filtered"
        )
        finalize.assert_awaited_once_with("call-a", "personal_prescreen_filtered")

    @pytest.mark.asyncio
    async def test_failed_hangup_command_waits_for_event_finalization(self) -> None:
        runtime, telephony = _runtime()
        telephony.call_hangup = AsyncMock(side_effect=RuntimeError("not connected"))
        finalize = AsyncMock()

        with patch.object(runtime, "_finalize_hangup", new=finalize):
            await runtime._safe_hangup("call-a", "personal_prescreen_filtered")

        finalize.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_post_opening_silence_timeout_is_three_seconds(self) -> None:
        runtime, _ = _runtime()
        assign_human = AsyncMock()

        with (
            patch(
                "app.services.personal_auto_outbound_runtime.asyncio.sleep",
                new=AsyncMock(),
            ) as sleep,
            patch.object(runtime, "_assign_human", new=assign_human),
        ):
            await runtime._silence_timeout("call-a")

        sleep.assert_awaited_once_with(3)
        assign_human.assert_awaited_once_with("call-a", degraded_reason="prescreen_timeout")

    @pytest.mark.asyncio
    async def test_non_terminal_turn_assigns_human_immediately(self) -> None:
        runtime, _ = _runtime()
        session = SimpleNamespace(intent_snapshot=[{"intent_key": "reject"}])
        decision = SimpleNamespace(auto_hangup=False, reason="below_threshold")
        assign_human = AsyncMock()

        with (
            patch.object(
                runtime,
                "_lookup",
                new=AsyncMock(return_value={"id": 12, "session_id": 5, "stage": "screening"}),
            ),
            patch(
                "app.services.personal_auto_outbound_runtime.AsyncSessionLocal",
                side_effect=lambda: _SessionContext(),
            ),
            patch(
                "app.services.personal_auto_outbound_runtime.PersonalAutoOutboundRepository.get_session",
                new=AsyncMock(return_value=session),
            ),
            patch(
                "app.services.personal_auto_outbound_runtime.OutboundPrescreenService.classify_snapshot",
                new=AsyncMock(return_value=decision),
            ),
            patch.object(runtime, "_assign_human", new=assign_human),
        ):
            runtime._speech_completed.add("call-a")
            await runtime._classify("call-a", {"text": "请稍等", "voiced_ms": 600})

        assign_human.assert_awaited_once_with(
            "call-a", degraded_reason="below_threshold", last_utterance="请稍等"
        )

    @pytest.mark.asyncio
    async def test_ineligible_utterance_keeps_listening_without_transfer(self) -> None:
        runtime, _ = _runtime()
        session = SimpleNamespace(intent_snapshot=[{"intent_key": "reject"}])
        decision = SimpleNamespace(auto_hangup=False, reason="insufficient_voiced_ms")
        assign_human = AsyncMock()
        filter_call = AsyncMock()

        with (
            patch.object(
                runtime,
                "_lookup",
                new=AsyncMock(return_value={"id": 12, "session_id": 5, "stage": "screening"}),
            ),
            patch(
                "app.services.personal_auto_outbound_runtime.AsyncSessionLocal",
                side_effect=lambda: _SessionContext(),
            ),
            patch(
                "app.services.personal_auto_outbound_runtime.PersonalAutoOutboundRepository.get_session",
                new=AsyncMock(return_value=session),
            ),
            patch(
                "app.services.personal_auto_outbound_runtime.OutboundPrescreenService.classify_snapshot",
                new=AsyncMock(return_value=decision),
            ),
            patch.object(runtime, "_assign_human", new=assign_human),
            patch.object(runtime, "_filter_call", new=filter_call),
        ):
            runtime._speech_completed.add("call-a")
            runtime._opening_ended.add("call-a")
            await runtime._classify("call-a", {"text": "衣服", "voiced_ms": 260})

        assign_human.assert_not_awaited()
        filter_call.assert_not_awaited()
        assert "call-a" not in runtime._speech_completed
        # The silence window restarts so a real reply still gets through.
        assert "call-a" in runtime._silence_tasks
        runtime._silence_tasks["call-a"].cancel()
        runtime._silence_tasks.pop("call-a", None)

    @pytest.mark.asyncio
    async def test_screening_call_closes_replenish_gate(self) -> None:
        runtime, _ = _runtime()
        session = SimpleNamespace(
            id=5,
            tenant_id=3,
            primary_agent_id=7,
            status="running",
            effective_concurrency=4,
        )
        claim = AsyncMock()
        with (
            patch(
                "app.services.personal_auto_outbound_runtime.AsyncSessionLocal",
                side_effect=lambda: _SessionContext(),
            ),
            patch(
                "app.services.personal_auto_outbound_runtime.PersonalAutoOutboundRepository.get_session",
                new=AsyncMock(return_value=session),
            ),
            patch(
                "app.services.personal_auto_outbound_runtime.PersonalAutoOutboundRepository.counts",
                new=AsyncMock(
                    return_value={
                        "ringing_current": 1,
                        "screening_current": 1,
                        "primary_human_current": 0,
                    }
                ),
            ),
            patch(
                "app.services.personal_auto_outbound_runtime.PersonalAutoOutboundRepository.claim_calls",
                new=claim,
            ),
        ):
            await runtime._replenish(5)

        claim.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_replenish_accepts_primary_reservation_owned_by_same_session(self) -> None:
        runtime, _ = _runtime()
        session = SimpleNamespace(
            id=5,
            tenant_id=3,
            primary_agent_id=7,
            status="running",
            effective_concurrency=1,
        )
        counts = {
            "ringing_current": 0,
            "screening_current": 0,
            "primary_human_current": 0,
        }
        claim = AsyncMock(return_value=[])
        auto_pause = AsyncMock()
        finish = AsyncMock()
        with (
            patch(
                "app.services.personal_auto_outbound_runtime.AsyncSessionLocal",
                side_effect=lambda: _SessionContext(),
            ),
            patch(
                "app.services.personal_auto_outbound_runtime.PersonalAutoOutboundRepository.get_session",
                new=AsyncMock(return_value=session),
            ),
            patch(
                "app.services.personal_auto_outbound_runtime.PersonalAutoOutboundRepository.get_session_for_update",
                new=AsyncMock(return_value=session),
            ),
            patch(
                "app.services.personal_auto_outbound_runtime.PersonalAutoOutboundRepository.counts",
                new=AsyncMock(return_value=counts),
            ),
            patch(
                "app.services.personal_auto_outbound_runtime.PersonalAutoOutboundRepository.claim_calls",
                new=claim,
            ),
            patch(
                "app.services.personal_auto_outbound_runtime.CcAgentStatusService.get_for_employee",
                new=AsyncMock(
                    return_value={
                        "status": "busy",
                        "resource_state": "reserved",
                        "current_call_id": "personal-session:5",
                    }
                ),
            ),
            patch.object(runtime, "_ensure_primary_reserved", new=AsyncMock(return_value=True)),
            patch.object(runtime, "_auto_pause", new=auto_pause),
            patch.object(runtime, "_finish_session_if_idle", new=finish),
        ):
            await runtime._replenish(5)

        auto_pause.assert_not_awaited()
        claim.assert_awaited_once()
        finish.assert_awaited_once_with(5, exhaust_running=True)

    @pytest.mark.asyncio
    async def test_stop_releases_db_before_hangup_rpc(self) -> None:
        state = {"active": 0}
        runtime, telephony = _runtime()

        async def hangup(call_id: str, reason: str | None = None):
            assert state["active"] == 0
            assert reason == "personal_session_stopped"

        telephony.call_hangup = hangup
        with (
            patch(
                "app.services.personal_auto_outbound_runtime.AsyncSessionLocal",
                side_effect=lambda: _SessionContext(state),
            ),
            patch(
                "app.services.personal_auto_outbound_runtime.PersonalAutoOutboundRepository.active_call_ids",
                new=AsyncMock(return_value=["call-a", "call-b"]),
            ),
            patch.object(runtime, "_finish_session_if_idle", new=AsyncMock()),
        ):
            await runtime.stop_session(5)

        assert state["active"] == 0

    @pytest.mark.asyncio
    async def test_restore_rebuilds_active_call_timers(self) -> None:
        runtime, _ = _runtime()
        screening = SimpleNamespace(
            id=12,
            session_id=5,
            telephony_call_id="call-live",
            stage="screening",
            started_at=datetime.now(timezone.utc),
        )
        with (
            patch(
                "app.services.personal_auto_outbound_runtime.AsyncSessionLocal",
                side_effect=lambda: _SessionContext(),
            ),
            patch(
                "app.services.personal_auto_outbound_runtime.PersonalAutoOutboundRepository.list_running_session_ids",
                new=AsyncMock(return_value=[5]),
            ),
            patch(
                "app.services.personal_auto_outbound_runtime.PersonalAutoOutboundRepository.list_active_calls",
                new=AsyncMock(return_value=[screening]),
            ),
            patch.object(runtime, "_replace_silence_timer") as replace_timer,
            patch.object(runtime, "_schedule_replenish") as replenish,
        ):
            await runtime.restore_running_sessions({"call-live"}, complete=True)

        assert runtime._call_rows == {"call-live": 12}
        assert runtime._session_by_call == {"call-live": 5}
        replace_timer.assert_called_once_with("call-live")
        replenish.assert_called_once_with(5)

    @pytest.mark.asyncio
    async def test_lookup_recovers_mapping_from_database(self) -> None:
        runtime, _ = _runtime()
        row = SimpleNamespace(
            id=12,
            session_id=5,
            tenant_id=3,
            task_id=8,
            target_id=9,
            phone_number="10086",
            stage="ringing",
        )
        with (
            patch(
                "app.services.personal_auto_outbound_runtime.AsyncSessionLocal",
                side_effect=lambda: _SessionContext(),
            ),
            patch(
                "app.services.personal_auto_outbound_runtime.PersonalAutoOutboundRepository.get_call_by_telephony_id",
                new=AsyncMock(return_value=row),
            ),
        ):
            result = await runtime._lookup("call-restored")

        assert result["id"] == 12
        assert runtime._call_rows["call-restored"] == 12

    @pytest.mark.asyncio
    async def test_dial_does_not_overwrite_terminal_call_after_fast_hangup(self) -> None:
        runtime, telephony = _runtime()
        call = SimpleNamespace(
            id=12,
            session_id=5,
            phone_number="10086",
            stage="dialing",
        )
        terminal = SimpleNamespace(id=12, stage="not_connected", ended_at=datetime.now(timezone.utc))
        terminal.telephony_call_id = None
        terminal.call_record_id = None
        session = SimpleNamespace(
            id=5,
            tenant_id=3,
            status="running",
            outbound_phone_number_id="pn-1",
        )
        number = SimpleNamespace(
            trunk_id="trunk-1",
            called_number_prefix="",
            phone_number="0210000",
        )
        telephony.call_originate = AsyncMock(return_value={"call_id": "call-fast"})
        update = AsyncMock()
        contexts = [_SessionContext(), _SessionContext(), _SessionContext()]
        contexts[0].db.get = AsyncMock(return_value=number)
        with (
            patch(
                "app.services.personal_auto_outbound_runtime.AsyncSessionLocal",
                side_effect=contexts,
            ),
            patch(
                "app.services.personal_auto_outbound_runtime.PersonalAutoOutboundRepository.get_call",
                new=AsyncMock(return_value=call),
            ),
            patch(
                "app.services.personal_auto_outbound_runtime.PersonalAutoOutboundRepository.get_session",
                new=AsyncMock(return_value=session),
            ),
            patch(
                "app.services.personal_auto_outbound_runtime.CallRecordService.create_for_outbound",
                new=AsyncMock(return_value={"id": 99}),
            ),
            patch(
                "app.services.personal_auto_outbound_runtime.PersonalAutoOutboundRepository.get_call_for_update",
                new=AsyncMock(return_value=terminal),
            ),
            patch(
                "app.services.personal_auto_outbound_runtime.PersonalAutoOutboundRepository.update_call",
                new=update,
            ),
        ):
            await runtime._dial(12)

        update.assert_awaited_once()
        assert update.await_args.args[2] == {
            "telephony_call_id": "call-fast",
            "call_record_id": 99,
        }
        orchestrator = runtime.orchestrator
        assert orchestrator.finalize_outbound_cdr_if_already_ended.await_count == 4
        orchestrator.finalize_outbound_cdr_if_already_ended.assert_awaited_with(
            contexts[1].db, tenant_id=3, call_id="call-fast"
        )

    @pytest.mark.asyncio
    async def test_dial_sip_target_uses_configured_outbound_trunk(self) -> None:
        runtime, telephony = _runtime()
        call = SimpleNamespace(
            id=12,
            session_id=5,
            phone_number="sip:tenant-9001",
            stage="dialing",
            ended_at=None,
            telephony_call_id=None,
            call_record_id=None,
        )
        session = SimpleNamespace(
            id=5,
            tenant_id=3,
            status="running",
            outbound_phone_number_id="pn-1",
        )
        telephony.call_originate = AsyncMock(return_value={"call_id": "call-sip"})
        contexts = [_SessionContext(), _SessionContext(), _SessionContext()]
        number = SimpleNamespace(
            trunk_id="trunk-vsp",
            called_number_prefix="",
            phone_number="9000001",
        )
        contexts[0].db.get = AsyncMock(return_value=number)

        with (
            patch(
                "app.services.personal_auto_outbound_runtime.AsyncSessionLocal",
                side_effect=contexts,
            ),
            patch(
                "app.services.personal_auto_outbound_runtime.PersonalAutoOutboundRepository.get_call",
                new=AsyncMock(return_value=call),
            ),
            patch(
                "app.services.personal_auto_outbound_runtime.PersonalAutoOutboundRepository.get_session",
                new=AsyncMock(return_value=session),
            ),
            patch(
                "app.services.personal_auto_outbound_runtime.CallRecordService.create_for_outbound",
                new=AsyncMock(return_value={"id": 99}),
            ) as create_cdr,
            patch(
                "app.services.personal_auto_outbound_runtime.PersonalAutoOutboundRepository.get_call_for_update",
                new=AsyncMock(return_value=call),
            ),
            patch(
                "app.services.personal_auto_outbound_runtime.PersonalAutoOutboundRepository.update_call",
                new=AsyncMock(),
            ),
        ):
            await runtime._dial(12)

        telephony.call_originate.assert_awaited_once_with(
            uri="tenant-9001",
            caller_id="9000001",
            trunk_id="trunk-vsp",
            request_id="pao:12",
        )
        assert create_cdr.await_args.kwargs["to_number"] == "sip:tenant-9001"

    @pytest.mark.asyncio
    async def test_dial_retries_late_early_failure_before_leaving_cdr_active(self) -> None:
        runtime, telephony = _runtime()
        call = SimpleNamespace(
            id=12,
            session_id=5,
            phone_number="0210001",
            stage="dialing",
            ended_at=None,
            telephony_call_id=None,
            call_record_id=None,
        )
        session = SimpleNamespace(
            id=5,
            tenant_id=3,
            status="running",
            outbound_phone_number_id="pn-1",
        )
        number = SimpleNamespace(
            trunk_id="trunk-1",
            called_number_prefix="",
            phone_number="9000001",
        )
        telephony.call_originate = AsyncMock(return_value={"call_id": "call-fast"})
        runtime.orchestrator.finalize_outbound_cdr_if_already_ended = AsyncMock(
            side_effect=[None, None, ("rejected", 404)]
        )
        contexts = [_SessionContext(), _SessionContext(), _SessionContext()]
        contexts[0].db.get = AsyncMock(return_value=number)

        with (
            patch(
                "app.services.personal_auto_outbound_runtime.AsyncSessionLocal",
                side_effect=contexts,
            ),
            patch(
                "app.services.personal_auto_outbound_runtime.PersonalAutoOutboundRepository.get_call",
                new=AsyncMock(return_value=call),
            ),
            patch(
                "app.services.personal_auto_outbound_runtime.PersonalAutoOutboundRepository.get_session",
                new=AsyncMock(return_value=session),
            ),
            patch(
                "app.services.personal_auto_outbound_runtime.CallRecordService.create_for_outbound",
                new=AsyncMock(return_value={"id": 99}),
            ),
            patch(
                "app.services.personal_auto_outbound_runtime.PersonalAutoOutboundRepository.get_call_for_update",
                new=AsyncMock(return_value=call),
            ),
            patch(
                "app.services.personal_auto_outbound_runtime.PersonalAutoOutboundRepository.update_call",
                new=AsyncMock(),
            ),
            patch("app.services.personal_auto_outbound_runtime.asyncio.sleep", new=AsyncMock()),
        ):
            await runtime._dial(12)

        assert runtime.orchestrator.finalize_outbound_cdr_if_already_ended.await_count == 3

    @pytest.mark.asyncio
    async def test_hangup_uses_atomic_call_and_target_settlement(self) -> None:
        runtime, _ = _runtime()
        runtime._call_rows["call-a"] = 12
        call = SimpleNamespace(
            id=12,
            session_id=5,
            stage="ringing",
            ended_at=None,
            metadata_json={"previous_target_status": "pending"},
            prescreen_result=None,
            hangup_reason=None,
            answered_at=None,
            assigned_agent_id=None,
            telephony_call_id="call-a",
        )
        atomic_update = AsyncMock()
        with (
            patch(
                "app.services.personal_auto_outbound_runtime.AsyncSessionLocal",
                side_effect=lambda: _SessionContext(),
            ),
            patch.object(
                runtime,
                "_lookup",
                new=AsyncMock(return_value={"id": 12, "session_id": 5}),
            ),
            patch(
                "app.services.personal_auto_outbound_runtime.PersonalAutoOutboundRepository.get_call_for_update",
                new=AsyncMock(return_value=call),
            ),
            patch(
                "app.services.personal_auto_outbound_runtime.PersonalAutoOutboundRepository.update_call_and_settle_target",
                new=atomic_update,
            ),
            patch.object(runtime, "_finish_session_if_idle", new=AsyncMock()),
            patch.object(runtime, "_schedule_replenish"),
        ):
            await runtime._finalize_hangup("call-a", "normal_clearing")

        assert atomic_update.await_count == 1
        assert atomic_update.await_args.kwargs == {
            "target_status": "pending",
            "result": "not_connected",
            "answered": False,
        }

@pytest.mark.asyncio
async def test_assign_human_graph_disables_transfer_prompt() -> None:
    """The inline assign graph built by _assign_human carries
    queue_prompt_text="" so the callee hears no transfer TTS before the agent."""
    runtime, telephony = _runtime()
    telephony.call_stop = AsyncMock()

    context = {
        "id": 1,
        "session_id": 2,
        "tenant_id": 7,
        "task_id": 3,
        "target_id": 4,
        "phone_number": "13800000000",
        "stage": "screening",
    }
    call_screening = SimpleNamespace(id=1, stage="screening")
    call_assigning = SimpleNamespace(id=1, stage="assigning", ended_at=None)
    session = SimpleNamespace(
        tenant_id=7, primary_agent_id=11, fallback_group_id=22, task_id=3,
    )

    class _FakeWorkflow:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.done = asyncio.Event()
            self.ended_reason = None

        async def start(self):
            self.done.set()

        def bridged_agent_info(self):
            return None

    with (
        patch.object(runtime, "_lookup", new=AsyncMock(return_value=context)),
        patch(
            "app.services.personal_auto_outbound_runtime.AsyncSessionLocal",
            return_value=_SessionContext(),
        ),
        patch(
            "app.services.personal_auto_outbound_runtime.PersonalAutoOutboundRepository"
        ) as repo,
        patch(
            "app.services.personal_auto_outbound_runtime.VoiceFlowWorkflow",
            _FakeWorkflow,
        ),
        patch.object(runtime, "_release_primary", new=AsyncMock()),
        patch.object(runtime, "_safe_hangup", new=AsyncMock()),
        patch.object(runtime, "_finish_session_if_idle", new=AsyncMock()),
        patch.object(runtime, "_schedule_replenish", new=Mock()),
    ):
        repo.get_call_for_update = AsyncMock(
            side_effect=[call_screening, call_assigning, call_assigning]
        )
        repo.get_session = AsyncMock(return_value=session)
        repo.update_call = AsyncMock()
        repo.update_call_and_settle_target = AsyncMock()

        await runtime._assign_human("call-x")

    workflow = runtime.orchestrator._workflows["call-x"]
    graph = workflow.kwargs["graph"]
    assign_node = next(n for n in graph["nodes"] if n["type"] == "assign_queue")
    assert assign_node["data"]["queue_prompt_text"] == ""
