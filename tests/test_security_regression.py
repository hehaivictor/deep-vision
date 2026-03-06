import io
import importlib.util
import json
import os
import sys
import tempfile
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
        send_resp = self.client.post(
            "/api/auth/sms/send-code",
            json={"account": account, "scene": "login"},
        )
        self.assertEqual(send_resp.status_code, 200, send_resp.get_data(as_text=True))
        code = (send_resp.get_json() or {}).get("test_code")
        self.assertTrue(code, "TESTING 模式应返回 test_code")

        login_resp = self.client.post(
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

    def test_should_not_retry_v3_failover_when_multiple_gate_issues(self):
        payload = {
            "status": "failed",
            "reason": "quality_gate_failed",
            "final_issue_count": 2,
            "review_issues": [
                {"type": "blindspot", "severity": "high", "target": "actions", "message": "盲区未处理"},
                {"type": "quality_gate_table", "severity": "high", "target": "actions", "message": "表格化不足"},
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

    def test_resolve_ai_client_with_lane_skips_cooled_report_lane(self):
        keys = [
            "GATEWAY_CIRCUIT_BREAKER_ENABLED",
            "GATEWAY_CIRCUIT_FAIL_THRESHOLD",
            "GATEWAY_CIRCUIT_COOLDOWN_SECONDS",
            "GATEWAY_CIRCUIT_FAILURE_WINDOW_SECONDS",
            "question_ai_client",
            "report_ai_client",
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
            report_client = object()
            self.server.question_ai_client = question_client
            self.server.report_ai_client = report_client
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
            report_client = _DummyClient("report-lane-ok")
            self.server.question_ai_client = question_client
            self.server.report_ai_client = report_client
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
            self.assertEqual(report_client.messages.calls, 0)
            self.assertEqual(question_client.messages.calls, 1)
        finally:
            self.server.reset_gateway_circuit_state()
            for key, value in backup.items():
                setattr(self.server, key, value)

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
