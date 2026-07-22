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

fail() {
  echo "$1" >&2
  exit 1
}

[[ -x "${MANAGER}" ]] || fail "缺少可执行的生产发布管理入口"
[[ -x "${DRILL}" ]] || fail "缺少可执行的隔离生产发布演练"
[[ -f "${COMPOSE_FILE}" ]] || fail "缺少双槽生产 Compose"
[[ -f "${LOAD_TEST}" ]] || fail "缺少生产 TLS Edge 容量压测入口"
[[ -f "${SSE_LOAD_TEST}" ]] || fail "缺少生产 SSE 长连接压测入口"
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
grep -Fq 'k6 run' "${DRILL}" || fail "生产演练没有执行正式容量压测"
grep -Fq 'sse_load_test.py' "${DRILL}" || fail "生产演练没有执行 SSE 长连接压测"
for drill_sse_contract in \
  'COMMON_AGENT_SSE_CONNECTIONS=128' \
  'COMMON_AGENT_SSE_DURATION_SECONDS=360' \
  'COMMON_AGENT_SSE_RAMP_CONNECTIONS_PER_SECOND=16' \
  'COMMON_AGENT_SSE_HANDSHAKE_P95_MS=500'; do
  grep -Fq "${drill_sse_contract}" "${DRILL}" || \
    fail "生产演练缺少 SSE 长连接目标：${drill_sse_contract}"
done
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

echo "生产构建与回滚契约通过"
