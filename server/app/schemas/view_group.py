"""
Shared Pydantic schemas for view-based group aggregation.

Used by ticket / user / organization workspaces to render group bars and
filter the list by a chosen group value.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ViewGroupConditionItem(BaseModel):
    """Loose condition item shape; mirrors xxx_view.ConditionItem but stays
    domain-agnostic so this schema can be reused across all three domains.
    """

    field_id: int | None = None
    field_key: str | None = None
    operator: str
    value: Any = None


class ViewGroupRequest(BaseModel):
    """POST body for view group aggregation.

    Mirrors the *filter* portion of xxxQueryRequest so the group counts use
    the exact same filter set as the list view (search + temp filters).
    The view's own conditions are always applied server-side from the view
    record itself; clients never pass them explicitly.
    """

    search: str | None = Field(default=None, max_length=256)
    temp_conditions: list[ViewGroupConditionItem] = Field(default_factory=list)
    temp_condition_logic: str = Field(default="and", max_length=8)


class ViewGroupItem(BaseModel):
    value: str | None
    count: int


class ViewGroupFieldInfo(BaseModel):
    id: int
    field_type: str
    name: str


class ViewGroupResponse(BaseModel):
    """Response payload for view group aggregation.

    `group_field` is None when the view has no group_field_id configured
    (or the field has been removed). In that case `items` is empty and the
    workspace UI should hide the group bar.
    """

    group_field: ViewGroupFieldInfo | None = None
    items: list[ViewGroupItem] = Field(default_factory=list)
    total: int = 0
