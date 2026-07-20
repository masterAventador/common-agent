# common-agent

`common-agent` 是一个面向本机开发的通用 AI Agent 中台。第一版优先跑通连续 AI 会话、数字员工、RAGFlow 知识库和最小可视化工作流，不包含登录鉴权、Skill 市场、企业多租户或远程部署。

## MVP 能力

- AI 会话：像常规聊天一样连续追问、流式回复、停止、重试和恢复历史；
- 数字员工：配置名称和系统指令，绑定一个知识库后自动检索再回答；
- 知识库：创建知识库、上传文档并查看 RAGFlow 解析状态；
- 工作流：拖拽开始、AI 对话、知识检索、结束四类节点，支持手动和数字员工触发。

## 技术栈

- 前端：React、TypeScript、Vite、Ant Design、React Flow；
- 后端：Python、FastAPI、SQLAlchemy async、Alembic；平台正式持久化使用独立 MySQL 8.4 LTS，技术方案不设白名单，可按真实需要引入 Redis、消息队列、对象存储、Worker 等其他组件；
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
以 12 GiB 运行，只启动平台 MySQL、FastAPI 和 Vite，不启动 RAGFlow，也不会调用百炼
embedding/rerank。真实知识库链路仍由后续 `real` 入口把同一 profile 重启到暂定 32 GiB 后验收，
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
pnpm；macOS 前后端进程使用项目专属 launchd 标签托管，`stop/clean` 不按模糊进程名停止其他项目。
`clean` 删除本入口的进程、容器、日志和已被 submodule 取代的旧 RAGFlow checkout，但保留
MySQL/RAGFlow 数据、依赖和官方镜像。

## 项目文档

- [产品范围](docs/product-scope.md)：只定义产品功能和边界；
- [开发路线图](docs/development-roadmap.md)：任务状态、完成标准和验证证据的唯一核对源；
- [工程结构](docs/project-structure.md)：目标目录和模块职责；
- [后端架构](docs/backend-architecture.md)：领域、接口、数据和适配层；
- [前端架构](docs/frontend-architecture.md)：路由、状态和交互约束；
- [项目主规则](CLAUDE.md)：开发、测试、验收与本地资源规则。
- [平台 MySQL 本机栈](infra/platform/README.md)：固定版本、隔离端口、Volume 和复用方式。
- [RAGFlow 本机栈](infra/ragflow/README.md)：固定版本、隔离端口、资源和复用方式。

具体任务状态和当前下一步只以开发路线图为准。
