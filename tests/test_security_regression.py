import io
import importlib.util
import json
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
            "**访谈日期**: 2024-01-01\n"
            "报告生成时间：2025年6月\n"
        )

        normalized = self.server.normalize_report_time_fields(raw, generated_at=generated_at)

        self.assertIn("| 报告生成时间 | 2026年3月 |", normalized)
        self.assertIn("**访谈日期**: 2026-03-05", normalized)
        self.assertIn("报告生成时间：2026年3月", normalized)
        self.assertNotIn("2025年6月", normalized)

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
