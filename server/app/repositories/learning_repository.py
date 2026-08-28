"""
Learning center repositories: data access for courses, sections, materials,
assignments and material learning records.
"""
from sqlalchemy import case, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee
from app.models.employee_group import EmployeeGroup, EmployeeGroupMember
from app.models.learning import (
    ASSIGNMENT_TARGET_EMPLOYEE,
    ASSIGNMENT_TARGET_GROUP,
    RECORD_STATUS_COMPLETED,
    LearningCourse,
    LearningCourseAssignment,
    LearningMaterial,
    LearningMaterialRecord,
    LearningSection,
)


class LearningCourseRepository:
    @staticmethod
    async def get_by_id(db: AsyncSession, tenant_id: int, course_id: int) -> LearningCourse | None:
        result = await db.execute(
            select(LearningCourse).where(
                LearningCourse.id == course_id,
                LearningCourse.tenant_id == tenant_id,
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
    ) -> tuple[list[LearningCourse], int]:
        base = select(LearningCourse).where(LearningCourse.tenant_id == tenant_id)
        if q:
            base = base.where(LearningCourse.name.ilike(f"%{q}%"))
        if status:
            base = base.where(LearningCourse.status == status)

        total_result = await db.execute(select(func.count()).select_from(base.subquery()))
        total = total_result.scalar_one()

        result = await db.execute(
            base.order_by(LearningCourse.updated_at.desc()).offset((page - 1) * per_page).limit(per_page)
        )
        return list(result.scalars().all()), total

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> LearningCourse:
        course = LearningCourse(**data)
        db.add(course)
        await db.commit()
        await db.refresh(course)
        return course

    @staticmethod
    async def update(db: AsyncSession, course: LearningCourse, data: dict) -> LearningCourse:
        for key, value in data.items():
            setattr(course, key, value)
        await db.commit()
        await db.refresh(course)
        return course

    @staticmethod
    async def delete(db: AsyncSession, course: LearningCourse) -> None:
        await db.delete(course)
        await db.commit()

    @staticmethod
    async def count_sections_by_course(db: AsyncSession, course_ids: list[int]) -> dict[int, int]:
        if not course_ids:
            return {}
        result = await db.execute(
            select(LearningSection.course_id, func.count())
            .where(LearningSection.course_id.in_(course_ids))
            .group_by(LearningSection.course_id)
        )
        return {row[0]: row[1] for row in result.all()}

    @staticmethod
    async def count_materials_by_course(db: AsyncSession, course_ids: list[int]) -> dict[int, int]:
        if not course_ids:
            return {}
        result = await db.execute(
            select(LearningMaterial.course_id, func.count())
            .where(LearningMaterial.course_id.in_(course_ids))
            .group_by(LearningMaterial.course_id)
        )
        return {row[0]: row[1] for row in result.all()}


class LearningSectionRepository:
    @staticmethod
    async def get_by_id(db: AsyncSession, tenant_id: int, section_id: int) -> LearningSection | None:
        result = await db.execute(
            select(LearningSection).where(
                LearningSection.id == section_id,
                LearningSection.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_by_course(db: AsyncSession, course_id: int) -> list[LearningSection]:
        result = await db.execute(
            select(LearningSection)
            .where(LearningSection.course_id == course_id)
            .order_by(LearningSection.sort_order.asc(), LearningSection.id.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def next_sort_order(db: AsyncSession, course_id: int) -> int:
        result = await db.execute(
            select(func.count()).select_from(LearningSection).where(LearningSection.course_id == course_id)
        )
        return result.scalar_one()

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> LearningSection:
        section = LearningSection(**data)
        db.add(section)
        await db.commit()
        await db.refresh(section)
        return section

    @staticmethod
    async def update(db: AsyncSession, section: LearningSection, data: dict) -> LearningSection:
        for key, value in data.items():
            setattr(section, key, value)
        await db.commit()
        await db.refresh(section)
        return section

    @staticmethod
    async def apply_order(db: AsyncSession, course_id: int, ordered_ids: list[int]) -> None:
        await db.execute(
            update(LearningSection)
            .where(LearningSection.course_id == course_id)
            .values(sort_order=_case_order(ordered_ids, LearningSection.id)),
        )
        await db.commit()

    @staticmethod
    async def delete(db: AsyncSession, section: LearningSection) -> None:
        await db.delete(section)
        await db.commit()


class LearningMaterialRepository:
    @staticmethod
    async def get_by_id(db: AsyncSession, tenant_id: int, material_id: int) -> LearningMaterial | None:
        result = await db.execute(
            select(LearningMaterial).where(
                LearningMaterial.id == material_id,
                LearningMaterial.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_by_course(db: AsyncSession, course_id: int) -> list[LearningMaterial]:
        result = await db.execute(
            select(LearningMaterial)
            .where(LearningMaterial.course_id == course_id)
            .order_by(LearningMaterial.sort_order.asc(), LearningMaterial.id.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def next_sort_order(db: AsyncSession, section_id: int) -> int:
        result = await db.execute(
            select(func.count()).select_from(LearningMaterial).where(LearningMaterial.section_id == section_id)
        )
        return result.scalar_one()

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> LearningMaterial:
        material = LearningMaterial(**data)
        db.add(material)
        await db.commit()
        await db.refresh(material)
        return material

    @staticmethod
    async def update(db: AsyncSession, material: LearningMaterial, data: dict) -> LearningMaterial:
        for key, value in data.items():
            setattr(material, key, value)
        await db.commit()
        await db.refresh(material)
        return material

    @staticmethod
    async def apply_order(db: AsyncSession, section_id: int, ordered_ids: list[int]) -> None:
        await db.execute(
            update(LearningMaterial)
            .where(LearningMaterial.section_id == section_id)
            .values(sort_order=_case_order(ordered_ids, LearningMaterial.id)),
        )
        await db.commit()

    @staticmethod
    async def delete(db: AsyncSession, material: LearningMaterial) -> None:
        await db.delete(material)
        await db.commit()

    @staticmethod
    async def update_transcode_by_vod_video_id(
        db: AsyncSession,
        vod_video_id: str,
        transcode_status: str,
        duration_seconds: int | None = None,
    ) -> int:
        values: dict = {"transcode_status": transcode_status}
        if duration_seconds is not None:
            values["duration_seconds"] = duration_seconds
        result = await db.execute(
            update(LearningMaterial)
            .where(LearningMaterial.vod_video_id == vod_video_id)
            .values(**values)
        )
        await db.commit()
        return result.rowcount or 0


def _case_order(ordered_ids: list[int], id_column):
    """Build a CASE expression mapping each id to its position in ordered_ids."""
    return case({item_id: index for index, item_id in enumerate(ordered_ids)}, value=id_column)


class LearningAssignmentRepository:
    @staticmethod
    async def list_by_course(db: AsyncSession, course_id: int) -> list[LearningCourseAssignment]:
        result = await db.execute(
            select(LearningCourseAssignment)
            .where(LearningCourseAssignment.course_id == course_id)
            .order_by(LearningCourseAssignment.id.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_by_courses(db: AsyncSession, course_ids: list[int]) -> list[LearningCourseAssignment]:
        if not course_ids:
            return []
        result = await db.execute(
            select(LearningCourseAssignment).where(LearningCourseAssignment.course_id.in_(course_ids))
        )
        return list(result.scalars().all())

    @staticmethod
    async def add_many(db: AsyncSession, rows: list[dict]) -> None:
        db.add_all([LearningCourseAssignment(**row) for row in rows])
        await db.commit()

    @staticmethod
    async def get_by_id(
        db: AsyncSession, tenant_id: int, assignment_id: int
    ) -> LearningCourseAssignment | None:
        result = await db.execute(
            select(LearningCourseAssignment).where(
                LearningCourseAssignment.id == assignment_id,
                LearningCourseAssignment.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def delete(db: AsyncSession, assignment: LearningCourseAssignment) -> None:
        await db.delete(assignment)
        await db.commit()

    @staticmethod
    async def list_visible_employee_ids(db: AsyncSession, tenant_id: int, course_id: int) -> set[int]:
        """Expand an assigned course's audience: direct employees ∪ active group members."""
        direct_q = select(LearningCourseAssignment.target_id).where(
            LearningCourseAssignment.course_id == course_id,
            LearningCourseAssignment.target_type == ASSIGNMENT_TARGET_EMPLOYEE,
        )
        group_ids_q = select(LearningCourseAssignment.target_id).where(
            LearningCourseAssignment.course_id == course_id,
            LearningCourseAssignment.target_type == ASSIGNMENT_TARGET_GROUP,
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

    @staticmethod
    async def list_existing_pairs(db: AsyncSession, course_id: int) -> set[tuple[str, int]]:
        result = await db.execute(
            select(LearningCourseAssignment.target_type, LearningCourseAssignment.target_id).where(
                LearningCourseAssignment.course_id == course_id
            )
        )
        return {(row[0], row[1]) for row in result.all()}

    @staticmethod
    async def expand_assignments(
        db: AsyncSession, tenant_id: int, course_ids: list[int]
    ) -> dict[int, set[int]]:
        """Bulk-expand assigned courses to their visible active employee id sets."""
        if not course_ids:
            return {}
        assignments = await LearningAssignmentRepository.list_by_courses(db, course_ids)
        direct_map: dict[int, set[int]] = {}
        group_map: dict[int, set[int]] = {}
        for row in assignments:
            if row.target_type == ASSIGNMENT_TARGET_EMPLOYEE:
                direct_map.setdefault(row.course_id, set()).add(row.target_id)
            else:
                group_map.setdefault(row.course_id, set()).add(row.target_id)

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
        for course_id in course_ids:
            members = set(direct_map.get(course_id, set()))
            for group_id in group_map.get(course_id, set()):
                members |= group_members.get(group_id, set())
            visible[course_id] = members
        return visible

    # -- employee / group lookup helpers for the assignment UI ---------------

    @staticmethod
    async def get_groups_by_ids(
        db: AsyncSession, tenant_id: int, group_ids: list[int]
    ) -> dict[int, EmployeeGroup]:
        if not group_ids:
            return {}
        result = await db.execute(
            select(EmployeeGroup).where(
                EmployeeGroup.id.in_(group_ids), EmployeeGroup.tenant_id == tenant_id
            )
        )
        return {group.id: group for group in result.scalars().all()}

    @staticmethod
    async def get_employees_by_ids(
        db: AsyncSession, tenant_id: int, employee_ids: list[int] | set[int]
    ) -> dict[int, Employee]:
        if not employee_ids:
            return {}
        result = await db.execute(
            select(Employee).where(
                Employee.id.in_(employee_ids), Employee.tenant_id == tenant_id
            )
        )
        return {employee.id: employee for employee in result.scalars().all()}

    @staticmethod
    async def count_active_members_by_groups(
        db: AsyncSession, tenant_id: int, group_ids: list[int] | set[int]
    ) -> dict[int, int]:
        if not group_ids:
            return {}
        result = await db.execute(
            select(EmployeeGroupMember.group_id, func.count())
            .join(Employee, Employee.id == EmployeeGroupMember.employee_id)
            .where(
                EmployeeGroupMember.group_id.in_(group_ids),
                Employee.tenant_id == tenant_id,
                Employee.is_active.is_(True),
            )
            .group_by(EmployeeGroupMember.group_id)
        )
        return {row[0]: row[1] for row in result.all()}

    @staticmethod
    async def list_groups_with_member_counts(
        db: AsyncSession, tenant_id: int, q: str | None = None
    ) -> list[tuple[EmployeeGroup, int]]:
        stmt = (
            select(EmployeeGroup, func.count(Employee.id))
            .outerjoin(EmployeeGroupMember, EmployeeGroupMember.group_id == EmployeeGroup.id)
            .outerjoin(
                Employee,
                (Employee.id == EmployeeGroupMember.employee_id) & Employee.is_active.is_(True),
            )
            .where(EmployeeGroup.tenant_id == tenant_id)
            .group_by(EmployeeGroup.id)
            .order_by(EmployeeGroup.id.asc())
        )
        if q:
            stmt = stmt.where(EmployeeGroup.name.ilike(f"%{q}%"))
        result = await db.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]

    @staticmethod
    async def list_active_employees(
        db: AsyncSession, tenant_id: int, q: str | None = None
    ) -> list[Employee]:
        stmt = (
            select(Employee)
            .where(Employee.tenant_id == tenant_id, Employee.is_active.is_(True))
            .order_by(Employee.id.asc())
        )
        if q:
            stmt = stmt.where(Employee.name.ilike(f"%{q}%"))
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def list_group_names_by_employees(
        db: AsyncSession, tenant_id: int, employee_ids: list[int] | set[int]
    ) -> dict[int, list[str]]:
        """Map employee id -> names of the groups they belong to (sorted by group id)."""
        if not employee_ids:
            return {}
        result = await db.execute(
            select(EmployeeGroupMember.employee_id, EmployeeGroup.name)
            .join(EmployeeGroup, EmployeeGroup.id == EmployeeGroupMember.group_id)
            .where(
                EmployeeGroupMember.employee_id.in_(employee_ids),
                EmployeeGroup.tenant_id == tenant_id,
            )
            .order_by(EmployeeGroup.id.asc())
        )
        mapping: dict[int, list[str]] = {}
        for employee_id, group_name in result.all():
            mapping.setdefault(employee_id, []).append(group_name)
        return mapping


class LearningRecordRepository:
    @staticmethod
    async def list_employee_ids_with_records(db: AsyncSession, course_id: int) -> set[int]:
        result = await db.execute(
            select(LearningMaterialRecord.employee_id)
            .where(LearningMaterialRecord.course_id == course_id)
            .distinct()
        )
        return set(result.scalars().all())

    @staticmethod
    async def count_completed_by_course(db: AsyncSession, course_id: int, employee_ids: set[int]) -> dict[int, int]:
        """Per-employee count of completed material records in one course."""
        if not employee_ids:
            return {}
        result = await db.execute(
            select(LearningMaterialRecord.employee_id, func.count())
            .where(
                LearningMaterialRecord.course_id == course_id,
                LearningMaterialRecord.employee_id.in_(employee_ids),
                LearningMaterialRecord.status == RECORD_STATUS_COMPLETED,
            )
            .group_by(LearningMaterialRecord.employee_id)
        )
        return {row[0]: row[1] for row in result.all()}

    @staticmethod
    async def get_record(
        db: AsyncSession, material_id: int, employee_id: int
    ) -> LearningMaterialRecord | None:
        result = await db.execute(
            select(LearningMaterialRecord).where(
                LearningMaterialRecord.material_id == material_id,
                LearningMaterialRecord.employee_id == employee_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create_record(db: AsyncSession, data: dict) -> LearningMaterialRecord:
        record = LearningMaterialRecord(**data)
        db.add(record)
        await db.commit()
        await db.refresh(record)
        return record

    @staticmethod
    async def save_record(db: AsyncSession, record: LearningMaterialRecord) -> LearningMaterialRecord:
        db.add(record)
        await db.commit()
        await db.refresh(record)
        return record

    @staticmethod
    async def list_by_course_employee(
        db: AsyncSession, course_id: int, employee_id: int
    ) -> list[LearningMaterialRecord]:
        result = await db.execute(
            select(LearningMaterialRecord).where(
                LearningMaterialRecord.course_id == course_id,
                LearningMaterialRecord.employee_id == employee_id,
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def aggregate_by_course(
        db: AsyncSession, course_id: int, employee_ids: set[int] | list[int]
    ) -> dict[int, dict]:
        """Per-employee rollup for the learner progress table."""
        if not employee_ids:
            return {}
        result = await db.execute(
            select(
                LearningMaterialRecord.employee_id,
                func.count().label("total_records"),
                func.count()
                .filter(LearningMaterialRecord.status == RECORD_STATUS_COMPLETED)
                .label("completed"),
                func.max(LearningMaterialRecord.last_learn_at).label("last_learn_at"),
            )
            .where(
                LearningMaterialRecord.course_id == course_id,
                LearningMaterialRecord.employee_id.in_(employee_ids),
            )
            .group_by(LearningMaterialRecord.employee_id)
        )
        return {
            row[0]: {"total_records": row[1], "completed": row[2], "last_learn_at": row[3]}
            for row in result.all()
        }

    @staticmethod
    async def aggregate_by_courses_for_employee(
        db: AsyncSession, course_ids: list[int], employee_id: int
    ) -> dict[int, dict]:
        """Per-course rollup of one employee's records (for the my-learning list)."""
        if not course_ids:
            return {}
        result = await db.execute(
            select(
                LearningMaterialRecord.course_id,
                func.count().label("total_records"),
                func.count()
                .filter(LearningMaterialRecord.status == RECORD_STATUS_COMPLETED)
                .label("completed"),
            )
            .where(
                LearningMaterialRecord.course_id.in_(course_ids),
                LearningMaterialRecord.employee_id == employee_id,
            )
            .group_by(LearningMaterialRecord.course_id)
        )
        return {row[0]: {"total_records": row[1], "completed": row[2]} for row in result.all()}

    @staticmethod
    async def delete_by_course(db: AsyncSession, course_id: int) -> None:
        await db.execute(delete(LearningMaterialRecord).where(LearningMaterialRecord.course_id == course_id))
        await db.commit()
