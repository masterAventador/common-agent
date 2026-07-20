# 平台基础设施

这里管理 common-agent 自有的稳定基础设施，不复用 RAGFlow 内部数据库，也不使用其他项目的
容器、网络、端口或 Volume。B1-05 首先加入平台 MySQL，后续缓存、队列、对象存储和 Worker
只有在路线图任务产生真实需要时才扩展同一管理边界。

## MySQL

- 官方镜像固定为 `mysql:8.4.10`，属于 MySQL 8.4 LTS 系列；
- Docker context 固定为 `colima-common-agent-dev`；
- 容器名为 `common-agent-platform-mysql`；
- 仅绑定 `127.0.0.1:19506`，与 RAGFlow 自带的 `127.0.0.1:19432` 完全分离；
- 数据 Volume 为 `common-agent-platform-mysql-data`，实际目录位于
  `.local/dev/common-agent-dev/platform/mysql`；
- 从另一个 Git 克隆调用管理脚本时，如果这个专属 Volume 已存在，脚本读取并复用其原始 bind
  目录，不按新克隆路径请求重建；显式指定的目录与现有绑定冲突时关闭失败，数据迁移必须另设
  有备份的任务；
- 本机开发不做复制或时间点恢复，关闭 binary log，避免 macOS bind mount 在容器重启时因
  `binlog.index` 权限同步产生瞬态启动失败；事务恢复仍由 InnoDB redo/undo 保证；
- 默认开发数据库/用户为 `common_agent`，仅用于本机 loopback 开发链路。
- `manage.sh up` 会幂等准备 `common_agent_test` 并授予同一本机开发用户访问权限；pytest 和
  测试 Uvicorn 只连接该测试库，不写入 `common_agent` 演示/开发数据。

```bash
infra/platform/manage.sh check-ports
infra/platform/manage.sh pull-image
infra/platform/manage.sh up
infra/platform/manage.sh status
infra/platform/manage.sh stop
```

稳定栈跨任务复用；普通后端测试不得重复重建 MySQL。`down` 只删除容器和网络，不删除
Volume/数据目录。版本升级、数据清理或删除 Volume 必须作为明确任务单独验收。

日常 64 GiB 开发机优先从仓库根目录执行 `scripts/dev.sh up`：统一入口会把同一个项目专属
Colima profile 切换到 12 GiB，只启动平台 MySQL 和 Demo 前后端。需要完整 RAGFlow 时再由 real
入口切回暂定 32 GiB，两种模式不得并行。

配置门禁：

```bash
infra/platform/test-manage.sh
shellcheck infra/platform/manage.sh infra/platform/test-manage.sh
```

版本依据：[MySQL 8.4 LTS 发布模型](https://dev.mysql.com/doc/refman/8.4/en/mysql-releases.html)、
[MySQL 8.4 Release Notes](https://dev.mysql.com/doc/relnotes/mysql/8.4/en/)。
