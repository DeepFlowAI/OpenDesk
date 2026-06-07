"""add session routing multi queue

Revision ID: 0f1e2d3c4b5a
Revises: f0a1b2c3d4e5
Create Date: 2026-05-30
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "0f1e2d3c4b5a"
down_revision: Union[str, None] = "f0a1b2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "session_routing_rules",
        sa.Column(
            "target_strategy",
            sa.String(length=32),
            nullable=False,
            server_default="sequential_overflow",
        ),
    )
    op.add_column(
        "session_routing_rules",
        sa.Column("target_queue_sources", JSONB, nullable=False, server_default="[]"),
    )
    op.alter_column("session_routing_rules", "target_group_id", nullable=True)
    op.execute(
        """
        UPDATE session_routing_rules
        SET target_queue_sources = jsonb_build_array(
            jsonb_build_object(
                'source_type', 'employee_group',
                'target_ids', jsonb_build_array(target_group_id)
            )
        )
        WHERE target_group_id IS NOT NULL
          AND target_queue_sources = '[]'::jsonb
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE session_routing_rules
        SET target_group_id = (
            SELECT (source->'target_ids'->>0)::integer
            FROM jsonb_array_elements(target_queue_sources) AS source
            WHERE source->>'source_type' = 'employee_group'
              AND jsonb_array_length(source->'target_ids') > 0
            LIMIT 1
        )
        WHERE target_group_id IS NULL
        """
    )
    op.alter_column("session_routing_rules", "target_group_id", nullable=False)
    op.drop_column("session_routing_rules", "target_queue_sources")
    op.drop_column("session_routing_rules", "target_strategy")
