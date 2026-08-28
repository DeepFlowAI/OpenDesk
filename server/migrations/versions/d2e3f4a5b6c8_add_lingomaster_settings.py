"""add lingomaster settings

Revision ID: d2e3f4a5b6c8
Revises: c1d2e3f4a5b7
Create Date: 2026-08-04 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.constants.lingomaster import DEFAULT_AGENT_TRANSLATION_PROMPT, DEFAULT_VISITOR_TRANSLATION_PROMPT


revision: str = "d2e3f4a5b6c8"
down_revision: Union[str, None] = "c1d2e3f4a5b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "system_settings",
        sa.Column("lingomaster_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "system_settings",
        sa.Column("lingomaster_visitor_prompt", sa.Text(), server_default=DEFAULT_VISITOR_TRANSLATION_PROMPT, nullable=False),
    )
    op.add_column(
        "system_settings",
        sa.Column("lingomaster_agent_prompt", sa.Text(), server_default=DEFAULT_AGENT_TRANSLATION_PROMPT, nullable=False),
    )


def downgrade() -> None:
    op.drop_column("system_settings", "lingomaster_agent_prompt")
    op.drop_column("system_settings", "lingomaster_visitor_prompt")
    op.drop_column("system_settings", "lingomaster_enabled")
