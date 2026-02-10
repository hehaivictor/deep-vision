#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
DeepVision 管理员归属迁移脚本

用途：
1) 手动将历史会话/报告批量归属到指定用户
2) 规避“首次访问自动归属”带来的运营不确定性
3) 提供 dry-run 预览、落盘备份、可回滚能力

示例：
  # 1) 查看可选用户
  python3 scripts/admin_migrate_ownership.py list-users

  # 2) 预览：将所有无归属数据迁移给手机号账号
  python3 scripts/admin_migrate_ownership.py migrate \
    --to-account 13770696032 \
    --scope unowned

  # 3) 执行：落盘迁移并自动生成备份目录
  python3 scripts/admin_migrate_ownership.py migrate \
    --to-account 13770696032 \
    --scope unowned \
    --apply

  # 4) 使用备份目录回滚
  python3 scripts/admin_migrate_ownership.py rollback \
    --backup-dir data/operations/ownership-migrations/20260210-142200-to-1
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
SESSIONS_DIR = DATA_DIR / "sessions"
REPORTS_DIR = DATA_DIR / "reports"
AUTH_DIR = DATA_DIR / "auth"
REPORT_OWNERS_FILE = REPORTS_DIR / ".owners.json"
DEFAULT_AUTH_DB_PATH = AUTH_DIR / "users.db"
DEFAULT_BACKUP_ROOT = DATA_DIR / "operations" / "ownership-migrations"

AUTH_EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
AUTH_PHONE_PATTERN = re.compile(r"^1\d{10}$")


class Color:
    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    YELLOW = "\033[1;33m"
    BLUE = "\033[0;34m"
    NC = "\033[0m"


def log_info(message: str) -> None:
    print(f"{Color.GREEN}[INFO]{Color.NC} {message}")


def log_warn(message: str) -> None:
    print(f"{Color.YELLOW}[WARN]{Color.NC} {message}")


def log_error(message: str) -> None:
    print(f"{Color.RED}[ERROR]{Color.NC} {message}")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def utc_now_tag() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def parse_owner_id(raw_owner: Any) -> int:
    try:
        owner_id = int(raw_owner)
    except (TypeError, ValueError):
        return 0
    return owner_id if owner_id > 0 else 0


def normalize_phone_number(raw_phone: str) -> str:
    normalized = re.sub(r"[\s-]", "", raw_phone or "")
    if normalized.startswith("+86"):
        normalized = normalized[3:]
    elif normalized.startswith("86") and len(normalized) == 13:
        normalized = normalized[2:]
    return normalized


def normalize_account(account: str) -> tuple[Optional[str], Optional[str], str]:
    account_text = str(account or "").strip()
    if not account_text:
        return None, None, "账号不能为空"

    if "@" in account_text:
        email = account_text.lower()
        if not AUTH_EMAIL_PATTERN.match(email):
            return None, None, "请输入有效的邮箱地址"
        return email, None, ""

    phone = normalize_phone_number(account_text)
    if not AUTH_PHONE_PATTERN.match(phone):
        return None, None, "请输入有效的手机号（中国大陆 11 位）"
    return None, phone, ""


def resolve_auth_db_path(raw_auth_db: str) -> Path:
    env_path = os.environ.get("DEEPVISION_AUTH_DB_PATH", "")
    input_path = str(raw_auth_db or "").strip() or env_path
    path = Path(input_path).expanduser() if input_path else DEFAULT_AUTH_DB_PATH
    if not path.is_absolute():
        path = (ROOT_DIR / path).resolve()
    return path


def get_auth_db_connection(auth_db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(auth_db_path)
    conn.row_factory = sqlite3.Row
    return conn


def query_user_by_id(auth_db_path: Path, user_id: int) -> Optional[sqlite3.Row]:
    with get_auth_db_connection(auth_db_path) as conn:
        return conn.execute(
            "SELECT id, email, phone, created_at FROM users WHERE id = ? LIMIT 1",
            (int(user_id),),
        ).fetchone()


def query_user_by_account(auth_db_path: Path, account: str) -> Optional[sqlite3.Row]:
    email, phone, account_error = normalize_account(account)
    if account_error:
        raise ValueError(account_error)

    with get_auth_db_connection(auth_db_path) as conn:
        if email:
            return conn.execute(
                "SELECT id, email, phone, created_at FROM users WHERE email = ? LIMIT 1",
                (email,),
            ).fetchone()
        if phone:
            return conn.execute(
                "SELECT id, email, phone, created_at FROM users WHERE phone = ? LIMIT 1",
                (phone,),
            ).fetchone()
    return None


def list_users(auth_db_path: Path, limit: int) -> int:
    if not auth_db_path.exists():
        log_error(f"用户数据库不存在: {auth_db_path}")
        return 2

    with get_auth_db_connection(auth_db_path) as conn:
        rows = conn.execute(
            "SELECT id, email, phone, created_at FROM users ORDER BY id ASC LIMIT ?",
            (max(1, int(limit)),),
        ).fetchall()

    if not rows:
        log_warn("users 表为空，没有可选目标用户")
        return 0

    print(f"{Color.BLUE}{'━' * 86}{Color.NC}")
    print(f"{'user_id':<10} {'账号(account)':<34} {'邮箱':<24} {'手机号':<16}")
    print(f"{Color.BLUE}{'━' * 86}{Color.NC}")
    for row in rows:
        email = row["email"] or ""
        phone = row["phone"] or ""
        account = email or phone
        print(f"{int(row['id']):<10} {account:<34} {email:<24} {phone:<16}")
    print(f"{Color.BLUE}{'━' * 86}{Color.NC}")
    print(f"共 {len(rows)} 条")
    return 0


def load_report_owners(path: Path) -> dict[str, int]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

    if not isinstance(payload, dict):
        return {}

    normalized: dict[str, int] = {}
    for name, owner in payload.items():
        if not isinstance(name, str):
            continue
        owner_id = parse_owner_id(owner)
        if owner_id <= 0:
            continue
        normalized[name] = owner_id
    return normalized


def save_report_owners(path: Path, owners: dict[str, int]) -> None:
    sorted_items = sorted(owners.items(), key=lambda x: x[0])
    payload = {name: int(owner_id) for name, owner_id in sorted_items}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_kinds(raw_kinds: str) -> set[str]:
    tokens = [token.strip().lower() for token in str(raw_kinds or "").split(",") if token.strip()]
    if not tokens:
        tokens = ["sessions", "reports"]

    mapping = {
        "session": "sessions",
        "sessions": "sessions",
        "report": "reports",
        "reports": "reports",
    }

    kinds: set[str] = set()
    for token in tokens:
        if token not in mapping:
            raise ValueError(f"无效 --kinds 取值: {token}（允许: sessions,reports）")
        kinds.add(mapping[token])
    return kinds


def should_migrate_owner(owner_id: int, target_user_id: int, scope: str, from_user_id: Optional[int]) -> bool:
    if scope == "unowned":
        return owner_id <= 0

    if scope == "all":
        return owner_id != int(target_user_id)

    if scope == "from-user":
        return owner_id == int(from_user_id or 0) and owner_id != int(target_user_id)

    return False


def resolve_target_user(auth_db_path: Path, to_user_id: Optional[int], to_account: str) -> dict[str, Any]:
    if not auth_db_path.exists():
        raise RuntimeError(f"用户数据库不存在: {auth_db_path}")

    if to_user_id is not None:
        row = query_user_by_id(auth_db_path, int(to_user_id))
    else:
        row = query_user_by_account(auth_db_path, to_account)

    if not row:
        raise RuntimeError("目标用户不存在，请先使用 list-users 确认用户")

    return {
        "id": int(row["id"]),
        "email": row["email"] or "",
        "phone": row["phone"] or "",
        "account": (row["email"] or row["phone"] or ""),
        "created_at": row["created_at"],
    }


def prepare_backup_dir(backup_dir_arg: str, target_user_id: int, apply_mode: bool) -> Optional[Path]:
    if not apply_mode:
        return None

    if str(backup_dir_arg or "").strip():
        backup_dir = Path(backup_dir_arg).expanduser()
    else:
        backup_dir = DEFAULT_BACKUP_ROOT / f"{utc_now_tag()}-to-{int(target_user_id)}"

    if not backup_dir.is_absolute():
        backup_dir = (ROOT_DIR / backup_dir).resolve()

    if backup_dir.exists():
        existing = list(backup_dir.iterdir())
        if existing:
            raise RuntimeError(f"备份目录已存在且非空: {backup_dir}")
    else:
        backup_dir.mkdir(parents=True, exist_ok=True)

    (backup_dir / "sessions").mkdir(parents=True, exist_ok=True)
    (backup_dir / "reports").mkdir(parents=True, exist_ok=True)
    return backup_dir


def backup_file_once(src: Path, dest: Path) -> None:
    if dest.exists():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)


def run_migrate(args: argparse.Namespace) -> int:
    try:
        kinds = parse_kinds(args.kinds)
    except ValueError as exc:
        log_error(str(exc))
        return 2

    if args.scope == "from-user" and args.from_user_id is None:
        log_error("scope=from-user 时必须提供 --from-user-id")
        return 2

    auth_db_path = resolve_auth_db_path(args.auth_db)

    try:
        target_user = resolve_target_user(auth_db_path, args.to_user_id, args.to_account)
    except Exception as exc:
        log_error(str(exc))
        return 2

    target_user_id = int(target_user["id"])
    apply_mode = bool(args.apply)

    if args.scope == "from-user" and int(args.from_user_id) == target_user_id:
        log_warn("from_user_id 与目标用户相同，本次迁移不会产生变更")

    if not SESSIONS_DIR.exists() or not REPORTS_DIR.exists():
        log_error("data 目录结构不完整，请确认在项目根目录执行")
        return 2

    try:
        backup_dir = prepare_backup_dir(args.backup_dir, target_user_id, apply_mode)
    except Exception as exc:
        log_error(f"初始化备份目录失败: {exc}")
        return 2

    summary: dict[str, Any] = {
        "generated_at": utc_now_iso(),
        "mode": "apply" if apply_mode else "dry-run",
        "scope": args.scope,
        "from_user_id": int(args.from_user_id) if args.from_user_id is not None else None,
        "kinds": sorted(list(kinds)),
        "target_user": target_user,
        "auth_db_path": str(auth_db_path),
        "backup_dir": str(backup_dir) if backup_dir else None,
        "sessions": {
            "scanned": 0,
            "matched": 0,
            "updated": 0,
            "skipped_invalid": 0,
            "examples": [],
        },
        "reports": {
            "scanned": 0,
            "matched": 0,
            "updated": 0,
            "examples": [],
        },
    }

    sessions_examples: list[dict[str, Any]] = []
    reports_examples: list[dict[str, Any]] = []

    # 迁移 sessions
    if "sessions" in kinds:
        for session_file in sorted(SESSIONS_DIR.glob("*.json")):
            summary["sessions"]["scanned"] += 1
            try:
                data = json.loads(session_file.read_text(encoding="utf-8"))
            except Exception:
                summary["sessions"]["skipped_invalid"] += 1
                continue

            if not isinstance(data, dict):
                summary["sessions"]["skipped_invalid"] += 1
                continue

            current_owner = parse_owner_id(data.get("owner_user_id"))
            should_migrate = should_migrate_owner(
                current_owner,
                target_user_id,
                args.scope,
                args.from_user_id,
            )
            if not should_migrate:
                continue

            summary["sessions"]["matched"] += 1
            summary["sessions"]["updated"] += 1

            session_example = {
                "session_file": session_file.name,
                "session_id": data.get("session_id") or session_file.stem,
                "from_owner": current_owner,
                "to_owner": target_user_id,
            }
            if len(sessions_examples) < int(args.max_examples):
                sessions_examples.append(session_example)

            if apply_mode and backup_dir:
                backup_file_once(session_file, backup_dir / "sessions" / session_file.name)
                data["owner_user_id"] = target_user_id
                session_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    # 迁移 reports owner map
    if "reports" in kinds:
        owners = load_report_owners(REPORT_OWNERS_FILE)

        report_files = sorted(REPORTS_DIR.glob("*.md"))
        for report_file in report_files:
            report_name = report_file.name
            summary["reports"]["scanned"] += 1
            current_owner = parse_owner_id(owners.get(report_name, 0))

            should_migrate = should_migrate_owner(
                current_owner,
                target_user_id,
                args.scope,
                args.from_user_id,
            )
            if not should_migrate:
                continue

            summary["reports"]["matched"] += 1
            summary["reports"]["updated"] += 1

            report_example = {
                "report_name": report_name,
                "from_owner": current_owner,
                "to_owner": target_user_id,
            }
            if len(reports_examples) < int(args.max_examples):
                reports_examples.append(report_example)

            if apply_mode:
                owners[report_name] = target_user_id

        if apply_mode and summary["reports"]["updated"] > 0:
            if backup_dir:
                owners_backup = backup_dir / "reports" / ".owners.json"
                owners_absent_marker = backup_dir / "reports" / ".owners.absent"
                if REPORT_OWNERS_FILE.exists():
                    backup_file_once(REPORT_OWNERS_FILE, owners_backup)
                elif not owners_absent_marker.exists():
                    owners_absent_marker.write_text("absent\n", encoding="utf-8")

            save_report_owners(REPORT_OWNERS_FILE, owners)

    summary["sessions"]["examples"] = sessions_examples
    summary["reports"]["examples"] = reports_examples

    if apply_mode and backup_dir:
        metadata_file = backup_dir / "metadata.json"
        metadata_file.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    if str(args.summary_json or "").strip():
        summary_path = Path(args.summary_json).expanduser()
        if not summary_path.is_absolute():
            summary_path = (ROOT_DIR / summary_path).resolve()
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        log_info(f"摘要已写入: {summary_path}")

    mode_label = "执行模式(APPLY)" if apply_mode else "预览模式(DRY-RUN)"
    print(f"\n{Color.BLUE}{'=' * 78}{Color.NC}")
    print(f"管理员归属迁移完成 - {mode_label}")
    print(f"目标用户: id={target_user_id}, account={target_user['account']}")
    print(f"范围: scope={args.scope}, kinds={','.join(sorted(kinds))}")
    print(f"sessions: 扫描 {summary['sessions']['scanned']} | 匹配 {summary['sessions']['matched']} | 变更 {summary['sessions']['updated']} | 异常 {summary['sessions']['skipped_invalid']}")
    print(f"reports : 扫描 {summary['reports']['scanned']} | 匹配 {summary['reports']['matched']} | 变更 {summary['reports']['updated']}")
    if backup_dir:
        print(f"备份目录: {backup_dir}")
    print(f"{Color.BLUE}{'=' * 78}{Color.NC}\n")

    if sessions_examples:
        print("sessions 示例（最多展示前 N 条）:")
        for item in sessions_examples:
            print(f"- {item['session_file']} : {item['from_owner']} -> {item['to_owner']}")

    if reports_examples:
        print("reports 示例（最多展示前 N 条）:")
        for item in reports_examples:
            print(f"- {item['report_name']} : {item['from_owner']} -> {item['to_owner']}")

    if not apply_mode:
        print("\n提示：当前为 dry-run，仅预览未落盘。")
        print("如确认执行，请追加参数: --apply")

    return 0


def run_rollback(args: argparse.Namespace) -> int:
    backup_dir = Path(args.backup_dir).expanduser()
    if not backup_dir.is_absolute():
        backup_dir = (ROOT_DIR / backup_dir).resolve()

    if not backup_dir.exists() or not backup_dir.is_dir():
        log_error(f"备份目录不存在: {backup_dir}")
        return 2

    sessions_backup_dir = backup_dir / "sessions"
    reports_backup_dir = backup_dir / "reports"

    restored_sessions = 0
    if sessions_backup_dir.exists():
        for backup_file in sorted(sessions_backup_dir.glob("*.json")):
            target_file = SESSIONS_DIR / backup_file.name
            target_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup_file, target_file)
            restored_sessions += 1

    owners_backup = reports_backup_dir / ".owners.json"
    owners_absent_marker = reports_backup_dir / ".owners.absent"
    owners_restored = False
    owners_removed = False

    if owners_backup.exists():
        REPORT_OWNERS_FILE.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(owners_backup, REPORT_OWNERS_FILE)
        owners_restored = True
    elif owners_absent_marker.exists():
        if REPORT_OWNERS_FILE.exists():
            REPORT_OWNERS_FILE.unlink()
        owners_removed = True

    print(f"\n{Color.BLUE}{'=' * 78}{Color.NC}")
    print("回滚完成")
    print(f"备份目录: {backup_dir}")
    print(f"恢复会话文件数: {restored_sessions}")
    print(f"恢复报告归属文件: {'是' if owners_restored else '否'}")
    print(f"移除报告归属文件: {'是' if owners_removed else '否'}")
    print(f"{Color.BLUE}{'=' * 78}{Color.NC}\n")
    return 0


def run_audit(args: argparse.Namespace) -> int:
    auth_db_path = resolve_auth_db_path(args.auth_db)

    try:
        target_user = resolve_target_user(auth_db_path, args.user_id, args.user_account)
    except Exception as exc:
        log_error(str(exc))
        return 2

    target_user_id = int(target_user["id"])
    kinds = parse_kinds(args.kinds)

    sessions_owned = 0
    sessions_total = 0
    sessions_invalid = 0
    if "sessions" in kinds:
        for session_file in SESSIONS_DIR.glob("*.json"):
            sessions_total += 1
            try:
                data = json.loads(session_file.read_text(encoding="utf-8"))
            except Exception:
                sessions_invalid += 1
                continue
            if not isinstance(data, dict):
                sessions_invalid += 1
                continue
            if parse_owner_id(data.get("owner_user_id")) == target_user_id:
                sessions_owned += 1

    reports_owned = 0
    reports_total = 0
    if "reports" in kinds:
        owners = load_report_owners(REPORT_OWNERS_FILE)
        for report_file in REPORTS_DIR.glob("*.md"):
            reports_total += 1
            if parse_owner_id(owners.get(report_file.name, 0)) == target_user_id:
                reports_owned += 1

    print(f"\n{Color.BLUE}{'=' * 78}{Color.NC}")
    print("归属审计")
    print(f"用户: id={target_user_id}, account={target_user['account']}")
    if "sessions" in kinds:
        print(f"sessions: {sessions_owned}/{sessions_total}（异常文件 {sessions_invalid}）")
    if "reports" in kinds:
        print(f"reports : {reports_owned}/{reports_total}")
    print(f"{Color.BLUE}{'=' * 78}{Color.NC}\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="DeepVision 管理员归属迁移工具（支持 dry-run / apply / rollback）"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_users = subparsers.add_parser("list-users", help="列出用户账号，便于选择迁移目标")
    p_users.add_argument("--auth-db", default="", help="用户数据库路径（默认 data/auth/users.db）")
    p_users.add_argument("--limit", type=int, default=200, help="最多展示用户条数")
    p_users.set_defaults(func=lambda a: list_users(resolve_auth_db_path(a.auth_db), a.limit))

    p_migrate = subparsers.add_parser("migrate", help="执行归属迁移（默认 dry-run）")
    target_group = p_migrate.add_mutually_exclusive_group(required=True)
    target_group.add_argument("--to-user-id", type=int, help="目标用户 ID")
    target_group.add_argument("--to-account", default="", help="目标账号（邮箱或手机号）")

    p_migrate.add_argument(
        "--scope",
        choices=["unowned", "all", "from-user"],
        default="unowned",
        help="迁移范围：unowned=仅无归属，all=全部改为目标用户，from-user=仅指定来源用户",
    )
    p_migrate.add_argument("--from-user-id", type=int, default=None, help="当 scope=from-user 时必填")
    p_migrate.add_argument(
        "--kinds",
        default="sessions,reports",
        help="迁移对象，逗号分隔：sessions,reports（默认两者都迁移）",
    )
    p_migrate.add_argument("--apply", action="store_true", help="确认落盘执行；默认 dry-run")
    p_migrate.add_argument("--backup-dir", default="", help="备份目录（仅 apply 模式生效）")
    p_migrate.add_argument("--auth-db", default="", help="用户数据库路径（默认 data/auth/users.db）")
    p_migrate.add_argument("--summary-json", default="", help="将迁移摘要写入 JSON 文件")
    p_migrate.add_argument("--max-examples", type=int, default=20, help="输出示例最多展示条数")
    p_migrate.set_defaults(func=run_migrate)

    p_rollback = subparsers.add_parser("rollback", help="根据备份目录回滚一次迁移")
    p_rollback.add_argument("--backup-dir", required=True, help="迁移时生成的备份目录")
    p_rollback.set_defaults(func=run_rollback)

    p_audit = subparsers.add_parser("audit", help="审计某个用户当前拥有的数据量")
    user_group = p_audit.add_mutually_exclusive_group(required=True)
    user_group.add_argument("--user-id", type=int, help="用户 ID")
    user_group.add_argument("--user-account", default="", help="用户账号（邮箱或手机号）")
    p_audit.add_argument("--auth-db", default="", help="用户数据库路径（默认 data/auth/users.db）")
    p_audit.add_argument("--kinds", default="sessions,reports", help="审计对象：sessions,reports")
    p_audit.set_defaults(func=run_audit)

    return parser


def main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        log_warn("已取消执行")
        return 130
    except Exception as exc:
        log_error(f"执行失败: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

