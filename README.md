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
