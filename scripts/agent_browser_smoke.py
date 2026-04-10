#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
DeepVision 浏览器级 UI smoke 入口。

目标：
1. 用真实浏览器补静态资源、前端交互和后台入口的最小回归
2. 同时支持 mock 浏览器回归与隔离数据目录下的 live 真链路
3. 保持为 opt-in 阶段，避免默认 harness 被浏览器依赖绑死
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


NODE_RUNNER = ROOT_DIR / "scripts" / "agent_browser_smoke_runner.mjs"
PLAYWRIGHT_PACKAGE_DIR = ROOT_DIR / "node_modules" / "playwright"


@dataclass(frozen=True)
class BrowserScenario:
    scenario_id: str
    label: str
    description: str


MINIMAL_SCENARIOS = [
    BrowserScenario(
        "help-docs",
        "帮助文档静态页",
        "确认 help.html 可加载，标题与关键文案可见。",
    ),
    BrowserScenario(
        "solution-share",
        "方案页分享面板",
        "确认 solution.html 在 mock API 下可渲染，并能打开分享面板。",
    ),
    BrowserScenario(
        "admin-config-entry",
        "管理员中心入口",
        "确认管理员账号可从 index.html 主界面进入管理员中心。",
    ),
]

EXTENDED_EXTRA_SCENARIOS = [
    BrowserScenario(
        "solution-public-readonly",
        "方案页公开分享只读",
        "确认公开分享模式可渲染，且不会暴露分享动作按钮。",
    ),
    BrowserScenario(
        "solution-public-readonly-refresh",
        "方案页公开分享刷新保持只读",
        "确认公开分享页刷新后仍保持只读模式，不会泄露分享动作按钮或动作栏。",
    ),
    BrowserScenario(
        "login-view",
        "登录前端视图",
        "确认未登录状态会展示登录表单，并提示当前登录方式的可用性。",
    ),
    BrowserScenario(
        "login-sms-only-view",
        "登录视图仅短信 provider",
        "确认微信 provider 关闭或缺失时，前端仍展示短信登录表单，并隐藏微信入口与无 provider 告警。",
    ),
    BrowserScenario(
        "login-wechat-only-view",
        "登录视图仅微信 provider",
        "确认短信 provider 关闭时，前端仍展示微信登录入口，并隐藏短信表单与无 provider 告警。",
    ),
    BrowserScenario(
        "license-gate-view",
        "License 门禁前端视图",
        "确认已登录但无有效 License 时，首页会进入 License gate，并展示绑定输入框。",
    ),
    BrowserScenario(
        "license-activate-success",
        "License 绑定成功后切回业务壳",
        "确认在 License gate 中提交有效 License 后，前端会退出门禁并回到访谈会话主页。",
    ),
    BrowserScenario(
        "license-activate-refresh",
        "License 绑定后刷新保持业务壳",
        "确认绑定成功后刷新首页，前端仍保持已登录且不回到 License gate。",
    ),
    BrowserScenario(
        "report-detail-flow",
        "报告详情与方案入口",
        "确认可从报告列表进入报告详情，并看到方案入口按钮与核心报告内容。",
    ),
    BrowserScenario(
        "report-detail-refresh",
        "报告详情刷新后保持详情态",
        "确认报告详情页刷新后仍恢复到同一份报告详情，而不是退回报告列表。",
    ),
    BrowserScenario(
        "interview-refresh",
        "访谈进行中刷新后保持当前会话",
        "确认访谈进行中刷新页面后，前端仍恢复到同一会话与当前问题，而不是退回会话列表或文档准备步骤。",
    ),
    BrowserScenario(
        "report-generation-refresh",
        "报告生成中刷新后保持进度",
        "确认需求摘要确认页触发报告生成后刷新页面，前端仍恢复到当前会话，并继续显示报告生成进度。",
    ),
    BrowserScenario(
        "admin-config-tab",
        "管理员配置中心页签",
        "确认管理员中心中的配置中心可加载，并能切换 env/config/site 三类来源。",
    ),
]

LIVE_EXTENDED_SCENARIOS = [
    BrowserScenario(
        "live-login-license-flow",
        "真实后端登录与 License 绑定",
        "确认隔离运行态下可完成短信验证码登录、License 绑定，并切回访谈会话主页。",
    ),
    BrowserScenario(
        "live-report-generation-refresh",
        "真实后端报告生成中刷新恢复",
        "确认隔离运行态下触发报告生成后刷新页面，前端仍恢复到同一会话并继续显示生成进度。",
    ),
    BrowserScenario(
        "live-report-solution-flow",
        "真实后端报告详情与方案页",
        "确认隔离运行态下可生成真实报告，进入报告详情并打开方案页。",
    ),
    BrowserScenario(
        "live-solution-public-share-flow",
        "真实后端公开分享只读链路",
        "确认隔离运行态下可从真实方案页生成分享链接，并以匿名态访问只读分享页。",
    ),
]

SUITES = {
    "minimal": {
        "description": "帮助页 + 方案页分享 + 管理后台配置入口",
        "scenarios": MINIMAL_SCENARIOS,
    },
    "extended": {
        "description": "在 minimal 基础上补公开分享只读及刷新恢复、登录 provider 可见反馈、License 门禁视图、License 绑定成功与刷新恢复、访谈/报告详情恢复链路和配置中心页签切换",
        "scenarios": [*MINIMAL_SCENARIOS, *EXTENDED_EXTRA_SCENARIOS],
    },
    "live-minimal": {
        "description": "隔离数据目录下启动真实后端，覆盖短信登录 + License 绑定 + 业务壳切换真链路",
        "scenarios": [
            BrowserScenario(
                "live-login-license-flow",
                "真实后端登录与 License 绑定",
                "确认隔离运行态下可完成短信验证码登录、License 绑定，并在刷新后仍留在访谈会话主页。",
            ),
        ],
    },
    "live-extended": {
        "description": "在 live-minimal 基础上补真实报告生成恢复、真实报告详情、真实方案页和公开分享只读链路",
        "scenarios": LIVE_EXTENDED_SCENARIOS,
    },
}


def resolve_suite_scenarios(suite_name: str) -> list[BrowserScenario]:
    if suite_name not in SUITES:
        raise KeyError(f"未知 browser smoke suite: {suite_name}")
    return list(SUITES[suite_name]["scenarios"])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DeepVision 浏览器级 UI smoke 入口")
    parser.add_argument(
        "--suite",
        default="minimal",
        choices=sorted(SUITES.keys()),
        help="选择 browser smoke 套件",
    )
    parser.add_argument("--list", action="store_true", help="仅列出套件内容，不执行浏览器检查")
    parser.add_argument("--install-browser", action="store_true", help="执行前显式安装 Chromium 浏览器")
    parser.add_argument("--json", action="store_true", help="输出 JSON 结果")
    parser.add_argument("--quiet", action="store_true", help="仅输出最终摘要")
    return parser


def print_suite_listing(*, suite_name: str, description: str, scenarios: list[BrowserScenario]) -> int:
    print(f"Suite: {suite_name}")
    print(f"描述: {description}")
    for index, scenario in enumerate(scenarios, 1):
        print(f"{index}. {scenario.label}: {scenario.scenario_id}")
        print(f"   {scenario.description}")
    return 0


def _dependency_summary() -> dict[str, object]:
    return {
        "node_available": bool(shutil.which("node")),
        "npm_available": bool(shutil.which("npm")),
        "uv_available": bool(shutil.which("uv")),
        "playwright_package_installed": PLAYWRIGHT_PACKAGE_DIR.exists(),
        "runner_exists": NODE_RUNNER.exists(),
    }


def _failure_payload(*, suite_name: str, dependency_status: dict[str, object], detail: str, hints: list[str]) -> dict:
    return {
        "suite": suite_name,
        "summary": {"PASS": 0, "WARN": 0, "FAIL": 1},
        "overall": "BLOCKED",
        "results": [
            {
                "scenario_id": "environment",
                "label": "浏览器环境检查",
                "status": "FAIL",
                "detail": detail,
                "highlights": hints,
            }
        ],
        "dependency_status": dependency_status,
    }


def run_browser_smoke(*, suite_name: str = "minimal", install_browser: bool = False) -> tuple[dict, int]:
    dependency_status = _dependency_summary()
    suite_is_live = suite_name.startswith("live-")
    if not dependency_status["node_available"]:
        return (
            _failure_payload(
                suite_name=suite_name,
                dependency_status=dependency_status,
                detail="未检测到 node，可先安装 Node.js 22+。",
                hints=["恢复命令: node -v", "浏览器 smoke 依赖本地 Node 运行时。"],
            ),
            2,
        )
    if suite_is_live and not dependency_status["uv_available"]:
        return (
            _failure_payload(
                suite_name=suite_name,
                dependency_status=dependency_status,
                detail="live 浏览器 smoke 需要 uv 来启动隔离后端。",
                hints=["恢复命令: uv --version", "live 套件会通过 uv run web/server.py 启动真实后端。"],
            ),
            2,
        )
    if not dependency_status["npm_available"]:
        return (
            _failure_payload(
                suite_name=suite_name,
                dependency_status=dependency_status,
                detail="未检测到 npm，无法执行 Playwright runner。",
                hints=["恢复命令: npm -v"],
            ),
            2,
        )
    if not dependency_status["runner_exists"]:
        return (
            _failure_payload(
                suite_name=suite_name,
                dependency_status=dependency_status,
                detail="缺少 scripts/agent_browser_smoke_runner.mjs。",
                hints=["请确认仓库脚本完整。"],
            ),
            2,
        )
    if not dependency_status["playwright_package_installed"]:
        return (
            _failure_payload(
                suite_name=suite_name,
                dependency_status=dependency_status,
                detail="未检测到本地 Playwright 依赖。",
                hints=["恢复命令: npm install", "如首次执行，后续再运行: npx playwright install chromium chromium-headless-shell"],
            ),
            2,
        )

    if install_browser:
        install_process = subprocess.run(
            ["npx", "playwright", "install", "chromium", "chromium-headless-shell"],
            cwd=str(ROOT_DIR),
            capture_output=True,
            text=True,
            check=False,
        )
        if install_process.returncode != 0:
            return (
                _failure_payload(
                    suite_name=suite_name,
                    dependency_status=dependency_status,
                    detail="Chromium 安装失败。",
                    hints=[
                        line.strip()
                        for line in (install_process.stderr or install_process.stdout or "").splitlines()
                        if line.strip()
                    ][:8]
                    or ["恢复命令: npx playwright install chromium chromium-headless-shell"],
                ),
                2,
            )

    completed = subprocess.run(
        ["node", str(NODE_RUNNER), "--suite", suite_name],
        cwd=str(ROOT_DIR),
        capture_output=True,
        text=True,
        check=False,
    )

    stdout_text = str(completed.stdout or "").strip()
    stderr_text = str(completed.stderr or "").strip()
    if stdout_text:
        try:
            payload = json.loads(stdout_text)
            payload["dependency_status"] = dependency_status
            overall = str(payload.get("overall") or "").strip()
            return payload, 0 if overall == "READY" and completed.returncode == 0 else 2
        except json.JSONDecodeError:
            pass

    detail = "浏览器 smoke 执行失败。"
    hints: list[str] = []
    combined = "\n".join(part for part in [stderr_text, stdout_text] if part).strip()
    lowered = combined.lower()
    if "cannot find package 'playwright'" in lowered or "cannot find module 'playwright'" in lowered:
        detail = "本地 Playwright 依赖未安装完成。"
        hints = ["恢复命令: npm install"]
    elif "executable doesn't exist" in lowered or "please run the following command" in lowered:
        detail = "Chromium 浏览器尚未安装。"
        hints = ["恢复命令: npx playwright install chromium chromium-headless-shell"]
    elif combined:
        hints = [line.strip() for line in combined.splitlines() if line.strip()][:8]
    else:
        hints = ["请直接执行 node scripts/agent_browser_smoke_runner.mjs --suite minimal 查看原始错误。"]

    return (
        _failure_payload(
            suite_name=suite_name,
            dependency_status=dependency_status,
            detail=detail,
            hints=hints,
        ),
        2,
    )


def render_text_output(payload: dict) -> None:
    summary = payload.get("summary", {}) if isinstance(payload.get("summary", {}), dict) else {}
    print(f"DeepVision browser smoke | suite={payload.get('suite', '')}")
    print(f"总体状态: {payload.get('overall', '')}")
    dependency_status = payload.get("dependency_status", {}) if isinstance(payload.get("dependency_status", {}), dict) else {}
    if dependency_status:
        print(
            "环境: "
            f"node={'yes' if dependency_status.get('node_available') else 'no'} "
            f"npm={'yes' if dependency_status.get('npm_available') else 'no'} "
            f"playwright={'yes' if dependency_status.get('playwright_package_installed') else 'no'}"
        )
    print("")
    for item in list(payload.get("results", []) or []):
        if not isinstance(item, dict):
            continue
        print(f"[{item.get('status', '')}] {item.get('label', '')}: {item.get('detail', '')}")
        for line in list(item.get("highlights", []) or [])[:6]:
            text = str(line or "").strip()
            if text:
                print(f"        - {text}")
    print("")
    print(
        "Summary: "
        f"PASS={int(summary.get('PASS', 0) or 0)} "
        f"WARN={int(summary.get('WARN', 0) or 0)} "
        f"FAIL={int(summary.get('FAIL', 0) or 0)}"
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    scenarios = resolve_suite_scenarios(args.suite)
    suite_meta = SUITES[args.suite]
    if args.list:
        return print_suite_listing(
            suite_name=args.suite,
            description=suite_meta["description"],
            scenarios=scenarios,
        )

    payload, exit_code = run_browser_smoke(suite_name=args.suite, install_browser=args.install_browser)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    elif not args.quiet or exit_code != 0:
        render_text_output(payload)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
