from __future__ import annotations

import argparse
import math
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from tests.performance.ragflow_v0264_baseline import (
    EXPECTED_RAGFLOW_COMMIT,
    EXPECTED_RAGFLOW_VERSION,
    RagFlowApi,
    ResourceMonitor,
    ScaleDatabase,
    ScalePrefixes,
    _connect_mysql,
    _read_api_key,
    _run_command,
    _write_report,
)


def parse_bounded_positive_int(raw: str, *, name: str, maximum: int) -> int:
    try:
        value = int(raw)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer within 1..{maximum}") from error
    if value < 1 or value > maximum:
        raise ValueError(f"{name} must be an integer within 1..{maximum}")
    return value


def build_write_documents(
    *,
    document_count: int,
    paragraphs_per_document: int,
    words_per_paragraph: int,
    marker: str,
) -> tuple[tuple[str, bytes], ...]:
    if not 1 <= document_count <= 32:
        raise ValueError("document_count must be within 1..32")
    if not 1 <= paragraphs_per_document <= 256:
        raise ValueError("paragraphs_per_document must be within 1..256")
    if not 1 <= words_per_paragraph <= 2048:
        raise ValueError("words_per_paragraph must be within 1..2048")
    if not marker.strip() or len(marker) > 256:
        raise ValueError("marker must be non-empty and no longer than 256 characters")

    documents: list[tuple[str, bytes]] = []
    for document_index in range(document_count):
        paragraphs: list[str] = []
        for paragraph_index in range(paragraphs_per_document):
            words = " ".join(
                f"term{document_index}_{paragraph_index}_{word_index % 97}"
                for word_index in range(words_per_paragraph)
            )
            retrieval_marker = marker if document_index == 0 and paragraph_index == 0 else ""
            paragraphs.append(
                f"document {document_index} paragraph {paragraph_index} "
                f"{retrieval_marker} {words}."
            )
        documents.append(
            (
                f"r2-04-write-{document_index:02d}.txt",
                ("\n\n".join(paragraphs) + "\n").encode(),
            )
        )
    return tuple(documents)


def source_audit(source_root: Path, source_mode: str) -> dict[str, object]:
    limiter = (source_root / "rag/svr/task_executor_limiter.py").read_text(
        encoding="utf-8"
    )
    file_service = (source_root / "api/db/services/file_service.py").read_text(
        encoding="utf-8"
    )
    tika_guard_path = source_root / "rag/utils/tika_parser.py"
    parser_sources = tuple(
        path.read_text(encoding="utf-8")
        for path in (source_root / "rag").rglob("*.py")
        if path != tika_guard_path
    )
    direct_tika_callers = sum(
        "from tika import parser as tika_parser" in source for source in parser_sources
    )
    guarded_tika_callers = sum(
        "from rag.utils import tika_parser" in source for source in parser_sources
    )

    if source_mode == "official":
        checks: dict[str, bool] = {
            "embedding_limiter_reuses_chunk_limit": (
                "embed_limiter = LoopLocalSemaphore(MAX_CONCURRENT_CHUNK_BUILDERS)"
                in limiter
            ),
            "root_lookup_compares_columns": (
                "parent_id == cls.model.id" in file_service
                or "parent_id == model.id" in file_service
            ),
            "tika_callers_bypass_startup_guard": direct_tika_callers > 0,
            "tika_startup_guard_absent": not tika_guard_path.exists(),
        }
    elif source_mode == "patched":
        tika_guard = tika_guard_path.read_text(encoding="utf-8")
        checks = {
            "independent_embedding_limiter": (
                "MAX_CONCURRENT_EMBEDDINGS" in limiter
                and "embed_limiter = LoopLocalSemaphore(MAX_CONCURRENT_EMBEDDINGS)"
                in limiter
            ),
            "indexable_root_lookup": (
                'model.name == "/"' in file_service
                and "model.type == FileType.FOLDER.value" in file_service
                and "file.parent_id == file.id" in file_service
                and "parent_id == cls.model.id" not in file_service
            ),
            "tika_startup_guard": (
                "_startup_lock = threading.Lock()" in tika_guard
                and "with _startup_lock:" in tika_guard
                and "parsed = _from_buffer(blob)" in tika_guard
            ),
            "all_tika_callers_guarded": (
                direct_tika_callers == 0 and guarded_tika_callers >= 1
            ),
        }
    else:
        raise RuntimeError(f"unsupported RAGFlow source mode: {source_mode}")
    if not all(checks.values()):
        raise RuntimeError(
            f"RAGFlow v0.26.4 {source_mode} write source shape no longer matches"
        )
    return {"mode": source_mode, "checks": checks}


def _wait_for_documents(
    api: RagFlowApi,
    *,
    dataset_id: str,
    document_ids: tuple[str, ...],
    timeout_seconds: float,
) -> tuple[dict[str, float], dict[str, dict[str, Any]]]:
    started = time.monotonic()
    deadline = started + timeout_seconds
    completed_at: dict[str, float] = {}
    final_documents: dict[str, dict[str, Any]] = {}
    expected = set(document_ids)
    while time.monotonic() < deadline:
        payload = api.list_documents(dataset_id, page_size=100)
        documents = {
            str(item.get("id")): item
            for item in payload["docs"]
            if isinstance(item, dict) and item.get("id") in expected
        }
        for document_id, document in documents.items():
            run_status = str(document.get("run", "")).upper()
            if run_status in {"4", "FAIL", "FAILED"}:
                raise RuntimeError("RAGFlow write benchmark document parsing failed")
            if run_status in {"3", "DONE", "COMPLETED"}:
                completed_at.setdefault(document_id, time.monotonic() - started)
                final_documents[document_id] = document
        if len(completed_at) == len(expected):
            return completed_at, final_documents
        time.sleep(0.5)
    raise TimeoutError("RAGFlow write benchmark parsing timed out")


def _write_profile(
    api: RagFlowApi,
    *,
    dataset_id: str,
    document_count: int,
    paragraphs_per_document: int,
    words_per_paragraph: int,
    timeout_seconds: float,
    rerank_model: str,
) -> dict[str, object]:
    marker = f"R2-04-WRITE-{uuid4().hex}"
    documents = build_write_documents(
        document_count=document_count,
        paragraphs_per_document=paragraphs_per_document,
        words_per_paragraph=words_per_paragraph,
        marker=marker,
    )
    upload_started = time.monotonic()
    document_ids = api.upload_documents(dataset_id, documents)
    upload_seconds = time.monotonic() - upload_started
    parse_started = time.monotonic()
    api.start_parsing(dataset_id, document_ids)
    completion, final_documents = _wait_for_documents(
        api,
        dataset_id=dataset_id,
        document_ids=document_ids,
        timeout_seconds=timeout_seconds,
    )
    parse_seconds = time.monotonic() - parse_started
    chunk_count = sum(
        int(document.get("chunk_count", document.get("chunk_num", 0)) or 0)
        for document in final_documents.values()
    )
    if chunk_count < document_count:
        raise RuntimeError("RAGFlow write benchmark produced too few chunks")

    retrieval_started = time.monotonic()
    retrieval = api.retrieve(
        dataset_id,
        f"What is the unique marker {marker}?",
        rerank_model=rerank_model,
    )
    retrieval_seconds = time.monotonic() - retrieval_started
    marker_returned = any(
        marker in str(chunk.get("content", ""))
        for chunk in retrieval["chunks"]
        if isinstance(chunk, dict)
    )
    if not marker_returned:
        raise RuntimeError("RAGFlow write benchmark marker was not retrievable")
    end_to_end = upload_seconds + parse_seconds
    return {
        "documents": document_count,
        "bytes": sum(len(content) for _, content in documents),
        "chunks": chunk_count,
        "upload_seconds": round(upload_seconds, 6),
        "parse_seconds": round(parse_seconds, 6),
        "end_to_end_seconds": round(end_to_end, 6),
        "documents_per_second": round(document_count / end_to_end, 6),
        "chunks_per_second": round(chunk_count / parse_seconds, 6),
        "first_document_seconds": round(min(completion.values()), 6),
        "last_document_seconds": round(max(completion.values()), 6),
        "retrieval_seconds": round(retrieval_seconds, 6),
        "marker_returned": True,
    }


def _root_lookup_profile(
    database: ScaleDatabase,
    *,
    dataset_id: str,
    target_documents: int,
    prefixes: ScalePrefixes,
) -> dict[str, object]:
    insert_seconds = database.seed_to_count(
        dataset_id=dataset_id,
        target_count=target_documents,
        prefixes=prefixes,
    )
    tenant_id = database.dataset_identity(dataset_id)[0]
    official_plan, official_analysis = database.explain(
        "SELECT f.* FROM file AS f "
        "WHERE f.tenant_id = %s AND f.parent_id = f.id",
        (tenant_id,),
    )
    patched_plan, patched_analysis = database.explain(
        "SELECT f.* FROM file AS f "
        "WHERE f.tenant_id = %s AND f.name = %s AND f.type = %s "
        "ORDER BY f.create_time ASC",
        (tenant_id, "/", "folder"),
    )
    return {
        "target_documents": target_documents,
        "insert_seconds": round(insert_seconds, 6),
        "official_column_comparison": {
            "analysis": asdict(official_analysis),
            "plan": official_plan,
        },
        "patched_constant_lookup": {
            "analysis": asdict(patched_analysis),
            "plan": patched_plan,
        },
    }


def run(args: argparse.Namespace) -> dict[str, object]:
    source_root = args.source_root.resolve()
    source_commit = _run_command("git", "rev-parse", "HEAD", cwd=source_root)
    if source_commit != args.expected_source_commit:
        raise RuntimeError("RAGFlow write benchmark source commit mismatch")
    if _run_command("git", "status", "--porcelain", cwd=source_root):
        raise RuntimeError("RAGFlow write benchmark source checkout must be clean")

    api = RagFlowApi(
        base_url=args.base_url,
        api_key=_read_api_key(args.api_key_file),
        timeout_seconds=args.timeout_seconds,
    )
    connection = _connect_mysql(args)
    database = ScaleDatabase(connection)
    monitor = ResourceMonitor(interval_seconds=args.resource_interval_seconds)
    live_dataset_id: str | None = None
    scale_dataset_id: str | None = None
    prefixes = ScalePrefixes(
        document=uuid4().hex[:8],
        file=uuid4().hex[:8],
        link=uuid4().hex[:8],
    )
    cleanup: dict[str, object] = {}
    monitor.start()
    try:
        version = api.version()
        if version != EXPECTED_RAGFLOW_VERSION:
            raise RuntimeError("RAGFlow write benchmark version mismatch")
        report: dict[str, object] = {
            "schema_version": 1,
            "ragflow_version": version,
            "ragflow_commit": source_commit,
            "ragflow_upstream_commit": EXPECTED_RAGFLOW_COMMIT,
            "source_audit": source_audit(source_root, args.source_mode),
            "configuration": {
                "doc_bulk_size": args.doc_bulk_size,
                "embedding_concurrency": args.embedding_concurrency,
                "document_count": args.document_count,
                "paragraphs_per_document": args.paragraphs_per_document,
                "words_per_paragraph": args.words_per_paragraph,
                "root_scale_documents": args.root_scale_documents,
            },
            "started_at": datetime.now(UTC).isoformat(),
        }
        args.partial_report = report
        run_id = uuid4().hex[:12]
        live_dataset_id = api.create_dataset(f"common-agent-r2-04-write-{run_id}")
        report["write_profile"] = _write_profile(
            api,
            dataset_id=live_dataset_id,
            document_count=args.document_count,
            paragraphs_per_document=args.paragraphs_per_document,
            words_per_paragraph=args.words_per_paragraph,
            timeout_seconds=args.parse_timeout_seconds,
            rerank_model=args.rerank_model,
        )
        api.delete_dataset(live_dataset_id)
        cleanup["live_dataset_deleted"] = True
        live_dataset_id = None

        scale_dataset_id = api.create_dataset(f"common-agent-r2-04-root-{run_id}")
        report["root_lookup_profile"] = _root_lookup_profile(
            database,
            dataset_id=scale_dataset_id,
            target_documents=args.root_scale_documents,
            prefixes=prefixes,
        )
        report["completed_at"] = datetime.now(UTC).isoformat()
        return report
    finally:
        errors: list[str] = []
        if scale_dataset_id is not None:
            try:
                cleanup["scale"] = database.cleanup(
                    dataset_id=scale_dataset_id,
                    prefixes=prefixes,
                )
            except Exception as error:
                errors.append(type(error).__name__)
        if live_dataset_id is not None:
            try:
                api.delete_dataset(live_dataset_id)
                cleanup["live_dataset_deleted"] = True
            except Exception as error:
                errors.append(type(error).__name__)
        cleanup["errors"] = errors
        try:
            cleanup["resources"] = monitor.stop()
        finally:
            connection.close()
            api.close()
        args.cleanup_result.clear()
        args.cleanup_result.update(cleanup)


def determine_status(report: dict[str, object]) -> str:
    cleanup = report.get("cleanup")
    if not isinstance(cleanup, dict) or cleanup.get("errors") != []:
        raise RuntimeError("RAGFlow write benchmark cleanup failed")
    resources = cleanup.get("resources")
    if not isinstance(resources, dict) or resources.get("sampling_errors") != []:
        raise RuntimeError("RAGFlow write benchmark resource sampling failed")
    final_state = resources.get("final_container_state")
    if not isinstance(final_state, dict):
        raise RuntimeError("RAGFlow write benchmark container state is missing")
    api_state = final_state.get("common-agent-ragflow-api")
    if not isinstance(api_state, dict) or api_state.get("oom_killed") is not False:
        raise RuntimeError("RAGFlow write benchmark API was OOM-killed")
    write_profile = report.get("write_profile")
    if not isinstance(write_profile, dict) or write_profile.get("marker_returned") is not True:
        raise RuntimeError("RAGFlow write benchmark retrieval proof is missing")
    if not math.isfinite(float(write_profile.get("chunks_per_second", 0))):
        raise RuntimeError("RAGFlow write benchmark throughput is invalid")
    return "passed"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="RAGFlow v0.26.4 write concurrency and root lookup benchmark"
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:19380")
    parser.add_argument("--api-key-file", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--source-mode", choices=("official", "patched"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mysql-host", default="127.0.0.1")
    parser.add_argument("--mysql-port", type=int, default=19432)
    parser.add_argument("--mysql-user", default="root")
    parser.add_argument("--doc-bulk-size", type=int, required=True)
    parser.add_argument("--embedding-concurrency", type=int, required=True)
    parser.add_argument("--document-count", type=int, default=4)
    parser.add_argument("--paragraphs-per-document", type=int, default=32)
    parser.add_argument("--words-per-paragraph", type=int, default=600)
    parser.add_argument("--root-scale-documents", type=int, default=250000)
    parser.add_argument("--timeout-seconds", type=float, default=300.0)
    parser.add_argument("--parse-timeout-seconds", type=float, default=900.0)
    parser.add_argument("--resource-interval-seconds", type=float, default=1.0)
    parser.add_argument(
        "--rerank-model",
        default="qwen3-rerank@common-agent-rerank@OpenAI-API-Compatible",
    )
    return parser


def main() -> None:
    args = _parser().parse_args()
    try:
        args.doc_bulk_size = parse_bounded_positive_int(
            str(args.doc_bulk_size), name="doc_bulk_size", maximum=1024
        )
        args.embedding_concurrency = parse_bounded_positive_int(
            str(args.embedding_concurrency),
            name="embedding_concurrency",
            maximum=128,
        )
        args.document_count = parse_bounded_positive_int(
            str(args.document_count), name="document_count", maximum=32
        )
        args.paragraphs_per_document = parse_bounded_positive_int(
            str(args.paragraphs_per_document),
            name="paragraphs_per_document",
            maximum=256,
        )
        args.words_per_paragraph = parse_bounded_positive_int(
            str(args.words_per_paragraph),
            name="words_per_paragraph",
            maximum=2048,
        )
        args.root_scale_documents = parse_bounded_positive_int(
            str(args.root_scale_documents),
            name="root_scale_documents",
            maximum=1_000_000,
        )
    except ValueError as error:
        raise SystemExit(str(error)) from error
    if args.timeout_seconds <= 0 or args.parse_timeout_seconds <= 0:
        raise SystemExit("timeouts must be positive")
    if not 0 < args.resource_interval_seconds <= 10:
        raise SystemExit("resource interval must be within (0, 10]")

    args.cleanup_result = {}
    args.partial_report = None
    report: dict[str, object] | None = None
    try:
        report = run(args)
    except BaseException as error:
        partial = args.partial_report
        if isinstance(partial, dict):
            partial["completed_at"] = datetime.now(UTC).isoformat()
            partial["cleanup"] = args.cleanup_result
            partial["status"] = "failed"
            partial["failure"] = {"type": type(error).__name__}
            _write_report(args.output, partial)
        raise
    if report is None:
        raise RuntimeError("RAGFlow write benchmark produced no report")
    report["cleanup"] = args.cleanup_result
    try:
        report["status"] = determine_status(report)
    except Exception as error:
        report["status"] = "failed"
        report["failure"] = {"type": type(error).__name__}
        _write_report(args.output, report)
        raise
    _write_report(args.output, report)
    print(args.output)


if __name__ == "__main__":
    main()
