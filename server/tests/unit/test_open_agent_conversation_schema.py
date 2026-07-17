import pytest
from pydantic import ValidationError

from app.schemas.open_agent_conversation import OpenAgentChatRequest


def test_open_agent_chat_accepts_one_attachment_without_text():
    request = OpenAgentChatRequest(
        attachments=[
            {
                "file_id": "file_1",
                "type": "image",
                "name": "demo.png",
                "mime_type": "image/png",
                "size": 10,
            }
        ]
    )

    assert request.message is None
    assert request.attachments[0].file_id == "file_1"


def test_open_agent_chat_rejects_textless_request_without_attachment():
    with pytest.raises(ValidationError):
        OpenAgentChatRequest(message="  ")


def test_open_agent_chat_rejects_multiple_attachments():
    attachment = {
        "file_id": "file_1",
        "type": "file",
        "name": "demo.pdf",
        "mime_type": "application/pdf",
        "size": 10,
    }
    with pytest.raises(ValidationError):
        OpenAgentChatRequest(attachments=[attachment, attachment])
