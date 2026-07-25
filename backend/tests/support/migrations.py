"""测试用的迁移信息。

历史上有两处测试写死了"当前最新迁移版本号", 每加一个迁移就要人工同步, 漏改会让整套集成
测试连不上数据库(其中一处还会把版本号强行改回旧值, 导致下次启动重复执行迁移)。这里直接问
Alembic 要 head, 新增迁移不再需要改测试。
"""

from __future__ import annotations

from alembic.config import Config
from alembic.script import ScriptDirectory

from common_agent.adapters.persistence.migrations import _alembic_config_path


def current_head_revision() -> str:
    config = Config(str(_alembic_config_path()))
    head = ScriptDirectory.from_config(config).get_current_head()
    if head is None:
        raise RuntimeError("无法确定当前 Alembic head")
    return head
