import importlib.util
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT_DIR / "scripts" / "version_manager.py"


def load_module():
    spec = importlib.util.spec_from_file_location("dv_version_manager_test", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class VersionManagerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def test_parse_commit_message_supports_chinese_multiline_changes(self):
        version_type, title, changes = self.module.parse_commit_message(
            "优化：完善按钮提交更新日志\n前端：同步更新日志弹窗展示文案。\n后端：优化版本日志生成逻辑。\n测试：补充回归用例。"
        )

        self.assertEqual(version_type, "patch")
        self.assertEqual(title, "完善按钮提交更新日志")
        self.assertEqual(
            changes,
            [
                "前端：同步更新日志弹窗展示文案。",
                "后端：优化版本日志生成逻辑。",
                "测试：补充回归用例。",
            ],
        )

    def test_build_release_notes_falls_back_to_diff_when_title_is_dirty(self):
        version_type, title, changes = self.module.build_release_notes_from_context(
            "实现其他选项语义化展示逻辑」} ভুল? need remove non",
            [
                "scripts/version_manager.py",
                ".githooks/post-commit",
                "tests/test_version_manager.py",
                "README.md",
            ],
        )

        self.assertEqual(version_type, "patch")
        self.assertEqual(title, "优化版本日志生成与提交流程并补充回归测试")
        self.assertIn("工程：优化版本日志生成脚本，支持从提交改动自动整理结构化更新说明。", changes)
        self.assertIn("工程：统一提交后自动升版流程，确保按钮提交也会生成结构化更新日志。", changes)
        self.assertIn("测试：补充版本日志生成回归用例，覆盖脏提交信息与差异归类场景。", changes)
        self.assertIn("文档：补充 Hook 安装与版本日志维护说明。", changes)

    def test_build_release_notes_keeps_clean_title_and_uses_diff_changes(self):
        version_type, title, changes = self.module.build_release_notes_from_context(
            "修复：更新日志展示异常",
            ["web/app.js", "web/server.py", "tests/test_api_comprehensive.py"],
        )

        self.assertEqual(version_type, "patch")
        self.assertEqual(title, "更新日志展示异常")
        self.assertIn("前端：更新界面交互与展示逻辑。", changes)
        self.assertIn("后端：更新接口与数据处理逻辑。", changes)
        self.assertIn("测试：补充并校验相关回归用例。", changes)

    def test_build_release_notes_respects_explicit_minor_type(self):
        version_type, title, changes = self.module.build_release_notes_from_context(
            "feat: 支持按钮提交自动生成结构化更新日志",
            ["scripts/version_manager.py"],
        )

        self.assertEqual(version_type, "minor")
        self.assertEqual(title, "支持按钮提交自动生成结构化更新日志")
        self.assertTrue(changes)


if __name__ == "__main__":
    unittest.main(verbosity=2)
