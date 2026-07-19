#!/usr/bin/env bash
set -euo pipefail

contract_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
contract_project_root="$(cd "${contract_script_dir}/.." && pwd)"
contract_temp_dir="$(mktemp -d "${TMPDIR:-/tmp}/common-agent-contracts.XXXXXX")"
contract_temp_openapi="${contract_temp_dir}/openapi.json"
contract_temp_conversation_event="${contract_temp_dir}/conversation-event.schema.json"
contract_temp_workflow_run_event="${contract_temp_dir}/workflow-run-event.schema.json"
contract_temp_types="${contract_temp_dir}/schema.d.ts"

cleanup_contract_temp() {
  rm -f \
    "${contract_temp_openapi}" \
    "${contract_temp_conversation_event}" \
    "${contract_temp_workflow_run_event}" \
    "${contract_temp_types}"
  rmdir "${contract_temp_dir}"
}
trap cleanup_contract_temp EXIT

cd "${contract_project_root}/backend"
uv run --frozen python -m common_agent.contracts.export_openapi --output "${contract_temp_openapi}"
uv run --frozen python -m common_agent.contracts.export_event_schema \
  --output "${contract_temp_conversation_event}" \
  --workflow-output "${contract_temp_workflow_run_event}"

cd "${contract_project_root}/frontend"
pnpm exec openapi-typescript "${contract_temp_openapi}" -o "${contract_temp_types}"

cmp "${contract_project_root}/contracts/openapi/openapi.json" "${contract_temp_openapi}"
cmp "${contract_project_root}/contracts/events/conversation-event.schema.json" \
  "${contract_temp_conversation_event}"
cmp "${contract_project_root}/contracts/events/workflow-run-event.schema.json" \
  "${contract_temp_workflow_run_event}"
cmp "${contract_project_root}/frontend/src/api/generated/schema.d.ts" "${contract_temp_types}"
