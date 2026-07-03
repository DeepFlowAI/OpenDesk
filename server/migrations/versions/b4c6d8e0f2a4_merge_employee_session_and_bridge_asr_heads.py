"""merge employee session and bridge ASR heads

Revision ID: b4c6d8e0f2a4
Revises: a3b5c7d9e1f2, a3c5e7f9b1d4
Create Date: 2026-06-30
"""
from typing import Sequence, Union


revision: str = "b4c6d8e0f2a4"
down_revision: Union[str, Sequence[str], None] = (
    "a3b5c7d9e1f2",
    "a3c5e7f9b1d4",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
