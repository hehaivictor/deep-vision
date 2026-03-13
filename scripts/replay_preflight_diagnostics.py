#!/usr/bin/env python3
"""
访谈中途预检离线回放诊断工具

用途：
1. 用历史会话模拟当前 evidence ledger / mid-interview preflight 链路
2. 统计预检触发次数、被冷却拦截次数和按维度分布
3. 输出首个触发点和若干条关键事件，便于判断访谈是否被过度打断
"""

from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Iterable


def get_script_dir() -> Path:
    return Path(__file__).parent.resolve()


def get_session_dir() -> Path:
    session_dir = get_script_dir().parent / "data" / "sessions"
    session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir


def load_server_module():
    root_dir = get_script_dir().parent
    if str(root_dir) not in sys.path:
        sys.path.insert(0, str(root_dir))
    import web.server as server  # noqa: WPS433

    return server


def resolve_target_session_files(session_dir: Path, session_ids: list[str], include_all: bool) -> list[Path]:
    if include_all:
        return sorted(session_dir.glob("*.json"))

    targets = []
    for session_id in session_ids:
        session_file = session_dir / f"{session_id}.json"
        if not session_file.exists():
            raise FileNotFoundError(f"会话不存在: {session_id}")
        targets.append(session_file)
    return targets


def _append_count(counter: dict, key: str) -> None:
    text = str(key or "").strip()
    if not text:
        return
    counter[text] = counter.get(text, 0) + 1


def simulate_session_preflight(session_data: dict, *, server_module=None, max_events: int = 12) -> dict:
    server = server_module or load_server_module()
    session = deepcopy(session_data) if isinstance(session_data, dict) else {}
    logs = session.get("interview_log", [])
    if not isinstance(logs, list):
        logs = []

    rolling_session = deepcopy(session)
    rolling_session["interview_log"] = []
    triggered_events = []
    throttled_events = []
    by_dimension = {}
    last_plan = None

    for index, raw_log in enumerate(logs, 1):
        current_log = deepcopy(raw_log) if isinstance(raw_log, dict) else {}
        if last_plan and last_plan.get("should_intervene"):
            current_log["preflight_intervened"] = True
            current_log["preflight_fingerprint"] = last_plan.get("fingerprint", "")
            current_log["preflight_planner_mode"] = last_plan.get("planner_mode", "")
            current_log["preflight_probe_slots"] = list(last_plan.get("probe_slots", []) or [])

        rolling_session["interview_log"].append(current_log)
        dimension = str(current_log.get("dimension", "") or "").strip()
        ledger = server.build_session_evidence_ledger(rolling_session)
        plan = server.plan_mid_interview_preflight(rolling_session, dimension, ledger=ledger)

        if plan.get("cooldown_suppressed"):
            throttled_events.append(
                {
                    "index": index,
                    "dimension": dimension,
                    "reason": plan.get("cooldown_reason", ""),
                    "probe_slots": list(plan.get("probe_slots", []) or []),
                }
            )

        if plan.get("should_intervene"):
            _append_count(by_dimension, dimension)
            triggered_events.append(
                {
                    "index": index,
                    "dimension": dimension,
                    "planner_mode": plan.get("planner_mode", ""),
                    "reason": plan.get("reason", ""),
                    "probe_slots": list(plan.get("probe_slots", []) or []),
                    "force_follow_up": bool(plan.get("force_follow_up", False)),
                    "fingerprint": plan.get("fingerprint", ""),
                }
            )

        last_plan = plan

    return {
        "session_id": session.get("session_id", ""),
        "topic": session.get("topic", ""),
        "trigger_total": len(triggered_events),
        "throttled_total": len(throttled_events),
        "by_dimension": by_dimension,
        "first_trigger": triggered_events[0] if triggered_events else None,
        "triggered_events": triggered_events[:max(0, int(max_events))],
        "throttled_events": throttled_events[:max(0, int(max_events))],
    }


def simulate_session_files(
    session_files: Iterable[Path],
    *,
    server_module=None,
    max_events: int = 12,
) -> dict:
    server = server_module or load_server_module()
    results = []
    for session_file in session_files:
        session_data = json.loads(session_file.read_text(encoding="utf-8"))
        results.append(
            simulate_session_preflight(
                session_data,
                server_module=server,
                max_events=max_events,
            )
        )

    return {
        "sessions_total": len(results),
        "results": results,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="回放历史会话，诊断 mid-interview preflight 的触发与节流行为",
    )
    parser.add_argument("session_ids", nargs="*", help="指定会话 ID；为空时需配合 --all")
    parser.add_argument("--all", action="store_true", help="处理 data/sessions 下的全部会话")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出摘要")
    parser.add_argument("--max-events", type=int, default=12, help="每个会话最多输出多少条事件")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if not args.all and not args.session_ids:
        parser.error("请提供至少一个 session_id，或使用 --all")

    session_dir = get_session_dir()
    session_files = resolve_target_session_files(session_dir, args.session_ids, args.all)
    summary = simulate_session_files(session_files, max_events=max(1, int(args.max_events)))

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    print(f"会话总数: {summary['sessions_total']}")
    for result in summary["results"]:
        print(f"- {result['session_id']} | {result['topic']}")
        print(
            f"  trigger_total={result['trigger_total']} | "
            f"throttled_total={result['throttled_total']} | "
            f"by_dimension={json.dumps(result['by_dimension'], ensure_ascii=False)}"
        )
        if result.get("first_trigger"):
            print(f"  first_trigger={json.dumps(result['first_trigger'], ensure_ascii=False)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
