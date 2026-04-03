#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

ENV_FILE="web/.env.local"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "未找到本地环境文件: $ENV_FILE" >&2
  echo "请先根据 web/.env.example 创建 web/.env.local" >&2
  exit 1
fi

export DEEPVISION_ENV_FILE="$ENV_FILE"

echo "启动 DeepVision 本地开发环境"
echo "环境文件: ${DEEPVISION_ENV_FILE}"

exec uv run web/server.py "$@"
