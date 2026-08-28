"""
Scheduling Center router: shift templates, scheduling pool, and assignments.

All endpoints require the ``scheduling.center.manage`` permission.
"""
from datetime import date

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import EffectivePrincipal, get_db, require_permission
from app.libs.excel import XLSX_MEDIA_TYPE, xlsx_content_disposition
from app.repositories.system_settings_repository import SystemSettingsRepository
from app.schemas.scheduling import (
    AssignmentBulkCreateRequest,
    AssignmentBulkCreateResponse,
    AssignmentBulkDeleteRequest,
    AssignmentBulkDeleteResponse,
    AssignmentListResponse,
    CopyWeekRequest,
    CopyWeekResponse,
    MessageResponse,
    MyScheduleResponse,
    PoolMemberListResponse,
    PublishRequest,
    PublishResetResponse,
    PublishStatusResponse,
    ShiftCreate,
    ShiftListResponse,
    ShiftResponse,
    ShiftUpdate,
)
from app.schemas.scheduling_rule import (
    GenerateApplyResponse,
    GeneratePreviewResponse,
    GenerateRequest,
    RuleSetCreate,
    RuleSetListResponse,
    RuleSetResponse,
    RuleSetUpdate,
    ViolationListResponse,
)
from app.services.scheduling_plan_service import SchedulingPlanService
from app.services.scheduling_my_service import SchedulingMyService
from app.services.scheduling_publish_service import SchedulingPublishService
from app.services.scheduling_rule_service import SchedulingRuleService
from app.services.scheduling_service import SchedulingService

router = APIRouter(prefix="/scheduling", tags=["Scheduling"])

ManageDep = Depends(require_permission("scheduling.center.manage"))
MyViewDep = Depends(require_permission("scheduling.my.view"))


@router.get("/me", response_model=MyScheduleResponse)
async def get_my_schedule(
    week: date | None = None,
    principal: EffectivePrincipal = MyViewDep,
    db: AsyncSession = Depends(get_db),
) -> MyScheduleResponse:
    """Return only the current employee's published schedule for one week."""
    return await SchedulingMyService.get_week(
        db,
        tenant_id=principal.tenant_id,
        employee_id=principal.user_id,
        requested_week=week,
    )


@router.get("/shifts", response_model=ShiftListResponse)
async def list_shifts(
    principal: EffectivePrincipal = ManageDep,
    db: AsyncSession = Depends(get_db),
) -> ShiftListResponse:
    """List all shift templates of the tenant (enabled and disabled)."""
    items = await SchedulingService.list_shifts(db, tenant_id=principal.tenant_id)
    return ShiftListResponse(items=items)


@router.post("/shifts", response_model=ShiftResponse, status_code=status.HTTP_201_CREATED)
async def create_shift(
    body: ShiftCreate,
    principal: EffectivePrincipal = ManageDep,
    db: AsyncSession = Depends(get_db),
) -> ShiftResponse:
    """Create a shift template."""
    return await SchedulingService.create_shift(db, tenant_id=principal.tenant_id, data=body)


@router.put("/shifts/{shift_id}", response_model=ShiftResponse)
async def update_shift(
    shift_id: int,
    body: ShiftUpdate,
    principal: EffectivePrincipal = ManageDep,
    db: AsyncSession = Depends(get_db),
) -> ShiftResponse:
    """Update a shift template (including enable/disable)."""
    return await SchedulingService.update_shift(
        db, tenant_id=principal.tenant_id, shift_id=shift_id, data=body
    )


@router.delete("/shifts/{shift_id}", response_model=MessageResponse)
async def delete_shift(
    shift_id: int,
    principal: EffectivePrincipal = ManageDep,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Delete a shift template; rejected while assignments still reference it."""
    await SchedulingService.delete_shift(db, tenant_id=principal.tenant_id, shift_id=shift_id)
    return MessageResponse(message="Deleted successfully")


@router.get("/pool-members", response_model=PoolMemberListResponse)
async def get_pool_members(
    group_ids: list[int] = Query(min_length=1),
    principal: EffectivePrincipal = ManageDep,
    db: AsyncSession = Depends(get_db),
) -> PoolMemberListResponse:
    """Resolve the scheduling pool: distinct active members of the given groups."""
    items = await SchedulingService.list_pool(
        db, tenant_id=principal.tenant_id, group_ids=group_ids
    )
    return PoolMemberListResponse(items=items)


@router.get("/assignments", response_model=AssignmentListResponse)
async def list_assignments(
    start_date: date,
    end_date: date,
    principal: EffectivePrincipal = ManageDep,
    db: AsyncSession = Depends(get_db),
) -> AssignmentListResponse:
    """List assignments in a date range (not filtered by the current pool)."""
    items = await SchedulingService.list_assignments(
        db, tenant_id=principal.tenant_id, start_date=start_date, end_date=end_date
    )
    return AssignmentListResponse(items=items)


@router.post(
    "/assignments",
    response_model=AssignmentBulkCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_assignments(
    body: AssignmentBulkCreateRequest,
    principal: EffectivePrincipal = ManageDep,
    db: AsyncSession = Depends(get_db),
) -> AssignmentBulkCreateResponse:
    """Bulk-write assignments; existing (employee, shift, date) rows are skipped."""
    created, skipped, replaced = await SchedulingService.create_assignments(
        db, tenant_id=principal.tenant_id, data=body
    )
    return AssignmentBulkCreateResponse(
        created=created, skipped=skipped, replaced=replaced
    )


@router.delete("/assignments", response_model=AssignmentBulkDeleteResponse)
async def delete_assignments(
    body: AssignmentBulkDeleteRequest,
    principal: EffectivePrincipal = ManageDep,
    db: AsyncSession = Depends(get_db),
) -> AssignmentBulkDeleteResponse:
    """Bulk-delete assignments by record ids."""
    deleted = await SchedulingService.delete_assignments(
        db, tenant_id=principal.tenant_id, ids=body.ids
    )
    return AssignmentBulkDeleteResponse(deleted=deleted)


@router.post("/assignments/copy-week", response_model=CopyWeekResponse)
async def copy_week(
    body: CopyWeekRequest,
    principal: EffectivePrincipal = ManageDep,
    db: AsyncSession = Depends(get_db),
) -> CopyWeekResponse:
    """Copy last week's pool assignments into the target week (skip/overwrite)."""
    copied, skipped_cells, skipped_leave_conflicts = (
        await SchedulingService.copy_week(
            db, tenant_id=principal.tenant_id, data=body
        )
    )
    return CopyWeekResponse(
        copied=copied,
        skipped_cells=skipped_cells,
        skipped_leave_conflicts=skipped_leave_conflicts,
    )


@router.get("/rule-sets", response_model=RuleSetListResponse)
async def list_rule_sets(
    principal: EffectivePrincipal = ManageDep,
    db: AsyncSession = Depends(get_db),
) -> RuleSetListResponse:
    """List all scheduling rule sets of the tenant."""
    items = await SchedulingRuleService.list_rule_sets(db, tenant_id=principal.tenant_id)
    return RuleSetListResponse(items=items)


@router.post("/rule-sets", response_model=RuleSetResponse, status_code=status.HTTP_201_CREATED)
async def create_rule_set(
    body: RuleSetCreate,
    principal: EffectivePrincipal = ManageDep,
    db: AsyncSession = Depends(get_db),
) -> RuleSetResponse:
    """Create a rule set; the tenant's first rule set becomes the default."""
    return await SchedulingRuleService.create_rule_set(db, tenant_id=principal.tenant_id, data=body)


@router.get("/rule-sets/{rule_set_id}", response_model=RuleSetResponse)
async def get_rule_set(
    rule_set_id: int,
    principal: EffectivePrincipal = ManageDep,
    db: AsyncSession = Depends(get_db),
) -> RuleSetResponse:
    """Get a rule set by id."""
    return await SchedulingRuleService.get_rule_set(
        db, tenant_id=principal.tenant_id, rule_set_id=rule_set_id
    )


@router.put("/rule-sets/{rule_set_id}", response_model=RuleSetResponse)
async def update_rule_set(
    rule_set_id: int,
    body: RuleSetUpdate,
    principal: EffectivePrincipal = ManageDep,
    db: AsyncSession = Depends(get_db),
) -> RuleSetResponse:
    """Update a rule set (basic info, targets, constraints, rotation templates)."""
    return await SchedulingRuleService.update_rule_set(
        db, tenant_id=principal.tenant_id, rule_set_id=rule_set_id, data=body
    )


@router.delete("/rule-sets/{rule_set_id}", response_model=MessageResponse)
async def delete_rule_set(
    rule_set_id: int,
    principal: EffectivePrincipal = ManageDep,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Delete a rule set; the default one must hand over default first."""
    await SchedulingRuleService.delete_rule_set(db, tenant_id=principal.tenant_id, rule_set_id=rule_set_id)
    return MessageResponse(message="Deleted successfully")


@router.post(
    "/rule-sets/{rule_set_id}/copy",
    response_model=RuleSetResponse,
    status_code=status.HTTP_201_CREATED,
)
async def copy_rule_set(
    rule_set_id: int,
    principal: EffectivePrincipal = ManageDep,
    db: AsyncSession = Depends(get_db),
) -> RuleSetResponse:
    """Copy a rule set as "{name} 副本" (never default)."""
    return await SchedulingRuleService.copy_rule_set(
        db, tenant_id=principal.tenant_id, rule_set_id=rule_set_id
    )


@router.post("/rule-sets/{rule_set_id}/set-default", response_model=RuleSetResponse)
async def set_rule_set_default(
    rule_set_id: int,
    principal: EffectivePrincipal = ManageDep,
    db: AsyncSession = Depends(get_db),
) -> RuleSetResponse:
    """Mark a rule set as the tenant default (clears the previous default)."""
    return await SchedulingRuleService.set_default(
        db, tenant_id=principal.tenant_id, rule_set_id=rule_set_id
    )


@router.post("/generate/preview", response_model=GeneratePreviewResponse)
async def generate_preview(
    body: GenerateRequest,
    principal: EffectivePrincipal = ManageDep,
    db: AsyncSession = Depends(get_db),
) -> GeneratePreviewResponse:
    """Preview rule-based generation; nothing is written."""
    return await SchedulingPlanService.preview(db, tenant_id=principal.tenant_id, data=body)


@router.post("/generate/apply", response_model=GenerateApplyResponse)
async def generate_apply(
    body: GenerateRequest,
    principal: EffectivePrincipal = ManageDep,
    db: AsyncSession = Depends(get_db),
) -> GenerateApplyResponse:
    """Write the rule-based generation plan into the draft schedule."""
    return await SchedulingPlanService.apply(db, tenant_id=principal.tenant_id, data=body)


@router.get("/violations", response_model=ViolationListResponse)
async def list_violations(
    start_date: date,
    end_date: date,
    group_ids: list[int] = Query(min_length=1),
    principal: EffectivePrincipal = ManageDep,
    db: AsyncSession = Depends(get_db),
) -> ViolationListResponse:
    """Validate the draft schedule against the tenant's default rule set."""
    return await SchedulingPlanService.list_violations(
        db,
        tenant_id=principal.tenant_id,
        group_ids=group_ids,
        start=start_date,
        end=end_date,
    )


@router.get("/publish-status", response_model=PublishStatusResponse)
async def get_publish_status(
    date: date,
    principal: EffectivePrincipal = ManageDep,
    db: AsyncSession = Depends(get_db),
) -> PublishStatusResponse:
    """Publish state of the calendar week containing ``date``."""
    return await SchedulingPublishService.get_status(
        db, tenant_id=principal.tenant_id, day=date
    )


@router.post("/publish", response_model=PublishStatusResponse)
async def publish_week(
    body: PublishRequest,
    principal: EffectivePrincipal = ManageDep,
    db: AsyncSession = Depends(get_db),
) -> PublishStatusResponse:
    """Freeze the week's draft assignments as the published snapshot."""
    return await SchedulingPublishService.publish(
        db,
        tenant_id=principal.tenant_id,
        day=body.date,
        published_by=principal.user_id,
    )


@router.post("/reset", response_model=PublishResetResponse)
async def reset_week(
    body: PublishRequest,
    principal: EffectivePrincipal = ManageDep,
    db: AsyncSession = Depends(get_db),
) -> PublishResetResponse:
    """Overwrite the week's draft assignments with the published snapshot."""
    return await SchedulingPublishService.reset(
        db, tenant_id=principal.tenant_id, day=body.date
    )


@router.get("/export.xlsx")
async def export_assignments(
    start_date: date,
    end_date: date,
    group_ids: list[int] = Query(min_length=1),
    principal: EffectivePrincipal = ManageDep,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Download the schedule workbook (shift×day, employee×day, detail sheets)."""
    settings = await SystemSettingsRepository.get_by_tenant_id(db, principal.tenant_id)
    lang = settings.default_language if settings else "zh"
    content, filename = await SchedulingService.export_assignments_xlsx(
        db,
        tenant_id=principal.tenant_id,
        start_date=start_date,
        end_date=end_date,
        group_ids=group_ids,
        lang=lang,
    )
    return Response(
        content=content,
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": xlsx_content_disposition(filename)},
    )
