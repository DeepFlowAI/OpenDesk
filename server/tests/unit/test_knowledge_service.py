"""
Unit tests for knowledge service helpers.
"""
from datetime import datetime

import pytest

from app.core.exceptions import ValidationError
from app.models.knowledge import KnowledgeDocument
from app.services.knowledge_service import KnowledgeService, html_to_plain_text


def test_html_to_plain_text_strips_tags_and_collapses_whitespace() -> None:
    html = "<h2>退款</h2><p>  先核实&nbsp;订单 </p><script>alert(1)</script>"

    assert html_to_plain_text(html) == "退款 先核实 订单 alert(1)"


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
