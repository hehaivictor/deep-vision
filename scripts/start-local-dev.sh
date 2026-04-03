#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

ENV_FILES=("web/.env.local")
if [[ -f "web/.env.local.private" ]]; then
  ENV_FILES+=("web/.env.local.private")
fi

export DEEPVISION_ENV_FILE="$(IFS=:; echo "${ENV_FILES[*]}")"

echo "启动 DeepVision 本地开发环境"
echo "环境文件链路: ${DEEPVISION_ENV_FILE}"

exec uv run web/server.py "$@"
