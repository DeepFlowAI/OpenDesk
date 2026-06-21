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


def test_validate_internal_note_returns_content():
    content = "handoff context"

    result = ConversationService.validate_message_content("internal_note", content)

    assert result == content


def test_validate_rich_text_sanitizes_dangerous_markup():
    content = '<p onclick="alert(1)">Hello <strong>there</strong></p><script>alert(1)</script>'

    result = ConversationService.validate_message_content("rich_text", content)

    assert "script" not in result
    assert "onclick" not in result
    assert "<strong>there</strong>" in result


def test_validate_rich_text_allows_image_only_content():
    content = '<p></p><img data-file-id="conversation-files/1/2/a.png" alt="a">'

    result = ConversationService.validate_message_content("rich_text", content)

    assert "data-file-id" in result


def test_validate_empty_rich_text_raises_error():
    with pytest.raises(ValidationError):
        ConversationService.validate_message_content("rich_text", "<p><br></p>")


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


def test_build_internal_note_preview_adds_internal_prefix():
    preview = ConversationService.build_message_preview("internal_note", "请稍后跟进")

    assert preview == "[内部] 请稍后跟进"


def test_build_rich_text_preview_strips_html():
    preview = ConversationService.build_message_preview("rich_text", "<p>Hello&nbsp;<strong>there</strong></p>")

    assert preview == "Hello there"


def test_build_rich_text_preview_uses_image_placeholder():
    preview = ConversationService.build_message_preview("rich_text", '<img data-file-id="x">')

    assert preview == "[图片]"


def test_visitor_environment_data_trims_and_limits_values():
    data = ConversationService._visitor_environment_data(
        visitor_system=" macOS 15.5 ",
        visitor_browser=" Chrome " + "1" * 200,
        visitor_ip=" 203.0.113.42 ",
    )

    assert data["visitor_system"] == "macOS 15.5"
    assert data["visitor_browser"] == ("Chrome " + "1" * 121)
    assert data["visitor_ip"] == "203.0.113.42"


def test_visitor_environment_data_ignores_empty_values():
    data = ConversationService._visitor_environment_data(
        visitor_system=" ",
        visitor_browser=None,
        visitor_ip="",
    )

    assert data == {}
