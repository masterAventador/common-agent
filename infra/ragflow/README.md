# RAGFlow 独立开发栈

本项目固定使用 RAGFlow 官方稳定版 `v0.25.6`，并同时固定官方 tag 对应提交
`8f0632c8d9efacbcd11aaf6e0f4cb634169bfea4`，禁止使用 `latest` 或漂移分支。
`manage.sh` 把未修改的官方 checkout 放到
`.local/dev/common-agent-dev/ragflow/upstream/`，本项目只维护外围 Compose 覆盖层，
不复制、Fork 或修改 RAGFlow 源码和官方 Compose。

## 使用

```bash
colima start common-agent-dev --cpus 12 --memory 48 --disk 100 --root-disk 20 \
  --runtime docker --vm-type vz --vz-rosetta --activate=false
infra/ragflow/manage.sh prepare
infra/ragflow/manage.sh pull-image
infra/ragflow/manage.sh check-model
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
模型。真实首次启动发现共享 Colima 的 30GiB 内容分区已经被其他项目占满，因此本项目
使用独立 profile：12 CPU、48GiB 内存、100GiB 容器磁盘。为保证中文知识检索，稳定栈
默认启用官方 `tei-cpu` profile 和 `BAAI/bge-m3`，不静默降级到英文模型。

TEI 运行时固定为 Hugging Face 官方
`ghcr.io/huggingface/text-embeddings-inference:cpu-1.8`。模型以只读 bind mount 从
`.local/dev/common-agent-dev/ragflow/models/BAAI/bge-m3` 挂载到容器 `/data/BAAI/bge-m3`，
避免把 4GB 级权重重复塞进 Docker 内容分区。`check-model` 会在启动前验证模型配置和
权重文件；模型缺失时必须从官方 Hugging Face 仓库准备，不得自动换成其他模型。

容器上限为：embedding 24GiB、RAGFlow 5GiB、Elasticsearch 3GiB（JVM 1GiB）、
MySQL 2GiB、MinIO 1GiB、Valkey 256MiB。K2-03 首次真实解析记录启动峰值和稳定占用；
若仍出现 OOM 或内存压力，应提高独立 profile 资源，而不是裁剪必需服务、降低验收范围
或改用不适合中文的 embedding。宿主机有 128GB RAM，48GiB profile 不影响现有 32GiB
默认 profile 并行运行。

Apple Silicon 使用官方 `linux/amd64` 镜像并由独立 Colima VZ/Rosetta 环境运行。镜像已存在时
`pull-image` 直接复用；下载 Docker Hub 不稳定时，可通过官方 tag 对应镜像源覆盖：

```bash
RAGFLOW_IMAGE_SOURCE=swr.cn-north-4.myhuaweicloud.com/infiniflow/ragflow:v0.25.6 \
  infra/ragflow/manage.sh pull-image
```

升级必须作为独立路线图任务：修改 `VERSION` 与 `UPSTREAM_COMMIT`，运行配置契约、正式
适配器契约和完整纵向链路回归；禁止在 `.local/` 内维护上游补丁。
