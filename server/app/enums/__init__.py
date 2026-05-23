"""
Shared enum definitions for the application.
"""
import enum


class ConversationStatus(str, enum.Enum):
    QUEUED = "queued"
    ACTIVE = "active"
    CLOSED = "closed"


class MessageSenderType(str, enum.Enum):
    VISITOR = "visitor"
    AGENT = "agent"
    SYSTEM = "system"


class MessageContentType(str, enum.Enum):
    TEXT = "text"
    IMAGE = "image"
    FILE = "file"
    SYSTEM = "system"
    WELCOME = "welcome"
    SATISFACTION_EVENT = "satisfaction_event"


class AgentOnlineStatus(str, enum.Enum):
    ONLINE = "online"
    BUSY = "busy"
    OFFLINE = "offline"


# ── Dynamic Field System enums ──


class FieldDomain(str, enum.Enum):
    USER = "user"
    ORGANIZATION = "organization"
    SHARED_POOL = "shared_pool"


class FieldType(str, enum.Enum):
    SINGLE_LINE_TEXT = "single_line_text"
    MULTI_LINE_TEXT = "multi_line_text"
    NUMBER = "number"
    DATE = "date"
    TIME = "time"
    DATETIME = "datetime"
    SINGLE_SELECT = "single_select"
    MULTI_SELECT = "multi_select"
    SINGLE_SELECT_TREE = "single_select_tree"
    MULTI_SELECT_TREE = "multi_select_tree"
    EMAIL = "email"
    PHONE = "phone"
    URL = "url"
    FILE = "file"
    RICH_TEXT = "rich_text"
    USER_SELECT = "user_select"
    ORGANIZATION_SELECT = "organization_select"
    EMPLOYEE_SELECT = "employee_select"
    GROUP_SELECT = "group_select"


class FieldSource(str, enum.Enum):
    SYSTEM = "system"
    CUSTOM = "custom"


class ApplicableModule(str, enum.Enum):
    TICKET = "ticket"
    SESSION_SUMMARY = "session_summary"
    CALL_SUMMARY = "call_summary"


class FieldDefaultState(str, enum.Enum):
    HIDDEN = "hidden"
    REQUIRED = "required"
    OPTIONAL = "optional"
    READONLY = "readonly"
