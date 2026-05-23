"""Unit tests for reports date-range validation."""
from datetime import date

import pytest
from fastapi import HTTPException

import app.extensions  # triggers private overlay
import importlib

validators = importlib.import_module("app.extensions.reports.lib.validators")
validate_date_range = validators.validate_date_range


class TestValidateDateRange:

    def test_same_day_passes(self):
        validate_date_range(date(2026, 5, 19), date(2026, 5, 19))

    def test_normal_range_passes(self):
        validate_date_range(date(2026, 5, 1), date(2026, 5, 19))

    def test_max_366_days_passes(self):
        validate_date_range(date(2025, 5, 19), date(2026, 5, 18))

    def test_start_after_end_raises_400(self):
        with pytest.raises(HTTPException) as exc:
            validate_date_range(date(2026, 5, 20), date(2026, 5, 19))
        assert exc.value.status_code == 400
        assert "Start date cannot be later than end date" in exc.value.detail

    def test_over_366_days_raises_400(self):
        with pytest.raises(HTTPException) as exc:
            validate_date_range(date(2025, 1, 1), date(2026, 5, 19))
        assert exc.value.status_code == 400
        assert "366" in exc.value.detail
