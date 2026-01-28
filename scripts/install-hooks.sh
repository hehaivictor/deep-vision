#!/bin/bash
#
# 安装 Git Hooks
#
# 用法：
#   ./scripts/install-hooks.sh
#

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
GIT_HOOKS_DIR="$PROJECT_ROOT/.git/hooks"
CUSTOM_HOOKS_DIR="$SCRIPT_DIR/git-hooks"

echo "========================================"
echo "  Deep Vision Git Hooks 安装程序"
echo "========================================"
echo ""

# 检查是否是 git 仓库
if [[ ! -d "$PROJECT_ROOT/.git" ]]; then
    echo "错误: 当前目录不是 git 仓库"
    exit 1
fi

# 创建 hooks 目录（如果不存在）
mkdir -p "$GIT_HOOKS_DIR"

# 安装 post-commit hook
if [[ -f "$CUSTOM_HOOKS_DIR/post-commit" ]]; then
    # 设置可执行权限
    chmod +x "$CUSTOM_HOOKS_DIR/post-commit"

    # 创建软链接
    ln -sf "$CUSTOM_HOOKS_DIR/post-commit" "$GIT_HOOKS_DIR/post-commit"

    echo "✓ post-commit hook 已安装"
    echo "  - 自动根据 commit message 更新版本号"
else
    echo "✗ post-commit hook 文件不存在"
fi

echo ""
echo "========================================"
echo "  安装完成！"
echo "========================================"
echo ""
echo "Commit Message 规范："
echo "  feat: xxx     → minor 版本升级 (新功能)"
echo "  fix: xxx      → patch 版本升级 (修复)"
echo "  breaking: xxx → major 版本升级 (重大变更)"
echo "  docs: xxx     → 不升级版本"
echo ""
echo "示例："
echo "  git commit -m \"feat: 添加用户认证功能\""
echo "  git commit -m \"fix: 修复登录页面样式问题\""
echo ""
echo "跳过版本更新："
echo "  VERSION_SKIP=1 git commit -m \"xxx\""
echo ""
