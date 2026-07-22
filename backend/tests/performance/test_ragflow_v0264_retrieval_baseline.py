from pathlib import Path

import pytest

from tests.performance.ragflow_v0264_retrieval_baseline import (
    build_synthetic_chunks,
    determine_status,
    parse_scale_count,
    source_audit,
)


def test_synthetic_chunks_are_bounded_sortable_and_vector_free() -> None:
    chunks = build_synthetic_chunks(
        count=3,
        prefix="r205",
        dataset_id="dataset",
        document_id="document",
    )

    assert [chunk["id"] for chunk in chunks] == ["r20500000000", "r20500000001", "r20500000002"]
    assert [chunk["chunk_order_int"] for chunk in chunks] == [1_000_000, 1_000_001, 1_000_002]
    assert all(chunk["doc_id"] == "document" for chunk in chunks)
    assert all(not any(key.endswith("_vec") for key in chunk) for chunk in chunks)

    with pytest.raises(ValueError, match="count"):
        build_synthetic_chunks(
            count=0,
            prefix="r205",
            dataset_id="dataset",
            document_id="document",
        )


def test_scale_count_parser_is_positive_and_bounded() -> None:
    assert parse_scale_count("12000") == 12000
    for invalid in ("", "0", "1000001", "many"):
        with pytest.raises(ValueError, match="scale_count"):
            parse_scale_count(invalid)


def test_source_audit_distinguishes_official_and_patched_boundaries(tmp_path: Path) -> None:
    root = tmp_path / "ragflow"
    pagination = root / "api/utils/pagination_utils.py"
    chunk = root / "api/apps/restful_apis/chunk_api.py"
    dify = root / "api/apps/restful_apis/dify_retrieval_api.py"
    bot = root / "api/apps/restful_apis/bot_api.py"
    search = root / "rag/nlp/search.py"
    for path in (pagination, chunk, dify, bot, search):
        path.parent.mkdir(parents=True, exist_ok=True)
    pagination.write_text("REST_API_MAX_PAGE_SIZE = 100", encoding="utf-8")
    chunk.write_text(
        'validate_rest_api_page_size\ndef _strip_chunk_runtime_fields(): "_vec$|_sm_|_tks|_ltks"\n'
        'top = int(req.get("top_k", 1024))',
        encoding="utf-8",
    )
    dify.write_text('top = int(retrieval_setting.get("top_k", 1024))', encoding="utf-8")
    bot.write_text('top = int(req.get("top_k", 1024))', encoding="utf-8")
    search.write_text(
        'def _rerank_window(): math.ceil(64 / page_size)\n'
        'if settings.DOC_ENGINE_OCEANBASE: src.append(f"q_{len(q_vec)}_vec")',
        encoding="utf-8",
    )
    assert source_audit(root, "official")["mode"] == "official"

    pagination.write_text(
        "REST_API_MAX_TOP_K = 2048\ndef validate_rest_api_top_k(top_k): return top_k",
        encoding="utf-8",
    )
    chunk.write_text(
        "validate_rest_api_page_size validate_rest_api_top_k validate_rest_api_top_k\n"
        'def _strip_chunk_runtime_fields(): "_vec$|_sm_|_tks|_ltks"',
        encoding="utf-8",
    )
    dify.write_text("validate_rest_api_top_k validate_rest_api_top_k", encoding="utf-8")
    bot.write_text(
        "validate_rest_api_top_k validate_rest_api_top_k validate_rest_api_top_k",
        encoding="utf-8",
    )
    audit = source_audit(root, "patched")
    assert audit["mode"] == "patched"
    checks = audit["checks"]
    assert isinstance(checks, dict)
    assert all(checks.values())


def test_report_status_requires_mode_specific_boundary_and_cleanup() -> None:
    base: dict[str, object] = {
        "source_audit": {"mode": "patched"},
        "retrieval_profile": {
            "marker_returned": True,
            "boundary": {"code": 102, "message": "less than or equal to 2048"},
            "levels": [
                {"elapsed_seconds": 0.1},
                {"elapsed_seconds": 0.2},
                {"elapsed_seconds": 0.3},
            ],
        },
        "chunk_read_profile": {
            "target_synthetic_chunks": 12000,
            "first_page": {"returned": 100},
            "deep_page": {"returned": 100},
            "oversize_page": {"code": 100},
            "single_chunk_runtime_fields_absent": True,
        },
        "cleanup": {
            "errors": [],
            "synthetic_delete_errors": 0,
            "resources": {
                "sampling_errors": [],
                "final_container_state": {
                    "common-agent-ragflow-api": {"oom_killed": False}
                },
            },
        },
    }

    assert determine_status(base) == "passed"
    boundary = base["retrieval_profile"]
    assert isinstance(boundary, dict)
    boundary["marker_returned"] = False
    with pytest.raises(RuntimeError, match="marker"):
        determine_status(base)


def test_formal_runner_pins_source_image_and_secret_file() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    runner = (repository_root / "scripts/ragflow-v0264-retrieval-benchmark.sh").read_text(
        encoding="utf-8"
    )

    assert "COMMON_AGENT_RAGFLOW_RETRIEVAL_EXPECTED_COMMIT" in runner
    assert "COMMON_AGENT_RAGFLOW_RETRIEVAL_IMAGE_REVISION" in runner
    assert '[[ "${SOURCE_MODE}" == "patched" && -z "${EXPECTED_IMAGE_REVISION}" ]]' in runner
    assert "--api-key-file" in runner
    assert "--mysql-password" not in runner
    assert "RAGFLOW_BENCHMARK_MYSQL_PASSWORD" in runner
    assert "RAGFLOW_BENCHMARK_ELASTIC_PASSWORD" in runner
    assert "--elasticsearch-password" not in runner
    assert "restore_api_if_needed" in runner
