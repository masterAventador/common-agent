# 通用 Agent 中台工程结构

> 状态：V1 结构已落地，V2 工具/MCP 与私有 RAGFlow 目标结构已确认
> 确认日期：2026-07-22

## 1. 核心决策

项目采用单一 Git 仓库，前端和后端分别位于 `frontend/` 与 `backend/`。初始形态用独立前后端进程快速闭环；任何数据库、中间件、存储、运行时、协议、调度、观测和工程工具都可以按当前功能与工程需要加入，技术方案不因首版业务范围被禁止，也不限于文档已经列举的组件。

```text
common-agent/
├── frontend/                   # React 聊天工作台
├── backend/                    # FastAPI 与 Agent 编排
├── contracts/                  # OpenAPI、会话/工作流事件和公共样例
├── infra/                      # RAGFlow 等外部依赖的本地接入说明
├── third_party/                # 项目实际消费源码的锁定 Git submodule
├── scripts/                    # 跨前后端生成与验证脚本
├── docs/                       # 产品、架构、冻结 V1 和当前 V2 路线图
├── AGENTS.md
├── CLAUDE.md
├── README.md
├── .editorconfig
├── .gitignore
└── .env.example
```

根目录只保存跨工程内容，不放 React 或 Python 业务实现。

## 2. 后端结构

```text
backend/
├── src/
│   └── common_agent/
│       ├── bootstrap/           # 配置和依赖装配
│       ├── api/                 # FastAPI 路由、依赖和错误边界
│       │   ├── routers/
│       │   │   ├── auth.py                 # 引导、登录、恢复和注销
│       │   │   ├── audit.py                # Owner 审计查询、策略和完整性
│       │   │   ├── tenants.py              # 工作区列表、创建与成员配置
│       │   │   ├── system.py
│       │   │   ├── conversations.py       # 会话 REST 编排
│       │   │   ├── conversation_events.py # 会话 SSE 边界
│       │   │   ├── services.py            # 路由依赖解析
│       │   │   ├── employees.py
│       │   │   ├── knowledge.py
│       │   │   ├── resource_deletion.py  # 删除依赖与稳定错误映射
│       │   │   ├── workflows.py
│       │   │   └── workflow_runs.py
│       │   ├── schemas/           # 会话、工作流和运行 HTTP DTO
│       │   ├── authentication.py  # Cookie、CSRF、Origin 与路由认证依赖
│       │   ├── audit.py           # HTTP 审计分类、资源标记与关闭失败边界
│       │   ├── tenancy.py         # 租户选择、权限判断与请求上下文
│       │   ├── app.py            # FastAPI 组合根
│       │   ├── observability.py  # HTTP 关联、请求日志和进程内指标边界
│       │   └── server.py         # Uvicorn 进程边界
│       ├── application/         # 平台工作流用例编排
│       │   ├── resource_deletion.py      # 四类资源引用安全删除
│       │   ├── resource_locks.py         # 跨资源变更进程内串行区
│       │   ├── workflow_service.py        # 稳定薄门面
│       │   ├── workflow_catalog.py        # 定义校验/持久化
│       │   ├── workflow_runs.py           # 运行协调
│       │   └── workflow_run_projection.py # 运行投影
│       ├── concurrency.py       # 可回收的按 ID 异步锁池
│       ├── auth/                # 平台身份、会话模型、端口与认证用例
│       ├── audit/               # 固定审计模型、哈希链、策略、端口与服务
│       ├── tenancy/             # 组织/租户访问模型、角色、端口与上下文
│       ├── conversations/       # 会话门面、持久化、运行协调、消息投影与事件
│       ├── events/              # 平台持久事件模型与 Journal 端口
│       ├── tasks/               # 持久任务模型、队列端口、租约 Worker 与并发池
│       ├── employees/           # 数字员工应用服务与启动 Seed
│       ├── model_configurations/ # 租户模型配置应用服务与引用安全删除
│       ├── tools/              # MCP 来源、能力、工具集、精确授权与调用协议
│       ├── domain/              # 与第三方无关的会话和能力模型
│       │   ├── conversation.py
│       │   ├── employee.py
│       │   ├── knowledge.py
│       │   ├── model_configuration.py
│       │   ├── workflow.py
│       │   └── workflow_run.py
│       ├── models/              # 平台自有消息、模型流、错误和释放协议
│       │   ├── base.py
│       │   └── prompts.py
│       ├── observability/       # 平台 JSON 日志、关联上下文和有界指标
│       ├── runtimes/            # EmployeeRuntime 协议
│       │   └── base.py
│       ├── workflows/           # 平台工作流协议、校验、节点与事件
│       │   ├── validator.py
│       │   ├── execution.py
│       │   ├── events.py
│       │   └── nodes/
│       ├── knowledge/           # KnowledgeService 协议
│       │   ├── base.py
│       │   ├── service.py
│       │   └── retrieval.py
│       ├── ports/               # 仓储、资源删除、缓存、事件、对象存储与任务端口
│       ├── worker_app.py        # 独立 Worker 组合根
│       ├── worker_main.py       # Worker 信号与进程入口
│       └── adapters/            # 数据库、模型及第三方外围适配
│           ├── auth/            # Argon2id 密码适配器
│           ├── backup/          # 流式 AES-256-GCM 归档、清单校验与安全解包
│           ├── agent/           # Deep Agents 正式适配器
│           ├── knowledge/       # RAGFlow 正式适配器
│           ├── model/           # 阿里百炼转换与仅适配层可见的 LangChain 桥
│           ├── mcp/             # MCP SDK、托管 HTTP 转换、外部连接与工具包装
│           ├── workflow/        # LangGraph 编译、状态与节点框架转换
│           └── persistence/     # MySQL 适配器，含业务事务、任务队列与事件日志
├── migrations/                  # 当前正式数据库迁移
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── architecture/           # 生产 import/AST 依赖边界门禁
│   ├── contract/
│   ├── soak/                    # 事件、锁与长时间运行资源回落验证
│   └── fixtures/
├── pyproject.toml
├── uv.lock
├── .env.demo                    # 私有仓库唯一获准版本化的现有百炼 Demo 配置
├── .env.example
└── README.md
```

### 后端依赖方向

```text
api -> application -> domain
          |             ^
          +-> workflows |
          +-> runtimes -+
          +-> knowledge-+
```

- `api/` 只负责 HTTP/SSE、参数校验、错误转换和 HTTP 可观测边界；
- `auth/` 定义用户、服务端会话、恢复码及仓储/密码端口；Cookie、Origin 和 CSRF 只在 API
  边界处理，Argon2id 与 SQLAlchemy 分别留在对应适配层；
- `tenancy/` 定义 Owner/Editor/Viewer、工作区访问解析和 fail-closed 上下文；平台资源仓储、
  事件与锁以租户命名空间运行，RAGFlow 外部 ID 归属保存在平台 MySQL，不触碰上游内部表；
- `observability/` 只用标准库定义 JSON 日志、W3C trace context 与进程内有界指标；业务服务
  绑定平台会话/工作流 ID，外围 HTTP 适配器负责把 trace context 传给 RAGFlow 与百炼；
- `tasks/` 与 `events/` 只定义平台模型、端口和执行协议；API 组合根只提交/读取，独立
  `worker_app.py` 才装配会话回复与工作流执行处理器，二者共享 MySQL 适配器但不互相导入；
- `application/` 分别负责“发送消息并生成回复”和“触发工作流”用例；
- 会话和工作流公开 Service 只作稳定用例门面；事务持久化、运行协调和权威投影位于独立模块，
  实现模块不得反向导入门面或形成循环依赖；
- `domain/` 不导入 FastAPI、Deep Agents、LangGraph 或 RAGFlow；
- `models/` 定义平台自有 system/user/assistant 消息、请求、增量、完成终态、安全错误和释放协议，
  不导入 LangChain、OpenAI、Deep Agents 或供应商 SDK；
- `workflows/` 只定义平台节点/边、校验、编译/执行/观察/停止/结果端口和节点函数；
  `adapters/workflow/langgraph/` 独占 StateGraph、Runtime context、图状态、节点包装和
  LangGraph 异常转换；数字员工只通过 `WorkflowService` 调用工作流；
- 第三方 SDK 类型不得越过适配层；百炼负责平台消息与 LangChain 消息转换，Deep Agents 负责
  平台运行请求/事件与 LangChain/Deep Agents 类型转换，二者共享的 `BaseChatModel` 只能经
  `adapters/model/langchain.py` 的适配层内部桥传递；
- `tests/architecture/` 对生产树执行关闭失败的 AST 扫描；所有非标准库依赖
  必须登记允许目录，未登记新 SDK 直接失败。FastAPI/Starlette/Uvicorn 只在
  `api/`，SQLAlchemy/Alembic/数据库驱动只在 `adapters/persistence/`，HTTP/模型/
  代理/图/供应商 SDK 只在 `adapters/`；
- 员工、会话、消息、工作流和知识库绑定必须经过仓储端口；正式实现使用平台独立 MySQL、SQLAlchemy async 和 Alembic，不改变领域模型依赖方向；
- 任何第三方技术依赖都通过与其职责相符的应用端口和外围适配器接入；当前任务/事件用平台
  MySQL 适配器实现，不把 RAGFlow 内部 Valkey 冒充平台队列，也不引入没有调用方的 Redis/MQ；
- RAGFlow 保存知识文档和索引，平台不直连其内部数据库、缓存、检索引擎或对象存储。

## 3. 前端结构

```text
frontend/
├── src/
│   ├── app/                     # Provider、布局和入口
│   ├── features/
│   │   ├── auth/                # 首位所有者、登录、恢复与认证门禁
│   │   ├── audit/               # Owner 审计查询、策略与完整性页面
│   │   ├── chat/                # 页面编排、Query/SSE 控制器、消息投影与三栏展示
│   │   ├── employees/           # 数字员工列表、编辑和知识库绑定
│   │   ├── knowledge-bases/     # 知识库创建、文档上传和解析状态
│   │   ├── model-configurations/ # 百炼模型配置、真实验证与引用阻断
│   │   ├── tools/               # MCP、业务工具集、能力目录与 OpenAPI 导入
│   │   └── workflows/           # 页面编排、设计器控制器、节点面板、画布、属性和运行
│   ├── components/              # 真实跨功能复用的公共 UI
│   ├── api/                     # Axios、SSE、Query Client 和生成契约
│   ├── schemas/                 # Zod 运行时边界
│   ├── styles/
│   ├── test/
│   └── main.tsx
├── e2e/                         # Playwright 核心聊天链路
├── scripts/                     # 生产 manifest、chunk 与路由图预算分析
├── public/
├── package.json
├── pnpm-lock.yaml
├── vite.config.ts
├── tsconfig.json
├── .env.example
└── README.md
```

V2 业务区包含聊天工作台、数字员工、知识库、独立工作流设计器、模型管理、工具箱，以及仅 Owner
可见的审计事件页；工具箱代码只随对应 V2 任务落地，不提前创建空入口。未认证或尚未选择工作区时由真实
`auth` Provider 阻止业务路由挂载，工作区选择和成员配置复用全局壳层，不为其他未实现能力创建
空目录或菜单。工作流画布使用成熟的 React 节点
图库，不自行实现缩放、拖拽、连线和命中测试。
页面容器只组合控制器和展示区域；协议映射、服务端状态、流式/运行状态、画布和属性表单分模块维护。
架构门禁限制页面容器体量、跨 Feature 私有导入、实现层反向依赖容器和拆分模块循环依赖。
Vite 生产构建保留六个路由异步入口并使用入口感知 vendor 分组；manifest 分析同时约束 500,000
bytes 单 chunk 和 1,500,000 bytes 单路由首次 JS 图，生产 preview 浏览器验证首屏、切换和复用。

## 4. 跨端契约

```text
FastAPI / Pydantic
       ├── OpenAPI ------------------> contracts/openapi/
       └── 会话/工作流事件 Schema ---> contracts/events/
                                         |
                                         v
                                frontend/src/api/generated/
```

- Pydantic 是 REST 和流式事件的唯一协议来源；
- `contracts/` 保存生成快照和公共样例，不手写第二份 DTO；
- 前端生成代码禁止手工修改；
- CI/本地门禁检查生成结果无漂移；
- 会话事件使用显式版本、`conversation_id`、`message_id`、`turn_id` 和单调序号；工作流事件使用显式版本、`run_id`、`workflow_id`、节点快照和运行内单调序号。

## 5. 基础设施

```text
infra/ragflow/
├── VERSION                     # 确切版本，禁止 latest
├── UPSTREAM_COMMIT             # 官方 tag 对应提交，防止上游引用漂移
├── compose.override.yaml       # loopback、名称、数据目录和资源覆盖
├── manage.sh                   # 准备、校验、启动和停止稳定栈
├── test-manage.sh              # Compose 与端口失败门禁
└── README.md                   # 独立服务、配置和验证说明

infra/platform/                 # 当前路线图实际采用的平台基础设施
├── compose.yaml                # 平台独立 MySQL；其他组件按真实需要增加
├── manage.sh                   # 固定 context、端口、启动、停止和状态检查
└── README.md                   # 端口、资源、持久化和清理边界

infra/backup/                   # 平台与 RAGFlow 的可恢复备份边界
├── policy.env                  # RPO、RTO、保留代际和灾演周期单一来源
├── deployment-config.allowlist # 不含凭据的部署配置白名单
├── manage.sh                   # 加密备份、验证、保留和空环境恢复
├── drill.sh                    # 独立源销毁后由正式页面验收的灾难演练
├── recovery-ragflow.override.yaml # recovery 专属容器、端口和 Volume
├── test-manage.sh              # 安全、策略、停写和隔离恢复契约
└── README.md                   # 密钥分离、调度和恢复 Runbook

third_party/
└── ragflow/                    # 当前官方 submodule；V2 切换到私有补丁仓库的锁定提交
```

不让平台代码直连 RAGFlow 的内部依赖。V2 只允许在独立私有 RAGFlow 仓库中维护基于精确官方
`v0.26.4` 提交的版本化补丁；管理脚本只读取 `third_party/ragflow` 锁定 submodule，且在上游基线、
fork commit、origin、镜像标签或工作区完整性不匹配时关闭失败；
运行数据仍位于 `.local/dev/common-agent-dev/ragflow/`，稳定开发栈可以跨任务复用。普通 Python/npm
包必须以实际安装使用的 `uv.lock`/`pnpm-lock.yaml` 为准，不能用旁路源码目录替代包管理器锁定。
平台自有基础设施只有在路线图选用后才进入正式 Compose 和生产同路径验收。

## 6. 测试归属

| 测试类型 | 位置 |
| --- | --- |
| Python 领域/应用单元测试 | `backend/tests/unit/` |
| Deep Agents/LangGraph/RAGFlow 适配测试 | `backend/tests/integration/` |
| 加密归档与备份恢复契约 | `backend/tests/unit/adapters/backup/`、`infra/backup/test-manage.sh` |
| API 与事件契约测试 | `backend/tests/contract/` |
| React 组件与交互测试 | 与 `frontend/src/` 被测文件就近放置 |
| 核心聊天与恢复后页面流程 | `frontend/e2e/` |
| 前后端公共样例 | `contracts/fixtures/` |

## 7. 禁止事项

- 禁止在根目录混放前后端业务代码；
- 禁止前端直连模型、RAGFlow、Deep Agents、LangGraph、MCP 或业务 HTTP；
- 禁止前端以任务模型取代会话和消息；
- 禁止前端自行解释和执行工作流图；节点图必须提交后端统一校验并由 LangGraph 执行；
- 禁止复制前后端协议模型并分别维护；
- 禁止创建没有当前调用方和验收路径的空模块；有明确架构、可靠性或功能需要时，不得以“第一版”为由拒绝合适的技术组件；
- 禁止把 `automation-tool` 的 RPA 或行业代码复制进本项目；
- 除用户明确批准的现有百炼 Demo API Key 外，禁止提交其他密钥、运行数据、知识库数据、上传文件、缓存和日志。
