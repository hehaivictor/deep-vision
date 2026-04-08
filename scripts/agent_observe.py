#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
DeepVision agent 运行态观察入口。

目标：
1. 收口运行态健康、运维历史和最近 harness 结果
2. 尽量只读地观察本地文件、SQLite 数据和 artifact
3. 为 agent 提供“先观察，再改动”的固定入口
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from collections import Counter
from contextlib import closing
from dataclasses import asdict
from dataclasses import dataclass
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts import agent_history

DEFAULT_AUTH_DB = ROOT_DIR / "data" / "auth" / "users.db"
DEFAULT_LICENSE_DB = ROOT_DIR / "data" / "auth" / "licenses.db"
DEFAULT_META_INDEX_DB = ROOT_DIR / "data" / "meta_index.db"
DEFAULT_METRICS_FILE = ROOT_DIR / "data" / "metrics" / "api_metrics.json"
DEFAULT_SUMMARIES_DIR = ROOT_DIR / "data" / "summaries"
DEFAULT_OPERATIONS_DIR = ROOT_DIR / "data" / "operations"
DEFAULT_HARNESS_RUNS_DIR = ROOT_DIR / "artifacts" / "harness-runs"
HISTORY_SIGNAL_KINDS = (
    "harness",
    "evaluator",
    "ci-agent-smoke",
    "ci-guardrails",
    "ci-browser-smoke",
)
CONSECUTIVE_PROBLEM_ALERT_THRESHOLD = 2
CONSECUTIVE_PROBLEM_FAIL_THRESHOLD = 3
FREQUENT_BLOCKER_ALERT_THRESHOLD = 2
SLOW_REGRESSION_DELTA_ALERT_MS = 150.0
SLOW_REGRESSION_DELTA_FAIL_MS = 500.0
SLOW_REGRESSION_RATIO_ALERT = 1.2


@dataclass
class ObservationItem:
    name: str
    status: str
    detail: str
    data: dict[str, Any] | None = None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_env_file(env_file: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not env_file.exists():
        return values
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if value and len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[key] = value
    return values


def parse_bool(raw_value: object, default: bool = False) -> bool:
    text = str(raw_value or "").strip().lower()
    if not text:
        return default
    return text in {"1", "true", "yes", "on"}


def parse_iso_datetime(raw_value: object) -> datetime | None:
    text = str(raw_value or "").strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def format_dt(raw_value: object) -> str:
    dt = parse_iso_datetime(raw_value)
    if dt is None:
        return str(raw_value or "").strip()
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def file_modified_iso(path: Path) -> str:
    if not path.exists():
        return ""
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def to_repo_relative(root_dir: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(root_dir.resolve()))
    except Exception:
        return str(path)


def resolve_selected_env_file(*, root_dir: Path, profile: str, explicit_env_file: str) -> tuple[Path | None, str]:
    if str(explicit_env_file or "").strip():
        candidate = Path(str(explicit_env_file).strip()).expanduser()
        if not candidate.is_absolute():
            candidate = (root_dir / candidate).resolve()
        return candidate, "explicit"

    env_from_process = str(os.environ.get("DEEPVISION_ENV_FILE", "") or "").strip()
    if env_from_process:
        candidate = Path(env_from_process).expanduser()
        if not candidate.is_absolute():
            candidate = (root_dir / candidate).resolve()
        return candidate, "process_env"

    defaults = {
        "local": root_dir / "web" / ".env.local",
        "cloud": root_dir / "web" / ".env.cloud",
    }
    if profile in defaults:
        return defaults[profile], f"profile:{profile}"

    for profile_name in ("local", "cloud"):
        candidate = defaults[profile_name]
        if candidate.exists():
            return candidate, f"auto:{profile_name}"
    return None, "none"


def resolve_local_path(root_dir: Path, raw_value: object, default_path: Path) -> Path | None:
    text = str(raw_value or "").strip()
    if not text:
        return default_path
    if "://" in text:
        return None
    candidate = Path(text).expanduser()
    if not candidate.is_absolute():
        candidate = (root_dir / candidate).resolve()
    return candidate


def open_sqlite_readonly(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def sqlite_table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1",
        (str(table_name or "").strip(),),
    ).fetchone()
    return row is not None


def sqlite_count(conn: sqlite3.Connection, table_name: str) -> int:
    row = conn.execute(f"SELECT COUNT(1) AS total FROM {table_name}").fetchone()
    return int((row["total"] if row else 0) or 0)


def summarize_env(root_dir: Path, profile: str, selected_env_file: Path | None, env_source: str) -> ObservationItem:
    file_values = parse_env_file(selected_env_file) if selected_env_file and selected_env_file.exists() else {}
    admin_phones = [item.strip() for item in str(file_values.get("ADMIN_PHONE_NUMBERS", "") or "").split(",") if item.strip()]
    detail = (
        f"profile={profile} env={to_repo_relative(root_dir, selected_env_file) if selected_env_file else 'none'} "
        f"source={env_source} keys={len(file_values)}"
    )
    return ObservationItem(
        name="env",
        status="PASS" if selected_env_file and selected_env_file.exists() else "WARN",
        detail=detail,
        data={
            "profile": profile,
            "source": env_source,
            "env_file": str(selected_env_file) if selected_env_file else "",
            "config_resolution_mode": str(file_values.get("CONFIG_RESOLUTION_MODE", "") or "").strip(),
            "debug_mode": parse_bool(file_values.get("DEBUG_MODE", ""), default=False),
            "enable_ai": parse_bool(file_values.get("ENABLE_AI", ""), default=True),
            "sms_login_enabled": parse_bool(file_values.get("SMS_LOGIN_ENABLED", ""), default=True),
            "sms_provider": str(file_values.get("SMS_PROVIDER", "") or "").strip(),
            "wechat_login_enabled": parse_bool(file_values.get("WECHAT_LOGIN_ENABLED", ""), default=False),
            "instance_scope_key": str(file_values.get("INSTANCE_SCOPE_KEY", "") or "").strip(),
            "admin_phone_numbers_count": len(admin_phones),
        },
    )


def summarize_db_health(root_dir: Path, env_data: dict[str, Any]) -> ObservationItem:
    auth_db = resolve_local_path(root_dir, env_data.get("AUTH_DB_PATH"), DEFAULT_AUTH_DB)
    license_db = resolve_local_path(root_dir, env_data.get("LICENSE_DB_PATH"), DEFAULT_LICENSE_DB)
    meta_index_db = resolve_local_path(root_dir, env_data.get("META_INDEX_DB_PATH"), DEFAULT_META_INDEX_DB)

    payload: dict[str, Any] = {
        "auth_db": {"path": str(auth_db) if auth_db else "", "exists": bool(auth_db and auth_db.exists())},
        "license_db": {"path": str(license_db) if license_db else "", "exists": bool(license_db and license_db.exists())},
        "meta_index_db": {"path": str(meta_index_db) if meta_index_db else "", "exists": bool(meta_index_db and meta_index_db.exists())},
    }
    warnings: list[str] = []

    if auth_db and auth_db.exists():
        with closing(open_sqlite_readonly(auth_db)) as conn:
            payload["auth_db"]["users"] = sqlite_count(conn, "users") if sqlite_table_exists(conn, "users") else 0
            payload["auth_db"]["wechat_identities"] = sqlite_count(conn, "wechat_identities") if sqlite_table_exists(conn, "wechat_identities") else 0
            payload["auth_db"]["modified_at"] = file_modified_iso(auth_db)
    else:
        warnings.append("auth_db 缺失")

    if license_db and license_db.exists():
        with closing(open_sqlite_readonly(license_db)) as conn:
            if sqlite_table_exists(conn, "licenses"):
                row = conn.execute(
                    """
                    SELECT
                        COUNT(1) AS total,
                        SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END) AS active_count,
                        SUM(CASE WHEN status = 'expired' THEN 1 ELSE 0 END) AS expired_count,
                        SUM(CASE WHEN status = 'revoked' THEN 1 ELSE 0 END) AS revoked_count
                    FROM licenses
                    """
                ).fetchone()
                payload["license_db"]["summary"] = {
                    "total": int((row["total"] if row else 0) or 0),
                    "active": int((row["active_count"] if row else 0) or 0),
                    "expired": int((row["expired_count"] if row else 0) or 0),
                    "revoked": int((row["revoked_count"] if row else 0) or 0),
                }
            payload["license_db"]["modified_at"] = file_modified_iso(license_db)
    else:
        warnings.append("license_db 缺失")

    if meta_index_db and meta_index_db.exists():
        with closing(open_sqlite_readonly(meta_index_db)) as conn:
            table_counts = {}
            required_tables = [
                "session_store",
                "report_store",
                "summary_cache_store",
                "runtime_metrics_store",
            ]
            for table_name in required_tables:
                table_counts[table_name] = sqlite_count(conn, table_name) if sqlite_table_exists(conn, table_name) else None
                if table_counts[table_name] is None:
                    warnings.append(f"{table_name} 缺失")
            payload["meta_index_db"]["table_counts"] = table_counts
            payload["meta_index_db"]["schema_ready"] = all(table_counts.get(name) is not None for name in required_tables)
            payload["meta_index_db"]["modified_at"] = file_modified_iso(meta_index_db)
    else:
        warnings.append("meta_index_db 缺失")

    detail = (
        f"auth={payload['auth_db'].get('users', 'n/a')} users "
        f"license={payload['license_db'].get('summary', {}).get('total', 'n/a')} "
        f"meta_schema={'ready' if payload['meta_index_db'].get('schema_ready') else 'unknown'}"
    )
    return ObservationItem(
        name="db_health",
        status="WARN" if warnings else "PASS",
        detail=detail,
        data={**payload, "warnings": warnings},
    )


def _load_metrics_payload(meta_index_db: Path | None, metrics_file: Path) -> tuple[dict[str, Any], str]:
    if meta_index_db and meta_index_db.exists():
        with closing(open_sqlite_readonly(meta_index_db)) as conn:
            if sqlite_table_exists(conn, "runtime_metrics_store"):
                row = conn.execute(
                    "SELECT payload_json FROM runtime_metrics_store WHERE metric_key = 'api_metrics' LIMIT 1"
                ).fetchone()
                if row and row["payload_json"]:
                    try:
                        return json.loads(str(row["payload_json"])), "runtime_metrics_store"
                    except Exception:
                        pass
    if metrics_file.exists():
        try:
            return json.loads(metrics_file.read_text(encoding="utf-8")), "api_metrics.json"
        except Exception:
            pass
    return {}, ""


def summarize_metrics(root_dir: Path, meta_index_db: Path | None, recent: int) -> ObservationItem:
    metrics_payload, source = _load_metrics_payload(meta_index_db, root_dir / "data" / "metrics" / "api_metrics.json")
    calls = metrics_payload.get("calls", []) if isinstance(metrics_payload, dict) else []
    if not isinstance(calls, list):
        calls = []
    api_calls = [item for item in calls if isinstance(item, dict) and str(item.get("event_kind", "api_call")).lower() == "api_call"]
    summary = metrics_payload.get("summary", {}) if isinstance(metrics_payload.get("summary", {}), dict) else {}
    sorted_calls = sorted(
        [item for item in api_calls if str(item.get("timestamp") or "").strip()],
        key=lambda item: str(item.get("timestamp") or ""),
        reverse=True,
    )
    recent_failures = [
        {
            "timestamp": format_dt(item.get("timestamp")),
            "type": str(item.get("type") or "").strip(),
            "stage": str(item.get("stage") or "").strip(),
            "timeout": bool(item.get("timeout", False)),
            "error": str(item.get("error") or "").strip(),
        }
        for item in sorted_calls
        if (not bool(item.get("success", True))) or bool(item.get("timeout", False)) or str(item.get("error") or "").strip()
    ][:recent]
    top_types = Counter(str(item.get("type") or "").strip() for item in api_calls if str(item.get("type") or "").strip()).most_common(5)
    detail = (
        f"source={source or 'none'} total={int(summary.get('total_calls', 0) or 0)} "
        f"avg_ms={float(summary.get('avg_response_time', 0) or 0):.1f} recent_failures={len(recent_failures)}"
    )
    return ObservationItem(
        name="metrics",
        status="PASS" if source else "WARN",
        detail=detail,
        data={
            "source": source,
            "summary": {
                "total_calls": int(summary.get("total_calls", 0) or 0),
                "total_timeouts": int(summary.get("total_timeouts", 0) or 0),
                "total_cache_hits": int(summary.get("total_cache_hits", 0) or 0),
                "avg_response_time": float(summary.get("avg_response_time", 0) or 0),
                "avg_queue_wait_ms": float(summary.get("avg_queue_wait_ms", 0) or 0),
            },
            "latest_call_at": format_dt(sorted_calls[0].get("timestamp")) if sorted_calls else "",
            "recent_failures": recent_failures,
            "top_types": [{"type": name, "count": count} for name, count in top_types],
        },
    )


def summarize_summaries(root_dir: Path, meta_index_db: Path | None) -> ObservationItem:
    payload: dict[str, Any] = {"source": "", "cached_count": 0, "cache_size_bytes": 0}
    summaries_dir = root_dir / "data" / "summaries"
    if meta_index_db and meta_index_db.exists():
        with closing(open_sqlite_readonly(meta_index_db)) as conn:
            if sqlite_table_exists(conn, "summary_cache_store"):
                row = conn.execute(
                    "SELECT COUNT(1) AS total, COALESCE(SUM(LENGTH(summary_text)), 0) AS total_size FROM summary_cache_store"
                ).fetchone()
                payload["source"] = "summary_cache_store"
                payload["cached_count"] = int((row["total"] if row else 0) or 0)
                payload["cache_size_bytes"] = int((row["total_size"] if row else 0) or 0)
    if not payload["source"]:
        files = list(summaries_dir.glob("*.txt")) if summaries_dir.exists() else []
        payload["source"] = "summaries_dir" if summaries_dir.exists() else ""
        payload["cached_count"] = len(files)
        payload["cache_size_bytes"] = sum(item.stat().st_size for item in files)
    detail = f"source={payload['source'] or 'none'} cached={payload['cached_count']} size_kb={round(payload['cache_size_bytes'] / 1024, 2)}"
    return ObservationItem(
        name="summaries",
        status="PASS" if payload["source"] else "WARN",
        detail=detail,
        data=payload,
    )


def summarize_config_sources(root_dir: Path, env_file: str, env_source: str, file_values: dict[str, str]) -> ObservationItem:
    selected_env_file = Path(env_file) if env_file else None
    sources = []
    for label, path in [
        ("env", selected_env_file),
        ("config", root_dir / "web" / "config.py"),
        ("site", root_dir / "web" / "site-config.js"),
    ]:
        if path is None:
            sources.append({"source": label, "path": "", "exists": False, "modified_at": "", "size_bytes": 0})
            continue
        sources.append(
            {
                "source": label,
                "path": to_repo_relative(root_dir, path),
                "exists": path.exists(),
                "modified_at": file_modified_iso(path),
                "size_bytes": int(path.stat().st_size) if path.exists() else 0,
            }
        )
    detail = (
        f"env_source={env_source} env={sources[0]['path'] or 'none'} "
        f"sms={'on' if parse_bool(file_values.get('SMS_LOGIN_ENABLED', ''), default=True) else 'off'}"
        f"({str(file_values.get('SMS_PROVIDER', '') or '').strip() or '-'}) "
        f"ai={'on' if parse_bool(file_values.get('ENABLE_AI', ''), default=True) else 'off'}"
    )
    return ObservationItem(
        name="config_sources",
        status="PASS" if any(item["exists"] for item in sources[1:]) or sources[0]["exists"] else "WARN",
        detail=detail,
        data={
            "sources": sources,
            "note": "当前没有独立的配置中心写入审计，这里使用源文件存在性与修改时间做近似观察。",
        },
    )


def summarize_ownership_history(root_dir: Path, recent: int) -> ObservationItem:
    backup_root = root_dir / "data" / "operations" / "ownership-migrations"
    items: list[dict[str, Any]] = []
    if backup_root.exists():
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
                    "generated_at": format_dt(metadata.get("generated_at")),
                    "mode": str(metadata.get("mode") or "").strip(),
                    "scope": str(metadata.get("scope") or "").strip(),
                    "target_account": str((metadata.get("target_user") or {}).get("account") or "").strip(),
                    "sessions_updated": int(((metadata.get("sessions") or {}).get("updated", 0)) or 0),
                    "reports_updated": int(((metadata.get("reports") or {}).get("updated", 0)) or 0),
                    "rolled_back": bool(rollback_payload),
                    "rolled_back_at": format_dt((rollback_payload or {}).get("rolled_back_at")),
                }
            )
    items.sort(key=lambda item: str(item.get("generated_at") or ""), reverse=True)
    recent_items = items[:recent]
    detail = f"items={len(items)} latest={recent_items[0]['backup_id'] if recent_items else 'none'}"
    return ObservationItem(
        name="ownership_history",
        status="PASS" if items else "WARN",
        detail=detail,
        data={"items": recent_items},
    )


def summarize_cloud_import_backups(root_dir: Path, recent: int) -> ObservationItem:
    backup_root = root_dir / "data" / "operations" / "cloud-import-backups"
    items: list[dict[str, Any]] = []
    if backup_root.exists():
        for manifest_path in backup_root.glob("*/backup-manifest.json"):
            try:
                payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            items.append(
                {
                    "backup_id": str(payload.get("backup_id") or manifest_path.parent.name).strip(),
                    "captured_at": format_dt(payload.get("captured_at")),
                    "backup_dir": to_repo_relative(root_dir, manifest_path.parent),
                    "restorable_tables": sorted((payload.get("restorable_tables") or {}).keys()) if isinstance(payload.get("restorable_tables"), dict) else [],
                }
            )
    items.sort(key=lambda item: str(item.get("captured_at") or ""), reverse=True)
    recent_items = items[:recent]
    detail = f"items={len(items)} latest={recent_items[0]['backup_id'] if recent_items else 'none'}"
    return ObservationItem(
        name="cloud_import_backups",
        status="PASS" if items else "WARN",
        detail=detail,
        data={"items": recent_items},
    )


def summarize_recent_operations(root_dir: Path, recent: int) -> ObservationItem:
    operations_dir = root_dir / "data" / "operations"
    items: list[dict[str, Any]] = []
    if operations_dir.exists():
        for path in operations_dir.iterdir():
            if not path.is_file():
                continue
            items.append(
                {
                    "path": to_repo_relative(root_dir, path),
                    "modified_at": file_modified_iso(path),
                    "size_bytes": int(path.stat().st_size),
                }
            )
    items.sort(key=lambda item: str(item.get("modified_at") or ""), reverse=True)
    recent_items = items[:recent]
    detail = f"recent_files={len(recent_items)} latest={recent_items[0]['path'] if recent_items else 'none'}"
    return ObservationItem(
        name="recent_operations",
        status="PASS" if recent_items else "WARN",
        detail=detail,
        data={"items": recent_items},
    )


def summarize_harness_runs(root_dir: Path, recent: int) -> ObservationItem:
    runs_root = root_dir / "artifacts" / "harness-runs"
    runs: list[dict[str, Any]] = []
    if runs_root.exists():
        for run_dir in runs_root.iterdir():
            if not run_dir.is_dir():
                continue
            summary_file = run_dir / "summary.json"
            if not summary_file.exists():
                continue
            try:
                payload = json.loads(summary_file.read_text(encoding="utf-8"))
            except Exception:
                continue
            failed_stages = [
                str(item.get("name") or "").strip()
                for item in list(payload.get("results", []) or [])
                if str(item.get("status") or "").strip() == "FAIL"
            ]
            runs.append(
                {
                    "run_name": run_dir.name,
                    "generated_at": format_dt(payload.get("generated_at")),
                    "overall": str(payload.get("overall") or "").strip(),
                    "summary": payload.get("summary") or {},
                    "failed_stages": failed_stages,
                    "task": ((payload.get("task") or {}).get("name") if isinstance(payload.get("task"), dict) else ""),
                }
            )
    runs.sort(key=lambda item: str(item.get("generated_at") or ""), reverse=True)
    latest_pointer = {}
    latest_file = runs_root / "latest.json"
    if latest_file.exists():
        try:
            latest_pointer = json.loads(latest_file.read_text(encoding="utf-8"))
        except Exception:
            latest_pointer = {}
    blocked_runs = [item for item in runs if str(item.get("overall") or "").strip() == "BLOCKED"][:recent]
    detail = (
        f"runs={len(runs)} latest={str(latest_pointer.get('overall') or '').strip() or 'none'} "
        f"blocked={len(blocked_runs)}"
    )
    return ObservationItem(
        name="harness_runs",
        status="PASS" if runs else "WARN",
        detail=detail,
        data={
            "latest_pointer": latest_pointer,
            "recent_runs": runs[:recent],
            "recent_blocked_runs": blocked_runs,
        },
    )


def _history_health_bucket(overall: object) -> str:
    value = str(overall or "").strip().upper()
    if not value:
        return "missing"
    if value in {"READY", "HEALTHY", "PASS", "UNCHANGED"}:
        return "healthy"
    if value in {"BLOCKED", "FAIL", "FAILED", "ERROR", "EMPTY"}:
        return "problem"
    return "warning"


def _load_json_file(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _load_run_summary(record: dict[str, Any]) -> dict[str, Any]:
    files = record.get("files", {}) if isinstance(record.get("files", {}), dict) else {}
    summary_path = Path(str(files.get("summary_file") or "")).resolve() if str(files.get("summary_file") or "").strip() else None
    return _load_json_file(summary_path)


def _load_run_handoff(record: dict[str, Any]) -> dict[str, Any]:
    files = record.get("files", {}) if isinstance(record.get("files", {}), dict) else {}
    handoff_path = Path(str(files.get("handoff_file") or "")).resolve() if str(files.get("handoff_file") or "").strip() else None
    return _load_json_file(handoff_path)


def _shorten_text(value: object, limit: int = 48) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _aggregate_problem_tasks(root_dir: Path, recent: int) -> list[dict[str, Any]]:
    runs = agent_history.list_history_runs("harness", root_dir=root_dir, limit=max(3, recent * 4))
    counts: dict[str, dict[str, Any]] = {}
    for record in runs:
        overall = str(record.get("overall") or "").strip()
        if _history_health_bucket(overall) not in {"problem", "warning"}:
            continue
        subject = str(record.get("subject") or "").strip()
        if not subject:
            continue
        entry = counts.setdefault(
            subject,
            {
                "subject": subject,
                "count": 0,
                "overalls": Counter(),
                "latest_generated_at": "",
            },
        )
        entry["count"] += 1
        entry["overalls"][overall] += 1
        generated_at = str(record.get("generated_at") or "").strip()
        if generated_at > str(entry.get("latest_generated_at") or ""):
            entry["latest_generated_at"] = generated_at
    sortable = list(counts.values())
    sortable.sort(
        key=lambda item: (
            -int(item.get("count", 0) or 0),
            str(item.get("latest_generated_at") or ""),
            str(item.get("subject") or ""),
        ),
        reverse=False,
    )
    normalized: list[dict[str, Any]] = []
    for item in sortable[:5]:
        overalls_counter = item.get("overalls")
        normalized.append(
            {
                "subject": str(item.get("subject") or "").strip(),
                "count": int(item.get("count", 0) or 0),
                "latest_generated_at": str(item.get("latest_generated_at") or "").strip(),
                "overalls": dict(overalls_counter) if isinstance(overalls_counter, Counter) else {},
            }
        )
    return normalized


def _aggregate_top_blockers(root_dir: Path, recent: int) -> list[dict[str, Any]]:
    counts: dict[str, dict[str, Any]] = {}
    for kind in ("harness", "evaluator", "ci-agent-smoke", "ci-guardrails", "ci-browser-smoke"):
        runs = agent_history.list_history_runs(kind, root_dir=root_dir, limit=max(3, recent))
        for record in runs:
            handoff = _load_run_handoff(record)
            blockers = [str(item).strip() for item in list(handoff.get("blockers", []) or []) if str(item).strip()]
            if not blockers:
                continue
            for blocker in blockers:
                entry = counts.setdefault(
                    blocker,
                    {
                        "text": blocker,
                        "count": 0,
                        "kinds": Counter(),
                        "latest_generated_at": "",
                    },
                )
                entry["count"] += 1
                entry["kinds"][kind] += 1
                generated_at = str(record.get("generated_at") or "").strip()
                if generated_at > str(entry.get("latest_generated_at") or ""):
                    entry["latest_generated_at"] = generated_at
    sortable = list(counts.values())
    sortable.sort(
        key=lambda item: (
            -int(item.get("count", 0) or 0),
            str(item.get("latest_generated_at") or ""),
            str(item.get("text") or ""),
        ),
        reverse=False,
    )
    normalized: list[dict[str, Any]] = []
    for item in sortable[:5]:
        kinds_counter = item.get("kinds")
        normalized.append(
            {
                "text": str(item.get("text") or "").strip(),
                "count": int(item.get("count", 0) or 0),
                "latest_generated_at": str(item.get("latest_generated_at") or "").strip(),
                "kinds": dict(kinds_counter) if isinstance(kinds_counter, Counter) else {},
            }
        )
    return normalized


def _extract_slow_scenario_entries(summary_payload: dict[str, Any]) -> list[dict[str, Any]]:
    slowest = summary_payload.get("slowest_scenarios")
    if isinstance(slowest, list) and slowest:
        items: list[dict[str, Any]] = []
        for item in slowest:
            if not isinstance(item, dict):
                continue
            items.append(
                {
                    "name": str(item.get("name") or "").strip(),
                    "category": str(item.get("category") or "").strip(),
                    "max_duration_ms": float(item.get("max_duration_ms", 0) or 0),
                    "budget_exceeded": bool(item.get("budget_exceeded", False)),
                }
            )
        if items:
            return items

    items = []
    for result in list(summary_payload.get("results", []) or []):
        if not isinstance(result, dict):
            continue
        stats = result.get("stats", {}) if isinstance(result.get("stats", {}), dict) else {}
        max_duration_ms = float(stats.get("max_duration_ms", 0) or 0)
        if max_duration_ms <= 0:
            continue
        items.append(
            {
                "name": str(result.get("name") or "").strip(),
                "category": str(result.get("category") or "").strip(),
                "max_duration_ms": max_duration_ms,
                "budget_exceeded": bool(stats.get("budget_exceeded", False)),
            }
        )
    return items


def _aggregate_slow_scenarios(root_dir: Path, recent: int) -> list[dict[str, Any]]:
    runs = agent_history.list_history_runs("evaluator", root_dir=root_dir, limit=max(3, recent))
    aggregated: dict[str, dict[str, Any]] = {}
    for record in runs:
        summary_payload = _load_run_summary(record)
        for item in _extract_slow_scenario_entries(summary_payload):
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            entry = aggregated.setdefault(
                name,
                {
                    "name": name,
                    "category": str(item.get("category") or "").strip(),
                    "count": 0,
                    "max_duration_ms": 0.0,
                    "budget_exceeded": False,
                },
            )
            entry["count"] += 1
            entry["max_duration_ms"] = max(float(entry.get("max_duration_ms", 0) or 0), float(item.get("max_duration_ms", 0) or 0))
            entry["budget_exceeded"] = bool(entry.get("budget_exceeded", False) or item.get("budget_exceeded", False))
            if not entry.get("category") and item.get("category"):
                entry["category"] = str(item.get("category") or "").strip()
    sortable = list(aggregated.values())
    sortable.sort(
        key=lambda item: (
            -float(item.get("max_duration_ms", 0) or 0),
            -int(item.get("count", 0) or 0),
            str(item.get("name") or ""),
        )
    )
    return [
        {
            "name": str(item.get("name") or "").strip(),
            "category": str(item.get("category") or "").strip(),
            "count": int(item.get("count", 0) or 0),
            "max_duration_ms": round(float(item.get("max_duration_ms", 0) or 0), 2),
            "budget_exceeded": bool(item.get("budget_exceeded", False)),
        }
        for item in sortable[:5]
    ]


def _aggregate_consecutive_problem_runs(root_dir: Path, recent: int) -> list[dict[str, Any]]:
    alert_items: list[dict[str, Any]] = []
    for kind in HISTORY_SIGNAL_KINDS:
        runs = agent_history.list_history_runs(kind, root_dir=root_dir, limit=max(4, recent * 4))
        if not runs:
            continue
        streak = 0
        latest_record: dict[str, Any] | None = None
        for record in runs:
            if _history_health_bucket(record.get("overall")) != "problem":
                break
            streak += 1
            if latest_record is None:
                latest_record = record
        if streak < CONSECUTIVE_PROBLEM_ALERT_THRESHOLD or latest_record is None:
            continue
        alert_items.append(
            {
                "kind": kind,
                "streak": streak,
                "overall": str(latest_record.get("overall") or "").strip(),
                "subject": str(latest_record.get("subject") or "").strip(),
                "generated_at": str(latest_record.get("generated_at") or "").strip(),
                "run_name": str(latest_record.get("run_name") or "").strip(),
            }
        )
    alert_items.sort(
        key=lambda item: (
            -int(item.get("streak", 0) or 0),
            str(item.get("generated_at") or ""),
            str(item.get("kind") or ""),
        ),
    )
    return alert_items[:5]


def _aggregate_frequent_blockers(top_blockers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    frequent: list[dict[str, Any]] = []
    for item in top_blockers:
        if int(item.get("count", 0) or 0) < FREQUENT_BLOCKER_ALERT_THRESHOLD:
            continue
        frequent.append(
            {
                "text": str(item.get("text") or "").strip(),
                "count": int(item.get("count", 0) or 0),
                "latest_generated_at": str(item.get("latest_generated_at") or "").strip(),
                "kinds": dict(item.get("kinds") or {}) if isinstance(item.get("kinds"), dict) else {},
            }
        )
    return frequent[:5]


def _aggregate_slow_regressions(root_dir: Path, recent: int) -> list[dict[str, Any]]:
    runs = agent_history.list_history_runs("evaluator", root_dir=root_dir, limit=max(3, recent * 3))
    if len(runs) < 2:
        return []
    latest_summary = _load_run_summary(runs[0])
    previous_summary = _load_run_summary(runs[1])
    latest_items = {
        str(item.get("name") or "").strip(): item
        for item in _extract_slow_scenario_entries(latest_summary)
        if str(item.get("name") or "").strip()
    }
    previous_items = {
        str(item.get("name") or "").strip(): item
        for item in _extract_slow_scenario_entries(previous_summary)
        if str(item.get("name") or "").strip()
    }
    regressions: list[dict[str, Any]] = []
    for name in sorted(set(latest_items) & set(previous_items)):
        latest_item = latest_items[name]
        previous_item = previous_items[name]
        after_ms = float(latest_item.get("max_duration_ms", 0) or 0)
        before_ms = float(previous_item.get("max_duration_ms", 0) or 0)
        if after_ms <= before_ms:
            continue
        delta_ms = after_ms - before_ms
        ratio = (after_ms / before_ms) if before_ms > 0 else float("inf")
        if delta_ms < SLOW_REGRESSION_DELTA_ALERT_MS and ratio < SLOW_REGRESSION_RATIO_ALERT:
            continue
        regressions.append(
            {
                "name": name,
                "category": str(latest_item.get("category") or previous_item.get("category") or "").strip(),
                "before_ms": round(before_ms, 2),
                "after_ms": round(after_ms, 2),
                "delta_ms": round(delta_ms, 2),
                "ratio": round(ratio, 2) if ratio != float("inf") else "inf",
                "budget_exceeded": bool(latest_item.get("budget_exceeded", False) or previous_item.get("budget_exceeded", False)),
                "latest_run": str(runs[0].get("run_name") or "").strip(),
                "previous_run": str(runs[1].get("run_name") or "").strip(),
            }
        )
    regressions.sort(
        key=lambda item: (
            not bool(item.get("budget_exceeded", False)),
            -float(item.get("delta_ms", 0) or 0),
            -float(item.get("after_ms", 0) or 0),
            str(item.get("name") or ""),
        )
    )
    return regressions[:5]


def _extract_resume_commands(record: dict[str, Any]) -> list[str]:
    handoff = _load_run_handoff(record)
    return [str(item).strip() for item in list(handoff.get("resume_commands", []) or []) if str(item).strip()]


def _build_default_task_command(task_name: str) -> str:
    return f"python3 scripts/agent_harness.py --task {task_name} --profile auto --artifact-dir artifacts/harness-runs"


def _build_default_scenario_command(name: str) -> str:
    return f"python3 scripts/agent_eval.py --scenario {name} --artifact-dir artifacts/harness-eval"


def _infer_blocker_command(blocker_text: str, task_name: str = "") -> str:
    text = str(blocker_text or "").strip().lower()
    if not text:
        return ""
    if "browser_smoke" in text or "browser smoke" in text:
        return "python3 scripts/agent_browser_smoke.py --suite extended"
    if text.startswith("guardrails:") or " guardrails" in text:
        return "python3 scripts/agent_guardrails.py --quiet"
    if text.startswith("smoke:") or text == "smoke" or " smoke" in text:
        return "python3 scripts/agent_smoke.py"
    if text.startswith("doctor:") or text == "doctor" or " doctor" in text:
        return "python3 scripts/agent_doctor.py --profile auto"
    if "workflow" in text and task_name:
        return (
            f"python3 scripts/agent_harness.py --task {task_name} "
            "--workflow-execute preview --artifact-dir artifacts/harness-runs"
        )
    return _build_default_task_command(task_name) if task_name else ""


def _append_unique_command(target: list[dict[str, Any]], *, reason: str, command: str, source: str, subject: str = "") -> None:
    normalized = str(command or "").strip()
    if not normalized:
        return
    if any(str(item.get("command") or "").strip() == normalized for item in target):
        return
    target.append(
        {
            "reason": str(reason or "").strip(),
            "command": normalized,
            "source": str(source or "").strip(),
            "subject": str(subject or "").strip(),
        }
    )


def summarize_diagnostic_panel(root_dir: Path, recent: int, history_data: dict[str, Any]) -> ObservationItem:
    problem_tasks = list(history_data.get("problem_tasks", []) or [])
    top_blockers = list(history_data.get("top_blockers", []) or [])
    slow_scenarios = list(history_data.get("slow_scenarios", []) or [])
    consecutive_problems = list(history_data.get("consecutive_problems", []) or [])
    frequent_blockers = list(history_data.get("frequent_blockers", []) or [])
    slow_regressions = list(history_data.get("slow_regressions", []) or [])
    latest_items = list(history_data.get("latest", []) or [])
    warning_kinds = list(history_data.get("warning_kinds", []) or [])
    problem_kinds = list(history_data.get("problem_kinds", []) or [])

    top_task = problem_tasks[0] if problem_tasks else {}
    top_blocker = top_blockers[0] if top_blockers else {}
    top_slow = slow_scenarios[0] if slow_scenarios else {}
    top_problem_streak = consecutive_problems[0] if consecutive_problems else {}
    top_repeat_blocker = frequent_blockers[0] if frequent_blockers else {}
    top_regression = slow_regressions[0] if slow_regressions else {}

    recommendations: list[dict[str, Any]] = []

    top_task_name = str(top_task.get("subject") or "").strip()
    if top_task_name:
        harness_runs = agent_history.list_history_runs("harness", root_dir=root_dir, limit=max(3, recent * 4))
        resume_commands: list[str] = []
        for record in harness_runs:
            if str(record.get("subject") or "").strip() != top_task_name:
                continue
            resume_commands = _extract_resume_commands(record)
            if resume_commands:
                break
        if resume_commands:
            for command in resume_commands[:2]:
                _append_unique_command(
                    recommendations,
                    reason="复跑最近最常告警 task",
                    command=command,
                    source="handoff",
                    subject=top_task_name,
                )
        else:
            _append_unique_command(
                recommendations,
                reason="复跑最近最常告警 task",
                command=_build_default_task_command(top_task_name),
                source="heuristic",
                subject=top_task_name,
            )

    blocker_text = str(top_blocker.get("text") or "").strip()
    if blocker_text:
        matched_resume: list[str] = []
        for kind in ("harness", "evaluator", "ci-agent-smoke", "ci-guardrails", "ci-browser-smoke"):
            runs = agent_history.list_history_runs(kind, root_dir=root_dir, limit=max(3, recent * 4))
            for record in runs:
                handoff = _load_run_handoff(record)
                blockers = [str(item).strip() for item in list(handoff.get("blockers", []) or []) if str(item).strip()]
                if blocker_text not in blockers:
                    continue
                matched_resume = _extract_resume_commands(record)
                if matched_resume:
                    break
            if matched_resume:
                break
        if matched_resume:
            for command in matched_resume[:2]:
                _append_unique_command(
                    recommendations,
                    reason="定位 Top blocker",
                    command=command,
                    source="handoff",
                    subject=blocker_text,
                )
        else:
            _append_unique_command(
                recommendations,
                reason="定位 Top blocker",
                command=_infer_blocker_command(blocker_text, top_task_name),
                source="heuristic",
                subject=blocker_text,
            )

    slow_name = str(top_slow.get("name") or "").strip()
    if slow_name:
        eval_runs = agent_history.list_history_runs("evaluator", root_dir=root_dir, limit=max(3, recent * 4))
        resume_commands = []
        for record in eval_runs:
            summary_payload = _load_run_summary(record)
            result_names = {
                str(item.get("name") or "").strip()
                for item in list(summary_payload.get("results", []) or [])
                if isinstance(item, dict)
            }
            if slow_name not in result_names and slow_name not in {str(item.get("name") or "").strip() for item in _extract_slow_scenario_entries(summary_payload)}:
                continue
            resume_commands = _extract_resume_commands(record)
            if resume_commands:
                break
        if resume_commands:
            for command in resume_commands[:2]:
                _append_unique_command(
                    recommendations,
                    reason="复跑最近最慢场景",
                    command=command,
                    source="handoff",
                    subject=slow_name,
                )
        else:
            _append_unique_command(
                recommendations,
                reason="复跑最近最慢场景",
                command=_build_default_scenario_command(slow_name),
                source="heuristic",
                subject=slow_name,
            )

    streak_kind = str(top_problem_streak.get("kind") or "").strip()
    streak_subject = str(top_problem_streak.get("subject") or "").strip()
    if streak_kind:
        streak_runs = agent_history.list_history_runs(streak_kind, root_dir=root_dir, limit=max(3, recent * 4))
        streak_resume: list[str] = []
        for record in streak_runs:
            if str(record.get("subject") or "").strip() != streak_subject:
                if streak_subject:
                    continue
            streak_resume = _extract_resume_commands(record)
            if streak_resume:
                break
        if streak_resume:
            for command in streak_resume[:2]:
                _append_unique_command(
                    recommendations,
                    reason="连续失败链路复跑",
                    command=command,
                    source="handoff",
                    subject=f"{streak_kind}:{streak_subject or 'latest'}",
                )
        elif streak_kind == "evaluator":
            _append_unique_command(
                recommendations,
                reason="连续失败链路复跑",
                command="python3 scripts/agent_eval.py --tag nightly --artifact-dir artifacts/harness-eval",
                source="heuristic",
                subject=streak_kind,
            )
        elif streak_kind == "ci-browser-smoke":
            _append_unique_command(
                recommendations,
                reason="连续失败链路复跑",
                command="python3 scripts/agent_browser_smoke.py --suite extended",
                source="heuristic",
                subject=streak_kind,
            )
        elif streak_subject:
            _append_unique_command(
                recommendations,
                reason="连续失败链路复跑",
                command=_build_default_task_command(streak_subject),
                source="heuristic",
                subject=streak_subject,
            )

    repeated_blocker_text = str(top_repeat_blocker.get("text") or "").strip()
    if repeated_blocker_text:
        _append_unique_command(
            recommendations,
            reason="重复 blocker 复盘",
            command=_infer_blocker_command(repeated_blocker_text, top_task_name),
            source="heuristic",
            subject=repeated_blocker_text,
        )

    regression_name = str(top_regression.get("name") or "").strip()
    if regression_name:
        _append_unique_command(
            recommendations,
            reason="慢场景回归复跑",
            command=_build_default_scenario_command(regression_name),
            source="heuristic",
            subject=regression_name,
        )

    for item in latest_items:
        kind = str(item.get("kind") or "").strip()
        bucket = str(item.get("bucket") or "").strip()
        if bucket != "problem":
            continue
        if kind == "ci-browser-smoke":
            _append_unique_command(
                recommendations,
                reason="CI browser smoke 最近失败",
                command="python3 scripts/agent_harness.py --browser-smoke --browser-smoke-suite extended --skip-doctor --skip-static-guardrails --skip-guardrails --skip-smoke --artifact-dir artifacts/ci/browser-smoke",
                source="heuristic",
                subject=kind,
            )
        elif kind == "ci-agent-smoke":
            _append_unique_command(
                recommendations,
                reason="CI agent smoke 最近失败",
                command="python3 scripts/agent_harness.py --skip-doctor --skip-guardrails --smoke-suite minimal --artifact-dir artifacts/ci/agent-smoke",
                source="heuristic",
                subject=kind,
            )
        elif kind == "ci-guardrails":
            _append_unique_command(
                recommendations,
                reason="CI guardrails 最近失败",
                command="python3 scripts/agent_harness.py --skip-doctor --skip-smoke --guardrails-suite minimal --artifact-dir artifacts/ci/guardrails",
                source="heuristic",
                subject=kind,
            )

    top_task_name = top_task_name or "none"
    short_blocker = _shorten_text(blocker_text, limit=36) if blocker_text else "none"
    top_slow_name = slow_name or "none"
    streak_hint = f"{streak_kind}:{int(top_problem_streak.get('streak', 0) or 0)}" if streak_kind else "none"
    blocker_repeat_hint = (
        f"{_shorten_text(repeated_blocker_text, limit=24)}x{int(top_repeat_blocker.get('count', 0) or 0)}"
        if repeated_blocker_text
        else "none"
    )
    regression_hint = regression_name or "none"
    replay_hint = _shorten_text(recommendations[0]["command"], limit=68) if recommendations else "none"
    detail = (
        f"task={top_task_name} blocker={short_blocker} slow={top_slow_name} "
        f"problem_kinds={len(problem_kinds)} warning_kinds={len(warning_kinds)} "
        f"streak={streak_hint} blocker_repeat={blocker_repeat_hint} regression={regression_hint} "
        f"replay={replay_hint}"
    )

    severe_alert = (
        int(top_problem_streak.get("streak", 0) or 0) >= CONSECUTIVE_PROBLEM_FAIL_THRESHOLD
        or bool(top_regression.get("budget_exceeded", False))
        or float(top_regression.get("delta_ms", 0) or 0) >= SLOW_REGRESSION_DELTA_FAIL_MS
    )
    status = "FAIL" if severe_alert else (
        "WARN"
        if (
            problem_tasks
            or top_blockers
            or slow_scenarios
            or recommendations
            or problem_kinds
            or warning_kinds
            or consecutive_problems
            or frequent_blockers
            or slow_regressions
        )
        else "PASS"
    )
    return ObservationItem(
        name="diagnostic_panel",
        status=status,
        detail=detail,
        data={
            "top_problem_task": top_task,
            "top_blocker": top_blocker,
            "top_slow_scenario": top_slow,
            "problem_kinds": problem_kinds,
            "warning_kinds": warning_kinds,
            "top_consecutive_problem": top_problem_streak,
            "top_frequent_blocker": top_repeat_blocker,
            "top_slow_regression": top_regression,
            "consecutive_problems": consecutive_problems,
            "frequent_blockers": frequent_blockers,
            "slow_regressions": slow_regressions,
            "alert_thresholds": {
                "consecutive_problem_warn": CONSECUTIVE_PROBLEM_ALERT_THRESHOLD,
                "consecutive_problem_fail": CONSECUTIVE_PROBLEM_FAIL_THRESHOLD,
                "frequent_blocker_warn": FREQUENT_BLOCKER_ALERT_THRESHOLD,
                "slow_regression_delta_warn_ms": SLOW_REGRESSION_DELTA_ALERT_MS,
                "slow_regression_delta_fail_ms": SLOW_REGRESSION_DELTA_FAIL_MS,
                "slow_regression_ratio_warn": SLOW_REGRESSION_RATIO_ALERT,
            },
            "recommended_commands": recommendations[:6],
        },
    )


def summarize_history_trends(root_dir: Path, recent: int) -> ObservationItem:
    index_payload = agent_history.build_history_index(kind="all", root_dir=root_dir, limit=recent)
    latest_items: list[dict[str, Any]] = []
    problem_kinds: list[str] = []
    warning_kinds: list[str] = []

    for kind, collection in (index_payload.get("collections", {}) or {}).items():
        if not isinstance(collection, dict):
            continue
        latest = collection.get("latest")
        if not isinstance(latest, dict):
            continue
        overall = str(latest.get("overall") or "").strip()
        bucket = _history_health_bucket(overall)
        latest_items.append(
            {
                "kind": kind,
                "overall": overall,
                "subject": str(latest.get("subject") or "").strip(),
                "generated_at": str(latest.get("generated_at") or "").strip(),
                "run_name": str(latest.get("run_name") or "").strip(),
                "bucket": bucket,
            }
        )
        if bucket == "problem":
            problem_kinds.append(kind)
        elif bucket == "warning":
            warning_kinds.append(kind)

    diff_targets = HISTORY_SIGNAL_KINDS
    diff_payloads: dict[str, dict[str, Any]] = {
        kind: agent_history.build_history_diff(kind=kind, root_dir=root_dir) for kind in diff_targets
    }
    drift_items: list[dict[str, Any]] = []
    for kind in diff_targets:
        payload = diff_payloads[kind]
        for item in list(payload.get("changed_results", []) or [])[:3]:
            if not isinstance(item, dict):
                continue
            drift_items.append(
                {
                    "kind": kind,
                    "name": str(item.get("name") or "").strip(),
                    "before": str(item.get("before") or "").strip(),
                    "after": str(item.get("after") or "").strip(),
                }
            )
    drift_items = drift_items[:6]

    problem_tasks = _aggregate_problem_tasks(root_dir, recent)
    top_blockers = _aggregate_top_blockers(root_dir, recent)
    slow_scenarios = _aggregate_slow_scenarios(root_dir, recent)
    consecutive_problems = _aggregate_consecutive_problem_runs(root_dir, recent)
    frequent_blockers = _aggregate_frequent_blockers(top_blockers)
    slow_regressions = _aggregate_slow_regressions(root_dir, recent)

    top_task = problem_tasks[0]["subject"] if problem_tasks else "none"
    top_blocker = _shorten_text(top_blockers[0]["text"], limit=36) if top_blockers else "none"
    top_slow = slow_scenarios[0]["name"] if slow_scenarios else "none"
    top_streak = (
        f"{consecutive_problems[0]['kind']}:{int(consecutive_problems[0]['streak'] or 0)}"
        if consecutive_problems
        else "none"
    )
    top_repeat = (
        f"{_shorten_text(frequent_blockers[0]['text'], limit=24)}x{int(frequent_blockers[0]['count'] or 0)}"
        if frequent_blockers
        else "none"
    )
    top_regression = slow_regressions[0]["name"] if slow_regressions else "none"

    detail = (
        f"latest={len(latest_items)} problem={len(problem_kinds)} warning={len(warning_kinds)} "
        f"harness_diff={str(diff_payloads['harness'].get('overall') or '').strip() or 'EMPTY'} "
        f"evaluator_diff={str(diff_payloads['evaluator'].get('overall') or '').strip() or 'EMPTY'} "
        f"task={top_task} blocker={top_blocker} slow={top_slow} "
        f"streak={top_streak} blocker_repeat={top_repeat} regression={top_regression}"
    )
    if latest_items:
        status = "WARN" if problem_kinds or warning_kinds else "PASS"
    else:
        status = "WARN"
    return ObservationItem(
        name="history_trends",
        status=status,
        detail=detail,
        data={
            "latest": latest_items,
            "problem_kinds": problem_kinds,
            "warning_kinds": warning_kinds,
            "drift_items": drift_items,
            "diffs": diff_payloads,
            "problem_tasks": problem_tasks,
            "top_blockers": top_blockers,
            "slow_scenarios": slow_scenarios,
            "consecutive_problems": consecutive_problems,
            "frequent_blockers": frequent_blockers,
            "slow_regressions": slow_regressions,
        },
    )


def _normalize_startup_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    phases: list[dict[str, Any]] = []
    for item in payload.get("phases", []) if isinstance(payload.get("phases", []), list) else []:
        if not isinstance(item, dict):
            continue
        phases.append(
            {
                "name": str(item.get("name") or "").strip(),
                "elapsed_ms": round(float(item.get("elapsed_ms", 0) or 0), 2),
            }
        )
    return {
        "initialized": bool(payload.get("initialized", False)),
        "reason": str(payload.get("reason") or "").strip(),
        "started_at": format_dt(payload.get("started_at")),
        "completed_at": format_dt(payload.get("completed_at")),
        "total_ms": round(float(payload.get("total_ms", 0) or 0), 2),
        "phases": phases,
        "failed_phase": str(payload.get("failed_phase") or "").strip(),
        "error": str(payload.get("error") or "").strip(),
    }


def _load_runtime_startup_payload(meta_index_db: Path | None, startup_file: Path) -> tuple[dict[str, Any], str]:
    if meta_index_db and meta_index_db.exists():
        with closing(open_sqlite_readonly(meta_index_db)) as conn:
            if sqlite_table_exists(conn, "runtime_metrics_store"):
                row = conn.execute(
                    "SELECT payload_json FROM runtime_metrics_store WHERE metric_key = 'runtime_startup' LIMIT 1"
                ).fetchone()
                if row and row["payload_json"]:
                    try:
                        return _normalize_startup_payload(json.loads(str(row["payload_json"]))), "runtime_metrics_store"
                    except Exception:
                        pass
    if startup_file.exists():
        try:
            return _normalize_startup_payload(json.loads(startup_file.read_text(encoding="utf-8"))), "operations/runtime-startup"
        except Exception:
            pass
    return {}, ""


def summarize_startup_snapshot(root_dir: Path, meta_index_db: Path | None) -> ObservationItem:
    payload, source = _load_runtime_startup_payload(meta_index_db, root_dir / "data" / "operations" / "runtime-startup" / "latest.json")
    if not source:
        detail = "source=none startup snapshot 缺失，服务最近可能尚未完成启动初始化。"
        return ObservationItem(
            name="startup_snapshot",
            status="WARN",
            detail=detail,
            data={
                "source": "",
                "initialized": False,
                "status": "missing",
                "note": "agent_observe 不会主动触发初始化；可通过启动服务或预启动脚本生成最新快照。",
            },
        )

    initialized = bool(payload.get("initialized", False))
    status = "PASS" if initialized else "FAIL"
    detail = (
        f"source={source} initialized={'yes' if initialized else 'no'} "
        f"total_ms={float(payload.get('total_ms', 0) or 0):.2f} "
        f"completed_at={str(payload.get('completed_at') or '').strip() or '-'}"
    )
    return ObservationItem(
        name="startup_snapshot",
        status=status,
        detail=detail,
        data={
            "source": source,
            "initialized": initialized,
            "status": "ready" if initialized else "failed",
            "reason": str(payload.get("reason") or "").strip(),
            "started_at": str(payload.get("started_at") or "").strip(),
            "completed_at": str(payload.get("completed_at") or "").strip(),
            "total_ms": float(payload.get("total_ms", 0) or 0),
            "phases": payload.get("phases", []),
            "failed_phase": str(payload.get("failed_phase") or "").strip(),
            "error": str(payload.get("error") or "").strip(),
        },
    )


def build_summary(items: list[ObservationItem]) -> dict[str, int]:
    summary = {"PASS": 0, "WARN": 0, "FAIL": 0}
    for item in items:
        summary[item.status] = summary.get(item.status, 0) + 1
    return summary


def determine_overall(summary: dict[str, int]) -> str:
    if summary.get("FAIL", 0) > 0:
        return "BLOCKED"
    if summary.get("WARN", 0) > 0:
        return "DEGRADED"
    return "HEALTHY"


def render_text(payload: dict[str, Any]) -> None:
    print("DeepVision agent observe")
    print(f"仓库目录: {payload['root_dir']}")
    print("")
    for item in payload["items"]:
        print(f"[{item['status']}] {item['name']}: {item['detail']}")
        recommendations = list(((item.get("data") or {}).get("recommended_commands", []) or [])) if isinstance(item, dict) else []
        for entry in recommendations[:3]:
            command = str(entry.get("command") or "").strip()
            reason = str(entry.get("reason") or "").strip()
            if command:
                print(f"        - {reason}: {command}")
    print("")
    print(
        "Summary: "
        f"PASS={payload['summary']['PASS']} "
        f"WARN={payload['summary']['WARN']} "
        f"FAIL={payload['summary']['FAIL']}"
    )
    print(f"Overall: {payload['overall']}")


def run_observe(
    *,
    profile: str = "auto",
    env_file: str = "",
    recent: int = 5,
    root_dir: Path = ROOT_DIR,
) -> tuple[dict[str, Any], int]:
    selected_env_file, env_source = resolve_selected_env_file(root_dir=root_dir, profile=profile, explicit_env_file=env_file)
    file_values = parse_env_file(selected_env_file) if selected_env_file and selected_env_file.exists() else {}
    env_item = summarize_env(root_dir, profile, selected_env_file, env_source)
    db_health_item = summarize_db_health(root_dir, file_values)
    meta_index_db_raw = (((db_health_item.data or {}).get("meta_index_db") or {}).get("path") or "")
    meta_index_db = Path(meta_index_db_raw) if meta_index_db_raw else None
    items = [
        env_item,
        summarize_startup_snapshot(root_dir, meta_index_db),
        db_health_item,
        summarize_metrics(root_dir, meta_index_db, recent),
        summarize_summaries(root_dir, meta_index_db),
        summarize_config_sources(root_dir, str(selected_env_file) if selected_env_file else "", env_source, file_values),
        summarize_ownership_history(root_dir, recent),
        summarize_cloud_import_backups(root_dir, recent),
        summarize_recent_operations(root_dir, recent),
        summarize_harness_runs(root_dir, recent),
    ]
    history_item = summarize_history_trends(root_dir, recent)
    diagnostic_item = summarize_diagnostic_panel(root_dir, recent, history_item.data or {})
    items.extend(
        [
            history_item,
            diagnostic_item,
        ]
    )
    summary = build_summary(items)
    overall = determine_overall(summary)
    payload = {
        "generated_at": utc_now_iso(),
        "root_dir": str(root_dir),
        "profile": profile,
        "recent": recent,
        "items": [asdict(item) for item in items],
        "summary": summary,
        "overall": overall,
    }
    return payload, 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DeepVision agent 运行态观察入口")
    parser.add_argument("--profile", default="auto", choices=["auto", "local", "cloud", "production"], help="观察时使用的环境场景")
    parser.add_argument("--env-file", default="", help="显式指定环境文件")
    parser.add_argument("--recent", type=int, default=5, help="每类最近记录展示条数")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload, exit_code = run_observe(
        profile=args.profile,
        env_file=args.env_file,
        recent=max(1, int(args.recent or 5)),
    )
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        render_text(payload)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
