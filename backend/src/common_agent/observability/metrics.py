from __future__ import annotations

import re
from dataclasses import dataclass
from threading import Lock
from time import monotonic

_ERROR_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


@dataclass(frozen=True, slots=True)
class LatencySnapshot:
    count: int
    total: float
    maximum: float


@dataclass(frozen=True, slots=True)
class MetricsSnapshot:
    uptime_seconds: float
    requests_in_flight: int
    requests_total: int
    responses_by_status: dict[str, int]
    errors_by_code: dict[str, int]
    latency_ms: LatencySnapshot


class MetricsRegistry:
    def __init__(self, *, max_error_codes: int = 64) -> None:
        if max_error_codes < 1 or max_error_codes > 256:
            raise ValueError("max_error_codes must be between 1 and 256")
        self._max_error_codes = max_error_codes
        self._started_at = monotonic()
        self._lock = Lock()
        self._requests_in_flight = 0
        self._requests_total = 0
        self._responses_by_status: dict[str, int] = {}
        self._errors_by_code: dict[str, int] = {}
        self._latency_count = 0
        self._latency_total = 0.0
        self._latency_maximum = 0.0

    def begin_request(self) -> float:
        with self._lock:
            self._requests_in_flight += 1
        return monotonic()

    def complete_request(
        self,
        started_at: float,
        *,
        status_code: int,
        error_code: str | None,
    ) -> float:
        duration_ms = max(0.0, (monotonic() - started_at) * 1000)
        status_bucket = _status_bucket(status_code)
        with self._lock:
            normalized_error = self._error_label(error_code)
            self._requests_in_flight = max(0, self._requests_in_flight - 1)
            self._requests_total += 1
            self._responses_by_status[status_bucket] = (
                self._responses_by_status.get(status_bucket, 0) + 1
            )
            if normalized_error is not None:
                self._errors_by_code[normalized_error] = (
                    self._errors_by_code.get(normalized_error, 0) + 1
                )
            self._latency_count += 1
            self._latency_total += duration_ms
            self._latency_maximum = max(self._latency_maximum, duration_ms)
        return duration_ms

    def snapshot(self) -> MetricsSnapshot:
        with self._lock:
            return MetricsSnapshot(
                uptime_seconds=max(0.0, monotonic() - self._started_at),
                requests_in_flight=self._requests_in_flight,
                requests_total=self._requests_total,
                responses_by_status=dict(sorted(self._responses_by_status.items())),
                errors_by_code=dict(sorted(self._errors_by_code.items())),
                latency_ms=LatencySnapshot(
                    count=self._latency_count,
                    total=self._latency_total,
                    maximum=self._latency_maximum,
                ),
            )

    def _error_label(self, error_code: str | None) -> str | None:
        if error_code is None:
            return None
        normalized = error_code.strip().lower()
        if not _ERROR_CODE_PATTERN.fullmatch(normalized):
            return "other"
        if normalized in self._errors_by_code:
            return normalized
        known_count = sum(code != "other" for code in self._errors_by_code)
        if known_count >= self._max_error_codes:
            return "other"
        return normalized


def _status_bucket(status_code: int) -> str:
    if status_code < 100 or status_code > 599:
        return "other"
    return f"{status_code // 100}xx"
