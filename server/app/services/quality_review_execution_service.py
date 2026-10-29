"""Materialize and execute online quality reviews."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import json

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.db.session import AsyncSessionLocal
from app.models.platform_llm_call import PlatformLLMCall
from app.models.quality import QualityPlan, QualityReview, QualityReviewItem
from app.repositories.platform_llm_call_repository import PlatformLLMCallRepository
from app.repositories.quality_review_repository import QualityReviewRepository
from app.schemas.permission import EffectivePrincipal
from app.schemas.quality_review import (
    QualityLLMResult,
    QualityMaterializeResponse,
    QualityRetryResponse,
)
from app.services.platform_llm_queue_service import PlatformLLMQueueService
from app.services.quality_plan_service import QualityPlanService

_SEVERITY = {"normal": 0, "notice": 1, "issue": 2, "serious": 3, "fatal": 4}


class QualityReviewExecutionService:
    @staticmethod
    async def materialize(db: AsyncSession, principal: EffectivePrincipal, plan_id: int) -> QualityMaterializeResponse:
        plan = await QualityReviewRepository.plan(db, plan_id)
        if plan is None or plan.tenant_id != principal.tenant_id:
            raise NotFoundError("Quality plan not found")
        if plan.status not in {"running", "completed", "partial_failed", "failed"}:
            raise ValidationError("Activate the quality plan first")
        version = await QualityReviewRepository.scorecard_version(db, plan.scorecard_version_id)
        if version is None:
            raise ValidationError("Scorecard version not found")
        candidates = await QualityReviewRepository.unmaterialized_candidates(db, principal.tenant_id, plan_id)
        created = queued = 0
        criteria = [criterion for section in version.sections for criterion in section.criteria]
        for candidate in candidates:
            conversation, messages = await QualityReviewRepository.conversation_snapshot(db, candidate.conversation_id)
            if conversation is None:
                continue
            snapshot = [
                {
                    "id": message.id,
                    "sender_type": message.sender_type,
                    "sender_id": message.sender_id,
                    "content_type": message.content_type,
                    "content": message.content,
                    "is_recalled": message.is_recalled,
                    "metadata": message.metadata_,
                    "created_at": message.created_at.isoformat(),
                }
                for message in messages
            ]
            is_human = plan.execution_strategy == "human"
            eligible_reviewers = await QualityPlanService.eligible_reviewer_ids(
                db,
                plan.tenant_id,
                plan.reviewer_ids,
                target_agent_id=candidate.target_agent_id,
                group_id=candidate.group_id_snapshot,
            )
            reviewer_id = (
                eligible_reviewers[created % len(eligible_reviewers)]
                if is_human and eligible_reviewers
                else None
            )
            review = QualityReview(
                tenant_id=plan.tenant_id,
                plan_id=plan.id,
                candidate_id=candidate.id,
                conversation_id=candidate.conversation_id,
                target_agent_id=candidate.target_agent_id,
                scorecard_version_id=version.id,
                status="pending_human" if is_human else "ai_processing",
                route_reasons=["human_full_review"] if is_human else [],
                assigned_reviewer_id=reviewer_id,
                conversation_snapshot={
                    "public_id": conversation.public_id,
                    "ended_at": conversation.ended_at.isoformat() if conversation.ended_at else None,
                    "segment_ids": candidate.segment_ids,
                    "agent_name": candidate.agent_name_snapshot,
                    "group_id": candidate.group_id_snapshot,
                    "group_name": candidate.group_name_snapshot,
                    "pass_score": str(version.pass_score) if version.pass_score is not None else None,
                },
                message_snapshot=snapshot,
            )
            db.add(review)
            await db.flush()
            created += 1
            for order, criterion in enumerate(criteria):
                criterion_snapshot = {"id": criterion.id, "name": criterion.name, "rubric": criterion.rubric, "max_points": str(criterion.max_points), "is_required": criterion.is_required, "evidence_policy": criterion.evidence_policy, "options": [{"id": option.id, "name": option.name, "description": option.description, "points": str(option.points), "severity": option.severity} for option in criterion.options]}
                item = QualityReviewItem(
                    review_id=review.id,
                    criterion_id=criterion.id,
                    sort_order=order,
                    criterion_snapshot=criterion_snapshot,
                    status="pending_human" if is_human else "queued",
                )
                db.add(item)
                await db.flush()
                if not is_human:
                    call = await QualityReviewExecutionService._enqueue_call(
                        db, plan, review, item, version.id
                    )
                    item.llm_call_id = call.id
                    queued += 1
            candidate.status = "generated"
        await db.commit()
        await QualityReviewExecutionService._update_one_time_plan_status(db, plan.id)
        return QualityMaterializeResponse(created_reviews=created, queued_calls=queued)

    @staticmethod
    def _prompt(review: QualityReview, criterion: dict) -> list[dict[str, str]]:
        allowed = [{"id": option["id"], "name": option["name"], "description": option["description"]} for option in criterion["options"]]
        messages = [message for message in review.message_snapshot if not message["is_recalled"]]
        return [
            {
                "role": "system",
                "content": (
                    "Evaluate only the supplied criterion. Return strict JSON with "
                    "result_type, option_id, reason, evidence_message_ids and no extra fields. "
                    "Evidence may reference only supplied non-recalled message ids."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Target agent id: {review.target_agent_id}\n"
                    f"Criterion: {criterion['name']}\nRubric: {criterion['rubric']}\n"
                    f"Allowed options: {json.dumps(allowed, ensure_ascii=False)}\n"
                    f"Messages: {json.dumps(messages, ensure_ascii=False)}"
                ),
            },
        ]

    @staticmethod
    async def _enqueue_call(
        db: AsyncSession,
        plan: QualityPlan,
        review: QualityReview,
        item: QualityReviewItem,
        version_id: int,
    ) -> PlatformLLMCall:
        call = PlatformLLMCall(
            tenant_id=plan.tenant_id,
            business_type="quality_criterion",
            business_id=str(item.id),
            idempotency_key=(
                f"quality:{review.id}:{version_id}:{item.criterion_id}:"
                f"{item.execution_round}"
            ),
            status="queued",
            request_payload={
                "tenant_id": plan.tenant_id,
                "plan_id": plan.id,
                "review_id": review.id,
                "scorecard_version_id": version_id,
                "criterion_id": item.criterion_id,
                "execution_round": item.execution_round,
                "messages": QualityReviewExecutionService._prompt(
                    review, item.criterion_snapshot
                ),
            },
            available_at=datetime.now(timezone.utc),
            execution_round=item.execution_round,
        )
        return await PlatformLLMCallRepository.enqueue(db, call)

    @staticmethod
    async def retry_failed(
        db: AsyncSession,
        principal: EffectivePrincipal,
        plan_id: int,
        review_id: int,
    ) -> QualityRetryResponse:
        review = await QualityReviewRepository.review_by_id(
            db, principal.tenant_id, review_id
        )
        if review is None or review.plan_id != plan_id:
            raise NotFoundError("Quality review not found")
        if review.status != "execution_failed":
            raise ValidationError("Only failed reviews can be retried")
        plan = await QualityReviewRepository.plan(db, plan_id)
        if plan is None:
            raise NotFoundError("Quality plan not found")
        queued = 0
        for item in review.items:
            if item.status != "failed":
                continue
            item.execution_round += 1
            item.status = "queued"
            item.last_error = None
            call = await QualityReviewExecutionService._enqueue_call(
                db, plan, review, item, review.scorecard_version_id
            )
            item.llm_call_id = call.id
            queued += 1
        if not queued:
            raise ValidationError("No failed criteria can be retried")
        review.status = "ai_processing"
        await db.commit()
        return QualityRetryResponse(review_id=review.id, queued_calls=queued)

    @staticmethod
    async def complete_call_managed(call_id: int, payload: dict) -> None:
        async with AsyncSessionLocal() as db:
            await QualityReviewExecutionService._complete_call(db, call_id, payload)

    @staticmethod
    async def _complete_call(db: AsyncSession, call_id: int, payload: dict) -> None:
        call = await PlatformLLMCallRepository.get(db, call_id)
        if call is None:
            raise NotFoundError("LLM call target not found")
        pair = await QualityReviewRepository.review_by_call_id(db, call_id)
        if pair is None:
            raise NotFoundError("LLM call target not found")
        item, review = pair
        result = QualityLLMResult.model_validate(payload)
        option_ids = {option["id"] for option in item.criterion_snapshot["options"]}
        if result.result_type == "option" and result.option_id not in option_ids:
            raise ValidationError("LLM returned an invalid option")
        if result.result_type != "option" and result.option_id is not None:
            raise ValidationError("System results cannot include an option")
        message_ids = {
            message["id"]
            for message in review.message_snapshot
            if not message["is_recalled"]
        }
        if not set(result.evidence_message_ids).issubset(message_ids):
            raise ValidationError("LLM returned invalid evidence")
        if result.result_type == "option" and QualityReviewExecutionService._evidence_required(item.criterion_snapshot, result.option_id) and not result.evidence_message_ids:
            result = QualityLLMResult(result_type="insufficient_evidence", option_id=None, reason="Required reliable evidence was not returned", evidence_message_ids=[])
        call.status = "succeeded"; call.response_payload = result.model_dump(); call.completed_at = datetime.now(timezone.utc)
        item.status = "succeeded"; item.result_type = result.result_type; item.option_id = result.option_id; item.reason = result.reason; item.evidence_message_ids = list(dict.fromkeys(result.evidence_message_ids))
        await QualityReviewExecutionService._aggregate_if_ready(db, review)
        await db.commit()
        await QualityReviewExecutionService._update_one_time_plan_status(db, review.plan_id)

    @staticmethod
    async def fail_call_managed(call_id: int, error: str) -> None:
        async with AsyncSessionLocal() as db:
            call = await PlatformLLMCallRepository.get(db, call_id)
            pair = await QualityReviewRepository.review_by_call_id(db, call_id)
            if call is None or pair is None:
                return
            item, review = pair
            call.last_error = error
            item.last_error = error
            retrying = PlatformLLMQueueService.schedule_retry(call, datetime.now(timezone.utc))
            item.status = "queued" if retrying else "failed"
            if not retrying:
                review.status = "execution_failed"
            await db.commit()
            if not retrying:
                await QualityReviewExecutionService._update_one_time_plan_status(
                    db, review.plan_id
                )

    @staticmethod
    async def _aggregate_if_ready(db: AsyncSession, review: QualityReview) -> None:
        if any(item.status != "succeeded" for item in review.items):
            return
        plan = await QualityReviewRepository.plan(db, review.plan_id)
        if plan is None:
            return
        route_reasons: list[str] = []
        results = []
        for item in review.items:
            if item.result_type == "insufficient_evidence": route_reasons.append("insufficient_evidence")
            option = next((value for value in item.criterion_snapshot["options"] if value["id"] == item.option_id), None)
            results.append((item, option))
        if all(item.result_type == "not_applicable" for item in review.items): route_reasons.append("all_not_applicable")
        threshold = _SEVERITY.get(plan.manual_route_severity or "issue", 2)
        maximum = max((_SEVERITY[option["severity"]] for _, option in results if option), default=0)
        if maximum >= threshold: route_reasons.append("suspected_fatal" if maximum == 4 else f"risk_{plan.manual_route_severity}")
        applicable = [(item, option) for item, option in results if option]
        scored = [(item, option) for item, option in applicable if Decimal(item.criterion_snapshot["max_points"]) > 0]
        if scored:
            earned = sum(Decimal(option["points"]) for item, option in scored)
            maximum_points = sum(
                Decimal(item.criterion_snapshot["max_points"])
                for item, option in scored
            )
            review.ai_score = (earned / maximum_points * 100).quantize(Decimal("0.1"))
        review.issue_count = sum(_SEVERITY[option["severity"]] >= 2 for _, option in applicable)
        version = await QualityReviewRepository.scorecard_version(db, review.scorecard_version_id)
        review.ai_outcome = "failed" if maximum == 4 or (review.ai_score is not None and version and version.pass_score is not None and review.ai_score < version.pass_score) else "passed" if review.ai_score is not None else "issues" if review.issue_count else "no_issues"
        review_rate = Decimal(plan.normal_review_rate) / 100
        if (
            not route_reasons
            and QualityPlanService.stable_sample_value(
                plan.id, review.conversation_id, review.target_agent_id
            )
            < review_rate
        ):
            route_reasons.append("sample_review")
        review.route_reasons = list(dict.fromkeys(route_reasons))
        if route_reasons:
            review.status = "pending_human"
            eligible = await QualityPlanService.eligible_reviewer_ids(
                db,
                plan.tenant_id,
                plan.reviewer_ids,
                target_agent_id=review.target_agent_id,
                group_id=review.conversation_snapshot.get("group_id"),
            )
            review.assigned_reviewer_id = (
                eligible[(review.id - 1) % len(eligible)]
                if eligible
                else None
            )
        else:
            review.status = "ai_completed"
            review.final_source = "ai"
            review.final_score = review.ai_score
            review.final_outcome = review.ai_outcome
            review.final_issue_count = review.issue_count
            review.completed_at = datetime.now(timezone.utc)

    @staticmethod
    def _evidence_required(criterion: dict, option_id: int | None) -> bool:
        option = next((value for value in criterion["options"] if value["id"] == option_id), None)
        if option is None: return False
        return option["severity"] == "fatal" or criterion["evidence_policy"] == "always" or (criterion["evidence_policy"] == "issue_only" and _SEVERITY[option["severity"]] >= 2)

    @staticmethod
    async def _update_one_time_plan_status(db: AsyncSession, plan_id: int) -> None:
        plan = await QualityReviewRepository.plan(db, plan_id)
        if plan is None or plan.run_mode != "one_time":
            return
        reviews = await QualityReviewRepository.reviews_by_plan(db, plan_id)
        if not reviews or any(
            item.status not in {"succeeded", "failed", "pending_human"}
            for review in reviews
            for item in review.items
        ):
            return
        failed = sum(review.status == "execution_failed" for review in reviews)
        plan.status = (
            "failed"
            if failed == len(reviews)
            else "partial_failed"
            if failed
            else "completed"
        )
        await db.commit()
