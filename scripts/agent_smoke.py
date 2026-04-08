#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
DeepVision agent 最小回归入口。

目标：
1. 把 brownfield 仓库的最小主链路回归收口成固定命令
2. 默认只跑 deterministic 的 unittest 用例，不依赖真实外部服务
3. 用一套命令覆盖鉴权、会话、报告、方案页和安全边界
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.agent_test_runner import SuiteCase
from scripts.agent_test_runner import execute_suite
from scripts.agent_test_runner import print_suite_listing

MINIMAL_CASES = [
    SuiteCase(
        "tests.test_api_comprehensive.ComprehensiveApiTests.test_auth_lifecycle",
        "鉴权生命周期",
    ),
    SuiteCase(
        "tests.test_api_comprehensive.ComprehensiveApiTests.test_license_activation_and_status_summary",
        "License 激活与状态汇总",
    ),
    SuiteCase(
        "tests.test_api_comprehensive.ComprehensiveApiTests.test_standard_user_can_generate_balanced_but_cannot_access_solution_appendix_or_presentation",
        "标准版主链路与能力门禁",
    ),
    SuiteCase(
        "tests.test_api_comprehensive.ComprehensiveApiTests.test_professional_user_can_access_solution_share_appendix_and_presentation_endpoints",
        "专业版方案页与分享能力",
    ),
    SuiteCase(
        "tests.test_solution_payload.SolutionPayloadTests.test_build_solution_payload_falls_back_to_legacy_markdown_for_old_report",
        "方案页旧报告兼容",
    ),
    SuiteCase(
        "tests.test_security_regression.SecurityRegressionTests.test_anonymous_write_endpoints_are_blocked",
        "匿名写接口拦截",
    ),
    SuiteCase(
        "tests.test_security_regression.SecurityRegressionTests.test_report_solution_share_link_requires_owner_and_allows_public_readonly_access",
        "方案页分享权限边界",
    ),
]

EXTENDED_EXTRA_CASES = [
    SuiteCase(
        "tests.test_api_comprehensive.ComprehensiveApiTests.test_admin_ownership_migration_endpoints_cover_search_preview_apply_and_rollback",
        "归属迁移预览与回滚",
    ),
    SuiteCase(
        "tests.test_api_comprehensive.ComprehensiveApiTests.test_admin_config_center_endpoints_cover_catalog_and_file_persistence",
        "配置中心目录与落盘",
    ),
    SuiteCase(
        "tests.test_security_regression.SecurityRegressionTests.test_ops_endpoints_require_admin_role",
        "运维接口管理员权限",
    ),
    SuiteCase(
        "tests.test_scripts_comprehensive.ComprehensiveScriptTests.test_replay_preflight_diagnostics_simulates_trigger_and_throttle",
        "预检回放脚本",
    ),
]

SUITES = {
    "minimal": {
        "description": "最小主链路：鉴权 -> 会话 -> 报告 -> 方案页 -> 安全边界",
        "cases": MINIMAL_CASES,
    },
    "extended": {
        "description": "在 minimal 基础上补管理后台与脚本回归",
        "cases": [*MINIMAL_CASES, *EXTENDED_EXTRA_CASES],
    },
}


def resolve_suite_cases(suite_name: str) -> list[SuiteCase]:
    if suite_name not in SUITES:
        raise KeyError(f"未知 smoke suite: {suite_name}")
    return list(SUITES[suite_name]["cases"])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DeepVision agent 最小回归入口")
    parser.add_argument(
        "--suite",
        default="minimal",
        choices=sorted(SUITES.keys()),
        help="选择 smoke 套件",
    )
    parser.add_argument("--list", action="store_true", help="仅列出套件内容，不执行测试")
    parser.add_argument("--failfast", action="store_true", help="遇到首个失败后停止")
    parser.add_argument("--quiet", action="store_true", help="仅输出最终摘要")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    suite_meta = SUITES[args.suite]
    cases = resolve_suite_cases(args.suite)

    if args.list:
        return print_suite_listing(
            suite_name=args.suite,
            description=suite_meta["description"],
            cases=cases,
        )

    return execute_suite(
        suite_name=args.suite,
        title="DeepVision agent smoke",
        description=suite_meta["description"],
        cases=cases,
        quiet=args.quiet,
        failfast=args.failfast,
    )


if __name__ == "__main__":
    raise SystemExit(main())
