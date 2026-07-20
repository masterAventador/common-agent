# RAGFlow 独立开发栈

本项目固定使用 RAGFlow 官方稳定版 `v0.25.6`，并同时固定官方 tag 对应提交
`8f0632c8d9efacbcd11aaf6e0f4cb634169bfea4`，禁止使用 `latest` 或漂移分支。
未修改的官方 checkout 以 `third_party/ragflow` Git submodule 纳入父仓库，`manage.sh` 只读取
该目录；本项目只维护外围 Compose 覆盖层，不复制、Fork 或修改 RAGFlow 源码和官方 Compose。
commit、tag、origin 或工作区任一不匹配时管理脚本都会关闭失败。

## 使用

```bash
git submodule update --init --recursive third_party/ragflow
colima start common-agent-dev --cpus 8 --memory 32 --disk 100 --root-disk 20 \
  --runtime docker --vm-type vz --vz-rosetta --activate=false
infra/ragflow/manage.sh prepare
infra/ragflow/manage.sh pull-image
infra/ragflow/manage.sh check-ports
infra/ragflow/manage.sh up
infra/ragflow/manage.sh configure-bailian
infra/ragflow/manage.sh check-bailian
infra/ragflow/manage.sh plan-bailian-migration
infra/ragflow/manage.sh status
infra/ragflow/manage.sh config
infra/ragflow/manage.sh logs
infra/ragflow/manage.sh stop
infra/ragflow/manage.sh down
bash infra/ragflow/test-manage.sh
```

固定开发栈 Compose project name 为 `common-agent-dev`。普通开发和定向测试复用该栈，
不因 FastAPI 或 React 改动重建 RAGFlow；`stop` 停止服务但保留容器，`down` 删除容器和
网络但保留数据。数据和日志位于被 Git 忽略的 `.local/dev/common-agent-dev/ragflow/`，官方
checkout 位于 `third_party/ragflow` submodule。只有改动 RAGFlow 版本、submodule 指针、Compose
或存储时才重建整栈；任务镜像清理不得删除仍由稳定栈使用的官方镜像。

管理脚本默认固定使用 Docker context `colima-common-agent-dev`。该 context 来自同名独立
Colima profile，不会改变全局当前 context，也不会与其他项目共享 Docker 镜像存储、
容器、网络或 Volume。`RAGFLOW_DOCKER_CONTEXT` 只用于配置契约等显式测试场景覆盖，
正式开发栈不得指向其他项目正在使用的 context。

## 端口与隔离

所有端口只绑定 `127.0.0.1`：

| 服务 | 端口 |
| --- | ---: |
| RAGFlow REST API | `19380` |
| RAGFlow Web HTTP / HTTPS | `19381` / `19387` |
| RAGFlow Admin | `19382` |
| RAGFlow MCP | `19383` |
| Go Admin / HTTP | `19384` / `19385` |
| Valkey | `19379` |
| Elasticsearch | `19200` |
| MySQL | `19432` |
| MinIO | `19900` / `19901` |

平台只连接 REST API `http://127.0.0.1:19380`，不得连接 RAGFlow 内部数据库、缓存、
检索引擎或对象存储。每个端口都可用同名 `RAGFLOW_*_PORT` 环境变量传入新的纯数字端口；
管理脚本在首次启动前拒绝已被占用或非法的端口，不会停止其他项目进程。

## 资源策略

官方最低要求是 4 核、16GB RAM 和 50GB 磁盘。本项目不再启动 `tei-cpu`，也不维护本地
embedding/rerank 权重、端口、挂载或下载入口；知识库统一通过 RAGFlow 官方
`Tongyi-Qianwen` 能力调用阿里百炼 `text-embedding-v4` 与 `qwen3-rerank`。管理脚本默认要求
Docker context 至少 24GiB，并建议项目独立 profile 使用 8 CPU、32GiB 内存和 100GiB 容器磁盘。

非本地模型容器上限为：RAGFlow 5GiB、Elasticsearch 3GiB（JVM 1GiB）、MySQL 2GiB、MinIO
1GiB、Valkey 256MiB。`configure-bailian` 从获准的后端 Demo 配置或同名环境变量读取百炼 Key，
只通过 RAGFlow 官方 UI/API 注册两个模型并设置租户默认值，不打印凭据；`check-bailian` 只报告
embedding、rerank 和默认绑定是否就绪。新知识库显式固定
`text-embedding-v4@Tongyi-Qianwen`，平台检索显式固定 `qwen3-rerank@Tongyi-Qianwen`。

从其他 embedding 迁移已有知识库时，必须先更新知识库模型并通过 RAGFlow 官方重建入口重新
向量化全部文档，再执行中文召回与重排基准；不得复用旧向量冒充迁移成功。32GiB 是否作为长期
real 默认值仍以路线图 R8-04 的峰值和稳定性门禁为准，日常 Demo 不应启动本栈。

迁移先执行只读预检，输出知识库、文档、待更新模型和正在解析的文档数量，不输出知识正文、名称
或凭据：

```bash
infra/ragflow/manage.sh plan-bailian-migration
```

重建会重新调用百炼 embedding，产生外部数据传输、API 费用和限流风险，因此没有默认确认值。
确认预检结果、费用和数据边界后才显式执行；可用逗号分隔的知识库 ID 缩小范围：

```bash
RAGFLOW_BAILIAN_MIGRATION_DATASET_IDS=dataset-id-1,dataset-id-2 \
RAGFLOW_CONFIRM_BAILIAN_REINDEX=yes \
  infra/ragflow/manage.sh migrate-bailian
```

迁移在任何写操作前拒绝仍在解析的文档；更新模型后使用 RAGFlow v0.25.6 公开文档重建 API，
保留原始文件并等待所有文档进入完成态。中断、限流、超时或解析失败会返回脱敏阶段码，可在上游
恢复后使用同一命令重新执行，不需要修改 RAGFlow 数据库或源码。等待上限默认 3600 秒，可通过
`RAGFLOW_BAILIAN_MIGRATION_TIMEOUT_SECONDS` 在 1-86400 秒内调整。

Apple Silicon 使用官方 `linux/amd64` 镜像并由独立 Colima VZ/Rosetta 环境运行。镜像已存在时
`pull-image` 直接复用；下载 Docker Hub 不稳定时，可通过官方 tag 对应镜像源覆盖：

```bash
RAGFLOW_IMAGE_SOURCE=swr.cn-north-4.myhuaweicloud.com/infiniflow/ragflow:v0.25.6 \
  infra/ragflow/manage.sh pull-image
```

升级必须作为独立路线图任务：同步修改 submodule 指针、`VERSION` 与 `UPSTREAM_COMMIT`，运行
配置契约、正式适配器契约和完整纵向链路回归；禁止修改 submodule 或维护上游补丁。
