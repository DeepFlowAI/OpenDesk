"""
Knowledge import/export schemas.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

KnowledgeImportAction = Literal["create", "update", "skip", "error"]


class KnowledgeImportSummary(BaseModel):
    filename: str
    total_rows: int
    create_directories: int
    create_documents: int
    update_documents: int
    skipped_rows: int
    error_rows: int


class KnowledgeImportRowResult(BaseModel):
    row_number: int
    action: KnowledgeImportAction
    id: int | None = None
    directory_path: str | None = None
    title: str | None = None
    message: str | None = None
    errors: list[str] = Field(default_factory=list)
    raw_values: list[str] = Field(default_factory=list)


class KnowledgeImportPreviewResponse(BaseModel):
    preview_token: str
    summary: KnowledgeImportSummary
    file_headers: list[str] = Field(default_factory=list)
    rows: list[KnowledgeImportRowResult] = Field(default_factory=list)
    has_errors: bool = False


class KnowledgeImportExecuteRequest(BaseModel):
    preview_token: str = Field(..., min_length=8, max_length=128)


class KnowledgeImportExecuteResponse(BaseModel):
    summary: KnowledgeImportSummary
    rows: list[KnowledgeImportRowResult] = Field(default_factory=list)
    has_errors: bool = False
