# 通用 Agent 中台任务级开发路线图

> 文档性质：项目开发进度唯一执行台账  
> 建立日期：2026-07-19  
> 当前阶段：MVP 已完成生产同路径验收；后续工程加固、资源优化与生产化任务已规划
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

快照日期：2026-07-21。

| 范围 | 当前结果 |
| --- | --- |
| 旧项目复盘 | `✅` 已审阅 `agent-platform` 规则/架构和 `automation-tool` 任务级路线图形式 |
| 项目拆分 | `✅` `common-agent` 只做 AI 中台；业务自动化留在 `automation-tool` |
| 产品交互 | `✅` 普通数字员工采用连续会话，不把每条消息变成任务 |
| 第一版范围 | `✅` MVP 历史基线为 AI 会话、数字员工、知识库、最小可视化工作流且无鉴权；S10-02 已在生产化阶段增加首位所有者与安全会话，Skill 仍未进入当前范围 |
| 模型 | `✅` 只直接接阿里百炼，继续复用私有仓库中明确获准的现有 Demo Key，不引入模型网关 |
| 技术架构 | `✅` 技术方案不设白名单；平台正式持久化已切换为独立 MySQL 8.4 LTS，其他技术组件可按当前真实需要进入正式链路 |
| 开发环境 | `✅` 全部本机联调，不部署服务器；端口和 Docker 资源与其他项目隔离 |
| GitHub | `✅` `masterAventador/common-agent` 已创建为 PRIVATE，`main` 跟踪 `origin/main` |
| 项目规则/架构 | `✅` 主规则、产品边界、工程架构和任务级路线图已建立并校验 |
| 工程骨架 | `✅` frontend/backend/contracts/infra/scripts 已按目标边界建立，未混入临时 Sites 或空业务模块 |
| 后端入口 | `✅` FastAPI app factory、lifespan、请求 ID、统一错误和真实 loopback Health 已跑通 |
| 平台持久化 | `✅` 独立 MySQL 8.4.10、aiomysql、PyMySQL >=1.1.1、SQLAlchemy async、Alembic、隔离测试库、事务回滚和容器/进程重启恢复已跑通；SQLite 不再是正式验收依赖 |
| 百炼配置 | `✅` 现有 Demo Key 按用户明确要求继续只在私有仓库指定文件版本化且不轮换；普通测试、日志、归档、构建产物和 Git 历史传播边界已有自动门禁 |
| 前端入口 | `✅` React/Vite/Ant Design 五入口壳层已通过组件、构建和真实浏览器导航验收；审计入口仅对 Owner 可见 |
| 跨端契约 | `✅` FastAPI OpenAPI、前端生成 DTO 和隔离漂移检查已形成单一来源闭环 |
| 前端 API | `✅` Axios、Query Client、Zod、CORS 与后端真实成功/失败状态已跨端跑通 |
| RAGFlow 基线 | `✅` 官方 v0.25.6/tag commit、common-agent-dev 隔离栈、loopback 端口、数据目录和资源策略已锁定 |
| 产品代码 | `✅` 知识库、数字员工、连续会话、工作流设计/运行及两类触发的 MVP 正式链路已完成 |
| 本地服务 | `✅` S10-04 验收后 demo/real 前后端、平台/RAGFlow 容器、浏览器和项目专属 Colima 已停止；原生 Volume、0600 Token、现有 Demo Key 与官方镜像保留，下一任务可按需复用 |
| 后续整改 | `🟨` Wave 7、Wave 8、Wave 9、S10-01 至 S10-04 已完成；下一任务 S10-05 建立持久任务、事件与 Worker，MVP 完成事实不变 |

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

| 边界 | 必须覆盖的失败 | MVP 适用性、自动化与真实证据 |
| --- | --- | --- |
| 配置 | 缺少、格式错误、端口冲突、错误环境和敏感值泄漏 | ✅ `test_settings.py`、模型配置测试、两类 `test-manage.sh` 和 E2E 端口预检；正式错误/`repr`/前端契约均不含 Key、密码或上游正文 |
| SQLite | 文件不可写、迁移失败、唯一冲突、事务回滚和重启恢复 | ➖ 不适用：B1-05 后平台正式与测试链均只装配 MySQL，源码和依赖没有 SQLite 运行适配器；不得以历史 B1-03 记录冒充当前链路 |
| 平台 MySQL | 未启动、连接/认证失败、迁移失败、唯一冲突、事务回滚、重启恢复、端口/Volume 隔离和资源清理 | ✅ `test_database.py`、各 SQLAlchemy 仓储/正式 Uvicorn 集成、Alembic check、`infra/platform/test-manage.sh`；真实 8.4.10 容器重启与正式 app lifespan 已验收 |
| PostgreSQL | 连接失败、迁移失败、连接池耗尽、事务回滚和 Schema 隔离 | ➖ 不适用：MVP 未选择 PostgreSQL，也没有驱动、容器或运行时代码 |
| Redis/消息队列 | 不可用、超时、重复投递、乱序、积压、消费失败和恢复 | ➖ 平台不适用：没有平台 Redis/MQ；进程内 SSE Broker 的顺序、历史缺口、慢消费者关闭、重放、有界订阅/状态与 TTL/LRU 回收由事件测试及 `tests/soak/` 覆盖；RAGFlow 内部 Valkey 不作为平台接口 |
| 对象存储 | Bucket/权限错误、上传中断、重复对象、清理失败和容量上限 | ➖ 平台不适用：文档只经 RAGFlow 正式 API，平台没有对象存储适配器；RAGFlow 内部 MinIO 由固定上游栈管理，不绕过 RAGFlow 直连 |
| Worker | 启动失败、任务丢失、超时、重试幂等、崩溃恢复和优雅停止 | ➖ 平台不适用：MVP 没有分布式 Worker；会话/工作流进程内任务的恢复、取消、停止和 lifespan 关闭分别有服务测试 |
| RAGFlow | 未启动、Key 错误、超时、知识库不存在和 API 版本漂移 | ✅ `adapters/knowledge/test_ragflow.py` 故障注入定位，真实 v0.25.6 生命周期/公开 HTTP/会话检索验收；正式适配层统一安全错误 |
| 文档 | 空文件、超限、不支持类型、重复上传、解析失败和解析超时 | ✅ `knowledge/test_service.py`、RAGFlow 重复/上传未知结果/状态映射测试、知识页状态测试；真实 RAGFlow 用 900 秒 deadline 验收解析超时，解析失败真实页面路径已有证据 |
| 数字员工 | 字段非法、绑定知识库失效、模型配置错误和工作流越权 | ✅ Employee 领域/服务/正式 HTTP/MySQL 测试；真实失效绑定、百炼配置和有权/无权工作流会话分别由 E3-02、A4-02、W5-07 验收 |
| 会话 | 重复提交、同会话并发、断流、晚到事件、停止与完成竞态 | ✅ `test_conversation_service.py`、正式 HTTP/SSE 和聊天页覆盖；Q6-01 新增“停止已接受后晚到 completed”单终态测试并修复停止优先语义 |
| 检索 | 空结果、低相关、引用缺字段、知识库切换和检索失败 | ✅ RAGFlow/`ConversationKnowledgeResolver` 测试覆盖；Q6-01 新增适配层阈值与 top_k 二次收口、逐轮当前知识库绑定测试，缺字段/重复/超量引用 fail closed |
| 百炼 | Key 错误、限流、超时、5xx、流中断和输出为空 | ✅ `test_bailian_adapter.py` 覆盖有限重试/脱敏/分块超时/中断/空流，真实百炼同时验证成功流与无效 Key |
| Deep Agents | 工具失败、未知事件、非预期状态和无授权工作流调用 | ✅ Deep Agents 适配/工具注册表失败矩阵；真实官方运行时、真实百炼与有权/无权工作流会话验收 |
| 工作流图 | 缺少开始/结束、孤立、自环、重复边、环、未知节点和无效配置 | ✅ 领域、完整服务端 Validator、编译器、正式 HTTP 与 React Flow 页面均覆盖，非法图不打开写事务 |
| 工作流运行 | 节点失败、停止、输出不匹配、知识库失效和模型失败 | ✅ `test_run_service.py`、正式 HTTP/SSE、真实 RAGFlow/LangGraph/百炼和无头运行 UI；终态均以 MySQL 摘要恢复 |
| 前端 | 后端不可用、Schema 漂移、刷新恢复、重复事件和安全错误展示 | ✅ 各 API Zod/错误边界和四页面组件测试；真实无头页面覆盖解析失败、停止/重试、刷新恢复、运行失败/摘要；公共错误不展示 provider detail |
| Docker | 端口/名称冲突、内存不足、健康失败、其他项目隔离和镜像清理 | ✅ 两类 `test-manage.sh` 与 `test-real.sh` 覆盖非法/占用端口、12/32 GiB 模式边界、非法资源值及平台/RAGFlow 健康失败；独立 `colima-common-agent-dev` context、固定名称/端口/原生 Volume/资源上限经真实 stop→Colima 关闭→up 核对，迁移后的 MySQL 不再受 macOS bind UID/大小写字典限制，镜像与数据按项目复用 |

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
| W5-06 | 手动运行 UI | 输入、运行、节点高亮、失败和最终结果 | W5-04,W5-05 | ✅ 已完成 |
| W5-07 | 数字员工触发工具 | 只允许调用员工 allowlist 中工作流，共用 WorkflowService | W5-04,A4-04 | ✅ 已完成 |
| W5-08 | 工作流 E2E | 创建图→保存→手动运行→员工触发→刷新查看摘要 | W5-06,W5-07 | ✅ 已完成 |

## 12. Wave 6：MVP 收口

| ID | 任务 | 交付物与完成定义 | 依赖 | 状态 |
| --- | --- | --- | --- | --- |
| Q6-01 | 完整失败矩阵 | 第 5 节所有适用分支有自动化或明确真实证据 | A4-09,W5-08 | ✅ 已完成 |
| Q6-02 | Docker 资源与清理验收 | 记录峰值/稳定内存、48GiB 独立 profile 建议、端口/context 隔离；证明稳定栈复用、按影响重建，并清理重复任务镜像和悬空层 | Q6-01 | ✅ 已完成 |
| Q6-03 | 全量自动化 | 后端、前端、契约、构建和 Playwright 全量通过 | Q6-02 | ✅ 已完成 |
| Q6-04 | 本机 MVP 验收 | 从空平台完成知识库→员工→两轮对话→工作流，全部走正式入口 | Q6-03 | ✅ 已完成 |
| Q6-05 | 规格与质量复审 | 核对范围、假绿、泄密、资源泄漏、残留进程和无用代码 | Q6-04 | ✅ 已完成 |

## 13. MVP 后续整改决策与边界

2026-07-20 代码审阅确认：MVP 用户链路与既有完成记录保持有效，但工程门禁、第三方隔离、
运行态生命周期、可观测性、长期维护、开发体验、资源占用、数据管理与生产化仍需继续整改。
用户已明确要求本节列出的全部问题进入路线图，不再作为“以后可能处理”的非阻塞备注。

后续任务遵守以下决策：

- 平台新增自有消息、模型流和图执行协议；LangChain、LangGraph、Deep Agents、HTTP SDK 与供应商
  类型全部收回 `adapters/`，领域、应用、端口、运行时和工作流平台层不再导入第三方框架类型；
- GitHub CI 负责可在隔离环境稳定执行的冻结安装、单元/集成、静态检查、契约、构建、供应链和
  Demo 门禁；真实 RAGFlow/百炼链路继续由显式本机或后续受控自托管门禁执行，不能用 Mock 替代；
- 知识库向量化与检索重排统一使用阿里百炼：embedding 固定以 `text-embedding-v4` 为首选，
  rerank 固定以 `qwen3-rerank` 为首选；通过 RAGFlow 官方 `Tongyi-Qianwen` 供应商能力和公开
  UI/API/配置接入，不修改 RAGFlow 源码、官方镜像内文件或已安装包，不维护 fork/patch；若当前
  锁定版本的公开能力无法通过兼容性验收，只允许升级到支持该能力的官方版本并完成全量回归；
- 百炼迁移完成并重建既有知识库索引、通过中文召回与重排质量门禁后，项目彻底移除本地
  BGE-M3/TEI embedding 与本地 rerank 模型的服务、权重、挂载、下载检查、端口和启停入口，不保留
  本地模型兜底；迁移前不得先删权重导致既有正式链路不可恢复；
- 当前正式工作流和会话仍是单 FastAPI 进程托管形态；先修复事件 Broker、锁表和历史状态的
  无界增长，再在生产化阶段引入持久事件与可靠 Worker，不用一次重构混合两个风险层级；
- 认证、租户、RBAC、审计、备份与远程部署属于 MVP 之后的生产化范围，不追溯修改已经完成的
  MVP 定义；对应任务真正开始并改变产品边界时，必须在同一任务更新产品和架构基线；
- 远程部署任务进入路线图不等于立即部署。首次创建远程环境、公开入口或发布仍需用户另行明确
  下令，未获得该次授权时只允许完成可部署工件、配置契约、回滚方案和本机/隔离环境验证；
- 用户在 S10-01 再次明确要求：现有百炼 Demo Key 继续随私有仓库版本化，以便两台开发电脑直接
  拉取使用；不轮换、不作废，也不改成本机 Secret。该授权只覆盖 `backend/.env.demo` 中的现有值，
  不扩展到其他 Key、Token、Cookie、密码或生产凭据；日志、Trace、测试与构建产物仍禁止复制它。

### 13.1 Colima 32 GiB 评估结论

当前不能直接把完整 `common-agent-dev` 从 48 GiB 改为 32 GiB。Q6-02 的真实证据是：代表性
稳定/E2E 占用约 28.63 GiB，其中 BGE-M3 embedding 约 21.66 GiB；七个容器内存上限合计
37.25 GiB。32 GiB 只有约 3.37 GiB 余量，既低于容器上限，也不足以覆盖冷启动、文档解析峰值、
Docker/Colima 开销和短时抖动。现有 `manage.sh` 至少要求 40 GiB 并建议 48 GiB，因此不能仅修改
profile 数字或 `mem_limit` 制造“可以启动”的假结论。

48 GiB profile 在 128 GiB 开发机上已验证可用，但当前日常电脑总内存只有 64 GiB 且需要并行
运行其他任务，48 GiB 不得继续作为这台电脑的日常默认方案。两台 Mac 之间不能直连，因此
128 GiB 电脑只能通过 Git 获取同一 revision 后独立执行同一套百炼 real 回归，不能成为 64 GiB
电脑的 RAGFlow、数据库、embedding、rerank 或隧道依赖，完成证据必须记录准确 revision。

64 GiB 电脑优先通过 R8-00 建立完全本地的低资源模式：日常 `demo-light` 只运行前后端和轻量
平台 MySQL；需要真实知识链路时，`real-light` 仍在本机运行 RAGFlow，但通过 RAGFlow 官方配置
接入阿里百炼 `text-embedding-v4` 与 `qwen3-rerank`，停用并最终移除占用约 21.66 GiB 的本地
BGE-M3/TEI 及所有本地 rerank 模型。知识片段和候选召回内容会发送到百炼，因此必须在界面/配置
中明确凭据、费用、限流与数据边界，并通过中文向量召回和重排质量基准；不能静默切换供应方，
也不再提供 `real-heavy` 本地模型模式。

移除本地 TEI 后，按现有采样静态扣除可从约 28.63 GiB 降到约 6.97 GiB，非 TEI 容器内存上限
合计约 13.25 GiB，因此 32 GiB 已是高概率足够且有明显余量的目标；但静态相减不等于峰值验收。
R8-00 按用户要求先把 real profile 从 48 GiB 调整为 32 GiB，并完成一次真实解析、重建和检索
基础验收。R8-04 随后从 Colima 完全停止态完成 88.934 秒冷启动、真实文档解析/检索、索引重建、
两轮会话、工作流和 30 分钟稳定性测试；180 个 10 秒样本的 VM 峰值 6.91 GiB、容器合计峰值
6.85 GiB，Swap、容器重启、OOM、健康抖动和中文质量下降均为 0。完整链路远低于 25 GiB 门禁，
因此 32 GiB 正式确认为长期 `real` 默认值。日常 Demo 仍使用 12 GiB 轻量模式，避免在 64 GiB
主机运行其他任务时长期占住一半内存；不得只调低 `mem_limit` 冒充后续优化。

## 14. Wave 7：架构与工程质量加固

### 目标

建立自动执行的质量门禁，彻底收回第三方类型，补齐可观测性和运行态生命周期，并降低核心代码
与前端产物的维护成本。除安全错误、诊断能力和资源生命周期外，本 Wave 不改变用户业务语义。

| ID | 任务 | 交付物与完成定义 | 依赖 | 状态 |
| --- | --- | --- | --- | --- |
| H7-01 | 本地质量门禁与可选 GitHub CI 镜像 | 以本机冻结安装和可复现命令为权威，执行后端 pytest/Ruff/Mypy/uv lock/audit、前端 Vitest/ESLint/Typecheck/Build/pnpm audit、契约漂移、ShellCheck 和 Demo 链路；PR/main workflow 只镜像同一组门禁，不依赖付费 Hosted Runner，也不作为完成前提；缓存不得绕过锁文件，失败不得吞掉；真实外部依赖门禁保留显式入口 | D8-03 | ✅ 已完成 |
| H7-02 | 自动化覆盖率门禁 | 后端、前端分别生成行/分支覆盖率；先记录真实基线并补足缺口，最终后端总体行覆盖率不低于 85%、核心领域/应用不低于 90%，前端总体行覆盖率不低于 80%，新增改动不得降低；报告不进入 Git | H7-01 | ✅ 已完成 |
| H7-03 | 平台自有消息与模型协议 | 定义不依赖 LangChain 的平台消息、模型请求、增量、终态、错误和释放协议；会话与工作流节点只消费平台类型；百炼与 Deep Agents 适配器负责双向转换；真实百炼、会话和工作流回归全部通过 | H7-02 | ✅ 已完成 |
| H7-04 | 平台自有图执行协议 | 定义不依赖 LangGraph 的编译、执行、节点观察、停止和结果协议；把 LangGraph 编译器、运行状态和节点框架转换移入 `adapters/workflow/langgraph/`；`WorkflowService` 只依赖平台端口，手动与员工触发语义不变 | H7-03 | ✅ 已完成 |
| H7-05 | 第三方依赖边界门禁 | 增加可自动执行的 import/AST 架构测试；除 `api/` 的 FastAPI 边界和 `adapters/` 外，生产平台层不得导入 FastAPI、SQLAlchemy、HTTP SDK、LangChain、LangGraph、Deep Agents 或供应商类型；修正规则和架构文档与实现口径 | H7-04 | ✅ 已完成 |
| H7-06 | 结构化日志、指标与追踪 | 统一 JSON 日志和关联上下文，覆盖 request/conversation/message/turn/workflow/run ID、耗时、状态与稳定错误码；提供本机最小健康/指标入口和跨服务 trace context；默认脱敏提示词、知识正文、Key、密码和上游响应，故障测试证明可定位且不泄密 | H7-05 | ✅ 已完成 |
| H7-07 | 事件与锁状态生命周期 | 为会话/工作流 Broker 历史、订阅者、per-ID 锁和终态状态增加有界容量、TTL/LRU 与安全回收；保留允许的 SSE 回放窗口，慢消费者和历史缺口语义不变；通过大量短会话/运行及长时间 soak 证明内存最终回落且无活跃状态误删 | H7-06 | ✅ 已完成 |
| H7-08 | 核心大文件按职责拆分 | 在既有行为测试保护下拆分 ChatPage、WorkflowsPage、ConversationService、WorkflowService 和大型路由；页面容器只做编排，消息/运行/设计器状态与协议映射独立；服务按用例/运行协调/持久化投影分责，禁止循环依赖和跨 Feature 私有导入 | H7-07 | ✅ 已完成 |
| H7-09 | 前端包体与加载性能 | 建立 bundle 分析和预算门禁，路由与稳定 vendor 合理拆分；任何初始或异步单 chunk 不超过 500 kB，四入口真实浏览器首屏、交互和缓存复用无回归；不得仅调高 warning 阈值 | H7-08 | ✅ 已完成 |

## 15. Wave 8：开发体验与资源优化

### 目标

让全新克隆可用明确的一键入口进入 Demo 或 real 模式，修复 Demo 重启后的状态语义，并在不牺牲
中文检索质量和正式链路的前提下评估 32 GiB Colima。

| ID | 任务 | 交付物与完成定义 | 依赖 | 状态 |
| --- | --- | --- | --- | --- |
| R8-00 | 百炼向量/重排迁移与本地模型退场 | 仅通过 RAGFlow v0.25.6 官方 `Tongyi-Qianwen` 供应商的公开 UI/API/配置接入百炼 `text-embedding-v4` 和 `qwen3-rerank`，禁止修改 RAGFlow 源码、镜像内文件、已安装包或维护 fork/patch；迁移 API Key、区域/业务空间、模型绑定、超时/限流/费用和脱敏诊断；embedding 变更必须重建既有知识库索引，中文基准同时验证初召回与重排顺序，失败时保持可恢复；正式门禁通过后移除本地 TEI 服务、BGE-M3/本地 rerank 权重、挂载、端口、profile、下载/检查和启停入口且不保留本地模型兜底；`real` 改为不含本地模型的按需 32 GiB 暂定模式，不复用旧 48 GiB 重型 profile；统一 `demo-light` 入口与 8-12 GiB 门禁由紧随其后的 D8-01 交付 | Q6-05 | ✅ 已完成 |
| D8-01 | 全新克隆一键 Demo | 提供统一的 `doctor/setup/up/status/stop/clean` 开发入口；检查并冻结安装 uv/pnpm 依赖、使用轻量平台 MySQL 启动 Demo 前后端、显示访问地址并精确清理；从无 `.venv`/`node_modules` 的临时克隆完成两轮 Demo 会话，失败给出可操作信息，当前 64 GiB 电脑不启动 48 GiB profile | R8-00 | ✅ 已完成 |
| D8-02 | Demo 知识状态持久语义 | Demo 知识库、文档和解析/检索状态使用可重启恢复的项目专属持久边界，或采用同等一致的显式生命周期设计；员工绑定、会话引用与知识数据在后端重启后保持一致，不出现持久员工引用已消失内存知识库；与 real 协议和错误语义保持契约一致 | D8-01 | ✅ 已完成 |
| D8-03 | real 模式一键体检与启停 | 在不打印凭据的前提下统一检查按需 Colima context、MySQL、RAGFlow 官方版本/源码完整性、RAGFlow Token、百炼 embedding/rerank 供应商、模型绑定、区域/业务空间、端口和磁盘；提供不含本地模型的 `real` 模式可重复启停、健康和费用诊断，保留稳定栈复用；64 GiB 电脑本地完成知识库→员工→两轮会话→工作流，向量/重排配置、限流、超时和费用边界失败显示真实可恢复错误；128 GiB 电脑仅可按相同 Git revision 独立执行同一门禁，不作为远程依赖 | D8-02,R8-00 | ✅ 已完成 |
| R8-04 | Colima 32 GiB 专项优化与验收 | 以原 28.63 GiB 和 R8-00 真实稳定采样约 6.25 GiB 为上下界基线，实测百炼 embedding/rerank 下的 RAGFlow/ES/解析/运行峰值、中文召回与重排质量、延迟、费用、限流和数据边界；把本机完整 `real` 链路峰值压到不高于 25 GiB，在暂定 32 GiB profile 连续完成冷启动、解析/检索、两轮会话、工作流及 30 分钟 soak，无 OOM、持续 Swap 压力、重启或质量下降后确认并保留 real 默认值，否则按实测上调；`demo-light` 仍保持 8-12 GiB，避免长期占用 64 GiB 主机一半内存 | D8-03 | ✅ 已完成 |

## 16. Wave 9：数据管理与产品可维护性

### 目标

补齐 MVP 为控制范围而省略的数据生命周期和大列表能力，避免长期使用后只能依赖测试脚本或直接
数据库清理。任务开始时同步更新产品范围与 API/前端架构，不引入任务中心或业务自动化模型。

| ID | 任务 | 交付物与完成定义 | 依赖 | 状态 |
| --- | --- | --- | --- | --- |
| U9-01 | 资源删除策略与后端 API | 为会话、数字员工、知识库和工作流定义引用检查、级联/拒绝策略、外部副作用不确定语义和幂等删除；实现正式 API、MySQL/RAGFlow 事务边界及失败恢复，删除前后不留下悬空绑定、运行来源或文档 | R8-04 | ✅ 已完成 |
| U9-02 | 删除 UI 与真实验收 | 四入口提供目标清晰的删除确认、引用阻断说明和完成/失败状态；无头浏览器验证创建→引用→阻断/解绑→删除→刷新消失，不能用测试清理器代替用户链路 | U9-01 | ✅ 已完成 |
| U9-03 | 列表分页、搜索与稳定排序 | 为会话、员工、知识库、工作流和运行摘要建立统一游标或明确分页契约、服务端搜索和稳定排序；前端保持筛选/页游标并处理新增/删除并发变化；大数据集下无全表/N+1 和重复/遗漏项 | U9-02 | ✅ 已完成 |

## 17. Wave 10：安全、可靠性与生产化

### 目标

在用户明确需要远程、多用户运行的前提下，把当前本机单用户 MVP 提升为可安全部署、可恢复、
可审计的平台。每项能力必须通过正式入口和真实依赖验收，不能用仅本机成功替代生产门禁。

| ID | 任务 | 交付物与完成定义 | 依赖 | 状态 |
| --- | --- | --- | --- | --- |
| S10-01 | 授权 Demo Key 边界与泄漏门禁 | 保留用户明确批准、私有仓库版本化且不轮换的现有百炼 Demo Key；自动证明它只存在于指定后端配置及其 Git 历史，普通测试使用假值，日志、Trace、后端归档和前端产物不得复制；错误与诊断只显示配置状态，不显示值，其他凭据仍一律禁止版本化 | U9-03 | ✅ 已完成 |
| S10-02 | 身份认证与安全会话 | 实现注册策略、登录/退出、安全 Cookie 或等价会话、CSRF/重放/暴力尝试防护和凭据恢复边界；所有写接口默认拒绝未认证访问，真实浏览器覆盖成功、过期、撤销和攻击失败路径 | S10-01 | ✅ 已完成 |
| S10-03 | 组织、租户与 RBAC 隔离 | 为员工、知识库引用、会话、工作流和运行增加租户归属；定义最小角色/权限和跨租户拒绝；迁移、唯一约束、查询、缓存/事件命名空间和外部 RAGFlow 数据均隔离，越权测试覆盖 REST/SSE/工具调用 | S10-02 | ✅ 已完成 |
| S10-04 | 审计与安全事件 | 对登录、配置、绑定、上传、删除、工作流运行、权限拒绝和凭据操作写入不可篡改/可追溯审计记录；支持按租户、操作者、资源和时间查询，正文与凭据脱敏，保留策略和容量上限明确 | S10-03,H7-06 | ✅ 已完成 |
| S10-05 | 持久任务、事件与 Worker | 通过平台自有任务/事件端口引入真实队列和 Worker；会话回复、工作流运行、停止、幂等、重试、积压、崩溃恢复和至少一次投递语义明确；SSE 可从持久序列恢复，多 API/Worker 实例不重复执行副作用 | S10-04,H7-07 | ⬜ 未开始 |
| S10-06 | 备份、恢复与灾难演练 | 为平台 MySQL、对象/上传数据、RAGFlow 外部引用和部署配置定义备份、加密、保留、恢复点与恢复时间；从独立备份恢复到空环境并由正式页面验证核心数据与引用，演练不污染正式数据 | S10-05 | ⬜ 未开始 |
| S10-07 | 生产构建、远程部署与回滚 | 建立最小权限镜像、不可变版本、环境配置、TLS/域名、数据库迁移、健康/就绪、灰度与回滚流水线；先在隔离环境完成生产同路径。实际创建远程资源和首次发布必须再次取得用户明确部署指令 | S10-06 | ⬜ 未开始 |
| S10-08 | 生产安全、性能与最终验收 | 执行依赖/SAST/Secret/容器扫描、权限与输入攻击测试、并发/容量/长连接/故障恢复压测；定义并满足 SLO、资源预算和告警；从新租户通过正式浏览器完成知识库→员工→会话→工作流并验证审计、备份与回滚 | S10-07 | ⬜ 未开始 |

## 18. 当前下一步

R8-00 至 R8-04、D8-01 至 D8-03、H7-01 至 H7-09 与 Wave 9 已完成：RAGFlow 官方源码以 submodule 固定且保持未修改，知识库
embedding/rerank 统一使用阿里百炼，本地模型退场；全新克隆可由统一入口进入 12 GiB
`demo-light`，Demo 知识、员工绑定与会话引用在后端重启后保持一致；`real` 可按需切到固定
32 GiB，完成脱敏体检、费用诊断、真实纵向门禁、跨 Colima 重启恢复和 30 分钟专项资源验收；本机质量门禁已经冻结，
GitHub Hosted Runner 只作可选镜像、不作为验收依赖；前后端行/分支覆盖率已建立本机不回退门禁；
平台消息/模型/图执行协议不再暴露 LangChain、OpenAI、Deep Agents 或 LangGraph 类型，生产
第三方 import 和平台内部依赖方向由关闭失败的统一 AST 门禁约束；正式 API、会话、工作流及
RAGFlow/百炼出站已具备脱敏 JSON 日志、有界进程指标和关联追踪；事件历史、订阅者、per-ID
锁与终态状态也已具备容量、TTL/LRU 和安全回收；核心页面、服务与大型路由已按编排、运行协调、
持久化和投影职责拆分，并由体量、依赖方向、Feature 私有边界和循环依赖门禁保护；五路由异步
入口和稳定 vendor 已按 Vite 8/Rolldown 正式能力拆分，单 chunk 与单路由首次加载图均有本机
不回退门禁。32 GiB `real` 的 180 个连续样本 VM 峰值 6.91 GiB、容器峰值 6.85 GiB，且无
Swap、重启、OOM 或健康抖动，已经正式确认为长期默认值。四类资源已有引用安全、幂等的正式
DELETE API，并由真实 RAGFlow 生命周期验证；四个正式页面也已提供受控确认、引用阻断指引和
完成/失败状态，真实浏览器完成创建→引用→阻断/解绑→删除→刷新消失。会话、员工、知识库、
工作流和运行摘要现已统一为 `items + next_cursor`，平台 MySQL 使用稳定 keyset 与前缀搜索索引，
RAGFlow 官方页码只留在适配层；页面保持搜索与游标页链并按 ID 去重，创建/删除后重置权威页链。
S10-01 已完成：按用户再次确认的边界，现有百炼 Demo Key 继续只在私有仓库
`backend/.env.demo` 版本化且不轮换；非真实测试已与真 Key 隔离，源码、Git 全历史、日志/Trace、
后端归档和前端生产包由同一指纹门禁扫描。S10-02 也已完成：空库只允许一次性创建首位所有者，
业务 REST/SSE 全部经过可过期、可撤销的服务端会话，浏览器使用 HttpOnly Cookie、内存 CSRF 与
可信 Origin，登录限流、恢复码单次消费和攻击失败路径已通过真实 Chromium。S10-03 已完成：
默认组织/工作区、Owner/Editor/Viewer、成员配置、五类资源复合约束、仓储/事件/锁命名空间和
RAGFlow 外部 ID 归属均按租户关闭失败，REST/SSE/工具调用越权与真实 Viewer 页面已验收。S10-04
也已完成：登录、凭据、配置/绑定、上传、删除、会话回复、工作流运行/停止和安全拒绝使用固定
元数据写入租户或平台哈希链；MySQL 触发器禁止原地更新/删除，Owner 可按操作者、动作、资源和
时间查询并验证完整性，正文与凭据不进入类型或响应，365 天保留标记与每作用域 100 万容量关闭
失败。当前进入 S10-05，以平台自有端口交付持久任务、事件与 Worker，并明确至少一次投递、幂等、
重试、积压、崩溃恢复、多实例副作用和持久 SSE 序列语义。所有后续任务仍
遵循 Red-Green-Refactor、生产同路径验收、失败矩阵、资源清理和单任务完成
后提交推送规则；GitHub CI 仍只作可选镜像，不作为完成依据。

## 19. 高冲突与唯一写入区域

- 根目录规则、路线图、依赖锁文件和忽略规则；
- 当前正式数据库 migration revision；
- OpenAPI、会话事件和生成 DTO；
- FastAPI app 装配、前端 Query Client 和全局导航；
- RAGFlow Compose、端口、Volume 和版本；
- 百炼 Demo 配置；
- 工作流节点 Schema 和注册表；

当前不使用子代理；只有用户明确要求后才允许并行，并为这些区域指定唯一写入者。

## 20. 每项任务的完成记录格式

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

### W5-06 手动运行 UI

- 状态：✅ 已完成
- 日期：2026-07-20
- 提交：本任务提交（见 Git 历史）
- RED：先新增工作流运行 HTTP/SSE 严格边界测试，首次定向执行因 `api/workflowRuns` 不存在而按预期在导入阶段失败；实现适配层后 3 项通过。随后为正式页面新增启动、节点高亮、停止、终态、断流恢复、URL 刷新恢复和未保存草稿禁跑测试，首次执行 10 项中原有 5 项通过、新增 5 项均因运行输入和面板不存在而失败；实现后又补充终态晚到事件、运行中编辑锁定和用户切换优先级，最终页面 11 项通过。首次真实 E2E 已完成百炼成功和协作停止，却在刷新停止摘要后切换失败工作流时再次运行了成功定义，证明 URL 恢复 effect 会与用户选择竞态；增加每个 run 只同步一次定义的门闩及回归测试后，第二轮三种终态全部通过
- GREEN：工作流运行 API/SSE 3 项、工作流页面 11 项定向测试通过；最终前端 14 个文件 56 passed，ESLint、TypeScript、生产 Build 与 pnpm 冻结锁通过。后端全量 371 passed/10 个显式外部验收 skip，Ruff lint、146 个非不可变迁移文件格式、严格 Mypy 141 个源/测试文件和 uv lock 通过；Shellcheck、OpenAPI/双事件 Schema/生成 TypeScript 契约漂移与 `git diff --check` 通过。专属无头 Chromium 真实依赖验收 1 passed in 4.9s
- 运行边界：新增前端 `workflowRuns` 适配层，只调用正式启动、权威摘要、停止和命名 SSE 入口；运行、事件、停止接受响应均在生成 DTO 之外通过严格 Zod，拒绝额外字段、未知状态/事件、非法 ID/时间/节点和 Schema 漂移。SSE 从显式序号恢复并过滤重复/晚到序号，事件快照与 GET 摘要按更新时间和状态单调合并，终态不会被晚到 running 覆盖；断流立即 GET 正式 MySQL 摘要并向用户说明恢复结果，所有订阅在切换、终态和卸载时显式关闭
- 页面与隔离：右侧新增独立手动运行面板，提供 20 万字符上限输入、启动/停止、五态标签、逐节点进度、最终输出、停止说明和稳定错误码；运行 ID 写入 URL，刷新后先经正式 GET 恢复摘要和对应工作流，再决定是否重连活动 SSE。运行投影完全独立于工作流 reducer，不回写节点配置、位置或边；只有已保存且无脏修改的定义能运行，活动运行期间锁定新建、切换、保存、拖拽、连线、删除和配置输入，避免画布草稿与服务端执行版本混淆。完成/当前/失败节点分别以绿色、动态蓝色和红色映射到同一 React Flow 节点，并提供 reduced-motion 降级
- 生产同路径边界：专属 `workflow-run-ui` 套件只用正式平台 API准备三个已保存定义和一个随后真实失效的 RAGFlow v0.25.6 数据集；所有待交付运行行为均从无头 Chromium 用户页面触发。第一条路径经 `Vite -> Axios -> Uvicorn/FastAPI -> WorkflowService -> MySQL -> LangGraph -> BailianChatModelAdapter -> 阿里百炼`，页面在 AI 节点期间显示活动高亮和编辑锁，终态输出唯一 `COMMON_AGENT_WORKFLOW_UI_REAL_OK`，刷新用 URL/GET 恢复三节点完成摘要；第二条路径在真实 AI 节点执行中点击停止，经正式 stop 路由和协作取消得到 stopped，刷新恢复；第三条路径从页面运行引用已被官方 RAGFlow API删除的数据集，经知识节点失败并展示 `knowledge_base_not_found` 与红色失败节点，刷新仍由 MySQL 恢复失败摘要。浏览器没有直连 19380，完成证据没有 Mock/Fake、进程内客户端、直接函数、DOM 注入或日志断言
- 失败矩阵：覆盖空白输入与未保存/脏定义禁跑、启动/摘要/停止 HTTP 错误、未知状态/事件/Schema 与额外字段、SSE 畸形/重复/晚到/断流、事件身份不一致过滤、权威摘要恢复失败、当前/完成/失败节点样式、真实模型完成、运行中真实停止、真实知识依赖失效、终态刷新恢复、恢复与用户切换竞态，以及活动运行结构编辑关闭。分层测试负责精确错误定位，真实页面用例负责最终交付，不互相替代
- 编排与清理：统一 E2E 脚本新增 `workflow-run-ui` suite，继续使用固定 `chromium-headless-shell`、单 worker、15 秒动作上限、失败截图/Trace、独立端口预检和 PID trap；为成功/停止/失败定义及失效知识库生成唯一名称，成功、失败或中断后先关闭浏览器/Vite/FastAPI，再按名称级联删除工作流和运行摘要并清理残留数据集。最终测试库工作流/节点/边/运行均为 0，RAGFlow `common-agent-w5-06-*` 前缀为 0，18200/18280 无监听，无 Uvicorn/Vite/Playwright/Chromium/agent-browser、失败 Trace、dist、tsbuildinfo、项目测试缓存或悬空镜像残留；健康 MySQL/RAGFlow 稳定栈继续复用
- 格式边界：继续保持已应用不可变迁移 `20260720_0005` 不被改写，Ruff 全目录格式门禁精确排除该历史文件；其余 146 个文件全部已格式化，lint 与 Mypy 仍覆盖迁移相关代码
- 文档：只更新唯一进度源、E2E 脚本说明和正式调用脚本；产品范围没有变化，未修改 `docs/product-scope.md`
- 遗留：无；下一任务 W5-07 让数字员工只通过已配置 allowlist 调用同一个 `WorkflowService`，不复制编译、执行、事件或持久化链路

### W5-07 数字员工触发工具

- 状态：✅ 已完成
- 日期：2026-07-20
- 提交：本任务提交（见 Git 历史）
- RED：先新增员工工作流工具、`WorkflowService.wait_for_run` 和员工 allowlist 服务测试；定向 pytest 因生产模块 `common_agent.adapters.agent.workflow_tools` 不存在发生收集错误，证明当前静态 Deep Agents 工具注册表尚不能把用户新保存的工作流解析为受控工具。后续最小实现必须同时打通员工配置保存、逐工作流动态工具暴露、`employee` 触发来源、终态等待和稳定失败返回，不能用直接编译图或测试工具替代同一个 `WorkflowService`
- GREEN：工作流工具/等待、Deep Agents 注册表、员工领域/服务与运行服务定向 31 passed，员工正式 HTTP、Deep Agents 适配和会话服务回归 21 passed；最终后端全量 378 passed/11 个显式外部验收 skip，Ruff lint、除不可变已应用 `20260720_0005` 外 149 个文件格式、严格 Mypy 150 个源/测试文件和 uv lock 通过。前端最终 14 个文件 57 passed，ESLint、TypeScript、生产 Build、pnpm 冻结锁和 OpenAPI/生成 DTO 漂移通过；ShellCheck 与 `git diff --check` 通过。专属真实员工工具验收 1 passed in 5.95s
- 员工配置与引用：公开 Employee POST/PUT 的 `allowed_workflow_ids` 现支持最多 100 个无重复 UUID，创建和更新会在数据库事务外逐项经正式 `WorkflowService.get()` 确认定义存在，再原子保存原顺序；不存在引用返回 `workflow_not_found`，重复/超量在访问工作流前返回 `validation_error`，失败创建不写库、失败更新不覆盖原配置。React 员工表单从正式工作流列表多选权限，卡片显示授权数量；员工、知识库和工作流三类查询独立失败，工作流不可用只禁用对应字段
- 动态工具与双重边界：`DeepAgentsEmployeeRuntime` 的注册口提升为异步 `DeepAgentToolResolver`，生产 `WorkflowToolRegistry` 每轮按当前员工持久化 allowlist 重新读取定义并只返回同序工具；空 allowlist 不暴露工具，失效 ID fail closed。每个工具名称含唯一 UUID 且闭包固定目标工作流，模型参数只有受领域上限约束的 `input`，无法在调用时替换目标 ID；原 Deep Agents 保留名、重复名、文件/Shell/Todo/task 禁用与未知能力测试继续全量回归
- 共用运行服务：工具只调用现有 `WorkflowService.start_run(..., trigger=employee)`，由同一仓储、LangGraph 编译器、节点观察器、事件 Broker 和 MySQL 摘要执行；新增 `wait_for_run()` 屏蔽调用方取消对后台任务的直接传播并返回已持久化终态。工具取消会再经同一服务发送停止意图，完成结果以包含 run/workflow ID、名称、状态和 output 的安全 JSON 交给模型；失败/停止只暴露稳定平台语义，不直接导入工作流图或复制执行代码
- 生产同路径验收：显式 real 用例从随机 loopback 正式 Uvicorn/FastAPI 先创建 start→end 工作流和带 allowlist 员工，再经公开会话创建、消息 POST 和 SSE 进入 `ConversationService -> DeepAgentsEmployeeRuntime -> deepagents 0.6.12 -> BailianChatModelAdapter -> 阿里百炼 -> WorkflowToolRegistry -> WorkflowService -> SQLAlchemy/MySQL -> LangGraph`。真实模型调用工具后助手终态和正式运行 GET 均返回唯一 `COMMON_AGENT_W5_07_*` 标记，运行摘要确认 `trigger=employee`、真实输入、completed 和同一工作流；随后无 allowlist 员工通过同一会话入口请求按 ID 绕过权限，助手正常说明且该工作流运行记录逐字段保持不变。完成证据没有 Mock/Fake、TestClient、进程内 ASGI、直接编译器调用或日志断言；数据库只用于确认真实副作用及再从公开 GET 读取 run ID
- 失败矩阵：覆盖空/单个/多项 allowlist、重复/超量/不存在引用、创建/更新前置验证和事务保持、动态定义缺失、精确工具名与顺序、employee 触发来源、工作流完成/模型节点失败/停止、未知运行、工具取消、稳定错误不泄漏，以及正式会话有权执行与无权零副作用。低层 Probe/Fake 只定位失败；真实 Deep Agents/百炼会话链解除本任务完成门禁。员工页面的多选与独立失败由 Vitest 覆盖，完整无头浏览器“设计→手动运行→员工触发→刷新摘要”仍由专门 W5-08 验收，不把本内部工具任务冒充跨页面总 E2E
- 契约与文档：Employee 请求 Schema、OpenAPI 和前端生成 DTO 增加有上限的 UUID allowlist 并经隔离重建逐字节一致；后端/前端说明与后端架构同步动态工具和共享服务边界。唯一进度源为本 roadmap，产品边界未变化，未修改 `docs/product-scope.md`
- 清理与正式库：真实验收以 finally 按会话→员工→工作流顺序精确清理；最终测试库员工/会话/消息/工作流/运行全为 0，W5-07 工作流名前缀为 0。发现默认正式库仍停在既有 `20260719_0003` 后，通过正式 `python -m common_agent` lifespan 无旁路升级到 `20260720_0005`，公开 Health 返回 200，正式库保持 Seed 1、会话/消息/工作流/运行 0；两库 `alembic check` 均无漂移。18200/18280 无监听，无 Uvicorn/Vite/Playwright/Chromium 残留，无 dangling 镜像；本任务未启动浏览器，构建产物和项目测试缓存已删除，健康 MySQL/RAGFlow 稳定栈继续复用
- 遗留：无；下一任务 W5-08 只组合已完成的设计器、手动运行和员工工具，通过固定无头 Chromium 从真实页面完成跨端闭环，并补齐员工触发运行卡片/刷新摘要的用户可见关联

### W5-08 工作流 E2E

- 状态：✅ 已完成
- 日期：2026-07-20
- 提交：本任务提交（见 Git 历史）
- RED：先新增员工工作流运行来源、会话筛选和工具关联测试；定向 pytest 因领域层尚无 `WorkflowRunOrigin` 发生 3 个收集错误，证明当前员工工具虽然会真实执行，但运行摘要无法稳定关联到发起它的会话和助手消息，浏览器刷新后也就没有权威依据恢复内联运行卡片
- GREEN：领域、工具注册表、运行服务与仓储定向 38 passed，真实 MySQL 运行仓储 4 passed，数据库迁移/正式系统入口 12 passed；最终后端全量 381 passed/11 个显式外部验收 skip，Ruff lint、除不可变 0005 外 151 个文件格式、严格 Mypy 145 个源/测试文件、uv lock、OpenAPI/双事件 Schema/生成 TypeScript 和正式/测试 MySQL Alembic 漂移全部通过。前端最终 14 个文件 58 passed，ESLint、TypeScript、生产 Build、冻结 pnpm 锁与契约漂移通过；ShellCheck 和 `git diff --check` 通过。显式真实 Deep Agents/百炼员工运行来源验收 1 passed in 5.87s
- 权威关联与契约：新增不可变迁移 `20260720_0006`，`workflow_runs` 为 employee 触发保存 `employee_id`、`conversation_id`、`assistant_message_id`，以 assistant message 外键级联、trigger/origin 一致性 CHECK 和 conversation/created 索引约束；手动运行三项必须为空。`WorkflowRunOrigin` 从正式 `EmployeeRuntimeRequest` 传入动态工具，再进入同一个 `WorkflowService` 和 MySQL 摘要，工具不能自行伪造来源。公开 `GET /api/v1/workflow-runs?conversation_id=...` 只读返回该会话权威摘要，OpenAPI、工作流 SSE Schema、生成 DTO 和前端 Zod 边界同步且严格拒绝 manual/employee 来源不一致
- 对话运行卡片：聊天页按选中会话从正式查询恢复运行，并以 `assistant_message_id` 归档到实际助手消息；生成期间轮询、助手终态和 SSE 恢复时都重新读取服务端摘要。每条运行以可展开卡片显示工作流名称、状态、节点进度、输入、结果或稳定错误码，点击“查看运行详情”进入既有 `/workflows?run_id=...` 正式摘要入口；页面刷新后不依赖内存事件或模型文本重新构造状态
- 生产同路径验收：新增独立 `workflow-chat-e2e` suite，固定 `chromium-headless-shell`、单 worker、零重试、无视频。最终 1 passed in 8.2s：真实浏览器从 React Flow 页面拖入开始/结束节点并连线、服务端校验保存，经手动运行入口看到持久化结果；再从员工页面创建员工并多选授权，从聊天页面新建会话和发送消息，完整经过 `FastAPI -> ConversationService -> Deep Agents -> 阿里百炼 -> WorkflowToolRegistry -> WorkflowService -> LangGraph -> MySQL`，展开 employee 运行卡片看到唯一标记，刷新页面后恢复同一摘要，再点击卡片进入正式工作流运行详情。浏览器请求监听确认没有直连 RAGFlow 或百炼；首次执行仅因结果标记同时匹配输入框和 `<pre>` 的 Playwright strict selector 失败，当轮真实手动运行已经完成，收紧到正式结果区域后复跑通过，没有把定位器失败冒充产品失败
- 失败矩阵：领域和前端边界覆盖 employee 缺来源、manual 携带来源、非 UUID、部分/额外来源字段与触发类型不一致；MySQL 覆盖来源外键、CHECK、重启回读、按会话排序和级联清理；HTTP 覆盖 manual 来源为空、无运行会话空列表、非法 query 和真实 employee 来源三 ID 对齐；既有工作流运行的重复、缺失、失败、停止、SSE 恢复与工具取消/越权矩阵继续全量回归。Mock/Fake 只用于失败定位，W5-08 完成状态只取真实无头用户路径和真实外部依赖证据
- 清理与正式库：E2E trap 无论成功、失败或中断都先关闭 Playwright、Vite、FastAPI，再按会话→员工→工作流顺序精确清理；最终测试库 W5-08 员工/工作流前缀、会话、消息、工作流和运行均为 0。正式应用通过 `python -m common_agent` lifespan 从 0005 升级到 0006，公开 Health 200；正式库保留 Seed 员工 1，会话/消息/工作流/运行 0，两库均为 0006 且 `alembic check` 无漂移。18200/18280 无监听，无 Uvicorn/Vite/Playwright/Chromium 残留；成功产物和首次定位器失败 Trace 已删除，健康 MySQL/RAGFlow 稳定栈继续复用。发现本机缺少后续持续需要的 MySQL CLI，按全局规则以 Homebrew 安装并全局 link `mysql-client 9.7.1`
- 遗留：无；下一任务 Q6-01 汇总第 5 节全平台失败矩阵，补齐尚未显式自动化或真实验收的适用分支

### Q6-01 完整失败矩阵

- 状态：✅ 已完成
- 日期：2026-07-20
- 提交：本任务提交（见 Git 历史）
- 审计结论：逐项重写第 5 节为“适用性、自动化与真实证据”矩阵。SQLite、PostgreSQL、平台 Redis/MQ、平台对象存储和分布式 Worker 因 MVP 正式运行时没有对应适配器而明确标为不适用，不把 RAGFlow 内部 Valkey/MinIO 或进程内事件 Broker 冒充平台能力；MySQL、RAGFlow、文档、员工、会话、检索、百炼、Deep Agents、工作流、前端和 Docker 均映射到具体分层测试及生产同路径证据，后续引入的新技术仍必须即时补矩阵
- RED：真实补测首先让 RAGFlow 适配层返回低于阈值及超过 `top_k` 的片段，现状错误地将三条全部传给会话；随后构造“停止已被正式服务接受、运行时仍晚到 completed”竞态，现状把助手消息持久化为 completed。两次失败分别定位到供应商响应缺少本地防御收口、会话运行循环只相信晚到终态，没有用 Mock 结果冒充修复完成
- GREEN：RAGFlow 正式适配层现在按请求阈值二次过滤并按供应商顺序截断 `top_k`；会话服务在下一事件、流结束或异常三个边界都让已接受的停止优先，只持久化/广播一个 stopped 终态。补充重复文件 HTTP 200/业务拒绝脱敏、逐轮读取员工当前知识库绑定及停止/完成单终态回归；定向检索 47 passed、会话/事件 10 passed，后端全量 385 passed/11 个显式外部验收 skip
- 生产同路径验收：真实官方 RAGFlow v0.25.6 检索 1 passed in 3.72s；正式 Uvicorn/FastAPI、MySQL、RAGFlow、Deep Agents 和阿里百炼的停止→重试→重复提交边界 1 passed in 13.51s。分层故障注入用于定位低相关、版本/认证/超时/断流等失败，最终功能状态仍来自公开 HTTP/SSE、正式适配层和真实依赖
- 文档边界：唯一进度源和矩阵只更新本路线图，没有修改 `docs/product-scope.md`；Q6-02 已补齐矩阵中最后一个未完成的 Docker 专项，因此 Q6-01 才从测试中转为完成
- 遗留：无；Docker 资源和清理证据见紧随其后的 Q6-02

### Q6-02 Docker 资源与清理验收

- 状态：✅ 已完成
- 日期：2026-07-20
- 提交：本任务提交（见 Git 历史）
- RED：先要求 RAGFlow 正式 `up` 在启动前读取独立 context 内存，32 GiB 场景必须失败并建议 48 GiB，测试按预期报告“缺少 Docker 内存预检”；再要求平台 MySQL 健康等待有可注入的有限超时，测试按预期报告“缺少健康超时”。补完平台后首轮 GREEN 又真实暴露测试断言把右括号误作正则分组，改为固定字符串后通过。最后新增 RAGFlow 正式 `up` 健康超时测试，现状按预期因缺少 `RAGFLOW_HEALTH_TIMEOUT_SECONDS` 失败
- 资源门禁：`infra/ragflow/manage.sh up` 默认要求 Docker context 至少 40 GiB 并明确建议独立 48 GiB profile，非法值和读取失败关闭失败；当前 `colima-common-agent-dev` 实际可见 50,412,425,216 bytes（约 46.95 GiB）。稳定/代表性 E2E 采样约 28.63 GiB，其中本地 BGE-M3 embedding 为 21.66 GiB/24 GiB，七容器资源上限合计 37.25 GiB；32 GiB 仅余约 3.37 GiB 且低于总上限，结论为不安全，保留当前 48 GiB profile
- 健康与隔离：平台 `check-health` 复用正式 60 秒稳定健康等待并允许 1-600 秒故障注入；RAGFlow 正式 `up` 使用 `docker compose up -d --wait --wait-timeout`，默认 180 秒并允许 1-600 秒。持续 unhealthy 和 Compose 健康失败均经相同管理入口关闭失败；真实栈为独立 `colima-common-agent-dev` context、项目名、loopback 19xxx 端口、专属数据目录和固定资源，最终七个容器均 running，五个声明健康检查的容器均 healthy
- 稳定栈复用：真实 `pull-image` 分别返回“复用本机平台 MySQL 镜像 mysql:8.4.10”和“复用本机 RAGFlow 镜像 infiniflow/ragflow:v0.25.6”。代表性 `workflow-chat-e2e` 只临时启动当前代码的 Uvicorn/Vite/无头 Chromium，1 passed in 8.2s；测试前后七个容器的完整 ID 与 `StartedAt` 逐字一致（平台 MySQL `3ac257...`，RAGFlow API `b6960d...`，其余依赖同样不变），证明未重复拉取、重建或重启稳定基础设施
- 镜像与磁盘：独立 context 共七个活动镜像且每个仓库/标签只有一个 digest，活动容器全部引用；dangling 查询为 0、Build Cache 为 0，没有可安全删除的重复任务镜像或悬空层，因此没有为了制造“已清理”证据而删除正在复用的 19.17 GB 固定镜像。容器可写层约 8.56 MB，宿主磁盘仍有约 3.3 TiB 可用
- 清理：E2E 后测试库只保留固定 Seed 员工 1 条，会话/消息/工作流/运行均为 0；18200/18280 无监听，无 Uvicorn/Vite/Playwright/Chromium 残留，持续 `docker stats` 采样进程已显式关闭。稳定 MySQL/RAGFlow 容器保持运行供后续任务复用
- GREEN：平台和 RAGFlow 两套管理脚本测试通过，ShellCheck 覆盖管理/测试/故障注入脚本；内存不足、非法资源值、端口冲突、平台 unhealthy 与 RAGFlow Compose 健康失败均有自动化，真实健康栈、固定镜像、资源采样、无头用户路径和清理状态提供生产同路径证据
- 遗留：无；下一任务 Q6-03 执行后端、前端、契约、构建、基础设施与全部无头 Playwright 套件的最终全量自动化

### Q6-03 全量自动化

- 状态：✅ 已完成
- 日期：2026-07-20
- 提交：本任务提交（见 Git 历史）
- 后端全量：显式设置 `TEST_BAILIAN_REAL=1`、真实 `TEST_RAGFLOW_BASE_URL=http://127.0.0.1:19380` 与 `v0.25.6` 后执行完整 pytest，最终 `396 passed in 89.71s`，此前 11 个按环境跳过的 RAGFlow 生命周期/公开 HTTP/会话检索、百炼成功与无效 Key、Deep Agents、会话停止重试、LangGraph 工作流和员工工具验收全部真实执行，没有 skip。Ruff lint、除已应用不可变 0005 外 151 个文件格式、严格 Mypy 145 个源/测试文件和 uv lock 全部通过
- 前端与契约：14 个 Vitest 文件 58 passed，ESLint、TypeScript、冻结 `pnpm install`、27 个顶层依赖解析、生产 Vite Build 和 OpenAPI/双 SSE/生成 TypeScript 逐字节漂移检查全部通过；构建如实保留 `errors` chunk 602.76 kB 的既有大于 500 kB 提示，不把 warning 隐藏或误报为失败
- 无头 Playwright：所有套件固定 `chromium-headless-shell`、单 worker、零重试顺序执行。默认 real 平台套件 2 passed in 35.0s，Demo 两轮引用/中断恢复 1 passed in 5.8s，React Flow 设计器 1 passed in 5.5s，手动运行成功/停止/知识失效 1 passed in 4.8s，设计→手动运行→员工触发→刷新详情跨页面闭环 1 passed in 8.0s；合计 6 项全部通过，未打开可见浏览器
- 基础设施与数据库：平台/RAGFlow 两套管理脚本门禁及 ShellCheck 全部通过。正式 `common_agent` 与隔离 `common_agent_test` 两库均为 `20260720_0006 (head)`，`alembic check` 均返回 `No new upgrade operations detected`；稳定七容器继续复用，声明健康检查的容器全部 healthy，没有因全量测试重建基础设施
- 执行异常与复验：首轮并行后端全量虽然自然结束，但调度层只返回进行中的点状输出且未保留最终句柄，因此没有采信该轮，单独完整重跑后才记录 396 项通过。首轮 Alembic 命令因 zsh 把未引号包裹的 `?charset` 当作 glob 而在进入 Alembic 前失败；单引号包裹完整 URL 后正式/测试库四项 revision/check 全部通过。两项均是验收命令问题，没有修改产品代码或降低门禁
- 清理：五个 E2E suite 的 finally 分别清理唯一知识库、员工、会话、工作流和运行；最终正式库/测试库都只保留固定 Seed 员工 1 条，会话/消息/工作流/运行为 0。18200/18280 无监听，无 pytest/Uvicorn/Vite/Playwright/Chromium 残留，dist、tsbuildinfo、测试产物和 Python 工具缓存已精确删除；独立 Docker context dangling 镜像为 0，固定 MySQL/RAGFlow 栈保持运行
- 遗留：无；下一任务 Q6-04 必须从空业务数据开始，由真实浏览器一次连续完成知识库→员工绑定→两轮知识对话→工作流设计→手动运行→员工触发，不以本任务各独立套件的组合结果替代总验收

### Q6-04 本机 MVP 验收

- 状态：✅ 已完成
- 日期：2026-07-20
- 提交：本任务提交（见 Git 历史）
- RED：先只增加公开 `pnpm test:e2e:mvp` 入口，首轮按预期以 exit 2 报告“不支持的 E2E suite：mvp-acceptance”，证明现有五个分散套件不能冒充一次连续总验收。实现编排后首次真实浏览器执行已从空数据走到最终运行详情，页面正确显示工作流输入 `COMMON_AGENT_Q6_04_WORKFLOW_*`、最终输出 `COMMON_AGENT_REAL_TWO_TURN_OK`，但测试错误沿用 start→end 工作流的“输出等于输入”假设，在最后一项等待 180 秒后失败；截图与页面实际值证明知识检索→AI 节点行为正确，收紧为“运行卡片验证原输入、详情验证知识工作流输出”后重新从空数据执行
- 空数据门禁：新增只用于验收前置的 `mvp_acceptance_empty`，经正式 MySQL 连接确认测试库除可选固定 Seed 外没有其他员工，会话、消息、引用、工作流定义/节点/边和运行全部为 0；再经 RAGFlow 官方数据集 API 确认知识库为 0。任何残留都会在启动应用和浏览器前关闭失败，不静默删除未知数据，也不把上轮清理后的内存状态当作空平台证据
- 单一用户旅程：新增独立 `mvp-acceptance` 无头 suite，同一个 Chromium 页面会话从“还没有知识库/还没有已保存工作流”开始：创建知识库、上传真实 TXT 并等到 RAGFlow completed；创建并绑定数字员工；新建会话连续两轮提问，两轮均经 RAGFlow 检索、真实 Deep Agents/百炼返回 `COMMON_AGENT_REAL_TWO_TURN_OK` 和文档引用，刷新恢复两轮历史；随后在 React Flow 拖入开始→知识检索→AI 对话→结束并真实连线，绑定同一知识库、校验保存、手动运行并得到知识标记；最后编辑同一员工保留知识库并授权该工作流，在原会话第三轮让真实模型调用工具，展开/刷新员工运行卡片并进入运行详情恢复输入与知识输出
- 生产同路径：最终 `1 passed in 19.3s`，全程只通过 `React -> Axios -> Uvicorn/FastAPI -> 应用服务 -> MySQL/RAGFlow/Deep Agents/LangGraph/阿里百炼` 的正式用户入口；浏览器网络监听确认没有直连 19380 或百炼域名。Guard 和 cleanup 只负责验收前置/后置，不准备业务对象或替代任何待交付步骤；没有 Mock/Fake、进程内客户端、直接仓储写入、DOM 注入或日志断言参与完成状态
- 编排与质量：统一 E2E 脚本新增唯一名称、空数据门禁、专属 Playwright 分支和 finally 清理，`frontend/package.json` 提供稳定调用入口。后端 Ruff、除不可变迁移外 153 个文件格式、严格 Mypy 147 个源/测试文件通过；前端 58 项 Vitest、ESLint、TypeScript、生产 Build 和 ShellCheck 通过，构建仍如实保留既有 602.76 kB chunk warning
- 清理：成功或失败均先关闭无头浏览器、Vite 和 Uvicorn，再按会话→员工→工作流→RAGFlow 数据集顺序精确清理本轮唯一名称。最终测试库只保留 Seed 员工 1 条，其余业务表为 0，18200/18280 无监听，无 Uvicorn/Vite/Playwright/Chromium 残留；首轮错误断言的截图/Trace 在人工核对并完成第二轮全链路 GREEN 后删除，成功产物、dist、tsbuildinfo 和项目缓存同样删除，稳定 MySQL/RAGFlow 继续复用
- 遗留：无；下一任务 Q6-05 做最终规格、假绿、泄密、无用代码、资源和残留进程复审，在没有真实证据的地方不得把 MVP 标为交付

### Q6-05 规格与质量复审

- 状态：✅ 已完成
- 日期：2026-07-20
- 提交：本任务提交（见 Git 历史）
- 规格 RED：逐项核对 `product-scope.md` 时发现 4.5 已要求工作台显示后端、模型、RAGFlow 和运行模式，但现有公开入口只有 `/system/health`，前端只显示后端/模式，既不能看到百炼配置状态也不能区分 RAGFlow 未配置与不可用。先写正式 Uvicorn/OpenAPI 测试得到 2 failed、14 passed，公开 `/api/v1/system/status` 实际 404；前端先要求严格解析和三项状态展示，得到 5 failed，证明不是在已有实现上补绿断言
- 状态链路：新增 `SystemService` 和严格 `/api/v1/system/status` 契约；后端始终报告自身可用，real 模式只把百炼标为“已配置”而不伪造无副作用健康探测，RAGFlow 则经正式 `KnowledgeService.status()` 返回 provider、available/unconfigured/unavailable、版本和稳定错误码，未知异常关闭失败且不泄漏 detail；Demo 明确显示三项演示状态。React 顶栏改走新入口并展示“后端正常 / 百炼已配置 / RAGFlow 正常”或对应真实降级状态，总验收同时断言三项 real 标签
- 供应链 RED 与修复：`uv audit --frozen` 发现 `asyncmy 0.2.11` 的同一 SQL 注入漏洞以 GHSA/PYSEC 两个别名报告，且上游尚无修复版本。先把正式 URL 门禁改为 `mysql+aiomysql` 期望，真实得到 12 failed、24 passed；随后把 SQLAlchemy async 驱动切换到官方支持的 `aiomysql 0.3.2`，直接约束 PyMySQL `>=1.1.1`，锁文件实际解析为 PyMySQL 1.2.0，并同步配置、测试、正式 E2E 与当前架构规则。驱动切换后配置/真实 MySQL 边界 42 passed，`uv audit --frozen` 为 81 个包无已知漏洞/不良项目状态，前端 `pnpm audit --prod` 同样无已知漏洞
- 最终自动化：显式启用真实 RAGFlow v0.25.6、Deep Agents 和阿里百炼后，后端全量 401 passed in 100.24s、没有 skip；Ruff、排除已应用不可变 0005 后的 155 个文件格式、严格 Mypy 149 个源/测试文件、uv lock 全部通过。前端 14 个 Vitest 文件 61 passed，ESLint、TypeScript、生产 Build、OpenAPI/双 SSE/生成 DTO 逐字节漂移均通过；平台/RAGFlow 管理脚本、ShellCheck、`git diff --check` 通过。开发库和测试库都为 `20260720_0006 (head)`，两次 `alembic check` 均无新操作
- 生产同路径复验：切换数据库驱动和状态入口后，重新从空业务数据执行唯一 `pnpm test:e2e:mvp`，固定 `chromium-headless-shell`、单 worker、零重试，最终 1 passed in 21.2s；同一真实浏览器旅程完整经过知识库创建/上传/解析、员工绑定、两轮检索对话与引用、工作流拖拽/连线/保存/手动运行、员工授权/工具触发及刷新恢复，同时看到真实三项系统状态。测试后再次通过正式 MySQL 和 RAGFlow 空数据门禁，证明不是用上一轮残留状态假绿
- 范围与无用代码：前端正式路由只保留聊天、知识库、数字员工和工作流四个入口；公开 OpenAPI 只包含这四类 MVP API、运行记录及系统状态，没有登录/注册/RBAC、Skill、LiteLLM、多模型、任务中心、桌面壳/自动更新或远程部署实现。生产源码没有 TODO/FIXME/HACK、`NotImplementedError` 或空业务函数；扫描命中的 placeholder 是正常输入框/助手预留消息术语，`pass` 是无状态异常类、SQLAlchemy Base 或无资源可关的 Demo `aclose`，测试 support 中的 `NotImplementedError` 只用于协议最小桩和失败定位
- 安全与仓库：`masterAventador/common-agent` 复核为 PRIVATE、默认分支 main；版本化环境文件只有公开样例和用户批准的后端 `.env.demo`。逐 revision 用授权 Demo Key 精确扫描，Key 未出现在例外文件之外，也未进入前端生产产物；通用高风险模式只命中一处明确的 `sk-a4-02-must-not-leak` 失败测试夹具。错误、repr、HTTP 契约和浏览器端继续不暴露模型 Key、数据库密码或 RAGFlow 凭据
- 资源与清理：最终 18200/18280 无监听，无 Uvicorn、Vite、Playwright 或 Chromium 进程；测试库及 RAGFlow 回到空业务基线。精确删除 dist、tsbuildinfo、pytest/Ruff/Mypy/Python 缓存和空验收目录；独立 Docker context 的平台 MySQL 与 RAGFlow 六服务共七个稳定容器保持复用，五个声明健康检查的容器 healthy，dangling 镜像与 Build Cache 都为 0，没有重复任务镜像可删，宿主磁盘约 3.3 TiB 可用
- 已知非阻塞项：生产构建仍如实报告 `errors` chunk 602.76 kB 超过 500 kB 的性能提示，但不影响正确性或 MVP 交付；百炼状态刻意表达“配置已就绪”而不是用额外模型请求伪造实时健康，实际可用性继续由每次真实会话和稳定错误码判断
- 文档边界：规格核对未改变产品功能或边界，因此没有修改 `docs/product-scope.md`；所有任务状态、RED/GREEN、真实证据和遗留只写入本路线图

### R8-00 百炼向量/重排迁移与本地模型退场

- 状态：✅ 已完成
- 日期：2026-07-20
- 提交：本任务提交（见 Git 历史）
- RED 与契约收口：新增迁移测试最初因 `RagFlowBailianIndexMigrator` 不存在而收集失败；实现首轮又真实暴露空筛选被误判为知识库缺失，修复后迁移单元测试转绿。后端全量首轮 401 passed/1 failed，正式 Uvicorn 知识库测试仍按旧创建载荷断言，补入强制 `text-embedding-v4@Tongyi-Qianwen` 后定向与全量复跑通过，没有放宽新契约
- 官方依赖与源码完整性：新增 `third_party/ragflow` 官方 Git submodule，固定 `v0.25.6` 提交 `8f0632c8d9efacbcd11aaf6e0f4cb634169bfea4`；管理脚本在 origin、tag、commit、工作区或暂存区漂移时关闭失败，不再运行时临时 clone。RAGFlow submodule 最终 `git diff`/`git diff --cached` 均为空，官方 Compose、镜像内容、安装包和源码没有修改或补丁
- 百炼模型接入：只经 RAGFlow 官方 UI/API 注册 `text-embedding-v4` 与 `qwen3-rerank`，设置 `Tongyi-Qianwen` 租户默认值；工作空间兼容地址严格转换为对应原生 `/api/v1`，loopback 客户端忽略系统代理。新知识库创建显式携带 embedding ID，每次平台检索显式携带 rerank ID；配置只接受这两个锁定值。`check-bailian` 最终报告 embedding/rerank/defaults 全部 ready，错误、CLI、状态对象和测试输出均不回显百炼 Key 或上游响应体
- 索引迁移与恢复：新增只读 `plan-bailian-migration` 和需 `RAGFLOW_CONFIRM_BAILIAN_REINDEX=yes` 的显式 `migrate-bailian`；支持知识库 ID 白名单、100 文档分批、1-86400 秒有限等待。迁移先分页盘点所有知识库/文档，任何文档正在解析时在首个写请求前拒绝；随后经 RAGFlow v0.25.6 公开数据集更新与文档 parse API 更新 embedding 并全量重建，保留原文件，失败、取消、限流、超时或中断只返回脱敏阶段码，同一命令会再次重建全部目标文档以恢复。费用确认、数据传输和限流边界已写入本机栈说明
- 真实数据与中文质量：迁移前后两次只读盘点均为 `datasets=0, documents=0, model_updates=0, busy_documents=0`，证明没有保留用户知识库需要变更，也没有把测试数据冒充既有迁移。隔离真实验收创建 3 份中文文档（正确口令、相似干扰、无关内容），首次阿里百炼向量召回与 `qwen3-rerank` 将唯一正确文档排首；随后对同一知识库执行官方全量索引重建，再次检索仍将正确文档排首，`1 passed in 13.27s`，finally 删除唯一测试知识库
- 本地模型与资源：正式 Compose、管理脚本和文档移除 TEI/BGE-M3/本地 rerank 服务、profile、24 GiB 容器上限、权重挂载、19386 端口、路径、下载/检查和启停入口，磁盘扫描没有本地 safetensors/bin/onnx 权重。独立 Colima 已从 48 GiB 调整为暂定 32 GiB，真实重建后平台 MySQL 与 RAGFlow 五容器合计约 6.25 GiB；RAGFlow API/ES/MySQL/MinIO/Valkey 分别约 3.819 GiB/1.487 GiB/410 MiB/70 MiB/3.9 MiB，五容器均 0 restart、`OOMKilled=false`。这只完成 R8-00 基础证明，完整冷启动、会话、工作流、峰值与 30 分钟 soak 仍由 R8-04 决定是否长期保留 32 GiB
- 自动化与工具：相关配置/适配器/迁移 77 passed，最终 RAGFlow 单元 37 passed；后端全量 `402 passed, 12 skipped`，12 项均为需显式外部开关的既有真实门禁，本任务另行显式执行真实 RAGFlow/百炼重建。Ruff 全仓 lint、本轮 10 个 Python 文件格式、严格 Mypy 151 个源/测试文件、uv lock、OpenAPI/事件/前端 DTO 漂移、RAGFlow 管理脚本、Bash 语法、ShellCheck 0.11.0、`git diff --check` 和 submodule 完整性全部通过。全仓格式检查仍会提示一个与本任务无关、已提交的不可变 migration `20260720_0005_workflow_runs.py`，本轮未改写历史迁移
- 资源与清理：为全量集成门禁补拉并启动项目锁定的 `mysql:8.4.10`，平台 MySQL 与五个 RAGFlow 容器继续在专属 32 GiB context 复用；没有启动前端、可见浏览器或长期测试进程，RAGFlow 临时知识库清理后回到 0。官方活动镜像全部有运行容器引用，Build Cache 为 0，未删除仍需复用的基础镜像；被 submodule 取代的 132 MiB Git 忽略旧 checkout 不参与运行，留给 D8-01 的统一 `clean` 做可预览、精确清理
- 遗留：统一 `demo-light` 的 `doctor/setup/up/status/stop/clean`、8-12 GiB 门禁和全新克隆验证由下一任务 D8-01 交付；32 GiB real 的完整峰值与 soak 不在本任务伪装完成，由 R8-04 保持未开始

### D8-01 全新克隆一键 Demo

- 状态：✅ 已完成
- 日期：2026-07-20
- 提交：本任务提交（见 Git 历史）
- RED：统一入口契约首先按预期报告“缺少统一的 demo-light 开发入口”。首轮 `doctor` 又真实发现全局 pnpm 为 10.33.0、与项目锁定的 11.9.0 漂移；改为 `npx pnpm@11.9.0` 后不修改全局工具。首轮真实 `up` 虽在当前命令内健康，但命令退出后 Uvicorn/Vite 被会话回收，改用两个项目专属 launchd 标签后跨命令复查健康。临时新克隆首次复用平台 MySQL 时，Compose 提示现有 Volume 与新 checkout 路径不一致并询问是否重建；新增行为测试先失败，再让管理脚本读取并复用现有 Volume 的真实 bind 目录，显式冲突关闭失败且禁止自动重建/迁移
- 统一入口：新增可执行 `scripts/dev.sh`，提供 `doctor/setup/up/status/stop/clean`。`setup/up` 校验 Node >=22、uv、Docker/Colima、RAGFlow submodule 和两份锁文件，以 `uv sync --frozen`、固定 pnpm 11.9.0 安装；`up` 显式使用 `COMMON_AGENT_INTEGRATION_MODE=demo`，启动平台 MySQL、FastAPI 与 Vite并显示 loopback 地址。状态检查同时核对实际 Docker 内存、MySQL health、launchd 标签和 HTTP health；端口被非本入口进程占用时拒绝启动
- 资源与模式边界：复用同一个项目专属 `common-agent-dev` profile，但切换到 Demo 前先停止本项目 RAGFlow 和平台容器，再停止/重启虚拟机；Docker 实际 `MemTotal=12,514,689,024` bytes（约 11.66 GiB），门禁仅接受 8-12 GiB。运行态只有 `common-agent-platform-mysql` 一个容器，后端 Health 返回 `integration_mode=demo`，RAGFlow 五容器保持停止；完整 real 仍由后续 D8-03 在同一 profile 切回暂定 32 GiB，12 GiB 不冒充真实知识链路或 RAGFlow 验收
- 全新克隆：在 `/private/tmp/common-agent-d8-01.aVjBKl` 创建独立递归 Git 克隆，官方 RAGFlow submodule 精确为 `8f0632c8d9efacbcd11aaf6e0f4cb634169bfea4 (v0.25.6)`；启动前确认没有 `backend/.venv` 和 `frontend/node_modules`。只执行统一 `up` 后从零创建 Python 3.12 环境并安装锁定的 81 个 Python 包、379 个前端包，pnpm 实际为 11.9.0；跨命令 `status` 的 Colima/MySQL/FastAPI/Vite 四项全部健康
- 页面验收：同一临时克隆固定使用无窗口 `chromium-headless-shell`、单 worker、零重试，经正式 React 页面、Axios/SSE、loopback FastAPI、平台 MySQL 和显式 Demo 适配器完成两轮带引用对话，并验证中断后的正式重试恢复，最终 `1 passed (8.2s)`；Demo 不调用 RAGFlow、Deep Agents 或百炼，因此这些真实外部依赖对本任务不适用，不能把本结果用于解除 D8-03/R8-04 的 real 门禁
- GREEN：`scripts/test-dev.sh`、平台 MySQL 管理脚本测试、Bash 语法、ShellCheck 和 `git diff --check` 通过；新克隆安全复用原平台 Volume 的自动化覆盖原目录复用与显式目录冲突。实际验证了 profile 停止/12 GiB 重启、RAGFlow 停止、依赖冷安装、进程跨终端存活、HTTP 健康、两轮浏览器会话、测试数据 finally 清理和统一 clean
- 清理：无头用例精确删除本轮会话、员工和固定 Seed；统一 `clean` 只按两个 launchd 标签、固定 Compose project/container/network 和固定运行目录清理，最终 18200/18280 无监听、两个标签不存在、项目专属 Colima 已停止。临时克隆目录已删除；根工作区中被官方 submodule 取代的旧 RAGFlow checkout 也在确认官方 origin 后删除。平台 MySQL/RAGFlow 数据目录、冻结依赖缓存、Colima 磁盘和官方镜像保留，没有删除 Volume 或用户业务数据
- 遗留：无；下一任务 D8-02 让 Demo 知识库、文档和检索状态在后端重启后与已持久化员工/会话引用保持一致

### D8-02 Demo 知识状态持久语义

- 状态：✅ 已完成
- 日期：2026-07-20
- 提交：本任务提交（见 Git 历史）
- RED：新增正式 Uvicorn/MySQL 重启用例：第一进程经公开 API 创建 Demo 知识库、上传文档、绑定员工并完成第一轮带引用会话，彻底停止后以同一数据库启动第二进程；现状按预期在知识库列表断言失败，原 ID `b8b66da8787b43efba311f0e38b228a5` 对应的重启后集合为空，证明持久员工与消息正在引用已被进程退出清空的内存知识。没有用直接调用适配器或 Mock 冒充跨进程缺陷
- 持久边界：新增不可变迁移 `20260720_0007`，平台 MySQL 增加 `demo_knowledge_bases` 与 `demo_knowledge_documents`；保存知识库名称/说明/创建顺序、文档名称/大小/正文/解析状态/稳定错误码和创建顺序。主键、唯一名称、字段长度、20 MiB 上限、状态/错误组合、文档归属外键和查询索引受 MySQL 约束，文档随知识库级联；员工表仍保存通用不透明 ID，不建立 Demo 专用外键，也不影响 real 的 RAGFlow 权威边界
- 端口与适配：新增平台自有 `DemoKnowledgeRepository`/Unit of Work 端口和 SQLAlchemy 实现；`DemoKnowledgeService` 继续实现与 RAGFlow 相同的 `KnowledgeService`，但所有 CRUD、列表、完成态和检索正文经事务读写 MySQL。重复名称仍返回 `knowledge_request_rejected`，失效 ID 返回 `knowledge_base_not_found`，写入冲突返回 `document_upload_failed`；`aclose()` 只关闭当前适配器实例，不再删除已提交知识数据。RAGFlow submodule 和上游源码保持未修改
- 重启一致性：正式测试在第二个独立 Uvicorn 进程中读取同一知识库 ID、完成态文档和员工绑定，第一轮已持久化消息引用仍指向同一知识库/文档；随后发送第二轮消息，Demo 运行时从恢复的历史识别为“第 2 轮”，重新检索到同一文档并生成同源引用，最终 `1 passed in 4.49s`。内存级测试也以两个独立服务实例证明关闭/重开不会改变仓储状态
- 页面与清理语义：无头 `chromium-headless-shell` 继续从正式 React 页面完成知识库创建/上传、员工绑定、两轮引用、断流和重试，最终 `1 passed (5.5s)`；浏览器未直连 RAGFlow 或百炼。E2E finally 现在显式按唯一名称删除持久 Demo 知识库，不再依赖后端退出自动消失，输出确认会话、员工、知识库和固定 Seed 全部清理
- GREEN：迁移/系统入口/Demo 重启/适配器定向 `16 passed, 1 skipped`，唯一 skip 是本任务不启动的真实 RAGFlow 状态探测；后端全量 `403 passed, 12 skipped in 65.47s`，12 项都是需显式 real/RAGFlow/百炼开关的既有门禁，本任务的 Demo 重启与页面门禁没有 skip。Ruff 全仓、156 个文件格式、严格 Mypy 155 个源/测试文件、uv 82 包锁、OpenAPI/生成 DTO 漂移、E2E 脚本 ShellCheck、Bash 语法和 `git diff --check` 全部通过
- 数据库与清理：正式 `common_agent` 和隔离 `common_agent_test` 均由应用 lifespan 升到 `20260720_0007 (head)`，两次 `alembic check` 都返回无新操作。最终两库 Demo 知识库/文档均为 0，测试库会话/消息为 0；18200/18280 无监听、两个项目 launchd 标签不存在，平台容器/网络已删除，12 GiB 项目专属 Colima 已停止。MySQL/RAGFlow 数据目录、Colima 磁盘与官方镜像保留
- 遗留：无；下一任务 D8-03 在不泄漏凭据的前提下提供完整 real 模式一键体检、32 GiB 切换、健康/费用诊断和本机真实纵向链路

### D8-03 real 模式一键体检与启停

- 状态：✅ 已完成
- 日期：2026-07-20
- 提交：本任务提交（见 Git 历史）
- RED：新增 `scripts/test-real.sh` 后首轮按预期以“缺少统一的 real 开发入口”失败；Token 文件单元测试首轮 3 项因 `RagFlowModelConfigurator.ensure_api_token` 尚不存在失败，随后实现公开 Token 查询/创建、有效性探测和原子 0600 落盘后转绿。首次真实 `up` 进一步暴露旧 macOS bind Volume 在 Colima 重启后映射为容器内 `root:root`，RAGFlow MySQL 因不能写 `binlog.index` unhealthy；物理复制到 Linux 原生 Volume 又真实暴露数据字典 `lower_case_table_names=2` 与 Linux `0` 不兼容，没有删除数据或用空库绕过
- 统一入口与体检：新增可执行 `scripts/real.sh doctor/setup/up/status/cost/stop`，固定项目 `common-agent-dev` profile/context、8 CPU、暂定 32 GiB/100 GiB 磁盘和 loopback 端口；检查 Node/uv/pnpm、两份锁、RAGFlow 官方 submodule origin/tag/commit/工作区、磁盘、端口、平台 MySQL、五个 RAGFlow 容器、重启/OOM、FastAPI real 状态和 Vite。百炼诊断只报告 `provider=bailian`、北京业务空间、聊天/embedding/rerank 模型、60/60/2 超时重试和凭据存在状态，不输出 Key 或业务空间主机标识
- Token 与凭据：复用现有 RAGFlow 本地会话，只经 v0.25.6 公开 `/api/v1/system/tokens` 与公开数据集探测查询/创建/验证 API Token；Token 原子写到 Git 忽略的项目本地文件，父目录 0700、文件实测 0600，symlink、错误权限、无效前缀和失效 Token 关闭失败。launchd 任务只拿脚本路径，后端子进程启动时读取文件；CLI、费用诊断、状态、测试和日志均不打印 Token/百炼 Key
- 稳定数据卷：外围 Compose 把 Elasticsearch、MySQL、MinIO、Valkey 切到项目专属 Colima 原生 external Volume。首次迁移停止并重建外围容器，前三者/Valkey 从旧卷只读复制；旧 MySQL 先只读复制到 Git 忽略快照，再以同版本 8.0.39 从快照逻辑导出 `rag_flow`，导入原生 v3 Volume，跨越 macOS 大小写字典边界。旧 bind 目录、旧 Volume、快照和中间物理复制均保留；目标就绪标记让重复 `up` 直接复用。最终完整 `stop → Colima 关闭 → up` 后五容器再次 healthy，全部 `restarts=0`、`oom=false`
- 真实模式与费用：`up` 先按锁文件幂等安装，复用本地 `infiniflow/ragflow:v0.25.6` 镜像和稳定数据，再配置并验证 `text-embedding-v4`、`qwen3-rerank` 与租户默认绑定；RAGFlow 容器健康早于账号 API 完全就绪的竞态由 60 秒有限重试吸收，失败只保留阶段码。`cost` 明确聊天、embedding、rerank 的百炼按量计费、数据外发区域、实时价格来源、重试/限流/超时恢复边界，并只读报告 `datasets=0, documents=0` 和容器内存；不启动或回退到任何本地 embedding/rerank
- 64 GiB 本机验收：项目专属 Docker 实际 `MemTotal=33,585,893,376` bytes（约 31.28 GiB）。同一无头 Chromium、单 worker、零重试从空业务数据经正式 React/FastAPI/MySQL/RAGFlow/Deep Agents/百炼连续完成知识库上传与向量化、员工绑定、两轮带引用检索会话、工作流设计/手动运行和员工工具触发，最终 `1 passed (22.6s)`，finally 删除工作流与知识库。验收不连接 128 GiB Mac，也没有远程依赖；其他电脑只能 checkout 同一 Git revision 独立运行同一门禁
- 资源与失败边界：稳定采样 RAGFlow API/ES/MySQL/MinIO/Valkey/平台 MySQL 约为 4.124 GiB/1.419 GiB/394.2 MiB/73.77 MiB/4.051 MiB/486.3 MiB，合计约 6.50 GiB；五个 RAGFlow 容器无重启或 OOM。模型限流/有限重试/请求与分块超时/5xx/空流、RAGFlow 超时/服务失败/非法响应和脱敏恢复定向 `53 passed`；费用命令不硬编码易漂移单价，金额以执行时百炼控制台为准
- GREEN：后端全量 `407 passed, 12 skipped in 64.99s`，12 项仍是需显式外部开关的分层真实测试，本任务已由唯一完整 MVP real 浏览器门禁解除纵向链路风险；Ruff lint、排除已应用不可变 0005 后 162 个 Python 文件格式、严格 Mypy 155 个源/测试文件、uv 82 包锁通过。前端 14 files/61 tests、ESLint、TypeScript、Build、OpenAPI/生成 DTO 漂移和 pnpm frozen lock 通过；`test-real.sh`、两类 `test-manage.sh`、`test-dev.sh`、项目全部 ShellCheck、Alembic 无漂移、Bash 语法、`git diff --check` 和 RAGFlow submodule 完整性通过
- 清理：真实 E2E 产物和业务数据已由 finally 删除，RAGFlow 迁移计划回到 0 知识库/0 文档；最终 real launchd 前后端、平台/RAGFlow 容器和 32 GiB Colima 已停止，释放当前 64 GiB 电脑内存。稳定原生 Volume、旧卷/迁移快照、0600 Token、冻结依赖和官方镜像保留，未删除用户数据；无临时 MySQL 探针或迁移容器残留
- 遗留：32 GiB 只证明当前功能链路和跨重启可用，完整峰值不高于 25 GiB、30 分钟 soak、持续 Swap 和中文质量/费用基线仍由 R8-04 保持未开始；下一任务 H7-01 建立 CI 基线，之后按路线图进入覆盖率、平台自有消息/模型/图执行协议与第三方类型边界

### H7-01 本地质量门禁与可选 GitHub CI 镜像

- 状态：✅ 已完成
- 日期：2026-07-20
- 提交：本任务提交（见 Git 历史）
- 权威边界：项目验收只依赖本机可复现命令和实际运行结果，不依赖 GitHub Hosted Runner、付费额度或 `gh` 查询结果。`.github/workflows/ci.yml` 只是同一组命令的 PR/main 可选镜像；Hosted Runner 不可用时不降级、不伪造通过，也不阻断按本机证据完成任务。真实 RAGFlow/百炼门禁继续由 `scripts/real.sh up` 与 `pnpm test:e2e:mvp` 显式执行，公共 CI 不自动产生外部费用
- RED：新增 `scripts/test-ci.sh` 后首次按预期以“缺少 PR/main GitHub CI workflow”失败。实现推送后 GitHub 创建了三个 Check Run，但均在执行任何 Step 前被账户级 `recent account payments have failed or your spending limit needs to be increased` 拒绝；该结果证明 Hosted Runner 服务不可用，不是代码或测试失败，按用户明确边界不付款、不提高额度，也不把远端状态纳入项目验收
- 门禁实现：新增后端、前端、Demo/契约/基础设施三组隔离任务，Action 固定到不可变提交，uv 0.11.16、Python 3.12、Node 22、pnpm 11.9.0 固定；缓存分别绑定 `backend/uv.lock` 和 `frontend/pnpm-lock.yaml`，所有安装均 frozen，禁止 `continue-on-error` 或管道吞错。Demo 只运行显式固定适配器；RAGFlow 官方 submodule 递归检出但不修改源码
- 跨平台复用：平台和 RAGFlow 管理脚本测试新增可覆盖的测试 Docker context，浏览器 E2E 新增 `COMMON_AGENT_E2E_DOCKER_CONTEXT`；macOS 默认仍使用项目专属 `colima-common-agent-dev`，Linux 可使用 `default`，没有复制或维护第二套验收逻辑。`scripts/test-ci.sh` 固定检查触发器、任务、版本、锁文件缓存、Action 提交、不可变迁移排除、ShellCheck、Demo 和 real 隔离契约
- 本机 GREEN：CI 锁定的 uv 0.11.16 完成 frozen sync、Ruff lint、排除已应用不可变 0005 后 162 个文件格式、严格 Mypy 155 个源/测试文件、uv lock 和 81 个包安全审计；后端全量 `407 passed, 12 skipped in 65.93s`，12 项均为需显式 real 开关的既有真实门禁。锁定 pnpm 11.9.0 完成 frozen install、前端 14 files/61 tests、ESLint、TypeScript、生产 Build、契约漂移和依赖审计且无已知漏洞；两类基础设施管理脚本、`test-dev.sh`、`test-real.sh`、`test-ci.sh`、全部项目 ShellCheck、Bash/YAML 语法与 `git diff --check` 通过
- Demo 验收与清理：项目专属 Colima 仅以 12 GiB demo-light 启动；无头 Chromium 经正式 React/FastAPI/MySQL 和 Demo 适配器完成两轮带引用会话及中断恢复，`1 passed (6.0s)`，finally 清理唯一会话、员工、知识库和固定 Seed。随后平台容器、网络与 Colima 已停止，18200/18280 无项目进程；MySQL/RAGFlow 数据、冻结依赖和官方镜像保留
- 遗留：无；下一任务 H7-02 在同一本机权威门禁上记录真实行/分支覆盖率基线并补足缺口，GitHub Hosted Runner 仍只作可选镜像

### H7-02 自动化覆盖率门禁

- 状态：✅ 已完成
- 日期：2026-07-20
- 提交：本任务提交（见 Git 历史）
- RED 与真实基线：新增 `scripts/test-coverage.sh` 后首轮按预期以“缺少可执行的本机权威覆盖率入口”失败。前端首次完整 V8 采集为行 86.17%、分支 75.00%，已超过 80% 目标。后端首次只采 pytest 主进程为总体行 83.22%、分支 65.24%，低于 85%；报告同时显示现有正式 Uvicorn 子进程集成测试已经执行的 API、仓储和应用装配没有被计入，不能用重复测试或排除生产文件掩盖采集缺口
- 子进程采集：按 pytest-cov 7.1/coverage.py 7.15 官方机制启用 `patch = ["subprocess"]`、`sigterm = true`、branch 与 relative source；由现有集成测试启动的独立 Uvicorn 进程继承采集并在 SIGTERM 时保存，pytest-cov 合并并继续覆盖同一 5,375 条生产语句。修复后后端总体行从 83.22% 提升到稳定 90.90% 以上，不是修改业务实现、增加重复测试或通过 omit 缩小分母
- 本机权威入口：新增 `scripts/coverage.sh backend/frontend/all`。后端一次 pytest 生成 term、JSON、XML，再由严格类型的 `check-backend-coverage.py` 分别聚合全部生产包和 `domain/application` 核心层；前端固定 pnpm 11.9.0 执行 Vitest V8。新增 `scripts/test-coverage.sh` 固定依赖、生产范围、六项阈值、报告忽略和可选 CI 复用契约；把四项阈值故障注入为 100% 时会明确非零失败
- 不回退阈值：后端总体行不低于 90.90%、总体分支不低于 72.20%、核心行不低于 93.17%、核心分支不低于 74.26%，均高于路线图 85%/90% 的行覆盖率目标；前端行不低于 86.17%、分支不低于 75.00%，高于 80% 行目标。阈值锁在本轮可复现基线，后续新增生产代码或减少测试会直接失败，不能只保留宽松最低目标
- 依赖与可选镜像：后端冻结新增 pytest-cov 7.1.0 与 coverage 7.15.2，前端冻结与 Vitest 完全同版的 `@vitest/coverage-v8` 4.1.10。PR/main workflow 后端直接复用 `./scripts/coverage.sh backend`，前端执行同一 `pnpm test:coverage` 配置；GitHub Hosted Runner 仍只是可选镜像，本机 `coverage.sh all` 才是当前权威结果
- GREEN：唯一入口最终后端 `407 passed, 12 skipped in 127.99s`，12 项均为需显式 real 开关的既有外部门禁；总体行 90.92%、分支 72.20%，核心行 93.18%、分支 74.26%。前端 14 files/61 tests，行 86.17%、分支 75.00%。新增解析器和后端通过 Ruff lint、163 个文件格式及严格 Mypy 156 个源/测试文件；uv lock、83 包审计、前端 ESLint/TypeScript/Build/pnpm audit、ShellCheck、CI/覆盖率契约和 `git diff --check` 全部通过
- 报告与清理：后端 JSON/XML 只写入 Git 忽略的 `.local/coverage/backend`，前端 summary 只写入已忽略的 `frontend/coverage`，`git check-ignore` 已实证且没有报告进入暂存范围。覆盖率使用的项目专属 12 GiB demo-light、平台 MySQL、网络和前后端 launchd 进程最终全部停止，释放内存；稳定数据、冻结依赖和官方镜像保留
- 遗留：无；下一任务 H7-03 定义平台自有消息与模型协议，把 LangChain/供应商类型完整收回适配层

### H7-03 平台自有消息与模型协议

- 状态：✅ 已完成
- 日期：2026-07-20
- 提交：本任务提交（见 Git 历史）
- RED：在既有模型契约测试中先要求 `ModelMessage/ModelRequest/ModelStreamEvent`，首次定向执行因平台模块无法导入这些类型而在收集阶段按预期失败；实现最小协议后 3 项转绿。迁移工作流时再增加缺少终态、空终态、重复终态和终态后增量四种协议失败，证明平台节点不会把不完整供应商流误写为成功
- 平台协议：`models/base.py` 只用标准库定义不可变 system/user/assistant `ModelMessage`、非空 `ModelRequest`、非空 `ModelStreamDelta`、唯一 `ModelStreamCompleted`、增量/终态联合类型、稳定安全错误家族、错误翻译和幂等异步释放；不导入 LangChain、OpenAI、Deep Agents 或供应商 SDK。运行时协议检查和构造边界拒绝空消息、非法角色、空请求及空增量
- 百炼转换：`BailianChatModelAdapter` 的正式端口只接受平台请求并返回平台事件；在适配器内部把三种平台角色转换为 LangChain System/Human/AI Message，把供应商 Chunk 正文转换为平台增量，并且只有非空流正常结束才发完成终态。认证/权限、请求拒绝、限流/连接/超时/5xx、空响应和首个增量后的中断继续转换为原稳定错误码，错误与事件不携带上游响应、Key 或提示词
- Deep Agents 边界：移除平台 `StreamingChatModel.chat_model: BaseChatModel` 泄漏；新增 `adapters/model/langchain.py` 的适配层内部 `LangChainChatModelProvider`，只允许百炼与 Deep Agents 两个外围适配器传递 Deep Agents 官方 API 当前必需的 `BaseChatModel`。Deep Agents 继续在适配层把平台历史转换为 Human/AI Message、把 AIMessage/Chunk 转为平台 Runtime delta/终态，并翻译错误、停止与释放；application/domain/conversations/workflows/runtimes 不消费该桥
- 工作流消费：AI 节点现在构造平台 system/user 请求，只累计平台增量；必须恰好看到一个完成终态且正文非空才提交节点输出。已有增量后无终态映射为可重试 `model_stream_interrupted`，无增量完成、重复完成、完成后输出或未知事件映射为 `model_response_invalid`。Demo 模型同样实现平台增量和终态，不保留 LangChain 类型捷径
- 自动边界：模型契约增加 AST 扫描，生产 `adapters/` 之外禁止导入 `langchain/langchain_core/langchain_openai/openai/deepagents`；最终扫描只剩百炼、Deep Agents 和工具适配器内部第三方导入。架构文档明确平台协议、唯一完成终态和适配层内部桥，产品范围没有变化，RAGFlow 官方 submodule 与源码未修改
- GREEN：平台协议/工作流定向 28 passed，百炼/Deep Agents/Demo/工作流适配定向 41 passed；后端全量 `414 passed, 12 skipped in 64.05s`，12 项为显式 real 分层门禁。覆盖率全量 `414 passed, 12 skipped in 130.26s`，总体行 90.98%、分支 72.58%、核心行 93.18%、核心分支 74.26%，未降低 H7-02。Ruff lint、排除不可变 0005 后 163 个文件格式及严格 Mypy 156 个源/测试文件通过；Demo 正式浏览器两轮会话与恢复 `1 passed (6.2s)`
- 真实回归：在项目专属 32 GiB real 栈上显式启用而非依赖默认 skip，一次执行真实百炼适配、Deep Agents 流/协作停止/错误、会话 HTTP/SSE、RAGFlow+百炼工作流编译、手动工作流运行和员工 allowlist 工具触发共 `6 passed in 37.54s`。六项均经正式适配器/API/MySQL/RAGFlow/百炼路径完成并由 finally 删除唯一数据，没有 Mock/Fake 或 GitHub Runner 结果
- 清理：Demo 与 real 测试 finally 已删除会话、员工、知识库和工作流唯一数据；real 前后端、平台/RAGFlow 容器及项目专属 32 GiB Colima 最终停止，释放当前电脑内存。稳定数据、0600 Token、冻结依赖和官方镜像保留；覆盖率报告只在 Git 忽略目录生成并在提交前精确删除
- 遗留：无；下一任务 H7-04 定义平台自有图编译、执行、节点观察、停止与结果协议，把 LangGraph 类型和运行状态收回 `adapters/workflow/langgraph/`

### H7-04 平台自有图执行协议

- 状态：✅ 已完成
- 日期：2026-07-20
- 提交：本任务提交（见 Git 历史）
- RED：先新增平台图执行契约测试，首次定向执行因 `common_agent.workflows.execution` 不存在而在收集阶段按预期失败；同一契约同时扫描生产包，要求只有 `adapters/workflow/langgraph/` 能导入 LangGraph。实现后平台协议、LangGraph 适配器、应用服务与员工工具定向首轮 `30 passed`
- 平台协议：新增 `workflows/execution.py`，仅用平台类型定义可运行时检查的 `WorkflowCompiler/CompiledWorkflow`、节点观察器、停止信号与幂等停止令牌、不可变节点输入/输出及最终结果。非空输入/输出、知识类型、已完成节点唯一性与步数一致性在构造边界关闭失败，不保留 LangGraph 兼容捷径
- 适配层收口：删除平台包的 `workflows/compiler.py` 和 `workflows/state.py`，把 `StateGraph`、START/END、Runtime context、TypedDict 图状态、节点包装、停止竞速、递归上限与编译/运行异常翻译全部移入 `adapters/workflow/langgraph/`。平台节点注册表改为只处理 `WorkflowNodeExecutionContext/Result`，节点 ID、完成顺序和步数由适配器投影
- 应用边界：`WorkflowService` 现在只注入平台 `WorkflowCompiler` 端口，并使用平台观察器、停止令牌和结果；缺少编译器/事件端口直接拒绝运行。FastAPI 装配根才实例化 `LangGraphWorkflowCompiler`，手动触发、员工 allowlist 工具、节点观察、协作停止、错误码和持久摘要语义不变
- 边界门禁：新增 AST 扫描硬性禁止适配目录外的任何 LangGraph import；最终生产扫描只剩 `adapters/workflow/langgraph/compiler.py` 和 `state.py` 导入第三方图类型。架构与目录文档明确平台端口、外围状态投影和唯一装配根，RAGFlow 官方 submodule 与源码保持未修改
- 覆盖率门禁：新协议首轮使总体行降到 `90.81%` 并被冻结门禁真实拒绝；补齐非法节点上下文/结果、重复节点、步数错配、空已编译输入和缺失编译器端口后，最终用项目固定 uv 0.11.16 完整执行 `418 passed, 12 skipped in 121.17s`，总体行 `90.99%`、分支 `73.06%`、核心行 `93.26%`、核心分支 `74.63%`，六项均不低于 H7-02 冻结阈值，没有排除生产文件或放宽阈值
- 本机工具修复：末次门禁发现全局 Homebrew uv 实际为 0.7.21，无法执行 H7-01 记录的 audit 预览子命令。新增 `scripts/uv.sh` 固定 0.11.16：版本匹配时直接执行，否则经精确版本的隔离 `uv tool run`，不修改用户全局工具。coverage、dev、real、契约与 E2E 入口统一改走该脚本，CI 契约验证实际版本；固定 uv 完成 lock 检查和 83 包安全审计，无已知漏洞或不良项目状态
- GREEN：普通后端全量 `416 passed, 12 skipped in 67.06s`，最终覆盖率全量如上；提交前固定 uv 定向 `32 passed`，Ruff lint、161 个文件格式及严格 Mypy 161 个源/测试/门禁文件通过。前端 14 files/61 tests，行 `86.17%`、分支 `75.00%`，ESLint、TypeScript、Build、pnpm audit 与生成契约通过；602.76 kB 既有 chunk 警告保留给 H7-09，未提高阈值。CI/覆盖率/dev/real/两类基础设施契约、ShellCheck、`git diff --check` 全部通过
- 真实验收：12 GiB demo-light 上正式 React/FastAPI/MySQL 两轮带引用会话与中断恢复 `1 passed (5.4s)`。随后临时切到项目专属 32 GiB real，显式执行真实百炼、Deep Agents 流/停止/错误、会话 HTTP/SSE、RAGFlow+百炼图编译、手动运行和员工 allowlist 工具触发共 `6 passed in 35.49s`，没有 Mock/Fake 或 GitHub Runner 结果
- 清理：Demo/real 测试 finally 已删除唯一业务数据；real 前后端、平台/RAGFlow 容器和项目专属 32 GiB Colima 已停止，稳定数据、0600 Token、冻结依赖与官方镜像保留。覆盖率报告、前端构建/覆盖率产物与两次环境前置失败日志在提交前精确删除
- 遗留：无；下一任务 H7-05 将 FastAPI、SQLAlchemy、HTTP SDK、LangChain、LangGraph、Deep Agents 和供应商类型的完整平台/适配层依赖方向固化为自动架构门禁

### H7-05 第三方依赖边界门禁

- 状态：✅ 已完成
- 日期：2026-07-20
- 提交：本任务提交（见 Git 历史）
- RED：新增统一 `tests/architecture/test_dependency_boundaries.py` 后首次定向执行得到 `1 failed`，准确报告根启动文件 `__main__.py:1:uvicorn (allowed: api)`；证明现有 H7-03/H7-04 局部扫描没有覆盖 FastAPI/Uvicorn、数据库、HTTP SDK 和完整依赖方向。最小修复把 Uvicorn 启动收回 `api/server.py`，根入口只调用平台 HTTP 边界；随后补充相对 import 解析测试，防止合法平台内部导入被新门禁误报
- 统一门禁：AST 扫描全部 `backend/src/common_agent/**/*.py`，标准库与平台包之外的 import 必须登记唯一职责目录，未登记 SDK 默认失败。FastAPI/Starlette/Uvicorn/multipart 只允许 `api/`，SQLAlchemy/Alembic/MySQL 驱动只允许 `adapters/persistence/`，HTTP、模型、代理、图、缓存、对象存储和供应商 SDK 只允许 `adapters/`；Pydantic、dotenv 和 cryptography 也按当前实际职责限定目录，不以第三方尚未使用为由放行
- 平台依赖方向：除唯一 FastAPI 组合根 `api/app.py` 外，生产平台层不能导入 `common_agent.adapters`；API 只允许被 API 自身、契约导出与根启动入口消费；`domain/` 只能依赖自身和标准库。原模型与 LangGraph 两套重复 AST 扫描已删除，避免同一规则分散漂移；默认 pytest/覆盖率会自动发现统一门禁，`test-ci.sh` 同时验证门禁入口没有被移除
- GREEN：架构/启动/原模型与图契约定向 `9 passed`，统一架构文件自身 `4 passed`；后端覆盖率全量 `421 passed, 12 skipped in 121.31s`，总体行 `91.08%`、分支 `73.06%`、核心行 `93.26%`、核心分支 `74.63%`，全部高于冻结阈值。Ruff lint、171 个文件格式、严格 Mypy 164 个源/测试/门禁文件、uv lock 与 83 包安全审计通过；前端 14 files/61 tests、行 `86.17%`、分支 `75.00%`、ESLint、TypeScript、Build、pnpm audit 和契约漂移通过。两类基础设施、dev/real/CI/覆盖率契约、全部 ShellCheck 与 `git diff --check` 通过
- 真实回归：12 GiB demo-light 上正式 React/FastAPI/MySQL 两轮引用会话与中断恢复 `1 passed (6.2s)`。随后临时切到项目专属 32 GiB real，显式启用而非接受 skip，真实百炼、Deep Agents 流/停止/错误、会话 HTTP/SSE、RAGFlow+百炼图编译、手动运行和员工 allowlist 工具触发共 `6 passed in 37.17s`；完成状态没有使用 Mock/Fake 或 GitHub Runner 结果，RAGFlow 官方 submodule 工作区保持未修改
- 失败矩阵：覆盖未知第三方依赖默认拒绝、框架/数据库/HTTP/模型/图 SDK 越层、平台反向依赖适配器、领域越层、根入口直接持有 Uvicorn 和相对平台 import 误判；既有真实回归继续覆盖供应商认证/超时/断流、停止、知识检索、工作流结果与工具权限。H7-05 不新增外部副作用或用户语义，因此不另造远端资源、部署或浏览器功能
- 清理：Demo 和 real 用例 finally 已删除唯一会话、员工、知识库和工作流数据；无头浏览器、Vite、Uvicorn、平台/RAGFlow 容器和项目专属 Colima 已停止，18200/18280 无监听。前端 dist/覆盖率/tsbuildinfo、后端覆盖率数据已精确删除；稳定数据、0600 Token、冻结依赖和官方镜像保留
- 文档：`docs/backend-architecture.md` 与 `docs/project-structure.md` 同步唯一依赖矩阵、装配根、启动边界和架构测试归属；进度、命令、真实边界和清理只写入本路线图，产品范围没有变化
- 遗留：无；下一任务 H7-06 统一 JSON 日志、关联上下文、健康/指标和跨服务 trace context，并用故障测试证明可定位且不泄漏提示词、知识正文、Key、密码或上游响应

### H7-06 结构化日志、指标与追踪

- 状态：✅ 已完成
- 日期：2026-07-20
- 提交：本任务提交（见 Git 历史）
- RED：先新增平台关联、JSON 脱敏和有界指标单元测试，首次收集因 `common_agent.observability` 不存在按预期失败；再启动正式 Uvicorn/MySQL，首轮在健康响应缺少 `traceparent` 处按预期失败，证明既有中间件只有随机请求 ID，没有追踪、指标或结构化请求完成事件
- 关联上下文：平台标准库模块实现可嵌套 ContextVar 上下文，接受合法 W3C `00` 版 `traceparent`、拒绝全零/非法值并安全生成本地 trace/span；响应同时返回 UUID `X-Request-ID` 与当前 `traceparent`。HTTP 路由模板和会话/消息/轮次/工作流/运行 ID 按白名单关联，异步后台任务继承请求 trace；RAGFlow 与百炼正式 HTTP 请求派生子 span 并透传 trace/request ID，认证 header 保持适配层私有
- 日志与故障：Uvicorn、应用和应用内 Alembic 统一单行 JSON，包含 UTC 时间、级别、logger、稳定事件、源码、状态、耗时与稳定错误码；会话和工作流各写 started/finished 生命周期。字段与自由文本共同脱敏 prompt、query/content/body、知识/文档正文、Key、Authorization/Token、密码、Secret 和上游响应；未知异常只写异常类型，并由观测中间件返回带同一请求/trace ID 的稳定 `internal_error`。末次在已停止 MySQL 上复验真实发现 Uvicorn 把启动 traceback 当作普通多行 message，虽然保持 JSON 却暴露本机路径；新增关闭失败测试后把多行 traceback 收敛为安全占位并只保留异常类型，不输出异常消息、堆栈正文或路径
- 指标：新增 `GET /api/v1/system/metrics` 进程内 JSON 快照，提供 uptime、in-flight、请求总数、2xx-5xx 桶、稳定错误码与延迟 count/total/maximum；错误码集合有固定容量，未知/非法或超限归入 `other`，并发更新在同一锁内完成。指标入口自身不污染快照，高基数业务 ID 和任何正文/凭据不进入标签；OpenAPI 与前端生成类型同步
- GREEN：H7-06 关键路径定向批次分别 `62 passed`、`10 passed` 和补强后的 `24 passed`；traceback 脱敏补强后最终权威覆盖率全量 `428 passed, 12 skipped in 125.73s`。总体行 `91.18%`、分支 `73.54%`、核心行 `93.19%`、核心分支 `74.63%`，均高于冻结阈值；Ruff 与严格 Mypy 170 个源/测试文件通过，uv lock 和 83 包安全审计通过。前端 14 files/61 tests、行 `86.17%`、分支 `75.00%`，ESLint、TypeScript、Build、pnpm audit 与契约漂移通过；既有 602.76 kB chunk 警告留给 H7-09，未调高阈值
- 生产同路径：12 GiB demo-light 正式 React/FastAPI/MySQL 两轮引用会话与中断恢复 `1 passed in 6.2s`，并由正式 Uvicorn 日志测试证明所有非空日志行均为 JSON、请求/会话/消息/轮次可关联且请求正文不泄漏。临时 32 GiB real 复用官方 RAGFlow v0.25.6 镜像，embedding/rerank 均为百炼 ready、本地模型 absent；显式真实百炼、Deep Agents、会话 SSE、RAGFlow+百炼编译、手动运行与员工工具共 `6 passed in 38.57s`，没有使用 GitHub Runner 结果
- 失败矩阵：覆盖非法 traceparent、嵌套上下文恢复、出站子 span、内部异常、422 稳定错误、敏感结构字段与自由文本、错误码基数上限、指标并发安全、正式日志纯 JSON、会话/工作流完成关联，以及既有认证、超时、断流、停止和真实供应商链路；测试不把提示词、知识正文、Key、密码或上游响应写入失败输出
- 清理与边界：Demo/real 用例 finally 已清理本轮会话、员工、知识库和工作流数据；前后端、Playwright、平台/RAGFlow 容器和项目专属 Colima 已停止，18200/18280 无监听，稳定数据、固定镜像、冻结依赖与 0600 Token 保留。RAGFlow 官方 submodule 与源码未修改；指标是本机进程诊断而非持久审计/跨实例聚合，审计与生产指标仍由 Wave 10 对应任务交付
- 遗留：无；下一任务 H7-07 为事件历史、订阅者、per-ID 锁和终态状态增加有界容量、TTL/LRU 与安全回收，并以压力/soak 证明内存回落且不误删活跃状态

### H7-07 事件与锁状态生命周期

- 状态：✅ 已完成
- 日期：2026-07-20
- 提交：本任务提交（见 Git 历史）
- RED：先为会话/工作流 Broker 增加大量终态 ID、活跃状态保护、TTL、单 ID 订阅者上限和按 ID 锁取消等待回收测试，首次收集因 `common_agent.concurrency` 不存在按预期失败；最小实现后再补全局订阅容量与“容量已满时活跃状态不得误删”用例，避免不同 ID 的长连接绕过单 ID 上限，也不以强制淘汰正在运行的状态冒充有界治理
- 生命周期边界：两类 Broker 每个 ID 最多保留 512 个事件、每个订阅队列 128 项、每个 ID 最多 64 个订阅者、进程内总订阅者最多 1024 个；无活跃运行且无订阅者的状态最多保留 1024 个并按 LRU 淘汰，空闲 300 秒后由可取消定时器回收。活动运行和正在消费的 SSE 不会被 TTL/LRU 删除；瞬时活动数超过保留上限时只允许受实际活动负载保护的临时超额，转为终态后立即向 1024 收敛。容量淘汰、TTL 或进程重启后的续传继续返回原 `event_history_unavailable`，客户端读取 MySQL 权威消息/运行摘要；慢消费者仍关闭该流且不静默丢事件
- 锁与关闭：新增标准库 `KeyedLockPool`，同一会话/运行继续严格串行，不同 ID 互不阻塞；持有者、等待者和取消等待者都计入引用，最后一个使用者离开即删除锁项，不使用会永久增长的 `defaultdict(asyncio.Lock)`。FastAPI lifespan 在服务停止并等待后台任务后关闭两个 Broker，取消所有回收定时器、唤醒并关闭订阅流、清空进程状态；关闭后发布/续传关闭失败
- 压测：新增可独立运行的 `tests/soak/event_lifecycle_soak.py`。最终 60 秒在不启动 Docker 的情况下完成 149,100 轮唯一短会话、工作流与锁，两个 Broker 状态峰值始终为 128，TTL 后状态和锁项全部回到 0；tracemalloc 峰值 794,640 bytes、回收后相对基线残留 44,424 bytes。定向失败矩阵与短 soak 共 `28 passed`，覆盖活跃保护、终态即时收敛、LRU/TTL、局部/全局订阅上限、历史缺口、慢消费者、关闭唤醒、锁串行及取消回收
- GREEN：最终权威后端覆盖率全量 `451 passed, 12 skipped in 126.67s`，总体行 `91.28%`、分支 `74.17%`、核心行 `93.19%`、核心分支 `74.63%`，全部高于冻结阈值；Ruff、严格 Mypy 174 个源/测试文件、uv lock、83 包安全审计和 CI 镜像契约通过。前端 14 files/61 tests、行 `86.17%`、分支 `75.00%`，ESLint、TypeScript、Build、pnpm audit 与契约漂移通过；既有 602.76 kB chunk 警告仍留给 H7-09，本任务未修改前端协议、依赖或构建阈值
- 生产同路径：12 GiB demo-light 上正式 React/FastAPI/MySQL 两轮带引用会话与中断恢复 `1 passed in 6.1s`；随后临时切到项目专属 32 GiB real，显式执行真实百炼、Deep Agents 流/停止/错误、会话 HTTP/SSE、RAGFlow+百炼图编译、手动运行和员工 allowlist 工具触发共 `6 passed in 38.79s`。没有使用 Mock/Fake 或 GitHub Runner 结果，RAGFlow 官方 submodule 与源码保持未修改
- 清理与边界：Demo/real 用例 finally 已删除唯一会话、员工、知识库和工作流数据；前后端、无头浏览器、平台/RAGFlow 容器和项目专属 Colima 已停止，18200/18280 无监听，稳定数据、固定镜像、冻结依赖与 0600 Token 保留。当前仍是单 FastAPI 进程内短期回放；跨进程持久事件、可靠队列和 Worker 只由 S10-05 交付，不用本任务的内存 Broker 冒充分布式可靠性
- 遗留：无；下一任务 H7-08 在现有行为与覆盖率保护下拆分 ChatPage、WorkflowsPage、ConversationService、WorkflowService 和大型路由

### H7-08 核心大文件按职责拆分

- 状态：✅ 已完成
- 日期：2026-07-20
- 提交：本任务提交（见 Git 历史）
- RED：先增加职责预算、实现层不得反向依赖门面、跨 Feature 私有导入和页面容器反向依赖门禁，首次定向执行准确得到 7 个失败：`ConversationService` 633 行、`WorkflowService` 470 行、会话/工作流/运行路由 421/430/295 行、`ChatPage` 691 行、`WorkflowsPage` 725 行；证明原实现把用例、运行、持久化、协议和展示集中在同一文件。拆分完成后补充前后端循环依赖扫描，默认 pytest 会自动执行
- 后端职责：`ConversationService` 收敛为 153 行用例门面，事务读写与重试准备、运行协调、消息权威投影及稳定 contracts 分别进入独立模块；`WorkflowService` 收敛为 120 行门面，定义目录、运行协调、运行投影及 contracts 分责。发送和重试继续先确认员工与活动状态再提交消息，运行停止、恢复、关闭、锁与事件语义不变；实现模块不导入门面且依赖图无环
- API 边界：会话、工作流定义和工作流运行路由分别收敛为 180/144/194 行；Pydantic DTO 移入 `api/schemas/`，服务依赖解析移入 `api/routers/services.py`，会话 SSE 移入 `conversation_events.py`。既有路由路径、OpenAPI、错误信封和公开响应类导入保持兼容，事件路由不重复生成 Tag
- 前端职责：`ChatPage` 从 691 行收敛为 91 行，只处理页面状态和三栏编排；Query/Mutation/SSE/URL 协调、消息归并、消息/引用展示和工作区分别进入 controller/state/presentation。`WorkflowsPage` 从 725 行收敛为 155 行；设计器 Query/reducer/保存/运行同步、画布、节点面板、属性与运行面板、拖拽协议分离。跨 Feature 私有导入、实现层反向依赖页面容器和拆分模块循环依赖均由架构门禁关闭失败
- GREEN：架构、依赖与 OpenAPI 定向 `26 passed`；Ruff 和严格 Mypy 189 个源/测试文件通过。权威后端覆盖率全量 `464 passed, 12 skipped in 128.48s`，总体行 `91.66%`、分支 `74.23%`、核心行 `93.74%`、核心分支 `74.63%`，均高于冻结阈值。前端 14 files/61 tests，行 `86.30%`、分支 `75.48%`，ESLint、TypeScript、生产 Build 和生成契约漂移通过；现有 602.76 kB chunk 警告如实保留给 H7-09，没有调高阈值
- 生产同路径：12 GiB demo-light 经正式 React/FastAPI/MySQL 完成两轮引用会话与中断恢复，浏览器用例 `1 passed in 5.2s`；退出阶段的 runner 等待被人工中断后，已用正式清理器删除其唯一会话、员工、知识库和 Seed。随后临时切到项目专属 32 GiB real，显式执行真实百炼、Deep Agents、会话 SSE、RAGFlow+百炼图编译、手动运行与员工工具共 `6 passed in 35.37s`，没有 Mock/Fake 或 GitHub Runner 结果
- 清理与边界：Demo/real 唯一测试数据已删除；前后端、浏览器、平台/RAGFlow 容器和项目专属 Colima 已停止，18200/18280 无监听。覆盖率、构建、tsbuildinfo、字节码和保留日志已精确清理；稳定数据、0600 Token、冻结依赖与官方镜像保留，RAGFlow 官方 submodule commit 与 `UPSTREAM_COMMIT` 一致且工作区未修改
- 遗留：无；下一任务 H7-09 建立 bundle 分析和单 chunk 不超过 500 kB 的门禁，并验证四入口真实浏览器加载与缓存复用

### H7-09 前端包体与加载性能

- 状态：✅ 已完成
- 日期：2026-07-20
- 提交：本任务提交（见 Git 历史）
- RED：先增加隔离 bundle 契约，首次执行按预期因缺少分析器失败；实现后对 500,001 bytes 单 chunk、四个 400,000 bytes 依赖组成的 1.6 MB `/chat` 首次图、缺失 manifest 和缺失四路由入口逐项故障注入，均返回非零并指出具体文件、路由、预算或修复边界。改动前生产构建如实复现 `errors-*.js` 602,760 bytes 与 Vite 大 chunk 警告，没有通过提高 `chunkSizeWarningLimit` 消音
- 构建拆分：保留 `App` 四个动态 import，按 Vite 8 正式 `build.rolldownOptions.output.codeSplitting` 将 React core、Ant Design/RC、TanStack/Axios/Zod 和 React Flow/Zustand/D3 分成入口感知、带内容哈希的稳定组；小分组可合并，大组按 400,000 bytes 上限继续拆分。入口感知避免普通页面无条件加载完整工作流画布，未使用已废弃的 object `manualChunks`
- 自动预算：生产构建固定生成 `.vite/manifest.json`，`pnpm build` 在 Vite 成功后必跑 `check-bundle-budget.mjs`。分析器扫描所有 JS chunk，硬性拒绝超过 500,000 bytes；解析 manifest 递归计算 `/chat`、`/employees`、`/knowledge-bases`、`/workflows` 首次静态 JS 图，任一路由超过 1,500,000 bytes 或不再是异步入口同样失败。可选 CI 复用 `pnpm build`、隔离故障注入和生产 preview 浏览器入口，但本机结果仍为权威
- 结果：最终最大 chunk 为 `react-core` 189,644 bytes，较 602,760 bytes 基线下降 68.5%，没有构建警告；四路由首次 JS 图分别为 1,101,220 / 1,157,532 / 1,360,071 / 1,176,468 bytes，全部低于 1.5 MB 门禁。前端 14 files/61 tests，行 `86.30%`、分支 `75.48%`，ESLint、TypeScript、生产 Build、pnpm 高危审计、跨端契约、ShellCheck、bundle 与 CI 镜像契约全部通过
- 浏览器验收：12 GiB demo-light 下生产 preview 逐个直达四入口、校验 10 秒本机首屏上限和页面异常，再通过菜单加载全部异步路由；第二轮切换没有任何重复 JS 请求，`2 passed in 4.9s`。随后临时切换到 32 GiB real，生产 preview 连接正式 MySQL、RAGFlow 与百炼配置的 real 后端，同一套首屏/交互/缓存复用验收再次 `2 passed in 4.9s`；该任务不发送模型请求或上传文档，不产生百炼调用费用
- 清理与边界：Demo/real 前后端、生产 preview、浏览器、平台/RAGFlow 容器和项目专属 Colima 已停止，18200/18280 无监听；构建、manifest、覆盖率、tsbuildinfo 和临时浏览器产物在提交前精确删除。稳定数据、0600 Token、冻结依赖和官方镜像保留，RAGFlow 官方 submodule 未修改
- 遗留：无；Wave 7 全部完成，下一任务 R8-04 在暂定 32 GiB real profile 下完成峰值不高于 25 GiB、中文检索质量与 30 分钟 soak 专项验收

### R8-04 Colima 32 GiB 专项优化与验收

- 状态：✅ 已完成
- 日期：2026-07-20
- 提交：本任务提交（见 Git 历史）
- RED：新增 `scripts/test-real-resource-soak.sh` 后首次按预期以“缺少 32 GiB real 资源监视器”失败；最小实现转绿后，首轮正式运行又由实时报告暴露采样器把约 2.5 秒 Docker 采集耗时叠加到 10 秒等待，按原节拍跑满只会取得约 144 个样本并被 162 个样本门禁正确拒绝。该轮已安全中断并自动停止完整栈，没有用降低样本门槛掩盖问题；采样循环改为按启动时间的绝对 10 秒刻度调度，静态、类型、Shell 和契约检查通过后从完全停止态重新执行完整验收
- 可复现入口：新增标准库 `scripts/real-resource-monitor.py`，分别记录冷启动和稳定期的 Colima `/proc/meminfo`、六容器 `docker stats/inspect` 与正式 `/api/v1/system/status`；硬门禁为 VM/容器峰值不高于 25 GiB、Swap 峰值不高于 512 MiB且首尾增长不超过 64 MiB、VM 总内存 24-32 GiB、稳定期不少于 1800 秒和 90% 理论样本、全程 ready、容器 running/healthy、重启 0、OOM 0。`scripts/real-resource-soak.sh` 强制从停止态启动，不接受少于 1800 秒，串联真实中文质量和完整 MVP 页面链路，成功失败均清理唯一业务数据并停止 real；单次 JSON、日志和浏览器产物只写入 Git 忽略的 `.local/soak/r8-04/`
- 冷启动与资源：正式 32 GiB VM 实际 `MemTotal=33,585,905,664` bytes，从 Colima 完全停止到平台连续 ready 为 88.934 秒；冷启动 39 个有效样本的 VM/容器峰值为 6.78/6.67 GiB、Swap 0，启动前 15 次容器尚不存在的采集失败单独保留且不冒充健康样本。稳定期取得 180 个 10 秒样本，末样本 1790.008 秒，VM 峰值 6.91 GiB、容器合计峰值 6.85 GiB、Swap 首尾与峰值均为 0、采样错误 0、全程 ready、所有容器重启 0/OOM 0；分项峰值约为 RAGFlow API 4.16、ES 1.57、平台 MySQL 0.48、RAGFlow MySQL 0.43、MinIO 0.19、Valkey 0.02 GiB，完整链路远低于 25 GiB 上限
- 中文质量与真实链路：RAGFlow v0.25.6 仍通过官方 `Tongyi-Qianwen` 接入百炼 `text-embedding-v4` 和 `qwen3-rerank`，本地 embedding/rerank 保持未启动。真实用例创建正确、相似干扰和无关三份中文文档，首次解析检索和同库完整索引重建后的检索均把唯一正确文档排首，`1 passed in 14.49s`；随后从空业务数据经正式 React/FastAPI/MySQL/RAGFlow/Deep Agents/百炼完成知识库解析、员工绑定、真实两轮带引用会话、工作流手动和员工触发及刷新恢复，`1 passed (25.3s)`。业务测试完成后仍继续保持同一真实栈直到 30 分钟结束，没有用空闲短跑代替稳定性窗口
- 费用、限流和数据边界：正式 `cost` 诊断再次确认聊天、文档 embedding 和检索 rerank 均调用北京百炼业务空间并按账号实时计费，金额以执行时控制台单价/账单为准；平台请求保持 60 秒请求/流超时和 2 次有限重试，RAGFlow 解析/检索的限流、超时和上游失败继续返回稳定可恢复错误。知识片段与检索查询会发送到所配百炼区域，凭据只报告 present/0600 状态，不输出 Key、Token、知识正文或供应商响应；本任务没有修改 RAGFlow submodule、镜像或容器内文件
- GREEN：资源监视器自测、少于 30 分钟关闭失败、链路/清理契约、Ruff lint/format、严格 Mypy 和两份脚本 ShellCheck 全部通过；正式入口最终输出 `real cold-start ... passed`、`real soak ... passed` 与 R8-04 总验收通过。32 GiB 因此从“暂定可运行值”确认为长期 `real` 默认值；12 GiB `demo-light` 保持不变，日常开发不启动 RAGFlow
- 清理：真实中文知识库和 MVP 的唯一知识库、员工、会话与工作流已由 finally 清理；前后端、浏览器、平台/RAGFlow 六容器和项目专属 Colima 已停止，释放 64 GiB 主机内存。稳定原生 Volume、0600 Token、冻结依赖与本机官方镜像保留；被中断首轮和正式次轮的脱敏报告留在 Git 忽略目录供本机核验，不进入提交
- 文档：README、后端架构、RAGFlow 资源说明、项目规则与本路线图统一把 32 GiB 更新为已验收的长期 real 默认值，并保留 25 GiB 峰值门禁、12 GiB demo-light 和不依赖另一台 128 GiB Mac 的边界
- 遗留：无；Wave 8 全部完成，下一任务 U9-01 定义并实现会话、员工、知识库和工作流的引用安全与幂等删除 API

### U9-01 资源删除策略与后端 API

- 状态：✅ 已完成
- 日期：2026-07-20
- 提交：本任务提交（见 Git 历史）
- RED：先为四类资源编写应用服务成功、重复删除和五种引用阻断测试，首次收集因
  `common_agent.application.resource_deletion` 不存在按预期失败；随后增加正式 Uvicorn/MySQL
  生命周期用例，从公开 HTTP 建立员工、知识库、工作流、会话和活跃运行引用，证明阻断解除前
  不允许删除、终态级联和重复 DELETE 语义必须由生产装配满足
- 策略与事务：新增平台 `ResourceDeletionService`、仓储端口与 SQLAlchemy 适配器。会话只在无
  活跃生成时删除并级联消息、引用和员工触发运行；员工有会话时拒绝；知识库有员工绑定或工作流
  知识节点时拒绝；工作流在员工 allowlist 或有 `pending/running` 运行时拒绝，终态运行随定义删除。
  MySQL 删除在同一事务内重新检查引用并由外键兜底，四条公开 DELETE 对不存在资源统一返回 204
- 并发与外部副作用：创建/更新员工、创建会话、创建/更新/启动工作流和四类删除共享可回收的
  `ResourceMutationGuard`，按资源键排序持锁，防止单进程内引用检查后新增引用。知识库经 RAGFlow
  v0.25.6 官方 `DELETE /api/v1/datasets` 删除，404/已不存在幂等成功；连接、5xx 或非法响应映射为
  不可自动重放的 `knowledge_base_delete_result_unknown`，要求刷新权威状态后再重试。RAGFlow 官方
  submodule、镜像和容器内文件均未修改；多实例互斥仍明确留给 S10-05
- GREEN：应用删除定向 `8 passed`，受影响后端定向 `109 passed`；正式 Uvicorn/MySQL 引用、阻断、
  活跃运行、级联及四类重复删除集成 `1 passed in 4.92s`。权威后端全量 `476 passed, 12 skipped
  in 134.26s`，总体行 `91.55%`、分支 `73.87%`、核心行 `94.00%`、核心分支 `75.35%`，均高于
  冻结阈值；Ruff、严格 Mypy 196 个源/测试文件、uv lock、83 包安全审计和契约漂移通过。前端
  14 files/61 tests、行 `86.30%`、分支 `75.48%`，ESLint、TypeScript、Build、pnpm audit 与
  bundle 门禁通过，最大 chunk 189,644 bytes，四路由首次加载图预算均未回退
- 生产同路径：临时 32 GiB real 复用官方 RAGFlow、百炼 embedding/rerank 和正式平台 MySQL，
  从公开 HTTP 创建知识库、上传并完成解析，再执行首次/重复删除并确认文档入口 404，
  `test_real_knowledge_http_lifecycle 1 passed in 4.44s`；未调用或修改 RAGFlow 私有数据库/源码
- 清理与文档：集成和 real 用例已删除本轮会话、员工、知识库、工作流及文档；正式前后端、平台/
  RAGFlow 容器和项目专属 Colima 已停止，稳定 Volume、0600 Token、冻结依赖和官方镜像保留。
  产品范围、前后端架构和工程结构已同步删除矩阵、幂等/不确定语义与单进程锁边界
- 遗留：后端能力无遗留；下一任务 U9-02 从四个正式页面提供确认、引用阻断说明与完成/失败状态，
  并由浏览器完成创建→建立引用→阻断/解绑→删除→刷新消失，不用测试清理器替代用户链路

### U9-02 删除 UI 与真实验收

- 状态：✅ 已完成
- 日期：2026-07-21
- 提交：本任务提交（见 Git 历史）
- RED：先在会话、数字员工、知识库和工作流四个页面增加正式删除行为测试，首次得到新增 4 项
  失败而既有 61 项继续通过，证明页面没有删除入口。真实链路初轮又依次关闭失败于已停止 Colima
  未自动恢复、RAGFlow 冷启动后 Token 首次连接被关闭、知识库按钮定位歧义和 Ant Select 键盘清空
  未真正解除单选绑定；覆盖率模式还捕获到静态 `Modal.confirm` 在测试环境销毁后残留 React 调度
- 交互与状态：新增复用的受控删除确认组件，明确展示资源类型、名称、永久影响和“不可恢复”，
  默认聚焦取消按钮，确认按钮具有唯一可访问名称；会话生成、工作流活跃运行和知识库上传期间禁用
  冲突入口。四页均不做乐观删除，只有 `204` 后才移除列表/详情/消息/运行 Query 并安全选择下一项
  或空状态；失败保留权威快照。确认框随所属 React 树卸载，不再创建全局静态渲染任务
- 阻断说明：集中映射 `conversation_busy`、员工被会话引用、知识库被员工/工作流引用、工作流被员工
  授权或存在活跃运行，以及 RAGFlow 删除结果不确定等稳定错误码；页面分别引导停止生成/运行、删除
  会话、解除员工绑定或授权、修改知识节点、刷新权威状态后人工重试，未知稳定错误仍安全显示后端文案
- 真实用户旅程：新增独立 `resource-deletion` 无头 suite，同一 Chromium 页面创建并解析真实 RAGFlow
  知识库，创建引用它的工作流、同时绑定二者的数字员工和引用该员工的会话；依次观察员工被会话、
  工作流被员工、知识库被员工拒绝，随后从员工编辑框用组件清除按钮解除两项绑定，再观察知识库被
  工作流节点拒绝，最终只通过四个正式页面删除工作流、知识库、会话和员工，并逐页刷新确认消失
- 生产同路径：最终 `1 passed (17.4s)`，全程经过
  `React -> Axios -> Uvicorn/FastAPI -> ResourceDeletionService -> MySQL/RAGFlow v0.25.6`；真实文档
  上传等待解析完成，浏览器网络监听确认没有直连 19380 或阿里云域名。兜底清理器只在场景结束后按
  唯一名称检查和回收，没有创建业务对象、解除引用或代替任何 UI 删除步骤，成功轮报告工作流/知识库
  均为 0
- GREEN：后端权威全量 `476 passed, 12 skipped in 134.59s`，总体行 91.58%、分支 73.93%、核心行
  94.00%、核心分支 75.35%；Ruff、205 文件格式、严格 Mypy 198 个源/测试文件、uv lock 和 83 包
  审计通过。前端 16 files/76 tests，行 86.95%、分支 75.60%，ESLint、TypeScript、生产 Build、
  pnpm audit、契约与 bundle 门禁通过；最大 chunk 189,644 bytes，四路由首次加载图均低于 1.5 MB
- 编排与失败恢复：正式 E2E 入口会按 suite 自动启动 12 GiB demo 或 32 GiB real Colima，RAGFlow
  Token 冷启动申请有 60 秒有限重试且诊断不泄露 Token；本轮浏览器、Vite 和 Uvicorn 的回收最多
  等待 15 秒后精确终止，避免失败清理无限挂住。失败轮保留脱敏截图/Trace，成功轮自动删除产物
- 清理与边界：当前轮四类业务对象已由页面删除，兜底复核为 0；此前人工中断轮次的唯一会话、员工、
  工作流和知识库已精确清理。18200/18280 无监听，项目专属 Colima 已停止，稳定 Volume、0600
  Token、冻结依赖和官方镜像保留；RAGFlow submodule、镜像与容器内文件均未修改
- 遗留：无；下一任务 U9-03 为会话、员工、知识库、工作流和运行摘要建立服务端分页、搜索、稳定
  排序及前端游标状态，并验证大数据集下无全表/N+1、重复或遗漏项

### U9-03 列表分页、搜索与稳定排序

- 状态：✅ 已完成
- 日期：2026-07-21
- 提交：本任务提交（见 Git 历史）
- RED：先建立平台分页原语测试，首次因 `common_agent.pagination` 尚不存在按预期收集失败；随后为
  RAGFlow 官方数据集页码转换、前端页合并/去重和知识库搜索/加载更多增加用例。真实 MySQL 初轮
  又由迁移测试仍倒写旧 revision 暴露 0008 索引重复应用，并正确级联关闭失败；修复最新 revision
  基线后重新从健康测试库执行，没有绕过迁移。覆盖率首轮也按冻结阈值拒绝新增 infinite-query 分支，
  通过拆分和补齐真实交互测试转绿，没有降低行/分支门禁
- 协议与查询：五类公开列表统一接受最长 128 字符 `search`、`1-100` 的 `limit` 和 opaque
  `cursor`，返回 `items + next_cursor`；URL-safe 游标绑定资源、规范化搜索词和页大小，并带校验和，
  篡改或跨条件复用返回 `invalid_page_cursor`。平台 MySQL 使用不可变
  `created_at DESC, id DESC` keyset，只取 `limit + 1`；名称/标题/运行输入用 B-tree 前缀搜索，完整
  UUID 和运行状态用等值索引，0008/0009 迁移补齐组合索引，不使用 `%关键词%` 全表包含扫描
- 大数据与并发：同时间戳 5 条员工记录按 ID 稳定翻完三页；首屏后删除游标锚点并新增更靠前记录，
  后续页仍无重复/遗漏且不会混入新记录。25 个含完整节点/边的工作流取 20 条时固定 3 条 SQL：
  一条定义页、节点和边各一条批量查询，不随条目数增长。正式 HTTP 重复同一新增/删除场景并验证
  游标跨搜索词关闭失败；迁移后的真实 MySQL 索引、0009 revision 和有界查询均已核对
- 适配与前端：RAGFlow v0.25.6 只通过官方 `page/page_size/orderby/desc` 与 `ext.keywords`，官方
  `total_datasets` 在适配层转成平台 offset cursor，第三方分页类型未越过端口。四个页面和员工/
  知识库/工作流远程选择器使用 `useInfiniteQuery`，搜索进入 Query Key，页合并按 ID 去重，创建或
  删除后重置全部旧游标页；工作流页头进一步拆出，继续满足 180 行职责预算
- GREEN：后端权威全量 `484 passed, 13 skipped in 139.36s`，总体行 90.90%、分支 72.88%、
  核心行 93.59%、核心分支 75.00%，全部达到冻结门禁；Ruff、210 文件格式、严格 Mypy 200 个
  源/测试文件、uv lock、OpenAPI/生成 DTO 漂移和架构门禁通过。前端 17 files/82 tests，行
  86.77%、分支 75.00%，ESLint、TypeScript、生产 Build、pnpm 高危审计、bundle 门禁通过；最大
  chunk 189,644 bytes，四路由首次 JS 图均低于 1.5 MB
- 真实边界：12 GiB `list-pagination` Chromium suite 通过，页面展示 25 条两页员工，在锚点被删、
  首屏后新增时无重复，新搜索从第一页发现新增项，`1 passed (2.5s)`；临时 32 GiB real 通过官方
  RAGFlow 创建 3 个唯一数据集并按 2+1 两页搜索，ID 集合完整无重复，`1 passed in 0.33s`。没有
  修改 RAGFlow submodule、镜像、容器内文件或数据库，也没有调用 embedding/rerank/chat 产生费用
- 清理与文档：浏览器用例和真实 RAGFlow 用例已分别幂等删除 26 个员工及 3 个数据集；32 GiB real
  验收后立即停止。最终回归使用 12 GiB demo-light，完成后停止前后端、平台容器和项目专属 Colima；
  稳定 Volume、0600 Token、冻结依赖和官方镜像保留。产品范围、前后端架构、OpenAPI、生成 DTO
  和本路线图同步统一分页契约、索引前缀搜索及并发页链语义
- 遗留：无；Wave 9 全部完成，下一任务 S10-01 执行授权 Demo Key 边界和全链路泄漏扫描

### S10-01 授权 Demo Key 边界与泄漏门禁

- 状态：✅ 已完成
- 日期：2026-07-21
- 提交：本任务提交（见 Git 历史）
- 用户授权边界：用户再次明确要求继续使用现有百炼 Demo Key，并只在私有仓库
  `backend/.env.demo` 中版本化，以便两台开发电脑直接运行；本任务不迁移本机 Secret、不轮换、
  不作废该 Key。该文件是唯一获准例外，其他 API Key、密码、Token 和凭据仍禁止进入版本控制
- RED：最初的泄漏扫描会正确拒绝任何仓库内 Key；用户确认现有 Demo Key 为唯一版本化例外后，
  改为先证明指定文件恰好存在一个授权指纹，再关闭失败于其他源码、未忽略文件、Git 全历史、
  `.local` 日志、后端 wheel/sdist 和前端生产包中的未知指纹。普通 HTTP 集成测试首次暴露会隐式
  读取真实 Key，随即用测试专用假配置隔离；真实百炼边界测试仍显式读取授权配置
- 泄漏门禁：新增标准库扫描器与独立入口，自校验会向明文、ZIP 和 TAR 注入临时假 Key，确认三类
  载体均能检出且失败输出不显示值。正式扫描覆盖 350 个源码/配置文件、Git 全历史和 60 个含
  wheel、sdist、前端 bundle、日志在内的产物；构建产物清理后再次扫描 21 个保留产物，均只识别
  到一个授权历史指纹。错误、诊断、日志和测试断言只报告 present/布尔状态或脱敏表示
- 测试隔离与真实边界：普通 HTTP 集成装配固定使用无效假 Key、假模型和公开百炼基址，不会误计费；
  `TEST_BAILIAN_REAL=1` 才显式启用仓库内现有配置。正式 Uvicorn/MySQL 下真实百炼调用
  `1 passed in 1.44s`，证明现有 Key 可用；非法 Key 失败路径不回显 Key 或上游敏感响应
- 供应链修复：本轮 npm 审计发现 `openapi-typescript -> @redocly/openapi-core` 间接使用受高危公告
  影响的 `js-yaml 4.2.0`；按 pnpm 11 根配置规则覆盖为修复版 `4.3.0`，锁文件只保留一个版本，
  官方审计最终输出零已知漏洞。CI 继续只作可选镜像，并通过全历史 checkout 复用同一 Secret 门禁，
  本机结果仍为完成依据
- GREEN：后端权威全量 `485 passed, 13 skipped in 151.15s`，总体行 90.97%、分支 72.88%、
  核心行 93.59%、核心分支 75.00%；Ruff、199 文件格式、严格 Mypy 200 个源/测试文件、uv lock、
  83 包安全审计和真实百炼边界通过。前端 17 files/82 tests，行 86.77%、分支 75.00%，ESLint、
  TypeScript、生产 Build、零高危依赖审计、契约、bundle 和 CI 自检通过；最大 chunk 189,644 bytes，
  四路由首次 JS 图均低于 1.5 MB
- 清理：本轮正式前后端、平台容器和 12 GiB `demo-light` 已停止，构建与覆盖率临时产物已删除；
  18200/18280 服务不再运行。稳定 Volume、官方镜像、0600 Token 与用户授权的现有 Demo Key 保留；
  RAGFlow 官方 submodule、镜像和容器内文件均未修改
- 遗留：无；下一任务 S10-02 实现注册策略、登录/退出、安全会话、CSRF/重放/暴力尝试防护和凭据恢复边界

### S10-02 身份认证与安全会话

- 状态：✅ 已完成
- 日期：2026-07-21
- 提交：本任务提交（见 Git 历史）
- RED：先为密码策略、首位所有者并发注册、登录/限流、会话过期/撤销、恢复码单次消费、Cookie、
  CSRF、Origin 和 OpenAPI 保护响应建立单元/正式 MySQL/HTTP 测试，最初分别因认证领域、仓储、
  路由和前端身份门禁不存在按预期失败。真实 Chromium 又依次捕获旧服务启动时只显示“后端不可用”、
  原生 EventSource 未携带 Cookie 导致 SSE 401、Vite/Rolldown 拆包循环导致生产白屏、旧知识库
  定位器同时命中卡片与删除按钮，以及 Colima 32 GiB 在 Docker 内约 31.28 GiB 被四舍五入误判；
  每项都保留失败原因后修复，没有放宽安全、浏览器或资源门禁
- 身份与会话：新增 `auth_users`、`auth_sessions`、`auth_recovery_codes`、`auth_login_attempts` 和
  唯一引导槽迁移。空数据库只允许持有一次性引导令牌的请求创建一名 `owner`，并发请求由事务与
  唯一约束收敛；密码使用 Argon2id，恢复码和 256-bit 会话令牌只保存摘要。登录使用统一公共错误
  和按邮箱/来源地址时间窗限流，过期且不再锁定的失败状态按 `updated_at` 索引机会式清理；会话
  同时受空闲、绝对过期和撤销约束，恢复成功消费当前恢复码并撤销旧会话。引导令牌不进入版本
  控制，由 demo/real 入口分别在本机共享的 Git 忽略 `secrets/` 目录
  自动生成并强制 `0600`，用户授权版本化的仍只有既有百炼 Demo Key
- HTTP 与前端边界：除健康、状态和公开认证入口外，业务 REST/SSE 默认要求认证；非安全方法还
  必须通过精确可信 Origin 与会话 CSRF。后端只设置 `HttpOnly`、`SameSite=Strict` Cookie，不在
  JSON、OpenAPI 样例或 JavaScript 状态返回会话令牌。`AuthGate` 在业务路由/Query 挂载前处理首位
  所有者、登录、恢复、一次性恢复码展示和注销；CSRF 只留在 React 内存，401 统一清空业务缓存，
  Axios 与 EventSource 都携带 Cookie。生产拆包启用严格执行顺序，四路由预算继续全部低于 1.5 MB
- 失败矩阵：真实浏览器验证跨源首位注册 403、缺 CSRF 写入 403、跨源写入 403、第二名所有者 409、
  会话真实数据库过期后退回登录、注销撤销后旧 Cookie 重放 401；后端另覆盖弱密码、错误凭据、
  邮箱规范化、暴力尝试 429、恢复码错误/复用、空闲和绝对过期、并发引导及数据库约束。浏览器
  可见响应、Cookie 以外存储、日志、Trace、构建和全历史 Secret 扫描均不含会话/密码/恢复码
- GREEN：后端权威全量 `511 passed, 13 skipped in 162.07s`，总体行 91.16%、分支 72.78%、
  核心行 93.59%、核心分支 75.00%；Ruff、228 文件格式、严格 Mypy 216 个源/测试文件、uv lock、
  Alembic `20260721_0012` head/无模型漂移、OpenAPI/生成 DTO、固定 `pip-audit 2.9.0` 锁文件审计、
  架构和 Secret 门禁通过。前端 20 files/94 tests，行 87.08%、分支 75.10%，ESLint、TypeScript、
  Build、pnpm 高危审计、bundle、ShellCheck 与启动/CI/基础设施契约全部通过；最大 chunk 189,644
  bytes，四路由首次 JS 图为 1,455,902-1,479,531 bytes
- 生产同路径：12 GiB Chromium 认证套件完成注册、恢复、过期、重新登录、撤销和攻击路径，生产
  preview 首屏 `2 passed`、分页 `1 passed`、Demo 两轮 SSE `1 passed`。32 GiB real 复用官方
  RAGFlow v0.25.6、平台 MySQL 与百炼，员工/知识库 `2 passed (38.0s)`，工作流设计、手动运行、
  员工触发、空数据 MVP 总旅程和资源删除分别 `1 passed`；全程没有修改 RAGFlow submodule、镜像、
  容器内文件或私有数据库
- 清理与文档：所有 E2E 唯一业务数据和认证状态已由 finally 清理，失败截图核对后与成功产物、
  前端 dist/coverage/test-results、临时审计清单一并精确删除；18200、18280、19506 无监听，平台/
  RAGFlow 容器、浏览器和项目专属 Colima 已停止。稳定 Volume、0600 RAGFlow/本机所有者引导
  Token、冻结依赖、官方镜像和用户授权的百炼 Demo Key 保留；产品范围、工程结构、前后端架构、README、脚本说明、
  OpenAPI 和本路线图已同步
- 遗留：无；下一任务 S10-03 为五类资源、缓存/事件和 RAGFlow 外部数据增加租户归属、最小角色/
  权限与跨租户关闭失败门禁

### S10-03 组织、租户与 RBAC 隔离

- 状态：✅ 已完成
- 日期：2026-07-21
- 提交：本任务提交（见 Git 历史）
- RED：先为租户上下文、Owner/Editor/Viewer 权限、成员关系、跨租户仓储与复合外键、REST/SSE、
  工作流工具、事件/锁命名空间和 RAGFlow 外部归属建立失败测试，最初分别因 `tenancy` 模块、
  `tenant_id` 列和选择依赖不存在按预期失败。MySQL 回放又捕获外键辅助索引阻断降级，以及
  非事务 DDL 中断造成的半回退；修正顺序并显式清理自动索引后完成 `0014 → 0013 → 0014` 闭环。
  Starlette 异常路径还暴露跨任务重置 ContextVar token 会把 422 变成 500，改为在请求任务内激活
  已验证上下文后恢复稳定错误。真实 Chromium 依次抓到空工作区没有聊天按钮、重新登录仍位于
  员工页和 E2E 只删账号不删测试工作区三项测试假设，按实际页面和可重复清理修正，未放宽权限
- 数据与 RBAC：新增默认组织/工作区及成员关系迁移，首位 Owner 在同一事务取得默认工作区；Owner
  可在所属组织创建工作区并创建成员账号，恢复码只显示一次。`owner/editor/viewer` 三角色固定为
  全部可读、Owner/Editor 可写、仅 Owner 可管理；后端是权威判定，前端 Viewer 禁用写入口并提示
  只读。多工作区账号必须显式选择，单工作区兼容自动选择，任意伪造工作区统一拒绝
- 资源与外部隔离：员工、Demo 知识库/文档、会话、工作流和运行记录增加租户列、组合索引、唯一
  约束和复合外键；所有查询、删除引用检查和启动恢复按租户执行，消息通过会话继承归属。事件历史、
  订阅者和资源锁把租户纳入 key，相同资源 ID 不共享运行态。RAGFlow 继续保持官方 v0.25.6
  submodule/源码/内部数据库未修改；平台以全局唯一外部知识库 ID 映射租户，列表、详情、上传、
  检索和删除先验归属，只有默认工作区可惰性接管升级前未登记数据集
- HTTP 与前端：认证后先取得工作区访问列表再挂载业务路由；REST 使用 `X-Tenant-ID`，原生
  EventSource 因不能设置自定义头而使用同源 `tenant_id` 参数，头/参数冲突返回 422。顶部选择器
  展示角色，Owner 可创建工作区和 Editor/Viewer，切换时清空 Query Cache；会话令牌仍只在
  HttpOnly Cookie，CSRF 仍只在内存，持久偏好只保存非凭据工作区 ID。OpenAPI 与生成 DTO 同步
- GREEN：隔离的 `common_agent_s1003_test` 上后端权威全量 `528 passed, 13 skipped in 167.57s`，
  总体行 91.26%、分支 72.57%、核心行 93.59%、核心分支 75.00%，全部高于冻结门槛；Ruff、250
  文件格式、严格 Mypy 235 个源/测试文件、Alembic 空库升降级/无漂移、架构、OpenAPI/SSE、CI
  镜像契约、覆盖率配置和 Secret 扫描通过。前端 21 files/101 tests，行 87.31%、分支 75.98%，
  ESLint、TypeScript、生产 Build、契约与 bundle 预算通过；最大 chunk 189,644 bytes，四路由首次
  JS 图 1,460,738-1,484,436 bytes
- 生产同路径与失败矩阵：12 GiB Demo 的正式 React/FastAPI/MySQL/Chromium 用例 `1 passed
  (9.4s)`，完成 Owner 注册→创建工作区→创建 Viewer→Viewer 登录只读→Owner 重新登录，并继续
  验证跨源注册/写入、缺 CSRF、第二 Owner、恢复码、会话数据库过期、注销撤销和旧 Cookie 重放。
  正式 Uvicorn 集成另覆盖多工作区未选择 409、伪造租户 403、跨租户资源/SSE 404、Viewer 写入/
  管理 403、数据库跨租户外键拒绝、工具 allowlist 隔离和 RAGFlow 归属过滤
- 清理与文档：E2E finally 现同时清除认证状态和所有非默认测试工作区，失败截图/Trace、前端
  dist/coverage、后端覆盖率与本轮独立测试库已精确删除；18200/18280 无监听，平台容器和项目
  专属 Colima 已停止。默认开发库、稳定 Volume、镜像、0600 Token、冻结依赖和用户授权的百炼
  Demo Key 保留；产品范围、工程结构、前后端架构、README、OpenAPI 和本路线图已同步
- 遗留：无；下一任务 S10-04 对登录、配置、绑定、上传、删除、运行、权限拒绝和凭据操作建立
  不可篡改、可查询、脱敏且有明确保留/容量边界的审计与安全事件

### S10-04 审计与安全事件

- 状态：✅ 已完成
- 日期：2026-07-21
- 提交：本任务提交（见 Git 历史）
- RED：先为固定动作/结果/资源类型、UTC 与安全标识校验、SHA-256 规范载荷、保留/容量策略建立
  领域测试，最初因 `common_agent.audit` 与 `AuditSettings` 不存在失败；随后仓储测试因审计适配器
  不存在失败，正式 HTTP 测试因 Owner 审计入口返回 404 失败，前端 API/页面/路由测试因模块和
  菜单不存在失败，E2E 入口也先以“不支持 audit suite”关闭失败。全量复跑还揭示不可变平台链
  不能用 100 条临时容量反复复用脏测试库，修正测试为正式 100 万上限并使用本任务隔离空库，
  没有删除或放宽生产审计证据
- 领域与持久化：新增平台自有 `AuditEntry/Event/Query/Policy/Integrity` 与 `AuditStore` 端口，
  类型只允许动作、结果、请求/追踪 ID、可选租户/操作者/资源/错误码和 UTC 时间，不提供正文或
  任意 metadata 字段。`audit_chain_heads` 按 `platform` / `tenant:<uuid>` 串行分配序号，事件以
  规范 JSON 链接前一条 SHA-256；事件 ID、作用域序号、查询索引和链头约束由 MySQL 兜底，两个
  触发器拒绝既有事件 `UPDATE/DELETE`，Owner 可重建整链验证。默认保留标记 365 天、每作用域
  1,000,000 条、禁止自动删除，容量耗尽关闭失败
- HTTP 与前端：中间件覆盖登录/注销/恢复、成员/工作区、员工配置与绑定、知识上传、四类删除、
  会话回复、工作流手动/员工工具运行与停止，以及 401/403/429 安全拒绝；工具触发因绕过 HTTP
  显式复用同一审计服务。Owner 页面可切换当前工作区/平台作用域，按操作者、动作、资源和 UTC
  时间查询并继续加载游标，展示保留策略和链完整性；Editor/Viewer 的菜单、路由和后端入口均
  拒绝。OpenAPI、生成 DTO、第五路由 lazy chunk 和单路由首次 JS 图门禁同步
- 失败矩阵与生产同路径：正式 MySQL 仓储证明追加、倒序游标、平台/租户隔离、容量拒绝、触发器
  防改/防删和链校验；正式 Uvicorn 覆盖受审计变更、Viewer 拒绝、恢复凭据脱敏和平台链验证。
  12 GiB 正式 React/FastAPI/MySQL/Chromium 审计套件先后抓到 Ant Design 过滤器宽度、下拉定位和
  中文按钮可访问名称三项真实交互问题，修复后完成创建员工→Owner 审计页→完整性/策略→资源
  过滤→固定元数据/正文不出现，最终 `1 passed (3.1s)`；未启动或修改 RAGFlow，未调用百炼
- GREEN：后端权威全量 `553 passed, 13 skipped in 97.64s`；覆盖率
  全量同为 `553 passed, 13 skipped in 187.56s`，总体行 91.35%、分支 72.89%、核心行 93.59%、
  核心分支 75.00%，全部超过冻结阈值。Ruff、266 文件格式、严格 Mypy 250 个源/测试文件、uv
  lock、85 包安全审计、Alembic `0015` head/无漂移及 `0015→0014→0015`、OpenAPI/生成 DTO、
  架构、CI/覆盖率/E2E 入口、ShellCheck 和 Secret 门禁通过。前端 23 files/107 tests，行 87.35%、
  分支 76.04%，ESLint、TypeScript、Build、零高危依赖审计、契约与五路由 bundle 门禁通过；
  最大 chunk 189,644 bytes，审计路由首次 JS 图 1,458,569 bytes
- 清理与文档：E2E finally 精确删除测试员工并重置认证状态，失败截图/Trace 在完成诊断与 GREEN
  后删除；审计事件按禁止删除策略保留，覆盖率/构建/工具缓存等可再生产物已精确删除，18200、
  18280、19380、19506 无监听，平台/RAGFlow 容器和项目专属 Colima 已停止。稳定 Volume、官方
  镜像、0600 Token、冻结依赖和用户授权的
  百炼 Demo Key 保留；RAGFlow 官方 v0.25.6 submodule/源码/镜像/容器内文件均未修改。产品范围、
  工程结构、前后端架构、README、OpenAPI、生成 DTO 和本路线图已同步
- 遗留：无；下一任务 S10-05 以平台自有端口交付持久队列/Worker、至少一次投递、幂等重试、
  积压/崩溃恢复、多实例副作用互斥和可从持久序列恢复的 SSE
