# Scripts

保存跨前后端且有明确调用方的生成、启动、验收和清理脚本。

脚本必须：

- 从统一配置读取端口和路径；
- 只操作可确认属于 `common-agent` 的进程、容器、镜像和数据；
- 失败时返回非零状态，不吞掉真实错误；
- 被相关自动化测试或任务门禁直接调用。

当前脚本：

- `generate-contracts.sh`：从正式 FastAPI 应用导出 OpenAPI 并生成前端 TypeScript 类型；
- `check-contracts.sh`：在隔离临时目录重建契约并检查已提交文件无漂移；
- `test-platform-e2e.sh`：复用健康的稳定基础设施，以无窗口 `chromium-headless-shell` 编排正式
  FastAPI/Vite；默认 `platform` 套件验收真实 RAGFlow/Deep Agents/百炼路径，设置
  `COMMON_AGENT_E2E_SUITE=demo-chat` 时只启用显式 Demo 固定适配器，验证两轮会话、引用、断流
  和重试；设置 `COMMON_AGENT_E2E_SUITE=workflow-designer` 时只验收 React Flow 拖拽、连线、
  服务端校验、真实知识库引用与 MySQL 保存/刷新回显。各套件都负责唯一测试数据、预置测试
  Seed、本轮 Playwright/前后端进程和成功产物清理。
