#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FORK_MANAGER="${SCRIPT_DIR}/fork.sh"
FORK_METADATA="${SCRIPT_DIR}/fork.env"

fail() {
  echo "$1" >&2
  exit 1
}

[[ -x "${FORK_MANAGER}" ]] || fail "缺少可执行的 RAGFlow fork 管理脚本"
[[ -f "${FORK_METADATA}" ]] || fail "缺少 RAGFlow fork 元数据"

# shellcheck disable=SC1090
source "${FORK_METADATA}"

[[ "${RAGFLOW_FORK_GITHUB_REPOSITORY}" == "masterAventador/common-agent-ragflow" ]] || \
  fail "RAGFlow 私有仓库标识漂移"
[[ "${RAGFLOW_FORK_SSH_URL}" == "git@github.com:masterAventador/common-agent-ragflow.git" ]] || \
  fail "RAGFlow 私有仓库 SSH 地址漂移"
[[ "${RAGFLOW_UPSTREAM_URL}" == "https://github.com/infiniflow/ragflow.git" ]] || \
  fail "RAGFlow 官方 upstream 地址漂移"
[[ "${RAGFLOW_UPSTREAM_VERSION}" == "v0.26.4" ]] || fail "RAGFlow 上游版本漂移"
[[ "${RAGFLOW_UPSTREAM_COMMIT}" == "cb93883f3f8c975eecb2fed81210effeb3bdb06f" ]] || \
  fail "RAGFlow 上游基线提交漂移"
[[ "${RAGFLOW_FORK_DEFAULT_BRANCH}" == "main" ]] || fail "RAGFlow fork 基线分支漂移"
[[ "${RAGFLOW_PATCH_BRANCH}" == "common-agent/v0.26.4-minimal" ]] || \
  fail "RAGFlow 版本化补丁分支漂移"

rg --color=never --fixed-strings --quiet \
  'gh repo view "${RAGFLOW_FORK_GITHUB_REPOSITORY}" --json isPrivate,defaultBranchRef' \
  "${FORK_MANAGER}" || fail "远端校验没有关闭失败地检查 GitHub 私有性"

TEST_ROOT="$(mktemp -d)"
cleanup() {
  rm -rf "${TEST_ROOT}"
}
trap cleanup EXIT

SEED_ROOT="${TEST_ROOT}/seed"
UPSTREAM_REMOTE="${TEST_ROOT}/upstream.git"
FORK_REMOTE="${TEST_ROOT}/fork.git"
WORKTREE="${TEST_ROOT}/worktree"

git init --quiet --initial-branch=main "${SEED_ROOT}"
git -C "${SEED_ROOT}" config user.name "common-agent test"
git -C "${SEED_ROOT}" config user.email "common-agent-test@example.invalid"
printf 'official baseline\n' > "${SEED_ROOT}/README.md"
git -C "${SEED_ROOT}" add README.md
git -C "${SEED_ROOT}" commit --quiet -m "official baseline"
BASELINE_COMMIT="$(git -C "${SEED_ROOT}" rev-parse HEAD)"
git -C "${SEED_ROOT}" tag v0.26.4
git clone --quiet --bare "${SEED_ROOT}" "${UPSTREAM_REMOTE}"
git clone --quiet --bare "${SEED_ROOT}" "${FORK_REMOTE}"
git --git-dir="${FORK_REMOTE}" update-ref \
  refs/heads/common-agent/v0.26.4-minimal "${BASELINE_COMMIT}"

fork_command() {
  RAGFLOW_FORK_REMOTE_URL_OVERRIDE="${FORK_REMOTE}" \
  RAGFLOW_UPSTREAM_URL_OVERRIDE="${UPSTREAM_REMOTE}" \
  RAGFLOW_UPSTREAM_COMMIT_OVERRIDE="${BASELINE_COMMIT}" \
  RAGFLOW_FORK_WORKTREE="${WORKTREE}" \
  RAGFLOW_FORK_SKIP_GITHUB_PRIVACY_CHECK=1 \
    "${FORK_MANAGER}" "$@"
}

fork_command prepare
fork_command verify
fork_command verify-remote

[[ "$(git -C "${WORKTREE}" branch --show-current)" == "common-agent/v0.26.4-minimal" ]] || \
  fail "fork 工作区没有检出版本化补丁分支"
[[ "$(git -C "${WORKTREE}" remote get-url origin)" == "${FORK_REMOTE}" ]] || \
  fail "fork origin 没有指向私有仓库"
[[ "$(git -C "${WORKTREE}" remote get-url upstream)" == "${UPSTREAM_REMOTE}" ]] || \
  fail "fork upstream 没有指向官方仓库"
[[ "$(git -C "${WORKTREE}" remote get-url --push upstream)" == "DISABLED" ]] || \
  fail "fork upstream 没有配置为只读"

# 补丁分支允许前进，但必须始终包含锁定的官方基线；main 不允许随补丁漂移。
git -C "${WORKTREE}" config user.name "common-agent test"
git -C "${WORKTREE}" config user.email "common-agent-test@example.invalid"
printf 'patch\n' >> "${WORKTREE}/README.md"
git -C "${WORKTREE}" add README.md
git -C "${WORKTREE}" commit --quiet -m "test patch"
PATCH_COMMIT="$(git -C "${WORKTREE}" rev-parse HEAD)"
git -C "${WORKTREE}" push --quiet origin HEAD:refs/heads/common-agent/v0.26.4-minimal
fork_command verify
fork_command verify-remote

git --git-dir="${FORK_REMOTE}" update-ref refs/heads/main "${PATCH_COMMIT}"
if fork_command verify-remote > /dev/null 2>&1; then
  fail "fork main 偏离官方基线时远端校验仍然放行"
fi

echo "RAGFlow 私有镜像仓库、只读 upstream 与版本化补丁分支门禁通过"
