"""
Unit tests for TicketCommentService validation rules.

Validation logic does not depend on DB calls before failing, so these tests
exercise the service directly with a sentinel session that should never be
touched on the validation paths.
"""
import pytest

from app.core.exceptions import ValidationError
from app.schemas.ticket_comment import (
    TicketCommentAttachment,
    TicketCommentCreate,
)
from app.services.ticket_comment_service import (
    MAX_ATTACHMENTS_PER_COMMENT,
    MAX_BODY_LENGTH,
    TicketCommentService,
)


class _DummyDB:
    """Sentinel async session — failing validations must short-circuit."""


class TestTicketCommentServiceValidation:

    def test_normalize_body_strips_blank_payloads(self):
        assert TicketCommentService._normalize_body(None) is None
        assert TicketCommentService._normalize_body("") is None
        assert TicketCommentService._normalize_body("   \n\t") is None
        assert TicketCommentService._normalize_body("hi") == "hi"
        assert TicketCommentService._normalize_body("  hi  ") == "hi"

    @pytest.mark.asyncio
    async def test_create_rejects_when_body_and_attachments_both_empty(self, monkeypatch):
        async def _fake_ensure(*_args, **_kwargs):
            return None

        async def _fake_resolve(*_args, **_kwargs):
            return None

        monkeypatch.setattr(TicketCommentService, "_ensure_ticket", _fake_ensure)
        monkeypatch.setattr(TicketCommentService, "_resolve_author_name", _fake_resolve)

        data = TicketCommentCreate(body="   ", attachments=None)

        with pytest.raises(ValidationError):
            await TicketCommentService.create(
                _DummyDB(), tenant_id=1, ticket_id=1, author_id=1, data=data
            )

    @pytest.mark.asyncio
    async def test_create_rejects_when_attachments_exceed_limit(self, monkeypatch):
        async def _fake_ensure(*_args, **_kwargs):
            return None

        async def _fake_resolve(*_args, **_kwargs):
            return None

        monkeypatch.setattr(TicketCommentService, "_ensure_ticket", _fake_ensure)
        monkeypatch.setattr(TicketCommentService, "_resolve_author_name", _fake_resolve)

        attachments = [
            TicketCommentAttachment(url=f"https://x/{i}.bin", name=f"{i}.bin")
            for i in range(MAX_ATTACHMENTS_PER_COMMENT + 1)
        ]
        data = TicketCommentCreate(body=None, attachments=attachments)

        with pytest.raises(ValidationError):
            await TicketCommentService.create(
                _DummyDB(), tenant_id=1, ticket_id=1, author_id=1, data=data
            )

    @pytest.mark.asyncio
    async def test_create_rejects_when_body_exceeds_max_length(self, monkeypatch):
        async def _fake_ensure(*_args, **_kwargs):
            return None

        async def _fake_resolve(*_args, **_kwargs):
            return None

        monkeypatch.setattr(TicketCommentService, "_ensure_ticket", _fake_ensure)
        monkeypatch.setattr(TicketCommentService, "_resolve_author_name", _fake_resolve)

        # Bypass schema's max_length so the service-side guard is the only check.
        data = TicketCommentCreate.model_construct(
            body="x" * (MAX_BODY_LENGTH + 1),
            body_format="html",
            attachments=None,
        )

        with pytest.raises(ValidationError):
            await TicketCommentService.create(
                _DummyDB(), tenant_id=1, ticket_id=1, author_id=1, data=data
            )
