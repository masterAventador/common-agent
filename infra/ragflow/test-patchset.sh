#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATCHSET_VERIFIER="${SCRIPT_DIR}/verify-patchset.sh"
PATCHSET_METADATA="${SCRIPT_DIR}/patchset.env"

fail() {
  echo "$1" >&2
  exit 1
}

[[ -x "${PATCHSET_VERIFIER}" ]] || fail "缺少可执行的 RAGFlow 补丁集验证脚本"
[[ -f "${PATCHSET_METADATA}" ]] || fail "缺少 RAGFlow 补丁集元数据"

TEST_ROOT="$(mktemp -d)"
cleanup() {
  rm -rf "${TEST_ROOT}"
}
trap cleanup EXIT

WORKTREE="${TEST_ROOT}/worktree"
git init --quiet --initial-branch=main "${WORKTREE}"
git -C "${WORKTREE}" config user.name "common-agent test"
git -C "${WORKTREE}" config user.email "common-agent-test@example.invalid"

mkdir -p "${WORKTREE}/api/apps/services"
printf 'baseline\n' > "${WORKTREE}/api/apps/services/example.py"
printf 'baseline\n' > "${WORKTREE}/api/apps/services/conflict.py"
git -C "${WORKTREE}" add .
git -C "${WORKTREE}" commit --quiet -m "official baseline"
BASE_COMMIT="$(git -C "${WORKTREE}" rev-parse HEAD)"

git -C "${WORKTREE}" switch --quiet -c patchset
printf 'patch one\n' >> "${WORKTREE}/api/apps/services/example.py"
git -C "${WORKTREE}" add .
git -C "${WORKTREE}" commit --quiet -m "patch one"
PATCH_ONE="$(git -C "${WORKTREE}" rev-parse HEAD)"
printf 'patch side\n' >> "${WORKTREE}/api/apps/services/conflict.py"
git -C "${WORKTREE}" add .
git -C "${WORKTREE}" commit --quiet -m "patch two"
PATCH_TWO="$(git -C "${WORKTREE}" rev-parse HEAD)"
PATCH_TWO_SHORT="$(git -C "${WORKTREE}" rev-parse --short "${PATCH_TWO}")"

git -C "${WORKTREE}" switch --quiet -c upgrade-audit "${BASE_COMMIT}"
printf 'upstream side\n' >> "${WORKTREE}/api/apps/services/conflict.py"
git -C "${WORKTREE}" add .
git -C "${WORKTREE}" commit --quiet -m "upstream change"
UPGRADE_COMMIT="$(git -C "${WORKTREE}" rev-parse HEAD)"
git -C "${WORKTREE}" switch --quiet patchset

verify_fixture() {
  RAGFLOW_PATCHSET_WORKTREE_OVERRIDE="${WORKTREE}" \
  RAGFLOW_PATCH_BASE_OVERRIDE="${BASE_COMMIT}" \
  RAGFLOW_PATCH_HEAD_OVERRIDE="${PATCH_TWO}" \
  RAGFLOW_PATCH_SHORT_OVERRIDE="${PATCH_TWO_SHORT}" \
  RAGFLOW_PATCH_COMMITS_OVERRIDE="${PATCH_ONE},${PATCH_TWO}" \
  RAGFLOW_UPGRADE_AUDIT_COMMIT_OVERRIDE="${UPGRADE_COMMIT}" \
  RAGFLOW_UPGRADE_EXPECTED_CONFLICTS_OVERRIDE="api/apps/services/conflict.py" \
  RAGFLOW_PATCHSET_SKIP_REMOTE_VERIFY=1 \
    "${PATCHSET_VERIFIER}"
}

verify_fixture >/dev/null

if RAGFLOW_PATCHSET_WORKTREE_OVERRIDE="${WORKTREE}" \
  RAGFLOW_PATCH_BASE_OVERRIDE="${BASE_COMMIT}" \
  RAGFLOW_PATCH_HEAD_OVERRIDE="${PATCH_TWO}" \
  RAGFLOW_PATCH_SHORT_OVERRIDE="${PATCH_TWO_SHORT}" \
  RAGFLOW_PATCH_COMMITS_OVERRIDE="${PATCH_TWO},${PATCH_ONE}" \
  RAGFLOW_UPGRADE_AUDIT_COMMIT_OVERRIDE="${UPGRADE_COMMIT}" \
  RAGFLOW_UPGRADE_EXPECTED_CONFLICTS_OVERRIDE="api/apps/services/conflict.py" \
  RAGFLOW_PATCHSET_SKIP_REMOTE_VERIFY=1 \
    "${PATCHSET_VERIFIER}" >/dev/null 2>&1; then
  fail "补丁顺序漂移时验证仍然放行"
fi

if RAGFLOW_PATCHSET_WORKTREE_OVERRIDE="${WORKTREE}" \
  RAGFLOW_PATCH_BASE_OVERRIDE="${BASE_COMMIT}" \
  RAGFLOW_PATCH_HEAD_OVERRIDE="${PATCH_TWO}" \
  RAGFLOW_PATCH_SHORT_OVERRIDE="${PATCH_TWO_SHORT}" \
  RAGFLOW_PATCH_COMMITS_OVERRIDE="${PATCH_ONE},${PATCH_TWO}" \
  RAGFLOW_UPGRADE_AUDIT_COMMIT_OVERRIDE="${UPGRADE_COMMIT}" \
  RAGFLOW_UPGRADE_EXPECTED_CONFLICTS_OVERRIDE="api/apps/services/other.py" \
  RAGFLOW_PATCHSET_SKIP_REMOTE_VERIFY=1 \
    "${PATCHSET_VERIFIER}" >/dev/null 2>&1; then
  fail "升级冲突路径漂移时验证仍然放行"
fi

printf 'dirty\n' >> "${WORKTREE}/api/apps/services/example.py"
if verify_fixture >/dev/null 2>&1; then
  fail "补丁工作区不干净时验证仍然放行"
fi

echo "RAGFlow 补丁顺序、升级冲突和干净工作区契约通过"
