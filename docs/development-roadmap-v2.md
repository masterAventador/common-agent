# 通用 Agent 中台 V2 开发路线图

> 文档性质：V2 当前任务与执行结果的唯一台账
> 建立日期：2026-07-22
> 当前阶段：R2-09 已完成
> 当前下一步：当前路线图没有未完成任务；后续缺陷回到对应任务证据排查，新范围另建路线图

任务状态、执行顺序、TDD、生产同路径、失败矩阵、完成定义、安全、资源清理和提交规则统一见
根目录 `CLAUDE.md`，本文件不复制长期规则。

`docs/development-roadmap.md` 是已经完成的 V1 历史台账，冻结 SHA-256 为
`9fd738cf7ecc8d44d4e59eaf502ba524cc4a5b345031772e73710567555eec94`。V2 不回写 V1；只有排查
历史决策或旧验收证据时才读取它。

## 1. V2 范围

V2 只交付两条增量链路：

1. 工具与 MCP：让通用 AI 会话和数字员工都能通过 Deep Agents 调用明确授权的 MCP 工具；平台
   托管 MCP 把现有业务 HTTP API 统一包装成 MCP，外部 MCP 直接接入同一目录和运行时；业务工具集
   聚合多个 MCP 来源，但最终权限始终落到稳定的单项能力 ID。
2. RAGFlow 性能：以当前 `v0.26.4` 为上游基线，复核本机 `ragflow-deploy` 中基于 `v0.26.1`
   的写入、删除和读取优化，按基准移植仍有效的补丁；代码进入私有 RAGFlow 镜像仓库与版本化分支，
   `common-agent` 再把 submodule 切到该私有提交。

V2 不包含工具/MCP 市场、付费内置工具、用户名密码代登录、OAuth、任意本机 stdio MCP、匿名公开
MCP 入口、多模型供应商扩张，也不触发远程部署。

## 2. 前期审计执行结果

### 2.1 `bjx/hug-ai` 工具链

审计基线：`develop@f66d2f1e957a11bb5cac1b1b0b0eea8c613ba502`。

| 主题 | 已确认实现 | V2 采用方式 |
| --- | --- | --- |
| 托管 MCP | MCP 级 `base_url/auth`，能力级 method/path/schema/参数位置/响应路径 | 复用分层思路，改成租户隔离、稳定 ID 和加密凭据 |
| OpenAPI | OpenAPI 3 JSON/YAML、预览选择、局部 `$ref`、批量事务导入 | 采用；拒绝外部引用，并补文件、深度、数量和循环上限 |
| 外部 MCP | Streamable HTTP `tools/list`、`tools/call`，按来源物化工具目录 | V2 首期只接 Streamable HTTP；同步不直接改员工权限 |
| 业务工具集 | 一个工具集关联多个托管/外部 MCP 来源 | 采用；工具集只负责分组和一次性展开，不是运行时继承权限 |
| 员工授权 | 保存当前叶子工具名，新增能力不会自动进入既有员工 | 保留“新增不自动授权”语义，但改用能力 UUID 关联表，不用可变名称 JSON |
| 通用工具 | `GENERAL_TOOLS` 自动注入所有会话 | 不采用；内置、托管、外部工具都必须显式授权 |
| 托管 HTTP 鉴权 | none、Bearer、自定义 Header、公司专用账密登录 | 只保留前三种；账密代登录及公司专用加密算法不进入 common-agent |
| 模型流式兼容 | `streaming_breaks_tool_calls` 标记，工具调用时自动非流式 | 采用能力标记与降级机制；只按复现证据登记具体模型 |
| 内置工具 | 多种搜索、代码、文件、语音和图像工具 | 不照搬；首个只提供零费用、无外部依赖的“当前时间”工具 |

需要规避的参考实现问题：敏感 Header/Token 不能以可回显 JSON 明文保存；平台不得自动给所有会话
扩权；远端工具名称不能充当权限主键；业务内网 HTTP 与外部 MCP 都必须有明确出站策略、超时、
响应上限、重定向和 DNS/地址校验。

### 2.2 `ragflow-deploy` 与 RAGFlow `v0.26.4`

旧改动基线：`hugai-main@01330b61f`，上游起点 `v0.26.1@a3e3bdd38`。当前 common-agent 基线：
`v0.26.4@cb93883f3f8c975eecb2fed81210effeb3bdb06f`。

| 旧改动 | `v0.26.4` 现状 | V2 决策 |
| --- | --- | --- |
| 删除文档归属定向查询 | 仍会为少量 ID 物化整个知识库文档集合 | 需要移植并补当前版本测试/基准 |
| 文档列表独立计数 | 仍对带展示 JOIN 的查询执行 `count()` | 需要移植 |
| 分页延迟 JOIN | 仍先 JOIN 全量结果再排序分页 | 需要移植 |
| embedding 并发与 chunk 构建解耦 | `embed_limiter` 仍复用 chunk 并发值 | 引入独立配置，具体默认值由 common-agent 资源基准决定 |
| Tika 首次启动串行化 | `.doc` 解析仍直接并发触发 python-tika 懒启动 | 需要移植并适配当前 parser |
| 画像批量写入接口 | 上游没有等价接口，但旧路由和 DTO 带 HugAI 画像语义 | 不原样移植；按 common-agent 写入场景设计通用批量边界 |
| ES refresh 开关 | 上游写入固定 `wait_for`、删除固定 `true` | 不采用旧全局开关；只允许具体批量操作显式选择并验证一致性 |
| 根/知识库目录 TTL 缓存 | 根目录查询仍含 `parent_id = id`，但 `v0.26.4` 已增加目录去重逻辑 | 先用批量写基准确认，再在服务层设计可失效缓存，不能覆盖去重修复 |
| 知识图谱参数改动 | 旧分支已自行 revert | 不进入 V2 |

上述“需要移植”表示问题在源码层仍存在，不代表旧补丁可以直接 cherry-pick；每项都要基于
`v0.26.4` 重新写 RED、适配当前代码并用隔离数据验证语义和性能。

## 3. 任务总表

### 3.1 基线

| ID | 任务 | 依赖 | 状态 |
| --- | --- | --- | --- |
| V2-00 | 冻结 V1，新建 V2，集中长期规则并同步产品/架构基线 | — | ✅ 已完成 |

### 3.2 工具与 MCP

| ID | 任务 | 依赖 | 状态 |
| --- | --- | --- | --- |
| T2-01 | 工具/MCP 领域、API/事件契约、租户数据模型与迁移 | V2-00 | ✅ 已完成 |
| T2-02 | MCP 凭据加密、脱敏和出站访问安全底座 | T2-01 | ✅ 已完成 |
| T2-03 | 平台 MCP 运行时与“当前时间”内置工具纵向闭环 | T2-02 | ✅ 已完成 |
| T2-04 | 托管 HTTP MCP 的手工配置、发现、调用和管理页 | T2-03 | ✅ 已完成 |
| T2-05 | OpenAPI 3 文件预览、选择、编辑与原子批量导入 | T2-04 | ✅ 已完成 |
| T2-06 | 外部 MCP 来源、业务工具集多来源聚合与同步 | T2-05 | ✅ 已完成 |
| T2-07 | 数字员工和通用会话的精确能力授权与工具交互 UI | T2-06 | ✅ 已完成 |
| T2-08 | 工具调用流式兼容模型标记与自动非流式降级 | T2-07 | ✅ 已完成 |
| T2-09 | 工具链失败、安全、并发、恢复与生产同路径总验收 | T2-08 | ✅ 已完成 |

### 3.3 RAGFlow 私有补丁与性能

| ID | 任务 | 依赖 | 状态 |
| --- | --- | --- | --- |
| R2-01 | 建立 `v0.26.4` 写入、删除、列表和检索可复现性能基线 | V2-00 | ✅ 已完成 |
| R2-02 | 创建私有 RAGFlow 镜像仓库、上游 remote 和版本化补丁分支 | R2-01 | ✅ 已完成 |
| R2-03 | 移植删除定向校验、独立计数和延迟 JOIN 分页 | R2-02 | ✅ 已完成 |
| R2-04 | 重做批量写入、独立 embedding 并发、Tika 启动与必要目录缓存 | R2-03 | ✅ 已完成 |
| R2-05 | 评估并优化语义检索、文档/切片读取和大结果边界 | R2-04 | ✅ 已完成 |
| R2-06 | 私有补丁集的正确性、性能、升级冲突和安全回归 | R2-05 | ✅ 已完成 |
| R2-07 | 推送私有仓库并把 common-agent submodule/镜像/脚本切到 fork 提交 | R2-06 | ✅ 已完成 |
| R2-08 | 真实知识链、备份恢复、资源与全新递归克隆验收 | R2-07 | ✅ 已完成 |
| R2-09 | 平台工作区与 RAGFlow 技术租户 1:1 隔离及存量默认工作区迁移 | R2-08 | ✅ 已完成 |

### 3.4 V2 收口

| ID | 任务 | 依赖 | 状态 |
| --- | --- | --- | --- |
| Q2-01 | 工具链与私有 RAGFlow 的全量回归、安全复审和 V2 最终验收 | T2-09,R2-08 | ✅ 已完成 |

## 4. 任务说明

### T2-01 ～ T2-03：先跑通唯一工具出口

- 建立租户级 MCP 来源、工具能力、工具集、来源关联、员工能力授权和会话能力授权；所有授权引用稳定
  UUID，远端名称、显示名和集合关系都不能直接成为权限依据。
- 员工选择整个工具集时，只把保存当时的叶子能力展开为授权记录；集合或 MCP 后续新增能力只进入
  可选目录，不修改既有员工或会话。
- 工作流工具迁入同一平台能力解析边界；Deep Agents 最终仍接收 LangChain `BaseTool`，但该转换
  只存在 MCP 适配层，平台领域和会话事件不暴露 SDK 类型。
- 首个内置能力固定为“当前时间”：不调用收费 API、不读本机文件、不执行代码，也不自动授权。
  分别从通用 AI 会话和数字员工会话显式选择后调用，证明 MCP `tools/list`、`tools/call`、模型工具
  调用、持久事件、审计、刷新恢复和最终回复完整闭环。

### T2-02：凭据与网络边界

- MCP Bearer Token 和自定义 Header 值使用独立平台主密钥加密落库，只返回掩码；更新时可保留未改
  的密文，日志、异常、审计、OpenAPI、前端缓存、模型输入和工具结果都不能出现明文。
- V2 不定义用户名/密码登录 DTO、数据库字段或前端选项；未来若确有通用认证编排需求，另起版本设计。
- 托管 HTTP 与外部 MCP 共用可审计出站策略：固定 scheme/origin、主机或 CIDR 许可、DNS 重解析、
  metadata/loopback 特例、重定向、代理、连接/调用超时、响应大小和并发上限；业务内网地址通过明确
  配置放行，不能为了防 SSRF 一刀切禁用合法内网，也不能让普通输入任意探测网络。

### T2-04 ～ T2-06：托管、导入与聚合

- 托管 MCP 在 MCP 级配置业务 `base_url` 和认证，在能力级配置 method、path、描述、输入 Schema、
  path/query/header/cookie/body 参数位置、超时和可选响应提取；运行时保护认证 Header、Host 和固定源。
- OpenAPI 只接受受限 OpenAPI 3 JSON/YAML。先预览规范化结果，用户可选择和补充描述，再以单事务
  导入；冲突、非法引用或任一选中能力失败时不留下半批数据。
- 业务工具集可关联多个平台托管或外部 MCP 来源。注册不联网冒充成功，显式刷新逐来源发现；远端
  能力消失或 Schema 漂移时保留稳定目录事实并标记不可用，不删除授权历史或静默改指其他能力。

### T2-07 ～ T2-09：授权、模型兼容与总验收

- 数字员工编辑页支持多个工具集和单项能力选择；通用 AI 在创建/继续会话时保存本会话精确能力
  列表。两者默认无工具，Viewer 只读，后端每次调用再次校验租户、授权、来源和能力启用状态。
- 会话持久事件增加工具开始、完成、失败状态，使用稳定 `tool_call_id` 串联；前端展示能力名称和
  安全状态，不展示认证信息或默认回显完整请求/响应正文。外部副作用结果不确定时不自动重放。
- 建立平台维护的模型工具流兼容记录。对已复现“只有首个 chunk 带工具名/ID”的模型，在绑定工具
  时关闭供应商流式调用并一次性取得完整工具调用；平台对浏览器的 SSE 通道仍保留，普通纯文本模型
  流不受影响。当前候选 `deepseek-v4-pro` 必须先以百炼真实 Trace 复现再登记。

### R2-01 ～ R2-06：基准驱动的私有补丁

- 基准覆盖小数据正确性和大数据退化曲线，分别记录 API 延迟、SQL 形态/扫描行、RDS 或本机 MySQL、
  RAGFlow API/Worker、Elasticsearch 与资源峰值；已知 76 万文档、81.6 万 file 行证据作为目标工作量
  参考，实际本机分层规模与生成方法写入执行记录。
- 私有仓库从官方 `v0.26.4` 精确提交建立，保留只读 `upstream` remote；补丁分支和版本号同时记录
  上游基线与 common-agent patch revision。旧 `ragflow-deploy` 只作参考，不直接成为 submodule。
- 查询补丁先移植通用且已确认仍缺失的三项；写入补丁去除 `HugAI` 路由语义，ES refresh 改为每次
  批量操作的显式策略，验证写后读取、删除后不可见和异常恢复；并发默认值只按 32 GiB 正式栈实测。
- 语义检索没有可直接移植的旧补丁，先从真实检索、文档/切片读取和大结果响应定位瓶颈；没有可复现
  退化就记录“不改”，禁止为了凑补丁修改核心搜索算法。

### R2-07 ～ R2-08：让另一台电脑可复现

- 私有 RAGFlow 远端包含补丁分支和 common-agent 锁定提交；`.gitmodules`、版本/上游基线文件、
  完整性检查、镜像标签、Compose 与安全扫描都识别 fork revision，不再要求 origin 必须是官方仓库。
- 从新的空目录执行带 submodule 的递归克隆，证明具备 GitHub 私有仓库权限时能取得完全相同源码；
  没有权限时给出明确配置错误，不能静默退回官方 RAGFlow。
- 用私有镜像完成真实创建知识库、批量写入/解析、列表、检索、删除、员工引用回答、备份和空环境
  恢复；保留官方上游基线和逐补丁回滚路径。

## 5. 执行记录

### V2-00 冻结 V1，新建 V2，集中长期规则并同步基线

- 状态：✅ 已完成
- 日期：2026-07-22
- 输入核对：完整读取项目规则与产品/工程/前后端/设计基线；V1 冻结前 SHA-256 为
  `9fd738cf7ecc8d44d4e59eaf502ba524cc4a5b345031772e73710567555eec94`。
- 参考审计：完成 `bjx/hug-ai` 工具/MCP、精确授权和模型流式兼容实现审计；完成
  `bjx/ragflow-deploy` 自 `v0.26.1` 起的提交链与 common-agent `v0.26.4` 逐项对照。
- 文档结果：新建本文件；`CLAUDE.md` 改为必读 V2 并集中状态、完成、安全、资源与第三方规则；
  产品范围、工程结构、后端、前端和 README 同步 V2 目标，不在其他文档建立进度台账。
- 校验：`git diff --check` 通过；全部必读基线存在；冲突措辞扫描无命中；V1 定向 diff 为空，
  冻结文件 SHA-256 仍为
  `9fd738cf7ecc8d44d4e59eaf502ba524cc4a5b345031772e73710567555eec94`。
- 真实边界：本任务只建立 V2 计划与规则，没有实现工具/MCP、创建私有 RAGFlow 仓库、修改
  submodule、构建镜像或部署服务。
- 清理与遗留：未启动服务、容器或浏览器，无临时运行资源；下一任务为 T2-01。
- 提交：本任务提交（见 Git 历史）。

后续任务完成时，只在本节之后追加对应 ID 的实际结果，不把长期执行规则复制回来。

### T2-01 工具/MCP 领域、API/事件契约、租户数据模型与迁移

- 状态：✅ 已完成
- 日期：2026-07-22
- RED：新增工具领域、授权展开、工具调用安全契约、工具持久事件、正式 HTTP 和迁移断言；首次运行因
  `common_agent.tools`、工具仓储端口和 `ToolCallEvent` 尚不存在按预期失败。随后分别补了端点查询串
  敏感值、工具授权审计动作和前端审计解析 RED，均先观察到目标失败再实现。
- 领域与权限：新建平台自有 `tools/`，定义平台/托管 HTTP/外部 MCP 来源、能力状态、规范化
  JSON Schema fingerprint、业务工具集、员工/通用会话精确授权、调用请求/结果和稳定错误码；参数和
  结果从 `repr` 排除，来源 URL 拒绝用户信息、查询串和片段。实现不复制 HugAI 的可变工具名权限、
  明文认证 JSON 或全局自动授权。
- 数据与 API：Alembic `20260722_0023` 新增 8 张租户复合外键表，集合选择快照与最终授权分离，
  凭据字段明确不进入本迁移。新增只读工具目录以及员工/通用会话授权读写契约；父集合只在显式保存
  时解析当前 `ready + active` 叶子，来源发现或新增能力不会改写既有授权。员工会话拒绝会话级授权，
  继续只从员工授权取得能力。
- 事件与审计：会话事件契约升级为 `schema_version=2`，增加
  `assistant.tool.started/completed/failed`，只持久化稳定 `tool_call_id`、能力 ID/名称和失败错误码，
  不保存调用参数、结果或凭据；前端 SSE 边界可安全接收但本任务不提前实现工具交互 UI。员工/会话
  授权写入使用 `tool.grants.updated` 元数据审计动作。
- 正式验证：项目专属 MySQL 8.4.10 上完成空库升级、重启恢复、租户隔离、集合展开、员工和通用
  会话正式 Uvicorn API、授权后新增危险能力不自动扩权、未知/跨租户/员工会话授权关闭失败、持久
  工具事件重建与 Alembic 无漂移验证。
- 门禁：后端全量 `783 passed, 13 skipped`（跳过项均为本任务未启用且未修改的真实 RAGFlow/百炼/
  Deep Agents 验收）；前端全量 `142 passed`；Ruff、Mypy、ESLint、TypeScript typecheck、生产构建、
  包体预算、OpenAPI/事件 Schema/生成 DTO 漂移和 `git diff --check` 通过。
- 真实边界：本任务没有引入 MCP SDK、发起 MCP/业务 HTTP 网络调用、保存认证值、建立管理页面、调用
  真实 RAGFlow/百炼或部署远程服务；这些边界分别属于 T2-02 及后续任务。
- 清理与遗留：停止本轮启动的 `common-agent-platform-mysql`，保留项目稳定 Volume；无本轮
  Uvicorn、Worker、Vite 或浏览器残留。检测到的 `8681 app.main:app` 是其他项目既有进程，未处理。
  下一任务为 T2-02。
- 提交：本任务提交（见 Git 历史）。

### T2-02 MCP 凭据加密、脱敏和出站访问安全底座

- 状态：✅ 已完成
- 日期：2026-07-22
- RED：先新增凭据领域/服务、AES-GCM 适配器、密钥配置、凭据 HTTP、出站策略和安全 HTTP 客户端
  测试，分别确认模块、端口、配置和 OpenAPI 路径尚不存在的预期失败。随后用真实本地 HTTP 服务证明
  复用 `httpx.AsyncClient` 会把服务端设置的 Cookie 带到下一次工具调用，再改为逐次隔离客户端并
  保留共享并发闸门，回归确认环境 Cookie、代理和前次响应状态都不会串入工具请求。
- 凭据模型：只支持 `bearer` 与 `custom_headers`，更新使用显式 `keep/replace/clear`，不把掩码当
  密文保留哨兵。API 输入使用秘密类型，响应固定返回 `********`；领域对象、设置、加密信封和 HTTP
  响应的 `repr` 均排除敏感正文。自定义 Header 拒绝认证、代理、传输控制类保留头以及控制字符，
  Bearer 必须走独立类型；平台内置来源不可设置凭据。
- 加密与数据：新增独立的 AES-256-GCM 多密钥 keyring，写入只用 active key、读取支持旧 key；随机
  96-bit nonce，AAD 绑定格式版本、租户 UUID 和来源 UUID，跨租户或跨来源调换密文会统一解密失败。
  生产环境没有默认密钥并要求显式 `COMMON_AGENT_TOOL_CREDENTIAL_KEYS`；本地缺省值只用于开发。
  Alembic `20260722_0024` 新增独立凭据表，数据库只保存类型、key id、nonce、ciphertext 和非敏感
  Header 名，不存在 Token/Header 值、用户名或密码字段；`keep` 不重写密文或更新时间。
- 出站边界：托管 HTTP 与后续外部 MCP 复用固定 origin 策略，按精确 host、CIDR 和独立明文 HTTP
  host 白名单放行；每次建连重新解析 DNS，所有解析地址都必须通过策略。metadata/link-local、组播和
  未指定地址恒拒绝，私网必须 host 与 CIDR 双重放行，loopback 还需独立开关。安全传输校验后直连
  选定 IP，同时保留原 Host/TLS SNI；不修改进程全局 socket，不读取系统代理，不跟随重定向，限制
  连接/读取/总调用超时、响应体大小与共享并发数，并禁用连接复用以避免 DNS 校验被绕过。
- 参考取舍：没有复制 HugAI 的明文认证 JSON、`***` 掩码猜测式回填，也没有复制旧 RAGFlow 的
  `socket.getaddrinfo` 进程级 monkey patch；前者会混淆真实值和保留操作，后者会污染无关协程并有
  并发竞态。实现改为显式更新动作、租户绑定加密和 `httpcore` 连接后端内的逐连接地址校验。
- 正式验证：项目 MySQL 上完成迁移、无漂移、正式 Uvicorn 凭据 API、数据库明文缺失、固定掩码、
  `keep` 字节级不变、自定义 Header 加密、内置来源拒绝、未知/跨租户隐藏、元数据审计和幂等清除。
  真实本地 HTTP 服务覆盖代理环境变量无效、跨源拒绝、重定向拒绝、超限响应、超时、逐请求 DNS
  重解析和 Cookie 不串请求；Alembic 自动检查无待生成迁移。
- 门禁：后端全量 `818 passed, 13 skipped`（跳过项均为未启用且未修改的真实 RAGFlow/百炼/Deep
  Agents 验收）；前端全量 `143 passed`；Ruff、Mypy（182 个源文件）、ESLint、TypeScript
  typecheck、生产构建与包体预算、OpenAPI/生成 DTO 漂移、生产运维脚本、Secret 治理、
  `git diff --check` 均通过。V1 冻结 SHA-256 保持不变。
- 真实边界：本任务交付的是凭据和通用出站安全底座，尚未引入 MCP SDK、执行模型工具调用、配置
  业务 HTTP 能力、连接真实外部 MCP 或提供工具管理 UI；这些从 T2-03、T2-04、T2-06 和 T2-07
  依次实现。本轮网络验收使用真实 loopback TCP/HTTP 服务验证传输语义，不冒充外部目标验收。
- 清理与遗留：停止本轮项目 MySQL 并保留稳定 Volume；无本轮 Uvicorn、Worker、Vite 或浏览器残留。
  其他项目既有进程不处理。下一任务为 T2-03。
- 提交：本任务提交（见 Git 历史）。

### T2-03 平台 MCP 运行时与“当前时间”内置工具纵向闭环

- 状态：✅ 已完成
- 日期：2026-07-22
- RED：先新增平台 MCP 协议与运行时事件契约测试，确认 `adapters.mcp`、`tools/list/tools/call` 和
  `RuntimeEventEmitter.tool_started` 尚不存在；随后补官方 Deep Agents 实际工具调用与工作流 MCP
  出口测试，分别观察到缺少 MCP 运行时，以及取消 MCP 调用后工作流仍停在 `running` 的预期失败。
- 协议与目录：锁定官方稳定 `mcp>=1.28.1,<2`，平台内置 MCP 使用官方协议和进程内双端传输，不
  新建匿名 HTTP/stdio 入口。每个租户启动或创建时幂等物化稳定的平台来源和“当前时间”能力 UUID；
  目录可见但默认授权为空，定义漂移由平台种子修复且不会更新正常记录时间。当前时间只接受
  `-14:00` 到 `+14:00` 的 UTC offset，不访问网络、文件、代码执行或收费工具。
- 唯一出口：Deep Agents 仍只消费最后一跳 `BaseTool`，但工具闭包每次执行前重新校验当前租户、
  员工/会话精确授权、来源和能力状态，再经过 MCP `tools/call`。既有工作流工具也迁入动态 MCP
  `tools/list/tools/call`，不再从 LangChain Tool 直接调用 `WorkflowService`；取消时使用内部调用令牌
  只停止对应工作流，保留原成功、失败、审计、租户隔离和取消语义。
- 会话与安全事件：员工会话从员工授权快照取能力，通用会话从会话授权快照取能力；新建通用会话
  在落库前固定为空，不把“目标尚不存在”误判为服务故障。模型工具调用转换为稳定
  `assistant.tool.started/completed/failed`，供应商 call ID 按助手消息命名空间生成平台 UUID；停止、
  协议中断和未知结果使用稳定错误码，事件和 `tool.called` 审计都不保存参数、结果或凭据。
- 正式验证：在正式 loopback Uvicorn、独立持久 Worker、MySQL 8.4、官方 Deep Agents、真实百炼
  Demo 模型与官方 MCP 协议上，员工和通用会话分别经正式授权 API 调用“当前时间”，均收到工具开始、
  完成和最终回复；服务完全重启后从事件日志重放出相同序号、类型与 `tool_call_id`。审计查询确认
  started/succeeded 元数据完整且无请求参数或结果正文。另以真实协议验证平台和工作流
  `tools/list/tools/call`、逐次撤权拒绝、错误、取消与双目标授权。
- 门禁：后端全量 `833 passed, 14 skipped`，并单独显式启用本任务真实百炼用例 `1 passed`；Ruff、
  Mypy（191 个源文件）通过。前端 `143 passed`，ESLint、TypeScript typecheck、生产构建和包体预算
  通过；OpenAPI/事件 Schema/生成 DTO 漂移、Secret/安全扫描、V1 冻结哈希和 `git diff --check`
  通过；无头 Chromium 核心聊天 E2E `1 passed`。
- 真实边界：本任务完成平台内置与既有工作流的 MCP 运行出口，但不提前实现托管业务 HTTP、OpenAPI
  导入、外部 Streamable HTTP MCP、工具管理/授权交互 UI 或模型流式兼容表；它们分别属于
  T2-04～T2-08。当前平台 MCP 只在服务内部暴露协议端点，不对匿名网络开放，也未触发远程部署。
- 清理与遗留：真实测试创建的员工和两类会话已删除；E2E 的 API、Worker、Vite、无头浏览器和测试
  数据由脚本清理；停止本轮 `common-agent-platform-mysql` 并保留稳定 Volume。其他项目进程未处理。
  下一任务为 T2-04。
- 提交：本任务提交（见 Git 历史）。

### T2-04 托管 HTTP MCP 的手工配置、发现、调用和管理页

- 状态：✅ 已完成
- 日期：2026-07-22
- RED：先新增 Base URL、能力 HTTP 映射、请求构建、响应提取、服务编排、官方 MCP 适配和运行时
  目录测试，确认托管 HTTP 领域、仓储和执行器尚不存在；随后补非法 JSON Schema、数据库并发唯一
  冲突、来源不存在时的错误优先级、正式 HTTP 纵向链路和管理页测试，均先观察目标失败再实现。
- 领域与数据：托管来源固定 `scheme/origin/base path`，能力定义 method/path、描述、输入 JSON
  Schema、path/query/header/cookie/body 参数映射、超时和可选 JSON Pointer 响应提取；拒绝覆盖
  Host、认证和传输控制类 Header。Alembic `20260722_0025` 新增租户复合外键的来源与能力定义表，
  稳定能力 UUID 与可变远端名称分离，并将并发写入唯一冲突统一映射为领域错误。
- 执行与安全：托管能力通过官方 MCP SDK 暴露 `tools/list/tools/call`，运行时使用已加密的 Bearer 或
  自定义 Header 凭据和 T2-02 安全出站客户端；固定源、逐次 DNS/地址校验、无代理/重定向、超时、
  响应大小和共享并发闸门保持生效。Deep Agents 工具目录支持托管来源，并在每次实际调用前再次
  校验租户精确授权和能力可用状态；撤权后旧工具闭包不能继续调用。
- API 与管理页：新增托管来源、凭据、手工能力、发现和测试调用 API；Owner 可在 `/tools` 创建、
  编辑和删除来源/能力，配置 Bearer 或自定义 Header，发现当前工具并在明确警告后测试调用，Viewer
  全程只读。前端对全部工具响应使用严格 Zod 边界，并补审计动作与中文展示。
- 参考取舍：只采用 HugAI 的 MCP 级 Base URL、能力级 HTTP 映射思路，没有复制任意 JSON 拼装、
  明文认证、公司专用账密登录或可变名称权限；请求由结构化参数位置生成，认证值不进入模型输入、
  API 回显、测试结果、日志或审计。
- 正式验证：项目 MySQL 8.4、正式 Uvicorn、真实 loopback 业务 HTTP 服务、加密凭据和官方 MCP
  协议完成创建来源/能力、发现、调用、响应提取、撤权拒绝、禁用和删除纵向验收；生产构建预览下的
  Playwright 管理页完成来源、凭据、能力、发现、测试调用和删除全流程。
- 门禁：后端全量 `856 passed, 14 skipped`，Ruff、Mypy（360 个源文件）通过；前端全量 30 个文件
  `150 passed`，ESLint、TypeScript typecheck、生产构建和七路由包体预算通过，其中 `/tools` 首屏
  `1,308,861` bytes、最大 chunk `178,410` bytes。OpenAPI/生成 DTO 漂移、CI/E2E 资源契约、Secret
  与安全扫描、正式 MySQL 集成、Playwright `managed-tools`、V1 冻结哈希和 `git diff --check` 通过。
- 真实边界：本任务只支持手工配置托管 HTTP 能力；OpenAPI 导入、外部 MCP、业务工具集、员工/通用
  会话授权管理 UI 和模型流兼容降级仍分别属于 T2-05～T2-08。运行时目录已具备托管工具解析能力，
  但本任务不冒充后续真实模型会话和完整授权交互验收，也未触发远程部署。
- 清理与遗留：正式 E2E 创建的数据、临时 API、Vite 预览和无头浏览器已清理；为不中断后续任务，
  保留项目稳定 MySQL 容器与 Volume，T2-05 继续复用。下一任务为 T2-05。
- 提交：本任务提交（见 Git 历史）。

### T2-05 OpenAPI 3 文件预览、选择、编辑与原子批量导入

- 状态：✅ 已完成
- 日期：2026-07-22
- RED：先新增受限 JSON/YAML 解析、本地 `$ref`、参数/请求体映射、预览、批量服务与正式 HTTP 测试，
  确认 OpenAPI 适配器、端口和批量服务尚不存在；随后补嵌套参数说明、上传文件关闭、超限读取、空
  说明预览响应及页面选择/编辑测试，均先暴露目标缺口再实现。测试还发现并修复了 `tools` 包初始化
  的冷启动循环依赖，以及预览加载状态与导入按钮交互的时序边界。
- 解析边界：新增独立 `adapters/openapi/`，支持 OpenAPI 3.0/3.1 的 UTF-8 JSON、YAML 和本地 JSON
  Pointer 引用；拒绝重复键、YAML 别名、外部/缺失/循环引用、重复 `operationId` 或规范化名称、受保护
  Header 参数、非 JSON 对象请求体和不可稳定映射的复杂参数。文件限制 5 MiB，并对文档深度、节点数、
  引用深度和最多 200 项操作设硬上限；缺失能力/嵌套参数说明作为可编辑问题返回，不静默补伪说明。
- 原子导入：预览先验证来源但不写库，并返回已存在远端名称供页面默认取消选择；最终导入对选中草稿
  再做严格递归说明、批内/既有名称和全部领域校验，能力目录与 HTTP 配置在一个仓储批次、一个数据库
  事务内写入，任何无效项或并发唯一冲突都整批失败，不留下半批能力。成功写入固定元数据审计动作，
  上传文件在成功、解析失败和超限路径均关闭。
- 管理页：`/tools` 新增 OpenAPI 文件上传与预览弹窗，展示操作、冲突和缺失说明；Owner/Editor 可
  逐项勾选并编辑 MCP 名称、显示名、说明、输入 Schema、参数映射、响应 Pointer 和超时后一次导入，
  Viewer 全部写入口禁用。浏览器只做扩展名/5 MiB 预检和严格 Zod 响应校验，不自行解析规范或访问
  业务接口。
- 参考取舍：采用 HugAI 的预览、选择和本地引用思路，但没有复制其无预解析 YAML 别名上限、无结构
  深度/节点上限、重复工具名静默加后缀及逐项写入风险；解析器与领域服务重新按 common-agent 的租户、
  稳定 ID、失败关闭和原子事务边界实现。
- 正式验证：项目 MySQL、正式 Uvicorn API 验证预览不落库、非法整批无残留、只导入选中项、批内/
  既有冲突全回滚和修正后成功；生产构建 preview 下的 Playwright `managed-tools` 上传真实 OpenAPI，
  补全缺失参数说明与响应 Pointer，取得 201 后继续完成官方 MCP 发现、Bearer 认证的真实业务 HTTP
  调用、响应提取和资源删除，`1 passed`。
- 门禁：后端全量 `877 passed, 14 skipped`，Ruff、Mypy（366 个源文件）通过；前端全量 30 个文件
  `152 passed`，ESLint、TypeScript typecheck、生产构建和七路由包体预算通过，其中 `/tools` 首屏
  `1,316,447` bytes、最大 chunk `178,410` bytes。OpenAPI/生成 DTO 漂移、CI/E2E 资源契约、Secret、
  安全入口、正式 MySQL 集成、V1 冻结哈希和 `git diff --check` 通过。
- 真实边界：本任务不接外部 MCP、不建立业务工具集、不改变员工/会话授权，也不调用真实模型或远程
  部署；外部来源同步、能力漂移和多来源集合属于 T2-06。
- 清理与遗留：正式 E2E 创建的数据、API、Worker、Vite、无头浏览器和监听端口已清理；E2E 轻量档
  同时停止项目 MySQL/Colima，稳定 Volume 保留，后续正式测试按需精确启动。下一任务为 T2-06。
- 提交：本任务提交（见 Git 历史）。

### T2-06 外部 MCP 来源、业务工具集多来源聚合与同步

- 状态：✅ 已完成
- 日期：2026-07-22
- RED：先新增外部 MCP 来源领域、同步对账、应用服务、官方协议适配、持久化和正式 HTTP 测试，确认
  对应端口与实现尚不存在；再新增业务工具集 CRUD、多来源关联、运行时目录、前端严格 DTO、管理页和
  Playwright RED。回归中进一步发现集合删除会触发关联级联并误删员工/会话授权，补真实 MySQL RED
  后改成显式清理集合选择与来源关联，保留已经展开的精确能力授权。最终审查还发现来源端点变化会把
  旧凭据带到新目标，新增托管/外部来源 RED 后改为在来源更新事务内清除原密文，仅元数据编辑仍保留。
- 外部 MCP：注册与编辑只保存离线配置，不自动连接远端；用户显式同步时使用官方 Streamable HTTP
  MCP 客户端完成初始化、分页 `tools/list` 和目录对账，单来源最多 500 项。稳定能力 UUID 与远端名称
  分离；首次 Schema 漂移先隔离为不可用，下一次显式取得完全相同定义才重新启用，远端删除则保留
  目录事实并标记不可用。重复名称、非对象/非法 JSON Schema、异常分页和超限目录均失败关闭。
- 调用与安全：外部 `tools/call` 复用 T2-02 固定 origin、逐连接 DNS 校验、无系统代理/重定向、
  连接与读取超时、响应大小和共享并发闸门，并使用租户/来源绑定的加密 Bearer 或自定义 Header；每次
  模型工具闭包调用前重新校验租户、精确授权、来源、远端名称、Schema fingerprint 和当前可用状态。
  同步失败只把来源标记为失败并保留旧目录，不把网络或协议故障冒充空目录。
  托管或外部来源端点变化会原子清除旧鉴权并在页面明确提示重新配置，避免旧系统 Token 外发给新域名。
- 业务工具集：新增多来源 CRUD 和统一工具目录；同一集合可关联平台托管 HTTP 和外部 MCP 来源，
  可用状态由当前来源/能力派生。集合仍只是选择入口，员工/会话保存时展开当时可用的能力 ID；后续
  来源新增、漂移、移除或集合修改都不会静默改写已有授权。删除被集合引用的来源会明确拒绝，删除
  集合会清理集合选择但保留已展开能力授权。
- 管理页：`/tools` 新增外部 MCP 和业务工具集区块，支持来源离线创建/编辑/删除、共享鉴权弹窗、
  显式同步、Schema 漂移告警、能力测试调用，以及跨来源创建/编辑集合；Viewer 全程只读。所有响应
  都经严格 Zod 校验，页面不会保存或回显凭据正文，也不会在创建来源时隐式访问远端。
- 参考取舍：采用 HugAI 的 Streamable HTTP 发现、按来源物化目录和多 MCP 工具集思路，但没有复制
  明文认证、自动发现即授权或用可变名称作为权限。协议生命周期使用官方 MCP SDK，目录对账、失败
  关闭、稳定 ID、租户事务和外发安全按 common-agent 现有架构重新实现。
- 正式验证：真实 FastMCP/Uvicorn Streamable HTTP 服务、正式 common-agent Uvicorn、项目 MySQL 和
  加密 Bearer 完成离线创建、显式同步、多来源集合、授权快照不扩张、Schema 漂移隔离/确认恢复、
  远端删除、真实 `tools/call`、引用删除保护与集合清理纵向集成，`1 passed`；生产 preview 下的
  Playwright `managed-tools` 同时完成既有托管 HTTP/OpenAPI 链路和真实外部 MCP/工具集页面链路，
  `2 passed`。
- 门禁：后端全量 `890 passed, 14 skipped`，Ruff、Mypy（376 个源文件）通过；前端全量 30 个文件
  `157 passed`，ESLint、TypeScript typecheck、生产构建和七路由包体预算通过，其中 `/tools` 首屏
  `1,329,444` bytes、最大 chunk `178,410` bytes。OpenAPI/生成 DTO 漂移、CI/E2E 资源契约、Secret、
  正式源码安全扫描、MySQL `20260722_0025 (head)`/无迁移漂移、V1 冻结哈希和 `git diff --check`
  均通过。
- 失败矩阵：覆盖无鉴权/错误鉴权、来源不可达和同步失败保留旧目录、Schema 漂移/移除/恢复、重复名、
  非法 Schema、分页与数量上限、超时/超限/连接释放、跨租户、逐次撤权、集合新增不扩权、被引用来源
  删除、集合删除后的授权保留及端点变化清除旧凭据。模型真实发起外部工具调用、工具事件页面交互、
  缺失 chunk 兼容和副作用重放策略分别由 T2-07～T2-09 验收，本任务不以管理页测试调用冒充模型闭环。
- 真实边界：本任务没有增加员工/通用会话授权编辑界面，没有改变模型供应商流式行为，也没有调用
  RAGFlow、创建私有仓库、修改 submodule 或部署远程服务。
- 清理与遗留：正式 E2E 的外部 MCP、业务 HTTP、API、Worker、Vite、浏览器和测试数据均由脚本清理；
  全量门禁临时复用的稳定开发栈在提交前精确停止，数据库 Volume 保留。下一任务为 T2-07。
- 提交：本任务提交（见 Git 历史）。

### T2-07 数字员工和通用会话的精确能力授权与工具交互 UI

- 状态：✅ 已完成
- 日期：2026-07-23
- RED：先新增首轮通用会话授权输入、同事务快照、员工覆盖拒绝和失败无残留测试，确认原首轮接口会先
  落会话再另行授权；再新增员工编辑、通用会话选择器、工具事件归并、刷新恢复和 Viewer 只读前端
  RED，分别暴露无授权入口、首轮竞态、工具事件不可见及不可用能力无法安全撤权的缺口。正式浏览器
  首轮还发现多选控件定位和弹层关闭时序问题，修正测试交互后用相同生产页面重跑通过。
- 原子授权：通用会话首轮接受工具集和单项能力的精确选择，先解析可用叶子，再把会话、集合选择、
  能力快照、用户/助手消息和生成任务写入同一个 MySQL 事务；未知集合、不可用能力或模型失败均不留
  半成品。员工会话只继承员工授权，首轮显式覆盖在 Schema 边界返回 422；新建员工默认无工具。
- 授权交互：复用一个严格类型的授权选择器；员工编辑页可选择多个业务工具集和单项能力并保存当时
  的叶子快照，通用会话侧栏在首轮原子提交，既有会话则显式保存。集合后续新增能力不会自动扩权；
  已授权能力漂移为不可用时仍可显示和撤销，但不能新授不可用能力。工具目录加载失败不阻断普通聊天，
  Viewer 可以查看目录和授权摘要但没有写入口。
- 工具事件：聊天状态按稳定 `tool_call_id` 归并持久的 started/completed/failed 事件，并用目录映射
  显示能力名称和安全状态；页面不展示调用参数、认证信息或完整结果正文。历史刷新使用同一消息事件
  重建逻辑，不依赖仅存内存的流式状态；员工聊天明确展示继承的授权能力数量。
- 正式验证：生产构建 preview、正式 Uvicorn、独立 Worker、项目 MySQL、真实百炼 Deep Agents 和
  平台 MCP“当前时间”能力下，Playwright 完成通用会话首轮精确授权、模型真实工具调用、开始/完成
  状态、最终回答及刷新恢复，并完成数字员工编辑授权与继承调用，`1 passed`。测试数据和运行资源由
  E2E 清理器精确回收。
- 门禁：后端全量 `894 passed, 14 skipped`，Ruff、Mypy（377 个源文件）通过；前端全量 30 个文件
  `163 passed`，ESLint、TypeScript typecheck、生产构建和七路由包体预算通过，其中 `/chat` 首屏
  `1,331,378` bytes、`/employees` `1,320,276` bytes、`/tools` `1,330,599` bytes、最大 chunk
  `178,410` bytes。OpenAPI/生成 DTO 漂移、架构、CI/E2E 资源、Secret、正式源码安全扫描、V1 冻结
  哈希和 `git diff --check` 均通过。
- 失败矩阵：覆盖员工首轮越权、未知/不可用能力、授权目标不存在、Viewer 写入、目录加载失败、集合
  新增不扩权、能力漂移后的显示/撤权、工具 started/completed/failed 乱序归并和刷新恢复；运行时继续
  每次校验租户、精确授权、来源和能力状态。供应商缺失 chunk 兼容和副作用不确定时的重放边界仍按
  计划分别由 T2-08、T2-09 验收。
- 真实边界：本任务没有登记未经复现的模型兼容标记，没有改变百炼供应商流式策略，没有接触 RAGFlow
  私有补丁、submodule、GitHub 私有仓库或远程部署。业务工具集仍只聚合平台托管 HTTP 与外部 MCP；
  免费内置能力通过单项授权进入员工或通用会话。
- 清理与遗留：正式 E2E 创建的会话与员工、API、Worker、Vite、浏览器和临时产物已清理；项目 MySQL
  与 Colima 已停止，稳定 Volume 保留。下一任务为 T2-08。
- 提交：本任务提交（见 Git 历史）。

### T2-08 工具调用流式兼容模型标记与自动非流式降级

- 状态：✅ 已完成
- 日期：2026-07-23
- RED 与参考取舍：先为模型兼容事实、租户模型只读派生字段、会话/工作流运行时透传、解析器双变体
  复用和“只有标记模型且本轮存在工具才禁流”建立失败测试；再用真实百炼 Trace 复现
  `deepseek-v4-pro` 的分块关联问题。审计 HugAI 后只采用按模型标识登记兼容能力的思路，没有复制其
  同步数据库读取、进程全局缓存或用户可编辑开关。照搬 `disable_streaming="tool_calling"` 的首次实现
  还暴露了构造器固定 `streaming=True` 会覆盖公开降级的问题，测试先收到错误的异步流对象后再修正。
- 平台兼容目录：Alembic `20260723_0026` 新增无 `tenant_id` 的
  `model_tool_streaming_capabilities`，以 `provider + model_identifier` 为主键，并保存布尔能力、
  `evidence_revision`、实测时间和更新时间；迁移只登记已有真实证据的
  `bailian/deepseek-v4-pro`。租户 `model_configurations` 不保存该字段，创建/编辑 DTO 明确拒绝用户写入，
  列表、详情和运行目标每次联表取得只读派生事实；未登记模型默认正常流式，数据库故障不靠缓存猜测。
- 降级实现：模型解析器按“模型标识 + 工具流兼容模式”分别复用并统一释放正式百炼适配器；
  Deep Agents 先解析本轮精确授权工具，只有兼容标记为真且工具非空时才通过 LangChain 公开
  `disable_streaming=tool_calling` 取得完整工具调用。`ChatOpenAI` 构造器不再固定流式，平台普通文本
  适配入口显式传 `stream=True`，因此纯文本、无工具及未登记模型继续流式，浏览器 SSE 和持久工具事件
  不变。通用会话、员工会话、回复重试和工作流 AI 员工目标均从当前模型目录透传同一事实。
- 真实 Trace 与正式链路：真实百炼流式请求观察到 6 个同索引 tool-call chunk，仅首块包含调用 ID 和
  工具名，后续参数块缺少二者；兼容适配后一次取得带完整 ID、名称和参数的 `AIMessage`，定向测试
  `1 passed`。生产构建页面创建 `deepseek-v4-pro` 后自动显示“工具调用自动非流式”，再分别把它设为
  通用会话当前模型和员工默认模型，经正式 Axios/SSE、Uvicorn、独立 Worker、Deep Agents、真实百炼
  与平台 MCP 调用“当前时间”，两路工具开始/完成事件和最终回复完整，无头 Playwright `1 passed`。
- 门禁：后端全量 `902 passed, 15 skipped`，Ruff、Mypy（377 个源文件）和 Alembic 无漂移通过；
  前端全量 30 个文件 `163 passed`，ESLint、TypeScript typecheck、生产构建和七路由包体预算通过，
  其中 `/chat` 首屏 `1,331,410` bytes、`/model-configurations` `1,298,419` bytes、最大 chunk
  `178,410` bytes。OpenAPI/生成 DTO、CI/E2E 资源、ShellCheck、基础设施、Secret、正式源码安全扫描、
  V1 冻结哈希和 `git diff --check` 均通过。
- 失败矩阵：覆盖兼容标记类型错误、租户越权写标记、未登记默认值、平台表与租户表边界、迁移种子
  证据、标记/未标记 × 有/无工具四种解析组合、适配器缓存隔离和释放、缺失 ID/名称分块、完整非流式
  工具调用、普通文本强制流式、会话重试及工作流透传。工具副作用结果未知、并发限流和失败后的重放
  策略仍按计划由 T2-09 总验收。
- 真实边界：本任务只登记已复现的 `deepseek-v4-pro`，没有推测或批量标记其他模型；没有修改
  Deep Agents/LangChain/百炼第三方源码，没有改变租户模型凭据边界，也没有触碰 RAGFlow 私有补丁、
  submodule、GitHub 仓库或远程部署。
- 清理与遗留：两轮正式 E2E 创建的模型、员工、两类会话、认证状态、API、Worker、Vite、浏览器和
  成功产物均已精确清理，`18200/18280` 无监听残留。为连续执行 T2-09，保留项目专属 Colima、平台
  MySQL 与官方 RAGFlow 稳定容器/Volume；其他项目资源未处理。下一任务为 T2-09。
- 提交：本任务提交（见 Git 历史）。

### T2-09 工具链失败、安全、并发、恢复与生产同路径总验收

- 状态：✅ 已完成
- 日期：2026-07-23
- RED：先用故障注入证明托管 HTTP 在请求已发出后断流、响应 JSON/指针异常或关闭连接失败仍被错误
  标为可重试，外部 MCP 在 `tools/call` 后断流也无法区分握手前失败；再证明相同供应商
  `tool_call_id` 会重复执行、结果未知后同轮仍能继续外发，以及持久 Worker 重启会把已开始的副作用工具
  整轮重放。生产组装测试还确认独立 Worker 原先只注入平台内置 MCP，托管 HTTP 和外部 MCP 只存在于
  API 进程，并且两类出站客户端各自限流、不能共享总并发上限。
- 失败与重放收敛：出站层显式携带“请求可能已发送”事实；托管 HTTP 的发出后超时、断流、响应超限、
  重定向、非预期响应或释放失败，以及外部 MCP 的 `tools/call` 发出后连接/协议异常统一收敛为不可重试
  的 `tool_result_unknown`，握手前不可达仍保持可重试的来源失败，远端明确 `isError`/非 2xx 则保持明确
  执行失败。每个解析出的 LangChain 工具按供应商 `tool_call_id` 合并同轮重复调用；任一调用结果未知后
  对该能力本轮熔断，审计或结果序列化在副作用之后失败也按结果未知处理，不伪造成普通失败。
- 持久恢复与生产组装：会话事件代理可从持久 Journal 分页重建工具 started/completed/failed 证据；任务
  重试和进程启动恢复一旦发现本轮曾开始工具调用，就持久化助手失败和未决工具失败事件，不自动重放
  整轮副作用，未调用工具的普通生成仍沿用既有恢复。API 与独立 Worker 都正式组装托管 HTTP、外部 MCP、
  加密凭据和同一进程级共享 Semaphore，因此两类出站调用共同受一个总并发上限约束；Demo 路径不凭空
  注入真实外部依赖。
- 正式验证：生产构建 React 页面经正式 Axios/SSE、loopback Uvicorn、项目 MySQL、独立持久 Worker、
  Deep Agents、真实百炼 `deepseek-v4-pro` 和平台 MCP 完成通用会话与数字员工“当前时间”调用；同一
  Playwright 场景再创建带 Bearer 的托管 HTTP POST 能力，让真实业务服务在副作用落地后主动断开，页面
  收到 `tool_result_unknown` 且服务端计数严格为 1；随后由数字员工显式授权并调用独立 Streamable HTTP
  MCP，返回真实订单结果且服务端计数严格为 1。无头 Playwright `1 passed (40.0s)`，证明三类工具均走
  正式 Worker 而非 API 测试旁路。
- 门禁：后端全量 `915 passed, 15 skipped`，Ruff 与 Mypy（378 个源文件）通过；前端全量 30 个文件
  `163 passed`，ESLint、TypeScript typecheck、生产构建和七路由包体预算通过，其中 `/chat` 首屏
  `1,331,410` bytes、`/tools` `1,330,599` bytes、最大 chunk `178,410` bytes。OpenAPI/生成 DTO 漂移、
  CI/E2E 资源、全仓 ShellCheck、Secret、正式源码依赖/配置安全扫描、V1 冻结哈希和
  `git diff --check` 均通过。
- 失败矩阵：覆盖托管 HTTP 与外部 MCP 的握手前不可达、调用后断流/超时、明确远端失败、异常 JSON/
  JSON Pointer、响应超限、关闭失败、结果序列化/审计失败、重复 `tool_call_id`、结果未知后的同轮再次
  调用、持久 Journal 重建、Worker 重试与启动恢复、无工具普通恢复，以及托管/外部共享并发实测。既有
  T2-02～T2-08 测试继续覆盖跨租户/越权、集合新增不扩权、停用与 Schema 漂移、认证 Header 覆盖、
  SSRF/DNS/重定向、凭据脱敏、模型缺失 chunk、平台 SSE 顺序和刷新恢复。RAGFlow、OpenAPI 导入和
  工作流各自的专项失败项本任务未改动，继续由既有门禁及后续 R2/Q2 任务负责；任意 stdio MCP、OAuth、
  用户名密码代登录和付费内置工具不在 V2 产品范围。
- 真实边界：未修改或复制 Deep Agents、LangChain、MCP SDK、百炼及其他第三方源码；没有把测试提示词
  当作防重放保证，安全保证落在执行器、持久事件与任务恢复边界。没有修改 RAGFlow 私有补丁、submodule、
  GitHub 仓库或远程部署，下一阶段才进入 RAGFlow `v0.26.4` 性能基线。
- 清理与遗留：正式 E2E 创建的两类会话、员工、模型、两个 MCP 来源及其凭据/能力均已精确清理；API、
  Worker、Vite、业务 HTTP、外部 MCP 和 Chromium 均已停止，`18200/18280` 无监听、无 common-agent
  浏览器或运行中容器残留，三份已结束失败验收的日志/截图/trace 已删除。未删除项目持久 Volume，也未
  处理其他项目资源。下一任务为 R2-01。
- 提交：本任务提交（见 Git 历史）。

### R2-01 建立 RAGFlow `v0.26.4` 写入、删除、列表和检索性能基线

- 状态：✅ 已完成
- 日期：2026-07-23
- RED：先新增规模档位、延迟分位数、`EXPLAIN ANALYZE` 实际行数解析和上游提交绑定测试，确认基准
  模块不存在；再新增正式运行器契约，确认脚本不存在。首轮真实烟测还复现基准连接在 MySQL
  `REPEATABLE READ` 下误读 API 写入前快照，补回归后显式结束只读事务。扩到 250k 时官方单删稳定
  触发连接断开与 API OOM，又补测试要求只有“断连 + 容器 OOMKilled”才能作为已测上游边界，并让
  失败也写脱敏报告、精确清理和恢复服务，其他断连继续关闭失败。
- 可复现方法：`scripts/ragflow-v0264-baseline.sh` 同时校验 submodule 精确提交
  `cb93883f3f8c975eecb2fed81210effeb3bdb06f`、干净工作区、`v0.26.4` 版本端点、0600 Token 与
  百炼 embedding/rerank ready。第一层经官方 API、真实 Worker、Elasticsearch、MinIO 和百炼对 8 个
  隔离文本完成上传、解析、检索、单删与删除后不可见；第二层只为规模退化向独立知识库的
  `document/file/file2document` 分批写入 1k/10k/50k/100k/250k 合成目录行，再调用同一个官方列表和
  删除 API，并记录实际 SQL 计划。直接写库部分只生成规模，不冒充真实写入/检索链。
- 真实写入与检索：8 文档上传 `0.107s`、解析 `13.532s`、端到端 `13.639s`，吞吐
  `0.587 docs/s`；带 `qwen3-rerank` 的真实检索 p50 `0.523s`、p95 `0.877s`，唯一标记命中；小规模
  单删 `0.067s`，文档随后在列表和检索中均不可见。
- 退化曲线：1k/10k/50k/100k/250k 的第一页 p50 分别为
  `0.022/0.122/0.764/1.802/5.075s`，深分页 p50 为
  `0.022/0.132/0.854/1.992/5.526s`；单删前四档为
  `0.064/0.400/1.915/4.896s`。带展示 JOIN 的计数实际累计扫描工作按
  `9,001/90,001/450,001/900,001/2,250,001` 线性放大，删除归属查询也逐档物化全部
  `1k/10k/50k/100k/250k` 文档。250k 单删运行 `6.211s` 后服务端无响应并杀死 5GiB 上限的 RAGFlow
  API 进程，正式报告状态为 `completed_with_upstream_oom`；因此旧分支的定向删除、独立计数和延迟
  JOIN 三项在 `v0.26.4` 上均有直接移植依据，而不是仅凭旧代码推测。
- 资源：67 个后台采样中 VM 峰值 `9,251,270,656` bytes、Swap 为 0；RAGFlow API、MySQL、ES 峰值
  分别为 `5,230,196,425`、`1,650,341,183`、`1,721,208,144` bytes。250k OOM 被报告记录后，运行器
  精确重启 API 并重新验证版本与百炼模型；恢复后 API/MySQL/ES 均 `oom=false`、运行正常。
- 门禁：基准契约 `7 passed`；后端全量 `922 passed, 15 skipped`，Ruff 与 Mypy（381 个源文件）
  通过；前端全量 30 个文件 `163 passed`，ESLint、TypeScript typecheck、生产构建和七路由包体预算
  通过。全仓 ShellCheck、CI 基线契约、Secret、正式源码依赖/配置安全扫描、V1 冻结哈希和
  `git diff --check` 均通过。
- 失败矩阵与边界：覆盖错误/重复/逆序/超限规模参数、空延迟、缺失实际执行行数、错误上游提交、
  不安全 Token 文件、源码漂移、MySQL 旧快照、真实解析/检索/删除后可见性、API 断连、OOM、资源
  采样错误、清理失败和稳定栈恢复。已知 76 万 document/81.6 万 file 只作为生产参考；本机在 250k
  已先到 5GiB API OOM，禁止继续堆到 76 万制造无新增信息的重复 OOM。没有修改 RAGFlow submodule、
  官方镜像、上游源码或远端仓库，也没有将合成目录行视为 embedding/检索吞吐。
- 清理与遗留：live 数据集在规模阶段前经官方 API 清理；最终 scale 清理删除 250,000 document、
  250,004 file、250,000 关联和 1 个知识库，随后数据库三类 `common-agent-r2-01-*` 计数均为 0。
  四个被最终结果取代的烟测/中间目录已删除，只保留 Git 忽略的最终脱敏报告
  `.local/benchmarks/r2-01/20260722182923-60692/baseline.json`；稳定 RAGFlow 栈和 Volume 保留给
  R2-02，其他项目资源未处理。下一任务为 R2-02。
- 提交：本任务提交（见 Git 历史）。

### R2-02 创建私有 RAGFlow 镜像仓库、上游 remote 和版本化补丁分支

- 状态：✅ 已完成
- 日期：2026-07-23
- RED：先新增 `infra/ragflow/test-fork.sh`，确认缺少 fork 元数据和可执行管理脚本时关闭失败；实现
  本地仓库契约后，再把 CI 基线加入新门禁并确认 workflow 尚未执行该测试时按预期失败。
- 远端：创建 GitHub 私有镜像 `masterAventador/common-agent-ragflow`，仓库可见性为 private、默认
  分支为 `main`；`main`、`v0.26.4` 和 `common-agent/v0.26.4-patches` 初始均精确指向官方
  `cb93883f3f8c975eecb2fed81210effeb3bdb06f`。由于公开仓库不能形成私有 GitHub fork，本仓库采用
  权限独立的私有镜像语义，官方历史、tag 与基线提交仍完整保留。
- 工作区：新增 `fork.env` 作为私有仓库、官方 upstream、基线版本/提交、默认分支和补丁分支的单一
  元数据源；`fork.sh prepare` 从私有 origin 在 Git 忽略的 `.local/ragflow-fork` 克隆补丁工作区，
  保留官方 `https://github.com/infiniflow/ragflow.git` 为 upstream，并把其 push URL 固定为
  `DISABLED`。正式复现得到 origin、upstream、分支和 HEAD 均与锁定值一致。
- 完整性：本地与远端校验要求私有 `main`/tag 永远等于官方基线，补丁分支可以前进但必须包含该
  基线，工作区必须干净；真实 `gh repo view` 关闭失败地检查 private 和默认分支。本地裸仓库测试
  已证明合法补丁提交可通过，而把远端 main 指向补丁提交会被拒绝。CI 基础设施门禁现已执行该无网
  络 fixture 测试。
- 门禁：私有 fork fixture、真实 GitHub 远端完整性、既有官方 submodule/Compose 基础设施契约、全仓
  ShellCheck、CI 基线、Secret 治理、正式源码依赖/配置安全扫描、V1 冻结哈希和 `git diff --check`
  全部通过。
- 阶段边界：本任务没有修改官方 `third_party/ragflow` submodule 指针、RAGFlow 源码、正式 Compose
  或官方镜像，也没有把补丁工作区接入运行栈；前三项性能补丁从 R2-03 开始逐项实现，统一到 R2-07
  才把 common-agent 依赖切换到已推送且完整回归的 fork commit。
- 清理与遗留：测试裸仓库和工作区由 trap 精确删除；保留 `.local/ragflow-fork` 作为后续补丁开发
  工作区，稳定 RAGFlow 容器与 Volume 未改动，其他项目资源未处理。下一任务为 R2-03。
- 提交：本任务提交（见 Git 历史）。

### R2-03 移植删除定向校验、独立计数和延迟 JOIN 分页

- 状态：✅ 已完成
- 日期：2026-07-23
- RED 与参考取舍：逐项对照旧提交 `3a0b4812a`（定向删除）、`d1e28c85e`（独立计数）和
  `cd7a88c6f`（延迟 JOIN）后，确认官方 `v0.26.4` 三个问题仍存在；新增查询形态与行为测试，首次
  运行 4 项按预期失败。没有照抄旧实现：REST handler 不构造 Peewee 查询，列表以 `Document` 作为
  计数和分页的唯一事实源，完全移除既不筛选也不提供返回列的 `File2Document/File` JOIN，只把
  `UserCanvas/User` 展示 JOIN 延迟到页内 ID 已收敛之后，避免缺失映射让列表与总数互相矛盾。
- fork 实现：`DocumentService.get_by_kb_id` 复用同一过滤器生成 `COUNT(Document.id)` 和纯文档分页
  ID 查询，再对最多一页 ID 查询详情；不需要总数的内部调用显式跳过 count。新增
  `get_ids_by_kb_id(kb_id, doc_ids)`，删除一个或少量文档时只查询该知识库内请求 ID，删除全部时也只
  返回 ID 列，不再把全部 ORM 文档对象装入 API 进程。补丁以 `89be2313a` 初次提交；首轮真实删除
  暴露当前镜像 Peewee 的 `scalars()` 返回 generator、不能继续调用 `.iterator()`，随后加入真实返回
  形态回归并改为 query iterator，修复提交
  `b29cf25ce1c7d848c691768195d52adbd5275a1e` 已推送私有
  `common-agent/v0.26.4-patches`，远端 private/main/tag/upstream 完整性仍通过。
- 基准可信度：扩展 R2-01 正式运行器，使其绑定候选源码 commit、`patched` AST 形态审计和临时镜像
  OCI revision；报告按模式采集真实 SQL，不再给补丁运行误记官方 JOIN 计划。为此先写报告 RED，再
  实现独立计数、分页 ID、页内详情和删除归属四类 `EXPLAIN ANALYZE`；同时修正旧报告深页计划使用
  `target - 30` 而非真实 API 页偏移的问题。源码、commit、镜像或查询形态任一不匹配均关闭失败。
- 正式性能：在相同 1k/10k/50k/100k/250k 档位、3 次采样和真实 RAGFlow API 下，第一页 p50 为
  `0.014/0.033/0.175/0.041/0.075s`，官方基线为
  `0.022/0.122/0.764/1.802/5.075s`；深页 p50 为
  `0.014/0.029/0.103/0.349/0.918s`，官方为
  `0.022/0.132/0.854/1.992/5.526s`。单删为
  `0.029/0.040/0.111/0.191/0.468s`；官方前四档为
  `0.064/0.400/1.915/4.896s`，250k 则在 `6.211s` 后断连并 OOM。补丁版 250k 成功返回且删除后
  不存在，API 无重启、无 OOM。
- SQL 与真实链路：250k 时独立 count 的实际累计工作为 `250,001`，官方展示 JOIN count 为
  `2,250,001`；深页先完成 `500,010` 的纯文档分页工作，再把展示 JOIN 限制到 10 个页内 ID、累计
  工作 60；删除归属从物化 250,000 个文档降到主键命中 1 行。另以真实 Worker、MinIO、ES 和百炼对
  8 文档完成上传 `0.088s`、解析 `7.330s`、带 rerank 检索 p50/p95 `0.516/0.526s`、删除
  `0.065s`，唯一标记命中且删除后列表和检索均不可见；该小样本只证明正确性，不把网络波动当成查询
  补丁收益。
- 资源与门禁：47 个采样中 VM 峰值 `8,379,146,240` bytes、Swap 为 0，RAGFlow API 峰值
  `4,434,553,733` bytes，最终五个容器均运行、无重启、无 OOM。fork 受影响 DB service 全目录
  `72 passed`，改动文件 Ruff、编译和 diff 通过；common-agent 基准契约 `9 passed`，后端全量
  `924 passed, 15 skipped`，Ruff 与 Mypy（381 个源文件）通过；前端 30 个文件 `163 passed`，
  ESLint、TypeScript、生产构建与七路由包体预算通过。全仓 ShellCheck、CI、RAGFlow 官方栈/fork
  fixture 与真实远端、安全/Secret、OpenAPI/事件/生成 DTO 漂移、V1 冻结哈希和 `git diff --check`
  均通过。
- 失败矩阵与边界：覆盖错误源码模式、源码/commit/镜像不一致、旧查询形态漂移、空页、请求 ID
  归属、删除全部、无效 ID 顺序与错误、筛选条件下 count/page 一致性、Peewee generator 运行时差异、
  删除后可见、服务断连/OOM、资源采样和清理失败。没有把补丁写进官方 submodule、运行中容器或官方
  镜像，也没有把候选镜像变成正式 Compose 依赖；正式 submodule/镜像切换仍只在 R2-07 进行。写入、
  embedding、Tika、目录缓存和检索算法不在本任务修改范围，分别留给 R2-04/R2-05。
- 清理与遗留：正式报告保留在 Git 忽略的
  `.local/benchmarks/r2-03/b29cf25ce/baseline.json`；live 数据集经 API 删除，scale 清理移除剩余
  249,999 document、250,004 file、249,999 关联和 1 个知识库，随后按测试名称复核 dataset、
  document、file 均为 0。已删除首个失败候选报告、临时
  Dockerfile 和两个无容器引用的自建候选镜像；稳定栈已恢复
  `infiniflow/ragflow:v0.26.4`，版本端点与百炼 embedding/rerank/defaults 均 ready，项目 Volume
  保留。下一任务为 R2-04。
- 提交：RAGFlow fork 提交 `89be2313a`、`b29cf25ce`；common-agent 本任务提交见 Git 历史。

### R2-04 重做批量写入、独立 embedding 并发、Tika 启动与必要目录缓存

- 状态：✅ 已完成
- 日期：2026-07-23
- RED 与参考取舍：逐项审计旧提交 `9ada40a90`（embedding 解耦）、`c2c8ac450`（Tika 锁）、
  `bc3e8f387/f95006ebd`（画像批量写与全局 refresh）和 `bd1ad1a47`（目录 TTL 缓存）。先证明官方
  limiter 仍把 embedding 绑定到 chunk builder、六条生产 parser 路径仍直连 python-tika、根目录查询
  仍使用 `parent_id = id` 列比较；对应行为/源码测试分别先失败。common-agent 写入基准模块和正式运行
  脚本也先以缺失模块/文件失败，Docker 默认参数契约先以 `4/缺少独立值` 失败。没有复制 HugAI 专用
  画像路由，也没有关闭全局 ES refresh；写入继续使用上游 `wait_for` 可见性语义。没有采用可能陈旧的
  进程内 TTL 缓存，改为可走索引且无需失效协议的根目录常量查询。
- fork 实现：`MAX_CONCURRENT_EMBEDDINGS` 与 chunk 构建限流独立，通用 Python 缺省仍保守为 `1`；
  新增统一 Tika 包装器，只串行化首次成功冷启动，失败可重试、热路径保持并发，并把
  `parser/laws/naive/presentation/book/one` 六个实际调用方全部接入；根目录先按
  `tenant_id + name=/ + type=folder` 索引条件查询，再在 Python 验证 `parent_id == id`，能跳过同名嵌套
  目录且不引入缓存一致性问题。基于正式 5 GiB API 容器的参数对照后，Docker profile 固定有界默认
  `DOC_BULK_SIZE=32`、task/chunk/embedding 并发 `5/1/8`，并记录小容器与供应商限流时必须下调。
- 参数基准：相同 4 文档、每文档 32 段 × 600 词、128 chunks 的试验中，`bulk=32/embed=4` 为
  `22.685s/5.642 chunks/s`；`32/8` 为 `19.493s/6.567 chunks/s`；保持 embed=8 把 bulk 降回 4 后为
  `27.414s/4.669 chunks/s`，证明独立并发和有界 bulk 均有收益，而不是照抄旧默认。所有配置均由
  容器实际环境和 OCI revision 双重校验，未只改报告参数。
- 正式性能：官方 `cb93883f3`、`bulk=4/embed=1` 解析 `37.033s`、吞吐
  `3.456 chunks/s`；最终 fork `e81ce4fdf`、`32/8` 解析 `22.152s`、吞吐
  `5.778 chunks/s`，吞吐约提升 67%，唯一标记经真实 `qwen3-rerank` 检索命中。25 万规模下旧根目录
  列比较累计读取 `250,013` 行，新常量索引查询只读取 3 行；两份报告均完成隔离数据精确清理，API
  无重启、无 OOM、Swap 为 0，最终候选 API 峰值内存 `4,479,650,890` bytes。
- Tika 与提交：最终候选镜像一次性容器执行 8 路真实文本冷启动，python-tika/Java 服务只完成一次受
  保护启动，8 次解析均返回正文。补丁按职责提交并推送私有分支：`32aa5fa7c`（独立 limiter）、
  `9c88b3073`（全路径 Tika guard）、`8b02c52ec`（索引化根目录查询）、`e81ce4fdf`（基准选定的有界
  Docker 参数）；本地/远端完整提交均为 `e81ce4fdfc6edcd388709a1094e39d1ddbf51a7f`，私有 main/tag 与
  官方 upstream 基线未漂移。
- 门禁：fork 数据库服务全目录、limiter 和 Tika 共 `80 passed`，改动文件 Ruff、编译与 diff 通过；
  common-agent 后端全量 `928 passed, 15 skipped`，Ruff 与 Mypy（383 个源文件）通过；前端 30 个文件
  `163 passed`，ESLint、TypeScript、生产构建与七路由包体预算通过。OpenAPI/事件/生成 DTO 漂移、
  RAGFlow fork/官方栈、platform/backup/production、CI/覆盖率/Bundle、安全入口、实际 Semgrep/Trivy、
  Secret、全仓 ShellCheck、V1 冻结哈希和 `git diff --check` 均通过。
- 失败矩阵与边界：覆盖无效/越界规模与并发参数、源码/commit/镜像 revision/运行参数不一致、Tika
  冷启动失败重试与热并发、遗漏生产调用方、嵌套同名目录、写入解析失败/超时、分块不足、标记检索
  不可见、资源采样/清理/OOM；运行器在既有栈异常时重启并复核 API/模型，由它临时启动整栈时负责
  停止，最小真实写入 smoke 已执行成功路径 trap。旧画像 API、全局 refresh 开关、TTL 缓存和知识
  图谱参数均明确不采用。本任务没有修改官方 submodule、正式 Compose 或检索算法，私有依赖切换仍
  留在 R2-07。
- 清理与遗留：只保留 Git 忽略的官方报告
  `.local/benchmarks/r2-04/official/baseline.json` 与最终报告
  `.local/benchmarks/r2-04/e81ce4fdf/final.json`；参数中间报告、临时 Dockerfile/Compose override 和两个
  无容器引用的候选镜像已精确删除。稳定栈恢复为 `infiniflow/ragflow:v0.26.4`，版本端点与百炼
  embedding/rerank/defaults 均 ready，项目 Volume 保留。下一任务为 R2-05。
- 提交：RAGFlow fork 提交 `32aa5fa7c`、`9c88b3073`、`8b02c52ec`、`e81ce4fdf`；common-agent
  本任务提交见 Git 历史。

### R2-05 评估并优化语义检索、文档/切片读取和大结果边界

- 状态：✅ 已完成
- 日期：2026-07-23
- 审计与取舍：`ragflow-deploy` 没有可直接移植的检索/读取补丁；逐段复核官方 `v0.26.4` 后确认其已
  有约 64 条的有界 rerank 窗口、Elasticsearch 主查询不返回向量、超过 10k 的切片列表使用
  `search_after`、页大小限制为 100，且单切片响应会移除向量/token 等运行字段。真实 12,016 条切片
  深分页、单切片和带百炼 rerank 检索均正常，因此没有为制造改动而重写检索算法、复制旧版实现或给
  已有读取路径再加第二套分页。审计发现的实际缺口是三个公开入口允许无上限正整数 `top_k`：官方
  `/api/v1/retrieval` 以 `top_k=5001` 请求时把非法候选规模传入 Elasticsearch，返回业务码 100 和
  `x_content_parse_exception/BadRequestError`，而不是稳定的输入错误。
- RED/GREEN 与 fork 实现：先为共享候选池上限和三个 handler 接入写 RED，首次因常量/校验器不存在
  失败；随后在现有分页工具模块增加与官方 dataset search 一致的 `REST_API_MAX_TOP_K=2048` 和共享
  校验，应用到 REST retrieval、Dify retrieval、searchbot 请求值及 search 配置回退值。无效值在进入
  embedding/rerank/Elasticsearch 前以明确业务错误返回；没有改变合法请求排序、阈值或响应结构。
  补丁提交 `9140f309de9129dc7cd6c889f2e0335b3f384628` 已推送私有
  `common-agent/v0.26.4-patches`，GitHub 远端 HEAD 与本地一致。
- 基准可信度：新增的正式运行器绑定源码 commit、`official/patched` 源码形态和候选镜像 OCI
  revision；凭据只从 0600 Token 文件或环境读取，不进命令参数/报告。每轮先经真实 API 创建 2 个
  文档、解析 32 个真实切片并执行 `qwen3-rerank` 检索，再给真实文档精确附加 12,000 条无向量合成
  切片，只用于验证页首、越过 10k 的第 110 页、超限页大小和单切片响应；最终按精确 ID 删除合成
  数据并经 API 删除数据集。源码、镜像、密钥、参数、资源采样或清理任一漂移均关闭失败。
- 正式结果：官方合法 `top_k=5/64/2048` 分别为 `0.550/0.830/0.811s`，候选为
  `1.042/0.796/0.854s`，均返回 5 条且唯一标记命中；该请求包含外部 rerank 波动，只证明合法行为和
  有界延迟，不把差值宣称为补丁性能收益。官方超大候选池在 `0.244s` 后暴露 Elasticsearch 异常；
  候选 `top_k=2049` 在 `0.008s` 以业务码 102 和明确的 `<=2048` 信息提前拒绝，响应从 1,107 bytes
  降到 68 bytes。官方/候选页首 100 条为 `0.046/0.027s`，第 110 页为 `0.290/0.164s`，单切片为
  `0.008/0.007s` 且运行字段均未泄漏；读取算法未改，差值只作健康观测。
- 资源与门禁：候选 VM 峰值 `8,750,456,832` bytes、Swap 为 0，API/ES 峰值分别为
  `4,486,093,341/2,008,970,953` bytes，五个容器最终均运行、无重启、无 OOM。fork 完整 API 单元
  回归 `249 passed`，改动文件 Ruff、内存语法编译和 diff 通过；common-agent 基准契约纳入后端全量
  `933 passed, 15 skipped`，Ruff 与 Mypy（385 个源文件）通过。前端 30 个文件 `163 passed`，ESLint、
  TypeScript、生产构建和七路由包体预算通过。OpenAPI/事件/生成 DTO、RAGFlow fork/官方栈、
  platform/backup/production、CI/覆盖率/Bundle、安全入口及权威 Semgrep/Trivy、Secret、全仓
  ShellCheck、V1 冻结哈希和 `git diff --check` 均通过。
- 失败矩阵与边界：覆盖源码/commit/镜像 revision 不一致、缺失或非 0600 Token、非法规模和深页参数、
  `top_k` 非正数/超过上限、searchbot 配置二次覆盖、官方 ES 大结果异常、标记未命中、页大小超过
  100、深页不足、单切片字段泄漏、批量写/删部分失败、资源采样、服务断连/OOM 和异常后 API 恢复。
  本任务没有修改官方 submodule、正式 Compose、检索排序算法或读取查询；私有依赖切换仍只在 R2-07
  进行。
- 清理与遗留：只保留 Git 忽略的官方报告
  `.local/benchmarks/r2-05/official/baseline.json` 与候选报告
  `.local/benchmarks/r2-05/9140f309d/final.json`；两轮各 12,000 条合成切片均精确删除，MySQL 中
  `common-agent-r2-05-*` 数据集复核为 0。失败报告、临时 Semgrep/uv 文件、Dockerfile、Compose
  override 和无容器引用的候选镜像均已删除。稳定栈恢复为 `infiniflow/ragflow:v0.26.4`，版本端点与
  百炼 embedding/rerank/defaults 均 ready，项目 Volume 保留。下一任务为 R2-06。
- 提交：RAGFlow fork 提交 `9140f309d`；common-agent 本任务提交见 Git 历史。

### R2-06 私有补丁集的正确性、性能、升级冲突和安全回归

- 状态：✅ 已完成
- 日期：2026-07-23
- RED/GREEN 与补丁锁定：先以缺失验证器、错误提交顺序、错误冲突集合、脏工作区和旧阶段报告建立
  关闭失败契约，再新增 `patchset.env`、`verify-patchset.sh` 和三报告汇总门禁。最终补丁从官方
  `cb93883f3f8c975eecb2fed81210effeb3bdb06f` 线性前进到
  `9140f309de9129dc7cd6c889f2e0335b3f384628`，共 7 个按职责拆分的提交、无 merge commit，改动只在
  `api/docker/rag/test`；本地工作区、私有远端 `common-agent/v0.26.4-patches` 和锁定 HEAD 一致且
  均干净。CI 基础设施门禁已执行无网络 fixture，真实验证另行检查私有远端。
- 升级冲突审计：抓取官方 `main@d19a036cdaa7da3eb6e0cf1dc0d905f4a87c1d0d`，它位于基线之后
  364 个提交；`merge-tree` 对完整补丁集只产生
  `api/apps/services/dataset_api_service.py` 一处已知人工合并点，因为上游已移除旧
  `run_embedding` 调用，而本补丁仍在旧调用上增加 `calculate_total=False`。验证器把该精确冲突集
  当成快照，冲突消失、新增或换路径都会失败；截至本次审计没有比 `v0.26.4` 更新的稳定 tag，未用
  “零冲突”措辞掩盖后续升级工作。
- 最终正确性与性能：三份报告均绑定最终 commit、候选镜像 OCI revision 和 `patched` 源码审计。
  25 万文档第一页/深页/单删为 `0.076794/0.914179/0.034456s`，独立 count、页内详情和定向归属查询
  分别累计读取 `250001/60/1` 行，纯文档深页 ID 工作为 `500010` 行；真实 8 文档 Worker 解析、带
  rerank 检索、删除后列表/检索不可见均通过。128 chunks 最终写入解析 `16.737187s`、吞吐
  `7.647641 chunks/s`，相对官方 `3.456390` 为 `2.212609x`；25 万目录下旧/新根查询从
  `250013` 行降到 `3` 行。合法 `top_k=5/64/2048` 为
  `0.571706/0.794550/0.965017s`，`2049` 在 `0.006005s` 以明确边界拒绝；12k 合成切片页首/深页为
  `0.019260/0.158345s`，单条运行字段不泄漏，超限页大小被拒绝。
- 测试与上游限制：候选镜像内覆盖全部改动点的 64 个定向 RAGFlow 单测通过，三组真实
  API/Worker/MySQL/Elasticsearch/MinIO/百炼基准通过。尝试收集完整上游单测时，官方锁定的
  `scholarly==1.7.11` 在镜像 Python 3.13 下因无效转义触发语法错误，排除最先暴露的三个文件后，
  其他 Agent 用例导入同一包仍会失败；同样问题在未修改官方源码上可复现，故未热改依赖或把它误记为
  补丁回归，以全部改动点测试和正式纵向基准作为本任务可归因门禁。
- 安全回归：补丁生产源码 Semgrep `p/default` 的 5 条命中均由官方基线提交引入，本补丁新增为 0；
  RAGFlow 全树 Trivy Secret 的 2 条命中位于未改动前端示例常量，新增为 0。官方和候选镜像使用相同
  High/Critical、Secret、`ignore-unfixed` 规则归一化后都为 83 个既有指纹，集合完全相等，新增/移除
  均为 0。common-agent 权威 Secret、Semgrep、Trivy 依赖与 IaC 门禁通过，Python 98 个包和前端依赖
  审计均无已知漏洞。
- 资源与全量门禁：三轮最终报告的 VM/API 最高峰值分别为 `8,851,447,808` 和
  `4,490,388,308` bytes，Swap 始终为 0，五个基础容器最终均运行、重启 0、OOM=false。common-agent
  补丁报告契约纳入后端全量 `941 passed, 15 skipped`，Ruff 与 Mypy（387 个源文件）通过；前端
  30 个文件 `163 passed`，ESLint、TypeScript、生产构建、七路由包体预算和 OpenAPI 生成契约通过。
  RAGFlow manage/fork/patchset、platform/backup/production、CI/覆盖率/Bundle/安全入口、全仓
  ShellCheck、V1 冻结哈希和 `git diff --check` 均通过。
- 清理、报告与阶段边界：最终报告保留在 Git 忽略的
  `.local/benchmarks/r2-06/9140f309d/{list-delete,write,retrieval,summary}.json`；所有 R2 临时知识库和
  文档复核为 0。候选容器、Dockerfile、Compose override、Trivy 临时报告和无容器引用的精确候选镜像
  已删除；稳定栈已恢复 `infiniflow/ragflow:v0.26.4`，API 重启 0、OOM=false，百炼
  embedding/rerank/defaults ready，项目 Volume 保留。官方 submodule、正式 Compose 和镜像依赖尚未
  切换，下一任务 R2-07 才把已推送且已回归的 fork 提交作为 common-agent 正式依赖。
- 提交：RAGFlow fork 最终补丁集 HEAD `9140f309d`；common-agent 本任务提交见 Git 历史。

### R2-07 推送私有仓库并把 common-agent submodule/镜像/脚本切到 fork 提交

- 状态：✅ 已完成
- 日期：2026-07-23
- RED 与依赖锁定：先以缺失 `image.sh` 建立 fork 镜像契约并观察预期失败；随后把 `.gitmodules`
  改为可随父仓库 SSH/HTTPS 协议解析的私有 sibling 相对 URL，submodule gitlink、私有远端补丁分支和
  本地工作区统一锁定
  `9140f309de9129dc7cd6c889f2e0335b3f384628`。官方 `v0.26.4` tag 仍精确指向
  `cb93883f3f8c975eecb2fed81210effeb3bdb06f` 且是 fork HEAD 祖先；来源脏改、origin、tag、祖先、revision
  或补丁路径任一漂移都会关闭失败。
- 可复现镜像：新增 `Dockerfile.fork`、`image.env`、`image.sh` 和契约测试，从官方固定
  `infiniflow/ragflow@sha256:e0048bb...` 基底覆盖完整 `api/rag`，不在构建中下载或重解依赖。首次正式
  构建分别暴露 Docker ARG 作用域和空行哈希比较问题，修复后逐一核对 17 个补丁生产文件、OCI
  source/revision/base 标签和 amd64 架构；最终镜像固定为
  `common-agent/ragflow:v0.26.4-9140f309d`，容器内源码与 submodule 完全一致。
- Compose、脚本与 CI：稳定栈、备份恢复、开发/real 入口和三组正式基准默认统一消费 fork 提交；写入
  默认同步为实测的 `bulk=32/embedding=8`。CI 递归检出加入可选的跨私有 sibling 仓库细粒度 Token，
  并加入无 Docker 的 image/source 契约；本机权威验收不依赖 Hosted Runner Secret。README、项目结构、
  后端架构和运维说明已从“官方 checkout/镜像”切到正式私有依赖。
- 可变标签失败与修复：实际第三方镜像门禁在切换后发现 Elasticsearch tag digest 被官方重新发布、
  Valkey 滚动 `:8` 已漂移到两条有修复版本的 High 漏洞。没有更新基线放行：Valkey 固定回零
  High/Critical 的既有已审阅 digest；Elasticsearch 旧 digest 已被官方仓库移除，重新审阅的当前 arm64
  digest 与原 High/Critical 数量及规范化指纹完全相同后才替换。Elasticsearch、MySQL、MinIO、Valkey
  最终全部由 Compose 直接消费精确 digest，安全扫描也直接扫描 digest，不再依赖本机可变 tag。
- 真实稳定栈：保留四个原生 Volume 重建外围容器并复用 fork API 镜像；最终 API、Elasticsearch、
  MySQL、MinIO、Valkey 均运行，重启 0、OOM=false，API 容器参数为
  `DOC_BULK_SIZE=32`、task/chunk/embedding `5/1/8`，百炼 embedding/rerank/defaults 全部 ready。
  fork 镜像安全基线为 High 75、Critical 5，相对官方基底没有新增或改变 Secret；六个第三方镜像的
  精确 digest、漏洞数量和明细指纹全部通过。
- 全量门禁：后端 `941 passed, 15 skipped`，Ruff 与 Mypy（387 个源文件）通过；前端 30 个文件
  `163 passed`，ESLint、TypeScript、生产构建、七路由包体预算和 OpenAPI/事件/生成 DTO 漂移通过。
  RAGFlow image/manage/fork/patchset、platform/backup/production、CI/覆盖率/Bundle、安全/Secret、实际
  Semgrep/Trivy、Python 98 包和前端依赖审计、主仓 ShellCheck、V1 冻结哈希及 `git diff --check` 均通过。
- 清理与阶段边界：镜像扫描临时报告均已删除，失败构建未留下悬空镜像；稳定数据 Volume 保留，正式
  fork 栈继续运行供 R2-08 真实链路复用。本任务验证了私有远端与当前工作区依赖闭环；从全新空目录
  递归克隆、完整知识链、备份恢复和资源/清理由 R2-08 独立执行。
- 提交：RAGFlow 私有补丁 HEAD `9140f309d` 已在远端；common-agent 本任务提交见 Git 历史。

### R2-08 真实知识链、备份恢复、资源与全新递归克隆验收

- 状态：✅ 已完成
- 日期：2026-07-23
- 全新克隆与权限边界：在一次性空目录从 GitHub 私有主仓执行递归克隆，父仓精确取得
  `a8a9bb3b275999fc7bdd2db492386f8b38db4433`，submodule 精确取得
  `9140f309de9129dc7cd6c889f2e0335b3f384628`；相对 URL 解析到私有 sibling origin，父仓与
  submodule 均洁净，镜像来源和 image 契约通过。另以没有 SSH 身份的隔离配置复现私有 submodule
  初始化失败，Git 保留私有 URL 且没有静默回退官方仓库；README 已补双仓权限排障说明。
- 正式 fork 真实知识链：在固定 fork 镜像上连续通过 MVP 与批量知识 E2E。MVP 从创建知识库、上传解析
  到员工两轮回答、Citation、真实工作流检索/手动运行/员工触发完整通过；批量链以并发不高于 2 上传
  12 个多格式文件，覆盖解析重试、跨文档 `18/12/6` 回答、双 Citation 和 101 条文档分页。删除 E2E
  实际发现 DELETE 204 后没有用户可见完成状态，先补 RED 测试，再复用 mutation 状态显示“会话已删除”；
  同时把旧测试的“还没有会话”修正为产品稳定文案“暂无历史会话”，最终会话、工作流、知识库删除与
  清理全部通过。
- 加密备份与空环境恢复：`infra/backup/manage.sh drill` 在隔离 Compose project 和全新四个 RAGFlow
  Volume 上完成 AES-256-GCM 备份、清单校验、源环境销毁、平台 MySQL 与 RAGFlow 全量恢复；恢复后
  浏览器从外部引用重新访问知识链通过，总恢复 61 秒、外部引用 1 条，低于 120 分钟 RTO。恢复容器、
  Volume、端口和归档已按演练脚本清理，没有借用源环境继续运行。
- 资源专项与监视器修复：首次从完全停止状态启动时，系统 Python 的 `HTTPConnection` 不支持上下文
  管理器，真实门禁在采样前关闭失败并自动停止资源。增加不实现 `__enter__` 的 RED 自测后，把探活改为
  显式 `close()`，自测与脚本合同转绿。最终冷启动 38 个样本、93.879 秒，VM/容器峰值
  `7,372,144,640/7,305,590,473` bytes；30 分钟稳态 180 个样本，VM/容器峰值
  `7,984,836,608/7,901,089,366` bytes，Swap 0、采样错误 0、重启 0、OOM=false、未就绪样本 0。
  同轮真实 RAGFlow 生命周期和 MVP 再次通过。
- 全量门禁：后端 `941 passed, 15 skipped`，Ruff 与 Mypy（387 个源文件）通过；前端 30 个文件
  `163 passed`，ESLint、TypeScript、生产构建、七路由固定包体预算和 OpenAPI/事件/生成 DTO 契约
  通过。RAGFlow image/manage/fork/patchset、platform/backup/production、dev/real/resource/CI/覆盖率/
  Bundle/平台 E2E/安全/Secret 合同、主仓 ShellCheck 均通过；实际 Secret/Semgrep/Trivy 源码扫描、
  Python 98 包和前端依赖审计均无新增或已知漏洞。生产构建一度精确暴露 `/workflows` 首屏图超预算
  154 bytes，收紧删除提示实现后在不放宽预算的前提下恢复通过。
- 清理、报告与阶段边界：真实 E2E 业务数据清理为 0；递归克隆、备份恢复资源和临时端口均已删除；
  稳定容器与 `common-agent-dev` Colima 已停止，原生数据 Volume 和已验证 fork 镜像保留。失败诊断与
  最终资源证据保留在 Git 忽略的 `.local/soak/r8-04/20260722231140-76892` 和
  `.local/soak/r8-04/20260722231508-79452`，没有泄漏凭据。下一任务为 Q2-01。
- 提交：RAGFlow fork 仍锁定已推送的 `9140f309d`；common-agent 本任务提交见 Git 历史。

### Q2-01 工具链与私有 RAGFlow 的全量回归、安全复审和 V2 最终验收

- 状态：✅ 已完成
- 日期：2026-07-23
- 生产同路径复核：从 R2-08 提交后的干净主线重新执行三组正式页面链路。工具授权 E2E 通过 1 个
  用例，分别验证零费用“当前时间”在通用会话和数字员工中的精确授权、托管 HTTP 有副作用调用断连后
  只形成一次 `tool_result_unknown`、外部 Streamable HTTP MCP 只调用一次；真实私有 RAGFlow MVP
  通过 1 个用例，重新覆盖知识库上传/解析、员工回答与 Citation、工作流检索和清理；托管工具管理页
  通过 2 个用例，覆盖手工能力、OpenAPI 导入和外部 MCP 管理。三轮清理分别确认通用会话 2、员工 1、
  模型 1、MCP 来源 2，以及工作流 1、知识库 1 等本轮业务数据均被精确删除。
- 回归补强与关闭失败：首次实际覆盖率门禁准确暴露后端总行/分支只有 `89.36%/70.44%`，没有降低
  阈值；补齐工具路由稳定错误、托管 HTTP 参数构造、OpenAPI 非法结构/引用/参数/请求体、RAGFlow
  模型配置/迁移/Token 文件安全、事件/OpenAPI 导出、模型连通验证和运行时输入不变量。完整后端最终
  为 `1095 passed, 15 skipped`，总行/分支 `90.99%/74.24%`，核心行/分支
  `93.23%/77.68%`；Ruff 与 Mypy 对 390 个源文件通过。前端首次覆盖为 `84.38%`，补齐工具和系统
  API 的请求编码、严格响应与传输失败契约后，30 个文件 `167 passed`，行/分支
  `86.18%/75.27%`。查看者权限组件在全并发覆盖运行中曾超过原显式 10 秒但单测 4.66 秒通过，测试
  超时只调整为 20 秒，断言、产品逻辑和覆盖阈值均未放宽。
- 构建与契约：前端 ESLint、TypeScript、OpenAPI/会话事件/工作流事件/生成 DTO 漂移和生产构建通过；
  七个异步路由均在固定预算内，最大 chunk `178410` bytes，最紧的 `/workflows` 首次 JS 图仍为
  `1499991/1500000` bytes。RAGFlow manage/fork/patchset/image、平台、备份、生产回滚、dev/real、CI、
  覆盖率、Bundle、平台 E2E、资源和安全入口合同及全仓 ShellCheck 全部通过；V1 冻结哈希仍为
  `9fd738cf7ecc8d44d4e59eaf502ba524cc4a5b345031772e73710567555eec94`。
- 私有依赖与安全复审：submodule、本地/私有远端补丁分支和正式镜像继续精确锁定已推送的
  `9140f309de9129dc7cd6c889f2e0335b3f384628`，未回退官方镜像或改变七项补丁。最终工作树 Secret、
  Semgrep、Trivy 依赖与 IaC 实扫通过，Python/前端锁文件漏洞均为 0。生产 API/Web 镜像
  `adc68860b0d503cafb85453243dde7713fdb4823-20260723T001201Z` 的 High/Critical/Secret 均为 0；
  平台 MySQL、私有 RAGFlow、Elasticsearch、RAGFlow MySQL、MinIO、Valkey 的已审阅精确镜像结果
  分别为 `19/1`、`75/5`、`27/3`、`140/4`、`32/0`、`0/0`，digest、数量和指纹均与固定基线一致。
  本任务只增加测试和测试稳定性配置，生产源码、依赖锁和镜像输入未改变，因此不为制造新 revision
  重建同内容镜像。
- 失败矩阵与真实边界：新增覆盖不存在的托管/外部 MCP、能力、集合与凭据资源，OpenAPI 重复/循环/
  外部引用、非法路径/参数/Header/Schema/请求体，RAGFlow 非法数据集/文档响应、迁移忙碌/失败/超时、
  非官方百炼 URL、Token 符号链接/权限/原子替换失败，模型连通流关闭，以及前端 API Schema 漂移和
  网络失败。既有真实链继续覆盖越权、Schema 漂移不自动扩权、副作用结果不确定不重放、凭据脱敏与
  私有 RAGFlow 写入/检索/删除。Q2 没有修改 RAGFlow 生产代码，R2-08 已在相同 fork/镜像上完成的
  30 分钟资源 soak 和空环境恢复不重复消耗外部费用；本轮重新执行真实知识 MVP 和工具链确认依赖未漂移。
- 清理、遗留与提交：所有测试 API、Worker、Vite、Playwright、无头浏览器、临时数据库记录、MCP
  服务和合同临时目录均已退出或清理；项目 Docker context 无容器，最终停止空闲的 32 GiB
  `common-agent-dev` Colima，保留已验证的项目 Volume 和正式 fork 镜像。V2 当前没有未完成任务或
  待验收项；远程部署、工具市场、用户名密码代登录、OAuth 和更多付费内置工具仍在既定 V2 范围外。
  本任务提交见 Git 历史。

### R2-06/R2-07 维护复审：把 RAGFlow fork 收敛为最小补丁栈

- 状态：✅ 已完成
- 日期：2026-07-23
- 复审结论：逐项检查 RAGFlow `v0.26.4` 的公开插件、配置与外围扩展能力后，确认文档列表/定向删除
  查询、embedding 独立限流和根目录索引查询没有可替代的官方扩展钩子，继续保留源码补丁；Tika
  启动锁不覆盖 common-agent 当前允许的 TXT/Markdown/PDF/DOCX 路径，删除并保留未来外置 Tika
  Server 的无 fork 方案；批量大小和 task/chunk/embedding 并发属于部署参数，迁移到 common-agent
  `compose.override.yaml`；公共 retrieval `top_k` 补丁退出 fork，平台正式检索继续固定 `top_k=5`，
  不替 RAGFlow 的 Dify/searchbot 等无关入口改变语义。旧分支与旧提交保留为历史证据，没有强制重写。
- 最小 fork：从官方 `v0.26.4@cb93883f3f8c975eecb2fed81210effeb3bdb06f` 新建并推送
  `common-agent/v0.26.4-minimal`，最终 HEAD 为
  `21eb8fb4001421f2952ce3125e46e753825d3f9b`。三项能力分别由线性提交
  `0262bf6d1`、`bb7c0f316`、`21eb8fb40` 承载；相对官方共改 8 个文件、`+358/-45`，其中生产代码
  严格限制为 4 个文件、`+73/-44`。`patchset.env` 新增精确生产文件白名单；私有远端、提交顺序、
  无 merge、工作区洁净和白名单全部关闭失败。与锁定官方
  `main@d19a036cdaa7da3eb6e0cf1dc0d905f4a87c1d0d` 的 `merge-tree` 冲突从旧栈 1 处降为 0。
- RED/GREEN：三组 fork 补丁均先在官方基线上观察目标失败，再做最小实现；文档查询 6 个定向用例、
  embedding 联合 7 个用例、最终含文件上传/目录逻辑的 29 个联合用例全部通过，语法编译和
  `git diff --check` 通过。主仓配置契约分别先因旧分支、旧 commit、缺少生产文件白名单失败，修正后
  fork/patchset/image/manage 四组门禁及真实远端升级审计通过。写入和检索基准测试中残留的 Tika 与
  `top_k<=2048` 旧假设也先 RED，再改为验证 Tika guard 缺席和 retrieval 官方形态保留，相关 17 个
  后端单测通过。
- 镜像与安全：submodule、镜像 revision 和正式标签统一切换到 `21eb8fb40`，新镜像
  `common-agent/ragflow:v0.26.4-21eb8fb40` 只从锁定官方 digest 覆盖完整 `api/rag`，容器内所有改动
  文件哈希与 submodule 一致。Trivy 在线更新因 `mirror.gcr.io` 超时关闭失败，随后使用 2026-07-22
  已下载缓存数据库重跑同一锁定门禁，High 75、Critical 5，Secret 与官方基底一致；没有用网络失败
  跳过扫描或更新安全基线。旧 `v0.26.4-9140f309d` 标签在确认无容器引用后删除。
- 性能与真实链：新报告保存在 Git 忽略的
  `.local/benchmarks/r2-06/21eb8fb40/{list-delete,write,retrieval,summary}.json`。25 万文档首/深页
  P50 为 `0.881727/0.883253s`，定向删除 `0.044673s`，count/详情/归属查询工作量为
  `250001/60/1` 行；128 chunks 写入吞吐 `6.913858 chunks/s`，为官方 `3.456390` 的
  `2.000312x`；25 万目录的根查询从 `250013` 行降为 `3` 行。正式 `top_k=5` 检索为
  `0.598609s`，12k 切片首/深页为 `0.045060/0.263315s`。三轮均清理隔离数据，Swap 0，五个容器
  重启 0、OOM=false。正式无头页面 E2E 首轮知识库用例通过，但员工链暴露唯一旧 ARIA 断言仍写
  “会话列表”；组件和其他测试的权威名称均为“历史会话”，一行修正后 React→FastAPI→Worker→
  新 RAGFlow 的员工/知识库两条链路 `2 passed`，业务数据和临时进程全部清理。
- 最终门禁：后端全量 `1095 passed, 15 skipped`，总行/分支覆盖率 `90.97%/74.19%`、核心
  `93.29%/77.68%`，Ruff 和 Mypy（390 个源文件）通过；前端 30 个文件 `167 passed`，行/分支
  `86.18%/75.27%`，ESLint、TypeScript、生产构建、Bundle 预算和 OpenAPI/事件/生成 DTO 漂移通过。
  RAGFlow 三报告统一门禁、远端补丁集、镜像源码/安全、Compose 参数、真实百炼模型状态及页面生产
  同路径均通过。最终移除 RAGFlow 与平台测试容器、停止 32 GiB `common-agent-dev` Colima，保留原生
  数据 Volume、新验证镜像和 Git 忽略报告；本次没有新增产品范围或遗留待验收项。

### R2-09 平台工作区与 RAGFlow 技术租户 1:1 隔离及存量默认工作区迁移

- 状态：✅ 已完成
- 日期：2026-07-23
- 迁移审计：真实平台库只有默认工作区，RAGFlow 中
  `common-agent@local.test` 持有 5 个数据集和 1 个 API Token，其他平台工作区和知识库归属映射为
  0，因此默认工作区可以原位接管现有账号，无需复制文档或重写员工、工作流及 Citation 引用。公开
  RAGFlow API 已确认 Token 按账号/tenant ID 限定命名空间；公开 API 没有数据集所有者转移能力。
  对未来发现的“非默认工作区已有旧归属但尚无独立身份”场景，迁移守卫启动关闭失败，不静默复制、
  过滤或错绑数据。
- RED/GREEN：先增加工作区身份 keyring、Token AAD、确定性账号密码、接管/重试/旧映射守卫、动态
  请求 Token、会话每轮归属复核、独立账号公开 API 和 Alembic head 测试，分别观察到模块、构造参数、
  迁移和归属路径不存在的预期失败；旧账号密码轮换也先因 adopt 参数与公开 PATCH 能力缺失失败。
  实现后定向 124 项回归通过，完整后端最终 `1110 passed, 15 skipped`，跳过项均为需要显式外部配置
  的既有真实 RAGFlow/百炼/Deep Agents 专项。
- 身份与密文：Alembic `20260723_0027` 增加 `ragflow_tenant_identities`，平台租户为主键，RAGFlow
  账号邮箱和租户 ID 分别全局唯一；`provisioning/active` 约束保证半成品没有伪装成可用身份。
  RAGFlow Token 使用独立 AES-256-GCM 多密钥 keyring，随机 96-bit nonce，AAD 绑定格式版本、平台
  租户、账号邮箱和 RAGFlow 租户 ID；生产环境缺少
  `COMMON_AGENT_RAGFLOW_IDENTITY_KEYS` 直接拒绝启动。账号密码按租户和记录的 key ID 用 HMAC-SHA256
  派生，只以 RAGFlow 要求的 RSA 密文发送，不落库、不回前端。
- 运行链路：API 与 Worker 启动时复核存量迁移并尽力初始化当前工作区；外部 RAGFlow 暂时不可用时
  平台仍可启动，首次知识操作安全重试初始化并返回稳定 503。新工作区通过公开注册、登录、资料、
  provider/model/default 和 Token API 建立独立 RAGFlow 技术租户；每次知识请求从当前
  `TenantAccess` 动态解密 Token，不再共享进程级 Header。会话检索改用已经装配归属仓储的
  `KnowledgeBaseService`，绑定后每一轮仍复核知识库归属。
- 默认账号升级：默认工作区以既有 0600 Token 原位接管 `common-agent@local.test`，保留 5 个知识库
  和现有外部 ID；首次接管把源码历史固定密码轮换为工作区派生密码。`real.sh` 和 RAGFlow 模型配置
  CLI 改为优先用 Token 文件，密码轮换后再次启动、模型检查与 Token 检查全部通过。平台库只保存
  12-byte nonce 和 67-byte ciphertext，未保存明文 Token 或密码；备份文档同步要求恢复时从独立秘密
  存储提供原身份 keyring。
- 真实双租户验收：从真实前端 Origin 调用正式 FastAPI 注册临时 Owner 并创建第二工作区，平台自动
  创建第二个 RAGFlow 账号/租户和独立 Token。默认工作区列表为 5，第二工作区初始为 0；在第二工作区
  创建临时知识库后其列表为 1，而默认工作区仍为 5 且看不到该 ID，`isolated=true`。随后通过平台 API
  删除临时知识库，并精确清理临时 Owner、平台工作区、RAGFlow Token/model provider/root file、
  user-tenant、tenant 和 user；复核临时记录均为 0，默认账号和 5 个知识库未改变。
- 门禁与安全：Ruff、Mypy（212 个生产源文件）、Alembic 空库/重启/损坏恢复、MySQL/HTTP 集成、
  real 统一入口合同和 `git diff --check` 通过；前端 30 个文件 `167 passed`，ESLint、TypeScript、
  生产构建和七路由包体预算通过。Secret 自检/治理与 Semgrep 通过；在线 Trivy DB 两次下载均因
  `mirror.gcr.io` 超时关闭失败，随后使用 2026-07-22 已验证缓存数据库执行相同
  High/Critical/Secret 规则，Python/前端锁文件漏洞为 0，四个 IaC 目标均无高危配置。
- 清理与提交：真实双租户业务与账号临时数据已清零，测试库身份状态由每个 fake RAGFlow 用例自行
  清理，未留下浏览器或测试服务。最终交付前停止本轮启动的 real 栈和 32 GiB Colima，保留正式默认
  身份、原有 5 个知识库、项目 Volume 与已验证 fork 镜像。本任务提交见 Git 历史。

## 附:2026-07-24 代码 Review 修复

拉取 `3bf41c1`(V2 工具/MCP + 私有补丁 RAGFlow + 生产化门禁)后做整体 review,并修复发现的
问题。这些不属于既有 V2 任务,作为独立缺陷修复记录:

| 问题 | 类型 | 修复 | 提交 |
| --- | --- | --- | --- |
| `infra/ragflow/image.sh` 的 `ensure_image` 在 fork 镜像缺失或校验漂移时经 `fail`(exit 1) 直接终止脚本,`build_image` 成为不可达代码——全新克隆、submodule 切 fork 或镜像被清理后首次 `real.sh up` 必然失败,需手动 `build-image` | 启动阻塞 | 子 shell 包裹 `verify_image` 使 exit 只退出子 shell、返回码交 if;末尾 case 加 `BASH_SOURCE` 守卫支持 source 后验证控制流;`test-image.sh` 补契约用例 | `2f9058b` |
| 托管 HTTP 运行时 `build_managed_http_request` 未复核 PATH 参数值,参数为 `.`/`..` 时可越出能力设计的路径范围(配置期已校验点段、运行期未对齐) | 安全纵深 | 渲染完 path 后复用 `_safe_path` 点段校验,运行期与配置期对齐;新增 RED 测试 | `2ac2fc3` |
| tools 大聚合模块(`routers/tools.py` 864、`openapi/managed_http.py` 708、`ToolsPage.tsx` 715)未纳入体量门禁,缺膨胀监控 | 一致性 | 新增 `AGGREGATE_LINE_CEILINGS` 防膨胀天花板门禁锁定现状上限;不做大拆分(拆分纯组织性、有回归风险,应作为独立重构任务) | `54fe851` |

验收:real 完整栈本机启动(real 模式、RAGFlow available、百炼 configured、五容器 healthy);
后端 unit+architecture+contract `915 passed`、Ruff、Mypy(212 源文件);前端 lint、typecheck、
vitest、build 与七路由包体预算全部通过。启动时 ES 官方镜像层从 docker.io 拉取断流,改用
daocloud 国内 pull-through 按**同一 digest** 补层,未改动任何 digest pin。
