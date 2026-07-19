from __future__ import annotations

from common_agent.models.base import (
    ModelConfigurationInvalid,
    ModelProviderResponseInvalid,
    ModelRequestRejected,
    ModelServiceUnavailable,
    ModelStreamInterrupted,
)


def test_model_errors_expose_only_stable_safe_metadata() -> None:
    expected = [
        (ModelConfigurationInvalid(), "configuration_missing", False),
        (ModelRequestRejected(), "model_request_rejected", False),
        (ModelServiceUnavailable(), "model_unavailable", True),
        (ModelProviderResponseInvalid(), "model_response_invalid", False),
        (ModelStreamInterrupted(), "model_stream_interrupted", True),
    ]

    for error, code, retryable in expected:
        assert error.code == code
        assert error.retryable is retryable
        assert str(error) == error.message
        assert "upstream" not in repr(error).lower()
