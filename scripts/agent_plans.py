#!/usr/bin/env python3
"""
DeepVision harness Planner artifact 引用辅助。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parent.parent
PLANNER_ARTIFACT_DIR = ROOT_DIR / "artifacts" / "planner"
PLANNER_TASK_INDEX_DIR = PLANNER_ARTIFACT_DIR / "by-task"
PLANS_DOC_DIR = ROOT_DIR / "docs" / "agent" / "plans"

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts import agent_profiles


def _relative_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT_DIR))
    except Exception:
        return str(path.resolve())


def _task_pointer_path(task_name: str) -> Path:
    return PLANNER_TASK_INDEX_DIR / str(task_name or "").strip() / "latest.json"


def write_task_latest_pointer(
    payload: dict[str, Any],
    *,
    markdown_path: Path,
    json_path: Path,
) -> dict[str, Any]:
    task_name = str(payload.get("task") or "").strip()
    if not task_name:
        raise ValueError("planner payload 缺少 task，无法写入 latest pointer")
    pointer_path = _task_pointer_path(task_name)
    pointer_path.parent.mkdir(parents=True, exist_ok=True)
    pointer_payload = {
        "kind": "planner_pointer",
        "generated_at": str(payload.get("generated_at") or "").strip(),
        "task": task_name,
        "plan_name": str(payload.get("plan_name") or "").strip(),
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


def get_plan_for_profile(profile: dict[str, Any]) -> dict[str, Any] | None:
    planner_meta = profile.get("planner") if isinstance(profile.get("planner"), dict) else None
    if not planner_meta:
        return None

    task_name = str(profile.get("name") or "").strip()
    if not task_name:
        return None

    latest_pointer = load_task_latest_pointer(task_name)
    recommended_markdown = PLANS_DOC_DIR / f"{task_name}.md"
    generate_command = (
        f'python3 scripts/agent_planner.py --task {task_name} --goal "<补充目标>" --artifact-dir artifacts/planner'
    )
    publish_command = (
        f'python3 scripts/agent_planner.py --task {task_name} --goal "<补充目标>" '
        f'--output-markdown docs/agent/plans/{task_name}.md'
    )

    docs = [
        "docs/agent/plans/README.md",
        *[
            str(item).strip()
            for item in list(profile.get("docs", []) or [])
            if str(item).strip()
        ],
    ]

    source_file = _relative_path(recommended_markdown)
    markdown_file = ""
    json_file = ""
    plan_name = ""
    goal = ""
    generated_at = ""
    status = "recommended"
    if latest_pointer:
        markdown_file = str(latest_pointer.get("markdown_file") or "").strip()
        json_file = str(latest_pointer.get("json_file") or "").strip()
        plan_name = str(latest_pointer.get("plan_name") or "").strip()
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
        "title": f"Planner Artifact · {task_name}",
        "summary": str(planner_meta.get("summary") or profile.get("description") or "").strip(),
        "status": status,
        "plan_name": plan_name,
        "goal": goal,
        "generated_at": generated_at,
        "source_file": source_file,
        "markdown_file": markdown_file,
        "json_file": json_file,
        "recommended_markdown": _relative_path(recommended_markdown),
        "generate_command": generate_command,
        "publish_command": publish_command,
        "docs": unique_docs,
        "task_source_file": str(profile.get("source_file") or "").strip(),
    }


def get_plan(task_name: str) -> dict[str, Any] | None:
    return get_plan_for_profile(agent_profiles.get_task_profile(task_name))
