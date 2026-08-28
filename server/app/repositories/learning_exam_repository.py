"""
Learning center exam repositories: data access for exams, questions,
assignments and attempts.
"""
from sqlalchemy import case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee
from app.models.employee_group import EmployeeGroupMember
from app.models.learning import ASSIGNMENT_TARGET_EMPLOYEE, ASSIGNMENT_TARGET_GROUP
from app.models.learning_exam import (
    ATTEMPT_STATUS_ABANDONED,
    ATTEMPT_STATUS_IN_PROGRESS,
    ATTEMPT_STATUS_SUBMITTED,
    LearningExam,
    LearningExamAssignment,
    LearningExamAttempt,
    LearningExamQuestion,
)


class LearningExamRepository:
    @staticmethod
    async def get_by_id(db: AsyncSession, tenant_id: int, exam_id: int) -> LearningExam | None:
        result = await db.execute(
            select(LearningExam).where(
                LearningExam.id == exam_id,
                LearningExam.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_paginated(
        db: AsyncSession,
        tenant_id: int,
        page: int,
        per_page: int,
        q: str | None = None,
        status: str | None = None,
    ) -> tuple[list[LearningExam], int]:
        base = select(LearningExam).where(LearningExam.tenant_id == tenant_id)
        if q:
            base = base.where(LearningExam.name.ilike(f"%{q}%"))
        if status:
            base = base.where(LearningExam.status == status)

        total_result = await db.execute(select(func.count()).select_from(base.subquery()))
        total = total_result.scalar_one()

        result = await db.execute(
            base.order_by(LearningExam.updated_at.desc()).offset((page - 1) * per_page).limit(per_page)
        )
        return list(result.scalars().all()), total

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> LearningExam:
        exam = LearningExam(**data)
        db.add(exam)
        await db.commit()
        await db.refresh(exam)
        return exam

    @staticmethod
    async def update(db: AsyncSession, exam: LearningExam, data: dict) -> LearningExam:
        for key, value in data.items():
            setattr(exam, key, value)
        await db.commit()
        await db.refresh(exam)
        return exam

    @staticmethod
    async def delete(db: AsyncSession, exam: LearningExam) -> None:
        await db.delete(exam)
        await db.commit()

    @staticmethod
    async def aggregate_questions_by_exam(db: AsyncSession, exam_ids: list[int]) -> dict[int, dict]:
        """Per-exam question count and total score."""
        if not exam_ids:
            return {}
        result = await db.execute(
            select(
                LearningExamQuestion.exam_id,
                func.count().label("question_count"),
                func.coalesce(func.sum(LearningExamQuestion.score), 0).label("total_score"),
            )
            .where(LearningExamQuestion.exam_id.in_(exam_ids))
            .group_by(LearningExamQuestion.exam_id)
        )
        return {row[0]: {"question_count": row[1], "total_score": row[2]} for row in result.all()}


class LearningExamQuestionRepository:
    @staticmethod
    async def get_by_id(db: AsyncSession, tenant_id: int, question_id: int) -> LearningExamQuestion | None:
        result = await db.execute(
            select(LearningExamQuestion).where(
                LearningExamQuestion.id == question_id,
                LearningExamQuestion.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_by_exam(db: AsyncSession, exam_id: int) -> list[LearningExamQuestion]:
        result = await db.execute(
            select(LearningExamQuestion)
            .where(LearningExamQuestion.exam_id == exam_id)
            .order_by(LearningExamQuestion.sort_order.asc(), LearningExamQuestion.id.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def next_sort_order(db: AsyncSession, exam_id: int) -> int:
        result = await db.execute(
            select(func.count()).select_from(LearningExamQuestion).where(LearningExamQuestion.exam_id == exam_id)
        )
        return result.scalar_one()

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> LearningExamQuestion:
        question = LearningExamQuestion(**data)
        db.add(question)
        await db.commit()
        await db.refresh(question)
        return question

    @staticmethod
    async def update(db: AsyncSession, question: LearningExamQuestion, data: dict) -> LearningExamQuestion:
        for key, value in data.items():
            setattr(question, key, value)
        await db.commit()
        await db.refresh(question)
        return question

    @staticmethod
    async def apply_order(db: AsyncSession, exam_id: int, ordered_ids: list[int]) -> None:
        await db.execute(
            update(LearningExamQuestion)
            .where(LearningExamQuestion.exam_id == exam_id)
            .values(sort_order=case({item_id: index for index, item_id in enumerate(ordered_ids)}, value=LearningExamQuestion.id)),
        )
        await db.commit()

    @staticmethod
    async def delete(db: AsyncSession, question: LearningExamQuestion) -> None:
        await db.delete(question)
        await db.commit()


class LearningExamAssignmentRepository:
    @staticmethod
    async def list_by_exam(db: AsyncSession, exam_id: int) -> list[LearningExamAssignment]:
        result = await db.execute(
            select(LearningExamAssignment)
            .where(LearningExamAssignment.exam_id == exam_id)
            .order_by(LearningExamAssignment.id.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_by_exams(db: AsyncSession, exam_ids: list[int]) -> list[LearningExamAssignment]:
        if not exam_ids:
            return []
        result = await db.execute(
            select(LearningExamAssignment).where(LearningExamAssignment.exam_id.in_(exam_ids))
        )
        return list(result.scalars().all())

    @staticmethod
    async def add_many(db: AsyncSession, rows: list[dict]) -> None:
        db.add_all([LearningExamAssignment(**row) for row in rows])
        await db.commit()

    @staticmethod
    async def get_by_id(
        db: AsyncSession, tenant_id: int, assignment_id: int
    ) -> LearningExamAssignment | None:
        result = await db.execute(
            select(LearningExamAssignment).where(
                LearningExamAssignment.id == assignment_id,
                LearningExamAssignment.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def delete(db: AsyncSession, assignment: LearningExamAssignment) -> None:
        await db.delete(assignment)
        await db.commit()

    @staticmethod
    async def list_existing_pairs(db: AsyncSession, exam_id: int) -> set[tuple[str, int]]:
        result = await db.execute(
            select(LearningExamAssignment.target_type, LearningExamAssignment.target_id).where(
                LearningExamAssignment.exam_id == exam_id
            )
        )
        return {(row[0], row[1]) for row in result.all()}

    @staticmethod
    async def expand_assignments(
        db: AsyncSession, tenant_id: int, exam_ids: list[int]
    ) -> dict[int, set[int]]:
        """Bulk-expand assigned exams to their visible active employee id sets."""
        if not exam_ids:
            return {}
        assignments = await LearningExamAssignmentRepository.list_by_exams(db, exam_ids)
        direct_map: dict[int, set[int]] = {}
        group_map: dict[int, set[int]] = {}
        for row in assignments:
            if row.target_type == ASSIGNMENT_TARGET_EMPLOYEE:
                direct_map.setdefault(row.exam_id, set()).add(row.target_id)
            else:
                group_map.setdefault(row.exam_id, set()).add(row.target_id)

        all_group_ids = set().union(*group_map.values()) if group_map else set()
        group_members: dict[int, set[int]] = {}
        if all_group_ids:
            result = await db.execute(
                select(EmployeeGroupMember.group_id, EmployeeGroupMember.employee_id)
                .join(Employee, Employee.id == EmployeeGroupMember.employee_id)
                .where(
                    EmployeeGroupMember.group_id.in_(all_group_ids),
                    Employee.tenant_id == tenant_id,
                    Employee.is_active.is_(True),
                )
            )
            for group_id, employee_id in result.all():
                group_members.setdefault(group_id, set()).add(employee_id)

        visible: dict[int, set[int]] = {}
        for exam_id in exam_ids:
            members = set(direct_map.get(exam_id, set()))
            for group_id in group_map.get(exam_id, set()):
                members |= group_members.get(group_id, set())
            visible[exam_id] = members
        return visible

    @staticmethod
    async def list_visible_employee_ids(db: AsyncSession, tenant_id: int, exam_id: int) -> set[int]:
        """Expand an assigned exam's audience: direct employees union active group members."""
        direct_q = select(LearningExamAssignment.target_id).where(
            LearningExamAssignment.exam_id == exam_id,
            LearningExamAssignment.target_type == ASSIGNMENT_TARGET_EMPLOYEE,
        )
        group_ids_q = select(LearningExamAssignment.target_id).where(
            LearningExamAssignment.exam_id == exam_id,
            LearningExamAssignment.target_type == ASSIGNMENT_TARGET_GROUP,
        )
        group_members_q = (
            select(EmployeeGroupMember.employee_id)
            .join(Employee, Employee.id == EmployeeGroupMember.employee_id)
            .where(
                EmployeeGroupMember.group_id.in_(group_ids_q),
                Employee.tenant_id == tenant_id,
                Employee.is_active.is_(True),
            )
        )
        direct_ids = set((await db.execute(direct_q)).scalars().all())
        group_member_ids = set((await db.execute(group_members_q)).scalars().all())
        visible = direct_ids | group_member_ids
        if not visible:
            return set()
        # Keep only active employees of this tenant (covers direct assignments too).
        active_q = select(Employee.id).where(
            Employee.id.in_(visible),
            Employee.tenant_id == tenant_id,
            Employee.is_active.is_(True),
        )
        return set((await db.execute(active_q)).scalars().all())


class LearningExamAttemptRepository:
    @staticmethod
    async def create(db: AsyncSession, data: dict) -> LearningExamAttempt:
        attempt = LearningExamAttempt(**data)
        db.add(attempt)
        await db.commit()
        await db.refresh(attempt)
        return attempt

    @staticmethod
    async def get_by_id(
        db: AsyncSession, tenant_id: int, attempt_id: int
    ) -> LearningExamAttempt | None:
        result = await db.execute(
            select(LearningExamAttempt).where(
                LearningExamAttempt.id == attempt_id,
                LearningExamAttempt.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def save(db: AsyncSession, attempt: LearningExamAttempt) -> LearningExamAttempt:
        db.add(attempt)
        await db.commit()
        await db.refresh(attempt)
        return attempt

    @staticmethod
    async def get_in_progress(
        db: AsyncSession, exam_id: int, employee_id: int
    ) -> LearningExamAttempt | None:
        result = await db.execute(
            select(LearningExamAttempt).where(
                LearningExamAttempt.exam_id == exam_id,
                LearningExamAttempt.employee_id == employee_id,
                LearningExamAttempt.status == ATTEMPT_STATUS_IN_PROGRESS,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def abandon_in_progress(db: AsyncSession, exam_id: int, employee_id: int) -> None:
        """Mark any lingering in-progress attempt as abandoned (a new one replaces it)."""
        await db.execute(
            update(LearningExamAttempt)
            .where(
                LearningExamAttempt.exam_id == exam_id,
                LearningExamAttempt.employee_id == employee_id,
                LearningExamAttempt.status == ATTEMPT_STATUS_IN_PROGRESS,
            )
            .values(status=ATTEMPT_STATUS_ABANDONED)
        )
        await db.commit()

    @staticmethod
    async def list_submitted_by_exam_employee(
        db: AsyncSession, exam_id: int, employee_id: int
    ) -> list[LearningExamAttempt]:
        """Submitted attempts, newest first (attempt history)."""
        result = await db.execute(
            select(LearningExamAttempt)
            .where(
                LearningExamAttempt.exam_id == exam_id,
                LearningExamAttempt.employee_id == employee_id,
                LearningExamAttempt.status == ATTEMPT_STATUS_SUBMITTED,
            )
            .order_by(LearningExamAttempt.submitted_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def aggregate_by_exams_for_employee(
        db: AsyncSession, exam_ids: list[int], employee_id: int
    ) -> dict[int, dict]:
        """Per-exam rollup of one employee's submitted attempts (my-exams cards)."""
        if not exam_ids:
            return {}
        result = await db.execute(
            select(
                LearningExamAttempt.exam_id,
                func.count().label("submitted_count"),
                func.max(LearningExamAttempt.score).label("best_score"),
            )
            .where(
                LearningExamAttempt.exam_id.in_(exam_ids),
                LearningExamAttempt.employee_id == employee_id,
                LearningExamAttempt.status == ATTEMPT_STATUS_SUBMITTED,
            )
            .group_by(LearningExamAttempt.exam_id)
        )
        return {row[0]: {"submitted_count": row[1], "best_score": row[2]} for row in result.all()}

    @staticmethod
    async def aggregate_by_exam(
        db: AsyncSession, exam_id: int, employee_ids: set[int] | list[int]
    ) -> dict[int, dict]:
        """Per-employee rollup for the admin results table."""
        if not employee_ids:
            return {}
        result = await db.execute(
            select(
                LearningExamAttempt.employee_id,
                func.count().label("submitted_count"),
                func.max(LearningExamAttempt.score).label("best_score"),
                func.max(LearningExamAttempt.submitted_at).label("last_submitted_at"),
            )
            .where(
                LearningExamAttempt.exam_id == exam_id,
                LearningExamAttempt.employee_id.in_(employee_ids),
                LearningExamAttempt.status == ATTEMPT_STATUS_SUBMITTED,
            )
            .group_by(LearningExamAttempt.employee_id)
        )
        return {
            row[0]: {
                "submitted_count": row[1],
                "best_score": row[2],
                "last_submitted_at": row[3],
            }
            for row in result.all()
        }

    @staticmethod
    async def count_passed_employees_by_exam(db: AsyncSession, exam_ids: list[int]) -> dict[int, int]:
        """Distinct employees with at least one passed submitted attempt, per exam."""
        if not exam_ids:
            return {}
        result = await db.execute(
            select(
                LearningExamAttempt.exam_id,
                func.count(func.distinct(LearningExamAttempt.employee_id)),
            )
            .where(
                LearningExamAttempt.exam_id.in_(exam_ids),
                LearningExamAttempt.status == ATTEMPT_STATUS_SUBMITTED,
                LearningExamAttempt.passed.is_(True),
            )
            .group_by(LearningExamAttempt.exam_id)
        )
        return {row[0]: row[1] for row in result.all()}
