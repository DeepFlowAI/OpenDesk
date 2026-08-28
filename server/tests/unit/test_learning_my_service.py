"""Unit tests for the employee-side learning service (visibility gating, open /
progress / complete semantics)."""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import BusinessError, NotFoundError
from app.libs.vod.base import VodPlayInfo
from app.services.learning_my_service import LearningMyService

TENANT_ID = 1
EMPLOYEE_ID = 100
COURSE_ID = 10


def _course(status: str = "published", visibility: str = "assigned"):
    return SimpleNamespace(
        id=COURSE_ID,
        tenant_id=TENANT_ID,
        name="新人培训",
        cover_url=None,
        intro="简介",
        status=status,
        visibility=visibility,
        updated_at=None,
    )


def _material(material_id: int = 1, mtype: str = "video", duration: int | None = 100):
    return SimpleNamespace(
        id=material_id,
        tenant_id=TENANT_ID,
        course_id=COURSE_ID,
        section_id=5,
        name="材料",
        type=mtype,
        vod_video_id="vid-1" if mtype == "video" else None,
        file_key=None if mtype == "video" else f"learning-materials/1/{material_id}.bin",
        duration_seconds=duration,
        transcode_status="ok" if mtype == "video" else None,
        file_size=1024,
        sort_order=0,
        created_at=None,
        updated_at=None,
    )


def _record(status: str = "in_progress", position: int = 0):
    return SimpleNamespace(
        id=1,
        material_id=1,
        course_id=COURSE_ID,
        employee_id=EMPLOYEE_ID,
        status=status,
        play_position_seconds=position,
        completed_at=None,
        last_learn_at=None,
    )


def _visibility_patches(course, visible_ids):
    return (
        patch(
            "app.services.learning_my_service.LearningCourseRepository.get_by_id",
            new=AsyncMock(return_value=course),
        ),
        patch(
            "app.services.learning_my_service.LearningAssignmentRepository.list_visible_employee_ids",
            new=AsyncMock(return_value=visible_ids),
        ),
    )


class TestVisibilityGating:
    async def test_unpublished_course_is_404(self):
        course, visible = _visibility_patches(_course(status="draft"), {EMPLOYEE_ID})
        with course, visible:
            with pytest.raises(NotFoundError):
                await LearningMyService.get_my_course_detail(
                    AsyncMock(), tenant_id=TENANT_ID, course_id=COURSE_ID, employee_id=EMPLOYEE_ID
                )

    async def test_employee_outside_assignments_is_404(self):
        course, visible = _visibility_patches(_course(), {999})
        with course, visible:
            with pytest.raises(NotFoundError):
                await LearningMyService.get_my_course_detail(
                    AsyncMock(), tenant_id=TENANT_ID, course_id=COURSE_ID, employee_id=EMPLOYEE_ID
                )

    async def test_all_visibility_needs_no_assignment_lookup(self):
        course, visible = _visibility_patches(_course(visibility="all"), set())
        with (
            course,
            visible as visible_mock,
            patch(
                "app.services.learning_my_service.LearningSectionRepository.list_by_course",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "app.services.learning_my_service.LearningMaterialRepository.list_by_course",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "app.services.learning_my_service.LearningRecordRepository.list_by_course_employee",
                new=AsyncMock(return_value=[]),
            ),
        ):
            detail = await LearningMyService.get_my_course_detail(
                AsyncMock(), tenant_id=TENANT_ID, course_id=COURSE_ID, employee_id=EMPLOYEE_ID
            )
        visible_mock.assert_not_awaited()
        assert detail["id"] == COURSE_ID and detail["status"] == "not_started"


class TestListMyCourses:
    async def test_filters_to_visible_published_and_aggregates(self):
        all_course = _course(visibility="all")
        assigned_hit = SimpleNamespace(**{**vars(_course()), "id": 11, "name": "指派课"})
        assigned_miss = SimpleNamespace(**{**vars(_course()), "id": 12, "name": "不可见课"})
        with (
            patch(
                "app.services.learning_my_service.LearningCourseRepository.list_paginated",
                new=AsyncMock(return_value=([all_course, assigned_hit, assigned_miss], 3)),
            ),
            patch(
                "app.services.learning_my_service.LearningAssignmentRepository.expand_assignments",
                new=AsyncMock(return_value={11: {EMPLOYEE_ID}, 12: {999}}),
            ),
            patch(
                "app.services.learning_my_service.LearningCourseRepository.count_materials_by_course",
                new=AsyncMock(return_value={COURSE_ID: 2, 11: 4}),
            ),
            patch(
                "app.services.learning_my_service.LearningRecordRepository.aggregate_by_courses_for_employee",
                new=AsyncMock(return_value={COURSE_ID: {"total_records": 1, "completed": 1}}),
            ),
        ):
            result = await LearningMyService.list_my_courses(
                AsyncMock(), tenant_id=TENANT_ID, employee_id=EMPLOYEE_ID, q=None, page=1, per_page=20
            )
        ids = [item["id"] for item in result["items"]]
        assert ids == [COURSE_ID, 11]
        mine = result["items"][0]
        assert mine["completed_count"] == 1 and mine["progress"] == 50 and mine["status"] == "in_progress"
        untouched = result["items"][1]
        assert untouched["progress"] == 0 and untouched["status"] == "not_started"


class TestOpenMaterial:
    async def test_video_returns_play_url_and_creates_record(self):
        record = _record()
        vod = MagicMock()
        vod.get_play_info = AsyncMock(return_value=VodPlayInfo(video_id="vid-1", play_url="https://play", status="ok"))
        course, visible = _visibility_patches(_course(), {EMPLOYEE_ID})
        with (
            course,
            visible,
            patch(
                "app.services.learning_my_service.LearningMaterialRepository.get_by_id",
                new=AsyncMock(return_value=_material()),
            ),
            patch(
                "app.services.learning_my_service.LearningRecordRepository.get_record",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.services.learning_my_service.LearningRecordRepository.create_record",
                new=AsyncMock(return_value=record),
            ) as create_mock,
            patch(
                "app.services.learning_my_service.LearningRecordRepository.save_record",
                new=AsyncMock(side_effect=lambda db, r: r),
            ),
            patch("app.services.learning_my_service.get_vod_client", return_value=vod),
        ):
            result = await LearningMyService.open_material(
                AsyncMock(), tenant_id=TENANT_ID, material_id=1, employee_id=EMPLOYEE_ID
            )
        assert result["play_url"] == "https://play"
        assert result["file_url"] is None
        create_mock.assert_awaited_once()
        assert create_mock.await_args.args[1]["status"] == "in_progress"

    async def test_video_processing_returns_no_play_url(self):
        vod = MagicMock()
        vod.get_play_info = AsyncMock(return_value=VodPlayInfo(video_id="vid-1", play_url=None, status="processing"))
        course, visible = _visibility_patches(_course(), {EMPLOYEE_ID})
        with (
            course,
            visible,
            patch(
                "app.services.learning_my_service.LearningMaterialRepository.get_by_id",
                new=AsyncMock(return_value=_material()),
            ),
            patch(
                "app.services.learning_my_service.LearningRecordRepository.get_record",
                new=AsyncMock(return_value=_record()),
            ),
            patch(
                "app.services.learning_my_service.LearningRecordRepository.save_record",
                new=AsyncMock(side_effect=lambda db, r: r),
            ),
            patch("app.services.learning_my_service.get_vod_client", return_value=vod),
        ):
            result = await LearningMyService.open_material(
                AsyncMock(), tenant_id=TENANT_ID, material_id=1, employee_id=EMPLOYEE_ID
            )
        assert result["play_url"] is None

    async def test_pdf_returns_preview_and_download_urls(self):
        storage = MagicMock()
        storage.get_temporary_url = AsyncMock(side_effect=["https://preview", "https://download"])
        course, visible = _visibility_patches(_course(), {EMPLOYEE_ID})
        with (
            course,
            visible,
            patch(
                "app.services.learning_my_service.LearningMaterialRepository.get_by_id",
                new=AsyncMock(return_value=_material(mtype="pdf", duration=None)),
            ),
            patch(
                "app.services.learning_my_service.LearningRecordRepository.get_record",
                new=AsyncMock(return_value=_record(position=3)),
            ),
            patch(
                "app.services.learning_my_service.LearningRecordRepository.save_record",
                new=AsyncMock(side_effect=lambda db, r: r),
            ),
            patch("app.services.learning_my_service.create_storage_client", return_value=storage),
        ):
            result = await LearningMyService.open_material(
                AsyncMock(), tenant_id=TENANT_ID, material_id=1, employee_id=EMPLOYEE_ID
            )
        assert result["file_url"] == "https://preview"
        assert result["download_url"] == "https://download"
        assert result["file_name"] == "材料.bin"
        # Resume position comes back for the client.
        assert result["play_position_seconds"] == 3

    async def test_document_returns_preview_and_download_urls(self):
        storage = MagicMock()
        storage.get_temporary_url = AsyncMock(side_effect=["https://preview", "https://download"])
        course, visible = _visibility_patches(_course(), {EMPLOYEE_ID})
        material = _material(mtype="document", duration=None)
        material.file_key = "learning-materials/1/1.pptx"
        with (
            course,
            visible,
            patch(
                "app.services.learning_my_service.LearningMaterialRepository.get_by_id",
                new=AsyncMock(return_value=material),
            ),
            patch(
                "app.services.learning_my_service.LearningRecordRepository.get_record",
                new=AsyncMock(return_value=_record(position=0)),
            ),
            patch(
                "app.services.learning_my_service.LearningRecordRepository.save_record",
                new=AsyncMock(side_effect=lambda db, r: r),
            ),
            patch("app.services.learning_my_service.create_storage_client", return_value=storage),
        ):
            result = await LearningMyService.open_material(
                AsyncMock(), tenant_id=TENANT_ID, material_id=1, employee_id=EMPLOYEE_ID
            )
        assert result["file_url"] == "https://preview"
        assert result["download_url"] == "https://download"
        assert result["file_name"] == "材料.pptx"


class TestReportProgress:
    async def test_position_never_regresses(self):
        record = _record(position=80)
        course, visible = _visibility_patches(_course(), {EMPLOYEE_ID})
        with (
            course,
            visible,
            patch(
                "app.services.learning_my_service.LearningMaterialRepository.get_by_id",
                new=AsyncMock(return_value=_material()),
            ),
            patch(
                "app.services.learning_my_service.LearningRecordRepository.get_record",
                new=AsyncMock(return_value=record),
            ),
            patch(
                "app.services.learning_my_service.LearningRecordRepository.save_record",
                new=AsyncMock(side_effect=lambda db, r: r),
            ),
        ):
            saved = await LearningMyService.report_progress(
                AsyncMock(), tenant_id=TENANT_ID, material_id=1, employee_id=EMPLOYEE_ID, position_seconds=30
            )
        assert saved.play_position_seconds == 80


class TestCompleteMaterial:
    def _patches(self, material, record):
        course, visible = _visibility_patches(_course(), {EMPLOYEE_ID})
        return (
            course,
            visible,
            patch(
                "app.services.learning_my_service.LearningMaterialRepository.get_by_id",
                new=AsyncMock(return_value=material),
            ),
            patch(
                "app.services.learning_my_service.LearningRecordRepository.get_record",
                new=AsyncMock(return_value=record),
            ),
            patch(
                "app.services.learning_my_service.LearningRecordRepository.save_record",
                new=AsyncMock(side_effect=lambda db, r: r),
            ),
            patch(
                "app.services.learning_my_service.LearningCourseRepository.count_materials_by_course",
                new=AsyncMock(return_value={COURSE_ID: 1}),
            ),
            patch(
                "app.services.learning_my_service.LearningRecordRepository.list_by_course_employee",
                new=AsyncMock(return_value=[record]),
            ),
        )

    async def test_video_below_90_percent_rejected(self):
        ctx = self._patches(_material(duration=100), _record(position=89))
        with ctx[0], ctx[1], ctx[2], ctx[3], ctx[4], ctx[5], ctx[6]:
            with pytest.raises(BusinessError) as exc:
                await LearningMyService.complete_material(
                    AsyncMock(), tenant_id=TENANT_ID, material_id=1, employee_id=EMPLOYEE_ID
                )
        assert exc.value.code == "COMPLETE_NOT_ELIGIBLE"

    async def test_video_without_duration_rejected(self):
        ctx = self._patches(_material(duration=None), _record(position=500))
        with ctx[0], ctx[1], ctx[2], ctx[3], ctx[4], ctx[5], ctx[6]:
            with pytest.raises(BusinessError) as exc:
                await LearningMyService.complete_material(
                    AsyncMock(), tenant_id=TENANT_ID, material_id=1, employee_id=EMPLOYEE_ID
                )
        assert exc.value.code == "COMPLETE_NOT_ELIGIBLE"

    async def test_video_at_90_percent_completes(self):
        record = _record(position=90)
        ctx = self._patches(_material(duration=100), record)
        with ctx[0], ctx[1], ctx[2], ctx[3], ctx[4], ctx[5], ctx[6]:
            result = await LearningMyService.complete_material(
                AsyncMock(), tenant_id=TENANT_ID, material_id=1, employee_id=EMPLOYEE_ID
            )
        assert record.status == "completed" and record.completed_at is not None
        assert result["course_status"] == "completed"
        assert result["course_completed_count"] == 1

    async def test_pdf_completes_without_position(self):
        record = _record(position=0)
        ctx = self._patches(_material(mtype="pdf", duration=None), record)
        with ctx[0], ctx[1], ctx[2], ctx[3], ctx[4], ctx[5], ctx[6]:
            result = await LearningMyService.complete_material(
                AsyncMock(), tenant_id=TENANT_ID, material_id=1, employee_id=EMPLOYEE_ID
            )
        assert record.status == "completed"
        assert result["course_status"] == "completed"

    async def test_repeat_complete_is_idempotent(self):
        record = _record(status="completed", position=100)
        record.completed_at = datetime(2026, 8, 1, tzinfo=timezone.utc)
        material = _material(duration=100)
        course, visible = _visibility_patches(_course(), {EMPLOYEE_ID})
        with (
            course,
            visible,
            patch(
                "app.services.learning_my_service.LearningMaterialRepository.get_by_id",
                new=AsyncMock(return_value=material),
            ),
            patch(
                "app.services.learning_my_service.LearningRecordRepository.get_record",
                new=AsyncMock(return_value=record),
            ),
            patch(
                "app.services.learning_my_service.LearningRecordRepository.save_record",
                new=AsyncMock(side_effect=lambda db, r: r),
            ) as save_mock,
            patch(
                "app.services.learning_my_service.LearningCourseRepository.count_materials_by_course",
                new=AsyncMock(return_value={COURSE_ID: 1}),
            ),
            patch(
                "app.services.learning_my_service.LearningRecordRepository.list_by_course_employee",
                new=AsyncMock(return_value=[record]),
            ),
        ):
            result = await LearningMyService.complete_material(
                AsyncMock(), tenant_id=TENANT_ID, material_id=1, employee_id=EMPLOYEE_ID
            )
        save_mock.assert_not_awaited()
        assert result["record"].status == "completed"
