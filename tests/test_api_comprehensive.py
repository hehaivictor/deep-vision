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
from datetime import datetime
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
        cls.server.PRESENTATION_MAP_FILE = cls.server.PRESENTATIONS_DIR / ".presentation_map.json"
        cls.server.DELETED_REPORTS_FILE = cls.server.REPORTS_DIR / ".deleted_reports.json"
        cls.server.DELETED_DOCS_FILE = cls.server.DATA_DIR / ".deleted_docs.json"
        cls.server.REPORT_OWNERS_FILE = cls.server.REPORTS_DIR / ".owners.json"
        cls.server.REPORT_SCOPES_FILE = cls.server.REPORTS_DIR / ".scopes.json"

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

        # 避免测试中启动后台预生成线程和外部依赖。
        cls.server.ENABLE_AI = False
        cls.server.ENABLE_DEBUG_LOG = False
        cls.server.question_ai_client = None
        cls.server.report_ai_client = None
        cls.server.prefetch_first_question = lambda _session_id: None
        cls.server.trigger_prefetch_if_needed = lambda *_args, **_kwargs: None

        # 使用测试沙箱内的场景存储，避免污染仓库数据。
        from scripts import scenario_loader as scenario_loader_module

        scenarios_dir = cls.server.DATA_DIR / "scenarios"
        scenario_loader_module._scenario_loader = scenario_loader_module.ScenarioLoader(scenarios_dir)
        cls.server.scenario_loader = scenario_loader_module._scenario_loader

    def setUp(self):
        self.client = self.server.app.test_client()
        self.server.reset_list_metrics()
        self.server.report_owners_cache["signature"] = None
        self.server.report_owners_cache["data"] = {}
        self.server.report_scopes_cache["signature"] = None
        self.server.report_scopes_cache["data"] = {}
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
        self.server.SESSIONS_LIST_SEMAPHORE = threading.BoundedSemaphore(self.server.SESSIONS_LIST_MAX_INFLIGHT)
        self.server.REPORTS_LIST_SEMAPHORE = threading.BoundedSemaphore(self.server.REPORTS_LIST_MAX_INFLIGHT)

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

    def _create_session(self, topic="综合测试会话", description="测试描述"):
        response = self.client.post(
            "/api/sessions",
            json={"topic": topic, "description": description},
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        payload = response.get_json()
        self.assertIn("session_id", payload)
        return payload

    def _submit_answer(self, session_id, dimension, question="测试问题", answer="测试回答"):
        response = self.client.post(
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

    def _build_scoped_report_name(self, topic, date_str="20990101"):
        slug = self.server.normalize_topic_slug(topic)
        tag = self.server.get_instance_scope_short_tag()
        if tag:
            return f"deep-vision-{date_str}-{tag}-{slug}.md"
        return f"deep-vision-{date_str}-{slug}.md"

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

    def _generate_report_with_fixed_now(self, session_id, fixed_now: datetime, action="generate", report_profile="quality"):
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

        get_session_resp = self.client.get(f"/api/sessions/{session_id}")
        self.assertEqual(get_session_resp.status_code, 200)
        materials = get_session_resp.get_json().get("reference_materials", [])
        self.assertEqual(len(materials), 1)
        self.assertEqual(materials[0]["name"], "note.md")

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
        self._register()

        # 触发列表接口指标
        self.client.get("/api/sessions")
        self.client.get("/api/reports")

        metrics = self.client.get("/api/metrics")
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

        reset = self.client.post("/api/metrics/reset", json={})
        self.assertEqual(reset.status_code, 200)
        self.assertTrue(reset.get_json().get("success"))

        summaries = self.client.get("/api/summaries")
        self.assertEqual(summaries.status_code, 200)
        self.assertIn("cached_count", summaries.get_json())
        self.assertNotIn("cache_directory", summaries.get_json())

        clear_resp = self.client.post("/api/summaries/clear", json={})
        self.assertEqual(clear_resp.status_code, 200)
        self.assertTrue(clear_resp.get_json().get("success"))

    def test_report_generation_and_report_endpoints(self):
        user = self._register()
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

        reports_resp = self.client.get("/api/reports")
        self.assertEqual(reports_resp.status_code, 200)
        report_names = [item["name"] for item in reports_resp.get_json()]
        self.assertIn(report_name, report_names)

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
        self.assertTrue(solution_payload.get("title"))
        self.assertTrue(solution_payload.get("subtitle"))
        self.assertNotIn("###", solution_payload.get("overview", ""))
        self.assertEqual(solution_payload.get("source_mode"), "legacy_markdown")
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

        appendix_pdf_resp = self.client.get(f"/api/reports/{report_name}/appendix/pdf")
        self.assertEqual(appendix_pdf_resp.status_code, 200)
        self.assertEqual(appendix_pdf_resp.mimetype, "application/pdf")
        appendix_pdf_bytes = appendix_pdf_resp.get_data()
        self.assertTrue(appendix_pdf_bytes.startswith(b"%PDF"))
        self.assertGreater(len(appendix_pdf_bytes), 1500)

        other_client = self.server.app.test_client()
        self._register(client=other_client)
        forbidden_get = other_client.get(f"/api/reports/{report_name}")
        self.assertEqual(forbidden_get.status_code, 404)
        forbidden_solution = other_client.get(f"/api/reports/{report_name}/solution")
        self.assertEqual(forbidden_solution.status_code, 404)
        forbidden_appendix_pdf = other_client.get(f"/api/reports/{report_name}/appendix/pdf")
        self.assertEqual(forbidden_appendix_pdf.status_code, 404)

        delete_resp = self.client.delete(f"/api/reports/{report_name}")
        self.assertEqual(delete_resp.status_code, 200)

        list_after_delete = self.client.get("/api/reports")
        self.assertEqual(list_after_delete.status_code, 200)
        names_after_delete = [item["name"] for item in list_after_delete.get_json()]
        self.assertNotIn(report_name, names_after_delete)

    def test_regenerate_report_overwrites_current_session_report(self):
        self._register()
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
        self.assertEqual(first_report_name, self._build_scoped_report_name(created["topic"], date_str="20990101"))

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
        self.assertEqual(len(report_names), 1)

        refreshed_session = self.client.get(f"/api/sessions/{session_id}")
        self.assertEqual(refreshed_session.status_code, 200)
        refreshed_payload = refreshed_session.get_json() or {}
        self.assertEqual(refreshed_payload.get("current_report_name"), first_report_name)

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
