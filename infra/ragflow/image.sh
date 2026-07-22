#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
IMAGE_METADATA="${SCRIPT_DIR}/image.env"
PATCHSET_METADATA="${SCRIPT_DIR}/patchset.env"
FORK_METADATA="${SCRIPT_DIR}/fork.env"
FORK_DOCKERFILE="${SCRIPT_DIR}/Dockerfile.fork"

fail() {
  echo "$1" >&2
  exit 1
}

for metadata in "${IMAGE_METADATA}" "${PATCHSET_METADATA}" "${FORK_METADATA}"; do
  [[ -f "${metadata}" ]] || fail "缺少 RAGFlow 镜像元数据：${metadata}"
done
[[ -f "${FORK_DOCKERFILE}" ]] || fail "缺少 RAGFlow fork 镜像 Dockerfile"

# shellcheck disable=SC1090
source "${IMAGE_METADATA}"
# shellcheck disable=SC1090
source "${PATCHSET_METADATA}"
# shellcheck disable=SC1090
source "${FORK_METADATA}"

SOURCE_ROOT="${RAGFLOW_RUNTIME_ROOT:-${REPOSITORY_ROOT}/third_party/ragflow}"
EXPECTED_REVISION="${RAGFLOW_IMAGE_EXPECTED_REVISION_OVERRIDE:-${RAGFLOW_FORK_IMAGE_REVISION}}"
EXPECTED_BASE_COMMIT="${RAGFLOW_IMAGE_BASE_COMMIT_OVERRIDE:-${RAGFLOW_UPSTREAM_COMMIT}}"
IMAGE="${RAGFLOW_IMAGE_OVERRIDE:-${RAGFLOW_FORK_IMAGE}}"
BASE_IMAGE="${RAGFLOW_IMAGE_BASE_OVERRIDE:-${RAGFLOW_FORK_IMAGE_BASE}}"
BASE_DIGEST="${RAGFLOW_IMAGE_BASE_DIGEST_OVERRIDE:-${RAGFLOW_FORK_IMAGE_BASE_DIGEST}}"
DOCKER_CONTEXT_NAME="${RAGFLOW_DOCKER_CONTEXT:-colima-common-agent-dev}"

docker_cli() {
  docker --context "${DOCKER_CONTEXT_NAME}" "$@"
}

origin_is_private_fork() {
  case "$1" in
    "${RAGFLOW_FORK_SSH_URL}" | "${RAGFLOW_FORK_HTTPS_URL}") return 0 ;;
    *) return 1 ;;
  esac
}

verify_source() {
  git -C "${SOURCE_ROOT}" rev-parse --is-inside-work-tree >/dev/null 2>&1 || \
    fail "RAGFlow submodule 未初始化：${SOURCE_ROOT}"

  local actual_revision baseline_tag origin changed_path
  actual_revision="$(git -C "${SOURCE_ROOT}" rev-parse HEAD)"
  baseline_tag="$(git -C "${SOURCE_ROOT}" rev-parse "refs/tags/${RAGFLOW_UPSTREAM_VERSION}^{commit}")"
  origin="$(git -C "${SOURCE_ROOT}" remote get-url origin)"

  [[ "${EXPECTED_REVISION}" == "${RAGFLOW_PATCH_HEAD}" ]] || \
    fail "RAGFlow 镜像 revision 覆盖值与补丁集 HEAD 不一致"
  [[ "${RAGFLOW_FORK_IMAGE_REVISION}" == "${RAGFLOW_PATCH_HEAD}" ]] || \
    fail "RAGFlow 镜像元数据与补丁集 HEAD 不一致"
  [[ "${actual_revision}" == "${EXPECTED_REVISION}" ]] || \
    fail "RAGFlow submodule 未锁定镜像 revision：${actual_revision}"
  [[ "${baseline_tag}" == "${EXPECTED_BASE_COMMIT}" ]] || \
    fail "RAGFlow submodule 官方基线 tag 漂移"
  git -C "${SOURCE_ROOT}" merge-base --is-ancestor "${EXPECTED_BASE_COMMIT}" "${actual_revision}" || \
    fail "RAGFlow 镜像 revision 不包含官方基线"
  origin_is_private_fork "${origin}" || fail "RAGFlow submodule origin 未指向私有 fork：${origin}"
  [[ -z "$(git -C "${SOURCE_ROOT}" status --short)" ]] || \
    fail "RAGFlow submodule 必须保持未修改状态：${SOURCE_ROOT}"
  git -C "${SOURCE_ROOT}" diff --check "${EXPECTED_BASE_COMMIT}..${actual_revision}"

  while IFS= read -r changed_path; do
    case "${changed_path}" in
      api/* | rag/* | test/* | docker/*) ;;
      *) fail "RAGFlow 覆盖镜像未包含补丁生产路径：${changed_path}" ;;
    esac
  done < <(git -C "${SOURCE_ROOT}" diff --name-only "${EXPECTED_BASE_COMMIT}..${actual_revision}")

  echo "image=${IMAGE} revision=${actual_revision} base=${EXPECTED_BASE_COMMIT}"
}

ensure_base_image() {
  local repo_digests architecture
  if ! docker_cli image inspect "${BASE_IMAGE}" >/dev/null 2>&1; then
    docker_cli pull --platform linux/amd64 "${BASE_DIGEST}"
    docker_cli tag "${BASE_DIGEST}" "${BASE_IMAGE}"
  fi
  repo_digests="$(docker_cli image inspect "${BASE_IMAGE}" --format '{{json .RepoDigests}}')"
  [[ "${repo_digests}" == *"${BASE_DIGEST}"* ]] || \
    fail "RAGFlow 官方基底 digest 漂移：${repo_digests}"
  architecture="$(docker_cli image inspect "${BASE_IMAGE}" --format '{{.Architecture}}')"
  [[ "${architecture}" == "amd64" ]] || fail "RAGFlow 官方基底必须为 amd64：${architecture}"
}

changed_runtime_paths() {
  local changed_path
  while IFS= read -r changed_path; do
    case "${changed_path}" in
      api/* | rag/*) printf '%s\n' "${changed_path}" ;;
    esac
  done < <(git -C "${SOURCE_ROOT}" diff --name-only "${EXPECTED_BASE_COMMIT}..${EXPECTED_REVISION}")
}

verify_runtime_files() {
  local changed_path digest expected actual
  local -a container_paths=()
  expected=""
  while IFS= read -r changed_path; do
    digest="$(shasum -a 256 "${SOURCE_ROOT}/${changed_path}" | awk '{print $1}')"
    expected+="${digest}  /ragflow/${changed_path}"$'\n'
    container_paths+=("/ragflow/${changed_path}")
  done < <(changed_runtime_paths)
  ((${#container_paths[@]} > 0)) || fail "RAGFlow 补丁集没有可验证的生产源码"
  actual="$(docker_cli run --rm --platform linux/amd64 --entrypoint sha256sum \
    "${IMAGE}" "${container_paths[@]}")"
  [[ "$(printf '%s' "${actual}" | LC_ALL=C sort)" == \
      "$(printf '%s' "${expected}" | LC_ALL=C sort)" ]] || \
    fail "RAGFlow fork 镜像内源码与 submodule 不一致"
}

verify_image() {
  verify_source >/dev/null
  docker_cli image inspect "${IMAGE}" >/dev/null 2>&1 || fail "缺少 RAGFlow fork 镜像：${IMAGE}"

  local revision source base_name base_digest architecture
  revision="$(docker_cli image inspect "${IMAGE}" --format '{{index .Config.Labels "org.opencontainers.image.revision"}}')"
  source="$(docker_cli image inspect "${IMAGE}" --format '{{index .Config.Labels "org.opencontainers.image.source"}}')"
  base_name="$(docker_cli image inspect "${IMAGE}" --format '{{index .Config.Labels "org.opencontainers.image.base.name"}}')"
  base_digest="$(docker_cli image inspect "${IMAGE}" --format '{{index .Config.Labels "com.common-agent.ragflow.base.digest"}}')"
  architecture="$(docker_cli image inspect "${IMAGE}" --format '{{.Architecture}}')"

  [[ "${revision}" == "${EXPECTED_REVISION}" ]] || fail "RAGFlow fork 镜像 revision 漂移"
  [[ "${source}" == "${RAGFLOW_FORK_IMAGE_SOURCE}" ]] || fail "RAGFlow fork 镜像 source 漂移"
  [[ "${base_name}" == "${BASE_IMAGE}" ]] || fail "RAGFlow fork 镜像 base name 漂移"
  [[ "${base_digest}" == "${BASE_DIGEST}" ]] || fail "RAGFlow fork 镜像 base digest 漂移"
  [[ "${architecture}" == "amd64" ]] || fail "RAGFlow fork 镜像必须为 amd64"
  verify_runtime_files
  echo "RAGFlow fork 镜像验证通过：${IMAGE} (${EXPECTED_REVISION})"
}

build_image() {
  verify_source >/dev/null
  ensure_base_image
  docker_cli build \
    --platform linux/amd64 \
    --pull=false \
    --file "${FORK_DOCKERFILE}" \
    --build-arg "RAGFLOW_FORK_IMAGE_BASE=${BASE_IMAGE}" \
    --build-arg "RAGFLOW_FORK_IMAGE_REVISION=${EXPECTED_REVISION}" \
    --build-arg "RAGFLOW_FORK_IMAGE_SOURCE=${RAGFLOW_FORK_IMAGE_SOURCE}" \
    --build-arg "RAGFLOW_FORK_IMAGE_BASE_DIGEST=${BASE_DIGEST}" \
    --tag "${IMAGE}" \
    "${SOURCE_ROOT}"
  verify_image
}

ensure_image() {
  verify_source >/dev/null
  if verify_image >/dev/null 2>&1; then
    echo "复用已验证的 RAGFlow fork 镜像：${IMAGE}"
    return
  fi
  build_image
}

scan_image() {
  verify_image >/dev/null
  command -v trivy >/dev/null 2>&1 || fail "缺少 Trivy，无法扫描 RAGFlow fork 镜像"
  command -v jq >/dev/null 2>&1 || fail "缺少 jq，无法核对 RAGFlow fork 镜像"

  local scan_root fork_report base_report normalized actual_high actual_critical actual_sha docker_host
  scan_root="$(mktemp -d "${TMPDIR:-/tmp}/common-agent-ragflow-image-scan.XXXXXX")"
  fork_report="${scan_root}/fork.json"
  base_report="${scan_root}/base.json"
  normalized="${scan_root}/fork.normalized.json"
  cleanup_scan() {
    find "${scan_root}" -type f -delete
    rmdir "${scan_root}"
  }
  trap cleanup_scan EXIT INT TERM

  docker_host="$(docker context inspect "${DOCKER_CONTEXT_NAME}" --format '{{.Endpoints.docker.Host}}')"
  DOCKER_HOST="${docker_host}" trivy image --quiet --scanners vuln,secret \
    --severity HIGH,CRITICAL --ignore-unfixed --format json --output "${fork_report}" "${IMAGE}"
  DOCKER_HOST="${docker_host}" trivy image --quiet --scanners vuln,secret \
    --severity HIGH,CRITICAL --ignore-unfixed --format json --output "${base_report}" "${BASE_IMAGE}"

  jq -cS '
    [.Results[]?.Vulnerabilities[]?
     | select(.Severity == "HIGH" or .Severity == "CRITICAL")
     | {id: .VulnerabilityID, package: .PkgName, installed_version: .InstalledVersion,
        fixed_version: (.FixedVersion // ""), severity: .Severity}]
    | unique_by([.id, .package, .installed_version, .fixed_version, .severity])
    | sort_by(.severity, .id, .package, .installed_version, .fixed_version)
  ' "${fork_report}" >"${normalized}"
  actual_high="$(jq '[.[] | select(.severity == "HIGH")] | length' "${normalized}")"
  actual_critical="$(jq '[.[] | select(.severity == "CRITICAL")] | length' "${normalized}")"
  actual_sha="$(shasum -a 256 "${normalized}" | awk '{print $1}')"
  [[ "${actual_high}" == "${RAGFLOW_FORK_IMAGE_HIGH}" ]] || fail "RAGFlow fork 镜像 High 结果漂移"
  [[ "${actual_critical}" == "${RAGFLOW_FORK_IMAGE_CRITICAL}" ]] || fail "RAGFlow fork 镜像 Critical 结果漂移"
  [[ "${actual_sha}" == "${RAGFLOW_FORK_IMAGE_FINDINGS_SHA256}" ]] || fail "RAGFlow fork 镜像漏洞明细漂移"

  jq -e --slurpfile base "${base_report}" '
    def secrets($doc):
      [$doc.Results[]? as $result | $result.Secrets[]?
       | [.RuleID, $result.Target, (.StartLine | tostring), (.EndLine | tostring)] | join("|")] | unique;
    secrets(.) == secrets($base[0])
  ' "${fork_report}" >/dev/null || fail "RAGFlow fork 镜像相对官方基底新增或改变 Secret"

  cleanup_scan
  trap - EXIT INT TERM
  echo "RAGFlow fork 镜像安全基线通过：High=${actual_high}, Critical=${actual_critical}, Secret 与官方一致"
}

case "${1:-}" in
  verify-source)
    verify_source
    ;;
  build)
    [[ "${RAGFLOW_IMAGE_SKIP_DOCKER:-0}" == "1" ]] && fail "跳过 Docker 时不能构建镜像"
    build_image
    ;;
  verify)
    if [[ "${RAGFLOW_IMAGE_SKIP_DOCKER:-0}" == "1" ]]; then
      verify_source
    else
      verify_image
    fi
    ;;
  ensure)
    if [[ "${RAGFLOW_IMAGE_SKIP_DOCKER:-0}" == "1" ]]; then
      verify_source
    else
      ensure_image
    fi
    ;;
  scan)
    [[ "${RAGFLOW_IMAGE_SKIP_DOCKER:-0}" == "1" ]] && fail "跳过 Docker 时不能扫描镜像"
    scan_image
    ;;
  *)
    echo "用法: $0 {verify-source|build|verify|ensure|scan}" >&2
    exit 2
    ;;
esac
