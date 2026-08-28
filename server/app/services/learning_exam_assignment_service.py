"""
Learning center exam assignment service: visibility switching, assignment
target CRUD, assignable pickers and the learner results table.
"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessError, NotFoundError
from app.models.learning import (
    ASSIGNMENT_TARGET_EMPLOYEE,
    ASSIGNMENT_TARGET_GROUP,
    VISIBILITY_ALL,
)
from app.models.learning_exam import LearningExam
from app.repositories.learning_exam_repository import (
    LearningExamAssignmentRepository,
    LearningExamAttemptRepository,
    LearningExamRepository,
)
from app.repositories.learning_repository import LearningAssignmentRepository
from app.services.learning_exam_admin_service import pass_score_of


class LearningExamAssignmentService:
    @staticmethod
    async def update_visibility(
        db: AsyncSession, *, tenant_id: int, exam_id: int, visibility: str
    ) -> LearningExam:
        exam = await _get_exam_or_404(db, tenant_id, exam_id)
        return await LearningExamRepository.update(db, exam, {"visibility": visibility})

    @staticmethod
    async def list_assignments(db: AsyncSession, *, tenant_id: int, exam_id: int) -> list[dict]:
        await _get_exam_or_404(db, tenant_id, exam_id)
        assignments = await LearningExamAssignmentRepository.list_by_exam(db, exam_id)
        group_ids = [a.target_id for a in assignments if a.target_type == ASSIGNMENT_TARGET_GROUP]
        employee_ids = [a.target_id for a in assignments if a.target_type == ASSIGNMENT_TARGET_EMPLOYEE]
        groups = await LearningAssignmentRepository.get_groups_by_ids(db, tenant_id, group_ids)
        employees = await LearningAssignmentRepository.get_employees_by_ids(db, tenant_id, employee_ids)
        member_counts = await LearningAssignmentRepository.count_active_members_by_groups(
            db, tenant_id, group_ids
        )
        group_names = await LearningAssignmentRepository.list_group_names_by_employees(
            db, tenant_id, employee_ids
        )

        items = []
        for row in assignments:
            if row.target_type == ASSIGNMENT_TARGET_GROUP:
                group = groups.get(row.target_id)
                if group is None:
                    continue
                items.append(
                    {
                        "id": row.id,
                        "target_type": row.target_type,
                        "target_id": row.target_id,
                        "name": group.name,
                        "detail": member_counts.get(group.id, 0),
                    }
                )
            else:
                employee = employees.get(row.target_id)
                if employee is None:
                    continue
                items.append(
                    {
                        "id": row.id,
                        "target_type": row.target_type,
                        "target_id": row.target_id,
                        "name": employee.name,
                        "detail": "、".join(group_names.get(employee.id, [])) or None,
                    }
                )
        return items

    @staticmethod
    async def add_assignments(
        db: AsyncSession, *, tenant_id: int, exam_id: int, targets: list
    ) -> int:
        await _get_exam_or_404(db, tenant_id, exam_id)
        group_ids = [t.target_id for t in targets if t.target_type == ASSIGNMENT_TARGET_GROUP]
        employee_ids = [t.target_id for t in targets if t.target_type == ASSIGNMENT_TARGET_EMPLOYEE]
        groups = await LearningAssignmentRepository.get_groups_by_ids(db, tenant_id, group_ids)
        employees = await LearningAssignmentRepository.get_employees_by_ids(db, tenant_id, employee_ids)
        for target in targets:
            found = (
                target.target_id in groups
                if target.target_type == ASSIGNMENT_TARGET_GROUP
                else target.target_id in employees
            )
            if not found:
                raise BusinessError(
                    "Assignment target not found",
                    status_code=400,
                    code="INVALID_ASSIGNMENT_TARGET",
                )

        existing = await LearningExamAssignmentRepository.list_existing_pairs(db, exam_id)
        rows = []
        for target in targets:
            pair = (target.target_type, target.target_id)
            if pair in existing:
                continue
            existing.add(pair)
            rows.append(
                {
                    "tenant_id": tenant_id,
                    "exam_id": exam_id,
                    "target_type": target.target_type,
                    "target_id": target.target_id,
                }
            )
        if rows:
            await LearningExamAssignmentRepository.add_many(db, rows)
        return len(rows)

    @staticmethod
    async def remove_assignment(
        db: AsyncSession, *, tenant_id: int, exam_id: int, assignment_id: int
    ) -> None:
        await _get_exam_or_404(db, tenant_id, exam_id)
        assignment = await LearningExamAssignmentRepository.get_by_id(db, tenant_id, assignment_id)
        if assignment is None or assignment.exam_id != exam_id:
            raise NotFoundError("Assignment not found")
        await LearningExamAssignmentRepository.delete(db, assignment)

    @staticmethod
    async def list_assignable_groups(
        db: AsyncSession, *, tenant_id: int, exam_id: int, q: str | None
    ) -> list[dict]:
        await _get_exam_or_404(db, tenant_id, exam_id)
        existing = await LearningExamAssignmentRepository.list_existing_pairs(db, exam_id)
        rows = await LearningAssignmentRepository.list_groups_with_member_counts(db, tenant_id, q)
        return [
            {
                "id": group.id,
                "name": group.name,
                "active_member_count": count,
                "added": (ASSIGNMENT_TARGET_GROUP, group.id) in existing,
            }
            for group, count in rows
        ]

    @staticmethod
    async def list_assignable_employees(
        db: AsyncSession, *, tenant_id: int, exam_id: int, q: str | None, page: int, per_page: int
    ) -> dict:
        await _get_exam_or_404(db, tenant_id, exam_id)
        employees = await LearningAssignmentRepository.list_active_employees(db, tenant_id, q)
        existing = await LearningExamAssignmentRepository.list_existing_pairs(db, exam_id)
        covered = await LearningExamAssignmentRepository.list_visible_employee_ids(db, tenant_id, exam_id)
        direct_ids = {target_id for (t, target_id) in existing if t == ASSIGNMENT_TARGET_EMPLOYEE}

        group_names = await LearningAssignmentRepository.list_group_names_by_employees(
            db, tenant_id, {employee.id for employee in employees}
        )
        total = len(employees)
        window = employees[(page - 1) * per_page : page * per_page]
        items = [
            {
                "id": employee.id,
                "name": employee.name,
                "group_names": group_names.get(employee.id, []),
                "assigned": employee.id in direct_ids,
                "covered": employee.id in covered and employee.id not in direct_ids,
            }
            for employee in window
        ]
        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": (total + per_page - 1) // per_page if per_page else 0,
        }

    @staticmethod
    async def list_results(
        db: AsyncSession, *, tenant_id: int, exam_id: int, q: str | None, page: int, per_page: int
    ) -> dict:
        """Learner results table: best score / status / attempt count per employee."""
        exam = await _get_exam_or_404(db, tenant_id, exam_id)
        stats = (await LearningExamRepository.aggregate_questions_by_exam(db, [exam.id])).get(
            exam.id, {"question_count": 0, "total_score": 0}
        )
        pass_score = pass_score_of(stats["total_score"], exam.pass_percent)

        if exam.visibility == VISIBILITY_ALL:
            employees = await LearningAssignmentRepository.list_active_employees(db, tenant_id, q)
            direct_ids: set[int] = set()
            assigned_groups: dict[int, list[str]] = {}
        else:
            visible_ids = await LearningExamAssignmentRepository.list_visible_employee_ids(
                db, tenant_id, exam.id
            )
            employees_map = await LearningAssignmentRepository.get_employees_by_ids(
                db, tenant_id, visible_ids
            )
            employees = sorted(employees_map.values(), key=lambda item: item.id)
            if q:
                keyword = q.lower()
                employees = [item for item in employees if keyword in item.name.lower()]
            existing = await LearningExamAssignmentRepository.list_existing_pairs(db, exam.id)
            direct_ids = {target_id for (t, target_id) in existing if t == ASSIGNMENT_TARGET_EMPLOYEE}
            assigned_groups = await _assigned_group_names_by_employee(db, tenant_id, exam.id)

        employee_ids = {employee.id for employee in employees}
        aggregates = await LearningExamAttemptRepository.aggregate_by_exam(db, exam.id, employee_ids)
        group_names = await LearningAssignmentRepository.list_group_names_by_employees(
            db, tenant_id, employee_ids
        )

        items = []
        for employee in employees:
            agg = aggregates.get(
                employee.id, {"submitted_count": 0, "best_score": None, "last_submitted_at": None}
            )
            best_score = agg["best_score"]
            if best_score is None:
                result_status = "not_started"
            elif best_score >= pass_score:
                result_status = "passed"
            else:
                result_status = "failed"
            items.append(
                {
                    "employee_id": employee.id,
                    "name": employee.name,
                    "group_names": group_names.get(employee.id, []),
                    "direct_assigned": employee.id in direct_ids,
                    "assigned_group_names": assigned_groups.get(employee.id, []),
                    "best_score": best_score,
                    "status": result_status,
                    "submitted_count": agg["submitted_count"],
                    "last_submitted_at": agg["last_submitted_at"],
                }
            )

        total = len(items)
        window = items[(page - 1) * per_page : page * per_page]
        return {
            "items": window,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": (total + per_page - 1) // per_page if per_page else 0,
        }


async def _assigned_group_names_by_employee(
    db: AsyncSession, tenant_id: int, exam_id: int
) -> dict[int, list[str]]:
    """Map active employee id -> names of this exam's assigned groups they belong to."""
    from sqlalchemy import select

    from app.models.employee import Employee
    from app.models.employee_group import EmployeeGroup, EmployeeGroupMember

    assignments = await LearningExamAssignmentRepository.list_by_exam(db, exam_id)
    group_ids = [a.target_id for a in assignments if a.target_type == ASSIGNMENT_TARGET_GROUP]
    if not group_ids:
        return {}
    result = await db.execute(
        select(EmployeeGroupMember.employee_id, EmployeeGroup.name)
        .join(EmployeeGroup, EmployeeGroup.id == EmployeeGroupMember.group_id)
        .join(Employee, Employee.id == EmployeeGroupMember.employee_id)
        .where(
            EmployeeGroupMember.group_id.in_(group_ids),
            EmployeeGroup.tenant_id == tenant_id,
            Employee.tenant_id == tenant_id,
            Employee.is_active.is_(True),
        )
        .order_by(EmployeeGroup.id.asc())
    )
    mapping: dict[int, list[str]] = {}
    for employee_id, group_name in result.all():
        mapping.setdefault(employee_id, []).append(group_name)
    return mapping


async def _get_exam_or_404(db: AsyncSession, tenant_id: int, exam_id: int) -> LearningExam:
    exam = await LearningExamRepository.get_by_id(db, tenant_id, exam_id)
    if exam is None:
        raise NotFoundError("Exam not found")
    return exam
