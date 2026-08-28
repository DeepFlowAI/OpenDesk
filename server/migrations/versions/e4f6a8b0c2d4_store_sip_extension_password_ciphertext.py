"""Store encrypted SIP extension passwords.

Revision ID: e4f6a8b0c2d4
Revises: c3d5e7f9a1b2
"""

from alembic import op
import sqlalchemy as sa


revision: str = "e4f6a8b0c2d4"
down_revision: str | None = "c3d5e7f9a1b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sip_extensions",
        sa.Column("auth_password_ciphertext", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("sip_extensions", "auth_password_ciphertext")
