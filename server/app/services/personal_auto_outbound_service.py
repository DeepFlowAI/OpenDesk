"""Agent-owned recording and session configuration for personal auto-outbound."""
from datetime import datetime, timezone

import redis.asyncio as aioredis
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.db.session import AsyncSessionLocal
from app.repositories.employee_group_repository import EmployeeGroupRepository
from app.repositories.outbound_prescreen_repository import OutboundPrescreenRepository
from app.repositories.personal_auto_outbound_repository import PersonalAutoOutboundRepository
from app.repositories.tenant_phone_number_repository import TenantPhoneNumberRepository
from app.models.outbound_task import OutboundTask, OutboundTaskTarget
from app.models.user import User
from app.schemas.auto_outbound import (
    AutoOutboundAgentContextRecord,
    AutoOutboundAgentContextResponse,
    AutoOutboundWrapupRequest,
)
from app.schemas.outbound_task import OutboundTaskField
from app.schemas.permission import EffectivePrincipal
from app.schemas.personal_auto_outbound import PersonalAutoOutboundStartRequest
from app.services.audio_asset_service import AudioAssetService
from app.services.agent_call_device_service import AgentCallDeviceService
from app.services.cc_agent_status_service import CcAgentStatusService
from app.services.system_settings_service import SystemSettingsService
from app.services.tenant_phone_number_service import TenantPhoneNumberService

RECORDING_TYPES = {"opening", "closing"}
PERSONAL_AUTO_OUTBOUND_WRAPUP_SECONDS = 60


class PersonalAutoOutboundService:
    @staticmethod
    async def _authorized_business_call(db, principal: EffectivePrincipal, call_id: int):
        call = await PersonalAutoOutboundRepository.get_call(db, call_id)
        if call is None or call.tenant_id != principal.tenant_id:
            raise NotFoundError("Personal auto-outbound call not found")
        session = await PersonalAutoOutboundRepository.get_session(db, call.session_id)
        if session is None:
            raise NotFoundError("Personal auto-outbound session not found")
        allowed = session.primary_agent_id == principal.user_id or call.assigned_agent_id == principal.user_id
        if not allowed:
            raise ForbiddenError("Only the primary or assigned agent can view this call")
        return call, session

    @staticmethod
    async def get_business_context_managed(
        principal: EffectivePrincipal, call_id: int
    ) -> AutoOutboundAgentContextResponse:
        async with AsyncSessionLocal() as db:
            call, _session = await PersonalAutoOutboundService._authorized_business_call(
                db, principal, call_id
            )
            task = await db.get(OutboundTask, call.task_id)
            target = await db.get(OutboundTaskTarget, call.target_id)
            if task is None or target is None:
                raise NotFoundError("Outbound task target not found")
            fields: list[OutboundTaskField] = []
            for raw in task.fields or []:
                try:
                    fields.append(OutboundTaskField.model_validate(raw))
                except Exception:  # noqa: BLE001
                    continue
            metadata = dict(call.metadata_json or {})
            reception_result = metadata.get("wrapup")
            user = await db.get(User, target.user_id) if target.user_id else None
            try:
                settings = await SystemSettingsService.get_settings(db, principal.tenant_id)
                wrapup_seconds = int(settings.call_wrapup_seconds)
            except Exception:  # noqa: BLE001
                wrapup_seconds = PERSONAL_AUTO_OUTBOUND_WRAPUP_SECONDS
            return AutoOutboundAgentContextResponse(
                task_id=task.id,
                task_name=task.name,
                template_name=task.template_name,
                fields=fields,
                wrapup_seconds=wrapup_seconds,
                record=AutoOutboundAgentContextRecord(
                    id=call.id,
                    target_id=target.id,
                    field_values=dict(target.field_values or {}),
                    reception_result=reception_result if isinstance(reception_result, dict) else None,
                ),
                opening_script_text=getattr(_session, "opening_script_text", None),
                last_utterance=getattr(call, "last_utterance", None),
                target_name=getattr(user, "name", None),
                target_phone=call.phone_number,
                assignment_type=call.assignment_type,
            )

    @staticmethod
    async def submit_wrapup_managed(
        principal: EffectivePrincipal,
        call_id: int,
        body: AutoOutboundWrapupRequest,
    ) -> dict:
        async with AsyncSessionLocal() as db:
            authorized_call, _session = await PersonalAutoOutboundService._authorized_business_call(
                db, principal, call_id
            )
            call = await PersonalAutoOutboundRepository.get_call_for_update(
                db, authorized_call.id
            )
            if call is None:
                raise NotFoundError("Personal auto-outbound call not found")
            if call.assigned_agent_id != principal.user_id:
                raise ForbiddenError("Only the assigned agent can submit wrap-up")
            if call.ended_at is None:
                raise ValidationError("Call has not ended yet")
            metadata = dict(call.metadata_json or {})
            previous_wrapup = metadata.get("wrapup")
            if metadata.get("wrapup_submitted") and not (
                isinstance(previous_wrapup, dict)
                and previous_wrapup.get("auto_submitted") is True
            ):
                raise ValidationError("Wrap-up already submitted")
            field_values = body.field_values
            if field_values is None:
                nested = body.reception_result.get("field_values")
                field_values = nested if isinstance(nested, dict) else {}
            target = await db.get(OutboundTaskTarget, call.target_id)
            if target is None:
                raise NotFoundError("Outbound task target not found")
            merged = dict(target.field_values or {})
            merged.update(field_values or {})
            target.field_values = merged
            target.status = "completed"
            metadata["wrapup_submitted"] = True
            metadata["wrapup"] = {
                **dict(body.reception_result or {}),
                "field_values": field_values or {},
                "auto_submitted": False,
                "submitted_by": principal.user_id,
                "submitted_at": datetime.now(timezone.utc).isoformat(),
            }
            call.metadata_json = metadata
            await db.commit()
            return {"id": call.id, "target_id": target.id, "field_values": merged}

    @staticmethod
    async def _ready_fallback_count(db, principal: EffectivePrincipal, group_id: int | None, r: aioredis.Redis | None) -> int:
        if group_id is None or group_id not in principal.group_ids:
            return 0
        group = await EmployeeGroupRepository.get_by_id(db, group_id)
        if group is None or group.tenant_id != principal.tenant_id:
            return 0
        agents = await CcAgentStatusService.list_consultable_agents(
            db, principal.tenant_id, principal.user_id, None, r
        )
        return sum(
            1
            for agent in agents
            if agent["status"] == "ready" and group.name in agent["group_names"]
        )

    @staticmethod
    async def get_config_managed(principal: EffectivePrincipal, r: aioredis.Redis | None = None) -> dict:
        recording_ids: dict[str, int] = {}
        script_by_type: dict[str, str | None] = {}
        async with AsyncSessionLocal() as db:
            tasks = await PersonalAutoOutboundRepository.list_task_options(
                db, principal.tenant_id, principal.user_id
            )
            tenant_string_id = await TenantPhoneNumberService._tenant_string_id(db, principal.tenant_id)
            phone_rows = await TenantPhoneNumberRepository.list_assigned(
                db, tenant_string_id, offset=0, limit=200
            )
            phones = [
                {"id": row.id, "phone_number": row.phone_number}
                for row in phone_rows
                if "outbound" in (row.call_types or [])
            ]
            groups = await EmployeeGroupRepository.list_filter_options(
                db, principal.tenant_id, principal.group_ids
            )
            fallback_groups = []
            for group in groups:
                fallback_groups.append(
                    {
                        "id": group.id,
                        "name": group.name,
                        "ready_agent_count": await PersonalAutoOutboundService._ready_fallback_count(
                            db, principal, group.id, r
                        ),
                    }
                )
            for row in await PersonalAutoOutboundRepository.list_recordings(
                db, principal.tenant_id, principal.user_id
            ):
                recording_ids[row.recording_type] = row.audio_asset_id
                script_by_type[row.recording_type] = getattr(row, "script_text", None)
            intents, examples = await OutboundPrescreenRepository.list_config(db, principal.tenant_id)
            examples_by_intent: dict[int, list] = {}
            for example in examples:
                examples_by_intent.setdefault(example.intent_id, []).append(example)
            has_enabled_prescreen_intents = any(
                intent.enabled
                and examples_by_intent.get(intent.id)
                and all(
                    example.embedding_status == "ready" and example.embedding is not None
                    for example in examples_by_intent[intent.id]
                )
                for intent in intents
            )

        recordings = {}
        for recording_type, asset_id in recording_ids.items():
            recordings[recording_type] = {
                "recording_type": recording_type,
                "audio": await AudioAssetService.get_managed(asset_id, principal.tenant_id),
                "script_text": script_by_type.get(recording_type) if recording_type == "opening" else None,
            }
        return {
            "tasks": tasks,
            "phone_numbers": phones,
            "fallback_groups": fallback_groups,
            "recordings": recordings,
            "has_enabled_prescreen_intents": has_enabled_prescreen_intents,
        }

    @staticmethod
    async def upload_recording_managed(
        principal: EffectivePrincipal,
        recording_type: str,
        *,
        filename: str,
        content_type: str | None,
        data: bytes,
    ) -> dict:
        if recording_type not in RECORDING_TYPES:
            raise NotFoundError("Recording type not found")
        async with AsyncSessionLocal() as db:
            if await PersonalAutoOutboundRepository.get_current_session(
                db, principal.tenant_id, principal.user_id
            ):
                raise ConflictError("Recording cannot be replaced while a session is active")

        audio = await AudioAssetService.upload_managed(
            principal.tenant_id,
            principal.user_id,
            filename=filename,
            content_type=content_type,
            data=data,
        )
        async with AsyncSessionLocal() as db:
            row = await PersonalAutoOutboundRepository.replace_recording(
                db,
                principal.tenant_id,
                principal.user_id,
                recording_type,
                audio["id"],
            )
            script_text = getattr(row, "script_text", None) if recording_type == "opening" else None
        return {"recording_type": recording_type, "audio": audio, "script_text": script_text}

    @staticmethod
    async def save_opening_script_managed(principal: EffectivePrincipal, script_text: str | None) -> dict:
        cleaned = (script_text or "").strip()
        if len(cleaned) > 200:
            raise ValidationError("Opening script must be at most 200 characters")
        value = cleaned or None
        async with AsyncSessionLocal() as db:
            if await PersonalAutoOutboundRepository.get_current_session(
                db, principal.tenant_id, principal.user_id
            ):
                raise ConflictError("Opening script cannot be changed while a session is active")
            row = await PersonalAutoOutboundRepository.get_recording(
                db, principal.tenant_id, principal.user_id, "opening", include_inactive=True
            )
            if row is None:
                raise NotFoundError("Opening recording not found")
            row = await PersonalAutoOutboundRepository.update_recording_script(db, row, value)
            asset_id = row.audio_asset_id
            saved = row.script_text
        return {
            "recording_type": "opening",
            "audio": await AudioAssetService.get_managed(asset_id, principal.tenant_id),
            "script_text": saved,
        }

    @staticmethod
    async def remove_recording_managed(principal: EffectivePrincipal, recording_type: str) -> None:
        if recording_type not in RECORDING_TYPES:
            raise NotFoundError("Recording type not found")
        async with AsyncSessionLocal() as db:
            if await PersonalAutoOutboundRepository.get_current_session(
                db, principal.tenant_id, principal.user_id
            ):
                raise ConflictError("Recording cannot be removed while a session is active")
            row = await PersonalAutoOutboundRepository.get_recording(
                db, principal.tenant_id, principal.user_id, recording_type
            )
            if row is None:
                raise NotFoundError("Recording not found")
            await PersonalAutoOutboundRepository.remove_recording(db, row)

    @staticmethod
    async def get_current_session_managed(principal: EffectivePrincipal) -> dict:
        async with AsyncSessionLocal() as db:
            session = await PersonalAutoOutboundRepository.get_current_session(
                db, principal.tenant_id, principal.user_id
            )
            if session is None:
                return {"session": None, "metrics": {}, "calls": [], "gate_reason": None}
            metrics = await PersonalAutoOutboundRepository.counts(db, session.id)
            calls = await PersonalAutoOutboundRepository.list_calls(db, session.id)
        if session.status != "running":
            gate_reason = session.pause_reason or session.status
        elif metrics["screening_current"] > 0:
            gate_reason = "screening"
        elif metrics["primary_human_current"] > 0:
            gate_reason = "primary_human"
        else:
            gate_reason = None
        metrics.pop("primary_human_current", None)
        return {"session": session, "metrics": metrics, "calls": calls, "gate_reason": gate_reason}

    @staticmethod
    async def control_session_managed(
        principal: EffectivePrincipal,
        session_id: int,
        action: str,
        r: aioredis.Redis | None = None,
    ):
        if action not in {"pause", "resume", "stop"}:
            raise ValidationError("Unsupported session action")
        async with AsyncSessionLocal() as db:
            session = await PersonalAutoOutboundRepository.get_owned_session(
                db, principal.tenant_id, principal.user_id, session_id
            )
            if session is None:
                raise NotFoundError("Personal auto-outbound session not found")
            if action == "pause":
                if session.status == "running":
                    session = await PersonalAutoOutboundRepository.update_session(
                        db,
                        session,
                        {"status": "paused", "pause_reason": "manual", "paused_at": datetime.now(timezone.utc)},
                    )
            elif action == "resume":
                if session.status in {"paused", "auto_paused"}:
                    agent_status = await CcAgentStatusService.get_for_employee(
                        db, principal.tenant_id, principal.user_id, r
                    )
                    if agent_status["status"] != "ready" or agent_status.get("resource_state") in {
                        "reserved",
                        "ringing",
                        "in_call",
                    }:
                        raise ValidationError("Primary agent must be ready")
                    device = await AgentCallDeviceService.get_current_device(
                        db, principal.tenant_id, principal.user_id, r
                    )
                    if not device.get("available"):
                        raise ValidationError("Current call device is unavailable")
                    task = await PersonalAutoOutboundRepository.get_task_option(
                        db, principal.tenant_id, principal.user_id, session.task_id
                    )
                    if task is None:
                        raise ValidationError("Outbound task has no callable targets")
                    tenant_string_id = await TenantPhoneNumberService._tenant_string_id(
                        db, principal.tenant_id
                    )
                    phone = await TenantPhoneNumberRepository.get_assigned_by_id(
                        db, tenant_string_id, session.outbound_phone_number_id
                    )
                    if phone is None or "outbound" not in (phone.call_types or []):
                        raise ValidationError("Outbound phone number is unavailable")
                    ready_fallback_count = await PersonalAutoOutboundService._ready_fallback_count(
                        db, principal, session.fallback_group_id, r
                    )
                    effective_concurrency = (
                        session.configured_concurrency
                        if session.configured_concurrency == 1 or ready_fallback_count > 0
                        else 1
                    )
                    session = await PersonalAutoOutboundRepository.update_session(
                        db,
                        session,
                        {
                            "status": "running",
                            "pause_reason": None,
                            "paused_at": None,
                            "effective_concurrency": effective_concurrency,
                        },
                    )
            elif action == "stop" and session.status in {"running", "paused", "auto_paused"}:
                session = await PersonalAutoOutboundRepository.update_session(
                    db,
                    session,
                    {"status": "stopping", "pause_reason": None, "stopping_at": datetime.now(timezone.utc)},
                )
        return session

    @staticmethod
    async def start_session_managed(
        principal: EffectivePrincipal,
        body: PersonalAutoOutboundStartRequest,
        r: aioredis.Redis | None = None,
    ):
        async with AsyncSessionLocal() as db:
            existing = await PersonalAutoOutboundRepository.get_current_session(
                db, principal.tenant_id, principal.user_id
            )
            if existing is not None:
                return existing

            agent_status = await CcAgentStatusService.get_for_employee(
                db, principal.tenant_id, principal.user_id, r
            )
            if agent_status["status"] != "ready" or agent_status.get("resource_state") in {"reserved", "ringing", "in_call"}:
                raise ValidationError("Primary agent must be ready")
            device = await AgentCallDeviceService.get_current_device(
                db, principal.tenant_id, principal.user_id, r
            )
            if not device.get("available"):
                raise ValidationError("Current call device is unavailable")

            task = await PersonalAutoOutboundRepository.get_task_option(
                db, principal.tenant_id, principal.user_id, body.task_id
            )
            if task is None:
                raise ValidationError("Outbound task has no callable targets")

            tenant_string_id = await TenantPhoneNumberService._tenant_string_id(db, principal.tenant_id)
            phone = await TenantPhoneNumberRepository.get_assigned_by_id(
                db, tenant_string_id, body.outbound_phone_number_id
            )
            if phone is None or "outbound" not in (phone.call_types or []):
                raise ValidationError("Outbound phone number is unavailable")

            recordings = {
                row.recording_type: row
                for row in await PersonalAutoOutboundRepository.list_recordings(
                    db, principal.tenant_id, principal.user_id
                )
            }
            if "opening" not in recordings or "closing" not in recordings:
                raise ValidationError("Opening and closing recordings are required")

            if body.fallback_group_id is not None:
                group = await EmployeeGroupRepository.get_by_id(db, body.fallback_group_id)
                if (
                    group is None
                    or group.tenant_id != principal.tenant_id
                    or body.fallback_group_id not in principal.group_ids
                ):
                    raise ValidationError("Fallback group is unavailable")

            intents, examples = await OutboundPrescreenRepository.list_config(db, principal.tenant_id)
            examples_by_intent: dict[int, list] = {}
            for example in examples:
                examples_by_intent.setdefault(example.intent_id, []).append(example)
            enabled_intents = [
                intent
                for intent in intents
                if intent.enabled
                and examples_by_intent.get(intent.id)
                and all(
                    example.embedding_status == "ready" and example.embedding is not None
                    for example in examples_by_intent[intent.id]
                )
            ]
            if not enabled_intents:
                raise ValidationError("No enabled outbound prescreen intent configuration")

            ready_fallback_count = await PersonalAutoOutboundService._ready_fallback_count(
                db, principal, body.fallback_group_id, r
            )
            effective_concurrency = (
                body.configured_concurrency
                if body.configured_concurrency == 1 or ready_fallback_count > 0
                else 1
            )
            snapshot = [
                {
                    "intent_key": intent.intent_key,
                    "name": intent.name,
                    "similarity_threshold": float(intent.similarity_threshold),
                    "examples": [
                        {
                            "example_type": example.example_type,
                            "text": example.text,
                            "embedding": list(example.embedding),
                        }
                        for example in examples_by_intent[intent.id]
                        if example.embedding is not None
                    ],
                }
                for intent in enabled_intents
            ]
            now = datetime.now(timezone.utc)
            try:
                return await PersonalAutoOutboundRepository.create_session(
                    db,
                    {
                        "tenant_id": principal.tenant_id,
                        "primary_agent_id": principal.user_id,
                        "task_id": body.task_id,
                        "outbound_phone_number_id": body.outbound_phone_number_id,
                        "fallback_group_id": body.fallback_group_id,
                        "opening_audio_asset_id": recordings["opening"].audio_asset_id,
                        "closing_audio_asset_id": recordings["closing"].audio_asset_id,
                        "opening_script_text": (getattr(recordings["opening"], "script_text", None) or "").strip() or None,
                        "configured_concurrency": body.configured_concurrency,
                        "effective_concurrency": effective_concurrency,
                        "status": "running",
                        "intent_snapshot": snapshot,
                        "started_at": now,
                    },
                )
            except IntegrityError as exc:
                await db.rollback()
                current = await PersonalAutoOutboundRepository.get_current_session(
                    db, principal.tenant_id, principal.user_id
                )
                if current is not None:
                    return current
                raise ConflictError("Personal auto-outbound session already exists") from exc
