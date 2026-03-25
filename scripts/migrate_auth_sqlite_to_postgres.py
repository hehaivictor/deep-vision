#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["flask", "flask-cors", "anthropic", "requests", "reportlab", "pillow", "jdcloud-sdk", "psycopg[binary]"]
# ///
from __future__ import annotations

import argparse
import importlib.util
import sqlite3
import sys
from pathlib import Path

import psycopg

ROOT_DIR = Path(__file__).resolve().parent.parent
SERVER_PATH = ROOT_DIR / "web" / "server.py"
DEFAULT_USERS_DB = ROOT_DIR / "data" / "auth" / "users.db"
DEFAULT_LICENSE_DB = ROOT_DIR / "data" / "auth" / "licenses.db"

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from db_compat import sanitize_postgres_dsn


def load_server_module():
    spec = importlib.util.spec_from_file_location("dv_server_pg_migration", SERVER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载服务模块: {SERVER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fetch_rows(db_path: Path, table_name: str) -> list[dict]:
    if not db_path.exists():
        return []
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(f"SELECT * FROM {table_name}").fetchall()
    return [dict(row) for row in rows]


def choose_primary_rows(primary: list[dict], fallback: list[dict]) -> list[dict]:
    return primary if primary else fallback


def merge_auth_meta(primary: list[dict], secondary: list[dict]) -> list[dict]:
    merged: dict[str, dict] = {}
    for row in secondary:
        key = str(row.get("meta_key") or "").strip()
        if key:
            merged[key] = dict(row)
    for row in primary:
        key = str(row.get("meta_key") or "").strip()
        if key:
            merged[key] = dict(row)
    return [merged[key] for key in sorted(merged.keys())]


def reset_target_tables(conn: psycopg.Connection) -> None:
    conn.execute(
        """
        TRUNCATE TABLE
            wechat_identities,
            auth_sms_codes,
            license_events,
            licenses,
            users,
            auth_meta
        RESTART IDENTITY CASCADE
        """
    )


def sync_identity_sequence(conn: psycopg.Connection, table_name: str) -> None:
    conn.execute(
        """
        SELECT setval(
            pg_get_serial_sequence(%s, 'id'),
            COALESCE((SELECT MAX(id) FROM """ + table_name + """), 1),
            COALESCE((SELECT MAX(id) FROM """ + table_name + """), 0) > 0
        )
        """,
        (table_name,),
    )


def insert_auth_meta(conn: psycopg.Connection, rows: list[dict]) -> None:
    if not rows:
        return
    with conn.cursor() as cursor:
        cursor.executemany(
            """
            INSERT INTO auth_meta (meta_key, meta_value, updated_at)
            VALUES (%s, %s, %s)
            ON CONFLICT(meta_key) DO UPDATE SET
                meta_value = EXCLUDED.meta_value,
                updated_at = EXCLUDED.updated_at
            """,
            [
                (
                    str(row.get("meta_key") or ""),
                    str(row.get("meta_value") or ""),
                    str(row.get("updated_at") or ""),
                )
                for row in rows
            ],
        )


def insert_users(conn: psycopg.Connection, rows: list[dict]) -> None:
    if not rows:
        return
    with conn.cursor() as cursor:
        cursor.executemany(
            """
            INSERT INTO users (id, email, phone, password_hash, created_at, updated_at, merged_into_user_id, merged_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(id) DO UPDATE SET
                email = EXCLUDED.email,
                phone = EXCLUDED.phone,
                password_hash = EXCLUDED.password_hash,
                created_at = EXCLUDED.created_at,
                updated_at = EXCLUDED.updated_at,
                merged_into_user_id = EXCLUDED.merged_into_user_id,
                merged_at = EXCLUDED.merged_at
            """,
            [
                (
                    row.get("id"),
                    row.get("email"),
                    row.get("phone"),
                    row.get("password_hash"),
                    row.get("created_at"),
                    row.get("updated_at"),
                    row.get("merged_into_user_id"),
                    row.get("merged_at"),
                )
                for row in rows
            ],
        )


def insert_wechat_identities(conn: psycopg.Connection, rows: list[dict]) -> None:
    if not rows:
        return
    with conn.cursor() as cursor:
        cursor.executemany(
            """
            INSERT INTO wechat_identities (id, user_id, app_id, openid, unionid, nickname, avatar_url, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(id) DO UPDATE SET
                user_id = EXCLUDED.user_id,
                app_id = EXCLUDED.app_id,
                openid = EXCLUDED.openid,
                unionid = EXCLUDED.unionid,
                nickname = EXCLUDED.nickname,
                avatar_url = EXCLUDED.avatar_url,
                created_at = EXCLUDED.created_at,
                updated_at = EXCLUDED.updated_at
            """,
            [
                (
                    row.get("id"),
                    row.get("user_id"),
                    row.get("app_id"),
                    row.get("openid"),
                    row.get("unionid"),
                    row.get("nickname"),
                    row.get("avatar_url"),
                    row.get("created_at"),
                    row.get("updated_at"),
                )
                for row in rows
            ],
        )


def insert_auth_sms_codes(conn: psycopg.Connection, rows: list[dict]) -> None:
    if not rows:
        return
    with conn.cursor() as cursor:
        cursor.executemany(
            """
            INSERT INTO auth_sms_codes (id, phone, scene, code_hash, request_ip, created_at, expires_at, consumed_at, attempts, max_attempts)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(id) DO UPDATE SET
                phone = EXCLUDED.phone,
                scene = EXCLUDED.scene,
                code_hash = EXCLUDED.code_hash,
                request_ip = EXCLUDED.request_ip,
                created_at = EXCLUDED.created_at,
                expires_at = EXCLUDED.expires_at,
                consumed_at = EXCLUDED.consumed_at,
                attempts = EXCLUDED.attempts,
                max_attempts = EXCLUDED.max_attempts
            """,
            [
                (
                    row.get("id"),
                    row.get("phone"),
                    row.get("scene"),
                    row.get("code_hash"),
                    row.get("request_ip"),
                    row.get("created_at"),
                    row.get("expires_at"),
                    row.get("consumed_at"),
                    row.get("attempts"),
                    row.get("max_attempts"),
                )
                for row in rows
            ],
        )


def insert_licenses(conn: psycopg.Connection, rows: list[dict]) -> None:
    if not rows:
        return
    with conn.cursor() as cursor:
        cursor.executemany(
            """
            INSERT INTO licenses (
                id, batch_id, code_hash, code_mask, status, not_before_at, expires_at, duration_days,
                bound_user_id, bound_at, replaced_by_license_id, revoked_at, revoked_reason, note, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(id) DO UPDATE SET
                batch_id = EXCLUDED.batch_id,
                code_hash = EXCLUDED.code_hash,
                code_mask = EXCLUDED.code_mask,
                status = EXCLUDED.status,
                not_before_at = EXCLUDED.not_before_at,
                expires_at = EXCLUDED.expires_at,
                duration_days = EXCLUDED.duration_days,
                bound_user_id = EXCLUDED.bound_user_id,
                bound_at = EXCLUDED.bound_at,
                replaced_by_license_id = EXCLUDED.replaced_by_license_id,
                revoked_at = EXCLUDED.revoked_at,
                revoked_reason = EXCLUDED.revoked_reason,
                note = EXCLUDED.note,
                created_at = EXCLUDED.created_at,
                updated_at = EXCLUDED.updated_at
            """,
            [
                (
                    row.get("id"),
                    row.get("batch_id"),
                    row.get("code_hash"),
                    row.get("code_mask"),
                    row.get("status"),
                    row.get("not_before_at"),
                    row.get("expires_at"),
                    row.get("duration_days") or 0,
                    row.get("bound_user_id"),
                    row.get("bound_at"),
                    row.get("replaced_by_license_id"),
                    row.get("revoked_at"),
                    row.get("revoked_reason"),
                    row.get("note"),
                    row.get("created_at"),
                    row.get("updated_at"),
                )
                for row in rows
            ],
        )


def insert_license_events(conn: psycopg.Connection, rows: list[dict]) -> None:
    if not rows:
        return
    with conn.cursor() as cursor:
        cursor.executemany(
            """
            INSERT INTO license_events (id, license_id, actor_user_id, event_type, payload_json, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT(id) DO UPDATE SET
                license_id = EXCLUDED.license_id,
                actor_user_id = EXCLUDED.actor_user_id,
                event_type = EXCLUDED.event_type,
                payload_json = EXCLUDED.payload_json,
                created_at = EXCLUDED.created_at
            """,
            [
                (
                    row.get("id"),
                    row.get("license_id"),
                    row.get("actor_user_id"),
                    row.get("event_type"),
                    row.get("payload_json"),
                    row.get("created_at"),
                )
                for row in rows
            ],
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="将 DeepVision users.db / licenses.db 迁移到 PostgreSQL")
    parser.add_argument("--users-db", default=str(DEFAULT_USERS_DB), help="users.db 路径")
    parser.add_argument("--license-db", default=str(DEFAULT_LICENSE_DB), help="licenses.db 路径")
    parser.add_argument("--target-dsn", required=True, help="PostgreSQL 连接串")
    args = parser.parse_args()

    users_db = Path(args.users_db).expanduser().resolve()
    license_db = Path(args.license_db).expanduser().resolve()
    target_dsn = sanitize_postgres_dsn(args.target_dsn)

    server = load_server_module()
    server.AUTH_DB_PATH = target_dsn
    server.LICENSE_DB_PATH = target_dsn
    server.init_auth_db()
    server.init_license_db()

    users_rows = fetch_rows(users_db, "users")
    wechat_rows = fetch_rows(users_db, "wechat_identities")
    sms_rows = fetch_rows(users_db, "auth_sms_codes")
    licenses_rows = choose_primary_rows(fetch_rows(users_db, "licenses"), fetch_rows(license_db, "licenses"))
    events_rows = choose_primary_rows(fetch_rows(users_db, "license_events"), fetch_rows(license_db, "license_events"))
    auth_meta_rows = merge_auth_meta(fetch_rows(users_db, "auth_meta"), fetch_rows(license_db, "auth_meta"))

    with psycopg.connect(target_dsn, connect_timeout=10) as conn:
        reset_target_tables(conn)
        insert_auth_meta(conn, auth_meta_rows)
        insert_users(conn, users_rows)
        insert_wechat_identities(conn, wechat_rows)
        insert_auth_sms_codes(conn, sms_rows)
        insert_licenses(conn, licenses_rows)
        insert_license_events(conn, events_rows)
        for table_name in ("users", "wechat_identities", "auth_sms_codes", "licenses", "license_events"):
            sync_identity_sequence(conn, table_name)
        conn.commit()

    print("迁移完成")
    print(f"target_dsn={target_dsn}")
    print(f"users={len(users_rows)}")
    print(f"wechat_identities={len(wechat_rows)}")
    print(f"auth_sms_codes={len(sms_rows)}")
    print(f"licenses={len(licenses_rows)}")
    print(f"license_events={len(events_rows)}")
    print(f"auth_meta={len(auth_meta_rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
