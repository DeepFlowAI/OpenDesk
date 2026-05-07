"""
Tenant initialization — seed default data when a new tenant is created.

Creates default form layouts so the tenant has a working ticket system
out of the box.
"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.fd_form_layout_repository import FdFormLayoutRepository


# ── Default form layout definitions ──

def _new_ticket_layout() -> dict:
    """Layout for creating a new ticket (scene=new_ticket)."""
    return {
        "name": "新建工单",
        "scene": "new_ticket",
        "columns_per_row": 2,
        "label_position": "top",
        "tabs": [
            {
                "name": "基本信息",
                "sort_order": 0,
                "sections": [
                    {
                        "name": "工单信息",
                        "sort_order": 0,
                        "fields": [
                            {"field_key": "title", "field_source": "ticket", "default_state": "required", "column_span": 2, "sort_order": 0},
                            {"field_key": "user_id", "field_source": "ticket", "default_state": "optional", "column_span": 1, "sort_order": 1},
                            {"field_key": "priority", "field_source": "ticket", "default_state": "required", "column_span": 1, "sort_order": 2},
                            {"field_key": "assignee_group", "field_source": "ticket", "default_state": "optional", "column_span": 1, "sort_order": 3},
                            {"field_key": "assignee", "field_source": "ticket", "default_state": "optional", "column_span": 1, "sort_order": 4},
                            {"field_key": "description", "field_source": "ticket", "default_state": "optional", "column_span": 2, "sort_order": 5},
                        ],
                    },
                ],
            },
        ],
    }


def _ticket_detail_layout() -> dict:
    """Layout for viewing/editing ticket details (scene=ticket_detail)."""
    return {
        "name": "工单详情",
        "scene": "ticket_detail",
        "columns_per_row": 2,
        "label_position": "top",
        "tabs": [
            {
                "name": "基本信息",
                "sort_order": 0,
                "sections": [
                    {
                        "name": "工单信息",
                        "sort_order": 0,
                        "fields": [
                            {"field_key": "ticket_number", "field_source": "ticket", "default_state": "readonly", "column_span": 1, "sort_order": 0},
                            {"field_key": "title", "field_source": "ticket", "default_state": "required", "column_span": 1, "sort_order": 1},
                            {"field_key": "user_id", "field_source": "ticket", "default_state": "optional", "column_span": 1, "sort_order": 2},
                            {"field_key": "status", "field_source": "ticket", "default_state": "required", "column_span": 1, "sort_order": 3},
                            {"field_key": "priority", "field_source": "ticket", "default_state": "required", "column_span": 1, "sort_order": 4},
                            {"field_key": "assignee_group", "field_source": "ticket", "default_state": "optional", "column_span": 1, "sort_order": 5},
                            {"field_key": "assignee", "field_source": "ticket", "default_state": "optional", "column_span": 1, "sort_order": 6},
                            {"field_key": "description", "field_source": "ticket", "default_state": "optional", "column_span": 2, "sort_order": 7},
                        ],
                    },
                    {
                        "name": "时间信息",
                        "sort_order": 1,
                        "fields": [
                            {"field_key": "created_at", "field_source": "ticket_metadata", "default_state": "readonly", "column_span": 1, "sort_order": 0},
                            {"field_key": "updated_at", "field_source": "ticket_metadata", "default_state": "readonly", "column_span": 1, "sort_order": 1},
                        ],
                    },
                ],
            },
        ],
    }


DEFAULT_LAYOUTS = [_new_ticket_layout, _ticket_detail_layout]


async def init_tenant_data(db: AsyncSession, tenant_pk: int) -> None:
    """Seed all default data for a newly created tenant.

    Called from TenantService.create() after the tenant and admin
    employee have been persisted (but before the final commit).
    """
    for layout_fn in DEFAULT_LAYOUTS:
        await FdFormLayoutRepository.create(db, tenant_pk, layout_fn())
