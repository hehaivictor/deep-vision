#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
DeepVision agent 任务工作流执行器。

目标：
1. 把 task workflow 从“只渲染”升级成“可受控执行”
2. 默认只做 plan/preview，不默认触发高风险 apply
3. 输出结构化步骤结果，便于 harness 落盘与交接
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts import agent_profiles
from scripts import agent_doctor
from scripts import agent_browser_smoke
from scripts import admin_ownership_service
from db_compat import connect_db
from db_compat import db_target_exists
from db_compat import resolve_db_target
from scripts.agent_test_runner import SuiteCase
from scripts.agent_test_runner import SuiteExecution
from scripts.agent_test_runner import build_unittest_command
from scripts.agent_test_runner import run_suite_process


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def extract_highlights(raw_text: str, *, limit: int = 8) -> list[str]:
    lines = [line.rstrip() for line in str(raw_text or "").splitlines() if line.strip()]
    if not lines:
        return []
    focused = [
        line
        for line in lines
        if line.startswith("FAIL:")
        or line.startswith("ERROR:")
        or "Traceback" in line
        or "AssertionError" in line
        or line.startswith("FAILED")
        or line.startswith("OK")
    ]
    selected = focused if focused else lines[-limit:]
    return selected[:limit]


def _resolve_local_path(root_dir: Path, raw_value: object) -> Path:
    candidate = Path(str(raw_value or "").strip()).expanduser()
    if not candidate.is_absolute():
        candidate = (root_dir / candidate).resolve()
    return candidate


def _normalize_artifact_specs(raw_value: Any) -> list[str]:
    if isinstance(raw_value, str):
        text = str(raw_value).strip()
        return [text] if text else []
    if isinstance(raw_value, list):
        result: list[str] = []
        for item in raw_value:
            text = str(item or "").strip()
            if text:
                result.append(text)
        return result
    return []


def build_step_summary(step_results: list[dict[str, Any]]) -> dict[str, int]:
    summary = {"PASS": 0, "FAIL": 0, "BLOCKED": 0, "MANUAL": 0, "PLANNED": 0, "SKIP": 0}
    for item in step_results:
        status = str(item.get("status") or "").strip()
        if status in summary:
            summary[status] += 1
    return summary


def determine_overall(
    *,
    execute_mode: str,
    workflow: dict[str, Any],
    precondition_results: list[dict[str, Any]],
    step_results: list[dict[str, Any]],
) -> str:
    if any(str(item.get("status") or "").strip() == "BLOCKED" for item in precondition_results):
        return "ATTENTION_REQUIRED"
    if any(str(item.get("status") or "").strip() == "FAIL" for item in step_results):
        return "BLOCKED"
    if any(str(item.get("status") or "").strip() == "BLOCKED" for item in step_results):
        return "ATTENTION_REQUIRED"
    if list(workflow.get("missing_vars", []) or []):
        return "ATTENTION_REQUIRED"
    if execute_mode == "plan":
        return "PLANNED"
    return "READY"


def _run_command(command: str, *, root_dir: Path) -> dict[str, Any]:
    started_at = time.perf_counter()
    completed = subprocess.run(
        shlex.split(str(command or "").strip()),
        cwd=str(root_dir),
        capture_output=True,
        text=True,
        check=False,
    )
    duration_ms = round((time.perf_counter() - started_at) * 1000.0, 2)
    combined = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
    return {
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "duration_ms": duration_ms,
        "highlights": extract_highlights(combined),
    }


def _build_unittest_cases(step: dict[str, Any]) -> list[SuiteCase]:
    cases: list[SuiteCase] = []
    for item in list(step.get("cases", []) or []):
        if isinstance(item, str):
            test_id = str(item).strip()
            if test_id:
                cases.append(SuiteCase(test_id=test_id, label=test_id))
            continue
        if not isinstance(item, dict):
            continue
        test_id = str(item.get("test_id") or "").strip()
        if not test_id:
            continue
        label = str(item.get("label") or test_id).strip() or test_id
        cases.append(SuiteCase(test_id=test_id, label=label))
    return cases


def _resolve_step_command(step: dict[str, Any]) -> str:
    command = str(step.get("command") or "").strip()
    if command:
        return command
    executor = str(step.get("executor") or "").strip()
    if executor != "unittest":
        return ""
    cases = _build_unittest_cases(step)
    if not cases:
        return ""
    quiet = bool(step.get("quiet", True))
    failfast = bool(step.get("failfast", False))
    return " ".join(build_unittest_command(cases, quiet=quiet, failfast=failfast))


def _execute_step(step: dict[str, Any], *, root_dir: Path) -> dict[str, Any]:
    executor = str(step.get("executor") or "").strip()
    if executor == "unittest":
        cases = _build_unittest_cases(step)
        if not cases:
            return {
                "returncode": 1,
                "stdout": "",
                "stderr": "workflow unittest step 缺少 cases 配置\n",
                "duration_ms": 0.0,
                "highlights": ["workflow unittest step 缺少 cases 配置"],
            }
        quiet = bool(step.get("quiet", True))
        failfast = bool(step.get("failfast", False))
        started_at = time.perf_counter()
        execution = run_suite_process(cases, quiet=quiet, failfast=failfast)
        duration_ms = round((time.perf_counter() - started_at) * 1000.0, 2)
        combined = "\n".join(part for part in (execution.stdout, execution.stderr) if part)
        return {
            "returncode": execution.returncode,
            "stdout": execution.stdout,
            "stderr": execution.stderr,
            "duration_ms": duration_ms,
            "highlights": extract_highlights(combined),
        }
    return _run_command(str(step.get("command") or "").strip(), root_dir=root_dir)


def _check_backup_requirement(*, task_vars: dict[str, str], root_dir: Path) -> tuple[bool, str, str]:
    raw_backup_dir = str(task_vars.get("backup_dir") or "").strip()
    if not raw_backup_dir:
        return False, "需要先提供 backup_dir，并确认备份目录真实存在。", ""
    backup_dir = _resolve_local_path(root_dir, raw_backup_dir)
    if not backup_dir.exists() or not backup_dir.is_dir():
        return False, f"backup_dir 不存在或不是目录: {backup_dir}", str(backup_dir)
    return True, f"backup_dir={backup_dir}", str(backup_dir)


def _summarize_governance_values(governance: dict[str, Any]) -> str:
    values = governance.get("values", {}) if isinstance(governance.get("values", {}), dict) else {}
    if not values:
        return ""
    parts: list[str] = []
    for key in ("operator", "approver", "ticket"):
        value = str(values.get(key) or "").strip()
        if value:
            parts.append(f"{key}={value}")
    if not parts and str(values.get("change_reason") or "").strip():
        parts.append("change_reason=已填写")
    return " ".join(parts)


def _resolve_workflow_db_paths(*, root_dir: Path, profile: dict[str, Any]) -> dict[str, str]:
    defaults = {
        "local": root_dir / "web" / ".env.local",
        "cloud": root_dir / "web" / ".env.cloud",
    }
    doctor_profile = str(profile.get("doctor_profile") or "auto").strip() or "auto"
    env_file = None
    process_env_file = str(os.environ.get("DEEPVISION_ENV_FILE", "") or "").strip()
    if process_env_file:
        candidate = Path(process_env_file).expanduser()
        env_file = candidate if candidate.is_absolute() else (root_dir / candidate).resolve()
    elif doctor_profile in defaults:
        env_file = defaults[doctor_profile]
    else:
        for profile_name in ("local", "cloud"):
            candidate = defaults[profile_name]
            if candidate.exists():
                env_file = candidate
                break

    _file_values, effective_env = agent_doctor.build_effective_env(env_file, os.environ)
    auth_db = resolve_db_target(effective_env.get("AUTH_DB_PATH", ""), root_dir=root_dir, default_path=root_dir / "data" / "auth" / "users.db")
    license_db = resolve_db_target(
        effective_env.get("LICENSE_DB_PATH", ""),
        root_dir=root_dir,
        default_path=root_dir / "data" / "auth" / "licenses.db",
    )
    return {
        "auth_db": auth_db,
        "license_db": license_db,
        "env_file": str(env_file) if env_file else "",
        "effective_env": dict(effective_env),
    }


def _split_env_list(raw_value: Any) -> list[str]:
    if isinstance(raw_value, (list, tuple, set)):
        return [str(item or "").strip() for item in raw_value if str(item or "").strip()]
    return [token.strip() for token in str(raw_value or "").split(",") if token.strip()]


def _parse_admin_user_ids(raw_value: Any) -> set[int]:
    values: set[int] = set()
    for token in _split_env_list(raw_value):
        try:
            values.add(int(token))
        except Exception:
            continue
    return values


def _parse_admin_phone_numbers(raw_value: Any) -> set[str]:
    return {token for token in _split_env_list(raw_value) if token}


def _count_active_licenses(license_db_path: str, *, bound_user_id: int | None = None) -> int:
    if not db_target_exists(license_db_path):
        return 0
    sql = "SELECT COUNT(1) AS total FROM licenses WHERE status = 'active'"
    params: tuple[Any, ...] = ()
    if bound_user_id is not None and int(bound_user_id) > 0:
        sql += " AND bound_user_id = ?"
        params = (int(bound_user_id),)
    with connect_db(license_db_path) as conn:
        try:
            row = conn.execute(sql, params).fetchone()
        except Exception:
            return 0
    if row is None:
        return 0
    try:
        return int((row["total"] if hasattr(row, "keys") else row[0]) or 0)
    except Exception:
        return 0


def _build_precondition_result(condition: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(condition.get("id") or condition.get("type") or "precondition").strip(),
        "title": str(condition.get("title") or condition.get("id") or condition.get("type") or "precondition").strip(),
        "check_type": str(condition.get("type") or "").strip(),
        "status": "",
        "detail": str(condition.get("detail") or "").strip(),
        "missing_vars": [str(item).strip() for item in list(condition.get("missing_vars", []) or []) if str(item).strip()],
        "highlights": [],
        "resolved": {},
    }


def _evaluate_precondition(
    condition: dict[str, Any],
    *,
    profile: dict[str, Any],
    task_vars: dict[str, str],
    root_dir: Path,
    db_paths: dict[str, str],
) -> dict[str, Any]:
    result = _build_precondition_result(condition)
    if result["missing_vars"]:
        result["status"] = "BLOCKED"
        result["detail"] = "缺少变量: " + ", ".join(result["missing_vars"])
        return result

    check_type = result["check_type"]
    if check_type == "account_exists":
        account = str(condition.get("account") or "").strip()
        auth_db = str(_resolve_local_path(root_dir, condition.get("auth_db") or db_paths.get("auth_db") or "")).strip()
        result["resolved"] = {"account": account, "auth_db": auth_db}
        if not account:
            result["status"] = "BLOCKED"
            result["detail"] = "缺少待检查账号。"
            return result
        if not db_target_exists(auth_db):
            result["status"] = "BLOCKED"
            result["detail"] = f"用户数据库不存在: {auth_db}"
            return result
        try:
            row = admin_ownership_service.query_user_by_account(auth_db, account)
        except Exception as exc:
            result["status"] = "BLOCKED"
            result["detail"] = f"账号检查失败: {exc}"
            return result
        if not row:
            result["status"] = "BLOCKED"
            result["detail"] = f"目标账号不存在: {account}"
            return result
        serialized = admin_ownership_service.serialize_user(row)
        result["status"] = "PASS"
        result["detail"] = f"目标账号存在: id={serialized['id']} account={serialized['account']}"
        result["resolved"]["user"] = serialized
        return result

    if check_type == "user_exists":
        auth_db = str(_resolve_local_path(root_dir, condition.get("auth_db") or db_paths.get("auth_db") or "")).strip()
        user_id_var = str(condition.get("user_id_var") or "").strip()
        account_var = str(condition.get("account_var") or "").strip()
        result["resolved"] = {"auth_db": auth_db, "user_id_var": user_id_var, "account_var": account_var}
        if not db_target_exists(auth_db):
            result["status"] = "BLOCKED"
            result["detail"] = f"用户数据库不存在: {auth_db}"
            return result
        try:
            if user_id_var:
                raw_user_id = str(task_vars.get(user_id_var, "") or "").strip()
                row = admin_ownership_service.query_user_by_id(auth_db, int(raw_user_id))
            elif account_var:
                raw_account = str(task_vars.get(account_var, "") or "").strip()
                row = admin_ownership_service.query_user_by_account(auth_db, raw_account)
            else:
                raise ValueError("user_exists 需要配置 user_id_var 或 account_var")
        except Exception as exc:
            result["status"] = "BLOCKED"
            result["detail"] = f"用户检查失败: {exc}"
            return result
        if not row:
            result["status"] = "BLOCKED"
            if user_id_var:
                result["detail"] = f"目标用户不存在: {task_vars.get(user_id_var, '')}"
            else:
                result["detail"] = f"目标账号不存在: {task_vars.get(account_var, '')}"
            return result
        serialized = admin_ownership_service.serialize_user(row)
        result["status"] = "PASS"
        result["detail"] = f"目标用户存在: id={serialized['id']} account={serialized['account']}"
        result["resolved"]["user"] = serialized
        return result

    if check_type == "active_license_exists":
        license_db = str(_resolve_local_path(root_dir, condition.get("license_db") or db_paths.get("license_db") or "")).strip()
        account_var = str(condition.get("account_var") or "").strip()
        auth_db = str(_resolve_local_path(root_dir, condition.get("auth_db") or db_paths.get("auth_db") or "")).strip()
        bound_user_id = None
        result["resolved"] = {"license_db": license_db, "auth_db": auth_db}
        if account_var:
            account = str(task_vars.get(account_var, "") or "").strip()
            result["resolved"]["account"] = account
            if db_target_exists(auth_db) and account:
                try:
                    user_row = admin_ownership_service.query_user_by_account(auth_db, account)
                except Exception:
                    user_row = None
                if user_row:
                    serialized = admin_ownership_service.serialize_user(user_row)
                    bound_user_id = int(serialized["id"])
                    result["resolved"]["user"] = serialized
        active_count = _count_active_licenses(license_db, bound_user_id=bound_user_id)
        if active_count <= 0:
            result["status"] = "BLOCKED"
            if bound_user_id is not None:
                result["detail"] = f"未找到绑定到目标账号的活跃 License: {task_vars.get(account_var, '')}"
            else:
                result["detail"] = f"未找到活跃 License: {license_db}"
            return result
        result["status"] = "PASS"
        if bound_user_id is not None:
            result["detail"] = f"目标账号存在活跃 License: count={active_count}"
        else:
            result["detail"] = f"环境存在活跃 License: count={active_count}"
        result["resolved"]["active_count"] = active_count
        return result

    if check_type == "requires_admin_session":
        auth_db = str(_resolve_local_path(root_dir, condition.get("auth_db") or db_paths.get("auth_db") or "")).strip()
        effective_env = dict(db_paths.get("effective_env") or {})
        admin_user_ids = _parse_admin_user_ids(effective_env.get("ADMIN_USER_IDS", ""))
        admin_phone_numbers = _parse_admin_phone_numbers(effective_env.get("ADMIN_PHONE_NUMBERS", ""))
        user_id_var = str(condition.get("user_id_var") or "").strip()
        account_var = str(condition.get("account_var") or "").strip()
        result["resolved"] = {
            "auth_db": auth_db,
            "env_file": str(db_paths.get("env_file") or "").strip(),
            "admin_user_ids_count": len(admin_user_ids),
            "admin_phone_numbers_count": len(admin_phone_numbers),
            "user_id_var": user_id_var,
            "account_var": account_var,
        }
        if not admin_user_ids and not admin_phone_numbers:
            result["status"] = "BLOCKED"
            result["detail"] = "当前环境未配置管理员白名单: ADMIN_USER_IDS / ADMIN_PHONE_NUMBERS"
            return result
        if not user_id_var and not account_var:
            result["status"] = "PASS"
            result["detail"] = (
                f"管理员白名单已配置: user_ids={len(admin_user_ids)} "
                f"phones={len(admin_phone_numbers)}"
            )
            return result
        if not db_target_exists(auth_db):
            result["status"] = "BLOCKED"
            result["detail"] = f"用户数据库不存在: {auth_db}"
            return result
        try:
            if user_id_var:
                raw_user_id = str(task_vars.get(user_id_var, "") or "").strip()
                user_row = admin_ownership_service.query_user_by_id(auth_db, int(raw_user_id))
            else:
                raw_account = str(task_vars.get(account_var, "") or "").strip()
                user_row = admin_ownership_service.query_user_by_account(auth_db, raw_account)
        except Exception as exc:
            result["status"] = "BLOCKED"
            result["detail"] = f"管理员身份检查失败: {exc}"
            return result
        if not user_row:
            result["status"] = "BLOCKED"
            if user_id_var:
                result["detail"] = f"管理员用户不存在: {task_vars.get(user_id_var, '')}"
            else:
                result["detail"] = f"管理员账号不存在: {task_vars.get(account_var, '')}"
            return result
        serialized = admin_ownership_service.serialize_user(user_row)
        result["resolved"]["user"] = serialized
        is_admin = int(serialized["id"]) in admin_user_ids or str(serialized.get("phone") or "").strip() in admin_phone_numbers
        if not is_admin:
            result["status"] = "BLOCKED"
            result["detail"] = f"目标账号不在管理员白名单中: {serialized['account']}"
            return result
        result["status"] = "PASS"
        result["detail"] = f"管理员身份已就绪: id={serialized['id']} account={serialized['account']}"
        return result

    if check_type == "requires_browser_env":
        suite_name = str(condition.get("suite") or "minimal").strip() or "minimal"
        dependency_status = agent_browser_smoke._dependency_summary()
        result["resolved"] = {"suite": suite_name, **dependency_status}
        missing: list[str] = []
        if not dependency_status.get("node_available"):
            missing.append("node")
        if not dependency_status.get("npm_available"):
            missing.append("npm")
        if not dependency_status.get("runner_exists"):
            missing.append("browser runner")
        if not dependency_status.get("playwright_package_installed"):
            missing.append("playwright package")
        if missing:
            result["status"] = "BLOCKED"
            result["detail"] = "浏览器环境未就绪: " + ", ".join(missing)
            result["highlights"] = [
                "恢复命令: npm install",
                "如首次执行，继续运行: npx playwright install chromium chromium-headless-shell",
            ]
            return result
        result["status"] = "PASS"
        result["detail"] = (
            f"浏览器环境就绪: suite={suite_name} "
            f"node=yes npm=yes playwright=yes"
        )
        return result

    if check_type == "requires_live_backend":
        suite_name = str(condition.get("suite") or "live").strip() or "live"
        server_path = _resolve_local_path(root_dir, condition.get("server_path") or "web/server.py")
        env_file = str(condition.get("env_file") or db_paths.get("env_file") or "").strip()
        data_dir_var = str(condition.get("data_dir_var") or "").strip()
        require_env_file = bool(condition.get("require_env_file", False))
        result["resolved"] = {
            "suite": suite_name,
            "server_path": str(server_path),
            "env_file": env_file,
            "data_dir_var": data_dir_var,
            "uv_available": bool(shutil.which("uv")),
        }
        missing: list[str] = []
        if not shutil.which("uv"):
            missing.append("uv")
        if not server_path.exists():
            missing.append(f"server:{server_path}")
        if require_env_file:
            if not env_file:
                missing.append("env_file")
            elif not Path(env_file).exists():
                missing.append(f"env_file:{env_file}")
        if data_dir_var:
            raw_data_dir = str(task_vars.get(data_dir_var, "") or "").strip()
            if raw_data_dir:
                data_dir = _resolve_local_path(root_dir, raw_data_dir)
                result["resolved"]["data_dir"] = str(data_dir)
                parent_dir = data_dir if data_dir.exists() else data_dir.parent
                if not parent_dir.exists():
                    missing.append(f"data_dir_parent:{parent_dir}")
        if missing:
            result["status"] = "BLOCKED"
            result["detail"] = "live backend 环境未就绪: " + ", ".join(missing)
            return result
        result["status"] = "PASS"
        result["detail"] = f"live backend 环境就绪: suite={suite_name} server={server_path.name}"
        return result

    if check_type == "path_exists":
        path_text = str(condition.get("path") or "").strip()
        path_kind = str(condition.get("path_kind") or "any").strip()
        resolved_path = _resolve_local_path(root_dir, path_text)
        result["resolved"] = {"path": str(resolved_path), "path_kind": path_kind}
        if not resolved_path.exists():
            result["status"] = "BLOCKED"
            result["detail"] = f"路径不存在: {resolved_path}"
            return result
        if path_kind == "dir" and not resolved_path.is_dir():
            result["status"] = "BLOCKED"
            result["detail"] = f"路径不是目录: {resolved_path}"
            return result
        if path_kind == "file" and not resolved_path.is_file():
            result["status"] = "BLOCKED"
            result["detail"] = f"路径不是文件: {resolved_path}"
            return result
        result["status"] = "PASS"
        result["detail"] = f"路径存在: {resolved_path}"
        return result

    result["status"] = "BLOCKED"
    result["detail"] = f"未知 precondition 类型: {check_type}"
    return result


def run_task_workflow(
    *,
    profile: dict[str, Any],
    task_vars: dict[str, str],
    allow_apply: bool = False,
    execute_mode: str = "plan",
    continue_on_failure: bool = False,
    root_dir: Path = ROOT_DIR,
) -> tuple[dict[str, Any], int]:
    workflow = agent_profiles.render_task_workflow(
        profile,
        task_vars=task_vars,
        allow_apply=allow_apply,
    )
    governance = dict(workflow.get("governance") or {}) if isinstance(workflow.get("governance"), dict) else {}
    normalized_execute_mode = str(execute_mode or "plan").strip() or "plan"
    if normalized_execute_mode not in {"plan", "preview", "full"}:
        raise ValueError(f"未知 workflow execute 模式: {normalized_execute_mode}")

    db_paths = _resolve_workflow_db_paths(root_dir=root_dir, profile=profile)
    precondition_results = [
        _evaluate_precondition(
            condition,
            profile=profile,
            task_vars=task_vars,
            root_dir=root_dir,
            db_paths=db_paths,
        )
        for condition in list(workflow.get("preconditions", []) or [])
        if isinstance(condition, dict)
    ]
    preconditions_blocked = any(str(item.get("status") or "").strip() == "BLOCKED" for item in precondition_results)
    step_results: list[dict[str, Any]] = []
    previous_failed = False

    for index, step in enumerate(list(workflow.get("steps", []) or []), 1):
        step = dict(step)
        step["command"] = _resolve_step_command(step)
        command = str(step.get("command") or "").strip()
        executor = str(step.get("executor") or "").strip() or "command"
        confirmation_token = str(step.get("confirmation_token") or "").strip()
        missing_vars = [str(item).strip() for item in list(step.get("missing_vars", []) or []) if str(item).strip()]
        artifact_specs = _normalize_artifact_specs(step.get("produces_artifact"))
        result: dict[str, Any] = {
            "index": index,
            "id": str(step.get("id") or f"step-{index}").strip(),
            "title": str(step.get("title") or step.get("id") or f"step-{index}").strip(),
            "executor": executor,
            "requires_apply": bool(step.get("requires_apply", False)),
            "requires_backup": bool(step.get("requires_backup", False)),
            "rollback_of": str(step.get("rollback_of") or "").strip(),
            "confirmation_required": bool(confirmation_token),
            "confirmation_token_hint": confirmation_token,
            "missing_vars": missing_vars,
            "command": command,
            "detail": str(step.get("detail") or "").strip(),
            "status": "",
            "executed": False,
            "returncode": 0,
            "duration_ms": 0.0,
            "stdout": "",
            "stderr": "",
            "highlights": [],
            "artifact_paths": [],
            "backup_dir": "",
            "governance_required": False,
            "governance_missing_fields": [],
            "governance_values": {},
        }

        workflow["steps"][index - 1] = step

        if missing_vars:
            result["status"] = "BLOCKED"
            result["detail"] = "缺少变量: " + ", ".join(missing_vars)
            step_results.append(result)
            previous_failed = True
            if not continue_on_failure:
                continue
            continue

        if preconditions_blocked and not continue_on_failure:
            result["status"] = "SKIP"
            result["detail"] = "前置条件未满足，已跳过。"
            step_results.append(result)
            continue

        if previous_failed and not continue_on_failure:
            result["status"] = "SKIP"
            result["detail"] = "前序步骤失败，已跳过。"
            step_results.append(result)
            continue

        if normalized_execute_mode == "plan":
            result["status"] = "PLANNED"
            result["detail"] = command
            step_results.append(result)
            continue

        if normalized_execute_mode == "preview" and bool(step.get("requires_apply", False)):
            result["status"] = "SKIP"
            result["detail"] = "preview 模式跳过高风险 apply/rollback 步骤。"
            step_results.append(result)
            continue

        governance_required = bool(governance.get("required_for_apply", False) and step.get("requires_apply", False))
        governance_missing = [str(item).strip() for item in list(governance.get("missing_fields", []) or []) if str(item).strip()]
        governance_values = dict(governance.get("values") or {}) if isinstance(governance.get("values"), dict) else {}
        result["governance_required"] = governance_required
        result["governance_missing_fields"] = governance_missing
        result["governance_values"] = governance_values
        if governance_required and governance_missing:
            result["status"] = "BLOCKED"
            result["detail"] = "缺少治理字段: " + ", ".join(governance_missing)
            step_results.append(result)
            previous_failed = True
            if not continue_on_failure:
                continue
            continue

        if bool(step.get("requires_backup", False)):
            backup_ready, backup_detail, backup_path = _check_backup_requirement(task_vars=task_vars, root_dir=root_dir)
            result["backup_dir"] = backup_path
            if not backup_ready:
                result["status"] = "BLOCKED"
                result["detail"] = backup_detail
                step_results.append(result)
                previous_failed = True
                if not continue_on_failure:
                    continue
                continue

        if confirmation_token:
            provided_token = str(task_vars.get("confirmation_token") or "").strip()
            if provided_token != confirmation_token:
                result["status"] = "BLOCKED"
                result["detail"] = (
                    "需要确认词: "
                    f"{confirmation_token}。请通过 --task-var confirmation_token={confirmation_token} 显式确认后再执行。"
                )
                step_results.append(result)
                previous_failed = True
                if not continue_on_failure:
                    continue
                continue

        if not command:
            result["status"] = "MANUAL"
            if not result["detail"]:
                result["detail"] = "当前步骤需要人工执行。"
            if confirmation_token:
                result["detail"] += f" 执行前需确认词 {confirmation_token}。"
            if bool(step.get("requires_backup", False)):
                result["detail"] += " 执行前需确认 backup_dir 已准备。"
            if governance_required and governance_values:
                result["detail"] += " 已记录治理字段。"
            step_results.append(result)
            continue

        execution = _execute_step(step, root_dir=root_dir)
        result["executed"] = True
        result["returncode"] = int(execution["returncode"] or 0)
        result["duration_ms"] = float(execution["duration_ms"] or 0.0)
        result["stdout"] = str(execution["stdout"] or "")
        result["stderr"] = str(execution["stderr"] or "")
        result["highlights"] = list(execution.get("highlights", []) or [])
        if result["returncode"] == 0:
            result["status"] = "PASS"
            result["detail"] = f"执行成功，用时 {result['duration_ms']:.2f}ms"
            governance_hint = _summarize_governance_values(governance)
            if governance_required and governance_hint:
                result["detail"] += f" | governance={governance_hint}"
            artifact_paths = [_resolve_local_path(root_dir, item) for item in artifact_specs]
            result["artifact_paths"] = [str(path) for path in artifact_paths]
            if artifact_paths:
                missing_artifacts = [str(path) for path in artifact_paths if not path.exists()]
                if missing_artifacts:
                    result["status"] = "FAIL"
                    result["returncode"] = 3
                    result["detail"] = "执行成功但未产出工件: " + ", ".join(missing_artifacts)
                    result["highlights"].append(result["detail"])
                    previous_failed = True
                else:
                    result["detail"] += f" | artifacts={len(artifact_paths)}"
                    result["highlights"].append("artifact: " + ", ".join(str(path) for path in artifact_paths[:3]))
        else:
            result["status"] = "FAIL"
            result["detail"] = f"执行失败，returncode={result['returncode']} 用时 {result['duration_ms']:.2f}ms"
            previous_failed = True
        step_results.append(result)

    precondition_summary = build_step_summary(precondition_results)
    summary = build_step_summary(precondition_results + step_results)
    overall = determine_overall(
        execute_mode=normalized_execute_mode,
        workflow=workflow,
        precondition_results=precondition_results,
        step_results=step_results,
    )
    payload = {
        "generated_at": utc_now_iso(),
        "root_dir": str(root_dir),
        "task": profile["name"],
        "description": str(profile.get("description") or "").strip(),
        "risk_level": str(profile.get("risk_level") or "medium").strip(),
        "execute_mode": normalized_execute_mode,
        "allow_apply": bool(allow_apply),
        "continue_on_failure": bool(continue_on_failure),
        "workflow": workflow,
        "governance": governance,
        "precondition_results": precondition_results,
        "precondition_summary": precondition_summary,
        "step_results": step_results,
        "summary": summary,
        "overall": overall,
    }
    if overall == "BLOCKED":
        exit_code = 2
    elif overall == "ATTENTION_REQUIRED":
        exit_code = 1
    else:
        exit_code = 0
    return payload, exit_code


def render_text(payload: dict[str, Any]) -> None:
    print("DeepVision agent workflow")
    print(
        f"任务画像: {payload['task']} | risk={payload['risk_level']} | "
        f"execute={payload['execute_mode']} | overall={payload['overall']}"
    )
    governance = payload.get("governance") if isinstance(payload.get("governance"), dict) else {}
    fields = [item for item in list(governance.get("fields", []) or []) if isinstance(item, dict)]
    if fields:
        present = [str(item.get("name") or "").strip() for item in fields if str(item.get("value") or "").strip()]
        missing = [str(item).strip() for item in list(governance.get("missing_fields", []) or []) if str(item).strip()]
        print(
            "治理字段: "
            f"required_for_apply={'yes' if governance.get('required_for_apply') else 'no'} "
            f"present={','.join(present) if present else '-'} "
            f"missing={','.join(missing) if missing else '-'}"
        )
    print("")
    for item in payload.get("precondition_results", []):
        print(f"[{item['status']}] {item['title']}: {item['detail']}")
    if payload.get("precondition_results"):
        print("")
    for item in payload["step_results"]:
        print(f"[{item['status']}] {item['title']}: {item['detail']}")
        if item.get("command"):
            print(f"        command: {item['command']}")
        for line in list(item.get("highlights", []) or [])[:6]:
            print(f"        - {line}")
    hidden_steps = list(((payload.get("workflow") or {}).get("hidden_apply_steps", []) or []))
    if hidden_steps:
        print("")
        print(f"已隐藏 {len(hidden_steps)} 个高风险 apply/rollback 步骤，传 --allow-apply 后可见。")
    print("")
    print(
        "Summary: "
        f"PASS={payload['summary']['PASS']} "
        f"FAIL={payload['summary']['FAIL']} "
        f"BLOCKED={payload['summary']['BLOCKED']} "
        f"MANUAL={payload['summary']['MANUAL']} "
        f"PLANNED={payload['summary']['PLANNED']} "
        f"SKIP={payload['summary']['SKIP']}"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DeepVision agent 任务工作流执行器")
    parser.add_argument("--task", required=True, choices=agent_profiles.list_task_names(), help="选择任务画像")
    parser.add_argument("--task-var", action="append", default=[], help="任务变量，格式 key=value，可重复传入")
    parser.add_argument("--allow-apply", action="store_true", help="显示并允许执行高风险 apply/rollback 步骤")
    parser.add_argument(
        "--execute",
        default="plan",
        choices=["plan", "preview", "full"],
        help="plan 仅渲染步骤，preview 执行安全步骤，full 执行当前可见的全部命令步骤",
    )
    parser.add_argument("--continue-on-failure", action="store_true", help="步骤失败后继续执行后续步骤")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    profile = agent_profiles.get_task_profile(args.task)
    task_vars = agent_profiles.parse_task_vars(args.task_var)
    payload, exit_code = run_task_workflow(
        profile=profile,
        task_vars=task_vars,
        allow_apply=args.allow_apply,
        execute_mode=args.execute,
        continue_on_failure=args.continue_on_failure,
    )
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        render_text(payload)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
