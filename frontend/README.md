# Frontend

React/TypeScript/Vite/Ant Design 前端工程。F1-02 会在此建立应用、测试和构建工具链。

边界：

- 只通过统一 API/SSE 客户端访问 FastAPI；
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
pnpm dev
```

开发服务器固定监听 `127.0.0.1:18280` 并启用 strict port；启动前仍须确认端口没有被其他项目占用。

API 默认访问 `http://127.0.0.1:18200/api/v1`，可通过 `VITE_API_BASE_URL` 覆盖。响应先经过生成 TypeScript 类型对应的 Zod 边界，后端错误统一转换为不含传输细节的 `ApiClientError`。

`/knowledge-bases` 是知识库正式页面：通过平台 API 创建知识库、上传 TXT/Markdown/PDF/DOCX，
并显示 RAGFlow 返回的 `uploaded`、`parsing`、`completed`、`failed` 状态。存在未完成文档时每
2 秒刷新后端快照；后端不可用、列表/文档加载失败和上传失败均提供明确错误或重试入口。前端
不保存 RAGFlow Token，也不直接请求 RAGFlow。

`/employees` 是数字员工正式页面：通过平台 API 查看、新建和编辑数字员工，可选绑定一个
RAGFlow 知识库，并从卡片进入带 `employee_id` 的聊天入口。员工列表与知识库列表独立加载；
知识库暂不可用时仍能查看和编辑员工，已有失效绑定会明确标记，两个失败边界分别提供重试。
页面不直接请求 RAGFlow，也不包含行业或业务自动化字段。

`pnpm test:e2e` 是知识库浏览器闭环的唯一正式入口。它复用健康的项目 MySQL/RAGFlow 稳定
栈，临时启动正式 FastAPI/Vite 和 Playwright Chromium，验证创建、上传、完成、刷新恢复与
真实 RAGFlow 取消解析后的失败展示；入口会按锁定的 Playwright 版本检查 Chromium，已安装
版本直接复用、缺少时一次性下载；成功或失败都会停止临时进程并按唯一名称清理知识库。
