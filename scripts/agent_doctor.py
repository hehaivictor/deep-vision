#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
DeepVision agent 环境自检。

目标：
1. 给 agent 一个稳定、只读的仓库与环境检查入口
2. 在真正改代码前尽早发现 env、工具链和高风险配置问题
3. 输出可读摘要，并用退出码表达是否存在阻断项
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping


ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_ENV_FILES = {
    "local": ROOT_DIR / "web" / ".env.local",
    "cloud": ROOT_DIR / "web" / ".env.cloud",
}
REQUIRED_REPO_PATHS = [
    ROOT_DIR / "AGENTS.md",
    ROOT_DIR / "README.md",
    ROOT_DIR / "web" / "server.py",
    ROOT_DIR / "web" / "app.js",
    ROOT_DIR / "tests" / "test_api_comprehensive.py",
    ROOT_DIR / "tests" / "test_security_regression.py",
    ROOT_DIR / "docs" / "agent" / "README.md",
]


@dataclass
class CheckResult:
    name: str
    status: str
    detail: str
    hint: str = ""


def looks_like_placeholder(raw_value: str) -> bool:
    value = str(raw_value or "").strip()
    if not value:
        return True
    lowered = value.lower()
    return (
        lowered.startswith("your-")
        or "replace-with" in lowered
        or lowered in {"changeme", "todo", "example", "example.com"}
    )


def parse_env_file(env_file: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not env_file.exists():
        return values
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if value and len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[key] = value
    return values


def resolve_selected_env_file(profile: str, explicit_env_file: str, process_env: Mapping[str, str]) -> tuple[Path | None, str]:
    explicit_text = str(explicit_env_file or "").strip()
    if explicit_text:
        target = Path(explicit_text).expanduser()
        if not target.is_absolute():
            target = (ROOT_DIR / target).resolve()
        return target, "explicit"

    process_env_file = str(process_env.get("DEEPVISION_ENV_FILE", "") or "").strip()
    if process_env_file:
        target = Path(process_env_file).expanduser()
        if not target.is_absolute():
            target = (ROOT_DIR / target).resolve()
        return target, "process_env"

    if profile in DEFAULT_ENV_FILES:
        return DEFAULT_ENV_FILES[profile], f"profile:{profile}"

    for profile_name in ("local", "cloud"):
        candidate = DEFAULT_ENV_FILES[profile_name]
        if candidate.exists():
            return candidate, f"auto:{profile_name}"

    return None, "none"


def build_effective_env(selected_env_file: Path | None, process_env: Mapping[str, str]) -> tuple[dict[str, str], dict[str, str]]:
    file_values = parse_env_file(selected_env_file) if selected_env_file else {}
    effective = dict(file_values)
    for key, value in process_env.items():
        if key.startswith("DEEPVISION_") or key in {
            "CONFIG_RESOLUTION_MODE",
            "DEBUG_MODE",
            "ENABLE_AI",
            "SECRET_KEY",
            "AUTH_DB_PATH",
            "LICENSE_DB_PATH",
            "META_INDEX_DB_PATH",
            "INSTANCE_SCOPE_KEY",
            "INSTANCE_SCOPE_ENFORCEMENT_ENABLED",
            "SMS_LOGIN_ENABLED",
            "SMS_PROVIDER",
            "SMS_TEST_CODE",
            "WECHAT_LOGIN_ENABLED",
            "WECHAT_APP_ID",
            "WECHAT_APP_SECRET",
            "WECHAT_REDIRECT_URI",
            "JD_SMS_ACCESS_KEY_ID",
            "JD_SMS_ACCESS_KEY_SECRET",
            "JD_SMS_SIGN_ID",
            "JD_SMS_TEMPLATE_ID_LOGIN",
            "JD_SMS_TEMPLATE_ID_BIND",
            "JD_SMS_TEMPLATE_ID_RECOVER",
        }:
            effective[key] = value
    return file_values, effective


def parse_bool(raw_value: str, default: bool = False) -> bool:
    text = str(raw_value or "").strip().lower()
    if not text:
        return default
    return text in {"1", "true", "yes", "on"}


def resolve_local_path(raw_value: str) -> Path | None:
    value = str(raw_value or "").strip()
    if not value:
        return None
    lowered = value.lower()
    if "://" in lowered:
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = (ROOT_DIR / path).resolve()
    return path


def add_result(results: list[CheckResult], name: str, status: str, detail: str, hint: str = "") -> None:
    results.append(CheckResult(name=name, status=status, detail=detail, hint=hint))


def collect_checks(
    *,
    profile: str,
    selected_env_file: Path | None,
    env_source: str,
    file_values: Mapping[str, str],
    effective_env: Mapping[str, str],
) -> list[CheckResult]:
    results: list[CheckResult] = []

    missing_repo_paths = [path for path in REQUIRED_REPO_PATHS if not path.exists()]
    if missing_repo_paths:
        add_result(
            results,
            "仓库结构",
            "FAIL",
            "缺少关键路径: " + ", ".join(path.relative_to(ROOT_DIR).as_posix() for path in missing_repo_paths),
        )
    else:
        add_result(results, "仓库结构", "PASS", "关键入口、测试与 agent 文档均存在。")

    python_path = shutil.which("python3")
    if python_path:
        add_result(results, "Python", "PASS", f"已检测到 python3: {python_path}")
    else:
        add_result(results, "Python", "FAIL", "未找到 python3，无法运行脚本与测试。")

    uv_path = shutil.which("uv")
    if uv_path:
        add_result(results, "uv", "PASS", f"已检测到 uv: {uv_path}")
    elif profile in {"local", "cloud", "auto"}:
        add_result(results, "uv", "FAIL", "未找到 uv，本地与云端联调启动脚本默认依赖 uv。")
    else:
        add_result(results, "uv", "WARN", "未找到 uv；如果仅运行生产脚本可暂不阻断。")

    if selected_env_file is None:
        add_result(
            results,
            "环境文件",
            "WARN",
            "未解析到环境文件，将只基于进程环境判断。",
            "可通过 --env-file 指定，或设置 DEEPVISION_ENV_FILE。",
        )
    elif not selected_env_file.exists():
        add_result(
            results,
            "环境文件",
            "FAIL",
            f"环境文件不存在: {selected_env_file}",
            "本地开发通常使用 web/.env.local，云端联调通常使用 web/.env.cloud。",
        )
    else:
        add_result(
            results,
            "环境文件",
            "PASS",
            f"已选择 {selected_env_file}（来源: {env_source}），解析到 {len(file_values)} 个字段。",
        )

    debug_mode = parse_bool(effective_env.get("DEBUG_MODE", ""), default=False)
    sms_login_enabled = parse_bool(effective_env.get("SMS_LOGIN_ENABLED", ""), default=True)
    sms_provider = str(effective_env.get("SMS_PROVIDER", "") or "").strip().lower()
    secret_key = str(effective_env.get("SECRET_KEY", "") or "")
    instance_scope_key = str(effective_env.get("INSTANCE_SCOPE_KEY", "") or "")

    if looks_like_placeholder(secret_key):
        status = "WARN" if profile in {"local", "auto"} else "FAIL"
        add_result(
            results,
            "SECRET_KEY",
            status,
            "SECRET_KEY 缺失或仍为占位值。",
            "调试环境至少使用本机随机值；云端与生产环境必须替换为真实强密钥。",
        )
    else:
        add_result(results, "SECRET_KEY", "PASS", "SECRET_KEY 已配置为非占位值。")

    if looks_like_placeholder(instance_scope_key):
        status = "WARN" if profile in {"local", "auto"} else "FAIL"
        add_result(
            results,
            "INSTANCE_SCOPE_KEY",
            status,
            "INSTANCE_SCOPE_KEY 缺失或仍为占位值。",
            "共享 data 目录或多实例部署时，这会直接影响数据可见边界。",
        )
    else:
        add_result(results, "INSTANCE_SCOPE_KEY", "PASS", f"已配置实例隔离键: {instance_scope_key}")

    if not sms_login_enabled:
        add_result(results, "短信登录", "PASS", "当前未启用短信登录。")
        if sms_provider:
            add_result(results, "SMS_PROVIDER", "PASS", f"短信登录已关闭，当前短信通道配置为 {sms_provider}。")
        else:
            add_result(results, "SMS_PROVIDER", "PASS", "短信登录已关闭，未显式配置短信通道。")
    elif sms_provider == "mock":
        if debug_mode:
            add_result(results, "SMS_PROVIDER", "WARN", "当前使用 mock 短信，仅适合本地调试或演示环境。")
        else:
            add_result(
                results,
                "SMS_PROVIDER",
                "FAIL",
                "当前使用 mock 短信，但 DEBUG_MODE=false。",
                "README 已明确说明此组合不适合正式环境，服务启动期也会拒绝。",
            )
    elif sms_provider == "jdcloud":
        missing_sms = [
            key
            for key in (
                "JD_SMS_ACCESS_KEY_ID",
                "JD_SMS_ACCESS_KEY_SECRET",
                "JD_SMS_SIGN_ID",
                "JD_SMS_TEMPLATE_ID_LOGIN",
            )
            if looks_like_placeholder(effective_env.get(key, ""))
        ]
        if missing_sms:
            add_result(
                results,
                "JDCloud 短信",
                "FAIL",
                "缺少关键短信配置: " + ", ".join(missing_sms),
                "至少补齐 Access Key、签名 ID 和登录模板 ID。",
            )
        else:
            add_result(results, "JDCloud 短信", "PASS", "关键短信配置已就绪。")
    elif sms_provider:
        add_result(results, "SMS_PROVIDER", "WARN", f"检测到未知短信提供商: {sms_provider}")
    else:
        add_result(results, "SMS_PROVIDER", "WARN", "未显式配置 SMS_PROVIDER。")

    if parse_bool(effective_env.get("WECHAT_LOGIN_ENABLED", ""), default=False):
        missing_wechat = [
            key
            for key in ("WECHAT_APP_ID", "WECHAT_APP_SECRET", "WECHAT_REDIRECT_URI")
            if looks_like_placeholder(effective_env.get(key, ""))
        ]
        if missing_wechat:
            add_result(
                results,
                "微信登录",
                "FAIL",
                "微信登录已启用，但缺少字段: " + ", ".join(missing_wechat),
            )
        else:
            add_result(results, "微信登录", "PASS", "微信登录启用且关键配置完整。")
    else:
        add_result(results, "微信登录", "PASS", "当前未启用微信登录。")

    for name, raw_value in (
        ("AUTH_DB_PATH", effective_env.get("AUTH_DB_PATH", "data/auth/users.db")),
        ("LICENSE_DB_PATH", effective_env.get("LICENSE_DB_PATH", "data/auth/licenses.db")),
        ("META_INDEX_DB_PATH", effective_env.get("META_INDEX_DB_PATH", "data/meta_index.db")),
        ("CUSTOM_SCENARIOS_DIR", effective_env.get("CUSTOM_SCENARIOS_DIR", "data/scenarios/custom")),
    ):
        local_path = resolve_local_path(str(raw_value or ""))
        if local_path is None:
            add_result(results, name, "PASS", f"使用远程或非文件路径配置: {raw_value}")
            continue
        parent = local_path.parent if local_path.suffix else local_path
        if parent.exists():
            add_result(results, name, "PASS", f"路径可解析，父目录存在: {parent}")
        else:
            add_result(
                results,
                name,
                "WARN",
                f"路径可解析，但父目录暂不存在: {parent}",
                "若这是首次初始化，可在启动或预启动阶段创建；若用于现网，请确认部署卷和权限。",
            )

    if parse_bool(effective_env.get("LICENSE_ENFORCEMENT_ENABLED", ""), default=False):
        add_result(results, "License 开关", "PASS", "当前启用了登录后 License 强制校验。")
    else:
        add_result(results, "License 开关", "WARN", "当前未启用登录后 License 强制校验。")

    return results


def build_summary(results: list[CheckResult]) -> dict[str, int]:
    summary = {"PASS": 0, "WARN": 0, "FAIL": 0}
    for item in results:
        summary[item.status] = summary.get(item.status, 0) + 1
    return summary


def resolve_exit_code(summary: Mapping[str, int], *, strict: bool = False) -> int:
    if int(summary.get("FAIL", 0)) > 0:
        return 2
    if strict and int(summary.get("WARN", 0)) > 0:
        return 1
    return 0


def run_doctor(
    *,
    profile: str,
    env_file: str = "",
    strict: bool = False,
    process_env: Mapping[str, str] | None = None,
) -> tuple[dict, int]:
    current_env = dict(process_env or os.environ)
    selected_env_file, env_source = resolve_selected_env_file(profile, env_file, current_env)
    file_values, effective_env = build_effective_env(selected_env_file, current_env)
    results = collect_checks(
        profile=profile,
        selected_env_file=selected_env_file,
        env_source=env_source,
        file_values=file_values,
        effective_env=effective_env,
    )
    summary = build_summary(results)
    payload = {
        "profile": profile,
        "root_dir": str(ROOT_DIR),
        "selected_env_file": str(selected_env_file) if selected_env_file else "",
        "env_source": env_source,
        "summary": summary,
        "results": [asdict(item) for item in results],
    }
    return payload, resolve_exit_code(summary, strict=strict)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DeepVision agent 环境自检")
    parser.add_argument(
        "--profile",
        default="auto",
        choices=["auto", "local", "cloud", "production"],
        help="检查场景；auto 会优先使用 DEEPVISION_ENV_FILE，其次探测 web/.env.local 或 web/.env.cloud。",
    )
    parser.add_argument("--env-file", default="", help="显式指定环境文件路径")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出检查结果")
    parser.add_argument("--strict", action="store_true", help="将 WARN 也视为非零退出")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload, exit_code = run_doctor(
        profile=args.profile,
        env_file=args.env_file,
        strict=args.strict,
    )
    summary = payload["summary"]
    results = [CheckResult(**item) for item in payload["results"]]
    selected_env_file = payload["selected_env_file"]
    env_source = payload["env_source"]

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("DeepVision agent doctor")
        print(f"仓库目录: {payload['root_dir']}")
        print(f"检查场景: {payload['profile']}")
        if selected_env_file:
            print(f"环境文件: {selected_env_file} ({env_source})")
        else:
            print(f"环境文件: 未选择 ({env_source})")
        print("")
        for item in results:
            print(f"[{item.status}] {item.name}: {item.detail}")
            if item.hint:
                print(f"        hint: {item.hint}")
        print("")
        print(
            "Summary: "
            f"PASS={summary['PASS']} "
            f"WARN={summary['WARN']} "
            f"FAIL={summary['FAIL']}"
        )

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
