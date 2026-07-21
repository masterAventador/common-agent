# Backend

Python/FastAPI 后端工程。B1-01 会在此建立 Python 3.12、uv、`src` layout 和测试工具链，后续业务代码统一位于 `src/common_agent/`。

边界：

- 浏览器只调用本后端公开 API；
- 领域与应用层不依赖第三方 SDK；
- 数据库、中间件、模型、RAGFlow、Deep Agents 和 LangGraph 通过正式端口/适配层接入；
- 本目录不保存本机运行数据、上传文件、日志或除用户明确授权的现有百炼 Demo Key 外的凭据。

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
“演示模式”，不得把固定回答冒充真实外部服务。Demo 知识库、文档正文和完成态由
`20260720_0007` 迁移建立的项目专属 MySQL 表保存，与员工、会话、消息和引用一起在后端重启后
恢复；Demo 不借此冒充 RAGFlow 解析、向量或重排能力。

启动时会通过 Alembic 把平台正式 MySQL 升级到 `head` 并执行连接探测。默认连接为 `127.0.0.1:19506/common_agent`，使用 SQLAlchemy async、`aiomysql`、PyMySQL `>=1.1.1` 和 MySQL 8.4 LTS；该实例、端口和 Volume 与 RAGFlow 内部 MySQL 完全隔离。配置只接受带用户名、密码、端口和数据库名的 loopback `mysql+aiomysql` URL。

单独运行迁移时必须显式指定目标，避免误建占位数据库：

```bash
COMMON_AGENT_DATABASE_URL='mysql+aiomysql://common_agent:common_agent_dev@127.0.0.1:19506/common_agent?charset=utf8mb4' \
  uv run alembic upgrade head
```

知识库公开入口统一位于 `/api/v1/knowledge-bases`：支持列表、创建、单文件上传和文档解析
状态列表。上传只接受 TXT、Markdown、PDF、DOCX，单文件最大 20 MiB；文件会在读取完成或
失败后关闭，RAGFlow 不可用、版本漂移、结果未知和上传输入错误均转换为稳定错误信封。
正式入口只读取 loopback `RAGFLOW_*` 配置，并在 FastAPI lifespan 中创建和释放 RAGFlow
客户端。Demo 适配器实现同一 `KnowledgeService` 契约，通过平台仓储端口读写 MySQL；关闭
适配器只释放实例，不删除已提交知识数据，重复名称、失效 ID 和上传失败仍映射为同一平台错误。

数字员工使用平台自有 `employees` 表保存通用会话角色配置：名称、说明、系统指令、可选的
RAGFlow 知识库 ID 和独立工作流 allowlist。表由 `20260719_0002` 迁移建立，字段长度、空白、
JSON 数组和 UTC 时间顺序同时受领域模型与 MySQL CHECK 约束；`DATETIME(6)` 保留更新时间精度。
知识库 ID 是外围服务的不透明引用，不对 RAGFlow 内库建外键，绑定有效性必须由应用层通过
正式 `KnowledgeService` 校验。

数字员工公开入口为 `/api/v1/employees`：集合支持 GET/POST，`/{employee_id}` 支持 GET/PUT。
创建和更新请求只接受上述通用会话配置，不接受业务字段；`allowed_workflow_ids` 最多 100 项且
不得重复。非空知识库 ID 会先经 `KnowledgeBaseService` 和 RAGFlow 官方数据集详情 API 校验，
每个工作流 ID 也必须经同一个 `WorkflowService` 确认存在，全部验证成功后才进入 Employee Unit
of Work 并提交 MySQL；失效引用或外围服务失败都会关闭失败且不写入。员工不存在时优先返回
`employee_not_found`，不发起无意义的外围校验。

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

工作流定义由 `20260720_0004` 迁移建立 `workflows`、`workflow_nodes` 和 `workflow_edges`。
节点画布坐标使用独立数值列，按节点类型判别的业务配置单独保存为 JSON 对象；节点和边保留
提交顺序，边的起点与终点通过 `(workflow_id, node_id)` 复合外键引用同一工作流节点。领域与
MySQL 同时约束名称、标识、节点类型、JSON 类型、序号、时间和引用完整性，定义、节点与边在
同一个 Workflow Unit of Work 中原子新增或整体替换。

工作流公开入口位于 `/api/v1/workflows`：集合支持 GET/POST，`/{workflow_id}` 支持 GET/PUT，
`/validate` 在不写入的前提下返回完整图问题列表。请求 Schema 使用 `type` 判别开始、AI 对话、
知识检索和结束四类节点，拒绝未知节点、错配配置与额外字段。创建和编辑在开启 MySQL 事务前先
完成图校验；知识检索节点还会经同一个正式 `KnowledgeBaseService` 验证 RAGFlow 数据集存在，
结构非法、引用失效或 RAGFlow 不可用均关闭失败且不写入。

`WorkflowCompiler` 直接消费已验证的 `WorkflowDefinition`，并使用锁定的 `langgraph==1.2.9`
公共 `StateGraph` API 编译执行图。平台节点 ID 会映射到独立内部命名空间，虚拟 `START/END`
只负责接入和退出；`start`、`ai_chat`、`knowledge_retrieval`、`end` 四类平台节点仍逐个真实执行。
节点由 `WorkflowNodeRegistry` 注入正式模型与知识服务，AI 节点复用平台知识安全指令，检索节点
复用统一首版检索参数。编译前再次执行平台图校验；LangGraph 编译失败、未注册节点、执行失败
和递归步数超限均映射为不泄漏第三方细节的稳定平台错误。当前编译器是内部生产组件，手动运行
层通过同一个 `WorkflowService` 调用，不在编译器内建立第二套传输协议。

工作流运行摘要由 `20260720_0005` 迁移建立 `workflow_runs` 表，并通过外键归属于正式工作流
定义。公开入口包括 `POST /api/v1/workflows/{workflow_id}/runs`、
`GET /api/v1/workflow-runs/{run_id}`、`POST /api/v1/workflow-runs/{run_id}/stop` 和
`GET /api/v1/workflow-runs/{run_id}/events` SSE。客户端生成的 `run_id` 是幂等边界；运行输入、
当前/已完成/失败节点、最终输出、稳定错误码和时间均由 MySQL 摘要保存。节点与终态事件严格在
对应摘要提交后发布，事件携带 `schema_version=1` 和完整已提交快照，可按 `after_sequence` 或
`Last-Event-ID` 续传当前进程内历史，无法续传时调用方重新读取摘要。

当前 MVP 的交互式工作流由 FastAPI 进程内异步任务托管：停止信号与当前 LangGraph 节点执行
竞速，停止胜出后取消节点并持久化 stopped；应用优雅关闭先请求活跃运行停止，启动时把遗留
`pending/running` 收敛为 `failed/workflow_run_interrupted`。现阶段没有需要跨进程可靠投递的
调用方，因此不预建消息队列或 Worker；一旦并发、重试或调度需求进入路线图，再让同一
`WorkflowService` 端口接入真实基础设施并按生产同路径重新验收。

`ModelSettings.from_env()` 默认读取版本化的 `.env.demo`，并允许同名 `BAILIAN_*` 环境变量覆盖。
用户明确要求现有 Demo Key 继续随私有仓库版本化，方便两台开发电脑直接使用；它是唯一获准的
凭据例外，不轮换、不作废，也不要求额外本机 Secret 文件。Key 使用 `SecretStr`，不得进入 repr、
JSON、日志、异常或前端响应。Base URL 只接受百炼官方 `compatible-mode/v1` HTTPS 地址，禁止
URL 凭据、查询参数和非官方主机。

`scripts/test-secrets.sh` 会对该唯一授权值计算不回显的指纹，并扫描当前源码、Git 全历史、
日志/Trace、后端 wheel/sdist 与前端生产产物；除 `backend/.env.demo` 及其历史外，任何复制都会
关闭失败。普通集成测试强制使用固定假 Key，只有显式真实百炼验收才读取版本化配置。

`BailianChatModelAdapter` 使用锁定的 `langchain-openai==1.3.5` 构造正式 `ChatOpenAI`，通过 `stream_text()` 暴露增量文本，并通过 `chat_model` 把同一个模型实例交给 Deep Agents 适配层。每个适配器显式创建独立同步/异步 HTTP 客户端，关闭当前实例不会关闭其他会话使用的客户端。总请求超时、流式逐块超时与重试次数分别由 `BAILIAN_TIMEOUT_SECONDS`、`BAILIAN_STREAM_CHUNK_TIMEOUT_SECONDS` 和 `BAILIAN_MAX_RETRIES` 控制，默认 `60/60/2`，最大 `300/300/3`；认证、请求拒绝、限流、超时、5xx、流中断和空输出都会转换成不含上游响应体或凭据的稳定平台错误。持有适配器的 lifespan 必须调用幂等 `aclose()` 释放自有模型客户端。

`EmployeeRuntime` 是一次会话回复的框架无关协议：`stream(request, stop=...)` 接收 Conversation/Employee/助手消息 ID、有序聊天历史、员工系统指令、显式知识库绑定与检索片段，以及允许调用的工作流 ID；它不包含旧任务模型的启动、审批、恢复或产物接口。运行时只返回单调递增的 `delta` 和一个 `completed/failed/stopped` 终态，终态后的事件由 `RuntimeEventEmitter` 拒绝。`RuntimeStopToken` 可重复请求但只在第一次改变状态；Deep Agents 适配器会让停止信号与上游下一事件竞速，停止胜出后关闭异步流。系统指令、历史正文、知识片段和模型增量均从对象 repr 排除。

`DeepAgentsEmployeeRuntime` 固定使用 `deepagents==0.6.12` 的公开 `create_deep_agent`。它通过异步工具解析器只装配员工本轮白名单中的平台工具，使用非 Sandbox 的 `StateBackend`，并通过公开 Harness Profile 和文件权限规则从模型工具面移除 Todo、本机文件、Shell、默认子代理和 `task`。生产 `WorkflowToolRegistry` 每轮从正式定义仓储解析 allowlist，为每个工作流生成绑定固定 ID 的独立工具；工具以 `employee` 触发来源调用同一个 `WorkflowService.start_run()`，通过 `wait_for_run()` 等待已持久化终态后才把安全结果交回模型，失败只返回平台错误码。调用被取消时会向同一运行服务发送停止意图，不复制或直接导入 LangGraph 图。知识片段被标记为不可信外部数据；Deep Agents 原始消息、工具和异常不会越过适配层。

`ConversationKnowledgeResolver` 把员工绑定与当前已完成用户消息转换为本轮知识上下文。未绑定员工直接返回无知识库语义且不访问 RAGFlow；已绑定员工每次都先经 `KnowledgeBaseService` 检查真实服务可用性和 `v0.25.6` 版本，再按固定首版参数检索。零命中保留知识库 ID；命中片段按原顺序映射成同源的 `RuntimeKnowledgeChunk` 与连续 `Citation`。配置、版本、知识库不存在、服务失败、非法响应和调用方取消均保持明确语义，不静默跳过检索。
