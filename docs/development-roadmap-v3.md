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
  `docs/product-scope.md` 4.11（首个内置工具只有零费用的当前时间）。不是 2 个。
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
| G7 | 本机真实容器验证单槽改造 | 单槽 rollout 在真实容器上多次跑通；身份初始化在"空 legacy token + 无历史账号"下 status=active，等价复现全新服务器场景 | 🔍 待验收 |
| G8 | 服务器真实链路验收 | 正式页面走完整链路、30 分钟 soak 修正估算值、真实 rollout/rollback、证书签发与续期 | ⬜ 未开始 |

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

## 3. 当前下一步

D1~D16 与 U1 全部完成并推送。当前推进中的是 §2.5 的单机 demo 部署：G1~G6 已完成，
G7（本机 drill）进行中，G8（服务器真实链路验收）待服务器代码就位后执行。

剩余待用户定夺 / 跟进的两项：

- **D12 模型版本号展示**：调研结论是百炼不提供可稳定展示的版本号（别名调用只回显别名，
  背后快照随季度漂移），当前卡片直接展示真实调用标识已是最准确做法。是否额外标注「底层
  代际」由用户决定，未擅自加。
- **工作流路由首屏被画布库拖大**（约 170KB，详见 `docs/development-roadmap-ui.md` 末节）：
  用户已明确表示暂不处理，保留记录备查。
