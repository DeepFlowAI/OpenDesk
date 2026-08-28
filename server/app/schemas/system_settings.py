"""
System settings schemas
"""
from pydantic import BaseModel, ConfigDict, Field, field_validator
from zoneinfo import available_timezones


SUPPORTED_LANGUAGES = {
    "zh",
    "en",
    "fr-FR",
    "es-ES",
    "es-419",
    "pt-BR",
    "pt-PT",
    "it-IT",
    "nl-NL",
    "pl-PL",
    "ru-RU",
    "tr-TR",
    "th-TH",
    "vi-VN",
    "id-ID",
}
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


class CallTranscriptionSettingsUpdate(BaseModel):
    enabled: bool


class CallWrapupSettingsUpdate(BaseModel):
    seconds: int = Field(ge=0, le=60)


class SystemSettingsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    default_language: str
    default_timezone: str
    organization_enabled: bool = False
    bridge_asr_enabled: bool = False
    call_wrapup_seconds: int = 30
    lingomaster_enabled: bool = False
    lingomaster_visitor_prompt: str = ""
    lingomaster_agent_prompt: str = ""
