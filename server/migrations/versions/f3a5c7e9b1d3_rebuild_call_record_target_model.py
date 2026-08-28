"""rebuild call record target model

Revision ID: f3a5c7e9b1d3
Revises: f2a4c6e8b0d2
Create Date: 2026-08-09
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "f3a5c7e9b1d3"
down_revision: Union[str, None] = "f2a4c6e8b0d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# migration-safety: contract-approved
# This maintenance-window cutover intentionally rebuilds the empty CDR model.


_DEPENDENT_FOREIGN_KEYS = (
    ("call_events", "call_events_call_record_id_fkey", "CASCADE"),
    (
        "call_summary_field_values",
        "call_summary_field_values_call_record_id_fkey",
        "CASCADE",
    ),
    ("tickets", "fk_tickets_call_record_id_call_records", "SET NULL"),
    (
        "outbound_call_records",
        "outbound_call_records_call_record_id_fkey",
        "SET NULL",
    ),
    (
        "auto_outbound_call_records",
        "auto_outbound_call_records_call_record_id_fkey",
        "SET NULL",
    ),
    ("sms_send_records", "sms_send_records_call_record_id_fkey", "SET NULL"),
)


def _drop_dependent_foreign_keys() -> None:
    for table_name, constraint_name, _ondelete in _DEPENDENT_FOREIGN_KEYS:
        op.drop_constraint(constraint_name, table_name, type_="foreignkey")


def _create_dependent_foreign_keys() -> None:
    for table_name, constraint_name, ondelete in _DEPENDENT_FOREIGN_KEYS:
        op.create_foreign_key(
            constraint_name,
            table_name,
            "call_records",
            ["call_record_id"],
            ["id"],
            ondelete=ondelete,
        )


def _alter_dependent_id_type(column_type: sa.types.TypeEngine) -> None:
    for table_name, _constraint_name, _ondelete in _DEPENDENT_FOREIGN_KEYS:
        op.alter_column(
            table_name,
            "call_record_id",
            type_=column_type,
            postgresql_using="call_record_id::bigint"
            if isinstance(column_type, sa.BigInteger)
            else "call_record_id::integer",
        )


def upgrade() -> None:
    op.execute("DELETE FROM call_events")
    op.execute("DELETE FROM call_summary_field_values")
    op.execute("UPDATE tickets SET call_record_id = NULL WHERE call_record_id IS NOT NULL")
    op.execute(
        "UPDATE outbound_call_records SET call_record_id = NULL "
        "WHERE call_record_id IS NOT NULL"
    )
    op.execute(
        "UPDATE auto_outbound_call_records SET call_record_id = NULL "
        "WHERE call_record_id IS NOT NULL"
    )
    op.execute(
        "UPDATE sms_send_records SET call_record_id = NULL "
        "WHERE call_record_id IS NOT NULL"
    )

    _drop_dependent_foreign_keys()
    _alter_dependent_id_type(sa.BigInteger())
    op.drop_table("call_records")

    op.create_table(
        "call_records",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("public_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("call_id", sa.String(length=80), nullable=False),
        sa.Column("conversation_id", sa.String(length=80), nullable=True),
        sa.Column("root_call_id", sa.String(length=80), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("call_source", sa.String(length=24), nullable=False),
        sa.Column("customer_number", sa.String(length=64), nullable=True),
        sa.Column("service_number", sa.String(length=64), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("voice_flow_id", sa.Integer(), nullable=True),
        sa.Column("voice_flow_version_id", sa.Integer(), nullable=True),
        sa.Column("initiator_agent_id", sa.Integer(), nullable=True),
        sa.Column("last_serving_agent_id", sa.Integer(), nullable=True),
        sa.Column("last_queue_type", sa.String(length=24), nullable=True),
        sa.Column("last_queue_id", sa.Integer(), nullable=True),
        sa.Column(
            "lifecycle_status",
            sa.String(length=16),
            server_default="active",
            nullable=False,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("customer_connected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_agent_connected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finalization_status", sa.String(length=16), nullable=True),
        sa.Column("ended_event_id", sa.String(length=96), nullable=True),
        sa.Column("result_rule_version", sa.SmallInteger(), nullable=True),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actual_reception_type", sa.String(length=16), nullable=True),
        sa.Column("call_result", sa.String(length=32), nullable=True),
        sa.Column("hangup_party", sa.String(length=16), nullable=True),
        sa.Column("hangup_reason_code", sa.String(length=48), nullable=True),
        sa.Column("total_duration_ms", sa.BigInteger(), nullable=True),
        sa.Column("customer_ring_duration_ms", sa.BigInteger(), nullable=True),
        sa.Column("agent_wait_duration_ms", sa.BigInteger(), nullable=True),
        sa.Column("customer_agent_talk_duration_ms", sa.BigInteger(), nullable=True),
        sa.Column(
            "recording_status",
            sa.String(length=16),
            server_default="none",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(last_queue_type IS NULL) = (last_queue_id IS NULL)",
            name="ck_cr_last_queue_pair",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["voice_flow_id"], ["voice_flows.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["voice_flow_version_id"],
            ["voice_flow_versions.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["initiator_agent_id"], ["employees.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["last_serving_agent_id"], ["employees.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "call_id", name="uq_cr_tenant_call_id"),
        sa.UniqueConstraint("public_id", name="uq_cr_public_id"),
        sa.UniqueConstraint("ended_event_id", name="uq_cr_ended_event_id"),
    )
    op.create_index("ix_cr_tenant_started", "call_records", ["tenant_id", "started_at", "id"])
    op.create_index(
        "ix_cr_tenant_lifecycle_started",
        "call_records",
        ["tenant_id", "lifecycle_status", "started_at"],
    )
    op.create_index(
        "ix_cr_tenant_result_started",
        "call_records",
        ["tenant_id", "call_result", "started_at"],
    )
    op.create_index(
        "ix_cr_tenant_hangup_party_started",
        "call_records",
        ["tenant_id", "hangup_party", "started_at"],
    )
    op.create_index(
        "ix_cr_tenant_user_started",
        "call_records",
        ["tenant_id", "user_id", "started_at"],
    )
    op.create_index(
        "ix_cr_tenant_last_agent_started",
        "call_records",
        ["tenant_id", "last_serving_agent_id", "started_at"],
    )
    op.create_index(
        "ix_cr_tenant_last_queue_started",
        "call_records",
        ["tenant_id", "last_queue_type", "last_queue_id", "started_at"],
    )
    op.create_index(
        "ix_cr_tenant_customer_number",
        "call_records",
        ["tenant_id", "customer_number"],
    )
    op.create_index(
        "ix_cr_tenant_service_number",
        "call_records",
        ["tenant_id", "service_number"],
    )
    op.create_index("ix_cr_conversation", "call_records", ["conversation_id"])
    _create_dependent_foreign_keys()

    op.create_table(
        "call_record_access_scopes",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("call_record_id", sa.BigInteger(), nullable=False),
        sa.Column("subject_type", sa.String(length=24), nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=24), nullable=False),
        sa.Column("source_event_id", sa.String(length=96), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["call_record_id"], ["call_records.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "call_record_id",
            "subject_type",
            "subject_id",
            "reason",
            name="uq_cras_record_subject_reason",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "source_event_id",
            "subject_type",
            "subject_id",
            "reason",
            name="uq_cras_source_subject_reason",
        ),
    )
    op.create_index(
        "ix_cras_tenant_subject_record",
        "call_record_access_scopes",
        ["tenant_id", "subject_type", "subject_id", "call_record_id"],
    )
    op.create_index(
        "ix_cras_call_record", "call_record_access_scopes", ["call_record_id"]
    )

    op.create_table(
        "call_recordings",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("call_record_id", sa.BigInteger(), nullable=False),
        sa.Column("recording_id", sa.String(length=96), nullable=False),
        sa.Column("call_leg_id", sa.String(length=80), nullable=True),
        sa.Column("phase", sa.String(length=24), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.BigInteger(), nullable=True),
        sa.Column("source_event_id", sa.String(length=96), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["call_record_id"], ["call_records.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "recording_id", name="uq_call_recordings_tenant_recording"
        ),
    )
    op.create_index(
        "ix_call_recordings_record_started",
        "call_recordings",
        ["call_record_id", "started_at"],
    )


def downgrade() -> None:
    op.drop_table("call_recordings")
    op.drop_table("call_record_access_scopes")
    _drop_dependent_foreign_keys()
    op.drop_table("call_records")
    _alter_dependent_id_type(sa.Integer())

    op.create_table(
        "call_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("call_id", sa.String(length=80), nullable=False),
        sa.Column("conversation_id", sa.String(length=80), nullable=True),
        sa.Column("root_call_id", sa.String(length=80), nullable=True),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("state", sa.String(length=24), nullable=False),
        sa.Column("from_number", sa.String(length=64), nullable=True),
        sa.Column("to_number", sa.String(length=64), nullable=True),
        sa.Column("voice_flow_id", sa.Integer(), nullable=True),
        sa.Column("voice_flow_version_id", sa.Integer(), nullable=True),
        sa.Column("employee_group_id", sa.Integer(), nullable=True),
        sa.Column("agent_id", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ring_duration_ms", sa.Integer(), nullable=True),
        sa.Column("talk_duration_ms", sa.Integer(), nullable=True),
        sa.Column("device_type", sa.String(length=24), nullable=True),
        sa.Column("device_identifier", sa.String(length=80), nullable=True),
        sa.Column("hangup_reason", sa.String(length=80), nullable=True),
        sa.Column("recording_url", sa.String(length=500), nullable=True),
        sa.Column("recording_duration_ms", sa.Integer(), nullable=True),
        sa.Column(
            "extra_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["voice_flow_id"], ["voice_flows.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["voice_flow_version_id"],
            ["voice_flow_versions.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["employee_group_id"], ["employee_groups.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["agent_id"], ["employees.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("uq_cr_call_id", "call_records", ["call_id"], unique=True)
    op.create_index("ix_cr_tenant_started", "call_records", ["tenant_id", "started_at"])
    op.create_index("ix_cr_tenant_agent", "call_records", ["tenant_id", "agent_id"])
    op.create_index("ix_cr_tenant_user", "call_records", ["tenant_id", "user_id"])
    op.create_index("ix_cr_tenant_state", "call_records", ["tenant_id", "state"])
    op.create_index("ix_cr_conversation", "call_records", ["conversation_id"])
    _create_dependent_foreign_keys()
