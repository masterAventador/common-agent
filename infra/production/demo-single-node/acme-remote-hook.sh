#!/usr/bin/env bash
# certbot 的 manual hook: 把 HTTP-01 挑战文件投放到远端服务器的 ACME webroot。
#
# 用途: 部署机所在网络无法访问 Let's Encrypt 的 ACME API（国内云常见), 因此在能访问
# LE 的机器上运行 certbot, 由本脚本经 SSH 把挑战文件放到服务器。Let's Encrypt 仍从
# 公网回连服务器的 80 端口完成验证, 验证主体和结果与在服务器本地签发完全一致。
#
# 用法:
#   COMMON_AGENT_ACME_SSH_TARGET=ubuntu@<服务器地址> \
#   COMMON_AGENT_ACME_REMOTE_ROOT=/var/lib/common-agent/production/acme \
#     certbot certonly --manual --preferred-challenges http \
#       --manual-auth-hook "<本脚本> deploy" \
#       --manual-cleanup-hook "<本脚本> clean" \
#       -d <域名> --email <邮箱> --agree-tos --no-eff-email --non-interactive \
#       --config-dir ... --work-dir ... --logs-dir ...
set -euo pipefail

# 提示语里不能出现 }, 否则会提前结束参数展开, 使 ACTION 多带一个右花括号。
ACTION="${1:?用法: 需要 deploy 或 clean 作为第一个参数}"
SSH_TARGET="${COMMON_AGENT_ACME_SSH_TARGET:?缺少 COMMON_AGENT_ACME_SSH_TARGET}"
REMOTE_ROOT="${COMMON_AGENT_ACME_REMOTE_ROOT:?缺少 COMMON_AGENT_ACME_REMOTE_ROOT}"
CHALLENGE_DIR="${REMOTE_ROOT}/.well-known/acme-challenge"

# 令牌来自 certbot, 只含 base64url 字符; 仍显式校验以免拼接出意外路径。
[[ "${CERTBOT_TOKEN:?缺少 CERTBOT_TOKEN}" =~ ^[A-Za-z0-9_-]+$ ]] || {
  echo "非法的 ACME 令牌: ${CERTBOT_TOKEN}" >&2
  exit 1
}

case "${ACTION}" in
  deploy)
    printf '%s' "${CERTBOT_VALIDATION:?缺少 CERTBOT_VALIDATION}" \
      | ssh -o BatchMode=yes "${SSH_TARGET}" \
          "install -m 644 /dev/stdin '${CHALLENGE_DIR}/${CERTBOT_TOKEN}'"
    ;;
  clean)
    ssh -o BatchMode=yes "${SSH_TARGET}" \
      "rm -f '${CHALLENGE_DIR}/${CERTBOT_TOKEN}'" || true
    ;;
  *)
    echo "未知动作: ${ACTION}（应为 deploy 或 clean）" >&2
    exit 1
    ;;
esac
