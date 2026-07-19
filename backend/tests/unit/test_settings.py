import pytest

from common_agent.bootstrap.settings import ApiSettings, ConfigurationError


def test_api_settings_use_project_loopback_defaults() -> None:
    settings = ApiSettings.from_mapping({})

    assert settings.host == "127.0.0.1"
    assert settings.port == 18200


def test_api_settings_accept_project_specific_override() -> None:
    settings = ApiSettings.from_mapping(
        {
            "COMMON_AGENT_API_HOST": "localhost",
            "COMMON_AGENT_API_PORT": "18201",
        }
    )

    assert settings.host == "localhost"
    assert settings.port == 18201


@pytest.mark.parametrize("port", ["not-a-port", "0", "65536"])
def test_api_settings_reject_invalid_port(port: str) -> None:
    with pytest.raises(ConfigurationError, match="COMMON_AGENT_API_PORT"):
        ApiSettings.from_mapping({"COMMON_AGENT_API_PORT": port})


def test_api_settings_reject_public_bind_address() -> None:
    with pytest.raises(ConfigurationError, match="loopback"):
        ApiSettings.from_mapping({"COMMON_AGENT_API_HOST": "0.0.0.0"})
