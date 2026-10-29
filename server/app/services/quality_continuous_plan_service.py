"""Discover newly ended conversations for active continuous quality plans."""
from datetime import datetime, timezone

from app.db.session import AsyncSessionLocal
from app.repositories.quality_plan_repository import QualityPlanRepository
from app.schemas.permission import EffectivePrincipal
from app.services.quality_plan_service import QualityPlanService
from app.services.quality_review_execution_service import QualityReviewExecutionService


class QualityContinuousPlanService:
    @staticmethod
    async def run_tick() -> dict[str, int]:
        discovered = reviews = calls = 0
        async with AsyncSessionLocal() as db:
            plans = await QualityPlanRepository.running_continuous(db)
            for plan in plans:
                now = datetime.now(timezone.utc)
                snapshot = plan.scope_snapshot or {}
                scope = snapshot.get("scope", "self")
                scope_groups = snapshot.get("group_ids", [])
                creator_id = snapshot.get("created_by_id")
                agent_ids = plan.agent_ids
                if scope == "self":
                    agent_ids = [creator_id] if creator_id is not None else []
                rows = await QualityPlanRepository.candidate_segments(
                    db,
                    plan.tenant_id,
                    start_at=plan.last_candidate_scan_at or plan.activated_at,
                    end_at=now,
                    group_ids=plan.group_ids,
                    agent_ids=agent_ids,
                    scope=scope,
                    scope_group_ids=scope_groups,
                )
                grouped: dict[tuple[int, int], list] = {}
                for segment, conversation in rows:
                    grouped.setdefault((conversation.id, int(segment.agent_id)), []).append(
                        (segment, conversation)
                    )
                values = []
                for (conversation_id, agent_id), entries in grouped.items():
                    if not QualityPlanService._is_sampled(plan, conversation_id, agent_id):
                        continue
                    segment, conversation = entries[0]
                    values.append(
                        {
                            "plan_id": plan.id,
                            "conversation_id": conversation_id,
                            "target_agent_id": agent_id,
                            "segment_ids": [entry[0].id for entry in entries],
                            "agent_name_snapshot": segment.agent_name_snapshot,
                            "group_id_snapshot": segment.group_id,
                            "group_name_snapshot": segment.group_name_snapshot,
                            "conversation_ended_at": conversation.ended_at,
                            "sampled": True,
                            "sample_value": QualityPlanService.stable_sample_value(
                                plan.id, conversation_id, agent_id
                            ),
                            "status": "pending",
                        }
                    )
                discovered += await QualityPlanRepository.insert_candidates_ignore(db, values)
                result = await QualityReviewExecutionService.materialize(
                    db,
                    EffectivePrincipal(
                        user_id=creator_id,
                        tenant_id=plan.tenant_id,
                        is_super_admin=True,
                    ),
                    plan.id,
                )
                reviews += result.created_reviews
                calls += result.queued_calls
                plan.last_candidate_scan_at = now
                await db.commit()
        return {"candidates": discovered, "reviews": reviews, "calls": calls}
