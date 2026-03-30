from __future__ import annotations

import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from db_compat import (
    connect_db,
    db_target_exists,
    db_target_name,
    db_target_supports_file_backup,
    normalize_db_cache_key,
    resolve_db_target,
)

DATA_DIR = ROOT_DIR / "data"
AUTH_DIR = DATA_DIR / "auth"
DEFAULT_AUTH_DB_PATH = AUTH_DIR / "users.db"
DEFAULT_LICENSE_DB_PATH = AUTH_DIR / "licenses.db"
DEFAULT_META_INDEX_DB_PATH = DATA_DIR / "meta_index.db"
DEFAULT_BACKUP_ROOT = DATA_DIR / "operations" / "ownership-migrations"

AUTH_EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
AUTH_PHONE_PATTERN = re.compile(r"^1\d{10}$")
VALID_OWNERSHIP_SCOPES = {"unowned", "all", "from-user"}


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


def resolve_auth_db_path(raw_auth_db: str) -> str:
    return resolve_db_target(raw_auth_db, root_dir=ROOT_DIR, default_path=DEFAULT_AUTH_DB_PATH)


def resolve_license_db_path(raw_license_db: str, *, auth_db_path: Optional[str] = None) -> str:
    input_path = str(raw_license_db or "").strip()
    if input_path:
        return resolve_db_target(input_path, root_dir=ROOT_DIR, default_path=DEFAULT_LICENSE_DB_PATH)
    if auth_db_path is not None and not str(auth_db_path).strip().lower().startswith(("postgres://", "postgresql://")):
        path = Path(auth_db_path).expanduser().parent / "licenses.db"
        return resolve_db_target(str(path), root_dir=ROOT_DIR, default_path=DEFAULT_LICENSE_DB_PATH)
    return resolve_db_target("", root_dir=ROOT_DIR, default_path=DEFAULT_LICENSE_DB_PATH)


def resolve_meta_index_db_path(raw_meta_index_db: str) -> str:
    return resolve_db_target(raw_meta_index_db, root_dir=ROOT_DIR, default_path=DEFAULT_META_INDEX_DB_PATH)


def get_auth_db_connection(auth_db_path: str):
    return connect_db(auth_db_path)


def get_license_db_connection(license_db_path: str):
    return connect_db(license_db_path)


def get_meta_index_connection(meta_index_db_path: str):
    return connect_db(meta_index_db_path)


def _use_meta_index_storage(meta_index_db_path: Optional[str]) -> bool:
    return bool(str(meta_index_db_path or "").strip())


def _row_to_dict(row: Any) -> dict[str, Any]:
    if row is None:
        return {}
    if isinstance(row, dict):
        return dict(row)
    if hasattr(row, "keys"):
        return {str(key): row[key] for key in row.keys()}
    return {}


def _fetch_all_dicts(conn, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    rows = conn.execute(sql, params).fetchall()
    return [_row_to_dict(row) for row in rows]


def _write_json_snapshot(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_json_snapshot(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def query_user_by_id(auth_db_path: str, user_id: int):
    with get_auth_db_connection(auth_db_path) as conn:
        return conn.execute(
            "SELECT id, email, phone, created_at FROM users WHERE id = ? LIMIT 1",
            (int(user_id),),
        ).fetchone()


def query_user_by_account(auth_db_path: str, account: str):
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


def serialize_user(row) -> dict[str, Any]:
    email = str(row["email"] or "").strip()
    phone = str(row["phone"] or "").strip()
    account = email or phone or f"user-{int(row['id'])}"
    return {
        "id": int(row["id"]),
        "email": email,
        "phone": phone,
        "account": account,
        "created_at": str(row["created_at"] or "").strip(),
    }


def search_users(auth_db_path: str, query: str = "", limit: int = 20) -> list[dict[str, Any]]:
    if not db_target_exists(auth_db_path):
        raise RuntimeError(f"用户数据库不存在: {auth_db_path}")

    normalized_query = str(query or "").strip()
    max_limit = max(1, min(int(limit or 20), 100))

    sql = "SELECT id, email, phone, created_at FROM users"
    params: list[object] = []
    if normalized_query:
        if normalized_query.isdigit():
            sql += " WHERE id = ? OR phone LIKE ? OR email LIKE ?"
            params.extend([int(normalized_query), f"%{normalized_query}%", f"%{normalized_query}%"])
        else:
            sql += " WHERE phone LIKE ? OR email LIKE ?"
            params.extend([f"%{normalized_query}%", f"%{normalized_query}%"])
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(max_limit)

    with get_auth_db_connection(auth_db_path) as conn:
        rows = conn.execute(sql, tuple(params)).fetchall()
    return [serialize_user(row) for row in rows]


def parse_kinds(raw_kinds: Any) -> set[str]:
    if isinstance(raw_kinds, (list, tuple, set)):
        tokens = [str(token or "").strip().lower() for token in raw_kinds if str(token or "").strip()]
    else:
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
            raise ValueError(f"无效 kinds 取值: {token}（允许: sessions,reports）")
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


def resolve_target_user(auth_db_path: str, to_user_id: Optional[int], to_account: str) -> dict[str, Any]:
    if not db_target_exists(auth_db_path):
        raise RuntimeError(f"用户数据库不存在: {auth_db_path}")

    row = query_user_by_id(auth_db_path, int(to_user_id)) if to_user_id is not None else query_user_by_account(auth_db_path, to_account)
    if not row:
        raise RuntimeError("目标用户不存在，请先确认用户")
    return serialize_user(row)


def resolve_user_reference(auth_db_path: str, *, user_id: Optional[int] = None, user_account: str = "") -> dict[str, Any]:
    if user_id is not None:
        row = query_user_by_id(auth_db_path, int(user_id))
    else:
        row = query_user_by_account(auth_db_path, user_account)
    if not row:
        raise RuntimeError("指定用户不存在")
    return serialize_user(row)


def load_report_owners(path: Path, meta_index_db_path: Optional[str] = None) -> dict[str, int]:
    if _use_meta_index_storage(meta_index_db_path):
        with get_meta_index_connection(str(meta_index_db_path)) as conn:
            rows = _fetch_all_dicts(
                conn,
                """
                SELECT file_name, owner_user_id
                FROM report_meta_owners
                """,
            )
        normalized: dict[str, int] = {}
        for row in rows:
            name = str(row.get("file_name") or "").strip()
            owner_id = parse_owner_id(row.get("owner_user_id"))
            if not name or owner_id <= 0:
                continue
            normalized[name] = owner_id
        return normalized

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


def save_report_owners(path: Path, owners: dict[str, int], meta_index_db_path: Optional[str] = None) -> None:
    sorted_items = sorted(owners.items(), key=lambda item: item[0])
    payload = {name: int(owner_id) for name, owner_id in sorted_items}
    if _use_meta_index_storage(meta_index_db_path):
        with get_meta_index_connection(str(meta_index_db_path)) as conn:
            conn.execute("DELETE FROM report_meta_owners")
            if payload:
                conn.executemany(
                    """
                    INSERT INTO report_meta_owners(file_name, owner_user_id, updated_at)
                    VALUES (?, ?, ?)
                    """,
                    [
                        (name, int(owner_id), utc_now_iso())
                        for name, owner_id in payload.items()
                    ],
                )
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_solution_share_records(report_solution_shares_file: Path, meta_index_db_path: Optional[str] = None) -> dict[str, dict[str, Any]]:
    if _use_meta_index_storage(meta_index_db_path):
        with get_meta_index_connection(str(meta_index_db_path)) as conn:
            rows = _fetch_all_dicts(
                conn,
                """
                SELECT share_token, report_name, owner_user_id, created_at, updated_at
                FROM report_meta_solution_shares
                """,
            )
        normalized: dict[str, dict[str, Any]] = {}
        for row in rows:
            token = str(row.get("share_token") or "").strip()
            if not token:
                continue
            normalized[token] = {
                "report_name": str(row.get("report_name") or "").strip(),
                "owner_user_id": parse_owner_id(row.get("owner_user_id")),
                "created_at": str(row.get("created_at") or "").strip(),
                "updated_at": str(row.get("updated_at") or "").strip(),
            }
        return normalized

    payload = _load_json_file(report_solution_shares_file, {})
    return payload if isinstance(payload, dict) else {}


def save_solution_share_records(
    report_solution_shares_file: Path,
    payload: dict[str, dict[str, Any]],
    meta_index_db_path: Optional[str] = None,
) -> None:
    normalized = payload if isinstance(payload, dict) else {}
    if _use_meta_index_storage(meta_index_db_path):
        with get_meta_index_connection(str(meta_index_db_path)) as conn:
            conn.execute("DELETE FROM report_meta_solution_shares")
            if normalized:
                conn.executemany(
                    """
                    INSERT INTO report_meta_solution_shares(
                        share_token, report_name, owner_user_id, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            str(token),
                            str((record or {}).get("report_name") or "").strip(),
                            parse_owner_id((record or {}).get("owner_user_id")),
                            str((record or {}).get("created_at") or "").strip(),
                            str((record or {}).get("updated_at") or "").strip(),
                        )
                        for token, record in normalized.items()
                        if isinstance(record, dict) and str(token).strip()
                    ],
                )
        return
    _write_json_file(report_solution_shares_file, normalized)


def prepare_backup_dir(backup_root: Path, backup_id: str, target_user_id: int, apply_mode: bool) -> Optional[Path]:
    if not apply_mode:
        return None

    backup_root = Path(backup_root).expanduser()
    if not backup_root.is_absolute():
        backup_root = (ROOT_DIR / backup_root).resolve()
    backup_root.mkdir(parents=True, exist_ok=True)

    if str(backup_id or "").strip():
        backup_dir = backup_root / str(backup_id).strip()
    else:
        backup_dir = backup_root / f"{utc_now_tag()}-to-{int(target_user_id)}"

    if backup_dir.exists():
        existing = list(backup_dir.iterdir())
        if existing:
            raise RuntimeError(f"备份目录已存在且非空: {backup_dir}")
    else:
        backup_dir.mkdir(parents=True, exist_ok=True)

    (backup_dir / "sessions").mkdir(parents=True, exist_ok=True)
    (backup_dir / "reports").mkdir(parents=True, exist_ok=True)
    (backup_dir / "auth").mkdir(parents=True, exist_ok=True)
    (backup_dir / "licenses").mkdir(parents=True, exist_ok=True)
    (backup_dir / "custom_scenarios").mkdir(parents=True, exist_ok=True)
    return backup_dir


def backup_file_once(src: Path, dest: Path) -> None:
    if dest.exists():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)


def backup_absent_marker_once(dest: Path) -> None:
    if dest.exists():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("absent\n", encoding="utf-8")


def capture_account_merge_db_snapshot(
    *,
    backup_dir: Path,
    auth_db_path: str,
    license_db_path: str,
    source_user_id: int,
    target_user_id: int,
) -> Optional[Path]:
    if not backup_dir:
        return None

    snapshot = {
        "snapshot_type": "account_merge_db_state",
        "captured_at": utc_now_iso(),
        "auth_db_path": normalize_db_cache_key(auth_db_path),
        "license_db_path": normalize_db_cache_key(license_db_path),
        "source_user_id": int(source_user_id),
        "target_user_id": int(target_user_id),
        "users": [],
        "wechat_identities": [],
        "licenses": [],
    }

    with get_auth_db_connection(auth_db_path) as conn:
        ensure_user_merge_columns(conn)
        snapshot["users"] = _fetch_all_dicts(
            conn,
            """
            SELECT id, email, phone, password_hash, created_at, updated_at, merged_into_user_id, merged_at
            FROM users
            WHERE id IN (?, ?)
            ORDER BY id
            """,
            (int(source_user_id), int(target_user_id)),
        )
        snapshot["wechat_identities"] = _fetch_all_dicts(
            conn,
            """
            SELECT id, user_id, app_id, openid, unionid, nickname, avatar_url, created_at, updated_at
            FROM wechat_identities
            WHERE user_id IN (?, ?)
            ORDER BY id
            """,
            (int(source_user_id), int(target_user_id)),
        )

    with get_license_db_connection(license_db_path) as conn:
        snapshot["licenses"] = _fetch_all_dicts(
            conn,
            """
            SELECT id, batch_id, code_hash, code_mask, status, not_before_at, expires_at, duration_days,
                   bound_user_id, bound_at, replaced_by_license_id, revoked_at, revoked_reason, note, created_at, updated_at
            FROM licenses
            WHERE bound_user_id = ?
            ORDER BY id
            """,
            (int(source_user_id),),
        )

    snapshot_path = backup_dir / "auth" / "account-merge-db-snapshot.json"
    _write_json_snapshot(snapshot_path, snapshot)
    return snapshot_path


def restore_account_merge_db_snapshot(
    *,
    snapshot_path: Path,
    auth_db_path: str,
    license_db_path: str,
) -> dict[str, int]:
    snapshot = _load_json_snapshot(snapshot_path)
    if not snapshot:
        raise RuntimeError(f"数据库快照不存在或无效: {snapshot_path}")

    snapshot_auth_db_path = normalize_db_cache_key(snapshot.get("auth_db_path"))
    snapshot_license_db_path = normalize_db_cache_key(snapshot.get("license_db_path"))
    current_auth_db_path = normalize_db_cache_key(auth_db_path)
    current_license_db_path = normalize_db_cache_key(license_db_path)
    if snapshot_auth_db_path and current_auth_db_path and snapshot_auth_db_path != current_auth_db_path:
        raise RuntimeError("当前鉴权数据库与备份快照记录不一致，已拒绝回滚")
    if snapshot_license_db_path and current_license_db_path and snapshot_license_db_path != current_license_db_path:
        raise RuntimeError("当前 License 数据库与备份快照记录不一致，已拒绝回滚")

    users_rows = [item for item in snapshot.get("users", []) if isinstance(item, dict)]
    wechat_rows = [item for item in snapshot.get("wechat_identities", []) if isinstance(item, dict)]
    license_rows = [item for item in snapshot.get("licenses", []) if isinstance(item, dict)]

    restored = {
        "users": 0,
        "wechat_identities": 0,
        "licenses": 0,
    }

    if users_rows or wechat_rows:
        with get_auth_db_connection(auth_db_path) as conn:
            ensure_user_merge_columns(conn)
            conn.execute("BEGIN IMMEDIATE")
            for row in users_rows:
                conn.execute(
                    """
                    INSERT INTO users (id, email, phone, password_hash, created_at, updated_at, merged_into_user_id, merged_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        email = excluded.email,
                        phone = excluded.phone,
                        password_hash = excluded.password_hash,
                        created_at = excluded.created_at,
                        updated_at = excluded.updated_at,
                        merged_into_user_id = excluded.merged_into_user_id,
                        merged_at = excluded.merged_at
                    """,
                    (
                        row.get("id"),
                        row.get("email"),
                        row.get("phone"),
                        row.get("password_hash"),
                        row.get("created_at"),
                        row.get("updated_at"),
                        row.get("merged_into_user_id"),
                        row.get("merged_at"),
                    ),
                )
                restored["users"] += 1
            for row in wechat_rows:
                conn.execute(
                    """
                    INSERT INTO wechat_identities (id, user_id, app_id, openid, unionid, nickname, avatar_url, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        user_id = excluded.user_id,
                        app_id = excluded.app_id,
                        openid = excluded.openid,
                        unionid = excluded.unionid,
                        nickname = excluded.nickname,
                        avatar_url = excluded.avatar_url,
                        created_at = excluded.created_at,
                        updated_at = excluded.updated_at
                    """,
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
                    ),
                )
                restored["wechat_identities"] += 1
            conn.commit()

    if license_rows:
        with get_license_db_connection(license_db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            for row in license_rows:
                conn.execute(
                    """
                    INSERT INTO licenses (
                        id, batch_id, code_hash, code_mask, status, not_before_at, expires_at, duration_days,
                        bound_user_id, bound_at, replaced_by_license_id, revoked_at, revoked_reason, note, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        batch_id = excluded.batch_id,
                        code_hash = excluded.code_hash,
                        code_mask = excluded.code_mask,
                        status = excluded.status,
                        not_before_at = excluded.not_before_at,
                        expires_at = excluded.expires_at,
                        duration_days = excluded.duration_days,
                        bound_user_id = excluded.bound_user_id,
                        bound_at = excluded.bound_at,
                        replaced_by_license_id = excluded.replaced_by_license_id,
                        revoked_at = excluded.revoked_at,
                        revoked_reason = excluded.revoked_reason,
                        note = excluded.note,
                        created_at = excluded.created_at,
                        updated_at = excluded.updated_at
                    """,
                    (
                        row.get("id"),
                        row.get("batch_id"),
                        row.get("code_hash"),
                        row.get("code_mask"),
                        row.get("status"),
                        row.get("not_before_at"),
                        row.get("expires_at"),
                        row.get("duration_days"),
                        row.get("bound_user_id"),
                        row.get("bound_at"),
                        row.get("replaced_by_license_id"),
                        row.get("revoked_at"),
                        row.get("revoked_reason"),
                        row.get("note"),
                        row.get("created_at"),
                        row.get("updated_at"),
                    ),
                )
                restored["licenses"] += 1
            conn.commit()

    return restored


def _load_json_file(path: Path, default):
    if not path.exists():
        return default
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default
    return payload


def _write_json_file(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _build_session_store_update_row(row: dict[str, Any], target_user_id: int, updated_at: str) -> dict[str, Any]:
    payload_text = str(row.get("payload_json") or "").strip()
    try:
        payload = json.loads(payload_text) if payload_text else {}
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    payload["owner_user_id"] = int(target_user_id)
    payload["updated_at"] = updated_at
    updated_payload_text = json.dumps(payload, ensure_ascii=False, indent=2)
    return {
        "session_id": str(row.get("session_id") or "").strip(),
        "file_name": str(row.get("file_name") or "").strip(),
        "owner_user_id": int(target_user_id),
        "instance_scope_key": str(row.get("instance_scope_key") or "").strip(),
        "payload_json": updated_payload_text,
        "created_at": str(row.get("created_at") or "").strip(),
        "updated_at": updated_at,
        "payload_mtime_ns": int(row.get("payload_mtime_ns") or 0),
        "payload_size": len(updated_payload_text.encode("utf-8")),
    }


def _upsert_session_store_rows(conn, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    conn.executemany(
        """
        INSERT INTO session_store (
            session_id, file_name, owner_user_id, instance_scope_key,
            payload_json, created_at, updated_at, payload_mtime_ns, payload_size
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(session_id) DO UPDATE SET
            file_name = excluded.file_name,
            owner_user_id = excluded.owner_user_id,
            instance_scope_key = excluded.instance_scope_key,
            payload_json = excluded.payload_json,
            created_at = excluded.created_at,
            updated_at = excluded.updated_at,
            payload_mtime_ns = excluded.payload_mtime_ns,
            payload_size = excluded.payload_size
        """,
        [
            (
                row["session_id"],
                row["file_name"],
                row["owner_user_id"],
                row["instance_scope_key"],
                row["payload_json"],
                row["created_at"],
                row["updated_at"],
                row["payload_mtime_ns"],
                row["payload_size"],
            )
            for row in rows
        ],
    )


def _ensure_custom_scenarios_meta_table(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS custom_scenarios (
            scenario_id TEXT PRIMARY KEY,
            owner_user_id INTEGER NOT NULL,
            instance_scope_key TEXT NOT NULL DEFAULT '',
            payload_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT ''
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_custom_scenarios_owner_scope_updated ON custom_scenarios(owner_user_id, instance_scope_key, updated_at DESC)"
    )


def _build_custom_scenario_update_row(row: dict[str, Any], target_user_id: int, updated_at: str) -> dict[str, Any]:
    payload_text = str(row.get("payload_json") or "").strip()
    try:
        payload = json.loads(payload_text) if payload_text else {}
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    payload["owner_user_id"] = int(target_user_id)
    meta = payload.get("meta")
    if isinstance(meta, dict) and "owner_user_id" in meta:
        meta["owner_user_id"] = int(target_user_id)
    payload["updated_at"] = updated_at
    updated_payload_text = json.dumps(payload, ensure_ascii=False, indent=2)
    return {
        "scenario_id": str(row.get("scenario_id") or "").strip(),
        "owner_user_id": int(target_user_id),
        "instance_scope_key": str(row.get("instance_scope_key") or "").strip(),
        "payload_json": updated_payload_text,
        "created_at": str(row.get("created_at") or "").strip(),
        "updated_at": updated_at,
    }


def _upsert_custom_scenario_rows(conn, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    _ensure_custom_scenarios_meta_table(conn)
    conn.executemany(
        """
        INSERT INTO custom_scenarios (
            scenario_id, owner_user_id, instance_scope_key, payload_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(scenario_id) DO UPDATE SET
            owner_user_id = excluded.owner_user_id,
            instance_scope_key = excluded.instance_scope_key,
            payload_json = excluded.payload_json,
            created_at = excluded.created_at,
            updated_at = excluded.updated_at
        """,
        [
            (
                row["scenario_id"],
                row["owner_user_id"],
                row["instance_scope_key"],
                row["payload_json"],
                row["created_at"],
                row["updated_at"],
            )
            for row in rows
        ],
    )


def _capture_meta_storage_snapshot(
    *,
    backup_dir: Path,
    meta_index_db_path: str,
    session_rows: list[dict[str, Any]],
    report_owner_rows: list[dict[str, Any]],
    report_owner_absent: list[str],
    solution_share_rows: list[dict[str, Any]],
    solution_share_absent: list[str],
    custom_scenario_rows: list[dict[str, Any]],
) -> Optional[Path]:
    if not backup_dir or not _use_meta_index_storage(meta_index_db_path):
        return None
    snapshot = {
        "snapshot_type": "meta_storage_state",
        "captured_at": utc_now_iso(),
        "meta_index_db_path": normalize_db_cache_key(meta_index_db_path),
        "session_store_rows": session_rows,
        "report_owner_rows": report_owner_rows,
        "report_owner_absent": sorted({str(name).strip() for name in report_owner_absent if str(name).strip()}),
        "solution_share_rows": solution_share_rows,
        "solution_share_absent": sorted({str(token).strip() for token in solution_share_absent if str(token).strip()}),
        "custom_scenario_rows": custom_scenario_rows,
    }
    snapshot_path = backup_dir / "meta" / "meta-storage-snapshot.json"
    _write_json_snapshot(snapshot_path, snapshot)
    return snapshot_path


def restore_meta_storage_snapshot(*, snapshot_path: Path, meta_index_db_path: str) -> dict[str, int]:
    snapshot = _load_json_snapshot(snapshot_path)
    if not snapshot:
        raise RuntimeError(f"元数据快照不存在或无效: {snapshot_path}")

    snapshot_meta_path = normalize_db_cache_key(snapshot.get("meta_index_db_path"))
    current_meta_path = normalize_db_cache_key(meta_index_db_path)
    if snapshot_meta_path and current_meta_path and snapshot_meta_path != current_meta_path:
        raise RuntimeError("当前元数据数据库与备份快照记录不一致，已拒绝回滚")

    session_rows = [item for item in snapshot.get("session_store_rows", []) if isinstance(item, dict)]
    report_owner_rows = [item for item in snapshot.get("report_owner_rows", []) if isinstance(item, dict)]
    report_owner_absent = [str(item).strip() for item in snapshot.get("report_owner_absent", []) if str(item).strip()]
    solution_share_rows = [item for item in snapshot.get("solution_share_rows", []) if isinstance(item, dict)]
    solution_share_absent = [str(item).strip() for item in snapshot.get("solution_share_absent", []) if str(item).strip()]
    custom_scenario_rows = [item for item in snapshot.get("custom_scenario_rows", []) if isinstance(item, dict)]

    restored = {
        "session_store_rows": 0,
        "report_owner_rows": 0,
        "report_owner_deleted": 0,
        "solution_share_rows": 0,
        "solution_share_deleted": 0,
        "custom_scenario_rows": 0,
    }

    with get_meta_index_connection(meta_index_db_path) as conn:
        _upsert_session_store_rows(conn, session_rows)
        restored["session_store_rows"] = len(session_rows)

        for row in report_owner_rows:
            conn.execute(
                """
                INSERT INTO report_meta_owners(file_name, owner_user_id, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(file_name) DO UPDATE SET
                    owner_user_id = excluded.owner_user_id,
                    updated_at = excluded.updated_at
                """,
                (
                    str(row.get("file_name") or "").strip(),
                    parse_owner_id(row.get("owner_user_id")),
                    str(row.get("updated_at") or "").strip() or utc_now_iso(),
                ),
            )
        restored["report_owner_rows"] = len(report_owner_rows)
        for file_name in report_owner_absent:
            conn.execute("DELETE FROM report_meta_owners WHERE file_name = ?", (file_name,))
        restored["report_owner_deleted"] = len(report_owner_absent)

        for row in solution_share_rows:
            conn.execute(
                """
                INSERT INTO report_meta_solution_shares(
                    share_token, report_name, owner_user_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(share_token) DO UPDATE SET
                    report_name = excluded.report_name,
                    owner_user_id = excluded.owner_user_id,
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at
                """,
                (
                    str(row.get("share_token") or "").strip(),
                    str(row.get("report_name") or "").strip(),
                    parse_owner_id(row.get("owner_user_id")),
                    str(row.get("created_at") or "").strip(),
                    str(row.get("updated_at") or "").strip() or utc_now_iso(),
                ),
            )
        restored["solution_share_rows"] = len(solution_share_rows)
        for token in solution_share_absent:
            conn.execute("DELETE FROM report_meta_solution_shares WHERE share_token = ?", (token,))
        restored["solution_share_deleted"] = len(solution_share_absent)

        _upsert_custom_scenario_rows(conn, custom_scenario_rows)
        restored["custom_scenario_rows"] = len(custom_scenario_rows)

    return restored


def _read_user_columns(conn) -> set[str]:
    return {str(row[1]) for row in conn.execute("PRAGMA table_info(users)").fetchall()}


def ensure_user_merge_columns(conn) -> None:
    user_columns = _read_user_columns(conn)
    if "merged_into_user_id" not in user_columns:
        conn.execute("ALTER TABLE users ADD COLUMN merged_into_user_id INTEGER")
    if "merged_at" not in user_columns:
        conn.execute("ALTER TABLE users ADD COLUMN merged_at TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_users_merged_into_user_id ON users(merged_into_user_id)")


def query_wechat_identities_by_user_id(auth_db_path: Path, user_id: int) -> list[dict[str, Any]]:
    with get_auth_db_connection(auth_db_path) as conn:
        rows = conn.execute(
            """
            SELECT id, user_id, app_id, openid, unionid, nickname, avatar_url, created_at, updated_at
            FROM wechat_identities
            WHERE user_id = ?
            ORDER BY updated_at DESC, id DESC
            """,
            (int(user_id),),
        ).fetchall()
    return [dict(row) for row in rows]


def count_bound_licenses(license_db_path: Path, user_id: int) -> int:
    with get_license_db_connection(license_db_path) as conn:
        row = conn.execute(
            "SELECT COUNT(1) AS count FROM licenses WHERE bound_user_id = ?",
            (int(user_id),),
        ).fetchone()
    try:
        return int((row or {})["count"] or 0)
    except Exception:
        return 0


def count_owned_sessions(sessions_dir: Path, owner_user_id: int, meta_index_db_path: Optional[str] = None) -> int:
    if _use_meta_index_storage(meta_index_db_path):
        with get_meta_index_connection(str(meta_index_db_path)) as conn:
            row = conn.execute(
                "SELECT COUNT(1) AS count FROM session_store WHERE owner_user_id = ?",
                (int(owner_user_id),),
            ).fetchone()
        return parse_owner_id((row or {}).get("count") if isinstance(row, dict) else row["count"] if row else 0)
    matched = 0
    for session_file in sessions_dir.glob("*.json"):
        try:
            payload = json.loads(session_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        if parse_owner_id(payload.get("owner_user_id")) == int(owner_user_id):
            matched += 1
    return matched


def count_owned_reports(
    reports_dir: Path,
    report_owners_file: Path,
    owner_user_id: int,
    meta_index_db_path: Optional[str] = None,
) -> int:
    matched = 0
    owners = load_report_owners(report_owners_file, meta_index_db_path=meta_index_db_path)
    for report_file in reports_dir.glob("*.md"):
        if parse_owner_id(owners.get(report_file.name, 0)) == int(owner_user_id):
            matched += 1
    return matched


def count_owned_custom_scenarios(
    custom_scenarios_dir: Path,
    owner_user_id: int,
    meta_index_db_path: Optional[str] = None,
) -> int:
    if _use_meta_index_storage(meta_index_db_path):
        with get_meta_index_connection(str(meta_index_db_path)) as conn:
            _ensure_custom_scenarios_meta_table(conn)
            row = conn.execute(
                "SELECT COUNT(1) AS count FROM custom_scenarios WHERE owner_user_id = ?",
                (int(owner_user_id),),
            ).fetchone()
        return parse_owner_id((row or {}).get("count") if isinstance(row, dict) else row["count"] if row else 0)

    matched = 0
    if not custom_scenarios_dir.exists():
        return 0
    for scenario_file in custom_scenarios_dir.glob("*.json"):
        try:
            payload = json.loads(scenario_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        if parse_owner_id(payload.get("owner_user_id")) == int(owner_user_id):
            matched += 1
    return matched


def count_owned_solution_shares(
    report_solution_shares_file: Path,
    owner_user_id: int,
    meta_index_db_path: Optional[str] = None,
) -> int:
    payload = load_solution_share_records(
        report_solution_shares_file,
        meta_index_db_path=meta_index_db_path,
    )
    matched = 0
    for record in payload.values():
        if not isinstance(record, dict):
            continue
        if parse_owner_id(record.get("owner_user_id")) == int(owner_user_id):
            matched += 1
    return matched


def build_account_merge_asset_counts(
    *,
    auth_db_path: Path,
    license_db_path: Path,
    sessions_dir: Path,
    reports_dir: Path,
    report_owners_file: Path,
    custom_scenarios_dir: Path,
    report_solution_shares_file: Path,
    meta_index_db_path: Optional[str] = None,
    user_id: int,
) -> dict[str, int]:
    return {
        "sessions": count_owned_sessions(sessions_dir, user_id, meta_index_db_path=meta_index_db_path),
        "reports": count_owned_reports(
            reports_dir,
            report_owners_file,
            user_id,
            meta_index_db_path=meta_index_db_path,
        ),
        "custom_scenarios": count_owned_custom_scenarios(
            custom_scenarios_dir,
            user_id,
            meta_index_db_path=meta_index_db_path,
        ),
        "solution_shares": count_owned_solution_shares(
            report_solution_shares_file,
            user_id,
            meta_index_db_path=meta_index_db_path,
        ),
        "licenses": count_bound_licenses(license_db_path, user_id),
        "wechat_identities": len(query_wechat_identities_by_user_id(auth_db_path, user_id)),
    }


def list_owned_session_records(
    sessions_dir: Path,
    owner_user_id: int,
    meta_index_db_path: Optional[str] = None,
) -> list[dict[str, Any]]:
    if _use_meta_index_storage(meta_index_db_path):
        with get_meta_index_connection(str(meta_index_db_path)) as conn:
            return _fetch_all_dicts(
                conn,
                """
                SELECT
                    session_id, file_name, owner_user_id, instance_scope_key,
                    payload_json, created_at, updated_at, payload_mtime_ns, payload_size
                FROM session_store
                WHERE owner_user_id = ?
                ORDER BY updated_at DESC, session_id DESC
                """,
                (int(owner_user_id),),
            )

    rows: list[dict[str, Any]] = []
    for session_file in sorted(sessions_dir.glob("*.json")):
        try:
            payload = json.loads(session_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        if parse_owner_id(payload.get("owner_user_id")) != int(owner_user_id):
            continue
        rows.append({
            "session_id": str(payload.get("session_id") or session_file.stem),
            "file_name": session_file.name,
            "payload_json": json.dumps(payload, ensure_ascii=False, indent=2),
        })
    return rows


def list_owned_report_names(
    reports_dir: Path,
    report_owners_file: Path,
    owner_user_id: int,
    meta_index_db_path: Optional[str] = None,
) -> list[str]:
    owners = load_report_owners(report_owners_file, meta_index_db_path=meta_index_db_path)
    return [
        report_file.name
        for report_file in sorted(reports_dir.glob("*.md"))
        if parse_owner_id(owners.get(report_file.name, 0)) == int(owner_user_id)
    ]


def list_owned_custom_scenario_records(
    custom_scenarios_dir: Path,
    owner_user_id: int,
    meta_index_db_path: Optional[str] = None,
) -> list[dict[str, Any]]:
    if _use_meta_index_storage(meta_index_db_path):
        with get_meta_index_connection(str(meta_index_db_path)) as conn:
            _ensure_custom_scenarios_meta_table(conn)
            return _fetch_all_dicts(
                conn,
                """
                SELECT scenario_id, owner_user_id, instance_scope_key, payload_json, created_at, updated_at
                FROM custom_scenarios
                WHERE owner_user_id = ?
                ORDER BY updated_at DESC, scenario_id DESC
                """,
                (int(owner_user_id),),
            )

    rows: list[dict[str, Any]] = []
    if not custom_scenarios_dir.exists():
        return rows
    for scenario_file in sorted(custom_scenarios_dir.glob("*.json")):
        try:
            payload = json.loads(scenario_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        if parse_owner_id(payload.get("owner_user_id")) != int(owner_user_id):
            continue
        rows.append({
            "scenario_id": str(payload.get("id") or scenario_file.stem),
            "owner_user_id": parse_owner_id(payload.get("owner_user_id")),
            "instance_scope_key": str(payload.get("instance_scope_key") or "").strip(),
            "payload_json": json.dumps(payload, ensure_ascii=False, indent=2),
            "created_at": str(payload.get("created_at") or "").strip(),
            "updated_at": str(payload.get("updated_at") or "").strip(),
            "file_name": scenario_file.name,
        })
    return rows


def list_owned_solution_share_records(
    report_solution_shares_file: Path,
    owner_user_id: int,
    meta_index_db_path: Optional[str] = None,
) -> dict[str, dict[str, Any]]:
    payload = load_solution_share_records(
        report_solution_shares_file,
        meta_index_db_path=meta_index_db_path,
    )
    return {
        str(token): dict(record)
        for token, record in payload.items()
        if isinstance(record, dict) and parse_owner_id(record.get("owner_user_id")) == int(owner_user_id)
    }


def _build_account_merge_summary(
    *,
    target_user: dict[str, Any],
    source_user: dict[str, Any],
    auth_db_path: Path,
    license_db_path: Path,
    source_asset_counts: dict[str, int],
    identity_type: str,
    identity_value: str,
    actor_user_id: Optional[int],
    backup_dir: Optional[Path],
    apply_mode: bool,
) -> dict[str, Any]:
    return {
        "generated_at": utc_now_iso(),
        "mode": "apply" if apply_mode else "dry-run",
        "operation_type": "account_merge",
        "identity_type": str(identity_type or "").strip(),
        "identity_value": str(identity_value or "").strip(),
        "actor_user_id": int(actor_user_id) if actor_user_id is not None else None,
        "target_user": target_user,
        "source_user": source_user,
        "auth_db_path": str(auth_db_path),
        "license_db_path": str(license_db_path),
        "backup_dir": str(backup_dir) if backup_dir else None,
        "sessions": {
            "matched": int(source_asset_counts.get("sessions", 0) or 0),
            "updated": int(source_asset_counts.get("sessions", 0) or 0),
            "examples": [],
        },
        "reports": {
            "matched": int(source_asset_counts.get("reports", 0) or 0),
            "updated": int(source_asset_counts.get("reports", 0) or 0),
            "examples": [],
        },
        "custom_scenarios": {
            "matched": int(source_asset_counts.get("custom_scenarios", 0) or 0),
            "updated": int(source_asset_counts.get("custom_scenarios", 0) or 0),
            "examples": [],
        },
        "solution_shares": {
            "matched": int(source_asset_counts.get("solution_shares", 0) or 0),
            "updated": int(source_asset_counts.get("solution_shares", 0) or 0),
            "examples": [],
        },
        "licenses": {
            "matched": int(source_asset_counts.get("licenses", 0) or 0),
            "updated": int(source_asset_counts.get("licenses", 0) or 0),
        },
        "wechat_identities": {
            "matched": int(source_asset_counts.get("wechat_identities", 0) or 0),
            "updated": int(source_asset_counts.get("wechat_identities", 0) or 0),
        },
        "user_record": {
            "source_marked_merged": False,
            "source_phone_cleared": False,
            "target_phone_transferred": False,
        },
        "db_snapshot": {
            "captured": False,
            "snapshot_file": "",
            "restore_mode": "file_backup" if db_target_supports_file_backup(auth_db_path) and db_target_supports_file_backup(license_db_path) else "row_snapshot",
        },
    }


def _generate_merged_placeholder_email(conn, source_user_id: int) -> str:
    base = f"merged_{int(source_user_id)}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    for attempt in range(12):
        suffix = "" if attempt == 0 else f"_{attempt + 1}"
        candidate = f"{base}{suffix}@merged.local"
        exists = conn.execute("SELECT 1 FROM users WHERE email = ? LIMIT 1", (candidate,)).fetchone()
        if not exists:
            return candidate
    return f"merged_{int(source_user_id)}_{utc_now_tag()}_{int(datetime.now().timestamp())}@merged.local"


def run_account_merge(
    *,
    auth_db_path: Path,
    license_db_path: Path,
    sessions_dir: Path,
    reports_dir: Path,
    report_owners_file: Path,
    report_solution_shares_file: Path,
    meta_index_db_path: Optional[str] = None,
    custom_scenarios_dir: Path,
    backup_root: Path,
    target_user_id: int,
    source_user_id: int,
    identity_type: str,
    identity_value: str = "",
    actor_user_id: Optional[int] = None,
    apply_mode: bool = False,
    backup_id: str = "",
    max_examples: int = 20,
) -> dict[str, Any]:
    normalized_target_user_id = int(target_user_id or 0)
    normalized_source_user_id = int(source_user_id or 0)
    if normalized_target_user_id <= 0 or normalized_source_user_id <= 0:
        raise ValueError("账号合并参数无效")
    if normalized_target_user_id == normalized_source_user_id:
        raise ValueError("源账号与目标账号不能相同")

    target_user = resolve_user_reference(auth_db_path, user_id=normalized_target_user_id)
    source_user = resolve_user_reference(auth_db_path, user_id=normalized_source_user_id)
    source_asset_counts = build_account_merge_asset_counts(
        auth_db_path=auth_db_path,
        license_db_path=license_db_path,
        sessions_dir=sessions_dir,
        reports_dir=reports_dir,
        report_owners_file=report_owners_file,
        custom_scenarios_dir=custom_scenarios_dir,
        report_solution_shares_file=report_solution_shares_file,
        meta_index_db_path=meta_index_db_path,
        user_id=normalized_source_user_id,
    )
    backup_dir = prepare_backup_dir(backup_root, backup_id, normalized_target_user_id, apply_mode)
    summary = _build_account_merge_summary(
        target_user=target_user,
        source_user=source_user,
        auth_db_path=auth_db_path,
        license_db_path=license_db_path,
        source_asset_counts=source_asset_counts,
        identity_type=identity_type,
        identity_value=identity_value,
        actor_user_id=actor_user_id,
        backup_dir=backup_dir,
        apply_mode=apply_mode,
    )

    sessions_examples: list[dict[str, Any]] = []
    reports_examples: list[dict[str, Any]] = []
    scenarios_examples: list[dict[str, Any]] = []
    shares_examples: list[dict[str, Any]] = []
    examples_limit = max(1, min(int(max_examples or 20), 50))

    source_session_rows = list_owned_session_records(
        sessions_dir,
        normalized_source_user_id,
        meta_index_db_path=meta_index_db_path,
    )
    source_session_files = [
        sessions_dir / str(row.get("file_name") or "").strip()
        for row in source_session_rows
        if str(row.get("file_name") or "").strip()
    ]
    for session_row in source_session_rows:
        session_name = str(session_row.get("file_name") or "").strip()
        session_id = str(session_row.get("session_id") or "").strip() or Path(session_name).stem
        if len(sessions_examples) < examples_limit:
            sessions_examples.append(
                {
                    "session_file": session_name,
                    "session_id": session_id,
                    "from_owner": normalized_source_user_id,
                    "to_owner": normalized_target_user_id,
                }
            )
    summary["sessions"]["examples"] = sessions_examples

    source_report_names = list_owned_report_names(
        reports_dir,
        report_owners_file,
        normalized_source_user_id,
        meta_index_db_path=meta_index_db_path,
    )
    owners = load_report_owners(report_owners_file, meta_index_db_path=meta_index_db_path)
    for report_name in source_report_names:
        if len(reports_examples) < examples_limit:
            reports_examples.append(
                {
                    "report_name": report_name,
                    "from_owner": normalized_source_user_id,
                    "to_owner": normalized_target_user_id,
                }
            )
    summary["reports"]["examples"] = reports_examples

    source_scenario_rows = list_owned_custom_scenario_records(
        custom_scenarios_dir,
        normalized_source_user_id,
        meta_index_db_path=meta_index_db_path,
    )
    source_scenario_files = [
        custom_scenarios_dir / str(row.get("file_name") or "").strip()
        for row in source_scenario_rows
        if str(row.get("file_name") or "").strip()
    ]
    for scenario_row in source_scenario_rows:
        scenario_name = str(scenario_row.get("file_name") or "").strip() or f"{scenario_row.get('scenario_id')}.json"
        if len(scenarios_examples) < examples_limit:
            scenarios_examples.append(
                {
                    "scenario_id": str(scenario_row.get("scenario_id") or "").strip(),
                    "file_name": scenario_name,
                    "from_owner": normalized_source_user_id,
                    "to_owner": normalized_target_user_id,
                }
            )
    summary["custom_scenarios"]["examples"] = scenarios_examples

    solution_shares_payload = list_owned_solution_share_records(
        report_solution_shares_file,
        normalized_source_user_id,
        meta_index_db_path=meta_index_db_path,
    )
    source_share_tokens: list[str] = []
    for token, record in solution_shares_payload.items():
        source_share_tokens.append(str(token))
        if len(shares_examples) < examples_limit:
            shares_examples.append(
                {
                    "share_token": str(token),
                    "report_name": str(record.get("report_name") or "").strip(),
                    "from_owner": normalized_source_user_id,
                    "to_owner": normalized_target_user_id,
                }
            )
    summary["solution_shares"]["examples"] = shares_examples

    with get_auth_db_connection(auth_db_path) as conn:
        ensure_user_merge_columns(conn)
        target_row = conn.execute(
            "SELECT id, email, phone, created_at, merged_into_user_id, merged_at FROM users WHERE id = ? LIMIT 1",
            (normalized_target_user_id,),
        ).fetchone()
        source_row = conn.execute(
            "SELECT id, email, phone, created_at, merged_into_user_id, merged_at FROM users WHERE id = ? LIMIT 1",
            (normalized_source_user_id,),
        ).fetchone()
        if not target_row or not source_row:
            raise RuntimeError("待合并账号不存在")
        if parse_owner_id(source_row["merged_into_user_id"]) > 0:
            raise RuntimeError("源账号已被合并，请刷新页面后重试")

        target_phone = normalize_phone_number(str(target_row["phone"] or "").strip())
        source_phone = normalize_phone_number(str(source_row["phone"] or "").strip())
        target_wechat_rows = query_wechat_identities_by_user_id(auth_db_path, normalized_target_user_id)
        source_wechat_rows = query_wechat_identities_by_user_id(auth_db_path, normalized_source_user_id)

        if target_phone and source_phone and target_phone != source_phone:
            raise RuntimeError("两个账号都已绑定不同手机号，暂不支持自助合并，请联系管理员")

        if target_wechat_rows and source_wechat_rows:
            source_keys = {
                (
                    str(item.get("app_id") or "").strip(),
                    str(item.get("openid") or "").strip(),
                    str(item.get("unionid") or "").strip(),
                )
                for item in source_wechat_rows
            }
            target_keys = {
                (
                    str(item.get("app_id") or "").strip(),
                    str(item.get("openid") or "").strip(),
                    str(item.get("unionid") or "").strip(),
                )
                for item in target_wechat_rows
            }
            if any(key not in target_keys for key in source_keys):
                raise RuntimeError("两个账号都已绑定不同微信，暂不支持自助合并，请联系管理员")

        if not apply_mode:
            return summary

        if backup_dir:
            if db_target_supports_file_backup(auth_db_path):
                backup_file_once(Path(auth_db_path), backup_dir / "auth" / db_target_name(auth_db_path, "users.db"))
            if db_target_supports_file_backup(license_db_path):
                backup_file_once(Path(license_db_path), backup_dir / "licenses" / db_target_name(license_db_path, "licenses.db"))
            if not (db_target_supports_file_backup(auth_db_path) and db_target_supports_file_backup(license_db_path)):
                snapshot_path = capture_account_merge_db_snapshot(
                    backup_dir=backup_dir,
                    auth_db_path=auth_db_path,
                    license_db_path=license_db_path,
                    source_user_id=normalized_source_user_id,
                    target_user_id=normalized_target_user_id,
                )
                if snapshot_path is not None:
                    summary["db_snapshot"]["captured"] = True
                    summary["db_snapshot"]["snapshot_file"] = str(snapshot_path)
            if _use_meta_index_storage(meta_index_db_path):
                meta_snapshot_path = _capture_meta_storage_snapshot(
                    backup_dir=backup_dir,
                    meta_index_db_path=str(meta_index_db_path),
                    session_rows=source_session_rows,
                    report_owner_rows=[
                        {
                            "file_name": report_name,
                            "owner_user_id": owners.get(report_name, 0),
                            "updated_at": utc_now_iso(),
                        }
                        for report_name in source_report_names
                    ],
                    report_owner_absent=[],
                    solution_share_rows=[
                        {
                            "share_token": token,
                            **dict(record),
                        }
                        for token, record in solution_shares_payload.items()
                    ],
                    solution_share_absent=[],
                    custom_scenario_rows=source_scenario_rows,
                )
                if meta_snapshot_path is not None:
                    summary["meta_storage_snapshot"] = {
                        "captured": True,
                        "snapshot_file": str(meta_snapshot_path),
                    }
            else:
                for session_file in source_session_files:
                    backup_file_once(session_file, backup_dir / "sessions" / session_file.name)
                if source_report_names:
                    owners_backup = backup_dir / "reports" / ".owners.json"
                    owners_absent_marker = backup_dir / "reports" / ".owners.absent"
                    if report_owners_file.exists():
                        backup_file_once(report_owners_file, owners_backup)
                    else:
                        backup_absent_marker_once(owners_absent_marker)
                if source_share_tokens:
                    shares_backup = backup_dir / "reports" / ".solution_shares.json"
                    shares_absent_marker = backup_dir / "reports" / ".solution_shares.absent"
                    if report_solution_shares_file.exists():
                        backup_file_once(report_solution_shares_file, shares_backup)
                    else:
                        backup_absent_marker_once(shares_absent_marker)
            if _use_meta_index_storage(meta_index_db_path):
                pass
            else:
                for scenario_file in source_scenario_files:
                    backup_file_once(scenario_file, backup_dir / "custom_scenarios" / scenario_file.name)

        now_iso = utc_now_iso()
        with get_auth_db_connection(auth_db_path) as conn:
            ensure_user_merge_columns(conn)
            conn.execute("BEGIN IMMEDIATE")
            target_row = conn.execute(
                "SELECT id, email, phone FROM users WHERE id = ? LIMIT 1",
                (normalized_target_user_id,),
            ).fetchone()
            source_row = conn.execute(
                "SELECT id, email, phone, merged_into_user_id FROM users WHERE id = ? LIMIT 1",
                (normalized_source_user_id,),
            ).fetchone()
            if not target_row or not source_row:
                conn.rollback()
                raise RuntimeError("待合并账号不存在")
            if parse_owner_id(source_row["merged_into_user_id"]) > 0:
                conn.rollback()
                raise RuntimeError("源账号已被合并，请刷新页面后重试")

            target_phone = normalize_phone_number(str(target_row["phone"] or "").strip())
            source_phone = normalize_phone_number(str(source_row["phone"] or "").strip())
            if source_phone:
                summary["user_record"]["source_phone_cleared"] = True

            conn.execute(
                """
                UPDATE wechat_identities
                SET user_id = ?, updated_at = ?
                WHERE user_id = ?
                """,
                (normalized_target_user_id, now_iso, normalized_source_user_id),
            )

            source_email = str(source_row["email"] or "").strip()
            merged_email = source_email or _generate_merged_placeholder_email(conn, normalized_source_user_id)
            conn.execute(
                """
                UPDATE users
                SET email = ?, phone = NULL, merged_into_user_id = ?, merged_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    merged_email,
                    normalized_target_user_id,
                    now_iso,
                    now_iso,
                    normalized_source_user_id,
                ),
            )
            summary["user_record"]["source_marked_merged"] = True
            if not target_phone and source_phone:
                conn.execute(
                    "UPDATE users SET phone = ?, updated_at = ? WHERE id = ?",
                    (source_phone, now_iso, normalized_target_user_id),
                )
                summary["user_record"]["target_phone_transferred"] = True
            conn.execute(
                "UPDATE users SET updated_at = ? WHERE id = ?",
                (now_iso, normalized_target_user_id),
            )
            conn.commit()

        with get_license_db_connection(license_db_path) as license_conn:
            license_conn.execute("BEGIN IMMEDIATE")
            license_conn.execute(
                """
                UPDATE licenses
                SET bound_user_id = ?, updated_at = ?
                WHERE bound_user_id = ?
                """,
                (normalized_target_user_id, now_iso, normalized_source_user_id),
            )
            license_conn.commit()

        if _use_meta_index_storage(meta_index_db_path):
            with get_meta_index_connection(str(meta_index_db_path)) as meta_conn:
                updated_session_rows = [
                    _build_session_store_update_row(row, normalized_target_user_id, now_iso)
                    for row in source_session_rows
                ]
                _upsert_session_store_rows(meta_conn, updated_session_rows)
                for report_name in source_report_names:
                    meta_conn.execute(
                        """
                        INSERT INTO report_meta_owners(file_name, owner_user_id, updated_at)
                        VALUES (?, ?, ?)
                        ON CONFLICT(file_name) DO UPDATE SET
                            owner_user_id = excluded.owner_user_id,
                            updated_at = excluded.updated_at
                        """,
                        (report_name, normalized_target_user_id, now_iso),
                    )
                for token, record in solution_shares_payload.items():
                    meta_conn.execute(
                        """
                        INSERT INTO report_meta_solution_shares(
                            share_token, report_name, owner_user_id, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(share_token) DO UPDATE SET
                            report_name = excluded.report_name,
                            owner_user_id = excluded.owner_user_id,
                            created_at = excluded.created_at,
                            updated_at = excluded.updated_at
                        """,
                        (
                            str(token),
                            str(record.get("report_name") or "").strip(),
                            normalized_target_user_id,
                            str(record.get("created_at") or "").strip(),
                            now_iso,
                        ),
                    )
                updated_scenario_rows = [
                    _build_custom_scenario_update_row(row, normalized_target_user_id, now_iso)
                    for row in source_scenario_rows
                ]
                _upsert_custom_scenario_rows(meta_conn, updated_scenario_rows)
        else:
            for session_file in source_session_files:
                payload = json.loads(session_file.read_text(encoding="utf-8"))
                if not isinstance(payload, dict):
                    continue
                payload["owner_user_id"] = normalized_target_user_id
                session_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

            if source_report_names:
                for report_name in source_report_names:
                    owners[report_name] = normalized_target_user_id
                save_report_owners(report_owners_file, owners)

            if source_share_tokens and isinstance(solution_shares_payload, dict):
                for token in source_share_tokens:
                    record = solution_shares_payload.get(token)
                    if isinstance(record, dict):
                        record["owner_user_id"] = normalized_target_user_id
                        record["updated_at"] = now_iso
                save_solution_share_records(
                    report_solution_shares_file,
                    solution_shares_payload,
                    meta_index_db_path=meta_index_db_path,
                )

        if not _use_meta_index_storage(meta_index_db_path):
            for scenario_file in source_scenario_files:
                payload = json.loads(scenario_file.read_text(encoding="utf-8"))
                if not isinstance(payload, dict):
                    continue
                payload["owner_user_id"] = normalized_target_user_id
                meta = payload.get("meta")
                if isinstance(meta, dict) and "owner_user_id" in meta:
                    meta["owner_user_id"] = normalized_target_user_id
                scenario_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        if backup_dir:
            metadata_file = backup_dir / "metadata.json"
            metadata_file.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    return summary


def _build_migration_summary(
    *,
    target_user: dict[str, Any],
    auth_db_path: Path,
    scope: str,
    from_user_id: Optional[int],
    kinds: set[str],
    backup_dir: Optional[Path],
    apply_mode: bool,
) -> dict[str, Any]:
    return {
        "generated_at": utc_now_iso(),
        "mode": "apply" if apply_mode else "dry-run",
        "scope": scope,
        "from_user_id": int(from_user_id) if from_user_id is not None else None,
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


def run_ownership_migration(
    *,
    auth_db_path: Path,
    sessions_dir: Path,
    reports_dir: Path,
    report_owners_file: Path,
    meta_index_db_path: Optional[str] = None,
    backup_root: Path,
    to_user_id: Optional[int] = None,
    to_account: str = "",
    scope: str = "unowned",
    from_user_id: Optional[int] = None,
    kinds: Any = "sessions,reports",
    apply_mode: bool = False,
    backup_id: str = "",
    max_examples: int = 20,
) -> dict[str, Any]:
    if scope not in VALID_OWNERSHIP_SCOPES:
        raise ValueError("scope 必须是 unowned / all / from-user")
    if scope == "from-user" and from_user_id is None:
        raise ValueError("scope=from-user 时必须提供 from_user_id")

    parsed_kinds = parse_kinds(kinds)
    target_user = resolve_target_user(auth_db_path, to_user_id, to_account)
    target_user_id = int(target_user["id"])

    if scope == "from-user" and int(from_user_id or 0) == target_user_id:
        raise ValueError("from_user_id 不能与目标用户相同")

    if "sessions" in parsed_kinds and not _use_meta_index_storage(meta_index_db_path) and not sessions_dir.exists():
        raise RuntimeError("会话目录不存在，无法迁移本地会话归属")
    if "reports" in parsed_kinds and not reports_dir.exists():
        raise RuntimeError("报告目录不存在，无法迁移报告归属")

    backup_dir = prepare_backup_dir(backup_root, backup_id, target_user_id, apply_mode)
    summary = _build_migration_summary(
        target_user=target_user,
        auth_db_path=auth_db_path,
        scope=scope,
        from_user_id=from_user_id,
        kinds=parsed_kinds,
        backup_dir=backup_dir,
        apply_mode=apply_mode,
    )

    sessions_examples: list[dict[str, Any]] = []
    reports_examples: list[dict[str, Any]] = []
    examples_limit = max(1, int(max_examples or 20))
    meta_snapshot_session_rows: list[dict[str, Any]] = []
    meta_snapshot_report_owner_rows: list[dict[str, Any]] = []
    meta_snapshot_report_owner_absent: list[str] = []

    if "sessions" in parsed_kinds:
        if _use_meta_index_storage(meta_index_db_path):
            with get_meta_index_connection(str(meta_index_db_path)) as conn:
                session_items: list[dict[str, Any] | Path] = _fetch_all_dicts(
                    conn,
                    """
                    SELECT
                        session_id, file_name, owner_user_id, instance_scope_key,
                        payload_json, created_at, updated_at, payload_mtime_ns, payload_size
                    FROM session_store
                    ORDER BY updated_at DESC, session_id DESC
                    """,
                )
        else:
            session_items = list(sorted(sessions_dir.glob("*.json")))

        matched_session_rows: list[dict[str, Any]] = []
        for session_item in session_items:
            summary["sessions"]["scanned"] += 1
            if isinstance(session_item, dict):
                data_text = str(session_item.get("payload_json") or "").strip()
                try:
                    data = json.loads(data_text) if data_text else {}
                except Exception:
                    summary["sessions"]["skipped_invalid"] += 1
                    continue
                session_name = str(session_item.get("file_name") or "").strip()
            else:
                session_file = session_item
                try:
                    data = json.loads(session_file.read_text(encoding="utf-8"))
                except Exception:
                    summary["sessions"]["skipped_invalid"] += 1
                    continue
                session_name = session_file.name

            if not isinstance(data, dict):
                summary["sessions"]["skipped_invalid"] += 1
                continue

            current_owner = parse_owner_id(data.get("owner_user_id"))
            should_migrate = should_migrate_owner(current_owner, target_user_id, scope, from_user_id)
            if not should_migrate:
                continue

            summary["sessions"]["matched"] += 1
            summary["sessions"]["updated"] += 1
            example = {
                "session_file": session_name,
                "session_id": data.get("session_id") or Path(session_name).stem,
                "from_owner": current_owner,
                "to_owner": target_user_id,
            }
            if len(sessions_examples) < examples_limit:
                sessions_examples.append(example)

            if apply_mode:
                if isinstance(session_item, dict):
                    matched_session_rows.append(dict(session_item))
                    meta_snapshot_session_rows.append(dict(session_item))
                else:
                    if backup_dir:
                        backup_file_once(session_file, backup_dir / "sessions" / session_file.name)
                    data["owner_user_id"] = target_user_id
                    session_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

        if apply_mode and _use_meta_index_storage(meta_index_db_path) and matched_session_rows:
            updated_rows = [
                _build_session_store_update_row(row, target_user_id, utc_now_iso())
                for row in matched_session_rows
            ]
            with get_meta_index_connection(str(meta_index_db_path)) as conn:
                _upsert_session_store_rows(conn, updated_rows)

    if "reports" in parsed_kinds:
        owners = load_report_owners(report_owners_file, meta_index_db_path=meta_index_db_path)
        matched_report_names: list[str] = []
        absent_report_names: list[str] = []
        for report_file in sorted(reports_dir.glob("*.md")):
            summary["reports"]["scanned"] += 1
            report_name = report_file.name
            current_owner = parse_owner_id(owners.get(report_name, 0))
            should_migrate = should_migrate_owner(current_owner, target_user_id, scope, from_user_id)
            if not should_migrate:
                continue

            summary["reports"]["matched"] += 1
            summary["reports"]["updated"] += 1
            example = {
                "report_name": report_name,
                "from_owner": current_owner,
                "to_owner": target_user_id,
            }
            if len(reports_examples) < examples_limit:
                reports_examples.append(example)

            if apply_mode:
                matched_report_names.append(report_name)
                if report_name not in owners:
                    absent_report_names.append(report_name)
                    if _use_meta_index_storage(meta_index_db_path):
                        meta_snapshot_report_owner_absent.append(report_name)
                elif _use_meta_index_storage(meta_index_db_path):
                    meta_snapshot_report_owner_rows.append(
                        {
                            "file_name": report_name,
                            "owner_user_id": parse_owner_id(owners.get(report_name, 0)),
                            "updated_at": utc_now_iso(),
                        }
                    )
                owners[report_name] = target_user_id

        if apply_mode and summary["reports"]["updated"] > 0:
            if _use_meta_index_storage(meta_index_db_path):
                save_report_owners(report_owners_file, owners, meta_index_db_path=meta_index_db_path)
            else:
                if backup_dir:
                    owners_backup = backup_dir / "reports" / ".owners.json"
                    owners_absent_marker = backup_dir / "reports" / ".owners.absent"
                    if report_owners_file.exists():
                        backup_file_once(report_owners_file, owners_backup)
                    elif not owners_absent_marker.exists():
                        owners_absent_marker.write_text("absent\n", encoding="utf-8")
                save_report_owners(report_owners_file, owners)

    if apply_mode and backup_dir and _use_meta_index_storage(meta_index_db_path):
        snapshot_path = _capture_meta_storage_snapshot(
            backup_dir=backup_dir,
            meta_index_db_path=str(meta_index_db_path),
            session_rows=meta_snapshot_session_rows,
            report_owner_rows=meta_snapshot_report_owner_rows,
            report_owner_absent=meta_snapshot_report_owner_absent,
            solution_share_rows=[],
            solution_share_absent=[],
            custom_scenario_rows=[],
        )
        if snapshot_path is not None:
            summary["meta_storage_snapshot"] = {
                "captured": True,
                "snapshot_file": str(snapshot_path),
            }

    summary["sessions"]["examples"] = sessions_examples
    summary["reports"]["examples"] = reports_examples

    if apply_mode and backup_dir:
        metadata_file = backup_dir / "metadata.json"
        metadata_file.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    return summary


def audit_ownership(
    *,
    auth_db_path: Path,
    sessions_dir: Path,
    reports_dir: Path,
    report_owners_file: Path,
    meta_index_db_path: Optional[str] = None,
    user_id: Optional[int] = None,
    user_account: str = "",
    kinds: Any = "sessions,reports",
) -> dict[str, Any]:
    target_user = resolve_user_reference(auth_db_path, user_id=user_id, user_account=user_account)
    target_user_id = int(target_user["id"])
    parsed_kinds = parse_kinds(kinds)

    sessions_owned = 0
    sessions_total = 0
    sessions_invalid = 0
    if "sessions" in parsed_kinds:
        if _use_meta_index_storage(meta_index_db_path):
            with get_meta_index_connection(str(meta_index_db_path)) as conn:
                total_row = conn.execute("SELECT COUNT(1) AS count FROM session_store").fetchone()
                owned_row = conn.execute(
                    "SELECT COUNT(1) AS count FROM session_store WHERE owner_user_id = ?",
                    (target_user_id,),
                ).fetchone()
            sessions_total = int((total_row["count"] if total_row else 0) or 0)
            sessions_owned = int((owned_row["count"] if owned_row else 0) or 0)
        else:
            for session_file in sessions_dir.glob("*.json"):
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
    if "reports" in parsed_kinds:
        owners = load_report_owners(report_owners_file, meta_index_db_path=meta_index_db_path)
        for report_file in reports_dir.glob("*.md"):
            reports_total += 1
            if parse_owner_id(owners.get(report_file.name, 0)) == target_user_id:
                reports_owned += 1

    return {
        "generated_at": utc_now_iso(),
        "user": target_user,
        "kinds": sorted(list(parsed_kinds)),
        "sessions": {
            "owned": sessions_owned,
            "total": sessions_total,
            "invalid": sessions_invalid,
        },
        "reports": {
            "owned": reports_owned,
            "total": reports_total,
        },
    }


def _resolve_backup_dir(backup_root: Path, backup_id: Optional[str] = None, backup_dir: Optional[Path] = None) -> Path:
    if backup_dir is not None:
        resolved = Path(backup_dir).expanduser()
        if not resolved.is_absolute():
            resolved = (ROOT_DIR / resolved).resolve()
        return resolved

    backup_root = Path(backup_root).expanduser()
    if not backup_root.is_absolute():
        backup_root = (ROOT_DIR / backup_root).resolve()
    backup_id_text = str(backup_id or "").strip()
    if not backup_id_text or "/" in backup_id_text or "\\" in backup_id_text or ".." in backup_id_text:
        raise ValueError("backup_id 无效")
    return (backup_root / backup_id_text).resolve()


def rollback_ownership_migration(
    *,
    backup_root: Path,
    sessions_dir: Path,
    reports_dir: Path,
    report_owners_file: Path,
    auth_db_path: Optional[Path] = None,
    license_db_path: Optional[Path] = None,
    meta_index_db_path: Optional[str] = None,
    custom_scenarios_dir: Optional[Path] = None,
    report_solution_shares_file: Optional[Path] = None,
    backup_id: Optional[str] = None,
    backup_dir: Optional[Path] = None,
) -> dict[str, Any]:
    resolved_backup_dir = _resolve_backup_dir(backup_root, backup_id=backup_id, backup_dir=backup_dir)
    if not resolved_backup_dir.exists() or not resolved_backup_dir.is_dir():
        raise RuntimeError(f"备份目录不存在: {resolved_backup_dir}")

    metadata = _load_json_snapshot(resolved_backup_dir / "metadata.json")
    operation_type = str(metadata.get("operation_type") or "ownership_migration").strip() or "ownership_migration"

    sessions_backup_dir = resolved_backup_dir / "sessions"
    reports_backup_dir = resolved_backup_dir / "reports"

    restored_sessions = 0
    if sessions_backup_dir.exists():
        for backup_file in sorted(sessions_backup_dir.glob("*.json")):
            target_file = sessions_dir / backup_file.name
            target_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup_file, target_file)
            restored_sessions += 1

    owners_backup = reports_backup_dir / ".owners.json"
    owners_absent_marker = reports_backup_dir / ".owners.absent"
    solution_shares_backup = reports_backup_dir / ".solution_shares.json"
    solution_shares_absent_marker = reports_backup_dir / ".solution_shares.absent"
    owners_restored = False
    owners_removed = False
    solution_shares_restored = False
    solution_shares_removed = False
    meta_storage_snapshot_restored = False

    if owners_backup.exists():
        report_owners_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(owners_backup, report_owners_file)
        owners_restored = True
    elif owners_absent_marker.exists():
        if report_owners_file.exists():
            report_owners_file.unlink()
        owners_removed = True

    if report_solution_shares_file is not None:
        if solution_shares_backup.exists():
            report_solution_shares_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(solution_shares_backup, report_solution_shares_file)
            solution_shares_restored = True
        elif solution_shares_absent_marker.exists():
            if report_solution_shares_file.exists():
                report_solution_shares_file.unlink()
            solution_shares_removed = True

    restored_custom_scenarios = 0
    custom_scenarios_backup_dir = resolved_backup_dir / "custom_scenarios"
    if custom_scenarios_dir is not None and custom_scenarios_backup_dir.exists():
        custom_scenarios_dir.mkdir(parents=True, exist_ok=True)
        for backup_file in sorted(custom_scenarios_backup_dir.glob("*.json")):
            target_file = custom_scenarios_dir / backup_file.name
            shutil.copy2(backup_file, target_file)
            restored_custom_scenarios += 1

    auth_db_restored = False
    auth_db_snapshot_restored = False
    auth_backup_file = resolved_backup_dir / "auth" / "users.db"
    if not auth_backup_file.exists():
        auth_candidates = sorted((resolved_backup_dir / "auth").glob("*.db"))
        auth_backup_file = auth_candidates[0] if auth_candidates else auth_backup_file
    if auth_db_path is not None and auth_backup_file.exists():
        if not db_target_supports_file_backup(auth_db_path):
            raise RuntimeError("当前使用 PostgreSQL，暂不支持通过文件备份回滚鉴权数据库")
        Path(auth_db_path).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(auth_backup_file, Path(auth_db_path))
        auth_db_restored = True

    license_db_restored = False
    license_db_snapshot_restored = False
    license_backup_file = resolved_backup_dir / "licenses" / "licenses.db"
    if not license_backup_file.exists():
        license_candidates = sorted((resolved_backup_dir / "licenses").glob("*.db"))
        license_backup_file = license_candidates[0] if license_candidates else license_backup_file
    if license_db_path is not None and license_backup_file.exists():
        if not db_target_supports_file_backup(license_db_path):
            raise RuntimeError("当前使用 PostgreSQL，暂不支持通过文件备份回滚 License 数据库")
        Path(license_db_path).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(license_backup_file, Path(license_db_path))
        license_db_restored = True

    if operation_type == "account_merge" and auth_db_path is not None and license_db_path is not None:
        snapshot_path = resolved_backup_dir / "auth" / "account-merge-db-snapshot.json"
        if snapshot_path.exists() and not (auth_db_restored or license_db_restored):
            restored_counts = restore_account_merge_db_snapshot(
                snapshot_path=snapshot_path,
                auth_db_path=auth_db_path,
                license_db_path=license_db_path,
            )
            auth_db_snapshot_restored = restored_counts.get("users", 0) > 0 or restored_counts.get("wechat_identities", 0) > 0
            license_db_snapshot_restored = restored_counts.get("licenses", 0) > 0
        elif snapshot_path.exists():
            # 已执行文件级数据库回滚时，无需再次写回行级快照
            pass
        elif not (auth_db_restored and license_db_restored) and not (
            db_target_supports_file_backup(auth_db_path) and db_target_supports_file_backup(license_db_path)
        ):
            raise RuntimeError("当前为 PostgreSQL 账号合并记录，但缺少数据库行级快照，无法安全回滚")

    meta_snapshot_path = resolved_backup_dir / "meta" / "meta-storage-snapshot.json"
    if meta_snapshot_path.exists():
        if not _use_meta_index_storage(meta_index_db_path):
            raise RuntimeError("备份包含元数据数据库快照，但当前未提供 meta_index_db_path，无法安全回滚")
        restored_meta_counts = restore_meta_storage_snapshot(
            snapshot_path=meta_snapshot_path,
            meta_index_db_path=str(meta_index_db_path),
        )
        meta_storage_snapshot_restored = any(int(value or 0) > 0 for value in restored_meta_counts.values())

    result = {
        "backup_id": resolved_backup_dir.name,
        "backup_dir": str(resolved_backup_dir),
        "operation_type": operation_type,
        "restored_sessions": restored_sessions,
        "owners_restored": owners_restored,
        "owners_removed": owners_removed,
        "solution_shares_restored": solution_shares_restored,
        "solution_shares_removed": solution_shares_removed,
        "restored_custom_scenarios": restored_custom_scenarios,
        "auth_db_restored": auth_db_restored,
        "license_db_restored": license_db_restored,
        "auth_db_snapshot_restored": auth_db_snapshot_restored,
        "license_db_snapshot_restored": license_db_snapshot_restored,
        "meta_storage_snapshot_restored": meta_storage_snapshot_restored,
        "rolled_back_at": utc_now_iso(),
    }
    (resolved_backup_dir / "rollback.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def list_ownership_migrations(backup_root: Path, limit: int = 50) -> list[dict[str, Any]]:
    backup_root = Path(backup_root).expanduser()
    if not backup_root.is_absolute():
        backup_root = (ROOT_DIR / backup_root).resolve()
    if not backup_root.exists():
        return []

    items: list[dict[str, Any]] = []
    for backup_dir in backup_root.iterdir():
        if not backup_dir.is_dir():
            continue
        metadata_file = backup_dir / "metadata.json"
        if not metadata_file.exists():
            continue
        try:
            metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        rollback_file = backup_dir / "rollback.json"
        rollback_payload = None
        if rollback_file.exists():
            try:
                rollback_payload = json.loads(rollback_file.read_text(encoding="utf-8"))
            except Exception:
                rollback_payload = None

        items.append(
            {
                "backup_id": backup_dir.name,
                "backup_dir": str(backup_dir),
                "generated_at": str(metadata.get("generated_at") or "").strip(),
                "scope": str(metadata.get("scope") or "").strip(),
                "mode": str(metadata.get("mode") or "").strip(),
                "operation_type": str(metadata.get("operation_type") or "ownership_migration").strip(),
                "kinds": metadata.get("kinds") or [],
                "target_user": metadata.get("target_user") or {},
                "source_user": metadata.get("source_user") or {},
                "identity_type": str(metadata.get("identity_type") or "").strip(),
                "sessions": metadata.get("sessions") or {},
                "reports": metadata.get("reports") or {},
                "custom_scenarios": metadata.get("custom_scenarios") or {},
                "solution_shares": metadata.get("solution_shares") or {},
                "licenses": metadata.get("licenses") or {},
                "db_snapshot": metadata.get("db_snapshot") or {},
                "rolled_back": bool(rollback_payload),
                "rolled_back_at": str((rollback_payload or {}).get("rolled_back_at") or "").strip(),
            }
        )

    items.sort(
        key=lambda item: (
            str(item.get("generated_at") or ""),
            str(item.get("backup_id") or ""),
        ),
        reverse=True,
    )
    return items[: max(1, min(int(limit or 50), 200))]
