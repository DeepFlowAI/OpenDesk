"""
Pydantic schemas for end-user bulk import.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.user import CustomFieldValue


class UserImportColumnMapping(BaseModel):
    file_header: str
    field_key: str | None = None
    field_id: int | None = None
    field_name: str | None = None
    field_type: str | None = None
    status: str
    message: str | None = None


class UserImportRowError(BaseModel):
    row_number: int
    identifier: str | None = None
    field: str
    reason: str
    raw_values: list[str] = Field(default_factory=list)


class UserImportPreviewSummary(BaseModel):
    filename: str
    total_rows: int
    importable_rows: int
    blocked_rows: int
    unsupported_columns: int


class UserImportPreviewResponse(BaseModel):
    preview_token: str
    summary: UserImportPreviewSummary
    file_headers: list[str] = Field(default_factory=list)
    column_mappings: list[UserImportColumnMapping]
    errors: list[UserImportRowError]
    has_more_errors: bool = False


class UserImportExecuteRequest(BaseModel):
    preview_token: str = Field(..., min_length=8, max_length=128)


class UserImportExecuteSummary(BaseModel):
    total_rows: int
    created: int
    failed: int
    skipped: int


class UserImportExecuteResponse(BaseModel):
    summary: UserImportExecuteSummary
    errors: list[UserImportRowError] = Field(default_factory=list)


class UserImportErrorReportRow(BaseModel):
    row_number: int
    values: list[str] = Field(default_factory=list)
    error_reason: str


class UserImportErrorReportRequest(BaseModel):
    headers: list[str] = Field(default_factory=list)
    rows: list[UserImportErrorReportRow] = Field(default_factory=list)


class ParsedImportUser(BaseModel):
    row_number: int
    name: str
    email: str | None = None
    phone: str | None = None
    web_id: str | None = None
    gender: str | None = None
    level: str | None = None
    address: str | None = None
    remark: str | None = None
    organization_id: int | None = None
    custom_fields: dict[str, CustomFieldValue] = Field(default_factory=dict)
    raw_values: list[str] = Field(default_factory=list)
