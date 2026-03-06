#!/usr/bin/env python3
"""
审计账号隔离风险（微信映射与会话归属）。

用途：
1. 检测 wechat_identities 是否存在重复映射（同 openid / unionid 对应多个账号）。
2. 检测 wechat_identities 是否存在孤儿映射（user_id 不存在）。
3. 检测 sessions 文件 owner_user_id 是否缺失/非法/不存在。

示例：
  python3 scripts/audit_identity_isolation.py
  python3 scripts/audit_identity_isolation.py --auth-db data/auth/users.db --sessions-dir data/sessions --write-json
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path


def resolve_project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def resolve_auth_db_path(project_root: Path, raw_auth_db: str) -> Path:
    if raw_auth_db:
        path = Path(raw_auth_db).expanduser()
        return path if path.is_absolute() else (project_root / path).resolve()

    env_path = str(os.environ.get("DEEPVISION_AUTH_DB_PATH", "")).strip()
    if env_path:
        path = Path(env_path).expanduser()
        return path if path.is_absolute() else (project_root / path).resolve()
    return (project_root / "data" / "auth" / "users.db").resolve()


def resolve_sessions_dir(project_root: Path, raw_sessions_dir: str) -> Path:
    if raw_sessions_dir:
        path = Path(raw_sessions_dir).expanduser()
        return path if path.is_absolute() else (project_root / path).resolve()
    return (project_root / "data" / "sessions").resolve()


def get_conn(auth_db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(auth_db_path))
    conn.row_factory = sqlite3.Row
    return conn


def query_scalar(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> int:
    row = conn.execute(sql, params).fetchone()
    if not row:
        return 0
    return int((row[0] if isinstance(row, tuple) else row[0]) or 0)


def fetch_user_ids(conn: sqlite3.Connection) -> set[int]:
    rows = conn.execute("SELECT id FROM users").fetchall()
    return {int(row["id"]) for row in rows}


def fetch_duplicate_wechat_openid(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT app_id, openid, COUNT(*) AS row_count, COUNT(DISTINCT user_id) AS user_count
        FROM wechat_identities
        GROUP BY app_id, openid
        HAVING COUNT(*) > 1 OR COUNT(DISTINCT user_id) > 1
        ORDER BY user_count DESC, row_count DESC
        """
    ).fetchall()
    result: list[dict] = []
    for row in rows:
        result.append(
            {
                "app_id": str(row["app_id"] or ""),
                "openid": str(row["openid"] or ""),
                "row_count": int(row["row_count"] or 0),
                "user_count": int(row["user_count"] or 0),
            }
        )
    return result


def fetch_duplicate_wechat_unionid(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT unionid, COUNT(*) AS row_count, COUNT(DISTINCT user_id) AS user_count
        FROM wechat_identities
        WHERE unionid IS NOT NULL AND TRIM(unionid) <> ''
        GROUP BY unionid
        HAVING COUNT(*) > 1 OR COUNT(DISTINCT user_id) > 1
        ORDER BY user_count DESC, row_count DESC
        """
    ).fetchall()
    result: list[dict] = []
    for row in rows:
        result.append(
            {
                "unionid": str(row["unionid"] or ""),
                "row_count": int(row["row_count"] or 0),
                "user_count": int(row["user_count"] or 0),
            }
        )
    return result


def fetch_orphan_wechat_identities(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT wi.id, wi.user_id, wi.app_id, wi.openid, COALESCE(wi.unionid, '') AS unionid
        FROM wechat_identities wi
        LEFT JOIN users u ON u.id = wi.user_id
        WHERE u.id IS NULL
        ORDER BY wi.id ASC
        """
    ).fetchall()
    result: list[dict] = []
    for row in rows:
        result.append(
            {
                "id": int(row["id"]),
                "user_id": int(row["user_id"]),
                "app_id": str(row["app_id"] or ""),
                "openid": str(row["openid"] or ""),
                "unionid": str(row["unionid"] or ""),
            }
        )
    return result


def audit_sessions_owner(sessions_dir: Path, valid_user_ids: set[int]) -> dict:
    report = {
        "total_files": 0,
        "invalid_json": [],
        "missing_owner": [],
        "owner_not_found": [],
    }
    if not sessions_dir.exists():
        return report

    for session_file in sorted(sessions_dir.glob("*.json")):
        report["total_files"] += 1
        try:
            payload = json.loads(session_file.read_text(encoding="utf-8"))
        except Exception:
            report["invalid_json"].append(session_file.name)
            continue

        owner_raw = payload.get("owner_user_id")
        try:
            owner_id = int(owner_raw)
        except (TypeError, ValueError):
            owner_id = 0

        if owner_id <= 0:
            report["missing_owner"].append(session_file.name)
            continue
        if owner_id not in valid_user_ids:
            report["owner_not_found"].append(
                {
                    "file": session_file.name,
                    "owner_user_id": owner_id,
                    "session_id": str(payload.get("session_id") or ""),
                }
            )
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="审计账号隔离风险（微信映射 + 会话归属）")
    parser.add_argument("--auth-db", default="", help="用户库路径，默认 data/auth/users.db 或 DEEPVISION_AUTH_DB_PATH")
    parser.add_argument("--sessions-dir", default="", help="会话目录，默认 data/sessions")
    parser.add_argument("--write-json", action="store_true", help="将审计结果写入 data/operations")
    parser.add_argument("--json-path", default="", help="自定义 JSON 输出路径（配合 --write-json）")
    parser.add_argument("--fail-on-issues", action="store_true", help="发现高风险问题时返回非 0 退出码")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_root = resolve_project_root()
    auth_db_path = resolve_auth_db_path(project_root, args.auth_db)
    sessions_dir = resolve_sessions_dir(project_root, args.sessions_dir)

    if not auth_db_path.exists():
        print(f"[ERROR] 用户库不存在: {auth_db_path}")
        return 2

    with get_conn(auth_db_path) as conn:
        users_count = query_scalar(conn, "SELECT COUNT(1) FROM users")
        wechat_count = query_scalar(conn, "SELECT COUNT(1) FROM wechat_identities")
        valid_user_ids = fetch_user_ids(conn)
        dup_openid = fetch_duplicate_wechat_openid(conn)
        dup_unionid = fetch_duplicate_wechat_unionid(conn)
        orphan_identities = fetch_orphan_wechat_identities(conn)

    sessions_audit = audit_sessions_owner(sessions_dir, valid_user_ids)

    result = {
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "auth_db_path": str(auth_db_path),
        "sessions_dir": str(sessions_dir),
        "summary": {
            "users_count": users_count,
            "wechat_identities_count": wechat_count,
            "wechat_duplicate_openid_groups": len(dup_openid),
            "wechat_duplicate_unionid_groups": len(dup_unionid),
            "wechat_orphan_identity_count": len(orphan_identities),
            "sessions_total_files": int(sessions_audit["total_files"]),
            "sessions_invalid_json_count": len(sessions_audit["invalid_json"]),
            "sessions_missing_owner_count": len(sessions_audit["missing_owner"]),
            "sessions_owner_not_found_count": len(sessions_audit["owner_not_found"]),
        },
        "wechat": {
            "duplicate_openid_groups": dup_openid,
            "duplicate_unionid_groups": dup_unionid,
            "orphan_identities": orphan_identities,
        },
        "sessions": sessions_audit,
    }

    print("=== DeepVision 账号隔离审计 ===")
    print(f"auth_db: {auth_db_path}")
    print(f"sessions: {sessions_dir}")
    print("")
    print("[摘要]")
    for key, value in result["summary"].items():
        print(f"- {key}: {value}")

    high_risk_issue_count = (
        len(dup_openid)
        + len(dup_unionid)
        + len(orphan_identities)
        + len(sessions_audit["owner_not_found"])
    )
    has_high_risk = high_risk_issue_count > 0
    if has_high_risk:
        print("")
        print("[高风险] 发现可能导致串号的数据问题，请优先处理。")
    else:
        print("")
        print("[高风险] 未发现。")

    if args.write_json:
        if args.json_path:
            output_path = Path(args.json_path).expanduser()
            if not output_path.is_absolute():
                output_path = (project_root / output_path).resolve()
        else:
            output_dir = (project_root / "data" / "operations").resolve()
            output_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d-%H%M%S")
            output_path = output_dir / f"identity-isolation-audit-{ts}.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[输出] 已写入: {output_path}")

    if args.fail_on_issues and has_high_risk:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
