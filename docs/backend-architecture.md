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
- 模型适配器提供超时、有限重试和错误转换，不无限重放。

### 2.3 Deep Agents 负责数字员工

- 使用官方 `create_deep_agent` 公共 API；
- 向 Deep Agents 传入配置好的 `ChatOpenAI` 模型实例、系统指令和受控工具；
- 第一版使用无本机 Shell 能力的状态后端，不给数字员工任意文件系统或命令执行权限；
- 知识检索与工作流触发通过显式工具进入平台应用服务；
- 平台业务只依赖 `EmployeeRuntime`，Deep Agents 的消息、状态和事件在适配层转换。

### 2.4 LangGraph 负责独立工作流

- 前端提交平台自定义的节点和边，不提交 Python 代码；
- 后端先做业务校验，再把节点转换为 `StateGraph` 节点并编译；
- 第一版只允许有向无环的线性/汇合图，不支持条件分支、循环和并行；
- 开始、AI 对话、知识检索、结束四类节点由后端注册表提供；
- 用户手动运行和数字员工工具调用都经过同一个 `WorkflowService`。

### 2.5 平台基础设施经端口接入

平台持久化保存：

- 数字员工和知识库绑定；
- 会话与消息；
- 工作流定义和运行摘要；
- RAGFlow 知识库的稳定引用和展示缓存。

平台正式持久化使用独立 MySQL 8.4 LTS，通过 SQLAlchemy async、`asyncmy` 与 Alembic 接入，固定开发入口为 `127.0.0.1:19506/common_agent`。领域与应用层只依赖仓储端口；平台 MySQL 使用专属容器、端口、Volume 和资源限制，与 RAGFlow 内部 MySQL 完全隔离。SQLite 和其他数据库不能替代当前正式 MySQL 的完成验收。

任何外围技术依赖都按当前用例需要通过职责清晰的端口接入；`Cache`、`EventBus`、`ObjectStore`、`JobQueue` 以及 Redis、消息队列、对象存储和 Worker 只是示例。只要被正式调用链采用，就必须补齐适用于该技术的健康、失败、恢复、隔离、安全、资源和清理门禁。知识文档、切片、向量和解析产物仍由 RAGFlow 管理。

## 3. 分层与依赖方向

```text
api
 |
 v
application --------------+
 |                         |
 +-> domain                |
 +-> runtimes ------------>+ adapters/deep_agents
 +-> knowledge ----------->+ adapters/ragflow
 +-> workflows ----------->+ langgraph
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

- `EmployeeService`：数字员工 CRUD 和知识库绑定；
- `KnowledgeBaseService`：RAGFlow 知识库与文档操作；
- `ConversationService`：创建会话、保存消息、自动检索、生成回复；
- `WorkflowService`：校验、保存和运行工作流；
- `SystemService`：报告后端、百炼和 RAGFlow 真实状态。

### 3.3 Domain 层

只定义平台模型和协议，不导入第三方框架。

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
├── role: user | assistant
├── content: string
├── status: pending | streaming | completed | failed | stopped
├── citations: list[Citation]
├── error_code: string | null
└── created_at
```

用户消息必须先持久化。助手占位消息随后创建并通过事件更新，终态再写回平台 MySQL。失败和停止也要保留，便于用户重试。

### 4.3 知识库引用

```text
KnowledgeBaseRef
├── id: RAGFlow dataset id
├── name
├── description
├── document_count
├── parsing_count
└── synced_at
```

RAGFlow 是知识库状态的权威来源，平台 MySQL 只缓存展示字段和绑定 ID。

### 4.4 工作流

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
├── current_node_id
├── input
├── output
└── timestamps
```

前端位置只用于设计器显示，不影响执行顺序；执行顺序只由通过校验的边决定。

## 5. AI 会话链路

```text
用户发送消息
  -> 校验会话和数字员工
  -> 持久化用户消息与助手占位消息
  -> 如果员工绑定知识库：KnowledgeService.retrieve(question)
  -> 把历史消息、系统指令、知识片段和引用交给 EmployeeRuntime
  -> Deep Agents 调用阿里百炼
  -> 转换为 message.delta / message.completed 等会话事件
  -> 写回助手消息和引用
```

检索为空不是错误：数字员工应明确说明未找到相关知识，并基于通用能力回答或说明无法确定。RAGFlow 请求失败则本轮回复失败，不静默跳过知识库后假装是知识回答。

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

执行时后端用节点注册表创建函数，构建并编译 `StateGraph`。LangGraph 自己的编译检查是第二道门禁，不能替代平台校验。

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
GET    /api/v1/workflow-runs/{run_id}/events
```

删除接口、批量操作、分页高级筛选和权限不进入第一版。

## 8. 会话与工作流事件

事件统一使用 SSE，至少包含：

```text
conversation.message.accepted
conversation.retrieval.started
conversation.retrieval.completed
conversation.message.delta
conversation.message.completed
conversation.message.failed
conversation.message.stopped

workflow.run.started
workflow.node.started
workflow.node.completed
workflow.node.failed
workflow.run.completed
workflow.run.failed
```

每个事件包含 `version`、资源 ID、单调 `sequence`、时间和安全 payload。前端只消费平台事件，不解析 LangGraph 或 Deep Agents 原始事件。

## 9. 错误语义

稳定错误至少包括：

- `configuration_missing`：必要本地配置缺失；
- `model_unavailable`：百炼超时、限流或服务错误；
- `knowledge_service_unavailable`：RAGFlow 不可达；
- `knowledge_base_not_found`：绑定或节点引用失效；
- `document_upload_failed`：文件上传失败；
- `workflow_invalid`：节点图不合法；
- `workflow_run_failed`：节点执行失败；
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

RAGFlow 固定为官方 `v0.25.6` 及其 tag 提交 `8f0632c8d9efacbcd11aaf6e0f4cb634169bfea4`，通过仓库 `infra/ragflow/manage.sh` 运行未修改的官方 Compose。默认启用多语言 `BAAI/bge-m3` embedding；稳定栈固定使用独立 `common-agent-dev` Colima profile（12 CPU、48GiB 内存、100GiB 容器磁盘）和 `colima-common-agent-dev` Docker context，不静默降级模型、裁剪必需服务或占用其他项目的默认 context。

## 11. 官方能力依据

- Deep Agents 官方 `create_deep_agent` 支持传入模型实例、工具和系统提示词；
- 阿里百炼官方提供 OpenAI 兼容 Chat Completions 和 `ChatOpenAI` 接入；
- LangGraph `StateGraph` 以状态、节点和边描述并编译图；
- RAGFlow 官方 HTTP/Python API 提供数据集、文档和检索能力。

具体依赖版本在对应路线图任务中锁定，禁止使用漂移版本。
