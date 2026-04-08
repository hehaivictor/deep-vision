#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
DeepVision harness 历史索引与 diff 入口。

目标：
1. 快速查看 harness / evaluator / CI artifact 最近跑了什么
2. 对比最近两次运行，定位 overall 与结果状态漂移
3. 为后续 observe 趋势面和 run dashboard 预留统一数据结构
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


TARGETS = {
    "harness": "artifacts/harness-runs",
    "evaluator": "artifacts/harness-eval",
    "ci-agent-smoke": "artifacts/ci/agent-smoke",
    "ci-guardrails": "artifacts/ci/guardrails",
    "ci-browser-smoke": "artifacts/ci/browser-smoke",
}


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def resolve_targets(kind: str, *, root_dir: Path = ROOT_DIR) -> dict[str, Path]:
    normalized = str(kind or "all").strip() or "all"
    if normalized == "all":
        return {name: (root_dir / rel).resolve() for name, rel in TARGETS.items()}
    if normalized not in TARGETS:
        raise KeyError(f"未知 history kind: {normalized}")
    return {normalized: (root_dir / TARGETS[normalized]).resolve()}


def _extract_subject(kind: str, payload: dict[str, Any]) -> str:
    if kind in {"harness", "ci-agent-smoke", "ci-guardrails"}:
        task_payload = payload.get("task", {}) if isinstance(payload.get("task", {}), dict) else {}
        return str(task_payload.get("name") or "").strip()
    if kind == "evaluator":
        filters = payload.get("filters", {}) if isinstance(payload.get("filters", {}), dict) else {}
        if list(filters.get("scenario_names", []) or []):
            return ",".join(str(item).strip() for item in list(filters["scenario_names"]) if str(item).strip())
        if list(filters.get("tags", []) or []):
            return "tags=" + ",".join(str(item).strip() for item in list(filters["tags"]) if str(item).strip())
        if list(filters.get("categories", []) or []):
            return "categories=" + ",".join(str(item).strip() for item in list(filters["categories"]) if str(item).strip())
    return ""


def _extract_result_statuses(payload: dict[str, Any]) -> dict[str, str]:
    statuses: dict[str, str] = {}
    for item in list(payload.get("results", []) or []):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        category = str(item.get("category") or "").strip()
        key = f"{category}/{name}" if category else name
        statuses[key] = str(item.get("status") or "").strip() or "UNKNOWN"
    return statuses


def _read_run_record(kind: str, run_dir: Path) -> dict[str, Any] | None:
    summary_path = run_dir / "summary.json"
    if not summary_path.exists():
        return None
    summary_payload = _load_json(summary_path)
    if not summary_payload:
        return None
    metadata = summary_payload.get("metadata", {}) if isinstance(summary_payload.get("metadata", {}), dict) else {}
    if not metadata:
        metadata = _load_json(run_dir / "run-meta.json")
    summary_counts = summary_payload.get("summary", {}) if isinstance(summary_payload.get("summary", {}), dict) else {}
    return {
        "kind": kind,
        "run_name": run_dir.name,
        "run_dir": str(run_dir),
        "generated_at": str(metadata.get("generated_at") or summary_payload.get("generated_at") or "").strip(),
        "overall": str(summary_payload.get("overall") or "").strip(),
        "summary": summary_counts,
        "subject": _extract_subject(kind, summary_payload),
        "results_count": len(list(summary_payload.get("results", []) or [])),
        "files": {
            "summary_file": str(summary_path),
            "progress_file": str(run_dir / "progress.md") if (run_dir / "progress.md").exists() else "",
            "failure_summary_file": str(run_dir / "failure-summary.md") if (run_dir / "failure-summary.md").exists() else "",
            "handoff_file": str(run_dir / "handoff.json") if (run_dir / "handoff.json").exists() else "",
        },
    }


def list_history_runs(
    kind: str,
    *,
    root_dir: Path = ROOT_DIR,
    limit: int = 5,
) -> list[dict[str, Any]]:
    targets = resolve_targets(kind, root_dir=root_dir)
    if len(targets) != 1:
        raise ValueError("list_history_runs 只支持单个 kind")
    target_kind, base_dir = next(iter(targets.items()))
    if not base_dir.exists():
        return []
    runs: list[dict[str, Any]] = []
    for child in sorted(base_dir.iterdir(), key=lambda path: path.name, reverse=True):
        if not child.is_dir():
            continue
        record = _read_run_record(target_kind, child)
        if record:
            runs.append(record)
        if len(runs) >= max(1, int(limit or 5)):
            break
    return runs


def build_history_index(
    *,
    kind: str = "all",
    root_dir: Path = ROOT_DIR,
    limit: int = 5,
) -> dict[str, Any]:
    targets = resolve_targets(kind, root_dir=root_dir)
    collections: dict[str, Any] = {}
    for target_kind in targets:
        runs = list_history_runs(target_kind, root_dir=root_dir, limit=limit)
        collections[target_kind] = {
            "kind": target_kind,
            "base_dir": str((root_dir / TARGETS[target_kind]).resolve()),
            "latest": runs[0] if runs else None,
            "runs": runs,
        }
    return {
        "generated_at": "",
        "root_dir": str(root_dir),
        "kind": kind,
        "limit": max(1, int(limit or 5)),
        "collections": collections,
    }


def _find_run_record(runs: list[dict[str, Any]], selector: str) -> dict[str, Any] | None:
    text = str(selector or "").strip()
    if not text:
        return None
    for item in runs:
        if text in {item["run_name"], item["run_dir"], Path(item["run_dir"]).name}:
            return item
    return None


def _summary_delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, int]:
    keys = sorted(set(before.keys()) | set(after.keys()))
    delta: dict[str, int] = {}
    for key in keys:
        before_value = int(before.get(key, 0) or 0)
        after_value = int(after.get(key, 0) or 0)
        delta[key] = after_value - before_value
    return delta


def build_history_diff(
    *,
    kind: str,
    root_dir: Path = ROOT_DIR,
    from_run: str = "",
    to_run: str = "",
) -> dict[str, Any]:
    runs = list_history_runs(kind, root_dir=root_dir, limit=200)
    if not runs:
        return {
            "kind": kind,
            "root_dir": str(root_dir),
            "overall": "EMPTY",
            "before": None,
            "after": None,
            "summary_delta": {},
            "changed_results": [],
        }

    after_record = _find_run_record(runs, to_run) if to_run else runs[0]
    before_record = _find_run_record(runs, from_run) if from_run else (runs[1] if len(runs) > 1 else None)
    if after_record is None or before_record is None:
        return {
            "kind": kind,
            "root_dir": str(root_dir),
            "overall": "INSUFFICIENT_HISTORY",
            "before": before_record,
            "after": after_record,
            "summary_delta": {},
            "changed_results": [],
        }

    before_payload = _load_json(Path(before_record["run_dir"]) / "summary.json")
    after_payload = _load_json(Path(after_record["run_dir"]) / "summary.json")
    before_statuses = _extract_result_statuses(before_payload)
    after_statuses = _extract_result_statuses(after_payload)

    changed_results: list[dict[str, Any]] = []
    for key in sorted(set(before_statuses) | set(after_statuses)):
        before_status = before_statuses.get(key, "MISSING")
        after_status = after_statuses.get(key, "MISSING")
        if before_status == after_status:
            continue
        changed_results.append(
            {
                "name": key,
                "before": before_status,
                "after": after_status,
            }
        )

    return {
        "kind": kind,
        "root_dir": str(root_dir),
        "overall": "CHANGED" if changed_results or before_record["overall"] != after_record["overall"] else "UNCHANGED",
        "before": before_record,
        "after": after_record,
        "overall_change": {
            "before": before_record["overall"],
            "after": after_record["overall"],
        },
        "summary_delta": _summary_delta(
            before_record.get("summary", {}) if isinstance(before_record.get("summary", {}), dict) else {},
            after_record.get("summary", {}) if isinstance(after_record.get("summary", {}), dict) else {},
        ),
        "changed_results": changed_results,
    }


def render_index(payload: dict[str, Any]) -> None:
    print("DeepVision agent history")
    print(f"仓库目录: {payload['root_dir']}")
    print("")
    for kind, collection in payload["collections"].items():
        latest = collection.get("latest")
        print(f"[{kind}] base={collection['base_dir']}")
        if not latest:
            print("  - 无历史运行")
            print("")
            continue
        print(
            f"  - latest: {latest['run_name']} | overall={latest['overall']} | "
            f"generated_at={latest['generated_at'] or '-'}"
        )
        if latest.get("subject"):
            print(f"  - subject: {latest['subject']}")
        for item in list(collection.get("runs", []) or [])[: payload["limit"]]:
            print(
                f"    * {item['run_name']} | overall={item['overall']} | "
                f"results={item['results_count']} | subject={item.get('subject') or '-'}"
            )
        print("")


def render_diff(payload: dict[str, Any]) -> None:
    print("DeepVision agent history diff")
    print(f"kind: {payload['kind']}")
    print(f"overall: {payload['overall']}")
    before = payload.get("before")
    after = payload.get("after")
    if not before or not after:
        print("历史不足，无法生成 diff。")
        return
    print(f"before: {before['run_name']} | overall={before['overall']}")
    print(f"after:  {after['run_name']} | overall={after['overall']}")
    print("")
    print("Summary Delta:")
    for key, value in payload.get("summary_delta", {}).items():
        print(f"- {key}: {value:+d}")
    print("")
    changed_results = list(payload.get("changed_results", []) or [])
    if not changed_results:
        print("结果状态没有变化。")
        return
    print("Changed Results:")
    for item in changed_results[:30]:
        print(f"- {item['name']}: {item['before']} -> {item['after']}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DeepVision harness 历史索引与 diff")
    parser.add_argument(
        "--kind",
        default="all",
        choices=["all", *TARGETS.keys()],
        help="选择查看的历史类别",
    )
    parser.add_argument("--limit", type=int, default=5, help="最多展示最近多少次运行")
    parser.add_argument("--diff", action="store_true", help="对比同一类别最近两次运行，或配合 --from-run/--to-run 指定")
    parser.add_argument("--from-run", default="", help="指定 diff 的 before 运行名或运行目录")
    parser.add_argument("--to-run", default="", help="指定 diff 的 after 运行名或运行目录")
    parser.add_argument("--root-dir", default=str(ROOT_DIR), help="仓库根目录，默认当前仓库")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root_dir = Path(str(args.root_dir or "").strip()).expanduser()
    if not root_dir.is_absolute():
        root_dir = (ROOT_DIR / root_dir).resolve()

    if args.diff:
        if args.kind == "all":
            raise SystemExit("--diff 仅支持单个 kind，请显式指定 --kind")
        payload = build_history_diff(
            kind=args.kind,
            root_dir=root_dir,
            from_run=args.from_run,
            to_run=args.to_run,
        )
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            render_diff(payload)
        return 0 if payload.get("overall") not in {"EMPTY"} else 1

    payload = build_history_index(
        kind=args.kind,
        root_dir=root_dir,
        limit=max(1, int(args.limit or 5)),
    )
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        render_index(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
