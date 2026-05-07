"""
Unit tests for conversation file service helpers.
"""
import pytest

from app.core.exceptions import ValidationError
from app.services.conversation_file_service import ConversationFileService


def test_file_id_round_trip_returns_original_key():
    key = "conversation-files/1/2/20260501/demo.pdf"

    file_id = ConversationFileService.encode_file_id(key)
    decoded = ConversationFileService.decode_file_id(file_id)

    assert decoded == key


def test_decode_invalid_file_id_raises_validation_error():
    with pytest.raises(ValidationError):
        ConversationFileService.decode_file_id("%%%")


def test_safe_download_name_strips_header_breaking_characters():
    safe_name = ConversationFileService._safe_download_name('bad"\r\nname.pdf')

    assert '"' not in safe_name
    assert "\r" not in safe_name
    assert "\n" not in safe_name


def test_validate_image_magic_number_rejects_mismatch():
    with pytest.raises(ValidationError):
        ConversationFileService._validate_magic_number("image/png", b"not-a-png")
