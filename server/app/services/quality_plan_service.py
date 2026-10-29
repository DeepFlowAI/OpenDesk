"""Business logic for online quality plans."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.models.quality import QualityPlan, QualityPlanCandidate
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.quality_plan_repository import QualityPlanRepository
from app.schemas.permission import EffectivePrincipal
from app.schemas.quality_plan import QualityPlanEstimateResponse, QualityPlanListResponse, QualityPlanPayload, QualityPlanResponse, QualityPlanReviewersPayload
from app.services.data_scope_service import DataScopeService
from app.services.permission_service import PermissionService

SAMPLE_ALGORITHM_VERSION = "v1"


class QualityPlanService:
    @staticmethod
    def stable_sample_value(plan_id: int, conversation_id: int, agent_id: int) -> Decimal:
        raw = f"{SAMPLE_ALGORITHM_VERSION}:{plan_id}:{conversation_id}:{agent_id}".encode()
        value = int.from_bytes(hashlib.sha256(raw).digest()[:8], "big") / 2**64
        return Decimal(str(value)).quantize(Decimal("0.000001"))

    @staticmethod
    def config_signature(payload: QualityPlanPayload, principal: EffectivePrincipal) -> str:
        data = payload.model_dump(mode="json")
        data["scope"] = DataScopeService.get_scope(principal, "session_record")
        data["scope_group_ids"] = sorted(principal.group_ids)
        return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    @staticmethod
    async def list_plans(db: AsyncSession, principal: EffectivePrincipal, **params) -> QualityPlanListResponse:
        rows, total = await QualityPlanRepository.list_paginated(db, principal.tenant_id, **params)
        return QualityPlanListResponse(items=[QualityPlanResponse.model_validate(row) for row in rows], total=total, page=params["page"], per_page=params["per_page"], pages=(total + params["per_page"] - 1) // params["per_page"])

    @staticmethod
    async def get_plan(db: AsyncSession, principal: EffectivePrincipal, plan_id: int) -> QualityPlanResponse:
        return QualityPlanResponse.model_validate(await QualityPlanService._require_plan(db, principal, plan_id))

    @staticmethod
    async def create_plan(db: AsyncSession, principal: EffectivePrincipal, payload: QualityPlanPayload) -> QualityPlanResponse:
        QualityPlanService._require_manage_scope(principal)
        await QualityPlanService._validate_references(db, principal, payload)
        row = QualityPlan(tenant_id=principal.tenant_id, created_by_id=principal.user_id, status="draft", sample_algorithm_version=SAMPLE_ALGORITHM_VERSION, **payload.model_dump())
        row = await QualityPlanRepository.save(db, row)
        return QualityPlanResponse.model_validate(row)

    @staticmethod
    async def update_plan(db: AsyncSession, principal: EffectivePrincipal, plan_id: int, payload: QualityPlanPayload) -> QualityPlanResponse:
        QualityPlanService._require_manage_scope(principal)
        row = await QualityPlanService._require_plan(db, principal, plan_id)
        if row.status != "draft":
            raise ConflictError("Core plan configuration is immutable after activation")
        await QualityPlanService._validate_references(db, principal, payload)
        for key, value in payload.model_dump().items():
            setattr(row, key, value)
        row.estimate_signature = None
        row.estimate_result = {}
        row.estimated_at = None
        row = await QualityPlanRepository.save(db, row)
        return QualityPlanResponse.model_validate(row)

    @staticmethod
    async def estimate(db: AsyncSession, principal: EffectivePrincipal, plan_id: int) -> QualityPlanEstimateResponse:
        QualityPlanService._require_manage_scope(principal)
        plan = await QualityPlanService._require_plan(db, principal, plan_id)
        payload = QualityPlanService._payload(plan)
        pairs = await QualityPlanService._candidate_objects(db, principal, plan)
        agents = {pair[1] for pair in pairs}
        sampled = sum(QualityPlanService._is_sampled(plan, pair[0], pair[1]) for pair in pairs)
        result = QualityPlanEstimateResponse(candidate_count=len(pairs), target_agent_count=len(agents), estimated_review_count=sampled, reference_days=7 if plan.run_mode == "continuous" else None, estimated_daily_count=(Decimal(sampled) / Decimal(7)).quantize(Decimal("0.1")) if plan.run_mode == "continuous" else None)
        plan.estimate_signature = QualityPlanService.config_signature(payload, principal)
        plan.estimate_result = result.model_dump(mode="json")
        plan.estimated_at = datetime.now(timezone.utc)
        await QualityPlanRepository.save(db, plan)
        return result

    @staticmethod
    async def activate(db: AsyncSession, principal: EffectivePrincipal, plan_id: int) -> QualityPlanResponse:
        QualityPlanService._require_manage_scope(principal)
        plan = await QualityPlanService._require_plan(db, principal, plan_id)
        if plan.status != "draft":
            raise ConflictError("Only draft plans can be activated")
        payload = QualityPlanService._payload(plan)
        if plan.estimate_signature != QualityPlanService.config_signature(payload, principal):
            raise ValidationError("Estimate eligible conversations before activation")
        await QualityPlanService._validate_references(db, principal, payload)
        pairs = await QualityPlanService._candidate_objects(db, principal, plan)
        if plan.run_mode == "one_time" and not pairs:
            raise ValidationError("No eligible conversations match the filters")
        if len(pairs) > 10000:
            raise ValidationError("One-time plans support at most 10,000 review objects")
        for pair in pairs:
            if not QualityPlanService._is_sampled(plan, pair[0], pair[1]):
                continue
            eligible = await QualityPlanService.eligible_reviewer_ids(
                db,
                principal.tenant_id,
                plan.reviewer_ids,
                target_agent_id=pair[1],
                group_id=pair[4],
            )
            if not eligible:
                raise ValidationError(
                    "No selected reviewer can access every sampled target agent",
                    details={"target_agent_id": pair[1]},
                )
        candidates = (
            [QualityPlanService._candidate(plan, *pair) for pair in pairs if QualityPlanService._is_sampled(plan, pair[0], pair[1])]
            if plan.run_mode == "one_time"
            else []
        )
        plan.scope_snapshot = {"scope": DataScopeService.get_scope(principal, "session_record"), "group_ids": principal.group_ids, "created_by_id": principal.user_id}
        plan.status = "running"
        plan.activated_at = datetime.now(timezone.utc)
        plan.last_candidate_scan_at = plan.activated_at if plan.run_mode == "continuous" else None
        plan = await QualityPlanRepository.replace_candidates(db, plan, candidates)
        return QualityPlanResponse.model_validate(plan)

    @staticmethod
    async def transition(db: AsyncSession, principal: EffectivePrincipal, plan_id: int, action: str) -> QualityPlanResponse:
        QualityPlanService._require_manage_scope(principal)
        plan = await QualityPlanService._require_plan(db, principal, plan_id)
        if plan.run_mode != "continuous" or (action == "pause" and plan.status != "running") or (action == "resume" and plan.status != "paused"):
            raise ConflictError("Invalid plan state transition")
        plan.status = "paused" if action == "pause" else "running"
        plan.paused_at = datetime.now(timezone.utc) if action == "pause" else None
        plan = await QualityPlanRepository.save(db, plan)
        return QualityPlanResponse.model_validate(plan)

    @staticmethod
    async def update_reviewers(
        db: AsyncSession,
        principal: EffectivePrincipal,
        plan_id: int,
        payload: QualityPlanReviewersPayload,
    ) -> QualityPlanResponse:
        QualityPlanService._require_manage_scope(principal)
        plan = await QualityPlanService._require_plan(db, principal, plan_id)
        for reviewer_id in payload.reviewer_ids:
            if not await EmployeeRepository.has_effective_permission(
                db,
                principal.tenant_id,
                reviewer_id,
                "quality.online.review.perform",
            ):
                raise ValidationError(
                    "Selected reviewer is not eligible",
                    details={"reviewer_id": reviewer_id},
                )
        for candidate in plan.candidates:
            eligible = await QualityPlanService.eligible_reviewer_ids(
                db,
                principal.tenant_id,
                payload.reviewer_ids,
                target_agent_id=candidate.target_agent_id,
                group_id=candidate.group_id_snapshot,
            )
            if not eligible:
                raise ValidationError(
                    "No selected reviewer can access every sampled target agent",
                    details={"target_agent_id": candidate.target_agent_id},
                )
        plan.reviewer_ids = list(dict.fromkeys(payload.reviewer_ids))
        plan = await QualityPlanRepository.save(db, plan)
        return QualityPlanResponse.model_validate(plan)

    @staticmethod
    async def _candidate_objects(db: AsyncSession, principal: EffectivePrincipal, plan: QualityPlan) -> list[tuple[int, int, list[int], str | None, int | None, str | None, datetime]]:
        now = datetime.now(timezone.utc)
        start = plan.range_start_at if plan.run_mode == "one_time" else now - timedelta(days=7)
        end = plan.range_end_at if plan.run_mode == "one_time" else now
        scope = DataScopeService.get_scope(principal, "session_record")
        agent_ids = plan.agent_ids
        if scope == "self":
            agent_ids = [principal.user_id] if principal.user_id is not None else []
        rows = await QualityPlanRepository.candidate_segments(db, principal.tenant_id, start_at=start, end_at=end, group_ids=plan.group_ids, agent_ids=agent_ids, scope=scope, scope_group_ids=principal.group_ids)
        grouped: dict[tuple[int, int], list] = {}
        for segment, conversation in rows:
            grouped.setdefault((conversation.id, int(segment.agent_id)), []).append((segment, conversation))
        result = []
        for (conversation_id, agent_id), values in grouped.items():
            segment = values[0][0]; conversation = values[0][1]
            result.append((conversation_id, agent_id, [value[0].id for value in values], segment.agent_name_snapshot, segment.group_id, segment.group_name_snapshot, conversation.ended_at))
        return result

    @staticmethod
    def _is_sampled(plan: QualityPlan, conversation_id: int, agent_id: int, *_args) -> bool:
        return plan.coverage_mode == "all" or QualityPlanService.stable_sample_value(plan.id, conversation_id, agent_id) < Decimal(plan.sample_rate) / 100

    @staticmethod
    def _candidate(plan: QualityPlan, conversation_id: int, agent_id: int, segment_ids: list[int], agent_name: str | None, group_id: int | None, group_name: str | None, ended_at: datetime) -> QualityPlanCandidate:
        return QualityPlanCandidate(conversation_id=conversation_id, target_agent_id=agent_id, segment_ids=segment_ids, agent_name_snapshot=agent_name, group_id_snapshot=group_id, group_name_snapshot=group_name, conversation_ended_at=ended_at, sampled=True, sample_value=QualityPlanService.stable_sample_value(plan.id, conversation_id, agent_id), status="pending")

    @staticmethod
    async def _validate_references(db: AsyncSession, principal: EffectivePrincipal, payload: QualityPlanPayload) -> None:
        if payload.run_mode == "one_time" and payload.range_end_at - payload.range_start_at > timedelta(days=90):
            raise ValidationError("Historical range cannot exceed 90 days")
        if await QualityPlanRepository.get_published_version(db, principal.tenant_id, payload.scorecard_version_id) is None:
            raise ValidationError("Select an active published scorecard version")
        for reviewer_id in payload.reviewer_ids:
            if not await EmployeeRepository.has_effective_permission(db, principal.tenant_id, reviewer_id, "quality.online.review.perform"):
                raise ValidationError("Selected reviewer is not eligible", details={"reviewer_id": reviewer_id})

    @staticmethod
    async def eligible_reviewer_ids(
        db: AsyncSession,
        tenant_id: int,
        reviewer_ids: list[int],
        *,
        target_agent_id: int,
        group_id: int | None,
    ) -> list[int]:
        eligible: list[int] = []
        for reviewer_id in reviewer_ids:
            try:
                reviewer = await PermissionService.get_current_principal(
                    db, {"user_id": reviewer_id, "tenant_id": tenant_id}
                )
            except Exception:  # noqa: BLE001
                continue
            if not reviewer.has_permission("quality.online.review.perform"):
                continue
            scope = DataScopeService.get_scope(reviewer, "session_record")
            if scope == "all" or (scope == "self" and reviewer_id == target_agent_id):
                eligible.append(reviewer_id)
                continue
            if scope == "group":
                peers = await DataScopeService.get_group_peer_employee_ids(
                    db, reviewer.group_ids
                )
                if group_id in reviewer.group_ids or target_agent_id in peers:
                    eligible.append(reviewer_id)
        return eligible

    @staticmethod
    def _require_manage_scope(principal: EffectivePrincipal) -> None:
        if DataScopeService.get_scope(principal, "session_record") == "self":
            raise ForbiddenError("Self-scoped users cannot manage quality plans")

    @staticmethod
    def _payload(plan: QualityPlan) -> QualityPlanPayload:
        return QualityPlanPayload.model_validate({key: getattr(plan, key) for key in QualityPlanPayload.model_fields})

    @staticmethod
    async def _require_plan(db: AsyncSession, principal: EffectivePrincipal, plan_id: int) -> QualityPlan:
        plan = await QualityPlanRepository.get_by_id(db, principal.tenant_id, plan_id)
        if plan is None:
            raise NotFoundError("Quality plan not found")
        return plan
