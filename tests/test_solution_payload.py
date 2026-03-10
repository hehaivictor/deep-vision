import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path


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

    spec = importlib.util.spec_from_file_location("dv_server_solution_payload_test", SERVER_PATH)
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


class SolutionPayloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = load_server_module()
        cls.temp_dir = tempfile.TemporaryDirectory(prefix="dv-solution-payload-tests-")
        cls.sandbox_root = Path(cls.temp_dir.name).resolve()
        cls.server.DATA_DIR = cls.sandbox_root / "data"
        cls.server.DATA_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    def test_build_solution_payload_outputs_proposal_sections(self):
        report_content = (
            '# DeepVision 访谈报告\n\n'
            '## 1. 访谈概述\n'
            '- **访谈场景** - 微信私域客户接待\n'
            '- **核心问题** - 高意向客户识别和分层效率低\n'
            '- **关键触点** - 首轮咨询分流\n\n'
            '## 2. 需求摘要\n'
            '### 客户需求\n'
            '- **尽快识别高意向客户** - 减少人工二次筛选和漏跟进。\n'
            '- **统一后续动作** - 让坐席知道下一步该怎么推进。\n'
            '### 业务流程\n'
            '- **首轮咨询分流** - 按来源、意图和问题类型进行初步分层。\n'
            '- **转人工前打标签** - 输出优先级和建议动作。\n'
            '### 技术约束\n'
            '- **对话内容需要脱敏** - 禁止原文外流并保留审计记录。\n'
            '### 项目约束\n'
            '- **四周内完成试点** - 先覆盖一个业务线。\n'
        )
        payload = self.server.build_solution_payload_from_report('proposal.md', report_content)

        self.assertEqual(payload.get('report_name'), 'proposal.md')
        self.assertIn('落地方案', payload.get('title', ''))
        self.assertTrue(payload.get('decision_summary'))
        self.assertEqual(
            [item.get('id') for item in payload.get('nav_items', [])],
            ['decision', 'comparison', 'modules', 'architecture', 'dataflow', 'value', 'roadmap', 'risks', 'actions'],
        )
        self.assertGreaterEqual(len(payload.get('decision_cards', [])), 3)
        self.assertGreaterEqual(len(payload.get('comparison_items', [])), 3)
        self.assertGreaterEqual(len(payload.get('architecture_nodes', [])), 4)
        self.assertGreaterEqual(len(payload.get('dataflow_steps', [])), 4)
        self.assertGreaterEqual(len(payload.get('value_table', [])), 4)
        self.assertGreaterEqual(len(payload.get('dimension_cards', [])), 4)
        self.assertGreaterEqual(len(payload.get('roadmap', [])), 3)
        self.assertGreaterEqual(len(payload.get('risk_cards', [])), 1)
        self.assertEqual(payload.get('headline_cards', [])[0].get('value'), '微信私域客户接待')
        self.assertEqual(payload.get('headline_cards', [])[2].get('value'), '首轮咨询分流')

    def test_build_solution_payload_strips_html_and_prefers_overview_facts(self):
        report_content = (
            '# DeepVision 访谈报告\n\n'
            '## 1. 访谈概述\n'
            '- **访谈场景** - <b>售后服务回访</b>\n'
            '- **核心问题** - <script>alert(1)</script>回访记录无法统一归因\n'
            '- **关键触点** - 回访结束后的总结页面\n\n'
            '## 2. 需求摘要\n'
            '### 客户需求\n'
            '- **别名场景** - 这个字段不应覆盖访谈概述里的场景。\n'
            '### 业务流程\n'
            '- **总结页面归档** - <div>回访后沉淀结论</div>\n'
            '### 技术约束\n'
            '- **内容脱敏** - <span>敏感信息不能外流</span>\n'
            '### 项目约束\n'
            '- **两周内给出演示版本** - 先对接一个团队。\n'
        )
        payload = self.server.build_solution_payload_from_report('sanitize.md', report_content)

        def iter_strings(value):
            if isinstance(value, str):
                yield value
            elif isinstance(value, dict):
                for item in value.values():
                    yield from iter_strings(item)
            elif isinstance(value, list):
                for item in value:
                    yield from iter_strings(item)

        all_strings = list(iter_strings(payload))
        self.assertTrue(all_strings)
        for value in all_strings:
            lowered = value.lower()
            self.assertNotIn('<script', lowered)
            self.assertNotIn('</script', lowered)
            self.assertNotIn('<div', lowered)

        self.assertIn('售后服务回访', payload.get('title', ''))
        self.assertEqual(payload.get('headline_cards', [])[0].get('value'), '售后服务回访')
        self.assertEqual(payload.get('headline_cards', [])[2].get('value'), '回访结束后的总结页面')

    def test_build_solution_payload_avoids_using_full_report_title_as_scene(self):
        report_content = (
            '# 交互式访谈产品需求调研报告\n\n'
            '## 1. 访谈概述\n'
            '本次访谈主题为「交互式访谈产品需求调研报告」，共收集了 1 个问题的回答。\n\n'
            '## 2. 需求摘要\n'
            '### 客户需求\n'
            '- **需要进一步明确核心痛点** - 聚焦最先验证的问题。\n'
            '### 业务流程\n'
            '- **关键业务触点** - 先从一个入口做试点。\n'
            '### 技术约束\n'
            '- **数据需要脱敏** - 不能泄露原始会话。\n'
            '### 项目约束\n'
            '- **四周内完成验证** - 先做最小闭环。\n'
        )
        payload = self.server.build_solution_payload_from_report('generic.md', report_content)

        self.assertNotIn('产品需求调研报告落地方案', payload.get('title', ''))
        self.assertNotIn('调研报告', payload.get('headline_cards', [])[0].get('value', ''))



if __name__ == '__main__':
    unittest.main()
