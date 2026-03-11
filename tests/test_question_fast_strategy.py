import importlib.util
import json
import sys
import tempfile
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
        self.server.QUESTION_FAST_TIMEOUT = 12.0
        self.server.QUESTION_FAST_MAX_TOKENS = 1000
        self.server.QUESTION_FAST_LIGHT_PROMPT_MAX_CHARS = 1800
        self.server.QUESTION_FAST_SKIP_WHEN_TRUNCATED_DOCS = True
        self.server.QUESTION_FAST_ADAPTIVE_ENABLED = True
        self.server.QUESTION_FAST_ADAPTIVE_WINDOW_SIZE = 4
        self.server.QUESTION_FAST_ADAPTIVE_MIN_SAMPLES = 4
        self.server.QUESTION_FAST_ADAPTIVE_MIN_HIT_RATE = 0.5
        self.server.QUESTION_FAST_ADAPTIVE_COOLDOWN_SECONDS = 600.0
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
        self.server.PREFETCH_QUESTION_TIMEOUT = 48.0
        self.server.PREFETCH_QUESTION_MAX_TOKENS = 1200
        self.server.PREFETCH_QUESTION_FAST_TIMEOUT = 10.5
        self.server.PREFETCH_QUESTION_FAST_MAX_TOKENS = 760
        self.server.PREFETCH_QUESTION_HEDGE_DELAY_SECONDS = 2.4
        self.server.PREFETCH_QUESTION_PRIMARY_LANE = "summary"
        self.server.PREFETCH_QUESTION_SECONDARY_LANE = "question"
        self.server.MAX_TOKENS_QUESTION = 1600
        self.server.API_TIMEOUT = 90.0
        self.server.reset_question_fast_strategy_state()
        self.server.reset_question_lane_strategy_state()
        with self.server.prefetch_cache_lock:
            self.server.prefetch_cache.clear()

    def test_skip_reason_when_prompt_too_long(self):
        reason = self.server._get_question_fast_skip_reason("x" * 1900, truncated_docs=[])
        self.assertEqual(reason, "prompt_too_long:1900>1800")

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

    def test_prepare_runtime_builds_light_prompt_variant(self):
        calls = []
        original_build = self.server.build_interview_prompt
        original_select = self.server._select_question_generation_runtime_profile
        self.addCleanup(setattr, self.server, "build_interview_prompt", original_build)
        self.addCleanup(setattr, self.server, "_select_question_generation_runtime_profile", original_select)

        def fake_build(session, dimension, all_dim_logs, session_id=None, session_signature=None, output_mode="full"):
            calls.append(output_mode)
            return (
                f"PROMPT:{output_mode}",
                [],
                {
                    "output_mode": output_mode,
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
        self.assertIn("question", response)

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

        def fake_generate(prompt, truncated_docs=None, debug=False, base_call_type="question", allow_fast_path=True, fast_prompt=None, runtime_profile=None):
            generate_calls.append({
                "prompt": prompt,
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
