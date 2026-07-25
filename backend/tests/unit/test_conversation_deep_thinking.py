from __future__ import annotations

from uuid import uuid4

from common_agent.conversations.targets import effective_deep_thinking
from common_agent.domain.employee import Employee


def _employee(*, deep_thinking_enabled: bool) -> Employee:
    return Employee.create(
        name="被测员工",
        system_prompt="回答问题。",
        default_model_configuration_id=uuid4(),
        default_model_identifier="qwen-plus",
        deep_thinking_enabled=deep_thinking_enabled,
    )


def test_switch_on_asks_the_model_to_think() -> None:
    """打开时显式要求思考: 默认不思考的模型(如 qwen-plus)也会给出思考过程。"""
    assert (
        effective_deep_thinking(
            _employee(deep_thinking_enabled=True), thinking_can_be_disabled=True
        )
        is True
    )


def test_switch_off_asks_the_model_to_skip_thinking() -> None:
    assert (
        effective_deep_thinking(
            _employee(deep_thinking_enabled=False), thinking_can_be_disabled=True
        )
        is False
    )


def test_switch_off_is_not_forced_on_a_model_that_refuses_to_stop_thinking() -> None:
    """MiniMax-M2.5 实测拒绝 enable_thinking=false, 硬传会让这个员工彻底不能对话。

    这种模型上不下发该参数, 让它按自身行为继续; 界面另行明确提示关不掉。
    """
    assert (
        effective_deep_thinking(
            _employee(deep_thinking_enabled=False), thinking_can_be_disabled=False
        )
        is None
    )


def test_switch_on_still_works_on_a_model_that_only_supports_thinking() -> None:
    assert (
        effective_deep_thinking(
            _employee(deep_thinking_enabled=True), thinking_can_be_disabled=False
        )
        is True
    )


def test_generic_conversation_keeps_the_provider_default() -> None:
    """通用 AI 没有员工配置, 不去改模型自身的思考行为。"""
    assert effective_deep_thinking(None, thinking_can_be_disabled=True) is None
