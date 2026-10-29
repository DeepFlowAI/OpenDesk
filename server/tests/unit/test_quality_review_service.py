from types import SimpleNamespace

import pytest
from sqlalchemy import inspect
from sqlalchemy.orm.attributes import NO_VALUE

from app.core.exceptions import ValidationError
from app.models.quality import QualityHumanReviewDraft
from app.services.quality_review_service import QualityReviewService


def source_item(*, result_type="option", option_id=1, policy="issue_only", required=True):
    return SimpleNamespace(
        id=10,
        result_type=result_type,
        option_id=option_id,
        criterion_snapshot={
            "is_required": required,
            "max_points": "10",
            "evidence_policy": policy,
            "options": [
                {"id": 1, "points": "10", "severity": "normal"},
                {"id": 2, "points": "0", "severity": "issue"},
                {"id": 3, "points": "0", "severity": "fatal"},
            ],
        },
    )


def human_item(*, option_id=1, evidence=None, judgment=None, change_reason=None):
    return SimpleNamespace(
        review_item_id=10,
        result_type="option",
        option_id=option_id,
        evidence_message_ids=evidence or [],
        judgment=judgment,
        change_reason=change_reason,
    )


def review_and_draft(source, human):
    return (
        SimpleNamespace(items=[source], conversation_snapshot={"pass_score": "80"}),
        SimpleNamespace(items=[human]),
    )


def test_human_normal_result_scores_and_passes():
    review, draft = review_and_draft(source_item(), human_item())
    score, outcome, issue_count = QualityReviewService._validate_and_score(review, draft)
    assert str(score) == "100.0"
    assert outcome == "passed"
    assert issue_count == 0


def test_changed_ai_option_requires_explanation():
    review, draft = review_and_draft(
        source_item(), human_item(option_id=2, evidence=[100])
    )
    with pytest.raises(ValidationError, match="Explain why"):
        QualityReviewService._validate_and_score(review, draft)


def test_issue_option_requires_evidence():
    review, draft = review_and_draft(
        source_item(result_type=None, option_id=None),
        human_item(option_id=2, change_reason="人工判断存在一般问题"),
    )
    with pytest.raises(ValidationError, match="evidence"):
        QualityReviewService._validate_and_score(review, draft)


def test_fatal_option_requires_detailed_judgment():
    review, draft = review_and_draft(
        source_item(result_type=None, option_id=None),
        human_item(
            option_id=3,
            evidence=[100],
            judgment="太短",
            change_reason="人工核对后改为致命问题",
        ),
    )
    with pytest.raises(ValidationError, match="detailed judgment"):
        QualityReviewService._validate_and_score(review, draft)


def test_new_human_draft_initializes_empty_items() -> None:
    draft = QualityHumanReviewDraft(review_id=1, items=[])
    assert inspect(draft).attrs["items"].loaded_value is not NO_VALUE
