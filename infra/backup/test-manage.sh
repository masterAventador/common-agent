#!/usr/bin/env bash
# shellcheck disable=SC2016 # Contract assertions intentionally match literal shell expressions.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANAGER="${SCRIPT_DIR}/manage.sh"
POLICY="${SCRIPT_DIR}/policy.env"

fail() {
  echo "$1" >&2
  exit 1
}

[[ -x "${MANAGER}" ]] || fail "缺少可执行的备份恢复管理入口"
[[ -f "${POLICY}" ]] || fail "缺少版本化的备份恢复策略"

for expected in \
  'BACKUP_RPO_HOURS=24' \
  'BACKUP_RTO_MINUTES=120' \
  'BACKUP_RETENTION_DAYS=30' \
  'BACKUP_MINIMUM_GENERATIONS=7' \
  'BACKUP_DRILL_INTERVAL_DAYS=90'; do
  grep -Fq "${expected}" "${POLICY}" || fail "备份策略缺少 ${expected}"
done

for action in init-key backup verify restore prune drill; do
  grep -Fq "${action})" "${MANAGER}" || fail "备份入口缺少 ${action} 动作"
done

for volume in esdata-v2 mysql-data-v3 minio-data-v2 valkey-data-v2; do
  grep -Fq "${volume}" "${MANAGER}" || fail "备份入口缺少 RAGFlow ${volume} 数据"
done

grep -Fq -- '--single-transaction' "${MANAGER}" || fail "平台 MySQL 没有一致性逻辑备份"
grep -Fq 'ragflow-external-references.json' "${MANAGER}" || \
  fail "备份没有显式登记 RAGFlow 外部引用"
grep -Fq 'BACKUP_ENCRYPTION_KEY_FILE' "${MANAGER}" || fail "备份没有使用独立加密密钥文件"
grep -Fq 'common_agent.adapters.backup.archive' "${MANAGER}" || \
  fail "备份没有使用认证加密归档"
grep -Fq 'BACKUP_RESTORE_CONFIRMATION=restore-to-empty-recovery-environment' "${MANAGER}" || \
  fail "恢复没有要求空 recovery 环境确认"
grep -Fq 'common-agent-recovery-' "${MANAGER}" || fail "恢复资源没有强制隔离命名空间"
grep -Fq 'RAGFlow 容器必须已停止' "${MANAGER}" || fail "RAGFlow 冷快照没有停写前置条件"
grep -Fq 'common-agent.real.worker' "${MANAGER}" || fail "备份没有检查独立 Worker 停写"
grep -Fq "stat -c '%Y'" "${MANAGER}" || fail "保留策略缺少 Linux 文件时间兼容路径"
grep -Fq 'backup-recovery-seed.spec.ts' "${SCRIPT_DIR}/drill.sh" || \
  fail "灾难演练没有通过正式页面建立源数据"
grep -Fq 'backup-recovery-verify.spec.ts' "${SCRIPT_DIR}/drill.sh" || \
  fail "灾难演练没有通过正式页面验证恢复数据"
grep -Fq 'remove_ragflow_environment "${SOURCE_ID}"' "${SCRIPT_DIR}/drill.sh" || \
  fail "灾难演练没有在恢复前销毁隔离源 RAGFlow"
grep -Fq 'remove_mysql_environment "${SOURCE_MYSQL_CONTAINER}"' "${SCRIPT_DIR}/drill.sh" || \
  fail "灾难演练没有在恢复前销毁隔离源 MySQL"

if grep -Eq 'BAILIAN_API_KEY|RAGFLOW_API_KEY|AUTH_BOOTSTRAP_TOKEN|PASSWORD=' \
  "${SCRIPT_DIR}/deployment-config.allowlist"; then
  fail "部署配置白名单包含凭据"
fi

KEY_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/common-agent-backup-contract.XXXXXX")"
trap 'find "${KEY_ROOT}" -depth -delete' EXIT
BACKUP_ENCRYPTION_KEY_FILE="${KEY_ROOT}/backup.key" "${MANAGER}" init-key
[[ "$(wc -c < "${KEY_ROOT}/backup.key" | tr -d ' ')" == "65" ]] || fail "备份密钥格式错误"
if ! KEY_MODE="$(stat -f '%Lp' "${KEY_ROOT}/backup.key" 2>/dev/null)"; then
  KEY_MODE="$(stat -c '%a' "${KEY_ROOT}/backup.key")"
fi
[[ "${KEY_MODE}" == "600" ]] || fail "备份密钥权限不是 0600"

mkdir -p "${KEY_ROOT}/retention"
for generation in 01 02 03 04 05 06 07 08; do
  archive="${KEY_ROOT}/retention/common-agent-202001${generation}T000000Z.cab"
  : > "${archive}"
  touch -t "202001${generation}0000" "${archive}"
done
BACKUP_ROOT="${KEY_ROOT}/retention" "${MANAGER}" prune
[[ ! -e "${KEY_ROOT}/retention/common-agent-20200101T000000Z.cab" ]] || \
  fail "保留策略没有删除超期且超出最小代际的备份"
[[ "$(find "${KEY_ROOT}/retention" -type f -name '*.cab' | wc -l | tr -d ' ')" == "7" ]] || \
  fail "保留策略没有保住最新 7 个代际"

INVALID_OUTPUT="$(mktemp)"
if "${MANAGER}" invalid >"${INVALID_OUTPUT}" 2>&1; then
  rm -f "${INVALID_OUTPUT}"
  fail "未知备份动作仍被放行"
fi
grep -Fq '用法: infra/backup/manage.sh {init-key|backup|verify|restore|prune|drill}' \
  "${INVALID_OUTPUT}" || fail "未知动作没有稳定用法"
rm -f "${INVALID_OUTPUT}"

echo "备份恢复管理契约通过"
