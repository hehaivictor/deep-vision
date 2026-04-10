#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
DeepVision harness 薄运营面入口。

目标：
1. 把 heartbeat、doc gardener、task 覆盖率、latest 指针收口到一个只读入口
2. 为当前阶段提供 status / phase / task-gap / latest-runs / gardening-report 五类轻量运维视图
3. 默认只读，不自动刷新 heartbeat / gardening / autodream
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from dataclasses import dataclass
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_ARTIFACT_DIR = ROOT_DIR / "artifacts" / "ops"

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts import agent_calibration
from scripts import agent_contracts
from scripts import agent_doc_gardener
from scripts import agent_heartbeat
from scripts import agent_history
from scripts import agent_missions
from scripts import agent_plans
from scripts import agent_profiles

STABILITY_RELEASE_WARN_MS = 20 * 60 * 1000.0
STABILITY_RELEASE_FAIL_MS = STABILITY_RELEASE_WARN_MS * 1.2


@dataclass
class OpsArtifactPaths:
    run_dir: str
    json_file: str
    markdown_file: str
    latest_json: str
    latest_markdown: str


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _relative_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT_DIR.resolve()))
    except Exception:
        return str(path.resolve())


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _build_task_gap_payload() -> dict[str, Any]:
    task_rows: list[dict[str, Any]] = []
    planner_meta = 0
    mission_meta = 0
    planner_materialized = 0
    mission_materialized = 0
    high_risk_total = 0
    high_risk_contracts = 0

    missing_planner_meta: list[str] = []
    missing_mission_meta: list[str] = []
    missing_planner_pointer: list[str] = []
    missing_mission_pointer: list[str] = []
    missing_contracts: list[str] = []

    for task_name in agent_profiles.list_task_names():
        profile = agent_profiles.get_task_profile(task_name)
        risk_level = str(profile.get("risk_level") or "medium").strip()
        planner_ready = isinstance(profile.get("planner"), dict)
        mission_ready = isinstance(profile.get("mission"), dict)
        planner_pointer = agent_plans.load_task_latest_pointer(task_name)
        mission_pointer = agent_missions.load_task_latest_pointer(task_name)
        contract_payload = agent_contracts.get_contract_for_profile(profile)
        contract_ready = isinstance(contract_payload, dict) and bool(str(contract_payload.get("name") or "").strip())

        if planner_ready:
            planner_meta += 1
        else:
            missing_planner_meta.append(task_name)
        if mission_ready:
            mission_meta += 1
        else:
            missing_mission_meta.append(task_name)
        if planner_pointer:
            planner_materialized += 1
        elif planner_ready:
            missing_planner_pointer.append(task_name)
        if mission_pointer:
            mission_materialized += 1
        elif mission_ready:
            missing_mission_pointer.append(task_name)
        if risk_level == "high":
            high_risk_total += 1
            if contract_ready:
                high_risk_contracts += 1
            else:
                missing_contracts.append(task_name)

        task_rows.append(
            {
                "task": task_name,
                "risk_level": risk_level,
                "planner": {
                    "meta": planner_ready,
                    "materialized": bool(planner_pointer),
                },
                "mission": {
                    "meta": mission_ready,
                    "materialized": bool(mission_pointer),
                },
                "contract": {
                    "attached": contract_ready,
                    "name": str((contract_payload or {}).get("name") or "").strip(),
                },
                "source_file": str(profile.get("source_file") or "").strip(),
            }
        )

    overall = "HEALTHY"
    if (
        missing_planner_meta
        or missing_mission_meta
        or missing_planner_pointer
        or missing_mission_pointer
        or missing_contracts
    ):
        overall = "ATTENTION_REQUIRED"

    return {
        "overall": overall,
        "task_count": len(task_rows),
        "planner_meta": planner_meta,
        "planner_materialized": planner_materialized,
        "mission_meta": mission_meta,
        "mission_materialized": mission_materialized,
        "high_risk_contracts": high_risk_contracts,
        "high_risk_total": high_risk_total,
        "missing": {
            "planner_meta": missing_planner_meta,
            "mission_meta": missing_mission_meta,
            "planner_materialized": missing_planner_pointer,
            "mission_materialized": missing_mission_pointer,
            "contracts": missing_contracts,
        },
        "tasks": task_rows,
    }


def _build_latest_runs_payload(root_dir: Path) -> dict[str, Any]:
    heartbeat_payload = agent_heartbeat.build_heartbeat_payload(root_dir=root_dir)
    latest_runs = [item for item in list(heartbeat_payload.get("latest_runs", []) or []) if isinstance(item, dict)]
    blockers: list[str] = []
    warnings: list[str] = []
    for item in latest_runs:
        duration_ms = float(item.get("duration_ms", 0) or 0)
        duration_text = f" duration_ms={duration_ms:.2f}" if duration_ms > 0 else ""
        label = f"{item.get('kind', '-')}: overall={item.get('overall', '-')}{duration_text}"
        overall = str(item.get("overall") or "").strip()
        if overall == "BLOCKED":
            blockers.append(label)
        elif overall in {"READY_WITH_WARNINGS", "ATTENTION_REQUIRED"}:
            warnings.append(label)
        if str(item.get("kind") or "").strip() == "harness-stability-release" and duration_ms > 0:
            if duration_ms > STABILITY_RELEASE_FAIL_MS:
                blockers.append(
                    f"stability-local-release: duration_ms={duration_ms:.2f} 超过 FAIL 阈值 {STABILITY_RELEASE_FAIL_MS:.2f}"
                )
            elif duration_ms > STABILITY_RELEASE_WARN_MS:
                warnings.append(
                    f"stability-local-release: duration_ms={duration_ms:.2f} 超过 WARN 阈值 {STABILITY_RELEASE_WARN_MS:.2f}"
                )

    harness_diff = agent_history.build_history_diff(kind="harness", root_dir=root_dir)
    evaluator_diff = agent_history.build_history_diff(kind="evaluator", root_dir=root_dir)
    ci_browser_diff = agent_history.build_history_diff(kind="ci-browser-smoke", root_dir=root_dir)

    return {
        "latest_runs": latest_runs,
        "blockers": blockers,
        "warnings": warnings,
        "stability_gates": {
            "release_max_duration_warn_ms": STABILITY_RELEASE_WARN_MS,
            "release_max_duration_fail_ms": STABILITY_RELEASE_FAIL_MS,
        },
        "diffs": {
            "harness": {
                "overall": str(harness_diff.get("overall") or "").strip(),
                "changed_results": len(list(harness_diff.get("changed_results", []) or [])),
            },
            "evaluator": {
                "overall": str(evaluator_diff.get("overall") or "").strip(),
                "changed_results": len(list(evaluator_diff.get("changed_results", []) or [])),
            },
            "ci-browser-smoke": {
                "overall": str(ci_browser_diff.get("overall") or "").strip(),
                "changed_results": len(list(ci_browser_diff.get("changed_results", []) or [])),
            },
        },
    }


def build_ops_payload(*, root_dir: Path = ROOT_DIR) -> dict[str, Any]:
    heartbeat_payload = agent_heartbeat.build_heartbeat_payload(root_dir=root_dir)
    gardening_payload = agent_doc_gardener.build_doc_gardening_report()
    task_gap = _build_task_gap_payload()
    latest_runs = _build_latest_runs_payload(root_dir)
    calibration_count = len(agent_calibration.load_calibration_samples())
    active_phase = heartbeat_payload.get("active_phase", {}) if isinstance(heartbeat_payload.get("active_phase"), dict) else {}

    blockers = list(latest_runs.get("blockers", []) or [])
    warnings = list(latest_runs.get("warnings", []) or [])
    if gardening_payload.get("overall") == "BLOCKED":
        blockers.append("doc-gardener: overall=BLOCKED")
    elif gardening_payload.get("overall") == "ATTENTION_REQUIRED":
        warnings.append("doc-gardener: overall=ATTENTION_REQUIRED")

    if blockers:
        overall = "BLOCKED"
    elif warnings or task_gap.get("overall") != "HEALTHY":
        overall = "ATTENTION_REQUIRED"
    else:
        overall = "HEALTHY"

    return {
        "kind": "ops_status",
        "generated_at": utc_now_iso(),
        "root_dir": str(root_dir.resolve()),
        "overall": overall,
        "phase": {
            "name": str(active_phase.get("name") or "").strip(),
            "current_priority": str(active_phase.get("current_priority") or "").strip(),
            "progress_file": str(active_phase.get("progress_file") or "").strip(),
            "plan_file": str(active_phase.get("plan_file") or "").strip(),
        },
        "coverage": {
            "task_count": _safe_int(task_gap.get("task_count")),
            "planner_meta": _safe_int(task_gap.get("planner_meta")),
            "planner_materialized": _safe_int(task_gap.get("planner_materialized")),
            "mission_meta": _safe_int(task_gap.get("mission_meta")),
            "mission_materialized": _safe_int(task_gap.get("mission_materialized")),
            "high_risk_contracts": _safe_int(task_gap.get("high_risk_contracts")),
            "high_risk_total": _safe_int(task_gap.get("high_risk_total")),
            "calibration_samples": calibration_count,
            "agent_entrypoint_count": _safe_int(((heartbeat_payload.get("capabilities") or {}).get("agent_entrypoint_count"))),
            "scenario_count": _safe_int(((heartbeat_payload.get("capabilities") or {}).get("scenario_count"))),
        },
        "task_gap": task_gap,
        "doc_gardening": {
            "overall": str(gardening_payload.get("overall") or "").strip(),
            "summary": dict(gardening_payload.get("summary", {}) if isinstance(gardening_payload.get("summary", {}), dict) else {}),
            "checks": list(gardening_payload.get("checks", []) or []),
        },
        "latest_runs": latest_runs,
        "stable_entrypoints": dict(heartbeat_payload.get("stable_entrypoints", {}) if isinstance(heartbeat_payload.get("stable_entrypoints"), dict) else {}),
        "recommended_commands": [
            "python3 scripts/agent_ops.py status",
            "python3 scripts/agent_ops.py task-gap",
            "python3 scripts/agent_ops.py latest-runs",
            "python3 scripts/agent_doc_gardener.py",
            "python3 scripts/agent_heartbeat.py",
        ],
    }


def render_status_markdown(payload: dict[str, Any]) -> str:
    phase = payload.get("phase", {}) if isinstance(payload.get("phase"), dict) else {}
    coverage = payload.get("coverage", {}) if isinstance(payload.get("coverage"), dict) else {}
    latest_runs = payload.get("latest_runs", {}) if isinstance(payload.get("latest_runs"), dict) else {}
    task_gap = payload.get("task_gap", {}) if isinstance(payload.get("task_gap"), dict) else {}
    gardening = payload.get("doc_gardening", {}) if isinstance(payload.get("doc_gardening"), dict) else {}

    lines = [
        "# DeepVision Harness Ops",
        "",
        f"> 生成时间：{payload.get('generated_at', '')}",
        "",
        "## 总览",
        "",
        f"- overall：`{payload.get('overall', '-')}`",
        f"- 当前阶段：`{phase.get('name', '-')}`",
        f"- 当前优先项：`{phase.get('current_priority', '-')}`",
        f"- phase 台账：`{phase.get('progress_file', '-')}`",
        "",
        "## 覆盖率",
        "",
        f"- task：`{coverage.get('task_count', 0)}`",
        f"- planner：`{coverage.get('planner_materialized', 0)}/{coverage.get('planner_meta', 0)}`",
        f"- mission：`{coverage.get('mission_materialized', 0)}/{coverage.get('mission_meta', 0)}`",
        f"- 高风险 contract：`{coverage.get('high_risk_contracts', 0)}/{coverage.get('high_risk_total', 0)}`",
        f"- calibration：`{coverage.get('calibration_samples', 0)}`",
        f"- evaluator 场景：`{coverage.get('scenario_count', 0)}`",
        f"- AGENTS 入口：`{coverage.get('agent_entrypoint_count', 0)}`",
        "",
        "## 园丁状态",
        "",
        f"- overall：`{gardening.get('overall', '-')}`",
        f"- summary：`PASS={_safe_int((gardening.get('summary') or {}).get('PASS'))} WARN={_safe_int((gardening.get('summary') or {}).get('WARN'))} FAIL={_safe_int((gardening.get('summary') or {}).get('FAIL'))}`",
        "",
        "## 最新运行",
        "",
    ]

    for item in list(latest_runs.get("latest_runs", []) or []):
        if not isinstance(item, dict):
            continue
        lines.append(
            f"- `{item.get('kind', '-')}`: overall=`{item.get('overall', '-')}` | generated_at=`{item.get('generated_at', '-')}` | duration_ms=`{float(item.get('duration_ms', 0) or 0):.2f}` | latest=`{item.get('latest_json', '-')}`"
        )
    if not list(latest_runs.get("latest_runs", []) or []):
        lines.append("- 暂无 latest 指针。")
    lines.append("")

    diffs = latest_runs.get("diffs", {}) if isinstance(latest_runs.get("diffs"), dict) else {}
    lines.extend(["## 漂移摘要", ""])
    for key in ("harness", "evaluator", "ci-browser-smoke"):
        diff_payload = diffs.get(key, {}) if isinstance(diffs.get(key), dict) else {}
        lines.append(
            f"- `{key}`: overall=`{diff_payload.get('overall', '-')}` | changed_results=`{_safe_int(diff_payload.get('changed_results'))}`"
        )
    lines.append("")

    blockers = list(latest_runs.get("blockers", []) or [])
    warnings = list(latest_runs.get("warnings", []) or [])
    lines.extend(["## 风险提示", ""])
    if blockers:
        for item in blockers:
            lines.append(f"- BLOCKER: {item}")
    if warnings:
        for item in warnings:
            lines.append(f"- WARN: {item}")
    if not blockers and not warnings and task_gap.get("overall") == "HEALTHY":
        lines.append("- 当前没有额外 blocker；覆盖率与最新指针均处于健康状态。")
    lines.append("")

    stability_gates = latest_runs.get("stability_gates", {}) if isinstance(latest_runs.get("stability_gates"), dict) else {}
    lines.extend(["## 稳定性门槛", ""])
    lines.append(
        f"- `stability-local-release` WARN：`{float(stability_gates.get('release_max_duration_warn_ms', 0) or 0):.2f}ms`"
    )
    lines.append(
        f"- `stability-local-release` FAIL：`{float(stability_gates.get('release_max_duration_fail_ms', 0) or 0):.2f}ms`"
    )
    lines.append("")

    missing = task_gap.get("missing", {}) if isinstance(task_gap.get("missing"), dict) else {}
    lines.extend(["## 覆盖缺口", ""])
    for label, items in (
        ("planner_meta", list(missing.get("planner_meta", []) or [])),
        ("mission_meta", list(missing.get("mission_meta", []) or [])),
        ("planner_materialized", list(missing.get("planner_materialized", []) or [])),
        ("mission_materialized", list(missing.get("mission_materialized", []) or [])),
        ("contracts", list(missing.get("contracts", []) or [])),
    ):
        if items:
            lines.append(f"- `{label}`: {', '.join(items)}")
    if not any(list(missing.get(key, []) or []) for key in ("planner_meta", "mission_meta", "planner_materialized", "mission_materialized", "contracts")):
        lines.append("- 当前 task 契约覆盖无缺口。")
    lines.append("")

    lines.extend(["## 推荐入口", ""])
    for command in list(payload.get("recommended_commands", []) or []):
        lines.append(f"- `{command}`")
    return "\n".join(lines).rstrip() + "\n"


def write_artifacts(payload: dict[str, Any], *, artifact_dir: Path) -> OpsArtifactPaths:
    generated_at = str(payload.get("generated_at") or utc_now_iso()).replace(":", "").replace("-", "")
    run_name = generated_at.replace("T", "T").replace("Z", "Z")
    run_dir = artifact_dir / run_name
    run_dir.mkdir(parents=True, exist_ok=True)

    json_file = run_dir / "summary.json"
    markdown_file = run_dir / "summary.md"
    json_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_file.write_text(render_status_markdown(payload), encoding="utf-8")

    latest_json = artifact_dir / "latest.json"
    latest_markdown = artifact_dir / "latest.md"
    latest_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    latest_markdown.write_text(render_status_markdown(payload), encoding="utf-8")

    return OpsArtifactPaths(
        run_dir=str(run_dir.resolve()),
        json_file=str(json_file.resolve()),
        markdown_file=str(markdown_file.resolve()),
        latest_json=str(latest_json.resolve()),
        latest_markdown=str(latest_markdown.resolve()),
    )


def render_phase(payload: dict[str, Any]) -> None:
    phase = payload.get("phase", {}) if isinstance(payload.get("phase"), dict) else {}
    print("DeepVision harness ops phase")
    print(f"overall: {payload.get('overall', '')}")
    print(f"phase: {phase.get('name', '-')}")
    print(f"priority: {phase.get('current_priority', '-')}")
    print(f"progress: {phase.get('progress_file', '-')}")
    print(f"plan: {phase.get('plan_file', '-')}")


def render_task_gap(payload: dict[str, Any]) -> None:
    gap = payload.get("task_gap", {}) if isinstance(payload.get("task_gap"), dict) else {}
    print("DeepVision harness ops task-gap")
    print(f"overall: {gap.get('overall', '')}")
    print(
        "coverage: "
        f"planner={gap.get('planner_materialized', 0)}/{gap.get('planner_meta', 0)} "
        f"mission={gap.get('mission_materialized', 0)}/{gap.get('mission_meta', 0)} "
        f"high-risk-contract={gap.get('high_risk_contracts', 0)}/{gap.get('high_risk_total', 0)}"
    )
    for row in list(gap.get("tasks", []) or []):
        if not isinstance(row, dict):
            continue
        print(
            f"- {row.get('task', '-')}: risk={row.get('risk_level', '-')} "
            f"planner={int(bool((row.get('planner') or {}).get('materialized')))} "
            f"mission={int(bool((row.get('mission') or {}).get('materialized')))} "
            f"contract={int(bool((row.get('contract') or {}).get('attached')))}"
        )


def render_latest_runs(payload: dict[str, Any]) -> None:
    latest_runs = payload.get("latest_runs", {}) if isinstance(payload.get("latest_runs"), dict) else {}
    print("DeepVision harness ops latest-runs")
    for item in list(latest_runs.get("latest_runs", []) or []):
        if not isinstance(item, dict):
            continue
        print(
            f"- {item.get('kind', '-')}: overall={item.get('overall', '-')} generated_at={item.get('generated_at', '-')} duration_ms={float(item.get('duration_ms', 0) or 0):.2f} latest={item.get('latest_json', '-')}"
        )
    for item in list(latest_runs.get("blockers", []) or []):
        print(f"BLOCKER: {item}")
    for item in list(latest_runs.get("warnings", []) or []):
        print(f"WARN: {item}")


def render_gardening_report(payload: dict[str, Any]) -> None:
    gardening = payload.get("doc_gardening", {}) if isinstance(payload.get("doc_gardening"), dict) else {}
    print("DeepVision harness ops gardening-report")
    print(f"overall: {gardening.get('overall', '')}")
    summary = gardening.get("summary", {}) if isinstance(gardening.get("summary", {}), dict) else {}
    print(
        f"summary: PASS={_safe_int(summary.get('PASS'))} WARN={_safe_int(summary.get('WARN'))} FAIL={_safe_int(summary.get('FAIL'))}"
    )
    for item in list(gardening.get("checks", []) or []):
        if not isinstance(item, dict):
            continue
        print(f"- [{item.get('status', '-')}] {item.get('name', '-')}: {item.get('detail', '-')}")


def render_status(payload: dict[str, Any]) -> None:
    print(render_status_markdown(payload).rstrip())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DeepVision harness 薄运营面入口")
    parser.add_argument(
        "command",
        nargs="?",
        default="status",
        choices=["status", "phase", "task-gap", "latest-runs", "gardening-report"],
        help="选择输出视图，默认 status",
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--artifact-dir", default="", help="可选：把当前 ops 摘要落盘到指定目录")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_ops_payload(root_dir=ROOT_DIR)

    if args.artifact_dir:
        write_artifacts(payload, artifact_dir=Path(args.artifact_dir).expanduser().resolve())

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if args.command == "phase":
        render_phase(payload)
    elif args.command == "task-gap":
        render_task_gap(payload)
    elif args.command == "latest-runs":
        render_latest_runs(payload)
    elif args.command == "gardening-report":
        render_gardening_report(payload)
    else:
        render_status(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
