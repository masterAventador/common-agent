# RAGFlow 独立开发栈

本项目以 RAGFlow 官方稳定版
`v0.26.4@cb93883f3f8c975eecb2fed81210effeb3bdb06f` 为不可漂移基线，正式依赖锁定私有 fork
`21eb8fb4001421f2952ce3125e46e753825d3f9b`，禁止使用 `latest` 或漂移分支。
`third_party/ragflow` Git submodule 通过相对 URL 指向 `masterAventador/common-agent-ragflow`，因此会
跟随父仓库所用 SSH/HTTPS 协议；`manage.sh` 只读取该锁定目录，不读取 `.local/ragflow-fork` 开发
工作区。fork commit、官方 tag/基线、origin、工作区或镜像 revision 任一不匹配时都会关闭失败。

## 私有补丁仓库

私有仓库为 `masterAventador/common-agent-ragflow`。它不是 GitHub 的公开 fork 关系，而是权限独立的
私有镜像：`main` 和 `v0.26.4` 永久固定官方基线提交，所有经基准和测试审查的改动只进入
`common-agent/v0.26.4-minimal`。`infra/ragflow/fork.env` 是仓库、版本和分支的单一元数据源；
`fork.sh` 在 Git 忽略的 `.local/ragflow-fork` 创建补丁工作区，将私有仓库设为 `origin`，将官方
仓库设为只读 `upstream`，并禁止 upstream push。

另一台电脑具备该私有仓库的 SSH 权限并完成 `gh auth login` 后，执行：

```bash
infra/ragflow/fork.sh prepare
infra/ragflow/fork.sh verify
infra/ragflow/fork.sh verify-remote
infra/ragflow/fork.sh status
bash infra/ragflow/test-fork.sh
bash infra/ragflow/test-patchset.sh
infra/ragflow/verify-patchset.sh
```

`verify-remote` 同时校验 GitHub 仓库仍为 private、默认分支仍为 `main`、官方与私有 tag 指向同一
基线、私有 `main` 未漂移，以及远端补丁分支仍包含基线。补丁开发只在 `.local/ragflow-fork`
完成并推送，不直接在 detached 的 `third_party/ragflow` 中开发；该 submodule 只消费已回归、已推送
的精确 fork commit。

本机通过父仓库同一 SSH/HTTPS 凭据解析相对 submodule URL。可选 GitHub Actions 若要递归检出两个
私有 sibling 仓库，需要把同时只读授权这两个仓库的细粒度 Token 保存为
`COMMON_AGENT_REPOSITORIES_TOKEN`；本机权威验收不依赖该 Secret 或 Hosted Runner。

`patchset.env` 固定补丁基线、最终提交、有序提交栈、允许改动目录、4 个生产文件白名单、升级审计目标
及冲突集合；`verify-patchset.sh` 同时检查本地与远端补丁头、线性历史、工作区洁净和 `merge-tree`
冲突集。当前最小补丁与锁定的官方 `main` 审计快照无冲突；任何提交顺序、生产文件、远端提交或升级
冲突集合漂移都会关闭失败。

性能补丁候选必须让基准源码、预期 Git commit 和镜像 OCI revision 三者一致，并显式使用
`patched` 源码审计模式；正式栈固定使用本地可复现的 fork 覆盖镜像。基准运行器沿用 R2-01 的规模
档位和报告变量，以保证补丁前后可以直接比较：

```bash
COMMON_AGENT_RAGFLOW_BENCHMARK_SOURCE="$PWD/.local/ragflow-fork" \
COMMON_AGENT_RAGFLOW_BENCHMARK_EXPECTED_COMMIT="$(git -C .local/ragflow-fork rev-parse HEAD)" \
COMMON_AGENT_RAGFLOW_BENCHMARK_SOURCE_MODE=patched \
COMMON_AGENT_RAGFLOW_BENCHMARK_IMAGE_REVISION="$(git -C .local/ragflow-fork rev-parse HEAD)" \
COMMON_AGENT_R2_01_REPORT_PATH="$PWD/.local/benchmarks/candidate/baseline.json" \
  scripts/ragflow-v0264-baseline.sh
```

运行器会按源码模式分别记录官方 JOIN 查询或补丁后的独立计数、分页 ID、页内详情和定向删除
`EXPLAIN ANALYZE`，并校验写入、检索、删除后不可见、资源采样和隔离数据清理。候选镜像如何构建与
正式镜像由 `Dockerfile.fork` 从锁定官方 digest 起步，只覆盖 submodule 的完整 `api/rag` 目录；
`DOC_BULK_SIZE=32` 及 task/chunk/embedding 并发 `5/1/8` 由 common-agent 的
`compose.override.yaml` 注入，RAGFlow 自带 `docker/` 保持官方原样。构建不下载、不重解依赖，也不
允许仅靠环境变量把未提交源码变成项目依赖。外围 Elasticsearch、MySQL、MinIO、Valkey 继续使用
官方镜像，但 Compose 从 `image.env` 读取已审阅的精确 digest，不再依赖可变 tag。

R2-06 补丁集回归报告必须来自 `patchset.env` 固定的最终提交，分别覆盖 25 万行列表/定向删除、
真实批量写入与 embedding 并发、合法和越界检索及 12k 切片读取。执行
`scripts/ragflow-v0264-patchset-check.sh` 会统一校验性能阈值、SQL 扫描行数、删除后不可见、清理、
五个基础容器存活以及 Swap/重启/OOM 边界，并生成 Git 忽略的汇总报告。

## 使用

```bash
git submodule update --init --recursive third_party/ragflow
colima start common-agent-dev --cpus 8 --memory 32 --disk 100 --root-disk 20 \
  --runtime docker --vm-type vz --vz-rosetta --activate=false
infra/ragflow/manage.sh prepare
infra/ragflow/manage.sh pull-image
infra/ragflow/manage.sh verify-image
infra/ragflow/manage.sh scan-image
infra/ragflow/manage.sh migrate-native-volumes
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
bash infra/ragflow/test-patchset.sh
bash infra/ragflow/test-image.sh
```

固定开发栈 Compose project name 为 `common-agent-dev`。普通开发和定向测试复用该栈，
不因 FastAPI 或 React 改动重建 RAGFlow；`stop` 停止服务但保留容器，`down` 删除容器和
网络但保留数据。Elasticsearch、MySQL、MinIO 和 Valkey 状态使用项目专属 Colima 内的原生
Docker Volume，日志位于被 Git 忽略的 `.local/dev/common-agent-dev/ragflow/data/logs/`，私有 fork
checkout 位于 `third_party/ragflow` submodule。只有改动 RAGFlow 版本、submodule 指针、Compose
或存储时才重建整栈；任务镜像清理不得删除仍由稳定栈使用的 fork 镜像或其官方固定基底。

旧版外围层曾把四个数据卷 bind 到 macOS `.local/`。VZ/virtiofs 在 Colima 重启后会把这些文件
重新映射为容器内 `root:root`，导致 MySQL 无法写 binlog；旧 MySQL 还使用只能在大小写不敏感
文件系统启动的 `lower_case_table_names=2` 数据字典。`migrate-native-volumes` 因此先停止并仅在
首次迁移时重建旧外围容器，
对 Elasticsearch/MinIO/Valkey 做只读复制；MySQL 旧卷先只读复制到 Git 忽略的迁移快照，再以
同版本 MySQL 启动该快照，逻辑导出 `rag_flow` 后导入新的原生 v3 Volume。旧 bind 目录、旧
Volume、迁移快照和物理复制 v2 均不删除，可用于回退；目标卷带就绪标记，重复 `real up` 只
复用，不重复迁移。

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
`OpenAI-API-Compatible` 能力的两个独立实例调用阿里百炼 `text-embedding-v4` 与
`qwen3-rerank`。管理脚本默认要求
Docker context 至少 24GiB，并建议项目独立 profile 使用 8 CPU、32GiB 内存和 100GiB 容器磁盘。

非本地模型容器上限为：RAGFlow 5GiB、Elasticsearch 3GiB（JVM 1GiB）、MySQL 2GiB、MinIO
1GiB、Valkey 256MiB。`configure-bailian` 从获准的后端 Demo 配置或同名环境变量读取百炼 Key，
只通过 RAGFlow 官方 UI/API 注册两个模型并设置租户默认值，不打印凭据；`check-bailian` 只报告
embedding、rerank 和默认绑定是否就绪。新知识库显式固定
`text-embedding-v4@common-agent-embedding@OpenAI-API-Compatible`，平台检索显式固定
`qwen3-rerank@common-agent-rerank@OpenAI-API-Compatible`。

这里的 `OpenAI-API-Compatible` 只是 RAGFlow 到同一个阿里百炼供应商的传输适配，不是模型
网关，也没有引入第二家模型供应商。v0.26.4 的 Python Provider API 在新建
`Tongyi-Qianwen` 实例时会遍历静态模型目录，并因其中尚不支持的 OCR 类型返回错误码 102；本项目
不修改上游源码、镜像或数据库，而是只经 v0.26.4 公开 Provider/Model API 创建两个独立兼容实例：
embedding 使用百炼官方 `compatible-mode/v1/embeddings`，rerank 使用百炼官方
`compatible-api/v1/reranks`。实例、模型类型、默认绑定和真实请求均由关闭失败的配置与适配器
测试核对。

从其他 embedding 迁移已有知识库时，必须先更新知识库模型并通过 RAGFlow 官方重建入口重新
向量化全部文档，再执行中文召回与重排基准；不得复用旧向量冒充迁移成功。32GiB 已通过路线图
R8-04 的完整业务峰值与 30 分钟稳定性门禁，并在 S10-07A 升级 v0.26.4 后以 180 个连续样本再次
验证 VM/容器峰值 7.28/7.23GiB、Swap/重启/OOM 为 0，因此继续作为长期 `real` 默认值；日常 Demo
仍不应启动本栈。

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

迁移在任何写操作前拒绝仍在解析的文档；更新模型后使用 RAGFlow v0.26.4 公开文档重建 API，
保留原始文件并等待所有文档进入完成态。中断、限流、超时或解析失败会返回脱敏阶段码，可在上游
恢复后使用同一命令重新执行，不需要修改 RAGFlow 数据库或源码。等待上限默认 3600 秒，可通过
`RAGFLOW_BAILIAN_MIGRATION_TIMEOUT_SECONDS` 在 1-86400 秒内调整。

Apple Silicon 使用 `linux/amd64` fork 覆盖镜像并由独立 Colima VZ/Rosetta 环境运行。`pull-image`
先验证 submodule、官方基底 digest、OCI 标签和补丁文件哈希；镜像已存在且完全匹配时复用，否则从
锁定官方基底本地重建。四个外围服务保持原生 arm64，并由各自精确 digest 固定：

```bash
infra/ragflow/manage.sh pull-image
infra/ragflow/manage.sh verify-image
infra/ragflow/manage.sh scan-image
```

从 v0.25.6 升级到 v0.26.4 时保持四个原生数据卷不变，停止服务后先创建冷备份，且禁止执行
`docker compose down -v`。v0.26.4 官方入口会在 API 启动前执行数据库 schema 同步和模型供应商表
迁移；首次启动后必须检查迁移日志、版本端点、既有数据集/文档和真实检索，再清理临时回滚资源。
后续升级仍必须作为独立路线图任务：同步修改 submodule 指针、`VERSION`、`UPSTREAM_COMMIT`、
`patchset.env` 与 `image.env`，运行配置契约、镜像安全扫描、正式适配器契约和完整纵向链路回归；
禁止直接修改 detached submodule 或运行中容器，补丁只能在已锁定基线的版本化私有分支中维护。
