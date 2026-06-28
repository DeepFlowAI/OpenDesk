"""
SQLAlchemy type for pgvector columns.
"""
from __future__ import annotations

import math
from collections.abc import Sequence

from sqlalchemy.types import UserDefinedType


def _to_vector_literal(value: Sequence[float]) -> str:
    parts: list[str] = []
    for item in value:
        number = float(item)
        if not math.isfinite(number):
            raise ValueError("Embedding vector contains non-finite values")
        parts.append(f"{number:.8f}")
    return f"[{','.join(parts)}]"


def _parse_vector_literal(value: str) -> list[float]:
    inner = value.strip().strip("[]")
    if not inner:
        return []
    return [float(part) for part in inner.split(",")]


class Vector(UserDefinedType):
    cache_ok = True

    def __init__(self, dimensions: int | None = None) -> None:
        self.dimensions = dimensions

    def get_col_spec(self, **kw) -> str:
        if self.dimensions:
            return f"vector({self.dimensions})"
        return "vector"

    def bind_processor(self, dialect):
        # pgvector accepts its text representation ("[v1,v2,...]"); asyncpg has no
        # native codec for the vector type, so a Python list must be sent as a string.
        def process(value):
            if value is None:
                return None
            if isinstance(value, str):
                return value
            return _to_vector_literal(value)

        return process

    def result_processor(self, dialect, coltype):
        def process(value):
            if value is None:
                return None
            if isinstance(value, str):
                return _parse_vector_literal(value)
            return list(value)

        return process
