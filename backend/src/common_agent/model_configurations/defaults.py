from __future__ import annotations

from hashlib import sha256
from uuid import UUID

PLATFORM_DEFAULT_MODEL_DISPLAY_NAME_PREFIX = "平台默认模型"
PLATFORM_DEFAULT_MODEL_IDENTIFIER = "qwen-plus"


def platform_default_model_configuration_id(tenant_id: UUID) -> UUID:
    digest = sha256(f"common-agent:platform-default-model:{tenant_id}".encode()).hexdigest()[:32]
    return UUID(digest)


__all__ = [
    "PLATFORM_DEFAULT_MODEL_DISPLAY_NAME_PREFIX",
    "PLATFORM_DEFAULT_MODEL_IDENTIFIER",
    "platform_default_model_configuration_id",
]
