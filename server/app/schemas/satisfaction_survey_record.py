"""
Satisfaction survey invitation, submission, and record schemas.
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.satisfaction_survey_config import SatisfactionSurveyConfigPayload


SatisfactionSurveyType = Literal["service", "product"]
SatisfactionRecordStatus = Literal["none", "invited", "submitted", "closed", "expired"]
SatisfactionEventType = Literal["invitation_sent", "feedback_submitted"]


class SatisfactionSurveyEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    conversation_id: int
    record_id: int
    event_type: SatisfactionEventType
    actor_type: str
    actor_id: int | None = None
    actor_name: str | None = None
    summary: str
    config_version: int
    occurred_at: datetime
    metadata: dict = Field(default_factory=dict)


class SatisfactionSurveyResultResponse(BaseModel):
    type: SatisfactionSurveyType
    rating_mode: str
    section_title: str | None = None
    option_key: str
    option_name: str
    labels: list[str] = Field(default_factory=list)
    remark: str | None = None
    resolved: bool | None = None
    submitted_at: str | None = None


class SatisfactionSurveyRecordResponse(BaseModel):
    id: int
    conversation_id: int
    config_version: int
    config_snapshot: SatisfactionSurveyConfigPayload
    invitation_source: str
    invited_by_id: int | None = None
    invited_by_name: str | None = None
    invited_at: datetime | None = None
    status: str
    survey_types: list[SatisfactionSurveyType]
    service_result: SatisfactionSurveyResultResponse | None = None
    product_result: SatisfactionSurveyResultResponse | None = None
    submitted_at: datetime | None = None


class SatisfactionSummaryResponse(BaseModel):
    status: SatisfactionRecordStatus
    labels: list[str] = Field(default_factory=list)
    invited_at: datetime | None = None
    submitted_at: datetime | None = None
    config_version: int | None = None


class SatisfactionConversationState(BaseModel):
    can_invite: bool
    disabled_reason: str | None = None
    needs_confirmation: bool = False
    record: SatisfactionSurveyRecordResponse | None = None
    summary: SatisfactionSummaryResponse
    latest_event: SatisfactionSurveyEventResponse | None = None


class SatisfactionInviteRequest(BaseModel):
    force: bool = False


class SatisfactionSubmissionTypePayload(BaseModel):
    rating_option_key: str = Field(min_length=1, max_length=128)
    labels: list[str] = Field(default_factory=list)
    remark: str | None = Field(default=None, max_length=500)
    resolved: bool | None = None

    @field_validator("labels")
    @classmethod
    def normalize_labels(cls, value: list[str]) -> list[str]:
        labels: list[str] = []
        for item in value:
            label = str(item).strip()
            if label and label not in labels:
                labels.append(label)
        return labels

    @field_validator("remark")
    @classmethod
    def normalize_remark(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip()


class SatisfactionSubmissionPayload(BaseModel):
    service: SatisfactionSubmissionTypePayload | None = None
    product: SatisfactionSubmissionTypePayload | None = None


class PublicSatisfactionInvitation(BaseModel):
    invitation: SatisfactionSurveyRecordResponse | None = None
    can_initiate: bool = False
    disabled_reason: str | None = None


class PublicSatisfactionSubmitResponse(BaseModel):
    record: SatisfactionSurveyRecordResponse
    latest_event: SatisfactionSurveyEventResponse


class SessionRecordSatisfactionResponse(BaseModel):
    record: SatisfactionSurveyRecordResponse | None = None
    events: list[SatisfactionSurveyEventResponse] = Field(default_factory=list)


class SatisfactionFilterOption(BaseModel):
    key: str
    label: str


class SatisfactionFilterOptionsResponse(BaseModel):
    configured: bool
    current_version: int | None = None
    survey_types: list[SatisfactionSurveyType] = Field(default_factory=list)
    show_resolution: bool = False
    service_options: list[SatisfactionFilterOption] = Field(default_factory=list)
    service_labels: list[SatisfactionFilterOption] = Field(default_factory=list)
    product_options: list[SatisfactionFilterOption] = Field(default_factory=list)
    product_labels: list[SatisfactionFilterOption] = Field(default_factory=list)
