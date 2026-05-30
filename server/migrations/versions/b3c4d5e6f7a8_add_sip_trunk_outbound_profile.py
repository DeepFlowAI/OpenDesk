"""add outbound_profile to sip_trunks

Revision ID: b3c4d5e6f7a8
Revises: a1b2c3d4e5f6
Create Date: 2026-05-26

Adds a nullable JSONB column carrying per-trunk outbound gateway config:
  { server, port, user, pass, realm, callee_prefix }

Required for genuine multi-trunk outbound via FlowKit Catalog. When
NULL, the trunk is inbound-only and `call.originate` against it returns
`trunk_not_ready`. Operators populate this column to enable outbound on
a given trunk.

TODO(security): pass is currently stored plaintext. Encrypt at rest in a
follow-up; the FlowKit-side Catalog redacts it from /catalog responses.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "b3c4d5e6f7a8"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "sip_trunks",
        sa.Column("outbound_profile", JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("sip_trunks", "outbound_profile")
