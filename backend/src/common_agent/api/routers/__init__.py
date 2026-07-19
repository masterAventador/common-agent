from common_agent.api.routers.conversations import router as conversation_router
from common_agent.api.routers.employees import router as employee_router
from common_agent.api.routers.knowledge import router as knowledge_router
from common_agent.api.routers.system import router as system_router
from common_agent.api.routers.workflows import router as workflow_router

__all__ = [
    "conversation_router",
    "employee_router",
    "knowledge_router",
    "system_router",
    "workflow_router",
]
