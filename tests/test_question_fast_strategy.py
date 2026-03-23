import importlib.util
import json
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest import mock


ROOT_DIR = Path(__file__).resolve().parents[1]
SERVER_PATH = ROOT_DIR / "web" / "server.py"


def load_server_module(module_name: str = "dv_server_question_fast_strategy_test"):
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

    spec = importlib.util.spec_from_file_location(module_name, SERVER_PATH)
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


class QuestionFastStrategyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = load_server_module()

    def setUp(self):
        self.server.QUESTION_FAST_PATH_ENABLED = True
        self.server.ENABLE_WEB_SEARCH = False
        self.server.QUESTION_FAST_TIMEOUT = 12.0
        self.server.QUESTION_FAST_REFERENCE_TIMEOUT = 15.0
        self.server.QUESTION_FAST_REFERENCE_QUESTION_TIMEOUT = 15.0
        self.server.QUESTION_FAST_REFERENCE_REPORT_TIMEOUT = 14.0
        self.server.QUESTION_FAST_MAX_TOKENS = 1000
        self.server.QUESTION_FAST_REFERENCE_QUESTION_MAX_TOKENS = 1000
        self.server.QUESTION_FAST_REFERENCE_REPORT_MAX_TOKENS = 1100
        self.server.QUESTION_FAST_LIGHT_PROMPT_MAX_CHARS = 1800
        self.server.QUESTION_FAST_LIGHT_REFERENCE_DOCS_ENABLED = True
        self.server.QUESTION_FAST_LIGHT_MAX_REFERENCE_DOCS = 2
        self.server.QUESTION_FAST_SKIP_WHEN_TRUNCATED_DOCS = True
        self.server.QUESTION_FAST_ADAPTIVE_ENABLED = True
        self.server.QUESTION_FAST_ADAPTIVE_WINDOW_SIZE = 4
        self.server.QUESTION_FAST_ADAPTIVE_MIN_SAMPLES = 4
        self.server.QUESTION_FAST_ADAPTIVE_MIN_HIT_RATE = 0.5
        self.server.QUESTION_FAST_ADAPTIVE_COOLDOWN_SECONDS = 600.0
        self.server.QUESTION_FAST_LIGHT_DOC_BUDGET = 1400
        self.server.QUESTION_FAST_REFERENCE_PROMPT_MAX_CHARS = 2600
        self.server.QUESTION_LANE_DYNAMIC_ENABLED = True
        self.server.QUESTION_LANE_STATS_WINDOW_SIZE = 6
        self.server.QUESTION_LANE_STATS_MIN_SAMPLES = 3
        self.server.QUESTION_LANE_SWITCH_SUCCESS_MARGIN = 0.08
        self.server.QUESTION_LANE_SWITCH_LATENCY_RATIO = 0.18
        self.server.QUESTION_FAST_TIMEOUT_BY_LANE = {}
        self.server.QUESTION_FAST_MAX_TOKENS_BY_LANE = {}
        self.server.QUESTION_FULL_TIMEOUT_BY_LANE = {}
        self.server.QUESTION_FULL_MAX_TOKENS_BY_LANE = {}
        self.server.QUESTION_HEDGE_DELAY_BY_LANE = {}
        self.server.QUESTION_HEDGE_ADAPTIVE_ENABLED = True
        self.server.QUESTION_HEDGE_ADAPTIVE_MIN_SAMPLES = 3
        self.server.QUESTION_HEDGE_ADAPTIVE_PERCENTILE = 0.75
        self.server.QUESTION_HEDGE_ADAPTIVE_TIMEOUT_RATIO = 0.4
        self.server.QUESTION_HIGH_EVIDENCE_PRIMARY_LANE = "question"
        self.server.QUESTION_HIGH_EVIDENCE_SECONDARY_LANE = "report"
        self.server.QUESTION_HIGH_EVIDENCE_DISABLE_DYNAMIC_LANE = True
        self.server.QUESTION_HIGH_EVIDENCE_HEDGED_ENABLED = False
        self.server.QUESTION_HIGH_EVIDENCE_FAST_PATH_ENABLED = True
        self.server.QUESTION_HEDGE_FAILURE_FALLBACK_ENABLED = True
        self.server.QUESTION_HEDGE_REQUIRE_SHADOW_BLOCKER = True
        self.server.QUESTION_FAST_REFERENCE_HEDGE_BYPASS_BUDGET = True
        self.server.QUESTION_SESSION_HEDGE_BUDGET = 4
        self.server.QUESTION_DIMENSION_HEDGE_BUDGET = 1
        self.server.PREFETCH_QUESTION_TIMEOUT = 48.0
        self.server.PREFETCH_QUESTION_MAX_TOKENS = 1200
        self.server.PREFETCH_QUESTION_FAST_TIMEOUT = 10.5
        self.server.PREFETCH_QUESTION_FAST_MAX_TOKENS = 760
        self.server.PREFETCH_QUESTION_HEDGE_DELAY_SECONDS = 2.4
        self.server.PREFETCH_QUESTION_PRIMARY_LANE = "summary"
        self.server.PREFETCH_QUESTION_SECONDARY_LANE = "question"
        self.server.SEARCH_DECISION_MAX_INFLIGHT = 1
        self.server.SEARCH_DECISION_PREFETCH_RULE_ONLY = True
        self.server.SEARCH_DECISION_SEMAPHORE = self.server.threading.BoundedSemaphore(self.server.SEARCH_DECISION_MAX_INFLIGHT)
        self.server.MAX_TOKENS_QUESTION = 1600
        self.server.API_TIMEOUT = 90.0
        self.server.reset_question_fast_strategy_state()
        self.server.reset_question_lane_strategy_state()
        self.server.reset_search_decision_stats()
        with self.server.prefetch_cache_lock:
            self.server.prefetch_cache.clear()
        with self.server.search_decision_cache_lock:
            self.server.search_decision_cache.clear()
            self.server.search_decision_inflight.clear()

    def test_skip_reason_when_prompt_too_long(self):
        reason = self.server._get_question_fast_skip_reason("x" * 1900, truncated_docs=[])
        self.assertEqual(reason, "prompt_too_long:1900>1800")

    def test_skip_reason_ignores_compacted_docs_when_allowed(self):
        reason = self.server._get_question_fast_skip_reason(
            "x" * 1200,
            truncated_docs=["参考资料已压缩"],
            allow_compacted_docs=True,
        )
        self.assertEqual(reason, "")

    def test_low_hit_rate_opens_fast_path_cooldown(self):
        for _ in range(4):
            self.server._record_question_fast_outcome(False, lane="question", reason="timeout")

        snapshot = self.server.get_question_fast_strategy_snapshot()
        self.assertTrue(snapshot.get("cooldown_active"))
        self.assertGreater(snapshot.get("cooldown_remaining_seconds", 0.0), 0.0)
        self.assertIn("命中率", snapshot.get("last_reason", ""))

        reason = self.server._get_question_fast_skip_reason("short prompt", truncated_docs=[])
        self.assertTrue(reason.startswith("adaptive_cooldown:"))

    def test_generate_question_skips_fast_for_heavy_prompt(self):
        calls = []
        fake_result = {
            "question": "请描述当前最关键的阻塞点？",
            "options": ["选项A", "选项B", "选项C"],
            "multi_select": False,
            "is_follow_up": False,
            "follow_up_reason": None,
            "conflict_detected": False,
            "conflict_description": None,
            "ai_recommendation": None,
        }

        original_call = self.server._call_question_with_optional_hedge
        original_parse = self.server.parse_question_response
        self.addCleanup(setattr, self.server, "_call_question_with_optional_hedge", original_call)
        self.addCleanup(setattr, self.server, "parse_question_response", original_parse)

        def fake_call(prompt, max_tokens, call_type, truncated_docs=None, timeout=None, retry_on_timeout=False, debug=False, **_kwargs):
            calls.append({
                "prompt_length": len(prompt or ""),
                "max_tokens": max_tokens,
                "call_type": call_type,
                "timeout": timeout,
            })
            return "{\"question\": \"ok\"}", "summary", {"response_length": 18}

        self.server._call_question_with_optional_hedge = fake_call
        self.server.parse_question_response = lambda _response, debug=False: dict(fake_result)

        response, result, tier_used = self.server.generate_question_with_tiered_strategy(
            "x" * 2500,
            truncated_docs=[],
            debug=False,
            base_call_type="question",
            allow_fast_path=True,
        )

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["call_type"], "question")
        self.assertEqual(calls[0]["max_tokens"], 1600)
        self.assertEqual(tier_used, "full:summary")
        self.assertEqual(response, "{\"question\": \"ok\"}")
        self.assertEqual(result.get("question"), fake_result["question"])

    def test_runtime_profile_prefers_light_prompt_for_follow_up(self):
        profile = self.server._select_question_generation_runtime_profile(
            prompt="x" * 2400,
            truncated_docs=[],
            decision_meta={
                "should_follow_up": True,
                "has_search": False,
                "has_reference_docs": False,
                "has_truncated_docs": False,
                "missing_aspects": [],
                "formal_questions_count": 1,
                "follow_up_round": 1,
            },
            base_call_type="question",
            allow_fast_path=True,
        )

        self.assertEqual(profile["profile_name"], "question_follow_up_light")
        self.assertTrue(profile["allow_fast_path"])
        self.assertEqual(profile["fast_output_mode"], "light")
        self.assertLess(profile["fast_max_tokens"], self.server.MAX_TOKENS_QUESTION)

    def test_runtime_profile_keeps_fast_path_for_high_intent_follow_up_question(self):
        profile = self.server._select_question_generation_runtime_profile(
            prompt="x" * 1600,
            truncated_docs=[],
            decision_meta={
                "should_follow_up": True,
                "has_search": False,
                "has_reference_docs": False,
                "has_truncated_docs": False,
                "missing_aspects": ["角色分工"],
                "formal_questions_count": 2,
                "follow_up_round": 1,
                "answer_mode": "pick_with_reason",
                "requires_rationale": True,
                "evidence_intent": "high",
            },
            base_call_type="question",
            allow_fast_path=True,
        )

        self.assertEqual(profile["profile_name"], "question_follow_up_evidence")
        self.assertTrue(profile["allow_fast_path"])
        self.assertEqual(profile["fast_output_mode"], "light")
        self.assertIn("evidence_fast", profile["selection_reason"])
        self.assertEqual(profile["primary_lane"], "question")

    def test_runtime_profile_does_not_promote_pick_with_reason_to_high_evidence_by_default(self):
        profile = self.server._select_question_generation_runtime_profile(
            prompt="x" * 1400,
            truncated_docs=[],
            decision_meta={
                "should_follow_up": False,
                "has_search": False,
                "has_reference_docs": False,
                "has_truncated_docs": False,
                "missing_aspects": ["预算口径"],
                "formal_questions_count": 2,
                "follow_up_round": 0,
                "answer_mode": "pick_with_reason",
                "requires_rationale": False,
                "evidence_intent": "",
            },
            base_call_type="question",
            allow_fast_path=True,
        )

        self.assertEqual(profile["evidence_intent"], "medium")
        self.assertEqual(profile["profile_name"], "question_probe_light")
        self.assertTrue(profile["allow_fast_path"])
        self.assertEqual(profile["fast_output_mode"], "light")
        self.assertTrue(profile["requires_rationale"])
        self.assertEqual(profile["secondary_lane"], "summary")
        self.assertFalse(profile["fallback_enabled"])
        self.assertTrue(profile["dynamic_lane_order_enabled"])
        self.assertEqual(profile["disallowed_lanes"], [])

    def test_runtime_profile_uses_reference_light_when_docs_present(self):
        profile = self.server._select_question_generation_runtime_profile(
            prompt="x" * 2200,
            truncated_docs=[],
            decision_meta={
                "should_follow_up": False,
                "has_search": False,
                "has_reference_docs": True,
                "has_truncated_docs": False,
                "missing_aspects": ["实施路径"],
                "formal_questions_count": 2,
                "follow_up_round": 0,
                "answer_mode": "pick_only",
                "requires_rationale": False,
                "evidence_intent": "low",
            },
            base_call_type="question",
            allow_fast_path=True,
        )

        self.assertEqual(profile["profile_name"], "question_probe_reference_light")
        self.assertTrue(profile["allow_fast_path"])
        self.assertEqual(profile["fast_output_mode"], "light")
        self.assertEqual(profile["fast_prompt_max_chars"], 2600)
        self.assertEqual(profile["fast_timeout"], 15.0)
        self.assertEqual(profile["fast_timeout_by_lane"].get("question"), 15.0)
        self.assertEqual(profile["fast_timeout_by_lane"].get("report"), 14.0)
        self.assertEqual(profile["fast_max_tokens_by_lane"].get("question"), 1000)
        self.assertEqual(profile["fast_max_tokens_by_lane"].get("report"), 1100)
        self.assertIn("reference_light", profile["selection_reason"])

    def test_runtime_profile_keeps_fast_path_for_high_evidence_probe_with_reference_docs(self):
        profile = self.server._select_question_generation_runtime_profile(
            prompt="x" * 3200,
            truncated_docs=["需求文档A"],
            decision_meta={
                "should_follow_up": False,
                "has_search": False,
                "has_reference_docs": True,
                "has_truncated_docs": True,
                "missing_aspects": ["角色分工"],
                "formal_questions_count": 2,
                "follow_up_round": 0,
                "answer_mode": "pick_with_reason",
                "requires_rationale": True,
                "evidence_intent": "high",
            },
            base_call_type="question",
            allow_fast_path=True,
        )

        self.assertEqual(profile["profile_name"], "question_probe_reference_light")
        self.assertTrue(profile["allow_fast_path"])
        self.assertEqual(profile["fast_output_mode"], "light")
        self.assertEqual(profile["fast_timeout"], 15.0)
        self.assertEqual(profile["fast_timeout_by_lane"].get("question"), 15.0)
        self.assertEqual(profile["fast_timeout_by_lane"].get("report"), 14.0)
        self.assertIn("evidence_fast", profile["selection_reason"])
        self.assertIn("has_reference_docs", profile["selection_reason"])

    def test_runtime_profile_uses_reference_light_for_first_high_evidence_question_with_docs(self):
        profile = self.server._select_question_generation_runtime_profile(
            prompt="x" * 2800,
            truncated_docs=[],
            decision_meta={
                "should_follow_up": False,
                "has_search": False,
                "has_reference_docs": True,
                "has_truncated_docs": False,
                "missing_aspects": [],
                "formal_questions_count": 0,
                "follow_up_round": 0,
                "answer_mode": "pick_with_reason",
                "requires_rationale": True,
                "evidence_intent": "high",
            },
            base_call_type="question",
            allow_fast_path=True,
        )

        self.assertEqual(profile["profile_name"], "question_evidence_reference_light")
        self.assertTrue(profile["allow_fast_path"])
        self.assertEqual(profile["fast_output_mode"], "light")
        self.assertEqual(profile["fast_timeout"], 15.0)
        self.assertEqual(profile["fast_timeout_by_lane"].get("question"), 15.0)
        self.assertEqual(profile["fast_timeout_by_lane"].get("report"), 14.0)
        self.assertIn("evidence_fast", profile["selection_reason"])
        self.assertIn("reference_light", profile["selection_reason"])

    def test_dynamic_lane_order_respects_disallowed_summary_for_high_intent_question(self):
        runtime_profile = {
            "profile_name": "question_follow_up_evidence",
            "fast_prompt_mode": "full",
            "full_prompt_mode": "full",
            "primary_lane": "question",
            "secondary_lane": "report",
            "dynamic_lane_order_enabled": False,
            "disallowed_lanes": ["summary"],
        }

        primary_lane, secondary_lane, lane_meta = self.server._resolve_dynamic_question_lane_order(runtime_profile, phase="full")
        self.assertEqual(primary_lane, "question")
        self.assertEqual(secondary_lane, "report")
        self.assertNotIn("summary", lane_meta["ordered_candidates"])
        self.assertFalse(lane_meta["dynamic_enabled"])

    def test_normalize_generated_question_result_uses_fallback_contract(self):
        result = self.server.normalize_generated_question_result(
            {
                "question": "最关键的阻塞点是什么？",
                "options": ["审批慢", "接口不稳", "资源不足"],
            },
            fallback_contract={
                "answer_mode": "pick_with_reason",
                "requires_rationale": True,
                "evidence_intent": "high",
            },
        )

        self.assertEqual(result["answer_mode"], "pick_with_reason")
        self.assertTrue(result["requires_rationale"])
        self.assertEqual(result["evidence_intent"], "high")

    def test_prepare_runtime_builds_light_prompt_variant(self):
        calls = []
        original_build = self.server.build_interview_prompt
        original_select = self.server._select_question_generation_runtime_profile
        self.addCleanup(setattr, self.server, "build_interview_prompt", original_build)
        self.addCleanup(setattr, self.server, "_select_question_generation_runtime_profile", original_select)

        def fake_build(session, dimension, all_dim_logs, session_id=None, session_signature=None, output_mode="full", search_mode="default"):
            calls.append(output_mode)
            return (
                f"PROMPT:{output_mode}",
                [],
                {
                    "output_mode": output_mode,
                    "search_mode": search_mode,
                    "should_follow_up": output_mode == "light",
                    "has_search": False,
                    "has_reference_docs": False,
                    "has_truncated_docs": False,
                    "missing_aspects": [],
                    "formal_questions_count": 1,
                    "follow_up_round": 0,
                },
            )

        def fake_select(prompt, truncated_docs=None, decision_meta=None, base_call_type="question", allow_fast_path=True):
            return {
                "profile_name": "question_follow_up_light",
                "selection_reason": "follow_up",
                "allow_fast_path": True,
                "fast_output_mode": "light",
                "full_output_mode": "full",
                "fast_timeout": 8.0,
                "fast_max_tokens": 640,
                "full_timeout": 24.0,
                "full_max_tokens": 1200,
                "primary_lane": "question",
                "secondary_lane": "summary",
                "hedged_enabled": True,
                "hedge_delay_seconds": 1.0,
            }

        self.server.build_interview_prompt = fake_build
        self.server._select_question_generation_runtime_profile = fake_select

        prepared = self.server._prepare_question_generation_runtime(
            session={"topic": "测试", "session_id": "sid"},
            dimension="customer_needs",
            all_dim_logs=[],
            base_call_type="question",
            allow_fast_path=True,
        )

        self.assertEqual(calls, ["full", "light"])
        self.assertEqual(prepared["full_prompt"], "PROMPT:full")
        self.assertEqual(prepared["fast_prompt"], "PROMPT:light")
        self.assertEqual(prepared["runtime_profile"]["fast_prompt_mode"], "light")

    def test_build_light_prompt_trims_reference_context_and_history(self):
        self.server.ENABLE_WEB_SEARCH = False
        session = {
            "topic": "机加工艺方案评审",
            "description": "背景" + ("A" * 320) + "尾部标记",
            "session_id": "sid",
            "reference_materials": [
                {
                    "name": "超长参考资料文档-用于轻量压缩",
                    "content": "前段信息 " + ("资料片段 " * 80) + " 尾部唯一标记",
                }
            ],
            "dimensions": {"target_architecture": {"coverage": 30, "items": []}},
            "interview_log": [
                {"dimension": "target_architecture", "question": "旧问题保留标记1", "answer": "旧回答保留标记1", "is_follow_up": False},
                {"dimension": "target_architecture", "question": "最近问题保留标记2", "answer": "最近回答保留标记2 " + ("B" * 180), "is_follow_up": False},
            ],
            "scenario_config": {
                "dimensions": [
                    {
                        "id": "target_architecture",
                        "name": "目标架构",
                        "description": "需要确认目标架构的边界、系统关系、部署约束和演进节奏",
                    }
                ]
            },
        }
        all_dim_logs = [log for log in session["interview_log"] if log.get("dimension") == "target_architecture"]

        prompt, _truncated_docs, meta = self.server.build_interview_prompt(
            session,
            "target_architecture",
            all_dim_logs,
            output_mode="light",
        )

        self.assertEqual(meta["output_mode"], "light")
        self.assertIn("最近问题保留标记2", prompt)
        self.assertNotIn("旧问题保留标记1", prompt)
        self.assertNotIn("尾部标记", prompt)
        self.assertNotIn("尾部唯一标记", prompt)
        self.assertLess(len(prompt), 2600)

    def test_prepare_runtime_keeps_reference_light_fast_path_when_light_prompt_compacts_docs(self):
        original_build = self.server.build_interview_prompt
        original_select = self.server._select_question_generation_runtime_profile
        self.addCleanup(setattr, self.server, "build_interview_prompt", original_build)
        self.addCleanup(setattr, self.server, "_select_question_generation_runtime_profile", original_select)

        def fake_build(session, dimension, all_dim_logs, session_id=None, session_signature=None, output_mode="full", search_mode="default"):
            if output_mode == "full":
                return (
                    "FULL_PROMPT",
                    [],
                    {
                        "output_mode": "full",
                        "search_mode": search_mode,
                        "has_search": False,
                        "has_reference_docs": True,
                        "has_truncated_docs": False,
                        "reference_docs_compact_mode": False,
                        "formal_questions_count": 2,
                        "missing_aspects": ["可维护性"],
                        "answer_mode": "pick_with_reason",
                        "requires_rationale": True,
                        "evidence_intent": "high",
                    },
                )
            return (
                "LIGHT_PROMPT",
                ["参考资料已压缩"],
                {
                    "output_mode": "light",
                    "search_mode": search_mode,
                    "has_search": False,
                    "has_reference_docs": True,
                    "has_truncated_docs": True,
                    "reference_docs_compact_mode": True,
                    "formal_questions_count": 2,
                    "missing_aspects": ["可维护性"],
                    "answer_mode": "pick_with_reason",
                    "requires_rationale": True,
                    "evidence_intent": "high",
                },
            )

        self.server.build_interview_prompt = fake_build
        self.server._select_question_generation_runtime_profile = lambda *args, **kwargs: {
            "profile_name": "question_probe_reference_light",
            "selection_reason": "reference_light",
            "allow_fast_path": True,
            "fast_output_mode": "light",
            "full_output_mode": "full",
            "fast_timeout": 8.0,
            "fast_max_tokens": 760,
            "full_timeout": 24.0,
            "full_max_tokens": 1200,
            "primary_lane": "question",
            "secondary_lane": "summary",
            "hedged_enabled": True,
            "hedge_delay_seconds": 1.0,
            "evidence_intent": "high",
            "requires_rationale": True,
            "answer_mode": "pick_with_reason",
        }

        prepared = self.server._prepare_question_generation_runtime(
            session={"topic": "测试", "session_id": "sid"},
            dimension="target_architecture",
            all_dim_logs=[],
            base_call_type="question",
            allow_fast_path=True,
        )

        self.assertTrue(prepared["runtime_profile"]["allow_fast_path"])
        self.assertEqual(prepared["fast_prompt"], "LIGHT_PROMPT")
        self.assertEqual(prepared["fast_truncated_docs"], ["参考资料已压缩"])
        self.assertEqual(prepared["runtime_profile"]["fast_prompt_mode"], "light")
        self.assertTrue(prepared["runtime_profile"]["fast_allow_compacted_docs"])
        self.assertNotIn("light_prompt_truncated_docs", prepared["runtime_profile"]["selection_reason"])

    def test_generate_question_allows_fast_with_compacted_reference_docs(self):
        calls = []
        original_call = self.server._call_question_with_optional_hedge
        original_parse = self.server.parse_question_response
        self.addCleanup(setattr, self.server, "_call_question_with_optional_hedge", original_call)
        self.addCleanup(setattr, self.server, "parse_question_response", original_parse)

        def fake_call(prompt, max_tokens, call_type, truncated_docs=None, timeout=None, retry_on_timeout=False, debug=False, **kwargs):
            calls.append({
                "prompt": prompt,
                "truncated_docs": list(truncated_docs or []),
                "call_type": call_type,
            })
            return (
                '{"question":"请确认扩展规模","options":["100万","500万","1000万"],"multi_select":false,"is_follow_up":false,"follow_up_reason":null}',
                "question",
                {"response_length": 72},
            )

        self.server._call_question_with_optional_hedge = fake_call
        self.server.parse_question_response = lambda response, debug=False: {
            "question": "请确认扩展规模",
            "options": ["100万", "500万", "1000万"],
            "multi_select": False,
            "is_follow_up": False,
            "follow_up_reason": None,
        }

        _response, result, tier_used = self.server.generate_question_with_tiered_strategy(
            "FULL_PROMPT",
            truncated_docs=[],
            fast_truncated_docs=["参考资料已压缩"],
            debug=False,
            base_call_type="question",
            allow_fast_path=True,
            fast_prompt="LIGHT_PROMPT",
            runtime_profile={
                "profile_name": "question_probe_reference_light",
                "selection_reason": "reference_light",
                "allow_fast_path": True,
                "fast_prompt_mode": "light",
                "fast_prompt_max_chars": 2600,
                "fast_allow_compacted_docs": True,
                "full_output_mode": "full",
                "fast_timeout": 8.0,
                "fast_max_tokens": 760,
                "full_timeout": 24.0,
                "full_max_tokens": 1200,
                "primary_lane": "question",
                "secondary_lane": "summary",
                "hedged_enabled": True,
                "hedge_delay_seconds": 1.0,
            },
        )

        self.assertEqual(calls[0]["call_type"], "question_fast")
        self.assertEqual(calls[0]["truncated_docs"], ["参考资料已压缩"])
        self.assertEqual(tier_used, "fast:question")
        self.assertEqual(result["question"], "请确认扩展规模")

    def test_smart_search_decision_uses_rule_only_mode_for_prefetch(self):
        self.server.ENABLE_WEB_SEARCH = True
        original_should_search = self.server.should_search
        original_ai_evaluate = self.server.ai_evaluate_search_need
        self.addCleanup(setattr, self.server, "should_search", original_should_search)
        self.addCleanup(setattr, self.server, "ai_evaluate_search_need", original_ai_evaluate)
        self.server.should_search = lambda *_args, **_kwargs: True

        ai_calls = []

        def _unexpected_ai(*_args, **_kwargs):
            ai_calls.append(True)
            return {"need_search": False, "reason": "unexpected", "search_query": ""}

        self.server.ai_evaluate_search_need = _unexpected_ai

        need_search, search_query, reason = self.server.smart_search_decision(
            "机加工艺方案评审",
            "target_architecture",
            {"topic": "机加工艺方案评审"},
            [],
            decision_mode="rule_only",
        )

        self.assertFalse(need_search)
        self.assertEqual(search_query, "")
        self.assertEqual(ai_calls, [])
        self.assertIn("预取降级", reason)
        stats = self.server.get_search_decision_stats_snapshot()
        self.assertEqual(stats["rule_only"], 1)

    def test_ai_search_decision_degrades_on_rate_limit_without_retry(self):
        self.server.ENABLE_WEB_SEARCH = True

        class _RateLimitedMessages:
            def __init__(self):
                self.calls = 0

            def create(self, **_kwargs):
                self.calls += 1
                raise RuntimeError("Error code: 429 Too Many Requests")

        ai_client = type("Client", (), {"messages": _RateLimitedMessages()})()
        original_resolve_ai_client = self.server.resolve_ai_client
        original_resolve_model_name = self.server.resolve_model_name
        self.addCleanup(setattr, self.server, "resolve_ai_client", original_resolve_ai_client)
        self.addCleanup(setattr, self.server, "resolve_model_name", original_resolve_model_name)
        self.server.resolve_ai_client = lambda call_type="search_decision": ai_client if call_type == "search_decision" else None
        self.server.resolve_model_name = lambda call_type="search_decision": "fake-search-decision-model"

        result = self.server.ai_evaluate_search_need(
            "机加工艺方案评审",
            "target_architecture",
            {"topic": "机加工艺方案评审"},
            [{"question": "Q1", "answer": "A1"}],
        )

        self.assertFalse(result["need_search"])
        self.assertIn("决策降级", result["reason"])
        self.assertEqual(ai_client.messages.calls, 1)
        stats = self.server.get_search_decision_stats_snapshot()
        self.assertEqual(stats["degraded"], 1)
        self.assertEqual(stats["degrade_reasons"].get("rate_limited"), 1)

    def test_prepare_runtime_disables_high_evidence_hedge_without_shadow_blocker(self):
        original_build = self.server.build_interview_prompt
        original_select = self.server._select_question_generation_runtime_profile
        original_refresh = self.server.refresh_session_evidence_ledger
        self.addCleanup(setattr, self.server, "build_interview_prompt", original_build)
        self.addCleanup(setattr, self.server, "_select_question_generation_runtime_profile", original_select)
        self.addCleanup(setattr, self.server, "refresh_session_evidence_ledger", original_refresh)

        self.server.build_interview_prompt = lambda *args, **kwargs: (
            "PROMPT:full",
            [],
            {"output_mode": "full", "answer_mode": "pick_with_reason", "requires_rationale": True, "evidence_intent": "high"},
        )
        self.server._select_question_generation_runtime_profile = lambda *args, **kwargs: {
            "profile_name": "question_probe_evidence",
            "selection_reason": "high_evidence_intent",
            "allow_fast_path": False,
            "fast_output_mode": "full",
            "full_output_mode": "full",
            "fast_timeout": 8.0,
            "fast_max_tokens": 640,
            "full_timeout": 24.0,
            "full_max_tokens": 1200,
            "primary_lane": "question",
            "secondary_lane": "report",
            "hedged_enabled": True,
            "fallback_enabled": True,
            "answer_mode": "pick_with_reason",
            "requires_rationale": True,
            "evidence_intent": "high",
        }
        self.server.refresh_session_evidence_ledger = lambda _session: {
            "shadow_draft": {
                "solutions": {"ready": False, "blocking_dimensions": ["other_dimension"], "readiness_score": 0.1},
            }
        }

        prepared = self.server._prepare_question_generation_runtime(
            session={"topic": "测试", "dimensions": {"project_constraints": {"items": []}}, "interview_log": []},
            dimension="project_constraints",
            all_dim_logs=[],
        )

        self.assertFalse(prepared["runtime_profile"]["hedged_enabled"])
        self.assertTrue(prepared["runtime_profile"]["fallback_enabled"])
        self.assertIn("hedge_blocked=no_shadow_blocker", prepared["runtime_profile"]["selection_reason"])

    def test_prepare_runtime_disables_hedge_when_budget_exhausted(self):
        original_build = self.server.build_interview_prompt
        original_select = self.server._select_question_generation_runtime_profile
        original_refresh = self.server.refresh_session_evidence_ledger
        self.addCleanup(setattr, self.server, "build_interview_prompt", original_build)
        self.addCleanup(setattr, self.server, "_select_question_generation_runtime_profile", original_select)
        self.addCleanup(setattr, self.server, "refresh_session_evidence_ledger", original_refresh)

        self.server.build_interview_prompt = lambda *args, **kwargs: (
            "PROMPT:full",
            [],
            {"output_mode": "full", "answer_mode": "pick_with_reason", "requires_rationale": True, "evidence_intent": "high"},
        )
        self.server._select_question_generation_runtime_profile = lambda *args, **kwargs: {
            "profile_name": "question_probe_evidence",
            "selection_reason": "high_evidence_intent",
            "allow_fast_path": False,
            "fast_output_mode": "full",
            "full_output_mode": "full",
            "fast_timeout": 8.0,
            "fast_max_tokens": 640,
            "full_timeout": 24.0,
            "full_max_tokens": 1200,
            "primary_lane": "question",
            "secondary_lane": "report",
            "hedged_enabled": True,
            "fallback_enabled": True,
            "answer_mode": "pick_with_reason",
            "requires_rationale": True,
            "evidence_intent": "high",
        }
        self.server.refresh_session_evidence_ledger = lambda _session: {
            "shadow_draft": {
                "actions": {"ready": False, "blocking_dimensions": ["project_constraints"], "readiness_score": 0.1},
            }
        }

        prepared = self.server._prepare_question_generation_runtime(
            session={
                "topic": "测试",
                "dimensions": {"project_constraints": {"items": []}},
                "interview_log": [{"dimension": "project_constraints", "question_hedge_triggered": True}],
            },
            dimension="project_constraints",
            all_dim_logs=[],
        )

        self.assertFalse(prepared["runtime_profile"]["hedged_enabled"])
        self.assertEqual(prepared["runtime_profile"]["hedge_budget"]["dimension_remaining"], 0)
        self.assertIn("hedge_blocked=budget_exhausted", prepared["runtime_profile"]["selection_reason"])

    def test_prepare_runtime_keeps_fast_hedge_for_reference_light_when_budget_exhausted(self):
        original_build = self.server.build_interview_prompt
        original_select = self.server._select_question_generation_runtime_profile
        original_refresh = self.server.refresh_session_evidence_ledger
        self.addCleanup(setattr, self.server, "build_interview_prompt", original_build)
        self.addCleanup(setattr, self.server, "_select_question_generation_runtime_profile", original_select)
        self.addCleanup(setattr, self.server, "refresh_session_evidence_ledger", original_refresh)

        def fake_build(*_args, output_mode="full", **_kwargs):
            return (
                f"PROMPT:{output_mode}",
                [],
                {
                    "output_mode": output_mode,
                    "answer_mode": "pick_with_reason",
                    "requires_rationale": True,
                    "evidence_intent": "high",
                    "has_search": False,
                    "has_reference_docs": True,
                },
            )

        self.server.build_interview_prompt = fake_build
        self.server._select_question_generation_runtime_profile = lambda *args, **kwargs: {
            "profile_name": "question_probe_reference_light",
            "selection_reason": "high_evidence_intent,reference_light",
            "allow_fast_path": True,
            "fast_output_mode": "light",
            "full_output_mode": "full",
            "fast_timeout": 15.0,
            "fast_max_tokens": 880,
            "full_timeout": 24.0,
            "full_max_tokens": 1200,
            "primary_lane": "question",
            "secondary_lane": "report",
            "hedged_enabled": True,
            "fallback_enabled": True,
            "answer_mode": "pick_with_reason",
            "requires_rationale": True,
            "evidence_intent": "high",
        }
        self.server.refresh_session_evidence_ledger = lambda _session: {
            "shadow_draft": {
                "target_architecture": {"ready": False, "blocking_dimensions": ["target_architecture"], "readiness_score": 0.1},
            }
        }

        prepared = self.server._prepare_question_generation_runtime(
            session={
                "topic": "测试",
                "dimensions": {"target_architecture": {"items": []}},
                "interview_log": [{"dimension": "target_architecture", "question_hedge_triggered": True}],
            },
            dimension="target_architecture",
            all_dim_logs=[],
        )

        self.assertTrue(prepared["runtime_profile"]["fast_hedged_enabled"])
        self.assertFalse(prepared["runtime_profile"]["full_hedged_enabled"])
        self.assertTrue(prepared["runtime_profile"]["hedged_enabled"])
        self.assertIn("fast_hedge_budget_bypass=reference_light", prepared["runtime_profile"]["selection_reason"])

    def test_generate_question_uses_fast_prompt_and_runtime_profile(self):
        calls = []
        original_call = self.server._call_question_with_optional_hedge
        original_parse = self.server.parse_question_response
        self.addCleanup(setattr, self.server, "_call_question_with_optional_hedge", original_call)
        self.addCleanup(setattr, self.server, "parse_question_response", original_parse)

        def fake_call(prompt, max_tokens, call_type, truncated_docs=None, timeout=None, retry_on_timeout=False, debug=False, **kwargs):
            calls.append({
                "prompt": prompt,
                "max_tokens": max_tokens,
                "call_type": call_type,
                "timeout": timeout,
                "kwargs": kwargs,
            })
            return (
                '{"question":"请确认最核心诉求？","options":["效率","成本","体验"],"multi_select":false,"is_follow_up":false,"follow_up_reason":null}',
                kwargs.get("primary_lane", "question"),
                {"response_length": 88},
            )

        self.server._call_question_with_optional_hedge = fake_call
        self.server.parse_question_response = lambda response, debug=False: {
            "question": "请确认最核心诉求？",
            "options": ["效率", "成本", "体验"],
            "multi_select": False,
            "is_follow_up": False,
            "follow_up_reason": None,
        }

        response, result, tier_used = self.server.generate_question_with_tiered_strategy(
            "FULL_PROMPT",
            truncated_docs=[],
            debug=False,
            base_call_type="question",
            allow_fast_path=True,
            fast_prompt="LIGHT_PROMPT",
            runtime_profile={
                "profile_name": "question_follow_up_light",
                "selection_reason": "follow_up",
                "allow_fast_path": True,
                "fast_prompt_mode": "light",
                "full_prompt_mode": "full",
                "fast_timeout": 8.0,
                "fast_max_tokens": 640,
                "full_timeout": 24.0,
                "full_max_tokens": 1200,
                "primary_lane": "question",
                "secondary_lane": "summary",
                "hedged_enabled": True,
                "hedge_delay_seconds": 1.0,
            },
        )

        self.assertEqual(calls[0]["prompt"], "LIGHT_PROMPT")
        self.assertEqual(calls[0]["max_tokens"], 640)
        self.assertEqual(calls[0]["call_type"], "question_fast")
        self.assertEqual(calls[0]["kwargs"]["secondary_lane"], "summary")
        self.assertEqual(tier_used, "fast:question")
        self.assertEqual(result["question"], "请确认最核心诉求？")
        self.assertFalse(result["question_hedge_triggered"])
        self.assertFalse(result["question_fallback_triggered"])
        self.assertIn("question", response)

    def test_generate_question_splits_fast_and_full_hedge_flags(self):
        calls = []
        original_call = self.server._call_question_with_optional_hedge
        original_parse = self.server.parse_question_response
        self.addCleanup(setattr, self.server, "_call_question_with_optional_hedge", original_call)
        self.addCleanup(setattr, self.server, "parse_question_response", original_parse)

        def fake_call(prompt, max_tokens, call_type, truncated_docs=None, timeout=None, retry_on_timeout=False, debug=False, **kwargs):
            calls.append({
                "call_type": call_type,
                "hedged_enabled": kwargs.get("hedged_enabled"),
                "primary_lane": kwargs.get("primary_lane"),
            })
            if call_type == "question_fast":
                return None, "question", {
                    "attempts": [{"lane": "question", "success": False, "failure_reason": "timeout", "timeout_occurred": True, "timeout_seconds": timeout}],
                }
            return (
                '{"question":"请确认系统边界","options":["内部系统","协同平台","供应商接口"],"multi_select":true,"is_follow_up":false,"follow_up_reason":null}',
                kwargs.get("primary_lane", "question"),
                {"response_length": 66},
            )

        self.server._call_question_with_optional_hedge = fake_call
        self.server.parse_question_response = lambda response, debug=False: {
            "question": "请确认系统边界",
            "options": ["内部系统", "协同平台", "供应商接口"],
            "multi_select": True,
            "is_follow_up": False,
            "follow_up_reason": None,
        } if response else None

        _response, result, tier_used = self.server.generate_question_with_tiered_strategy(
            "FULL_PROMPT",
            truncated_docs=[],
            debug=False,
            base_call_type="question",
            allow_fast_path=True,
            fast_prompt="LIGHT_PROMPT",
            runtime_profile={
                "profile_name": "question_probe_reference_light",
                "selection_reason": "high_evidence_intent,reference_light,fast_hedge_budget_bypass=reference_light",
                "allow_fast_path": True,
                "fast_prompt_mode": "light",
                "full_prompt_mode": "full",
                "fast_timeout": 15.0,
                "fast_max_tokens": 880,
                "full_timeout": 24.0,
                "full_max_tokens": 1200,
                "primary_lane": "question",
                "secondary_lane": "report",
                "hedged_enabled": True,
                "fast_hedged_enabled": True,
                "full_hedged_enabled": False,
                "fallback_enabled": True,
                "hedge_delay_seconds": 1.0,
            },
        )

        self.assertEqual([item["call_type"] for item in calls], ["question_fast", "question"])
        self.assertTrue(calls[0]["hedged_enabled"])
        self.assertFalse(calls[1]["hedged_enabled"])
        self.assertEqual(tier_used, "full:question")
        self.assertEqual(result["question"], "请确认系统边界")

    def test_reference_light_runtime_overrides_apply_question_and_report_lanes(self):
        overrides = self.server._apply_reference_light_lane_runtime_overrides(
            {},
            {},
            base_fast_timeout=12.0,
            max_tokens_ceiling=1600,
            is_prefetch=False,
        )

        timeout_by_lane, max_tokens_by_lane, effective_timeout, effective_tokens = overrides
        self.assertEqual(effective_timeout, 15.0)
        self.assertEqual(effective_tokens, 1000)
        self.assertEqual(timeout_by_lane["question"], 15.0)
        self.assertEqual(timeout_by_lane["report"], 14.0)
        self.assertEqual(max_tokens_by_lane["question"], 1000)
        self.assertEqual(max_tokens_by_lane["report"], 1100)

    def test_generate_question_uses_fast_truncated_docs_instead_of_full_prompt_truncation(self):
        calls = []
        original_call = self.server._call_question_with_optional_hedge
        original_parse = self.server.parse_question_response
        self.addCleanup(setattr, self.server, "_call_question_with_optional_hedge", original_call)
        self.addCleanup(setattr, self.server, "parse_question_response", original_parse)

        def fake_call(prompt, max_tokens, call_type, truncated_docs=None, timeout=None, retry_on_timeout=False, debug=False, **kwargs):
            calls.append({
                "prompt": prompt,
                "truncated_docs": list(truncated_docs or []),
                "call_type": call_type,
            })
            return (
                '{"question":"请确认最核心诉求？","options":["效率","成本","体验"],"multi_select":false,"is_follow_up":false,"follow_up_reason":null}',
                "question",
                {"response_length": 88},
            )

        self.server._call_question_with_optional_hedge = fake_call
        self.server.parse_question_response = lambda response, debug=False: {
            "question": "请确认最核心诉求？",
            "options": ["效率", "成本", "体验"],
            "multi_select": False,
            "is_follow_up": False,
            "follow_up_reason": None,
        }

        response, result, tier_used = self.server.generate_question_with_tiered_strategy(
            "FULL_PROMPT",
            truncated_docs=["完整资料被截断"],
            fast_truncated_docs=[],
            debug=False,
            base_call_type="question",
            allow_fast_path=True,
            fast_prompt="L" * 2200,
            runtime_profile={
                "profile_name": "question_probe_reference_light",
                "selection_reason": "reference_light",
                "allow_fast_path": True,
                "fast_prompt_mode": "light",
                "fast_prompt_max_chars": 2600,
                "full_prompt_mode": "full",
                "fast_timeout": 8.0,
                "fast_max_tokens": 760,
                "full_timeout": 24.0,
                "full_max_tokens": 1200,
                "primary_lane": "question",
                "secondary_lane": "summary",
                "hedged_enabled": True,
                "hedge_delay_seconds": 1.0,
            },
        )

        self.assertEqual(calls[0]["call_type"], "question_fast")
        self.assertEqual(calls[0]["truncated_docs"], [])
        self.assertEqual(tier_used, "fast:question")
        self.assertEqual(result["question"], "请确认最核心诉求？")
        self.assertIn("question", response)

    def test_generate_question_uses_secondary_fallback_for_high_evidence_primary_failure(self):
        calls = []
        original_call = self.server._call_question_with_optional_hedge
        original_parse = self.server.parse_question_response
        self.addCleanup(setattr, self.server, "_call_question_with_optional_hedge", original_call)
        self.addCleanup(setattr, self.server, "parse_question_response", original_parse)

        def fake_call(prompt, max_tokens, call_type, truncated_docs=None, timeout=None, retry_on_timeout=False, debug=False, **kwargs):
            calls.append({
                "call_type": call_type,
                "primary_lane": kwargs.get("primary_lane"),
                "secondary_lane": kwargs.get("secondary_lane"),
                "hedged_enabled": kwargs.get("hedged_enabled"),
            })
            if call_type == "question":
                return None, "question", {"attempts": [{"lane": "question", "success": False}]}
            return (
                '{"question":"请补充关键成熟度判断","options":["稳定性","成本","生态"],"multi_select":true,"is_follow_up":false,"follow_up_reason":null}',
                "report",
                {"attempts": [{"lane": "report", "success": True}], "response_length": 60},
            )

        self.server._call_question_with_optional_hedge = fake_call
        self.server.parse_question_response = lambda response, debug=False: {
            "question": "请补充关键成熟度判断",
            "options": ["稳定性", "成本", "生态"],
            "multi_select": True,
            "is_follow_up": False,
            "follow_up_reason": None,
        } if response else None

        response, result, tier_used = self.server.generate_question_with_tiered_strategy(
            "FULL_PROMPT",
            truncated_docs=[],
            debug=False,
            base_call_type="question",
            allow_fast_path=False,
            fast_prompt="FULL_PROMPT",
            runtime_profile={
                "profile_name": "question_probe_evidence",
                "selection_reason": "high_evidence_intent",
                "allow_fast_path": False,
                "fast_prompt_mode": "full",
                "full_prompt_mode": "full",
                "full_timeout": 24.0,
                "full_max_tokens": 1200,
                "primary_lane": "question",
                "secondary_lane": "report",
                "hedged_enabled": False,
                "fallback_enabled": True,
                "hedge_delay_seconds": 1.0,
                "answer_mode": "pick_with_reason",
                "requires_rationale": True,
                "evidence_intent": "high",
            },
        )

        self.assertEqual([item["call_type"] for item in calls], ["question", "question_fallback"])
        self.assertEqual(calls[1]["primary_lane"], "report")
        self.assertFalse(calls[1]["hedged_enabled"])
        self.assertEqual(tier_used, "full_fallback:report")
        self.assertTrue(result["question_fallback_triggered"])
        self.assertFalse(result["question_hedge_triggered"])
        self.assertEqual(result["question"], "请补充关键成熟度判断")
        self.assertIn("report", tier_used)

    def test_dynamic_lane_order_promotes_better_lane(self):
        runtime_profile = {
            "profile_name": "question_follow_up_light",
            "fast_prompt_mode": "light",
            "full_prompt_mode": "full",
            "primary_lane": "question",
            "secondary_lane": "summary",
        }
        strategy_key = self.server._build_question_lane_strategy_key(runtime_profile, "fast")

        for _ in range(3):
            self.server._record_question_lane_strategy_outcome(
                strategy_key,
                "question",
                "ok",
                {"response_time_ms": 900.0, "queue_wait_ms": 50.0},
            )
            self.server._record_question_lane_strategy_outcome(
                strategy_key,
                "summary",
                "ok",
                {"response_time_ms": 180.0, "queue_wait_ms": 10.0},
            )

        primary_lane, secondary_lane, lane_meta = self.server._resolve_dynamic_question_lane_order(runtime_profile, phase="fast")
        self.assertEqual(primary_lane, "summary")
        self.assertEqual(secondary_lane, "question")
        self.assertIn("summary", lane_meta["ordered_candidates"])

    def test_generate_question_uses_dynamic_lane_order(self):
        runtime_profile = {
            "profile_name": "question_follow_up_light",
            "selection_reason": "follow_up",
            "allow_fast_path": True,
            "fast_prompt_mode": "light",
            "full_prompt_mode": "full",
            "fast_timeout": 8.0,
            "fast_max_tokens": 640,
            "full_timeout": 24.0,
            "full_max_tokens": 1200,
            "primary_lane": "question",
            "secondary_lane": "summary",
            "hedged_enabled": True,
            "hedge_delay_seconds": 1.0,
        }
        strategy_key = self.server._build_question_lane_strategy_key(runtime_profile, "fast")
        for _ in range(3):
            self.server._record_question_lane_strategy_outcome(
                strategy_key,
                "question",
                None,
                {"response_time_ms": 1100.0, "failure_reason": "timeout"},
            )
            self.server._record_question_lane_strategy_outcome(
                strategy_key,
                "summary",
                "ok",
                {"response_time_ms": 220.0},
            )

        calls = []
        original_call = self.server._call_question_with_optional_hedge
        original_parse = self.server.parse_question_response
        self.addCleanup(setattr, self.server, "_call_question_with_optional_hedge", original_call)
        self.addCleanup(setattr, self.server, "parse_question_response", original_parse)

        def fake_call(prompt, max_tokens, call_type, truncated_docs=None, timeout=None, retry_on_timeout=False, debug=False, **kwargs):
            calls.append(kwargs)
            return (
                '{"question":"请继续说明最关键诉求","options":["效率","成本","体验"],"multi_select":false,"is_follow_up":false,"follow_up_reason":null}',
                kwargs.get("primary_lane", "question"),
                {"response_length": 88},
            )

        self.server._call_question_with_optional_hedge = fake_call
        self.server.parse_question_response = lambda response, debug=False: {
            "question": "请继续说明最关键诉求",
            "options": ["效率", "成本", "体验"],
            "multi_select": False,
            "is_follow_up": False,
            "follow_up_reason": None,
        }

        response, result, tier_used = self.server.generate_question_with_tiered_strategy(
            "FULL_PROMPT",
            truncated_docs=[],
            debug=False,
            base_call_type="question",
            allow_fast_path=True,
            fast_prompt="LIGHT_PROMPT",
            runtime_profile=runtime_profile,
        )

        self.assertEqual(calls[0]["primary_lane"], "summary")
        self.assertEqual(calls[0]["secondary_lane"], "question")
        self.assertEqual(tier_used, "fast:summary")
        self.assertEqual(result["question"], "请继续说明最关键诉求")
        self.assertIn("question", response)

    def test_generate_question_applies_lane_specific_runtime_params(self):
        self.server.QUESTION_FAST_TIMEOUT_BY_LANE = {"summary": 7.0}
        self.server.QUESTION_FAST_MAX_TOKENS_BY_LANE = {"summary": 580}
        self.server.QUESTION_HEDGE_DELAY_BY_LANE = {"summary": 0.8}

        runtime_profile = {
            "profile_name": "question_follow_up_light",
            "selection_reason": "follow_up",
            "allow_fast_path": True,
            "fast_prompt_mode": "light",
            "full_prompt_mode": "full",
            "fast_timeout": 8.0,
            "fast_max_tokens": 640,
            "full_timeout": 24.0,
            "full_max_tokens": 1200,
            "primary_lane": "question",
            "secondary_lane": "summary",
            "hedged_enabled": True,
            "hedge_delay_seconds": 1.0,
        }
        strategy_key = self.server._build_question_lane_strategy_key(runtime_profile, "fast")
        for _ in range(3):
            self.server._record_question_lane_strategy_outcome(
                strategy_key,
                "question",
                None,
                {"response_time_ms": 1100.0, "failure_reason": "timeout"},
            )
            self.server._record_question_lane_strategy_outcome(
                strategy_key,
                "summary",
                "ok",
                {"response_time_ms": 220.0},
            )

        calls = []
        original_call = self.server._call_question_with_optional_hedge
        original_parse = self.server.parse_question_response
        self.addCleanup(setattr, self.server, "_call_question_with_optional_hedge", original_call)
        self.addCleanup(setattr, self.server, "parse_question_response", original_parse)

        def fake_call(prompt, max_tokens, call_type, truncated_docs=None, timeout=None, retry_on_timeout=False, debug=False, **kwargs):
            calls.append({
                "max_tokens": max_tokens,
                "timeout": timeout,
                "kwargs": kwargs,
            })
            return (
                '{"question":"请继续说明最关键诉求","options":["效率","成本","体验"],"multi_select":false,"is_follow_up":false,"follow_up_reason":null}',
                kwargs.get("primary_lane", "question"),
                {"response_length": 88},
            )

        self.server._call_question_with_optional_hedge = fake_call
        self.server.parse_question_response = lambda response, debug=False: {
            "question": "请继续说明最关键诉求",
            "options": ["效率", "成本", "体验"],
            "multi_select": False,
            "is_follow_up": False,
            "follow_up_reason": None,
        }

        _response, _result, tier_used = self.server.generate_question_with_tiered_strategy(
            "FULL_PROMPT",
            truncated_docs=[],
            debug=False,
            base_call_type="question",
            allow_fast_path=True,
            fast_prompt="LIGHT_PROMPT",
            runtime_profile=runtime_profile,
        )

        self.assertEqual(calls[0]["kwargs"]["primary_lane"], "summary")
        self.assertEqual(calls[0]["timeout"], 7.0)
        self.assertEqual(calls[0]["max_tokens"], 580)
        self.assertEqual(calls[0]["kwargs"]["hedge_delay_seconds"], 0.8)
        self.assertEqual(tier_used, "fast:summary")

    def test_call_question_hedge_uses_secondary_lane_runtime_params(self):
        records = []
        original_call = self.server.call_claude
        original_resolve = self.server.resolve_ai_client
        self.addCleanup(setattr, self.server, "call_claude", original_call)
        self.addCleanup(setattr, self.server, "resolve_ai_client", original_resolve)

        clients = {
            "summary": object(),
            "question": object(),
        }

        self.server.resolve_ai_client = lambda call_type="", model_name="", preferred_lane="": clients.get(preferred_lane)

        def fake_call(prompt, max_tokens=None, retry_on_timeout=True, call_type="unknown", truncated_docs=None,
                      timeout=None, model_name="", preferred_lane="", hedge_triggered=False,
                      cache_hit=False, return_meta=False):
            records.append({
                "lane": preferred_lane,
                "timeout": timeout,
                "max_tokens": max_tokens,
                "call_type": call_type,
            })
            if preferred_lane == "summary":
                time.sleep(0.12)
                payload = None
            else:
                payload = '{"question":"请补充说明最关键诉求","options":["效率","成本","体验"],"multi_select":false,"is_follow_up":false,"follow_up_reason":null}'
            meta = {
                "selected_lane": preferred_lane,
                "timeout_seconds": timeout,
                "max_tokens": max_tokens,
            }
            return (payload, meta) if return_meta else payload

        self.server.call_claude = fake_call

        response, lane, meta = self.server._call_question_with_optional_hedge(
            "PROMPT",
            max_tokens=580,
            call_type="question_fast",
            timeout=0.3,
            retry_on_timeout=False,
            debug=False,
            primary_lane="summary",
            secondary_lane="question",
            hedged_enabled=True,
            hedge_delay_seconds=0.05,
            lane_runtime_overrides={
                "summary": {"timeout": 0.3, "max_tokens": 580},
                "question": {"timeout": 0.8, "max_tokens": 960},
            },
        )

        self.assertEqual(lane, "question")
        self.assertIsNotNone(response)
        calls_by_lane = {item["lane"]: item for item in records}
        self.assertEqual(calls_by_lane["summary"]["timeout"], 0.3)
        self.assertEqual(calls_by_lane["summary"]["max_tokens"], 580)
        self.assertEqual(calls_by_lane["question"]["timeout"], 0.8)
        self.assertEqual(calls_by_lane["question"]["max_tokens"], 960)
        attempts = meta.get("attempts", [])
        self.assertEqual(len(attempts), 2)

    def test_question_primary_hedge_delay_adds_grace_window(self):
        self.assertEqual(
            self.server._resolve_question_hedge_trigger_delay(1.0, "question", 8.0),
            2.5,
        )
        self.assertEqual(
            self.server._resolve_question_hedge_trigger_delay(1.0, "question", 24.0),
            3.0,
        )
        self.assertEqual(
            self.server._resolve_question_hedge_trigger_delay(1.0, "summary", 8.0),
            1.0,
        )

    def test_question_hedge_delay_uses_latency_percentile_when_ready(self):
        runtime_profile = {
            "profile_name": "question_follow_up_light",
            "fast_prompt_mode": "light",
            "full_prompt_mode": "full",
            "primary_lane": "question",
            "secondary_lane": "summary",
        }
        strategy_key = self.server._build_question_lane_strategy_key(runtime_profile, "fast")
        for latency in [2600.0, 3000.0, 3400.0]:
            self.server._record_question_lane_strategy_outcome(
                strategy_key,
                "question",
                "ok",
                {"response_time_ms": latency},
            )

        self.assertEqual(
            self.server._compute_question_lane_latency_percentile_ms(strategy_key, "question"),
            3400.0,
        )
        self.assertEqual(
            self.server._resolve_question_hedge_trigger_delay(1.0, "question", 12.0, lane_profile_name=strategy_key),
            3.4,
        )


    def test_prefetch_runtime_profile_uses_independent_params(self):
        self.server.QUESTION_FAST_TIMEOUT = 7.0
        self.server.QUESTION_FAST_MAX_TOKENS = 520
        self.server.QUESTION_HEDGED_DELAY_SECONDS = 0.9

        profile = self.server._select_question_generation_runtime_profile(
            "轻量 prompt",
            truncated_docs=[],
            decision_meta={"formal_questions_count": 0},
            base_call_type="prefetch",
            allow_fast_path=True,
        )

        self.assertEqual(profile["profile_name"], "prefetch_balanced_light")
        self.assertTrue(profile["allow_fast_path"])
        self.assertEqual(profile["primary_lane"], "summary")
        self.assertEqual(profile["secondary_lane"], "question")
        self.assertEqual(profile["fast_timeout"], 10.5)
        self.assertEqual(profile["fast_max_tokens"], 760)
        self.assertEqual(profile["full_timeout"], 48.0)
        self.assertEqual(profile["full_max_tokens"], 1200)
        self.assertEqual(profile["hedge_delay_seconds"], 2.4)
        self.assertEqual(profile["fast_timeout_by_lane"], {})
        self.assertEqual(profile["full_timeout_by_lane"], {})
        self.assertEqual(profile["hedge_delay_by_lane"], {})

    def test_prefetch_first_runtime_profile_uses_prefetch_route(self):
        profile = self.server._select_question_generation_runtime_profile(
            "首题轻量 prompt",
            truncated_docs=[],
            decision_meta={"formal_questions_count": 0},
            base_call_type="prefetch_first",
            allow_fast_path=True,
        )

        self.assertEqual(profile["profile_name"], "prefetch_first_balanced_light")
        self.assertEqual(profile["primary_lane"], "summary")
        self.assertEqual(profile["secondary_lane"], "question")
        self.assertEqual(profile["full_timeout"], 48.0)
        self.assertEqual(profile["full_max_tokens"], 1200)

    def test_generate_prefetch_question_keeps_background_runtime_isolation(self):
        self.server.QUESTION_FAST_TIMEOUT_BY_LANE = {"summary": 7.0}
        self.server.QUESTION_FAST_MAX_TOKENS_BY_LANE = {"summary": 580}
        self.server.QUESTION_HEDGE_DELAY_BY_LANE = {"summary": 0.8}

        runtime_profile = self.server._select_question_generation_runtime_profile(
            "轻量 prompt",
            truncated_docs=[],
            decision_meta={"formal_questions_count": 0},
            base_call_type="prefetch",
            allow_fast_path=True,
        )

        calls = []
        original_call = self.server._call_question_with_optional_hedge
        original_parse = self.server.parse_question_response
        self.addCleanup(setattr, self.server, "_call_question_with_optional_hedge", original_call)
        self.addCleanup(setattr, self.server, "parse_question_response", original_parse)

        def fake_call(prompt, max_tokens, call_type, truncated_docs=None, timeout=None, retry_on_timeout=False, debug=False, **kwargs):
            calls.append({
                "max_tokens": max_tokens,
                "timeout": timeout,
                "call_type": call_type,
                "kwargs": kwargs,
            })
            return (
                '{"question":"后台预生成问题","options":["效率","成本","体验"],"multi_select":false,"is_follow_up":false,"follow_up_reason":null}',
                kwargs.get("primary_lane", "summary"),
                {"response_length": 66},
            )

        self.server._call_question_with_optional_hedge = fake_call
        self.server.parse_question_response = lambda response, debug=False: {
            "question": "后台预生成问题",
            "options": ["效率", "成本", "体验"],
            "multi_select": False,
            "is_follow_up": False,
            "follow_up_reason": None,
        }

        _response, _result, tier_used = self.server.generate_question_with_tiered_strategy(
            "FULL_PREFETCH_PROMPT",
            truncated_docs=[],
            debug=False,
            base_call_type="prefetch",
            allow_fast_path=True,
            fast_prompt="LIGHT_PREFETCH_PROMPT",
            runtime_profile=runtime_profile,
        )

        self.assertEqual(calls[0]["call_type"], "prefetch_fast")
        self.assertEqual(calls[0]["kwargs"]["primary_lane"], "summary")
        self.assertEqual(calls[0]["timeout"], 10.5)
        self.assertEqual(calls[0]["max_tokens"], 760)
        self.assertEqual(calls[0]["kwargs"]["hedge_delay_seconds"], 2.4)
        self.assertEqual(tier_used, "fast:summary")

    def test_trigger_prefetch_if_needed_uses_tiered_runtime(self):
        session_id = "prefetch-session"
        session_payload = {
            "session_id": session_id,
            "topic": "测试主题",
            "interview_log": [
                {"dimension": "customer_needs", "question": "Q1", "answer": "A1", "is_follow_up": False},
                {"dimension": "customer_needs", "question": "Q2", "answer": "A2", "is_follow_up": False},
            ],
        }

        runtime_profile = {
            "profile_name": "prefetch_balanced_light",
            "selection_reason": "prefetch_balanced_light",
            "allow_fast_path": True,
            "fast_prompt_mode": "light",
            "full_prompt_mode": "full",
            "fast_timeout": 10.5,
            "fast_max_tokens": 760,
            "full_timeout": 48.0,
            "full_max_tokens": 1200,
            "primary_lane": "summary",
            "secondary_lane": "question",
            "hedged_enabled": True,
            "hedge_delay_seconds": 2.4,
            "fast_timeout_by_lane": {},
            "fast_max_tokens_by_lane": {},
            "full_timeout_by_lane": {},
            "full_max_tokens_by_lane": {},
            "hedge_delay_by_lane": {},
        }
        prepare_calls = []
        generate_calls = []

        original_wait = self.server._wait_for_prefetch_idle
        original_prepare = self.server._prepare_question_generation_runtime
        original_generate = self.server.generate_question_with_tiered_strategy
        original_mode = self.server.get_interview_mode_config
        original_order = self.server.get_dimension_order_for_session
        original_thread = self.server.threading.Thread
        self.addCleanup(setattr, self.server, "_wait_for_prefetch_idle", original_wait)
        self.addCleanup(setattr, self.server, "_prepare_question_generation_runtime", original_prepare)
        self.addCleanup(setattr, self.server, "generate_question_with_tiered_strategy", original_generate)
        self.addCleanup(setattr, self.server, "get_interview_mode_config", original_mode)
        self.addCleanup(setattr, self.server, "get_dimension_order_for_session", original_order)
        self.addCleanup(setattr, self.server.threading, "Thread", original_thread)

        self.server._wait_for_prefetch_idle = lambda _seconds: True
        self.server.get_interview_mode_config = lambda _session: {"formal_questions_per_dim": 2}
        self.server.get_dimension_order_for_session = lambda _session: ["customer_needs", "business_process", "tech_constraints"]

        def fake_prepare(session, dimension, all_dim_logs, session_id=None, session_signature=None, base_call_type="question", allow_fast_path=True):
            prepare_calls.append({
                "dimension": dimension,
                "base_call_type": base_call_type,
                "allow_fast_path": allow_fast_path,
                "log_count": len(all_dim_logs),
            })
            return {
                "full_prompt": "FULL_PREFETCH_PROMPT",
                "fast_prompt": "LIGHT_PREFETCH_PROMPT",
                "truncated_docs": [],
                "decision_meta": {"runtime_profile": "prefetch_balanced_light"},
                "runtime_profile": dict(runtime_profile),
            }

        def fake_generate(
            prompt,
            truncated_docs=None,
            fast_truncated_docs=None,
            debug=False,
            base_call_type="question",
            allow_fast_path=True,
            fast_prompt=None,
            runtime_profile=None,
        ):
            generate_calls.append({
                "prompt": prompt,
                "truncated_docs": list(truncated_docs or []),
                "fast_truncated_docs": list(fast_truncated_docs or []),
                "base_call_type": base_call_type,
                "allow_fast_path": allow_fast_path,
                "fast_prompt": fast_prompt,
                "runtime_profile": dict(runtime_profile or {}),
            })
            return (
                '{"question":"后台预生成问题"}',
                {
                    "question": "后台预生成问题",
                    "options": ["效率", "成本", "体验"],
                    "multi_select": False,
                    "is_follow_up": False,
                    "follow_up_reason": None,
                },
                "fast:summary",
            )

        class ImmediateThread:
            def __init__(self, target=None, args=(), kwargs=None, daemon=None, name=None):
                self._target = target
                self._args = args
                self._kwargs = kwargs or {}

            def start(self):
                if self._target:
                    self._target(*self._args, **self._kwargs)

        self.server._prepare_question_generation_runtime = fake_prepare
        self.server.generate_question_with_tiered_strategy = fake_generate
        self.server.threading.Thread = ImmediateThread

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            session_file = tmpdir_path / f"{session_id}.json"
            session_file.write_text(json.dumps(session_payload, ensure_ascii=False), encoding="utf-8")
            with mock.patch.object(self.server, "SESSIONS_DIR", tmpdir_path):
                self.server.trigger_prefetch_if_needed(session_payload, "customer_needs")

        self.assertEqual(len(prepare_calls), 1)
        self.assertEqual(prepare_calls[0]["dimension"], "business_process")
        self.assertEqual(prepare_calls[0]["base_call_type"], "prefetch")
        self.assertTrue(prepare_calls[0]["allow_fast_path"])
        self.assertEqual(len(generate_calls), 1)
        self.assertEqual(generate_calls[0]["base_call_type"], "prefetch")
        self.assertEqual(generate_calls[0]["fast_prompt"], "LIGHT_PREFETCH_PROMPT")
        with self.server.prefetch_cache_lock:
            cached = self.server.prefetch_cache.get(session_id, {}).get("business_process")
        self.assertIsNotNone(cached)
        self.assertEqual(cached["question_data"]["question"], "后台预生成问题")

    def test_generate_question_auto_corrects_plural_enumeration_to_multi_select(self):
        original_call = self.server._call_question_with_optional_hedge
        original_parse = self.server.parse_question_response
        self.addCleanup(setattr, self.server, "_call_question_with_optional_hedge", original_call)
        self.addCleanup(setattr, self.server, "parse_question_response", original_parse)

        self.server._call_question_with_optional_hedge = lambda *args, **kwargs: (
            '{"question":"需要与哪些现有系统集成？","options":["ERP系统","CRM系统","OA办公系统"],"multi_select":false,"is_follow_up":false,"follow_up_reason":null}',
            "summary",
            {"response_length": 96},
        )
        self.server.parse_question_response = lambda _response, debug=False: {
            "question": "需要与哪些现有系统集成？",
            "options": ["ERP系统", "CRM系统", "OA办公系统"],
            "multi_select": False,
            "is_follow_up": False,
            "follow_up_reason": None,
        }

        _response, result, tier_used = self.server.generate_question_with_tiered_strategy(
            "PROMPT",
            truncated_docs=[],
            debug=False,
            base_call_type="question",
            allow_fast_path=False,
        )

        self.assertEqual(tier_used, "full:summary")
        self.assertFalse(result["question_multi_select"])
        self.assertTrue(result["multi_select"])

    def test_generate_question_keeps_single_select_for_unique_priority_prompt(self):
        original_call = self.server._call_question_with_optional_hedge
        original_parse = self.server.parse_question_response
        self.addCleanup(setattr, self.server, "_call_question_with_optional_hedge", original_call)
        self.addCleanup(setattr, self.server, "parse_question_response", original_parse)

        self.server._call_question_with_optional_hedge = lambda *args, **kwargs: (
            '{"question":"当前最优先解决的问题是什么？","options":["效率","成本","体验"],"multi_select":false,"is_follow_up":false,"follow_up_reason":null}',
            "summary",
            {"response_length": 88},
        )
        self.server.parse_question_response = lambda _response, debug=False: {
            "question": "当前最优先解决的问题是什么？",
            "options": ["效率", "成本", "体验"],
            "multi_select": False,
            "is_follow_up": False,
            "follow_up_reason": None,
        }

        _response, result, _tier_used = self.server.generate_question_with_tiered_strategy(
            "PROMPT",
            truncated_docs=[],
            debug=False,
            base_call_type="question",
            allow_fast_path=False,
        )

        self.assertFalse(result["question_multi_select"])
        self.assertFalse(result["multi_select"])


if __name__ == "__main__":
    unittest.main()
