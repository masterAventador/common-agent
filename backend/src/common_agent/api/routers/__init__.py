from common_agent.api.routers.audit import router as audit_router
from common_agent.api.routers.auth import router as auth_router
from common_agent.api.routers.conversations import router as conversation_router
from common_agent.api.routers.employees import router as employee_router
from common_agent.api.routers.knowledge import router as knowledge_router
from common_agent.api.routers.model_configurations import router as model_configuration_router
from common_agent.api.routers.system import router as system_router
from common_agent.api.routers.tenants import router as tenant_router
from common_agent.api.routers.tools import router as tool_router
from common_agent.api.routers.workflow_runs import router as workflow_run_router
from common_agent.api.routers.workflows import router as workflow_router

__all__ = [
    "audit_router",
    "auth_router",
    "conversation_router",
    "employee_router",
    "knowledge_router",
    "model_configuration_router",
    "system_router",
    "tenant_router",
    "tool_router",
    "workflow_router",
    "workflow_run_router",
]
