import io
import importlib.util
import json
import sys
import tempfile
import types
import unittest
import uuid
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SERVER_PATH = ROOT_DIR / "web" / "server.py"
APP_JS_PATH = ROOT_DIR / "web" / "app.js"


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

    spec = importlib.util.spec_from_file_location("dv_server_security_test", SERVER_PATH)
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


class SecurityRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = load_server_module()
        cls.temp_dir = tempfile.TemporaryDirectory(prefix="dv-security-tests-")
        cls.sandbox_root = Path(cls.temp_dir.name).resolve()
        cls._configure_sandbox_paths()

        cls.server.app.config["TESTING"] = True

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
        cls.server.init_auth_db()

        # Keep tests deterministic and avoid external model calls.
        cls.server.ENABLE_AI = False
        cls.server.question_ai_client = None
        cls.server.report_ai_client = None

    def setUp(self):
        self.client = self.server.app.test_client()

    def _register_user(self):
        account = f"1{uuid.uuid4().int % 10**10:010d}"
        response = self.client.post(
            "/api/auth/register",
            json={"account": account, "password": "Password123!"},
        )
        self.assertEqual(response.status_code, 201, response.get_data(as_text=True))
        return response.get_json()["user"]

    def _create_session(self, topic="安全回归测试"):
        response = self.client.post("/api/sessions", json={"topic": topic})
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        payload = response.get_json()
        self.assertIn("session_id", payload)
        return payload["session_id"]

    def test_anonymous_write_endpoints_are_blocked(self):
        blocked_cases = [
            ("post", "/api/scenarios/custom", {"name": "x", "dimensions": [{"name": "d"}]}),
            ("post", "/api/scenarios/generate", {"user_description": "这是一个足够长的场景描述文本用于测试鉴权"}),  # noqa: E501
            ("post", "/api/metrics/reset", {}),
            ("post", "/api/summaries/clear", {}),
        ]

        for method, path, body in blocked_cases:
            response = getattr(self.client, method)(path, json=body)
            self.assertEqual(response.status_code, 401, f"{path} should be protected")

        summaries_response = self.client.get("/api/summaries")
        self.assertEqual(summaries_response.status_code, 401)

        public_read = self.client.get("/api/scenarios")
        self.assertEqual(public_read.status_code, 200)

    def test_status_anonymous_response_is_minimal(self):
        response = self.client.get("/api/status")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()

        self.assertEqual(payload.get("status"), "running")
        self.assertFalse(payload.get("authenticated"))
        self.assertNotIn("sessions_dir", payload)
        self.assertNotIn("reports_dir", payload)
        self.assertNotIn("model", payload)
        self.assertNotIn("question_model", payload)
        self.assertNotIn("report_model", payload)

    def test_wechat_start_blocks_external_return_to(self):
        old_enabled = self.server.WECHAT_LOGIN_ENABLED
        old_app_id = self.server.WECHAT_APP_ID
        old_secret = self.server.WECHAT_APP_SECRET
        old_redirect = self.server.WECHAT_REDIRECT_URI
        try:
            self.server.WECHAT_LOGIN_ENABLED = True
            self.server.WECHAT_APP_ID = "wx-test-app"
            self.server.WECHAT_APP_SECRET = "wx-test-secret"
            self.server.WECHAT_REDIRECT_URI = "http://localhost:5001/api/auth/wechat/callback"

            response = self.client.get("/api/auth/wechat/start?return_to=https://evil.example/steal")
            self.assertEqual(response.status_code, 302)
            self.assertIn("open.weixin.qq.com/connect/qrconnect", response.headers.get("Location", ""))

            with self.client.session_transaction() as sess:
                self.assertEqual(sess.get("wechat_oauth_return_to"), "/index.html")
        finally:
            self.server.WECHAT_LOGIN_ENABLED = old_enabled
            self.server.WECHAT_APP_ID = old_app_id
            self.server.WECHAT_APP_SECRET = old_secret
            self.server.WECHAT_REDIRECT_URI = old_redirect

    def test_static_route_blocks_sensitive_files(self):
        denied_paths = ["/server.py", "/config.py", "/../server.py", "/.gitignore"]
        for path in denied_paths:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 404, f"{path} should be denied")

        allowed_paths = ["/index.html", "/app.js", "/styles.css", "/vendor/js/marked.min.js"]
        for path in allowed_paths:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, f"{path} should be served")
            response.close()

    def test_upload_filename_is_sanitized_and_cannot_escape_temp_dir(self):
        self._register_user()
        session_id = self._create_session()

        external_target = Path("/tmp") / f"dv-upload-escape-{uuid.uuid4().hex}.txt"
        if external_target.exists():
            external_target.unlink()
        malicious_name = f"../../../../tmp/{external_target.name}"

        response = self.client.post(
            f"/api/sessions/{session_id}/documents",
            data={"file": (io.BytesIO(b"security regression"), malicious_name)},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertFalse(external_target.exists(), "upload should not write outside TEMP_DIR")

        session_file = self.server.SESSIONS_DIR / f"{session_id}.json"
        self.assertTrue(session_file.exists())
        session_data = json.loads(session_file.read_text(encoding="utf-8"))
        docs = session_data.get("reference_materials", [])
        self.assertTrue(docs, "uploaded document should be recorded")
        stored_name = docs[-1].get("name", "")
        self.assertEqual(stored_name, external_target.name)
        self.assertNotIn("..", stored_name)
        self.assertNotIn("/", stored_name)

    def test_frontend_markdown_render_has_sanitizer_guard(self):
        content = APP_JS_PATH.read_text(encoding="utf-8")
        self.assertIn("sanitizeMarkdownHtml(rawHtml)", content)
        self.assertIn("return this.sanitizeMarkdownHtml(html);", content)
        self.assertIn("return this.sanitizeMarkdownHtml(fallbackHtml);", content)
        self.assertIn("attrName.startsWith('on')", content)
        self.assertIn("isSafeUrl(url)", content)


if __name__ == "__main__":
    unittest.main(verbosity=2)
