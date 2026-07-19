# 通用 Agent 中台任务级开发路线图

> 文档性质：项目开发进度唯一执行台账  
> 建立日期：2026-07-19  
> 当前阶段：Wave 4 连续 AI 会话与自动检索
> MVP 顺序：知识库 → 数字员工绑定 → AI 会话 → 可视化工作流

本文件是任务进度、状态、完成定义和验证证据的唯一核对源。`product-scope.md` 只描述产品功能和边界，不承担进度同步；普通任务完成只更新本路线图。

## 1. 如何使用本路线图

开始任何任务前必须：

1. 检查前置任务全部满足；
2. 只把一个任务标为 `🧪 RED` 或 `🚧 实现中`；
3. 有业务逻辑时先写测试并实际看到目标失败；
4. 写最小实现并运行该任务门禁；
5. 验证真实边界、失败矩阵和资源清理；
6. 更新实际证据并标记最终状态；
7. 再启动下一任务。

文档、纯配置和生成代码不要求为内容本身编写单元测试，但必须执行适用的格式、链接、契约或生成校验。

每个任务的实现、适用测试、真实边界、资源清理和本路线图记录全部通过后，立即提交并推送当前分支。任务记录与代码进入同一提交时写“本任务提交（见 Git 历史）”；没有远端或写权限时先保留本地提交并记录解除条件。

## 2. 状态

| 状态 | 含义 |
| --- | --- |
| `⬜ 未开始` | 前置未满足或尚未进入任务 |
| `🧪 RED` | 目标测试已写并按预期失败 |
| `🚧 实现中` | 正在完成最小实现或文档/配置任务 |
| `🔍 待验收` | 自动化通过，仍缺真实 RAGFlow、百炼、桌面浏览器或资源门禁 |
| `⛔ 受阻` | 有明确外部阻塞、证据和解除条件 |
| `✅ 已完成` | 完成定义、测试、真实边界、清理和文档全部通过 |

## 3. 当前进度快照

快照日期：2026-07-20。

| 范围 | 当前结果 |
| --- | --- |
| 旧项目复盘 | `✅` 已审阅 `agent-platform` 规则/架构和 `automation-tool` 任务级路线图形式 |
| 项目拆分 | `✅` `common-agent` 只做 AI 中台；业务自动化留在 `automation-tool` |
| 产品交互 | `✅` 普通数字员工采用连续会话，不把每条消息变成任务 |
| 第一版范围 | `✅` AI 会话、数字员工、知识库、最小可视化工作流；无登录鉴权和 Skill |
| 模型 | `✅` 只直接接阿里百炼，复用旧私有仓库的 Demo Key，不引入模型网关 |
| 技术架构 | `✅` 技术方案不设白名单；平台正式持久化已切换为独立 MySQL 8.4 LTS，其他技术组件可按当前真实需要进入正式链路 |
| 开发环境 | `✅` 全部本机联调，不部署服务器；端口和 Docker 资源与其他项目隔离 |
| GitHub | `✅` `masterAventador/common-agent` 已创建为 PRIVATE，`main` 跟踪 `origin/main` |
| 项目规则/架构 | `✅` 主规则、产品边界、工程架构和任务级路线图已建立并校验 |
| 工程骨架 | `✅` frontend/backend/contracts/infra/scripts 已按目标边界建立，未混入临时 Sites 或空业务模块 |
| 后端入口 | `✅` FastAPI app factory、lifespan、请求 ID、统一错误和真实 loopback Health 已跑通 |
| 平台持久化 | `✅` 独立 MySQL 8.4.10、asyncmy、SQLAlchemy async、Alembic、隔离测试库、事务回滚和容器/进程重启恢复已跑通；SQLite 不再是正式验收依赖 |
| 百炼配置 | `✅` 已从 agent-platform 的 Git 跟踪配置迁移 Demo 模型/Base URL/Key，Key 仅存在于获准的私有配置文件 |
| 前端入口 | `✅` React/Vite/Ant Design 四入口壳层已通过组件、构建和真实浏览器导航验收 |
| 跨端契约 | `✅` FastAPI OpenAPI、前端生成 DTO 和隔离漂移检查已形成单一来源闭环 |
| 前端 API | `✅` Axios、Query Client、Zod、CORS 与后端真实成功/失败状态已跨端跑通 |
| RAGFlow 基线 | `✅` 官方 v0.25.6/tag commit、common-agent-dev 隔离栈、loopback 端口、数据目录和资源策略已锁定 |
| 产品代码 | `🚧` 知识库、数字员工、连续会话及工作流定义/编译/运行正式链路已完成；进入工作流设计器 |
| 本地服务 | `✅` 临时前后端均已停止；平台 MySQL 与 RAGFlow 六服务保留在独立 `colima-common-agent-dev` 稳定栈供后续复用 |

## 4. 全局完成门禁

每个代码任务都必须满足：

- TDD：保存 RED 失败证据，再进入 GREEN；
- Python：相关 pytest、Ruff、Mypy；
- TypeScript：相关 Vitest、ESLint、Typecheck、Build；
- UI：相关 Playwright；
- 协议：OpenAPI、事件 Schema 和生成 DTO 无漂移；
- 平台基础设施：当前正式数据库、缓存、队列、对象存储和 Worker 的迁移/隔离、事务或幂等、恢复与清理；
- RAGFlow：通过正式适配层连接独立真实服务；
- 模型/数字员工：通过 Deep Agents 正式适配层调用阿里百炼；
- 工作流：服务端校验、LangGraph 编译和真实节点运行；
- 安全：Key 不进前端/日志/错误，输入和上传有上限；
- 本地隔离：项目专属端口、名称、网络、Volume 和数据目录；
- 清理：停止本轮临时前后端/浏览器/验收环境，删除本项目无用测试容器、重复任务镜像和悬空层；固定 `common-agent-dev` RAGFlow 栈按项目规则复用；
- 文档：同一任务更新本路线图状态、命令、证据和遗留项。

仅通过 Mock 或 Demo Adapter 的跨层功能最多标 `🔍 待验收`。真实账号/外部服务暂不可用时可以继续不依赖它的任务，但不得冒充真实链路完成。

## 5. MVP 失败矩阵

每个相关任务开始前把适用项映射到具体测试，不适用项写明理由。

| 边界 | 必须覆盖的失败 |
| --- | --- |
| 配置 | 缺少、格式错误、端口冲突、错误环境和敏感值泄漏 |
| SQLite | 文件不可写、迁移失败、唯一冲突、事务回滚和重启恢复 |
| 平台 MySQL | 未启动、连接/认证失败、迁移失败、唯一冲突、事务回滚、重启恢复、端口/Volume 隔离和资源清理 |
| PostgreSQL | 连接失败、迁移失败、连接池耗尽、事务回滚和 Schema 隔离 |
| Redis/消息队列 | 不可用、超时、重复投递、乱序、积压、消费失败和恢复 |
| 对象存储 | Bucket/权限错误、上传中断、重复对象、清理失败和容量上限 |
| Worker | 启动失败、任务丢失、超时、重试幂等、崩溃恢复和优雅停止 |
| RAGFlow | 未启动、Key 错误、超时、知识库不存在和 API 版本漂移 |
| 文档 | 空文件、超限、不支持类型、重复上传、解析失败和解析超时 |
| 数字员工 | 字段非法、绑定知识库失效、模型配置错误和工作流越权 |
| 会话 | 重复提交、同会话并发、断流、晚到事件、停止与完成竞态 |
| 检索 | 空结果、低相关、引用缺字段、知识库切换和检索失败 |
| 百炼 | Key 错误、限流、超时、5xx、流中断和输出为空 |
| Deep Agents | 工具失败、未知事件、非预期状态和无授权工作流调用 |
| 工作流图 | 缺少开始/结束、孤立、自环、重复边、环、未知节点和无效配置 |
| 工作流运行 | 节点失败、停止、输出不匹配、知识库失效和模型失败 |
| 前端 | 后端不可用、Schema 漂移、刷新恢复、重复事件和安全错误展示 |
| Docker | 端口/名称冲突、内存不足、健康失败、其他项目隔离和镜像清理 |

表内技术是当前已识别边界，不构成白名单。任务采用其他数据库、中间件、存储、运行时、协议、调度、观测或工程工具时，必须在进入实现前把该技术的正式依赖、失败模式和清理证据补入本矩阵及任务完成定义。

## 6. Wave 0：规则与架构基线

| ID | 任务 | 交付物与完成定义 | 依赖 | 状态 |
| --- | --- | --- | --- | --- |
| R0-01 | 复盘旧项目 | 识别可复用规则、范围失控点和路线图形式，不复制旧业务代码 | — | ✅ 已完成 |
| R0-02 | 锁定 MVP 范围 | 会话优先；四项 MVP；无登录；本机联调；百炼单供应商 | R0-01 | ✅ 已完成 |
| R0-03 | 建立项目规则和架构 | `AGENTS.md`、`CLAUDE.md`、产品/工程/前后端架构一致且无旧范围残留 | R0-02 | ✅ 已完成 |
| R0-04 | 建立任务级路线图 | 本文件覆盖依赖、完成定义、失败矩阵、状态和完成记录 | R0-03 | ✅ 已完成 |
| R0-05 | 建立仓库入口和忽略规则 | 清理临时 Sites 骨架；README、`.gitignore`、`.editorconfig`；本机数据和除百炼 Demo Key 外的凭据不入 Git | R0-04 | ✅ 已完成 |
| R0-06 | 校正技术边界并体检环境 | 技术方案不设白名单；记录 Python/uv/Node/pnpm/Docker/gh/浏览器版本、端口、Docker 内存和可用磁盘 | R0-05 | ✅ 已完成 |
| R0-07 | 建立本地 Git 基线 | `main` 分支、首个规则/文档提交、工作树干净且无临时 Sites 文件 | R0-06 | ✅ 已完成 |
| R0-08 | 创建 GitHub 私有仓库 | 创建同名 `common-agent` PRIVATE 仓库、remote 正确并推送 `main` | R0-07 | ✅ 已完成 |

## 7. Wave 1：工程骨架与本地开发闭环

### 目标

建立标准 `frontend/`、`backend/` 工程和本机专属端口，不实现业务。

| ID | 任务 | 交付物与完成定义 | 依赖 | 状态 |
| --- | --- | --- | --- | --- |
| F1-01 | 建立目标工程骨架 | 建立 frontend/backend/contracts/infra/scripts；无业务代码混放和空功能目录 | R0-08 | ✅ 已完成 |
| B1-01 | 初始化 Backend 包 | Python 3.12、uv、src layout、pytest/Ruff/Mypy 和冻结锁文件 | F1-01 | ✅ 已完成 |
| B1-02 | FastAPI 与错误边界 | app factory、lifespan、统一错误和真实 loopback Health | B1-01 | ✅ 已完成 |
| B1-03 | 平台持久化基线 | 持久化适配边界、初始 SQLite 正式适配器、迁移、async session、空库升级和重启恢复；为 PostgreSQL 适配保留稳定边界 | B1-02 | ✅ 已完成 |
| B1-04 | 百炼 Demo 配置 | 从 agent-platform 安全迁移模型/base URL/Key；Key 不进入输出和测试快照 | B1-01 | ✅ 已完成 |
| B1-05 | 平台 MySQL 正式切换 | 独立 MySQL 容器/端口/Volume、SQLAlchemy async 驱动、Alembic、事务/迁移/重启恢复；正式链路不再以 SQLite 验收 | B1-03,K2-01 | ✅ 已完成 |
| F1-02 | 初始化 Frontend | React/TypeScript/Vite/Ant Design/pnpm、四入口空壳和专属端口 | F1-01 | ✅ 已完成 |
| C1-01 | OpenAPI 契约闭环 | 后端导出、前端生成、漂移检查和公共错误 DTO | B1-02,F1-02 | ✅ 已完成 |
| F1-03 | 前端 API 基线 | Axios、Query Client、Zod 和后端真实状态提示 | C1-01 | ✅ 已完成 |

## 8. Wave 2：RAGFlow 知识库闭环

### 目标

先让用户在本机真正创建知识库、上传文档并看到解析结果。

| ID | 任务 | 交付物与完成定义 | 依赖 | 状态 |
| --- | --- | --- | --- | --- |
| K2-01 | 锁定 RAGFlow 版本与资源 | 确切稳定版本；固定 `common-agent-dev`、独立端口/Volume；评估 Docker 32GB 级资源和复用策略 | R0-06 | ✅ 已完成 |
| K2-02 | KnowledgeService 契约 | list/create/upload/list-documents/retrieve/status 平台协议和失败测试 | B1-02 | ✅ 已完成 |
| K2-03 | RAGFlow 适配器 | 官方 SDK/API 接入、超时、错误转换、版本健康和真实服务验收 | K2-01,K2-02 | ✅ 已完成 |
| K2-04 | 知识库 API | 列表、创建、文档上传、解析状态；上传大小/类型限制 | K2-03,B1-05,C1-01 | ✅ 已完成 |
| K2-05 | 知识库页面 | 创建、上传、真实状态、失败重试和空状态 | K2-04,F1-03 | ✅ 已完成 |
| K2-06 | 知识库 Playwright | 浏览器完成创建→上传→解析完成/失败展示 | K2-05 | ✅ 已完成 |

## 9. Wave 3：数字员工与知识库绑定

### 目标

创建可用于会话的数字员工，并稳定绑定一个 RAGFlow 知识库。

| ID | 任务 | 交付物与完成定义 | 依赖 | 状态 |
| --- | --- | --- | --- | --- |
| E3-01 | Employee 领域与迁移 | 模型、字段限制、正式持久化模型和知识库引用完整性策略 | B1-03,K2-02 | ✅ 已完成 |
| E3-02 | 数字员工 API | 列表、详情、创建、编辑和知识库绑定；失效绑定明确拒绝 | E3-01,K2-03,C1-01 | ✅ 已完成 |
| E3-03 | 预置知识助理 Seed | 幂等创建、可编辑、不制造重复记录 | E3-02 | ✅ 已完成 |
| E3-04 | 数字员工页面 | 列表、创建/编辑表单、知识库选择和“开始对话” | E3-02,F1-03 | ✅ 已完成 |
| E3-05 | 数字员工 Playwright | 创建员工→绑定知识库→刷新后仍存在→进入对话 | E3-04 | ✅ 已完成 |

## 10. Wave 4：连续 AI 会话与自动检索

### 目标

完成最核心的“发一句、回一句、继续追问”闭环，并自动检索员工绑定知识库。

| ID | 任务 | 交付物与完成定义 | 依赖 | 状态 |
| --- | --- | --- | --- | --- |
| A4-01 | 会话/消息领域与迁移 | Conversation/Message/Citation、终态和正式持久化重启恢复 | B1-03,E3-01 | ✅ 已完成 |
| A4-02 | 百炼模型适配器 | `ChatOpenAI`、流式输出、超时/有限重试和脱敏错误 | B1-04 | ✅ 已完成 |
| A4-03 | EmployeeRuntime 契约 | 历史、系统指令、知识上下文、流式事件和停止语义 | A4-01,K2-02 | ✅ 已完成 |
| A4-04 | Deep Agents 适配器 | 官方 `create_deep_agent`、受控工具、无 Shell/本机文件权限 | A4-02,A4-03 | ✅ 已完成 |
| A4-05 | 自动知识检索 | 每条消息按员工绑定检索、空结果语义、引用映射和检索失败 fail closed | A4-03,K2-03,E3-02 | ✅ 已完成 |
| A4-06 | 会话 API 与 SSE | 新建/列表/历史/发送/停止/重试；事件单调、持久化后推送 | A4-04,A4-05,C1-01 | ✅ 已完成 |
| A4-07 | 聊天工作台 | 三栏会话、流式回复、引用、停止、重试和刷新恢复 | A4-06,F1-03 | ✅ 已完成 |
| A4-08 | Demo 核心 E2E | 固定适配器完成两轮会话、检索引用、断流和重试 | A4-07 | ✅ 已完成 |
| A4-09 | 真实会话验收 | 本机 RAGFlow + Deep Agents + 阿里百炼完成两轮知识问答并验证引用 | A4-08 | ✅ 已完成 |

## 11. Wave 5：最小可视化工作流

### 目标

拖拽四类节点形成有效图，后端转换为 LangGraph 并支持手动/数字员工触发。

| ID | 任务 | 交付物与完成定义 | 依赖 | 状态 |
| --- | --- | --- | --- | --- |
| W5-01 | 工作流 Schema 与校验 | 四类节点、边、配置、图不变量和完整非法矩阵 | B1-03,K2-02,A4-02 | ✅ 已完成 |
| W5-02 | 工作流持久化与 API | 正式仓储、列表/详情/创建/编辑/校验，位置与业务配置分离 | W5-01,C1-01 | ✅ 已完成 |
| W5-03 | LangGraph 编译器 | 注册节点转换、StateGraph 编译、步数上限和错误映射 | W5-01,K2-03,A4-02 | ✅ 已完成 |
| W5-04 | 工作流运行与事件 | 手动运行、节点事件、结果、失败和停止摘要 | W5-02,W5-03 | ✅ 已完成 |
| W5-05 | 工作流设计器 | React Flow 拖拽/连线/配置/保存/服务端校验 | W5-02,F1-03 | ✅ 已完成 |
| W5-06 | 手动运行 UI | 输入、运行、节点高亮、失败和最终结果 | W5-04,W5-05 | ⬜ 未开始 |
| W5-07 | 数字员工触发工具 | 只允许调用员工 allowlist 中工作流，共用 WorkflowService | W5-04,A4-04 | ⬜ 未开始 |
| W5-08 | 工作流 E2E | 创建图→保存→手动运行→员工触发→刷新查看摘要 | W5-06,W5-07 | ⬜ 未开始 |

## 12. Wave 6：MVP 收口

| ID | 任务 | 交付物与完成定义 | 依赖 | 状态 |
| --- | --- | --- | --- | --- |
| Q6-01 | 完整失败矩阵 | 第 5 节所有适用分支有自动化或明确真实证据 | A4-09,W5-08 | ⬜ 未开始 |
| Q6-02 | Docker 资源与清理验收 | 记录峰值/稳定内存、48GiB 独立 profile 建议、端口/context 隔离；证明稳定栈复用、按影响重建，并清理重复任务镜像和悬空层 | Q6-01 | ⬜ 未开始 |
| Q6-03 | 全量自动化 | 后端、前端、契约、构建和 Playwright 全量通过 | Q6-02 | ⬜ 未开始 |
| Q6-04 | 本机 MVP 验收 | 从空平台完成知识库→员工→两轮对话→工作流，全部走正式入口 | Q6-03 | ⬜ 未开始 |
| Q6-05 | 规格与质量复审 | 核对范围、假绿、泄密、资源泄漏、残留进程和无用代码 | Q6-04 | ⬜ 未开始 |

## 13. 高冲突与唯一写入区域

- 根目录规则、路线图、依赖锁文件和忽略规则；
- 当前正式数据库 migration revision；
- OpenAPI、会话事件和生成 DTO；
- FastAPI app 装配、前端 Query Client 和全局导航；
- RAGFlow Compose、端口、Volume 和版本；
- 百炼 Demo 配置；
- 工作流节点 Schema 和注册表；

当前不使用子代理；只有用户明确要求后才允许并行，并为这些区域指定唯一写入者。

## 14. 每项任务的完成记录格式

```text
### <任务 ID> <任务名>

- 状态：✅ 已完成 / 🔍 待验收 / ⛔ 受阻
- 日期：YYYY-MM-DD
- 提交：<commit 或“本任务提交（见 Git 历史）”>
- RED：<失败测试与正确失败原因；文档/配置任务写不适用理由>
- GREEN：<实际命令与结果>
- 真实边界：<本机服务、版本、数据和最终状态>
- 失败矩阵：<覆盖项与不适用理由>
- 清理：<进程/容器/镜像/端口/临时数据>
- 文档：<同步更新文件>
- 遗留：<非阻断低风险项或无>
```

### R0-01 复盘旧项目

- 状态：✅ 已完成
- 日期：2026-07-19
- 提交：待 R0-07 纳入首个基线提交
- RED：不适用；只读调研任务，没有生产代码
- GREEN：完整读取全局规则、`agent-platform/CLAUDE.md`、核心工程结构与 `automation-tool/CLAUDE.md`、路线图任务/完成记录格式
- 真实边界：只读访问两个本地参考仓库，没有复制业务代码或修改参考项目
- 失败矩阵：重点识别认证、租户、Tauri、模型网关、行业能力包、部署等范围膨胀来源
- 清理：没有启动参考项目服务或创建临时文件
- 文档：结论进入当前项目规则、产品范围和架构
- 遗留：旧项目代码只在具体任务证明可复用时再审计

### R0-02 锁定 MVP 范围

- 状态：✅ 已完成
- 日期：2026-07-19
- 提交：待 R0-07 纳入首个基线提交
- RED：不适用；产品决策任务，没有生产代码
- GREEN：用户逐项确认会话优先、工作流独立且可拖拽、首版四能力、无登录鉴权、本机联调、百炼单供应商和 Docker 资源/清理要求
- 真实边界：范围以本文件和 `docs/product-scope.md` 为准，未启动产品实现
- 失败矩阵：明确排除 Skill、登录注册等企业用户功能、业务自动化、远程部署和面向用户的多供应商管理；技术基础设施不作为产品非目标
- 清理：无额外进程、容器或临时数据
- 文档：`CLAUDE.md`、`docs/product-scope.md`、前后端与工程架构
- 遗留：无；后续范围变化必须新增或调整路线图任务

### R0-03 建立项目规则和架构

- 状态：✅ 已完成
- 日期：2026-07-19
- 提交：待 R0-07 纳入首个基线提交
- RED：不适用；规则、产品边界和架构文档任务，没有生产代码
- GREEN：`git diff --check` 通过；必读文件存在性检查通过；旧项目专属范围关键词检查无残留；规则/架构关键边界检查命中预期内容
- 真实边界：完整对照本机 `agent-platform` 与 `automation-tool` 主规则；重复规则以 `automation-tool` 的 TDD、生产同路径、失败矩阵和工作方式为准
- 失败矩阵：覆盖范围膨胀、任务/会话混淆、工作流归属、凭据例外、本机端口冲突、Docker 资源、稳定栈复用和镜像清理
- 清理：停止并退出临时 Sites 前端预览；未启动后端、RAGFlow 或浏览器测试
- 文档：`AGENTS.md`、`CLAUDE.md`、`docs/product-scope.md`、`docs/project-structure.md`、`docs/backend-architecture.md`、`docs/frontend-architecture.md`
- 遗留：临时 Sites 源文件和依赖目录由 R0-05 精确清理；本路线图完整性由 R0-04 单独校验

### R0-04 建立任务级路线图

- 状态：✅ 已完成
- 日期：2026-07-19
- 提交：待 R0-07 纳入首个基线提交
- RED：不适用；任务拆分和台账文档任务，没有生产代码
- GREEN：解析任务表得到 49 个任务、唯一进行中任务 1 个、缺失依赖 0 个；MVP 四能力、正式技术边界和最终真实验收关键词全部命中；`git diff --check` 随基线统一复验
- 真实边界：任务从规则/仓库建立覆盖到本机正式入口 MVP 验收，外部依赖不可用时只能进入 `🔍 待验收`
- 失败矩阵：配置、数据库、Redis/消息队列、对象存储、Worker、RAGFlow、文档、员工、会话、检索、百炼、Deep Agents、工作流、前端和 Docker 均有失败边界
- 清理：校验只读执行，未新增进程、容器、镜像或临时数据
- 文档：`docs/development-roadmap.md`
- 遗留：无；后续每项任务只在本文件维护状态与证据

### R0-05 建立仓库入口和忽略规则

- 状态：✅ 已完成
- 日期：2026-07-19
- 提交：待 R0-07 纳入首个基线提交
- RED：不适用；仓库入口、忽略规则和临时生成物清理任务，没有生产代码
- GREEN：`git diff --check` 通过；根目录只保留规则、文档和 Git 元数据；README 引用的项目文档存在；`.local/`、常规 `.env` 命中忽略，`backend/.env.demo` 可被 Git 跟踪
- 真实边界：README 只描述产品、技术栈和文档入口，任务进度仍唯一指向本路线图
- 失败矩阵：验证本机数据、普通凭据、测试报告和 RAGFlow 数据不会进入 Git，同时保留用户明确授权的百炼 Demo 配置例外
- 清理：精确删除本轮 Sites 初始化产生的目录、配置和约 776MB `node_modules`；可由原初始化命令重建，没有删除用户原有文件
- 文档：`README.md`、`.gitignore`、`.editorconfig`、`docs/development-roadmap.md`
- 遗留：无；目标 React/FastAPI 工程由 F1-01 后续建立

### R0-06 校正技术边界并体检环境

- 状态：✅ 已完成
- 日期：2026-07-19
- 提交：待 R0-07 纳入首个基线提交
- RED：不适用；产品/技术边界校正和只读环境体检任务，没有生产代码
- GREEN：路线图解析得到 49 个任务、唯一进行中任务 1 个、缺失依赖 0 个；Homebrew 安装并复验 Python 3.12.13；其余工具版本命令、端口监听检查、`docker info/ps/system df`、`df -h` 和 `gh auth status` 均成功
- 真实边界：uv 0.11.28、Node 26.0.0、pnpm 11.9.0、Docker 29.4.3、Compose 5.3.1、gh 2.92.0、Chrome 150.0.7871.128、Homebrew 6.0.11；GitHub 当前账号为 `masterAventador`
- 失败矩阵：正式端口 18200/18280/19380 和潜在隔离端口 19379/19432/19900 均无监听；Docker Desktop 可用内存 33,585,897,472 字节（约 31.3 GiB，满足 32GB 级配置）；磁盘可用约 3.4TiB；检测到 `agent-platform` 容器运行中，未复用其 8000/8080/4000/5432/6379/9000-9001 端口
- 清理：只安装可长期复用的 Python 3.12 并由 Homebrew 完成自身清理；未停止、重启或删除任何其他项目容器、镜像、Volume 或进程
- 文档：`CLAUDE.md`、`README.md`、`docs/product-scope.md`、`docs/project-structure.md`、`docs/backend-architecture.md`、`docs/development-roadmap.md`
- 遗留：具体采用哪些技术组件由对应功能任务按真实需要决定；RAGFlow 版本和各容器实测资源在 K2-01 锁定

### R0-07 建立本地 Git 基线

- 状态：✅ 已完成
- 日期：2026-07-19
- 提交：本任务提交（见 Git 历史）
- RED：不适用；Git 仓库基线任务，没有生产代码
- GREEN：`git diff --check` 通过；当前分支为 `main`；目标规则/文档/入口文件进入首个提交；提交后复验工作树
- 真实边界：基线只包含当前 `common-agent` 的规则、产品/架构文档、完整路线图、README 和忽略规则，不包含临时 Sites 脚手架、依赖或运行数据
- 失败矩阵：实际凭据模式扫描无命中；`.local/` 和常规环境文件被忽略；GitHub 远端由 R0-08 单独以 PRIVATE 可见性创建
- 清理：无临时进程或容器；临时 Sites 文件和依赖已在 R0-05 清理
- 文档：`docs/development-roadmap.md`
- 遗留：当前任务完成时尚无远端，R0-08 创建私有仓库后立即推送本提交

### R0-08 创建 GitHub 私有仓库

- 状态：✅ 已完成
- 日期：2026-07-19
- 提交：本任务提交（见 Git 历史）
- RED：不适用；远端仓库创建与规则配置任务，没有生产代码
- GREEN：`gh repo create common-agent --private --source=. --remote=origin --push` 成功；`gh repo view` 返回 `nameWithOwner=masterAventador/common-agent`、`visibility=PRIVATE`、默认分支 `main`
- 真实边界：`origin` 的 fetch/push URL 均指向 `https://github.com/masterAventador/common-agent.git`，本地 `main` 跟踪 `origin/main`，首个基线提交 `9d69a91` 已推送
- 失败矩阵：创建前确认同名仓库不存在；创建后没有以网页外观或命令成功文本代替可见性校验，直接读取 GitHub 仓库元数据证明为 PRIVATE
- 清理：未创建多余 remote、分支、仓库或临时凭据；没有启动本地服务或容器
- 文档：`CLAUDE.md` 增加项目范围内沙箱外执行持续授权；`docs/development-roadmap.md` 更新唯一任务状态和证据
- 遗留：无；后续每个完成任务按项目规则自动提交并推送

### F1-01 建立目标工程骨架

- 状态：✅ 已完成
- 日期：2026-07-19
- 提交：本任务提交（见 Git 历史）
- RED：不适用；目录边界和共享配置入口任务，没有生产代码
- GREEN：`git diff --check` 通过；backend/frontend/contracts/infra/scripts 均存在且无空目录；根 `.env.example` 可被 Git 跟踪；旧 Sites `app/`、`worker/` 不存在
- 真实边界：每个顶层目录只有职责、依赖方向和后续初始化任务说明，没有提前创建空业务 Feature 或伪实现
- 失败矩阵：共享配置只包含 loopback 地址、项目专属端口和空 RAGFlow Key；本机数据与真实凭据仍由 `.gitignore` 排除
- 清理：未安装依赖、启动进程、创建容器或生成缓存
- 文档：`.env.example`、各目标目录 README、`docs/development-roadmap.md`
- 遗留：具体 Python/React 结构分别由 B1-01、F1-02 建立

### B1-01 初始化 Backend 包

- 状态：✅ 已完成
- 日期：2026-07-19
- 提交：本任务提交（见 Git 历史）
- RED：先创建 `tests/test_package.py`，运行 `uvx --from pytest pytest -q tests/test_package.py`，因 `common_agent` 尚不存在以 `ModuleNotFoundError` 收集失败，证明测试能捕获缺失包
- GREEN：`uv run --frozen pytest -q` 1 passed；`ruff check .`、`ruff format --check .`、`mypy src tests` 和 `uv lock --check` 全部通过
- 真实边界：Homebrew CPython 3.12.13 创建 `.venv`；项目以 `src/common_agent` 可安装包运行；`uv.lock` 冻结 13 个包，实际门禁包含 pytest 9.1.1、Ruff 0.15.22、Mypy 1.20.2
- 失败矩阵：验证包缺失会真实失败、Python 版本限制为 `>=3.12,<3.13`、锁文件可复现；服务/网络/数据库失败不适用于纯包基线
- 清理：没有启动端口、进程或容器；`.venv` 作为后续任务复用的本机环境保留且被 Git 忽略
- 文档：`backend/README.md`、`backend/pyproject.toml`、`backend/.python-version`、`backend/uv.lock`、`docs/development-roadmap.md`
- 遗留：无；FastAPI 依赖和应用入口由 B1-02 以独立 RED/GREEN 引入

### B1-02 FastAPI 与错误边界

- 状态：✅ 已完成
- 日期：2026-07-19
- 提交：本任务提交（见 Git 历史）
- RED：真实 loopback 测试先启动 `python -m uvicorn`，两个用例均因 `No module named uvicorn` 失败；配置单元测试因 `common_agent.bootstrap` 不存在收集失败
- GREEN：全量 `uv run --frozen pytest -q` 12 passed；`ruff check .`、`ruff format --check .`、`mypy src tests`、`uv lock --check` 全部通过
- 真实边界：通过正式 `uv run --frozen python -m common_agent` 启动 `127.0.0.1:18200`；独立 curl 请求正式 Health 得到 200/版本 0.1.0，请求未知 API 得到 404 和含同一 `X-Request-ID` 的稳定错误信封
- 失败矩阵：覆盖非整数/越界端口、公开绑定地址拒绝、Uvicorn 未就绪、未知路由、应用错误、请求校验脱敏和内部异常脱敏；数据库与外部服务尚未进入本任务
- 清理：正式验收后向 Uvicorn 发送 SIGINT，lifespan 完整关闭并确认 18200 无监听；测试子进程均在 fixture `finally` 中终止
- 文档：`backend/README.md`、`backend/pyproject.toml`、`backend/uv.lock`、`docs/development-roadmap.md`
- 遗留：Health 当前只证明 API 自身就绪；数据库、RAGFlow 和百炼状态在各自正式适配任务接入

### B1-03 平台持久化基线

- 状态：✅ 已完成
- 日期：2026-07-19
- 提交：本任务提交（见 Git 历史）
- RED：数据库集成测试先因 `No module named sqlalchemy` 收集失败；数据库配置测试因 `DatabaseSettings` 不存在收集失败；首次真实 Alembic 执行还暴露缺少 SQLAlchemy async `greenlet` 依赖并正确失败
- GREEN：全量 `uv run --frozen pytest -q` 18 passed；Ruff、格式、Mypy（含 migrations）和锁文件检查通过；正式 Alembic CLI 升级隔离空库后读取 revision `20260719_0001`
- 真实边界：FastAPI lifespan 使用正式 `Database` 适配器自动迁移并探测连接；真实 SQLite、aiosqlite、SQLAlchemy async 与 Alembic 链路在两个独立 Uvicorn 进程间复用同一数据库并恢复成功
- 失败矩阵：覆盖缺失 SQLAlchemy/greenlet、缺少 CLI 数据库配置、父目录不存在、不可写父路径脱敏失败、事务异常回滚、空库升级、重复升级和进程重启；PostgreSQL 只验证 URL 可配置，未安装驱动或冒充真实适配完成
- 清理：pytest 临时数据库自动清理；手工验收的 `.local/acceptance/b1-03.db` 和误建空目录已精确删除；无 18200 监听或数据库进程残留
- 文档：`.env.example`、`backend/README.md`、Alembic 配置/迁移、正式 Database 适配器、`docs/development-roadmap.md`
- 遗留：领域专属 Repository 随 Employee/Conversation/Workflow 任务定义，避免当前提前创建无调用方的通用仓储；PostgreSQL 等其他正式适配器按真实需求单独 TDD 和验收

### B1-04 百炼 Demo 配置

- 状态：✅ 已完成
- 日期：2026-07-19
- 提交：本任务提交（见 Git 历史）
- RED：配置单元/集成测试先因 `ModelSettings` 不存在产生两个收集错误，证明测试能捕获缺少正式配置模型与 Demo 文件加载入口
- GREEN：百炼配置定向测试 6 passed；全量后端 pytest 24 passed；Ruff、格式、Mypy 和锁文件检查全部通过
- 真实边界：来源 `agent-platform/infra/compose/.env.litellm` 已由 `git ls-files` 证明受版本控制；迁移时把 LiteLLM 的 `dashscope/qwen-plus` 转为百炼直连模型名 `qwen-plus`，保留真实 HTTPS Base URL，Demo Key 只写入 PRIVATE 仓库获准的 `backend/.env.demo`
- 失败矩阵：覆盖三项配置分别缺失、非 HTTPS Base URL、`SecretStr` repr/JSON 脱敏、真实 Demo 文件加载；扫描确认三个字段各一条且 Key 未出现在 `.env.demo` 之外的项目文件
- 清理：未启动模型请求、端口、进程或容器；未创建临时 Key 文件或把 Key 打印到命令输出、测试快照、日志和路线图
- 文档：`.env.example`、`backend/.env.demo`、`backend/README.md`、ModelSettings 与配置测试、`docs/development-roadmap.md`
- 遗留：本任务只证明安全配置边界；`ChatOpenAI` 真实百炼请求、超时/重试和回复脱敏由 A4-02 验收

### F1-02 初始化 Frontend

- 状态：✅ 已完成
- 日期：2026-07-19
- 提交：本任务提交（见 Git 历史）
- RED：先建立路由壳层测试，`pnpm exec vitest run src/app/App.test.tsx` 因 `./App` 不存在按预期失败；实现后测试还发现跨用例 DOM 未清理并修正为显式 `afterEach(cleanup)`
- GREEN：Vitest 5 passed；ESLint、TypeScript typecheck、`pnpm build`、`pnpm peers check`、`pnpm install --frozen-lockfile` 全部通过
- 真实边界：正式 `pnpm dev` 在 `127.0.0.1:18280` strict port 启动；agent-browser 真实点击 AI 会话、数字员工、知识库、工作流四个链接并逐页确认 URL/标题，根路径真实重定向到 `/chat`；全页截图人工检查布局无重叠或缺失
- 失败矩阵：覆盖 App 缺失、测试隔离、根路由、四入口、未知路由回退、专属端口和依赖 peer 冲突；发现 TypeScript 7 不满足 typescript-eslint `<6.1`，锁定兼容的 TypeScript 6.0.3 后复验无 peer 问题
- 清理：关闭 agent-browser 会话和本轮 Vite；确认 18280 无监听；删除 `dist`、tsbuildinfo 和临时验收截图，保留被 Git 忽略且后续复用的 `node_modules`
- 文档：`frontend/README.md`、前端 package/lock/config、正式入口/样式/测试、`docs/development-roadmap.md`
- 遗留：Ant Design 当前单入口构建包约 564kB 并产生 chunk 提示；等真实 Feature 页面进入后按路由拆分，当前不调高阈值掩盖提示

### C1-01 OpenAPI 契约闭环

- 状态：✅ 已完成
- 日期：2026-07-19
- 提交：本任务提交（见 Git 历史）
- RED：后端契约测试因 OpenAPI 缺少 `ErrorEnvelope` 和快照文件不存在出现 2 个失败；前端 `pnpm typecheck` 因 `./contracts` 不存在失败
- GREEN：后端 pytest 26 passed，前端 Vitest 6 passed；Ruff、格式、Mypy、ESLint、typecheck、build、peer 和锁文件门禁通过；`check-contracts.sh` 隔离重建并逐字节比较通过
- 真实边界：正式 Uvicorn 使用隔离 SQLite 启动后，从真实 `http://127.0.0.1:18200/openapi.json` 获取 Schema，经 jq 排序与已提交 OpenAPI 完全一致；同一快照由 openapi-typescript 7.13.0 生成前端 `schema.d.ts`
- 失败矩阵：覆盖错误 DTO 缺失、快照缺失、前端类型入口缺失、生成漂移和工具 peer 冲突；openapi-typescript 要求 TypeScript 5，与 typescript-eslint 共同约束后锁定 TypeScript 5.9.3并复验无 peer 问题
- 清理：漂移脚本 trap 删除唯一临时目录；停止正式 Uvicorn 并确认 18200 无监听；删除隔离数据库、前端 dist 和 tsbuildinfo
- 文档：契约生成/检查脚本、`contracts/openapi/openapi.json`、前端生成类型与公共别名、contracts/scripts README、`docs/development-roadmap.md`
- 遗留：当前 Schema 只包含 Health 和公共错误；以后每个 API 任务必须同任务重新生成并通过漂移检查

### F1-03 前端 API 基线

- 状态：✅ 已完成
- 日期：2026-07-19
- 提交：本任务提交（见 Git 历史）
- RED：后端测试因 `CorsSettings` 缺失收集失败；前端测试因 Axios、`system.ts` 和 `SystemStatus` 缺失产生 2 个失败套件
- GREEN：后端 pytest 29 passed，前端 Vitest 11 passed；Ruff、格式、Mypy、ESLint、typecheck、build、peer 和契约漂移检查全部通过
- 真实边界：同时启动正式 Uvicorn 18200 与 Vite 18280，agent-browser 从正式 React 页面经 Axios/Zod 和真实 CORS 访问 Health，看到“后端正常”；停止 Uvicorn 并刷新同一页面后真实显示“后端不可用”
- 失败矩阵：覆盖 Health Schema 漂移、公共错误信封映射、传输细节脱敏、Query 成功/失败状态、远程 Origin 拒绝、正式 loopback Origin 允许和后端连接拒绝；没有 Mock 代替最终跨进程验收
- 清理：关闭 agent-browser、Uvicorn 和 Vite，确认 18200/18280 无监听；删除隔离 SQLite、dist 和 tsbuildinfo，保留被忽略的依赖缓存
- 文档：根/前端环境示例、frontend README、Axios/Query/Zod/状态组件/CORS 配置与测试、`docs/development-roadmap.md`
- 遗留：新增 Axios/Query/Zod 后单入口包约 709kB，仍保留真实构建提示；首个业务 Feature 开始时执行路由级懒加载和供应商分包，不调高阈值

### K2-01 锁定 RAGFlow 版本与资源

- 状态：✅ 已完成
- 日期：2026-07-19
- 提交：本任务提交（见 Git 历史）
- RED：首次执行 `bash infra/ragflow/test-manage.sh` 因正式 `manage.sh` 不存在以“缺少可执行的 RAGFlow 管理脚本”失败；TDD 自检发现非法端口校验缺独立 RED 后先撤销该实现，再以 `RAGFLOW_API_PORT=abc` 执行门禁，按预期因非法值仍被放行而失败
- GREEN：`bash infra/ragflow/test-manage.sh` 通过固定版本/提交、活动 Compose、loopback、Volume、资源、非法值和占用端口门禁；`shellcheck infra/ragflow/manage.sh infra/ragflow/test-manage.sh`、`git diff --check` 通过；正式 `manage.sh config` 由 Docker Compose 成功渲染，`manage.sh pull-image` 复用本机 `infiniflow/ragflow:v0.25.6`
- 真实边界：RAGFlow 官方 release `v0.25.6` 与 tag commit `8f0632c8d9efacbcd11aaf6e0f4cb634169bfea4` 双固定；未修改 checkout 位于 `.local/dev/common-agent-dev/ragflow/upstream/v0.25.6`；Compose project 为 `common-agent-dev`，容器/Volume 使用 `common-agent-ragflow-*`，REST API/Web 分别为 `127.0.0.1:19380/19381`，所有内部端口也只绑定独立 loopback 端口
- 失败矩阵：覆盖 `latest`/上游漂移防护、非法端口、真实监听冲突、公开绑定、其他项目名称/端口隔离；官方要求最低 16GB，而当前 Docker Desktop 为 31.28GiB、其他已运行项目实测约 2.2GiB，默认多语言 `BAAI/bge-m3` 设 24GiB 上限，首次解析若出现 OOM 则把 Docker Desktop 提高到 48GiB，不静默降级到英文 embedding
- 清理：端口冲突测试的临时 Python 监听由 trap 停止并删除输出文件；`common-agent-dev` 容器、网络和 Volume 均未创建，无任务镜像或悬空层；保留约 133MB 被忽略的稳定官方 checkout 和空数据目录，避免后续重复下载
- 文档：`.env.example`、`README.md`、`infra/README.md`、`infra/ragflow/*`、`docs/project-structure.md`、`docs/backend-architecture.md`、`docs/development-roadmap.md`
- 遗留：TEI 镜像、真实容器启动、API 健康与启动/稳定内存测量由 K2-03 完成；完整解析和检索压测在知识库纵向链路及 Q6-02 继续记录

### K2-02 KnowledgeService 契约

- 状态：✅ 已完成
- 日期：2026-07-19
- 提交：本任务提交（见 Git 历史）
- RED：先建立 `tests/unit/knowledge/test_contract.py`，执行 `uv run --frozen pytest -q tests/unit/knowledge/test_contract.py` 因 `common_agent.domain` 尚不存在以 `ModuleNotFoundError` 收集失败，证明测试能捕获平台知识契约缺失
- GREEN：契约定向测试 9 passed；后端全量 `uv run --frozen pytest -q` 38 passed；`ruff check .`、`ruff format --check .` 和 `mypy src tests` 全部通过
- 真实边界：新增 framework-independent 领域模型与 `KnowledgeService` Protocol，稳定覆盖 status、list/create knowledge base、upload/list documents 和 retrieve；协议不导入或泄露 RAGFlow SDK/API 类型，本任务是内部平台边界，不以 Fake 或直接下层调用冒充真实 RAGFlow 功能验收
- 失败矩阵：稳定建模未配置、服务不可用、知识库失效、明确上传失败、上传结果未知和上游响应非法；空检索由空 chunks 正常表达；文档二进制内容从 repr 排除，所有返回模型不可变；网络超时、HTTP/业务错误分类和真实版本漂移由 K2-03 适配器测试覆盖
- 清理：没有启动端口、进程、浏览器或容器；pytest 缓存被 Git 忽略，无上传文件、知识库数据、任务镜像或临时资源遗留
- 文档：`docs/development-roadmap.md`
- 遗留：K2-03 实现 RAGFlow v0.25.6 正式适配器并证明真实服务；K2-04 再把平台模型转换为 FastAPI/OpenAPI 对外契约

### K2-03 RAGFlow 适配器

- 状态：✅ 已完成
- 日期：2026-07-19
- 提交：本任务提交（见 Git 历史）
- RED：适配器单元测试先因正式模块/HTTP 依赖不存在而收集失败；基础设施配置测试分别捕获共享 Docker context、非官方 TEI 镜像和缺少只读本地模型门禁；首次真实调用在注册、登录成功后因错误使用 `/v1/system/tokens` 得到 404，证明真实 RAGFlow 契约能发现 Mock 未覆盖的路径差异；稳定栈运行后管理脚本测试又捕获端口值校验会被已占用端口抢先短路
- GREEN：适配器定向测试 26 passed；后端全量 `uv run --frozen pytest -q` 64 passed、1 个需显式真实环境的测试按设计 skipped；真实环境测试 1 passed in 7.51s；Ruff、格式、Mypy、锁文件、RAGFlow 管理脚本、ShellCheck 和 `git diff --check` 全部通过
- 真实边界：官方 RAGFlow `v0.25.6` 运行在独立 `common-agent-dev` Colima profile / `colima-common-agent-dev` Docker context（12 CPU、48GiB、100GiB 容器磁盘），正式版本端点 `http://127.0.0.1:19380/api/v1/system/version` 返回 `v0.25.6`；测试经正式 HTTP 入口自动注册/登录 loopback 账号、生成 API Token，再由平台适配器完成知识库创建/列表、中文文档上传/解析、唯一暗号语义检索和知识库删除，Token 未写入项目文件、测试快照或日志
- 资源：RAGFlow API、MySQL、MinIO、Valkey、Elasticsearch 和 Hugging Face 官方 TEI 六容器全部健康；采样占用分别约 3.80GiB、427MiB、122MiB、12MiB、1.71GiB、21.62GiB，证明原共享 32GiB 环境余量不足，48GiB 独立 profile 的选择合理；`BAAI/bge-m3` 约 4GB 权重通过宿主机只读挂载复用
- 失败矩阵：覆盖未配置、版本漂移、网络/超时/5xx、401/403/请求拒绝、知识库不存在、非法/跨库响应、空检索、文档状态映射、明确上传失败和上传结果未知；基础设施覆盖官方版本/提交漂移、模型缺失、公开绑定、非法/冲突端口、独立 context 和资源上限；真实启动实际经历 Docker Hub EOF/TLS/令牌过期、共享 30GiB 内容分区不足和多架构清单缺层，均在不影响其他项目的前提下恢复
- 清理：真实生命周期在 `finally` 删除唯一测试知识库；删除约 3GB 临时镜像层、临时下载脚本、空下载目录和早期探针遗留 Docker CLI；确认默认 context 无容器引用后删除本任务重复 RAGFlow 镜像与无效 Valkey 清单；保留专用 context 内六容器、正式镜像、Volume 和本地模型作为后续任务稳定开发栈，避免重复构建/拉取
- 文档：`.env.example`、`CLAUDE.md`、`infra/ragflow/README.md`、正式 RAGFlow Compose/管理脚本、异步适配器及单元/真实集成测试、`docs/development-roadmap.md`
- 遗留：按用户确认先完成 B1-05，把平台自有元数据从 SQLite 正式切到独立 MySQL；之后 K2-04 才把本适配器接入 FastAPI/OpenAPI 知识库接口

### B1-05 平台 MySQL 正式切换

- 状态：✅ 已完成
- 日期：2026-07-19
- 提交：本任务提交（见 Git 历史）
- RED：数据库配置测试先出现 5 failed、9 passed，证明默认 SQLite、非 MySQL URL 放行和密码 repr 泄漏；平台基础设施门禁先因正式管理脚本缺失失败；真实数据库测试在 asyncmy/MySQL 尚未接入时出现 3 failed、1 passed；容器停止/恢复验收进一步真实复现 macOS bind mount 下 `binlog.index` 权限错误与 Compose 假性健康，新增门禁分别因缺少稳定健康等待、关闭本机 binlog 和隔离测试库而失败
- GREEN：数据库/正式 Uvicorn 定向测试 11 passed，MySQL 配置定向测试 19 passed；后端全量 `uv run --frozen pytest -q` 77 passed、1 个需显式真实 RAGFlow 环境的测试按设计 skipped；`ruff check .`、`ruff format --check .`、`mypy src tests`、`uv lock --check`、OpenAPI/前端 DTO 漂移检查、平台/RAGFlow 管理脚本门禁、Shellcheck 和 `git diff --check` 全部通过
- 真实边界：官方 `mysql:8.4.10` 运行在独立 `colima-common-agent-dev` context、`common-agent-platform-dev` Compose project、`common-agent-platform-mysql` 容器、`127.0.0.1:19506` 和专属 Volume；正式 `uv run --frozen python -m common_agent` 经 FastAPI lifespan、Database、Alembic、SQLAlchemy async、asyncmy 连接 `common_agent`，MySQL 正常时真实 HTTP Health 成功，容器停止时 Uvicorn 以非零状态拒绝启动，恢复稳定健康后同一入口再次成功
- 失败矩阵：覆盖非 `mysql+asyncmy`、远程 host、缺少连接字段、配置/运行时密码脱敏、端口未监听、认证失败、非法 migration revision 闭合失败与修复恢复、唯一冲突、事务异常回滚、非法/占用端口、loopback/名称/Volume/2GiB 资源隔离、macOS bind mount 重启抖动和健康状态稳定等待；本机无复制/时间点恢复需求，关闭 binary log 规避 `binlog.index` 权限同步，InnoDB redo/undo 保留
- 数据隔离：平台管理入口幂等准备 `common_agent_test`；pytest 和测试 Uvicorn 只写该测试库，临时表均以唯一名称创建并在 `finally` 删除，不污染 `common_agent` 开发/演示数据；正式手工验收仍使用默认 `common_agent`
- 清理：两轮正式 Uvicorn 均已停止并释放 18200；未创建自建/任务镜像或重复 MySQL 镜像；确认无容器引用后删除独立 context 内约 3.69GB 悬空镜像；保留单一官方 MySQL 容器、数据 Volume 和 RAGFlow 稳定栈供后续任务复用
- 文档：`.env.example`、根/后端 README、`CLAUDE.md`、后端/工程架构、平台基础设施说明和 `docs/development-roadmap.md`
- 遗留：B1-03 记录保留当时 SQLite 基线的历史事实；从本任务起平台正式运行和后续 Repository 只以 MySQL 验收，下一步 K2-04 接入知识库 FastAPI/OpenAPI

### K2-04 知识库 API

- 状态：✅ 已完成
- 日期：2026-07-19
- 提交：本任务提交（见 Git 历史）
- RED：正式 Uvicorn 分层测试先从 `/api/v1/knowledge-bases` 得到 404，证明公开路由不存在；版本漂移用例先错误得到 200，证明业务请求未阻断不匹配 RAGFlow；OpenAPI 测试捕获创建/文档接口的 422 仍声明 FastAPI 默认 `HTTPValidationError`；RAGFlow 配置测试进一步以 3 failed、4 passed 捕获缺端口、非法端口和 URL 内嵌凭据被放行
- GREEN：知识库正式 HTTP 分层测试 6 passed，配置/知识契约/上传应用服务定向测试 44 passed，UploadFile 关闭测试 1 passed；启用真实 RAGFlow 后后端全量 `uv run --frozen pytest -q` 106 passed；Ruff、格式、Mypy、uv 锁文件、OpenAPI/前端 DTO 漂移、前端 11 项测试/Lint/类型/Build/peer、平台/RAGFlow 基础设施和 Shellcheck 门禁全部通过
- 真实边界：正式 Uvicorn 随机 loopback 端口经 FastAPI 路由、`KnowledgeBaseService`、`RagFlowKnowledgeService` 和官方 RAGFlow `v0.25.6` 完成真实知识库创建、列表、TXT multipart 上传、触发解析及轮询到 `completed`；MySQL 使用隔离 `common_agent_test`，真实 RAGFlow API Token 只存在于验收进程环境且未写入仓库/输出；与 K2-03 适配器生命周期合并执行 2 passed in 8.92s
- 失败矩阵：覆盖知识库名空白/长度、multipart 缺文件、空文件、扩展名/MIME 不匹配、20 MiB 超限、知识库不存在、RAGFlow 未配置/不可达/版本漂移、上游详情脱敏、固定错误信封与 Request ID；RAGFlow Base URL 强制 loopback、显式有效端口、无 URL 凭据/路径/查询，超时限制为 0-300 秒
- 资源与契约：上传按 1 MiB 分块读取到上限后一字节，所有终态在 `finally` 关闭 FastAPI `UploadFile`；只允许 TXT、Markdown、PDF、DOCX；Pydantic 是 OpenAPI 唯一来源，知识库/文档/解析枚举和 multipart DTO 已生成到前端，422 与运行时一致使用 `ErrorEnvelope`
- 清理：两个真实生命周期均在 `finally` 删除唯一测试知识库；所有分层假 RAGFlow 服务器、Uvicorn 和 HTTP 客户端由上下文关闭；18200/18280 无监听，前端 dist 与 tsbuildinfo 已删除；保留平台 MySQL 与 RAGFlow 六服务稳定栈供 K2-05/K2-06 复用
- 文档：后端 README、后端架构、OpenAPI 快照、前端生成 DTO、依赖锁文件和 `docs/development-roadmap.md`
- 遗留：K2-04 只交付 API，不提前实现页面；K2-05 通过正式 Axios/Query/Zod 接入这些接口，K2-06 再用 Playwright 完成浏览器生产同路径验收

### K2-05 知识库页面

- 状态：✅ 已完成
- 日期：2026-07-19
- 提交：本任务提交（见 Git 历史）
- RED：先新增知识库 API/Zod 边界与页面交互测试，定向 Vitest 因 `./knowledge` 和 `./KnowledgeBasesPage` 不存在出现 2 个失败套件；最小实现后继续真实捕获图标污染按钮可访问名称、jsdom 缺少 `matchMedia`/`ResizeObserver`、TanStack Query mutation 透传上下文和 Ant Design 6 弃用 API，均修正后进入 GREEN
- GREEN：知识库 API、页面与 App 路由定向测试 12 passed；前端全量 `pnpm test` 18 passed，ESLint、TypeScript、Vite Build 和 peer 门禁全部通过；知识库页面采用路由级 lazy import，构建由原单入口拆为入口、知识库和共享依赖 chunk，仍保留 653 KiB 共享 chunk 警告而未调高阈值掩盖
- 真实边界：`agent-browser` 从 `http://127.0.0.1:18280/knowledge-bases` 经正式 Vite、Axios、FastAPI、`KnowledgeBaseService`、RAGFlow 适配器和官方 RAGFlow v0.25.6 创建唯一通用知识库，上传 162 B TXT，页面轮询后显示 1 个文档和真实“已完成”；网络记录仅访问平台 `/api/v1/knowledge-bases`，创建 201、上传 202，前端未直连 RAGFlow；桌面视口 LCP 528 ms、CLS 0，页面异常为空
- 失败矩阵：组件/边界测试覆盖空状态、严格响应漂移、创建、multipart、`uploaded/parsing/completed/failed`、失败错误码、安全列表错误和同 Query 重试；真实浏览器中停止 FastAPI 后刷新显示“后端不可用 / 无法连接后端服务 / 重试加载”，恢复正式 API 后点击重试重新显示同一知识库和完成文档
- 通用性：页面与 API 只使用知识库名称、描述、文档和解析状态等平台通用字段，不包含行业、自动化任务或其他业务模型；所有第三方访问都封装在后端正式适配层
- 清理：按唯一 ID 删除浏览器验收知识库并经平台正式列表确认 `[]`；关闭 agent-browser 会话，停止临时 FastAPI/Vite；浏览器截图与报告仅保存在 `/tmp/common-agent-k2-05-qa`，不进入 Git；平台 MySQL 与 RAGFlow 六服务稳定栈保留供 K2-06 复用
- 文档：前端 README、知识库 API/Feature/样式/测试和 `docs/development-roadmap.md`
- 遗留：K2-06 增加可重复 Playwright 正式关键路径；共享依赖 chunk 的现有体积提示保留，后续页面增多后依据真实加载剖面细分稳定 vendor，而不是提前制造大量小 chunk

### K2-06 知识库 Playwright

- 状态：✅ 已完成
- 日期：2026-07-19
- 提交：本任务提交（见 Git 历史）
- RED：安装并锁定 `@playwright/test` 1.61.1 后先写正式浏览器规范，直接运行因尚无 Base URL/服务编排而以 `Cannot navigate to invalid URL` 失败，证明测试依赖真实入口；首轮真实运行进一步证明损坏 PDF 在 180 秒内保持 parsing，第二轮又捕获上传已落库但启动解析结果未知的正式幂等边界，没有把两种真实结果改写成假成功
- GREEN：`pnpm test:e2e` 经唯一正式脚本运行 Playwright Chromium，最终 1 passed in 10.1s；最终全量回归先捕获 Vitest 误收集 `e2e/*.spec.ts` 并显式隔离执行器，之后前端 18 项 Vitest、Playwright TypeScript/ESLint、脚本 Bash/Shellcheck、Python 清理/故障注入助手 Ruff/Mypy 全部通过；项目依赖冻结于 pnpm lock，入口按锁定版本复用或一次性安装 Chromium，不依赖全局 Node 包
- 真实边界：脚本复用健康的 `colima-common-agent-dev` MySQL/RAGFlow 稳定栈，不重新构建业务镜像；在隔离 `common_agent_test` 启动正式 FastAPI 与 Vite，Chromium 从 `/knowledge-bases` 创建唯一知识库，确认 POST 201，上传 156 B TXT 确认 202 并等待真实 completed，刷新页面后知识库和文档仍存在；随后上传约 2 MiB 合法 TXT，测试进程通过 RAGFlow v0.25.6 官方 DELETE chunks 入口做真实取消解析故障注入，页面经正式平台 GET 轮询显示“解析失败”和 `document_parsing_failed`
- 失败矩阵：覆盖缺少 E2E Base URL、项目端口占用、服务 60 秒未就绪、上传结果未知、长时间 parsing、真实 CANCEL→failed 状态、前端直连 RAGFlow 检测、测试/清理失败非零退出；Playwright 禁止 `.only`、单 Worker、无重试，失败保留截图/Trace/前后端日志，成功删除本轮产物
- 安全与通用性：RAGFlow Token 只存在于验收进程环境，不进入浏览器、前端变量、命令参数、日志、Trace 或仓库；知识库名称/描述/文档均为通用平台内容，无行业或 automation-tool 业务字段；故障注入只属于测试支持，不进入产品 API
- 清理：三轮运行均按唯一名称删除各 1 个真实 RAGFlow 知识库并停止 FastAPI/Vite/Chromium；最终成功后清除本轮产物，并精确删除前两轮已失去用途的失败 Trace/截图；18200/18280 释放，无悬空任务镜像，平台 MySQL 与 RAGFlow 六服务稳定栈保留复用
- 文档：Playwright 配置/规范与通用夹具、正式运行脚本、测试支持、frontend/scripts README、pnpm lock 和 `docs/development-roadmap.md`
- 遗留：无；Wave 2 纵向闭环完成，下一任务按 Roadmap 进入 E3-01

### E3-01 Employee 领域与迁移

- 状态：✅ 已完成
- 日期：2026-07-19
- 提交：本任务提交（见 Git 历史）
- RED：先建立 Employee 领域和正式仓储集成测试，定向 pytest 因 `common_agent.domain.employee` 与 `common_agent.adapters.persistence.employees` 不存在出现 2 个收集错误；最小实现首次进入真实 MySQL 后又捕获普通 `DATETIME` 丢失微秒，以及 MySQL 8.4 CHECK 失败由 asyncmy 映射为 `OperationalError` 的真实驱动差异，随后改用 `DATETIME(6)` 和共同数据库错误边界
- GREEN：Employee/数据库定向测试 27 passed；启用真实 RAGFlow 后后端全量 127 passed；Ruff、格式、Mypy、uv lock、真实 MySQL `alembic check`、前端 18 项 Vitest/Lint/类型/Build/peer、OpenAPI/DTO 漂移、平台/RAGFlow 管理规则和 ShellCheck 全部通过
- 真实使用路径：在专属 18200 端口两次运行正式 `uv run python -m common_agent`；第一次经 FastAPI lifespan、`Database`、Alembic、SQLAlchemy async 与 asyncmy 把正式 `common_agent` 从 `20260719_0001` 升级到 `20260719_0002`，第二次从已迁移状态无损重启，两次均由独立 curl 经真实 loopback Health 得到 200；实际 `SHOW CREATE TABLE employees` 确认 JSON、`DATETIME(6)` 及七项 CHECK 已落在 MySQL。E3-01 没有对外员工接口，仓储直测仅作分层定位；其用户/API 正式调用链由紧接的 E3-02 通过真实 Uvicorn 入口验收
- 模型与通用性：不可变 `Employee` 只包含 UUID、名称、说明、系统指令、可选知识库 ID、独立工作流 allowlist 和 UTC 时间，不包含行业、业务任务、automation-tool 或第三方 SDK 类型；名称 128、说明 1000、系统指令 12000、知识库 ID 128 的单一领域常量被 ORM 复用，迁移作为不可变历史快照固化相同约束
- 引用完整性：MySQL 只保存 RAGFlow 数据集的不透明 ID，不直连 RAGFlow 内部数据库也不建跨服务外键；E3-02 的 `EmployeeService` 必须通过正式 `KnowledgeService` fail closed 校验创建/修改绑定，已绑定知识库后来失效时不得静默退化为无知识回答；工作流定义保持独立，allowlist 在 Wave 5 前保持空数组
- 失败矩阵：覆盖空白/超长/错误类型字段、非 UUID/重复工作流引用、非 UTC/逆序时间、重复主键、事务异常回滚、不存在记录、MySQL 直接非法写入、迁移 revision 损坏后关闭失败与修复恢复、迁移/应用重启；RAGFlow 失效绑定、模型配置和工作流越权分别由 E3-02、A4-02 与 W5-07 的正式入口完成
- 清理：精确删除首次失败留下的 4 条隔离测试记录并给所有仓储用例增加 `finally` 清理；最终 `common_agent_test.employees=0`、正式 `common_agent.employees=0`，RAGFlow 的 K2-03/K2-04/K2-06 测试知识库列表为空；两次 Uvicorn 均已停止，18200/18280 无监听，删除前端 dist/tsbuildinfo，无悬空镜像；保留健康的项目 MySQL 和 RAGFlow 稳定栈复用
- 文档：后端 README、后端架构、Employee 领域/仓储/ORM/Alembic/测试和 `docs/development-roadmap.md`；`product-scope.md` 未作进度性修改
- 遗留：E3-02 通过正式 API 串起 `EmployeeService -> EmployeeRepository -> MySQL`，并经真实 `KnowledgeService -> RAGFlow` 验证有效/失效知识库绑定；本任务不提前实现路由或页面

### E3-02 数字员工 API

- 状态：✅ 已完成
- 日期：2026-07-19
- 提交：本任务提交（见 Git 历史）
- RED：EmployeeService/契约测试先因 `EmployeeConfiguration` 不存在而收集失败；独立启动真实 Uvicorn/MySQL 后 POST `/api/v1/employees` 得到 404，证明正式入口缺失；实现中新增“缺失员工优先于知识库校验”用例，先真实得到 `KnowledgeBaseNotFound` 而不是预期的 `EmployeeNotFound`，随后调整为先确认员工、事务外校验外围引用、再在新事务内重读更新
- GREEN：Employee/知识适配/正式 HTTP/OpenAPI 定向测试 50 passed；启用官方 RAGFlow 后后端全量 138 passed；Ruff、格式、Mypy、uv lock、真实 MySQL Alembic 漂移、前端 18 项 Vitest/Lint/类型/Build/peer、OpenAPI/生成 DTO 逐字节漂移、平台/RAGFlow 管理规则、ShellCheck 和补丁格式全部通过
- 真实用户/API 路径：正式 Uvicorn、`EmployeeService`、`EmployeeUnitOfWorkFactory`、SQLAlchemy Repository 和隔离 MySQL 完成 POST 创建、GET 列表/详情、PUT 更新，并在 Uvicorn 进程重启后由同一 GET 恢复；随后通过官方 RAGFlow v0.25.6 创建唯一真实数据集，正式员工 POST 先经 Health 与官方 GET dataset detail 校验再提交 MySQL，真实列表/详情返回绑定，第二个 Uvicorn 进程仍恢复同一绑定
- 真实失效绑定：对不存在的 RAGFlow 数据集分别执行员工 POST 和已有员工 PUT，正式 API 都返回 404 `knowledge_base_not_found`；失败更新后再次 GET 证明知识库 ID、说明和系统指令均未被覆盖，失败创建未出现在正式列表。无 Key 返回 503 `configuration_missing`，loopback 连接拒绝返回可重试 503 `knowledge_service_unavailable`，两者均经列表确认未写库
- API 与事务：公开 `/api/v1/employees` GET/POST 和 `/{employee_id}` GET/PUT；Pydantic/OpenAPI 复用领域长度常量且拒绝额外字段，工作流 allowlist 只读返回空数组并在 Wave 5 前不允许客户端写入；创建在外围校验成功后才开启事务，更新先确认员工存在、事务外校验引用、再在新 Unit of Work 内重读并原子提交，外部网络等待不占用数据库事务
- 通用性与隔离：请求/响应只含名称、说明、系统指令、知识库引用、能力 allowlist 和平台时间，不含行业、任务中心或 automation-tool 业务字段；平台只调用 RAGFlow 官方 API，不接触其内部 MySQL/Redis/MinIO/Elasticsearch；测试 Fake 只用于 EmployeeService 分层定位，不计入完成验收
- 失败矩阵：覆盖空白/超长/额外字段、客户端越权写工作流 allowlist、非法 UUID、员工不存在 GET/PUT、缺失员工不触发外围调用、知识库缺配置/不可达/不存在、失效更新不覆盖、RAGFlow 版本/上游错误公共映射、事务回滚和 Uvicorn/MySQL 重启恢复；模型配置与工作流越权不属于 CRUD，在 A4-02/W5-07 真实入口验收
- 契约：FastAPI/Pydantic 仍为唯一来源，新增 Employee 请求/响应和四个 operation 后重新生成 `contracts/openapi/openapi.json` 与前端 `schema.d.ts`，隔离重建逐字节一致；原知识库错误转换被提升为共享 API 映射，知识库 HTTP 回归保持通过
- 清理：所有员工 ID 在 `finally` 通过隔离测试支持精确删除，唯一 RAGFlow 数据集通过官方 DELETE 清理；最终正式/测试 `employees` 均为 0、`common-agent-e3-02-*` 数据集列表为空，18200/18280 无监听，删除 dist/tsbuildinfo，无悬空镜像；健康 MySQL 与 RAGFlow 稳定栈继续保留复用
- 文档：后端 README、后端架构、正式 Employee API/应用服务/UoW、KnowledgeService detail 契约、OpenAPI/前端生成 DTO、测试支持和 `docs/development-roadmap.md`；`product-scope.md` 未作进度性修改
- 遗留：E3-03 通过同一 `EmployeeService`/Repository 幂等写入可编辑的预置知识助理；E3-04 再从正式 React 页面消费本 API，E3-05 负责浏览器纵向验收

### E3-03 预置知识助理 Seed

- 状态：✅ 已完成
- 日期：2026-07-19
- 提交：本任务提交（见 Git 历史）
- RED：Seed 单元和正式启动测试先因 `common_agent.employees.seeds` 不存在出现 2 个收集错误；顺序路径转绿后再新增双 Uvicorn 并发启动测试，先因正式测试支持缺少 `running_apis` 再次收集失败，随后扩展同一 Uvicorn 启停/就绪工具而未复制进程编排代码
- GREEN：Seed 定向 4 passed；启用官方 RAGFlow 后后端全量 142 passed；Ruff、格式、Mypy、uv lock、真实 MySQL Alembic 漂移、前端 18 项 Vitest/Lint/类型/Build/peer、OpenAPI/DTO 漂移、平台/RAGFlow 管理规则、ShellCheck 和补丁格式全部通过
- 真实用户路径：隔离测试库中第一次正式 Uvicorn 启动自动创建固定 UUID 知识助理，经正式 GET 验证；用户再经正式 PUT 修改名称、说明和系统指令，第二个 Uvicorn 进程启动后同一 GET 返回全部用户修改且 `created_at` 不变，列表中固定 ID 恰好一次。另同时启动两个正式 Uvicorn 指向同一 MySQL，两个进程均成功就绪且都只看到同一固定 ID
- 正式开发数据：在项目固定 `127.0.0.1:18200` 两次运行 `uv run python -m common_agent` 并访问真实 `/api/v1/employees`；两次响应都只有 UUID `6f3d43e0-6f6d-5a67-9f25-756a0b9ed2ab` 的“知识助理”，字段和微秒级创建时间完全一致；MySQL 直接只读核对 count=1/min=max=固定 ID。该记录是后续页面与会话使用的正式 Demo 数据，按规则保留而非当测试残留删除
- 幂等与可编辑性：默认配置不绑定知识库或工作流，只包含通用名称、说明和安全系统指令；`EmployeeService.ensure` 先读取已存在记录并原样返回，不覆盖用户修改。缺失时在校验后进入新 Unit of Work 二次读取再创建，固定主键阻止重复；并发冲突经正式 `EmployeeAlreadyExists` 边界回滚后重读胜出记录
- 资源与故障：lifespan 在数据库启动后把知识适配器、EmployeeService、Seed 和 ready 状态纳入同一 `try/finally`，Seed 失败时仍关闭 RAGFlow 客户端和数据库连接；覆盖顺序重复启动、用户编辑保留、固定 ID 唯一和双进程竞争。Seed 默认无外围引用，因此 RAGFlow 未配置不会阻断 App 启动，也不会伪造绑定
- 清理：并发/编辑测试均在 `finally` 精确删除固定测试 ID；最终 `common_agent_test.employees=0`，正式 `common_agent.employees=1` 且仅为保留 Demo Seed；全量回归知识库前缀列表为空，18200/18280 无监听，删除 dist/tsbuildinfo，无悬空镜像；稳定 MySQL 与 RAGFlow 栈继续运行复用
- 文档：后端 README、后端架构、通用 Seed/ensure/lifespan、并发 Uvicorn 测试支持和 `docs/development-roadmap.md`；`product-scope.md` 未作进度性修改
- 遗留：E3-04 在数字员工页面展示这条预置记录并允许继续编辑/绑定真实知识库；E3-05 由 Playwright 验证刷新恢复和进入对话

### E3-04 数字员工页面

- 状态：✅ 已完成
- 日期：2026-07-19
- 提交：本任务提交（见 Git 历史）
- RED：先新增 Employee API/Zod 边界、页面和 App 路由测试，定向 Vitest 因 `./employees` 与 `./EmployeesPage` 不存在出现 2 个失败套件；真实 Chrome 在 1280×720 视口进一步捕获编辑弹窗底部操作按钮被截断，随后增加短视口布局契约，测试先因 Modal body 缺少高度与滚动约束而失败
- GREEN：Employee API、页面与 App 路由定向测试 13 passed，短视口回归由 RED 转为 GREEN；前端全量 `pnpm test` 27 passed，ESLint、TypeScript、Vite Build、peer 与冻结安装门禁全部通过；启用官方 RAGFlow 后后端全量 142 passed，Ruff、格式、Mypy、uv lock、OpenAPI/DTO 漂移、平台/RAGFlow 管理脚本和 ShellCheck 门禁全部通过
- 真实用户路径：`agent-browser` 从 `http://127.0.0.1:18280/employees` 经正式 Vite、Axios、FastAPI、`EmployeeService`、SQLAlchemy Repository 与 MySQL 展示预置知识助理；再通过知识库正式页面和 RAGFlow v0.25.6 创建唯一知识库，在数字员工页面创建并绑定员工、刷新恢复、编辑说明并保持绑定，最后点击“开始对话”进入 `/chat?employee_id=<真实 UUID>`
- 真实失败与恢复：停止 FastAPI 后刷新，页面显示“后端不可用 / 数字员工加载失败 / 无法连接后端服务 / 重试加载”；恢复正式 API 后员工列表可重试恢复。知识库请求单独失败时员工卡片和编辑入口仍可用，页面明确标记知识库不可用并提供独立重试，恢复后重新显示真实知识库名称；浏览器未直连 19380，控制台无错误
- 页面与边界：列表、创建/编辑共用严格 Employee DTO，UUID 和 UTC 时间先过 Zod；员工与知识库使用独立 Query，绑定可选且失效引用不静默伪装正常；Modal body 在短视口内滚动并保持操作按钮可达；字段仅含名称、说明、系统指令、可选知识库和只读能力，无行业或 automation-tool 业务耦合
- 失败矩阵：覆盖员工/知识库列表失败与分别重试、严格响应漂移、创建/编辑、绑定保留、知识库不可用、失效绑定展示、后端断开与恢复、短视口可达性和正式聊天路由；模型、Deep Agents 与工作流尚未进入本任务调用链，分别留在 A4/W5 任务验收
- 性能与证据：真实桌面浏览器 TTFB 1.2 ms、FCP 80 ms、LCP 416 ms、CLS 约 0.0009；问题报告、修复前后截图和视频保留在 `/tmp/common-agent-e3-04-qa` 作为人工探索证据，不进入仓库，E3-05 再固化为可重复 Playwright 纵向验收
- 清理：精确删除本轮真实员工和唯一 RAGFlow 知识库；隔离测试库固定 Seed 残留按主键删除，最终 `common_agent_test.employees=0`，正式库仅保留固定 UUID 预置知识助理；RAGFlow 相关测试前缀为 0，临时 FastAPI/Vite/浏览器均停止，18200/18280 无监听，dist/tsbuildinfo 已删除，无悬空镜像；健康 MySQL 与 RAGFlow 稳定栈继续运行复用
- 文档：前端 README、Employee API/Feature/样式/测试和 `docs/development-roadmap.md`；按用户纠正的产品边界，从 `product-scope.md` 与本路线图移除尚未实现且不适用于当前 Web 中台的桌面 App 自动更新规划
- 遗留：E3-05 把创建员工、绑定知识库、刷新恢复和进入对话固化为正式 Playwright 入口；聊天页面当前仍是 Wave 1 壳层，连续会话由 A4-01 至 A4-09 依次实现

### E3-05 数字员工 Playwright

- 状态：✅ 已完成
- 日期：2026-07-19
- 提交：本任务提交（见 Git 历史）
- RED：新增数字员工 Playwright 规范后，现有知识库专用 `pnpm test:e2e` 正式入口因缺少 `COMMON_AGENT_E2E_EMPLOYEE_NAME` 明确失败，证明进程/数据编排尚未覆盖 E3-05；泛化入口后真实 Chromium 又先后捕获 Ant Design 虚拟 option 的 ARIA 节点不可见、Select 的只读 input 不承载已选文字，两次都保留截图/Trace 定位，再改为点击与断言真实可见标题节点
- GREEN：锁定无窗口 `chromium-headless-shell` 后，`pnpm test:e2e` 在单 Worker、零重试下 2 passed in 14.0s，同时保留 K2-06 知识库回归；前端 Vitest 27 passed，ESLint、TypeScript、Build、peer、冻结锁文件通过；启用官方 RAGFlow 后后端 142 passed，Ruff、格式、Mypy、uv lock、真实 MySQL Alembic、OpenAPI/DTO、平台/RAGFlow 管理与 ShellCheck 门禁全部通过；构建仍如实报告既有 622.12 KiB 共享 chunk 提示
- 正式用户链路：在隔离 `common_agent_test` 启动正式 FastAPI/Vite，Playwright 从知识库页面经平台 API/RAGFlow v0.25.6 创建唯一知识库，再由侧栏进入数字员工页面，创建唯一员工并通过 POST 201 绑定；页面刷新后仍显示员工、真实知识库名与说明，打开编辑弹窗确认绑定，PUT 200 更新说明后再次刷新恢复，最后点击该员工“开始对话”进入 `/chat?employee_id=<真实 UUID>` 并显示 AI 会话入口
- 请求与安全边界：浏览器监听全程确认无 19380 直连，RAGFlow Token 只存在于后端/E2E 编排进程环境；所有测试名称和文案均为平台通用内容，无行业或 automation-tool 业务字段。聊天页面当前仅验收正式入口与员工参数，消息发送、模型和检索不在 E3-05 冒充完成
- 失败矩阵：入口覆盖 E2E 唯一变量缺失、18200/18280 占用、MySQL/RAGFlow 健康恢复、服务 60 秒未就绪、创建响应状态、刷新恢复、知识绑定保留、编辑持久化、错误聊天参数、浏览器直连 RAGFlow、清理失败非零退出和失败产物保留；员工/知识库服务不可用与分别恢复已由 E3-04 真实浏览器验收及组件回归覆盖
- 无打扰浏览器：按用户要求在 `CLAUDE.md` 固化所有自动化浏览器只使用无窗口模式；Playwright 配置同时强制 `headless: true` 与 `channel: chromium-headless-shell`，安装入口也只检查 headless shell。最终运行后 OS 进程核对无 Playwright/headless-shell/Vite/Uvicorn 残留
- 通用编排与清理：知识库专用脚本升级为 `test-platform-e2e.sh`，统一复用稳定 MySQL/RAGFlow，不构建业务镜像；脚本记录本轮 Playwright/Vite/FastAPI PID 并在成功、失败或中断时由 trap 回收，随后通过测试支持按唯一员工名称、固定 Seed UUID 和两个唯一知识库名称清理。最终测试库员工 0、E3-05/K2-06 RAGFlow 前缀 0、正式库仍只有固定预置知识助理、18200/18280 空闲、无浏览器或悬空镜像
- 文档：项目浏览器/清理规则、Playwright 配置与 Employee 规范、通用平台 E2E/清理支持、frontend/scripts README 和 `docs/development-roadmap.md`
- 遗留：无；Wave 3 完成，下一任务按 Roadmap 进入 A4-01 会话/消息/Citation 领域与正式持久化

### A4-01 会话/消息领域与迁移

- 状态：✅ 已完成
- 日期：2026-07-20
- 提交：本任务提交（见 Git 历史）
- RED：先新增 Conversation/Message/Citation 领域、正式 Repository 和迁移恢复测试，定向 pytest 因 `common_agent.domain.conversation` 与 `common_agent.adapters.persistence.conversations` 不存在出现 2 个收集错误；最小持久化首次进入真实 MySQL 后又以 2 failed 捕获 ORM 在无关系映射时先 flush 引用、触发 `fk_message_citations_message_id`，随后保持外键开启并在同一事务中显式先 flush 消息行
- GREEN：会话领域/仓储/数据库定向 38 passed，最终启用官方 RAGFlow 的后端全量 175 passed；Ruff、格式、Mypy、uv lock、正式/测试 MySQL Alembic 漂移、前端 27 项 Vitest/ESLint/TypeScript/Build/peer/冻结锁文件、OpenAPI/DTO、平台/RAGFlow 管理脚本和 ShellCheck 全部通过；前端构建仍如实保留既有 622.12 KiB 共享 chunk 提示
- 正式持久化路径：在专属 18200 端口两次运行正式 `uv run --frozen python -m common_agent`；第一次经 FastAPI lifespan、Database、Alembic、SQLAlchemy async 与 asyncmy 把正式 `common_agent` 从 `20260719_0002` 升级到 `20260719_0003`，真实 loopback Health 返回 200，第二次从已迁移状态无损重启并再次返回 200。实际 `SHOW CREATE TABLE messages` 确认外键、会话内唯一序号、角色/终态/CHECK 与 `MEDIUMTEXT` 已落入 MySQL
- 重启恢复：正式 Repository 在隔离 MySQL 中原子写入员工、会话、用户消息及带引用的完成助手消息，关闭首个 Database engine 后由全新 engine 读取，Conversation、按序 Message 与 Citation 逐字段一致；A4-01 没有公开会话接口，该 Repository/真实 MySQL 证据只证明内部持久化任务，用户生产入口仍由 A4-06 通过正式 HTTP/SSE 补齐，不用下层测试冒充跨端完成
- 领域状态：用户消息创建即为 `completed`；助手消息从 `pending` 开始，首个 delta 进入 `streaming`，只允许进入 `completed/failed/stopped` 终态，终态拒绝晚到 delta。完成内容非空，失败必须有安全错误码，停止不伪造失败；引用只属于完成助手消息，位置必须从 1 连续递增，知识库/切片/文档引用、片段和 0-1 有限分数均有长度/类型边界
- 持久化结构：`conversations` 以正式外键引用 `employees`；`messages` 以 `(conversation_id, sequence_number)` 唯一约束形成权威历史顺序；`message_citations` 用 `(message_id, position)` 复合主键。消息/引用随会话子记录级联，员工删除被会话外键拒绝；Repository 更新只覆盖标题或消息运行态，不允许迁移员工/会话归属、序号、角色与创建时间；复核实际 DDL 后移除被唯一约束完全覆盖的重复普通索引
- 失败矩阵：覆盖空白/超长/错误类型、非 UUID、非 UTC/逆序时间、非法角色与角色/状态组合、空完成内容、错误码语义、非法/不连续引用、终态晚到内容、重复会话 ID、重复消息 ID、同会话重复序号、事务回滚、直接非法 MySQL 状态/分数、缺失员工/会话/消息外键、Repository/Unit of Work 生命周期、迁移损坏恢复和正式/测试库元数据漂移
- 清理：所有仓储测试在 `finally` 按会话→员工顺序精确清理；新增仅作用于 `_test` 数据库的集成测试 session finalizer，修复既有正式启动测试反复留下固定 Seed 的问题。最终正式/测试库 revision 均为 `0003`，`common_agent_test` 的员工/会话/消息/引用均为 0，正式库三张会话表为 0 且仅保留固定预置知识助理；18200/18280 空闲，无 Playwright/headless-shell/Vite/Uvicorn 或悬空镜像，稳定 MySQL/RAGFlow 栈继续复用
- 文档：后端 README、后端架构、Conversation/Message/Citation 领域、正式端口/UoW/Repository、MySQL 迁移、领域/集成/清理测试和 `docs/development-roadmap.md`；`product-scope.md` 未作进度性修改
- 遗留：A4-02 接入阿里百炼流式模型端口；A4-03 定义 EmployeeRuntime 与平台事件；公开会话 CRUD/发送/停止/重试和 SSE 统一留在 A4-06，未提前扩大本任务

### A4-02 百炼模型适配器

- 状态：✅ 已完成
- 日期：2026-07-20
- 提交：本任务提交（见 Git 历史）
- RED：先新增 ModelSettings 运行参数、稳定模型错误、正式 `ChatOpenAI` 流式适配器和真实百炼验收测试，定向 pytest 因 `common_agent.models` 与 `langchain_core`/`langchain-openai` 均不存在出现 3 个收集错误；新增环境变量覆盖与显式客户端释放分别先得到 `60 != 45` 和缺少 `aclose` 的独立失败，再进入最小实现
- GREEN：模型配置/契约/适配器失败矩阵 29 passed，真实百炼 1 passed；启用正式 MySQL、官方 RAGFlow 与真实百炼的后端全量 200 passed；Ruff、格式、Mypy、uv lock、前端 27 项 Vitest/ESLint/TypeScript/Build/peer/冻结锁文件、OpenAPI/DTO、平台/RAGFlow 管理脚本和 ShellCheck 全部通过。前端构建继续如实报告既有 622.12 KiB 共享 chunk 提示
- 正式百炼路径：`ModelSettings.from_demo_file -> BailianChatModelAdapter -> langchain-openai 1.3.5 ChatOpenAI -> openai 2.46.0 -> 百炼业务空间 OpenAI-compatible /chat/completions` 真实发送系统消息和用户消息，经增量流返回并组合出唯一验收标记 `COMMON_AGENT_A4_02_OK`；同一正式适配器随后用无效 Key 请求真实百炼并收到认证失败，平台只返回安全 `configuration_missing` 语义，未输出真实 Key、无效 Key 或上游响应体
- 流式与复用：`stream_text` 只投影文本增量，忽略结束/元数据空块，完整成功流若没有非空文本则关闭失败；`chat_model` 暴露同一正式 `BaseChatModel` 实例供 A4-04 注入 Deep Agents，不另建第二套供应商客户端。适配器提供幂等 `aclose`，关闭自有同步/异步 OpenAI HTTP 客户端；注入的异步客户端仍由注入方管理
- 配置边界：锁定 `langchain-openai==1.3.5`、`langchain-core==1.4.9` 与 `openai==2.46.0`；Base URL 只允许百炼官方 `compatible-mode/v1` HTTPS 主机且拒绝 URL 凭据、非 443 端口、查询和片段。总请求/逐块超时默认 60 秒且最大 300 秒，SDK 重试默认 2 次且最大 3 次，三项均可由环境变量覆盖；Key 继续只存在于获准的私有 `.env.demo` 并使用 `SecretStr`
- 失败矩阵：OpenAI-compatible 故障注入覆盖真实请求路径与 Bearer/消息结构、两次 503 后第三次成功、429/503 耗尽后恰好停止、400 不重试、连接读取超时、异步逐块超时、401、首个 delta 后断流、空成功流和客户端幂等释放；错误投影覆盖配置无效、请求拒绝、服务不可用、响应非法和流中断，全部不携带供应商 detail 或 Key。第一次断流夹具错误地提前发送 `[DONE]` 时按正常完成暴露夹具缺陷并已修正；全量测试还捕获两个非包目录下同名 `test_contract.py` 的收集冲突并改为唯一文件名
- 生产同路径边界：A4-02 的交付对象就是内部百炼适配器，因此真实百炼请求通过该正式入口而不是直接调用 OpenAI SDK；当前尚无公开发送消息接口，Deep Agents、会话持久化编排和用户 HTTP/SSE 路径分别由 A4-03 至 A4-06 补齐，不能用本任务的适配器验收冒充用户聊天功能完成
- 清理：真实请求不创建远端持久资源；所有自有模型 HTTP 客户端显式关闭，Demo Key 未打印。全量测试 finalizer 后测试库员工/会话/消息/引用为 0，RAGFlow K2/E3 测试知识库为 0；未启动浏览器、Vite 或 Uvicorn，18200/18280 空闲；前端 dist/tsbuildinfo 在提交前精确删除，无悬空镜像，健康 MySQL/RAGFlow 稳定栈继续复用
- 文档：`.env.example`、后端 README、后端架构、ModelSettings、模型稳定契约、百炼正式适配器、分层/真实集成测试、依赖锁和 `docs/development-roadmap.md`；`product-scope.md` 未作进度性修改
- 遗留：A4-03 建立 EmployeeRuntime 输入/事件/停止契约；A4-04 把本任务的 `chat_model` 注入官方 Deep Agents 并走真实数字员工模型路径；公开聊天入口仍由 A4-06/A4-07 验收

### A4-03 EmployeeRuntime 契约

- 状态：✅ 已完成
- 日期：2026-07-20
- 提交：本任务提交（见 Git 历史）
- RED：先新增聊天历史、系统指令、知识上下文、流式事件、EventEmitter、StopToken 与 `EmployeeRuntime` 协议测试，定向 pytest 因 `common_agent.runtimes` 不存在出现 1 个收集错误；最小实现后再增加敏感上下文 repr 安全测试，先真实看到系统指令/历史/知识正文和模型增量被完整打印的失败，再逐字段关闭 repr
- GREEN：A4-03 契约 26 passed；启用正式 MySQL、官方 RAGFlow 与真实百炼的后端全量 226 passed；Ruff、格式、Mypy、uv lock、前端 27 项 Vitest/ESLint/TypeScript/Build/peer/冻结锁文件、OpenAPI/DTO、平台/RAGFlow 管理脚本和 ShellCheck 全部通过。前端构建继续如实报告既有 622.12 KiB 共享 chunk 提示
- 聊天式接口：一次 `EmployeeRuntime.stream(request, stop=...)` 只负责在已有会话中回复当前用户消息；契约没有 `start/approve/reject/resume/get_artifacts` 等旧任务 API。请求分别携带会话/员工/助手占位消息身份、按权威序号严格递增且最后一条为当前用户的历史、员工系统指令、知识绑定/上下文和工作流 allowlist；助手序号必须紧跟当前用户消息，消息 ID、片段引用和工作流 ID 均不可重复
- 知识语义：`knowledge_base_id=None + 空上下文` 表示员工未绑定知识库；`knowledge_base_id=真实 ID + 空上下文` 表示已检索但零命中，两者不会混淆。非空片段必须全部来自当前绑定知识库；历史上限 100 条/400,000 字符，知识上限 20 段/120,000 字符，单条内容继续复用 Conversation/Citation/Employee 的领域长度常量
- 流式与停止：`RuntimeEventEmitter` 从 sequence 1 递增发出非空 delta，并只允许一个 `completed/failed/stopped` 终态；错误码只属于 failed，stopped 明确不是失败，终态后晚到 delta 或第二终态均拒绝。`RuntimeStopToken.request_stop()` 第一次返回 true、后续返回 false，并唤醒所有等待者；A4-04 必须把它与真实 Deep Agents 上游读取竞速，当前契约不假装已经停止第三方调用
- 安全与框架隔离：`common_agent.runtimes.base` 只导入标准库和平台领域，不导入 LangChain、Deep Agents、HTTP 或数据库；系统指令、历史正文、知识原文和模型增量均从 dataclass repr 排除。稳定 RuntimeEvent 不透出 Deep Agents/LangGraph 原始事件，A4-06 才映射为持久化后推送的 SSE 事件序列
- 失败矩阵：覆盖非 UUID/非正序号、空白/超长系统指令、空历史、最后一条非用户、历史倒序/重复序号/重复消息 ID、助手序号错位、历史数量/总字符上限、未绑定却带知识、跨库/重复/超量片段、重复/非法工作流 ID、各事件 payload 非法组合、空 delta、失败缺错误码、终态晚到事件、停止幂等与 waiter 唤醒，以及协议运行时确实不具备任务式方法
- 生产同路径边界：A4-03 的交付物是纯平台协议和不变量，没有外部服务或公开用户入口可旁路验收；测试通过运行时公开构造器、Emitter、StopToken 和 runtime-checkable Protocol。真实 Deep Agents + 百炼由 A4-04 走该协议验收，知识检索编排由 A4-05 补齐，用户 HTTP/SSE 正式路径仍由 A4-06/A4-07 验收，当前不把 Fake 协议实现冒充跨端完成
- 清理：本任务不创建数据库或远端持久资源；全量测试 finalizer 后测试库员工/会话/消息/引用为 0，RAGFlow K2/E3 测试知识库为 0。未启动浏览器、Vite 或 Uvicorn，18200/18280 空闲；前端 dist/tsbuildinfo 在提交前精确删除，无悬空镜像，健康 MySQL/RAGFlow 稳定栈继续复用
- 文档：后端 README、后端架构、框架无关 Runtime 请求/事件/停止协议、契约测试和 `docs/development-roadmap.md`；`product-scope.md` 未作进度性修改
- 遗留：A4-04 使用官方 `create_deep_agent` 实现该协议并验证真实百炼流式/停止/受控工具边界；A4-05 把正式 RAGFlow 检索结果映射为 RuntimeKnowledgeChunk 与最终 Citation

### A4-04 Deep Agents 适配器

- 状态：✅ 已完成
- 日期：2026-07-20
- 提交：本任务提交（见 Git 历史）
- RED：先新增工具白名单、官方 `create_deep_agent` 装配、平台事件投影、停止/取消、失败收敛和真实 Deep Agents + 百炼验收测试；初次定向 pytest 因 `common_agent.runtimes.deep_agents` 与正式 `deepagents` 依赖均不存在出现 3 个收集错误。复核“第三方类型不得越过适配层”后把正式入口归位到 `common_agent.adapters.agent.deep_agents`，再次因该适配层不存在得到 3 个收集错误；真实连续运行还稳定暴露两个百炼适配器共享 OpenAI 默认底层 HTTP client，关闭第一实例会令第二实例 `is_closed=True` 的独立失败测试
- GREEN：Deep Agents 工具/运行时分层 22 passed，连同百炼适配器失败矩阵共 34 passed；启用正式 MySQL、官方 RAGFlow、真实百炼和真实 Deep Agents 后后端全量 250 passed。Ruff、格式、Mypy、uv lock、正式/测试 MySQL Alembic 漂移、前端 27 项 Vitest/ESLint/TypeScript/Build/peer/冻结锁文件、OpenAPI/DTO、平台/RAGFlow 管理脚本与 ShellCheck 全部通过；前端构建继续如实保留既有 622.12 KiB 共享 chunk 提示
- 正式 Deep Agents 路径：`EmployeeRuntime.stream -> DeepAgentsEmployeeRuntime -> deepagents 0.6.12 create_deep_agent -> A4-02 同一 ChatOpenAI -> openai 2.46.0 -> 阿里百炼`。真实知识上下文携带唯一标记 `COMMON_AGENT_A4_04_OK` 并经 Deep Agents 增量事件返回；第二个独立正式运行时在首个真实模型 delta 后收到停止意图，最终只产生 `stopped` 而无 completed/failed；无效 Key 经同一路径只产生安全 `configuration_missing`，真实/无效 Key 与上游响应体均未输出
- 工具与权限：`DeepAgentToolRegistry` 只按本轮 `allowed_workflow_ids` 顺序解析已注册 `BaseTool`，空白名单不暴露平台工具，未知能力 ID fail closed；重复工具名以及 `write_todos/ls/read_file/write_file/edit_file/glob/grep/execute/task` 保留名在启动时拒绝。由于 0.6.12 即使 `subagents=[]` 也会默认加入通用子代理，适配器使用其公开 Harness Profile 显式禁用默认子代理并排除全部内置工具；官方 `create_deep_agent` + 正式 Tool Binding 测试确认模型最终只绑定允许的 `allowed_workflow`，没有 Shell、文件、Todo 或 task
- 后端与提示词安全：使用非 `SandboxBackendProtocol` 的临时 `StateBackend`，同时传入 `FilesystemPermission(read/write, /**, deny)`，能力边界由工具/后端强制执行而非依赖提示词。员工系统指令、平台安全约束和知识上下文分区构造，明确把知识片段视为不可信外部数据；原始 Deep Agents/LangGraph 消息、工具状态和异常不进入平台 RuntimeEvent
- 流式与生命周期：平台历史转换为 LangChain human/ai 消息，只有 AI 文本块投影为单调 delta；独立空白块缓存并合并到下一个有效文本，纯空输出收敛为 `model_response_invalid`。每次上游 `anext` 与 `RuntimeStopSignal.wait` 竞速；预停止不创建 Agent，首字前/首字后停止均取消读取、关闭异步迭代并只发一个 stopped，父协程取消原样上抛且仍释放上游。模型已出字后的异常统一为 `model_stream_interrupted`，认证/请求/服务错误由模型适配器翻译，未知构建/执行错误只返回 `deep_agent_execution_failed`
- 多会话修复：真实第二轮 Deep Agents 首字前连续复现 `APIConnectionError`，脱敏探针确认两个独立 `ChatOpenAI` 包装器共享同一个 OpenAI 默认 HTTP client；新增隔离 RED 后让每个 `BailianChatModelAdapter` 显式创建独立同步/异步 httpx client。关闭第一实例后第二实例保持 open，真实“正常回复→停止→无效 Key”三段验收随即通过；注入的异步测试 client 仍由注入方管理
- 失败矩阵：覆盖空/单个/多个 allowlist、未知能力、保留名/重复名、官方内置工具排除、非 Sandbox 后端和全路径文件 deny、历史/知识提示投影、未知事件忽略、独立空白块、空输出、模型安全错误、未知执行异常、首个 delta 后断流、预停止、首字前/首字后停止、父取消、上游关闭、客户端幂等关闭与跨实例隔离；工作流工具真实副作用尚未存在，留给 W5-07 经公开 WorkflowService 验收
- 生产同路径边界：A4-04 的交付对象是内部 `EmployeeRuntime` 正式适配器，因此真实验收从该稳定协议进入官方 Deep Agents、正式百炼适配器和真实百炼，而不是直接调用模型 SDK；A4-06 尚未提供公开消息 HTTP/SSE，A4-07 尚无聊天页面，本任务不启动 Playwright，也不把内部适配器证据冒充最终用户会话完成。知识片段由测试输入进入运行时只证明运行时投影，正式 RAGFlow 每消息检索与 Citation 映射由 A4-05 补齐
- 清理：真实模型调用不创建远端持久资源，所有运行时和自有模型 HTTP client 显式关闭。全量测试后正式库为固定预置员工 1/会话 0/消息 0/引用 0，测试库四类记录全为 0，RAGFlow `common-agent-k2/e3/a4` 测试知识库为 0；18200/18280 无监听，无 Playwright/headless-shell/Vite/Uvicorn 遗留，前端 dist/tsbuildinfo 已精确删除，无悬空镜像；健康平台 MySQL 与 RAGFlow 六服务按稳定栈规则继续复用
- 文档：后端 README、后端架构、工程结构、Deep Agents/百炼正式适配层、运行时/模型端口、依赖锁、分层/真实测试和 `docs/development-roadmap.md`；`product-scope.md` 未作进度性修改
- 遗留：A4-05 通过正式 `KnowledgeService` 在每条消息前检索员工绑定知识库并映射 RuntimeKnowledgeChunk/Citation；A4-06 再把运行时接入会话持久化、发送/停止/重试和持久化后 SSE，W5-07 才注册真实工作流工具

### A4-05 自动知识检索

- 状态：✅ 已完成
- 日期：2026-07-20
- 提交：本任务提交（见 Git 历史）
- RED：先新增未绑定跳过、已绑定每条消息检索、空命中语义、运行时片段/Citation 同源映射、已知/未知失败 fail closed、非法上游片段、调用方取消和正式 RAGFlow 文档检索验收测试；定向 pytest 因 `common_agent.knowledge.retrieval` 不存在出现 2 个收集错误。最小实现后复核真实适配器发现 `RagFlowKnowledgeService.retrieve` 不会自行校验版本，新增 `KnowledgeBaseService.retrieve` 和会话前置健康/版本门禁测试，分别以方法不存在及 3 个状态未被检查得到 4 failed，避免用 Fake 直接抛版本错误掩盖正式旁路
- GREEN：知识服务/会话检索定向 24 passed，知识/Runtime 相关回归 61 passed，正式 RAGFlow 解析检索 1 passed；启用正式 MySQL、官方 RAGFlow、真实百炼和 Deep Agents 后后端全量 271 passed。Ruff、格式、Mypy、uv lock、正式/测试 MySQL Alembic 漂移、前端 27 项 Vitest/ESLint/TypeScript/Build/peer/冻结锁文件、OpenAPI/DTO、平台/RAGFlow 管理脚本与 ShellCheck 全部通过；前端构建继续如实保留既有 622.12 KiB 共享 chunk 提示
- 正式检索路径：测试通过正式 `ConversationKnowledgeResolver -> KnowledgeBaseService -> KnowledgeService -> RagFlowKnowledgeService -> RAGFlow v0.25.6` 创建唯一 `common-agent-a4-05-*` 知识库、上传真实 TXT、等待官方解析完成，再以当前用户消息检索唯一动态标记 `COMMON_AGENT_A4_05_*`；返回片段经正式 Resolver 映射后仍命中标记，RuntimeKnowledgeChunk 与 Citation 数量、片段 ID 和顺序逐项一致，finally 删除该知识库
- 每消息与空语义：Resolver 只接受领域层已完成用户消息。员工 `knowledge_base_id=None` 时直接返回 `None + 空片段/空引用`，不会调用 status 或 retrieve；已绑定时每次 resolve 都重新执行 status/version 与 retrieve，不缓存或复用上一问。零命中返回 `真实 knowledge_base_id + 空片段/空引用`，与未绑定明确区分，供 Deep Agents 提示“已检索但无结果”
- 健康与版本：在现有 `KnowledgeBaseService` 增加正式 retrieve 用例，复用同一个 `_ensure_available`；每条已绑定消息先核对 RAGFlow 的真实可用性和固定版本，再以 `top_k=5`、`similarity_threshold=0.2` 检索。未配置、服务不可用和 `knowledge_service_version_mismatch` 均在检索前失败，失效知识库、请求拒绝和供应商非法响应保持原稳定错误，不静默改成无知识上下文继续调用模型
- 引用映射：供应商顺序是唯一顺序；每个 RetrievedChunk 同源构造 RuntimeKnowledgeChunk 与从 1 连续编号的 Citation，知识库/片段/文档/正文/分数完全一致。重复片段 ID、超过 top_k 的返回、非法分数、超长正文或非平台结果统一转换为 `knowledge_service_invalid_response`；Citation 正文从 repr 排除，ResolvedKnowledgeContext 的片段/引用字段也整体不参与 repr
- 失败矩阵：覆盖未绑定零调用、连续两条消息各自检索、绑定零命中、未配置、版本不匹配、不可用、知识库不存在、请求拒绝、已知错误原样传播、未知异常安全收敛且不泄漏 detail、重复/超量/非法分数/超长片段、非用户消息前置拒绝和父协程取消原样上抛；RAGFlow 检索成功但随后模型失败由 A4-06 负责把助手消息写入 failed，当前 Resolver 不制造模型或持久化状态
- 生产同路径边界：A4-05 的交付对象是内部会话知识解析器，因此真实验收从该正式入口经过应用服务和正式 RAGFlow 适配器，不直接调用下层 HTTP 作为完成证据；公开发送消息 HTTP/SSE 与持久化编排尚在 A4-06，聊天页面在 A4-07，本任务不启动 Playwright，也不把内部解析器验收冒充最终用户自动检索闭环
- 清理：真实验收创建的唯一 A4-05 知识库和文档在 finally 精确删除；全量测试后正式库保持固定预置员工 1/会话 0/消息 0/引用 0，测试库四类记录全为 0，RAGFlow `common-agent-k2/e3/a4` 测试知识库为 0。18200/18280 无监听，无 Playwright/headless-shell/Vite/Uvicorn 遗留，前端 dist/tsbuildinfo 已精确删除，无悬空镜像；健康平台 MySQL 与 RAGFlow 六服务按稳定栈规则继续复用
- 文档：后端 README、后端架构、工程结构、会话知识解析器、KnowledgeBaseService 检索入口、Citation repr 安全、分层/真实测试和 `docs/development-roadmap.md`；`product-scope.md` 未作进度性修改
- 遗留：A4-06 把 Resolver、EmployeeRuntime、Conversation/Message Repository 接入公开会话 CRUD、发送/停止/重试与持久化后 SSE；A4-07 再通过正式聊天页面验收用户可见自动检索和引用

### A4-06 会话 API 与 SSE

- 状态：✅ 已完成
- 日期：2026-07-20
- 提交：本任务提交（见 Git 历史）
- RED：领域测试先以缺少 `Conversation.touch`/`Message.retry` 得到 3 failed；真实 MySQL 仓储测试以缺少全量会话和活跃消息查询得到 1 failed；事件总线与会话服务测试分别因 `common_agent.conversations.events/service` 不存在发生收集错误；OpenAPI 契约先因正式会话路径缺失失败，独立 SSE Schema 又以文件不存在失败，最后继续用 RED 捕获 OpenAPI 仍把事件载荷声明成无类型 string，逐层进入最小实现
- GREEN：Conversation 领域 24 passed，事件总线 3 passed，会话服务持久化/停止/重试/恢复/断流/乱序/晚到事件 6 passed，正式 HTTP CRUD/错误路径和真实 HTTP/SSE+百炼各 1 passed；最终后端全量 281 passed、7 个显式外部验收 skip，真实百炼适配器/Deep Agents/会话 API 串行 3 passed。Ruff、格式、Mypy、uv lock、OpenAPI/SSE/前端类型漂移、契约脚本 ShellCheck 全部通过；前端 27 项 Vitest、ESLint、TypeScript、Build、peer 与冻结锁文件通过，构建继续如实报告既有 622.12 KiB 共享 chunk 提示
- 正式用户链路：正式 Uvicorn 经 `/api/v1/conversations` 创建会话，POST 消息先写入真实 MySQL，再进入 `ConversationKnowledgeResolver -> DeepAgentsEmployeeRuntime -> deepagents 0.6.12 -> BailianChatModelAdapter -> 阿里百炼`；测试从正式 SSE 收到首个真实 delta 后调用正式 stop 得到 stopped，再调用正式 retry 复用同一助手消息并重新进入真实百炼直至 completed，最后从正式历史接口确认仍只有用户/助手两条消息。该员工未绑定知识库，因此本任务链路真实执行“未绑定零检索”分支；绑定知识库的 RAGFlow 生产链路由已完成 A4-05 和后续 A4-08/A4-09 覆盖，不伪造本任务证据
- 提交后发布：发送在同一 Conversation Unit of Work 中原子提交用户消息、助手占位和会话更新时间，提交完成后才发布 `assistant.started` 并创建后台运行；每个 delta/completed/failed/stopped 都重新读取当前消息、完成 MySQL 提交后再进入 EventBroker。终态立即停止消费上游，晚到事件不落库；断流和乱序分别收敛为安全 `runtime_stream_interrupted`/`runtime_response_invalid`
- 停止、重试与恢复：同会话只有一个活跃运行，第二次发送返回 `conversation_busy`；停止通过同一 `RuntimeStopToken` 传到 Deep Agents，最终 stopped 由运行时事件持久化。只有最后一条 failed/stopped 助手消息可重试，复用消息 ID/序号并清空残留内容和错误，不重复用户消息；lifespan 关闭先停止活跃运行并释放模型客户端，启动把遗留 pending/streaming 恢复成 `failed/generation_interrupted`
- API 与跨端契约：正式入口覆盖创建/列表/历史/发送/停止/重试和 SSE；客户端生成的用户 `message_id` 是重复提交边界。SSE 使用 `schema_version=1`、会话/消息/turn ID、会话内单调 sequence、持久化消息快照和安全 delta，`id` 与 sequence 一致；支持 `after_sequence`/`Last-Event-ID`，历史淘汰或进程重启后返回 `event_history_unavailable` 并要求重载权威消息历史。Pydantic 同时生成 OpenAPI、`contracts/events/conversation-event.schema.json` 和前端 TypeScript 类型，隔离重建逐字节一致
- 失败矩阵：覆盖重复会话/用户消息、同会话并发、无活跃生成停止、非法重试、消息/会话不存在、空白/超长输入、事件回放断档、慢消费者关闭、运行时断流/乱序/错误终态、终态后晚到内容、停止后重试、停止与生成竞态和进程中断恢复；模型/RAGFlow 的认证、超时、版本和非法返回继续复用 A4-02/A4-04/A4-05 分层与真实验收
- 清理与资源：所有 HTTP/服务测试经 `finally` 和正式 lifespan 关闭 Uvicorn、Deep Agents、模型/RAGFlow HTTP 客户端并精确删除会话/员工；最终正式库为固定 Seed 1、会话/消息/引用 0，测试库四类记录全 0。18200/18280 无监听，未发现 Playwright/headless-shell/Uvicorn/Vite 残留；本任务未启动浏览器，前端 dist/tsbuildinfo 已精确删除，专属 Docker context 无悬空镜像，健康 MySQL/RAGFlow 稳定栈继续复用
- 文档：后端 README、后端架构、正式会话应用服务/API/SSE、事件与 OpenAPI 生成契约、分层/真实验收和 `docs/development-roadmap.md`；`product-scope.md` 未作进度性修改
- 遗留：A4-07 在聊天工作台消费本任务 API/SSE 并实现三栏会话、引用、停止、重试与刷新恢复；A4-08 用无头 Playwright 覆盖真实用户页面路径，A4-09 再完成绑定知识库的两轮 RAGFlow+Deep Agents+百炼验收

### A4-07 聊天工作台

- 状态：✅ 已完成
- 日期：2026-07-20
- 提交：本任务提交（见 Git 历史）
- RED：先新增会话 REST/SSE 客户端测试，因 `api/conversations` 不存在发生模块收集失败；再新增聊天页组件测试，因 `features/chat/ChatPage` 不存在发生模块收集失败。实现后继续增加“SSE 增量先到、HTTP 202 接受快照后到”的竞态用例，修正前真实回退为 pending 并丢失已显示内容。正式页面首次跑通 2/2 后，清理器因新增会话的员工外键保护真实失败，暴露出旧 E3-05 清理顺序不再覆盖会话链路
- GREEN：会话客户端 3 passed，聊天页 5 passed，前端最终全量 35 passed；TypeScript、ESLint、生产 Build、冻结 pnpm 锁文件、顶层依赖/peer、OpenAPI/SSE 生成漂移全部通过，构建如实保留既有 601.45 KiB 共享 chunk 提示。后端清理支持修正后 Ruff、格式、严格 Mypy 97 个源文件、uv lock 与全量 281 passed/7 个显式外部验收 skip 通过；最终无头 Playwright 2 passed in 33.3s，并在退出阶段成功删除 2 个唯一 RAGFlow 知识库及关联平台数据
- 正式用户链路：`chromium-headless-shell` 从正式知识库页面创建唯一 RAGFlow 知识库、上传真实 TXT 并等待解析 completed，再从正式数字员工页面创建并绑定员工、刷新确认后点击“开始对话”；聊天页从正式入口创建 MySQL 会话，发送要求引用知识库且持续输出的消息，经 Axios/FastAPI、`ConversationKnowledgeResolver -> RAGFlow v0.25.6 -> DeepAgentsEmployeeRuntime -> deepagents 0.6.12 -> BailianChatModelAdapter -> 阿里百炼` 收到 SSE 流式内容，用户点击停止得到 stopped，再点击重试至 completed，页面显示真实 `generic-knowledge.txt` 引用，整页刷新后回答与引用仍从正式历史接口恢复
- 页面与跨端边界：`/chat` 不再是任务式占位页，固定为会话列表、消息区和数字员工信息三栏；支持按员工过滤会话、新建/选择会话、Enter 发送与 Shift+Enter 换行、生成中状态、停止、失败/停止后重试、引用文档/片段/相关度、员工知识库绑定状态和系统指令。浏览器只调用平台 REST/SSE，不直接接触 RAGFlow、Deep Agents 或百炼；响应和事件以生成契约类型配合严格 Zod 做运行时拒绝，第三方凭据始终只在后端
- 事件顺序与恢复：原生 EventSource 消费五类命名事件并显式 close；会话内只接受严格递增 sequence，晚到/重复事件不覆盖新快照。消息以服务端持久化快照为权威，`updated_at` 与状态进度共同阻止较旧 HTTP pending 响应覆盖先到 SSE streaming/completed；会话列表刷新不重建当前 SSE 订阅。事件格式错误或连接中断显示明确警告并重新读取正式消息历史，URL 保留员工/会话 ID，刷新恢复当前会话
- 失败矩阵：分层覆盖未知事件版本/状态/额外敏感字段、格式错误 SSE、显式关闭、空会话、新建、发送、停止、重试、晚到和重复 sequence、SSE/HTTP 竞态及断线权威历史恢复；复用 A4-02 至 A4-06 对模型认证/超时/上游错误、RAGFlow 未配置/版本/空检索/失败、并发发送、重复提交、停止竞态和安全错误的正式与分层覆盖。正式页面额外验证浏览器未直连 RAGFlow、POST 201/202、真实解析终态、真实流式停止/重试/引用/刷新；后端不可用由统一系统状态和请求错误呈现，不静默回退到假回复
- 清理与资源：补齐“按唯一员工名查询会话并按引用→消息→会话→员工顺序删除”的 E2E 清理，先精确清掉首次失败留下的数据，再复跑确认脚本自动清理成功。最终正式库为固定 Seed 1、会话/消息/引用 0，`common_agent_test` 四类记录全 0，RAGFlow 的 K2-06/E3-05 测试前缀为 0；18200/18280 无监听，无 Playwright/headless-shell/Vite/Uvicorn 残留，无前端 dist/tsbuildinfo/E2E 产物或专属 Docker context 悬空镜像，健康 MySQL/RAGFlow 稳定栈继续运行复用
- 文档：同步聊天页使用与正式无头验收入口到前端 README，进度只写入唯一事实源 `docs/development-roadmap.md`；`docs/product-scope.md` 未作进度性修改，既有产品/前后端架构边界无变化
- 遗留：A4-08 用固定正式适配器补充可重复的两轮会话、检索引用、断流和重试核心 E2E；A4-09 再用真实 RAGFlow、Deep Agents 与阿里百炼完成两轮连续知识问答并验证上下文和引用

### A4-08 Demo 核心 E2E

- 状态：✅ 已完成
- 日期：2026-07-20
- 提交：本任务提交（见 Git 历史）
- RED：模式配置测试先因缺少 `IntegrationModeSettings` 收集失败，固定知识/运行时测试先因 `common_agent.adapters.demo` 不存在收集失败；健康响应加入模式字段后，前端严格 Zod 因额外 `integration_mode` 真实失败，系统状态组件也因仍显示“后端正常”而找不到“演示模式”。实现后核对 Vitest 发现数，发现新增徽标用例一度覆盖既有真实健康/不可用两项测试，随即恢复并合并为 real/demo/unavailable 三分支
- GREEN：固定知识适配器与运行时、模式配置及正式 Uvicorn 定向 43 passed；最终后端 Ruff、格式、严格 Mypy 102 个源文件、uv lock 与全量 286 passed/7 个显式真实外部验收 skip 通过。前端最终 10 个文件 36 passed，TypeScript、ESLint、生产 Build、冻结 pnpm 锁文件与 OpenAPI 生成漂移通过，构建如实保留既有 601.45 KiB 共享 chunk 提示；ShellCheck 通过。Demo 无头 Playwright 首次正式执行 1 passed in 5.7s，默认 real 平台回归 2 passed in 34.5s
- 正式 Demo 用户链路：`COMMON_AGENT_INTEGRATION_MODE=demo` 仍从正式 React 页面进入同一 FastAPI、MySQL、Employee/Conversation Service、REST/SSE 和持久化后事件链，只把 `KnowledgeService` 与 `EmployeeRuntime` 切换到正式代码内的确定性固定适配器；页面全程显示“演示模式”。用户从页面创建进程内 Demo 知识库并上传 TXT、创建绑定员工、新建 MySQL 会话，连续发送两轮消息并在每轮看到引用；第三轮固定运行时先发 delta 后断流，正式会话服务收敛为 `failed/runtime_stream_interrupted`，页面保留部分内容并允许重试，同一助手消息重试后 completed，刷新仍恢复三轮消息与引用
- 固定适配器语义：Demo 知识适配器实现与 RAGFlow 端口相同的状态、列表、详情、创建、上传、文档列表和检索协议，上传立即进入真实 `completed` Demo 状态，缺失知识库/重复名称使用既有平台错误；Demo 运行时消费正式历史/知识上下文、发出单调 `RuntimeEvent`、按用户消息数证明第二轮历史存在、对同一助手消息只在第一次触发断流，并保持停止与幂等关闭语义。Demo 模式即使收到非法 RAGFlow/百炼地址仍可经正式 Uvicorn 启动，证明没有偷偷构造外部客户端
- 显式隔离：健康契约新增生成字段 `integration_mode: real|demo`，前端严格解析；Demo 使用 warning 徽标和“固定适配器，不代表真实外部服务”提示，默认及未配置值始终为 `real`。浏览器不直连 19380 或百炼域名；Demo 知识数据只存在当前后端进程，员工/会话/消息/引用仍写隔离 MySQL，不建立第二套 API、状态或错误协议
- E2E 复用与清理：单一 `test-platform-e2e.sh` 通过显式 suite 分流；`platform` 只发现真实知识库/员工用例，`demo-chat` 只发现 Demo 聊天用例并不启动 RAGFlow，两者固定 `chromium-headless-shell`、端口预检、PID 关闭和精确数据清理。Demo 清理按引用→消息→会话→员工→固定 Seed 执行；最终正式库为 Seed 1、会话/消息/引用 0，测试库四类记录全 0，18200/18280 无监听，无浏览器/Vite/Uvicorn、E2E 产物、dist/tsbuildinfo 或悬空镜像，稳定 MySQL/RAGFlow 栈继续复用
- 真实门禁解除：本任务交付的是可重复 Demo 回归，不能以固定知识、固定文本或 Demo 运行时冒充真实 AI 能力，因此最初如实记为 `🔍 待验收` 且未提前提交。随后 A4-09 从正式页面以本机 RAGFlow、官方 Deep Agents 和阿里百炼完成两轮连续知识问答，第二轮原样返回上一轮真实知识标记、两轮均显示引用并刷新恢复，最终 real 套件 2 passed in 31.3s，解除本任务真实依赖门禁后才升级为 `✅ 已完成`
- 文档：根环境样例、后端/前端/scripts README、生成 OpenAPI/TypeScript 健康契约与唯一进度源；`docs/product-scope.md` 已经定义 Demo 边界，本任务未作进度性修改

### A4-09 真实会话验收

- 状态：✅ 已完成
- 日期：2026-07-20
- 提交：本任务提交（见 Git 历史）
- RED：先把默认 real Playwright 提升为两轮并要求原样回答唯一标记，真实页面第一轮已完成 RAGFlow 检索、Deep Agents/百炼回复和引用，但测试文档没有该标记，模型只自行描述“第一轮/第二轮验收”，`COMMON_AGENT_REAL_TWO_TURN_OK` 断言在 180 秒后真实失败；随后把唯一标记加入真实上传文档，第一轮和第二轮实际均已原样回答，刷新后也恢复第二轮，但测试在第二个助手气泡创建前让 `.last()` 短暂匹配第一轮并错误保存了第一轮长文本，最终持久化比较再次 RED。增加助手气泡由 1 变 2 的显式等待后，没有修改业务实现或降低断言
- GREEN：最终 real `chromium-headless-shell` 平台套件 2 passed in 31.3s；员工/聊天用例完整通过真实知识解析、停止、重试、两轮回答/引用和刷新恢复，知识库用例继续通过真实 completed/failed 解析状态。A4-09 只增强真实验收夹具和用户路径，没有修改生产会话代码；同一工作区后端全量 286 passed/7 个显式外部验收 skip，Ruff、格式、严格 Mypy 102 个源文件和 uv lock 通过，前端 10 个文件 36 passed、TypeScript、ESLint、Build、冻结锁文件、OpenAPI/SSE 漂移和 ShellCheck 通过；A4-08 Demo 套件 1 passed in 5.7s
- 正式两轮用户链路：无头 Chromium 从正式知识库页面创建唯一 RAGFlow 数据集并上传包含 `COMMON_AGENT_REAL_TWO_TURN_OK` 的真实 TXT，等待 RAGFlow v0.25.6 解析 completed；再从正式员工页面创建并绑定唯一数字员工、刷新/编辑确认后进入聊天页并新建 MySQL 会话。第一轮消息要求回答知识定义与标记并持续输出，页面观察真实 delta 后调用正式 stop 得到 stopped，再从页面 retry 复用同一助手消息，经 RAGFlow 检索、官方 Deep Agents 0.6.12 和阿里百炼完成且显示真实文档引用
- 上下文与逐轮检索：第二轮用户明确询问上一轮回答过的标记；正式会话服务向运行时传入第一轮用户/助手历史，同时按 A4-05 规则对第二条用户消息再次访问员工绑定的 RAGFlow 知识库。第二个独立助手气泡原样返回 `COMMON_AGENT_REAL_TWO_TURN_OK`，并再次显示 `generic-knowledge.txt` 引用；用例明确等待两个助手气泡，刷新整页后第二轮正文和最后一轮引用仍由 MySQL 权威历史恢复，证明不是单轮 DOM 残留或固定前端文本
- 生产同路径边界：浏览器只访问正式 React 与平台 API/SSE，没有对 19380 的浏览器直连；后端真实调用 `KnowledgeBaseService -> RagFlowKnowledgeService -> ConversationKnowledgeResolver -> ConversationService -> DeepAgentsEmployeeRuntime -> BailianChatModelAdapter`，没有 Demo、Mock、Fake、进程内客户端、直接下层函数或日志断言参与完成证据。百炼/RAGFlow 凭据只存在后端验收进程，唯一标记来自真实上传文档而不是提示词硬编码回答
- 失败矩阵与定位：真实覆盖文档缺少知识事实时模型不会凭空满足唯一断言、首轮长流停止/重试、两轮连续发送、每轮检索/引用、刷新恢复和浏览器禁止直连第三方；测试同步失败通过“期望第一轮长文、实际第二轮准确标记”的页面证据定位为 Locator 竞态，而非篡改业务状态。模型认证/超时/断流、RAGFlow 配置/版本/空检索/失败、并发/重复提交、事件乱序/晚到和安全错误继续由 A4-02 至 A4-08 的分层及正式测试覆盖
- 清理与资源：三次 real 运行均按唯一名称清理会话→员工和 RAGFlow 数据；两次 RED 日志/截图/Trace 在定位完成后精确删除。最终正式库固定 Seed 1、会话/消息/引用 0，测试库四类记录全 0，18200/18280 无监听，无 Playwright/headless-shell/Vite/Uvicorn、E2E 产物、dist/tsbuildinfo 或专属 context 悬空镜像；健康 MySQL/RAGFlow 稳定栈继续复用
- 门禁收口：真实两轮结果解除 A4-08 的 `🔍 待验收`，Wave 4 的会话领域、百炼、运行时、Deep Agents、每消息知识检索、REST/SSE、聊天页、可重复 Demo E2E 和真实外部依赖验收现均完成；没有把工作流或业务自动化并入数字员工普通对话
- 文档：只在唯一进度源记录真实 RED/GREEN、正式边界、清理与遗留；`docs/product-scope.md` 未作进度性修改

### W5-01 工作流 Schema 与校验

- 状态：✅ 已完成
- 日期：2026-07-20
- 提交：本任务提交（见 Git 历史）
- RED：先新增领域 Schema 与图校验测试并实际运行，两个测试文件均在收集阶段因 `common_agent.domain.workflow` 不存在而失败；随后最小实现首次运行 34 passed/1 failed，失败证明重新配置没有阻止更新时间倒退，补上相对当前版本的单调时间校验后进入 GREEN
- GREEN：定向工作流测试 35 passed；同一工作区后端全量 321 passed/7 个显式外部验收 skip，Ruff、107 个文件格式、严格 Mypy 55 个源文件和 uv lock 均通过
- 四类 Schema：不可变领域模型固定 `start`、`ai_chat`、`knowledge_retrieval`、`end` 四种类型，开始/结束使用空配置，AI 对话要求非空且有上限的提示词，知识检索要求非空且有上限的不透明知识库 ID；节点 `position` 与业务 `config` 分离，坐标必须是有限数值，节点类型与配置类型必须严格匹配，工作流定义保留 UUID、名称、说明、节点、边和 UTC 时间
- 图不变量：单次校验聚合返回稳定问题码与关联节点/边，覆盖节点/边数量上限、节点/边 ID 重复、缺少或多个开始、缺少结束、边端不存在、自环、重复连线、开始入边、结束出边、首版禁分支/并行、孤立节点、开始不可达、无法到达任一结束节点和环路；有效的“开始 → AI 对话 → 结束”正式生产 Schema 无问题通过
- 真实边界：本任务是无 HTTP、页面、持久化和外部副作用的内部生产组件，交付物是 W5-02/W5-03 将直接调用的领域构造器与 `validate_workflow_graph`/`ensure_workflow_graph_valid`，测试没有 Mock、Fake、进程内 HTTP 或第三方替身；工作流对外创建/校验入口及真实 MySQL 持久化属于 W5-02，不用本项低层测试提前冒充用户功能验收
- 失败矩阵：覆盖未知节点类型、类型/配置错配、空白/超长提示词、空白/超长知识库引用、非法/无限坐标、空白标识、字段类型、非 UTC/逆序时间及全部图结构非法项；知识库 ID 的真实存在性必须在 W5-02 正式保存/校验服务通过 `KnowledgeService` 验证，LangGraph 编译与运行步数/输入上限分别留给 W5-03/W5-04 的正式调用链
- 清理：本任务没有启动前端、Uvicorn、浏览器、数据库新实例或 Docker 容器，也没有构建镜像；测试生成的 Python 缓存按项目目录精确清理，项目临时前后端端口无监听，稳定 MySQL/RAGFlow 栈未重建或误删
- 文档：只更新唯一进度源中的任务状态、RED/GREEN、边界、失败矩阵和下一步；产品范围与架构决策未变化，未修改 `docs/product-scope.md`
- 遗留：无；真实外层能力按依赖进入 W5-02

### W5-02 工作流持久化与 API

- 状态：✅ 已完成
- 日期：2026-07-20
- 提交：本任务提交（见 Git 历史）
- RED：先建立应用服务、正式 MySQL 仓储、随机端口 Uvicorn API、OpenAPI 和真实 RAGFlow 验收测试，测试收集因 `common_agent.workflows.service` 与 `common_agent.adapters.persistence.workflows` 不存在而失败；最小实现后真实 MySQL 往返继续以 `mysql.DOUBLE` 解码为 `Decimal`、领域只接受有限 int/float 的正确边界失败，正式映射改为 `asdecimal=False` 后通过。全量测试还发现两个无关业务的测试基础问题并直接收正：工作流与知识模块同名 `test_service.py` 缺少包隔离，以及旧迁移 revision 断言仍停在 `20260719_0003`；OpenAPI 定向测试最初误以为判别联合内联在数组项，检查正式生成结果确认它被抽为 `WorkflowNodeBody` 组件后修正测试，未改变生产协议
- GREEN：工作流应用服务与受影响员工服务 23 passed，正式 MySQL 迁移/仓储 14 passed，随机端口正式 Uvicorn 工作流 API 4 passed，应用层移动后的服务/API/OpenAPI 19 passed；最终后端全量 342 passed/8 个显式外部验收 skip，Ruff、125 个文件格式、严格 Mypy 61 个源文件和 uv lock 通过。前端 10 个文件 36 passed，TypeScript、ESLint、Build、冻结锁文件通过；OpenAPI/会话事件/生成 TypeScript 漂移检查通过
- 正式持久化：新增不可变 Alembic `20260720_0004` 和正式 `workflows`、`workflow_nodes`、`workflow_edges` 三表；节点顺序、类型与画布 `position_x/position_y` 是独立列，按节点类型判别的业务配置只存在单独 JSON 对象，边以同一 `workflow_id` 下的复合外键引用真实节点。定义/节点/边在同一个 Workflow Unit of Work 原子新增或整体替换，列表用三次查询批量装配图，不用 N+1；公共 UTC/MySQL 时间转换从员工/会话重复私有函数收敛成唯一适配器工具并通过原仓储回归
- API 与事务：公开 `/api/v1/workflows` GET/POST、`/{workflow_id}` GET/PUT 和 `/validate` POST；Pydantic/OpenAPI 用 `type` 判别四类节点并拒绝额外字段，校验入口返回完整稳定问题码且不写库。创建先校验后开启事务；更新先确认定义存在、事务外完成图与知识引用校验，再在新事务重读并原子替换，RAGFlow 网络等待不占 MySQL 事务。`WorkflowService` 按基线位于 `application/`，`workflows/` 只保留图校验并供下一步编译器复用
- 生产同路径边界：专属真实用例从随机 loopback 端口访问运行中的正式 Uvicorn/FastAPI，经正式 `WorkflowService`、SQLAlchemy 仓储和 `common_agent_test` MySQL，创建真实 RAGFlow v0.25.6 数据集后用知识检索节点调用 `/validate` 与创建接口；有效引用通过并落库，随机失效引用返回 `knowledge_base_not_found` 图问题，API 重启后从 MySQL 恢复相同知识库 ID 和节点配置。全程没有 TestClient、ASGI 进程内客户端、Mock/Fake、直接仓储调用或日志断言参与完成证据；当前尚无工作流正式页面，设计器用户入口属于 W5-05，不能用未来页面作为本 API 任务的前置门禁
- 失败矩阵：覆盖未知节点、类型/配置错配、开始/结束空配置额外字段、非法 UUID、定义不存在、逻辑非法图不落库、知识服务未配置/不可用、真实知识库存在/失效、校验不写库、重复身份、事务异常回滚、更新整体替换、MySQL 重启恢复、迁移损坏后关闭失败与修复恢复，以及数据库直接写入空白字段、未知节点类型和缺失边端外键；W5-01 的缺开始/结束、孤立、自环、重复边、环、不可达、超限和禁分支矩阵全部经同一正式应用服务复用。LangGraph 编译、运行输入/步数、节点失败、停止和运行摘要不属于持久化/API，分别进入 W5-03/W5-04
- 契约：FastAPI/Pydantic 仍是唯一来源，生成 OpenAPI 新增工作流 CRUD、校验响应、四类节点判别联合及配置上限，前端 `schema.d.ts` 由脚本生成，没有手写第二套 DTO；后端 README 同步正式表、API、事务和知识引用边界，产品范围未变化
- 清理：真实验收及所有失败路径均在 `finally` 删除唯一工作流和 RAGFlow 数据集；最终 `common_agent_test` revision 为 `20260720_0004`，工作流/节点/边均 0 条，RAGFlow `common-agent-w5-02-*` 数据集 0 个。18200/18280 无监听且无 Uvicorn、Vite、Playwright、浏览器残留；删除 dist、tsbuildinfo、pytest/Ruff/Python 缓存。本任务未构建镜像，连续运行约 9 小时的健康 MySQL/RAGFlow 稳定栈按规则继续复用，未重建、停止或误删
- 文档：更新后端运行说明、生成 OpenAPI/TypeScript 契约和唯一进度源；`docs/product-scope.md` 未作进度性修改，架构基线无变化
- 遗留：无；下一任务 W5-03 直接消费已验证并持久化的 `WorkflowDefinition`，不重复实现 API 或仓储

### W5-03 LangGraph 编译器

- 状态：✅ 已完成
- 日期：2026-07-20
- 提交：本任务提交（见 Git 历史）
- RED：先新增直接导入生产编译器并使用真实 `langgraph.graph.StateGraph` 的节点转换、顺序执行、二次校验、未注册节点、递归上限、编译异常安全映射和非法步数测试；实际执行在收集阶段按预期因 `common_agent.workflows.compiler` 不存在失败，确认不是通过既有实现或测试替身得到假绿
- GREEN：LangGraph 编译器定向 10 passed；真实 RAGFlow v0.25.6 + 阿里百炼编译执行链 1 passed；后端全量 352 passed/9 个需显式启用的外部验收 skip，Ruff、133 个文件格式和严格 Mypy 128 个源/测试文件通过；前端 10 个文件 36 passed，TypeScript、ESLint、Build、pnpm/uv 冻结锁与 OpenAPI/事件 Schema/生成 TypeScript 漂移检查全部通过
- 编译与隔离：直接锁定并使用 `langgraph==1.2.9` 公共 API；正式 `WorkflowDefinition` 在编译前再次通过平台图校验，平台节点 ID 映射到独立内部命名空间，LangGraph 虚拟 `START/END` 只连接平台开始/结束节点。节点注册表完整提供开始、AI 对话、知识检索和结束转换，运行结果保留原平台节点完成顺序、步数和最终文本；第三方 Runnable/状态类型只留在工作流内部边界，没有渗入领域、API 或持久化层
- 节点语义：开始节点把用户输入放入工作流上下文；知识节点通过正式 `KnowledgeBaseService` 按统一首版参数检索，并把片段校验后映射为受限运行时知识上下文；AI 节点通过正式 `StreamingChatModel` 流式收集结果，复用数字员工相同的知识片段不可信安全指令；结束节点优先返回上游输出，无上游输出时按知识或原始输入安全透传。AI 输出可成为后续知识检索查询，支持首版线性图的两种合法组合顺序
- 错误与上限：平台节点/边数量校验仍是第一道门，LangGraph 编译是第二道门；只允许 1 到 `MAX_WORKFLOW_NODES + 2` 的执行步数上限并传入公开 `recursion_limit`，真实 `GraphRecursionError` 映射为 `workflow_step_limit_exceeded`。未注册节点、编译失败和未知执行失败分别收敛为稳定错误，不回显 LangGraph 内部异常；模型与知识服务已有稳定错误保持原语义，不被笼统吞掉
- 生产同路径边界：W5-03 交付的是尚无独立 HTTP/页面入口的内部生产编译组件，真实验收直接调用其唯一正式入口 `WorkflowCompiler.compile(...).invoke(...)`，内部使用真实 LangGraph 编译产物，并依次进入正式 `RagFlowKnowledgeService`、本机 RAGFlow v0.25.6 文档解析/检索、正式 `BailianChatModelAdapter` 与阿里百炼，最终返回文档中的唯一随机标记和四个真实完成节点；没有 Mock/Fake、进程内 HTTP、第三方替身或日志断言参与完成证据。工作流对外手动运行入口、事件、停止与摘要属于 W5-04，设计器和用户页面属于 W5-05/W5-06，因此本任务不把直接组件验收冒充完整工作流用户功能验收
- 失败矩阵：覆盖平台非法图在构图前关闭失败、注册表缺节点、LangGraph 公共编译异常、真实递归上限、布尔/零/负数/超上限步数、模型空输出与模型/知识服务稳定异常边界、知识结果类型/数量/重复片段校验，并回归知识安全提示和检索默认参数单一来源。后端未启动、HTTP 重复运行、节点事件漂移、停止/晚到事件、运行摘要与结果不确定处理依赖 W5-04 的正式入口，不在内部编译器伪造测试入口
- 清理：真实验收创建的唯一 `common-agent-w5-03-*` RAGFlow 知识库和文档在 `finally` 精确删除，模型与知识 HTTP 客户端均显式关闭；本任务未启动浏览器、Vite、Uvicorn或构建 Docker 镜像，构建与测试临时产物在提交前清理，18200/18280 无监听。项目专属 MySQL/RAGFlow 稳定栈保持健康并继续复用，不重建、不停止、不删除仍有容器引用的基础镜像
- 文档：后端运行说明同步 LangGraph 正式边界、节点注册、错误与运行层职责；唯一进度源记录任务证据和下一步，产品边界未变化，未修改 `docs/product-scope.md`
- 遗留：无；下一任务 W5-04 直接装配编译器、工作流仓储和正式运行/事件 API，不重复实现节点执行

### W5-04 工作流运行与事件

- 状态：✅ 已完成
- 日期：2026-07-20
- 提交：本任务提交（见 Git 历史）
- RED：先新增运行领域、事件 Broker、应用服务、MySQL 仓储和随机端口正式 Uvicorn 测试，分别按预期以缺少 `common_agent.domain.workflow_run`、运行服务符号、持久化仓储和运行路由失败；新增 OpenAPI/工作流 SSE 契约测试后，正式快照按预期过期且 `workflow-run-event.schema.json` 不存在。首次对真实 MySQL 执行 `20260720_0005` 时还因 `trigger` 是 MySQL 保留字被 CHECK 约束拒绝，确认无半张表后在 ORM 与不可变迁移中统一引用该列再成功升级。最终全量首轮又发现旧 `test_system_http.py` 仍断言上一迁移头 `0004`，生产入口已实际迁移到 `0005`，修正基线后全绿
- GREEN：运行领域、事件、服务、编译、正式 MySQL 仓储与随机端口 Demo Uvicorn 相关回归 51 passed，OpenAPI 与双 SSE Schema 契约 9 passed；真实 RAGFlow v0.25.6 + LangGraph + 阿里百炼正式运行入口 1 passed in 8.86s。最终后端全量 371 passed/10 个需显式启用的外部验收 skip，Ruff 139 个文件、严格 Mypy 139 个源/测试文件与 uv lock 通过；前端 10 个文件 36 passed，ESLint、TypeScript、Build、pnpm 冻结锁和所有契约漂移门禁通过
- 运行模型与持久化：新增不可变 Alembic `20260720_0005` 和 `workflow_runs`，客户端 UUID 是重复提交幂等键，定义外键级联运行摘要；输入/输出上限、触发来源、五态状态机、当前/已完成/失败节点、稳定错误码与 UTC 时间同时受不可变领域模型、SQLAlchemy 映射和 MySQL CHECK 约束。运行仓储加入原 Workflow Unit of Work，不另开旁路事务；节点开始、节点完成和终态都先提交 MySQL 权威摘要再发布事件，编译结果节点顺序或步数与已提交摘要不一致时以 `workflow_run_result_invalid` 关闭失败
- 正式 API 与事件：公开 `POST /api/v1/workflows/{workflow_id}/runs`、`GET /api/v1/workflow-runs/{run_id}`、`POST /api/v1/workflow-runs/{run_id}/stop` 和 `GET /api/v1/workflow-runs/{run_id}/events`；手动运行返回 202 后在当前 FastAPI lifespan 内异步执行。工作流事件固定 `schema_version=1`，包含运行内单调序号、运行/工作流 ID、可选节点和已提交完整摘要，支持 `after_sequence`/`Last-Event-ID` 进程内回放；历史丢失或进程重启后以 GET MySQL 摘要为权威。通用 SSE resume 解析从会话路由收敛为公共 API 工具，OpenAPI、两类事件 JSON Schema 和前端生成 DTO 仍由单一 Pydantic 来源生成
- 停止、恢复与资源选择：编译节点执行与 `RuntimeStopToken` 竞速，停止胜出时取消当前节点任务且不伪造 completed；停止请求只设置协作意图，最终 stopped 由同一运行服务持久化。应用优雅关闭先停止活跃工作流再释放会话/共享模型客户端；启动时把遗留 pending/running 收敛为 `failed/workflow_run_interrupted`。当前调用方只有同进程交互式运行，没有跨进程调度、可靠投递或自动重试需求，因此首版不预建消息队列/Worker；该决定不限制后续真实需要时通过同一服务端口加入技术组件
- 生产同路径边界：专属验收从随机 loopback 端口访问运行中的正式 Uvicorn/FastAPI，先经平台知识库 API 在官方 RAGFlow v0.25.6 创建数据集、上传真实 TXT 并等待解析完成，再经工作流创建与运行 API 进入 `WorkflowService -> SQLAlchemy/MySQL -> WorkflowCompiler -> LangGraph -> RagFlowKnowledgeService -> RAGFlow -> BailianChatModelAdapter -> 阿里百炼`，最终摘要和 SSE 返回唯一动态标记及 start/retrieve/chat/end 四节点。随后经正式 stop 路由终止第二次真实运行，再通过 RAGFlow 官方删除入口让已保存引用失效，第三次正式运行以 retrieve 节点 `knowledge_base_not_found` 失败；重启正式 Uvicorn 后 GET 仍从 MySQL 恢复首个完成摘要。完成证据没有 TestClient、进程内 ASGI、Mock/Fake、直接函数或日志断言；W5-05/W5-06 尚未实现设计器/运行页面，因此本 API 任务不冒充浏览器用户功能验收
- 失败矩阵：覆盖空白/超长输入、非法 UUID、定义/运行不存在、重复运行 ID、非活跃运行停止、节点异常、模型失败、真实知识库失效、结果节点/步数不匹配、停止与晚到完成竞态、事件状态/节点快照不一致、断点历史淘汰、慢消费者溢出、事务回滚、数据库唯一冲突与非法状态直写、重启恢复、应用关闭协作停止和服务未装配；稳定错误只保存/返回平台码，不泄漏模型响应、知识正文、Key 或本机路径。Demo 随机端口 API 另验证完整事件序列、重复提交、停止和重启恢复，但只作为分层覆盖，不替代上述真实依赖验收
- 清理：所有 HTTP/服务测试通过正式 lifespan 与 `finally` 关闭 Uvicorn、模型/RAGFlow 客户端并级联删除工作流运行；最终 `common_agent_test` 工作流/节点/边/运行均为 0，RAGFlow `common-agent-w5-04-*` 前缀为 0。18200/18280 无监听，无 Uvicorn、Vite、Playwright 或 `chromium-headless-shell` 残留；本任务没有启动浏览器，前端 dist/tsbuildinfo 与 pytest/Ruff/Python 缓存已精确删除，专属 Docker context 无悬空镜像。健康 MySQL 与 RAGFlow 六服务稳定栈继续复用，未重建、停止或误删基础镜像
- 文档：后端运行说明、后端/工程架构、生成 OpenAPI/双事件 Schema/TypeScript 契约和唯一进度源已同步；产品功能与边界未变化，未修改 `docs/product-scope.md`
- 遗留：无；下一任务 W5-05 使用正式工作流 CRUD/校验 API 实现 React Flow 设计器，不把运行状态或 LangGraph 执行搬到前端

### W5-05 工作流设计器

- 状态：✅ 已完成
- 日期：2026-07-20
- 提交：本任务提交（见 Git 历史）
- RED：先新增工作流 API 解析/错误、受控编辑器状态和完整页面测试，首次定向执行因 `api/workflows`、`workflowEditor` 与 `WorkflowsPage` 三个生产模块均不存在而按预期收集失败；最小实现后页面测试又真实暴露 React Flow 的动态图节点无法稳定进入 JSDOM 可访问树，补上与画布共用同一 reducer 的键盘节点列表后 5 项页面行为通过。正式 Playwright 首轮用真实服务端消息修正过窄文案断言，逐节点门禁随后捕获空画布 `fitView` 放大到 1.8 倍造成节点/连接点遮挡，生产画布将首次适配上限收敛为 1 倍后真实鼠标三次连线全部成功；最后一次失败只因测试写请求计数漏匹配动态 PUT URL，功能创建、更新和两次刷新回显当时已全部成功，收正断言后最终复跑全绿
- GREEN：工作流 API 3、编辑器 reducer 3、页面 5 项定向测试通过；最终前端 13 个文件 47 passed，ESLint、TypeScript、生产 Build 与 pnpm 冻结锁通过。后端全量 371 passed/10 个需显式启用的外部验收 skip，Ruff lint、145 个非不可变迁移文件格式、严格 Mypy 140 个源/测试文件和 uv lock 通过；Shellcheck、OpenAPI/双事件 Schema/生成 TypeScript 契约漂移与 `git diff --check` 通过。专属无头 Chromium 生产同路径用例 1 passed in 4.7s，独立无头 `agent-browser` 抽查确认正式页面、节点面板、画布和键盘节点选择入口可操作
- 设计器与状态：前端精确锁定官方 `@xyflow/react` 12.11.2；四类节点使用单一受控 React Flow `nodes/edges` 与 reducer，拖拽、键盘点击添加、真实 Handle 连线、移动/删除节点、选择状态、脏状态、服务端问题定位和画布渲染不会形成多份图状态。节点位置与按类型判别的业务配置继续分离；开始/结束固定空配置，AI 节点编辑提示词，知识节点只保存平台知识库 ID；删除节点同步删除关联边，首版 UI 拒绝自环、重复连线、结束节点出边、开始节点入边和一对多分支，服务端仍是最终权威
- 保存与错误边界：页面只调用平台 `/api/v1/workflows`、`/validate` 和更新入口；每次保存先走正式服务端校验，有问题时展示完整消息并标记节点/边，绝不继续 POST/PUT。名称、AI 提示词和知识库选择提供即时本地反馈但不替代服务端图/引用校验；列表、创建和更新响应均按生成 DTO 之外再经严格 Zod 解析，网络/协议异常收敛为安全错误。切换或新建时对未保存修改显式确认，创建/更新成功后以服务端返回图替换草稿并刷新列表；W5-04 运行状态预留在独立投影，不混入设计器图状态
- 生产同路径边界：专属 `workflow-designer` 套件从无头 Chromium 用户入口访问正式 Vite 页面，经 Axios 平台适配层和正式 Uvicorn/FastAPI，先对空图调用 `/workflows/validate` 得到 `missing_start/missing_end` 且证明没有写请求；再从知识库页面经平台 API 在真实 RAGFlow v0.25.6 创建唯一数据集，回到设计器用真实 HTML 拖拽添加 start/retrieve/chat/end、真实鼠标连接三条边、选择真实知识库和编辑提示词。保存再次经服务端校验、`WorkflowService`、SQLAlchemy 与 `common_agent_test` MySQL 创建，刷新恢复四节点/三边/知识引用；随后通过同一页面 PUT 修改提示词并再次刷新恢复。浏览器网络观测证明从未直连 19380；完成证据没有 Mock/Fake、进程内客户端、直接仓储/函数、DOM 注入或日志断言
- 失败矩阵：覆盖空图服务端问题且不落库、空白名称、空白 AI 提示词、未选知识库、工作流列表加载失败与正式重试、协议响应漂移、重复/自环/非法端点/分支连接关闭、删节点同步删边、服务端节点/边问题定位、脏草稿切换保护、创建与更新顺序、刷新恢复、前端不直连 RAGFlow，以及真实缩放遮挡导致连接失败。Playwright 固定 `chromium-headless-shell`、15 秒动作上限、单 worker、失败截图/Trace 和显式 suite，低层单元/契约测试保留用于精确定位，不冒充分层外验收
- 编排与清理：`test-platform-e2e.sh` 新增独立 `workflow-designer` suite，只复用健康 MySQL/RAGFlow，不重建业务镜像；脚本为工作流和知识库生成唯一名称，记录 Playwright/Vite/FastAPI PID，并在成功、失败或中断时先关无头浏览器和前后端，再按名称级联删除 MySQL 图与 RAGFlow 数据集。最终测试库工作流/节点/边/运行均为 0，RAGFlow `common-agent-w5-05-*` 前缀为 0，18200/18280 无监听，无 Vite/Uvicorn/Playwright/Chromium/agent-browser 残留；六轮失败 Trace、dist、tsbuildinfo 和项目测试缓存已精确删除，未构建镜像，健康稳定基础设施继续复用
- 格式边界：后端全目录格式检查仅报告已应用且未由本任务修改的不可变迁移 `20260720_0005` 有一处等价字符串折叠建议；为保持迁移历史不可变，本任务没有改写它，改以精确排除该历史文件后验证其余 145 个文件全部已格式化，Ruff lint 与 Mypy 仍覆盖迁移相关代码
- 文档：只更新唯一进度源、E2E 脚本说明和调用脚本；产品范围没有变化，未修改 `docs/product-scope.md`
- 遗留：无；下一任务 W5-06 直接复用同一工作流详情和 W5-04 运行/事件 API，在设计器之外实现手动运行投影，不把执行状态写回图定义

## 15. 当前下一步

严格按顺序：

1. 完成 `W5-06`：实现输入、运行、节点高亮、失败和最终结果手动运行 UI；
2. 完成 `W5-07`：让数字员工只通过 allowlist 与同一个 `WorkflowService` 触发工作流；
3. 完成 `W5-08`：从真实浏览器完成创建图、手动运行、员工触发和刷新摘要的跨端验收。
