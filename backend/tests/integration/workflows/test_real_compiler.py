from __future__ import annotations

import asyncio
import os
from time import monotonic
from uuid import uuid4

import pytest

from common_agent.adapters.knowledge.ragflow import RagFlowKnowledgeService
from common_agent.adapters.model.bailian import BailianChatModelAdapter
from common_agent.bootstrap.settings import ModelSettings
from common_agent.domain.knowledge import (
    CreateKnowledgeBaseRequest,
    DocumentParsingStatus,
    DocumentUpload,
)
from common_agent.domain.workflow import (
    AiChatNodeConfig,
    EndNodeConfig,
    KnowledgeRetrievalNodeConfig,
    StartNodeConfig,
    WorkflowDefinition,
    WorkflowEdge,
    WorkflowNode,
    WorkflowNodePosition,
    WorkflowNodeType,
)
from common_agent.knowledge.service import KnowledgeBaseService
from common_agent.workflows.compiler import WorkflowCompiler
from common_agent.workflows.nodes.registry import create_workflow_node_registry
from tests.support.ragflow import delete_dataset, provision_api_key


def test_real_langgraph_compiler_uses_ragflow_and_bailian() -> None:
    base_url = os.environ.get("TEST_RAGFLOW_BASE_URL")
    api_key = os.environ.get("TEST_RAGFLOW_API_KEY")
    expected_version = os.environ.get("TEST_RAGFLOW_EXPECTED_VERSION")
    if os.environ.get("TEST_BAILIAN_REAL") != "1":
        pytest.skip("未显式启用真实百炼验收")
    if not base_url or not expected_version:
        pytest.skip("真实 RAGFlow 地址或期望版本未配置")
    if not api_key:
        api_key = asyncio.run(provision_api_key(base_url))

    asyncio.run(_exercise_real_compiler(base_url, api_key, expected_version))


async def _exercise_real_compiler(base_url: str, api_key: str, expected_version: str) -> None:
    knowledge = RagFlowKnowledgeService(
        base_url=base_url,
        api_key=api_key,
        expected_version=expected_version,
        timeout_seconds=120,
    )
    model = BailianChatModelAdapter(ModelSettings.from_demo_file())
    dataset_id: str | None = None
    marker = f"COMMON_AGENT_W5_03_{uuid4().hex}"
    try:
        dataset = await knowledge.create_knowledge_base(
            CreateKnowledgeBaseRequest(
                name=f"common-agent-w5-03-{uuid4().hex}",
                description="W5-03 LangGraph 编译器真实依赖验收",
            )
        )
        dataset_id = dataset.id
        uploaded = await knowledge.upload_document(
            dataset.id,
            DocumentUpload(
                file_name="w5-03-handbook.txt",
                content_type="text/plain",
                content=f"W5-03 工作流编译器的唯一验收标记是 {marker}。".encode(),
            ),
        )
        deadline = monotonic() + 900
        while monotonic() < deadline:
            documents = await knowledge.list_documents(dataset.id)
            current = next(item for item in documents if item.id == uploaded.id)
            if current.parsing_status is DocumentParsingStatus.COMPLETED:
                break
            if current.parsing_status is DocumentParsingStatus.FAILED:
                pytest.fail(f"W5-03 真实文档解析失败: {current.error_code}")
            await asyncio.sleep(2)
        else:
            pytest.fail("W5-03 真实文档解析超时")

        workflow = _workflow(dataset.id)
        compiler = WorkflowCompiler(
            create_workflow_node_registry(model, KnowledgeBaseService(knowledge))
        )
        result = await compiler.compile(workflow).invoke(
            f"请从知识库找出 W5-03 的唯一验收标记。提示: {marker}"
        )

        assert marker in result.output
        assert result.completed_node_ids == ("start", "retrieve", "chat", "end")
        assert result.step_count == 4
    finally:
        await model.aclose()
        await knowledge.aclose()
        if dataset_id is not None:
            await delete_dataset(base_url, api_key, dataset_id)


def _workflow(knowledge_base_id: str) -> WorkflowDefinition:
    nodes = (
        WorkflowNode(
            id="start",
            type=WorkflowNodeType.START,
            position=WorkflowNodePosition(x=0, y=0),
            config=StartNodeConfig(),
        ),
        WorkflowNode(
            id="retrieve",
            type=WorkflowNodeType.KNOWLEDGE_RETRIEVAL,
            position=WorkflowNodePosition(x=240, y=0),
            config=KnowledgeRetrievalNodeConfig(knowledge_base_id=knowledge_base_id),
        ),
        WorkflowNode(
            id="chat",
            type=WorkflowNodeType.AI_CHAT,
            position=WorkflowNodePosition(x=480, y=0),
            config=AiChatNodeConfig(
                prompt="根据检索到的知识片段回答。只输出唯一验收标记,不要添加其他内容。"
            ),
        ),
        WorkflowNode(
            id="end",
            type=WorkflowNodeType.END,
            position=WorkflowNodePosition(x=720, y=0),
            config=EndNodeConfig(),
        ),
    )
    return WorkflowDefinition.create(
        name="W5-03 真实编译验收",
        nodes=nodes,
        edges=(
            WorkflowEdge(id="edge-1", source="start", target="retrieve"),
            WorkflowEdge(id="edge-2", source="retrieve", target="chat"),
            WorkflowEdge(id="edge-3", source="chat", target="end"),
        ),
    )
