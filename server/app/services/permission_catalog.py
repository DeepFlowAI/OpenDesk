"""
Permission catalog and built-in role presets.
"""
from copy import deepcopy

DATA_SCOPE_KEYS = {"ticket", "session_record", "call_record"}
DATA_SCOPE_VALUES = {"all", "group", "self"}
SYSTEM_ROLE_KEYS = {"admin", "agent"}
DATA_SCOPE_PRIORITY = {"self": 1, "group": 2, "all": 3}

PERMISSION_TREE: list[dict] = [
    {
        "key": "workspace",
        "name": "工作台",
        "name_en": "Workspace",
        "modules": [
            {
                "key": "call",
                "name": "呼叫中心",
                "name_en": "Call Center",
                "permissions": [
                    {"key": "call.workspace.use", "name": "启用呼叫中心工作台", "name_en": "Use call workspace", "type": "switch"},
                    {"key": "call.record.view", "name": "查看通话记录", "name_en": "View call records", "type": "menu", "requires": "call.workspace.use", "data_scope_resource": "call_record"},
                    {"key": "call.record.export", "name": "导出通话记录", "name_en": "Export call records", "type": "action", "requires": "call.record.view"},
                    {"key": "call.monitor.view", "name": "查看呼叫监控", "name_en": "View call monitor", "type": "menu", "requires": "call.workspace.use"},
                    {"key": "call.report.view", "name": "查看通话报表", "name_en": "View call reports", "type": "menu", "requires": "call.workspace.use"},
                    {"key": "call.report.export", "name": "导出通话报表", "name_en": "Export call reports", "type": "action", "requires": "call.report.view"},
                ],
            },
            {
                "key": "chat",
                "name": "在线客服",
                "name_en": "Online Service",
                "permissions": [
                    {"key": "chat.workspace.use", "name": "启用在线客服工作台", "name_en": "Use chat workspace", "type": "switch"},
                    {"key": "chat.conversation.transfer", "name": "会话转接", "name_en": "Transfer conversations", "type": "action", "requires": "chat.workspace.use"},
                    {"key": "chat.session_record.view", "name": "查看会话记录", "name_en": "View session records", "type": "menu", "requires": "chat.workspace.use", "data_scope_resource": "session_record"},
                    {"key": "chat.session_record.export", "name": "导出会话记录", "name_en": "Export session records", "type": "action", "requires": "chat.session_record.view"},
                    {"key": "chat.online_monitor.view", "name": "查看在线监控", "name_en": "View online monitor", "type": "menu", "requires": "chat.workspace.use"},
                    {"key": "chat.session_report.view", "name": "查看会话报表", "name_en": "View session reports", "type": "menu", "requires": "chat.workspace.use"},
                    {"key": "chat.session_report.export", "name": "导出会话报表", "name_en": "Export session reports", "type": "action", "requires": "chat.session_report.view"},
                ],
            },
            {
                "key": "crm",
                "name": "用户与组织",
                "name_en": "Users & Organizations",
                "permissions": [
                    {"key": "crm.workspace.user.view", "name": "查看用户", "name_en": "View users", "type": "menu"},
                    {"key": "crm.workspace.user.create", "name": "新建用户", "name_en": "Create users", "type": "action", "requires": "crm.workspace.user.view"},
                    {"key": "crm.workspace.user.edit", "name": "编辑用户", "name_en": "Edit users", "type": "action", "requires": "crm.workspace.user.view"},
                    {"key": "crm.workspace.user.delete", "name": "删除用户", "name_en": "Delete users", "type": "action", "requires": "crm.workspace.user.view"},
                    {"key": "crm.workspace.org.view", "name": "查看组织", "name_en": "View organizations", "type": "menu"},
                    {"key": "crm.workspace.org.create", "name": "新建组织", "name_en": "Create organizations", "type": "action", "requires": "crm.workspace.org.view"},
                    {"key": "crm.workspace.org.edit", "name": "编辑组织", "name_en": "Edit organizations", "type": "action", "requires": "crm.workspace.org.view"},
                    {"key": "crm.workspace.org.delete", "name": "删除组织", "name_en": "Delete organizations", "type": "action", "requires": "crm.workspace.org.view"},
                ],
            },
            {
                "key": "ticket",
                "name": "工单",
                "name_en": "Tickets",
                "permissions": [
                    {"key": "ticket.workspace.view", "name": "查看工单", "name_en": "View tickets", "type": "menu", "data_scope_resource": "ticket"},
                    {"key": "ticket.workspace.create", "name": "新建工单", "name_en": "Create tickets", "type": "action", "requires": "ticket.workspace.view"},
                    {"key": "ticket.workspace.edit", "name": "编辑工单", "name_en": "Edit tickets", "type": "action", "requires": "ticket.workspace.view"},
                    {"key": "ticket.workspace.delete", "name": "删除工单", "name_en": "Delete tickets", "type": "action", "requires": "ticket.workspace.view"},
                    {"key": "ticket.workspace.comment", "name": "工单评论", "name_en": "Comment on tickets", "type": "action", "requires": "ticket.workspace.view"},
                    {"key": "ticket.workspace.export", "name": "导出工单", "name_en": "Export tickets", "type": "action", "requires": "ticket.workspace.view"},
                ],
            },
        ],
    },
    {
        "key": "admin",
        "name": "管理后台",
        "name_en": "Admin",
        "modules": [
            {
                "key": "admin_access",
                "name": "入口总开关",
                "name_en": "Access",
                "permissions": [
                    {"key": "admin.access", "name": "启用管理后台", "name_en": "Use admin console", "type": "switch"},
                ],
            },
            {
                "key": "organization",
                "name": "组织架构",
                "name_en": "Organization",
                "permissions": [
                    {"key": "org.employee.view", "name": "查看员工", "name_en": "View employees", "type": "menu", "requires": "admin.access"},
                    {"key": "org.employee.create", "name": "新建员工", "name_en": "Create employees", "type": "action", "requires": "org.employee.view"},
                    {"key": "org.employee.edit", "name": "编辑员工", "name_en": "Edit employees", "type": "action", "requires": "org.employee.view"},
                    {"key": "org.employee.delete", "name": "删除员工", "name_en": "Delete employees", "type": "action", "requires": "org.employee.view"},
                    {"key": "org.group.manage", "name": "管理员工组", "name_en": "Manage employee groups", "type": "manage", "requires": "admin.access"},
                    {"key": "org.queue.manage", "name": "管理队列配置", "name_en": "Manage queue settings", "type": "manage", "requires": "admin.access"},
                    {"key": "org.role.manage", "name": "管理角色", "name_en": "Manage roles", "type": "manage", "requires": "admin.access"},
                ],
            },
            {
                "key": "call_admin",
                "name": "呼叫中心",
                "name_en": "Call Center",
                "permissions": [
                    {"key": "call.admin.flow.manage", "name": "管理流程设计", "name_en": "Manage flows", "type": "manage", "requires": "admin.access"},
                    {"key": "call.admin.number.manage", "name": "管理号码", "name_en": "Manage phone numbers", "type": "manage", "requires": "admin.access"},
                    {"key": "call.admin.summary_config.manage", "name": "管理通话纪要配置", "name_en": "Manage call summaries", "type": "manage", "requires": "admin.access"},
                ],
            },
            {
                "key": "chat_admin",
                "name": "在线客服",
                "name_en": "Online Service",
                "permissions": [
                    {"key": "chat.admin.settings.manage", "name": "管理会话设置", "name_en": "Manage conversation settings", "type": "manage", "requires": "admin.access"},
                    {"key": "chat.admin.channel.manage", "name": "管理渠道", "name_en": "Manage channels", "type": "manage", "requires": "admin.access"},
                    {"key": "chat.admin.routing.manage", "name": "管理对话路由", "name_en": "Manage session routing", "type": "manage", "requires": "admin.access"},
                    {"key": "chat.admin.summary_config.manage", "name": "管理会话纪要配置", "name_en": "Manage session summaries", "type": "manage", "requires": "admin.access"},
                    {"key": "chat.admin.satisfaction.manage", "name": "管理满意度配置", "name_en": "Manage satisfaction", "type": "manage", "requires": "admin.access"},
                ],
            },
            {
                "key": "crm_admin",
                "name": "用户与组织",
                "name_en": "Users & Organizations",
                "permissions": [
                    {"key": "crm.admin.user_field.manage", "name": "管理用户字段", "name_en": "Manage user fields", "type": "manage", "requires": "admin.access"},
                    {"key": "crm.admin.org_field.manage", "name": "管理组织字段", "name_en": "Manage organization fields", "type": "manage", "requires": "admin.access"},
                    {"key": "crm.admin.user_view.manage", "name": "管理用户视图", "name_en": "Manage user views", "type": "manage", "requires": "admin.access"},
                    {"key": "crm.admin.org_view.manage", "name": "管理组织视图", "name_en": "Manage organization views", "type": "manage", "requires": "admin.access"},
                    {"key": "crm.admin.org_settings.manage", "name": "管理组织设置", "name_en": "Manage organization settings", "type": "manage", "requires": "admin.access"},
                ],
            },
            {
                "key": "ticket_admin",
                "name": "工单",
                "name_en": "Tickets",
                "permissions": [
                    {"key": "ticket.admin.layout.manage", "name": "管理表单布局", "name_en": "Manage form layouts", "type": "manage", "requires": "admin.access"},
                    {"key": "ticket.admin.shared_field.manage", "name": "管理共享字段", "name_en": "Manage shared fields", "type": "manage", "requires": "admin.access"},
                    {"key": "ticket.admin.view.manage", "name": "管理工单视图", "name_en": "Manage ticket views", "type": "manage", "requires": "admin.access"},
                    {"key": "ticket.admin.workflow.manage", "name": "管理工单工作流", "name_en": "Manage ticket workflows", "type": "manage", "requires": "admin.access"},
                ],
            },
            {
                "key": "settings",
                "name": "全局设置",
                "name_en": "Global Settings",
                "permissions": [
                    {"key": "settings.system.manage", "name": "管理系统设置", "name_en": "Manage system settings", "type": "manage", "requires": "admin.access"},
                    {"key": "settings.service_hours.manage", "name": "管理服务时间", "name_en": "Manage service hours", "type": "manage", "requires": "admin.access"},
                    {"key": "settings.open_agent.manage", "name": "管理 OpenAgent 配置", "name_en": "Manage OpenAgent", "type": "manage", "requires": "admin.access"},
                ],
            },
        ],
    },
]


def all_permission_keys() -> set[str]:
    keys: set[str] = set()
    for tab in PERMISSION_TREE:
        for module in tab["modules"]:
            for permission in module["permissions"]:
                keys.add(permission["key"])
    return keys


ALL_PERMISSION_KEYS = all_permission_keys()


def permission_requires_map() -> dict[str, str]:
    requires: dict[str, str] = {}
    for tab in PERMISSION_TREE:
        for module in tab["modules"]:
            for permission in module["permissions"]:
                parent_key = permission.get("requires")
                if parent_key:
                    requires[permission["key"]] = parent_key
    return requires


def permission_data_scope_resources() -> dict[str, str]:
    resources: dict[str, str] = {}
    for tab in PERMISSION_TREE:
        for module in tab["modules"]:
            for permission in module["permissions"]:
                resource = permission.get("data_scope_resource")
                if resource:
                    resources[permission["key"]] = resource
    return resources


PERMISSION_REQUIRES = permission_requires_map()
PERMISSION_DATA_SCOPE_RESOURCES = permission_data_scope_resources()

ADMIN_DATA_SCOPES = {key: "all" for key in DATA_SCOPE_KEYS}
AGENT_DATA_SCOPES = {key: "self" for key in DATA_SCOPE_KEYS}

AGENT_PERMISSION_KEYS = [
    "chat.workspace.use",
    "call.workspace.use",
    "ticket.workspace.view",
    "ticket.workspace.create",
    "ticket.workspace.edit",
    "ticket.workspace.comment",
    "crm.workspace.user.view",
    "crm.workspace.org.view",
    "chat.session_record.view",
    "call.record.view",
    "chat.conversation.transfer",
]

SYSTEM_ROLE_PRESETS = {
    "admin": {
        "name": "管理员",
        "description": "系统内置管理员角色",
        "permissions": sorted(ALL_PERMISSION_KEYS),
        "data_scopes": ADMIN_DATA_SCOPES,
    },
    "agent": {
        "name": "客服",
        "description": "系统内置客服角色",
        "permissions": AGENT_PERMISSION_KEYS,
        "data_scopes": AGENT_DATA_SCOPES,
    },
}


def permission_tree() -> list[dict]:
    return deepcopy(PERMISSION_TREE)


def normalize_permissions(values: list[str]) -> list[str]:
    return sorted(dict.fromkeys(values))


def normalize_data_scopes(values: dict[str, str]) -> dict[str, str]:
    return {key: values[key] for key in sorted(values.keys())}


def missing_required_permissions(values: list[str]) -> dict[str, str]:
    permission_set = set(values)
    missing: dict[str, str] = {}
    for permission in values:
        required = PERMISSION_REQUIRES.get(permission)
        if required and required not in permission_set:
            missing[permission] = required
    return missing


def filter_effective_permissions(values: list[str]) -> list[str]:
    effective = set(normalize_permissions(values))
    changed = True
    while changed:
        changed = False
        for permission in list(effective):
            required = PERMISSION_REQUIRES.get(permission)
            if required and required not in effective:
                effective.remove(permission)
                changed = True
    return sorted(effective)


def merge_data_scope(current: str | None, candidate: str | None) -> str | None:
    if candidate not in DATA_SCOPE_VALUES:
        return current
    if current not in DATA_SCOPE_VALUES:
        return candidate
    return candidate if DATA_SCOPE_PRIORITY[candidate] > DATA_SCOPE_PRIORITY[current] else current
