"""add provider_biz_id index on sms_bulk_targets

Delivery receipts look up targets by provider_biz_id; without an index the
lookup degrades as a task's target count grows.

Revision ID: e7f8a9b0c1d2
Revises: c5d6e7f8a9b0
Create Date: 2026-08-08 09:30:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "e7f8a9b0c1d2"
down_revision: Union[str, Sequence[str], None] = "c5d6e7f8a9b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_sms_bulk_targets_provider_biz_id",
        "sms_bulk_targets",
        ["provider_biz_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_sms_bulk_targets_provider_biz_id", table_name="sms_bulk_targets")
