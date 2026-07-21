import pytest

from common_agent.bootstrap.settings import ConfigurationError, ModelSettings


def _valid_values() -> dict[str, str]:
    return {
        "BAILIAN_API_KEY": "unit-test-secret",
        "BAILIAN_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1",
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


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("BAILIAN_BASE_URL", "https://user:password@dashscope.aliyuncs.com/compatible-mode/v1"),
        ("BAILIAN_BASE_URL", "https://example.invalid/compatible-mode/v1"),
        ("BAILIAN_BASE_URL", "https://dashscope.aliyuncs.com/v1?token=secret"),
        ("BAILIAN_TIMEOUT_SECONDS", "0"),
        ("BAILIAN_TIMEOUT_SECONDS", "301"),
        ("BAILIAN_TIMEOUT_SECONDS", "not-a-number"),
        ("BAILIAN_STREAM_CHUNK_TIMEOUT_SECONDS", "nan"),
        ("BAILIAN_STREAM_CHUNK_TIMEOUT_SECONDS", "301"),
        ("BAILIAN_MAX_RETRIES", "-1"),
        ("BAILIAN_MAX_RETRIES", "4"),
        ("BAILIAN_MAX_RETRIES", "not-an-integer"),
    ],
)
def test_model_settings_reject_unsafe_or_unbounded_runtime_values(key: str, value: str) -> None:
    values = _valid_values()
    values[key] = value

    with pytest.raises(ConfigurationError, match=key):
        ModelSettings.from_mapping(values)


def test_model_settings_have_bounded_runtime_defaults() -> None:
    settings = ModelSettings.from_mapping(_valid_values())

    assert settings.timeout_seconds == 60
    assert settings.stream_chunk_timeout_seconds == 60
    assert settings.max_retries == 2


def test_model_settings_env_overrides_versioned_demo_controls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BAILIAN_API_KEY", "unit-test-env-secret")
    monkeypatch.setenv("BAILIAN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    monkeypatch.setenv("BAILIAN_MODEL", "unit-test-model")
    monkeypatch.setenv("BAILIAN_TIMEOUT_SECONDS", "45")
    monkeypatch.setenv("BAILIAN_STREAM_CHUNK_TIMEOUT_SECONDS", "15")
    monkeypatch.setenv("BAILIAN_MAX_RETRIES", "1")

    settings = ModelSettings.from_env()

    assert settings.api_key.get_secret_value() == "unit-test-env-secret"
    assert settings.timeout_seconds == 45
    assert settings.stream_chunk_timeout_seconds == 15
    assert settings.max_retries == 1


def test_authorized_versioned_demo_config_loads_without_exposing_secret() -> None:
    settings = ModelSettings.from_demo_file()

    assert settings.provider == "bailian"
    assert settings.base_url.startswith("https://")
    assert bool(settings.model.strip())
    assert bool(settings.api_key.get_secret_value().strip())
    assert "**********" in repr(settings)


def test_model_settings_mask_api_key_in_repr_and_json() -> None:
    settings = ModelSettings.from_mapping(_valid_values())

    assert "unit-test-secret" not in repr(settings)
    assert "unit-test-secret" not in settings.model_dump_json()
    assert settings.api_key.get_secret_value() == "unit-test-secret"
