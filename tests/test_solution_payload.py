import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


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
        cls.server.ENABLE_AI = False
        cls.server.question_ai_client = None
        cls.server.report_ai_client = None
        cls.server.report_draft_ai_client = None
        cls.server.report_review_ai_client = None
        cls.server.summary_ai_client = None
        cls.server.search_decision_ai_client = None
        cls.server.assessment_ai_client = None

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

    def _build_snapshot(self, report_name: str, *, topic: str, scenario_id: str = "", scenario_name: str = "", overview: str, needs=None, solutions=None, risks=None, actions=None, open_questions=None, evidence_index=None, analysis=None, coverage: float = 0.78, has_structured_evidence: bool = True, solution_schema=None):
        payload = {
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
        if isinstance(solution_schema, dict):
            payload["solution_schema"] = solution_schema
        return payload

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

    def test_historical_interview_markdown_extracts_overview_and_structured_fields(self):
        report_path = ROOT_DIR / "data" / "reports" / "deep-vision-20260310-e2a4fd23-交互式访谈产品需求调研.md"
        report_content = report_path.read_text(encoding="utf-8")

        snapshot = self.server.build_solution_snapshot_from_markdown_report(report_path.name, report_content)
        draft = snapshot.get("draft", {})

        self.assertTrue(draft.get("overview"))
        self.assertIn("交易支付环节风控体验", draft.get("overview", ""))
        self.assertGreaterEqual(len(draft.get("needs", [])), 6)
        self.assertGreaterEqual(len(draft.get("solutions", [])), 5)
        self.assertGreaterEqual(len(draft.get("risks", [])), 5)
        self.assertGreaterEqual(len(draft.get("actions", [])), 8)
        self.assertEqual(draft.get("needs", [])[0].get("name"), "交易支付环节风控体验研究")
        self.assertTrue(draft.get("needs", [])[0].get("description"))
        self.assertEqual(draft.get("solutions", [])[0].get("title"), "智能触发引擎")
        self.assertTrue(draft.get("solutions", [])[0].get("description"))
        self.assertTrue(draft.get("solutions", [])[0].get("metric"))
        self.assertEqual(draft.get("risks", [])[0].get("risk"), "真实被拦截用户招募困难，样本偏差")
        self.assertTrue(draft.get("risks", [])[0].get("impact"))
        self.assertEqual(draft.get("actions", [])[0].get("owner"), "项目经理")
        self.assertEqual(draft.get("actions", [])[0].get("timeline"), "T+3天")

    def test_structured_sidecar_profiles_are_differentiated(self):
        feedback_schema = {
            "version": "v1",
            "sections": [
                "推进判断",
                "现状问题",
                "方案对比",
                "实施路径",
                "风险边界",
            ],
        }
        interview_schema = {
            "version": "v1",
            "sections": [
                "推进判断",
                "目标蓝图",
                "落地模块",
                "下一步推进",
                "未决问题",
            ],
        }
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
                solution_schema=feedback_schema,
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
                solution_schema=interview_schema,
            ),
        )

        feedback_nav = [item.get('id') for item in feedback_payload.get('nav_items', [])]
        interview_nav = [item.get('id') for item in interview_payload.get('nav_items', [])]

        self.assertEqual(feedback_payload.get('source_mode'), 'structured_sidecar')
        self.assertEqual(interview_payload.get('source_mode'), 'structured_sidecar')
        self.assertEqual(feedback_payload.get('solution_schema_meta', {}).get('render_mode'), 'schema')
        self.assertEqual(interview_payload.get('solution_schema_meta', {}).get('render_mode'), 'schema')
        self.assertNotEqual(feedback_payload.get('title'), interview_payload.get('title'))
        self.assertNotEqual(feedback_nav, interview_nav)
        self.assertEqual(feedback_nav[:5], ['decision', 'current-state', 'option-compare', 'roadmap', 'risks'])
        self.assertEqual(interview_nav[:5], ['decision', 'target-blueprint', 'modules', 'actions', 'open-questions'])
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

    def test_structured_sidecar_builds_proposal_brief_and_chapter_copy(self):
        payload = self._write_structured_sidecar(
            'proposal-sidecar.md',
            self._build_snapshot(
                'proposal-sidecar.md',
                topic='交易支付风控体验优化',
                scenario_name='交互式访谈',
                overview='当前需要先锁定高价值样本、真实触发时机和混合复现路径，才能解释用户为什么放弃支付而非申诉。',
                needs=[
                    {'priority': 'P0', 'name': '高价值样本招募更精准', 'description': '先锁定真实被拦截用户。', 'evidence_refs': ['Q1']},
                    {'priority': 'P0', 'name': '触发时机更贴近真实决策瞬间', 'description': '不能过早也不能过晚。', 'evidence_refs': ['Q2']},
                    {'priority': 'P1', 'name': '复现方式兼顾深度与成本', 'description': '高保真和低保真需要组合。', 'evidence_refs': ['Q3']},
                ],
                solutions=[
                    {'title': '建立高价值样本招募通道', 'description': '围绕支付失败页和拦截页组织样本入口。', 'owner': '运营', 'timeline': '第1周', 'metric': '形成首批样本池', 'evidence_refs': ['Q4']},
                    {'title': '设计延时触发策略', 'description': '在高信号时刻触发访谈，减少体验干扰。', 'owner': '研究', 'timeline': '第2周', 'metric': '触发命中率提升', 'evidence_refs': ['Q5']},
                    {'title': '搭建混合复现机制', 'description': '结合低保真原型和录屏回放提取真实变量。', 'owner': '设计+研究', 'timeline': '第3周', 'metric': '形成首轮归因洞察', 'evidence_refs': ['Q6']},
                ],
                risks=[
                    {'risk': '真实样本不足', 'impact': '结论失真', 'mitigation': '先锁定高价值入口', 'evidence_refs': ['Q7']},
                    {'risk': '合规评审拖慢试点', 'impact': '周期拉长', 'mitigation': '提前完成脱敏与评审', 'evidence_refs': ['Q8']},
                ],
                actions=[
                    {'action': '确认支付失败页样本入口', 'owner': '运营', 'timeline': 'T+3天', 'metric': '入口评审通过', 'evidence_refs': ['Q9']},
                    {'action': '制定延时触发规则', 'owner': '研究', 'timeline': 'T+5天', 'metric': '形成触发规则', 'evidence_refs': ['Q10']},
                    {'action': '完成混合复现原型', 'owner': '设计', 'timeline': 'T+7天', 'metric': '可点击原型就绪', 'evidence_refs': ['Q11']},
                    {'action': '启动首轮试点访谈', 'owner': '研究+运营', 'timeline': 'T+14天', 'metric': '回收首批有效样本', 'evidence_refs': ['Q12']},
                ],
            ),
        )

        proposal_brief = payload.get('proposal_brief', {}) or {}
        chapter_copy = payload.get('chapter_copy', {}) or {}
        proposal_page = payload.get('proposal_page', {}) or {}
        proposal_support = payload.get('proposal_support', {}) or {}
        decision_brief = payload.get('decision_brief', {}) or {}
        narrative_outline = payload.get('narrative_outline', {}) or {}
        page_copy = payload.get('page_copy', {}) or {}
        proposal_content_model = payload.get('proposal_content_model', {}) or {}
        content_priority_plan = payload.get('content_priority_plan', {}) or {}
        closing_block = payload.get('closing_block', {}) or {}
        summary_card = payload.get('summary_card', {}) or {}
        render_model = payload.get('render_model', {}) or {}
        audience_profile = payload.get('audience_profile', {}) or {}
        comparison_matrix = payload.get('comparison_matrix', {}) or {}
        value_board = payload.get('value_board', {}) or {}
        quality_review = payload.get('quality_review', {}) or {}
        chapters = chapter_copy.get('chapters', []) or []
        chapter_ids = [item.get('id') for item in chapters]

        self.assertTrue(proposal_brief.get('thesis', {}).get('headline'))
        self.assertGreaterEqual(len(proposal_brief.get('options', [])), 2)
        self.assertGreaterEqual(len(proposal_brief.get('workstreams', [])), 3)
        self.assertGreaterEqual(len(proposal_brief.get('value_model', [])), 3)
        self.assertEqual(payload.get('proposal_version'), 'decision_v1')
        self.assertEqual(len(chapters), 8)
        self.assertEqual(chapter_ids, ['hero', 'why_now', 'comparison', 'blueprint', 'workstreams', 'integration', 'roadmap', 'value_fit'])
        self.assertEqual(proposal_page.get('theme'), 'executive_dark_editorial')
        self.assertEqual(decision_brief.get('version'), 'decision_v1')
        self.assertEqual(narrative_outline.get('version'), 'decision_v1')
        self.assertEqual([item.get('id') for item in proposal_page.get('nav_items', [])], ['overview', 'urgency', 'comparison', 'delivery', 'value', 'closing'])
        self.assertEqual([item.get('id') for item in (narrative_outline.get('chapters', []) or [])], ['overview', 'urgency', 'comparison', 'delivery', 'value', 'closing'])
        self.assertTrue(decision_brief.get('insight_line'))
        self.assertGreaterEqual(len(decision_brief.get('trust_signals', [])), 2)
        self.assertTrue(page_copy.get('overview', {}).get('title'))
        self.assertTrue(page_copy.get('overview', {}).get('insightLine'))
        self.assertGreaterEqual(len(page_copy.get('overview', {}).get('trustSignals', [])), 2)
        self.assertEqual((((page_copy.get('urgency', {}) or {}).get('cards') or [])[0] or {}).get('tag'), '结构性矛盾')
        self.assertEqual((((page_copy.get('urgency', {}) or {}).get('cards') or [None, None])[1] or {}).get('tag'), '当前窗口')
        self.assertEqual((((page_copy.get('urgency', {}) or {}).get('cards') or [None, None, None])[2] or {}).get('tag'), '延迟代价')
        self.assertIn('derived', proposal_support)
        self.assertTrue((proposal_support.get('derived', {}) or {}).get('workstream_cards'))
        self.assertTrue((proposal_support.get('derived', {}) or {}).get('milestones'))
        self.assertEqual(proposal_content_model.get('version'), 'v2')
        self.assertIn('hero', proposal_content_model.get('chapters', {}))
        self.assertEqual(content_priority_plan.get('version'), 'decision_v1')
        self.assertIn('overview', content_priority_plan.get('chapters', {}))
        self.assertTrue(closing_block.get('headline'))
        self.assertTrue(closing_block.get('decision'))
        self.assertTrue(summary_card.get('title'))
        self.assertGreaterEqual(len(summary_card.get('bullets', [])), 2)
        self.assertEqual(render_model.get('mode'), 'decision_v1')
        self.assertTrue(render_model.get('overview', {}).get('insightLine'))
        self.assertGreaterEqual(len(render_model.get('overview', {}).get('trustSignals', [])), 2)
        self.assertTrue(render_model.get('closing', {}).get('headline'))
        self.assertIn('建议', render_model.get('closing', {}).get('decision', ''))
        self.assertTrue(render_model.get('summaryCard', {}).get('title'))
        self.assertEqual((render_model.get('navItems', []) or [])[-1].get('id'), 'closing')
        self.assertTrue(render_model.get('urgency', {}).get('cards'))
        self.assertTrue(render_model.get('delivery', {}).get('workstreams'))
        self.assertTrue(render_model.get('value', {}).get('fitCards'))
        self.assertEqual(audience_profile.get('key'), proposal_page.get('audience_profile', {}).get('key'))
        self.assertTrue(audience_profile.get('label'))
        self.assertGreaterEqual(len(comparison_matrix.get('rows', [])), 5)
        self.assertGreaterEqual(len(value_board.get('items', [])), 3)
        self.assertIn(quality_review.get('status'), {'strong', 'solid', 'needs_polish'})
        self.assertIn('overall_score', quality_review)

    def test_structured_sidecar_rule_copy_avoids_internal_implementation_terms(self):
        payload = self._write_structured_sidecar(
            'proposal-rule-copy.md',
            self._build_snapshot(
                'proposal-rule-copy.md',
                topic='交易支付风控体验优化',
                scenario_name='交互式访谈',
                overview='当前需要先锁定高价值样本、真实触发时机和混合复现路径，才能解释用户为什么放弃支付而非申诉。',
                needs=[
                    {'priority': 'P0', 'name': '高价值样本招募更精准', 'description': '先锁定真实被拦截用户。', 'evidence_refs': ['Q1']},
                    {'priority': 'P0', 'name': '触发时机更贴近真实决策瞬间', 'description': '不能过早也不能过晚。', 'evidence_refs': ['Q2']},
                    {'priority': 'P1', 'name': '复现方式兼顾深度与成本', 'description': '高保真和低保真需要组合。', 'evidence_refs': ['Q3']},
                ],
                solutions=[
                    {'title': '建立高价值样本招募通道', 'description': '围绕支付失败页和拦截页组织样本入口。', 'owner': '运营', 'timeline': '第1周', 'metric': '形成首批样本池', 'evidence_refs': ['Q4']},
                    {'title': '设计延时触发策略', 'description': '在高信号时刻触发访谈，减少体验干扰。', 'owner': '研究', 'timeline': '第2周', 'metric': '触发命中率提升', 'evidence_refs': ['Q5']},
                    {'title': '搭建混合复现机制', 'description': '结合低保真原型和录屏回放提取真实变量。', 'owner': '设计+研究', 'timeline': '第3周', 'metric': '形成首轮归因洞察', 'evidence_refs': ['Q6']},
                ],
                risks=[
                    {'risk': '真实样本不足', 'impact': '结论失真', 'mitigation': '先锁定高价值入口', 'evidence_refs': ['Q7']},
                    {'risk': '合规评审拖慢试点', 'impact': '周期拉长', 'mitigation': '提前完成脱敏与评审', 'evidence_refs': ['Q8']},
                ],
                actions=[
                    {'action': '确认支付失败页样本入口', 'owner': '运营', 'timeline': 'T+3天', 'metric': '入口评审通过', 'evidence_refs': ['Q9']},
                    {'action': '制定延时触发规则', 'owner': '研究', 'timeline': 'T+5天', 'metric': '形成触发规则', 'evidence_refs': ['Q10']},
                    {'action': '完成混合复现原型', 'owner': '设计', 'timeline': 'T+7天', 'metric': '可点击原型就绪', 'evidence_refs': ['Q11']},
                    {'action': '启动首轮试点访谈', 'owner': '研究+运营', 'timeline': 'T+14天', 'metric': '回收首批有效样本', 'evidence_refs': ['Q12']},
                ],
            ),
        )

        proposal_text = json.dumps([
            payload.get('proposal_brief', {}),
            payload.get('chapter_copy', {}),
        ], ensure_ascii=False)

        self.assertNotIn('结构化素材', proposal_text)
        self.assertNotIn('页面骨架', proposal_text)
        self.assertNotIn('渲染', proposal_text)

    def test_real_ai_platform_report_compresses_business_titles(self):
        report_path = ROOT_DIR / "data" / "reports" / "deep-vision-20260314-e2a4fd23-交互式访谈-AI-智能体需求调研.md.solution.json"
        snapshot = json.loads(report_path.read_text(encoding="utf-8"))

        self.assertEqual(self.server._proposal_focus_label("MLOps/LLMOps平台优先建设"), "AI工程底座")
        self.assertEqual(
            self.server._proposal_boundary_label("历史代码库依赖深，存量模型迁移复杂；基础设施/算力不足；需平衡重构风险与业务连续..."),
            "迁移复杂、算力受限、兼顾连续性",
        )

        proposal_brief = self.server.build_solution_proposal_brief(snapshot, quality_signals={}, source_mode='structured_sidecar')
        chapter_copy = self.server.build_solution_chapter_copy(snapshot, proposal_brief, quality_signals={})
        proposal_page = self.server.build_solution_proposal_page(snapshot, proposal_brief, chapter_copy)
        chapters = {item.get('id'): item for item in chapter_copy.get('chapters', []) if isinstance(item, dict)}
        render_model = proposal_page.get('render_model', {}) if isinstance(proposal_page, dict) else {}
        decision_brief = proposal_page.get('decision_brief', {}) if isinstance(proposal_page, dict) else {}
        delivery_render = render_model.get('delivery', {}) or {}
        comparison_render = render_model.get('comparison', {}) or {}
        value_render = render_model.get('value', {}) or {}

        self.assertIn('AI工程底座', proposal_brief.get('thesis', {}).get('headline', ''))
        self.assertNotIn('MLOps/LLMOps', proposal_brief.get('thesis', {}).get('headline', ''))
        self.assertLessEqual(len(proposal_brief.get('thesis', {}).get('headline', '')), 60)
        self.assertIn('AI工程底座', proposal_brief.get('thesis', {}).get('core_decision', ''))
        self.assertIn('迁移复杂、算力受限、兼顾连续性', proposal_brief.get('thesis', {}).get('core_decision', ''))
        self.assertIn('人才短缺、算力受限和历史迁移压力', proposal_brief.get('thesis', {}).get('why_now', ''))
        self.assertIn('分层架构', proposal_brief.get('recommended_solution', {}).get('architecture_statement', ''))
        self.assertIn('接口治理', proposal_brief.get('recommended_solution', {}).get('architecture_statement', ''))
        self.assertIn('AI工程底座', decision_brief.get('insight_line', ''))
        self.assertGreaterEqual(len(decision_brief.get('trust_signals', [])), 2)
        self.assertEqual((chapters.get('comparison') or {}).get('title'), '为什么选「AI工程底座」这条路')
        self.assertIn('AI工程底座', (chapters.get('comparison') or {}).get('judgement', ''))
        self.assertIn('难以直接形成可评审方案', ((((chapters.get('comparison') or {}).get('cards') or [])[0]) or {}).get('desc', ''))
        self.assertIn('更适合：', ((((chapters.get('comparison') or {}).get('cards') or [None, None])[1]) or {}).get('meta', ''))
        self.assertNotIn('MLOps/LLMOps', json.dumps((chapters.get('comparison') or {}).get('cards', []), ensure_ascii=False))
        self.assertEqual((((chapters.get('hero') or {}).get('cards') or [])[0] or {}).get('meta'), '迁移复杂、算力受限、兼顾连续性')
        self.assertEqual((((chapters.get('why_now') or {}).get('cards') or [])[2] or {}).get('title'), '混合云能力')
        self.assertEqual((((chapters.get('why_now') or {}).get('cards') or [])[3] or {}).get('title'), '接口治理')
        self.assertEqual((((chapters.get('why_now') or {}).get('cards') or [])[0] or {}).get('meta'), 'Q4 · Q6')
        self.assertEqual((chapters.get('blueprint') or {}).get('title'), '推荐蓝图：先稳住「AI工程底座」，再拉通「分层架构」')
        self.assertIn('接口治理', ((chapters.get('blueprint') or {}).get('diagram') or {}).get('caption', ''))
        self.assertNotIn('MLOps/LLMOps', json.dumps((chapters.get('blueprint') or {}).get('cards', []), ensure_ascii=False))
        self.assertEqual((((chapters.get('blueprint') or {}).get('cards') or [])[0] or {}).get('tag'), '能力底座')
        self.assertEqual((chapters.get('integration') or {}).get('title'), '把「AI工程底座」接进系统闭环')
        self.assertIn('系统闭环', (chapters.get('integration') or {}).get('title', ''))
        self.assertIn('组织效率', ((chapters.get('integration') or {}).get('diagram') or {}).get('caption', ''))
        self.assertEqual((chapters.get('value_fit') or {}).get('title'), '为什么这条路径更适合当前团队进入试点决策阶段')
        self.assertNotIn('MLOps/LLMOps', (chapters.get('value_fit') or {}).get('title', ''))
        self.assertEqual((((chapters.get('hero') or {}).get('metrics') or [])[1] or {}).get('label'), 'AI工程底座建设节奏')
        self.assertIn('完成平台POC', (((chapters.get('hero') or {}).get('metrics') or [])[1] or {}).get('value', ''))
        self.assertIn('前提：试点样本真实可控', (((chapters.get('hero') or {}).get('metrics') or [])[1] or {}).get('note', ''))
        self.assertIn('迁移复杂、算力受限、兼顾连续性', (((chapters.get('value_fit') or {}).get('cards') or [])[2] or {}).get('desc', ''))
        tabs = (delivery_render.get('workstreams', []) or [])
        left_option = comparison_render.get('left', {}) or {}
        right_option = comparison_render.get('right', {}) or {}
        boundary_cards = value_render.get('boundaryCards', []) or []
        self.assertEqual((render_model.get('overview', {}) or {}).get('title'), '为什么当前先做「AI工程底座」')
        self.assertEqual((render_model.get('urgency', {}) or {}).get('title'), '为什么现在要先锁定「AI工程底座」')
        self.assertEqual(comparison_render.get('title'), '为什么选「AI工程底座」这条路')
        self.assertEqual(comparison_render.get('judgement'), '先把「AI工程底座」试点跑通，再判断第二阶段投入，边界先锁定在「迁移复杂、算力受限」')
        self.assertIn('AI工程底座', (render_model.get('overview', {}) or {}).get('insightLine', ''))
        self.assertGreaterEqual(len((render_model.get('overview', {}) or {}).get('trustSignals', [])), 2)
        self.assertEqual((tabs[0] if len(tabs) > 0 else {}).get('headline'), 'AI工程底座优先建设')
        self.assertEqual((tabs[1] if len(tabs) > 1 else {}).get('headline'), '分层架构')
        self.assertEqual((tabs[2] if len(tabs) > 2 else {}).get('headline'), '接口治理')
        self.assertEqual(len((tabs[0] if len(tabs) > 0 else {}).get('capabilities', [])), 2)
        self.assertNotEqual(
            (((tabs[0] if len(tabs) > 0 else {}).get('capabilities') or [None])[0] or {}).get('desc'),
            (((tabs[0] if len(tabs) > 0 else {}).get('capabilities') or [None])[0] or {}).get('title'),
        )
        self.assertEqual((left_option.get('pros', []) or [None])[0], '启动最快')
        self.assertEqual((left_option.get('pros', []) or [None, None])[1], '适合早期探索')
        self.assertEqual((left_option.get('cons', []) or [None])[0], '难解释核心问题')
        self.assertEqual((right_option.get('pros', []) or [None])[0], '兼顾深度与落地')
        self.assertEqual((right_option.get('cons', []) or [None])[0], '边界需要先对齐')
        self.assertEqual((tabs[0] if len(tabs) > 0 else {}).get('owner'), '平台团队主责')
        self.assertEqual((((tabs[0] if len(tabs) > 0 else {}).get('dependencies') or [None]))[0], '迁移范围先锁定')
        self.assertEqual((((tabs[0] if len(tabs) > 0 else {}).get('deliverables') or [None]))[0], '核心流水线跑通')
        self.assertEqual((((tabs[0] if len(tabs) > 0 else {}).get('metrics') or [None]))[0], {'metric': '验收信号 01', 'target': '上线周期压到天级', 'note': '人工干预同步下降'})
        self.assertEqual((tabs[1] if len(tabs) > 1 else {}).get('owner'), '架构与稳定性')
        self.assertEqual((((tabs[1] if len(tabs) > 1 else {}).get('dependencies') or [None]))[0], '迁移范围先锁定')
        self.assertEqual((((tabs[1] if len(tabs) > 1 else {}).get('deliverables') or [None]))[0], '性能与切换达标')
        self.assertEqual((((tabs[1] if len(tabs) > 1 else {}).get('metrics') or [None]))[0], {'metric': '验收信号 01', 'target': '性能与切换达标', 'note': '核心时延与切换双达标'})
        self.assertEqual((tabs[2] if len(tabs) > 2 else {}).get('owner'), '平台与各层协同')
        self.assertEqual((((tabs[2] if len(tabs) > 2 else {}).get('dependencies') or [None]))[0], '迁移范围先锁定')
        self.assertEqual((((tabs[2] if len(tabs) > 2 else {}).get('deliverables') or [None]))[0], '契约与集成过线')
        self.assertEqual((((tabs[2] if len(tabs) > 2 else {}).get('metrics') or [None]))[0], {'metric': '验收信号 01', 'target': '契约与集成过线', 'note': '覆盖率和测试都过线'})
        self.assertTrue(value_render.get('fitCards'))
        self.assertIn('先补培训和研究侧补位', (((boundary_cards or [])[0]) or {}).get('desc', ''))
        self.assertIn('先设接口评审和协作门禁', (((boundary_cards or [None, None])[1]) or {}).get('desc', ''))
        self.assertNotIn('MLOps/LLMOps', json.dumps(value_render.get('fitCards', []), ensure_ascii=False))
        self.assertIn('批准', (render_model.get('closing', {}) or {}).get('decision', ''))
        self.assertNotEqual((render_model.get('closing', {}) or {}).get('headline'), comparison_render.get('judgement'))
        self.assertNotEqual((render_model.get('closing', {}) or {}).get('decision'), comparison_render.get('judgement'))

    def test_page_copy_v1_dedupes_delivery_and_value_content(self):
        decision_brief = {
            'core_conflicts': ['MVP验证期核心开发时间被反馈处理大量占用'],
            'why_now': '当前需要先锁定高信号试点范围，再决定是否扩大投入。',
            'chosen_path': {'name': '私有渠道优先切口', 'positioning': '先用私有渠道冻结边界'},
            'delivery_support': {
                'workstreams': [
                    {
                        'label': '完成数据辅助决策场景详细需求文档，Q2完成校准',
                        'headline': 'PRD文档',
                        'summary': 'PRD文档',
                        'owner': '产品经理',
                        'dependencies': ['PRD文档'],
                        'deliverables': ['PRD文档'],
                        'capabilities': [
                            {'tag': '关键动作', 'title': 'PRD文档', 'desc': 'PRD文档'},
                            {'tag': '交付物', 'title': 'PRD文档', 'desc': 'PRD文档'},
                        ],
                        'metrics': [
                            {'metric': 'PRD文档', 'target': 'PRD文档', 'note': 'PRD文档'},
                            {'metric': 'PRD文档', 'target': 'PRD文档', 'note': 'PRD文档'},
                        ],
                    }
                ],
                'phases': [],
            },
            'value_support': {
                'metrics': [
                    {'metric': '用户二次投诉率', 'target': '<5%', 'note': '前提：紧急退出机制有效运行'},
                    {'metric': '用户二次投诉率', 'target': '<5%', 'note': '前提：紧急退出机制有效运行'},
                ],
                'fit_cards': [
                    {'tag': '适配理由', 'title': '窗口期匹配', 'desc': '窗口期匹配'},
                    {'tag': '适配理由', 'title': '窗口期匹配', 'desc': '窗口期匹配'},
                ],
                'boundary_cards': [
                    {'tag': '边界', 'title': '样本偏差风险', 'desc': '先优先锁定真实样本入口'},
                    {'tag': '边界', 'title': '二次创伤边界', 'desc': '先优先锁定真实场景触发'},
                ],
            },
            'boundaries': [{'title': '样本偏差风险', 'detail': '先优先锁定真实样本入口'}],
        }
        page_copy = self.server.build_solution_page_copy_v1(
            decision_brief,
            {'overview': {'title': '为什么现在做', 'metrics': []}, 'comparison': {}},
            {},
            {},
            {'headline': '先锁定试点边界', 'decision': '当前建议先批准首轮试点', 'boundary': '样本边界需要前置锁定'},
            {},
            {'key': 'decision_maker', 'label': '决策层视角'},
        )

        workstream = (((page_copy.get('delivery', {}) or {}).get('workstreams', []) or [{}])[0]) or {}
        value = page_copy.get('value', {}) or {}
        self.assertNotEqual(workstream.get('summary'), workstream.get('headline'))
        self.assertLessEqual(len(workstream.get('metaPills', []) or []), 2)
        self.assertLessEqual(len(workstream.get('capabilities', []) or []), 2)
        self.assertEqual(len(workstream.get('metrics', []) or []), 1)
        self.assertLessEqual(len(workstream.get('tabTag', '') or ''), 12)
        self.assertNotIn('...', workstream.get('tabTag', '') or '')
        self.assertNotIn('...', workstream.get('tag', '') or '')
        self.assertFalse(any(
            (item or {}).get('title') == (item or {}).get('desc')
            for item in (workstream.get('capabilities', []) or [])
        ))
        self.assertEqual((value.get('metrics', []) or [{}])[0].get('target'), '<5%')
        self.assertEqual(len(value.get('metrics', []) or []), 1)
        self.assertEqual(len(value.get('fitCards', []) or []), 1)
        self.assertTrue(all(not item.get('tag') for item in (value.get('boundaryCards', []) or [])))

    def test_page_copy_v1_preserves_boundary_detail_from_boundaries_fallback(self):
        decision_brief = {
            'core_conflicts': ['高风险样本入口仍不稳定'],
            'why_now': '当前需要先锁定边界，再决定是否扩大范围。',
            'chosen_path': {'name': '高信号试点切口', 'positioning': '先冻结高风险入口'},
            'delivery_support': {'workstreams': [], 'phases': []},
            'value_support': {'metrics': [], 'fit_cards': []},
            'boundaries': [{'title': '样本偏差风险', 'detail': '先优先锁定真实样本入口'}],
        }
        page_copy = self.server.build_solution_page_copy_v1(
            decision_brief,
            {'overview': {'title': '为什么现在做', 'metrics': []}, 'comparison': {}},
            {},
            {},
            {'headline': '先锁定试点边界', 'decision': '当前建议先批准首轮试点', 'boundary': '样本边界需要前置锁定'},
            {},
            {'key': 'decision_maker', 'label': '决策层视角'},
        )

        boundary = ((((page_copy.get('value', {}) or {}).get('boundaryCards', []) or [{}])[0])) or {}
        self.assertEqual(boundary.get('title'), '样本偏差风险')
        self.assertEqual(boundary.get('desc'), '先优先锁定真实样本入口')

    def test_ai_prompts_include_sample_style_guidance(self):
        prompt_payload = {
            "meta": {"topic": "AI 智能体建设"},
            "audience_profile": {"key": "decision_maker", "label": "决策层视角"},
            "quality_signals": {"fallback_ratio": 0.0},
            "metric_cards": [{"label": "试点速度", "value": "8周"}],
        }
        proposal_prompt = self.server.build_solution_proposal_brief_ai_prompt(prompt_payload)
        chapter_prompt = self.server.build_solution_chapter_copy_ai_prompt(
            {"meta": {"topic": "AI 智能体建设"}, "thesis": {"headline": "测试标题"}},
            prompt_payload,
        )
        review_prompt = self.server.build_solution_quality_review_ai_prompt(
            {"meta": {"topic": "AI 智能体建设"}},
            {"chapters": [{"id": "hero", "title": "测试标题"}]},
            prompt_payload,
            {"status": "solid", "overall_score": 0.76},
        )

        self.assertIn('参考写法', proposal_prompt)
        self.assertIn('AI工程底座', proposal_prompt)
        self.assertIn('可复制推进', proposal_prompt)
        self.assertIn('audience_profile', proposal_prompt)
        self.assertIn('推荐蓝图：先稳住「AI工程底座」，再拉通「分层架构」', chapter_prompt)
        self.assertIn('把「支付失败页入口」接进系统闭环', chapter_prompt)
        self.assertIn('chapter_updates', review_prompt)
        self.assertIn('当前启发式审查结果', review_prompt)

    def test_auto_infers_execution_audience_for_action_heavy_snapshot(self):
        snapshot = self._build_snapshot(
            'proposal-audience.md',
            topic='客服知识接入提效',
            scenario_name='交互式访谈',
            overview='当前需要围绕客服接待流程冻结接口、负责人、上线节奏和回滚方案。',
            needs=[
                {'priority': 'P0', 'name': '客服入口稳定', 'description': '保证工单与IM入口都可接入。', 'evidence_refs': ['Q1']},
                {'priority': 'P0', 'name': '负责人明确', 'description': '每个动作都有 owner。', 'evidence_refs': ['Q2']},
            ],
            solutions=[
                {'title': '接入客服工单接口', 'description': '研发完成接口接入与埋点。', 'owner': '研发', 'timeline': '第1周', 'metric': '接口联调通过', 'evidence_refs': ['Q3']},
                {'title': '建立知识回流规则', 'description': '运营和客服共同补充知识反馈。', 'owner': '运营+客服', 'timeline': '第2周', 'metric': '首轮知识回流完成', 'evidence_refs': ['Q4']},
            ],
            actions=[
                {'action': '冻结接口字段', 'owner': '研发', 'timeline': 'T+2天', 'metric': '接口定义确认', 'evidence_refs': ['Q5']},
                {'action': '确认负责人矩阵', 'owner': '项目经理', 'timeline': 'T+3天', 'metric': '角色矩阵通过', 'evidence_refs': ['Q6']},
                {'action': '完成联调', 'owner': '研发', 'timeline': 'T+5天', 'metric': '联调通过', 'evidence_refs': ['Q7']},
                {'action': '安排上线窗口', 'owner': '运维', 'timeline': 'T+7天', 'metric': '上线计划锁定', 'evidence_refs': ['Q8']},
                {'action': '执行回滚演练', 'owner': '运维', 'timeline': 'T+8天', 'metric': '回滚方案通过', 'evidence_refs': ['Q9']},
            ],
        )
        profile = self.server.infer_solution_audience_profile(snapshot, quality_signals={})
        self.assertEqual(profile.get('key'), 'execution')
        self.assertEqual(profile.get('proposal_goal'), '试点推进')

    def test_structured_sidecar_prefers_ai_generated_proposal_and_chapter_copy(self):
        snapshot = self._build_snapshot(
            'proposal-ai.md',
            topic='交易支付风控体验优化',
            scenario_name='交互式访谈',
            overview='当前需要围绕真实拦截场景建立高信号试点，再决定是否扩大范围。',
            needs=[
                {'priority': 'P0', 'name': '高价值样本入口稳定', 'description': '先锁定真实被拦截用户。', 'evidence_refs': ['Q1']},
                {'priority': 'P0', 'name': '触发时机贴近决策瞬间', 'description': '避免过早或过晚触达。', 'evidence_refs': ['Q2']},
                {'priority': 'P1', 'name': '复现方式兼顾成本和深度', 'description': '低保真与高保真结合。', 'evidence_refs': ['Q3']},
            ],
            solutions=[
                {'title': '建立失败页高信号入口', 'description': '从最接近决策瞬间的页面切入。', 'owner': '运营', 'timeline': '第1周', 'metric': '入口评审通过', 'evidence_refs': ['Q4']},
                {'title': '设计延迟触发规则', 'description': '让访谈触达更贴近真实体验。', 'owner': '研究', 'timeline': '第2周', 'metric': '触发命中率提升', 'evidence_refs': ['Q5']},
                {'title': '搭建混合复现机制', 'description': '原型、录屏和回访脚本共同工作。', 'owner': '设计', 'timeline': '第3周', 'metric': '形成首轮洞察', 'evidence_refs': ['Q6']},
            ],
            risks=[
                {'risk': '真实样本不足', 'impact': '结论偏差', 'mitigation': '先锁定高价值入口', 'evidence_refs': ['Q7']},
                {'risk': '合规评审拖慢试点', 'impact': '排期拉长', 'mitigation': '前置脱敏和法务评审', 'evidence_refs': ['Q8']},
            ],
            actions=[
                {'action': '确认支付失败页样本入口', 'owner': '运营', 'timeline': 'T+3天', 'metric': '入口评审通过', 'evidence_refs': ['Q9']},
                {'action': '冻结延迟触发规则', 'owner': '研究', 'timeline': 'T+5天', 'metric': '规则确认', 'evidence_refs': ['Q10']},
                {'action': '完成混合复现原型', 'owner': '设计', 'timeline': 'T+7天', 'metric': '原型可试跑', 'evidence_refs': ['Q11']},
                {'action': '启动首轮试点访谈', 'owner': '研究+运营', 'timeline': 'T+14天', 'metric': '回收首批有效样本', 'evidence_refs': ['Q12']},
            ],
        )
        brief_response = {
            "meta": {
                "topic": "交易支付风控体验优化",
                "audience": "decision_maker",
                "proposal_goal": "内部共识",
                "confidence": 0.91,
            },
            "thesis": {
                "headline": "先围绕支付失败页完成高信号试点，再决定是否扩大风控体验改造",
                "subheadline": "当前最需要的不是继续收集泛样本，而是把最接近用户放弃瞬间的场景真正跑通。",
                "why_now": "关键入口、样本信号和约束边界已经足够清楚，适合进入提案和试点设计。",
                "core_decision": "建议以支付失败页为首轮试点切口，优先验证真实拦截场景下的放弃与申诉分流逻辑。",
            },
            "context": {
                "business_scene": "交易支付风控体验",
                "current_state": ["高价值样本仍然稀缺", "触发时机影响用户配合度", "复现成本高于预期"],
                "core_conflicts": ["要贴近真实决策瞬间，但又不能打扰用户", "要保证深度，还要控制试点投入"],
                "constraints": ["首轮试点只覆盖单一入口", "所有数据必须完成脱敏和审计"],
                "evidence_refs": ["Q1", "Q2", "Q7"],
            },
            "options": [
                {"name": "保守路径", "positioning": "先做泛样本收集", "pros": ["启动快"], "cons": ["难以解释真实放弃原因"], "fit_for": "只需要方向判断", "not_fit_for": "需要进入试点评审", "decision": "alternative", "evidence_refs": ["Q1"]},
                {"name": "失败页闭环试点", "positioning": "围绕支付失败页建立高信号试点闭环", "pros": ["最接近真实决策", "能同时沉淀规则和样本"], "cons": ["需要跨团队协调"], "fit_for": "希望尽快进入试点评审的团队", "not_fit_for": "无法获得真实入口的项目", "decision": "recommended", "evidence_refs": ["Q4", "Q9"]},
                {"name": "激进全量改造", "positioning": "直接重构全链路体验", "pros": ["覆盖面最大"], "cons": ["投入过高", "返工风险高"], "fit_for": "长期专项", "not_fit_for": "当前试点阶段", "decision": "rejected", "evidence_refs": ["Q7", "Q8"]},
            ],
            "recommended_solution": {
                "north_star": "把风控体验从一次性调研升级为可复用的试点能力。",
                "architecture_statement": "以支付失败页为入口，把样本获取、触发、复现和价值复盘连成闭环。",
                "modules": [
                    {"name": "样本入口治理", "objective": "锁定真实高价值样本入口", "acceptance_signals": ["入口评审通过"]},
                    {"name": "触发策略治理", "objective": "让触达更贴近真实决策瞬间", "acceptance_signals": ["触发命中率提升"]},
                    {"name": "混合复现机制", "objective": "在成本可控前提下还原真实路径", "acceptance_signals": ["首轮洞察产出"]},
                ],
                "integration_points": ["支付失败页入口", "延迟触发规则", "混合复现原型", "试点复盘机制"],
                "dataflow": ["入口触发", "样本筛选", "访谈执行", "复盘沉淀"],
                "governance": ["先完成脱敏评审", "先锁定试点范围"],
                "evidence_refs": ["Q4", "Q5", "Q6"],
            },
            "workstreams": [
                {"name": "样本入口治理", "objective": "锁定真实高价值样本入口", "key_actions": ["确认支付失败页入口", "建立样本筛选规则"], "deliverables": ["样本入口清单"], "owner_role": "运营", "timeline": "第1周", "dependencies": ["法务确认"], "acceptance_signals": ["入口评审通过"], "evidence_refs": ["Q4", "Q9"]},
                {"name": "触发策略治理", "objective": "让触达更贴近真实决策瞬间", "key_actions": ["冻结延迟触发规则", "验证不同时机触达"], "deliverables": ["触发规则说明"], "owner_role": "研究", "timeline": "第2周", "dependencies": ["样本入口稳定"], "acceptance_signals": ["触发命中率提升"], "evidence_refs": ["Q5", "Q10"]},
                {"name": "混合复现机制", "objective": "兼顾成本和深度还原真实路径", "key_actions": ["完成混合复现原型", "启动首轮试点"], "deliverables": ["可试跑原型"], "owner_role": "设计+研究", "timeline": "第3周", "dependencies": ["触发规则冻结"], "acceptance_signals": ["形成首轮洞察"], "evidence_refs": ["Q6", "Q11"]},
            ],
            "value_model": [
                {"metric": "试点推进速度", "baseline": "仍需多轮会议对齐", "target": "8周内形成闭环试点", "range": "3阶段推进", "assumptions": ["入口可用"], "evidence_refs": ["Q9"]},
                {"metric": "高价值洞察密度", "baseline": "泛样本噪声高", "target": "围绕真实失败场景形成结构化结论", "range": "3个核心工作流", "assumptions": ["样本质量稳定"], "evidence_refs": ["Q1", "Q4"]},
                {"metric": "证据绑定率", "baseline": "关键判断依赖人工翻阅", "target": "核心章节持续绑定 Q 编号", "range": "保持高证据密度", "assumptions": ["结构化条目持续完善"], "evidence_refs": ["Q4", "Q7"]},
            ],
            "fit_reasons": [
                {"title": "关键切口已经收敛", "detail": "支付失败页已经成为最清晰的试点入口。", "evidence_refs": ["Q4", "Q9"]},
                {"title": "约束边界已经显性化", "detail": "脱敏和单入口试点边界都可以提前锁定。", "evidence_refs": ["Q7", "Q8"]},
                {"title": "结构化素材足以支撑提案", "detail": "当前已有需求、方案、动作和风险四套结构化条目。", "evidence_refs": ["Q1", "Q4", "Q9"]},
            ],
            "risks_and_boundaries": [
                {"title": "真实样本不足", "detail": "如果入口无法锁定，结论会快速失真。", "type": "risk", "evidence_refs": ["Q7"]},
                {"title": "试点边界", "detail": "首轮只覆盖支付失败页，不做全链路改造。", "type": "boundary", "evidence_refs": ["Q8"]},
            ],
            "next_steps": [
                {"phase": "Phase 1｜范围冻结", "goal": "锁定入口、样本和规则边界", "actions": ["确认入口", "完成法务评审"], "milestone": "范围冻结完成", "evidence_refs": ["Q9"]},
                {"phase": "Phase 2｜试点执行", "goal": "完成触发策略与混合复现试跑", "actions": ["冻结触发规则", "完成原型"], "milestone": "首轮试点启动", "evidence_refs": ["Q10", "Q11"]},
                {"phase": "Phase 3｜价值复盘", "goal": "复盘高价值洞察与扩展条件", "actions": ["回收洞察", "评估是否扩展"], "milestone": "二期建议形成", "evidence_refs": ["Q12"]},
            ],
        }
        chapter_ids = ['hero', 'why_now', 'comparison', 'blueprint', 'workstreams', 'integration', 'roadmap', 'value_fit']
        chapter_layouts = ['hero_metrics', 'conflict_cards', 'dual_comparison', 'blueprint_diagram', 'tabbed_cards', 'loop_diagram', 'phased_timeline', 'value_grid']
        chapter_response = {
            "meta": {"theme": "executive_dark_editorial", "tone": "judgemental_clear_premium", "nav_style": "sticky"},
            "chapters": [
                {
                    "id": chapter_id,
                    "nav_label": f"章节{index + 1}",
                    "eyebrow": "AI 提案页",
                    "title": "AI 生成的判断标题" if chapter_id == 'hero' else f"{chapter_id} 章节标题",
                    "judgement": f"{chapter_id} 的 AI 判断句",
                    "summary": f"{chapter_id} 的 AI 概述",
                    "layout": chapter_layouts[index],
                    "metrics": [
                        {"label": "指标A", "value": "80%", "delta": "", "note": "说明A"},
                        {"label": "指标B", "value": "3阶段", "delta": "", "note": "说明B"},
                        {"label": "指标C", "value": "高", "delta": "", "note": "说明C"},
                    ] if chapter_id == 'hero' else [],
                    "cards": [
                        {"title": f"{chapter_id} 卡片1", "desc": "AI 卡片描述 1", "tag": "AI", "meta": "meta1"},
                        {"title": f"{chapter_id} 卡片2", "desc": "AI 卡片描述 2", "tag": "AI", "meta": "meta2"},
                        {"title": f"{chapter_id} 卡片3", "desc": "AI 卡片描述 3", "tag": "AI", "meta": "meta3"},
                    ] if chapter_id in {'comparison', 'workstreams', 'value_fit'} else [
                        {"title": f"{chapter_id} 卡片1", "desc": "AI 卡片描述 1", "tag": "AI", "meta": "meta1"},
                        {"title": f"{chapter_id} 卡片2", "desc": "AI 卡片描述 2", "tag": "AI", "meta": "meta2"},
                    ],
                    "diagram": {
                        "type": "architecture" if chapter_id == 'blueprint' else ("loop" if chapter_id == 'integration' else ("timeline" if chapter_id == 'roadmap' else "flow")),
                        "nodes": [{"id": "n1", "label": "节点1"}, {"id": "n2", "label": "节点2"}],
                        "edges": [{"from": "n1", "to": "n2", "label": "推进"}],
                        "caption": "AI 图解说明",
                    } if chapter_id in {'blueprint', 'integration', 'roadmap'} else None,
                    "cta": {"label": "继续查看", "target": chapter_ids[(index + 1) % len(chapter_ids)]},
                    "evidence_refs": ["Q1", "Q4"],
                }
                for index, chapter_id in enumerate(chapter_ids)
            ],
        }
        review_response = {
            "audience": "decision_maker",
            "overall_score": 0.91,
            "status": "strong",
            "issues": [],
            "chapter_scores": [
                {"id": "hero", "score": 0.94, "issue": ""},
                {"id": "comparison", "score": 0.9, "issue": ""},
                {"id": "value_fit", "score": 0.89, "issue": ""},
            ],
            "chapter_updates": [
                {"id": "hero", "title": "AI 自审后的判断标题", "judgement": "AI 自审后的 hero 判断句", "summary": "AI 自审后的 hero 概述"}
            ],
        }

        def _fake_call_claude(_prompt, *args, **kwargs):
            call_type = kwargs.get('call_type', '')
            if call_type == 'report_solution_proposal_brief':
                return json.dumps(brief_response, ensure_ascii=False)
            if call_type == 'report_solution_chapter_copy':
                return json.dumps(chapter_response, ensure_ascii=False)
            if call_type == 'report_solution_quality_review':
                return json.dumps(review_response, ensure_ascii=False)
            return ''

        with patch.object(self.server, 'ENABLE_AI', True), \
             patch.object(self.server, 'HAS_ANTHROPIC', True), \
             patch.object(self.server, 'call_claude', new=_fake_call_claude):
            payload = self._write_structured_sidecar('proposal-ai.md', snapshot)

        proposal_brief = payload.get('proposal_brief', {}) or {}
        chapter_copy = payload.get('chapter_copy', {}) or {}
        quality_review = payload.get('quality_review', {}) or {}
        self.assertEqual(proposal_brief.get('meta', {}).get('generation_mode'), 'ai')
        self.assertEqual(chapter_copy.get('meta', {}).get('generation_mode'), 'ai')
        self.assertEqual(chapter_copy.get('meta', {}).get('review_mode'), 'ai')
        self.assertEqual(proposal_brief.get('thesis', {}).get('headline'), brief_response['thesis']['headline'])
        self.assertEqual((chapter_copy.get('chapters', [])[0] or {}).get('title'), 'AI自审后的判断标题')
        self.assertEqual(quality_review.get('review_mode'), 'ai')
        self.assertEqual(quality_review.get('status'), 'strong')
        self.assertEqual(payload.get('proposal_page', {}).get('theme'), 'executive_dark_editorial')
        self.assertEqual(payload.get('proposal_page', {}).get('proposal_version'), 'decision_v1')
        self.assertEqual([item.get('id') for item in payload.get('proposal_page', {}).get('nav_items', [])], ['overview', 'urgency', 'comparison', 'delivery', 'value', 'closing'])
        self.assertTrue(payload.get('closing_block', {}).get('headline'))
        self.assertTrue(payload.get('summary_card', {}).get('bullets'))
        self.assertTrue(payload.get('render_model', {}).get('overview', {}).get('title'))

    def test_ai_outputs_are_postprocessed_to_sample_business_tone(self):
        report_path = ROOT_DIR / "data" / "reports" / "deep-vision-20260314-e2a4fd23-交互式访谈-AI-智能体需求调研.md.solution.json"
        snapshot = json.loads(report_path.read_text(encoding="utf-8"))

        technical_brief_response = {
            "meta": {
                "topic": "交互式访谈 AI 智能体需求调研",
                "audience": "decision_maker",
                "proposal_goal": "内部共识",
                "confidence": 0.92,
            },
            "thesis": {
                "headline": "先完成「MLOps/LLMOps平台优先建设」和「分层解耦架构落地」双核心落地，再把交互式访谈AI智能体需求调研推进到全链路",
                "subheadline": "当前需要同步完成MLOps/LLMOps自动化平台、分层解耦架构落地、规格驱动化接口治理和自动化迁移工具链建设。",
                "why_now": "当前阶段需要优先完成MLOps/LLMOps平台、混合云资源调度能力和规格驱动化接口治理，避免后续返工。",
                "core_decision": "建议采用MLOps/LLMOps平台优先建设路径，在分层解耦架构落地与自动化迁移工具链建设同时推进的前提下扩大投入。",
            },
            "context": {
                "business_scene": "AI 平台升级",
                "current_state": ["MLOps/LLMOps平台与TensorFlow工程链路割裂"],
                "core_conflicts": ["OpenAPI/gRPC契约与CI门禁尚未统一"],
                "constraints": ["历史代码库依赖深，存量模型迁移复杂", "基础设施/算力不足"],
                "evidence_refs": ["Q4", "Q6"],
            },
            "options": [
                {"name": "保守路径", "positioning": "先完成泛化MLOps能力梳理", "pros": ["快"], "cons": ["浅"], "fit_for": "预算紧的团队", "not_fit_for": "需要试点评审的团队", "decision": "alternative", "evidence_refs": ["Q4"]},
                {"name": "MLOps/LLMOps平台优先建设路径", "positioning": "先完成MLOps/LLMOps自动化平台与分层解耦架构落地", "pros": ["全"], "cons": ["复杂"], "fit_for": "希望尽快推进试点评审的团队", "not_fit_for": "无法锁定范围的团队", "decision": "recommended", "evidence_refs": ["Q6"]},
                {"name": "激进路径", "positioning": "直接重构全链路", "pros": ["大"], "cons": ["风险高"], "fit_for": "长期专项", "not_fit_for": "当前阶段", "decision": "rejected", "evidence_refs": ["Q7"]},
            ],
            "recommended_solution": {
                "north_star": "让MLOps/LLMOps平台、分层解耦架构落地和自动化迁移工具链建设一起推进。",
                "architecture_statement": "通过MLOps/LLMOps平台优先建设、分层解耦架构落地、规格驱动化接口治理和自动化迁移工具链建设形成统一体系。",
                "modules": [
                    {"name": "MLOps/LLMOps平台优先建设", "objective": "完成平台与流水线统一", "acceptance_signals": ["平台 POC"]},
                    {"name": "分层解耦架构落地", "objective": "完成模型层、推理层和网关层拆分", "acceptance_signals": ["完成拆分"]},
                    {"name": "规格驱动化接口治理", "objective": "完成 OpenAPI/gRPC 契约与 CI 门禁接入", "acceptance_signals": ["契约稳定"]},
                ],
                "integration_points": ["MLOps/LLMOps平台优先建设", "分层解耦架构落地", "规格驱动化接口治理", "自动化迁移工具链建设"],
                "dataflow": ["训练", "验证", "部署", "监控"],
                "governance": ["OpenAPI/gRPC契约", "CI门禁"],
                "evidence_refs": ["Q4", "Q6"],
            },
            "workstreams": [
                {"name": "MLOps/LLMOps平台优先建设", "objective": "完成平台选型和流水线搭建", "key_actions": ["选型"], "deliverables": ["POC"], "owner_role": "平台", "timeline": "第1阶段", "dependencies": ["云资源"], "acceptance_signals": ["POC"], "evidence_refs": ["Q4"]},
                {"name": "分层解耦架构落地", "objective": "拆分模型层/推理层/网关层", "key_actions": ["拆分"], "deliverables": ["边界"], "owner_role": "架构", "timeline": "第2阶段", "dependencies": ["平台"], "acceptance_signals": ["边界稳定"], "evidence_refs": ["Q6"]},
                {"name": "自动化迁移工具链建设", "objective": "完成 ONNX 与自动化验证流水线", "key_actions": ["迁移"], "deliverables": ["迁移工具"], "owner_role": "平台", "timeline": "第3阶段", "dependencies": ["分层"], "acceptance_signals": ["可迁移"], "evidence_refs": ["Q7"]},
            ],
            "value_model": [
                {"metric": "MLOps/LLMOps平台优先建设", "baseline": "无", "target": "完成平台POC，上线核心流水线", "range": "4个关键工作流", "assumptions": ["样本真实可控"], "evidence_refs": ["Q4"]},
                {"metric": "分层解耦架构落地", "baseline": "弱", "target": "完成边界定义", "range": "三层解耦", "assumptions": ["边界稳定"], "evidence_refs": ["Q6"]},
                {"metric": "自动化迁移工具链建设", "baseline": "人工为主", "target": "覆盖80%存量模型", "range": "单模型迁移投入下降", "assumptions": ["模型可迁移"], "evidence_refs": ["Q7"]},
            ],
            "fit_reasons": [
                {"title": "结构化素材足以支撑提案骨架渲染", "detail": "当前已有完整结构化素材和页面骨架渲染上下文。", "evidence_refs": ["Q4"]},
                {"title": "约束边界明确", "detail": "迁移复杂与算力受限已经显性化。", "evidence_refs": ["Q6"]},
                {"title": "试点节奏清晰", "detail": "可以进入试点评审。", "evidence_refs": ["Q7"]},
            ],
            "risks_and_boundaries": [
                {"title": "TensorFlow学习曲线陡峭", "detail": "团队需要额外培训。", "type": "risk", "evidence_refs": ["Q19"]},
                {"title": "试点边界", "detail": "首轮不做全量改造。", "type": "boundary", "evidence_refs": ["Q8"]},
            ],
            "next_steps": [
                {"phase": "Phase 1", "goal": "完成MLOps/LLMOps平台优先建设", "actions": ["POC"], "milestone": "平台 POC", "evidence_refs": ["Q4"]},
                {"phase": "Phase 2", "goal": "完成分层解耦架构落地", "actions": ["拆分"], "milestone": "边界稳定", "evidence_refs": ["Q6"]},
                {"phase": "Phase 3", "goal": "完成自动化迁移工具链建设", "actions": ["迁移"], "milestone": "迁移可用", "evidence_refs": ["Q7"]},
            ],
        }
        chapter_ids = ['hero', 'why_now', 'comparison', 'blueprint', 'workstreams', 'integration', 'roadmap', 'value_fit']
        technical_chapter_response = {
            "meta": {"theme": "executive_dark_editorial", "tone": "judgemental_clear_premium", "nav_style": "sticky"},
            "chapters": [
                {
                    "id": chapter_id,
                    "nav_label": f"章节{idx+1}",
                    "eyebrow": "AI 提案页",
                    "title": "先完成「MLOps/LLMOps平台优先建设」和「分层解耦架构落地」双核心落地，再把交互式访谈AI智能体需求调研推进到全链路" if chapter_id == 'hero' else (
                        "不是把内容堆满，而是先做对的路径选择" if chapter_id == 'comparison' else (
                            "把「MLOps/LLMOps平台优先建设」组织成分层蓝图与推进路径" if chapter_id == 'blueprint' else (
                                "没有回流机制，就只是一次性项目，不是长期能力" if chapter_id == 'integration' else (
                                    "高级方案页的最后一章，必须回答为什么这套方案尤其适合当前项目" if chapter_id == 'value_fit' else f"{chapter_id} 标题"
                                )
                            )
                        )
                    ),
                    "judgement": f"{chapter_id} 需要同时推进 MLOps/LLMOps 平台、OpenAPI/gRPC 契约与自动化迁移工具链建设。",
                    "summary": f"{chapter_id} 摘要里保留了 TensorFlow、ONNX 和 CI门禁 等长技术表述。",
                    "layout": ['hero_metrics', 'conflict_cards', 'dual_comparison', 'blueprint_diagram', 'tabbed_cards', 'loop_diagram', 'phased_timeline', 'value_grid'][idx],
                    "metrics": [
                        {"label": "MLOps/LLMOps平台优先建设", "value": "完成平台POC，上线核心流水线", "delta": "4个关键工作流", "note": "样本真实可控"},
                        {"label": "分层解耦架构落地", "value": "完成边界定义", "delta": "三层解耦", "note": "边界稳定"},
                        {"label": "自动化迁移工具链建设", "value": "覆盖80%存量模型", "delta": "人工投入下降", "note": "模型可迁移"},
                    ] if chapter_id in {'hero', 'value_fit'} else [],
                    "cards": [
                        {"title": "MLOps/LLMOps平台优先建设", "desc": "需要完成 MLOps/LLMOps 平台、OpenAPI/gRPC 契约和 ONNX 自动化验证。", "tag": "AI", "meta": "TensorFlow / ONNX / Q4"},
                        {"title": "分层解耦架构落地", "desc": "需要继续推动模型层/推理层/网关层拆分。", "tag": "AI", "meta": "Q6"},
                        {"title": "自动化迁移工具链建设", "desc": "需要推进 ONNX 和 CI门禁 接入。", "tag": "AI", "meta": "Q7"},
                    ],
                    "diagram": {
                        "type": "architecture" if chapter_id == 'blueprint' else ("loop" if chapter_id == 'integration' else None),
                        "nodes": [
                            {"id": "n1", "label": "MLOps/LLMOps平台优先建设", "group": "module"},
                            {"id": "n2", "label": "分层解耦架构落地", "group": "module"},
                        ] if chapter_id in {'blueprint', 'integration'} else [],
                        "edges": [{"from": "n1", "to": "n2", "label": "推进"}] if chapter_id in {'blueprint', 'integration'} else [],
                        "caption": "通过 MLOps/LLMOps 平台优先建设、OpenAPI/gRPC 契约和自动化迁移工具链建设完成闭环。" if chapter_id in {'blueprint', 'integration'} else "",
                    },
                    "cta": {"label": "继续", "target": "roadmap"},
                    "evidence_refs": ["Q4", "Q6"],
                }
                for idx, chapter_id in enumerate(chapter_ids)
            ],
        }
        quality_review_response = {
            "audience": "decision_maker",
            "overall_score": 0.79,
            "status": "solid",
            "issues": [],
            "chapter_scores": [{"id": "hero", "score": 0.78, "issue": ""}],
            "chapter_updates": [
                {"id": "hero", "title": "先完成「MLOps/LLMOps平台优先建设」和「分层解耦架构落地」双核心落地", "judgement": "同步推进 MLOps/LLMOps 平台与 OpenAPI/gRPC 契约", "summary": "保留 TensorFlow 与 ONNX 表述"},
                {"id": "blueprint", "title": "推荐蓝图：先稳住「MLOps/LLMOps平台优先建设」，再拉通「分层解耦架构落地」"},
            ],
        }

        def _fake_call_claude(_prompt, *args, **kwargs):
            call_type = kwargs.get('call_type', '')
            if call_type == 'report_solution_proposal_brief':
                return json.dumps(technical_brief_response, ensure_ascii=False)
            if call_type == 'report_solution_chapter_copy':
                return json.dumps(technical_chapter_response, ensure_ascii=False)
            if call_type == 'report_solution_quality_review':
                return json.dumps(quality_review_response, ensure_ascii=False)
            return ''

        with patch.object(self.server, 'ENABLE_AI', True), \
             patch.object(self.server, 'HAS_ANTHROPIC', True), \
             patch.object(self.server, 'call_claude', new=_fake_call_claude):
            payload = self.server._build_solution_payload_from_snapshot(snapshot, source_mode='structured_sidecar')

        proposal_brief = payload.get('proposal_brief', {}) or {}
        chapters = {item.get('id'): item for item in (payload.get('chapter_copy', {}) or {}).get('chapters', []) if isinstance(item, dict)}

        self.assertEqual(proposal_brief.get('meta', {}).get('generation_mode'), 'ai')
        self.assertEqual(payload.get('quality_review', {}).get('review_mode'), 'ai')
        self.assertEqual(payload.get('audience_profile', {}).get('key'), 'decision_maker')
        self.assertIn('AI工程底座', proposal_brief.get('thesis', {}).get('headline', ''))
        self.assertNotIn('MLOps/LLMOps', proposal_brief.get('thesis', {}).get('headline', ''))
        self.assertNotIn('OpenAPI/gRPC', proposal_brief.get('recommended_solution', {}).get('architecture_statement', ''))
        self.assertEqual((chapters.get('hero') or {}).get('title'), '为什么当前先做「AI工程底座」')
        self.assertEqual((chapters.get('comparison') or {}).get('title'), '为什么选「AI工程底座」这条路')
        self.assertEqual((chapters.get('blueprint') or {}).get('title'), '推荐蓝图：先稳住「AI工程底座」，再拉通「分层架构」')
        self.assertEqual((chapters.get('integration') or {}).get('title'), '把「AI工程底座」接进系统闭环')
        self.assertEqual((chapters.get('value_fit') or {}).get('title'), '为什么这条路径更适合当前团队进入试点决策阶段')
        self.assertNotIn('MLOps/LLMOps', json.dumps(chapters, ensure_ascii=False))
        metrics_text = json.dumps((chapters.get('hero') or {}).get('metrics', []), ensure_ascii=False)
        self.assertNotIn('MLOps/LLMOps', metrics_text)
        self.assertIn('分层架构推进度', metrics_text)
        self.assertIn('迁移工具链效率', metrics_text)
        self.assertIn('能力底座', json.dumps((chapters.get('blueprint') or {}).get('cards', []), ensure_ascii=False))
        self.assertNotIn('结构化素材', json.dumps((chapters.get('value_fit') or {}).get('cards', []), ensure_ascii=False))

    def test_build_solution_payload_from_report_rehardens_delivery_titles(self):
        report_path = ROOT_DIR / "data" / "reports" / "deep-vision-20260314-e2a4fd23-交互式访谈-AI-智能体需求调研.md.solution.json"
        snapshot = json.loads(report_path.read_text(encoding="utf-8"))
        report_name = "delivery-hardened.md"
        snapshot["report_name"] = report_name
        self.server.write_solution_sidecar(report_name, snapshot)

        stale_payload = self.server._build_solution_payload_from_snapshot(snapshot, source_mode='structured_sidecar')
        stale_payload["proposal_brief"]["thesis"]["headline"] = "先完成「MLOps/LLMOps平台优先建设」和「分层解耦架构落地」双核心落地，再把交互式访谈AI智能体需求调研推进到全链路"
        chapter_order = [item.get('id') for item in (stale_payload.get("chapter_copy", {}) or {}).get("chapters", []) if isinstance(item, dict)]
        stale_chapter_map = {item.get('id'): item for item in (stale_payload.get("chapter_copy", {}) or {}).get("chapters", []) if isinstance(item, dict)}
        stale_chapter_map["comparison"]["title"] = "不是把内容堆满，而是先做对的路径选择"
        stale_chapter_map["blueprint"]["title"] = "把「MLOps/LLMOps平台优先建设」组织成分层蓝图与推进路径"
        stale_chapter_map["integration"]["title"] = "没有回流机制，就只是一次性项目，不是长期能力"
        stale_chapter_map["value_fit"]["title"] = "高级方案页的最后一章，必须回答为什么这套方案尤其适合当前项目"
        stale_payload["chapter_copy"]["chapters"] = [stale_chapter_map[chapter_id] for chapter_id in chapter_order]

        with patch.object(self.server, "_build_solution_payload_from_snapshot", return_value=stale_payload):
            payload = self.server.build_solution_payload_from_report(report_name, "# 占位报告")

        final_chapters = {item.get('id'): item for item in (payload.get("chapter_copy", {}) or {}).get("chapters", []) if isinstance(item, dict)}
        self.assertEqual(payload.get("proposal_brief", {}).get("thesis", {}).get("headline"), "为什么当前先做「AI工程底座」")
        self.assertEqual((final_chapters.get("comparison") or {}).get("title"), "为什么选「AI工程底座」这条路")
        self.assertEqual((final_chapters.get("blueprint") or {}).get("title"), "推荐蓝图：先稳住「AI工程底座」，再拉通「分层架构」")
        self.assertEqual((final_chapters.get("integration") or {}).get("title"), "把「AI工程底座」接进系统闭环")
        self.assertEqual((final_chapters.get("value_fit") or {}).get("title"), "为什么这条路径更适合当前团队进入试点决策阶段")
        self.assertEqual(payload.get("proposal_page", {}).get("audience_profile", {}).get("key"), payload.get("audience_profile", {}).get("key"))

    def test_structured_sidecar_falls_back_to_rules_when_ai_returns_bad_json(self):
        snapshot = self._build_snapshot(
            'proposal-ai-bad-json.md',
            topic='交易支付风控体验优化',
            scenario_name='交互式访谈',
            overview='当前需要先锁定试点切口，再决定是否扩大投入。',
            needs=[
                {'priority': 'P0', 'name': '高价值样本入口稳定', 'description': '先锁定真实被拦截用户。', 'evidence_refs': ['Q1']},
                {'priority': 'P0', 'name': '触发时机贴近真实决策瞬间', 'description': '避免过早或过晚触达。', 'evidence_refs': ['Q2']},
                {'priority': 'P1', 'name': '复现方式兼顾成本和深度', 'description': '低保真与高保真结合。', 'evidence_refs': ['Q3']},
            ],
            solutions=[
                {'title': '建立失败页高信号入口', 'description': '从最接近决策瞬间的页面切入。', 'owner': '运营', 'timeline': '第1周', 'metric': '入口评审通过', 'evidence_refs': ['Q4']},
                {'title': '设计延迟触发规则', 'description': '让访谈触达更贴近真实体验。', 'owner': '研究', 'timeline': '第2周', 'metric': '触发命中率提升', 'evidence_refs': ['Q5']},
                {'title': '搭建混合复现机制', 'description': '原型、录屏和回访脚本共同工作。', 'owner': '设计', 'timeline': '第3周', 'metric': '形成首轮洞察', 'evidence_refs': ['Q6']},
            ],
            actions=[
                {'action': '确认支付失败页样本入口', 'owner': '运营', 'timeline': 'T+3天', 'metric': '入口评审通过', 'evidence_refs': ['Q9']},
                {'action': '冻结延迟触发规则', 'owner': '研究', 'timeline': 'T+5天', 'metric': '规则确认', 'evidence_refs': ['Q10']},
                {'action': '完成混合复现原型', 'owner': '设计', 'timeline': 'T+7天', 'metric': '原型可试跑', 'evidence_refs': ['Q11']},
            ],
            risks=[
                {'risk': '真实样本不足', 'impact': '结论偏差', 'mitigation': '先锁定高价值入口', 'evidence_refs': ['Q7']},
            ],
        )

        def _fake_call_claude(_prompt, *args, **kwargs):
            return '{"bad_json": '

        with patch.object(self.server, 'ENABLE_AI', True), \
             patch.object(self.server, 'HAS_ANTHROPIC', True), \
             patch.object(self.server, 'call_claude', new=_fake_call_claude):
            payload = self._write_structured_sidecar('proposal-ai-bad-json.md', snapshot)

        proposal_brief = payload.get('proposal_brief', {}) or {}
        chapter_copy = payload.get('chapter_copy', {}) or {}
        self.assertEqual(proposal_brief.get('meta', {}).get('generation_mode'), 'rule')
        self.assertEqual(chapter_copy.get('meta', {}).get('generation_mode'), 'rule')
        self.assertTrue(proposal_brief.get('thesis', {}).get('headline'))
        self.assertEqual(len(chapter_copy.get('chapters', []) or []), 8)

    def test_structured_sidecar_falls_back_to_rule_chapters_when_ai_chapters_incomplete(self):
        snapshot = self._build_snapshot(
            'proposal-ai-chapters.md',
            topic='交易支付风控体验优化',
            scenario_name='交互式访谈',
            overview='当前需要先锁定高价值样本、试点入口和排期边界。',
            needs=[
                {'priority': 'P0', 'name': '高价值样本入口稳定', 'description': '先锁定真实被拦截用户。', 'evidence_refs': ['Q1']},
                {'priority': 'P0', 'name': '触发时机贴近真实决策瞬间', 'description': '避免过早或过晚触达。', 'evidence_refs': ['Q2']},
                {'priority': 'P1', 'name': '复现方式兼顾成本和深度', 'description': '低保真与高保真结合。', 'evidence_refs': ['Q3']},
            ],
            solutions=[
                {'title': '建立失败页高信号入口', 'description': '从最接近决策瞬间的页面切入。', 'owner': '运营', 'timeline': '第1周', 'metric': '入口评审通过', 'evidence_refs': ['Q4']},
                {'title': '设计延迟触发规则', 'description': '让访谈触达更贴近真实体验。', 'owner': '研究', 'timeline': '第2周', 'metric': '触发命中率提升', 'evidence_refs': ['Q5']},
                {'title': '搭建混合复现机制', 'description': '原型、录屏和回访脚本共同工作。', 'owner': '设计', 'timeline': '第3周', 'metric': '形成首轮洞察', 'evidence_refs': ['Q6']},
            ],
            risks=[
                {'risk': '真实样本不足', 'impact': '结论偏差', 'mitigation': '先锁定高价值入口', 'evidence_refs': ['Q7']},
                {'risk': '合规评审拖慢试点', 'impact': '排期拉长', 'mitigation': '前置脱敏和法务评审', 'evidence_refs': ['Q8']},
            ],
            actions=[
                {'action': '确认支付失败页样本入口', 'owner': '运营', 'timeline': 'T+3天', 'metric': '入口评审通过', 'evidence_refs': ['Q9']},
                {'action': '冻结延迟触发规则', 'owner': '研究', 'timeline': 'T+5天', 'metric': '规则确认', 'evidence_refs': ['Q10']},
                {'action': '完成混合复现原型', 'owner': '设计', 'timeline': 'T+7天', 'metric': '原型可试跑', 'evidence_refs': ['Q11']},
                {'action': '启动首轮试点访谈', 'owner': '研究+运营', 'timeline': 'T+14天', 'metric': '回收首批有效样本', 'evidence_refs': ['Q12']},
            ],
        )
        brief_response = {
            "meta": {"topic": "交易支付风控体验优化", "audience": "decision_maker", "proposal_goal": "内部共识", "confidence": 0.9},
            "thesis": {"headline": "AI 版提案标题", "subheadline": "AI 版提案副标题", "why_now": "AI 版 why now", "core_decision": "AI 版核心判断"},
            "context": {"business_scene": "交易支付风控体验", "current_state": ["入口已收敛"], "core_conflicts": ["触达与打扰并存"], "constraints": ["单入口试点"], "evidence_refs": ["Q1"]},
            "options": [
                {"name": "保守路径", "positioning": "先收集样本", "pros": ["快"], "cons": ["浅"], "fit_for": "早期探索", "not_fit_for": "试点评审", "decision": "alternative", "evidence_refs": ["Q1"]},
                {"name": "失败页闭环试点", "positioning": "围绕失败页形成试点闭环", "pros": ["深"], "cons": ["需要协同"], "fit_for": "当前项目", "not_fit_for": "无真实入口场景", "decision": "recommended", "evidence_refs": ["Q4"]},
            ],
            "recommended_solution": {"north_star": "AI 北极星", "architecture_statement": "AI 架构主张", "modules": [], "integration_points": ["入口"], "dataflow": ["触发", "复盘"], "governance": ["法务"], "evidence_refs": ["Q4"]},
            "workstreams": [
                {"name": "样本入口治理", "objective": "锁定高价值样本", "key_actions": ["确认入口"], "deliverables": ["入口清单"], "owner_role": "运营", "timeline": "第1周", "dependencies": ["法务"], "acceptance_signals": ["入口评审通过"], "evidence_refs": ["Q4"]},
                {"name": "触发策略治理", "objective": "冻结触发规则", "key_actions": ["制定规则"], "deliverables": ["规则说明"], "owner_role": "研究", "timeline": "第2周", "dependencies": ["入口稳定"], "acceptance_signals": ["规则确认"], "evidence_refs": ["Q5"]},
                {"name": "混合复现机制", "objective": "完成首轮试跑", "key_actions": ["完成原型"], "deliverables": ["原型"], "owner_role": "设计", "timeline": "第3周", "dependencies": ["规则冻结"], "acceptance_signals": ["原型可试跑"], "evidence_refs": ["Q6"]},
            ],
            "value_model": [
                {"metric": "试点推进速度", "baseline": "慢", "target": "快", "range": "3阶段", "assumptions": ["入口可用"], "evidence_refs": ["Q9"]},
                {"metric": "高价值洞察密度", "baseline": "低", "target": "高", "range": "3个工作流", "assumptions": ["样本稳定"], "evidence_refs": ["Q1"]},
                {"metric": "证据绑定率", "baseline": "人工翻阅", "target": "高证据密度", "range": "持续绑定", "assumptions": ["结构化条目可用"], "evidence_refs": ["Q4"]},
            ],
            "fit_reasons": [
                {"title": "切口清晰", "detail": "失败页入口已经足够清晰。", "evidence_refs": ["Q4"]},
                {"title": "边界清晰", "detail": "单入口试点边界明确。", "evidence_refs": ["Q8"]},
                {"title": "素材充分", "detail": "已有完整结构化素材。", "evidence_refs": ["Q1", "Q4"]},
            ],
            "risks_and_boundaries": [
                {"title": "真实样本不足", "detail": "若入口不稳，结论会失真。", "type": "risk", "evidence_refs": ["Q7"]},
                {"title": "试点边界", "detail": "只做单入口试点。", "type": "boundary", "evidence_refs": ["Q8"]},
            ],
            "next_steps": [
                {"phase": "Phase 1", "goal": "锁定入口", "actions": ["确认入口"], "milestone": "入口确认", "evidence_refs": ["Q9"]},
                {"phase": "Phase 2", "goal": "冻结规则", "actions": ["冻结规则"], "milestone": "规则确认", "evidence_refs": ["Q10"]},
                {"phase": "Phase 3", "goal": "完成试点", "actions": ["启动访谈"], "milestone": "试点启动", "evidence_refs": ["Q12"]},
            ],
        }
        incomplete_chapter_response = {
            "meta": {"theme": "executive_dark_editorial", "tone": "judgemental_clear_premium", "nav_style": "sticky"},
            "chapters": [
                {
                    "id": chapter_id,
                    "nav_label": chapter_id,
                    "eyebrow": "AI 提案页",
                    "title": f"{chapter_id} 标题",
                    "judgement": f"{chapter_id} 判断",
                    "summary": f"{chapter_id} 摘要",
                    "layout": "hero_metrics" if chapter_id == 'hero' else "conflict_cards",
                    "metrics": [{"label": "指标", "value": "80%", "delta": "", "note": "说明"}] * 3 if chapter_id == 'hero' else [],
                    "cards": [{"title": f"{chapter_id} 卡片", "desc": "描述", "tag": "AI", "meta": "meta"}],
                    "diagram": None,
                    "cta": {"label": "继续", "target": "roadmap"},
                    "evidence_refs": ["Q1"],
                }
                for chapter_id in ['hero', 'why_now', 'comparison', 'blueprint', 'workstreams', 'integration', 'roadmap']
            ],
        }

        def _fake_call_claude(_prompt, *args, **kwargs):
            call_type = kwargs.get('call_type', '')
            if call_type == 'report_solution_proposal_brief':
                return json.dumps(brief_response, ensure_ascii=False)
            if call_type == 'report_solution_chapter_copy':
                return json.dumps(incomplete_chapter_response, ensure_ascii=False)
            return ''

        with patch.object(self.server, 'ENABLE_AI', True), \
             patch.object(self.server, 'HAS_ANTHROPIC', True), \
             patch.object(self.server, 'call_claude', new=_fake_call_claude):
            payload = self._write_structured_sidecar('proposal-ai-chapters.md', snapshot)

        proposal_brief = payload.get('proposal_brief', {}) or {}
        chapter_copy = payload.get('chapter_copy', {}) or {}
        self.assertEqual(proposal_brief.get('meta', {}).get('generation_mode'), 'ai')
        self.assertEqual(chapter_copy.get('meta', {}).get('generation_mode'), 'rule')
        self.assertEqual([item.get('id') for item in chapter_copy.get('chapters', [])], ['hero', 'why_now', 'comparison', 'blueprint', 'workstreams', 'integration', 'roadmap', 'value_fit'])


if __name__ == '__main__':
    unittest.main()
