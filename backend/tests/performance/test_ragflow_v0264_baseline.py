from __future__ import annotations

from pathlib import Path

import pytest

from tests.performance.ragflow_v0264_baseline import (
    EXPECTED_RAGFLOW_COMMIT,
    DatabaseCursor,
    ExplainAnalysis,
    ScaleDatabase,
    build_report_header,
    determine_report_status,
    parse_explain_analyze,
    parse_scale_levels,
    summarize_latencies,
)


class _ConnectionProbe:
    def __init__(self) -> None:
        self.rollback_count = 0

    def cursor(self) -> DatabaseCursor:
        raise AssertionError("cursor should not be used")

    def commit(self) -> None:
        raise AssertionError("commit should not be used")

    def rollback(self) -> None:
        self.rollback_count += 1

    def close(self) -> None:
        pass


def test_scale_levels_are_strictly_increasing_and_bounded() -> None:
    assert parse_scale_levels("100, 1000,10000") == (100, 1000, 10000)

    for invalid in ("", "0", "100,100", "1000,100", "100,1000001", "one"):
        with pytest.raises(ValueError):
            parse_scale_levels(invalid)


def test_latency_summary_uses_nearest_rank_percentiles() -> None:
    summary = summarize_latencies((0.4, 0.1, 0.3, 0.2, 0.5))

    assert summary == {
        "samples": 5,
        "minimum_seconds": 0.1,
        "mean_seconds": 0.3,
        "p50_seconds": 0.3,
        "p95_seconds": 0.5,
        "maximum_seconds": 0.5,
    }


def test_explain_analyze_records_actual_scan_work_instead_of_only_estimates() -> None:
    analysis = parse_explain_analyze(
        """
-> Aggregate: count(0)  (actual time=12.3..12.3 rows=1 loops=1)
    -> Nested loop inner join  (actual time=0.1..11.5 rows=30000 loops=1)
        -> Index lookup on document  (actual time=0.1..3.0 rows=10000 loops=1)
        -> Index lookup on file2document  (actual time=0.001..0.002 rows=3 loops=10000)
""".strip()
    )

    assert analysis == ExplainAnalysis(
        node_count=4,
        maximum_rows_per_node=30000,
        total_rows_across_loops=70001,
    )


def test_report_header_refuses_a_different_upstream_commit() -> None:
    assert build_report_header(
        source_commit=EXPECTED_RAGFLOW_COMMIT,
        source_version="v0.26.4",
        scale_levels=(100, 1000),
        live_document_count=4,
    ) == {
        "schema_version": 1,
        "ragflow_version": "v0.26.4",
        "ragflow_commit": EXPECTED_RAGFLOW_COMMIT,
        "scale_levels": [100, 1000],
        "live_document_count": 4,
    }

    with pytest.raises(ValueError, match="RAGFlow source commit mismatch"):
        build_report_header(
            source_commit="0" * 40,
            source_version="v0.26.4",
            scale_levels=(100,),
            live_document_count=1,
        )


def test_formal_runner_pins_source_and_keeps_secrets_out_of_arguments() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    runner = (repository_root / "scripts/ragflow-v0264-baseline.sh").read_text(
        encoding="utf-8"
    )

    assert EXPECTED_RAGFLOW_COMMIT in runner
    assert "RAGFLOW_BENCHMARK_MYSQL_PASSWORD" in runner
    assert "--api-key-file" in runner
    assert "--mysql-password" not in runner
    assert "STACK_STARTED_BY_RUNNER" in runner
    assert "restore_api_if_needed" in runner


def test_external_api_write_ends_repeatable_read_snapshot_before_verification() -> None:
    connection = _ConnectionProbe()

    ScaleDatabase(connection).refresh_after_external_write()

    assert connection.rollback_count == 1


def test_report_accepts_a_measured_server_disconnect_only_with_api_oom() -> None:
    report: dict[str, object] = {
        "scale_curve": [
            {"delete_one": {"outcome": "server_disconnected", "error_type": "ReadError"}}
        ],
        "cleanup": {
            "errors": [],
            "resources": {
                "sampling_errors": [],
                "final_container_state": {
                    "common-agent-ragflow-api": {"oom_killed": True}
                },
            },
        },
    }

    assert determine_report_status(report) == "completed_with_upstream_oom"

    api_state = report["cleanup"]
    assert isinstance(api_state, dict)
    resources = api_state["resources"]
    assert isinstance(resources, dict)
    containers = resources["final_container_state"]
    assert isinstance(containers, dict)
    containers["common-agent-ragflow-api"] = {"oom_killed": False}
    with pytest.raises(RuntimeError, match="without an OOM"):
        determine_report_status(report)
