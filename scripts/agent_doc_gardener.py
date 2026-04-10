#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
DeepVision harness 文档园丁 / 一致性报告。

目标：
1. 只读检查 task / playbook / contract / calibration / 索引文档之间是否一致
2. 输出可执行建议，但不自动修改业务代码或文档
3. 为当前阶段的 doc gardening 提供独立入口与 artifact
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
DEFAULT_ARTIFACT_DIR = ROOT_DIR / "artifacts" / "doc-gardening"
AGENTS_FILE = ROOT_DIR / "AGENTS.md"
README_FILE = ROOT_DIR / "README.md"
AGENT_README_FILE = ROOT_DIR / "docs" / "agent" / "README.md"
CALIBRATION_DOC_FILE = ROOT_DIR / "docs" / "agent" / "evaluator-calibration.md"
PLANNER_TASK_INDEX_DIR = ROOT_DIR / "artifacts" / "planner" / "by-task"
MISSION_TASK_INDEX_DIR = ROOT_DIR / "artifacts" / "planner" / "missions" / "by-task"
LOCAL_AGENT_FILES = (
    ROOT_DIR / "web" / "AGENTS.md",
    ROOT_DIR / "web" / "server_modules" / "AGENTS.md",
    ROOT_DIR / "web" / "app_modules" / "AGENTS.md",
    ROOT_DIR / "scripts" / "AGENTS.md",
    ROOT_DIR / "tests" / "AGENTS.md",
)

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts import agent_playbook_sync
from scripts import agent_profiles


@dataclass
class GardeningCheck:
    name: str
    status: str
    detail: str
    highlights: list[str]
    recommendations: list[str]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _relative_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT_DIR))
    except Exception:
        return str(path.resolve())


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _task_pointer_exists(base_dir: Path, task_name: str) -> bool:
    return (base_dir / str(task_name or "").strip() / "latest.json").exists()


def _build_check(
    name: str,
    status: str,
    detail: str,
    *,
    highlights: list[str] | None = None,
    recommendations: list[str] | None = None,
) -> GardeningCheck:
    return GardeningCheck(
        name=name,
        status=status,
        detail=detail,
        highlights=list(highlights or [])[:8],
        recommendations=list(recommendations or [])[:5],
    )


def _check_task_playbooks_synced() -> GardeningCheck:
    mismatches = agent_playbook_sync.check_task_playbooks()
    if mismatches:
        return _build_check(
            "task_playbooks_synced",
            "FAIL",
            f"drift={len(mismatches)}",
            highlights=mismatches,
            recommendations=[
                "先运行 python3 scripts/agent_playbook_sync.py，同步 task-backed playbook 文档。",
                "如果只改了单个 task，可使用 --task <name> 缩小同步范围，再复跑园丁报告。",
            ],
        )
    return _build_check(
        "task_playbooks_synced",
        "PASS",
        "all task-backed playbooks are in sync",
        highlights=["task-backed playbook 与 task 画像保持同步。"],
    )


def _check_doc_index_links() -> GardeningCheck:
    required = {
        AGENTS_FILE: [
            "docs/agent/heartbeat.md",
            "docs/agent/memory-notes.md",
            "ARCHITECTURE.md",
            "docs/agent/harness-iteration-plan-phase6.md",
            "python3 scripts/agent_ops.py status",
            "python3 scripts/agent_heartbeat.py",
            "python3 scripts/agent_autodream.py",
            "python3 scripts/agent_static_guardrails.py",
        ],
        AGENT_README_FILE: [
            "docs/agent/heartbeat.md",
            "docs/agent/memory-notes.md",
            "ARCHITECTURE.md",
            "docs/agent/harness-iteration-plan-phase6.md",
            "docs/agent/evaluator-calibration.md",
            "python3 scripts/agent_ops.py status",
            "python3 scripts/agent_heartbeat.py",
            "python3 scripts/agent_autodream.py",
            "python3 scripts/agent_static_guardrails.py",
        ],
        README_FILE: [
            "docs/agent/heartbeat.md",
            "docs/agent/memory-notes.md",
            "ARCHITECTURE.md",
            "Action for Agent",
            "python3 scripts/agent_ops.py status",
            "python3 scripts/agent_autodream.py",
        ],
    }
    missing: list[str] = []
    for path, snippets in required.items():
        text = _read_text(path)
        for snippet in snippets:
            if snippet not in text:
                missing.append(f"{_relative_path(path)} 缺少索引片段: {snippet}")
    if missing:
        return _build_check(
            "doc_index_links",
            "FAIL",
            f"missing={len(missing)}",
            highlights=missing,
            recommendations=[
                "补齐 AGENTS.md / docs/agent/README.md / README.md 中的入口链接和命令，避免园丁报告与实际入口漂移。",
                "如果 phase 状态有变化，更新 heartbeat 后再复核导航文档里的关键引用。",
            ],
        )
    return _build_check(
        "doc_index_links",
        "PASS",
        "key navigation docs include heartbeat/memory-notes/architecture/phase6 references",
        highlights=["入口文档已覆盖 heartbeat、memory-notes、ARCHITECTURE、phase6，以及 agent_ops / AutoDream Lite / 静态 guardrail 命令。"],
    )


def _check_hierarchical_agents_coverage() -> GardeningCheck:
    missing = [path for path in LOCAL_AGENT_FILES if not path.exists()]
    if missing:
        return _build_check(
            "hierarchical_agents_coverage",
            "WARN",
            f"required={len(LOCAL_AGENT_FILES)} materialized={len(LOCAL_AGENT_FILES) - len(missing)} missing={len(missing)}",
            highlights=[f"缺少局部 AGENTS: {_relative_path(path)}" for path in missing],
            recommendations=[
                "优先为 web/、web/server_modules/、web/app_modules/、scripts/、tests/ 补局部 AGENTS.md。",
                "局部 AGENTS 只写职责边界、禁止事项和复跑命令，不要复制根入口全文。",
            ],
        )
    return _build_check(
        "hierarchical_agents_coverage",
        "PASS",
        f"required={len(LOCAL_AGENT_FILES)} materialized={len(LOCAL_AGENT_FILES)}",
        highlights=["高频目录已具备局部 AGENTS.md，可按就近原则读取约束。"],
    )


def _check_contract_coverage() -> GardeningCheck:
    missing_contracts: list[str] = []
    high_risk_tasks = 0
    attached_contracts = 0
    for task_name in agent_profiles.list_task_names():
        profile = agent_profiles.get_task_profile(task_name)
        if str(profile.get("risk_level") or "").strip() != "high":
            continue
        high_risk_tasks += 1
        contract_name = str(profile.get("contract") or "").strip()
        if contract_name:
            contract_path = ROOT_DIR / "resources" / "harness" / "contracts" / f"{contract_name}.json"
            if contract_path.exists():
                attached_contracts += 1
                continue
        missing_contracts.append(task_name)
    if missing_contracts:
        return _build_check(
            "high_risk_contract_coverage",
            "WARN",
            f"high_risk={high_risk_tasks} covered={attached_contracts} missing={len(missing_contracts)}",
            highlights=[f"高风险 task 缺少 Sprint Contract: {name}" for name in missing_contracts],
            recommendations=[
                "优先为高风险 task 补 contract 元数据和 resources/harness/contracts/*.json，先覆盖真实写操作和回滚链路。",
                "补完 contract 后，再让 workflow / evaluator / handoff 共享同一份完成标准与证据要求。",
            ],
        )
    return _build_check(
        "high_risk_contract_coverage",
        "PASS",
        f"high_risk={high_risk_tasks} covered={attached_contracts}",
        highlights=["当前高风险 task 都已挂 Sprint Contract。"],
    )


def _check_planner_mission_materialization() -> GardeningCheck:
    planner_missing_pointer: list[str] = []
    mission_missing_pointer: list[str] = []
    planner_missing_meta: list[str] = []
    mission_missing_meta: list[str] = []
    task_count = 0
    planner_count = 0
    mission_count = 0
    for task_name in agent_profiles.list_task_names():
        task_count += 1
        profile = agent_profiles.get_task_profile(task_name)
        if isinstance(profile.get("planner"), dict):
            planner_count += 1
            if not _task_pointer_exists(PLANNER_TASK_INDEX_DIR, task_name):
                planner_missing_pointer.append(task_name)
        else:
            planner_missing_meta.append(task_name)
        if isinstance(profile.get("mission"), dict):
            mission_count += 1
            if not _task_pointer_exists(MISSION_TASK_INDEX_DIR, task_name):
                mission_missing_pointer.append(task_name)
        else:
            mission_missing_meta.append(task_name)
    if planner_missing_meta or mission_missing_meta or planner_missing_pointer or mission_missing_pointer:
        highlights: list[str] = []
        highlights.extend([f"planner 元数据缺失: {name}" for name in planner_missing_meta])
        highlights.extend([f"mission 元数据缺失: {name}" for name in mission_missing_meta])
        highlights.extend([f"planner 未物化 latest 指针: {name}" for name in planner_missing_pointer])
        highlights.extend([f"mission 未物化 latest 指针: {name}" for name in mission_missing_pointer])
        return _build_check(
            "planner_mission_materialization",
            "WARN",
            (
                f"tasks={task_count} planner={planner_count} planner_missing_meta={len(planner_missing_meta)} "
                f"planner_missing_pointer={len(planner_missing_pointer)} mission={mission_count} "
                f"mission_missing_meta={len(mission_missing_meta)} mission_missing_pointer={len(mission_missing_pointer)}"
            ),
            highlights=highlights,
            recommendations=[
                "先为缺失 task 补齐 planner / mission 元数据，保持一句话需求 -> plan -> workflow / evaluator 的统一入口。",
                '再对缺失 latest 指针的 task 运行 python3 scripts/agent_planner.py --task <name> --goal "<补充目标>" --artifact-dir artifacts/planner。',
            ],
        )
    return _build_check(
        "planner_mission_materialization",
        "PASS",
        f"tasks={task_count} planner={planner_count} mission={mission_count}",
        highlights=["全部内置 task 都已具备 planner / mission 元数据，且 latest 指针已物化。"],
    )


def _check_calibration_registry() -> GardeningCheck:
    calibration_dir = ROOT_DIR / "tests" / "harness_calibration"
    doc_text = _read_text(CALIBRATION_DOC_FILE)
    files = sorted(path.name for path in calibration_dir.glob("*.json"))
    missing = [name for name in files if name not in doc_text]
    if missing:
        return _build_check(
            "calibration_registry",
            "FAIL",
            f"samples={len(files)} undocumented={len(missing)}",
            highlights=[f"校准样本未写入 evaluator-calibration 文档: {name}" for name in missing],
            recommendations=[
                "在 docs/agent/evaluator-calibration.md 中补齐样本用途、适用场景和预期判定，避免样本存在但没人知道怎么用。",
            ],
        )
    return _build_check(
        "calibration_registry",
        "PASS",
        f"samples={len(files)} documented={len(files)}",
        highlights=["所有 evaluator 校准样本都已登记到 evaluator-calibration 文档。"],
    )


def build_doc_gardening_report() -> dict[str, Any]:
    checks = [
        _check_task_playbooks_synced(),
        _check_doc_index_links(),
        _check_hierarchical_agents_coverage(),
        _check_contract_coverage(),
        _check_planner_mission_materialization(),
        _check_calibration_registry(),
    ]
    summary = {
        "PASS": sum(1 for item in checks if item.status == "PASS"),
        "WARN": sum(1 for item in checks if item.status == "WARN"),
        "FAIL": sum(1 for item in checks if item.status == "FAIL"),
    }
    if summary["FAIL"] > 0:
        overall = "BLOCKED"
    elif summary["WARN"] > 0:
        overall = "ATTENTION_REQUIRED"
    else:
        overall = "HEALTHY"
    recommendations: list[str] = []
    for check in checks:
        for line in check.recommendations:
            if line not in recommendations:
                recommendations.append(line)
    return {
        "kind": "doc_gardening",
        "generated_at": utc_now_iso(),
        "overall": overall,
        "summary": summary,
        "checks": [asdict(item) for item in checks],
        "recommendations": recommendations[:8],
    }


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# DeepVision Doc Gardening Report",
        "",
        f"> 生成时间：{payload.get('generated_at', '')}",
        f"> Overall：`{payload.get('overall', '')}`",
        "",
        "## 汇总",
        "",
    ]
    summary = payload.get("summary", {}) if isinstance(payload.get("summary"), dict) else {}
    lines.extend(
        [
            f"- PASS：`{int(summary.get('PASS', 0) or 0)}`",
            f"- WARN：`{int(summary.get('WARN', 0) or 0)}`",
            f"- FAIL：`{int(summary.get('FAIL', 0) or 0)}`",
            "",
            "## 检查项",
            "",
        ]
    )
    for item in list(payload.get("checks", []) or []):
        if not isinstance(item, dict):
            continue
        lines.append(f"### {item.get('name', '')}")
        lines.append("")
        lines.append(f"- 状态：`{item.get('status', '')}`")
        lines.append(f"- 详情：{item.get('detail', '')}")
        highlights = [str(line or "").strip() for line in list(item.get("highlights", []) or []) if str(line or "").strip()]
        if highlights:
            lines.append("- 观察：")
            lines.extend([f"  - {line}" for line in highlights])
        recommendations = [str(line or "").strip() for line in list(item.get("recommendations", []) or []) if str(line or "").strip()]
        if recommendations:
            lines.append("- 建议：")
            lines.extend([f"  - {line}" for line in recommendations])
        lines.append("")
    recommendations = [str(line or "").strip() for line in list(payload.get("recommendations", []) or []) if str(line or "").strip()]
    if recommendations:
        lines.extend(["## 推荐动作", ""])
        lines.extend([f"- {line}" for line in recommendations])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_artifacts(payload: dict[str, Any], artifact_dir: Path) -> dict[str, str]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    json_path = artifact_dir / "latest.json"
    md_path = artifact_dir / "latest.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(payload), encoding="utf-8")
    return {
        "json_file": str(json_path.resolve()),
        "markdown_file": str(md_path.resolve()),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="生成 DeepVision harness 文档园丁一致性报告")
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR), help="报告输出目录")
    parser.add_argument("--json", action="store_true", help="输出 JSON 摘要")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_doc_gardening_report()
    artifact_info = write_artifacts(payload, Path(args.artifact_dir).expanduser().resolve())
    payload["artifacts"] = artifact_info
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("DeepVision agent doc gardening")
        print(f"overall: {payload.get('overall', '')}")
        print(
            "summary: PASS={PASS} WARN={WARN} FAIL={FAIL}".format(
                PASS=int(payload["summary"].get("PASS", 0) or 0),
                WARN=int(payload["summary"].get("WARN", 0) or 0),
                FAIL=int(payload["summary"].get("FAIL", 0) or 0),
            )
        )
        for item in list(payload.get("checks", []) or []):
            print(f"[{item.get('status', '')}] {item.get('name', '')}: {item.get('detail', '')}")
        print(f"[WRITE] {artifact_info['markdown_file']}")
        print(f"[WRITE] {artifact_info['json_file']}")
    return 2 if payload.get("overall") == "BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
