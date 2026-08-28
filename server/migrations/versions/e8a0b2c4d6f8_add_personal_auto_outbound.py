"""add personal auto outbound

Revision ID: e8a0b2c4d6f8
Revises: d7f9a1b3c5e7
Create Date: 2026-08-12 16:00:00.000000
"""
from __future__ import annotations

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e8a0b2c4d6f8"
down_revision: Union[str, Sequence[str], None] = "d7f9a1b3c5e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PERMISSION = "call.personal_auto_outbound.use"


def _permission_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        loaded = json.loads(value)
        return [str(item) for item in loaded] if isinstance(loaded, list) else []
    return [str(item) for item in value] if isinstance(value, list) else []


def _update_system_role_permissions(add: bool) -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, permissions FROM roles WHERE key IN ('admin', 'agent') AND is_system = true")
    ).mappings()
    for row in rows:
        permissions = set(_permission_list(row["permissions"]))
        permissions.add(PERMISSION) if add else permissions.discard(PERMISSION)
        bind.execute(
            sa.text(
                "UPDATE roles SET permissions = CAST(:permissions AS JSON), updated_at = now() WHERE id = :role_id"
            ),
            {"role_id": row["id"], "permissions": json.dumps(sorted(permissions))},
        )


def upgrade() -> None:
    op.create_table(
        "personal_outbound_recordings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("recording_type", sa.String(length=16), nullable=False),
        sa.Column("audio_asset_id", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("recording_type IN ('opening', 'closing')", name="ck_personal_outbound_recording_type"),
        sa.ForeignKeyConstraint(["audio_asset_id"], ["audio_assets.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "employee_id", "recording_type", name="uq_personal_outbound_recording_owner_type"),
    )
    op.create_index("ix_personal_outbound_recordings_owner", "personal_outbound_recordings", ["tenant_id", "employee_id"])

    op.create_table(
        "personal_auto_outbound_sessions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("primary_agent_id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("outbound_phone_number_id", sa.String(length=32), nullable=False),
        sa.Column("fallback_group_id", sa.Integer(), nullable=True),
        sa.Column("opening_audio_asset_id", sa.Integer(), nullable=False),
        sa.Column("closing_audio_asset_id", sa.Integer(), nullable=False),
        sa.Column("configured_concurrency", sa.Integer(), server_default="4", nullable=False),
        sa.Column("effective_concurrency", sa.Integer(), server_default="1", nullable=False),
        sa.Column("status", sa.String(length=24), server_default="running", nullable=False),
        sa.Column("pause_reason", sa.String(length=80), nullable=True),
        sa.Column("intent_snapshot", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stopping_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("configured_concurrency BETWEEN 1 AND 10", name="ck_personal_auto_outbound_configured_concurrency"),
        sa.CheckConstraint("effective_concurrency BETWEEN 1 AND 10", name="ck_personal_auto_outbound_effective_concurrency"),
        sa.ForeignKeyConstraint(["closing_audio_asset_id"], ["audio_assets.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["fallback_group_id"], ["employee_groups.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["opening_audio_asset_id"], ["audio_assets.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["outbound_phone_number_id"], ["phone_numbers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["primary_agent_id"], ["employees.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["task_id"], ["outbound_tasks.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_personal_auto_outbound_sessions_owner", "personal_auto_outbound_sessions", ["tenant_id", "primary_agent_id", "created_at"])
    op.create_index("ix_personal_auto_outbound_sessions_status", "personal_auto_outbound_sessions", ["tenant_id", "status"])
    op.create_index(
        "uq_personal_auto_outbound_active_owner",
        "personal_auto_outbound_sessions",
        ["tenant_id", "primary_agent_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('running', 'paused', 'auto_paused', 'stopping')"),
    )

    op.create_table(
        "personal_auto_outbound_calls",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=False),
        sa.Column("call_record_id", sa.BigInteger(), nullable=True),
        sa.Column("telephony_call_id", sa.String(length=80), nullable=True),
        sa.Column("phone_number", sa.String(length=64), nullable=False),
        sa.Column("stage", sa.String(length=24), server_default="pending", nullable=False),
        sa.Column("prescreen_result", sa.String(length=40), nullable=True),
        sa.Column("intent_key", sa.String(length=64), nullable=True),
        sa.Column("similarity", sa.Float(), nullable=True),
        sa.Column("degraded_reason", sa.String(length=80), nullable=True),
        sa.Column("assigned_agent_id", sa.Integer(), nullable=True),
        sa.Column("assignment_type", sa.String(length=16), nullable=True),
        sa.Column("hangup_reason", sa.String(length=80), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["assigned_agent_id"], ["employees.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["call_record_id"], ["call_records.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["session_id"], ["personal_auto_outbound_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_id"], ["outbound_task_targets.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["task_id"], ["outbound_tasks.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "target_id", name="uq_personal_auto_outbound_call_target"),
    )
    op.create_index("ix_personal_auto_outbound_calls_call_id", "personal_auto_outbound_calls", ["tenant_id", "telephony_call_id"])
    op.create_index("ix_personal_auto_outbound_calls_session_stage", "personal_auto_outbound_calls", ["session_id", "stage"])
    _update_system_role_permissions(True)


def downgrade() -> None:
    _update_system_role_permissions(False)
    op.drop_table("personal_auto_outbound_calls")
    op.drop_table("personal_auto_outbound_sessions")
    op.drop_table("personal_outbound_recordings")
