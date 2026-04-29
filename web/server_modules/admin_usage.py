from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from db_compat import connect_db


DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


def _parse_datetime(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _datetime_key(value: object) -> str:
    parsed = _parse_datetime(value)
    if not parsed:
        return ""
    return parsed.isoformat()


def _is_in_range(value: object, start_at: datetime | None, end_at: datetime | None) -> bool:
    parsed = _parse_datetime(value)
    if not parsed:
        return False
    if start_at and parsed < start_at:
        return False
    if end_at and parsed > end_at:
        return False
    return True


def _max_time(values: list[object]) -> str:
    parsed_values = [item for item in (_parse_datetime(value) for value in values) if item]
    if not parsed_values:
        return ""
    return max(parsed_values).isoformat()


def _safe_int(value: object, default: int = 0) -> int:
    try:
        return int(value or default)
    except (TypeError, ValueError):
        return default


def _decode_json(text: object, default: Any) -> Any:
    raw = str(text or "").strip()
    if not raw:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default


def _row_to_dict(row: Any) -> dict:
    if row is None:
        return {}
    if isinstance(row, dict):
        return dict(row)
    try:
        return dict(row)
    except Exception:
        return {}


def _fetch_rows(db_path: str | Path, sql: str, params: tuple = ()) -> list[dict]:
    try:
        with connect_db(str(db_path)) as conn:
            return [_row_to_dict(row) for row in conn.execute(sql, params).fetchall()]
    except Exception:
        return []


def parse_usage_filters(args: Mapping[str, Any], *, now: datetime | None = None) -> dict:
    current = now or datetime.now(timezone.utc)
    range_text = str(args.get("range") or "").strip().lower()
    days_text = str(args.get("days") or "").strip().lower()
    start_at = _parse_datetime(args.get("from") or args.get("start_at"))
    explicit_end = args.get("to") or args.get("end_at")
    end_at = _parse_datetime(explicit_end)

    if not start_at and range_text != "all" and days_text != "all":
        raw_days = days_text or range_text.removesuffix("d")
        days = _safe_int(raw_days, 30)
        if days <= 0:
            days = 30
        start_at = current - timedelta(days=days)
        range_text = f"{days}d"
    elif range_text == "all" or days_text == "all":
        range_text = "all"

    page = max(1, _safe_int(args.get("page"), 1))
    page_size = min(MAX_PAGE_SIZE, max(1, _safe_int(args.get("page_size"), DEFAULT_PAGE_SIZE)))

    return {
        "range": range_text or "custom",
        "from": start_at.isoformat() if start_at else "",
        "to": end_at.isoformat() if end_at else current.isoformat(),
        "start_at": start_at,
        "end_at": end_at,
        "query": str(args.get("q") or args.get("query") or "").strip().lower(),
        "scope": str(args.get("scope") or "").strip().lower(),
        "level_key": str(args.get("level_key") or "").strip().lower(),
        "license_status": str(args.get("license_status") or "").strip().lower(),
        "active": str(args.get("active") or "").strip().lower(),
        "page": page,
        "page_size": page_size,
    }


def _load_users(auth_db_path: str | Path) -> dict[int, dict]:
    rows = _fetch_rows(
        auth_db_path,
        """
        SELECT id, email, phone, created_at, updated_at, merged_into_user_id, merged_at
        FROM users
        ORDER BY id ASC
        """,
    )
    users: dict[int, dict] = {}
    for row in rows:
        user_id = _safe_int(row.get("id"), 0)
        if user_id <= 0:
            continue
        users[user_id] = {
            "id": user_id,
            "email": str(row.get("email") or "").strip(),
            "phone": str(row.get("phone") or "").strip(),
            "created_at": str(row.get("created_at") or "").strip(),
            "updated_at": str(row.get("updated_at") or "").strip(),
            "merged_into_user_id": _safe_int(row.get("merged_into_user_id"), 0) or None,
            "merged_at": str(row.get("merged_at") or "").strip(),
            "wechat": None,
        }

    wechat_rows = _fetch_rows(
        auth_db_path,
        """
        SELECT id, user_id, app_id, openid, unionid, nickname, avatar_url, created_at, updated_at
        FROM wechat_identities
        ORDER BY user_id ASC, updated_at DESC, id DESC
        """,
    )
    for row in wechat_rows:
        user_id = _safe_int(row.get("user_id"), 0)
        if user_id <= 0 or user_id not in users or users[user_id].get("wechat"):
            continue
        users[user_id]["wechat"] = {
            "nickname": str(row.get("nickname") or "").strip(),
            "avatar_url": str(row.get("avatar_url") or "").strip(),
            "app_id": str(row.get("app_id") or "").strip(),
            "openid": str(row.get("openid") or "").strip(),
            "unionid": str(row.get("unionid") or "").strip(),
            "updated_at": str(row.get("updated_at") or "").strip(),
        }
    return users


def _load_sessions(meta_index_db_path: str | Path) -> list[dict]:
    return _fetch_rows(
        meta_index_db_path,
        """
        SELECT session_id, file_name, owner_user_id, instance_scope_key, topic, status,
               created_at, updated_at, interview_count, scenario_id
        FROM session_index
        ORDER BY updated_at DESC, created_at DESC
        """,
    )


def _load_reports(meta_index_db_path: str | Path) -> list[dict]:
    return _fetch_rows(
        meta_index_db_path,
        """
        SELECT *
        FROM report_index
        WHERE deleted = 0
        ORDER BY created_at DESC
        """,
    )


def _load_documents(meta_index_db_path: str | Path) -> list[dict]:
    rows = _fetch_rows(
        meta_index_db_path,
        """
        SELECT session_id, file_name, owner_user_id, instance_scope_key, payload_json, created_at, updated_at
        FROM session_store
        ORDER BY updated_at DESC, created_at DESC
        """,
    )
    documents: list[dict] = []
    for row in rows:
        payload = _decode_json(row.get("payload_json"), {})
        if not isinstance(payload, dict):
            continue
        materials = payload.get("reference_materials")
        if not isinstance(materials, list):
            continue
        topic = str(payload.get("topic") or "").strip()
        for doc in materials:
            if not isinstance(doc, dict):
                continue
            uploaded_at = str(doc.get("uploaded_at") or row.get("updated_at") or "").strip()
            original_size = _safe_int(doc.get("original_size"), 0)
            stored_chars = _safe_int(doc.get("stored_chars"), 0)
            documents.append(
                {
                    "doc_id": str(doc.get("doc_id") or "").strip(),
                    "name": str(doc.get("name") or "").strip(),
                    "type": str(doc.get("type") or "").strip(),
                    "session_id": str(row.get("session_id") or "").strip(),
                    "session_file": str(row.get("file_name") or "").strip(),
                    "session_topic": topic,
                    "owner_user_id": _safe_int(row.get("owner_user_id"), 0),
                    "instance_scope_key": str(row.get("instance_scope_key") or "").strip(),
                    "uploaded_at": uploaded_at,
                    "parse_status": str(doc.get("parse_status") or "").strip() or "unknown",
                    "context_ready": bool(doc.get("context_ready")),
                    "is_truncated": bool(doc.get("is_truncated")),
                    "original_size": original_size,
                    "stored_chars": stored_chars,
                    "storage_backend": str(doc.get("storage_backend") or "").strip(),
                    "has_object_key": bool(str(doc.get("object_key") or "").strip()),
                }
            )
    return documents


def _license_rank(item: dict) -> tuple[int, str]:
    status = str(item.get("status") or "").strip().lower()
    rank = {
        "active": 0,
        "not_yet_active": 1,
        "issued": 2,
        "expired": 3,
        "revoked": 4,
        "replaced": 5,
    }.get(status, 9)
    return rank, _datetime_key(item.get("updated_at") or item.get("bound_at") or item.get("created_at"))


def _build_license_by_user(license_items: list[dict]) -> dict[int, dict]:
    licenses_by_user: dict[int, dict] = {}
    for item in license_items:
        user_id = _safe_int(item.get("bound_user_id"), 0)
        if user_id <= 0:
            continue
        current = licenses_by_user.get(user_id)
        if not current or _license_rank(item) < _license_rank(current):
            licenses_by_user[user_id] = {
                "id": _safe_int(item.get("id"), 0),
                "status": str(item.get("status") or "").strip() or "unknown",
                "level_key": str(item.get("level_key") or "").strip() or "standard",
                "level_name": str(item.get("level_name") or "").strip() or str(item.get("level_key") or "standard"),
                "bound_at": str(item.get("bound_at") or "").strip(),
                "expires_at": str(item.get("expires_at") or "").strip(),
                "masked_code": str(item.get("masked_code") or "").strip(),
            }
    return licenses_by_user


def _empty_usage() -> dict:
    return {
        "session_count": 0,
        "report_count": 0,
        "document_count": 0,
        "document_size_total": 0,
        "answer_count": 0,
        "instance_scope_keys": set(),
        "activity_times": [],
        "range_activity_times": [],
    }


def _matches_query(user: dict, query: str) -> bool:
    if not query:
        return True
    wechat = user.get("wechat") or {}
    haystack = " ".join(
        str(value or "").lower()
        for value in [
            user.get("id"),
            user.get("phone"),
            user.get("email"),
            wechat.get("nickname"),
            wechat.get("openid"),
            wechat.get("unionid"),
        ]
    )
    return query in haystack


def _scope_matches(record: dict, scope: str) -> bool:
    if not scope:
        return True
    return str(record.get("instance_scope_key") or "").strip().lower() == scope


def _user_display_account(user: dict) -> str:
    wechat = user.get("wechat") or {}
    return (
        str(wechat.get("nickname") or "").strip()
        or str(user.get("phone") or "").strip()
        or str(user.get("email") or "").strip()
        or f"用户 {user.get('id')}"
    )


def build_admin_usage_report(
    *,
    auth_db_path: str | Path,
    meta_index_db_path: str | Path,
    license_items: list[dict],
    filters: Mapping[str, Any],
    detail_user_id: int | None = None,
) -> dict:
    users = _load_users(auth_db_path)
    sessions = _load_sessions(meta_index_db_path)
    reports = _load_reports(meta_index_db_path)
    documents = _load_documents(meta_index_db_path)
    licenses_by_user = _build_license_by_user(license_items)

    start_at = filters.get("start_at")
    end_at = filters.get("end_at")
    query = str(filters.get("query") or "").strip().lower()
    scope = str(filters.get("scope") or "").strip().lower()
    level_filter = str(filters.get("level_key") or "").strip().lower()
    license_status_filter = str(filters.get("license_status") or "").strip().lower()
    active_filter = str(filters.get("active") or "").strip().lower()

    usage_by_user: dict[int, dict] = {user_id: _empty_usage() for user_id in users.keys()}
    detail_records = {
        "sessions": [],
        "reports": [],
        "documents": [],
    }

    for row in sessions:
        user_id = _safe_int(row.get("owner_user_id"), 0)
        if user_id <= 0 or user_id not in users or not _scope_matches(row, scope):
            continue
        usage = usage_by_user.setdefault(user_id, _empty_usage())
        updated_at = row.get("updated_at") or row.get("created_at")
        created_at = row.get("created_at")
        usage["activity_times"].extend([updated_at, created_at])
        if _is_in_range(updated_at, start_at, end_at) or _is_in_range(created_at, start_at, end_at):
            usage["session_count"] += 1
            usage["answer_count"] += max(0, _safe_int(row.get("interview_count"), 0))
            usage["range_activity_times"].append(updated_at or created_at)
        scope_key = str(row.get("instance_scope_key") or "").strip()
        if scope_key:
            usage["instance_scope_keys"].add(scope_key)
        if detail_user_id and user_id == detail_user_id:
            detail_records["sessions"].append(
                {
                    "session_id": str(row.get("session_id") or "").strip(),
                    "topic": str(row.get("topic") or "").strip(),
                    "status": str(row.get("status") or "").strip(),
                    "created_at": str(created_at or "").strip(),
                    "updated_at": str(updated_at or "").strip(),
                    "interview_count": _safe_int(row.get("interview_count"), 0),
                    "instance_scope_key": scope_key,
                }
            )

    for row in reports:
        user_id = _safe_int(row.get("owner_user_id"), 0)
        if user_id <= 0 or user_id not in users or not _scope_matches(row, scope):
            continue
        usage = usage_by_user.setdefault(user_id, _empty_usage())
        created_at = row.get("created_at")
        usage["activity_times"].append(created_at)
        if _is_in_range(created_at, start_at, end_at):
            usage["report_count"] += 1
            usage["range_activity_times"].append(created_at)
        scope_key = str(row.get("instance_scope_key") or "").strip()
        if scope_key:
            usage["instance_scope_keys"].add(scope_key)
        if detail_user_id and user_id == detail_user_id:
            detail_records["reports"].append(
                {
                    "file_name": str(row.get("file_name") or "").strip(),
                    "topic": str(row.get("topic") or "").strip(),
                    "created_at": str(created_at or "").strip(),
                    "report_type": str(row.get("report_type") or "").strip(),
                    "report_profile": str(row.get("report_profile") or "").strip(),
                    "report_variant_label": str(row.get("report_variant_label") or "").strip(),
                    "size": _safe_int(row.get("size") or row.get("file_size"), 0),
                    "instance_scope_key": scope_key,
                }
            )

    for row in documents:
        user_id = _safe_int(row.get("owner_user_id"), 0)
        if user_id <= 0 or user_id not in users or not _scope_matches(row, scope):
            continue
        usage = usage_by_user.setdefault(user_id, _empty_usage())
        uploaded_at = row.get("uploaded_at")
        usage["activity_times"].append(uploaded_at)
        if _is_in_range(uploaded_at, start_at, end_at):
            usage["document_count"] += 1
            usage["document_size_total"] += max(0, _safe_int(row.get("original_size"), 0))
            usage["range_activity_times"].append(uploaded_at)
        scope_key = str(row.get("instance_scope_key") or "").strip()
        if scope_key:
            usage["instance_scope_keys"].add(scope_key)
        if detail_user_id and user_id == detail_user_id:
            detail_records["documents"].append(
                {
                    "doc_id": str(row.get("doc_id") or "").strip(),
                    "name": str(row.get("name") or "").strip(),
                    "type": str(row.get("type") or "").strip(),
                    "session_id": str(row.get("session_id") or "").strip(),
                    "session_topic": str(row.get("session_topic") or "").strip(),
                    "uploaded_at": str(uploaded_at or "").strip(),
                    "parse_status": str(row.get("parse_status") or "").strip(),
                    "context_ready": bool(row.get("context_ready")),
                    "is_truncated": bool(row.get("is_truncated")),
                    "original_size": _safe_int(row.get("original_size"), 0),
                    "stored_chars": _safe_int(row.get("stored_chars"), 0),
                    "storage_backend": str(row.get("storage_backend") or "").strip(),
                    "has_object_key": bool(row.get("has_object_key")),
                    "instance_scope_key": scope_key,
                }
            )

    items: list[dict] = []
    status_counts: dict[str, int] = {}
    level_counts: dict[str, int] = {}
    scope_counts: dict[str, int] = {}
    total_sessions = 0
    total_reports = 0
    total_documents = 0
    total_document_size = 0

    for user_id, user in users.items():
        license_info = licenses_by_user.get(user_id) or {
            "status": "missing",
            "level_key": "",
            "level_name": "未绑定",
            "expires_at": "",
        }
        usage = usage_by_user.get(user_id) or _empty_usage()
        active = bool(usage["range_activity_times"])
        if not _matches_query(user, query):
            continue
        if level_filter and str(license_info.get("level_key") or "").lower() != level_filter:
            continue
        if license_status_filter and str(license_info.get("status") or "").lower() != license_status_filter:
            continue
        if active_filter in ("1", "true", "yes", "active") and not active:
            continue
        if active_filter in ("0", "false", "no", "inactive") and active:
            continue

        scope_keys = sorted(str(item) for item in usage["instance_scope_keys"] if item)
        for scope_key in scope_keys:
            scope_counts[scope_key] = scope_counts.get(scope_key, 0) + 1

        status_key = str(license_info.get("status") or "missing")
        level_key = str(license_info.get("level_key") or "missing")
        status_counts[status_key] = status_counts.get(status_key, 0) + 1
        level_counts[level_key] = level_counts.get(level_key, 0) + 1
        total_sessions += int(usage["session_count"])
        total_reports += int(usage["report_count"])
        total_documents += int(usage["document_count"])
        total_document_size += int(usage["document_size_total"])

        item = {
            "user": {
                **user,
                "account": _user_display_account(user),
                "wechat_bound": bool(user.get("wechat")),
            },
            "license": license_info,
            "usage": {
                "active": active,
                "session_count": int(usage["session_count"]),
                "report_count": int(usage["report_count"]),
                "document_count": int(usage["document_count"]),
                "document_size_total": int(usage["document_size_total"]),
                "answer_count": int(usage["answer_count"]),
                "instance_scope_keys": scope_keys,
                "last_activity_at": _max_time(usage["activity_times"]),
                "last_activity_in_range_at": _max_time(usage["range_activity_times"]),
                "last_login_at": "",
                "login_tracking_available": False,
            },
        }
        items.append(item)

    items.sort(
        key=lambda item: (
            item["usage"].get("last_activity_in_range_at") or item["usage"].get("last_activity_at") or "",
            item["user"].get("created_at") or "",
            item["user"].get("id") or 0,
        ),
        reverse=True,
    )

    page = _safe_int(filters.get("page"), 1)
    page_size = _safe_int(filters.get("page_size"), DEFAULT_PAGE_SIZE)
    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    paged_items = items[start:end]

    payload = {
        "filters": {
            "range": filters.get("range") or "custom",
            "from": filters.get("from") or "",
            "to": filters.get("to") or "",
            "query": query,
            "scope": scope,
            "level_key": level_filter,
            "license_status": license_status_filter,
            "active": active_filter,
        },
        "summary": {
            "total_users": len(users),
            "matched_users": total,
            "active_users": sum(1 for item in items if item["usage"].get("active")),
            "session_count": total_sessions,
            "report_count": total_reports,
            "document_count": total_documents,
            "document_size_total": total_document_size,
            "license_status_counts": status_counts,
            "license_level_counts": level_counts,
            "instance_scope_counts": scope_counts,
            "active_definition": "统计周期内有会话创建/更新、报告生成或参考文档上传；当前版本暂无独立登录流水。",
            "login_tracking_available": False,
        },
        "pagination": {
            "page": page,
            "page_size": page_size,
            "count": total,
            "total_pages": max(1, math.ceil(total / page_size)) if page_size else 1,
        },
        "items": paged_items,
    }

    if detail_user_id:
        detail = next((item for item in items if int(item["user"].get("id") or 0) == detail_user_id), None)
        payload["detail"] = {
            "user_id": detail_user_id,
            "found": bool(detail),
            "profile": detail,
            "sessions": detail_records["sessions"][:50],
            "reports": detail_records["reports"][:50],
            "documents": detail_records["documents"][:50],
        }

    return payload
