"""
Emoji setting service.
"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.configs.settings import settings
from app.models.emoji_setting import EmojiSetting
from app.repositories.emoji_setting_repository import EmojiSettingRepository
from app.repositories.tenant_repository import TenantRepository
from app.schemas.emoji_setting import (
    EmojiItem,
    EmojiSettingPayload,
    EmojiSettingResponse,
    EmojiSettingTargetPayload,
    EmojiTargetConfigResponse,
)


DEFAULT_EMOJI_ROWS: list[tuple[str, str, str, str, str, list[str]]] = [
    ("👋", "你好", "Hello", "打招呼", "Wave", ["hello", "hi", "greeting"]),
    ("😊", "微笑", "Smile", "微笑", "Smile", ["happy", "friendly"]),
    ("🙂", "好的", "Okay", "友好", "Friendly", ["ok", "friendly"]),
    ("😄", "开心", "Happy", "开心", "Happy", ["joy", "laugh"]),
    ("👍", "收到", "Got it", "收到", "Thumbs up", ["yes", "agree"]),
    ("👌", "OK", "OK", "可以", "Okay", ["ok", "fine"]),
    ("🙏", "感谢", "Thanks", "感谢", "Thank you", ["thanks", "please"]),
    ("🙇", "抱歉", "Sorry", "抱歉", "Apology", ["sorry", "apologize"]),
    ("💪", "加油", "Support", "支持", "Support", ["strong", "support"]),
    ("❤️", "喜欢", "Love", "爱心", "Heart", ["love", "like"]),
    ("⭐", "满意", "Satisfied", "星标", "Star", ["star", "satisfied"]),
    ("🎉", "恭喜", "Congrats", "庆祝", "Celebrate", ["party", "celebrate"]),
    ("🎁", "礼物", "Gift", "福利", "Gift", ["gift", "benefit"]),
    ("🔥", "热门", "Hot", "火热", "Fire", ["hot", "popular"]),
    ("⏳", "等待", "Waiting", "等待", "Wait", ["wait", "loading"]),
    ("👀", "看看", "Check", "查看", "Look", ["look", "view"]),
    ("🤔", "思考", "Thinking", "思考", "Think", ["think", "consider"]),
    ("❓", "疑问", "Question", "疑问", "Question", ["question", "unknown"]),
    ("❗", "注意", "Notice", "提醒", "Alert", ["notice", "important"]),
    ("📞", "电话", "Phone", "电话", "Phone", ["phone", "call"]),
    ("✉️", "邮件", "Email", "邮件", "Email", ["mail", "email"]),
    ("📄", "文件", "File", "文档", "Document", ["file", "document"]),
    ("🔗", "链接", "Link", "链接", "Link", ["url", "link"]),
    ("🛠️", "处理中", "Fixing", "工具 / 修复", "Tool / fix", ["tool", "fix"]),
    ("✅", "已完成", "Done", "完成", "Complete", ["done", "success"]),
    ("❌", "失败", "Failed", "错误", "Error", ["error", "failed"]),
    ("😂", "大笑", "Laughing", "大笑", "Laugh", ["laugh", "funny"]),
    ("🤣", "笑哭", "ROFL", "笑哭", "Laughing hard", ["laugh", "tears"]),
    ("😅", "尴尬", "Awkward", "无奈", "Awkward", ["awkward", "sweat"]),
    ("😢", "难过", "Sad", "难过", "Sad", ["sad", "cry"]),
    ("😭", "大哭", "Crying", "大哭", "Crying", ["cry", "sad"]),
    ("😞", "失望", "Disappointed", "失望", "Disappointed", ["disappointed"]),
    ("😕", "困惑", "Confused", "困惑", "Confused", ["confused"]),
    ("😮", "惊讶", "Surprised", "惊讶", "Surprised", ["surprise"]),
    ("😡", "生气", "Angry", "生气", "Angry", ["angry"]),
    ("🤯", "抓狂", "Mind blown", "抓狂", "Overwhelmed", ["mind blown"]),
    ("😩", "累了", "Tired", "累了", "Tired", ["tired"]),
    ("😟", "担心", "Worried", "担心", "Worried", ["worried"]),
]


class EmojiSettingService:
    @staticmethod
    def default_items() -> list[EmojiItem]:
        return [
            EmojiItem(
                emoji=emoji,
                name=name,
                name_en=name_en,
                alias=alias,
                alias_en=alias_en,
                keywords=keywords,
            )
            for emoji, name, name_en, alias, alias_en, keywords in DEFAULT_EMOJI_ROWS
        ]

    @staticmethod
    def default_payload() -> EmojiSettingPayload:
        default_items = EmojiSettingService.default_items()
        return EmojiSettingPayload(
            user=EmojiSettingTargetPayload(enabled=True, emojis=default_items),
            agent=EmojiSettingTargetPayload(enabled=True, emojis=default_items),
        )

    @staticmethod
    def _actor_name(current_user: dict) -> str | None:
        for key in ("display_name", "name", "username", "email"):
            value = current_user.get(key)
            if value:
                return str(value)[:128]
        return None

    @staticmethod
    def _row_to_payload(row: EmojiSetting) -> EmojiSettingPayload:
        return EmojiSettingPayload(
            user=EmojiSettingTargetPayload(
                enabled=row.user_enabled,
                emojis=row.user_emojis or [],
            ),
            agent=EmojiSettingTargetPayload(
                enabled=row.agent_enabled,
                emojis=row.agent_emojis or [],
            ),
        )

    @staticmethod
    def _row_to_response(row: EmojiSetting, configured: bool = True) -> EmojiSettingResponse:
        payload = EmojiSettingService._row_to_payload(row)
        data = payload.model_dump(mode="json")
        data.update(
            {
                "id": row.id,
                "tenant_id": row.tenant_id,
                "configured": configured,
                "updated_by_id": row.updated_by_id,
                "updated_by_name": row.updated_by_name,
                "updated_at": row.updated_at,
            }
        )
        return EmojiSettingResponse.model_validate(data)

    @staticmethod
    def _default_response(tenant_id: int) -> EmojiSettingResponse:
        data = EmojiSettingService.default_payload().model_dump(mode="json")
        data.update(
            {
                "id": None,
                "tenant_id": tenant_id,
                "configured": False,
                "updated_by_id": None,
                "updated_by_name": None,
                "updated_at": None,
            }
        )
        return EmojiSettingResponse.model_validate(data)

    @staticmethod
    def _target_response(
        *,
        target: str,
        configured: bool,
        payload: EmojiSettingTargetPayload,
        updated_at,
    ) -> EmojiTargetConfigResponse:
        return EmojiTargetConfigResponse(
            target=target,
            configured=configured,
            enabled=payload.enabled,
            emojis=payload.emojis,
            updated_at=updated_at,
        )

    @staticmethod
    async def get_current(db: AsyncSession, tenant_id: int) -> EmojiSettingResponse:
        row = await EmojiSettingRepository.get_by_tenant(db, tenant_id)
        if not row:
            return EmojiSettingService._default_response(tenant_id)
        return EmojiSettingService._row_to_response(row)

    @staticmethod
    async def save(
        db: AsyncSession,
        tenant_id: int,
        current_user: dict,
        payload: EmojiSettingPayload,
    ) -> EmojiSettingResponse:
        snapshot = payload.model_dump(mode="json")
        row = await EmojiSettingRepository.save(
            db,
            tenant_id,
            {
                "user_enabled": payload.user.enabled,
                "agent_enabled": payload.agent.enabled,
                "user_emojis": snapshot["user"]["emojis"],
                "agent_emojis": snapshot["agent"]["emojis"],
                "updated_by_id": current_user.get("user_id"),
                "updated_by_name": EmojiSettingService._actor_name(current_user),
            },
        )
        return EmojiSettingService._row_to_response(row)

    @staticmethod
    async def get_target(
        db: AsyncSession,
        tenant_id: int,
        target: str,
    ) -> EmojiTargetConfigResponse:
        row = await EmojiSettingRepository.get_by_tenant(db, tenant_id)
        if row:
            payload = EmojiSettingService._row_to_payload(row)
            target_payload = payload.agent if target == "agent" else payload.user
            return EmojiSettingService._target_response(
                target=target,
                configured=True,
                payload=target_payload,
                updated_at=row.updated_at,
            )

        defaults = EmojiSettingService.default_payload()
        target_payload = defaults.agent if target == "agent" else defaults.user
        return EmojiSettingService._target_response(
            target=target,
            configured=False,
            payload=target_payload,
            updated_at=None,
        )

    @staticmethod
    async def get_public_user_config(db: AsyncSession) -> EmojiTargetConfigResponse:
        tenant = await TenantRepository.get_by_tenant_id(db, settings.DEFAULT_TENANT_ID)
        if not tenant:
            tenants, _total = await TenantRepository.get_paginated(db, page=1, per_page=1)
            tenant = tenants[0] if tenants else None
        tenant_id = tenant.id if tenant else 0
        return await EmojiSettingService.get_target(db, tenant_id, "user")
