"""
Learning center employee-side service: my courses, course detail with per-material
progress, material open (playback URLs), progress reporting and completion.
"""
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessError, NotFoundError
from app.libs.storage.factory import create_storage_client
from app.libs.vod import get_vod_client
from app.models.learning import (
    COURSE_STATUS_PUBLISHED,
    MATERIAL_TYPE_AUDIO,
    MATERIAL_TYPE_DOCUMENT,
    MATERIAL_TYPE_PDF,
    MATERIAL_TYPE_VIDEO,
    RECORD_STATUS_COMPLETED,
    RECORD_STATUS_IN_PROGRESS,
    TRANSCODE_OK,
    VISIBILITY_ALL,
)
from app.repositories.learning_repository import (
    LearningAssignmentRepository,
    LearningCourseRepository,
    LearningMaterialRepository,
    LearningRecordRepository,
    LearningSectionRepository,
)
from app.services.learning_assignment_service import _progress_and_status

COMPLETE_MIN_RATIO = 0.9
TEMPORARY_URL_EXPIRES = 600


class LearningMyService:
    @staticmethod
    async def list_my_courses(
        db: AsyncSession,
        *,
        tenant_id: int,
        employee_id: int,
        q: str | None,
        page: int,
        per_page: int,
    ) -> dict:
        courses, _total = await LearningCourseRepository.list_paginated(
            db, tenant_id, page=1, per_page=10000, q=q, status=COURSE_STATUS_PUBLISHED
        )
        assigned_courses = [c for c in courses if c.visibility != VISIBILITY_ALL]
        visible_map = await LearningAssignmentRepository.expand_assignments(
            db, tenant_id, [c.id for c in assigned_courses]
        )
        visible_courses = [
            c
            for c in courses
            if c.visibility == VISIBILITY_ALL or employee_id in visible_map.get(c.id, set())
        ]

        course_ids = [c.id for c in visible_courses]
        material_counts = await LearningCourseRepository.count_materials_by_course(db, course_ids)
        aggregates = await LearningRecordRepository.aggregate_by_courses_for_employee(
            db, course_ids, employee_id
        )

        items = []
        for course in visible_courses:
            material_count = material_counts.get(course.id, 0)
            agg = aggregates.get(course.id, {"completed": 0, "total_records": 0})
            progress, status = _progress_and_status(
                agg["completed"], agg["total_records"], material_count
            )
            items.append(
                {
                    "id": course.id,
                    "name": course.name,
                    "cover_url": course.cover_url,
                    "intro": course.intro,
                    "material_count": material_count,
                    "completed_count": agg["completed"],
                    "progress": progress,
                    "status": status,
                    "updated_at": course.updated_at,
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

    @staticmethod
    async def get_my_course_detail(
        db: AsyncSession, *, tenant_id: int, course_id: int, employee_id: int
    ) -> dict:
        course = await _get_visible_course_or_404(db, tenant_id, course_id, employee_id)
        sections = await LearningSectionRepository.list_by_course(db, course.id)
        materials = await LearningMaterialRepository.list_by_course(db, course.id)
        records = await LearningRecordRepository.list_by_course_employee(db, course.id, employee_id)
        record_map = {record.material_id: record for record in records}

        completed_count = sum(1 for record in records if record.status == RECORD_STATUS_COMPLETED)
        material_count = len(materials)
        _progress, course_status = _progress_and_status(completed_count, len(records), material_count)

        materials_by_section: dict[int, list[dict]] = {}
        for material in materials:
            record = record_map.get(material.id)
            materials_by_section.setdefault(material.section_id, []).append(
                {
                    "id": material.id,
                    "section_id": material.section_id,
                    "name": material.name,
                    "type": material.type,
                    "duration_seconds": material.duration_seconds,
                    "transcode_status": material.transcode_status,
                    "sort_order": material.sort_order,
                    "my_status": record.status if record else "not_started",
                    "my_position_seconds": record.play_position_seconds if record else 0,
                }
            )
        return {
            "id": course.id,
            "name": course.name,
            "cover_url": course.cover_url,
            "intro": course.intro,
            "material_count": material_count,
            "completed_count": completed_count,
            "status": course_status,
            "sections": [
                {
                    "id": section.id,
                    "name": section.name,
                    "sort_order": section.sort_order,
                    "materials": materials_by_section.get(section.id, []),
                }
                for section in sections
            ],
        }

    @staticmethod
    async def open_material(
        db: AsyncSession, *, tenant_id: int, material_id: int, employee_id: int
    ) -> dict:
        material = await _get_visible_material_or_404(db, tenant_id, material_id, employee_id)
        record = await _ensure_record(db, tenant_id, material, employee_id)
        if record.status != RECORD_STATUS_COMPLETED:
            record.last_learn_at = datetime.now(timezone.utc)
            record = await LearningRecordRepository.save_record(db, record)

        play_url = file_url = download_url = file_name = None
        if material.type == MATERIAL_TYPE_VIDEO:
            play_info = await get_vod_client().get_play_info(video_id=material.vod_video_id or "")
            if play_info.status == TRANSCODE_OK:
                play_url = play_info.play_url
        else:
            storage = create_storage_client()
            file_url = await storage.get_temporary_url(
                material.file_key or "", expires_seconds=TEMPORARY_URL_EXPIRES
            )
            if material.type in (MATERIAL_TYPE_PDF, MATERIAL_TYPE_DOCUMENT):
                ext = (material.file_key or "").rsplit(".", 1)[-1].lower() if material.file_key else ""
                file_name = f"{material.name}.{ext}" if ext else material.name
                download_url = await storage.get_temporary_url(
                    material.file_key or "",
                    expires_seconds=TEMPORARY_URL_EXPIRES,
                    download_name=file_name,
                )
        return {
            "material": material,
            "play_url": play_url,
            "file_url": file_url,
            "download_url": download_url,
            "file_name": file_name,
            "record_status": record.status,
            "play_position_seconds": record.play_position_seconds,
        }

    @staticmethod
    async def report_progress(
        db: AsyncSession, *, tenant_id: int, material_id: int, employee_id: int, position_seconds: int
    ):
        material = await _get_visible_material_or_404(db, tenant_id, material_id, employee_id)
        record = await _ensure_record(db, tenant_id, material, employee_id)
        record.play_position_seconds = max(record.play_position_seconds, position_seconds)
        record.last_learn_at = datetime.now(timezone.utc)
        return await LearningRecordRepository.save_record(db, record)

    @staticmethod
    async def complete_material(
        db: AsyncSession, *, tenant_id: int, material_id: int, employee_id: int
    ) -> dict:
        material = await _get_visible_material_or_404(db, tenant_id, material_id, employee_id)
        record = await _ensure_record(db, tenant_id, material, employee_id)
        if record.status != RECORD_STATUS_COMPLETED:
            if material.type in (MATERIAL_TYPE_VIDEO, MATERIAL_TYPE_AUDIO):
                duration = material.duration_seconds
                if not duration or record.play_position_seconds < duration * COMPLETE_MIN_RATIO:
                    raise BusinessError(
                        "Playback has not reached 90% yet",
                        status_code=400,
                        code="COMPLETE_NOT_ELIGIBLE",
                    )
            now = datetime.now(timezone.utc)
            record.status = RECORD_STATUS_COMPLETED
            record.completed_at = now
            record.last_learn_at = now
            record = await LearningRecordRepository.save_record(db, record)

        material_count = (
            await LearningCourseRepository.count_materials_by_course(db, [material.course_id])
        ).get(material.course_id, 0)
        records = await LearningRecordRepository.list_by_course_employee(
            db, material.course_id, employee_id
        )
        completed_count = sum(1 for row in records if row.status == RECORD_STATUS_COMPLETED)
        _progress, course_status = _progress_and_status(completed_count, len(records), material_count)
        return {
            "record": record,
            "course_completed_count": completed_count,
            "course_material_count": material_count,
            "course_status": course_status,
        }


async def _get_visible_course_or_404(
    db: AsyncSession, tenant_id: int, course_id: int, employee_id: int
):
    course = await LearningCourseRepository.get_by_id(db, tenant_id, course_id)
    if course is None or course.status != COURSE_STATUS_PUBLISHED:
        raise NotFoundError("Course not found")
    if course.visibility != VISIBILITY_ALL:
        visible = await LearningAssignmentRepository.list_visible_employee_ids(
            db, tenant_id, course.id
        )
        if employee_id not in visible:
            raise NotFoundError("Course not found")
    return course


async def _get_visible_material_or_404(
    db: AsyncSession, tenant_id: int, material_id: int, employee_id: int
):
    material = await LearningMaterialRepository.get_by_id(db, tenant_id, material_id)
    if material is None:
        raise NotFoundError("Material not found")
    await _get_visible_course_or_404(db, tenant_id, material.course_id, employee_id)
    return material


async def _ensure_record(db: AsyncSession, tenant_id: int, material, employee_id: int):
    record = await LearningRecordRepository.get_record(db, material.id, employee_id)
    if record is not None:
        return record
    return await LearningRecordRepository.create_record(
        db,
        {
            "tenant_id": tenant_id,
            "course_id": material.course_id,
            "material_id": material.id,
            "employee_id": employee_id,
            "status": RECORD_STATUS_IN_PROGRESS,
            "play_position_seconds": 0,
            "last_learn_at": datetime.now(timezone.utc),
        },
    )
