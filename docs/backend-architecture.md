# 通用 Agent 中台后端架构

> 状态：已确认的 MVP 基线  
> 确认日期：2026-07-19  
> 运行范围：本机 FastAPI + 按需平台基础设施 + 本机 RAGFlow，外部只调用阿里百炼

## 1. 建设目标

后端为浏览器提供统一的平台 API，第一版完成四项能力：

- 会话式 AI 对话；
- 数字员工创建、编辑和知识库绑定；
- RAGFlow 知识库创建、文档上传、解析状态和自动检索；
- 可视化工作流定义的校验、保存与 LangGraph 执行。

普通聊天以 `Conversation` 和 `Message` 为主模型。只有用户或数字员工明确触发工作流时才创建 `WorkflowRun`。

## 2. 核心技术决策

### 2.1 模块化后端与可演进运行单元

最小启动形态使用一个 FastAPI 进程；当当前用例需要长任务、并发隔离、可靠重试、恢复或其他工程能力时，可以加入合适的技术组件，不需要把技术选型视为新的产品功能。下图中的组件只是当前可预见示例，不构成白名单：

```text
React
  -> FastAPI
       -> Repository（平台独立 MySQL）
       -> Cache / Message Queue / Object Storage / Worker（按实际需要）
       -> RAGFlow（知识文档、解析和检索）
       -> Deep Agents + 阿里百炼（数字员工回复）
       -> LangGraph（独立工作流）
```

文件解析由 RAGFlow 自己的独立 Docker 栈处理。FastAPI 只发起官方 API 请求和轮询状态，不直连 RAGFlow 的 MySQL、Redis、检索引擎或对象存储。

### 2.2 阿里百炼单供应商

- 第一版只支持阿里百炼，不引入 LiteLLM 或供应商路由；
- 使用百炼 OpenAI 兼容接口和 `langchain-openai` 的 `ChatOpenAI`；
- `base_url`、模型名和 API Key 来自后端配置；
- 用户已批准测试 API Key 写入私有仓库的 `backend/.env.demo`，这是唯一凭据例外；
- API Key 永远不进入前端响应、日志、异常、OpenAPI 样例或测试快照；
- 模型适配器固定使用锁文件中的 `langchain-openai==1.3.5`，只接受百炼官方
  `compatible-mode/v1` HTTPS 地址；每个适配器显式创建独立同步/异步 HTTP 客户端，关闭一轮
  会话不得关闭其他适配器的共享默认客户端；
- `ChatOpenAI` 总请求超时和异步流逐块超时默认均为 60 秒、最大 300 秒；SDK 重试默认
  2 次、最大 3 次，429/5xx/连接失败最多只重放到该上限，已输出文本后的异常不重新生成；
- 平台模型端口只接受自有 `ModelRequest/ModelMessage`，并只返回自有增量与完成终态；百炼适配器
  负责把 system/user/assistant 消息双向转换为 LangChain 类型，LangChain/OpenAI 类型不得进入
  工作流、会话、领域或应用层；
- 平台只投影增量文本和唯一完成终态；认证/权限、请求拒绝、限流、超时、5xx、空输出和已开始流的中断
  转换成稳定安全错误，不透传供应商响应体、提示词或凭据。

### 2.3 Deep Agents 负责数字员工

- 固定使用官方 `deepagents==0.6.12` 和公开 `create_deep_agent` API；
- Deep Agents 适配器通过 `adapters/model/langchain.py` 的适配层内部桥取得配置好的
  `ChatOpenAI`，再传入系统指令和受控工具；该桥不是平台端口，不能被 application、domain、
  conversations、workflows 或 runtimes 消费；
- 第一版使用非 Sandbox 的 `StateBackend`；通过公开 Harness Profile 禁用默认通用子代理，
  从模型工具面排除 Todo、文件、Shell 和 `task` 全部内置工具，同时用 deny 规则拒绝所有
  文件读写，不能只依赖提示词声明安全边界；
- 工具注册表只按本轮 `allowed_workflow_ids` 解析已注册能力；未知 ID、重复工具名或与 Deep
  Agents 内置工具重名时 fail closed；
- 知识检索与工作流触发通过显式工具进入平台应用服务；
- 平台业务只依赖 `EmployeeRuntime`，Deep Agents 的消息、状态和事件在适配层转换；停止信号与
  上游下一事件竞速，停止或调用方取消时关闭上游异步流。

### 2.4 LangGraph 负责独立工作流

- 前端提交平台自定义的节点和边，不提交 Python 代码；
- 平台只定义编译、执行、节点输入/输出、观察、停止与结果协议，
  `WorkflowService` 不识别 LangGraph 类型；
- `adapters/workflow/langgraph/` 先调用平台业务校验，再把平台节点转换为
  `StateGraph` 节点并编译；
- 第一版只允许有向无环的线性/汇合图，不支持条件分支、循环和并行；
- 开始、AI 对话、知识检索、结束四类节点由后端注册表提供；
- 用户手动运行和数字员工工具调用都经过同一个 `WorkflowService`。

### 2.5 平台基础设施经端口接入

平台持久化保存：

- 数字员工和知识库绑定；
- 会话与消息；
- 工作流定义和运行摘要；
- Demo 模式的知识库、文档正文与解析终态；
- RAGFlow 知识库的稳定引用和展示缓存。

平台正式持久化使用独立 MySQL 8.4 LTS，通过 SQLAlchemy async、`aiomysql`、PyMySQL `>=1.1.1` 与 Alembic 接入，固定开发入口为 `127.0.0.1:19506/common_agent`。领域与应用层只依赖仓储端口；平台 MySQL 使用专属容器、端口、Volume 和资源限制，与 RAGFlow 内部 MySQL 完全隔离。SQLite 和其他数据库不能替代当前正式 MySQL 的完成验收。

任何外围技术依赖都按当前用例需要通过职责清晰的端口接入；`Cache`、`EventBus`、`ObjectStore`、`JobQueue` 以及 Redis、消息队列、对象存储和 Worker 只是示例。只要被正式调用链采用，就必须补齐适用于该技术的健康、失败、恢复、隔离、安全、资源和清理门禁。知识文档、切片、向量和解析产物仍由 RAGFlow 管理。

## 3. 分层与依赖方向

```text
api
 |
 v
application --------------+
 |                         |
 +-> domain                |
 +-> models -------------->+ adapters/bailian
 +-> runtimes ------------>+ adapters/deep_agents
 +-> knowledge ----------->+ adapters/ragflow
 +-> workflows ----------->+ adapters/workflow/langgraph
 +-> ports ---------------->+ adapters/mysql|redis|queue|object_store
```

### 3.1 API 层

只负责：

- HTTP、multipart 上传和 SSE 边界；
- Pydantic 请求/响应校验；
- 应用错误到稳定错误信封的转换；
- 请求 ID、超时和资源释放。

知识库上传入口只接收 TXT、Markdown、PDF、DOCX，单文件上限 20 MiB；API 分块读取到
上限后一字节并在所有终态关闭 `UploadFile`，应用服务统一校验扩展名、MIME、空文件和大小，
通过后才调用正式 RAGFlow 适配器。

禁止在路由中拼提示词、直接调用 RAGFlow SDK、编译 LangGraph 或写 SQL。

### 3.2 Application 层

提供明确用例：

- `EmployeeService`：数字员工 CRUD、知识库绑定和工作流 allowlist 引用校验；
- `KnowledgeBaseService`：RAGFlow 知识库与文档操作；
- `ConversationService`：创建会话、保存消息、自动检索、生成回复；
- `WorkflowService`：校验、保存和运行工作流；
- `SystemService`：报告后端、百炼和 RAGFlow 真实状态。

`EmployeeService` 通过 `EmployeeUnitOfWorkFactory` 管理平台 MySQL 事务。创建绑定先在事务外经
`KnowledgeBaseService` 调用 RAGFlow 官方数据集详情入口，验证成功后才提交员工；更新先确认
员工存在，再校验新绑定，最后在新事务内重新读取并原子更新，避免把外部网络等待放进数据库
事务，也避免无效知识库覆盖已有配置。

工作流 allowlist 同样在事务外经正式 `WorkflowService.get()` 逐项确认；重复、超量或不存在引用
在员工写入前关闭失败。会话每一轮再按已持久化 allowlist 动态解析独立工具，每个工具闭包固定唯一
工作流 ID，模型不能通过参数替换目标；工具只调用 `WorkflowService.start_run()` / `wait_for_run()`，
触发来源固定为 `employee`，取消时通过同一服务停止，不直接编译或执行工作流图。

启动 Seed 复用同一个 `EmployeeService.ensure` 与 Unit of Work，不另写 SQL 或旁路仓储。固定
平台 UUID 只在记录不存在时创建默认知识助理；已存在即原样返回，因此用户编辑和后续知识库
绑定不会被重启覆盖。并发启动在事务内二次读取，并由 MySQL 主键唯一约束与冲突后重读保证
最终只有一条记录。

### 3.3 Domain 层

只定义平台模型和协议，不导入第三方框架。

平台模型协议由不可变 `ModelMessage(role, content)`、非空 `ModelRequest(messages)`、
`ModelStreamDelta(text)`、唯一 `ModelStreamCompleted`、稳定 `ModelServiceError` 家族及幂等
`aclose()` 组成。工作流节点必须看到完成终态后才接受输出：缺少终态、空输出、重复终态或终态
之后继续输出都关闭失败；已出现增量后缺终态映射为可重试流中断。供应商消息、Chunk、响应、
异常和客户端释放都由外围适配器转换，平台协议不暴露 LangChain、OpenAI 或 Deep Agents 类型。

平台图执行协议由 `WorkflowCompiler/CompiledWorkflow`、不可变节点上下文与结果、
`WorkflowExecutionObserver`、可幂等请求的 `WorkflowExecutionStopToken` 和严格
`WorkflowExecutionResult` 组成。结果要求已完成节点唯一且与步数完全一致；
LangGraph 的 `StateGraph`、Runtime context、TypedDict 状态、节点包装、递归上限异常与
编译结果都只存在于外围适配器。

### 3.4 自动依赖边界

`backend/tests/architecture/test_dependency_boundaries.py` 通过 AST 扫描每个生产 Python 文件。
Python 标准库和 `common_agent` 之外的所有 import 都视为第三方，必须先在门禁中
登记职责边界；未登记的新 SDK 默认失败，不得因当前尚未使用而绕过规则。

| 第三方能力 | 唯一允许位置 |
| --- | --- |
| FastAPI、Starlette、Uvicorn、multipart | `api/` |
| SQLAlchemy、Alembic、MySQL 驱动 | `adapters/persistence/` |
| HTTP 客户端、模型/代理/图/缓存/对象存储与供应商 SDK | `adapters/` |
| Pydantic | `api/`、`bootstrap/` 或 `adapters/knowledge/` |
| python-dotenv | `bootstrap/` |
| cryptography | `adapters/` |

内部依赖同时关闭失败：只有适配器自身和 `api/app.py` 组合根能导入
`common_agent.adapters`；只有 API、契约导出和根启动入口能导入 `common_agent.api`；
`domain/` 只能依赖自身与标准库。`__main__.py` 不再直接导入 Uvicorn，只调用
`api/server.py` 的 HTTP 边界函数。该架构测试由默认 pytest/覆盖率入口自动执行，
本机是当前权威结果，GitHub CI 只是同一命令的可选镜像。

## 4. 核心模型

### 4.1 数字员工

```text
Employee
├── id: UUID
├── name: string
├── description: string
├── system_prompt: string
├── knowledge_base_id: string | null
├── allowed_workflow_ids: list[UUID]
├── created_at
└── updated_at
```

第一版一个员工最多绑定一个 RAGFlow 知识库。员工未绑定知识库时不执行检索。

`Employee` 是与具体业务无关的会话角色配置：只保存名称、说明、系统指令和平台能力引用，
不保存行业字段、业务任务状态或 automation-tool 的业务模型。`allowed_workflow_ids` 只是对独立
工作流公开能力的调用白名单，不内嵌工作流图；在 Wave 5 接入工作流前保持空列表。

### 4.2 会话与消息

```text
Conversation
├── id: UUID
├── employee_id: UUID
├── title: string
├── created_at
└── updated_at

Message
├── id: UUID
├── conversation_id: UUID
├── sequence_number: integer
├── role: user | assistant
├── content: string
├── status: pending | streaming | completed | failed | stopped
├── citations: list[Citation]
├── error_code: string | null
├── created_at
└── updated_at

Citation
├── position: integer
├── knowledge_base_id: string
├── chunk_id: string
├── document_id: string
├── document_name: string
├── content: string
└── score: float
```

用户消息必须先以 `completed` 持久化。助手占位消息从 `pending` 开始，收到首个增量后进入
`streaming`，只能进入 `completed`、`failed` 或 `stopped` 终态；终态后的晚到增量不得改写
权威快照。`sequence_number` 在同一会话内唯一并作为历史顺序，不能用时间或 UUID 猜测顺序。
引用只属于已完成的助手消息，按从 1 连续递增的 `position` 保存；失败和停止也要保留，便于
用户重试和刷新恢复。

平台 MySQL 使用 `conversations`、`messages`、`message_citations` 三张表。会话通过正式外键
引用平台员工，消息和引用使用级联子记录；角色/状态组合、错误码、长度、时间顺序、会话内
消息序号及引用分数同时由领域模型和数据库约束。Repository 只更新标题或消息运行态等可变
字段，不允许借更新操作迁移员工、会话归属、序号、角色或创建时间。

### 4.3 EmployeeRuntime 会话协议

`EmployeeRuntime` 每次 `stream(request, stop=...)` 只生成同一会话中的一条助手回复，不创建
任务实体，也不暴露旧任务模型的启动、审批、恢复或产物方法。请求显式携带 Conversation、
Employee、助手占位消息 ID/序号、员工系统指令、按持久化序号排列的模型可见历史、知识库
绑定/检索片段和允许调用的工作流 ID；系统指令、历史正文与知识原文彼此分离，适配器不能靠
拼接无类型字典猜测来源。

历史最多 100 条且总计 400,000 字符；知识上下文最多 20 段且总计 120,000 字符。未绑定知识
库时上下文必须为空；已绑定但检索零命中仍保留 `knowledge_base_id` 并允许空上下文，不能把这
两种情况混为一谈。所有片段必须来自当前绑定知识库且引用唯一；允许的工作流 UUID 也必须
唯一并有数量上限。系统指令、历史正文、知识原文和模型增量从运行时对象 repr 排除。

运行时事件只包含 `delta/completed/failed/stopped`：序号在单次回复内从 1 单调递增，文本只
存在于 delta，错误码只存在于 failed，并且只能产生一个终态。`RuntimeStopToken` 表示幂等的
协作式停止意图；Deep Agents 适配器必须同时等待上游下一事件与停止信号，停止胜出时关闭上游
迭代并产生 stopped，不能把用户停止伪装成失败，也不能在终态后接受晚到内容。A4-06 再把
这些内部事件映射为持久化后才能推送的平台 SSE 事件，二者的 sequence 不互相冒充。

### 4.4 知识库引用

```text
KnowledgeBaseRef
├── id: RAGFlow dataset id
├── name
├── description
├── document_count
├── parsing_count
└── synced_at
```

real 模式下 RAGFlow 是知识库状态的权威来源。数字员工表只保存不透明的 `knowledge_base_id`，不直连
RAGFlow 内部 MySQL，也不跨服务建立数据库外键。创建或修改绑定时，`EmployeeService` 必须
通过正式 `KnowledgeService` 查询当前数据集并确认 ID 存在；RAGFlow 不可用或引用失效时
关闭失败并拒绝写入。已绑定的数据集后来被删除时，员工定义保留原引用，由读取/会话链路
返回稳定的“知识库不存在或已失效”错误，不能静默改成无知识库回答。展示缓存只有出现真实
性能需要时才引入，缓存不得取代 RAGFlow 的权威状态。

Demo 模式实现相同 `KnowledgeService` 协议，但不调用或伪装 RAGFlow。项目专属 MySQL 的
`demo_knowledge_bases` 与 `demo_knowledge_documents` 保存知识库、文档正文、完成/失败状态和
稳定顺序；外键只约束 Demo 文档归属，不把员工表绑定成 Demo 专用结构。后端重启后，员工绑定、
已有消息引用和重新检索必须指向同一知识库与文档；应用关闭不得清空已提交数据。Demo 数据仍由
明确测试/用户删除生命周期管理，不能依赖进程退出制造“已清理”。

### 4.5 工作流

```text
WorkflowDefinition
├── id: UUID
├── name
├── description
├── nodes: list[WorkflowNode]
├── edges: list[WorkflowEdge]
├── created_at
└── updated_at

WorkflowNode
├── id
├── type: start | ai_chat | knowledge_retrieval | end
├── position: {x, y}
└── config: 按节点类型判别的配置

WorkflowRun
├── id: UUID
├── workflow_id: UUID
├── trigger: manual | employee
├── status: pending | running | completed | failed | stopped
├── input
├── output
├── current_node_id
├── completed_node_ids
├── failed_node_id
├── error_code
└── timestamps
```

前端位置只用于设计器显示，不影响执行顺序；执行顺序只由通过校验的边决定。
`workflow_runs` 是平台 MySQL 中的权威运行摘要，客户端生成的 `run_id` 是手动运行幂等边界；
节点开始、完成以及运行终态每次都先提交摘要，再发布进程内 SSE 事件。首版交互式运行由当前
FastAPI 进程托管，不为尚不存在的并发或可靠投递需求预建队列与 Worker；应用关闭时协作停止
活跃运行，启动时把遗留 `pending/running` 收敛为 `failed/workflow_run_interrupted`。

## 5. AI 会话链路

```text
用户发送消息
  -> 校验会话和数字员工
  -> 持久化用户消息与助手占位消息
  -> ConversationKnowledgeResolver 检查员工知识库绑定
  -> 已绑定时经 KnowledgeBaseService 校验 RAGFlow 可用性/版本
  -> KnowledgeService.retrieve(question)
  -> 把历史消息、系统指令、知识片段和引用交给 EmployeeRuntime
  -> Deep Agents 调用阿里百炼
  -> 如模型调用授权工作流工具，经同一个 WorkflowService 运行并等待持久化终态
  -> 每个 Runtime delta/终态先写回助手消息和引用并提交 MySQL
  -> 再转换并发布 assistant.delta / assistant.completed 等平台 SSE 事件
```

检索为空不是错误：数字员工应明确说明未找到相关知识，并基于通用能力回答或说明无法确定。RAGFlow 请求失败则本轮回复失败，不静默跳过知识库后假装是知识回答。

`ConversationKnowledgeResolver` 只接受已完成用户消息。员工未绑定知识库时不访问 RAGFlow，
并返回 `knowledge_base_id=None`；员工已绑定时，每条消息都先通过 `KnowledgeBaseService`
检查真实可用性与锁定版本，再用固定首版参数 `top_k=5`、`similarity_threshold=0.2` 检索。
零命中保留非空绑定 ID 和空片段，以区别于未绑定。命中结果按供应商顺序一次性映射为
`RuntimeKnowledgeChunk` 与从 1 连续编号的 `Citation`；两者使用同一知识库、片段、文档、正文
和分数。重复片段、超量片段、非法分数/正文或无法识别的返回均关闭失败，任何 RAGFlow 错误
不得静默降级为普通模型回答。

## 6. 工作流校验与执行

保存前校验：

- 节点和边 ID 唯一；
- 恰好一个开始节点、至少一个结束节点；
- 开始节点无入边，结束节点无出边；
- 每条边的两端存在，禁止自环和重复边；
- 所有节点从开始可达且能到达某个结束节点；
- 第一版禁止环；
- AI 节点提示词非空；
- 知识检索节点引用的知识库存在；
- 节点数、边数、输入长度和运行步数有上限。

执行时平台节点注册表只接收 `WorkflowNodeExecutionContext` 并返回
`WorkflowNodeExecutionResult`；LangGraph 适配器负责构建 `StateGraph`、投影图状态、调用
节点、累计已完成顺序和步数，并将第三方递归/编译/执行异常转为稳定平台错误。
LangGraph 自己的编译检查是第二道门禁，不能替代平台校验。`WorkflowService` 从正式仓储
读取已校验定义，只持有平台编译器端口、停止令牌和节点观察器，逐步提交
`current_node_id/completed_node_ids`；执行结果的节点顺序或步数与已提交摘要不一致时关闭
失败，不接受不确定结果。知识库失效、模型失败与未知执行异常只保存稳定错误码，
不保存第三方响应或知识正文。

## 7. API 基线

```text
GET    /api/v1/system/status

GET    /api/v1/employees
POST   /api/v1/employees
GET    /api/v1/employees/{employee_id}
PUT    /api/v1/employees/{employee_id}

GET    /api/v1/knowledge-bases
POST   /api/v1/knowledge-bases
GET    /api/v1/knowledge-bases/{dataset_id}/documents
POST   /api/v1/knowledge-bases/{dataset_id}/documents

GET    /api/v1/conversations
POST   /api/v1/conversations
GET    /api/v1/conversations/{conversation_id}/messages
POST   /api/v1/conversations/{conversation_id}/messages
GET    /api/v1/conversations/{conversation_id}/events
POST   /api/v1/conversations/{conversation_id}/stop
POST   /api/v1/messages/{message_id}/retry

GET    /api/v1/workflows
POST   /api/v1/workflows
GET    /api/v1/workflows/{workflow_id}
PUT    /api/v1/workflows/{workflow_id}
POST   /api/v1/workflows/validate
POST   /api/v1/workflows/{workflow_id}/runs
GET    /api/v1/workflow-runs/{run_id}
POST   /api/v1/workflow-runs/{run_id}/stop
GET    /api/v1/workflow-runs/{run_id}/events
```

删除接口、批量操作、分页高级筛选和权限不进入第一版。

## 8. 会话与工作流事件

会话和工作流流式事件统一使用 SSE。当前会话事件为：

```text
assistant.started
assistant.delta
assistant.completed
assistant.failed
assistant.stopped

workflow.run.started
workflow.node.started
workflow.node.completed
workflow.node.failed
workflow.run.completed
workflow.run.failed
workflow.run.stopped
```

每个会话事件包含固定 `schema_version=1`、`conversation_id`、`message_id`、`turn_id`、会话内
单调 `sequence`、时间和已持久化的消息快照；delta 事件额外包含本次文本增量，重试开始事件
带 `retry=true`。SSE 的 `id` 与 payload sequence 一致，支持 `after_sequence` 和
`Last-Event-ID` 回放进程内保留历史。无法续传时前端必须重新读取 MySQL 权威消息历史，不能猜测
丢失内容。前端只消费平台事件，不解析 LangGraph 或 Deep Agents 原始事件。

每个工作流事件包含固定 `schema_version=1`、`run_id`、`workflow_id`、运行内单调
`sequence`、可选 `node_id`、时间和已提交的完整 `WorkflowRun` 快照。工作流 SSE 同样支持
`after_sequence` 与 `Last-Event-ID` 回放当前进程保留历史；历史丢失或应用重启后，客户端以
`GET /api/v1/workflow-runs/{run_id}` 的 MySQL 摘要为权威，不从缺失事件推测终态。

发送接口先在一个 Conversation Unit of Work 中提交用户消息、助手占位和会话更新时间，再
发布 started 并启动后台生成；后续每个事件也严格“提交后发布”。客户端生成的用户
`message_id` 是重复提交边界，同一会话有活跃助手消息时拒绝第二次发送。停止只发出停止意图，
最终 stopped 仍由正式运行时收敛并持久化；重试只允许最后一条 failed/stopped 助手消息，复用
原消息 ID/序号并清空不完整内容。应用重启时把遗留 pending/streaming 恢复为
`failed/generation_interrupted`。

手动运行接口先用客户端 `run_id` 提交 `pending`，再提交 `running`、发布 started 并启动后台
LangGraph；重复 ID 返回冲突且绝不重复执行。节点 started/completed 和最终
completed/failed/stopped 都严格提交后发布。停止接口只接受活跃运行并设置协作式停止意图，
当前节点与停止信号竞速，停止胜出后取消节点任务并由运行服务持久化 stopped；应用重启不伪造
已丢失事件，而是把中断摘要收敛为稳定失败。

## 9. 错误语义

稳定错误至少包括：

- `configuration_missing`：必要本地配置缺失；
- `model_unavailable`：百炼超时、限流或服务错误；
- `knowledge_service_unavailable`：RAGFlow 不可达；
- `knowledge_base_not_found`：绑定或节点引用失效；
- `document_upload_failed`：文件上传失败；
- `workflow_invalid`：节点图不合法；
- `workflow_run_conflict`：客户端运行 ID 已经提交；
- `workflow_run_not_active`：运行已终止或不在当前进程中，不能停止；
- `workflow_run_interrupted`：应用重启时恢复到的中断运行；
- 节点执行失败：摘要保存模型、知识库或工作流层稳定错误码；
- `conversation_busy`：同一会话已有回复在生成；
- `resource_not_found`：资源不存在；
- `validation_error`：请求字段错误；
- `internal_error`：未知错误的脱敏兜底。

错误信封固定包含 `code`、`message`、`request_id`、`retryable`，不回显第三方响应体、提示词、知识原文、API Key 或本机路径。

## 10. 本地配置与端口

默认端口只作为项目建议，启动前必须检查冲突并允许通过单一配置覆盖：

| 服务 | 建议值 |
| --- | --- |
| FastAPI | `127.0.0.1:18200` |
| React Vite | `127.0.0.1:18280` |
| 平台 MySQL | `127.0.0.1:19506` |
| RAGFlow REST API | `127.0.0.1:19380` |
| RAGFlow Web | `127.0.0.1:19381` |
| Playwright 测试 | 操作系统随机空闲端口 |

稳定开发栈使用 `common-agent-dev` 命名空间，其中 RAGFlow 相关服务使用 `common-agent-ragflow-*` 前缀，平台自有数据库、缓存、队列、对象存储和 Worker 使用 `common-agent-platform-*` 前缀。平台 MySQL 数据、上传临时文件、服务 Volume 映射和日志统一放在根目录 `.local/`；平台 MySQL 与 RAGFlow 使用不同的 Compose project、容器、网络和 Volume。

RAGFlow 固定为官方 `v0.25.6` 及其 tag 提交
`8f0632c8d9efacbcd11aaf6e0f4cb634169bfea4`，以 `third_party/ragflow` 官方 Git submodule
保存确切源码引用，并通过 `infra/ragflow/manage.sh` 运行未修改的官方 Compose。知识库新建、既有索引
重建和检索分别显式固定阿里百炼 `text-embedding-v4@Tongyi-Qianwen` 与
`qwen3-rerank@Tongyi-Qianwen`，不启动或兜底到本地 embedding/rerank。稳定栈使用独立
`common-agent-dev` Colima profile（8 CPU、32GiB 内存、100GiB 容器磁盘）和
`colima-common-agent-dev` Docker context；32GiB 的长期峰值与 soak 结论仍由 R8-04 单独验收，
不得裁剪 RAGFlow 必需服务、降低中文质量或占用其他项目的默认 context。

## 11. 官方能力依据

- Deep Agents 官方 `create_deep_agent` 支持传入模型实例、工具和系统提示词；
- 阿里百炼官方提供 OpenAI 兼容 Chat Completions 和 `ChatOpenAI` 接入；
- LangGraph `StateGraph` 以状态、节点和边描述并编译图；
- RAGFlow 官方 HTTP/Python API 提供数据集、文档和检索能力。

具体依赖版本在对应路线图任务中锁定，禁止使用漂移版本。
