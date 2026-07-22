from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID

import pytest

from common_agent.domain.model_configuration import (
    ModelConfiguration,
    ModelConfigurationInput,
    ModelConfigurationValidationError,
    ModelProvider,
)


def test_model_configuration_normalizes_user_managed_bailian_fields() -> None:
    now = datetime(2026, 7, 22, tzinfo=UTC)

    configuration = ModelConfiguration.create(
        configuration=ModelConfigurationInput(
            display_name="  Qwen Plus  ",
            model_identifier="  qwen-plus  ",
            enabled=True,
        ),
        model_configuration_id=UUID("10000000-0000-4000-8000-000000000018"),
        now=now,
        streaming_breaks_tool_calls=True,
    )

    assert configuration.display_name == "Qwen Plus"
    assert configuration.model_identifier == "qwen-plus"
    assert configuration.provider is ModelProvider.BAILIAN
    assert configuration.enabled is True
    assert configuration.streaming_breaks_tool_calls is True
    assert configuration.created_at == now
    assert configuration.updated_at == now


def test_model_configuration_reconfigure_preserves_identity_and_creation() -> None:
    now = datetime(2026, 7, 22, tzinfo=UTC)
    existing = ModelConfiguration.create(
        configuration=ModelConfigurationInput(
            display_name="Qwen Plus",
            model_identifier="qwen-plus",
            enabled=True,
        ),
        now=now,
        streaming_breaks_tool_calls=True,
    )

    updated = existing.reconfigure(
        ModelConfigurationInput(
            display_name="Qwen Max",
            model_identifier="qwen-max-latest",
            enabled=False,
        ),
        updated_at=now + timedelta(seconds=1),
        streaming_breaks_tool_calls=False,
    )

    assert updated.id == existing.id
    assert updated.provider is ModelProvider.BAILIAN
    assert updated.created_at == existing.created_at
    assert updated.updated_at > existing.updated_at
    assert updated.display_name == "Qwen Max"
    assert updated.model_identifier == "qwen-max-latest"
    assert updated.enabled is False
    assert updated.streaming_breaks_tool_calls is False


@pytest.mark.parametrize(
    ("display_name", "model_identifier"),
    [
        (" ", "qwen-plus"),
        ("Qwen", " "),
        ("Qwen", "qwen plus"),
        ("Qwen", "https://example.com/model"),
        ("Qwen", "../qwen-plus"),
    ],
)
def test_model_configuration_rejects_blank_or_unsafe_identifiers(
    display_name: str,
    model_identifier: str,
) -> None:
    with pytest.raises(ModelConfigurationValidationError):
        ModelConfigurationInput(
            display_name=display_name,
            model_identifier=model_identifier,
            enabled=True,
        )


@pytest.mark.parametrize(
    "configuration",
    [
        {"display_name": 1, "model_identifier": "qwen-plus", "enabled": True},
        {"display_name": "x" * 129, "model_identifier": "qwen-plus", "enabled": True},
        {"display_name": "Qwen", "model_identifier": "x" * 129, "enabled": True},
        {"display_name": "Qwen", "model_identifier": "qwen-plus", "enabled": 1},
    ],
)
def test_model_configuration_input_rejects_invalid_field_types_and_lengths(
    configuration: dict[str, object],
) -> None:
    with pytest.raises(ModelConfigurationValidationError):
        ModelConfigurationInput(**configuration)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "override",
    [
        {"id": "not-a-uuid"},
        {"provider": "openai"},
        {"created_at": "not-a-time"},
        {"created_at": datetime(2026, 7, 22)},
        {"created_at": datetime(2026, 7, 22, tzinfo=timezone(timedelta(hours=8)))},
        {"updated_at": datetime(2026, 7, 21, tzinfo=UTC)},
        {"streaming_breaks_tool_calls": 1},
    ],
)
def test_model_configuration_rejects_invalid_identity_provider_or_timestamps(
    override: dict[str, object],
) -> None:
    values: dict[str, object] = {
        "id": UUID("10000000-0000-4000-8000-000000000018"),
        "display_name": "Qwen Plus",
        "provider": ModelProvider.BAILIAN,
        "model_identifier": "qwen-plus",
        "enabled": True,
        "created_at": datetime(2026, 7, 22, tzinfo=UTC),
        "updated_at": datetime(2026, 7, 22, tzinfo=UTC),
    }
    values.update(override)

    with pytest.raises(ModelConfigurationValidationError):
        ModelConfiguration(**values)  # type: ignore[arg-type]
