#!/usr/bin/env python3
"""
DeepVision evaluator 校准样本装载器。
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parent.parent
CALIBRATION_DIR = ROOT_DIR / "tests" / "harness_calibration"


def _normalize_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT_DIR))
    except ValueError:
        return str(path)


def _normalize_string_list(raw_value: Any) -> list[str]:
    if not isinstance(raw_value, list):
        return []
    return [str(item).strip() for item in raw_value if str(item).strip()]


def _normalize_sample(payload: dict[str, Any], *, source_file: str = "") -> dict[str, Any]:
    applies_to = payload.get("applies_to", {}) if isinstance(payload.get("applies_to", {}), dict) else {}
    return {
        "name": str(payload.get("name") or "").strip(),
        "title": str(payload.get("title") or payload.get("name") or "").strip(),
        "category": str(payload.get("category") or "").strip(),
        "expected_decision": str(payload.get("expected_decision") or "").strip(),
        "rule": str(payload.get("rule") or "").strip(),
        "incident": str(payload.get("incident") or "").strip(),
        "source_file": str(source_file or payload.get("source_file") or "").strip(),
        "source_refs": _normalize_string_list(payload.get("source_refs")),
        "signals": _normalize_string_list(payload.get("signals")),
        "applies_to": {
            "scenarios": _normalize_string_list(applies_to.get("scenarios")),
            "categories": _normalize_string_list(applies_to.get("categories")),
            "tags": _normalize_string_list(applies_to.get("tags")),
            "executors": _normalize_string_list(applies_to.get("executors")),
        },
    }


@lru_cache(maxsize=1)
def load_calibration_samples() -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    if not CALIBRATION_DIR.exists():
        return samples
    for path in sorted(CALIBRATION_DIR.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            continue
        normalized = _normalize_sample(payload, source_file=_normalize_path(path))
        if not normalized["name"]:
            continue
        samples.append(normalized)
    return samples


def match_calibration_samples(
    *,
    scenario_name: str,
    category: str,
    tags: list[str] | tuple[str, ...],
    executor: str,
) -> list[dict[str, Any]]:
    normalized_tags = {str(item).strip() for item in tags if str(item).strip()}
    matched: list[dict[str, Any]] = []
    for sample in load_calibration_samples():
        applies_to = sample.get("applies_to", {}) if isinstance(sample.get("applies_to", {}), dict) else {}
        scenarios = set(_normalize_string_list(applies_to.get("scenarios")))
        categories = set(_normalize_string_list(applies_to.get("categories")))
        sample_tags = set(_normalize_string_list(applies_to.get("tags")))
        executors = set(_normalize_string_list(applies_to.get("executors")))

        # 优先使用更具体的匹配面，避免样本规模扩大后因 category/executor/tag 过宽而互相污染。
        if scenarios:
            if scenario_name in scenarios:
                matched.append(dict(sample))
            continue
        if categories:
            if category in categories:
                matched.append(dict(sample))
            continue
        if executors:
            if executor in executors:
                matched.append(dict(sample))
            continue
        if sample_tags and normalized_tags.intersection(sample_tags):
            matched.append(dict(sample))
    return matched
