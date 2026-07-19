from uuid import UUID

from common_agent.domain.employee import Employee, EmployeeConfiguration
from common_agent.employees.service import EmployeeService

DEFAULT_KNOWLEDGE_ASSISTANT_ID = UUID("6f3d43e0-6f6d-5a67-9f25-756a0b9ed2ab")
DEFAULT_KNOWLEDGE_ASSISTANT_CONFIGURATION = EmployeeConfiguration(
    name="知识助理",
    description="可按需绑定知识库的通用会话助理",
    system_prompt=(
        "请准确清晰地回答用户问题。优先依据提供的知识库上下文。"
        "没有可靠上下文时请明确说明。避免编造信息。"
    ),
    knowledge_base_id=None,
)


async def seed_default_employee(service: EmployeeService) -> Employee:
    return await service.ensure(
        DEFAULT_KNOWLEDGE_ASSISTANT_ID,
        DEFAULT_KNOWLEDGE_ASSISTANT_CONFIGURATION,
    )
