from __future__ import annotations

import json
import re
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
AUTH_DIR = DATA_DIR / "auth"
DEFAULT_AUTH_DB_PATH = AUTH_DIR / "users.db"
DEFAULT_LICENSE_DB_PATH = AUTH_DIR / "licenses.db"
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


def resolve_auth_db_path(raw_auth_db: str) -> Path:
    input_path = str(raw_auth_db or "").strip()
    path = Path(input_path).expanduser() if input_path else DEFAULT_AUTH_DB_PATH
    if not path.is_absolute():
        path = (ROOT_DIR / path).resolve()
    return path


def resolve_license_db_path(raw_license_db: str, *, auth_db_path: Optional[Path] = None) -> Path:
    input_path = str(raw_license_db or "").strip()
    if input_path:
        path = Path(input_path).expanduser()
    elif auth_db_path is not None:
        path = Path(auth_db_path).expanduser().parent / "licenses.db"
    else:
        path = DEFAULT_LICENSE_DB_PATH
    if not path.is_absolute():
        path = (ROOT_DIR / path).resolve()
    return path


def get_auth_db_connection(auth_db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(auth_db_path)
    conn.row_factory = sqlite3.Row
    return conn


def get_license_db_connection(license_db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(license_db_path)
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


def serialize_user(row: sqlite3.Row) -> dict[str, Any]:
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


def search_users(auth_db_path: Path, query: str = "", limit: int = 20) -> list[dict[str, Any]]:
    if not auth_db_path.exists():
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


def resolve_target_user(auth_db_path: Path, to_user_id: Optional[int], to_account: str) -> dict[str, Any]:
    if not auth_db_path.exists():
        raise RuntimeError(f"用户数据库不存在: {auth_db_path}")

    row = query_user_by_id(auth_db_path, int(to_user_id)) if to_user_id is not None else query_user_by_account(auth_db_path, to_account)
    if not row:
        raise RuntimeError("目标用户不存在，请先确认用户")
    return serialize_user(row)


def resolve_user_reference(auth_db_path: Path, *, user_id: Optional[int] = None, user_account: str = "") -> dict[str, Any]:
    if user_id is not None:
        row = query_user_by_id(auth_db_path, int(user_id))
    else:
        row = query_user_by_account(auth_db_path, user_account)
    if not row:
        raise RuntimeError("指定用户不存在")
    return serialize_user(row)


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
    sorted_items = sorted(owners.items(), key=lambda item: item[0])
    payload = {name: int(owner_id) for name, owner_id in sorted_items}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


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


def _read_user_columns(conn: sqlite3.Connection) -> set[str]:
    return {str(row[1]) for row in conn.execute("PRAGMA table_info(users)").fetchall()}


def ensure_user_merge_columns(conn: sqlite3.Connection) -> None:
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


def count_owned_sessions(sessions_dir: Path, owner_user_id: int) -> int:
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


def count_owned_reports(reports_dir: Path, report_owners_file: Path, owner_user_id: int) -> int:
    matched = 0
    owners = load_report_owners(report_owners_file)
    for report_file in reports_dir.glob("*.md"):
        if parse_owner_id(owners.get(report_file.name, 0)) == int(owner_user_id):
            matched += 1
    return matched


def count_owned_custom_scenarios(custom_scenarios_dir: Path, owner_user_id: int) -> int:
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


def count_owned_solution_shares(report_solution_shares_file: Path, owner_user_id: int) -> int:
    payload = _load_json_file(report_solution_shares_file, {})
    if not isinstance(payload, dict):
        return 0
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
    user_id: int,
) -> dict[str, int]:
    return {
        "sessions": count_owned_sessions(sessions_dir, user_id),
        "reports": count_owned_reports(reports_dir, report_owners_file, user_id),
        "custom_scenarios": count_owned_custom_scenarios(custom_scenarios_dir, user_id),
        "solution_shares": count_owned_solution_shares(report_solution_shares_file, user_id),
        "licenses": count_bound_licenses(license_db_path, user_id),
        "wechat_identities": len(query_wechat_identities_by_user_id(auth_db_path, user_id)),
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
    }


def _generate_merged_placeholder_email(conn: sqlite3.Connection, source_user_id: int) -> str:
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

    source_session_files: list[Path] = []
    for session_file in sorted(sessions_dir.glob("*.json")):
        try:
            payload = json.loads(session_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        if parse_owner_id(payload.get("owner_user_id")) != normalized_source_user_id:
            continue
        source_session_files.append(session_file)
        if len(sessions_examples) < examples_limit:
            sessions_examples.append(
                {
                    "session_file": session_file.name,
                    "session_id": payload.get("session_id") or session_file.stem,
                    "from_owner": normalized_source_user_id,
                    "to_owner": normalized_target_user_id,
                }
            )
    summary["sessions"]["examples"] = sessions_examples

    source_report_names: list[str] = []
    owners = load_report_owners(report_owners_file)
    for report_file in sorted(reports_dir.glob("*.md")):
        if parse_owner_id(owners.get(report_file.name, 0)) != normalized_source_user_id:
            continue
        source_report_names.append(report_file.name)
        if len(reports_examples) < examples_limit:
            reports_examples.append(
                {
                    "report_name": report_file.name,
                    "from_owner": normalized_source_user_id,
                    "to_owner": normalized_target_user_id,
                }
            )
    summary["reports"]["examples"] = reports_examples

    source_scenario_files: list[Path] = []
    if custom_scenarios_dir.exists():
        for scenario_file in sorted(custom_scenarios_dir.glob("*.json")):
            try:
                payload = json.loads(scenario_file.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(payload, dict):
                continue
            if parse_owner_id(payload.get("owner_user_id")) != normalized_source_user_id:
                continue
            source_scenario_files.append(scenario_file)
            if len(scenarios_examples) < examples_limit:
                scenarios_examples.append(
                    {
                        "scenario_id": str(payload.get("id") or scenario_file.stem),
                        "file_name": scenario_file.name,
                        "from_owner": normalized_source_user_id,
                        "to_owner": normalized_target_user_id,
                    }
                )
    summary["custom_scenarios"]["examples"] = scenarios_examples

    solution_shares_payload = _load_json_file(report_solution_shares_file, {})
    source_share_tokens: list[str] = []
    if isinstance(solution_shares_payload, dict):
        for token, record in solution_shares_payload.items():
            if not isinstance(record, dict):
                continue
            if parse_owner_id(record.get("owner_user_id")) != normalized_source_user_id:
                continue
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
            backup_file_once(auth_db_path, backup_dir / "auth" / auth_db_path.name)
            backup_file_once(license_db_path, backup_dir / "licenses" / license_db_path.name)
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
            _write_json_file(report_solution_shares_file, solution_shares_payload)

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

    if not sessions_dir.exists() or not reports_dir.exists():
        raise RuntimeError("数据目录结构不完整")

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

    if "sessions" in parsed_kinds:
        for session_file in sorted(sessions_dir.glob("*.json")):
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
            should_migrate = should_migrate_owner(current_owner, target_user_id, scope, from_user_id)
            if not should_migrate:
                continue

            summary["sessions"]["matched"] += 1
            summary["sessions"]["updated"] += 1
            example = {
                "session_file": session_file.name,
                "session_id": data.get("session_id") or session_file.stem,
                "from_owner": current_owner,
                "to_owner": target_user_id,
            }
            if len(sessions_examples) < examples_limit:
                sessions_examples.append(example)

            if apply_mode and backup_dir:
                backup_file_once(session_file, backup_dir / "sessions" / session_file.name)
                data["owner_user_id"] = target_user_id
                session_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    if "reports" in parsed_kinds:
        owners = load_report_owners(report_owners_file)
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
                owners[report_name] = target_user_id

        if apply_mode and summary["reports"]["updated"] > 0:
            if backup_dir:
                owners_backup = backup_dir / "reports" / ".owners.json"
                owners_absent_marker = backup_dir / "reports" / ".owners.absent"
                if report_owners_file.exists():
                    backup_file_once(report_owners_file, owners_backup)
                elif not owners_absent_marker.exists():
                    owners_absent_marker.write_text("absent\n", encoding="utf-8")
            save_report_owners(report_owners_file, owners)

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
        owners = load_report_owners(report_owners_file)
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
    custom_scenarios_dir: Optional[Path] = None,
    report_solution_shares_file: Optional[Path] = None,
    backup_id: Optional[str] = None,
    backup_dir: Optional[Path] = None,
) -> dict[str, Any]:
    resolved_backup_dir = _resolve_backup_dir(backup_root, backup_id=backup_id, backup_dir=backup_dir)
    if not resolved_backup_dir.exists() or not resolved_backup_dir.is_dir():
        raise RuntimeError(f"备份目录不存在: {resolved_backup_dir}")

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
    auth_backup_file = resolved_backup_dir / "auth" / "users.db"
    if not auth_backup_file.exists():
        auth_candidates = sorted((resolved_backup_dir / "auth").glob("*.db"))
        auth_backup_file = auth_candidates[0] if auth_candidates else auth_backup_file
    if auth_db_path is not None and auth_backup_file.exists():
        auth_db_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(auth_backup_file, auth_db_path)
        auth_db_restored = True

    license_db_restored = False
    license_backup_file = resolved_backup_dir / "licenses" / "licenses.db"
    if not license_backup_file.exists():
        license_candidates = sorted((resolved_backup_dir / "licenses").glob("*.db"))
        license_backup_file = license_candidates[0] if license_candidates else license_backup_file
    if license_db_path is not None and license_backup_file.exists():
        license_db_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(license_backup_file, license_db_path)
        license_db_restored = True

    result = {
        "backup_id": resolved_backup_dir.name,
        "backup_dir": str(resolved_backup_dir),
        "restored_sessions": restored_sessions,
        "owners_restored": owners_restored,
        "owners_removed": owners_removed,
        "solution_shares_restored": solution_shares_restored,
        "solution_shares_removed": solution_shares_removed,
        "restored_custom_scenarios": restored_custom_scenarios,
        "auth_db_restored": auth_db_restored,
        "license_db_restored": license_db_restored,
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
