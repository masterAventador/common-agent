#!/usr/bin/env bash
set -euo pipefail

UV_PROJECT_VERSION="0.11.16"
UV_SYSTEM_BIN="$(command -v uv || true)"

if [[ -z "${UV_SYSTEM_BIN}" ]]; then
  echo "缺少 uv；请先安装任意支持 'uv tool run' 的版本" >&2
  exit 127
fi

if [[ "$(${UV_SYSTEM_BIN} --version)" == "uv ${UV_PROJECT_VERSION}"* ]]; then
  exec "${UV_SYSTEM_BIN}" "$@"
fi

exec "${UV_SYSTEM_BIN}" tool run --from "uv==${UV_PROJECT_VERSION}" uv "$@"
