# Backend

Python/FastAPI 后端工程。B1-01 会在此建立 Python 3.12、uv、`src` layout 和测试工具链，后续业务代码统一位于 `src/common_agent/`。

边界：

- 浏览器只调用本后端公开 API；
- 领域与应用层不依赖第三方 SDK；
- 数据库、中间件、模型、RAGFlow、Deep Agents 和 LangGraph 通过正式端口/适配层接入；
- 本目录不保存本机运行数据、上传文件、日志或除已授权百炼 Demo Key 外的凭据。
