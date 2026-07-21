# common-agent

`common-agent` 是一个面向本机开发的通用 AI Agent 中台。MVP 已跑通连续 AI 会话、数字员工、RAGFlow 知识库和最小可视化工作流；当前生产化阶段已增加安全会话、组织下多工作区、成员账号、Owner/Editor/Viewer 最小 RBAC、不可篡改审计、由 MySQL 持久队列和独立 Worker 承载的可恢复执行、认证加密备份，以及固定镜像、双节点 TLS、蓝绿发布和代码回滚演练。Skill 市场、SSO、细粒度授权和实际远程上线仍不在当前完成范围。

## MVP 能力

- AI 会话：像常规聊天一样连续追问、流式回复、停止、重试和恢复历史；
- 数字员工：配置名称和系统指令，绑定一个知识库后自动检索再回答；
- 知识库：创建知识库、上传文档并查看 RAGFlow 解析状态；
- 工作流：拖拽开始、AI 对话、知识检索、结束四类节点，支持手动和数字员工触发。

## 技术栈

- 前端：React、TypeScript、Vite、Ant Design、React Flow；
- 后端：Python、FastAPI、独立 Worker、SQLAlchemy async、Alembic；平台正式 MySQL 8.4 LTS 同时承载业务数据、持久任务和 SSE 事件序列，不额外引入 Redis/MQ；
- Agent：Deep Agents；
- 工作流：LangGraph / LangChain；
- 知识库：RAGFlow；
- 模型：阿里云百炼 OpenAI 兼容接口。

全部服务在本机运行。项目使用专属端口、Compose project、Volume 和 `.local/` 数据目录，避免影响本机其他项目。

## 克隆与第三方源码

RAGFlow 是项目直接消费其官方 Compose 的源码级依赖，作为 Git submodule 固定到已验收 commit：

```bash
git clone --recurse-submodules git@github.com:masterAventador/common-agent.git
```

已有工作区使用 `git submodule update --init --recursive` 初始化。普通 Python/npm 依赖仍分别由
`backend/uv.lock` 和 `frontend/pnpm-lock.yaml` 冻结，不能用未参与实际安装的源码副本冒充版本锁定。

## 日常轻量开发

64 GiB 日常开发机默认使用项目专属的 `demo-light`：同一个 `common-agent-dev` Colima profile
以 12 GiB 运行，只启动平台 MySQL、FastAPI、独立 Worker 和 Vite，不启动 RAGFlow，也不会调用百炼
embedding/rerank。真实知识库链路由 `real` 入口把同一 profile 重启到已验收的 32 GiB 后运行，
两种模式不会同时运行。

```bash
scripts/dev.sh doctor  # 检查工具链、冻结依赖、submodule 与当前资源状态
scripts/dev.sh setup   # 初始化 submodule，以锁文件安装后端和前端依赖
scripts/dev.sh up      # 切换到 12 GiB demo-light 并启动服务
scripts/dev.sh status
scripts/dev.sh stop
scripts/dev.sh clean
```

`up` 成功后访问前端 <http://127.0.0.1:18280>，后端 API 位于
<http://127.0.0.1:18200/api/v1>。脚本使用 `packageManager` 锁定的 pnpm 11.9.0，不修改本机全局
pnpm；macOS API、Worker 和前端进程使用项目专属 launchd 标签托管，`stop/clean` 不按模糊进程名停止其他项目。
`clean` 删除本入口的进程、容器、日志和已被 submodule 取代的旧 RAGFlow checkout，但保留
MySQL/RAGFlow 数据、依赖和官方镜像。

空数据库首次打开会进入“创建首位所有者”页面。一次性引导令牌由统一启动脚本在工作区内 Git
忽略的 `.local/dev/common-agent-dev/secrets/owner-bootstrap-token` 自动生成并以 `0600`
保存；两台开发电脑各自拥有本地值，不相互依赖。所有者创建成功后引导入口永久关闭。之后使用
邮箱和密码登录，浏览器只保存 `HttpOnly` 会话 Cookie，CSRF 令牌只保存在当前页面内存中。
首位所有者自动拥有默认工作区；可以创建同组织工作区并添加 Editor/Viewer 成员。业务资源、
事件和 RAGFlow 外部知识库归属按工作区隔离，跨租户 REST/SSE/工具调用由后端关闭失败。

Owner 可从“审计事件”入口查询当前工作区或平台级安全事件，并按操作者、动作、资源与时间过滤；
每个作用域使用独立 SHA-256 哈希链，数据库禁止更新或删除既有事件，页面可直接校验链完整性。
审计只保存固定元数据，不保存请求正文、密码、Token、恢复码、提示词或知识正文；默认保留期为
365 天、每个作用域最多 1,000,000 条，达到容量时关闭失败且不会自动删除。

## 真实知识链路

需要调试或验收 RAGFlow、Deep Agents 和百炼时使用统一 `real` 入口：

```bash
scripts/real.sh doctor  # 脱敏检查工具、源码、模型/区域、端口、磁盘和当前栈
scripts/real.sh setup   # 初始化 submodule 并按锁文件安装依赖
scripts/real.sh up      # 按需切到已验收的 32 GiB，启动完整稳定栈和前后端
scripts/real.sh status  # 检查容器重启/OOM、模型绑定、Token 和平台依赖
scripts/real.sh cost    # 显示调用/重试/数据边界、待迁移文档数和实时容器内存
scripts/real.sh stop    # 停止并释放 Colima 内存，保留容器、数据、Token 和镜像
```

`real` 不启动本地 embedding/rerank；文档向量化和检索重排固定调用北京百炼业务空间的
`text-embedding-v4` 与 `qwen3-rerank`。RAGFlow API Token 仅保存在 Git 忽略、权限 `0600` 的
项目本地文件中，体检、日志和费用诊断只输出是否存在，不输出值。RAGFlow 状态数据使用项目专属
Colima 原生 Volume，避免 macOS bind mount 在虚拟机重启后丢失容器 UID；旧 bind 数据首次迁移
后仍保留作回退。32 GiB 已通过 R8-04 完整冷启动、真实业务链路和 30 分钟专项验收：VM
峰值 6.91 GiB、容器合计峰值 6.85 GiB、Swap/重启/OOM 均为 0，因此确认为长期 `real`
默认值；日常 Demo 仍使用 12 GiB `demo-light`。

## 备份与恢复

`infra/backup/manage.sh` 统一备份平台 MySQL、RAGFlow MySQL/MinIO/Elasticsearch/Valkey 四个
停写 Volume、平台持有的外部知识库归属，以及非敏感部署配置。归档使用独立 `0600` 256-bit
密钥和 AES-256-GCM，内含文件大小与 SHA-256 清单；密钥、百炼 Key、RAGFlow Token、认证凭据
和数据库口令不进入归档。策略固定为 24 小时 RPO、120 分钟 RTO、30 天保留、至少 7 个代际，
每 90 天执行一次恢复演练。

```bash
infra/backup/manage.sh init-key
scripts/real.sh stop
infra/platform/manage.sh up
infra/backup/manage.sh backup
infra/backup/manage.sh drill
```

`restore` 和 `drill` 只允许 `common-agent-recovery-*` 空环境，拒绝覆盖正式容器、数据库和 Volume；
完整运维步骤、密钥分离与恢复前置条件见 [备份恢复说明](infra/backup/README.md)。

## 项目文档

- [产品范围](docs/product-scope.md)：只定义产品功能和边界；
- [开发路线图](docs/development-roadmap.md)：任务状态、完成标准和验证证据的唯一核对源；
- [工程结构](docs/project-structure.md)：目标目录和模块职责；
- [后端架构](docs/backend-architecture.md)：领域、接口、数据和适配层；
- [前端架构](docs/frontend-architecture.md)：路由、状态和交互约束；
- [项目主规则](CLAUDE.md)：开发、测试、验收与本地资源规则。
- [平台 MySQL 本机栈](infra/platform/README.md)：固定版本、隔离端口、Volume 和复用方式。
- [RAGFlow 本机栈](infra/ragflow/README.md)：固定版本、隔离端口、资源和复用方式。
- [备份恢复与灾演](infra/backup/README.md)：数据边界、加密、保留、RPO/RTO 和隔离恢复入口。
- [生产构建与回滚](infra/production/README.md)：双节点边界、采购基线、TLS、不可变 release、迁移、灰度与回滚。

具体任务状态和当前下一步只以开发路线图为准。
