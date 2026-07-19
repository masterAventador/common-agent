from common_agent.bootstrap.settings import ModelSettings


def test_versioned_demo_config_loads_without_exposing_secret() -> None:
    settings = ModelSettings.from_demo_file()

    assert settings.provider == "bailian"
    assert settings.base_url.startswith("https://")
    assert settings.model.strip()
    assert settings.api_key.get_secret_value().strip()
    assert settings.api_key.get_secret_value() not in repr(settings)
