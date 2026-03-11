#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT=$(git rev-parse --show-toplevel)
cd "$PROJECT_ROOT"

mkdir -p .githooks
chmod +x .githooks/* 2>/dev/null || true

git config core.hooksPath .githooks

echo "[hooks] 已将 core.hooksPath 设置为 .githooks"
echo "[hooks] 当前按钮提交与命令行提交都会使用仓库内 Hook 生成变更碎片"
