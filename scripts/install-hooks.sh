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

# 设置 hooksPath，优先使用仓库内受版本控制的 hooks
# 使用绝对路径，避免不同执行目录导致解析失败
git config core.hooksPath "$CUSTOM_HOOKS_DIR"
echo "✓ 已配置 core.hooksPath"
echo "  - $CUSTOM_HOOKS_DIR"

# 设置可执行权限
find "$CUSTOM_HOOKS_DIR" -maxdepth 1 -type f -exec chmod +x {} \;

# 兼容说明：如存在旧的 .git/hooks/post-commit 文件，给出提示
if [[ -f "$GIT_HOOKS_DIR/post-commit" ]] && [[ ! -L "$GIT_HOOKS_DIR/post-commit" ]]; then
    echo ""
    echo "提示: 检测到旧的 .git/hooks/post-commit（已由 core.hooksPath 接管，可忽略）"
fi

echo ""
echo "========================================"
echo "  安装完成！"
echo "========================================"
echo ""
echo "当前机制："
echo "  - 使用 scripts/git-hooks 下的受控 Hook"
echo "  - 版本号更新通过 post-commit amend 到当前提交，不再新增第二个提交"
echo "  - rebase/cherry-pick/merge 场景自动跳过版本更新"
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
