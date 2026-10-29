"""Human workflow, records and statistics for online quality reviews."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.models.quality import (
    QualityHumanReviewDraft,
    QualityHumanReviewItem,
    QualityReview,
    QualityReviewAudit,
    QualityReviewItem,
)
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.quality_review_repository import QualityReviewRepository
from app.schemas.permission import EffectivePrincipal
from app.schemas.quality_review import (
    QualityDraftPayload,
    QualityReassignPayload,
    QualityReviewDetailResponse,
    QualityReviewListItem,
    QualityReviewListResponse,
    QualityStatisticsResponse,
    QualityUnablePayload,
    QualityWorkbenchResponse,
)
from app.services.data_scope_service import DataScopeService
from app.services.permission_service import PermissionService
from app.services.quality_review_execution_service import _SEVERITY


class QualityReviewService:
    @staticmethod
    async def pending_mine(
        db: AsyncSession,
        principal: EffectivePrincipal,
        plan_id: int,
        *,
        page: int,
        per_page: int,
    ) -> QualityReviewListResponse:
        if principal.user_id is None:
            raise ForbiddenError("Employee account required")
        await QualityReviewService._require_plan(db, principal, plan_id)
        allowed_agent_ids = await QualityReviewService._allowed_agent_ids(db, principal)
        rows, total = await QualityReviewRepository.pending_mine(
            db,
            principal.tenant_id,
            principal.user_id,
            plan_id,
            allowed_agent_ids=allowed_agent_ids,
            page=page,
            per_page=per_page,
        )
        return QualityReviewService._list_response(rows, total, page, per_page)

    @staticmethod
    async def open_review(
        db: AsyncSession, principal: EffectivePrincipal, review_id: int
    ) -> QualityWorkbenchResponse:
        review = await QualityReviewService._assigned_review(db, principal, review_id)
        if review.status == "pending_human":
            review.status = "human_reviewing"
        draft = await QualityReviewService._get_or_create_draft(db, review, principal.user_id)
        db.add(
            QualityReviewAudit(
                review_id=review.id,
                action="open",
                actor_id=principal.user_id,
                after_snapshot={"status": review.status, "draft_version": draft.version},
            )
        )
        await db.commit()
        return await QualityReviewService._workbench_after_commit(
            db, principal.tenant_id, review_id
        )

    @staticmethod
    async def get_workbench(
        db: AsyncSession, principal: EffectivePrincipal, review_id: int
    ) -> QualityWorkbenchResponse:
        review = await QualityReviewService._assigned_review(db, principal, review_id)
        draft = await QualityReviewRepository.draft(db, review.id)
        if draft is None:
            return QualityReviewService._workbench(review, None)
        return QualityReviewService._workbench(review, draft)

    @staticmethod
    async def save_draft(
        db: AsyncSession,
        principal: EffectivePrincipal,
        review_id: int,
        payload: QualityDraftPayload,
    ) -> QualityWorkbenchResponse:
        review = await QualityReviewService._assigned_review(db, principal, review_id)
        draft = await QualityReviewService._apply_payload(
            db, review, principal.user_id, payload
        )
        db.add(
            QualityReviewAudit(
                review_id=review.id,
                action="save_draft",
                actor_id=principal.user_id,
                after_snapshot=QualityReviewService._draft_snapshot(draft),
            )
        )
        await db.commit()
        return await QualityReviewService._workbench_after_commit(
            db, principal.tenant_id, review_id
        )

    @staticmethod
    async def submit(
        db: AsyncSession,
        principal: EffectivePrincipal,
        review_id: int,
        payload: QualityDraftPayload,
    ) -> QualityReviewDetailResponse:
        review = await QualityReviewService._assigned_review(db, principal, review_id)
        draft = await QualityReviewService._apply_payload(
            db, review, principal.user_id, payload, increment_version=False
        )
        score, outcome, issue_count = QualityReviewService._validate_and_score(
            review, draft
        )
        now = datetime.now(timezone.utc)
        draft.status = "submitted"
        draft.submitted_at = now
        draft.version += 1
        review.status = "human_completed"
        review.final_source = "human"
        review.final_score = score
        review.final_outcome = outcome
        review.final_issue_count = issue_count
        review.overall_comment = draft.overall_comment
        review.unable_reason = None
        review.submitted_by_id = principal.user_id
        review.completed_at = now
        db.add(
            QualityReviewAudit(
                review_id=review.id,
                action="submit",
                actor_id=principal.user_id,
                after_snapshot={
                    **QualityReviewService._draft_snapshot(draft),
                    "score": str(score) if score is not None else None,
                    "outcome": outcome,
                    "issue_count": issue_count,
                },
            )
        )
        await db.commit()
        return await QualityReviewService.detail(db, principal, review.id, allow_assignee=True)

    @staticmethod
    async def submit_unable(
        db: AsyncSession,
        principal: EffectivePrincipal,
        review_id: int,
        payload: QualityUnablePayload,
    ) -> QualityReviewDetailResponse:
        review = await QualityReviewService._assigned_review(db, principal, review_id)
        draft_payload = QualityDraftPayload(
            version=payload.version,
            overall_comment=payload.overall_comment,
            items=payload.items,
        )
        draft = await QualityReviewService._apply_payload(
            db, review, principal.user_id, draft_payload, increment_version=False
        )
        item_map = {item.review_item_id: item for item in draft.items}
        required_unresolved = any(
            item.criterion_snapshot["is_required"]
            and item_map[item.id].result_type == "unanswered"
            for item in review.items
        )
        any_applicable = any(item.result_type == "option" for item in draft.items)
        if any_applicable and not required_unresolved:
            raise ValidationError("This review has enough information for a normal submission")
        now = datetime.now(timezone.utc)
        draft.status = "submitted"
        draft.submitted_at = now
        draft.version += 1
        review.status = "human_completed"
        review.final_source = "human"
        review.final_score = None
        review.final_outcome = "unable"
        review.final_issue_count = None
        review.overall_comment = draft.overall_comment
        review.unable_reason = payload.reason
        review.submitted_by_id = principal.user_id
        review.completed_at = now
        db.add(
            QualityReviewAudit(
                review_id=review.id,
                action="submit_unable",
                actor_id=principal.user_id,
                after_snapshot={"reason": payload.reason, **QualityReviewService._draft_snapshot(draft)},
            )
        )
        await db.commit()
        return await QualityReviewService.detail(db, principal, review.id, allow_assignee=True)

    @staticmethod
    async def reassign(
        db: AsyncSession,
        principal: EffectivePrincipal,
        review_id: int,
        payload: QualityReassignPayload,
    ) -> QualityReviewListItem:
        review = await QualityReviewService._require_review(db, principal, review_id)
        if review.status not in {"pending_human", "human_reviewing"}:
            raise ConflictError("Only pending human reviews can be reassigned")
        plan = await QualityReviewRepository.plan(db, review.plan_id)
        if plan is None or payload.reviewer_id not in plan.reviewer_ids:
            raise ValidationError("Reviewer is not configured for this plan")
        if not await EmployeeRepository.has_effective_permission(
            db,
            principal.tenant_id,
            payload.reviewer_id,
            "quality.online.review.perform",
        ):
            raise ValidationError("Reviewer is no longer eligible")
        reviewer = await PermissionService.get_current_principal(
            db,
            {"user_id": payload.reviewer_id, "tenant_id": principal.tenant_id},
        )
        if not await QualityReviewService._in_scope(db, reviewer, review):
            raise ValidationError("Reviewer cannot access the target agent")
        previous = review.assigned_reviewer_id
        review.assigned_reviewer_id = payload.reviewer_id
        review.status = "pending_human"
        draft = await QualityReviewRepository.draft(db, review.id)
        if draft:
            draft.reviewer_id = payload.reviewer_id
            draft.version += 1
        db.add(
            QualityReviewAudit(
                review_id=review.id,
                action="reassign",
                actor_id=principal.user_id,
                before_snapshot={"reviewer_id": previous},
                after_snapshot={"reviewer_id": payload.reviewer_id},
            )
        )
        await db.commit()
        review = await QualityReviewRepository.review_by_id(
            db, principal.tenant_id, review_id
        )
        assert review is not None
        return QualityReviewService._list_item(review)

    @staticmethod
    async def list_reviews(
        db: AsyncSession,
        principal: EffectivePrincipal,
        plan_id: int,
        *,
        status: str | None,
        source: str | None,
        agent_id: int | None,
        page: int,
        per_page: int,
    ) -> QualityReviewListResponse:
        await QualityReviewService._require_plan(db, principal, plan_id)
        allowed_agent_ids = await QualityReviewService._allowed_agent_ids(db, principal)
        rows, total = await QualityReviewRepository.list_reviews(
            db,
            principal.tenant_id,
            plan_id,
            allowed_agent_ids=allowed_agent_ids,
            status=status,
            source=source,
            agent_id=agent_id,
            page=page,
            per_page=per_page,
        )
        return QualityReviewService._list_response(rows, total, page, per_page)

    @staticmethod
    async def statistics(
        db: AsyncSession, principal: EffectivePrincipal, plan_id: int
    ) -> QualityStatisticsResponse:
        await QualityReviewService._require_plan(db, principal, plan_id)
        rows = await QualityReviewRepository.reviews_for_statistics(
            db,
            principal.tenant_id,
            plan_id,
            allowed_agent_ids=await QualityReviewService._allowed_agent_ids(db, principal),
        )
        scored = [row for row in rows if row.final_score is not None]
        passed = [row for row in scored if row.final_outcome == "passed"]
        return QualityStatisticsResponse(
            total=len(rows),
            ai_completed=sum(row.status == "ai_completed" for row in rows),
            pending_human=sum(row.status in {"pending_human", "human_reviewing"} for row in rows),
            human_completed=sum(row.status == "human_completed" for row in rows),
            unable=sum(row.final_outcome == "unable" for row in rows),
            failed=sum(row.status == "execution_failed" for row in rows),
            average_score=(
                (sum(Decimal(row.final_score) for row in scored) / len(scored)).quantize(Decimal("0.1"))
                if scored
                else None
            ),
            pass_rate=(
                (Decimal(len(passed)) / len(scored) * 100).quantize(Decimal("0.1"))
                if scored
                else None
            ),
        )

    @staticmethod
    async def detail(
        db: AsyncSession,
        principal: EffectivePrincipal,
        review_id: int,
        *,
        allow_assignee: bool = False,
    ) -> QualityReviewDetailResponse:
        review = await QualityReviewService._require_review(db, principal, review_id)
        if not allow_assignee and not principal.has_permission("quality.online.record.view"):
            raise ForbiddenError("Permission denied")
        if not await QualityReviewService._in_scope(db, principal, review):
            raise ForbiddenError("Permission denied")
        draft = await QualityReviewRepository.draft(db, review.id)
        audits = await QualityReviewRepository.audits(db, review.id)
        workbench = QualityReviewService._workbench(review, draft).model_dump()
        return QualityReviewDetailResponse(
            **workbench,
            unable_reason=review.unable_reason,
            audits=[
                {
                    "action": audit.action,
                    "actor_id": audit.actor_id,
                    "before": audit.before_snapshot,
                    "after": audit.after_snapshot,
                    "created_at": audit.created_at,
                }
                for audit in audits
            ],
        )

    @staticmethod
    async def _apply_payload(
        db: AsyncSession,
        review: QualityReview,
        reviewer_id: int | None,
        payload: QualityDraftPayload,
        *,
        increment_version: bool = True,
    ) -> QualityHumanReviewDraft:
        draft = await QualityReviewRepository.draft(db, review.id)
        if draft is None:
            if payload.version != 0:
                raise ConflictError("Review draft was updated; refresh and try again")
            draft = await QualityReviewService._get_or_create_draft(db, review, reviewer_id)
        elif draft.version != payload.version:
            raise ConflictError("Review draft was updated; refresh and try again")
        if draft.status != "draft":
            raise ConflictError("Submitted reviews cannot be edited")
        input_ids = [item.review_item_id for item in payload.items]
        if len(input_ids) != len(set(input_ids)):
            raise ValidationError("Duplicate review items")
        source_items = {item.id: item for item in review.items}
        draft_items = {item.review_item_id: item for item in draft.items}
        valid_evidence = {
            message["id"] for message in review.message_snapshot if not message["is_recalled"]
        }
        for item_input in payload.items:
            source = source_items.get(item_input.review_item_id)
            target = draft_items.get(item_input.review_item_id)
            if source is None or target is None:
                raise ValidationError("Review item does not belong to this review")
            option_ids = {option["id"] for option in source.criterion_snapshot["options"]}
            if item_input.result_type == "option" and item_input.option_id not in option_ids:
                raise ValidationError("Select a valid rating option")
            if item_input.result_type != "option" and item_input.option_id is not None:
                raise ValidationError("System results cannot include an option")
            evidence = list(dict.fromkeys(item_input.evidence_message_ids))
            if not set(evidence).issubset(valid_evidence):
                raise ValidationError("Evidence must reference a non-recalled snapshot message")
            target.result_type = item_input.result_type
            target.option_id = item_input.option_id
            target.judgment = item_input.judgment
            target.change_reason = item_input.change_reason
            target.evidence_message_ids = evidence
        draft.overall_comment = payload.overall_comment
        draft.reviewer_id = reviewer_id
        draft.updated_by_id = reviewer_id
        if increment_version:
            draft.version += 1
        await db.flush()
        return draft

    @staticmethod
    def _validate_and_score(
        review: QualityReview, draft: QualityHumanReviewDraft
    ) -> tuple[Decimal | None, str, int]:
        human = {item.review_item_id: item for item in draft.items}
        results: list[tuple[QualityReviewItem, QualityHumanReviewItem, dict | None]] = []
        for source in review.items:
            target = human[source.id]
            if source.criterion_snapshot["is_required"] and target.result_type == "unanswered":
                raise ValidationError("Complete all required criteria")
            option = next(
                (option for option in source.criterion_snapshot["options"] if option["id"] == target.option_id),
                None,
            )
            if option:
                required = source.criterion_snapshot["evidence_policy"] == "always" or (
                    source.criterion_snapshot["evidence_policy"] == "issue_only"
                    and _SEVERITY[option["severity"]] >= 2
                )
                if required and not target.evidence_message_ids:
                    raise ValidationError("Add the required message evidence")
                if option["severity"] == "fatal" and len((target.judgment or "").strip()) < 10:
                    raise ValidationError("Fatal ratings require a detailed judgment")
            changed = source.result_type in {"option", "not_applicable"} and (
                source.result_type != target.result_type
                or source.option_id != target.option_id
            )
            if changed and len((target.change_reason or "").strip()) < 10:
                raise ValidationError("Explain why the AI rating was changed")
            results.append((source, target, option))
        applicable = [entry for entry in results if entry[2] is not None]
        if not applicable:
            raise ValidationError("Submit this review as unable to evaluate")
        scored = [
            entry for entry in applicable if Decimal(entry[0].criterion_snapshot["max_points"]) > 0
        ]
        score = None
        if scored:
            earned = sum(Decimal(entry[2]["points"]) for entry in scored)
            maximum = sum(Decimal(entry[0].criterion_snapshot["max_points"]) for entry in scored)
            score = (earned / maximum * 100).quantize(Decimal("0.1"))
        maximum_severity = max(_SEVERITY[entry[2]["severity"]] for entry in applicable)
        issue_count = sum(_SEVERITY[entry[2]["severity"]] >= 2 for entry in applicable)
        pass_score = review.conversation_snapshot.get("pass_score")
        outcome = (
            "failed"
            if maximum_severity == 4 or (score is not None and pass_score is not None and score < Decimal(str(pass_score)))
            else "passed"
            if score is not None
            else "issues"
            if issue_count
            else "no_issues"
        )
        return score, outcome, issue_count

    @staticmethod
    async def _get_or_create_draft(
        db: AsyncSession, review: QualityReview, reviewer_id: int | None
    ) -> QualityHumanReviewDraft:
        existing = await QualityReviewRepository.draft(db, review.id)
        if existing:
            return existing
        draft = QualityHumanReviewDraft(
            review_id=review.id,
            reviewer_id=reviewer_id,
            updated_by_id=reviewer_id,
            items=[],
        )
        db.add(draft)
        for source in review.items:
            result_type = source.result_type
            if result_type not in {"option", "not_applicable"}:
                result_type = "unanswered"
            draft.items.append(
                QualityHumanReviewItem(
                    review_item_id=source.id,
                    result_type=result_type,
                    option_id=source.option_id if result_type == "option" else None,
                    evidence_message_ids=(
                        list(source.evidence_message_ids) if result_type != "unanswered" else []
                    ),
                )
            )
        await db.flush()
        return draft

    @staticmethod
    async def _assigned_review(
        db: AsyncSession, principal: EffectivePrincipal, review_id: int
    ) -> QualityReview:
        review = await QualityReviewService._require_review(db, principal, review_id)
        if review.assigned_reviewer_id != principal.user_id:
            raise ForbiddenError("Only the assigned reviewer can edit this review")
        if review.status not in {"pending_human", "human_reviewing"}:
            raise ConflictError("This review is not open for human review")
        if not await QualityReviewService._in_scope(db, principal, review):
            raise ForbiddenError("Permission denied")
        return review

    @staticmethod
    async def _require_review(
        db: AsyncSession, principal: EffectivePrincipal, review_id: int
    ) -> QualityReview:
        review = await QualityReviewRepository.review_by_id(
            db, principal.tenant_id, review_id
        )
        if review is None:
            raise NotFoundError("Quality review not found")
        return review

    @staticmethod
    async def _workbench_after_commit(
        db: AsyncSession, tenant_id: int, review_id: int
    ) -> QualityWorkbenchResponse:
        review = await QualityReviewRepository.review_by_id(db, tenant_id, review_id)
        assert review is not None
        draft = await QualityReviewRepository.draft(db, review.id)
        return QualityReviewService._workbench(review, draft)

    @staticmethod
    async def _require_plan(db: AsyncSession, principal: EffectivePrincipal, plan_id: int):
        plan = await QualityReviewRepository.plan(db, plan_id)
        if plan is None or plan.tenant_id != principal.tenant_id:
            raise NotFoundError("Quality plan not found")
        return plan

    @staticmethod
    async def _in_scope(
        db: AsyncSession, principal: EffectivePrincipal, review: QualityReview
    ) -> bool:
        scope = DataScopeService.get_scope(principal, "session_record")
        if scope == "all":
            return True
        if scope == "self":
            return review.target_agent_id == principal.user_id
        peer_ids = await DataScopeService.get_group_peer_employee_ids(db, principal.group_ids)
        group_id = review.conversation_snapshot.get("group_id")
        return group_id in principal.group_ids or review.target_agent_id in set(peer_ids)

    @staticmethod
    async def _allowed_agent_ids(
        db: AsyncSession, principal: EffectivePrincipal
    ) -> list[int] | None:
        scope = DataScopeService.get_scope(principal, "session_record")
        if scope == "all":
            return None
        if scope == "self":
            return [principal.user_id] if principal.user_id is not None else []
        peers = await DataScopeService.get_group_peer_employee_ids(db, principal.group_ids)
        return sorted(set(peers) | ({principal.user_id} if principal.user_id is not None else set()))

    @staticmethod
    def _list_item(review: QualityReview) -> QualityReviewListItem:
        source = review.final_source
        if source is None and review.ai_outcome is not None and review.status in {"pending_human", "human_reviewing"}:
            source = "ai_pending"
        return QualityReviewListItem(
            id=review.id,
            plan_id=review.plan_id,
            conversation_id=review.conversation_id,
            target_agent_id=review.target_agent_id,
            agent_name=review.conversation_snapshot.get("agent_name"),
            status=review.status,
            result_source=source,
            score=review.final_score,
            outcome=review.final_outcome,
            issue_count=review.final_issue_count,
            route_reasons=review.route_reasons,
            assigned_reviewer_id=review.assigned_reviewer_id,
            created_at=review.created_at,
            completed_at=review.completed_at,
        )

    @staticmethod
    def _list_response(rows, total: int, page: int, per_page: int) -> QualityReviewListResponse:
        return QualityReviewListResponse(
            items=[QualityReviewService._list_item(row) for row in rows],
            total=total,
            page=page,
            per_page=per_page,
            pages=(total + per_page - 1) // per_page,
        )

    @staticmethod
    def _workbench(
        review: QualityReview, draft: QualityHumanReviewDraft | None
    ) -> QualityWorkbenchResponse:
        human = {item.review_item_id: item for item in draft.items} if draft else {}
        items = []
        for source in review.items:
            target = human.get(source.id)
            items.append(
                {
                    "review_item_id": source.id,
                    "criterion": source.criterion_snapshot,
                    "ai": {
                        "result_type": source.result_type,
                        "option_id": source.option_id,
                        "reason": source.reason,
                        "evidence_message_ids": source.evidence_message_ids,
                    },
                    "human": {
                        "review_item_id": source.id,
                        "result_type": target.result_type if target else "unanswered",
                        "option_id": target.option_id if target else None,
                        "judgment": target.judgment if target else None,
                        "change_reason": target.change_reason if target else None,
                        "evidence_message_ids": target.evidence_message_ids if target else [],
                    },
                }
            )
        return QualityWorkbenchResponse(
            review=QualityReviewService._list_item(review),
            conversation_snapshot=review.conversation_snapshot,
            message_snapshot=review.message_snapshot,
            draft_version=draft.version if draft else 0,
            draft_status=draft.status if draft else "new",
            overall_comment=draft.overall_comment if draft else None,
            items=items,
        )

    @staticmethod
    def _draft_snapshot(draft: QualityHumanReviewDraft) -> dict:
        return {
            "version": draft.version,
            "overall_comment": draft.overall_comment,
            "items": [
                {
                    "review_item_id": item.review_item_id,
                    "result_type": item.result_type,
                    "option_id": item.option_id,
                    "judgment": item.judgment,
                    "change_reason": item.change_reason,
                    "evidence_message_ids": item.evidence_message_ids,
                }
                for item in draft.items
            ],
        }
