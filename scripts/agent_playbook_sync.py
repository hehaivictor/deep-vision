#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
DeepVision task-backed playbook 同步脚本。

目标：
1. 把 task profile 与对应 playbook 文档收敛到同一份结构化元数据
2. 让高频任务的执行面和文档面保持同步，减少双份维护
3. 提供 --check 模式，便于本地与 CI 发现文档漂移
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts import agent_profiles


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text:
            items.append(text)
    return items


def _markdown_bullets(items: list[str]) -> list[str]:
    return [f"- {item}" for item in items]


def _fenced_commands(commands: list[str]) -> list[str]:
    lines = ["```bash"]
    lines.extend(commands)
    lines.append("```")
    return lines


def _normalize_output_path(raw_value: Any, *, profile: dict[str, Any]) -> Path:
    playbook_meta = profile.get("playbook", {}) if isinstance(profile.get("playbook"), dict) else {}
    output_value = str(playbook_meta.get("output") or raw_value or "").strip()
    if not output_value:
        output_value = f"docs/agent/playbooks/{profile['name']}.md"
    path = Path(output_value)
    if not path.is_absolute():
        path = (ROOT_DIR / path).resolve()
    return path


def render_playbook_markdown(profile: dict[str, Any]) -> tuple[Path, str]:
    playbook_meta = profile.get("playbook", {}) if isinstance(profile.get("playbook"), dict) else {}
    if not playbook_meta:
        raise ValueError(f"task {profile.get('name', '')} 缺少 playbook 元数据")

    title = str(playbook_meta.get("title") or profile.get("name") or "").strip()
    if not title:
        raise ValueError("playbook title 不能为空")
    output_path = _normalize_output_path(playbook_meta.get("output"), profile=profile)

    when_to_use = _string_list(playbook_meta.get("when_to_use"))
    artifact_files = _string_list(playbook_meta.get("artifact_files"))
    focus_points = _string_list(playbook_meta.get("focus_points"))
    manual_confirmations = _string_list(playbook_meta.get("manual_confirmations"))
    docs = _string_list(profile.get("docs"))
    command_blocks = list(playbook_meta.get("command_blocks", []) or [])

    lines = [
        f"# {title}",
        "",
        "> 本文件由 `python3 scripts/agent_playbook_sync.py` 基于 task 画像自动生成。",
        f"> 关联任务画像：`{profile.get('name', '')}` | 来源：`{profile.get('source_file', '')}`",
        "",
    ]

    summary = str(playbook_meta.get("summary") or "").strip()
    if summary:
        lines.extend([summary, ""])

    lines.extend(["## 什么时候用", ""])
    if when_to_use:
        lines.extend(_markdown_bullets(when_to_use))
    else:
        lines.append(f"- 处理 `{profile.get('name', '')}` 相关高频任务时使用。")

    lines.extend(["", "## 先跑哪些命令", ""])
    if not command_blocks:
        lines.extend(_fenced_commands([f"python3 scripts/agent_harness.py --task {profile.get('name', '')} --profile auto"]))
    else:
        for index, block in enumerate(command_blocks):
            if index > 0:
                lines.append("")
            if isinstance(block, dict):
                intro = str(block.get("intro") or "").strip()
                commands = _string_list(block.get("commands"))
            else:
                intro = ""
                commands = []
            if intro:
                lines.append(intro)
                lines.append("")
            if commands:
                lines.extend(_fenced_commands(commands))

    lines.extend(["", "## 看哪些 artifact", ""])
    if artifact_files:
        lines.extend(_markdown_bullets([f"`{item}`" for item in artifact_files]))
    else:
        lines.append(f"- `artifacts/harness-runs/latest.json`")

    if focus_points:
        lines.extend(["", "重点看：", ""])
        lines.extend(_markdown_bullets(focus_points))

    lines.extend(["", "## 哪些操作必须人工确认", ""])
    if manual_confirmations:
        lines.extend(_markdown_bullets(manual_confirmations))
    else:
        lines.append("- 所有会产生持久化写入、数据迁移或回滚的动作。")

    if docs:
        lines.extend(["", "## 相关文档", ""])
        lines.extend(_markdown_bullets([f"`{item}`" for item in docs]))

    content = "\n".join(lines).rstrip() + "\n"
    return output_path, content


def iter_task_playbooks(task_names: list[str] | None = None) -> list[tuple[str, Path, str]]:
    selected = set(task_names or [])
    rendered: list[tuple[str, Path, str]] = []
    for name in agent_profiles.list_task_names():
        if selected and name not in selected:
            continue
        profile = agent_profiles.get_task_profile(name)
        playbook_meta = profile.get("playbook", {}) if isinstance(profile.get("playbook"), dict) else {}
        if not playbook_meta:
            continue
        output_path, content = render_playbook_markdown(profile)
        rendered.append((name, output_path, content))
    return rendered


def write_task_playbooks(task_names: list[str] | None = None) -> list[Path]:
    written: list[Path] = []
    for _name, output_path, content in iter_task_playbooks(task_names):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content, encoding="utf-8")
        written.append(output_path)
    return written


def check_task_playbooks(task_names: list[str] | None = None) -> list[str]:
    mismatches: list[str] = []
    for name, output_path, content in iter_task_playbooks(task_names):
        if not output_path.exists():
            mismatches.append(f"{name}: 缺少 playbook 文件 {output_path}")
            continue
        current = output_path.read_text(encoding="utf-8")
        if current != content:
            mismatches.append(f"{name}: playbook 内容已漂移 {output_path}")
    return mismatches


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="同步 DeepVision task-backed playbook 文档")
    parser.add_argument("--task", action="append", dest="tasks", help="仅同步指定 task，可多次传入")
    parser.add_argument("--check", action="store_true", help="仅检查 playbook 是否与 task profile 保持同步")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    task_names = list(args.tasks or [])
    if args.check:
        mismatches = check_task_playbooks(task_names)
        if mismatches:
            print("DeepVision agent playbook check")
            for item in mismatches:
                print(f"[DRIFT] {item}")
            return 2
        print("DeepVision agent playbook check")
        print("[OK] task-backed playbook 均已同步")
        return 0

    written = write_task_playbooks(task_names)
    print("DeepVision agent playbook sync")
    for path in written:
        print(f"[WRITE] {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
