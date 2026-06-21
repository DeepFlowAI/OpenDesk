"""
Pydantic schemas for organization bulk import.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.organization import CustomFieldValue


class OrganizationImportColumnMapping(BaseModel):
    file_header: str
    field_key: str | None = None
    field_id: int | None = None
    field_name: str | None = None
    field_type: str | None = None
    status: str
    message: str | None = None


class OrganizationImportRowError(BaseModel):
    row_number: int
    identifier: str | None = None
    field: str
    reason: str
    raw_values: list[str] = Field(default_factory=list)


class OrganizationImportPreviewSummary(BaseModel):
    filename: str
    total_rows: int
    importable_rows: int
    blocked_rows: int
    unsupported_columns: int


class OrganizationImportPreviewResponse(BaseModel):
    preview_token: str
    summary: OrganizationImportPreviewSummary
    file_headers: list[str] = Field(default_factory=list)
    column_mappings: list[OrganizationImportColumnMapping]
    errors: list[OrganizationImportRowError]
    has_more_errors: bool = False


class OrganizationImportExecuteRequest(BaseModel):
    preview_token: str = Field(..., min_length=8, max_length=128)


class OrganizationImportExecuteSummary(BaseModel):
    total_rows: int
    created: int
    failed: int
    skipped: int


class OrganizationImportExecuteResponse(BaseModel):
    summary: OrganizationImportExecuteSummary
    errors: list[OrganizationImportRowError] = Field(default_factory=list)


class OrganizationImportErrorReportRow(BaseModel):
    row_number: int
    values: list[str] = Field(default_factory=list)
    error_reason: str


class OrganizationImportErrorReportRequest(BaseModel):
    headers: list[str] = Field(default_factory=list)
    rows: list[OrganizationImportErrorReportRow] = Field(default_factory=list)


class ParsedImportOrganization(BaseModel):
    row_number: int
    name: str
    description: str | None = None
    custom_fields: dict[str, CustomFieldValue] = Field(default_factory=dict)
    raw_values: list[str] = Field(default_factory=list)
