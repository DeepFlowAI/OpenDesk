"""
Rule-based scheduling orchestration: generation preview/apply and write validation.

Loads DB data, delegates the constraint math to the pure engine, and shapes
API responses. Write validation (hard block / soft warn) is shared by manual
assignment writes, copy-week, and is computed against the tenant's default
rule set.
"""
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessError, NotFoundError, ValidationError
from app.enums import ScheduleShiftType
from app.models.scheduling import ScheduleShift
from app.models.scheduling_rule import ScheduleRuleSet
from app.repositories.scheduling_repository import (
    ScheduleAssignmentRepository,
    ScheduleShiftRepository,
    list_pool_members,
)
from app.repositories.scheduling_rule_repository import ScheduleRuleSetRepository
from app.schemas.scheduling_rule import (
    GenerateApplyResponse,
    GeneratePreviewResponse,
    GenerateRequest,
    GenerateSampleLine,
    ViolationItem,
    ViolationListResponse,
    targets_to_engine_map,
)
from app.services.scheduling_rule_engine import (
    COVERAGE_KEYS,
    AssignmentKey,
    GeneratePlan,
    GenerationAborted,
    ShiftInfo,
    Violation,
    detect_coverage_violations,
    detect_employee_violations,
    detect_fairness_violations,
    generate_plan,
    iter_days,
)

# Extra days of assignment history loaded before the range start so
# consecutive-day / rest-hour checks have the context they need.
CONTEXT_BUFFER_DAYS = 31


def _to_shift_info(shifts: list[ScheduleShift]) -> list[ShiftInfo]:
    return [
        ShiftInfo(
            id=s.id,
            name=s.name,
            start_min=s.start_time.hour * 60 + s.start_time.minute,
            end_min=s.end_time.hour * 60 + s.end_time.minute,
        )
        for s in shifts
    ]


def _is_work_shift(shift: ScheduleShift) -> bool:
    return (shift.shift_type or ScheduleShiftType.WORK.value) == ScheduleShiftType.WORK.value


def _enabled_constraints(rule_set: ScheduleRuleSet) -> dict:
    return {
        key: cfg
        for key, cfg in (rule_set.constraints or {}).items()
        if isinstance(cfg, dict) and cfg.get("enabled")
    }


def _default_template(rule_set: ScheduleRuleSet) -> dict | None:
    templates = rule_set.rotation_templates or []
    for template in templates:
        if template.get("is_default"):
            return template
    return templates[0] if templates else None


def _to_item(
    violation: Violation,
    employee_names: dict[int, str],
    shift_names: dict[int, str],
) -> ViolationItem:
    return ViolationItem(
        level=violation.level,
        constraint=violation.constraint,
        date=violation.date,
        employee_id=violation.employee_id,
        employee_name=(
            employee_names.get(violation.employee_id)
            if violation.employee_id is not None
            else None
        ),
        shift_id=violation.shift_id,
        shift_name=(
            shift_names.get(violation.shift_id) if violation.shift_id is not None else None
        ),
        detail=violation.detail,
    )


class SchedulingPlanService:

    @staticmethod
    async def _load_context(
        db: AsyncSession,
        tenant_id: int,
        group_ids: list[int],
        start: date,
        end: date,
        buffer_days: int = 0,
    ) -> tuple[list[tuple[int, str]], list[ScheduleShift], set[AssignmentKey]]:
        pool_rows = await list_pool_members(db, tenant_id, sorted(set(group_ids)))
        shifts = await ScheduleShiftRepository.list_by_tenant(db, tenant_id)
        records = await ScheduleAssignmentRepository.list_by_date_range(
            db, tenant_id, start - timedelta(days=buffer_days), end
        )
        keys = {(r.employee_id, r.shift_id, r.date) for r in records}
        pool = [(row[0], row[1]) for row in pool_rows]
        return pool, shifts, keys

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    @staticmethod
    async def _build_plan(
        db: AsyncSession,
        tenant_id: int,
        data: GenerateRequest,
    ) -> tuple[
        ScheduleRuleSet,
        list[tuple[int, str]],
        list[ShiftInfo],
        set[int],
        GeneratePlan,
    ]:
        rule_set = await ScheduleRuleSetRepository.get_by_id(db, tenant_id, data.rule_set_id)
        if not rule_set:
            raise NotFoundError("Rule set not found")
        pool, shifts, keys = await SchedulingPlanService._load_context(
            db,
            tenant_id,
            data.group_ids,
            data.start_date,
            data.end_date,
            buffer_days=CONTEXT_BUFFER_DAYS,
        )
        if not pool:
            raise ValidationError("The scheduling pool is empty")
        targets_enabled = bool(getattr(rule_set, "targets_enabled", True))
        template = _default_template(rule_set)
        use_template = data.use_template and template is not None
        if not targets_enabled and not use_template:
            raise ValidationError(
                "Coverage targets are disabled; enable a rotation template "
                "or turn targets back on before generating"
            )
        work_shifts = [s for s in shifts if _is_work_shift(s)]
        work_shift_ids = {s.id for s in work_shifts}
        leave_shift_ids = {s.id for s in shifts if not _is_work_shift(s)}
        work_keys = {key for key in keys if key[1] in work_shift_ids}
        unavailable_emp_dates = {
            (employee_id, day)
            for employee_id, shift_id, day in keys
            if shift_id in leave_shift_ids
        }
        enabled_shifts = [s for s in work_shifts if s.is_enabled]
        shift_infos = _to_shift_info(enabled_shifts)
        try:
            plan = generate_plan(
                pool=pool,
                existing_keys=work_keys,
                shifts=shift_infos,
                targets=targets_to_engine_map(rule_set.targets),
                constraints=_enabled_constraints(rule_set),
                template=template,
                start=data.start_date,
                end=data.end_date,
                mode=data.mode,
                use_template=use_template,
                on_hard_conflict=data.on_hard_conflict,
                targets_enabled=targets_enabled,
                unavailable_emp_dates=unavailable_emp_dates,
            )
        except GenerationAborted as exc:
            violation = exc.violation
            raise ValidationError(
                f"Generation aborted: hard constraint "
                f"'{violation.constraint}' would be violated"
            ) from None
        return rule_set, pool, shift_infos, work_shift_ids, plan

    @staticmethod
    async def preview(
        db: AsyncSession, tenant_id: int, data: GenerateRequest
    ) -> GeneratePreviewResponse:
        rule_set, pool, shift_infos, _, plan = (
            await SchedulingPlanService._build_plan(db, tenant_id, data)
        )
        employee_names = dict(pool)
        shift_names = {s.id: s.name for s in shift_infos}
        shift_order = {s.id: index for index, s in enumerate(shift_infos)}

        soft_items = [
            _to_item(v, employee_names, shift_names) for v in plan.soft_violations[:5]
        ]

        # Preview sample: first changed cells in (date, shift order) order.
        targets = targets_to_engine_map(rule_set.targets)
        sample: list[GenerateSampleLine] = []
        ordered_cells = sorted(
            plan.added_by_cell.items(),
            key=lambda item: (item[0][1], shift_order.get(item[0][0], 0)),
        )
        for (shift_id, day), added in ordered_cells[:10]:
            band = targets.get(shift_id, {})
            target = (band.get("target") or [0] * 7)[day.weekday()]
            min_n = (band.get("min") or [0] * 7)[day.weekday()]
            actual = plan.cell_counts.get((shift_id, day), len(added))
            gap = max(0, min_n - actual) if min_n > 0 else max(0, target - actual)
            sample.append(
                GenerateSampleLine(
                    date=day,
                    shift_id=shift_id,
                    shift_name=shift_names.get(shift_id, ""),
                    added=[employee_names.get(e, str(e)) for e in added],
                    gap=gap,
                )
            )

        return GeneratePreviewResponse(
            to_create=len(plan.to_create),
            to_delete=len(plan.to_delete),
            skipped_cells=plan.skipped_cells,
            leave_skipped=plan.leave_skipped,
            target_met=plan.target_met,
            target_total=plan.target_total,
            hard_count=0,
            soft_count=len(plan.soft_violations),
            hard_violations=[],
            soft_violations=soft_items,
            sample=sample,
        )

    @staticmethod
    async def apply(
        db: AsyncSession, tenant_id: int, data: GenerateRequest
    ) -> GenerateApplyResponse:
        _, pool, _, work_shift_ids, plan = await SchedulingPlanService._build_plan(
            db, tenant_id, data
        )
        deleted = 0
        if plan.to_delete:
            deleted = await ScheduleAssignmentRepository.delete_work_by_employee_dates(
                db,
                tenant_id,
                [emp for emp, _ in pool],
                sorted(work_shift_ids),
                data.start_date,
                data.end_date,
            )
        rows = [
            {
                "tenant_id": tenant_id,
                "employee_id": employee_id,
                "shift_id": shift_id,
                "date": day,
            }
            for employee_id, shift_id, day in plan.to_create
        ]
        created = await ScheduleAssignmentRepository.bulk_create(db, rows)
        return GenerateApplyResponse(created=created, deleted=deleted)

    # ------------------------------------------------------------------
    # Violation queries & write validation
    # ------------------------------------------------------------------

    @staticmethod
    async def list_violations(
        db: AsyncSession,
        tenant_id: int,
        group_ids: list[int],
        start: date,
        end: date,
    ) -> ViolationListResponse:
        rule_set = await ScheduleRuleSetRepository.get_default(db, tenant_id)
        if not rule_set:
            return ViolationListResponse(items=[], hard_count=0, soft_count=0)
        constraints = _enabled_constraints(rule_set)
        if not constraints:
            return ViolationListResponse(items=[], hard_count=0, soft_count=0)

        pool, shifts, keys = await SchedulingPlanService._load_context(
            db, tenant_id, group_ids, start, end, buffer_days=CONTEXT_BUFFER_DAYS
        )
        pool_ids = {emp for emp, _ in pool}
        if not pool_ids:
            return ViolationListResponse(items=[], hard_count=0, soft_count=0)
        work_shifts = [shift for shift in shifts if _is_work_shift(shift)]
        work_shift_ids = {shift.id for shift in work_shifts}
        keys = {key for key in keys if key[1] in work_shift_ids}
        shift_infos = _to_shift_info(work_shifts)
        shift_map = {s.id: s for s in shift_infos}
        days = iter_days(start, end)
        day_set = set(days)

        employee_violations = [
            v
            for v in detect_employee_violations(keys, shift_map, constraints, pool_ids)
            if v.date in day_set or any(d in day_set for d in v.related_dates)
        ]
        targets_enabled = bool(getattr(rule_set, "targets_enabled", True))
        violations = (
            employee_violations
            + detect_coverage_violations(
                keys,
                shift_infos,
                constraints,
                targets_to_engine_map(rule_set.targets),
                days,
                pool_ids,
                targets_enabled=targets_enabled,
            )
            + detect_fairness_violations(keys, constraints, days, pool_ids)
        )
        violations.sort(key=lambda v: (v.level != "hard", v.date, v.constraint))

        employee_names = dict(pool)
        shift_names = {s.id: s.name for s in shift_infos}
        items = [_to_item(v, employee_names, shift_names) for v in violations]
        return ViolationListResponse(
            items=items,
            hard_count=sum(1 for v in violations if v.level == "hard"),
            soft_count=sum(1 for v in violations if v.level != "hard"),
        )

    @staticmethod
    async def validate_write(
        db: AsyncSession,
        tenant_id: int,
        group_ids: list[int],
        candidate_keys: set[AssignmentKey],
        deleted_keys: set[AssignmentKey] | None = None,
        allow_soft: bool = False,
    ) -> None:
        """Hard-block / soft-warn validation for manual writes and copy-week.

        Simulates the post-write state against the tenant's default rule set
        and raises 409 with violation details when constraints are broken.
        """
        if not candidate_keys:
            return
        rule_set = await ScheduleRuleSetRepository.get_default(db, tenant_id)
        if not rule_set:
            return
        constraints = _enabled_constraints(rule_set)
        if not constraints:
            return

        dates = [day for _, _, day in candidate_keys]
        min_date, max_date = min(dates), max(dates)
        pool, shifts, existing = await SchedulingPlanService._load_context(
            db,
            tenant_id,
            group_ids,
            min_date,
            max_date,
            buffer_days=CONTEXT_BUFFER_DAYS,
        )
        pool_ids = {emp for emp, _ in pool}
        work_shifts = [shift for shift in shifts if _is_work_shift(shift)]
        work_shift_ids = {shift.id for shift in work_shifts}
        candidate_keys = {key for key in candidate_keys if key[1] in work_shift_ids}
        if not candidate_keys:
            return
        existing = {key for key in existing if key[1] in work_shift_ids}
        deleted_keys = {
            key for key in (deleted_keys or set()) if key[1] in work_shift_ids
        }
        simulated = (existing - deleted_keys) | set(candidate_keys)

        shift_infos = _to_shift_info(work_shifts)
        shift_map = {s.id: s for s in shift_infos}
        employee_ids = {emp for emp, _, _ in candidate_keys}
        violations = detect_employee_violations(
            simulated, shift_map, constraints, employee_ids
        )
        candidate_cells = {(shift_id, day) for _, shift_id, day in candidate_keys}
        violations += detect_coverage_violations(
            simulated,
            shift_infos,
            constraints,
            targets_to_engine_map(rule_set.targets),
            iter_days(min_date, max_date),
            pool_ids,
            cells=candidate_cells,
            targets_enabled=bool(getattr(rule_set, "targets_enabled", True)),
        )

        candidate_emp_dates = {(emp, day) for emp, _, day in candidate_keys}

        def is_relevant(v: Violation) -> bool:
            if v.constraint in COVERAGE_KEYS:
                return (v.shift_id, v.date) in candidate_cells
            if (v.employee_id, v.date) in candidate_emp_dates:
                return True
            return any(
                (v.employee_id, day) in candidate_emp_dates for day in v.related_dates
            )

        relevant = [v for v in violations if is_relevant(v)]
        hard = [v for v in relevant if v.level == "hard"]
        soft = [v for v in relevant if v.level != "hard"]

        employee_names = dict(pool)
        shift_names = {s.id: s.name for s in shift_infos}

        def details(items: list[Violation]) -> dict:
            return {
                "violations": [
                    _to_item(v, employee_names, shift_names).model_dump(mode="json")
                    for v in items[:20]
                ]
            }

        if hard:
            raise BusinessError(
                "The change violates hard scheduling constraints",
                status_code=409,
                code="RULE_HARD_VIOLATION",
                details=details(hard),
            )
        if soft and not allow_soft:
            raise BusinessError(
                "The change triggers soft scheduling constraints",
                status_code=409,
                code="RULE_SOFT_VIOLATION",
                details=details(soft),
            )
