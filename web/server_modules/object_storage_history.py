import hashlib
import json
import os
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional


class ObjectStorageHistoryService:
    def __init__(
        self,
        *,
        is_object_storage_enabled: Callable[[], bool],
        ensure_object_storage_sdk_available: Callable[[], tuple[bool, str]],
        debug_enabled: bool,
        debug_print: Callable[[str], None],
        debug_log: Callable[[str], None],
        presentation_map_lock: threading.Lock,
        named_file_lock: Callable[..., Any],
        load_presentation_map: Callable[[], dict],
        save_presentation_map: Callable[[dict], None],
        upload_file_to_object_storage: Callable[..., dict],
        build_object_storage_key: Callable[..., str],
        guess_content_type: Callable[[str], str],
        get_active_instance_scope_key: Callable[[], str],
        normalize_object_storage_segment: Callable[..., str],
        object_storage_prefix: str,
        object_storage_key_exists: Callable[[str], bool],
        compute_file_sha256: Callable[[Path], str],
        get_meta_index_connection: Callable[[], Any],
        data_dir: Path,
        get_restore_backups_root: Callable[[], Path],
        get_session_backups_root: Callable[[], Path],
        temp_dir: Path,
        download_object_storage_bytes: Callable[[str], tuple[bytes, dict]],
    ) -> None:
        self._is_object_storage_enabled = is_object_storage_enabled
        self._ensure_object_storage_sdk_available = ensure_object_storage_sdk_available
        self._debug_enabled = bool(debug_enabled)
        self._debug_print = debug_print
        self._debug_log = debug_log
        self._presentation_map_lock = presentation_map_lock
        self._named_file_lock = named_file_lock
        self._load_presentation_map = load_presentation_map
        self._save_presentation_map = save_presentation_map
        self._upload_file_to_object_storage = upload_file_to_object_storage
        self._build_object_storage_key = build_object_storage_key
        self._guess_content_type = guess_content_type
        self._get_active_instance_scope_key = get_active_instance_scope_key
        self._normalize_object_storage_segment = normalize_object_storage_segment
        self._object_storage_prefix = object_storage_prefix
        self._object_storage_key_exists = object_storage_key_exists
        self._compute_file_sha256 = compute_file_sha256
        self._get_meta_index_connection = get_meta_index_connection
        self._data_dir = Path(data_dir).resolve()
        self._get_restore_backups_root = get_restore_backups_root
        self._get_session_backups_root = get_session_backups_root
        self._temp_dir = Path(temp_dir).resolve()
        self._download_object_storage_bytes = download_object_storage_bytes
        self._presentation_migration_lock = threading.Lock()
        self._presentation_migrated = False
        self._ops_archive_lock = threading.Lock()
        self._ops_archive_migrated = False

    def migrate_presentation_assets_to_object_storage_if_needed(self, *, force: bool = False) -> dict:
        summary = {
            "enabled": bool(self._is_object_storage_enabled()),
            "scanned": 0,
            "uploaded": 0,
            "already_migrated": bool(self._presentation_migrated),
        }
        if not self._is_object_storage_enabled():
            return summary
        if self._presentation_migrated and not force:
            return summary
        available, error_message = self._ensure_object_storage_sdk_available()
        if not available:
            summary["error"] = error_message or "当前环境未安装 boto3，请先安装 boto3"
            if self._debug_enabled:
                self._debug_print(f"⚠️ 演示文件迁移到对象存储已跳过: {error_message}")
            return summary
        with self._presentation_migration_lock:
            if self._presentation_migrated and not force:
                summary["already_migrated"] = True
                return summary
            try:
                with self._presentation_map_lock:
                    with self._named_file_lock("sidecar", "presentation_map"):
                        data = self._load_presentation_map()
                        mutated = False
                        for report_name, record in list(data.items()):
                            if not isinstance(record, dict):
                                continue
                            if record.get("object_key"):
                                continue
                            summary["scanned"] += 1
                            path_str = str(record.get("path") or "").strip()
                            if not path_str:
                                continue
                            file_path = Path(path_str)
                            if not file_path.exists() or not file_path.is_file():
                                continue
                            uploaded = self._upload_file_to_object_storage(
                                file_path,
                                object_key=self._build_object_storage_key(
                                    "presentations",
                                    Path(report_name).stem,
                                    filename=file_path.name,
                                ),
                                content_type=str(record.get("content_type") or self._guess_content_type(file_path.name)),
                                metadata={
                                    "report_name": report_name,
                                    "instance_scope_key": self._get_active_instance_scope_key(),
                                },
                            )
                            record["object_key"] = uploaded["object_key"]
                            record["bucket"] = uploaded["bucket"]
                            record["storage_backend"] = uploaded["storage_backend"]
                            record["content_type"] = uploaded["content_type"]
                            record["size"] = uploaded["size"]
                            record["filename"] = str(record.get("filename") or file_path.name)
                            mutated = True
                            summary["uploaded"] += 1
                        if mutated:
                            self._save_presentation_map(data)
            except Exception as exc:
                summary["error"] = str(exc)
                if self._debug_enabled:
                    self._debug_print(f"⚠️ 演示文件迁移到对象存储失败: {exc}")
                return summary
            self._presentation_migrated = True
            summary["already_migrated"] = True
            return summary

    def _normalize_ops_archive_relative_path(self, file_path: Path) -> str:
        target = Path(file_path).expanduser().resolve()
        relative = target.relative_to(self._data_dir.resolve())
        return str(relative).replace("\\", "/")

    def _classify_ops_archive_relative_path(self, relative_path: str) -> tuple[str, str]:
        normalized = str(relative_path or "").strip().replace("\\", "/")
        path_obj = Path(normalized)
        parts = path_obj.parts
        if len(parts) >= 3 and parts[0] == "operations" and parts[1] == "ownership-migrations":
            return "ownership_migration", str(parts[2]).strip()
        if len(parts) >= 2 and parts[0] == "restore_backups":
            return "restore_backup", str(parts[1]).strip()
        if len(parts) >= 2 and parts[0] == "session_backups":
            return "session_backup", str(parts[1]).strip()
        if parts and parts[0] == "operations":
            return "operations", ""
        return "", ""

    def build_ops_archive_object_key(self, relative_path: str) -> str:
        normalized = str(relative_path or "").strip().replace("\\", "/")
        path_obj = Path(normalized)
        scope_key = self._normalize_object_storage_segment(self._get_active_instance_scope_key(), fallback="default")
        prefix = self._normalize_object_storage_segment(self._object_storage_prefix, fallback="deepvision")
        parts = [prefix, scope_key, "ops-archives"]
        for segment in path_obj.parts:
            normalized_segment = self._normalize_object_storage_segment(segment, fallback="")
            if normalized_segment:
                parts.append(normalized_segment)
        return "/".join(parts)

    @staticmethod
    def _build_ops_archive_record_payload(row: Any) -> Optional[dict]:
        if not row:
            return None
        row_keys = row.keys()
        return {
            "archive_id": str(row["archive_id"] or "").strip(),
            "archive_group": str(row["archive_group"] or "").strip(),
            "backup_id": str(row["backup_id"] or "").strip(),
            "relative_path": str(row["relative_path"] or "").strip(),
            "object_key": str(row["object_key"] or "").strip(),
            "content_type": str(row["content_type"] or "application/octet-stream"),
            "file_sha256": str(row["file_sha256"] or "").strip(),
            "size": int(row["size"] if "size" in row_keys and row["size"] is not None else 0),
            "created_at": str(row["created_at"] or "").strip(),
            "updated_at": str(row["updated_at"] or "").strip(),
        }

    def _load_ops_archive_record_by_relative_path(self, conn: Any, relative_path: str) -> Optional[dict]:
        row = conn.execute(
            """
            SELECT archive_id, archive_group, backup_id, relative_path, object_key,
                   content_type, file_sha256, size, created_at, updated_at
            FROM ops_archive_store
            WHERE relative_path = ?
            LIMIT 1
            """,
            (str(relative_path or "").strip(),),
        ).fetchone()
        return self._build_ops_archive_record_payload(row)

    def _upsert_ops_archive_record(
        self,
        conn: Any,
        *,
        archive_group: str,
        backup_id: str,
        relative_path: str,
        object_key: str,
        content_type: str,
        file_sha256: str,
        size: int,
        created_at: str,
        updated_at: str,
    ) -> dict:
        normalized_relative_path = str(relative_path or "").strip().replace("\\", "/")
        archive_id = hashlib.sha1(normalized_relative_path.encode("utf-8")).hexdigest()
        conn.execute(
            """
            INSERT INTO ops_archive_store(
                archive_id, archive_group, backup_id, relative_path, object_key,
                content_type, file_sha256, size, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(relative_path) DO UPDATE SET
                archive_group = excluded.archive_group,
                backup_id = excluded.backup_id,
                object_key = excluded.object_key,
                content_type = excluded.content_type,
                file_sha256 = excluded.file_sha256,
                size = excluded.size,
                created_at = excluded.created_at,
                updated_at = excluded.updated_at
            """,
            (
                archive_id,
                str(archive_group or "").strip(),
                str(backup_id or "").strip(),
                normalized_relative_path,
                str(object_key or "").strip(),
                str(content_type or "application/octet-stream"),
                str(file_sha256 or "").strip(),
                int(size or 0),
                str(created_at or "").strip(),
                str(updated_at or "").strip(),
            ),
        )
        return {
            "archive_id": archive_id,
            "archive_group": str(archive_group or "").strip(),
            "backup_id": str(backup_id or "").strip(),
            "relative_path": normalized_relative_path,
            "object_key": str(object_key or "").strip(),
            "content_type": str(content_type or "application/octet-stream"),
            "file_sha256": str(file_sha256 or "").strip(),
            "size": int(size or 0),
            "created_at": str(created_at or "").strip(),
            "updated_at": str(updated_at or "").strip(),
        }

    def list_ops_archive_records(self, *, archive_group: str = "", backup_id: str = "") -> list[dict]:
        with self._get_meta_index_connection() as conn:
            clauses = []
            params: list[Any] = []
            if archive_group:
                clauses.append("archive_group = ?")
                params.append(str(archive_group).strip())
            if backup_id:
                clauses.append("backup_id = ?")
                params.append(str(backup_id).strip())
            where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
            rows = conn.execute(
                f"""
                SELECT archive_id, archive_group, backup_id, relative_path, object_key,
                       content_type, file_sha256, size, created_at, updated_at
                FROM ops_archive_store
                {where_sql}
                ORDER BY relative_path ASC
                """,
                tuple(params),
            ).fetchall()
        return [self._build_ops_archive_record_payload(row) for row in rows if row]

    def sync_ops_archive_file_to_object_storage(self, file_path: Path, *, relative_path: Optional[str] = None) -> Optional[dict]:
        if not self._is_object_storage_enabled():
            return None
        target = Path(file_path).expanduser().resolve()
        if not target.exists() or not target.is_file():
            return None
        normalized_relative_path = str(relative_path or self._normalize_ops_archive_relative_path(target)).strip().replace("\\", "/")
        archive_group, backup_id = self._classify_ops_archive_relative_path(normalized_relative_path)
        if not archive_group:
            return None
        sha256 = self._compute_file_sha256(target)
        object_key = self.build_ops_archive_object_key(normalized_relative_path)
        content_type = self._guess_content_type(target.name)
        stat = target.stat()
        created_at = datetime.fromtimestamp(stat.st_ctime, timezone.utc).isoformat()
        updated_at = datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat()
        with self._get_meta_index_connection() as conn:
            existing = self._load_ops_archive_record_by_relative_path(conn, normalized_relative_path)
            if existing and existing.get("file_sha256") == sha256 and self._object_storage_key_exists(existing.get("object_key") or ""):
                return existing
            self._upload_file_to_object_storage(
                target,
                object_key=object_key,
                content_type=content_type,
                metadata={
                    "archive-group": archive_group,
                    "backup-id": backup_id,
                    "relative-path": normalized_relative_path,
                    "sha256": sha256,
                },
            )
            return self._upsert_ops_archive_record(
                conn,
                archive_group=archive_group,
                backup_id=backup_id,
                relative_path=normalized_relative_path,
                object_key=object_key,
                content_type=content_type,
                file_sha256=sha256,
                size=int(stat.st_size),
                created_at=created_at,
                updated_at=updated_at,
            )

    @staticmethod
    def _iter_files_recursively(root_dir: Path) -> list[Path]:
        target_root = Path(root_dir)
        if not target_root.exists() or not target_root.is_dir():
            return []
        files: list[Path] = []
        for current_root, _dirs, filenames in os.walk(target_root):
            for filename in filenames:
                files.append((Path(current_root) / filename).resolve())
        return files

    def sync_ops_archive_directory_to_object_storage(self, root_dir: Path) -> int:
        synced_count = 0
        for file_path in self._iter_files_recursively(root_dir):
            try:
                if self.sync_ops_archive_file_to_object_storage(file_path):
                    synced_count += 1
            except Exception as exc:
                if self._debug_enabled:
                    self._debug_log(f"⚠️ 运维归档上传失败: file={file_path}, error={exc}")
        return synced_count

    def sync_materialized_ownership_backup_to_object_storage(self, backup_dir: Path, backup_id: str) -> int:
        target = Path(backup_dir).expanduser().resolve()
        if not target.exists() or not target.is_dir():
            return 0
        synced_count = 0
        canonical_prefix = Path("operations") / "ownership-migrations" / str(backup_id or "").strip()
        for file_path in self._iter_files_recursively(target):
            relative_inside = file_path.relative_to(target)
            canonical_relative = str((canonical_prefix / relative_inside).as_posix())
            try:
                if self.sync_ops_archive_file_to_object_storage(file_path, relative_path=canonical_relative):
                    synced_count += 1
            except Exception as exc:
                if self._debug_enabled:
                    self._debug_log(f"⚠️ 回滚归档上传失败: file={file_path}, error={exc}")
        return synced_count

    def materialize_ownership_backup_from_object_storage(self, backup_id: str) -> Path:
        normalized_backup_id = str(backup_id or "").strip()
        if not normalized_backup_id:
            raise RuntimeError("backup_id 不能为空")
        records = self.list_ops_archive_records(archive_group="ownership_migration", backup_id=normalized_backup_id)
        if not records:
            raise RuntimeError(f"对象存储中不存在备份: {normalized_backup_id}")
        temp_backup_dir = (self._temp_dir / "ownership-migration-archives" / normalized_backup_id).resolve()
        if temp_backup_dir.exists():
            shutil.rmtree(temp_backup_dir, ignore_errors=True)
        temp_backup_dir.mkdir(parents=True, exist_ok=True)
        canonical_prefix = Path("operations") / "ownership-migrations" / normalized_backup_id
        for record in records:
            relative_path = Path(str(record.get("relative_path") or "").strip())
            try:
                relative_inside = relative_path.relative_to(canonical_prefix)
            except Exception:
                continue
            content, _meta = self._download_object_storage_bytes(str(record.get("object_key") or "").strip())
            target_path = temp_backup_dir / relative_inside
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_bytes(content)
        return temp_backup_dir

    def list_archived_ownership_migrations(self, limit: int = 50) -> list[dict]:
        records = self.list_ops_archive_records(archive_group="ownership_migration")
        metadata_records = [
            record for record in records
            if str(record.get("relative_path") or "").strip().endswith("/metadata.json")
        ]
        items: list[dict] = []
        for record in metadata_records:
            backup_id = str(record.get("backup_id") or "").strip()
            if not backup_id:
                continue
            try:
                metadata_bytes, _ = self._download_object_storage_bytes(str(record.get("object_key") or "").strip())
                metadata = json.loads(metadata_bytes.decode("utf-8"))
            except Exception:
                continue
            rollback_payload = None
            rollback_record = next(
                (
                    candidate for candidate in records
                    if str(candidate.get("backup_id") or "").strip() == backup_id
                    and str(candidate.get("relative_path") or "").strip().endswith("/rollback.json")
                ),
                None,
            )
            if rollback_record:
                try:
                    rollback_bytes, _ = self._download_object_storage_bytes(str(rollback_record.get("object_key") or "").strip())
                    rollback_payload = json.loads(rollback_bytes.decode("utf-8"))
                except Exception:
                    rollback_payload = None
            items.append(
                {
                    "backup_id": backup_id,
                    "backup_dir": "",
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
                    "archive_backend": "object_storage",
                }
            )
        items.sort(
            key=lambda item: (
                str(item.get("generated_at") or ""),
                str(item.get("backup_id") or ""),
            ),
            reverse=True,
        )
        return items[: max(1, int(limit or 50))]

    def migrate_ops_archives_to_object_storage_if_needed(self, *, force: bool = False) -> dict:
        summary = {
            "enabled": bool(self._is_object_storage_enabled()),
            "roots": [],
            "uploaded": 0,
            "already_migrated": bool(self._ops_archive_migrated),
        }
        if not self._is_object_storage_enabled():
            return summary
        if self._ops_archive_migrated and not force:
            return summary
        available, error_message = self._ensure_object_storage_sdk_available()
        if not available:
            summary["error"] = error_message or "当前环境未安装 boto3，请先安装 boto3"
            if self._debug_enabled:
                self._debug_log(f"⚠️ 运维归档上传已跳过: {error_message}")
            return summary
        with self._ops_archive_lock:
            if self._ops_archive_migrated and not force:
                summary["already_migrated"] = True
                return summary
            total_synced = 0
            for root_dir in (
                self._data_dir / "operations",
                self._get_restore_backups_root(),
                self._get_session_backups_root(),
            ):
                synced = self.sync_ops_archive_directory_to_object_storage(root_dir)
                summary["roots"].append(
                    {
                        "path": str(root_dir),
                        "uploaded": int(synced or 0),
                    }
                )
                total_synced += synced
            self._ops_archive_migrated = True
            summary["uploaded"] = int(total_synced or 0)
            summary["already_migrated"] = True
            if self._debug_enabled and total_synced > 0:
                self._debug_log(f"✅ 已归档运维备份与回滚产物到对象存储: {total_synced} 个文件")
            return summary
