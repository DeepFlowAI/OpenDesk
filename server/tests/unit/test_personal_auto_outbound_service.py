"""Unit tests for personal auto-outbound recording and start validation."""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.schemas.permission import EffectivePrincipal
from app.schemas.personal_auto_outbound import PersonalAutoOutboundStartRequest
from app.schemas.auto_outbound import AutoOutboundWrapupRequest
from app.core.exceptions import ConflictError, ForbiddenError, ValidationError
from app.services.personal_auto_outbound_service import PersonalAutoOutboundService


def _principal() -> EffectivePrincipal:
    return EffectivePrincipal(
        user_id=7,
        tenant_id=3,
        permissions=["call.workspace.use", "call.personal_auto_outbound.use"],
        group_ids=[],
    )


class _SessionContext:
    def __init__(self, state: dict | None = None) -> None:
        self.state = state
        self.db = AsyncMock()

    async def __aenter__(self):
        if self.state is not None:
            self.state["active"] += 1
        return self.db

    async def __aexit__(self, exc_type, exc, tb):
        if self.state is not None:
            self.state["active"] -= 1


class TestPersonalAutoOutboundService:
    @pytest.mark.asyncio
    async def test_assigned_fallback_agent_can_open_business_context(self) -> None:
        call = SimpleNamespace(id=4, tenant_id=3, session_id=8, assigned_agent_id=7)
        session = SimpleNamespace(id=8, primary_agent_id=5)
        with (
            patch(
                "app.services.personal_auto_outbound_service.PersonalAutoOutboundRepository.get_call",
                new=AsyncMock(return_value=call),
            ),
            patch(
                "app.services.personal_auto_outbound_service.PersonalAutoOutboundRepository.get_session",
                new=AsyncMock(return_value=session),
            ),
        ):
            result = await PersonalAutoOutboundService._authorized_business_call(
                AsyncMock(), _principal(), 4
            )

        assert result == (call, session)

    @pytest.mark.asyncio
    async def test_unassigned_agent_cannot_open_business_context(self) -> None:
        call = SimpleNamespace(id=4, tenant_id=3, session_id=8, assigned_agent_id=9)
        session = SimpleNamespace(id=8, primary_agent_id=5)
        with (
            patch(
                "app.services.personal_auto_outbound_service.PersonalAutoOutboundRepository.get_call",
                new=AsyncMock(return_value=call),
            ),
            patch(
                "app.services.personal_auto_outbound_service.PersonalAutoOutboundRepository.get_session",
                new=AsyncMock(return_value=session),
            ),
        ):
            with pytest.raises(ForbiddenError):
                await PersonalAutoOutboundService._authorized_business_call(
                    AsyncMock(), _principal(), 4
                )

    def test_concurrency_range_is_enforced(self) -> None:
        with pytest.raises(PydanticValidationError):
            PersonalAutoOutboundStartRequest(
                task_id=1,
                outbound_phone_number_id="pn-1",
                configured_concurrency=11,
            )

    @pytest.mark.asyncio
    async def test_upload_does_not_hold_db_session_during_storage_io(self) -> None:
        state = {"active": 0}

        async def upload(*args, **kwargs):
            assert state["active"] == 0
            return {
                "id": 41,
                "name": "opening.mp3",
                "mime_type": "audio/mpeg",
                "size_bytes": 3,
                "duration_ms": None,
                "preview_url": "https://example.test/audio",
                "created_at": datetime.now(timezone.utc),
            }

        replace = AsyncMock(return_value=SimpleNamespace(script_text="已有开场白"))
        with (
            patch(
                "app.services.personal_auto_outbound_service.AsyncSessionLocal",
                side_effect=lambda: _SessionContext(state),
            ),
            patch(
                "app.services.personal_auto_outbound_service.PersonalAutoOutboundRepository.get_current_session",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.services.personal_auto_outbound_service.PersonalAutoOutboundRepository.replace_recording",
                new=replace,
            ),
            patch(
                "app.services.personal_auto_outbound_service.AudioAssetService.upload_managed",
                new=upload,
            ),
        ):
            response = await PersonalAutoOutboundService.upload_recording_managed(
                _principal(),
                "opening",
                filename="opening.mp3",
                content_type="audio/mpeg",
                data=b"ID3",
            )

        assert state["active"] == 0
        assert response["audio"]["id"] == 41
        assert response["script_text"] == "已有开场白"
        assert replace.await_args.args[1:4] == (3, 7, "opening")

    @pytest.mark.asyncio
    async def test_existing_session_is_returned_idempotently(self) -> None:
        existing = SimpleNamespace(id=91, status="running")
        with (
            patch(
                "app.services.personal_auto_outbound_service.AsyncSessionLocal",
                side_effect=lambda: _SessionContext(),
            ),
            patch(
                "app.services.personal_auto_outbound_service.PersonalAutoOutboundRepository.get_current_session",
                new=AsyncMock(return_value=existing),
            ),
        ):
            result = await PersonalAutoOutboundService.start_session_managed(
                _principal(),
                PersonalAutoOutboundStartRequest(
                    task_id=1,
                    outbound_phone_number_id="pn-1",
                ),
            )

        assert result is existing

    @pytest.mark.asyncio
    async def test_no_ready_fallback_lowers_effective_concurrency_to_one(self) -> None:
        intent = SimpleNamespace(id=8, intent_key="reject", name="Reject", enabled=True, similarity_threshold=0.86)
        example = SimpleNamespace(
            intent_id=8,
            embedding_status="ready",
            embedding=[1.0, 0.0],
            example_type="positive",
            text="No thanks",
        )
        recordings = [
            SimpleNamespace(recording_type="opening", audio_asset_id=11, script_text="  您好  "),
            SimpleNamespace(recording_type="closing", audio_asset_id=12),
        ]
        created = SimpleNamespace(id=101)
        create = AsyncMock(return_value=created)

        with (
            patch(
                "app.services.personal_auto_outbound_service.AsyncSessionLocal",
                side_effect=lambda: _SessionContext(),
            ),
            patch(
                "app.services.personal_auto_outbound_service.PersonalAutoOutboundRepository.get_current_session",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.services.personal_auto_outbound_service.CcAgentStatusService.get_for_employee",
                new=AsyncMock(return_value={"status": "ready", "resource_state": "idle"}),
            ),
            patch(
                "app.services.personal_auto_outbound_service.AgentCallDeviceService.get_current_device",
                new=AsyncMock(return_value={"device_type": "webrtc", "available": True}),
            ),
            patch(
                "app.services.personal_auto_outbound_service.PersonalAutoOutboundRepository.get_task_option",
                new=AsyncMock(return_value={"id": 1, "callable_count": 2}),
            ),
            patch(
                "app.services.personal_auto_outbound_service.TenantPhoneNumberService._tenant_string_id",
                new=AsyncMock(return_value="tenant-3"),
            ),
            patch(
                "app.services.personal_auto_outbound_service.TenantPhoneNumberRepository.get_assigned_by_id",
                new=AsyncMock(return_value=SimpleNamespace(call_types=["outbound"])),
            ),
            patch(
                "app.services.personal_auto_outbound_service.PersonalAutoOutboundRepository.list_recordings",
                new=AsyncMock(return_value=recordings),
            ),
            patch(
                "app.services.personal_auto_outbound_service.OutboundPrescreenRepository.list_config",
                new=AsyncMock(return_value=([intent], [example])),
            ),
            patch.object(
                PersonalAutoOutboundService,
                "_ready_fallback_count",
                new=AsyncMock(return_value=0),
            ),
            patch(
                "app.services.personal_auto_outbound_service.PersonalAutoOutboundRepository.create_session",
                new=create,
            ),
        ):
            result = await PersonalAutoOutboundService.start_session_managed(
                _principal(),
                PersonalAutoOutboundStartRequest(
                    task_id=1,
                    outbound_phone_number_id="pn-1",
                    configured_concurrency=4,
                ),
            )

        assert result is created
        assert create.await_args.args[1]["effective_concurrency"] == 1
        assert create.await_args.args[1]["opening_script_text"] == "您好"

    @pytest.mark.asyncio
    async def test_manual_wrapup_can_replace_backend_auto_submit(self) -> None:
        call = SimpleNamespace(
            id=4,
            tenant_id=3,
            session_id=8,
            assigned_agent_id=7,
            ended_at=datetime.now(timezone.utc),
            target_id=9,
            metadata_json={
                "wrapup_submitted": True,
                "wrapup": {"field_values": {}, "auto_submitted": True},
            },
        )
        session = SimpleNamespace(id=8, primary_agent_id=5)
        target = SimpleNamespace(id=9, field_values={"name": "old"}, status="redial")
        context = _SessionContext()
        context.db.get = AsyncMock(return_value=target)
        with (
            patch(
                "app.services.personal_auto_outbound_service.AsyncSessionLocal",
                return_value=context,
            ),
            patch.object(
                PersonalAutoOutboundService,
                "_authorized_business_call",
                new=AsyncMock(return_value=(call, session)),
            ),
            patch(
                "app.services.personal_auto_outbound_service.PersonalAutoOutboundRepository.get_call_for_update",
                new=AsyncMock(return_value=call),
            ),
        ):
            result = await PersonalAutoOutboundService.submit_wrapup_managed(
                _principal(),
                4,
                AutoOutboundWrapupRequest(field_values={"name": "new"}),
            )

        assert result["field_values"] == {"name": "new"}
        assert target.status == "completed"
        assert call.metadata_json["wrapup"]["auto_submitted"] is False
        context.db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_save_opening_script_strips_and_persists(self) -> None:
        row = SimpleNamespace(audio_asset_id=11, script_text="您好")
        update = AsyncMock(return_value=row)
        with (
            patch(
                "app.services.personal_auto_outbound_service.AsyncSessionLocal",
                side_effect=lambda: _SessionContext(),
            ),
            patch(
                "app.services.personal_auto_outbound_service.PersonalAutoOutboundRepository.get_current_session",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.services.personal_auto_outbound_service.PersonalAutoOutboundRepository.get_recording",
                new=AsyncMock(return_value=row),
            ),
            patch(
                "app.services.personal_auto_outbound_service.PersonalAutoOutboundRepository.update_recording_script",
                new=update,
            ),
            patch(
                "app.services.personal_auto_outbound_service.AudioAssetService.get_managed",
                new=AsyncMock(return_value={"id": 11}),
            ),
        ):
            result = await PersonalAutoOutboundService.save_opening_script_managed(
                _principal(), "  您好  "
            )

        assert result["script_text"] == "您好"
        assert update.await_args.args[2] == "您好"

    @pytest.mark.asyncio
    async def test_save_opening_script_rejects_when_session_active(self) -> None:
        with (
            patch(
                "app.services.personal_auto_outbound_service.AsyncSessionLocal",
                side_effect=lambda: _SessionContext(),
            ),
            patch(
                "app.services.personal_auto_outbound_service.PersonalAutoOutboundRepository.get_current_session",
                new=AsyncMock(return_value=SimpleNamespace(id=1)),
            ),
        ):
            with pytest.raises(ConflictError):
                await PersonalAutoOutboundService.save_opening_script_managed(_principal(), "您好")

    @pytest.mark.asyncio
    async def test_save_opening_script_rejects_over_200_chars(self) -> None:
        with pytest.raises(ValidationError):
            await PersonalAutoOutboundService.save_opening_script_managed(_principal(), "啊" * 201)
