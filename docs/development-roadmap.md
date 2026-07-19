# 通用 Agent 中台任务级开发路线图

> 文档性质：项目开发进度唯一执行台账  
> 建立日期：2026-07-19  
> 当前阶段：Wave 2 RAGFlow 知识库闭环
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

快照日期：2026-07-19。

| 范围 | 当前结果 |
| --- | --- |
| 旧项目复盘 | `✅` 已审阅 `agent-platform` 规则/架构和 `automation-tool` 任务级路线图形式 |
| 项目拆分 | `✅` `common-agent` 只做 AI 中台；业务自动化留在 `automation-tool` |
| 产品交互 | `✅` 普通数字员工采用连续会话，不把每条消息变成任务 |
| 第一版范围 | `✅` AI 会话、数字员工、知识库、最小可视化工作流；无登录鉴权和 Skill |
| 模型 | `✅` 只直接接阿里百炼，复用旧私有仓库的 Demo Key，不引入模型网关 |
| 技术架构 | `✅` 技术方案不设白名单；SQLite 是初始持久化基线，任何技术组件都可按当前真实需要进入正式链路 |
| 开发环境 | `✅` 全部本机联调，不部署服务器；端口和 Docker 资源与其他项目隔离 |
| GitHub | `✅` `masterAventador/common-agent` 已创建为 PRIVATE，`main` 跟踪 `origin/main` |
| 项目规则/架构 | `✅` 主规则、产品边界、工程架构和任务级路线图已建立并校验 |
| 工程骨架 | `✅` frontend/backend/contracts/infra/scripts 已按目标边界建立，未混入临时 Sites 或空业务模块 |
| 后端入口 | `✅` FastAPI app factory、lifespan、请求 ID、统一错误和真实 loopback Health 已跑通 |
| 平台持久化 | `✅` SQLite 正式适配器、Alembic、async session、空库迁移、回滚和进程重启恢复已跑通 |
| 百炼配置 | `✅` 已从 agent-platform 的 Git 跟踪配置迁移 Demo 模型/Base URL/Key，Key 仅存在于获准的私有配置文件 |
| 前端入口 | `✅` React/Vite/Ant Design 四入口壳层已通过组件、构建和真实浏览器导航验收 |
| 跨端契约 | `✅` FastAPI OpenAPI、前端生成 DTO 和隔离漂移检查已形成单一来源闭环 |
| 前端 API | `✅` Axios、Query Client、Zod、CORS 与后端真实成功/失败状态已跨端跑通 |
| 产品代码 | `⬜` 尚未开始；等待后端、前端基础工具链完成后按纵向功能任务进入 |
| 本地服务 | `✅` 临时前端初始化预览已停止；后端/RAGFlow 未启动 |

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
| F1-02 | 初始化 Frontend | React/TypeScript/Vite/Ant Design/pnpm、四入口空壳和专属端口 | F1-01 | ✅ 已完成 |
| C1-01 | OpenAPI 契约闭环 | 后端导出、前端生成、漂移检查和公共错误 DTO | B1-02,F1-02 | ✅ 已完成 |
| F1-03 | 前端 API 基线 | Axios、Query Client、Zod 和后端真实状态提示 | C1-01 | ✅ 已完成 |

## 8. Wave 2：RAGFlow 知识库闭环

### 目标

先让用户在本机真正创建知识库、上传文档并看到解析结果。

| ID | 任务 | 交付物与完成定义 | 依赖 | 状态 |
| --- | --- | --- | --- | --- |
| K2-01 | 锁定 RAGFlow 版本与资源 | 确切稳定版本；固定 `common-agent-dev`、独立端口/Volume；评估 Docker 32GB 级资源和复用策略 | R0-06 | 🚧 实现中 |
| K2-02 | KnowledgeService 契约 | list/create/upload/list-documents/retrieve/status 平台协议和失败测试 | B1-02 | ⬜ 未开始 |
| K2-03 | RAGFlow 适配器 | 官方 SDK/API 接入、超时、错误转换、版本健康和真实服务验收 | K2-01,K2-02 | ⬜ 未开始 |
| K2-04 | 知识库 API | 列表、创建、文档上传、解析状态；上传大小/类型限制 | K2-03,C1-01 | ⬜ 未开始 |
| K2-05 | 知识库页面 | 创建、上传、真实状态、失败重试和空状态 | K2-04,F1-03 | ⬜ 未开始 |
| K2-06 | 知识库 Playwright | 浏览器完成创建→上传→解析完成/失败展示 | K2-05 | ⬜ 未开始 |

## 9. Wave 3：数字员工与知识库绑定

### 目标

创建可用于会话的数字员工，并稳定绑定一个 RAGFlow 知识库。

| ID | 任务 | 交付物与完成定义 | 依赖 | 状态 |
| --- | --- | --- | --- | --- |
| E3-01 | Employee 领域与迁移 | 模型、字段限制、正式持久化模型和知识库引用完整性策略 | B1-03,K2-02 | ⬜ 未开始 |
| E3-02 | 数字员工 API | 列表、详情、创建、编辑和知识库绑定；失效绑定明确拒绝 | E3-01,K2-03,C1-01 | ⬜ 未开始 |
| E3-03 | 预置知识助理 Seed | 幂等创建、可编辑、不制造重复记录 | E3-02 | ⬜ 未开始 |
| E3-04 | 数字员工页面 | 列表、创建/编辑表单、知识库选择和“开始对话” | E3-02,F1-03 | ⬜ 未开始 |
| E3-05 | 数字员工 Playwright | 创建员工→绑定知识库→刷新后仍存在→进入对话 | E3-04 | ⬜ 未开始 |

## 10. Wave 4：连续 AI 会话与自动检索

### 目标

完成最核心的“发一句、回一句、继续追问”闭环，并自动检索员工绑定知识库。

| ID | 任务 | 交付物与完成定义 | 依赖 | 状态 |
| --- | --- | --- | --- | --- |
| A4-01 | 会话/消息领域与迁移 | Conversation/Message/Citation、终态和正式持久化重启恢复 | B1-03,E3-01 | ⬜ 未开始 |
| A4-02 | 百炼模型适配器 | `ChatOpenAI`、流式输出、超时/有限重试和脱敏错误 | B1-04 | ⬜ 未开始 |
| A4-03 | EmployeeRuntime 契约 | 历史、系统指令、知识上下文、流式事件和停止语义 | A4-01,K2-02 | ⬜ 未开始 |
| A4-04 | Deep Agents 适配器 | 官方 `create_deep_agent`、受控工具、无 Shell/本机文件权限 | A4-02,A4-03 | ⬜ 未开始 |
| A4-05 | 自动知识检索 | 每条消息按员工绑定检索、空结果语义、引用映射和检索失败 fail closed | A4-03,K2-03,E3-02 | ⬜ 未开始 |
| A4-06 | 会话 API 与 SSE | 新建/列表/历史/发送/停止/重试；事件单调、持久化后推送 | A4-04,A4-05,C1-01 | ⬜ 未开始 |
| A4-07 | 聊天工作台 | 三栏会话、流式回复、引用、停止、重试和刷新恢复 | A4-06,F1-03 | ⬜ 未开始 |
| A4-08 | Demo 核心 E2E | 固定适配器完成两轮会话、检索引用、断流和重试 | A4-07 | ⬜ 未开始 |
| A4-09 | 真实会话验收 | 本机 RAGFlow + Deep Agents + 阿里百炼完成两轮知识问答并验证引用 | A4-08 | ⬜ 未开始 |

## 11. Wave 5：最小可视化工作流

### 目标

拖拽四类节点形成有效图，后端转换为 LangGraph 并支持手动/数字员工触发。

| ID | 任务 | 交付物与完成定义 | 依赖 | 状态 |
| --- | --- | --- | --- | --- |
| W5-01 | 工作流 Schema 与校验 | 四类节点、边、配置、图不变量和完整非法矩阵 | B1-03,K2-02,A4-02 | ⬜ 未开始 |
| W5-02 | 工作流持久化与 API | 正式仓储、列表/详情/创建/编辑/校验，位置与业务配置分离 | W5-01,C1-01 | ⬜ 未开始 |
| W5-03 | LangGraph 编译器 | 注册节点转换、StateGraph 编译、步数上限和错误映射 | W5-01,K2-03,A4-02 | ⬜ 未开始 |
| W5-04 | 工作流运行与事件 | 手动运行、节点事件、结果、失败和停止摘要 | W5-02,W5-03 | ⬜ 未开始 |
| W5-05 | 工作流设计器 | React Flow 拖拽/连线/配置/保存/服务端校验 | W5-02,F1-03 | ⬜ 未开始 |
| W5-06 | 手动运行 UI | 输入、运行、节点高亮、失败和最终结果 | W5-04,W5-05 | ⬜ 未开始 |
| W5-07 | 数字员工触发工具 | 只允许调用员工 allowlist 中工作流，共用 WorkflowService | W5-04,A4-04 | ⬜ 未开始 |
| W5-08 | 工作流 E2E | 创建图→保存→手动运行→员工触发→刷新查看摘要 | W5-06,W5-07 | ⬜ 未开始 |

## 12. Wave 6：MVP 收口

| ID | 任务 | 交付物与完成定义 | 依赖 | 状态 |
| --- | --- | --- | --- | --- |
| Q6-01 | 完整失败矩阵 | 第 5 节所有适用分支有自动化或明确真实证据 | A4-09,W5-08 | ⬜ 未开始 |
| Q6-02 | Docker 资源与清理验收 | 记录峰值/稳定内存、32GB 建议、端口隔离；证明稳定栈复用、按影响重建，并清理重复任务镜像和悬空层 | Q6-01 | ⬜ 未开始 |
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
- 工作流节点 Schema 和注册表。

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

## 15. 当前下一步

严格按顺序：

1. 完成 `K2-01`：锁定 RAGFlow 版本、端口、Volume 和 32GB 级资源策略；
2. 完成 `K2-02`：建立 KnowledgeService 平台契约与失败测试；
3. 完成 `K2-03`：接入正式 RAGFlow 适配器并验收真实服务。
