import importlib.util
import os
import sys
import tempfile
import types
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch


ROOT_DIR = Path(__file__).resolve().parents[1]
SERVER_PATH = ROOT_DIR / "web" / "server.py"


def load_server_module(
    config_overrides=None,
    env_overrides=None,
    process_env_overrides=None,
    env_file_overlays=None,
):
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

    for key, value in (config_overrides or {}).items():
        setattr(config_stub, key, value)

    spec = importlib.util.spec_from_file_location("dv_server_runtime_token_test", SERVER_PATH)
    module = importlib.util.module_from_spec(spec)
    previous_config = sys.modules.get("config")
    previous_web_config = sys.modules.get("web.config")
    previous_web_package = sys.modules.get("web")
    previous_web_package_config = getattr(previous_web_package, "config", None) if previous_web_package else None

    overlay_payloads = list(env_file_overlays or [])
    if not overlay_payloads:
        overlay_payloads = [env_overrides or {}]

    env_paths: list[str] = []
    for payload in overlay_payloads:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as env_file:
            for key, value in (payload or {}).items():
                env_file.write(f"{key}={value}\n")
            env_paths.append(env_file.name)

    try:
        patched_env = {"DEEPVISION_ENV_FILE": os.pathsep.join(env_paths)}
        patched_env.update(process_env_overrides or {})
        with patch.dict(os.environ, patched_env, clear=True):
            sys.modules["config"] = config_stub
            sys.modules["web.config"] = config_stub
            if previous_web_package is not None:
                setattr(previous_web_package, "config", config_stub)
            spec.loader.exec_module(module)
    finally:
        for env_path in env_paths:
            Path(env_path).unlink(missing_ok=True)
        if previous_config is None:
            sys.modules.pop("config", None)
        else:
            sys.modules["config"] = previous_config
        if previous_web_config is None:
            sys.modules.pop("web.config", None)
        else:
            sys.modules["web.config"] = previous_web_config
        if previous_web_package is not None:
            if previous_web_package_config is None and hasattr(previous_web_package, "config"):
                delattr(previous_web_package, "config")
            elif previous_web_package_config is not None:
                setattr(previous_web_package, "config", previous_web_package_config)

    return module


class RuntimeTokenConfigTests(unittest.TestCase):
    def test_explicit_env_file_supports_base_and_overlay(self):
        module = load_server_module(
            env_file_overlays=[
                {
                    "DEBUG_MODE": "true",
                    "SECRET_KEY": "base-secret",
                    "INSTANCE_SCOPE_KEY": "base-scope",
                    "SMS_PROVIDER": "mock",
                },
                {
                    "SECRET_KEY": "overlay-secret",
                    "INSTANCE_SCOPE_KEY": "overlay-scope",
                },
            ]
        )

        self.assertEqual(module.app.secret_key, "overlay-secret")
        self.assertEqual(module.INSTANCE_SCOPE_KEY, "overlay-scope")
        self.assertEqual(len(module.LOADED_ENV_FILES), 2)
        self.assertEqual(module.get_admin_env_file_path().resolve(), Path(module.LOADED_ENV_FILES[-1]).resolve())

    def test_production_import_rejects_placeholder_secret_key(self):
        with self.assertRaises(RuntimeError) as ctx:
            load_server_module(
                env_overrides={
                    "DEBUG_MODE": "false",
                    "SECRET_KEY": "replace-with-a-strong-random-secret",
                    "INSTANCE_SCOPE_KEY": "prod-instance",
                    "SMS_PROVIDER": "jdcloud",
                },
            )
        self.assertIn("SECRET_KEY", str(ctx.exception))

    def test_production_import_rejects_empty_instance_scope_key(self):
        with self.assertRaises(RuntimeError) as ctx:
            load_server_module(
                env_overrides={
                    "DEBUG_MODE": "false",
                    "SECRET_KEY": "prod-secret-value",
                    "INSTANCE_SCOPE_KEY": "",
                    "SMS_PROVIDER": "jdcloud",
                },
            )
        self.assertIn("INSTANCE_SCOPE_KEY", str(ctx.exception))

    def test_production_import_rejects_mock_sms_provider(self):
        with self.assertRaises(RuntimeError) as ctx:
            load_server_module(
                env_overrides={
                    "DEBUG_MODE": "false",
                    "SECRET_KEY": "prod-secret-value",
                    "INSTANCE_SCOPE_KEY": "prod-instance",
                    "SMS_PROVIDER": "mock",
                },
            )
        self.assertIn("SMS_PROVIDER=mock", str(ctx.exception))

    def test_debug_import_warns_for_explicit_insecure_defaults(self):
        with patch("builtins.print") as mock_print:
            module = load_server_module(
                env_overrides={
                    "DEBUG_MODE": "true",
                    "SECRET_KEY": "replace-with-a-strong-random-secret",
                    "INSTANCE_SCOPE_KEY": "",
                    "SMS_PROVIDER": "mock",
                },
            )

        self.assertTrue(module.DEBUG_MODE)
        log_text = "\n".join(" ".join(str(arg) for arg in call.args) for call in mock_print.call_args_list)
        self.assertIn("SECRET_KEY 仍是模板占位值", log_text)
        self.assertIn("INSTANCE_SCOPE_KEY 为空", log_text)
        self.assertIn("SMS_PROVIDER=mock", log_text)

    def test_search_decision_uses_configured_attempt_tokens(self):
        module = load_server_module(
            {
                "SEARCH_DECISION_FIRST_MAX_TOKENS": 256,
                "SEARCH_DECISION_RETRY_MAX_TOKENS": 192,
            }
        )
        module.ENABLE_WEB_SEARCH = True
        module.ENABLE_DEBUG_LOG = False

        token_calls = []

        class DummyMessages:
            def create(self, **kwargs):
                token_calls.append(kwargs["max_tokens"])
                if len(token_calls) == 1:
                    return types.SimpleNamespace(content=[{"type": "thinking", "thinking": "..."}])
                return types.SimpleNamespace(
                    content=[
                        {
                            "type": "text",
                            "text": '{"need_search": false, "reason": "无需搜索", "search_query": ""}',
                        }
                    ]
                )

        client = types.SimpleNamespace(messages=DummyMessages())

        with patch.object(module, "resolve_ai_client", new=lambda *args, **kwargs: client), \
             patch.object(module, "ai_call_priority_slot", new=lambda *args, **kwargs: nullcontext()), \
             patch.object(module, "_build_search_decision_cache_key", new=lambda *args, **kwargs: ""), \
             patch.object(module, "get_dimension_info_for_session", new=lambda *args, **kwargs: {}):
            result = module.ai_evaluate_search_need("主题", "customer", {}, [])

        self.assertEqual(token_calls, [256, 256])
        self.assertFalse(result["need_search"])

    def test_search_decision_retry_success_does_not_emit_warning_log(self):
        module = load_server_module()
        module.ENABLE_WEB_SEARCH = True
        module.ENABLE_DEBUG_LOG = True

        class DummyMessages:
            def __init__(self):
                self.calls = 0

            def create(self, **kwargs):
                self.calls += 1
                if self.calls == 1:
                    return types.SimpleNamespace(content=[{"type": "thinking", "thinking": "..."}])
                return types.SimpleNamespace(
                    content=[
                        {
                            "type": "text",
                            "text": '{"need_search": false, "reason": "无需搜索", "search_query": ""}',
                        }
                    ]
                )

        client = types.SimpleNamespace(messages=DummyMessages())

        with patch.object(module, "resolve_ai_client", new=lambda *args, **kwargs: client), \
             patch.object(module, "ai_call_priority_slot", new=lambda *args, **kwargs: nullcontext()), \
             patch.object(module, "_build_search_decision_cache_key", new=lambda *args, **kwargs: ""), \
             patch.object(module, "get_dimension_info_for_session", new=lambda *args, **kwargs: {}), \
             patch("builtins.print") as mock_print:
            result = module.ai_evaluate_search_need("主题", "customer", {}, [])

        log_text = "\n".join(" ".join(str(arg) for arg in call.args) for call in mock_print.call_args_list)
        self.assertNotIn("⚠️  AI搜索决策第1次解析失败", log_text)
        self.assertIn("ℹ️  AI搜索决策第1次解析失败，准备重试", log_text)
        self.assertFalse(result["need_search"])

    def test_assessment_score_uses_configured_max_tokens(self):
        module = load_server_module(env_overrides={"ASSESSMENT_SCORE_MAX_TOKENS": "128"})
        module.ENABLE_DEBUG_LOG = False

        token_calls = []

        class DummyMessages:
            def create(self, **kwargs):
                token_calls.append(kwargs["max_tokens"])
                return types.SimpleNamespace(content=[{"type": "text", "text": "4.5"}])

        client = types.SimpleNamespace(messages=DummyMessages())
        session = {
            "scenario_config": {
                "dimensions": [
                    {
                        "id": "communication",
                        "name": "沟通表达",
                        "description": "表达结构与清晰度",
                        "scoring_criteria": {
                            "5": "表达清晰且有逻辑",
                            "3": "表达基本完整",
                            "1": "表达混乱",
                        },
                    }
                ]
            }
        }

        with patch.object(module, "resolve_ai_client", new=lambda *args, **kwargs: client), \
             patch.object(module, "ai_call_priority_slot", new=lambda *args, **kwargs: nullcontext()):
            score = module.score_assessment_answer(session, "communication", "请做自我介绍", "我擅长跨团队协作")

        self.assertEqual(token_calls, [128])
        self.assertEqual(score, 4.5)

    def test_assessment_score_prefers_assessment_lane_and_model(self):
        module = load_server_module(
            env_overrides={
                "QUESTION_MODEL_NAME": "minimax-question",
                "SUMMARY_MODEL_NAME": "glm-summary",
                "SEARCH_DECISION_MODEL_NAME": "glm-search",
                "ASSESSMENT_MODEL_NAME": "glm-assessment",
            }
        )
        module.question_ai_client = None
        module.report_ai_client = None
        module.summary_ai_client = None
        module.search_decision_ai_client = None
        assessment_client = object()
        module.assessment_ai_client = assessment_client

        selected_client, selected_lane, _meta = module.resolve_ai_client_with_lane(call_type="assessment_score")

        self.assertIs(selected_client, assessment_client)
        self.assertEqual(selected_lane, "assessment")
        self.assertEqual(module.resolve_model_name(call_type="assessment_score"), "glm-assessment")

    def test_report_phase_models_apply_on_report_lane(self):
        module = load_server_module(
            {
                "QUESTION_MODEL_NAME": "minimax-question",
                "REPORT_MODEL_NAME": "kimi-report",
                "REPORT_DRAFT_MODEL_NAME": "kimi-draft",
                "REPORT_REVIEW_MODEL_NAME": "glm-review",
            }
        )

        self.assertEqual(
            module.resolve_model_name_for_lane(call_type="report_v3_draft", selected_lane="report"),
            "kimi-draft",
        )
        self.assertEqual(
            module.resolve_model_name_for_lane(call_type="report_v3_review_round_1", selected_lane="report"),
            "glm-review",
        )
        self.assertEqual(
            module.resolve_model_name_for_lane(call_type="report_v3_draft", selected_lane="report_draft"),
            "kimi-draft",
        )
        self.assertEqual(
            module.resolve_model_name_for_lane(call_type="report_v3_review_round_1", selected_lane="report_review"),
            "glm-review",
        )
        self.assertEqual(
            module.resolve_model_name_for_lane(call_type="report_v3_draft", selected_lane="question"),
            "minimax-question",
        )

    def test_report_phase_clients_prefer_dedicated_gateways(self):
        module = load_server_module()
        question_client = object()
        draft_client = object()
        review_client = object()

        module.question_ai_client = question_client
        module.report_ai_client = review_client
        module.report_draft_ai_client = draft_client
        module.report_review_ai_client = review_client
        module.summary_ai_client = None
        module.search_decision_ai_client = None
        module.assessment_ai_client = None

        selected_client, selected_lane, _meta = module.resolve_ai_client_with_lane(
            call_type="report_v3_draft",
            preferred_lane="report",
        )
        self.assertIs(selected_client, draft_client)
        self.assertEqual(selected_lane, "report_draft")

        selected_client, selected_lane, _meta = module.resolve_ai_client_with_lane(
            call_type="report_v3_review_round_1",
            preferred_lane="report",
        )
        self.assertIs(selected_client, review_client)
        self.assertEqual(selected_lane, "report_review")

        selected_client, selected_lane, _meta = module.resolve_ai_client_with_lane(
            call_type="report_v3_review_parse_repair_round_1",
            preferred_lane="report",
        )
        self.assertIs(selected_client, review_client)
        self.assertEqual(selected_lane, "report_review")

    def test_report_v3_defaults_prefer_report_lane_for_draft_and_review(self):
        module = load_server_module()

        self.assertEqual(module.REPORT_V3_DRAFT_PRIMARY_LANE, "report")
        self.assertEqual(module.REPORT_V3_REVIEW_PRIMARY_LANE, "report")
        self.assertEqual(module.resolve_report_v3_phase_lane("draft", pipeline_lane="report"), "report")
        self.assertEqual(module.resolve_report_v3_phase_lane("review", pipeline_lane="report"), "report")

    def test_prefetch_defaults_to_question_then_summary(self):
        module = load_server_module()
        self.assertEqual(module.PREFETCH_QUESTION_PRIMARY_LANE, "question")
        self.assertEqual(module.PREFETCH_QUESTION_SECONDARY_LANE, "summary")

    def test_auto_mode_keeps_strategy_keys_falling_back_to_config_py(self):
        module = load_server_module(
            {
                "AI_CLIENT_EAGER_INIT": True,
                "MODEL_NAME": "config-question",
                "REPORT_MODEL_NAME": "config-report",
                "REPORT_API_TIMEOUT": 123.0,
                "QUESTION_HEDGE_ADAPTIVE_PERCENTILE": 0.72,
                "REPORT_V3_DRAFT_PRIMARY_LANE": "question",
                "SUPPORTED_IMAGE_TYPES": [".png", ".webp"],
                "MAX_IMAGE_SIZE_MB": 18,
                "API_TIMEOUT": 123.0,
            },
            env_overrides={
                "QUESTION_API_KEY": "sk-question-from-env",
            },
        )

        self.assertEqual(module.CONFIG_RESOLUTION_MODE, "auto")
        self.assertTrue(module.AI_CLIENT_EAGER_INIT)
        self.assertEqual(module.QUESTION_MODEL_NAME, "config-question")
        self.assertEqual(module.REPORT_MODEL_NAME, "config-report")
        self.assertEqual(module.REPORT_API_TIMEOUT, 123.0)
        self.assertEqual(module.QUESTION_HEDGE_ADAPTIVE_PERCENTILE, 0.72)
        self.assertEqual(module.REPORT_V3_DRAFT_PRIMARY_LANE, "question")
        self.assertEqual(module.SUPPORTED_IMAGE_TYPES, [".png", ".webp"])
        self.assertEqual(module.MAX_IMAGE_SIZE_MB, 18)
        self.assertEqual(module.API_TIMEOUT, 123.0)

    def test_env_only_mode_disables_ai_runtime_fallback_to_config_py(self):
        module = load_server_module(
            {
                "MODEL_NAME": "legacy-question",
                "REPORT_MODEL_NAME": "legacy-report",
                "REPORT_V3_DRAFT_PRIMARY_LANE": "question",
                "PREFETCH_QUESTION_PRIMARY_LANE": "summary",
                "PREFETCH_QUESTION_SECONDARY_LANE": "question",
            },
            process_env_overrides={
                "CONFIG_RESOLUTION_MODE": "env_only",
                "MODEL_NAME": "env-question",
            },
        )

        self.assertEqual(module.CONFIG_RESOLUTION_MODE, "env_only")
        self.assertEqual(module.QUESTION_MODEL_NAME, "env-question")
        self.assertEqual(module.REPORT_MODEL_NAME, "env-question")
        self.assertEqual(module.REPORT_V3_DRAFT_PRIMARY_LANE, "report")
        self.assertEqual(module.PREFETCH_QUESTION_PRIMARY_LANE, "question")
        self.assertEqual(module.PREFETCH_QUESTION_SECONDARY_LANE, "summary")

    def test_ai_clients_use_lazy_init_until_first_resolution(self):
        module = load_server_module(
            {
                "ENABLE_AI": True,
                "QUESTION_MODEL_NAME": "minimax-question",
                "REPORT_MODEL_NAME": "claude-report",
                "SUMMARY_MODEL_NAME": "glm-summary",
                "SEARCH_DECISION_MODEL_NAME": "glm-search",
                "ASSESSMENT_MODEL_NAME": "glm-assessment",
                "QUESTION_API_KEY": "sk-question-valid-123456",
                "REPORT_API_KEY": "sk-report-valid-123456",
                "SUMMARY_API_KEY": "sk-summary-valid-123456",
                "SEARCH_DECISION_API_KEY": "sk-search-valid-123456",
                "ASSESSMENT_API_KEY": "sk-assessment-valid-123456",
                "QUESTION_BASE_URL": "https://question.example.com",
                "REPORT_BASE_URL": "https://report.example.com",
                "SUMMARY_BASE_URL": "https://summary.example.com",
                "SEARCH_DECISION_BASE_URL": "https://search.example.com",
                "ASSESSMENT_BASE_URL": "https://assessment.example.com",
                "AI_CLIENT_EAGER_INIT": False,
                "AI_CLIENT_INIT_CONNECTION_TEST": False,
            }
        )

        self.assertFalse(module.get_ai_client_bootstrap_snapshot().get("attempted"))
        self.assertIsNone(module.question_ai_client)
        self.assertIsNone(module.report_ai_client)

        initialized_lanes = []

        def _fake_init_lane_client(lane_name, api_key, base_url, test_model, use_bearer_auth=False, run_connection_test=False):
            initialized_lanes.append((lane_name, test_model, run_connection_test))
            return types.SimpleNamespace(messages=types.SimpleNamespace())

        with patch.object(module, "_init_lane_client", new=_fake_init_lane_client):
            client, lane, meta = module.resolve_ai_client_with_lane(call_type="question")

        self.assertIsNotNone(client)
        self.assertEqual(lane, "question")
        self.assertEqual(meta.get("requested_lane"), "question")
        self.assertTrue(module.get_ai_client_bootstrap_snapshot().get("attempted"))
        self.assertTrue(module.get_ai_client_bootstrap_snapshot().get("initialized"))
        self.assertTrue(initialized_lanes)
        self.assertEqual(initialized_lanes[0][0], "问题")
        self.assertTrue(all(item[2] is False for item in initialized_lanes))
        snapshot = module.get_ai_client_bootstrap_snapshot()
        self.assertTrue(snapshot.get("report_draft_ai_available"))
        self.assertTrue(snapshot.get("report_review_ai_available"))

    def test_parse_question_response_uses_structured_parser_for_dirty_json(self):
        module = load_server_module()
        response = """
这里是建议题目，请直接采用：
{"question":"你当前推进项目最卡的环节是什么？","options":["需求频繁变化","资源协调困难","上线节奏不稳"],}
"""

        parsed = module.parse_question_response(response)

        self.assertIsInstance(parsed, dict)
        self.assertEqual(parsed.get("question"), "你当前推进项目最卡的环节是什么？")
        self.assertEqual(parsed.get("options"), ["需求频繁变化", "资源协调困难", "上线节奏不稳"])

    def test_normalize_generated_question_result_strips_option_prefixes(self):
        module = load_server_module()
        normalized = module.normalize_generated_question_result(
            {
                "question": "当前最需要优先确认哪一项？",
                "options": ["A. 成本控制", "B、实施周期", "（3）数据质量", "4) 组织协同"],
                "multi_select": False,
                "is_follow_up": False,
            }
        )

        self.assertEqual(
            normalized.get("options"),
            ["成本控制", "实施周期", "数据质量", "组织协同"],
        )

    def test_generate_question_strategy_strips_prefixed_options(self):
        module = load_server_module()

        response_text = """
{"question":"当前最优先推进哪一项？","options":["A. 成本控制","B、实施周期","（3）数据质量","4) 组织协同"],"multi_select":false,"is_follow_up":false}
"""

        def _fake_question_call(*_args, **kwargs):
            lane = kwargs.get("primary_lane", "question")
            return response_text, lane, {"selected_lane": lane, "attempts": [{"lane": lane, "success": True}]}

        with patch.object(module, "_call_question_with_optional_hedge", new=_fake_question_call):
            _question_raw, question_result, generation_mode = module.generate_question_with_tiered_strategy(
                prompt="请生成一个问题",
                allow_fast_path=False,
                runtime_profile={
                    "allow_fast_path": False,
                    "primary_lane": "question",
                    "secondary_lane": "summary",
                },
            )

        self.assertEqual(generation_mode, "full:question")
        self.assertEqual(
            question_result.get("options"),
            ["成本控制", "实施周期", "数据质量", "组织协同"],
        )

    def test_mocked_end_to_end_question_scoring_and_report_review_repair(self):
        module = load_server_module(
            {
                "QUESTION_MODEL_NAME": "minimax-question",
                "REPORT_MODEL_NAME": "claude-report",
                "REPORT_DRAFT_MODEL_NAME": "claude-draft",
                "REPORT_REVIEW_MODEL_NAME": "claude-review",
                "ASSESSMENT_MODEL_NAME": "glm-assessment",
                "REPORT_V3_DRAFT_PRIMARY_LANE": "report",
                "REPORT_V3_REVIEW_PRIMARY_LANE": "report",
                "REPORT_V3_MIN_REVIEW_ROUNDS": 1,
                "REPORT_V3_RELEASE_CONSERVATIVE_MODE": False,
                "REPORT_V3_SKIP_MODEL_REVIEW_IN_RELEASE_CONSERVATIVE": False,
                "REPORT_V3_REVIEW_REPAIR_RETRY_ENABLED": True,
                "REPORT_V3_REVIEW_REPAIR_MAX_TOKENS": 1800,
            }
        )
        module.ENABLE_DEBUG_LOG = False

        question_raw = """
推荐问题如下：
{"question":"你当前项目推进里最大的阻塞点是什么？","options":["需求变化频繁","跨团队协作慢","上线质量不稳定"],}
"""

        def _fake_question_call(*_args, **kwargs):
            lane = kwargs.get("primary_lane", "question")
            return question_raw, lane, {"selected_lane": lane, "attempts": [{"lane": lane, "success": True, "failure_reason": "ok"}]}

        with patch.object(module, "_call_question_with_optional_hedge", new=_fake_question_call):
            _question_raw, question_result, generation_mode = module.generate_question_with_tiered_strategy(
                prompt="请生成一个问题",
                allow_fast_path=False,
                runtime_profile={
                    "allow_fast_path": False,
                    "primary_lane": "question",
                    "secondary_lane": "summary",
                },
            )

        self.assertEqual(generation_mode, "full:question")
        self.assertEqual(question_result.get("question"), "你当前项目推进里最大的阻塞点是什么？")
        self.assertEqual(question_result.get("options"), ["需求变化频繁", "跨团队协作慢", "上线质量不稳定"])

        class DummyMessages:
            def create(self, **kwargs):
                self.last_kwargs = kwargs
                return types.SimpleNamespace(content=[{"type": "text", "text": "4.2"}])

        assessment_client = types.SimpleNamespace(messages=DummyMessages())
        assessment_session = {
            "scenario_config": {
                "dimensions": [
                    {
                        "id": "communication",
                        "name": "沟通表达",
                        "description": "表达清晰度与结构化程度",
                        "scoring_criteria": {
                            "5": "表达清晰、结构完整、观点有层次",
                            "3": "表达基本完整但深度一般",
                            "1": "表达混乱，缺少有效信息",
                        },
                    }
                ]
            }
        }

        with patch.object(module, "resolve_ai_client", new=lambda *args, **kwargs: assessment_client), \
             patch.object(module, "ai_call_priority_slot", new=lambda *args, **kwargs: nullcontext()):
            score = module.score_assessment_answer(
                assessment_session,
                "communication",
                question_result["question"],
                "目前最大的阻塞是需求变更太快，跨团队对齐成本很高。",
            )

        self.assertEqual(score, 4.2)

        report_call_types = []

        def _fake_call_claude(_prompt, **kwargs):
            call_type = str(kwargs.get("call_type", "") or "")
            report_call_types.append(call_type)
            if call_type.startswith("report_v3_draft"):
                return (
                    '{"overview":"初版概述","needs":[{"name":"需求稳定性","priority":"P0","description":"需要控制变更频率","evidence_refs":["Q1"]}],'
                    '"analysis":{"customer_needs":"需要更稳定的需求节奏","business_flow":"跨团队协作链路较长","tech_constraints":"上线质量需要更稳","project_constraints":"资源协调成本高"},'
                    '"visualizations":{},"solutions":[],"risks":[],"actions":[],"open_questions":[],"evidence_index":[]}'
                )
            if call_type.startswith("report_v3_review_round_"):
                return "审稿结论：整体可用，但请只保留 JSON，不要解释。"
            if call_type.startswith("report_v3_review_parse_repair_round_"):
                return '{"passed": true, "issues": [], "revised_draft": {"overview": "修复后概述", "actions": [{"action": "建立周度变更冻结窗口", "owner": "产品经理", "timeline": "2周内", "metric": "需求变更率下降20%", "evidence_refs": ["Q1"]}]}}'
            return ""

        report_session = {"topic": "项目访谈"}

        with patch.object(module, "build_report_evidence_pack", new=lambda _session: {"facts": [{"q_id": "Q1"}], "overall_coverage": 1.0}), \
             patch.object(module, "build_report_draft_prompt_v3", new=lambda *_args, **_kwargs: "draft prompt"), \
             patch.object(module, "build_report_review_prompt_v3", new=lambda *_args, **_kwargs: "review prompt"), \
             patch.object(module, "validate_report_draft_v3", new=lambda draft, _evidence: (draft, [])), \
             patch.object(module, "compute_report_quality_meta_v3", new=lambda *_args, **_kwargs: {"mode": "v3_structured_reviewed", "evidence_coverage": 1.0, "consistency": 1.0, "actionability": 1.0, "overall": 1.0}), \
             patch.object(module, "build_quality_gate_issues_v3", new=lambda *_args, **_kwargs: []), \
             patch.object(module, "render_report_from_draft_v3", new=lambda *_args, **_kwargs: "# final report"), \
             patch.object(module, "call_claude", new=_fake_call_claude):
            report_result = module.generate_report_v3_pipeline(
                report_session,
                preferred_lane="report",
                report_profile="balanced",
            )

        self.assertEqual(report_result.get("status"), "success")
        self.assertEqual(report_result.get("phase_lanes"), {"draft": "report", "review": "report"})
        self.assertIn("report_v3_review_parse_repair_round_1", report_call_types)

    def test_review_parse_repair_retry_builds_structured_result(self):
        module = load_server_module({"REPORT_V3_REVIEW_REPAIR_RETRY_ENABLED": True})
        module.ENABLE_DEBUG_LOG = False

        calls = []

        def _fake_call_claude(prompt, **kwargs):
            calls.append((prompt, kwargs))
            return '{"passed": true, "issues": [], "revised_draft": {"overview": "ok"}}'

        with patch.object(module, "call_claude", new=_fake_call_claude):
            repaired, meta, repair_raw = module.repair_report_review_response_v3(
                review_raw="上一轮输出不是合法 JSON",
                current_draft={"overview": "draft"},
                review_issues=[{"type": "quality_gate_table", "severity": "high", "message": "表格化不足", "target": "needs"}],
                preferred_lane="report",
                review_round_no=1,
                call_type_suffix="",
                max_tokens=1500,
                timeout=20.0,
            )

        self.assertTrue(repaired.get("passed"))
        self.assertEqual(repaired.get("revised_draft", {}).get("overview"), "ok")
        self.assertTrue(meta.get("attempted"))
        self.assertIn("report_v3_review_parse_repair_round_1", meta.get("repair_call_type", ""))
        self.assertIn("上一轮输出不是合法 JSON", calls[0][0])
        self.assertEqual(repair_raw, '{"passed": true, "issues": [], "revised_draft": {"overview": "ok"}}')


if __name__ == "__main__":
    unittest.main()
