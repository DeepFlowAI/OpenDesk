"""voice_flow graph + audio_assets + system variables

Revision ID: 5a1c2d3e4f5b
Revises: 4f5a6b7c8d9e
Create Date: 2026-05-25
"""
from __future__ import annotations

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "5a1c2d3e4f5b"
down_revision: Union[str, None] = "4f5a6b7c8d9e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_DEFAULT_GRAPH: dict = {
    "version": 1,
    "nodes": [
        {
            "id": "start",
            "type": "start",
            "position": {"x": 0, "y": 0},
            "data": {},
        }
    ],
    "edges": [],
    "variables": [],
}


def upgrade() -> None:
    # ── 1. audio_assets ──
    op.create_table(
        "audio_assets",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer, nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("storage_provider", sa.String(32), nullable=False),
        sa.Column("storage_key", sa.String(500), nullable=False),
        sa.Column("mime_type", sa.String(50), nullable=False),
        sa.Column("size_bytes", sa.BigInteger, nullable=False),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column("created_by_actor_type", sa.String(32), nullable=True),
        sa.Column("created_by_actor_id", sa.Integer, nullable=True),
        sa.Column("created_by_actor_name", sa.String(128), nullable=True),
        sa.Column("updated_by_actor_type", sa.String(32), nullable=True),
        sa.Column("updated_by_actor_id", sa.Integer, nullable=True),
        sa.Column("updated_by_actor_name", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime, nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_audio_assets_tenant", "audio_assets", ["tenant_id"], unique=False)

    # ── 2. voice_flow_versions ──
    op.create_table(
        "voice_flow_versions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer, nullable=False),
        sa.Column("voice_flow_id", sa.Integer, nullable=False),
        sa.Column("version_no", sa.Integer, nullable=False),
        sa.Column("graph_json", JSONB, nullable=False),
        sa.Column("comment", sa.String(200), nullable=True),
        sa.Column("created_by_actor_type", sa.String(32), nullable=True),
        sa.Column("created_by_actor_id", sa.Integer, nullable=True),
        sa.Column("created_by_actor_name", sa.String(128), nullable=True),
        sa.Column("updated_by_actor_type", sa.String(32), nullable=True),
        sa.Column("updated_by_actor_id", sa.Integer, nullable=True),
        sa.Column("updated_by_actor_name", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["voice_flow_id"], ["voice_flows.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("voice_flow_id", "version_no", name="uq_vfv_flow_version"),
    )
    op.create_index(
        "ix_vfv_tenant_flow",
        "voice_flow_versions",
        ["tenant_id", "voice_flow_id"],
        unique=False,
    )

    # ── 3. voice_flow_system_variables (global seed) ──
    op.create_table(
        "voice_flow_system_variables",
        sa.Column("name", sa.String(64), primary_key=True),
        sa.Column("display_name_zh", sa.String(64), nullable=False),
        sa.Column("display_name_en", sa.String(64), nullable=False),
        sa.Column("value_type", sa.String(16), nullable=False),
        sa.Column("description_zh", sa.Text, nullable=False),
        sa.Column("description_en", sa.Text, nullable=False),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
    )

    # ── 4. voice_flows: add description + current_version_id ──
    op.add_column("voice_flows", sa.Column("description", sa.String(200), nullable=True))
    op.add_column("voice_flows", sa.Column("current_version_id", sa.Integer, nullable=True))
    op.create_foreign_key(
        "fk_voice_flows_current_version",
        "voice_flows",
        "voice_flow_versions",
        ["current_version_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # ── 5. Seed v1 for every existing voice_flow row ──
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT id, tenant_id FROM voice_flows WHERE deleted_at IS NULL"
        )
    ).fetchall()
    graph_text = json.dumps(_DEFAULT_GRAPH)
    for vf_id, tenant_id in rows:
        result = conn.execute(
            sa.text(
                """
                INSERT INTO voice_flow_versions
                    (tenant_id, voice_flow_id, version_no, graph_json,
                     created_by_actor_type, created_by_actor_name,
                     created_at, updated_at)
                VALUES
                    (:tenant_id, :vf_id, 1, CAST(:graph AS jsonb),
                     'system', 'Migration', NOW(), NOW())
                RETURNING id
                """
            ),
            {"tenant_id": tenant_id, "vf_id": vf_id, "graph": graph_text},
        )
        version_id = result.scalar_one()
        conn.execute(
            sa.text(
                "UPDATE voice_flows SET current_version_id = :v WHERE id = :id"
            ),
            {"v": version_id, "id": vf_id},
        )

    # ── 6. Seed system variables ──
    sys_vars = [
        ("sys.caller_number", "用户号码", "Caller Number", "text",
         "当前来电的主叫号码（E.164 格式）", "Inbound caller number (E.164)", 10),
        ("sys.called_number", "服务号码", "Called Number", "text",
         "当前来电的被叫号码（企业对外服务号码）", "Inbound called/service number", 20),
        ("sys.current_time", "当前时间", "Current Time", "time",
         "流程执行到该节点时的服务器时间", "Server time when the node executes", 30),
    ]
    for row in sys_vars:
        conn.execute(
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
            ),
            {"n": row[0], "nzh": row[1], "nen": row[2], "vt": row[3],
             "dzh": row[4], "den": row[5], "so": row[6]},
        )


def downgrade() -> None:
    op.drop_constraint("fk_voice_flows_current_version", "voice_flows", type_="foreignkey")
    op.drop_column("voice_flows", "current_version_id")
    op.drop_column("voice_flows", "description")

    op.drop_table("voice_flow_system_variables")

    op.drop_index("ix_vfv_tenant_flow", table_name="voice_flow_versions")
    op.drop_table("voice_flow_versions")

    op.drop_index("ix_audio_assets_tenant", table_name="audio_assets")
    op.drop_table("audio_assets")
