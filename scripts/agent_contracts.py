#!/usr/bin/env python3
"""
DeepVision harness Sprint Contract 装载器。
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parent.parent
CONTRACTS_DIR = ROOT_DIR / "resources" / "harness" / "contracts"


def _normalize_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT_DIR))
    except ValueError:
        return str(path)


def _normalize_contract_payload(payload: dict[str, Any], *, source_file: str = "") -> dict[str, Any]:
    docs = [
        str(item).strip()
        for item in list(payload.get("docs", []) or [])
        if str(item).strip()
    ]
    done_when = [
        str(item).strip()
        for item in list(payload.get("done_when", []) or [])
        if str(item).strip()
    ]
    hard_failures = [
        str(item).strip()
        for item in list(payload.get("hard_failures", []) or [])
        if str(item).strip()
    ]
    evidence_required = [
        str(item).strip()
        for item in list(payload.get("evidence_required", []) or [])
        if str(item).strip()
    ]
    normalized = {
        "name": str(payload.get("name") or "").strip(),
        "title": str(payload.get("title") or payload.get("name") or "").strip(),
        "task": str(payload.get("task") or payload.get("name") or "").strip(),
        "summary": str(payload.get("summary") or "").strip(),
        "docs": docs,
        "done_when": done_when,
        "hard_failures": hard_failures,
        "evidence_required": evidence_required,
        "source_file": str(source_file or payload.get("source_file") or "").strip(),
    }
    if not normalized["name"]:
        raise ValueError("Sprint Contract 缺少 name")
    if not normalized["task"]:
        normalized["task"] = normalized["name"]
    return normalized


@lru_cache(maxsize=1)
def load_contracts() -> dict[str, dict[str, Any]]:
    contracts: dict[str, dict[str, Any]] = {}
    if not CONTRACTS_DIR.exists():
        return contracts

    for path in sorted(CONTRACTS_DIR.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            continue
        normalized = _normalize_contract_payload(payload, source_file=_normalize_path(path))
        contracts[normalized["name"]] = normalized
    return contracts


def get_contract(name: str) -> dict[str, Any]:
    contracts = load_contracts()
    contract_name = str(name or "").strip()
    if contract_name not in contracts:
        raise KeyError(f"未知 Sprint Contract: {contract_name}")
    return dict(contracts[contract_name])


def resolve_contract_reference(raw_value: Any) -> dict[str, Any] | None:
    if raw_value in (None, "", {}):
        return None
    if isinstance(raw_value, str):
        return get_contract(raw_value)
    if not isinstance(raw_value, dict):
        return None

    payload = dict(raw_value)
    contract_name = str(
        payload.get("name") or payload.get("contract") or payload.get("id") or ""
    ).strip()
    if contract_name:
        try:
            base = get_contract(contract_name)
        except KeyError:
            base = {}
        merged = {**base, **payload}
        source_file = str(merged.get("source_file") or base.get("source_file") or "").strip()
        return _normalize_contract_payload(merged, source_file=source_file)

    return _normalize_contract_payload(payload)


def get_contract_for_profile(profile: dict[str, Any]) -> dict[str, Any] | None:
    contract_ref = profile.get("contract", None)
    return resolve_contract_reference(contract_ref)
