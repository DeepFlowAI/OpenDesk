"""add voice speed settings

Revision ID: 9b2c3d4e5f6a
Revises: 8a1c2e3f4b5d
Create Date: 2026-06-26
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "9b2c3d4e5f6a"
down_revision: Union[str, Sequence[str], None] = "8a1c2e3f4b5d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("open_agent_settings", "base_url", existing_type=sa.String(length=512), nullable=True)
    op.alter_column("open_agent_settings", "api_key_ciphertext", existing_type=sa.Text(), nullable=True)
    op.add_column("open_agent_settings", sa.Column("voice_speed_base_url", sa.String(length=512), nullable=True))
    op.add_column("open_agent_settings", sa.Column("voice_speed_api_key_ciphertext", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("open_agent_settings", "voice_speed_api_key_ciphertext")
    op.drop_column("open_agent_settings", "voice_speed_base_url")
    op.alter_column("open_agent_settings", "api_key_ciphertext", existing_type=sa.Text(), nullable=False)
    op.alter_column("open_agent_settings", "base_url", existing_type=sa.String(length=512), nullable=False)
