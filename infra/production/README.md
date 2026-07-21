# 生产构建、双节点部署与回滚

本目录交付 S10-07 的生产同路径：固定 digest 的最小权限镜像、业务节点蓝绿槽、显式 Alembic
迁移、TLS 入口、健康验证、故障恢复和代码回滚。当前只在项目专属本机 Colima 中完成验收，**没有
连接、创建或修改任何远程资源**；第一次远程发布仍须用户再次明确授权。

## 推荐拓扑与资源

生产默认使用两个故障域：

- 业务节点：Edge、Web、API、Worker 和平台 MySQL；只通过私网 HTTPS 调用 RAGFlow；
- RAGFlow 节点：官方 RAGFlow 栈及独立 TLS Edge；只向业务节点所在私网开放 HTTPS。

当前业务 Compose 会在切换窗口同时运行蓝绿 API/Web，并短时并存两个 Worker。采购口径固定如下：

| 节点 | 承载组件 | 不接受 | 最低起步规格 | 推荐采购规格 | 系统盘/数据盘 | 采用依据 |
| --- | --- | --- | --- | --- | --- | --- |
| 业务节点 | Edge、Web、蓝绿 API、蓝绿 Worker、平台 MySQL | 4C4G | 4C16G | **8C16G** | SSD 不低于 100GB | 需要同时容纳迁移、MySQL、蓝绿切换和上一 release 回滚余量 |
| RAGFlow 节点 | RAGFlow API、Elasticsearch、MySQL、MinIO、Valkey、TLS Edge | 4C4G | 4C16G | **8C32G** | SSD 不低于 100GB，并按文档量扩容数据盘 | [RAGFlow 官方最低要求](https://github.com/infiniflow/ragflow#self-hosting)为 4C16G/50GB；本项目真实栈按 8C32G/100GB 长期验收 |

明确采购建议是：正式首发购买 **8C16G 业务节点 + 8C32G RAGFlow 节点**。预算受限时可以分别以
4C16G 起步，但只能用于低并发首发，并且必须先通过 S10-08 容量、长连接和故障压测。现有 4C4G
不承载业务核心或 RAGFlow，可保留作堡垒机、监控或其他轻量外围用途。若未来把平台 MySQL 拆为
托管数据库，业务节点规格必须在 S10-08 重新实测，不能直接据此下调。

本机 R8-04 的 30 分钟真实链路中，相关容器合计峰值约 6.85 GiB，RAGFlow API 单项峰值约
4.16 GiB；这些数据证明 32G 有充足稳定余量，但不能把当前低数据量峰值误当成 8G 生产规格，
因为远程环境仍需覆盖索引增长、解析峰值、宿主机和滚动发布余量。

业务节点和 RAGFlow 节点不得共享服务端私钥。业务节点只保存自己的 Edge 私钥与用于验证 RAGFlow
的 CA bundle；RAGFlow 私钥只保存在 RAGFlow 节点。MySQL 只加入 Docker internal 网络；API/Worker
另加入受宿主机防火墙约束的 egress 网络，以访问私网 RAGFlow 与百炼。两个节点间使用私网 DNS/IP、
网络 ACL 和正式 CA 证书，不向公网暴露 RAGFlow、MySQL 或容器管理端口。

## 本机权威演练

本机演练使用 `local-shared-network` 覆盖层模拟两节点，但应用请求仍经 RAGFlow HTTPS Edge，
不会直连其 HTTP API：

```bash
infra/production/manage.sh drill
```

演练会依次构建两个不可变 release、向前迁移数据库、蓝绿切流、通过正式 Chromium 验收五个入口、
注入 active API 故障并回滚。退出时停止生产演练与按需启动的 RAGFlow 容器，删除临时状态、凭据和
演练 MySQL Volume，保留可复用的固定镜像与 RAGFlow 稳定数据。

## RAGFlow 节点

先按 [`infra/ragflow/README.md`](../ragflow/README.md) 启动固定 v0.25.6 栈。为 TLS Edge 准备
正式证书，证书 SAN 必须覆盖业务配置使用的私网 DNS 名；再将下列变量替换为目标机绝对路径和
RAGFlow 所在 Docker network：

```bash
export COMMON_AGENT_RAGFLOW_EDGE_CONFIG=/opt/common-agent/infra/production/ragflow-edge.conf
export COMMON_AGENT_RAGFLOW_CERT=/etc/common-agent/tls/ragflow.crt
export COMMON_AGENT_RAGFLOW_KEY=/etc/common-agent/tls/ragflow.key
export COMMON_AGENT_RAGFLOW_NETWORK=common-agent-dev_ragflow
export COMMON_AGENT_RAGFLOW_HTTPS_BIND=10.0.0.12
export COMMON_AGENT_RAGFLOW_HTTPS_PORT=9443
docker compose -p common-agent-production-ragflow-edge \
  -f infra/production/ragflow-node.compose.yaml up -d
```

只允许业务节点访问 `10.0.0.12:9443`。`ragflow-node.local.compose.yaml` 仅供本机 drill，远程节点
禁止使用它。

## 业务节点配置

以 `env.example` 创建非敏感 `config.env`，至少把 `COMMON_AGENT_CORS_ORIGINS` 与
`RAGFLOW_BASE_URL` 改成实际 HTTPS 地址。另建 `secrets.env`，填入示例列出的全部键并设为
`0600`。密码进入数据库 URL 前必须 URL encode；文件不得提交、复制到镜像或输出到日志。

在状态目录的 `tls/` 中预置：

- `edge.crt`、`edge.key`：业务域名正式证书与私钥；
- `ca.crt`：验签证书；
- `ca-bundle.crt`：系统 CA 加上 RAGFlow 私有 CA，挂入 API/Worker。

业务节点不需要 `ragflow.key`。`init-tls` 只生成 30 天自签名材料供本机 drill，禁止用于远程生产。

示例环境边界：

```bash
export COMMON_AGENT_PRODUCTION_DOCKER_CONTEXT=default
export COMMON_AGENT_PRODUCTION_STATE_ROOT=/var/lib/common-agent/production
export COMMON_AGENT_PRODUCTION_CONFIG_FILE=/etc/common-agent/config.env
export COMMON_AGENT_PRODUCTION_SECRETS_FILE=/etc/common-agent/secrets.env
export COMMON_AGENT_RAGFLOW_EDGE_MODE=external
export COMMON_AGENT_PUBLIC_DOMAIN=agent.example.com
export COMMON_AGENT_PUBLIC_BASE_URL=https://agent.example.com
export COMMON_AGENT_HTTPS_BIND=0.0.0.0
export COMMON_AGENT_HTTPS_PORT=443
```

如果使用非本机 Docker context，管理脚本会关闭失败，直到额外提供精确确认值
`COMMON_AGENT_REMOTE_DEPLOY_CONFIRMATION=deploy-common-agent-to-approved-remote`。该确认只解除
context 防误触，不代表已经获得本项目首次远程发布授权，也不会自动采购、创建或修改云资源。

## 发布与回滚顺序

在已批准的业务节点工作副本中执行：

```bash
infra/production/manage.sh build
infra/production/manage.sh preflight
infra/production/manage.sh migrate
infra/production/manage.sh rollout
infra/production/manage.sh verify
infra/production/manage.sh status
```

`build` 将当前 Git revision 构建为本机不可变 `sha256` 镜像清单。`migrate` 只执行显式
`alembic upgrade head`；迁移必须保持至少前后两个 release 的向后兼容。`rollout` 先启动候选
API/Web，健康后切换 Edge 并验证公开 HTTPS、real 状态与 RAGFlow，再启动候选 Worker，最后停止
旧槽。

发布后若应用故障：

```bash
infra/production/manage.sh rollback
infra/production/manage.sh verify
```

回滚只恢复上一份代码镜像与流量，不自动执行 `alembic downgrade`。如果 schema 不兼容，必须先
按独立变更流程恢复兼容性，不能让脚本猜测性降级数据。正式发布前还应完成异地加密备份并验证
恢复点，步骤见 [`infra/backup/README.md`](../backup/README.md)。

停止当前编排但保留平台 MySQL Volume：

```bash
infra/production/manage.sh down
```

S10-08 将在采购规格与目标网络确定后补容器/SAST 扫描、攻击测试、并发与长连接压测、SLO、告警
和最终新租户全链路验收；完成这些门禁前，本目录不能被解释为已经上线。
