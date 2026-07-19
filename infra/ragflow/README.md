# RAGFlow 独立开发栈

本项目固定使用 RAGFlow 官方稳定版 `v0.25.6`，并同时固定官方 tag 对应提交
`8f0632c8d9efacbcd11aaf6e0f4cb634169bfea4`，禁止使用 `latest` 或漂移分支。
`manage.sh` 把未修改的官方 checkout 放到
`.local/dev/common-agent-dev/ragflow/upstream/`，本项目只维护外围 Compose 覆盖层，
不复制、Fork 或修改 RAGFlow 源码和官方 Compose。

## 使用

```bash
infra/ragflow/manage.sh prepare
infra/ragflow/manage.sh pull-image
infra/ragflow/manage.sh check-ports
infra/ragflow/manage.sh up
infra/ragflow/manage.sh status
infra/ragflow/manage.sh config
infra/ragflow/manage.sh logs
infra/ragflow/manage.sh stop
infra/ragflow/manage.sh down
bash infra/ragflow/test-manage.sh
```

固定开发栈 Compose project name 为 `common-agent-dev`。普通开发和定向测试复用该栈，
不因 FastAPI 或 React 改动重建 RAGFlow；`stop` 停止服务但保留容器，`down` 删除容器和
网络但保留数据。数据、日志和官方 checkout 全部位于被 Git 忽略的
`.local/dev/common-agent-dev/ragflow/`。只有改动 RAGFlow 版本、Compose 或存储时才重建
整栈；任务镜像清理不得删除仍由稳定栈使用的官方镜像。

## 端口与隔离

所有端口只绑定 `127.0.0.1`：

| 服务 | 端口 |
| --- | ---: |
| RAGFlow REST API | `19380` |
| RAGFlow Web HTTP / HTTPS | `19381` / `19387` |
| RAGFlow Admin | `19382` |
| RAGFlow MCP | `19383` |
| Go Admin / HTTP | `19384` / `19385` |
| 本地 embedding | `19386` |
| Valkey | `19379` |
| Elasticsearch | `19200` |
| MySQL | `19432` |
| MinIO | `19900` / `19901` |

平台只连接 REST API `http://127.0.0.1:19380`，不得连接 RAGFlow 内部数据库、缓存、
检索引擎或对象存储。每个端口都可用同名 `RAGFLOW_*_PORT` 环境变量传入新的纯数字端口；
管理脚本在首次启动前拒绝已被占用或非法的端口，不会停止其他项目进程。

## 资源策略

官方最低要求是 4 核、16GB RAM 和 50GB 磁盘；`v0.25.6` 镜像不包含 embedding
模型。当前开发机 Docker Desktop 可用约 31.28GiB，现有其他项目容器实测约占 2.2GiB，
属于 32GB 级配置但运行多语言 `BAAI/bge-m3` 时余量较紧。为保证中文知识检索，稳定栈
默认启用官方 `tei-cpu` profile 和 `BAAI/bge-m3`，不静默降级到英文模型。

容器上限为：embedding 24GiB、RAGFlow 5GiB、Elasticsearch 3GiB（JVM 1GiB）、
MySQL 2GiB、MinIO 1GiB、Valkey 256MiB。上限不是预留量，可以超过虚拟机总量；
K2-03 首次真实解析会记录启动峰值和稳定占用。当前 32GB 级配置用于首次验证；若出现
OOM 或内存压力，Docker Desktop 应提高到 48GiB，而不是裁剪必需服务、降低验收范围或
改用不适合中文的 embedding。宿主机有 128GB RAM，可为 Docker 提高资源后仍保留充足余量。

Apple Silicon 使用官方 `linux/amd64` 镜像并由 Docker Desktop 仿真。镜像已存在时
`pull-image` 直接复用；下载 Docker Hub 不稳定时，可通过官方 tag 对应镜像源覆盖：

```bash
RAGFLOW_IMAGE_SOURCE=swr.cn-north-4.myhuaweicloud.com/infiniflow/ragflow:v0.25.6 \
  infra/ragflow/manage.sh pull-image
```

升级必须作为独立路线图任务：修改 `VERSION` 与 `UPSTREAM_COMMIT`，运行配置契约、正式
适配器契约和完整纵向链路回归；禁止在 `.local/` 内维护上游补丁。
