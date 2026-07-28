# 通用 Agent 中台 V3 路线图：dogfood 反馈修复与 UI 对齐

> 文档性质：V2 完成后，本机 dogfood 试用反馈的 UI/体验/功能修复与页面样式对齐的唯一任务台账
> 建立日期：2026-07-25
> 状态说明：⬜ 未开始 · 🚧 进行中 · 🔍 待验收 · ✅ 已完成

V2（工具/MCP + 私有补丁 RAGFlow + 生产化门禁）已完成，见 `docs/development-roadmap-v2.md`。
本路线图承接 V2 之后 dogfood 试用中反馈的问题，长期工作/验收/安全/资源规则仍以根目录
`CLAUDE.md` 为准。每个任务遵循：实现 → 相关门禁验收 → 更新本文件状态 → 提交并推送。

## 1. 关键决策记录（避免会话丢失后重复讨论）

- **UI 现状核实**：全仓只有 `main` 分支。历史 `4c796b0 feat(ui): 按统一设计规范改造现有页面`
  确实做过 UI 改造，但只落地了 DESIGN.md 的颜色 token、logo 和基础类，**各功能页面的布局
  与交互结构没有对齐 `docs/design/PowerAI Atlas.html` demo**。用户反馈属实。
- **内置工具数量核实**：后端 `tools/platform.py` 只种了 1 个内置能力"当前时间"，符合
  `docs/product-boundary.md` 3.11（唯一内置工具是零费用的当前时间）。不是 2 个。
- **产品边界（对齐 demo 时必须守）**：只复用 demo 的**布局骨架、交互结构、视觉语言**；
  **不照搬** PowerAI 名称、电力行业定位、示例账号/数据，也不引入 demo 里的"团队空间/技能库"
  等超出当前产品范围的能力。业务文案与功能范围继续以本项目产品范围为准。
- **推进方式**：先清 🅑 独立小任务与 bug，UI 对齐 demo（🅐）作为单独阶段逐页推进；
  🅒 视觉细节并入 UI 阶段一起做，避免小改被大重构覆盖造成白做。
- **预置模型**：架构是单供应商阿里百炼。先查百炼真实上架的模型与确切标识，只预置能真实
  调通的；百炼未上架的（如 glm/kimi 若确无）不硬塞，并如实告知用户哪些可用。

## 2. 任务台账

### 2.1 🅑 独立小任务（先做，不依赖 UI 决策）

| ID | 任务 | 验收标准 | 状态 |
| --- | --- | --- | --- |
| D1 | 去掉顶部系统状态区（"后端正常/百炼已配置/RAGFlow 正常"标签） | 页面不再渲染该状态区；删除 `SystemStatus` 组件、其测试与仅服务它的孤儿 API；前端门禁通过 | ✅ 已完成 |
| D2 | 清理前端可见文案里的真实技术栈名（百炼、RAGFlow 等）为中性表述 | 模型管理页、知识库页等用户可见文案不出现"百炼/RAGFlow"；保留用户需自行填写的 qwen 模型标识示例 | ✅ 已完成 |
| D3 | 模型管理卡片不写"提供商/阿里百炼"，直接体现实际模型 | 卡片去掉"提供商：阿里百炼"行，模型标识仍展示 | ✅ 已完成 |
| D4 | 删除会话后"会话‘xx’已删除"提示不消失（bug） | 删除成功提示自动消失（或短暂后消失），不常驻；有测试覆盖 | ✅ 已完成 |
| D5 | "新建业务工具集"按钮一直不可点击 | 明确原因（无 MCP 来源时禁用）；给禁用按钮加可见原因提示，用户知道要先建 MCP 来源 | ✅ 已完成 |
| D6 | 找十几篇不同方向的民生/政策类公开资料放本地，供知识库上传解析+绑定测试 | 本地测试目录有 12+ 篇不同方向、贴近大众生活的公开文档（非学术），可用于上传测试；不进 Git | ✅ 已完成 |

### 2.2 🅓 需查证的功能

| ID | 任务 | 验收标准 | 状态 |
| --- | --- | --- | --- |
| D9 | 查阿里百炼真实上架模型目录，预置能真实调通的常用模型；创建表单加模型标识引导 | 预置的模型均能经正式链路真实调通百炼；创建模型表单对"模型标识"给出可选常用示例，降低填写困惑；百炼未上架的模型不预置并说明 | ✅ 已完成 |

> D9 说明：预置 6 个能真实调通的百炼一方模型（qwen-max/plus/turbo/long、deepseek-v3/r1），
> 覆盖所有现有工作区并在新建工作区时自动预置。**GLM/Kimi 未预置**：百炼虽上架，但属第三方
> 直供、需在百炼控制台单独"开通"后才可调（新工作区默认调不通），且标识含斜杠不符模型标识校验；
> 若用户开通并需要，须放宽标识校验作为独立改动。deepseek-v3/r1 百炼文档标注计划 2026-10-10
> 下架，届时需替换。创建表单模型标识字段已补常用标识引导。

### 2.2b 🅔 第二批 dogfood 反馈（功能 bug 与体验）

| ID | 任务 | 验收标准 | 状态 |
| --- | --- | --- | --- |
| D13 | 数字员工（qwen-long）对话报错「本次没有生成可显示的内容 / 生成失败」 | 根因：Deep Agents 中间件把系统消息 content 组装成数组，qwen-long 在百炼 compatible-mode 强制要求 content 为纯字符串（报 `Input should be a valid string`），其余模型宽容故未暴露。修复：Bailian 适配器出站前把内容块拍平为字符串；并给 deep_agents 两处被吞异常补 `_LOGGER.exception`。TDD 单测 + 真实 qwen-long 走真实 deep agent 适配层验证流式正常。生产同路径复验：经真实 FastAPI `POST /conversations/{id}/messages`（带真实会话 Cookie/CSRF/租户头）触发，同一会话内修复前消息 `status=failed / deep_agent_execution_failed`、修复后新消息 `status=completed` 并返回正常回复，真实页面截图两条消息对照可见 | ✅ 已完成 |
| D15 | qwen-max 预置在本端点调不通 | 该百炼专属 compatible-mode 端点上 qwen-max 返回非 OpenAI 结构（仅 finish_reason/text，无 choices/message），适配层无法解析，测试调用与会话都失败。从预置 seed 移除并更新说明；清理 dev 库中两个租户下无引用的 qwen-max 行。真实页面确认模型管理只剩 5 张可调通卡片、无 qwen-max | ✅ 已完成 |
| D10 | AI 对话页不随内容长度自动滚动到底部 | 对话区底部哨兵 + 按「消息条数:末条长度」变化触发 `scrollIntoView`，新消息与流式增量都会滚到最新；jsdom 缺 `scrollIntoView`，在 `src/test/setup.ts` 补 polyfill（同 matchMedia/ResizeObserver 既有做法）。RED→GREEN 单测 + 真实页面截图确认停在最新回复 | ✅ 已完成 |
| D11 | 引用资料只显示引用了哪些文档（名称） | `CitationList` 按 `document_name` 去重，只渲染名称 chip，移除片段正文与「相关度 xx%」标签；样式由片段卡片改为紧凑 chip。RED→GREEN 单测（含同文档多片段只出现一次）+ 真实页面确认只显示 `文明养犬管理规定.docx` / `文明旅游出行提示.pdf` | ✅ 已完成 |
| D14 | 模型卡片去掉「工具调用流」展示行 | 模型管理卡片不再展示「工具调用流：正常流式/自动非流式」这一行；测试改为断言该文案不存在；真实页面确认 5 张卡片均无此行 | ✅ 已完成 |
| D16 | 替换将下架的 deepseek-v3/r1，并预置各厂商前沿模型 | 先在真实端点枚举 231 个可用模型，对候选逐个实测三条真实路径（非流式 / 流式 / 流式+工具）并单独验证会输出真正 `content` 而非只有 `reasoning_content`；三条全过且标识合规才预置。新预置 8 个前沿模型：qwen3.7-max/plus/flash、deepseek-v4-pro/flash、glm-5.2、kimi-k2.6、MiniMax-M2.5，保留 qwen-plus/turbo/long，移除 deepseek-v3/r1。全部 11 个经真实「测试调用」接口返回连接成功，8 个新模型再经真实会话 API 走完整数字员工（Deep Agents）链路 `status=completed`。创建表单标识引导同步换为前沿模型 | ✅ 已完成 |

### 2.2c 🅕 需查证（第二批）

| ID | 任务 | 验收标准 | 状态 |
| --- | --- | --- | --- |
| D12 | 模型卡片标出版本号 | 调研结论：qwen-max/plus/turbo/long 是百炼**稳定别名**（背后快照随季度漂移），百炼不提供可稳定展示的版本号字段，别名调用只回显别名；`qwen-max` **不是** `qwen3.7-max`（后者是另一个独立的新代际模型）。故不能给别名硬编码版本号（会错且漂移）。现状卡片已直接展示真实调用标识（别名即稳定版本句柄），这是最准确做法。是否额外标注「底层代际」由用户定夺 | 🔍 待用户确认 |

> 补充（D16 后）：seed 现为 11 个实测可调通模型——qwen3.7-max/plus/flash、qwen-plus/turbo/long、
> deepseek-v4-pro/flash、glm-5.2、kimi-k2.6、MiniMax-M2.5。**D9 当初排除 GLM/Kimi 的理由已被实测
> 推翻**：该端点同时提供不含斜杠的合规标识（`glm-5.2`、`kimi-k2.6`），凭平台统一 Key 三条路径直接
> 调通，无需控制台单独开通，故已收录。旗舰位由 qwen3.7-max 承担（qwen-max 在本端点响应结构损坏）。
> 库中若有模型被历史消息引用则按平台外键语义停用而非删除，以保住会话记录完整。

### 2.3 🅒 视觉细节（并入 UI 阶段）

| ID | 任务 | 验收标准 | 状态 |
| --- | --- | --- | --- |
| D7 | 全局下拉/选中样式太深（Select 选中项深灰） | 选中态改为 DESIGN.md 的浅色 active（`--bg-active #F1F1EF`），全局一致 | ✅ 已完成 |
| D8 | 聊天气泡底部多出一块空白高度 | 气泡内最后一段文字底部多余 margin 清除，气泡上下 padding 对称 | ✅ 已完成 |

### 2.4 🅐 UI 大工程（独立阶段，逐页推进）

| ID | 任务 | 验收标准 | 状态 |
| --- | --- | --- | --- |
| U1 | 各功能页面布局/交互对齐 PowerAI Atlas demo（守产品边界） | 对话/知识库/工作流/数字员工/模型/工具/审计逐页对齐 demo 的布局骨架与交互；不照搬 PowerAI/电力定位；功能不回归；分多轮，每页单独验收提交 | ✅ 已完成 |

> U1 已拆解为逐页任务，详见 `docs/development-roadmap-ui.md`（UI-00 色调基线 → UI-01~UI-10 逐页），
> 全部完成并逐页真实页面验收，已在 `ui-align-demo` 分支六次提交后按 `--no-ff` 合并回 main。
> 期间用户否决了原型的 64px 窄侧栏方案（改为保留现有宽侧栏），UI-01a/UI-01c 随之作废。

### 2.5 🅖 单机 demo 部署（客户试用环境）

目标：把已验收的 `local-shared-network` 单机模式落到一台 4C16G 公网服务器，提供
`https://kb.xuanbai.tech` 的客户试用环境。设计与计划见
`docs/superpowers/specs/2026-07-27-single-node-demo-deployment-design.md` 与
`docs/superpowers/plans/2026-07-27-single-node-demo-deployment.md`。

| ID | 任务 | 验收标准 | 状态 |
| --- | --- | --- | --- |
| G1 | Edge 增加 HTTP 监听承载 ACME 与跳转 | `edge.conf.template` 新增容器内 9080 server 块（ACME 挑战路径 + 301 跳转），compose 映射 80、挂载 webroot，`manage.sh` 传递 `COMMON_AGENT_ACME_ROOT`；契约断言先失败后通过，compose config 生成 18443/18080 两端口 | ✅ 已完成 |
| G2 | 发布改为固定单槽停机模式 | 去掉 blue↔green 轮换，固定 `blue` 先停后建；验证失败不再自动切回旧槽而是提示 `rollback`；保留 `switch_edge` 调用以规避 nginx DNS 缓存 502 | ✅ 已完成 |
| G3 | 回滚改为单槽重建上一 release | 用 `previous_release` 镜像在同一槽重跑停机发布；回滚同样失败时要求人工介入；schema 不自动降级 | ✅ 已完成 |
| G4 | 单机资源覆盖与配置模板 | 按 soak 实测分配 4C16G 内存上限，RAGFlow API 加 2.0 CPU 配额并下调解析并发；实测 compose 叠加后各服务 mem_limit 真实生效 | ✅ 已完成 |
| G5 | 证书签发与自动续期 | 内部 CA 10 年有效期、SAN 为容器名；`ca.crt` 并入系统信任根以通过 preflight 对 Let's Encrypt 证书的校验（已实测 `openssl verify` 返回 OK）；新增 `edge-recreate` 供续期后重建容器 | ✅ 已完成 |
| G6 | 服务器基础环境准备 | Docker 29.6.2 + Compose v5.3.1、镜像加速、swap 4GiB、ufw 22/80/443、certbot 2.9.0、目录就位；7 个镜像中 6 个按 digest 拉取成功 | ✅ 已完成 |
| G7 | 本机真实容器验证单槽改造 | 单槽 rollout 在真实容器上多次跑通；身份初始化在"空 legacy token + 无历史账号"下 status=active，等价复现全新服务器场景 | ✅ 已完成 |
| G8 | 服务器首次部署上线 | 腾讯云轻量 4C16G/北京/Ubuntu 24.04 全栈部署完成：RAGFlow 五容器 + 业务六容器全部 healthy，Let's Encrypt 证书生效，`https://kb.xuanbai.tech` 公网可访问且无浏览器告警，HTTP 自动跳转 HTTPS | ✅ 已完成 |
| G9 | 服务器功能验收与资源实测 | 正式页面走完整用户链路（建知识库→传文档→解析→数字员工→带引用对话→工作流）、30 分钟 soak 修正 api/worker 估算值、真实 rollout/rollback 停机时长 | ✅ 已完成 |
| G10 | 证书自动续期 | 当前证书由 DNS-01 手动签发，90 天后需人工重签。需接入 DNS 服务商 API 实现自动续期，或改用云厂商 1 年期免费证书 | ⛔ 受阻 |

> G9 说明：2026-07-28 由用户在 `https://kb.xuanbai.tech` 正式页面手工走完整用户链路完成验收。
> 本条记录依据用户确认，**台账内尚未落入 30 分钟 soak 的实测数值与 rollout/rollback 实测停机
> 时长**；`resources.compose.yaml` 中 api/worker 是否已由估算值替换为实测值待补证据。
>
> G10 说明：2026-07-28 标记受阻，用户确认当前无法推进。已知阻塞事实：线上证书由 Let's Encrypt
> DNS-01 手动签发，自动续期需要 DNS 服务商 API 凭据，或改用云厂商 1 年期免费证书。
> 解除条件待补充。证书 2026-10-25 到期，在此之前必须人工重签或解除阻塞。

**G8 期间发现并修复的缺陷（均为本机演练无法暴露、全部已加回归断言）：**

| # | 缺陷 | 本机不暴露的原因 |
| --- | --- | --- |
| 1 | `preflight` 漏检四个加密主密钥，容器启动才崩 | 本机 drill 的 secrets 恰好齐全 |
| 2 | 六处日志用 `extra=` 传字段被静默丢弃 | 本机排查可直接读源码倒推 |
| 3 | RAGFlow `up` 强制要求 `backend/.venv` | 开发机本来就有 |
| 4 | 内存门槛按 32 GiB 开发机硬编码为 24 GiB | 本机满足该门槛 |
| 5 | 数据卷声明为 external 却无人创建 | 本机卷是历史遗留 |
| 6 | 新建数据卷不设属主，ES/Valkey 因权限反复重启 | 本机卷当年走的是带 chown 的迁移分支 |
| 7 | 构建依赖 ghcr.io | 本机网络可达 |
| 8 | 构建依赖 pypi.org / registry.npmjs.org | 同上 |
| 9 | **`file_mode` 在 Linux 上完全失效**：GNU `stat -f` 是"显示文件系统信息"且退出码为 0，回退分支永不触发 | macOS 上该语法恰好正确 |
| 10 | 私钥 0600 导致以非 root 运行的 Edge 无法加载证书 | Colima 挂载语义宽松 |

其中第 9 项性质最严重：它是**双向失效**的安全检查——这次表现为误拦部署，反过来一个真正
0644、所有人可读的密钥文件同样会被判为合规。

**G8 期间确认的环境约束（非代码缺陷，已写入 runbook §0）：**

- 云厂商控制台防火墙与服务器内 ufw 是独立两层，轻量实例默认模板不含 443；
- 该实例境外出网被完全阻断（同机房另一台实例却正常，与地域无关），导致 ghcr.io/PyPI/npm/
  Let's Encrypt API 全部不可达，且 LE 验证节点也回连不了它的 80 端口，HTTP-01 无法使用；
- 云服务器访问不了自己的公网 IP（无 NAT 回环），因此 `verify_edge` 必须走回环，
  部署时不得设置 `COMMON_AGENT_PUBLIC_BASE_URL`；
- 证书签发顺序必须是"临时证书 → rollout → 正式证书 → 重建 Edge"，因为 ACME 验证要求
  80 端口已有服务应答。

**G4/G5 期间发现并修复的两个计划外缺陷：**

- 业务与 RAGFlow 的 compose 调用都写死了 `-f` 文件列表，资源覆盖片段**根本无法叠加**，
  配置文件形同摆设。已改为支持 `COMMON_AGENT_COMPOSE_OVERRIDE` / `RAGFLOW_COMPOSE_OVERRIDE`，
  只追加文件，不改变依赖解析路径。
- RAGFlow 的 `MACOS` 开关被硬编码为 1。该开关会跳过 `update_progress` 的分布式锁
  （upstream `api/db/services/task_service.py:398`），只适用于 macOS 开发机，**Linux 部署会让
  并发任务进度更新失去互斥**。已改为按 `uname` 判定；另删除 `manage.sh` 中一处不起作用的
  `MACOS=1`（官方 compose 并未引用该变量）。

**待解除的外部风险：**

- **Docker Hub 上锁定的 RAGFlow 基础镜像 digest 已失效。** `infiniflow/ragflow:v0.26.4` 是可变
  tag，被上游重新推送，`image.env` 锁定的 `sha256:e0048bb5…` 在 Docker Hub 返回 404
  `MANIFEST_UNKNOWN`（已用 `docker manifest inspect` 独立复核）。**华为云 SWR 上同一 digest 仍
  可用**，内容一致，故锁定值无需修改，服务器按 runbook §3 从该源拉取即可。后续可考虑给
  `image.sh` 增加显式备用源支持，避免依赖"华为云路径恰好包含原仓库名"这一字符串匹配巧合。
- **Docker 发布端口绕过 ufw**（走自己的 iptables 链）。本部署只有 Edge 有意绑 `0.0.0.0:80/443`，
  RAGFlow 全部端口须保持 `127.0.0.1`；runbook §9.2 提供了核查命令。

**排查中确认的两个既有缺陷（已在 G7 期间修复）：**

1. `preflight` 的 secrets 必填清单漏了四个加密主密钥, 导致检查通过、迁移完成、直到 rollout
   拉起容器才崩溃。单槽停机发布下这意味着旧容器已停、新容器起不来, 服务直接不可用。
2. 六处日志用 `logger.xxx(msg, extra={...})` 传结构化字段, 而 JsonLogFormatter 只读
   `record.structured_fields`, 这些字段全部被静默丢弃。表现是日志看似记录了 exception_type,
   实际只有一个光秃秃的事件名, 排查只能靠读源码倒推; 审计追加失败那处连操作类型和阶段都丢。
   已全部改用 `log_event()` 并新增契约测试锁死。

**drill 在本机不可重复运行（已知限制, 未修）：**

平台用 `COMMON_AGENT_RAGFLOW_IDENTITY_KEYS` 派生每个工作区在 RAGFlow 侧的账号密码, 而 drill
每次生成随机密钥、又与开发环境共用同一个 RAGFlow 实例。第二次起, 新密钥派生的密码与 RAGFlow
里已存的账号对不上, 身份初始化必然失败, 表现为知识库页"服务暂时不可用"。

本轮通过清理 RAGFlow 侧的冲突技术账号后重新部署验证: 身份记录 `status=active`、
`ragflow_tenant_id` 已绑定、凭据加密落库, 全程无告警。该轮使用空 legacy token 且 RAGFlow 侧
无历史账号, **等价于全新服务器的首次部署场景**。

若要让 drill 可重复, 需让其使用固定测试密钥或在退出时清理自建的 RAGFlow 账号, 属独立任务。

**本轮明确降低的门禁（经使用方决定）：**

- 使用方选择不在服务器上补做本机 drill 中的压测门禁（k6 读容量、SSE 128 路、Worker 崩溃接管、
  攻击矩阵）。按 1-3 人试用规模判断可接受；并发规模上升时需补做。

### 2.6 🅜 文档内嵌多媒体解析

> 分支：`embedded-media-parsing`。
> 目标：知识库上传的文档里内嵌的音视频，其内容能被解析成可检索文本，而不是像现在这样被静默丢弃。
> 产品边界依据：`docs/product-boundary.md` 3.3 知识库。

**调研已确认的事实（2026-07-28 实测，避免重复验证）：**

| # | 事实 | 证据 |
| --- | --- | --- |
| 1 | RAGFlow 的 `extract_embed_file` 对 PDF 直接返回空，只处理 ZIP(OOXML) 与 OLE 容器 | `rag/utils/file_utils.py:92-150`；对构造的内嵌视频 PDF 实测返回 `[]` |
| 2 | PPTX 视频以原始文件直存 `ppt/media/`，无 OLE 包装，关系类型 `relationships/media` + `relationships/video` | 用户真实 WPS 演示产出（含 1 个 `.mov` + 2 个 `.mp4`）与 python-pptx `add_movie` 产出结构一致 |
| 3 | 现有 `embed_dirs` 缺 `ppt/media/`、`word/media/`、`xl/media/`，真实 PPT 三个视频一个都捞不到 | 对该真实 PPT 跑 `extract_embed_file` 返回 `[]` |
| 4 | `word/embeddings/*.bin` 能捞到但递归时死在 `.bin`，ZIP 分支不做 Ole10Native 解包 | 构造样本实测；`_extract_ole10native_payload` 只在 OLE 容器分支使用 |
| 5 | `_guess_ext` 不认视频 magic，mp4 返回 `.bin` | 实测 |
| 6 | `extract_embed_file` 全仓库唯一调用点是 `rag/app/naive.py:932`；PPTX 默认走 `presentation.py`，naive 也无 pptx 分支 | grep 全仓库 + 读 `presentation.py:244` |
| 7 | 视频理解能力已具备且正是百炼：`QWenCV._process_video` 走 DashScope `MultiModalConversation`（fps=2），`dashscope==1.25.11` 已 pin | `rag/llm/cv_model.py:328-437` |
| 8 | 视频切片器已存在：`rag/app/picture.py:51` 的 `VIDEO_EXTS` 分支 | 读码 |
| 9 | 内嵌文件解析失败当前被静默吞掉，只 log 不提示用户 | `rag/app/naive.py:932-944` |
| 10 | 平台侧当前传不进 pptx：白名单只有 docx/md/markdown/pdf/txt，且 `MAX_DOCUMENT_SIZE_BYTES = 20MB` | `backend/src/common_agent/knowledge/service.py:40-48` |
| 11 | 单个内嵌视频可达 42MB（真实 PPT 中的 `.mov`） | 同上真实样本 |
| 12 | LibreOffice 不能用于造 Office 内嵌视频样本，其 OOXML 导出会丢弃媒体字节 | 实测：转出的 docx/xlsx 无任何 media 部件 |

**已决架构方向：** 提取逻辑从 `naive.py` 上提到 `task_executor` 层，让所有切片器共享；
但**逻辑放新文件** `rag/app/embedded_media.py`，`task_executor.py` 只留 import + 3~5 行 hook，
以控制与上游的冲突面（当前补丁集对 `task_executor.py` 是零改动）。

| ID | 任务 | 验收标准 | 状态 |
| --- | --- | --- | --- |
| M1 | 内嵌媒体提取模块（可验证落点） | 新建 `rag/app/embedded_media.py`：PDF 覆盖 `/Names/EmbeddedFiles`、`/Screen` Rendition、`/RichMedia`；Office 覆盖 `word\|xl\|ppt/media/` 直存；视频 magic 嗅探（mp4/mov/mkv 等）；只挖一层、按内容去重、非媒体条目不返回。逐条 RED→GREEN | ✅ 已完成 |
| M1b | Office OLE 包装内嵌媒体解包 | `word/embeddings/*.bin` 的 Ole10Native 解包（`_extract_ole10native_payload` 已存在但只用于 OLE 容器分支）。**当前受阻**：本机无可写 OLE 复合文件的库（olefile 0.47 只读、oletools 无样本），LibreOffice 也造不出，写不出失败测试就不能写实现。解除条件：拿到一份真实 Word/Excel 内嵌视频样本 | ⛔ 受阻 |
| M2 | 接入 task_executor | `task_executor.py` 加 hook，内嵌媒体对所有切片器一视同仁；chunk 归属父文档（`docnm_kwd` 用父文档名 + `【内嵌视频 xxx】`前缀 + 重新分词）；追加到尾部不破坏 `cks[0].__outline__`；默认关闭；单个媒体失败不阻断父文档且必须 callback 可见 | ✅ 已完成 |
| M3 | 闸门与失败可见性 | 单个视频大小上限、单文档视频数量上限、解析开关（默认关）；失败不阻塞主文档解析，但必须 callback 出用户可见提示，不再静默丢弃 | ⬜ 未开始 |
| M4 | 平台侧上传边界调整 | 上传白名单增加 pptx（及决定是否含 xlsx）、`MAX_DOCUMENT_SIZE_BYTES` 上调；前后端契约、错误文案与测试同步 | ⬜ 未开始 |
| M5 | 引用类型贯穿到前端标记 | `doc_type` 从 RAGFlow 检索结果贯穿到引用 chip：`adapters/knowledge/ragflow.py` 取值 → `RetrievedChunk` / `Citation` / `RuntimeKnowledgeChunk` 加字段 → `message_citations` 加列 + Alembic 迁移 → 重新生成 OpenAPI 与前端 DTO → `conversations.ts` Zod schema → `ChatMessages.tsx` 渲染视频标记 | ⬜ 未开始 |
| M6 | 镜像重建与安全基线 | 基于最终补丁 HEAD 重建 fork 镜像，更新 `image.env` 的标签、revision 与安全扫描基线 | ⬜ 未开始 |

> **补丁集同步不是独立任务。** `verify-patchset.sh` 要求 `PATCH_HEAD`/`PATCH_COMMITS` 精确匹配、
> 非测试文件必须登记进 `PRODUCTION_FILES`、远端分支锁到同一 HEAD，因此每次向 fork 提交都必须
> 在同一任务内更新 `infra/ragflow/patchset.env` 并跑通门禁，不能推迟。原 M6 中的这部分已并入各任务。
>
> **两个 RAGFlow 工作区的分工（易踩）**：`third_party/ragflow` 是 submodule，用于开发与提交；
> `.local/ragflow-fork` 是 fork 工具链的校验工作区，`fork.sh prepare` 只 fetch 远端追踪引用、
> **不会**快进本地分支。跑 `verify-patchset.sh` 前需先在该工作区 `merge --ff-only`。

**M1 执行记录（2026-07-28）**

- RED：`test/unit_test/rag/app/test_embedded_media.py` 15 个用例全部因 `ModuleNotFoundError:
  No module named 'rag.app.embedded_media'` 失败；
- GREEN：新增 `rag/app/embedded_media.py` 后 15 passed；`test/unit_test/rag/app/` 全包 29 passed；
- REFACTOR：`picture.py` 的 `VIDEO_EXTS` 改为引用共享常量，消除两处重复定义；改动前后 Ruff
  告警数完全一致（12 条，均为上游既有），无新增；
- 真实边界：用户提供的真实 WPS 演示 pptx（`media1.mov` 41.9MB + `media2.mp4` 4.4MB +
  `media3.mp4` 1.6MB，共 47MB）实测，改前 `extract_embed_file` 返回空，改后三个视频按原字节
  全部取出，图片与 XML 部件正确排除；
- 门禁：`infra/ragflow/verify-patchset.sh` 通过，`head=0457b8f104d6e22e9875698427ce430e22e608dc`；
- 遗留：本任务只交付提取模块，尚未接入任何解析链路，用户侧无可见变化——接入在 M2。

**M2 执行记录（2026-07-28）**

- **原计划的「从 naive.py 摘除旧逻辑」被证明不需要做**：核对后确认两个提取器覆盖范围完全不
  重叠——上游 `extract_embed_file` 只看 `word/embeddings/`、`word/objects/`、`word/activex/`、
  `xl/embeddings/`、`ppt/embeddings/`，本模块只看 `*/media/`，PDF 上游本就返回空。不存在重复
  提取，因此 `naive.py` 一行未改；
- RED：`chunk_embedded_media` 9 个用例 + `append_embedded_media_chunks` 4 个用例分两轮各自先
  失败（`ImportError`），再实现转 GREEN；
- GREEN：`test/unit_test/rag/app/` 42 passed；
- **上游改动量：`rag/svr/task_executor.py` 净增 12 行、删 0 行**（1 行 import + 1 处调用），
  全部逻辑在新文件 `rag/app/embedded_media.py` 内，把跟上游的冲突面压到最小；
- 默认关闭：`parser_config["parse_embedded_media"]` 为真才执行。整段视频要送多模态模型，
  不允许存在「合并后即产生非预期计费」的中间态；
- Ruff：`task_executor.py` 改动前后均 153 条（上游既有），无新增；`embedded_media.py` 16 条，
  类别与周边代码一致（BLE001/LOG015/S112），均不在项目 select 内；
- 回归口径：`test/unit_test/rag/svr` 与 `rag/app` 共 19 个测试文件**逐文件加 60s 超时**跑，
  干净树与改动树逐项对照完全一致。整目录一次性跑会被下面第一条上游缺陷拖住不出结果；
- **已知上游缺陷（非本次引入，干净树复现）**：
  1. `test/unit_test/rag/svr/task_executor_refactor/test_chunk_builder.py` **挂起**（主线程
     阻塞在 `_pthread_cond_wait`，60s 不结束）；
  2. `test/unit_test/rag/svr/task_executor_refactor/test_dataflow_service.py` 存在
     `SyntaxError: invalid escape sequence '\d'`，整文件收集失败；
  两条均已在未改动的干净树上复现，其余 13 个 svr 文件与 4 个 app 文件全部通过；
- 环境注意：`rag/app/picture.py` 模块级构造 `OCR()`，导入即触发 HuggingFace 模型下载（实测
  >120s、约 47MB 落到 gitignore 的 `rag/res/deepdoc`）。因此本模块对真实切片器采用延迟导入，
  测试通过注入替身切片器隔离；
- 遗留：真实链路仍未打通——闸门（M3）、平台上传边界（M4）、引用标记（M5）、镜像重建（M6）
  完成后才能由 M7 做端到端验收。用户侧目前仍无可见变化。
| M7 | 真实链路验收 | 正式 React 页面上传含内嵌视频的真实文档 → 真实 FastAPI → 私有补丁 RAGFlow → 百炼视频理解 → 知识库中检索得到该视频内容的片段，引用 chip 带视频标记；Playwright 用例入回归集 | ⬜ 未开始 |

**已决：引用呈现方案（用户 2026-07-28 确认）**

内嵌视频产出的 chunk 必须能看出出自哪份文档，并在引用上标出它来自视频：

- `docnm_kwd` 覆盖为**父文档名**，不用内嵌文件名。`doc_id` 在 `task_executor.py:375` 本就已是
  父文档 ID，无需改动；
- chunk 内容加前缀 `【内嵌视频 <文件名>】`，让用户展开片段时知道来源；
- chunk 保留 `doc_type_kwd="video"`（`picture.chunk` 现有行为），并贯穿到前端；
- `ChatMessages.tsx:216` 现按 `document_name` 去重渲染 chip。**同一文档只要有任一片段来自视频，
  该 chip 就带视频标记**，不因去重丢失信息，也不把一份文档拆成两个 chip。

**待定项（动手前需确认）：**

- 真实 Word / Excel 插入视频的落点未能验证（LibreOffice 不可用作代理，用户无法产出样本）。
  M1 采取「两种落点都覆盖」的方案规避，不赌单一结构；
- DashScope `MultiModalConversation` 对本地视频文件的大小/时长硬限制需查明，直接决定 M3 闸门取值；
- 视频摘要作为独立 chunk 入库（`picture.chunk` 现有行为），还是需与其在原文档中的位置绑定 —— 后者改动显著更大。

## 3. 当前下一步

D1~D16 与 U1 全部完成并推送。§2.5 的单机 demo 部署 G1~G9 已完成，
`https://kb.xuanbai.tech` 已上线可访问，功能链路已由用户在正式页面手工验收。

当前推进 §2.6 🅜 文档内嵌多媒体解析（分支 `embedded-media-parsing`），下一个任务为 M1。

V3 原定范围内已无待启动任务。当前挂起两项：

- **G10 证书自动续期（⛔ 受阻）**：用户确认暂时无法推进，解除条件待补充。证书 2026-10-25
  到期，在此之前必须人工重签或解除阻塞，不能漏。
- **G9 遗留证据待补**：30 分钟 soak 实测数值与 rollout/rollback 实测停机时长尚未落台账，
  `resources.compose.yaml` 中 api/worker 是否已替换为实测值待确认。

剩余待用户定夺 / 跟进的两项：

- **D12 模型版本号展示**：调研结论是百炼不提供可稳定展示的版本号（别名调用只回显别名，
  背后快照随季度漂移），当前卡片直接展示真实调用标识已是最准确做法。是否额外标注「底层
  代际」由用户决定，未擅自加。
- **工作流路由首屏被画布库拖大**（约 170KB，详见 `docs/development-roadmap-ui.md` 末节）：
  用户已明确表示暂不处理，保留记录备查。
