#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
COMPOSE_FILE="${SCRIPT_DIR}/compose.yaml"
# 可选的资源覆盖片段，供单机 demo 等部署形态叠加；不改变任何依赖解析路径。
COMPOSE_OVERRIDE_FILE="${COMMON_AGENT_COMPOSE_OVERRIDE:-}"
RAGFLOW_COMPOSE_FILE="${SCRIPT_DIR}/ragflow-node.compose.yaml"
STATE_ROOT="${COMMON_AGENT_PRODUCTION_STATE_ROOT:-${REPOSITORY_ROOT}/.local/production}"
RELEASE_ROOT="${STATE_ROOT}/releases"
TLS_ROOT="${STATE_ROOT}/tls"
CONFIG_FILE="${COMMON_AGENT_PRODUCTION_CONFIG_FILE:-${STATE_ROOT}/config.env}"
SECRETS_FILE="${COMMON_AGENT_PRODUCTION_SECRETS_FILE:-${STATE_ROOT}/secrets.env}"
STATE_FILE="${STATE_ROOT}/deployment.env"
CANDIDATE_FILE="${STATE_ROOT}/candidate-release.env"
EDGE_CONFIG="${STATE_ROOT}/edge.conf"
WEB_CONFIG="${STATE_ROOT}/common-agent-web.conf"
DOCKER_CONTEXT_NAME="${COMMON_AGENT_PRODUCTION_DOCKER_CONTEXT:-colima-common-agent-dev}"
HTTPS_BIND="${COMMON_AGENT_HTTPS_BIND:-127.0.0.1}"
HTTPS_PORT="${COMMON_AGENT_HTTPS_PORT:-18443}"
HTTP_BIND="${COMMON_AGENT_HTTP_BIND:-127.0.0.1}"
HTTP_PORT="${COMMON_AGENT_HTTP_PORT:-18080}"
ACME_ROOT="${STATE_ROOT}/acme"
PUBLIC_DOMAIN="${COMMON_AGENT_PUBLIC_DOMAIN:-common-agent.test}"
PUBLIC_BASE_URL="${COMMON_AGENT_PUBLIC_BASE_URL:-https://${PUBLIC_DOMAIN}:${HTTPS_PORT}}"
RAGFLOW_NETWORK="${COMMON_AGENT_RAGFLOW_NETWORK:-common-agent-dev_ragflow}"
RAGFLOW_EDGE_MODE="${COMMON_AGENT_RAGFLOW_EDGE_MODE:-external}"
LOCAL_CONTEXT_CONFIRMATION="deploy-common-agent-to-approved-remote"
# 单机 demo 固定使用 blue 槽停机发布；green 的 compose 定义保留但不再启动。
DEPLOY_SLOT="blue"

usage() {
  echo "用法: $0 {build|init-tls|edge-recreate|preflight|migrate|rollout|verify|rollback|status|down|drill}" >&2
}

fail() {
  echo "$1" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "缺少生产发布工具：$1"
}

validate_public_domain() {
  [[ "${PUBLIC_DOMAIN}" =~ ^[a-z0-9]([a-z0-9.-]{0,251}[a-z0-9])?$ ]] || \
    fail "生产域名格式无效：${PUBLIC_DOMAIN}"
  [[ "${PUBLIC_DOMAIN}" != *..* ]] || fail "生产域名不能包含空标签：${PUBLIC_DOMAIN}"
  local label
  local -a labels=()
  IFS='.' read -r -a labels <<<"${PUBLIC_DOMAIN}"
  for label in "${labels[@]}"; do
    [[ "${#label}" -le 63 && "${label}" != -* && "${label}" != *- ]] || \
      fail "生产域名标签无效：${PUBLIC_DOMAIN}"
  done
}

docker_cli() {
  docker --context "${DOCKER_CONTEXT_NAME}" "$@"
}

guard_docker_context() {
  local endpoint
  endpoint="$(docker context inspect "${DOCKER_CONTEXT_NAME}" --format '{{.Endpoints.docker.Host}}' 2>/dev/null)" || \
    fail "Docker context 不存在：${DOCKER_CONTEXT_NAME}"
  if [[ "${DOCKER_CONTEXT_NAME}" == "colima-common-agent-dev" ]]; then
    [[ "${endpoint}" == unix://* ]] || fail "项目本地 context 不是 Unix socket：${endpoint}"
    return
  fi
  if [[ "${DOCKER_CONTEXT_NAME}" == "default" && "${endpoint}" == unix://* ]]; then
    return
  fi
  if [[ "${COMMON_AGENT_REMOTE_DEPLOY_CONFIRMATION:-}" != "${LOCAL_CONTEXT_CONFIRMATION}" ]]; then
    fail "远程 context 需要 COMMON_AGENT_REMOTE_DEPLOY_CONFIRMATION=deploy-common-agent-to-approved-remote"
  fi
}

prepare_state_root() {
  mkdir -p "${RELEASE_ROOT}" "${TLS_ROOT}" "${ACME_ROOT}/.well-known/acme-challenge"
  chmod 700 "${STATE_ROOT}" "${RELEASE_ROOT}" "${TLS_ROOT}"
  # webroot 需要被容器内 nginx（uid 101）读取，因此不能沿用 0700。
  chmod 755 "${ACME_ROOT}" "${ACME_ROOT}/.well-known" "${ACME_ROOT}/.well-known/acme-challenge"
}

file_mode() {
  stat -f '%Lp' "$1" 2>/dev/null || stat -c '%a' "$1"
}

require_secret_file() {
  [[ -f "${SECRETS_FILE}" && ! -L "${SECRETS_FILE}" ]] || \
    fail "生产凭据文件不存在或是符号链接：${SECRETS_FILE}"
  [[ "$(file_mode "${SECRETS_FILE}")" == "600" ]] || \
    fail "生产凭据文件权限必须为 0600：${SECRETS_FILE}"
  local key
  # 后四项是应用在 production 下强制要求的加密主密钥；缺任一项容器会在启动时崩溃，
  # 必须在 preflight 拦截，不能等到 rollout 停机后才发现。
  for key in MYSQL_ROOT_PASSWORD MYSQL_DATABASE MYSQL_USER MYSQL_PASSWORD \
    COMMON_AGENT_DATABASE_URL COMMON_AGENT_AUTH_BOOTSTRAP_TOKEN BAILIAN_API_KEY \
    COMMON_AGENT_TOOL_CREDENTIAL_KEYS COMMON_AGENT_TOOL_CREDENTIAL_ACTIVE_KEY_ID \
    COMMON_AGENT_RAGFLOW_IDENTITY_KEYS COMMON_AGENT_RAGFLOW_IDENTITY_ACTIVE_KEY_ID; do
    grep -Eq "^${key}=.+" "${SECRETS_FILE}" || fail "生产凭据缺少：${key}"
  done
  # RAGFlow 全新安装后没有可继承的 legacy token，平台会自行创建租户账号并签发凭据。
  # 该键必须显式声明以免配置遗漏，但允许留空，否则全新服务器的首次部署会被挡在这里。
  grep -Eq "^RAGFLOW_API_KEY=" "${SECRETS_FILE}" || fail "生产凭据缺少：RAGFLOW_API_KEY"
}

require_config_file() {
  [[ -f "${CONFIG_FILE}" && ! -L "${CONFIG_FILE}" ]] || \
    fail "生产配置文件不存在或是符号链接：${CONFIG_FILE}"
  grep -Fxq 'COMMON_AGENT_INTEGRATION_MODE=real' "${CONFIG_FILE}" || \
    fail "生产配置必须使用 real 集成模式"
  grep -Fxq 'COMMON_AGENT_AUTH_COOKIE_SECURE=true' "${CONFIG_FILE}" || \
    fail "生产配置必须启用 Secure Cookie"
  grep -Eq '^COMMON_AGENT_CORS_ORIGINS=https://' "${CONFIG_FILE}" || \
    fail "生产 CORS 必须使用 HTTPS 来源"
  grep -Eq '^RAGFLOW_BASE_URL=https://' "${CONFIG_FILE}" || \
    fail "生产 RAGFlow 必须使用 HTTPS"
}

write_release_file() {
  local path="$1" release_id="$2" revision="$3" api_image="$4" web_image="$5"
  local temporary
  temporary="$(mktemp "${STATE_ROOT}/release.XXXXXX")"
  chmod 600 "${temporary}"
  {
    printf 'RELEASE_ID=%s\n' "${release_id}"
    printf 'SOURCE_REVISION=%s\n' "${revision}"
    printf 'COMMON_AGENT_API_IMAGE=%s\n' "${api_image}"
    printf 'COMMON_AGENT_WEB_IMAGE=%s\n' "${web_image}"
  } >"${temporary}"
  mv "${temporary}" "${path}"
}

load_release() {
  local release_id="$1"
  local release_file="${RELEASE_ROOT}/${release_id}.env"
  # 所有镜像都必须通过 docker image inspect 解析为本地不可变 sha256 ID。
  [[ "${release_id}" =~ ^[0-9a-f]{12,40}-[0-9]{8}T[0-9]{6}Z$ ]] || \
    fail "非法 release id：${release_id}"
  [[ -f "${release_file}" && ! -L "${release_file}" ]] || fail "release 不存在：${release_id}"
  RELEASE_ID=""
  SOURCE_REVISION=""
  COMMON_AGENT_API_IMAGE=""
  COMMON_AGENT_WEB_IMAGE=""
  # 该文件只由 write_release_file 生成，且值由 Git SHA、时间戳、镜像 ID 构成。
  # shellcheck disable=SC1090
  source "${release_file}"
  [[ "${RELEASE_ID}" == "${release_id}" ]] || fail "release 清单标识不一致"
  [[ "${SOURCE_REVISION}" =~ ^[0-9a-f]{40}$ ]] || fail "release 源码 revision 非法"
  [[ "${COMMON_AGENT_API_IMAGE}" == sha256:* ]] || fail "API 镜像不是不可变 sha256 ID"
  [[ "${COMMON_AGENT_WEB_IMAGE}" == sha256:* ]] || fail "Web 镜像不是不可变 sha256 ID"
  docker_cli image inspect "${COMMON_AGENT_API_IMAGE}" >/dev/null
  docker_cli image inspect "${COMMON_AGENT_WEB_IMAGE}" >/dev/null
}

candidate_release_id() {
  [[ -f "${CANDIDATE_FILE}" && ! -L "${CANDIDATE_FILE}" ]] || fail "尚未执行 build"
  sed -n 's/^RELEASE_ID=//p' "${CANDIDATE_FILE}"
}

load_state() {
  active_slot=""
  active_release=""
  previous_slot=""
  previous_release=""
  if [[ -f "${STATE_FILE}" ]]; then
    [[ ! -L "${STATE_FILE}" ]] || fail "部署状态文件不能是符号链接"
    # 该文件只由 write_state 生成，值均经过白名单校验。
    # shellcheck disable=SC1090
    source "${STATE_FILE}"
  fi
  [[ -z "${active_slot}" || "${active_slot}" == "blue" || "${active_slot}" == "green" ]] || \
    fail "部署状态中的 active_slot 非法"
  [[ -z "${previous_slot}" || "${previous_slot}" == "blue" || "${previous_slot}" == "green" ]] || \
    fail "部署状态中的 previous_slot 非法"
}

write_state() {
  local next_active_slot="$1" next_active_release="$2" next_previous_slot="$3" next_previous_release="$4"
  local temporary
  [[ "${next_active_slot}" == "blue" || "${next_active_slot}" == "green" ]] || fail "非法 active slot"
  [[ -z "${next_previous_slot}" || "${next_previous_slot}" == "blue" || "${next_previous_slot}" == "green" ]] || \
    fail "非法 previous slot"
  temporary="$(mktemp "${STATE_ROOT}/deployment.XXXXXX")"
  chmod 600 "${temporary}"
  {
    printf 'active_slot=%s\n' "${next_active_slot}"
    printf 'active_release=%s\n' "${next_active_release}"
    printf 'previous_slot=%s\n' "${next_previous_slot}"
    printf 'previous_release=%s\n' "${next_previous_release}"
  } >"${temporary}"
  mv "${temporary}" "${STATE_FILE}"
}

compose_loaded_release() {
  local -a compose_files=(-f "${COMPOSE_FILE}")
  if [[ -n "${COMPOSE_OVERRIDE_FILE}" ]]; then
    [[ -f "${COMPOSE_OVERRIDE_FILE}" && ! -L "${COMPOSE_OVERRIDE_FILE}" ]] || \
      fail "compose 覆盖文件不存在或是符号链接：${COMPOSE_OVERRIDE_FILE}"
    compose_files+=(-f "${COMPOSE_OVERRIDE_FILE}")
  fi
  COMMON_AGENT_RUNTIME_ENV=production \
  COMMON_AGENT_API_IMAGE="${COMMON_AGENT_API_IMAGE}" \
  COMMON_AGENT_WEB_IMAGE="${COMMON_AGENT_WEB_IMAGE}" \
  COMMON_AGENT_CONFIG_FILE="${CONFIG_FILE}" \
  COMMON_AGENT_SECRETS_FILE="${SECRETS_FILE}" \
  COMMON_AGENT_CA_BUNDLE="${TLS_ROOT}/ca-bundle.crt" \
  COMMON_AGENT_EDGE_CONFIG="${EDGE_CONFIG}" \
  COMMON_AGENT_WEB_CONFIG="${WEB_CONFIG}" \
  COMMON_AGENT_EDGE_CERT="${TLS_ROOT}/edge.crt" \
  COMMON_AGENT_EDGE_KEY="${TLS_ROOT}/edge.key" \
  COMMON_AGENT_HTTPS_BIND="${HTTPS_BIND}" \
  COMMON_AGENT_HTTPS_PORT="${HTTPS_PORT}" \
  COMMON_AGENT_HTTP_BIND="${HTTP_BIND}" \
  COMMON_AGENT_HTTP_PORT="${HTTP_PORT}" \
  COMMON_AGENT_ACME_ROOT="${ACME_ROOT}" \
  COMMON_AGENT_PUBLIC_DOMAIN="${PUBLIC_DOMAIN}" \
    docker_cli compose --project-name common-agent-production "${compose_files[@]}" "$@"
}

ragflow_compose() {
  COMMON_AGENT_RAGFLOW_EDGE_CONFIG="${SCRIPT_DIR}/ragflow-edge.conf" \
  COMMON_AGENT_RAGFLOW_CERT="${TLS_ROOT}/ragflow.crt" \
  COMMON_AGENT_RAGFLOW_KEY="${TLS_ROOT}/ragflow.key" \
  COMMON_AGENT_RAGFLOW_NETWORK="${RAGFLOW_NETWORK}" \
    docker_cli compose --project-name common-agent-production-ragflow-edge \
      -f "${RAGFLOW_COMPOSE_FILE}" -f "${SCRIPT_DIR}/ragflow-node.local.compose.yaml" "$@"
}

render_edge_config() {
  local slot="$1"
  [[ "${slot}" == "blue" || "${slot}" == "green" ]] || fail "非法 edge slot"
  validate_public_domain
  sed \
    -e "s/{{ACTIVE_SLOT}}/${slot}/g" \
    -e "s/{{PUBLIC_DOMAIN}}/${PUBLIC_DOMAIN}/g" \
    "${SCRIPT_DIR}/edge.conf.template" >"${EDGE_CONFIG}"
  cp "${SCRIPT_DIR}/web.conf.template" "${WEB_CONFIG}"
  chmod 644 "${EDGE_CONFIG}" "${WEB_CONFIG}"
}

wait_for_service() {
  local service="$1" timeout_seconds="${2:-180}" container_id state deadline
  container_id="$(compose_loaded_release ps -q "${service}")"
  [[ -n "${container_id}" ]] || fail "服务容器不存在：${service}"
  deadline=$((SECONDS + timeout_seconds))
  while ((SECONDS < deadline)); do
    state="$(docker_cli inspect --format '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "${container_id}")"
    if [[ "${state}" == "running healthy" ]]; then
      return
    fi
    if [[ "${state}" == exited* || "${state}" == dead* ]]; then
      compose_loaded_release logs --no-color "${service}" >&2 || true
      fail "服务提前退出：${service} (${state})"
    fi
    sleep 2
  done
  compose_loaded_release logs --no-color "${service}" >&2 || true
  fail "服务未在 ${timeout_seconds} 秒内就绪：${service}"
}

wait_for_ragflow_edge() {
  local container_id state deadline
  container_id="$(ragflow_compose ps -q ragflow-edge)"
  [[ -n "${container_id}" ]] || fail "RAGFlow TLS edge 容器不存在"
  deadline=$((SECONDS + 180))
  while ((SECONDS < deadline)); do
    state="$(docker_cli inspect --format '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "${container_id}")"
    if [[ "${state}" == "running healthy" ]]; then
      return
    fi
    if [[ "${state}" == exited* || "${state}" == dead* ]]; then
      ragflow_compose logs --no-color ragflow-edge >&2 || true
      fail "RAGFlow TLS edge 提前退出：${state}"
    fi
    sleep 2
  done
  ragflow_compose logs --no-color ragflow-edge >&2 || true
  fail "RAGFlow TLS edge 未在 180 秒内稳定就绪"
}

verify_local_ragflow_tls_material() {
  [[ -f "${TLS_ROOT}/ragflow.crt" && -f "${TLS_ROOT}/ragflow.key" ]] || \
    fail "本地联合演练缺少 RAGFlow TLS 材料"
  openssl verify -CAfile "${TLS_ROOT}/ca.crt" "${TLS_ROOT}/ragflow.crt" >/dev/null
  openssl pkey -in "${TLS_ROOT}/ragflow.key" -check -noout >/dev/null
}

verify_edge() {
  local health="" status page attempt
  local -a connection_args=()
  if [[ -z "${COMMON_AGENT_PUBLIC_BASE_URL:-}" ]]; then
    connection_args=(--resolve "${PUBLIC_DOMAIN}:${HTTPS_PORT}:127.0.0.1")
  fi
  for ((attempt = 1; attempt <= 30; attempt++)); do
    if health="$(curl --fail --silent --show-error --noproxy '*' \
      --cacert "${TLS_ROOT}/ca.crt" "${connection_args[@]}" \
      "${PUBLIC_BASE_URL%/}/api/v1/system/health" 2>/dev/null)"; then
      break
    fi
    sleep 1
  done
  if [[ "${health}" != *'"status":"ok"'* || "${health}" != *'"integration_mode":"real"'* ]]; then
    echo "生产健康响应不符合 real 契约" >&2
    return 1
  fi
  status="$(curl --fail --silent --show-error --noproxy '*' \
    --cacert "${TLS_ROOT}/ca.crt" "${connection_args[@]}" \
    "${PUBLIC_BASE_URL%/}/api/v1/system/status")" || return 1
  if [[ "${status}" != *'"integration_mode":"real"'* || "${status}" != *'"availability":"available"'* ]]; then
    echo "RAGFlow 生产 TLS 路径不可用" >&2
    return 1
  fi
  page="$(curl --fail --silent --show-error --noproxy '*' \
    --cacert "${TLS_ROOT}/ca.crt" "${connection_args[@]}" \
    "${PUBLIC_BASE_URL%/}/")" || return 1
  if [[ "${page}" != *'<div id="root">'* ]]; then
    echo "生产 Web 页面不可用" >&2
    return 1
  fi
}

build_release() {
  local revision timestamp release_id api_tag web_tag api_image web_image
  guard_docker_context
  prepare_state_root
  revision="$(git -C "${REPOSITORY_ROOT}" rev-parse HEAD)"
  timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
  release_id="${revision}-${timestamp}"
  api_tag="common-agent-api:${release_id}"
  web_tag="common-agent-web:${release_id}"
  # ghcr.io 不可达的网络需要改用预先载入本地的同一 uv 镜像; 默认仍走 Dockerfile 锁定的 digest。
  local -a api_build_args=()
  [[ -z "${COMMON_AGENT_UV_IMAGE:-}" ]] || \
    api_build_args+=(--build-arg "UV_IMAGE=${COMMON_AGENT_UV_IMAGE}")
  docker_cli build --pull=false --build-arg "SOURCE_REVISION=${revision}" \
    "${api_build_args[@]}" --tag "${api_tag}" "${REPOSITORY_ROOT}/backend"
  docker_cli build --pull=false --build-arg "SOURCE_REVISION=${revision}" \
    --build-arg VITE_API_BASE_URL=/api/v1 --tag "${web_tag}" "${REPOSITORY_ROOT}/frontend"
  api_image="$(docker_cli image inspect "${api_tag}" --format '{{.Id}}')"
  web_image="$(docker_cli image inspect "${web_tag}" --format '{{.Id}}')"
  [[ "${api_image}" == sha256:* && "${web_image}" == sha256:* ]] || fail "镜像 ID 不是 sha256:"
  write_release_file "${RELEASE_ROOT}/${release_id}.env" "${release_id}" "${revision}" \
    "${api_image}" "${web_image}"
  cp "${RELEASE_ROOT}/${release_id}.env" "${CANDIDATE_FILE}"
  chmod 600 "${CANDIDATE_FILE}"
  echo "已构建不可变候选 release：${release_id}"
}

init_tls() {
  local release_id
  guard_docker_context
  validate_public_domain
  prepare_state_root
  release_id="$(candidate_release_id)"
  load_release "${release_id}"
  if [[ -f "${TLS_ROOT}/ca.crt" && -f "${TLS_ROOT}/edge.crt" && \
    -f "${TLS_ROOT}/edge.key" && -f "${TLS_ROOT}/ragflow.crt" && \
    -f "${TLS_ROOT}/ragflow.key" && -f "${TLS_ROOT}/ca-bundle.crt" ]]; then
    echo "复用现有本地生产 TLS 材料"
    return
  fi
  if find "${TLS_ROOT}" -mindepth 1 -maxdepth 1 -print -quit | grep -q .; then
    fail "TLS 目录存在不完整材料，拒绝自动覆盖：${TLS_ROOT}"
  fi
  umask 077
  openssl req -x509 -newkey rsa:3072 -sha256 -nodes -days 30 \
    -subj '/CN=common-agent-local-ca' \
    -keyout "${TLS_ROOT}/ca.key" -out "${TLS_ROOT}/ca.crt" >/dev/null 2>&1
  openssl req -new -newkey rsa:3072 -sha256 -nodes \
    -subj "/CN=${PUBLIC_DOMAIN}" -addext "subjectAltName=DNS:${PUBLIC_DOMAIN}" \
    -keyout "${TLS_ROOT}/edge.key" -out "${TLS_ROOT}/edge.csr" >/dev/null 2>&1
  openssl x509 -req -sha256 -days 30 -copy_extensions copyall \
    -in "${TLS_ROOT}/edge.csr" -CA "${TLS_ROOT}/ca.crt" -CAkey "${TLS_ROOT}/ca.key" \
    -CAcreateserial -out "${TLS_ROOT}/edge.crt" >/dev/null 2>&1
  openssl req -new -newkey rsa:3072 -sha256 -nodes \
    -subj '/CN=common-agent-production-ragflow-edge' \
    -addext 'subjectAltName=DNS:common-agent-production-ragflow-edge' \
    -keyout "${TLS_ROOT}/ragflow.key" -out "${TLS_ROOT}/ragflow.csr" >/dev/null 2>&1
  openssl x509 -req -sha256 -days 30 -copy_extensions copyall \
    -in "${TLS_ROOT}/ragflow.csr" -CA "${TLS_ROOT}/ca.crt" -CAkey "${TLS_ROOT}/ca.key" \
    -CAcreateserial -out "${TLS_ROOT}/ragflow.crt" >/dev/null 2>&1
  docker_cli run --rm --entrypoint cat "${COMMON_AGENT_API_IMAGE}" \
    /etc/ssl/certs/ca-certificates.crt >"${TLS_ROOT}/ca-bundle.crt"
  cat "${TLS_ROOT}/ca.crt" >>"${TLS_ROOT}/ca-bundle.crt"
  rm -f "${TLS_ROOT}/edge.csr" "${TLS_ROOT}/ragflow.csr" "${TLS_ROOT}/ca.srl"
  chmod 600 "${TLS_ROOT}"/*.key
  chmod 644 "${TLS_ROOT}"/*.crt
  echo "已生成 30 天本地演练证书；远程发布必须改用正式 CA 证书"
}

preflight() {
  local release_id
  require_command docker
  require_command curl
  require_command openssl
  require_command git
  guard_docker_context
  validate_public_domain
  prepare_state_root
  require_config_file
  require_secret_file
  [[ "${PUBLIC_BASE_URL}" == https://* ]] || fail "生产验收入口必须使用 HTTPS：${PUBLIC_BASE_URL}"
  release_id="$(candidate_release_id)"
  load_release "${release_id}"
  [[ -f "${TLS_ROOT}/ca.crt" && -f "${TLS_ROOT}/ca-bundle.crt" && \
    -f "${TLS_ROOT}/edge.crt" && -f "${TLS_ROOT}/edge.key" ]] || fail "生产 TLS 材料不完整"
  openssl verify -CAfile "${TLS_ROOT}/ca.crt" "${TLS_ROOT}/edge.crt" >/dev/null
  openssl pkey -in "${TLS_ROOT}/edge.key" -check -noout >/dev/null
  case "${RAGFLOW_EDGE_MODE}" in
    external) ;;
    local-shared-network)
      verify_local_ragflow_tls_material
      docker_cli network inspect "${RAGFLOW_NETWORK}" >/dev/null || \
        fail "RAGFlow 私网不存在：${RAGFLOW_NETWORK}"
      ragflow_compose config --quiet
      ;;
    *) fail "COMMON_AGENT_RAGFLOW_EDGE_MODE 必须是 external 或 local-shared-network" ;;
  esac
  docker_cli image inspect "${COMMON_AGENT_API_IMAGE}" "${COMMON_AGENT_WEB_IMAGE}" >/dev/null
  compose_loaded_release --profile blue --profile green --profile operations config --quiet
  echo "生产发布前置检查通过：${release_id}"
}

migrate() {
  local release_id
  preflight
  release_id="$(candidate_release_id)"
  load_release "${release_id}"
  render_edge_config blue
  compose_loaded_release up -d platform-mysql
  wait_for_service platform-mysql 180
  # 数据库迁移只允许显式向前；自动回滚绝不执行 alembic downgrade。
  compose_loaded_release --profile operations run --rm migration alembic upgrade head
  : >"${STATE_ROOT}/migrated-${release_id}"
  chmod 600 "${STATE_ROOT}/migrated-${release_id}"
  echo "数据库已迁移到候选 release：${release_id}"
}

switch_edge() {
  local slot="$1"
  render_edge_config "${slot}"
  if [[ -n "$(compose_loaded_release ps -q edge)" ]]; then
    compose_loaded_release exec -T edge nginx -s reload
  else
    compose_loaded_release up -d --no-deps edge
    wait_for_service edge 60
  fi
}

# 证书续期后重建 Edge：docker secret 只在容器启动时拷贝，nginx reload 不会加载新证书。
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

verify() {
  guard_docker_context
  load_state
  [[ -n "${active_release}" ]] || fail "当前没有 active release"
  load_release "${active_release}"
  wait_for_service "api-${active_slot}" 30
  wait_for_service "worker-${active_slot}" 30
  wait_for_service "web-${active_slot}" 30
  wait_for_service edge 30
  verify_edge || fail "active release 的生产入口验证失败"
  echo "active release 验证通过：${active_release} (${active_slot})"
}

rollback() {
  local rollback_release current_release
  guard_docker_context
  load_state
  [[ -n "${previous_release}" ]] || fail "没有可回滚的 previous release"
  current_release="${active_release}"
  rollback_release="${previous_release}"
  load_release "${rollback_release}"

  # 单槽回滚：用上一 release 的镜像重建同一槽，与发布同样存在停机窗口。
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

status() {
  guard_docker_context
  load_state
  echo "active_release=${active_release:-none} active_slot=${active_slot:-none}"
  echo "previous_release=${previous_release:-none} previous_slot=${previous_slot:-none}"
  if [[ -n "${active_release}" ]]; then
    load_release "${active_release}"
  elif [[ -f "${CANDIDATE_FILE}" ]]; then
    load_release "$(candidate_release_id)"
  else
    return
  fi
  compose_loaded_release --profile blue --profile green ps
  if [[ "${RAGFLOW_EDGE_MODE}" == "local-shared-network" ]]; then
    ragflow_compose ps
  fi
}

down() {
  local release_id
  guard_docker_context
  if [[ -f "${CANDIDATE_FILE}" ]]; then
    release_id="$(candidate_release_id)"
  else
    load_state
    [[ -n "${active_release}" ]] || return
    release_id="${active_release}"
  fi
  load_release "${release_id}"
  if [[ "${RAGFLOW_EDGE_MODE}" == "local-shared-network" ]]; then
    ragflow_compose down --remove-orphans
  fi
  compose_loaded_release --profile blue --profile green --profile operations down --remove-orphans
  echo "生产演练容器已停止；平台 MySQL 数据卷未删除"
}

case "${1:-}" in
  build) build_release ;;
  init-tls) init_tls ;;
  edge-recreate) edge_recreate ;;
  preflight) preflight ;;
  migrate) migrate ;;
  rollout) rollout ;;
  verify) verify ;;
  rollback) rollback ;;
  status) status ;;
  down) down ;;
  drill) exec "${SCRIPT_DIR}/drill.sh" ;;
  *) usage; exit 2 ;;
esac
