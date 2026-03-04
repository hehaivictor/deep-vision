#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "启动 DeepVision 生产模式（Gunicorn）"
echo "配置文件: web/gunicorn.conf.py"

exec uv run --with gunicorn gunicorn -c web/gunicorn.conf.py web.wsgi:app

