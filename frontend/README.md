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
