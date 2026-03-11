#!/usr/bin/env python3
"""
Deep Vision 版本管理器

自动根据 Git commit message 与本次提交改动更新 version.json。
优先使用规范的提交信息；当提交标题质量较差或缺少结构化正文时，
回退为基于 HEAD 改动文件的结构化更新日志，提升按钮提交场景下的日志质量。

Commit Message 规范：
- feat: / feature: / 新增：/ 实现：/ 支持：  → minor 版本升级
- fix: / bugfix: / patch: / 修复：/ 优化：/ 调整： → patch 版本升级
- breaking: / major: / 重大变更：/ 破坏性变更： → major 版本升级
- docs: / style: / refactor: / test: / chore: / 文档：/ 测试： → 可按原规则跳过

用法：
    python version_manager.py                    # 根据最新 commit 自动更新
    python version_manager.py --type minor       # 手动指定版本类型
    python version_manager.py --version 2.0.0    # 手动指定版本号
    python version_manager.py --dry-run          # 预览变更，不实际修改
"""

import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional, Tuple


SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
VERSION_FILE = PROJECT_ROOT / "web" / "version.json"

CONVENTIONAL_TYPE_MAP = {
    "feat": "minor",
    "feature": "minor",
    "fix": "patch",
    "bugfix": "patch",
    "patch": "patch",
    "breaking": "major",
    "major": "major",
    "docs": "skip",
    "style": "skip",
    "refactor": "skip",
    "test": "skip",
    "chore": "skip",
}

CHINESE_TYPE_MAP = {
    "新增": "minor",
    "实现": "minor",
    "支持": "minor",
    "修复": "patch",
    "优化": "patch",
    "调整": "patch",
    "改进": "patch",
    "完善": "patch",
    "兼容": "patch",
    "重构": "patch",
    "重大变更": "major",
    "破坏性变更": "major",
    "文档": "skip",
    "测试": "skip",
    "工程": "patch",
}

CHANGE_PREFIXES = (
    "前端",
    "后端",
    "测试",
    "工程",
    "文档",
    "资源",
    "运维",
    "流程",
    "修复",
    "优化",
    "新增",
    "实现",
    "支持",
    "兼容",
)

CATEGORY_ORDER = ("前端", "后端", "测试", "工程", "文档", "资源")
CATEGORY_CHANGE_HINTS = {
    "前端": "前端：更新界面交互与展示逻辑。",
    "后端": "后端：更新接口与数据处理逻辑。",
    "测试": "测试：补充并校验相关回归用例。",
    "工程": "工程：更新脚本与自动化流程。",
    "文档": "文档：同步说明与使用文档。",
    "资源": "资源：同步内置资源与示例内容。",
}

ALLOWED_TITLE_CHAR_RE = re.compile(r"[\u4e00-\u9fffA-Za-z0-9\s，。；：、“”‘’《》【】（）()、,.!！?？:：/&%+#\-_=]")
PURE_ASCII_RE = re.compile(r"^[A-Za-z0-9 _./:+\-]+$")

SPECIAL_CHANGE_HINTS = (
    (
        ("scripts/version_manager.py",),
        "工程：优化版本日志生成脚本，支持从提交改动自动整理结构化更新说明。",
    ),
    (
        (".githooks/post-commit",),
        "工程：统一提交后自动升版流程，确保按钮提交也会生成结构化更新日志。",
    ),
    (
        ("scripts/install-hooks.sh",),
        "工程：提供仓库 Hook 安装脚本，统一本地提交流程。",
    ),
    (
        ("tests/test_version_manager.py",),
        "测试：补充版本日志生成回归用例，覆盖脏提交信息与差异归类场景。",
    ),
    (
        ("README.md",),
        "文档：补充 Hook 安装与版本日志维护说明。",
    ),
)

MINOR_KEYWORDS = (
    "新增",
    "实现",
    "支持",
    "接入",
    "引入",
    "创建",
    "提供",
    "上线",
)
PATCH_KEYWORDS = (
    "修复",
    "优化",
    "调整",
    "改进",
    "完善",
    "兼容",
    "补充",
    "稳定",
    "增强",
    "清理",
    "统一",
)
MAJOR_KEYWORDS = ("BREAKING CHANGE", "重大变更", "破坏性变更", "不兼容", "移除")


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").replace("\u00a0", " ")).strip()


def _dedupe_keep_order(items: Iterable[str]) -> List[str]:
    result: List[str] = []
    seen = set()
    for item in items:
        normalized = _normalize_text(item)
        if not normalized or normalized in seen:
            continue
        result.append(normalized)
        seen.add(normalized)
    return result


def _run_git(args: List[str]) -> str:
    result = subprocess.run(
        args,
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        check=False,
    )
    return result.stdout.strip()


def get_latest_commit_message() -> str:
    """获取最新的 commit message。"""
    try:
        return _run_git(["git", "log", "-1", "--pretty=%B"])
    except Exception as exc:
        print(f"获取 commit message 失败: {exc}")
        return ""


def get_latest_commit_hash() -> str:
    """获取最新的 commit hash（短格式）。"""
    try:
        return _run_git(["git", "log", "-1", "--pretty=%h"])
    except Exception:
        return ""


def _normalize_repo_path(path: str) -> str:
    normalized = _normalize_text(path)
    return normalized[2:] if normalized.startswith('./') else normalized


def get_head_changed_files() -> List[str]:
    """获取 HEAD 提交涉及的文件列表。"""
    output = _run_git(["git", "show", "--name-only", "--pretty=", "HEAD"])
    files = []
    for line in output.splitlines():
        path = _normalize_repo_path(line)
        if not path or path == "web/version.json":
            continue
        files.append(path)
    return _dedupe_keep_order(files)


def _path_matches(path: str, pattern: str) -> bool:
    normalized_path = path.strip("/")
    normalized_pattern = pattern.strip("/")
    if normalized_path == normalized_pattern:
        return True
    return normalized_path.startswith(normalized_pattern + "/")


def _categorize_file(path: str) -> str:
    if path.startswith("tests/"):
        return "测试"
    if path == "README.md" or path.startswith("docs/"):
        return "文档"
    if path.startswith(".githooks/") or path.startswith("scripts/") or path.startswith("deploy/"):
        return "工程"
    if path.startswith("resources/"):
        return "资源"
    if path == "web/server.py" or path.endswith(".py"):
        return "后端"
    if path.startswith("web/") and path.endswith((".js", ".html", ".css")):
        return "前端"
    if path.startswith("web/"):
        return "资源"
    return "工程"


def _contains_chinese(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text or ""))


def _looks_like_clean_title(title: str) -> bool:
    text = _normalize_text(title)
    if not text or len(text) < 4:
        return False
    if not _contains_chinese(text):
        return False
    if PURE_ASCII_RE.fullmatch(text):
        return False
    disallowed_count = sum(1 for char in text if not ALLOWED_TITLE_CHAR_RE.fullmatch(char))
    return disallowed_count == 0


def _extract_commit_type_and_title(first_line: str) -> Tuple[Optional[str], str]:
    text = _normalize_text(first_line)
    if not text:
        return None, ""

    conventional_match = re.match(
        r"^(feat|feature|fix|bugfix|patch|breaking|major|docs|style|refactor|test|chore)(\([^)]+\))?:\s*(.+)$",
        text,
        re.IGNORECASE,
    )
    if conventional_match:
        commit_type = conventional_match.group(1).lower()
        return CONVENTIONAL_TYPE_MAP.get(commit_type), _normalize_text(conventional_match.group(3))

    chinese_match = re.match(r"^(新增|实现|支持|修复|优化|调整|改进|完善|兼容|重构|重大变更|破坏性变更|文档|测试|工程)[：:]\s*(.+)$", text)
    if chinese_match:
        prefix = chinese_match.group(1)
        return CHINESE_TYPE_MAP.get(prefix), _normalize_text(chinese_match.group(2))

    return None, text


def _normalize_change_line(line: str) -> Optional[str]:
    text = _normalize_text(line)
    if not text or text.startswith("#"):
        return None

    if text.startswith("- ") or text.startswith("* "):
        text = _normalize_text(text[2:])
    elif re.match(rf"^({'|'.join(CHANGE_PREFIXES)})[：:]\s*.+$", text):
        pass
    elif _contains_chinese(text):
        pass
    else:
        return None

    return text or None


def parse_commit_message(message: str) -> Tuple[str, str, List[str]]:
    """解析 commit message，返回 (版本类型, 标题, 变更列表)。"""
    raw_lines = [_normalize_text(line) for line in str(message or "").splitlines()]
    lines = [line for line in raw_lines if line and not line.startswith("#")]
    if not lines:
        return "patch", "", []

    explicit_type, title = _extract_commit_type_and_title(lines[0])
    version_type = explicit_type or "patch"

    changes = _dedupe_keep_order(
        change for change in (_normalize_change_line(line) for line in lines[1:]) if change
    )

    if not changes and title:
        changes = [title]

    return version_type, title, changes


def increment_version(current: str, version_type: str) -> str:
    """根据版本类型递增版本号。"""
    parts = current.split(".")
    if len(parts) != 3:
        parts = ["1", "0", "0"]

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
    """加载现有的版本数据。"""
    if VERSION_FILE.exists():
        with open(VERSION_FILE, "r", encoding="utf-8") as handle:
            return json.load(handle)
    return {
        "version": "1.0.0",
        "releaseDate": datetime.now().strftime("%Y-%m-%d"),
        "changelog": [],
    }


def save_version_data(data: dict) -> None:
    """保存版本数据。"""
    with open(VERSION_FILE, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)


def _changes_need_diff_fallback(title: str, changes: List[str], changed_files: List[str]) -> bool:
    if not changed_files:
        return False
    if not changes:
        return True
    if len(changes) == 1 and _normalize_text(changes[0]) == _normalize_text(title):
        return True
    if not all(_contains_chinese(change) for change in changes):
        return True
    return False


def _build_changes_from_files(changed_files: List[str]) -> List[str]:
    normalized_files = _dedupe_keep_order(_normalize_repo_path(path) for path in changed_files)
    if not normalized_files:
        return []

    bullets: List[str] = []
    covered_categories = set()

    for patterns, bullet in SPECIAL_CHANGE_HINTS:
        if any(any(_path_matches(path, pattern) for pattern in patterns) for path in normalized_files):
            bullets.append(bullet)
            covered_categories.add(bullet.split("：", 1)[0])

    categories = _dedupe_keep_order(_categorize_file(path) for path in normalized_files)
    for category in CATEGORY_ORDER:
        if category in categories and category not in covered_categories:
            bullets.append(CATEGORY_CHANGE_HINTS[category])

    return _dedupe_keep_order(bullets)


def _build_title_from_files(changed_files: List[str]) -> str:
    normalized_files = _dedupe_keep_order(_normalize_repo_path(path) for path in changed_files)
    categories = set(_categorize_file(path) for path in normalized_files)

    if any(_path_matches(path, "scripts/version_manager.py") for path in normalized_files) or any(
        _path_matches(path, ".githooks/post-commit") for path in normalized_files
    ):
        title = "优化版本日志生成与提交流程"
    elif "前端" in categories and "后端" in categories:
        title = "完善前后端功能链路"
    elif "前端" in categories:
        title = "优化前端交互与展示逻辑"
    elif "后端" in categories:
        title = "完善后端处理逻辑"
    elif "工程" in categories and "文档" in categories:
        title = "完善工程流程与使用说明"
    elif "工程" in categories:
        title = "优化工程脚本与提交流程"
    elif "资源" in categories:
        title = "同步内置资源与配置"
    elif "文档" in categories:
        title = "补充使用说明与维护文档"
    elif "测试" in categories:
        title = "补充回归测试"
    else:
        title = "同步本次功能与流程改动"

    if "测试" in categories and "测试" not in title and "回归" not in title:
        title += "并补充回归测试"

    return title


def _infer_version_type_from_context(title: str, changes: List[str], changed_files: List[str]) -> str:
    categories = set(_categorize_file(_normalize_repo_path(path)) for path in changed_files)
    combined_text = "\n".join([title] + list(changes))

    if categories and categories.issubset({"文档", "测试"}):
        return "skip"
    if categories and categories.issubset({"工程", "文档", "测试"}):
        return "patch"
    if any(keyword in combined_text for keyword in MAJOR_KEYWORDS):
        return "major"
    if any(keyword in combined_text for keyword in MINOR_KEYWORDS):
        return "minor"
    if any(keyword in combined_text for keyword in PATCH_KEYWORDS):
        return "patch"
    return "patch"


def build_release_notes_from_context(message: str, changed_files: List[str]) -> Tuple[str, str, List[str]]:
    """基于提交信息与改动文件生成结构化版本日志。"""
    parsed_type, parsed_title, parsed_changes = parse_commit_message(message)
    explicit_type, _ = _extract_commit_type_and_title(_normalize_text(message.splitlines()[0]) if message.strip() else "")

    title = parsed_title if _looks_like_clean_title(parsed_title) else _build_title_from_files(changed_files)

    if _changes_need_diff_fallback(parsed_title, parsed_changes, changed_files):
        changes = _build_changes_from_files(changed_files)
    else:
        changes = parsed_changes

    if not changes:
        changes = [title] if title else []

    version_type = explicit_type or _infer_version_type_from_context(title, changes, changed_files)
    return version_type, title, _dedupe_keep_order(changes)


def update_version(
    version_type: Optional[str] = None,
    new_version: Optional[str] = None,
    title: Optional[str] = None,
    changes: Optional[List[str]] = None,
    dry_run: bool = False,
) -> bool:
    """更新版本信息。"""
    if version_type is None and new_version is None:
        commit_msg = get_latest_commit_message()
        if not commit_msg:
            print("无法获取 commit message")
            return False

        changed_files = get_head_changed_files()
        version_type, parsed_title, parsed_changes = build_release_notes_from_context(commit_msg, changed_files)

        if title is None:
            title = parsed_title
        if changes is None:
            changes = parsed_changes

        print(f"Commit: {commit_msg.split(chr(10))[0]}")
        print(f"解析结果: type={version_type}, title={title}")
        if changed_files:
            print(f"改动文件: {', '.join(changed_files)}")

    if version_type == "skip":
        print("此 commit 类型不需要更新版本 (docs/style/refactor/test/chore)")
        return False

    data = load_version_data()
    current_version = data.get("version", "1.0.0")
    next_version = new_version or increment_version(current_version, version_type)

    if next_version == current_version:
        print(f"版本号未变化: {current_version}")
        return False

    today = datetime.now().strftime("%Y-%m-%d")
    new_entry = {
        "version": next_version,
        "date": today,
        "type": version_type if version_type in {"major", "minor", "patch"} else "patch",
        "title": title or f"版本 {next_version}",
        "changes": changes or [],
    }

    if dry_run:
        print("\n========== 预览变更 ==========")
        print(f"版本: {current_version} → {next_version}")
        print(f"类型: {new_entry['type']}")
        print(f"标题: {new_entry['title']}")
        print("变更:")
        for change in new_entry["changes"]:
            print(f"  - {change}")
        print("==============================\n")
        return True

    data["version"] = next_version
    data["releaseDate"] = today
    if "changelog" not in data:
        data["changelog"] = []
    data["changelog"].insert(0, new_entry)
    save_version_data(data)

    print(f"版本已更新: {current_version} → {next_version}")
    print(f"版本文件: {VERSION_FILE}")
    return True


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Deep Vision 版本管理器")
    parser.add_argument("--type", "-t", choices=["major", "minor", "patch"], help="手动指定版本类型")
    parser.add_argument("--version", "-v", help="手动指定版本号 (如 2.0.0)")
    parser.add_argument("--title", help="版本标题")
    parser.add_argument("--changes", "-c", nargs="+", help="变更列表")
    parser.add_argument("--dry-run", "-n", action="store_true", help="预览变更，不实际修改")

    args = parser.parse_args()

    success = update_version(
        version_type=args.type,
        new_version=args.version,
        title=args.title,
        changes=args.changes,
        dry_run=args.dry_run,
    )
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
