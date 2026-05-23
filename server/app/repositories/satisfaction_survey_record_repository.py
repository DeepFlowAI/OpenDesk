"""
Satisfaction survey record repository.
"""
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import MessageContentType, MessageSenderType
from app.models.message import Message
from app.models.satisfaction_survey_record import SatisfactionSurveyRecord


class SatisfactionSurveyRecordRepository:
    @staticmethod
    async def get_by_conversation(
        db: AsyncSession,
        conversation_id: int,
    ) -> SatisfactionSurveyRecord | None:
        result = await db.execute(
            select(SatisfactionSurveyRecord).where(
                SatisfactionSurveyRecord.conversation_id == conversation_id
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_conversation_ids(
        db: AsyncSession,
        conversation_ids: list[int],
    ) -> dict[int, SatisfactionSurveyRecord]:
        if not conversation_ids:
            return {}
        result = await db.execute(
            select(SatisfactionSurveyRecord).where(
                SatisfactionSurveyRecord.conversation_id.in_(conversation_ids)
            )
        )
        rows = list(result.scalars().all())
        return {row.conversation_id: row for row in rows}

    @staticmethod
    async def create_or_update_invitation(
        db: AsyncSession,
        conversation_id: int,
        data: dict,
        message_data: dict,
    ) -> tuple[SatisfactionSurveyRecord, Message]:
        record = await SatisfactionSurveyRecordRepository.get_by_conversation(db, conversation_id)
        if record:
            for key, value in data.items():
                setattr(record, key, value)
        else:
            record = SatisfactionSurveyRecord(**data)
            db.add(record)

        await db.flush()
        message = SatisfactionSurveyRecordRepository._build_event_message(record, message_data)
        db.add(message)
        await db.commit()
        await db.refresh(record)
        await db.refresh(message)
        return record, message

    @staticmethod
    async def create_or_update_record(
        db: AsyncSession,
        conversation_id: int,
        data: dict,
    ) -> SatisfactionSurveyRecord:
        record = await SatisfactionSurveyRecordRepository.get_by_conversation(db, conversation_id)
        if record:
            for key, value in data.items():
                setattr(record, key, value)
        else:
            record = SatisfactionSurveyRecord(**data)
            db.add(record)

        await db.commit()
        await db.refresh(record)
        return record

    @staticmethod
    async def save_submission(
        db: AsyncSession,
        record: SatisfactionSurveyRecord,
        data: dict,
        message_data: dict,
    ) -> tuple[SatisfactionSurveyRecord, Message]:
        for key, value in data.items():
            setattr(record, key, value)
        await db.flush()
        message = SatisfactionSurveyRecordRepository._build_event_message(record, message_data)
        db.add(message)
        await db.commit()
        await db.refresh(record)
        await db.refresh(message)
        return record, message

    @staticmethod
    def _build_event_message(record: SatisfactionSurveyRecord, data: dict) -> Message:
        metadata = dict(data.get("metadata_") or {})
        metadata.setdefault("satisfaction_record_id", record.id)
        metadata.setdefault("config_version", record.config_version)
        message_data = {
            "tenant_id": data["tenant_id"],
            "conversation_id": data["conversation_id"],
            "sender_type": MessageSenderType.SYSTEM.value,
            "sender_id": data.get("actor_id"),
            "content_type": MessageContentType.SATISFACTION_EVENT.value,
            "content": data["summary"],
            "metadata_": metadata,
        }
        if data.get("occurred_at") is not None:
            message_data["created_at"] = data["occurred_at"]
        return Message(**message_data)

    @staticmethod
    async def get_event_messages_by_conversation(
        db: AsyncSession,
        conversation_id: int,
    ) -> list[Message]:
        result = await db.execute(
            select(Message)
            .where(
                Message.conversation_id == conversation_id,
                Message.content_type == MessageContentType.SATISFACTION_EVENT.value,
            )
            .order_by(Message.created_at.asc(), Message.id.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    def apply_filters(
        base_filters: list,
        *,
        statuses: list[str] | None = None,
        current_version: int | None = None,
        resolved: list[str] | None = None,
        service_options: list[str] | None = None,
        service_labels: list[str] | None = None,
        product_options: list[str] | None = None,
        product_labels: list[str] | None = None,
    ) -> list:
        filters = list(base_filters)
        status_clauses = []
        for status in statuses or []:
            if status == "none":
                status_clauses.append(SatisfactionSurveyRecord.id.is_(None))
            elif status == "invited":
                status_clauses.append(SatisfactionSurveyRecord.status == "invited")
            elif status == "submitted":
                status_clauses.append(SatisfactionSurveyRecord.status == "submitted")
        if status_clauses:
            filters.append(or_(*status_clauses))

        has_version_filters = any([resolved, service_options, service_labels, product_options, product_labels])
        if has_version_filters:
            filters.append(SatisfactionSurveyRecord.status == "submitted")
            if current_version is not None:
                filters.append(SatisfactionSurveyRecord.config_version == current_version)

        if resolved:
            resolved_clauses = []
            if "resolved" in resolved:
                resolved_clauses.append(SatisfactionSurveyRecord.service_result["resolved"].astext == "true")
            if "unresolved" in resolved:
                resolved_clauses.append(SatisfactionSurveyRecord.service_result["resolved"].astext == "false")
            if resolved_clauses:
                filters.append(or_(*resolved_clauses))

        if service_options:
            filters.append(SatisfactionSurveyRecord.service_result["option_key"].astext.in_(service_options))
        if product_options:
            filters.append(SatisfactionSurveyRecord.product_result["option_key"].astext.in_(product_options))
        if service_labels:
            filters.append(
                or_(*[
                    SatisfactionSurveyRecord.service_result["labels"].contains([label])
                    for label in service_labels
                ])
            )
        if product_labels:
            filters.append(
                or_(*[
                    SatisfactionSurveyRecord.product_result["labels"].contains([label])
                    for label in product_labels
                ])
            )

        return filters
