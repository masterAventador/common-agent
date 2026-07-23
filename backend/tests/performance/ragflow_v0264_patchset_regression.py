from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

EXPECTED_PATCH_HEAD = "21eb8fb4001421f2952ce3125e46e753825d3f9b"
EXPECTED_CONTAINERS = frozenset(
    {
        "common-agent-ragflow-api",
        "common-agent-ragflow-elasticsearch",
        "common-agent-ragflow-minio",
        "common-agent-ragflow-mysql",
        "common-agent-ragflow-valkey",
    }
)


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RuntimeError(f"{label} is missing")
    return value


def _finite_number(value: object, label: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RuntimeError(f"{label} is not numeric")
    result = float(value)
    if not math.isfinite(result) or (positive and result <= 0):
        raise RuntimeError(f"{label} is invalid")
    return result


def _patched_report(
    report: dict[str, object],
    label: str,
    expected_commit: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if report.get("status") != "passed":
        raise RuntimeError(f"{label} report did not pass")
    if report.get("ragflow_commit") != expected_commit:
        raise RuntimeError(f"{label} report is not from the final patch head")
    audit = _mapping(report.get("source_audit"), f"{label} source audit")
    if audit.get("mode") != "patched":
        raise RuntimeError(f"{label} report did not use patched source mode")
    cleanup = _mapping(report.get("cleanup"), f"{label} cleanup")
    if cleanup.get("errors") != []:
        raise RuntimeError(f"{label} cleanup failed")
    resources = _mapping(cleanup.get("resources"), f"{label} resources")
    if resources.get("sampling_errors") != []:
        raise RuntimeError(f"{label} resource sampling failed")
    if resources.get("peak_swap_used_bytes") != 0:
        raise RuntimeError(f"{label} swap usage regressed")
    final_state = _mapping(
        resources.get("final_container_state"), f"{label} final container state"
    )
    if not EXPECTED_CONTAINERS.issubset(final_state):
        raise RuntimeError(f"{label} final container state is incomplete")
    for name in EXPECTED_CONTAINERS:
        state = _mapping(final_state.get(name), f"{label} {name} state")
        if (
            state.get("status") != "running"
            or state.get("restart_count") != 0
            or state.get("oom_killed") is not False
        ):
            raise RuntimeError(f"{label} container health regressed: {name}")
    return cleanup, resources


def _validate_list_report(
    report: dict[str, object], expected_commit: str
) -> dict[str, object]:
    cleanup, _ = _patched_report(report, "list/delete", expected_commit)
    if cleanup.get("live_dataset_deleted") is not True:
        raise RuntimeError("list/delete live dataset cleanup failed")
    curve = report.get("scale_curve")
    if not isinstance(curve, list) or not curve:
        raise RuntimeError("list/delete scale curve is missing")
    last = _mapping(curve[-1], "list/delete largest scale")
    target = last.get("target_documents")
    if target != 250_000:
        raise RuntimeError("list/delete largest scale is not 250000 documents")
    first_page = _mapping(last.get("first_page"), "list/delete first page")
    deep_page = _mapping(last.get("deep_page"), "list/delete deep page")
    deletion = _mapping(last.get("delete_one"), "list/delete delete result")
    first_seconds = _finite_number(first_page.get("p50_seconds"), "first page latency")
    deep_seconds = _finite_number(deep_page.get("p50_seconds"), "deep page latency")
    delete_seconds = _finite_number(deletion.get("seconds"), "delete latency")
    if first_seconds > 1.5 or deep_seconds > 2.5:
        raise RuntimeError("list/delete pagination latency regressed")
    if deletion.get("outcome") != "succeeded" or delete_seconds > 2.0:
        raise RuntimeError("list/delete delete behavior regressed")

    sql = _mapping(last.get("sql"), "list/delete SQL evidence")
    row_limits = {
        "direct_count": 250_001,
        "page_details": 200,
        "delete_ownership_lookup": 1,
    }
    sql_rows: dict[str, int] = {}
    for name, maximum in row_limits.items():
        evidence = _mapping(sql.get(name), f"list/delete SQL {name}")
        analysis = _mapping(evidence.get("analysis"), f"list/delete SQL {name} analysis")
        rows = analysis.get("total_rows_across_loops")
        if isinstance(rows, bool) or not isinstance(rows, int) or rows > maximum:
            raise RuntimeError(f"list/delete SQL work regressed: {name}")
        sql_rows[name] = rows

    live = _mapping(report.get("live_api_worker"), "list/delete live API/Worker")
    retrieval = _mapping(live.get("retrieval"), "list/delete live retrieval")
    live_delete = _mapping(live.get("delete"), "list/delete live deletion")
    if retrieval.get("returned_marker") is not True:
        raise RuntimeError("list/delete live retrieval marker is missing")
    if (
        live_delete.get("list_invisible") is not True
        or live_delete.get("retrieval_invisible") is not True
    ):
        raise RuntimeError("list/delete live delete visibility regressed")
    return {
        "target_documents": target,
        "first_page_p50_seconds": first_seconds,
        "deep_page_p50_seconds": deep_seconds,
        "delete_seconds": delete_seconds,
        "sql_rows": sql_rows,
    }


def _validate_write_report(
    official: dict[str, object],
    patched: dict[str, object],
    expected_commit: str,
) -> dict[str, object]:
    cleanup, _ = _patched_report(patched, "write", expected_commit)
    if cleanup.get("live_dataset_deleted") is not True:
        raise RuntimeError("write live dataset cleanup failed")
    if official.get("status") != "passed":
        raise RuntimeError("official write baseline did not pass")
    official_profile = _mapping(official.get("write_profile"), "official write profile")
    patch_profile = _mapping(patched.get("write_profile"), "patched write profile")
    official_throughput = _finite_number(
        official_profile.get("chunks_per_second"),
        "official write throughput",
        positive=True,
    )
    patch_throughput = _finite_number(
        patch_profile.get("chunks_per_second"),
        "patched write throughput",
        positive=True,
    )
    throughput_ratio = patch_throughput / official_throughput
    if throughput_ratio < 1.25:
        raise RuntimeError("write throughput regressed below the 1.25x gate")
    if patch_profile.get("marker_returned") is not True:
        raise RuntimeError("write retrieval marker is missing")
    configuration = _mapping(patched.get("configuration"), "write configuration")
    if (
        configuration.get("doc_bulk_size") != 32
        or configuration.get("embedding_concurrency") != 8
        or configuration.get("root_scale_documents") != 250_000
    ):
        raise RuntimeError("write benchmark configuration drifted")
    root = _mapping(patched.get("root_lookup_profile"), "root lookup profile")
    if root.get("target_documents") != 250_000:
        raise RuntimeError("root lookup scale drifted")
    official_lookup = _mapping(
        root.get("official_column_comparison"), "official root lookup"
    )
    patched_lookup = _mapping(
        root.get("patched_constant_lookup"), "patched root lookup"
    )
    official_rows = _mapping(
        official_lookup.get("analysis"), "official root lookup analysis"
    ).get("total_rows_across_loops")
    patched_rows = _mapping(
        patched_lookup.get("analysis"), "patched root lookup analysis"
    ).get("total_rows_across_loops")
    if (
        isinstance(official_rows, bool)
        or not isinstance(official_rows, int)
        or official_rows < 100_000
        or isinstance(patched_rows, bool)
        or not isinstance(patched_rows, int)
        or patched_rows > 100
    ):
        raise RuntimeError("root lookup SQL work regressed")
    return {
        "official_chunks_per_second": official_throughput,
        "patched_chunks_per_second": patch_throughput,
        "throughput_ratio": round(throughput_ratio, 6),
        "official_lookup_rows": official_rows,
        "patched_lookup_rows": patched_rows,
    }


def _validate_retrieval_report(
    official: dict[str, object],
    patched: dict[str, object],
    expected_commit: str,
) -> dict[str, object]:
    cleanup, _ = _patched_report(patched, "retrieval", expected_commit)
    if official.get("status") != "passed":
        raise RuntimeError("official retrieval baseline did not pass")
    if (
        cleanup.get("dataset_deleted") is not True
        or cleanup.get("synthetic_deleted") != 12_000
        or cleanup.get("synthetic_delete_errors") != 0
    ):
        raise RuntimeError("retrieval synthetic cleanup regressed")
    retrieval = _mapping(patched.get("retrieval_profile"), "retrieval profile")
    if retrieval.get("marker_returned") is not True:
        raise RuntimeError("retrieval marker is missing")
    levels = retrieval.get("levels")
    if not isinstance(levels, list) or [level.get("top_k") for level in levels] != [5, 64, 2048]:
        raise RuntimeError("retrieval levels drifted")
    level_seconds: dict[str, float] = {}
    for level in levels:
        mapping = _mapping(level, "retrieval level")
        seconds = _finite_number(mapping.get("elapsed_seconds"), "retrieval latency")
        if seconds > 3.0:
            raise RuntimeError("retrieval latency regressed")
        level_seconds[str(mapping["top_k"])] = seconds
    boundary = _mapping(retrieval.get("boundary"), "retrieval boundary")
    boundary_message = str(boundary.get("message", ""))
    boundary_seconds = _finite_number(
        boundary.get("elapsed_seconds"), "retrieval boundary latency"
    )
    if (
        boundary.get("requested_top_k") != 5001
        or boundary.get("code") == 0
        or not (
            "BadRequestError" in boundary_message
            or "x_content_parse_exception" in boundary_message
        )
        or boundary_seconds > 3.0
    ):
        raise RuntimeError("retrieval boundary regressed")
    chunks = _mapping(patched.get("chunk_read_profile"), "chunk read profile")
    first_page = _mapping(chunks.get("first_page"), "chunk first page")
    deep_page = _mapping(chunks.get("deep_page"), "chunk deep page")
    if chunks.get("target_synthetic_chunks") != 12_000:
        raise RuntimeError("chunk synthetic scale drifted")
    if first_page.get("returned") != 100 or deep_page.get("returned") != 100:
        raise RuntimeError("chunk pages are incomplete")
    first_seconds = _finite_number(first_page.get("elapsed_seconds"), "chunk first page")
    deep_seconds = _finite_number(deep_page.get("elapsed_seconds"), "chunk deep page")
    if first_seconds > 1.0 or deep_seconds > 2.0:
        raise RuntimeError("chunk read latency regressed")
    oversize = _mapping(chunks.get("oversize_page"), "chunk oversize page")
    if oversize.get("code") == 0:
        raise RuntimeError("chunk oversize page was accepted")
    if chunks.get("single_chunk_runtime_fields_absent") is not True:
        raise RuntimeError("chunk runtime fields leaked")
    return {
        "levels_seconds": level_seconds,
        "boundary_seconds": boundary_seconds,
        "first_page_seconds": first_seconds,
        "deep_page_seconds": deep_seconds,
    }


def validate_patchset_reports(
    list_report: dict[str, object],
    official_write_report: dict[str, object],
    write_report: dict[str, object],
    official_retrieval_report: dict[str, object],
    retrieval_report: dict[str, object],
    *,
    expected_commit: str = EXPECTED_PATCH_HEAD,
) -> dict[str, object]:
    if len(expected_commit) != 40:
        raise RuntimeError("expected patch head must be a full commit")
    upgrade_scale = _validate_list_report(list_report, expected_commit)
    write = _validate_write_report(
        official_write_report, write_report, expected_commit
    )
    retrieval = _validate_retrieval_report(
        official_retrieval_report, retrieval_report, expected_commit
    )
    return {
        "schema_version": 1,
        "status": "passed",
        "ragflow_commit": expected_commit,
        "upgrade_scale": upgrade_scale,
        "write": write,
        "retrieval": retrieval,
    }


def _load_report(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"report is not an object: {path}")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate the complete RAGFlow v0.26.4 common-agent patchset"
    )
    parser.add_argument("--list-report", type=Path, required=True)
    parser.add_argument("--official-write-report", type=Path, required=True)
    parser.add_argument("--write-report", type=Path, required=True)
    parser.add_argument("--official-retrieval-report", type=Path, required=True)
    parser.add_argument("--retrieval-report", type=Path, required=True)
    parser.add_argument("--expected-commit", default=EXPECTED_PATCH_HEAD)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = validate_patchset_reports(
        _load_report(args.list_report),
        _load_report(args.official_write_report),
        _load_report(args.write_report),
        _load_report(args.official_retrieval_report),
        _load_report(args.retrieval_report),
        expected_commit=args.expected_commit,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(args.output)


if __name__ == "__main__":
    main()
