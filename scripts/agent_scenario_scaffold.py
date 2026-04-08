#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
DeepVision harness 场景脚手架。

目标：
1. 把一次失败的 harness/evaluator 结果更快沉淀为 tests/harness_scenarios 模板
2. 优先复用已有 artifact 与 unittest id，减少手工复制粘贴
3. 默认生成 manual/incident 场景，人工补充背景后再决定是否进入 nightly
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import sys
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parent.parent
HARNESS_ARTIFACTS_DIR = ROOT_DIR / "artifacts" / "harness-runs"
EVAL_ARTIFACTS_DIR = ROOT_DIR / "artifacts" / "harness-eval"
SCENARIOS_DIR = ROOT_DIR / "tests" / "harness_scenarios"

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


FAILURE_PATTERN = re.compile(r"^(?:FAIL|ERROR): .*?\(([^)]+)\)$", re.MULTILINE)

CATEGORY_TAG_HINTS = {
    "browser": ["browser", "ui"],
    "migration": ["migration"],
    "ops": ["ops"],
    "report-solution": ["report"],
    "security": ["security"],
    "tenant": ["tenant"],
    "workflow": ["workflow"],
}

BROWSER_SUITE_BUDGETS = {
    "minimal": 120000,
    "extended": 240000,
    "live-minimal": 180000,
    "live-extended": 360000,
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def slugify(value: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(value or "").strip()).strip("-._")
    return text or "scenario"


def load_json_file(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_file(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_failure_test_ids(raw_text: str) -> list[str]:
    return [
        match.group(1).strip()
        for match in FAILURE_PATTERN.finditer(str(raw_text or ""))
        if match.group(1).strip()
    ]


def normalize_tags(raw_tags: object) -> list[str]:
    if not isinstance(raw_tags, list):
        return []
    return [str(item or "").strip() for item in raw_tags if str(item or "").strip()]


def merge_tags(*groups: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for item in group:
            tag = str(item or "").strip()
            if not tag or tag in seen:
                continue
            seen.add(tag)
            merged.append(tag)
    return merged


def normalize_case_entries(raw_cases: object) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    seen: set[str] = set()
    if not isinstance(raw_cases, list):
        return entries
    for item in raw_cases:
        if not isinstance(item, dict):
            continue
        test_id = str(item.get("test_id") or "").strip()
        if not test_id or test_id in seen:
            continue
        seen.add(test_id)
        entries.append(
            {
                "test_id": test_id,
                "label": str(item.get("label") or test_id).strip() or test_id,
            }
        )
    return entries


def merge_case_entries(*groups: list[dict[str, str]]) -> list[dict[str, str]]:
    merged: list[dict[str, str]] = []
    seen: set[str] = set()
    for group in groups:
        for item in group:
            test_id = str(item.get("test_id") or "").strip()
            if not test_id or test_id in seen:
                continue
            seen.add(test_id)
            merged.append(
                {
                    "test_id": test_id,
                    "label": str(item.get("label") or test_id).strip() or test_id,
                }
            )
    return merged


def derive_output_path(*, category: str, name: str) -> Path:
    return (SCENARIOS_DIR / category / f"{name}.json").resolve()


def to_repo_relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT_DIR))
    except Exception:
        return str(path)


def parse_command_tokens(raw_command: object) -> list[str]:
    text = str(raw_command or "").strip()
    if not text:
        return []
    try:
        return [str(item or "").strip() for item in shlex.split(text) if str(item or "").strip()]
    except ValueError:
        return [text]


def find_command_flag_value(tokens: list[str], flag: str) -> str:
    for index, token in enumerate(tokens):
        if token == flag and index + 1 < len(tokens):
            return str(tokens[index + 1] or "").strip()
        if token.startswith(flag + "="):
            return token.split("=", 1)[1].strip()
    return ""


def infer_budget_from_executor(executor_type: str, executor_config: dict[str, Any]) -> int:
    if executor_type == "browser_smoke":
        suite_name = str(executor_config.get("suite") or "").strip() or "minimal"
        return int(BROWSER_SUITE_BUDGETS.get(suite_name, 240000))
    if executor_type == "workflow":
        return 180000
    if executor_type == "harness":
        return 120000
    return 120000


def parse_manual_cases(values: list[str]) -> list[dict[str, str]]:
    parsed: list[dict[str, str]] = []
    for raw in values:
        text = str(raw or "").strip()
        if not text:
            continue
        if "=" in text:
            test_id, label = text.split("=", 1)
        else:
            test_id, label = text, text
        test_id = test_id.strip()
        if not test_id:
            continue
        parsed.append({"test_id": test_id, "label": label.strip() or test_id})
    return merge_case_entries(parsed)


def load_latest_pointer(base_dir: Path) -> dict[str, Any] | None:
    latest_file = base_dir / "latest.json"
    if not latest_file.exists():
        return None
    try:
        return load_json_file(latest_file)
    except Exception:
        return None


def resolve_source_kind(source: str) -> str:
    normalized = str(source or "latest").strip().lower()
    if normalized in {"latest", "harness", "eval"}:
        return normalized
    raise ValueError(f"未知 source: {source}")


def resolve_latest_source() -> tuple[str, Path]:
    candidates: list[tuple[str, str, Path]] = []
    harness_latest = load_latest_pointer(HARNESS_ARTIFACTS_DIR)
    if harness_latest and str(harness_latest.get("run_dir") or "").strip():
        candidates.append(("harness", str(harness_latest.get("generated_at") or ""), Path(str(harness_latest["run_dir"]))))
    eval_latest = load_latest_pointer(EVAL_ARTIFACTS_DIR)
    if eval_latest and str(eval_latest.get("run_dir") or "").strip():
        candidates.append(("eval", str(eval_latest.get("generated_at") or ""), Path(str(eval_latest["run_dir"]))))
    if not candidates:
        raise FileNotFoundError("未找到 latest.json，可先执行 agent_harness 或 agent_eval 生成 artifact。")
    candidates.sort(key=lambda item: item[1], reverse=True)
    kind, _, run_dir = candidates[0]
    return kind, run_dir


def load_source_snapshot(*, source: str, run_dir: str = "") -> tuple[str, Path, dict[str, Any]]:
    source_kind = resolve_source_kind(source)
    if run_dir:
        resolved_run_dir = Path(str(run_dir)).expanduser()
        if not resolved_run_dir.is_absolute():
            resolved_run_dir = (ROOT_DIR / resolved_run_dir).resolve()
        summary_file = resolved_run_dir / "summary.json"
        if not summary_file.exists():
            raise FileNotFoundError(f"summary.json 不存在: {summary_file}")
        payload = load_json_file(summary_file)
        if source_kind == "latest":
            source_kind = "eval" if "failure_hotspots" in payload or "filters" in payload else "harness"
        return source_kind, resolved_run_dir, payload

    if source_kind == "latest":
        source_kind, resolved_run_dir = resolve_latest_source()
    elif source_kind == "harness":
        latest = load_latest_pointer(HARNESS_ARTIFACTS_DIR)
        if not latest or not str(latest.get("run_dir") or "").strip():
            raise FileNotFoundError("未找到 harness latest.json。")
        resolved_run_dir = Path(str(latest["run_dir"]))
    else:
        latest = load_latest_pointer(EVAL_ARTIFACTS_DIR)
        if not latest or not str(latest.get("run_dir") or "").strip():
            raise FileNotFoundError("未找到 evaluator latest.json。")
        resolved_run_dir = Path(str(latest["run_dir"]))

    return source_kind, resolved_run_dir, load_json_file(resolved_run_dir / "summary.json")


def infer_category_from_cases(cases: list[dict[str, str]]) -> str:
    joined = " ".join(str(item.get("test_id") or "") for item in cases).lower()
    if "security" in joined or "license_gate" in joined or "anonymous_write" in joined:
        return "security"
    if "ownership_migration" in joined or "migration" in joined:
        return "migration"
    if "solution" in joined or "report" in joined or "presentation" in joined:
        return "report-solution"
    if "config" in joined or "observe" in joined or "doctor" in joined or "runtime" in joined or "metrics" in joined:
        return "ops"
    return "ops"


def infer_category_from_task(task_payload: dict[str, Any] | None) -> str:
    task_name = str((task_payload or {}).get("name") or "").strip()
    if task_name == "ownership-migration":
        return "migration"
    if task_name == "report-solution":
        return "report-solution"
    return "ops"


def infer_category_from_executor(executor_type: str, executor_config: dict[str, Any], *, fallback: str = "") -> str:
    if fallback:
        return fallback
    if executor_type == "browser_smoke":
        return "browser"
    if executor_type == "workflow":
        task_name = str(executor_config.get("task") or "").strip()
        if task_name == "report-solution":
            return "workflow"
        if task_name == "ownership-migration":
            return "migration"
        return "ops"
    if executor_type == "harness":
        return "ops"
    return "ops"


def infer_tags(
    *,
    category: str,
    source_kind: str,
    executor_type: str,
    meta: dict[str, Any],
    extra_tags: list[str] | None = None,
) -> list[str]:
    selected_tags = [tag for tag in list(meta.get("selected_tags", []) or []) if tag and tag != "nightly"]
    tags = merge_tags(["incident", "manual"], selected_tags, list(CATEGORY_TAG_HINTS.get(category, [])))
    if executor_type == "browser_smoke":
        tags = merge_tags(tags, ["browser", "ui"])
        suite_name = str((meta.get("executor_config") or {}).get("suite") or "").strip()
        if suite_name.startswith("live-"):
            tags = merge_tags(tags, ["live"])
    elif executor_type == "workflow":
        tags = merge_tags(tags, ["workflow"])
    elif executor_type == "harness":
        tags = merge_tags(tags, ["harness"])
    if source_kind == "eval" and str(meta.get("category") or "").strip() == "tenant":
        tags = merge_tags(tags, ["tenant"])
    return merge_tags(tags, list(extra_tags or []))


def summarize_source(*, source_kind: str, meta: dict[str, Any], source_run_dir: Path) -> str:
    if source_kind == "eval":
        names = [str(item).strip() for item in list(meta.get("selected_names", []) or []) if str(item).strip()]
        executor_type = str(meta.get("executor_type") or "unittest").strip() or "unittest"
        category = str(meta.get("category") or "").strip() or "-"
        target = "、".join(names) if names else source_run_dir.name
        return f"eval:{source_run_dir.name} category={category} target={target} executor={executor_type}"
    stages = [str(item).strip() for item in list(meta.get("stage_names", []) or []) if str(item).strip()]
    task_name = str(meta.get("task_name") or "").strip()
    stage_summary = "/".join(stages) if stages else source_run_dir.name
    if task_name:
        return f"harness:{source_run_dir.name} task={task_name} stages={stage_summary}"
    return f"harness:{source_run_dir.name} stages={stage_summary}"


def build_scaffold_commands(*, source_kind: str, run_dir: Path, context: dict[str, Any]) -> dict[str, str]:
    base_command = [
        "python3",
        "scripts/agent_scenario_scaffold.py",
        "--source",
        source_kind,
        "--run-dir",
        str(run_dir),
        "--name",
        str(context.get("name") or "").strip(),
        "--category",
        str(context.get("category") or "").strip(),
        "--budget-ms",
        str(int(context.get("suggested_budget_ms", 120000) or 120000)),
        "--output",
        str(context.get("suggested_output_path") or "").strip(),
    ]
    for tag in list(context.get("suggested_tags", []) or []):
        base_command.extend(["--tag", str(tag)])
    return {
        "preview": shlex.join([*base_command, "--dry-run"]),
        "write": shlex.join(base_command),
    }


def _extract_eval_executor_meta(selected: list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    if not selected:
        return "unittest", {}
    executor_types = {str(item.get("executor") or "unittest").strip() or "unittest" for item in selected}
    if len(executor_types) != 1:
        return "unittest", {}
    executor_type = executor_types.pop()
    if executor_type == "unittest":
        return executor_type, {}
    configs = [
        dict(item.get("executor_config") or {})
        for item in selected
        if isinstance(item.get("executor_config"), dict)
    ]
    if not configs:
        return executor_type, {"type": executor_type}
    serialized = {json.dumps(config, ensure_ascii=False, sort_keys=True) for config in configs}
    if len(serialized) != 1:
        return executor_type, {"type": executor_type}
    config = dict(configs[0])
    config["type"] = executor_type
    return executor_type, config


def _extract_harness_executor_meta(
    *,
    run_dir: Path,
    stage_names: list[str],
    task_payload: dict[str, Any] | None,
) -> tuple[str, dict[str, Any]]:
    normalized_stage_names = [str(item or "").strip() for item in stage_names if str(item or "").strip()]
    task_name = str((task_payload or {}).get("name") or "").strip()
    if normalized_stage_names == ["workflow"] and task_name:
        workflow_file = run_dir / "workflow.json"
        command_tokens = parse_command_tokens(load_json_file(workflow_file).get("command")) if workflow_file.exists() else []
        execute_mode = find_command_flag_value(command_tokens, "--execute") or "preview"
        executor_config = {
            "type": "workflow",
            "task": task_name,
            "execute_mode": execute_mode,
            "allowed_overalls": ["READY"],
        }
        return "workflow", executor_config
    if normalized_stage_names == ["browser_smoke"]:
        browser_file = run_dir / "browser_smoke.json"
        browser_payload = load_json_file(browser_file) if browser_file.exists() else {}
        suite_name = str(((browser_payload.get("payload") or {}).get("suite") or "minimal")).strip() or "minimal"
        return "browser_smoke", {
            "type": "browser_smoke",
            "suite": suite_name,
            "allowed_overalls": ["READY"],
        }

    args: list[str] = []
    if "doctor" not in normalized_stage_names:
        args.append("--skip-doctor")
    if "observe" in normalized_stage_names:
        args.append("--observe")
        args.extend(["--observe-recent", "3"])
    if "workflow" not in normalized_stage_names:
        args.append("--skip-workflow")
    elif task_name:
        args.extend(["--task", task_name, "--workflow-execute", "preview"])
    if "static_guardrails" not in normalized_stage_names:
        args.append("--skip-static-guardrails")
    if "guardrails" not in normalized_stage_names:
        args.append("--skip-guardrails")
    if "smoke" not in normalized_stage_names:
        args.append("--skip-smoke")
    if "browser_smoke" in normalized_stage_names:
        args.append("--browser-smoke")
        browser_file = run_dir / "browser_smoke.json"
        browser_payload = load_json_file(browser_file) if browser_file.exists() else {}
        suite_name = str(((browser_payload.get("payload") or {}).get("suite") or "minimal")).strip() or "minimal"
        args.extend(["--browser-smoke-suite", suite_name])
    return "harness", {
        "type": "harness",
        "args": args,
        "allowed_overalls": ["READY"],
    }


def extract_cases_from_eval_summary(
    summary_payload: dict[str, Any],
    *,
    scenario_names: list[str] | None = None,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    scenario_set = {str(item or "").strip() for item in scenario_names or [] if str(item or "").strip()}
    results = [item for item in list(summary_payload.get("results", []) or []) if isinstance(item, dict)]
    selected: list[dict[str, Any]] = []
    for item in results:
        if scenario_set and str(item.get("name") or "").strip() not in scenario_set:
            continue
        status = str(item.get("status") or "").strip()
        stats = item.get("stats", {}) if isinstance(item.get("stats", {}), dict) else {}
        if scenario_set or status in {"FAIL", "FLAKY"} or bool(stats.get("budget_exceeded", False)):
            selected.append(item)
    if not selected and results:
        selected = [results[0]]

    cases = merge_case_entries(*[normalize_case_entries(item.get("cases")) for item in selected])
    categories = sorted({str(item.get("category") or "").strip() for item in selected if str(item.get("category") or "").strip()})
    budgets = [
        int(float(((item.get("stats") or {}).get("max_duration_budget_ms", 0) or 0)))
        for item in selected
        if isinstance(item.get("stats", {}), dict)
    ]
    executor_type, executor_config = _extract_eval_executor_meta(selected)
    return cases, {
        "category": infer_category_from_executor(executor_type, executor_config, fallback=categories[0] if len(categories) == 1 else ""),
        "selected_names": [str(item.get("name") or "").strip() for item in selected],
        "budget_ms": max(budgets) if budgets else 0,
        "selected_tags": merge_tags(*[normalize_tags(item.get("tags")) for item in selected]),
        "executor_type": executor_type,
        "executor_config": executor_config,
    }


def extract_cases_from_harness_run(
    run_dir: Path,
    summary_payload: dict[str, Any],
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    results = [item for item in list(summary_payload.get("results", []) or []) if isinstance(item, dict)]
    actionable = [item for item in results if str(item.get("status") or "").strip() == "FAIL"]
    if not actionable:
        actionable = [item for item in results if str(item.get("status") or "").strip() == "WARN"]

    merged_cases: list[dict[str, str]] = []
    stage_names: list[str] = []
    for item in actionable:
        stage_name = str(item.get("name") or "").strip()
        if stage_name:
            stage_names.append(stage_name)
        if stage_name not in {"smoke", "guardrails"}:
            continue
        stage_file = run_dir / f"{stage_name}.json"
        if not stage_file.exists():
            continue
        stage_payload = load_json_file(stage_file)
        stage_cases = normalize_case_entries(stage_payload.get("cases"))
        case_map = {case["test_id"]: case for case in stage_cases}
        stdout_text = (run_dir / f"{stage_name}.stdout.log").read_text(encoding="utf-8") if (run_dir / f"{stage_name}.stdout.log").exists() else ""
        stderr_text = (run_dir / f"{stage_name}.stderr.log").read_text(encoding="utf-8") if (run_dir / f"{stage_name}.stderr.log").exists() else ""
        failed_ids = parse_failure_test_ids("\n".join(part for part in [stdout_text, stderr_text] if part))
        if failed_ids:
            selected_cases = [case_map.get(test_id, {"test_id": test_id, "label": test_id}) for test_id in failed_ids]
        else:
            selected_cases = stage_cases
        merged_cases = merge_case_entries(merged_cases, selected_cases)

    task_payload = summary_payload.get("task") if isinstance(summary_payload.get("task"), dict) else None
    executor_type, executor_config = _extract_harness_executor_meta(
        run_dir=run_dir,
        stage_names=stage_names,
        task_payload=task_payload,
    )
    return merged_cases, {
        "category": infer_category_from_executor(
            executor_type,
            executor_config,
            fallback=infer_category_from_task(task_payload),
        ),
        "task_name": str((task_payload or {}).get("name") or "").strip(),
        "stage_names": stage_names,
        "budget_ms": infer_budget_from_executor(executor_type, executor_config),
        "selected_tags": list(CATEGORY_TAG_HINTS.get(infer_category_from_task(task_payload), [])),
        "executor_type": executor_type,
        "executor_config": executor_config,
    }


def build_default_name(*, source_kind: str, category: str, meta: dict[str, Any]) -> str:
    stamp = datetime.now().strftime("%Y%m%d")
    if source_kind == "eval":
        selected_names = [str(item).strip() for item in list(meta.get("selected_names", []) or []) if str(item).strip()]
        if len(selected_names) == 1:
            return slugify(f"{selected_names[0]}-incident")
    task_name = str(meta.get("task_name") or "").strip()
    if task_name:
        return slugify(f"{task_name}-incident-{stamp}")
    return slugify(f"{category}-incident-{stamp}")


def build_default_description(*, source_kind: str, meta: dict[str, Any], source_run_dir: Path) -> str:
    if source_kind == "eval":
        names = [str(item).strip() for item in list(meta.get("selected_names", []) or []) if str(item).strip()]
        if names:
            return f"基于 evaluator 运行 {source_run_dir.name} 抽取 {'、'.join(names)} 的回归案例，建议补充事故背景后再决定是否纳入 nightly。"
        return f"基于 evaluator 运行 {source_run_dir.name} 自动生成的回归场景，建议补充事故背景后再决定是否纳入 nightly。"
    stages = [str(item).strip() for item in list(meta.get("stage_names", []) or []) if str(item).strip()]
    if stages:
        return f"基于 harness 运行 {source_run_dir.name} 的 {' / '.join(stages)} 结果自动生成，建议补充事故背景和期望边界。"
    return f"基于 harness 运行 {source_run_dir.name} 自动生成的回归场景，建议补充事故背景和期望边界。"


def build_scenario_payload(
    *,
    name: str,
    category: str,
    description: str,
    tags: list[str],
    budget_ms: int,
    cases: list[dict[str, str]],
    executor_type: str,
    executor_config: dict[str, Any],
    source_kind: str,
    source_run_dir: Path,
    meta: dict[str, Any],
) -> dict[str, Any]:
    payload = {
        "name": name,
        "category": category,
        "description": description,
        "tags": sorted({str(item or "").strip() for item in tags if str(item or "").strip()}),
        "budgets": {
            "max_duration_ms": int(max(1000, budget_ms or 120000)),
        },
        "scaffold": {
            "generated_at": utc_now_iso(),
            "source_kind": source_kind,
            "source_run_dir": str(source_run_dir),
            "meta": meta,
        },
    }
    if cases:
        payload["cases"] = cases
    if executor_type and executor_type != "unittest":
        payload["executor"] = {
            **dict(executor_config or {}),
            "type": executor_type,
        }
    return payload


def resolve_output_path(*, category: str, name: str, output: str, force: bool) -> Path:
    if output:
        path = Path(str(output)).expanduser()
        if not path.is_absolute():
            path = (ROOT_DIR / path).resolve()
    else:
        path = derive_output_path(category=category, name=name)
    if path.exists() and not force:
        raise FileExistsError(f"场景文件已存在: {path}")
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="从 harness/evaluator artifact 生成 harness 场景模板")
    parser.add_argument("--source", default="latest", choices=["latest", "harness", "eval"], help="artifact 来源")
    parser.add_argument("--run-dir", default="", help="显式指定 artifact run dir；不传则读取 latest.json")
    parser.add_argument("--scenario", action="append", default=[], help="只对 evaluator 来源生效，指定要抽取的场景名")
    parser.add_argument("--case", action="append", default=[], help="手工追加 unittest，用例格式 test_id 或 test_id=标签")
    parser.add_argument("--name", default="", help="生成场景名，默认自动推断")
    parser.add_argument("--category", default="", help="生成场景分类，默认自动推断")
    parser.add_argument("--description", default="", help="生成场景描述，默认自动生成")
    parser.add_argument("--tag", action="append", default=[], help="追加 tag")
    parser.add_argument("--budget-ms", type=int, default=0, help="显式指定 max_duration_ms")
    parser.add_argument("--output", default="", help="输出文件路径，默认写入 tests/harness_scenarios/<category>/<name>.json")
    parser.add_argument("--dry-run", action="store_true", help="只打印场景 JSON，不落盘")
    parser.add_argument("--force", action="store_true", help="允许覆盖已存在的输出文件")
    return parser


def scaffold_scenario(
    *,
    source: str = "latest",
    run_dir: str = "",
    scenario_names: list[str] | None = None,
    manual_cases: list[dict[str, str]] | None = None,
    name_override: str = "",
    category_override: str = "",
    description_override: str = "",
    extra_tags: list[str] | None = None,
    budget_ms_override: int = 0,
) -> tuple[dict[str, Any], dict[str, Any]]:
    source_kind, resolved_run_dir, summary_payload = load_source_snapshot(source=source, run_dir=run_dir)
    if source_kind == "eval":
        cases, meta = extract_cases_from_eval_summary(summary_payload, scenario_names=scenario_names)
    else:
        cases, meta = extract_cases_from_harness_run(resolved_run_dir, summary_payload)
    merged_cases = merge_case_entries(cases, manual_cases or [])
    executor_type = str(meta.get("executor_type") or "unittest").strip() or "unittest"
    executor_config = dict(meta.get("executor_config") or {})
    if not merged_cases and executor_type == "unittest":
        raise RuntimeError("当前 artifact 未能提取出 unittest 用例；如来源是 browser smoke，请使用 --case 手工补充 test_id。")

    category = str(category_override or meta.get("category") or "").strip()
    if not category:
        category = infer_category_from_executor(executor_type, executor_config)
    if not category and merged_cases:
        category = infer_category_from_cases(merged_cases)
    name = str(name_override or "").strip() or build_default_name(source_kind=source_kind, category=category, meta=meta)
    description = str(description_override or "").strip() or build_default_description(
        source_kind=source_kind,
        meta=meta,
        source_run_dir=resolved_run_dir,
    )
    tags = infer_tags(
        category=category,
        source_kind=source_kind,
        executor_type=executor_type,
        meta=meta,
        extra_tags=list(extra_tags or []),
    )
    suggested_budget_ms = int(budget_ms_override or meta.get("budget_ms") or infer_budget_from_executor(executor_type, executor_config))
    suggested_output_path = to_repo_relative(derive_output_path(category=category, name=name))
    source_summary = summarize_source(source_kind=source_kind, meta=meta, source_run_dir=resolved_run_dir)
    payload = build_scenario_payload(
        name=name,
        category=category,
        description=description,
        tags=tags,
        budget_ms=suggested_budget_ms,
        cases=merged_cases,
        executor_type=executor_type,
        executor_config=executor_config,
        source_kind=source_kind,
        source_run_dir=resolved_run_dir,
        meta=meta,
    )
    context = {
        "source_kind": source_kind,
        "run_dir": str(resolved_run_dir),
        "category": category,
        "name": name,
        "cases_count": len(merged_cases),
        "executor_type": executor_type,
        "suggested_category": category,
        "suggested_tags": tags,
        "suggested_budget_ms": suggested_budget_ms,
        "suggested_output_path": suggested_output_path,
        "source_summary": source_summary,
    }
    context["scaffold_commands"] = build_scaffold_commands(
        source_kind=source_kind,
        run_dir=resolved_run_dir,
        context=context,
    )
    return payload, context


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload, context = scaffold_scenario(
        source=args.source,
        run_dir=args.run_dir,
        scenario_names=args.scenario,
        manual_cases=parse_manual_cases(args.case),
        name_override=args.name,
        category_override=args.category,
        description_override=args.description,
        extra_tags=args.tag,
        budget_ms_override=int(args.budget_ms or 0),
    )
    if args.dry_run:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    output_path = resolve_output_path(
        category=context["category"],
        name=context["name"],
        output=args.output,
        force=args.force,
    )
    write_json_file(output_path, payload)
    print(f"Scaffolded: {output_path}")
    print(f"Source: {context['source_kind']} | run_dir={context['run_dir']}")
    print(f"Cases: {context['cases_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
