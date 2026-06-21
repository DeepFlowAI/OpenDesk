"""
Unit tests for knowledge import helpers.
"""
from datetime import datetime

import pytest

from app.core.exceptions import ValidationError
from app.services.knowledge_import_service import KnowledgeImportService


def test_parse_id_cell_accepts_excel_integer_text() -> None:
    assert KnowledgeImportService._parse_id_cell("123") == 123
    assert KnowledgeImportService._parse_id_cell("123.0") == 123
    assert KnowledgeImportService._parse_id_cell("abc") is None


def test_text_to_html_escapes_and_keeps_paragraphs() -> None:
    html = KnowledgeImportService._text_to_html("第一段\n<script>alert(1)</script>")

    assert html == "<p>第一段</p><p>&lt;script&gt;alert(1)&lt;/script&gt;</p>"


def test_parse_datetime_cell_accepts_local_text() -> None:
    errors: list[str] = []

    result = KnowledgeImportService._parse_datetime_cell(
        "2026-06-01 09:30",
        None,
        errors,
        keep_existing=False,
    )

    assert result == datetime(2026, 6, 1, 9, 30)
    assert errors == []


def test_validate_headers_rejects_missing_required_column() -> None:
    with pytest.raises(ValidationError):
        KnowledgeImportService._validate_headers(["id", "title", "content_text"])
