"""
Learning center admin service: course lifecycle, section/material management,
upload credential issuing and VOD transcode event handling.
"""
import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessError, NotFoundError, ValidationError
from app.libs.storage.factory import create_storage_client
from app.libs.vod import get_vod_client
from app.configs.settings import settings
from app.models.learning import (
    COURSE_STATUS_DRAFT,
    COURSE_STATUS_PUBLISHED,
    COURSE_STATUS_UNPUBLISHED,
    MATERIAL_TYPE_AUDIO,
    MATERIAL_TYPE_DOCUMENT,
    MATERIAL_TYPE_PDF,
    MATERIAL_TYPE_VIDEO,
    TRANSCODE_FAILED,
    TRANSCODE_OK,
    TRANSCODE_PROCESSING,
)
from app.repositories.learning_repository import (
    LearningAssignmentRepository,
    LearningCourseRepository,
    LearningMaterialRepository,
    LearningRecordRepository,
    LearningSectionRepository,
)
from app.schemas.learning import (
    LearningCourseCreate,
    LearningCourseUpdate,
    LearningMaterialCreate,
    MaterialUploadCredentialRequest,
)

logger = logging.getLogger(__name__)

# Extension whitelist per material type and per-type size limits (bytes).
MATERIAL_EXTENSIONS: dict[str, set[str]] = {
    MATERIAL_TYPE_VIDEO: {"mp4", "mov", "avi", "mkv", "flv"},
    MATERIAL_TYPE_AUDIO: {"mp3", "wav", "aac"},
    MATERIAL_TYPE_PDF: {"pdf"},
    MATERIAL_TYPE_DOCUMENT: {"doc", "docx", "ppt", "pptx", "xls", "xlsx"},
}
MATERIAL_SIZE_LIMITS: dict[str, int] = {
    MATERIAL_TYPE_VIDEO: 1 * 1024 * 1024 * 1024,  # 1GB
    MATERIAL_TYPE_AUDIO: 100 * 1024 * 1024,  # 100MB
    MATERIAL_TYPE_PDF: 50 * 1024 * 1024,  # 50MB
    MATERIAL_TYPE_DOCUMENT: 50 * 1024 * 1024,  # 50MB
}
MATERIAL_CONTENT_TYPES: dict[str, str] = {
    "mp4": "video/mp4",
    "mov": "video/quicktime",
    "avi": "video/x-msvideo",
    "mkv": "video/x-matroska",
    "flv": "video/x-flv",
    "mp3": "audio/mpeg",
    "wav": "audio/wav",
    "aac": "audio/aac",
    "pdf": "application/pdf",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "ppt": "application/vnd.ms-powerpoint",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "xls": "application/vnd.ms-excel",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}

COVER_MAX_BYTES = 2 * 1024 * 1024  # 2MB
COVER_CONTENT_TYPES = {"image/jpeg", "image/png"}

DEFAULT_COURSE_NAME = "未命名课程"


def _file_extension(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


class LearningCourseAdminService:
    """Course lifecycle for tenant admins (learning.course.manage)."""

    @staticmethod
    async def list_courses(
        db: AsyncSession,
        *,
        tenant_id: int,
        page: int,
        per_page: int,
        q: str | None,
        status: str | None,
    ) -> dict:
        courses, total = await LearningCourseRepository.list_paginated(
            db, tenant_id, page, per_page, q=q, status=status
        )
        course_ids = [course.id for course in courses]
        section_counts = await LearningCourseRepository.count_sections_by_course(db, course_ids)
        material_counts = await LearningCourseRepository.count_materials_by_course(db, course_ids)

        items = []
        for course in courses:
            material_total = material_counts.get(course.id, 0)
            if course.visibility == "all":
                # "All employees" courses have no fixed roster; None renders as 全员.
                # Completion is counted over employees who have records (the only
                # ones who can possibly be completed), filtered to active staff.
                learner_count: int | None = None
                candidate_ids = await LearningRecordRepository.list_employee_ids_with_records(db, course.id)
                visible_ids = await _filter_active_employee_ids(db, tenant_id, candidate_ids)
            else:
                visible_ids = await LearningAssignmentRepository.list_visible_employee_ids(
                    db, tenant_id, course.id
                )
                learner_count = len(visible_ids)
            completed = 0
            if material_total > 0 and visible_ids:
                completed_map = await LearningRecordRepository.count_completed_by_course(
                    db, course.id, visible_ids
                )
                completed = sum(1 for count in completed_map.values() if count >= material_total)
            items.append(
                {
                    "id": course.id,
                    "name": course.name,
                    "cover_url": course.cover_url,
                    "status": course.status,
                    "visibility": course.visibility,
                    "section_count": section_counts.get(course.id, 0),
                    "material_count": material_total,
                    "learner_count": learner_count,
                    "completed_count": completed,
                    "updated_at": course.updated_at,
                }
            )
        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": (total + per_page - 1) // per_page if per_page else 0,
        }

    @staticmethod
    async def create_course(
        db: AsyncSession, *, tenant_id: int, employee_id: int, data: LearningCourseCreate
    ):
        return await LearningCourseRepository.create(
            db,
            {
                "tenant_id": tenant_id,
                "name": (data.name or DEFAULT_COURSE_NAME).strip() or DEFAULT_COURSE_NAME,
                "created_by": employee_id,
            },
        )

    @staticmethod
    async def get_course_detail(db: AsyncSession, *, tenant_id: int, course_id: int) -> dict:
        course = await _get_course_or_404(db, tenant_id, course_id)
        sections = await LearningSectionRepository.list_by_course(db, course.id)
        materials = await LearningMaterialRepository.list_by_course(db, course.id)
        materials_by_section: dict[int, list] = {}
        for material in materials:
            materials_by_section.setdefault(material.section_id, []).append(material)
        return {
            "id": course.id,
            "name": course.name,
            "cover_url": course.cover_url,
            "intro": course.intro,
            "status": course.status,
            "visibility": course.visibility,
            "created_by": course.created_by,
            "created_at": course.created_at,
            "updated_at": course.updated_at,
            "sections": [
                {
                    "id": section.id,
                    "course_id": section.course_id,
                    "name": section.name,
                    "sort_order": section.sort_order,
                    "created_at": section.created_at,
                    "updated_at": section.updated_at,
                    "materials": materials_by_section.get(section.id, []),
                }
                for section in sections
            ],
        }

    @staticmethod
    async def update_course(
        db: AsyncSession, *, tenant_id: int, course_id: int, data: LearningCourseUpdate
    ):
        course = await _get_course_or_404(db, tenant_id, course_id)
        payload = data.model_dump(exclude_unset=True)
        for nullable_key in ("intro", "cover_url"):
            if payload.get(nullable_key) == "":
                payload[nullable_key] = None
        if not payload:
            return course
        return await LearningCourseRepository.update(db, course, payload)

    @staticmethod
    async def publish_course(db: AsyncSession, *, tenant_id: int, course_id: int):
        course = await _get_course_or_404(db, tenant_id, course_id)
        if course.status == COURSE_STATUS_PUBLISHED:
            return course
        section_count = (await LearningCourseRepository.count_sections_by_course(db, [course.id])).get(course.id, 0)
        material_count = (await LearningCourseRepository.count_materials_by_course(db, [course.id])).get(course.id, 0)
        if section_count < 1 or material_count < 1:
            raise BusinessError(
                "Course content is not ready",
                status_code=400,
                code="COURSE_NOT_READY",
            )
        return await LearningCourseRepository.update(db, course, {"status": COURSE_STATUS_PUBLISHED})

    @staticmethod
    async def unpublish_course(db: AsyncSession, *, tenant_id: int, course_id: int):
        course = await _get_course_or_404(db, tenant_id, course_id)
        if course.status != COURSE_STATUS_PUBLISHED:
            return course
        return await LearningCourseRepository.update(db, course, {"status": COURSE_STATUS_UNPUBLISHED})

    @staticmethod
    async def delete_course(db: AsyncSession, *, tenant_id: int, course_id: int) -> None:
        course = await _get_course_or_404(db, tenant_id, course_id)
        if course.status == COURSE_STATUS_PUBLISHED:
            raise BusinessError(
                "Published courses cannot be deleted; unpublish first",
                status_code=400,
                code="COURSE_NOT_DELETABLE",
            )
        await LearningCourseRepository.delete(db, course)

    @staticmethod
    async def upload_cover(*, tenant_id: int, filename: str, data: bytes, content_type: str) -> str:
        if content_type not in COVER_CONTENT_TYPES:
            raise ValidationError("Unsupported cover image format")
        if len(data) > COVER_MAX_BYTES:
            raise ValidationError("Cover image exceeds the size limit")
        ext = _file_extension(filename) or "png"
        key = f"learning-covers/{tenant_id}/{uuid.uuid4().hex}.{ext}"
        return await create_storage_client().upload(key, data, content_type=content_type)


class LearningSectionAdminService:
    """Section management inside one course."""

    @staticmethod
    async def create_section(
        db: AsyncSession, *, tenant_id: int, course_id: int, name: str | None
    ):
        await _get_course_or_404(db, tenant_id, course_id)
        sort_order = await LearningSectionRepository.next_sort_order(db, course_id)
        return await LearningSectionRepository.create(
            db,
            {
                "tenant_id": tenant_id,
                "course_id": course_id,
                "name": (name or f"章节 {sort_order + 1}").strip(),
                "sort_order": sort_order,
            },
        )

    @staticmethod
    async def rename_section(db: AsyncSession, *, tenant_id: int, section_id: int, name: str):
        section = await _get_section_or_404(db, tenant_id, section_id)
        return await LearningSectionRepository.update(db, section, {"name": name.strip()})

    @staticmethod
    async def reorder_sections(db: AsyncSession, *, tenant_id: int, course_id: int, ordered_ids: list[int]) -> None:
        await _get_course_or_404(db, tenant_id, course_id)
        existing = await LearningSectionRepository.list_by_course(db, course_id)
        _validate_order_payload([section.id for section in existing], ordered_ids)
        await LearningSectionRepository.apply_order(db, course_id, ordered_ids)

    @staticmethod
    async def delete_section(db: AsyncSession, *, tenant_id: int, section_id: int) -> None:
        section = await _get_section_or_404(db, tenant_id, section_id)
        await LearningSectionRepository.delete(db, section)


class LearningMaterialAdminService:
    """Material upload credential issuing and material management."""

    @staticmethod
    async def create_upload_credential(
        *, tenant_id: int, data: MaterialUploadCredentialRequest
    ) -> dict:
        ext = _file_extension(data.filename)
        if ext not in MATERIAL_EXTENSIONS.get(data.material_type, set()):
            raise ValidationError("Unsupported file format")
        if data.file_size > MATERIAL_SIZE_LIMITS[data.material_type]:
            raise ValidationError("File exceeds the size limit")

        if data.material_type == MATERIAL_TYPE_VIDEO:
            credential = await get_vod_client().create_upload_credential(
                title=data.filename, filename=data.filename
            )
            return {
                "channel": "vod",
                "video_id": credential.video_id,
                "upload_address": credential.upload_address,
                "upload_auth": credential.upload_auth,
            }

        key = f"learning-materials/{tenant_id}/{uuid.uuid4().hex}.{ext}"
        upload_url = await create_storage_client().get_presigned_upload_url(
            key, content_type=MATERIAL_CONTENT_TYPES[ext]
        )
        return {"channel": "oss", "upload_url": upload_url, "file_key": key}

    @staticmethod
    async def create_material(
        db: AsyncSession, *, tenant_id: int, section_id: int, data: LearningMaterialCreate
    ):
        section = await _get_section_or_404(db, tenant_id, section_id)
        if data.type == MATERIAL_TYPE_VIDEO:
            if not data.vod_video_id:
                raise ValidationError("vod_video_id is required for video materials")
            transcode_status = TRANSCODE_OK if settings.VOD_PROVIDER == "mock" else TRANSCODE_PROCESSING
            file_key = None
        else:
            if not data.file_key:
                raise ValidationError("file_key is required for audio/pdf/document materials")
            transcode_status = None
            file_key = data.file_key
        sort_order = await LearningMaterialRepository.next_sort_order(db, section.id)
        return await LearningMaterialRepository.create(
            db,
            {
                "tenant_id": tenant_id,
                "course_id": section.course_id,
                "section_id": section.id,
                "name": (data.name or "").strip() or "未命名材料",
                "type": data.type,
                "vod_video_id": data.vod_video_id,
                "file_key": file_key,
                "file_size": data.file_size,
                "duration_seconds": data.duration_seconds,
                "transcode_status": transcode_status,
                "sort_order": sort_order,
            },
        )

    @staticmethod
    async def rename_material(db: AsyncSession, *, tenant_id: int, material_id: int, name: str):
        material = await _get_material_or_404(db, tenant_id, material_id)
        return await LearningMaterialRepository.update(db, material, {"name": name.strip()})

    @staticmethod
    async def reorder_materials(db: AsyncSession, *, tenant_id: int, section_id: int, ordered_ids: list[int]) -> None:
        section = await _get_section_or_404(db, tenant_id, section_id)
        materials = await LearningMaterialRepository.list_by_course(db, section.course_id)
        existing = [material.id for material in materials if material.section_id == section.id]
        _validate_order_payload(existing, ordered_ids)
        await LearningMaterialRepository.apply_order(db, section.id, ordered_ids)

    @staticmethod
    async def delete_material(db: AsyncSession, *, tenant_id: int, material_id: int) -> None:
        material = await _get_material_or_404(db, tenant_id, material_id)
        await LearningMaterialRepository.delete(db, material)

    @staticmethod
    async def retranscode_material(db: AsyncSession, *, tenant_id: int, material_id: int):
        material = await _get_material_or_404(db, tenant_id, material_id)
        if material.type != MATERIAL_TYPE_VIDEO or material.transcode_status != TRANSCODE_FAILED:
            raise BusinessError(
                "Only failed video materials can be re-transcoded",
                status_code=400,
                code="RETRANSCODE_NOT_ALLOWED",
            )
        if settings.VOD_PROVIDER == "mock":
            return await LearningMaterialRepository.update(db, material, {"transcode_status": TRANSCODE_OK})
        accepted = await get_vod_client().submit_transcode(video_id=material.vod_video_id or "")
        if not accepted:
            raise BusinessError("Transcode submission failed", status_code=502, code="TRANSCODE_SUBMIT_FAILED")
        return await LearningMaterialRepository.update(db, material, {"transcode_status": TRANSCODE_PROCESSING})

    @staticmethod
    async def handle_vod_event(db: AsyncSession, *, provider: str, payload: dict[str, Any]) -> bool:
        """Apply one transcode event; returns True when a material was updated.

        One provider account feeds every environment (production mirrors its
        callback to test), so an event whose video_id belongs to another
        environment matches no material here and is ignored on purpose.
        """
        event = get_vod_client().parse_transcode_event(payload)
        if event is None:
            logger.info(
                "VOD event unparsed, ignored (provider=%s, event_type=%s, keys=%s)",
                provider,
                payload.get("EventType"),
                sorted(payload.keys()),
            )
            return False
        updated = await LearningMaterialRepository.update_transcode_by_vod_video_id(
            db,
            event.video_id,
            TRANSCODE_OK if event.success else TRANSCODE_FAILED,
            duration_seconds=event.duration_seconds,
        )
        if updated:
            logger.info(
                "VOD transcode event applied (provider=%s, video_id=%s, success=%s, duration=%s)",
                provider,
                event.video_id,
                event.success,
                event.duration_seconds,
            )
        else:
            logger.info(
                "VOD transcode event unmatched, ignored (provider=%s, video_id=%s)",
                provider,
                event.video_id,
            )
        return updated > 0


async def _get_course_or_404(db: AsyncSession, tenant_id: int, course_id: int):
    course = await LearningCourseRepository.get_by_id(db, tenant_id, course_id)
    if course is None:
        raise NotFoundError("Course not found")
    return course


async def _get_section_or_404(db: AsyncSession, tenant_id: int, section_id: int):
    section = await LearningSectionRepository.get_by_id(db, tenant_id, section_id)
    if section is None:
        raise NotFoundError("Section not found")
    return section


async def _get_material_or_404(db: AsyncSession, tenant_id: int, material_id: int):
    material = await LearningMaterialRepository.get_by_id(db, tenant_id, material_id)
    if material is None:
        raise NotFoundError("Material not found")
    return material


async def _filter_active_employee_ids(db: AsyncSession, tenant_id: int, employee_ids: set[int]) -> set[int]:
    if not employee_ids:
        return set()
    from app.models.employee import Employee
    from sqlalchemy import select

    result = await db.execute(
        select(Employee.id).where(
            Employee.id.in_(employee_ids),
            Employee.tenant_id == tenant_id,
            Employee.is_active.is_(True),
        )
    )
    return set(result.scalars().all())


def _validate_order_payload(existing_ids: list[int], ordered_ids: list[int]) -> None:
    if set(ordered_ids) != set(existing_ids) or len(ordered_ids) != len(existing_ids):
        raise ValidationError("ordered_ids must match the existing items exactly")
