import importlib.util
import json
import sqlite3
import sys
import tempfile
import types
import unittest
from pathlib import Path

from scripts import import_external_local_data_to_cloud as import_script
from scripts import rollback_external_local_data_import as rollback_script


ROOT_DIR = Path(__file__).resolve().parents[1]
SERVER_PATH = ROOT_DIR / "web" / "server.py"


def load_server_module():
    if str(ROOT_DIR) not in sys.path:
        sys.path.insert(0, str(ROOT_DIR))

    config_stub = types.ModuleType("config")
    config_stub.ANTHROPIC_API_KEY = ""
    config_stub.ANTHROPIC_BASE_URL = ""
    config_stub.MODEL_NAME = "claude-sonnet-4-20250514"
    config_stub.MAX_TOKENS_DEFAULT = 5000
    config_stub.MAX_TOKENS_QUESTION = 2000
    config_stub.MAX_TOKENS_REPORT = 10000
    config_stub.SERVER_HOST = "127.0.0.1"
    config_stub.SERVER_PORT = 5001
    config_stub.DEBUG_MODE = True
    config_stub.ENABLE_AI = False
    config_stub.ENABLE_DEBUG_LOG = False
    config_stub.ENABLE_WEB_SEARCH = False
    config_stub.ZHIPU_API_KEY = ""
    config_stub.ZHIPU_SEARCH_ENGINE = "search_pro"
    config_stub.SEARCH_MAX_RESULTS = 3
    config_stub.SEARCH_TIMEOUT = 10
    config_stub.VISION_MODEL_NAME = ""
    config_stub.VISION_API_URL = ""
    config_stub.ENABLE_VISION = False
    config_stub.MAX_IMAGE_SIZE_MB = 10
    config_stub.SUPPORTED_IMAGE_TYPES = [".jpg", ".jpeg", ".png", ".gif", ".webp"]
    config_stub.REFLY_API_URL = ""
    config_stub.REFLY_API_KEY = ""
    config_stub.REFLY_WORKFLOW_ID = ""
    config_stub.REFLY_INPUT_FIELD = "report"
    config_stub.REFLY_FILES_FIELD = "files"
    config_stub.REFLY_TIMEOUT = 30

    spec = importlib.util.spec_from_file_location("dv_server_external_import_test", SERVER_PATH)
    module = importlib.util.module_from_spec(spec)
    previous_config = sys.modules.get("config")
    sys.modules["config"] = config_stub
    try:
        spec.loader.exec_module(module)
    finally:
        if previous_config is None:
            sys.modules.pop("config", None)
        else:
            sys.modules["config"] = previous_config
    return module


class ExternalLocalDataImportTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="dv-external-import-")
        self.root = Path(self.temp_dir.name).resolve()
        self.server = load_server_module()
        self._configure_server_paths()
        self.backup_root = self.root / "backups"
        self.backup_root.mkdir(parents=True, exist_ok=True)
        self._previous_backup_root = import_script.DEFAULT_BACKUP_ROOT
        import_script.DEFAULT_BACKUP_ROOT = self.backup_root

    def tearDown(self):
        import_script.DEFAULT_BACKUP_ROOT = self._previous_backup_root
        self.temp_dir.cleanup()

    def _configure_server_paths(self):
        data_dir = self.root / "target-data"
        self.server.DATA_DIR = data_dir
        self.server.SESSIONS_DIR = data_dir / "sessions"
        self.server.REPORTS_DIR = data_dir / "reports"
        self.server.AUTH_DIR = data_dir / "auth"
        self.server.CONVERTED_DIR = data_dir / "converted"
        self.server.TEMP_DIR = data_dir / "temp"
        self.server.METRICS_DIR = data_dir / "metrics"
        self.server.SUMMARIES_DIR = data_dir / "summaries"
        self.server.PRESENTATIONS_DIR = data_dir / "presentations"
        self.server.AUTH_DB_PATH = self.server.AUTH_DIR / "users.db"
        self.server.LICENSE_DB_PATH = self.server.AUTH_DIR / "licenses.db"
        self.server.META_INDEX_DB_TARGET_RAW = str((data_dir / "meta_index.db").resolve())
        self.server.DELETED_REPORTS_FILE = self.server.REPORTS_DIR / ".deleted_reports.json"
        self.server.DELETED_DOCS_FILE = self.server.DATA_DIR / ".deleted_docs.json"
        self.server.REPORT_OWNERS_FILE = self.server.REPORTS_DIR / ".owners.json"
        self.server.REPORT_SCOPES_FILE = self.server.REPORTS_DIR / ".scopes.json"
        self.server.REPORT_SOLUTION_SHARES_FILE = self.server.REPORTS_DIR / ".solution_shares.json"

        for path in [
            self.server.SESSIONS_DIR,
            self.server.REPORTS_DIR,
            self.server.AUTH_DIR,
            self.server.CONVERTED_DIR,
            self.server.TEMP_DIR,
            self.server.METRICS_DIR,
            self.server.SUMMARIES_DIR,
            self.server.PRESENTATIONS_DIR,
        ]:
            path.mkdir(parents=True, exist_ok=True)

        self.server._use_postgres_shared_meta_storage = lambda: True
        self.server._use_pure_cloud_session_storage = lambda: True
        self.server._use_pure_cloud_report_storage = lambda: True
        with self.server.meta_index_state_lock:
            self.server.meta_index_state["db_path"] = ""
            self.server.meta_index_state["schema_ready"] = False
            self.server.meta_index_state["sessions_bootstrapped"] = False
            self.server.meta_index_state["reports_bootstrapped"] = False
        self.server.init_auth_db()
        self.server.ensure_meta_index_schema()

    def _create_target_user(self, *, user_id: int, phone: str = "", email: str = ""):
        with self.server.get_auth_db_connection() as conn:
            conn.execute(
                """
                INSERT INTO users(id, email, phone, password_hash, created_at, updated_at)
                VALUES (?, ?, ?, '', '2026-04-02T00:00:00Z', '2026-04-02T00:00:00Z')
                ON CONFLICT(id) DO UPDATE SET
                    email=excluded.email,
                    phone=excluded.phone,
                    updated_at=excluded.updated_at
                """,
                (int(user_id), email or None, phone or None),
            )

    def _create_target_wechat_identity(self, *, user_id: int, app_id: str, openid: str, unionid: str = ""):
        with self.server.get_auth_db_connection() as conn:
            conn.execute(
                """
                INSERT INTO wechat_identities(user_id, app_id, openid, unionid, nickname, avatar_url, created_at, updated_at)
                VALUES (?, ?, ?, ?, '', '', '2026-04-02T00:00:00Z', '2026-04-02T00:00:00Z')
                """,
                (int(user_id), app_id, openid, unionid or None),
            )

    def _seed_target_session(self, session_id: str, owner_user_id: int, topic: str = "已有会话"):
        payload = {
            "session_id": session_id,
            "owner_user_id": int(owner_user_id),
            "topic": topic,
            "status": "completed",
            "created_at": "2026-04-01T00:00:00Z",
            "updated_at": "2026-04-01T00:00:00Z",
            "dimensions": {},
            "interview_log": [],
        }
        session_file = self.server.SESSIONS_DIR / f"{session_id}.json"
        session_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        with self.server.get_meta_index_connection() as conn:
            record = self.server._build_session_store_record(session_file, payload)
            self.server._upsert_session_store_record(conn, record)
        self.server.rebuild_session_index_from_disk(full_reset=True)

    def _seed_target_report(self, file_name: str, owner_user_id: int):
        with self.server.get_meta_index_connection() as conn:
            record = self.server._build_report_store_record(
                file_name,
                "# 已有报告\n\n内容",
                created_at="2026-04-01T00:00:00Z",
                updated_at="2026-04-01T00:00:00Z",
                signature=(1712016000000000000, len("# 已有报告\n\n内容".encode("utf-8"))),
            )
            self.server._upsert_report_store_record(conn, record)
            conn.execute(
                """
                INSERT INTO report_meta_owners(file_name, owner_user_id, updated_at)
                VALUES (?, ?, '2026-04-01T00:00:00Z')
                ON CONFLICT(file_name) DO UPDATE SET
                    owner_user_id=excluded.owner_user_id,
                    updated_at=excluded.updated_at
                """,
                (file_name, int(owner_user_id)),
            )
        self.server.rebuild_report_index_from_sources(full_reset=True)

    def _create_source_bundle(self) -> Path:
        source_root = self.root / "source-package" / "data"
        (source_root / "sessions").mkdir(parents=True, exist_ok=True)
        (source_root / "reports").mkdir(parents=True, exist_ok=True)
        (source_root / "auth").mkdir(parents=True, exist_ok=True)
        return source_root

    def _create_source_auth_db(self, db_path: Path):
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute(
                """
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY,
                    email TEXT,
                    phone TEXT,
                    created_at TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE wechat_identities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    app_id TEXT NOT NULL,
                    openid TEXT NOT NULL,
                    unionid TEXT,
                    nickname TEXT,
                    avatar_url TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
                """
            )

    def test_dry_run_maps_source_users_and_reports_conflicts(self):
        self._create_target_user(user_id=3, phone="13886047722")
        self._create_target_user(user_id=7, email="mapped@example.com")
        self._create_target_user(user_id=9, phone="13900000000")
        self._create_target_wechat_identity(user_id=9, app_id="wx-app", openid="openid-9", unionid="union-9")
        self._seed_target_session("session-conflict", 3)
        self._seed_target_report("conflict.md", 3)

        source_root = self._create_source_bundle()
        source_auth_db = source_root / "auth" / "users.db"
        self._create_source_auth_db(source_auth_db)
        with sqlite3.connect(str(source_auth_db)) as conn:
            conn.execute("INSERT INTO users(id, email, phone, created_at) VALUES (11, '', '13886047722', '2026-04-01T00:00:00Z')")
            conn.execute("INSERT INTO users(id, email, phone, created_at) VALUES (12, 'mapped@example.com', '', '2026-04-01T00:00:00Z')")
            conn.execute("INSERT INTO users(id, email, phone, created_at) VALUES (13, '', '', '2026-04-01T00:00:00Z')")
            conn.execute("INSERT INTO users(id, email, phone, created_at) VALUES (14, '', '13700000000', '2026-04-01T00:00:00Z')")
            conn.execute(
                "INSERT INTO wechat_identities(user_id, app_id, openid, unionid, nickname, avatar_url, created_at, updated_at) VALUES (13, 'wx-app', 'openid-9', 'union-9', '', '', '2026-04-01T00:00:00Z', '2026-04-01T00:00:00Z')"
            )

        session_conflict = {
            "session_id": "session-conflict",
            "owner_user_id": 11,
            "topic": "冲突会话",
            "created_at": "2026-04-01T00:00:00Z",
            "updated_at": "2026-04-01T00:00:00Z",
            "dimensions": {},
            "interview_log": [],
        }
        session_ok = {
            "session_id": "session-ok",
            "owner_user_id": 12,
            "topic": "正常会话",
            "created_at": "2026-04-01T00:00:00Z",
            "updated_at": "2026-04-01T00:00:00Z",
            "current_report_name": "report-ok.md",
            "dimensions": {},
            "interview_log": [],
        }
        (source_root / "sessions" / "session-conflict.json").write_text(json.dumps(session_conflict, ensure_ascii=False, indent=2), encoding="utf-8")
        (source_root / "sessions" / "session-ok.json").write_text(json.dumps(session_ok, ensure_ascii=False, indent=2), encoding="utf-8")
        (source_root / "reports" / "conflict.md").write_text("# 冲突报告", encoding="utf-8")
        (source_root / "reports" / "report-ok.md").write_text("# 正常报告", encoding="utf-8")
        (source_root / "reports" / ".owners.json").write_text(
            json.dumps({"conflict.md": 11, "report-ok.md": 12}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        result = import_script.run_import(
            source_data_dir=str(source_root),
            source_auth_db=str(source_auth_db),
            apply_changes=False,
            server_module=self.server,
        )

        self.assertFalse(result["applied"])
        self.assertEqual(3, len(result["resolved_user_mappings"]))
        self.assertEqual(1, len(result["unresolved_users"]))
        self.assertEqual(1, result["planned_import"]["sessions"]["conflicts"])
        self.assertEqual(1, result["planned_import"]["reports"]["conflicts"])

    def test_apply_ownerless_import_rebuilds_indexes_and_uses_overrides(self):
        self._create_target_user(user_id=3, phone="13886047722")
        self._create_target_user(user_id=7, email="pro@example.com")

        source_root = self._create_source_bundle()
        session_a = {
            "session_id": "session-a",
            "topic": "默认归属",
            "created_at": "2026-04-01T00:00:00Z",
            "updated_at": "2026-04-01T00:00:00Z",
            "current_report_name": "report-a.md",
            "dimensions": {},
            "interview_log": [],
        }
        session_b = {
            "session_id": "session-b",
            "topic": "覆盖归属",
            "created_at": "2026-04-01T00:00:00Z",
            "updated_at": "2026-04-01T00:00:00Z",
            "current_report_name": "report-b.md",
            "dimensions": {},
            "interview_log": [],
        }
        (source_root / "sessions" / "session-a.json").write_text(json.dumps(session_a, ensure_ascii=False, indent=2), encoding="utf-8")
        (source_root / "sessions" / "session-b.json").write_text(json.dumps(session_b, ensure_ascii=False, indent=2), encoding="utf-8")
        (source_root / "reports" / "report-a.md").write_text("# 普通报告 A", encoding="utf-8")
        (source_root / "reports" / "report-b.md").write_text("# 普通报告 B", encoding="utf-8")
        (source_root / "reports" / ".scopes.json").write_text(
            json.dumps({"report-a.md": "default", "report-b.md": "default"}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (source_root / "reports" / ".solution_shares.json").write_text(
            json.dumps(
                {
                    "share-token-abcdefghijkl": {
                        "report_name": "report-a.md",
                        "owner_user_id": 0,
                        "created_at": "2026-04-01T00:00:00Z",
                        "updated_at": "2026-04-01T00:00:00Z",
                    }
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        custom_dir = source_root / "custom_scenarios"
        custom_dir.mkdir(parents=True, exist_ok=True)
        (custom_dir / "scenario-a.json").write_text(
            json.dumps({"id": "scenario-a", "name": "自定义场景 A"}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        user_map_path = self.root / "ownerless-map.json"
        user_map_path.write_text(
            json.dumps(
                {
                    "default_target_user_id": 3,
                    "session_map": {"session-b": 7},
                    "report_map": {"report-b.md": 7},
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        result = import_script.run_import(
            source_data_dir=str(source_root),
            target_user_id=3,
            user_map_json=str(user_map_path),
            apply_changes=True,
            include="sessions,reports,report-meta,indexes,custom-scenarios",
            server_module=self.server,
        )

        self.assertTrue(result["applied"])
        self.assertTrue(result["backup"]["performed"])
        self.assertEqual(2, result["imported"]["sessions"])
        self.assertEqual(2, result["imported"]["reports"])
        self.assertEqual(1, result["imported"]["custom_scenarios"])
        self.assertTrue(result["imported"]["indexes_rebuilt"])

        sessions_user_3, total_user_3 = self.server.query_session_index_for_user(3, 1, 20)
        sessions_user_7, total_user_7 = self.server.query_session_index_for_user(7, 1, 20)
        self.assertEqual(1, total_user_3)
        self.assertEqual(1, total_user_7)
        self.assertEqual({"session-a"}, {item["session_id"] for item in sessions_user_3})
        self.assertEqual({"session-b"}, {item["session_id"] for item in sessions_user_7})

        reports_user_3, reports_total_3 = self.server.query_report_index_for_user(3, 1, 20)
        reports_user_7, reports_total_7 = self.server.query_report_index_for_user(7, 1, 20)
        self.assertEqual(1, reports_total_3)
        self.assertEqual(1, reports_total_7)
        self.assertEqual({"report-a.md"}, {item["name"] for item in reports_user_3})
        self.assertEqual({"report-b.md"}, {item["name"] for item in reports_user_7})

        with self.server.get_meta_index_connection() as conn:
            owner_rows = {
                row["file_name"]: int(row["owner_user_id"])
                for row in conn.execute("SELECT file_name, owner_user_id FROM report_meta_owners").fetchall()
            }
            self.assertEqual(3, owner_rows["report-a.md"])
            self.assertEqual(7, owner_rows["report-b.md"])

    def test_apply_rewrites_source_scope_to_active_scope_by_default(self):
        self._create_target_user(user_id=3, phone="13886047722")
        self.server.INSTANCE_SCOPE_ENFORCEMENT_ENABLED = True
        self.server.INSTANCE_SCOPE_KEY = "cloud-prod"

        source_root = self._create_source_bundle()
        session_payload = {
            "session_id": "scope-session",
            "topic": "作用域迁移会话",
            "created_at": "2026-04-01T00:00:00Z",
            "updated_at": "2026-04-01T00:00:00Z",
            "current_report_name": "scope-report.md",
            "instance_scope_key": "legacy-local",
            "dimensions": {},
            "interview_log": [],
        }
        (source_root / "sessions" / "scope-session.json").write_text(
            json.dumps(session_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (source_root / "reports" / "scope-report.md").write_text("# 作用域报告", encoding="utf-8")
        (source_root / "reports" / ".scopes.json").write_text(
            json.dumps({"scope-report.md": "legacy-local"}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        result = import_script.run_import(
            source_data_dir=str(source_root),
            target_user_id=3,
            apply_changes=True,
            include="sessions,reports,report-meta,indexes",
            server_module=self.server,
        )

        self.assertTrue(result["applied"])
        self.assertEqual("cloud-prod", result["source_summary"]["active_scope_key"])
        self.assertTrue(result["source_summary"]["rewrite_to_active_scope"])

        sessions_user_3, total_sessions = self.server.query_session_index_for_user(3, 1, 20)
        reports_user_3, total_reports = self.server.query_report_index_for_user(3, 1, 20)
        self.assertEqual(1, total_sessions)
        self.assertEqual(1, total_reports)
        self.assertEqual({"scope-session"}, {item["session_id"] for item in sessions_user_3})
        self.assertEqual({"scope-report.md"}, {item["name"] for item in reports_user_3})

        with self.server.get_meta_index_connection() as conn:
            session_row = conn.execute(
                "SELECT instance_scope_key FROM session_store WHERE session_id = ?",
                ("scope-session",),
            ).fetchone()
            report_scope_row = conn.execute(
                "SELECT instance_scope_key FROM report_meta_scopes WHERE file_name = ?",
                ("scope-report.md",),
            ).fetchone()
        self.assertEqual("cloud-prod", str(session_row["instance_scope_key"] or ""))
        self.assertEqual("cloud-prod", str(report_scope_row["instance_scope_key"] or ""))

    def test_rollback_restores_pre_import_snapshot(self):
        self._create_target_user(user_id=3, phone="13886047722")
        self._seed_target_session("baseline-session", 3, topic="基线会话")
        self._seed_target_report("baseline-report.md", 3)

        source_root = self._create_source_bundle()
        session_new = {
            "session_id": "imported-session",
            "topic": "待回滚会话",
            "created_at": "2026-04-01T00:00:00Z",
            "updated_at": "2026-04-01T00:00:00Z",
            "current_report_name": "imported-report.md",
            "dimensions": {},
            "interview_log": [],
        }
        (source_root / "sessions" / "imported-session.json").write_text(json.dumps(session_new, ensure_ascii=False, indent=2), encoding="utf-8")
        (source_root / "reports" / "imported-report.md").write_text("# 待回滚报告", encoding="utf-8")

        apply_result = import_script.run_import(
            source_data_dir=str(source_root),
            target_user_id=3,
            apply_changes=True,
            include="sessions,reports,report-meta,indexes",
            server_module=self.server,
        )
        self.assertTrue(apply_result["applied"])
        backup_dir = apply_result["backup"]["backup_dir"]
        sessions_after_import, total_after_import = self.server.query_session_index_for_user(3, 1, 20)
        self.assertEqual(2, total_after_import)
        self.assertIn("imported-session", {item["session_id"] for item in sessions_after_import})

        rollback_result = rollback_script.run_rollback(
            backup_dir=backup_dir,
            server_module=self.server,
        )
        self.assertTrue(rollback_result["applied"])

        sessions_after_rollback, total_after_rollback = self.server.query_session_index_for_user(3, 1, 20)
        self.assertEqual(1, total_after_rollback)
        self.assertEqual({"baseline-session"}, {item["session_id"] for item in sessions_after_rollback})

        reports_after_rollback, reports_total_after_rollback = self.server.query_report_index_for_user(3, 1, 20)
        self.assertEqual(1, reports_total_after_rollback)
        self.assertEqual({"baseline-report.md"}, {item["name"] for item in reports_after_rollback})
