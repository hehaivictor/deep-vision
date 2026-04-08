#!/usr/bin/env python3
"""
DeepVision agent harness 工件辅助函数。
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parent.parent
from scripts import agent_scenario_scaffold


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_artifact_base_dir(base_dir: str) -> Path:
    candidate = Path(str(base_dir or "").strip()).expanduser()
    if not candidate.is_absolute():
        candidate = (ROOT_DIR / candidate).resolve()
    return candidate


def prepare_run_dir(base_dir: str) -> tuple[Path, str]:
    base_path = resolve_artifact_base_dir(base_dir)
    base_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_name = f"{timestamp}-pid{os.getpid()}"
    run_dir = base_path / run_name
    suffix = 1
    while run_dir.exists():
        suffix += 1
        run_dir = base_path / f"{run_name}-{suffix}"
    run_dir.mkdir(parents=True, exist_ok=False)
    return base_path, run_dir.name


def collect_git_context(root_dir: Path = ROOT_DIR) -> dict[str, Any]:
    def run_git(args: list[str]) -> str:
        completed = subprocess.run(
            ["git", *args],
            cwd=str(root_dir),
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            return ""
        return completed.stdout.strip()

    status_text = run_git(["status", "--short"])
    dirty_lines = [line for line in status_text.splitlines() if line.strip()]
    return {
        "commit": run_git(["rev-parse", "HEAD"]),
        "short_commit": run_git(["rev-parse", "--short", "HEAD"]),
        "branch": run_git(["rev-parse", "--abbrev-ref", "HEAD"]),
        "is_dirty": bool(dirty_lines),
        "dirty_files_count": len(dirty_lines),
        "dirty_files_preview": dirty_lines[:20],
    }


def write_json_file(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(content or ""), encoding="utf-8")


def _stringify_command(command: object) -> str:
    if isinstance(command, list):
        return " ".join(str(item or "").strip() for item in command if str(item or "").strip())
    return str(command or "").strip()


def _stringify_lines(items: object, *, limit: int = 6) -> list[str]:
    if not isinstance(items, list):
        return []
    lines: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if text:
            lines.append(text)
        if len(lines) >= limit:
            break
    return lines


def _append_unique(items: list[str], value: object) -> None:
    text = str(value or "").strip()
    if not text or text in items:
        return
    items.append(text)


def _build_scenario_scaffold_recommendation(*, source: str, run_dir: Path) -> dict[str, Any]:
    try:
        _payload, context = agent_scenario_scaffold.scaffold_scenario(
            source=source,
            run_dir=str(run_dir),
        )
    except Exception as exc:
        return {
            "preview_command": f"python3 scripts/agent_scenario_scaffold.py --source {source} --run-dir {run_dir} --dry-run",
            "write_command": f"python3 scripts/agent_scenario_scaffold.py --source {source} --run-dir {run_dir}",
            "error": str(exc),
        }
    commands = dict(context.get("scaffold_commands") or {})
    return {
        "name": str(context.get("name") or "").strip(),
        "category": str(context.get("suggested_category") or context.get("category") or "").strip(),
        "tags": [str(item).strip() for item in list(context.get("suggested_tags", []) or []) if str(item).strip()],
        "budget_ms": int(context.get("suggested_budget_ms", 0) or 0),
        "output_path": str(context.get("suggested_output_path") or "").strip(),
        "source_summary": str(context.get("source_summary") or "").strip(),
        "executor_type": str(context.get("executor_type") or "").strip(),
        "preview_command": str(commands.get("preview") or "").strip(),
        "write_command": str(commands.get("write") or "").strip(),
    }


def build_harness_progress_markdown(summary_payload: dict[str, Any], metadata: dict[str, Any]) -> str:
    results = list(summary_payload.get("results", []) or [])
    summary = summary_payload.get("summary", {}) if isinstance(summary_payload.get("summary", {}), dict) else {}
    task_payload = summary_payload.get("task") if isinstance(summary_payload.get("task"), dict) else None
    lines = [
        "# Harness Progress",
        "",
        f"- 生成时间: {metadata.get('generated_at', '')}",
        f"- 总体状态: {summary_payload.get('overall', '')}",
        f"- Git 分支: {((metadata.get('git') or {}).get('branch') or '').strip() or '-'}",
        f"- Git 提交: {((metadata.get('git') or {}).get('short_commit') or '').strip() or '-'}",
    ]
    if task_payload:
        lines.append(
            f"- 任务画像: {task_payload.get('name', '')} | risk={task_payload.get('risk_level', '')} | mode={task_payload.get('workflow_mode', '')}"
        )
    lines.extend(
        [
            "",
            "## 摘要",
            "",
            f"- PASS={int(summary.get('PASS', 0) or 0)}",
            f"- WARN={int(summary.get('WARN', 0) or 0)}",
            f"- FAIL={int(summary.get('FAIL', 0) or 0)}",
            f"- SKIP={int(summary.get('SKIP', 0) or 0)}",
            "",
            "## 阶段结果",
            "",
        ]
    )
    for item in results:
        if not isinstance(item, dict):
            continue
        lines.append(f"- `{item.get('name', '')}`: {item.get('status', '')} | {item.get('detail', '')}")

    blocked_items = [item for item in results if isinstance(item, dict) and str(item.get("status") or "").strip() == "FAIL"]
    warned_items = [item for item in results if isinstance(item, dict) and str(item.get("status") or "").strip() == "WARN"]
    lines.extend(["", "## 下一步建议", ""])
    if blocked_items:
        lines.append("- 先打开 `failure-summary.md`，按失败阶段逐条处理。")
        first_item = blocked_items[0]
        if str(first_item.get("command") or "").strip():
            lines.append(f"- 优先复跑失败阶段命令：`{first_item['command']}`")
    elif warned_items:
        lines.append("- 当前没有阻断失败，但有告警；优先检查 `failure-summary.md` 中的 WARN 项。")
    else:
        lines.append("- 当前检查全绿，可继续进入后续开发、交付或人工复核。")
    lines.append("- 如需交接，优先附带 `summary.json`、`progress.md`、`failure-summary.md` 和 `handoff.json`。")
    return "\n".join(lines).rstrip() + "\n"


def build_harness_failure_summary_markdown(summary_payload: dict[str, Any], metadata: dict[str, Any]) -> str:
    results = list(summary_payload.get("results", []) or [])
    actionable = [
        item
        for item in results
        if isinstance(item, dict) and str(item.get("status") or "").strip() in {"FAIL", "WARN"}
    ]
    lines = [
        "# Harness Failure Summary",
        "",
        f"- 生成时间: {metadata.get('generated_at', '')}",
        f"- 总体状态: {summary_payload.get('overall', '')}",
        "",
    ]
    scaffold_recommendation = None
    run_dir = str(metadata.get("run_dir") or "").strip()
    if run_dir:
        scaffold_recommendation = _build_scenario_scaffold_recommendation(source="harness", run_dir=Path(run_dir))
    if not actionable:
        lines.extend(
            [
                "当前没有 FAIL/WARN 阶段。",
                "",
                "- 可直接查看 `progress.md` 获取本次运行摘要。",
            ]
        )
        return "\n".join(lines).rstrip() + "\n"

    for item in actionable:
        lines.extend(
            [
                f"## {item.get('name', '')}",
                "",
                f"- 状态: {item.get('status', '')}",
                f"- 详情: {item.get('detail', '')}",
            ]
        )
        command = _stringify_command(item.get("command"))
        if command:
            lines.append(f"- 复跑命令: `{command}`")
        highlights = _stringify_lines(item.get("highlights"), limit=8)
        if highlights:
            lines.append("- 关键信号:")
            for line in highlights:
                lines.append(f"  - {line}")
        lines.append("")
    if scaffold_recommendation:
        lines.extend(
            [
                "## 回灌建议",
                "",
                f"- 推荐分类: `{scaffold_recommendation.get('category', '-')}`",
                f"- 推荐标签: `{', '.join(scaffold_recommendation.get('tags', [])) or '-'}`",
                f"- 推荐预算: `{int(scaffold_recommendation.get('budget_ms', 0) or 0)}` ms",
                f"- 推荐输出: `{scaffold_recommendation.get('output_path', '-')}`",
                f"- 来源摘要: `{scaffold_recommendation.get('source_summary', '-')}`",
            ]
        )
        if str(scaffold_recommendation.get("error") or "").strip():
            lines.append(f"- 说明: `{scaffold_recommendation['error']}`")
        preview_command = str(scaffold_recommendation.get("preview_command") or "").strip()
        write_command = str(scaffold_recommendation.get("write_command") or "").strip()
        if preview_command:
            lines.append(f"- 预览模板: `{preview_command}`")
        if write_command:
            lines.append(f"- 直接写入: `{write_command}`")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def build_eval_progress_markdown(summary_payload: dict[str, Any], metadata: dict[str, Any]) -> str:
    results = list(summary_payload.get("results", []) or [])
    summary = summary_payload.get("summary", {}) if isinstance(summary_payload.get("summary", {}), dict) else {}
    filters = summary_payload.get("filters", {}) if isinstance(summary_payload.get("filters", {}), dict) else {}
    lines = [
        "# Evaluator Progress",
        "",
        f"- 生成时间: {metadata.get('generated_at', '')}",
        f"- 总体状态: {summary_payload.get('overall', '')}",
        f"- 重复次数: {summary_payload.get('repeat', 1)}",
        f"- Git 分支: {((metadata.get('git') or {}).get('branch') or '').strip() or '-'}",
        f"- Git 提交: {((metadata.get('git') or {}).get('short_commit') or '').strip() or '-'}",
        "",
        "## 过滤条件",
        "",
        f"- scenario_names: {', '.join(filters.get('scenario_names', [])) or '-'}",
        f"- categories: {', '.join(filters.get('categories', [])) or '-'}",
        f"- tags: {', '.join(filters.get('tags', [])) or '-'}",
        "",
        "## 摘要",
        "",
        f"- PASS={int(summary.get('PASS', 0) or 0)}",
        f"- FLAKY={int(summary.get('FLAKY', 0) or 0)}",
        f"- FAIL={int(summary.get('FAIL', 0) or 0)}",
        f"- budget_exceeded={int(summary.get('budget_exceeded', 0) or 0)}",
        "",
        "## 场景结果",
        "",
    ]
    for item in results:
        if not isinstance(item, dict):
            continue
        lines.append(f"- `{item.get('category', '')}/{item.get('name', '')}`: {item.get('status', '')} | {item.get('detail', '')}")

    lines.extend(["", "## 下一步建议", ""])
    if str(summary_payload.get("overall") or "").strip() == "BLOCKED":
        lines.append("- 先打开 `failure-summary.md`，定位失败场景和 failure hotspot。")
    elif str(summary_payload.get("overall") or "").strip() == "DEGRADED":
        lines.append("- 优先处理 `FLAKY` 场景或预算超标场景，再决定是否纳入 nightly。")
    else:
        lines.append("- 当前 nightly 场景健康，可继续补充新的事故场景或扩大覆盖面。")
    lines.append("- 如需交接，优先附带 `summary.json`、`progress.md`、`failure-summary.md` 和 `handoff.json`。")
    return "\n".join(lines).rstrip() + "\n"


def build_eval_failure_summary_markdown(summary_payload: dict[str, Any], metadata: dict[str, Any]) -> str:
    results = list(summary_payload.get("results", []) or [])
    actionable = [
        item
        for item in results
        if isinstance(item, dict)
        and (
            str(item.get("status") or "").strip() in {"FAIL", "FLAKY"}
            or bool(((item.get("stats") or {}).get("budget_exceeded", False)))
        )
    ]
    hotspots = list(summary_payload.get("failure_hotspots", []) or [])
    lines = [
        "# Evaluator Failure Summary",
        "",
        f"- 生成时间: {metadata.get('generated_at', '')}",
        f"- 总体状态: {summary_payload.get('overall', '')}",
        "",
    ]
    scaffold_recommendation = None
    run_dir = str(metadata.get("run_dir") or "").strip()
    if run_dir:
        scaffold_recommendation = _build_scenario_scaffold_recommendation(source="eval", run_dir=Path(run_dir))
    if not actionable and not hotspots:
        lines.extend(
            [
                "当前没有失败、波动或预算超标场景。",
                "",
                "- 可直接查看 `progress.md` 获取本次 evaluator 摘要。",
            ]
        )
        return "\n".join(lines).rstrip() + "\n"

    if hotspots:
        lines.extend(["## Failure Hotspots", ""])
        for item in hotspots[:10]:
            if not isinstance(item, dict):
                continue
            lines.append(f"- `{item.get('test_id', '')}` x{int(item.get('count', 0) or 0)}")
        lines.append("")

    for item in actionable:
        stats = item.get("stats", {}) if isinstance(item.get("stats", {}), dict) else {}
        lines.extend(
            [
                f"## {item.get('category', '')}/{item.get('name', '')}",
                "",
                f"- 状态: {item.get('status', '')}",
                f"- 详情: {item.get('detail', '')}",
                f"- max_duration_ms: {float(stats.get('max_duration_ms', 0) or 0):.2f}",
                f"- budget_exceeded: {'yes' if bool(stats.get('budget_exceeded', False)) else 'no'}",
            ]
        )
        for hotspot in item.get("failure_hotspots", []) if isinstance(item.get("failure_hotspots", []), list) else []:
            if not isinstance(hotspot, dict):
                continue
            lines.append(f"- hotspot: `{hotspot.get('test_id', '')}` x{int(hotspot.get('count', 0) or 0)}")
        highlights = _stringify_lines(item.get("highlights"), limit=8)
        if highlights:
            lines.append("- 关键信号:")
            for line in highlights:
                lines.append(f"  - {line}")
        lines.append("")
    if scaffold_recommendation:
        lines.extend(
            [
                "## 回灌建议",
                "",
            ]
        )
        lines.append(f"- 推荐分类: `{scaffold_recommendation.get('category', '-')}`")
        lines.append(f"- 推荐标签: `{', '.join(scaffold_recommendation.get('tags', [])) or '-'}`")
        lines.append(f"- 推荐预算: `{int(scaffold_recommendation.get('budget_ms', 0) or 0)}` ms")
        lines.append(f"- 推荐输出: `{scaffold_recommendation.get('output_path', '-')}`")
        lines.append(f"- 来源摘要: `{scaffold_recommendation.get('source_summary', '-')}`")
        if str(scaffold_recommendation.get("error") or "").strip():
            lines.append(f"- 说明: `{scaffold_recommendation['error']}`")
        preview_command = str(scaffold_recommendation.get("preview_command") or "").strip()
        write_command = str(scaffold_recommendation.get("write_command") or "").strip()
        if preview_command:
            lines.append(f"- 预览模板: `{preview_command}`")
        if write_command:
            lines.append(f"- 直接写入: `{write_command}`")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def build_harness_handoff_payload(
    summary_payload: dict[str, Any],
    metadata: dict[str, Any],
    stage_artifacts: dict[str, dict[str, Any]],
    *,
    run_dir: Path,
    base_path: Path,
) -> dict[str, Any]:
    results = [item for item in list(summary_payload.get("results", []) or []) if isinstance(item, dict)]
    task_payload = summary_payload.get("task") if isinstance(summary_payload.get("task"), dict) else None
    workflow_payload = (
        ((stage_artifacts.get("workflow") or {}).get("workflow"))
        if isinstance(stage_artifacts.get("workflow"), dict)
        else None
    )
    rendered_workflow = (
        (workflow_payload.get("workflow") if isinstance(workflow_payload.get("workflow"), dict) else workflow_payload)
        if isinstance(workflow_payload, dict)
        else None
    )
    governance_payload = (
        (workflow_payload.get("governance") if isinstance(workflow_payload.get("governance"), dict) else {})
        if isinstance(workflow_payload, dict)
        else {}
    )
    workflow_step_results = [
        item for item in list((workflow_payload or {}).get("step_results", []) or []) if isinstance(item, dict)
    ] if isinstance(workflow_payload, dict) else []
    workflow_precondition_results = [
        item for item in list((workflow_payload or {}).get("precondition_results", []) or []) if isinstance(item, dict)
    ] if isinstance(workflow_payload, dict) else []

    todo: list[str] = []
    blockers: list[str] = []
    next_steps: list[str] = []
    resume_commands: list[str] = []
    docs: list[str] = []
    scaffold_recommendation = _build_scenario_scaffold_recommendation(source="harness", run_dir=run_dir)

    for item in list((task_payload or {}).get("docs", []) or []):
        _append_unique(docs, item)
    for item in list((rendered_workflow or {}).get("docs", []) or []):
        _append_unique(docs, item)

    for item in results:
        status = str(item.get("status") or "").strip()
        name = str(item.get("name") or "").strip()
        detail = str(item.get("detail") or "").strip()
        command = _stringify_command(item.get("command"))
        if status == "FAIL":
            _append_unique(blockers, f"{name}: {detail}")
            if command and not command.startswith("task-profile:"):
                _append_unique(resume_commands, command)
        elif status == "WARN":
            _append_unique(todo, f"{name}: {detail}")
            if command and not command.startswith("task-profile:"):
                _append_unique(resume_commands, command)

    if isinstance(rendered_workflow, dict):
        missing_vars = list(rendered_workflow.get("missing_vars", []) or [])
        if missing_vars:
            _append_unique(blockers, "补齐 task 变量: " + ", ".join(sorted(str(item).strip() for item in missing_vars if str(item).strip())))
        governance_missing = [str(item).strip() for item in list((governance_payload or {}).get("missing_fields", []) or []) if str(item).strip()]
        governance_values = (
            {str(key).strip(): str(value).strip() for key, value in dict((governance_payload or {}).get("values") or {}).items() if str(key).strip() and str(value).strip()}
            if isinstance((governance_payload or {}).get("values"), dict)
            else {}
        )
        if governance_missing:
            _append_unique(todo, "高风险写操作前需补齐治理字段: " + ", ".join(governance_missing))
        if governance_values:
            governance_summary = ", ".join(f"{key}={value}" for key, value in governance_values.items())
            _append_unique(next_steps, "治理记录已准备: " + governance_summary)
        hidden_apply_steps = list(rendered_workflow.get("hidden_apply_steps", []) or [])
        if hidden_apply_steps:
            _append_unique(todo, f"如需正式 apply/rollback，人工确认后使用 --allow-apply，目前已隐藏 {len(hidden_apply_steps)} 个高风险步骤。")

        for precondition_result in workflow_precondition_results:
            status = str(precondition_result.get("status") or "").strip()
            title = str(precondition_result.get("title") or precondition_result.get("id") or "").strip()
            detail = str(precondition_result.get("detail") or "").strip()
            if status == "BLOCKED":
                _append_unique(blockers, f"{title}: {detail}" if title else detail)

        for step_result in workflow_step_results:
            status = str(step_result.get("status") or "").strip()
            title = str(step_result.get("title") or step_result.get("id") or "").strip()
            detail = str(step_result.get("detail") or "").strip()
            command = _stringify_command(step_result.get("command"))
            confirmation_hint = str(step_result.get("confirmation_token_hint") or "").strip()
            artifact_paths = [str(item).strip() for item in list(step_result.get("artifact_paths", []) or []) if str(item).strip()]
            if status == "FAIL":
                _append_unique(blockers, f"{title}: {detail}" if title else detail)
                if command:
                    _append_unique(resume_commands, command)
            elif status == "BLOCKED":
                _append_unique(blockers, f"{title}: {detail}" if title else detail)
            if confirmation_hint and status in {"BLOCKED", "MANUAL", "SKIP"}:
                _append_unique(todo, f"{title}: 如需继续，请传 --task-var confirmation_token={confirmation_hint}")
            if artifact_paths:
                for artifact_path in artifact_paths[:3]:
                    _append_unique(next_steps, f"{title}: 查看工件 {artifact_path}")

        visible_steps = [item for item in list(rendered_workflow.get("steps", []) or []) if isinstance(item, dict)]
        for step in visible_steps[:3]:
            step_missing = [str(item).strip() for item in list(step.get("missing_vars", []) or []) if str(item).strip()]
            if step_missing:
                continue
            title = str(step.get("title") or step.get("id") or "").strip()
            command = _stringify_command(step.get("command"))
            detail = str(step.get("detail") or "").strip()
            confirmation_hint = str(step.get("confirmation_token") or "").strip()
            if confirmation_hint:
                _append_unique(todo, f"{title}: 执行前需显式确认 confirmation_token={confirmation_hint}")
            if bool(step.get("requires_backup", False)):
                _append_unique(todo, f"{title}: 执行前需准备真实 backup_dir，并确认目录可读。")
            if command:
                _append_unique(next_steps, f"{title}: {command}" if title else command)
                _append_unique(resume_commands, command)
            elif detail:
                _append_unique(next_steps, f"{title}: {detail}" if title else detail)

    if not next_steps:
        if blockers:
            _append_unique(next_steps, "先查看 failure-summary.md，按阻塞项顺序处理。")
        elif todo:
            _append_unique(next_steps, "先查看 failure-summary.md，处理 WARN 项并决定是否继续。")
        else:
            _append_unique(next_steps, "当前无阻塞，可继续执行后续开发、交付或人工复核。")

    if blockers or todo:
        preview_command = str(scaffold_recommendation.get("preview_command") or "").strip()
        write_command = str(scaffold_recommendation.get("write_command") or "").strip()
        category_hint = str(scaffold_recommendation.get("category") or "").strip()
        output_hint = str(scaffold_recommendation.get("output_path") or "").strip()
        if preview_command:
            _append_unique(next_steps, f"如需预览场景模板，可执行：{preview_command}")
            _append_unique(resume_commands, preview_command)
        if write_command:
            scaffold_hint = "如需沉淀本次失败，可执行："
            if category_hint or output_hint:
                scaffold_hint = (
                    "如需沉淀本次失败，可执行："
                    f"{write_command} (category={category_hint or '-'} output={output_hint or '-'})"
                )
                _append_unique(next_steps, scaffold_hint)
            else:
                _append_unique(next_steps, scaffold_hint + write_command)
            _append_unique(resume_commands, write_command)

    return {
        "kind": "harness",
        "generated_at": metadata.get("generated_at", ""),
        "overall": summary_payload.get("overall", ""),
        "task": task_payload,
        "todo": todo,
        "blockers": blockers,
        "next_steps": next_steps,
        "resume_commands": resume_commands,
        "docs": docs,
        "governance": {
            "required_for_apply": bool((governance_payload or {}).get("required_for_apply", False)),
            "missing_fields": [str(item).strip() for item in list((governance_payload or {}).get("missing_fields", []) or []) if str(item).strip()],
            "values": (
                {str(key).strip(): str(value).strip() for key, value in dict((governance_payload or {}).get("values") or {}).items() if str(key).strip() and str(value).strip()}
                if isinstance((governance_payload or {}).get("values"), dict)
                else {}
            ),
            "ready": bool((governance_payload or {}).get("ready", True)),
        },
        "scaffold_recommendation": scaffold_recommendation,
        "pointers": {
            "run_dir": str(run_dir),
            "summary_file": str(run_dir / "summary.json"),
            "progress_file": str(run_dir / "progress.md"),
            "failure_summary_file": str(run_dir / "failure-summary.md"),
            "handoff_file": str(run_dir / "handoff.json"),
            "latest_json": str(base_path / "latest.json"),
            "latest_handoff": str(base_path / "latest-handoff.json"),
        },
    }


def build_eval_handoff_payload(
    summary_payload: dict[str, Any],
    metadata: dict[str, Any],
    *,
    run_dir: Path,
    base_path: Path,
) -> dict[str, Any]:
    results = [item for item in list(summary_payload.get("results", []) or []) if isinstance(item, dict)]
    todo: list[str] = []
    blockers: list[str] = []
    next_steps: list[str] = []
    resume_commands: list[str] = []
    scaffold_recommendation = _build_scenario_scaffold_recommendation(source="eval", run_dir=run_dir)

    repeat = int(summary_payload.get("repeat", 1) or 1)
    for item in results:
        status = str(item.get("status") or "").strip()
        category = str(item.get("category") or "").strip()
        name = str(item.get("name") or "").strip()
        detail = str(item.get("detail") or "").strip()
        rerun_command = f"python3 scripts/agent_eval.py --scenario {name}"
        if repeat > 1:
            rerun_command += f" --repeat {repeat}"
        if status == "FAIL":
            _append_unique(blockers, f"{category}/{name}: {detail}")
            _append_unique(resume_commands, rerun_command)
        elif status == "FLAKY":
            _append_unique(todo, f"{category}/{name}: {detail}")
            _append_unique(resume_commands, rerun_command)
        stats = item.get("stats", {}) if isinstance(item.get("stats", {}), dict) else {}
        if bool(stats.get("budget_exceeded", False)):
            _append_unique(todo, f"{category}/{name}: 超出预算 {float(stats.get('max_duration_budget_ms', 0) or 0):.2f}ms")
            _append_unique(resume_commands, rerun_command)

    hotspots = list(summary_payload.get("failure_hotspots", []) or [])
    if hotspots:
        top = hotspots[0]
        if isinstance(top, dict) and str(top.get("test_id") or "").strip():
            _append_unique(next_steps, f"优先查看 failure-summary.md 中的 hotspot：{top['test_id']}")

    if not next_steps:
        overall = str(summary_payload.get("overall") or "").strip()
        if overall == "BLOCKED":
            _append_unique(next_steps, "先按失败场景逐条重跑，再决定是否回退到单个 unittest。")
        elif overall == "DEGRADED":
            _append_unique(next_steps, "优先处理波动场景或预算超标场景，再决定是否继续纳入 nightly。")
        else:
            _append_unique(next_steps, "当前 evaluator 健康，可继续补充新的事故场景或扩大覆盖。")

    if blockers or todo:
        preview_command = str(scaffold_recommendation.get("preview_command") or "").strip()
        write_command = str(scaffold_recommendation.get("write_command") or "").strip()
        category_hint = str(scaffold_recommendation.get("category") or "").strip()
        output_hint = str(scaffold_recommendation.get("output_path") or "").strip()
        if preview_command:
            _append_unique(next_steps, f"如需预览新的 evaluator 场景模板，可执行：{preview_command}")
            _append_unique(resume_commands, preview_command)
        if write_command:
            scaffold_hint = "如需沉淀新的 evaluator 场景，可执行："
            if category_hint or output_hint:
                scaffold_hint = (
                    "如需沉淀新的 evaluator 场景，可执行："
                    f"{write_command} (category={category_hint or '-'} output={output_hint or '-'})"
                )
                _append_unique(next_steps, scaffold_hint)
            else:
                _append_unique(next_steps, scaffold_hint + write_command)
            _append_unique(resume_commands, write_command)

    return {
        "kind": "evaluator",
        "generated_at": metadata.get("generated_at", ""),
        "overall": summary_payload.get("overall", ""),
        "filters": summary_payload.get("filters", {}),
        "todo": todo,
        "blockers": blockers,
        "next_steps": next_steps,
        "resume_commands": resume_commands,
        "docs": [
            "docs/agent/evaluator.md",
            "docs/agent/playbooks/README.md",
        ],
        "scaffold_recommendation": scaffold_recommendation,
        "pointers": {
            "run_dir": str(run_dir),
            "summary_file": str(run_dir / "summary.json"),
            "progress_file": str(run_dir / "progress.md"),
            "failure_summary_file": str(run_dir / "failure-summary.md"),
            "handoff_file": str(run_dir / "handoff.json"),
            "latest_json": str(base_path / "latest.json"),
            "latest_handoff": str(base_path / "latest-handoff.json"),
        },
    }


def write_harness_artifacts(
    *,
    base_dir: str,
    summary_payload: dict[str, Any],
    stage_artifacts: dict[str, dict[str, Any]],
    root_dir: Path = ROOT_DIR,
) -> dict[str, str]:
    base_path, run_name = prepare_run_dir(base_dir)
    run_dir = base_path / run_name
    generated_at = utc_now_iso()

    metadata = {
        "generated_at": generated_at,
        "root_dir": str(root_dir),
        "run_name": run_name,
        "base_dir": str(base_path),
        "run_dir": str(run_dir),
        "git": collect_git_context(root_dir),
    }

    write_json_file(run_dir / "run-meta.json", metadata)
    write_json_file(run_dir / "summary.json", {**summary_payload, "metadata": metadata})

    for stage_name, payload in stage_artifacts.items():
        payload_to_write = dict(payload or {})
        stdout = str(payload_to_write.pop("stdout", "") or "")
        stderr = str(payload_to_write.pop("stderr", "") or "")
        write_json_file(run_dir / f"{stage_name}.json", payload_to_write)
        if stdout:
            write_text_file(run_dir / f"{stage_name}.stdout.log", stdout)
        if stderr:
            write_text_file(run_dir / f"{stage_name}.stderr.log", stderr)

    progress_content = build_harness_progress_markdown(summary_payload, metadata)
    failure_summary_content = build_harness_failure_summary_markdown(summary_payload, metadata)
    write_text_file(run_dir / "progress.md", progress_content)
    write_text_file(run_dir / "failure-summary.md", failure_summary_content)

    handoff_payload = build_harness_handoff_payload(
        summary_payload,
        metadata,
        stage_artifacts,
        run_dir=run_dir,
        base_path=base_path,
    )
    write_json_file(run_dir / "handoff.json", handoff_payload)

    latest_payload = {
        "generated_at": generated_at,
        "run_name": run_name,
        "run_dir": str(run_dir),
        "summary_file": str(run_dir / "summary.json"),
        "progress_file": str(run_dir / "progress.md"),
        "failure_summary_file": str(run_dir / "failure-summary.md"),
        "handoff_file": str(run_dir / "handoff.json"),
        "overall": summary_payload.get("overall", ""),
    }
    write_json_file(base_path / "latest.json", latest_payload)
    write_text_file(base_path / "latest.txt", str(run_dir))
    write_text_file(base_path / "latest-progress.md", progress_content)
    write_text_file(base_path / "latest-failure-summary.md", failure_summary_content)
    write_json_file(base_path / "latest-handoff.json", handoff_payload)

    return {
        "base_dir": str(base_path),
        "run_dir": str(run_dir),
        "latest_json": str(base_path / "latest.json"),
        "latest_txt": str(base_path / "latest.txt"),
        "progress_file": str(run_dir / "progress.md"),
        "failure_summary_file": str(run_dir / "failure-summary.md"),
        "handoff_file": str(run_dir / "handoff.json"),
        "latest_progress": str(base_path / "latest-progress.md"),
        "latest_failure_summary": str(base_path / "latest-failure-summary.md"),
        "latest_handoff": str(base_path / "latest-handoff.json"),
    }
