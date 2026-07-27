#!/usr/bin/env bash
# 单机 demo 的证书管理：长效内部 CA（RAGFlow Edge）+ Let's Encrypt 公网证书（业务 Edge）。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PRODUCTION_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPOSITORY_ROOT="$(cd "${PRODUCTION_DIR}/../.." && pwd)"
STATE_ROOT="${COMMON_AGENT_PRODUCTION_STATE_ROOT:-${REPOSITORY_ROOT}/.local/production}"
TLS_ROOT="${STATE_ROOT}/tls"
ACME_ROOT="${STATE_ROOT}/acme"
SYSTEM_CA_BUNDLE="${COMMON_AGENT_SYSTEM_CA_BUNDLE:-/etc/ssl/certs/ca-certificates.crt}"
INTERNAL_CA_DAYS=3650
RAGFLOW_EDGE_HOST=common-agent-production-ragflow-edge

fail() {
  echo "$1" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "缺少工具：$1"
}

require_public_domain() {
  [[ -n "${COMMON_AGENT_PUBLIC_DOMAIN:-}" ]] || fail "缺少 COMMON_AGENT_PUBLIC_DOMAIN"
  PUBLIC_DOMAIN="${COMMON_AGENT_PUBLIC_DOMAIN}"
  LETSENCRYPT_LIVE="/etc/letsencrypt/live/${PUBLIC_DOMAIN}"
}

# ca.crt 供 manage.sh preflight 校验 edge.crt 与 ragflow.crt。业务 Edge 用的是
# Let's Encrypt 证书，其签发链根不在内部 CA 中，因此 ca.crt 必须同时包含两者；
# openssl verify -CAfile 支持多证书文件。
# ca-bundle.crt 挂进 api/worker，用于验证 RAGFlow（内部 CA）与百炼（公网 CA）。
build_ca_files() {
  [[ -f "${SYSTEM_CA_BUNDLE}" ]] || fail "系统信任根不存在：${SYSTEM_CA_BUNDLE}"
  cat "${TLS_ROOT}/internal-ca.crt" "${SYSTEM_CA_BUNDLE}" >"${TLS_ROOT}/ca.crt"
  cat "${SYSTEM_CA_BUNDLE}" "${TLS_ROOT}/internal-ca.crt" >"${TLS_ROOT}/ca-bundle.crt"
  # Edge 容器以非 root(101) 运行, 0600 的私钥会让 nginx 因 Permission denied 无法启动。
  # 私钥放宽到 0644, 其保护由 0700 的父目录承担: 宿主机上其他用户无法进入该目录,
  # 实际暴露面与 0600 相同（已实测验证）。目录权限因此是本方案的前提, 不可放宽。
  chmod 700 "${TLS_ROOT}"
  chmod 644 "${TLS_ROOT}"/*.key "${TLS_ROOT}"/*.crt
}

internal_ca() {
  require_command openssl
  mkdir -p "${TLS_ROOT}"
  chmod 700 "${TLS_ROOT}"
  [[ ! -f "${TLS_ROOT}/internal-ca.key" ]] || \
    fail "内部 CA 已存在，重建会使既有 RAGFlow 证书失效：${TLS_ROOT}/internal-ca.key"

  openssl req -x509 -newkey rsa:3072 -sha256 -nodes -days "${INTERNAL_CA_DAYS}" \
    -subj '/CN=common-agent-demo-internal-ca' \
    -keyout "${TLS_ROOT}/internal-ca.key" -out "${TLS_ROOT}/internal-ca.crt"
  openssl req -new -newkey rsa:3072 -sha256 -nodes \
    -subj "/CN=${RAGFLOW_EDGE_HOST}" \
    -addext "subjectAltName=DNS:${RAGFLOW_EDGE_HOST}" \
    -keyout "${TLS_ROOT}/ragflow.key" -out "${TLS_ROOT}/ragflow.csr"
  openssl x509 -req -sha256 -days "${INTERNAL_CA_DAYS}" -copy_extensions copyall \
    -CA "${TLS_ROOT}/internal-ca.crt" -CAkey "${TLS_ROOT}/internal-ca.key" -CAcreateserial \
    -in "${TLS_ROOT}/ragflow.csr" -out "${TLS_ROOT}/ragflow.crt"
  rm -f "${TLS_ROOT}/ragflow.csr"

  build_ca_files
  echo "内部 CA 与 RAGFlow 证书已生成，有效期 ${INTERNAL_CA_DAYS} 天"
}

# 把 certbot 产物复制成 compose secret 期望的固定路径。
install_public_cert() {
  [[ -f "${LETSENCRYPT_LIVE}/fullchain.pem" ]] || fail "未找到签发结果：${LETSENCRYPT_LIVE}"
  [[ -f "${TLS_ROOT}/internal-ca.crt" ]] || fail "内部 CA 尚未生成，请先执行 internal-ca"
  cp "${LETSENCRYPT_LIVE}/fullchain.pem" "${TLS_ROOT}/edge.crt"
  cp "${LETSENCRYPT_LIVE}/privkey.pem" "${TLS_ROOT}/edge.key"
  # 与 build_ca_files 保持一致: Edge 容器以非 root 运行需要能读私钥, 保护由 0700 目录承担。
  chmod 644 "${TLS_ROOT}/edge.key" "${TLS_ROOT}/edge.crt"
  build_ca_files
}

# docker secret 在容器启动时拷贝，续期后必须重建 edge 才会加载新证书。
recreate_edge() {
  COMMON_AGENT_PRODUCTION_STATE_ROOT="${STATE_ROOT}" \
    "${PRODUCTION_DIR}/manage.sh" edge-recreate
}

issue() {
  require_command certbot
  require_public_domain
  [[ -d "${ACME_ROOT}/.well-known/acme-challenge" ]] || \
    fail "ACME webroot 不存在，请先执行一次 manage.sh preflight"
  [[ -n "${COMMON_AGENT_CERTBOT_EMAIL:-}" ]] || fail "缺少 COMMON_AGENT_CERTBOT_EMAIL"
  certbot certonly --webroot -w "${ACME_ROOT}" \
    -d "${PUBLIC_DOMAIN}" \
    --email "${COMMON_AGENT_CERTBOT_EMAIL}" \
    --agree-tos --no-eff-email --non-interactive
  install_public_cert
  echo "公网证书已签发：${PUBLIC_DOMAIN}"
}

certificate_fingerprint() {
  [[ -f "${LETSENCRYPT_LIVE}/fullchain.pem" ]] || return 0
  openssl x509 -noout -fingerprint -sha256 -in "${LETSENCRYPT_LIVE}/fullchain.pem"
}

renew() {
  require_command certbot
  require_command openssl
  require_public_domain
  local before after
  before="$(certificate_fingerprint)"
  certbot renew --webroot -w "${ACME_ROOT}" --non-interactive
  after="$(certificate_fingerprint)"
  if [[ "${before}" == "${after}" ]]; then
    echo "证书未到续期窗口，Edge 无需重建"
    return
  fi
  install_public_cert
  recreate_edge
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
