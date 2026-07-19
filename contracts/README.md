# Contracts

保存由后端生成并由前端消费的跨端契约：

- OpenAPI 快照；
- 会话与工作流流式事件 Schema；
- 跨端契约样例和漂移检查输入。

Pydantic 模型是协议唯一来源。本目录不维护与后端并行的手写 DTO。

生成和检查：

```bash
bash scripts/generate-contracts.sh
bash scripts/check-contracts.sh
```

生成脚本从正式 FastAPI app factory 导出 OpenAPI，再生成前端 TypeScript 类型；检查脚本在隔离临时目录重建并逐字节比较，发现漂移返回非零状态。
