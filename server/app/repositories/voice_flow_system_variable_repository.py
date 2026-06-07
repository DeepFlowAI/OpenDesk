"""
VoiceFlowSystemVariable repository — global seed table; read-only at runtime.
"""
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.voice_flow_system_variable import VoiceFlowSystemVariable


BUILTIN_SYSTEM_VARIABLES = [
    {
        "name": "sys.assign_queue_status",
        "display_name_zh": "分配队列状态",
        "display_name_en": "Assign Queue Status",
        "value_type": "text",
        "description_zh": "最近一次分配队列节点的失败状态，可用于 timeout 出口后的信息判定",
        "description_en": "Failure status from the latest assign queue node for timeout-branch conditions",
        "sort_order": 40,
    },
    {
        "name": "sys.assign_queue_limit_reason",
        "display_name_zh": "分配队列上限原因",
        "display_name_en": "Assign Queue Limit Reason",
        "value_type": "text",
        "description_zh": "达到排队上限时的原因：max_waiting_count、max_wait_seconds 或 mixed_limit",
        "description_en": "Queue limit reason: max_waiting_count, max_wait_seconds, or mixed_limit",
        "sort_order": 50,
    },
]


class VoiceFlowSystemVariableRepository:

    @staticmethod
    async def list_all(db: AsyncSession) -> list[VoiceFlowSystemVariable | SimpleNamespace]:
        q = select(VoiceFlowSystemVariable).order_by(
            VoiceFlowSystemVariable.sort_order.asc(),
            VoiceFlowSystemVariable.name.asc(),
        )
        rows = list((await db.execute(q)).scalars().all())
        existing = {row.name for row in rows}
        for item in BUILTIN_SYSTEM_VARIABLES:
            if item["name"] not in existing:
                rows.append(SimpleNamespace(**item))
        return sorted(rows, key=lambda row: (row.sort_order, row.name))

    @staticmethod
    async def names(db: AsyncSession) -> set[str]:
        q = select(VoiceFlowSystemVariable.name)
        names = set((await db.execute(q)).scalars().all())
        names.update(item["name"] for item in BUILTIN_SYSTEM_VARIABLES)
        return names
