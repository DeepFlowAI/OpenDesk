"""
Unit tests for knowledge service helpers.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch, sentinel

import pytest

from app.core.exceptions import ValidationError
from app.models.knowledge import KnowledgeDocument, KnowledgeDocumentAttachment, KnowledgeInspiration
from app.schemas.knowledge import KnowledgeDocumentCreate, KnowledgeDocumentUpdate, KnowledgeInspirationCreate
from app.services.knowledge_service import KnowledgeService, html_to_plain_text


def test_html_to_plain_text_strips_tags_and_collapses_whitespace() -> None:
    html = "<h2>退款</h2><p>  先核实&nbsp;订单 </p><script>alert(1)</script>"

    assert html_to_plain_text(html) == "退款 先核实 订单 alert(1)"


def test_html_to_plain_text_keeps_image_only_content_non_empty() -> None:
    html = '<p><img src="https://cdn.example.com/a.png" alt="退款截图"></p>'

    assert html_to_plain_text(html) == "退款截图"


def test_html_to_plain_text_uses_image_placeholder_without_label() -> None:
    html = '<p><img src="https://cdn.example.com/a.png"></p>'

    assert html_to_plain_text(html) == "[image]"


def test_document_display_status_returns_expired_outside_period() -> None:
    document = KnowledgeDocument(
        tenant_id=1,
        directory_id=1,
        title="A",
        content_html="<p>A</p>",
        content_plain="A",
        status="published",
        validity_type="scheduled",
        valid_from=datetime(2026, 1, 1, 0, 0),
        valid_to=datetime(2026, 1, 31, 23, 59),
    )

    assert KnowledgeService.document_display_status(document, datetime(2026, 2, 1, 0, 0)) == "expired"


def test_document_display_status_keeps_draft_inside_period() -> None:
    document = KnowledgeDocument(
        tenant_id=1,
        directory_id=1,
        title="A",
        content_html="<p>A</p>",
        content_plain="A",
        status="draft",
        validity_type="scheduled",
        valid_from=datetime(2026, 1, 1, 0, 0),
        valid_to=datetime(2026, 1, 31, 23, 59),
    )

    assert KnowledgeService.document_display_status(document, datetime(2026, 1, 2, 0, 0)) == "draft"


def test_document_display_status_keeps_draft_outside_period() -> None:
    document = KnowledgeDocument(
        tenant_id=1,
        directory_id=1,
        title="A",
        content_html="<p>A</p>",
        content_plain="A",
        status="draft",
        validity_type="scheduled",
        valid_from=datetime(2026, 1, 1, 0, 0),
        valid_to=datetime(2026, 1, 31, 23, 59),
    )

    assert KnowledgeService.document_display_status(document, datetime(2026, 2, 1, 0, 0)) == "draft"


def test_validate_document_values_rejects_invalid_period() -> None:
    with pytest.raises(ValidationError):
        KnowledgeService._validate_document_values(
            {
                "validity_type": "scheduled",
                "valid_from": datetime(2026, 1, 2),
                "valid_to": datetime(2026, 1, 1),
            }
        )


def test_normalize_inspiration_content_converts_plain_text_to_html() -> None:
    content_html, content_plain = KnowledgeService._normalize_inspiration_content(
        KnowledgeInspirationCreate(content="退款流程\n先核实订单", content_format="text")
    )

    assert content_html == "<p>退款流程</p><p>先核实订单</p>"
    assert content_plain == "退款流程 先核实订单"


def test_normalize_inspiration_content_extracts_rich_text_plain_content() -> None:
    content_html, content_plain = KnowledgeService._normalize_inspiration_content(
        KnowledgeInspirationCreate(content="<p>退款 <strong>订单</strong></p>", content_format="rich_text")
    )

    assert content_html == "<p>退款 <strong>订单</strong></p>"
    assert content_plain == "退款 订单"


def test_normalize_inspiration_content_preserves_html_when_format_is_text() -> None:
    content_html, content_plain = KnowledgeService._normalize_inspiration_content(
        KnowledgeInspirationCreate(content="<p>退款 <strong>订单</strong></p>", content_format="text")
    )

    assert content_html == "<p>退款 <strong>订单</strong></p>"
    assert content_plain == "退款 订单"


@pytest.mark.asyncio
async def test_sync_document_attachments_binds_in_requested_order() -> None:
    document = KnowledgeDocument(
        id=8,
        tenant_id=2,
        directory_id=1,
        title="A",
        content_html="",
        content_plain="",
    )
    first = KnowledgeDocumentAttachment(
        id=11,
        tenant_id=2,
        storage_key="knowledge-attachments/2/first.pdf",
        name="first.pdf",
        size=10,
        mime_type="application/pdf",
        created_by_actor_id=7,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    second = KnowledgeDocumentAttachment(
        id=12,
        tenant_id=2,
        storage_key="knowledge-attachments/2/second.pdf",
        name="second.pdf",
        size=20,
        mime_type="application/pdf",
        created_by_actor_id=7,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db = AsyncMock()

    with (
        patch(
            "app.services.knowledge_service.KnowledgeDocumentAttachmentRepository.list_for_document",
            AsyncMock(return_value=[]),
        ),
        patch(
            "app.services.knowledge_service.KnowledgeDocumentAttachmentRepository.get_by_ids_for_update",
            AsyncMock(return_value=[first, second]),
        ),
    ):
        attachments, removed_keys = await KnowledgeService._sync_document_attachments(
            db,
            tenant_id=2,
            document=document,
            attachment_ids=[12, 11],
            actor_id=7,
        )

    assert [attachment.id for attachment in attachments] == [12, 11]
    assert [attachment.sort_order for attachment in attachments] == [0, 1]
    assert all(attachment.document_id == 8 for attachment in attachments)
    assert all(attachment.expires_at is None for attachment in attachments)
    assert removed_keys == []
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_sync_document_attachments_rejects_another_document_attachment() -> None:
    document = KnowledgeDocument(
        id=8,
        tenant_id=2,
        directory_id=1,
        title="A",
        content_html="",
        content_plain="",
    )
    attachment = KnowledgeDocumentAttachment(
        id=11,
        tenant_id=2,
        document_id=9,
        storage_key="knowledge-attachments/2/first.pdf",
        name="first.pdf",
        size=10,
        mime_type="application/pdf",
    )

    with (
        patch(
            "app.services.knowledge_service.KnowledgeDocumentAttachmentRepository.list_for_document",
            AsyncMock(return_value=[]),
        ),
        patch(
            "app.services.knowledge_service.KnowledgeDocumentAttachmentRepository.get_by_ids_for_update",
            AsyncMock(return_value=[attachment]),
        ),
    ):
        with pytest.raises(ValidationError, match="another document"):
            await KnowledgeService._sync_document_attachments(
                AsyncMock(),
                tenant_id=2,
                document=document,
                attachment_ids=[11],
                actor_id=7,
            )


@pytest.mark.asyncio
async def test_create_document_reloads_attachments_after_commit() -> None:
    document = SimpleNamespace(id=8, directory_id=3)
    db = AsyncMock()
    reload_attachments = AsyncMock(return_value=[sentinel.reloaded_attachment])

    with (
        patch.object(KnowledgeService, "_validate_directory_exists", AsyncMock()),
        patch.object(KnowledgeService, "_actor_create", AsyncMock(return_value={})),
        patch(
            "app.services.knowledge_service.KnowledgeDocumentRepository.get_by_title",
            AsyncMock(return_value=None),
        ),
        patch(
            "app.services.knowledge_service.KnowledgeDocumentRepository.create_pending",
            AsyncMock(return_value=document),
        ),
        patch.object(
            KnowledgeService,
            "_sync_document_attachments",
            AsyncMock(return_value=([sentinel.staged_attachment], [])),
        ),
        patch(
            "app.services.knowledge_service.KnowledgeDocumentAttachmentRepository.list_for_document",
            reload_attachments,
        ),
        patch(
            "app.services.knowledge_service.KnowledgeDirectoryRepository.list_all",
            AsyncMock(return_value=[]),
        ),
        patch.object(
            KnowledgeService,
            "_document_response",
            return_value=sentinel.response,
        ) as build_response,
        patch(
            "app.services.knowledge_recommendation_service.KnowledgeRecommendationService.schedule_document_embedding_refresh"
        ),
    ):
        response = await KnowledgeService.create_document(
            db,
            tenant_id=2,
            data=KnowledgeDocumentCreate(
                title="Attachment article",
                directory_id=3,
                content_html="",
                attachment_ids=[11],
            ),
            actor_id=7,
        )

    reload_attachments.assert_awaited_once_with(db, 2, 8)
    build_response.assert_called_once_with(document, [], [sentinel.reloaded_attachment])
    assert response is sentinel.response


@pytest.mark.asyncio
async def test_update_document_reloads_attachments_after_commit() -> None:
    document = SimpleNamespace(
        id=8,
        tenant_id=2,
        directory_id=3,
        title="Attachment article",
        content_plain="",
        validity_type="permanent",
        valid_from=None,
        valid_to=None,
    )
    db = AsyncMock()
    list_attachments = AsyncMock(
        side_effect=[
            [sentinel.current_attachment],
            [sentinel.first_attachment, sentinel.second_attachment],
        ]
    )

    with (
        patch.object(KnowledgeService, "_validate_directory_exists", AsyncMock()),
        patch.object(KnowledgeService, "_actor_update", AsyncMock(return_value={})),
        patch(
            "app.services.knowledge_service.KnowledgeDocumentRepository.get_by_id",
            AsyncMock(return_value=document),
        ),
        patch(
            "app.services.knowledge_service.KnowledgeDocumentRepository.get_by_title",
            AsyncMock(return_value=None),
        ),
        patch(
            "app.services.knowledge_service.KnowledgeDocumentRepository.update_pending",
            AsyncMock(return_value=document),
        ),
        patch.object(
            KnowledgeService,
            "_sync_document_attachments",
            AsyncMock(return_value=([sentinel.staged_attachment], [])),
        ),
        patch(
            "app.services.knowledge_service.KnowledgeDocumentAttachmentRepository.list_for_document",
            list_attachments,
        ),
        patch(
            "app.services.knowledge_service.KnowledgeDirectoryRepository.list_all",
            AsyncMock(return_value=[]),
        ),
        patch.object(
            KnowledgeService,
            "_document_response",
            return_value=sentinel.response,
        ) as build_response,
        patch(
            "app.services.knowledge_recommendation_service.KnowledgeRecommendationService.schedule_document_embedding_refresh"
        ),
    ):
        response = await KnowledgeService.update_document(
            db,
            tenant_id=2,
            document_id=8,
            data=KnowledgeDocumentUpdate(attachment_ids=[11, 12]),
            actor_id=7,
        )

    assert list_attachments.await_count == 2
    list_attachments.assert_awaited_with(db, 2, 8)
    build_response.assert_called_once_with(
        document,
        [],
        [sentinel.first_attachment, sentinel.second_attachment],
    )
    assert response is sentinel.response


@pytest.mark.asyncio
async def test_archive_inspiration_rejects_non_pending_status() -> None:
    inspiration = KnowledgeInspiration(
        id=1,
        tenant_id=2,
        content_html="<p>退款</p>",
        content_plain="退款",
        status="archived",
    )

    with patch(
        "app.services.knowledge_service.KnowledgeInspirationRepository.get_by_id",
        AsyncMock(return_value=inspiration),
    ):
        with pytest.raises(ValidationError):
            await KnowledgeService.archive_inspiration(AsyncMock(), 2, 1, 7)
