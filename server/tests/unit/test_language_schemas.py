"""
Language validation schema tests (15-language expansion).
"""
import pytest
from pydantic import ValidationError

from app.schemas.employee import VALID_LANGUAGES, EmployeeCreate, EmployeeUpdate
from app.schemas.system_settings import SUPPORTED_LANGUAGES, SystemSettingsUpdate

NEW_LANGUAGES = [
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
]


def _employee_create(language: str) -> EmployeeCreate:
    return EmployeeCreate(
        name="Agent",
        username="agent01",
        email="agent@example.com",
        password="password123",
        default_language=language,
    )


class TestLanguageSets:
    def test_supported_languages_contains_15_locales(self):
        assert SUPPORTED_LANGUAGES == {"zh", "en", *NEW_LANGUAGES}

    def test_valid_languages_is_supported_plus_system(self):
        assert VALID_LANGUAGES == {"system", "zh", "en", *NEW_LANGUAGES}


class TestSystemSettingsLanguage:
    @pytest.mark.parametrize("language", ["zh", "en", *NEW_LANGUAGES])
    def test_accepts_all_supported_languages(self, language: str):
        payload = SystemSettingsUpdate(default_language=language, default_timezone="UTC")
        assert payload.default_language == language

    @pytest.mark.parametrize("language", ["system", "fr", "de-DE", "ar-SA", "he-IL", ""])
    def test_rejects_invalid_languages(self, language: str):
        with pytest.raises(ValidationError):
            SystemSettingsUpdate(default_language=language, default_timezone="UTC")


class TestEmployeeCreateLanguage:
    @pytest.mark.parametrize("language", ["system", "zh", "en", *NEW_LANGUAGES])
    def test_accepts_system_and_all_supported_languages(self, language: str):
        assert _employee_create(language).default_language == language

    @pytest.mark.parametrize("language", ["fr", "de-DE", "ar-SA", "he-IL", ""])
    def test_rejects_invalid_languages(self, language: str):
        with pytest.raises(ValidationError):
            _employee_create(language)


class TestEmployeeUpdateLanguage:
    @pytest.mark.parametrize("language", ["system", "zh", "en", *NEW_LANGUAGES])
    def test_accepts_system_and_all_supported_languages(self, language: str):
        assert EmployeeUpdate(default_language=language).default_language == language

    @pytest.mark.parametrize("language", ["fr", "de-DE", "ar-SA", "he-IL", ""])
    def test_rejects_invalid_languages(self, language: str):
        with pytest.raises(ValidationError):
            EmployeeUpdate(default_language=language)

    def test_omitted_language_stays_none(self):
        assert EmployeeUpdate().default_language is None
