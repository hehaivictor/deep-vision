#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["psycopg[binary]"]
# ///
"""
DeepVision License 运维脚本

示例：
  python3 scripts/license_manager.py generate --count 10 \
    --duration-days 30

  python3 scripts/license_manager.py generate --count 10 \
    --not-before 2026-03-24T00:00:00+00:00 \
    --expires-at 2026-12-31T23:59:59+00:00

  python3 scripts/license_manager.py list --status active
  python3 scripts/license_manager.py revoke 12 --reason "人工撤销"
  python3 scripts/license_manager.py extend 12 --expires-at 2027-03-31T23:59:59+00:00
  python3 scripts/license_manager.py enforcement-status
  python3 scripts/license_manager.py enforcement-set --enabled true --sync-default
  python3 scripts/license_manager.py enforcement-follow-default
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
SERVER_PATH = ROOT_DIR / "web" / "server.py"
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from db_compat import resolve_db_target


def load_server_module():
    if str(ROOT_DIR) not in sys.path:
        sys.path.insert(0, str(ROOT_DIR))
    spec = importlib.util.spec_from_file_location("dv_server_license_cli", SERVER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载服务模块: {SERVER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def resolve_auth_db_path(raw_auth_db: str) -> str:
    env_path = os.environ.get("DEEPVISION_AUTH_DB_PATH", "")
    value = str(raw_auth_db or "").strip() or env_path
    return resolve_db_target(value, root_dir=ROOT_DIR, default_path=ROOT_DIR / "data" / "auth" / "users.db")


def resolve_license_db_path(raw_license_db: str, auth_db_path: str) -> str:
    env_path = os.environ.get("DEEPVISION_LICENSE_DB_PATH", "")
    value = str(raw_license_db or "").strip() or env_path
    default_path = ROOT_DIR / "data" / "auth" / "licenses.db"
    if not value and "://" not in str(auth_db_path):
        default_path = Path(auth_db_path).expanduser().parent / "licenses.db"
    return resolve_db_target(value, root_dir=ROOT_DIR, default_path=default_path)


def configure_server_databases(server, auth_db_path: str, license_db_path: str) -> None:
    server.AUTH_DB_PATH = auth_db_path
    if "://" not in str(auth_db_path):
        server.AUTH_DIR = Path(auth_db_path).expanduser().parent
        server.AUTH_DIR.mkdir(parents=True, exist_ok=True)
    server.LICENSE_DB_PATH = license_db_path
    server.init_auth_db()
    server.init_license_db()


def print_json(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def print_license_table(items: list[dict]) -> None:
    if not items:
        print("无匹配的 License")
        return
    header = f"{'id':<6} {'batch_id':<24} {'status':<16} {'duration':<12} {'masked_code':<32} {'bound_account':<18} {'expires_at'}"
    print(header)
    print("-" * len(header))
    for item in items:
        print(
            f"{int(item.get('id') or 0):<6} "
            f"{str(item.get('batch_id') or ''):<24} "
            f"{str(item.get('status') or ''):<16} "
            f"{(str(item.get('duration_days') or '') + 'd') if int(item.get('duration_days') or 0) > 0 else '-':<12} "
            f"{str(item.get('masked_code') or ''):<32} "
            f"{str(item.get('bound_account') or ''):<18} "
            f"{str(item.get('expires_at') or '')}"
        )


def run_generate(args: argparse.Namespace) -> int:
    server = load_server_module()
    auth_db_path = resolve_auth_db_path(args.auth_db)
    configure_server_databases(server, auth_db_path, resolve_license_db_path(args.license_db, auth_db_path))
    try:
        payload = server.generate_license_batch(
            count=args.count,
            duration_days=args.duration_days,
            not_before_at=args.not_before,
            expires_at=args.expires_at,
            note=args.note,
            actor_user_id=None,
        )
    except Exception as exc:
        print(f"[ERROR] 生成 License 失败: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print_json(payload)
    else:
        print(f"batch_id: {payload['batch_id']}")
        for item in payload.get("licenses", []):
            print(
                f"- id={item['id']} code={item['code']} "
                f"masked={item['masked_code']} duration_days={item.get('duration_days') or 0} "
                f"expires_at={item['expires_at']}"
            )
    return 0


def run_list(args: argparse.Namespace) -> int:
    server = load_server_module()
    auth_db_path = resolve_auth_db_path(args.auth_db)
    configure_server_databases(server, auth_db_path, resolve_license_db_path(args.license_db, auth_db_path))
    items = server.list_licenses_admin(
        batch_id=args.batch_id,
        status=args.status,
        bound_account=args.bound_account,
    )
    if args.json:
        print_json({"count": len(items), "items": items})
    else:
        print_license_table(items)
    return 0


def run_revoke(args: argparse.Namespace) -> int:
    server = load_server_module()
    auth_db_path = resolve_auth_db_path(args.auth_db)
    configure_server_databases(server, auth_db_path, resolve_license_db_path(args.license_db, auth_db_path))
    try:
        payload = server.revoke_license_by_id(args.license_id, reason=args.reason, actor_user_id=None)
    except Exception as exc:
        print(f"[ERROR] 撤销 License 失败: {exc}", file=sys.stderr)
        return 2
    print_json(payload if args.json else {"success": True, **payload})
    return 0


def run_extend(args: argparse.Namespace) -> int:
    server = load_server_module()
    auth_db_path = resolve_auth_db_path(args.auth_db)
    configure_server_databases(server, auth_db_path, resolve_license_db_path(args.license_db, auth_db_path))
    try:
        payload = server.extend_license_by_id(
            args.license_id,
            expires_at=args.expires_at,
            duration_days=args.duration_days,
            actor_user_id=None,
        )
    except Exception as exc:
        print(f"[ERROR] 延期 License 失败: {exc}", file=sys.stderr)
        return 2
    print_json(payload if args.json else {"success": True, **payload})
    return 0


def run_enforcement_status(args: argparse.Namespace) -> int:
    server = load_server_module()
    auth_db_path = resolve_auth_db_path(args.auth_db)
    configure_server_databases(server, auth_db_path, resolve_license_db_path(args.license_db, auth_db_path))
    payload = server.get_license_enforcement_state()
    print_json(payload)
    return 0


def run_enforcement_set(args: argparse.Namespace) -> int:
    server = load_server_module()
    auth_db_path = resolve_auth_db_path(args.auth_db)
    configure_server_databases(server, auth_db_path, resolve_license_db_path(args.license_db, auth_db_path))
    enabled = server._parse_bool_like(args.enabled)
    if enabled is None:
        print("[ERROR] --enabled 仅支持 true/false/on/off/1/0", file=sys.stderr)
        return 2
    payload = server.set_license_enforcement_override(
        enabled,
        actor_user_id=None,
        sync_default=bool(args.sync_default),
    )
    print_json({"success": True, **payload})
    return 0


def run_enforcement_follow_default(args: argparse.Namespace) -> int:
    server = load_server_module()
    auth_db_path = resolve_auth_db_path(args.auth_db)
    configure_server_databases(server, auth_db_path, resolve_license_db_path(args.license_db, auth_db_path))
    payload = server.set_license_enforcement_override(None, actor_user_id=None, sync_default=False)
    print_json({"success": True, **payload})
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DeepVision License 运维脚本")
    parser.add_argument("--auth-db", default="", help="鉴权数据库路径，默认 data/auth/users.db 或 DEEPVISION_AUTH_DB_PATH")
    parser.add_argument("--license-db", default="", help="License 数据库路径，默认 data/auth/licenses.db 或 DEEPVISION_LICENSE_DB_PATH")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_generate = subparsers.add_parser("generate", help="批量生成 License")
    p_generate.add_argument("--count", type=int, required=True, help="生成数量，1-500")
    p_generate.add_argument("--duration-days", type=int, default=None, help="激活后有效期天数，优先使用")
    p_generate.add_argument("--not-before", default="", help="兼容旧模式：生效时间，ISO-8601")
    p_generate.add_argument("--expires-at", default="", help="兼容旧模式：失效时间，ISO-8601")
    p_generate.add_argument("--note", default="", help="备注")
    p_generate.set_defaults(func=run_generate)

    p_list = subparsers.add_parser("list", help="查询 License")
    p_list.add_argument("--batch-id", default="", help="按批次筛选")
    p_list.add_argument("--status", default="", help="按状态筛选")
    p_list.add_argument("--bound-account", default="", help="按绑定账号筛选")
    p_list.set_defaults(func=run_list)

    p_revoke = subparsers.add_parser("revoke", help="撤销指定 License")
    p_revoke.add_argument("license_id", type=int, help="License ID")
    p_revoke.add_argument("--reason", default="", help="撤销原因")
    p_revoke.set_defaults(func=run_revoke)

    p_extend = subparsers.add_parser("extend", help="延期指定 License")
    p_extend.add_argument("license_id", type=int, help="License ID")
    p_extend.add_argument("--duration-days", type=int, default=None, help="新的有效期天数")
    p_extend.add_argument("--expires-at", default="", help="兼容旧模式：新的失效时间，ISO-8601")
    p_extend.set_defaults(func=run_extend)

    p_enforcement_status = subparsers.add_parser("enforcement-status", help="查看 License 校验开关状态")
    p_enforcement_status.set_defaults(func=run_enforcement_status)

    p_enforcement_set = subparsers.add_parser("enforcement-set", help="设置 License 校验开关")
    p_enforcement_set.add_argument("--enabled", required=True, help="true/false")
    p_enforcement_set.add_argument("--sync-default", action="store_true", help="同时写回 .env 中的 LICENSE_ENFORCEMENT_ENABLED")
    p_enforcement_set.set_defaults(func=run_enforcement_set)

    p_enforcement_follow_default = subparsers.add_parser("enforcement-follow-default", help="清除运行时覆盖并恢复跟随默认值")
    p_enforcement_follow_default.set_defaults(func=run_enforcement_follow_default)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
