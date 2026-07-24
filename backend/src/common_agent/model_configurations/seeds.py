from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

from common_agent.domain.model_configuration import ModelConfiguration, ModelConfigurationInput
from common_agent.model_configurations.service import ModelConfigurationService
from common_agent.tenancy import bind_tenant, system_tenant_access

# 默认工作区预置的常用阿里百炼聊天模型。
#
# 只收录"百炼平台一方部署, 凭平台统一 API Key 即可直接调用, 无需在控制台单独开通"
# 的模型标识, 确保 seed 出来的配置都能真实调通:
# - 通义千问系列 qwen-*: 阿里自研一方模型, 随百炼 API Key 默认可用;
# - DeepSeek R1/V3 deepseek-*: 由阿里云在百炼上部署, 凭 API Key 直接调用, 无需开通第三方模型。
#
# 刻意不收录智谱 GLM、月之暗面 Kimi 等第三方直供模型: 它们虽在百炼模型广场上架, 但
# 1. 必须先在百炼控制台"立即开通"后账号才能调用, 新工作区默认调不通;
# 2. 其百炼标识形如 ZHIPU/GLM-5.2、kimi/kimi-k3, 含斜杠, 无法通过平台
#    model_identifier 校验 (仅允许字母、数字、点、下划线、连字符)。
# 因此按"宁可少预置也不预置调不通的模型"原则排除, 等真实开通与标识校验放开后再单独评估。
COMMON_MODEL_CONFIGURATION_SEEDS: tuple[ModelConfigurationInput, ...] = (
    ModelConfigurationInput(display_name="通义千问-Max", model_identifier="qwen-max", enabled=True),
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
        display_name="DeepSeek-R1", model_identifier="deepseek-r1", enabled=True
    ),
    ModelConfigurationInput(
        display_name="DeepSeek-V3", model_identifier="deepseek-v3", enabled=True
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
