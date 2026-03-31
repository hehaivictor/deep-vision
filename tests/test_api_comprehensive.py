import io
import importlib.util
import json
import sys
import tempfile
import threading
import time
import types
import unittest
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote


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

    spec = importlib.util.spec_from_file_location("dv_server_api_test", SERVER_PATH)
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


class ComprehensiveApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = load_server_module()
        cls.temp_dir = tempfile.TemporaryDirectory(prefix="dv-api-tests-")
        cls.sandbox_root = Path(cls.temp_dir.name).resolve()
        cls._configure_sandbox_paths()
        cls.server.app.config["TESTING"] = True
        cls.server.SMS_SEND_COOLDOWN_SECONDS = 0
        cls.server._use_postgres_shared_meta_storage = lambda: False
        cls.server._use_pure_cloud_session_storage = lambda: False

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    @classmethod
    def _configure_sandbox_paths(cls):
        data_dir = cls.sandbox_root / "data"
        cls.server.DATA_DIR = data_dir
        cls.server.SESSIONS_DIR = data_dir / "sessions"
        cls.server.REPORTS_DIR = data_dir / "reports"
        cls.server.CONVERTED_DIR = data_dir / "converted"
        cls.server.TEMP_DIR = data_dir / "temp"
        cls.server.METRICS_DIR = data_dir / "metrics"
        cls.server.SUMMARIES_DIR = data_dir / "summaries"
        cls.server.PRESENTATIONS_DIR = data_dir / "presentations"
        cls.server.AUTH_DIR = data_dir / "auth"
        cls.server.AUTH_DB_PATH = cls.server.AUTH_DIR / "users.db"
        cls.server.LICENSE_DB_PATH = cls.server.AUTH_DIR / "licenses.db"
        cls.server.META_INDEX_DB_TARGET_RAW = str((data_dir / "meta_index.db").resolve())
        cls.server.PRESENTATION_MAP_FILE = cls.server.PRESENTATIONS_DIR / ".presentation_map.json"
        cls.server.DELETED_REPORTS_FILE = cls.server.REPORTS_DIR / ".deleted_reports.json"
        cls.server.DELETED_DOCS_FILE = cls.server.DATA_DIR / ".deleted_docs.json"
        cls.server.REPORT_OWNERS_FILE = cls.server.REPORTS_DIR / ".owners.json"
        cls.server.REPORT_SCOPES_FILE = cls.server.REPORTS_DIR / ".scopes.json"
        cls.server.REPORT_SOLUTION_SHARES_FILE = cls.server.REPORTS_DIR / ".solution_shares.json"

        for path in [
            cls.server.SESSIONS_DIR,
            cls.server.REPORTS_DIR,
            cls.server.CONVERTED_DIR,
            cls.server.TEMP_DIR,
            cls.server.METRICS_DIR,
            cls.server.SUMMARIES_DIR,
            cls.server.PRESENTATIONS_DIR,
            cls.server.AUTH_DIR,
        ]:
            path.mkdir(parents=True, exist_ok=True)

        cls.server.metrics_collector.metrics_file = cls.server.METRICS_DIR / "api_metrics.json"
        with cls.server.meta_index_state_lock:
            cls.server.meta_index_state["db_path"] = ""
            cls.server.meta_index_state["schema_ready"] = False
            cls.server.meta_index_state["sessions_bootstrapped"] = False
            cls.server.meta_index_state["reports_bootstrapped"] = False
        cls.server.metrics_collector.metrics_file.write_text(
            json.dumps(
                {
                    "calls": [],
                    "summary": {
                        "total_calls": 0,
                        "total_timeouts": 0,
                        "total_truncations": 0,
                        "avg_response_time": 0,
                        "avg_prompt_length": 0,
                    },
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        cls.server.init_auth_db()
        cls.server.init_license_db()

        # 避免测试中启动后台预生成线程和外部依赖。
        cls.server.ENABLE_AI = False
        cls.server.ENABLE_DEBUG_LOG = False
        cls.server.question_ai_client = None
        cls.server.report_ai_client = None
        cls.server.prefetch_first_question = lambda _session_id: None
        cls.real_trigger_current_dimension_prefetch = cls.server.trigger_current_dimension_prefetch
        cls.server.trigger_prefetch_if_needed = lambda *_args, **_kwargs: None
        cls.server.trigger_current_dimension_prefetch = lambda *_args, **_kwargs: None

        # 使用测试沙箱内的场景存储，避免污染仓库数据。
        from scripts import scenario_loader as scenario_loader_module

        scenarios_dir = cls.server.DATA_DIR / "scenarios"
        scenario_loader_module._scenario_loader = scenario_loader_module.ScenarioLoader(scenarios_dir)
        cls.server.scenario_loader = scenario_loader_module._scenario_loader

    def setUp(self):
        self.client = self.server.app.test_client()
        self.server.LICENSE_ENFORCEMENT_ENABLED = False
        self.server.set_license_enforcement_override(False)
        self.server.SMS_PROVIDER = "mock"
        self.server.reset_list_metrics()
        self.server.report_owners_cache["signature"] = None
        self.server.report_owners_cache["data"] = {}
        self.server.report_scopes_cache["signature"] = None
        self.server.report_scopes_cache["data"] = {}
        self.server.report_solution_shares_cache["signature"] = None
        self.server.report_solution_shares_cache["data"] = {}
        self.server.session_list_cache.clear()
        self.server.INSTANCE_SCOPE_KEY = ""
        with self.server.report_generation_status_lock:
            self.server.report_generation_status.clear()
        with self.server.report_generation_workers_lock:
            self.server.report_generation_workers.clear()
        with self.server.report_generation_queue_stats_lock:
            for key in self.server.report_generation_queue_stats.keys():
                self.server.report_generation_queue_stats[key] = 0
        with self.server.list_overload_stats_lock:
            for key in self.server.list_overload_stats.keys():
                self.server.list_overload_stats[key]["rejected"] = 0
        with self.server.question_result_cache_lock:
            self.server.question_result_cache.clear()
        with self.server.prefetch_cache_lock:
            self.server.prefetch_cache.clear()
        with self.server.question_prefetch_inflight_lock:
            self.server.question_prefetch_inflight.clear()
        with self.server.session_payload_cache_lock:
            self.server.session_payload_cache_by_id.clear()
            self.server.session_payload_cache_by_file_name.clear()
        self.server.SESSIONS_LIST_SEMAPHORE = threading.BoundedSemaphore(self.server.SESSIONS_LIST_MAX_INFLIGHT)
        self.server.REPORTS_LIST_SEMAPHORE = threading.BoundedSemaphore(self.server.REPORTS_LIST_MAX_INFLIGHT)
        self.server.QUESTION_GENERATION_SEMAPHORE = threading.BoundedSemaphore(self.server.QUESTION_GENERATION_MAX_INFLIGHT)
        self.server.QUESTION_GENERATION_PENDING_SEMAPHORE = threading.BoundedSemaphore(self.server.QUESTION_GENERATION_MAX_PENDING)
        self.server.reset_question_generation_stats()
        self.server.reset_question_generation_runtime_stats()
        self.server.reset_report_generation_runtime_stats()

    def _register(self, client=None):
        target = client or self.client
        account = f"1{uuid.uuid4().int % 10**10:010d}"
        send_resp = target.post(
            "/api/auth/sms/send-code",
            json={"account": account, "scene": "login"},
        )
        self.assertEqual(send_resp.status_code, 200, send_resp.get_data(as_text=True))
        code = (send_resp.get_json() or {}).get("test_code")
        self.assertTrue(code, "TESTING 模式应返回 test_code")

        login_resp = target.post(
            "/api/auth/login/code",
            json={"account": account, "code": code, "scene": "login"},
        )
        self.assertEqual(login_resp.status_code, 200, login_resp.get_data(as_text=True))
        return login_resp.get_json()["user"]

    def _set_authenticated_client(self, client, user):
        with client.session_transaction() as sess:
            sess["user_id"] = int(user["id"])
            sess["auth_instance_id"] = str(self.server.get_auth_instance_id() or "")

    def _generate_license_batch(
        self,
        *,
        count=1,
        duration_days=30,
        use_absolute_window=False,
        starts_in_days=-1,
        expires_in_days=30,
        note="测试 License 批次",
        level_key="standard",
    ):
        kwargs = {
            "count": count,
            "note": note,
            "level_key": level_key,
            "actor_user_id": None,
        }
        if use_absolute_window:
            now = datetime.utcnow().replace(microsecond=0)
            kwargs["not_before_at"] = (now + timedelta(days=starts_in_days)).isoformat()
            kwargs["expires_at"] = (now + timedelta(days=expires_in_days)).isoformat()
        else:
            kwargs["duration_days"] = duration_days
        return self.server.generate_license_batch(**kwargs)

    def _activate_license(self, code: str, client=None):
        target = client or self.client
        response = target.post("/api/licenses/activate", json={"code": code})
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        return response.get_json() or {}

    def _create_wechat_user(
        self,
        *,
        app_id="wx-test-app",
        openid=None,
        unionid=None,
        nickname="微信用户",
        avatar_url="https://example.com/avatar.png",
    ):
        openid_value = openid or f"openid-{uuid.uuid4().hex[:8]}"
        unionid_value = unionid or f"unionid-{uuid.uuid4().hex[:8]}"
        return self.server.resolve_user_for_wechat_identity(
            app_id=app_id,
            openid=openid_value,
            unionid=unionid_value,
            nickname=nickname,
            avatar_url=avatar_url,
        )

    def _create_owned_merge_fixture(self, user_id: int, prefix: str) -> dict:
        now_iso = datetime.utcnow().isoformat()
        session_id = f"{prefix}-session"
        session_file = self.server.SESSIONS_DIR / f"{session_id}.json"
        self.server.save_session_json_and_sync(
            session_file,
            {
                "session_id": session_id,
                "topic": f"{prefix} 会话",
                "status": "in_progress",
                "created_at": now_iso,
                "updated_at": now_iso,
                "owner_user_id": int(user_id),
                "dimensions": {},
                "interview_log": [],
            },
        )

        report_name = f"{prefix}-report.md"
        (self.server.REPORTS_DIR / report_name).write_text("# 报告\n", encoding="utf-8")
        self.server.set_report_owner_id(report_name, int(user_id))
        share_record = self.server.create_or_get_solution_share(report_name, int(user_id))

        scenario_id = self.server.scenario_loader.save_custom_scenario(
            {
                "name": f"{prefix} 场景",
                "description": "测试场景",
                "keywords": [prefix, "测试"],
                "dimensions": [
                    {
                        "id": "dim_1",
                        "name": "维度1",
                        "description": "描述",
                        "key_aspects": ["A", "B"],
                        "min_questions": 2,
                        "max_questions": 4,
                    }
                ],
                "report": {"type": "standard", "template": "default"},
                "owner_user_id": int(user_id),
            }
        )

        license_batch = self._generate_license_batch(count=1, note=f"{prefix} License")
        activation_code = license_batch["licenses"][0]["code"]
        ok, status_code, payload = self.server.activate_license_for_user(activation_code, int(user_id))
        self.assertTrue(ok, payload)
        self.assertEqual(200, status_code)

        return {
            "session_file": session_file,
            "report_name": report_name,
            "share_token": share_record["share_token"],
            "scenario_id": scenario_id,
            "license_status": payload,
        }

    def _create_session(self, topic="综合测试会话", description="测试描述", interview_mode=None, client=None):
        payload = {"topic": topic, "description": description}
        if interview_mode:
            payload["interview_mode"] = interview_mode
        target = client or self.client
        response = target.post(
            "/api/sessions",
            json=payload,
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        payload = response.get_json()
        self.assertIn("session_id", payload)
        return payload

    def _submit_answer(self, session_id, dimension, question="测试问题", answer="测试回答", client=None):
        target = client or self.client
        response = target.post(
            f"/api/sessions/{session_id}/submit-answer",
            json={
                "question": question,
                "answer": answer,
                "dimension": dimension,
                "options": ["A", "B"],
                "is_follow_up": False,
            },
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        return response.get_json()

    def _build_scoped_report_name(self, topic, date_str="20990101", session_id=""):
        slug = self.server.normalize_topic_slug(topic)
        parts = ["deep-vision", date_str]
        tag = self.server.get_instance_scope_short_tag()
        if tag:
            parts.append(tag)
        if session_id:
            parts.append(session_id)
        parts.append(slug)
        return "-".join(parts) + ".md"

    def _create_owned_report(self, user_id: int, *, topic="用户级别报告", content=None):
        report_name = self._build_scoped_report_name(topic, session_id=uuid.uuid4().hex[:8])
        report_content = content or (
            f"# {topic}访谈报告\n\n"
            "## 一、需求摘要\n\n"
            "本报告用于验证用户级别能力控制。\n\n"
            "## 二、结论建议\n\n"
            "建议按等级控制导出、方案与演示入口。\n\n"
            "## 附录：完整访谈记录\n\n"
            "### 问题 1：需求是什么？\n\n"
            "<div><strong>回答：</strong></div>\n"
            "<div>需要完整的等级能力控制。</div>\n"
        )
        report_path = self.server.REPORTS_DIR / report_name
        report_path.write_text(report_content, encoding="utf-8")
        self.server.set_report_owner_id(report_name, int(user_id))
        return report_name

    def _wait_report_generation(self, session_id, expected_state="completed", attempts=120):
        status_payload = {}
        for _ in range(attempts):
            status_resp = self.client.get(f"/api/status/report-generation/{session_id}")
            self.assertEqual(status_resp.status_code, 200, status_resp.get_data(as_text=True))
            status_payload = status_resp.get_json() or {}
            if status_payload.get("state") == expected_state:
                if expected_state != "completed" or status_payload.get("report_name"):
                    break
            time.sleep(0.05)

        self.assertEqual(status_payload.get("state"), expected_state, status_payload)
        return status_payload

    def _generate_report_with_fixed_now(
        self,
        session_id,
        fixed_now: datetime,
        action="generate",
        report_profile="quality",
        source_report_name="",
    ):
        real_datetime = self.server.datetime

        class FixedDateTime(real_datetime):
            @classmethod
            def now(cls, tz=None):
                if tz is not None:
                    return fixed_now.replace(tzinfo=tz)
                return fixed_now.replace(tzinfo=None)

        self.server.datetime = FixedDateTime
        try:
            response = self.client.post(
                f"/api/sessions/{session_id}/generate-report",
                json={
                    "action": action,
                    "report_profile": report_profile,
                    "source_report_name": source_report_name,
                },
            )
            self.assertEqual(response.status_code, 202, response.get_data(as_text=True))
            return self._wait_report_generation(session_id)
        finally:
            self.server.datetime = real_datetime

    def test_auth_lifecycle(self):
        self._register()

        me_resp = self.client.get("/api/auth/me")
        self.assertEqual(me_resp.status_code, 200)
        self.assertIn("user", me_resp.get_json())

        logout_resp = self.client.post("/api/auth/logout")
        self.assertEqual(logout_resp.status_code, 200)

        me_after_logout = self.client.get("/api/auth/me")
        self.assertEqual(me_after_logout.status_code, 401)

        send_again = self.client.post(
            "/api/auth/sms/send-code",
            json={"account": me_resp.get_json()["user"]["account"], "scene": "login"},
        )
        self.assertEqual(send_again.status_code, 200, send_again.get_data(as_text=True))
        code = (send_again.get_json() or {}).get("test_code")
        self.assertTrue(code)

        login_resp = self.client.post(
            "/api/auth/login/code",
            json={"account": me_resp.get_json()["user"]["account"], "code": code, "scene": "login"},
        )
        self.assertEqual(login_resp.status_code, 200)

        me_after_login = self.client.get("/api/auth/me")
        self.assertEqual(me_after_login.status_code, 200)

    def test_auth_and_status_include_user_level_payload(self):
        self._register()

        me_resp = self.client.get("/api/auth/me")
        self.assertEqual(me_resp.status_code, 200, me_resp.get_data(as_text=True))
        me_payload = me_resp.get_json() or {}
        self.assertEqual("experience", (me_payload.get("level") or {}).get("key"))
        self.assertEqual(["balanced"], me_payload.get("allowed_report_profiles"))
        self.assertEqual("balanced", me_payload.get("report_profile_default"))
        self.assertEqual(["quick"], me_payload.get("allowed_interview_modes"))
        self.assertEqual("quick", me_payload.get("interview_mode_default"))
        self.assertEqual("standard", ((me_payload.get("interview_mode_requirements") or {}).get("standard") or {}).get("key"))
        self.assertEqual("professional", ((me_payload.get("interview_mode_requirements") or {}).get("deep") or {}).get("key"))
        self.assertFalse((me_payload.get("capabilities") or {}).get("report.export.basic"))

        status_resp = self.client.get("/api/status")
        self.assertEqual(status_resp.status_code, 200, status_resp.get_data(as_text=True))
        status_payload = status_resp.get_json() or {}
        self.assertEqual("experience", (status_payload.get("level") or {}).get("key"))
        self.assertEqual(["balanced"], status_payload.get("allowed_report_profiles"))
        self.assertEqual(["balanced"], status_payload.get("report_profile_options"))
        self.assertEqual(["quick"], status_payload.get("allowed_interview_modes"))
        self.assertEqual("quick", status_payload.get("interview_mode_default"))

    def test_experience_user_cannot_create_standard_or_deep_session(self):
        self._register()
        original_is_license_protected_route = self.server.is_license_protected_route
        try:
            self.server.is_license_protected_route = lambda _path: False

            standard_resp = self.client.post(
                "/api/sessions",
                json={"topic": "体验版标准模式", "description": "测试", "interview_mode": "standard"},
            )
            self.assertEqual(standard_resp.status_code, 403, standard_resp.get_data(as_text=True))
            standard_payload = standard_resp.get_json() or {}
            self.assertEqual("level_capability_denied", standard_payload.get("error_code"))
            self.assertEqual("interview.mode.standard", standard_payload.get("capability_key"))
            self.assertEqual("experience", (standard_payload.get("current_level") or {}).get("key"))
            self.assertEqual("standard", (standard_payload.get("required_level") or {}).get("key"))

            deep_resp = self.client.post(
                "/api/sessions",
                json={"topic": "体验版深度模式", "description": "测试", "interview_mode": "deep"},
            )
            self.assertEqual(deep_resp.status_code, 403, deep_resp.get_data(as_text=True))
            deep_payload = deep_resp.get_json() or {}
            self.assertEqual("level_capability_denied", deep_payload.get("error_code"))
            self.assertEqual("interview.mode.deep", deep_payload.get("capability_key"))
            self.assertEqual("professional", (deep_payload.get("required_level") or {}).get("key"))
        finally:
            self.server.is_license_protected_route = original_is_license_protected_route

    def test_standard_user_cannot_create_deep_session(self):
        self._register()
        standard_code = self._generate_license_batch(level_key="standard", note="标准版访谈模式")["licenses"][0]["code"]
        activate_payload = self._activate_license(standard_code)
        self.assertEqual("standard", (activate_payload.get("level") or {}).get("key"))

        me_payload = self.client.get("/api/auth/me").get_json() or {}
        self.assertEqual(["quick", "standard"], me_payload.get("allowed_interview_modes"))
        self.assertEqual("standard", me_payload.get("interview_mode_default"))

        deep_resp = self.client.post(
            "/api/sessions",
            json={"topic": "标准版深度模式", "description": "测试", "interview_mode": "deep"},
        )
        self.assertEqual(deep_resp.status_code, 403, deep_resp.get_data(as_text=True))
        payload = deep_resp.get_json() or {}
        self.assertEqual("level_capability_denied", payload.get("error_code"))
        self.assertEqual("interview.mode.deep", payload.get("capability_key"))
        self.assertEqual("standard", (payload.get("current_level") or {}).get("key"))
        self.assertEqual("professional", (payload.get("required_level") or {}).get("key"))

    def test_license_activation_and_status_summary(self):
        self._register()

        current_before = self.client.get("/api/licenses/current")
        self.assertEqual(current_before.status_code, 200, current_before.get_data(as_text=True))
        current_before_payload = current_before.get_json()
        self.assertFalse(current_before_payload.get("has_valid_license"))
        self.assertEqual("missing", current_before_payload.get("status"))

        generated = self._generate_license_batch()
        code = generated["licenses"][0]["code"]

        activate_resp = self.client.post("/api/licenses/activate", json={"code": code})
        self.assertEqual(activate_resp.status_code, 200, activate_resp.get_data(as_text=True))
        activate_payload = activate_resp.get_json()
        self.assertTrue(activate_payload.get("has_valid_license"))
        self.assertEqual("active", activate_payload.get("status"))
        self.assertEqual("standard", (activate_payload.get("level") or {}).get("key"))
        self.assertEqual(["balanced"], activate_payload.get("allowed_report_profiles"))
        self.assertTrue((activate_payload.get("license") or {}).get("masked_code"))
        self.assertEqual(30, (activate_payload.get("license") or {}).get("duration_days"))
        self.assertEqual("standard", (activate_payload.get("license") or {}).get("level_key"))
        self.assertTrue((activate_payload.get("license") or {}).get("not_before_at"))
        self.assertTrue((activate_payload.get("license") or {}).get("expires_at"))

        current_after = self.client.get("/api/licenses/current")
        self.assertEqual(current_after.status_code, 200, current_after.get_data(as_text=True))
        current_after_payload = current_after.get_json()
        self.assertTrue(current_after_payload.get("has_valid_license"))
        self.assertEqual("active", current_after_payload.get("status"))
        self.assertEqual("standard", (current_after_payload.get("level") or {}).get("key"))
        self.assertEqual("standard", (current_after_payload.get("license") or {}).get("level_key"))

        status_resp = self.client.get("/api/status")
        self.assertEqual(status_resp.status_code, 200, status_resp.get_data(as_text=True))
        status_payload = status_resp.get_json()
        self.assertIn("license", status_payload)
        self.assertTrue(status_payload["license"].get("has_valid_license"))
        self.assertEqual("active", status_payload["license"].get("status"))
        self.assertEqual("standard", (status_payload.get("level") or {}).get("key"))
        self.assertEqual(["balanced"], status_payload.get("allowed_report_profiles"))
        self.assertEqual(["balanced"], status_payload.get("report_profile_options"))
        self.assertEqual("standard", (status_payload["license"].get("license") or {}).get("level_key"))

    def test_admin_license_routes_require_valid_license_even_when_gate_disabled(self):
        user = self._register()
        old_admin_ids = set(self.server.ADMIN_USER_IDS)
        old_admin_phones = set(self.server.ADMIN_PHONE_NUMBERS)
        try:
            self.server.ADMIN_USER_IDS = {int(user["id"])}
            self.server.ADMIN_PHONE_NUMBERS = set()

            denied_resp = self.client.post(
                "/api/admin/licenses/batch",
                json={
                    "count": 1,
                    "duration_days": 30,
                    "note": "管理员测试",
                },
            )
            self.assertEqual(denied_resp.status_code, 403, denied_resp.get_data(as_text=True))
            self.assertEqual("license_required", denied_resp.get_json().get("error_code"))

            activation_code = self._generate_license_batch(note="管理员激活")["licenses"][0]["code"]
            activate_resp = self.client.post("/api/licenses/activate", json={"code": activation_code})
            self.assertEqual(activate_resp.status_code, 200, activate_resp.get_data(as_text=True))

            batch_resp = self.client.post(
                "/api/admin/licenses/batch",
                json={
                    "count": 2,
                    "duration_days": 60,
                    "note": "管理员测试",
                },
            )
            self.assertEqual(batch_resp.status_code, 200, batch_resp.get_data(as_text=True))
            batch_payload = batch_resp.get_json()
            self.assertEqual(2, batch_payload.get("count"))
            self.assertEqual("standard", batch_payload.get("level_key"))
            self.assertEqual(2, len(batch_payload.get("licenses", [])))
            self.assertTrue(all(item.get("level_key") == "standard" for item in batch_payload.get("licenses", [])))

            list_resp = self.client.get(f"/api/admin/licenses?batch_id={batch_payload['batch_id']}")
            self.assertEqual(list_resp.status_code, 200, list_resp.get_data(as_text=True))
            self.assertEqual(2, list_resp.get_json().get("count"))
            self.assertTrue(all(item.get("level_key") == "standard" for item in list_resp.get_json().get("items", [])))
        finally:
            self.server.ADMIN_USER_IDS = old_admin_ids
            self.server.ADMIN_PHONE_NUMBERS = old_admin_phones

    def test_admin_can_toggle_license_enforcement_runtime(self):
        user = self._register()
        old_admin_ids = set(self.server.ADMIN_USER_IDS)
        old_admin_phones = set(self.server.ADMIN_PHONE_NUMBERS)
        old_get_env_file_path = self.server.get_admin_env_file_path
        env_path = self.server.DATA_DIR / f"license-enforcement-{uuid.uuid4().hex}.env"
        try:
            self.server.ADMIN_USER_IDS = {int(user["id"])}
            self.server.ADMIN_PHONE_NUMBERS = set()
            self.server.set_license_enforcement_override(None)
            env_path.write_text("LICENSE_ENFORCEMENT_ENABLED=false\n", encoding="utf-8")
            self.server.get_admin_env_file_path = lambda: env_path

            activation_code = self._generate_license_batch(note="管理员开关激活")["licenses"][0]["code"]
            activate_resp = self.client.post("/api/licenses/activate", json={"code": activation_code})
            self.assertEqual(activate_resp.status_code, 200, activate_resp.get_data(as_text=True))

            current_setting_resp = self.client.get("/api/admin/license-enforcement")
            self.assertEqual(current_setting_resp.status_code, 200, current_setting_resp.get_data(as_text=True))
            self.assertFalse(current_setting_resp.get_json().get("enabled"))
            self.assertEqual("env_default", current_setting_resp.get_json().get("source"))

            enable_resp = self.client.post("/api/admin/license-enforcement", json={"enabled": True, "sync_default": True})
            self.assertEqual(enable_resp.status_code, 200, enable_resp.get_data(as_text=True))
            enable_payload = enable_resp.get_json()
            self.assertTrue(enable_payload.get("enabled"))
            self.assertEqual("runtime_override", enable_payload.get("source"))
            self.assertEqual(int(user["id"]), enable_payload.get("updated_by_user_id"))
            self.assertTrue(enable_payload.get("default_enabled"))
            self.assertTrue(enable_payload.get("default_sync_written"))
            self.assertIn("LICENSE_ENFORCEMENT_ENABLED=true", env_path.read_text(encoding="utf-8"))

            status_resp = self.client.get("/api/status")
            self.assertEqual(status_resp.status_code, 200, status_resp.get_data(as_text=True))
            self.assertTrue(status_resp.get_json().get("license_enforcement_enabled"))
            self.assertEqual("runtime_override", status_resp.get_json().get("license_enforcement_source"))

            other_client = self.server.app.test_client()
            self._register(client=other_client)
            blocked_resp = other_client.post("/api/sessions", json={"topic": "运行时开关拦截"})
            self.assertEqual(blocked_resp.status_code, 403, blocked_resp.get_data(as_text=True))
            self.assertEqual("license_required", blocked_resp.get_json().get("error_code"))

            follow_resp = self.client.post("/api/admin/license-enforcement/follow-default", json={})
            self.assertEqual(follow_resp.status_code, 200, follow_resp.get_data(as_text=True))
            follow_payload = follow_resp.get_json()
            self.assertTrue(follow_payload.get("enabled"))
            self.assertEqual("env_default", follow_payload.get("source"))
            self.assertIsNone(follow_payload.get("override_enabled"))

            env_path.write_text("LICENSE_ENFORCEMENT_ENABLED=false\n", encoding="utf-8")
            synced_setting_resp = self.client.get("/api/admin/license-enforcement")
            self.assertEqual(synced_setting_resp.status_code, 200, synced_setting_resp.get_data(as_text=True))
            self.assertFalse(synced_setting_resp.get_json().get("enabled"))
            self.assertFalse(synced_setting_resp.get_json().get("default_enabled"))
            self.assertEqual("env_default", synced_setting_resp.get_json().get("source"))

            unblocked_resp = other_client.post("/api/sessions", json={"topic": "运行时开关放行"})
            self.assertEqual(unblocked_resp.status_code, 200, unblocked_resp.get_data(as_text=True))
        finally:
            self.server.set_license_enforcement_override(None)
            self.server.ADMIN_USER_IDS = old_admin_ids
            self.server.ADMIN_PHONE_NUMBERS = old_admin_phones
            self.server.get_admin_env_file_path = old_get_env_file_path

    def test_admin_license_management_endpoints_cover_summary_detail_search_and_bulk_actions(self):
        user = self._register()
        old_admin_ids = set(self.server.ADMIN_USER_IDS)
        old_admin_phones = set(self.server.ADMIN_PHONE_NUMBERS)
        try:
            self.server.ADMIN_USER_IDS = {int(user["id"])}
            self.server.ADMIN_PHONE_NUMBERS = set()

            activation_code = self._generate_license_batch(note="管理员 License 管理激活")["licenses"][0]["code"]
            activate_resp = self.client.post("/api/licenses/activate", json={"code": activation_code})
            self.assertEqual(activate_resp.status_code, 200, activate_resp.get_data(as_text=True))

            generated = self._generate_license_batch(count=3, note="后台测试批次")
            generated_ids = [int(item["id"]) for item in generated["licenses"]]
            raw_code = generated["licenses"][0]["code"]

            summary_resp = self.client.get("/api/admin/licenses/summary")
            self.assertEqual(summary_resp.status_code, 200, summary_resp.get_data(as_text=True))
            summary_payload = summary_resp.get_json()
            self.assertIn("counts", summary_payload)
            self.assertIn("recent_events", summary_payload)
            self.assertGreaterEqual(summary_payload.get("total", 0), 4)

            query_resp = self.client.get(f"/api/admin/licenses?code={quote(raw_code)}")
            self.assertEqual(query_resp.status_code, 200, query_resp.get_data(as_text=True))
            query_payload = query_resp.get_json()
            self.assertEqual(1, query_payload.get("count"))
            queried_item = query_payload["items"][0]
            self.assertEqual(generated_ids[0], queried_item["id"])
            self.assertEqual("standard", queried_item.get("level_key"))
            self.assertNotEqual(raw_code, queried_item["masked_code"])
            self.assertNotIn("code", queried_item)

            sorted_resp = self.client.get(
                f"/api/admin/licenses?batch_id={quote(generated['batch_id'])}&sort_by=id&sort_order=asc&page_size=2&page=2"
            )
            self.assertEqual(sorted_resp.status_code, 200, sorted_resp.get_data(as_text=True))
            sorted_payload = sorted_resp.get_json()
            self.assertEqual(3, sorted_payload.get("count"))
            self.assertEqual(2, sorted_payload.get("total_pages"))
            self.assertEqual(2, sorted_payload.get("page"))
            self.assertEqual("id", sorted_payload.get("sort_by"))
            self.assertEqual("asc", sorted_payload.get("sort_order"))
            self.assertEqual(1, len(sorted_payload.get("items", [])))
            self.assertEqual(max(generated_ids), sorted_payload["items"][0]["id"])

            detail_resp = self.client.get(f"/api/admin/licenses/{generated_ids[0]}")
            self.assertEqual(detail_resp.status_code, 200, detail_resp.get_data(as_text=True))
            detail_payload = detail_resp.get_json()
            self.assertEqual(generated_ids[0], detail_payload["id"])
            self.assertEqual("后台测试批次", detail_payload["note"])
            self.assertEqual("standard", detail_payload.get("level_key"))

            events_resp = self.client.get(f"/api/admin/licenses/{generated_ids[0]}/events")
            self.assertEqual(events_resp.status_code, 200, events_resp.get_data(as_text=True))
            events_payload = events_resp.get_json()
            self.assertTrue(any(item.get("event_type") == "generated" for item in events_payload.get("items", [])))

            extend_resp = self.client.post(
                "/api/admin/licenses/bulk-extend",
                json={"license_ids": generated_ids[:2], "duration_days": 90},
            )
            self.assertEqual(extend_resp.status_code, 200, extend_resp.get_data(as_text=True))
            extend_payload = extend_resp.get_json()
            self.assertEqual(2, len(extend_payload.get("succeeded", [])))
            self.assertEqual([], extend_payload.get("failed", []))
            self.assertTrue(all(item.get("duration_days") == 90 for item in extend_payload.get("succeeded", [])))

            revoke_resp = self.client.post(
                "/api/admin/licenses/bulk-revoke",
                json={"license_ids": [generated_ids[2]], "reason": "批量撤销测试"},
            )
            self.assertEqual(revoke_resp.status_code, 200, revoke_resp.get_data(as_text=True))
            revoke_payload = revoke_resp.get_json()
            self.assertEqual(1, len(revoke_payload.get("succeeded", [])))
            self.assertEqual("revoked", revoke_payload["succeeded"][0]["status"])

            revoked_detail = self.client.get(f"/api/admin/licenses/{generated_ids[2]}")
            self.assertEqual(revoked_detail.status_code, 200, revoked_detail.get_data(as_text=True))
            self.assertEqual("revoked", revoked_detail.get_json().get("status"))
            self.assertEqual("批量撤销测试", revoked_detail.get_json().get("revoked_reason"))
        finally:
            self.server.ADMIN_USER_IDS = old_admin_ids
            self.server.ADMIN_PHONE_NUMBERS = old_admin_phones

    def test_admin_generate_license_batch_can_assign_professional_level(self):
        user = self._register()
        old_admin_ids = set(self.server.ADMIN_USER_IDS)
        old_admin_phones = set(self.server.ADMIN_PHONE_NUMBERS)
        try:
            self.server.ADMIN_USER_IDS = {int(user["id"])}
            self.server.ADMIN_PHONE_NUMBERS = set()

            activation_code = self._generate_license_batch(note="管理员专业版激活")["licenses"][0]["code"]
            activate_resp = self.client.post("/api/licenses/activate", json={"code": activation_code})
            self.assertEqual(activate_resp.status_code, 200, activate_resp.get_data(as_text=True))

            batch_resp = self.client.post(
                "/api/admin/licenses/batch",
                json={
                    "count": 2,
                    "duration_days": 90,
                    "level_key": "professional",
                    "note": "专业版批次",
                },
            )
            self.assertEqual(batch_resp.status_code, 200, batch_resp.get_data(as_text=True))
            batch_payload = batch_resp.get_json()
            self.assertEqual("professional", batch_payload.get("level_key"))
            self.assertEqual("专业版", batch_payload.get("level_name"))
            self.assertTrue(all(item.get("level_key") == "professional" for item in batch_payload.get("licenses", [])))

            list_resp = self.client.get(f"/api/admin/licenses?batch_id={batch_payload['batch_id']}&level_key=professional")
            self.assertEqual(list_resp.status_code, 200, list_resp.get_data(as_text=True))
            list_payload = list_resp.get_json()
            self.assertEqual(2, list_payload.get("count"))
            self.assertTrue(all(item.get("level_key") == "professional" for item in list_payload.get("items", [])))

            detail_resp = self.client.get(f"/api/admin/licenses/{batch_payload['licenses'][0]['id']}")
            self.assertEqual(detail_resp.status_code, 200, detail_resp.get_data(as_text=True))
            self.assertEqual("professional", detail_resp.get_json().get("level_key"))
        finally:
            self.server.ADMIN_USER_IDS = old_admin_ids
            self.server.ADMIN_PHONE_NUMBERS = old_admin_phones

    def test_init_license_db_migrates_legacy_licenses_without_level_key_to_standard(self):
        old_auth_dir = self.server.AUTH_DIR
        old_auth_db_path = self.server.AUTH_DB_PATH
        old_license_db_path = self.server.LICENSE_DB_PATH
        legacy_auth_dir = self.server.DATA_DIR / f"legacy-auth-{uuid.uuid4().hex}"
        legacy_auth_db = legacy_auth_dir / "users.db"
        legacy_license_db = legacy_auth_dir / "licenses.db"
        now = datetime.utcnow().replace(microsecond=0).isoformat()
        try:
            legacy_auth_dir.mkdir(parents=True, exist_ok=True)
            self.server.AUTH_DIR = legacy_auth_dir
            self.server.AUTH_DB_PATH = legacy_auth_db
            self.server.LICENSE_DB_PATH = legacy_license_db
            self.server._clear_cached_license_signing_secret()
            self.server.init_auth_db()

            with self.server.get_auth_db_connection() as conn:
                conn.execute(
                    """
                    CREATE TABLE licenses (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        batch_id TEXT NOT NULL,
                        code_hash TEXT NOT NULL UNIQUE,
                        code_mask TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'issued',
                        not_before_at TEXT NOT NULL,
                        expires_at TEXT NOT NULL,
                        duration_days INTEGER NOT NULL DEFAULT 0,
                        bound_user_id INTEGER,
                        bound_at TEXT,
                        replaced_by_license_id INTEGER,
                        revoked_at TEXT,
                        revoked_reason TEXT NOT NULL DEFAULT '',
                        note TEXT NOT NULL DEFAULT '',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE license_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        license_id INTEGER,
                        actor_user_id INTEGER,
                        event_type TEXT NOT NULL,
                        payload_json TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    INSERT INTO licenses (
                        id, batch_id, code_hash, code_mask, status, not_before_at, expires_at, duration_days,
                        bound_user_id, bound_at, replaced_by_license_id, revoked_at, revoked_reason, note,
                        created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        1,
                        "legacy-batch",
                        "legacy-hash",
                        "DV-LEGACY",
                        "active",
                        now,
                        now,
                        30,
                        9,
                        now,
                        None,
                        None,
                        "",
                        "旧版 License",
                        now,
                        now,
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO license_events (id, license_id, actor_user_id, event_type, payload_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (1, 1, 9, "activated", '{"source":"legacy"}', now),
                )
                conn.executemany(
                    """
                    INSERT INTO auth_meta (meta_key, meta_value, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(meta_key) DO UPDATE SET
                        meta_value = excluded.meta_value,
                        updated_at = excluded.updated_at
                    """,
                    [
                        (self.server.AUTH_META_LICENSE_SIGNING_SECRET_KEY, "legacy-secret", now),
                        (self.server.AUTH_META_LICENSE_ENFORCEMENT_ENABLED_KEY, "true", now),
                    ],
                )
                conn.commit()

            self.server.init_license_db()

            with self.server.get_license_db_connection() as conn:
                license_row = conn.execute(
                    "SELECT id, status, level_key, bound_user_id, note FROM licenses WHERE id = 1"
                ).fetchone()
                event_row = conn.execute(
                    "SELECT license_id, actor_user_id, event_type, payload_json FROM license_events WHERE id = 1"
                ).fetchone()
                meta_rows = conn.execute(
                    """
                    SELECT meta_key, meta_value
                    FROM auth_meta
                    WHERE meta_key IN (?, ?)
                    ORDER BY meta_key ASC
                    """,
                    (
                        self.server.AUTH_META_LICENSE_ENFORCEMENT_ENABLED_KEY,
                        self.server.AUTH_META_LICENSE_SIGNING_SECRET_KEY,
                    ),
                ).fetchall()

            self.assertIsNotNone(license_row)
            self.assertEqual("active", license_row["status"])
            self.assertEqual("standard", license_row["level_key"])
            self.assertEqual(9, int(license_row["bound_user_id"] or 0))
            self.assertEqual("旧版 License", license_row["note"])
            self.assertIsNotNone(event_row)
            self.assertEqual(1, int(event_row["license_id"] or 0))
            self.assertEqual(9, int(event_row["actor_user_id"] or 0))
            self.assertEqual("activated", event_row["event_type"])
            self.assertEqual('{"source":"legacy"}', event_row["payload_json"])
            meta_payload = {str(row["meta_key"]): str(row["meta_value"]) for row in meta_rows}
            self.assertEqual("legacy-secret", meta_payload.get(self.server.AUTH_META_LICENSE_SIGNING_SECRET_KEY))
            self.assertEqual("true", meta_payload.get(self.server.AUTH_META_LICENSE_ENFORCEMENT_ENABLED_KEY))
        finally:
            self.server.AUTH_DIR = old_auth_dir
            self.server.AUTH_DB_PATH = old_auth_db_path
            self.server.LICENSE_DB_PATH = old_license_db_path
            self.server._clear_cached_license_signing_secret()
            self.server.init_auth_db()
            self.server.init_license_db()

    def test_init_license_db_preserves_legacy_level_key_from_auth_db(self):
        old_auth_dir = self.server.AUTH_DIR
        old_auth_db_path = self.server.AUTH_DB_PATH
        old_license_db_path = self.server.LICENSE_DB_PATH
        legacy_auth_dir = self.server.DATA_DIR / f"legacy-auth-{uuid.uuid4().hex}"
        legacy_auth_db = legacy_auth_dir / "users.db"
        legacy_license_db = legacy_auth_dir / "licenses.db"
        now = datetime.utcnow().replace(microsecond=0).isoformat()
        try:
            legacy_auth_dir.mkdir(parents=True, exist_ok=True)
            self.server.AUTH_DIR = legacy_auth_dir
            self.server.AUTH_DB_PATH = legacy_auth_db
            self.server.LICENSE_DB_PATH = legacy_license_db
            self.server._clear_cached_license_signing_secret()
            self.server.init_auth_db()

            with self.server.get_auth_db_connection() as conn:
                conn.execute(
                    """
                    CREATE TABLE licenses (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        batch_id TEXT NOT NULL,
                        code_hash TEXT NOT NULL UNIQUE,
                        code_mask TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'issued',
                        level_key TEXT NOT NULL DEFAULT 'standard',
                        not_before_at TEXT NOT NULL,
                        expires_at TEXT NOT NULL,
                        duration_days INTEGER NOT NULL DEFAULT 0,
                        bound_user_id INTEGER,
                        bound_at TEXT,
                        replaced_by_license_id INTEGER,
                        revoked_at TEXT,
                        revoked_reason TEXT NOT NULL DEFAULT '',
                        note TEXT NOT NULL DEFAULT '',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    INSERT INTO licenses (
                        id, batch_id, code_hash, code_mask, status, level_key, not_before_at, expires_at, duration_days,
                        bound_user_id, bound_at, replaced_by_license_id, revoked_at, revoked_reason, note,
                        created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        7,
                        "legacy-pro-batch",
                        "legacy-pro-hash",
                        "DV-PRO",
                        "issued",
                        "professional",
                        now,
                        now,
                        90,
                        None,
                        None,
                        None,
                        None,
                        "",
                        "旧版专业版 License",
                        now,
                        now,
                    ),
                )
                conn.commit()

            self.server.init_license_db()

            with self.server.get_license_db_connection() as conn:
                license_row = conn.execute(
                    "SELECT id, level_key, duration_days, note FROM licenses WHERE id = 7"
                ).fetchone()

            self.assertIsNotNone(license_row)
            self.assertEqual("professional", license_row["level_key"])
            self.assertEqual(90, int(license_row["duration_days"] or 0))
            self.assertEqual("旧版专业版 License", license_row["note"])
        finally:
            self.server.AUTH_DIR = old_auth_dir
            self.server.AUTH_DB_PATH = old_auth_db_path
            self.server.LICENSE_DB_PATH = old_license_db_path
            self.server._clear_cached_license_signing_secret()
            self.server.init_auth_db()
            self.server.init_license_db()

    def test_admin_can_bootstrap_first_seed_license_without_existing_license(self):
        old_admin_ids = set(self.server.ADMIN_USER_IDS)
        old_admin_phones = set(self.server.ADMIN_PHONE_NUMBERS)
        old_auth_dir = self.server.AUTH_DIR
        old_auth_db_path = self.server.AUTH_DB_PATH
        old_license_db_path = self.server.LICENSE_DB_PATH
        old_enforcement_enabled = self.server.LICENSE_ENFORCEMENT_ENABLED
        bootstrap_auth_dir = self.server.DATA_DIR / f"bootstrap-auth-{uuid.uuid4().hex}"
        bootstrap_auth_db = bootstrap_auth_dir / "users.db"
        bootstrap_license_db = bootstrap_auth_dir / "licenses.db"
        try:
            bootstrap_auth_dir.mkdir(parents=True, exist_ok=True)
            self.server.AUTH_DIR = bootstrap_auth_dir
            self.server.AUTH_DB_PATH = bootstrap_auth_db
            self.server.LICENSE_DB_PATH = bootstrap_license_db
            self.server.init_auth_db()
            self.server.init_license_db()
            self.server.LICENSE_ENFORCEMENT_ENABLED = True

            client = self.server.app.test_client()
            user = self._register(client=client)
            self.server.ADMIN_USER_IDS = {int(user["id"])}
            self.server.ADMIN_PHONE_NUMBERS = set()

            status_resp = client.get("/api/admin/licenses/bootstrap/status")
            self.assertEqual(status_resp.status_code, 200, status_resp.get_data(as_text=True))
            status_payload = status_resp.get_json()
            self.assertTrue(status_payload.get("eligible"))
            self.assertEqual("seed_available", status_payload.get("reason"))
            self.assertEqual(0, status_payload.get("total_license_count"))

            bootstrap_resp = client.post(
                "/api/admin/licenses/bootstrap",
                json={
                    "duration_days": 365,
                    "note": "首个种子 License 测试",
                },
            )
            self.assertEqual(bootstrap_resp.status_code, 200, bootstrap_resp.get_data(as_text=True))
            bootstrap_payload = bootstrap_resp.get_json()
            self.assertTrue(bootstrap_payload.get("has_valid_license"))
            self.assertEqual("active", bootstrap_payload.get("status"))
            self.assertTrue(bootstrap_payload.get("bootstrap_seeded"))
            self.assertTrue(bootstrap_payload.get("license", {}).get("masked_code"))

            post_status_resp = client.get("/api/admin/licenses/bootstrap/status")
            self.assertEqual(post_status_resp.status_code, 200, post_status_resp.get_data(as_text=True))
            self.assertEqual("already_has_valid_license", post_status_resp.get_json().get("reason"))

            summary_resp = client.get("/api/admin/licenses/summary")
            self.assertEqual(summary_resp.status_code, 200, summary_resp.get_data(as_text=True))
            self.assertGreaterEqual(summary_resp.get_json().get("total", 0), 1)
        finally:
            self.server.ADMIN_USER_IDS = old_admin_ids
            self.server.ADMIN_PHONE_NUMBERS = old_admin_phones
            self.server.AUTH_DIR = old_auth_dir
            self.server.AUTH_DB_PATH = old_auth_db_path
            self.server.LICENSE_DB_PATH = old_license_db_path
            self.server.LICENSE_ENFORCEMENT_ENABLED = old_enforcement_enabled
            self.server._clear_cached_license_signing_secret()
            self.server.init_auth_db()
            self.server.init_license_db()

    def test_admin_ownership_migration_endpoints_cover_search_preview_apply_and_rollback(self):
        admin_user = self._register()
        target_client = self.server.app.test_client()
        target_user = self._register(client=target_client)
        old_admin_ids = set(self.server.ADMIN_USER_IDS)
        old_admin_phones = set(self.server.ADMIN_PHONE_NUMBERS)
        old_sessions_dir = self.server.SESSIONS_DIR
        old_reports_dir = self.server.REPORTS_DIR
        old_report_owners_file = self.server.REPORT_OWNERS_FILE
        old_report_scopes_file = self.server.REPORT_SCOPES_FILE
        old_deleted_reports_file = self.server.DELETED_REPORTS_FILE
        old_report_solution_shares_file = self.server.REPORT_SOLUTION_SHARES_FILE
        old_get_admin_meta_index_db_target = self.server._get_admin_meta_index_db_target
        old_use_postgres_shared_meta_storage = self.server._use_postgres_shared_meta_storage
        try:
            self.server.ADMIN_USER_IDS = {int(admin_user["id"])}
            self.server.ADMIN_PHONE_NUMBERS = set()
            self.server._get_admin_meta_index_db_target = lambda: None
            self.server._use_postgres_shared_meta_storage = lambda: False
            activation_code = self._generate_license_batch(note="归属迁移管理员 License")["licenses"][0]["code"]
            ok, status_code, payload = self.server.activate_license_for_user(activation_code, int(admin_user["id"]))
            self.assertTrue(ok, payload)
            self.assertEqual(200, status_code)

            isolated_root = self.server.DATA_DIR / f"ownership-migration-{uuid.uuid4().hex}"
            isolated_sessions_dir = isolated_root / "sessions"
            isolated_reports_dir = isolated_root / "reports"
            isolated_sessions_dir.mkdir(parents=True, exist_ok=True)
            isolated_reports_dir.mkdir(parents=True, exist_ok=True)
            self.server.SESSIONS_DIR = isolated_sessions_dir
            self.server.REPORTS_DIR = isolated_reports_dir
            self.server.REPORT_OWNERS_FILE = isolated_reports_dir / ".owners.json"
            self.server.REPORT_SCOPES_FILE = isolated_reports_dir / ".scopes.json"
            self.server.DELETED_REPORTS_FILE = isolated_reports_dir / ".deleted_reports.json"
            self.server.REPORT_SOLUTION_SHARES_FILE = isolated_reports_dir / ".solution_shares.json"
            self.server.report_owners_cache["signature"] = None
            self.server.report_owners_cache["data"] = {}
            self.server.report_scopes_cache["signature"] = None
            self.server.report_scopes_cache["data"] = {}
            self.server.report_solution_shares_cache["signature"] = None
            self.server.report_solution_shares_cache["data"] = {}

            session_file = self.server.SESSIONS_DIR / "ownership-preview-session.json"
            session_file.write_text(
                json.dumps(
                    {
                        "session_id": "ownership-preview-session",
                        "topic": "迁移预览会话",
                        "owner_user_id": 0,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            report_name = "ownership-preview-report.md"
            (self.server.REPORTS_DIR / report_name).write_text("# 测试报告\n", encoding="utf-8")

            user_search = self.client.get(f"/api/admin/users?q={target_user['account']}")
            self.assertEqual(user_search.status_code, 200, user_search.get_data(as_text=True))
            self.assertTrue(any(item.get("id") == int(target_user["id"]) for item in user_search.get_json().get("items", [])))

            audit_before = self.client.post(
                "/api/admin/ownership-migrations/audit",
                json={"user_id": int(target_user["id"]), "kinds": ["sessions", "reports"]},
            )
            self.assertEqual(audit_before.status_code, 200, audit_before.get_data(as_text=True))
            self.assertEqual(0, audit_before.get_json()["sessions"]["owned"])
            self.assertEqual(0, audit_before.get_json()["reports"]["owned"])

            preview_resp = self.client.post(
                "/api/admin/ownership-migrations/preview",
                json={
                    "to_user_id": int(target_user["id"]),
                    "scope": "unowned",
                    "kinds": ["sessions", "reports"],
                    "max_examples": 5,
                },
            )
            self.assertEqual(preview_resp.status_code, 200, preview_resp.get_data(as_text=True))
            preview_payload = preview_resp.get_json()
            self.assertEqual("dry-run", preview_payload["summary"]["mode"])
            self.assertEqual(1, preview_payload["summary"]["sessions"]["matched"])
            self.assertEqual(1, preview_payload["summary"]["reports"]["matched"])
            self.assertTrue(preview_payload.get("preview_token"))
            self.assertTrue(preview_payload.get("confirm_phrase"))

            wrong_apply = self.client.post(
                "/api/admin/ownership-migrations/apply",
                json={
                    "to_user_id": int(target_user["id"]),
                    "scope": "unowned",
                    "kinds": ["sessions", "reports"],
                    "max_examples": 5,
                    "preview_token": preview_payload["preview_token"],
                    "confirm_text": "确认词错误",
                },
            )
            self.assertEqual(wrong_apply.status_code, 400, wrong_apply.get_data(as_text=True))

            apply_resp = self.client.post(
                "/api/admin/ownership-migrations/apply",
                json={
                    "to_user_id": int(target_user["id"]),
                    "scope": "unowned",
                    "kinds": ["sessions", "reports"],
                    "max_examples": 5,
                    "preview_token": preview_payload["preview_token"],
                    "confirm_text": preview_payload["confirm_phrase"],
                },
            )
            self.assertEqual(apply_resp.status_code, 200, apply_resp.get_data(as_text=True))
            apply_payload = apply_resp.get_json()
            self.assertEqual("apply", apply_payload["summary"]["mode"])
            self.assertTrue(apply_payload["summary"]["backup_dir"])

            migrated_session = json.loads(session_file.read_text(encoding="utf-8"))
            self.assertEqual(int(target_user["id"]), migrated_session["owner_user_id"])
            report_owners_payload = json.loads(self.server.REPORT_OWNERS_FILE.read_text(encoding="utf-8"))
            self.assertEqual(int(target_user["id"]), int(report_owners_payload[report_name]))

            audit_after = self.client.post(
                "/api/admin/ownership-migrations/audit",
                json={"user_id": int(target_user["id"]), "kinds": ["sessions", "reports"]},
            )
            self.assertEqual(audit_after.status_code, 200, audit_after.get_data(as_text=True))
            self.assertEqual(1, audit_after.get_json()["sessions"]["owned"])
            self.assertEqual(1, audit_after.get_json()["reports"]["owned"])

            history_resp = self.client.get("/api/admin/ownership-migrations")
            self.assertEqual(history_resp.status_code, 200, history_resp.get_data(as_text=True))
            history_payload = history_resp.get_json()
            self.assertGreaterEqual(history_payload.get("count", 0), 1)
            backup_id = history_payload["items"][0]["backup_id"]
            self.assertTrue(backup_id)

            rollback_resp = self.client.post(
                "/api/admin/ownership-migrations/rollback",
                json={"backup_id": backup_id},
            )
            self.assertEqual(rollback_resp.status_code, 200, rollback_resp.get_data(as_text=True))
            rollback_payload = rollback_resp.get_json()
            self.assertEqual(backup_id, rollback_payload["backup_id"])

            rolled_back_session = json.loads(session_file.read_text(encoding="utf-8"))
            self.assertEqual(0, rolled_back_session["owner_user_id"])
            self.assertFalse(self.server.REPORT_OWNERS_FILE.exists())
        finally:
            self.server.ADMIN_USER_IDS = old_admin_ids
            self.server.ADMIN_PHONE_NUMBERS = old_admin_phones
            self.server.SESSIONS_DIR = old_sessions_dir
            self.server.REPORTS_DIR = old_reports_dir
            self.server.REPORT_OWNERS_FILE = old_report_owners_file
            self.server.REPORT_SCOPES_FILE = old_report_scopes_file
            self.server.DELETED_REPORTS_FILE = old_deleted_reports_file
            self.server.REPORT_SOLUTION_SHARES_FILE = old_report_solution_shares_file
            self.server._get_admin_meta_index_db_target = old_get_admin_meta_index_db_target
            self.server._use_postgres_shared_meta_storage = old_use_postgres_shared_meta_storage
            self.server.report_owners_cache["signature"] = None
            self.server.report_owners_cache["data"] = {}
            self.server.report_scopes_cache["signature"] = None
            self.server.report_scopes_cache["data"] = {}
            self.server.report_solution_shares_cache["signature"] = None
            self.server.report_solution_shares_cache["data"] = {}

    def test_admin_config_center_endpoints_cover_catalog_and_file_persistence(self):
        admin_user = self._register()
        old_admin_ids = set(self.server.ADMIN_USER_IDS)
        old_admin_phones = set(self.server.ADMIN_PHONE_NUMBERS)
        old_get_env_file_path = self.server.get_admin_env_file_path
        old_get_config_file_path = self.server.get_admin_config_file_path
        old_get_site_config_file_path = self.server.get_admin_site_config_file_path
        old_runtime_config = self.server.runtime_config
        env_path = self.server.DATA_DIR / "admin-center.env"
        config_path = self.server.DATA_DIR / "admin-center-config.py"
        site_config_path = self.server.DATA_DIR / "admin-center-site-config.js"
        env_path.write_text(
            "\n".join(
                [
                    "ENABLE_AI=false",
                    "SERVER_PORT=5001",
                    "SECRET_KEY=env-secret",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        config_path.write_text(
            "\n".join(
                [
                    'MODEL_NAME = "legacy-model"',
                    "REPORT_V3_PROFILE = 'balanced'",
                    "OTHER_UNRELATED_FLAG = True",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        site_config_path.write_text(
            "\n".join(
                [
                    "const SITE_CONFIG = {",
                    '  quotes: { enabled: true, interval: 5000, items: [{ text: "旧诗句", source: "——旧来源" }] },',
                    '  researchTips: ["旧提示"],',
                    '  colors: { primary: "#357BE2", success: "#22C55E", progressComplete: "#357BE2" },',
                    '  theme: { defaultMode: "system" },',
                    '  visualPresets: { default: "rational", locked: true, options: { rational: { label: "科技理性" } } },',
                    '  designTokens: { light: { colors: { brand: "#357BE2" } }, dark: { colors: { brand: "#5C98FF" } } },',
                    '  motion: { durations: { fast: 140, base: 180, slow: 240, progress: 420 }, easing: { standard: "ease", emphasized: "ease-in-out" }, reducedMotion: { disableTypingEffect: true, disableNonEssentialPulse: true } },',
                    '  a11y: { minContrastAA: 4.5, toast: { defaultLive: "polite", errorLive: "assertive" }, dialogs: {} },',
                    '  api: { baseUrl: "http://localhost:5001/api", webSearchPollInterval: 200 },',
                    '  version: { configFile: "version.json" },',
                    '  presentation: { enabled: false },',
                    '  solution: { enabled: true }',
                    "};",
                    "if (typeof module !== 'undefined' && module.exports) {",
                    "  module.exports = SITE_CONFIG;",
                    "}",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        try:
            self.server.ADMIN_USER_IDS = {int(admin_user["id"])}
            self.server.ADMIN_PHONE_NUMBERS = set()
            self.server.get_admin_env_file_path = lambda: env_path
            self.server.get_admin_config_file_path = lambda: config_path
            self.server.get_admin_site_config_file_path = lambda: site_config_path
            self.server.runtime_config = types.SimpleNamespace(
                MODEL_NAME="legacy-model",
                REPORT_V3_PROFILE="balanced",
            )

            catalog_resp = self.client.get("/api/admin/config-center")
            self.assertEqual(catalog_resp.status_code, 200, catalog_resp.get_data(as_text=True))
            catalog_payload = catalog_resp.get_json()
            self.assertIn("env", catalog_payload)
            self.assertIn("config", catalog_payload)
            self.assertIn("site", catalog_payload)
            self.assertTrue(any(group.get("id") == "env_resolution" for group in catalog_payload["env"]["groups"]))
            self.assertTrue(any(group.get("id") == "config_models" for group in catalog_payload["config"]["groups"]))
            self.assertTrue(any(group.get("id") == "config_observability_cache" for group in catalog_payload["config"]["groups"]))
            self.assertTrue(any(group.get("id") == "site_home_copy" for group in catalog_payload["site"]["groups"]))

            env_resolution_group = next(group for group in catalog_payload["env"]["groups"] if group.get("id") == "env_resolution")
            env_resolution_keys = {item.get("key") for item in env_resolution_group.get("items", [])}
            self.assertIn("AI_CLIENT_EAGER_INIT", env_resolution_keys)
            self.assertIn("AI_CLIENT_INIT_CONNECTION_TEST", env_resolution_keys)

            env_deploy_group = next(group for group in catalog_payload["env"]["groups"] if group.get("id") == "env_deploy")
            env_deploy_keys = {item.get("key") for item in env_deploy_group.get("items", [])}
            self.assertIn("GUNICORN_ACCESSLOG", env_deploy_keys)
            self.assertIn("GUNICORN_ERRORLOG", env_deploy_keys)

            config_observability_group = next(group for group in catalog_payload["config"]["groups"] if group.get("id") == "config_observability_cache")
            observability_items = {item.get("key"): item for item in config_observability_group.get("items", [])}
            self.assertIn("METRICS_ASYNC_BATCH_SIZE", observability_items)
            self.assertTrue(observability_items["METRICS_ASYNC_BATCH_SIZE"].get("advanced"))

            save_env_resp = self.client.post(
                "/api/admin/config-center/save",
                json={
                    "source": "env",
                    "group_id": "env_resolution",
                    "values": {
                        "CONFIG_RESOLUTION_MODE": "env_only",
                        "DEBUG_MODE": "false",
                        "ENABLE_AI": "true",
                        "ENABLE_WEB_SEARCH": "true",
                        "ENABLE_VISION": "false",
                        "ENABLE_DEBUG_LOG": "false",
                        "FOCUS_GENERATION_ACCESS_LOG": "true",
                        "SUPPRESS_STATUS_POLL_ACCESS_LOG": "true",
                        "LICENSE_ENFORCEMENT_ENABLED": "false",
                    },
                },
            )
            self.assertEqual(save_env_resp.status_code, 200, save_env_resp.get_data(as_text=True))
            env_text = env_path.read_text(encoding="utf-8")
            self.assertIn("CONFIG_RESOLUTION_MODE=env_only", env_text)
            self.assertIn("ENABLE_AI=true", env_text)
            self.assertIn("ENABLE_WEB_SEARCH=true", env_text)
            self.assertIn("DEBUG_MODE=false", env_text)

            save_config_resp = self.client.post(
                "/api/admin/config-center/save",
                json={
                    "source": "config",
                    "group_id": "config_models",
                    "values": {
                        "MODEL_NAME": "gpt-5.4",
                        "QUESTION_MODEL_NAME": "gpt-5.4",
                        "REPORT_MODEL_NAME": "gpt-5.4-mini",
                    },
                },
            )
            self.assertEqual(save_config_resp.status_code, 200, save_config_resp.get_data(as_text=True))
            config_text = config_path.read_text(encoding="utf-8")
            self.assertIn("OTHER_UNRELATED_FLAG = True", config_text)
            self.assertIn("DEEPVISION ADMIN UI MANAGED CONFIG BEGIN", config_text)
            self.assertIn("MODEL_NAME = 'gpt-5.4'", config_text)
            self.assertIn("QUESTION_MODEL_NAME = 'gpt-5.4'", config_text)
            self.assertIn("REPORT_MODEL_NAME = 'gpt-5.4-mini'", config_text)

            refreshed_payload = save_config_resp.get_json().get("config_center", {})
            config_groups = refreshed_payload.get("config", {}).get("groups", [])
            config_models_group = next(group for group in config_groups if group.get("id") == "config_models")
            config_items = {item["key"]: item for item in config_models_group.get("items", [])}
            self.assertEqual("gpt-5.4", config_items["MODEL_NAME"]["value"])
            self.assertEqual("gpt-5.4-mini", config_items["REPORT_MODEL_NAME"]["value"])

            save_site_resp = self.client.post(
                "/api/admin/config-center/save",
                json={
                    "source": "site",
                    "group_id": "site_home_copy",
                    "values": {
                        "quotes.enabled": "false",
                        "quotes.interval": "3000",
                        "quotes.items": json.dumps(
                            [{"text": "新的诗句", "source": "——测试来源"}],
                            ensure_ascii=False,
                        ),
                        "researchTips": "第一条提示\n第二条提示",
                    },
                },
            )
            self.assertEqual(save_site_resp.status_code, 200, save_site_resp.get_data(as_text=True))
            site_save_payload = save_site_resp.get_json() or {}
            self.assertEqual("site", site_save_payload.get("source"))
            self.assertIn("site_config_store", site_save_payload.get("message", ""))
            saved_site_values = self.server.load_runtime_site_config_values()
            self.assertFalse(saved_site_values["quotes"]["enabled"])
            self.assertEqual(3000, saved_site_values["quotes"]["interval"])
            self.assertEqual("新的诗句", saved_site_values["quotes"]["items"][0]["text"])
            self.assertEqual(["第一条提示", "第二条提示"], saved_site_values["researchTips"])
            refreshed_site_payload = site_save_payload.get("config_center", {}).get("site", {})
            self.assertEqual("site_config_store", (refreshed_site_payload.get("file") or {}).get("storage"))
        finally:
            self.server.ADMIN_USER_IDS = old_admin_ids
            self.server.ADMIN_PHONE_NUMBERS = old_admin_phones
            self.server.get_admin_env_file_path = old_get_env_file_path
            self.server.get_admin_config_file_path = old_get_config_file_path
            self.server.get_admin_site_config_file_path = old_get_site_config_file_path
            self.server.runtime_config = old_runtime_config

    def test_wechat_auth_lifecycle_success(self):
        old_enabled = self.server.WECHAT_LOGIN_ENABLED
        old_app_id = self.server.WECHAT_APP_ID
        old_secret = self.server.WECHAT_APP_SECRET
        old_redirect = self.server.WECHAT_REDIRECT_URI
        old_scope = self.server.WECHAT_OAUTH_SCOPE
        old_exchange = self.server.exchange_wechat_code_for_token
        old_profile = self.server.fetch_wechat_user_profile
        try:
            self.server.WECHAT_LOGIN_ENABLED = True
            self.server.WECHAT_APP_ID = "wx-test-app"
            self.server.WECHAT_APP_SECRET = "wx-test-secret"
            self.server.WECHAT_REDIRECT_URI = "http://localhost:5001/api/auth/wechat/callback"
            self.server.WECHAT_OAUTH_SCOPE = "snsapi_login"

            def _fake_exchange(_code):
                return {
                    "access_token": "mock-token",
                    "openid": "mock-openid",
                    "unionid": "mock-unionid",
                }, ""

            def _fake_profile(_token, _openid):
                return {
                    "nickname": "微信用户A",
                    "headimgurl": "https://example.com/avatar-a.png",
                    "unionid": "mock-unionid",
                }, ""

            self.server.exchange_wechat_code_for_token = _fake_exchange
            self.server.fetch_wechat_user_profile = _fake_profile

            start_resp = self.client.get("/api/auth/wechat/start?return_to=/")
            self.assertEqual(start_resp.status_code, 302)
            self.assertIn("open.weixin.qq.com/connect/qrconnect", start_resp.headers.get("Location", ""))

            with self.client.session_transaction() as sess:
                oauth_state = sess.get("wechat_oauth_state")

            self.assertTrue(oauth_state)
            callback_resp = self.client.get(f"/api/auth/wechat/callback?code=mock-code&state={oauth_state}")
            self.assertEqual(callback_resp.status_code, 302)
            self.assertIn("auth_result=wechat_success", callback_resp.headers.get("Location", ""))

            me_resp = self.client.get("/api/auth/me")
            self.assertEqual(me_resp.status_code, 200)
            payload = me_resp.get_json().get("user", {})
            self.assertGreater(int(payload.get("id", 0)), 0)
        finally:
            self.server.WECHAT_LOGIN_ENABLED = old_enabled
            self.server.WECHAT_APP_ID = old_app_id
            self.server.WECHAT_APP_SECRET = old_secret
            self.server.WECHAT_REDIRECT_URI = old_redirect
            self.server.WECHAT_OAUTH_SCOPE = old_scope
            self.server.exchange_wechat_code_for_token = old_exchange
            self.server.fetch_wechat_user_profile = old_profile

    def test_wechat_auth_normalizes_nickname_and_prefers_nickname_account(self):
        old_enabled = self.server.WECHAT_LOGIN_ENABLED
        old_app_id = self.server.WECHAT_APP_ID
        old_secret = self.server.WECHAT_APP_SECRET
        old_redirect = self.server.WECHAT_REDIRECT_URI
        old_scope = self.server.WECHAT_OAUTH_SCOPE
        old_exchange = self.server.exchange_wechat_code_for_token
        old_profile = self.server.fetch_wechat_user_profile
        try:
            self.server.WECHAT_LOGIN_ENABLED = True
            self.server.WECHAT_APP_ID = "wx-test-app"
            self.server.WECHAT_APP_SECRET = "wx-test-secret"
            self.server.WECHAT_REDIRECT_URI = "http://localhost:5001/api/auth/wechat/callback"
            self.server.WECHAT_OAUTH_SCOPE = "snsapi_login"

            def _fake_exchange(_code):
                return {
                    "access_token": "mock-token",
                    "openid": "mock-openid-b",
                    "unionid": "mock-unionid-b",
                }, ""

            def _fake_profile(_token, _openid):
                return {
                    "nickname": "ä½ å¥½ Victor",
                    "headimgurl": "https://example.com/avatar-b.png",
                    "unionid": "mock-unionid-b",
                }, ""

            self.server.exchange_wechat_code_for_token = _fake_exchange
            self.server.fetch_wechat_user_profile = _fake_profile

            start_resp = self.client.get("/api/auth/wechat/start?return_to=/")
            self.assertEqual(start_resp.status_code, 302)

            with self.client.session_transaction() as sess:
                oauth_state = sess.get("wechat_oauth_state")

            callback_resp = self.client.get(f"/api/auth/wechat/callback?code=mock-code&state={oauth_state}")
            self.assertEqual(callback_resp.status_code, 302)
            self.assertIn("auth_result=wechat_success", callback_resp.headers.get("Location", ""))

            me_resp = self.client.get("/api/auth/me")
            self.assertEqual(me_resp.status_code, 200)
            payload = me_resp.get_json().get("user", {})
            self.assertEqual(payload.get("wechat_nickname"), "你好 Victor")
            self.assertEqual(payload.get("account"), "你好 Victor")

            identity = self.server.query_wechat_identity_by_user_id(int(payload["id"]))
            self.assertIsNotNone(identity)
            self.assertEqual(identity.get("nickname"), "你好 Victor")
        finally:
            self.server.WECHAT_LOGIN_ENABLED = old_enabled
            self.server.WECHAT_APP_ID = old_app_id
            self.server.WECHAT_APP_SECRET = old_secret
            self.server.WECHAT_REDIRECT_URI = old_redirect
            self.server.WECHAT_OAUTH_SCOPE = old_scope
            self.server.exchange_wechat_code_for_token = old_exchange
            self.server.fetch_wechat_user_profile = old_profile

    def test_auth_me_repairs_garbled_wechat_nickname_for_existing_identity(self):
        now_iso = datetime.utcnow().isoformat()
        with self.server.get_auth_db_connection() as conn:
            created = conn.execute(
                """
                INSERT INTO users (email, phone, password_hash, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                ("wx_existing_case@wechat.local", None, "test-hash", now_iso, now_iso),
            )
            user_id = int(created.lastrowid)
            conn.execute(
                """
                INSERT INTO wechat_identities
                (user_id, app_id, openid, unionid, nickname, avatar_url, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    "wx-test-app",
                    "mock-openid-existing",
                    "mock-unionid-existing",
                    "ä½ å¥½ Victor",
                    "https://example.com/avatar-existing.png",
                    now_iso,
                    now_iso,
                ),
            )
            conn.commit()

        self._set_authenticated_client(self.client, {"id": user_id})
        me_resp = self.client.get("/api/auth/me")
        self.assertEqual(me_resp.status_code, 200)
        payload = me_resp.get_json().get("user", {})
        self.assertEqual(payload.get("wechat_nickname"), "你好 Victor")
        self.assertEqual(payload.get("account"), "你好 Victor")

    def test_wechat_callback_rejects_invalid_state(self):
        old_enabled = self.server.WECHAT_LOGIN_ENABLED
        old_app_id = self.server.WECHAT_APP_ID
        old_secret = self.server.WECHAT_APP_SECRET
        old_redirect = self.server.WECHAT_REDIRECT_URI
        try:
            self.server.WECHAT_LOGIN_ENABLED = True
            self.server.WECHAT_APP_ID = "wx-test-app"
            self.server.WECHAT_APP_SECRET = "wx-test-secret"
            self.server.WECHAT_REDIRECT_URI = "http://localhost:5001/api/auth/wechat/callback"

            start_resp = self.client.get("/api/auth/wechat/start?return_to=/")
            self.assertEqual(start_resp.status_code, 302)

            callback_resp = self.client.get("/api/auth/wechat/callback?code=mock-code&state=wrong-state")
            self.assertEqual(callback_resp.status_code, 302)
            location = callback_resp.headers.get("Location", "")
            self.assertIn("auth_result=wechat_error", location)

            me_resp = self.client.get("/api/auth/me")
            self.assertEqual(me_resp.status_code, 401)
        finally:
            self.server.WECHAT_LOGIN_ENABLED = old_enabled
            self.server.WECHAT_APP_ID = old_app_id
            self.server.WECHAT_APP_SECRET = old_secret
            self.server.WECHAT_REDIRECT_URI = old_redirect

    def test_account_merge_preview_requires_login_and_candidate_context(self):
        unauth_client = self.server.app.test_client()
        unauth_resp = unauth_client.post("/api/auth/account-merge/preview", json={})
        self.assertEqual(unauth_resp.status_code, 401, unauth_resp.get_data(as_text=True))

        self._register()
        missing_candidate_resp = self.client.post("/api/auth/account-merge/preview", json={})
        self.assertEqual(missing_candidate_resp.status_code, 409, missing_candidate_resp.get_data(as_text=True))
        self.assertIn("合并上下文已失效", missing_candidate_resp.get_json().get("error", ""))

    def test_account_merge_apply_requires_login_and_active_preview(self):
        unauth_client = self.server.app.test_client()
        unauth_resp = unauth_client.post(
            "/api/auth/account-merge/apply",
            json={"preview_token": "missing", "confirm_text": "确认合并"},
        )
        self.assertEqual(unauth_resp.status_code, 401, unauth_resp.get_data(as_text=True))

        self._register()
        missing_preview_resp = self.client.post(
            "/api/auth/account-merge/apply",
            json={"preview_token": "missing", "confirm_text": "确认合并"},
        )
        self.assertEqual(missing_preview_resp.status_code, 409, missing_preview_resp.get_data(as_text=True))
        self.assertIn("预览已失效", missing_preview_resp.get_json().get("error", ""))

    def test_bind_phone_directly_takes_over_empty_phone_account(self):
        target_row = self._create_wechat_user(nickname="当前微信账号")
        self.assertIsNotNone(target_row)
        self._set_authenticated_client(self.client, {"id": int(target_row["id"])})

        source_client = self.server.app.test_client()
        source_user = self._register(client=source_client)

        send_resp = self.client.post(
            "/api/auth/sms/send-code",
            json={"phone": source_user["phone"], "scene": "bind"},
        )
        self.assertEqual(send_resp.status_code, 200, send_resp.get_data(as_text=True))
        bind_code = send_resp.get_json()["test_code"]

        bind_resp = self.client.post(
            "/api/auth/bind/phone",
            json={"phone": source_user["phone"], "code": bind_code},
        )
        self.assertEqual(bind_resp.status_code, 200, bind_resp.get_data(as_text=True))
        payload = bind_resp.get_json()
        self.assertTrue(payload.get("merge_applied"))
        self.assertEqual(source_user["phone"], payload["user"]["phone"])
        self.assertTrue(payload["user"]["wechat_bound"])

        me_resp = self.client.get("/api/auth/me")
        self.assertEqual(me_resp.status_code, 200, me_resp.get_data(as_text=True))
        self.assertEqual(source_user["phone"], me_resp.get_json()["user"]["phone"])

        source_row_after = self.server.query_user_by_id(int(source_user["id"]))
        self.assertIsNotNone(source_row_after)
        self.assertEqual(int(target_row["id"]), int(source_row_after["merged_into_user_id"] or 0))
        self.assertIsNone(source_row_after["phone"])

    def test_bind_phone_conflict_requires_preview_apply_and_admin_rollback(self):
        target_row = self._create_wechat_user(nickname="微信主账号")
        self.assertIsNotNone(target_row)
        self._set_authenticated_client(self.client, {"id": int(target_row["id"])})

        source_client = self.server.app.test_client()
        source_user = self._register(client=source_client)
        fixture = self._create_owned_merge_fixture(int(source_user["id"]), f"phone-merge-{uuid.uuid4().hex[:6]}")

        send_resp = self.client.post(
            "/api/auth/sms/send-code",
            json={"phone": source_user["phone"], "scene": "bind"},
        )
        self.assertEqual(send_resp.status_code, 200, send_resp.get_data(as_text=True))
        bind_code = send_resp.get_json()["test_code"]

        bind_resp = self.client.post(
            "/api/auth/bind/phone",
            json={"phone": source_user["phone"], "code": bind_code},
        )
        self.assertEqual(bind_resp.status_code, 409, bind_resp.get_data(as_text=True))
        bind_payload = bind_resp.get_json()
        self.assertTrue(bind_payload.get("merge_required"))
        self.assertEqual("phone", bind_payload.get("conflict_identity_type"))
        self.assertEqual(int(source_user["id"]), int(bind_payload["conflict_account_summary"]["id"]))

        preview_resp = self.client.post("/api/auth/account-merge/preview", json={})
        self.assertEqual(preview_resp.status_code, 200, preview_resp.get_data(as_text=True))
        preview_payload = preview_resp.get_json()
        self.assertEqual(1, preview_payload["source_account"]["asset_counts"]["sessions"])
        self.assertEqual(1, preview_payload["source_account"]["asset_counts"]["reports"])
        self.assertEqual(1, preview_payload["source_account"]["asset_counts"]["custom_scenarios"])
        self.assertEqual(1, preview_payload["source_account"]["asset_counts"]["solution_shares"])
        self.assertEqual(1, preview_payload["source_account"]["asset_counts"]["licenses"])
        self.assertTrue(preview_payload.get("preview_token"))
        self.assertTrue(preview_payload.get("confirm_phrase"))

        invalid_token_resp = self.client.post(
            "/api/auth/account-merge/apply",
            json={"preview_token": "wrong-token", "confirm_text": preview_payload["confirm_phrase"]},
        )
        self.assertEqual(invalid_token_resp.status_code, 409, invalid_token_resp.get_data(as_text=True))

        wrong_confirm_resp = self.client.post(
            "/api/auth/account-merge/apply",
            json={"preview_token": preview_payload["preview_token"], "confirm_text": "确认词错误"},
        )
        self.assertEqual(wrong_confirm_resp.status_code, 400, wrong_confirm_resp.get_data(as_text=True))

        apply_resp = self.client.post(
            "/api/auth/account-merge/apply",
            json={
                "preview_token": preview_payload["preview_token"],
                "confirm_text": preview_payload["confirm_phrase"],
            },
        )
        self.assertEqual(apply_resp.status_code, 200, apply_resp.get_data(as_text=True))
        apply_payload = apply_resp.get_json()
        self.assertEqual(source_user["phone"], apply_payload["user"]["phone"])
        self.assertTrue(apply_payload["user"]["wechat_bound"])

        migrated_session = json.loads(fixture["session_file"].read_text(encoding="utf-8"))
        self.assertEqual(int(target_row["id"]), int(migrated_session["owner_user_id"]))
        report_owners = json.loads(self.server.REPORT_OWNERS_FILE.read_text(encoding="utf-8"))
        self.assertEqual(int(target_row["id"]), int(report_owners[fixture["report_name"]]))
        shares = self.server.load_solution_share_map()
        self.assertEqual(int(target_row["id"]), int(shares[fixture["share_token"]]["owner_user_id"]))
        merged_scenario = self.server.scenario_loader.get_scenario(fixture["scenario_id"])
        self.assertEqual(int(target_row["id"]), int(merged_scenario["owner_user_id"]))
        self.assertEqual("active", self.server.get_user_license_state(int(target_row["id"]))["status"])

        source_row_after = self.server.query_user_by_id(int(source_user["id"]))
        self.assertEqual(int(target_row["id"]), int(source_row_after["merged_into_user_id"] or 0))

        old_admin_ids = set(self.server.ADMIN_USER_IDS)
        old_admin_phones = set(self.server.ADMIN_PHONE_NUMBERS)
        try:
            self.server.ADMIN_USER_IDS = {int(target_row["id"])}
            self.server.ADMIN_PHONE_NUMBERS = set()
            history_resp = self.client.get("/api/admin/ownership-migrations?limit=20")
            self.assertEqual(history_resp.status_code, 200, history_resp.get_data(as_text=True))
            history_payload = history_resp.get_json()
            backup_item = next(
                item
                for item in history_payload.get("items", [])
                if item.get("operation_type") == "account_merge"
                and int((item.get("source_user") or {}).get("id") or 0) == int(source_user["id"])
            )
            rollback_resp = self.client.post(
                "/api/admin/ownership-migrations/rollback",
                json={"backup_id": backup_item["backup_id"]},
            )
            self.assertEqual(rollback_resp.status_code, 200, rollback_resp.get_data(as_text=True))
        finally:
            self.server.ADMIN_USER_IDS = old_admin_ids
            self.server.ADMIN_PHONE_NUMBERS = old_admin_phones

        rolled_back_session = json.loads(fixture["session_file"].read_text(encoding="utf-8"))
        self.assertEqual(int(source_user["id"]), int(rolled_back_session["owner_user_id"]))
        rolled_back_owners = json.loads(self.server.REPORT_OWNERS_FILE.read_text(encoding="utf-8"))
        self.assertEqual(int(source_user["id"]), int(rolled_back_owners[fixture["report_name"]]))
        rolled_back_shares = self.server.load_solution_share_map()
        self.assertEqual(int(source_user["id"]), int(rolled_back_shares[fixture["share_token"]]["owner_user_id"]))
        self.server.scenario_loader.reload()
        rolled_back_scenario = self.server.scenario_loader.get_scenario(fixture["scenario_id"])
        self.assertEqual(int(source_user["id"]), int(rolled_back_scenario["owner_user_id"]))
        source_license_state = self.server.get_user_license_state(int(source_user["id"]))
        self.assertEqual("active", source_license_state["status"])

    def test_bind_wechat_directly_takes_over_empty_wechat_shadow_account(self):
        target_user = self._register()
        source_wechat = self._create_wechat_user(
            app_id="wx-test-app",
            openid="mock-openid-direct",
            unionid="mock-unionid-direct",
            nickname="直接绑定微信",
        )
        self.assertIsNotNone(source_wechat)

        old_enabled = self.server.WECHAT_LOGIN_ENABLED
        old_app_id = self.server.WECHAT_APP_ID
        old_secret = self.server.WECHAT_APP_SECRET
        old_redirect = self.server.WECHAT_REDIRECT_URI
        old_scope = self.server.WECHAT_OAUTH_SCOPE
        old_exchange = self.server.exchange_wechat_code_for_token
        old_profile = self.server.fetch_wechat_user_profile
        try:
            self.server.WECHAT_LOGIN_ENABLED = True
            self.server.WECHAT_APP_ID = "wx-test-app"
            self.server.WECHAT_APP_SECRET = "wx-test-secret"
            self.server.WECHAT_REDIRECT_URI = "http://localhost:5001/api/auth/wechat/callback"
            self.server.WECHAT_OAUTH_SCOPE = "snsapi_login"

            self.server.exchange_wechat_code_for_token = lambda _code: ({
                "access_token": "bind-token",
                "openid": "mock-openid-direct",
                "unionid": "mock-unionid-direct",
            }, "")
            self.server.fetch_wechat_user_profile = lambda _token, _openid: ({
                "nickname": "直接绑定微信",
                "headimgurl": "https://example.com/direct.png",
                "unionid": "mock-unionid-direct",
            }, "")

            start_resp = self.client.get("/api/auth/bind/wechat/start?return_to=/")
            self.assertEqual(start_resp.status_code, 302, start_resp.get_data(as_text=True))
            with self.client.session_transaction() as sess:
                bind_state = sess.get("wechat_bind_state")
            callback_resp = self.client.get(f"/api/auth/wechat/callback?code=bind-code&state={bind_state}")
            self.assertEqual(callback_resp.status_code, 302, callback_resp.get_data(as_text=True))
            self.assertIn("auth_result=wechat_bind_success", callback_resp.headers.get("Location", ""))

            me_resp = self.client.get("/api/auth/me")
            self.assertEqual(me_resp.status_code, 200, me_resp.get_data(as_text=True))
            self.assertTrue(me_resp.get_json()["user"]["wechat_bound"])
            source_row_after = self.server.query_user_by_id(int(source_wechat["id"]))
            self.assertEqual(int(target_user["id"]), int(source_row_after["merged_into_user_id"] or 0))
        finally:
            self.server.WECHAT_LOGIN_ENABLED = old_enabled
            self.server.WECHAT_APP_ID = old_app_id
            self.server.WECHAT_APP_SECRET = old_secret
            self.server.WECHAT_REDIRECT_URI = old_redirect
            self.server.WECHAT_OAUTH_SCOPE = old_scope
            self.server.exchange_wechat_code_for_token = old_exchange
            self.server.fetch_wechat_user_profile = old_profile

    def test_bind_wechat_conflict_redirects_to_merge_preview_and_apply(self):
        target_user = self._register()
        source_wechat = self._create_wechat_user(
            app_id="wx-test-app",
            openid="mock-openid-merge",
            unionid="mock-unionid-merge",
            nickname="微信历史账号",
        )
        fixture = self._create_owned_merge_fixture(int(source_wechat["id"]), f"wechat-merge-{uuid.uuid4().hex[:6]}")

        old_enabled = self.server.WECHAT_LOGIN_ENABLED
        old_app_id = self.server.WECHAT_APP_ID
        old_secret = self.server.WECHAT_APP_SECRET
        old_redirect = self.server.WECHAT_REDIRECT_URI
        old_scope = self.server.WECHAT_OAUTH_SCOPE
        old_exchange = self.server.exchange_wechat_code_for_token
        old_profile = self.server.fetch_wechat_user_profile
        old_get_admin_meta_index_db_target = self.server._get_admin_meta_index_db_target
        old_use_postgres_shared_meta_storage = self.server._use_postgres_shared_meta_storage
        try:
            self.server.WECHAT_LOGIN_ENABLED = True
            self.server.WECHAT_APP_ID = "wx-test-app"
            self.server.WECHAT_APP_SECRET = "wx-test-secret"
            self.server.WECHAT_REDIRECT_URI = "http://localhost:5001/api/auth/wechat/callback"
            self.server.WECHAT_OAUTH_SCOPE = "snsapi_login"
            self.server._get_admin_meta_index_db_target = lambda: None
            self.server._use_postgres_shared_meta_storage = lambda: False

            self.server.exchange_wechat_code_for_token = lambda _code: ({
                "access_token": "bind-token",
                "openid": "mock-openid-merge",
                "unionid": "mock-unionid-merge",
            }, "")
            self.server.fetch_wechat_user_profile = lambda _token, _openid: ({
                "nickname": "微信历史账号",
                "headimgurl": "https://example.com/merge.png",
                "unionid": "mock-unionid-merge",
            }, "")

            start_resp = self.client.get("/api/auth/bind/wechat/start?return_to=/")
            self.assertEqual(start_resp.status_code, 302, start_resp.get_data(as_text=True))
            with self.client.session_transaction() as sess:
                bind_state = sess.get("wechat_bind_state")
            callback_resp = self.client.get(f"/api/auth/wechat/callback?code=bind-code&state={bind_state}")
            self.assertEqual(callback_resp.status_code, 302, callback_resp.get_data(as_text=True))
            self.assertIn("auth_result=wechat_bind_merge_required", callback_resp.headers.get("Location", ""))

            preview_resp = self.client.post("/api/auth/account-merge/preview", json={})
            self.assertEqual(preview_resp.status_code, 200, preview_resp.get_data(as_text=True))
            preview_payload = preview_resp.get_json()
            self.assertEqual("wechat", preview_payload.get("identity_type"))
            self.assertEqual(1, preview_payload["source_account"]["asset_counts"]["sessions"])
            self.assertEqual(1, preview_payload["source_account"]["asset_counts"]["reports"])

            apply_resp = self.client.post(
                "/api/auth/account-merge/apply",
                json={
                    "preview_token": preview_payload["preview_token"],
                    "confirm_text": preview_payload["confirm_phrase"],
                },
            )
            self.assertEqual(apply_resp.status_code, 200, apply_resp.get_data(as_text=True))
            me_resp = self.client.get("/api/auth/me")
            self.assertEqual(me_resp.status_code, 200, me_resp.get_data(as_text=True))
            me_payload = me_resp.get_json()["user"]
            self.assertTrue(me_payload["wechat_bound"])
            self.assertEqual("微信历史账号", me_payload["wechat_nickname"])

            migrated_session = json.loads(fixture["session_file"].read_text(encoding="utf-8"))
            self.assertEqual(int(target_user["id"]), int(migrated_session["owner_user_id"]))
            shares = self.server.load_solution_share_map()
            self.assertEqual(int(target_user["id"]), int(shares[fixture["share_token"]]["owner_user_id"]))
            source_row_after = self.server.query_user_by_id(int(source_wechat["id"]))
            self.assertEqual(int(target_user["id"]), int(source_row_after["merged_into_user_id"] or 0))
        finally:
            self.server.WECHAT_LOGIN_ENABLED = old_enabled
            self.server.WECHAT_APP_ID = old_app_id
            self.server.WECHAT_APP_SECRET = old_secret
            self.server.WECHAT_REDIRECT_URI = old_redirect
            self.server.WECHAT_OAUTH_SCOPE = old_scope
            self.server.exchange_wechat_code_for_token = old_exchange
            self.server.fetch_wechat_user_profile = old_profile
            self.server._get_admin_meta_index_db_target = old_get_admin_meta_index_db_target
            self.server._use_postgres_shared_meta_storage = old_use_postgres_shared_meta_storage

    def test_session_crud(self):
        self._register()
        created = self._create_session(topic="CRUD测试主题")
        session_id = created["session_id"]

        list_resp = self.client.get("/api/sessions")
        self.assertEqual(list_resp.status_code, 200)
        ids = [item["session_id"] for item in list_resp.get_json()]
        self.assertIn(session_id, ids)

        get_resp = self.client.get(f"/api/sessions/{session_id}")
        self.assertEqual(get_resp.status_code, 200)
        self.assertEqual(get_resp.get_json()["topic"], "CRUD测试主题")

        update_resp = self.client.put(
            f"/api/sessions/{session_id}",
            json={"topic": "已更新主题", "status": "paused", "owner_user_id": 999999},
        )
        self.assertEqual(update_resp.status_code, 200)
        updated = update_resp.get_json()
        self.assertEqual(updated["topic"], "已更新主题")
        self.assertEqual(updated["status"], "paused")
        self.assertNotEqual(updated.get("owner_user_id"), 999999)

        delete_resp = self.client.delete(f"/api/sessions/{session_id}")
        self.assertEqual(delete_resp.status_code, 200)

        get_deleted = self.client.get(f"/api/sessions/{session_id}")
        self.assertEqual(get_deleted.status_code, 404)

    def test_create_session_falls_back_when_scenario_dimensions_malformed(self):
        user = self._register()
        broken_scenario_id = "custom-broken"
        self.server.scenario_loader._cache[broken_scenario_id] = {
            "id": broken_scenario_id,
            "name": "异常场景",
            "description": "历史脏数据",
            "builtin": False,
            "custom": True,
            "owner_user_id": int(user["id"]),
            self.server.INSTANCE_SCOPE_FIELD: "",
            "dimensions": [
                "invalid-dimension",
                {"name": "缺少ID"},
                {"id": "   ", "name": "空ID"},
            ],
        }

        try:
            response = self.client.post(
                "/api/sessions",
                json={"topic": "异常场景创建", "scenario_id": broken_scenario_id},
            )
            self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
            payload = response.get_json()
            self.assertEqual(payload.get("scenario_id"), "product-requirement")
            self.assertIn("customer_needs", payload.get("dimensions", {}))
            self.assertGreaterEqual(len(payload.get("dimensions", {})), 4)
        finally:
            self.server.scenario_loader._cache.pop(broken_scenario_id, None)

    def test_session_isolation_between_users(self):
        user_a = self._register()
        session_id = self._create_session(topic="隔离测试")["session_id"]

        other_client = self.server.app.test_client()
        self._register(client=other_client)

        list_other = other_client.get("/api/sessions")
        self.assertEqual(list_other.status_code, 200)
        self.assertNotIn(session_id, [s["session_id"] for s in list_other.get_json()])

        get_other = other_client.get(f"/api/sessions/{session_id}")
        self.assertEqual(get_other.status_code, 404)

        delete_other = other_client.delete(f"/api/sessions/{session_id}")
        self.assertEqual(delete_other.status_code, 404)

        self.assertGreater(user_a["id"], 0)

    def test_session_isolation_between_instance_scopes_for_same_user(self):
        old_scope = self.server.INSTANCE_SCOPE_KEY
        try:
            self.server.INSTANCE_SCOPE_KEY = "instance-a"
            user = self._register()
            session_id = self._create_session(topic="实例隔离会话")["session_id"]

            list_a = self.client.get("/api/sessions")
            self.assertEqual(list_a.status_code, 200)
            self.assertIn(session_id, [item["session_id"] for item in list_a.get_json()])

            self.server.INSTANCE_SCOPE_KEY = "instance-b"
            list_b = self.client.get("/api/sessions")
            self.assertEqual(list_b.status_code, 200)
            self.assertNotIn(session_id, [item["session_id"] for item in list_b.get_json()])

            get_b = self.client.get(f"/api/sessions/{session_id}")
            self.assertEqual(get_b.status_code, 404)

            delete_b = self.client.delete(f"/api/sessions/{session_id}")
            self.assertEqual(delete_b.status_code, 404)

            self.assertGreater(user["id"], 0)
        finally:
            self.server.INSTANCE_SCOPE_KEY = old_scope

    def test_report_isolation_between_instance_scopes_for_same_user(self):
        old_scope = self.server.INSTANCE_SCOPE_KEY
        try:
            self.server.INSTANCE_SCOPE_KEY = "instance-a"
            user = self._register()
            report_name = self._build_scoped_report_name("实例隔离报告")
            (self.server.REPORTS_DIR / report_name).write_text("# 实例隔离报告\n", encoding="utf-8")
            self.server.set_report_owner_id(report_name, int(user["id"]))

            list_a = self.client.get("/api/reports")
            self.assertEqual(list_a.status_code, 200)
            self.assertIn(report_name, [item["name"] for item in list_a.get_json()])

            self.server.INSTANCE_SCOPE_KEY = "instance-b"
            list_b = self.client.get("/api/reports")
            self.assertEqual(list_b.status_code, 200)
            self.assertNotIn(report_name, [item["name"] for item in list_b.get_json()])

            get_b = self.client.get(f"/api/reports/{report_name}")
            self.assertEqual(get_b.status_code, 404)

            delete_b = self.client.delete(f"/api/reports/{report_name}")
            self.assertEqual(delete_b.status_code, 404)
        finally:
            self.server.INSTANCE_SCOPE_KEY = old_scope

    def test_sessions_list_supports_pagination_headers(self):
        self._register()
        for i in range(25):
            self._create_session(topic=f"分页会话-{i:02d}")

        list_resp = self.client.get("/api/sessions?page=2&page_size=10")
        self.assertEqual(list_resp.status_code, 200, list_resp.get_data(as_text=True))
        payload = list_resp.get_json()
        self.assertIsInstance(payload, list)
        self.assertEqual(len(payload), 10)
        self.assertEqual(list_resp.headers.get("X-Page"), "2")
        self.assertEqual(list_resp.headers.get("X-Page-Size"), "10")
        self.assertEqual(list_resp.headers.get("X-Total-Count"), "25")
        self.assertEqual(list_resp.headers.get("X-Total-Pages"), "3")
        etag = list_resp.headers.get("ETag")
        self.assertTrue(etag)

        not_modified = self.client.get(
            "/api/sessions?page=2&page_size=10",
            headers={"If-None-Match": etag},
        )
        self.assertEqual(not_modified.status_code, 304)
        self.assertEqual(not_modified.get_data(as_text=True), "")

    def test_reports_list_supports_pagination_headers(self):
        user = self._register()
        user_id = int(user["id"])
        for i in range(25):
            report_name = f"deep-vision-20990101-report-{i:02d}.md"
            report_file = self.server.REPORTS_DIR / report_name
            report_file.write_text(f"# report {i}\n", encoding="utf-8")
            self.server.set_report_owner_id(report_name, user_id)

        list_resp = self.client.get("/api/reports?page=2&page_size=10")
        self.assertEqual(list_resp.status_code, 200, list_resp.get_data(as_text=True))
        payload = list_resp.get_json()
        self.assertIsInstance(payload, list)
        self.assertEqual(len(payload), 10)
        self.assertEqual(list_resp.headers.get("X-Page"), "2")
        self.assertEqual(list_resp.headers.get("X-Page-Size"), "10")
        self.assertEqual(list_resp.headers.get("X-Total-Count"), "25")
        self.assertEqual(list_resp.headers.get("X-Total-Pages"), "3")
        etag = list_resp.headers.get("ETag")
        self.assertTrue(etag)

        not_modified = self.client.get(
            "/api/reports?page=2&page_size=10",
            headers={"If-None-Match": etag},
        )
        self.assertEqual(not_modified.status_code, 304)
        self.assertEqual(not_modified.get_data(as_text=True), "")

    def test_list_endpoints_return_429_when_overloaded(self):
        self._register()
        self._create_session(topic="过载保护会话")

        old_sessions_semaphore = self.server.SESSIONS_LIST_SEMAPHORE
        old_reports_semaphore = self.server.REPORTS_LIST_SEMAPHORE
        self.server.SESSIONS_LIST_SEMAPHORE = threading.BoundedSemaphore(1)
        self.server.REPORTS_LIST_SEMAPHORE = threading.BoundedSemaphore(1)
        self.assertTrue(self.server.SESSIONS_LIST_SEMAPHORE.acquire(blocking=False))
        self.assertTrue(self.server.REPORTS_LIST_SEMAPHORE.acquire(blocking=False))
        try:
            sessions_resp = self.client.get("/api/sessions")
            self.assertEqual(sessions_resp.status_code, 429)
            self.assertEqual(
                sessions_resp.headers.get("Retry-After"),
                str(self.server.LIST_API_RETRY_AFTER_SECONDS),
            )

            reports_resp = self.client.get("/api/reports")
            self.assertEqual(reports_resp.status_code, 429)
            self.assertEqual(
                reports_resp.headers.get("Retry-After"),
                str(self.server.LIST_API_RETRY_AFTER_SECONDS),
            )
        finally:
            self.server.SESSIONS_LIST_SEMAPHORE.release()
            self.server.REPORTS_LIST_SEMAPHORE.release()
            self.server.SESSIONS_LIST_SEMAPHORE = old_sessions_semaphore
            self.server.REPORTS_LIST_SEMAPHORE = old_reports_semaphore

    def test_submit_answer_and_undo(self):
        self._register()
        created = self._create_session(topic="问答链路")
        session_id = created["session_id"]
        dimension = list(created["dimensions"].keys())[0]

        after_submit = self._submit_answer(
            session_id=session_id,
            dimension=dimension,
            question="你最想先优化哪个环节？",
            answer="这是一个用于自动化测试的回答",
        )
        self.assertEqual(len(after_submit.get("interview_log", [])), 1)
        self.assertGreater(after_submit["dimensions"][dimension]["coverage"], 0)

        undo_resp = self.client.post(f"/api/sessions/{session_id}/undo-answer", json={})
        self.assertEqual(undo_resp.status_code, 200)
        undo_payload = undo_resp.get_json()
        self.assertEqual(len(undo_payload.get("interview_log", [])), 0)

    def test_submit_answer_persists_ai_recommendation_for_undo_restore(self):
        self._register()
        created = self._create_session(topic="AI推荐持久化")
        session_id = created["session_id"]
        dimension = list(created["dimensions"].keys())[0]

        response = self.client.post(
            f"/api/sessions/{session_id}/submit-answer",
            json={
                "question": "优先推进哪个方向？",
                "answer": "方案A",
                "dimension": dimension,
                "options": ["方案A", "方案B", "方案C"],
                "is_follow_up": False,
                "ai_recommendation": {
                    "recommended_options": ["方案A"],
                    "summary": "现阶段建议优先验证方案A",
                    "confidence": "high",
                    "reasons": [
                        {"text": "与已确认目标更贴近", "evidence": ["Q1", "Q2"]},
                    ],
                },
            },
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        payload = response.get_json() or {}
        log = (payload.get("interview_log") or [])[-1]
        self.assertEqual(
            log.get("ai_recommendation"),
            {
                "recommended_options": ["方案A"],
                "summary": "现阶段建议优先验证方案A",
                "confidence": "high",
                "reasons": [
                    {"text": "与已确认目标更贴近", "evidence": ["Q1", "Q2"]},
                ],
            },
        )

        detail_resp = self.client.get(f"/api/sessions/{session_id}")
        self.assertEqual(detail_resp.status_code, 200, detail_resp.get_data(as_text=True))
        detail_payload = detail_resp.get_json() or {}
        self.assertEqual(
            ((detail_payload.get("interview_log") or [])[-1] or {}).get("ai_recommendation", {}),
            log.get("ai_recommendation"),
        )

    def test_submit_answer_triggers_current_dimension_prefetch_with_latest_signature(self):
        self._register()
        created = self._create_session(topic="提交答案触发预取")
        session_id = created["session_id"]
        dimension = list(created["dimensions"].keys())[0]

        captured = {}
        old_trigger = self.server.trigger_current_dimension_prefetch
        try:
            def _capture(session, target_dimension, session_signature=None):
                captured["session_id"] = session.get("session_id")
                captured["dimension"] = target_dimension
                captured["signature"] = session_signature

            self.server.trigger_current_dimension_prefetch = _capture
            self._submit_answer(
                session_id=session_id,
                dimension=dimension,
                question="Q1",
                answer="A1",
            )
        finally:
            self.server.trigger_current_dimension_prefetch = old_trigger

        session_file = self.server.SESSIONS_DIR / f"{session_id}.json"
        self.assertEqual(captured.get("session_id"), session_id)
        self.assertEqual(captured.get("dimension"), dimension)
        self.assertEqual(captured.get("signature"), self.server.get_file_signature(session_file))

    def test_submit_answer_prefetches_current_dimension_next_question(self):
        self._register()
        created = self._create_session(topic="当前维度下一题预取")
        session_id = created["session_id"]
        dimension = list(created["dimensions"].keys())[0]

        old_trigger = self.server.trigger_current_dimension_prefetch
        old_generate_question = self.server.generate_question_with_tiered_strategy
        old_evaluate_completion = self.server.evaluate_dimension_completion_v2
        generate_calls = []

        try:
            self.server.trigger_current_dimension_prefetch = self.__class__.real_trigger_current_dimension_prefetch
            self.server.evaluate_dimension_completion_v2 = lambda *_args, **_kwargs: {"can_complete": False}

            def _generate_prefetched_question(*_args, **kwargs):
                generate_calls.append(kwargs.get("base_call_type"))
                return (
                    '{"question":"预取后的下一题","options":["选项A","选项B"],"multi_select":false}',
                    {
                        "question": "预取后的下一题",
                        "options": ["选项A", "选项B"],
                        "multi_select": False,
                    },
                    "fast:summary",
                )

            self.server.generate_question_with_tiered_strategy = _generate_prefetched_question

            submit_resp = self.client.post(
                f"/api/sessions/{session_id}/submit-answer",
                json={
                    "question": "当前题",
                    "answer": "当前回答",
                    "dimension": dimension,
                    "options": ["A", "B"],
                    "is_follow_up": False,
                },
            )
            self.assertEqual(submit_resp.status_code, 200, submit_resp.get_data(as_text=True))

            session_file = self.server.SESSIONS_DIR / f"{session_id}.json"
            expected_signature = self.server.get_file_signature(session_file)
            deadline = time.time() + 1.0
            while time.time() < deadline:
                with self.server.prefetch_cache_lock:
                    cached = self.server.prefetch_cache.get(session_id, {}).get(dimension)
                    if cached and cached.get("session_signature") == expected_signature:
                        break
                time.sleep(0.02)
            else:
                self.fail("提交答案后未生成当前维度预取缓存")

            next_q = self.client.post(
                f"/api/sessions/{session_id}/next-question",
                json={"dimension": dimension},
            )
            self.assertEqual(next_q.status_code, 200, next_q.get_data(as_text=True))
            payload = next_q.get_json() or {}
            self.assertEqual(payload.get("question"), "预取后的下一题")
            self.assertTrue(payload.get("prefetched") or payload.get("cached"))
            self.assertEqual(payload.get("dimension"), dimension)
            self.assertEqual(generate_calls, ["prefetch_current"])
        finally:
            self.server.trigger_current_dimension_prefetch = old_trigger
            self.server.generate_question_with_tiered_strategy = old_generate_question
            self.server.evaluate_dimension_completion_v2 = old_evaluate_completion

    def test_next_question_uses_fallback_when_ai_disabled(self):
        self._register()
        created = self._create_session(topic="fallback链路")
        session_id = created["session_id"]
        dimension = list(created["dimensions"].keys())[0]

        next_q = self.client.post(
            f"/api/sessions/{session_id}/next-question",
            json={"dimension": dimension},
        )
        self.assertEqual(next_q.status_code, 200, next_q.get_data(as_text=True))
        payload = next_q.get_json()
        self.assertEqual(payload.get("dimension"), dimension)
        self.assertFalse(payload.get("ai_generated", True))
        self.assertTrue(payload.get("question"))
        self.assertIsInstance(payload.get("options"), list)
        self.assertGreater(len(payload.get("options", [])), 0)
        stats = self.server.get_question_generation_stats_snapshot()
        self.assertEqual(stats.get("fallback_served"), 1)
        self.assertEqual(stats.get("fallback_reasons", {}).get("ai_disabled"), 1)

    def test_next_question_returns_429_when_generation_slots_exhausted(self):
        self._register()
        created = self._create_session(topic="问题并发闸门")
        session_id = created["session_id"]
        dimension = list(created["dimensions"].keys())[0]

        acquired_tokens = []
        for _ in range(self.server.QUESTION_GENERATION_MAX_INFLIGHT):
            acquired = self.server.QUESTION_GENERATION_SEMAPHORE.acquire(blocking=False)
            self.assertTrue(acquired)
            acquired_tokens.append(True)
        old_resolve_ai_client = self.server.resolve_ai_client
        old_queue_wait_seconds = self.server.QUESTION_GENERATION_QUEUE_WAIT_SECONDS
        try:
            self.server.QUESTION_GENERATION_QUEUE_WAIT_SECONDS = 0.01
            self.server.resolve_ai_client = lambda call_type="question": object()
            next_q = self.client.post(
                f"/api/sessions/{session_id}/next-question",
                json={"dimension": dimension},
            )
            self.assertEqual(next_q.status_code, 429, next_q.get_data(as_text=True))
            payload = next_q.get_json() or {}
            self.assertEqual(payload.get("code"), "overloaded")
            self.assertEqual(payload.get("endpoint"), "question_generation")
            self.assertEqual(next_q.headers.get("Retry-After"), str(self.server.QUESTION_GENERATION_RETRY_AFTER_SECONDS))
            stats = self.server.get_question_generation_stats_snapshot()
            self.assertEqual(stats.get("overloaded"), 1)
        finally:
            self.server.QUESTION_GENERATION_QUEUE_WAIT_SECONDS = old_queue_wait_seconds
            self.server.resolve_ai_client = old_resolve_ai_client
            for _ in acquired_tokens:
                self.server.QUESTION_GENERATION_SEMAPHORE.release()

    def test_next_question_returns_429_when_generation_queue_is_full(self):
        self._register()
        created = self._create_session(topic="问题短队列满载")
        session_id = created["session_id"]
        dimension = list(created["dimensions"].keys())[0]

        acquired_tokens = []
        for _ in range(self.server.QUESTION_GENERATION_MAX_PENDING):
            acquired = self.server.QUESTION_GENERATION_PENDING_SEMAPHORE.acquire(blocking=False)
            self.assertTrue(acquired)
            acquired_tokens.append(True)

        old_resolve_ai_client = self.server.resolve_ai_client
        try:
            self.server.resolve_ai_client = lambda call_type="question": object()
            next_q = self.client.post(
                f"/api/sessions/{session_id}/next-question",
                json={"dimension": dimension},
            )
            self.assertEqual(next_q.status_code, 429, next_q.get_data(as_text=True))
            payload = next_q.get_json() or {}
            self.assertEqual(payload.get("code"), "overloaded")
            self.assertEqual(payload.get("endpoint"), "question_generation")
            stats = self.server.get_question_generation_stats_snapshot()
            self.assertEqual(stats.get("overloaded"), 1)
        finally:
            self.server.resolve_ai_client = old_resolve_ai_client
            for _ in acquired_tokens:
                self.server.QUESTION_GENERATION_PENDING_SEMAPHORE.release()

    def test_next_question_waits_in_short_queue_until_generation_slot_available(self):
        self._register()
        created = self._create_session(topic="问题短队列等待成功")
        session_id = created["session_id"]
        dimension = list(created["dimensions"].keys())[0]

        acquired_tokens = []
        for _ in range(self.server.QUESTION_GENERATION_MAX_INFLIGHT):
            acquired = self.server.QUESTION_GENERATION_SEMAPHORE.acquire(blocking=False)
            self.assertTrue(acquired)
            acquired_tokens.append(True)

        old_resolve_ai_client = self.server.resolve_ai_client
        old_prepare_runtime = self.server._prepare_question_generation_runtime
        old_generate_question = self.server.generate_question_with_tiered_strategy
        old_trigger_prefetch = self.server.trigger_prefetch_if_needed
        old_queue_wait_seconds = self.server.QUESTION_GENERATION_QUEUE_WAIT_SECONDS
        releaser = None
        try:
            self.server.QUESTION_GENERATION_QUEUE_WAIT_SECONDS = 0.2
            self.server.resolve_ai_client = lambda call_type="question": object()
            self.server._prepare_question_generation_runtime = lambda *args, **kwargs: {
                "full_prompt": "full prompt",
                "truncated_docs": [],
                "fast_truncated_docs": [],
                "decision_meta": {},
                "runtime_profile": {
                    "profile_name": "question_probe_light",
                    "selection_reason": "queued_test",
                    "allow_fast_path": True,
                },
                "fast_prompt": "fast prompt",
            }
            self.server.generate_question_with_tiered_strategy = lambda *args, **kwargs: (
                "{\"question\":\"排队后的下一题\"}",
                {
                    "question": "排队后的下一题",
                    "options": ["选项一", "选项二"],
                    "multi_select": False,
                    "is_follow_up": False,
                },
                "fast:question",
            )
            self.server.trigger_prefetch_if_needed = lambda *args, **kwargs: None

            def _release_one_slot():
                time.sleep(0.03)
                self.server.QUESTION_GENERATION_SEMAPHORE.release()

            releaser = threading.Thread(target=_release_one_slot, daemon=True)
            releaser.start()
            started_at = time.perf_counter()
            next_q = self.client.post(
                f"/api/sessions/{session_id}/next-question",
                json={"dimension": dimension},
            )
            elapsed_ms = (time.perf_counter() - started_at) * 1000.0
            self.assertEqual(next_q.status_code, 200, next_q.get_data(as_text=True))
            payload = next_q.get_json() or {}
            self.assertEqual(payload.get("question"), "排队后的下一题")
            self.assertEqual(payload.get("question_generation_tier"), "fast:question")
            self.assertGreater(elapsed_ms, 20.0)
        finally:
            if releaser and releaser.is_alive():
                releaser.join(timeout=0.3)
            self.server.QUESTION_GENERATION_QUEUE_WAIT_SECONDS = old_queue_wait_seconds
            self.server.resolve_ai_client = old_resolve_ai_client
            self.server._prepare_question_generation_runtime = old_prepare_runtime
            self.server.generate_question_with_tiered_strategy = old_generate_question
            self.server.trigger_prefetch_if_needed = old_trigger_prefetch
            while acquired_tokens:
                acquired_tokens.pop()
                try:
                    self.server.QUESTION_GENERATION_SEMAPHORE.release()
                except ValueError:
                    break

    def test_next_question_repairs_truncated_ai_response(self):
        self._register()
        created = self._create_session(topic="问题修复链路")
        session_id = created["session_id"]
        dimension = list(created["dimensions"].keys())[0]

        old_resolve_ai_client = self.server.resolve_ai_client
        old_generate_question = self.server.generate_question_with_tiered_strategy
        try:
            self.server.resolve_ai_client = lambda call_type="question": object()
            self.server.generate_question_with_tiered_strategy = lambda *_args, **_kwargs: (
                '{"question":"当前最需要优先确认的重点是什么？","options":["预算范围","上线节奏"',
                None,
                "fast:summary",
            )

            next_q = self.client.post(
                f"/api/sessions/{session_id}/next-question",
                json={"dimension": dimension},
            )
            self.assertEqual(next_q.status_code, 200, next_q.get_data(as_text=True))
            payload = next_q.get_json() or {}
            self.assertEqual(payload.get("dimension"), dimension)
            self.assertTrue(payload.get("ai_generated"))
            self.assertTrue(payload.get("repair_applied"))
            self.assertGreaterEqual(len(payload.get("options", [])), 2)
            self.assertEqual(payload.get("question"), "当前最需要优先确认的重点是什么？")
        finally:
            self.server.resolve_ai_client = old_resolve_ai_client
            self.server.generate_question_with_tiered_strategy = old_generate_question

    def test_next_question_falls_back_when_ai_generation_raises(self):
        self._register()
        created = self._create_session(topic="问题异常回退")
        session_id = created["session_id"]
        dimension = list(created["dimensions"].keys())[0]

        old_resolve_ai_client = self.server.resolve_ai_client
        old_generate_question = self.server.generate_question_with_tiered_strategy
        try:
            self.server.resolve_ai_client = lambda call_type="question": object()

            def _raise_timeout(*_args, **_kwargs):
                raise TimeoutError("simulated timeout")

            self.server.generate_question_with_tiered_strategy = _raise_timeout

            next_q = self.client.post(
                f"/api/sessions/{session_id}/next-question",
                json={"dimension": dimension},
            )
            self.assertEqual(next_q.status_code, 200, next_q.get_data(as_text=True))
            payload = next_q.get_json() or {}
            self.assertEqual(payload.get("dimension"), dimension)
            self.assertFalse(payload.get("ai_generated", True))
            self.assertTrue(payload.get("question"))
            self.assertIn("已切换为备用题目", payload.get("detail", ""))
        finally:
            self.server.resolve_ai_client = old_resolve_ai_client
            self.server.generate_question_with_tiered_strategy = old_generate_question

    def test_next_question_waits_for_inflight_prefetch(self):
        self._register()
        created = self._create_session(topic="首题等待预生成")
        session_id = created["session_id"]
        dimension = list(created["dimensions"].keys())[0]
        session_file = self.server.SESSIONS_DIR / f"{session_id}.json"
        session_signature = self.server.get_file_signature(session_file)
        cache_key = self.server._build_question_result_cache_key(session_id, dimension, session_signature)
        owner_event, is_owner = self.server._begin_question_prefetch_inflight(cache_key)
        self.assertTrue(is_owner)

        old_wait = self.server.QUESTION_PREFETCH_INFLIGHT_WAIT_SECONDS
        old_resolve_ai_client = self.server.resolve_ai_client
        old_generate_question = self.server.generate_question_with_tiered_strategy
        try:
            self.server.QUESTION_PREFETCH_INFLIGHT_WAIT_SECONDS = 0.4
            self.server.resolve_ai_client = lambda call_type="question": object()

            def _should_not_generate(*_args, **_kwargs):
                raise AssertionError("存在在途预生成时不应再触发实时出题")

            self.server.generate_question_with_tiered_strategy = _should_not_generate

            def _complete_prefetch():
                time.sleep(0.05)
                with self.server.prefetch_cache_lock:
                    self.server.prefetch_cache.setdefault(session_id, {})[dimension] = {
                        "question_data": {
                            "question": "预生成首题",
                            "options": ["选项A", "选项B"],
                            "multi_select": False,
                            "dimension": dimension,
                            "ai_generated": True,
                        },
                        "created_at": time.time(),
                        "topic": created.get("topic"),
                        "session_signature": session_signature,
                        "valid": True,
                    }
                self.server._end_question_prefetch_inflight(cache_key, owner_event)

            worker = threading.Thread(target=_complete_prefetch, daemon=True)
            worker.start()

            next_q = self.client.post(
                f"/api/sessions/{session_id}/next-question",
                json={"dimension": dimension},
            )
            worker.join(timeout=1.0)

            self.assertEqual(next_q.status_code, 200, next_q.get_data(as_text=True))
            payload = next_q.get_json()
            self.assertEqual(payload.get("question"), "预生成首题")
            self.assertTrue(payload.get("prefetched"))
            self.assertEqual(payload.get("dimension"), dimension)
        finally:
            self.server.QUESTION_PREFETCH_INFLIGHT_WAIT_SECONDS = old_wait
            self.server.resolve_ai_client = old_resolve_ai_client
            self.server.generate_question_with_tiered_strategy = old_generate_question
            self.server._end_question_prefetch_inflight(cache_key, owner_event)

    def test_next_question_prefers_longer_wait_for_submit_prefetch(self):
        self._register()
        created = self._create_session(topic="提交后优先等待预取")
        session_id = created["session_id"]
        dimension = list(created["dimensions"].keys())[0]
        session_file = self.server.SESSIONS_DIR / f"{session_id}.json"
        session_signature = self.server.get_file_signature(session_file)
        cache_key = self.server._build_question_result_cache_key(session_id, dimension, session_signature)
        owner_event, is_owner = self.server._begin_question_prefetch_inflight(cache_key)
        self.assertTrue(is_owner)

        old_wait = self.server.QUESTION_PREFETCH_INFLIGHT_WAIT_SECONDS
        old_submit_wait = self.server.QUESTION_SUBMIT_PREFETCH_WAIT_SECONDS
        old_resolve_ai_client = self.server.resolve_ai_client
        old_generate_question = self.server.generate_question_with_tiered_strategy
        try:
            self.server.QUESTION_PREFETCH_INFLIGHT_WAIT_SECONDS = 0.05
            self.server.QUESTION_SUBMIT_PREFETCH_WAIT_SECONDS = 0.4
            self.server.resolve_ai_client = lambda call_type="question": object()

            def _should_not_generate(*_args, **_kwargs):
                raise AssertionError("提交后优先等待预取命中时不应再触发实时出题")

            self.server.generate_question_with_tiered_strategy = _should_not_generate

            def _complete_prefetch():
                time.sleep(0.12)
                prefetched_question = {
                    "question": "提交后命中的预取题",
                    "options": ["选项A", "选项B"],
                    "multi_select": False,
                    "dimension": dimension,
                    "ai_generated": True,
                }
                self.server._set_question_result_cache(cache_key, prefetched_question)
                with self.server.prefetch_cache_lock:
                    self.server.prefetch_cache.setdefault(session_id, {})[dimension] = {
                        "question_data": prefetched_question,
                        "created_at": time.time(),
                        "topic": created.get("topic"),
                        "session_signature": session_signature,
                        "valid": True,
                    }
                self.server._end_question_prefetch_inflight(cache_key, owner_event)

            worker = threading.Thread(target=_complete_prefetch, daemon=True)
            worker.start()

            next_q = self.client.post(
                f"/api/sessions/{session_id}/next-question",
                json={"dimension": dimension, "prefer_prefetch": True},
            )
            worker.join(timeout=1.0)

            self.assertEqual(next_q.status_code, 200, next_q.get_data(as_text=True))
            payload = next_q.get_json() or {}
            self.assertEqual(payload.get("question"), "提交后命中的预取题")
            self.assertTrue(payload.get("cached"))
        finally:
            self.server.QUESTION_PREFETCH_INFLIGHT_WAIT_SECONDS = old_wait
            self.server.QUESTION_SUBMIT_PREFETCH_WAIT_SECONDS = old_submit_wait
            self.server.resolve_ai_client = old_resolve_ai_client
            self.server.generate_question_with_tiered_strategy = old_generate_question
            self.server._end_question_prefetch_inflight(cache_key, owner_event)

    def test_next_question_discards_stale_prefetch_after_signature_change(self):
        self._register()
        created = self._create_session(topic="过期预生成丢弃")
        session_id = created["session_id"]
        dimension = list(created["dimensions"].keys())[0]
        session_file = self.server.SESSIONS_DIR / f"{session_id}.json"
        stale_signature = self.server.get_file_signature(session_file)

        with self.server.prefetch_cache_lock:
            self.server.prefetch_cache.setdefault(session_id, {})[dimension] = {
                "question_data": {
                    "question": "过期预生成题",
                    "options": ["旧选项A", "旧选项B"],
                    "multi_select": False,
                    "dimension": dimension,
                    "ai_generated": True,
                },
                "created_at": time.time(),
                "topic": created.get("topic"),
                "session_signature": stale_signature,
                "valid": True,
            }

        self._submit_answer(session_id, dimension, question="Q1", answer="A1")

        next_q = self.client.post(
            f"/api/sessions/{session_id}/next-question",
            json={"dimension": dimension},
        )

        self.assertEqual(next_q.status_code, 200, next_q.get_data(as_text=True))
        payload = next_q.get_json()
        self.assertNotEqual(payload.get("question"), "过期预生成题")
        self.assertFalse(payload.get("prefetched", False))
        with self.server.prefetch_cache_lock:
            self.assertNotIn(dimension, self.server.prefetch_cache.get(session_id, {}))

    def test_complete_dimension_requires_coverage_threshold(self):
        self._register()
        created = self._create_session(topic="完成维度测试")
        session_id = created["session_id"]
        dimension = list(created["dimensions"].keys())[0]

        too_early = self.client.post(
            f"/api/sessions/{session_id}/complete-dimension",
            json={"dimension": dimension},
        )
        self.assertEqual(too_early.status_code, 400)

        self._submit_answer(session_id, dimension, question="Q1", answer="A1")
        self._submit_answer(session_id, dimension, question="Q2", answer="A2")

        complete = self.client.post(
            f"/api/sessions/{session_id}/complete-dimension",
            json={"dimension": dimension},
        )
        self.assertEqual(complete.status_code, 200, complete.get_data(as_text=True))

    def test_document_upload_and_delete(self):
        self._register()
        session_id = self._create_session(topic="文档上传测试")["session_id"]

        upload_resp = self.client.post(
            f"/api/sessions/{session_id}/documents",
            data={"file": (io.BytesIO(b"# title\nhello"), "note.md")},
            content_type="multipart/form-data",
        )
        self.assertEqual(upload_resp.status_code, 200, upload_resp.get_data(as_text=True))
        upload_payload = upload_resp.get_json() or {}
        uploaded_document = upload_payload.get("uploaded_document") or {}
        self.assertTrue(uploaded_document.get("doc_id"))
        self.assertEqual(uploaded_document.get("name"), "note.md")

        get_session_resp = self.client.get(f"/api/sessions/{session_id}")
        self.assertEqual(get_session_resp.status_code, 200)
        materials = get_session_resp.get_json().get("reference_materials", [])
        self.assertEqual(len(materials), 1)
        self.assertEqual(materials[0]["name"], "note.md")
        self.assertEqual(materials[0].get("doc_id"), uploaded_document.get("doc_id"))

        cn_name = "开目AI产品手册.md"
        upload_cn_resp = self.client.post(
            f"/api/sessions/{session_id}/documents",
            data={"file": (io.BytesIO("# 说明\n中文文件名".encode("utf-8")), cn_name)},
            content_type="multipart/form-data",
        )
        self.assertEqual(upload_cn_resp.status_code, 200, upload_cn_resp.get_data(as_text=True))

        get_session_cn_resp = self.client.get(f"/api/sessions/{session_id}")
        self.assertEqual(get_session_cn_resp.status_code, 200)
        cn_materials = get_session_cn_resp.get_json().get("reference_materials", [])
        self.assertEqual(len(cn_materials), 2)
        self.assertIn(cn_name, [item.get("name") for item in cn_materials])

        bad_type_upload = self.client.post(
            f"/api/sessions/{session_id}/documents",
            data={"file": (io.BytesIO(b"evil"), "evil.exe")},
            content_type="multipart/form-data",
        )
        self.assertEqual(bad_type_upload.status_code, 400)

        delete_cn_resp = self.client.delete(
            f"/api/sessions/{session_id}/documents/{quote(cn_name)}"
        )
        self.assertEqual(delete_cn_resp.status_code, 200)

        delete_resp = self.client.delete(f"/api/sessions/{session_id}/documents/note.md")
        self.assertEqual(delete_resp.status_code, 200)

        invalid_name = self.client.delete(f"/api/sessions/{session_id}/documents/../hack.md")
        self.assertEqual(invalid_name.status_code, 400)

    def test_document_delete_by_doc_id_keeps_same_name_files(self):
        self._register()
        session_id = self._create_session(topic="文档唯一标识删除")["session_id"]

        first_resp = self.client.post(
            f"/api/sessions/{session_id}/documents",
            data={"file": (io.BytesIO(b"first"), "note.md")},
            content_type="multipart/form-data",
        )
        second_resp = self.client.post(
            f"/api/sessions/{session_id}/documents",
            data={"file": (io.BytesIO(b"second"), "note.md")},
            content_type="multipart/form-data",
        )
        self.assertEqual(first_resp.status_code, 200, first_resp.get_data(as_text=True))
        self.assertEqual(second_resp.status_code, 200, second_resp.get_data(as_text=True))

        first_doc = (first_resp.get_json() or {}).get("uploaded_document") or {}
        second_doc = (second_resp.get_json() or {}).get("uploaded_document") or {}
        self.assertTrue(first_doc.get("doc_id"))
        self.assertTrue(second_doc.get("doc_id"))
        self.assertNotEqual(first_doc.get("doc_id"), second_doc.get("doc_id"))

        delete_resp = self.client.delete(
            f"/api/sessions/{session_id}/documents/note.md?doc_id={quote(second_doc['doc_id'])}"
        )
        self.assertEqual(delete_resp.status_code, 200, delete_resp.get_data(as_text=True))
        delete_payload = delete_resp.get_json() or {}
        self.assertEqual(delete_payload.get("deleted_doc_id"), second_doc.get("doc_id"))

        get_session_resp = self.client.get(f"/api/sessions/{session_id}")
        self.assertEqual(get_session_resp.status_code, 200)
        materials = get_session_resp.get_json().get("reference_materials", [])
        self.assertEqual(len(materials), 1)
        self.assertEqual(materials[0].get("doc_id"), first_doc.get("doc_id"))

    def test_generate_scenario_with_ai_retries_and_normalizes_dirty_json(self):
        self._register()

        class FakeMessages:
            def __init__(self, responses):
                self.responses = list(responses)
                self.calls = 0

            def create(self, **_kwargs):
                self.calls += 1
                text = self.responses[min(self.calls - 1, len(self.responses) - 1)]
                return types.SimpleNamespace(
                    content=[types.SimpleNamespace(type="text", text=text)]
                )

        class FakeClient:
            def __init__(self, responses):
                self.messages = FakeMessages(responses)

        fake_client = FakeClient([
            "这次先解释一下设计思路，但没有返回 JSON。",
            """```json
{
  "name": "售后回访",
  "description": "用于识别售后回访中的问题归因与处理节奏",
  "dimensions": [
    {
      "name": "问题归因",
      "description": "确认问题来源与责任边界",
      "key_aspects": "问题来源,责任归属,升级条件"
    }
  ],
  "explanation": "先锁定问题归因，再决定后续处理优先级"
}
```""",
        ])

        old_resolve_ai_client = self.server.resolve_ai_client
        try:
            self.server.resolve_ai_client = lambda call_type="scenario_generate": fake_client
            response = self.client.post(
                "/api/scenarios/generate",
                json={"user_description": "我想做一套售后回访问题归因和处理节奏的访谈场景"},
            )
            self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
            payload = response.get_json() or {}
            generated = payload.get("generated_scenario") or {}
            self.assertTrue(payload.get("success"))
            self.assertEqual(fake_client.messages.calls, 2)
            self.assertEqual(generated.get("name"), "售后回访")
            self.assertEqual(generated.get("dimensions", [])[0].get("id"), "dim_1")
            self.assertEqual(generated.get("dimensions", [])[0].get("min_questions"), 2)
            self.assertEqual(generated.get("dimensions", [])[0].get("max_questions"), 4)
            self.assertEqual(generated.get("dimensions", [])[0].get("key_aspects"), ["问题来源", "责任归属", "升级条件"])
            self.assertEqual(generated.get("report", {}).get("type"), "standard")
            self.assertTrue(payload.get("ai_explanation"))
        finally:
            self.server.resolve_ai_client = old_resolve_ai_client

    def test_generate_scenario_with_ai_accepts_plain_text_fallback(self):
        self._register()

        class FakeMessages:
            def __init__(self, responses):
                self.responses = list(responses)
                self.calls = 0

            def create(self, **_kwargs):
                self.calls += 1
                text = self.responses[min(self.calls - 1, len(self.responses) - 1)]
                return types.SimpleNamespace(
                    content=[types.SimpleNamespace(type="text", text=text)]
                )

        class FakeClient:
            def __init__(self, responses):
                self.messages = FakeMessages(responses)

        fake_client = FakeClient([
            """场景名称：创建访谈
场景描述：适用于方案、项目和产品创建阶段的通用访谈配置
维度1：创建目标
关键点：创建动机、目标边界、预期成果
维度2：创建内容
描述：明确本次创建涉及的内容范围和优先级
关键点：核心内容、交付范围、优先级
维度3：实施条件
关键点：资源准备、协作机制、时间约束
设计思路：先明确目标和范围，再确认执行条件。"""
        ])

        old_resolve_ai_client = self.server.resolve_ai_client
        try:
            self.server.resolve_ai_client = lambda call_type="scenario_generate": fake_client
            response = self.client.post(
                "/api/scenarios/generate",
                json={"user_description": "我想生成一个用于项目和方案创建阶段的访谈场景"},
            )
            self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
            payload = response.get_json() or {}
            generated = payload.get("generated_scenario") or {}
            self.assertTrue(payload.get("success"))
            self.assertEqual(fake_client.messages.calls, 1)
            self.assertEqual(generated.get("name"), "创建访谈")
            self.assertEqual(len(generated.get("dimensions") or []), 3)
            self.assertEqual(generated.get("dimensions", [])[0].get("name"), "创建目标")
            self.assertEqual(
                generated.get("dimensions", [])[0].get("key_aspects"),
                ["创建动机", "目标边界", "预期成果"],
            )
            self.assertTrue(payload.get("ai_explanation"))
        finally:
            self.server.resolve_ai_client = old_resolve_ai_client

    def test_generate_scenario_with_ai_normalizes_alias_fields(self):
        self._register()

        class FakeMessages:
            def __init__(self, responses):
                self.responses = list(responses)
                self.calls = 0

            def create(self, **_kwargs):
                self.calls += 1
                text = self.responses[min(self.calls - 1, len(self.responses) - 1)]
                return types.SimpleNamespace(
                    content=[types.SimpleNamespace(type="text", text=text)]
                )

        class FakeClient:
            def __init__(self, responses):
                self.messages = FakeMessages(responses)

        fake_client = FakeClient([
            json.dumps(
                {
                    "scene_name": "技术评审",
                    "summary": "用于技术方案评审与风险识别的访谈配置",
                    "dims": [
                        {
                            "title": "风险识别",
                            "desc": "确认潜在技术风险与阻塞点",
                            "points": ["架构风险", "依赖风险", "交付风险"],
                        },
                        {
                            "label": "落地条件",
                            "focus": "评估资源、时间和协作条件",
                            "keywords": "资源约束,时间窗口,协作机制",
                        },
                    ],
                    "design_thinking": "先识别风险，再评估落地条件。",
                },
                ensure_ascii=False,
            )
        ])

        old_resolve_ai_client = self.server.resolve_ai_client
        try:
            self.server.resolve_ai_client = lambda call_type="scenario_generate": fake_client
            response = self.client.post(
                "/api/scenarios/generate",
                json={"user_description": "我想做一个技术方案评审和落地风险识别的访谈场景"},
            )
            self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
            payload = response.get_json() or {}
            generated = payload.get("generated_scenario") or {}
            self.assertEqual(generated.get("name"), "技术评审")
            self.assertEqual(generated.get("description"), "用于技术方案评审与风险识别的访谈配置")
            self.assertEqual(generated.get("dimensions", [])[0].get("name"), "风险识别")
            self.assertEqual(generated.get("dimensions", [])[1].get("name"), "落地条件")
            self.assertEqual(
                generated.get("dimensions", [])[1].get("key_aspects"),
                ["资源约束", "时间窗口", "协作机制"],
            )
            self.assertEqual(payload.get("ai_explanation"), "先识别风险，再评估落地条件。")
        finally:
            self.server.resolve_ai_client = old_resolve_ai_client

    def test_generate_scenario_with_ai_falls_back_to_local_draft_when_invalid(self):
        self._register()

        class FakeMessages:
            def __init__(self, responses):
                self.responses = list(responses)
                self.calls = 0

            def create(self, **_kwargs):
                self.calls += 1
                text = self.responses[min(self.calls - 1, len(self.responses) - 1)]
                return types.SimpleNamespace(
                    content=[types.SimpleNamespace(type="text", text=text)]
                )

        class FakeClient:
            def __init__(self, responses):
                self.messages = FakeMessages(responses)

        fake_client = FakeClient([
            "这是一次解释说明，但没有任何结构化内容。",
            "还是没有 JSON，也没有维度列表，请自由发挥。",
        ])

        old_resolve_ai_client = self.server.resolve_ai_client
        try:
            self.server.resolve_ai_client = lambda call_type="scenario_generate": fake_client
            response = self.client.post(
                "/api/scenarios/generate",
                json={"user_description": "我想做一个古典风格偏好评分和判断标准的访谈场景"},
            )
            self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
            payload = response.get_json() or {}
            generated = payload.get("generated_scenario") or {}
            self.assertTrue(payload.get("success"))
            self.assertEqual(payload.get("generation_mode"), "local_fallback")
            self.assertEqual(fake_client.messages.calls, 2)
            self.assertTrue(str(generated.get("name") or "").startswith("古典风格"))
            self.assertEqual(len(generated.get("dimensions") or []), 4)
            self.assertEqual(generated.get("dimensions", [])[0].get("name"), "评判目标")
            self.assertEqual(generated.get("report", {}).get("type"), "standard")
            self.assertIn("可编辑草案", payload.get("ai_explanation", ""))
        finally:
            self.server.resolve_ai_client = old_resolve_ai_client

    def test_custom_scenario_create_and_delete(self):
        self._register()
        create_resp = self.client.post(
            "/api/scenarios/custom",
            json={
                "name": "测试场景",
                "description": "用于自动化测试",
                "dimensions": [
                    {"name": "维度A", "description": "描述A", "key_aspects": ["x", "y"]},
                    {"name": "维度B", "description": "描述B", "key_aspects": ["m", "n"]},
                ],
                "report": {"type": "standard"},
            },
        )
        self.assertEqual(create_resp.status_code, 200, create_resp.get_data(as_text=True))
        scenario_id = create_resp.get_json()["scenario_id"]
        self.assertTrue(scenario_id.startswith("custom-"))

        get_resp = self.client.get(f"/api/scenarios/{scenario_id}")
        self.assertEqual(get_resp.status_code, 200)
        self.assertEqual(get_resp.get_json()["name"], "测试场景")

        delete_resp = self.client.delete(f"/api/scenarios/custom/{scenario_id}")
        self.assertEqual(delete_resp.status_code, 200)

        get_after_delete = self.client.get(f"/api/scenarios/{scenario_id}")
        self.assertEqual(get_after_delete.status_code, 404)

    def test_custom_scenario_is_owner_scoped(self):
        owner = self._register()
        create_resp = self.client.post(
            "/api/scenarios/custom",
            json={
                "name": "私有场景",
                "description": "仅限创建者可见",
                "dimensions": [
                    {"name": "维度A", "description": "描述A", "key_aspects": ["x", "y"]},
                ],
            },
        )
        self.assertEqual(create_resp.status_code, 200, create_resp.get_data(as_text=True))
        payload = create_resp.get_json() or {}
        scenario_id = payload.get("scenario_id")
        self.assertTrue(scenario_id)

        owner_list = self.client.get("/api/scenarios")
        self.assertEqual(owner_list.status_code, 200)
        self.assertTrue(any(item.get("id") == scenario_id for item in (owner_list.get_json() or [])))

        anonymous_client = self.server.app.test_client()
        anonymous_list = anonymous_client.get("/api/scenarios")
        self.assertEqual(anonymous_list.status_code, 200)
        self.assertFalse(any(item.get("id") == scenario_id for item in (anonymous_list.get_json() or [])))
        anonymous_detail = anonymous_client.get(f"/api/scenarios/{scenario_id}")
        self.assertEqual(anonymous_detail.status_code, 404)

        other_client = self.server.app.test_client()
        self._register(client=other_client)
        other_detail = other_client.get(f"/api/scenarios/{scenario_id}")
        self.assertEqual(other_detail.status_code, 404)
        other_delete = other_client.delete(f"/api/scenarios/custom/{scenario_id}")
        self.assertEqual(other_delete.status_code, 404)
        other_session = other_client.post(
            "/api/sessions",
            json={"topic": "越权使用场景", "scenario_id": scenario_id},
        )
        self.assertEqual(other_session.status_code, 404)

        owner_detail = self.client.get(f"/api/scenarios/{scenario_id}")
        self.assertEqual(owner_detail.status_code, 200)
        owner_payload = owner_detail.get_json() or {}
        self.assertNotIn("owner_user_id", owner_payload)
        self.assertNotIn(self.server.INSTANCE_SCOPE_FIELD, owner_payload)

    def test_custom_scenario_create_with_custom_report_schema(self):
        self._register()
        create_resp = self.client.post(
            "/api/scenarios/custom",
            json={
                "name": "自定义报告场景",
                "description": "验证 report.schema 入库与归一化",
                "dimensions": [
                    {"name": "维度A", "description": "描述A", "key_aspects": ["目标", "痛点"]},
                ],
                "report": {
                    "type": "standard",
                    "template": "custom",
                    "schema": {
                        "version": "v1",
                        "sections": [
                            {
                                "section_id": "exec_summary",
                                "title": "执行摘要",
                                "component": "paragraph",
                                "source": "overview",
                                "required": True,
                            },
                            {
                                "section_id": "priority_matrix",
                                "title": "优先级矩阵",
                                "component": "mermaid",
                                "source": "priority_matrix",
                                "required": True,
                            },
                            {
                                "section_id": "action_plan",
                                "title": "行动计划",
                                "component": "table",
                                "source": "actions",
                                "required": False,
                            },
                        ],
                    },
                },
            },
        )
        self.assertEqual(create_resp.status_code, 200, create_resp.get_data(as_text=True))
        payload = create_resp.get_json()
        scenario_id = payload["scenario_id"]
        scenario = payload["scenario"]
        report_cfg = scenario.get("report", {})
        self.assertEqual(report_cfg.get("template"), self.server.REPORT_TEMPLATE_CUSTOM_V1)
        self.assertEqual(report_cfg.get("type"), "standard")
        self.assertIsInstance(report_cfg.get("schema"), dict)
        self.assertEqual(report_cfg["schema"].get("version"), "v1")
        self.assertEqual(len(report_cfg["schema"].get("sections", [])), 3)

        list_resp = self.client.get("/api/scenarios")
        self.assertEqual(list_resp.status_code, 200)
        matched = next((item for item in (list_resp.get_json() or []) if item.get("id") == scenario_id), None)
        self.assertIsNotNone(matched)
        self.assertEqual(matched.get("report_template"), self.server.REPORT_TEMPLATE_CUSTOM_V1)
        self.assertTrue(matched.get("has_custom_report_schema"))

        delete_resp = self.client.delete(f"/api/scenarios/custom/{scenario_id}")
        self.assertEqual(delete_resp.status_code, 200)

    def test_submit_answer_preserves_both_logs_under_concurrent_requests(self):
        owner = self._register()
        payload = self._create_session(topic="并发提交测试")
        session_id = payload["session_id"]
        dimension = next(iter(payload.get("dimensions", {}).keys()))

        client_a = self.server.app.test_client()
        client_b = self.server.app.test_client()
        self._set_authenticated_client(client_a, owner)
        self._set_authenticated_client(client_b, owner)

        original_evaluate_answer_depth = self.server.evaluate_answer_depth
        barrier = threading.Barrier(2)

        def delayed_evaluate_answer_depth(*args, **kwargs):
            try:
                barrier.wait(timeout=0.2)
            except threading.BrokenBarrierError:
                pass
            return original_evaluate_answer_depth(*args, **kwargs)

        responses = []
        errors = []
        responses_lock = threading.Lock()
        self.server.evaluate_answer_depth = delayed_evaluate_answer_depth
        try:
            def submit(client, label):
                try:
                    response = client.post(
                        f"/api/sessions/{session_id}/submit-answer",
                        json={
                            "question": f"问题-{label}",
                            "answer": f"回答-{label}",
                            "dimension": dimension,
                            "options": ["A", "B"],
                            "is_follow_up": False,
                        },
                    )
                    with responses_lock:
                        responses.append((response.status_code, response.get_json() or {}))
                except Exception as exc:
                    with responses_lock:
                        errors.append(str(exc))

            threads = [
                threading.Thread(target=submit, args=(client_a, "A")),
                threading.Thread(target=submit, args=(client_b, "B")),
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
        finally:
            self.server.evaluate_answer_depth = original_evaluate_answer_depth

        self.assertFalse(errors, errors)
        self.assertEqual([200, 200], sorted(status for status, _payload in responses))

        final_resp = self.client.get(f"/api/sessions/{session_id}")
        self.assertEqual(final_resp.status_code, 200, final_resp.get_data(as_text=True))
        final_payload = final_resp.get_json() or {}
        interview_log = final_payload.get("interview_log", [])
        self.assertEqual(2, len(interview_log), interview_log)
        self.assertEqual({"回答-A", "回答-B"}, {item.get("answer") for item in interview_log})

    def test_custom_scenario_create_with_solution_dsl(self):
        self._register()
        create_resp = self.client.post(
            "/api/scenarios/custom",
            json={
                "name": "自定义方案场景",
                "description": "验证 solution.dsl 编译与场景摘要输出",
                "dimensions": [
                    {"name": "现状诊断", "description": "识别当前问题", "key_aspects": ["问题", "影响"]},
                    {"name": "目标蓝图", "description": "明确目标状态", "key_aspects": ["目标", "边界"]},
                ],
                "solution": {
                    "mode": "dsl",
                    "dsl": {
                        "hero_focus": "推进判断",
                        "solution_outline": ["现状问题", "目标蓝图", "方案对比", "实施路径"],
                        "emphasis": ["风险边界", "下一步推进"],
                    },
                },
            },
        )
        self.assertEqual(create_resp.status_code, 200, create_resp.get_data(as_text=True))
        payload = create_resp.get_json() or {}
        scenario_id = payload["scenario_id"]
        scenario = payload["scenario"]

        self.assertEqual((scenario.get("solution", {}) or {}).get("mode"), "dsl")
        compiled_schema = scenario.get("compiled_solution_schema", {}) or {}
        self.assertEqual(compiled_schema.get("version"), "v1")
        self.assertEqual(
            [item.get("section_id") for item in compiled_schema.get("sections", [])[:6]],
            ["decision", "current-state", "target-blueprint", "option-compare", "roadmap", "risks"],
        )

        detail_resp = self.client.get(f"/api/scenarios/{scenario_id}")
        self.assertEqual(detail_resp.status_code, 200)
        detail_payload = detail_resp.get_json() or {}
        self.assertEqual((detail_payload.get("meta", {}) or {}).get("source"), "user_defined")
        self.assertTrue((detail_payload.get("compiled_solution_schema", {}) or {}).get("sections"))

        list_resp = self.client.get("/api/scenarios")
        self.assertEqual(list_resp.status_code, 200)
        matched = next((item for item in (list_resp.get_json() or []) if item.get("id") == scenario_id), None)
        self.assertIsNotNone(matched)
        self.assertTrue(matched.get("has_solution_schema"))
        self.assertEqual(matched.get("solution_mode"), "dsl")
        self.assertGreaterEqual(int(matched.get("solution_sections_count") or 0), 6)
        self.assertEqual(matched.get("scenario_source"), "user_defined")

        delete_resp = self.client.delete(f"/api/scenarios/custom/{scenario_id}")
        self.assertEqual(delete_resp.status_code, 200)

    def test_custom_scenario_persists_after_loader_reinitialize(self):
        self._register()
        create_resp = self.client.post(
            "/api/scenarios/custom",
            json={
                "name": "跨重载场景",
                "description": "验证应用更新后自定义场景不会被覆盖",
                "dimensions": [
                    {"name": "现状判断", "description": "确认当前状态", "key_aspects": ["问题", "影响"]},
                    {"name": "推进路径", "description": "确定下一步动作", "key_aspects": ["目标", "节奏"]},
                ],
                "solution": {
                    "mode": "schema",
                    "schema": {
                        "version": "v1",
                        "hero": {"focus": "推进判断"},
                        "sections": [
                            "推进判断",
                            "风险边界",
                            "下一步动作",
                        ],
                    },
                },
            },
        )
        self.assertEqual(create_resp.status_code, 200, create_resp.get_data(as_text=True))
        payload = create_resp.get_json() or {}
        scenario_id = payload.get("scenario_id")
        self.assertTrue(scenario_id)

        from scripts import scenario_loader as scenario_loader_module

        reloaded_loader = scenario_loader_module.ScenarioLoader(
            scenarios_dir=self.server.scenario_loader.scenarios_dir,
            builtin_dir=self.server.scenario_loader.builtin_dir,
            custom_dir=self.server.scenario_loader.custom_dir,
            migrate_legacy_custom_dir=self.server.scenario_loader.legacy_custom_dir,
        )
        scenario_loader_module._scenario_loader = reloaded_loader
        self.server.scenario_loader = reloaded_loader

        detail_resp = self.client.get(f"/api/scenarios/{scenario_id}")
        self.assertEqual(detail_resp.status_code, 200, detail_resp.get_data(as_text=True))
        detail_payload = detail_resp.get_json() or {}
        self.assertEqual(detail_payload.get("name"), "跨重载场景")
        self.assertEqual((detail_payload.get("solution", {}) or {}).get("mode"), "schema")
        self.assertEqual(
            (((detail_payload.get("solution", {}) or {}).get("schema", {}) or {}).get("sections") or [])[:3],
            ["推进判断", "风险边界", "下一步动作"],
        )
        compiled_schema = detail_payload.get("compiled_solution_schema", {}) or {}
        self.assertEqual(
            [item.get("title") for item in compiled_schema.get("sections", [])[:3]],
            ["推进判断", "风险边界", "下一步推进"],
        )

        list_resp = self.client.get("/api/scenarios")
        self.assertEqual(list_resp.status_code, 200, list_resp.get_data(as_text=True))
        matched = next((item for item in (list_resp.get_json() or []) if item.get("id") == scenario_id), None)
        self.assertIsNotNone(matched)
        self.assertEqual(matched.get("scenario_source"), "user_defined")
        self.assertEqual(matched.get("solution_mode"), "schema")
        self.assertEqual(int(matched.get("solution_sections_count") or 0), 3)

        delete_resp = self.client.delete(f"/api/scenarios/custom/{scenario_id}")
        self.assertEqual(delete_resp.status_code, 200)

    def test_report_template_validate_and_preview_api(self):
        self._register()

        schema = {
            "version": "v1",
            "sections": [
                {
                    "section_id": "summary",
                    "title": "执行摘要",
                    "component": "paragraph",
                    "source": "overview",
                    "required": True,
                },
                {
                    "section_id": "matrix",
                    "title": "优先级矩阵",
                    "component": "mermaid",
                    "source": "priority_matrix",
                    "required": True,
                },
                {
                    "section_id": "actions",
                    "title": "行动计划",
                    "component": "table",
                    "source": "actions",
                    "required": False,
                },
            ],
        }

        validate_ok = self.client.post("/api/report-templates/validate", json={"schema": schema})
        self.assertEqual(validate_ok.status_code, 200, validate_ok.get_data(as_text=True))
        validated = validate_ok.get_json()
        self.assertTrue(validated.get("success"))
        self.assertEqual(validated.get("schema", {}).get("version"), "v1")
        self.assertEqual(len(validated.get("schema", {}).get("sections", [])), 3)

        validate_bad = self.client.post(
            "/api/report-templates/validate",
            json={
                "schema": {
                    "sections": [
                        {
                            "section_id": "bad",
                            "title": "无效章节",
                            "component": "html",
                            "source": "overview",
                        }
                    ]
                }
            },
        )
        self.assertEqual(validate_bad.status_code, 400)
        bad_payload = validate_bad.get_json() or {}
        self.assertFalse(bad_payload.get("success"))
        self.assertTrue(bad_payload.get("details"))

        preview_resp = self.client.post(
            "/api/report-templates/preview",
            json={"topic": "模板预览测试", "schema": schema},
        )
        self.assertEqual(preview_resp.status_code, 200, preview_resp.get_data(as_text=True))
        preview_payload = preview_resp.get_json()
        self.assertTrue(preview_payload.get("success"))
        markdown = preview_payload.get("preview_markdown", "")
        self.assertIn("# 模板预览测试 访谈报告", markdown)
        self.assertIn("## 1. 执行摘要", markdown)
        self.assertIn("## 2. 优先级矩阵", markdown)
        self.assertIn("```mermaid", markdown)
        self.assertIn("| 编号 | 行动项 | Owner | 时间计划 | 验收指标 | 证据 |", markdown)

    def test_metrics_and_summaries_authenticated(self):
        # 触发列表接口指标
        self.client.get("/api/sessions")
        self.client.get("/api/reports")
        self.server.record_question_generation_runtime_sample(
            durations={
                "total_ms": 150.5,
                "session_load_ms": 12.5,
                "prompt_build_ms": 8.0,
                "ai_call_ms": 120.0,
                "parse_repair_ms": 10.0,
            },
            runtime_profile="question_probe_light",
            tier_used="fast:question",
            selection_reason="unit_test",
            outcome="completed",
        )
        self.server.record_report_generation_runtime_sample(
            durations={
                "total_ms": 267.0,
                "session_load_ms": 15.0,
                "evidence_pack_ms": 25.0,
                "draft_gen_ms": 180.0,
                "review_ms": 35.0,
                "persist_ms": 12.0,
            },
            runtime_profile="balanced",
            path="v3_pipeline",
            reason="unit_test",
            outcome="completed",
        )

        with self.server.app.test_request_context("/api/metrics?last_n=20"):
            metrics = self.server.get_metrics.__wrapped__()
        self.assertEqual(metrics.status_code, 200)
        metrics_payload = metrics.get_json()
        self.assertTrue(
            "summary" in metrics_payload or "total_calls" in metrics_payload,
            f"unexpected metrics payload: {metrics_payload}",
        )
        self.assertIn("list_endpoints", metrics_payload)
        self.assertIn("endpoints", metrics_payload["list_endpoints"])
        self.assertIn("cache", metrics_payload["list_endpoints"])
        self.assertIn("sessions_list", metrics_payload["list_endpoints"]["endpoints"])
        self.assertIn("reports_list", metrics_payload["list_endpoints"]["endpoints"])
        self.assertIn("list_overload", metrics_payload)
        self.assertIn("report_generation_queue", metrics_payload)
        self.assertIn("running", metrics_payload["report_generation_queue"])
        self.assertIn("pending", metrics_payload["report_generation_queue"])
        self.assertIn("submitted", metrics_payload["report_generation_queue"])
        self.assertIn("rejected", metrics_payload["report_generation_queue"])
        self.assertIn("question_generation_runtime", metrics_payload)
        self.assertEqual(metrics_payload["question_generation_runtime"]["calls"], 1)
        self.assertEqual(metrics_payload["question_generation_runtime"]["completed"], 1)
        self.assertEqual(
            metrics_payload["question_generation_runtime"]["last_profile"],
            "question_probe_light",
        )
        self.assertIn("ai_call_ms", metrics_payload["question_generation_runtime"]["stages"])
        self.assertIn("report_generation_runtime", metrics_payload)
        self.assertEqual(metrics_payload["report_generation_runtime"]["calls"], 1)
        self.assertEqual(metrics_payload["report_generation_runtime"]["completed"], 1)
        self.assertEqual(metrics_payload["report_generation_runtime"]["last_path"], "v3_pipeline")
        self.assertIn("draft_gen_ms", metrics_payload["report_generation_runtime"]["stages"])

        with self.server.app.test_request_context("/api/metrics/reset", method="POST", json={}):
            reset = self.server.reset_metrics.__wrapped__()
        self.assertEqual(reset.status_code, 200)
        self.assertTrue(reset.get_json().get("success"))
        with self.server.app.test_request_context("/api/metrics"):
            metrics_after_reset = self.server.get_metrics.__wrapped__()
        self.assertEqual(metrics_after_reset.status_code, 200)
        metrics_after_reset_payload = metrics_after_reset.get_json()
        self.assertEqual(metrics_after_reset_payload["question_generation_runtime"]["calls"], 0)
        self.assertEqual(metrics_after_reset_payload["report_generation_runtime"]["calls"], 0)

        with self.server.app.test_request_context("/api/summaries"):
            summaries = self.server.get_summaries_info.__wrapped__()
        if isinstance(summaries, tuple):
            summaries = summaries[0]
        self.assertEqual(summaries.status_code, 200)
        self.assertIn("cached_count", summaries.get_json())
        self.assertNotIn("cache_directory", summaries.get_json())

        with self.server.app.test_request_context("/api/summaries/clear", method="POST", json={}):
            clear_resp = self.server.clear_summaries_cache.__wrapped__()
        if isinstance(clear_resp, tuple):
            clear_resp = clear_resp[0]
        self.assertEqual(clear_resp.status_code, 200)
        self.assertTrue(clear_resp.get_json().get("success"))

    def test_build_report_generation_payload_exposes_runtime_fields(self):
        record = {
            "active": False,
            "status": "completed",
            "state": "completed",
            "stage_label": "已完成",
            "detail_key": "finished",
            "detail_label": "报告已生成",
            "next_hint": "可直接查看报告",
            "eta_hint": "",
            "estimated_wait_seconds": 0,
            "runtime_timings": {
                "session_load_ms": 10.0,
                "draft_gen_ms": 120.0,
                "review_ms": 40.0,
            },
            "runtime_summary": {
                "path": "v3_pipeline",
                "reason": "quality_gate_passed",
                "outcome": "completed",
                "total_ms": 190.0,
            },
        }

        payload = self.server.build_report_generation_payload(record)

        self.assertEqual(payload["state"], "completed")
        self.assertEqual(payload["stage_label"], "已完成")
        self.assertEqual(payload["detail_key"], "finished")
        self.assertEqual(payload["detail_label"], "报告已生成")
        self.assertEqual(payload["next_hint"], "可直接查看报告")
        self.assertEqual(payload["estimated_wait_seconds"], 0)
        self.assertEqual(payload["runtime_timings"]["draft_gen_ms"], 120.0)
        self.assertEqual(payload["runtime_summary"]["path"], "v3_pipeline")
        self.assertEqual(payload["runtime_summary"]["outcome"], "completed")

    def test_sync_report_generation_queue_metadata_sets_queue_detail_fields(self):
        session_id = "session-report-queue-detail"
        old_status = dict(getattr(self.server, "report_generation_status", {}))
        try:
            self.server.report_generation_status[session_id] = {
                "active": True,
                "state": "queued",
                "stage_index": 0,
                "total_stages": 6,
                "progress": 5,
                "message": "报告任务正在处理中...",
            }

            snapshot = {
                "pending": 3,
                "running": 2,
                "queue_positions": {session_id: 2},
            }
            self.server.sync_report_generation_queue_metadata(session_id, snapshot=snapshot)
            record = self.server.get_report_generation_record(session_id)

            self.assertEqual(record["queue_position"], 2)
            self.assertEqual(record["estimated_wait_seconds"], 55)
            self.assertEqual(record["detail_key"], "queue_wait")
            self.assertIn("前方还有 2 个待执行任务", record["next_hint"])
            self.assertIn("预计还需等待约 55 秒", record["eta_hint"])
            self.assertIn("2 个正在执行", record["eta_hint"])
        finally:
            self.server.report_generation_status.clear()
            self.server.report_generation_status.update(old_status)

    def test_estimate_report_generation_wait_seconds_accounts_for_running_workers(self):
        self.assertEqual(
            self.server.estimate_report_generation_wait_seconds(queue_position=1, running=1, max_workers=2),
            0,
        )
        self.assertEqual(
            self.server.estimate_report_generation_wait_seconds(queue_position=2, running=2, max_workers=2),
            55,
        )
        self.assertEqual(
            self.server.estimate_report_generation_wait_seconds(queue_position=3, running=2, max_workers=2),
            110,
        )

    def test_update_report_generation_status_tracks_phase_history(self):
        session_id = "session-report-phase-history"
        old_status = dict(getattr(self.server, "report_generation_status", {}))
        try:
            self.server.report_generation_status.clear()
            self.server.update_report_generation_status(
                session_id,
                "queued",
                message="报告任务正在处理中...",
                detail_key="queue_wait",
            )
            self.server.update_report_generation_status(
                session_id,
                "building_prompt",
                message="正在构建证据包...",
                detail_key="evidence_pack",
            )
            record = self.server.get_report_generation_record(session_id)
            payload = self.server.build_report_generation_payload(record)

            self.assertIn("started_at", record)
            self.assertIn("phase_history", payload)
            self.assertEqual(len(payload["phase_history"]), 2)
            self.assertEqual(payload["phase_history"][0]["detail_key"], "queue_wait")
            self.assertEqual(payload["phase_history"][1]["detail_key"], "evidence_pack")
        finally:
            self.server.report_generation_status.clear()
            self.server.report_generation_status.update(old_status)

    def test_report_v3_runtime_config_balanced_release_mode_is_more_conservative(self):
        old_profile = self.server.REPORT_V3_PROFILE
        old_release = self.server.REPORT_V3_RELEASE_CONSERVATIVE_MODE
        old_failover = self.server.REPORT_V3_FAILOVER_ENABLED
        try:
            self.server.REPORT_V3_PROFILE = "balanced"
            self.server.REPORT_V3_RELEASE_CONSERVATIVE_MODE = True
            self.server.REPORT_V3_FAILOVER_ENABLED = True

            runtime_cfg = self.server.get_report_v3_runtime_config("balanced")

            self.assertEqual(runtime_cfg["profile"], "balanced")
            self.assertTrue(runtime_cfg["release_conservative_mode"])
            self.assertLessEqual(runtime_cfg["draft_timeout"], 60.0)
            self.assertLessEqual(runtime_cfg["draft_timeout_cap"], 68.0)
            self.assertLessEqual(runtime_cfg["review_timeout"], 60.0)
            self.assertLessEqual(runtime_cfg["draft_max_tokens"], 2600)
            self.assertLessEqual(runtime_cfg["draft_token_floor"], 1600)
            self.assertLessEqual(runtime_cfg["draft_facts_limit"], 18)
            self.assertEqual(runtime_cfg["review_base_rounds"], 1)
            self.assertEqual(runtime_cfg["quality_fix_rounds"], 0)
            self.assertFalse(runtime_cfg["review_repair_retry_enabled"])
            self.assertTrue(runtime_cfg["skip_model_review"])
            self.assertTrue(runtime_cfg["draft_strict_primary_lane"])
            self.assertFalse(runtime_cfg["draft_allow_alternate_lane"])
            self.assertFalse(runtime_cfg["salvage_on_quality_gate_failure"])
            self.assertFalse(runtime_cfg["failover_on_single_issue"])
            self.assertFalse(runtime_cfg["failover_enabled"])
        finally:
            self.server.REPORT_V3_PROFILE = old_profile
            self.server.REPORT_V3_RELEASE_CONSERVATIVE_MODE = old_release
            self.server.REPORT_V3_FAILOVER_ENABLED = old_failover

    def test_build_report_prompt_with_options_compact_mode_uses_evidence_snapshot(self):
        session = {
            "topic": "报告紧凑回退验证",
            "description": "验证 V3 失败后的紧凑 prompt",
            "interview_log": [
                {"dimension": "cost", "question": "预算范围？", "answer": "控制在 200 万以内"},
                {"dimension": "timeline", "question": "计划周期？", "answer": "希望 3 个月内完成 MVP"},
            ],
            "scenario_config": {"report": {"type": "standard"}},
            "reference_materials": [
                {
                    "name": "超长资料",
                    "content": "这是非常长的资料。" * 600,
                    "source": "user",
                }
            ],
        }
        evidence_pack = {
            "dimension_coverage": {
                "cost": {
                    "name": "预算约束",
                    "coverage_percent": 80,
                    "formal_count": 1,
                    "follow_up_count": 0,
                    "missing_aspects": ["投资回收周期"],
                }
            },
            "facts": [
                {
                    "q_id": "Q1",
                    "dimension": "cost",
                    "dimension_name": "预算约束",
                    "question": "预算范围？",
                    "answer": "控制在 200 万以内",
                    "quality_score": 0.82,
                    "answer_evidence_class": "rich_option",
                    "hard_triggered": False,
                    "is_follow_up": False,
                }
            ],
            "contradictions": [],
            "unknowns": [{"q_id": "Q2", "dimension": "周期", "reason": "里程碑未完全明确"}],
            "blindspots": [{"dimension": "预算约束", "aspect": "投资回收周期"}],
            "report_type": "standard",
        }

        prompt = self.server.build_report_prompt_with_options(
            session,
            evidence_pack=evidence_pack,
            compact_mode=True,
        )

        self.assertIn("证据快照", prompt)
        self.assertIn("高价值证据", prompt)
        self.assertIn("超长资料", prompt)
        self.assertNotIn("这是非常长的资料。" * 50, prompt)
        self.assertLess(len(prompt), 4000)

    def test_build_report_draft_prompt_v3_compact_mode_is_shorter(self):
        session = {
            "topic": "报告草案压缩验证",
            "description": "验证 release conservative 下草案 prompt 进一步缩短",
        }
        evidence_pack = {
            "report_type": "standard",
            "dimension_coverage": {
                "d1": {"name": "目标", "coverage_percent": 88, "formal_count": 3, "follow_up_count": 1, "missing_aspects": ["边界", "指标"]},
                "d2": {"name": "流程", "coverage_percent": 76, "formal_count": 2, "follow_up_count": 1, "missing_aspects": ["交接"]},
                "d3": {"name": "资源", "coverage_percent": 62, "formal_count": 2, "follow_up_count": 0, "missing_aspects": ["预算"]},
                "d4": {"name": "风险", "coverage_percent": 58, "formal_count": 1, "follow_up_count": 1, "missing_aspects": ["兜底"]},
                "d5": {"name": "验收", "coverage_percent": 51, "formal_count": 1, "follow_up_count": 0, "missing_aspects": ["量化标准"]},
            },
            "facts": [
                {
                    "q_id": f"Q{i}",
                    "dimension_name": "目标",
                    "question": "这是一个很长的问题描述" * 6,
                    "answer": "这是一个更长的回答描述，用来验证 compact prompt 会裁剪问题和答案长度。" * 6,
                    "quality_score": 0.82,
                    "answer_evidence_class": "explicit",
                }
                for i in range(1, 20)
            ],
            "contradictions": [{"detail": "交付节奏与资源排期存在冲突" * 3, "evidence_refs": ["Q1", "Q2"]}] * 8,
            "unknowns": [{"q_id": f"Q{i}", "dimension": "验收", "reason": "指标定义仍不明确" * 3} for i in range(1, 8)],
            "blindspots": [{"dimension": "风险", "aspect": "回退预案尚未确认" * 3}] * 8,
        }

        full_prompt = self.server.build_report_draft_prompt_v3(session, evidence_pack, facts_limit=18)
        compact_prompt = self.server.build_report_draft_prompt_v3(
            session,
            evidence_pack,
            facts_limit=18,
            compact_mode=True,
        )

        self.assertLess(len(compact_prompt), len(full_prompt))
        self.assertLess(compact_prompt.count("\n- "), full_prompt.count("\n- "))

    def test_build_report_quality_meta_fallback_reuses_provided_evidence_pack(self):
        evidence_pack = {
            "overall_coverage": 0.66,
            "contradictions": [{"detail": "冲突"}],
            "facts": [{"q_id": "Q1"}],
            "unknowns": [{"q_id": "Q2"}],
            "blindspots": [{"dimension": "范围", "aspect": "指标"}],
        }

        original_builder = self.server.build_report_evidence_pack
        try:
            def fail_builder(_session):
                raise AssertionError("不应回退重建证据包")

            self.server.build_report_evidence_pack = fail_builder
            quality_meta = self.server.build_report_quality_meta_fallback(
                {"topic": "质量元数据复用"},
                mode="legacy_ai_fallback",
                evidence_pack=evidence_pack,
            )
        finally:
            self.server.build_report_evidence_pack = original_builder

        self.assertEqual(quality_meta["mode"], "legacy_ai_fallback")
        self.assertEqual(quality_meta["evidence_context"]["facts_count"], 1)
        self.assertEqual(quality_meta["evidence_context"]["unknown_count"], 1)
        self.assertEqual(quality_meta["evidence_context"]["blindspots_count"], 1)

    def test_can_release_conservative_soft_pass_v3_only_allows_soft_quality_gate_issues(self):
        quality_meta = {
            "evidence_coverage": 0.68,
            "actionability": 0.41,
            "table_readiness": 0.56,
        }
        runtime_cfg = {"release_conservative_mode": True}
        soft_issues = [
            {"type": "quality_gate_expression"},
            {"type": "quality_gate_weak_binding"},
            {"type": "style_template_violation"},
        ]
        hard_issues = soft_issues + [{"type": "quality_gate_evidence"}]

        self.assertTrue(
            self.server.can_release_conservative_soft_pass_v3(
                soft_issues,
                quality_meta,
                runtime_cfg,
            )
        )
        self.assertFalse(
            self.server.can_release_conservative_soft_pass_v3(
                hard_issues,
                quality_meta,
                runtime_cfg,
            )
        )

    def test_safe_load_session_uses_cloud_payload_cache(self):
        self.server.set_license_enforcement_override(False)
        self._register()
        created = self._create_session(topic="会话热缓存命中")
        target_session_id = created["session_id"]
        session_file = self.server.SESSIONS_DIR / f"{target_session_id}.json"
        baseline = self.server.safe_load_session(session_file)
        self.assertIsInstance(baseline, dict)

        original_use_cloud = self.server._use_pure_cloud_session_storage
        original_load_store_entry = self.server._load_session_store_entry
        original_store_signature = self.server._get_session_store_signature
        load_calls = []
        signature_calls = []

        def fake_load_store_entry(*, session_id="", file_name=""):
            request_session_id = str(session_id or "").strip()
            request_file_name = str(file_name or "").strip()
            load_calls.append(request_session_id or request_file_name)
            if request_session_id and request_session_id != target_session_id:
                return None, None
            if request_file_name and request_file_name != session_file.name:
                return None, None
            return json.loads(json.dumps(baseline, ensure_ascii=False)), (123456789, 2048)

        def fake_store_signature(*args, **kwargs):
            signature_calls.append((args, kwargs))
            return None

        self.server._use_pure_cloud_session_storage = lambda: True
        self.server._load_session_store_entry = fake_load_store_entry
        self.server._get_session_store_signature = fake_store_signature
        self.addCleanup(setattr, self.server, "_use_pure_cloud_session_storage", original_use_cloud)
        self.addCleanup(setattr, self.server, "_load_session_store_entry", original_load_store_entry)
        self.addCleanup(setattr, self.server, "_get_session_store_signature", original_store_signature)
        self.server._invalidate_session_payload_cache(session_id=target_session_id, file_name=session_file.name)

        first = self.server.safe_load_session(session_file)
        second = self.server.safe_load_session(session_file)
        payload_cache_signature = self.server._get_session_payload_cache_signature(
            session_id=target_session_id,
            file_name=session_file.name,
        )
        file_signature = self.server.get_file_signature(session_file)

        self.assertEqual(load_calls, [target_session_id])
        self.assertEqual(first.get("session_id"), target_session_id)
        self.assertEqual(second.get("session_id"), target_session_id)
        self.assertEqual(payload_cache_signature, (123456789, 2048))
        self.assertIsInstance(file_signature, tuple)
        self.assertEqual(len(file_signature), 2)
        self.assertEqual(signature_calls, [])

        first["topic"] = "已污染的本地副本"
        third = self.server.safe_load_session(session_file)
        self.assertEqual(third.get("topic"), baseline.get("topic"))

    def test_save_session_json_and_sync_uses_compact_payload_for_cloud_store(self):
        self.server.set_license_enforcement_override(False)
        self._register()
        created = self._create_session(topic="云端紧凑会话存储", description="用于验证 payload 压缩")
        session_id = created["session_id"]
        session_file = self.server.SESSIONS_DIR / f"{session_id}.json"
        session_data = self.server.safe_load_session(session_file)
        session_data["description"] = "包含更多字段，验证 session_store 使用紧凑 JSON"
        session_data.setdefault("dimensions", {}).setdefault("extra_dim", {"coverage": 0, "items": []})

        original_use_cloud = self.server._use_pure_cloud_session_storage
        self.server._use_pure_cloud_session_storage = lambda: True
        self.addCleanup(setattr, self.server, "_use_pure_cloud_session_storage", original_use_cloud)

        signature = self.server.save_session_json_and_sync(session_file, session_data)
        compact_payload = self.server._serialize_session_payload(session_data, compact=True)

        with self.server.get_meta_index_connection() as conn:
            row = conn.execute(
                "SELECT payload_json, payload_size FROM session_store WHERE session_id = ? LIMIT 1",
                (session_id,),
            ).fetchone()

        self.assertIsNotNone(row)
        self.assertEqual(str(row["payload_json"] or ""), compact_payload)
        self.assertNotIn("\n  ", str(row["payload_json"] or ""))
        self.assertEqual(int(row["payload_size"] or 0), len(compact_payload.encode("utf-8")))
        self.assertEqual(signature[1], len(compact_payload.encode("utf-8")))

    def test_safe_load_session_applies_report_runtime_meta_from_session_index(self):
        self.server.set_license_enforcement_override(False)
        self._register()
        created = self._create_session(topic="索引覆盖报告绑定")
        session_id = created["session_id"]
        session_file = self.server.SESSIONS_DIR / f"{session_id}.json"
        baseline = self.server.safe_load_session(session_file)
        owner_user_id = int(baseline.get("owner_user_id") or 0)

        report_name = f"{session_id}-index-report.md"
        self.server.save_report_content_and_sync(report_name, "# 测试报告\n")
        self.server.set_report_owner_id(report_name, owner_user_id)

        indexed_session = json.loads(json.dumps(baseline, ensure_ascii=False))
        indexed_session["status"] = "completed"
        indexed_session["updated_at"] = "2026-03-31T10:00:00+08:00"
        indexed_session["current_report_name"] = report_name
        indexed_session["current_report_updated_at"] = "2026-03-31T10:00:00+08:00"
        indexed_session["last_report_name"] = report_name
        indexed_session["last_report_quality_meta"] = {"score": 0.92, "path": "v3_pipeline"}

        self.server.sync_session_index_and_bound_reports(session_file, indexed_session)
        self.server._invalidate_session_payload_cache(session_id=session_id, file_name=session_file.name)

        loaded = self.server.safe_load_session(session_file)

        self.assertEqual(loaded.get("status"), "completed")
        self.assertEqual(loaded.get("current_report_name"), report_name)
        self.assertEqual(loaded.get("last_report_name"), report_name)
        self.assertEqual(loaded.get("current_report_updated_at"), "2026-03-31T10:00:00+08:00")
        self.assertEqual(loaded.get("last_report_quality_meta", {}).get("score"), 0.92)
        self.assertEqual(Path(loaded.get("current_report_path", "")).name, report_name)

    def test_report_generation_and_report_endpoints(self):
        user = self._register()
        professional_code = self._generate_license_batch(level_key="professional", note="报告链路专业版")["licenses"][0]["code"]
        activate_payload = self._activate_license(professional_code)
        self.assertEqual("professional", (activate_payload.get("level") or {}).get("key"))
        created = self._create_session(topic="报告生成链路")
        session_id = created["session_id"]
        dimension = list(created["dimensions"].keys())[0]
        submit_resp = self.client.post(
            f"/api/sessions/{session_id}/submit-answer",
            json={
                "question": "需求是什么？",
                "answer": "可控的技术实现",
                "dimension": dimension,
                "options": ["细粒度权限控制", "敏感数据脱敏", "导出审计", "计算隔离"],
                "multi_select": False,
                "other_selected": True,
                "other_answer_text": "可控的技术实现",
                "is_follow_up": False,
            },
        )
        self.assertEqual(submit_resp.status_code, 200, submit_resp.get_data(as_text=True))

        gen_resp = self.client.post(
            f"/api/sessions/{session_id}/generate-report",
            json={"report_profile": "quality"},
        )
        self.assertEqual(gen_resp.status_code, 202, gen_resp.get_data(as_text=True))
        first_payload = gen_resp.get_json() or {}
        self.assertEqual(first_payload.get("report_profile"), "quality")

        status_payload = self._wait_report_generation(session_id)
        self.assertEqual(status_payload.get("report_profile"), "quality")
        report_name = status_payload.get("report_name")
        self.assertTrue(report_name)
        solution_cache_path = self.server.get_solution_payload_cache_path(report_name)
        self.assertTrue(solution_cache_path.exists(), str(solution_cache_path))
        solution_cache_payload = json.loads(solution_cache_path.read_text(encoding="utf-8"))
        self.assertEqual(solution_cache_payload.get("report_name"), report_name)
        self.assertEqual(solution_cache_payload.get("cache_version"), self.server.SOLUTION_PAYLOAD_CACHE_VERSION)
        sidecar_snapshot = self.server.read_solution_sidecar(report_name)
        if sidecar_snapshot:
            self.assertEqual(sidecar_snapshot.get("snapshot_stage"), "final_report")

        reports_resp = self.client.get("/api/reports")
        self.assertEqual(reports_resp.status_code, 200)
        report_items = reports_resp.get_json() or []
        report_names = [item["name"] for item in report_items]
        self.assertIn(report_name, report_names)
        report_meta = next(item for item in report_items if item.get("name") == report_name)
        self.assertEqual(report_meta.get("session_id"), session_id)
        self.assertEqual(report_meta.get("topic"), created.get("topic"))
        self.assertTrue(report_meta.get("scenario_name"))
        self.assertTrue(report_meta.get("report_template"))
        self.assertEqual(report_meta.get("report_type"), "standard")

        get_report_resp = self.client.get(f"/api/reports/{report_name}")
        self.assertEqual(get_report_resp.status_code, 200)
        content = get_report_resp.get_json().get("content", "")
        self.assertIn("访谈报告", content)
        self.assertIn("**生成日期**:", content)
        self.assertIn("**报告编号**: deep-vision-", content)
        self.assertIn("问题 1：需求是什么？", content)
        self.assertIn("】问题 1：需求是什么？", content)
        self.assertNotIn("Q1:", content)
        self.assertIn("<div><strong>回答：</strong></div>", content)
        self.assertIn("<div>☐ 细粒度权限控制</div>", content)
        self.assertIn("<div>☑ 其他（自由输入）：可控的技术实现</div>", content)
        self.assertIn("☐", content)
        self.assertIn("☑", content)
        self.assertNotIn("- ☐", content)
        self.assertNotIn("**维度**:", content)
        self.assertNotIn("记录时间", content)
        self.assertIn("本次访谈共收集了 1 个问题的回答", content)
        self.assertNotIn("点击展开/收起", content)

        solution_resp = self.client.get(f"/api/reports/{report_name}/solution")
        self.assertEqual(solution_resp.status_code, 200)
        solution_payload = solution_resp.get_json() or {}
        self.assertEqual(solution_payload.get("report_name"), report_name)
        self.assertTrue((solution_payload.get("viewer_capabilities") or {}).get("solution_share"))
        self.assertTrue(solution_payload.get("title"))
        self.assertTrue(solution_payload.get("subtitle"))
        self.assertNotIn("###", solution_payload.get("overview", ""))
        if sidecar_snapshot:
            self.assertEqual(solution_payload.get("source_mode"), "structured_sidecar")
        else:
            self.assertIn(solution_payload.get("source_mode"), {"legacy_markdown", "legacy_fallback"})
        self.assertIsInstance(solution_payload.get("quality_signals"), dict)
        self.assertIn("fallback_ratio", solution_payload.get("quality_signals", {}))
        self.assertIn("evidence_binding_ratio", solution_payload.get("quality_signals", {}))
        self.assertIn("similarity_score", solution_payload.get("quality_signals", {}))
        self.assertIsInstance(solution_payload.get("metrics"), list)
        self.assertGreaterEqual(len(solution_payload.get("metrics", [])), 3)
        self.assertIsInstance(solution_payload.get("headline_cards"), list)
        self.assertGreaterEqual(len(solution_payload.get("headline_cards", [])), 3)
        self.assertIsInstance(solution_payload.get("nav_items"), list)
        self.assertGreaterEqual(len(solution_payload.get("nav_items", [])), 4)
        self.assertTrue(solution_payload.get("decision_summary"))
        self.assertIsInstance(solution_payload.get("sections"), list)
        self.assertGreaterEqual(len(solution_payload.get("sections", [])), 4)
        self.assertEqual(
            [item.get("id") for item in solution_payload.get("nav_items", [])],
            [section.get("id") for section in solution_payload.get("sections", [])],
        )

        share_resp = self.client.post(f"/api/reports/{report_name}/solution/share")
        self.assertEqual(share_resp.status_code, 200, share_resp.get_data(as_text=True))
        share_payload = share_resp.get_json() or {}
        share_token = share_payload.get("share_token")
        self.assertTrue(share_token)
        self.assertIn("solution.html?share=", share_payload.get("share_url", ""))

        public_client = self.server.app.test_client()
        public_solution_resp = public_client.get(f"/api/public/solutions/{quote(share_token)}")
        self.assertEqual(public_solution_resp.status_code, 200, public_solution_resp.get_data(as_text=True))
        public_solution_payload = public_solution_resp.get_json() or {}
        self.assertEqual(public_solution_payload.get("share_mode"), "public")
        self.assertEqual(public_solution_payload.get("report_name"), "")
        self.assertFalse((public_solution_payload.get("viewer_capabilities") or {}).get("solution_share"))
        self.assertEqual(public_solution_payload.get("title"), solution_payload.get("title"))
        self.assertEqual(public_solution_payload.get("source_mode"), solution_payload.get("source_mode"))

        appendix_pdf_resp = self.client.get(f"/api/reports/{report_name}/appendix/pdf")
        self.assertEqual(appendix_pdf_resp.status_code, 200)
        self.assertEqual(appendix_pdf_resp.mimetype, "application/pdf")
        appendix_pdf_bytes = appendix_pdf_resp.get_data()
        self.assertTrue(appendix_pdf_bytes.startswith(b"%PDF"))
        self.assertGreater(len(appendix_pdf_bytes), 1500)

        other_client = self.server.app.test_client()
        self._register(client=other_client)
        other_professional_code = self._generate_license_batch(
            level_key="professional",
            note="报告链路他人专业版",
        )["licenses"][0]["code"]
        self._activate_license(other_professional_code, client=other_client)
        forbidden_get = other_client.get(f"/api/reports/{report_name}")
        self.assertEqual(forbidden_get.status_code, 404)
        forbidden_solution = other_client.get(f"/api/reports/{report_name}/solution")
        self.assertEqual(forbidden_solution.status_code, 404)
        forbidden_appendix_pdf = other_client.get(f"/api/reports/{report_name}/appendix/pdf")
        self.assertEqual(forbidden_appendix_pdf.status_code, 404)

        delete_resp = self.client.delete(f"/api/reports/{report_name}")
        self.assertEqual(delete_resp.status_code, 200)

        public_solution_after_delete = public_client.get(f"/api/public/solutions/{quote(share_token)}")
        self.assertEqual(public_solution_after_delete.status_code, 404)

        list_after_delete = self.client.get("/api/reports")
        self.assertEqual(list_after_delete.status_code, 200)
        names_after_delete = [item["name"] for item in list_after_delete.get_json()]
        self.assertNotIn(report_name, names_after_delete)

    def test_professional_user_can_generate_quality_variant_without_overwriting_balanced_report(self):
        self._register()
        professional_code = self._generate_license_batch(level_key="professional", note="精审版双轨专业版")["licenses"][0]["code"]
        activate_payload = self._activate_license(professional_code)
        self.assertEqual("professional", (activate_payload.get("level") or {}).get("key"))

        created = self._create_session(topic="精审版双轨测试", interview_mode="deep")
        session_id = created["session_id"]
        dimension = list(created["dimensions"].keys())[0]
        self._submit_answer(session_id, dimension, question="目标是什么？", answer="先出普通版，再出精审版")

        original_submit = self.server.report_generation_executor.submit
        fixed_now = datetime(2099, 1, 3, 10, 0, 0)

        class _ImmediateFuture:
            def result(self, timeout=None):
                return None

        def _fake_run_report_generation_job(session_id, user_id, request_id, report_profile="", action="generate", source_report_name=""):
            try:
                session_file = self.server.SESSIONS_DIR / f"{session_id}.json"
                session = self.server.safe_load_session(session_file)
                self.assertIsInstance(session, dict)
                report_profile = self.server.normalize_report_profile_choice(report_profile, fallback="balanced")
                if report_profile == "quality" and source_report_name:
                    report_name = self.server.build_report_variant_filename(source_report_name, report_profile)
                else:
                    report_name = self.server.build_session_report_filename(session, now=fixed_now)
                report_content = f"# {session['topic']}访谈报告\n\n模式：{report_profile}\n"
                report_path = self.server.save_report_content_and_sync(report_name, report_content)
                self.server.unmark_report_as_deleted(report_name)
                self.server.set_report_owner_id(report_name, int(user_id))

                session["status"] = "completed"
                session["updated_at"] = self.server.get_utc_now()
                if report_profile != "quality":
                    session["current_report_name"] = report_name
                    session["current_report_path"] = str(report_path)
                    session["current_report_updated_at"] = session["updated_at"]
                session["last_report_name"] = report_name
                session["last_report_quality_meta"] = {"path": "quality" if report_profile == "quality" else "balanced"}
                self.server.save_session_json_and_sync(session_file, session)

                snapshot = {
                    "version": self.server.SOLUTION_SNAPSHOT_VERSION,
                    "report_name": report_name,
                    "topic": session.get("topic", ""),
                    "session_id": session_id,
                    "scenario_id": session.get("scenario_id", ""),
                    "scenario_name": ((session.get("scenario_config") or {}).get("name") or ""),
                    "report_template": "default",
                    "report_type": "standard",
                    "report_profile": report_profile,
                    "source_report_name": source_report_name,
                    "report_variant_label": "精审版" if report_profile == "quality" else "普通版",
                    "snapshot_origin": "structured_sidecar",
                    "snapshot_stage": "final_report",
                    "has_structured_evidence": False,
                    "quality_meta": {},
                    "quality_snapshot": {},
                    "overall_coverage": 0.0,
                    "report_schema": {},
                    "solution_schema": {},
                    "draft": {
                        "overview": "测试概述",
                        "needs": [],
                        "analysis": {
                            "customer_needs": "",
                            "business_flow": "",
                            "tech_constraints": "",
                            "project_constraints": "",
                        },
                        "visualizations": {},
                        "solutions": [],
                        "risks": [],
                        "actions": [],
                        "open_questions": [],
                        "evidence_index": [],
                    },
                }
                self.server.write_solution_sidecar(report_name, snapshot)
                self.server.sync_report_index_for_filename(report_name)
                self.server.set_report_generation_metadata(session_id, {
                    "request_id": request_id,
                    "action": action,
                    "report_name": report_name,
                    "report_path": str(report_path),
                    "completed_at": self.server.get_utc_now(),
                    "report_profile": report_profile,
                    "source_report_name": source_report_name,
                    "report_variant_label": "精审版" if report_profile == "quality" else "普通版",
                    "ai_generated": True,
                })
                self.server.update_report_generation_status(
                    session_id,
                    "completed",
                    message="报告生成完成",
                    active=False,
                    detail_key="report_ready",
                    progress_override=100,
                )
            finally:
                self.server.release_report_generation_slot()

        try:
            self.server.report_generation_executor.submit = lambda fn, *args, **kwargs: (_fake_run_report_generation_job(*args, **kwargs), _ImmediateFuture())[1]

            balanced_resp = self.client.post(f"/api/sessions/{session_id}/generate-report", json={})
            self.assertEqual(balanced_resp.status_code, 202, balanced_resp.get_data(as_text=True))
            self.assertEqual("balanced", (balanced_resp.get_json() or {}).get("report_profile"))
            balanced_status = self._wait_report_generation(session_id)
            balanced_report = balanced_status.get("report_name")
            self.assertTrue(balanced_report)

            quality_resp = self.client.post(
                f"/api/sessions/{session_id}/generate-report",
                json={"report_profile": "quality", "source_report_name": balanced_report},
            )
            self.assertEqual(quality_resp.status_code, 202, quality_resp.get_data(as_text=True))
            self.assertEqual("quality", (quality_resp.get_json() or {}).get("report_profile"))
            quality_status = self._wait_report_generation(session_id)
            quality_report = quality_status.get("report_name")
            self.assertTrue(quality_report)
            self.assertNotEqual(balanced_report, quality_report)
            self.assertTrue(quality_report.endswith("-quality.md"))

            session_detail = self.client.get(f"/api/sessions/{session_id}")
            self.assertEqual(session_detail.status_code, 200, session_detail.get_data(as_text=True))
            session_payload = session_detail.get_json() or {}
            self.assertEqual(balanced_report, session_payload.get("current_report_name"))
            self.assertEqual(quality_report, session_payload.get("last_report_name"))

            reports_resp = self.client.get("/api/reports")
            self.assertEqual(reports_resp.status_code, 200, reports_resp.get_data(as_text=True))
            reports = {item.get("name"): item for item in (reports_resp.get_json() or [])}
            self.assertEqual("balanced", reports[balanced_report].get("report_profile"))
            self.assertEqual("普通版", reports[balanced_report].get("report_variant_label"))
            self.assertEqual("quality", reports[quality_report].get("report_profile"))
            self.assertEqual(balanced_report, reports[quality_report].get("source_report_name"))
            self.assertEqual("精审版", reports[quality_report].get("report_variant_label"))

            balanced_detail = self.client.get(f"/api/reports/{balanced_report}")
            self.assertEqual(balanced_detail.status_code, 200, balanced_detail.get_data(as_text=True))
            self.assertEqual("balanced", (balanced_detail.get_json() or {}).get("report_profile"))
            self.assertEqual("普通版", (balanced_detail.get_json() or {}).get("report_variant_label"))

            quality_detail = self.client.get(f"/api/reports/{quality_report}")
            self.assertEqual(quality_detail.status_code, 200, quality_detail.get_data(as_text=True))
            self.assertEqual("quality", (quality_detail.get_json() or {}).get("report_profile"))
            self.assertEqual(balanced_report, (quality_detail.get_json() or {}).get("source_report_name"))
            self.assertEqual("精审版", (quality_detail.get_json() or {}).get("report_variant_label"))
        finally:
            self.server.report_generation_executor.submit = original_submit

    def test_experience_user_cannot_request_quality_report(self):
        self._register()
        original_is_license_protected_route = self.server.is_license_protected_route
        try:
            self.server.is_license_protected_route = lambda path: False if str(path or "").startswith("/api/") else original_is_license_protected_route(path)
            created = self._create_session(topic="体验版质量报告限制", interview_mode="quick")
            session_id = created["session_id"]
            dimension = list(created["dimensions"].keys())[0]
            self._submit_answer(session_id, dimension, question="需求是什么？", answer="需要基础结论")

            response = self.client.post(
                f"/api/sessions/{session_id}/generate-report",
                json={"report_profile": "quality"},
            )
            self.assertEqual(response.status_code, 403, response.get_data(as_text=True))
            payload = response.get_json() or {}
            self.assertEqual("level_capability_denied", payload.get("error_code"))
            self.assertEqual("report.profile.quality", payload.get("capability_key"))
            self.assertEqual("experience", (payload.get("current_level") or {}).get("key"))
            self.assertEqual("professional", (payload.get("required_level") or {}).get("key"))
        finally:
            self.server.is_license_protected_route = original_is_license_protected_route

    def test_new_license_replaces_old_license_and_switches_level(self):
        self._register()
        standard_license = self._generate_license_batch(level_key="standard", note="标准版替换测试")["licenses"][0]
        professional_license = self._generate_license_batch(level_key="professional", note="专业版替换测试")["licenses"][0]

        first_payload = self._activate_license(standard_license["code"])
        self.assertEqual("standard", (first_payload.get("level") or {}).get("key"))

        second_payload = self._activate_license(professional_license["code"])
        self.assertEqual("professional", (second_payload.get("level") or {}).get("key"))

        current_payload = (self.client.get("/api/licenses/current").get_json() or {})
        self.assertEqual("professional", (current_payload.get("level") or {}).get("key"))
        self.assertEqual(int(professional_license["id"]), int((current_payload.get("license") or {}).get("id") or 0))

        with self.server.get_license_db_connection() as conn:
            old_row = conn.execute("SELECT status, replaced_by_license_id FROM licenses WHERE id = ?", (int(standard_license["id"]),)).fetchone()
            new_row = conn.execute("SELECT status FROM licenses WHERE id = ?", (int(professional_license["id"]),)).fetchone()

        self.assertEqual("replaced", str(old_row["status"]))
        self.assertEqual(int(professional_license["id"]), int(old_row["replaced_by_license_id"] or 0))
        self.assertEqual("active", str(new_row["status"]))

    def test_standard_user_can_generate_balanced_but_cannot_access_solution_appendix_or_presentation(self):
        user = self._register()
        standard_code = self._generate_license_batch(level_key="standard", note="标准版权限测试")["licenses"][0]["code"]
        activate_payload = self._activate_license(standard_code)
        self.assertEqual("standard", (activate_payload.get("level") or {}).get("key"))

        created = self._create_session(topic="标准版功能门禁")
        session_id = created["session_id"]
        dimension = list(created["dimensions"].keys())[0]
        self._submit_answer(session_id, dimension, question="需求是什么？", answer="需要标准版交付")

        gen_resp = self.client.post(
            f"/api/sessions/{session_id}/generate-report",
            json={"report_profile": "balanced"},
        )
        self.assertEqual(gen_resp.status_code, 202, gen_resp.get_data(as_text=True))
        self.assertEqual("balanced", (gen_resp.get_json() or {}).get("report_profile"))
        report_name = self._create_owned_report(int(user["id"]), topic="标准版手工权限报告")

        solution_resp = self.client.get(f"/api/reports/{report_name}/solution")
        self.assertEqual(solution_resp.status_code, 403, solution_resp.get_data(as_text=True))
        self.assertEqual("solution.view", (solution_resp.get_json() or {}).get("capability_key"))

        share_resp = self.client.post(f"/api/reports/{report_name}/solution/share")
        self.assertEqual(share_resp.status_code, 403, share_resp.get_data(as_text=True))
        self.assertEqual("solution.share", (share_resp.get_json() or {}).get("capability_key"))

        appendix_resp = self.client.get(f"/api/reports/{report_name}/appendix/pdf")
        self.assertEqual(appendix_resp.status_code, 403, appendix_resp.get_data(as_text=True))
        self.assertEqual("report.export.appendix", (appendix_resp.get_json() or {}).get("capability_key"))

        presentation_status_resp = self.client.get(f"/api/reports/{report_name}/presentation/status")
        self.assertEqual(presentation_status_resp.status_code, 403, presentation_status_resp.get_data(as_text=True))
        self.assertEqual("presentation.generate", (presentation_status_resp.get_json() or {}).get("capability_key"))

    def test_professional_user_can_access_solution_share_appendix_and_presentation_endpoints(self):
        user = self._register()
        professional_code = self._generate_license_batch(level_key="professional", note="专业版权限测试")["licenses"][0]["code"]
        activate_payload = self._activate_license(professional_code)
        self.assertEqual("professional", (activate_payload.get("level") or {}).get("key"))
        original_pil_available = self.server.PIL_AVAILABLE
        original_is_refly_configured = self.server.is_refly_configured
        self.server.PIL_AVAILABLE = False
        self.server.is_refly_configured = lambda: False
        self.addCleanup(setattr, self.server, "PIL_AVAILABLE", original_pil_available)
        self.addCleanup(setattr, self.server, "is_refly_configured", original_is_refly_configured)

        report_name = self._create_owned_report(int(user["id"]), topic="专业版功能门禁")

        solution_resp = self.client.get(f"/api/reports/{report_name}/solution")
        self.assertEqual(solution_resp.status_code, 200, solution_resp.get_data(as_text=True))
        self.assertTrue((solution_resp.get_json() or {}).get("viewer_capabilities", {}).get("solution_share"))

        share_resp = self.client.post(f"/api/reports/{report_name}/solution/share")
        self.assertEqual(share_resp.status_code, 200, share_resp.get_data(as_text=True))
        self.assertTrue((share_resp.get_json() or {}).get("share_url"))

        appendix_resp = self.client.get(f"/api/reports/{report_name}/appendix/pdf")
        self.assertEqual(appendix_resp.status_code, 200)
        self.assertEqual("application/pdf", appendix_resp.mimetype)

        presentation_status_resp = self.client.get(f"/api/reports/{report_name}/presentation/status")
        self.assertEqual(presentation_status_resp.status_code, 200, presentation_status_resp.get_data(as_text=True))
        self.assertFalse((presentation_status_resp.get_json() or {}).get("exists"))

        presentation_resp = self.client.post(f"/api/reports/{report_name}/refly")
        self.assertEqual(presentation_resp.status_code, 400, presentation_resp.get_data(as_text=True))
        self.assertNotEqual("level_capability_denied", (presentation_resp.get_json() or {}).get("error_code"))

    def test_export_asset_permission_follows_current_level(self):
        uploaded_objects = {}
        original_is_enabled = self.server.is_object_storage_enabled
        original_upload = self.server.upload_bytes_to_object_storage
        original_download = self.server.download_object_storage_bytes
        original_exists = self.server.object_storage_key_exists
        self.server.is_object_storage_enabled = lambda: True

        def fake_upload(content, *, object_key, content_type, metadata):
            uploaded_objects[object_key] = {
                "content": bytes(content),
                "content_type": content_type,
                "metadata": dict(metadata or {}),
            }
            return {
                "object_key": object_key,
                "storage_backend": "mock",
                "bucket": "mock-bucket",
                "content_type": content_type,
                "size": len(content),
            }

        def fake_download(object_key):
            item = uploaded_objects[object_key]
            return item["content"], {"content_type": item["content_type"]}

        self.server.upload_bytes_to_object_storage = fake_upload
        self.server.download_object_storage_bytes = fake_download
        self.server.object_storage_key_exists = lambda object_key: object_key in uploaded_objects
        self.addCleanup(setattr, self.server, "is_object_storage_enabled", original_is_enabled)
        self.addCleanup(setattr, self.server, "upload_bytes_to_object_storage", original_upload)
        self.addCleanup(setattr, self.server, "download_object_storage_bytes", original_download)
        self.addCleanup(setattr, self.server, "object_storage_key_exists", original_exists)

        standard_user = self._register()
        standard_code = self._generate_license_batch(level_key="standard", note="标准版导出测试")["licenses"][0]["code"]
        self._activate_license(standard_code)
        standard_report = self._create_owned_report(int(standard_user["id"]), topic="标准版导出")

        md_resp = self.client.post(
            f"/api/reports/{standard_report}/exports",
            data={
                "scope": "report",
                "format": "md",
                "source": "test_suite",
                "file": (io.BytesIO(b"# markdown export"), "standard-report.md"),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(md_resp.status_code, 201, md_resp.get_data(as_text=True))
        md_asset = md_resp.get_json() or {}

        docx_resp = self.client.post(
            f"/api/reports/{standard_report}/exports",
            data={
                "scope": "report",
                "format": "docx",
                "source": "test_suite",
                "file": (io.BytesIO(b"docx export"), "standard-report.docx"),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(docx_resp.status_code, 201, docx_resp.get_data(as_text=True))

        appendix_resp = self.client.post(
            f"/api/reports/{standard_report}/exports",
            data={
                "scope": "appendix",
                "format": "pdf",
                "source": "test_suite",
                "file": (io.BytesIO(b"%PDF-1.4 appendix"), "standard-appendix.pdf"),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(appendix_resp.status_code, 403, appendix_resp.get_data(as_text=True))
        self.assertEqual("report.export.appendix", (appendix_resp.get_json() or {}).get("capability_key"))

        list_resp = self.client.get(f"/api/reports/{standard_report}/exports")
        self.assertEqual(list_resp.status_code, 200, list_resp.get_data(as_text=True))
        listed_items = list_resp.get_json().get("items", [])
        self.assertEqual(2, len(listed_items))
        self.assertEqual({"md", "docx"}, {item.get("export_format") for item in listed_items})

        download_resp = self.client.get(f"/api/reports/{standard_report}/exports/{md_asset['asset_id']}")
        self.assertEqual(download_resp.status_code, 200, download_resp.get_data(as_text=True))
        self.assertEqual(b"# markdown export", download_resp.get_data())

        self.server.set_license_enforcement_override(False)
        experience_client = self.server.app.test_client()
        experience_user = self._register(client=experience_client)
        experience_report = self._create_owned_report(int(experience_user["id"]), topic="体验版导出")
        denied_resp = experience_client.post(
            f"/api/reports/{experience_report}/exports",
            data={
                "scope": "report",
                "format": "md",
                "source": "test_suite",
                "file": (io.BytesIO(b"# experience export"), "experience-report.md"),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(denied_resp.status_code, 403, denied_resp.get_data(as_text=True))
        self.assertEqual("report.export.basic", (denied_resp.get_json() or {}).get("capability_key"))

    def test_reports_list_returns_direct_binding_metadata_for_same_topic_sessions(self):
        user = self._register()
        first = self._create_session(topic="同主题元数据绑定")
        second = self._create_session(topic="同主题元数据绑定")
        first_session_id = first["session_id"]
        second_session_id = second["session_id"]
        report_name = self._build_scoped_report_name(first["topic"], session_id=first_session_id)
        report_path = self.server.REPORTS_DIR / report_name
        report_path.write_text("# 绑定测试报告\n", encoding="utf-8")
        self.server.set_report_owner_id(report_name, int(user["id"]))

        session_file = self.server.SESSIONS_DIR / f"{first_session_id}.json"
        session_data = self.server.safe_load_session(session_file)
        session_data["current_report_name"] = report_name
        session_data["current_report_path"] = str(report_path.resolve())
        self.server.save_session_json_and_sync(session_file, session_data)

        reports_resp = self.client.get("/api/reports")
        self.assertEqual(reports_resp.status_code, 200, reports_resp.get_data(as_text=True))
        report_items = reports_resp.get_json() or []
        report_meta = next(item for item in report_items if item.get("name") == report_name)
        self.assertEqual(report_meta.get("session_id"), first_session_id)
        self.assertNotEqual(report_meta.get("session_id"), second_session_id)
        self.assertEqual(report_meta.get("topic"), first["topic"])
        self.assertTrue(report_meta.get("scenario_name"))
        self.assertTrue(report_meta.get("report_template"))
        self.assertEqual(report_meta.get("report_type"), "standard")

    def test_reports_list_uses_indexed_binding_metadata_without_runtime_session_scan(self):
        user = self._register()
        created = self._create_session(topic="报告索引绑定元数据")
        session_id = created["session_id"]
        report_name = self._build_scoped_report_name(created["topic"], session_id=session_id)
        report_path = self.server.REPORTS_DIR / report_name
        report_path.write_text("# 索引绑定测试报告\n", encoding="utf-8")
        self.server.set_report_owner_id(report_name, int(user["id"]))

        session_file = self.server.SESSIONS_DIR / f"{session_id}.json"
        session_data = self.server.safe_load_session(session_file)
        session_data["current_report_name"] = report_name
        session_data["current_report_path"] = str(report_path.resolve())
        self.server.save_session_json_and_sync(session_file, session_data)

        with self.server.meta_index_state_lock:
            self.server.meta_index_state["reports_bootstrapped"] = False
        with self.server.get_meta_index_connection() as conn:
            conn.execute("DELETE FROM report_index")

        old_find_direct_bound = self.server.find_direct_bound_session_for_report
        try:
            def _should_not_scan(*_args, **_kwargs):
                raise AssertionError("报告列表不应在运行时扫描会话文件补元数据")

            self.server.find_direct_bound_session_for_report = _should_not_scan

            reports_resp = self.client.get("/api/reports")
            self.assertEqual(reports_resp.status_code, 200, reports_resp.get_data(as_text=True))
            report_items = reports_resp.get_json() or []
            report_meta = next(item for item in report_items if item.get("name") == report_name)
            self.assertEqual(report_meta.get("session_id"), session_id)
            self.assertEqual(report_meta.get("topic"), created["topic"])
            self.assertTrue(report_meta.get("scenario_name"))
            self.assertTrue(report_meta.get("report_template"))
            self.assertEqual(report_meta.get("report_type"), "standard")
        finally:
            self.server.find_direct_bound_session_for_report = old_find_direct_bound

    def test_regenerate_report_overwrites_current_session_report(self):
        self._register()
        self._activate_license(
            self._generate_license_batch(
                level_key="professional",
                note="跨天重生成专业版",
                use_absolute_window=True,
                starts_in_days=-1,
                expires_in_days=30000,
            )["licenses"][0]["code"]
        )
        created = self._create_session(topic="跨天重生成报告")
        session_id = created["session_id"]
        dimension = list(created["dimensions"].keys())[0]
        self._submit_answer(session_id, dimension, question="目标是什么？", answer="先生成首版")

        first_payload = self._generate_report_with_fixed_now(
            session_id,
            datetime(2099, 1, 1, 9, 0),
            action="generate",
            report_profile="quality",
        )
        first_report_name = first_payload.get("report_name")
        self.assertEqual(
            first_report_name,
            self._build_scoped_report_name(created["topic"], date_str="20990101", session_id=session_id),
        )

        session_detail = self.client.get(f"/api/sessions/{session_id}")
        self.assertEqual(session_detail.status_code, 200)
        session_payload = session_detail.get_json() or {}
        self.assertEqual(session_payload.get("current_report_name"), first_report_name)

        second_payload = self._generate_report_with_fixed_now(
            session_id,
            datetime(2099, 1, 2, 10, 30),
            action="regenerate",
            report_profile="quality",
        )
        second_report_name = second_payload.get("report_name")
        self.assertEqual(second_report_name, first_report_name)

        reports_resp = self.client.get("/api/reports")
        self.assertEqual(reports_resp.status_code, 200, reports_resp.get_data(as_text=True))
        report_names = [item["name"] for item in (reports_resp.get_json() or [])]
        self.assertEqual(report_names.count(first_report_name), 1)

        refreshed_session = self.client.get(f"/api/sessions/{session_id}")
        self.assertEqual(refreshed_session.status_code, 200)
        refreshed_payload = refreshed_session.get_json() or {}
        self.assertEqual(refreshed_payload.get("current_report_name"), first_report_name)

    def test_generate_report_uses_unique_filename_for_same_day_same_topic_sessions(self):
        self._register()
        self._activate_license(
            self._generate_license_batch(
                level_key="professional",
                note="同主题同日专业版",
                use_absolute_window=True,
                starts_in_days=-1,
                expires_in_days=30000,
            )["licenses"][0]["code"]
        )
        first = self._create_session(topic="同主题同日报告")
        second = self._create_session(topic="同主题同日报告")

        self._submit_answer(first["session_id"], list(first["dimensions"].keys())[0], question="目标是什么？", answer="第一份报告")
        self._submit_answer(second["session_id"], list(second["dimensions"].keys())[0], question="目标是什么？", answer="第二份报告")

        fixed_now = datetime(2099, 1, 1, 9, 30)
        first_payload = self._generate_report_with_fixed_now(first["session_id"], fixed_now, report_profile="quality")
        second_payload = self._generate_report_with_fixed_now(second["session_id"], fixed_now, report_profile="quality")

        first_report_name = first_payload.get("report_name")
        second_report_name = second_payload.get("report_name")

        self.assertNotEqual(first_report_name, second_report_name)
        self.assertEqual(
            first_report_name,
            self._build_scoped_report_name(first["topic"], date_str="20990101", session_id=first["session_id"]),
        )
        self.assertEqual(
            second_report_name,
            self._build_scoped_report_name(second["topic"], date_str="20990101", session_id=second["session_id"]),
        )

        reports_resp = self.client.get("/api/reports")
        self.assertEqual(reports_resp.status_code, 200, reports_resp.get_data(as_text=True))
        report_names = [item["name"] for item in (reports_resp.get_json() or [])]
        self.assertIn(first_report_name, report_names)
        self.assertIn(second_report_name, report_names)
        self.assertEqual(report_names.count(first_report_name), 1)
        self.assertEqual(report_names.count(second_report_name), 1)

    def test_generate_report_returns_429_when_queue_full(self):
        self._register()
        created = self._create_session(topic="队列满载测试")
        session_id = created["session_id"]

        acquired = 0
        for _ in range(self.server.REPORT_GENERATION_MAX_PENDING):
            if self.server.report_generation_slots.acquire(blocking=False):
                acquired += 1

        try:
            resp = self.client.post(f"/api/sessions/{session_id}/generate-report", json={})
            self.assertEqual(resp.status_code, 429, resp.get_data(as_text=True))
            self.assertEqual(
                resp.headers.get("Retry-After"),
                str(self.server.REPORT_GENERATION_QUEUE_RETRY_AFTER_SECONDS),
            )
            payload = resp.get_json() or {}
            self.assertIn("报告生成队列繁忙", payload.get("error", ""))
            self.assertIn("queue", payload)
        finally:
            for _ in range(acquired):
                self.server.release_report_generation_slot()

    def test_generate_report_rejects_invalid_profile(self):
        self._register()
        created = self._create_session(topic="档位参数校验")
        session_id = created["session_id"]

        resp = self.client.post(
            f"/api/sessions/{session_id}/generate-report",
            json={"report_profile": "turbo"},
        )
        self.assertEqual(resp.status_code, 400, resp.get_data(as_text=True))
        payload = resp.get_json() or {}
        self.assertIn("report_profile", payload.get("error", ""))

    def test_strip_inline_evidence_markers_for_report_text(self):
        raw_text = "核心结论[证据:Q1,Q4]。流程观察（证据：Q10，Q12）。补充说明(证据:Q19)。附加结论（Q4，Q7，Q8，Q9）。"
        cleaned = self.server.strip_inline_evidence_markers(raw_text)

        self.assertEqual(cleaned, "核心结论。流程观察。补充说明。附加结论。")
        self.assertNotIn("证据", cleaned)
        self.assertNotIn("Q1", cleaned)
        self.assertNotIn("Q7", cleaned)

    def test_validate_report_draft_removes_inline_evidence_markers(self):
        draft = {
            "overview": "这是概述[证据:Q1,Q2]（Q1, Q2）。",
            "needs": [
                {
                    "name": "需求名称（证据：Q1）",
                    "priority": "P0",
                    "description": "需求描述(证据:Q2)（Q2）",
                    "evidence_refs": ["Q1", "Q2"],
                }
            ],
            "analysis": {
                "customer_needs": "客户视角[证据:Q1]",
                "business_flow": "流程视角（证据：Q2）（Q2）",
                "tech_constraints": "技术约束",
                "project_constraints": "项目约束",
            },
            "visualizations": {},
            "solutions": [],
            "risks": [],
            "actions": [],
            "open_questions": [],
            "evidence_index": [],
        }
        evidence_pack = {
            "facts": [{"q_id": "Q1"}, {"q_id": "Q2"}],
            "contradictions": [],
            "unknowns": [],
            "blindspots": [],
        }

        normalized, _issues = self.server.validate_report_draft_v3(draft, evidence_pack)
        self.assertEqual(normalized["overview"], "这是概述。")
        self.assertEqual(normalized["needs"][0]["name"], "需求名称")
        self.assertEqual(normalized["needs"][0]["description"], "需求描述")
        self.assertEqual(normalized["analysis"]["customer_needs"], "客户视角")
        self.assertEqual(normalized["analysis"]["business_flow"], "流程视角")

    def test_batch_delete_sessions_with_linked_reports(self):
        user = self._register()
        first = self._create_session(topic="批量删除主题A")
        second = self._create_session(topic="批量删除主题B")

        sid_a = first["session_id"]
        sid_b = second["session_id"]
        report_a = self._build_scoped_report_name(first["topic"])
        report_b = self._build_scoped_report_name(second["topic"])

        (self.server.REPORTS_DIR / report_a).write_text("# Report A\n", encoding="utf-8")
        (self.server.REPORTS_DIR / report_b).write_text("# Report B\n", encoding="utf-8")
        self.server.set_report_owner_id(report_a, int(user["id"]))
        self.server.set_report_owner_id(report_b, int(user["id"]))

        batch = self.client.post(
            "/api/sessions/batch-delete",
            json={"session_ids": [sid_a, sid_b], "delete_reports": True},
        )
        self.assertEqual(batch.status_code, 200, batch.get_data(as_text=True))
        payload = batch.get_json()
        self.assertTrue(payload.get("success"))
        self.assertEqual(sorted(payload.get("deleted_sessions", [])), sorted([sid_a, sid_b]))
        self.assertEqual(sorted(payload.get("deleted_reports", [])), sorted([report_a, report_b]))

        list_reports = self.client.get("/api/reports")
        self.assertEqual(list_reports.status_code, 200)
        listed = [item["name"] for item in list_reports.get_json()]
        self.assertNotIn(report_a, listed)
        self.assertNotIn(report_b, listed)

    def test_batch_delete_sessions_does_not_delete_reports_from_other_scope(self):
        old_scope = self.server.INSTANCE_SCOPE_KEY
        try:
            self.server.INSTANCE_SCOPE_KEY = "instance-a"
            user = self._register()
            created = self._create_session(topic="跨实例同主题")
            session_id = created["session_id"]
            report_a = self._build_scoped_report_name(created["topic"])
            (self.server.REPORTS_DIR / report_a).write_text("# Scope A\n", encoding="utf-8")
            self.server.set_report_owner_id(report_a, int(user["id"]))

            self.server.INSTANCE_SCOPE_KEY = "instance-b"
            report_b = self._build_scoped_report_name(created["topic"])
            (self.server.REPORTS_DIR / report_b).write_text("# Scope B\n", encoding="utf-8")
            self.server.set_report_owner_id(report_b, int(user["id"]))

            self.server.INSTANCE_SCOPE_KEY = "instance-a"
            batch = self.client.post(
                "/api/sessions/batch-delete",
                json={"session_ids": [session_id], "delete_reports": True},
            )
            self.assertEqual(batch.status_code, 200, batch.get_data(as_text=True))
            payload = batch.get_json() or {}
            self.assertEqual(payload.get("deleted_reports"), [report_a])
            self.assertIn(report_a, self.server.get_deleted_reports())
            self.assertNotIn(report_b, self.server.get_deleted_reports())

            self.server.INSTANCE_SCOPE_KEY = "instance-b"
            reports_b = self.client.get("/api/reports")
            self.assertEqual(reports_b.status_code, 200)
            self.assertIn(report_b, [item["name"] for item in reports_b.get_json()])
        finally:
            self.server.INSTANCE_SCOPE_KEY = old_scope

    def test_submit_answer_persists_original_and_effective_selection_modes(self):
        self._register()
        created = self._create_session(topic="单选转多选提交")
        session_id = created["session_id"]
        dimension = list(created["dimensions"].keys())[0]

        response = self.client.post(
            f"/api/sessions/{session_id}/submit-answer",
            json={
                "question": "需要哪些能力支持？",
                "answer": "A；B",
                "dimension": dimension,
                "options": ["A", "B", "C"],
                "multi_select": True,
                "question_multi_select": False,
                "selection_escalated_from_single": True,
                "other_selected": True,
                "other_answer_text": "以上都要",
                "other_resolution": {
                    "mode": "reference",
                    "matched_options": ["A", "B"],
                    "custom_text": "",
                    "source_text": "以上都要",
                },
                "is_follow_up": False,
            },
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        payload = response.get_json() or {}
        log = (payload.get("interview_log") or [])[-1]
        self.assertTrue(log["multi_select"])
        self.assertFalse(log["question_multi_select"])
        self.assertTrue(log["selection_escalated_from_single"])
        self.assertTrue(log["other_selected"])
        self.assertEqual(log["other_answer_text"], "以上都要")
        self.assertEqual(
            log["other_resolution"],
            {
                "mode": "reference",
                "matched_options": ["A", "B"],
                "custom_text": "",
                "source_text": "以上都要",
            },
        )
        self.assertEqual(payload["dimensions"][dimension]["items"][-1]["name"], "A；B")

    def test_submit_answer_rejects_invalid_other_resolution(self):
        self._register()
        created = self._create_session(topic="非法其他解析")
        session_id = created["session_id"]
        dimension = list(created["dimensions"].keys())[0]

        response = self.client.post(
            f"/api/sessions/{session_id}/submit-answer",
            json={
                "question": "需要哪些能力支持？",
                "answer": "A",
                "dimension": dimension,
                "options": ["A", "B", "C"],
                "other_selected": True,
                "other_answer_text": "A",
                "other_resolution": {
                    "mode": "custom",
                    "matched_options": ["A"],
                    "custom_text": "A",
                    "source_text": "A",
                },
                "is_follow_up": False,
            },
        )

        self.assertEqual(response.status_code, 400, response.get_data(as_text=True))
        self.assertIn("other_resolution.custom", (response.get_json() or {}).get("error", ""))

    def test_render_appendix_answer_block_honors_other_resolution_modes(self):
        reference_log = {
            "answer": "A；C",
            "options": ["A", "B", "C"],
            "other_selected": True,
            "other_answer_text": "1、3",
            "other_resolution": {
                "mode": "reference",
                "matched_options": ["A", "C"],
                "custom_text": "",
                "source_text": "1、3",
            },
        }
        reference_block = self.server.render_appendix_answer_block(reference_log)
        self.assertIn("<div>☑ A</div>", reference_block)
        self.assertIn("<div>☐ B</div>", reference_block)
        self.assertIn("<div>☑ C</div>", reference_block)
        self.assertNotIn("其他（自由输入）", reference_block)

        mixed_log = {
            "answer": "A；C；另外还要支持导出",
            "options": ["A", "B", "C"],
            "other_selected": True,
            "other_answer_text": "1、3，另外还要支持导出",
            "other_resolution": {
                "mode": "mixed",
                "matched_options": ["A", "C"],
                "custom_text": "另外还要支持导出",
                "source_text": "1、3，另外还要支持导出",
            },
        }
        mixed_block = self.server.render_appendix_answer_block(mixed_log)
        self.assertIn("<div>☑ A</div>", mixed_block)
        self.assertIn("<div>☐ B</div>", mixed_block)
        self.assertIn("<div>☑ C</div>", mixed_block)
        self.assertIn("<div>☑ 其他补充说明：另外还要支持导出</div>", mixed_block)
        self.assertNotIn("其他（自由输入）", mixed_block)


if __name__ == "__main__":
    unittest.main(verbosity=2)
