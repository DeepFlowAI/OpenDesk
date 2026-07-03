"""add inbound routing rule multi-target

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-06-29 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "f2a3b4c5d6e7"
down_revision: Union[str, Sequence[str], None] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "inbound_routing_rules",
        sa.Column("target_type", sa.String(length=32), nullable=False, server_default="voice_flow"),
    )
    op.add_column(
        "inbound_routing_rules",
        sa.Column("voicespeed_agent_id", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "inbound_routing_rules",
        sa.Column("voicespeed_agent_name", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "inbound_routing_rules",
        sa.Column("transfer_target", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    # Backfill existing rows (also covered by the server_default above).
    op.execute(
        "UPDATE inbound_routing_rules SET target_type = 'voice_flow' WHERE target_type IS NULL"
    )

    # Relax the voice-flow target NOT NULL so VoiceSpeed-targeted rules are allowed.
    op.alter_column(
        "inbound_routing_rules",
        "target_voice_flow_id",
        existing_type=sa.Integer(),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "inbound_routing_rules",
        "target_voice_flow_id",
        existing_type=sa.Integer(),
        nullable=False,
    )
    op.drop_column("inbound_routing_rules", "transfer_target")
    op.drop_column("inbound_routing_rules", "voicespeed_agent_name")
    op.drop_column("inbound_routing_rules", "voicespeed_agent_id")
    op.drop_column("inbound_routing_rules", "target_type")
