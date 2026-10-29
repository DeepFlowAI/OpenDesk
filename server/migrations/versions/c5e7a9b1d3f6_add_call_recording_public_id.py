"""add call recording public id

Revision ID: c5e7a9b1d3f6
Revises: c5e7a9b1d3f5
Create Date: 2026-10-22

Additive: a nullable public UUID for call recordings. New rows get it from the
column default; existing rows are backfilled in small committed batches and the
unique index is built concurrently, so the table is never rewritten or locked
for long.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c5e7a9b1d3f6"
down_revision: Union[str, Sequence[str], None] = "c5e7a9b1d3f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

BACKFILL_BATCH_SIZE = 5000
INDEX_NAME = "uq_call_recordings_public_id"


def upgrade() -> None:
    op.add_column(
        "call_recordings",
        sa.Column("public_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.execute(
        "ALTER TABLE call_recordings ALTER COLUMN public_id SET DEFAULT gen_random_uuid()"
    )

    with op.get_context().autocommit_block():
        bind = op.get_bind()
        while True:
            result = bind.execute(
                sa.text(
                    """
                    UPDATE call_recordings
                    SET public_id = gen_random_uuid()
                    WHERE id IN (
                        SELECT id FROM call_recordings
                        WHERE public_id IS NULL
                        LIMIT :batch
                    )
                    """
                ),
                {"batch": BACKFILL_BATCH_SIZE},
            )
            if not result.rowcount:
                break

    with op.get_context().autocommit_block():
        op.create_index(
            INDEX_NAME,
            "call_recordings",
            ["public_id"],
            unique=True,
            postgresql_concurrently=True,
            if_not_exists=True,
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.drop_index(
            INDEX_NAME,
            table_name="call_recordings",
            postgresql_concurrently=True,
            if_exists=True,
        )
    op.drop_column("call_recordings", "public_id")
