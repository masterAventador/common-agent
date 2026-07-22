# Scripts

保存跨前后端且有明确调用方的生成、启动、验收和清理脚本。

脚本必须：

- 从统一配置读取端口和路径；
- 只操作可确认属于 `common-agent` 的进程、容器、镜像和数据；
- 失败时返回非零状态，不吞掉真实错误；
- 被相关自动化测试或任务门禁直接调用。

当前脚本：

- `dev.sh`：macOS 本机统一 `demo-light` 入口，提供 `doctor/setup/up/status/stop/clean`；复用项目
  专属 `common-agent-dev` Colima profile，但会在停止完整 real 栈后将其重启为 12 GiB，只启动
  平台 MySQL、Demo FastAPI、独立持久任务 Worker 和 Vite。前端依赖始终以 `npx pnpm@11.9.0`
  按锁文件安装，不改全局 pnpm；API/Worker/前端使用精确 launchd 标签管理，并在 Git 忽略的项目专属 `secrets/` 目录自动生成
  `0600` 首次所有者引导令牌，清理保留数据库数据、冻结依赖和官方镜像；
- `test-dev.sh`：检查统一入口动作、12 GiB 资源边界、Demo 适配器、固定 pnpm、项目专属进程标签
  和精确清理契约；
- `real.sh`：macOS 本机统一 `real` 入口，提供 `doctor/setup/up/status/cost/stop`；按需把同一项目
  profile 切到暂定 32 GiB，复用平台 MySQL、官方 RAGFlow 原生 Volume 与镜像，通过 0600 本地
  文件向 FastAPI 与独立 Worker 传递 RAGFlow Token，并对百炼区域、模型绑定、重试、费用和外发数据边界做脱敏
  诊断；与 demo-light 复用同一 Git 忽略的本地所有者引导令牌，不启动本地 embedding/rerank；
- `test-real.sh`：检查 real 入口动作、32 GiB/context、官方 RAGFlow、原生数据卷、百炼绑定、
  Token 文件、费用脱敏、本地模型退场，以及仅允许 `common_agent`/`common_agent_test` 的数据库
  选择与 API/Worker 子进程透传契约；
- `real-resource-soak.sh`：在 `common_agent_test` 隔离业务库和受控测试认证状态中启动完整 real
  链路，执行真实 RAGFlow 生命周期与浏览器 MVP 后持续采样 30 分钟 VM/容器资源、Swap、重启、
  OOM 和健康状态；成功或失败均重置测试认证、停止本轮业务进程并保留脱敏报告用于核对；
- `test-real-resource-soak.sh`：静态检查 soak 只能使用隔离测试库、显式 API/认证变量、受控状态
  初始化与清理，并保持 32 GiB、峰值、Swap、重启/OOM 和完整业务链门禁；
- `test-ci.sh`：检查本机权威命令在 PR/main GitHub CI 可选镜像中的冻结安装、固定 Action、
  后端/前端/契约/Demo/基础设施门禁、缓存锁文件边界，以及 real 外部付费依赖不进入公共
  Runner 的隔离契约；项目验收不依赖 Hosted Runner、付费额度或远端执行结果；
- `coverage.sh`：本机权威覆盖率入口，提供 `backend/frontend/all`；后端合并正式 Uvicorn
  子进程后同时检查总体与 `domain/application` 核心层行/分支基线，报告写入 Git 忽略的
  `.local/coverage/backend`；前端固定 pnpm 11.9.0，通过 Vitest V8 检查行/分支基线；
- `test-coverage.sh`：检查覆盖率依赖、生产代码范围、六项不回退阈值、报告忽略和可选 CI
  复用本机入口的契约；
- `test-frontend-bundle.sh`：对隔离构建 fixture 故障注入，证明前端分析器会拒绝超过 500,000
  bytes 的单 JS chunk、超过 1,500,000 bytes 的单路由首次 JS 图、缺失 manifest 或六路由入口；
- `security-scan.sh`：本机权威安全门禁，`source` 使用现有凭据指纹门禁、Semgrep `p/default`、
  Trivy 文件系统与生产 IaC 扫描，`images` 扫描指定 API/Web 业务镜像中已有修复版本的
  High/Critical 漏洞和 Secret，`all` 串行执行两者；默认使用项目专属 Docker context，要求本机
  已安装 Semgrep、Trivy、jq 与 shasum。已应用迁移中的固定 SQL 例外必须同时匹配精确文件指纹、
  规则、路径和行号，禁止宽泛排除迁移目录；
- `test-security-scan.sh`：以隔离假工具验证安全门禁的扫描范围、第三方源码和授权 Demo Key 例外、
  已审阅静态 SQL 复扫、镜像前缀、参数校验与失败透传；可选 CI 只执行该无网络契约，真实扫描仍
  由 S10-08 本机正式构建验收执行；
- `generate-contracts.sh`：从正式 FastAPI 应用导出 OpenAPI 并生成前端 TypeScript 类型；
- `check-contracts.sh`：在隔离临时目录重建契约并检查已提交文件无漂移；
- `test-platform-e2e.sh`：复用健康的稳定基础设施，以无窗口 `chromium-headless-shell` 编排正式
  FastAPI、独立 Worker 与 Vite；认证、Demo、生产首屏和分页套件使用 12 GiB 轻量档，真实 RAGFlow 套件使用
  32 GiB 档；若正在运行的专属 Colima 档位不符，会先精确停止本项目两套 Compose 再切换。默认
  `platform` 套件验收真实 RAGFlow/Deep Agents/百炼路径，设置
  `COMMON_AGENT_E2E_SUITE=auth` 时在隔离认证状态中验证首位所有者、登录、恢复、CSRF、跨源、
  会话撤销与 Cookie 重放失败；设置 `COMMON_AGENT_E2E_SUITE=tenant-rbac` 时验证工作区、成员、
  Viewer 只读和跨租户拒绝；设置 `COMMON_AGENT_E2E_SUITE=audit` 时验证 Owner 审计查询、链完整性、
  策略边界和固定脱敏元数据；设置
  `COMMON_AGENT_E2E_SUITE=demo-chat` 时只启用显式 Demo 固定适配器，验证两轮会话、引用、断流
  和 Worker 自动重试；设置 `COMMON_AGENT_E2E_SUITE=frontend-loading` 时构建并启动生产 preview，验证六入口
  首屏/交互与第二轮切换不重复请求 JS；设置 `COMMON_AGENT_E2E_SUITE=workflow-designer` 时只验收 React Flow 拖拽、连线、
  服务端校验、真实知识库引用与 MySQL 保存/刷新回显；设置
  `COMMON_AGENT_E2E_SUITE=workflow-run-ui` 时通过正式页面验收真实百炼完成、协作停止、真实
  RAGFlow 失效失败和刷新摘要恢复；设置 `COMMON_AGENT_E2E_SUITE=model-configurations` 时通过
  生产 preview、正式 API/MySQL 和真实百炼验收模型创建、验证、刷新、停用与引用安全删除；设置
  `COMMON_AGENT_E2E_SUITE=generic-chat-models` 时从模型管理页创建配置，再从空白通用会话首次
  发送原子建会话、逐轮切换真实百炼模型并验证刷新恢复。各套件
  都负责唯一测试数据、预置测试 Seed、本轮
  Playwright/前后端进程和成功产物清理；`COMMON_AGENT_E2E_DOCKER_CONTEXT` 可让同一脚本在
  GitHub Runner 的 `default` Docker context 下运行 Demo 门禁。
- `test-platform-e2e-contract.sh`：静态检查轻量/真实 E2E 的 12/32 GiB 分档、运行中内存探测和
  切档前的项目栈精确停止边界。

平台/RAGFlow 备份恢复属于 `infra/backup/` 的基础设施边界，不在 `scripts/` 建立第二套入口；
`infra/backup/manage.sh drill` 会编排正式 API、独立 Worker、Vite 和无头 Chromium，并在源环境
销毁后验证空 recovery 环境中的真实 RAGFlow 文档、员工绑定与审计链。
