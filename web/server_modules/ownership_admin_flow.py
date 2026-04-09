import json
import secrets
import time as _time
from pathlib import Path
from typing import Any, Callable, Optional


class AdminOwnershipMigrationService:
    def __init__(
        self,
        *,
        ownership_service: Any,
        get_auth_db_path: Callable[[], str],
        get_license_db_path: Callable[[], str],
        get_sessions_dir: Callable[[], Path],
        get_reports_dir: Callable[[], Path],
        get_report_owners_file: Callable[[], Path],
        get_report_solution_shares_file: Callable[[], Path],
        get_custom_scenarios_dir: Callable[[], Path],
        get_meta_index_db_target: Callable[[], Optional[str]],
        get_backup_root: Callable[[], Path],
        session_store_getter: Callable[[], Any],
        preview_session_key: str,
        preview_ttl_seconds: int,
        is_object_storage_enabled: Callable[[], bool],
        list_archived_ownership_migrations: Callable[..., list[dict]],
        materialize_ownership_backup_from_object_storage: Callable[[str], Path],
        sync_ops_archive_directory_to_object_storage: Callable[[Path], int],
        sync_materialized_ownership_backup_to_object_storage: Callable[[Path, str], int],
        refresh_runtime_state: Callable[[], None],
        debug_enabled: bool,
        debug_log: Callable[[str], None],
    ) -> None:
        self._ownership_service = ownership_service
        self._get_auth_db_path = get_auth_db_path
        self._get_license_db_path = get_license_db_path
        self._get_sessions_dir = get_sessions_dir
        self._get_reports_dir = get_reports_dir
        self._get_report_owners_file = get_report_owners_file
        self._get_report_solution_shares_file = get_report_solution_shares_file
        self._get_custom_scenarios_dir = get_custom_scenarios_dir
        self._get_meta_index_db_target = get_meta_index_db_target
        self._get_backup_root = get_backup_root
        self._session_store_getter = session_store_getter
        self._preview_session_key = str(preview_session_key or "").strip()
        self._preview_ttl_seconds = max(1, int(preview_ttl_seconds or 1))
        self._is_object_storage_enabled = is_object_storage_enabled
        self._list_archived_ownership_migrations = list_archived_ownership_migrations
        self._materialize_ownership_backup_from_object_storage = (
            materialize_ownership_backup_from_object_storage
        )
        self._sync_ops_archive_directory_to_object_storage = (
            sync_ops_archive_directory_to_object_storage
        )
        self._sync_materialized_ownership_backup_to_object_storage = (
            sync_materialized_ownership_backup_to_object_storage
        )
        self._refresh_runtime_state = refresh_runtime_state
        self._debug_enabled = bool(debug_enabled)
        self._debug_log = debug_log

    @staticmethod
    def _mark_session_modified(session_store: Any) -> None:
        try:
            session_store.modified = True
        except Exception:
            pass

    def _get_session_store(self) -> Any:
        return self._session_store_getter()

    def build_request_payload(self, data: Optional[dict]) -> dict:
        payload = data if isinstance(data, dict) else {}
        kinds = self._ownership_service.parse_kinds(payload.get("kinds") or "sessions,reports")
        return {
            "to_user_id": int(payload["to_user_id"]) if payload.get("to_user_id") not in (None, "") else None,
            "to_account": str(payload.get("to_account") or "").strip(),
            "scope": str(payload.get("scope") or "unowned").strip(),
            "from_user_id": int(payload["from_user_id"]) if payload.get("from_user_id") not in (None, "") else None,
            "kinds": sorted(list(kinds)),
            "max_examples": max(1, min(int(payload.get("max_examples") or 20), 50)),
        }

    @staticmethod
    def serialize_request_payload(payload: dict) -> str:
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)

    def store_preview(self, payload: dict) -> dict:
        session_store = self._get_session_store()
        token = secrets.token_urlsafe(18)
        target_label = str(payload.get("to_account") or payload.get("to_user_id") or "").strip() or "目标用户"
        confirm_phrase = f"确认迁移到 {target_label}"
        session_store[self._preview_session_key] = {
            "token": token,
            "issued_at": int(_time.time()),
            "payload": payload,
            "confirm_phrase": confirm_phrase,
        }
        self._mark_session_modified(session_store)
        return {
            "preview_token": token,
            "confirm_phrase": confirm_phrase,
            "expires_in_seconds": self._preview_ttl_seconds,
        }

    def pop_preview(self) -> Optional[dict]:
        session_store = self._get_session_store()
        preview = session_store.pop(self._preview_session_key, None)
        self._mark_session_modified(session_store)
        return preview if isinstance(preview, dict) else None

    def get_preview(self) -> Optional[dict]:
        session_store = self._get_session_store()
        preview = session_store.get(self._preview_session_key)
        if not isinstance(preview, dict):
            return None
        issued_at = int(preview.get("issued_at") or 0)
        if issued_at <= 0 or (int(_time.time()) - issued_at) > self._preview_ttl_seconds:
            session_store.pop(self._preview_session_key, None)
            self._mark_session_modified(session_store)
            return None
        return preview

    def audit_ownership(
        self,
        *,
        user_id: Optional[int],
        user_account: str,
        kinds: Any,
    ) -> dict:
        return self._ownership_service.audit_ownership(
            auth_db_path=self._get_auth_db_path(),
            sessions_dir=self._get_sessions_dir(),
            reports_dir=self._get_reports_dir(),
            report_owners_file=self._get_report_owners_file(),
            meta_index_db_path=self._get_meta_index_db_target(),
            user_id=int(user_id) if user_id is not None else None,
            user_account=str(user_account or "").strip(),
            kinds=kinds or "sessions,reports",
        )

    def finalize_apply(self, summary: Optional[dict]) -> dict:
        backup_dir = str((summary or {}).get("backup_dir") or "").strip()
        if backup_dir and self._is_object_storage_enabled():
            try:
                self._sync_ops_archive_directory_to_object_storage(Path(backup_dir))
            except Exception as exc:
                if self._debug_enabled:
                    self._debug_log(
                        f"⚠️ ownership migration 备份归档失败: backup_dir={backup_dir}, error={exc}"
                    )
        self.pop_preview()
        self._refresh_runtime_state()
        return {"success": True, "summary": summary}

    def list_migrations(self, *, limit: int = 50) -> dict:
        normalized_limit = max(1, int(limit or 50))
        local_items = self._ownership_service.list_ownership_migrations(
            self._get_backup_root(),
            limit=normalized_limit,
        )
        items_by_backup_id = {
            str(item.get("backup_id") or "").strip(): item
            for item in local_items
            if str(item.get("backup_id") or "").strip()
        }
        if self._is_object_storage_enabled():
            try:
                archived_items = self._list_archived_ownership_migrations(limit=normalized_limit)
                for item in archived_items:
                    backup_id = str(item.get("backup_id") or "").strip()
                    if backup_id and backup_id not in items_by_backup_id:
                        items_by_backup_id[backup_id] = item
            except Exception as exc:
                if self._debug_enabled:
                    self._debug_log(f"⚠️ 读取对象存储 ownership migration 历史失败: {exc}")
        items = list(items_by_backup_id.values())
        items.sort(
            key=lambda item: (
                str(item.get("generated_at") or ""),
                str(item.get("backup_id") or ""),
            ),
            reverse=True,
        )
        items = items[:normalized_limit]
        return {"items": items, "count": len(items)}

    def rollback_migration(self, backup_id: str) -> dict:
        normalized_backup_id = str(backup_id or "").strip()
        if not normalized_backup_id:
            raise ValueError("backup_id 不能为空")

        rollback_backup_dir = None
        local_backup_dir = (self._get_backup_root() / normalized_backup_id).resolve()
        if local_backup_dir.exists() and local_backup_dir.is_dir():
            rollback_backup_dir = local_backup_dir
        elif self._is_object_storage_enabled():
            rollback_backup_dir = self._materialize_ownership_backup_from_object_storage(
                normalized_backup_id
            )

        payload = self._ownership_service.rollback_ownership_migration(
            backup_root=self._get_backup_root(),
            sessions_dir=self._get_sessions_dir(),
            reports_dir=self._get_reports_dir(),
            report_owners_file=self._get_report_owners_file(),
            auth_db_path=self._get_auth_db_path(),
            license_db_path=self._get_license_db_path(),
            meta_index_db_path=self._get_meta_index_db_target(),
            custom_scenarios_dir=self._get_custom_scenarios_dir(),
            report_solution_shares_file=self._get_report_solution_shares_file(),
            backup_id=None if rollback_backup_dir is not None else normalized_backup_id,
            backup_dir=rollback_backup_dir,
        )

        if rollback_backup_dir is not None and self._is_object_storage_enabled():
            try:
                if rollback_backup_dir == local_backup_dir:
                    self._sync_ops_archive_directory_to_object_storage(rollback_backup_dir)
                else:
                    self._sync_materialized_ownership_backup_to_object_storage(
                        rollback_backup_dir,
                        normalized_backup_id,
                    )
            except Exception as exc:
                if self._debug_enabled:
                    self._debug_log(
                        "⚠️ ownership migration 回滚结果归档失败: "
                        f"backup_id={normalized_backup_id}, error={exc}"
                    )
        self._refresh_runtime_state()
        return {"success": True, **payload}
