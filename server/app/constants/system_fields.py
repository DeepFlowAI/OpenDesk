"""
Hardcoded system field definitions shared by all tenants.

System fields are NOT stored in fd_field_definitions.  Only per-tenant
overrides (show_in_workspace, sort_order, status) live in the
fd_system_field_overrides table.

To add / rename / remove a system field, edit THIS file — no SQL needed.
"""

from __future__ import annotations
from dataclasses import dataclass, field


@dataclass(frozen=True)
class SystemFieldDef:
    key: str
    name_zh: str
    name_en: str
    field_type: str
    type_config: dict = field(default_factory=dict)
    description: str | None = None
    help_text: str | None = None
    default_show_in_workspace: bool = True
    default_sort_order: int = 0


# ── User domain ──

SYSTEM_USER_FIELDS: tuple[SystemFieldDef, ...] = (
    SystemFieldDef(
        key="public_id",
        name_zh="用户 ID",
        name_en="User ID",
        field_type="single_line_text",
        type_config={"readonly": True, "max_length": 64},
        description="OpenDesk 生成的终端用户公开标识",
        help_text="用于分享链接、对外接口和排障检索；不可编辑",
        default_sort_order=0,
    ),
    SystemFieldDef(
        key="nickname",
        name_zh="昵称",
        name_en="Nickname",
        field_type="single_line_text",
        type_config={"max_length": 64},
        default_sort_order=1,
    ),
    SystemFieldDef(
        key="phone",
        name_zh="手机号",
        name_en="Phone",
        field_type="phone",
        type_config={"max_length": 32},
        default_sort_order=2,
    ),
    SystemFieldDef(
        key="email",
        name_zh="邮箱",
        name_en="Email",
        field_type="email",
        type_config={"max_length": 254},
        default_sort_order=3,
    ),
    SystemFieldDef(
        key="gender",
        name_zh="性别",
        name_en="Gender",
        field_type="single_select",
        type_config={
            "options": [
                {"label": "男", "value": "male"},
                {"label": "女", "value": "female"},
                {"label": "未知", "value": "unknown"},
            ],
        },
        default_sort_order=4,
    ),
    SystemFieldDef(
        key="address",
        name_zh="地址",
        name_en="Address",
        field_type="single_line_text",
        type_config={"max_length": 256},
        default_show_in_workspace=False,
        default_sort_order=5,
    ),
    SystemFieldDef(
        key="remark",
        name_zh="备注",
        name_en="Remark",
        field_type="multi_line_text",
        type_config={"max_length": 2000},
        default_show_in_workspace=False,
        default_sort_order=6,
    ),
    SystemFieldDef(
        key="organization_id",
        name_zh="组织",
        name_en="Organization",
        field_type="organization_select",
        type_config={
            "entity": "organization",
            "multiple": False,
            "search_placeholder_zh": "搜索组织名称或描述…",
            "search_placeholder_en": "Search by name or description…",
        },
        description="终端用户关联的组织",
        help_text="选择该用户所属组织（可空）",
        default_sort_order=7,
    ),
    SystemFieldDef(
        key="created_by",
        name_zh="创建人",
        name_en="Created By",
        field_type="single_line_text",
        type_config={"readonly": True, "value_kind": "actor"},
        default_show_in_workspace=False,
        default_sort_order=8,
    ),
    SystemFieldDef(
        key="updated_by",
        name_zh="更新人",
        name_en="Updated By",
        field_type="single_line_text",
        type_config={"readonly": True, "value_kind": "actor"},
        default_show_in_workspace=False,
        default_sort_order=9,
    ),
)

# ── Organization domain ──

SYSTEM_ORG_FIELDS: tuple[SystemFieldDef, ...] = (
    SystemFieldDef(
        key="public_id",
        name_zh="组织 ID",
        name_en="Organization ID",
        field_type="single_line_text",
        type_config={"readonly": True, "max_length": 64},
        description="OpenDesk 生成的组织公开标识",
        help_text="用于组织链接、对外接口和排障检索；不可编辑",
        default_sort_order=0,
    ),
    SystemFieldDef(
        key="name",
        name_zh="名称",
        name_en="Name",
        field_type="single_line_text",
        type_config={"max_length": 128},
        default_sort_order=1,
    ),
    SystemFieldDef(
        key="description",
        name_zh="描述",
        name_en="Description",
        field_type="multi_line_text",
        type_config={"max_length": 2000},
        default_sort_order=2,
    ),
    SystemFieldDef(
        key="created_by",
        name_zh="创建人",
        name_en="Created By",
        field_type="single_line_text",
        type_config={"readonly": True, "value_kind": "actor"},
        default_show_in_workspace=False,
        default_sort_order=3,
    ),
    SystemFieldDef(
        key="updated_by",
        name_zh="更新人",
        name_en="Updated By",
        field_type="single_line_text",
        type_config={"readonly": True, "value_kind": "actor"},
        default_show_in_workspace=False,
        default_sort_order=4,
    ),
)

# ── Ticket domain (system fields for ticket forms) ──

SYSTEM_TICKET_FIELDS: tuple[SystemFieldDef, ...] = (
    SystemFieldDef(
        key="ticket_number",
        name_zh="编号",
        name_en="Ticket Number",
        field_type="single_line_text",
        type_config={"max_length": 64, "auto_generate": True},
        default_sort_order=1,
    ),
    SystemFieldDef(
        key="title",
        name_zh="标题",
        name_en="Title",
        field_type="single_line_text",
        type_config={"max_length": 256},
        default_sort_order=2,
    ),
    SystemFieldDef(
        key="description",
        name_zh="描述",
        name_en="Description",
        field_type="rich_text",
        type_config={"max_length": 5000, "rich_format": "html"},
        default_sort_order=3,
    ),
    SystemFieldDef(
        key="status",
        name_zh="状态",
        name_en="Status",
        field_type="single_select",
        type_config={
            "options": [
                {
                    "label": "待处理",
                    "label_en": "Open",
                    "value": "open",
                    "color": "#FEF3C7",
                },
                {
                    "label": "处理中",
                    "label_en": "In Progress",
                    "value": "in_progress",
                    "color": "#E0E7FF",
                },
                {
                    "label": "已解决",
                    "label_en": "Resolved",
                    "value": "resolved",
                    "color": "#DCFCE7",
                },
                {
                    "label": "已关闭",
                    "label_en": "Closed",
                    "value": "closed",
                    "color": "#E2E8F0",
                },
            ],
        },
        default_sort_order=4,
    ),
    SystemFieldDef(
        key="priority",
        name_zh="优先级",
        name_en="Priority",
        field_type="single_select",
        type_config={
            "options": [
                {
                    "label": "紧急",
                    "label_en": "Urgent",
                    "value": "urgent",
                    "color": "#FEE2E2",
                },
                {
                    "label": "高",
                    "label_en": "High",
                    "value": "high",
                    "color": "#FFEDD5",
                },
                {
                    "label": "中",
                    "label_en": "Medium",
                    "value": "medium",
                    "color": "#DBEAFE",
                },
                {
                    "label": "低",
                    "label_en": "Low",
                    "value": "low",
                    "color": "#F1F5F9",
                },
            ],
        },
        default_sort_order=5,
    ),
    SystemFieldDef(
        key="assignee_group",
        name_zh="负责组",
        name_en="Assignee Group",
        field_type="group_select",
        type_config={
            "entity": "employee_group",
            "multiple": False,
            "search_placeholder_zh": "搜索负责组…",
            "search_placeholder_en": "Search groups...",
        },
        description="工单负责组",
        help_text="选择当前工单所属的负责组",
        default_sort_order=6,
    ),
    SystemFieldDef(
        key="assignee",
        name_zh="负责人",
        name_en="Assignee",
        field_type="employee_select",
        type_config={
            "entity": "employee",
            "multiple": False,
            "filter_by_group": True,
            "search_placeholder_zh": "搜索员工…",
            "search_placeholder_en": "Search employees...",
        },
        description="工单负责人",
        help_text="选择实际处理当前工单的客服",
        default_sort_order=7,
    ),
    SystemFieldDef(
        key="user_id",
        name_zh="关联用户",
        name_en="Linked User",
        field_type="user_select",
        type_config={
            "entity": "user",
            "multiple": False,
            "search_placeholder_zh": "搜索昵称、手机、邮箱...",
            "search_placeholder_en": "Search users...",
        },
        description="工单关联的终端用户",
        help_text="选择当前工单对应的终端用户",
        default_sort_order=8,
    ),
    SystemFieldDef(
        key="conversation_id",
        name_zh="关联会话",
        name_en="Linked Session",
        field_type="single_line_text",
        type_config={"max_length": 64, "readonly": True},
        description="工单关联的在线客服会话",
        help_text="基于会话创建工单时自动关联",
        default_sort_order=9,
    ),
    SystemFieldDef(
        key="created_by",
        name_zh="创建人",
        name_en="Created By",
        field_type="single_line_text",
        type_config={"readonly": True, "value_kind": "actor"},
        default_show_in_workspace=False,
        default_sort_order=10,
    ),
    SystemFieldDef(
        key="updated_by",
        name_zh="更新人",
        name_en="Updated By",
        field_type="single_line_text",
        type_config={"readonly": True, "value_kind": "actor"},
        default_show_in_workspace=False,
        default_sort_order=11,
    ),
)

# ── Registry keyed by domain ──

SYSTEM_FIELDS_BY_DOMAIN: dict[str, tuple[SystemFieldDef, ...]] = {
    "user": SYSTEM_USER_FIELDS,
    "organization": SYSTEM_ORG_FIELDS,
    "ticket": SYSTEM_TICKET_FIELDS,
}


def get_system_fields(domain: str) -> tuple[SystemFieldDef, ...]:
    return SYSTEM_FIELDS_BY_DOMAIN.get(domain, ())


def get_system_field(domain: str, key: str) -> SystemFieldDef | None:
    for f in get_system_fields(domain):
        if f.key == key:
            return f
    return None
