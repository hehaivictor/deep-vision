#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
DeepVision harness Planner artifact 生成器。

目标：
1. 把简短需求收口成结构化计划工件，而不是直接跳进 task workflow
2. 复用 task profile、playbook 与 workflow 元数据，减少重复维护
3. 同时输出 markdown 与 json，便于人类阅读和后续程序继续消费
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts import agent_profiles
from scripts import agent_missions
from scripts import agent_plans


DEFAULT_ARTIFACT_DIR = ROOT_DIR / "artifacts" / "planner"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text:
            items.append(text)
    return items


def _slugify(text: str, *, fallback: str) -> str:
    normalized = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", str(text or "").strip(), flags=re.UNICODE)
    normalized = re.sub(r"-{2,}", "-", normalized).strip("-_")
    return normalized or fallback


def _resolve_output_dir(value: str) -> Path:
    path = Path(str(value or "").strip() or str(DEFAULT_ARTIFACT_DIR)).expanduser()
    if not path.is_absolute():
        path = (ROOT_DIR / path).resolve()
    return path


def _task_command(task_name: str, *, task_vars: dict[str, str], workflow_execute: str | None = None, observe: bool = False) -> str:
    command = ["python3", "scripts/agent_harness.py", "--task", task_name]
    if observe:
        command.append("--observe")
    if workflow_execute:
        command.extend(["--workflow-execute", workflow_execute])
    for key in sorted(task_vars):
        command.extend(["--task-var", f"{key}={task_vars[key]}"])
    if not workflow_execute:
        command.extend(["--profile", "auto", "--artifact-dir", "artifacts/harness-runs"])
    return " ".join(command)


def _workflow_command(task_name: str, *, task_vars: dict[str, str], execute_mode: str) -> str:
    command = ["python3", "scripts/agent_workflow.py", "--task", task_name, "--execute", execute_mode]
    for key in sorted(task_vars):
        command.extend(["--task-var", f"{key}={task_vars[key]}"])
    return " ".join(command)


def _derive_scope_focus(profile: dict[str, Any], planner_meta: dict[str, Any]) -> list[str]:
    scope_focus = _string_list(planner_meta.get("scope_focus"))
    if scope_focus:
        return scope_focus

    focus_points = _string_list((profile.get("playbook") or {}).get("focus_points"))
    if focus_points:
        return focus_points[:5]

    steps = []
    for item in list((profile.get("workflow") or {}).get("steps", []) or []):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if title:
            steps.append(title)
    return steps[:5]


def _derive_acceptance(profile: dict[str, Any], planner_meta: dict[str, Any]) -> list[str]:
    acceptance = _string_list(planner_meta.get("acceptance_focus"))
    if acceptance:
        return acceptance

    derived: list[str] = []
    workflow = profile.get("workflow") if isinstance(profile.get("workflow"), dict) else {}
    for item in list(workflow.get("steps", []) or []):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if title:
            derived.append(f"完成“{title}”对应的验证与证据留存。")
    for focus in _string_list((profile.get("playbook") or {}).get("focus_points"))[:3]:
        derived.append(f"验证重点：{focus}")
    return derived[:6]


def build_plan_payload(
    profile: dict[str, Any],
    *,
    goal: str,
    context_lines: list[str],
    task_vars: dict[str, str],
    plan_name: str,
    mission_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    planner_meta = profile.get("planner", {}) if isinstance(profile.get("planner"), dict) else {}
    docs = _string_list(profile.get("docs"))
    playbook = profile.get("playbook", {}) if isinstance(profile.get("playbook"), dict) else {}
    summary = str(planner_meta.get("summary") or profile.get("description") or "").strip()
    recommended_commands = _string_list(planner_meta.get("recommended_commands"))
    if not recommended_commands:
        recommended_commands = [
            _workflow_command(profile["name"], task_vars=task_vars, execute_mode="plan"),
            _task_command(profile["name"], task_vars=task_vars, observe=True),
            _task_command(profile["name"], task_vars=task_vars, workflow_execute="preview"),
        ]

    return {
        "kind": "planner",
        "generated_at": utc_now_iso(),
        "plan_name": plan_name,
        "task": profile["name"],
        "task_source_file": str(profile.get("source_file") or "").strip(),
        "risk_level": str(profile.get("risk_level") or "medium").strip(),
        "workflow_mode": str((profile.get("workflow") or {}).get("mode") or "preview_first").strip(),
        "goal": goal,
        "summary": summary,
        "context": list(context_lines),
        "task_vars": dict(task_vars),
        "mission": mission_payload,
        "scope_focus": _derive_scope_focus(profile, planner_meta),
        "acceptance_focus": _derive_acceptance(profile, planner_meta),
        "non_goals": _string_list(planner_meta.get("non_goals")) or [
            "不要在 Planner 阶段承诺具体底层实现细节。",
            "不要绕开现有 harness / task workflow 直接定义一次性验证路径。",
        ],
        "risks": _string_list(planner_meta.get("risks")) or _string_list(playbook.get("manual_confirmations")),
        "open_questions": _string_list(planner_meta.get("open_questions")),
        "docs": docs,
        "recommended_commands": recommended_commands,
        "artifact_targets": [
            "artifacts/harness-runs/latest.json",
            "artifacts/harness-runs/latest-progress.md",
            "artifacts/harness-runs/latest-handoff.json",
        ],
    }


def render_plan_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# Planner Artifact · {payload.get('plan_name', '')}",
        "",
        f"> 生成时间：{payload.get('generated_at', '')}",
        f"> 对应 task：`{payload.get('task', '')}` | risk=`{payload.get('risk_level', '')}` | workflow=`{payload.get('workflow_mode', '')}`",
        f"> 来源画像：`{payload.get('task_source_file', '')}`",
        "",
        "## 目标",
        "",
        str(payload.get("goal") or "").strip(),
        "",
    ]

    summary = str(payload.get("summary") or "").strip()
    if summary:
        lines.extend(["## 规划摘要", "", summary, ""])

    mission_payload = payload.get("mission") if isinstance(payload.get("mission"), dict) else None
    if mission_payload:
        lines.extend(
            [
                "## 上游 Mission",
                "",
                f"- Mission 状态：`materialized`",
                f"- Mission 目标：{str(mission_payload.get('goal') or '').strip()}",
                f"- Mission 入口：`{str(mission_payload.get('json_file') or mission_payload.get('markdown_file') or '-').strip() or '-'}`",
                "",
            ]
        )

    context = _string_list(payload.get("context"))
    lines.extend(["## 初始上下文", ""])
    if context:
        lines.extend([f"- {item}" for item in context])
    else:
        lines.append("- 暂无额外上下文；建议先补业务背景、影响范围和已有异常表现。")
    lines.append("")

    lines.extend(["## 本次范围", ""])
    lines.extend([f"- {item}" for item in _string_list(payload.get("scope_focus"))] or ["- 先补范围说明。"])
    lines.append("")

    lines.extend(["## 完成定义", ""])
    lines.extend([f"- {item}" for item in _string_list(payload.get("acceptance_focus"))] or ["- 先补完成标准。"])
    lines.append("")

    lines.extend(["## 非目标", ""])
    lines.extend([f"- {item}" for item in _string_list(payload.get("non_goals"))] or ["- 暂无。"])
    lines.append("")

    lines.extend(["## 风险与边界", ""])
    lines.extend([f"- {item}" for item in _string_list(payload.get("risks"))] or ["- 暂无。"])
    lines.append("")

    open_questions = _string_list(payload.get("open_questions"))
    if open_questions:
        lines.extend(["## 待澄清问题", ""])
        lines.extend([f"- {item}" for item in open_questions])
        lines.append("")

    docs = _string_list(payload.get("docs"))
    if docs:
        lines.extend(["## 相关文档", ""])
        lines.extend([f"- `{item}`" for item in docs])
        lines.append("")

    task_vars = payload.get("task_vars", {}) if isinstance(payload.get("task_vars"), dict) else {}
    if task_vars:
        lines.extend(["## 任务变量", ""])
        for key in sorted(task_vars):
            lines.append(f"- `{key}` = `{task_vars[key]}`")
        lines.append("")

    lines.extend(["## 推荐执行顺序", ""])
    lines.append("```bash")
    for command in _string_list(payload.get("recommended_commands")):
        lines.append(command)
    lines.append("```")
    lines.append("")

    lines.extend(["## 关键证据入口", ""])
    lines.extend([f"- `{item}`" for item in _string_list(payload.get("artifact_targets"))])
    lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_plan_artifact(
    payload: dict[str, Any],
    *,
    output_dir: str,
    output_markdown: str = "",
    mission_output_markdown: str = "",
) -> dict[str, str]:
    mission_outputs: dict[str, str] = {}
    mission_payload = payload.get("mission") if isinstance(payload.get("mission"), dict) else None
    if mission_payload:
        if mission_output_markdown:
            mission_markdown_path = Path(mission_output_markdown).expanduser()
            if not mission_markdown_path.is_absolute():
                mission_markdown_path = (ROOT_DIR / mission_markdown_path).resolve()
            mission_markdown_path.parent.mkdir(parents=True, exist_ok=True)
        elif output_markdown:
            plan_markdown_path = Path(output_markdown).expanduser()
            if not plan_markdown_path.is_absolute():
                plan_markdown_path = (ROOT_DIR / plan_markdown_path).resolve()
            mission_markdown_path = plan_markdown_path.with_name(plan_markdown_path.stem + ".mission.md")
            mission_markdown_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            mission_target_dir = _resolve_output_dir(output_dir)
            mission_target_dir.mkdir(parents=True, exist_ok=True)
            mission_markdown_path = mission_target_dir / f"{payload['plan_name']}.mission.md"
        mission_json_path = mission_markdown_path.with_suffix(".json")
        mission_markdown_path.write_text(agent_missions.render_mission_markdown(mission_payload), encoding="utf-8")
        mission_json_path.write_text(json.dumps(mission_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        pointer_info = agent_missions.write_task_latest_pointer(
            mission_payload,
            markdown_path=mission_markdown_path,
            json_path=mission_json_path,
        )
        mission_payload["markdown_file"] = str(mission_markdown_path.resolve())
        mission_payload["json_file"] = str(mission_json_path.resolve())
        mission_payload["pointer_file"] = str(pointer_info["pointer_file"])
        mission_outputs = {
            "mission_markdown_file": str(mission_markdown_path),
            "mission_json_file": str(mission_json_path),
            "mission_pointer_file": str(pointer_info["pointer_file"]),
        }

    if output_markdown:
        markdown_path = Path(output_markdown).expanduser()
        if not markdown_path.is_absolute():
            markdown_path = (ROOT_DIR / markdown_path).resolve()
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        target_dir = _resolve_output_dir(output_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        markdown_path = target_dir / f"{payload['plan_name']}.md"

    json_path = markdown_path.with_suffix(".json")
    markdown_path.write_text(render_plan_markdown(payload), encoding="utf-8")
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pointer_info = agent_plans.write_task_latest_pointer(
        payload,
        markdown_path=markdown_path,
        json_path=json_path,
    )
    return {
        "markdown_file": str(markdown_path),
        "json_file": str(json_path),
        "pointer_file": str(pointer_info["pointer_file"]),
        **mission_outputs,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="生成 DeepVision harness Planner artifact")
    parser.add_argument("--task", required=True, choices=agent_profiles.list_task_names(), help="选择任务画像")
    parser.add_argument("--goal", required=True, help="用一句话描述本次要解决的问题或目标")
    parser.add_argument("--context-line", action="append", default=[], help="补充上下文，每次传入一行")
    parser.add_argument("--task-var", action="append", default=[], help="任务变量，格式 key=value，可重复传入")
    parser.add_argument("--plan-name", default="", help="显式指定计划名；默认按 task + goal 生成")
    parser.add_argument("--mission-name", default="", help="显式指定 mission 名；默认按 plan-name 派生")
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR.relative_to(ROOT_DIR)), help="默认输出目录")
    parser.add_argument("--output-markdown", default="", help="显式指定 markdown 输出路径；会同时写同名 json")
    parser.add_argument("--output-mission-markdown", default="", help="显式指定 mission markdown 输出路径；会同时写同名 json")
    parser.add_argument("--dry-run", action="store_true", help="仅打印 markdown，不写文件")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    profile = agent_profiles.get_task_profile(args.task)
    task_vars = agent_profiles.parse_task_vars(list(args.task_var or []))
    fallback_name = f"{args.task}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    default_name = f"{args.task}-{args.goal}"
    plan_name = _slugify(args.plan_name or default_name, fallback=fallback_name)
    mission_name = _slugify(args.mission_name or f"{plan_name}-mission", fallback=f"{fallback_name}-mission")
    mission_payload = agent_missions.build_mission_payload(
        profile,
        goal=str(args.goal).strip(),
        context_lines=[str(item).strip() for item in list(args.context_line or []) if str(item).strip()],
        task_vars=task_vars,
        mission_name=mission_name,
    )
    payload = build_plan_payload(
        profile,
        goal=str(args.goal).strip(),
        context_lines=[str(item).strip() for item in list(args.context_line or []) if str(item).strip()],
        task_vars=task_vars,
        plan_name=plan_name,
        mission_payload=mission_payload,
    )
    if args.dry_run:
        print(agent_missions.render_mission_markdown(mission_payload))
        print("")
        print(render_plan_markdown(payload))
        return 0

    outputs = write_plan_artifact(
        payload,
        output_dir=args.artifact_dir,
        output_markdown=args.output_markdown,
        mission_output_markdown=args.output_mission_markdown,
    )
    print("DeepVision agent planner")
    if outputs.get("mission_markdown_file"):
        print(f"[WRITE] {outputs['mission_markdown_file']}")
    if outputs.get("mission_json_file"):
        print(f"[WRITE] {outputs['mission_json_file']}")
    if outputs.get("mission_pointer_file"):
        print(f"[WRITE] {outputs['mission_pointer_file']}")
    print(f"[WRITE] {outputs['markdown_file']}")
    print(f"[WRITE] {outputs['json_file']}")
    print(f"[WRITE] {outputs['pointer_file']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
