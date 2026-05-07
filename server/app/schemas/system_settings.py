"""
System settings schemas
"""
from pydantic import BaseModel, ConfigDict, field_validator
from zoneinfo import available_timezones


SUPPORTED_LANGUAGES = {"zh", "en"}
VALID_TIMEZONES = available_timezones()


class SystemSettingsUpdate(BaseModel):
    default_language: str
    default_timezone: str

    @field_validator("default_language")
    @classmethod
    def validate_language(cls, v: str) -> str:
        if v not in SUPPORTED_LANGUAGES:
            raise ValueError(f"Language must be one of: {', '.join(sorted(SUPPORTED_LANGUAGES))}")
        return v

    @field_validator("default_timezone")
    @classmethod
    def validate_timezone(cls, v: str) -> str:
        if v not in VALID_TIMEZONES:
            raise ValueError(f"Invalid IANA timezone: {v}")
        return v


class OrganizationSettingsUpdate(BaseModel):
    organization_enabled: bool


class SystemSettingsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    default_language: str
    default_timezone: str
    organization_enabled: bool = False
