#!/usr/bin/env python3
"""
Deep Vision 版本管理器

自动根据 Git commit message 与本次提交改动整理版本变更信息。
默认保留传统的 version.json 直写能力，同时支持：
- 功能分支写入 `changes/unreleased/*.json` 变更碎片，避免并行开发抢占正式版本号
- 主线聚合所有变更碎片并生成正式 `web/version.json`

优先使用规范的提交信息；当提交标题质量较差或缺少结构化正文时，
回退为基于改动文件的结构化更新日志，提升按钮提交场景下的日志质量。

Commit Message 规范：
- feat: / feature: / 新增：/ 实现：/ 支持：  → minor 版本升级
- fix: / bugfix: / patch: / 修复：/ 优化：/ 调整： → patch 版本升级
- breaking: / major: / 重大变更：/ 破坏性变更： → major 版本升级
- docs: / style: / refactor: / test: / chore: / 文档：/ 测试： → 可按原规则跳过

用法：
    python version_manager.py                    # 兼容旧流程：根据最新 commit 自动更新 version.json
    python version_manager.py fragment           # 根据当前分支相对主线的改动更新变更碎片
    python version_manager.py release            # 聚合变更碎片并生成正式 version.json
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
from typing import Dict, Iterable, List, Optional, Tuple


SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
VERSION_FILE = PROJECT_ROOT / "web" / "version.json"
CHANGELOG_ROOT = PROJECT_ROOT / "changes"
UNRELEASED_DIR = CHANGELOG_ROOT / "unreleased"
FRAGMENT_SCHEMA_VERSION = 1
DEFAULT_BASE_REFS = ("origin/main", "main", "origin/master", "master")
GENERATED_CHANGE_PATH_PREFIX = "changes/unreleased/"
INTERNAL_RELEASE_SKIP_PATTERNS = (
    ".github/workflows/",
    ".github/actions/",
)

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
    "功能": "minor",
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
        "工程：统一提交后自动生成分支变更碎片，避免并行开发抢占正式版本号。",
    ),
    (
        ("scripts/install-hooks.sh",),
        "工程：提供仓库 Hook 安装脚本，统一本地变更碎片生成流程。",
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


def _normalize_multiline_text(text: str) -> str:
    lines = [_normalize_text(line) for line in str(text or "").replace("\r", "").splitlines()]
    normalized_lines = [line for line in lines if line]
    return "\n".join(normalized_lines)


def _clean_release_title(text: str) -> str:
    title = _normalize_text(text)
    title = re.sub(r"\s*\(#\d+\)$", "", title)
    title = re.sub(r"\s*\[skip release-version\]$", "", title, flags=re.IGNORECASE)
    return _normalize_text(title)


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


def _git_ok(args: List[str]) -> bool:
    result = subprocess.run(
        args,
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        check=False,
    )
    return result.returncode == 0


def get_latest_commit_message() -> str:
    """获取最新的 commit message。"""
    try:
        return _run_git(["git", "log", "-1", "--pretty=%B"])
    except Exception as exc:
        print(f"获取 commit message 失败: {exc}")
        return ""


def get_latest_commit_iso_datetime() -> str:
    """获取最新 commit 的提交时间（ISO-8601）。"""
    try:
        return _run_git(["git", "log", "-1", "--pretty=%cI"])
    except Exception:
        return datetime.now().isoformat(timespec="seconds")


def get_latest_commit_hash() -> str:
    """获取最新的 commit hash（短格式）。"""
    try:
        return _run_git(["git", "log", "-1", "--pretty=%h"])
    except Exception:
        return ""


def get_current_branch() -> str:
    """获取当前分支名。"""
    try:
        branch = _run_git(["git", "rev-parse", "--abbrev-ref", "HEAD"])
        return branch or "HEAD"
    except Exception:
        return "HEAD"


def resolve_base_ref(preferred_ref: Optional[str] = None) -> Optional[str]:
    """解析当前分支用于比较的主线引用。"""
    candidates: List[str] = []
    if preferred_ref:
        candidates.append(preferred_ref)
    for ref in DEFAULT_BASE_REFS:
        if ref not in candidates:
            candidates.append(ref)
    for ref in candidates:
        if _git_ok(["git", "rev-parse", "--verify", "--quiet", ref]):
            return ref
    return None


def _normalize_repo_path(path: str) -> str:
    normalized = _normalize_text(path)
    return normalized[2:] if normalized.startswith('./') else normalized


def _should_ignore_generated_path(path: str) -> bool:
    normalized = _normalize_repo_path(path)
    if not normalized:
        return True
    if normalized == "web/version.json":
        return True
    return normalized.startswith(GENERATED_CHANGE_PATH_PREFIX)


def get_head_changed_files() -> List[str]:
    """获取 HEAD 提交涉及的文件列表。"""
    output = _run_git(["git", "show", "--name-only", "--pretty=", "HEAD"])
    files = []
    for line in output.splitlines():
        path = _normalize_repo_path(line)
        if _should_ignore_generated_path(path):
            continue
        files.append(path)
    return _dedupe_keep_order(files)


def get_branch_changed_files(base_ref: Optional[str] = None) -> List[str]:
    """获取当前分支相对主线的累计改动文件。"""
    resolved_base = resolve_base_ref(base_ref)
    if not resolved_base:
        return get_head_changed_files()

    output = _run_git(["git", "diff", "--name-only", f"{resolved_base}...HEAD"])
    files = []
    for line in output.splitlines():
        path = _normalize_repo_path(line)
        if _should_ignore_generated_path(path):
            continue
        files.append(path)
    return _dedupe_keep_order(files)


def get_branch_commit_messages(base_ref: Optional[str] = None) -> List[str]:
    """获取当前分支相对主线的所有提交信息。"""
    resolved_base = resolve_base_ref(base_ref)
    if not resolved_base:
        latest_message = get_latest_commit_message()
        return [latest_message] if latest_message else []

    output = _run_git(["git", "log", "--format=%B%x1e", f"{resolved_base}..HEAD"])
    messages = [_normalize_multiline_text(chunk) for chunk in output.split("\x1e")]
    return [message for message in messages if message]


def get_branch_commit_count(base_ref: Optional[str] = None) -> int:
    """获取当前分支相对主线领先的提交数。"""
    resolved_base = resolve_base_ref(base_ref)
    if not resolved_base:
        return 1 if get_latest_commit_hash() else 0
    output = _run_git(["git", "rev-list", "--count", f"{resolved_base}..HEAD"])
    try:
        return int(output or "0")
    except ValueError:
        return 0


def get_branch_context_message(base_ref: Optional[str] = None) -> str:
    """汇总当前分支的提交信息，供版本归纳使用。"""
    messages = get_branch_commit_messages(base_ref)
    if not messages:
        return get_latest_commit_message()
    return "\n".join(messages)


def _path_matches(path: str, pattern: str) -> bool:
    normalized_path = path.strip("/")
    normalized_pattern = pattern.strip("/")
    if normalized_path == normalized_pattern:
        return True
    return normalized_path.startswith(normalized_pattern + "/")


def _is_internal_release_only_file(path: str) -> bool:
    normalized = _normalize_repo_path(path)
    if not normalized:
        return False
    return any(_path_matches(normalized, pattern) for pattern in INTERNAL_RELEASE_SKIP_PATTERNS)


def _should_skip_release_from_files(changed_files: List[str]) -> bool:
    normalized_files = _dedupe_keep_order(_normalize_repo_path(path) for path in changed_files)
    if not normalized_files:
        return False
    return all(_is_internal_release_only_file(path) for path in normalized_files)


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
    text = _clean_release_title(title)
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
        return CONVENTIONAL_TYPE_MAP.get(commit_type), _clean_release_title(conventional_match.group(3))

    chinese_match = re.match(r"^(功能|新增|实现|支持|修复|优化|调整|改进|完善|兼容|重构|重大变更|破坏性变更|文档|测试|工程)[：:]\s*(.+)$", text)
    if chinese_match:
        prefix = chinese_match.group(1)
        return CHINESE_TYPE_MAP.get(prefix), _clean_release_title(chinese_match.group(2))

    return None, _clean_release_title(text)


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


def _build_contextual_change_hint(category: str, title: str) -> str:
    subject = _clean_release_title(title)
    if not subject:
        return CATEGORY_CHANGE_HINTS[category]

    templates = {
        "前端": "前端：围绕“{subject}”更新界面交互与展示逻辑。",
        "后端": "后端：围绕“{subject}”更新接口与数据处理逻辑。",
        "测试": "测试：围绕“{subject}”补充并校验相关回归用例。",
        "工程": "工程：围绕“{subject}”更新脚本与自动化流程。",
        "文档": "文档：围绕“{subject}”同步说明与使用文档。",
        "资源": "资源：围绕“{subject}”同步内置资源与示例内容。",
    }
    return templates.get(category, CATEGORY_CHANGE_HINTS[category]).format(subject=subject)


def _has_specific_structured_changes(changes: List[str], title: str = "") -> bool:
    normalized_changes = _dedupe_keep_order(changes)
    if not normalized_changes:
        return False
    generic_values = set(CATEGORY_CHANGE_HINTS.values())
    clean_title = _clean_release_title(title)
    if len(normalized_changes) == 1 and clean_title and _normalize_text(normalized_changes[0]) == clean_title:
        return False
    return any(_normalize_text(change) not in generic_values for change in normalized_changes)


def _build_changes_from_files(changed_files: List[str], title: str = "") -> List[str]:
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
            bullets.append(_build_contextual_change_hint(category, title))

    return _dedupe_keep_order(bullets)


def _should_prefer_parsed_title(parsed_title: str, parsed_changes: List[str], prefer_diff_title: bool) -> bool:
    clean_title = _clean_release_title(parsed_title)
    if not _looks_like_clean_title(clean_title):
        return False
    if not prefer_diff_title:
        return True
    return len(clean_title) >= 8 or _has_specific_structured_changes(parsed_changes, clean_title)


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


def _infer_version_type_from_context(
    title: str,
    changes: List[str],
    changed_files: List[str],
    extra_text: str = "",
) -> str:
    if _should_skip_release_from_files(changed_files):
        return "skip"

    categories = set(_categorize_file(_normalize_repo_path(path)) for path in changed_files)
    combined_parts = [title, _normalize_text(extra_text)] + list(changes)
    combined_text = "\n".join(part for part in combined_parts if part)

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


def build_release_notes_from_context(
    message: str,
    changed_files: List[str],
    prefer_diff_title: bool = False,
    prefer_inferred_type: bool = False,
    prefer_diff_changes: bool = False,
) -> Tuple[str, str, List[str]]:
    """基于提交信息与改动文件生成结构化版本日志。"""
    parsed_type, parsed_title, parsed_changes = parse_commit_message(message)
    explicit_type, _ = _extract_commit_type_and_title(_normalize_text(message.splitlines()[0]) if message.strip() else "")
    parsed_title = _clean_release_title(parsed_title)
    parsed_has_specific_changes = _has_specific_structured_changes(parsed_changes, parsed_title)

    if _should_prefer_parsed_title(parsed_title, parsed_changes, prefer_diff_title):
        title = parsed_title
    else:
        title = _build_title_from_files(changed_files)

    if prefer_diff_changes:
        changes = parsed_changes if parsed_has_specific_changes else _build_changes_from_files(changed_files, title=title)
    elif _changes_need_diff_fallback(parsed_title, parsed_changes, changed_files):
        changes = _build_changes_from_files(changed_files, title=title)
    else:
        changes = parsed_changes

    if not changes:
        changes = [title] if title else []

    if _should_skip_release_from_files(changed_files):
        version_type = "skip"
    else:
        version_type = (
            _infer_version_type_from_context(title, changes, changed_files, extra_text=message)
            if prefer_inferred_type
            else explicit_type or _infer_version_type_from_context(title, changes, changed_files, extra_text=message)
        )
    return version_type, title, _dedupe_keep_order(changes)


def _sanitize_fragment_name(branch_name: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "-", _normalize_text(branch_name or ""))
    sanitized = re.sub(r"-{2,}", "-", sanitized).strip("-._")
    return sanitized or "detached-head"


def get_fragment_path(branch_name: str) -> Path:
    return UNRELEASED_DIR / f"{_sanitize_fragment_name(branch_name)}.json"


def build_release_fragment(branch_name: Optional[str] = None, base_ref: Optional[str] = None) -> Optional[Dict[str, object]]:
    """为当前分支构建唯一的变更碎片。"""
    resolved_branch = branch_name or get_current_branch()
    changed_files = get_branch_changed_files(base_ref)
    if not changed_files:
        return None

    commit_count = get_branch_commit_count(base_ref)
    context_message = get_branch_context_message(base_ref)
    version_type, title, changes = build_release_notes_from_context(
        context_message,
        changed_files,
        prefer_diff_title=commit_count > 1,
        prefer_inferred_type=commit_count > 1,
        prefer_diff_changes=commit_count > 1,
    )
    if version_type == "skip":
        return None

    return {
        "schemaVersion": FRAGMENT_SCHEMA_VERSION,
        "branch": resolved_branch,
        "baseRef": resolve_base_ref(base_ref),
        "sourceCommit": get_latest_commit_hash(),
        "committedAt": get_latest_commit_iso_datetime(),
        "versionType": version_type,
        "title": title,
        "changes": changes,
        "changedFiles": changed_files,
    }


def save_release_fragment(fragment: Dict[str, object], branch_name: Optional[str] = None) -> Path:
    """保存变更碎片。"""
    resolved_branch = branch_name or str(fragment.get("branch") or get_current_branch())
    fragment_path = get_fragment_path(resolved_branch)
    fragment_path.parent.mkdir(parents=True, exist_ok=True)
    with open(fragment_path, "w", encoding="utf-8") as handle:
        json.dump(fragment, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return fragment_path


def sync_release_fragment(branch_name: Optional[str] = None, base_ref: Optional[str] = None, dry_run: bool = False) -> bool:
    """同步当前分支的唯一变更碎片。"""
    resolved_branch = branch_name or get_current_branch()
    fragment = build_release_fragment(branch_name=resolved_branch, base_ref=base_ref)
    fragment_path = get_fragment_path(resolved_branch)

    if fragment is None:
        if fragment_path.exists() and not dry_run:
            fragment_path.unlink()
            print(f"已移除无需发布的变更碎片: {fragment_path.relative_to(PROJECT_ROOT)}")
        else:
            print("当前分支无须生成变更碎片")
        return False

    if dry_run:
        print("\n========== 变更碎片预览 ==========")
        print(f"分支: {resolved_branch}")
        print(f"碎片文件: {fragment_path.relative_to(PROJECT_ROOT)}")
        print(f"类型: {fragment['versionType']}")
        print(f"标题: {fragment['title']}")
        print("变更:")
        for change in fragment.get("changes", []):
            print(f"  - {change}")
        print("===============================\n")
        return True

    save_release_fragment(fragment, branch_name=resolved_branch)
    print(f"已更新变更碎片: {fragment_path.relative_to(PROJECT_ROOT)}")
    return True


def load_release_fragments() -> List[Tuple[Path, Dict[str, object]]]:
    """加载待发布的所有变更碎片。"""
    if not UNRELEASED_DIR.exists():
        return []

    fragments: List[Tuple[Path, Dict[str, object]]] = []
    for path in sorted(UNRELEASED_DIR.glob("*.json")):
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if not payload.get("title") or not payload.get("changes"):
            continue
        fragments.append((path, payload))

    fragments.sort(
        key=lambda item: (
            str(item[1].get("committedAt") or ""),
            str(item[1].get("branch") or ""),
            item[0].name,
        )
    )
    return fragments


def build_release_entries(current_version: str, fragments: List[Dict[str, object]]) -> Tuple[str, List[Dict[str, object]]]:
    """根据碎片顺序生成正式版本条目。"""
    next_version = current_version
    entries: List[Dict[str, object]] = []
    for fragment in fragments:
        version_type = str(fragment.get("versionType") or "patch")
        if version_type not in {"major", "minor", "patch"}:
            version_type = "patch"
        next_version = increment_version(next_version, version_type)
        committed_at = _normalize_text(str(fragment.get("committedAt") or ""))
        date_text = committed_at[:10] if committed_at else datetime.now().strftime("%Y-%m-%d")
        entries.append(
            {
                "version": next_version,
                "date": date_text,
                "type": version_type,
                "title": str(fragment.get("title") or f"版本 {next_version}"),
                "changes": _dedupe_keep_order(fragment.get("changes") or []),
            }
        )
    return next_version, entries


def release_from_fragments(dry_run: bool = False, consume: bool = True) -> bool:
    """聚合所有待发布碎片，生成正式 version.json。"""
    loaded_fragments = load_release_fragments()
    if not loaded_fragments:
        print("未找到待发布的变更碎片")
        return False

    data = load_version_data()
    current_version = data.get("version", "1.0.0")
    next_version, entries = build_release_entries(current_version, [payload for _, payload in loaded_fragments])
    if not entries:
        print("没有可写入的版本条目")
        return False

    if dry_run:
        print("\n========== 聚合发布预览 ==========")
        print(f"版本: {current_version} → {next_version}")
        print("碎片:")
        for path, payload in loaded_fragments:
            print(f"  - {path.relative_to(PROJECT_ROOT)} => {payload.get('title')}")
        print("正式条目:")
        for entry in entries:
            print(f"  - {entry['version']} [{entry['type']}] {entry['title']}")
        print("===============================\n")
        return True

    data["version"] = next_version
    data["releaseDate"] = entries[-1]["date"]
    if "changelog" not in data:
        data["changelog"] = []
    data["changelog"] = list(reversed(entries)) + list(data["changelog"])
    save_version_data(data)

    if consume:
        for path, _ in loaded_fragments:
            path.unlink(missing_ok=True)

    print(f"已聚合 {len(entries)} 个变更碎片，版本更新为 {next_version}")
    return True


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
    subparsers = parser.add_subparsers(dest="command")

    fragment_parser = subparsers.add_parser("fragment", help="根据当前分支累计改动更新变更碎片")
    fragment_parser.add_argument("--base-ref", help="指定比较基线（默认自动解析 origin/main/main）")
    fragment_parser.add_argument("--dry-run", "-n", action="store_true", help="预览变更碎片，不实际修改")

    release_parser = subparsers.add_parser("release", help="聚合变更碎片并更新正式 version.json")
    release_parser.add_argument("--dry-run", "-n", action="store_true", help="预览聚合结果，不实际修改")
    release_parser.add_argument("--keep-fragments", action="store_true", help="聚合后保留碎片文件")

    parser.add_argument("--type", "-t", choices=["major", "minor", "patch"], help="手动指定版本类型")
    parser.add_argument("--version", "-v", help="手动指定版本号 (如 2.0.0)")
    parser.add_argument("--title", help="版本标题")
    parser.add_argument("--changes", "-c", nargs="+", help="变更列表")
    parser.add_argument("--dry-run", "-n", action="store_true", help="预览变更，不实际修改")

    args = parser.parse_args()

    if args.command == "fragment":
        sync_release_fragment(base_ref=args.base_ref, dry_run=args.dry_run)
        sys.exit(0)

    if args.command == "release":
        release_from_fragments(dry_run=args.dry_run, consume=not args.keep_fragments)
        sys.exit(0)

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
