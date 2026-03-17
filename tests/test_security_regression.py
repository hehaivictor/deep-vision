import io
import importlib.util
import json
import os
import sys
import tempfile
import threading
import types
import unittest
import uuid
from datetime import datetime
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
        cls.server.init_auth_db()

        # Keep tests deterministic and avoid external model calls.
        cls.server.ENABLE_AI = False
        cls.server.question_ai_client = None
        cls.server.report_ai_client = None

    def setUp(self):
        self.client = self.server.app.test_client()
        self.server.SMS_SEND_COOLDOWN_SECONDS = 0
        self.server.SMS_TEST_CODE = ""
        self.server.report_owners_cache["signature"] = None
        self.server.report_owners_cache["data"] = {}
        self.server.report_scopes_cache["signature"] = None
        self.server.report_scopes_cache["data"] = {}
        self.server.report_solution_shares_cache["signature"] = None
        self.server.report_solution_shares_cache["data"] = {}

    def _register_user(self, client=None):
        target_client = client or self.client
        account = f"1{uuid.uuid4().int % 10**10:010d}"
        send_resp = target_client.post(
            "/api/auth/sms/send-code",
            json={"account": account, "scene": "login"},
        )
        self.assertEqual(send_resp.status_code, 200, send_resp.get_data(as_text=True))
        code = (send_resp.get_json() or {}).get("test_code")
        self.assertTrue(code, "TESTING 模式应返回 test_code")

        login_resp = target_client.post(
            "/api/auth/login/code",
            json={"account": account, "code": code, "scene": "login"},
        )
        self.assertEqual(login_resp.status_code, 200, login_resp.get_data(as_text=True))
        return login_resp.get_json()["user"]

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

    def test_sms_send_code_cooldown_is_not_bypassed_by_parallel_requests(self):
        phone = f"1{uuid.uuid4().int % 10**10:010d}"
        self.server.SMS_SEND_COOLDOWN_SECONDS = 120
        results = []
        errors = []
        barrier = threading.Barrier(8)
        result_lock = threading.Lock()

        def worker(index):
            try:
                barrier.wait(timeout=1.0)
                result = self.server.issue_sms_code(phone, "login", request_ip=f"ip-{index}")
                with result_lock:
                    results.append(result)
            except Exception as exc:
                with result_lock:
                    errors.append(str(exc))

        threads = [threading.Thread(target=worker, args=(idx,)) for idx in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertFalse(errors, errors)
        success_count = sum(1 for ok, _msg, _payload in results if ok)
        self.assertEqual(1, success_count, results)

    def test_sms_code_can_only_be_consumed_once_under_parallel_verify(self):
        phone = f"1{uuid.uuid4().int % 10**10:010d}"
        self.server.SMS_TEST_CODE = "246810"
        ok, error_message, _payload = self.server.issue_sms_code(phone, "login", request_ip="seed-ip")
        self.assertTrue(ok, error_message)

        results = []
        errors = []
        barrier = threading.Barrier(12)
        result_lock = threading.Lock()

        def worker():
            try:
                barrier.wait(timeout=1.0)
                result = self.server.verify_sms_code(phone, "login", "246810", consume=True)
                with result_lock:
                    results.append(result)
            except Exception as exc:
                with result_lock:
                    errors.append(str(exc))

        threads = [threading.Thread(target=worker) for _ in range(12)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertFalse(errors, errors)
        success_count = sum(1 for ok, _message in results if ok)
        self.assertEqual(1, success_count, results)

    def test_report_solution_endpoint_requires_auth(self):
        response = self.client.get('/api/reports/security-solution.md/solution')
        self.assertEqual(response.status_code, 401)

    def test_report_solution_endpoint_enforces_owner(self):
        owner_user = self._register_user()
        report_name = 'security-solution-report.md'
        report_content = (
            '# DeepVision 访谈报告\n\n'
            '## 1. 访谈概述\n'
            '- **访谈场景** - 产品需求调研\n'
            '- **核心问题** - 报告生成后缺少直接查看方案的入口\n'
            '- **关键触点** - 访谈报告详情页\n\n'
            '## 2. 需求摘要\n'
            '### 客户需求\n'
            '- **希望立即查看落地方案** - 用户希望报告生成后直接进入方案单页。\n'
            '### 业务流程\n'
            '- **从报告详情直接跳转** - 方案页需要在新页面打开并保留导航结构。\n'
            '### 技术约束\n'
            '- **保持账号隔离** - 方案接口必须沿用报告权限校验与文件归属校验。\n'
            '### 项目约束\n'
            '- **先完成最小闭环** - 优先交付同步提炼方案内容与单页展示能力。\n'
        )
        report_file = self.server.REPORTS_DIR / report_name
        report_file.write_text(report_content, encoding='utf-8')
        self.server.set_report_owner_id(report_name, owner_user['id'])

        owner_resp = self.client.get(f'/api/reports/{report_name}/solution')
        self.assertEqual(owner_resp.status_code, 200, owner_resp.get_data(as_text=True))
        owner_payload = owner_resp.get_json() or {}
        self.assertEqual(owner_payload.get('report_name'), report_name)
        self.assertEqual(owner_payload.get('source_mode'), 'legacy_markdown')
        self.assertTrue(owner_payload.get('metrics'))
        self.assertTrue(owner_payload.get('decision_summary'))
        self.assertIsInstance(owner_payload.get('quality_signals'), dict)
        self.assertTrue(owner_payload.get('sections'))
        self.assertEqual(
            [item.get('id') for item in owner_payload.get('nav_items', [])],
            [section.get('id') for section in owner_payload.get('sections', [])],
        )

        other_client = self.server.app.test_client()
        self._register_user(client=other_client)
        forbidden_resp = other_client.get(f'/api/reports/{report_name}/solution')
        self.assertEqual(forbidden_resp.status_code, 404)

    def test_report_solution_share_link_requires_owner_and_allows_public_readonly_access(self):
        owner_user = self._register_user()
        report_name = 'security-share-report.md'
        report_content = (
            '# DeepVision 访谈报告\n\n'
            '## 1. 访谈概述\n'
            '- **访谈场景** - 技术方案研讨\n'
            '- **核心问题** - 需要向外部伙伴共享最终方案页\n'
            '- **关键触点** - 方案页外链\n\n'
            '## 2. 需求摘要\n'
            '### 客户需求\n'
            '- **外部只读查看** - 链接打开后只能查看方案页内容。\n'
            '### 业务流程\n'
            '- **分享给合作方** - 无需登录也能打开。\n'
            '### 技术约束\n'
            '- **不能泄露账号态** - 外链不能回到主站登录后的内容。\n'
            '### 项目约束\n'
            '- **最小闭环** - 先支持匿名只读分享方案。\n'
        )
        report_file = self.server.REPORTS_DIR / report_name
        report_file.write_text(report_content, encoding='utf-8')
        self.server.set_report_owner_id(report_name, owner_user['id'])

        other_client = self.server.app.test_client()
        self._register_user(client=other_client)
        forbidden_share_resp = other_client.post(f'/api/reports/{report_name}/solution/share')
        self.assertEqual(forbidden_share_resp.status_code, 404)

        share_resp = self.client.post(f'/api/reports/{report_name}/solution/share')
        self.assertEqual(share_resp.status_code, 200, share_resp.get_data(as_text=True))
        share_payload = share_resp.get_json() or {}
        share_token = share_payload.get('share_token')
        self.assertTrue(share_token)
        self.assertIn('solution.html?share=', share_payload.get('share_url', ''))

        public_client = self.server.app.test_client()
        public_resp = public_client.get(f'/api/public/solutions/{share_token}')
        self.assertEqual(public_resp.status_code, 200, public_resp.get_data(as_text=True))
        public_payload = public_resp.get_json() or {}
        self.assertEqual(public_payload.get('share_mode'), 'public')
        self.assertEqual(public_payload.get('report_name'), '')
        self.assertTrue(public_payload.get('title'))
        self.assertTrue(public_payload.get('sections'))

        invalid_resp = public_client.get('/api/public/solutions/invalid-token')
        self.assertEqual(invalid_resp.status_code, 404)

        raw_report_resp = public_client.get(f'/api/reports/{report_name}')
        self.assertEqual(raw_report_resp.status_code, 401)

    def test_build_solution_payload_strips_html_from_new_fields(self):
        report_content = (
            '# DeepVision 访谈报告\n\n'
            '## 1. 访谈概述\n'
            '- **访谈场景** - 微信客服 <script>alert(1)</script> 接待\n'
            '- **核心问题** - <div>高意向客户识别慢</div>\n'
            '- **关键触点** - 首轮咨询分流\n\n'
            '## 2. 需求摘要\n'
            '### 客户需求\n'
            '- **尽快识别高意向线索<script>alert(2)</script>** - <b>减少人工二次筛选</b>\n'
            '### 业务流程\n'
            '- **首轮咨询分流** - 在转人工前完成标签归类与优先级判断。\n'
            '### 技术约束\n'
            '- **对话内容需要脱敏** - <span>禁止原文外流</span>\n'
            '### 项目约束\n'
            '- **四周内完成试点** - 先覆盖一个业务线。\n'
        )
        payload = self.server.build_solution_payload_from_report('solution-sanitize.md', report_content)

        def iter_strings(value):
            if isinstance(value, str):
                yield value
            elif isinstance(value, dict):
                for item in value.values():
                    yield from iter_strings(item)
            elif isinstance(value, list):
                for item in value:
                    yield from iter_strings(item)

        text_values = list(iter_strings(payload))
        self.assertTrue(text_values)
        for value in text_values:
            lowered = value.lower()
            self.assertNotIn('<script', lowered)
            self.assertNotIn('</script', lowered)
            self.assertNotIn('<div', lowered)
            self.assertNotIn('javascript:', lowered)

    def test_model_routing_aligns_with_reused_report_gateway(self):
        keys = [
            "QUESTION_MODEL_NAME",
            "REPORT_MODEL_NAME",
            "SUMMARY_MODEL_NAME",
            "SEARCH_DECISION_MODEL_NAME",
            "QUESTION_API_KEY",
            "QUESTION_BASE_URL",
            "QUESTION_USE_BEARER_AUTH",
            "REPORT_API_KEY",
            "REPORT_BASE_URL",
            "REPORT_USE_BEARER_AUTH",
            "SUMMARY_API_KEY",
            "SUMMARY_BASE_URL",
            "SUMMARY_USE_BEARER_AUTH",
            "SEARCH_DECISION_API_KEY",
            "SEARCH_DECISION_BASE_URL",
            "SEARCH_DECISION_USE_BEARER_AUTH",
        ]
        backup = {key: getattr(self.server, key) for key in keys}

        try:
            self.server.QUESTION_MODEL_NAME = "glm-4.7"
            self.server.REPORT_MODEL_NAME = "gpt-5.3-codex"
            self.server.SUMMARY_MODEL_NAME = "glm-4.7"
            self.server.SEARCH_DECISION_MODEL_NAME = "glm-4.7"

            self.server.QUESTION_API_KEY = "question-key"
            self.server.QUESTION_BASE_URL = "https://open.bigmodel.cn/api/anthropic"
            self.server.QUESTION_USE_BEARER_AUTH = False

            self.server.REPORT_API_KEY = "report-key"
            self.server.REPORT_BASE_URL = "https://api.aicodemirror.com/api/codex/backend-api/codex"
            self.server.REPORT_USE_BEARER_AUTH = True

            # 摘要与搜索决策复用报告网关，但未单独配置模型（沿用问题模型）
            self.server.SUMMARY_API_KEY = self.server.REPORT_API_KEY
            self.server.SUMMARY_BASE_URL = self.server.REPORT_BASE_URL
            self.server.SUMMARY_USE_BEARER_AUTH = self.server.REPORT_USE_BEARER_AUTH
            self.server.SEARCH_DECISION_API_KEY = self.server.REPORT_API_KEY
            self.server.SEARCH_DECISION_BASE_URL = self.server.REPORT_BASE_URL
            self.server.SEARCH_DECISION_USE_BEARER_AUTH = self.server.REPORT_USE_BEARER_AUTH

            self.assertEqual(self.server.resolve_model_name(call_type="summary"), "gpt-5.3-codex")
            self.assertEqual(self.server.resolve_model_name(call_type="search_decision"), "gpt-5.3-codex")
        finally:
            for key, value in backup.items():
                setattr(self.server, key, value)

    def test_should_retry_v3_failover_when_draft_parse_failed(self):
        payload = {
            "status": "failed",
            "reason": "draft_parse_failed",
            "error": "draft_attempts_exhausted(2),raw_length=10453",
        }
        self.assertTrue(self.server.should_retry_v3_with_failover(payload))

    def test_should_retry_v3_failover_when_review_parse_failed(self):
        payload = {
            "status": "failed",
            "reason": "review_parse_failed",
            "error": "review_round=1,raw_length=4096",
        }
        self.assertTrue(self.server.should_retry_v3_with_failover(payload))

    def test_should_retry_v3_failover_when_single_fixable_issue(self):
        payload = {
            "status": "failed",
            "reason": "quality_gate_failed",
            "final_issue_count": 1,
            "review_issues": [
                {"type": "blindspot", "severity": "high", "target": "actions", "message": "盲区已进入open_questions但未纳入actions"}
            ],
        }
        self.assertTrue(self.server.should_retry_v3_with_failover(payload))

    def test_should_retry_v3_failover_when_deterministic_issue_bucket(self):
        payload = {
            "status": "failed",
            "reason": "quality_gate_failed",
            "final_issue_count": 2,
            "review_issues": [
                {"type": "blindspot", "severity": "high", "target": "actions", "message": "盲区未处理"},
                {"type": "quality_gate_table", "severity": "high", "target": "actions", "message": "表格化不足"},
            ],
        }
        self.assertTrue(self.server.should_retry_v3_with_failover(payload))

    def test_should_not_retry_v3_failover_when_issue_bucket_contains_non_deterministic_problem(self):
        payload = {
            "status": "failed",
            "reason": "quality_gate_failed",
            "final_issue_count": 2,
            "review_issues": [
                {"type": "blindspot", "severity": "high", "target": "actions", "message": "盲区未处理"},
                {"type": "unresolved_contradiction", "severity": "high", "target": "risks", "message": "冲突未解释"},
            ],
        }
        self.assertFalse(self.server.should_retry_v3_with_failover(payload))

    def test_should_retry_v3_failover_for_legacy_reason_when_single_fixable_issue(self):
        payload = {
            "status": "failed",
            "reason": "review_not_passed_or_quality_gate_failed",
            "final_issue_count": 1,
            "review_issues": [{"type": "quality_gate_table", "severity": "high", "target": "actions"}],
        }
        self.assertTrue(self.server.should_retry_v3_with_failover(payload))

    def test_build_v3_failure_log_context_contains_diagnostics(self):
        failure_payload = {
            "reason": "review_parse_failed",
            "profile": "balanced",
            "parse_stage": "review_round_1",
            "lane": "report",
            "phase_lanes": {"draft": "question", "review": "report"},
            "error": "profile=balanced,review_round=1,timeout=210.0,raw_length=4096",
            "salvage_attempted": True,
            "salvage_success": False,
            "salvage_note": "quality_gate_blocked",
            "salvage_quality_issue_count": 3,
            "review_issues": [{"type": "blindspot", "target": "actions"}],
            "salvage_issue_types": ["quality_gate_table"],
        }

        context_text = self.server.build_v3_failure_log_context(failure_payload)
        self.assertIn("reason=review_parse_failed", context_text)
        self.assertIn("profile=balanced", context_text)
        self.assertIn("parse_stage=review_round_1", context_text)
        self.assertIn("phase_lanes=draft=question,review=report", context_text)
        self.assertIn("salvage_attempted=True", context_text)
        self.assertIn("salvage_quality_issue_count=3", context_text)
        self.assertIn("final_issue_types=blindspot", context_text)
        self.assertIn("salvage_issue_types=quality_gate_table", context_text)

    def test_attempt_salvage_v3_review_failure_success(self):
        backups = {
            "validate_report_draft_v3": self.server.validate_report_draft_v3,
            "compute_report_quality_meta_v3": self.server.compute_report_quality_meta_v3,
            "build_quality_gate_issues_v3": self.server.build_quality_gate_issues_v3,
            "render_report_from_draft_v3": self.server.render_report_from_draft_v3,
        }
        try:
            self.server.validate_report_draft_v3 = lambda draft, _evidence: (draft, [])
            self.server.compute_report_quality_meta_v3 = lambda _draft, _evidence, _issues: {
                "overall_score": 86,
                "structure_score": 85,
                "coverage_score": 87,
                "consistency_score": 88,
                "citation_density": 0.32,
                "metrics": {},
                "quality_gate": {},
            }
            self.server.build_quality_gate_issues_v3 = lambda _meta: []
            self.server.render_report_from_draft_v3 = lambda _session, _draft, _meta: "# 挽救报告"

            failed_payload = {
                "reason": "review_parse_failed",
                "profile": "balanced",
                "phase_lanes": {"draft": "question", "review": "report"},
                "draft_snapshot": {"overview": "ok", "needs": [], "analysis": {}},
                "evidence_pack": {"facts": [{"q_id": "Q1", "dimension": "customer_needs"}]},
                "review_issues": [],
            }
            outcome = self.server.attempt_salvage_v3_review_failure({"topic": "测试"}, failed_payload)
            self.assertTrue(outcome.get("attempted"))
            self.assertTrue(outcome.get("success"))
            self.assertEqual(outcome.get("note"), "quality_gate_passed")
            self.assertEqual(outcome.get("report_content"), "# 挽救报告")
            self.assertEqual(outcome.get("quality_gate_issue_count"), 0)
        finally:
            for name, fn in backups.items():
                setattr(self.server, name, fn)

    def test_attempt_salvage_v3_review_failure_blocked_by_quality_gate(self):
        backups = {
            "validate_report_draft_v3": self.server.validate_report_draft_v3,
            "compute_report_quality_meta_v3": self.server.compute_report_quality_meta_v3,
            "build_quality_gate_issues_v3": self.server.build_quality_gate_issues_v3,
        }
        try:
            self.server.validate_report_draft_v3 = lambda draft, _evidence: (draft, [])
            self.server.compute_report_quality_meta_v3 = lambda _draft, _evidence, _issues: {"overall_score": 60}
            self.server.build_quality_gate_issues_v3 = lambda _meta: [
                {"type": "quality_gate", "target": "summary", "message": "质量门禁未通过"}
            ]

            failed_payload = {
                "reason": "review_generation_failed",
                "profile": "quality",
                "phase_lanes": {"draft": "question", "review": "report"},
                "draft_snapshot": {"overview": "ok", "needs": [], "analysis": {}},
                "evidence_pack": {"facts": [{"q_id": "Q1", "dimension": "customer_needs"}]},
                "review_issues": [],
            }
            outcome = self.server.attempt_salvage_v3_review_failure({"topic": "测试"}, failed_payload)
            self.assertTrue(outcome.get("attempted"))
            self.assertFalse(outcome.get("success"))
            self.assertEqual(outcome.get("note"), "quality_gate_blocked")
            self.assertEqual(outcome.get("quality_gate_issue_count"), 1)
            self.assertEqual(len(outcome.get("review_issues") or []), 1)
            self.assertEqual(outcome.get("quality_gate_issue_types"), ["quality_gate"])
            self.assertEqual(len(outcome.get("quality_gate_issues") or []), 1)
        finally:
            for name, fn in backups.items():
                setattr(self.server, name, fn)

    def test_detect_unusable_legacy_report_content(self):
        unusable_text = (
            "我会为您生成一份专业的访谈报告。在创建文档之前，我需要先征得您的同意。"
            "请确认是否继续？如果同意，我会：创建文件名为 `xxx.md`。"
        )
        self.assertTrue(self.server.is_unusable_legacy_report_content(unusable_text))

        usable_text = (
            "# 需求访谈报告\\n\\n"
            "## 1. 访谈概述\\n"
            "本次访谈围绕企业知识库建设展开。\\n\\n"
            "## 2. 需求摘要\\n"
            "- 统一检索标准\\n\\n"
            "## 3. 详细需求分析\\n"
            "从用户侧和技术侧展开分析。\\n\\n"
            "## 4. 风险与行动\\n"
            "列出风险、建议与下一步行动。"
        )
        self.assertFalse(self.server.is_unusable_legacy_report_content(usable_text))

    def test_parse_structured_json_response_supports_repair(self):
        raw_text = """```json
{
  "overview": "ok",
  "needs": [],
  "analysis": {},
}
```"""
        parse_meta = {}
        parsed = self.server.parse_structured_json_response(
            raw_text,
            required_keys=["overview", "needs", "analysis"],
            require_all_keys=True,
            parse_meta=parse_meta,
        )
        self.assertIsInstance(parsed, dict)
        self.assertTrue(parse_meta.get("repair_applied"))

    def test_parse_structured_json_response_repairs_unescaped_newline(self):
        raw_text = "{\n\"overview\":\"第一行\n第二行\",\"needs\":[],\"analysis\":{}}\n"
        parse_meta = {}
        parsed = self.server.parse_structured_json_response(
            raw_text,
            required_keys=["overview", "needs", "analysis"],
            require_all_keys=True,
            parse_meta=parse_meta,
        )
        self.assertIsInstance(parsed, dict)
        self.assertIn("第一行", parsed.get("overview", ""))
        self.assertTrue(parse_meta.get("repair_applied"))

    def test_parse_structured_json_response_repairs_truncated_nested_json(self):
        raw_text = '{"passed": true, "issues": [], "revised_draft": {"overview": "ok"'
        parse_meta = {}
        parsed = self.server.parse_structured_json_response(
            raw_text,
            required_keys=["passed", "issues", "revised_draft"],
            require_all_keys=True,
            parse_meta=parse_meta,
        )
        self.assertIsInstance(parsed, dict)
        self.assertTrue(parse_meta.get("repair_applied"))
        self.assertEqual(parsed.get("revised_draft", {}).get("overview"), "ok")

    def test_merge_report_draft_patch_v3_preserves_unmodified_sections(self):
        base_draft = {
            "overview": "旧概述",
            "needs": [{"name": "需求A", "priority": "P1", "description": "旧", "evidence_refs": ["Q1"]}],
            "analysis": {
                "customer_needs": "旧客户需求",
                "business_flow": "旧流程",
                "tech_constraints": "旧技术",
                "project_constraints": "旧项目",
            },
            "visualizations": {"business_flow_mermaid": "flowchart TD\nA-->B"},
            "solutions": [{"title": "方案A", "owner": "产品", "timeline": "2周", "metric": "上线", "evidence_refs": ["Q1"]}],
            "risks": [],
            "actions": [{"action": "旧行动", "owner": "产品", "timeline": "2周", "metric": "完成", "evidence_refs": ["Q1"]}],
            "open_questions": [],
            "evidence_index": [],
        }
        revised_patch = {
            "overview": "新概述",
            "analysis": {"business_flow": "新流程"},
            "actions": [{"action": "新行动", "owner": "运营", "timeline": "1周", "metric": "复盘完成", "evidence_refs": ["Q1"]}],
        }

        merged = self.server.merge_report_draft_patch_v3(base_draft, revised_patch)

        self.assertEqual(merged.get("overview"), "新概述")
        self.assertEqual(merged.get("analysis", {}).get("business_flow"), "新流程")
        self.assertEqual(merged.get("analysis", {}).get("customer_needs"), "旧客户需求")
        self.assertEqual(merged.get("needs", [])[0].get("name"), "需求A")
        self.assertEqual(merged.get("actions", [])[0].get("action"), "新行动")

    def test_adaptive_report_timeout_and_tokens(self):
        short_timeout = self.server.compute_adaptive_report_timeout(120.0, 3000, timeout_cap=180.0)
        long_timeout = self.server.compute_adaptive_report_timeout(120.0, 13000, timeout_cap=180.0)
        self.assertGreater(long_timeout, short_timeout)

        short_tokens = self.server.compute_adaptive_report_tokens(4800, 3000)
        long_tokens = self.server.compute_adaptive_report_tokens(4800, 13000)
        self.assertLess(long_tokens, short_tokens)
        self.assertGreaterEqual(long_tokens, 2200)

    def test_v3_balanced_profile_defaults(self):
        self.assertEqual(self.server.REPORT_V3_PROFILE, "balanced")
        self.assertEqual(self.server.REPORT_V3_DRAFT_RETRY_COUNT, 1)
        self.assertTrue(self.server.REPORT_V3_FAST_FAIL_ON_DRAFT_EMPTY)
        self.assertGreaterEqual(self.server.REPORT_V3_REVIEW_MAX_TOKENS, 2600)
        self.assertTrue(self.server.REPORT_V3_DUAL_STAGE_ENABLED)

    def test_report_v3_runtime_min_review_rounds_by_profile(self):
        env_key = "REPORT_V3_MIN_REVIEW_ROUNDS"
        old_value = os.environ.get(env_key)
        try:
            if env_key in os.environ:
                del os.environ[env_key]

            balanced_cfg = self.server.get_report_v3_runtime_config("balanced")
            quality_cfg = self.server.get_report_v3_runtime_config("quality")

            self.assertEqual(balanced_cfg.get("min_required_review_rounds"), 1)
            self.assertGreaterEqual(quality_cfg.get("min_required_review_rounds", 0), 2)

            os.environ[env_key] = "0"
            balanced_auto_cfg = self.server.get_report_v3_runtime_config("balanced")
            quality_auto_cfg = self.server.get_report_v3_runtime_config("quality")
            self.assertEqual(balanced_auto_cfg.get("min_required_review_rounds"), 1)
            self.assertGreaterEqual(quality_auto_cfg.get("min_required_review_rounds", 0), 2)

            os.environ[env_key] = "3"
            balanced_forced_cfg = self.server.get_report_v3_runtime_config("balanced")
            quality_forced_cfg = self.server.get_report_v3_runtime_config("quality")
            self.assertEqual(balanced_forced_cfg.get("min_required_review_rounds"), 3)
            self.assertEqual(quality_forced_cfg.get("min_required_review_rounds"), 3)
        finally:
            if old_value is None:
                os.environ.pop(env_key, None)
            else:
                os.environ[env_key] = old_value

    def test_build_quality_gate_issues_v3_detects_style_template_violation(self):
        quality_meta = {
            "runtime_profile": "quality",
            "evidence_coverage": 0.95,
            "consistency": 0.9,
            "actionability": 0.82,
            "expression_structure": 0.65,
            "table_readiness": 0.58,
            "action_acceptance": 0.5,
            "milestone_coverage": 0.42,
            "template_minimums": {
                "needs": 2,
                "solutions": 2,
                "risks": 1,
                "actions": 3,
                "open_questions": 1,
            },
            "list_counts": {
                "needs": 1,
                "solutions": 1,
                "risks": 1,
                "actions": 1,
                "open_questions": 0,
            },
        }

        issues = self.server.build_quality_gate_issues_v3(quality_meta)
        issue_types = {item.get("type") for item in issues if isinstance(item, dict)}

        self.assertIn("quality_gate_expression", issue_types)
        self.assertIn("quality_gate_table", issue_types)
        self.assertIn("quality_gate_milestone", issue_types)
        self.assertIn("style_template_violation", issue_types)

    def test_report_v3_runtime_quality_single_lane_defaults(self):
        env_keys = [
            "REPORT_V3_QUALITY_FORCE_SINGLE_LANE",
            "REPORT_V3_QUALITY_PRIMARY_LANE",
        ]
        env_backup = {key: os.environ.get(key) for key in env_keys}
        try:
            for key in env_keys:
                os.environ.pop(key, None)

            cfg = self.server.get_report_v3_runtime_config("quality")
            self.assertTrue(cfg.get("quality_force_single_lane"))
            self.assertEqual(cfg.get("quality_primary_lane"), "report")
            self.assertTrue(cfg.get("weak_binding_enabled"))
            self.assertTrue(cfg.get("salvage_on_quality_gate_failure"))
            self.assertTrue(cfg.get("failover_on_single_issue"))
            self.assertTrue(cfg.get("blindspot_action_required_quality"))
            self.assertFalse(cfg.get("blindspot_action_required_balanced"))
            self.assertTrue(cfg.get("unknown_followup_enabled"))
            self.assertGreaterEqual(cfg.get("unknown_followup_max_items", 0), 1)
        finally:
            for key, value in env_backup.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_report_v3_failover_single_lane_default_disabled(self):
        self.assertFalse(self.server.REPORT_V3_FAILOVER_FORCE_SINGLE_LANE)

    def test_resolve_report_v3_phase_lane_defaults_and_failover_behavior(self):
        keys = [
            "REPORT_V3_DUAL_STAGE_ENABLED",
            "REPORT_V3_DRAFT_PRIMARY_LANE",
            "REPORT_V3_REVIEW_PRIMARY_LANE",
            "REPORT_V3_FAILOVER_FORCE_SINGLE_LANE",
        ]
        backup = {key: getattr(self.server, key) for key in keys}
        try:
            self.server.REPORT_V3_DUAL_STAGE_ENABLED = True
            self.server.REPORT_V3_DRAFT_PRIMARY_LANE = "question"
            self.server.REPORT_V3_REVIEW_PRIMARY_LANE = "report"
            self.server.REPORT_V3_FAILOVER_FORCE_SINGLE_LANE = True

            self.assertEqual(self.server.resolve_report_v3_phase_lane("draft", pipeline_lane="report"), "question")
            self.assertEqual(self.server.resolve_report_v3_phase_lane("review", pipeline_lane="report"), "report")
            self.assertEqual(self.server.resolve_report_v3_phase_lane("draft", pipeline_lane="question"), "question")
            self.assertEqual(self.server.resolve_report_v3_phase_lane("review", pipeline_lane="question"), "question")

            self.server.REPORT_V3_FAILOVER_FORCE_SINGLE_LANE = False
            self.assertEqual(self.server.resolve_report_v3_phase_lane("review", pipeline_lane="question"), "report")
        finally:
            for key, value in backup.items():
                setattr(self.server, key, value)

    def test_generate_report_v3_pipeline_falls_back_to_alternate_draft_lane_once(self):
        env_keys = [
            "REPORT_V3_DRAFT_RETRY_COUNT",
            "REPORT_V3_REVIEW_BASE_ROUNDS",
            "REPORT_V3_QUALITY_FIX_ROUNDS",
            "REPORT_V3_MIN_REVIEW_ROUNDS",
            "REPORT_V3_QUALITY_FORCE_SINGLE_LANE",
            "REPORT_V3_QUALITY_PRIMARY_LANE",
        ]
        env_backup = {key: os.environ.get(key) for key in env_keys}
        fn_keys = [
            "build_report_evidence_pack",
            "build_report_draft_prompt_v3",
            "parse_structured_json_response",
            "validate_report_draft_v3",
            "build_report_review_prompt_v3",
            "parse_report_review_response_v3",
            "compute_report_quality_meta_v3",
            "build_quality_gate_issues_v3",
            "render_report_from_draft_v3",
            "call_claude",
        ]
        fn_backup = {key: getattr(self.server, key) for key in fn_keys}
        client_keys = ["question_ai_client", "report_ai_client"]
        client_backup = {key: getattr(self.server, key) for key in client_keys}
        draft_calls = []
        try:
            os.environ["REPORT_V3_DRAFT_RETRY_COUNT"] = "1"
            os.environ["REPORT_V3_REVIEW_BASE_ROUNDS"] = "1"
            os.environ["REPORT_V3_QUALITY_FIX_ROUNDS"] = "0"
            os.environ["REPORT_V3_MIN_REVIEW_ROUNDS"] = "1"
            os.environ["REPORT_V3_QUALITY_FORCE_SINGLE_LANE"] = "true"
            os.environ["REPORT_V3_QUALITY_PRIMARY_LANE"] = "report"

            self.server.report_ai_client = object()
            self.server.question_ai_client = object()
            self.server.build_report_evidence_pack = lambda _session: {"facts": [{"q_id": "Q1"}], "overall_coverage": 1.0}
            self.server.build_report_draft_prompt_v3 = lambda *_args, **_kwargs: "draft prompt"
            self.server.parse_structured_json_response = lambda *_args, **_kwargs: {
                "overview": "ok",
                "needs": [],
                "analysis": {},
            }
            self.server.validate_report_draft_v3 = lambda draft, _evidence: (draft, [])
            self.server.build_report_review_prompt_v3 = lambda *_args, **_kwargs: "review prompt"
            self.server.parse_report_review_response_v3 = lambda _raw, parse_meta=None: {
                "passed": True,
                "issues": [],
                "revised_draft": {},
            }
            self.server.compute_report_quality_meta_v3 = lambda *_args, **_kwargs: {
                "mode": "v3_structured_reviewed",
                "evidence_coverage": 1.0,
                "consistency": 1.0,
                "actionability": 1.0,
                "overall": 1.0,
            }
            self.server.build_quality_gate_issues_v3 = lambda *_args, **_kwargs: []
            self.server.render_report_from_draft_v3 = lambda *_args, **_kwargs: "# mock report"

            def _fake_call_claude(_prompt, **kwargs):
                call_type = str(kwargs.get("call_type", "") or "")
                preferred_lane = str(kwargs.get("preferred_lane", "") or "")
                if call_type.startswith("report_v3_draft"):
                    draft_calls.append((call_type, preferred_lane))
                    if preferred_lane == "report":
                        return ""
                    if preferred_lane == "question":
                        return '{"overview":"ok","needs":[],"analysis":{}}'
                if call_type.startswith("report_v3_review_round_"):
                    return '{"passed":true,"issues":[],"revised_draft":{}}'
                return '{"ok":true}'

            self.server.call_claude = _fake_call_claude

            result = self.server.generate_report_v3_pipeline(
                {"topic": "测试"},
                report_profile="quality",
                preferred_lane="report",
            )

            self.assertIsInstance(result, dict)
            self.assertEqual(result.get("status"), "success")
            self.assertEqual(result.get("phase_lanes"), {"draft": "question", "review": "report"})
            self.assertEqual(
                draft_calls,
                [
                    ("report_v3_draft", "report"),
                    ("report_v3_draft_fallback_question", "question"),
                ],
            )
        finally:
            for key, value in fn_backup.items():
                setattr(self.server, key, value)
            for key, value in client_backup.items():
                setattr(self.server, key, value)
            for key, value in env_backup.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_generate_report_v3_pipeline_quality_requires_at_least_two_review_rounds(self):
        env_keys = [
            "REPORT_V3_REVIEW_BASE_ROUNDS",
            "REPORT_V3_QUALITY_FIX_ROUNDS",
            "REPORT_V3_MIN_REVIEW_ROUNDS",
            "REPORT_V3_QUALITY_FORCE_SINGLE_LANE",
            "REPORT_V3_QUALITY_PRIMARY_LANE",
        ]
        env_backup = {key: os.environ.get(key) for key in env_keys}
        fn_keys = [
            "build_report_evidence_pack",
            "build_report_draft_prompt_v3",
            "parse_structured_json_response",
            "validate_report_draft_v3",
            "build_report_review_prompt_v3",
            "parse_report_review_response_v3",
            "compute_report_quality_meta_v3",
            "build_quality_gate_issues_v3",
            "render_report_from_draft_v3",
            "call_claude",
        ]
        fn_backup = {key: getattr(self.server, key) for key in fn_keys}
        review_call_types = []
        phase_lane_calls = []
        try:
            os.environ["REPORT_V3_REVIEW_BASE_ROUNDS"] = "2"
            os.environ["REPORT_V3_QUALITY_FIX_ROUNDS"] = "0"
            os.environ["REPORT_V3_MIN_REVIEW_ROUNDS"] = "2"
            os.environ["REPORT_V3_QUALITY_FORCE_SINGLE_LANE"] = "true"
            os.environ["REPORT_V3_QUALITY_PRIMARY_LANE"] = "report"

            self.server.build_report_evidence_pack = lambda _session: {"facts": [{"q_id": "Q1"}], "overall_coverage": 1.0}
            self.server.build_report_draft_prompt_v3 = lambda *_args, **_kwargs: "draft prompt"
            self.server.parse_structured_json_response = lambda *_args, **_kwargs: {
                "overview": "ok",
                "needs": [],
                "analysis": {},
            }
            self.server.validate_report_draft_v3 = lambda draft, _evidence: (draft, [])
            self.server.build_report_review_prompt_v3 = lambda *_args, **_kwargs: "review prompt"
            self.server.parse_report_review_response_v3 = lambda _raw, parse_meta=None: {
                "passed": True,
                "issues": [],
                "revised_draft": {"overview": "ok", "needs": [], "analysis": {}},
            }
            self.server.compute_report_quality_meta_v3 = lambda *_args, **_kwargs: {
                "mode": "v3_structured_reviewed",
                "evidence_coverage": 1.0,
                "consistency": 1.0,
                "actionability": 1.0,
                "overall": 1.0,
            }
            self.server.build_quality_gate_issues_v3 = lambda *_args, **_kwargs: []
            self.server.render_report_from_draft_v3 = lambda *_args, **_kwargs: "# mock report"

            def _fake_call_claude(_prompt, **kwargs):
                call_type = str(kwargs.get("call_type", "") or "")
                preferred_lane = str(kwargs.get("preferred_lane", "") or "")
                phase_lane_calls.append((call_type, preferred_lane))
                if call_type.startswith("report_v3_review_round_"):
                    review_call_types.append(call_type)
                return "{\"ok\":true}"

            self.server.call_claude = _fake_call_claude

            result = self.server.generate_report_v3_pipeline(
                {"topic": "测试"},
                report_profile="quality",
                preferred_lane="report",
            )

            self.assertIsInstance(result, dict)
            self.assertEqual(result.get("status"), "success")
            self.assertEqual(len(review_call_types), 2)
            self.assertEqual(result.get("review_rounds_executed"), 2)
            self.assertEqual(result.get("min_required_review_rounds"), 2)
            self.assertEqual(result.get("phase_lanes"), {"draft": "report", "review": "report"})

            report_phase_calls = [
                lane
                for call_type, lane in phase_lane_calls
                if call_type.startswith("report_v3_draft") or call_type.startswith("report_v3_review_round_")
            ]
            self.assertTrue(report_phase_calls)
            self.assertTrue(all(lane == "report" for lane in report_phase_calls))
        finally:
            for key, value in fn_backup.items():
                setattr(self.server, key, value)
            for key, value in env_backup.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_generate_report_v3_pipeline_recovers_from_review_parse_failure_via_repair(self):
        env_keys = [
            "REPORT_V3_REVIEW_BASE_ROUNDS",
            "REPORT_V3_QUALITY_FIX_ROUNDS",
            "REPORT_V3_MIN_REVIEW_ROUNDS",
            "REPORT_V3_REVIEW_REPAIR_RETRY_ENABLED",
            "REPORT_V3_REVIEW_REPAIR_MAX_TOKENS",
            "REPORT_V3_REVIEW_REPAIR_TIMEOUT",
        ]
        env_backup = {key: os.environ.get(key) for key in env_keys}
        fn_keys = [
            "build_report_evidence_pack",
            "build_report_draft_prompt_v3",
            "build_report_review_prompt_v3",
            "validate_report_draft_v3",
            "compute_report_quality_meta_v3",
            "build_quality_gate_issues_v3",
            "render_report_from_draft_v3",
            "call_claude",
        ]
        fn_backup = {key: getattr(self.server, key) for key in fn_keys}
        lane_keys = [
            "REPORT_V3_DRAFT_PRIMARY_LANE",
            "REPORT_V3_REVIEW_PRIMARY_LANE",
        ]
        lane_backup = {key: getattr(self.server, key) for key in lane_keys}
        call_types = []
        try:
            os.environ["REPORT_V3_REVIEW_BASE_ROUNDS"] = "1"
            os.environ["REPORT_V3_QUALITY_FIX_ROUNDS"] = "0"
            os.environ["REPORT_V3_MIN_REVIEW_ROUNDS"] = "1"
            os.environ["REPORT_V3_REVIEW_REPAIR_RETRY_ENABLED"] = "true"
            os.environ["REPORT_V3_REVIEW_REPAIR_MAX_TOKENS"] = "1800"
            os.environ["REPORT_V3_REVIEW_REPAIR_TIMEOUT"] = "20"
            self.server.REPORT_V3_DRAFT_PRIMARY_LANE = "report"
            self.server.REPORT_V3_REVIEW_PRIMARY_LANE = "report"

            self.server.build_report_evidence_pack = lambda _session: {"facts": [{"q_id": "Q1"}], "overall_coverage": 1.0}
            self.server.build_report_draft_prompt_v3 = lambda *_args, **_kwargs: "draft prompt"
            self.server.build_report_review_prompt_v3 = lambda *_args, **_kwargs: "review prompt"
            self.server.validate_report_draft_v3 = lambda draft, _evidence: (draft, [])
            self.server.compute_report_quality_meta_v3 = lambda *_args, **_kwargs: {
                "mode": "v3_structured_reviewed",
                "evidence_coverage": 1.0,
                "consistency": 1.0,
                "actionability": 1.0,
                "overall": 1.0,
            }
            self.server.build_quality_gate_issues_v3 = lambda *_args, **_kwargs: []
            self.server.render_report_from_draft_v3 = lambda *_args, **_kwargs: "# repaired report"

            def _fake_call_claude(_prompt, **kwargs):
                call_type = str(kwargs.get("call_type", "") or "")
                call_types.append(call_type)
                if call_type.startswith("report_v3_draft"):
                    return (
                        '{"overview":"初版","needs":[{"name":"需求稳定性","priority":"P0","description":"控制需求频繁变更","evidence_refs":["Q1"]}],'
                        '"analysis":{"customer_needs":"需要稳定节奏","business_flow":"跨团队链路长","tech_constraints":"质量门槛高","project_constraints":"协调成本高"},'
                        '"visualizations":{},"solutions":[],"risks":[],"actions":[],"open_questions":[],"evidence_index":[]}'
                    )
                if call_type.startswith("report_v3_review_round_"):
                    return "这是上一轮审稿的非 JSON 输出，请转成结构化结果。"
                if call_type.startswith("report_v3_review_parse_repair_round_"):
                    return (
                        '{"passed": true, "issues": [], '
                        '"revised_draft": {"overview": "修复后的概述", '
                        '"actions": [{"action": "建立变更冻结窗口", "owner": "产品经理", "timeline": "两周内", "metric": "需求变更率下降20%", "evidence_refs": ["Q1"]}]}}'
                    )
                return ""

            self.server.call_claude = _fake_call_claude

            result = self.server.generate_report_v3_pipeline(
                {"topic": "测试"},
                report_profile="balanced",
                preferred_lane="report",
            )

            self.assertIsInstance(result, dict)
            self.assertEqual(result.get("status"), "success")
            self.assertEqual(result.get("phase_lanes"), {"draft": "report", "review": "report"})
            self.assertEqual(result.get("draft_snapshot", {}).get("overview"), "修复后的概述")
            self.assertIn("report_v3_review_parse_repair_round_1", call_types)
        finally:
            for key, value in fn_backup.items():
                setattr(self.server, key, value)
            for key, value in lane_backup.items():
                setattr(self.server, key, value)
            for key, value in env_backup.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_filter_model_review_issues_v3_skips_hallucinated_template_rules(self):
        draft = {
            "overview": "ok",
            "needs": [],
            "analysis": {},
            "visualizations": {},
            "solutions": [],
            "risks": [{"risk": "风险A", "impact": "高", "mitigation": "降级", "evidence_refs": []}],
            "actions": [],
            "open_questions": [{"question": "待补问A", "reason": "未知", "impact": "中", "suggested_follow_up": "补问", "evidence_refs": []}],
            "evidence_index": [],
        }
        model_issues = [
            {
                "type": "quality_gate_table",
                "severity": "medium",
                "message": "needs表缺少acceptance_criteria字段",
                "target": "needs[]",
            },
            {
                "type": "no_evidence",
                "severity": "high",
                "message": "open_questions 缺少证据引用",
                "target": "open_questions[0]",
            },
            {
                "type": "no_evidence",
                "severity": "high",
                "message": "risks 缺少证据引用",
                "target": "risks[0]",
            },
        ]
        filtered = self.server.filter_model_review_issues_v3(model_issues, draft)
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0].get("target"), "risks[0]")

    def test_filter_model_review_issues_v3_soft_passes_blindspot_when_open_questions_covered(self):
        draft = {
            "overview": "ok",
            "needs": [],
            "analysis": {},
            "visualizations": {},
            "solutions": [],
            "risks": [],
            "actions": [],
            "open_questions": [
                {
                    "question": "业务流程中的角色分工仍不清晰，是否需要补采访谈？",
                    "reason": "角色分工未澄清",
                    "impact": "影响执行边界",
                    "suggested_follow_up": "补采角色职责口径",
                    "evidence_refs": ["Q2"],
                }
            ],
            "evidence_index": [],
        }
        evidence_pack = {
            "facts": [{"q_id": "Q2"}],
            "unknowns": [{"q_id": "Q2"}],
            "quality_snapshot": {"average_quality_score": 0.22},
        }
        model_issues = [
            {
                "type": "blindspot",
                "severity": "high",
                "message": "盲区证据'业务流程: 角色分工'已在open_questions中记录，但未纳入actions行动计划",
                "target": "actions",
            }
        ]
        filtered = self.server.filter_model_review_issues_v3(
            model_issues,
            draft,
            evidence_pack=evidence_pack,
            runtime_profile="balanced",
        )
        self.assertEqual(filtered, [])

    def test_filter_model_review_issues_v3_soft_passes_blindspot_cleanup_issue(self):
        draft = {
            "overview": "ok",
            "needs": [],
            "analysis": {},
            "visualizations": {},
            "solutions": [],
            "risks": [],
            "actions": [],
            "open_questions": [
                {
                    "question": "Q1/Q2/Q3 的不确定信号是否属于同一类角色分工问题？",
                    "reason": "描述重复",
                    "impact": "影响清晰度",
                    "suggested_follow_up": "去重合并",
                    "evidence_refs": ["Q1"],
                }
            ],
            "evidence_index": [],
        }
        model_issues = [
            {
                "type": "blindspot",
                "severity": "medium",
                "message": "open_questions 中 Q1/Q2/Q3 的重复不确定信号描述未合并，且描述过于通用，需去重以提高清晰度。",
                "target": "open_questions[0..2]",
            }
        ]

        filtered = self.server.filter_model_review_issues_v3(model_issues, draft, runtime_profile="balanced")
        self.assertEqual(filtered, [])

    def test_filter_model_review_issues_v3_soft_passes_blindspot_when_open_questions_cover_all_aspects(self):
        draft = {
            "overview": "ok",
            "needs": [],
            "analysis": {},
            "visualizations": {},
            "solutions": [],
            "risks": [],
            "actions": [],
            "open_questions": [
                {"question": "请补充决策因素的判断依据", "reason": "决策因素未覆盖"},
                {"question": "请补充信息渠道的获取方式", "reason": "信息渠道未覆盖"},
                {"question": "请补充行为模式的差异", "reason": "行为模式未覆盖"},
            ],
            "evidence_index": [],
        }
        evidence_pack = {
            "blindspots": [
                {"dimension": "客户需求", "aspect": "决策因素"},
                {"dimension": "客户需求", "aspect": "信息渠道"},
                {"dimension": "客户需求", "aspect": "行为模式"},
            ]
        }
        model_issues = [
            {
                "type": "blindspot",
                "severity": "high",
                "message": "部分关键盲区未转化为待确认问题",
                "target": "open_questions",
            }
        ]

        filtered = self.server.filter_model_review_issues_v3(
            model_issues,
            draft,
            evidence_pack=evidence_pack,
            runtime_profile="balanced",
        )
        self.assertEqual(filtered, [])

    def test_filter_model_review_issues_v3_ignores_visualization_no_evidence(self):
        draft = {
            "overview": "ok",
            "needs": [],
            "analysis": {},
            "visualizations": {
                "priority_quadrant_mermaid": "",
                "business_flow_mermaid": "",
                "demand_pie_mermaid": "",
                "architecture_mermaid": "",
            },
            "solutions": [],
            "risks": [],
            "actions": [],
            "open_questions": [],
            "evidence_index": [],
        }
        model_issues = [
            {
                "type": "no_evidence",
                "severity": "low",
                "message": "visualizations 中的 demand_pie_mermaid 为空字符串",
                "target": "visualizations.demand_pie_mermaid",
            }
        ]

        filtered = self.server.filter_model_review_issues_v3(model_issues, draft, runtime_profile="balanced")
        self.assertEqual(filtered, [])

    def test_filter_model_review_issues_v3_soft_passes_not_actionable_when_fields_complete(self):
        draft = {
            "overview": "ok",
            "needs": [],
            "analysis": {},
            "visualizations": {},
            "solutions": [
                {
                    "title": "方案A",
                    "description": "描述",
                    "owner": "产品经理",
                    "timeline": "2-4周内",
                    "metric": "形成方案评审纪要并确认验收口径",
                    "evidence_refs": ["Q1"],
                }
            ],
            "risks": [],
            "actions": [],
            "open_questions": [],
            "evidence_index": [],
        }
        model_issues = [
            {
                "type": "not_actionable",
                "severity": "medium",
                "message": "solutions[0] 缺少明确的 timeline 时间节点。",
                "target": "solutions[0].timeline",
            }
        ]
        filtered = self.server.filter_model_review_issues_v3(model_issues, draft, runtime_profile="balanced")
        self.assertEqual(filtered, [])

    def test_filter_model_review_issues_v3_soft_passes_not_actionable_when_long_horizon_action_exists(self):
        draft = {
            "overview": "ok",
            "needs": [],
            "analysis": {},
            "visualizations": {},
            "solutions": [],
            "risks": [],
            "actions": [
                {
                    "action": "围绕角色分工建立长期运营闭环并组织月度复盘",
                    "owner": "业务负责人",
                    "timeline": "季度内",
                    "metric": "发布闭环机制并完成至少1次跨角色复盘，输出长期优化清单",
                    "evidence_refs": ["Q1"],
                }
            ],
            "open_questions": [],
            "evidence_index": [],
        }
        model_issues = [
            {
                "type": "not_actionable",
                "severity": "medium",
                "message": "actions 部分原有的长期里程碑缺乏具体的落地执行动作，需补充全周期动作。",
                "target": "actions",
            }
        ]
        filtered = self.server.filter_model_review_issues_v3(model_issues, draft, runtime_profile="balanced")
        self.assertEqual(filtered, [])

    def test_filter_model_review_issues_v3_soft_passes_blindspot_when_open_questions_cover_all_aspects(self):
        draft = {
            "overview": "ok",
            "needs": [],
            "analysis": {},
            "visualizations": {},
            "solutions": [],
            "risks": [],
            "actions": [],
            "open_questions": [
                {"question": "请补充决策因素的判断依据", "reason": "决策因素未覆盖", "impact": "影响优先级", "suggested_follow_up": "补充决策依据", "evidence_refs": ["Q1"]},
                {"question": "请补充信息渠道的获取方式", "reason": "信息渠道未覆盖", "impact": "影响触达判断", "suggested_follow_up": "补充触达路径", "evidence_refs": ["Q2"]},
                {"question": "请补充行为模式的差异", "reason": "行为模式未覆盖", "impact": "影响场景判断", "suggested_follow_up": "补充行为差异", "evidence_refs": ["Q3"]},
            ],
            "evidence_index": [],
        }
        evidence_pack = {
            "blindspots": [
                {"dimension": "客户需求", "aspect": "决策因素"},
                {"dimension": "客户需求", "aspect": "信息渠道"},
                {"dimension": "客户需求", "aspect": "行为模式"},
            ]
        }
        model_issues = [
            {
                "type": "blindspot",
                "severity": "high",
                "message": "部分关键盲区未转化为待确认问题",
                "target": "open_questions",
            }
        ]

        filtered = self.server.filter_model_review_issues_v3(
            model_issues,
            draft,
            evidence_pack=evidence_pack,
            runtime_profile="balanced",
        )
        self.assertEqual(filtered, [])

    def test_filter_model_review_issues_v3_ignores_visualization_no_evidence(self):
        draft = {
            "overview": "ok",
            "needs": [],
            "analysis": {},
            "visualizations": {
                "priority_quadrant_mermaid": "",
                "business_flow_mermaid": "",
                "demand_pie_mermaid": "",
                "architecture_mermaid": "",
            },
            "solutions": [],
            "risks": [],
            "actions": [],
            "open_questions": [],
            "evidence_index": [],
        }
        model_issues = [
            {
                "type": "no_evidence",
                "severity": "low",
                "message": "visualizations 中 demand_pie_mermaid 为空字符串",
                "target": "visualizations.demand_pie_mermaid",
            }
        ]

        filtered = self.server.filter_model_review_issues_v3(model_issues, draft, runtime_profile="balanced")
        self.assertEqual(filtered, [])

    def test_filter_model_review_issues_v3_ignores_binding_mode_no_evidence_hallucination(self):
        draft = {
            "overview": "ok",
            "needs": [],
            "analysis": {},
            "visualizations": {},
            "solutions": [
                {
                    "title": "方案A",
                    "description": "描述",
                    "owner": "张三",
                    "timeline": "2周内",
                    "metric": "完成率>90%",
                    "evidence_refs": ["Q1"],
                    "evidence_binding_mode": "strong_explicit",
                }
            ],
            "risks": [],
            "actions": [],
            "open_questions": [],
            "evidence_index": [],
        }
        model_issues = [
            {
                "type": "no_evidence",
                "severity": "medium",
                "message": "solutions[0].evidence_binding_mode 字段为空",
                "target": "solutions[0].evidence_binding_mode",
            }
        ]

        filtered = self.server.filter_model_review_issues_v3(model_issues, draft, runtime_profile="balanced")
        self.assertEqual(filtered, [])

    def test_apply_deterministic_report_repairs_v3_binds_and_prunes_no_evidence(self):
        draft = {
            "overview": "概述",
            "needs": [],
            "analysis": {},
            "visualizations": {},
            "solutions": [],
            "risks": [
                {"risk": "跨部门协同阻塞", "impact": "交付延期", "mitigation": "建立周会", "evidence_refs": []}
            ],
            "actions": [
                {"action": "明确角色分工", "owner": "项目经理", "timeline": "2周内", "metric": "职责清单发布", "evidence_refs": []}
            ],
            "open_questions": [],
            "evidence_index": [
                {"claim": "结论A", "confidence": "high", "evidence_refs": []}
            ],
        }
        evidence_pack = {
            "facts": [
                {"q_id": "Q1", "dimension": "business_process", "dimension_name": "业务流程", "question": "跨部门协同现状", "answer": "目前职责边界不清晰", "quality_score": 0.72},
                {"q_id": "Q2", "dimension": "business_process", "dimension_name": "业务流程", "question": "角色分工是否明确", "answer": "还不明确", "quality_score": 0.68},
            ],
            "quality_snapshot": {"average_quality_score": 0.45},
            "dimension_coverage": {
                "business_process": {"name": "业务流程", "missing_aspects": ["角色分工"]},
            },
        }
        issues = [
            {"type": "no_evidence", "target": "risks[0]"},
            {"type": "no_evidence", "target": "actions[0]"},
            {"type": "no_evidence", "target": "evidence_index[0]"},
        ]
        repaired = self.server.apply_deterministic_report_repairs_v3(draft, evidence_pack, issues, runtime_profile="quality")
        self.assertTrue(repaired.get("changed"))
        repaired_draft = repaired.get("draft", {})

        risks = repaired_draft.get("risks", [])
        actions = repaired_draft.get("actions", [])
        open_questions = repaired_draft.get("open_questions", [])
        risk_refs = risks[0].get("evidence_refs", []) if risks else []
        action_refs = actions[0].get("evidence_refs", []) if actions else []
        self.assertTrue(risk_refs or action_refs or open_questions)
        self.assertEqual(len(repaired_draft.get("evidence_index", [])), 0)

    def test_apply_deterministic_report_repairs_v3_prunes_orphan_evidence_index(self):
        draft = {
            "overview": "概述",
            "needs": [
                {"name": "需求A", "priority": "P1", "description": "描述", "evidence_refs": ["Q1"]}
            ],
            "analysis": {},
            "visualizations": {},
            "solutions": [],
            "risks": [],
            "actions": [],
            "open_questions": [],
            "evidence_index": [
                {"claim": "核心痛点为人工收集效率低", "confidence": "high", "evidence_refs": ["Q10"]}
            ],
        }
        evidence_pack = {
            "facts": [
                {"q_id": "Q1", "dimension": "customer_needs", "dimension_name": "客户需求", "question": "问题A", "answer": "回答A", "quality_score": 0.72},
                {"q_id": "Q10", "dimension": "customer_needs", "dimension_name": "客户需求", "question": "问题B", "answer": "回答B", "quality_score": 0.68},
            ],
            "quality_snapshot": {"average_quality_score": 0.45},
        }
        issues = [
            {"type": "no_evidence", "target": "evidence_index[0]"},
        ]
        repaired = self.server.apply_deterministic_report_repairs_v3(draft, evidence_pack, issues, runtime_profile="balanced")
        self.assertTrue(repaired.get("changed"))
        self.assertEqual([], repaired.get("draft", {}).get("evidence_index", []))

    def test_apply_deterministic_report_repairs_v3_demotes_need_without_evidence_to_open_question(self):
        draft = {
            "overview": "概述",
            "needs": [
                {
                    "name": "跨部门协作流程明确",
                    "priority": "P1",
                    "description": "当前只是待确认方向",
                    "evidence_refs": [],
                    "evidence_binding_mode": "pending_follow_up",
                }
            ],
            "analysis": {},
            "visualizations": {},
            "solutions": [],
            "risks": [],
            "actions": [],
            "open_questions": [],
            "evidence_index": [],
        }
        evidence_pack = {
            "facts": [{"q_id": "Q1", "dimension": "business_process", "dimension_name": "业务流程", "question": "流程是否明确", "answer": "当前仍待确认", "quality_score": 0.52}],
            "quality_snapshot": {"average_quality_score": 0.52},
            "dimension_coverage": {"business_process": {"name": "业务流程", "missing_aspects": ["角色分工"]}},
        }
        issues = [{"type": "no_evidence", "target": "needs[0]"}]
        repaired = self.server.apply_deterministic_report_repairs_v3(draft, evidence_pack, issues, runtime_profile="balanced")
        self.assertTrue(repaired.get("changed"))
        repaired_draft = repaired.get("draft", {})
        self.assertEqual([], repaired_draft.get("needs", []))
        self.assertTrue(repaired_draft.get("open_questions", []))
        self.assertIn("跨部门协作流程明确", repaired_draft["open_questions"][0].get("question", ""))

    def test_apply_deterministic_report_repairs_v3_adds_blindspot_pending_action(self):
        draft = {
            "overview": "概述",
            "needs": [],
            "analysis": {},
            "visualizations": {},
            "solutions": [],
            "risks": [],
            "actions": [],
            "open_questions": [
                {
                    "question": "业务流程中的角色分工仍不清晰，是否需要补采访谈？",
                    "reason": "角色分工未澄清",
                    "impact": "影响执行边界",
                    "suggested_follow_up": "补采角色职责口径",
                    "evidence_refs": ["Q1"],
                }
            ],
            "evidence_index": [],
        }
        evidence_pack = {
            "facts": [
                {
                    "q_id": "Q1",
                    "dimension": "business_process",
                    "dimension_name": "业务流程",
                    "question": "角色分工是否明确",
                    "answer": "目前不明确",
                    "quality_score": 0.62,
                }
            ],
            "blindspots": [{"dimension": "业务流程", "aspect": "角色分工"}],
            "unknowns": [{"q_id": "Q1", "dimension": "业务流程", "reason": "回答存在模糊表述"}],
            "quality_snapshot": {"average_quality_score": 0.25},
        }
        issues = [
            {
                "type": "blindspot",
                "severity": "high",
                "target": "actions",
                "message": "盲区证据'业务流程: 角色分工'已在open_questions中记录，但未纳入actions行动计划",
            }
        ]
        repaired = self.server.apply_deterministic_report_repairs_v3(draft, evidence_pack, issues, runtime_profile="quality")
        self.assertTrue(repaired.get("changed"))
        repaired_draft = repaired.get("draft", {})
        actions = repaired_draft.get("actions", [])
        self.assertTrue(actions)
        self.assertIn("角色分工", actions[0].get("action", ""))
        self.assertTrue(actions[0].get("evidence_refs"))
        self.assertTrue(actions[0].get("owner"))
        self.assertTrue(actions[0].get("timeline"))
        self.assertTrue(actions[0].get("metric"))

    def test_apply_deterministic_report_repairs_v3_fills_not_actionable_action_fields(self):
        draft = {
            "overview": "概述",
            "needs": [],
            "analysis": {},
            "visualizations": {},
            "solutions": [],
            "risks": [],
            "actions": [
                {
                    "action": "补采并确认角色分工边界",
                    "owner": "",
                    "timeline": "",
                    "metric": "",
                    "evidence_refs": [],
                }
            ],
            "open_questions": [],
            "evidence_index": [],
        }
        evidence_pack = {
            "facts": [
                {
                    "q_id": "Q1",
                    "dimension": "business_process",
                    "dimension_name": "业务流程",
                    "question": "角色分工是否明确",
                    "answer": "目前分工边界不清晰，需要补充澄清",
                    "quality_score": 0.71,
                }
            ],
            "quality_snapshot": {"average_quality_score": 0.51},
            "dimension_coverage": {
                "business_process": {"name": "业务流程", "missing_aspects": ["角色分工"]},
            },
        }
        issues = [
            {
                "type": "not_actionable",
                "severity": "medium",
                "target": "actions[0]",
                "message": "actions 缺少 owner/timeline/metric",
            }
        ]
        repaired = self.server.apply_deterministic_report_repairs_v3(draft, evidence_pack, issues, runtime_profile="quality")
        self.assertTrue(repaired.get("changed"))
        action = repaired.get("draft", {}).get("actions", [{}])[0]
        self.assertTrue(action.get("owner"))
        self.assertTrue(action.get("timeline"))
        self.assertTrue(action.get("metric"))
        self.assertTrue(action.get("evidence_refs"))
        self.assertEqual(action.get("evidence_binding_mode"), "weak_inferred")

    def test_apply_deterministic_report_repairs_v3_upgrades_blindspot_to_actionable_action(self):
        draft = {
            "overview": "概述",
            "needs": [],
            "analysis": {},
            "visualizations": {},
            "solutions": [],
            "risks": [],
            "actions": [],
            "open_questions": [
                {
                    "question": "业务流程中的角色分工仍不清晰，是否需要补采访谈？",
                    "reason": "角色分工未澄清",
                    "impact": "影响执行边界",
                    "suggested_follow_up": "补采角色职责口径",
                    "evidence_refs": ["Q1"],
                }
            ],
            "evidence_index": [],
        }
        evidence_pack = {
            "facts": [
                {
                    "q_id": "Q1",
                    "dimension": "business_process",
                    "dimension_name": "业务流程",
                    "question": "角色分工是否明确",
                    "answer": "目前还不明确，需要后续明确责任边界",
                    "quality_score": 0.67,
                },
                {
                    "q_id": "Q2",
                    "dimension": "business_process",
                    "dimension_name": "业务流程",
                    "question": "责任边界是否已沉淀文档",
                    "answer": "还没有文档，需要补采并明确责任边界",
                    "quality_score": 0.7,
                },
            ],
            "blindspots": [{"dimension": "业务流程", "aspect": "角色分工"}],
            "quality_snapshot": {"average_quality_score": 0.48},
        }
        issues = [
            {
                "type": "blindspot",
                "severity": "high",
                "target": "actions",
                "message": "盲区证据'业务流程: 角色分工'已在open_questions中记录，但未纳入actions行动计划",
            }
        ]
        repaired = self.server.apply_deterministic_report_repairs_v3(draft, evidence_pack, issues, runtime_profile="balanced")
        self.assertTrue(repaired.get("changed"))
        action = repaired.get("draft", {}).get("actions", [{}])[0]
        self.assertIn("角色分工", action.get("action", ""))
        self.assertTrue(action.get("owner"))
        self.assertTrue(action.get("timeline"))
        self.assertTrue(action.get("metric"))
        self.assertTrue(action.get("evidence_refs"))

    def test_apply_deterministic_report_repairs_v3_marks_overview_blindspot_status(self):
        draft = {
            "overview": "当前结论已形成，但部分信息仍需补充。",
            "needs": [],
            "analysis": {"business_flow": "当前流程分析已形成，但角色边界仍需补充。"},
            "visualizations": {},
            "solutions": [],
            "risks": [],
            "actions": [],
            "open_questions": [],
            "evidence_index": [],
        }
        evidence_pack = {
            "facts": [{"q_id": "Q1", "dimension": "business_process", "dimension_name": "业务流程"}],
            "blindspots": [{"dimension": "业务流程", "aspect": "角色分工"}],
            "quality_snapshot": {"average_quality_score": 0.52},
        }
        issues = [
            {
                "type": "blindspot",
                "severity": "high",
                "target": "overview",
                "message": "overview 未明确标注业务流程-角色分工为盲区状态",
            }
        ]
        repaired = self.server.apply_deterministic_report_repairs_v3(draft, evidence_pack, issues, runtime_profile="balanced")
        self.assertTrue(repaired.get("changed"))
        self.assertIn("待补采盲区", repaired.get("draft", {}).get("overview", ""))
        self.assertIn("角色分工", repaired.get("draft", {}).get("overview", ""))

    def test_apply_deterministic_report_repairs_v3_marks_analysis_blindspot_status(self):
        draft = {
            "overview": "概述",
            "needs": [],
            "analysis": {"business_flow": "当前流程梳理基本完成，但仍有缺口。"},
            "visualizations": {},
            "solutions": [],
            "risks": [],
            "actions": [],
            "open_questions": [],
            "evidence_index": [],
        }
        evidence_pack = {
            "facts": [{"q_id": "Q1", "dimension": "business_process", "dimension_name": "业务流程"}],
            "blindspots": [{"dimension": "业务流程", "aspect": "角色分工"}],
            "quality_snapshot": {"average_quality_score": 0.52},
        }
        issues = [
            {
                "type": "blindspot",
                "severity": "medium",
                "target": "analysis.business_flow",
                "message": "建议同步更新analysis.business_flow以保持上下文一致。",
            }
        ]
        repaired = self.server.apply_deterministic_report_repairs_v3(draft, evidence_pack, issues, runtime_profile="balanced")
        self.assertTrue(repaired.get("changed"))
        self.assertIn("待补采盲区", repaired.get("draft", {}).get("analysis", {}).get("business_flow", ""))
        self.assertIn("角色分工", repaired.get("draft", {}).get("analysis", {}).get("business_flow", ""))

    def test_apply_deterministic_report_repairs_v3_normalizes_action_timeline_for_milestone(self):
        draft = {
            "overview": "概述",
            "needs": [],
            "analysis": {},
            "visualizations": {},
            "solutions": [],
            "risks": [],
            "actions": [
                {
                    "action": "补采并确认角色分工边界",
                    "owner": "产品经理",
                    "timeline": "近期推进",
                    "metric": "完成至少3条可追溯证据并更新结论",
                    "evidence_refs": ["Q1"],
                }
            ],
            "open_questions": [],
            "evidence_index": [],
        }
        evidence_pack = {
            "facts": [
                {
                    "q_id": "Q1",
                    "dimension": "business_process",
                    "dimension_name": "业务流程",
                    "question": "角色分工是否明确",
                    "answer": "当前责任边界不清晰，需要补采并确认",
                    "quality_score": 0.7,
                }
            ],
            "quality_snapshot": {"average_quality_score": 0.54},
        }
        repaired = self.server.apply_deterministic_report_repairs_v3(draft, evidence_pack, [], runtime_profile="balanced")
        self.assertTrue(repaired.get("changed"))
        action = repaired.get("draft", {}).get("actions", [{}])[0]
        self.assertEqual("1-2周内", action.get("timeline"))

    def test_apply_deterministic_report_repairs_v3_normalizes_action_metric_for_acceptance(self):
        draft = {
            "overview": "概述",
            "needs": [],
            "analysis": {},
            "visualizations": {},
            "solutions": [],
            "risks": [],
            "actions": [
                {
                    "action": "补采并确认角色分工边界",
                    "owner": "产品经理",
                    "timeline": "1-2周内",
                    "metric": "持续优化",
                    "evidence_refs": ["Q1"],
                }
            ],
            "open_questions": [],
            "evidence_index": [],
        }
        evidence_pack = {
            "facts": [
                {
                    "q_id": "Q1",
                    "dimension": "business_process",
                    "dimension_name": "业务流程",
                    "question": "角色分工是否明确",
                    "answer": "当前责任边界不清晰，需要补采并确认",
                    "quality_score": 0.7,
                }
            ],
            "quality_snapshot": {"average_quality_score": 0.54},
        }
        repaired = self.server.apply_deterministic_report_repairs_v3(draft, evidence_pack, [], runtime_profile="balanced")
        self.assertTrue(repaired.get("changed"))
        action = repaired.get("draft", {}).get("actions", [{}])[0]
        self.assertIn("至少3", action.get("metric", ""))

    def test_apply_deterministic_report_repairs_v3_reinforces_long_horizon_actions(self):
        draft = {
            "overview": "概述",
            "needs": [],
            "analysis": {},
            "visualizations": {},
            "solutions": [],
            "risks": [],
            "actions": [
                {
                    "action": "持续优化角色分工协同",
                    "owner": "业务负责人",
                    "timeline": "季度内",
                    "metric": "持续优化",
                    "evidence_refs": ["Q1"],
                }
            ],
            "open_questions": [],
            "evidence_index": [],
        }
        evidence_pack = {
            "facts": [
                {
                    "q_id": "Q1",
                    "dimension": "business_process",
                    "dimension_name": "业务流程",
                    "question": "角色分工是否明确",
                    "answer": "当前需要长期跟踪角色分工协同效果",
                    "quality_score": 0.7,
                }
            ],
            "quality_snapshot": {"average_quality_score": 0.58},
        }
        issues = [
            {
                "type": "not_actionable",
                "severity": "medium",
                "target": "actions",
                "message": "actions 部分原有的长期里程碑虽然存在但缺乏具体的落地执行动作，需补充长期运营执行动作以覆盖全周期。",
            }
        ]
        repaired = self.server.apply_deterministic_report_repairs_v3(draft, evidence_pack, issues, runtime_profile="balanced")
        self.assertTrue(repaired.get("changed"))
        action = repaired.get("draft", {}).get("actions", [{}])[0]
        self.assertIn("复盘", action.get("action", ""))
        self.assertIn("闭环", action.get("metric", ""))

    def test_compute_report_quality_meta_v3_counts_weak_binding_ratio(self):
        draft = {
            "overview": "概述",
            "needs": [{"name": "需求A", "priority": "P1", "description": "描述", "evidence_refs": ["Q1"]}],
            "analysis": {
                "customer_needs": "A",
                "business_flow": "B",
                "tech_constraints": "C",
                "project_constraints": "D",
            },
            "visualizations": {},
            "solutions": [],
            "risks": [],
            "actions": [
                {
                    "action": "行动A",
                    "owner": "负责人",
                    "timeline": "2周内",
                    "metric": "完成率>=90%",
                    "evidence_refs": ["Q2"],
                    "evidence_binding_mode": "weak_inferred",
                }
            ],
            "open_questions": [],
            "evidence_index": [],
        }
        evidence_pack = {
            "facts": [{"q_id": "Q1"}, {"q_id": "Q2"}],
            "contradictions": [],
            "unknowns": [],
            "blindspots": [],
            "quality_snapshot": {"average_quality_score": 0.6},
        }
        meta = self.server.compute_report_quality_meta_v3(draft, evidence_pack, [])
        self.assertGreater(meta.get("weak_binding_count", 0), 0)
        self.assertGreater(meta.get("weak_binding_ratio", 0), 0)
        self.assertLess(meta.get("evidence_coverage", 1.0), 1.0)

    def test_compute_report_quality_meta_v3_tracks_weak_binding_by_field_without_open_questions(self):
        draft = {
            "overview": "概述",
            "needs": [{"name": "需求A", "priority": "P1", "description": "描述", "evidence_refs": ["Q1"]}],
            "analysis": {
                "customer_needs": "A",
                "business_flow": "B",
                "tech_constraints": "C",
                "project_constraints": "D",
            },
            "visualizations": {},
            "solutions": [
                {
                    "title": "方案A",
                    "description": "描述",
                    "owner": "张三",
                    "timeline": "2周",
                    "metric": "完成率>=90%",
                    "evidence_refs": ["Q2"],
                    "evidence_binding_mode": "weak_inferred",
                }
            ],
            "risks": [
                {
                    "risk": "风险A",
                    "impact": "高",
                    "mitigation": "补采",
                    "evidence_refs": ["Q3"],
                    "evidence_binding_mode": "weak_inferred",
                }
            ],
            "actions": [
                {
                    "action": "行动A",
                    "owner": "负责人",
                    "timeline": "2周内",
                    "metric": "完成率>=90%",
                    "evidence_refs": ["Q4"],
                    "evidence_binding_mode": "strong_explicit",
                }
            ],
            "open_questions": [
                {
                    "question": "还需确认什么？",
                    "reason": "待补问",
                    "impact": "影响判断",
                    "suggested_follow_up": "继续访谈",
                    "evidence_refs": ["Q5"],
                    "evidence_binding_mode": "weak_inferred",
                }
            ],
            "evidence_index": [],
        }
        evidence_pack = {
            "facts": [{"q_id": f"Q{i}"} for i in range(1, 6)],
            "contradictions": [],
            "unknowns": [],
            "blindspots": [],
            "quality_snapshot": {"average_quality_score": 0.52},
        }

        meta = self.server.compute_report_quality_meta_v3(draft, evidence_pack, [])

        self.assertNotIn("open_questions", meta.get("weak_binding_ratio_by_field", {}))
        self.assertAlmostEqual(1.0, meta["weak_binding_ratio_by_field"]["solutions"], places=3)
        self.assertAlmostEqual(1.0, meta["weak_binding_ratio_by_field"]["risks"], places=3)
        self.assertAlmostEqual(0.0, meta["weak_binding_ratio_by_field"]["actions"], places=3)

    def test_compute_report_quality_meta_v3_excludes_pending_follow_up_open_questions_from_evidence_gate(self):
        draft = {
            "overview": "概述",
            "needs": [{"name": "需求A", "priority": "P1", "description": "描述", "evidence_refs": ["Q1"]}],
            "analysis": {
                "customer_needs": "A",
                "business_flow": "B",
                "tech_constraints": "C",
                "project_constraints": "D",
            },
            "visualizations": {},
            "solutions": [],
            "risks": [],
            "actions": [],
            "open_questions": [
                {
                    "question": "是否需要补采？",
                    "reason": "证据不足",
                    "impact": "影响判断",
                    "suggested_follow_up": "继续访谈",
                    "evidence_refs": ["Q2"],
                    "evidence_binding_mode": "pending_follow_up",
                }
            ],
            "evidence_index": [],
        }
        evidence_pack = {
            "facts": [{"q_id": "Q1"}, {"q_id": "Q2"}],
            "contradictions": [],
            "unknowns": [{"q_id": "Q2"}],
            "blindspots": [{"dimension": "业务流程", "aspect": "角色分工"}],
            "quality_snapshot": {"average_quality_score": 0.28},
        }
        meta = self.server.compute_report_quality_meta_v3(draft, evidence_pack, [])
        self.assertEqual(meta.get("claim_total"), 1)
        self.assertEqual(meta.get("claim_with_evidence"), 1)
        self.assertAlmostEqual(meta.get("evidence_coverage"), 1.0, places=3)

    def test_validate_report_draft_v3_defaults_binding_mode_when_refs_present(self):
        evidence_pack = {"facts": [{"q_id": "Q1"}], "contradictions": [], "blindspots": []}
        draft = {
            "overview": "概述",
            "needs": [{"name": "需求A", "priority": "P1", "description": "描述", "evidence_refs": ["Q1"]}],
            "analysis": {"customer_needs": "A", "business_flow": "B", "tech_constraints": "C", "project_constraints": "D"},
            "visualizations": {},
            "solutions": [{"title": "方案A", "description": "描述", "owner": "张三", "timeline": "2周", "metric": "完成率", "evidence_refs": ["Q1"]}],
            "risks": [{"risk": "风险A", "impact": "高", "mitigation": "规避", "evidence_refs": ["Q1"]}],
            "actions": [{"action": "行动A", "owner": "李四", "timeline": "1周", "metric": "完成", "evidence_refs": ["Q1"]}],
            "open_questions": [],
            "evidence_index": [{"claim": "结论A", "confidence": "high", "evidence_refs": ["Q1"]}],
        }
        normalized, issues = self.server.validate_report_draft_v3(draft, evidence_pack)
        self.assertEqual([], [item for item in issues if item.get("type") == "invalid_evidence_ref"])
        self.assertEqual("strong_explicit", normalized["needs"][0].get("evidence_binding_mode"))
        self.assertEqual("strong_explicit", normalized["solutions"][0].get("evidence_binding_mode"))
        self.assertEqual("strong_explicit", normalized["risks"][0].get("evidence_binding_mode"))
        self.assertEqual("strong_explicit", normalized["actions"][0].get("evidence_binding_mode"))

    def test_evaluate_answer_depth_does_not_penalize_single_select_answer_as_single_selection(self):
        result = self.server.evaluate_answer_depth(
            question="您当前最关注的场景是哪一个？",
            answer="交易支付环节的风控体验",
            dimension="customer_needs",
            options=["交易支付环节的风控体验", "售后服务", "营销活动"],
            is_follow_up=False,
            multi_select=False,
        )
        self.assertNotIn("single_selection", result.get("signals", []))
        self.assertNotIn("option_only", result.get("signals", []))

    def test_evaluate_answer_depth_pick_only_mode_does_not_require_extra_rationale(self):
        result = self.server.evaluate_answer_depth(
            question="当前最优先的目标是什么？",
            answer="提升审批效率",
            dimension="customer_needs",
            options=["提升审批效率", "降低成本", "减少风险"],
            is_follow_up=False,
            multi_select=False,
            answer_mode="pick_only",
            requires_rationale=False,
            evidence_intent="low",
        )
        self.assertNotIn("missing_rationale", result.get("signals", []))
        self.assertNotIn("option_only", result.get("signals", []))

    def test_evaluate_answer_depth_pick_with_reason_mode_accepts_rich_option_answer(self):
        result = self.server.evaluate_answer_depth(
            question="当前最优先的目标是什么？",
            answer="审批链条长导致整体处理慢",
            dimension="customer_needs",
            options=["审批链条长导致整体处理慢", "降低成本", "减少风险"],
            is_follow_up=False,
            multi_select=False,
            answer_mode="pick_with_reason",
            requires_rationale=True,
            evidence_intent="high",
        )
        self.assertIn("rich_option_answer", result.get("signals", []))
        self.assertNotIn("missing_rationale", result.get("signals", []))

    def test_build_report_evidence_pack_does_not_mark_informative_option_answer_as_unknown(self):
        quality_eval = self.server.evaluate_answer_quality(
            eval_result=self.server.evaluate_answer_depth(
                question="您当前最关注的场景是哪一个？",
                answer="误拦截/拒付率高的归因（挖掘被误伤用户的心理特征）",
                dimension="customer_needs",
                options=[
                    "误拦截/拒付率高的归因（挖掘被误伤用户的心理特征）",
                    "售后服务体验",
                    "营销转化问题",
                ],
                is_follow_up=False,
                multi_select=False,
            ),
            answer="误拦截/拒付率高的归因（挖掘被误伤用户的心理特征）",
            is_follow_up=False,
            follow_up_round=0,
        )
        session = {
            "topic": "测试",
            "scenario_config": {"report": {"type": "standard"}},
            "dimensions": {"customer_needs": {"coverage": 100}},
            "interview_log": [{
                "dimension": "customer_needs",
                "question": "您当前最关注的场景是哪一个？",
                "answer": "误拦截/拒付率高的归因（挖掘被误伤用户的心理特征）",
                "options": [
                    "误拦截/拒付率高的归因（挖掘被误伤用户的心理特征）",
                    "售后服务体验",
                    "营销转化问题",
                ],
                "multi_select": False,
                "is_follow_up": False,
                "follow_up_signals": quality_eval.get("quality_signals", []),
                "quality_score": quality_eval.get("quality_score", 0),
                "quality_signals": quality_eval.get("quality_signals", []),
                "hard_triggered": quality_eval.get("hard_triggered", False),
                "follow_up_round": 0,
            }],
        }
        evidence_pack = self.server.build_report_evidence_pack(session)
        self.assertEqual([], evidence_pack.get("unknowns", []))
        self.assertEqual("rich_option", evidence_pack["facts"][0].get("answer_evidence_class"))

    def test_backfill_session_interview_log_evidence_annotations_enriches_legacy_logs(self):
        session = {
            "topic": "历史会话",
            "scenario_config": {"report": {"type": "standard"}},
            "interview_log": [
                {
                    "question": "当前最优先的阻塞是什么？",
                    "answer": "审批链条长导致整体处理慢",
                    "dimension": "customer_needs",
                    "options": ["审批链条长导致整体处理慢", "成本高", "资源不足"],
                    "multi_select": False,
                    "is_follow_up": False,
                    "follow_up_round": 0,
                },
                {
                    "question": "您提到审批慢，主要卡在哪个角色？",
                    "answer": "风控复核环节",
                    "dimension": "customer_needs",
                    "options": ["风控复核环节", "客服回访环节", "商家补料环节"],
                    "multi_select": False,
                    "is_follow_up": True,
                    "follow_up_round": 1,
                },
            ],
        }

        result = self.server.backfill_session_interview_log_evidence_annotations(session)

        self.assertTrue(result.get("changed"))
        self.assertEqual(2, result.get("logs_updated"))
        first_log, second_log = session["interview_log"]
        self.assertEqual("pick_with_reason", first_log.get("answer_mode"))
        self.assertEqual("medium", first_log.get("evidence_intent"))
        self.assertEqual("rich_option", first_log.get("answer_evidence_class"))
        self.assertEqual("pick_with_reason", second_log.get("answer_mode"))
        self.assertEqual("high", second_log.get("evidence_intent"))
        self.assertIn("answer_evidence_class", result.get("field_updates", {}))

    def test_build_report_evidence_pack_uses_quality_adjusted_coverage_and_raw_quality_average(self):
        session = {
            "topic": "测试",
            "scenario_config": {"report": {"type": "standard"}},
            "dimensions": {
                "customer_needs": {"coverage": 100},
                "business_flow": {"coverage": 100},
            },
            "interview_log": [
                {
                    "dimension": "customer_needs",
                    "question": "Q1",
                    "answer": "A1",
                    "is_follow_up": False,
                    "follow_up_round": 0,
                    "quality_score": 1.0,
                    "quality_signals": [],
                    "follow_up_signals": [],
                    "hard_triggered": False,
                    "answer_mode": "pick_only",
                    "requires_rationale": False,
                    "evidence_intent": "low",
                },
                {
                    "dimension": "business_flow",
                    "question": "Q2",
                    "answer": "A2",
                    "is_follow_up": False,
                    "follow_up_round": 0,
                    "quality_score": 0.0,
                    "quality_signals": ["too_short"],
                    "follow_up_signals": ["too_short"],
                    "hard_triggered": False,
                    "answer_mode": "pick_with_reason",
                    "requires_rationale": True,
                    "evidence_intent": "high",
                },
            ],
        }

        original_get_dimension_info = self.server.get_dimension_info_for_session
        original_missing_aspects = self.server.get_dimension_missing_aspects
        self.addCleanup(setattr, self.server, "get_dimension_info_for_session", original_get_dimension_info)
        self.addCleanup(setattr, self.server, "get_dimension_missing_aspects", original_missing_aspects)
        self.server.get_dimension_info_for_session = lambda _session: {
            "customer_needs": {"name": "客户需求", "key_aspects": ["目标", "场景"]},
            "business_flow": {"name": "业务流程", "key_aspects": ["角色分工", "流程节点"]},
        }
        self.server.get_dimension_missing_aspects = lambda _session, dim_key: ["角色分工"] if dim_key == "business_flow" else []

        evidence_pack = self.server.build_report_evidence_pack(session)

        self.assertLess(evidence_pack["overall_coverage"], 1.0)
        self.assertEqual(100, evidence_pack["dimension_coverage"]["customer_needs"]["coverage_percent"])
        self.assertEqual(50, evidence_pack["dimension_coverage"]["business_flow"]["coverage_percent"])
        self.assertAlmostEqual(0.4, evidence_pack["quality_snapshot"]["average_quality_score"], places=3)
        self.assertAlmostEqual(0.4, evidence_pack["quality_snapshot"]["raw_average_quality_score"], places=3)
        self.assertAlmostEqual(0.4, evidence_pack["quality_snapshot"]["positive_only_average_quality_score"], places=3)
        self.assertEqual(1, evidence_pack["quality_snapshot"]["answer_mode_distribution"]["pick_only"])
        self.assertEqual(1, evidence_pack["quality_snapshot"]["answer_mode_distribution"]["pick_with_reason"])

    def test_compute_report_quality_meta_v3_assigns_mid_weight_to_rich_option_evidence(self):
        draft = {
            "overview": "概述",
            "needs": [{"name": "需求A", "priority": "P1", "description": "描述", "evidence_refs": ["Q1"]}],
            "analysis": {
                "customer_needs": "A",
                "business_flow": "B",
                "tech_constraints": "C",
                "project_constraints": "D",
            },
            "visualizations": {},
            "solutions": [
                {
                    "title": "方案A",
                    "description": "描述",
                    "owner": "张三",
                    "timeline": "2周",
                    "metric": "完成率>=90%",
                    "evidence_refs": ["Q2"],
                }
            ],
            "risks": [],
            "actions": [],
            "open_questions": [],
            "evidence_index": [],
        }
        evidence_pack = {
            "facts": [
                {"q_id": "Q1", "answer_evidence_class": "explicit"},
                {"q_id": "Q2", "answer_evidence_class": "rich_option"},
            ],
            "contradictions": [],
            "unknowns": [],
            "blindspots": [],
            "quality_snapshot": {"average_quality_score": 0.68},
        }

        meta = self.server.compute_report_quality_meta_v3(draft, evidence_pack, [])
        self.assertEqual(1, meta.get("rich_option_count"))
        self.assertAlmostEqual(0.89, meta.get("evidence_coverage"), places=2)
        self.assertEqual(0, meta.get("weak_binding_count"))

    def test_build_quality_gate_issues_v3_relaxes_expression_threshold_when_evidence_is_noisy(self):
        quality_meta = {
            "runtime_profile": "balanced",
            "evidence_coverage": 0.95,
            "consistency": 0.92,
            "actionability": 0.70,
            "expression_structure": 0.62,
            "table_readiness": 0.6,
            "action_acceptance": 0.58,
            "milestone_coverage": 0.55,
            "weak_binding_ratio": 0.20,
            "template_minimums": {"needs": 1, "solutions": 1, "risks": 1, "actions": 2, "open_questions": 1},
            "list_counts": {"needs": 1, "solutions": 1, "risks": 1, "actions": 2, "open_questions": 2},
            "evidence_context": {
                "facts_count": 24,
                "unknown_count": 20,
                "unknown_ratio": 0.83,
                "average_quality_score": 0.21,
            },
        }
        issues = self.server.build_quality_gate_issues_v3(quality_meta)
        issue_types = {item.get("type") for item in issues if isinstance(item, dict)}
        self.assertNotIn("quality_gate_actionability", issue_types)
        self.assertNotIn("quality_gate_table", issue_types)

    def test_build_quality_gate_issues_v3_relaxes_evidence_threshold_when_evidence_is_sparse(self):
        quality_meta = {
            "runtime_profile": "balanced",
            "evidence_coverage": 0.85,
            "consistency": 0.92,
            "actionability": 0.72,
            "expression_structure": 0.70,
            "table_readiness": 0.66,
            "action_acceptance": 0.64,
            "milestone_coverage": 0.50,
            "weak_binding_ratio": 0.20,
            "template_minimums": {"needs": 1, "solutions": 1, "risks": 1, "actions": 2, "open_questions": 1},
            "list_counts": {"needs": 1, "solutions": 1, "risks": 1, "actions": 2, "open_questions": 2},
            "evidence_context": {
                "facts_count": 34,
                "unknown_count": 29,
                "unknown_ratio": 29 / 34,
                "average_quality_score": 0.287,
            },
        }
        issues = self.server.build_quality_gate_issues_v3(quality_meta)
        issue_types = {item.get("type") for item in issues if isinstance(item, dict)}
        self.assertNotIn("quality_gate_evidence", issue_types)

    def test_build_quality_gate_issues_v3_relaxes_evidence_threshold_for_high_rich_option_ratio(self):
        quality_meta = {
            "runtime_profile": "balanced",
            "evidence_coverage": 0.78,
            "consistency": 0.92,
            "actionability": 0.86,
            "expression_structure": 0.82,
            "table_readiness": 0.80,
            "action_acceptance": 0.76,
            "milestone_coverage": 0.50,
            "weak_binding_ratio": 0.08,
            "claim_total": 20,
            "rich_option_count": 12,
            "rich_option_ratio": 0.60,
            "template_minimums": {"needs": 1, "solutions": 1, "risks": 1, "actions": 2, "open_questions": 1},
            "list_counts": {"needs": 2, "solutions": 2, "risks": 1, "actions": 3, "open_questions": 1},
            "evidence_context": {
                "facts_count": 31,
                "unknown_count": 2,
                "unknown_ratio": 2 / 31,
                "average_quality_score": 0.56,
            },
        }
        issues = self.server.build_quality_gate_issues_v3(quality_meta)
        issue_types = {item.get("type") for item in issues if isinstance(item, dict)}
        self.assertNotIn("quality_gate_evidence", issue_types)

    def test_build_quality_gate_issues_v3_relaxes_evidence_threshold_further_for_extreme_rich_option_ratio(self):
        quality_meta = {
            "runtime_profile": "balanced",
            "evidence_coverage": 0.73,
            "consistency": 0.92,
            "actionability": 0.86,
            "expression_structure": 0.82,
            "table_readiness": 0.80,
            "action_acceptance": 0.76,
            "milestone_coverage": 0.50,
            "weak_binding_ratio": 0.06,
            "claim_total": 20,
            "rich_option_count": 16,
            "rich_option_ratio": 0.80,
            "template_minimums": {"needs": 1, "solutions": 1, "risks": 1, "actions": 2, "open_questions": 1},
            "list_counts": {"needs": 2, "solutions": 2, "risks": 1, "actions": 3, "open_questions": 1},
            "evidence_context": {
                "facts_count": 31,
                "unknown_count": 2,
                "unknown_ratio": 0.06,
                "average_quality_score": 0.57,
            },
        }
        issues = self.server.build_quality_gate_issues_v3(quality_meta)
        issue_types = {item.get("type") for item in issues if isinstance(item, dict)}
        self.assertNotIn("quality_gate_evidence", issue_types)

    def test_build_quality_gate_issues_v3_relaxes_evidence_threshold_for_pending_follow_up_heavy_session(self):
        quality_meta = {
            "runtime_profile": "balanced",
            "evidence_coverage": 0.524,
            "consistency": 0.92,
            "actionability": 0.86,
            "expression_structure": 0.82,
            "table_readiness": 0.80,
            "action_acceptance": 0.76,
            "milestone_coverage": 0.50,
            "weak_binding_ratio": 0.05,
            "claim_total": 21,
            "rich_option_count": 8,
            "rich_option_ratio": 8 / 21,
            "pending_follow_up_count": 8,
            "pending_follow_up_ratio": 8 / 21,
            "template_minimums": {"needs": 1, "solutions": 1, "risks": 1, "actions": 2, "open_questions": 1},
            "list_counts": {"needs": 2, "solutions": 2, "risks": 1, "actions": 3, "open_questions": 4},
            "evidence_context": {
                "facts_count": 34,
                "unknown_count": 12,
                "blindspots_count": 13,
                "unknown_ratio": 12 / 34,
                "average_quality_score": 0.46,
            },
        }
        issues = self.server.build_quality_gate_issues_v3(quality_meta)
        issue_types = {item.get("type") for item in issues if isinstance(item, dict)}
        self.assertNotIn("quality_gate_evidence", issue_types)

    def test_build_quality_gate_issues_v3_uses_field_specific_weak_binding_limits(self):
        quality_meta = {
            "runtime_profile": "balanced",
            "evidence_coverage": 0.95,
            "consistency": 0.92,
            "actionability": 0.86,
            "expression_structure": 0.82,
            "table_readiness": 0.80,
            "action_acceptance": 0.76,
            "milestone_coverage": 0.66,
            "weak_binding_ratio": 0.20,
            "weak_binding_ratio_by_field": {
                "actions": 0.20,
                "solutions": 0.25,
                "risks": 0.78,
            },
            "template_minimums": {"needs": 1, "solutions": 1, "risks": 1, "actions": 2, "open_questions": 1},
            "list_counts": {"needs": 1, "solutions": 1, "risks": 1, "actions": 2, "open_questions": 1},
            "evidence_context": {
                "facts_count": 20,
                "unknown_count": 4,
                "unknown_ratio": 0.2,
                "average_quality_score": 0.62,
            },
        }

        issues = self.server.build_quality_gate_issues_v3(quality_meta)
        weak_binding_issues = [item for item in issues if item.get("type") == "quality_gate_weak_binding"]
        self.assertEqual(1, len(weak_binding_issues))
        self.assertEqual("risks", weak_binding_issues[0]["target"])


    def test_attempt_salvage_v3_review_failure_supports_quality_gate_failure_reason(self):
        backups = {
            "validate_report_draft_v3": self.server.validate_report_draft_v3,
            "apply_deterministic_report_repairs_v3": self.server.apply_deterministic_report_repairs_v3,
            "compute_report_quality_meta_v3": self.server.compute_report_quality_meta_v3,
            "build_quality_gate_issues_v3": self.server.build_quality_gate_issues_v3,
            "render_report_from_draft_v3": self.server.render_report_from_draft_v3,
        }
        old_toggle = self.server.REPORT_V3_SALVAGE_ON_QUALITY_GATE_FAILURE
        try:
            self.server.REPORT_V3_SALVAGE_ON_QUALITY_GATE_FAILURE = True
            self.server.validate_report_draft_v3 = lambda draft, _evidence: (draft, [])
            self.server.apply_deterministic_report_repairs_v3 = lambda draft, _evidence, _issues, runtime_profile="": {
                "draft": draft,
                "changed": False,
                "notes": [],
            }
            self.server.compute_report_quality_meta_v3 = lambda _draft, _evidence, _issues: {
                "overall": 0.88,
                "runtime_profile": "quality",
            }
            self.server.build_quality_gate_issues_v3 = lambda _meta: []
            self.server.render_report_from_draft_v3 = lambda _session, _draft, _meta: "# 挽救成功"

            failed_payload = {
                "reason": "review_not_passed_or_quality_gate_failed",
                "profile": "quality",
                "phase_lanes": {"draft": "report", "review": "report"},
                "draft_snapshot": {"overview": "ok", "needs": [], "analysis": {}},
                "evidence_pack": {"facts": [{"q_id": "Q1", "dimension": "customer_needs"}]},
                "review_issues": [{"type": "no_evidence", "target": "risks[0]"}],
            }
            outcome = self.server.attempt_salvage_v3_review_failure({"topic": "测试"}, failed_payload)
            self.assertTrue(outcome.get("attempted"))
            self.assertTrue(outcome.get("success"))
            self.assertEqual(outcome.get("report_content"), "# 挽救成功")
        finally:
            self.server.REPORT_V3_SALVAGE_ON_QUALITY_GATE_FAILURE = old_toggle
            for name, fn in backups.items():
                setattr(self.server, name, fn)

    def test_select_slimmed_facts_for_prompt_prioritizes_signal_and_dedup(self):
        keys = [
            "REPORT_V3_EVIDENCE_SLIM_ENABLED",
            "REPORT_V3_EVIDENCE_DEDUP_ENABLED",
            "REPORT_V3_EVIDENCE_DIM_QUOTA",
            "REPORT_V3_EVIDENCE_MIN_QUALITY",
            "REPORT_V3_EVIDENCE_KEEP_HARD_TRIGGERED",
        ]
        backup = {key: getattr(self.server, key) for key in keys}
        try:
            self.server.REPORT_V3_EVIDENCE_SLIM_ENABLED = True
            self.server.REPORT_V3_EVIDENCE_DEDUP_ENABLED = True
            self.server.REPORT_V3_EVIDENCE_DIM_QUOTA = 2
            self.server.REPORT_V3_EVIDENCE_MIN_QUALITY = 0.45
            self.server.REPORT_V3_EVIDENCE_KEEP_HARD_TRIGGERED = True

            evidence_pack = {
                "facts": [
                    {"q_id": "Q1", "dimension": "customer_needs", "question": "预算多少", "answer": "100万", "quality_score": 0.92},
                    {"q_id": "Q2", "dimension": "customer_needs", "question": "预算多少", "answer": "100万", "quality_score": 0.51},
                    {"q_id": "Q3", "dimension": "business_flow", "question": "上线窗口", "answer": "暂不确定", "quality_score": 0.15, "hard_triggered": True},
                    {"q_id": "Q4", "dimension": "tech_constraints", "question": "是否支持私有化", "answer": "必须支持", "quality_score": 0.31},
                    {"q_id": "Q5", "dimension": "tech_constraints", "question": "并发规模", "answer": "不清楚", "quality_score": 0.1},
                ],
                "contradictions": [{"evidence_refs": ["Q4"]}],
                "unknowns": [{"q_id": "Q3"}],
            }

            selected = self.server.select_slimmed_facts_for_prompt(evidence_pack, facts_limit=3)
            selected_ids = [item.get("q_id") for item in selected]

            self.assertLessEqual(len(selected), 3)
            self.assertIn("Q3", selected_ids)  # hard trigger 强保留
            self.assertIn("Q4", selected_ids)  # 冲突证据强保留
            self.assertTrue(("Q1" in selected_ids) ^ ("Q2" in selected_ids))  # 去重后仅保留一条
        finally:
            for key, value in backup.items():
                setattr(self.server, key, value)

    def test_metrics_stage_profiles_group_by_stage_lane_model(self):
        self.server.metrics_collector.reset()

        self.server.metrics_collector.record_api_call(
            call_type="report_v3_draft",
            prompt_length=1200,
            response_time=1.0,
            success=True,
            timeout=False,
            lane="question",
            model="glm-5",
            stage="draft_gen",
        )
        self.server.metrics_collector.record_api_call(
            call_type="report_v3_draft_retry_2",
            prompt_length=1100,
            response_time=2.0,
            success=False,
            timeout=True,
            error_msg="timeout",
            lane="question",
            model="glm-5",
            stage="draft_gen",
        )
        self.server.record_pipeline_stage_metric(
            stage="review_parse",
            success=True,
            elapsed_seconds=0.3,
            lane="report",
            model="gpt-5",
            error_msg="",
        )

        stats = self.server.metrics_collector.get_statistics(last_n=20)
        self.assertEqual(stats.get("total_calls"), 2)  # pipeline_stage 不应污染 API 总量
        self.assertIn("stage_profiles", stats)
        stage_profiles = stats.get("stage_profiles", {})
        self.assertGreaterEqual(stage_profiles.get("sample_count", 0), 3)

        groups = stage_profiles.get("groups", [])
        target_group = None
        for item in groups:
            if (
                item.get("stage") == "draft_gen"
                and item.get("lane") == "question"
                and item.get("model") == "glm-5"
            ):
                target_group = item
                break
        self.assertIsNotNone(target_group)
        self.assertEqual(target_group.get("count"), 2)
        self.assertIn("review_parse", stage_profiles.get("stages", {}))

    def test_gateway_circuit_breaker_opens_and_resets_after_success(self):
        keys = [
            "GATEWAY_CIRCUIT_BREAKER_ENABLED",
            "GATEWAY_CIRCUIT_FAIL_THRESHOLD",
            "GATEWAY_CIRCUIT_COOLDOWN_SECONDS",
            "GATEWAY_CIRCUIT_FAILURE_WINDOW_SECONDS",
        ]
        backup = {key: getattr(self.server, key) for key in keys}

        try:
            self.server.GATEWAY_CIRCUIT_BREAKER_ENABLED = True
            self.server.GATEWAY_CIRCUIT_FAIL_THRESHOLD = 2
            self.server.GATEWAY_CIRCUIT_COOLDOWN_SECONDS = 120.0
            self.server.GATEWAY_CIRCUIT_FAILURE_WINDOW_SECONDS = 180.0
            self.server.reset_gateway_circuit_state()

            first = self.server.record_gateway_lane_failure("report", "http_5xx")
            second = self.server.record_gateway_lane_failure("report", "timeout")
            self.assertTrue(first.get("counted"))
            self.assertTrue(second.get("circuit_opened"))
            self.assertTrue(self.server.is_gateway_lane_in_cooldown("report"))

            self.server.record_gateway_lane_success("report")
            snapshot = self.server.get_gateway_circuit_snapshot("report")
            self.assertEqual(snapshot.get("fail_count"), 0)
            self.assertEqual(snapshot.get("cooldown_remaining_seconds"), 0.0)
            self.assertFalse(self.server.is_gateway_lane_in_cooldown("report"))
        finally:
            self.server.reset_gateway_circuit_state()
            for key, value in backup.items():
                setattr(self.server, key, value)

    def test_report_phase_success_clears_legacy_report_cooldown(self):
        keys = [
            "GATEWAY_CIRCUIT_BREAKER_ENABLED",
            "GATEWAY_CIRCUIT_FAIL_THRESHOLD",
            "GATEWAY_CIRCUIT_COOLDOWN_SECONDS",
            "GATEWAY_CIRCUIT_FAILURE_WINDOW_SECONDS",
        ]
        backup = {key: getattr(self.server, key) for key in keys}

        try:
            self.server.GATEWAY_CIRCUIT_BREAKER_ENABLED = True
            self.server.GATEWAY_CIRCUIT_FAIL_THRESHOLD = 2
            self.server.GATEWAY_CIRCUIT_COOLDOWN_SECONDS = 120.0
            self.server.GATEWAY_CIRCUIT_FAILURE_WINDOW_SECONDS = 180.0
            self.server.reset_gateway_circuit_state()

            self.server.record_gateway_lane_failure("report", "http_5xx")
            self.server.record_gateway_lane_failure("report", "timeout")
            self.assertTrue(self.server.is_gateway_lane_in_cooldown("report_draft"))

            self.server.record_gateway_lane_success("report_draft")
            self.assertFalse(self.server.is_gateway_lane_in_cooldown("report"))
            self.assertFalse(self.server.is_gateway_lane_in_cooldown("report_draft"))
        finally:
            self.server.reset_gateway_circuit_state()
            for key, value in backup.items():
                setattr(self.server, key, value)

    def test_resolve_ai_client_with_lane_skips_cooled_report_lane(self):
        keys = [
            "GATEWAY_CIRCUIT_BREAKER_ENABLED",
            "GATEWAY_CIRCUIT_FAIL_THRESHOLD",
            "GATEWAY_CIRCUIT_COOLDOWN_SECONDS",
            "GATEWAY_CIRCUIT_FAILURE_WINDOW_SECONDS",
            "question_ai_client",
            "report_ai_client",
            "report_draft_ai_client",
            "report_review_ai_client",
            "summary_ai_client",
            "search_decision_ai_client",
        ]
        backup = {key: getattr(self.server, key) for key in keys}

        try:
            self.server.GATEWAY_CIRCUIT_BREAKER_ENABLED = True
            self.server.GATEWAY_CIRCUIT_FAIL_THRESHOLD = 2
            self.server.GATEWAY_CIRCUIT_COOLDOWN_SECONDS = 120.0
            self.server.GATEWAY_CIRCUIT_FAILURE_WINDOW_SECONDS = 180.0
            self.server.reset_gateway_circuit_state()

            question_client = object()
            draft_client = object()
            review_client = object()
            self.server.question_ai_client = question_client
            self.server.report_ai_client = review_client
            self.server.report_draft_ai_client = draft_client
            self.server.report_review_ai_client = review_client
            self.server.summary_ai_client = None
            self.server.search_decision_ai_client = None

            self.server.record_gateway_lane_failure("report", "http_5xx")
            self.server.record_gateway_lane_failure("report", "timeout")

            selected_client, selected_lane, meta = self.server.resolve_ai_client_with_lane(
                call_type="report_v3_draft",
                preferred_lane="report",
            )
            self.assertIs(selected_client, question_client)
            self.assertEqual(selected_lane, "question")
            self.assertIn("report", meta.get("skipped_open_lanes", []))
        finally:
            self.server.reset_gateway_circuit_state()
            for key, value in backup.items():
                setattr(self.server, key, value)

    def test_resolve_ai_client_with_lane_prefers_report_phase_clients(self):
        keys = [
            "question_ai_client",
            "report_ai_client",
            "report_draft_ai_client",
            "report_review_ai_client",
            "summary_ai_client",
            "search_decision_ai_client",
        ]
        backup = {key: getattr(self.server, key) for key in keys}

        try:
            question_client = object()
            draft_client = object()
            review_client = object()
            self.server.question_ai_client = question_client
            self.server.report_ai_client = review_client
            self.server.report_draft_ai_client = draft_client
            self.server.report_review_ai_client = review_client
            self.server.summary_ai_client = None
            self.server.search_decision_ai_client = None

            selected_client, selected_lane, _meta = self.server.resolve_ai_client_with_lane(
                call_type="report_v3_draft",
                preferred_lane="report",
            )
            self.assertIs(selected_client, draft_client)
            self.assertEqual(selected_lane, "report_draft")

            selected_client, selected_lane, _meta = self.server.resolve_ai_client_with_lane(
                call_type="report_v3_review_round_1",
                preferred_lane="report",
            )
            self.assertIs(selected_client, review_client)
            self.assertEqual(selected_lane, "report_review")

            selected_client, selected_lane, _meta = self.server.resolve_ai_client_with_lane(
                call_type="report_v3_review_parse_repair_round_1",
                preferred_lane="report",
            )
            self.assertIs(selected_client, review_client)
            self.assertEqual(selected_lane, "report_review")
        finally:
            for key, value in backup.items():
                setattr(self.server, key, value)

    def test_call_claude_switches_to_question_lane_when_report_cooled(self):
        class _DummyMessages:
            def __init__(self, text: str):
                self.text = text
                self.calls = 0

            def create(self, **kwargs):
                self.calls += 1
                return types.SimpleNamespace(content=[{"type": "text", "text": self.text}])

        class _DummyClient:
            def __init__(self, text: str):
                self.messages = _DummyMessages(text=text)

        keys = [
            "GATEWAY_CIRCUIT_BREAKER_ENABLED",
            "GATEWAY_CIRCUIT_FAIL_THRESHOLD",
            "GATEWAY_CIRCUIT_COOLDOWN_SECONDS",
            "GATEWAY_CIRCUIT_FAILURE_WINDOW_SECONDS",
            "question_ai_client",
            "report_ai_client",
            "report_draft_ai_client",
            "report_review_ai_client",
            "summary_ai_client",
            "search_decision_ai_client",
        ]
        backup = {key: getattr(self.server, key) for key in keys}

        try:
            self.server.GATEWAY_CIRCUIT_BREAKER_ENABLED = True
            self.server.GATEWAY_CIRCUIT_FAIL_THRESHOLD = 2
            self.server.GATEWAY_CIRCUIT_COOLDOWN_SECONDS = 120.0
            self.server.GATEWAY_CIRCUIT_FAILURE_WINDOW_SECONDS = 180.0
            self.server.reset_gateway_circuit_state()

            question_client = _DummyClient("question-lane-ok")
            draft_client = _DummyClient("draft-lane-ok")
            review_client = _DummyClient("review-lane-ok")
            self.server.question_ai_client = question_client
            self.server.report_ai_client = review_client
            self.server.report_draft_ai_client = draft_client
            self.server.report_review_ai_client = review_client
            self.server.summary_ai_client = None
            self.server.search_decision_ai_client = None

            self.server.record_gateway_lane_failure("report", "http_5xx")
            self.server.record_gateway_lane_failure("report", "timeout")
            self.assertTrue(self.server.is_gateway_lane_in_cooldown("report"))

            result = self.server.call_claude(
                "请生成报告摘要",
                max_tokens=256,
                call_type="report_v3_draft",
                preferred_lane="report",
                timeout=10.0,
            )
            self.assertEqual(result, "question-lane-ok")
            self.assertEqual(draft_client.messages.calls, 0)
            self.assertEqual(review_client.messages.calls, 0)
            self.assertEqual(question_client.messages.calls, 1)
        finally:
            self.server.reset_gateway_circuit_state()
            for key, value in backup.items():
                setattr(self.server, key, value)

    def test_call_claude_return_meta_marks_empty_text_response(self):
        class _DummyMessages:
            def create(self, **kwargs):
                return types.SimpleNamespace(content=[{"type": "text", "text": "   "}])

        class _DummyClient:
            def __init__(self):
                self.messages = _DummyMessages()

        keys = [
            "question_ai_client",
            "report_ai_client",
            "summary_ai_client",
            "search_decision_ai_client",
        ]
        backup = {key: getattr(self.server, key) for key in keys}

        try:
            self.server.question_ai_client = _DummyClient()
            self.server.report_ai_client = None
            self.server.summary_ai_client = None
            self.server.search_decision_ai_client = None

            result, meta = self.server.call_claude(
                "请生成问题",
                max_tokens=64,
                call_type="question_fast",
                preferred_lane="question",
                timeout=12.0,
                return_meta=True,
            )

            self.assertIsNone(result)
            self.assertEqual(meta.get("selected_lane"), "question")
            self.assertEqual(meta.get("failure_reason"), "empty_text")
            self.assertFalse(meta.get("success"))
            self.assertEqual(meta.get("timeout_seconds"), 12.0)
            self.assertEqual(meta.get("max_tokens"), 64)
        finally:
            for key, value in backup.items():
                setattr(self.server, key, value)

    def test_format_question_tier_attempts_for_log_uses_detailed_reason_labels(self):
        detail = self.server._format_question_tier_attempts_for_log({
            "attempts": [
                {
                    "lane": "question",
                    "failure_reason": "timeout",
                    "timeout_occurred": True,
                    "timeout_seconds": 12.0,
                    "queue_wait_ms": 523.4,
                },
                {
                    "lane": "summary",
                    "failure_reason": "empty_text",
                },
            ]
        })

        self.assertIn("question:超时", detail)
        self.assertIn("timeout>12s", detail)
        self.assertIn("queue=523ms", detail)
        self.assertIn("summary:空文本", detail)

    def test_ensure_flowchart_semantic_styles_adds_multicolor_classdefs(self):
        raw = (
            "flowchart TD\n"
            "    A[开始] --> B{判断}\n"
            "    B -->|通过| C[核心流程]\n"
            "    B -->|阻塞| D[风险处理]\n"
        )
        styled = self.server.ensure_flowchart_semantic_styles(raw)

        self.assertIn("classDef dvCore", styled)
        self.assertIn("classDef dvDecision", styled)
        self.assertIn("classDef dvRisk", styled)
        self.assertIn("classDef dvSupport", styled)
        self.assertIn("class ", styled)

    def test_ensure_flowchart_semantic_styles_keeps_existing_classdef(self):
        raw = (
            "flowchart TD\n"
            "    A[开始] --> B[结束]\n"
            "    classDef custom fill:#DBEAFE,stroke:#2563EB,color:#1E3A8A\n"
            "    class A,B custom\n"
        )
        styled = self.server.ensure_flowchart_semantic_styles(raw)
        self.assertEqual(styled, raw.strip())

    def test_render_report_from_draft_v3_uses_data_driven_mermaid_and_table_layout(self):
        old_flag = self.server.REPORT_V3_RENDER_MERMAID_FROM_DATA
        try:
            self.server.REPORT_V3_RENDER_MERMAID_FROM_DATA = True
            draft = {
                "overview": "这是一段用于验证渲染稳定性的概述。",
                "needs": [
                    {
                        "name": "统一任务追踪视图",
                        "priority": "P0",
                        "description": "希望统一查看全部任务状态",
                        "evidence_refs": ["Q1", "Q2"],
                    }
                ],
                "analysis": {
                    "customer_needs": "客户希望提升跨团队可见性。",
                    "business_flow": "当前流程跨部门协同效率较低。",
                    "tech_constraints": "需要兼容既有 SSO 和审计链路。",
                    "project_constraints": "预计两个月内完成首期上线。",
                },
                "visualizations": {
                    "business_flow_mermaid": "flowchart TD\nX[模型幻觉图]",
                    "architecture_mermaid": "flowchart TD\nY[模型幻觉架构]",
                },
                "solutions": [
                    {
                        "title": "建设统一工作台",
                        "description": "先聚合核心任务，再分阶段扩展。",
                        "owner": "产品经理",
                        "timeline": "1个月内",
                        "metric": "核心任务覆盖率>=90%",
                        "evidence_refs": ["Q3"],
                    }
                ],
                "risks": [
                    {
                        "risk": "跨系统数据口径不一致",
                        "impact": "影响报表可信度",
                        "mitigation": "建立统一口径映射与校验规则",
                        "evidence_refs": ["Q4"],
                    }
                ],
                "actions": [
                    {
                        "action": "完成首批系统接入",
                        "owner": "研发负责人",
                        "timeline": "2周内",
                        "metric": "接入系统数量>=3",
                        "evidence_refs": ["Q5"],
                    }
                ],
                "open_questions": [
                    {
                        "question": "审计链路是否需要额外留痕字段？",
                        "reason": "合规条款尚未最终确认",
                        "impact": "影响上线节奏",
                        "suggested_follow_up": "与合规团队确认字段清单",
                        "evidence_refs": ["Q6"],
                    }
                ],
                "evidence_index": [],
            }

            report = self.server.render_report_from_draft_v3({"topic": "渲染稳定性测试"}, draft, {})

            self.assertIn("### 5.1 建议清单（表格）", report)
            self.assertIn("| 编号 | 方案建议 | 说明 | Owner | 时间计划 | 验收指标 | 证据 |", report)
            self.assertIn("访谈输入", report)
            self.assertNotIn("模型幻觉图", report)
            self.assertNotIn("模型幻觉架构", report)
        finally:
            self.server.REPORT_V3_RENDER_MERMAID_FROM_DATA = old_flag

    def test_render_report_from_draft_v3_dispatches_assessment_and_custom_template(self):
        backup_assessment = self.server.render_report_from_draft_assessment_v1
        backup_custom = self.server.render_report_from_draft_custom_v1
        try:
            self.server.render_report_from_draft_assessment_v1 = lambda *_args, **_kwargs: "# assessment dispatch"
            self.server.render_report_from_draft_custom_v1 = lambda *_args, **_kwargs: "# custom dispatch"

            assessment = self.server.render_report_from_draft_v3(
                {
                    "scenario_config": {
                        "report": {"type": "assessment", "template": "assessment"},
                    }
                },
                {},
                {},
            )
            self.assertEqual(assessment, "# assessment dispatch")

            custom = self.server.render_report_from_draft_v3(
                {
                    "scenario_config": {
                        "report": {
                            "type": "standard",
                            "template": "custom_v1",
                            "schema": {
                                "sections": [
                                    {
                                        "section_id": "summary",
                                        "title": "执行摘要",
                                        "component": "paragraph",
                                        "source": "overview",
                                    }
                                ]
                            },
                        },
                    }
                },
                {},
                {},
            )
            self.assertEqual(custom, "# custom dispatch")
        finally:
            self.server.render_report_from_draft_assessment_v1 = backup_assessment
            self.server.render_report_from_draft_custom_v1 = backup_custom

    def test_build_report_prompt_supports_custom_template_blueprint(self):
        session = {
            "topic": "自定义回退报告测试",
            "description": "验证 legacy prompt 在 custom_v1 下按蓝图输出",
            "scenario_config": {
                "dimensions": [
                    {
                        "id": "customer_needs",
                        "name": "客户需求",
                        "key_aspects": ["目标", "动机"],
                    }
                ],
                "report": {
                    "type": "standard",
                    "template": "custom_v1",
                    "schema": {
                        "sections": [
                            {
                                "section_id": "summary",
                                "title": "执行摘要",
                                "component": "paragraph",
                                "source": "overview",
                                "required": True,
                            },
                            {
                                "section_id": "actions",
                                "title": "行动计划",
                                "component": "table",
                                "source": "actions",
                                "required": True,
                            },
                        ]
                    },
                },
            },
            "interview_log": [
                {
                    "dimension": "customer_needs",
                    "question": "你当前最大的业务挑战是什么？",
                    "answer": "跨部门协作效率低，交付周期不稳定。",
                }
            ],
            "dimensions": {
                "customer_needs": {"coverage": 30},
            },
        }

        prompt = self.server.build_report_prompt(session)
        self.assertIn("用户自定义章节蓝图", prompt)
        self.assertIn("执行摘要", prompt)
        self.assertIn("行动计划", prompt)
        self.assertIn("为 `table` 时输出 Markdown 表格", prompt)
        self.assertIn("你当前最大的业务挑战是什么？", prompt)

    def test_summarize_error_for_log_strips_html_payload(self):
        raw_error = (
            "<!DOCTYPE html><html><head><title>aicodemirror.com | 504: Gateway time-out</title></head>"
            "<body><h1>Gateway time-out</h1><p>cloudflare details</p></body></html>"
        )
        compact = self.server.summarize_error_for_log(raw_error, limit=80)
        self.assertNotIn("<html>", compact.lower())
        self.assertIn("504", compact)
        self.assertIn("Gateway time-out", compact)
        self.assertLessEqual(len(compact), 80)

    def test_normalize_report_time_fields_rewrites_model_hallucinated_time(self):
        generated_at = datetime(2026, 3, 5, 23, 58, 0)
        raw = (
            "| 报告生成时间 | 2025年6月 |\n"
            "| 访谈时间 | 2024年 |\n"
            "**访谈日期**: 2024-01-01\n"
            "- 访谈时间： 2024年\n"
            "报告生成时间：2025年6月\n"
            "报告编号：V-2024-001 访谈主题：B2C 生成日期：2024年\n"
        )

        normalized = self.server.normalize_report_time_fields(raw, generated_at=generated_at)

        self.assertIn("| 报告生成时间 | 2026年03月05日 23:58 |", normalized)
        self.assertIn("| 访谈时间 | 2026-03-05 |", normalized)
        self.assertIn("**访谈日期**: 2026-03-05", normalized)
        self.assertIn("- 访谈时间： 2026-03-05", normalized)
        self.assertIn("报告生成时间：2026年03月05日 23:58", normalized)
        self.assertIn("报告编号：deep-vision-20260305-2358", normalized)
        self.assertIn("生成日期：2026年03月05日 23:58", normalized)
        self.assertNotIn("2025年6月", normalized)
        self.assertNotIn("V-2024-001", normalized)
        self.assertNotIn("访谈时间： 2024年", normalized)

    def test_generate_interview_appendix_keeps_original_order_and_checkbox_markers(self):
        session = {
            "dimensions": {"customer_needs": {"coverage": 0, "items": []}},
            "interview_log": [
                {
                    "timestamp": "2026-03-05T12:00:02Z",
                    "dimension": "customer_needs",
                    "question": "第二题",
                    "answer": "B",
                    "options": ["A", "B"],
                    "other_selected": False,
                    "other_answer_text": "",
                },
                {
                    "timestamp": "2026-03-05T12:00:01Z",
                    "dimension": "customer_needs",
                    "question": "第一题",
                    "answer": "X",
                    "options": ["A", "B"],
                    "other_selected": True,
                    "other_answer_text": "X",
                },
            ],
        }

        appendix = self.server.generate_interview_appendix(session)

        pos_q1 = appendix.find("问题 1：第二题")
        pos_q2 = appendix.find("问题 2：第一题")
        self.assertTrue(pos_q1 >= 0 and pos_q2 > pos_q1)
        self.assertIn("<div><strong>回答：</strong></div>\n<div>☐ A</div>\n<div>☑ B</div>", appendix)
        self.assertIn("<div>☑ 其他（自由输入）：X</div>", appendix)
        self.assertIn("☐ A", appendix)
        self.assertIn("☑ B", appendix)

    def test_validate_report_draft_contradiction_check_uses_structured_refs(self):
        evidence_pack = {
            "facts": [{"q_id": "Q1"}],
            "contradictions": [{"detail": "Q1 与后续回答冲突", "evidence_refs": ["Q1"]}],
            "blindspots": [],
        }
        draft_with_refs = {
            "overview": "概述",
            "needs": [{"name": "需求A", "priority": "P1", "description": "描述", "evidence_refs": ["Q1"]}],
            "analysis": {
                "customer_needs": "分析",
                "business_flow": "分析",
                "tech_constraints": "分析",
                "project_constraints": "分析",
            },
            "visualizations": {},
            "solutions": [],
            "risks": [{"risk": "冲突风险", "impact": "高", "mitigation": "处理", "evidence_refs": ["Q1"]}],
            "actions": [],
            "open_questions": [],
            "evidence_index": [{"claim": "结论", "confidence": "high", "evidence_refs": ["Q1"]}],
        }
        _, issues_with_refs = self.server.validate_report_draft_v3(draft_with_refs, evidence_pack)
        issue_types_with_refs = [item.get("type") for item in issues_with_refs if isinstance(item, dict)]
        self.assertNotIn("unresolved_contradiction", issue_types_with_refs)

        draft_without_refs = dict(draft_with_refs)
        draft_without_refs["risks"] = [{"risk": "冲突风险", "impact": "高", "mitigation": "处理", "evidence_refs": []}]
        draft_without_refs["evidence_index"] = []
        _, issues_without_refs = self.server.validate_report_draft_v3(draft_without_refs, evidence_pack)
        issue_types_without_refs = [item.get("type") for item in issues_without_refs if isinstance(item, dict)]
        self.assertIn("unresolved_contradiction", issue_types_without_refs)

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

    def test_generate_interview_appendix_marks_escalated_single_answer_as_multi_select(self):
        session = {
            "dimensions": {"customer_needs": {"coverage": 0, "items": []}},
            "interview_log": [
                {
                    "timestamp": "2026-03-05T12:00:01Z",
                    "dimension": "customer_needs",
                    "question": "需要哪些能力支持？",
                    "answer": "A；B",
                    "options": ["A", "B", "C"],
                    "multi_select": True,
                    "question_multi_select": False,
                    "selection_escalated_from_single": True,
                    "other_selected": True,
                    "other_answer_text": "以上都要",
                },
            ],
        }

        appendix = self.server.generate_interview_appendix(session)

        self.assertIn("<div>☑ A</div>", appendix)
        self.assertIn("<div>☑ B</div>", appendix)
        self.assertIn("<div>☐ C</div>", appendix)
        self.assertIn("<div>☑ 其他（自由输入）：以上都要</div>", appendix)

    def test_build_session_evidence_ledger_tracks_priority_gaps_and_shadow_draft(self):
        session = {
            "topic": "证据账本测试",
            "dimensions": {
                "customer_needs": {"coverage": 75, "items": []},
                "business_process": {"coverage": 50, "items": []},
                "tech_constraints": {"coverage": 25, "items": []},
                "project_constraints": {"coverage": 25, "items": []},
            },
            "interview_log": [
                {
                    "dimension": "customer_needs",
                    "question": "最核心痛点更像哪种情况？",
                    "answer": "审批链条长导致整体处理慢",
                    "options": ["审批链条长导致整体处理慢", "接口偶发失败影响成交", "误拦截导致客户频繁投诉"],
                    "is_follow_up": False,
                    "needs_follow_up": False,
                    "follow_up_signals": ["rich_option_answer"],
                    "quality_score": 0.86,
                    "evidence_intent": "high",
                    "answer_evidence_class": "rich_option",
                },
                {
                    "dimension": "business_process",
                    "question": "当前流程最容易卡在哪个环节？",
                    "answer": "审批节点",
                    "options": ["审批节点", "分配节点", "回访节点"],
                    "is_follow_up": False,
                    "needs_follow_up": True,
                    "follow_up_signals": ["option_only"],
                    "quality_score": 0.31,
                    "evidence_intent": "high",
                    "answer_evidence_class": "pending_follow_up",
                },
                {
                    "dimension": "tech_constraints",
                    "question": "最核心的技术边界是什么？",
                    "answer": "接口稳定性",
                    "options": ["接口稳定性", "权限安全", "上线窗口"],
                    "is_follow_up": False,
                    "needs_follow_up": False,
                    "follow_up_signals": ["too_short"],
                    "quality_score": 0.28,
                    "evidence_intent": "medium",
                    "answer_evidence_class": "weak_inferred",
                },
                {
                    "dimension": "project_constraints",
                    "question": "项目最紧的约束是什么？",
                    "answer": "时间节点",
                    "options": ["时间节点", "预算范围", "资源限制"],
                    "is_follow_up": False,
                    "needs_follow_up": True,
                    "follow_up_signals": ["option_only", "no_quantification"],
                    "quality_score": 0.22,
                    "evidence_intent": "high",
                    "answer_evidence_class": "pending_follow_up",
                },
            ],
        }

        ledger = self.server.build_session_evidence_ledger(session)

        self.assertEqual(ledger["formal_questions_total"], 4)
        self.assertIn("project_constraints", ledger["priority_dimensions"][:2])
        self.assertFalse(ledger["shadow_draft"]["actions"]["ready"])
        self.assertIn("project_constraints", ledger["shadow_draft"]["actions"]["blocking_dimensions"])
        self.assertGreater(
            ledger["dimensions"]["project_constraints"]["gap_score"],
            ledger["dimensions"]["customer_needs"]["gap_score"],
        )

    def test_plan_mid_interview_preflight_forces_follow_up_on_critical_gap(self):
        session = {
            "topic": "预检追问测试",
            "dimensions": {
                "customer_needs": {"coverage": 80, "items": []},
                "business_process": {"coverage": 60, "items": []},
                "tech_constraints": {"coverage": 20, "items": []},
                "project_constraints": {"coverage": 40, "items": []},
            },
            "interview_log": [
                {
                    "dimension": "customer_needs",
                    "question": "当前最困扰的是哪种情况？",
                    "answer": "审批链条长导致整体处理慢",
                    "options": ["审批链条长导致整体处理慢", "接口偶发失败影响成交", "误拦截导致客户频繁投诉"],
                    "is_follow_up": False,
                    "needs_follow_up": False,
                    "follow_up_signals": ["rich_option_answer"],
                    "quality_score": 0.84,
                    "evidence_intent": "high",
                    "answer_evidence_class": "rich_option",
                },
                {
                    "dimension": "business_process",
                    "question": "当前流程主要卡在哪里？",
                    "answer": "审批节点",
                    "options": ["审批节点", "分配节点", "回访节点"],
                    "is_follow_up": False,
                    "needs_follow_up": True,
                    "follow_up_signals": ["option_only"],
                    "quality_score": 0.28,
                    "evidence_intent": "high",
                    "answer_evidence_class": "pending_follow_up",
                },
                {
                    "dimension": "tech_constraints",
                    "question": "上线时最担心什么？",
                    "answer": "接口稳定性",
                    "options": ["接口稳定性", "权限安全", "上线窗口"],
                    "is_follow_up": False,
                    "needs_follow_up": False,
                    "follow_up_signals": ["too_short"],
                    "quality_score": 0.26,
                    "evidence_intent": "medium",
                    "answer_evidence_class": "weak_inferred",
                },
                {
                    "dimension": "project_constraints",
                    "question": "当前最紧的项目约束是什么？",
                    "answer": "时间节点",
                    "options": ["时间节点", "预算范围", "资源限制"],
                    "is_follow_up": False,
                    "needs_follow_up": True,
                    "follow_up_signals": ["option_only", "no_quantification"],
                    "quality_score": 0.18,
                    "evidence_intent": "high",
                    "answer_evidence_class": "pending_follow_up",
                    "hard_triggered": True,
                },
            ],
        }

        ledger = self.server.build_session_evidence_ledger(session)
        plan = self.server.plan_mid_interview_preflight(session, "project_constraints", ledger=ledger)
        decision = self.server.should_follow_up_comprehensive(
            session,
            "project_constraints",
            {
                "needs_follow_up": False,
                "signals": [],
                "hard_triggered": False,
                "reason": None,
            },
            preflight_plan=plan,
        )

        self.assertTrue(plan["preflight_due"])
        self.assertTrue(plan["should_intervene"])
        self.assertTrue(plan["force_follow_up"])
        self.assertEqual(plan["planner_mode"], "follow_up")
        self.assertTrue(plan["probe_slots"])
        self.assertTrue(decision["should_follow_up"])
        self.assertIn("mid_interview_preflight", decision["decision_factors"])

    def test_build_interview_prompt_exposes_preflight_meta_and_boosts_evidence_intent(self):
        session = {
            "topic": "预检元信息测试",
            "description": "验证问题生成前移补证据",
            "reference_materials": [],
            "dimensions": {
                "customer_needs": {"coverage": 80, "items": []},
                "business_process": {"coverage": 60, "items": []},
                "tech_constraints": {"coverage": 20, "items": []},
                "project_constraints": {"coverage": 40, "items": []},
            },
            "interview_log": [
                {
                    "dimension": "customer_needs",
                    "question": "最核心痛点更像哪种情况？",
                    "answer": "审批链条长导致整体处理慢",
                    "options": ["审批链条长导致整体处理慢", "接口偶发失败影响成交", "误拦截导致客户频繁投诉"],
                    "is_follow_up": False,
                    "needs_follow_up": False,
                    "follow_up_signals": ["rich_option_answer"],
                    "quality_score": 0.86,
                    "evidence_intent": "high",
                    "answer_evidence_class": "rich_option",
                },
                {
                    "dimension": "business_process",
                    "question": "当前流程主要卡在哪里？",
                    "answer": "审批节点",
                    "options": ["审批节点", "分配节点", "回访节点"],
                    "is_follow_up": False,
                    "needs_follow_up": True,
                    "follow_up_signals": ["option_only"],
                    "quality_score": 0.28,
                    "evidence_intent": "high",
                    "answer_evidence_class": "pending_follow_up",
                },
                {
                    "dimension": "tech_constraints",
                    "question": "上线时最担心什么？",
                    "answer": "接口稳定性",
                    "options": ["接口稳定性", "权限安全", "上线窗口"],
                    "is_follow_up": False,
                    "needs_follow_up": False,
                    "follow_up_signals": ["too_short"],
                    "quality_score": 0.26,
                    "evidence_intent": "medium",
                    "answer_evidence_class": "weak_inferred",
                },
                {
                    "dimension": "project_constraints",
                    "question": "当前最紧的项目约束是什么？",
                    "answer": "时间节点",
                    "options": ["时间节点", "预算范围", "资源限制"],
                    "is_follow_up": False,
                    "needs_follow_up": True,
                    "follow_up_signals": ["option_only", "no_quantification"],
                    "quality_score": 0.18,
                    "evidence_intent": "high",
                    "answer_evidence_class": "pending_follow_up",
                    "hard_triggered": True,
                },
            ],
        }
        all_dim_logs = [log for log in session["interview_log"] if log.get("dimension") == "project_constraints"]

        prompt, _, meta = self.server.build_interview_prompt(session, "project_constraints", all_dim_logs)

        self.assertIn("证据预检优先级", prompt)
        self.assertEqual(meta["answer_mode"], "pick_with_reason")
        self.assertTrue(meta["requires_rationale"])
        self.assertEqual(meta["evidence_intent"], "high")
        self.assertTrue(meta["mid_interview_preflight"]["should_intervene"])
        self.assertIn("project_constraints", meta["evidence_ledger"]["priority_dimensions"])

    def test_plan_mid_interview_preflight_throttles_recent_same_focus(self):
        session = {
            "topic": "预检冷却测试",
            "dimensions": {
                "customer_needs": {"coverage": 80, "items": []},
                "business_process": {"coverage": 40, "items": []},
                "tech_constraints": {"coverage": 30, "items": []},
                "project_constraints": {"coverage": 50, "items": []},
            },
            "interview_log": [
                {
                    "dimension": "customer_needs",
                    "question": "主要痛点是什么？",
                    "answer": "审批链条长导致整体处理慢",
                    "options": ["审批链条长导致整体处理慢", "接口偶发失败影响成交", "误拦截导致客户频繁投诉"],
                    "is_follow_up": False,
                    "needs_follow_up": False,
                    "follow_up_signals": ["rich_option_answer"],
                    "quality_score": 0.82,
                    "evidence_intent": "high",
                    "answer_evidence_class": "rich_option",
                },
                {
                    "dimension": "business_process",
                    "question": "角色分工里最容易卡在哪一段？",
                    "answer": "审批节点",
                    "options": ["审批节点", "分配节点", "回访节点"],
                    "is_follow_up": False,
                    "needs_follow_up": True,
                    "follow_up_signals": ["option_only"],
                    "quality_score": 0.24,
                    "evidence_intent": "high",
                    "answer_evidence_class": "pending_follow_up",
                    "preflight_intervened": True,
                    "preflight_fingerprint": self.server._build_preflight_focus_fingerprint(
                        "business_process",
                        target_aspect="角色分工",
                        probe_slots=["角色分工", "异常处理"],
                        blocked_sections=["solutions", "actions"],
                    ),
                    "preflight_planner_mode": "gap_probe",
                    "preflight_probe_slots": ["角色分工", "异常处理"],
                },
                {
                    "dimension": "business_process",
                    "question": "异常处理通常由谁兜底？",
                    "answer": "还没有固定角色",
                    "options": ["由业务负责人兜底", "由运营同学兜底", "还没有固定角色"],
                    "is_follow_up": False,
                    "needs_follow_up": True,
                    "follow_up_signals": ["option_only"],
                    "quality_score": 0.28,
                    "evidence_intent": "high",
                    "answer_evidence_class": "pending_follow_up",
                },
            ],
        }

        initial_ledger = self.server.build_session_evidence_ledger(session)
        initial_plan = self.server.plan_mid_interview_preflight(session, "business_process", ledger=initial_ledger)
        session["interview_log"][1]["preflight_fingerprint"] = initial_plan["fingerprint"]

        ledger = self.server.build_session_evidence_ledger(session)
        plan = self.server.plan_mid_interview_preflight(session, "business_process", ledger=ledger)

        self.assertTrue(plan["cooldown_suppressed"])
        self.assertFalse(plan["should_intervene"])
        self.assertEqual(plan["planner_mode"], "observe")

    def test_plan_mid_interview_preflight_skips_low_value_gap_outside_priority_window(self):
        session = {
            "topic": "预检收益阈值测试",
            "scenario_config": {
                "dimensions": [
                    {"id": "insight_a", "name": "洞察A", "description": "", "key_aspects": ["场景", "角色", "目标"]},
                    {"id": "insight_b", "name": "洞察B", "description": "", "key_aspects": ["流程", "触发", "结果"]},
                    {"id": "insight_c", "name": "洞察C", "description": "", "key_aspects": ["边界", "频次", "影响"]},
                    {"id": "misc_notes", "name": "补充记录", "description": "", "key_aspects": ["补充信息"]},
                ]
            },
            "dimensions": {
                "insight_a": {"coverage": 80, "items": []},
                "insight_b": {"coverage": 75, "items": []},
                "insight_c": {"coverage": 70, "items": []},
                "misc_notes": {"coverage": 65, "items": []},
            },
            "interview_log": [
                {
                    "dimension": "insight_a",
                    "question": "主要痛点是什么？",
                    "answer": "审批链条长导致整体处理慢",
                    "options": ["审批链条长导致整体处理慢", "接口偶发失败影响成交", "误拦截导致客户频繁投诉"],
                    "is_follow_up": False,
                    "needs_follow_up": False,
                    "follow_up_signals": ["rich_option_answer"],
                    "quality_score": 0.84,
                    "evidence_intent": "high",
                    "answer_evidence_class": "rich_option",
                },
                {
                    "dimension": "insight_b",
                    "question": "哪段流程更值得优先优化？",
                    "answer": "审批节点",
                    "options": ["审批节点", "分配节点", "回访节点"],
                    "is_follow_up": False,
                    "needs_follow_up": False,
                    "follow_up_signals": ["rich_option_answer"],
                    "quality_score": 0.76,
                    "evidence_intent": "high",
                    "answer_evidence_class": "rich_option",
                },
                {
                    "dimension": "insight_c",
                    "question": "当前技术边界里最敏感的是哪一项？",
                    "answer": "权限安全",
                    "options": ["权限安全", "接口稳定性", "上线窗口"],
                    "is_follow_up": False,
                    "needs_follow_up": False,
                    "follow_up_signals": ["rich_option_answer"],
                    "quality_score": 0.73,
                    "evidence_intent": "high",
                    "answer_evidence_class": "rich_option",
                },
                {
                    "dimension": "misc_notes",
                    "question": "还有什么需要额外记录的补充信息？",
                    "answer": "补充信息暂时没有",
                    "options": ["暂时没有", "需要后续确认", "有少量补充说明"],
                    "is_follow_up": False,
                    "needs_follow_up": False,
                    "follow_up_signals": ["option_only"],
                    "quality_score": 0.48,
                    "evidence_intent": "medium",
                    "answer_evidence_class": "weak_inferred",
                },
            ],
        }

        ledger = self.server.build_session_evidence_ledger(session)
        plan = self.server.plan_mid_interview_preflight(session, "misc_notes", ledger=ledger)

        self.assertTrue(plan["preflight_due"])
        self.assertFalse(plan["high_value_gap"])
        self.assertFalse(plan["should_intervene"])
        self.assertEqual(plan["planner_mode"], "observe")

    def test_build_session_evidence_ledger_maps_dynamic_shadow_draft_sections(self):
        session = {
            "topic": "技术方案评审",
            "scenario_config": {
                "dimensions": [
                    {
                        "id": "current_state",
                        "name": "现状评估",
                        "description": "现有系统架构、技术债务、性能瓶颈、团队能力",
                        "key_aspects": ["系统架构", "技术债务", "性能瓶颈", "团队能力"],
                    },
                    {
                        "id": "target_architecture",
                        "name": "目标架构",
                        "description": "期望架构形态、扩展性要求、可用性目标",
                        "key_aspects": ["架构形态", "扩展性", "可用性", "可维护性"],
                    },
                    {
                        "id": "tech_selection",
                        "name": "技术选型",
                        "description": "候选技术栈对比、社区成熟度、学习成本、迁移风险",
                        "key_aspects": ["候选方案", "成熟度评估", "学习成本", "迁移风险"],
                    },
                    {
                        "id": "implementation_path",
                        "name": "实施路径",
                        "description": "阶段划分、里程碑定义、回滚策略、验证方案",
                        "key_aspects": ["阶段划分", "里程碑", "回滚策略", "验证方案"],
                    },
                ],
                "report": {
                    "sections": [
                        "overview",
                        "current_state_analysis",
                        "target_architecture",
                        "tech_comparison",
                        "implementation_roadmap",
                        "risks",
                        "recommendations",
                        "appendix",
                    ]
                },
            },
            "dimensions": {
                "current_state": {"coverage": 100, "items": []},
                "target_architecture": {"coverage": 100, "items": []},
                "tech_selection": {"coverage": 50, "items": []},
                "implementation_path": {"coverage": 0, "items": []},
            },
            "interview_log": [
                {
                    "dimension": "current_state",
                    "question": "当前系统最大的性能瓶颈是什么？",
                    "answer": "高峰期推理延迟明显升高",
                    "is_follow_up": False,
                    "follow_up_signals": ["rich_option_answer"],
                    "quality_score": 0.82,
                    "evidence_intent": "high",
                    "answer_evidence_class": "rich_option",
                },
                {
                    "dimension": "target_architecture",
                    "question": "目标架构更关注哪一项？",
                    "answer": "可维护性与扩展性",
                    "is_follow_up": False,
                    "follow_up_signals": ["rich_option_answer"],
                    "quality_score": 0.8,
                    "evidence_intent": "high",
                    "answer_evidence_class": "rich_option",
                },
                {
                    "dimension": "tech_selection",
                    "question": "目前的候选方案有哪些？",
                    "answer": "TensorFlow 与 PyTorch 都在评估",
                    "is_follow_up": False,
                    "follow_up_signals": ["rich_option_answer"],
                    "quality_score": 0.68,
                    "evidence_intent": "high",
                    "answer_evidence_class": "rich_option",
                },
            ],
        }

        ledger = self.server.build_session_evidence_ledger(session)
        shadow = ledger["shadow_draft"]

        self.assertIn("current_state_analysis", shadow)
        self.assertIn("tech_comparison", shadow)
        self.assertIn("implementation_roadmap", shadow)
        self.assertIn("current_state", shadow["current_state_analysis"]["blocking_dimensions"] or [])
        self.assertIn("implementation_path", shadow["implementation_roadmap"]["blocking_dimensions"])
        self.assertIn("tech_selection", shadow["tech_comparison"]["blocking_dimensions"])
        self.assertIn("implementation_path", shadow["actions"]["blocking_dimensions"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
