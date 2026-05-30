"""call-center runtime: agent_status + call_records + agent_webrtc_sessions

Revision ID: 6b2d3e4f5a6c
Revises: 5a1c2d3e4f5b
Create Date: 2026-05-25
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "6b2d3e4f5a6c"
down_revision: Union[str, None] = "5a1c2d3e4f5b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── agent_status ──
    op.create_table(
        "agent_status",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer, nullable=False),
        sa.Column("employee_id", sa.Integer, nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("reason", sa.String(120), nullable=True),
        sa.Column("status_changed_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("tenant_id", "employee_id", name="uq_agent_status_tenant_employee"),
    )
    op.create_index(
        "ix_agent_status_tenant_status",
        "agent_status",
        ["tenant_id", "status"],
        unique=False,
    )

    # ── call_records ──
    op.create_table(
        "call_records",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer, nullable=False),
        sa.Column("call_id", sa.String(80), nullable=False),
        sa.Column("conversation_id", sa.String(80), nullable=True),
        sa.Column("root_call_id", sa.String(80), nullable=True),
        sa.Column("direction", sa.String(16), nullable=False),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("from_number", sa.String(64), nullable=True),
        sa.Column("to_number", sa.String(64), nullable=True),
        sa.Column("voice_flow_id", sa.Integer, nullable=True),
        sa.Column("voice_flow_version_id", sa.Integer, nullable=True),
        sa.Column("employee_group_id", sa.Integer, nullable=True),
        sa.Column("agent_id", sa.Integer, nullable=True),
        sa.Column("started_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("answered_at", sa.DateTime, nullable=True),
        sa.Column("ended_at", sa.DateTime, nullable=True),
        sa.Column("ring_duration_ms", sa.Integer, nullable=True),
        sa.Column("talk_duration_ms", sa.Integer, nullable=True),
        sa.Column("hangup_reason", sa.String(80), nullable=True),
        sa.Column("recording_url", sa.String(500), nullable=True),
        sa.Column("recording_duration_ms", sa.Integer, nullable=True),
        sa.Column("extra_metadata", JSONB, server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["voice_flow_id"], ["voice_flows.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["voice_flow_version_id"], ["voice_flow_versions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["employee_group_id"], ["employee_groups.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["agent_id"], ["employees.id"], ondelete="SET NULL"),
    )
    op.create_index("uq_cr_call_id", "call_records", ["call_id"], unique=True)
    op.create_index("ix_cr_tenant_started", "call_records", ["tenant_id", "started_at"])
    op.create_index("ix_cr_tenant_agent", "call_records", ["tenant_id", "agent_id"])
    op.create_index("ix_cr_tenant_state", "call_records", ["tenant_id", "state"])
    op.create_index("ix_cr_conversation", "call_records", ["conversation_id"])

    # ── agent_webrtc_sessions ──
    op.create_table(
        "agent_webrtc_sessions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer, nullable=False),
        sa.Column("employee_id", sa.Integer, nullable=False),
        sa.Column("webrtc_call_id", sa.String(80), nullable=False),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("started_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("ended_at", sa.DateTime, nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_aws_tenant_employee_state",
        "agent_webrtc_sessions",
        ["tenant_id", "employee_id", "state"],
        unique=False,
    )
    op.create_index(
        "uq_aws_active_per_employee",
        "agent_webrtc_sessions",
        ["tenant_id", "employee_id"],
        unique=True,
        postgresql_where=sa.text("state <> 'disconnected'"),
    )


def downgrade() -> None:
    op.drop_index("uq_aws_active_per_employee", table_name="agent_webrtc_sessions")
    op.drop_index("ix_aws_tenant_employee_state", table_name="agent_webrtc_sessions")
    op.drop_table("agent_webrtc_sessions")

    op.drop_index("ix_cr_conversation", table_name="call_records")
    op.drop_index("ix_cr_tenant_state", table_name="call_records")
    op.drop_index("ix_cr_tenant_agent", table_name="call_records")
    op.drop_index("ix_cr_tenant_started", table_name="call_records")
    op.drop_index("uq_cr_call_id", table_name="call_records")
    op.drop_table("call_records")

    op.drop_index("ix_agent_status_tenant_status", table_name="agent_status")
    op.drop_table("agent_status")
