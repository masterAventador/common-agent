#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
METADATA_FILE="${SCRIPT_DIR}/fork.env"

if [[ ! -f "${METADATA_FILE}" ]]; then
  echo "缺少 RAGFlow fork 元数据：${METADATA_FILE}" >&2
  exit 1
fi

# shellcheck disable=SC1090
source "${METADATA_FILE}"

FORK_REMOTE_URL="${RAGFLOW_FORK_REMOTE_URL_OVERRIDE:-${RAGFLOW_FORK_SSH_URL}}"
UPSTREAM_REMOTE_URL="${RAGFLOW_UPSTREAM_URL_OVERRIDE:-${RAGFLOW_UPSTREAM_URL}}"
EXPECTED_COMMIT="${RAGFLOW_UPSTREAM_COMMIT_OVERRIDE:-${RAGFLOW_UPSTREAM_COMMIT}}"
FORK_WORKTREE="${RAGFLOW_FORK_WORKTREE:-${REPOSITORY_ROOT}/.local/ragflow-fork}"
READ_ONLY_PUSH_URL="DISABLED"

fail() {
  echo "$1" >&2
  exit 1
}

require_git_repository() {
  git -C "${FORK_WORKTREE}" rev-parse --is-inside-work-tree > /dev/null 2>&1 || \
    fail "RAGFlow fork 工作区不是 Git 仓库：${FORK_WORKTREE}"
}

remote_branch_commit() {
  local remote_url="$1"
  local branch="$2"
  local result commit extra

  result="$(git ls-remote --heads "${remote_url}" "refs/heads/${branch}")"
  read -r commit extra <<< "${result}"
  [[ -n "${commit:-}" && "${extra:-}" == "refs/heads/${branch}" ]] || \
    fail "远端缺少分支：${branch}"
  [[ "$(wc -l <<< "${result}" | tr -d '[:space:]')" == "1" ]] || \
    fail "远端分支解析结果不唯一：${branch}"
  echo "${commit}"
}

remote_tag_commit() {
  local remote_url="$1"
  local tag="$2"
  local result direct peeled

  result="$(git ls-remote --tags "${remote_url}" "refs/tags/${tag}" "refs/tags/${tag}^{}")"
  direct="$(awk -v ref="refs/tags/${tag}" '$2 == ref { print $1 }' <<< "${result}")"
  peeled="$(awk -v ref="refs/tags/${tag}^{}" '$2 == ref { print $1 }' <<< "${result}")"
  [[ -n "${peeled:-${direct}}" ]] || fail "远端缺少 tag：${tag}"
  echo "${peeled:-${direct}}"
}

verify_local() {
  require_git_repository

  local origin upstream upstream_push branch baseline_tag origin_main worktree_status
  origin="$(git -C "${FORK_WORKTREE}" remote get-url origin)"
  upstream="$(git -C "${FORK_WORKTREE}" remote get-url upstream)"
  upstream_push="$(git -C "${FORK_WORKTREE}" remote get-url --push upstream)"
  branch="$(git -C "${FORK_WORKTREE}" branch --show-current)"
  baseline_tag="$(git -C "${FORK_WORKTREE}" rev-parse "refs/tags/${RAGFLOW_UPSTREAM_VERSION}^{commit}")"
  origin_main="$(git -C "${FORK_WORKTREE}" rev-parse "refs/remotes/origin/${RAGFLOW_FORK_DEFAULT_BRANCH}^{commit}")"
  worktree_status="$(git -C "${FORK_WORKTREE}" status --short)"

  [[ "${origin}" == "${FORK_REMOTE_URL}" ]] || \
    fail "RAGFlow fork origin 不匹配：${origin}"
  [[ "${upstream}" == "${UPSTREAM_REMOTE_URL}" ]] || \
    fail "RAGFlow fork upstream 不匹配：${upstream}"
  [[ "${upstream_push}" == "${READ_ONLY_PUSH_URL}" ]] || \
    fail "RAGFlow fork upstream 未配置为只读"
  [[ "${branch}" == "${RAGFLOW_PATCH_BRANCH}" ]] || \
    fail "RAGFlow fork 工作区必须位于补丁分支：${RAGFLOW_PATCH_BRANCH}"
  [[ "${baseline_tag}" == "${EXPECTED_COMMIT}" ]] || \
    fail "RAGFlow fork 本地 tag 未锁定官方基线"
  [[ "${origin_main}" == "${EXPECTED_COMMIT}" ]] || \
    fail "RAGFlow fork 本地 main 未锁定官方基线"
  git -C "${FORK_WORKTREE}" merge-base --is-ancestor "${EXPECTED_COMMIT}" HEAD || \
    fail "RAGFlow 补丁分支不包含官方基线"
  [[ -z "${worktree_status}" ]] || \
    fail "RAGFlow fork 工作区必须保持未修改状态：${FORK_WORKTREE}"
}

prepare() {
  if [[ ! -e "${FORK_WORKTREE}" ]]; then
    mkdir -p "$(dirname "${FORK_WORKTREE}")"
    git clone --quiet --branch "${RAGFLOW_PATCH_BRANCH}" \
      "${FORK_REMOTE_URL}" "${FORK_WORKTREE}"
  fi

  require_git_repository
  [[ "$(git -C "${FORK_WORKTREE}" remote get-url origin)" == "${FORK_REMOTE_URL}" ]] || \
    fail "已有工作区的 origin 与锁定私有仓库不一致：${FORK_WORKTREE}"

  if git -C "${FORK_WORKTREE}" remote get-url upstream > /dev/null 2>&1; then
    [[ "$(git -C "${FORK_WORKTREE}" remote get-url upstream)" == "${UPSTREAM_REMOTE_URL}" ]] || \
      fail "已有工作区的 upstream 与官方仓库不一致：${FORK_WORKTREE}"
  else
    git -C "${FORK_WORKTREE}" remote add upstream "${UPSTREAM_REMOTE_URL}"
  fi
  git -C "${FORK_WORKTREE}" remote set-url --push upstream "${READ_ONLY_PUSH_URL}"

  git -C "${FORK_WORKTREE}" fetch --quiet origin \
    "+refs/heads/${RAGFLOW_FORK_DEFAULT_BRANCH}:refs/remotes/origin/${RAGFLOW_FORK_DEFAULT_BRANCH}" \
    "+refs/heads/${RAGFLOW_PATCH_BRANCH}:refs/remotes/origin/${RAGFLOW_PATCH_BRANCH}" \
    "refs/tags/${RAGFLOW_UPSTREAM_VERSION}:refs/tags/${RAGFLOW_UPSTREAM_VERSION}"
  git -C "${FORK_WORKTREE}" fetch --quiet upstream \
    "refs/tags/${RAGFLOW_UPSTREAM_VERSION}:refs/tags/${RAGFLOW_UPSTREAM_VERSION}"
  verify_local
  echo "RAGFlow fork 工作区：ready (${FORK_WORKTREE})"
}

verify_remote() {
  require_git_repository

  local fork_main fork_patch fork_tag upstream_tag github_state
  fork_main="$(remote_branch_commit "${FORK_REMOTE_URL}" "${RAGFLOW_FORK_DEFAULT_BRANCH}")"
  fork_patch="$(remote_branch_commit "${FORK_REMOTE_URL}" "${RAGFLOW_PATCH_BRANCH}")"
  fork_tag="$(remote_tag_commit "${FORK_REMOTE_URL}" "${RAGFLOW_UPSTREAM_VERSION}")"
  upstream_tag="$(remote_tag_commit "${UPSTREAM_REMOTE_URL}" "${RAGFLOW_UPSTREAM_VERSION}")"

  [[ "${fork_main}" == "${EXPECTED_COMMIT}" ]] || \
    fail "RAGFlow fork main 已偏离官方基线：${fork_main}"
  [[ "${fork_tag}" == "${EXPECTED_COMMIT}" ]] || \
    fail "RAGFlow fork tag 已偏离官方基线：${fork_tag}"
  [[ "${upstream_tag}" == "${EXPECTED_COMMIT}" ]] || \
    fail "RAGFlow 官方 tag 已偏离锁定基线：${upstream_tag}"

  git -C "${FORK_WORKTREE}" fetch --quiet origin \
    "+refs/heads/${RAGFLOW_FORK_DEFAULT_BRANCH}:refs/remotes/origin/${RAGFLOW_FORK_DEFAULT_BRANCH}" \
    "+refs/heads/${RAGFLOW_PATCH_BRANCH}:refs/remotes/origin/${RAGFLOW_PATCH_BRANCH}"
  git -C "${FORK_WORKTREE}" merge-base --is-ancestor "${EXPECTED_COMMIT}" "${fork_patch}" || \
    fail "RAGFlow 远端补丁分支不包含官方基线"

  if [[ "${RAGFLOW_FORK_SKIP_GITHUB_PRIVACY_CHECK:-0}" != "1" ]]; then
    command -v gh > /dev/null 2>&1 || fail "缺少 gh，无法验证 RAGFlow 私有仓库可见性"
    github_state="$(gh repo view "${RAGFLOW_FORK_GITHUB_REPOSITORY}" --json isPrivate,defaultBranchRef --jq '[.isPrivate, .defaultBranchRef.name] | @tsv')"
    [[ "${github_state}" == $'true\t'"${RAGFLOW_FORK_DEFAULT_BRANCH}" ]] || \
      fail "RAGFlow GitHub 仓库必须保持 private 且默认分支为 ${RAGFLOW_FORK_DEFAULT_BRANCH}"
  fi

  echo "RAGFlow fork 远端：private baseline/patch refs verified"
}

status() {
  require_git_repository
  echo "worktree=${FORK_WORKTREE}"
  echo "origin=$(git -C "${FORK_WORKTREE}" remote get-url origin)"
  echo "upstream=$(git -C "${FORK_WORKTREE}" remote get-url upstream)"
  echo "upstream_push=$(git -C "${FORK_WORKTREE}" remote get-url --push upstream)"
  echo "branch=$(git -C "${FORK_WORKTREE}" branch --show-current)"
  echo "head=$(git -C "${FORK_WORKTREE}" rev-parse HEAD)"
}

case "${1:-}" in
  prepare) prepare ;;
  verify) verify_local ;;
  verify-remote) verify_remote ;;
  status) status ;;
  *)
    echo "用法: $0 {prepare|verify|verify-remote|status}" >&2
    exit 2
    ;;
esac
