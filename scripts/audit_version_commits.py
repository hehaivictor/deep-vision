#!/usr/bin/env python3
"""
审计 Git 历史中的 version.json 重复提交模式。

输出内容：
1) 仅修改 web/version.json 的提交数量及占比
2) 同版本重复编辑（version 未变化）次数
3) 连续 version-only 提交对数量
"""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


PROJECT_ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = "web/version.json"


def run_git(args: List[str]) -> str:
    return subprocess.check_output(["git", *args], cwd=PROJECT_ROOT, text=True).strip()


def git_show_file(commit: str, path: str) -> Optional[str]:
    try:
        return run_git(["show", f"{commit}:{path}"])
    except subprocess.CalledProcessError:
        return None


@dataclass
class CommitRow:
    sha: str
    subject: str
    files: List[str]
    parent: Optional[str]


def collect_commits(limit: Optional[int]) -> List[CommitRow]:
    rev_list_args = ["rev-list", "--first-parent", "HEAD"]
    if limit is not None and limit > 0:
        rev_list_args.append(f"--max-count={limit}")

    commits = run_git(rev_list_args).splitlines()
    rows: List[CommitRow] = []

    for sha in commits:
        subject = run_git(["show", "-s", "--format=%s", sha])
        parent_line = run_git(["show", "-s", "--format=%P", sha])
        parent = parent_line.split()[0] if parent_line else None

        names = run_git(["show", "--name-only", "--pretty=format:", "--no-renames", sha]).splitlines()
        files = [name.strip() for name in names if name.strip()]

        rows.append(CommitRow(sha=sha, subject=subject, files=files, parent=parent))

    return rows


def parse_version(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    version = data.get("version")
    if version is None:
        return None
    return str(version).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="审计 version.json 重复提交")
    parser.add_argument("--limit", type=int, default=0, help="仅审计最近 N 条 first-parent 提交，0 表示全部")
    parser.add_argument("--sample", type=int, default=10, help="输出样例数量")
    args = parser.parse_args()

    limit = args.limit if args.limit > 0 else None
    rows = collect_commits(limit)

    version_only = [row for row in rows if row.files == [VERSION_FILE]]
    total = len(rows)
    version_only_count = len(version_only)
    ratio = (version_only_count / total * 100.0) if total else 0.0

    same_version_edits: List[CommitRow] = []
    for row in version_only:
        if not row.parent:
            continue
        cur_ver = parse_version(git_show_file(row.sha, VERSION_FILE))
        parent_ver = parse_version(git_show_file(row.parent, VERSION_FILE))
        if cur_ver and parent_ver and cur_ver == parent_ver:
            same_version_edits.append(row)

    consecutive_pairs = []
    for idx in range(len(rows) - 1):
        a = rows[idx]
        b = rows[idx + 1]
        if a.files == [VERSION_FILE] and b.files == [VERSION_FILE]:
            consecutive_pairs.append((a, b))

    print("========== version 提交审计 ==========")
    print(f"审计提交数(first-parent): {total}")
    print(f"仅修改 {VERSION_FILE} 提交: {version_only_count} ({ratio:.2f}%)")
    print(f"同版本重复编辑提交: {len(same_version_edits)}")
    print(f"连续 version-only 提交对: {len(consecutive_pairs)}")
    print("=====================================")

    sample = max(0, args.sample)
    if sample:
        print("\n[样例] 同版本重复编辑提交:")
        for row in same_version_edits[:sample]:
            print(f"- {row.sha[:8]} {row.subject}")

        print("\n[样例] 连续 version-only 提交对:")
        for a, b in consecutive_pairs[:sample]:
            print(f"- {a.sha[:8]} {a.subject}  ||  {b.sha[:8]} {b.subject}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
