from __future__ import annotations

import asyncio
import os
from time import monotonic
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

_TEST_EMAIL = "common-agent@local.test"
# RAGFlow 官方 SDK 测试夹具提供的 RSA 密文, 对应仅限 loopback 测试账号的密码 123。
_TEST_PASSWORD = (
    "ctAseGvejiaSWWZ88T/m4FQVOpQyUvP+x7sXtdv3feqZACiQleuewkUi35E16wSd5C5QcnkkcV9cYc8T"
    "KPTRZlxappDuirxghxoOvFcJxFU4ixLsDfN33jCHRoDUW81IH9zjij/vaw8IbVyb6vuwg6MX6inOEBRRzVbRYxXO"
    "u1wkWY6SsI8X70oF9aeLFp/PzQpjoe/YbSqpTq8qqrmHzn9vO+yvyYyvmDsphXeX8f7fp9c7vUsfOCkM+gHY3Pad"
    "G+QHa7KI7mzTKgUTZImK6BZtfRBATDTthEUbbaTewY4H0MnWiCeeDhcbeQao6cFy1To8pE3RpmxnGnS8BsBn8w=="
)


async def _provision_api_key(base_url: str) -> str:
    async with httpx.AsyncClient(base_url=base_url, timeout=60.0) as client:
        registration = await client.post(
            "/api/v1/users",
            json={
                "email": _TEST_EMAIL,
                "nickname": "common-agent",
                "password": _TEST_PASSWORD,
            },
        )
        registration.raise_for_status()
        registration_payload = registration.json()
        if registration_payload["code"] != 0:
            assert "already registered" in registration_payload["message"]

        login = await client.post(
            "/api/v1/auth/login",
            json={"email": _TEST_EMAIL, "password": _TEST_PASSWORD},
        )
        login.raise_for_status()
        assert login.json()["code"] == 0
        authorization = login.headers["Authorization"]

        tokens = await client.get(
            "/api/v1/system/tokens",
            headers={"Authorization": authorization},
        )
        tokens.raise_for_status()
        tokens_payload = tokens.json()
        assert tokens_payload["code"] == 0
        if tokens_payload["data"]:
            return str(tokens_payload["data"][0]["token"])

        created = await client.post(
            "/api/v1/system/tokens",
            headers={"Authorization": authorization},
        )
        created.raise_for_status()
        created_payload = created.json()
        assert created_payload["code"] == 0
        return str(created_payload["data"]["token"])


async def _delete_dataset(base_url: str, api_key: str, dataset_id: str) -> None:
    async with httpx.AsyncClient(base_url=base_url, timeout=60.0) as client:
        response = await client.request(
            "DELETE",
            "/api/v1/datasets",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"ids": [dataset_id]},
        )
        response.raise_for_status()
        payload = response.json()
        assert payload["code"] == 0


def test_real_ragflow_adapter_lifecycle() -> None:
    base_url = os.environ.get("TEST_RAGFLOW_BASE_URL")
    api_key = os.environ.get("TEST_RAGFLOW_API_KEY")
    expected_version = os.environ.get("TEST_RAGFLOW_EXPECTED_VERSION")
    if not base_url or not expected_version:
        pytest.skip("真实 RAGFlow 地址或期望版本未配置")
    if not api_key:
        api_key = asyncio.run(_provision_api_key(base_url))

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
            await _delete_dataset(base_url, api_key, dataset_id)
