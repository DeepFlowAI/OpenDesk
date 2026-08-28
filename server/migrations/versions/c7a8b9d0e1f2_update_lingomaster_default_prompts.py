"""update lingomaster default prompts

Revision ID: c7a8b9d0e1f2
Revises: e3f4a5b6c7d9
Create Date: 2026-08-05 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.constants.lingomaster import (
    DEFAULT_AGENT_TRANSLATION_PROMPT,
    DEFAULT_VISITOR_TRANSLATION_PROMPT,
)


revision: str = "c7a8b9d0e1f2"
down_revision: Union[str, None] = "e3f4a5b6c7d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


OLD_VISITOR_TRANSLATION_PROMPT = """你是客服场景的实时翻译引擎。请将以下{{source_language}}的访客消息翻译为{{target_language}}。
要求：准确保留原意与语气；品牌名、产品名、型号、URL、代码片段保持原文不译；只输出译文，不要输出任何解释。
以下会话历史均为双方消息原文，仅用于理解上下文：
{{conversation_history}}
当前消息：{{message}}"""

OLD_AGENT_TRANSLATION_PROMPT = """你是客服场景的实时翻译引擎。请将以下{{source_language}}的客服消息翻译为{{target_language}}。
要求：准确保留原意与语气；品牌名、产品名、型号、URL、代码片段保持原文不译；只输出译文，不要输出任何解释。
以下会话历史均为双方消息原文，仅用于理解上下文：
{{conversation_history}}
当前消息：{{message}}"""


def _settings_table() -> sa.TableClause:
    return sa.table(
        "system_settings",
        sa.column("lingomaster_visitor_prompt", sa.Text()),
        sa.column("lingomaster_agent_prompt", sa.Text()),
    )


def upgrade() -> None:
    settings = _settings_table()
    connection = op.get_bind()
    connection.execute(
        settings.update()
        .where(settings.c.lingomaster_visitor_prompt == OLD_VISITOR_TRANSLATION_PROMPT)
        .values(lingomaster_visitor_prompt=DEFAULT_VISITOR_TRANSLATION_PROMPT)
    )
    connection.execute(
        settings.update()
        .where(settings.c.lingomaster_agent_prompt == OLD_AGENT_TRANSLATION_PROMPT)
        .values(lingomaster_agent_prompt=DEFAULT_AGENT_TRANSLATION_PROMPT)
    )
    op.alter_column(
        "system_settings",
        "lingomaster_visitor_prompt",
        existing_type=sa.Text(),
        existing_nullable=False,
        server_default=DEFAULT_VISITOR_TRANSLATION_PROMPT,
    )
    op.alter_column(
        "system_settings",
        "lingomaster_agent_prompt",
        existing_type=sa.Text(),
        existing_nullable=False,
        server_default=DEFAULT_AGENT_TRANSLATION_PROMPT,
    )


def downgrade() -> None:
    settings = _settings_table()
    connection = op.get_bind()
    connection.execute(
        settings.update()
        .where(settings.c.lingomaster_visitor_prompt == DEFAULT_VISITOR_TRANSLATION_PROMPT)
        .values(lingomaster_visitor_prompt=OLD_VISITOR_TRANSLATION_PROMPT)
    )
    connection.execute(
        settings.update()
        .where(settings.c.lingomaster_agent_prompt == DEFAULT_AGENT_TRANSLATION_PROMPT)
        .values(lingomaster_agent_prompt=OLD_AGENT_TRANSLATION_PROMPT)
    )
    op.alter_column(
        "system_settings",
        "lingomaster_visitor_prompt",
        existing_type=sa.Text(),
        existing_nullable=False,
        server_default=OLD_VISITOR_TRANSLATION_PROMPT,
    )
    op.alter_column(
        "system_settings",
        "lingomaster_agent_prompt",
        existing_type=sa.Text(),
        existing_nullable=False,
        server_default=OLD_AGENT_TRANSLATION_PROMPT,
    )
