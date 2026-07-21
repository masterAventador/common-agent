# 备份、恢复与灾难演练

Common Agent 使用一份认证加密归档覆盖当前正式数据边界：

- 平台 MySQL 使用 `mysqldump --single-transaction` 逻辑备份，包含租户、认证摘要、审计链、员工、
  会话、工作流、持久任务/事件、Demo 上传和 RAGFlow 外部知识库归属；
- RAGFlow 停写后冷备其 MySQL、MinIO 上传对象、Elasticsearch 索引和 Valkey 状态四个专属 Volume；
- 额外导出平台持有的 `tenant_id -> knowledge_base_id` 外部引用清单；
- 部署配置只采集 `deployment-config.allowlist` 中的非敏感项和固定版本文件。百炼 Key、RAGFlow
  Token、会话/引导凭据、数据库口令和备份密钥都不进入归档，恢复前必须从独立密钥系统重新提供。

归档使用 256-bit 独立密钥和 AES-256-GCM；文件清单、大小、SHA-256 与加密头都经过认证。密钥文件
必须是普通 `0600` 文件并与归档分开、异地保管。默认本机路径仅用于演练：

```bash
infra/backup/manage.sh init-key
scripts/real.sh stop
infra/platform/manage.sh up
infra/backup/manage.sh backup
BACKUP_ARCHIVE_FILE=.local/backups/common-agent-YYYYMMDDTHHMMSSZ.cab \
  infra/backup/manage.sh verify
```

版本化策略定义 24 小时 RPO、120 分钟 RTO、30 天保留、至少 7 个代际和每 90 天一次恢复演练。
生产调度必须至少每日一次，成功后复制归档到与运行环境独立的受控存储并验证；只在超出 30 天且
仍保有最新 7 个代际时才删除本地旧归档。当前开发 MySQL 为避免 macOS bind mount 问题关闭了
binary log，因此恢复点是最近一次已验证归档，而不是任意时间点。

`restore` 只接受 `common-agent-recovery-<id>` 资源，要求目标 MySQL 数据库和四个 RAGFlow Volume
均为空且不存在，拒绝覆盖正式资源。`drill` 负责创建独立源与恢复环境、执行正式页面验证和精确
清理；任何远程生产部署仍属于 S10-07，未获用户明确指令不得执行。
