"""Unit tests for immutable Web SDK form-message submissions."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.configs.settings import settings
from app.core.exceptions import ValidationError
from app.services.conversation_file_service import ConversationFileService
from app.services.channel_form_submission_service import ChannelFormSubmissionService


def _field(
    *,
    field_key: str | None = None,
    field_id: int | None = None,
    name: str,
    field_type: str,
    required: bool = False,
    **definition_overrides,
) -> dict:
    return {
        "field_key": field_key,
        "field_id": field_id,
        "required": required,
        "definition": {
            "name": name,
            "field_type": field_type,
            "type_config": {},
            "options": [],
            "tree_nodes": [],
            **definition_overrides,
        },
    }


def test_build_ticket_uses_system_and_custom_values_and_keeps_snapshot():
    config = {
        "fields": [
            _field(field_key="title", name="主题", field_type="single_line_text", required=True),
            _field(
                field_id=19,
                name="联系邮箱",
                field_type="email",
                required=True,
                help_text="用于回复",
            ),
        ]
    }

    ticket, snapshot = ChannelFormSubmissionService._build_ticket_and_snapshot(
        config,
        {"key:title": "无法登录", "id:19": "visitor@example.com"},
    )

    assert ticket.title == "无法登录"
    assert ticket.custom_fields == {"19": "visitor@example.com"}
    assert snapshot == [
        {
            "field_key": "title",
            "field_id": None,
            "name": "主题",
            "field_type": "single_line_text",
            "required": True,
            "sort_order": 0,
            "value": "无法登录",
            "type_config": {},
            "options": [],
            "tree_nodes": [],
        },
        {
            "field_key": None,
            "field_id": 19,
            "name": "联系邮箱",
            "field_type": "email",
            "required": True,
            "sort_order": 1,
            "value": "visitor@example.com",
            "type_config": {},
            "options": [],
            "tree_nodes": [],
        },
    ]


def test_build_ticket_rejects_missing_required_and_unconfigured_values():
    config = {
        "fields": [
            _field(field_key="description", name="问题描述", field_type="multi_line_text", required=True),
        ]
    }

    with pytest.raises(ValidationError, match="Enter 问题描述"):
        ChannelFormSubmissionService._build_ticket_and_snapshot(config, {})

    with pytest.raises(ValidationError, match="not configured"):
        ChannelFormSubmissionService._build_ticket_and_snapshot(
            config,
            {"key:description": "详情", "key:status": "closed"},
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        (_field(field_id=1, name="邮箱", field_type="email"), "invalid"),
        (_field(field_id=2, name="网址", field_type="url"), "ftp://example.com"),
        (
            _field(
                field_id=3,
                name="类型",
                field_type="single_select",
                options=[{"label": "咨询", "value": "question"}],
            ),
            "unknown",
        ),
    ],
)
def test_build_ticket_rejects_invalid_field_formats(field, value):
    ref = f"id:{field['field_id']}"

    with pytest.raises(ValidationError, match="invalid"):
        ChannelFormSubmissionService._build_ticket_and_snapshot(
            {"fields": [field]},
            {ref: value},
        )


def test_build_ticket_generates_a_title_without_mutating_form_values():
    config = {
        "fields": [
            _field(field_id=7, name="描述", field_type="multi_line_text", required=True),
        ]
    }

    ticket, snapshot = ChannelFormSubmissionService._build_ticket_and_snapshot(
        config,
        {"id:7": "需要帮助"},
    )

    assert ticket.title.startswith("Web SDK 表单留言 ")
    assert snapshot[0]["value"] == "需要帮助"


def test_validate_submission_files_rejects_foreign_storage_keys():
    field = _field(field_id=8, name="附件", field_type="file")
    foreign_key = "form-message-files/7/99/20260804/file.pdf"

    with pytest.raises(ValidationError, match="does not belong"):
        ChannelFormSubmissionService._validate_submission_files(
            {"fields": [field]},
            {
                "id:8": [{
                    "file_id": ConversationFileService.encode_file_id(foreign_key),
                    "url": f"{settings.OSS_ADDR}/{foreign_key}",
                }]
            },
            tenant_id=7,
            channel_id=5,
        )


@pytest.mark.asyncio
async def test_managed_form_file_upload_closes_db_session_before_storage_io():
    field = _field(
        field_id=8,
        name="附件",
        field_type="file",
        type_config={"allowed_mime_types": "pdf", "max_file_size_mb": 2},
    )
    db = AsyncMock()
    session_active = True

    class SessionContext:
        async def __aenter__(self):
            return db

        async def __aexit__(self, *_args):
            nonlocal session_active
            session_active = False

    async def upload(*_args, **_kwargs):
        assert session_active is False
        return f"{settings.OSS_ADDR.rstrip('/')}/uploaded.pdf"

    storage = SimpleNamespace(upload=upload)
    with (
        patch(
            "app.services.channel_form_submission_service.AsyncSessionLocal",
            return_value=SessionContext(),
        ),
        patch(
            "app.services.channel_form_submission_service.ChannelFormConfigVersionRepository.get_by_channel_version",
            AsyncMock(return_value=SimpleNamespace(config={"fields": [field]})),
        ),
        patch(
            "app.services.channel_form_submission_service.ConversationFileService.read_validated_upload",
            AsyncMock(return_value=("proof.pdf", b"pdf", "application/pdf", "pdf")),
        ),
        patch(
            "app.services.channel_form_submission_service.create_storage_client",
            return_value=storage,
        ),
    ):
        result = await ChannelFormSubmissionService.upload_public_file_managed(
            {"tenant_id": 7, "channel_id": 5},
            3,
            "id:8",
            SimpleNamespace(),
        )

    assert result["name"] == "proof.pdf"
