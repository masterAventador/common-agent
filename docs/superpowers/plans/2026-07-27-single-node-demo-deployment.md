# 单台 4C16G 服务器 Demo 部署实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把已验收的 `local-shared-network` 单机模式落到一台 4C16G 公网服务器，提供 `https://kb.xuanbai.tech` 的客户试用环境。

**Architecture:** 复用现有 `infra/production/compose.yaml` 与 `manage.sh`，不新建并行 compose。发布从蓝绿轮换改为固定 `blue` 单槽停机发布；新增 Edge HTTP 监听承载 ACME 挑战与 HTTPS 跳转；新增 `infra/production/demo-single-node/` 存放单机资源覆盖、配置模板、证书脚本与 runbook。

**Tech Stack:** Bash、Docker Compose、nginx、OpenSSL、certbot（宿主机 webroot 模式）、systemd timer。

## Global Constraints

- 设计依据：`docs/superpowers/specs/2026-07-27-single-node-demo-deployment-design.md`
- 固定发布槽为 `blue`；`green` 的 compose 服务定义保留，但 `manage.sh` 不再引用它
- **目标服务器已就绪**：`43.143.210.107`，Ubuntu 24.04.4 LTS，x86_64，4 核 / 15Gi 内存，
  磁盘 178G（已用 5.5G），现有 swap 1.9G 需扩到 4G，Docker 未安装。本机公钥已装，
  `ssh ubuntu@43.143.210.107` 免密可用，密码登录按用户要求保留
- 公网域名固定 `kb.xuanbai.tech`；对外只开 22、80、443
- RAGFlow 五个容器不映射任何宿主机端口
- 容器内 nginx 以 `101:101` 运行，无法监听 1024 以下端口：容器内用 `9080`/`9443`，由宿主机映射 `80`/`443`
- 所有 shell 改动必须通过 `shellcheck`
- 每个任务结束提交一次，commit message 用中文，不加 AI 署名
- 本机验收使用 `colima-common-agent-dev` context；目标服务器使用 `default` context

---

### Task 1: Edge HTTP 监听与 ACME 挑战路径

Let's Encrypt 的 HTTP-01 验证需要 80 端口提供挑战文件。当前 `edge.conf.template` 只有 443（容器内 9443）server 块，`compose.yaml` 也只映射 443。本任务补齐 HTTP 监听、挑战路径与 webroot 挂载。

**Files:**
- Modify: `infra/production/edge.conf.template`
- Modify: `infra/production/compose.yaml:195-235`（edge 服务）
- Modify: `infra/production/manage.sh:8-24`（变量）、`72-75`（`prepare_state_root`）、`181-196`（`compose_loaded_release`）
- Test: `infra/production/test-manage.sh`

**Interfaces:**
- Produces: 环境变量 `COMMON_AGENT_ACME_ROOT`（宿主机 webroot 绝对路径）、`COMMON_AGENT_HTTP_BIND`、`COMMON_AGENT_HTTP_PORT`；manage.sh 内部变量 `ACME_ROOT`，值为 `${STATE_ROOT}/acme`
- Consumes: 无

- [ ] **Step 1: 写失败的契约断言**

在 `infra/production/test-manage.sh` 第 68 行（`grep -Fq '  app-egress:' "${COMPOSE_FILE}"` 那一行）之后插入：

```bash
grep -Fq 'listen 9080;' "${SCRIPT_DIR}/edge.conf.template" || \
  fail "Edge 模板缺少 ACME 与跳转用的 HTTP 监听"
grep -Fq '/.well-known/acme-challenge/' "${SCRIPT_DIR}/edge.conf.template" || \
  fail "Edge 模板缺少 ACME 挑战路径"
grep -Fq 'return 301 https://$host$request_uri;' "${SCRIPT_DIR}/edge.conf.template" || \
  fail "Edge 模板缺少 HTTP 到 HTTPS 跳转"
grep -Fq ':9080' "${COMPOSE_FILE}" || fail "Edge 容器没有发布 HTTP 端口"
grep -Fq 'COMMON_AGENT_ACME_ROOT' "${COMPOSE_FILE}" || fail "Edge 容器没有挂载 ACME webroot"
grep -Fq 'COMMON_AGENT_ACME_ROOT' "${MANAGER}" || fail "发布入口没有传递 ACME webroot"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `infra/production/test-manage.sh`
Expected: FAIL，输出 `Edge 模板缺少 ACME 与跳转用的 HTTP 监听`

- [ ] **Step 3: 给 edge 模板加 HTTP server 块**

在 `infra/production/edge.conf.template` 第 26 行（`upstream common_agent_web { ... }` 闭合花括号之后、`server { listen 9443 ssl;` 之前）插入：

```nginx
  server {
    listen 9080;
    server_name {{PUBLIC_DOMAIN}};
    if ($host != "{{PUBLIC_DOMAIN}}") { return 421; }

    # 仅供 Let's Encrypt HTTP-01 验证；webroot 由宿主机 certbot 写入。
    location ^~ /.well-known/acme-challenge/ {
      root /run/common-agent/acme;
      default_type text/plain;
    }

    location / {
      return 301 https://$host$request_uri;
    }
  }
```

- [ ] **Step 4: 给 compose 的 edge 服务加端口与挂载**

在 `infra/production/compose.yaml` 的 `edge` 服务中，把 `ports` 段替换为：

```yaml
    ports:
      - ${COMMON_AGENT_HTTPS_BIND:-127.0.0.1}:${COMMON_AGENT_HTTPS_PORT:-18443}:9443
      - ${COMMON_AGENT_HTTP_BIND:-127.0.0.1}:${COMMON_AGENT_HTTP_PORT:-18080}:9080
```

在同一服务的 `volumes` 段末尾（`common-agent-web.conf` 那一项之后）追加：

```yaml
      - type: bind
        source: ${COMMON_AGENT_ACME_ROOT:?COMMON_AGENT_ACME_ROOT is required}
        target: /run/common-agent/acme
        read_only: true
```

- [ ] **Step 5: 在 manage.sh 定义并传递变量**

在 `infra/production/manage.sh` 第 19 行（`HTTPS_PORT=...`）之后插入：

```bash
HTTP_BIND="${COMMON_AGENT_HTTP_BIND:-127.0.0.1}"
HTTP_PORT="${COMMON_AGENT_HTTP_PORT:-18080}"
ACME_ROOT="${STATE_ROOT}/acme"
```

把 `prepare_state_root()` 改为：

```bash
prepare_state_root() {
  mkdir -p "${RELEASE_ROOT}" "${TLS_ROOT}" "${ACME_ROOT}/.well-known/acme-challenge"
  chmod 700 "${STATE_ROOT}" "${RELEASE_ROOT}" "${TLS_ROOT}"
  # webroot 需要被容器内 nginx（uid 101）读取，因此不能是 0700。
  chmod 755 "${ACME_ROOT}" "${ACME_ROOT}/.well-known" "${ACME_ROOT}/.well-known/acme-challenge"
}
```

在 `compose_loaded_release()` 的环境变量列表中，`COMMON_AGENT_HTTPS_PORT="${HTTPS_PORT}" \` 之后插入：

```bash
  COMMON_AGENT_HTTP_BIND="${HTTP_BIND}" \
  COMMON_AGENT_HTTP_PORT="${HTTP_PORT}" \
  COMMON_AGENT_ACME_ROOT="${ACME_ROOT}" \
```

- [ ] **Step 6: 运行测试确认通过**

Run: `infra/production/test-manage.sh`
Expected: PASS，无输出且退出码 0

- [ ] **Step 7: 校验 shell 与 compose 语法**

Run: `shellcheck infra/production/manage.sh infra/production/test-manage.sh`
Expected: 无输出

Run: `docker --context colima-common-agent-dev compose -f infra/production/compose.yaml config --quiet` （需先 `export` 该文件引用的必填变量，参考 `drill.sh:15-40` 的赋值方式）
Expected: 无输出

- [ ] **Step 8: 提交**

```bash
git add infra/production/edge.conf.template infra/production/compose.yaml \
  infra/production/manage.sh infra/production/test-manage.sh
git commit -m "feat(production): Edge 增加 HTTP 监听承载证书验证与跳转

Let's Encrypt HTTP-01 验证需要 80 端口提供挑战文件，Edge 此前只监听
443。新增容器内 9080 监听，挑战路径指向宿主机 certbot 的 webroot，
其余请求 301 跳转 HTTPS。"
```

---

### Task 2: 单槽 rollout

把 rollout 从蓝绿轮换改为固定 `blue` 停机发布。发布期间服务不可用，验证失败不再自动切回旧槽。

**Files:**
- Modify: `infra/production/manage.sh:424-460`（`rollout()`）、第 24 行附近（新增 `DEPLOY_SLOT`）
- Test: `infra/production/test-manage.sh`

**Interfaces:**
- Consumes: Task 1 的 `ACME_ROOT`（`prepare_state_root` 已创建目录）
- Produces: manage.sh 内部常量 `DEPLOY_SLOT="blue"`，供 Task 3 的 `rollback()` 复用

**关于 nginx DNS 缓存：** 现有 `switch_edge()`（`manage.sh:413-422`）内部已执行 `nginx -s reload`，reload 会重新解析 upstream 的容器名。单槽 rollout 只要继续调用 `switch_edge`，容器重建后的新 IP 就会生效，**不需要新增 reload 函数**。删除这次调用会导致部署后全站 502。

- [ ] **Step 1: 写失败的契约断言**

在 `infra/production/test-manage.sh` 中 Task 1 新增的断言之后追加：

```bash
grep -Fq 'DEPLOY_SLOT="blue"' "${MANAGER}" || fail "发布入口没有固定单槽"
if grep -Eq 'target_slot="(blue|green)"' "${MANAGER}"; then
  fail "单槽发布不得保留蓝绿轮换"
fi
grep -Fq '请执行 rollback 恢复上一 release' "${MANAGER}" || \
  fail "单槽发布验证失败后没有提示回滚路径"
grep -Fq 'switch_edge "${DEPLOY_SLOT}"' "${MANAGER}" || \
  fail "单槽发布没有重载 Edge，容器重建后会指向失效 IP"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `infra/production/test-manage.sh`
Expected: FAIL，输出 `发布入口没有固定单槽`

- [ ] **Step 3: 定义固定槽常量**

在 `infra/production/manage.sh` 第 24 行（`LOCAL_CONTEXT_CONFIRMATION=...`）之后插入：

```bash
# 单机 demo 固定使用 blue 槽停机发布；green 的 compose 定义保留但不再启动。
DEPLOY_SLOT="blue"
```

- [ ] **Step 4: 重写 rollout**

把 `manage.sh` 的 `rollout()` 整个函数替换为：

```bash
rollout() {
  local release_id old_release
  preflight
  release_id="$(candidate_release_id)"
  [[ -f "${STATE_ROOT}/migrated-${release_id}" ]] || fail "候选 release 尚未执行 migrate"
  load_release "${release_id}"
  load_state
  old_release="${active_release}"

  if [[ "${RAGFLOW_EDGE_MODE}" == "local-shared-network" ]]; then
    ragflow_compose up -d
    wait_for_ragflow_edge
  fi

  # 单槽发布：先停旧容器再用新镜像重建同一槽，发布窗口内服务不可用。
  compose_loaded_release stop \
    "worker-${DEPLOY_SLOT}" "api-${DEPLOY_SLOT}" "web-${DEPLOY_SLOT}" || true
  compose_loaded_release --profile "${DEPLOY_SLOT}" up -d --no-deps --force-recreate \
    "api-${DEPLOY_SLOT}" "web-${DEPLOY_SLOT}"
  wait_for_service "api-${DEPLOY_SLOT}" 240
  wait_for_service "web-${DEPLOY_SLOT}" 60
  # 容器重建后 IP 变化，switch_edge 内的 nginx -s reload 会重新解析 upstream。
  switch_edge "${DEPLOY_SLOT}"
  if ! verify_edge; then
    fail "候选 release 验证失败；服务当前不可用，请执行 rollback 恢复上一 release"
  fi
  compose_loaded_release --profile "${DEPLOY_SLOT}" up -d --no-deps --force-recreate \
    "worker-${DEPLOY_SLOT}"
  wait_for_service "worker-${DEPLOY_SLOT}" 90
  write_state "${DEPLOY_SLOT}" "${release_id}" "${DEPLOY_SLOT}" "${old_release}"
  echo "release 已发布：${release_id} (${DEPLOY_SLOT})"
}
```

- [ ] **Step 5: 运行测试确认通过**

Run: `infra/production/test-manage.sh`
Expected: PASS

Run: `shellcheck infra/production/manage.sh infra/production/test-manage.sh`
Expected: 无输出

- [ ] **Step 6: 提交**

```bash
git add infra/production/manage.sh infra/production/test-manage.sh
git commit -m "feat(production): 发布改为固定单槽停机模式

单机 demo 不需要零停机发布。rollout 改为停掉 blue 槽后用新镜像重建
同一槽，发布窗口内服务不可用。验证失败不再自动切回旧槽（单槽下无旧
槽可切），改为明确提示执行 rollback。

保留对 switch_edge 的调用：容器重建后 IP 变化，其中的 nginx -s reload
负责重新解析 upstream，否则发布后全站 502。"
```

---

### Task 3: 单槽 rollback

回滚改为用 `previous_release` 的镜像在同一槽重跑一次单槽发布。

**Files:**
- Modify: `infra/production/manage.sh:475-500`（`rollback()`）
- Test: `infra/production/test-manage.sh`

**Interfaces:**
- Consumes: Task 2 的 `DEPLOY_SLOT`
- Produces: 无

- [ ] **Step 1: 写失败的契约断言**

在 `infra/production/test-manage.sh` 中 Task 2 新增的断言之后追加：

```bash
if grep -Fq 'rollback_slot' "${MANAGER}"; then
  fail "单槽回滚不得保留槽切换变量"
fi
grep -Fq '代码与流量已回滚' "${MANAGER}" || fail "回滚没有输出结果说明"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `infra/production/test-manage.sh`
Expected: FAIL，输出 `单槽回滚不得保留槽切换变量`

- [ ] **Step 3: 重写 rollback**

把 `manage.sh` 的 `rollback()` 整个函数替换为：

```bash
rollback() {
  local rollback_release current_release
  guard_docker_context
  load_state
  [[ -n "${previous_release}" ]] || fail "没有可回滚的 previous release"
  current_release="${active_release}"
  rollback_release="${previous_release}"
  load_release "${rollback_release}"

  compose_loaded_release stop \
    "worker-${DEPLOY_SLOT}" "api-${DEPLOY_SLOT}" "web-${DEPLOY_SLOT}" || true
  compose_loaded_release --profile "${DEPLOY_SLOT}" up -d --no-deps --force-recreate \
    "api-${DEPLOY_SLOT}" "web-${DEPLOY_SLOT}"
  wait_for_service "api-${DEPLOY_SLOT}" 240
  wait_for_service "web-${DEPLOY_SLOT}" 60
  switch_edge "${DEPLOY_SLOT}"
  if ! verify_edge; then
    fail "previous release 验证同样失败；服务仍不可用，请人工介入"
  fi
  compose_loaded_release --profile "${DEPLOY_SLOT}" up -d --no-deps --force-recreate \
    "worker-${DEPLOY_SLOT}"
  wait_for_service "worker-${DEPLOY_SLOT}" 90
  write_state "${DEPLOY_SLOT}" "${rollback_release}" "${DEPLOY_SLOT}" "${current_release}"
  echo "代码与流量已回滚；数据库 schema 保持向前版本：${rollback_release}"
}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `infra/production/test-manage.sh`
Expected: PASS

Run: `shellcheck infra/production/manage.sh infra/production/test-manage.sh`
Expected: 无输出

- [ ] **Step 5: 提交**

```bash
git add infra/production/manage.sh infra/production/test-manage.sh
git commit -m "feat(production): 回滚改为单槽重建上一 release

单槽下没有常驻的旧槽可以切回，回滚改为用 previous_release 的镜像在
同一槽重跑一次停机发布。回滚同样失败时明确要求人工介入，不静默留在
不可用状态。数据库 schema 仍不自动降级。"
```

---

### Task 4: 单机资源与配置档案

新增 `infra/production/demo-single-node/`，承载 4C16G 的资源覆盖与配置模板。资源值取自设计文档第 4.2 节。

**Files:**
- Create: `infra/production/demo-single-node/resources.compose.yaml`
- Create: `infra/production/demo-single-node/ragflow-resources.compose.yaml`
- Create: `infra/production/demo-single-node/config.env.example`
- Create: `infra/production/demo-single-node/test-demo-single-node.sh`
- Modify: `infra/production/test-manage.sh`

**Interfaces:**
- Consumes: 无
- Produces: 两个 compose 覆盖片段，供 Task 7 的 runbook 通过 `-f` 叠加使用

- [ ] **Step 1: 写失败的契约断言**

创建 `infra/production/demo-single-node/test-demo-single-node.sh`，内容：

```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESOURCES="${SCRIPT_DIR}/resources.compose.yaml"
RAGFLOW_RESOURCES="${SCRIPT_DIR}/ragflow-resources.compose.yaml"
CONFIG_EXAMPLE="${SCRIPT_DIR}/config.env.example"

fail() {
  echo "$1" >&2
  exit 1
}

[[ -f "${RESOURCES}" ]] || fail "缺少单机业务资源覆盖"
[[ -f "${RAGFLOW_RESOURCES}" ]] || fail "缺少单机 RAGFlow 资源覆盖"
[[ -f "${CONFIG_EXAMPLE}" ]] || fail "缺少单机配置模板"

for expected in 'mem_limit: 2g' 'mem_limit: 1536m' 'mem_limit: 1g' 'mem_limit: 64m'; do
  grep -Fq "${expected}" "${RESOURCES}" || fail "业务资源覆盖缺少：${expected}"
done

# RAGFlow API 实测峰值 4.53 GiB，不得压到 5g 以下。
grep -Fq 'mem_limit: 5g' "${RAGFLOW_RESOURCES}" || fail "RAGFlow API 内存上限被压到实测峰值以下"
grep -Fq 'cpus: 2.0' "${RAGFLOW_RESOURCES}" || fail "RAGFlow API 没有 CPU 配额，解析会吃满整机"
for expected in 'MAX_CONCURRENT_TASKS: "2"' 'MAX_CONCURRENT_EMBEDDINGS: "4"' 'DOC_BULK_SIZE: "16"'; do
  grep -Fq "${expected}" "${RAGFLOW_RESOURCES}" || fail "RAGFlow 解析并发没有下调：${expected}"
done

grep -Fxq 'COMMON_AGENT_INTEGRATION_MODE=real' "${CONFIG_EXAMPLE}" || \
  fail "单机配置必须使用 real 集成模式"
grep -Fxq 'RAGFLOW_BASE_URL=https://common-agent-production-ragflow-edge:9443' "${CONFIG_EXAMPLE}" || \
  fail "单机配置没有指向本机 RAGFlow Edge 容器名"
grep -Eq '^COMMON_AGENT_CORS_ORIGINS=https://kb\.xuanbai\.tech$' "${CONFIG_EXAMPLE}" || \
  fail "单机配置没有使用正式公网域名"

echo "单机部署配置契约通过"
```

赋予执行权限：

```bash
chmod +x infra/production/demo-single-node/test-demo-single-node.sh
```

- [ ] **Step 2: 运行测试确认失败**

Run: `infra/production/demo-single-node/test-demo-single-node.sh`
Expected: FAIL，输出 `缺少单机业务资源覆盖`

- [ ] **Step 3: 写业务资源覆盖**

创建 `infra/production/demo-single-node/resources.compose.yaml`：

```yaml
# 单台 4C16G 服务器的业务侧资源上限。
# api/worker 为估算值，须由目标机 30 分钟 soak 实测修正（见设计文档 4.2）。
services:
  api-blue:
    mem_limit: 2g
    cpus: 2.0
  worker-blue:
    mem_limit: 1536m
    cpus: 1.5
  platform-mysql:
    mem_limit: 1g
    cpus: 0.5
  web-blue:
    mem_limit: 64m
    cpus: 0.25
  edge:
    mem_limit: 64m
    cpus: 0.25
```

- [ ] **Step 4: 写 RAGFlow 资源覆盖**

创建 `infra/production/demo-single-node/ragflow-resources.compose.yaml`：

```yaml
# 单台 4C16G 服务器的 RAGFlow 侧资源上限与解析并发。
# 内存值以 30 分钟真实链路 soak 实测为准：合计峰值 7.23 GiB，API 单项 4.53 GiB。
services:
  ragflow-cpu:
    mem_limit: 5g
    # 单机上业务与 RAGFlow 共享 4 核；不限制 CPU 时文档解析会吃满整机，
    # 导致同一时刻的聊天与 SSE 明显卡顿。
    cpus: 2.0
    environment:
      MAX_CONCURRENT_TASKS: "2"
      MAX_CONCURRENT_EMBEDDINGS: "4"
      DOC_BULK_SIZE: "16"
  es01:
    mem_limit: 2g
    environment:
      ES_JAVA_OPTS: -Xms768m -Xmx768m
  mysql:
    mem_limit: 1g
  minio:
    mem_limit: 512m
  redis:
    mem_limit: 256m
```

- [ ] **Step 5: 写配置模板**

创建 `infra/production/demo-single-node/config.env.example`：

```bash
# 单台 4C16G demo 服务器的非敏感配置。凭据写入权限 0600 的 secrets.env。
COMMON_AGENT_INTEGRATION_MODE=real
COMMON_AGENT_CORS_ORIGINS=https://kb.xuanbai.tech
COMMON_AGENT_TRUSTED_PROXY_IPS=*
COMMON_AGENT_AUTH_COOKIE_SECURE=true
COMMON_AGENT_AUTH_SESSION_IDLE_SECONDS=1800
COMMON_AGENT_AUTH_SESSION_ABSOLUTE_SECONDS=43200
COMMON_AGENT_TOOL_EGRESS_ALLOWED_HOSTS=
COMMON_AGENT_TOOL_EGRESS_ALLOWED_CIDRS=
COMMON_AGENT_TOOL_EGRESS_HTTP_ALLOWED_HOSTS=
COMMON_AGENT_TOOL_EGRESS_ALLOW_LOOPBACK=false
COMMON_AGENT_TOOL_EGRESS_CONNECT_TIMEOUT_SECONDS=5
COMMON_AGENT_TOOL_EGRESS_READ_TIMEOUT_SECONDS=30
COMMON_AGENT_TOOL_EGRESS_CALL_TIMEOUT_SECONDS=60
COMMON_AGENT_TOOL_EGRESS_MAX_RESPONSE_BYTES=1048576
COMMON_AGENT_TOOL_EGRESS_MAX_CONCURRENCY=16
# 单机模式下业务通过 Docker 网络访问 RAGFlow Edge 容器名，不依赖真实 DNS。
RAGFLOW_BASE_URL=https://common-agent-production-ragflow-edge:9443
RAGFLOW_CA_BUNDLE=/run/common-agent/tls/ca-bundle.crt
RAGFLOW_EXPECTED_VERSION=v0.26.4
RAGFLOW_EMBEDDING_MODEL=text-embedding-v4@common-agent-embedding@OpenAI-API-Compatible
RAGFLOW_RERANK_MODEL=qwen3-rerank@common-agent-rerank@OpenAI-API-Compatible
RAGFLOW_TIMEOUT_SECONDS=120
BAILIAN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
BAILIAN_MODEL=qwen3-max

# secrets.env 需要的键名见 infra/production/env.example 末尾注释。
```

- [ ] **Step 6: 把新测试挂进主契约测试**

在 `infra/production/test-manage.sh` 末尾（`echo` 收尾行之前）追加：

```bash
"${SCRIPT_DIR}/demo-single-node/test-demo-single-node.sh" >/dev/null || \
  fail "单机部署配置契约未通过"
```

- [ ] **Step 7: 运行测试确认通过**

Run: `infra/production/demo-single-node/test-demo-single-node.sh`
Expected: PASS，输出 `单机部署配置契约通过`

Run: `infra/production/test-manage.sh`
Expected: PASS

Run: `shellcheck infra/production/demo-single-node/test-demo-single-node.sh`
Expected: 无输出

- [ ] **Step 8: 提交**

```bash
git add infra/production/demo-single-node/ infra/production/test-manage.sh
git commit -m "feat(production): 新增单机 demo 的资源覆盖与配置模板

按 30 分钟 soak 实测重新分配 4C16G 上的内存上限，并给 RAGFlow API 加
CPU 配额、下调解析并发，避免文档解析吃满整机导致聊天卡顿。业务侧
api/worker 为估算值，已在注释中标注须由目标机实测修正。"
```

---

### Task 5: 证书脚本

生成长效内部 CA（供 RAGFlow Edge）与 Let's Encrypt 公网证书（供业务 Edge），并提供续期入口。

**Files:**
- Create: `infra/production/demo-single-node/certs.sh`
- Create: `infra/production/demo-single-node/certbot-renew.service`
- Create: `infra/production/demo-single-node/certbot-renew.timer`
- Modify: `infra/production/demo-single-node/test-demo-single-node.sh`

**Interfaces:**
- Consumes: Task 1 的 `${STATE_ROOT}/acme` webroot
- Produces: `${STATE_ROOT}/tls/` 下的 `ca.key`、`ca.crt`、`ca-bundle.crt`、`ragflow.crt`、`ragflow.key`、`edge.crt`、`edge.key`

**关于 `ca.crt` 的双重用途：** `manage.sh:381` 的 `preflight` 会执行
`openssl verify -CAfile "${TLS_ROOT}/ca.crt" "${TLS_ROOT}/edge.crt"`。业务 Edge 用的是
Let's Encrypt 证书，其签发链根是 ISRG Root X1，**用纯内部 CA 验证必定失败**。因此
`ca.crt` 必须同时包含内部 CA 与系统信任根，`openssl verify -CAfile` 支持多证书文件。
两个文件的职责固定为：

- `ca.crt`：内部 CA + 系统信任根，供 `preflight` 验证 `edge.crt` 与 `ragflow.crt`
- `ca-bundle.crt`：系统信任根 + 内部 CA，挂进 api/worker，用于验证 RAGFlow 与百炼

- [ ] **Step 1: 写失败的契约断言**

在 `infra/production/demo-single-node/test-demo-single-node.sh` 的 `echo "单机部署配置契约通过"` 之前插入：

```bash
CERTS="${SCRIPT_DIR}/certs.sh"
MANAGER="${SCRIPT_DIR}/../manage.sh"
[[ -x "${CERTS}" ]] || fail "缺少可执行的证书脚本"
for action in internal-ca issue renew; do
  grep -Fq "${action})" "${CERTS}" || fail "证书脚本缺少 ${action} 动作"
done
# 内部 CA 必须长效，否则 30 天后 RAGFlow 调用全部失败。
grep -Fq '-days "${INTERNAL_CA_DAYS}"' "${CERTS}" || fail "内部 CA 没有使用长效有效期变量"
grep -Fq 'INTERNAL_CA_DAYS=3650' "${CERTS}" || fail "内部 CA 有效期过短"
grep -Fq 'common-agent-production-ragflow-edge' "${CERTS}" || \
  fail "内部证书 SAN 没有使用 RAGFlow Edge 容器名"
# docker secret 在容器启动时拷贝，续期后必须重建 edge 才生效。
grep -Fq 'edge-recreate' "${CERTS}" || fail "续期后没有调用 Edge 重建入口"
grep -Fq 'up -d --no-deps --force-recreate edge' "${MANAGER}" || \
  fail "发布入口缺少 Edge 重建实现，续期后新证书不会生效"
[[ -f "${SCRIPT_DIR}/certbot-renew.timer" ]] || fail "缺少续期定时器"
[[ -f "${SCRIPT_DIR}/certbot-renew.service" ]] || fail "缺少续期服务单元"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `infra/production/demo-single-node/test-demo-single-node.sh`
Expected: FAIL，输出 `缺少可执行的证书脚本`

- [ ] **Step 3: 写证书脚本**

创建 `infra/production/demo-single-node/certs.sh`：

```bash
#!/usr/bin/env bash
# 单机 demo 的证书管理：长效内部 CA + Let's Encrypt 公网证书。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PRODUCTION_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPOSITORY_ROOT="$(cd "${PRODUCTION_DIR}/../.." && pwd)"
STATE_ROOT="${COMMON_AGENT_PRODUCTION_STATE_ROOT:-${REPOSITORY_ROOT}/.local/production}"
TLS_ROOT="${STATE_ROOT}/tls"
ACME_ROOT="${STATE_ROOT}/acme"
PUBLIC_DOMAIN="${COMMON_AGENT_PUBLIC_DOMAIN:?COMMON_AGENT_PUBLIC_DOMAIN is required}"
CERTBOT_EMAIL="${COMMON_AGENT_CERTBOT_EMAIL:?COMMON_AGENT_CERTBOT_EMAIL is required}"
LETSENCRYPT_LIVE="/etc/letsencrypt/live/${PUBLIC_DOMAIN}"
SYSTEM_CA_BUNDLE="${COMMON_AGENT_SYSTEM_CA_BUNDLE:-/etc/ssl/certs/ca-certificates.crt}"
INTERNAL_CA_DAYS=3650

fail() {
  echo "$1" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "缺少工具：$1"
}

# 内部 CA 与 RAGFlow Edge 证书；SAN 使用容器名，不依赖真实 DNS。
internal_ca() {
  require_command openssl
  mkdir -p "${TLS_ROOT}"
  chmod 700 "${TLS_ROOT}"
  [[ ! -f "${TLS_ROOT}/ca.key" ]] || fail "内部 CA 已存在，重建会使既有证书失效"

  openssl req -x509 -newkey rsa:3072 -sha256 -nodes -days "${INTERNAL_CA_DAYS}" \
    -subj '/CN=common-agent-demo-internal-ca' \
    -keyout "${TLS_ROOT}/internal-ca.key" -out "${TLS_ROOT}/internal-ca.crt"
  openssl req -new -newkey rsa:3072 -sha256 -nodes \
    -subj '/CN=common-agent-production-ragflow-edge' \
    -addext 'subjectAltName=DNS:common-agent-production-ragflow-edge' \
    -keyout "${TLS_ROOT}/ragflow.key" -out "${TLS_ROOT}/ragflow.csr"
  openssl x509 -req -sha256 -days "${INTERNAL_CA_DAYS}" -copy_extensions copyall \
    -CA "${TLS_ROOT}/internal-ca.crt" -CAkey "${TLS_ROOT}/internal-ca.key" -CAcreateserial \
    -in "${TLS_ROOT}/ragflow.csr" -out "${TLS_ROOT}/ragflow.crt"
  rm -f "${TLS_ROOT}/ragflow.csr"

  build_ca_files
  echo "内部 CA 与 RAGFlow 证书已生成，有效期 ${INTERNAL_CA_DAYS} 天"
}

# ca.crt 供 preflight 校验两张证书，因此必须同时包含内部 CA 与系统信任根；
# ca-bundle.crt 挂进 api/worker，用于验证 RAGFlow 与百炼。
build_ca_files() {
  [[ -f "${SYSTEM_CA_BUNDLE}" ]] || fail "系统信任根不存在：${SYSTEM_CA_BUNDLE}"
  cat "${TLS_ROOT}/internal-ca.crt" "${SYSTEM_CA_BUNDLE}" >"${TLS_ROOT}/ca.crt"
  cat "${SYSTEM_CA_BUNDLE}" "${TLS_ROOT}/internal-ca.crt" >"${TLS_ROOT}/ca-bundle.crt"
  chmod 600 "${TLS_ROOT}"/*.key
  chmod 644 "${TLS_ROOT}"/*.crt
}

# 把 certbot 产物复制成 compose secret 期望的固定路径。
install_public_cert() {
  [[ -f "${LETSENCRYPT_LIVE}/fullchain.pem" ]] || fail "未找到签发结果：${LETSENCRYPT_LIVE}"
  cp "${LETSENCRYPT_LIVE}/fullchain.pem" "${TLS_ROOT}/edge.crt"
  cp "${LETSENCRYPT_LIVE}/privkey.pem" "${TLS_ROOT}/edge.key"
  chmod 600 "${TLS_ROOT}/edge.key"
  chmod 644 "${TLS_ROOT}/edge.crt"
}

# docker secret 在容器启动时拷贝，续期后必须重建 edge 才会加载新证书。
reload_edge() {
  COMMON_AGENT_PRODUCTION_STATE_ROOT="${STATE_ROOT}" \
    "${PRODUCTION_DIR}/manage.sh" edge-recreate
}

issue() {
  require_command certbot
  [[ -d "${ACME_ROOT}/.well-known/acme-challenge" ]] || \
    fail "ACME webroot 不存在，请先执行一次 manage.sh preflight"
  certbot certonly --webroot -w "${ACME_ROOT}" \
    -d "${PUBLIC_DOMAIN}" \
    --email "${CERTBOT_EMAIL}" \
    --agree-tos --no-eff-email --non-interactive
  install_public_cert
  echo "公网证书已签发：${PUBLIC_DOMAIN}"
}

renew() {
  require_command certbot
  local before after
  before="$(sha256sum "${LETSENCRYPT_LIVE}/fullchain.pem" 2>/dev/null | cut -d' ' -f1 || true)"
  certbot renew --webroot -w "${ACME_ROOT}" --non-interactive
  after="$(sha256sum "${LETSENCRYPT_LIVE}/fullchain.pem" 2>/dev/null | cut -d' ' -f1 || true)"
  if [[ "${before}" == "${after}" ]]; then
    echo "证书未到续期窗口，无需重建 Edge"
    return
  fi
  install_public_cert
  reload_edge
  echo "证书已续期并重建 Edge：${PUBLIC_DOMAIN}"
}

case "${1:-}" in
  internal-ca) internal_ca ;;
  issue) issue ;;
  renew) renew ;;
  *)
    echo "用法: $0 {internal-ca|issue|renew}" >&2
    exit 1
    ;;
esac
```

赋予执行权限：

```bash
chmod +x infra/production/demo-single-node/certs.sh
```

- [ ] **Step 4: 给 manage.sh 增加 edge-recreate 动作**

`certs.sh` 的 `reload_edge` 需要一个不走完整发布流程、只重建 Edge 的入口。在 `manage.sh`
的 `switch_edge()` 函数之后插入：

```bash
# 证书续期后重建 Edge：docker secret 只在容器启动时拷贝，reload 不会加载新证书。
edge_recreate() {
  guard_docker_context
  load_state
  [[ -n "${active_release}" ]] || fail "当前没有 active release"
  load_release "${active_release}"
  render_edge_config "${DEPLOY_SLOT}"
  compose_loaded_release up -d --no-deps --force-recreate edge
  wait_for_service edge 60
  echo "Edge 已使用当前证书重建"
}
```

在 `manage.sh` 末尾的 `case` 分发中，`init-tls) init_tls ;;` 之后插入：

```bash
  edge-recreate) edge_recreate ;;
```

并把 `usage()` 的提示字符串改为：

```bash
  echo "用法: $0 {build|init-tls|edge-recreate|preflight|migrate|rollout|verify|rollback|status|down|drill}" >&2
```

- [ ] **Step 5: 写 systemd 单元**

创建 `infra/production/demo-single-node/certbot-renew.service`：

```ini
[Unit]
Description=common-agent demo 证书续期
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
Environment=COMMON_AGENT_PUBLIC_DOMAIN=kb.xuanbai.tech
Environment=COMMON_AGENT_CERTBOT_EMAIL=REPLACE_WITH_YOUR_EMAIL
Environment=COMMON_AGENT_PRODUCTION_STATE_ROOT=/var/lib/common-agent/production
Environment=COMMON_AGENT_PRODUCTION_DOCKER_CONTEXT=default
ExecStart=/opt/common-agent/infra/production/demo-single-node/certs.sh renew
```

创建 `infra/production/demo-single-node/certbot-renew.timer`：

```ini
[Unit]
Description=每周检查 common-agent demo 证书续期

[Timer]
OnCalendar=weekly
RandomizedDelaySec=3600
Persistent=true

[Install]
WantedBy=timers.target
```

- [ ] **Step 6: 运行测试确认通过**

Run: `infra/production/demo-single-node/test-demo-single-node.sh`
Expected: PASS

Run: `infra/production/test-manage.sh`
Expected: PASS

Run: `shellcheck infra/production/demo-single-node/certs.sh infra/production/manage.sh`
Expected: 无输出

- [ ] **Step 7: 验证内部 CA 真的能签出可验证的证书**

在临时目录实际跑一遍，确认 `preflight` 用的 `openssl verify` 能通过：

```bash
TEMP_STATE="$(mktemp -d)"
COMMON_AGENT_PRODUCTION_STATE_ROOT="${TEMP_STATE}" \
COMMON_AGENT_PUBLIC_DOMAIN=kb.xuanbai.tech \
COMMON_AGENT_CERTBOT_EMAIL=test@example.com \
COMMON_AGENT_SYSTEM_CA_BUNDLE="$(python3 -c 'import certifi; print(certifi.where())')" \
  infra/production/demo-single-node/certs.sh internal-ca
openssl verify -CAfile "${TEMP_STATE}/tls/ca.crt" "${TEMP_STATE}/tls/ragflow.crt"
rm -rf "${TEMP_STATE}"
```

Expected: 输出以 `: OK` 结尾，确认 `ca.crt` 能验证 `ragflow.crt`

- [ ] **Step 8: 提交**

```bash
git add infra/production/demo-single-node/ infra/production/manage.sh
git commit -m "feat(production): 单机 demo 的证书签发与自动续期

内部 CA 与 RAGFlow Edge 证书改为 10 年有效期，SAN 使用容器名，避免
30 天后 RAGFlow 调用全部失败。

ca.crt 同时包含内部 CA 与系统信任根：preflight 用它校验 edge.crt，
而 edge.crt 由 Let's Encrypt 签发，纯内部 CA 无法验证。

新增 edge-recreate 动作供续期后调用——docker secret 只在容器启动时
拷贝，nginx reload 不会加载新证书。"
```

---

### Task 6: 验证 drill 在单槽下跑通

**已核实：`drill.sh` 不需要修改。** 它对槽的断言只有两处
（`drill.sh:204`、`drill.sh:440`），都是 `[[ "${active_slot}" == "blue" || "${active_slot}" == "green" ]]`，
只校验槽合法而不校验槽发生变化，单槽下取 `blue` 同样通过。
`exercise_failure_and_rollback`（`drill.sh:430-451`）的逻辑在单槽下也成立：停掉 active api
容器后 Edge 返回 502，`curl --fail` 失败，断言"流量不通过失效 API"照常满足；随后 `rollback`
用 `previous_release` 重建同一槽。

本任务的工作是**跑通验证**，不是改断言。若跑不通再按实际失败点修改。

**Files:**
- Test: 完整执行 `infra/production/manage.sh drill`
- Modify（仅当验证失败时）: `infra/production/drill.sh`

**Interfaces:**
- Consumes: Task 2、Task 3 的单槽 `rollout`/`rollback`
- Produces: 实测停机时长，写入 Task 7 的 runbook

- [ ] **Step 1: 确认 drill 的槽断言无需改动**

Run: `grep -n 'active_slot.*==.*blue' infra/production/drill.sh`
Expected: 两处输出，均为 `blue || green` 形式的合法性校验，无"槽必须变化"断言。
若与此不符，说明代码已变化，按实际情况调整后再继续。

- [ ] **Step 2: 启动本机 RAGFlow 稳定栈**

Run: `infra/ragflow/manage.sh up`
Expected: 五个容器全部 healthy

- [ ] **Step 3: 跑完整 drill**

Run: `infra/production/manage.sh drill`
Expected: 走完两次构建、迁移、单槽发布、Chromium 五入口验收、攻击矩阵、k6 读容量、SSE 128 路、Worker 容量与崩溃接管、故障注入回滚，最终输出 `本地双节点生产同路径演练通过`

若失败，按 `superpowers:systematic-debugging` 定位，不得跳过或放宽断言。

- [ ] **Step 4: 记录发布期间的停机行为**

在 drill 输出中确认：单槽 rollout 期间 Edge 返回 502 而非连接被拒绝，发布完成后
`verify_edge` 通过。用下面的命令量出实际停机时长，结果写进 Task 7 的 runbook：

```bash
# 另开一个终端，在 rollout 执行期间持续探测，统计不可用秒数
while true; do
  if curl --fail --silent --max-time 2 --noproxy '*' \
    --cacert .local/production/tls/ca.crt \
    --resolve 'common-agent.test:18443:127.0.0.1' \
    'https://common-agent.test:18443/api/v1/system/health' >/dev/null 2>&1; then
    printf 'up %s\n' "$(date +%s)"
  else
    printf 'DOWN %s\n' "$(date +%s)"
  fi
  sleep 1
done
```

- [ ] **Step 5: 清理本轮资源**

```bash
infra/production/manage.sh down
infra/ragflow/manage.sh stop
```

确认没有本项目容器残留：

Run: `docker --context colima-common-agent-dev ps -a --filter name=common-agent`
Expected: 无运行中容器

- [ ] **Step 6: 提交（仅当 drill.sh 实际被修改时）**

若 Step 3 全绿且未改动任何文件，本任务无提交，直接进入 Task 7。
若因实际失败修改了 `drill.sh`，按实际改动提交：

```bash
git add infra/production/drill.sh
git commit -m "test(production): 修正演练在单槽发布下的断言

<写明实际失败点与修改原因>"
```

---

### Task 7: 部署 runbook 与路线图记录

**Files:**
- Create: `infra/production/demo-single-node/README.md`
- Modify: `docs/development-roadmap-v3.md`

**Interfaces:**
- Consumes: Task 1-6 的全部产物
- Produces: 无

- [ ] **Step 1: 写 runbook**

创建 `infra/production/demo-single-node/README.md`。以下每一节都必须写出可直接复制执行的
命令，不允许只写要点。

**1. 服务器准备**

```bash
# 装 Docker 官方源版本（Ubuntu 仓库里的 docker.io 版本偏旧）
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker ubuntu   # 重新登录后生效
sudo systemctl enable --now docker

# 现有 swap 仅 1.9G，扩到 4G
sudo swapoff /swap.img
sudo fallocate -l 4G /swap.img
sudo chmod 600 /swap.img
sudo mkswap /swap.img
sudo swapon /swap.img
swapon --show

# 防火墙只放行 22/80/443（云厂商安全组也要同步放行）
sudo ufw allow 22/tcp && sudo ufw allow 80/tcp && sudo ufw allow 443/tcp
sudo ufw --force enable

# 仓库位置
sudo mkdir -p /opt/common-agent && sudo chown ubuntu:ubuntu /opt/common-agent
```

**2. 环境变量**

写入 `/etc/common-agent/deploy.env` 并在每次操作前 `source`：

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
export RAGFLOW_DOCKER_CONTEXT=default
```

**3. 首次部署顺序**

```bash
infra/ragflow/manage.sh up                          # 起 RAGFlow 栈
infra/production/demo-single-node/certs.sh internal-ca   # 内部 CA + RAGFlow 证书
infra/production/manage.sh build
infra/production/manage.sh preflight                # 会创建 ACME webroot
infra/production/demo-single-node/certs.sh issue    # 签发公网证书
infra/production/manage.sh migrate
infra/production/manage.sh rollout
infra/production/manage.sh verify
```

> **禁止在服务器上执行 `manage.sh init-tls`。** 它会用 30 天自签材料覆盖
> `tls/` 下的全部证书，包括刚签发的 Let's Encrypt 证书。该命令仅供本机 drill。

**4. 叠加资源覆盖**

说明业务栈与 RAGFlow 栈分别如何用 `-f` 追加 `resources.compose.yaml` 与
`ragflow-resources.compose.yaml`，并给出验证 `mem_limit` 已生效的
`docker inspect --format '{{.HostConfig.Memory}}'` 命令。

**5. 日常发布与回滚**

`build` → `migrate` → `rollout`，失败时 `rollback`。写明 Task 6 Step 4 实测的停机时长，
并提醒发布窗口内服务不可用。

**6. 创建客户账号**

用首位 Owner 登录后台，按租户为每家客户建独立账号，说明客户之间知识库、会话与数字员工
完全隔离。给出提前批量建号的建议。

**7. Demo Seed 重放**

数据卷重置后如何恢复预置数字员工与示例工作流。

**8. 证书维护**

```bash
sudo cp infra/production/demo-single-node/certbot-renew.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now certbot-renew.timer
systemctl list-timers certbot-renew.timer          # 确认已排程
openssl x509 -enddate -noout -in /var/lib/common-agent/production/tls/edge.crt   # 查到期日
```

内部 CA 到期日同样用上面的命令查 `ragflow.crt`，记入本节。

**9. 磁盘与镜像清理**

列出旧 release 镜像的查询与删除命令，强调只删本项目自建镜像，不碰 RAGFlow 等仍在复用的
官方基础镜像。

**10. 资源实测**

在目标机跑 `resource_monitor.py` 30 分钟 soak 的命令，以及如何用结果修正
`resources.compose.yaml` 与设计文档 4.2 节的估算值。

- [ ] **Step 2: 更新路线图**

在 `docs/development-roadmap-v3.md` 新增单机 demo 部署任务条目，状态设为 `🔍 待验收`，并写明：

- 已完成：Task 1-6 的实现与本机 drill 通过
- 待解除条件：服务器尚未租用，公网真实链路验收、30 分钟 soak 与证书签发未执行
- 业务侧 `mem_limit` 仍为估算值，实测后须回写 Task 4 的两个覆盖片段与设计文档 4.2 节

- [ ] **Step 3: 校验文档链接与格式**

Run: `infra/production/test-manage.sh`
Expected: PASS

- [ ] **Step 4: 提交**

```bash
git add infra/production/demo-single-node/README.md docs/development-roadmap-v3.md
git commit -m "docs(production): 单机 demo 部署 runbook 与路线图记录

覆盖服务器准备、首次部署、日常发布回滚、客户账号创建、证书维护、
磁盘清理与资源实测。路线图标记为待验收：服务器未租，公网真实链路
验收与 soak 尚未执行。"
```

---

## 服务器就绪后的验收（不属于上述任务，需机器到位后执行）

以下步骤依赖真实服务器，无法在本机完成，作为独立验收阶段执行：

1. 按 runbook 完成首次部署，`certs.sh issue` 取得 `kb.xuanbai.tech` 正式证书
2. Playwright 从 `https://kb.xuanbai.tech` 走完整链路：登录 → 建知识库 → 上传真实文档 →
   RAGFlow 解析完成 → 建数字员工绑定知识库 → 两轮带引用对话 → 手动运行工作流
3. `resource_monitor.py` 跑 30 分钟 soak，覆盖"解析文档同时保持聊天"，确认无 OOM 与容器重启
4. 用 soak 实测值回写 `resources.compose.yaml` 与设计文档 4.2 节，去掉"估算"标注
5. 真实执行一次 `rollout` 与一次 `rollback`，记录停机时长
6. 强制触发一次 `certs.sh renew`，确认 Edge 重建后新证书生效
7. 全部通过后把路线图任务改为 `✅ 已完成`，并合并回 `main`
