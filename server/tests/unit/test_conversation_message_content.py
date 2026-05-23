"""
Unit tests for conversation message content validation.
"""
import json

import pytest

from app.core.exceptions import ValidationError
from app.services.conversation_service import ConversationService


def test_validate_text_message_returns_content():
    content = "hello"

    result = ConversationService.validate_message_content("text", content)

    assert result == content


def test_validate_file_message_normalizes_json():
    payload = {
        "schema_version": 1,
        "file_id": "conversation-files/1/2/test.pdf",
        "name": "合同.pdf",
        "size": 1024,
        "mime_type": "application/pdf",
    }

    result = ConversationService.validate_message_content("file", json.dumps(payload))

    assert json.loads(result)["name"] == "合同.pdf"


def test_validate_image_message_requires_image_mime_type():
    payload = {
        "schema_version": 1,
        "file_id": "conversation-files/1/2/test.pdf",
        "name": "合同.pdf",
        "size": 1024,
        "mime_type": "application/pdf",
    }

    with pytest.raises(ValidationError):
        ConversationService.validate_message_content("image", json.dumps(payload))


def test_validate_unsupported_message_type_raises_error():
    with pytest.raises(ValidationError):
        ConversationService.validate_message_content("html", "<b>bad</b>")


def test_validate_welcome_message_type_is_server_only():
    with pytest.raises(ValidationError):
        ConversationService.validate_message_content("welcome", "<p>Hello</p>")


def test_build_welcome_preview_strips_html():
    preview = ConversationService.build_message_preview("welcome", "<p>Hello&nbsp;<strong>there</strong></p>")

    assert preview == "Hello there"


def test_build_file_preview_uses_file_name():
    payload = {
        "schema_version": 1,
        "file_id": "conversation-files/1/2/test.pdf",
        "name": "合同.pdf",
        "size": 1024,
        "mime_type": "application/pdf",
    }

    preview = ConversationService.build_message_preview("file", json.dumps(payload))

    assert preview == "[附件] 合同.pdf"
