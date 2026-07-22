#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
MANAGER="${SCRIPT_DIR}/manage.sh"
VERSION="$(tr -d '[:space:]' < "${SCRIPT_DIR}/VERSION")"
SUBMODULE_ROOT="${REPOSITORY_ROOT}/third_party/ragflow"
UPSTREAM_COMMIT="$(tr -d '[:space:]' < "${SCRIPT_DIR}/UPSTREAM_COMMIT")"
TEST_DOCKER_CONTEXT="${COMMON_AGENT_TEST_DOCKER_CONTEXT:-colima}"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/fork.env"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/patchset.env"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/image.env"
EXPECTED_COMMIT="${RAGFLOW_PATCH_HEAD}"

fail() {
  echo "$1" >&2
  exit 1
}

[[ -x "${MANAGER}" ]] || fail "缺少可执行的 RAGFlow 管理脚本"
[[ "${VERSION}" == "v0.26.4" ]] || fail "RAGFlow 版本未固定为 v0.26.4"
[[ "${UPSTREAM_COMMIT}" == "${RAGFLOW_UPSTREAM_COMMIT}" ]] || fail "RAGFlow 上游提交未固定"
[[ "${EXPECTED_COMMIT}" == "9140f309de9129dc7cd6c889f2e0335b3f384628" ]] || fail "RAGFlow fork 提交未固定"
[[ "${RAGFLOW_FORK_IMAGE_REVISION}" == "${EXPECTED_COMMIT}" ]] || fail "RAGFlow 镜像 revision 未固定"
ENV_VERSION_LINE="$(rg --color=never --only-matching '^RAGFLOW_EXPECTED_VERSION=.*' "${REPOSITORY_ROOT}/.env.example" || true)"
[[ "${ENV_VERSION_LINE#*=}" == "${VERSION}" ]] || fail "后端期望的 RAGFlow 版本与基础设施版本不一致"

if rg --color=never --fixed-strings --quiet 'v0.25.6' \
  "${REPOSITORY_ROOT}/.env.example" \
  "${REPOSITORY_ROOT}/README.md" \
  "${REPOSITORY_ROOT}/backend" \
  "${REPOSITORY_ROOT}/frontend" \
  "${REPOSITORY_ROOT}/infra/backup" \
  "${REPOSITORY_ROOT}/infra/production" \
  "${REPOSITORY_ROOT}/infra/ragflow/manage.sh" \
  "${REPOSITORY_ROOT}/infra/ragflow/compose.override.yaml" \
  "${REPOSITORY_ROOT}/scripts/real.sh" \
  "${REPOSITORY_ROOT}/scripts/real-resource-soak.sh" \
  "${REPOSITORY_ROOT}/scripts/test-platform-e2e.sh" \
  "${REPOSITORY_ROOT}/docs/backend-architecture.md"; then
  fail "活动配置、代码、测试或运维文档仍引用旧 RAGFlow v0.25.6"
fi

[[ -f "${REPOSITORY_ROOT}/.gitmodules" ]] || fail "缺少第三方源码 submodule 清单"
[[ "$(git config -f "${REPOSITORY_ROOT}/.gitmodules" --get submodule.third_party/ragflow.path)" == "third_party/ragflow" ]] || \
  fail "RAGFlow submodule 路径未固定"
[[ "$(git config -f "${REPOSITORY_ROOT}/.gitmodules" --get submodule.third_party/ragflow.url)" == "../common-agent-ragflow.git" ]] || \
  fail "RAGFlow submodule 未指向私有相对仓库"
[[ "$(git -C "${SUBMODULE_ROOT}" rev-parse HEAD)" == "${EXPECTED_COMMIT}" ]] || \
  fail "RAGFlow submodule commit 与基础设施锁定值不一致"
[[ "$(git -C "${SUBMODULE_ROOT}" rev-parse "refs/tags/${VERSION}^{commit}")" == "${UPSTREAM_COMMIT}" ]] || \
  fail "RAGFlow submodule 官方 tag 未锁定上游基线"
git -C "${SUBMODULE_ROOT}" merge-base --is-ancestor "${UPSTREAM_COMMIT}" "${EXPECTED_COMMIT}" || \
  fail "RAGFlow submodule fork commit 不包含上游基线"
case "$(git -C "${SUBMODULE_ROOT}" remote get-url origin)" in
  "${RAGFLOW_FORK_SSH_URL}" | "${RAGFLOW_FORK_HTTPS_URL}") ;;
  *) fail "RAGFlow submodule origin 未指向私有 fork" ;;
esac
git -C "${SUBMODULE_ROOT}" diff --quiet || fail "RAGFlow submodule 工作区被修改"
git -C "${SUBMODULE_ROOT}" diff --cached --quiet || fail "RAGFlow submodule 暂存区被修改"

rg --color=never --fixed-strings --quiet 'third_party/ragflow' "${MANAGER}" || \
  fail "RAGFlow 管理脚本没有使用项目 submodule"
rg --color=never --fixed-strings --quiet '"${IMAGE_MANAGER}" ensure' "${MANAGER}" || \
  fail "RAGFlow 管理脚本没有构建或复用已验证 fork 镜像"
rg --color=never --fixed-strings --quiet 'build-image) prepare; "${IMAGE_MANAGER}" build' "${MANAGER}" || \
  fail "RAGFlow 管理脚本缺少 fork 镜像显式构建入口"
rg --color=never --fixed-strings --quiet 'verify-image) prepare; "${IMAGE_MANAGER}" verify' "${MANAGER}" || \
  fail "RAGFlow 管理脚本缺少 fork 镜像验证入口"
rg --color=never --fixed-strings --quiet 'scan-image) prepare; "${IMAGE_MANAGER}" scan' "${MANAGER}" || \
  fail "RAGFlow 管理脚本缺少 fork 镜像安全扫描入口"
if rg --color=never --quiet 'git clone' "${MANAGER}"; then
  fail "RAGFlow 管理脚本不得在运行时临时 clone 上游源码"
fi

UNINITIALIZED_ROOT="$(mktemp -d)"
UNINITIALIZED_OUTPUT="$(mktemp)"
if RAGFLOW_RUNTIME_ROOT="${UNINITIALIZED_ROOT}" "${MANAGER}" prepare > "${UNINITIALIZED_OUTPUT}" 2>&1; then
  rm -rf "${UNINITIALIZED_ROOT}"
  rm -f "${UNINITIALIZED_OUTPUT}"
  fail "未初始化 RAGFlow submodule 时管理脚本仍然放行"
fi
rg --color=never --fixed-strings --quiet 'git submodule update --init --recursive third_party/ragflow' "${UNINITIALIZED_OUTPUT}" || \
  fail "未初始化 RAGFlow submodule 时没有给出可执行修复命令"
rm -rf "${UNINITIALIZED_ROOT}"
rm -f "${UNINITIALIZED_OUTPUT}"

rg --color=never --quiet 'RAGFLOW_DOCKER_CONTEXT:-colima-common-agent-dev' "${MANAGER}"
rg --color=never --quiet '^check_resources\(\)' "${MANAGER}" || \
  fail "RAGFlow 管理脚本缺少 Docker 内存预检"
rg --color=never --quiet 'RAGFLOW_MIN_DOCKER_MEMORY_GIB:-24' "${MANAGER}" || \
  fail "移除本地模型后的 RAGFlow 管理脚本没有保留 24 GiB 最低门禁"
rg --color=never --quiet '建议为 common-agent-dev 分配 32 GiB' "${MANAGER}" || \
  fail "RAGFlow 内存不足错误没有给出项目独立 32 GiB profile 建议"
rg --color=never --quiet 'RAGFLOW_HEALTH_TIMEOUT_SECONDS:-180' "${MANAGER}" || \
  fail "RAGFlow 正式 up 入口缺少可故障注入的有限健康超时"
rg --color=never --fixed-strings --quiet -- '--wait-timeout "${health_timeout_seconds}"' "${MANAGER}" || \
  fail "RAGFlow 正式 up 入口没有把健康超时交给 Docker Compose"
rg --color=never --fixed-strings --quiet 'configure-bailian) configure_bailian_models apply' "${MANAGER}" || \
  fail "RAGFlow 管理脚本缺少百炼模型配置入口"
rg --color=never --fixed-strings --quiet 'check-bailian) configure_bailian_models status' "${MANAGER}" || \
  fail "RAGFlow 管理脚本缺少百炼模型体检入口"
rg --color=never --fixed-strings --quiet 'plan-bailian-migration) configure_bailian_models plan-migration' "${MANAGER}" || \
  fail "RAGFlow 管理脚本缺少既有知识库迁移预检入口"
rg --color=never --fixed-strings --quiet 'migrate-bailian) configure_bailian_models migrate' "${MANAGER}" || \
  fail "RAGFlow 管理脚本缺少既有知识库显式重建入口"
rg --color=never --fixed-strings --quiet 'migrate-native-volumes) migrate_native_volumes' "${MANAGER}" || \
  fail "RAGFlow 管理脚本缺少 macOS bind volume 到原生 Volume 的迁移入口"
rg --color=never --fixed-strings --quiet 'mysqldump --socket=/tmp/mysql.sock' "${MANAGER}" || \
  fail "RAGFlow MySQL 没有通过逻辑导出跨越 lower_case_table_names 数据字典边界"
rg --color=never --fixed-strings --quiet -- '-v "${legacy_volume}:/source:ro"' "${MANAGER}" || \
  fail "RAGFlow MySQL 迁移没有只读复制旧 Volume"
rg --color=never --fixed-strings --quiet 'MYSQL_MIGRATION_SNAPSHOT_ROOT' "${MANAGER}" || \
  fail "RAGFlow MySQL 迁移没有通过独立快照保护旧 Volume"
rg --color=never --fixed-strings --quiet 'common-agent-ragflow-mysql-data-v3' "${MANAGER}" || \
  fail "RAGFlow MySQL 没有使用可跨 Colima 重启的原生 v3 Volume"
CONFIG="$(
  BAILIAN_API_KEY=fixture-bailian-secret \
    BAILIAN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1 \
    BAILIAN_MODEL=qwen-plus \
    RAGFLOW_DOCKER_CONTEXT="${TEST_DOCKER_CONTEXT}" \
    "${MANAGER}" config
)"

service_block() {
  local service_name="$1"
  awk -v service="${service_name}" '
    $0 == "  " service ":" { active = 1; next }
    active && /^  [^ ]/ { exit }
    active { print }
  ' <<< "${CONFIG}"
}

rg --color=never --quiet '^name: common-agent-dev$' <<< "${CONFIG}"
rg --color=never --quiet 'container_name: common-agent-ragflow-api' <<< "${CONFIG}"
rg --color=never --fixed-strings --quiet "image: ${RAGFLOW_FORK_IMAGE}" <<< "${CONFIG}"
rg --color=never --fixed-strings --quiet "RAGFLOW_IMAGE: ${RAGFLOW_FORK_IMAGE}" <<< "$(service_block ragflow-cpu)" || \
  fail "RAGFlow API 容器内镜像元数据没有同步 fork 标签"
rg --color=never --fixed-strings --quiet "image: ${RAGFLOW_ELASTICSEARCH_IMAGE}" <<< "$(service_block es01)" || \
  fail "RAGFlow Elasticsearch 没有锁定已审阅 digest"
rg --color=never --fixed-strings --quiet "image: ${RAGFLOW_MYSQL_IMAGE}" <<< "$(service_block mysql)" || \
  fail "RAGFlow MySQL 没有锁定已审阅 digest"
rg --color=never --fixed-strings --quiet "image: ${RAGFLOW_MINIO_IMAGE}" <<< "$(service_block minio)" || \
  fail "RAGFlow MinIO 没有锁定已审阅 digest"
rg --color=never --fixed-strings --quiet "image: ${RAGFLOW_VALKEY_IMAGE}" <<< "$(service_block redis)" || \
  fail "RAGFlow Valkey 没有锁定已审阅 digest"
rg --color=never --fixed-strings --quiet -- '--init-model-provider-tables' <<< "$(service_block ragflow-cpu)" || \
  fail "RAGFlow v0.26.4 启动入口没有执行官方模型供应商表迁移"
if rg --color=never --quiet '^  nats:' <<< "${CONFIG}"; then
  fail "Python API profile 不得误启用可选 ragflow-go/NATS 服务"
fi
rg --color=never --quiet 'DASHSCOPE_HTTP_BASE_URL: https://dashscope\.aliyuncs\.com/api/v1' <<< "${CONFIG}" || \
  fail "RAGFlow 容器没有通过 DashScope 官方环境变量固定百炼原生 API 端点"
rg --color=never --quiet 'platform: linux/amd64' <<< "$(service_block ragflow-cpu)" || \
  fail "RAGFlow 主镜像必须保持官方 amd64 平台"
for native_service in es01 mysql minio redis; do
  if rg --color=never --quiet 'platform: linux/amd64' <<< "$(service_block "${native_service}")"; then
    fail "外围服务 ${native_service} 不得在 Apple Silicon 强制使用 amd64"
  fi
done
if rg --color=never --quiet 'DOCKER_DEFAULT_PLATFORM' "${MANAGER}"; then
  fail "管理脚本不得把外围多架构镜像全局强制为 amd64"
fi
rg --color=never --quiet 'name: common-agent-ragflow-esdata-v2' <<< "${CONFIG}"
rg --color=never --quiet 'name: common-agent-ragflow-mysql-data-v3' <<< "${CONFIG}"
rg --color=never --quiet 'name: common-agent-ragflow-minio-data-v2' <<< "${CONFIG}"
rg --color=never --quiet 'name: common-agent-ragflow-valkey-data-v2' <<< "${CONFIG}"
if rg --color=never --quiet 'device: .*common-agent-dev/ragflow/data/(elasticsearch|mysql|minio|redis)' <<< "${CONFIG}"; then
  fail "RAGFlow 数据卷不得继续使用会在 Colima 重启后丢失容器 UID 的 macOS bind mount"
fi
rg --color=never --quiet 'host_ip: 127\.0\.0\.1' <<< "${CONFIG}"
rg --color=never --quiet 'published: "19380"' <<< "${CONFIG}"
rg --color=never --quiet 'published: "19387"' <<< "${CONFIG}"
if rg --color=never --quiet 'image: .*:latest' <<< "${CONFIG}"; then
  fail "活动栈不得使用 latest 镜像"
fi
if rg --color=never --quiet 'host_ip: 0\.0\.0\.0' <<< "${CONFIG}"; then
  fail "RAGFlow 端口不得公开绑定"
fi
if rg --color=never --quiet 'container_name: common-agent-ragflow-embedding|image: .*text-embeddings-inference|^  tei-cpu:' <<< "${CONFIG}"; then
  fail "RAGFlow 正式栈不得保留本地 embedding 服务或 profile"
fi
if rg --color=never --quiet 'RAGFLOW_MODEL_ROOT|RAGFLOW_TEI_MODEL|RAGFLOW_TEI_PORT|check-model' "${MANAGER}"; then
  fail "RAGFlow 管理脚本不得保留本地模型路径、端口或检查入口"
fi

INVALID_PORT_OUTPUT="$(mktemp)"
if RAGFLOW_API_PORT=abc "${MANAGER}" check-ports > "${INVALID_PORT_OUTPUT}" 2>&1; then
  rm -f "${INVALID_PORT_OUTPUT}"
  fail "非法端口值仍然被放行"
fi
rg --color=never --quiet '1-65535' "${INVALID_PORT_OUTPUT}"
rm -f "${INVALID_PORT_OUTPUT}"

FAKE_DOCKER_PATH="${REPOSITORY_ROOT}/infra/test-fixtures:${PATH}"
LOW_MEMORY_OUTPUT="$(mktemp)"
if PATH="${FAKE_DOCKER_PATH}" \
  COMMON_AGENT_TEST_DOCKER_MEMORY_BYTES="$((16 * 1024 * 1024 * 1024))" \
  "${MANAGER}" check-resources > "${LOW_MEMORY_OUTPUT}" 2>&1; then
  rm -f "${LOW_MEMORY_OUTPUT}"
  fail "16 GiB Docker profile 仍然被 RAGFlow 资源预检放行"
fi
rg --color=never --quiet '内存不足' "${LOW_MEMORY_OUTPUT}"
rg --color=never --quiet '32 GiB' "${LOW_MEMORY_OUTPUT}"
rm -f "${LOW_MEMORY_OUTPUT}"

PATH="${FAKE_DOCKER_PATH}" \
COMMON_AGENT_TEST_DOCKER_MEMORY_BYTES="$((32 * 1024 * 1024 * 1024))" \
  "${MANAGER}" check-resources

INVALID_MEMORY_OUTPUT="$(mktemp)"
if PATH="${FAKE_DOCKER_PATH}" \
  RAGFLOW_MIN_DOCKER_MEMORY_GIB=invalid \
  COMMON_AGENT_TEST_DOCKER_MEMORY_BYTES="$((32 * 1024 * 1024 * 1024))" \
  "${MANAGER}" check-resources > "${INVALID_MEMORY_OUTPUT}" 2>&1; then
  rm -f "${INVALID_MEMORY_OUTPUT}"
  fail "非法最低内存值仍然被 RAGFlow 资源预检放行"
fi
rg --color=never --quiet '1-128' "${INVALID_MEMORY_OUTPUT}"
rm -f "${INVALID_MEMORY_OUTPUT}"

HEALTH_TEST_OUTPUT="$(mktemp)"
if PATH="${FAKE_DOCKER_PATH}" \
  COMMON_AGENT_TEST_DOCKER_SCENARIO=ragflow-unhealthy \
  COMMON_AGENT_TEST_DOCKER_MEMORY_BYTES="$((32 * 1024 * 1024 * 1024))" \
  RAGFLOW_IMAGE_SKIP_DOCKER=1 \
  RAGFLOW_HEALTH_TIMEOUT_SECONDS=1 \
  "${MANAGER}" up > "${HEALTH_TEST_OUTPUT}" 2>&1; then
  rm -f "${HEALTH_TEST_OUTPUT}"
  fail "RAGFlow 健康失败时正式 up 入口仍然成功返回"
fi
rg --color=never --quiet '模拟 RAGFlow 健康检查失败' "${HEALTH_TEST_OUTPUT}"
rm -f "${HEALTH_TEST_OUTPUT}"

PORT_TEST_OUTPUT="$(mktemp)"
python3 -m http.server 29380 --bind 127.0.0.1 > /dev/null 2>&1 &
PORT_TEST_PID=$!
cleanup() {
  kill "${PORT_TEST_PID}" 2>/dev/null || true
  wait "${PORT_TEST_PID}" 2>/dev/null || true
  rm -f "${PORT_TEST_OUTPUT}"
}
trap cleanup EXIT
sleep 0.3

if RAGFLOW_ES_PORT=29200 \
  RAGFLOW_REDIS_PORT=29379 \
  RAGFLOW_API_PORT=29380 \
  "${MANAGER}" check-ports > "${PORT_TEST_OUTPUT}" 2>&1; then
  fail "端口冲突时管理脚本仍然放行"
fi
rg --color=never --quiet '29380' "${PORT_TEST_OUTPUT}"

echo "RAGFlow 固定版本、隔离、资源与端口冲突门禁通过"
