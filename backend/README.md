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

`COMMON_AGENT_INTEGRATION_MODE` 默认且正式取值为 `real`，会接入 RAGFlow、Deep Agents 与阿里
百炼。设为 `demo` 时仍使用同一 FastAPI、MySQL、领域服务、REST/SSE 和 React 页面，只把知识
服务与员工运行时切换为确定性固定适配器；健康接口返回 `integration_mode=demo`，前端必须显示
“演示模式”，不得把固定回答冒充真实外部服务。Demo 知识数据仅保存在当前后端进程内，员工、
会话、消息和引用仍写入正式配置的 MySQL。

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

正式 App 每次启动都会幂等确保固定 UUID `6f3d43e0-6f6d-5a67-9f25-756a0b9ed2ab` 的通用
“知识助理”存在。它默认不绑定知识库或工作流；若记录已存在，启动过程只读取，不覆盖用户
通过正式 API 修改的名称、说明、系统指令或绑定。多进程同时启动时由二次读取、主键唯一约束
和冲突后重读收敛到同一记录。

会话持久化由 `20260719_0003` 迁移建立 `conversations`、`messages` 和
`message_citations`。会话以正式外键引用数字员工；消息在同一会话内使用唯一正整数序号，
用户消息直接为 `completed`，助手消息只允许从 `pending/streaming` 进入
`completed/failed/stopped` 终态。引用按连续位置单独保存并随消息读取，只有已完成助手消息
可由领域模型携带引用。Conversation Unit of Work 让发送用例原子提交用户消息、助手占位与状态更新。

会话公开入口位于 `/api/v1/conversations`：支持创建/列表、消息历史、发送、停止、失败或已停止
消息重试，以及 `/{conversation_id}/events` SSE。发送请求必须携带客户端生成的 `message_id`；
平台先原子提交用户消息和助手占位消息，再启动知识检索与 Deep Agents。每个 delta/终态也先更新
MySQL 并提交，之后才发布带 `schema_version/conversation_id/message_id/turn_id/sequence` 的
平台事件。SSE 可通过 `after_sequence` 或 `Last-Event-ID` 续传；历史已淘汰或进程重启后不能续传
时返回 `event_history_unavailable`，调用方应重新加载权威消息历史。

同一会话同时只允许一个活跃回复；重复 `message_id`、并发发送、无活跃生成时停止和非法重试均
返回稳定冲突码。停止后重试复用原助手消息身份和序号，清空上次不完整内容，不重复写用户消息。
应用关闭时先请求所有活跃运行停止再释放模型客户端；启动时把上次进程遗留的
`pending/streaming` 助手消息恢复为 `failed/generation_interrupted`，避免页面永久显示生成中。

`ModelSettings.from_env()` 默认读取版本化的 `.env.demo`，并允许同名 `BAILIAN_*` 环境变量覆盖。`.env.demo` 只保存用户明确批准的测试模型、HTTPS Base URL 和 Demo Key；Key 使用 `SecretStr`，不得进入 repr、JSON、日志、异常或前端响应。Base URL 只接受百炼官方 `compatible-mode/v1` HTTPS 地址，禁止 URL 凭据、查询参数和非官方主机。

`BailianChatModelAdapter` 使用锁定的 `langchain-openai==1.3.5` 构造正式 `ChatOpenAI`，通过 `stream_text()` 暴露增量文本，并通过 `chat_model` 把同一个模型实例交给 Deep Agents 适配层。每个适配器显式创建独立同步/异步 HTTP 客户端，关闭当前实例不会关闭其他会话使用的客户端。总请求超时、流式逐块超时与重试次数分别由 `BAILIAN_TIMEOUT_SECONDS`、`BAILIAN_STREAM_CHUNK_TIMEOUT_SECONDS` 和 `BAILIAN_MAX_RETRIES` 控制，默认 `60/60/2`，最大 `300/300/3`；认证、请求拒绝、限流、超时、5xx、流中断和空输出都会转换成不含上游响应体或凭据的稳定平台错误。持有适配器的 lifespan 必须调用幂等 `aclose()` 释放自有模型客户端。

`EmployeeRuntime` 是一次会话回复的框架无关协议：`stream(request, stop=...)` 接收 Conversation/Employee/助手消息 ID、有序聊天历史、员工系统指令、显式知识库绑定与检索片段，以及允许调用的工作流 ID；它不包含旧任务模型的启动、审批、恢复或产物接口。运行时只返回单调递增的 `delta` 和一个 `completed/failed/stopped` 终态，终态后的事件由 `RuntimeEventEmitter` 拒绝。`RuntimeStopToken` 可重复请求但只在第一次改变状态；Deep Agents 适配器会让停止信号与上游下一事件竞速，停止胜出后关闭异步流。系统指令、历史正文、知识片段和模型增量均从对象 repr 排除。

`DeepAgentsEmployeeRuntime` 固定使用 `deepagents==0.6.12` 的公开 `create_deep_agent`。它通过 `DeepAgentToolRegistry` 只装配员工本轮白名单中的平台工具，使用非 Sandbox 的 `StateBackend`，并通过公开 Harness Profile 和文件权限规则从模型工具面移除 Todo、本机文件、Shell、默认子代理和 `task`。知识片段被标记为不可信外部数据；Deep Agents 原始消息、工具和异常不会越过适配层。

`ConversationKnowledgeResolver` 把员工绑定与当前已完成用户消息转换为本轮知识上下文。未绑定员工直接返回无知识库语义且不访问 RAGFlow；已绑定员工每次都先经 `KnowledgeBaseService` 检查真实服务可用性和 `v0.25.6` 版本，再按固定首版参数检索。零命中保留知识库 ID；命中片段按原顺序映射成同源的 `RuntimeKnowledgeChunk` 与连续 `Citation`。配置、版本、知识库不存在、服务失败、非法响应和调用方取消均保持明确语义，不静默跳过检索。
