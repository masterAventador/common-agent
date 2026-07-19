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
pnpm dev
```

开发服务器固定监听 `127.0.0.1:18280` 并启用 strict port；启动前仍须确认端口没有被其他项目占用。

API 默认访问 `http://127.0.0.1:18200/api/v1`，可通过 `VITE_API_BASE_URL` 覆盖。响应先经过生成 TypeScript 类型对应的 Zod 边界，后端错误统一转换为不含传输细节的 `ApiClientError`。

`/knowledge-bases` 是知识库正式页面：通过平台 API 创建知识库、上传 TXT/Markdown/PDF/DOCX，
并显示 RAGFlow 返回的 `uploaded`、`parsing`、`completed`、`failed` 状态。存在未完成文档时每
2 秒刷新后端快照；后端不可用、列表/文档加载失败和上传失败均提供明确错误或重试入口。前端
不保存 RAGFlow Token，也不直接请求 RAGFlow。
