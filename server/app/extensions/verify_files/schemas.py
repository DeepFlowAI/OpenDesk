"""
Verify file schemas — Tenant Platform domain-verification file contract.
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# A plain `.txt` file name with no path separators, e.g. XFu51qFh2n.txt
FILENAME_PATTERN = r"^[A-Za-z0-9_-]{1,60}\.txt$"


class VerifyFileCreate(BaseModel):
    filename: str = Field(..., min_length=5, max_length=64, pattern=FILENAME_PATTERN)
    content: str = Field(..., min_length=1, max_length=8192)
    remark: str | None = Field(default=None, max_length=256)


class VerifyFileUpdate(BaseModel):
    content: str | None = Field(default=None, min_length=1, max_length=8192)
    remark: str | None = Field(default=None, max_length=256)


class VerifyFileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    content: str
    remark: str | None = None
    # Public access path relative to the deployment domain, e.g. "/XFu51qFh2n.txt"
    url: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class VerifyFileListResponse(BaseModel):
    items: list[VerifyFileResponse]
    total: int
    page: int
    per_page: int
    pages: int
