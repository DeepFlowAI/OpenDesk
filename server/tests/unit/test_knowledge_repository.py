"""
Unit tests for knowledge repository helpers.
"""
from datetime import datetime, timezone

from app.models.knowledge import KnowledgeDocument
from app.repositories.knowledge_repository import KnowledgeDocumentRepository


def _document(document_id: int, title: str, content_plain: str, updated_at: datetime) -> KnowledgeDocument:
    document = KnowledgeDocument(
        id=document_id,
        tenant_id=1,
        directory_id=1,
        title=title,
        content_html=f"<p>{content_plain}</p>",
        content_plain=content_plain,
        status="published",
        validity_type="permanent",
    )
    document.updated_at = updated_at
    return document


def test_compute_keyword_score_counts_search_terms() -> None:
    score = KnowledgeDocumentRepository._compute_keyword_score(
        "退款 订单",
        "退款流程 订单核实后退款 订单",
    )

    assert score == 4


def test_sort_by_keyword_score_prefers_more_keyword_hits() -> None:
    low_score = _document(1, "退款流程", "先核实订单", datetime(2026, 1, 3, tzinfo=timezone.utc))
    high_score = _document(2, "退款订单", "订单 订单 退款", datetime(2026, 1, 1, tzinfo=timezone.utc))

    items = KnowledgeDocumentRepository._sort_by_keyword_score([low_score, high_score], "退款 订单")

    assert [item.id for item in items] == [2, 1]


def test_sort_by_keyword_score_uses_updated_at_and_id_as_tiebreakers() -> None:
    older = _document(1, "退款", "订单", datetime(2026, 1, 1, tzinfo=timezone.utc))
    newer_low_id = _document(2, "退款", "订单", datetime(2026, 1, 2, tzinfo=timezone.utc))
    newer_high_id = _document(3, "退款", "订单", datetime(2026, 1, 2, tzinfo=timezone.utc))

    items = KnowledgeDocumentRepository._sort_by_keyword_score([older, newer_low_id, newer_high_id], "退款")

    assert [item.id for item in items] == [3, 2, 1]
