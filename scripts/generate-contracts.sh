#!/usr/bin/env bash
set -euo pipefail

contract_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
contract_project_root="$(cd "${contract_script_dir}/.." && pwd)"
contract_openapi="${contract_project_root}/contracts/openapi/openapi.json"
contract_types="${contract_project_root}/frontend/src/api/generated/schema.d.ts"

cd "${contract_project_root}/backend"
uv run --frozen python -m common_agent.contracts.export_openapi --output "${contract_openapi}"

cd "${contract_project_root}/frontend"
pnpm exec openapi-typescript "${contract_openapi}" -o "${contract_types}"
