from __future__ import annotations

import asyncio
import os
from time import monotonic, sleep
from uuid import uuid4

import httpx
import pytest

from common_agent.adapters.knowledge.ragflow import RagFlowKnowledgeService
from common_agent.adapters.knowledge.ragflow_models import RagFlowBailianIndexMigrator
from common_agent.adapters.persistence.database import Database
from common_agent.domain.knowledge import (
    CreateKnowledgeBaseRequest,
    DocumentParsingStatus,
    DocumentUpload,
    KnowledgeRetrievalRequest,
    KnowledgeServiceAvailability,
)
from common_agent.pagination import ListPageRequest
from tests.support.employees import DEFAULT_TEST_MODEL_CONFIGURATION_ID, delete_employees
from tests.support.http import authenticated_client, running_api
from tests.support.ragflow import delete_dataset, provision_api_key
from tests.support.settings import TEST_DATABASE_URL
from tests.support.workflows import delete_workflows_from_database_url


def test_real_ragflow_adapter_lifecycle() -> None:
    base_url = os.environ.get("TEST_RAGFLOW_BASE_URL")
    api_key = os.environ.get("TEST_RAGFLOW_API_KEY")
    expected_version = os.environ.get("TEST_RAGFLOW_EXPECTED_VERSION")
    if not base_url or not expected_version:
        pytest.skip("真实 RAGFlow 地址或期望版本未配置")
    if not api_key:
        api_key = asyncio.run(provision_api_key(base_url))

    asyncio.run(_real_lifecycle(base_url, api_key, expected_version))


def test_real_ragflow_official_list_search_and_cursor_pagination() -> None:
    base_url = os.environ.get("TEST_RAGFLOW_BASE_URL")
    api_key = os.environ.get("TEST_RAGFLOW_API_KEY")
    expected_version = os.environ.get("TEST_RAGFLOW_EXPECTED_VERSION")
    if not base_url or not expected_version:
        pytest.skip("真实 RAGFlow 地址或期望版本未配置")
    if not api_key:
        api_key = asyncio.run(provision_api_key(base_url))

    asyncio.run(_real_list_pagination(base_url, api_key, expected_version))


async def _real_list_pagination(base_url: str, api_key: str, expected_version: str) -> None:
    service = RagFlowKnowledgeService(
        base_url=base_url,
        api_key=api_key,
        expected_version=expected_version,
        timeout_seconds=120.0,
    )
    dataset_ids: list[str] = []
    prefix = f"common-agent-u9-03-{uuid4().hex}"
    try:
        for index in range(3):
            created = await service.create_knowledge_base(
                CreateKnowledgeBaseRequest(
                    name=f"{prefix}-{index}",
                    description="U9-03 RAGFlow 官方列表分页验收",
                )
            )
            dataset_ids.append(created.id)

        first = await service.page_knowledge_bases(ListPageRequest(limit=2, search=prefix))
        assert len(first.items) == 2
        assert first.next_cursor is not None
        second = await service.page_knowledge_bases(
            ListPageRequest(limit=2, search=prefix, cursor=first.next_cursor)
        )
        assert len(second.items) == 1
        assert second.next_cursor is None
        listed_ids = [item.id for item in first.items + second.items]
        assert len(set(listed_ids)) == 3
        assert set(listed_ids) == set(dataset_ids)
    finally:
        await service.aclose()
        for dataset_id in dataset_ids:
            await delete_dataset(base_url, api_key, dataset_id)


async def _real_lifecycle(base_url: str, api_key: str, expected_version: str) -> None:
    service = RagFlowKnowledgeService(
        base_url=base_url,
        api_key=api_key,
        expected_version=expected_version,
        timeout_seconds=120.0,
    )
    dataset_id: str | None = None
    topic = f"星河计划-{uuid4().hex}"
    marker = f"青铜口令-{uuid4().hex}"
    try:
        status = await service.status()
        assert status.availability is KnowledgeServiceAvailability.AVAILABLE
        assert status.version == expected_version

        dataset = await service.create_knowledge_base(
            CreateKnowledgeBaseRequest(
                name=f"common-agent-k2-03-{uuid4().hex}",
                description="K2-03 正式适配器真实生命周期验收",
            )
        )
        dataset_id = dataset.id
        listed = await service.list_knowledge_bases()
        assert dataset.id in {item.id for item in listed}

        uploads = []
        for file_name, content in (
            (
                "k2-03-relevant.txt",
                f"{topic}的故障恢复主口令是 {marker}。这是唯一有效的恢复口令。",
            ),
            (
                "k2-03-distractor.txt",
                f"{topic}的项目负责人是林岚。这份说明不包含故障恢复主口令。",
            ),
            (
                "k2-03-unrelated.txt",
                "海潮计划的资产盘点安排在每月最后一个工作日。",
            ),
        ):
            uploaded = await service.upload_document(
                dataset.id,
                DocumentUpload(
                    file_name=file_name,
                    content_type="text/plain",
                    content=content.encode(),
                ),
            )
            assert uploaded.parsing_status is DocumentParsingStatus.PARSING
            uploads.append(uploaded)

        deadline = monotonic() + 900
        while monotonic() < deadline:
            documents = await service.list_documents(dataset.id)
            current_documents = {
                item.id: item for item in documents if item.id in {upload.id for upload in uploads}
            }
            if len(current_documents) == len(uploads) and all(
                item.parsing_status is DocumentParsingStatus.COMPLETED
                for item in current_documents.values()
            ):
                break
            failed = next(
                (
                    item
                    for item in current_documents.values()
                    if item.parsing_status is DocumentParsingStatus.FAILED
                ),
                None,
            )
            if failed is not None:
                pytest.fail(f"真实 RAGFlow 文档解析失败: {failed.error_code}")
            await asyncio.sleep(2)
        else:
            pytest.fail("真实 RAGFlow 文档解析超时")

        result_before_reindex = await service.retrieve(
            KnowledgeRetrievalRequest(
                knowledge_base_id=dataset.id,
                query=f"{topic}的故障恢复主口令是什么?",
                similarity_threshold=0.1,
            )
        )
        assert result_before_reindex.chunks
        assert marker in result_before_reindex.chunks[0].content

        def reindex_with_bailian() -> None:
            with httpx.Client(base_url=base_url, timeout=120.0, trust_env=False) as client:
                result = RagFlowBailianIndexMigrator(
                    client=client,
                    authorization=f"Bearer {api_key}",
                    poll_interval_seconds=0.5,
                    timeout_seconds=900.0,
                ).migrate(dataset_ids=(dataset.id,))
            assert result.dataset_count == 1
            assert result.document_count == len(uploads)

        await asyncio.to_thread(reindex_with_bailian)
        result_after_reindex = await service.retrieve(
            KnowledgeRetrievalRequest(
                knowledge_base_id=dataset.id,
                query=f"{topic}的故障恢复主口令是什么?",
                similarity_threshold=0.1,
            )
        )
        assert result_after_reindex.chunks
        assert marker in result_after_reindex.chunks[0].content
    finally:
        await service.aclose()
        if dataset_id is not None:
            await delete_dataset(base_url, api_key, dataset_id)


def test_real_knowledge_http_lifecycle() -> None:
    base_url = os.environ.get("TEST_RAGFLOW_BASE_URL")
    api_key = os.environ.get("TEST_RAGFLOW_API_KEY")
    expected_version = os.environ.get("TEST_RAGFLOW_EXPECTED_VERSION")
    if not base_url or not expected_version:
        pytest.skip("真实 RAGFlow 地址或期望版本未配置")
    if not api_key:
        api_key = asyncio.run(provision_api_key(base_url))

    dataset_id: str | None = None
    try:
        with (
            running_api(
                TEST_DATABASE_URL,
                env_overrides={
                    "RAGFLOW_BASE_URL": base_url,
                    "RAGFLOW_API_KEY": api_key,
                    "RAGFLOW_EXPECTED_VERSION": expected_version,
                    "RAGFLOW_TIMEOUT_SECONDS": "120",
                },
            ) as api_url,
            authenticated_client(base_url=api_url, timeout=120) as client,
        ):
            name = f"common-agent-k2-04-{uuid4().hex}"
            created_response = client.post(
                "/api/v1/knowledge-bases",
                json={"name": name, "description": "K2-04 正式 API 真实验收"},
            )
            assert created_response.status_code == 201
            created = created_response.json()
            dataset_id = str(created["id"])

            listed_response = client.get("/api/v1/knowledge-bases")
            assert listed_response.status_code == 200
            assert dataset_id in {item["id"] for item in listed_response.json()["items"]}

            uploaded_response = client.post(
                f"/api/v1/knowledge-bases/{dataset_id}/documents",
                files={
                    "file": (
                        "k2-04-acceptance.txt",
                        "common-agent K2-04 正式 API 解析验收。".encode(),
                        "text/plain",
                    )
                },
            )
            assert uploaded_response.status_code == 202
            uploaded = uploaded_response.json()
            assert uploaded["parsing_status"] == "parsing"

            deadline = monotonic() + 900
            while monotonic() < deadline:
                documents_response = client.get(f"/api/v1/knowledge-bases/{dataset_id}/documents")
                assert documents_response.status_code == 200
                current = next(
                    item for item in documents_response.json() if item["id"] == uploaded["id"]
                )
                if current["parsing_status"] == "completed":
                    break
                if current["parsing_status"] == "failed":
                    pytest.fail(f"真实知识库 API 文档解析失败: {current['error_code']}")
                sleep(2)
            else:
                pytest.fail("真实知识库 API 文档解析超时")

            deleted = client.delete(f"/api/v1/knowledge-bases/{dataset_id}")
            repeated = client.delete(f"/api/v1/knowledge-bases/{dataset_id}")
            missing_documents = client.get(f"/api/v1/knowledge-bases/{dataset_id}/documents")
            assert deleted.status_code == 204
            assert repeated.status_code == 204
            assert missing_documents.status_code == 404
            dataset_id = None
    finally:
        if dataset_id is not None:
            asyncio.run(delete_dataset(base_url, api_key, dataset_id))


def test_real_employee_http_binding_lifecycle() -> None:
    base_url = os.environ.get("TEST_RAGFLOW_BASE_URL")
    api_key = os.environ.get("TEST_RAGFLOW_API_KEY")
    expected_version = os.environ.get("TEST_RAGFLOW_EXPECTED_VERSION")
    if not base_url or not expected_version:
        pytest.skip("真实 RAGFlow 地址或期望版本未配置")
    if not api_key:
        api_key = asyncio.run(provision_api_key(base_url))

    dataset_id: str | None = None
    employee_id: str | None = None
    try:
        environment = {
            "RAGFLOW_BASE_URL": base_url,
            "RAGFLOW_API_KEY": api_key,
            "RAGFLOW_EXPECTED_VERSION": expected_version,
            "RAGFLOW_TIMEOUT_SECONDS": "120",
        }
        with (
            running_api(TEST_DATABASE_URL, env_overrides=environment) as api_url,
            authenticated_client(base_url=api_url, timeout=120) as client,
        ):
            dataset = client.post(
                "/api/v1/knowledge-bases",
                json={
                    "name": f"common-agent-e3-02-{uuid4().hex}",
                    "description": "E3-02 数字员工绑定正式验收",
                },
            )
            assert dataset.status_code == 201
            dataset_id = str(dataset.json()["id"])
            name = f"common-agent-e3-02-{uuid4().hex}"
            created = client.post(
                "/api/v1/employees",
                json={
                    "name": name,
                    "description": "E3-02 真实绑定验收",
                    "system_prompt": "根据已绑定知识库回答。",
                    "default_model_configuration_id": str(DEFAULT_TEST_MODEL_CONFIGURATION_ID),
                    "knowledge_base_id": dataset_id,
                },
            )
            assert created.status_code == 201
            employee_id = str(created.json()["id"])
            assert created.json()["knowledge_base_id"] == dataset_id

            missing_binding = client.post(
                "/api/v1/employees",
                json={
                    "name": f"missing-{uuid4().hex}",
                    "description": "不应落库",
                    "system_prompt": "通用指令",
                    "default_model_configuration_id": str(DEFAULT_TEST_MODEL_CONFIGURATION_ID),
                    "knowledge_base_id": f"missing-{uuid4().hex}",
                },
            )
            assert missing_binding.status_code == 404
            assert missing_binding.json()["code"] == "knowledge_base_not_found"
            rejected_update = client.put(
                f"/api/v1/employees/{employee_id}",
                json={
                    "name": name,
                    "description": "不应覆盖原绑定",
                    "system_prompt": "不应保存的指令",
                    "default_model_configuration_id": str(DEFAULT_TEST_MODEL_CONFIGURATION_ID),
                    "knowledge_base_id": f"missing-{uuid4().hex}",
                },
            )
            assert rejected_update.status_code == 404
            assert rejected_update.json()["code"] == "knowledge_base_not_found"
            unchanged = client.get(f"/api/v1/employees/{employee_id}")
            assert unchanged.status_code == 200
            assert unchanged.json()["knowledge_base_id"] == dataset_id
            assert unchanged.json()["description"] == "E3-02 真实绑定验收"
            listed = client.get("/api/v1/employees")
            assert listed.status_code == 200
            assert [item["id"] for item in listed.json()["items"] if item["name"] == name] == [
                employee_id
            ]

        with (
            running_api(TEST_DATABASE_URL, env_overrides=environment) as restarted_url,
            authenticated_client(base_url=restarted_url, timeout=120) as restarted_client,
        ):
            restored = restarted_client.get(f"/api/v1/employees/{employee_id}")
            assert restored.status_code == 200
            assert restored.json()["knowledge_base_id"] == dataset_id
    finally:
        if employee_id is not None:
            asyncio.run(_delete_real_employee(employee_id))
        if dataset_id is not None:
            asyncio.run(delete_dataset(base_url, api_key, dataset_id))


def test_real_workflow_http_validates_and_persists_knowledge_reference() -> None:
    base_url = os.environ.get("TEST_RAGFLOW_BASE_URL")
    api_key = os.environ.get("TEST_RAGFLOW_API_KEY")
    expected_version = os.environ.get("TEST_RAGFLOW_EXPECTED_VERSION")
    if not base_url or not expected_version:
        pytest.skip("真实 RAGFlow 地址或期望版本未配置")
    if not api_key:
        api_key = asyncio.run(provision_api_key(base_url))

    dataset_id: str | None = None
    workflow_id: str | None = None
    try:
        environment = {
            "RAGFLOW_BASE_URL": base_url,
            "RAGFLOW_API_KEY": api_key,
            "RAGFLOW_EXPECTED_VERSION": expected_version,
            "RAGFLOW_TIMEOUT_SECONDS": "120",
        }
        with (
            running_api(TEST_DATABASE_URL, env_overrides=environment) as api_url,
            authenticated_client(base_url=api_url, timeout=120) as client,
        ):
            dataset = client.post(
                "/api/v1/knowledge-bases",
                json={
                    "name": f"common-agent-w5-02-{uuid4().hex}",
                    "description": "W5-02 工作流知识引用正式验收",
                },
            )
            assert dataset.status_code == 201
            dataset_id = str(dataset.json()["id"])
            graph = _workflow_body(dataset_id)
            validated = client.post("/api/v1/workflows/validate", json=graph)
            assert validated.status_code == 200
            assert validated.json() == {"valid": True, "issues": []}

            created = client.post("/api/v1/workflows", json=graph)
            assert created.status_code == 201
            workflow_id = str(created.json()["id"])
            assert created.json()["nodes"][1]["config"]["knowledge_base_id"] == dataset_id

            missing_graph = _workflow_body(f"missing-{uuid4().hex}")
            rejected = client.post("/api/v1/workflows/validate", json=missing_graph)
            assert rejected.status_code == 200
            assert rejected.json()["valid"] is False
            assert rejected.json()["issues"] == [
                {
                    "code": "knowledge_base_not_found",
                    "message": "知识检索节点引用的知识库不存在或已失效",
                    "node_id": "retrieve",
                    "edge_id": None,
                }
            ]

        with (
            running_api(TEST_DATABASE_URL, env_overrides=environment) as restarted_url,
            authenticated_client(base_url=restarted_url, timeout=120) as restarted_client,
        ):
            restored = restarted_client.get(f"/api/v1/workflows/{workflow_id}")
            assert restored.status_code == 200
            assert restored.json()["nodes"][1]["config"]["knowledge_base_id"] == dataset_id
    finally:
        if workflow_id is not None:
            asyncio.run(delete_workflows_from_database_url(TEST_DATABASE_URL, workflow_id))
        if dataset_id is not None:
            asyncio.run(delete_dataset(base_url, api_key, dataset_id))


def _workflow_body(knowledge_base_id: str) -> dict[str, object]:
    return {
        "name": f"common-agent-w5-02-{uuid4().hex}",
        "description": "W5-02 正式 API 与真实 RAGFlow 验收",
        "nodes": [
            {
                "id": "start",
                "type": "start",
                "position": {"x": 0, "y": 0},
                "config": {},
            },
            {
                "id": "retrieve",
                "type": "knowledge_retrieval",
                "position": {"x": 240, "y": 0},
                "config": {"knowledge_base_id": knowledge_base_id},
            },
            {
                "id": "end",
                "type": "end",
                "position": {"x": 480, "y": 0},
                "config": {},
            },
        ],
        "edges": [
            {"id": "edge-1", "source": "start", "target": "retrieve"},
            {"id": "edge-2", "source": "retrieve", "target": "end"},
        ],
    }


async def _delete_real_employee(employee_id: str) -> None:
    database = Database(TEST_DATABASE_URL)
    await database.start()
    try:
        await delete_employees(database, employee_id)
    finally:
        await database.stop()
