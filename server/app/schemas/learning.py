"""
Learning center schemas: course admin APIs (course/section/material), upload
credentials and learner-side views.
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.base import PaginatedResponse


# ---------------------------------------------------------------------------
# Course
# ---------------------------------------------------------------------------


class LearningCourseCreate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=50)


class LearningCourseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=50)
    intro: str | None = Field(default=None, max_length=200)
    cover_url: str | None = Field(default=None, max_length=500)


class LearningCourseVisibilityUpdate(BaseModel):
    visibility: str = Field(pattern="^(all|assigned)$")


class LearningCourseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    cover_url: str | None = None
    intro: str | None = None
    status: str
    visibility: str
    created_by: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AdminCourseListItem(BaseModel):
    id: int
    name: str
    cover_url: str | None = None
    status: str
    visibility: str
    section_count: int
    material_count: int
    # None means "all employees" for visibility=all courses.
    learner_count: int | None = None
    completed_count: int
    updated_at: datetime | None = None


class AdminCourseListResponse(PaginatedResponse):
    items: list[AdminCourseListItem]


class CoverUploadResponse(BaseModel):
    url: str


# ---------------------------------------------------------------------------
# Section
# ---------------------------------------------------------------------------


class LearningSectionCreate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=30)


class LearningSectionUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=30)


class SectionOrderUpdate(BaseModel):
    ordered_ids: list[int] = Field(min_length=1)


class LearningSectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    course_id: int
    name: str
    sort_order: int
    created_at: datetime | None = None
    updated_at: datetime | None = None


# ---------------------------------------------------------------------------
# Material
# ---------------------------------------------------------------------------


class MaterialUploadCredentialRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    file_size: int = Field(gt=0)
    material_type: str = Field(pattern="^(video|audio|pdf|document)$")


class MaterialUploadCredentialResponse(BaseModel):
    channel: str  # "vod" | "oss"
    video_id: str | None = None
    upload_address: str | None = None
    upload_auth: str | None = None
    upload_url: str | None = None
    file_key: str | None = None


class LearningMaterialCreate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=50)
    type: str = Field(pattern="^(video|audio|pdf|document)$")
    vod_video_id: str | None = Field(default=None, max_length=128)
    file_key: str | None = Field(default=None, max_length=500)
    file_size: int | None = Field(default=None, gt=0)
    duration_seconds: int | None = Field(default=None, ge=0)


class LearningMaterialUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=50)


class MaterialOrderUpdate(BaseModel):
    ordered_ids: list[int] = Field(min_length=1)


class LearningMaterialResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    course_id: int
    section_id: int
    name: str
    type: str
    duration_seconds: int | None = None
    file_size: int | None = None
    transcode_status: str | None = None
    sort_order: int
    created_at: datetime | None = None
    updated_at: datetime | None = None


# ---------------------------------------------------------------------------
# Course detail tree
# ---------------------------------------------------------------------------


class LearningSectionWithMaterials(LearningSectionResponse):
    materials: list[LearningMaterialResponse] = []


class LearningCourseDetail(LearningCourseResponse):
    sections: list[LearningSectionWithMaterials] = []


class MessageResponse(BaseModel):
    message: str


# ---------------------------------------------------------------------------
# Assignments (admin)
# ---------------------------------------------------------------------------


class AssignmentTarget(BaseModel):
    target_type: str = Field(pattern="^(employee|group)$")
    target_id: int = Field(gt=0)


class AssignmentAddRequest(BaseModel):
    targets: list[AssignmentTarget] = Field(min_length=1, max_length=200)


class AssignmentAddResponse(BaseModel):
    added_count: int


class AssignmentItem(BaseModel):
    id: int
    target_type: str
    target_id: int
    name: str
    detail: str | int | None = None


class AssignmentListResponse(BaseModel):
    items: list[AssignmentItem]


class AssignableGroupItem(BaseModel):
    id: int
    name: str
    active_member_count: int
    added: bool


class AssignableGroupListResponse(BaseModel):
    items: list[AssignableGroupItem]


class AssignableEmployeeItem(BaseModel):
    id: int
    name: str
    group_names: list[str] = []
    assigned: bool = False
    covered: bool = False


class AssignableEmployeeListResponse(PaginatedResponse):
    items: list[AssignableEmployeeItem]


class LearnerItem(BaseModel):
    employee_id: int
    name: str
    group_names: list[str] = []
    direct_assigned: bool = False
    assigned_group_names: list[str] = []
    progress: int
    status: str  # not_started | in_progress | completed
    last_learn_at: datetime | None = None


class LearnerListResponse(PaginatedResponse):
    items: list[LearnerItem]


# ---------------------------------------------------------------------------
# Employee side ("my learning")
# ---------------------------------------------------------------------------


class MyCourseListItem(BaseModel):
    id: int
    name: str
    cover_url: str | None = None
    intro: str | None = None
    material_count: int
    completed_count: int
    progress: int
    status: str  # not_started | in_progress | completed
    updated_at: datetime | None = None


class MyCourseListResponse(PaginatedResponse):
    items: list[MyCourseListItem]


class MyMaterialItem(BaseModel):
    id: int
    section_id: int
    name: str
    type: str
    duration_seconds: int | None = None
    transcode_status: str | None = None
    sort_order: int
    my_status: str = "not_started"
    my_position_seconds: int = 0


class MySectionItem(BaseModel):
    id: int
    name: str
    sort_order: int
    materials: list[MyMaterialItem] = []


class MyCourseDetail(BaseModel):
    id: int
    name: str
    cover_url: str | None = None
    intro: str | None = None
    material_count: int
    completed_count: int
    status: str
    sections: list[MySectionItem] = []


class MaterialOpenResponse(BaseModel):
    material: LearningMaterialResponse
    play_url: str | None = None
    file_url: str | None = None
    download_url: str | None = None
    file_name: str | None = None
    record_status: str
    play_position_seconds: int


class ProgressReportRequest(BaseModel):
    position_seconds: int = Field(ge=0)


class LearningRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    material_id: int
    status: str
    play_position_seconds: int
    completed_at: datetime | None = None
    last_learn_at: datetime | None = None


class CompleteMaterialResponse(BaseModel):
    record: LearningRecordResponse
    course_completed_count: int
    course_material_count: int
    course_status: str
