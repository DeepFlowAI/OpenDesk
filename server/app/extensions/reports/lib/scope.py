"""Data scope helpers for report and monitor aggregations."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.permission import EffectivePrincipal
from app.services.data_scope_service import (
    DataScopeService,
    SCOPE_ALL,
    SCOPE_SELF,
)


@dataclass(frozen=True)
class ReportScope:
    employee_id: int | None
    agent_ids: list[int] | None
    visible_employee_ids: list[int] | None


async def build_report_scope(
    db: AsyncSession,
    principal: EffectivePrincipal,
    resource: str,
    requested_employee_id: int | None = None,
) -> ReportScope:
    peer_ids = await DataScopeService.get_group_peer_employee_ids(db, principal.group_ids)

    if requested_employee_id is not None:
        resolved = DataScopeService.resolve_agent_filter(
            principal,
            resource,
            requested_employee_id,
            peer_ids,
        )
        if resolved is None:
            return ReportScope(employee_id=None, agent_ids=[], visible_employee_ids=[])
        return ReportScope(
            employee_id=resolved,
            agent_ids=[resolved],
            visible_employee_ids=[resolved],
        )

    scope = DataScopeService.get_scope(principal, resource)
    if scope == SCOPE_ALL:
        return ReportScope(employee_id=None, agent_ids=None, visible_employee_ids=None)
    if scope == SCOPE_SELF:
        return ReportScope(
            employee_id=principal.user_id,
            agent_ids=[principal.user_id],
            visible_employee_ids=[principal.user_id],
        )

    allowed = sorted(set(peer_ids) | {principal.user_id})
    return ReportScope(
        employee_id=None,
        agent_ids=allowed,
        visible_employee_ids=allowed,
    )
