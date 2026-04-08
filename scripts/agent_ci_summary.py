#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
DeepVision CI 摘要生成器。

目标：
1. 从 latest.json / summary.json / handoff.json 生成短摘要
2. 让 GitHub Actions 不只上传 artifact，还能直接展示关键结论
3. 同时兼容 harness 与 evaluator 两类产物
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _format_summary_counts(summary: dict) -> str:
    if not isinstance(summary, dict):
        return "-"
    ordered_keys = ["PASS", "WARN", "FAIL", "SKIP", "FLAKY", "budget_exceeded", "scenarios_total", "attempts_total"]
    parts: list[str] = []
    used: set[str] = set()
    for key in ordered_keys:
        if key in summary:
            parts.append(f"{key}={summary[key]}")
            used.add(key)
    for key, value in summary.items():
        if key not in used:
            parts.append(f"{key}={value}")
    return " | ".join(parts) if parts else "-"


def _detect_kind(summary_payload: dict, handoff_payload: dict) -> str:
    handoff_kind = str(handoff_payload.get("kind") or "").strip().lower()
    if handoff_kind in {"harness", "evaluator"}:
        return handoff_kind
    results = summary_payload.get("results")
    if isinstance(results, list) and results and isinstance(results[0], dict) and "status" in results[0]:
        if "name" in results[0] and "category" in results[0]:
            return "evaluator"
        return "harness"
    return "unknown"


def _render_harness_results(results: list[dict], *, limit: int = 6) -> list[str]:
    lines: list[str] = []
    for item in results[:limit]:
        name = str(item.get("name") or "").strip() or "unknown"
        status = str(item.get("status") or "").strip() or "UNKNOWN"
        detail = str(item.get("detail") or "").strip()
        lines.append(f"- `{name}`: `{status}`" + (f" | {detail}" if detail else ""))
    return lines


def _render_eval_results(results: list[dict], *, limit: int = 6) -> list[str]:
    lines: list[str] = []
    for item in results[:limit]:
        name = str(item.get("name") or "").strip() or "unknown"
        status = str(item.get("status") or "").strip() or "UNKNOWN"
        detail = str(item.get("detail") or "").strip()
        lines.append(f"- `{name}`: `{status}`" + (f" | {detail}" if detail else ""))
    return lines


def render_summary_markdown(*, latest_payload: dict, summary_payload: dict, handoff_payload: dict, title: str = "") -> str:
    resolved_title = str(title or "").strip()
    if not resolved_title:
        resolved_title = "DeepVision CI Summary"

    kind = _detect_kind(summary_payload, handoff_payload)
    overall = str(latest_payload.get("overall") or summary_payload.get("overall") or handoff_payload.get("overall") or "").strip() or "UNKNOWN"
    generated_at = str(latest_payload.get("generated_at") or summary_payload.get("generated_at") or handoff_payload.get("generated_at") or "").strip()
    summary_counts = _format_summary_counts(summary_payload.get("summary") if isinstance(summary_payload.get("summary"), dict) else {})

    lines = [f"## {resolved_title}", ""]
    lines.append(f"- Overall: `{overall}`")
    if kind != "unknown":
        lines.append(f"- Kind: `{kind}`")
    if generated_at:
        lines.append(f"- Generated At: `{generated_at}`")
    run_name = str(latest_payload.get("run_name") or "").strip()
    if run_name:
        lines.append(f"- Run: `{run_name}`")
    lines.append(f"- Summary: {summary_counts}")

    results = summary_payload.get("results") if isinstance(summary_payload.get("results"), list) else []
    if results:
        lines.extend(["", "### Key Results"])
        if kind == "evaluator":
            lines.extend(_render_eval_results(results))
        else:
            lines.extend(_render_harness_results(results))

    blockers = [str(item).strip() for item in list(handoff_payload.get("blockers", []) or []) if str(item).strip()]
    todo = [str(item).strip() for item in list(handoff_payload.get("todo", []) or []) if str(item).strip()]
    next_steps = [str(item).strip() for item in list(handoff_payload.get("next_steps", []) or []) if str(item).strip()]

    if blockers or todo or next_steps:
        lines.extend(["", "### Action"])
        for item in blockers[:4]:
            lines.append(f"- Blocker: {item}")
        for item in todo[:4]:
            lines.append(f"- Todo: {item}")
        for item in next_steps[:4]:
            lines.append(f"- Next: {item}")

    failure_hotspots = summary_payload.get("failure_hotspots")
    if isinstance(failure_hotspots, list) and failure_hotspots:
        lines.extend(["", "### Failure Hotspots"])
        for item in failure_hotspots[:4]:
            if isinstance(item, dict):
                test_id = str(item.get("test_id") or item.get("name") or "").strip()
                failures = item.get("failures")
                attempts = item.get("attempts")
                detail_bits = []
                if failures is not None:
                    detail_bits.append(f"failures={failures}")
                if attempts is not None:
                    detail_bits.append(f"attempts={attempts}")
                suffix = f" | {' '.join(detail_bits)}" if detail_bits else ""
                lines.append(f"- `{test_id or 'unknown'}`{suffix}")

    pointers = handoff_payload.get("pointers") if isinstance(handoff_payload.get("pointers"), dict) else {}
    if pointers:
        lines.extend(["", "### Artifacts"])
        for key in ["summary_file", "progress_file", "failure_summary_file", "handoff_file", "latest_json"]:
            value = str(pointers.get(key) or latest_payload.get(key) or "").strip()
            if value:
                lines.append(f"- `{key}`: `{value}`")

    return "\n".join(lines).strip() + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="根据 latest.json 生成 GitHub Actions 可读摘要")
    parser.add_argument("--latest-json", required=True, help="latest.json 路径")
    parser.add_argument("--title", default="", help="摘要标题")
    parser.add_argument("--output", default="-", help="输出路径，默认 stdout")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    latest_path = Path(args.latest_json).resolve()
    if not latest_path.exists():
        parser.error(f"latest.json 不存在: {latest_path}")

    latest_payload = _read_json(latest_path)
    summary_file = Path(str(latest_payload.get("summary_file") or "")).resolve()
    handoff_file = Path(str(latest_payload.get("handoff_file") or "")).resolve()
    if not summary_file.exists():
        parser.error(f"summary.json 不存在: {summary_file}")
    if not handoff_file.exists():
        parser.error(f"handoff.json 不存在: {handoff_file}")

    summary_payload = _read_json(summary_file)
    handoff_payload = _read_json(handoff_file)
    markdown = render_summary_markdown(
        latest_payload=latest_payload,
        summary_payload=summary_payload,
        handoff_payload=handoff_payload,
        title=args.title,
    )

    if args.output == "-":
        sys.stdout.write(markdown)
    else:
        output_path = Path(args.output).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
