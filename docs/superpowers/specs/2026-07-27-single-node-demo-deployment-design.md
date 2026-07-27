# 单台 4C16G 服务器 Demo 部署设计

日期：2026-07-27
分支：`single-node-demo-deploy`
状态：设计已确认，待转实施计划

## 1. 背景与目标

项目现有生产方案（`infra/production/`）按**两个故障域**规划：8C16G 业务节点 + 8C32G RAGFlow
节点。该方案已在本机 Colima 通过完整 drill 验收，但从未远程部署。

当前需求是给客户提供一个**公网可访问的试用环境**，预算受限，只租一台 4C16G 服务器。本设计
把已验收的单机模式（`COMMON_AGENT_RAGFLOW_EDGE_MODE=local-shared-network`）从本机 drill
搬到真实服务器，并补齐正式证书、资源重配和单槽发布三处缺口。

本设计不改变产品功能边界，不进入 `docs/product-scope.md`；实施进度记入当前路线图。

## 2. 已确认的需求与决策

| 项 | 决策 | 说明 |
| --- | --- | --- |
| 使用形态 | 公网发链接给客户自己试用 | 同事也可能拿自己电脑现场演示 |
| 并发规模 | 1-3 人在线，几十份文档 | 4C16G 对该量级有余量 |
| 账号发放 | 一家客户一个租户 | 复用现有多租户隔离，零开发量 |
| 服务器与域名 | 国内云 + 已备案 `xuanbai.tech`，泛解析已配置 | 使用三级域名 `kb.xuanbai.tech` |
| 数据备份 | 不做备份流程 | 客户数据丢失可接受 |
| 可用性 | 不要求高可用，部署期间服务不可用可接受 | 发布窗口由使用方自行选择 |
| 发布方式 | 固定单槽，停机发布 | 放弃蓝绿零停机，接受改造工作量 |
| 回滚方式 | 一条 `rollback` 命令重启到上个镜像 | 保留不可变镜像，停机 30-60 秒 |
| 实现方式 | 配置档案为主 + 局部改 `manage.sh` | 不新建并行 compose，避免配置漂移 |

### 2.1 单槽决策的已知代价

使用方在了解以下代价后确认选择单槽：

- 现有 rollout 的"验证失败自动切回旧槽"安全网在单槽下不存在。新镜像起不来时，服务将保持
  不可用直到人工执行 `rollback`；
- 需要改动 `rollout()`、`rollback()`、`write_state()` 与 `test-manage.sh` / `drill.sh`，
  并重跑完整 drill 回归；
- 蓝绿在稳态不占额外内存（compose profiles 控制，非活动槽无容器），单槽节省的只是发布
  切换窗口约 1-2 GiB 的数十秒峰值。

## 3. 单机拓扑

### 3.0 服务器规格

| 项 | 规格 | 依据 |
| --- | --- | --- |
| CPU / 内存 | 4 核 16 GiB | 第 4 节资源预算 |
| 实例类型 | 通用型 / 计算型，**不得使用突发性能实例** | RAGFlow 解析是持续 CPU 负载，积分耗尽会导致性能骤降 |
| 架构 | **x86_64** | `infra/ragflow/compose.override.yaml` 固定 `platform: linux/amd64` |
| 磁盘 | **100 GB SSD** | 见下表实测账；50 GB 会被构建缓存与日志迅速填满 |
| 系统 | Ubuntu 22.04 / 24.04 LTS | Docker 官方源与 certbot 包现成 |
| 带宽 | 3-5 Mbps | 1-3 人试用，主要流量为首屏与文档上传 |

磁盘占用实测账（镜像体积取自本机 `docker images`）：

| 项 | 占用 |
| --- | --- |
| RAGFlow 镜像 | 12 GB |
| Elasticsearch | 1.23 GB |
| MySQL ×2（RAGFlow 与平台各一） | ~1.6 GB |
| MinIO + Valkey + nginx | ~0.45 GB |
| 业务 API 镜像 | ~1.5 GB |
| 上一个 release 镜像（回滚保留） | ~0.5 GB |
| Docker build cache | 3-5 GB |
| 运行数据（ES 索引、MinIO 原文、MySQL、日志） | ~5 GB |
| 系统与 Docker 本体 | ~10 GB |
| 合计 | **~37 GB** |

### 3.1 部署形态

一台 4C16G x86 Linux，Docker + Compose，三个 compose project 并存，全部复用现有文件。

```
                          客户浏览器
                              │ HTTPS :443（Let's Encrypt）
                              │ HTTP  :80 → 301 跳转 + ACME 挑战
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  project: common-agent-production            [infra/production] │
│    edge (nginx)                                                 │
│      ├─ /           ─▶ web-<slot>   (静态页面)                   │
│      └─ /api, /sse  ─▶ api-<slot>:8000                          │
│    worker-<slot>      platform-mysql (internal 网络)             │
└──────────┬──────────────────────────────────────────────────────┘
           │
           ├─ HTTPS ─▶ common-agent-production-ragflow-edge:9443
           │              │  [project: common-agent-production-ragflow-edge]
           │              │  同时挂 app-private + ragflow-private
           │              ▼
           │           RAGFlow 栈 [infra/ragflow, project: common-agent-dev]
           │           ragflow-api / elasticsearch / mysql / minio / valkey
           │
           └─ HTTPS ─▶ dashscope.aliyuncs.com（阿里百炼，唯一外部服务）
```

### 3.2 网络边界

| 网络 | 成员 | 出网 | 宿主机端口 |
| --- | --- | --- | --- |
| `edge-public` | edge | 否 | `0.0.0.0:443`、`0.0.0.0:80` |
| `app-private`（internal） | edge、web、api、worker、platform-mysql、ragflow-edge | 否 | 无 |
| `app-egress` | api、worker | 是 | 无 |
| `ragflow-private` | RAGFlow 五容器、ragflow-edge | 否 | 无 |

RAGFlow API、Elasticsearch、MySQL、MinIO、Valkey **一个端口都不映射到宿主机**。业务侧只能
通过 `ragflow-edge` 的 HTTPS 访问，与两节点方案的安全边界一致，差别仅在于把"跨主机私网"
换成"同机 Docker 网络"。

宿主机防火墙只放行 22（管理）、80、443。

### 3.3 与两节点方案的关系

两者共用同一份 `compose.yaml` 与 `manage.sh`，差异全部落在配置值：

- `COMMON_AGENT_RAGFLOW_EDGE_MODE`：`external`（两节点）/ `local-shared-network`（单机）
- `RAGFLOW_BASE_URL`：私网 DNS（两节点）/ 容器名 `common-agent-production-ragflow-edge`（单机）

产品代码读取配置的路径是同一条，符合项目单一构建路径规范。

## 4. 资源预算

### 4.1 实测基准

| 来源 | 数据 |
| --- | --- |
| `docs/development-roadmap.md:671` | 迁移前含本地 TEI 时，TEI 单容器占用 21.62 GiB |
| `infra/production/README.md` | 本地 embedding/rerank 退场后，30 分钟真实链路 180 个采样，RAGFlow 相关容器合计峰值 **7.23 GiB**，RAGFlow API 单项 **4.53 GiB**，Swap / 重启 / OOM 均为 0 |

RAGFlow 官方 4C16G 最低要求主要来自本机 embedding/rerank 模型。本项目已统一改调阿里百炼
API，该开销不再存在，因此单机 16 GiB 可行。

### 4.2 分配方案

| 层 | 容器 | 现有 `mem_limit` | 单机 demo | 依据 |
| --- | --- | --- | --- | --- |
| 系统 | OS + Docker | — | 预留 1.5 GiB | — |
| RAGFlow | ragflow-api | 5g | 5g | 实测峰值 4.53 GiB，不可压缩 |
| | elasticsearch | 3g / heap 1g | 2g / heap 768m | 实测 1.71 GiB |
| | mysql | 2g | 1g | 实测 427 MiB |
| | minio | 1g | 512m | 实测 122 MiB |
| | valkey | 256m | 256m | 实测 12 MiB |
| 业务 | api | 5g | 2g | **估算，待实测修正** |
| | worker | 5g | 1536m | **估算，待实测修正** |
| | platform-mysql | 1536m | 1g | demo 数据量小 |
| | web | 128m | 64m | nginx 静态 |
| | edge | 128m | 64m | nginx 反代 |

`mem_limit` 合计约 14.4 GiB。这是**护栏而非预留**——Docker 不预占内存，超过物理内存的上限
之和是允许的。护栏的作用是让失控容器被单独终止，而不是把整机拖入 swap。按实测推算，稳态
实际占用约 10-11 GiB。

### 4.3 CPU 分配与削峰

4 核机器上业务与 RAGFlow 争抢 CPU 是单机合并特有的风险，两节点方案不存在。

- `ragflow-api` 增加 `cpus: 2.0` 限制（当前无限制）。不限制时文档解析会吃满 4 核，导致
  同一时刻的聊天请求和 SSE 明显卡顿；
- RAGFlow 解析并发下调：`MAX_CONCURRENT_TASKS` 5→2、`MAX_CONCURRENT_EMBEDDINGS` 8→4、
  `DOC_BULK_SIZE` 32→16。几十份文档的场景下解析变慢可接受；
- 宿主机配置 4 GiB swap 作为瞬时尖峰兜底，避免直接触发 OOM killer。

## 5. 单槽发布改造

### 5.1 现有蓝绿流程

`infra/production/manage.sh:424-460`：

```
起新槽 api/web → 健康检查 → 切 edge → 验证公网入口
                                        ├─ 通过 → 起新 worker → 停旧槽
                                        └─ 失败 → 切回旧槽、停新槽、报错
```

### 5.2 目标单槽流程

固定使用 `blue` 槽，`green` 槽的 compose 服务定义保留但永不启动，以便两节点方案继续可用。

```
停当前槽 → 用新镜像起同一槽 → 健康检查 → 强制 reload edge → 验证公网入口
                                                    └─ 失败 → 报错并提示 rollback
```

### 5.3 改动清单

| 位置 | 改动 |
| --- | --- |
| `manage.sh` `rollout()` | 删除 blue↔green 轮换（第 433 行），固定 `blue`；改为先停后起；验证失败分支改为报错并提示 `rollback`，不再执行切回 |
| `manage.sh` `rollback()` | 同样固定 `blue`，用 `previous_release` 镜像重跑一次单槽发布 |
| `manage.sh` `write_state()` | `previous_slot` 恒等于 `active_slot`；`previous_release` 保留，作为回滚依据 |
| `manage.sh` rollout 尾部 | **新增**：起完新容器后强制 reload edge，即使配置内容未变 |
| `edge.conf.template` | **新增** 80 端口 server 块：`/.well-known/acme-challenge/` 指向 webroot，其余 301 跳转 443。当前模板只有 443（容器内 9443）server 块 |
| `compose.yaml` | edge 服务**新增** 80 端口映射与 ACME webroot 只读挂载。当前只映射 443 |
| `test-manage.sh` | 现有断言围绕蓝绿切换编写，需改为单槽断言（先改测试确认失败，再改实现） |
| `drill.sh` | 蓝绿切流相关断言改为单槽发布断言，需重跑完整 drill |

`compose.yaml` 的改动限于新增端口映射与挂载，不改变任何服务的依赖解析路径，两节点方案
沿用同一份文件（80 端口在 `external` 模式下同样可用于证书续期）。

### 5.4 必须处理的 nginx DNS 缓存问题

蓝绿模式每次切换都重新渲染 edge 配置并 reload，upstream 容器 IP 必然是新的。单槽模式下
edge 配置内容不变，但 api 容器重启后 Docker 分配的 IP 可能变化，nginx 会继续指向已销毁的
IP 并返回 502。

因此单槽 rollout 必须在起完新容器后强制 reload edge。缺少这一步的表现是"部署完成后页面
全部 502，手工重启 edge 即恢复"。

## 6. TLS 与证书

### 6.1 两套证书

| 用途 | 签发方式 | 有效期 | SAN |
| --- | --- | --- | --- |
| 对外 edge | Let's Encrypt，HTTP-01 验证 | 90 天，自动续期 | `kb.xuanbai.tech` |
| 对内 ragflow-edge | 自签内部 CA | 10 年 | `common-agent-production-ragflow-edge`（容器名） |

内部证书使用容器名作为 SAN，不依赖真实 DNS。现有 `init-tls` 生成 30 天自签材料且明确标注
禁止用于远程生产。内部 CA 的长有效期签发由新增的 `certs.sh` 承担，`init-tls` 保持原样只服务
本机 drill，避免削弱其"禁止用于远程生产"的约束。

### 6.2 80 端口用途

开放 80 仅用于两件事：ACME HTTP-01 挑战、其余请求 301 跳转到 443。80 上不提供任何业务内容。
选择 HTTP-01 而非 DNS-01，是因为不需要域名厂商 API token，且客户不带 `https://` 也能访问。

### 6.3 certbot 运行方式

certbot 安装在**宿主机**（非容器），使用 **webroot** 模式而非 standalone——standalone 需要
独占 80 端口，而 80 已由 edge 容器占用。

```
宿主机 certbot --webroot -w <state>/acme  →  写挑战文件
edge 容器只读挂载 <state>/acme            →  nginx 通过 /.well-known/acme-challenge/ 提供
```

### 6.4 续期链路

现有 compose 把证书作为 **docker secret** 挂载（`compose.yaml:250-254`）。docker secret 在
容器启动时拷贝，**续期后不会自动生效**，必须重启 edge。

```
systemd timer（每周） → certbot renew → 有更新则拷贝到 state/tls/edge.{crt,key}
                                      → docker compose up -d edge（重启数秒）
```

续期失败必须以非零退出码和日志暴露，不得静默。到期前 30 天开始尝试，保留重试窗口。

### 6.5 开机自启

所有容器已配置 `restart: unless-stopped`，将 Docker 服务设为开机自启即可，无需额外工作。

## 7. 失败矩阵

现有 RAGFlow、百炼、工具、工作流的失败矩阵已在项目内覆盖，此处只列本次新增部分。

| 场景 | 表现 | 处理 |
| --- | --- | --- |
| certbot 续期失败 | 证书到期，浏览器报不安全 | 非零退出 + 日志告警；提前 30 天开始尝试 |
| 新镜像起不来 | 服务持续不可用 | 健康检查超时后明确报错并提示 `rollback`，不自动重试掩盖 |
| edge reload 后 502 | nginx 指向已销毁容器 IP | 单槽 rollout 强制 reload edge；验证必须打真实公网入口 |
| 内存打满 | 容器被 OOM kill 或整机 swap 抖动 | `mem_limit` 护栏 + 4 GiB swap；`resource_monitor.py` 采样告警 |
| CPU 争抢 | 上传文档时聊天卡顿、SSE 断流 | `ragflow-api` 限 2.0 核 + 解析并发下调；soak 专项验证 |
| 磁盘满 | ES 写入失败、上传失败 | 部署时确认容量；runbook 提供清理旧 release 镜像的命令 |
| 重启后拉起顺序 | RAGFlow 未就绪时 api 已启动 | 现有失败处理 + `restart: unless-stopped` 重试 |
| 内部证书过期 | 业务调 RAGFlow 全部失败 | 签 10 年有效期，runbook 记录到期日 |
| 首次远程发布误触 | 误操作影响非目标环境 | 保留 `COMMON_AGENT_REMOTE_DEPLOY_CONFIRMATION` 防误触，不绕过 |

不适用项：备份与恢复演练（使用方已确认数据丢失可接受）、多副本容量扩展（1-3 人规模）。

## 8. 验收标准

遵循项目生产同路径规则，按以下顺序执行：

1. **本机门禁**：`test-manage.sh` 单槽断言先失败再通过（TDD），完整 `drill.sh` 在本机跑通；
2. **目标服务器真实验收**：Playwright 从 `https://kb.xuanbai.tech` 走完整用户链路——登录 →
   建知识库 → 上传真实文档 → RAGFlow 解析完成 → 建数字员工并绑定知识库 → 两轮带引用对话 →
   手动运行一次工作流；
3. **资源 soak**：`resource_monitor.py` 在目标机运行 30 分钟，覆盖"解析文档的同时保持聊天"，
   确认无 OOM、无容器重启、内存峰值留有余量。该步骤负责把第 4.2 节业务侧的估算值替换为实测值；
4. **发布演练**：在目标机真实执行一次 `rollout` 与一次 `rollback`，记录实际停机时长；
5. **证书演练**：强制触发一次续期流程，确认 edge 重启后新证书生效。

第 3 步完成前，业务侧资源数字在文档中保持"估算"标注，不得当作已验收结论。

## 9. 明确不做的事

- 不做备份与恢复演练流程（使用方确认数据可丢）；
- 不做公开注册功能，账号由管理员按租户手工创建；
- 不新建并行的 demo compose 或 demo 专用产品代码分支；
- 不因单机部署裁剪 RAGFlow 必需组件，不切换文档引擎到 Infinity；
- 不做多节点扩容、负载均衡与自动伸缩；
- 首次远程发布仍需使用方明确授权，本设计不代表已获授权。

## 10. 交付物清单

| 交付物 | 位置 |
| --- | --- |
| 单机部署配置模板 | `infra/production/demo-single-node/config.env.example` |
| 资源覆盖 compose 片段 | `infra/production/demo-single-node/resources.compose.yaml` |
| 证书签发与续期脚本 | `infra/production/demo-single-node/certs.sh` |
| 部署 runbook | `infra/production/demo-single-node/README.md`，至少覆盖：首次部署步骤、日常单槽发布与回滚命令、按租户创建客户账号的操作、Demo Seed 重放、磁盘与旧镜像清理、证书到期日与手工续期兜底 |
| 单槽发布改造 | `infra/production/manage.sh`、`test-manage.sh`、`drill.sh` |
| 路线图记录 | 当前 V3 路线图新增任务与完成证据 |
