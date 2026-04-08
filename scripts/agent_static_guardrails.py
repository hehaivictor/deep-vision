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
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SERVER_FILE = ROOT_DIR / "web" / "server.py"

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


def _build_result(name: str, ok: bool, detail: str, highlights: list[str]) -> StaticGuardrailResult:
    return StaticGuardrailResult(
        name=name,
        status="PASS" if ok else "FAIL",
        detail=detail,
        highlights=highlights[:8],
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
    )


def run_static_guardrails(*, server_file: Path = DEFAULT_SERVER_FILE) -> tuple[dict[str, Any], int]:
    handlers = collect_route_handlers(server_file)
    results = [
        _check_admin_routes_require_admin(handlers),
        _check_license_routes_require_valid_license(handlers),
        _check_solution_view_route(handlers),
        _check_solution_share_route(handlers),
        _check_public_solution_route(handlers),
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
