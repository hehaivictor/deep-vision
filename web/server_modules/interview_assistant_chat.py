import json
import re
import uuid
from typing import Any, Callable, Optional


ASSISTANT_CHAT_MAX_USER_MESSAGE_CHARS = 1000
ASSISTANT_CHAT_MAX_ASSISTANT_MESSAGE_CHARS = 2000
ASSISTANT_CHAT_MAX_CLIENT_MESSAGES = 8
ASSISTANT_CHAT_MAX_STORED_MESSAGES_PER_QUESTION = 20
ASSISTANT_CHAT_MAX_OPTIONS = 8
ASSISTANT_CHAT_MAX_OPTION_CHARS = 200
ASSISTANT_CHAT_MAX_CONTEXT_DOCS = 2
ASSISTANT_CHAT_REFERENCE_BUDGET = 1400
ASSISTANT_CHAT_POSITIVE_OPTION_HINTS = (
    "建议",
    "推荐",
    "优先",
    "应选",
    "选择",
    "可选",
    "更匹配",
    "适合",
    "核心",
    "主要",
    "关联",
    "保障",
    "直接关系",
)
ASSISTANT_CHAT_NEGATIVE_OPTION_HINTS = (
    "不建议",
    "不优先",
    "不需要",
    "无需",
    "不如",
    "不是",
    "后续",
    "较低",
    "容许",
    "侧重",
)
ASSISTANT_CHAT_CHINESE_INDEXES = {
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
}


def _clip_text(value: object, limit: int, *, collapse_whitespace: bool = True) -> str:
    text = str(value or "")
    if collapse_whitespace:
        text = re.sub(r"\s+", " ", text).strip()
    else:
        text = text.strip()
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    if limit <= 3:
        return text[:limit]
    return text[: limit - 3].rstrip() + "..."


def _normalize_string_list(
    value: object,
    *,
    max_items: int,
    max_chars: int,
    field_name: str,
    allow_empty: bool = True,
) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{field_name}必须是列表")
    if len(value) > max_items:
        raise ValueError(f"{field_name}最多支持{max_items}项")

    normalized: list[str] = []
    seen = set()
    for item in value:
        text = _clip_text(item, max_chars)
        if not text:
            continue
        if text in seen:
            continue
        normalized.append(text)
        seen.add(text)
    if not normalized and not allow_empty:
        raise ValueError(f"{field_name}不能为空")
    return normalized


def _normalize_option_reference_text(value: object) -> str:
    text = str(value or "").strip()
    text = re.sub(r"[\s\"'“”‘’《》<>「」『』（）()【】\[\]]+", "", text)
    return text


def _parse_option_reference_index(token: object, option_count: int) -> Optional[int]:
    text = str(token or "").strip()
    if not text:
        return None
    if text.isdigit():
        value = int(text)
    else:
        value = ASSISTANT_CHAT_CHINESE_INDEXES.get(text)
    if not value or value < 1 or value > option_count:
        return None
    return value - 1


def _extract_option_reference_indexes(text: object, option_count: int) -> list[int]:
    source = str(text or "")
    if not source or option_count <= 0:
        return []

    indexes: list[int] = []
    seen = set()
    patterns = [
        r"(?:选项|第)\s*([一二两三四五六七八\d]+)\s*(?:项|个)?",
        r"(?<![A-Za-z0-9])([1-8])\s*[.、)]",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, source):
            parsed = _parse_option_reference_index(match.group(1), option_count)
            if parsed is None or parsed in seen:
                continue
            indexes.append(parsed)
            seen.add(parsed)
    return indexes


def _append_unique_option(target: list[str], option: str, seen: set[str]) -> None:
    normalized = str(option or "").strip()
    if not normalized or normalized in seen:
        return
    target.append(normalized)
    seen.add(normalized)


def _map_option_references_to_options(raw_items: list[str], options: list[str]) -> list[str]:
    if not raw_items or not options:
        return []
    normalized_option_lookup = {
        _normalize_option_reference_text(option): option
        for option in options
        if _normalize_option_reference_text(option)
    }
    selected: list[str] = []
    seen = set()
    for raw_item in raw_items:
        text = str(raw_item or "").strip()
        if text in options:
            _append_unique_option(selected, text, seen)
            continue
        mapped = normalized_option_lookup.get(_normalize_option_reference_text(text))
        if mapped:
            _append_unique_option(selected, mapped, seen)
            continue
        for index in _extract_option_reference_indexes(text, len(options)):
            _append_unique_option(selected, options[index], seen)
    return selected


def _candidate_option_hint_segments(text: object) -> list[str]:
    source = str(text or "")
    if not source:
        return []
    segments = [
        segment.strip()
        for segment in re.split(r"[\n。！？!?；;]+", source)
        if segment.strip()
    ]
    candidates = []
    for segment in segments:
        if not any(hint in segment for hint in ASSISTANT_CHAT_POSITIVE_OPTION_HINTS):
            continue
        if any(hint in segment for hint in ASSISTANT_CHAT_NEGATIVE_OPTION_HINTS):
            continue
        candidates.append(segment)
    return candidates


def _infer_options_from_suggestion_texts(texts: list[object], options: list[str]) -> list[str]:
    if not texts or not options:
        return []
    selected: list[str] = []
    seen = set()
    normalized_options = [
        (option, _normalize_option_reference_text(option))
        for option in options
        if str(option or "").strip()
    ]
    for text in texts:
        for segment in _candidate_option_hint_segments(text):
            normalized_segment = _normalize_option_reference_text(segment)
            for option, normalized_option in normalized_options:
                if normalized_option and normalized_option in normalized_segment:
                    _append_unique_option(selected, option, seen)
            for index in _extract_option_reference_indexes(segment, len(options)):
                _append_unique_option(selected, options[index], seen)
    return selected


def build_interview_assistant_question_fingerprint(
    *,
    dimension: str,
    question: str,
    options: Optional[list[str]] = None,
    answer_mode: str = "",
) -> str:
    source = json.dumps(
        {
            "dimension": str(dimension or "").strip(),
            "question": str(question or "").strip(),
            "options": [str(item or "").strip() for item in (options or [])],
            "answer_mode": str(answer_mode or "").strip(),
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    hash_value = 2166136261
    for char in source:
        hash_value ^= ord(char)
        hash_value = (hash_value * 16777619) & 0xFFFFFFFF
    return f"q-{hash_value:08x}"


def normalize_interview_assistant_chat_payload(data: object, session: dict) -> dict:
    if not isinstance(data, dict):
        raise ValueError("无效的请求数据")

    dimensions = session.get("dimensions", {}) if isinstance(session, dict) else {}
    dimension = _clip_text(data.get("dimension"), 120)
    if not dimension or dimension not in dimensions:
        raise ValueError("无效的维度")

    question = _clip_text(data.get("question"), 1000)
    if not question:
        raise ValueError("问题不能为空")

    message = _clip_text(
        data.get("message"),
        ASSISTANT_CHAT_MAX_USER_MESSAGE_CHARS,
        collapse_whitespace=False,
    )
    if not message:
        raise ValueError("提问内容不能为空")

    options = _normalize_string_list(
        data.get("options", []),
        max_items=ASSISTANT_CHAT_MAX_OPTIONS,
        max_chars=ASSISTANT_CHAT_MAX_OPTION_CHARS,
        field_name="options",
    )
    selected_answers = _normalize_string_list(
        data.get("selected_answers", []),
        max_items=ASSISTANT_CHAT_MAX_OPTIONS,
        max_chars=ASSISTANT_CHAT_MAX_OPTION_CHARS,
        field_name="selected_answers",
    )
    if options:
        unknown_selected = [item for item in selected_answers if item not in options]
        if unknown_selected:
            raise ValueError("selected_answers包含无效选项")

    answer_mode = _clip_text(data.get("answer_mode"), 40).lower()
    if answer_mode not in {"pick_only", "pick_with_reason", "free_text"}:
        answer_mode = "pick_only"

    multi_select = data.get("multi_select", False)
    if not isinstance(multi_select, bool):
        raise ValueError("multi_select必须是布尔值")

    other_answer_text = _clip_text(
        data.get("other_answer_text"),
        ASSISTANT_CHAT_MAX_USER_MESSAGE_CHARS,
        collapse_whitespace=False,
    )

    client_messages = []
    raw_client_messages = data.get("client_messages", [])
    if raw_client_messages is None:
        raw_client_messages = []
    if not isinstance(raw_client_messages, list):
        raise ValueError("client_messages必须是列表")
    for item in raw_client_messages[-ASSISTANT_CHAT_MAX_CLIENT_MESSAGES:]:
        if not isinstance(item, dict):
            continue
        role = _clip_text(item.get("role"), 20).lower()
        if role not in {"user", "assistant"}:
            continue
        content = _clip_text(item.get("content"), 800, collapse_whitespace=False)
        if not content:
            continue
        client_messages.append({"role": role, "content": content})

    fingerprint = _clip_text(data.get("question_fingerprint"), 160)
    if not fingerprint:
        fingerprint = build_interview_assistant_question_fingerprint(
            dimension=dimension,
            question=question,
            options=options,
            answer_mode=answer_mode,
        )

    return {
        "dimension": dimension,
        "question": question,
        "options": options,
        "multi_select": multi_select,
        "answer_mode": answer_mode,
        "selected_answers": selected_answers,
        "other_answer_text": other_answer_text,
        "message": message,
        "question_fingerprint": fingerprint,
        "client_messages": client_messages,
    }


def _format_options(options: list[str]) -> str:
    if not options:
        return "本题无固定选项，用户需要自由补充。"
    return "\n".join(f"{index}. {option}" for index, option in enumerate(options, 1))


def _format_recent_interview_logs(session: dict, dimension_info: dict) -> str:
    logs = session.get("interview_log", []) if isinstance(session, dict) else []
    if not isinstance(logs, list) or not logs:
        return "暂无正式访谈记录。"
    parts = []
    recent_logs = [item for item in logs if isinstance(item, dict)][-5:]
    base_index = max(0, len(logs) - len(recent_logs))
    for offset, log in enumerate(recent_logs, 1):
        dim_key = str(log.get("dimension") or "")
        dim_name = (dimension_info.get(dim_key, {}) or {}).get("name") or dim_key or "未知维度"
        follow = " [追问]" if log.get("is_follow_up") else ""
        parts.append(
            f"Q{base_index + offset}（{dim_name}{follow}）: "
            f"{_clip_text(log.get('question'), 120)}\n"
            f"A: {_clip_text(log.get('answer'), 180)}"
        )
    return "\n".join(parts) if parts else "暂无正式访谈记录。"


def _format_client_messages(messages: list[dict]) -> str:
    if not messages:
        return "本题暂无历史辅助聊天。"
    parts = []
    for item in messages[-ASSISTANT_CHAT_MAX_CLIENT_MESSAGES:]:
        role = "用户" if item.get("role") == "user" else "助手"
        parts.append(f"{role}: {_clip_text(item.get('content'), 500, collapse_whitespace=False)}")
    return "\n".join(parts)


def _collect_reference_context(
    session: dict,
    payload: dict,
    *,
    select_reference_material_context: Optional[Callable[..., tuple[str, dict]]] = None,
    chunk_limit: int = 0,
) -> str:
    materials = session.get("reference_materials", []) if isinstance(session, dict) else []
    if not materials:
        materials = (session.get("reference_docs", []) or []) + (session.get("research_docs", []) or [])
    if not isinstance(materials, list) or not materials:
        return "暂无可用参考资料。"

    query_text = " ".join([
        str(session.get("topic") or ""),
        payload.get("dimension", ""),
        payload.get("question", ""),
        payload.get("message", ""),
        " ".join(payload.get("options", []) or []),
    ])
    parts = []
    remaining = ASSISTANT_CHAT_REFERENCE_BUDGET
    for doc in materials[:ASSISTANT_CHAT_MAX_CONTEXT_DOCS]:
        if not isinstance(doc, dict):
            continue
        if doc.get("context_ready") is False:
            continue
        name = _clip_text(doc.get("name") or "参考资料", 60)
        selected = ""
        if callable(select_reference_material_context):
            try:
                selected, _meta = select_reference_material_context(
                    doc,
                    query_text=query_text,
                    max_chars=max(240, remaining),
                    chunk_limit=chunk_limit,
                )
            except Exception:
                selected = ""
        if not selected:
            selected = str(doc.get("content") or "")[: max(240, remaining)]
        selected = _clip_text(selected, max(0, remaining), collapse_whitespace=False)
        if not selected:
            continue
        parts.append(f"### {name}\n{selected}")
        remaining -= len(selected)
        if remaining <= 120:
            break
    return "\n\n".join(parts) if parts else "暂无可用参考资料。"


def build_interview_assistant_prompt(
    session: dict,
    payload: dict,
    *,
    get_dimension_info_for_session: Optional[Callable[[dict], dict]] = None,
    select_reference_material_context: Optional[Callable[..., tuple[str, dict]]] = None,
    reference_context_chunk_limit: int = 0,
) -> str:
    dimension_info = get_dimension_info_for_session(session) if callable(get_dimension_info_for_session) else {}
    current_dimension = (dimension_info.get(payload.get("dimension"), {}) or {})
    current_dimension_name = current_dimension.get("name") or payload.get("dimension")
    current_dimension_description = current_dimension.get("description") or ""
    current_key_aspects = current_dimension.get("key_aspects", []) or []
    recent_logs = _format_recent_interview_logs(session, dimension_info)
    reference_context = _collect_reference_context(
        session,
        payload,
        select_reference_material_context=select_reference_material_context,
        chunk_limit=reference_context_chunk_limit,
    )
    client_messages = _format_client_messages(payload.get("client_messages", []))

    return f"""你是 DeepVision 访谈页里的题内助手。你的任务是帮助用户理解当前问题和选项，便于用户自己做选择。

必须遵守：
1. 只解释当前题、当前选项和相关上下文，不要替用户直接提交答案。
2. 不要声称辅助聊天已进入正式访谈记录；只有用户采纳并点击下一题后才会成为正式证据。
3. 如果上下文不足，明确说明不确定性，并给出用户可确认的问题。
4. 语言简洁、专业、可操作，避免长篇理论。
5. 严格输出 JSON 对象，不要 markdown 代码块。

## 会话背景
主题：{_clip_text(session.get('topic'), 160)}
描述：{_clip_text(session.get('description'), 360)}

## 当前维度
维度：{current_dimension_name}
说明：{_clip_text(current_dimension_description, 220)}
关键方面：{"、".join(_clip_text(item, 40) for item in current_key_aspects[:8]) or "未配置"}

## 当前问题
问题：{payload.get('question')}
题型：{"多选" if payload.get("multi_select") else "单选"}
回答模式：{payload.get("answer_mode")}
选项：
{_format_options(payload.get("options", []))}

用户当前已选：{"、".join(payload.get("selected_answers", []) or []) or "暂无"}
用户当前自由输入：{payload.get("other_answer_text") or "暂无"}

## 最近正式访谈记录
{recent_logs}

## 参考资料片段
{reference_context}

## 本题辅助聊天历史
{client_messages}

## 用户本次问题
{payload.get("message")}

## 输出 JSON
{{
  "content": "给用户看的解释，建议 2-5 句话；可用短列表，但必须是字符串",
  "suggested_answer": {{
    "selected_options": ["可预填的已有选项，必须来自当前选项；没有则为空数组"],
    "custom_text": "需要填入其他/自由输入时使用；没有则为空字符串",
    "rationale_text": "可作为补充说明的判断依据；没有则为空字符串"
  }}
}}

如果不适合给预填建议，请将 suggested_answer 设为 null。"""


def _extract_json_object(text: str) -> Optional[dict]:
    raw = str(text or "").strip()
    if not raw:
        return None
    try:
        payload = json.loads(raw)
        return payload if isinstance(payload, dict) else None
    except Exception:
        pass

    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        try:
            payload = json.loads(raw[start: end + 1])
            return payload if isinstance(payload, dict) else None
        except Exception:
            return None
    return None


def normalize_interview_assistant_suggested_answer(
    raw_value: object,
    options: list[str],
    *,
    content_text: str = "",
) -> Optional[dict]:
    if raw_value is None:
        return None
    if not isinstance(raw_value, dict):
        return None

    option_set = set(options or [])
    try:
        selected_options = _normalize_string_list(
            raw_value.get("selected_options", []),
            max_items=ASSISTANT_CHAT_MAX_OPTIONS,
            max_chars=ASSISTANT_CHAT_MAX_OPTION_CHARS,
            field_name="selected_options",
        )
    except ValueError:
        selected_options = []
    custom_text = _clip_text(
        raw_value.get("custom_text"),
        ASSISTANT_CHAT_MAX_USER_MESSAGE_CHARS,
        collapse_whitespace=False,
    )
    rationale_text = _clip_text(
        raw_value.get("rationale_text"),
        ASSISTANT_CHAT_MAX_USER_MESSAGE_CHARS,
        collapse_whitespace=False,
    )
    selected_options = _map_option_references_to_options(selected_options, options)
    if not selected_options:
        selected_options = _infer_options_from_suggestion_texts(
            [rationale_text, custom_text, content_text],
            options,
        )
    if option_set:
        selected_options = [item for item in selected_options if item in option_set]

    if not selected_options and not custom_text and not rationale_text:
        return None
    return {
        "selected_options": selected_options,
        "custom_text": custom_text,
        "rationale_text": rationale_text,
    }


def normalize_interview_assistant_model_response(raw_text: str, payload: dict) -> dict:
    parsed = _extract_json_object(raw_text)
    if isinstance(parsed, dict):
        content = _clip_text(
            parsed.get("content"),
            ASSISTANT_CHAT_MAX_ASSISTANT_MESSAGE_CHARS,
            collapse_whitespace=False,
        )
        suggested_answer = normalize_interview_assistant_suggested_answer(
            parsed.get("suggested_answer"),
            payload.get("options", []),
            content_text=content,
        )
        if content:
            return {
                "content": content,
                "suggested_answer": suggested_answer,
            }

    return {
        "content": _clip_text(
            raw_text,
            ASSISTANT_CHAT_MAX_ASSISTANT_MESSAGE_CHARS,
            collapse_whitespace=False,
        ),
        "suggested_answer": None,
    }


def generate_interview_assistant_chat_reply(
    session: dict,
    payload: dict,
    *,
    call_ai: Callable[..., Any],
    now_iso: str,
    get_dimension_info_for_session: Optional[Callable[[dict], dict]] = None,
    select_reference_material_context: Optional[Callable[..., tuple[str, dict]]] = None,
    reference_context_chunk_limit: int = 0,
) -> dict:
    prompt = build_interview_assistant_prompt(
        session,
        payload,
        get_dimension_info_for_session=get_dimension_info_for_session,
        select_reference_material_context=select_reference_material_context,
        reference_context_chunk_limit=reference_context_chunk_limit,
    )
    raw_result = call_ai(
        prompt,
        max_tokens=900,
        call_type="summary_interview_chat",
        timeout=30,
        return_meta=True,
    )
    if isinstance(raw_result, tuple):
        raw_text = raw_result[0]
    else:
        raw_text = raw_result
    if not raw_text:
        raise RuntimeError("AI 助手暂时不可用")

    normalized = normalize_interview_assistant_model_response(str(raw_text), payload)
    if not normalized.get("content"):
        raise RuntimeError("AI 助手暂时不可用")

    return {
        "message_id": f"iac-{uuid.uuid4().hex[:16]}",
        "content": normalized["content"],
        "suggested_answer": normalized.get("suggested_answer"),
        "created_at": now_iso,
        "question_fingerprint": payload.get("question_fingerprint", ""),
    }


def append_interview_assistant_chat_exchange(
    session: dict,
    payload: dict,
    assistant_reply: dict,
    *,
    now_iso: str,
) -> None:
    store = session.get("interview_assistant_chats")
    if not isinstance(store, dict):
        store = {}
        session["interview_assistant_chats"] = store

    fingerprint = str(payload.get("question_fingerprint") or "").strip()
    if not fingerprint:
        return

    thread = store.get(fingerprint)
    if not isinstance(thread, dict):
        thread = {}
    messages = thread.get("messages")
    if not isinstance(messages, list):
        messages = []

    user_message_id = f"iac-user-{uuid.uuid4().hex[:16]}"
    messages.append({
        "message_id": user_message_id,
        "role": "user",
        "content": payload.get("message", ""),
        "created_at": now_iso,
        "question_fingerprint": fingerprint,
    })
    messages.append({
        "message_id": assistant_reply.get("message_id", ""),
        "role": "assistant",
        "content": assistant_reply.get("content", ""),
        "suggested_answer": assistant_reply.get("suggested_answer"),
        "created_at": assistant_reply.get("created_at") or now_iso,
        "question_fingerprint": fingerprint,
    })

    thread.update({
        "question_fingerprint": fingerprint,
        "dimension": payload.get("dimension", ""),
        "question": payload.get("question", ""),
        "options": payload.get("options", []),
        "answer_mode": payload.get("answer_mode", ""),
        "updated_at": now_iso,
        "messages": messages[-ASSISTANT_CHAT_MAX_STORED_MESSAGES_PER_QUESTION:],
    })
    store[fingerprint] = thread
