# 通用 Agent 中台工程结构

> 状态：已确认的 MVP 基线  
> 确认日期：2026-07-19

## 1. 核心决策

项目采用单一 Git 仓库，前端和后端分别位于 `frontend/` 与 `backend/`。初始形态用独立前后端进程快速闭环；任何数据库、中间件、存储、运行时、协议、调度、观测和工程工具都可以按当前功能与工程需要加入，技术方案不因首版业务范围被禁止，也不限于文档已经列举的组件。

```text
common-agent/
├── frontend/                   # React 聊天工作台
├── backend/                    # FastAPI 与 Agent 编排
├── contracts/                  # OpenAPI、会话/工作流事件和公共样例
├── infra/                      # RAGFlow 等外部依赖的本地接入说明
├── third_party/                # 项目实际消费源码的官方 Git submodule
├── scripts/                    # 跨前后端生成与验证脚本
├── docs/                       # 产品、架构和唯一开发路线图
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
│       │   │   ├── system.py
│       │   │   ├── conversations.py
│       │   │   ├── employees.py
│       │   │   ├── knowledge.py
│       │   │   ├── workflows.py
│       │   │   └── workflow_runs.py
│       │   └── app.py
│       ├── application/         # 平台用例编排
│       │   └── workflow_service.py
│       ├── conversations/       # 连续会话应用服务与事件
│       ├── employees/           # 数字员工应用服务与启动 Seed
│       ├── domain/              # 与第三方无关的会话和能力模型
│       │   ├── conversation.py
│       │   ├── employee.py
│       │   ├── knowledge.py
│       │   ├── workflow.py
│       │   └── workflow_run.py
│       │   └── knowledge.py
│       ├── runtimes/            # EmployeeRuntime 协议
│       │   └── base.py
│       ├── workflows/           # 独立工作流校验与 LangGraph 运行时
│       │   ├── validator.py
│       │   ├── compiler.py
│       │   ├── events.py
│       │   └── nodes/
│       ├── knowledge/           # KnowledgeService 协议
│       │   ├── base.py
│       │   ├── service.py
│       │   └── retrieval.py
│       ├── ports/               # 仓储、缓存、事件、对象存储与任务端口
│       └── adapters/            # 数据库、模型及第三方外围适配
│           ├── agent/           # Deep Agents 正式适配器
│           ├── knowledge/       # RAGFlow 正式适配器
│           ├── model/           # 阿里百炼模型适配器
│           └── persistence/     # MySQL 持久化适配器
├── migrations/                  # 当前正式数据库迁移
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── contract/
│   └── fixtures/
├── pyproject.toml
├── uv.lock
├── .env.demo                    # 允许版本化的百炼 Demo 配置
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

- `api/` 只负责 HTTP/SSE、参数校验和错误转换；
- `application/` 分别负责“发送消息并生成回复”和“触发工作流”用例；
- `domain/` 不导入 FastAPI、Deep Agents、LangGraph 或 RAGFlow；
- `workflows/` 只接收平台节点/边定义，先验证再编译为 LangGraph；数字员工通过 `WorkflowService` 调用工作流，禁止直接导入工作流图；
- 第三方 SDK 类型不得越过适配层；
- 员工、会话、消息、工作流和知识库绑定必须经过仓储端口；正式实现使用平台独立 MySQL、SQLAlchemy async 和 Alembic，不改变领域模型依赖方向；
- 任何第三方技术依赖都通过与其职责相符的应用端口和外围适配器接入；Redis、消息队列、对象存储和 Worker 只是示例，不构成白名单；只实现当前用例实际调用的端口，不创建没有调用方的空实现；
- RAGFlow 保存知识文档和索引，平台不直连其内部数据库、缓存、检索引擎或对象存储。

## 3. 前端结构

```text
frontend/
├── src/
│   ├── app/                     # Provider、布局和入口
│   ├── features/
│   │   ├── chat/                # 会话列表、消息流、输入和员工信息
│   │   ├── employees/           # 数字员工列表、编辑和知识库绑定
│   │   ├── knowledge-bases/     # 知识库创建、文档上传和解析状态
│   │   └── workflows/           # 节点面板、画布、配置、运行和结果
│   ├── components/              # 真实跨功能复用的公共 UI
│   ├── api/                     # Axios、SSE、Query Client 和生成契约
│   ├── schemas/                 # Zod 运行时边界
│   ├── styles/
│   ├── test/
│   └── main.tsx
├── e2e/                         # Playwright 核心聊天链路
├── public/
├── package.json
├── pnpm-lock.yaml
├── vite.config.ts
├── tsconfig.json
├── .env.example
└── README.md
```

第一版只有聊天工作台与独立工作流设计器，不为未实现能力创建空 Feature 目录或菜单。工作流画布使用成熟的 React 节点图库，不自行实现缩放、拖拽、连线和命中测试。

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

third_party/
└── ragflow/                    # 官方 submodule；固定到 VERSION/UPSTREAM_COMMIT
```

不复制或修改 RAGFlow 源码，也不让平台代码直连 RAGFlow 的内部依赖。管理脚本只读取
`third_party/ragflow` 官方 submodule，且在 commit、tag、origin 或工作区完整性不匹配时关闭失败；
运行数据仍位于 `.local/dev/common-agent-dev/ragflow/`，稳定开发栈可以跨任务复用。普通 Python/npm
包必须以实际安装使用的 `uv.lock`/`pnpm-lock.yaml` 为准，不能用旁路源码目录替代包管理器锁定。
平台自有基础设施只有在路线图选用后才进入正式 Compose 和生产同路径验收。

## 6. 测试归属

| 测试类型 | 位置 |
| --- | --- |
| Python 领域/应用单元测试 | `backend/tests/unit/` |
| Deep Agents/LangGraph/RAGFlow 适配测试 | `backend/tests/integration/` |
| API 与事件契约测试 | `backend/tests/contract/` |
| React 组件与交互测试 | 与 `frontend/src/` 被测文件就近放置 |
| 核心聊天流程 | `frontend/e2e/` |
| 前后端公共样例 | `contracts/fixtures/` |

## 7. 禁止事项

- 禁止在根目录混放前后端业务代码；
- 禁止前端直连模型、RAGFlow、Deep Agents 或 LangGraph；
- 禁止前端以任务模型取代会话和消息；
- 禁止前端自行解释和执行工作流图；节点图必须提交后端统一校验并由 LangGraph 执行；
- 禁止复制前后端协议模型并分别维护；
- 禁止创建没有当前调用方和验收路径的空模块；有明确架构、可靠性或功能需要时，不得以“第一版”为由拒绝合适的技术组件；
- 禁止把 `automation-tool` 的 RPA 或行业代码复制进本项目；
- 除用户明确批准的百炼 Demo API Key 外，禁止提交其他密钥、运行数据、知识库数据、上传文件、缓存和日志。
