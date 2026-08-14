#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -z "${DEEPVISION_ENV_FILE:-}" ]]; then
  if [[ -f "web/.env.production" ]]; then
    export DEEPVISION_ENV_FILE="web/.env.production"
  elif [[ -f "web/.env.cloud" ]]; then
    export DEEPVISION_ENV_FILE="web/.env.cloud"
  else
    echo "生产启动必须提供环境文件。" >&2
    echo "请设置 DEEPVISION_ENV_FILE，或创建 web/.env.production / web/.env.cloud。" >&2
    exit 1
  fi
fi

echo "启动 DeepVision 生产环境"
echo "环境文件: ${DEEPVISION_ENV_FILE}"

exec python3 scripts/run_gunicorn.py "$@"
