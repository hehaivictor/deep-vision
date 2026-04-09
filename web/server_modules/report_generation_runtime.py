import copy
import json
import re
import time as _time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import requests


def configure_report_generation_runtime(bindings: dict[str, Any]) -> None:
    if not isinstance(bindings, dict):
        raise TypeError("bindings must be a dict")
    globals().update(bindings)


def _compute_table_row_readiness_v3(items: list, required_fields: list[str]) -> float:
    """计算列表字段在表格化输出场景中的行完整度。"""
    if not isinstance(items, list) or not items:
        return 0.0

    scores = []
    for item in items:
        if not isinstance(item, dict):
            continue
        filled = 0
        for field in required_fields:
            value = item.get(field, "")
            if field == "evidence_refs":
                if _normalize_evidence_refs(value):
                    filled += 1
            elif str(value or "").strip():
                filled += 1
        scores.append(filled / len(required_fields))

    if not scores:
        return 0.0
    return sum(scores) / len(scores)


def _is_action_metric_measurable_v3(metric_text: str) -> bool:
    text = str(metric_text or "").strip()
    if not text:
        return False

    patterns = [
        r"\d", r"%", r"sla", r"分钟", r"小时", r"天", r"周", r"月", r"季度", r"年",
        r"完成率", r"通过率", r"转化", r"留存", r"时延", r"成本", r"上线", r"缺陷",
        r"coverage", r"latency", r"uptime", r"kpi", r"okr",
    ]
    lowered = text.lower()
    return any(re.search(pattern, lowered, re.IGNORECASE) for pattern in patterns)


def _classify_action_timeline_bucket_v3(timeline_text: str) -> str:
    text = str(timeline_text or "").strip().lower()
    if not text:
        return "unknown"

    short_markers = ["今日", "今天", "本周", "当周", "本月", "立即", "立刻", "短期", "1周", "2周", "一周", "两周", "7天", "14天", "week"]
    mid_markers = ["中期", "一个月", "两个月", "三个月", "1个月", "2个月", "3个月", "季度", "q1", "q2", "q3", "q4", "month"]
    long_markers = ["长期", "半年", "6个月", "一年", "12个月", "年度", "year"]

    if any(marker in text for marker in long_markers):
        return "long"
    if any(marker in text for marker in mid_markers):
        return "mid"
    if any(marker in text for marker in short_markers):
        return "short"
    return "unknown"


def compute_report_quality_meta_v3(draft: dict, evidence_pack: dict, issues: list) -> dict:
    """计算 V3 报告质量元数据。"""
    claim_entries = _collect_claim_entries_for_quality(draft)
    claim_total = len(claim_entries)
    weighted_evidence_score = 0.0
    evidence_covered = 0
    weak_binding_count = 0
    rich_option_count = 0
    pending_follow_up_count = 0
    evidence_covered_by_field = {}
    weak_binding_count_by_field = {}
    answer_evidence_class_index = {}
    for fact in evidence_pack.get("facts", []) if isinstance(evidence_pack.get("facts", []), list) else []:
        if not isinstance(fact, dict):
            continue
        q_id = str(fact.get("q_id", "") or "").upper().strip()
        if not re.fullmatch(r"Q\d+", q_id):
            continue
        answer_evidence_class_index[q_id] = str(fact.get("answer_evidence_class", "") or "").strip().lower() or "explicit"
    weak_binding_weights = {
        "actions": 1.0,
        "solutions": 0.85,
        "risks": 0.55,
    }
    for entry in claim_entries:
        refs = entry.get("evidence_refs", [])
        field = str(entry.get("field", "") or "").strip().lower()
        if not refs:
            continue
        evidence_covered += 1
        evidence_covered_by_field[field] = evidence_covered_by_field.get(field, 0) + 1
        binding_mode = str(entry.get("evidence_binding_mode", "") or "").strip().lower()
        if binding_mode not in {"weak_inferred", "pending_follow_up", "rich_option"}:
            ref_classes = [
                answer_evidence_class_index.get(ref, "")
                for ref in refs
                if answer_evidence_class_index.get(ref, "")
            ]
            if "pending_follow_up" in ref_classes:
                binding_mode = "pending_follow_up"
            elif "weak_inferred" in ref_classes:
                binding_mode = "weak_inferred"
            elif "rich_option" in ref_classes:
                binding_mode = "rich_option"
            else:
                binding_mode = binding_mode or "strong_explicit"
        if binding_mode == "weak_inferred":
            if field in weak_binding_weights:
                weak_binding_count += 1
                weak_binding_count_by_field[field] = weak_binding_count_by_field.get(field, 0) + 1
            weighted_evidence_score += 0.45
        elif binding_mode == "rich_option":
            rich_option_count += 1
            weighted_evidence_score += 0.78
        elif binding_mode == "pending_follow_up":
            pending_follow_up_count += 1
            weighted_evidence_score += 0.0
        else:
            weighted_evidence_score += 1.0
    evidence_coverage = (weighted_evidence_score / claim_total) if claim_total > 0 else 0.0
    weak_binding_ratio_by_field = {}
    weighted_ratio_total = 0.0
    weighted_ratio_weight = 0.0
    for field, weight in weak_binding_weights.items():
        covered_count = int(evidence_covered_by_field.get(field, 0) or 0)
        weak_count = int(weak_binding_count_by_field.get(field, 0) or 0)
        ratio = (weak_count / covered_count) if covered_count > 0 else 0.0
        weak_binding_ratio_by_field[field] = round(ratio, 3)
        if covered_count > 0:
            weighted_ratio_total += ratio * weight
            weighted_ratio_weight += weight
    weak_binding_ratio = (weighted_ratio_total / weighted_ratio_weight) if weighted_ratio_weight > 0 else 0.0

    contradiction_total = len(evidence_pack.get("contradictions", []))
    unresolved_contradictions = len([item for item in issues if item.get("type") == "unresolved_contradiction"])
    if contradiction_total <= 0:
        consistency = 1.0
    else:
        consistency = max(0.0, 1.0 - unresolved_contradictions / contradiction_total)

    action_entries = [entry for entry in claim_entries if entry.get("field") in {"solutions", "actions"}]
    actionable_total = len(action_entries)
    actionable_count = len([
        entry for entry in action_entries
        if entry.get("owner") and entry.get("timeline") and entry.get("metric")
    ])
    actionability = (actionable_count / actionable_total) if actionable_total > 0 else 0.0

    needs = draft.get("needs", []) if isinstance(draft.get("needs", []), list) else []
    solutions = draft.get("solutions", []) if isinstance(draft.get("solutions", []), list) else []
    risks = draft.get("risks", []) if isinstance(draft.get("risks", []), list) else []
    actions = draft.get("actions", []) if isinstance(draft.get("actions", []), list) else []
    open_questions = draft.get("open_questions", []) if isinstance(draft.get("open_questions", []), list) else []
    analysis = draft.get("analysis", {}) if isinstance(draft.get("analysis", {}), dict) else {}

    facts_count = len(evidence_pack.get("facts", [])) if isinstance(evidence_pack.get("facts", []), list) else 0
    blindspot_count = len(evidence_pack.get("blindspots", [])) if isinstance(evidence_pack.get("blindspots", []), list) else 0
    unknown_count = len(evidence_pack.get("unknowns", [])) if isinstance(evidence_pack.get("unknowns", []), list) else 0
    quality_snapshot = evidence_pack.get("quality_snapshot", {}) if isinstance(evidence_pack.get("quality_snapshot", {}), dict) else {}
    avg_quality_score = max(0.0, min(1.0, _safe_float(quality_snapshot.get("average_quality_score", 0.0), default=0.0)))
    unknown_ratio = (unknown_count / facts_count) if facts_count > 0 else 0.0
    action_strategy = _derive_action_generation_strategy_v3(evidence_pack)
    action_minimum = max(1, int(action_strategy.get("min_actions", 2) or 2))

    template_minimums = {
        "needs": 2 if facts_count >= 8 else 1,
        "solutions": 2 if facts_count >= 8 else 1,
        "risks": 1,
        "actions": action_minimum,
        "open_questions": 1 if (blindspot_count > 0 or unknown_count > 0) else 0,
    }
    if unknown_ratio >= 0.65 or avg_quality_score <= 0.30:
        template_minimums["actions"] = min(template_minimums["actions"], 2)
        template_minimums["solutions"] = min(template_minimums["solutions"], 1 if facts_count < 14 else 2)
        if unknown_count > 0:
            template_minimums["open_questions"] = max(template_minimums["open_questions"], 2 if facts_count >= 10 else 1)
    if action_strategy.get("prefer_open_questions") and (blindspot_count > 0 or unknown_count > 0):
        template_minimums["open_questions"] = max(template_minimums["open_questions"], 2 if blindspot_count >= 8 or unknown_ratio >= 0.25 else 1)

    list_counts = {
        "needs": len(needs),
        "solutions": len(solutions),
        "risks": len(risks),
        "actions": len(actions),
        "open_questions": len(open_questions),
    }

    overview_ok = bool(str(draft.get("overview", "") or "").strip())
    analysis_fields = ["customer_needs", "business_flow", "tech_constraints", "project_constraints"]
    analysis_filled = sum(1 for key in analysis_fields if str(analysis.get(key, "") or "").strip())

    expression_checks = [
        overview_ok,
        analysis_filled >= 3,
        list_counts["needs"] >= template_minimums["needs"],
        list_counts["solutions"] >= template_minimums["solutions"],
        list_counts["risks"] >= template_minimums["risks"],
        list_counts["actions"] >= template_minimums["actions"],
    ]
    if template_minimums["open_questions"] > 0:
        expression_checks.append(list_counts["open_questions"] >= template_minimums["open_questions"])
    expression_structure = sum(1 for passed in expression_checks if passed) / len(expression_checks)

    needs_row_readiness = _compute_table_row_readiness_v3(
        needs,
        ["name", "priority", "description", "evidence_refs"],
    )
    solutions_row_readiness = _compute_table_row_readiness_v3(
        solutions,
        ["title", "description", "owner", "timeline", "metric", "evidence_refs"],
    )
    risks_row_readiness = _compute_table_row_readiness_v3(
        risks,
        ["risk", "impact", "mitigation", "evidence_refs"],
    )
    actions_row_readiness = _compute_table_row_readiness_v3(
        actions,
        ["action", "owner", "timeline", "metric", "evidence_refs"],
    )
    table_row_readiness = (
        needs_row_readiness
        + solutions_row_readiness
        + risks_row_readiness
        + actions_row_readiness
    ) / 4.0
    table_presence_score = (
        sum(1 for field in ("needs", "solutions", "risks", "actions") if list_counts.get(field, 0) > 0) / 4.0
    )
    table_readiness = 0.6 * table_row_readiness + 0.4 * table_presence_score

    measurable_actions = 0
    timeline_buckets = set()
    for item in actions:
        if not isinstance(item, dict):
            continue
        metric_text = str(item.get("metric", "") or "").strip()
        owner_text = str(item.get("owner", "") or "").strip()
        timeline_text = str(item.get("timeline", "") or "").strip()
        if owner_text and timeline_text and _is_action_metric_measurable_v3(metric_text):
            measurable_actions += 1
        bucket = _classify_action_timeline_bucket_v3(timeline_text)
        if bucket != "unknown":
            timeline_buckets.add(bucket)

    action_total = len(actions)
    action_acceptance = (measurable_actions / action_total) if action_total > 0 else 0.0
    if action_total <= 0:
        milestone_coverage = 0.0
    elif action_minimum <= 1:
        if len(timeline_buckets) >= 2:
            milestone_coverage = 1.0
        elif len(timeline_buckets) == 1:
            milestone_coverage = 0.68
        else:
            milestone_coverage = 0.28
    elif "short" in timeline_buckets and "mid" in timeline_buckets and action_total >= 3:
        milestone_coverage = 1.0
    elif len(timeline_buckets) >= 2:
        milestone_coverage = 0.78
    elif len(timeline_buckets) == 1:
        milestone_coverage = 0.48 if action_total >= 2 else 0.32
    else:
        milestone_coverage = 0.2 if action_total >= 2 else 0.0

    overall = (
        0.24 * evidence_coverage
        + 0.18 * consistency
        + 0.16 * actionability
        + 0.14 * expression_structure
        + 0.12 * table_readiness
        + 0.08 * action_acceptance
        + 0.08 * milestone_coverage
    )

    return {
        "mode": "v3_structured_reviewed",
        "evidence_coverage": round(evidence_coverage, 3),
        "consistency": round(consistency, 3),
        "actionability": round(actionability, 3),
        "expression_structure": round(expression_structure, 3),
        "table_readiness": round(table_readiness, 3),
        "action_acceptance": round(action_acceptance, 3),
        "milestone_coverage": round(milestone_coverage, 3),
        "overall": round(overall, 3),
        "claim_total": claim_total,
        "claim_with_evidence": evidence_covered,
        "weak_binding_count": weak_binding_count,
        "rich_option_count": rich_option_count,
        "pending_follow_up_count": pending_follow_up_count,
        "weak_binding_ratio": round(weak_binding_ratio, 3),
        "rich_option_ratio": round((rich_option_count / claim_total), 3) if claim_total > 0 else 0.0,
        "pending_follow_up_ratio": round((pending_follow_up_count / claim_total), 3) if claim_total > 0 else 0.0,
        "weak_binding_count_by_field": weak_binding_count_by_field,
        "weak_binding_ratio_by_field": weak_binding_ratio_by_field,
        "evidence_covered_by_field": evidence_covered_by_field,
        "analysis_section_filled": analysis_filled,
        "list_counts": list_counts,
        "template_minimums": template_minimums,
        "table_row_readiness": {
            "needs": round(needs_row_readiness, 3),
            "solutions": round(solutions_row_readiness, 3),
            "risks": round(risks_row_readiness, 3),
            "actions": round(actions_row_readiness, 3),
        },
        "evidence_context": {
            "facts_count": facts_count,
            "unknown_count": unknown_count,
            "blindspots_count": blindspot_count,
            "unknown_ratio": round(unknown_ratio, 3),
            "average_quality_score": round(avg_quality_score, 3),
            "action_generation_strategy": {
                "min_actions": action_minimum,
                "prefer_open_questions": bool(action_strategy.get("prefer_open_questions")),
                "low_signal_pressure": bool(action_strategy.get("low_signal_pressure")),
                "timeline_expectation": str(action_strategy.get("timeline_expectation", "short_and_mid") or "short_and_mid"),
            },
        },
        "timeline_buckets": sorted(timeline_buckets),
        "measurable_actions": measurable_actions,
        "review_issue_count": len(issues),
    }


def build_report_quality_meta_fallback(session: dict, mode: str, evidence_pack: Optional[dict] = None) -> dict:
    """回退流程的质量元数据估算。"""
    effective_evidence_pack = evidence_pack if isinstance(evidence_pack, dict) and evidence_pack else build_report_evidence_pack(session)
    evidence_coverage = float(effective_evidence_pack.get("overall_coverage", 0.0))
    contradiction_total = len(effective_evidence_pack.get("contradictions", []))
    consistency = 1.0 if contradiction_total == 0 else 0.6
    actionability = 0.4
    expression_structure = 0.55
    table_readiness = 0.5
    action_acceptance = 0.45
    milestone_coverage = 0.4
    overall = (
        0.24 * evidence_coverage
        + 0.18 * consistency
        + 0.16 * actionability
        + 0.14 * expression_structure
        + 0.12 * table_readiness
        + 0.08 * action_acceptance
        + 0.08 * milestone_coverage
    )

    return {
        "mode": mode,
        "evidence_coverage": round(evidence_coverage, 3),
        "consistency": round(consistency, 3),
        "actionability": round(actionability, 3),
        "expression_structure": round(expression_structure, 3),
        "table_readiness": round(table_readiness, 3),
        "action_acceptance": round(action_acceptance, 3),
        "milestone_coverage": round(milestone_coverage, 3),
        "overall": round(overall, 3),
        "claim_total": 0,
        "claim_with_evidence": 0,
        "weak_binding_count": 0,
        "weak_binding_ratio": 0.0,
        "analysis_section_filled": 0,
        "list_counts": {},
        "template_minimums": {},
        "table_row_readiness": {},
        "evidence_context": {
            "facts_count": len(effective_evidence_pack.get("facts", [])) if isinstance(effective_evidence_pack.get("facts", []), list) else 0,
            "unknown_count": len(effective_evidence_pack.get("unknowns", [])) if isinstance(effective_evidence_pack.get("unknowns", []), list) else 0,
            "blindspots_count": len(effective_evidence_pack.get("blindspots", [])) if isinstance(effective_evidence_pack.get("blindspots", []), list) else 0,
            "unknown_ratio": 0.0,
            "average_quality_score": 0.0,
        },
        "timeline_buckets": [],
        "measurable_actions": 0,
        "review_issue_count": 0,
    }


def generate_report_v3_pipeline(
    session: dict,
    session_id: Optional[str] = None,
    preferred_lane: str = "",
    call_type_suffix: str = "",
    report_profile: str = "",
    ) -> Optional[dict]:
    """执行 V3 报告生成流水线。失败时返回包含 reason 的调试结构。"""
    pipeline_timings = {
        "evidence_pack_ms": 0.0,
        "draft_gen_ms": 0.0,
        "review_ms": 0.0,
    }
    runtime_profile = normalize_report_profile_choice(report_profile, fallback=REPORT_V3_PROFILE)
    pipeline_lane = str(preferred_lane or "report").strip().lower() or "report"
    phase_lanes = {
        "draft": resolve_report_v3_phase_lane("draft", pipeline_lane=pipeline_lane),
        "review": resolve_report_v3_phase_lane("review", pipeline_lane=pipeline_lane),
    }
    evidence_pack: dict = {}
    current_draft: dict = {}
    exception_stage = "setup"
    exception_context: dict = {
        "profile": runtime_profile,
        "preferred_lane": pipeline_lane,
        "session_id": str(session_id or ""),
    }

    def _set_exception_stage(stage: str, **context) -> None:
        nonlocal exception_stage, exception_context
        exception_stage = str(stage or "setup").strip() or "setup"
        normalized_context = {}
        for key, value in context.items():
            if value is None:
                continue
            if isinstance(value, float):
                normalized_context[key] = round(value, 4)
            else:
                normalized_context[key] = value
        exception_context = normalized_context

    try:
        runtime_cfg = get_report_v3_runtime_config(report_profile)
        runtime_profile = runtime_cfg["profile"]
        _set_exception_stage("setup", profile=runtime_profile, preferred_lane=pipeline_lane, session_id=str(session_id or ""))
        if runtime_profile == "quality" and bool(runtime_cfg.get("quality_force_single_lane", True)):
            preferred_quality_lane = str(runtime_cfg.get("quality_primary_lane", "report") or "report").strip().lower()
            if preferred_quality_lane not in {"question", "report"}:
                preferred_quality_lane = "report"
            forced_lane = pipeline_lane if pipeline_lane != "report" else preferred_quality_lane
            draft_phase_lane = forced_lane
            review_phase_lane = forced_lane
        else:
            draft_phase_lane = resolve_report_v3_phase_lane("draft", pipeline_lane=pipeline_lane)
            review_phase_lane = resolve_report_v3_phase_lane("review", pipeline_lane=pipeline_lane)
        phase_lanes = {"draft": draft_phase_lane, "review": review_phase_lane}
        draft_phase_model = resolve_model_name_for_lane(call_type="report_v3_draft", selected_lane=draft_phase_lane)
        review_phase_model = resolve_model_name_for_lane(call_type="report_v3_review_round_1", selected_lane=review_phase_lane)
        report_draft_max_tokens = min(MAX_TOKENS_REPORT, runtime_cfg["draft_max_tokens"])
        report_review_max_tokens = min(MAX_TOKENS_REPORT, runtime_cfg["review_max_tokens"])

        _set_exception_stage("evidence_pack", phase_lanes=phase_lanes, profile=runtime_profile)
        evidence_pack_started_at = _time.perf_counter()
        evidence_pack = build_report_evidence_pack(session)
        pipeline_timings["evidence_pack_ms"] = round((_time.perf_counter() - evidence_pack_started_at) * 1000.0, 2)

        if session_id:
            update_report_generation_status(
                session_id,
                "building_prompt",
                message="正在构建证据包并生成结构化草案...",
                detail_key="evidence_pack",
                next_hint="证据包完成后将开始结构化草案生成",
                progress_override=24,
            )

        draft_attempt_total = runtime_cfg["draft_retry_count"] + 1
        draft_parsed = None
        last_draft_reason = "draft_generation_failed"
        last_draft_raw = ""
        last_draft_call_type = "report_v3_draft"
        last_facts_limit = runtime_cfg["draft_facts_limit"]
        last_draft_tokens = report_draft_max_tokens
        last_draft_timeout = float(runtime_cfg["draft_timeout"])
        last_draft_prompt_length = 0
        last_draft_parse_meta = {}

        for attempt_index in range(draft_attempt_total):
            round_no = attempt_index + 1
            is_first_attempt = attempt_index == 0
            current_facts_limit = max(
                runtime_cfg["draft_min_facts_limit"],
                runtime_cfg["draft_facts_limit"] - (attempt_index * 12),
            )
            current_contradiction_limit = max(8, 20 - (attempt_index * 5))
            current_unknown_limit = max(8, 20 - (attempt_index * 5))
            current_blindspot_limit = max(8, 20 - (attempt_index * 5))
            current_token_floor = int(runtime_cfg.get("draft_token_floor", 2200) or 2200)
            current_max_tokens = max(current_token_floor, int(report_draft_max_tokens * (0.82 ** attempt_index)))
            current_call_type = "report_v3_draft" if is_first_attempt else f"report_v3_draft_retry_{round_no}"
            current_call_type = f"{current_call_type}{call_type_suffix}"

            if session_id:
                update_report_generation_status(
                    session_id,
                    "generating",
                    message=(
                        f"草案生成失败，正在降载重试（第{round_no}/{draft_attempt_total}轮）..."
                        if not is_first_attempt
                        else f"正在生成结构化草案（第{round_no}/{draft_attempt_total}轮）..."
                    ),
                    detail_key="v3_draft_retry" if not is_first_attempt else "v3_draft",
                    next_hint="草案完成后将进入一致性审稿",
                    progress_override=42 if is_first_attempt else 48,
                )

            _set_exception_stage(
                "draft_prompt",
                draft_round_no=round_no,
                draft_attempt_total=draft_attempt_total,
                facts_limit=current_facts_limit,
                contradiction_limit=current_contradiction_limit,
                unknown_limit=current_unknown_limit,
                blindspot_limit=current_blindspot_limit,
                phase_lanes=phase_lanes,
            )
            draft_prompt = build_report_draft_prompt_v3(
                session,
                evidence_pack,
                facts_limit=current_facts_limit,
                contradiction_limit=current_contradiction_limit,
                unknown_limit=current_unknown_limit,
                blindspot_limit=current_blindspot_limit,
                compact_mode=bool(runtime_cfg.get("release_conservative_mode", False)),
            )
            current_prompt_length = len(draft_prompt)
            current_max_tokens = compute_adaptive_report_tokens(
                current_max_tokens,
                current_prompt_length,
                floor_tokens=current_token_floor,
            )
            current_timeout_cap = runtime_cfg.get("draft_timeout_cap")
            if current_timeout_cap in {None, ""}:
                current_timeout_cap = max(REPORT_API_TIMEOUT, runtime_cfg["draft_timeout"] + 45)
            current_timeout = compute_adaptive_report_timeout(
                runtime_cfg["draft_timeout"],
                current_prompt_length,
                timeout_cap=current_timeout_cap,
            )
            draft_lane_candidates = [draft_phase_lane]
            alternate_draft_lane = resolve_report_v3_alternate_lane(draft_phase_lane)
            if bool(runtime_cfg.get("draft_allow_alternate_lane", True)) and alternate_draft_lane:
                draft_lane_candidates.append(alternate_draft_lane)

            for lane_index, candidate_lane in enumerate(draft_lane_candidates):
                lane_call_type = current_call_type if lane_index == 0 else f"{current_call_type}_fallback_{candidate_lane}"
                lane_model = resolve_model_name_for_lane(call_type="report_v3_draft", selected_lane=candidate_lane)
                _set_exception_stage(
                    "draft_generation",
                    draft_round_no=round_no,
                    candidate_lane=candidate_lane,
                    call_type=lane_call_type,
                    model=lane_model,
                    max_tokens=current_max_tokens,
                    timeout=current_timeout,
                    prompt_length=current_prompt_length,
                )
                draft_call_started_at = _time.perf_counter()
                draft_raw = call_claude(
                    draft_prompt,
                    max_tokens=current_max_tokens,
                    call_type=lane_call_type,
                    timeout=current_timeout,
                    preferred_lane=candidate_lane,
                    strict_preferred_lane=bool(runtime_cfg.get("draft_strict_primary_lane", False)),
                )
                pipeline_timings["draft_gen_ms"] += max(0.0, (_time.perf_counter() - draft_call_started_at) * 1000.0)

                last_draft_call_type = lane_call_type
                last_facts_limit = current_facts_limit
                last_draft_tokens = current_max_tokens
                last_draft_timeout = float(current_timeout)
                last_draft_prompt_length = current_prompt_length
                last_draft_raw = draft_raw or ""

                if not draft_raw:
                    last_draft_reason = "draft_generation_failed"
                    continue

                draft_parse_meta = {}
                _set_exception_stage(
                    "draft_parse",
                    draft_round_no=round_no,
                    candidate_lane=candidate_lane,
                    call_type=lane_call_type,
                    model=lane_model,
                    raw_length=len(draft_raw or ""),
                )
                draft_parse_start = _time.perf_counter()
                draft_parsed = parse_structured_json_response(
                    draft_raw,
                    required_keys=["overview", "needs", "analysis"],
                    require_all_keys=True,
                    parse_meta=draft_parse_meta,
                )
                draft_parse_elapsed = _time.perf_counter() - draft_parse_start
                last_draft_parse_meta = draft_parse_meta
                record_pipeline_stage_metric(
                    stage="draft_parse",
                    success=bool(draft_parsed),
                    elapsed_seconds=draft_parse_elapsed,
                    lane=candidate_lane,
                    model=lane_model,
                    error_msg=str(draft_parse_meta.get("last_error", "") or ""),
                )
                if draft_parsed:
                    if candidate_lane != draft_phase_lane:
                        phase_lanes["draft"] = candidate_lane
                        draft_phase_model = lane_model
                    break
                last_draft_reason = "draft_parse_failed"

            if draft_parsed:
                break

            if not draft_parsed and runtime_cfg["fast_fail_on_draft_empty"] and attempt_index == 0 and draft_attempt_total > 1:
                if ENABLE_DEBUG_LOG and last_draft_reason == "draft_generation_failed":
                    print("⚠️ 草案首轮空响应，触发快速失败以尽快切换 failover 通道")
                if last_draft_reason == "draft_generation_failed":
                    break

            if attempt_index < (draft_attempt_total - 1) and runtime_cfg["draft_retry_backoff_seconds"] > 0:
                _time.sleep(min(5.0, runtime_cfg["draft_retry_backoff_seconds"] * round_no))

        if not draft_parsed:
            return {
                "status": "failed",
                "reason": last_draft_reason,
                "error": (
                    f"draft_attempts_exhausted({draft_attempt_total}),"
                    f"profile={runtime_profile},"
                    f"last_call_type={last_draft_call_type},"
                    f"facts_limit={last_facts_limit},"
                    f"max_tokens={last_draft_tokens},"
                    f"timeout={last_draft_timeout},"
                    f"prompt_length={last_draft_prompt_length},"
                    f"raw_length={len(last_draft_raw)}"
                ),
                "parse_stage": "draft",
                "profile": runtime_profile,
                "lane": pipeline_lane,
                "phase_lanes": phase_lanes,
                "raw_excerpt": last_draft_raw[:360],
                "repair_applied": bool(last_draft_parse_meta.get("repair_applied", False)),
                "parse_meta": {
                    "candidate_count": int(last_draft_parse_meta.get("candidate_count", 0) or 0),
                    "parse_attempts": int(last_draft_parse_meta.get("parse_attempts", 0) or 0),
                    "selected_source": str(last_draft_parse_meta.get("selected_source", "") or ""),
                    "missing_keys": list(last_draft_parse_meta.get("missing_keys", []) or []),
                    "last_error": str(last_draft_parse_meta.get("last_error", "") or ""),
                },
                "evidence_pack": evidence_pack,
                "review_issues": [],
                "timings": pipeline_timings,
            }

        _set_exception_stage(
            "draft_validate",
            phase_lanes=phase_lanes,
            facts_count=len((evidence_pack or {}).get("facts", []) or []),
            draft_sections=len(draft_parsed.keys()) if isinstance(draft_parsed, dict) else 0,
        )
        current_draft, local_issues = validate_report_draft_v3(draft_parsed, evidence_pack)
        pre_review_repair = apply_deterministic_report_repairs_v3(
            current_draft,
            evidence_pack,
            local_issues,
            runtime_profile=runtime_profile,
        )
        if pre_review_repair.get("changed"):
            current_draft, local_issues = validate_report_draft_v3(
                pre_review_repair.get("draft", current_draft),
                evidence_pack,
            )
        review_issues = list(local_issues)
        base_review_rounds = runtime_cfg["review_base_rounds"]
        quality_fix_rounds = runtime_cfg["quality_fix_rounds"]
        total_round_budget = base_review_rounds + quality_fix_rounds
        min_required_review_rounds = max(1, min(total_round_budget, int(runtime_cfg.get("min_required_review_rounds", 1) or 1)))
        remaining_quality_fix_rounds = quality_fix_rounds
        final_issues = list(local_issues)
        last_failed_stage = "review_gate"
        last_review_round_no = 0

        if bool(runtime_cfg.get("skip_model_review", False)):
            _set_exception_stage(
                "quality_gate",
                review_round_no=0,
                review_skipped=True,
                phase_lanes=phase_lanes,
            )
            quality_gate_start = _time.perf_counter()
            quality_meta = compute_report_quality_meta_v3(current_draft, evidence_pack, final_issues)
            if isinstance(quality_meta, dict):
                quality_meta["runtime_profile"] = runtime_profile
                quality_meta["review_skipped_by_release_conservative"] = True
            quality_gate_issues = build_quality_gate_issues_v3(quality_meta)
            quality_gate_elapsed = _time.perf_counter() - quality_gate_start
            if quality_gate_issues:
                soft_pass = resolve_quality_gate_soft_pass_v3(quality_gate_issues, quality_meta, runtime_cfg)
                if soft_pass:
                    soft_issue_types = list(soft_pass.get("issue_types", []) or [])
                    if isinstance(quality_meta, dict):
                        quality_meta.update(soft_pass.get("quality_meta_updates", {}))
                    record_pipeline_stage_metric(
                        stage="quality_gate",
                        success=True,
                        elapsed_seconds=quality_gate_elapsed,
                        lane=review_phase_lane,
                        model=review_phase_model,
                        error_msg=f"{soft_pass.get('kind', 'soft_pass')}:{'|'.join(soft_issue_types)}",
                    )
                    _set_exception_stage(
                        "render_report",
                        review_round_no=0,
                        quality_gate_issue_count=len(quality_gate_issues or []),
                        soft_pass_kind=str(soft_pass.get("kind", "") or ""),
                    )
                    report_content = render_report_from_draft_v3(session, current_draft, quality_meta)
                    return {
                        "status": "success",
                        "profile": runtime_profile,
                        "report_content": report_content,
                        "draft_snapshot": copy.deepcopy(current_draft),
                        "quality_meta": quality_meta,
                        "evidence_pack": evidence_pack,
                        "report_template": resolve_report_template_for_session(session, evidence_pack=evidence_pack),
                        "report_type": str(evidence_pack.get("report_type", "standard") or "standard").strip().lower() or "standard",
                        "review_issues": quality_gate_issues[:60],
                        "phase_lanes": phase_lanes,
                        "review_rounds_executed": 0,
                        "min_required_review_rounds": 0,
                        "timings": pipeline_timings,
                    }
                record_pipeline_stage_metric(
                    stage="quality_gate",
                    success=False,
                    elapsed_seconds=quality_gate_elapsed,
                    lane=review_phase_lane,
                    model=review_phase_model,
                    error_msg=f"quality_issue_count={len(quality_gate_issues)}",
                )
                return {
                    "status": "failed",
                    "reason": "quality_gate_failed",
                    "legacy_reason": "review_not_passed_or_quality_gate_failed",
                    "error": f"profile={runtime_profile},final_issue_count={len(quality_gate_issues)},review_skipped=true",
                    "parse_stage": "quality_gate",
                    "profile": runtime_profile,
                    "lane": pipeline_lane,
                    "phase_lanes": phase_lanes,
                    "raw_excerpt": "",
                    "repair_applied": False,
                    "evidence_pack": evidence_pack,
                    "draft_snapshot": current_draft if isinstance(current_draft, dict) else {},
                    "review_issues": quality_gate_issues,
                    "final_issue_count": len(quality_gate_issues),
                    "final_issue_types": summarize_issue_types_v3(quality_gate_issues),
                    "failure_stage": "quality_gate",
                    "timings": pipeline_timings,
                }
            record_pipeline_stage_metric(
                stage="quality_gate",
                success=True,
                elapsed_seconds=quality_gate_elapsed,
                lane=review_phase_lane,
                model=review_phase_model,
                error_msg="skipped_model_review",
            )
            _set_exception_stage(
                "render_report",
                review_round_no=0,
                quality_gate_issue_count=0,
                review_skipped=True,
            )
            report_content = render_report_from_draft_v3(session, current_draft, quality_meta)
            return {
                "status": "success",
                "profile": runtime_profile,
                "report_content": report_content,
                "draft_snapshot": copy.deepcopy(current_draft),
                "quality_meta": quality_meta,
                "evidence_pack": evidence_pack,
                "report_template": resolve_report_template_for_session(session, evidence_pack=evidence_pack),
                "report_type": str(evidence_pack.get("report_type", "standard") or "standard").strip().lower() or "standard",
                "review_issues": [],
                "phase_lanes": phase_lanes,
                "review_rounds_executed": 0,
                "min_required_review_rounds": 0,
                "timings": pipeline_timings,
            }

        for review_round in range(total_round_budget):
            review_round_no = review_round + 1
            last_review_round_no = review_round_no
            review_round_started_at = _time.perf_counter()
            if session_id:
                update_report_generation_status(
                    session_id,
                    "generating",
                    message=f"正在执行报告一致性审稿（第{review_round_no}/{total_round_budget}轮）...",
                    detail_key="v3_review",
                    next_hint="审稿通过后将执行质量门校验",
                    progress_override=68,
                )

            _set_exception_stage(
                "review_prompt",
                review_round_no=review_round_no,
                total_round_budget=total_round_budget,
                current_issue_count=len(review_issues or []),
                phase_lanes=phase_lanes,
            )
            review_prompt = build_report_review_prompt_v3(session, evidence_pack, current_draft, review_issues)
            review_prompt_length = len(review_prompt)
            review_max_tokens = compute_adaptive_report_tokens(
                report_review_max_tokens,
                review_prompt_length,
                floor_tokens=2400,
            )
            review_timeout = compute_adaptive_report_timeout(
                runtime_cfg["review_timeout"],
                review_prompt_length,
                timeout_cap=max(REPORT_REVIEW_API_TIMEOUT, runtime_cfg["review_timeout"] + 60),
            )
            _set_exception_stage(
                "review_generation",
                review_round_no=review_round_no,
                lane=review_phase_lane,
                model=review_phase_model,
                max_tokens=review_max_tokens,
                timeout=review_timeout,
                prompt_length=review_prompt_length,
            )
            review_raw = call_claude(
                review_prompt,
                max_tokens=review_max_tokens,
                call_type=f"report_v3_review_round_{review_round + 1}{call_type_suffix}",
                timeout=review_timeout,
                preferred_lane=review_phase_lane,
            )
            if not review_raw:
                pipeline_timings["review_ms"] += max(0.0, (_time.perf_counter() - review_round_started_at) * 1000.0)
                return {
                    "status": "failed",
                    "reason": "review_generation_failed",
                    "error": (
                        f"profile={runtime_profile},"
                        f"review_round={review_round_no},"
                        f"max_tokens={review_max_tokens},"
                        f"timeout={review_timeout},"
                        f"prompt_length={review_prompt_length},"
                        "raw_length=0"
                    ),
                    "parse_stage": f"review_round_{review_round_no}",
                    "profile": runtime_profile,
                    "lane": pipeline_lane,
                    "phase_lanes": phase_lanes,
                    "raw_excerpt": "",
                    "repair_applied": False,
                    "draft_snapshot": current_draft if isinstance(current_draft, dict) else {},
                    "evidence_pack": evidence_pack,
                    "review_issues": final_issues,
                    "timings": pipeline_timings,
                }

            review_parse_meta = {}
            _set_exception_stage(
                "review_parse",
                review_round_no=review_round_no,
                lane=review_phase_lane,
                raw_length=len(review_raw or ""),
            )
            review_parse_start = _time.perf_counter()
            review_parsed = parse_report_review_response_v3(review_raw, parse_meta=review_parse_meta)
            review_parse_elapsed = _time.perf_counter() - review_parse_start
            record_pipeline_stage_metric(
                stage="review_parse",
                success=bool(review_parsed),
                elapsed_seconds=review_parse_elapsed,
                lane=review_phase_lane,
                model=review_phase_model,
                error_msg=str(review_parse_meta.get("last_error", "") or ""),
            )
            repair_review_raw = ""
            repair_review_meta = {}
            if not review_parsed and runtime_cfg.get("review_repair_retry_enabled", True):
                _set_exception_stage(
                    "review_parse_repair",
                    review_round_no=review_round_no,
                    lane=review_phase_lane,
                    raw_length=len(review_raw or ""),
                    max_tokens=min(
                        int(runtime_cfg.get("review_repair_max_tokens", REPORT_V3_REVIEW_REPAIR_MAX_TOKENS) or REPORT_V3_REVIEW_REPAIR_MAX_TOKENS),
                        review_max_tokens,
                    ),
                    timeout=min(
                        float(runtime_cfg.get("review_repair_timeout", REPORT_V3_REVIEW_REPAIR_TIMEOUT) or REPORT_V3_REVIEW_REPAIR_TIMEOUT),
                        review_timeout,
                    ),
                )
                repair_start = _time.perf_counter()
                repaired_review, repair_review_meta, repair_review_raw = repair_report_review_response_v3(
                    review_raw=review_raw,
                    current_draft=current_draft,
                    review_issues=review_issues,
                    preferred_lane=review_phase_lane,
                    review_round_no=review_round_no,
                    call_type_suffix=call_type_suffix,
                    max_tokens=min(
                        int(runtime_cfg.get("review_repair_max_tokens", REPORT_V3_REVIEW_REPAIR_MAX_TOKENS) or REPORT_V3_REVIEW_REPAIR_MAX_TOKENS),
                        review_max_tokens,
                    ),
                    timeout=min(
                        float(runtime_cfg.get("review_repair_timeout", REPORT_V3_REVIEW_REPAIR_TIMEOUT) or REPORT_V3_REVIEW_REPAIR_TIMEOUT),
                        review_timeout,
                    ),
                )
                repair_elapsed = _time.perf_counter() - repair_start
                record_pipeline_stage_metric(
                    stage="review_parse_repair",
                    success=bool(repaired_review),
                    elapsed_seconds=repair_elapsed,
                    lane=review_phase_lane,
                    model=review_phase_model,
                    error_msg=str(repair_review_meta.get("last_error", "") or ""),
                )
                if repaired_review:
                    review_parsed = repaired_review
                    review_parse_meta["repair_applied"] = True
                    review_parse_meta["selected_source"] = str(
                        repair_review_meta.get("selected_source", "")
                        or repair_review_meta.get("repair_call_type", "")
                    )
                    review_parse_meta["candidate_count"] = int(repair_review_meta.get("candidate_count", 0) or 0)
                    review_parse_meta["parse_attempts"] = int(repair_review_meta.get("parse_attempts", 0) or 0)
                    review_parse_meta["missing_keys"] = list(repair_review_meta.get("missing_keys", []) or [])
                    review_parse_meta["last_error"] = ""
                else:
                    review_parse_meta["last_error"] = str(
                        repair_review_meta.get("last_error", "")
                        or review_parse_meta.get("last_error", "")
                        or ""
                    )
            if not review_parsed:
                pipeline_timings["review_ms"] += max(0.0, (_time.perf_counter() - review_round_started_at) * 1000.0)
                return {
                    "status": "failed",
                    "reason": "review_parse_failed",
                    "error": (
                        f"profile={runtime_profile},"
                        f"review_round={review_round_no},"
                        f"max_tokens={review_max_tokens},"
                        f"timeout={review_timeout},"
                        f"prompt_length={review_prompt_length},"
                        f"raw_length={len(review_raw or '')}"
                    ),
                    "parse_stage": f"review_round_{review_round_no}",
                    "profile": runtime_profile,
                    "lane": pipeline_lane,
                    "phase_lanes": phase_lanes,
                    "raw_excerpt": str(repair_review_raw or review_raw or "")[:360],
                    "repair_applied": bool(review_parse_meta.get("repair_applied", False)),
                    "draft_snapshot": current_draft if isinstance(current_draft, dict) else {},
                    "parse_meta": {
                        "candidate_count": int(review_parse_meta.get("candidate_count", 0) or 0),
                        "parse_attempts": int(review_parse_meta.get("parse_attempts", 0) or 0),
                        "selected_source": str(review_parse_meta.get("selected_source", "") or ""),
                        "missing_keys": list(review_parse_meta.get("missing_keys", []) or []),
                        "last_error": str(review_parse_meta.get("last_error", "") or ""),
                        "repair_attempted": bool(repair_review_meta.get("attempted", False)),
                    },
                    "evidence_pack": evidence_pack,
                    "review_issues": final_issues,
                    "timings": pipeline_timings,
                }

            if isinstance(review_parsed.get("revised_draft"), dict):
                current_draft = merge_report_draft_patch_v3(current_draft, review_parsed["revised_draft"])

            _set_exception_stage(
                "review_validate",
                review_round_no=review_round_no,
                model_passed=bool(review_parsed.get("passed", False)),
                model_issue_count=len(review_parsed.get("issues", []) if isinstance(review_parsed.get("issues", []), list) else []),
            )
            current_draft, local_issues = validate_report_draft_v3(current_draft, evidence_pack)
            repair_seed_issues = (review_parsed.get("issues", []) if isinstance(review_parsed.get("issues", []), list) else []) + list(local_issues)
            round_repair = apply_deterministic_report_repairs_v3(
                current_draft,
                evidence_pack,
                repair_seed_issues,
                runtime_profile=runtime_profile,
            )
            if round_repair.get("changed"):
                current_draft, local_issues = validate_report_draft_v3(
                    round_repair.get("draft", current_draft),
                    evidence_pack,
                )

            merged_issues, filtered_model_issues = merge_review_and_local_issues_v3(
                review_parsed.get("issues", []),
                local_issues,
                current_draft,
                evidence_pack=evidence_pack,
                runtime_profile=runtime_profile,
            )
            final_issues = merged_issues

            model_signaled_pass = bool(review_parsed.get("passed", False))
            passed = len(merged_issues) == 0 and (model_signaled_pass or len(filtered_model_issues) == 0)
            if passed:
                _set_exception_stage(
                    "quality_gate",
                    review_round_no=review_round_no,
                    merged_issue_count=len(merged_issues or []),
                    filtered_model_issue_count=len(filtered_model_issues or []),
                )
                quality_gate_start = _time.perf_counter()
                quality_meta = compute_report_quality_meta_v3(current_draft, evidence_pack, final_issues)
                if isinstance(quality_meta, dict):
                    quality_meta["runtime_profile"] = runtime_profile
                quality_gate_issues = build_quality_gate_issues_v3(quality_meta)
                quality_gate_elapsed = _time.perf_counter() - quality_gate_start
                if quality_gate_issues:
                    soft_pass = resolve_quality_gate_soft_pass_v3(quality_gate_issues, quality_meta, runtime_cfg)
                    if soft_pass:
                        soft_issue_types = list(soft_pass.get("issue_types", []) or [])
                        if isinstance(quality_meta, dict):
                            quality_meta.update(soft_pass.get("quality_meta_updates", {}))
                        record_pipeline_stage_metric(
                            stage="quality_gate",
                            success=True,
                            elapsed_seconds=quality_gate_elapsed,
                            lane=review_phase_lane,
                            model=review_phase_model,
                            error_msg=f"{soft_pass.get('kind', 'soft_pass')}:{'|'.join(soft_issue_types)}",
                        )
                        _set_exception_stage(
                            "render_report",
                            review_round_no=review_round_no,
                            quality_gate_issue_count=len(quality_gate_issues or []),
                            soft_pass_kind=str(soft_pass.get("kind", "") or ""),
                        )
                        report_content = render_report_from_draft_v3(session, current_draft, quality_meta)
                        pipeline_timings["review_ms"] += max(0.0, (_time.perf_counter() - review_round_started_at) * 1000.0)
                        return {
                            "status": "success",
                            "profile": runtime_profile,
                            "report_content": report_content,
                            "draft_snapshot": copy.deepcopy(current_draft),
                            "quality_meta": quality_meta,
                            "evidence_pack": evidence_pack,
                            "report_template": resolve_report_template_for_session(session, evidence_pack=evidence_pack),
                            "report_type": str(evidence_pack.get("report_type", "standard") or "standard").strip().lower() or "standard",
                            "review_issues": quality_gate_issues[:60],
                            "phase_lanes": phase_lanes,
                            "review_rounds_executed": review_round_no,
                            "min_required_review_rounds": min_required_review_rounds,
                            "timings": pipeline_timings,
                        }
                    last_failed_stage = "quality_gate"
                    final_issues = quality_gate_issues
                    record_pipeline_stage_metric(
                        stage="quality_gate",
                        success=False,
                        elapsed_seconds=quality_gate_elapsed,
                        lane=review_phase_lane,
                        model=review_phase_model,
                        error_msg=f"quality_issue_count={len(quality_gate_issues)}",
                    )
                    if remaining_quality_fix_rounds <= 0:
                        pipeline_timings["review_ms"] += max(0.0, (_time.perf_counter() - review_round_started_at) * 1000.0)
                        break
                    remaining_quality_fix_rounds -= 1
                    review_issues = quality_gate_issues
                    pipeline_timings["review_ms"] += max(0.0, (_time.perf_counter() - review_round_started_at) * 1000.0)
                    continue
                record_pipeline_stage_metric(
                    stage="quality_gate",
                    success=True,
                    elapsed_seconds=quality_gate_elapsed,
                    lane=review_phase_lane,
                    model=review_phase_model,
                    error_msg="",
                )

                if review_round_no < min_required_review_rounds:
                    review_issues = [{
                        "type": "extra_review_round",
                        "target": "overall",
                        "message": (
                            f"当前已通过质量门禁，但仅完成第{review_round_no}轮审稿。"
                            f"请继续进行第{review_round_no + 1}轮深度润色，"
                            "重点提升表达清晰度、证据衔接与行动可执行性。"
                        ),
                    }]
                    pipeline_timings["review_ms"] += max(0.0, (_time.perf_counter() - review_round_started_at) * 1000.0)
                    continue

                _set_exception_stage(
                    "render_report",
                    review_round_no=review_round_no,
                    quality_gate_issue_count=0,
                    min_required_review_rounds=min_required_review_rounds,
                )
                report_content = render_report_from_draft_v3(session, current_draft, quality_meta)
                pipeline_timings["review_ms"] += max(0.0, (_time.perf_counter() - review_round_started_at) * 1000.0)
                return {
                    "status": "success",
                    "profile": runtime_profile,
                    "report_content": report_content,
                    "draft_snapshot": copy.deepcopy(current_draft),
                    "quality_meta": quality_meta,
                    "evidence_pack": evidence_pack,
                    "report_template": resolve_report_template_for_session(session, evidence_pack=evidence_pack),
                    "report_type": str(evidence_pack.get("report_type", "standard") or "standard").strip().lower() or "standard",
                    "review_issues": final_issues,
                    "phase_lanes": phase_lanes,
                    "review_rounds_executed": review_round_no,
                    "min_required_review_rounds": min_required_review_rounds,
                    "timings": pipeline_timings,
                }

            review_issues = merged_issues
            last_failed_stage = "review_gate"
            pipeline_timings["review_ms"] += max(0.0, (_time.perf_counter() - review_round_started_at) * 1000.0)

        final_issue_types = summarize_issue_types_v3(final_issues)
        failure_reason = "quality_gate_failed" if last_failed_stage == "quality_gate" else "review_gate_failed"
        failure_stage = "quality_gate" if last_failed_stage == "quality_gate" else f"review_round_{max(1, int(last_review_round_no or 1))}"
        if failure_reason != "quality_gate_failed" and any(_is_quality_gate_issue_type_v3(item) for item in final_issue_types):
            failure_reason = "quality_gate_failed"
            failure_stage = "quality_gate"
        return {
            "status": "failed",
            "reason": failure_reason,
            "legacy_reason": "review_not_passed_or_quality_gate_failed",
            "error": f"profile={runtime_profile},final_issue_count={len(final_issues)}",
            "parse_stage": failure_stage,
            "profile": runtime_profile,
            "lane": pipeline_lane,
            "phase_lanes": phase_lanes,
            "raw_excerpt": "",
            "repair_applied": False,
            "evidence_pack": evidence_pack,
            "draft_snapshot": current_draft if isinstance(current_draft, dict) else {},
            "review_issues": final_issues,
            "final_issue_count": len(final_issues),
            "final_issue_types": final_issue_types,
            "failure_stage": last_failed_stage,
            "timings": pipeline_timings,
        }
    except Exception as e:
        if ENABLE_DEBUG_LOG:
            print(f"⚠️ V3 报告流程失败: {summarize_error_for_log(e, limit=260)}")
        exception_kind = classify_v3_pipeline_exception(e)
        return {
            "status": "failed",
            "reason": "exception",
            "error": summarize_error_for_log(e, limit=200),
            "parse_stage": exception_stage,
            "profile": runtime_profile,
            "lane": pipeline_lane,
            "phase_lanes": phase_lanes if isinstance(phase_lanes, dict) else {
                "draft": resolve_report_v3_phase_lane("draft", pipeline_lane=pipeline_lane),
                "review": resolve_report_v3_phase_lane("review", pipeline_lane=pipeline_lane),
            },
            "raw_excerpt": "",
            "repair_applied": False,
            "evidence_pack": evidence_pack if isinstance(evidence_pack, dict) else {},
            "draft_snapshot": current_draft if isinstance(current_draft, dict) else {},
            "review_issues": [],
            "timings": pipeline_timings if isinstance(pipeline_timings, dict) else {},
            "failure_stage": exception_stage,
            "exception_stage": exception_stage,
            "exception_kind": exception_kind,
            "exception_context": exception_context if isinstance(exception_context, dict) else {},
        }


def is_unusable_legacy_report_content(content: Optional[str]) -> bool:
    """检测标准回退报告是否为无效的工具确认话术。"""
    text = str(content or "").strip()
    if not text:
        return True

    head = text[:900]
    blocked_markers = [
        "在创建文档之前，我需要先征得您的同意",
        "是否允许我创建这份访谈报告文档",
        "请确认是否继续",
        "如果同意，我会：",
        "创建文件名为",
    ]
    if any(marker in head for marker in blocked_markers):
        return True

    section_count = len(re.findall(r"(?m)^##\\s+", text))
    numbered_section_count = len(re.findall(r"(?m)^##\\s*[1-9][\\\\.、]", text))
    quality_keywords = ["访谈概述", "需求摘要", "分析", "风险", "行动", "建议"]
    keyword_hits = sum(1 for item in quality_keywords if item in text)
    if section_count < 4 and numbered_section_count < 3 and keyword_hits < 3:
        return True

    return False


def classify_v3_pipeline_exception(exc: Exception) -> str:
    """归类 V3 流水线异常类型，便于区分运行异常与内容门禁问题。"""
    if isinstance(exc, (TimeoutError, requests.exceptions.Timeout)):
        return "timeout"
    if isinstance(exc, (requests.exceptions.ConnectionError, requests.exceptions.SSLError)):
        return "network"
    if isinstance(exc, json.JSONDecodeError):
        return "parse"

    message = str(exc or "").strip().lower()
    if not message:
        return "unexpected"

    if any(token in message for token in ("timeout", "timed out", "超时")):
        return "timeout"
    if any(token in message for token in ("connection", "reset by peer", "gateway", "502", "503", "504", "ssl")):
        return "network"
    if any(token in message for token in ("json", "parse", "schema", "解析")):
        return "parse"
    if any(token in message for token in ("empty", "未包含可用文本内容", "响应为空")):
        return "empty"
    if isinstance(exc, ValueError):
        return "value_error"
    return "unexpected"


def run_report_generation_job(
    session_id: str,
    user_id: int,
    request_id: str,
    report_profile: str = "",
    action: str = "generate",
    source_report_name: str = "",
) -> None:
    """后台生成报告任务。"""
    job_started_at = _time.perf_counter()
    report_runtime_durations = {
        "session_load_ms": 0.0,
        "evidence_pack_ms": 0.0,
        "draft_gen_ms": 0.0,
        "review_ms": 0.0,
        "salvage_ms": 0.0,
        "failover_ms": 0.0,
        "legacy_fallback_ms": 0.0,
        "persist_ms": 0.0,
    }

    def _job_elapsed_ms(started_at: float) -> float:
        return max(0.0, (_time.perf_counter() - float(started_at or _time.perf_counter())) * 1000.0)

    def _merge_pipeline_timings(payload: Optional[dict]) -> None:
        if not isinstance(payload, dict):
            return
        timings = payload.get("timings")
        if not isinstance(timings, dict):
            return
        for key in ("evidence_pack_ms", "draft_gen_ms", "review_ms"):
            report_runtime_durations[key] = round(
                max(float(report_runtime_durations.get(key, 0.0) or 0.0), _safe_float(timings.get(key), 0.0)),
                2,
            )

    def _build_report_runtime_summary(path: str = "", reason: str = "", outcome: str = "completed") -> dict:
        timings = dict(report_runtime_durations)
        timings["total_ms"] = round(_job_elapsed_ms(job_started_at), 2)
        summary = {
            "path": str(path or ""),
            "reason": str(reason or ""),
            "outcome": str(outcome or ""),
            "timings": timings,
        }
        return summary

    def _record_report_runtime(outcome: str, runtime_profile: str = "", path: str = "", reason: str = "") -> None:
        runtime_summary = _build_report_runtime_summary(path=path, reason=reason, outcome=outcome)
        set_report_generation_metadata(
            session_id,
            {
                "runtime_timings": runtime_summary.get("timings", {}),
                "runtime_summary": {
                    "path": runtime_summary.get("path", ""),
                    "reason": runtime_summary.get("reason", ""),
                    "outcome": runtime_summary.get("outcome", ""),
                },
            },
        )
        record_report_generation_runtime_sample(
            durations=runtime_summary.get("timings", {}),
            outcome=outcome,
            runtime_profile=runtime_profile,
            path=path,
            reason=reason,
        )

    try:
        requested_action = "regenerate" if str(action or "").strip() == "regenerate" else "generate"
        selected_report_profile = normalize_report_profile_choice(report_profile, fallback=REPORT_V3_PROFILE)
        normalized_source_report_name = normalize_solution_report_filename(source_report_name)
        selected_report_variant_label = "精审版" if selected_report_profile == "quality" else "普通版"
        selected_report_runtime_cfg = get_report_v3_runtime_config(selected_report_profile)
        set_report_generation_metadata(session_id, {
            "report_profile": selected_report_profile,
            "source_report_name": normalized_source_report_name,
            "report_variant_label": selected_report_variant_label,
        })
        update_report_generation_status(
            session_id,
            "building_prompt",
            message="正在加载会话并准备报告任务...",
            detail_key="session_load",
            next_hint="完成后将开始构建证据包",
            progress_override=10,
        )
        session_load_started_at = _time.perf_counter()
        loaded = load_session_for_user(session_id, user_id, include_missing=True)
        report_runtime_durations["session_load_ms"] = round(_job_elapsed_ms(session_load_started_at), 2)
        session_file, session, state = loaded
        if state != "ok" or session_file is None or session is None:
            error_msg = "会话不存在或无权限"
            update_report_generation_status(
                session_id,
                "failed",
                message=f"报告生成失败：{error_msg}",
                active=False,
                detail_key="failed",
                next_hint="请检查会话权限或稍后重试",
            )
            set_report_generation_metadata(session_id, {
                "request_id": request_id,
                "error": error_msg,
                "completed_at": get_utc_now(),
            })
            _record_report_runtime("failed", runtime_profile=selected_report_profile, path="session_load", reason="session_unavailable")
            return

        session = migrate_session_docs(session)

        def persist_report(content: str, quality_meta: Optional[dict] = None) -> tuple[Path, str]:
            """保存报告并更新会话状态。"""
            persist_started_at = _time.perf_counter()
            filename = ""
            is_quality_variant = selected_report_profile == "quality" and bool(normalized_source_report_name)
            if requested_action == "regenerate":
                filename = resolve_session_bound_report_name(session, user_id)
            elif is_quality_variant:
                filename = build_report_variant_filename(normalized_source_report_name, selected_report_profile)

            if not filename:
                filename = build_session_report_filename(session, now=datetime.now())

            report_file = save_report_content_and_sync(filename, content)
            report_reference = build_report_storage_reference(filename) or str(report_file)
            unmark_report_as_deleted(filename)
            set_report_owner_id(filename, user_id)

            with named_file_lock("sessions", session_id):
                latest_session = safe_load_session(session_file)
                if isinstance(latest_session, dict) and ensure_session_owner(latest_session, user_id):
                    latest_session["status"] = "completed"
                    latest_session["updated_at"] = get_utc_now()
                    report_updated_at = get_utc_now()
                    if not is_quality_variant:
                        latest_session["current_report_name"] = filename
                        latest_session["current_report_path"] = report_reference
                        latest_session["current_report_updated_at"] = report_updated_at
                    latest_session["last_report_name"] = filename
                    if isinstance(quality_meta, dict):
                        latest_session["last_report_quality_meta"] = quality_meta
                    if isinstance(session.get("last_report_v3_debug"), dict):
                        latest_session["last_report_v3_debug"] = session["last_report_v3_debug"]
                    save_session_json_and_sync(session_file, latest_session)

                    if not is_quality_variant:
                        session["current_report_name"] = filename
                        session["current_report_path"] = report_reference
                        session["current_report_updated_at"] = latest_session["current_report_updated_at"]
                    session["last_report_name"] = filename
                    if isinstance(quality_meta, dict):
                        session["last_report_quality_meta"] = quality_meta
                    if isinstance(latest_session.get("last_report_v3_debug"), dict):
                        session["last_report_v3_debug"] = latest_session["last_report_v3_debug"]

            report_runtime_durations["persist_ms"] = round(
                float(report_runtime_durations.get("persist_ms", 0.0) or 0.0) + _job_elapsed_ms(persist_started_at),
                2,
            )
            return report_file, filename

        def build_v3_failure_debug(result: Optional[dict]) -> dict:
            if isinstance(result, dict):
                return {
                    "reason": result.get("reason", "v3_pipeline_returned_empty"),
                    "profile": result.get("profile", selected_report_profile),
                    "error": result.get("error", ""),
                    "parse_stage": result.get("parse_stage", ""),
                    "lane": result.get("lane", ""),
                    "phase_lanes": result.get("phase_lanes", {}) if isinstance(result.get("phase_lanes", {}), dict) else {},
                    "raw_excerpt": str(result.get("raw_excerpt", "") or "")[:360],
                    "repair_applied": bool(result.get("repair_applied", False)),
                    "parse_meta": result.get("parse_meta", {}) if isinstance(result.get("parse_meta", {}), dict) else {},
                    "review_issues": (result.get("review_issues", []) if isinstance(result.get("review_issues", []), list) else [])[:60],
                    "final_issue_count": int(result.get("final_issue_count", len(result.get("review_issues", []) or [])) or 0),
                    "final_issue_types": list(result.get("final_issue_types", summarize_issue_types_v3(result.get("review_issues", []))) or []),
                    "failure_stage": str(result.get("failure_stage", "") or ""),
                    "exception_stage": str(result.get("exception_stage", "") or ""),
                    "exception_kind": str(result.get("exception_kind", "") or ""),
                    "exception_context": result.get("exception_context", {}) if isinstance(result.get("exception_context", {}), dict) else {},
                    "evidence_pack_summary": summarize_evidence_pack_for_debug(result.get("evidence_pack", {})),
                    "salvage_attempted": bool(result.get("salvage_attempted", False)),
                    "salvage_success": bool(result.get("salvage_success", False)),
                    "salvage_note": str(result.get("salvage_note", "") or ""),
                    "salvage_error": str(result.get("salvage_error", "") or ""),
                    "salvage_quality_issue_count": int(result.get("salvage_quality_issue_count", 0) or 0),
                    "salvage_issue_types": list(result.get("salvage_issue_types", []) or []),
                    "salvage_issues": (result.get("salvage_issues", []) if isinstance(result.get("salvage_issues", []), list) else [])[:60],
                    "short_circuit_meta": result.get("short_circuit_meta", {}) if isinstance(result.get("short_circuit_meta", {}), dict) else {},
                }
            return {
                "reason": "v3_pipeline_returned_empty",
                "profile": selected_report_profile,
                "error": "",
                "parse_stage": "",
                "lane": "",
                "phase_lanes": {},
                "raw_excerpt": "",
                "repair_applied": False,
                "parse_meta": {},
                "review_issues": [],
                "final_issue_count": 0,
                "final_issue_types": [],
                "failure_stage": "",
                "exception_stage": "",
                "exception_kind": "",
                "exception_context": {},
                "evidence_pack_summary": {},
                "salvage_attempted": False,
                "salvage_success": False,
                "salvage_note": "",
                "salvage_error": "",
                "salvage_quality_issue_count": 0,
                "salvage_issue_types": [],
                "salvage_issues": [],
                "short_circuit_meta": {},
            }

        def persist_v3_success_result(
            result: dict,
            status_reason: str,
            saving_message: str,
            extra_debug: Optional[dict] = None,
        ) -> bool:
            if not isinstance(result, dict):
                return False
            report_body = str(result.get("report_content", "") or "")
            if not report_body.strip():
                return False

            report_content = report_body + generate_interview_appendix(session)
            quality_meta = result.get("quality_meta", {})
            if not isinstance(quality_meta, dict):
                quality_meta = {}
            session["last_report_quality_meta"] = quality_meta
            _merge_pipeline_timings(result)

            debug_payload = {
                "generated_at": get_utc_now(),
                "status": "success",
                "reason": status_reason,
                "profile": result.get("profile", selected_report_profile),
                "phase_lanes": result.get("phase_lanes", {}) if isinstance(result.get("phase_lanes", {}), dict) else {},
                "review_rounds_executed": int(result.get("review_rounds_executed", 0) or 0),
                "min_required_review_rounds": int(result.get("min_required_review_rounds", 0) or 0),
                "quality_meta": quality_meta,
                "review_issues": (result.get("review_issues", []) if isinstance(result.get("review_issues", []), list) else [])[:60],
                "evidence_pack_summary": summarize_evidence_pack_for_debug(result.get("evidence_pack", {})),
            }
            if isinstance(extra_debug, dict):
                debug_payload.update(extra_debug)
            session["last_report_v3_debug"] = debug_payload

            update_report_generation_status(
                session_id,
                "saving",
                message=saving_message,
                detail_key="persist_report",
                next_hint="保存完成后即可查看报告",
            )
            report_file, filename = persist_report(report_content, quality_meta=quality_meta)
            structured_snapshot = build_solution_sidecar_snapshot(
                report_name=filename,
                session_id=session_id,
                session=session,
                draft_snapshot=result.get("draft_snapshot", {}),
                quality_meta=quality_meta,
                evidence_pack=result.get("evidence_pack", {}),
                report_template=result.get("report_template", ""),
                report_type=result.get("report_type", ""),
                report_profile=selected_report_profile,
                source_report_name=normalized_source_report_name,
                report_variant_label=selected_report_variant_label,
            )
            write_solution_sidecar(
                filename,
                build_final_solution_sidecar_snapshot(structured_snapshot, report_content),
            )
            ensure_solution_payload_ready(filename, report_content, session_id=session_id)
            update_report_generation_status(
                session_id,
                "completed",
                active=False,
                detail_key="finished",
                next_hint="报告已生成，可直接查看",
            )
            set_report_generation_metadata(session_id, {
                "request_id": request_id,
                "report_name": filename,
                "report_path": str(report_file),
                "ai_generated": True,
                "v3_enabled": True,
                "report_quality_meta": quality_meta,
                "source_report_name": normalized_source_report_name,
                "report_variant_label": selected_report_variant_label,
                "error": "",
                "completed_at": get_utc_now(),
            })
            _record_report_runtime(
                "completed",
                runtime_profile=result.get("profile", selected_report_profile),
                path="v3_pipeline",
                reason=status_reason,
            )
            return True

        fast_short_circuit_meta = get_release_conservative_report_short_circuit_meta(
            selected_report_runtime_cfg,
            preferred_lane="report",
        )
        if resolve_ai_client(call_type="report"):
            if fast_short_circuit_meta.get("triggered"):
                v3_result = {
                    "status": "failed",
                    "reason": "release_conservative_short_circuit",
                    "legacy_reason": "release_conservative_short_circuit",
                    "error": str(fast_short_circuit_meta.get("message", "") or ""),
                    "parse_stage": "draft_short_circuit",
                    "profile": selected_report_profile,
                    "lane": "report",
                    "phase_lanes": {"draft": "report", "review": "report"},
                    "raw_excerpt": "",
                    "repair_applied": False,
                    "parse_meta": {},
                    "review_issues": [],
                    "final_issue_count": 0,
                    "final_issue_types": [],
                    "failure_stage": "draft_short_circuit",
                    "evidence_pack": {},
                    "timings": {
                        "evidence_pack_ms": 0.0,
                        "draft_gen_ms": 0.0,
                        "review_ms": 0.0,
                    },
                    "short_circuit_meta": fast_short_circuit_meta,
                }
                set_report_generation_metadata(session_id, {
                    "runtime_summary": {
                        "path": "legacy_fallback_short_circuit",
                        "reason": str(fast_short_circuit_meta.get("reason", "") or "release_conservative_short_circuit"),
                        "message": str(fast_short_circuit_meta.get("message", "") or ""),
                    }
                })
                update_report_generation_status(
                    session_id,
                    "generating",
                    message=str(fast_short_circuit_meta.get("message", "") or "检测到报告草案连续超时，直接回退标准报告生成..."),
                    detail_key="draft_short_circuit",
                    next_hint="已跳过 V3 草案，直接进入紧凑回退生成",
                    progress_override=58,
                )
            else:
                update_report_generation_status(
                    session_id,
                    "building_prompt",
                    message="正在执行 V3 证据包构建与结构化草案...",
                    detail_key="evidence_pack",
                    next_hint="完成证据包后会生成结构化草案",
                    progress_override=20,
                )
                v3_result = generate_report_v3_pipeline(
                    session,
                    session_id=session_id,
                    preferred_lane="report",
                    report_profile=selected_report_profile,
                )
            _merge_pipeline_timings(v3_result)

            if v3_result and v3_result.get("report_content"):
                if persist_v3_success_result(
                    v3_result,
                    status_reason="v3_pipeline_passed",
                    saving_message="正在保存 V3 审稿增强报告...",
                ):
                    return

            if bool(selected_report_runtime_cfg.get("salvage_on_quality_gate_failure", True)):
                update_report_generation_status(
                    session_id,
                    "generating",
                    message="正在尝试挽救当前 V3 草案，避免直接回退...",
                    detail_key="v3_salvage",
                    next_hint="如果挽救成功将直接进入保存",
                    progress_override=74,
                )
                salvage_started_at = _time.perf_counter()
                primary_salvage = attempt_salvage_v3_review_failure(session, v3_result)
                report_runtime_durations["salvage_ms"] = round(
                    float(report_runtime_durations.get("salvage_ms", 0.0) or 0.0) + _job_elapsed_ms(salvage_started_at),
                    2,
                )
            else:
                primary_salvage = {"attempted": False, "success": False, "note": "disabled_by_release_conservative_mode"}
            if isinstance(v3_result, dict):
                v3_result["salvage_attempted"] = bool(primary_salvage.get("attempted", False))
                v3_result["salvage_success"] = bool(primary_salvage.get("success", False))
                v3_result["salvage_note"] = str(primary_salvage.get("note", "") or "")
                v3_result["salvage_error"] = str(primary_salvage.get("error", "") or "")
                v3_result["salvage_quality_issue_count"] = int(primary_salvage.get("quality_gate_issue_count", 0) or 0)
                v3_result["salvage_issue_types"] = list(primary_salvage.get("quality_gate_issue_types", []) or [])
                v3_result["salvage_issues"] = (primary_salvage.get("quality_gate_issues", []) if isinstance(primary_salvage.get("quality_gate_issues", []), list) else [])[:60]

            if primary_salvage.get("success"):
                if ENABLE_DEBUG_LOG:
                    print(
                        "ℹ️ V3 审稿阶段失败后触发草案挽救成功，"
                        f"reason={primary_salvage.get('reason', '-')},profile={primary_salvage.get('profile', selected_report_profile)}"
                    )
                primary_salvage_result = {
                    "profile": primary_salvage.get("profile", selected_report_profile),
                    "phase_lanes": primary_salvage.get("phase_lanes", {}),
                    "report_content": primary_salvage.get("report_content", ""),
                    "quality_meta": primary_salvage.get("quality_meta", {}),
                    "review_issues": primary_salvage.get("review_issues", []),
                    "evidence_pack": primary_salvage.get("evidence_pack", {}),
                }
                if persist_v3_success_result(
                    primary_salvage_result,
                    status_reason="v3_pipeline_salvaged_after_primary_failure",
                    saving_message="V3 审稿异常已自动挽救，正在保存报告...",
                    extra_debug={
                        "salvage_mode": "primary",
                        "salvage_from_reason": primary_salvage.get("reason", ""),
                        "salvage_note": primary_salvage.get("note", ""),
                    },
                ):
                    return

            primary_failure = build_v3_failure_debug(v3_result)
            failover_attempted = False
            failover_success = False
            failover_failure = None
            failover_result = None

            if (
                bool(selected_report_runtime_cfg.get("failover_enabled", REPORT_V3_FAILOVER_ENABLED))
                and bool(selected_report_runtime_cfg.get("failover_on_single_issue", True))
                and can_use_v3_failover_lane()
                and should_retry_v3_with_failover(v3_result)
            ):
                failover_attempted = True
                if ENABLE_DEBUG_LOG:
                    print(
                        f"{choose_v3_failure_log_icon(primary_failure.get('reason', ''))} V3 主网关未直接通过，"
                        f"尝试切换备用网关 lane={REPORT_V3_FAILOVER_LANE} 重试；"
                        f"{build_v3_failure_log_context(primary_failure)}"
                    )
                update_report_generation_status(
                    session_id,
                    "generating",
                    message=(
                        f"V3 {describe_v3_failure_reason(primary_failure.get('reason', ''))}，"
                        f"正在切换备用网关（{REPORT_V3_FAILOVER_LANE}）重试..."
                    ),
                    detail_key="v3_failover",
                    next_hint=f"正在使用 {REPORT_V3_FAILOVER_LANE} 备用网关补救",
                    progress_override=70,
                )
                failover_suffix = f"_failover_{REPORT_V3_FAILOVER_LANE}"
                failover_started_at = _time.perf_counter()
                failover_result = generate_report_v3_pipeline(
                    session,
                    session_id=session_id,
                    preferred_lane=REPORT_V3_FAILOVER_LANE,
                    call_type_suffix=failover_suffix,
                    report_profile=selected_report_profile,
                )
                report_runtime_durations["failover_ms"] = round(
                    float(report_runtime_durations.get("failover_ms", 0.0) or 0.0) + _job_elapsed_ms(failover_started_at),
                    2,
                )
                _merge_pipeline_timings(failover_result)
                if failover_result and failover_result.get("report_content"):
                    failover_success = True
                    if persist_v3_success_result(
                        failover_result,
                        status_reason="v3_pipeline_passed_after_failover",
                        saving_message="备用网关重试成功，正在保存 V3 审稿增强报告...",
                        extra_debug={
                            "failover_lane": REPORT_V3_FAILOVER_LANE,
                            "primary_failure_reason": primary_failure.get("reason", ""),
                            "primary_profile": primary_failure.get("profile", selected_report_profile),
                            "primary_failure_error": primary_failure.get("error", ""),
                            "primary_parse_stage": primary_failure.get("parse_stage", ""),
                            "primary_lane": primary_failure.get("lane", ""),
                            "primary_phase_lanes": primary_failure.get("phase_lanes", {}),
                            "primary_repair_applied": primary_failure.get("repair_applied", False),
                            "primary_parse_meta": primary_failure.get("parse_meta", {}),
                            "primary_raw_excerpt": primary_failure.get("raw_excerpt", ""),
                            "primary_failure_context": build_v3_failure_log_context(primary_failure),
                        },
                    ):
                        return

                if bool(selected_report_runtime_cfg.get("salvage_on_quality_gate_failure", True)):
                    update_report_generation_status(
                        session_id,
                        "generating",
                        message="备用网关未直接通过，正在尝试挽救当前草案...",
                        detail_key="v3_salvage",
                        next_hint="如果挽救成功将直接进入保存",
                        progress_override=76,
                    )
                    failover_salvage_started_at = _time.perf_counter()
                    failover_salvage = attempt_salvage_v3_review_failure(session, failover_result)
                    report_runtime_durations["salvage_ms"] = round(
                        float(report_runtime_durations.get("salvage_ms", 0.0) or 0.0) + _job_elapsed_ms(failover_salvage_started_at),
                        2,
                    )
                else:
                    failover_salvage = {"attempted": False, "success": False, "note": "disabled_by_release_conservative_mode"}
                if isinstance(failover_result, dict):
                    failover_result["salvage_attempted"] = bool(failover_salvage.get("attempted", False))
                    failover_result["salvage_success"] = bool(failover_salvage.get("success", False))
                    failover_result["salvage_note"] = str(failover_salvage.get("note", "") or "")
                    failover_result["salvage_error"] = str(failover_salvage.get("error", "") or "")
                    failover_result["salvage_quality_issue_count"] = int(failover_salvage.get("quality_gate_issue_count", 0) or 0)
                    failover_result["salvage_issue_types"] = list(failover_salvage.get("quality_gate_issue_types", []) or [])
                    failover_result["salvage_issues"] = (failover_salvage.get("quality_gate_issues", []) if isinstance(failover_salvage.get("quality_gate_issues", []), list) else [])[:60]

                if failover_salvage.get("success"):
                    failover_success = True
                    if ENABLE_DEBUG_LOG:
                        print(
                            "ℹ️ V3 备用网关审稿阶段失败后触发草案挽救成功，"
                            f"reason={failover_salvage.get('reason', '-')},profile={failover_salvage.get('profile', selected_report_profile)}"
                        )
                    failover_salvage_result = {
                        "profile": failover_salvage.get("profile", selected_report_profile),
                        "phase_lanes": failover_salvage.get("phase_lanes", {}),
                        "report_content": failover_salvage.get("report_content", ""),
                        "quality_meta": failover_salvage.get("quality_meta", {}),
                        "review_issues": failover_salvage.get("review_issues", []),
                        "evidence_pack": failover_salvage.get("evidence_pack", {}),
                    }
                    if persist_v3_success_result(
                        failover_salvage_result,
                        status_reason="v3_pipeline_salvaged_after_failover",
                        saving_message="备用网关审稿异常已自动挽救，正在保存报告...",
                        extra_debug={
                            "salvage_mode": "failover",
                            "failover_lane": REPORT_V3_FAILOVER_LANE,
                            "salvage_from_reason": failover_salvage.get("reason", ""),
                            "salvage_note": failover_salvage.get("note", ""),
                            "primary_failure_reason": primary_failure.get("reason", ""),
                            "primary_profile": primary_failure.get("profile", selected_report_profile),
                            "primary_failure_context": build_v3_failure_log_context(primary_failure),
                        },
                    ):
                        return

                failover_failure = build_v3_failure_debug(failover_result)

            session["last_report_v3_debug"] = {
                "generated_at": get_utc_now(),
                "status": "failed",
                "reason": primary_failure.get("reason", "v3_pipeline_returned_empty"),
                "profile": primary_failure.get("profile", selected_report_profile),
                "error": primary_failure.get("error", ""),
                "parse_stage": primary_failure.get("parse_stage", ""),
                "lane": primary_failure.get("lane", ""),
                "phase_lanes": primary_failure.get("phase_lanes", {}),
                "repair_applied": primary_failure.get("repair_applied", False),
                "parse_meta": primary_failure.get("parse_meta", {}),
                "raw_excerpt": primary_failure.get("raw_excerpt", ""),
                "review_issues": primary_failure.get("review_issues", []),
                "final_issue_count": primary_failure.get("final_issue_count", 0),
                "final_issue_types": primary_failure.get("final_issue_types", []),
                "failure_stage": primary_failure.get("failure_stage", ""),
                "exception_stage": primary_failure.get("exception_stage", ""),
                "exception_kind": primary_failure.get("exception_kind", ""),
                "exception_context": primary_failure.get("exception_context", {}) if isinstance(primary_failure.get("exception_context", {}), dict) else {},
                "evidence_pack_summary": primary_failure.get("evidence_pack_summary", {}),
                "salvage_attempted": primary_failure.get("salvage_attempted", False),
                "salvage_success": primary_failure.get("salvage_success", False),
                "salvage_note": primary_failure.get("salvage_note", ""),
                "salvage_error": primary_failure.get("salvage_error", ""),
                "salvage_quality_issue_count": primary_failure.get("salvage_quality_issue_count", 0),
                "salvage_issue_types": primary_failure.get("salvage_issue_types", []),
                "salvage_issues": primary_failure.get("salvage_issues", []),
                "short_circuit_meta": primary_failure.get("short_circuit_meta", {}) if isinstance(primary_failure.get("short_circuit_meta", {}), dict) else {},
                "failover_attempted": failover_attempted,
                "failover_lane": REPORT_V3_FAILOVER_LANE if failover_attempted else "",
                "failover_success": failover_success,
                "failover_reason": failover_failure.get("reason", "") if failover_failure else "",
                "failover_profile": failover_failure.get("profile", selected_report_profile) if failover_failure else "",
                "failover_error": failover_failure.get("error", "") if failover_failure else "",
                "failover_parse_stage": failover_failure.get("parse_stage", "") if failover_failure else "",
                "failover_lane_effective": failover_failure.get("lane", "") if failover_failure else "",
                "failover_phase_lanes": failover_failure.get("phase_lanes", {}) if failover_failure else {},
                "failover_repair_applied": failover_failure.get("repair_applied", False) if failover_failure else False,
                "failover_parse_meta": failover_failure.get("parse_meta", {}) if failover_failure else {},
                "failover_raw_excerpt": failover_failure.get("raw_excerpt", "") if failover_failure else "",
                "failover_final_issue_count": failover_failure.get("final_issue_count", 0) if failover_failure else 0,
                "failover_final_issue_types": failover_failure.get("final_issue_types", []) if failover_failure else [],
                "failover_failure_stage": failover_failure.get("failure_stage", "") if failover_failure else "",
                "failover_exception_stage": failover_failure.get("exception_stage", "") if failover_failure else "",
                "failover_exception_kind": failover_failure.get("exception_kind", "") if failover_failure else "",
                "failover_exception_context": (
                    failover_failure.get("exception_context", {})
                    if failover_failure and isinstance(failover_failure.get("exception_context", {}), dict)
                    else {}
                ),
                "failover_salvage_attempted": failover_failure.get("salvage_attempted", False) if failover_failure else False,
                "failover_salvage_success": failover_failure.get("salvage_success", False) if failover_failure else False,
                "failover_salvage_note": failover_failure.get("salvage_note", "") if failover_failure else "",
                "failover_salvage_error": failover_failure.get("salvage_error", "") if failover_failure else "",
                "failover_salvage_quality_issue_count": failover_failure.get("salvage_quality_issue_count", 0) if failover_failure else 0,
                "failover_salvage_issue_types": failover_failure.get("salvage_issue_types", []) if failover_failure else [],
                "failover_salvage_issues": failover_failure.get("salvage_issues", []) if failover_failure else [],
                "primary_failure_context": build_v3_failure_log_context(primary_failure),
                "failover_failure_context": build_v3_failure_log_context(failover_failure) if failover_failure else "",
            }

            if ENABLE_DEBUG_LOG:
                print(
                    f"{choose_v3_failure_log_icon(primary_failure.get('reason', ''))} V3 报告流程未通过，自动回退标准流程；"
                    f"primary[{build_v3_failure_log_context(primary_failure)}]"
                    + (f"; failover[{build_v3_failure_log_context(failover_failure)}]" if failover_failure else "")
                )

            update_report_generation_status(
                session_id,
                "generating",
                message=(
                    str(primary_failure.get("error", "") or "")
                    if primary_failure.get("reason") == "release_conservative_short_circuit"
                    else f"V3 {describe_v3_failure_reason(primary_failure.get('reason', ''))}，正在回退标准报告生成..."
                ),
                detail_key="legacy_fallback",
                next_hint="回退成功后将直接保存报告",
                progress_override=78,
            )
            fallback_evidence_pack = None
            if isinstance(failover_result, dict) and isinstance(failover_result.get("evidence_pack"), dict) and failover_result.get("evidence_pack"):
                fallback_evidence_pack = failover_result.get("evidence_pack")
            elif isinstance(v3_result, dict) and isinstance(v3_result.get("evidence_pack"), dict) and v3_result.get("evidence_pack"):
                fallback_evidence_pack = v3_result.get("evidence_pack")

            compact_legacy_prompt = bool(selected_report_runtime_cfg.get("release_conservative_mode", False))
            short_circuit_legacy_fallback = primary_failure.get("reason") == "release_conservative_short_circuit"
            short_circuit_fallback_lane = (
                REPORT_V3_RELEASE_SHORT_CIRCUIT_FALLBACK_LANE
                if short_circuit_legacy_fallback
                else ""
            )
            prompt = build_report_prompt_with_options(
                session,
                evidence_pack=fallback_evidence_pack,
                compact_mode=compact_legacy_prompt,
            )

            if ENABLE_DEBUG_LOG:
                ref_docs_count = len(_collect_report_reference_materials(session))
                interview_count = len(session.get("interview_log", []))
                print(
                    "📊 回退报告 Prompt 统计："
                    f"模式={'compact' if compact_legacy_prompt else 'full'}，"
                    f"总长度={len(prompt)}字符，参考资料={ref_docs_count}个，访谈记录={interview_count}条"
                )

            legacy_timeout_base = (
                REPORT_V3_RELEASE_SHORT_CIRCUIT_FALLBACK_TIMEOUT
                if short_circuit_legacy_fallback and compact_legacy_prompt
                else (75.0 if compact_legacy_prompt else REPORT_API_TIMEOUT)
            )
            legacy_timeout = compute_adaptive_report_timeout(
                legacy_timeout_base,
                len(prompt),
                timeout_cap=(
                    min(60.0, legacy_timeout_base + 8.0)
                    if short_circuit_legacy_fallback and compact_legacy_prompt
                    else (95.0 if compact_legacy_prompt else max(REPORT_API_TIMEOUT, REPORT_DRAFT_API_TIMEOUT + 60))
                ),
            )
            legacy_max_tokens = compute_adaptive_report_tokens(
                (
                    REPORT_V3_RELEASE_SHORT_CIRCUIT_FALLBACK_MAX_TOKENS
                    if short_circuit_legacy_fallback and compact_legacy_prompt
                    else (2800 if compact_legacy_prompt else min(MAX_TOKENS_REPORT, 7000))
                ),
                len(prompt),
                floor_tokens=(
                    1100
                    if short_circuit_legacy_fallback and compact_legacy_prompt
                    else (1400 if compact_legacy_prompt else 2200)
                ),
            )
            legacy_started_at = _time.perf_counter()
            report_content = call_claude(
                prompt,
                max_tokens=legacy_max_tokens,
                retry_on_timeout=not short_circuit_legacy_fallback,
                call_type=(
                    "report_legacy_fallback_short_circuit"
                    if short_circuit_legacy_fallback
                    else "report_legacy_fallback"
                ),
                timeout=legacy_timeout,
                preferred_lane=short_circuit_fallback_lane,
            )
            report_runtime_durations["legacy_fallback_ms"] = round(
                float(report_runtime_durations.get("legacy_fallback_ms", 0.0) or 0.0) + _job_elapsed_ms(legacy_started_at),
                2,
            )

            if is_unusable_legacy_report_content(report_content):
                fallback_primary_lane = resolve_call_lane(call_type="report_legacy_fallback")
                fallback_primary_model = resolve_model_name_for_lane(
                    call_type="report_legacy_fallback",
                    selected_lane=fallback_primary_lane,
                )
                retry_lane = ""
                if bool(selected_report_runtime_cfg.get("failover_enabled", REPORT_V3_FAILOVER_ENABLED)) and can_use_v3_failover_lane():
                    retry_lane = REPORT_V3_FAILOVER_LANE
                if ENABLE_DEBUG_LOG:
                    print(
                        "ℹ️ 标准回退报告命中工具确认话术，准备重试；"
                        f"lane={fallback_primary_lane or '-'},model={fallback_primary_model or '-'},"
                        f"prompt_length={len(prompt)},raw_length={len(str(report_content or ''))},"
                        f"timeout={legacy_timeout:.1f}s,retry_lane={retry_lane or '-'}"
                    )
                if retry_lane:
                    retry_call_type = f"report_legacy_fallback_retry_{retry_lane}"
                    retry_model = resolve_model_name_for_lane(
                        call_type=retry_call_type,
                        selected_lane=retry_lane,
                    )
                    retry_content = call_claude(
                        prompt,
                        max_tokens=legacy_max_tokens,
                        call_type=retry_call_type,
                        timeout=legacy_timeout,
                        preferred_lane=retry_lane,
                    )
                    if not is_unusable_legacy_report_content(retry_content):
                        report_content = retry_content
                    else:
                        if ENABLE_DEBUG_LOG:
                            print(
                                "⚠️ 标准回退报告重试后仍疑似工具确认话术；"
                                f"retry_lane={retry_lane},retry_model={retry_model or '-'},"
                                f"retry_raw_length={len(str(retry_content or ''))}"
                            )
                        report_content = ""
                else:
                    if ENABLE_DEBUG_LOG:
                        print("⚠️ 标准回退报告命中工具确认话术，但当前无可用备用网关可重试")
                    report_content = ""

            if report_content:
                report_content = report_content + generate_interview_appendix(session)
                quality_meta = build_report_quality_meta_fallback(
                    session,
                    mode="legacy_ai_fallback",
                    evidence_pack=fallback_evidence_pack,
                )
                session["last_report_quality_meta"] = quality_meta

                update_report_generation_status(
                    session_id,
                    "saving",
                    message="正在保存回退生成报告...",
                    detail_key="persist_report",
                    next_hint="保存完成后即可查看报告",
                )
                report_file, filename = persist_report(report_content, quality_meta=quality_meta)
                rebound_snapshot = build_bound_solution_sidecar_snapshot(
                    filename,
                    report_content,
                    session,
                    report_profile=selected_report_profile,
                    source_report_name=normalized_source_report_name,
                    report_variant_label=selected_report_variant_label,
                )
                if rebound_snapshot:
                    write_solution_sidecar(filename, rebound_snapshot)
                ensure_solution_payload_ready(filename, report_content, session_id=session_id)
                update_report_generation_status(
                    session_id,
                    "completed",
                    active=False,
                    detail_key="finished",
                    next_hint="报告已生成，可直接查看",
                )
                set_report_generation_metadata(session_id, {
                    "request_id": request_id,
                    "report_name": filename,
                    "report_path": str(report_file),
                    "ai_generated": True,
                    "v3_enabled": False,
                    "report_quality_meta": quality_meta if isinstance(quality_meta, dict) else {},
                    "source_report_name": normalized_source_report_name,
                    "report_variant_label": selected_report_variant_label,
                    "error": "",
                    "completed_at": get_utc_now(),
                })
                fallback_runtime_path = "legacy_ai_fallback"
                fallback_runtime_reason = "v3_pipeline_fallback"
                if primary_failure.get("reason") == "release_conservative_short_circuit":
                    fallback_runtime_path = "legacy_fallback_short_circuit"
                    fallback_runtime_reason = str(
                        (primary_failure.get("short_circuit_meta", {}) or {}).get("reason", "")
                        or "release_conservative_short_circuit"
                    )
                _record_report_runtime(
                    "completed",
                    runtime_profile=selected_report_profile,
                    path=fallback_runtime_path,
                    reason=fallback_runtime_reason,
                )
                return

        update_report_generation_status(
            session_id,
            "fallback",
            message="AI 回退失败，正在使用模板报告兜底...",
            detail_key="simple_template_fallback",
            next_hint="模板报告生成完成后将立即保存",
            progress_override=84,
        )
        report_content = generate_simple_report(session)
        quality_meta = build_report_quality_meta_fallback(session, mode="simple_template_fallback")
        session["last_report_quality_meta"] = quality_meta
        update_report_generation_status(
            session_id,
            "saving",
            detail_key="persist_report",
            next_hint="保存完成后即可查看报告",
        )
        report_file, filename = persist_report(report_content, quality_meta=quality_meta)
        rebound_snapshot = build_bound_solution_sidecar_snapshot(
            filename,
            report_content,
            session,
            report_profile=selected_report_profile,
            source_report_name=normalized_source_report_name,
            report_variant_label=selected_report_variant_label,
        )
        if rebound_snapshot:
            write_solution_sidecar(filename, rebound_snapshot)

        ensure_solution_payload_ready(filename, report_content, session_id=session_id)
        update_report_generation_status(
            session_id,
            "completed",
            active=False,
            detail_key="finished",
            next_hint="报告已生成，可直接查看",
        )
        set_report_generation_metadata(session_id, {
            "request_id": request_id,
            "report_name": filename,
            "report_path": str(report_file),
            "ai_generated": False,
            "v3_enabled": False,
            "report_quality_meta": quality_meta if isinstance(quality_meta, dict) else {},
            "source_report_name": normalized_source_report_name,
            "report_variant_label": selected_report_variant_label,
            "error": "",
            "completed_at": get_utc_now(),
        })
        _record_report_runtime(
            "completed",
            runtime_profile=selected_report_profile,
            path="simple_template_fallback",
            reason="legacy_fallback_failed",
        )
    except Exception as exc:
        error_detail = str(exc)[:200] or "未知错误"
        update_report_generation_status(
            session_id,
            "failed",
            message=f"报告生成失败：{error_detail}",
            active=False,
            detail_key="failed",
            next_hint="可稍后重试或切换更保守策略",
        )
        set_report_generation_metadata(session_id, {
            "request_id": request_id,
            "error": error_detail,
            "completed_at": get_utc_now(),
        })
        _record_report_runtime(
            "failed",
            runtime_profile=selected_report_profile if 'selected_report_profile' in locals() else "",
            path="exception",
            reason=error_detail,
        )
        if ENABLE_DEBUG_LOG:
            print(f"❌ 报告生成异常: {error_detail}")
    finally:
        final_record = get_report_generation_record(session_id)
        final_state = str(final_record.get("state") or "").strip() if isinstance(final_record, dict) else ""
        cleanup_report_generation_worker(session_id)
        queue_snapshot = get_report_generation_worker_snapshot(include_positions=True)
        sync_report_generation_queue_metadata(session_id, snapshot=queue_snapshot)
        if final_state == "completed":
            record_report_generation_queue_event("completed")
        else:
            record_report_generation_queue_event("failed")
        release_report_generation_slot()
