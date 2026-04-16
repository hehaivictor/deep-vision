#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
DeepVision agent 单入口检查。

目标：
1. 一次执行完成 doctor、guardrails、smoke 三类检查
2. 输出结构化摘要与失败诊断，减少人工拼装结果
3. 为后续自动化任务或 inbox 集成提供统一入口
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from datetime import timezone
from dataclasses import asdict
from dataclasses import dataclass
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts import agent_doctor
from scripts import agent_browser_smoke
from scripts import agent_guardrails
from scripts import agent_smoke
from scripts import agent_static_guardrails
from scripts import agent_artifacts
from scripts import agent_observe
from scripts import agent_profiles
from scripts import agent_missions
from scripts import agent_plans
from scripts import agent_contracts
from scripts import agent_workflow
from scripts.agent_test_runner import SuiteExecution
from scripts.agent_test_runner import SuiteCase
from scripts.agent_test_runner import run_suite_process


HARNESS_PROFILE_PRESETS = {
    "auto": {"doctor_profile": "auto"},
    "local": {"doctor_profile": "local"},
    "cloud": {"doctor_profile": "cloud"},
    "production": {"doctor_profile": "production"},
    "stability-local-core": {
        "doctor_profile": "auto",
        "observe": True,
        "guardrails_suite": "extended",
        "smoke_suite": "extended",
        "browser_smoke": True,
        "browser_smoke_suite": "extended",
    },
    "stability-local-release": {
        "doctor_profile": "auto",
        "observe": True,
        "guardrails_suite": "extended",
        "smoke_suite": "extended",
        "browser_smoke": True,
        "browser_smoke_suite": "live-minimal",
    },
}


@dataclass
class HarnessStageResult:
    name: str
    status: str
    exit_code: int
    detail: str
    command: str = ""
    highlights: list[str] | None = None
    summary: dict | None = None


@dataclass
class HarnessStageExecution:
    result: HarnessStageResult
    artifact_payload: dict | None = None


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
        or line.startswith("Summary:")
        or line.startswith("Exit code:")
    ]
    selected = focused if focused else lines[-limit:]
    return selected[:limit] if focused else selected


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def run_doctor_stage(*, profile: str, env_file: str, strict_doctor: bool) -> HarnessStageExecution:
    payload, exit_code = agent_doctor.run_doctor(
        profile=profile,
        env_file=env_file,
        strict=strict_doctor,
    )
    summary = payload["summary"]
    results = payload["results"]
    failures = [item for item in results if item["status"] == "FAIL"]
    warnings = [item for item in results if item["status"] == "WARN"]

    if failures:
        status = "FAIL"
        highlights = [f"{item['name']}: {item['detail']}" for item in failures[:6]]
    elif warnings:
        status = "WARN"
        highlights = [f"{item['name']}: {item['detail']}" for item in warnings[:6]]
    else:
        status = "PASS"
        highlights = []

    detail = (
        f"profile={payload['profile']} "
        f"env={payload['selected_env_file'] or 'none'} "
        f"PASS={summary['PASS']} WARN={summary['WARN']} FAIL={summary['FAIL']}"
    )
    command_parts = ["python3", "scripts/agent_doctor.py", "--profile", profile]
    if env_file:
        command_parts.extend(["--env-file", env_file])
    if strict_doctor:
        command_parts.append("--strict-doctor")
    command = " ".join(command_parts)
    result = HarnessStageResult(
        name="doctor",
        status=status,
        exit_code=exit_code,
        detail=detail,
        command=command,
        highlights=highlights,
        summary=payload,
    )
    return HarnessStageExecution(
        result=result,
        artifact_payload={
            "name": "doctor",
            "command": command,
            "exit_code": exit_code,
            "payload": payload,
        },
    )


def run_observe_stage(*, profile: str, env_file: str, recent: int) -> HarnessStageExecution:
    payload, exit_code = agent_observe.run_observe(
        profile=profile,
        env_file=env_file,
        recent=recent,
    )
    summary = payload["summary"]
    if summary.get("FAIL", 0) > 0:
        status = "FAIL"
    elif summary.get("WARN", 0) > 0:
        status = "WARN"
    else:
        status = "PASS"

    highlights: list[str] = []
    item_map = {item["name"]: item for item in list(payload.get("items", []) or []) if isinstance(item, dict)}
    metrics_item = item_map.get("metrics") or {}
    harness_item = item_map.get("harness_runs") or {}
    history_item = item_map.get("history_trends") or {}
    diagnostic_item = item_map.get("diagnostic_panel") or {}
    ownership_item = item_map.get("ownership_history") or {}
    startup_item = item_map.get("startup_snapshot") or {}

    if metrics_item:
        highlights.append(metrics_item.get("detail", ""))
    if ownership_item:
        highlights.append(ownership_item.get("detail", ""))
    if harness_item:
        highlights.append(harness_item.get("detail", ""))
    if history_item:
        highlights.append(history_item.get("detail", ""))
    if diagnostic_item:
        highlights.append(diagnostic_item.get("detail", ""))
    if startup_item:
        highlights.append(startup_item.get("detail", ""))
    highlights = [line for line in highlights if str(line or "").strip()][:6]

    result = HarnessStageResult(
        name="observe",
        status=status,
        exit_code=exit_code if status == "FAIL" else 0,
        detail=f"recent={recent} overall={payload['overall']}",
        command=" ".join(
            ["python3", "scripts/agent_observe.py", "--profile", profile]
            + (["--env-file", env_file] if env_file else [])
            + ["--recent", str(recent)]
        ),
        highlights=highlights,
        summary=payload,
    )
    return HarnessStageExecution(
        result=result,
        artifact_payload={
            "name": "observe",
            "command": result.command,
            "exit_code": exit_code,
            "payload": payload,
        },
    )


def run_suite_stage(
    *,
    stage_name: str,
    suite_name: str,
    resolver,
    description: str,
    failfast: bool,
) -> HarnessStageExecution:
    cases: list[SuiteCase] = resolver(suite_name)
    execution: SuiteExecution = run_suite_process(cases, quiet=True, failfast=failfast)
    status = "PASS" if execution.returncode == 0 else "FAIL"
    combined_output = "\n".join(part for part in (execution.stdout, execution.stderr) if part)
    highlights = extract_highlights(combined_output)
    detail = f"suite={suite_name} cases={len(cases)}"
    result = HarnessStageResult(
        name=stage_name,
        status=status,
        exit_code=0 if execution.returncode == 0 else 2,
        detail=detail,
        command=" ".join(execution.command),
        highlights=highlights,
        summary={
            "suite": suite_name,
            "description": description,
            "cases": [asdict(case) for case in cases],
            "returncode": execution.returncode,
        },
    )
    return HarnessStageExecution(
        result=result,
        artifact_payload={
            "name": stage_name,
            "suite": suite_name,
            "description": description,
            "command": execution.command,
            "returncode": execution.returncode,
            "cases": [asdict(case) for case in cases],
            "stdout": execution.stdout,
            "stderr": execution.stderr,
        },
    )


def run_static_guardrails_stage() -> HarnessStageExecution:
    payload, exit_code = agent_static_guardrails.run_static_guardrails(server_file=ROOT_DIR / "web" / "server.py")
    summary = payload.get("summary", {}) if isinstance(payload.get("summary", {}), dict) else {}
    results = [item for item in list(payload.get("results", []) or []) if isinstance(item, dict)]
    failures = [item for item in results if str(item.get("status") or "").strip() == "FAIL"]
    highlights: list[str] = []
    for item in (failures or results)[:3]:
        name = str(item.get("name") or "").strip()
        detail = str(item.get("detail") or "").strip()
        if detail:
            highlights.append(f"{name}: {detail}")
        for line in list(item.get("highlights", []) or [])[:1]:
            text = str(line or "").strip()
            if text:
                highlights.append(text)
        repair_layer = str(item.get("repair_layer") or "").strip()
        if repair_layer:
            highlights.append(f"{name} 修复层级: {repair_layer}")
        recommended_actions = [str(line or "").strip() for line in list(item.get("recommended_actions", []) or []) if str(line or "").strip()]
        if recommended_actions:
            highlights.append(f"{name} 建议: {recommended_actions[0]}")
        rerun_commands = [str(line or "").strip() for line in list(item.get("rerun_commands", []) or []) if str(line or "").strip()]
        if rerun_commands:
            highlights.append(f"{name} 复跑: {rerun_commands[0]}")
        if len(highlights) >= 6:
            break
    result = HarnessStageResult(
        name="static_guardrails",
        status="PASS" if exit_code == 0 else "FAIL",
        exit_code=exit_code,
        detail=f"rules={int(summary.get('PASS', 0) or 0) + int(summary.get('FAIL', 0) or 0)} fail={int(summary.get('FAIL', 0) or 0)}",
        command="python3 scripts/agent_static_guardrails.py",
        highlights=highlights[:6],
        summary=payload,
    )
    return HarnessStageExecution(
        result=result,
        artifact_payload={
            "name": "static_guardrails",
            "command": result.command,
            "exit_code": exit_code,
            "payload": payload,
        },
    )


def run_browser_smoke_stage(*, suite_name: str, install_browser: bool) -> HarnessStageExecution:
    payload, exit_code = agent_browser_smoke.run_browser_smoke(
        suite_name=suite_name,
        install_browser=install_browser,
    )
    summary = payload.get("summary", {}) if isinstance(payload.get("summary", {}), dict) else {}
    results = [item for item in list(payload.get("results", []) or []) if isinstance(item, dict)]
    failures = [item for item in results if str(item.get("status") or "").strip() == "FAIL"]
    warnings = [item for item in results if str(item.get("status") or "").strip() == "WARN"]
    status = "FAIL" if failures or exit_code != 0 else ("WARN" if warnings else "PASS")
    highlights: list[str] = []
    for item in (failures or warnings or results)[:6]:
        label = str(item.get("label") or item.get("scenario_id") or "").strip()
        detail = str(item.get("detail") or "").strip()
        if label and detail:
            highlights.append(f"{label}: {detail}")
        for line in list(item.get("highlights", []) or [])[:2]:
            text = str(line or "").strip()
            if text:
                highlights.append(text)
        if len(highlights) >= 6:
            break
    command_parts = ["python3", "scripts/agent_browser_smoke.py", "--suite", suite_name]
    if install_browser:
        command_parts.append("--install-browser")
    command = " ".join(command_parts)
    result = HarnessStageResult(
        name="browser_smoke",
        status=status,
        exit_code=exit_code if status == "FAIL" else 0,
        detail=(
            f"suite={suite_name} "
            f"scenarios={int(summary.get('PASS', 0) or 0) + int(summary.get('WARN', 0) or 0) + int(summary.get('FAIL', 0) or 0)} "
            f"fail={int(summary.get('FAIL', 0) or 0)}"
        ),
        command=command,
        highlights=highlights[:6],
        summary=payload,
    )
    return HarnessStageExecution(
        result=result,
        artifact_payload={
            "name": "browser_smoke",
            "command": command,
            "exit_code": exit_code,
            "payload": payload,
        },
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DeepVision agent 单入口检查")
    parser.add_argument(
        "--profile",
        default="local",
        choices=sorted(HARNESS_PROFILE_PRESETS.keys()),
        help="harness 运行画像；基础画像会映射到 doctor 环境，稳定性画像会自动补 observe/browser/extended suites",
    )
    parser.add_argument("--env-file", default="", help="显式指定 doctor 使用的环境文件")
    parser.add_argument("--task", default="", choices=["", *agent_profiles.list_task_names()], help="按任务画像自动选择 doctor / suite / workflow")
    parser.add_argument("--task-var", action="append", default=[], help="为任务画像提供变量，格式 key=value，可重复传入")
    parser.add_argument("--allow-apply", action="store_true", help="在 task workflow 中显示高风险 apply / rollback 步骤")
    parser.add_argument(
        "--workflow-execute",
        default="plan",
        choices=["plan", "preview", "full"],
        help="task workflow 的执行模式；plan 仅预演，preview 执行安全步骤，full 执行当前可见全部命令步骤",
    )
    parser.add_argument("--workflow-continue-on-failure", action="store_true", help="workflow 步骤失败后继续执行后续步骤")
    parser.add_argument("--strict-doctor", action="store_true", help="将 doctor 的 WARN 视为非零退出")
    parser.add_argument("--skip-doctor", action="store_true", help="跳过环境自检阶段")
    parser.add_argument("--observe", action="store_true", help="增加运行态观察阶段")
    parser.add_argument("--observe-recent", type=int, default=5, help="observe 阶段每类最近记录展示条数")
    parser.add_argument("--skip-workflow", action="store_true", help="跳过 task workflow 阶段")
    parser.add_argument("--skip-static-guardrails", action="store_true", help="跳过源码级静态 guardrail 阶段")
    parser.add_argument("--skip-guardrails", action="store_true", help="跳过关键不变量阶段")
    parser.add_argument("--skip-smoke", action="store_true", help="跳过主链路 smoke 阶段")
    parser.add_argument("--browser-smoke", action="store_true", help="增加浏览器级 UI smoke 阶段")
    parser.add_argument(
        "--browser-smoke-suite",
        default="minimal",
        choices=sorted(agent_browser_smoke.SUITES.keys()),
        help="选择 browser smoke 套件",
    )
    parser.add_argument("--browser-smoke-install-browser", action="store_true", help="执行 browser smoke 前显式安装 Chromium")
    parser.add_argument("--guardrails-suite", default="minimal", choices=sorted(agent_guardrails.SUITES.keys()), help="选择 guardrails 套件")
    parser.add_argument("--smoke-suite", default="minimal", choices=sorted(agent_smoke.SUITES.keys()), help="选择 smoke 套件")
    parser.add_argument("--failfast", action="store_true", help="遇到首个失败后停止后续阶段")
    parser.add_argument("--artifact-dir", default="", help="将本次执行摘要和日志落盘到指定目录")
    parser.add_argument("--json", action="store_true", help="输出 JSON 摘要")
    parser.add_argument("--list-stages", action="store_true", help="仅列出默认阶段与套件")
    parser.add_argument("--list-tasks", action="store_true", help="仅列出内置 task 画像，不执行检查")
    return parser


def list_stages(args: argparse.Namespace) -> int:
    doctor_profile = resolve_doctor_profile(args.profile)
    print("DeepVision agent harness stages")
    print(f"1. doctor: profile={doctor_profile}")
    stage_index = 2
    if args.observe:
        print(f"{stage_index}. observe: recent={args.observe_recent}")
        stage_index += 1
    if args.task and not args.skip_workflow:
        print(f"{stage_index}. workflow: task={args.task}")
        stage_index += 1
    if not args.skip_static_guardrails:
        print(f"{stage_index}. static_guardrails")
        stage_index += 1
    if not args.skip_guardrails:
        print(f"{stage_index}. guardrails: suite={args.guardrails_suite}")
        stage_index += 1
    if not args.skip_smoke:
        print(f"{stage_index}. smoke: suite={args.smoke_suite}")
        stage_index += 1
    if args.browser_smoke:
        print(f"{stage_index}. browser_smoke: suite={args.browser_smoke_suite}")
    return 0


def list_tasks() -> int:
    print("DeepVision agent harness tasks")
    for index, name in enumerate(agent_profiles.list_task_names(), 1):
        profile = agent_profiles.get_task_profile(name)
        print(
            f"{index}. {name} | risk={profile.get('risk_level', 'medium')} | "
            f"doctor={profile.get('doctor_profile', 'local')} | "
            f"guardrails={profile.get('guardrails_suite', 'minimal')} | "
            f"smoke={profile.get('smoke_suite', 'minimal')}"
        )
        print(f"   {profile.get('description', '')}")
    return 0


def summarize_results(results: list[HarnessStageResult]) -> dict[str, int]:
    summary = {"PASS": 0, "WARN": 0, "FAIL": 0, "SKIP": 0}
    for item in results:
        summary[item.status] = summary.get(item.status, 0) + 1
    return summary


def determine_overall_status(summary: dict[str, int]) -> str:
    if summary.get("FAIL", 0) > 0:
        return "BLOCKED"
    if summary.get("WARN", 0) > 0:
        return "READY_WITH_WARNINGS"
    return "READY"


def build_output_payload(
    results: list[HarnessStageResult],
    summary: dict[str, int],
    overall: str,
    *,
    duration_ms: float | None = None,
    artifact_paths: dict[str, str] | None = None,
    task_payload: dict | None = None,
) -> dict:
    payload = {
        "generated_at": utc_now_iso(),
        "root_dir": str(ROOT_DIR),
        "results": [asdict(item) for item in results],
        "summary": summary,
        "overall": overall,
    }
    if duration_ms is not None:
        payload["duration_ms"] = round(float(duration_ms), 2)
    if task_payload:
        payload["task"] = task_payload
    if artifact_paths:
        payload["artifacts"] = artifact_paths
    return payload


def render_text_output(
    results: list[HarnessStageResult],
    summary: dict[str, int],
    overall: str,
    *,
    artifact_paths: dict[str, str] | None = None,
    task_payload: dict | None = None,
) -> None:
    print("DeepVision agent harness")
    print(f"仓库目录: {ROOT_DIR}")
    if task_payload:
        print(f"任务画像: {task_payload['name']} | risk={task_payload['risk_level']} | mode={task_payload['workflow_mode']}")
        if isinstance(task_payload.get("mission"), dict):
            print(
                "Mission Contract: "
                f"{str(task_payload['mission'].get('title') or '').strip()} "
                f"| status={str(task_payload['mission'].get('status') or '-').strip() or '-'}"
            )
    print("")
    for item in results:
        print(f"[{item.status}] {item.name}: {item.detail}")
        if item.command:
            print(f"        command: {item.command}")
        for line in item.highlights or []:
            print(f"        - {line}")
    print("")
    print(
        "Summary: "
        f"PASS={summary['PASS']} "
        f"WARN={summary['WARN']} "
        f"FAIL={summary['FAIL']} "
        f"SKIP={summary['SKIP']}"
    )
    print(f"Overall: {overall}")
    if artifact_paths:
        print(f"Artifacts: {artifact_paths['run_dir']}")
        print(f"Latest: {artifact_paths['latest_json']}")
        print(f"Progress: {artifact_paths['progress_file']}")
        print(f"Failure Summary: {artifact_paths['failure_summary_file']}")
        print(f"Handoff: {artifact_paths['handoff_file']}")


def persist_artifacts(
    *,
    artifact_dir: str,
    results: list[HarnessStageResult],
    summary: dict[str, int],
    overall: str,
    duration_ms: float | None,
    executions: list[HarnessStageExecution],
    task_payload: dict | None = None,
) -> dict[str, str]:
    if not artifact_dir:
        return {}
    stage_artifacts = {}
    for item in executions:
        if item.artifact_payload:
            stage_artifacts[item.result.name] = item.artifact_payload
    summary_payload = build_output_payload(
        results,
        summary,
        overall,
        duration_ms=duration_ms,
        task_payload=task_payload,
    )
    return agent_artifacts.write_harness_artifacts(
        base_dir=artifact_dir,
        summary_payload=summary_payload,
        stage_artifacts=stage_artifacts,
        root_dir=ROOT_DIR,
    )


def build_workflow_stage(
    *,
    profile: dict,
    task_vars: dict[str, str],
    allow_apply: bool,
    execute_mode: str,
    continue_on_failure: bool,
) -> HarnessStageExecution:
    workflow_command_parts = ["python3", "scripts/agent_workflow.py", "--task", profile["name"], "--execute", execute_mode]
    for key in sorted(task_vars.keys()):
        workflow_command_parts.extend(["--task-var", f"{key}={task_vars[key]}"])
    if allow_apply:
        workflow_command_parts.append("--allow-apply")
    if continue_on_failure:
        workflow_command_parts.append("--continue-on-failure")
    workflow_command = " ".join(workflow_command_parts)

    workflow_payload, workflow_exit_code = agent_workflow.run_task_workflow(
        profile=profile,
        task_vars=task_vars,
        allow_apply=allow_apply,
        execute_mode=execute_mode,
        continue_on_failure=continue_on_failure,
    )
    workflow = dict(workflow_payload.get("workflow") or {})
    contract = workflow_payload.get("contract") if isinstance(workflow_payload.get("contract"), dict) else None
    mission = workflow_payload.get("mission") if isinstance(workflow_payload.get("mission"), dict) else None
    governance = dict(workflow_payload.get("governance") or {}) if isinstance(workflow_payload.get("governance"), dict) else {}
    precondition_results = [item for item in list(workflow_payload.get("precondition_results", []) or []) if isinstance(item, dict)]
    step_results = [item for item in list(workflow_payload.get("step_results", []) or []) if isinstance(item, dict)]
    highlights: list[str] = []
    if workflow.get("missing_vars"):
        highlights.append("缺少 task 变量: " + ", ".join(list(workflow.get("missing_vars", []) or [])))
    if contract:
        highlights.append(
            "Sprint Contract: "
            f"{str(contract.get('title') or contract.get('name') or '-').strip()} "
            f"source={str(contract.get('source_file') or '-').strip() or '-'}"
        )
    if mission:
        highlights.append(
            "Mission Contract: "
            f"{str(mission.get('title') or mission.get('task') or '-').strip()} "
            f"status={str(mission.get('status') or '-').strip() or '-'}"
        )
    if governance.get("fields"):
        missing_governance = [str(item).strip() for item in list(governance.get("missing_fields", []) or []) if str(item).strip()]
        present_governance = [
            str(item.get("name") or "").strip()
            for item in list(governance.get("fields", []) or [])
            if isinstance(item, dict) and str(item.get("value") or "").strip()
        ]
        highlights.append(
            "治理字段: "
            f"present={','.join(present_governance) if present_governance else '-'} "
            f"missing={','.join(missing_governance) if missing_governance else '-'}"
        )
    for item in precondition_results[:4]:
        highlights.append(f"{item.get('status', '')} {item.get('title', '')}: {str(item.get('detail') or '').strip()}".strip())
    for step_result in step_results[:6]:
        label = f"{step_result.get('status', '')} {step_result.get('title', '')}".strip()
        detail = str(step_result.get("detail") or "").strip()
        if detail:
            highlights.append(f"{label}: {detail}")
        elif step_result.get("command"):
            highlights.append(f"{label}: {step_result['command']}")
    if workflow.get("hidden_apply_steps"):
        highlights.append(f"已隐藏 {len(list(workflow.get('hidden_apply_steps', []) or []))} 个高风险 apply/rollback 步骤，传 --allow-apply 查看。")

    workflow_overall = str(workflow_payload.get("overall") or "").strip()
    if workflow_overall == "BLOCKED":
        status = "FAIL"
    elif workflow_overall == "ATTENTION_REQUIRED" or workflow.get("missing_vars"):
        status = "WARN"
    else:
        status = "PASS"
    detail = (
        f"task={profile['name']} risk={workflow['risk_level']} "
        f"mode={workflow['workflow_mode']} execute={execute_mode} "
        f"preconditions={len(precondition_results)} steps={len(list(workflow.get('steps', []) or []))}"
    )
    if contract:
        detail += f" contract={str(contract.get('name') or '-').strip() or '-'}"
    if governance.get("fields"):
        detail += (
            f" governance={len([item for item in list(governance.get('fields', []) or []) if isinstance(item, dict) and str(item.get('value') or '').strip()])}"
            f"/{len(list(governance.get('fields', []) or []))}"
        )
    if execute_mode != "plan":
        summary = workflow_payload.get("summary", {}) if isinstance(workflow_payload.get("summary", {}), dict) else {}
        detail += (
            f" pass={int(summary.get('PASS', 0) or 0)}"
            f" fail={int(summary.get('FAIL', 0) or 0)}"
            f" blocked={int(summary.get('BLOCKED', 0) or 0)}"
        )
    result = HarnessStageResult(
        name="workflow",
        status=status,
        exit_code=workflow_exit_code if status == "FAIL" else 0,
        detail=detail,
        command=workflow_command,
        highlights=highlights,
        summary=workflow_payload,
    )
    return HarnessStageExecution(
        result=result,
        artifact_payload={
            "name": "workflow",
            "command": workflow_command,
            "profile": profile,
            "workflow": workflow_payload,
        },
    )


def collect_explicit_flags(raw_argv: list[str]) -> set[str]:
    flags: set[str] = set()
    for token in raw_argv:
        text = str(token or "")
        if not text.startswith("--"):
            continue
        if "=" in text:
            flags.add(text.split("=", 1)[0] + "=")
            flags.add(text.split("=", 1)[0])
        else:
            flags.add(text)
    return flags


def resolve_doctor_profile(profile_name: str) -> str:
    preset = HARNESS_PROFILE_PRESETS.get(str(profile_name or "").strip(), {})
    return str(preset.get("doctor_profile") or "local").strip() or "local"


def apply_harness_profile_preset(args: argparse.Namespace, explicit_flags: set[str]) -> str:
    preset = HARNESS_PROFILE_PRESETS.get(str(args.profile or "").strip(), {})
    doctor_profile = str(preset.get("doctor_profile") or "local").strip() or "local"
    if "--observe" not in explicit_flags and "--observe=" not in explicit_flags and "observe" in preset:
        args.observe = bool(preset["observe"])
    if "--guardrails-suite" not in explicit_flags and "--guardrails-suite=" not in explicit_flags and preset.get("guardrails_suite"):
        args.guardrails_suite = str(preset["guardrails_suite"]).strip() or args.guardrails_suite
    if "--smoke-suite" not in explicit_flags and "--smoke-suite=" not in explicit_flags and preset.get("smoke_suite"):
        args.smoke_suite = str(preset["smoke_suite"]).strip() or args.smoke_suite
    if "--browser-smoke" not in explicit_flags and "--browser-smoke=" not in explicit_flags and "browser_smoke" in preset:
        args.browser_smoke = bool(preset["browser_smoke"])
    if "--browser-smoke-suite" not in explicit_flags and "--browser-smoke-suite=" not in explicit_flags and preset.get("browser_smoke_suite"):
        args.browser_smoke_suite = str(preset["browser_smoke_suite"]).strip() or args.browser_smoke_suite
    return doctor_profile


def main(argv: list[str] | None = None) -> int:
    started_at = time.perf_counter()
    raw_argv = list(argv) if argv is not None else sys.argv[1:]
    args = build_parser().parse_args(raw_argv)
    explicit_flags = collect_explicit_flags(raw_argv)
    task_profile = None
    task_vars: dict[str, str] = {}

    if args.task:
        task_profile = agent_profiles.get_task_profile(args.task)
        task_vars = agent_profiles.parse_task_vars(args.task_var)
        agent_profiles.apply_profile_defaults(args, task_profile, explicit_flags)

    doctor_profile = apply_harness_profile_preset(args, explicit_flags)

    if args.list_tasks:
        return list_tasks()
    if args.list_stages:
        return list_stages(args)

    results: list[HarnessStageResult] = []
    executions: list[HarnessStageExecution] = []

    task_payload = None
    if task_profile:
        task_contract = agent_contracts.get_contract_for_profile(task_profile)
        task_mission = agent_missions.get_mission_for_profile(task_profile)
        task_plan = agent_plans.get_plan_for_profile(task_profile)
        task_payload = {
            "name": task_profile["name"],
            "description": task_profile.get("description", ""),
            "risk_level": task_profile.get("risk_level", "medium"),
            "workflow_mode": task_profile.get("workflow", {}).get("mode", "preview_first"),
            "docs": list(task_profile.get("docs", []) or []),
            "task_vars": task_vars,
            "contract": task_contract,
            "mission": task_mission,
            "plan": task_plan,
        }

    def finalize() -> int:
        summary = summarize_results(results)
        overall = determine_overall_status(summary)
        duration_ms = round((time.perf_counter() - started_at) * 1000.0, 2)
        artifact_paths = persist_artifacts(
            artifact_dir=args.artifact_dir,
            results=results,
            summary=summary,
            overall=overall,
            duration_ms=duration_ms,
            executions=executions,
            task_payload=task_payload,
        )
        payload = build_output_payload(
            results,
            summary,
            overall,
            duration_ms=duration_ms,
            artifact_paths=artifact_paths or None,
            task_payload=task_payload,
        )
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            render_text_output(
                results,
                summary,
                overall,
                artifact_paths=artifact_paths or None,
                task_payload=task_payload,
            )
        return 2 if summary["FAIL"] > 0 else 0

    if args.skip_doctor:
        results.append(HarnessStageResult(name="doctor", status="SKIP", exit_code=0, detail="手动跳过"))
    else:
        doctor_execution = run_doctor_stage(
            profile=doctor_profile,
            env_file=args.env_file,
            strict_doctor=args.strict_doctor,
        )
        executions.append(doctor_execution)
        results.append(doctor_execution.result)
        if args.failfast and doctor_execution.result.status == "FAIL":
            return finalize()

    if args.observe:
        observe_execution = run_observe_stage(
            profile=doctor_profile,
            env_file=args.env_file,
            recent=max(1, int(args.observe_recent or 5)),
        )
        executions.append(observe_execution)
        results.append(observe_execution.result)
        if args.failfast and observe_execution.result.status == "FAIL":
            return finalize()

    if task_profile and not args.skip_workflow:
        workflow_execution = build_workflow_stage(
            profile=task_profile,
            task_vars=task_vars,
            allow_apply=args.allow_apply,
            execute_mode=args.workflow_execute,
            continue_on_failure=args.workflow_continue_on_failure,
        )
        executions.append(workflow_execution)
        results.append(workflow_execution.result)
        if args.failfast and workflow_execution.result.status == "FAIL":
            return finalize()

    if args.skip_static_guardrails:
        results.append(HarnessStageResult(name="static_guardrails", status="SKIP", exit_code=0, detail="手动跳过"))
    else:
        static_execution = run_static_guardrails_stage()
        executions.append(static_execution)
        results.append(static_execution.result)
        if args.failfast and static_execution.result.status == "FAIL":
            return finalize()

    if args.skip_guardrails:
        results.append(HarnessStageResult(name="guardrails", status="SKIP", exit_code=0, detail="手动跳过"))
    else:
        guardrails_execution = run_suite_stage(
            stage_name="guardrails",
            suite_name=args.guardrails_suite,
            resolver=agent_guardrails.resolve_suite_cases,
            description=agent_guardrails.SUITES[args.guardrails_suite]["description"],
            failfast=args.failfast,
        )
        executions.append(guardrails_execution)
        results.append(guardrails_execution.result)
        if args.failfast and guardrails_execution.result.status == "FAIL":
            return finalize()

    if args.skip_smoke:
        results.append(HarnessStageResult(name="smoke", status="SKIP", exit_code=0, detail="手动跳过"))
    else:
        smoke_execution = run_suite_stage(
            stage_name="smoke",
            suite_name=args.smoke_suite,
            resolver=agent_smoke.resolve_suite_cases,
            description=agent_smoke.SUITES[args.smoke_suite]["description"],
            failfast=args.failfast,
        )
        executions.append(smoke_execution)
        results.append(smoke_execution.result)

    if args.browser_smoke:
        browser_execution = run_browser_smoke_stage(
            suite_name=args.browser_smoke_suite,
            install_browser=args.browser_smoke_install_browser,
        )
        executions.append(browser_execution)
        results.append(browser_execution.result)

    return finalize()


if __name__ == "__main__":
    raise SystemExit(main())
