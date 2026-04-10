import copy
import json
import queue
import re
import threading
import time as _time
from typing import Any, Optional


def configure_interview_runtime(bindings: dict[str, Any]) -> None:
    if not isinstance(bindings, dict):
        raise TypeError("bindings must be a dict")
    globals().update(bindings)


def _normalize_question_prompt_output_mode(output_mode: str = "full") -> str:
    normalized = str(output_mode or "full").strip().lower()
    if normalized in {"light", "fast", "fast_light", "lite"}:
        return "light"
    return "full"


def _clip_prompt_text(text: str, limit: int, *, keep_newlines: bool = False) -> str:
    if limit <= 0:
        return ""
    raw = str(text or "")
    if keep_newlines:
        normalized = "\n".join(line.strip() for line in raw.splitlines() if line.strip())
    else:
        normalized = re.sub(r"\s+", " ", raw).strip()
    if len(normalized) <= limit:
        return normalized
    if limit <= 3:
        return normalized[:limit]
    return normalized[: limit - 3].rstrip() + "..."


def build_interview_prompt(
    session: dict,
    dimension: str,
    all_dim_logs: list,
    session_id: str = None,
    session_signature: Optional[tuple[int, int]] = None,
    output_mode: str = "full",
    search_mode: str = "default",
    runtime_probe: bool = False,
) -> tuple[str, list, dict]:
    """构建访谈 prompt（使用滑动窗口 + 摘要压缩 + 智能追问）"""
    topic = session.get("topic", "未知项目")
    description = session.get("description")
    reference_materials = session.get("reference_materials", [])
    if not reference_materials:
        reference_materials = session.get("reference_docs", []) + session.get("research_docs", [])
    interview_log = session.get("interview_log", [])
    session_dim_info = get_dimension_info_for_session(session)
    dim_info = session_dim_info.get(dimension, {})
    interview_mode = get_mode_identifier(session)
    blindspot_cap = get_interview_mode_blindspot_cap(interview_mode)
    critical_dimension_hit = is_interview_mode_critical_dimension(interview_mode, dimension, dim_info)
    cache_session_id = str(session.get("session_id", "") or "").strip()
    normalized_output_mode = _normalize_question_prompt_output_mode(output_mode)
    normalized_search_mode = _normalize_search_decision_mode(search_mode)
    effective_search_mode = "rule_only" if runtime_probe and normalized_search_mode != "rule_only" else normalized_search_mode
    prompt_cache_key = _build_interview_prompt_cache_key(
        session_signature,
        dimension,
        cache_session_id,
        output_mode=normalized_output_mode,
        search_mode=effective_search_mode,
        runtime_probe=runtime_probe,
    )
    if prompt_cache_key:
        cached_prompt = _get_interview_prompt_cache(prompt_cache_key)
        if isinstance(cached_prompt, tuple) and len(cached_prompt) == 3:
            if ENABLE_DEBUG_LOG:
                print(f"📦 命中访谈 Prompt 缓存: dim={dimension}, mode={normalized_output_mode}")
            return cached_prompt

    is_lightweight_output = normalized_output_mode == "light"
    context_window_limit = 1 if is_lightweight_output else CONTEXT_WINDOW_SIZE
    include_history_summary = not is_lightweight_output and not runtime_probe
    search_result_limit = 1 if is_lightweight_output else 2
    search_excerpt_limit = 80 if is_lightweight_output else 150
    topic_text = _clip_prompt_text(topic, 80 if is_lightweight_output else 200)
    description_text = _clip_prompt_text(description, 220 if is_lightweight_output else 500)
    dimension_description = _clip_prompt_text(dim_info.get("description", ""), 72 if is_lightweight_output else 180)
    key_aspects = list(dim_info.get("key_aspects", []) or [])
    if is_lightweight_output:
        key_aspects = [_clip_prompt_text(item, 12) for item in key_aspects[:3] if _clip_prompt_text(item, 12)]
    key_aspects_text = "、".join(key_aspects) if key_aspects else "待补充"
    effective_reference_materials = list(reference_materials or [])
    doc_budget = MAX_TOTAL_DOCS
    if is_lightweight_output:
        if QUESTION_FAST_LIGHT_REFERENCE_DOCS_ENABLED:
            doc_budget = min(MAX_TOTAL_DOCS, QUESTION_FAST_LIGHT_DOC_BUDGET)
            effective_reference_materials = effective_reference_materials[:QUESTION_FAST_LIGHT_MAX_REFERENCE_DOCS]
        else:
            effective_reference_materials = []
            doc_budget = 0

    context_parts = [f"当前访谈主题：{topic_text}"]

    if description_text:
        context_parts.append(f"\n主题描述：{description_text}")

    total_doc_length = 0
    truncated_docs = []
    summarized_docs = []
    if effective_reference_materials and doc_budget > 0:
        context_parts.append("\n## 参考资料：")
        for doc in effective_reference_materials:
            if doc.get("content") and total_doc_length < doc_budget:
                remaining = doc_budget - total_doc_length
                if is_lightweight_output and remaining < min(SMART_SUMMARY_TARGET, 600):
                    break
                original_length = len(doc["content"])

                doc_name, processed_content, used_length, was_processed = process_document_for_context(
                    doc,
                    remaining,
                    topic,
                    allow_smart_summary=not runtime_probe,
                )

                if processed_content:
                    display_name = _clip_prompt_text(doc_name, 22 if is_lightweight_output else 48)
                    if is_lightweight_output:
                        light_doc_limit = min(320, max(180, remaining))
                        processed_content = _clip_prompt_text(processed_content, light_doc_limit, keep_newlines=True)
                        used_length = len(processed_content)
                        if used_length < original_length:
                            was_processed = True
                    source_marker = "🔄 " if doc.get("source") == "auto" else ""
                    context_parts.append(f"### {source_marker}{display_name}")
                    context_parts.append(processed_content)
                    total_doc_length += used_length

                    if was_processed:
                        if used_length < original_length * 0.6:
                            summarized_docs.append(display_name if is_lightweight_output else f"{doc_name}（原{original_length}字符，摘要至{used_length}字符）")
                        else:
                            truncated_docs.append(display_name if is_lightweight_output else f"{doc_name}（原{original_length}字符，截取{used_length}字符）")

    if summarized_docs:
        if is_lightweight_output:
            context_parts.append(f"\n提示：文档已摘要：{', '.join(summarized_docs[:2])}")
        else:
            context_parts.append(f"\n📝 注意：以下文档已通过AI生成摘要以保留关键信息：{', '.join(summarized_docs)}")
    if truncated_docs:
        if is_lightweight_output:
            context_parts.append(f"\n提示：文档有截断：{', '.join(truncated_docs[:2])}")
        else:
            context_parts.append(f"\n⚠️ 注意：以下文档因长度限制已被截断，请基于已有信息进行提问：{', '.join(truncated_docs)}")

    recent_qa = interview_log[-3:] if interview_log else []
    will_search, search_query, search_reason = smart_search_decision(
        topic,
        dimension,
        session,
        recent_qa,
        decision_mode=effective_search_mode,
    )

    if will_search and search_query:
        if session_id:
            update_thinking_status(session_id, "searching", has_search=True)

        if ENABLE_DEBUG_LOG:
            print(f"🔍 执行搜索: {search_query} (原因: {search_reason})")

        search_results = web_search(search_query)

        if search_results:
            context_parts.append("\n## 行业知识参考（联网搜索）：")
            for idx, result in enumerate(search_results[:search_result_limit], 1):
                if result["type"] == "intent":
                    context_parts.append(f"**{result['content'][:search_excerpt_limit]}**")
                else:
                    context_parts.append(f"{idx}. **{result.get('title', '参考信息')[:40]}**")
                    context_parts.append(f"   {result['content'][:search_excerpt_limit]}")

    if interview_log:
        context_parts.append("\n## 已收集的信息：")

        if len(interview_log) > context_window_limit:
            history_count = len(interview_log) - context_window_limit
            cached_summary = session.get("context_summary", {}) if isinstance(session.get("context_summary", {}), dict) else {}
            cached_count = int(cached_summary.get("log_count", 0) or 0)
            if cached_count < history_count:
                target_session_id = str(session_id or session.get("session_id", "") or "").strip()
                if target_session_id:
                    if not runtime_probe:
                        schedule_context_summary_update_async(target_session_id)

            history_summary = None
            if include_history_summary:
                history_summary = generate_history_summary(
                    session,
                    exclude_recent=context_window_limit,
                    allow_ai_generation=False,
                )
            if history_summary and include_history_summary:
                context_parts.append(f"\n### 历史访谈摘要（共{len(interview_log) - context_window_limit}条）：")
                context_parts.append(history_summary)
                context_parts.append("\n### 最近问答记录：")

            recent_logs = interview_log[-context_window_limit:]
        else:
            recent_logs = interview_log

        base_index = len(interview_log) - len(recent_logs)
        for offset, log in enumerate(recent_logs, 1):
            follow_up_mark = " [追问]" if log.get("is_follow_up") else ""
            q_number = base_index + offset
            if is_lightweight_output:
                question_text = _clip_prompt_text(log.get("question", ""), 72)
                answer_text = _clip_prompt_text(log.get("answer", ""), 120)
                context_parts.append(f"- Q{q_number}: {question_text}{follow_up_mark}")
                context_parts.append(f"  A: {answer_text}")
            else:
                context_parts.append(f"- Q{q_number}: {log['question']}{follow_up_mark}")
                context_parts.append(f"  A: {log['answer']}")
                dim_name = session_dim_info.get(log.get("dimension", ""), {}).get("name", "")
                if dim_name:
                    context_parts.append(f"  (维度: {dim_name})")

    formal_questions_count = len([log for log in all_dim_logs if not log.get("is_follow_up", False)])
    dimension_follow_up_count = len([log for log in all_dim_logs if log.get("is_follow_up", False)])
    mode_config = get_interview_mode_config(session)

    last_log = None
    should_follow_up = False
    suggest_ai_eval = False
    follow_up_reason = ""
    eval_signals = []
    comprehensive_decision = None
    hard_triggered = False
    missing_aspects = []
    evidence_ledger = refresh_session_evidence_ledger(session)
    preflight_plan = plan_mid_interview_preflight(session, dimension, ledger=evidence_ledger)
    follow_up_round = get_follow_up_round_for_dimension_logs(all_dim_logs)
    remaining_question_follow_up_budget = max(0, mode_config.get("max_questions_per_formal", 1) - follow_up_round)

    if all_dim_logs:
        last_log = all_dim_logs[-1]
        last_answer = last_log.get("answer", "")
        last_question = last_log.get("question", "")
        last_options = last_log.get("options", [])
        last_is_follow_up = last_log.get("is_follow_up", False)

        eval_result = evaluate_answer_depth(
            question=last_question,
            answer=last_answer,
            dimension=dimension,
            options=last_options,
            is_follow_up=last_is_follow_up,
            multi_select=bool(last_log.get("multi_select", False)),
            answer_mode=last_log.get("answer_mode", ""),
            requires_rationale=bool(last_log.get("requires_rationale", False)),
            evidence_intent=last_log.get("evidence_intent", ""),
        )

        eval_signals = eval_result["signals"]
        hard_triggered = bool(eval_result.get("hard_triggered", False))

        comprehensive_decision = should_follow_up_comprehensive(
            session=session,
            dimension=dimension,
            rule_based_result=eval_result,
            preflight_plan=preflight_plan,
        )

        should_follow_up = comprehensive_decision["should_follow_up"]
        follow_up_reason = comprehensive_decision["reason"] or ""

        suggest_ai_eval = eval_result["suggest_ai_eval"] and comprehensive_decision["should_follow_up"]

        missing_aspects = get_dimension_missing_aspects(session, dimension)
        preflight_plan = plan_mid_interview_preflight(
            session,
            dimension,
            ledger=evidence_ledger,
            rule_based_result=eval_result,
        )

        if ENABLE_DEBUG_LOG:
            budget = comprehensive_decision.get("budget_status", {})
            saturation = comprehensive_decision.get("saturation", {})
            fatigue = comprehensive_decision.get("fatigue", {})
            print(f"🔍 追问决策: should_follow_up={should_follow_up}, reason={follow_up_reason}")
            print(f"   预算: {budget.get('total_used', 0)}/{budget.get('total_budget', 0)} (维度: {budget.get('dimension_used', 0)}/{budget.get('dimension_budget', 0)})")
            if saturation:
                print(f"   饱和度: {saturation.get('saturation_score', 0):.0%} ({saturation.get('level', 'unknown')})")
            if fatigue:
                print(f"   疲劳度: {fatigue.get('fatigue_score', 0):.0%}, 信号: {fatigue.get('detected_signals', [])}")

    capture_contract = build_question_capture_contract(
        should_follow_up=should_follow_up,
        hard_triggered=hard_triggered,
        missing_aspects=missing_aspects,
        formal_questions_count=formal_questions_count,
        dimension=dimension,
    )
    if preflight_plan.get("boost_evidence_intent"):
        capture_contract["answer_mode"] = "pick_with_reason"
        capture_contract["requires_rationale"] = True
        capture_contract["evidence_intent"] = "high"
    answer_mode = capture_contract.get("answer_mode", "pick_only")
    requires_rationale = bool(capture_contract.get("requires_rationale", False))
    evidence_intent = capture_contract.get("evidence_intent", "low")
    prompt_missing_aspects = list(missing_aspects[:blindspot_cap]) if blindspot_cap > 0 else []

    ai_eval_guidance = ""
    if suggest_ai_eval and last_log and not is_lightweight_output:
        ai_eval_guidance = f"""
## 回答深度评估

请先评估用户的上一个回答是否需要追问：

**上一个问题**: {last_log.get('question', '')[:100]}
**用户回答**: {last_log.get('answer', '')}
**检测信号**: {', '.join(eval_signals) if eval_signals else '无明显问题'}

判断标准（满足任一条即应追问）：
1. 回答只是选择了抽象选项，选项文本本身也没有体现具体场景、原因或角色
2. 缺少量化指标（如时间、数量、频率等）
3. 回答比较笼统，没有针对性细节
4. 可能隐藏了更深层的需求或顾虑

如果判断需要追问，请：
- 设置 is_follow_up: true
- 针对上一个回答进行深入提问
- 问题要更具体，引导用户给出明确答案

如果本题 answer_mode 为 pick_with_reason，请优先设计自带场景、原因、角色或流程信息的高信息量选项；若证据仍不足，再通过下一题补一个轻量追问。

如果判断不需要追问，请生成新问题继续访谈。
"""

    blindspot_guidance = ""
    if not should_follow_up:
        min_formal = mode_config.get("formal_questions_per_dim", 3)
        if formal_questions_count >= min_formal and prompt_missing_aspects:
            if is_lightweight_output:
                blindspot_guidance = f"""
## 盲区补问

仍缺：{', '.join(prompt_missing_aspects)}

本题只补 1 个最关键缺口，不要重复已覆盖信息。
"""
            else:
                blindspot_guidance = f"""
## 盲区补问优先（必须执行）

当前维度仍有未覆盖关键方面：{', '.join(prompt_missing_aspects)}

生成新问题时请满足：
1. 问题必须直接点名至少 1 个未覆盖方面
2. 不要重复已充分覆盖的信息
3. 若有多个盲区，优先提问影响决策最大的方面
"""

    preflight_guidance = ""
    if preflight_plan.get("should_intervene"):
        focus_slots = [slot for slot in list(preflight_plan.get("probe_slots", []) or []) if str(slot or "").strip()]
        focus_text = "、".join(focus_slots[:EVIDENCE_LEDGER_MAX_FOCUS_SLOTS]) if focus_slots else "关键依据"
        blocked_sections = [item for item in list(preflight_plan.get("blocked_sections", []) or []) if str(item or "").strip()]
        blocked_text = f"，当前阻塞段落：{', '.join(blocked_sections)}" if blocked_sections else ""
        if is_lightweight_output:
            preflight_guidance = f"""
## 证据预检

优先补：{focus_text}{blocked_text}

要求：一次只补 1 个关键依据，优先用选项补原因/频次/角色/影响。
"""
        else:
            preflight_guidance = f"""
## 证据预检优先级（必须优先）

系统在访谈中途检测到当前维度仍有关键证据缺口：{preflight_plan.get('reason', '需要优先补齐关键依据')}{blocked_text}

本题请优先补齐：{focus_text}

执行要求：
1. 只补一个最关键的缺口，不要同时发散到多个新话题
2. 优先用 3-4 个可一键选择的高信息量选项完成补证据
3. 如果是追问，请围绕上一条回答补“原因/频次/角色/影响范围”中的一个
4. 若当前维度已有盲区，优先覆盖盲区而不是重复已充分信息
"""

    follow_up_section = ""
    if should_follow_up:
        if is_lightweight_output:
            follow_up_section = f"""## 追问模式（必须执行）

上一个用户回答需要追问。原因：{follow_up_reason}

**上一个问题**: {_clip_prompt_text(last_log.get('question', ''), 72) if last_log else ''}
**用户回答**: {_clip_prompt_text(last_log.get('answer', ''), 120) if last_log else ''}

追问要求：
1. 必须设置 is_follow_up: true
2. 追问必须紧扣上一条回答，不要跳题
3. 问题尽量简洁，优先问最关键的一个缺口
4. 优先给 3-4 个可一键选择的高信息量选项
"""
        else:
            follow_up_section = f"""## 追问模式（必须执行）

上一个用户回答需要追问。原因：{follow_up_reason}

**上一个问题**: {last_log.get('question', '')[:100] if last_log else ''}
**用户回答**: {last_log.get('answer', '') if last_log else ''}

追问要求：
1. 必须设置 is_follow_up: true
2. 针对上一个回答进行深入提问，不要跳到新话题
3. 追问问题要更具体、更有针对性
4. 优先通过 3-4 个高信息量选项收集原因、频次、角色或影响，不要依赖开放式长输入
5. 可以使用"您提到的XXX，主要是因为哪一种情况？"这样的句式，让用户一键补齐关键依据
"""
    else:
        if is_lightweight_output:
            follow_up_section = """## 问题生成要求

1. 生成 1 个清晰、聚焦的问题
2. 提供 3-4 个简洁选项
3. 优先覆盖当前最关键的一个缺口，不要贪多
4. 根据问题性质判断单选或多选：
   - 可并存枚举题优先多选
   - 只有明确唯一主项时才单选
5. 若 answer_mode=pick_with_reason，优先输出自带场景、原因或角色信息的选项
"""
        else:
            follow_up_section = """## 问题生成要求

1. 生成 1 个针对性的问题，用于收集该维度的关键信息
2. 为这个问题提供 3-4 个具体的选项
3. 选项要基于：
   - 访谈主题的行业特点
   - 参考文档中的信息（如有）
   - 联网搜索的行业知识（如有）
   - 已收集的上下文信息
4. 根据问题性质判断是单选还是多选：
   - 单选场景：互斥选项（是/否）、优先级选择、唯一选择
   - 多选场景：可并存的功能需求、多个痛点、多种用户角色
   - 凡是“哪些/哪些方面/哪些角色/哪些系统/哪些环节/需要与哪些集成/希望解决哪些问题”这类可并存枚举题，优先输出多选
   - 只有包含“最核心/最优先/唯一/当前最重要”等唯一性语义时才输出单选
5. 如果用户的回答与参考文档内容有冲突，要在问题中指出并请求澄清
6. 若 answer_mode=pick_with_reason，优先生成高信息量选项；只有证据仍不足时，才通过后续问题补一个轻追问
"""

    if is_lightweight_output:
        prompt = f"""**严格输出要求：你的回复必须是纯 JSON 对象，不要添加任何解释、markdown 代码块或其他文本。第一个字符必须是 {{，最后一个字符必须是 }}**

你是一个高效率的访谈师，正在进行"{topic_text}"的访谈。
请用尽量少的文字，生成一个可直接选择的问题。

{chr(10).join(context_parts)}

## 当前任务

你现在需要针对「{dim_info.get('name', dimension)}」维度收集信息。
这个维度关注：{dimension_description}

该维度已收集了 {formal_questions_count} 个正式问题的回答，关键方面包括：{key_aspects_text}
{blindspot_guidance}
{preflight_guidance}
{follow_up_section}

## JSON 模板

    {{
        "question": "你的问题",
        "options": ["选项1", "选项2", "选项3"],
        "multi_select": false,
        "answer_mode": {json.dumps(answer_mode, ensure_ascii=False)},
        "requires_rationale": {'true' if requires_rationale else 'false'},
        "evidence_intent": {json.dumps(evidence_intent, ensure_ascii=False)},
        "is_follow_up": {'true' if should_follow_up else 'false'},
        "follow_up_reason": {json.dumps(follow_up_reason, ensure_ascii=False) if should_follow_up else 'null'}
    }}

约束：
- 只输出这个 JSON，不要代码块，不要额外说明
- options 保持 3-4 个，每项尽量不超过 14 个字
- 不要输出 ai_recommendation、conflict_detected、conflict_description
- is_follow_up 必须严格照抄模板中的值"""
    else:
        prompt = f"""**严格输出要求：你的回复必须是纯 JSON 对象，不要添加任何解释、markdown 代码块或其他文本。第一个字符必须是 {{，最后一个字符必须是 }}**

你是一个专业的访谈师，正在进行"{topic_text}"的访谈。
你的核心职责是**深度挖掘用户的真实需求**，不满足于表面回答。

{chr(10).join(context_parts)}

## 当前任务

你现在需要针对「{dim_info.get('name', dimension)}」维度收集信息。
这个维度关注：{dimension_description or dim_info.get('description', '')}

该维度已收集了 {formal_questions_count} 个正式问题的回答，关键方面包括：{key_aspects_text}
{ai_eval_guidance}
{blindspot_guidance}
{preflight_guidance}
{follow_up_section}

如果信息足够，请基于已收集的回答给出对当前选项的 AI 推荐，用于辅助用户决策。若无法推荐，请将 ai_recommendation 设为 null。

## 输出格式（必须严格遵守）

你的回复必须是一个纯 JSON 对象，格式如下：

    {{
        "question": "你的问题",
        "options": ["选项1", "选项2", "选项3", "选项4"],
        "multi_select": false,
        "answer_mode": {json.dumps(answer_mode, ensure_ascii=False)},
        "requires_rationale": {'true' if requires_rationale else 'false'},
        "evidence_intent": {json.dumps(evidence_intent, ensure_ascii=False)},
        "is_follow_up": {'true' if should_follow_up else 'false'},
        "follow_up_reason": {json.dumps(follow_up_reason, ensure_ascii=False) if should_follow_up else 'null'},
        "conflict_detected": false,
        "conflict_description": null,
        "ai_recommendation": {{
            "recommended_options": ["选项1"],
            "summary": "一句话推荐理由",
            "reasons": [
                {{"text": "理由1", "evidence": ["Q1", "Q3"]}},
                {{"text": "理由2", "evidence": ["Q2"]}}
            ],
            "confidence": "high"
        }}
    }}

字段说明：
- question: 字符串，你要问的问题
- options: 字符串数组，3-4 个选项
- multi_select: 布尔值，true=可多选，false=单选
- answer_mode: "pick_only" | "pick_with_reason"
- requires_rationale: 布尔值，true 表示该题需要更强证据，系统必要时会自动补追问
- evidence_intent: "low" | "medium" | "high"
- is_follow_up: 布尔值，true=追问（针对上一回答深入），false=新问题
- follow_up_reason: 字符串或 null，追问时说明原因
- conflict_detected: 布尔值
- conflict_description: 字符串或 null
- ai_recommendation: 推荐对象或 null
  - recommended_options: 数组（单选时只放 1 个，多选时可放多个）
  - summary: 一句话推荐理由（不超过 25 字）
  - reasons: 2-3 条理由，需附证据编号（如 Q1、Q3）
  - confidence: "high" | "medium" | "low"

如果当前信息不足以做推荐，请将 ai_recommendation 设为 null。

**关键提醒：**
- 不要使用 ```json 代码块标记
- 不要在 JSON 前后添加任何说明文字
- 确保 JSON 语法完全正确（所有字符串用双引号，布尔值用 true/false，空值用 null）
- 你的整个回复就是这个 JSON 对象，没有其他内容
- **重要**：is_follow_up 的值已由系统根据预算和饱和度预先决定，请严格按照上述模板设置"""

    decision_meta = {
        "mode": interview_mode,
        "follow_up_round": follow_up_round,
        "dimension_follow_up_count": dimension_follow_up_count,
        "remaining_question_follow_up_budget": remaining_question_follow_up_budget,
        "hard_triggered": hard_triggered,
        "missing_aspects": missing_aspects,
        "prompt_missing_aspects": prompt_missing_aspects,
        "blindspot_cap": blindspot_cap,
        "critical_dimension_hit": bool(critical_dimension_hit),
        "should_follow_up": should_follow_up,
        "answer_mode": answer_mode,
        "requires_rationale": requires_rationale,
        "evidence_intent": evidence_intent,
        "has_search": bool(will_search and search_query),
        "search_mode": effective_search_mode,
        "output_mode": normalized_output_mode,
        "runtime_probe": bool(runtime_probe),
        "formal_questions_count": formal_questions_count,
        "has_reference_docs": bool(reference_materials),
        "reference_docs_compact_mode": bool(is_lightweight_output and effective_reference_materials),
        "has_truncated_docs": bool(truncated_docs),
        "evidence_ledger": {
            "formal_questions_total": int((evidence_ledger or {}).get("formal_questions_total", 0) or 0),
            "overall_evidence_density": float((evidence_ledger or {}).get("overall_evidence_density", 0.0) or 0.0),
            "priority_dimensions": list((evidence_ledger or {}).get("priority_dimensions", []) or []),
        },
        "shadow_draft": copy.deepcopy((evidence_ledger or {}).get("shadow_draft", {})),
        "mid_interview_preflight": copy.deepcopy(preflight_plan),
    }

    if prompt_cache_key:
        _set_interview_prompt_cache(
            prompt_cache_key,
            prompt,
            truncated_docs,
            decision_meta,
        )

    return prompt, truncated_docs, decision_meta


def _select_question_generation_runtime_profile(
    prompt: str,
    truncated_docs: Optional[list] = None,
    decision_meta: Optional[dict] = None,
    base_call_type: str = "question",
    allow_fast_path: bool = True,
    mode_strategy: Optional[dict] = None,
) -> dict:
    normalized_meta = dict(decision_meta or {})
    normalized_mode_strategy = dict(mode_strategy or {})
    normalized_mode = normalize_interview_mode_key(normalized_mode_strategy.get("mode", DEFAULT_INTERVIEW_MODE))
    lowered_call_type = str(base_call_type or "").strip().lower()
    is_prefetch_first = lowered_call_type.startswith("prefetch_first")
    is_prefetch = lowered_call_type.startswith("prefetch")
    profile_prefix = "prefetch_first" if is_prefetch_first else ("prefetch" if is_prefetch else "question")
    prompt_length = len(prompt or "")
    has_search = bool(normalized_meta.get("has_search", False))
    has_reference_docs = bool(normalized_meta.get("has_reference_docs", False))
    has_truncated_docs = bool(normalized_meta.get("has_truncated_docs", False) or truncated_docs)
    should_follow_up = bool(normalized_meta.get("should_follow_up", False))
    hard_triggered = bool(normalized_meta.get("hard_triggered", False))
    missing_aspects = list(normalized_meta.get("missing_aspects", []) or [])
    blindspot_cap = max(1, int(normalized_meta.get("blindspot_cap", normalized_mode_strategy.get("blindspot_cap", INTERVIEW_MODE_MAX_BLINDSPOTS_STANDARD)) or INTERVIEW_MODE_MAX_BLINDSPOTS_STANDARD))
    follow_up_round = max(0, int(normalized_meta.get("follow_up_round", 0) or 0))
    dimension_follow_up_count = max(0, int(normalized_meta.get("dimension_follow_up_count", follow_up_round) or 0))
    formal_questions_count = max(0, int(normalized_meta.get("formal_questions_count", 0) or 0))
    critical_dimension_hit = bool(normalized_meta.get("critical_dimension_hit", False))
    answer_mode = normalize_question_answer_mode(normalized_meta.get("answer_mode", ""), fallback="pick_only")
    explicit_requires_rationale = bool(normalized_meta.get("requires_rationale", False))
    requires_rationale = bool(explicit_requires_rationale or answer_mode == "pick_with_reason")
    evidence_intent = normalize_question_evidence_intent(
        normalized_meta.get("evidence_intent", ""),
        fallback="high" if explicit_requires_rationale else ("medium" if answer_mode == "pick_with_reason" else "low"),
    )
    allow_high_evidence = bool(normalized_mode_strategy.get("allow_high_evidence", True))
    promote_high_evidence = bool(normalized_mode_strategy.get("promote_high_evidence", False))
    standard_high_evidence_signal_count = sum(
        1
        for flag in (
            explicit_requires_rationale,
            has_reference_docs,
            bool(missing_aspects),
            hard_triggered,
            should_follow_up,
        )
        if bool(flag)
    )
    deep_high_evidence_signal_count = sum(
        1
        for flag in (
            explicit_requires_rationale,
            has_reference_docs,
            should_follow_up,
            hard_triggered,
            bool(missing_aspects),
            formal_questions_count >= 2,
            critical_dimension_hit,
        )
        if bool(flag)
    )
    if evidence_intent == "medium":
        if normalized_mode == "deep" and promote_high_evidence:
            if critical_dimension_hit and deep_high_evidence_signal_count >= QUESTION_HIGH_EVIDENCE_PROMOTION_MIN_SIGNALS_DEEP:
                evidence_intent = "high"
        elif normalized_mode == "standard" and allow_high_evidence:
            if standard_high_evidence_signal_count >= QUESTION_HIGH_EVIDENCE_PROMOTION_MIN_SIGNALS_STANDARD:
                evidence_intent = "high"
    if not allow_high_evidence and evidence_intent == "high":
        evidence_intent = "medium" if requires_rationale else "low"
    high_evidence_policy = str(
        normalized_mode_strategy.get("high_evidence_policy")
        or INTERVIEW_MODE_HIGH_EVIDENCE_POLICIES.get(normalized_mode, INTERVIEW_MODE_HIGH_EVIDENCE_POLICIES["standard"])
    )
    high_evidence_intent = evidence_intent == "high" and not is_prefetch
    can_use_light_prompt = not has_search and (
        not has_truncated_docs or (has_reference_docs and QUESTION_FAST_LIGHT_REFERENCE_DOCS_ENABLED)
    )
    reference_light_candidate = bool(can_use_light_prompt and has_reference_docs)
    high_evidence_fast_candidate = bool(high_evidence_intent and can_use_light_prompt and QUESTION_HIGH_EVIDENCE_FAST_PATH_ENABLED)
    effective_fast_allowed = bool(allow_fast_path)

    profile_name = f"{profile_prefix}_balanced_full"
    fast_output_mode = "full"
    fast_prompt_max_chars = QUESTION_FAST_LIGHT_PROMPT_MAX_CHARS
    primary_lane = "question"
    secondary_lane = QUESTION_HEDGED_SECONDARY_LANE
    hedged_enabled = bool(QUESTION_HEDGED_ENABLED)
    hedge_delay_seconds = float(QUESTION_HEDGED_DELAY_SECONDS)
    dynamic_lane_order_enabled = True
    disallowed_lanes = []
    fallback_enabled = False
    fast_timeout = _clamp_question_generation_timeout(QUESTION_FAST_TIMEOUT, minimum=5.0)
    fast_max_tokens = _clamp_question_generation_tokens(QUESTION_FAST_MAX_TOKENS, minimum=500)
    full_timeout = None
    full_max_tokens = _clamp_question_generation_tokens(MAX_TOKENS_QUESTION, minimum=700)
    max_tokens_ceiling = MAX_TOKENS_QUESTION
    fast_timeout_by_lane = QUESTION_FAST_TIMEOUT_BY_LANE
    fast_max_tokens_by_lane = QUESTION_FAST_MAX_TOKENS_BY_LANE
    full_timeout_by_lane = QUESTION_FULL_TIMEOUT_BY_LANE
    full_max_tokens_by_lane = QUESTION_FULL_MAX_TOKENS_BY_LANE
    hedge_delay_by_lane = QUESTION_HEDGE_DELAY_BY_LANE
    reasons = []
    release_conservative_mode = bool(QUESTION_RELEASE_CONSERVATIVE_MODE and not is_prefetch)

    if is_prefetch:
        primary_lane = PREFETCH_QUESTION_PRIMARY_LANE
        secondary_lane = PREFETCH_QUESTION_SECONDARY_LANE
        hedge_delay_seconds = float(PREFETCH_QUESTION_HEDGE_DELAY_SECONDS)
        fast_timeout = _clamp_question_generation_timeout(PREFETCH_QUESTION_FAST_TIMEOUT, minimum=5.0)
        fast_max_tokens = _clamp_question_generation_tokens(
            PREFETCH_QUESTION_FAST_MAX_TOKENS,
            minimum=500,
            ceiling=PREFETCH_QUESTION_MAX_TOKENS,
        )
        full_timeout = _clamp_question_generation_timeout(PREFETCH_QUESTION_TIMEOUT, minimum=15.0)
        full_max_tokens = _clamp_question_generation_tokens(
            PREFETCH_QUESTION_MAX_TOKENS,
            minimum=700,
            ceiling=PREFETCH_QUESTION_MAX_TOKENS,
        )
        max_tokens_ceiling = PREFETCH_QUESTION_MAX_TOKENS
        fast_timeout_by_lane = {}
        fast_max_tokens_by_lane = {}
        full_timeout_by_lane = {}
        full_max_tokens_by_lane = {}
        hedge_delay_by_lane = {}

    if high_evidence_intent:
        primary_lane = QUESTION_HIGH_EVIDENCE_PRIMARY_LANE
        secondary_lane = QUESTION_HIGH_EVIDENCE_SECONDARY_LANE
        hedged_enabled = bool(QUESTION_HIGH_EVIDENCE_HEDGED_ENABLED)
        fallback_enabled = bool(QUESTION_HEDGE_FAILURE_FALLBACK_ENABLED)
        fast_output_mode = "full"
        full_timeout = _clamp_question_generation_timeout(
            max((15.0 if is_prefetch else 18.0), float((full_timeout or fast_timeout)) if full_timeout is not None else float(fast_timeout) + 10.0),
            minimum=15.0 if is_prefetch else 18.0,
        )
        full_max_tokens = _clamp_question_generation_tokens(
            min(max_tokens_ceiling, max(1400, int(full_max_tokens or 0))),
            minimum=900,
            ceiling=max_tokens_ceiling,
        )
        disallowed_lanes.append("summary")
        dynamic_lane_order_enabled = not QUESTION_HIGH_EVIDENCE_DISABLE_DYNAMIC_LANE
        reasons.append("high_evidence_intent")
        if requires_rationale:
            reasons.append("requires_rationale")

    if has_search or (has_truncated_docs and not can_use_light_prompt):
        profile_name = f"{profile_prefix}_evidence_search_full" if high_evidence_intent else f"{profile_prefix}_search_full"
        effective_fast_allowed = False
        if has_search:
            reasons.append("has_search")
        if has_truncated_docs:
            reasons.append("has_truncated_docs")
    elif high_evidence_intent:
        if should_follow_up:
            profile_name = (
                f"{profile_prefix}_follow_up_reference_light"
                if reference_light_candidate else f"{profile_prefix}_follow_up_evidence"
            )
        elif hard_triggered or missing_aspects or formal_questions_count >= 2:
            profile_name = (
                f"{profile_prefix}_probe_reference_light"
                if reference_light_candidate else f"{profile_prefix}_probe_evidence"
            )
        else:
            profile_name = (
                f"{profile_prefix}_evidence_reference_light"
                if reference_light_candidate else f"{profile_prefix}_evidence_full"
            )
        if high_evidence_fast_candidate and (profile_name != f"{profile_prefix}_evidence_full" or reference_light_candidate):
            effective_fast_allowed = bool(allow_fast_path)
            fast_output_mode = "light"
            fast_prompt_max_chars = (
                QUESTION_FAST_REFERENCE_PROMPT_MAX_CHARS
                if reference_light_candidate else QUESTION_FAST_LIGHT_PROMPT_MAX_CHARS
            )
            if reference_light_candidate:
                fast_timeout = _resolve_reference_light_fast_timeout(fast_timeout, is_prefetch=is_prefetch)
            else:
                fast_timeout = _clamp_question_generation_timeout(
                    max(7.0, float(fast_timeout) - 2.0),
                    minimum=5.0,
                )
            fast_max_tokens = _clamp_question_generation_tokens(
                min(max_tokens_ceiling, 880 if reference_light_candidate else 760),
                minimum=500,
                ceiling=max_tokens_ceiling,
            )
            full_timeout = _clamp_question_generation_timeout(
                max((15.0 if is_prefetch else 18.0), float(full_timeout or fast_timeout) + 8.0),
                minimum=15.0 if is_prefetch else 18.0,
            )
            full_max_tokens = _clamp_question_generation_tokens(
                min(max_tokens_ceiling, 1500 if reference_light_candidate else 1400),
                minimum=820,
                ceiling=max_tokens_ceiling,
            )
            reasons.append("evidence_fast")
            if reference_light_candidate:
                fast_timeout_by_lane, fast_max_tokens_by_lane, fast_timeout, fast_max_tokens = _apply_reference_light_lane_runtime_overrides(
                    fast_timeout_by_lane,
                    fast_max_tokens_by_lane,
                    base_fast_timeout=fast_timeout,
                    max_tokens_ceiling=max_tokens_ceiling,
                    is_prefetch=is_prefetch,
                )
                reasons.append("reference_light")
        else:
            effective_fast_allowed = False
        if should_follow_up:
            reasons.append("follow_up")
        if hard_triggered:
            reasons.append("hard_triggered")
        if missing_aspects:
            reasons.append(f"missing_aspects={len(missing_aspects)}")
        if formal_questions_count >= 2:
            reasons.append(f"formal_questions={formal_questions_count}")
    elif can_use_light_prompt and should_follow_up:
        profile_name = (
            f"{profile_prefix}_follow_up_reference_light"
            if reference_light_candidate else f"{profile_prefix}_follow_up_light"
        )
        fast_output_mode = "light"
        fast_prompt_max_chars = (
            QUESTION_FAST_REFERENCE_PROMPT_MAX_CHARS
            if reference_light_candidate else QUESTION_FAST_LIGHT_PROMPT_MAX_CHARS
        )
        secondary_lane = "summary" if not is_prefetch else secondary_lane
        hedge_delay_seconds = min(float(hedge_delay_seconds), 1.0 if not is_prefetch else float(PREFETCH_QUESTION_HEDGE_DELAY_SECONDS))
        if reference_light_candidate:
            fast_timeout = _resolve_reference_light_fast_timeout(fast_timeout, is_prefetch=is_prefetch)
        else:
            fast_timeout = _clamp_question_generation_timeout(max(6.0, float(fast_timeout) - 3.0), minimum=5.0)
        fast_max_tokens = _clamp_question_generation_tokens(
            min(max_tokens_ceiling, 760 if reference_light_candidate else (650 if follow_up_round > 0 else 720)),
            minimum=420,
            ceiling=max_tokens_ceiling,
        )
        full_timeout = _clamp_question_generation_timeout(
            max((15.0 if is_prefetch else 18.0), float((full_timeout or fast_timeout)) if full_timeout is not None else float(fast_timeout) + 8.0),
            minimum=15.0 if is_prefetch else 18.0,
        )
        full_max_tokens = _clamp_question_generation_tokens(
            min(max_tokens_ceiling, 1300),
            minimum=720,
            ceiling=max_tokens_ceiling,
        )
        reasons.append("follow_up")
        if reference_light_candidate:
            fast_timeout_by_lane, fast_max_tokens_by_lane, fast_timeout, fast_max_tokens = _apply_reference_light_lane_runtime_overrides(
                fast_timeout_by_lane,
                fast_max_tokens_by_lane,
                base_fast_timeout=fast_timeout,
                max_tokens_ceiling=max_tokens_ceiling,
                is_prefetch=is_prefetch,
            )
            reasons.append("reference_light")
    elif can_use_light_prompt and (hard_triggered or missing_aspects or formal_questions_count >= 2 or prompt_length > QUESTION_FAST_LIGHT_PROMPT_MAX_CHARS):
        profile_name = (
            f"{profile_prefix}_probe_reference_light"
            if reference_light_candidate else f"{profile_prefix}_probe_light"
        )
        fast_output_mode = "light"
        fast_prompt_max_chars = (
            QUESTION_FAST_REFERENCE_PROMPT_MAX_CHARS
            if reference_light_candidate else QUESTION_FAST_LIGHT_PROMPT_MAX_CHARS
        )
        secondary_lane = "summary" if not is_prefetch else secondary_lane
        if reference_light_candidate:
            fast_timeout = _resolve_reference_light_fast_timeout(fast_timeout, is_prefetch=is_prefetch)
        else:
            fast_timeout = _clamp_question_generation_timeout(float(fast_timeout), minimum=5.0)
        fast_max_tokens = _clamp_question_generation_tokens(
            min(max_tokens_ceiling, 920 if reference_light_candidate else 850),
            minimum=500,
            ceiling=max_tokens_ceiling,
        )
        full_timeout = _clamp_question_generation_timeout(
            max((15.0 if is_prefetch else 18.0), float((full_timeout or fast_timeout)) if full_timeout is not None else float(fast_timeout) + 10.0),
            minimum=15.0 if is_prefetch else 18.0,
        )
        full_max_tokens = _clamp_question_generation_tokens(
            min(max_tokens_ceiling, 1500),
            minimum=800,
            ceiling=max_tokens_ceiling,
        )
        if hard_triggered:
            reasons.append("hard_triggered")
        if missing_aspects:
            reasons.append(f"missing_aspects={len(missing_aspects)}")
        if formal_questions_count >= 2:
            reasons.append(f"formal_questions={formal_questions_count}")
        if reference_light_candidate:
            fast_timeout_by_lane, fast_max_tokens_by_lane, fast_timeout, fast_max_tokens = _apply_reference_light_lane_runtime_overrides(
                fast_timeout_by_lane,
                fast_max_tokens_by_lane,
                base_fast_timeout=fast_timeout,
                max_tokens_ceiling=max_tokens_ceiling,
                is_prefetch=is_prefetch,
            )
            reasons.append("reference_light")
    elif can_use_light_prompt:
        profile_name = (
            f"{profile_prefix}_balanced_reference_light"
            if reference_light_candidate else f"{profile_prefix}_balanced_light"
        )
        fast_output_mode = "light"
        fast_prompt_max_chars = (
            QUESTION_FAST_REFERENCE_PROMPT_MAX_CHARS
            if reference_light_candidate else QUESTION_FAST_LIGHT_PROMPT_MAX_CHARS
        )
        secondary_lane = "summary" if not is_prefetch else secondary_lane
        if reference_light_candidate:
            fast_timeout = _resolve_reference_light_fast_timeout(fast_timeout, is_prefetch=is_prefetch)
        full_timeout = _clamp_question_generation_timeout(
            max((15.0 if is_prefetch else 18.0), float((full_timeout or fast_timeout)) if full_timeout is not None else float(fast_timeout) + 12.0),
            minimum=15.0 if is_prefetch else 18.0,
        )
        full_max_tokens = _clamp_question_generation_tokens(
            min(max_tokens_ceiling, 1500 if reference_light_candidate else 1400),
            minimum=800,
            ceiling=max_tokens_ceiling,
        )
        if reference_light_candidate:
            fast_timeout_by_lane, fast_max_tokens_by_lane, fast_timeout, fast_max_tokens = _apply_reference_light_lane_runtime_overrides(
                fast_timeout_by_lane,
                fast_max_tokens_by_lane,
                base_fast_timeout=fast_timeout,
                max_tokens_ceiling=max_tokens_ceiling,
                is_prefetch=is_prefetch,
            )
            reasons.append("reference_light")

    if has_reference_docs:
        reasons.append("has_reference_docs")
    if critical_dimension_hit:
        reasons.append("critical_dimension")
    if release_conservative_mode:
        if full_timeout is not None:
            conservative_full_timeout = 15.0 if high_evidence_intent else 14.0
            full_timeout = _clamp_question_generation_timeout(
                min(float(full_timeout), conservative_full_timeout),
                minimum=12.0 if not high_evidence_intent else 13.0,
            )
        full_max_tokens = _clamp_question_generation_tokens(
            min(max_tokens_ceiling, int(full_max_tokens or max_tokens_ceiling), 1200 if high_evidence_intent else 1100),
            minimum=720,
            ceiling=max_tokens_ceiling,
        )
        reasons.append("release_conservative")
    if not reasons:
        reasons.append(profile_name)

    return {
        "profile_name": profile_name,
        "selection_reason": ",".join([item for item in reasons if item]),
        "allow_fast_path": effective_fast_allowed,
        "fast_output_mode": _normalize_question_prompt_output_mode(fast_output_mode),
        "fast_prompt_max_chars": int(fast_prompt_max_chars),
        "full_output_mode": "full",
        "fast_timeout": fast_timeout,
        "fast_max_tokens": fast_max_tokens,
        "full_timeout": full_timeout,
        "full_max_tokens": full_max_tokens,
        "primary_lane": primary_lane,
        "secondary_lane": secondary_lane,
        "hedged_enabled": hedged_enabled,
        "hedge_delay_seconds": max(0.5, float(hedge_delay_seconds)),
        "fast_timeout_by_lane": fast_timeout_by_lane,
        "fast_max_tokens_by_lane": fast_max_tokens_by_lane,
        "full_timeout_by_lane": full_timeout_by_lane,
        "full_max_tokens_by_lane": full_max_tokens_by_lane,
        "hedge_delay_by_lane": hedge_delay_by_lane,
        "dynamic_lane_order_enabled": dynamic_lane_order_enabled,
        "disallowed_lanes": sorted(set(disallowed_lanes)),
        "fallback_enabled": fallback_enabled,
        "answer_mode": answer_mode,
        "requires_rationale": requires_rationale,
        "evidence_intent": evidence_intent,
        "critical_dimension_hit": critical_dimension_hit,
        "high_evidence_policy": high_evidence_policy,
        "blindspot_cap": blindspot_cap,
        "dimension_follow_up_count": dimension_follow_up_count,
    }


def _scale_question_lane_numeric_map(raw_map: Optional[dict], scale: float, *, minimum: float, clamp_fn) -> dict:
    source = raw_map if isinstance(raw_map, dict) else {}
    scaled = {}
    for lane, value in source.items():
        try:
            numeric_value = float(value)
        except Exception:
            continue
        scaled[lane] = clamp_fn(max(minimum, numeric_value * scale))
    return scaled


def _prepare_question_generation_runtime(
    session: dict,
    dimension: str,
    all_dim_logs: list,
    session_id: str = None,
    session_signature: Optional[tuple[int, int]] = None,
    base_call_type: str = "question",
    allow_fast_path: bool = True,
) -> dict:
    evidence_ledger = refresh_session_evidence_ledger(session)
    interview_mode = normalize_interview_mode_key(session.get("interview_mode", DEFAULT_INTERVIEW_MODE))
    mode_strategy = get_interview_mode_runtime_strategy(interview_mode)
    search_mode = str(mode_strategy.get("search_mode") or _resolve_prompt_search_mode(base_call_type))
    probe_full_prompt, probe_truncated_docs, probe_decision_meta = build_interview_prompt(
        session,
        dimension,
        all_dim_logs,
        session_id=session_id,
        session_signature=session_signature,
        output_mode="full",
        search_mode=search_mode,
        runtime_probe=True,
    )
    runtime_profile = _select_question_generation_runtime_profile(
        probe_full_prompt,
        truncated_docs=probe_truncated_docs,
        decision_meta=probe_decision_meta,
        base_call_type=base_call_type,
        allow_fast_path=allow_fast_path,
        mode_strategy=mode_strategy,
    )
    fast_timeout_scale = max(0.5, _safe_float(mode_strategy.get("fast_timeout_scale"), 1.0))
    fast_tokens_scale = max(0.5, _safe_float(mode_strategy.get("fast_tokens_scale"), 1.0))
    full_timeout_scale = max(0.5, _safe_float(mode_strategy.get("full_timeout_scale"), 1.0))
    full_tokens_scale = max(0.5, _safe_float(mode_strategy.get("full_tokens_scale"), 1.0))

    runtime_profile["interview_mode"] = interview_mode
    runtime_profile["blindspot_budget"] = str(mode_strategy.get("blindspot_budget") or "balanced")
    runtime_profile["blindspot_cap"] = max(1, int(mode_strategy.get("blindspot_cap", INTERVIEW_MODE_MAX_BLINDSPOTS_STANDARD) or INTERVIEW_MODE_MAX_BLINDSPOTS_STANDARD))
    runtime_profile["high_evidence_policy"] = str(mode_strategy.get("high_evidence_policy") or INTERVIEW_MODE_HIGH_EVIDENCE_POLICIES["standard"])
    runtime_profile["deep_model_fallback"] = bool(mode_strategy.get("deep_model_fallback", False))
    runtime_profile["lane_model_overrides"] = copy.deepcopy(mode_strategy.get("lane_model_overrides", {}) or {})
    runtime_profile["fast_timeout"] = _clamp_question_generation_timeout(
        max(5.0, _safe_float(runtime_profile.get("fast_timeout"), QUESTION_FAST_TIMEOUT) * fast_timeout_scale),
        minimum=5.0,
    )
    runtime_profile["fast_max_tokens"] = _clamp_question_generation_tokens(
        max(400, int(_safe_float(runtime_profile.get("fast_max_tokens"), QUESTION_FAST_MAX_TOKENS) * fast_tokens_scale)),
        minimum=400,
    )
    if runtime_profile.get("full_timeout") is not None:
        runtime_profile["full_timeout"] = _clamp_question_generation_timeout(
            max(12.0, _safe_float(runtime_profile.get("full_timeout"), QUESTION_FAST_TIMEOUT) * full_timeout_scale),
            minimum=12.0,
        )
    runtime_profile["full_max_tokens"] = _clamp_question_generation_tokens(
        max(600, int(_safe_float(runtime_profile.get("full_max_tokens"), MAX_TOKENS_QUESTION) * full_tokens_scale)),
        minimum=600,
    )
    runtime_profile["fast_timeout_by_lane"] = _scale_question_lane_numeric_map(
        runtime_profile.get("fast_timeout_by_lane"),
        fast_timeout_scale,
        minimum=5.0,
        clamp_fn=lambda value: _clamp_question_generation_timeout(value, minimum=5.0),
    )
    runtime_profile["fast_max_tokens_by_lane"] = _scale_question_lane_numeric_map(
        runtime_profile.get("fast_max_tokens_by_lane"),
        fast_tokens_scale,
        minimum=400,
        clamp_fn=lambda value: _clamp_question_generation_tokens(int(value), minimum=400),
    )
    runtime_profile["full_timeout_by_lane"] = _scale_question_lane_numeric_map(
        runtime_profile.get("full_timeout_by_lane"),
        full_timeout_scale,
        minimum=12.0,
        clamp_fn=lambda value: _clamp_question_generation_timeout(value, minimum=12.0),
    )
    runtime_profile["full_max_tokens_by_lane"] = _scale_question_lane_numeric_map(
        runtime_profile.get("full_max_tokens_by_lane"),
        full_tokens_scale,
        minimum=600,
        clamp_fn=lambda value: _clamp_question_generation_tokens(int(value), minimum=600),
    )

    full_prompt = probe_full_prompt
    truncated_docs = list(probe_truncated_docs or [])
    decision_meta = dict(probe_decision_meta or {})
    fast_prompt = full_prompt
    fast_truncated_docs = list(truncated_docs or [])
    fast_prompt_mode = str((decision_meta or {}).get("output_mode", "full") or "full")
    fast_allow_compacted_docs = False
    if runtime_profile.get("allow_fast_path") and runtime_profile.get("fast_output_mode") == "light":
        light_prompt, light_truncated_docs, light_decision_meta = build_interview_prompt(
            session,
            dimension,
            all_dim_logs,
            session_id=session_id,
            session_signature=session_signature,
            output_mode="light",
            search_mode=search_mode,
            runtime_probe=True,
        )
        light_compaction_allowed = bool(
            (light_decision_meta or {}).get("reference_docs_compact_mode", False)
            and not (light_decision_meta or {}).get("has_search", False)
        )
        if light_truncated_docs and not light_compaction_allowed:
            runtime_profile["allow_fast_path"] = False
            runtime_profile["selection_reason"] = (
                f"{runtime_profile.get('selection_reason', '')},light_prompt_truncated_docs".strip(",")
            )
        else:
            fast_prompt = light_prompt
            fast_truncated_docs = list(light_truncated_docs or [])
            fast_prompt_mode = str((light_decision_meta or {}).get("output_mode", "light") or "light")
            fast_allow_compacted_docs = bool(light_compaction_allowed)
    else:
        full_prompt, truncated_docs, decision_meta = build_interview_prompt(
            session,
            dimension,
            all_dim_logs,
            session_id=session_id,
            session_signature=session_signature,
            output_mode="full",
            search_mode=search_mode,
            runtime_probe=False,
        )
        fast_prompt = full_prompt
        fast_truncated_docs = list(truncated_docs or [])
        fast_prompt_mode = str((decision_meta or {}).get("output_mode", "full") or "full")

    runtime_profile["fast_prompt_mode"] = fast_prompt_mode
    runtime_profile["fast_allow_compacted_docs"] = bool(fast_allow_compacted_docs)
    runtime_profile["full_prompt_mode"] = str((decision_meta or {}).get("output_mode", "full") or "full")
    hedge_budget_state = _get_question_hedge_budget_state(session, dimension)
    shadow_blocker_state = _get_question_shadow_blocker_state(session, dimension, ledger=evidence_ledger)
    concurrent_hedge_allowed = bool(runtime_profile.get("hedged_enabled", QUESTION_HEDGED_ENABLED))
    fast_hedged_enabled = bool(concurrent_hedge_allowed)
    full_hedged_enabled = bool(concurrent_hedge_allowed)
    fallback_enabled = bool(runtime_profile.get("fallback_enabled", False))
    selection_reason = str(runtime_profile.get("selection_reason", "") or "").strip()
    reference_light_fast_candidate = bool(
        runtime_profile.get("fast_output_mode") == "light"
        and "reference_light" in str(runtime_profile.get("profile_name", "") or "")
        and not bool((decision_meta or {}).get("has_search", False))
    )

    if runtime_profile.get("evidence_intent") == "high":
        if QUESTION_HEDGE_REQUIRE_SHADOW_BLOCKER and not shadow_blocker_state["is_blocker"]:
            concurrent_hedge_allowed = False
            fast_hedged_enabled = False
            full_hedged_enabled = False
            selection_reason = ",".join(filter(None, [selection_reason, "hedge_blocked=no_shadow_blocker"]))
        if not hedge_budget_state["hedge_allowed"]:
            concurrent_hedge_allowed = False
            full_hedged_enabled = False
            if reference_light_fast_candidate and QUESTION_FAST_REFERENCE_HEDGE_BYPASS_BUDGET:
                fast_hedged_enabled = True
                selection_reason = ",".join(filter(None, [selection_reason, "hedge_blocked=budget_exhausted", "fast_hedge_budget_bypass=reference_light"]))
            else:
                fast_hedged_enabled = False
                selection_reason = ",".join(filter(None, [selection_reason, "hedge_blocked=budget_exhausted"]))
        else:
            fast_hedged_enabled = bool(concurrent_hedge_allowed)
            full_hedged_enabled = bool(concurrent_hedge_allowed)
    else:
        fast_hedged_enabled = bool(concurrent_hedge_allowed)
        full_hedged_enabled = bool(concurrent_hedge_allowed)

    if not bool(concurrent_hedge_allowed) and not reference_light_fast_candidate:
        fast_hedged_enabled = False
        full_hedged_enabled = False

    runtime_profile["hedged_enabled"] = bool(fast_hedged_enabled or full_hedged_enabled)
    runtime_profile["fast_hedged_enabled"] = bool(fast_hedged_enabled)
    runtime_profile["full_hedged_enabled"] = bool(full_hedged_enabled)
    runtime_profile["reference_light_fast_candidate"] = bool(reference_light_fast_candidate)
    runtime_profile["fallback_enabled"] = bool(fallback_enabled)
    runtime_profile["selection_reason"] = selection_reason
    runtime_profile["hedge_budget"] = copy.deepcopy(hedge_budget_state)
    runtime_profile["shadow_blocker"] = copy.deepcopy(shadow_blocker_state)

    enriched_decision_meta = dict(decision_meta or {})
    enriched_decision_meta.update({
        "runtime_profile": runtime_profile.get("profile_name", ""),
        "selection_reason": runtime_profile.get("selection_reason", ""),
        "fast_path_enabled": bool(runtime_profile.get("allow_fast_path", allow_fast_path)),
        "fast_prompt_mode": runtime_profile.get("fast_prompt_mode", "full"),
        "fast_allow_compacted_docs": bool(runtime_profile.get("fast_allow_compacted_docs", False)),
        "full_prompt_mode": runtime_profile.get("full_prompt_mode", "full"),
        "fast_timeout": runtime_profile.get("fast_timeout"),
        "fast_max_tokens": runtime_profile.get("fast_max_tokens"),
        "full_timeout": runtime_profile.get("full_timeout"),
        "full_max_tokens": runtime_profile.get("full_max_tokens"),
        "fast_timeout_by_lane": copy.deepcopy(runtime_profile.get("fast_timeout_by_lane", {}) or {}),
        "fast_max_tokens_by_lane": copy.deepcopy(runtime_profile.get("fast_max_tokens_by_lane", {}) or {}),
        "primary_lane": runtime_profile.get("primary_lane", "question"),
        "secondary_lane": runtime_profile.get("secondary_lane", QUESTION_HEDGED_SECONDARY_LANE),
        "interview_mode": interview_mode,
        "blindspot_budget": runtime_profile.get("blindspot_budget", "balanced"),
        "blindspot_cap": runtime_profile.get("blindspot_cap", INTERVIEW_MODE_MAX_BLINDSPOTS_STANDARD),
        "lane_model_overrides": copy.deepcopy(runtime_profile.get("lane_model_overrides", {}) or {}),
        "high_evidence_policy": runtime_profile.get("high_evidence_policy", INTERVIEW_MODE_HIGH_EVIDENCE_POLICIES["standard"]),
        "deep_model_fallback": bool(runtime_profile.get("deep_model_fallback", False)),
        "critical_dimension_hit": bool(runtime_profile.get("critical_dimension_hit", False)),
        "fast_prompt_length": len(fast_prompt or ""),
        "full_prompt_length": len(full_prompt or ""),
        "dynamic_lane_order_enabled": bool(runtime_profile.get("dynamic_lane_order_enabled", True)),
        "disallowed_lanes": list(runtime_profile.get("disallowed_lanes", []) or []),
        "hedged_enabled": bool(runtime_profile.get("hedged_enabled", QUESTION_HEDGED_ENABLED)),
        "fast_hedged_enabled": bool(runtime_profile.get("fast_hedged_enabled", runtime_profile.get("hedged_enabled", QUESTION_HEDGED_ENABLED))),
        "full_hedged_enabled": bool(runtime_profile.get("full_hedged_enabled", runtime_profile.get("hedged_enabled", QUESTION_HEDGED_ENABLED))),
        "fallback_enabled": bool(runtime_profile.get("fallback_enabled", False)),
        "hedge_budget": copy.deepcopy(hedge_budget_state),
        "shadow_blocker": copy.deepcopy(shadow_blocker_state),
        "answer_mode": runtime_profile.get("answer_mode", enriched_decision_meta.get("answer_mode", "pick_only")),
        "requires_rationale": bool(runtime_profile.get("requires_rationale", enriched_decision_meta.get("requires_rationale", False))),
        "evidence_intent": runtime_profile.get("evidence_intent", enriched_decision_meta.get("evidence_intent", "low")),
    })
    runtime_profile["answer_mode"] = enriched_decision_meta.get("answer_mode", "pick_only")
    runtime_profile["requires_rationale"] = bool(enriched_decision_meta.get("requires_rationale", False))
    runtime_profile["evidence_intent"] = enriched_decision_meta.get("evidence_intent", "low")
    runtime_profile["critical_dimension_hit"] = bool(enriched_decision_meta.get("critical_dimension_hit", False))

    return {
        "fast_prompt": fast_prompt,
        "fast_truncated_docs": fast_truncated_docs,
        "full_prompt": full_prompt,
        "truncated_docs": truncated_docs,
        "decision_meta": enriched_decision_meta,
        "evidence_ledger": evidence_ledger,
        "runtime_profile": runtime_profile,
    }


def _call_question_with_optional_hedge(
    prompt: str,
    max_tokens: int,
    call_type: str,
    truncated_docs: Optional[list] = None,
    timeout: Optional[float] = None,
    retry_on_timeout: bool = False,
    debug: bool = False,
    primary_lane: str = "question",
    secondary_lane: Optional[str] = None,
    hedged_enabled: Optional[bool] = None,
    hedge_delay_seconds: Optional[float] = None,
    lane_profile_name: str = "",
    lane_runtime_overrides: Optional[dict] = None,
    lane_model_overrides: Optional[dict] = None,
) -> tuple[Optional[str], str, dict]:
    """问题生成可选竞速：主通道先发，延迟触发备用通道，谁先返回可用结果用谁。"""
    valid_lanes = {"question", "report", "summary", "search_decision"}
    primary_lane = str(primary_lane or "question").strip().lower() or "question"
    default_secondary_lane = str(globals().get("QUESTION_HEDGED_SECONDARY_LANE", "summary") or "summary").strip().lower() or "summary"
    secondary_lane = str(secondary_lane or default_secondary_lane).strip().lower() or default_secondary_lane
    if primary_lane not in valid_lanes:
        primary_lane = "question"
    if secondary_lane not in valid_lanes:
        secondary_lane = default_secondary_lane
    hedged_enabled = bool(globals().get("QUESTION_HEDGED_ENABLED", False)) if hedged_enabled is None else bool(hedged_enabled)
    primary_timeout, _ = _resolve_question_lane_call_runtime_overrides(
        lane_runtime_overrides,
        primary_lane,
        timeout,
        max_tokens,
    )
    secondary_timeout, _ = _resolve_question_lane_call_runtime_overrides(
        lane_runtime_overrides,
        secondary_lane,
        timeout,
        max_tokens,
    )
    hedge_delay_seconds = _resolve_question_hedge_trigger_delay(hedge_delay_seconds, primary_lane, primary_timeout, lane_profile_name=lane_profile_name)

    def _run_single(lane: str, lane_call_type: str, hedge_flag: bool = False) -> tuple[Optional[str], dict]:
        started_at = _time.perf_counter()
        lane_timeout, lane_max_tokens = _resolve_question_lane_call_runtime_overrides(
            lane_runtime_overrides,
            lane,
            timeout,
            max_tokens,
        )
        override_model = ""
        if isinstance(lane_model_overrides, dict):
            override_model = str(lane_model_overrides.get(lane, "") or "").strip()
        raw_result = call_claude(
            prompt,
            max_tokens=lane_max_tokens,
            retry_on_timeout=retry_on_timeout,
            call_type=lane_call_type,
            truncated_docs=truncated_docs,
            timeout=lane_timeout,
            preferred_lane=lane,
            model_name=override_model,
            hedge_triggered=hedge_flag,
            return_meta=True,
        )
        response_text, response_meta = _normalize_question_call_result(raw_result, lane=lane, max_tokens=lane_max_tokens, timeout=lane_timeout)
        response_meta = dict(response_meta or {})
        response_meta.setdefault("response_time_ms", round((_time.perf_counter() - started_at) * 1000.0, 2))
        _record_question_lane_strategy_outcome(lane_profile_name, lane, response_text, response_meta)
        return response_text, response_meta

    def _build_attempts_summary(responses: list[tuple[str, Optional[str], dict]], started_lanes: list[str]) -> list[dict]:
        attempt_map = {}
        for resp_lane, resp_text, resp_meta in responses:
            attempt_map[resp_lane] = _build_question_attempt_summary(resp_lane, resp_text, resp_meta)
        for lane_name in started_lanes:
            lane_timeout, lane_max_tokens = _resolve_question_lane_call_runtime_overrides(
                lane_runtime_overrides,
                lane_name,
                timeout,
                max_tokens,
            )
            attempt_map.setdefault(
                lane_name,
                _build_question_attempt_summary(
                    lane_name,
                    None,
                    {
                        "selected_lane": lane_name,
                        "timeout_seconds": float(lane_timeout if lane_timeout is not None else API_TIMEOUT),
                        "max_tokens": int(lane_max_tokens),
                        "failure_reason": "no_result",
                    },
                ),
            )
        return [attempt_map[lane_name] for lane_name in started_lanes if lane_name in attempt_map]

    if not hedged_enabled or secondary_lane == primary_lane:
        response_text, response_meta = _run_single(primary_lane, call_type)
        response_meta = dict(response_meta or {})
        response_meta["attempts"] = _build_attempts_summary([(primary_lane, response_text, response_meta)], [primary_lane])
        return response_text, primary_lane, response_meta

    primary_client = resolve_ai_client(call_type=call_type, preferred_lane=primary_lane)
    secondary_client = resolve_ai_client(call_type=call_type, preferred_lane=secondary_lane)
    if not primary_client:
        return None, primary_lane, {
            "selected_lane": primary_lane,
            "attempts": _build_attempts_summary([], [primary_lane]),
        }
    if not secondary_client:
        response_text, response_meta = _run_single(primary_lane, call_type)
        response_meta = dict(response_meta or {})
        response_meta["attempts"] = _build_attempts_summary([(primary_lane, response_text, response_meta)], [primary_lane])
        return response_text, primary_lane, response_meta
    if QUESTION_HEDGED_ONLY_WHEN_DISTINCT_CLIENT and primary_client is secondary_client:
        response_text, response_meta = _run_single(primary_lane, call_type)
        response_meta = dict(response_meta or {})
        response_meta["attempts"] = _build_attempts_summary([(primary_lane, response_text, response_meta)], [primary_lane])
        return response_text, primary_lane, response_meta

    result_queue: queue.Queue = queue.Queue()
    started_lanes = [primary_lane]

    def _runner(lane: str, lane_call_type: str, hedge_flag: bool) -> None:
        response_text, response_meta = _run_single(lane, lane_call_type, hedge_flag=hedge_flag)
        result_queue.put((lane, response_text, response_meta))

    primary_thread = threading.Thread(
        target=_runner,
        args=(primary_lane, call_type, False),
        daemon=True,
        name=f"question-hedge-{call_type}-primary",
    )
    primary_thread.start()

    responses: list[tuple[str, Optional[str], dict]] = []
    delay_deadline = _time.time() + float(hedge_delay_seconds)
    while _time.time() < delay_deadline:
        wait_timeout = max(0.01, min(0.15, delay_deadline - _time.time()))
        try:
            lane, response_text, response_meta = result_queue.get(timeout=wait_timeout)
            responses.append((lane, response_text, response_meta))
            if response_text:
                response_meta = dict(response_meta or {})
                response_meta["attempts"] = _build_attempts_summary(responses, started_lanes)
                return response_text, lane, response_meta
        except queue.Empty:
            if not primary_thread.is_alive():
                break

    secondary_thread = None
    if all(not text for _lane, text, _meta in responses):
        if debug:
            print(f"⚡ 触发问题生成竞速: {primary_lane} vs {secondary_lane}")
        started_lanes.append(secondary_lane)
        secondary_thread = threading.Thread(
            target=_runner,
            args=(secondary_lane, f"{call_type}_hedged_{secondary_lane}", True),
            daemon=True,
            name=f"question-hedge-{call_type}-secondary",
        )
        secondary_thread.start()

    expected_count = 1 + (1 if secondary_thread else 0)
    longest_timeout = max(
        float(primary_timeout if primary_timeout is not None else API_TIMEOUT),
        float(secondary_timeout if secondary_timeout is not None else API_TIMEOUT),
    )
    finish_deadline = _time.time() + max(2.0, longest_timeout + 2.0)
    while len(responses) < expected_count and _time.time() < finish_deadline:
        wait_timeout = max(0.01, min(0.2, finish_deadline - _time.time()))
        try:
            lane, response_text, response_meta = result_queue.get(timeout=wait_timeout)
            responses.append((lane, response_text, response_meta))
            if response_text:
                response_meta = dict(response_meta or {})
                response_meta["attempts"] = _build_attempts_summary(responses, started_lanes)
                if debug and lane != primary_lane:
                    print(f"🏁 竞速命中备用通道: {lane}")
                return response_text, lane, response_meta
        except queue.Empty:
            secondary_alive = bool(secondary_thread and secondary_thread.is_alive())
            if not primary_thread.is_alive() and not secondary_alive:
                break

    return None, primary_lane, {
        "selected_lane": primary_lane,
        "attempts": _build_attempts_summary(responses, started_lanes),
    }


def generate_question_with_tiered_strategy(
    prompt: str,
    truncated_docs: Optional[list] = None,
    fast_truncated_docs: Optional[list] = None,
    debug: bool = False,
    base_call_type: str = "question",
    allow_fast_path: bool = True,
    fast_prompt: Optional[str] = None,
    runtime_profile: Optional[dict] = None,
) -> tuple[Optional[str], Optional[dict], str]:
    """问题生成双档策略：轻量 prompt 才尝试快档，失败时回退全量竞速。"""

    def _annotate_question_result(
        result_payload: Optional[dict],
        call_meta: Optional[dict],
        *,
        fallback_triggered: bool = False,
        hedge_triggered_override: Optional[bool] = None,
    ) -> Optional[dict]:
        if not isinstance(result_payload, dict):
            return result_payload
        meta = dict(call_meta or {})
        attempts = copy.deepcopy(meta.get("attempts", [])) if isinstance(meta.get("attempts", []), list) else []
        hedge_triggered = bool(hedge_triggered_override) if hedge_triggered_override is not None else len(attempts) > 1
        result_payload["question_hedge_triggered"] = bool(hedge_triggered)
        result_payload["question_fallback_triggered"] = bool(fallback_triggered)
        result_payload["question_attempts"] = attempts
        return result_payload

    runtime_profile = dict(runtime_profile or {})
    effective_fast_prompt = fast_prompt if isinstance(fast_prompt, str) and fast_prompt else prompt
    effective_fast_allowed = bool(runtime_profile.get("allow_fast_path", allow_fast_path))
    fast_timeout = runtime_profile.get("fast_timeout")
    if fast_timeout is None:
        fast_timeout = min(float(API_TIMEOUT), float(QUESTION_FAST_TIMEOUT))
    fast_max_tokens = _clamp_question_generation_tokens(
        runtime_profile.get("fast_max_tokens", QUESTION_FAST_MAX_TOKENS),
        minimum=400,
    )
    full_timeout = runtime_profile.get("full_timeout")
    full_max_tokens = _clamp_question_generation_tokens(
        runtime_profile.get("full_max_tokens", MAX_TOKENS_QUESTION),
        minimum=600,
    )
    hedged_enabled = runtime_profile.get("hedged_enabled", QUESTION_HEDGED_ENABLED)
    fast_hedged_enabled = runtime_profile.get("fast_hedged_enabled", hedged_enabled)
    full_hedged_enabled = runtime_profile.get("full_hedged_enabled", hedged_enabled)
    fallback_enabled = bool(runtime_profile.get("fallback_enabled", False))
    hedge_delay_seconds = runtime_profile.get("hedge_delay_seconds", QUESTION_HEDGED_DELAY_SECONDS)
    fast_primary_lane, fast_secondary_lane, fast_lane_meta = _resolve_dynamic_question_lane_order(runtime_profile, phase="fast")
    full_primary_lane, full_secondary_lane, full_lane_meta = _resolve_dynamic_question_lane_order(runtime_profile, phase="full")
    fast_primary_timeout, fast_primary_max_tokens, fast_hedge_delay_seconds = _resolve_question_lane_runtime_params(
        runtime_profile,
        fast_primary_lane,
        "fast",
        fast_timeout,
        fast_max_tokens,
        hedge_delay_seconds,
    )
    fast_secondary_timeout, fast_secondary_max_tokens, _ = _resolve_question_lane_runtime_params(
        runtime_profile,
        fast_secondary_lane,
        "fast",
        fast_timeout,
        fast_max_tokens,
        hedge_delay_seconds,
    )
    full_primary_timeout, full_primary_max_tokens, full_hedge_delay_seconds = _resolve_question_lane_runtime_params(
        runtime_profile,
        full_primary_lane,
        "full",
        full_timeout,
        full_max_tokens,
        hedge_delay_seconds,
    )
    full_secondary_timeout, full_secondary_max_tokens, _ = _resolve_question_lane_runtime_params(
        runtime_profile,
        full_secondary_lane,
        "full",
        full_timeout,
        full_max_tokens,
        hedge_delay_seconds,
    )
    fast_lane_runtime_overrides = {
        fast_primary_lane: {"timeout": fast_primary_timeout, "max_tokens": fast_primary_max_tokens},
        fast_secondary_lane: {"timeout": fast_secondary_timeout, "max_tokens": fast_secondary_max_tokens},
    }
    full_lane_runtime_overrides = {
        full_primary_lane: {"timeout": full_primary_timeout, "max_tokens": full_primary_max_tokens},
        full_secondary_lane: {"timeout": full_secondary_timeout, "max_tokens": full_secondary_max_tokens},
    }

    if debug and runtime_profile:
        print(
            "⚙️ 问题运行时档位: "
            f"profile={runtime_profile.get('profile_name', '-')},"
            f"fast_mode={runtime_profile.get('fast_prompt_mode', runtime_profile.get('fast_output_mode', 'full'))},"
            f"full_mode={runtime_profile.get('full_prompt_mode', 'full')},"
            f"fast_hedge={'on' if bool(runtime_profile.get('fast_hedged_enabled', fast_hedged_enabled)) else 'off'},"
            f"full_hedge={'on' if bool(runtime_profile.get('full_hedged_enabled', full_hedged_enabled)) else 'off'},"
            f"fast_lanes={fast_primary_lane}({fast_primary_timeout}s/{fast_primary_max_tokens})->{fast_secondary_lane}({fast_secondary_timeout}s/{fast_secondary_max_tokens}),"
            f"full_lanes={full_primary_lane}({full_primary_timeout}s/{full_primary_max_tokens})->{full_secondary_lane}({full_secondary_timeout}s/{full_secondary_max_tokens}),"
            f"reason={runtime_profile.get('selection_reason', '-') or '-'}"
        )

    fast_skip_reason = ""
    if effective_fast_allowed:
        fast_skip_reason = _get_question_fast_skip_reason(
            effective_fast_prompt,
            truncated_docs=fast_truncated_docs if fast_truncated_docs is not None else truncated_docs,
            prompt_max_chars=runtime_profile.get("fast_prompt_max_chars"),
            allow_compacted_docs=bool(runtime_profile.get("fast_allow_compacted_docs", False)),
        )

    if effective_fast_allowed and not fast_skip_reason:
        fast_response, fast_lane, fast_meta = _call_question_with_optional_hedge(
            effective_fast_prompt,
            max_tokens=fast_primary_max_tokens,
            call_type=f"{base_call_type}_fast",
            truncated_docs=fast_truncated_docs if fast_truncated_docs is not None else truncated_docs,
            timeout=fast_primary_timeout,
            retry_on_timeout=False,
            debug=debug,
            primary_lane=fast_primary_lane,
            secondary_lane=fast_secondary_lane,
            hedged_enabled=fast_hedged_enabled,
            hedge_delay_seconds=fast_hedge_delay_seconds,
            lane_profile_name=str(fast_lane_meta.get("strategy_key", "") or ""),
            lane_runtime_overrides=fast_lane_runtime_overrides,
            lane_model_overrides=runtime_profile.get("lane_model_overrides", {}) or {},
        )
        if fast_response:
            fast_result = normalize_generated_question_result(
                parse_question_response(fast_response, debug=debug),
                fallback_contract=runtime_profile,
            )
            if fast_result:
                fast_result = _annotate_question_result(fast_result, fast_meta, fallback_triggered=False)
                _record_question_fast_outcome(True, lane=fast_lane, reason="ok")
                return fast_response, fast_result, f"fast:{fast_lane}"
            _record_question_fast_outcome(False, lane=fast_lane, reason="parse_failed")
            if debug:
                response_length = int(fast_meta.get("response_length", len(fast_response)) or len(fast_response))
                print(f"⚠️ 快档响应解析失败: lane={fast_lane}, len={response_length}，回退全量档重试")
        else:
            _record_question_fast_outcome(False, lane=fast_lane, reason=_format_question_tier_attempts_for_log(fast_meta))
            if debug:
                print(f"⚠️ 快档未命中，原因: {_format_question_tier_attempts_for_log(fast_meta)}，回退全量档重试")
    elif debug and effective_fast_allowed:
        print(f"ℹ️ 跳过快档：{_describe_question_fast_skip_reason(fast_skip_reason)}，直接走全量竞速")

    full_response, full_lane, full_meta = _call_question_with_optional_hedge(
        prompt,
        max_tokens=full_primary_max_tokens,
        call_type=base_call_type,
        truncated_docs=truncated_docs,
        timeout=full_primary_timeout,
        retry_on_timeout=True,
        debug=debug,
        primary_lane=full_primary_lane,
        secondary_lane=full_secondary_lane,
        hedged_enabled=full_hedged_enabled,
        hedge_delay_seconds=full_hedge_delay_seconds,
        lane_profile_name=str(full_lane_meta.get("strategy_key", "") or ""),
        lane_runtime_overrides=full_lane_runtime_overrides,
        lane_model_overrides=runtime_profile.get("lane_model_overrides", {}) or {},
    )
    full_result = normalize_generated_question_result(
        parse_question_response(full_response, debug=debug),
        fallback_contract=runtime_profile,
    ) if full_response else None
    if full_result:
        full_result = _annotate_question_result(full_result, full_meta, fallback_triggered=False)

    should_try_fallback = (
        fallback_enabled
        and not bool(full_hedged_enabled)
        and full_primary_lane != full_secondary_lane
        and not full_result
    )
    if should_try_fallback:
        if debug:
            print(f"↪️ 主通道未稳定产出，切换备用通道补发: {full_primary_lane} -> {full_secondary_lane}")
        fallback_response, fallback_lane, fallback_meta = _call_question_with_optional_hedge(
            prompt,
            max_tokens=full_secondary_max_tokens,
            call_type=f"{base_call_type}_fallback",
            truncated_docs=truncated_docs,
            timeout=full_secondary_timeout,
            retry_on_timeout=True,
            debug=debug,
            primary_lane=full_secondary_lane,
            secondary_lane=full_secondary_lane,
            hedged_enabled=False,
            hedge_delay_seconds=full_hedge_delay_seconds,
            lane_profile_name=str(full_lane_meta.get("strategy_key", "") or ""),
            lane_runtime_overrides=full_lane_runtime_overrides,
            lane_model_overrides=runtime_profile.get("lane_model_overrides", {}) or {},
        )
        fallback_result = normalize_generated_question_result(
            parse_question_response(fallback_response, debug=debug),
            fallback_contract=runtime_profile,
        ) if fallback_response else None
        if fallback_result:
            fallback_meta = dict(fallback_meta or {})
            primary_attempts = list((full_meta or {}).get("attempts", []) if isinstance((full_meta or {}).get("attempts", []), list) else [])
            fallback_attempts = list(fallback_meta.get("attempts", []) if isinstance(fallback_meta.get("attempts", []), list) else [])
            fallback_meta["attempts"] = primary_attempts + fallback_attempts
            fallback_result = _annotate_question_result(
                fallback_result,
                fallback_meta,
                fallback_triggered=True,
                hedge_triggered_override=False,
            )
            return fallback_response, fallback_result, f"full_fallback:{fallback_lane}"

    if debug and not full_response:
        print(f"⚠️ 全量档未命中，原因: {_format_question_tier_attempts_for_log(full_meta)}")
    elif debug and full_response and not full_result:
        response_length = int(full_meta.get("response_length", len(full_response)) or len(full_response))
        print(f"⚠️ 全量档响应解析失败: lane={full_lane}, len={response_length}")
    return full_response, full_result, f"full:{full_lane}"
