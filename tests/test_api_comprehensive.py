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
        self.server.session_list_cache.clear()
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
        self._register()
        broken_scenario_id = "custom-broken"
        self.server.scenario_loader._cache[broken_scenario_id] = {
            "id": broken_scenario_id,
            "name": "异常场景",
            "description": "历史脏数据",
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

        gen_resp = self.client.post(f"/api/sessions/{session_id}/generate-report", json={})
        self.assertEqual(gen_resp.status_code, 202, gen_resp.get_data(as_text=True))

        status_payload = {}
        for _ in range(120):
            status_resp = self.client.get(f"/api/status/report-generation/{session_id}")
            self.assertEqual(status_resp.status_code, 200)
            status_payload = status_resp.get_json() or {}
            if status_payload.get("state") == "completed" and status_payload.get("report_name"):
                break
            time.sleep(0.05)
        self.assertEqual(status_payload.get("state"), "completed", status_payload)
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
        self.assertIn("问题 1：需求是什么？", content)
        self.assertIn("】问题 1：需求是什么？", content)
        self.assertNotIn("Q1:", content)
        self.assertIn("☐ 细粒度权限控制", content)
        self.assertIn("☑ 其他（自由输入）：可控的技术实现", content)
        self.assertIn("☐", content)
        self.assertIn("☑", content)
        self.assertIn("**回答**：  \n☐ 细粒度权限控制", content)
        self.assertNotIn("- ☐", content)
        self.assertNotIn("**维度**:", content)
        self.assertNotIn("记录时间", content)
        self.assertIn("本次访谈共手机了 1 个问题的回答（点击展开/收起）", content)

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
        forbidden_appendix_pdf = other_client.get(f"/api/reports/{report_name}/appendix/pdf")
        self.assertEqual(forbidden_appendix_pdf.status_code, 404)

        delete_resp = self.client.delete(f"/api/reports/{report_name}")
        self.assertEqual(delete_resp.status_code, 200)

        list_after_delete = self.client.get("/api/reports")
        self.assertEqual(list_after_delete.status_code, 200)
        names_after_delete = [item["name"] for item in list_after_delete.get_json()]
        self.assertNotIn(report_name, names_after_delete)
        self.assertGreater(user["id"], 0)

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

    def test_strip_inline_evidence_markers_for_report_text(self):
        raw_text = "核心结论[证据:Q1,Q4]。流程观察（证据：Q10，Q12）。补充说明(证据:Q19)。"
        cleaned = self.server.strip_inline_evidence_markers(raw_text)

        self.assertEqual(cleaned, "核心结论。流程观察。补充说明。")
        self.assertNotIn("证据", cleaned)
        self.assertNotIn("Q1", cleaned)

    def test_validate_report_draft_removes_inline_evidence_markers(self):
        draft = {
            "overview": "这是概述[证据:Q1,Q2]。",
            "needs": [
                {
                    "name": "需求名称（证据：Q1）",
                    "priority": "P0",
                    "description": "需求描述(证据:Q2)",
                    "evidence_refs": ["Q1", "Q2"],
                }
            ],
            "analysis": {
                "customer_needs": "客户视角[证据:Q1]",
                "business_flow": "流程视角（证据：Q2）",
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
        slug_a = self.server.normalize_topic_slug(first["topic"])
        slug_b = self.server.normalize_topic_slug(second["topic"])
        report_a = f"deep-vision-20990101-{slug_a}.md"
        report_b = f"deep-vision-20990101-{slug_b}.md"

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
