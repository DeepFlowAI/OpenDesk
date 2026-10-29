"""Unit tests for online quality scorecard validation."""
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import inspect
from sqlalchemy.orm.attributes import NO_VALUE

from app.core.exceptions import ValidationError
from app.repositories.quality_scorecard_repository import (
    QualityScorecardRepository,
    build_sections,
)
from app.schemas.quality_scorecard import (
    QualityScorecardCreate,
    QualityScorecardCriterionInput,
    QualityScorecardSectionInput,
)
from app.services.quality_scorecard_service import QualityScorecardService


def _option(
    name: str,
    points: str,
    severity: str = "normal",
) -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        description=f"{name} description",
        points=Decimal(points),
        severity=severity,
    )


def _criterion(
    *,
    max_points: str = "10",
    evidence_policy: str = "issue_only",
    options: list[SimpleNamespace] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        name="Service quality",
        rubric="The agent must provide an observable and accurate response.",
        max_points=Decimal(max_points),
        evidence_policy=evidence_policy,
        options=options
        or [
            _option("Meets", max_points, "normal"),
            _option("Does not meet", "0", "issue"),
        ],
    )


def _sections(criterion: SimpleNamespace) -> list[SimpleNamespace]:
    return [SimpleNamespace(name="Service", criteria=[criterion])]


def test_validate_for_publish_accepts_scored_criterion() -> None:
    QualityScorecardService.validate_for_publish(
        _sections(_criterion()), Decimal("80")
    )


def test_create_schema_accepts_incomplete_criterion_in_draft() -> None:
    draft = QualityScorecardCreate.model_validate(
        {
            "name": "Support quality",
            "sections": [
                {
                    "name": "Service",
                    "criteria": [
                        {
                            "name": "",
                            "rubric": "",
                            "max_points": 10,
                            "is_required": True,
                            "evidence_policy": "issue_only",
                            "options": [
                                {
                                    "name": "Meets",
                                    "description": "",
                                    "points": 10,
                                    "severity": "normal",
                                },
                                {
                                    "name": "Does not meet",
                                    "description": "",
                                    "points": 0,
                                    "severity": "issue",
                                },
                            ],
                        }
                    ],
                }
            ],
        }
    )

    assert draft.sections is not None
    assert draft.sections[0].criteria[0].rubric == ""


def test_build_sections_initializes_empty_draft_relationships() -> None:
    empty_section = build_sections([QualityScorecardSectionInput(name="Service")])[0]
    sections = build_sections(
        [
            QualityScorecardSectionInput(
                name="Service",
                criteria=[
                    QualityScorecardCriterionInput(
                        name="",
                        rubric="",
                        max_points=Decimal("10"),
                    )
                ],
            )
        ]
    )

    assert inspect(empty_section).attrs.criteria.loaded_value is not NO_VALUE
    assert inspect(sections[0]).attrs.criteria.loaded_value is not NO_VALUE
    assert inspect(sections[0].criteria[0]).attrs.options.loaded_value is not NO_VALUE


@pytest.mark.asyncio
async def test_save_reloads_scorecard_after_commit(monkeypatch) -> None:
    db = MagicMock()
    db.commit = AsyncMock()
    scorecard = SimpleNamespace(id=3, tenant_id=1)
    reloaded = SimpleNamespace(id=3, tenant_id=1, updated_at="fresh")

    async def fake_get_by_id(_db, tenant_id: int, scorecard_id: int):
        assert _db is db
        assert tenant_id == 1
        assert scorecard_id == 3
        return reloaded

    monkeypatch.setattr(QualityScorecardRepository, "get_by_id", fake_get_by_id)

    result = await QualityScorecardRepository.save(db, scorecard)

    db.add.assert_called_once_with(scorecard)
    db.commit.assert_awaited_once()
    assert result is reloaded


def test_validate_for_publish_requires_at_least_one_criterion() -> None:
    with pytest.raises(ValidationError, match="Add at least one criterion"):
        QualityScorecardService.validate_for_publish([], Decimal("80"))


def test_validate_for_publish_rejects_incomplete_criterion() -> None:
    criterion = _criterion()
    criterion.rubric = ""
    with pytest.raises(ValidationError, match="at least 10 characters"):
        QualityScorecardService.validate_for_publish(
            _sections(criterion), Decimal("80")
        )


def test_validate_for_publish_rejects_incomplete_option() -> None:
    criterion = _criterion()
    criterion.options[0].description = ""
    with pytest.raises(ValidationError, match="option names and descriptions"):
        QualityScorecardService.validate_for_publish(
            _sections(criterion), Decimal("80")
        )


def test_validate_for_publish_rejects_observation_points() -> None:
    criterion = _criterion(
        max_points="0",
        options=[_option("No issue", "0", "normal"), _option("Issue", "1", "issue")],
    )
    with pytest.raises(ValidationError, match="zero points"):
        QualityScorecardService.validate_for_publish(_sections(criterion), None)


def test_validate_for_publish_rejects_fatal_without_evidence() -> None:
    criterion = _criterion(
        evidence_policy="none",
        options=[_option("Meets", "10", "normal"), _option("Fatal", "0", "fatal")],
    )
    with pytest.raises(ValidationError, match="must require evidence"):
        QualityScorecardService.validate_for_publish(
            _sections(criterion), Decimal("80")
        )


def test_validate_for_publish_requires_normal_option() -> None:
    criterion = _criterion(
        options=[_option("Notice", "5", "notice"), _option("Issue", "0", "issue")]
    )
    with pytest.raises(ValidationError, match="normal option"):
        QualityScorecardService.validate_for_publish(
            _sections(criterion), Decimal("80")
        )
