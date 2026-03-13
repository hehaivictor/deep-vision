#!/usr/bin/env python3
"""
历史会话证据标注迁移工具

默认 dry-run，仅输出将发生的变更；传入 --apply 才会落盘。
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Iterable, Optional


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


def ensure_backup_dir(backup_dir: Optional[str]) -> Optional[Path]:
    if not backup_dir:
        return None
    target = Path(backup_dir).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    return target


def backup_session_file(session_file: Path, backup_dir: Path) -> Path:
    backup_path = backup_dir / session_file.name
    shutil.copy2(session_file, backup_path)
    return backup_path


def backfill_session_files(
    session_files: Iterable[Path],
    *,
    apply_changes: bool = False,
    backup_dir: Optional[Path] = None,
    server_module=None,
) -> dict:
    server = server_module or load_server_module()
    summary = {
        "sessions_total": 0,
        "sessions_changed": 0,
        "logs_total": 0,
        "logs_updated": 0,
        "field_updates": {},
        "changed_sessions": [],
    }

    for session_file in session_files:
        session_data = json.loads(session_file.read_text(encoding="utf-8"))
        result = server.backfill_session_interview_log_evidence_annotations(
            session_data,
            refresh_quality=True,
            overwrite_contract=False,
        )
        summary["sessions_total"] += 1
        summary["logs_total"] += int(result.get("logs_total", 0) or 0)
        summary["logs_updated"] += int(result.get("logs_updated", 0) or 0)

        for field, count in (result.get("field_updates", {}) or {}).items():
            summary["field_updates"][field] = summary["field_updates"].get(field, 0) + int(count or 0)

        if result.get("changed"):
            summary["sessions_changed"] += 1
            session_entry = {
                "session_id": session_data.get("session_id", session_file.stem),
                "topic": session_data.get("topic", ""),
                "logs_updated": int(result.get("logs_updated", 0) or 0),
                "field_updates": dict(result.get("field_updates", {}) or {}),
            }
            summary["changed_sessions"].append(session_entry)

            if apply_changes:
                if backup_dir is not None:
                    backup_session_file(session_file, backup_dir)
                session_data["updated_at"] = server.get_utc_now()
                session_file.write_text(
                    json.dumps(session_data, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="批量回填历史会话的 evidence 契约、质量字段与 answer_evidence_class",
    )
    parser.add_argument("session_ids", nargs="*", help="指定会话 ID；为空时需配合 --all")
    parser.add_argument("--all", action="store_true", help="处理 data/sessions 下的全部会话")
    parser.add_argument("--apply", action="store_true", help="确认落盘；默认 dry-run")
    parser.add_argument("--backup-dir", default="", help="落盘前的备份目录，仅 --apply 时生效")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出摘要")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if not args.all and not args.session_ids:
        parser.error("请提供至少一个 session_id，或使用 --all")

    session_dir = get_session_dir()
    backup_dir = ensure_backup_dir(args.backup_dir) if args.apply else None
    session_files = resolve_target_session_files(session_dir, args.session_ids, args.all)
    summary = backfill_session_files(
        session_files,
        apply_changes=bool(args.apply),
        backup_dir=backup_dir,
    )

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        mode = "APPLY" if args.apply else "DRY-RUN"
        print(f"[{mode}] 会话总数: {summary['sessions_total']}")
        print(f"[{mode}] 发生变更: {summary['sessions_changed']}")
        print(f"[{mode}] 处理日志: {summary['logs_total']}，更新日志: {summary['logs_updated']}")
        if summary["field_updates"]:
            print(f"[{mode}] 字段变更: {json.dumps(summary['field_updates'], ensure_ascii=False)}")
        for item in summary["changed_sessions"][:20]:
            print(
                f"- {item['session_id']} | {item['topic']} | "
                f"logs_updated={item['logs_updated']} | fields={json.dumps(item['field_updates'], ensure_ascii=False)}"
            )
        if summary["sessions_changed"] > 20:
            print(f"... 其余 {summary['sessions_changed'] - 20} 个会话未展开")
        if args.apply and backup_dir is not None:
            print(f"[APPLY] 备份目录: {backup_dir}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
