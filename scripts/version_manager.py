#!/usr/bin/env python3
"""
Deep Vision 版本管理器

自动根据 Git commit message 更新 version.json

Commit Message 规范：
- feat: / feature:  → minor 版本升级 (新功能)
- fix: / bugfix: / patch:  → patch 版本升级 (修复)
- breaking: / major:  → major 版本升级 (重大变更)
- docs: / style: / refactor: / test: / chore:  → 不升级版本

用法：
    python version_manager.py                    # 根据最新 commit 自动更新
    python version_manager.py --type minor       # 手动指定版本类型
    python version_manager.py --version 2.0.0    # 手动指定版本号
    python version_manager.py --dry-run          # 预览变更，不实际修改
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, List


# 版本文件路径
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
VERSION_FILE = PROJECT_ROOT / "web" / "version.json"


def get_latest_commit_message() -> str:
    """获取最新的 commit message"""
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--pretty=%B"],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT
        )
        return result.stdout.strip()
    except Exception as e:
        print(f"获取 commit message 失败: {e}")
        return ""


def get_latest_commit_hash() -> str:
    """获取最新的 commit hash（短格式）"""
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--pretty=%h"],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT
        )
        return result.stdout.strip()
    except Exception:
        return ""


def parse_commit_message(message: str) -> Tuple[str, str, List[str]]:
    """
    解析 commit message，返回 (版本类型, 标题, 变更列表)

    支持的格式：
    - 单行: "feat: 添加新功能"
    - 多行: "feat: 添加新功能\n\n- 变更1\n- 变更2"
    """
    lines = message.strip().split('\n')
    first_line = lines[0].strip() if lines else ""

    # 解析第一行获取类型和标题
    version_type = "patch"  # 默认
    title = first_line

    # 匹配 type: description 或 type(scope): description 格式
    match = re.match(r'^(feat|feature|fix|bugfix|patch|breaking|major|docs|style|refactor|test|chore)(\([^)]+\))?:\s*(.+)$', first_line, re.IGNORECASE)

    if match:
        commit_type = match.group(1).lower()
        title = match.group(3).strip()

        if commit_type in ['feat', 'feature']:
            version_type = "minor"
        elif commit_type in ['fix', 'bugfix', 'patch']:
            version_type = "patch"
        elif commit_type in ['breaking', 'major']:
            version_type = "major"
        elif commit_type in ['docs', 'style', 'refactor', 'test', 'chore']:
            version_type = "skip"  # 不更新版本

    # 检查是否有 BREAKING CHANGE
    if 'BREAKING CHANGE' in message.upper():
        version_type = "major"

    # 解析变更列表（从第三行开始，跳过空行）
    changes = []
    for line in lines[2:]:
        line = line.strip()
        if line.startswith('- '):
            changes.append(line[2:])
        elif line.startswith('* '):
            changes.append(line[2:])
        elif line and not line.startswith('#'):
            changes.append(line)

    # 如果没有变更列表，使用标题作为唯一变更
    if not changes and title:
        changes = [title]

    return version_type, title, changes


def increment_version(current: str, version_type: str) -> str:
    """根据版本类型递增版本号"""
    parts = current.split('.')
    if len(parts) != 3:
        parts = ['1', '0', '0']

    major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])

    if version_type == "major":
        major += 1
        minor = 0
        patch = 0
    elif version_type == "minor":
        minor += 1
        patch = 0
    elif version_type == "patch":
        patch += 1

    return f"{major}.{minor}.{patch}"


def load_version_data() -> dict:
    """加载现有的版本数据"""
    if VERSION_FILE.exists():
        with open(VERSION_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "version": "1.0.0",
        "releaseDate": datetime.now().strftime("%Y-%m-%d"),
        "changelog": []
    }


def save_version_data(data: dict) -> None:
    """保存版本数据"""
    with open(VERSION_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def update_version(
    version_type: Optional[str] = None,
    new_version: Optional[str] = None,
    title: Optional[str] = None,
    changes: Optional[List[str]] = None,
    dry_run: bool = False
) -> bool:
    """
    更新版本信息

    Args:
        version_type: 版本类型 (major/minor/patch/skip)
        new_version: 直接指定新版本号
        title: 版本标题
        changes: 变更列表
        dry_run: 是否只预览不实际修改

    Returns:
        是否成功更新
    """
    # 如果没有指定，从 commit message 解析
    if version_type is None and new_version is None:
        commit_msg = get_latest_commit_message()
        if not commit_msg:
            print("无法获取 commit message")
            return False

        version_type, parsed_title, parsed_changes = parse_commit_message(commit_msg)

        if title is None:
            title = parsed_title
        if changes is None:
            changes = parsed_changes

        print(f"Commit: {commit_msg.split(chr(10))[0]}")
        print(f"解析结果: type={version_type}, title={title}")

    # 跳过不需要更新版本的 commit
    if version_type == "skip":
        print("此 commit 类型不需要更新版本 (docs/style/refactor/test/chore)")
        return False

    # 加载现有数据
    data = load_version_data()
    current_version = data.get("version", "1.0.0")

    # 计算新版本号
    if new_version:
        next_version = new_version
    else:
        next_version = increment_version(current_version, version_type)

    # 检查是否需要更新
    if next_version == current_version:
        print(f"版本号未变化: {current_version}")
        return False

    # 构建新的 changelog 条目
    today = datetime.now().strftime("%Y-%m-%d")
    new_entry = {
        "version": next_version,
        "date": today,
        "type": version_type if version_type in ["major", "minor", "patch"] else "patch",
        "title": title or f"版本 {next_version}",
        "changes": changes or []
    }

    # 预览模式
    if dry_run:
        print("\n========== 预览变更 ==========")
        print(f"版本: {current_version} → {next_version}")
        print(f"类型: {new_entry['type']}")
        print(f"标题: {new_entry['title']}")
        print(f"变更:")
        for change in new_entry['changes']:
            print(f"  - {change}")
        print("==============================\n")
        return True

    # 更新数据
    data["version"] = next_version
    data["releaseDate"] = today

    # 将新条目插入到 changelog 开头
    if "changelog" not in data:
        data["changelog"] = []
    data["changelog"].insert(0, new_entry)

    # 保存
    save_version_data(data)

    print(f"版本已更新: {current_version} → {next_version}")
    print(f"版本文件: {VERSION_FILE}")

    return True


def main():
    """命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(description="Deep Vision 版本管理器")
    parser.add_argument("--type", "-t", choices=["major", "minor", "patch"],
                        help="手动指定版本类型")
    parser.add_argument("--version", "-v", help="手动指定版本号 (如 2.0.0)")
    parser.add_argument("--title", help="版本标题")
    parser.add_argument("--changes", "-c", nargs="+", help="变更列表")
    parser.add_argument("--dry-run", "-n", action="store_true",
                        help="预览变更，不实际修改")

    args = parser.parse_args()

    success = update_version(
        version_type=args.type,
        new_version=args.version,
        title=args.title,
        changes=args.changes,
        dry_run=args.dry_run
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
