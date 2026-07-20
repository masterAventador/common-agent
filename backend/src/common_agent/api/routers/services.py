from __future__ import annotations

from fastapi import Request

from common_agent.api.errors import AppError
from common_agent.application.workflow_service import WorkflowService
from common_agent.conversations.events import ConversationEventBroker
from common_agent.conversations.service import ConversationService
from common_agent.workflows.events import WorkflowEventBroker


def conversation_service(request: Request) -> ConversationService:
    application = getattr(request.app.state, "conversations", None)
    if not isinstance(application, ConversationService):
        raise AppError(
            code="conversation_service_unavailable",
            message="会话服务暂时不可用",
            status_code=503,
            retryable=True,
        )
    return application


def conversation_event_broker(request: Request) -> ConversationEventBroker:
    broker = getattr(request.app.state, "conversation_events", None)
    if not isinstance(broker, ConversationEventBroker):
        raise AppError(
            code="conversation_service_unavailable",
            message="会话服务暂时不可用",
            status_code=503,
            retryable=True,
        )
    return broker


def workflow_service(request: Request) -> WorkflowService:
    application = getattr(request.app.state, "workflows", None)
    if not isinstance(application, WorkflowService):
        raise AppError(
            code="workflow_service_unavailable",
            message="工作流服务暂时不可用",
            status_code=503,
            retryable=True,
        )
    return application


def workflow_event_broker(request: Request) -> WorkflowEventBroker:
    broker = getattr(request.app.state, "workflow_events", None)
    if not isinstance(broker, WorkflowEventBroker):
        raise AppError(
            code="workflow_service_unavailable",
            message="工作流服务暂时不可用",
            status_code=503,
            retryable=True,
        )
    return broker


__all__ = [
    "conversation_event_broker",
    "conversation_service",
    "workflow_event_broker",
    "workflow_service",
]
