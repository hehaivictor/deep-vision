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
        cls.server.REPORTS_DIR = cls.server.DATA_DIR / "reports"
        cls.server.REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    def setUp(self):
        for path in self.server.REPORTS_DIR.glob("*"):
            if path.is_file():
                path.unlink()

    def _write_structured_sidecar(self, report_name: str, snapshot: dict):
        self.server.write_solution_sidecar(report_name, snapshot)
        return self.server.build_solution_payload_from_report(report_name, "# 占位报告")

    def _build_snapshot(self, report_name: str, *, topic: str, scenario_id: str = "", scenario_name: str = "", overview: str, needs=None, solutions=None, risks=None, actions=None, open_questions=None, evidence_index=None, analysis=None, coverage: float = 0.78, has_structured_evidence: bool = True):
        return {
            "report_name": report_name,
            "topic": topic,
            "session_id": f"session-{report_name}",
            "scenario_id": scenario_id,
            "scenario_name": scenario_name,
            "report_template": self.server.REPORT_TEMPLATE_STANDARD_V1,
            "report_type": "standard",
            "quality_meta": {"snapshot_source": "test"},
            "quality_snapshot": {"quality_score": 0.86},
            "overall_coverage": coverage,
            "snapshot_origin": "structured_sidecar",
            "has_structured_evidence": has_structured_evidence,
            "draft": {
                "overview": overview,
                "needs": needs or [],
                "analysis": analysis or {
                    "customer_needs": "需要把真实问题、分发方式和复盘机制放进同一条闭环。",
                    "business_flow": "从反馈采集到归因、分发、执行和复盘形成闭环。",
                    "tech_constraints": "所有原始反馈都需要脱敏并保留审计。",
                    "project_constraints": "首轮试点只覆盖一个业务线和一个反馈来源。",
                },
                "visualizations": {},
                "solutions": solutions or [],
                "risks": risks or [],
                "actions": actions or [],
                "open_questions": open_questions or [],
                "evidence_index": evidence_index or [],
            },
        }

    def test_build_solution_payload_falls_back_to_legacy_markdown_for_old_report(self):
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
        self.assertEqual(payload.get('source_mode'), 'legacy_markdown')
        self.assertIn('落地方案', payload.get('title', ''))
        self.assertTrue(payload.get('decision_summary'))
        self.assertGreaterEqual(len(payload.get('nav_items', [])), 4)
        self.assertGreaterEqual(len(payload.get('sections', [])), 4)
        self.assertEqual(payload.get('headline_cards', [])[0].get('value'), '微信私域客户接待')
        self.assertEqual(payload.get('headline_cards', [])[2].get('value'), '首轮咨询分流')
        self.assertIn('fallback_ratio', payload.get('quality_signals', {}))
        self.assertIn('evidence_binding_ratio', payload.get('quality_signals', {}))

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

        self.assertEqual(payload.get('source_mode'), 'legacy_markdown')
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

        self.assertEqual(payload.get('source_mode'), 'legacy_markdown')
        self.assertNotIn('产品需求调研报告落地方案', payload.get('title', ''))
        self.assertNotIn('调研报告', payload.get('headline_cards', [])[0].get('value', ''))

    def test_real_v3_markdown_report_builds_dynamic_sections(self):
        report_content = (
            '# 用户反馈访谈报告\n\n'
            '## 1. 访谈概述\n'
            '本轮聚焦售后回访反馈闭环，目标是减少重复分发与漏处理。\n\n'
            '## 2. 需求摘要\n'
            '### 核心需求\n'
            '| 优先级 | 需求项 | 描述 | 证据 |\n'
            '| --- | --- | --- | --- |\n'
            '| P0 | 回访问题归因不统一 | 同一类问题被分发到不同团队，导致复盘困难。 | Q1 Q2 |\n'
            '| P1 | 反馈闭环进度不可见 | 处理进度分散在多个系统中。 | Q3 |\n\n'
            '## 3. 详细需求分析\n'
            '### 客户需求\n'
            '希望建立稳定的反馈闭环与优先级治理机制。\n\n'
            '### 业务流程\n'
            '采集反馈后需要完成归因、分发、执行、复盘。\n\n'
            '### 技术约束\n'
            '敏感反馈需要脱敏并保留审计留痕。\n\n'
            '### 项目约束\n'
            '首轮只覆盖售后回访团队。\n\n'
            '## 4. 方案建议\n'
            '### 建议清单\n'
            '| 方案建议 | 说明 | Owner | 时间计划 | 验收指标 | 证据 |\n'
            '| --- | --- | --- | --- | --- | --- |\n'
            '| 反馈标签统一归因 | 建立统一标签字典并收口归因口径。 | 产品 | 第1周 | 归因准确率 > 85% | Q4 |\n'
            '| 建立反馈分发SLA | 分发时直接绑定负责人和超时提醒。 | 运营 | 第2周 | 超时率 < 10% | Q5 |\n\n'
            '## 5. 风险评估\n'
            '### 风险清单\n'
            '| 风险项 | 影响 | 缓解措施 | 证据 |\n'
            '| --- | --- | --- | --- |\n'
            '| 反馈口径不一致 | 指标失真，团队争议大 | 先统一标签词典，再开放扩展字段 | Q6 |\n\n'
            '## 6. 下一步行动\n'
            '### 行动计划\n'
            '| 行动项 | Owner | 时间计划 | 验收指标 | 证据 |\n'
            '| --- | --- | --- | --- | --- |\n'
            '| 对齐标签词典与优先级标准 | 产品+运营 | 第1周 | 形成统一规则文档 | Q7 |\n'
            '| 上线反馈分发看板试点 | 运营 | 第2-3周 | 每日分发时效可追踪 | Q8 |\n'
        )
        payload = self.server.build_solution_payload_from_report('feedback-v3.md', report_content)

        nav_ids = [item.get('id') for item in payload.get('nav_items', [])]
        self.assertEqual(payload.get('source_mode'), 'legacy_markdown')
        self.assertIn('problem-map', nav_ids)
        self.assertIn('feedback-loop', nav_ids)
        self.assertIn('dispatch', nav_ids)
        self.assertIn('priority', nav_ids)
        self.assertIn('roadmap', nav_ids)
        self.assertGreaterEqual(len(payload.get('sections', [])), 5)
        self.assertGreater(payload.get('quality_signals', {}).get('evidence_binding_ratio', 0), 0.5)

    def test_historical_markdown_direct_tables_expand_feedback_sections(self):
        report_content = (
            '# 用户反馈访谈报告\n\n'
            '## 1. 访谈概述\n'
            '围绕用户反馈处理效率和优先级误判问题开展访谈。\n\n'
            '## 2. 需求摘要\n'
            '### 2.1 核心需求列表\n'
            '| 编号 | 需求项 | 来源痛点 |\n'
            '| --- | --- | --- |\n'
            '| N1 | 多渠道反馈自动聚合 | 每天需要跨平台复制粘贴，效率低。 |\n'
            '| N2 | 智能分类与去重 | 大量重复反馈占用产品时间。 |\n\n'
            '## 5. 方案建议\n'
            '### 工具选型建议\n'
            '| 方向 | 推荐思路 | 理由 |\n'
            '| --- | --- | --- |\n'
            '| 轻量级SaaS | 先试用反馈聚合工具 | 可以快速验证闭环效率。 |\n'
            '| 低代码自建 | 飞书多维表格 + 机器人 | 能贴合现有协作链路。 |\n\n'
            '## 6. 风险评估\n'
            '| 风险项 | 可能性 | 影响 | 应对策略 |\n'
            '| --- | --- | --- | --- |\n'
            '| 团队无法持续使用 | 高 | 高 | 方案必须融入现有工作流。 |\n\n'
            '## 7. 下一步行动\n'
            '| 序号 | 行动项 | 负责方 | 时间建议 | 交付物 |\n'
            '| --- | --- | --- | --- | --- |\n'
            '| 1 | 评估所有反馈来源接入方式 | 产品 + 开发 | 本周内 | 数据源清单 |\n'
            '| 2 | 试用一套反馈看板方案 | 产品 | 两周内 | 试点评估结论 |\n'
        )
        payload = self.server.build_solution_payload_from_report('historical-feedback.md', report_content)

        nav_ids = [item.get('id') for item in payload.get('nav_items', [])]
        self.assertEqual(payload.get('source_mode'), 'legacy_markdown')
        self.assertIn('problem-map', nav_ids)
        self.assertIn('feedback-loop', nav_ids)
        self.assertIn('dispatch', nav_ids)
        self.assertIn('priority', nav_ids)
        self.assertIn('roadmap', nav_ids)
        self.assertIn('risks', nav_ids)
        self.assertGreaterEqual(len(payload.get('sections', [])), 6)
        self.assertEqual(payload.get('headline_cards', [])[0].get('value'), '用户反馈')

    def test_structured_sidecar_profiles_are_differentiated(self):
        feedback_payload = self._write_structured_sidecar(
            'feedback-sidecar.md',
            self._build_snapshot(
                'feedback-sidecar.md',
                topic='用户反馈落地方案',
                scenario_id='user-research',
                scenario_name='用户反馈闭环',
                overview='当前最大问题不是没有反馈，而是反馈无法稳定归因、分发和复盘。',
                needs=[
                    {'priority': 'P0', 'name': '反馈归因口径统一', 'description': '先把高频反馈按统一标签收口。', 'evidence_refs': ['Q1', 'Q2']},
                    {'priority': 'P1', 'name': '反馈分发责任明确', 'description': '每条反馈都要有明确 owner 和处理 SLA。', 'evidence_refs': ['Q3']},
                ],
                solutions=[
                    {'title': '建立反馈标签字典', 'description': '统一售后回访中的问题标签与升级规则。', 'owner': '产品', 'timeline': '第1周', 'metric': '标签一致率 > 90%', 'evidence_refs': ['Q4']},
                    {'title': '搭建闭环分发看板', 'description': '对反馈流转状态和超时项进行看板化管理。', 'owner': '运营', 'timeline': '第2周', 'metric': '超时率 < 10%', 'evidence_refs': ['Q5']},
                ],
                risks=[
                    {'risk': '跨团队口径不一致', 'impact': '闭环数据失真，无法复盘。', 'mitigation': '先冻结标签字典与升级规则。', 'evidence_refs': ['Q6']},
                ],
                actions=[
                    {'action': '完成标签词典评审', 'owner': '产品+运营', 'timeline': '第1周', 'metric': '评审通过', 'evidence_refs': ['Q7']},
                    {'action': '上线反馈分发试点', 'owner': '运营', 'timeline': '第2-3周', 'metric': '分发时效可追踪', 'evidence_refs': ['Q8']},
                ],
                evidence_index=[{'claim': '反馈闭环需要先统一归因口径', 'confidence': 'high', 'evidence_refs': ['Q1', 'Q4']}],
            ),
        )
        interview_payload = self._write_structured_sidecar(
            'interview-sidecar.md',
            self._build_snapshot(
                'interview-sidecar.md',
                topic='交互式访谈落地方案',
                scenario_name='交互式访谈',
                overview='当前重点是优化访谈策略、问题编排和样本触发，提升洞察沉淀质量。',
                needs=[
                    {'priority': 'P0', 'name': '访谈问题编排更稳定', 'description': '关键追问需要根据样本状态动态切换。', 'evidence_refs': ['Q1']},
                    {'priority': 'P1', 'name': '样本触发链路可追踪', 'description': '需要知道哪些样本进入了哪类访谈脚本。', 'evidence_refs': ['Q2']},
                ],
                solutions=[
                    {'title': '重构访谈策略树', 'description': '按样本意图、风险和进度切换追问节点。', 'owner': '研究', 'timeline': '第1周', 'metric': '关键追问命中率 > 80%', 'evidence_refs': ['Q3']},
                    {'title': '建立洞察沉淀仓', 'description': '把高价值洞察沉淀为可检索的结论片段。', 'owner': '产品', 'timeline': '第2周', 'metric': '高价值洞察沉淀率 > 70%', 'evidence_refs': ['Q4']},
                ],
                risks=[
                    {'risk': '低质量样本稀释洞察', 'impact': '问题编排无法收敛有效结论。', 'mitigation': '先建立样本筛选与触发标准。', 'evidence_refs': ['Q5']},
                ],
                actions=[
                    {'action': '设计样本触发规则', 'owner': '研究', 'timeline': '第1周', 'metric': '样本触发准确率 > 85%', 'evidence_refs': ['Q6']},
                    {'action': '上线访谈策略试点', 'owner': '研究+产品', 'timeline': '第2-3周', 'metric': '访谈完成率提升', 'evidence_refs': ['Q7']},
                ],
                open_questions=[{'question': '是否要按样本成熟度拆分策略树', 'reason': '不同样本追问深度差异大', 'impact': '影响问题编排复杂度', 'suggested_follow_up': '补问高频样本路径', 'evidence_refs': ['Q8']}],
                evidence_index=[{'claim': '访谈策略需要按样本状态动态切换', 'confidence': 'high', 'evidence_refs': ['Q1', 'Q3']}],
            ),
        )

        feedback_nav = [item.get('id') for item in feedback_payload.get('nav_items', [])]
        interview_nav = [item.get('id') for item in interview_payload.get('nav_items', [])]

        self.assertEqual(feedback_payload.get('source_mode'), 'structured_sidecar')
        self.assertEqual(interview_payload.get('source_mode'), 'structured_sidecar')
        self.assertNotEqual(feedback_payload.get('title'), interview_payload.get('title'))
        self.assertNotEqual(feedback_nav, interview_nav)
        self.assertEqual(feedback_nav[:5], ['decision', 'problem-map', 'feedback-loop', 'dispatch', 'priority'])
        self.assertEqual(interview_nav[:5], ['decision', 'strategy', 'orchestration', 'sample-trigger', 'insight-repo'])
        self.assertGreaterEqual(len(set(feedback_nav) ^ set(interview_nav)), 4)

    def test_structured_sidecar_degrades_when_evidence_binding_is_too_low(self):
        payload = self._write_structured_sidecar(
            'degraded-sidecar.md',
            self._build_snapshot(
                'degraded-sidecar.md',
                topic='低证据绑定方案',
                scenario_name='用户反馈闭环',
                overview='当前只有粗粒度摘要，没有绑定到足够的真实证据。',
                needs=[{'priority': 'P0', 'name': '需要统一问题口径', 'description': '先对齐问题定义。', 'evidence_refs': []}],
                solutions=[{'title': '建立统一标签词典', 'description': '先从标签字典开始。', 'owner': '产品', 'timeline': '第1周', 'metric': '完成评审', 'evidence_refs': []}],
                risks=[{'risk': '事实不足', 'impact': '容易继续输出模板化结论。', 'mitigation': '先补证据再出方案。', 'evidence_refs': []}],
                actions=[{'action': '补齐关键证据', 'owner': '研究', 'timeline': '本周', 'metric': '补齐 Q 编号', 'evidence_refs': []}],
                has_structured_evidence=False,
            ),
        )

        self.assertEqual(payload.get('source_mode'), 'degraded')
        self.assertEqual(payload.get('fallback_source_mode'), 'structured_sidecar')
        self.assertTrue(payload.get('quality_signals', {}).get('degraded_reasons'))
        self.assertGreaterEqual(len(payload.get('sections', [])), 1)
        self.assertIn('真实信息摘要', payload.get('title', ''))


if __name__ == '__main__':
    unittest.main()
