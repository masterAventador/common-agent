#!/usr/bin/env bash
# shellcheck disable=SC2016 # Contract assertions intentionally match literal shell expressions.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
MANAGER="${SCRIPT_DIR}/manage.sh"
DRILL="${SCRIPT_DIR}/drill.sh"
COMPOSE_FILE="${SCRIPT_DIR}/compose.yaml"
LOAD_TEST="${SCRIPT_DIR}/load-test.js"
SSE_LOAD_TEST="${SCRIPT_DIR}/sse_load_test.py"
WORKER_LOAD_TEST="${SCRIPT_DIR}/worker_load_test.py"
SLO_GATE="${SCRIPT_DIR}/slo_gate.py"
SLO_POLICY="${SCRIPT_DIR}/slo-policy.json"
RESOURCE_MONITOR="${SCRIPT_DIR}/resource_monitor.py"

fail() {
  echo "$1" >&2
  exit 1
}

[[ -x "${MANAGER}" ]] || fail "缺少可执行的生产发布管理入口"
[[ -x "${DRILL}" ]] || fail "缺少可执行的隔离生产发布演练"
[[ -f "${COMPOSE_FILE}" ]] || fail "缺少双槽生产 Compose"
[[ -f "${LOAD_TEST}" ]] || fail "缺少生产 TLS Edge 容量压测入口"
[[ -f "${SSE_LOAD_TEST}" ]] || fail "缺少生产 SSE 长连接压测入口"
[[ -f "${WORKER_LOAD_TEST}" ]] || fail "缺少生产 Worker 容量与故障恢复压测入口"
[[ -f "${SLO_GATE}" ]] || fail "缺少生产 SLO 门禁"
[[ -f "${SLO_POLICY}" ]] || fail "缺少版本化 SLO 与告警策略"
[[ -f "${RESOURCE_MONITOR}" ]] || fail "缺少生产资源监视器"
[[ -f "${SCRIPT_DIR}/ragflow-node.local.compose.yaml" ]] || fail "缺少本地双节点网络覆盖层"
[[ -f "${REPOSITORY_ROOT}/backend/Dockerfile" ]] || fail "缺少后端生产镜像"
[[ -f "${REPOSITORY_ROOT}/frontend/Dockerfile" ]] || fail "缺少前端生产镜像"
[[ -f "${REPOSITORY_ROOT}/backend/.dockerignore" ]] || fail "后端构建缺少上下文排除规则"
[[ -f "${REPOSITORY_ROOT}/frontend/.dockerignore" ]] || fail "前端构建缺少上下文排除规则"

for action in build init-tls preflight migrate rollout verify rollback status down drill; do
  grep -Fq "${action})" "${MANAGER}" || fail "生产发布入口缺少 ${action} 动作"
done

for expected in \
  'COMMON_AGENT_RUNTIME_ENV=production' \
  'alembic upgrade head' \
  'COMMON_AGENT_REMOTE_DEPLOY_CONFIRMATION' \
  'deploy-common-agent-to-approved-remote' \
  'COMMON_AGENT_PUBLIC_BASE_URL' \
  'previous_release' \
  'active_release' \
  'docker image inspect' \
  'wait_for_ragflow_edge' \
  'verify_local_ragflow_tls_material' \
  'COMMON_AGENT_RAGFLOW_EDGE_MODE' \
  'external' \
  'local-shared-network' \
  'sha256:'; do
  grep -Fq "${expected}" "${MANAGER}" || fail "生产发布入口缺少契约：${expected}"
done

grep -Fq 'COMMON_AGENT_RAGFLOW_HTTPS_BIND' "${SCRIPT_DIR}/ragflow-node.compose.yaml" || \
  fail "RAGFlow 节点没有私网 HTTPS 发布入口"
if grep -Fq 'app-private' "${SCRIPT_DIR}/ragflow-node.compose.yaml"; then
  fail "跨节点 RAGFlow 基础编排不得依赖业务节点 Docker 网络"
fi
grep -Fq 'app-private' "${SCRIPT_DIR}/ragflow-node.local.compose.yaml" || \
  fail "本地演练覆盖层没有接入业务私网"
[[ "$(grep -Fc '    - app-egress' "${COMPOSE_FILE}")" == "2" ]] || \
  fail "生产 API 与 Worker 没有独立出站网络"
grep -Fq '  app-egress:' "${COMPOSE_FILE}" || fail "生产 Compose 缺少出站网络定义"

grep -Fq 'listen 9080;' "${SCRIPT_DIR}/edge.conf.template" || \
  fail "Edge 模板缺少 ACME 与跳转用的 HTTP 监听"
grep -Fq '/.well-known/acme-challenge/' "${SCRIPT_DIR}/edge.conf.template" || \
  fail "Edge 模板缺少 ACME 挑战路径"
grep -Fq 'return 301 https://$host$request_uri;' "${SCRIPT_DIR}/edge.conf.template" || \
  fail "Edge 模板缺少 HTTP 到 HTTPS 跳转"
grep -Fq ':9080' "${COMPOSE_FILE}" || fail "Edge 容器没有发布 HTTP 端口"
grep -Fq 'COMMON_AGENT_ACME_ROOT' "${COMPOSE_FILE}" || fail "Edge 容器没有挂载 ACME webroot"
grep -Fq 'COMMON_AGENT_ACME_ROOT' "${MANAGER}" || fail "发布入口没有传递 ACME webroot"

grep -Fq 'DEPLOY_SLOT="blue"' "${MANAGER}" || fail "发布入口没有固定单槽"
if grep -Eq 'target_slot="(blue|green)"' "${MANAGER}"; then
  fail "单槽发布不得保留蓝绿轮换"
fi
grep -Fq '请执行 rollback 恢复上一 release' "${MANAGER}" || \
  fail "单槽发布验证失败后没有提示回滚路径"
grep -Fq 'switch_edge "${DEPLOY_SLOT}"' "${MANAGER}" || \
  fail "单槽发布没有重载 Edge，容器重建后会指向失效 IP"

if grep -Fq 'rollback_slot' "${MANAGER}"; then
  fail "单槽回滚不得保留槽切换变量"
fi
grep -Fq '代码与流量已回滚' "${MANAGER}" || fail "回滚没有输出结果说明"

# 应用在 production 下强制要求这四个加密密钥，缺任一项容器会在启动时崩溃。
# preflight 必须提前拦截，演练必须真实生成，否则 rollout 到一半才失败、单槽下服务直接不可用。
for credential_key in \
  'COMMON_AGENT_TOOL_CREDENTIAL_KEYS' \
  'COMMON_AGENT_TOOL_CREDENTIAL_ACTIVE_KEY_ID' \
  'COMMON_AGENT_RAGFLOW_IDENTITY_KEYS' \
  'COMMON_AGENT_RAGFLOW_IDENTITY_ACTIVE_KEY_ID'; do
  grep -Fq "${credential_key}" "${MANAGER}" || \
    fail "preflight 没有检查生产必需的加密密钥：${credential_key}"
  grep -Fq "${credential_key}" "${DRILL}" || \
    fail "演练没有生成生产必需的加密密钥：${credential_key}"
done

for expected in \
  'read_only: true' \
  'no-new-privileges:true' \
  'cap_drop:' \
  'healthcheck:' \
  'internal: true' \
  'common-agent-production-edge' \
  'common-agent-production-platform-mysql'; do
  grep -Fq "${expected}" "${COMPOSE_FILE}" || fail "生产 Compose 缺少安全边界：${expected}"
done

if grep -Eq 'image:[[:space:]]+[^#[:space:]]+:latest' "${COMPOSE_FILE}"; then
  fail "生产 Compose 禁止 latest 镜像"
fi

for dockerfile in "${REPOSITORY_ROOT}/backend/Dockerfile" "${REPOSITORY_ROOT}/frontend/Dockerfile"; do
  grep -Eq '^FROM .+@sha256:[0-9a-f]{64}' "${dockerfile}" || fail "基础镜像没有固定 digest"
  grep -Eq '^USER [1-9][0-9]*' "${dockerfile}" || fail "生产镜像没有使用非 root 用户"
  grep -Fq 'HEALTHCHECK' "${dockerfile}" || fail "生产镜像缺少健康检查"
done

for ignore_file in "${REPOSITORY_ROOT}/backend/.dockerignore" "${REPOSITORY_ROOT}/frontend/.dockerignore"; do
  grep -Fq '.env' "${ignore_file}" || fail "Docker 构建上下文没有排除环境凭据"
  grep -Fq '.git' "${ignore_file}" || fail "Docker 构建上下文没有排除 Git 数据"
done

grep -Fq 'ssl_protocols TLSv1.2 TLSv1.3' "${SCRIPT_DIR}/edge.conf.template" || \
  fail "TLS 边缘入口没有固定安全协议"
grep -Fq 'client_max_body_size 24m' "${SCRIPT_DIR}/edge.conf.template" || \
  fail "TLS 边缘入口没有为 20 MiB 文档保留有界 multipart 空间"
grep -Fq 'server_name {{PUBLIC_DOMAIN}}' "${SCRIPT_DIR}/edge.conf.template" || \
  fail "TLS 边缘入口没有绑定正式域名"
grep -Fq '$host != "{{PUBLIC_DOMAIN}}"' "${SCRIPT_DIR}/edge.conf.template" || \
  fail "TLS 边缘入口没有拒绝伪造 Host"
grep -Fq '$request_uri ~* "^/[^?]*(?:\.\.|%2e%2e|\.%2e|%2e\.)' \
  "${SCRIPT_DIR}/edge.conf.template" || \
  fail "TLS 边缘入口没有在 URI 规范化前拒绝路径穿越点段"
grep -Fq -- '--header=Host: ${COMMON_AGENT_PUBLIC_DOMAIN:' "${COMPOSE_FILE}" || \
  fail "TLS Edge 健康检查没有使用正式域名"
for security_header in \
  'Strict-Transport-Security' \
  'Content-Security-Policy' \
  'X-Content-Type-Options' \
  'X-Frame-Options' \
  'Referrer-Policy' \
  'Permissions-Policy'; do
  grep -Fq "${security_header}" "${SCRIPT_DIR}/edge.conf.template" || \
    fail "TLS 边缘入口缺少浏览器安全响应头：${security_header}"
done
grep -Fq 'proxy_buffering off' "${SCRIPT_DIR}/web.conf.template" || \
  fail "前端代理没有关闭 SSE 缓冲"
grep -Fq 'proxy_read_timeout 600s' "${SCRIPT_DIR}/web.conf.template" || \
  fail "前端代理没有为生产 SSE 长连接保留完整验收窗口"
grep -Fq 'backup-recovery' "${DRILL}" || fail "生产演练没有复用正式页面恢复验证"
grep -Fq 'production-request-limits.spec.ts' "${DRILL}" || \
  fail "生产演练没有从正式浏览器与 TLS Edge 验证请求体边界"
grep -Fq 'production-security-headers.spec.ts' "${DRILL}" || \
  fail "生产演练没有从正式浏览器验证安全响应头与页面兼容性"
grep -Fq 'production-security-attacks.spec.ts' "${DRILL}" || \
  fail "生产演练没有从 TLS Edge 验证权限与输入攻击矩阵"
grep -Fq 'COMMON_AGENT_E2E_MVP_MODEL_NAME' "${DRILL}" || \
  fail "生产演练没有从页面验证新租户模型"
grep -Fq 'mvp-acceptance.spec.ts' "${DRILL}" || \
  fail "生产演练没有执行模型到工作流全链"
grep -Fq 'audit.spec.ts' "${DRILL}" || \
  fail "生产演练没有从正式页面验证审计链"
grep -Fq 'k6 run' "${DRILL}" || fail "生产演练没有执行正式容量压测"
grep -Fq 'sse_load_test.py' "${DRILL}" || fail "生产演练没有执行 SSE 长连接压测"
grep -Fq 'worker_load_test.py' "${DRILL}" || fail "生产演练没有执行 Worker 容量压测"
grep -Fq 'resource_monitor.py' "${DRILL}" || fail "生产演练没有持续采集容器资源"
grep -Fq 'slo_gate.py' "${DRILL}" || fail "生产演练没有执行统一 SLO/告警门禁"
grep -Fq 'COMMON_AGENT_K6_RESULT_FILE' "${DRILL}" || \
  fail "生产演练没有保留 k6 SLO 证据"
grep -Fq 'COMMON_AGENT_SSE_RESULT_FILE' "${DRILL}" || \
  fail "生产演练没有保留 SSE SLO 证据"
grep -Fq 'max_attempts' "${DRILL}" || \
  fail "生产演练没有保留 Worker 崩溃接管证据"
for drill_sse_contract in \
  'COMMON_AGENT_SSE_CONNECTIONS=128' \
  'COMMON_AGENT_SSE_DURATION_SECONDS=360' \
  'COMMON_AGENT_SSE_RAMP_CONNECTIONS_PER_SECOND=16' \
  'COMMON_AGENT_SSE_HANDSHAKE_P95_MS=500'; do
  grep -Fq "${drill_sse_contract}" "${DRILL}" || \
    fail "生产演练缺少 SSE 长连接目标：${drill_sse_contract}"
done
for drill_worker_contract in \
  'COMMON_AGENT_WORKER_CAPACITY_TASKS=24' \
  'COMMON_AGENT_WORKER_RECOVERY_TASKS=8' \
  'COMMON_AGENT_WORKER_WRITE_CONCURRENCY=12' \
  'COMMON_AGENT_WORKER_ENQUEUE_P95_MS=1000' \
  'COMMON_AGENT_WORKER_DRAIN_TIMEOUT_SECONDS=120' \
  'COMMON_AGENT_WORKER_RECOVERY_TIMEOUT_SECONDS=300' \
  'durable_tasks' \
  'stop --time 0' \
  'aggregate-ids' \
  'MAX(attempts)'; do
  grep -Fq "${drill_worker_contract}" "${DRILL}" || \
    fail "生产演练缺少 Worker 容量/恢复目标：${drill_worker_contract}"
done
grep -Fq 'worker_task_diagnostics' "${DRILL}" || \
  fail "生产演练没有在 Worker 超时前保留任务状态诊断"
for capacity_contract in \
  'constant-arrival-rate' \
  'rate<0.001' \
  'p(95)<500' \
  'p(99)<1000' \
  'count==0' \
  'COMMON_AGENT_PERFORMANCE_BASE_URL'; do
  grep -Fq "${capacity_contract}" "${LOAD_TEST}" || \
    fail "生产容量压测缺少关闭失败契约：${capacity_contract}"
done
for slo_evidence_contract in \
  'handleSummary' \
  'summaryTrendStats' \
  'COMMON_AGENT_K6_RESULT_FILE' \
  'http_req_failed' \
  'dropped_iterations' \
  'p(95)' \
  'p(99)'; do
  grep -Fq "${slo_evidence_contract}" "${LOAD_TEST}" || \
    fail "k6 没有产出完整 SLO 证据：${slo_evidence_contract}"
done
grep -Fq '[[ -s "${K6_RESULT}" ]]' "${DRILL}" || \
  fail "生产演练会吞掉 k6 summary hook 失败"
for sse_contract in \
  'COMMON_AGENT_SSE_CONNECTIONS' \
  'COMMON_AGENT_SSE_DURATION_SECONDS' \
  'COMMON_AGENT_SSE_RAMP_CONNECTIONS_PER_SECOND' \
  'COMMON_AGENT_SSE_HANDSHAKE_P95_MS' \
  'text/event-stream' \
  'unexpected_disconnects' \
  'requests_in_flight'; do
  grep -Fq "${sse_contract}" "${SSE_LOAD_TEST}" || \
    fail "生产 SSE 长连接压测缺少关闭失败契约：${sse_contract}"
done
for worker_contract in \
  'COMMON_AGENT_WORKER_CAPACITY_TASKS' \
  'COMMON_AGENT_WORKER_RECOVERY_TASKS' \
  'COMMON_AGENT_WORKER_WRITE_CONCURRENCY' \
  'COMMON_AGENT_WORKER_ENQUEUE_P95_MS' \
  'COMMON_AGENT_WORKER_DRAIN_TIMEOUT_SECONDS' \
  'COMMON_AGENT_WORKER_RECOVERY_TIMEOUT_SECONDS' \
  'conversation-turns' \
  'completed_tasks' \
  'aggregate_ids'; do
  grep -Fq "${worker_contract}" "${WORKER_LOAD_TEST}" || \
    fail "生产 Worker 压测缺少关闭失败契约：${worker_contract}"
done
grep -Fq 'verify_untrusted_host_is_rejected' "${DRILL}" || \
  fail "生产演练没有从 TLS Edge 验证伪造 Host 拒绝"
grep -Fq 'verify_path_traversal_is_rejected' "${DRILL}" || \
  fail "生产演练没有保留原始 URI 验证路径穿越拒绝"
grep -Fq -- '--path-as-is' "${DRILL}" || \
  fail "路径穿越验收会被 HTTP 客户端预先规范化"
grep -Fq "COMMON_AGENT_E2E_FRONTEND_URL='https://common-agent.test:18443'" "${DRILL}" || \
  fail "生产浏览器没有使用正式域名入口"
grep -Fq "COMMON_AGENT_E2E_API_HOST_HEADER='common-agent.test'" "${DRILL}" || \
  fail "生产 API 验收没有通过 loopback 发送正式 Host"
grep -Fq '"--proxy-server=direct://"' "${REPOSITORY_ROOT}/frontend/playwright.config.ts" || \
  fail "生产浏览器本地域名映射没有显式绕过系统代理"
grep -Fq 'verify_forwarded_for_spoof_is_rate_limited' "${DRILL}" || \
  fail "生产演练没有从正式 TLS Edge 验证伪造来源头"
grep -Fq 'X-Forwarded-For: 203.0.113.${attempt}' "${DRILL}" || \
  fail "生产演练没有轮换伪造来源地址"
grep -Fq '[[ "${status}" == "429" ]]' "${DRILL}" || \
  fail "生产演练没有验证 Edge 后真实来源限流"

"${SCRIPT_DIR}/demo-single-node/test-demo-single-node.sh" >/dev/null || \
  fail "单机部署配置契约未通过"

echo "生产构建与回滚契约通过"
