# 通用 Agent 中台后端架构

> 状态：V1 已落地，V2 工具/MCP、私有 RAGFlow 与工作区级 RAGFlow 身份已落地
> 确认日期：2026-07-23
> 运行范围：本机 FastAPI + 按需平台基础设施 + 本机 RAGFlow，外部只调用阿里百炼

## 1. 建设目标

后端为浏览器提供统一的平台 API，MVP 完成四项业务能力，当前生产化阶段再为它们增加统一身份边界：

- 会话式 AI 对话；
- 数字员工创建、编辑和知识库绑定；
- RAGFlow 知识库创建、文档上传、解析状态和自动检索；
- 可视化工作流定义的校验、保存与 LangGraph 执行。
- 租户隔离的阿里百炼模型配置、真实调用验证和引用安全生命周期。
- 首位所有者注册、登录、恢复与可撤销的服务端安全会话。
- 组织下的多工作区、成员角色与五类业务资源的租户隔离。
- 固定元数据、租户隔离且不可原地篡改的审计与安全事件。
- MySQL 持久任务/事件、独立 Worker、租约恢复与跨进程 SSE 续传。
- 租户隔离的 MCP 来源、业务工具集、精确能力授权，以及通用 AI/数字员工工具调用。
- 基于官方 `v0.26.4` 精确提交、由私有仓库和 submodule 锁定的 RAGFlow 性能补丁。

普通聊天以 `Conversation` 和 `Message` 为主模型。只有用户或数字员工明确触发工作流时才创建 `WorkflowRun`。

## 2. 核心技术决策

### 2.1 模块化后端与可演进运行单元

当前启动形态把请求接入与长任务执行拆成 FastAPI 和独立 Worker 两类进程；二者共享平台端口与
MySQL 权威状态，不共享进程内任务。技术选型仍不构成产品功能或固定白名单：

```text
React
  -> FastAPI
       -> Repository + TaskQueue + EventJournal（平台独立 MySQL）
       -> 独立 Worker
            -> RAGFlow（知识文档、解析和检索）
            -> Deep Agents + 阿里百炼（数字员工回复）
            -> MCP Gateway（平台能力、托管 HTTP 与外部 MCP）
            -> LangGraph（独立工作流）
```

文件解析由 RAGFlow 自己的独立 Docker 栈处理。FastAPI 只发起官方 API 请求和轮询状态，不直连 RAGFlow 的 MySQL、Redis、检索引擎或对象存储。

### 2.2 阿里百炼单供应商

- 第一版只支持阿里百炼，不引入 LiteLLM 或供应商路由；
- 使用百炼 OpenAI 兼容接口和 `langchain-openai` 的 `ChatOpenAI`；
- `base_url` 和 API Key 来自后端配置；通用会话模型来自该会话当前持久化配置，数字员工默认
  模型来自员工配置，每轮请求可显式选择当前租户启用模型；独立工作流 AI 节点在 S10-07I 前仍
  使用后端默认模型；
- 用户明确批准现有百炼 Demo API Key 只在私有仓库 `backend/.env.demo` 中版本化，且明确选择不轮换；这是唯一凭据例外；
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
- `BailianModelConfigurationVerifier` 只接收经过领域校验的模型标识，以服务端统一凭据创建短生命周期
  百炼适配器并走同一平台 `ModelRequest` 流协议；无论成功失败都关闭同步/异步 HTTP 客户端。

### 2.3 Deep Agents 负责数字员工

- 固定使用官方 `deepagents==0.6.12` 和公开 `create_deep_agent` API；
- Deep Agents 适配器通过 `adapters/model/langchain.py` 的适配层内部桥取得配置好的
  `ChatOpenAI`，再传入系统指令和受控工具；该桥不是平台端口，不能被 application、domain、
  conversations、workflows 或 runtimes 消费；
- 第一版使用非 Sandbox 的 `StateBackend`；通过公开 Harness Profile 禁用默认通用子代理，
  从模型工具面排除 Todo、文件、Shell 和 `task` 全部内置工具，同时用 deny 规则拒绝所有
  文件读写，不能只依赖提示词声明安全边界；
- 工具解析器按本轮精确工作流授权与工具能力授权生成唯一调用面；未知/跨租户/停用 ID、重复远端
  名称或与 Deep Agents 保留工具重名时 fail closed；业务工具能力统一经 MCP 适配层，不能绕过
  网关直连业务 HTTP；
- 知识检索、工作流触发与 V2 工具调用通过显式受控能力进入平台应用服务；
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

- 组织、租户、成员关系和最小角色；
- 数字员工和知识库绑定；
- 租户模型配置及数字员工、工作流、会话对模型的通用引用关系；
- 会话与消息；
- 工作流定义和运行摘要；
- Demo 模式的知识库、文档正文与解析终态；
- RAGFlow 知识库的租户归属映射。
- 会话回复/工作流运行任务、租约/停止状态，以及可恢复的会话/工作流事件序列。

平台正式持久化使用独立 MySQL 8.4 LTS，通过 SQLAlchemy async、`aiomysql`、PyMySQL `>=1.1.1` 与 Alembic 接入，固定开发入口为 `127.0.0.1:19506/common_agent`。领域与应用层只依赖仓储端口；平台 MySQL 使用专属容器、端口、Volume 和资源限制，与 RAGFlow 内部 MySQL 完全隔离。SQLite 和其他数据库不能替代当前正式 MySQL 的完成验收。

`TaskQueue`、`TaskSubmission` 与 `EventJournal` 是平台自有端口，当前由 MySQL
`durable_tasks/durable_event_streams/durable_events` 实现，不引入 Redis/MQ，也不复用 RAGFlow
内部 Valkey。业务占位与任务在同一个 Unit of Work 原子提交；事件按租户与聚合串行分配序号。
任何未来外围实现仍必须补齐健康、失败、恢复、隔离、安全、容量和清理门禁。知识文档、切片、
向量和解析产物继续只由 RAGFlow 管理。

### 2.6 身份认证与安全会话

- 空数据库仅允许通过后端配置的一次性引导令牌创建首位 `owner`；本机统一入口把它自动生成到
  Git 忽略、权限 `0600` 的项目专属文件。数据库唯一引导槽与用户记录在同一事务内提交，创建
  成功后所有后续引导请求关闭失败；
- 密码由适配层使用 Argon2id 哈希，恢复码和随机会话令牌只保存 SHA-256 摘要，数据库泄露时
  不提供可直接重放的明文凭据；
- 登录成功设置 `HttpOnly`、`SameSite=Strict` Cookie，不在 JSON、日志或前端状态中返回会话
  令牌；会话同时受空闲时限、绝对时限和显式撤销约束；
- 浏览器写请求除 Cookie 外必须携带内存中的会话 CSRF 令牌，并通过精确 Origin 校验；SSE 只
  接受同源且已认证的 Cookie；
- 登录尝试按规范化邮箱和来源地址做时间窗限制，认证失败使用稳定公共错误，不泄露邮箱是否存在；
  新失败写入时按索引清理已超过时间窗且不再锁定的状态，避免记录永久累积；
- 恢复码只显示一次、逐枚消费且不能重放，成功重置密码后撤销全部旧会话。

### 2.7 组织、租户与 RBAC

- 首位所有者自动加入固定默认组织的默认工作区；Owner 可以在同一组织创建其他工作区，并为
  当前工作区创建 Editor 或 Viewer 成员账号。成员初始密码只在请求中出现，恢复码只返回一次；
- 角色固定为 `owner`、`editor`、`viewer`：三者都可读，Owner 与 Editor 可修改业务资源，只有
  Owner 可创建工作区和成员。后端权限判断是权威边界，前端禁用按钮只用于交互提示；
- 认证后先解析租户访问上下文。只有一个成员关系时可兼容省略选择；存在多个工作区时必须显式
  选择。REST 使用 `X-Tenant-ID`，原生 EventSource 因不能设置自定义请求头而使用同源
  `tenant_id` 查询参数；两者同时出现且不一致时关闭失败；
- 员工、Demo 知识库/文档、会话、工作流和运行记录都保存 `tenant_id`。所有仓储查询和删除检查
  必须带租户条件；复合唯一约束与复合外键阻止把其他租户的员工、会话、消息或工作流拼进当前
  资源。消息通过所属会话继承租户，不维护第二份可漂移字段；
- 请求上下文使用平台 `ContextVar` 传递已验证的 `TenantAccess`，仓储在缺失上下文时关闭失败。
  会话/工作流事件历史和资源变更锁都把租户 ID 纳入命名空间，相同资源 ID 不能跨租户共享状态；
- RAGFlow 仍只通过官方 API 使用。每个平台工作区对应一个独立 RAGFlow 技术账号/租户；
  `ragflow_tenant_identities` 保存平台租户、RAGFlow 租户 ID、账号邮箱和加密 Token，API 与 Worker
  在每次业务请求中按已验证的当前工作区动态解析 Token，不共享进程级认证 Header；
- 新工作区通过 RAGFlow 公开注册、登录、用户资料、模型和 Token API 自动初始化，并配置本工作区
  的百炼 embedding/rerank 实例与默认模型。默认工作区升级时原位接管既有
  `common-agent@local.test` 账号，不复制已有知识库；旧固定密码随接管轮换成按工作区和密钥版本
  派生的密码，密码不落库，后续本机模型配置脚本优先使用权限为 `0600` 的 API Token；
- RAGFlow Token 用独立 AES-256-GCM 多密钥 keyring 加密，AAD 同时绑定格式版本、平台租户、
  RAGFlow 账号邮箱和 RAGFlow 租户 ID；生产环境必须显式配置
  `COMMON_AGENT_RAGFLOW_IDENTITY_KEYS`，浏览器、日志和审计都不能取得明文；
- 平台知识库归属表继续作为第二层授权和旧数据接管证据：列表、详情、上传、检索和删除都复核
  归属，会话每轮检索也使用同一个带归属检查的 `KnowledgeBaseService`。升级前未登记的数据集只
  允许默认工作区惰性接管；若发现尚无独立身份的非默认旧映射，启动关闭失败并要求显式迁移，
  不静默复制、过滤或串租户。不修改或直连 RAGFlow 内部数据库。

### 2.8 审计与安全事件

- `audit/` 定义平台自有的固定动作、结果、资源类型、记录、事件、查询、完整性和保留策略；类型
  本身不提供正文或任意 metadata 字段，防止调用方误把密码、Token、恢复码、提示词或知识正文
  写入审计；
- HTTP 中间件在认证/租户解析完成后覆盖登录、凭据恢复、成员/工作区、员工配置与绑定、知识上传、
  资源删除、会话回复、工作流运行/停止和拒绝事件。路由只标记已成功解析的资源 ID；员工工具触发
  工作流因不经过 HTTP，直接通过同一 `AuditService` 记录；
- 平台安全事件使用 `platform` 作用域，各工作区使用 `tenant:<uuid>`；每个作用域由
  `audit_chain_heads` 串行分配单调序号并链接前一条 SHA-256 摘要，事件的规范 JSON 决定当前摘要；
- `audit_events` 只允许追加。MySQL 触发器拒绝 `UPDATE` 与 `DELETE`，唯一约束保护事件 ID 和
  作用域序号，Owner 可重建整条哈希链并与链头校验；普通角色和跨租户请求关闭失败；
- 默认保留策略为 365 天、每个作用域 1,000,000 条且禁止自动删除。`retention_until` 是策略标记，
  不是后台清理授权；达到容量时追加失败，已经成功的受审计业务请求转换为 503，不能静默漏记；
- 查询使用倒序 keyset 游标，支持租户/平台作用域、操作者、动作、资源和 UTC 时间范围。审计失败
  日志只包含动作与异常类型，不包含记录内容或上游响应。

### 2.9 备份、恢复与灾难演练

- 平台 MySQL 以应用停写后的 `mysqldump --single-transaction` 逻辑备份作为可移植恢复源；平台
  持有的 RAGFlow 外部知识库租户归属另行导出清单，恢复后必须与真实 RAGFlow 列表交叉验证；
- 平台不直连对象存储。上传对象、RAGFlow 元数据、检索索引和运行状态分别由其 MinIO、MySQL、
  Elasticsearch 与 Valkey 专属 Volume 持有，因此四者在 RAGFlow 停写后一起创建冷快照；
- `adapters/backup` 只负责大文件流式 AES-256-GCM、认证头、逐文件 SHA-256 清单和安全解包。
  Docker 停写、数据采集、保留和恢复编排属于 `infra/backup`，不进入 API/领域调用路径；
- 256-bit 备份密钥只从独立 `0600` 文件读取并与归档分开保管。部署配置采用显式白名单；百炼
  Key、RAGFlow 明文 Token、RAGFlow 身份 keyring、认证/恢复/引导凭据和数据库口令不得进入归档。
  平台库只包含 RAGFlow Token 密文；恢复时必须从独立秘密存储提供原身份 keyring，否则关闭失败；
- 当前恢复点是最近一次已验证归档，目标 RPO 24 小时、RTO 120 分钟、保留 30 天且至少保留 7
  个代际，每 90 天演练。开发 MySQL 未开启 binary log，因此不声称支持归档间任意时间点恢复；
- `restore` 只接受全新的 `common-agent-recovery-*` MySQL、Volume 和目录，任何既有表、Volume
  或目录都会关闭失败。灾演先从正式 React 页面向隔离源写入真实 RAGFlow 文档与绑定，再停写
  备份并销毁源，恢复到另一套空环境，最后由同一正式页面验证文档、绑定和审计链。

### 2.10 工具与 MCP

平台自有 `tools/` 模块定义 MCP 来源、能力、工具集、来源关联、精确授权、调用请求/结果和稳定错误，
不导入 MCP、LangChain、HTTP 客户端或供应商 SDK。`adapters/mcp/` 独占 MCP SDK、HTTP 转换、连接和
工具 Schema 映射；`adapters/agent/` 只在 Deep Agents 边界把平台 MCP 描述符包装成最后一跳
`BaseTool`，MCP 适配器本身不反向依赖 LangChain。
`jsonschema` 是该模块唯一登记的通用格式校验依赖，用于在配置写入和调用两处校验同一输入 Schema；
它不负责网络、供应商协议或运行时装配。

```text
Employee/Conversation exact grants
  -> ToolCapabilityResolver
  -> MCP Tool Adapter
       -> platform-native MCP（当前时间、工作流等平台能力）
       -> managed MCP -> fixed business HTTP base_url + capability path
       -> external MCP Streamable HTTP
```

- `mcp_sources` 保存租户、类型、显示信息、连接状态和稳定来源 ID；托管来源保存固定 Base URL，外部
  来源保存 Streamable HTTP URL。`mcp_source_credentials` 只保存类型、密钥 ID、12 字节随机 nonce、
  AES-256-GCM 密文、非秘密 Header 名称和时间戳，并用租户 ID、来源 ID 和格式版本作为 AAD；密文
  调换到其他租户或来源记录后无法解密；
- `tool_capabilities` 保存稳定 UUID、来源、远端名称、显示名、描述、输入 Schema、状态和 Schema
  fingerprint；托管 HTTP 能力另存 method/path/参数位置/超时/响应映射。远端改名视为新能力，旧能力
  标记不可用并保留历史引用；
- `tool_collections` 与 `tool_collection_sources` 只负责聚合目录；
  `employee_tool_collection_selections`、`conversation_tool_collection_selections` 只还原用户选择快照，
  `employee_tool_grants`、`conversation_tool_grants` 才是运行时权限。选择父集合只在显式保存时展开为
  当前可用叶子 UUID，任何发现、同步或新增能力都不得写授权表；
- 平台原生、托管和外部能力统一通过 MCP `tools/list` / `tools/call` 语义执行，再转换成平台自有结果
  与持久事件；Deep Agents 看不到来源类型，业务系统也不需要实现平台私有工具协议；
- T2-04 已落地托管 HTTP 的手工配置纵向切片：租户内 Base URL 与能力配置规范化入库，官方 MCP SDK
  负责进程内 `tools/list` / `tools/call`，调用前重新读取来源、能力、精确授权和服务端凭据，再经固定
  origin 的安全 HTTP 客户端执行；
- T2-05 的 `adapters/openapi/` 只接受 OpenAPI 3.0/3.1 JSON、YAML 和本地 JSON Pointer 引用，拒绝
  YAML 别名、重复键、外部/循环引用、受保护 Header 参数和不受支持的请求体，并对文件字节、结构
  深度/节点、引用深度和操作数设硬上限。预览只返回可编辑草稿与缺失说明，不写数据库；导入再次
  递归校验说明、名称冲突和整批内容，再以单个数据库事务写入能力及 HTTP 配置，任一项失败整批回滚；
- T2-06 的外部来源创建与编辑不发网络请求，只有显式同步才通过受控 Streamable HTTP 建立官方 MCP
  会话并分页执行 `tools/list`。同步按远端名称维持稳定能力 UUID；Schema 漂移先更新目录事实并隔离为
  `unavailable`，只有下一次得到相同 Schema 的显式同步才重新启用，能力消失则保留历史记录并标记
  不可用。同步失败只更新来源状态，不破坏上次能力目录；
- 业务工具集只允许关联当前租户的托管 HTTP 或外部来源。创建、修改和删除集合不会新增、删除或改写
  能力授权；删除集合只清除集合选择记录，已经展开保存的员工/会话精确能力授权继续保留；
- 首批平台原生运行时使用官方 MCP 1.x 稳定协议和进程内双端传输，不建立匿名 HTTP MCP 入口；
  “当前时间”只接受受限 UTC offset。既有工作流能力也先经过动态 MCP `tools/list/tools/call`，取消
  MCP 调用时按该次平台调用令牌停止对应工作流，不能绕过 MCP 直接从 LangChain Tool 调服务；
- V2 托管 HTTP 鉴权只允许 none、Bearer 和自定义 Header。可逆凭据使用独立多版本主密钥环认证
  加密，只有活动密钥写新密文、旧密钥只用于解密；API 只返回固定长度掩码，更新显式区分
  `keep/replace/clear`，不会把掩码当作数据回传或猜测用户意图。用户名/密码代登录、OAuth 与 stdio
  MCP 不建立 DTO、数据库字段或前端选项；
- 托管/外部网络访问固定 origin。运维配置只接受精确主机与规范 CIDR，私网必须命中显式 CIDR，
  loopback 还需独立开关，link-local/metadata、multicast 和 unspecified 永不放行；明文 HTTP 另有精确
  主机许可。自定义 HTTP transport 在每次 TCP 建连前重新解析全部地址、全部校验后直接连接已验证
  IP，同时保留原主机用于 Host/TLS SNI，不修改进程全局 DNS；连接池禁用 keepalive，系统代理和
  自动重定向均不启用；总调用、连接、读取、响应大小与并发均有平台上限；
- 工具参数和自定义凭据不能覆盖 Host、连接/分帧或代理 Header，自定义 Header 也不能伪装 Bearer
  `Authorization`；响应正文和 Header 不进入对象 `repr`，安全异常只返回稳定分类，不带 URL 查询、
  DNS 地址、凭据或上游正文；
- 工具调用默认不自动重试有副作用的 `tools/call`。调用结果未知、能力失效、软失败、协议错误和
  响应超限分别映射稳定错误；每次调用在 Worker 中再次检查租户与授权，并写固定元数据审计和会话
  工具事件，不保存凭据或默认保存完整参数/结果；
- 模型兼容目录按 provider + model identifier 保存“绑定工具时禁用供应商流式调用”能力。只有真实
  Trace 证明 tool-call chunk 无法关联时才登记；适配器用公开模型配置能力取得完整调用，外层平台
  SSE、工具事件和纯文本模型流继续工作。

### 2.11 私有 RAGFlow 补丁

V2 允许 RAGFlow 成为第三方零侵入规则的唯一受控例外。补丁仓库从官方
`v0.26.4@cb93883f3f8c975eecb2fed81210effeb3bdb06f` 建立，保留 `upstream` remote、官方基线、
版本化 common-agent 分支、逐补丁测试/基准和回滚提交。平台仍只调用公开 RAGFlow API，不因维护
fork 而直连其 MySQL、Elasticsearch、Valkey 或 MinIO。

common-agent 的 `third_party/ragflow` 只锁定已经推送到私有远端的提交；基础设施同时校验上游基线、
fork commit、submodule origin、镜像标签和干净工作树。写入、删除、列表/读取和检索补丁按测得瓶颈
逐项进入，不能复制 HugAI 专用路由、全局关闭 ES refresh 或未经 32 GiB 正式栈验证的并发值。

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
+-> tools --------------->+ adapters/mcp/http
+-> workflows ----------->+ adapters/workflow/langgraph
 +-> ports ---------------->+ adapters/mysql|redis|queue|object_store

worker_app -> application/tasks/events -> adapters/mysql|ragflow|bailian|deep_agents|langgraph
```

### 3.1 API 层

只负责：

- HTTP、multipart 上传和 SSE 边界；
- 身份 Cookie、CSRF、可信 Origin 与安全响应头；
- Pydantic 请求/响应校验；
- 应用错误到稳定错误信封的转换；
- 请求 ID、W3C trace context、进程内指标、超时和资源释放。

知识库上传入口只接收 TXT、Markdown、PDF、DOCX，单文件上限 20 MiB；API 分块读取到
上限后一字节并在所有终态关闭 `UploadFile`，应用服务统一校验扩展名、MIME、空文件和大小，
通过后才调用正式 RAGFlow 适配器。

禁止在路由中拼提示词、直接调用 RAGFlow SDK、编译 LangGraph 或写 SQL。

会话、工作流定义和工作流运行路由只保留 HTTP 用例编排；Pydantic DTO 位于
`api/schemas/`，服务依赖解析集中在 `api/routers/services.py`，会话 SSE 独立位于
`conversation_events.py`，历史列表、详情和删除入口独立位于 `conversation_history.py`。路由不能
重新吸收 Schema、事件流实现或服务装配。

### 3.2 Application 层

提供明确用例：

- `EmployeeService`：数字员工 CRUD、知识库绑定和工作流 allowlist 引用校验；
- `KnowledgeBaseService`：RAGFlow 知识库与文档操作；
- `ToolService`：MCP 来源、能力、工具集、精确授权、发现与调用；
- `ConversationService`：创建会话、保存消息、自动检索、生成回复；
- `WorkflowService`：校验、保存和运行工作流；
- `ResourceDeletionService`：统一执行会话、员工、知识库和工作流的引用安全删除；
- `SystemService`：报告后端、百炼和 RAGFlow 真实状态。

API 中的会话发送和工作流启动只创建权威业务占位与持久任务，不调用模型或编译器；独立
`worker_app` 按任务租户绑定关闭失败的系统上下文，再调用同一个服务门面执行。会话任务与工作流
任务按类型领取，默认八个槽位由会话和工作流各保留四个消费者，避免数字员工等待子工作流时
耗尽全部消费者，也避免工作流积压饥饿。

`ConversationService` 与 `WorkflowService` 是保持公开调用面的薄门面，不承载全部实现：

- 会话由 `ConversationPersistence` 管理事务读写与重试准备，`ConversationRuntimeCoordinator`
  管理活动生成、停止和资源关闭，`ConversationMessageProjector` 把运行事件写入消息权威快照；
- 工作流由 `WorkflowCatalog` 管理定义校验与保存，`WorkflowRunCoordinator` 管理编译、执行、
  停止和等待，`WorkflowRunProjection` 管理运行摘要与事件投影；
- contracts 模块保存稳定服务错误和返回值，具体实现不得反向导入门面，也不得形成循环依赖。

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

资源创建、引用变更、运行启动与删除共享 `ResourceMutationGuard`，按员工、知识库和工作流键排序
持锁；应用服务先在锁内重新检查引用，再提交本地事务或调用 RAGFlow，避免同一进程内出现“检查
通过后新增引用”的竞态。该锁只覆盖当前进程；跨 API/Worker 的执行互斥由 MySQL 原子业务提交、
任务幂等键、`FOR UPDATE SKIP LOCKED`、租约和随机栅栏令牌保证，不能把进程锁当成分布式锁。

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
| Argon2 | `adapters/auth/` |

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
├── default_model_configuration_id: UUID
├── default_model_identifier: string
├── knowledge_base_id: string | null
├── allowed_workflow_ids: list[UUID]
├── selected_tool_collection_ids: list[UUID]（仅选择快照）
├── granted_tool_capability_ids: list[UUID]（关系表权威权限）
├── created_at
└── updated_at
```

第一版一个员工最多绑定一个 RAGFlow 知识库，并必须绑定当前租户的一个模型配置。员工未绑定
知识库时不执行检索。模型标识由模型配置联表解析，不在员工表维护第二份可漂移副本。

`Employee` 是与具体业务无关的会话角色配置：只保存名称、说明、系统指令和平台能力引用，
不保存行业字段、业务任务状态或 automation-tool 的业务模型。`allowed_workflow_ids` 只是对独立
工作流公开能力的调用白名单，不内嵌工作流图。工具集合选择用于还原用户选择视图，真正调用权限
来自租户内 `employee_tool_grants` 的稳定能力 UUID；保存父集合时展开一次，后续同步不自动增加。

### 4.2 模型配置

```text
ModelConfiguration
├── id: UUID
├── display_name
├── provider: bailian
├── model_identifier
├── enabled
├── streaming_breaks_tool_calls: bool（平台目录派生，只读）
├── created_at
└── updated_at

ModelToolStreamingCapability
├── provider: bailian
├── model_identifier
├── streaming_breaks_tool_calls: bool
├── evidence_revision
├── observed_at
└── updated_at
```

模型配置是当前租户的业务资源；显示名称和同一提供商模型标识在租户内唯一，模型标识只允许
字母、数字、点、下划线和连字符，不能把 URL、路径或任意供应商参数带入适配器。列表使用
`created_at DESC, id DESC` keyset 游标，并可只返回启用配置，筛选条件进入游标作用域。

`model_configuration_references` 是员工、工作流和会话绑定模型的统一引用表。员工写入与
`employees.default_model_configuration_id` 和引用表在同一事务更新。删除在同一租户
分布式资源锁和 MySQL 事务中重新查询引用，有引用时返回 `model_configuration_in_use`；复合外键
同时阻止跨租户引用和绕过应用层的删除。停用只影响后续新选择，不改写既有引用。测试调用允许在
启用前执行，以便用户先验证再启用；它不持久化提示词或供应商正文，只审计固定动作与资源 ID。

工具流兼容记录是平台维护的模型能力事实，不由普通租户配置随意开启。解析模型时按
`provider + model_identifier` 合并；未登记默认保持正常流式，只有可复现 Trace 和回归证据才能写入
禁流标记。兼容表没有 `tenant_id`，租户模型配置增删改 DTO 也不接受该字段；模型列表和详情只返回
当前目录联表派生出的只读结果。数据库读取失败不能把所有模型静默切成另一模式，调用应按稳定错误
收敛，不能靠进程缓存或租户输入猜测兼容性。

### 4.3 会话与消息

```text
Conversation
├── id: UUID
├── source: generic | employee
├── employee_id: UUID | null
├── model_configuration_id: UUID | null
├── granted_tool_capability_ids: list[UUID]（关系表）
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
├── model_configuration_id: UUID | null
├── model_identifier: string | null
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

`generic` 会话不得绑定员工且必须持久化当前模型配置；`employee` 会话必须绑定员工且不保存可
漂移的会话级模型。助手消息同时保存本轮实际模型配置 ID 和百炼模型标识快照，用户消息的两个
字段必须为空；因此员工后续改默认模型或通用会话后续切模都不会改写历史事实。

通用会话的工具授权由 `conversation_tool_grants` 保存；员工会话每轮从员工精确授权创建不可变
执行快照。两种来源都默认空，工具集合关系不能在运行时动态扩展权限。既有授权后来不可用时可在
编辑动作中原样保留或显式撤销，但不能把新的不可用能力加入授权；运行时仍按当前来源和能力状态
关闭失败。历史工具调用通过持久会话事件保留状态，不把完整参数、结果或凭据塞入消息正文。

平台 MySQL 使用 `conversations`、`messages`、`message_citations` 三张表。员工会话通过正式外键
引用平台员工，通用会话通过复合外键引用模型配置，消息和引用使用级联子记录；角色/状态组合、错误码、长度、时间顺序、会话内
消息序号及引用分数同时由领域模型和数据库约束。Repository 只更新标题或消息运行态等可变
字段；只有通用会话可在每轮提交时更新当前模型，不允许借更新操作迁移来源、员工、会话归属、
序号、角色或创建时间。

### 4.4 EmployeeRuntime 会话协议

`EmployeeRuntime` 每次 `stream(request, stop=...)` 只生成同一会话中的一条助手回复，不创建
任务实体，也不暴露旧任务模型的启动、审批、恢复或产物方法。请求显式携带 Conversation、
Employee、助手占位消息 ID/序号、员工系统指令、按持久化序号排列的模型可见历史、知识库
绑定/检索片段、员工解析后的模型标识、允许调用的工作流 ID 和精确工具能力 ID；系统指令、历史正文与知识原文彼此分离，适配器不能靠
拼接无类型字典猜测来源。

`DeepAgentsEmployeeRuntime` 每轮按请求模型标识从 `BailianChatModelResolver` 取得对应
`ChatOpenAI`；解析器按“模型标识 + 工具流兼容模式”分别复用适配器并在运行时关闭时统一释放客户端。
只有本轮存在授权工具且模型目录已标记时才使用 LangChain 公开的 `disable_streaming=tool_calling`
能力；适配器构造时不固定 `streaming=True`，普通平台文本流在调用处显式请求流式，以免覆盖工具调用
的公开非流式降级。模型配置停用不中断已有员工，员工改选或新建时则由 `EmployeeService` 关闭失败。

历史最多 100 条且总计 400,000 字符；知识上下文最多 20 段且总计 120,000 字符。未绑定知识
库时上下文必须为空；已绑定但检索零命中仍保留 `knowledge_base_id` 并允许空上下文，不能把这
两种情况混为一谈。所有片段必须来自当前绑定知识库且引用唯一；允许的工作流 UUID 也必须
唯一并有数量上限；工具能力 ID 同样必须唯一、属于当前租户和本轮授权快照。系统指令、历史正文、
知识原文、工具参数/结果和模型增量从运行时对象 repr 排除。

运行时事件只包含 `delta/completed/failed/stopped`：序号在单次回复内从 1 单调递增，文本只
存在于 delta，错误码只存在于 failed，并且只能产生一个终态。`RuntimeStopToken` 表示幂等的
协作式停止意图；Deep Agents 适配器必须同时等待上游下一事件与停止信号，停止胜出时关闭上游
迭代并产生 stopped，不能把用户停止伪装成失败，也不能在终态后接受晚到内容。A4-06 再把
这些内部事件映射为持久化后才能推送的平台 SSE 事件，二者的 sequence 不互相冒充。

### 4.5 知识库引用

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
关闭失败并拒绝写入。若数据集在平台之外被直接删除，员工定义保留原引用，由读取/会话链路
返回稳定的“知识库不存在或已失效”错误，不能静默改成无知识库回答。展示缓存只有出现真实
性能需要时才引入，缓存不得取代 RAGFlow 的权威状态。

Demo 模式实现相同 `KnowledgeService` 协议，但不调用或伪装 RAGFlow。项目专属 MySQL 的
`demo_knowledge_bases` 与 `demo_knowledge_documents` 保存知识库、文档正文、完成/失败状态和
稳定顺序；外键只约束 Demo 文档归属，不把员工表绑定成 Demo 专用结构。后端重启后，员工绑定、
已有消息引用和重新检索必须指向同一知识库与文档；应用关闭不得清空已提交数据。Demo 数据仍由
明确测试/用户删除生命周期管理，不能依赖进程退出制造“已清理”。

### 4.6 工作流

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
节点开始、完成以及运行终态每次都先提交摘要，再写入持久 SSE 事件。启动运行时在同一事务提交
`pending` 摘要与确定性任务；独立 Worker 领取后才进入 `running` 并编译执行。进程关闭只取消
本进程执行，租约到期后由任一 Worker 接管；用户停止则持久写入停止意图并由心跳传给当前持有者。

## 5. AI 会话链路

```text
用户发送消息
  -> 已有会话校验来源和执行目标；空白通用对话经原子首轮入口创建会话
  -> 校验本轮模型属于当前租户且启用；员工临时选择不修改员工默认模型
  -> 同一事务持久化用户消息、助手占位消息与确定性回复任务
  -> 独立 Worker 按租约领取并绑定任务租户
  -> ConversationExecutionTargetResolver 解析通用或员工执行目标及实际模型
  -> 员工目标由 ConversationKnowledgeResolver 检查知识库绑定；通用目标不执行知识检索
  -> 已绑定时经 KnowledgeBaseService 校验 RAGFlow 可用性/版本
  -> KnowledgeService.retrieve(question)
  -> 把历史消息、系统指令、知识片段和引用交给 EmployeeRuntime
  -> Deep Agents 调用阿里百炼
  -> 如模型调用授权能力，经统一解析器进入平台 MCP、托管 HTTP、外部 MCP 或 WorkflowService
  -> 工具开始/完成/失败先形成持久事件，再把 MCP 结果交回模型继续生成
  -> 每个 Runtime delta/终态先写回助手消息和引用并提交 MySQL
  -> 再把 assistant.delta / assistant.completed 等平台事件追加到持久序列
```

检索为空不是错误：数字员工应明确说明未找到相关知识，并基于通用能力回答或说明无法确定。RAGFlow 请求失败则本轮回复失败，不静默跳过知识库后假装是知识回答。

`POST /api/v1/conversation-turns` 是空白通用对话的原子首轮入口：同一 MySQL Unit of Work 创建
会话、精确工具授权、完成态用户消息、助手占位和持久任务；工具集在进入事务前解析为当时可用的
稳定能力 ID，任何模型、授权、租户或事务失败均不留下空会话、半轮消息或孤立授权。数字员工首轮
拒绝会话级覆盖，只继承员工精确授权。既有会话继续使用消息入口；两者都把助手实际模型与工具
授权快照交给独立 Worker，Worker 不读取可能已变化的员工、会话模型或集合关系来重算本轮选择。

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
GET    /api/v1/system/health
GET    /api/v1/system/status
GET    /api/v1/system/metrics

GET    /api/v1/auth/policy
POST   /api/v1/auth/register
POST   /api/v1/auth/login
GET    /api/v1/auth/session
POST   /api/v1/auth/logout
POST   /api/v1/auth/recovery/reset

GET    /api/v1/audit-events
GET    /api/v1/audit-events/integrity
GET    /api/v1/audit-events/policy

GET    /api/v1/model-configurations
POST   /api/v1/model-configurations
GET    /api/v1/model-configurations/{model_configuration_id}
PUT    /api/v1/model-configurations/{model_configuration_id}
DELETE /api/v1/model-configurations/{model_configuration_id}
POST   /api/v1/model-configurations/{model_configuration_id}/verify

GET    /api/v1/managed-mcp-sources
POST   /api/v1/managed-mcp-sources
GET    /api/v1/managed-mcp-sources/{source_id}
PUT    /api/v1/managed-mcp-sources/{source_id}
DELETE /api/v1/managed-mcp-sources/{source_id}
POST   /api/v1/managed-mcp-sources/{source_id}/discover
POST   /api/v1/managed-mcp-sources/{source_id}/capabilities
PUT    /api/v1/managed-mcp-sources/{source_id}/capabilities/{capability_id}
DELETE /api/v1/managed-mcp-sources/{source_id}/capabilities/{capability_id}
POST   /api/v1/managed-mcp-sources/{source_id}/capabilities/{capability_id}/test-call
GET    /api/v1/mcp-sources/{source_id}/credentials
PUT    /api/v1/mcp-sources/{source_id}/credentials

GET    /api/v1/mcp-sources
POST   /api/v1/mcp-sources
GET    /api/v1/mcp-sources/{source_id}
PUT    /api/v1/mcp-sources/{source_id}
DELETE /api/v1/mcp-sources/{source_id}
POST   /api/v1/mcp-sources/{source_id}/refresh
GET    /api/v1/mcp-sources/{source_id}/capabilities
POST   /api/v1/mcp-sources/{source_id}/capabilities
POST   /api/v1/mcp-sources/{source_id}/openapi/preview
POST   /api/v1/mcp-sources/{source_id}/openapi/import
GET    /api/v1/tool-collections
POST   /api/v1/tool-collections
GET    /api/v1/tool-collections/{collection_id}
PUT    /api/v1/tool-collections/{collection_id}
DELETE /api/v1/tool-collections/{collection_id}
GET    /api/v1/tool-capabilities
GET    /api/v1/tool-catalog
GET    /api/v1/employees/{employee_id}/tool-grants
PUT    /api/v1/employees/{employee_id}/tool-grants
GET    /api/v1/conversations/{conversation_id}/tool-grants
PUT    /api/v1/conversations/{conversation_id}/tool-grants

GET    /api/v1/employees
POST   /api/v1/employees
GET    /api/v1/employees/{employee_id}
PUT    /api/v1/employees/{employee_id}
DELETE /api/v1/employees/{employee_id}

GET    /api/v1/knowledge-bases
POST   /api/v1/knowledge-bases
GET    /api/v1/knowledge-bases/{dataset_id}/documents
POST   /api/v1/knowledge-bases/{dataset_id}/documents
DELETE /api/v1/knowledge-bases/{dataset_id}

GET    /api/v1/conversations
POST   /api/v1/conversations
POST   /api/v1/conversation-turns
GET    /api/v1/conversations/{conversation_id}/messages
POST   /api/v1/conversations/{conversation_id}/messages
GET    /api/v1/conversations/{conversation_id}/events
POST   /api/v1/conversations/{conversation_id}/stop
DELETE /api/v1/conversations/{conversation_id}
POST   /api/v1/messages/{message_id}/retry

GET    /api/v1/workflows
POST   /api/v1/workflows
GET    /api/v1/workflows/{workflow_id}
PUT    /api/v1/workflows/{workflow_id}
DELETE /api/v1/workflows/{workflow_id}
POST   /api/v1/workflows/validate
POST   /api/v1/workflows/{workflow_id}/runs
GET    /api/v1/workflow-runs/{run_id}
POST   /api/v1/workflow-runs/{run_id}/stop
GET    /api/v1/workflow-runs/{run_id}/events
```

四类删除是 MVP 后 U9-01 增加的正式能力；模型配置另有自己的引用安全删除。U9-03 为既有五类
列表交付统一游标与基础服务端搜索，模型配置沿用同一分页协议。
权限与 Owner 审计已由 Wave 10 交付；批量操作和业务列表高级筛选仍不属于当前范围。

### 7.1 资源删除矩阵

| 资源 | 删除前检查 | 成功后的子资源 | 阻断语义 |
| --- | --- | --- | --- |
| 会话 | MySQL 中没有 `pending/streaming` 助手消息 | 消息、引用、由该会话触发的员工工作流运行级联删除 | 活跃回复返回 `conversation_busy` |
| 数字员工 | 没有会话引用 | 员工记录删除 | 有会话返回 `employee_in_use_by_conversations` |
| 知识库 | 没有员工绑定或工作流节点引用 | RAGFlow 数据集及其文档/索引由官方 API 删除；Demo 文档外键级联 | 分别返回 `knowledge_base_in_use_by_employees` / `knowledge_base_in_use_by_workflows` |
| 工作流 | 不在员工 allowlist，且没有 `pending/running` 运行 | 定义、节点、边和已终止运行级联删除 | 分别返回 `workflow_in_use_by_employees` / `workflow_has_active_runs` |

所有 DELETE 成功都返回 `204`，目标已经不存在时也返回 `204`，以便客户端安全重试。MySQL 删除
在单事务内重新检查引用，并以外键约束兜底；知识库必须先完成本地引用检查，再调用 RAGFlow
官方删除接口。连接中断、5xx、非法响应等无法确认远端结果的情况返回稳定且不可自动重放的
`knowledge_base_delete_result_unknown`，客户端刷新权威列表确认后再由用户重试，避免重复外部
副作用被伪装成确定成功。

### 7.2 列表分页、搜索与排序

会话、数字员工、知识库、工作流和会话内运行摘要的公开列表统一接受 `search`、`limit`、
`cursor`，统一返回 `items` 与可空 `next_cursor`。`limit` 为 `1-100`，搜索词最多 128 字符，
游标最多 1024 字符；游标使用 URL-safe 的规范 JSON、上下文指纹和校验和封装，绑定资源作用域、
搜索词和页大小，被修改或跨筛选复用时以 `invalid_page_cursor` 关闭失败，不包含凭据或业务正文。

平台 MySQL 的普通资源查询按不可变的 `created_at DESC, id DESC` 做 keyset seek；会话历史按
`updated_at DESC, id DESC` 排序，使新消息把会话稳定移动到顶部。两类查询都用组合索引覆盖无筛选
翻页；每次只读取 `limit + 1` 条判断下一页，不先物化全表。工作流列表先读取一页定义，再分别以
两条批量查询装载节点和边，因此非空页固定为 3 条 SQL，不按工作流数量增长。名称、标题和运行
输入采用可命中 B-tree 组合索引的前缀搜索，完整 UUID 与状态走等值索引；不使用 `%关键词%`
全表扫描，也不把全表拉入应用进程。会话员工筛选和运行会话筛选均保留在组合索引首列。

RAGFlow v0.26.4 数据集列表只走官方 `page/page_size/orderby/desc` 与 `ext.keywords` 能力；其页码
和总数在 `RagflowKnowledgeService` 内转换为平台 opaque offset cursor，第三方分页类型不越过
适配层。平台运行时不热改 RAGFlow，也不直连其 MySQL；V2 性能修改只存在于 submodule 锁定的私有
补丁仓库。创建或删除后客户端必须废弃旧页链；在同一
页链内新增的更靠前记录不会插入后续 keyset 页，删除游标锚点也不会使读取失效。

### 7.3 日志、指标与追踪

正式应用统一向标准输出写单行 JSON 日志，固定包含 UTC 时间、级别、logger、稳定事件名和
源码位置；HTTP 完成事件附带方法、路由模板、状态、耗时与稳定错误码。每个请求生成
`X-Request-ID`，接受合法 W3C `traceparent` 并建立本地 span；非法或缺失 header 安全替换，
响应返回当前 `traceparent`。RAGFlow 与百炼外围适配器从平台上下文派生子 span 并透传
`traceparent`/请求 ID，不把供应商 HTTP 类型带入平台层。

会话后台运行绑定 `conversation_id/message_id/turn_id`，工作流绑定
`workflow_id/run_id`，员工触发工作流同时继承会话来源；started/finished 事件只记录状态、
耗时和稳定错误码。日志默认按字段和文本模式脱敏提示词、知识/文档正文、请求/响应正文、
API Key、Authorization、Token、密码和 Secret；未知异常只记录异常类型，不记录异常消息或
堆栈正文。应用内 Alembic 迁移复用同一 JSON logger，独立 Alembic CLI 仍保留其工程输出。

`GET /api/v1/system/metrics` 返回当前进程启动时间、请求进行中/总数、2xx-5xx 状态桶、
有容量上限的稳定错误码计数和延迟 count/total/maximum；指标入口自身不计入快照，避免读取
改变所读数值。该入口是本机最小诊断面，不是持久审计、跨实例聚合或 Prometheus 兼容承诺，
进程重启后重置；不得以高基数业务 ID、提示词、知识正文或凭据作为指标标签。

## 8. 会话与工作流事件

会话和工作流流式事件统一使用 SSE。当前会话事件为：

```text
assistant.started
assistant.delta
assistant.completed
assistant.failed
assistant.stopped
assistant.tool.started
assistant.tool.completed
assistant.tool.failed

workflow.run.started
workflow.node.started
workflow.node.completed
workflow.node.failed
workflow.run.completed
workflow.run.failed
workflow.run.stopped
```

每个会话事件包含固定 `schema_version`、`conversation_id`、`message_id`、`turn_id`、会话内
单调 `sequence`、时间和已持久化的消息快照；delta 事件额外包含本次文本增量，重试开始事件
带 `retry=true`。工具事件额外包含稳定 `tool_call_id`、能力 UUID、显示名和安全状态，不包含
凭据或默认包含完整参数/结果；新增事件必须提升并生成对应 Schema 版本。SSE 的 `id` 与 payload sequence 一致，支持 `after_sequence` 和
`Last-Event-ID` 从 MySQL 持久序列跨 API/Worker 重启回放。无法续传时前端必须重新读取 MySQL 权威消息历史，不能猜测
丢失内容。前端只消费平台事件，不解析 LangGraph 或 Deep Agents 原始事件。

每个工作流事件包含固定 `schema_version=1`、`run_id`、`workflow_id`、运行内单调
`sequence`、可选 `node_id`、时间和已提交的完整 `WorkflowRun` 快照。工作流 SSE 同样支持
`after_sequence` 与 `Last-Event-ID` 回放 MySQL 持久历史；历史超过保留期或出现缺口时，客户端以
`GET /api/v1/workflow-runs/{run_id}` 的 MySQL 摘要为权威，不从缺失事件推测终态。

正式 Broker 使用每流最多 100,000 个事件、默认 30 天保留标记和整个 API 进程最多 1,024 个
持久订阅者；每个订阅者按最多 128 条一批轮询，不在 API 内复制无界历史。达到流容量时关闭失败，
保留边界造成缺口时返回 `event_history_unavailable`。未装配 Journal 的分层测试 Broker 继续使用
每 ID 512 条、每订阅队列 128 条、每 ID 64 个订阅者、全局 1,024 个订阅者及 300 秒 TTL/LRU，
两种实现共享完全相同的平台事件协议。

会话和工作流的按 ID 串行区使用引用计数锁池；持有者、等待者及取消中的等待者离开后，最后
一个引用会安全删除锁项。因此大量一次性会话/运行不会在进程内永久留下 `asyncio.Lock`，同一
ID 的并发互斥语义保持不变。

发送接口在一个 Conversation Unit of Work 中原子提交用户消息、助手占位、会话更新时间和任务；
Worker 领取后发布 started，后续每个事件也严格“提交后发布”。客户端生成的用户
`message_id` 是重复提交边界，同一会话有活跃助手消息时拒绝第二次发送。停止只发出停止意图，
最终 stopped 仍由正式运行时收敛并持久化；重试只允许最后一条 failed/stopped 助手消息，复用
原消息 ID/序号并清空不完整内容。运行中进程消失后任务由租约恢复，不提前把消息写成失败。

手动运行接口用客户端 `run_id` 原子提交 `pending` 摘要与任务；Worker 领取后提交 `running`、
发布 started 并启动 LangGraph。重复 ID 返回冲突且绝不重复入队。节点 started/completed 和最终
completed/failed/stopped 都严格提交后发布。停止接口只接受活跃运行并设置协作式停止意图，
当前节点与持久停止信号竞速，停止胜出后取消节点任务并由运行服务持久化 stopped；Worker 崩溃
不伪造终态，租约到期后重启执行并清除上一尝试的部分节点进度。

任务语义为至少一次：同一租户幂等键只创建一条记录；领取使用行锁跳过已占用任务，有限重试采用
有界指数退避。租约心跳同时传播停止意图；租约丢失会直接取消旧处理器且不写任务/业务停止终态，
完成、失败和取消都必须携带当前随机栅栏令牌。最终业务终态已提交但事件追加中断时，重试只补写
确定性终态事件，不再次调用模型或执行工作流副作用。

## 9. 错误语义

稳定错误至少包括：

- `configuration_missing`：必要本地配置缺失；
- `model_configuration_not_found`：当前工作区不存在指定模型配置；
- `model_configuration_conflict`：显示名称或百炼模型标识在当前工作区重复；
- `model_configuration_in_use`：数字员工、工作流或会话仍引用该模型配置；
- `employee_model_disabled`：新建员工或切换默认模型时选择了已停用配置；
- `model_unavailable`：百炼超时、限流或服务错误；
- `knowledge_service_unavailable`：RAGFlow 不可达；
- `knowledge_base_not_found`：绑定或节点引用失效；
- `document_upload_failed`：文件上传失败；
- `workflow_invalid`：节点图不合法；
- `workflow_run_conflict`：客户端运行 ID 已经提交；
- `workflow_run_not_active`：运行已终止或没有可停止的持久任务；
- `event_history_unavailable`：请求序号不存在或已超过持久事件保留边界；
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

稳定开发栈使用 `common-agent-dev` 命名空间，其中 RAGFlow 相关服务使用
`common-agent-ragflow-*` 前缀；平台 MySQL 使用 `common-agent-platform-*`，API 与 Worker 使用
互不冲突的项目专属 launchd 标签和日志。平台 MySQL 数据、上传临时文件、服务 Volume 映射和
日志统一放在根目录 `.local/`；平台 MySQL 与 RAGFlow 使用不同的 Compose project、容器、网络和 Volume。

RAGFlow 正式 submodule 已固定私有补丁 revision
`21eb8fb4001421f2952ce3125e46e753825d3f9b`，其官方上游基线仍为
`v0.26.4@cb93883f3f8c975eecb2fed81210effeb3bdb06f`；`infra/ragflow/manage.sh` 同时验证
upstream tag/祖先关系、fork origin/commit、官方基底 digest、镜像 OCI revision 和补丁文件哈希。
私有补丁只保留文档列表/定向删除、embedding 独立限流、根目录查询三项无法由官方扩展点实现的能力，
生产改动严格限制为 4 个文件；批量写入及三类并发参数由 common-agent Compose 覆盖层维护，不修改
RAGFlow 自带 Docker 配置。
知识库新建、既有索引
重建和检索分别显式固定阿里百炼
`text-embedding-v4@common-agent-embedding@OpenAI-API-Compatible` 与
`qwen3-rerank@common-agent-rerank@OpenAI-API-Compatible`，不启动或兜底到本地
embedding/rerank。
`OpenAI-API-Compatible` 在这里只是 RAGFlow v0.26.4 调用百炼官方 embedding/rerank 兼容端点的
传输类型；聊天、向量和重排仍全部来自单一阿里百炼供应商，不构成多模型网关，也不允许平台
业务层直接依赖 RAGFlow 的 Provider 类型。稳定栈使用独立
`common-agent-dev` Colima profile（8 CPU、32GiB 内存、100GiB 容器磁盘）和
`colima-common-agent-dev` Docker context。R8-04 已在完整冷启动、中文索引重建/检索、两轮会话、
工作流和 30 分钟连续采样下确认 VM 峰值 6.91GiB、容器峰值 6.85GiB、Swap/重启/OOM 为 0，
S10-07A 升级 v0.26.4 后又以 180 个连续样本确认 VM/容器峰值 7.28/7.23GiB 且同样无 Swap、重启
或 OOM，因此 32GiB 是长期 `real` 默认值；不得裁剪 RAGFlow 必需服务、降低中文质量或占用其他
项目的默认 context。

## 11. 官方能力依据

- Deep Agents 官方 `create_deep_agent` 支持传入模型实例、工具和系统提示词；
- 阿里百炼官方提供 OpenAI 兼容 Chat Completions 和 `ChatOpenAI` 接入；
- LangGraph `StateGraph` 以状态、节点和边描述并编译图；
- RAGFlow 官方 HTTP/Python API 提供数据集、文档和检索能力。

具体依赖版本在对应路线图任务中锁定，禁止使用漂移版本。
