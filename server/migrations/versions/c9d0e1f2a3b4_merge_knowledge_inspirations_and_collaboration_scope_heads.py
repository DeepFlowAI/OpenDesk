"""merge knowledge inspirations and collaboration scope heads

Revision ID: c9d0e1f2a3b4
Revises: b2c4d6e8f0a2, d6e7f8a9b0c2
Create Date: 2026-07-04
"""
from typing import Sequence, Union


revision: str = "c9d0e1f2a3b4"
down_revision: Union[str, Sequence[str], None] = (
    "b2c4d6e8f0a2",
    "d6e7f8a9b0c2",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
