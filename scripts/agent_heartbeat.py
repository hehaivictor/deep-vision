#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
DeepVision harness 全局 heartbeat / memory 指针生成器。
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
DEFAULT_MARKDOWN_PATH = ROOT_DIR / "docs" / "agent" / "heartbeat.md"
DEFAULT_ARTIFACT_DIR = ROOT_DIR / "artifacts" / "memory"

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts import agent_profiles


PHASE_FILES = (
    ("phase5", "docs/agent/harness-progress-phase5.md", "docs/agent/harness-iteration-plan-phase5.md"),
    ("phase4", "docs/agent/harness-progress-phase4.md", "docs/agent/harness-iteration-plan-phase4.md"),
    ("phase3", "docs/agent/harness-progress-phase3.md", "docs/agent/harness-iteration-plan-phase3.md"),
    ("phase2", "docs/agent/harness-progress.md", "docs/agent/harness-iteration-plan.md"),
)
RUN_POINTERS = (
    ("harness", "artifacts/harness-runs/latest.json"),
    ("evaluator", "artifacts/harness-eval/latest.json"),
    ("ci-agent-smoke", "artifacts/ci/agent-smoke/latest.json"),
    ("ci-guardrails", "artifacts/ci/guardrails/latest.json"),
    ("ci-browser-smoke", "artifacts/ci/browser-smoke/latest.json"),
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _relative_path(root_dir: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(root_dir.resolve()))
    except Exception:
        return str(path.resolve())


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _parse_progress_snapshot(progress_path: Path) -> dict[str, Any] | None:
    if not progress_path.exists():
        return None
    text = progress_path.read_text(encoding="utf-8")
    current_stage_match = re.search(r"- 当前阶段：`([^`]+)`", text)
    current_priority_match = re.search(r"- 当前优先项：`([^`]+)`", text)
    latest_row = ""
    for line in text.splitlines():
        if (
            line.startswith("| ")
            and not line.startswith("| ---")
            and "YYYY-MM-DD" not in line
            and "| 日期 |" not in line
        ):
            latest_row = line
    return {
        "current_stage": current_stage_match.group(1).strip() if current_stage_match else "",
        "current_priority": current_priority_match.group(1).strip() if current_priority_match else "",
        "latest_row": latest_row,
    }


def _collect_phase_status(root_dir: Path) -> dict[str, Any]:
    phases: list[dict[str, Any]] = []
    active_phase: dict[str, Any] | None = None
    for phase_name, progress_rel, plan_rel in PHASE_FILES:
        progress_path = root_dir / progress_rel
        plan_path = root_dir / plan_rel
        snapshot = _parse_progress_snapshot(progress_path)
        if not snapshot:
            continue
        payload = {
            "name": phase_name,
            "progress_file": _relative_path(root_dir, progress_path),
            "plan_file": _relative_path(root_dir, plan_path),
            "current_stage": snapshot.get("current_stage", ""),
            "current_priority": snapshot.get("current_priority", ""),
            "latest_row": snapshot.get("latest_row", ""),
        }
        phases.append(payload)
        if active_phase is None and payload["current_stage"] == "active":
            active_phase = payload
    if active_phase is None and phases:
        active_phase = phases[0]
    return {
        "active_phase": active_phase or {},
        "phases": phases,
    }


def _collect_task_pointers(root_dir: Path, rel_dir: str, *, key_name: str) -> list[dict[str, Any]]:
    base_dir = root_dir / rel_dir
    results: list[dict[str, Any]] = []
    if not base_dir.exists():
        return results
    for pointer_path in sorted(base_dir.glob("*/latest.json")):
        payload = _load_json(pointer_path)
        if not payload:
            continue
        entry = {
            "task": str(payload.get("task") or "").strip(),
            "generated_at": str(payload.get("generated_at") or "").strip(),
            "source_file": _relative_path(root_dir, pointer_path),
            "goal": str(payload.get("goal") or "").strip(),
            key_name: str(payload.get(key_name) or "").strip(),
            "markdown_file": str(payload.get("markdown_file") or "").strip(),
            "json_file": str(payload.get("json_file") or "").strip(),
        }
        if entry["task"]:
            results.append(entry)
    results.sort(key=lambda item: (str(item.get("generated_at") or ""), str(item.get("task") or "")), reverse=True)
    return results


def _collect_run_pointers(root_dir: Path) -> list[dict[str, Any]]:
    pointers: list[dict[str, Any]] = []
    for kind, rel_path in RUN_POINTERS:
        latest_path = root_dir / rel_path
        payload = _load_json(latest_path)
        if not payload:
            continue
        pointers.append(
            {
                "kind": kind,
                "latest_json": _relative_path(root_dir, latest_path),
                "overall": str(payload.get("overall") or "").strip(),
                "generated_at": str((payload.get("metadata") or {}).get("generated_at") or payload.get("generated_at") or "").strip(),
                "handoff_file": str(payload.get("handoff_file") or "").strip(),
                "progress_file": str(payload.get("progress_file") or "").strip(),
            }
        )
    return pointers


def build_heartbeat_payload(*, root_dir: Path = ROOT_DIR) -> dict[str, Any]:
    phase_status = _collect_phase_status(root_dir)
    mission_pointers = _collect_task_pointers(
        root_dir,
        "artifacts/planner/missions/by-task",
        key_name="mission_name",
    )
    plan_pointers = _collect_task_pointers(
        root_dir,
        "artifacts/planner/by-task",
        key_name="plan_name",
    )
    run_pointers = _collect_run_pointers(root_dir)
    scenario_count = len(list((root_dir / "tests" / "harness_scenarios").glob("**/*.json")))

    return {
        "kind": "heartbeat",
        "generated_at": utc_now_iso(),
        "active_phase": phase_status.get("active_phase", {}),
        "phase_index": phase_status.get("phases", []),
        "stable_entrypoints": {
            "docs": [
                "AGENTS.md",
                "ARCHITECTURE.md",
                "docs/agent/README.md",
                "docs/agent/heartbeat.md",
            ],
            "commands": [
                "python3 scripts/agent_harness.py --profile auto",
                "python3 scripts/agent_observe.py --profile auto",
                "python3 scripts/agent_history.py --kind harness --diff",
                "python3 scripts/agent_heartbeat.py",
            ],
        },
        "capabilities": {
            "task_count": len(agent_profiles.list_task_names()),
            "scenario_count": scenario_count,
            "browser_suites": ["minimal", "extended", "live-minimal", "live-extended"],
        },
        "missions": mission_pointers[:6],
        "plans": plan_pointers[:6],
        "latest_runs": run_pointers,
        "notes": [
            "先看 heartbeat，再决定进入哪个阶段计划、mission/plan 或运行工件。",
            "入口文档只做导航，阶段状态和稳定入口以 heartbeat 为准。",
        ],
    }


def render_heartbeat_markdown(payload: dict[str, Any]) -> str:
    active_phase = payload.get("active_phase", {}) if isinstance(payload.get("active_phase"), dict) else {}
    lines = [
        "# DeepVision Heartbeat",
        "",
        f"> 生成时间：{payload.get('generated_at', '')}",
        "",
        "## 当前焦点",
        "",
        f"- 当前阶段：`{str(active_phase.get('name') or '-').strip() or '-'}`",
        f"- 当前优先项：`{str(active_phase.get('current_priority') or '-').strip() or '-'}`",
        f"- 阶段台账：`{str(active_phase.get('progress_file') or '-').strip() or '-'}`",
        f"- 阶段计划：`{str(active_phase.get('plan_file') or '-').strip() or '-'}`",
        "",
        "## 稳定入口",
        "",
    ]
    for doc in list(((payload.get("stable_entrypoints") or {}).get("docs") or [])):
        lines.append(f"- 文档：`{doc}`")
    for command in list(((payload.get("stable_entrypoints") or {}).get("commands") or [])):
        lines.append(f"- 命令：`{command}`")
    lines.append("")

    capabilities = payload.get("capabilities", {}) if isinstance(payload.get("capabilities"), dict) else {}
    lines.extend(
        [
            "## 当前能力基线",
            "",
            f"- task 数量：`{int(capabilities.get('task_count', 0) or 0)}`",
            f"- evaluator 场景数：`{int(capabilities.get('scenario_count', 0) or 0)}`",
            f"- browser suites：`{', '.join(list(capabilities.get('browser_suites', []) or [])) or '-'}`",
            "",
        ]
    )

    mission_entries = [item for item in list(payload.get("missions", []) or []) if isinstance(item, dict)]
    if mission_entries:
        lines.extend(["## 最近 Mission Contracts", ""])
        for item in mission_entries:
            lines.append(
                f"- `{item.get('task', '-')}`: `{item.get('mission_name', '-')}` | `{item.get('generated_at', '-')}` | `{item.get('source_file', '-')}`"
            )
        lines.append("")

    plan_entries = [item for item in list(payload.get("plans", []) or []) if isinstance(item, dict)]
    if plan_entries:
        lines.extend(["## 最近 Planner Artifacts", ""])
        for item in plan_entries:
            lines.append(
                f"- `{item.get('task', '-')}`: `{item.get('plan_name', '-')}` | `{item.get('generated_at', '-')}` | `{item.get('source_file', '-')}`"
            )
        lines.append("")

    run_entries = [item for item in list(payload.get("latest_runs", []) or []) if isinstance(item, dict)]
    if run_entries:
        lines.extend(["## 最新运行指针", ""])
        for item in run_entries:
            lines.append(
                f"- `{item.get('kind', '-')}`: overall=`{item.get('overall', '-')}` | generated_at=`{item.get('generated_at', '-')}` | latest=`{item.get('latest_json', '-')}`"
            )
        lines.append("")

    lines.extend(["## 说明", ""])
    for note in list(payload.get("notes", []) or []):
        lines.append(f"- {note}")
    lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_heartbeat_artifacts(
    payload: dict[str, Any],
    *,
    root_dir: Path = ROOT_DIR,
    artifact_dir: str = str(DEFAULT_ARTIFACT_DIR.relative_to(ROOT_DIR)),
    output_markdown: str = str(DEFAULT_MARKDOWN_PATH.relative_to(ROOT_DIR)),
) -> dict[str, str]:
    artifact_path = Path(artifact_dir).expanduser()
    if not artifact_path.is_absolute():
        artifact_path = (root_dir / artifact_path).resolve()
    artifact_path.mkdir(parents=True, exist_ok=True)

    markdown_path = Path(output_markdown).expanduser()
    if not markdown_path.is_absolute():
        markdown_path = (root_dir / markdown_path).resolve()
    markdown_path.parent.mkdir(parents=True, exist_ok=True)

    json_path = artifact_path / "latest.json"
    markdown_path.write_text(render_heartbeat_markdown(payload), encoding="utf-8")
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "markdown_file": str(markdown_path),
        "json_file": str(json_path),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="生成 DeepVision 全局 heartbeat / memory 指针")
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR.relative_to(ROOT_DIR)), help="JSON 指针输出目录")
    parser.add_argument("--output-markdown", default=str(DEFAULT_MARKDOWN_PATH.relative_to(ROOT_DIR)), help="Heartbeat markdown 输出路径")
    parser.add_argument("--dry-run", action="store_true", help="仅打印 markdown，不写文件")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_heartbeat_payload(root_dir=ROOT_DIR)
    if args.dry_run:
        print(render_heartbeat_markdown(payload))
        return 0

    outputs = write_heartbeat_artifacts(
        payload,
        root_dir=ROOT_DIR,
        artifact_dir=args.artifact_dir,
        output_markdown=args.output_markdown,
    )
    print("DeepVision agent heartbeat")
    print(f"[WRITE] {outputs['markdown_file']}")
    print(f"[WRITE] {outputs['json_file']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
