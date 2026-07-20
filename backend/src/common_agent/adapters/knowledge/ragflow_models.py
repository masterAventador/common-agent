from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from time import monotonic, sleep
from typing import Any, Final, Literal, cast
from urllib.parse import urlparse

import httpx

from common_agent.bootstrap.settings import ConfigurationError, ModelSettings, RagFlowSettings

BAILIAN_FACTORY: Final = "Tongyi-Qianwen"
BAILIAN_EMBEDDING_MODEL: Final = "text-embedding-v4"
BAILIAN_RERANK_MODEL: Final = "qwen3-rerank"
BAILIAN_EMBEDDING_ID: Final = f"{BAILIAN_EMBEDDING_MODEL}@{BAILIAN_FACTORY}"
BAILIAN_RERANK_ID: Final = f"{BAILIAN_RERANK_MODEL}@{BAILIAN_FACTORY}"

_LOCAL_EMAIL: Final = "common-agent@local.test"
_LOCAL_ENCRYPTED_PASSWORD: Final = (
    "ctAseGvejiaSWWZ88T/m4FQVOpQyUvP+x7sXtdv3feqZACiQleuewkUi35E16wSd5C5QcnkkcV9cYc8T"
    "KPTRZlxappDuirxghxoOvFcJxFU4ixLsDfN33jCHRoDUW81IH9zjij/vaw8IbVyb6vuwg6MX6inOEBRRzVbRYxXO"
    "u1wkWY6SsI8X70oF9aeLFp/PzQpjoe/YbSqpTq8qqrmHzn9vO+yvyYyvmDsphXeX8f7fp9c7vUsfOCkM+gHY3Pad"
    "G+QHa7KI7mzTKgUTZImK6BZtfRBATDTthEUbbaTewY4H0MnWiCeeDhcbeQao6cFy1To8pE3RpmxnGnS8BsBn8w=="
)


class RagFlowModelConfigurationError(RuntimeError):
    code = "ragflow_model_configuration_failed"

    def __init__(self, stage: str = "unknown") -> None:
        self.stage = stage
        super().__init__(f"{self.code}:{stage}")


@dataclass(frozen=True, slots=True)
class RagFlowModelStatus:
    embedding_ready: bool
    rerank_ready: bool
    defaults_ready: bool


@dataclass(frozen=True, slots=True)
class RagFlowBailianMigrationPlan:
    dataset_count: int
    document_count: int
    datasets_requiring_model_update: int
    busy_document_count: int


@dataclass(frozen=True, slots=True)
class RagFlowBailianMigrationResult:
    dataset_count: int
    document_count: int
    datasets_updated: int


@dataclass(frozen=True, slots=True)
class _MigrationDocument:
    id: str
    run: str


@dataclass(frozen=True, slots=True)
class _MigrationDataset:
    id: str
    embedding_model: str
    documents: tuple[_MigrationDocument, ...]


class RagFlowBailianIndexMigrator:
    """Re-index retained RAGFlow datasets through its documented public API."""

    def __init__(
        self,
        *,
        client: httpx.Client,
        authorization: str,
        poll_interval_seconds: float = 1.0,
        timeout_seconds: float = 3600.0,
    ) -> None:
        if not authorization.strip() or poll_interval_seconds < 0 or timeout_seconds <= 0:
            raise RagFlowModelConfigurationError("migration_input")
        self._client = client
        self._authorization = authorization.strip()
        self._poll_interval_seconds = poll_interval_seconds
        self._timeout_seconds = timeout_seconds

    def plan(self, *, dataset_ids: tuple[str, ...] = ()) -> RagFlowBailianMigrationPlan:
        datasets = self._inventory(dataset_ids=dataset_ids)
        return RagFlowBailianMigrationPlan(
            dataset_count=len(datasets),
            document_count=sum(len(dataset.documents) for dataset in datasets),
            datasets_requiring_model_update=sum(
                dataset.embedding_model != BAILIAN_EMBEDDING_ID for dataset in datasets
            ),
            busy_document_count=sum(
                _is_busy(document.run) for dataset in datasets for document in dataset.documents
            ),
        )

    def migrate(self, *, dataset_ids: tuple[str, ...] = ()) -> RagFlowBailianMigrationResult:
        datasets = self._inventory(dataset_ids=dataset_ids)
        if any(_is_busy(document.run) for dataset in datasets for document in dataset.documents):
            raise RagFlowModelConfigurationError("migration_documents_busy")

        datasets_updated = 0
        for dataset in datasets:
            if dataset.embedding_model != BAILIAN_EMBEDDING_ID:
                self._request(
                    "PUT",
                    f"/api/v1/datasets/{dataset.id}",
                    stage="migration_update_dataset",
                    json={"embedding_model": BAILIAN_EMBEDDING_ID},
                )
                datasets_updated += 1
            for document_ids in _batches(
                tuple(document.id for document in dataset.documents), size=100
            ):
                self._request(
                    "POST",
                    f"/api/v1/datasets/{dataset.id}/documents/parse",
                    stage="migration_start_reindex",
                    json={"document_ids": list(document_ids)},
                )

        for dataset in datasets:
            if dataset.documents:
                self._wait_for_documents(dataset)

        return RagFlowBailianMigrationResult(
            dataset_count=len(datasets),
            document_count=sum(len(dataset.documents) for dataset in datasets),
            datasets_updated=datasets_updated,
        )

    def _inventory(self, *, dataset_ids: tuple[str, ...]) -> tuple[_MigrationDataset, ...]:
        requested_ids = {value.strip() for value in dataset_ids if value.strip()}
        datasets: list[_MigrationDataset] = []
        page = 1
        while True:
            data = self._request(
                "GET",
                "/api/v1/datasets",
                stage="migration_list_datasets",
                params={
                    "page": page,
                    "page_size": 100,
                    "orderby": "create_time",
                    "desc": "true",
                },
            )
            if not isinstance(data, list):
                raise RagFlowModelConfigurationError("migration_list_datasets")
            for item in data:
                if not isinstance(item, dict):
                    raise RagFlowModelConfigurationError("migration_list_datasets")
                dataset_id = item.get("id")
                embedding_model = item.get("embedding_model", "")
                if not isinstance(dataset_id, str) or not dataset_id:
                    raise RagFlowModelConfigurationError("migration_list_datasets")
                if not isinstance(embedding_model, str):
                    raise RagFlowModelConfigurationError("migration_list_datasets")
                if requested_ids and dataset_id not in requested_ids:
                    continue
                datasets.append(
                    _MigrationDataset(
                        id=dataset_id,
                        embedding_model=embedding_model,
                        documents=self._list_documents(dataset_id),
                    )
                )
            if len(data) < 100:
                break
            page += 1

        if requested_ids and requested_ids != {dataset.id for dataset in datasets}:
            raise RagFlowModelConfigurationError("migration_dataset_not_found")
        return tuple(datasets)

    def _list_documents(self, dataset_id: str) -> tuple[_MigrationDocument, ...]:
        documents: list[_MigrationDocument] = []
        page = 1
        while True:
            data = self._request(
                "GET",
                f"/api/v1/datasets/{dataset_id}/documents",
                stage="migration_list_documents",
                params={
                    "page": page,
                    "page_size": 100,
                    "orderby": "create_time",
                    "desc": "true",
                },
            )
            if not isinstance(data, dict) or not isinstance(data.get("docs"), list):
                raise RagFlowModelConfigurationError("migration_list_documents")
            raw_documents = data["docs"]
            for item in raw_documents:
                if not isinstance(item, dict):
                    raise RagFlowModelConfigurationError("migration_list_documents")
                document_id = item.get("id")
                run = item.get("run")
                if not isinstance(document_id, str) or not document_id or not isinstance(run, str):
                    raise RagFlowModelConfigurationError("migration_list_documents")
                documents.append(_MigrationDocument(id=document_id, run=run))
            if len(raw_documents) < 100:
                break
            page += 1
        return tuple(documents)

    def _wait_for_documents(self, dataset: _MigrationDataset) -> None:
        expected_ids = {document.id for document in dataset.documents}
        deadline = monotonic() + self._timeout_seconds
        while monotonic() < deadline:
            documents = {document.id: document for document in self._list_documents(dataset.id)}
            if not expected_ids.issubset(documents):
                raise RagFlowModelConfigurationError("migration_document_missing")
            states = {documents[document_id].run.upper() for document_id in expected_ids}
            if states.issubset({"3", "DONE"}):
                return
            if states.intersection({"2", "CANCEL", "4", "FAIL"}):
                raise RagFlowModelConfigurationError("migration_reindex_failed")
            sleep(self._poll_interval_seconds)
        raise RagFlowModelConfigurationError("migration_reindex_timeout")

    def _request(self, method: str, path: str, *, stage: str, **kwargs: Any) -> Any:
        try:
            response = self._client.request(
                method,
                path,
                headers={"Authorization": self._authorization},
                **kwargs,
            )
            response.raise_for_status()
            payload = _payload(response)
        except (httpx.HTTPError, TypeError, ValueError):
            raise RagFlowModelConfigurationError(stage) from None
        if payload.get("code") != 0:
            raise RagFlowModelConfigurationError(stage)
        return payload.get("data")


class RagFlowModelConfigurator:
    def __init__(self, *, client: httpx.Client) -> None:
        self._client = client
        self._authorization: str | None = None

    def apply(self, *, api_key: str, provider_base_url: str) -> RagFlowModelStatus:
        key = api_key.strip()
        ragflow_provider_base_url = _ragflow_provider_base_url(provider_base_url)
        if not key or ragflow_provider_base_url is None:
            raise RagFlowModelConfigurationError("input")
        self._authenticate()
        self._add_model(
            api_key=key,
            provider_base_url=ragflow_provider_base_url,
            model_name=BAILIAN_EMBEDDING_MODEL,
            model_type="embedding",
            max_tokens=8192,
        )
        self._add_model(
            api_key=key,
            provider_base_url=ragflow_provider_base_url,
            model_name=BAILIAN_RERANK_MODEL,
            model_type="rerank",
            max_tokens=4000,
        )

        tenant = self._tenant_models(stage="read_defaults")
        tenant_id = tenant.get("tenant_id")
        if not isinstance(tenant_id, str) or not tenant_id:
            raise RagFlowModelConfigurationError("read_defaults")
        self._request(
            "PATCH",
            "/api/v1/users/me/models",
            stage="set_defaults",
            json={
                "tenant_id": tenant_id,
                "asr_id": _string_value(tenant.get("asr_id")),
                "embd_id": BAILIAN_EMBEDDING_ID,
                "img2txt_id": _string_value(tenant.get("img2txt_id")),
                "llm_id": _string_value(tenant.get("llm_id")),
                "rerank_id": BAILIAN_RERANK_ID,
            },
        )
        status = self.status()
        if not (status.embedding_ready and status.rerank_ready and status.defaults_ready):
            raise RagFlowModelConfigurationError("verify")
        return status

    def status(self) -> RagFlowModelStatus:
        self._authenticate()
        tenant = self._tenant_models(stage="status_defaults")
        llms = self._request("GET", "/v1/llm/my_llms", stage="status_models")
        provider = llms.get(BAILIAN_FACTORY)
        configured_models = provider.get("llm", []) if isinstance(provider, dict) else []
        model_pairs = {
            (item.get("name"), item.get("type"))
            for item in configured_models
            if isinstance(item, dict)
        }
        embedding_ready = (BAILIAN_EMBEDDING_MODEL, "embedding") in model_pairs
        rerank_ready = (BAILIAN_RERANK_MODEL, "rerank") in model_pairs
        defaults_ready = (
            tenant.get("embd_id") == BAILIAN_EMBEDDING_ID
            and tenant.get("rerank_id") == BAILIAN_RERANK_ID
        )
        return RagFlowModelStatus(
            embedding_ready=embedding_ready,
            rerank_ready=rerank_ready,
            defaults_ready=defaults_ready,
        )

    def authorization(self) -> str:
        self._authenticate()
        return cast(str, self._authorization)

    def _authenticate(self) -> None:
        if self._authorization is not None:
            return
        registration = self._request_anonymous(
            "POST",
            "/api/v1/users",
            json={
                "email": _LOCAL_EMAIL,
                "nickname": "common-agent",
                "password": _LOCAL_ENCRYPTED_PASSWORD,
            },
            allow_error=True,
            stage="register_local_account",
        )
        registration_code = registration.get("code")
        registration_message = registration.get("message")
        if registration_code != 0 and (
            not isinstance(registration_message, str)
            or "already registered" not in registration_message.lower()
        ):
            raise RagFlowModelConfigurationError("register_local_account")

        try:
            response = self._client.post(
                "/api/v1/auth/login",
                json={"email": _LOCAL_EMAIL, "password": _LOCAL_ENCRYPTED_PASSWORD},
            )
            response.raise_for_status()
            payload = _payload(response)
            authorization = response.headers.get("Authorization", "").strip()
        except (httpx.HTTPError, TypeError, ValueError):
            raise RagFlowModelConfigurationError("login") from None
        if payload.get("code") != 0 or not authorization:
            raise RagFlowModelConfigurationError("login")
        self._authorization = authorization

    def _add_model(
        self,
        *,
        api_key: str,
        provider_base_url: str,
        model_name: str,
        model_type: Literal["embedding", "rerank"],
        max_tokens: int,
    ) -> None:
        self._request(
            "POST",
            "/v1/llm/add_llm",
            stage=f"register_{model_type}",
            json={
                "llm_factory": BAILIAN_FACTORY,
                "llm_name": model_name,
                "model_type": model_type,
                "api_base": provider_base_url,
                "api_key": api_key,
                "max_tokens": max_tokens,
            },
        )

    def _tenant_models(self, *, stage: str) -> dict[str, Any]:
        return self._request("GET", "/api/v1/users/me/models", stage=stage)

    def _request(self, method: str, path: str, *, stage: str, **kwargs: Any) -> dict[str, Any]:
        self._authenticate()
        try:
            response = self._client.request(
                method,
                path,
                headers={"Authorization": cast(str, self._authorization)},
                **kwargs,
            )
            response.raise_for_status()
            payload = _payload(response)
        except (httpx.HTTPError, TypeError, ValueError):
            raise RagFlowModelConfigurationError(stage) from None
        if payload.get("code") != 0:
            raise RagFlowModelConfigurationError(stage)
        data = payload.get("data")
        if isinstance(data, dict):
            return data
        if data is True:
            return {}
        raise RagFlowModelConfigurationError(stage)

    def _request_anonymous(
        self,
        method: str,
        path: str,
        *,
        allow_error: bool = False,
        stage: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        try:
            response = self._client.request(method, path, **kwargs)
            response.raise_for_status()
            payload = _payload(response)
        except (httpx.HTTPError, TypeError, ValueError):
            raise RagFlowModelConfigurationError(stage) from None
        if not allow_error and payload.get("code") != 0:
            raise RagFlowModelConfigurationError(stage)
        return payload


def _payload(response: httpx.Response) -> dict[str, Any]:
    value = response.json()
    if not isinstance(value, dict):
        raise TypeError("invalid RAGFlow response")
    return value


def _ragflow_provider_base_url(value: str) -> str | None:
    parsed = urlparse(value)
    host = parsed.hostname or ""
    official_host = host in {
        "dashscope.aliyuncs.com",
        "dashscope-intl.aliyuncs.com",
    } or any(
        host.endswith(suffix) and host != suffix.removeprefix(".")
        for suffix in (
            ".cn-beijing.maas.aliyuncs.com",
            ".ap-southeast-1.maas.aliyuncs.com",
        )
    )
    if (
        parsed.scheme != "https"
        or not official_host
        or parsed.port not in {None, 443}
        or parsed.path.rstrip("/") != "/compatible-mode/v1"
        or parsed.username
        or parsed.password
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        return None
    return f"https://{host}/api/v1"


def _string_value(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _is_busy(value: str) -> bool:
    return value.upper() in {"1", "RUNNING"}


def _batches(values: tuple[str, ...], *, size: int) -> tuple[tuple[str, ...], ...]:
    return tuple(values[index : index + size] for index in range(0, len(values), size))


def main(argv: list[str] | None = None) -> int:
    arguments = argv if argv is not None else sys.argv[1:]
    action = arguments[0] if arguments else "status"
    if action not in {
        "apply",
        "status",
        "native-base-url",
        "plan-migration",
        "migrate",
    }:
        print(
            "用法: python -m common_agent.adapters.knowledge.ragflow_models "
            "{apply|status|native-base-url|plan-migration|migrate}",
            file=sys.stderr,
        )
        return 2
    try:
        if action == "native-base-url":
            bailian = ModelSettings.from_env()
            native_base_url = _ragflow_provider_base_url(bailian.base_url)
            if native_base_url is None:
                raise RagFlowModelConfigurationError("input")
            print(native_base_url)
            return 0
        if (
            action == "migrate"
            and os.environ.get("RAGFLOW_CONFIRM_BAILIAN_REINDEX", "").strip().lower() != "yes"
        ):
            raise RagFlowModelConfigurationError("migration_confirmation")
        ragflow = RagFlowSettings.from_env()
        with httpx.Client(
            base_url=ragflow.base_url,
            timeout=httpx.Timeout(ragflow.timeout_seconds),
            trust_env=False,
        ) as client:
            configurator = RagFlowModelConfigurator(client=client)
            if action == "apply":
                bailian = ModelSettings.from_env()
                status = configurator.apply(
                    api_key=bailian.api_key.get_secret_value(),
                    provider_base_url=bailian.base_url,
                )
            elif action == "status":
                status = configurator.status()
            else:
                status = configurator.status()
                if not (status.embedding_ready and status.rerank_ready and status.defaults_ready):
                    raise RagFlowModelConfigurationError("migration_models_not_ready")
                raw_timeout = os.environ.get("RAGFLOW_BAILIAN_MIGRATION_TIMEOUT_SECONDS", "3600")
                try:
                    migration_timeout = float(raw_timeout)
                except ValueError:
                    raise RagFlowModelConfigurationError("migration_input") from None
                if migration_timeout <= 0 or migration_timeout > 86400:
                    raise RagFlowModelConfigurationError("migration_input")
                dataset_ids = tuple(
                    value.strip()
                    for value in os.environ.get("RAGFLOW_BAILIAN_MIGRATION_DATASET_IDS", "").split(
                        ","
                    )
                    if value.strip()
                )
                migrator = RagFlowBailianIndexMigrator(
                    client=client,
                    authorization=configurator.authorization(),
                    timeout_seconds=migration_timeout,
                )
                if action == "plan-migration":
                    plan = migrator.plan(dataset_ids=dataset_ids)
                    print(
                        "RAGFlow 百炼索引迁移计划: "
                        f"datasets={plan.dataset_count}, "
                        f"documents={plan.document_count}, "
                        "model_updates="
                        f"{plan.datasets_requiring_model_update}, "
                        f"busy_documents={plan.busy_document_count}"
                    )
                    return 0
                result = migrator.migrate(dataset_ids=dataset_ids)
                print(
                    "RAGFlow 百炼索引迁移完成: "
                    f"datasets={result.dataset_count}, "
                    f"documents={result.document_count}, "
                    f"model_updates={result.datasets_updated}"
                )
                return 0
    except ConfigurationError:
        print(f"{RagFlowModelConfigurationError.code}:input", file=sys.stderr)
        return 1
    except RagFlowModelConfigurationError as error:
        print(f"{error.code}:{error.stage}", file=sys.stderr)
        return 1

    print(
        "RAGFlow 百炼模型状态: "
        f"embedding={'ready' if status.embedding_ready else 'missing'}, "
        f"rerank={'ready' if status.rerank_ready else 'missing'}, "
        f"defaults={'ready' if status.defaults_ready else 'missing'}"
    )
    return 0 if status.embedding_ready and status.rerank_ready and status.defaults_ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
