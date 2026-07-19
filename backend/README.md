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

先启动平台正式 MySQL，再启动本机 API：

```bash
../infra/platform/manage.sh up
uv run python -m common_agent
```

默认只监听 `127.0.0.1:18200`，可通过根目录 `.env.example` 中的同名环境变量覆盖；非 loopback 地址会被拒绝。

启动时会通过 Alembic 把平台正式 MySQL 升级到 `head` 并执行连接探测。默认连接为 `127.0.0.1:19506/common_agent`，使用 SQLAlchemy async、`asyncmy` 和 MySQL 8.4 LTS；该实例、端口和 Volume 与 RAGFlow 内部 MySQL 完全隔离。配置只接受带用户名、密码、端口和数据库名的 loopback `mysql+asyncmy` URL。

单独运行迁移时必须显式指定目标，避免误建占位数据库：

```bash
COMMON_AGENT_DATABASE_URL='mysql+asyncmy://common_agent:common_agent_dev@127.0.0.1:19506/common_agent?charset=utf8mb4' \
  uv run alembic upgrade head
```

知识库公开入口统一位于 `/api/v1/knowledge-bases`：支持列表、创建、单文件上传和文档解析
状态列表。上传只接受 TXT、Markdown、PDF、DOCX，单文件最大 20 MiB；文件会在读取完成或
失败后关闭，RAGFlow 不可用、版本漂移、结果未知和上传输入错误均转换为稳定错误信封。
正式入口只读取 loopback `RAGFLOW_*` 配置，并在 FastAPI lifespan 中创建和释放 RAGFlow
客户端。

数字员工使用平台自有 `employees` 表保存通用会话角色配置：名称、说明、系统指令、可选的
RAGFlow 知识库 ID 和独立工作流 allowlist。表由 `20260719_0002` 迁移建立，字段长度、空白、
JSON 数组和 UTC 时间顺序同时受领域模型与 MySQL CHECK 约束；`DATETIME(6)` 保留更新时间精度。
知识库 ID 是外围服务的不透明引用，不对 RAGFlow 内库建外键，绑定有效性必须由应用层通过
正式 `KnowledgeService` 校验。

数字员工公开入口为 `/api/v1/employees`：集合支持 GET/POST，`/{employee_id}` 支持 GET/PUT。
创建和更新请求只接受上述通用会话配置，不接受业务字段，也暂不允许客户端写入工作流
allowlist。非空知识库 ID 会先经 `KnowledgeBaseService` 和 RAGFlow 官方数据集详情 API 校验，
只有验证成功后才进入 Employee Unit of Work 并提交 MySQL；失效引用、RAGFlow 不可用或未配置
都会关闭失败且不写入。员工不存在时优先返回 `employee_not_found`，不发起无意义的外围校验。

`ModelSettings.from_env()` 默认读取版本化的 `.env.demo`，并允许同名 `BAILIAN_*` 环境变量覆盖。`.env.demo` 只保存用户明确批准的测试模型、HTTPS Base URL 和 Demo Key；Key 使用 `SecretStr`，不得进入 repr、JSON、日志、异常或前端响应。
