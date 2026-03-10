import importlib.util
import sys
import types
import unittest
from pathlib import Path


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
        self.server.MAX_TOKENS_QUESTION = 1600
        self.server.API_TIMEOUT = 90.0
        self.server.reset_question_fast_strategy_state()

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

        def fake_call(prompt, max_tokens, call_type, truncated_docs=None, timeout=None, retry_on_timeout=False, debug=False):
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


if __name__ == "__main__":
    unittest.main()
