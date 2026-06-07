"""seed assign queue system variables

Revision ID: 1a2b3c4d5e6f
Revises: 0f1e2d3c4b5a
Create Date: 2026-05-30
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "1a2b3c4d5e6f"
down_revision: Union[str, None] = "0f1e2d3c4b5a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SYS_VARS = [
    (
        "sys.assign_queue_status",
        "分配队列状态",
        "Assign Queue Status",
        "text",
        "最近一次分配队列节点的失败状态，可用于 timeout 出口后的信息判定",
        "Failure status from the latest assign queue node for timeout-branch conditions",
        40,
    ),
    (
        "sys.assign_queue_limit_reason",
        "分配队列上限原因",
        "Assign Queue Limit Reason",
        "text",
        "达到排队上限时的原因：max_waiting_count、max_wait_seconds 或 mixed_limit",
        "Queue limit reason: max_waiting_count, max_wait_seconds, or mixed_limit",
        50,
    ),
]


def upgrade() -> None:
    for row in SYS_VARS:
        op.execute(
            sa.text(
                """
                INSERT INTO voice_flow_system_variables
                    (name, display_name_zh, display_name_en, value_type,
                     description_zh, description_en, sort_order)
                VALUES (:n, :nzh, :nen, :vt, :dzh, :den, :so)
                ON CONFLICT (name) DO UPDATE SET
                    display_name_zh = EXCLUDED.display_name_zh,
                    display_name_en = EXCLUDED.display_name_en,
                    value_type      = EXCLUDED.value_type,
                    description_zh  = EXCLUDED.description_zh,
                    description_en  = EXCLUDED.description_en,
                    sort_order      = EXCLUDED.sort_order
                """
            ).bindparams(
                n=row[0],
                nzh=row[1],
                nen=row[2],
                vt=row[3],
                dzh=row[4],
                den=row[5],
                so=row[6],
            )
        )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM voice_flow_system_variables
        WHERE name IN ('sys.assign_queue_status', 'sys.assign_queue_limit_reason')
        """
    )
