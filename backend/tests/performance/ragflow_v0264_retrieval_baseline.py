from __future__ import annotations

import argparse
import json
import math
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx

from tests.performance.ragflow_v0264_baseline import (
    EXPECTED_RAGFLOW_COMMIT,
    EXPECTED_RAGFLOW_VERSION,
    RagFlowApi,
    ResourceMonitor,
    ScaleDatabase,
    _connect_mysql,
    _read_api_key,
    _run_command,
    _write_report,
)
from tests.performance.ragflow_v0264_write_baseline import (
    _wait_for_documents,
    build_write_documents,
)


def parse_scale_count(raw: str) -> int:
    try:
        value = int(raw)
    except ValueError as error:
        raise ValueError("scale_count must be an integer within 1..1000000") from error
    if value < 1 or value > 1_000_000:
        raise ValueError("scale_count must be an integer within 1..1000000")
    return value


def build_synthetic_chunks(
    *,
    count: int,
    prefix: str,
    dataset_id: str,
    document_id: str,
    start_index: int = 0,
) -> tuple[dict[str, object], ...]:
    if count < 1 or count > 1_000_000:
        raise ValueError("count must be within 1..1000000")
    if not prefix or len(prefix) > 32:
        raise ValueError("prefix must be non-empty and no longer than 32 characters")
    if not dataset_id or not document_id:
        raise ValueError("dataset_id and document_id must be non-empty")
    return tuple(
        {
            "id": f"{prefix}{index:08d}",
            "doc_id": document_id,
            "kb_id": dataset_id,
            "docnm_kwd": "r2-05-scale.txt",
            "content_with_weight": f"R2-05 synthetic chunk read scale row {index}",
            "content_ltks": f"r2 05 synthetic chunk read scale row {index}",
            "available_int": 1,
            "chunk_order_int": 1_000_000 + index,
            "page_num_int": 1_000_000 + index,
            "top_int": index,
            "create_timestamp_flt": 1_700_000_000_000 + index,
            "important_kwd": ["r2-05", "scale"],
            "question_kwd": [],
            "position_int": [],
        }
        for index in range(start_index, start_index + count)
    )


def source_audit(source_root: Path, source_mode: str) -> dict[str, object]:
    pagination = (source_root / "api/utils/pagination_utils.py").read_text(
        encoding="utf-8"
    )
    handlers = {
        "chunk": (source_root / "api/apps/restful_apis/chunk_api.py").read_text(
            encoding="utf-8"
        ),
        "dify": (
            source_root / "api/apps/restful_apis/dify_retrieval_api.py"
        ).read_text(encoding="utf-8"),
        "searchbot": (source_root / "api/apps/restful_apis/bot_api.py").read_text(
            encoding="utf-8"
        ),
    }
    search = (source_root / "rag/nlp/search.py").read_text(encoding="utf-8")
    common_checks = {
        "bounded_rerank_window_present": (
            "def _rerank_window" in search and "math.ceil(64 / page_size)" in search
        ),
        "elasticsearch_main_search_omits_vectors": (
            "if settings.DOC_ENGINE_OCEANBASE:" in search
            and 'src.append(f"q_{len(q_vec)}_vec")' in search
        ),
        "chunk_pages_already_bounded": (
            "validate_rest_api_page_size" in handlers["chunk"]
        ),
        "single_chunk_runtime_fields_stripped": (
            "def _strip_chunk_runtime_fields" in handlers["chunk"]
            and "_vec$|_sm_|_tks|_ltks" in handlers["chunk"]
        ),
    }
    if source_mode == "official":
        mode_checks = {
            "shared_top_k_limit_absent": "REST_API_MAX_TOP_K" not in pagination,
            "chunk_top_k_unbounded": "validate_rest_api_top_k" not in handlers["chunk"],
            "dify_top_k_unbounded": "validate_rest_api_top_k" not in handlers["dify"],
            "searchbot_top_k_unbounded": (
                "validate_rest_api_top_k" not in handlers["searchbot"]
            ),
        }
    elif source_mode == "patched":
        mode_checks = {
            "upstream_shared_top_k_limit_absent": (
                "REST_API_MAX_TOP_K" not in pagination
            ),
            "upstream_chunk_top_k_preserved": (
                "validate_rest_api_top_k" not in handlers["chunk"]
            ),
            "upstream_dify_top_k_preserved": (
                "validate_rest_api_top_k" not in handlers["dify"]
            ),
            "upstream_searchbot_top_k_preserved": (
                "validate_rest_api_top_k" not in handlers["searchbot"]
            ),
        }
    else:
        raise RuntimeError(f"unsupported RAGFlow source mode: {source_mode}")
    checks = {**common_checks, **mode_checks}
    if not all(checks.values()):
        raise RuntimeError(
            f"RAGFlow v0.26.4 {source_mode} retrieval source shape no longer matches"
        )
    return {"mode": source_mode, "checks": checks}


class RetrievalApi(RagFlowApi):
    def envelope(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        response = self._client.request(method, path, **kwargs)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("code"), int):
            raise RuntimeError("RAGFlow response envelope is invalid")
        payload["_response_bytes"] = len(response.content)
        return payload


class ElasticsearchChunkScale:
    def __init__(
        self,
        *,
        base_url: str,
        index_name: str,
        dataset_id: str,
        document_id: str,
        prefix: str,
        timeout_seconds: float,
        username: str,
        password: str,
    ) -> None:
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            auth=httpx.BasicAuth(username=username, password=password),
            timeout=httpx.Timeout(timeout_seconds),
            trust_env=False,
        )
        self._index_name = index_name
        self._dataset_id = dataset_id
        self._document_id = document_id
        self._prefix = prefix
        self._ids: list[str] = []

    def close(self) -> None:
        self._client.close()

    def seed(self, count: int, *, batch_size: int = 1000) -> float:
        started = time.monotonic()
        for start in range(0, count, batch_size):
            chunks = build_synthetic_chunks(
                count=min(batch_size, count - start),
                prefix=self._prefix,
                dataset_id=self._dataset_id,
                document_id=self._document_id,
                start_index=start,
            )
            lines: list[str] = []
            batch_ids: list[str] = []
            for chunk in chunks:
                chunk_id = str(chunk["id"])
                batch_ids.append(chunk_id)
                lines.append(
                    json.dumps(
                        {"index": {"_index": self._index_name, "_id": chunk_id}},
                        separators=(",", ":"),
                    )
                )
                lines.append(json.dumps(chunk, separators=(",", ":")))
            response = self._client.post(
                "/_bulk",
                params={"refresh": "wait_for"},
                headers={"Content-Type": "application/x-ndjson"},
                content="\n".join(lines) + "\n",
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict) or payload.get("errors") is not False:
                raise RuntimeError("R2-05 synthetic chunk bulk insert failed")
            self._ids.extend(batch_ids)
        return time.monotonic() - started

    def cleanup(self, *, batch_size: int = 1000) -> dict[str, int]:
        delete_errors = 0
        deleted = 0
        for start in range(0, len(self._ids), batch_size):
            lines = [
                json.dumps(
                    {"delete": {"_index": self._index_name, "_id": chunk_id}},
                    separators=(",", ":"),
                )
                for chunk_id in self._ids[start : start + batch_size]
            ]
            response = self._client.post(
                "/_bulk",
                params={"refresh": "wait_for"},
                headers={"Content-Type": "application/x-ndjson"},
                content="\n".join(lines) + "\n",
            )
            response.raise_for_status()
            payload = response.json()
            items = payload.get("items") if isinstance(payload, dict) else None
            if not isinstance(items, list):
                raise RuntimeError("R2-05 synthetic chunk cleanup response is invalid")
            for item in items:
                deletion = item.get("delete") if isinstance(item, dict) else None
                status = deletion.get("status") if isinstance(deletion, dict) else None
                if status == 200:
                    deleted += 1
                else:
                    delete_errors += 1
        self._ids.clear()
        return {"deleted": deleted, "delete_errors": delete_errors}


def _retrieval_request(
    api: RetrievalApi,
    *,
    dataset_id: str,
    question: str,
    top_k: int,
    page_size: int,
    rerank_model: str,
) -> tuple[dict[str, Any], float]:
    started = time.monotonic()
    envelope = api.envelope(
        "POST",
        "/api/v1/retrieval",
        json={
            "dataset_ids": [dataset_id],
            "question": question,
            "page": 1,
            "page_size": page_size,
            "top_k": top_k,
            "similarity_threshold": 0.0,
            "vector_similarity_weight": 0.3,
            "rerank_id": rerank_model,
            "highlight": False,
            "include_metadata": True,
        },
    )
    return envelope, time.monotonic() - started


def _profile_retrieval(
    api: RetrievalApi,
    *,
    dataset_id: str,
    marker: str,
    source_mode: str,
    rerank_model: str,
) -> dict[str, object]:
    levels: list[dict[str, object]] = []
    marker_returned = False
    for top_k in (5, 64, 2048):
        envelope, elapsed = _retrieval_request(
            api,
            dataset_id=dataset_id,
            question=f"Find the unique semantic marker {marker}",
            top_k=top_k,
            page_size=5,
            rerank_model=rerank_model,
        )
        if envelope.get("code") != 0:
            raise RuntimeError("bounded R2-05 retrieval request failed")
        data = envelope.get("data")
        chunks = data.get("chunks") if isinstance(data, dict) else None
        if not isinstance(chunks, list):
            raise RuntimeError("bounded R2-05 retrieval chunks are invalid")
        marker_returned = marker_returned or any(
            marker in str(chunk.get("content", ""))
            for chunk in chunks
            if isinstance(chunk, dict)
        )
        levels.append(
            {
                "top_k": top_k,
                "elapsed_seconds": round(elapsed, 6),
                "returned": len(chunks),
                "response_bytes": envelope["_response_bytes"],
            }
        )

    boundary_top_k = 5001
    boundary, boundary_elapsed = _retrieval_request(
        api,
        dataset_id=dataset_id,
        question=f"Find the unique semantic marker {marker}",
        top_k=boundary_top_k,
        page_size=5,
        rerank_model=rerank_model,
    )
    return {
        "levels": levels,
        "marker_returned": marker_returned,
        "boundary": {
            "requested_top_k": boundary_top_k,
            "code": boundary.get("code"),
            "message": str(boundary.get("message", ""))[:512],
            "elapsed_seconds": round(boundary_elapsed, 6),
            "response_bytes": boundary["_response_bytes"],
        },
    }


def _timed_envelope(
    api: RetrievalApi,
    method: str,
    path: str,
    **kwargs: Any,
) -> tuple[dict[str, Any], float]:
    started = time.monotonic()
    envelope = api.envelope(method, path, **kwargs)
    return envelope, time.monotonic() - started


def _chunk_page_summary(
    envelope: dict[str, Any],
    elapsed: float,
) -> tuple[dict[str, object], list[dict[str, Any]]]:
    if envelope.get("code") != 0:
        raise RuntimeError("R2-05 chunk page request failed")
    data = envelope.get("data")
    chunks = data.get("chunks") if isinstance(data, dict) else None
    total = data.get("total") if isinstance(data, dict) else None
    if not isinstance(chunks, list) or not isinstance(total, int):
        raise RuntimeError("R2-05 chunk page response is invalid")
    typed_chunks = [chunk for chunk in chunks if isinstance(chunk, dict)]
    if len(typed_chunks) != len(chunks):
        raise RuntimeError("R2-05 chunk page contains invalid rows")
    return (
        {
            "elapsed_seconds": round(elapsed, 6),
            "returned": len(typed_chunks),
            "total": total,
            "response_bytes": envelope["_response_bytes"],
        },
        typed_chunks,
    )


def _profile_chunk_reads(
    api: RetrievalApi,
    scale: ElasticsearchChunkScale,
    *,
    dataset_id: str,
    document_id: str,
    target_synthetic_chunks: int,
    deep_page: int,
) -> dict[str, object]:
    insert_seconds = scale.seed(target_synthetic_chunks)
    path = f"/api/v1/datasets/{dataset_id}/documents/{document_id}/chunks"
    first_envelope, first_elapsed = _timed_envelope(
        api,
        "GET",
        path,
        params={"page": 1, "page_size": 100},
    )
    first_summary, first_chunks = _chunk_page_summary(first_envelope, first_elapsed)
    deep_envelope, deep_elapsed = _timed_envelope(
        api,
        "GET",
        path,
        params={"page": deep_page, "page_size": 100},
    )
    deep_summary, _ = _chunk_page_summary(deep_envelope, deep_elapsed)
    oversize, oversize_elapsed = _timed_envelope(
        api,
        "GET",
        path,
        params={"page": 1, "page_size": 101},
    )
    if not first_chunks or not isinstance(first_chunks[0].get("id"), str):
        raise RuntimeError("R2-05 chunk page did not contain a retrievable chunk")
    chunk_id = str(first_chunks[0]["id"])
    single, single_elapsed = _timed_envelope(
        api,
        "GET",
        f"{path}/{chunk_id}",
    )
    single_data = single.get("data")
    if single.get("code") != 0 or not isinstance(single_data, dict):
        raise RuntimeError("R2-05 single chunk response is invalid")
    runtime_fields_absent = not any(
        key.endswith("_vec") or "_sm_" in key or key.endswith("_tks") or key.endswith("_ltks")
        for key in single_data
    )
    return {
        "target_synthetic_chunks": target_synthetic_chunks,
        "insert_seconds": round(insert_seconds, 6),
        "deep_page_number": deep_page,
        "first_page": first_summary,
        "deep_page": deep_summary,
        "oversize_page": {
            "code": oversize.get("code"),
            "message": str(oversize.get("message", ""))[:256],
            "elapsed_seconds": round(oversize_elapsed, 6),
            "response_bytes": oversize["_response_bytes"],
        },
        "single_chunk_seconds": round(single_elapsed, 6),
        "single_chunk_response_bytes": single["_response_bytes"],
        "single_chunk_runtime_fields_absent": runtime_fields_absent,
    }


def run(args: argparse.Namespace) -> dict[str, object]:
    source_root = args.source_root.resolve()
    source_commit = _run_command("git", "rev-parse", "HEAD", cwd=source_root)
    if source_commit != args.expected_source_commit:
        raise RuntimeError("RAGFlow retrieval benchmark source commit mismatch")
    if _run_command("git", "status", "--porcelain", cwd=source_root):
        raise RuntimeError("RAGFlow retrieval benchmark source checkout must be clean")

    api = RetrievalApi(
        base_url=args.base_url,
        api_key=_read_api_key(args.api_key_file),
        timeout_seconds=args.timeout_seconds,
    )
    connection = _connect_mysql(args)
    database = ScaleDatabase(connection)
    monitor = ResourceMonitor(interval_seconds=args.resource_interval_seconds)
    dataset_id: str | None = None
    scale: ElasticsearchChunkScale | None = None
    cleanup: dict[str, object] = {}
    monitor.start()
    try:
        version = api.version()
        if version != EXPECTED_RAGFLOW_VERSION:
            raise RuntimeError("RAGFlow retrieval benchmark version mismatch")
        report: dict[str, object] = {
            "schema_version": 1,
            "ragflow_version": version,
            "ragflow_commit": source_commit,
            "ragflow_upstream_commit": EXPECTED_RAGFLOW_COMMIT,
            "source_audit": source_audit(source_root, args.source_mode),
            "configuration": {
                "scale_count": args.scale_count,
                "deep_page": args.deep_page,
                "document_count": args.document_count,
                "paragraphs_per_document": args.paragraphs_per_document,
                "words_per_paragraph": args.words_per_paragraph,
            },
            "started_at": datetime.now(UTC).isoformat(),
        }
        args.partial_report = report
        run_id = uuid4().hex[:12]
        marker = f"R2-05-RETRIEVAL-{uuid4().hex}"
        dataset_id = api.create_dataset(f"common-agent-r2-05-{run_id}")
        documents = build_write_documents(
            document_count=args.document_count,
            paragraphs_per_document=args.paragraphs_per_document,
            words_per_paragraph=args.words_per_paragraph,
            marker=marker,
        )
        document_ids = api.upload_documents(dataset_id, documents)
        api.start_parsing(dataset_id, document_ids)
        completion, final_documents = _wait_for_documents(
            api,
            dataset_id=dataset_id,
            document_ids=document_ids,
            timeout_seconds=args.parse_timeout_seconds,
        )
        parsed_chunks = sum(
            int(document.get("chunk_count", document.get("chunk_num", 0)) or 0)
            for document in final_documents.values()
        )
        if parsed_chunks < args.document_count:
            raise RuntimeError("R2-05 live parsing produced too few chunks")
        report["live_write"] = {
            "documents": len(document_ids),
            "chunks": parsed_chunks,
            "last_document_seconds": round(max(completion.values()), 6),
        }
        report["retrieval_profile"] = _profile_retrieval(
            api,
            dataset_id=dataset_id,
            marker=marker,
            source_mode=args.source_mode,
            rerank_model=args.rerank_model,
        )
        tenant_id = database.dataset_identity(dataset_id)[0]
        scale = ElasticsearchChunkScale(
            base_url=args.elasticsearch_url,
            index_name=f"ragflow_{tenant_id}",
            dataset_id=dataset_id,
            document_id=document_ids[0],
            prefix=f"r205{uuid4().hex[:12]}",
            timeout_seconds=args.timeout_seconds,
            username=args.elasticsearch_user,
            password=os.environ.get("RAGFLOW_BENCHMARK_ELASTIC_PASSWORD", ""),
        )
        report["chunk_read_profile"] = _profile_chunk_reads(
            api,
            scale,
            dataset_id=dataset_id,
            document_id=document_ids[0],
            target_synthetic_chunks=args.scale_count,
            deep_page=args.deep_page,
        )
        report["completed_at"] = datetime.now(UTC).isoformat()
        return report
    finally:
        errors: list[str] = []
        if scale is not None:
            try:
                scale_cleanup = scale.cleanup()
                cleanup["synthetic_deleted"] = scale_cleanup["deleted"]
                cleanup["synthetic_delete_errors"] = scale_cleanup["delete_errors"]
            except Exception as error:
                cleanup["synthetic_delete_errors"] = -1
                errors.append(type(error).__name__)
            finally:
                scale.close()
        else:
            cleanup["synthetic_delete_errors"] = 0
        if dataset_id is not None:
            try:
                api.delete_dataset(dataset_id)
                cleanup["dataset_deleted"] = True
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
    audit = report.get("source_audit")
    if not isinstance(audit, dict) or audit.get("mode") not in {"official", "patched"}:
        raise RuntimeError("RAGFlow retrieval benchmark source mode is missing")
    cleanup = report.get("cleanup")
    if not isinstance(cleanup, dict) or cleanup.get("errors") != []:
        raise RuntimeError("RAGFlow retrieval benchmark cleanup failed")
    if cleanup.get("synthetic_delete_errors") != 0:
        raise RuntimeError("RAGFlow synthetic chunk cleanup failed")
    resources = cleanup.get("resources")
    if not isinstance(resources, dict) or resources.get("sampling_errors") != []:
        raise RuntimeError("RAGFlow retrieval resource sampling failed")
    final_state = resources.get("final_container_state")
    if not isinstance(final_state, dict):
        raise RuntimeError("RAGFlow retrieval final container state is missing")
    api_state = final_state.get("common-agent-ragflow-api")
    if not isinstance(api_state, dict) or api_state.get("oom_killed") is not False:
        raise RuntimeError("RAGFlow retrieval API was OOM-killed")

    retrieval = report.get("retrieval_profile")
    if not isinstance(retrieval, dict) or retrieval.get("marker_returned") is not True:
        raise RuntimeError("RAGFlow retrieval marker proof is missing")
    boundary = retrieval.get("boundary")
    if not isinstance(boundary, dict):
        raise RuntimeError("RAGFlow retrieval boundary proof is missing")
    message = str(boundary.get("message", ""))
    if (
        boundary.get("requested_top_k") != 5001
        or boundary.get("code") == 0
        or not (
            "BadRequestError" in message or "x_content_parse_exception" in message
        )
    ):
        raise RuntimeError("upstream retrieval boundary failure was not reproduced")

    chunk_reads = report.get("chunk_read_profile")
    if not isinstance(chunk_reads, dict):
        raise RuntimeError("RAGFlow chunk read profile is missing")
    for name in ("first_page", "deep_page"):
        page = chunk_reads.get(name)
        if not isinstance(page, dict) or page.get("returned") != 100:
            raise RuntimeError(f"RAGFlow chunk {name} is incomplete")
    oversize = chunk_reads.get("oversize_page")
    if not isinstance(oversize, dict) or oversize.get("code") == 0:
        raise RuntimeError("RAGFlow chunk oversize page was accepted")
    if chunk_reads.get("single_chunk_runtime_fields_absent") is not True:
        raise RuntimeError("RAGFlow single chunk leaked runtime fields")
    levels = retrieval.get("levels")
    if not isinstance(levels, list) or len(levels) != 3:
        raise RuntimeError("RAGFlow retrieval level profile is incomplete")
    for level in levels:
        if not isinstance(level, dict) or not math.isfinite(
            float(level.get("elapsed_seconds", 0))
        ):
            raise RuntimeError("RAGFlow retrieval latency is invalid")
    return "passed"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="RAGFlow v0.26.4 retrieval and large chunk read benchmark"
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:19380")
    parser.add_argument("--elasticsearch-url", default="http://127.0.0.1:19200")
    parser.add_argument("--elasticsearch-user", default="elastic")
    parser.add_argument("--api-key-file", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--source-mode", choices=("official", "patched"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mysql-host", default="127.0.0.1")
    parser.add_argument("--mysql-port", type=int, default=19432)
    parser.add_argument("--mysql-user", default="root")
    parser.add_argument("--scale-count", default="12000")
    parser.add_argument("--deep-page", type=int, default=110)
    parser.add_argument("--document-count", type=int, default=2)
    parser.add_argument("--paragraphs-per-document", type=int, default=16)
    parser.add_argument("--words-per-paragraph", type=int, default=300)
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
        args.scale_count = parse_scale_count(str(args.scale_count))
    except ValueError as error:
        raise SystemExit(str(error)) from error
    if not 101 <= args.deep_page <= 10_000:
        raise SystemExit("deep_page must be within 101..10000")
    if not 1 <= args.document_count <= 16:
        raise SystemExit("document_count must be within 1..16")
    if not 1 <= args.paragraphs_per_document <= 256:
        raise SystemExit("paragraphs_per_document must be within 1..256")
    if not 1 <= args.words_per_paragraph <= 2048:
        raise SystemExit("words_per_paragraph must be within 1..2048")
    if args.scale_count < args.deep_page * 100:
        raise SystemExit("scale_count must cover the requested deep_page")
    if args.timeout_seconds <= 0 or args.parse_timeout_seconds <= 0:
        raise SystemExit("timeouts must be positive")
    if not os.environ.get("RAGFLOW_BENCHMARK_ELASTIC_PASSWORD"):
        raise SystemExit("RAGFLOW_BENCHMARK_ELASTIC_PASSWORD is required")
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
        raise RuntimeError("RAGFlow retrieval benchmark produced no report")
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
