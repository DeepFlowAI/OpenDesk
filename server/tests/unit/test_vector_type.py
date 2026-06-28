"""
Unit tests for the pgvector SQLAlchemy column type.
"""
from __future__ import annotations

import pytest

from app.models.vector import Vector


class TestVectorBindProcessor:
    def test_list_is_serialized_to_pgvector_literal(self) -> None:
        process = Vector(3).bind_processor(dialect=None)

        assert process([0.1, -0.2, 0.3]) == "[0.10000000,-0.20000000,0.30000000]"

    def test_none_stays_none(self) -> None:
        process = Vector(3).bind_processor(dialect=None)

        assert process(None) is None

    def test_string_passes_through(self) -> None:
        process = Vector(3).bind_processor(dialect=None)

        assert process("[1,2,3]") == "[1,2,3]"

    def test_non_finite_values_are_rejected(self) -> None:
        process = Vector(3).bind_processor(dialect=None)

        with pytest.raises(ValueError):
            process([0.1, float("nan"), 0.3])


class TestVectorResultProcessor:
    def test_literal_is_parsed_to_float_list(self) -> None:
        process = Vector(3).result_processor(dialect=None, coltype=None)

        assert process("[0.1,-0.2,0.3]") == [0.1, -0.2, 0.3]

    def test_none_stays_none(self) -> None:
        process = Vector(3).result_processor(dialect=None, coltype=None)

        assert process(None) is None

    def test_empty_literal_is_empty_list(self) -> None:
        process = Vector(3).result_processor(dialect=None, coltype=None)

        assert process("[]") == []
