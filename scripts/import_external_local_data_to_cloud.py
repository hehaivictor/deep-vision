#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["flask", "flask-cors", "anthropic", "requests", "reportlab", "pillow", "jdcloud-sdk", "psycopg[binary]"]
# ///
from __future__ import annotations

import argparse
import importlib.util
import json
import sqlite3
import sys
from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent
SERVER_PATH = ROOT_DIR / "web" / "server.py"
DEFAULT_BACKUP_ROOT = ROOT_DIR / "data" / "operations" / "cloud-import-backups"

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from db_compat import connect_db, db_target_exists, normalize_db_cache_key
from scripts import admin_ownership_service as ownership_admin_service


DEFAULT_INCLUDE = ("sessions", "reports", "report-meta", "indexes")
SOURCE_DELETED_REPORT_FILE_NAMES = (".deleted.json", ".deleted_reports.json")
BACKUP_TABLE_GROUPS = {
    "auth": ("users", "wechat_identities"),
    "meta": (
        "session_store",
        "session_index",
        "report_store",
        "report_meta_owners",
        "report_meta_scopes",
        "report_meta_solution_shares",
        "report_meta_deleted_reports",
        "custom_scenarios",
        "report_index",
    ),
}
RESTORE_TABLE_ORDER = {
    "auth": {
        "delete": ("wechat_identities", "users"),
        "insert": ("users", "wechat_identities"),
    },
    "meta": {
        "delete": (
            "report_index",
            "session_index",
            "report_meta_solution_shares",
            "report_meta_scopes",
            "report_meta_owners",
            "report_meta_deleted_reports",
            "report_store",
            "session_store",
            "custom_scenarios",
        ),
        "insert": (
            "session_store",
            "report_store",
            "report_meta_owners",
            "report_meta_scopes",
            "report_meta_solution_shares",
            "report_meta_deleted_reports",
            "custom_scenarios",
            "session_index",
            "report_index",
        ),
    },
}


@dataclass
class SourceBundle:
    root_dir: Path
    sessions_dir: Path
    reports_dir: Path
    auth_dir: Path
    custom_scenarios_dir: Optional[Path]
    report_owners_file: Path
    report_scopes_file: Path
    report_solution_shares_file: Path
    deleted_reports_file: Optional[Path]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def utc_now_tag() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def load_server_module():
    spec = importlib.util.spec_from_file_location("dv_server_external_import", SERVER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载服务模块: {SERVER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="将第三方本地 data 导入当前云端环境")
    parser.add_argument("--source-data-dir", required=True, help="外部迁移包中的 data 目录")
    parser.add_argument("--source-auth-db", default="", help="源端 auth 数据库路径（有用户体系时必填）")
    parser.add_argument("--target-user-id", type=int, default=0, help="无源端用户体系时的默认目标云端用户 ID")
    parser.add_argument("--user-map-json", default="", help="可选的用户/会话/报告映射 JSON 文件")
    parser.add_argument("--dry-run", action="store_true", help="仅做诊断与计划，不写入云端")
    parser.add_argument("--apply", action="store_true", help="正式写入云端")
    parser.add_argument("--output-json", default="", help="将结果写入指定 JSON 文件")
    parser.add_argument(
        "--include",
        default=",".join(DEFAULT_INCLUDE),
        help="要导入的部分：sessions,reports,report-meta,indexes,custom-scenarios",
    )
    parser.add_argument("--skip-existing", dest="skip_existing", action="store_true", default=True, help="目标云端已有同主键数据时默认跳过")
    parser.add_argument("--no-skip-existing", dest="skip_existing", action="store_false", help="目标云端已有同主键数据时允许覆盖")
    parser.add_argument("--rebuild-indexes", dest="rebuild_indexes", action="store_true", default=True, help="导入后自动重建索引")
    parser.add_argument("--no-rebuild-indexes", dest="rebuild_indexes", action="store_false", help="导入后不自动重建索引")
    parser.add_argument(
        "--preserve-source-scope",
        dest="rewrite_to_active_scope",
        action="store_false",
        default=True,
        help="默认会把导入数据的 instance_scope_key 改写为当前实例 scope；传此参数可保留源 scope",
    )
    parser.add_argument(
        "--cleanup-target-user-scope-residue",
        dest="cleanup_target_user_scope_residue",
        action="store_true",
        default=None,
        help="按本次迁移涉及的目标用户，额外清理其历史会话/报告/自定义场景中的旧 scope 残留",
    )
    parser.add_argument(
        "--no-cleanup-target-user-scope-residue",
        dest="cleanup_target_user_scope_residue",
        action="store_false",
        help="禁用按目标用户清理历史 scope 残留",
    )
    args = parser.parse_args()
    if args.dry_run == args.apply:
        raise SystemExit("必须且只能选择 --dry-run 或 --apply 其中一个")
    return args


def parse_include(raw_include: object) -> set[str]:
    tokens = [str(token or "").strip().lower() for token in str(raw_include or "").split(",") if str(token or "").strip()]
    if not tokens:
        return set(DEFAULT_INCLUDE)
    mapping = {
        "sessions": "sessions",
        "session": "sessions",
        "reports": "reports",
        "report": "reports",
        "report-meta": "report-meta",
        "report_meta": "report-meta",
        "indexes": "indexes",
        "index": "indexes",
        "custom-scenarios": "custom-scenarios",
        "custom_scenarios": "custom-scenarios",
        "custom": "custom-scenarios",
    }
    includes: set[str] = set()
    for token in tokens:
        normalized = mapping.get(token)
        if not normalized:
            raise ValueError(f"无效 include 取值: {token}")
        includes.add(normalized)
    return includes


def _row_to_dict(row: Any) -> dict[str, Any]:
    if row is None:
        return {}
    if isinstance(row, dict):
        return dict(row)
    if hasattr(row, "keys"):
        return {str(key): row[key] for key in row.keys()}
    return {}


def fetch_all_dicts(conn, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    rows = conn.execute(sql, params).fetchall()
    return [_row_to_dict(row) for row in rows]


def sqlite_table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1",
        (str(table_name or "").strip(),),
    ).fetchone()
    return row is not None


def db_table_exists(conn, table_name: str) -> bool:
    try:
        rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    except Exception:
        return False
    return bool(rows)


def get_table_columns(conn, table_name: str) -> list[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    columns: list[str] = []
    for row in rows:
        if isinstance(row, dict):
            name = row.get("name")
        elif hasattr(row, "keys"):
            name = row["name"]
        else:
            name = row[1] if len(row) > 1 else ""
        text = str(name or "").strip()
        if text:
            columns.append(text)
    return columns


def read_json_file(path: Path, default: Any):
    if not path.exists():
        return default
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default
    return payload


def write_json_file(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def discover_source_bundle(source_data_dir: Path) -> SourceBundle:
    root = Path(source_data_dir).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise RuntimeError(f"source-data-dir 不存在或不是目录: {root}")
    sessions_dir = root / "sessions"
    reports_dir = root / "reports"
    if not sessions_dir.exists():
        raise RuntimeError(f"未找到会话目录: {sessions_dir}")
    if not reports_dir.exists():
        raise RuntimeError(f"未找到报告目录: {reports_dir}")
    custom_candidates = [
        root / "custom_scenarios",
        root / "scenarios" / "custom",
    ]
    custom_dir = next((candidate for candidate in custom_candidates if candidate.exists() and candidate.is_dir()), None)
    deleted_reports_file = next((reports_dir / name for name in SOURCE_DELETED_REPORT_FILE_NAMES if (reports_dir / name).exists()), None)
    return SourceBundle(
        root_dir=root,
        sessions_dir=sessions_dir,
        reports_dir=reports_dir,
        auth_dir=root / "auth",
        custom_scenarios_dir=custom_dir,
        report_owners_file=reports_dir / ".owners.json",
        report_scopes_file=reports_dir / ".scopes.json",
        report_solution_shares_file=reports_dir / ".solution_shares.json",
        deleted_reports_file=deleted_reports_file,
    )


def load_source_users(source_auth_db: Path) -> list[dict[str, Any]]:
    if not source_auth_db.exists():
        raise RuntimeError(f"源端 auth 数据库不存在: {source_auth_db}")
    with sqlite3.connect(str(source_auth_db)) as conn:
        conn.row_factory = sqlite3.Row
        if not sqlite_table_exists(conn, "users"):
            raise RuntimeError(f"源端 auth 数据库缺少 users 表: {source_auth_db}")
        return [dict(row) for row in conn.execute("SELECT id, email, phone, created_at FROM users ORDER BY id").fetchall()]


def load_source_wechat_identities(source_auth_db: Path) -> list[dict[str, Any]]:
    if not source_auth_db.exists():
        return []
    with sqlite3.connect(str(source_auth_db)) as conn:
        conn.row_factory = sqlite3.Row
        if not sqlite_table_exists(conn, "wechat_identities"):
            return []
        return [
            dict(row)
            for row in conn.execute(
                "SELECT id, user_id, app_id, openid, unionid, nickname, avatar_url, created_at, updated_at FROM wechat_identities ORDER BY id"
            ).fetchall()
        ]


def load_target_users(auth_db_path: str) -> list[dict[str, Any]]:
    with ownership_admin_service.get_auth_db_connection(auth_db_path) as conn:
        return fetch_all_dicts(conn, "SELECT id, email, phone, created_at FROM users ORDER BY id")


def load_target_wechat_identities(auth_db_path: str) -> list[dict[str, Any]]:
    with ownership_admin_service.get_auth_db_connection(auth_db_path) as conn:
        if not db_table_exists(conn, "wechat_identities"):
            return []
        return fetch_all_dicts(
            conn,
            "SELECT id, user_id, app_id, openid, unionid, nickname, avatar_url, created_at, updated_at FROM wechat_identities ORDER BY id",
        )


def serialize_user_row(row: dict[str, Any]) -> dict[str, Any]:
    user_id = ownership_admin_service.parse_owner_id(row.get("id"))
    email = str(row.get("email") or "").strip().lower()
    phone = ownership_admin_service.normalize_phone_number(str(row.get("phone") or "").strip())
    account = email or phone or f"user-{user_id}"
    return {
        "id": user_id,
        "email": email,
        "phone": phone,
        "account": account,
        "created_at": str(row.get("created_at") or "").strip(),
    }


def load_user_map_json(path: str, *, ownerless_mode: bool) -> dict[str, Any]:
    if not str(path or "").strip():
        return {
            "default_target_user_id": 0,
            "source_user_map": {},
            "session_map": {},
            "report_map": {},
        }
    payload = read_json_file(Path(path).expanduser().resolve(), {})
    if not isinstance(payload, dict):
        raise RuntimeError("user-map-json 格式无效，必须是 JSON 对象")
    source_user_map = payload.get("source_user_map") or {}
    if ownerless_mode and source_user_map:
        raise RuntimeError("无源端用户体系模式下不允许提供 source_user_map")

    def _parse_positive_mapping(raw_mapping: object, label: str) -> dict[str, int]:
        if not raw_mapping:
            return {}
        if not isinstance(raw_mapping, dict):
            raise RuntimeError(f"{label} 必须是 JSON 对象")
        normalized: dict[str, int] = {}
        for raw_key, raw_value in raw_mapping.items():
            key = str(raw_key or "").strip()
            target_user_id = ownership_admin_service.parse_owner_id(raw_value)
            if not key:
                raise RuntimeError(f"{label} 存在空 key")
            if target_user_id <= 0:
                raise RuntimeError(f"{label} 中 {key} 的目标用户 ID 无效")
            normalized[key] = target_user_id
        return normalized

    default_target_user_id = ownership_admin_service.parse_owner_id(payload.get("default_target_user_id"))
    return {
        "default_target_user_id": default_target_user_id,
        "source_user_map": _parse_positive_mapping(source_user_map, "source_user_map"),
        "session_map": _parse_positive_mapping(payload.get("session_map") or {}, "session_map"),
        "report_map": _parse_positive_mapping(payload.get("report_map") or {}, "report_map"),
    }


def build_target_user_indexes(target_users: list[dict[str, Any]], target_wechat_identities: list[dict[str, Any]]) -> dict[str, Any]:
    serialized_users = [serialize_user_row(row) for row in target_users]
    user_by_id = {user["id"]: user for user in serialized_users if user["id"] > 0}
    phone_index: dict[str, set[int]] = defaultdict(set)
    email_index: dict[str, set[int]] = defaultdict(set)
    for user in serialized_users:
        if user["phone"]:
            phone_index[user["phone"]].add(user["id"])
        if user["email"]:
            email_index[user["email"]].add(user["id"])

    unionid_index: dict[str, set[int]] = defaultdict(set)
    openid_index: dict[tuple[str, str], set[int]] = defaultdict(set)
    for row in target_wechat_identities:
        user_id = ownership_admin_service.parse_owner_id(row.get("user_id"))
        if user_id <= 0 or user_id not in user_by_id:
            continue
        unionid = str(row.get("unionid") or "").strip()
        if unionid:
            unionid_index[unionid].add(user_id)
        app_id = str(row.get("app_id") or "").strip()
        openid = str(row.get("openid") or "").strip()
        if app_id and openid:
            openid_index[(app_id, openid)].add(user_id)
    return {
        "users": serialized_users,
        "user_by_id": user_by_id,
        "phone_index": phone_index,
        "email_index": email_index,
        "unionid_index": unionid_index,
        "openid_index": openid_index,
    }


def build_source_identity_index(source_wechat_identities: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    result: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in source_wechat_identities:
        user_id = ownership_admin_service.parse_owner_id(row.get("user_id"))
        if user_id <= 0:
            continue
        result[user_id].append(dict(row))
    return result


def resolve_source_user_mappings(
    *,
    source_users: list[dict[str, Any]],
    source_wechat_identity_map: dict[int, list[dict[str, Any]]],
    target_indexes: dict[str, Any],
    user_map_config: dict[str, Any],
) -> tuple[dict[int, dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    resolved: dict[int, dict[str, Any]] = {}
    unresolved: list[dict[str, Any]] = []
    ambiguous: list[dict[str, Any]] = []
    target_user_by_id = target_indexes["user_by_id"]
    override_map = user_map_config.get("source_user_map") or {}

    for source_row in source_users:
        source_user = serialize_user_row(source_row)
        source_user_id = source_user["id"]
        if source_user_id <= 0:
            continue

        override_target = ownership_admin_service.parse_owner_id(override_map.get(str(source_user_id)))
        if override_target > 0:
            target_user = target_user_by_id.get(override_target)
            if not target_user:
                unresolved.append({
                    "source_user": source_user,
                    "reason": "source_user_map 指向的云端用户不存在",
                    "requested_target_user_id": override_target,
                })
                continue
            resolved[source_user_id] = {
                "source_user": source_user,
                "target_user": target_user,
                "match_type": "source_user_map",
            }
            continue

        checks = []
        if source_user["phone"]:
            checks.append(("phone", set(target_indexes["phone_index"].get(source_user["phone"], set()))))
        if source_user["email"]:
            checks.append(("email", set(target_indexes["email_index"].get(source_user["email"], set()))))

        identities = source_wechat_identity_map.get(source_user_id, [])
        unionid_candidates: set[int] = set()
        openid_candidates: set[int] = set()
        for identity in identities:
            unionid = str(identity.get("unionid") or "").strip()
            if unionid:
                unionid_candidates.update(target_indexes["unionid_index"].get(unionid, set()))
            app_id = str(identity.get("app_id") or "").strip()
            openid = str(identity.get("openid") or "").strip()
            if app_id and openid:
                openid_candidates.update(target_indexes["openid_index"].get((app_id, openid), set()))
        if unionid_candidates:
            checks.append(("unionid", unionid_candidates))
        if openid_candidates:
            checks.append(("openid", openid_candidates))

        matched = False
        for match_type, candidate_ids in checks:
            if len(candidate_ids) == 1:
                target_user_id = next(iter(candidate_ids))
                resolved[source_user_id] = {
                    "source_user": source_user,
                    "target_user": target_user_by_id[target_user_id],
                    "match_type": match_type,
                }
                matched = True
                break
            if len(candidate_ids) > 1:
                ambiguous.append({
                    "source_user": source_user,
                    "match_type": match_type,
                    "candidate_user_ids": sorted(candidate_ids),
                })
                matched = True
                break
        if matched:
            continue

        unresolved.append({
            "source_user": source_user,
            "reason": "未匹配到云端现有用户",
        })

    return resolved, unresolved, ambiguous


def assert_target_user_ids_exist(target_indexes: dict[str, Any], user_map_config: dict[str, Any], explicit_target_user_id: int) -> None:
    target_user_by_id = target_indexes["user_by_id"]
    candidate_ids: set[int] = set()
    explicit_target = ownership_admin_service.parse_owner_id(explicit_target_user_id)
    if explicit_target > 0:
        candidate_ids.add(explicit_target)
    default_target = ownership_admin_service.parse_owner_id(user_map_config.get("default_target_user_id"))
    if default_target > 0:
        candidate_ids.add(default_target)
    for mapping_name in ("source_user_map", "session_map", "report_map"):
        mapping = user_map_config.get(mapping_name) or {}
        for target_user_id in mapping.values():
            normalized = ownership_admin_service.parse_owner_id(target_user_id)
            if normalized > 0:
                candidate_ids.add(normalized)
    missing = sorted(user_id for user_id in candidate_ids if user_id not in target_user_by_id)
    if missing:
        raise RuntimeError(f"以下云端目标用户不存在: {missing}")


def resolve_default_target_user_id(*, user_map_config: dict[str, Any], explicit_target_user_id: int) -> int:
    explicit_target = ownership_admin_service.parse_owner_id(explicit_target_user_id)
    if explicit_target > 0:
        return explicit_target
    return ownership_admin_service.parse_owner_id(user_map_config.get("default_target_user_id"))


def build_source_report_owner_map(bundle: SourceBundle) -> dict[str, int]:
    payload = read_json_file(bundle.report_owners_file, {})
    if not isinstance(payload, dict):
        return {}
    normalized: dict[str, int] = {}
    for raw_name, raw_owner in payload.items():
        name = str(raw_name or "").strip()
        owner_user_id = ownership_admin_service.parse_owner_id(raw_owner)
        if not name or owner_user_id <= 0:
            continue
        normalized[name] = owner_user_id
    return normalized


def build_source_report_scope_map(bundle: SourceBundle) -> dict[str, str]:
    payload = read_json_file(bundle.report_scopes_file, {})
    if not isinstance(payload, dict):
        return {}
    normalized: dict[str, str] = {}
    for raw_name, raw_scope in payload.items():
        name = str(raw_name or "").strip()
        if not name:
            continue
        normalized[name] = str(raw_scope or "").strip()
    return normalized


def build_source_solution_shares(bundle: SourceBundle) -> dict[str, dict[str, Any]]:
    payload = read_json_file(bundle.report_solution_shares_file, {})
    return payload if isinstance(payload, dict) else {}


def build_source_deleted_reports(bundle: SourceBundle) -> set[str]:
    if bundle.deleted_reports_file is None:
        return set()
    payload = read_json_file(bundle.deleted_reports_file, {})
    if isinstance(payload, dict):
        deleted = payload.get("deleted")
        if isinstance(deleted, list):
            return {str(item or "").strip() for item in deleted if str(item or "").strip()}
    if isinstance(payload, list):
        return {str(item or "").strip() for item in payload if str(item or "").strip()}
    return set()


def resolve_target_scope_key(
    *,
    source_scope_key: object,
    rewrite_to_active_scope: bool,
    active_scope_key: str,
    server_module,
) -> str:
    if rewrite_to_active_scope:
        return server_module.get_record_instance_scope_key(active_scope_key)
    return server_module.get_record_instance_scope_key(source_scope_key)


def load_source_sessions(bundle: SourceBundle) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for session_file in sorted(bundle.sessions_dir.glob("*.json")):
        payload = read_json_file(session_file, {})
        if not isinstance(payload, dict):
            continue
        session_id = str(payload.get("session_id") or "").strip() or session_file.stem
        payload["session_id"] = session_id
        rows.append({
            "file_path": session_file,
            "file_name": session_file.name,
            "session_id": session_id,
            "payload": payload,
            "source_owner_user_id": ownership_admin_service.parse_owner_id(payload.get("owner_user_id")),
        })
    return rows


def infer_report_target_owner_map(source_sessions: list[dict[str, Any]], session_target_map: dict[str, int], server_module) -> tuple[dict[str, int], list[dict[str, Any]]]:
    inferred: dict[str, int] = {}
    conflicts: list[dict[str, Any]] = []
    for item in source_sessions:
        target_owner_id = ownership_admin_service.parse_owner_id(session_target_map.get(item["session_id"]))
        if target_owner_id <= 0:
            continue
        report_names = []
        try:
            report_names = list(server_module._collect_direct_bound_report_names(item["payload"]))
        except Exception:
            report_names = []
        for report_name in report_names:
            normalized_name = str(report_name or "").strip()
            if not normalized_name:
                continue
            existing = ownership_admin_service.parse_owner_id(inferred.get(normalized_name))
            if existing > 0 and existing != target_owner_id:
                conflicts.append({
                    "report_name": normalized_name,
                    "first_owner_user_id": existing,
                    "conflict_owner_user_id": target_owner_id,
                    "session_id": item["session_id"],
                })
                inferred.pop(normalized_name, None)
                continue
            if existing <= 0:
                inferred[normalized_name] = target_owner_id
    conflict_names = {item["report_name"] for item in conflicts}
    for report_name in conflict_names:
        inferred.pop(report_name, None)
    return inferred, conflicts


def discover_custom_scenario_files(bundle: SourceBundle) -> list[Path]:
    if bundle.custom_scenarios_dir is None or not bundle.custom_scenarios_dir.exists():
        return []
    return sorted(bundle.custom_scenarios_dir.glob("*.json"))


def summarize_cloud_tables(server_module) -> dict[str, Any]:
    server_module.ensure_meta_index_schema()
    auth_db_path = str(server_module.AUTH_DB_PATH)
    meta_index_db_path = str(server_module.get_meta_index_db_target())
    summary = {
        "auth_db_path": normalize_db_cache_key(auth_db_path),
        "meta_index_db_path": normalize_db_cache_key(meta_index_db_path),
        "tables": {},
    }
    with ownership_admin_service.get_auth_db_connection(auth_db_path) as auth_conn:
        for table_name in BACKUP_TABLE_GROUPS["auth"]:
            total = 0
            if db_table_exists(auth_conn, table_name):
                row = auth_conn.execute(f"SELECT COUNT(1) AS total FROM {table_name}").fetchone()
                total = int((_row_to_dict(row).get("total") or 0))
            summary["tables"][table_name] = total
    with ownership_admin_service.get_meta_index_connection(meta_index_db_path) as meta_conn:
        for table_name in BACKUP_TABLE_GROUPS["meta"]:
            total = 0
            if db_table_exists(meta_conn, table_name):
                row = meta_conn.execute(f"SELECT COUNT(1) AS total FROM {table_name}").fetchone()
                total = int((_row_to_dict(row).get("total") or 0))
            summary["tables"][table_name] = total
    return summary


def capture_db_snapshot(backup_dir: Path, *, auth_db_path: str, meta_index_db_path: str) -> dict[str, Any]:
    manifest = {
        "backup_id": backup_dir.name,
        "captured_at": utc_now_iso(),
        "backup_dir": str(backup_dir),
        "auth_db_path": normalize_db_cache_key(auth_db_path),
        "meta_index_db_path": normalize_db_cache_key(meta_index_db_path),
        "backed_up_tables": {"auth": [], "meta": []},
        "restorable_tables": {
            "auth": [],
            "meta": list(BACKUP_TABLE_GROUPS["meta"]),
        },
    }
    auth_backup_dir = backup_dir / "auth_tables"
    meta_backup_dir = backup_dir / "meta_tables"
    auth_backup_dir.mkdir(parents=True, exist_ok=True)
    meta_backup_dir.mkdir(parents=True, exist_ok=True)

    with ownership_admin_service.get_auth_db_connection(auth_db_path) as auth_conn:
        for table_name in BACKUP_TABLE_GROUPS["auth"]:
            rows = fetch_all_dicts(auth_conn, f"SELECT * FROM {table_name}") if db_table_exists(auth_conn, table_name) else []
            write_json_file(auth_backup_dir / f"{table_name}.json", rows)
            manifest["backed_up_tables"]["auth"].append(table_name)

    with ownership_admin_service.get_meta_index_connection(meta_index_db_path) as meta_conn:
        for table_name in BACKUP_TABLE_GROUPS["meta"]:
            rows = fetch_all_dicts(meta_conn, f"SELECT * FROM {table_name}") if db_table_exists(meta_conn, table_name) else []
            write_json_file(meta_backup_dir / f"{table_name}.json", rows)
            manifest["backed_up_tables"]["meta"].append(table_name)

    write_json_file(backup_dir / "backup-manifest.json", manifest)
    return manifest


def _delete_tables(conn, table_names: list[str]) -> None:
    for table_name in table_names:
        if db_table_exists(conn, table_name):
            conn.execute(f"DELETE FROM {table_name}")


def _insert_table_rows(conn, table_name: str, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    columns = get_table_columns(conn, table_name)
    if not columns:
        return 0
    placeholders = ", ".join(["?"] * len(columns))
    sql = f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders})"
    conn.executemany(
        sql,
        [
            tuple(row.get(column) for column in columns)
            for row in rows
        ],
    )
    return len(rows)


def restore_db_snapshot(backup_dir: Path, *, auth_db_path: str, meta_index_db_path: str) -> dict[str, Any]:
    manifest = read_json_file(backup_dir / "backup-manifest.json", {})
    if not isinstance(manifest, dict):
        raise RuntimeError(f"备份清单不存在或无效: {backup_dir}")
    expected_auth_db = normalize_db_cache_key(manifest.get("auth_db_path"))
    expected_meta_db = normalize_db_cache_key(manifest.get("meta_index_db_path"))
    if expected_auth_db and expected_auth_db != normalize_db_cache_key(auth_db_path):
        raise RuntimeError("当前鉴权数据库与备份记录不一致，拒绝回滚")
    if expected_meta_db and expected_meta_db != normalize_db_cache_key(meta_index_db_path):
        raise RuntimeError("当前元数据数据库与备份记录不一致，拒绝回滚")

    restored = {"auth": {}, "meta": {}}
    auth_tables = list((manifest.get("restorable_tables") or {}).get("auth") or [])
    meta_tables = list((manifest.get("restorable_tables") or {}).get("meta") or [])

    with ownership_admin_service.get_auth_db_connection(auth_db_path) as auth_conn:
        _delete_tables(auth_conn, [table for table in RESTORE_TABLE_ORDER["auth"]["delete"] if table in auth_tables])
        for table_name in RESTORE_TABLE_ORDER["auth"]["insert"]:
            if table_name not in auth_tables:
                continue
            rows = read_json_file(backup_dir / "auth_tables" / f"{table_name}.json", [])
            restored["auth"][table_name] = _insert_table_rows(auth_conn, table_name, rows if isinstance(rows, list) else [])

    with ownership_admin_service.get_meta_index_connection(meta_index_db_path) as meta_conn:
        _delete_tables(meta_conn, [table for table in RESTORE_TABLE_ORDER["meta"]["delete"] if table in meta_tables])
        for table_name in RESTORE_TABLE_ORDER["meta"]["insert"]:
            if table_name not in meta_tables:
                continue
            rows = read_json_file(backup_dir / "meta_tables" / f"{table_name}.json", [])
            restored["meta"][table_name] = _insert_table_rows(meta_conn, table_name, rows if isinstance(rows, list) else [])
    return restored


def resolve_session_target_owner(
    *,
    session_id: str,
    source_owner_user_id: int,
    resolved_source_user_map: dict[int, dict[str, Any]],
    user_map_config: dict[str, Any],
    default_target_user_id: int,
) -> int:
    target_user_id = ownership_admin_service.parse_owner_id((user_map_config.get("session_map") or {}).get(session_id))
    if target_user_id > 0:
        return target_user_id
    if source_owner_user_id > 0:
        resolved = resolved_source_user_map.get(int(source_owner_user_id))
        if resolved:
            return ownership_admin_service.parse_owner_id((resolved.get("target_user") or {}).get("id"))
    return ownership_admin_service.parse_owner_id(default_target_user_id)


def resolve_report_target_owner(
    *,
    report_name: str,
    source_owner_user_id: int,
    inferred_owner_user_id: int,
    resolved_source_user_map: dict[int, dict[str, Any]],
    user_map_config: dict[str, Any],
    default_target_user_id: int,
) -> int:
    target_user_id = ownership_admin_service.parse_owner_id((user_map_config.get("report_map") or {}).get(report_name))
    if target_user_id > 0:
        return target_user_id
    if source_owner_user_id > 0:
        resolved = resolved_source_user_map.get(int(source_owner_user_id))
        if resolved:
            return ownership_admin_service.parse_owner_id((resolved.get("target_user") or {}).get("id"))
    if inferred_owner_user_id > 0:
        return ownership_admin_service.parse_owner_id(inferred_owner_user_id)
    return ownership_admin_service.parse_owner_id(default_target_user_id)


def resolve_custom_scenario_target_owner(
    *,
    source_owner_user_id: int,
    resolved_source_user_map: dict[int, dict[str, Any]],
    default_target_user_id: int,
) -> int:
    if source_owner_user_id > 0:
        resolved = resolved_source_user_map.get(int(source_owner_user_id))
        if resolved:
            return ownership_admin_service.parse_owner_id((resolved.get("target_user") or {}).get("id"))
    return ownership_admin_service.parse_owner_id(default_target_user_id)


def plan_import(
    *,
    bundle: SourceBundle,
    includes: set[str],
    ownerless_mode: bool,
    resolved_source_user_map: dict[int, dict[str, Any]],
    unresolved_users: list[dict[str, Any]],
    ambiguous_users: list[dict[str, Any]],
    user_map_config: dict[str, Any],
    default_target_user_id: int,
    target_existing_session_ids: set[str],
    target_existing_report_names: set[str],
    rewrite_to_active_scope: bool,
    active_scope_key: str,
    server_module,
) -> dict[str, Any]:
    source_sessions = load_source_sessions(bundle)
    planned_sessions: list[dict[str, Any]] = []
    session_target_map: dict[str, int] = {}
    skipped_sessions: list[dict[str, Any]] = []
    session_conflicts: list[dict[str, Any]] = []

    for item in source_sessions:
        target_owner_user_id = resolve_session_target_owner(
            session_id=item["session_id"],
            source_owner_user_id=item["source_owner_user_id"],
            resolved_source_user_map=resolved_source_user_map,
            user_map_config=user_map_config,
            default_target_user_id=default_target_user_id,
        )
        if target_owner_user_id <= 0:
            skipped_sessions.append({
                "session_id": item["session_id"],
                "file_name": item["file_name"],
                "reason": "无法映射 owner_user_id",
                "source_owner_user_id": item["source_owner_user_id"],
            })
            continue
        exists = item["session_id"] in target_existing_session_ids
        if exists:
            session_conflicts.append({
                "session_id": item["session_id"],
                "file_name": item["file_name"],
                "reason": "session_id 已存在于云端",
            })
        planned_sessions.append({
            **item,
            "target_owner_user_id": target_owner_user_id,
            "target_instance_scope_key": resolve_target_scope_key(
                source_scope_key=item["payload"].get(server_module.INSTANCE_SCOPE_FIELD, ""),
                rewrite_to_active_scope=rewrite_to_active_scope,
                active_scope_key=active_scope_key,
                server_module=server_module,
            ),
            "exists": exists,
        })
        session_target_map[item["session_id"]] = target_owner_user_id

    source_report_owner_map = build_source_report_owner_map(bundle)
    source_report_scope_map = build_source_report_scope_map(bundle)
    source_solution_shares = build_source_solution_shares(bundle)
    source_deleted_reports = build_source_deleted_reports(bundle)
    inferred_report_owner_map, inferred_owner_conflicts = infer_report_target_owner_map(source_sessions, session_target_map, server_module)

    planned_reports: list[dict[str, Any]] = []
    report_conflicts: list[dict[str, Any]] = []
    skipped_reports: list[dict[str, Any]] = []
    imported_report_name_set: set[str] = set()
    for report_file in sorted(bundle.reports_dir.glob("*.md")):
        report_name = report_file.name
        source_owner_user_id = ownership_admin_service.parse_owner_id(source_report_owner_map.get(report_name))
        inferred_owner_user_id = ownership_admin_service.parse_owner_id(inferred_report_owner_map.get(report_name))
        target_owner_user_id = resolve_report_target_owner(
            report_name=report_name,
            source_owner_user_id=source_owner_user_id,
            inferred_owner_user_id=inferred_owner_user_id,
            resolved_source_user_map=resolved_source_user_map,
            user_map_config=user_map_config,
            default_target_user_id=default_target_user_id,
        )
        if target_owner_user_id <= 0:
            skipped_reports.append({
                "file_name": report_name,
                "reason": "无法映射 owner_user_id",
                "source_owner_user_id": source_owner_user_id,
                "inferred_owner_user_id": inferred_owner_user_id,
            })
            continue
        exists = report_name in target_existing_report_names
        if exists:
            report_conflicts.append({
                "file_name": report_name,
                "reason": "报告文件名已存在于云端",
            })
        planned_reports.append({
            "file_path": report_file,
            "file_name": report_name,
            "target_owner_user_id": target_owner_user_id,
            "exists": exists,
            "instance_scope_key": resolve_target_scope_key(
                source_scope_key=source_report_scope_map.get(report_name, ""),
                rewrite_to_active_scope=rewrite_to_active_scope,
                active_scope_key=active_scope_key,
                server_module=server_module,
            ),
            "deleted": report_name in source_deleted_reports,
        })
        if not exists:
            imported_report_name_set.add(report_name)

    planned_custom_scenarios: list[dict[str, Any]] = []
    skipped_custom_scenarios: list[dict[str, Any]] = []
    if "custom-scenarios" in includes:
        for scenario_file in discover_custom_scenario_files(bundle):
            payload = read_json_file(scenario_file, {})
            if not isinstance(payload, dict):
                skipped_custom_scenarios.append({
                    "file_name": scenario_file.name,
                    "reason": "场景文件 JSON 无效",
                })
                continue
            meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
            source_owner_user_id = ownership_admin_service.parse_owner_id(payload.get("owner_user_id") or meta.get("owner_user_id"))
            target_owner_user_id = resolve_custom_scenario_target_owner(
                source_owner_user_id=source_owner_user_id,
                resolved_source_user_map=resolved_source_user_map,
                default_target_user_id=default_target_user_id,
            )
            if target_owner_user_id <= 0:
                skipped_custom_scenarios.append({
                    "file_name": scenario_file.name,
                    "reason": "无法映射 owner_user_id",
                    "source_owner_user_id": source_owner_user_id,
                })
                continue
            planned_custom_scenarios.append({
                "file_path": scenario_file,
                "file_name": scenario_file.name,
                "scenario_id": str(payload.get("id") or scenario_file.stem).strip(),
                "payload": payload,
                "target_owner_user_id": target_owner_user_id,
                "instance_scope_key": resolve_target_scope_key(
                    source_scope_key=str(payload.get("instance_scope_key") or meta.get("instance_scope_key") or "").strip(),
                    rewrite_to_active_scope=rewrite_to_active_scope,
                    active_scope_key=active_scope_key,
                    server_module=server_module,
                ),
            })

    planned_solution_shares: list[dict[str, Any]] = []
    for share_token, record in (source_solution_shares or {}).items():
        if not isinstance(record, dict):
            continue
        report_name = str(record.get("report_name") or "").strip()
        if not report_name:
            continue
        target_report_name = report_name
        target_owner_user_id = resolve_report_target_owner(
            report_name=report_name,
            source_owner_user_id=ownership_admin_service.parse_owner_id(record.get("owner_user_id")),
            inferred_owner_user_id=ownership_admin_service.parse_owner_id(inferred_report_owner_map.get(report_name)),
            resolved_source_user_map=resolved_source_user_map,
            user_map_config=user_map_config,
            default_target_user_id=default_target_user_id,
        )
        if target_owner_user_id <= 0:
            continue
        if report_name in {item["file_name"] for item in report_conflicts}:
            continue
        planned_solution_shares.append({
            "share_token": str(share_token or "").strip(),
            "report_name": target_report_name,
            "owner_user_id": target_owner_user_id,
            "created_at": str(record.get("created_at") or "").strip(),
            "updated_at": str(record.get("updated_at") or "").strip(),
        })

    return {
        "source_sessions": source_sessions,
        "planned_sessions": planned_sessions,
        "planned_reports": planned_reports,
        "planned_custom_scenarios": planned_custom_scenarios,
        "planned_solution_shares": planned_solution_shares,
        "skipped_sessions": skipped_sessions,
        "skipped_reports": skipped_reports,
        "skipped_custom_scenarios": skipped_custom_scenarios,
        "conflicts": {
            "sessions": session_conflicts,
            "reports": report_conflicts,
            "report_owner_inference": inferred_owner_conflicts,
        },
        "source_meta": {
            "report_owner_entries": len(source_report_owner_map),
            "report_scope_entries": len(source_report_scope_map),
            "solution_share_entries": len(source_solution_shares),
            "deleted_report_entries": len(source_deleted_reports),
        },
        "rewrite_to_active_scope": bool(rewrite_to_active_scope),
        "active_scope_key": server_module.get_record_instance_scope_key(active_scope_key),
    }


def build_summary_payload(
    *,
    bundle: SourceBundle,
    ownerless_mode: bool,
    default_target_user_id: int,
    source_users: list[dict[str, Any]],
    source_wechat_identities: list[dict[str, Any]],
    resolved_source_user_map: dict[int, dict[str, Any]],
    unresolved_users: list[dict[str, Any]],
    ambiguous_users: list[dict[str, Any]],
    plan: dict[str, Any],
    cloud_summary_before: dict[str, Any],
    backup: Optional[dict[str, Any]],
    applied: bool,
    cloud_summary_after: Optional[dict[str, Any]],
    scope_cleanup: Optional[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "source_summary": {
            "source_data_dir": str(bundle.root_dir),
            "ownerless_mode": bool(ownerless_mode),
            "default_target_user_id": int(default_target_user_id or 0),
            "rewrite_to_active_scope": bool(plan.get("rewrite_to_active_scope", True)),
            "active_scope_key": str(plan.get("active_scope_key") or ""),
            "sessions_count": len(list(bundle.sessions_dir.glob("*.json"))),
            "reports_count": len(list(bundle.reports_dir.glob("*.md"))),
            "custom_scenarios_count": len(discover_custom_scenario_files(bundle)),
            "source_users_count": len(source_users),
            "source_wechat_identities_count": len(source_wechat_identities),
            "has_source_auth_db": bool(source_users),
        },
        "cloud_summary_before": cloud_summary_before,
        "resolved_user_mappings": [
            {
                "source_user_id": source_user_id,
                "target_user_id": ownership_admin_service.parse_owner_id((mapping.get("target_user") or {}).get("id")),
                "match_type": str(mapping.get("match_type") or ""),
                "source_account": str((mapping.get("source_user") or {}).get("account") or ""),
                "target_account": str((mapping.get("target_user") or {}).get("account") or ""),
            }
            for source_user_id, mapping in sorted(resolved_source_user_map.items())
        ],
        "unresolved_users": unresolved_users,
        "ambiguous_users": ambiguous_users,
        "planned_import": {
            "sessions": {
                "total": len(plan["planned_sessions"]),
                "conflicts": len(plan["conflicts"]["sessions"]),
                "skipped_unmapped": len(plan["skipped_sessions"]),
                "ready": len([item for item in plan["planned_sessions"] if not item["exists"]]),
            },
            "reports": {
                "total": len(plan["planned_reports"]),
                "conflicts": len(plan["conflicts"]["reports"]),
                "skipped_unmapped": len(plan["skipped_reports"]),
                "ready": len([item for item in plan["planned_reports"] if not item["exists"]]),
            },
            "custom_scenarios": {
                "total": len(plan["planned_custom_scenarios"]),
                "skipped_unmapped": len(plan["skipped_custom_scenarios"]),
            },
        },
        "conflicts": plan["conflicts"],
        "backup": backup or {"performed": False},
        "applied": bool(applied),
        "cloud_summary_after": cloud_summary_after or {},
        "scope_cleanup": scope_cleanup or {},
        "ownerless_mode": bool(ownerless_mode),
        "default_target_user_id": int(default_target_user_id or 0),
        "session_map_override_count": len((plan.get("session_map_overrides") or {})) if isinstance(plan, dict) else 0,
        "report_map_override_count": len((plan.get("report_map_overrides") or {})) if isinstance(plan, dict) else 0,
    }


def resolve_scope_cleanup_enabled(
    *,
    rewrite_to_active_scope: bool,
    cleanup_target_user_scope_residue: Optional[bool],
) -> bool:
    if cleanup_target_user_scope_residue is None:
        return bool(rewrite_to_active_scope)
    return bool(cleanup_target_user_scope_residue)


def collect_target_owner_user_ids(plan: dict[str, Any]) -> list[int]:
    owner_ids: set[int] = set()
    for item in plan.get("planned_sessions") or []:
        owner_id = ownership_admin_service.parse_owner_id(item.get("target_owner_user_id"))
        if owner_id > 0:
            owner_ids.add(owner_id)
    for item in plan.get("planned_reports") or []:
        owner_id = ownership_admin_service.parse_owner_id(item.get("target_owner_user_id"))
        if owner_id > 0:
            owner_ids.add(owner_id)
    for item in plan.get("planned_custom_scenarios") or []:
        owner_id = ownership_admin_service.parse_owner_id(item.get("target_owner_user_id"))
        if owner_id > 0:
            owner_ids.add(owner_id)
    return sorted(owner_ids)


def _build_owner_placeholders(owner_ids: list[int]) -> tuple[str, tuple[int, ...]]:
    normalized = tuple(int(owner_id) for owner_id in owner_ids if int(owner_id) > 0)
    if not normalized:
        return "", ()
    return ", ".join(["?"] * len(normalized)), normalized


def _apply_scope_to_payload(payload: dict[str, Any], *, target_scope_key: str, scope_field: str) -> dict[str, Any]:
    payload[scope_field] = target_scope_key
    meta = payload.get("meta")
    if isinstance(meta, dict):
        meta[scope_field] = target_scope_key
    return payload


def collect_scope_cleanup_candidates(
    *,
    target_owner_user_ids: list[int],
    target_scope_key: str,
    server_module,
) -> dict[str, Any]:
    summary = {
        "target_owner_user_ids": [int(owner_id) for owner_id in target_owner_user_ids if int(owner_id) > 0],
        "target_scope_key": str(target_scope_key or ""),
        "required": False,
        "session_store": {"count": 0, "examples": []},
        "report_meta_scopes": {"count": 0, "examples": []},
        "custom_scenarios": {"count": 0, "examples": []},
    }
    if not summary["target_owner_user_ids"]:
        return summary

    placeholders, params = _build_owner_placeholders(summary["target_owner_user_ids"])
    if not placeholders:
        return summary

    scope_field = str(getattr(server_module, "INSTANCE_SCOPE_FIELD", "instance_scope_key") or "instance_scope_key")
    target_scope = str(target_scope_key or "")
    session_examples: list[str] = []
    report_examples: list[str] = []
    scenario_examples: list[str] = []
    session_count = 0
    report_count = 0
    scenario_count = 0

    with ownership_admin_service.get_meta_index_connection(str(server_module.get_meta_index_db_target())) as conn:
        session_rows = fetch_all_dicts(
            conn,
            f"""
            SELECT session_id, instance_scope_key, payload_json
            FROM session_store
            WHERE owner_user_id IN ({placeholders})
            """,
            params,
        )
        for row in session_rows:
            row_scope = server_module.get_record_instance_scope_key(row.get("instance_scope_key"))
            payload_scope = row_scope
            try:
                payload = json.loads(str(row.get("payload_json") or "{}"))
                if isinstance(payload, dict):
                    payload_scope = server_module.get_record_instance_scope_key(payload.get(scope_field))
            except Exception:
                payload_scope = row_scope
            if row_scope == target_scope and payload_scope == target_scope:
                continue
            session_count += 1
            session_id = str(row.get("session_id") or "").strip()
            if session_id and len(session_examples) < 20:
                session_examples.append(session_id)

        report_rows = fetch_all_dicts(
            conn,
            f"""
            SELECT o.file_name, COALESCE(s.instance_scope_key, '') AS instance_scope_key
            FROM report_meta_owners o
            LEFT JOIN report_meta_scopes s ON s.file_name = o.file_name
            WHERE o.owner_user_id IN ({placeholders})
            """,
            params,
        )
        for row in report_rows:
            row_scope = server_module.get_record_instance_scope_key(row.get("instance_scope_key"))
            if row_scope == target_scope:
                continue
            report_count += 1
            file_name = str(row.get("file_name") or "").strip()
            if file_name and len(report_examples) < 20:
                report_examples.append(file_name)

        scenario_rows = fetch_all_dicts(
            conn,
            f"""
            SELECT scenario_id, instance_scope_key, payload_json
            FROM custom_scenarios
            WHERE owner_user_id IN ({placeholders})
            """,
            params,
        )
        for row in scenario_rows:
            row_scope = server_module.get_record_instance_scope_key(row.get("instance_scope_key"))
            payload_scope = row_scope
            try:
                payload = json.loads(str(row.get("payload_json") or "{}"))
                if isinstance(payload, dict):
                    payload_scope = server_module.get_record_instance_scope_key(payload.get(scope_field) or (payload.get("meta") or {}).get(scope_field))
            except Exception:
                payload_scope = row_scope
            if row_scope == target_scope and payload_scope == target_scope:
                continue
            scenario_count += 1
            scenario_id = str(row.get("scenario_id") or "").strip()
            if scenario_id and len(scenario_examples) < 20:
                scenario_examples.append(scenario_id)

    summary["session_store"] = {"count": session_count, "examples": session_examples}
    summary["report_meta_scopes"] = {"count": report_count, "examples": report_examples}
    summary["custom_scenarios"] = {"count": scenario_count, "examples": scenario_examples}
    summary["required"] = bool(session_count or report_count or scenario_count)
    return summary


def apply_scope_cleanup(
    *,
    target_owner_user_ids: list[int],
    target_scope_key: str,
    server_module,
) -> dict[str, Any]:
    cleanup_summary = {
        "target_owner_user_ids": [int(owner_id) for owner_id in target_owner_user_ids if int(owner_id) > 0],
        "target_scope_key": str(target_scope_key or ""),
        "session_store": 0,
        "report_meta_scopes": 0,
        "custom_scenarios": 0,
        "requires_indexes_rebuild": False,
        "requires_scenario_loader_reload": False,
    }
    if not cleanup_summary["target_owner_user_ids"]:
        return cleanup_summary

    placeholders, params = _build_owner_placeholders(cleanup_summary["target_owner_user_ids"])
    if not placeholders:
        return cleanup_summary

    now_iso = utc_now_iso()
    time_ns = int(datetime.now().timestamp() * 1_000_000_000)
    scope_field = str(getattr(server_module, "INSTANCE_SCOPE_FIELD", "instance_scope_key") or "instance_scope_key")
    target_scope = str(target_scope_key or "")

    with ownership_admin_service.get_meta_index_connection(str(server_module.get_meta_index_db_target())) as conn:
        session_rows = fetch_all_dicts(
            conn,
            f"""
            SELECT session_id, instance_scope_key, payload_json
            FROM session_store
            WHERE owner_user_id IN ({placeholders})
            """,
            params,
        )
        for row in session_rows:
            session_id = str(row.get("session_id") or "").strip()
            if not session_id:
                continue
            try:
                payload = json.loads(str(row.get("payload_json") or "{}"))
            except Exception:
                payload = {}
            if not isinstance(payload, dict):
                continue
            row_scope = server_module.get_record_instance_scope_key(row.get("instance_scope_key"))
            payload_scope = server_module.get_record_instance_scope_key(payload.get(scope_field))
            if row_scope == target_scope and payload_scope == target_scope:
                continue
            payload = _apply_scope_to_payload(payload, target_scope_key=target_scope, scope_field=scope_field)
            payload_text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
            conn.execute(
                """
                UPDATE session_store
                SET instance_scope_key = ?, payload_json = ?, payload_mtime_ns = ?, payload_size = ?
                WHERE session_id = ?
                """,
                (target_scope, payload_text, time_ns, len(payload_text.encode("utf-8")), session_id),
            )
            cleanup_summary["session_store"] += 1

        report_rows = fetch_all_dicts(
            conn,
            f"""
            SELECT o.file_name, COALESCE(s.instance_scope_key, '') AS instance_scope_key
            FROM report_meta_owners o
            LEFT JOIN report_meta_scopes s ON s.file_name = o.file_name
            WHERE o.owner_user_id IN ({placeholders})
            """,
            params,
        )
        for row in report_rows:
            file_name = str(row.get("file_name") or "").strip()
            if not file_name:
                continue
            row_scope = server_module.get_record_instance_scope_key(row.get("instance_scope_key"))
            if row_scope == target_scope:
                continue
            if target_scope:
                conn.execute(
                    """
                    INSERT INTO report_meta_scopes(file_name, instance_scope_key, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(file_name) DO UPDATE SET
                        instance_scope_key=excluded.instance_scope_key,
                        updated_at=excluded.updated_at
                    """,
                    (file_name, target_scope, now_iso),
                )
            else:
                conn.execute("DELETE FROM report_meta_scopes WHERE file_name = ?", (file_name,))
            cleanup_summary["report_meta_scopes"] += 1

        scenario_rows = fetch_all_dicts(
            conn,
            f"""
            SELECT scenario_id, instance_scope_key, payload_json
            FROM custom_scenarios
            WHERE owner_user_id IN ({placeholders})
            """,
            params,
        )
        for row in scenario_rows:
            scenario_id = str(row.get("scenario_id") or "").strip()
            if not scenario_id:
                continue
            try:
                payload = json.loads(str(row.get("payload_json") or "{}"))
            except Exception:
                payload = {}
            if not isinstance(payload, dict):
                continue
            row_scope = server_module.get_record_instance_scope_key(row.get("instance_scope_key"))
            payload_scope = server_module.get_record_instance_scope_key(payload.get(scope_field) or (payload.get("meta") or {}).get(scope_field))
            if row_scope == target_scope and payload_scope == target_scope:
                continue
            payload = _apply_scope_to_payload(payload, target_scope_key=target_scope, scope_field=scope_field)
            payload_text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
            conn.execute(
                """
                UPDATE custom_scenarios
                SET instance_scope_key = ?, payload_json = ?, updated_at = ?
                WHERE scenario_id = ?
                """,
                (target_scope, payload_text, now_iso, scenario_id),
            )
            cleanup_summary["custom_scenarios"] += 1

    cleanup_summary["requires_indexes_rebuild"] = bool(
        cleanup_summary["session_store"] or cleanup_summary["report_meta_scopes"]
    )
    cleanup_summary["requires_scenario_loader_reload"] = bool(cleanup_summary["custom_scenarios"])
    return cleanup_summary


def apply_import_plan(
    *,
    plan: dict[str, Any],
    server_module,
    includes: set[str],
    skip_existing: bool,
    rebuild_indexes: bool,
    rewrite_to_active_scope: bool,
    active_scope_key: str,
) -> dict[str, Any]:
    server_module.ensure_meta_index_schema()
    imported = {
        "sessions": 0,
        "reports": 0,
        "report_meta_owners": 0,
        "report_meta_scopes": 0,
        "report_meta_solution_shares": 0,
        "report_meta_deleted_reports": 0,
        "custom_scenarios": 0,
        "indexes_rebuilt": False,
    }
    with ownership_admin_service.get_meta_index_connection(str(server_module.get_meta_index_db_target())) as conn:
        if "sessions" in includes:
            for item in plan["planned_sessions"]:
                if item["exists"] and skip_existing:
                    continue
                payload = deepcopy(item["payload"])
                payload["owner_user_id"] = int(item["target_owner_user_id"])
                payload[server_module.INSTANCE_SCOPE_FIELD] = resolve_target_scope_key(
                    source_scope_key=item.get("target_instance_scope_key", ""),
                    rewrite_to_active_scope=rewrite_to_active_scope,
                    active_scope_key=active_scope_key,
                    server_module=server_module,
                )
                record = server_module._build_session_store_record(item["file_path"], payload)
                if not record:
                    continue
                server_module._upsert_session_store_record(conn, record)
                imported["sessions"] += 1

        imported_report_names: set[str] = set()
        if "reports" in includes:
            for item in plan["planned_reports"]:
                if item["exists"] and skip_existing:
                    continue
                content = item["file_path"].read_text(encoding="utf-8")
                signature = server_module.get_file_signature(item["file_path"])
                if signature is None:
                    signature = (int(datetime.now().timestamp() * 1_000_000_000), len(content.encode("utf-8")))
                record = server_module._build_report_store_record(
                    item["file_name"],
                    content,
                    created_at="",
                    updated_at="",
                    signature=signature,
                )
                if not record:
                    continue
                server_module._upsert_report_store_record(conn, record)
                imported["reports"] += 1
                imported_report_names.add(item["file_name"])

        if "report-meta" in includes:
            now_iso = utc_now_iso()
            for item in plan["planned_reports"]:
                if item["exists"] and skip_existing:
                    continue
                conn.execute(
                    """
                    INSERT INTO report_meta_owners(file_name, owner_user_id, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(file_name) DO UPDATE SET
                        owner_user_id=excluded.owner_user_id,
                        updated_at=excluded.updated_at
                    """,
                    (item["file_name"], int(item["target_owner_user_id"]), now_iso),
                )
                imported["report_meta_owners"] += 1
                scope_key = str(item.get("instance_scope_key") or "").strip()
                if scope_key:
                    conn.execute(
                        """
                        INSERT INTO report_meta_scopes(file_name, instance_scope_key, updated_at)
                        VALUES (?, ?, ?)
                        ON CONFLICT(file_name) DO UPDATE SET
                            instance_scope_key=excluded.instance_scope_key,
                            updated_at=excluded.updated_at
                        """,
                        (item["file_name"], scope_key, now_iso),
                    )
                    imported["report_meta_scopes"] += 1
                else:
                    conn.execute(
                        "DELETE FROM report_meta_scopes WHERE file_name = ?",
                        (item["file_name"],),
                    )
                if item.get("deleted"):
                    conn.execute(
                        """
                        INSERT INTO report_meta_deleted_reports(file_name, deleted_at)
                        VALUES (?, ?)
                        ON CONFLICT(file_name) DO UPDATE SET
                            deleted_at=excluded.deleted_at
                        """,
                        (item["file_name"], now_iso),
                    )
                    imported["report_meta_deleted_reports"] += 1

            for row in plan["planned_solution_shares"]:
                if row["report_name"] not in imported_report_names and skip_existing:
                    continue
                conn.execute(
                    """
                    INSERT INTO report_meta_solution_shares(
                        share_token, report_name, owner_user_id, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(share_token) DO UPDATE SET
                        report_name=excluded.report_name,
                        owner_user_id=excluded.owner_user_id,
                        created_at=excluded.created_at,
                        updated_at=excluded.updated_at
                    """,
                    (
                        row["share_token"],
                        row["report_name"],
                        int(row["owner_user_id"]),
                        row["created_at"] or now_iso,
                        row["updated_at"] or now_iso,
                    ),
                )
                imported["report_meta_solution_shares"] += 1

        if "custom-scenarios" in includes:
            rows = []
            for item in plan["planned_custom_scenarios"]:
                payload = deepcopy(item["payload"])
                payload["owner_user_id"] = int(item["target_owner_user_id"])
                payload[server_module.INSTANCE_SCOPE_FIELD] = resolve_target_scope_key(
                    source_scope_key=item.get("instance_scope_key", ""),
                    rewrite_to_active_scope=rewrite_to_active_scope,
                    active_scope_key=active_scope_key,
                    server_module=server_module,
                )
                meta = payload.get("meta")
                if isinstance(meta, dict):
                    meta["owner_user_id"] = int(item["target_owner_user_id"])
                    meta["instance_scope_key"] = payload[server_module.INSTANCE_SCOPE_FIELD]
                rows.append({
                    "scenario_id": item["scenario_id"],
                    "owner_user_id": int(item["target_owner_user_id"]),
                    "instance_scope_key": str(payload.get(server_module.INSTANCE_SCOPE_FIELD) or ""),
                    "payload_json": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                    "created_at": str(payload.get("created_at") or ""),
                    "updated_at": str(payload.get("updated_at") or ""),
                })
            if rows:
                ownership_admin_service._upsert_custom_scenario_rows(conn, rows)
                imported["custom_scenarios"] = len(rows)

    if "indexes" in includes and rebuild_indexes:
        server_module.rebuild_session_index_from_disk(full_reset=True)
        server_module.rebuild_report_index_from_sources(full_reset=True)
        imported["indexes_rebuilt"] = True
    return imported


def run_import(
    *,
    source_data_dir: str,
    source_auth_db: str = "",
    target_user_id: int = 0,
    user_map_json: str = "",
    apply_changes: bool = False,
    output_json: str = "",
    include: str = ",".join(DEFAULT_INCLUDE),
    skip_existing: bool = True,
    rebuild_indexes: bool = True,
    rewrite_to_active_scope: bool = True,
    cleanup_target_user_scope_residue: Optional[bool] = None,
    server_module=None,
) -> dict[str, Any]:
    if server_module is None:
        server_module = load_server_module()

    includes = parse_include(include)
    bundle = discover_source_bundle(Path(source_data_dir))
    source_auth_db_path = Path(source_auth_db).expanduser().resolve() if str(source_auth_db or "").strip() else None
    ownerless_mode = source_auth_db_path is None
    user_map_config = load_user_map_json(user_map_json, ownerless_mode=ownerless_mode)

    server_module.ensure_meta_index_schema()
    auth_db_path = str(server_module.AUTH_DB_PATH)
    meta_index_db_path = str(server_module.get_meta_index_db_target())
    if not db_target_exists(auth_db_path):
        raise RuntimeError(f"目标鉴权数据库不存在: {auth_db_path}")

    target_users = load_target_users(auth_db_path)
    target_wechat_identities = load_target_wechat_identities(auth_db_path)
    target_indexes = build_target_user_indexes(target_users, target_wechat_identities)
    assert_target_user_ids_exist(target_indexes, user_map_config, target_user_id)

    source_users: list[dict[str, Any]] = []
    source_wechat_identities: list[dict[str, Any]] = []
    resolved_source_user_map: dict[int, dict[str, Any]] = {}
    unresolved_users: list[dict[str, Any]] = []
    ambiguous_users: list[dict[str, Any]] = []
    if source_auth_db_path is not None:
        source_users = load_source_users(source_auth_db_path)
        source_wechat_identities = load_source_wechat_identities(source_auth_db_path)
        resolved_source_user_map, unresolved_users, ambiguous_users = resolve_source_user_mappings(
            source_users=source_users,
            source_wechat_identity_map=build_source_identity_index(source_wechat_identities),
            target_indexes=target_indexes,
            user_map_config=user_map_config,
        )

    default_target_user_id = resolve_default_target_user_id(
        user_map_config=user_map_config,
        explicit_target_user_id=target_user_id,
    )
    if ownerless_mode and default_target_user_id <= 0:
        raise RuntimeError("无源端用户体系时必须提供 --target-user-id 或 user-map-json.default_target_user_id")

    active_scope_key = server_module.get_active_instance_scope_key()

    cloud_summary_before = summarize_cloud_tables(server_module)
    with ownership_admin_service.get_meta_index_connection(meta_index_db_path) as meta_conn:
        target_existing_session_ids = {
            str(row.get("session_id") or "").strip()
            for row in fetch_all_dicts(meta_conn, "SELECT session_id FROM session_store")
            if str(row.get("session_id") or "").strip()
        }
        target_existing_report_names = {
            str(row.get("file_name") or "").strip()
            for row in fetch_all_dicts(meta_conn, "SELECT file_name FROM report_store")
            if str(row.get("file_name") or "").strip()
        }

    plan = plan_import(
        bundle=bundle,
        includes=includes,
        ownerless_mode=ownerless_mode,
        resolved_source_user_map=resolved_source_user_map,
        unresolved_users=unresolved_users,
        ambiguous_users=ambiguous_users,
        user_map_config=user_map_config,
        default_target_user_id=default_target_user_id,
        target_existing_session_ids=target_existing_session_ids,
        target_existing_report_names=target_existing_report_names,
        rewrite_to_active_scope=bool(rewrite_to_active_scope),
        active_scope_key=active_scope_key,
        server_module=server_module,
    )
    plan["session_map_overrides"] = user_map_config.get("session_map") or {}
    plan["report_map_overrides"] = user_map_config.get("report_map") or {}
    scope_cleanup_enabled = resolve_scope_cleanup_enabled(
        rewrite_to_active_scope=bool(rewrite_to_active_scope),
        cleanup_target_user_scope_residue=cleanup_target_user_scope_residue,
    )
    plan["scope_cleanup"] = {
        "enabled": bool(scope_cleanup_enabled),
        **collect_scope_cleanup_candidates(
            target_owner_user_ids=collect_target_owner_user_ids(plan) if scope_cleanup_enabled else [],
            target_scope_key=server_module.get_record_instance_scope_key(active_scope_key),
            server_module=server_module,
        ),
    }

    backup_summary = None
    cloud_summary_after = None
    imported_summary = None
    scope_cleanup_summary = {
        **(plan.get("scope_cleanup") or {}),
        "applied": False,
        "cleaned": {
            "session_store": 0,
            "report_meta_scopes": 0,
            "custom_scenarios": 0,
        },
        "indexes_rebuilt": False,
        "scenario_loader_reloaded": False,
    }
    if apply_changes:
        backup_id = f"external-import-{utc_now_tag()}"
        backup_dir = ownership_admin_service.prepare_backup_dir(
            DEFAULT_BACKUP_ROOT,
            backup_id,
            default_target_user_id or 0,
            True,
        )
        backup_manifest = capture_db_snapshot(
            backup_dir,
            auth_db_path=auth_db_path,
            meta_index_db_path=meta_index_db_path,
        )
        imported_summary = apply_import_plan(
            plan=plan,
            server_module=server_module,
            includes=includes,
            skip_existing=skip_existing,
            rebuild_indexes=rebuild_indexes,
            rewrite_to_active_scope=bool(rewrite_to_active_scope),
            active_scope_key=active_scope_key,
        )
        if scope_cleanup_enabled:
            cleanup_result = apply_scope_cleanup(
                target_owner_user_ids=list((plan.get("scope_cleanup") or {}).get("target_owner_user_ids") or []),
                target_scope_key=server_module.get_record_instance_scope_key(active_scope_key),
                server_module=server_module,
            )
            scope_cleanup_summary["applied"] = bool(
                cleanup_result.get("session_store")
                or cleanup_result.get("report_meta_scopes")
                or cleanup_result.get("custom_scenarios")
            )
            scope_cleanup_summary["cleaned"] = {
                "session_store": int(cleanup_result.get("session_store") or 0),
                "report_meta_scopes": int(cleanup_result.get("report_meta_scopes") or 0),
                "custom_scenarios": int(cleanup_result.get("custom_scenarios") or 0),
            }
            if cleanup_result.get("requires_indexes_rebuild"):
                server_module.rebuild_session_index_from_disk(full_reset=True)
                server_module.rebuild_report_index_from_sources(full_reset=True)
                imported_summary["indexes_rebuilt"] = True
                scope_cleanup_summary["indexes_rebuilt"] = True
            if cleanup_result.get("requires_scenario_loader_reload"):
                try:
                    server_module.scenario_loader.reload()
                    scope_cleanup_summary["scenario_loader_reloaded"] = True
                except Exception:
                    scope_cleanup_summary["scenario_loader_reloaded"] = False
        cloud_summary_after = summarize_cloud_tables(server_module)
        backup_summary = {
            "performed": True,
            "backup_id": backup_manifest.get("backup_id"),
            "backup_dir": str(backup_dir),
            "manifest": backup_manifest,
        }
    else:
        backup_summary = {"performed": False}

    result = build_summary_payload(
        bundle=bundle,
        ownerless_mode=ownerless_mode,
        default_target_user_id=default_target_user_id,
        source_users=source_users,
        source_wechat_identities=source_wechat_identities,
        resolved_source_user_map=resolved_source_user_map,
        unresolved_users=unresolved_users,
        ambiguous_users=ambiguous_users,
        plan=plan,
        cloud_summary_before=cloud_summary_before,
        backup=backup_summary,
        applied=apply_changes,
        cloud_summary_after=cloud_summary_after,
        scope_cleanup=scope_cleanup_summary,
    )
    if imported_summary is not None:
        result["imported"] = imported_summary
    if str(output_json or "").strip():
        write_json_file(Path(output_json).expanduser().resolve(), result)
    return result


def main() -> None:
    args = parse_args()
    result = run_import(
        source_data_dir=args.source_data_dir,
        source_auth_db=args.source_auth_db,
        target_user_id=args.target_user_id,
        user_map_json=args.user_map_json,
        apply_changes=bool(args.apply),
        output_json=args.output_json,
        include=args.include,
        skip_existing=bool(args.skip_existing),
        rebuild_indexes=bool(args.rebuild_indexes),
        rewrite_to_active_scope=bool(args.rewrite_to_active_scope),
        cleanup_target_user_scope_residue=args.cleanup_target_user_scope_residue,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
