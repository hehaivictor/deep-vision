#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
DeepVision harness AutoDream Lite 巡检器。

目标：
1. 只刷新 heartbeat、doc gardener 和最近稳定经验摘要
2. 产出只读的运营面摘要，不自动修改业务代码或提交 PR
3. 让 phase6 可以通过单命令刷新当前导航、知识状态与稳定入口
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_AUTODREAM_DIR = ROOT_DIR / "artifacts" / "autodream"
DEFAULT_DOC_GARDENING_DIR = ROOT_DIR / "artifacts" / "doc-gardening"
DEFAULT_MEMORY_DIR = ROOT_DIR / "artifacts" / "memory"
DEFAULT_MEMORY_NOTES_PATH = ROOT_DIR / "docs" / "agent" / "memory-notes.md"
DEFAULT_HEARTBEAT_PATH = ROOT_DIR / "docs" / "agent" / "heartbeat.md"

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts import agent_doc_gardener
from scripts import agent_heartbeat


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _ensure_path(root_dir: Path, value: str) -> Path:
    path = Path(str(value or "").strip()).expanduser()
    if not path.is_absolute():
        path = (root_dir / path).resolve()
    return path


def _normalize_run_entries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    entries = [item for item in list(payload.get("latest_runs", []) or []) if isinstance(item, dict)]
    entries.sort(
        key=lambda item: (
            str(item.get("generated_at") or ""),
            str(item.get("kind") or ""),
        ),
        reverse=True,
    )
    return entries


def _stable_run_highlights(run_entries: list[dict[str, Any]]) -> list[str]:
    highlights: list[str] = []
    for item in run_entries:
        kind = str(item.get("kind") or "").strip()
        overall = str(item.get("overall") or "").strip()
        latest_json = str(item.get("latest_json") or "").strip()
        if kind == "harness" and overall in {"READY", "READY_WITH_WARNINGS"}:
            highlights.append(f"最近 harness 可用：优先复用 `{latest_json}` 对应的 latest 指针，再决定是否重新跑 `agent_harness.py --profile auto`。")
        elif kind == "evaluator" and overall in {"HEALTHY", "DEGRADED"}:
            highlights.append(f"最近 evaluator 已有有效产物：优先复用 `{latest_json}` 对应的 failure-summary / handoff，再决定是否补场景。")
        elif kind == "ci-browser-smoke" and overall == "READY":
            highlights.append("前端相关改动优先沿 browser smoke lane 验证，减少只靠 unittest 的盲区。")
        elif kind == "ci-agent-smoke" and overall == "READY":
            highlights.append("Runtime smoke 最近稳定，改动后优先走 `agent_harness.py --profile auto` 而不是单独挑命令。")
        elif kind == "ci-guardrails" and overall == "READY":
            highlights.append("关键不变量 gate 最近稳定，涉及高风险边界时优先先看 guardrails，再决定是否下钻到单测。")
    deduped: list[str] = []
    for item in highlights:
        if item not in deduped:
            deduped.append(item)
    return deduped[:5]


def _check_map(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("name") or "").strip(): item
        for item in list(payload.get("checks", []) or [])
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    }


def build_best_practices_payload(
    *,
    heartbeat_payload: dict[str, Any],
    gardening_payload: dict[str, Any],
) -> dict[str, Any]:
    active_phase = heartbeat_payload.get("active_phase", {}) if isinstance(heartbeat_payload.get("active_phase"), dict) else {}
    check_map = _check_map(gardening_payload)
    run_entries = _normalize_run_entries(heartbeat_payload)

    stable_practices: list[str] = [
        "先读 heartbeat 与就近 AGENTS，再决定进入哪个领域文档、task workflow 或 evaluator 场景。",
        "高风险 task 默认先走 workflow preview，并保留 artifact / handoff，而不是直接进入 apply 或裸跑脚本。",
    ]
    if str((check_map.get("task_playbooks_synced") or {}).get("status") or "").strip() == "PASS":
        stable_practices.append("修改 task 画像后先跑 `agent_playbook_sync.py --check` 和 `agent_doc_gardener.py`，避免 playbook 漂移。")
    if str((check_map.get("planner_mission_materialization") or {}).get("status") or "").strip() == "PASS":
        stable_practices.append("新增需求优先先生成 mission + planner latest 指针，再进入 workflow / evaluator，避免只留控制台历史。")
    if str((check_map.get("high_risk_contract_coverage") or {}).get("status") or "").strip() == "PASS":
        stable_practices.append("高风险 task 已有 Sprint Contract，默认按 contract 的 done_when / evidence_required 收口，而不是临时定义完成标准。")
    if str((check_map.get("hierarchical_agents_coverage") or {}).get("status") or "").strip() == "PASS":
        stable_practices.append("进入 `web/`、`web/server_modules/`、`web/app_modules/`、`scripts/`、`tests/` 时优先读取局部 AGENTS，减少上下文加载成本。")

    attention_items: list[str] = []
    if str(gardening_payload.get("overall") or "").strip() != "HEALTHY":
        for line in list(gardening_payload.get("recommendations", []) or [])[:4]:
            text = str(line or "").strip()
            if text:
                attention_items.append(text)
    for item in run_entries:
        overall = str(item.get("overall") or "").strip()
        if overall in {"BLOCKED", "FAIL", "EMPTY"}:
            attention_items.append(
                f"`{str(item.get('kind') or '-').strip()}` 当前为 `{overall}`，优先查看 `{str(item.get('latest_json') or '-').strip()}` 对应的 latest 指针。"
            )

    commands = [
        "python3 scripts/agent_autodream.py",
        "python3 scripts/agent_heartbeat.py",
        "python3 scripts/agent_doc_gardener.py",
        "python3 scripts/agent_harness.py --profile auto",
        "python3 scripts/agent_eval.py --tag nightly",
    ]

    return {
        "kind": "best_practices",
        "generated_at": utc_now_iso(),
        "active_phase": {
            "name": str(active_phase.get("name") or "").strip(),
            "current_priority": str(active_phase.get("current_priority") or "").strip(),
            "progress_file": str(active_phase.get("progress_file") or "").strip(),
            "plan_file": str(active_phase.get("plan_file") or "").strip(),
        },
        "stable_practices": stable_practices[:8],
        "stable_run_highlights": _stable_run_highlights(run_entries),
        "attention_items": attention_items[:6],
        "recommended_commands": commands,
        "pointers": {
            "heartbeat_markdown": "docs/agent/heartbeat.md",
            "heartbeat_json": "artifacts/memory/latest.json",
            "doc_gardening_markdown": "artifacts/doc-gardening/latest.md",
            "doc_gardening_json": "artifacts/doc-gardening/latest.json",
        },
    }


def render_best_practices_markdown(payload: dict[str, Any]) -> str:
    active_phase = payload.get("active_phase", {}) if isinstance(payload.get("active_phase"), dict) else {}
    lines = [
        "# DeepVision Memory Notes",
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
        "## 最近稳定经验",
        "",
    ]
    practices = [str(item or "").strip() for item in list(payload.get("stable_practices", []) or []) if str(item or "").strip()]
    lines.extend([f"- {item}" for item in practices] or ["- 暂无稳定经验摘要。"])
    lines.append("")

    run_highlights = [str(item or "").strip() for item in list(payload.get("stable_run_highlights", []) or []) if str(item or "").strip()]
    lines.extend(["## 最近健康指针", ""])
    lines.extend([f"- {item}" for item in run_highlights] or ["- 暂无可用的健康运行指针。"])
    lines.append("")

    attention_items = [str(item or "").strip() for item in list(payload.get("attention_items", []) or []) if str(item or "").strip()]
    lines.extend(["## 注意事项", ""])
    lines.extend([f"- {item}" for item in attention_items] or ["- 当前没有额外注意事项。"])
    lines.append("")

    lines.extend(["## 刷新命令", ""])
    lines.extend(
        [f"- `{item}`" for item in list(payload.get("recommended_commands", []) or []) if str(item or "").strip()]
        or ["- 暂无推荐命令。"]
    )
    lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_best_practices_artifacts(
    payload: dict[str, Any],
    *,
    root_dir: Path = ROOT_DIR,
    artifact_dir: str = str(DEFAULT_MEMORY_DIR.relative_to(ROOT_DIR)),
    output_markdown: str = str(DEFAULT_MEMORY_NOTES_PATH.relative_to(ROOT_DIR)),
) -> dict[str, str]:
    artifact_path = _ensure_path(root_dir, artifact_dir)
    artifact_path.mkdir(parents=True, exist_ok=True)

    markdown_path = _ensure_path(root_dir, output_markdown)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)

    json_path = artifact_path / "best-practices-latest.json"
    markdown_path.write_text(render_best_practices_markdown(payload), encoding="utf-8")
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "markdown_file": str(markdown_path.resolve()),
        "json_file": str(json_path.resolve()),
    }


def build_autodream_payload(
    *,
    gardening_payload: dict[str, Any],
    heartbeat_payload: dict[str, Any],
    best_practices_payload: dict[str, Any],
    gardening_outputs: dict[str, str],
    heartbeat_outputs: dict[str, str],
    best_practices_outputs: dict[str, str],
) -> dict[str, Any]:
    gardening_overall = str(gardening_payload.get("overall") or "").strip()
    if gardening_overall == "BLOCKED":
        overall = "BLOCKED"
    elif gardening_overall == "ATTENTION_REQUIRED":
        overall = "ATTENTION_REQUIRED"
    else:
        overall = "HEALTHY"
    return {
        "kind": "autodream_lite",
        "generated_at": utc_now_iso(),
        "overall": overall,
        "actions": [
            "只刷新 heartbeat / doc gardener / memory-notes，不自动修改业务代码或文档结构。",
            "如果发现 BLOCKED / ATTENTION_REQUIRED，优先把建议动作写回台账或下一轮任务，而不是由 AutoDream Lite 直接修复。",
        ],
        "doc_gardening": {
            "overall": gardening_overall,
            "summary": gardening_payload.get("summary", {}),
            "artifacts": gardening_outputs,
        },
        "heartbeat": {
            "active_phase": heartbeat_payload.get("active_phase", {}),
            "artifacts": heartbeat_outputs,
        },
        "best_practices": {
            "stable_practices": list(best_practices_payload.get("stable_practices", []) or []),
            "attention_items": list(best_practices_payload.get("attention_items", []) or []),
            "artifacts": best_practices_outputs,
        },
    }


def render_autodream_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# DeepVision AutoDream Lite",
        "",
        f"> 生成时间：{payload.get('generated_at', '')}",
        f"> Overall：`{payload.get('overall', '')}`",
        "",
        "## 已刷新输出",
        "",
    ]
    doc_gardening = payload.get("doc_gardening", {}) if isinstance(payload.get("doc_gardening"), dict) else {}
    heartbeat = payload.get("heartbeat", {}) if isinstance(payload.get("heartbeat"), dict) else {}
    best_practices = payload.get("best_practices", {}) if isinstance(payload.get("best_practices"), dict) else {}
    lines.append(f"- 文档园丁：`{str(doc_gardening.get('overall') or '-').strip() or '-'}`")
    lines.append(f"- heartbeat：`{str(((heartbeat.get('active_phase') or {}).get('current_priority') or '-')).strip() or '-'}`")
    lines.append(
        f"- memory-notes：稳定经验 `{len(list(best_practices.get('stable_practices', []) or []))}` 条 / 注意事项 `{len(list(best_practices.get('attention_items', []) or []))}` 条"
    )
    lines.append("")

    for title, block in (
        ("文档园丁 artifacts", doc_gardening.get("artifacts", {})),
        ("heartbeat artifacts", heartbeat.get("artifacts", {})),
        ("memory-notes artifacts", best_practices.get("artifacts", {})),
    ):
        if not isinstance(block, dict):
            continue
        lines.append(f"## {title}")
        lines.append("")
        for key, value in block.items():
            if str(value or "").strip():
                lines.append(f"- `{key}`: `{value}`")
        lines.append("")

    lines.extend(["## 执行约束", ""])
    for item in list(payload.get("actions", []) or []):
        lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_autodream_artifacts(payload: dict[str, Any], *, root_dir: Path = ROOT_DIR, artifact_dir: str = str(DEFAULT_AUTODREAM_DIR.relative_to(ROOT_DIR))) -> dict[str, str]:
    artifact_path = _ensure_path(root_dir, artifact_dir)
    artifact_path.mkdir(parents=True, exist_ok=True)
    json_path = artifact_path / "latest.json"
    markdown_path = artifact_path / "latest.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(render_autodream_markdown(payload), encoding="utf-8")
    return {
        "json_file": str(json_path.resolve()),
        "markdown_file": str(markdown_path.resolve()),
    }


def run_autodream_lite(
    *,
    root_dir: Path = ROOT_DIR,
    doc_gardening_dir: str = str(DEFAULT_DOC_GARDENING_DIR.relative_to(ROOT_DIR)),
    heartbeat_artifact_dir: str = str(DEFAULT_MEMORY_DIR.relative_to(ROOT_DIR)),
    heartbeat_markdown: str = str(DEFAULT_HEARTBEAT_PATH.relative_to(ROOT_DIR)),
    best_practices_artifact_dir: str = str(DEFAULT_MEMORY_DIR.relative_to(ROOT_DIR)),
    best_practices_markdown: str = str(DEFAULT_MEMORY_NOTES_PATH.relative_to(ROOT_DIR)),
    autodream_artifact_dir: str = str(DEFAULT_AUTODREAM_DIR.relative_to(ROOT_DIR)),
) -> tuple[dict[str, Any], dict[str, dict[str, str]]]:
    gardening_payload = agent_doc_gardener.build_doc_gardening_report()
    gardening_outputs = agent_doc_gardener.write_artifacts(gardening_payload, _ensure_path(root_dir, doc_gardening_dir))
    gardening_payload["artifacts"] = gardening_outputs

    heartbeat_payload = agent_heartbeat.build_heartbeat_payload(root_dir=root_dir)
    heartbeat_outputs = agent_heartbeat.write_heartbeat_artifacts(
        heartbeat_payload,
        root_dir=root_dir,
        artifact_dir=heartbeat_artifact_dir,
        output_markdown=heartbeat_markdown,
    )
    heartbeat_payload["artifacts"] = heartbeat_outputs

    best_practices_payload = build_best_practices_payload(
        heartbeat_payload=heartbeat_payload,
        gardening_payload=gardening_payload,
    )
    best_practices_outputs = write_best_practices_artifacts(
        best_practices_payload,
        root_dir=root_dir,
        artifact_dir=best_practices_artifact_dir,
        output_markdown=best_practices_markdown,
    )
    best_practices_payload["artifacts"] = best_practices_outputs

    autodream_payload = build_autodream_payload(
        gardening_payload=gardening_payload,
        heartbeat_payload=heartbeat_payload,
        best_practices_payload=best_practices_payload,
        gardening_outputs=gardening_outputs,
        heartbeat_outputs=heartbeat_outputs,
        best_practices_outputs=best_practices_outputs,
    )
    autodream_outputs = write_autodream_artifacts(
        autodream_payload,
        root_dir=root_dir,
        artifact_dir=autodream_artifact_dir,
    )
    autodream_payload["artifacts"] = autodream_outputs

    return autodream_payload, {
        "doc_gardening": gardening_outputs,
        "heartbeat": heartbeat_outputs,
        "best_practices": best_practices_outputs,
        "autodream": autodream_outputs,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="运行 DeepVision AutoDream Lite，只刷新 heartbeat / gardening / memory-notes")
    parser.add_argument("--doc-gardening-dir", default=str(DEFAULT_DOC_GARDENING_DIR.relative_to(ROOT_DIR)), help="文档园丁 artifact 输出目录")
    parser.add_argument("--heartbeat-artifact-dir", default=str(DEFAULT_MEMORY_DIR.relative_to(ROOT_DIR)), help="heartbeat JSON 输出目录")
    parser.add_argument("--heartbeat-markdown", default=str(DEFAULT_HEARTBEAT_PATH.relative_to(ROOT_DIR)), help="heartbeat markdown 输出路径")
    parser.add_argument("--best-practices-artifact-dir", default=str(DEFAULT_MEMORY_DIR.relative_to(ROOT_DIR)), help="稳定经验摘要 JSON 输出目录")
    parser.add_argument("--best-practices-markdown", default=str(DEFAULT_MEMORY_NOTES_PATH.relative_to(ROOT_DIR)), help="稳定经验摘要 markdown 输出路径")
    parser.add_argument("--artifact-dir", default=str(DEFAULT_AUTODREAM_DIR.relative_to(ROOT_DIR)), help="AutoDream Lite 汇总 artifact 输出目录")
    parser.add_argument("--json", action="store_true", help="输出 JSON 摘要")
    parser.add_argument("--dry-run", action="store_true", help="仅打印汇总 markdown，不写文件")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.dry_run:
        gardening_payload = agent_doc_gardener.build_doc_gardening_report()
        heartbeat_payload = agent_heartbeat.build_heartbeat_payload(root_dir=ROOT_DIR)
        best_practices_payload = build_best_practices_payload(
            heartbeat_payload=heartbeat_payload,
            gardening_payload=gardening_payload,
        )
        payload = build_autodream_payload(
            gardening_payload=gardening_payload,
            heartbeat_payload=heartbeat_payload,
            best_practices_payload=best_practices_payload,
            gardening_outputs={},
            heartbeat_outputs={},
            best_practices_outputs={},
        )
        print(render_autodream_markdown(payload))
        return 0

    payload, outputs = run_autodream_lite(
        root_dir=ROOT_DIR,
        doc_gardening_dir=args.doc_gardening_dir,
        heartbeat_artifact_dir=args.heartbeat_artifact_dir,
        heartbeat_markdown=args.heartbeat_markdown,
        best_practices_artifact_dir=args.best_practices_artifact_dir,
        best_practices_markdown=args.best_practices_markdown,
        autodream_artifact_dir=args.artifact_dir,
    )
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("DeepVision agent autodream lite")
        print(f"overall: {payload.get('overall', '')}")
        for title in ("doc_gardening", "heartbeat", "best_practices", "autodream"):
            for path in outputs.get(title, {}).values():
                print(f"[WRITE] {path}")
    return 2 if str(payload.get("overall") or "").strip() == "BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
