#!/usr/bin/env bash
# shellcheck disable=SC2016 # Contract assertions intentionally match literal shell expressions.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNNER="${SCRIPT_DIR}/test-platform-e2e.sh"
PLAYWRIGHT_CONFIG="${SCRIPT_DIR}/../frontend/playwright.config.ts"

fail() {
  echo "$1" >&2
  exit 1
}

grep -Fq 'LIGHT_E2E_MEMORY_GIB=12' "${RUNNER}" || \
  fail "轻量 E2E 没有固定 12 GiB Colima 预算"
grep -Fq 'REAL_E2E_MEMORY_GIB=32' "${RUNNER}" || \
  fail "真实 E2E 没有固定 32 GiB Colima 预算"
grep -Fq 'current_memory_bytes=' "${RUNNER}" || \
  fail "E2E 入口没有检查正在运行的 Colima 实际内存"
grep -Fq 'current_memory_bytes + 1073741823' "${RUNNER}" || \
  fail "E2E 入口没有按 GiB 向上折算 Docker 预留内存"
grep -Fq 'current_memory_gib >= memory_gib' "${RUNNER}" || \
  fail "E2E 入口会为了轻量验收把已经足够的高配 Colima 降档重启"
grep -Fq 'colima stop common-agent-dev' "${RUNNER}" || \
  fail "E2E 入口不能在资源档位不符时重启专属 profile"
grep -Fq 'PLATFORM_DOCKER_CONTEXT="${DOCKER_CONTEXT_NAME}"' "${RUNNER}" || \
  fail "E2E 调整内存前没有限定平台栈 Docker context"
grep -Fq 'infra/ragflow/manage.sh" stop' "${RUNNER}" || \
  fail "E2E 调整内存前没有停止本项目 RAGFlow"
grep -Fq '"auth" || "${E2E_SUITE}" == "tenant-rbac" || "${E2E_SUITE}" == "audit" || "${E2E_SUITE}" == "demo-chat"' "${RUNNER}" || \
  fail "认证、租户和审计 E2E 没有归入轻量档位"
grep -Fq 'e2e/audit.spec.ts' "${RUNNER}" || \
  fail "E2E 入口没有执行正式审计页面用例"
grep -Fq 'COMMON_AGENT_E2E_API_PORT:-18200' "${RUNNER}" || \
  fail "E2E 入口不支持为并行本地项目隔离 API 端口"
grep -Fq 'COMMON_AGENT_E2E_FRONTEND_PORT:-18280' "${RUNNER}" || \
  fail "E2E 入口不支持为并行本地项目隔离前端端口"
grep -Fq 'COMMON_AGENT_API_PORT="${API_PORT}"' "${RUNNER}" || \
  fail "E2E 独立 API 没有实际绑定所选隔离端口"
grep -Fq 'COMMON_AGENT_CORS_ORIGINS="http://127.0.0.1:${FRONTEND_PORT}"' "${RUNNER}" || \
  fail "E2E 独立 API 没有信任所选隔离前端端口"
grep -Fq 'e2e/design-system.spec.ts' "${RUNNER}" || \
  fail "E2E 入口没有执行统一设计正式页面用例"
grep -Fq 'e2e/model-configurations.spec.ts' "${RUNNER}" || \
  fail "E2E 入口没有执行正式模型管理页面用例"
grep -Fq 'e2e/employee-default-model.spec.ts' "${RUNNER}" || \
  fail "E2E 入口没有执行数字员工默认模型正式页面用例"
grep -Fq 'BAILIAN_MODEL="common-agent-invalid-model"' "${RUNNER}" || \
  fail "员工默认模型 E2E 没有排除进程默认模型误命中的假阳性"
grep -Fq 'tests.support.employee_default_model_e2e_cleanup' "${RUNNER}" || \
  fail "员工默认模型 E2E 没有登记精确业务数据清理器"
grep -Fq 'e2e/generic-chat-models.spec.ts' "${RUNNER}" || \
  fail "E2E 入口没有执行通用会话逐轮模型切换正式页面用例"
grep -Fq 'tests.support.generic_chat_models_e2e_cleanup' "${RUNNER}" || \
  fail "通用会话逐轮模型切换 E2E 没有登记精确业务数据清理器"
grep -Fq 'tests.support.model_configuration_e2e_state cleanup' "${RUNNER}" || \
  fail "模型管理 E2E 没有登记精确引用与业务数据清理器"
grep -Fq 'tests.support.audit_e2e_cleanup' "${RUNNER}" || \
  fail "审计 E2E 没有登记精确业务数据清理器"
grep -Fq 'e2e/knowledge-pagination.spec.ts' "${RUNNER}" || \
  fail "E2E 入口没有执行真实 RAGFlow 大分页页面用例"
grep -Fq 'tests.support.knowledge_pagination_e2e_cleanup' "${RUNNER}" || \
  fail "知识库大分页 E2E 没有登记精确业务数据清理器"
grep -Fq 'e2e/knowledge-batch.spec.ts' "${RUNNER}" || \
  fail "E2E 入口没有执行知识库批量拖拽正式页面用例"
grep -Fq 'tests.support.knowledge_batch_e2e_cleanup' "${RUNNER}" || \
  fail "知识库批量拖拽 E2E 没有登记精确业务数据清理器"
grep -Fq 'WORKER_LOG="${ARTIFACT_ROOT}/worker.log"' "${RUNNER}" || \
  fail "平台 E2E 没有保留独立 Worker 日志"
grep -Fq 'python -m common_agent.worker_main' "${RUNNER}" || \
  fail "平台 E2E 没有启动正式独立 Worker 入口"
grep -Fq 'stop_process "${WORKER_PID}"' "${RUNNER}" || \
  fail "平台 E2E 清理阶段没有停止独立 Worker"
grep -Fq 'headless: true' "${PLAYWRIGHT_CONFIG}" || \
  fail "Playwright 没有强制无头运行"
grep -Fq 'channel: "chromium-headless-shell"' "${PLAYWRIGHT_CONFIG}" || \
  fail "Playwright 没有锁定无窗口 chromium-headless-shell"
grep -Fq '"--headless"' "${PLAYWRIGHT_CONFIG}" || \
  fail "Playwright 启动参数没有显式禁止有头模式"
grep -Fq '"--no-startup-window"' "${PLAYWRIGHT_CONFIG}" || \
  fail "Playwright 启动参数没有禁止创建启动窗口"

echo "平台 E2E 资源档位契约通过"
