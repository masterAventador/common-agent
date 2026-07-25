from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

from common_agent.domain.model_configuration import ModelConfiguration, ModelConfigurationInput
from common_agent.model_configurations.service import ModelConfigurationService
from common_agent.tenancy import bind_tenant, system_tenant_access

# 默认工作区预置的百炼聊天模型, 覆盖各厂商前沿代际。
#
# 收录标准是"在当前项目接入的百炼端点上实测可调通", 不以模型广场是否上架为准。每个候选都在
# 三条真实路径上验证过, 三条全过才预置:
#   1. 非流式对话: 返回标准 choices/message.content 结构;
#   2. 流式对话: 返回标准 SSE 且有文本增量;
#   3. 流式 + 工具: 能返回 tool_calls, 满足数字员工 (Deep Agents) 的调用形态。
# 另外单独验证过每个模型都会输出真正的 content, 而不是只有 reasoning_content 思考内容,
# 否则平台会判定为空回复。标识必须不含斜杠, 以通过 model_identifier 校验。
#
# 不收录 qwen-max: 该端点上 qwen-max 返回的响应不是 OpenAI 标准结构 (仅有 finish_reason/text,
# 无 choices/message), 平台适配层无法解析, 测试调用与会话都会失败。旗舰位由 qwen3.7-max 承担。
#
# 不再收录 deepseek-v3 与 deepseek-r1: 百炼文档标注二者 (含 deepseek-v3.1、deepseek-r1-0528)
# 于 2026-10-10 下架, 已替换为同厂商前沿代际 deepseek-v4-pro / deepseek-v4-flash。
#
# 智谱 GLM 与月之暗面 Kimi 此前因"标识含斜杠、需控制台单独开通"被排除; 实测该端点同时提供
# 不含斜杠的合规标识 (glm-5.2、kimi-k2.6), 且凭平台统一 API Key 三条路径均直接调通, 故收录。
COMMON_MODEL_CONFIGURATION_SEEDS: tuple[ModelConfigurationInput, ...] = (
    ModelConfigurationInput(
        display_name="通义千问3.7-Max", model_identifier="qwen3.7-max", enabled=True
    ),
    ModelConfigurationInput(
        display_name="通义千问3.7-Plus", model_identifier="qwen3.7-plus", enabled=True
    ),
    ModelConfigurationInput(
        display_name="通义千问3.7-Flash", model_identifier="qwen3.7-flash", enabled=True
    ),
    ModelConfigurationInput(
        display_name="通义千问-Plus", model_identifier="qwen-plus", enabled=True
    ),
    ModelConfigurationInput(
        display_name="通义千问-Turbo", model_identifier="qwen-turbo", enabled=True
    ),
    ModelConfigurationInput(
        display_name="通义千问-Long", model_identifier="qwen-long", enabled=True
    ),
    ModelConfigurationInput(
        display_name="DeepSeek-V4-Pro", model_identifier="deepseek-v4-pro", enabled=True
    ),
    ModelConfigurationInput(
        display_name="DeepSeek-V4-Flash", model_identifier="deepseek-v4-flash", enabled=True
    ),
    ModelConfigurationInput(display_name="智谱GLM-5.2", model_identifier="glm-5.2", enabled=True),
    ModelConfigurationInput(display_name="Kimi-K2.6", model_identifier="kimi-k2.6", enabled=True),
    ModelConfigurationInput(
        display_name="MiniMax-M2.5", model_identifier="MiniMax-M2.5", enabled=True
    ),
)


async def seed_common_model_configurations(
    service: ModelConfigurationService,
) -> list[ModelConfiguration]:
    """在当前工作区幂等预置常用百炼模型配置, 返回每个标识对应的最终配置。

    通过 ModelConfigurationService.ensure 复用正式服务与仓储: 已存在的标识
    (如迁移预置的默认 qwen-plus) 原样保留, 缺失的按启用状态创建。重复调用安全。
    """
    return [await service.ensure(seed) for seed in COMMON_MODEL_CONFIGURATION_SEEDS]


async def seed_common_model_configurations_for_tenants(
    service: ModelConfigurationService,
    tenant_ids: Iterable[UUID],
) -> None:
    """对多个工作区分别在各自租户上下文中幂等预置常用百炼模型配置。

    模型配置按 tenant_id 隔离, 因此对每个目标工作区先绑定其系统租户上下文,
    再复用单工作区的 seed_common_model_configurations。用于启动时覆盖全部现有
    工作区, 以及新建工作区时初始化单个工作区; 重复调用安全。
    """
    for tenant_id in tenant_ids:
        with bind_tenant(system_tenant_access(tenant_id)):
            await seed_common_model_configurations(service)


__all__ = [
    "COMMON_MODEL_CONFIGURATION_SEEDS",
    "seed_common_model_configurations",
    "seed_common_model_configurations_for_tenants",
]
