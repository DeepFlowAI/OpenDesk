"""
Unit tests for learning center admin services: course lifecycle, section/material
management, upload credential issuing and VOD transcode event handling.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import BusinessError, NotFoundError, ValidationError
from app.schemas.learning import (
    LearningCourseCreate,
    LearningCourseUpdate,
    LearningMaterialCreate,
    MaterialUploadCredentialRequest,
)
from app.services.learning_admin_service import (
    LearningCourseAdminService,
    LearningMaterialAdminService,
    LearningSectionAdminService,
)

TENANT = 1


def _course(**overrides):
    data = {
        "id": 10,
        "tenant_id": TENANT,
        "name": "新员工入职培训",
        "status": "draft",
        "visibility": "assigned",
        "cover_url": None,
        "intro": None,
        "created_by": 7,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def _section(**overrides):
    data = {"id": 20, "tenant_id": TENANT, "course_id": 10, "name": "章节 1", "sort_order": 0}
    data.update(overrides)
    return SimpleNamespace(**data)


def _material(**overrides):
    data = {
        "id": 30,
        "tenant_id": TENANT,
        "course_id": 10,
        "section_id": 20,
        "name": "开场白",
        "type": "video",
        "vod_video_id": "vod-1",
        "file_key": None,
        "transcode_status": "ok",
        "duration_seconds": None,
        "file_size": 1024,
        "sort_order": 0,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


@pytest.fixture
def mock_db():
    return AsyncMock()


class TestCourseLifecycle:
    @pytest.mark.asyncio
    async def test_create_course_defaults_to_draft_and_assigned(self, mock_db, monkeypatch):
        captured = {}

        async def fake_create(db, data):
            captured.update(data)
            return _course(name=data["name"])

        monkeypatch.setattr(
            "app.services.learning_admin_service.LearningCourseRepository.create", fake_create
        )

        course = await LearningCourseAdminService.create_course(
            mock_db, tenant_id=TENANT, employee_id=7, data=LearningCourseCreate()
        )
        assert captured["tenant_id"] == TENANT
        assert captured["created_by"] == 7
        assert course.name == "未命名课程"

    @pytest.mark.asyncio
    async def test_publish_without_content_raises_not_ready(self, mock_db, monkeypatch):
        monkeypatch.setattr(
            "app.services.learning_admin_service.LearningCourseRepository.get_by_id",
            AsyncMock(return_value=_course()),
        )
        monkeypatch.setattr(
            "app.services.learning_admin_service.LearningCourseRepository.count_sections_by_course",
            AsyncMock(return_value={10: 1}),
        )
        monkeypatch.setattr(
            "app.services.learning_admin_service.LearningCourseRepository.count_materials_by_course",
            AsyncMock(return_value={}),
        )

        with pytest.raises(BusinessError) as exc_info:
            await LearningCourseAdminService.publish_course(mock_db, tenant_id=TENANT, course_id=10)
        assert exc_info.value.code == "COURSE_NOT_READY"

    @pytest.mark.asyncio
    async def test_publish_with_content_marks_published(self, mock_db, monkeypatch):
        monkeypatch.setattr(
            "app.services.learning_admin_service.LearningCourseRepository.get_by_id",
            AsyncMock(return_value=_course()),
        )
        monkeypatch.setattr(
            "app.services.learning_admin_service.LearningCourseRepository.count_sections_by_course",
            AsyncMock(return_value={10: 2}),
        )
        monkeypatch.setattr(
            "app.services.learning_admin_service.LearningCourseRepository.count_materials_by_course",
            AsyncMock(return_value={10: 3}),
        )
        update = AsyncMock(side_effect=lambda db, course, data: _course(status=data["status"]))
        monkeypatch.setattr(
            "app.services.learning_admin_service.LearningCourseRepository.update", update
        )

        course = await LearningCourseAdminService.publish_course(mock_db, tenant_id=TENANT, course_id=10)
        assert course.status == "published"

    @pytest.mark.asyncio
    async def test_delete_published_course_rejected(self, mock_db, monkeypatch):
        monkeypatch.setattr(
            "app.services.learning_admin_service.LearningCourseRepository.get_by_id",
            AsyncMock(return_value=_course(status="published")),
        )

        with pytest.raises(BusinessError) as exc_info:
            await LearningCourseAdminService.delete_course(mock_db, tenant_id=TENANT, course_id=10)
        assert exc_info.value.code == "COURSE_NOT_DELETABLE"

    @pytest.mark.asyncio
    async def test_delete_draft_course_calls_repository(self, mock_db, monkeypatch):
        monkeypatch.setattr(
            "app.services.learning_admin_service.LearningCourseRepository.get_by_id",
            AsyncMock(return_value=_course()),
        )
        delete = AsyncMock()
        monkeypatch.setattr(
            "app.services.learning_admin_service.LearningCourseRepository.delete", delete
        )

        await LearningCourseAdminService.delete_course(mock_db, tenant_id=TENANT, course_id=10)
        delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_course_not_found_raises(self, mock_db, monkeypatch):
        monkeypatch.setattr(
            "app.services.learning_admin_service.LearningCourseRepository.get_by_id",
            AsyncMock(return_value=None),
        )

        with pytest.raises(NotFoundError):
            await LearningCourseAdminService.update_course(
                mock_db, tenant_id=TENANT, course_id=999, data=LearningCourseUpdate(name="x")
            )


class TestSectionManagement:
    @pytest.mark.asyncio
    async def test_create_section_uses_default_name_and_next_order(self, mock_db, monkeypatch):
        monkeypatch.setattr(
            "app.services.learning_admin_service.LearningCourseRepository.get_by_id",
            AsyncMock(return_value=_course()),
        )
        monkeypatch.setattr(
            "app.services.learning_admin_service.LearningSectionRepository.next_sort_order",
            AsyncMock(return_value=2),
        )
        captured = {}

        async def fake_create(db, data):
            captured.update(data)
            return _section(name=data["name"], sort_order=data["sort_order"])

        monkeypatch.setattr(
            "app.services.learning_admin_service.LearningSectionRepository.create", fake_create
        )

        section = await LearningSectionAdminService.create_section(
            mock_db, tenant_id=TENANT, course_id=10, name=None
        )
        assert section.name == "章节 3"
        assert captured["sort_order"] == 2

    @pytest.mark.asyncio
    async def test_reorder_rejects_mismatched_ids(self, mock_db, monkeypatch):
        monkeypatch.setattr(
            "app.services.learning_admin_service.LearningCourseRepository.get_by_id",
            AsyncMock(return_value=_course()),
        )
        monkeypatch.setattr(
            "app.services.learning_admin_service.LearningSectionRepository.list_by_course",
            AsyncMock(return_value=[_section(id=1), _section(id=2)]),
        )

        with pytest.raises(ValidationError):
            await LearningSectionAdminService.reorder_sections(
                mock_db, tenant_id=TENANT, course_id=10, ordered_ids=[2, 3]
            )


class TestMaterialManagement:
    def _credential_request(self, **overrides):
        data = {"filename": "intro.mp4", "file_size": 1024, "material_type": "video"}
        data.update(overrides)
        return MaterialUploadCredentialRequest(**data)

    @pytest.mark.asyncio
    async def test_upload_credential_rejects_unknown_extension(self):
        with pytest.raises(ValidationError):
            await LearningMaterialAdminService.create_upload_credential(
                tenant_id=TENANT,
                data=self._credential_request(filename="slides.xyz", material_type="document"),
            )

    @pytest.mark.asyncio
    async def test_upload_credential_rejects_oversized_file(self):
        with pytest.raises(ValidationError):
            await LearningMaterialAdminService.create_upload_credential(
                tenant_id=TENANT,
                data=self._credential_request(
                    filename="a.pdf", material_type="pdf", file_size=51 * 1024 * 1024
                ),
            )

    @pytest.mark.asyncio
    async def test_upload_credential_video_goes_to_vod_channel(self, monkeypatch):
        from app.libs.vod.providers.mock import MockVodClient

        monkeypatch.setattr(
            "app.services.learning_admin_service.get_vod_client", lambda: MockVodClient()
        )
        result = await LearningMaterialAdminService.create_upload_credential(
            tenant_id=TENANT, data=self._credential_request()
        )
        assert result["channel"] == "vod"
        assert result["video_id"].startswith("MOCK-")

    @pytest.mark.asyncio
    async def test_upload_credential_pdf_goes_to_oss_channel(self, monkeypatch):
        class _FakeStorage:
            async def get_presigned_upload_url(self, key, content_type="application/octet-stream"):
                return f"https://oss.example.com/{key}?signed"

        monkeypatch.setattr(
            "app.services.learning_admin_service.create_storage_client", lambda: _FakeStorage()
        )
        result = await LearningMaterialAdminService.create_upload_credential(
            tenant_id=TENANT,
            data=self._credential_request(filename="handbook.pdf", material_type="pdf", file_size=1024),
        )
        assert result["channel"] == "oss"
        assert result["file_key"].startswith(f"learning-materials/{TENANT}/")
        assert result["file_key"].endswith(".pdf")

    @pytest.mark.asyncio
    async def test_upload_credential_office_document_goes_to_oss_channel(self, monkeypatch):
        class _FakeStorage:
            async def get_presigned_upload_url(self, key, content_type="application/octet-stream"):
                return f"https://oss.example.com/{key}?signed"

        monkeypatch.setattr(
            "app.services.learning_admin_service.create_storage_client", lambda: _FakeStorage()
        )
        result = await LearningMaterialAdminService.create_upload_credential(
            tenant_id=TENANT,
            data=self._credential_request(
                filename="slides.pptx", material_type="document", file_size=2048
            ),
        )
        assert result["channel"] == "oss"
        assert result["file_key"].endswith(".pptx")

    @pytest.mark.asyncio
    async def test_create_video_material_requires_vod_video_id(self, mock_db, monkeypatch):
        monkeypatch.setattr(
            "app.services.learning_admin_service.LearningSectionRepository.get_by_id",
            AsyncMock(return_value=_section()),
        )

        with pytest.raises(ValidationError):
            await LearningMaterialAdminService.create_material(
                mock_db,
                tenant_id=TENANT,
                section_id=20,
                data=LearningMaterialCreate(type="video"),
            )

    @pytest.mark.asyncio
    async def test_create_video_material_mock_provider_is_ready(self, mock_db, monkeypatch):
        monkeypatch.setattr(
            "app.services.learning_admin_service.LearningSectionRepository.get_by_id",
            AsyncMock(return_value=_section()),
        )
        monkeypatch.setattr(
            "app.services.learning_admin_service.LearningMaterialRepository.next_sort_order",
            AsyncMock(return_value=1),
        )
        captured = {}

        async def fake_create(db, data):
            captured.update(data)
            return _material(**{k: v for k, v in data.items() if k in _material().__dict__})

        monkeypatch.setattr(
            "app.services.learning_admin_service.LearningMaterialRepository.create", fake_create
        )
        monkeypatch.setattr("app.services.learning_admin_service.settings.VOD_PROVIDER", "mock")

        await LearningMaterialAdminService.create_material(
            mock_db,
            tenant_id=TENANT,
            section_id=20,
            data=LearningMaterialCreate(type="video", vod_video_id="vod-1", name="开场白"),
        )
        assert captured["transcode_status"] == "ok"
        assert captured["sort_order"] == 1

    @pytest.mark.asyncio
    async def test_retranscode_only_for_failed_videos(self, mock_db, monkeypatch):
        monkeypatch.setattr(
            "app.services.learning_admin_service.LearningMaterialRepository.get_by_id",
            AsyncMock(return_value=_material(transcode_status="ok")),
        )

        with pytest.raises(BusinessError) as exc_info:
            await LearningMaterialAdminService.retranscode_material(mock_db, tenant_id=TENANT, material_id=30)
        assert exc_info.value.code == "RETRANSCODE_NOT_ALLOWED"

    @pytest.mark.asyncio
    async def test_retranscode_failed_video_mock_marks_ok(self, mock_db, monkeypatch):
        monkeypatch.setattr(
            "app.services.learning_admin_service.LearningMaterialRepository.get_by_id",
            AsyncMock(return_value=_material(transcode_status="failed")),
        )
        update = AsyncMock(side_effect=lambda db, m, data: _material(transcode_status=data["transcode_status"]))
        monkeypatch.setattr(
            "app.services.learning_admin_service.LearningMaterialRepository.update", update
        )
        monkeypatch.setattr("app.services.learning_admin_service.settings.VOD_PROVIDER", "mock")

        material = await LearningMaterialAdminService.retranscode_material(
            mock_db, tenant_id=TENANT, material_id=30
        )
        assert material.transcode_status == "ok"

    @pytest.mark.asyncio
    async def test_handle_vod_event_updates_material(self, mock_db, monkeypatch):
        update = AsyncMock(return_value=1)
        monkeypatch.setattr(
            "app.services.learning_admin_service.LearningMaterialRepository.update_transcode_by_vod_video_id",
            update,
        )
        from app.libs.vod.providers.mock import MockVodClient

        monkeypatch.setattr(
            "app.services.learning_admin_service.get_vod_client", lambda: MockVodClient()
        )

        received = await LearningMaterialAdminService.handle_vod_event(
            mock_db, provider="mock", payload={"video_id": "vod-1", "success": False}
        )
        assert received is True
        assert update.call_args[0][2] == "failed"

    @pytest.mark.asyncio
    async def test_handle_vod_event_ignores_unknown_video(self, mock_db, monkeypatch):
        # Mirrored callbacks deliver every event to every environment; an event
        # whose video_id lives in another environment matches no material here.
        update = AsyncMock(return_value=0)
        monkeypatch.setattr(
            "app.services.learning_admin_service.LearningMaterialRepository.update_transcode_by_vod_video_id",
            update,
        )
        from app.libs.vod.providers.mock import MockVodClient

        monkeypatch.setattr(
            "app.services.learning_admin_service.get_vod_client", lambda: MockVodClient()
        )
        received = await LearningMaterialAdminService.handle_vod_event(
            mock_db, provider="mock", payload={"video_id": "other-env-video", "success": True}
        )
        assert received is False
        assert update.await_count == 1

    @pytest.mark.asyncio
    async def test_handle_vod_event_ignores_irrelevant_payload(self, mock_db, monkeypatch):
        from app.libs.vod.providers.mock import MockVodClient

        monkeypatch.setattr(
            "app.services.learning_admin_service.get_vod_client", lambda: MockVodClient()
        )
        received = await LearningMaterialAdminService.handle_vod_event(
            mock_db, provider="mock", payload={"unrelated": True}
        )
        assert received is False
