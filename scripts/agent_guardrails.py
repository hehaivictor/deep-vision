#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
DeepVision agent 关键不变量 gate。

目标：
1. 把项目级关键不变量收口成固定命令
2. 让高风险权限、实例隔离、分享边界与运维 apply/rollback 都有独立 gate
3. 让 CI 与 ship 能直接复用同一套 guardrail 套件
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
        "tests.test_security_regression.SecurityRegressionTests.test_anonymous_write_endpoints_are_blocked",
        "匿名写接口必须被拦截",
    ),
    SuiteCase(
        "tests.test_security_regression.SecurityRegressionTests.test_license_gate_blocks_business_routes_but_allows_auth_and_license_endpoints",
        "License 门禁必须阻断业务写链路",
    ),
    SuiteCase(
        "tests.test_api_comprehensive.ComprehensiveApiTests.test_admin_license_routes_require_valid_license_even_when_gate_disabled",
        "管理员接口仍需有效 License",
    ),
    SuiteCase(
        "tests.test_api_comprehensive.ComprehensiveApiTests.test_license_activation_and_status_summary",
        "License 激活状态必须一致",
    ),
    SuiteCase(
        "tests.test_api_comprehensive.ComprehensiveApiTests.test_standard_user_can_generate_balanced_but_cannot_access_solution_appendix_or_presentation",
        "标准版能力边界必须收紧",
    ),
    SuiteCase(
        "tests.test_security_regression.SecurityRegressionTests.test_report_solution_endpoint_requires_auth",
        "方案页必须要求登录",
    ),
    SuiteCase(
        "tests.test_security_regression.SecurityRegressionTests.test_report_solution_endpoint_enforces_owner",
        "方案页必须校验 owner",
    ),
    SuiteCase(
        "tests.test_security_regression.SecurityRegressionTests.test_report_solution_share_link_requires_owner_and_allows_public_readonly_access",
        "方案分享必须只读且受 owner 保护",
    ),
    SuiteCase(
        "tests.test_api_comprehensive.ComprehensiveApiTests.test_admin_ownership_migration_endpoints_cover_search_preview_apply_and_rollback",
        "归属迁移必须支持 preview/apply/rollback",
    ),
    SuiteCase(
        "tests.test_api_comprehensive.ComprehensiveApiTests.test_professional_user_can_access_solution_share_appendix_and_presentation_endpoints",
        "专业版能力必须完整开放",
    ),
]

EXTENDED_EXTRA_CASES = [
    SuiteCase(
        "tests.test_security_regression.SecurityRegressionTests.test_deleted_reports_sidecar_keeps_all_entries_under_parallel_updates",
        "删除报告 sidecar 并发更新不丢数据",
    ),
    SuiteCase(
        "tests.test_security_regression.SecurityRegressionTests.test_solution_share_sidecar_keeps_all_entries_under_parallel_updates",
        "方案分享 sidecar 并发更新不丢数据",
    ),
    SuiteCase(
        "tests.test_security_regression.SecurityRegressionTests.test_deleted_docs_sidecar_keeps_all_entries_under_parallel_updates",
        "删除文档 sidecar 并发更新不丢数据",
    ),
    SuiteCase(
        "tests.test_security_regression.SecurityRegressionTests.test_presentation_map_remains_valid_under_parallel_updates",
        "演示稿映射并发更新保持有效",
    ),
    SuiteCase(
        "tests.test_security_regression.SecurityRegressionTests.test_build_solution_payload_strips_html_from_new_fields",
        "方案页新字段必须做 HTML 清洗",
    ),
]

SUITES = {
    "minimal": {
        "description": "关键不变量：权限、实例隔离、分享边界、高风险运维入口",
        "cases": MINIMAL_CASES,
    },
    "extended": {
        "description": "在 minimal 基础上补 sidecar 并发与 HTML 清洗 guardrail",
        "cases": [*MINIMAL_CASES, *EXTENDED_EXTRA_CASES],
    },
}


def resolve_suite_cases(suite_name: str) -> list[SuiteCase]:
    if suite_name not in SUITES:
        raise KeyError(f"未知 guardrail suite: {suite_name}")
    return list(SUITES[suite_name]["cases"])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DeepVision agent 关键不变量 gate")
    parser.add_argument(
        "--suite",
        default="minimal",
        choices=sorted(SUITES.keys()),
        help="选择 guardrail 套件",
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
        title="DeepVision agent guardrails",
        description=suite_meta["description"],
        cases=cases,
        quiet=args.quiet,
        failfast=args.failfast,
    )


if __name__ == "__main__":
    raise SystemExit(main())
