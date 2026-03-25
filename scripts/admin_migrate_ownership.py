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
import sys
from pathlib import Path

from scripts import admin_ownership_service as service


ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
SESSIONS_DIR = DATA_DIR / "sessions"
REPORTS_DIR = DATA_DIR / "reports"
REPORT_OWNERS_FILE = REPORTS_DIR / ".owners.json"
DEFAULT_BACKUP_ROOT = DATA_DIR / "operations" / "ownership-migrations"


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


def list_users(auth_db_path: Path, limit: int, query: str = "") -> int:
    if not auth_db_path.exists():
        log_error(f"用户数据库不存在: {auth_db_path}")
        return 2

    rows = service.search_users(auth_db_path, query=query, limit=limit)
    if not rows:
        log_warn("users 表为空，没有可选目标用户")
        return 0

    print(f"{Color.BLUE}{'━' * 86}{Color.NC}")
    print(f"{'user_id':<10} {'账号(account)':<34} {'邮箱':<24} {'手机号':<16}")
    print(f"{Color.BLUE}{'━' * 86}{Color.NC}")
    for row in rows:
        print(f"{int(row['id']):<10} {row['account']:<34} {row['email']:<24} {row['phone']:<16}")
    print(f"{Color.BLUE}{'━' * 86}{Color.NC}")
    print(f"共 {len(rows)} 条")
    return 0


def run_migrate(args: argparse.Namespace) -> int:
    auth_db_path = service.resolve_auth_db_path(args.auth_db)
    try:
        summary = service.run_ownership_migration(
            auth_db_path=auth_db_path,
            sessions_dir=SESSIONS_DIR,
            reports_dir=REPORTS_DIR,
            report_owners_file=REPORT_OWNERS_FILE,
            backup_root=DEFAULT_BACKUP_ROOT,
            to_user_id=args.to_user_id,
            to_account=args.to_account,
            scope=args.scope,
            from_user_id=args.from_user_id,
            kinds=args.kinds,
            apply_mode=bool(args.apply),
            backup_id=str(args.backup_dir or "").strip(),
            max_examples=args.max_examples,
        )
    except Exception as exc:
        log_error(str(exc))
        return 2

    if str(args.summary_json or "").strip():
        summary_path = Path(args.summary_json).expanduser()
        if not summary_path.is_absolute():
            summary_path = (ROOT_DIR / summary_path).resolve()
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        log_info(f"摘要已写入: {summary_path}")

    mode_label = "执行模式(APPLY)" if args.apply else "预览模式(DRY-RUN)"
    print(f"\n{Color.BLUE}{'=' * 78}{Color.NC}")
    print(f"管理员归属迁移完成 - {mode_label}")
    print(f"目标用户: id={summary['target_user']['id']}, account={summary['target_user']['account']}")
    print(f"范围: scope={summary['scope']}, kinds={','.join(summary['kinds'])}")
    print(
        f"sessions: 扫描 {summary['sessions']['scanned']} | 匹配 {summary['sessions']['matched']} | "
        f"变更 {summary['sessions']['updated']} | 异常 {summary['sessions']['skipped_invalid']}"
    )
    print(
        f"reports : 扫描 {summary['reports']['scanned']} | 匹配 {summary['reports']['matched']} | "
        f"变更 {summary['reports']['updated']}"
    )
    if summary.get("backup_dir"):
        print(f"备份目录: {summary['backup_dir']}")
    print(f"{Color.BLUE}{'=' * 78}{Color.NC}\n")

    if summary["sessions"]["examples"]:
        print("sessions 示例（最多展示前 N 条）:")
        for item in summary["sessions"]["examples"]:
            print(f"- {item['session_file']} : {item['from_owner']} -> {item['to_owner']}")

    if summary["reports"]["examples"]:
        print("reports 示例（最多展示前 N 条）:")
        for item in summary["reports"]["examples"]:
            print(f"- {item['report_name']} : {item['from_owner']} -> {item['to_owner']}")

    if not args.apply:
        print("\n提示：当前为 dry-run，仅预览未落盘。")
        print("如确认执行，请追加参数: --apply")

    return 0


def run_rollback(args: argparse.Namespace) -> int:
    try:
        result = service.rollback_ownership_migration(
            backup_root=DEFAULT_BACKUP_ROOT,
            sessions_dir=SESSIONS_DIR,
            reports_dir=REPORTS_DIR,
            report_owners_file=REPORT_OWNERS_FILE,
            backup_dir=Path(args.backup_dir),
        )
    except Exception as exc:
        log_error(str(exc))
        return 2

    print(f"\n{Color.BLUE}{'=' * 78}{Color.NC}")
    print("回滚完成")
    print(f"备份目录: {result['backup_dir']}")
    print(f"恢复会话文件数: {result['restored_sessions']}")
    print(f"恢复报告归属文件: {'是' if result['owners_restored'] else '否'}")
    print(f"移除报告归属文件: {'是' if result['owners_removed'] else '否'}")
    print(f"{Color.BLUE}{'=' * 78}{Color.NC}\n")
    return 0


def run_audit(args: argparse.Namespace) -> int:
    auth_db_path = service.resolve_auth_db_path(args.auth_db)
    try:
        summary = service.audit_ownership(
            auth_db_path=auth_db_path,
            sessions_dir=SESSIONS_DIR,
            reports_dir=REPORTS_DIR,
            report_owners_file=REPORT_OWNERS_FILE,
            user_id=args.user_id,
            user_account=args.user_account,
            kinds=args.kinds,
        )
    except Exception as exc:
        log_error(str(exc))
        return 2

    print(f"\n{Color.BLUE}{'=' * 78}{Color.NC}")
    print("归属审计")
    print(f"用户: id={summary['user']['id']}, account={summary['user']['account']}")
    if "sessions" in summary["kinds"]:
        print(f"sessions: {summary['sessions']['owned']}/{summary['sessions']['total']}（异常文件 {summary['sessions']['invalid']}）")
    if "reports" in summary["kinds"]:
        print(f"reports : {summary['reports']['owned']}/{summary['reports']['total']}")
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
    p_users.add_argument("--query", default="", help="按用户 ID / 手机号 / 邮箱搜索")
    p_users.set_defaults(func=lambda a: list_users(service.resolve_auth_db_path(a.auth_db), a.limit, a.query))

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
    p_migrate.add_argument("--kinds", default="sessions,reports", help="迁移对象，逗号分隔：sessions,reports")
    p_migrate.add_argument("--apply", action="store_true", help="确认落盘执行；默认 dry-run")
    p_migrate.add_argument("--backup-dir", default="", help="备份目录名（默认自动生成）")
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
