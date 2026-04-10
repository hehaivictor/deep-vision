#!/usr/bin/env python3
"""
DeepVision harness Mission Contract 引用与生成辅助。
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parent.parent
MISSION_ARTIFACT_DIR = ROOT_DIR / "artifacts" / "planner" / "missions"
MISSION_TASK_INDEX_DIR = MISSION_ARTIFACT_DIR / "by-task"
MISSION_DOC_DIR = ROOT_DIR / "docs" / "agent" / "plans"

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts import agent_profiles


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _relative_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT_DIR))
    except Exception:
        return str(path.resolve())


def _slugify(text: str, *, fallback: str) -> str:
    normalized = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", str(text or "").strip(), flags=re.UNICODE)
    normalized = re.sub(r"-{2,}", "-", normalized).strip("-_")
    return normalized or fallback


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text:
            result.append(text)
    return result


def _task_pointer_path(task_name: str) -> Path:
    return MISSION_TASK_INDEX_DIR / str(task_name or "").strip() / "latest.json"


def write_task_latest_pointer(
    payload: dict[str, Any],
    *,
    markdown_path: Path,
    json_path: Path,
) -> dict[str, Any]:
    task_name = str(payload.get("task") or "").strip()
    if not task_name:
        raise ValueError("mission payload 缺少 task，无法写入 latest pointer")
    pointer_path = _task_pointer_path(task_name)
    pointer_path.parent.mkdir(parents=True, exist_ok=True)
    pointer_payload = {
        "kind": "mission_pointer",
        "generated_at": str(payload.get("generated_at") or "").strip(),
        "task": task_name,
        "mission_name": str(payload.get("mission_name") or "").strip(),
        "goal": str(payload.get("goal") or "").strip(),
        "summary": str(payload.get("summary") or "").strip(),
        "markdown_file": str(markdown_path.resolve()),
        "json_file": str(json_path.resolve()),
    }
    pointer_path.write_text(json.dumps(pointer_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "pointer_file": str(pointer_path.resolve()),
        "pointer_payload": pointer_payload,
    }


def load_task_latest_pointer(task_name: str) -> dict[str, Any] | None:
    pointer_path = _task_pointer_path(task_name)
    if not pointer_path.exists():
        return None
    try:
        payload = json.loads(pointer_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def build_mission_payload(
    profile: dict[str, Any],
    *,
    goal: str,
    context_lines: list[str],
    task_vars: dict[str, str],
    mission_name: str,
) -> dict[str, Any]:
    mission_meta = profile.get("mission") if isinstance(profile.get("mission"), dict) else {}
    planner_meta = profile.get("planner") if isinstance(profile.get("planner"), dict) else {}
    playbook = profile.get("playbook") if isinstance(profile.get("playbook"), dict) else {}

    desired_outcomes = _string_list(mission_meta.get("desired_outcomes"))
    if not desired_outcomes:
        desired_outcomes = _string_list(planner_meta.get("acceptance_focus"))

    acceptance = _string_list(mission_meta.get("acceptance_criteria"))
    if not acceptance:
        acceptance = _string_list(planner_meta.get("acceptance_focus"))

    non_goals = _string_list(mission_meta.get("non_goals"))
    if not non_goals:
        non_goals = _string_list(planner_meta.get("non_goals"))

    risks = _string_list(mission_meta.get("risks"))
    if not risks:
        risks = _string_list(planner_meta.get("risks")) or _string_list(playbook.get("manual_confirmations"))

    evidence = _string_list(mission_meta.get("evidence_expectations"))
    if not evidence:
        evidence = [
            "artifacts/harness-runs/latest.json",
            "artifacts/harness-runs/latest-progress.md",
            "artifacts/harness-runs/latest-handoff.json",
        ]

    return {
        "kind": "mission",
        "generated_at": utc_now_iso(),
        "mission_name": mission_name,
        "task": str(profile.get("name") or "").strip(),
        "task_source_file": str(profile.get("source_file") or "").strip(),
        "risk_level": str(profile.get("risk_level") or "medium").strip(),
        "goal": goal,
        "summary": str(mission_meta.get("summary") or planner_meta.get("summary") or profile.get("description") or "").strip(),
        "context": list(context_lines),
        "task_vars": dict(task_vars),
        "desired_outcomes": desired_outcomes,
        "acceptance_criteria": acceptance,
        "non_goals": non_goals or [
            "不要在 mission 阶段承诺底层实现细节。",
            "不要绕开既有 harness / workflow / evaluator 入口单独设计临时流程。",
        ],
        "risks": risks,
        "evidence_expectations": evidence,
        "docs": _string_list(profile.get("docs")),
        "planner_handoff": {
            "generate_plan_command": (
                f'python3 scripts/agent_planner.py --task {profile["name"]} --goal "{goal}" --artifact-dir artifacts/planner'
            ),
            "recommended_markdown": f"docs/agent/plans/{profile['name']}.md",
        },
    }


def render_mission_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# Mission Contract · {payload.get('mission_name', '')}",
        "",
        f"> 生成时间：{payload.get('generated_at', '')}",
        f"> 对应 task：`{payload.get('task', '')}` | risk=`{payload.get('risk_level', '')}`",
        f"> 来源画像：`{payload.get('task_source_file', '')}`",
        "",
        "## 任务使命",
        "",
        str(payload.get("goal") or "").strip(),
        "",
    ]

    summary = str(payload.get("summary") or "").strip()
    if summary:
        lines.extend(["## 使命摘要", "", summary, ""])

    context = _string_list(payload.get("context"))
    lines.extend(["## 已知上下文", ""])
    if context:
        lines.extend([f"- {item}" for item in context])
    else:
        lines.append("- 暂无额外上下文；建议先补业务背景、影响范围和用户可见现象。")
    lines.append("")

    lines.extend(["## 期望结果", ""])
    lines.extend([f"- {item}" for item in _string_list(payload.get("desired_outcomes"))] or ["- 先补期望结果。"])
    lines.append("")

    lines.extend(["## 验收标准", ""])
    lines.extend([f"- {item}" for item in _string_list(payload.get("acceptance_criteria"))] or ["- 先补验收标准。"])
    lines.append("")

    lines.extend(["## 非目标", ""])
    lines.extend([f"- {item}" for item in _string_list(payload.get("non_goals"))] or ["- 暂无。"])
    lines.append("")

    lines.extend(["## 风险与边界", ""])
    lines.extend([f"- {item}" for item in _string_list(payload.get("risks"))] or ["- 暂无。"])
    lines.append("")

    lines.extend(["## 证据要求", ""])
    lines.extend([f"- `{item}`" for item in _string_list(payload.get("evidence_expectations"))] or ["- 暂无。"])
    lines.append("")

    task_vars = payload.get("task_vars", {}) if isinstance(payload.get("task_vars"), dict) else {}
    if task_vars:
        lines.extend(["## 任务变量", ""])
        for key in sorted(task_vars):
            lines.append(f"- `{key}` = `{task_vars[key]}`")
        lines.append("")

    handoff = payload.get("planner_handoff", {}) if isinstance(payload.get("planner_handoff"), dict) else {}
    lines.extend(["## 下一步", ""])
    command = str(handoff.get("generate_plan_command") or "").strip()
    if command:
        lines.append("```bash")
        lines.append(command)
        lines.append("```")
    recommended_markdown = str(handoff.get("recommended_markdown") or "").strip()
    if recommended_markdown:
        lines.append(f"- 推荐长期计划文档：`{recommended_markdown}`")
    return "\n".join(lines).rstrip() + "\n"


def get_mission_for_profile(profile: dict[str, Any]) -> dict[str, Any] | None:
    mission_meta = profile.get("mission") if isinstance(profile.get("mission"), dict) else None
    if not mission_meta:
        return None

    task_name = str(profile.get("name") or "").strip()
    if not task_name:
        return None

    latest_pointer = load_task_latest_pointer(task_name)
    recommended_markdown = MISSION_DOC_DIR / f"{task_name}-mission.md"
    generate_command = (
        f'python3 scripts/agent_planner.py --task {task_name} --goal "<补充目标>" --artifact-dir artifacts/planner'
    )

    docs = [
        "docs/agent/plans/README.md",
        *[str(item).strip() for item in list(profile.get("docs", []) or []) if str(item).strip()],
    ]

    source_file = _relative_path(recommended_markdown)
    markdown_file = ""
    json_file = ""
    mission_name = ""
    goal = ""
    generated_at = ""
    status = "recommended"
    if latest_pointer:
        markdown_file = str(latest_pointer.get("markdown_file") or "").strip()
        json_file = str(latest_pointer.get("json_file") or "").strip()
        mission_name = str(latest_pointer.get("mission_name") or "").strip()
        goal = str(latest_pointer.get("goal") or "").strip()
        generated_at = str(latest_pointer.get("generated_at") or "").strip()
        source_file = json_file or markdown_file or source_file
        status = "materialized"
        if markdown_file:
            docs.append(_relative_path(Path(markdown_file)))
        if json_file:
            docs.append(_relative_path(Path(json_file)))

    unique_docs: list[str] = []
    for item in docs:
        text = str(item or "").strip()
        if text and text not in unique_docs:
            unique_docs.append(text)

    return {
        "task": task_name,
        "title": f"Mission Contract · {task_name}",
        "summary": str(mission_meta.get("summary") or profile.get("description") or "").strip(),
        "status": status,
        "mission_name": mission_name,
        "goal": goal,
        "generated_at": generated_at,
        "source_file": source_file,
        "markdown_file": markdown_file,
        "json_file": json_file,
        "recommended_markdown": _relative_path(recommended_markdown),
        "generate_command": generate_command,
        "docs": unique_docs,
        "task_source_file": str(profile.get("source_file") or "").strip(),
    }


def get_mission(task_name: str) -> dict[str, Any] | None:
    return get_mission_for_profile(agent_profiles.get_task_profile(task_name))
