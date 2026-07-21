# Frontend

React/TypeScript/Vite/Ant Design 前端工程。

边界：

- 只通过统一 API/SSE 客户端访问 FastAPI；
- 未认证时只展示首位所有者引导、登录或恢复入口，认证成功后才挂载业务路由；
- 不直连阿里百炼、RAGFlow、Deep Agents 或 LangGraph；
- 用户交互以会话和消息为核心，工作流保持独立入口；
- 不提前创建未进入路线图的菜单、页面和空 Feature。

## 工具链

```bash
pnpm install --frozen-lockfile
pnpm test
pnpm lint
pnpm typecheck
pnpm build
pnpm test:e2e
pnpm test:e2e:demo
pnpm test:e2e:deletion
pnpm dev
```

开发服务器固定监听 `127.0.0.1:18280` 并启用 strict port；启动前仍须确认端口没有被其他项目占用。

API 默认访问 `http://127.0.0.1:18200/api/v1`，可通过 `VITE_API_BASE_URL` 覆盖。响应先经过生成 TypeScript 类型对应的 Zod 边界，后端错误统一转换为不含传输细节的 `ApiClientError`。

`AuthGate` 在业务 Query 和路由挂载前读取服务端会话状态。浏览器使用 `HttpOnly` Cookie 发送
身份凭据，脚本不可读取会话令牌；CSRF 令牌只保存在 React 内存状态，刷新后重新从会话接口获取。
REST 写请求携带 CSRF，原生 EventSource 显式启用 credentials；收到 `401` 时统一清空认证状态
和业务 Query，回到登录页。首位所有者恢复码仅在创建或重置成功页显示一次。

`/knowledge-bases` 是知识库正式页面：通过平台 API 创建知识库、上传 TXT/Markdown/PDF/DOCX，
并显示 RAGFlow 返回的 `uploaded`、`parsing`、`completed`、`failed` 状态。存在未完成文档时每
2 秒刷新后端快照；后端不可用、列表/文档加载失败和上传失败均提供明确错误或重试入口。前端
不保存 RAGFlow Token，也不直接请求 RAGFlow。

`/employees` 是数字员工正式页面：通过平台 API 查看、新建和编辑数字员工，可选绑定一个
RAGFlow 知识库、从正式工作流列表多选允许调用项，并从卡片进入带 `employee_id` 的聊天入口。
员工、知识库与工作流列表独立加载；任一选项服务暂不可用时只禁用对应字段，已有绑定和授权数量
仍明确展示并提供独立重试。页面不直接请求 RAGFlow，也不包含行业或业务自动化字段。

`/chat` 是连续会话工作台：左侧按当前数字员工展示和新建历史会话，中间通过正式 REST/SSE
发送消息、显示流式回复与引用并支持停止和重试，右侧展示员工、知识库绑定和系统指令。当前员工
和会话 ID 保存在 URL；事件只按严格递增序号更新服务端消息快照，连接中断时重新读取正式历史，
整页刷新后可恢复回答和引用。EventSource 在切换会话或卸载页面时显式关闭。

`pnpm test:e2e` 是平台浏览器闭环的唯一正式入口。它复用健康的项目 MySQL/RAGFlow 稳定栈，
临时启动正式 FastAPI/Vite 和 Playwright `chromium-headless-shell`：知识库链路验证创建、上传、
完成、刷新恢复与真实 RAGFlow 取消解析后的失败展示；数字员工链路验证创建知识库、创建并绑定
员工、刷新恢复和编辑，再从正式聊天页面新建会话，经过真实 RAGFlow、Deep Agents 与阿里百炼
观察流式内容、停止、重试、引用和刷新恢复。入口只运行不会创建桌面窗口的无头浏览器；已安装
版本直接复用、缺少时一次性下载。成功、失败或中断都会关闭本轮浏览器/前后端进程，并按唯一名
称依次清理会话、员工、预置 Seed 和知识库。

`pnpm test:e2e:demo` 复用同一无头入口，但后端显式运行 `demo` 模式且不启动 RAGFlow：页面会
持续显示“演示模式”，用固定知识与运行时适配器验证两轮连续会话、每轮引用、一次运行时断流、
失败后重试和刷新恢复。该套件负责快速、可重复的协议与页面回归，不能替代真实外部依赖验收。

`pnpm test:e2e:deletion` 运行 real 模式的四资源删除闭环：页面创建知识库、工作流、数字员工和
会话，验证引用阻断与员工解绑，再从四个正式入口确认删除并在刷新后检查资源消失。成功或失败都
按本轮唯一名称执行兜底清理；清理器不准备数据、不解除引用，也不能代替待验收的用户操作。
