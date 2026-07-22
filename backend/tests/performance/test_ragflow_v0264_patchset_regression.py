from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from pathlib import Path

import pytest

from tests.performance.ragflow_v0264_patchset_regression import (
    EXPECTED_PATCH_HEAD,
    validate_patchset_reports,
)


def _resources() -> dict[str, object]:
    return {
        "sampling_errors": [],
        "peak_swap_used_bytes": 0,
        "final_container_state": {
            name: {"status": "running", "restart_count": 0, "oom_killed": False}
            for name in (
                "common-agent-ragflow-api",
                "common-agent-ragflow-elasticsearch",
                "common-agent-ragflow-minio",
                "common-agent-ragflow-mysql",
                "common-agent-ragflow-valkey",
            )
        },
    }


def _reports() -> tuple[dict[str, object], ...]:
    list_report: dict[str, object] = {
        "status": "passed",
        "ragflow_commit": EXPECTED_PATCH_HEAD,
        "source_audit": {"mode": "patched"},
        "scale_curve": [
            {
                "target_documents": 250000,
                "first_page": {"p50_seconds": 0.1},
                "deep_page": {"p50_seconds": 1.0},
                "delete_one": {"outcome": "succeeded", "seconds": 0.5},
                "sql": {
                    "direct_count": {"analysis": {"total_rows_across_loops": 250001}},
                    "page_details": {"analysis": {"total_rows_across_loops": 60}},
                    "delete_ownership_lookup": {
                        "analysis": {"total_rows_across_loops": 1}
                    },
                },
            }
        ],
        "live_api_worker": {
            "retrieval": {"returned_marker": True},
            "delete": {"list_invisible": True, "retrieval_invisible": True},
        },
        "cleanup": {"errors": [], "live_dataset_deleted": True, "resources": _resources()},
    }
    official_write: dict[str, object] = {
        "status": "passed",
        "write_profile": {"chunks_per_second": 3.4},
    }
    patch_write: dict[str, object] = {
        "status": "passed",
        "ragflow_commit": EXPECTED_PATCH_HEAD,
        "source_audit": {"mode": "patched"},
        "configuration": {
            "doc_bulk_size": 32,
            "embedding_concurrency": 8,
            "root_scale_documents": 250000,
        },
        "write_profile": {"chunks_per_second": 5.7, "marker_returned": True},
        "root_lookup_profile": {
            "target_documents": 250000,
            "official_column_comparison": {
                "analysis": {"total_rows_across_loops": 250013}
            },
            "patched_constant_lookup": {"analysis": {"total_rows_across_loops": 3}},
        },
        "cleanup": {"errors": [], "live_dataset_deleted": True, "resources": _resources()},
    }
    official_retrieval: dict[str, object] = {"status": "passed"}
    patch_retrieval: dict[str, object] = {
        "status": "passed",
        "ragflow_commit": EXPECTED_PATCH_HEAD,
        "source_audit": {"mode": "patched"},
        "retrieval_profile": {
            "marker_returned": True,
            "levels": [
                {"top_k": 5, "elapsed_seconds": 1.0},
                {"top_k": 64, "elapsed_seconds": 0.8},
                {"top_k": 2048, "elapsed_seconds": 0.9},
            ],
            "boundary": {
                "requested_top_k": 2049,
                "code": 102,
                "message": "`top_k` must be less than or equal to 2048",
                "elapsed_seconds": 0.01,
            },
        },
        "chunk_read_profile": {
            "target_synthetic_chunks": 12000,
            "first_page": {"returned": 100, "elapsed_seconds": 0.03},
            "deep_page": {"returned": 100, "elapsed_seconds": 0.2},
            "oversize_page": {"code": 100},
            "single_chunk_runtime_fields_absent": True,
        },
        "cleanup": {
            "errors": [],
            "dataset_deleted": True,
            "synthetic_deleted": 12000,
            "synthetic_delete_errors": 0,
            "resources": _resources(),
        },
    }
    return list_report, official_write, patch_write, official_retrieval, patch_retrieval


def test_patchset_reports_require_final_head_performance_and_cleanup() -> None:
    summary = validate_patchset_reports(*_reports())

    assert summary["status"] == "passed"
    assert summary["ragflow_commit"] == EXPECTED_PATCH_HEAD
    write = summary["write"]
    upgrade_scale = summary["upgrade_scale"]
    assert isinstance(write, dict)
    assert isinstance(upgrade_scale, dict)
    assert write["throughput_ratio"] > 1.5
    assert upgrade_scale["target_documents"] == 250000


@pytest.mark.parametrize(
    ("report_index", "mutation", "message"),
    [
        (0, lambda report: report.update(ragflow_commit="0" * 40), "final patch head"),
        (
            0,
            lambda report: report["scale_curve"][-1]["delete_one"].update(
                outcome="server_disconnected"
            ),
            "delete",
        ),
        (
            2,
            lambda report: report["write_profile"].update(chunks_per_second=3.5),
            "throughput",
        ),
        (
            4,
            lambda report: report["retrieval_profile"]["boundary"].update(
                message="Elasticsearch BadRequestError"
            ),
            "boundary",
        ),
        (
            4,
            lambda report: report["cleanup"].update(synthetic_deleted=11999),
            "synthetic",
        ),
        (
            4,
            lambda report: report["cleanup"]["resources"].update(
                peak_swap_used_bytes=1
            ),
            "swap",
        ),
    ],
)
def test_patchset_reports_close_fail_on_regressions(
    report_index: int,
    mutation: Callable[[dict[str, object]], None],
    message: str,
) -> None:
    reports = list(deepcopy(_reports()))
    report = reports[report_index]
    assert isinstance(report, dict)
    mutation(report)

    with pytest.raises(RuntimeError, match=message):
        validate_patchset_reports(*reports)


def test_formal_patchset_runner_pins_all_three_final_reports() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    runner = (repository_root / "scripts/ragflow-v0264-patchset-check.sh").read_text(
        encoding="utf-8"
    )

    assert "infra/ragflow/patchset.env" in runner
    assert "RAGFLOW_PATCH_SHORT" in runner
    assert "COMMON_AGENT_R2_06_LIST_REPORT" in runner
    assert "COMMON_AGENT_R2_06_WRITE_REPORT" in runner
    assert "COMMON_AGENT_R2_06_RETRIEVAL_REPORT" in runner
    assert '--expected-commit "${RAGFLOW_PATCH_HEAD}"' in runner
    assert "ragflow_v0264_patchset_regression" in runner
