from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

MODEL_DISPLAY_NAME_MAX_LENGTH = 128
MODEL_IDENTIFIER_MAX_LENGTH = 128
_MODEL_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class ModelConfigurationValidationError(ValueError):
    def __init__(self, field: str, reason: str) -> None:
        self.field = field
        self.reason = reason
        super().__init__(f"模型配置字段 {field} {reason}")


class ModelProvider(StrEnum):
    BAILIAN = "bailian"


@dataclass(frozen=True, slots=True)
class ModelConfigurationInput:
    display_name: str
    model_identifier: str
    enabled: bool

    def __post_init__(self) -> None:
        display_name = _required_text(
            "display_name",
            self.display_name,
            MODEL_DISPLAY_NAME_MAX_LENGTH,
        )
        model_identifier = normalize_model_identifier(self.model_identifier)
        if not isinstance(self.enabled, bool):
            raise ModelConfigurationValidationError("enabled", "必须是布尔值")
        object.__setattr__(self, "display_name", display_name)
        object.__setattr__(self, "model_identifier", model_identifier)


@dataclass(frozen=True, slots=True)
class ModelConfiguration:
    id: UUID
    display_name: str
    provider: ModelProvider
    model_identifier: str
    enabled: bool
    created_at: datetime
    updated_at: datetime
    streaming_breaks_tool_calls: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.id, UUID):
            raise ModelConfigurationValidationError("id", "必须是 UUID")
        if self.provider is not ModelProvider.BAILIAN:
            raise ModelConfigurationValidationError("provider", "当前只支持阿里百炼")
        normalized = ModelConfigurationInput(
            display_name=self.display_name,
            model_identifier=self.model_identifier,
            enabled=self.enabled,
        )
        if not isinstance(self.streaming_breaks_tool_calls, bool):
            raise ModelConfigurationValidationError(
                "streaming_breaks_tool_calls",
                "必须是布尔值",
            )
        _utc_timestamp("created_at", self.created_at)
        _utc_timestamp("updated_at", self.updated_at)
        if self.updated_at < self.created_at:
            raise ModelConfigurationValidationError("updated_at", "不能早于创建时间")
        object.__setattr__(self, "display_name", normalized.display_name)
        object.__setattr__(self, "model_identifier", normalized.model_identifier)

    @classmethod
    def create(
        cls,
        *,
        configuration: ModelConfigurationInput,
        model_configuration_id: UUID | None = None,
        now: datetime | None = None,
        streaming_breaks_tool_calls: bool = False,
    ) -> ModelConfiguration:
        created_at = now or datetime.now(UTC)
        return cls(
            id=model_configuration_id or uuid4(),
            display_name=configuration.display_name,
            provider=ModelProvider.BAILIAN,
            model_identifier=configuration.model_identifier,
            enabled=configuration.enabled,
            created_at=created_at,
            updated_at=created_at,
            streaming_breaks_tool_calls=streaming_breaks_tool_calls,
        )

    def reconfigure(
        self,
        configuration: ModelConfigurationInput,
        *,
        updated_at: datetime | None = None,
        streaming_breaks_tool_calls: bool = False,
    ) -> ModelConfiguration:
        return replace(
            self,
            display_name=configuration.display_name,
            model_identifier=configuration.model_identifier,
            enabled=configuration.enabled,
            streaming_breaks_tool_calls=streaming_breaks_tool_calls,
            updated_at=updated_at or datetime.now(UTC),
        )


def _required_text(field: str, value: object, max_length: int) -> str:
    if not isinstance(value, str):
        raise ModelConfigurationValidationError(field, "必须是字符串")
    normalized = value.strip()
    if not normalized:
        raise ModelConfigurationValidationError(field, "不能为空")
    if len(normalized) > max_length:
        raise ModelConfigurationValidationError(field, f"不能超过 {max_length} 个字符")
    return normalized


def normalize_model_identifier(value: object) -> str:
    model_identifier = _required_text(
        "model_identifier",
        value,
        MODEL_IDENTIFIER_MAX_LENGTH,
    )
    if _MODEL_IDENTIFIER_PATTERN.fullmatch(model_identifier) is None:
        raise ModelConfigurationValidationError(
            "model_identifier",
            "只能包含字母、数字、点、下划线和连字符",
        )
    return model_identifier


def _utc_timestamp(field: str, value: object) -> None:
    if not isinstance(value, datetime):
        raise ModelConfigurationValidationError(field, "必须是时间")
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ModelConfigurationValidationError(field, "必须使用 UTC 时区")
