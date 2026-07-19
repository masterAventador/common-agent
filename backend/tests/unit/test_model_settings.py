import pytest

from common_agent.bootstrap.settings import ConfigurationError, ModelSettings


def _valid_values() -> dict[str, str]:
    return {
        "BAILIAN_API_KEY": "unit-test-secret",
        "BAILIAN_BASE_URL": "https://example.invalid/v1",
        "BAILIAN_MODEL": "unit-test-model",
    }


@pytest.mark.parametrize("missing", ["BAILIAN_API_KEY", "BAILIAN_BASE_URL", "BAILIAN_MODEL"])
def test_model_settings_require_every_bailian_field(missing: str) -> None:
    values = _valid_values()
    del values[missing]

    with pytest.raises(ConfigurationError, match=missing):
        ModelSettings.from_mapping(values)


def test_model_settings_reject_non_https_upstream() -> None:
    values = _valid_values()
    values["BAILIAN_BASE_URL"] = "http://example.invalid/v1"

    with pytest.raises(ConfigurationError, match="BAILIAN_BASE_URL"):
        ModelSettings.from_mapping(values)


def test_model_settings_mask_api_key_in_repr_and_json() -> None:
    settings = ModelSettings.from_mapping(_valid_values())

    assert "unit-test-secret" not in repr(settings)
    assert "unit-test-secret" not in settings.model_dump_json()
    assert settings.api_key.get_secret_value() == "unit-test-secret"
