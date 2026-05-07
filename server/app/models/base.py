from datetime import date, datetime

from sqlalchemy import Date, DateTime, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class MetadataMixin(TimestampMixin):
    """
    Metadata columns always exposed in list / detail views.
    Currently inherits created_at & updated_at from TimestampMixin;
    extend here when new metadata columns are needed (e.g. sort_key).
    """
    pass


class AuditActorMixin:
    """
    Stores extensible creator/updater references.

    actor_type is intentionally not constrained to an FK-backed enum so future
    actors such as end users or API clients can be represented without schema
    changes.
    """

    created_by_actor_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_by_actor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by_actor_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    updated_by_actor_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    updated_by_actor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_by_actor_name: Mapped[str | None] = mapped_column(String(128), nullable=True)

    @staticmethod
    def _build_actor_ref(
        actor_type: str | None,
        actor_id: int | None,
        actor_name: str | None,
    ) -> dict | None:
        if actor_type is None and actor_id is None and actor_name is None:
            return None
        return {
            "actor_type": actor_type,
            "actor_id": actor_id,
            "actor_name": actor_name,
        }

    @property
    def created_by(self) -> dict | None:
        return self._build_actor_ref(
            self.created_by_actor_type,
            self.created_by_actor_id,
            self.created_by_actor_name,
        )

    @property
    def updated_by(self) -> dict | None:
        return self._build_actor_ref(
            self.updated_by_actor_type,
            self.updated_by_actor_id,
            self.updated_by_actor_name,
        )


class SlotColumnMixin:
    """
    Pre-allocated slot columns for dynamic custom field values.
    Business entity models inherit this mixin to gain identical
    extensible columns. Slot allocation is managed by
    fd_field_definitions.slot_column.
    """

    # ── str: String(2048) ×20 ──
    str_1:  Mapped[str | None] = mapped_column(String(2048), nullable=True)
    str_2:  Mapped[str | None] = mapped_column(String(2048), nullable=True)
    str_3:  Mapped[str | None] = mapped_column(String(2048), nullable=True)
    str_4:  Mapped[str | None] = mapped_column(String(2048), nullable=True)
    str_5:  Mapped[str | None] = mapped_column(String(2048), nullable=True)
    str_6:  Mapped[str | None] = mapped_column(String(2048), nullable=True)
    str_7:  Mapped[str | None] = mapped_column(String(2048), nullable=True)
    str_8:  Mapped[str | None] = mapped_column(String(2048), nullable=True)
    str_9:  Mapped[str | None] = mapped_column(String(2048), nullable=True)
    str_10: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    str_11: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    str_12: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    str_13: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    str_14: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    str_15: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    str_16: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    str_17: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    str_18: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    str_19: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    str_20: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    # ── text: Text ×5 ──
    text_1: Mapped[str | None] = mapped_column(Text, nullable=True)
    text_2: Mapped[str | None] = mapped_column(Text, nullable=True)
    text_3: Mapped[str | None] = mapped_column(Text, nullable=True)
    text_4: Mapped[str | None] = mapped_column(Text, nullable=True)
    text_5: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── num: Numeric(20,10) ×10 ──
    num_1:  Mapped[float | None] = mapped_column(Numeric(20, 10), nullable=True)
    num_2:  Mapped[float | None] = mapped_column(Numeric(20, 10), nullable=True)
    num_3:  Mapped[float | None] = mapped_column(Numeric(20, 10), nullable=True)
    num_4:  Mapped[float | None] = mapped_column(Numeric(20, 10), nullable=True)
    num_5:  Mapped[float | None] = mapped_column(Numeric(20, 10), nullable=True)
    num_6:  Mapped[float | None] = mapped_column(Numeric(20, 10), nullable=True)
    num_7:  Mapped[float | None] = mapped_column(Numeric(20, 10), nullable=True)
    num_8:  Mapped[float | None] = mapped_column(Numeric(20, 10), nullable=True)
    num_9:  Mapped[float | None] = mapped_column(Numeric(20, 10), nullable=True)
    num_10: Mapped[float | None] = mapped_column(Numeric(20, 10), nullable=True)

    # ── date: Date ×5 ──
    date_1: Mapped[date | None] = mapped_column(Date, nullable=True)
    date_2: Mapped[date | None] = mapped_column(Date, nullable=True)
    date_3: Mapped[date | None] = mapped_column(Date, nullable=True)
    date_4: Mapped[date | None] = mapped_column(Date, nullable=True)
    date_5: Mapped[date | None] = mapped_column(Date, nullable=True)

    # ── datetime: DateTime(timezone=True) ×5 ──
    datetime_1: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    datetime_2: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    datetime_3: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    datetime_4: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    datetime_5: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # ── json: JSONB ×10 ──
    json_1:  Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    json_2:  Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    json_3:  Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    json_4:  Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    json_5:  Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    json_6:  Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    json_7:  Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    json_8:  Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    json_9:  Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    json_10: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
