import copy
from types import SimpleNamespace

from app.services.satisfaction_survey_config_service import SatisfactionSurveyConfigService


def _config_row(**overrides):
    data = {
        "id": 12,
        "tenant_id": 1,
        "name": "Draft survey",
        "enabled": True,
        "current_version": None,
        "triggers": {},
        "service_settings": {},
        "product_settings": {},
        "updated_by_id": None,
        "updated_by_name": None,
        "updated_at": None,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_empty_persisted_settings_return_default_unconfigured_response():
    response = SatisfactionSurveyConfigService._config_to_response(_config_row())

    assert response["configured"] is False
    assert response["current_version"] is None
    assert response["triggers"]["agent_invite"] is True
    assert response["triggers"]["session_end_invite"] is True
    assert response["service"]["section_title"]
    assert response["product"]["section_title"]
    assert len(response["service"]["rating_options"]) >= 2
    assert len(response["product"]["rating_options"]) >= 2


def test_partial_persisted_settings_merge_defaults():
    response = SatisfactionSurveyConfigService._config_to_response(
        _config_row(
            current_version=3,
            triggers={"agent_invite": False, "session_end_invite": True},
            service_settings={
                "rating_mode": "emoji",
                "rating_options": [
                    {"key": "good", "name": "Good", "score": 10},
                    {"key": "bad", "name": "Bad", "score": 1},
                ],
            },
            product_settings={"enabled": False},
        )
    )

    assert response["configured"] is True
    assert response["current_version"] == 3
    assert response["triggers"]["agent_invite"] is False
    assert response["triggers"]["session_end_invite"] is True
    assert response["service"]["rating_mode"] == "emoji"
    assert response["service"]["section_title"]
    assert response["service"]["popup_title"]
    assert response["service"]["rating_options"][0]["name"] == "Good"
    assert response["product"]["enabled"] is False


def _snapshot(service_options=None, product_options=None, service_mode="stars", product_mode="stars"):
    payload = SatisfactionSurveyConfigService.default_payload().model_dump(mode="json")
    if service_options is not None:
        payload["service"]["rating_options"] = service_options
    if product_options is not None:
        payload["product"]["rating_options"] = product_options
    payload["service"]["rating_mode"] = service_mode
    payload["product"]["rating_mode"] = product_mode
    return payload


def test_should_bump_version_on_first_save():
    snapshot = _snapshot()
    assert SatisfactionSurveyConfigService.should_bump_version(None, snapshot) is True


def test_should_not_bump_version_for_score_or_order_changes():
    base = _snapshot()
    rescore = copy.deepcopy(base)
    rescore["service"]["rating_options"][0]["score"] = 99

    reordered = copy.deepcopy(base)
    reordered["service"]["rating_options"] = list(reversed(reordered["service"]["rating_options"]))

    assert SatisfactionSurveyConfigService.should_bump_version(base, rescore) is False
    assert SatisfactionSurveyConfigService.should_bump_version(base, reordered) is False


def test_should_bump_version_for_rating_mode_or_option_changes():
    base = _snapshot()
    mode_changed = copy.deepcopy(base)
    mode_changed["service"]["rating_mode"] = "text"

    renamed = copy.deepcopy(base)
    renamed["service"]["rating_options"][0]["name"] = "Renamed"

    disabled = copy.deepcopy(base)
    disabled["service"]["rating_options"][0]["enabled"] = False

    assert SatisfactionSurveyConfigService.should_bump_version(base, mode_changed) is True
    assert SatisfactionSurveyConfigService.should_bump_version(base, renamed) is True
    assert SatisfactionSurveyConfigService.should_bump_version(base, disabled) is True
