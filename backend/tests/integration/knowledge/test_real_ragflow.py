from __future__ import annotations

import asyncio
import os
from time import monotonic, sleep
from uuid import uuid4

import httpx
import pytest

from common_agent.adapters.knowledge.ragflow import RagFlowKnowledgeService
from common_agent.domain.knowledge import (
    CreateKnowledgeBaseRequest,
    DocumentParsingStatus,
    DocumentUpload,
    KnowledgeRetrievalRequest,
    KnowledgeServiceAvailability,
)
from tests.support.http import running_api
from tests.support.ragflow import delete_dataset, provision_api_key
from tests.support.settings import TEST_DATABASE_URL


def test_real_ragflow_adapter_lifecycle() -> None:
    base_url = os.environ.get("TEST_RAGFLOW_BASE_URL")
    api_key = os.environ.get("TEST_RAGFLOW_API_KEY")
    expected_version = os.environ.get("TEST_RAGFLOW_EXPECTED_VERSION")
    if not base_url or not expected_version:
        pytest.skip("真实 RAGFlow 地址或期望版本未配置")
    if not api_key:
        api_key = asyncio.run(provision_api_key(base_url))

    asyncio.run(_real_lifecycle(base_url, api_key, expected_version))


async def _real_lifecycle(base_url: str, api_key: str, expected_version: str) -> None:
    service = RagFlowKnowledgeService(
        base_url=base_url,
        api_key=api_key,
        expected_version=expected_version,
        timeout_seconds=120.0,
    )
    dataset_id: str | None = None
    marker = f"星河-{uuid4().hex}"
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

        uploaded = await service.upload_document(
            dataset.id,
            DocumentUpload(
                file_name="k2-03-acceptance.txt",
                content_type="text/plain",
                content=f"common-agent 知识库验收暗号是 {marker}。".encode(),
            ),
        )
        assert uploaded.parsing_status is DocumentParsingStatus.PARSING

        deadline = monotonic() + 900
        while monotonic() < deadline:
            documents = await service.list_documents(dataset.id)
            current = next(item for item in documents if item.id == uploaded.id)
            if current.parsing_status is DocumentParsingStatus.COMPLETED:
                break
            if current.parsing_status is DocumentParsingStatus.FAILED:
                pytest.fail(f"真实 RAGFlow 文档解析失败: {current.error_code}")
            await asyncio.sleep(2)
        else:
            pytest.fail("真实 RAGFlow 文档解析超时")

        result = await service.retrieve(
            KnowledgeRetrievalRequest(
                knowledge_base_id=dataset.id,
                query=f"common-agent 知识库验收暗号是什么? 提示 {marker}",
                similarity_threshold=0.1,
            )
        )
        assert result.chunks
        assert any(marker in chunk.content for chunk in result.chunks)
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
            httpx.Client(base_url=api_url, timeout=120) as client,
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
            assert dataset_id in {item["id"] for item in listed_response.json()}

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
    finally:
        if dataset_id is not None:
            asyncio.run(delete_dataset(base_url, api_key, dataset_id))
