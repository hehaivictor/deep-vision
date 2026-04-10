#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
DeepVision harness 场景 evaluator。

目标：
1. 把高价值回归链路沉淀成可枚举的场景语料库
2. 用统一入口跑 nightly evaluator，输出失败热点、波动场景和耗时摘要
3. 为后续持续吸收线上回归案例预留固定格式
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter
from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from datetime import timezone
from pathlib import Path
import subprocess
from typing import Any


ROOT_DIR = Path(__file__).resolve().parent.parent
SCENARIOS_DIR = ROOT_DIR / "tests" / "harness_scenarios"

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts import agent_artifacts
from scripts import agent_browser_smoke
from scripts import agent_calibration
from scripts import agent_contracts
from scripts import agent_missions
from scripts import agent_plans
from scripts import agent_profiles
from scripts import agent_workflow
from scripts.agent_test_runner import SuiteCase
from scripts.agent_test_runner import SuiteExecution
from scripts.agent_test_runner import run_suite_process


FAILURE_PATTERN = re.compile(r"^(?:FAIL|ERROR): .*?\(([^)]+)\)$", re.MULTILINE)


@dataclass(frozen=True)
class EvalScenario:
    name: str
    category: str
    description: str
    path: str
    tags: tuple[str, ...]
    budgets: dict[str, Any]
    cases: tuple[SuiteCase, ...]
    executor: str = "unittest"
    executor_config: dict[str, Any] = field(default_factory=dict)
    contract: dict[str, Any] | None = None
    mission: dict[str, Any] | None = None
    plan: dict[str, Any] | None = None
    calibration_samples: tuple[dict[str, Any], ...] = ()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def slugify(value: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(value or "").strip()).strip("-._")
    return text or "scenario"


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


def parse_failure_test_ids(
    raw_text: str,
    cases: tuple[SuiteCase, ...],
    *,
    allow_single_case_fallback: bool = False,
) -> list[str]:
    matches = [match.group(1).strip() for match in FAILURE_PATTERN.finditer(str(raw_text or "")) if match.group(1).strip()]
    if matches:
        return matches
    if allow_single_case_fallback and str(raw_text or "").strip() and len(cases) == 1:
        return [cases[0].test_id]
    return []


def normalize_executor_spec(raw_value: Any) -> tuple[str, dict[str, Any]]:
    if isinstance(raw_value, dict):
        executor_type = str(raw_value.get("type") or "unittest").strip() or "unittest"
        return executor_type, dict(raw_value)
    if isinstance(raw_value, str):
        executor_type = str(raw_value or "").strip() or "unittest"
        return executor_type, {"type": executor_type}
    return "unittest", {"type": "unittest"}


def validate_executor_config(
    *,
    executor_type: str,
    executor_config: dict[str, Any],
    path: Path,
    cases: list[SuiteCase],
) -> None:
    if executor_type == "unittest":
        if not cases:
            raise ValueError(f"{path}: unittest 场景必须提供至少一个 cases")
        return
    if executor_type == "browser_smoke":
        suite_name = str(executor_config.get("suite") or "").strip()
        if not suite_name:
            raise ValueError(f"{path}: browser_smoke 场景必须提供 executor.suite")
        return
    if executor_type == "workflow":
        task_name = str(executor_config.get("task") or "").strip()
        if not task_name:
            raise ValueError(f"{path}: workflow 场景必须提供 executor.task")
        return
    if executor_type == "harness":
        args = executor_config.get("args", [])
        if not isinstance(args, list):
            raise ValueError(f"{path}: harness 场景的 executor.args 必须为列表")
        return
    raise ValueError(f"{path}: 不支持的 executor.type={executor_type}")


def scenario_target_summary(scenario: EvalScenario) -> str:
    if scenario.executor == "unittest":
        return f"cases={len(scenario.cases)}"
    if scenario.executor == "browser_smoke":
        return f"suite={str(scenario.executor_config.get('suite') or '').strip() or '-'}"
    if scenario.executor == "workflow":
        task_name = str(scenario.executor_config.get("task") or "").strip() or "-"
        execute_mode = str(scenario.executor_config.get("execute_mode") or "plan").strip() or "plan"
        return f"task={task_name} execute={execute_mode}"
    if scenario.executor == "harness":
        args = [str(item or "").strip() for item in list(scenario.executor_config.get("args", []) or []) if str(item or "").strip()]
        return f"args={len(args)}"
    return scenario.executor


def resolve_allowed_overalls(*, scenario: EvalScenario) -> set[str]:
    raw_value = scenario.executor_config.get("allowed_overalls", None)
    if isinstance(raw_value, list):
        normalized = {str(item or "").strip() for item in raw_value if str(item or "").strip()}
        if normalized:
            return normalized
    if scenario.executor == "browser_smoke":
        return {"READY"}
    if scenario.executor == "workflow":
        return {"READY", "PLANNED"}
    if scenario.executor == "harness":
        return {"READY"}
    return set()


def build_unittest_attempt(
    scenario: EvalScenario,
    *,
    failfast: bool,
) -> dict[str, Any]:
    started_at = time.perf_counter()
    execution: SuiteExecution = run_suite_process(list(scenario.cases), quiet=True, failfast=failfast)
    duration_ms = round((time.perf_counter() - started_at) * 1000.0, 2)
    combined_output = "\n".join(part for part in (execution.stdout, execution.stderr) if part)
    failed_tests = parse_failure_test_ids(
        combined_output,
        scenario.cases,
        allow_single_case_fallback=execution.returncode != 0,
    )
    return {
        "status": "PASS" if execution.returncode == 0 else "FAIL",
        "returncode": execution.returncode,
        "duration_ms": duration_ms,
        "command": execution.command,
        "failed_tests": failed_tests,
        "highlights": extract_highlights(combined_output),
        "stdout": execution.stdout,
        "stderr": execution.stderr,
        "executor_overall": "PASS" if execution.returncode == 0 else "FAIL",
    }


def build_browser_smoke_attempt(scenario: EvalScenario) -> dict[str, Any]:
    suite_name = str(scenario.executor_config.get("suite") or "minimal").strip() or "minimal"
    install_browser = bool(scenario.executor_config.get("install_browser", False))
    started_at = time.perf_counter()
    payload, exit_code = agent_browser_smoke.run_browser_smoke(
        suite_name=suite_name,
        install_browser=install_browser,
    )
    duration_ms = round((time.perf_counter() - started_at) * 1000.0, 2)
    results = [item for item in list(payload.get("results", []) or []) if isinstance(item, dict)]
    highlights: list[str] = []
    failed_subjects: list[str] = []
    for item in results:
        status = str(item.get("status") or "").strip()
        scenario_id = str(item.get("scenario_id") or item.get("label") or "scenario").strip()
        detail = str(item.get("detail") or "").strip()
        if status == "FAIL":
            failed_subjects.append(f"browser_smoke:{scenario_id}")
            if detail:
                highlights.append(f"{scenario_id}: {detail}")
        for line in list(item.get("highlights", []) or [])[:2]:
            text = str(line or "").strip()
            if text:
                highlights.append(text)
        if len(highlights) >= 8:
            break
    overall = str(payload.get("overall") or "").strip()
    allowed_overalls = resolve_allowed_overalls(scenario=scenario)
    passed = exit_code == 0 and (not allowed_overalls or overall in allowed_overalls)
    command = ["python3", "scripts/agent_browser_smoke.py", "--suite", suite_name]
    if install_browser:
        command.append("--install-browser")
    return {
        "status": "PASS" if passed else "FAIL",
        "returncode": 0 if passed else int(exit_code or 2),
        "duration_ms": duration_ms,
        "command": command,
        "failed_tests": failed_subjects,
        "highlights": highlights[:8],
        "stdout": json.dumps(payload, ensure_ascii=False),
        "stderr": "",
        "executor_overall": overall,
    }


def build_workflow_command(scenario: EvalScenario) -> list[str]:
    task_name = str(scenario.executor_config.get("task") or "").strip()
    execute_mode = str(scenario.executor_config.get("execute_mode") or "plan").strip() or "plan"
    command = ["python3", "scripts/agent_workflow.py", "--task", task_name, "--execute", execute_mode]
    for key, value in sorted((scenario.executor_config.get("task_vars", {}) or {}).items()):
        command.extend(["--task-var", f"{key}={value}"])
    if bool(scenario.executor_config.get("allow_apply", False)):
        command.append("--allow-apply")
    if bool(scenario.executor_config.get("continue_on_failure", False)):
        command.append("--continue-on-failure")
    return command


def build_workflow_attempt(scenario: EvalScenario) -> dict[str, Any]:
    task_name = str(scenario.executor_config.get("task") or "").strip()
    task_vars = {
        str(key).strip(): str(value).strip()
        for key, value in dict(scenario.executor_config.get("task_vars", {}) or {}).items()
        if str(key).strip()
    }
    execute_mode = str(scenario.executor_config.get("execute_mode") or "plan").strip() or "plan"
    allow_apply = bool(scenario.executor_config.get("allow_apply", False))
    continue_on_failure = bool(scenario.executor_config.get("continue_on_failure", False))
    profile = agent_profiles.get_task_profile(task_name)

    started_at = time.perf_counter()
    payload, exit_code = agent_workflow.run_task_workflow(
        profile=profile,
        task_vars=task_vars,
        allow_apply=allow_apply,
        execute_mode=execute_mode,
        continue_on_failure=continue_on_failure,
        root_dir=ROOT_DIR,
    )
    duration_ms = round((time.perf_counter() - started_at) * 1000.0, 2)

    failed_subjects: list[str] = []
    highlights: list[str] = []
    for item in list(payload.get("precondition_results", []) or []):
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "").strip()
        title = str(item.get("title") or item.get("id") or "precondition").strip()
        detail = str(item.get("detail") or "").strip()
        if status == "BLOCKED":
            failed_subjects.append(f"workflow:{task_name}:precondition:{str(item.get('id') or title).strip()}")
            if detail:
                highlights.append(f"{title}: {detail}")
    for item in list(payload.get("step_results", []) or []):
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "").strip()
        title = str(item.get("title") or item.get("id") or "step").strip()
        detail = str(item.get("detail") or "").strip()
        if status in {"FAIL", "BLOCKED"}:
            failed_subjects.append(f"workflow:{task_name}:step:{str(item.get('id') or title).strip()}")
            if detail:
                highlights.append(f"{title}: {detail}")
        for line in list(item.get("highlights", []) or [])[:2]:
            text = str(line or "").strip()
            if text:
                highlights.append(text)
        if len(highlights) >= 8:
            break
    overall = str(payload.get("overall") or "").strip()
    allowed_overalls = resolve_allowed_overalls(scenario=scenario)
    passed = exit_code == 0 and (not allowed_overalls or overall in allowed_overalls)
    stdout_payload = {
        "overall": overall,
        "summary": payload.get("summary", {}),
        "precondition_summary": payload.get("precondition_summary", {}),
    }
    if isinstance(payload.get("contract"), dict):
        stdout_payload["contract"] = payload.get("contract")
    if isinstance(payload.get("mission"), dict):
        stdout_payload["mission"] = payload.get("mission")
    if isinstance(payload.get("plan"), dict):
        stdout_payload["plan"] = payload.get("plan")
    return {
        "status": "PASS" if passed else "FAIL",
        "returncode": 0 if passed else int(exit_code or 2),
        "duration_ms": duration_ms,
        "command": build_workflow_command(scenario),
        "failed_tests": failed_subjects,
        "highlights": highlights[:8],
        "stdout": json.dumps(stdout_payload, ensure_ascii=False),
        "stderr": "",
        "executor_overall": overall,
    }


def build_harness_attempt(scenario: EvalScenario) -> dict[str, Any]:
    raw_args = [str(item or "").strip() for item in list(scenario.executor_config.get("args", []) or []) if str(item or "").strip()]
    command = ["python3", "scripts/agent_harness.py", *raw_args]
    if "--json" not in raw_args:
        command.append("--json")
    started_at = time.perf_counter()
    completed = subprocess.run(
        command,
        cwd=str(ROOT_DIR),
        capture_output=True,
        text=True,
        check=False,
    )
    duration_ms = round((time.perf_counter() - started_at) * 1000.0, 2)
    payload: dict[str, Any] = {}
    stdout_text = str(completed.stdout or "").strip()
    if stdout_text:
        try:
            payload = json.loads(stdout_text)
        except json.JSONDecodeError:
            payload = {}
    overall = str(payload.get("overall") or "").strip()
    results = [item for item in list(payload.get("results", []) or []) if isinstance(item, dict)]
    failed_subjects: list[str] = []
    highlights: list[str] = []
    for item in results:
        status = str(item.get("status") or "").strip()
        name = str(item.get("name") or "stage").strip()
        detail = str(item.get("detail") or "").strip()
        if status in {"FAIL", "WARN"}:
            failed_subjects.append(f"harness:{name}")
            if detail:
                highlights.append(f"{name}: {detail}")
        for line in list(item.get("highlights", []) or [])[:2]:
            text = str(line or "").strip()
            if text:
                highlights.append(text)
        if len(highlights) >= 8:
            break
    allowed_overalls = resolve_allowed_overalls(scenario=scenario)
    passed = completed.returncode == 0 and (not allowed_overalls or overall in allowed_overalls)
    return {
        "status": "PASS" if passed else "FAIL",
        "returncode": 0 if passed else int(completed.returncode or 2),
        "duration_ms": duration_ms,
        "command": command,
        "failed_tests": failed_subjects,
        "highlights": highlights[:8],
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "executor_overall": overall,
    }


def execute_scenario_attempt(
    scenario: EvalScenario,
    *,
    failfast: bool,
) -> dict[str, Any]:
    if scenario.executor == "unittest":
        return build_unittest_attempt(scenario, failfast=failfast)
    if scenario.executor == "browser_smoke":
        return build_browser_smoke_attempt(scenario)
    if scenario.executor == "workflow":
        return build_workflow_attempt(scenario)
    if scenario.executor == "harness":
        return build_harness_attempt(scenario)
    raise ValueError(f"不支持的场景执行器: {scenario.executor}")


def load_scenarios(*, scenarios_root: Path = SCENARIOS_DIR) -> list[EvalScenario]:
    scenarios: list[EvalScenario] = []
    for path in sorted(scenarios_root.rglob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            continue
        raw_cases = payload.get("cases", [])
        cases: list[SuiteCase] = []
        if isinstance(raw_cases, list):
            for item in raw_cases:
                if not isinstance(item, dict):
                    continue
                test_id = str(item.get("test_id") or "").strip()
                if not test_id:
                    continue
                label = str(item.get("label") or test_id).strip() or test_id
                cases.append(SuiteCase(test_id=test_id, label=label))
        executor_type, executor_config = normalize_executor_spec(payload.get("executor"))
        validate_executor_config(
            executor_type=executor_type,
            executor_config=executor_config,
            path=path,
            cases=cases,
        )
        task_profile = None
        task_name = str(executor_config.get("task") or "").strip()
        if executor_type == "workflow" and task_name:
            try:
                task_profile = agent_profiles.get_task_profile(task_name)
            except KeyError:
                task_profile = None
        contract_payload = agent_contracts.resolve_contract_reference(
            payload.get("contract", executor_config.get("contract"))
        )
        if contract_payload is None and task_profile is not None:
            contract_payload = agent_contracts.get_contract_for_profile(task_profile)
        mission_payload = agent_missions.get_mission_for_profile(task_profile) if task_profile is not None else None
        plan_payload = agent_plans.get_plan_for_profile(task_profile) if task_profile is not None else None
        raw_tags = payload.get("tags", [])
        tags = tuple(
            sorted(
                {
                    str(item or "").strip()
                    for item in raw_tags
                    if str(item or "").strip()
                }
            )
        ) if isinstance(raw_tags, list) else ()
        budgets = payload.get("budgets", {})
        try:
            scenario_path = str(path.relative_to(ROOT_DIR))
        except Exception:
            scenario_path = str(path)
        scenarios.append(
            EvalScenario(
                name=str(payload.get("name") or path.stem).strip() or path.stem,
                category=str(payload.get("category") or path.parent.name).strip() or path.parent.name,
                description=str(payload.get("description") or "").strip(),
                path=scenario_path,
                tags=tags,
                budgets=budgets if isinstance(budgets, dict) else {},
                cases=tuple(cases),
                executor=executor_type,
                executor_config=executor_config,
                contract=contract_payload,
                mission=mission_payload,
                plan=plan_payload,
                calibration_samples=tuple(
                    agent_calibration.match_calibration_samples(
                        scenario_name=str(payload.get("name") or path.stem).strip() or path.stem,
                        category=str(payload.get("category") or path.parent.name).strip() or path.parent.name,
                        tags=tags,
                        executor=executor_type,
                    )
                ),
            )
        )
    return scenarios


def filter_scenarios(
    scenarios: list[EvalScenario],
    *,
    scenario_names: list[str] | None = None,
    categories: list[str] | None = None,
    tags: list[str] | None = None,
) -> list[EvalScenario]:
    scenario_set = {str(item or "").strip() for item in scenario_names or [] if str(item or "").strip()}
    category_set = {str(item or "").strip() for item in categories or [] if str(item or "").strip()}
    tag_set = {str(item or "").strip() for item in tags or [] if str(item or "").strip()}

    selected: list[EvalScenario] = []
    for scenario in scenarios:
        if scenario_set and scenario.name not in scenario_set:
            continue
        if category_set and scenario.category not in category_set:
            continue
        if tag_set and not tag_set.intersection(set(scenario.tags)):
            continue
        selected.append(scenario)
    return selected


def evaluate_scenario(
    scenario: EvalScenario,
    *,
    repeat: int,
    failfast: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    attempts: list[dict[str, Any]] = []
    failure_counter: Counter[str] = Counter()

    for attempt_index in range(1, max(1, int(repeat or 1)) + 1):
        execution = execute_scenario_attempt(scenario, failfast=failfast)
        failure_counter.update(list(execution.get("failed_tests", []) or []))
        attempts.append({"attempt": attempt_index, "executor": scenario.executor, **execution})

    pass_attempts = sum(1 for item in attempts if item["status"] == "PASS")
    fail_attempts = len(attempts) - pass_attempts
    if fail_attempts <= 0:
        status = "PASS"
    elif pass_attempts <= 0:
        status = "FAIL"
    else:
        status = "FLAKY"

    max_duration_ms = max((float(item["duration_ms"]) for item in attempts), default=0.0)
    avg_duration_ms = round(
        sum(float(item["duration_ms"]) for item in attempts) / max(1, len(attempts)),
        2,
    )
    max_budget_ms = round(float(scenario.budgets.get("max_duration_ms", 0) or 0), 2)
    budget_exceeded = bool(max_budget_ms > 0 and max_duration_ms > max_budget_ms)

    summary = {
        "name": scenario.name,
        "category": scenario.category,
        "description": scenario.description,
        "path": scenario.path,
        "tags": list(scenario.tags),
        "executor": scenario.executor,
        "executor_config": scenario.executor_config,
        "contract": scenario.contract,
        "mission": scenario.mission,
        "plan": scenario.plan,
        "calibration_samples": list(scenario.calibration_samples),
        "target": scenario_target_summary(scenario),
        "status": status,
        "cases": [asdict(case) for case in scenario.cases],
        "stats": {
            "attempts": len(attempts),
            "pass_attempts": pass_attempts,
            "fail_attempts": fail_attempts,
            "avg_duration_ms": avg_duration_ms,
            "max_duration_ms": max_duration_ms,
            "max_duration_budget_ms": max_budget_ms,
            "budget_exceeded": budget_exceeded,
        },
        "failure_hotspots": [
            {"test_id": test_id, "count": count}
            for test_id, count in failure_counter.most_common(5)
        ],
        "highlights": [
            line
            for line in attempts[-1].get("highlights", [])
            if str(line or "").strip()
        ][:6],
    }
    detail = (
        f"attempts={len(attempts)} "
        f"pass={pass_attempts} fail={fail_attempts} "
        f"{scenario_target_summary(scenario)} "
        f"max_ms={max_duration_ms:.2f}"
    )
    if budget_exceeded:
        detail += f" budget_exceeded>{max_budget_ms:.2f}"
    summary["detail"] = detail

    artifact_payload = {
        **summary,
        "attempts": attempts,
        "budgets": scenario.budgets,
    }
    return summary, artifact_payload


def build_summary(results: list[dict[str, Any]]) -> dict[str, int]:
    summary = {"PASS": 0, "FLAKY": 0, "FAIL": 0, "budget_exceeded": 0, "scenarios_total": len(results), "attempts_total": 0}
    for item in results:
        status = str(item.get("status") or "").strip()
        if status in summary:
            summary[status] += 1
        stats = item.get("stats", {}) if isinstance(item.get("stats", {}), dict) else {}
        summary["attempts_total"] += int(stats.get("attempts", 0) or 0)
        if bool(stats.get("budget_exceeded", False)):
            summary["budget_exceeded"] += 1
    return summary


def determine_overall(results: list[dict[str, Any]], summary: dict[str, int]) -> str:
    if not results:
        return "EMPTY"
    if summary.get("FAIL", 0) > 0:
        return "BLOCKED"
    if summary.get("FLAKY", 0) > 0 or summary.get("budget_exceeded", 0) > 0:
        return "DEGRADED"
    return "HEALTHY"


def build_category_summary(results: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    category_summary: dict[str, dict[str, int]] = {}
    for item in results:
        category = str(item.get("category") or "unknown").strip() or "unknown"
        bucket = category_summary.setdefault(
            category,
            {"PASS": 0, "FLAKY": 0, "FAIL": 0, "budget_exceeded": 0, "scenarios": 0},
        )
        bucket["scenarios"] += 1
        status = str(item.get("status") or "").strip()
        if status in {"PASS", "FLAKY", "FAIL"}:
            bucket[status] += 1
        stats = item.get("stats", {}) if isinstance(item.get("stats", {}), dict) else {}
        if bool(stats.get("budget_exceeded", False)):
            bucket["budget_exceeded"] += 1
    return category_summary


def build_failure_hotspots(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    for item in results:
        for hotspot in item.get("failure_hotspots", []) if isinstance(item.get("failure_hotspots", []), list) else []:
            if not isinstance(hotspot, dict):
                continue
            test_id = str(hotspot.get("test_id") or "").strip()
            if not test_id:
                continue
            counter[test_id] += int(hotspot.get("count", 0) or 0)
    return [{"test_id": test_id, "count": count} for test_id, count in counter.most_common(10)]


def build_slowest_scenarios(results: list[dict[str, Any]], *, limit: int = 5) -> list[dict[str, Any]]:
    sortable = []
    for item in results:
        stats = item.get("stats", {}) if isinstance(item.get("stats", {}), dict) else {}
        sortable.append(
            {
                "name": item.get("name"),
                "category": item.get("category"),
                "status": item.get("status"),
                "max_duration_ms": float(stats.get("max_duration_ms", 0) or 0),
                "avg_duration_ms": float(stats.get("avg_duration_ms", 0) or 0),
            }
        )
    sortable.sort(key=lambda item: float(item.get("max_duration_ms", 0) or 0), reverse=True)
    return sortable[:limit]


def write_eval_artifacts(
    *,
    base_dir: str,
    payload: dict[str, Any],
    scenario_artifacts: list[dict[str, Any]],
) -> dict[str, str]:
    base_path, run_name = agent_artifacts.prepare_run_dir(base_dir)
    run_dir = base_path / run_name
    generated_at = utc_now_iso()
    metadata = {
        "generated_at": generated_at,
        "root_dir": str(ROOT_DIR),
        "run_name": run_name,
        "base_dir": str(base_path),
        "run_dir": str(run_dir),
        "git": agent_artifacts.collect_git_context(ROOT_DIR),
    }

    agent_artifacts.write_json_file(run_dir / "run-meta.json", metadata)
    agent_artifacts.write_json_file(run_dir / "summary.json", {**payload, "metadata": metadata})
    progress_content = agent_artifacts.build_eval_progress_markdown(payload, metadata)
    failure_summary_content = agent_artifacts.build_eval_failure_summary_markdown(payload, metadata)
    agent_artifacts.write_text_file(run_dir / "progress.md", progress_content)
    agent_artifacts.write_text_file(run_dir / "failure-summary.md", failure_summary_content)

    for artifact in scenario_artifacts:
        scenario_name = slugify(str(artifact.get("name") or "scenario"))
        attempts = artifact.get("attempts", []) if isinstance(artifact.get("attempts", []), list) else []
        artifact_payload = dict(artifact)
        artifact_payload.pop("attempts", None)
        agent_artifacts.write_json_file(run_dir / f"{scenario_name}.json", artifact_payload)
        for attempt in attempts:
            if not isinstance(attempt, dict):
                continue
            attempt_index = int(attempt.get("attempt", 0) or 0)
            stdout = str(attempt.get("stdout") or "")
            stderr = str(attempt.get("stderr") or "")
            attempt_meta = dict(attempt)
            attempt_meta.pop("stdout", None)
            attempt_meta.pop("stderr", None)
            agent_artifacts.write_json_file(run_dir / f"{scenario_name}.attempt{attempt_index}.json", attempt_meta)
            if stdout:
                agent_artifacts.write_text_file(run_dir / f"{scenario_name}.attempt{attempt_index}.stdout.log", stdout)
            if stderr:
                agent_artifacts.write_text_file(run_dir / f"{scenario_name}.attempt{attempt_index}.stderr.log", stderr)

    handoff_payload = agent_artifacts.build_eval_handoff_payload(
        payload,
        metadata,
        run_dir=run_dir,
        base_path=base_path,
    )
    agent_artifacts.write_json_file(run_dir / "handoff.json", handoff_payload)

    latest_payload = {
        "generated_at": generated_at,
        "run_name": run_name,
        "run_dir": str(run_dir),
        "summary_file": str(run_dir / "summary.json"),
        "progress_file": str(run_dir / "progress.md"),
        "failure_summary_file": str(run_dir / "failure-summary.md"),
        "handoff_file": str(run_dir / "handoff.json"),
        "overall": payload.get("overall", ""),
    }
    agent_artifacts.write_json_file(base_path / "latest.json", latest_payload)
    agent_artifacts.write_text_file(base_path / "latest.txt", str(run_dir))
    agent_artifacts.write_text_file(base_path / "latest-progress.md", progress_content)
    agent_artifacts.write_text_file(base_path / "latest-failure-summary.md", failure_summary_content)
    agent_artifacts.write_json_file(base_path / "latest-handoff.json", handoff_payload)
    return {
        "base_dir": str(base_path),
        "run_dir": str(run_dir),
        "latest_json": str(base_path / "latest.json"),
        "latest_txt": str(base_path / "latest.txt"),
        "progress_file": str(run_dir / "progress.md"),
        "failure_summary_file": str(run_dir / "failure-summary.md"),
        "handoff_file": str(run_dir / "handoff.json"),
        "latest_progress": str(base_path / "latest-progress.md"),
        "latest_failure_summary": str(base_path / "latest-failure-summary.md"),
        "latest_handoff": str(base_path / "latest-handoff.json"),
    }


def run_eval(
    *,
    scenarios_root: Path = SCENARIOS_DIR,
    scenario_names: list[str] | None = None,
    categories: list[str] | None = None,
    tags: list[str] | None = None,
    repeat: int = 1,
    failfast: bool = False,
    artifact_dir: str = "",
) -> tuple[dict[str, Any], dict[str, str] | None, int]:
    loaded = load_scenarios(scenarios_root=scenarios_root)
    selected = filter_scenarios(
        loaded,
        scenario_names=scenario_names,
        categories=categories,
        tags=tags,
    )
    results: list[dict[str, Any]] = []
    scenario_artifacts: list[dict[str, Any]] = []

    for scenario in selected:
        result, artifact_payload = evaluate_scenario(
            scenario,
            repeat=repeat,
            failfast=failfast,
        )
        results.append(result)
        scenario_artifacts.append(artifact_payload)

    summary = build_summary(results)
    overall = determine_overall(results, summary)
    payload = {
        "generated_at": utc_now_iso(),
        "root_dir": str(ROOT_DIR),
        "scenarios_root": str(scenarios_root),
        "filters": {
            "scenario_names": [item for item in scenario_names or [] if str(item or "").strip()],
            "categories": [item for item in categories or [] if str(item or "").strip()],
            "tags": [item for item in tags or [] if str(item or "").strip()],
        },
        "repeat": max(1, int(repeat or 1)),
        "results": results,
        "summary": summary,
        "overall": overall,
        "category_summary": build_category_summary(results),
        "failure_hotspots": build_failure_hotspots(results),
        "slowest_scenarios": build_slowest_scenarios(results),
        "flake_scenarios": [item["name"] for item in results if item.get("status") == "FLAKY"],
        "calibration_matches": sorted(
            {
                str(sample.get("name") or "").strip()
                for item in results
                for sample in list(item.get("calibration_samples", []) or [])
                if isinstance(sample, dict) and str(sample.get("name") or "").strip()
            }
        ),
    }

    artifact_paths = None
    if artifact_dir:
        artifact_paths = write_eval_artifacts(
            base_dir=artifact_dir,
            payload=payload,
            scenario_artifacts=scenario_artifacts,
        )
        payload["artifacts"] = artifact_paths

    if overall == "EMPTY":
        exit_code = 1
    elif overall == "BLOCKED":
        exit_code = 2
    else:
        exit_code = 0
    return payload, artifact_paths, exit_code


def render_text(payload: dict[str, Any]) -> None:
    print("DeepVision harness evaluator")
    print(f"场景目录: {payload['scenarios_root']}")
    print("")
    for item in payload["results"]:
        print(
            f"[{item['status']}] {item['category']}/{item['name']}: "
            f"{item['detail']}"
        )
        calibration_samples = [sample for sample in list(item.get("calibration_samples", []) or []) if isinstance(sample, dict)]
        if calibration_samples:
            print(
                "        calibration: "
                + ", ".join(str(sample.get("name") or "-").strip() for sample in calibration_samples[:3])
            )
    print("")
    print(
        "Summary: "
        f"PASS={payload['summary']['PASS']} "
        f"FLAKY={payload['summary']['FLAKY']} "
        f"FAIL={payload['summary']['FAIL']} "
        f"budget_exceeded={payload['summary']['budget_exceeded']}"
    )
    if payload.get("failure_hotspots"):
        top = payload["failure_hotspots"][0]
        print(f"Top failure hotspot: {top['test_id']} x{top['count']}")
    print(f"Overall: {payload['overall']}")
    if payload.get("artifacts"):
        print(f"Artifacts: {payload['artifacts']['run_dir']}")
        print(f"Progress: {payload['artifacts']['progress_file']}")
        print(f"Failure Summary: {payload['artifacts']['failure_summary_file']}")
        print(f"Handoff: {payload['artifacts']['handoff_file']}")


def list_scenarios(scenarios: list[EvalScenario]) -> int:
    print("DeepVision harness scenarios")
    for index, scenario in enumerate(scenarios, 1):
        print(
            f"{index}. {scenario.category}/{scenario.name} | "
            f"executor={scenario.executor} | {scenario_target_summary(scenario)} | tags={','.join(scenario.tags) or '-'}"
        )
        print(f"   {scenario.description}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DeepVision harness 场景 evaluator")
    parser.add_argument("--scenario-root", default=str(SCENARIOS_DIR), help="场景目录，默认 tests/harness_scenarios")
    parser.add_argument("--scenario", action="append", default=[], help="仅执行指定场景名，可重复传入")
    parser.add_argument("--category", action="append", default=[], help="仅执行指定分类，可重复传入")
    parser.add_argument("--tag", action="append", default=[], help="仅执行包含指定 tag 的场景，可重复传入")
    parser.add_argument("--repeat", type=int, default=1, help="每个场景重复执行次数，用于识别波动")
    parser.add_argument("--failfast", action="store_true", help="单次 unittest 执行遇到首个失败后停止")
    parser.add_argument("--artifact-dir", default="", help="将 evaluator 结果落盘到指定目录")
    parser.add_argument("--list", action="store_true", help="仅列出场景，不执行")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    scenarios_root = Path(str(args.scenario_root or "").strip()).expanduser()
    if not scenarios_root.is_absolute():
        scenarios_root = (ROOT_DIR / scenarios_root).resolve()

    scenarios = load_scenarios(scenarios_root=scenarios_root)
    if args.list:
        filtered = filter_scenarios(
            scenarios,
            scenario_names=args.scenario,
            categories=args.category,
            tags=args.tag,
        )
        return list_scenarios(filtered)

    payload, _artifact_paths, exit_code = run_eval(
        scenarios_root=scenarios_root,
        scenario_names=args.scenario,
        categories=args.category,
        tags=args.tag,
        repeat=max(1, int(args.repeat or 1)),
        failfast=args.failfast,
        artifact_dir=args.artifact_dir,
    )
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        render_text(payload)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
