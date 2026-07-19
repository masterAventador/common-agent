# Backend

Python/FastAPI 后端工程。B1-01 会在此建立 Python 3.12、uv、`src` layout 和测试工具链，后续业务代码统一位于 `src/common_agent/`。

边界：

- 浏览器只调用本后端公开 API；
- 领域与应用层不依赖第三方 SDK；
- 数据库、中间件、模型、RAGFlow、Deep Agents 和 LangGraph 通过正式端口/适配层接入；
- 本目录不保存本机运行数据、上传文件、日志或除已授权百炼 Demo Key 外的凭据。

## 工具链

```bash
uv sync --frozen
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src tests
```

启动本机 API：

```bash
uv run python -m common_agent
```

默认只监听 `127.0.0.1:18200`，可通过根目录 `.env.example` 中的同名环境变量覆盖；非 loopback 地址会被拒绝。

启动时会通过 Alembic 把当前正式数据库升级到 `head` 并执行连接探测。默认数据库位于仓库根目录 `.local/common-agent.db`；可使用 `COMMON_AGENT_DATABASE_URL` 指向其他正式 SQLAlchemy async 适配器。

单独运行迁移时必须显式指定目标，避免误建占位数据库：

```bash
COMMON_AGENT_DATABASE_URL=sqlite+aiosqlite:////absolute/path/to/database.db \
  uv run alembic upgrade head
```
