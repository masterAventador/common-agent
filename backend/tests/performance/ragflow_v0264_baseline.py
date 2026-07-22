from __future__ import annotations

import argparse
import json
import math
import os
import re
import stat
import subprocess
import threading
import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from statistics import fmean
from types import TracebackType
from typing import Any, Final, Protocol, TypedDict, cast
from uuid import uuid4

import httpx
import pymysql  # type: ignore[import-untyped]

EXPECTED_RAGFLOW_COMMIT: Final = "cb93883f3f8c975eecb2fed81210effeb3bdb06f"
EXPECTED_RAGFLOW_VERSION: Final = "v0.26.4"
MAX_SCALE_DOCUMENTS: Final = 1_000_000
RAGFLOW_CONTAINERS: Final = (
    "common-agent-ragflow-api",
    "common-agent-ragflow-elasticsearch",
    "common-agent-ragflow-mysql",
    "common-agent-ragflow-minio",
    "common-agent-ragflow-valkey",
)
_ACTUAL_ROWS = re.compile(
    r"actual time=[^)]*?rows=(?P<rows>[0-9]+(?:\.[0-9]+)?) loops=(?P<loops>[0-9]+)"
)


@dataclass(frozen=True, slots=True)
class ExplainAnalysis:
    node_count: int
    maximum_rows_per_node: int
    total_rows_across_loops: int


class DatabaseCursor(Protocol):
    def __enter__(self) -> DatabaseCursor: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    def execute(self, query: str, args: object = ...) -> int: ...

    def executemany(self, query: str, args: Sequence[Sequence[object]]) -> int: ...

    def fetchone(self) -> dict[str, object] | None: ...


class DatabaseConnection(Protocol):
    def cursor(self) -> DatabaseCursor: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...

    def close(self) -> None: ...


class ContainerResourceSample(TypedDict):
    cpu_percent: float
    memory_bytes: int


class ResourceSample(TypedDict):
    vm_used_bytes: int
    swap_used_bytes: int
    containers: dict[str, ContainerResourceSample]


def parse_scale_levels(raw: str) -> tuple[int, ...]:
    try:
        values = tuple(int(value.strip()) for value in raw.split(",") if value.strip())
    except ValueError as error:
        raise ValueError("scale levels must be comma-separated integers") from error
    if (
        not values
        or any(value <= 0 or value > MAX_SCALE_DOCUMENTS for value in values)
        or any(left >= right for left, right in pairwise(values))
    ):
        raise ValueError(
            f"scale levels must be strictly increasing within 1..{MAX_SCALE_DOCUMENTS}"
        )
    return values


def summarize_latencies(values: Sequence[float]) -> dict[str, int | float]:
    if not values or any(not math.isfinite(value) or value < 0 for value in values):
        raise ValueError("latency samples must be finite non-negative values")
    ordered = sorted(values)

    def nearest_rank(percentile: float) -> float:
        index = max(0, math.ceil(percentile * len(ordered)) - 1)
        return round(ordered[index], 6)

    return {
        "samples": len(ordered),
        "minimum_seconds": round(ordered[0], 6),
        "mean_seconds": round(fmean(ordered), 6),
        "p50_seconds": nearest_rank(0.50),
        "p95_seconds": nearest_rank(0.95),
        "maximum_seconds": round(ordered[-1], 6),
    }


def parse_explain_analyze(plan: str) -> ExplainAnalysis:
    matches = tuple(_ACTUAL_ROWS.finditer(plan))
    if not matches:
        raise ValueError("EXPLAIN ANALYZE did not contain actual row counts")
    rows_per_node = tuple(round(float(match.group("rows"))) for match in matches)
    rows_across_loops = tuple(
        round(float(match.group("rows"))) * int(match.group("loops")) for match in matches
    )
    return ExplainAnalysis(
        node_count=len(matches),
        maximum_rows_per_node=max(rows_per_node),
        total_rows_across_loops=sum(rows_across_loops),
    )


def build_report_header(
    *,
    source_commit: str,
    source_version: str,
    scale_levels: Sequence[int],
    live_document_count: int,
) -> dict[str, object]:
    if source_commit != EXPECTED_RAGFLOW_COMMIT:
        raise ValueError("RAGFlow source commit mismatch")
    if source_version != EXPECTED_RAGFLOW_VERSION:
        raise ValueError("RAGFlow source version mismatch")
    if parse_scale_levels(",".join(str(value) for value in scale_levels)) != tuple(
        scale_levels
    ):
        raise ValueError("invalid scale levels")
    if live_document_count < 2 or live_document_count > 32:
        raise ValueError("live document count must be within 2..32")
    return {
        "schema_version": 1,
        "ragflow_version": source_version,
        "ragflow_commit": source_commit,
        "scale_levels": list(scale_levels),
        "live_document_count": live_document_count,
    }


class RagFlowApi:
    def __init__(self, *, base_url: str, api_key: str, timeout_seconds: float) -> None:
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=httpx.Timeout(timeout_seconds),
            trust_env=False,
        )

    def close(self) -> None:
        self._client.close()

    def version(self) -> str:
        data = self.request("GET", "/api/v1/system/version")
        if not isinstance(data, str):
            raise RuntimeError("RAGFlow version response is invalid")
        return data

    def create_dataset(self, name: str) -> str:
        data = self.request(
            "POST",
            "/api/v1/datasets",
            json={
                "name": name,
                "description": "common-agent R2-01 isolated performance baseline",
                "permission": "me",
                "chunk_method": "naive",
                "embedding_model": (
                    "text-embedding-v4@common-agent-embedding@OpenAI-API-Compatible"
                ),
            },
        )
        if not isinstance(data, dict):
            raise RuntimeError("RAGFlow create dataset response is invalid")
        dataset_id = data.get("id")
        if not isinstance(dataset_id, str):
            raise RuntimeError("RAGFlow create dataset response is invalid")
        return dataset_id

    def delete_dataset(self, dataset_id: str) -> None:
        self.request("DELETE", "/api/v1/datasets", json={"ids": [dataset_id]})

    def upload_documents(
        self,
        dataset_id: str,
        documents: Sequence[tuple[str, bytes]],
    ) -> tuple[str, ...]:
        files = [
            ("file", (name, content, "text/plain")) for name, content in documents
        ]
        data = self.request(
            "POST",
            f"/api/v1/datasets/{dataset_id}/documents",
            files=files,
        )
        if not isinstance(data, list):
            raise RuntimeError("RAGFlow upload response is invalid")
        document_ids = tuple(
            item.get("id") for item in data if isinstance(item, dict)
        )
        if len(document_ids) != len(documents) or not all(
            isinstance(document_id, str) for document_id in document_ids
        ):
            raise RuntimeError("RAGFlow upload response did not contain every document")
        return cast(tuple[str, ...], document_ids)

    def start_parsing(self, dataset_id: str, document_ids: Sequence[str]) -> None:
        self.request(
            "POST",
            f"/api/v1/datasets/{dataset_id}/chunks",
            json={"document_ids": list(document_ids)},
        )

    def list_documents(
        self,
        dataset_id: str,
        *,
        page: int = 1,
        page_size: int = 30,
    ) -> dict[str, Any]:
        data = self.request(
            "GET",
            f"/api/v1/datasets/{dataset_id}/documents",
            params={
                "page": page,
                "page_size": page_size,
                "orderby": "create_time",
                "desc": "true",
            },
        )
        if (
            not isinstance(data, dict)
            or not isinstance(data.get("total"), int)
            or not isinstance(data.get("docs"), list)
        ):
            raise RuntimeError("RAGFlow document list response is invalid")
        return data

    def wait_until_parsed(
        self,
        dataset_id: str,
        document_ids: Sequence[str],
        *,
        timeout_seconds: float,
    ) -> None:
        expected = set(document_ids)
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            payload = self.list_documents(dataset_id, page_size=100)
            documents = {
                item.get("id"): item
                for item in payload["docs"]
                if isinstance(item, dict) and item.get("id") in expected
            }
            failed = tuple(
                document_id
                for document_id, item in documents.items()
                if str(item.get("run", "")).upper() in {"4", "FAIL", "FAILED"}
            )
            if failed:
                raise RuntimeError("RAGFlow document parsing failed")
            if len(documents) == len(expected) and all(
                str(item.get("run", "")).upper() in {"3", "DONE", "COMPLETED"}
                for item in documents.values()
            ):
                return
            time.sleep(1)
        raise TimeoutError("RAGFlow document parsing timed out")

    def retrieve(
        self,
        dataset_id: str,
        question: str,
        *,
        rerank_model: str,
    ) -> dict[str, Any]:
        data = self.request(
            "POST",
            "/api/v1/retrieval",
            json={
                "dataset_ids": [dataset_id],
                "question": question,
                "page": 1,
                "page_size": 5,
                "similarity_threshold": 0.1,
                "vector_similarity_weight": 0.3,
                "top_k": 128,
                "rerank_id": rerank_model,
                "highlight": False,
            },
        )
        if not isinstance(data, dict) or not isinstance(data.get("chunks"), list):
            raise RuntimeError("RAGFlow retrieval response is invalid")
        return data

    def delete_document(self, dataset_id: str, document_id: str) -> None:
        data = self.request(
            "DELETE",
            f"/api/v1/datasets/{dataset_id}/documents",
            json={"ids": [document_id]},
        )
        if not isinstance(data, dict) or data.get("deleted") != 1:
            raise RuntimeError("RAGFlow delete response is invalid")

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        response = self._client.request(method, path, **kwargs)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or payload.get("code") != 0:
            raise RuntimeError(f"RAGFlow request failed at {method} {path}")
        return payload.get("data")


@dataclass(frozen=True, slots=True)
class ScalePrefixes:
    document: str
    file: str
    link: str


class ScaleDatabase:
    def __init__(self, connection: DatabaseConnection) -> None:
        self._connection = connection
        self._next_index = 0

    def dataset_identity(self, dataset_id: str) -> tuple[str, str, str, str | None, str]:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT tenant_id, created_by, parser_id, pipeline_id, parser_config "
                "FROM knowledgebase WHERE id = %s",
                (dataset_id,),
            )
            row = cursor.fetchone()
        if row is None:
            raise RuntimeError("benchmark dataset is missing from RAGFlow MySQL")
        return (
            str(row["tenant_id"]),
            str(row["created_by"]),
            str(row["parser_id"]),
            None if row["pipeline_id"] is None else str(row["pipeline_id"]),
            str(row["parser_config"]),
        )

    def document_count(self, dataset_id: str) -> int:
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS count FROM document WHERE kb_id = %s", (dataset_id,))
            row = cursor.fetchone()
        if row is None:
            raise RuntimeError("could not count benchmark documents")
        count = row["count"]
        if not isinstance(count, int):
            raise RuntimeError("benchmark document count is invalid")
        return count

    def seed_to_count(
        self,
        *,
        dataset_id: str,
        target_count: int,
        prefixes: ScalePrefixes,
        batch_size: int = 2000,
    ) -> float:
        current = self.document_count(dataset_id)
        if target_count <= current:
            raise ValueError("target count must be greater than the current count")
        tenant_id, created_by, parser_id, pipeline_id, parser_config = self.dataset_identity(
            dataset_id
        )
        remaining = target_count - current
        started = time.monotonic()
        while remaining:
            size = min(batch_size, remaining)
            indexes = range(self._next_index, self._next_index + size)
            document_rows: list[tuple[object, ...]] = []
            file_rows: list[tuple[object, ...]] = []
            link_rows: list[tuple[object, ...]] = []
            for index in indexes:
                document_id = f"{prefixes.document}{index:024x}"
                file_id = f"{prefixes.file}{index:024x}"
                link_id = f"{prefixes.link}{index:024x}"
                name = f"r2-01-scale-{index:07d}.txt"
                timestamp = 1_700_000_000_000 + index
                document_rows.append(
                    (
                        document_id,
                        dataset_id,
                        parser_id,
                        pipeline_id,
                        parser_config,
                        "benchmark",
                        "virtual",
                        created_by,
                        name,
                        "",
                        0,
                        0,
                        0,
                        1.0,
                        "",
                        0.0,
                        "txt",
                        "",
                        "3",
                        "1",
                        timestamp,
                    )
                )
                file_rows.append(
                    (
                        file_id,
                        prefixes.file,
                        tenant_id,
                        created_by,
                        name,
                        "",
                        0,
                        "virtual",
                        "benchmark",
                        timestamp,
                    )
                )
                link_rows.append((link_id, file_id, document_id, timestamp))
            with self._connection.cursor() as cursor:
                cursor.executemany(
                    "INSERT INTO document "
                    "(id, kb_id, parser_id, pipeline_id, parser_config, source_type, type, "
                    "created_by, name, location, size, token_num, chunk_num, progress, "
                    "progress_msg, process_duration, suffix, content_hash, run, status, "
                    "create_time) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
                    "%s, %s, %s, %s, %s, %s, %s)",
                    document_rows,
                )
                cursor.executemany(
                    "INSERT INTO file "
                    "(id, parent_id, tenant_id, created_by, name, location, size, type, "
                    "source_type, create_time) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    file_rows,
                )
                cursor.executemany(
                    "INSERT INTO file2document (id, file_id, document_id, create_time) "
                    "VALUES (%s, %s, %s, %s)",
                    link_rows,
                )
            self._connection.commit()
            self._next_index += size
            remaining -= size
        with self._connection.cursor() as cursor:
            cursor.execute(
                "UPDATE knowledgebase SET doc_num = %s WHERE id = %s",
                (target_count, dataset_id),
            )
        self._connection.commit()
        actual = self.document_count(dataset_id)
        if actual != target_count:
            raise RuntimeError("benchmark seed count mismatch")
        return time.monotonic() - started

    def victim_document_id(self, dataset_id: str, document_prefix: str) -> str:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM document WHERE kb_id = %s AND id LIKE %s "
                "ORDER BY id LIMIT 1",
                (dataset_id, f"{document_prefix}%"),
            )
            row = cursor.fetchone()
        if row is None:
            raise RuntimeError("benchmark delete victim is missing")
        return str(row["id"])

    def document_exists(self, document_id: str) -> bool:
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT 1 AS found FROM document WHERE id = %s", (document_id,))
            return cursor.fetchone() is not None

    def refresh_after_external_write(self) -> None:
        """End MySQL's repeatable-read snapshot before checking an API-side write."""
        self._connection.rollback()

    def explain(self, sql: str, parameters: Sequence[object]) -> tuple[str, ExplainAnalysis]:
        with self._connection.cursor() as cursor:
            cursor.execute(f"EXPLAIN ANALYZE {sql}", parameters)
            row = cursor.fetchone()
        if row is None:
            raise RuntimeError("EXPLAIN ANALYZE returned no plan")
        plan = str(next(iter(row.values())))
        return plan, parse_explain_analyze(plan)

    def cleanup(
        self,
        *,
        dataset_id: str,
        prefixes: ScalePrefixes,
    ) -> dict[str, int]:
        deleted: dict[str, int] = {}
        try:
            with self._connection.cursor() as cursor:
                deleted["links"] = cursor.execute(
                    "DELETE FROM file2document WHERE id LIKE %s",
                    (f"{prefixes.link}%",),
                )
                deleted["files"] = cursor.execute(
                    "DELETE FROM file WHERE id LIKE %s",
                    (f"{prefixes.file}%",),
                )
                deleted["documents"] = cursor.execute(
                    "DELETE FROM document WHERE kb_id = %s",
                    (dataset_id,),
                )
                deleted["datasets"] = cursor.execute(
                    "DELETE FROM knowledgebase WHERE id = %s",
                    (dataset_id,),
                )
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        return deleted


class ResourceMonitor:
    def __init__(self, *, interval_seconds: float = 1.0) -> None:
        self._interval_seconds = interval_seconds
        self._stop = threading.Event()
        self._samples: list[ResourceSample] = []
        self._errors: list[str] = []
        self._thread = threading.Thread(target=self._run, name="ragflow-baseline-resources")

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> dict[str, object]:
        self._stop.set()
        self._thread.join(timeout=30)
        if self._thread.is_alive():
            raise RuntimeError("resource monitor did not stop")
        if not self._samples:
            raise RuntimeError("resource monitor collected no samples")
        containers: dict[str, dict[str, float | int]] = {}
        for name in RAGFLOW_CONTAINERS:
            container_samples = [sample["containers"][name] for sample in self._samples]
            containers[name] = {
                "peak_cpu_percent": max(float(item["cpu_percent"]) for item in container_samples),
                "peak_memory_bytes": max(int(item["memory_bytes"]) for item in container_samples),
            }
        return {
            "sample_count": len(self._samples),
            "sampling_errors": self._errors,
            "peak_vm_used_bytes": max(int(sample["vm_used_bytes"]) for sample in self._samples),
            "peak_swap_used_bytes": max(
                int(sample["swap_used_bytes"]) for sample in self._samples
            ),
            "containers": containers,
            "final_container_state": _container_state(),
        }

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._samples.append(_resource_sample())
            except (OSError, RuntimeError, subprocess.SubprocessError) as error:
                self._errors.append(type(error).__name__)
            self._stop.wait(self._interval_seconds)


def _resource_sample() -> ResourceSample:
    meminfo = _run_command(
        "colima",
        "ssh",
        "--profile",
        "common-agent-dev",
        "--",
        "cat",
        "/proc/meminfo",
    )
    memory: dict[str, int] = {}
    for line in meminfo.splitlines():
        key, separator, remainder = line.partition(":")
        if separator and key in {"MemTotal", "MemAvailable", "SwapTotal", "SwapFree"}:
            memory[key] = int(remainder.strip().split()[0]) * 1024
    if set(memory) != {"MemTotal", "MemAvailable", "SwapTotal", "SwapFree"}:
        raise RuntimeError("Colima memory sample is incomplete")
    stats = _run_command(
        "docker",
        "--context",
        "colima-common-agent-dev",
        "stats",
        "--no-stream",
        "--format",
        "{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}",
        *RAGFLOW_CONTAINERS,
    )
    containers: dict[str, ContainerResourceSample] = {}
    for line in stats.splitlines():
        fields = line.split("\t")
        if len(fields) != 3:
            continue
        containers[fields[0]] = {
            "cpu_percent": float(fields[1].removesuffix("%")),
            "memory_bytes": _parse_size(fields[2].partition("/")[0].strip()),
        }
    if set(containers) != set(RAGFLOW_CONTAINERS):
        raise RuntimeError("Docker resource sample is incomplete")
    return {
        "vm_used_bytes": memory["MemTotal"] - memory["MemAvailable"],
        "swap_used_bytes": memory["SwapTotal"] - memory["SwapFree"],
        "containers": containers,
    }


def _container_state() -> dict[str, dict[str, object]]:
    payload = _run_command(
        "docker",
        "--context",
        "colima-common-agent-dev",
        "inspect",
        "--format",
        "{{.Name}}\t{{.RestartCount}}\t{{.State.OOMKilled}}\t{{.State.Status}}",
        *RAGFLOW_CONTAINERS,
    )
    result: dict[str, dict[str, object]] = {}
    for line in payload.splitlines():
        fields = line.split("\t")
        if len(fields) != 4:
            raise RuntimeError("Docker inspect output is invalid")
        result[fields[0].removeprefix("/")] = {
            "restart_count": int(fields[1]),
            "oom_killed": fields[2].lower() == "true",
            "status": fields[3],
        }
    if set(result) != set(RAGFLOW_CONTAINERS):
        raise RuntimeError("Docker inspect container set is incomplete")
    return result


def _parse_size(value: str) -> int:
    units = {
        "KiB": 1024,
        "MiB": 1024**2,
        "GiB": 1024**3,
        "KB": 1000,
        "MB": 1000**2,
        "GB": 1000**3,
        "B": 1,
    }
    for suffix in sorted(units, key=len, reverse=True):
        if value.endswith(suffix):
            return round(float(value[: -len(suffix)].strip()) * units[suffix])
    raise RuntimeError("Docker memory size is invalid")


def _run_command(*command: str, cwd: Path | None = None) -> str:
    return subprocess.run(
        command,
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    ).stdout.strip()


def _api_latency_samples(operation: Any, sample_count: int) -> tuple[float, ...]:
    values: list[float] = []
    for _ in range(sample_count):
        started = time.monotonic()
        operation()
        values.append(time.monotonic() - started)
    return tuple(values)


def _source_audit(source_root: Path) -> dict[str, object]:
    document_service = (
        source_root / "api/db/services/document_service.py"
    ).read_text(encoding="utf-8")
    document_api = (
        source_root / "api/apps/restful_apis/document_api.py"
    ).read_text(encoding="utf-8")
    checks: dict[str, object] = {
        "list_count_uses_joined_query": (
            ".join(File2Document" in document_service and "count = docs.count()" in document_service
        ),
        "delete_materializes_dataset_documents": (
            "dataset_doc_ids = {doc.id for doc in DocumentService.query(kb_id=dataset_id)}"
            in document_api
        ),
        "delete_all_materializes_dataset_documents": (
            "doc_ids = [doc.id for doc in DocumentService.query(kb_id=dataset_id)]"
            in document_api
        ),
    }
    if not all(checks.values()):
        raise RuntimeError("RAGFlow v0.26.4 source shape no longer matches the baseline")
    return checks


def _read_api_key(path: Path) -> str:
    file_stat = path.lstat()
    if stat.S_ISLNK(file_stat.st_mode) or file_stat.st_mode & 0o077:
        raise RuntimeError("RAGFlow API key file permissions are unsafe")
    value = path.read_text(encoding="utf-8").strip()
    if not value.startswith("ragflow-") or not 32 <= len(value) <= 256:
        raise RuntimeError("RAGFlow API key file is invalid")
    return value


def _connect_mysql(args: argparse.Namespace) -> DatabaseConnection:
    password = os.environ.get("RAGFLOW_BENCHMARK_MYSQL_PASSWORD")
    if not password:
        raise RuntimeError("RAGFLOW_BENCHMARK_MYSQL_PASSWORD is required")
    return cast(
        DatabaseConnection,
        pymysql.connect(
            host=args.mysql_host,
            port=args.mysql_port,
            user=args.mysql_user,
            password=password,
            database="rag_flow",
            charset="utf8mb4",
            autocommit=False,
            cursorclass=pymysql.cursors.DictCursor,
            read_timeout=args.timeout_seconds,
            write_timeout=args.timeout_seconds,
        ),
    )


def _live_api_baseline(
    api: RagFlowApi,
    *,
    dataset_id: str,
    document_count: int,
    sample_count: int,
    timeout_seconds: float,
    rerank_model: str,
) -> dict[str, object]:
    marker = f"R2-01-LIVE-{uuid4().hex}"
    documents: list[tuple[str, bytes]] = []
    for index in range(document_count):
        detail = (
            f"唯一删除后不可见标记是 {marker}。"
            if index == 0
            else "用于写入解析吞吐测量。"
        )
        documents.append(
            (
                f"r2-01-live-{index:02d}.txt",
                f"R2-01 官方基线文档 {index}。{detail}".encode(),
            )
        )
    upload_started = time.monotonic()
    document_ids = api.upload_documents(dataset_id, documents)
    upload_seconds = time.monotonic() - upload_started
    parse_started = time.monotonic()
    api.start_parsing(dataset_id, document_ids)
    api.wait_until_parsed(
        dataset_id,
        document_ids,
        timeout_seconds=timeout_seconds,
    )
    parse_seconds = time.monotonic() - parse_started

    question = f"唯一删除后不可见标记 {marker} 是什么?"
    retrieval_latencies = _api_latency_samples(
        lambda: api.retrieve(dataset_id, question, rerank_model=rerank_model),
        sample_count,
    )
    retrieved = api.retrieve(dataset_id, question, rerank_model=rerank_model)
    contents = tuple(
        str(chunk.get("content", ""))
        for chunk in retrieved["chunks"]
        if isinstance(chunk, dict)
    )
    if not any(marker in content for content in contents):
        raise RuntimeError("live retrieval did not return the unique marker")

    delete_started = time.monotonic()
    api.delete_document(dataset_id, document_ids[0])
    delete_seconds = time.monotonic() - delete_started
    remaining = api.list_documents(dataset_id, page_size=100)
    if any(
        isinstance(item, dict) and item.get("id") == document_ids[0]
        for item in remaining["docs"]
    ):
        raise RuntimeError("deleted live document is still visible in the list")
    after_delete = api.retrieve(dataset_id, question, rerank_model=rerank_model)
    if any(
        marker in str(chunk.get("content", ""))
        for chunk in after_delete["chunks"]
        if isinstance(chunk, dict)
    ):
        raise RuntimeError("deleted live document is still visible in retrieval")
    return {
        "write": {
            "documents": document_count,
            "upload_seconds": round(upload_seconds, 6),
            "parse_seconds": round(parse_seconds, 6),
            "end_to_end_seconds": round(upload_seconds + parse_seconds, 6),
            "documents_per_second": round(
                document_count / (upload_seconds + parse_seconds),
                6,
            ),
        },
        "retrieval": {
            "query_samples": summarize_latencies(retrieval_latencies),
            "returned_marker": True,
            "rerank_enabled": True,
        },
        "delete": {
            "seconds": round(delete_seconds, 6),
            "list_invisible": True,
            "retrieval_invisible": True,
        },
    }


_JOIN_FROM = (
    " FROM document AS d"
    " INNER JOIN file2document AS f2d ON f2d.document_id = d.id"
    " LEFT OUTER JOIN user_canvas AS c ON d.pipeline_id = c.id"
    " INNER JOIN file AS f ON f.id = f2d.file_id"
    " LEFT OUTER JOIN user AS u ON d.created_by = u.id"
    " WHERE d.kb_id = %s"
)


def _scale_baseline(
    api: RagFlowApi,
    database: ScaleDatabase,
    *,
    dataset_id: str,
    prefixes: ScalePrefixes,
    levels: Sequence[int],
    sample_count: int,
) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for target in levels:
        insert_seconds = database.seed_to_count(
            dataset_id=dataset_id,
            target_count=target,
            prefixes=prefixes,
        )
        first_page = _api_latency_samples(
            lambda: api.list_documents(dataset_id, page=1, page_size=30),
            sample_count,
        )
        deep_page_number = max(1, math.ceil(target / 30))
        deep_page = _api_latency_samples(
            lambda page=deep_page_number: api.list_documents(
                dataset_id,
                page=page,
                page_size=30,
            ),
            sample_count,
        )
        count_plan, count_analysis = database.explain(
            "SELECT COUNT(1)" + _JOIN_FROM,
            (dataset_id,),
        )
        deep_plan, deep_analysis = database.explain(
            "SELECT d.id" + _JOIN_FROM + " ORDER BY d.create_time DESC LIMIT 30 OFFSET %s",
            (dataset_id, max(0, target - 30)),
        )
        ownership_plan, ownership_analysis = database.explain(
            "SELECT d.* FROM document AS d WHERE d.kb_id = %s",
            (dataset_id,),
        )
        result: dict[str, object] = {
            "target_documents": target,
            "new_rows_insert_seconds": round(insert_seconds, 6),
            "first_page": summarize_latencies(first_page),
            "deep_page_number": deep_page_number,
            "deep_page": summarize_latencies(deep_page),
            "sql": {
                "joined_count": {
                    "analysis": asdict(count_analysis),
                    "plan": count_plan,
                },
                "deep_page": {
                    "analysis": asdict(deep_analysis),
                    "plan": deep_plan,
                },
                "delete_ownership_materialization": {
                    "analysis": asdict(ownership_analysis),
                    "plan": ownership_plan,
                },
            },
        }
        victim = database.victim_document_id(dataset_id, prefixes.document)
        delete_started = time.monotonic()
        try:
            api.delete_document(dataset_id, victim)
        except httpx.TransportError as error:
            result["delete_one"] = {
                "outcome": "server_disconnected",
                "error_type": type(error).__name__,
                "elapsed_seconds": round(time.monotonic() - delete_started, 6),
            }
            results.append(result)
            return results
        delete_seconds = time.monotonic() - delete_started
        database.refresh_after_external_write()
        if database.document_exists(victim):
            raise RuntimeError("scale delete victim is still present")
        actual_after_delete = database.document_count(dataset_id)
        if actual_after_delete != target - 1:
            raise RuntimeError("scale document count after delete is invalid")
        result["delete_one"] = {
            "outcome": "succeeded",
            "seconds": round(delete_seconds, 6),
        }
        result["actual_documents_after_delete"] = actual_after_delete
        results.append(result)
    return results


def determine_report_status(report: dict[str, object]) -> str:
    cleanup = report.get("cleanup")
    if not isinstance(cleanup, dict) or cleanup.get("errors") != []:
        raise RuntimeError("benchmark cleanup was not successful")
    resources = cleanup.get("resources")
    if not isinstance(resources, dict) or resources.get("sampling_errors") != []:
        raise RuntimeError("benchmark resource sampling was not successful")
    final_state = resources.get("final_container_state")
    if not isinstance(final_state, dict):
        raise RuntimeError("benchmark final container state is missing")
    api_state = final_state.get("common-agent-ragflow-api")
    if not isinstance(api_state, dict) or not isinstance(api_state.get("oom_killed"), bool):
        raise RuntimeError("benchmark RAGFlow API state is invalid")
    curve = report.get("scale_curve")
    if not isinstance(curve, list) or not curve:
        raise RuntimeError("benchmark scale curve is missing")
    last = curve[-1]
    delete_one = last.get("delete_one") if isinstance(last, dict) else None
    disconnected = (
        isinstance(delete_one, dict) and delete_one.get("outcome") == "server_disconnected"
    )
    if disconnected:
        if api_state["oom_killed"] is not True:
            raise RuntimeError("server disconnected without an OOM boundary")
        return "completed_with_upstream_oom"
    if api_state["oom_killed"] is True:
        raise RuntimeError("RAGFlow API OOM was not associated with the measured delete")
    return "passed"


def run(args: argparse.Namespace) -> dict[str, object]:
    source_root = args.source_root.resolve()
    source_commit = _run_command("git", "rev-parse", "HEAD", cwd=source_root)
    if _run_command("git", "status", "--porcelain", cwd=source_root):
        raise RuntimeError("RAGFlow source checkout must be clean")
    levels = parse_scale_levels(args.scale_levels)
    api_key = _read_api_key(args.api_key_file)
    api = RagFlowApi(
        base_url=args.base_url,
        api_key=api_key,
        timeout_seconds=args.timeout_seconds,
    )
    connection = _connect_mysql(args)
    database = ScaleDatabase(connection)
    live_dataset_id: str | None = None
    scale_dataset_id: str | None = None
    run_id = uuid4().hex[:12]
    prefixes = ScalePrefixes(
        document=uuid4().hex[:8],
        file=uuid4().hex[:8],
        link=uuid4().hex[:8],
    )
    monitor = ResourceMonitor(interval_seconds=args.resource_interval_seconds)
    cleanup: dict[str, object] = {}
    started_at = datetime.now(UTC)
    monitor.start()
    try:
        source_version = api.version()
        report: dict[str, object] = build_report_header(
            source_commit=source_commit,
            source_version=source_version,
            scale_levels=levels,
            live_document_count=args.live_document_count,
        )
        report["started_at"] = started_at.isoformat()
        report["source_audit"] = _source_audit(source_root)
        args.partial_report = report
        live_dataset_id = api.create_dataset(f"common-agent-r2-01-live-{run_id}")
        report["live_api_worker"] = _live_api_baseline(
            api,
            dataset_id=live_dataset_id,
            document_count=args.live_document_count,
            sample_count=args.samples,
            timeout_seconds=args.parse_timeout_seconds,
            rerank_model=args.rerank_model,
        )
        api.delete_dataset(live_dataset_id)
        cleanup["live_dataset_deleted"] = True
        live_dataset_id = None
        scale_dataset_id = api.create_dataset(f"common-agent-r2-01-scale-{run_id}")
        report["scale_curve"] = _scale_baseline(
            api,
            database,
            dataset_id=scale_dataset_id,
            prefixes=prefixes,
            levels=levels,
            sample_count=args.samples,
        )
        report["completed_at"] = datetime.now(UTC).isoformat()
        return report
    finally:
        cleanup_errors: list[str] = []
        if scale_dataset_id is not None:
            try:
                cleanup["scale"] = database.cleanup(
                    dataset_id=scale_dataset_id,
                    prefixes=prefixes,
                )
            except Exception as error:
                cleanup_errors.append(type(error).__name__)
        if live_dataset_id is not None:
            try:
                api.delete_dataset(live_dataset_id)
                cleanup["live_dataset_deleted"] = True
            except Exception as error:
                cleanup_errors.append(type(error).__name__)
        cleanup["errors"] = cleanup_errors
        try:
            cleanup["resources"] = monitor.stop()
        finally:
            connection.close()
            api.close()
        args.cleanup_result.clear()
        args.cleanup_result.update(cleanup)


def _write_report(path: Path, report: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="RAGFlow v0.26.4 write/delete/list/retrieval performance baseline"
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:19380")
    parser.add_argument("--api-key-file", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mysql-host", default="127.0.0.1")
    parser.add_argument("--mysql-port", type=int, default=19432)
    parser.add_argument("--mysql-user", default="root")
    parser.add_argument("--scale-levels", default="1000,10000,50000,100000,250000")
    parser.add_argument("--live-document-count", type=int, default=8)
    parser.add_argument("--samples", type=int, default=3)
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
    if args.samples < 1 or args.samples > 20:
        raise SystemExit("--samples must be within 1..20")
    if args.timeout_seconds <= 0 or args.parse_timeout_seconds <= 0:
        raise SystemExit("timeouts must be positive")
    if args.resource_interval_seconds <= 0 or args.resource_interval_seconds > 10:
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
        raise RuntimeError("benchmark produced no report")
    report["cleanup"] = args.cleanup_result
    try:
        report["status"] = determine_report_status(report)
    except Exception as error:
        report["status"] = "failed"
        report["failure"] = {"type": type(error).__name__}
        _write_report(args.output, report)
        raise
    _write_report(args.output, report)
    print(args.output)


if __name__ == "__main__":
    main()
