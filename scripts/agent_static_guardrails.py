#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
DeepVision agent 源码级静态 guardrail。

目标：
1. 把最关键的高风险路由约束前移到源码扫描阶段
2. 在 runtime guardrails 之外，再补一层更快的静态回归
3. 为 harness / CI 提供独立可复用的静态检查入口
"""

from __future__ import annotations

import argparse
import ast
import json
from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SERVER_FILE = ROOT_DIR / "web" / "server.py"
DEFAULT_WEB_ROOT = ROOT_DIR / "web"
FRONTEND_SOURCE_SUFFIXES = {".js", ".html", ".css"}

FRONTEND_HARNESS_PATH_SNIPPETS = [
    "scripts/agent_",
    "resources/harness",
    "tests/harness_",
    "artifacts/harness-",
    "artifacts/planner",
]

PYTHON_TEST_ASSET_SNIPPETS = [
    "tests/harness_scenarios",
    "tests/harness_calibration",
    "tests/test_",
    "tests.harness_scenarios",
    "tests.harness_calibration",
    "tests.test_",
]

PYTHON_HARNESS_RESOURCE_SNIPPETS = [
    "resources/harness",
    "artifacts/harness-",
    "artifacts/planner",
    "artifacts/memory",
    "artifacts/doc-gardening",
    "docs/agent/",
]

LICENSE_GATED_ADMIN_ROUTES = {
    "/api/admin/licenses/batch",
    "/api/admin/license-enforcement",
    "/api/admin/license-enforcement/follow-default",
    "/api/admin/presentation-feature",
    "/api/admin/presentation-feature/follow-default",
    "/api/admin/licenses",
    "/api/admin/licenses/summary",
    "/api/admin/licenses/<int:license_id>",
    "/api/admin/licenses/<int:license_id>/events",
    "/api/admin/licenses/bulk-revoke",
    "/api/admin/licenses/bulk-extend",
    "/api/admin/licenses/<int:license_id>/revoke",
    "/api/admin/licenses/<int:license_id>/extend",
}

ADMIN_ONLY_NON_ADMIN_PREFIX_ROUTES = {
    "/api/metrics",
    "/api/metrics/reset",
    "/api/summaries",
    "/api/summaries/clear",
}


@dataclass
class RouteHandler:
    path: str
    methods: list[str]
    function_name: str
    decorators: list[str]
    source: str


@dataclass
class StaticGuardrailResult:
    name: str
    status: str
    detail: str
    highlights: list[str]
    repair_layer: str = ""
    recommended_actions: list[str] = field(default_factory=list)
    rerun_commands: list[str] = field(default_factory=list)


def _decorator_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        if isinstance(node.value, ast.Name):
            return f"{node.value.id}.{node.attr}"
        return node.attr
    if isinstance(node, ast.Call):
        return _decorator_name(node.func)
    return ""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _extract_route_path(node: ast.Call) -> str:
    if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
        return node.args[0].value
    return ""


def _extract_route_methods(node: ast.Call) -> list[str]:
    for keyword in node.keywords:
        if keyword.arg != "methods":
            continue
        if isinstance(keyword.value, (ast.List, ast.Tuple)):
            methods: list[str] = []
            for item in keyword.value.elts:
                if isinstance(item, ast.Constant) and isinstance(item.value, str):
                    methods.append(item.value.upper())
            return methods or ["GET"]
    return ["GET"]


def collect_route_handlers(server_file: Path = DEFAULT_SERVER_FILE) -> list[RouteHandler]:
    source = Path(server_file).read_text(encoding="utf-8")
    module = ast.parse(source, filename=str(server_file))
    handlers: list[RouteHandler] = []

    for node in module.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        route_calls = [
            decorator
            for decorator in node.decorator_list
            if isinstance(decorator, ast.Call) and _decorator_name(decorator) == "app.route"
        ]
        if not route_calls:
            continue

        decorators = [
            name
            for name in (_decorator_name(decorator) for decorator in node.decorator_list)
            if name and name != "app.route"
        ]
        source_segment = ast.get_source_segment(source, node) or ""
        for route_call in route_calls:
            path = _extract_route_path(route_call)
            if not path:
                continue
            handlers.append(
                RouteHandler(
                    path=path,
                    methods=_extract_route_methods(route_call),
                    function_name=node.name,
                    decorators=list(decorators),
                    source=source_segment,
                )
            )
    return handlers


def collect_python_files(base_dir: Path) -> list[Path]:
    if not base_dir.exists():
        return []
    return sorted(path for path in base_dir.rglob("*.py") if "__pycache__" not in path.parts)


def collect_source_files(base_dir: Path, suffixes: set[str]) -> list[Path]:
    if not base_dir.exists():
        return []
    return sorted(
        path
        for path in base_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in suffixes and "__pycache__" not in path.parts
    )


def _import_targets(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names if alias.name]
    if isinstance(node, ast.ImportFrom):
        module = str(node.module or "").strip()
        targets: list[str] = []
        if module:
            targets.append(module)
            if module == "scripts":
                targets.extend(f"scripts.{alias.name}" for alias in node.names if alias.name)
        return targets
    return []


def _display_path(path: Path, base_dir: Path) -> str:
    for root in (ROOT_DIR, base_dir):
        try:
            return str(path.relative_to(root))
        except ValueError:
            continue
    return str(path)


def _scan_forbidden_snippets(
    files: list[Path],
    *,
    base_dir: Path,
    forbidden_snippets: list[str],
) -> tuple[int, list[str]]:
    violations: list[str] = []
    checked = 0
    for source_file in files:
        checked += 1
        try:
            source = source_file.read_text(encoding="utf-8")
        except Exception as exc:
            violations.append(f"{_display_path(source_file, base_dir)} 读取失败: {exc}")
            continue
        for snippet in forbidden_snippets:
            if snippet in source:
                violations.append(f"{_display_path(source_file, base_dir)} -> {snippet}")
    return checked, violations


def _find_handler(handlers: list[RouteHandler], path: str, method: str) -> RouteHandler | None:
    normalized_method = str(method or "GET").upper()
    for handler in handlers:
        if handler.path != path:
            continue
        if normalized_method in handler.methods:
            return handler
    return None


def _contains_all(source: str, required: list[str]) -> tuple[bool, list[str]]:
    missing = [snippet for snippet in required if snippet not in source]
    return not missing, missing


def _contains_none(source: str, forbidden: list[str]) -> tuple[bool, list[str]]:
    found = [snippet for snippet in forbidden if snippet in source]
    return not found, found


def _build_result(
    name: str,
    ok: bool,
    detail: str,
    highlights: list[str],
    *,
    repair_layer: str = "",
    recommended_actions: list[str] | None = None,
    rerun_commands: list[str] | None = None,
) -> StaticGuardrailResult:
    return StaticGuardrailResult(
        name=name,
        status="PASS" if ok else "FAIL",
        detail=detail,
        highlights=highlights[:8],
        repair_layer=repair_layer if not ok else "",
        recommended_actions=list(recommended_actions or [])[:5] if not ok else [],
        rerun_commands=list(rerun_commands or [])[:3] if not ok else [],
    )


def _check_admin_routes_require_admin(handlers: list[RouteHandler]) -> StaticGuardrailResult:
    admin_routes = [
        handler
        for handler in handlers
        if handler.path.startswith("/api/admin/") or handler.path in ADMIN_ONLY_NON_ADMIN_PREFIX_ROUTES
    ]
    missing = [
        f"{handler.path} [{','.join(handler.methods)}] -> {handler.function_name}"
        for handler in admin_routes
        if "require_admin" not in handler.decorators
    ]
    return _build_result(
        "admin_routes_require_admin",
        not missing,
        f"checked={len(admin_routes)} routes missing={len(missing)}",
        missing or ["所有高风险管理/运维路由都带 require_admin。"],
        repair_layer="Flask 管理/运维路由装饰器层",
        recommended_actions=[
            "为缺失的高风险管理/运维路由补回 @require_admin，避免匿名或普通用户直接进入写接口。",
            "如果路由只是薄封装，优先在路由层补装饰器，不要把管理员校验下沉到业务分支里兜底。",
        ],
        rerun_commands=[
            "python3 scripts/agent_static_guardrails.py",
            "python3 scripts/agent_harness.py --skip-doctor --skip-smoke --guardrails-suite minimal --artifact-dir artifacts/ci/guardrails",
        ],
    )


def _check_license_routes_require_valid_license(handlers: list[RouteHandler]) -> StaticGuardrailResult:
    targets = [handler for handler in handlers if handler.path in LICENSE_GATED_ADMIN_ROUTES]
    missing = [
        f"{handler.path} [{','.join(handler.methods)}] -> {handler.function_name}"
        for handler in targets
        if "require_valid_license" not in handler.decorators
    ]
    return _build_result(
        "license_admin_routes_require_valid_license",
        not missing,
        f"checked={len(targets)} routes missing={len(missing)}",
        missing or ["所有 License 管理路由都带 require_valid_license。"],
        repair_layer="License 管理路由装饰器层",
        recommended_actions=[
            "为 License 管理和功能开关路由补回 @require_valid_license，保持管理员能力仍受有效 License 门禁约束。",
            "如果路由已委托 helper，仍应把 License 门禁放在路由入口，而不是依赖 helper 内部兜底。",
        ],
        rerun_commands=[
            "python3 scripts/agent_static_guardrails.py",
            "python3 scripts/agent_harness.py --task license-admin --workflow-execute preview",
        ],
    )


def _check_solution_view_route(handlers: list[RouteHandler]) -> StaticGuardrailResult:
    handler = _find_handler(handlers, "/api/reports/<path:filename>/solution", "GET")
    if not handler:
        return _build_result("solution_view_guard", False, "route missing", ["缺少 /api/reports/<path:filename>/solution GET 路由"])
    required = [
        "get_current_user()",
        "user_has_level_capability(",
        '"solution.view"',
        "enforce_report_owner_or_404(",
    ]
    ok, missing = _contains_all(handler.source, required)
    return _build_result(
        "solution_view_guard",
        ok,
        f"function={handler.function_name}",
        [f"缺少源码信号: {item}" for item in missing] if missing else ["已检测到登录、能力校验和 owner 约束。"],
        repair_layer="方案页查看路由层",
        recommended_actions=[
            "在方案页查看路由补回 get_current_user()、solution.view 能力校验和 enforce_report_owner_or_404() 三段式约束。",
            "不要只在 payload 构造阶段做 owner 判断，必须在路由入口先收敛登录态和 owner 边界。",
        ],
        rerun_commands=[
            "python3 scripts/agent_static_guardrails.py",
            "python3 scripts/agent_harness.py --task report-solution --workflow-execute preview",
        ],
    )


def _check_solution_share_route(handlers: list[RouteHandler]) -> StaticGuardrailResult:
    handler = _find_handler(handlers, "/api/reports/<path:filename>/solution/share", "POST")
    if not handler:
        return _build_result("solution_share_guard", False, "route missing", ["缺少 /api/reports/<path:filename>/solution/share POST 路由"])
    required = [
        "get_current_user()",
        "user_has_level_capability(",
        '"solution.share"',
        "enforce_report_owner_or_404(",
        "create_or_get_solution_share(",
    ]
    ok, missing = _contains_all(handler.source, required)
    return _build_result(
        "solution_share_guard",
        ok,
        f"function={handler.function_name}",
        [f"缺少源码信号: {item}" for item in missing] if missing else ["已检测到登录、分享能力校验和 owner 约束。"],
        repair_layer="方案页分享路由层",
        recommended_actions=[
            "在方案页分享路由补回 get_current_user()、solution.share 能力校验和 enforce_report_owner_or_404()，再调用 create_or_get_solution_share()。",
            "分享链接的创建必须在 owner 校验之后，避免通过分享接口绕过报告归属判断。",
        ],
        rerun_commands=[
            "python3 scripts/agent_static_guardrails.py",
            "python3 scripts/agent_harness.py --task report-solution --workflow-execute preview",
        ],
    )


def _check_public_solution_route(handlers: list[RouteHandler]) -> StaticGuardrailResult:
    handler = _find_handler(handlers, "/api/public/solutions/<share_token>", "GET")
    if not handler:
        return _build_result("public_solution_readonly", False, "route missing", ["缺少 /api/public/solutions/<share_token> GET 路由"])
    required = [
        "get_solution_share_record(",
        "get_report_owner_id(report_name) != owner_user_id",
        'payload["share_mode"] = "public"',
        'payload["report_name"] = ""',
        '"solution_share": False',
        'response.headers["X-Robots-Tag"]',
    ]
    forbidden = ["@require_login", "@require_admin", "get_current_user()"]
    has_required, missing = _contains_all(handler.source, required)
    has_no_forbidden, found = _contains_none(handler.source, forbidden)
    ok = has_required and has_no_forbidden
    highlights: list[str] = []
    highlights.extend([f"缺少源码信号: {item}" for item in missing])
    highlights.extend([f"只读分享路由不应出现: {item}" for item in found])
    if not highlights:
        highlights.append("已检测到 owner 校验、匿名只读字段收敛和 noindex header。")
    return _build_result(
        "public_solution_readonly",
        ok,
        f"function={handler.function_name}",
        highlights,
        repair_layer="公开分享只读载荷收敛层",
        recommended_actions=[
            "公开分享路由保留匿名只读模式，不要重新引入登录依赖、写权限或泄露 report_name。",
            "补回 share_mode=public、viewer_capabilities.solution_share=False、report_name 置空与 noindex header 约束。",
        ],
        rerun_commands=[
            "python3 scripts/agent_static_guardrails.py",
            "python3 scripts/agent_harness.py --task report-solution --workflow-execute preview",
        ],
    )


def _check_ownership_preview_route(handlers: list[RouteHandler]) -> StaticGuardrailResult:
    handler = _find_handler(handlers, "/api/admin/ownership-migrations/preview", "POST")
    if not handler:
        return _build_result("ownership_preview_dry_run", False, "route missing", ["缺少 ownership preview 路由"])
    required = ["apply_mode=False", "_store_admin_ownership_preview("]
    ok = "require_admin" in handler.decorators
    has_required, missing = _contains_all(handler.source, required)
    ok = ok and has_required
    highlights: list[str] = []
    if "require_admin" not in handler.decorators:
        highlights.append("preview 路由缺少 require_admin 装饰器")
    highlights.extend([f"缺少源码信号: {item}" for item in missing])
    if not highlights:
        highlights.append("已检测到管理员鉴权、dry-run 执行和 preview 持久化。")
    return _build_result(
        "ownership_preview_dry_run",
        ok,
        f"function={handler.function_name}",
        highlights,
        repair_layer="ownership preview 路由层",
        recommended_actions=[
            "preview 路由必须保留 @require_admin、apply_mode=False 和 preview 持久化，确保管理员先看到 dry-run 结果再进入 apply。",
            "不要把 preview 实现退化成直接 apply；preview token 和审计证据要在 preview 阶段先落盘。",
        ],
        rerun_commands=[
            "python3 scripts/agent_static_guardrails.py",
            "python3 scripts/agent_harness.py --task ownership-migration --task-var target_account=13700000000 --workflow-execute preview",
        ],
    )


def _check_ownership_apply_route(handlers: list[RouteHandler]) -> StaticGuardrailResult:
    handler = _find_handler(handlers, "/api/admin/ownership-migrations/apply", "POST")
    if not handler:
        return _build_result("ownership_apply_confirmation", False, "route missing", ["缺少 ownership apply 路由"])
    required = [
        "_get_admin_ownership_preview(",
        "preview_token",
        "_serialize_admin_ownership_request_payload(",
        "confirm_phrase",
        "confirm_text",
        "apply_mode=True",
    ]
    ok = "require_admin" in handler.decorators
    has_required, missing = _contains_all(handler.source, required)
    ok = ok and has_required
    highlights: list[str] = []
    if "require_admin" not in handler.decorators:
        highlights.append("apply 路由缺少 require_admin 装饰器")
    highlights.extend([f"缺少源码信号: {item}" for item in missing])
    if not highlights:
        highlights.append("已检测到管理员鉴权、preview token 校验、确认词和 apply_mode=True。")
    return _build_result(
        "ownership_apply_confirmation",
        ok,
        f"function={handler.function_name}",
        highlights,
        repair_layer="ownership apply 路由层",
        recommended_actions=[
            "apply 路由补回 preview_token、confirm_phrase/confirm_text 与 apply_mode=True，保持 preview -> confirm -> apply 的确认链。",
            "正式 apply 前不要跳过 _get_admin_ownership_preview() 与请求 payload 序列化，避免脱离 preview 直接写数据。",
        ],
        rerun_commands=[
            "python3 scripts/agent_static_guardrails.py",
            "python3 scripts/agent_harness.py --task ownership-migration --task-var target_account=13700000000 --allow-apply",
        ],
    )


def _check_ownership_rollback_route(handlers: list[RouteHandler]) -> StaticGuardrailResult:
    handler = _find_handler(handlers, "/api/admin/ownership-migrations/rollback", "POST")
    if not handler:
        return _build_result("ownership_rollback_requires_backup", False, "route missing", ["缺少 ownership rollback 路由"])
    required = ["backup_id = ", "if not backup_id:"]
    ok = "require_admin" in handler.decorators
    has_required, missing = _contains_all(handler.source, required)
    ok = ok and has_required
    highlights: list[str] = []
    if "require_admin" not in handler.decorators:
        highlights.append("rollback 路由缺少 require_admin 装饰器")
    highlights.extend([f"缺少源码信号: {item}" for item in missing])
    if not highlights:
        highlights.append("已检测到管理员鉴权和 backup_id 前置校验。")
    return _build_result(
        "ownership_rollback_requires_backup",
        ok,
        f"function={handler.function_name}",
        highlights,
        repair_layer="ownership rollback 路由层",
        recommended_actions=[
            "rollback 路由补回 @require_admin 和 backup_id 前置校验，确保回滚动作只能基于已有备份执行。",
            "不要在 rollback 路由里推导默认 backup；没有显式 backup_id 时必须阻断。",
        ],
        rerun_commands=[
            "python3 scripts/agent_static_guardrails.py",
            "python3 scripts/agent_harness.py --task ownership-migration --task-var target_account=13700000000 --workflow-execute preview",
        ],
    )


def _check_config_center_routes_delegate_helpers(handlers: list[RouteHandler]) -> StaticGuardrailResult:
    get_handler = _find_handler(handlers, "/api/admin/config-center", "GET")
    save_handler = _find_handler(handlers, "/api/admin/config-center/save", "POST")
    highlights: list[str] = []
    ok = True

    if not get_handler:
        return _build_result(
            "config_center_routes_delegate_helpers",
            False,
            "route missing",
            ["缺少 /api/admin/config-center GET 路由"],
        )
    if not save_handler:
        return _build_result(
            "config_center_routes_delegate_helpers",
            False,
            "route missing",
            ["缺少 /api/admin/config-center/save POST 路由"],
        )

    get_required = ["build_admin_config_center_payload("]
    get_forbidden = [
        "_build_admin_settings_source_payload(",
        "_write_admin_env_updates(",
        "_write_admin_config_updates(",
        "_write_admin_site_config_updates(",
    ]
    save_required = [
        "save_admin_config_group(",
        'source=str(data.get("source") or "").strip()',
        'group_id=str(data.get("group_id") or "").strip()',
        "values=data.get(\"values\")",
    ]
    save_forbidden = [
        "_write_admin_env_updates(",
        "_write_admin_config_updates(",
        "_write_admin_site_config_updates(",
        "write_text(",
    ]

    has_required, missing = _contains_all(get_handler.source, get_required)
    has_no_forbidden, found = _contains_none(get_handler.source, get_forbidden)
    ok = ok and has_required and has_no_forbidden
    highlights.extend([f"config-center GET 缺少源码信号: {item}" for item in missing])
    highlights.extend([f"config-center GET 不应直接调用: {item}" for item in found])

    has_required, missing = _contains_all(save_handler.source, save_required)
    has_no_forbidden, found = _contains_none(save_handler.source, save_forbidden)
    ok = ok and has_required and has_no_forbidden
    highlights.extend([f"config-center SAVE 缺少源码信号: {item}" for item in missing])
    highlights.extend([f"config-center SAVE 不应直接调用: {item}" for item in found])

    if not highlights:
        highlights.append("配置中心路由已委托 build_admin_config_center_payload/save_admin_config_group，未在路由层直接写配置文件。")
    return _build_result(
        "config_center_routes_delegate_helpers",
        ok,
        f"get={get_handler.function_name} save={save_handler.function_name}",
        highlights,
        repair_layer="配置中心路由委托层",
        recommended_actions=[
            "配置中心 GET/POST 路由应继续委托 build_admin_config_center_payload() 和 save_admin_config_group()，不要在路由层直接写 .env、config.py 或 site-config.js。",
            "如果需要新增配置源处理，优先扩展 helper/service，而不是把文件写入逻辑塞回 Flask 路由。",
        ],
        rerun_commands=[
            "python3 scripts/agent_static_guardrails.py",
            "python3 scripts/agent_harness.py --task config-center --workflow-execute preview",
        ],
    )


def _check_business_python_does_not_import_harness(web_root: Path) -> StaticGuardrailResult:
    violations: list[str] = []
    checked = 0
    base_dir = web_root.parent if web_root.name == "web" else web_root
    for python_file in collect_python_files(web_root):
        checked += 1
        try:
            source = python_file.read_text(encoding="utf-8")
            module = ast.parse(source, filename=str(python_file))
        except Exception as exc:
            violations.append(f"{_display_path(python_file, base_dir)} 解析失败: {exc}")
            continue
        for node in ast.walk(module):
            for target in _import_targets(node):
                if target.startswith("scripts.agent_"):
                    violations.append(f"{_display_path(python_file, base_dir)} -> {target}")
    return _build_result(
        "business_python_does_not_import_harness",
        not violations,
        f"checked={checked} python files violations={len(violations)}",
        violations or ["web/ 下 Python 业务代码未反向依赖 scripts.agent_* harness 脚本。"],
        repair_layer="Python 业务模块 import 边界",
        recommended_actions=[
            "不要在 web/server.py 或 web/server_modules/* 中直接 import scripts.agent_*；把共享逻辑下沉到业务 helper / service，再由 harness 侧读取结果。",
            "如果只是想复用校验或报告格式，优先抽到 web/server_modules/* 或通用模块，避免业务代码反向依赖 harness 脚本。",
        ],
        rerun_commands=[
            "python3 scripts/agent_static_guardrails.py",
            "python3 scripts/agent_harness.py --profile auto",
        ],
    )


def _check_frontend_assets_do_not_reference_harness_paths(web_root: Path) -> StaticGuardrailResult:
    base_dir = web_root.parent if web_root.name == "web" else web_root
    checked, violations = _scan_forbidden_snippets(
        collect_source_files(web_root, FRONTEND_SOURCE_SUFFIXES),
        base_dir=base_dir,
        forbidden_snippets=FRONTEND_HARNESS_PATH_SNIPPETS,
    )
    return _build_result(
        "frontend_assets_do_not_reference_harness_paths",
        not violations,
        f"checked={checked} frontend files violations={len(violations)}",
        violations or ["web/ 下前端静态资源未反向引用 harness 路径、工件或测试语料。"],
        repair_layer="前端静态资源依赖边界",
        recommended_actions=[
            "前端静态资源不要直接引用 scripts/agent_*、resources/harness、tests/harness_* 或 artifacts/* 路径；浏览器需要的信息应通过后端 API 暴露。",
            "如果只是调试说明或运行指引，把内容留在 AGENTS / docs / tests，不要把 harness 路径嵌进 app.js、solution.js、HTML 或 CSS。",
        ],
        rerun_commands=[
            "python3 scripts/agent_static_guardrails.py",
            "python3 scripts/agent_browser_smoke.py --suite extended",
        ],
    )


def _check_runtime_python_does_not_reference_test_assets(web_root: Path) -> StaticGuardrailResult:
    base_dir = web_root.parent if web_root.name == "web" else web_root
    checked, violations = _scan_forbidden_snippets(
        collect_python_files(web_root),
        base_dir=base_dir,
        forbidden_snippets=PYTHON_TEST_ASSET_SNIPPETS,
    )
    return _build_result(
        "runtime_python_does_not_reference_test_assets",
        not violations,
        f"checked={checked} python files violations={len(violations)}",
        violations or ["web/ 下 Python 运行时代码未反向依赖 tests/ 下的 harness 场景、校准样本或测试模块。"],
        repair_layer="Python 运行时与测试资产边界",
        recommended_actions=[
            "业务运行时代码不要直接读取 tests/harness_scenarios、tests/harness_calibration 或 tests/test_*；这类语料只给 evaluator、guardrail 和测试进程使用。",
            "如果运行时确实需要共享示例或默认值，优先抽到正式的业务配置/fixture 模块，再让测试与 harness 复用它，而不是反向读取 tests/。",
        ],
        rerun_commands=[
            "python3 scripts/agent_static_guardrails.py",
            "python3 scripts/agent_harness.py --profile auto",
        ],
    )


def _check_runtime_python_does_not_reference_harness_resources(web_root: Path) -> StaticGuardrailResult:
    base_dir = web_root.parent if web_root.name == "web" else web_root
    checked, violations = _scan_forbidden_snippets(
        collect_python_files(web_root),
        base_dir=base_dir,
        forbidden_snippets=PYTHON_HARNESS_RESOURCE_SNIPPETS,
    )
    return _build_result(
        "runtime_python_does_not_reference_harness_resources",
        not violations,
        f"checked={checked} python files violations={len(violations)}",
        violations or ["web/ 下 Python 运行时代码未反向依赖 harness resources、artifact 或 agent 文档指针。"],
        repair_layer="Python 运行时与 harness 资源边界",
        recommended_actions=[
            "业务运行时代码不要直接读取 resources/harness、artifacts/* 或 docs/agent/* 作为正式依赖；这些内容只服务 planner/mission/contract/evaluator/handoff。",
            "如果某段业务逻辑需要稳定配置，优先把配置移到业务 service/helper 或正式配置源，不要从 harness 文档、artifact 或 task 元数据里取值。",
        ],
        rerun_commands=[
            "python3 scripts/agent_static_guardrails.py",
            "python3 scripts/agent_harness.py --profile auto",
        ],
    )


def run_static_guardrails(*, server_file: Path = DEFAULT_SERVER_FILE) -> tuple[dict[str, Any], int]:
    handlers = collect_route_handlers(server_file)
    web_root = server_file.parent if server_file.parent.exists() else DEFAULT_WEB_ROOT
    results = [
        _check_admin_routes_require_admin(handlers),
        _check_license_routes_require_valid_license(handlers),
        _check_solution_view_route(handlers),
        _check_solution_share_route(handlers),
        _check_public_solution_route(handlers),
        _check_config_center_routes_delegate_helpers(handlers),
        _check_frontend_assets_do_not_reference_harness_paths(web_root),
        _check_runtime_python_does_not_reference_test_assets(web_root),
        _check_runtime_python_does_not_reference_harness_resources(web_root),
        _check_business_python_does_not_import_harness(web_root),
        _check_ownership_preview_route(handlers),
        _check_ownership_apply_route(handlers),
        _check_ownership_rollback_route(handlers),
    ]
    summary = {
        "PASS": sum(1 for item in results if item.status == "PASS"),
        "FAIL": sum(1 for item in results if item.status == "FAIL"),
    }
    overall = "READY" if summary["FAIL"] == 0 else "BLOCKED"
    payload = {
        "generated_at": utc_now_iso(),
        "server_file": str(server_file),
        "route_count": len(handlers),
        "results": [asdict(item) for item in results],
        "summary": summary,
        "overall": overall,
    }
    return payload, 0 if overall == "READY" else 2


def render_text_output(payload: dict[str, Any]) -> None:
    print("DeepVision agent static guardrails")
    print(f"server: {payload.get('server_file', '')}")
    print(f"routes: {int(payload.get('route_count', 0) or 0)}")
    print("")
    for item in list(payload.get("results", []) or []):
        print(f"[{item.get('status', '')}] {item.get('name', '')}: {item.get('detail', '')}")
        for line in list(item.get("highlights", []) or []):
            print(f"        - {line}")
        if str(item.get("status") or "").strip() == "FAIL":
            repair_layer = str(item.get("repair_layer") or "").strip()
            recommended_actions = [str(line or "").strip() for line in list(item.get("recommended_actions", []) or []) if str(line or "").strip()]
            rerun_commands = [str(line or "").strip() for line in list(item.get("rerun_commands", []) or []) if str(line or "").strip()]
            if repair_layer or recommended_actions or rerun_commands:
                print("        Action for Agent:")
                if repair_layer:
                    print(f"        - 修复层级: {repair_layer}")
                for line in recommended_actions:
                    print(f"        - 建议动作: {line}")
                for line in rerun_commands:
                    print(f"        - 推荐复跑: {line}")
    summary = payload.get("summary", {}) if isinstance(payload.get("summary", {}), dict) else {}
    print("")
    print(f"Summary: PASS={int(summary.get('PASS', 0) or 0)} FAIL={int(summary.get('FAIL', 0) or 0)}")
    print(f"Overall: {payload.get('overall', '')}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DeepVision agent 源码级静态 guardrail")
    parser.add_argument("--server-file", default=str(DEFAULT_SERVER_FILE), help="显式指定要扫描的 Flask 服务文件")
    parser.add_argument("--json", action="store_true", help="输出 JSON 摘要")
    parser.add_argument("--list", action="store_true", help="仅列出内置静态 guardrail 规则")
    return parser


def list_rules() -> int:
    rules = [
        "admin_routes_require_admin",
        "license_admin_routes_require_valid_license",
        "solution_view_guard",
        "solution_share_guard",
        "public_solution_readonly",
        "config_center_routes_delegate_helpers",
        "frontend_assets_do_not_reference_harness_paths",
        "runtime_python_does_not_reference_test_assets",
        "runtime_python_does_not_reference_harness_resources",
        "business_python_does_not_import_harness",
        "ownership_preview_dry_run",
        "ownership_apply_confirmation",
        "ownership_rollback_requires_backup",
    ]
    print("DeepVision agent static guardrails")
    for index, rule in enumerate(rules, 1):
        print(f"{index}. {rule}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.list:
        return list_rules()
    payload, exit_code = run_static_guardrails(server_file=Path(args.server_file).expanduser().resolve())
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        render_text_output(payload)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
