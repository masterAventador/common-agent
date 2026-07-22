from __future__ import annotations

from pathlib import Path

import pytest

from tests.performance.ragflow_v0264_baseline import (
    EXPECTED_RAGFLOW_COMMIT,
    DatabaseCursor,
    ExplainAnalysis,
    ScaleDatabase,
    _scale_query_shapes,
    _source_audit,
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
        "schema_version": 2,
        "ragflow_version": "v0.26.4",
        "ragflow_commit": EXPECTED_RAGFLOW_COMMIT,
        "ragflow_upstream_commit": EXPECTED_RAGFLOW_COMMIT,
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

    patch_commit = "1" * 40
    patched = build_report_header(
        source_commit=patch_commit,
        expected_source_commit=patch_commit,
        source_version="v0.26.4",
        scale_levels=(100,),
        live_document_count=2,
    )
    assert patched["ragflow_commit"] == patch_commit
    assert patched["ragflow_upstream_commit"] == EXPECTED_RAGFLOW_COMMIT


def test_source_audit_distinguishes_official_and_patched_query_shapes(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "ragflow"
    service_path = source_root / "api/db/services/document_service.py"
    api_path = source_root / "api/apps/restful_apis/document_api.py"
    service_path.parent.mkdir(parents=True)
    api_path.parent.mkdir(parents=True)
    service_path.write_text(
        """
class DocumentService:
    def get_by_kb_id(self):
        docs = docs.join(File2Document)
        count = docs.count()
""".strip(),
        encoding="utf-8",
    )
    api_path.write_text(
        """
async def delete_documents():
    doc_ids = [doc.id for doc in DocumentService.query(kb_id=dataset_id)]
    dataset_doc_ids = {doc.id for doc in DocumentService.query(kb_id=dataset_id)}
""".strip(),
        encoding="utf-8",
    )
    assert _source_audit(source_root, "official")["mode"] == "official"

    service_path.write_text(
        """
class DocumentService:
    def get_by_kb_id(self):
        count_query = apply_filters(model.select(fn.COUNT(model.id)))
        count = count_query.scalar()
        page_query = apply_filters(model.select(model.id))
        page_ids = [row.id for row in page_query.paginate(page_number, items_per_page)]
        docs = docs.where(model.id.in_(page_ids))

    def get_ids_by_kb_id(self):
        query = query.where(model.id.in_(doc_ids))
        return [row.id for row in query.iterator()]
""".strip(),
        encoding="utf-8",
    )
    api_path.write_text(
        """
async def delete_documents():
    owned_doc_ids = DocumentService.get_ids_by_kb_id(dataset_id, doc_ids)
""".strip(),
        encoding="utf-8",
    )
    audit = _source_audit(source_root, "patched")
    assert audit["mode"] == "patched"
    checks = audit["checks"]
    assert isinstance(checks, dict)
    assert all(checks.values())

    service_path.write_text(
        service_path.read_text(encoding="utf-8").replace(
            "return [row.id for row in query.iterator()]",
            "return query.scalars().iterator()",
        ),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="source shape"):
        _source_audit(source_root, "patched")

    with pytest.raises(RuntimeError, match="source shape"):
        _source_audit(source_root, "official")


def test_scale_query_shapes_match_the_measured_source_mode() -> None:
    official = _scale_query_shapes("official")
    assert set(official) == {
        "joined_count",
        "deep_page",
        "delete_ownership_materialization",
    }
    assert "file2document" in official["joined_count"]
    assert "file2document" in official["deep_page"]
    assert "SELECT d.*" in official["delete_ownership_materialization"]

    patched = _scale_query_shapes("patched")
    assert set(patched) == {
        "direct_count",
        "page_ids",
        "page_details",
        "delete_ownership_lookup",
    }
    assert "JOIN" not in patched["direct_count"]
    assert "JOIN" not in patched["page_ids"]
    assert "file2document" not in patched["page_details"]
    assert "user_canvas" in patched["page_details"]
    assert "d.id IN ({page_ids})" in patched["page_details"]
    assert "d.id IN (%s)" in patched["delete_ownership_lookup"]

    with pytest.raises(RuntimeError, match="unsupported RAGFlow source mode"):
        _scale_query_shapes("unknown")


def test_formal_runner_pins_source_and_keeps_secrets_out_of_arguments() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    runner = (repository_root / "scripts/ragflow-v0264-baseline.sh").read_text(
        encoding="utf-8"
    )

    assert "infra/ragflow/patchset.env" in runner
    assert "RAGFLOW_PATCH_HEAD" in runner
    assert 'COMMON_AGENT_RAGFLOW_BENCHMARK_SOURCE_MODE:-patched' in runner
    assert "RAGFLOW_BENCHMARK_MYSQL_PASSWORD" in runner
    assert "--api-key-file" in runner
    assert "--mysql-password" not in runner
    assert "STACK_STARTED_BY_RUNNER" in runner
    assert "restore_api_if_needed" in runner
    assert "COMMON_AGENT_RAGFLOW_BENCHMARK_SOURCE" in runner
    assert "COMMON_AGENT_RAGFLOW_BENCHMARK_EXPECTED_COMMIT" in runner
    assert "COMMON_AGENT_RAGFLOW_BENCHMARK_IMAGE_REVISION" in runner
    assert (
        '[[ "${SOURCE_MODE}" == "patched" && -z "${EXPECTED_IMAGE_REVISION}" ]]'
        in runner
    )
    assert "--expected-source-commit" in runner
    assert "--source-mode" in runner


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
