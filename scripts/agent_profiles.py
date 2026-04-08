#!/usr/bin/env python3
"""
DeepVision agent harness 任务画像与高风险 workflow 辅助。
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from string import Formatter
from typing import Any


ROOT_DIR = Path(__file__).resolve().parent.parent
TASKS_DIR = ROOT_DIR / "resources" / "harness" / "tasks"


class _SafeFormatDict(dict):
    def __missing__(self, key: str) -> str:
        return "{" + str(key) + "}"


def _normalize_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT_DIR))
    except ValueError:
        return str(path)


@lru_cache(maxsize=1)
def load_task_profiles() -> dict[str, dict[str, Any]]:
    profiles: dict[str, dict[str, Any]] = {}
    if not TASKS_DIR.exists():
        return profiles

    for path in sorted(TASKS_DIR.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        name = str(payload.get("name") or path.stem).strip()
        if not name:
            continue
        payload["name"] = name
        payload["source_file"] = _normalize_path(path)
        profiles[name] = payload
    return profiles


def list_task_names() -> list[str]:
    return sorted(load_task_profiles().keys())


def get_task_profile(name: str) -> dict[str, Any]:
    profiles = load_task_profiles()
    if name not in profiles:
        raise KeyError(f"未知 harness task: {name}")
    return dict(profiles[name])


def parse_task_vars(items: list[str] | None) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in items or []:
        text = str(item or "").strip()
        if not text:
            continue
        if "=" not in text:
            raise ValueError(f"task 变量格式错误，应为 key=value: {text}")
        key, value = text.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            raise ValueError(f"task 变量 key 不能为空: {text}")
        result[key] = value
    return result


def apply_profile_defaults(args, profile: dict[str, Any], explicit_flags: set[str]) -> None:
    if "--profile" not in explicit_flags and "--profile=" not in explicit_flags:
        doctor_profile = str(profile.get("doctor_profile") or "").strip()
        if doctor_profile:
            args.profile = doctor_profile
    if "--guardrails-suite" not in explicit_flags and "--guardrails-suite=" not in explicit_flags:
        guardrails_suite = str(profile.get("guardrails_suite") or "").strip()
        if guardrails_suite:
            args.guardrails_suite = guardrails_suite
    if "--smoke-suite" not in explicit_flags and "--smoke-suite=" not in explicit_flags:
        smoke_suite = str(profile.get("smoke_suite") or "").strip()
        if smoke_suite:
            args.smoke_suite = smoke_suite
    if "--strict-doctor" not in explicit_flags and bool(profile.get("strict_doctor", False)):
        args.strict_doctor = True


def _extract_template_fields(template: str) -> list[str]:
    fields: list[str] = []
    for _literal, field_name, _format_spec, _conversion in Formatter().parse(str(template or "")):
        if field_name:
            fields.append(field_name)
    return fields


def _render_template_value(value: Any, task_vars: dict[str, str]) -> Any:
    if isinstance(value, str):
        return value.format_map(_SafeFormatDict(task_vars))
    if isinstance(value, list):
        return [_render_template_value(item, task_vars) for item in value]
    return value


def _render_governance(profile: dict[str, Any], *, task_vars: dict[str, str]) -> dict[str, Any]:
    raw_governance = (
        profile.get("workflow", {}).get("governance", {})
        if isinstance(profile.get("workflow", {}), dict)
        else {}
    )
    if not isinstance(raw_governance, dict):
        return {}
    fields: list[dict[str, Any]] = []
    missing_fields: list[str] = []
    for raw_field in list(raw_governance.get("fields", []) or []):
        if not isinstance(raw_field, dict):
            continue
        field_name = str(raw_field.get("name") or "").strip()
        if not field_name:
            continue
        required = bool(raw_field.get("required", True))
        label = str(raw_field.get("label") or field_name).strip() or field_name
        value = str(task_vars.get(field_name, "") or "").strip()
        field_payload = {
            "name": field_name,
            "label": label,
            "required": required,
            "value": value,
        }
        fields.append(field_payload)
        if required and not value:
            missing_fields.append(field_name)
    return {
        "required_for_apply": bool(raw_governance.get("required_for_apply", False)),
        "fields": fields,
        "missing_fields": missing_fields,
        "values": {
            str(item["name"]): str(item["value"])
            for item in fields
            if str(item.get("value") or "").strip()
        },
        "ready": (not missing_fields) if fields else True,
    }


def render_task_workflow(profile: dict[str, Any], *, task_vars: dict[str, str], allow_apply: bool) -> dict[str, Any]:
    steps: list[dict[str, Any]] = []
    preconditions: list[dict[str, Any]] = []
    hidden_apply_steps: list[dict[str, Any]] = []
    missing_vars: list[str] = []

    for raw_condition in list(profile.get("workflow", {}).get("preconditions", []) or []):
        condition = dict(raw_condition)
        template_fields = []
        for field_name in (
            "detail",
            "path",
            "account",
            "auth_db",
            "license_db",
            "env_file",
            "server_path",
            "suite",
            "data_dir_var",
            "user_id_var",
            "account_var",
        ):
            if condition.get(field_name):
                template_fields.extend(_extract_template_fields(str(condition[field_name])))
        required_vars = [str(item).strip() for item in list(condition.get("requires", []) or []) if str(item).strip()]
        for field_name in template_fields:
            if field_name not in required_vars:
                required_vars.append(field_name)

        condition_missing = [name for name in required_vars if not str(task_vars.get(name, "") or "").strip()]
        missing_vars.extend(condition_missing)

        rendered_condition = dict(condition)
        for field_name in (
            "detail",
            "path",
            "account",
            "auth_db",
            "license_db",
            "env_file",
            "server_path",
            "suite",
            "data_dir_var",
            "user_id_var",
            "account_var",
        ):
            if condition.get(field_name):
                rendered_condition[field_name] = str(condition[field_name]).format_map(_SafeFormatDict(task_vars))
        rendered_condition["missing_vars"] = condition_missing
        preconditions.append(rendered_condition)

    for raw_step in list(profile.get("workflow", {}).get("steps", []) or []):
        step = dict(raw_step)
        if bool(step.get("requires_apply")) and not allow_apply:
            hidden_apply_steps.append(step)
            continue

        template_fields = []
        if step.get("command"):
            template_fields.extend(_extract_template_fields(str(step["command"])))
        if step.get("detail"):
            template_fields.extend(_extract_template_fields(str(step["detail"])))
        required_vars = [str(item).strip() for item in list(step.get("requires", []) or []) if str(item).strip()]
        for field_name in template_fields:
            if field_name not in required_vars:
                required_vars.append(field_name)

        step_missing = [name for name in required_vars if not str(task_vars.get(name, "") or "").strip()]
        missing_vars.extend(step_missing)

        rendered = dict(step)
        if step.get("command"):
            rendered["command"] = str(step["command"]).format_map(_SafeFormatDict(task_vars))
        if step.get("detail"):
            rendered["detail"] = str(step["detail"]).format_map(_SafeFormatDict(task_vars))
        if step.get("produces_artifact"):
            rendered["produces_artifact"] = _render_template_value(step.get("produces_artifact"), task_vars)
        rendered["missing_vars"] = step_missing
        steps.append(rendered)

    unique_missing_vars = sorted(set(missing_vars))
    governance = _render_governance(profile, task_vars=task_vars)
    return {
        "task": profile["name"],
        "description": str(profile.get("description") or "").strip(),
        "risk_level": str(profile.get("risk_level") or "medium").strip(),
        "workflow_mode": str(profile.get("workflow", {}).get("mode") or "preview_first").strip(),
        "docs": list(profile.get("docs", []) or []),
        "governance": governance,
        "preconditions": preconditions,
        "steps": steps,
        "hidden_apply_steps": hidden_apply_steps,
        "missing_vars": unique_missing_vars,
        "task_vars": dict(task_vars),
    }
