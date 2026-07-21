# Infrastructure

保存本项目在本机使用的正式基础设施配置和运行说明。RAGFlow、数据库、中间件、存储、Worker 或其他技术依赖只有在路线图任务实际采用后才加入，统一使用 `common-agent` 名称前缀、项目专属端口和 `.local/` 数据目录。

本目录不复制第三方项目源码，也不保存本机 Volume 数据或凭据。

- [`ragflow/`](ragflow/)：固定官方版本、外围 Compose 覆盖层、稳定开发栈管理入口和配置门禁。
- [`platform/`](platform/)：平台独立 MySQL 的固定版本、专属端口、Volume 和生命周期入口。
- [`backup/`](backup/)：平台/RAGFlow 认证加密归档、保留策略、空 recovery 环境恢复和正式页面灾演。
- [`production/`](production/)：固定 digest 镜像、双节点 TLS 边界、蓝绿发布、显式迁移、故障演练和代码回滚。
