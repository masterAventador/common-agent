from __future__ import annotations

import asyncio
import os
from time import monotonic
from uuid import uuid4

import pytest

from common_agent.adapters.knowledge.ragflow import RagFlowKnowledgeService
from common_agent.domain.conversation import Message
from common_agent.domain.employee import Employee
from common_agent.domain.knowledge import (
    CreateKnowledgeBaseRequest,
    DocumentParsingStatus,
    DocumentUpload,
)
from common_agent.knowledge.retrieval import ConversationKnowledgeResolver
from tests.support.ragflow import delete_dataset, provision_api_key


def test_real_ragflow_conversation_retrieval_and_citation_mapping() -> None:
    base_url = os.environ.get("TEST_RAGFLOW_BASE_URL")
    api_key = os.environ.get("TEST_RAGFLOW_API_KEY")
    expected_version = os.environ.get("TEST_RAGFLOW_EXPECTED_VERSION")
    if not base_url or not expected_version:
        pytest.skip("真实 RAGFlow 地址或期望版本未配置")
    if not api_key:
        api_key = asyncio.run(provision_api_key(base_url))

    asyncio.run(_exercise_real_resolver(base_url, api_key, expected_version))


async def _exercise_real_resolver(base_url: str, api_key: str, expected_version: str) -> None:
    knowledge = RagFlowKnowledgeService(
        base_url=base_url,
        api_key=api_key,
        expected_version=expected_version,
        timeout_seconds=120,
    )
    dataset_id: str | None = None
    marker = f"COMMON_AGENT_A4_05_{uuid4().hex}"
    try:
        dataset = await knowledge.create_knowledge_base(
            CreateKnowledgeBaseRequest(
                name=f"common-agent-a4-05-{uuid4().hex}",
                description="A4-05 会话自动检索真实验收",
            )
        )
        dataset_id = dataset.id
        uploaded = await knowledge.upload_document(
            dataset.id,
            DocumentUpload(
                file_name="a4-05-handbook.txt",
                content_type="text/plain",
                content=f"A4-05 会话自动检索验收标记是 {marker}。".encode(),
            ),
        )
        deadline = monotonic() + 900
        while monotonic() < deadline:
            documents = await knowledge.list_documents(dataset.id)
            current = next(item for item in documents if item.id == uploaded.id)
            if current.parsing_status is DocumentParsingStatus.COMPLETED:
                break
            if current.parsing_status is DocumentParsingStatus.FAILED:
                pytest.fail(f"A4-05 真实文档解析失败: {current.error_code}")
            await asyncio.sleep(2)
        else:
            pytest.fail("A4-05 真实文档解析超时")

        employee = Employee.create(
            name="A4-05 知识助理",
            system_prompt="根据绑定知识库回答。",
            knowledge_base_id=dataset.id,
        )
        user_message = Message.create_user(
            conversation_id=uuid4(),
            sequence_number=1,
            content=f"会话自动检索验收标记是什么? 提示: {marker}",
        )
        resolved = await ConversationKnowledgeResolver(knowledge).resolve(
            employee,
            user_message,
        )

        assert resolved.knowledge_base_id == dataset.id
        assert resolved.runtime_chunks
        assert resolved.citations
        assert len(resolved.runtime_chunks) == len(resolved.citations)
        assert any(marker in chunk.content for chunk in resolved.runtime_chunks)
        assert [citation.position for citation in resolved.citations] == list(
            range(1, len(resolved.citations) + 1)
        )
        assert [chunk.chunk_id for chunk in resolved.runtime_chunks] == [
            citation.chunk_id for citation in resolved.citations
        ]
    finally:
        await knowledge.aclose()
        if dataset_id is not None:
            await delete_dataset(base_url, api_key, dataset_id)
