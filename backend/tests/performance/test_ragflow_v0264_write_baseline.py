from pathlib import Path

import pytest

from tests.performance.ragflow_v0264_write_baseline import (
    build_write_documents,
    parse_bounded_positive_int,
    source_audit,
)


def test_write_documents_are_bounded_unique_and_contain_the_retrieval_marker() -> None:
    generated = build_write_documents(
        document_count=3,
        paragraphs_per_document=4,
        words_per_paragraph=8,
        marker="R2-04-MARKER",
    )

    assert [name for name, _ in generated] == [
        "r2-04-write-00.txt",
        "r2-04-write-01.txt",
        "r2-04-write-02.txt",
    ]
    assert len({content for _, content in generated}) == 3
    assert b"R2-04-MARKER" in generated[0][1]
    assert all(content for _, content in generated)

    with pytest.raises(ValueError, match="document_count"):
        build_write_documents(
            document_count=0,
            paragraphs_per_document=4,
            words_per_paragraph=8,
            marker="marker",
        )


def test_bounded_positive_integer_parser_closes_invalid_configuration() -> None:
    assert parse_bounded_positive_int("32", name="bulk", maximum=128) == 32

    for invalid in ("", "0", "-1", "129", "many"):
        with pytest.raises(ValueError, match="bulk"):
            parse_bounded_positive_int(invalid, name="bulk", maximum=128)


def test_source_audit_distinguishes_official_and_write_patched_shapes(
    tmp_path: Path,
) -> None:
    root = tmp_path / "ragflow"
    limiter = root / "rag/svr/task_executor_limiter.py"
    file_service = root / "api/db/services/file_service.py"
    limiter.parent.mkdir(parents=True)
    file_service.parent.mkdir(parents=True)
    limiter.write_text(
        "embed_limiter = LoopLocalSemaphore(MAX_CONCURRENT_CHUNK_BUILDERS)",
        encoding="utf-8",
    )
    file_service.write_text(
        "query.where(model.tenant_id == tenant_id, model.parent_id == model.id)",
        encoding="utf-8",
    )
    assert source_audit(root, "official")["mode"] == "official"

    limiter.write_text(
        "MAX_CONCURRENT_EMBEDDINGS = 1\n"
        "embed_limiter = LoopLocalSemaphore(MAX_CONCURRENT_EMBEDDINGS)",
        encoding="utf-8",
    )
    file_service.write_text(
        'query.where(model.tenant_id == tenant_id, model.name == "/", '
        "model.type == FileType.FOLDER.value)\n"
        "if file.parent_id == file.id: return file.to_dict()",
        encoding="utf-8",
    )
    audit = source_audit(root, "patched")
    assert audit["mode"] == "patched"
    checks = audit["checks"]
    assert isinstance(checks, dict)
    assert all(checks.values())
    assert checks["tika_startup_guard_absent"] is True

    with pytest.raises(RuntimeError, match="source shape"):
        source_audit(root, "official")


def test_formal_write_runner_pins_runtime_configuration_and_secrets() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    runner = (repository_root / "scripts/ragflow-v0264-write-benchmark.sh").read_text(
        encoding="utf-8"
    )

    assert "COMMON_AGENT_RAGFLOW_WRITE_EXPECTED_COMMIT" in runner
    assert "COMMON_AGENT_RAGFLOW_WRITE_IMAGE_REVISION" in runner
    assert "RAGFLOW_PATCH_HEAD" in runner
    assert 'COMMON_AGENT_RAGFLOW_WRITE_SOURCE_MODE:-patched' in runner
    assert 'COMMON_AGENT_RAGFLOW_WRITE_DOC_BULK_SIZE:-32' in runner
    assert 'COMMON_AGENT_RAGFLOW_WRITE_EMBEDDING_CONCURRENCY:-8' in runner
    assert "COMMON_AGENT_RAGFLOW_WRITE_DOC_BULK_SIZE" in runner
    assert "COMMON_AGENT_RAGFLOW_WRITE_EMBEDDING_CONCURRENCY" in runner
    assert '[[ "${SOURCE_MODE}" == "patched" && -z "${EXPECTED_IMAGE_REVISION}" ]]' in runner
    assert '"${ACTUAL_DOC_BULK_SIZE}" != "${DOC_BULK_SIZE}"' in runner
    assert '"${ACTUAL_EMBEDDING_CONCURRENCY}" != "${EMBEDDING_CONCURRENCY}"' in runner
    assert "--api-key-file" in runner
    assert "--mysql-password" not in runner
    assert "RAGFLOW_BENCHMARK_MYSQL_PASSWORD" in runner
    assert "STACK_STARTED_BY_RUNNER" in runner
    assert "restore_api_if_needed" in runner
    assert "trap cleanup EXIT" in runner
