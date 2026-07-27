# 单台 4C16G 服务器 Demo 部署 Runbook

面向一台 4C16G / 100GB+ SSD / x86_64 / Ubuntu LTS 的公网服务器，提供
`https://kb.xuanbai.tech` 的客户试用环境。

设计依据：`docs/superpowers/specs/2026-07-27-single-node-demo-deployment-design.md`

与两节点生产方案共用同一份 `compose.yaml` 与 `manage.sh`，差异只在配置值：
`COMMON_AGENT_RAGFLOW_EDGE_MODE=local-shared-network` 让 RAGFlow Edge 同时挂进业务私网与
RAGFlow 私网，业务侧通过 Docker 网络访问它，不需要跨主机私网。

## 0. 本部署的固定事实

| 项 | 值 |
| --- | --- |
| 公网域名 | `kb.xuanbai.tech` |
| 发布槽 | 固定 `blue`，停机发布（见 §5） |
| 对外端口 | 仅 22 / 80 / 443 |
| RAGFlow | 五个容器均不映射宿主机端口，只经内部 TLS Edge 访问 |
| 备份 | 不做备份流程（使用方已确认 demo 数据可丢） |

## 1. 服务器准备

### 1.1 安装 Docker

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker ubuntu   # 重新登录后生效
sudo systemctl enable --now docker
```

**国内节点注意：** `download.docker.com` 可能完全不可达。此时改用云厂商维护的官方 `docker-ce`
仓库镜像（例如腾讯云 `mirrors.tencentyun.com/docker-ce`），**不要**退回 Ubuntu 仓库的
`docker.io`（版本偏旧）。换源后务必核对 GPG 指纹为 Docker 官方值：

```
9DC8 5822 9FC7 DD38 854A  E2D8 8D81 803C 0EBF CD88
```

验证：`docker version` 与 `docker compose version` 均正常，且 `ubuntu` 用户免 sudo 可用 docker。

### 1.2 镜像加速与日志轮转

```bash
sudo tee /etc/docker/daemon.json >/dev/null <<'JSON'
{
  "registry-mirrors": ["https://mirror.ccs.tencentyun.com"],
  "log-driver": "json-file",
  "log-opts": { "max-size": "50m", "max-file": "3" }
}
JSON
sudo systemctl restart docker
```

本项目镜像全部以 sha256 digest 锁定，加速器只做缓存不改变内容，digest 校验依然有效。
日志轮转是必需的：不加会让容器日志无上限增长吃满磁盘。

### 1.3 swap 扩到 4 GiB

```bash
sudo swapoff /swap.img
sudo fallocate -l 4G /swap.img
sudo chmod 600 /swap.img
sudo mkswap /swap.img
sudo swapon /swap.img
swapon --show
```

确认 `/etc/fstab` 中 swap 条目是**路径形式**（`/swap.img none swap sw 0 0`）。若是 UUID 形式，
`mkswap` 后 UUID 变化会导致重启后挂载失败，需同步更新。

### 1.4 防火墙

```bash
sudo ufw allow 22/tcp && sudo ufw allow 80/tcp && sudo ufw allow 443/tcp
sudo ufw --force enable
```

**启用前必须先放行 22，否则会把自己锁在外面。** 启用后立刻另开一个终端验证 SSH 仍可连接。
云厂商安全组需要同步放行这三个端口。

> **⚠️ Docker 会绕过 ufw。** Docker 通过自己的 iptables 链发布端口，任何 `-p` 映射到
> `0.0.0.0` 的端口都会直接暴露到公网，**ufw 规则拦不住**。本部署只有 Edge 有意绑
> `0.0.0.0:80/443`；RAGFlow 全部端口必须保持绑定 `127.0.0.1` 或不映射。部署后用
> §9.2 的命令核查。

### 1.5 基础工具与目录

```bash
sudo apt-get install -y git curl openssl certbot
sudo mkdir -p /opt/common-agent /var/lib/common-agent/production /etc/common-agent
sudo chown ubuntu:ubuntu /opt/common-agent /var/lib/common-agent/production /etc/common-agent
sudo chmod 750 /etc/common-agent
```

## 2. 代码上机

主仓库与 RAGFlow submodule 都是私有仓库，需要先给服务器配置访问权限：

```bash
ssh-keygen -t ed25519 -C "common-agent-demo-server" -f ~/.ssh/id_ed25519 -N ''
cat ~/.ssh/id_ed25519.pub
```

把输出的公钥加到 GitHub 账号（Settings → SSH and GPG keys）。用账号级 key 而非单仓库
deploy key，因为需要同时访问主仓库和 `common-agent-ragflow` submodule。然后：

```bash
git clone --recurse-submodules git@github.com:masterAventador/common-agent.git /opt/common-agent
cd /opt/common-agent && git submodule status   # 确认 submodule 已就位
```

## 3. RAGFlow 基础镜像

> **⚠️ Docker Hub 上锁定的 digest 已失效。** `infiniflow/ragflow:v0.26.4` 是可变 tag，被上游
> 重新推送过，仓库锁定的 `sha256:e0048bb5…` 在 Docker Hub 已返回 404 `MANIFEST_UNKNOWN`。
> 华为云 SWR 上**同一个 digest 仍然可用**，内容完全一致，因此锁定值无需修改。

在跑 `image.sh` 之前，先手工把基础镜像拉到位：

```bash
docker pull --platform linux/amd64 \
  swr.cn-north-4.myhuaweicloud.com/infiniflow/ragflow@sha256:e0048bb5ee60f8bcd2e9a2c4851de80f39a0b7318ad4e55bf7bbcef126eaa9ac
docker tag \
  swr.cn-north-4.myhuaweicloud.com/infiniflow/ragflow@sha256:e0048bb5ee60f8bcd2e9a2c4851de80f39a0b7318ad4e55bf7bbcef126eaa9ac \
  infiniflow/ragflow:v0.26.4
```

验证 `image.sh` 的 digest 校验会通过（其判据是 RepoDigests 包含锁定值，华为云路径天然包含）：

```bash
docker image inspect infiniflow/ragflow:v0.26.4 --format '{{json .RepoDigests}}'
```

输出须包含 `infiniflow/ragflow@sha256:e0048bb5…` 子串。之后 `image.sh ensure` 会因
`image inspect` 成功而跳过拉取，直接构建 fork 镜像。

## 4. 环境变量

写入 `/etc/common-agent/deploy.env`，每次操作前 `source`：

```bash
export COMMON_AGENT_PRODUCTION_DOCKER_CONTEXT=default
export COMMON_AGENT_PRODUCTION_STATE_ROOT=/var/lib/common-agent/production
export COMMON_AGENT_PRODUCTION_CONFIG_FILE=/etc/common-agent/config.env
export COMMON_AGENT_PRODUCTION_SECRETS_FILE=/etc/common-agent/secrets.env
export COMMON_AGENT_RAGFLOW_EDGE_MODE=local-shared-network
export COMMON_AGENT_RAGFLOW_NETWORK=common-agent-dev_ragflow
export COMMON_AGENT_PUBLIC_DOMAIN=kb.xuanbai.tech
export COMMON_AGENT_PUBLIC_BASE_URL=https://kb.xuanbai.tech
export COMMON_AGENT_HTTPS_BIND=0.0.0.0
export COMMON_AGENT_HTTPS_PORT=443
export COMMON_AGENT_HTTP_BIND=0.0.0.0
export COMMON_AGENT_HTTP_PORT=80
export COMMON_AGENT_CERTBOT_EMAIL=<你的邮箱>
export COMMON_AGENT_COMPOSE_OVERRIDE=/opt/common-agent/infra/production/demo-single-node/resources.compose.yaml
export RAGFLOW_DOCKER_CONTEXT=default
export RAGFLOW_COMPOSE_OVERRIDE=/opt/common-agent/infra/production/demo-single-node/ragflow-resources.compose.yaml
# 部署机不安装后端开发依赖, 因此显式提供百炼原生地址（在开发机执行
# `uv run python -m common_agent.adapters.knowledge.ragflow_models native-base-url` 取得）。
export RAGFLOW_DASHSCOPE_HTTP_BASE_URL=<百炼原生地址, 形如 https://ws-xxxx.cn-beijing.maas.aliyuncs.com/api/v1>
```

再按 `config.env.example` 建 `/etc/common-agent/config.env`。

`secrets.env` 需要 12 个键，其中 4 个是应用在 production 下**强制要求的加密主密钥**，
缺任一项容器会在启动时崩溃。它们必须是 **URL-safe base64 的 32 字节**
（`settings.py` 用 `altchars=b"-_"` 且 `validate=True`，标准 base64 的 `+` `/` 会被拒绝）：

```bash
DB_PASSWORD="$(openssl rand -hex 24)"
DB_ROOT_PASSWORD="$(openssl rand -hex 24)"
TOOL_KEY="$(openssl rand -base64 32 | tr '+/' '-_')"
IDENTITY_KEY="$(openssl rand -base64 32 | tr '+/' '-_')"

umask 077
cat > /etc/common-agent/secrets.env <<EOF
MYSQL_ROOT_PASSWORD=${DB_ROOT_PASSWORD}
MYSQL_DATABASE=common_agent
MYSQL_USER=common_agent
MYSQL_PASSWORD=${DB_PASSWORD}
COMMON_AGENT_DATABASE_URL=mysql+aiomysql://common_agent:${DB_PASSWORD}@platform-mysql:3306/common_agent?charset=utf8mb4
COMMON_AGENT_AUTH_BOOTSTRAP_TOKEN=$(openssl rand -hex 32)
RAGFLOW_API_KEY=
BAILIAN_API_KEY=<百炼 API Key>
COMMON_AGENT_TOOL_CREDENTIAL_KEYS=v1:${TOOL_KEY}
COMMON_AGENT_TOOL_CREDENTIAL_ACTIVE_KEY_ID=v1
COMMON_AGENT_RAGFLOW_IDENTITY_KEYS=v1:${IDENTITY_KEY}
COMMON_AGENT_RAGFLOW_IDENTITY_ACTIVE_KEY_ID=v1
EOF
chmod 600 /etc/common-agent/secrets.env
```

数据库密码若含特殊字符，进 `COMMON_AGENT_DATABASE_URL` 前必须 URL encode（上面用 hex
随机串可回避该问题）。

> **`RAGFLOW_API_KEY` 在全新部署时应当留空**，键必须存在但值为空。它只用于接管某个**已存在**
> 的 RAGFlow 账号（历史遗留场景）。全新安装的 RAGFlow 没有任何账号，平台会自行为每个工作区
> 创建独立的 RAGFlow 技术租户并签发凭据。若在这里填了无效值，接管流程会失败，表现为知识库页
> 显示"知识库服务暂时不可用"。

> **⚠️ `COMMON_AGENT_RAGFLOW_IDENTITY_KEYS` 生成后不可更换。**
>
> 平台用它派生每个工作区在 RAGFlow 侧的账号密码。一旦更换或丢失，已创建的 RAGFlow 账号
> **再也登不进去**——平台会用新密钥派生出不同的密码，而 RAGFlow 里存的还是旧密码，表现为
> 知识库页持续显示"知识库服务暂时不可用"，且无法自动恢复。
>
> 这一点已在本机实测复现：同一个工作区反复用不同密钥部署后，其 RAGFlow 账号就永久失联，
> 只能手工到 RAGFlow 侧重置账号才能恢复。
>
> 因此这两份密钥必须妥善留存（至少抄一份到密码管理器）。同理，`COMMON_AGENT_TOOL_CREDENTIAL_KEYS`
> 丢失会导致已落库的 MCP 凭据无法解密。`preflight` 只检查这 12 个键是否齐全，**不会**校验
> 密钥与库中密文、RAGFlow 账号是否匹配。

## 5. 首次部署

```bash
source /etc/common-agent/deploy.env
cd /opt/common-agent

infra/ragflow/manage.sh up                                    # 起 RAGFlow 栈
infra/production/demo-single-node/certs.sh internal-ca        # 内部 CA + RAGFlow 证书（10 年）
infra/production/manage.sh build
infra/production/manage.sh preflight                          # 会创建 ACME webroot
infra/production/demo-single-node/certs.sh issue              # 签发公网证书
infra/production/manage.sh migrate
infra/production/manage.sh rollout
infra/production/manage.sh verify
```

> **🚫 禁止在服务器上执行 `manage.sh init-tls`。** 它会用 30 天自签材料覆盖 `tls/` 下全部证书，
> 包括刚签发的 Let's Encrypt 证书。该命令仅供本机 drill 使用。

## 6. 日常发布与回滚

```bash
source /etc/common-agent/deploy.env
infra/production/manage.sh build
infra/production/manage.sh migrate
infra/production/manage.sh rollout
```

**发布期间服务不可用。** 本部署固定单槽（`blue`），rollout 会先停掉当前容器再用新镜像重建，
不是蓝绿零停机切换。请挑无人使用的窗口发布。

发布后若发现问题：

```bash
infra/production/manage.sh rollback
infra/production/manage.sh verify
```

回滚用上一个 release 的镜像重建同一槽，同样有停机窗口。**回滚只恢复代码，不执行
`alembic downgrade`**；若新版本的迁移不向后兼容，需人工处理 schema。

若 `rollout` 报"候选 release 验证失败"，服务会保持不可用状态直到你执行 `rollback`——这是单槽
模式的固有代价，不是故障。

## 7. 创建客户账号

产品**不提供公开注册**。每家客户一个独立租户，由管理员手工创建：

1. 用首位 Owner 账号登录 `https://kb.xuanbai.tech`
2. 为每家客户创建独立租户与账号
3. 把地址与账号密码发给对应客户

不同租户之间知识库、会话、数字员工和 RAGFlow 工作区完全隔离。建议提前批量建好若干账号，
发链接时一家一个，避免临时开通的摩擦。

**不要让多家客户共用同一账号**——这是知识库产品，客户会上传自己的真实资料，共用账号会导致
互相看见对方文档。

## 8. 证书维护

安装续期定时器（先按实际值改 `certbot-renew.service` 里的域名与邮箱）：

```bash
sudo cp /opt/common-agent/infra/production/demo-single-node/certbot-renew.{service,timer} \
  /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now certbot-renew.timer
systemctl list-timers certbot-renew.timer
```

查询到期日：

```bash
openssl x509 -enddate -noout -in /var/lib/common-agent/production/tls/edge.crt      # 公网证书，90 天
openssl x509 -enddate -noout -in /var/lib/common-agent/production/tls/ragflow.crt   # 内部证书，10 年
```

手工续期兜底：

```bash
source /etc/common-agent/deploy.env
infra/production/demo-single-node/certs.sh renew
```

续期成功后会自动重建 Edge 容器（数秒不可用）——docker secret 只在容器启动时拷贝，
`nginx -s reload` 不会加载新证书。

## 9. 部署后核查

### 9.1 资源上限已生效

```bash
docker inspect common-agent-production-api-blue --format '{{.HostConfig.Memory}}'   # 期望 2147483648
docker inspect common-agent-ragflow-api --format '{{.HostConfig.Memory}}'           # 期望 5368709120
docker inspect common-agent-ragflow-api --format '{{.HostConfig.NanoCpus}}'         # 期望 2000000000
```

若返回 0，说明资源覆盖没有生效，检查 `COMMON_AGENT_COMPOSE_OVERRIDE` /
`RAGFLOW_COMPOSE_OVERRIDE` 是否已导出。

### 9.2 端口暴露面（因为 Docker 绕过 ufw，这步必做）

```bash
docker ps --format '{{.Names}}\t{{.Ports}}'
sudo ss -tlnp | grep -E ':(80|443|9380|3306|9200|9000|6379)'
```

期望：只有 Edge 监听 `0.0.0.0:80` 与 `0.0.0.0:443`；RAGFlow 的 API/MySQL/ES/MinIO/Valkey
**不得**出现在 `0.0.0.0` 上。

### 9.3 RAGFlow 只经内部 TLS 访问

```bash
curl -sk https://kb.xuanbai.tech/api/v1/system/health    # 应正常
curl -s --max-time 5 http://<公网IP>:9380/ && echo "❌ RAGFlow 直接暴露！" || echo "✅ RAGFlow 未暴露"
```

## 10. 磁盘与镜像清理

```bash
df -h /
docker images --format '{{.Repository}}:{{.Tag}}\t{{.ID}}\t{{.Size}}'
docker ps -a --format '{{.Image}}' | sort -u        # 仍被引用的镜像
```

删除被新版本替代且无容器引用的旧 release 镜像：

```bash
docker image rm <旧镜像ID>
```

**只删本项目自建镜像**（`common-agent/*` 前缀与 `manage.sh build` 产出的无 tag 镜像）。
不要删 `infiniflow/ragflow`、`elasticsearch`、`mysql`、`minio`、`valkey`、`nginx` 等仍在复用的
官方基础镜像，也不要执行 `docker system prune -a`。

## 11. 资源实测（首次部署后必做）

`resources.compose.yaml` 中 api 与 worker 的内存上限目前是**估算值**，须由真实 soak 修正：

```bash
source /etc/common-agent/deploy.env
python3 infra/production/resource_monitor.py --duration-seconds 1800 --output /tmp/soak.json
```

soak 期间必须覆盖"上传文档解析的同时保持聊天"这一组合负载——这是单机上业务与 RAGFlow 争抢
CPU 最容易暴露的场景。跑完后：

1. 确认无 OOM、无容器重启、无持续 swap 压力
2. 用实测峰值回写 `resources.compose.yaml` 与设计文档 §4.2，去掉"估算"标注
3. 把结论记入路线图任务的完成证据

## 12. 已知限制

- 单槽发布有停机窗口，发布失败时服务保持不可用直到人工 `rollback`
- 不做备份，数据卷损坏即数据丢失
- 未做本机完整 drill 的压测门禁（k6 读容量、SSE 128 路、Worker 崩溃接管），
  按 1-3 人试用规模判断为可接受，若并发规模上升需补做
- Docker Hub 上的 RAGFlow 基础镜像 digest 已失效，重装时必须走 §3 的华为云路径
