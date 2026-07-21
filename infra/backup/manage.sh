#!/usr/bin/env bash
# shellcheck disable=SC2016 # Container-side commands expand only inside their target container.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
POLICY_FILE="${SCRIPT_DIR}/policy.env"
CONFIG_ALLOWLIST="${SCRIPT_DIR}/deployment-config.allowlist"
# shellcheck disable=SC1090 # The policy path is resolved from this script's absolute directory.
source "${POLICY_FILE}"

DOCKER_CONTEXT_NAME="${BACKUP_DOCKER_CONTEXT:-colima-common-agent-dev}"
BACKUP_ROOT="${BACKUP_ROOT:-${REPOSITORY_ROOT}/.local/backups}"
BACKUP_ENCRYPTION_KEY_FILE="${BACKUP_ENCRYPTION_KEY_FILE:-${REPOSITORY_ROOT}/.local/secrets/backup-encryption-key}"
PLATFORM_CONTAINER="${BACKUP_PLATFORM_CONTAINER:-common-agent-platform-mysql}"
PLATFORM_DATABASE="${BACKUP_PLATFORM_DATABASE:-common_agent}"
RAGFLOW_CONTAINER_PREFIX="${BACKUP_RAGFLOW_CONTAINER_PREFIX:-common-agent-ragflow}"
RAGFLOW_VOLUME_PREFIX="${BACKUP_RAGFLOW_VOLUME_PREFIX:-common-agent-ragflow}"
SNAPSHOT_IMAGE="mysql:8.0.39"

docker_cli() {
  docker --context "${DOCKER_CONTEXT_NAME}" "$@"
}

archive_cli() {
  (
    cd "${REPOSITORY_ROOT}/backend"
    "${REPOSITORY_ROOT}/scripts/uv.sh" run --frozen python -m \
      common_agent.adapters.backup.archive "$@"
  )
}

validate_positive_integer() {
  local name="$1"
  local value="$2"
  if [[ ! "${value}" =~ ^[1-9][0-9]*$ ]]; then
    echo "${name} 必须是正整数：${value}" >&2
    return 1
  fi
}

validate_policy() {
  validate_positive_integer BACKUP_RPO_HOURS "${BACKUP_RPO_HOURS}"
  validate_positive_integer BACKUP_RTO_MINUTES "${BACKUP_RTO_MINUTES}"
  validate_positive_integer BACKUP_RETENTION_DAYS "${BACKUP_RETENTION_DAYS}"
  validate_positive_integer BACKUP_MINIMUM_GENERATIONS "${BACKUP_MINIMUM_GENERATIONS}"
  validate_positive_integer BACKUP_DRILL_INTERVAL_DAYS "${BACKUP_DRILL_INTERVAL_DAYS}"
  if ((BACKUP_RETENTION_DAYS < 7 || BACKUP_MINIMUM_GENERATIONS < 2)); then
    echo "备份保留策略不得低于 7 天和 2 个代际" >&2
    return 1
  fi
}

validate_database_identifier() {
  local value="$1"
  if [[ ! "${value}" =~ ^[A-Za-z][A-Za-z0-9_]{0,63}$ ]]; then
    echo "数据库名称格式非法：${value}" >&2
    return 1
  fi
}

validate_key_file() {
  if [[ ! -f "${BACKUP_ENCRYPTION_KEY_FILE}" || -L "${BACKUP_ENCRYPTION_KEY_FILE}" ]]; then
    echo "备份加密密钥不存在或不是普通文件：${BACKUP_ENCRYPTION_KEY_FILE}" >&2
    return 1
  fi
  local permissions
  if ! permissions="$(stat -f '%Lp' "${BACKUP_ENCRYPTION_KEY_FILE}" 2>/dev/null)"; then
    permissions="$(stat -c '%a' "${BACKUP_ENCRYPTION_KEY_FILE}")"
  fi
  if [[ "${permissions}" != "600" ]]; then
    echo "备份加密密钥权限必须是 0600：${BACKUP_ENCRYPTION_KEY_FILE}" >&2
    return 1
  fi
  if ! grep -Eq '^[0-9a-fA-F]{64}$' "${BACKUP_ENCRYPTION_KEY_FILE}"; then
    echo "备份加密密钥必须是 64 位十六进制值" >&2
    return 1
  fi
}

init_key() {
  if [[ -e "${BACKUP_ENCRYPTION_KEY_FILE}" ]]; then
    validate_key_file
    echo "复用现有备份加密密钥：${BACKUP_ENCRYPTION_KEY_FILE}"
    return
  fi
  umask 077
  mkdir -p "$(dirname "${BACKUP_ENCRYPTION_KEY_FILE}")"
  openssl rand -hex 32 > "${BACKUP_ENCRYPTION_KEY_FILE}"
  chmod 0600 "${BACKUP_ENCRYPTION_KEY_FILE}"
  validate_key_file
  echo "已创建备份加密密钥：${BACKUP_ENCRYPTION_KEY_FILE}"
  echo "密钥必须与备份分开保管；丢失后归档无法恢复"
}

container_state() {
  docker_cli inspect --format '{{.State.Status}}' "$1" 2>/dev/null || true
}

require_platform_mysql() {
  if [[ "$(container_state "${PLATFORM_CONTAINER}")" != "running" ]]; then
    echo "平台 MySQL 容器必须正在运行：${PLATFORM_CONTAINER}" >&2
    return 1
  fi
  if ! docker_cli exec "${PLATFORM_CONTAINER}" sh -ec \
    'MYSQL_PWD="${MYSQL_ROOT_PASSWORD}" mysqladmin --protocol=socket -uroot ping --silent'; then
    echo "平台 MySQL 未通过健康检查：${PLATFORM_CONTAINER}" >&2
    return 1
  fi
}

require_quiesced_application() {
  local label
  local port
  if command -v launchctl > /dev/null 2>&1; then
    for label in \
      com.masteraventador.common-agent.dev.worker \
      com.masteraventador.common-agent.real.worker; do
      if launchctl list "${label}" > /dev/null 2>&1; then
        echo "备份前必须停止独立 Worker：${label}" >&2
        return 1
      fi
    done
  fi
  for port in "${COMMON_AGENT_API_PORT:-18200}" "${COMMON_AGENT_WEB_PORT:-18280}"; do
    if lsof -nP -iTCP:"${port}" -sTCP:LISTEN > /dev/null 2>&1; then
      echo "备份前必须停止 API、Worker 和前端；端口仍在监听：${port}" >&2
      return 1
    fi
  done
}

require_stopped_ragflow() {
  local suffix
  local name
  local state
  for suffix in api elasticsearch mysql minio valkey; do
    name="${RAGFLOW_CONTAINER_PREFIX}-${suffix}"
    state="$(container_state "${name}")"
    if [[ "${state}" == "running" || "${state}" == "restarting" ]]; then
      echo "RAGFlow 容器必须已停止后才能创建一致冷快照：${name}" >&2
      return 1
    fi
  done
}

ragflow_volume_name() {
  case "$1" in
    esdata-v2) echo "${RAGFLOW_VOLUME_PREFIX}-esdata-v2" ;;
    mysql-data-v3) echo "${RAGFLOW_VOLUME_PREFIX}-mysql-data-v3" ;;
    minio-data-v2) echo "${RAGFLOW_VOLUME_PREFIX}-minio-data-v2" ;;
    valkey-data-v2) echo "${RAGFLOW_VOLUME_PREFIX}-valkey-data-v2" ;;
    *) echo "未知 RAGFlow 数据卷：$1" >&2; return 2 ;;
  esac
}

require_ragflow_volumes() {
  local component
  local volume
  for component in esdata-v2 mysql-data-v3 minio-data-v2 valkey-data-v2; do
    volume="$(ragflow_volume_name "${component}")"
    if ! docker_cli volume inspect "${volume}" > /dev/null 2>&1; then
      echo "RAGFlow 数据卷不存在：${volume}" >&2
      return 1
    fi
  done
}

mysql_root() {
  docker_cli exec "${PLATFORM_CONTAINER}" sh -ec \
    'MYSQL_PWD="${MYSQL_ROOT_PASSWORD}" mysql --protocol=socket -uroot "$@"' sh "$@"
}

capture_platform_database() {
  local stage_root="$1"
  validate_database_identifier "${PLATFORM_DATABASE}"
  mkdir -p "${stage_root}/platform"
  docker_cli exec "${PLATFORM_CONTAINER}" sh -ec \
    'MYSQL_PWD="${MYSQL_ROOT_PASSWORD}" mysqldump --protocol=socket -uroot \
      --single-transaction --quick --routines --triggers --events --hex-blob \
      --set-gtid-purged=OFF --no-tablespaces "$1"' sh "${PLATFORM_DATABASE}" \
    > "${stage_root}/platform/mysql.sql"
  if [[ ! -s "${stage_root}/platform/mysql.sql" ]]; then
    echo "平台 MySQL 逻辑备份为空" >&2
    return 1
  fi
  mysql_root --batch --skip-column-names "${PLATFORM_DATABASE}" --execute \
    "SELECT COALESCE(JSON_ARRAYAGG(JSON_OBJECT('tenant_id', tenant_id, 'knowledge_base_id', knowledge_base_id)), JSON_ARRAY()) FROM (SELECT tenant_id, knowledge_base_id FROM ragflow_knowledge_base_ownerships ORDER BY tenant_id, knowledge_base_id) AS refs" \
    > "${stage_root}/platform/ragflow-external-references.json"
  mysql_root --batch --skip-column-names "${PLATFORM_DATABASE}" --execute \
    "SELECT version_num FROM alembic_version LIMIT 1" \
    > "${stage_root}/platform/alembic-version.txt"
}

capture_ragflow_volumes() {
  local stage_root="$1"
  local component
  local volume
  mkdir -p "${stage_root}/ragflow"
  for component in esdata-v2 mysql-data-v3 minio-data-v2 valkey-data-v2; do
    volume="$(ragflow_volume_name "${component}")"
    docker_cli run --rm \
      --entrypoint sh \
      -v "${volume}:/source:ro" \
      -v "${stage_root}/ragflow:/backup" \
      "${SNAPSHOT_IMAGE}" \
      -ec 'tar -C /source -cpf "/backup/$1.tar" .' sh "${component}"
    if [[ ! -s "${stage_root}/ragflow/${component}.tar" ]]; then
      echo "RAGFlow 数据卷快照为空：${volume}" >&2
      return 1
    fi
  done
}

capture_deployment_config() {
  local stage_root="$1"
  local variable
  local value
  mkdir -p "${stage_root}/config/repository"
  : > "${stage_root}/config/deployment.env"
  while IFS= read -r variable; do
    [[ -n "${variable}" ]] || continue
    value="${!variable-}"
    [[ -n "${value}" ]] || continue
    if [[ "${value}" == *$'\n'* || "${value}" == *$'\r'* ]]; then
      echo "部署配置包含非法换行：${variable}" >&2
      return 1
    fi
    printf '%s=%s\n' "${variable}" "${value}" >> "${stage_root}/config/deployment.env"
  done < "${CONFIG_ALLOWLIST}"
  cp "${REPOSITORY_ROOT}/.env.example" "${stage_root}/config/repository/env.example"
  cp "${REPOSITORY_ROOT}/infra/platform/compose.yaml" \
    "${stage_root}/config/repository/platform-compose.yaml"
  cp "${REPOSITORY_ROOT}/infra/platform/MYSQL_VERSION" \
    "${stage_root}/config/repository/platform-mysql-version.txt"
  cp "${REPOSITORY_ROOT}/infra/ragflow/compose.override.yaml" \
    "${stage_root}/config/repository/ragflow-compose.override.yaml"
  cp "${REPOSITORY_ROOT}/infra/ragflow/VERSION" \
    "${stage_root}/config/repository/ragflow-version.txt"
  cp "${REPOSITORY_ROOT}/infra/ragflow/UPSTREAM_COMMIT" \
    "${stage_root}/config/repository/ragflow-upstream-commit.txt"
  cp "${POLICY_FILE}" "${stage_root}/config/repository/backup-policy.env"
}

write_metadata() {
  local output="$1"
  local archive_id="$2"
  local created_at="$3"
  local revision
  revision="$(git -C "${REPOSITORY_ROOT}" rev-parse HEAD)"
  jq -n \
    --arg archive_id "${archive_id}" \
    --arg created_at "${created_at}" \
    --arg source_revision "${revision}" \
    --argjson rpo_hours "${BACKUP_RPO_HOURS}" \
    --argjson rto_minutes "${BACKUP_RTO_MINUTES}" \
    --argjson retention_days "${BACKUP_RETENTION_DAYS}" \
    --argjson minimum_generations "${BACKUP_MINIMUM_GENERATIONS}" \
    --argjson drill_interval_days "${BACKUP_DRILL_INTERVAL_DAYS}" \
    '{archive_id: $archive_id, created_at: $created_at, source_revision: $source_revision,
      policy: {rpo_hours: $rpo_hours, rto_minutes: $rto_minutes,
        retention_days: $retention_days, minimum_generations: $minimum_generations,
        drill_interval_days: $drill_interval_days},
      consistency: "application-quiesced-ragflow-cold-platform-mysql-single-transaction"}' \
    > "${output}"
}

cleanup_work_directory() {
  local path="$1"
  [[ -n "${path}" && "${path}" == "${BACKUP_ROOT}/work/"* ]] || return 1
  rm -rf -- "${path}"
}

create_backup() {
  validate_policy
  validate_key_file
  require_quiesced_application
  require_platform_mysql
  require_stopped_ragflow
  require_ragflow_volumes
  mkdir -p "${BACKUP_ROOT}/work"
  chmod 0700 "${BACKUP_ROOT}" "${BACKUP_ROOT}/work"
  local created_at
  local timestamp
  local archive_id
  local output
  local work_directory
  created_at="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  timestamp="$(date -u '+%Y%m%dT%H%M%SZ')"
  archive_id="common-agent-${timestamp}"
  output="${BACKUP_ROOT}/${archive_id}.cab"
  work_directory="$(mktemp -d "${BACKUP_ROOT}/work/${archive_id}.XXXXXX")"
  trap 'cleanup_work_directory "${work_directory}"' RETURN
  mkdir -p "${work_directory}/payload"

  capture_platform_database "${work_directory}/payload"
  capture_ragflow_volumes "${work_directory}/payload"
  capture_deployment_config "${work_directory}/payload"
  write_metadata "${work_directory}/metadata.json" "${archive_id}" "${created_at}"
  archive_cli pack \
    --source "${work_directory}/payload" \
    --output "${output}" \
    --key-file "${BACKUP_ENCRYPTION_KEY_FILE}" \
    --metadata-file "${work_directory}/metadata.json" > /dev/null
  BACKUP_ARCHIVE_FILE="${output}" verify_backup > /dev/null
  prune_backups
  echo "已创建并验证加密备份：${output}"
}

resolve_archive_file() {
  local archive="${BACKUP_ARCHIVE_FILE:-}"
  if [[ -z "${archive}" || ! -f "${archive}" || -L "${archive}" ]]; then
    echo "BACKUP_ARCHIVE_FILE 必须指向普通备份文件" >&2
    return 1
  fi
  printf '%s\n' "${archive}"
}

verify_backup() {
  validate_key_file
  local archive
  archive="$(resolve_archive_file)"
  archive_cli inspect --input "${archive}" --key-file "${BACKUP_ENCRYPTION_KEY_FILE}"
}

prune_backups() {
  validate_policy
  mkdir -p "${BACKUP_ROOT}"
  local now
  local cutoff
  local kept=0
  local archive
  local modified
  now="$(date +%s)"
  cutoff=$((now - BACKUP_RETENTION_DAYS * 86400))
  while IFS= read -r archive; do
    [[ -n "${archive}" ]] || continue
    kept=$((kept + 1))
    if ((kept <= BACKUP_MINIMUM_GENERATIONS)); then
      continue
    fi
    if ! modified="$(stat -f '%m' "${archive}" 2>/dev/null)"; then
      modified="$(stat -c '%Y' "${archive}")"
    fi
    if ((modified < cutoff)); then
      rm -f -- "${archive}"
      echo "已按保留策略删除过期备份：${archive}"
    fi
  done < <(find "${BACKUP_ROOT}" -maxdepth 1 -type f -name 'common-agent-*.cab' -print | sort -r)
}

validate_recovery_target() {
  local recovery_id="$1"
  if [[ ! "${recovery_id}" =~ ^[a-z0-9][a-z0-9-]{3,39}$ ]]; then
    echo "BACKUP_RECOVERY_ID 必须是 4-40 位小写隔离标识" >&2
    return 1
  fi
  if [[ "${BACKUP_RESTORE_CONFIRMATION:-}" != "restore-to-empty-recovery-environment" ]]; then
    echo "恢复前必须显式设置 BACKUP_RESTORE_CONFIRMATION=restore-to-empty-recovery-environment" >&2
    return 1
  fi
}

require_empty_recovery_mysql() {
  local container="$1"
  local database="$2"
  if [[ "$(container_state "${container}")" != "running" ]]; then
    echo "空恢复 MySQL 容器必须正在运行：${container}" >&2
    return 1
  fi
  local table_count
  table_count="$(docker_cli exec "${container}" sh -ec \
    'MYSQL_PWD="${MYSQL_ROOT_PASSWORD}" mysql --protocol=socket -N -uroot -e \
      "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = '\''$1'\''"' \
    sh "${database}")"
  if [[ "${table_count}" != "0" ]]; then
    echo "恢复目标数据库不是空环境：${database}" >&2
    return 1
  fi
}

require_absent_recovery_volumes() {
  local prefix="$1"
  local component
  local volume
  for component in esdata-v2 mysql-data-v3 minio-data-v2 valkey-data-v2; do
    volume="${prefix}-${component}"
    if docker_cli volume inspect "${volume}" > /dev/null 2>&1; then
      echo "恢复目标数据卷已存在，拒绝覆盖：${volume}" >&2
      return 1
    fi
  done
}

restore_platform_database() {
  local container="$1"
  local database="$2"
  local dump="$3"
  docker_cli exec "${container}" sh -ec \
    'MYSQL_PWD="${MYSQL_ROOT_PASSWORD}" mysql --protocol=socket -uroot -e \
      "CREATE DATABASE IF NOT EXISTS \`$1\` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci"' \
    sh "${database}"
  docker_cli exec -i "${container}" sh -ec \
    'MYSQL_PWD="${MYSQL_ROOT_PASSWORD}" mysql --protocol=socket -uroot "$1"' \
    sh "${database}" < "${dump}"
}

restore_ragflow_volumes() {
  local prefix="$1"
  local payload_root="$2"
  local component
  local volume
  for component in esdata-v2 mysql-data-v3 minio-data-v2 valkey-data-v2; do
    volume="${prefix}-${component}"
    docker_cli volume create "${volume}" > /dev/null
    docker_cli run --rm \
      --entrypoint sh \
      -v "${volume}:/target" \
      -v "${payload_root}/ragflow:/backup:ro" \
      "${SNAPSHOT_IMAGE}" \
      -ec 'test -z "$(ls -A /target)"; tar -C /target -xpf "/backup/$1.tar"' \
      sh "${component}"
  done
}

restore_backup() {
  validate_policy
  validate_key_file
  local recovery_id="${BACKUP_RECOVERY_ID:-}"
  validate_recovery_target "${recovery_id}"
  local archive
  local mysql_container="common-agent-recovery-${recovery_id}-mysql"
  local database="common_agent_recovery"
  local volume_prefix="common-agent-recovery-${recovery_id}-ragflow"
  local recovery_root="${REPOSITORY_ROOT}/.local/recovery/${recovery_id}"
  local work_directory
  archive="$(resolve_archive_file)"
  if [[ -e "${recovery_root}" ]]; then
    echo "恢复目录已存在，拒绝覆盖：${recovery_root}" >&2
    return 1
  fi
  require_empty_recovery_mysql "${mysql_container}" "${database}"
  require_absent_recovery_volumes "${volume_prefix}"
  mkdir -p "${BACKUP_ROOT}/work" "$(dirname "${recovery_root}")"
  work_directory="$(mktemp -d "${BACKUP_ROOT}/work/restore-${recovery_id}.XXXXXX")"
  trap 'cleanup_work_directory "${work_directory}"' RETURN
  archive_cli restore \
    --input "${archive}" \
    --destination "${work_directory}/payload" \
    --key-file "${BACKUP_ENCRYPTION_KEY_FILE}" > "${work_directory}/manifest.json"
  for required in \
    platform/mysql.sql \
    platform/ragflow-external-references.json \
    ragflow/esdata-v2.tar \
    ragflow/mysql-data-v3.tar \
    ragflow/minio-data-v2.tar \
    ragflow/valkey-data-v2.tar \
    config/deployment.env; do
    if [[ ! -f "${work_directory}/payload/${required}" ]]; then
      echo "备份缺少恢复组件：${required}" >&2
      return 1
    fi
  done
  restore_platform_database \
    "${mysql_container}" "${database}" "${work_directory}/payload/platform/mysql.sql"
  restore_ragflow_volumes "${volume_prefix}" "${work_directory}/payload"
  mkdir -p "${recovery_root}"
  chmod 0700 "${recovery_root}"
  cp -R "${work_directory}/payload/config" "${recovery_root}/deployment"
  cp "${work_directory}/payload/platform/ragflow-external-references.json" \
    "${recovery_root}/ragflow-external-references.json"
  cp "${work_directory}/manifest.json" "${recovery_root}/manifest.json"
  chmod -R go-rwx "${recovery_root}"
  echo "已恢复到独立空环境：${recovery_id}"
  echo "平台 MySQL：${mysql_container}/${database}"
  echo "RAGFlow Volume 前缀：${volume_prefix}"
}

run_drill() {
  exec "${SCRIPT_DIR}/drill.sh"
}

case "${1:-}" in
  init-key) init_key ;;
  backup) create_backup ;;
  verify) verify_backup ;;
  restore) restore_backup ;;
  prune) prune_backups ;;
  drill) run_drill ;;
  *)
    echo "用法: infra/backup/manage.sh {init-key|backup|verify|restore|prune|drill}" >&2
    exit 2
    ;;
esac
