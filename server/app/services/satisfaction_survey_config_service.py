"""
Satisfaction survey configuration service.
"""
from copy import deepcopy

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.satisfaction_survey_config import SatisfactionSurveyConfig, SatisfactionSurveyConfigVersion
from app.repositories.satisfaction_survey_config_repository import SatisfactionSurveyConfigRepository
from app.schemas.satisfaction_survey_config import (
    ProductSatisfactionSettings,
    SatisfactionRatingOption,
    SatisfactionSurveyConfigPayload,
    SatisfactionSurveyConfigResponse,
    SatisfactionSurveyVersionDetail,
    ServiceSatisfactionSettings,
    SatisfactionTriggerSettings,
)


class SatisfactionSurveyConfigService:
    @staticmethod
    def _default_options(prefix: str, mode: str, kind: str) -> list[SatisfactionRatingOption]:
        positive = (
            ["响应及时", "态度友好", "解决问题", "表达清晰"]
            if kind == "service"
            else ["易于使用", "功能清晰", "速度快", "符合预期"]
        )
        negative = (
            ["等待太久", "没有解决", "态度不好", "重复沟通"]
            if kind == "service"
            else ["操作复杂", "功能缺失", "加载慢", "不符合预期"]
        )
        if mode == "emoji":
            rows = [("不满意", 2, negative, "required"), ("一般", 6, [], "optional"), ("满意", 10, positive, "hidden")]
        elif mode == "text":
            rows = [
                ("超级满意", 10, positive, "hidden"),
                ("满意", 8, positive, "optional"),
                ("一般", 6, [], "optional"),
                ("不满意", 4, negative, "required"),
                ("非常不满意", 2, negative, "required"),
            ]
        else:
            rows = [
                ("非常不满意", 2, negative, "required"),
                ("不满意", 4, negative, "required"),
                ("一般", 6, [], "optional"),
                ("满意", 8, positive, "optional"),
                ("非常满意", 10, positive, "hidden"),
            ]
        return [
            SatisfactionRatingOption(
                key=f"{prefix}-{index}",
                name=name,
                score=score,
                labels=labels,
                remark_requirement=remark_requirement,
            )
            for index, (name, score, labels, remark_requirement) in enumerate(rows, start=1)
        ]

    @staticmethod
    def default_payload() -> SatisfactionSurveyConfigPayload:
        return SatisfactionSurveyConfigPayload(
            name="满意度调查",
            enabled=True,
            triggers=SatisfactionTriggerSettings(),
            service=ServiceSatisfactionSettings(
                enabled=True,
                section_title="服务满意度",
                popup_title="请评价本次服务",
                rating_mode="stars",
                rating_options=SatisfactionSurveyConfigService._default_options("service-stars", "stars", "service"),
                tag_selection_mode="multiple",
                remark_enabled=True,
                remark_placeholder="欢迎补充更多反馈",
                show_resolution=True,
            ),
            product=ProductSatisfactionSettings(
                enabled=True,
                section_title="产品满意度",
                popup_title="请评价本次产品体验",
                rating_mode="stars",
                rating_options=SatisfactionSurveyConfigService._default_options("product-stars", "stars", "product"),
                tag_selection_mode="multiple",
                remark_enabled=True,
                remark_placeholder="欢迎补充更多反馈",
            ),
        )

    @staticmethod
    def _actor_name(current_user: dict) -> str | None:
        for key in ("display_name", "name", "username", "email"):
            value = current_user.get(key)
            if value:
                return str(value)[:128]
        return None

    @staticmethod
    def _payload_to_snapshot(payload: SatisfactionSurveyConfigPayload) -> dict:
        return payload.model_dump(mode="json")

    @staticmethod
    def _merge_settings(defaults: dict, persisted: dict | None) -> dict:
        if not isinstance(persisted, dict) or not persisted:
            return deepcopy(defaults)

        merged = deepcopy(defaults)
        for key, value in persisted.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = SatisfactionSurveyConfigService._merge_settings(merged[key], value)
            else:
                merged[key] = value
        return merged

    @staticmethod
    def _normalize_triggers(persisted: dict | None, defaults: dict) -> dict:
        if not isinstance(persisted, dict) or not persisted:
            return deepcopy(defaults)
        return SatisfactionTriggerSettings.model_validate(persisted).model_dump(mode="json")

    @staticmethod
    def _normalize_type_settings(
        persisted: dict | None,
        defaults: dict,
        schema: type[ServiceSatisfactionSettings] | type[ProductSatisfactionSettings],
    ) -> dict:
        merged = SatisfactionSurveyConfigService._merge_settings(defaults, persisted)
        return schema.model_validate(merged).model_dump(mode="json")

    @staticmethod
    def _config_to_payload(row: SatisfactionSurveyConfig) -> SatisfactionSurveyConfigPayload:
        defaults = SatisfactionSurveyConfigService.default_payload().model_dump(mode="json")
        return SatisfactionSurveyConfigPayload.model_validate(
            {
                "name": row.name or defaults["name"],
                "enabled": row.enabled if row.enabled is not None else defaults["enabled"],
                "triggers": SatisfactionSurveyConfigService._normalize_triggers(
                    row.triggers,
                    defaults["triggers"],
                ),
                "service": SatisfactionSurveyConfigService._normalize_type_settings(
                    row.service_settings,
                    defaults["service"],
                    ServiceSatisfactionSettings,
                ),
                "product": SatisfactionSurveyConfigService._normalize_type_settings(
                    row.product_settings,
                    defaults["product"],
                    ProductSatisfactionSettings,
                ),
            }
        )

    @staticmethod
    def _config_to_response(row: SatisfactionSurveyConfig, configured: bool = True) -> dict:
        payload = SatisfactionSurveyConfigService._config_to_payload(row)
        data = payload.model_dump(mode="json")
        data.update(
            {
                "id": row.id,
                "tenant_id": row.tenant_id,
                "configured": configured and row.current_version is not None,
                "current_version": row.current_version,
                "updated_by_id": row.updated_by_id,
                "updated_by_name": row.updated_by_name,
                "updated_at": row.updated_at,
            }
        )
        return data

    @staticmethod
    def _default_response(tenant_id: int) -> dict:
        data = SatisfactionSurveyConfigService.default_payload().model_dump(mode="json")
        data.update(
            {
                "id": None,
                "tenant_id": tenant_id,
                "configured": False,
                "current_version": None,
                "updated_by_id": None,
                "updated_by_name": None,
                "updated_at": None,
            }
        )
        return data

    @staticmethod
    def _trigger_modes(triggers: dict) -> list[str]:
        normalized = SatisfactionTriggerSettings.model_validate(triggers or {})
        modes: list[str] = []
        if normalized.agent_invite:
            modes.append("agent_invite")
        if normalized.user_initiated:
            modes.append("user_initiated")
        if normalized.session_end_invite:
            modes.append("session_end_invite")
        return modes

    @staticmethod
    def _version_summary(snapshot: dict) -> dict:
        service = snapshot.get("service") or {}
        product = snapshot.get("product") or {}
        triggers = snapshot.get("triggers") or {}

        survey_types: list[str] = []
        rating_modes: dict[str, str] = {}
        if service.get("enabled"):
            survey_types.append("service")
            rating_modes["service"] = str(service.get("rating_mode") or "")
        if product.get("enabled"):
            survey_types.append("product")
            rating_modes["product"] = str(product.get("rating_mode") or "")

        trigger_modes: list[str] = SatisfactionSurveyConfigService._trigger_modes(triggers)

        return {
            "survey_types": survey_types,
            "rating_modes": rating_modes,
            "trigger_modes": trigger_modes,
        }

    @staticmethod
    def _type_rating_fingerprint(settings: dict) -> tuple[str, frozenset[tuple[bool, str]]]:
        rating_mode = str(settings.get("rating_mode") or "")
        options = frozenset(
            (bool(option.get("enabled", True)), str(option.get("name") or "").strip())
            for option in (settings.get("rating_options") or [])
        )
        return rating_mode, options

    @staticmethod
    def _snapshot_rating_fingerprint(snapshot: dict) -> dict[str, tuple[str, frozenset[tuple[bool, str]]]]:
        return {
            "service": SatisfactionSurveyConfigService._type_rating_fingerprint(snapshot.get("service") or {}),
            "product": SatisfactionSurveyConfigService._type_rating_fingerprint(snapshot.get("product") or {}),
        }

    @staticmethod
    def should_bump_version(previous_snapshot: dict | None, new_snapshot: dict) -> bool:
        if previous_snapshot is None:
            return True
        return SatisfactionSurveyConfigService._snapshot_rating_fingerprint(previous_snapshot) != (
            SatisfactionSurveyConfigService._snapshot_rating_fingerprint(new_snapshot)
        )

    @staticmethod
    def _version_to_list_item(row: SatisfactionSurveyConfigVersion, current_version: int | None) -> dict:
        summary = SatisfactionSurveyConfigService._version_summary(row.snapshot or {})
        return {
            "id": row.id,
            "version": row.version,
            "is_current": current_version == row.version,
            "updated_by_id": row.updated_by_id,
            "updated_by_name": row.updated_by_name,
            "published_at": row.published_at,
            **summary,
        }

    @staticmethod
    async def get_current(db: AsyncSession, tenant_id: int) -> dict:
        row = await SatisfactionSurveyConfigRepository.get_current(db, tenant_id)
        if not row:
            return SatisfactionSurveyConfigService._default_response(tenant_id)
        return SatisfactionSurveyConfigService._config_to_response(row)

    @staticmethod
    async def save(
        db: AsyncSession,
        tenant_id: int,
        current_user: dict,
        payload: SatisfactionSurveyConfigPayload,
    ) -> dict:
        actor_id = current_user.get("user_id")
        actor_name = SatisfactionSurveyConfigService._actor_name(current_user)
        snapshot = SatisfactionSurveyConfigService._payload_to_snapshot(payload)
        config_data = {
            "name": payload.name,
            "enabled": payload.enabled,
            "triggers": snapshot["triggers"],
            "service_settings": snapshot["service"],
            "product_settings": snapshot["product"],
            "updated_by_id": actor_id,
            "updated_by_name": actor_name,
        }
        version_data = {
            "snapshot": snapshot,
            "updated_by_id": actor_id,
            "updated_by_name": actor_name,
        }

        current = await SatisfactionSurveyConfigRepository.get_current(db, tenant_id)
        previous_snapshot: dict | None = None
        if current and current.current_version is not None:
            current_version = await SatisfactionSurveyConfigRepository.get_version(
                db,
                tenant_id,
                current.current_version,
            )
            if current_version:
                previous_snapshot = current_version.snapshot

        bump_version = SatisfactionSurveyConfigService.should_bump_version(previous_snapshot, snapshot)
        row, _version = await SatisfactionSurveyConfigRepository.save(
            db,
            tenant_id,
            config_data,
            version_data,
            bump_version=bump_version,
        )
        return SatisfactionSurveyConfigService._config_to_response(row)

    @staticmethod
    async def patch_enabled(
        db: AsyncSession,
        tenant_id: int,
        current_user: dict,
        enabled: bool,
    ) -> dict:
        current = await SatisfactionSurveyConfigRepository.get_current(db, tenant_id)
        payload = (
            SatisfactionSurveyConfigService._config_to_payload(current)
            if current
            else SatisfactionSurveyConfigService.default_payload()
        )
        payload.enabled = enabled
        return await SatisfactionSurveyConfigService.save(db, tenant_id, current_user, payload)

    @staticmethod
    async def list_versions(db: AsyncSession, tenant_id: int, page: int = 1, per_page: int = 50) -> dict:
        current = await SatisfactionSurveyConfigRepository.get_current(db, tenant_id)
        current_version = current.current_version if current else None
        rows, total = await SatisfactionSurveyConfigRepository.list_versions(db, tenant_id, page, per_page)
        pages = (total + per_page - 1) // per_page if total > 0 else 0
        return {
            "items": [
                SatisfactionSurveyConfigService._version_to_list_item(row, current_version)
                for row in rows
            ],
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": pages,
            "current_version": current_version,
        }

    @staticmethod
    async def get_version(db: AsyncSession, tenant_id: int, version: int) -> SatisfactionSurveyVersionDetail:
        current = await SatisfactionSurveyConfigRepository.get_current(db, tenant_id)
        row = await SatisfactionSurveyConfigRepository.get_version(db, tenant_id, version)
        if not row:
            raise NotFoundError("Satisfaction survey version not found")
        return SatisfactionSurveyVersionDetail(
            id=row.id,
            version=row.version,
            is_current=bool(current and current.current_version == row.version),
            snapshot=SatisfactionSurveyConfigPayload.model_validate(row.snapshot or {}),
            updated_by_id=row.updated_by_id,
            updated_by_name=row.updated_by_name,
            published_at=row.published_at,
        )
