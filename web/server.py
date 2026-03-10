#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["flask", "flask-cors", "anthropic", "requests", "reportlab", "pillow"]
# ///
"""
Deep Vision Web Server - AI 驱动版本

完整实现 deep-vision 技能的所有功能：
- 动态生成问题和选项（基于上下文和行业知识）
- 智能追问（识别表面需求，挖掘本质）
- 冲突检测（检测回答与参考文档的冲突）
- 知识增强（专业领域信息融入选项）
- 生成专业访谈报告
"""

import base64
import copy
import atexit
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager
import hashlib
import html
import json
import os
import queue
import re
import secrets
import sqlite3
import threading
import time as _time
import requests
from functools import wraps
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from typing import Optional
from urllib.parse import quote, unquote, urlparse, parse_qsl, urlencode, urlunparse

from flask import Flask, jsonify, request, send_from_directory, redirect, session, send_file, make_response
from flask_cors import CORS
from werkzeug.security import generate_password_hash
from werkzeug.serving import WSGIRequestHandler
from werkzeug.utils import secure_filename


def _parse_env_assignment(line: str) -> Optional[tuple[str, str]]:
    text = str(line or "").strip()
    if not text or text.startswith("#"):
        return None

    if text.startswith("export "):
        text = text[len("export "):].strip()

    match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", text)
    if not match:
        return None

    key = match.group(1).strip()
    raw_value = match.group(2).strip()

    if not raw_value:
        return key, ""

    if (raw_value.startswith('"') and raw_value.endswith('"')) or (raw_value.startswith("'") and raw_value.endswith("'")):
        return key, raw_value[1:-1]

    # 非引号值允许行尾注释：KEY=value # comment
    if " #" in raw_value:
        raw_value = raw_value.split(" #", 1)[0].rstrip()
    return key, raw_value


def load_env_files() -> None:
    """加载 .env 文件到 os.environ（默认不覆盖已存在环境变量）。"""
    current_dir = Path(__file__).resolve().parent
    project_dir = current_dir.parent
    explicit_env_file = os.environ.get("DEEPVISION_ENV_FILE", "").strip()
    override_existing = str(os.environ.get("DEEPVISION_ENV_OVERRIDE", "")).strip().lower() in {"1", "true", "yes", "on", "y"}

    candidates: list[Path] = []
    if explicit_env_file:
        explicit_path = Path(explicit_env_file).expanduser()
        if not explicit_path.is_absolute():
            explicit_path = (project_dir / explicit_path).resolve()
        candidates.append(explicit_path)
    else:
        candidates.extend([
            current_dir / ".env",
            project_dir / ".env",
        ])

    loaded_any = False
    for env_path in candidates:
        if not env_path.exists() or not env_path.is_file():
            continue

        try:
            for raw_line in env_path.read_text(encoding="utf-8").splitlines():
                parsed = _parse_env_assignment(raw_line)
                if not parsed:
                    continue
                key, value = parsed
                if not override_existing and key in os.environ:
                    continue
                os.environ[key] = value
            loaded_any = True
            print(f"✅ 已加载环境变量文件: {env_path}")
        except Exception as exc:
            print(f"⚠️  读取环境变量文件失败: {env_path}, 错误: {exc}")

    if explicit_env_file and not loaded_any:
        print(f"⚠️  指定的环境变量文件不存在或不可读: {explicit_env_file}")


load_env_files()

try:
    import config as runtime_config
    print("✅ 配置文件加载成功")
except Exception:
    runtime_config = None
    print("⚠️  未找到 config.py，使用默认配置")
    print("   请复制 config.example.py 为 config.py 并填入实际配置")

try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False
    print("警告: anthropic 库未安装，将无法使用 AI 功能")

try:
    from jdcloud_sdk.core.credential import Credential as JdCredential
    from jdcloud_sdk.core.config import Config as JdConfig
    from jdcloud_sdk.services.sms.client.SmsClient import SmsClient as JdSmsClient
    from jdcloud_sdk.services.sms.apis.BatchSendRequest import BatchSendRequest as JdBatchSendRequest
    JD_SMS_SDK_AVAILABLE = True
except Exception:
    JdCredential = None
    JdConfig = None
    JdSmsClient = None
    JdBatchSendRequest = None
    JD_SMS_SDK_AVAILABLE = False

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfgen import canvas as report_canvas
    REPORTLAB_AVAILABLE = True
except Exception:
    A4 = None
    mm = None
    ImageReader = None
    pdfmetrics = None
    UnicodeCIDFont = None
    report_canvas = None
    REPORTLAB_AVAILABLE = False

try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except Exception:
    Image = None
    ImageDraw = None
    ImageFont = None
    PIL_AVAILABLE = False

# ============ 配置读取工具 ============
def _cfg_get(name: str, default):
    # 生产环境可通过 DEEPVISION_ 前缀变量覆盖（优先级最高）
    env_prefixed_val = os.environ.get(f"DEEPVISION_{name}")
    if env_prefixed_val is not None:
        return env_prefixed_val

    # 兼容同名环境变量（次优先）
    env_val = os.environ.get(name)
    if env_val is not None:
        return env_val

    # 本地开发默认从 config.py 读取
    if runtime_config and hasattr(runtime_config, name):
        return getattr(runtime_config, name)
    return default


def _cfg_int(name: str, default: int) -> int:
    try:
        return int(_cfg_get(name, default))
    except Exception:
        return default


def _cfg_float(name: str, default: float) -> float:
    try:
        return float(_cfg_get(name, default))
    except Exception:
        return default


def _cfg_bool(name: str, default: bool) -> bool:
    value = _cfg_get(name, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        v = value.strip().lower()
        if v in {"1", "true", "yes", "on", "y"}:
            return True
        if v in {"0", "false", "no", "off", "n"}:
            return False
    return default


def _cfg_text(name: str, default: str = "") -> str:
    return str(_cfg_get(name, default) or "").strip()


def summarize_error_for_log(error: object, limit: int = 240) -> str:
    """压缩异常文本，避免在日志中输出整段 HTML/长响应体。"""
    text = str(error or "").strip()
    if not text:
        return "未知错误"

    # 去除 HTML 标签（例如网关 504 的整页 HTML 错误页）
    stripped = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", text)
    stripped = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", stripped)
    stripped = re.sub(r"(?is)<[^>]+>", " ", stripped)
    stripped = re.sub(r"\s+", " ", stripped).strip()
    if stripped:
        text = stripped

    limit = max(32, int(limit or 240))
    if len(text) > limit:
        text = text[: limit - 1] + "…"

    return text


def _cfg_text_list(name: str, default: list[str]) -> list[str]:
    value = _cfg_get(name, default)
    if isinstance(value, (list, tuple, set)):
        cleaned = [str(item).strip() for item in value if str(item).strip()]
        return cleaned or list(default)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return list(default)
        if text.startswith("[") and text.endswith("]"):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    cleaned = [str(item).strip() for item in parsed if str(item).strip()]
                    return cleaned or list(default)
            except Exception:
                pass
        cleaned = [item.strip() for item in text.split(",") if item.strip()]
        return cleaned or list(default)
    return list(default)


def _first_non_empty(*values: str) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _is_bearer_gateway_url(url: str) -> bool:
    """判断网关是否默认使用 Authorization: Bearer。"""
    lowered = str(url or "").strip().lower()
    if not lowered:
        return False
    # aicodemirror 代理当前要求 Bearer 鉴权
    return "aicodemirror.com" in lowered


def _guess_bearer_auth_default() -> bool:
    """在未显式配置鉴权开关时，基于网关地址推断默认鉴权模式。"""
    candidates = [
        _cfg_text("QUESTION_BASE_URL", ""),
        _cfg_text("REPORT_BASE_URL", ""),
        _cfg_text("ANTHROPIC_BASE_URL", str(ANTHROPIC_BASE_URL or "").strip()),
    ]
    return any(_is_bearer_gateway_url(url) for url in candidates if str(url or "").strip())


# ============ 配置中心（集中管理） ============
# 向后兼容：保留历史函数名，避免潜在外部引用断裂
def _runtime_cfg(name: str, default):
    return _cfg_get(name, default)


def _runtime_cfg_int(name: str, default: int) -> int:
    return _cfg_int(name, default)


def _runtime_cfg_float(name: str, default: float) -> float:
    return _cfg_float(name, default)


def _runtime_cfg_bool(name: str, default: bool) -> bool:
    return _cfg_bool(name, default)


# 基础配置
ANTHROPIC_API_KEY = _cfg_text("ANTHROPIC_API_KEY", "")
ANTHROPIC_BASE_URL = _cfg_text("ANTHROPIC_BASE_URL", "")
MODEL_NAME = _cfg_text("MODEL_NAME", "")
MAX_TOKENS_DEFAULT = _cfg_int("MAX_TOKENS_DEFAULT", 5000)
MAX_TOKENS_DEFAULT = max(1, MAX_TOKENS_DEFAULT)
MAX_TOKENS_QUESTION = _cfg_int("MAX_TOKENS_QUESTION", 2000)
MAX_TOKENS_QUESTION = max(1, MAX_TOKENS_QUESTION)
MAX_TOKENS_REPORT = _cfg_int("MAX_TOKENS_REPORT", 10000)
MAX_TOKENS_REPORT = max(1, MAX_TOKENS_REPORT)
SERVER_HOST = _cfg_text("SERVER_HOST", "0.0.0.0") or "0.0.0.0"
SERVER_PORT = _cfg_int("SERVER_PORT", 5001)
SERVER_PORT = max(1, SERVER_PORT)
DEBUG_MODE = _cfg_bool("DEBUG_MODE", True)
ENABLE_AI = _cfg_bool("ENABLE_AI", True)
ENABLE_DEBUG_LOG = _cfg_bool("ENABLE_DEBUG_LOG", True)
SUPPRESS_STATUS_POLL_ACCESS_LOG = _cfg_bool("SUPPRESS_STATUS_POLL_ACCESS_LOG", True)
FOCUS_GENERATION_ACCESS_LOG = _cfg_bool("FOCUS_GENERATION_ACCESS_LOG", True)
ENABLE_WEB_SEARCH = _cfg_bool("ENABLE_WEB_SEARCH", False)
ZHIPU_API_KEY = _cfg_text("ZHIPU_API_KEY", "")
ZHIPU_SEARCH_ENGINE = _cfg_text("ZHIPU_SEARCH_ENGINE", "search_pro") or "search_pro"
SEARCH_MAX_RESULTS = _cfg_int("SEARCH_MAX_RESULTS", 3)
SEARCH_MAX_RESULTS = max(1, SEARCH_MAX_RESULTS)
SEARCH_TIMEOUT = _cfg_int("SEARCH_TIMEOUT", 10)
SEARCH_TIMEOUT = max(1, SEARCH_TIMEOUT)
VISION_MODEL_NAME = _cfg_text("VISION_MODEL_NAME", "")
VISION_API_URL = _cfg_text("VISION_API_URL", "")
ENABLE_VISION = _cfg_bool("ENABLE_VISION", True)
MAX_IMAGE_SIZE_MB = _cfg_int("MAX_IMAGE_SIZE_MB", 10)
MAX_IMAGE_SIZE_MB = max(1, MAX_IMAGE_SIZE_MB)
SUPPORTED_IMAGE_TYPES = _cfg_text_list("SUPPORTED_IMAGE_TYPES", [".jpg", ".jpeg", ".png", ".gif", ".webp"])
REFLY_API_URL = _cfg_text("REFLY_API_URL", "")
REFLY_API_KEY = _cfg_text("REFLY_API_KEY", "")
REFLY_WORKFLOW_ID = _cfg_text("REFLY_WORKFLOW_ID", "")
REFLY_INPUT_FIELD = _cfg_text("REFLY_INPUT_FIELD", "report") or "report"
REFLY_FILES_FIELD = _cfg_text("REFLY_FILES_FIELD", "files") or "files"
REFLY_TIMEOUT = _cfg_int("REFLY_TIMEOUT", 30)
REFLY_TIMEOUT = max(1, REFLY_TIMEOUT)
REFLY_POLL_TIMEOUT = _cfg_int("REFLY_POLL_TIMEOUT", 600)
if REFLY_POLL_TIMEOUT < 30:
    REFLY_POLL_TIMEOUT = 30
REFLY_POLL_INTERVAL = _cfg_float("REFLY_POLL_INTERVAL", 2.0)
if REFLY_POLL_INTERVAL <= 0:
    REFLY_POLL_INTERVAL = 2.0

# 列表接口性能与并发保护配置
LIST_API_DEFAULT_PAGE_SIZE = _cfg_int("LIST_API_DEFAULT_PAGE_SIZE", 20)
if LIST_API_DEFAULT_PAGE_SIZE < 1:
    LIST_API_DEFAULT_PAGE_SIZE = 20

LIST_API_MAX_PAGE_SIZE = _cfg_int("LIST_API_MAX_PAGE_SIZE", 100)
if LIST_API_MAX_PAGE_SIZE < LIST_API_DEFAULT_PAGE_SIZE:
    LIST_API_MAX_PAGE_SIZE = LIST_API_DEFAULT_PAGE_SIZE

SESSIONS_LIST_MAX_INFLIGHT = _cfg_int("SESSIONS_LIST_MAX_INFLIGHT", 8)
if SESSIONS_LIST_MAX_INFLIGHT < 1:
    SESSIONS_LIST_MAX_INFLIGHT = 8

REPORTS_LIST_MAX_INFLIGHT = _cfg_int("REPORTS_LIST_MAX_INFLIGHT", 8)
if REPORTS_LIST_MAX_INFLIGHT < 1:
    REPORTS_LIST_MAX_INFLIGHT = 8

LIST_API_RETRY_AFTER_SECONDS = _cfg_int("LIST_API_RETRY_AFTER_SECONDS", 2)
if LIST_API_RETRY_AFTER_SECONDS < 1:
    LIST_API_RETRY_AFTER_SECONDS = 2

# 报告生成任务池与排队上限（并发优化）
REPORT_GENERATION_MAX_WORKERS = _cfg_int("REPORT_GENERATION_MAX_WORKERS", 2)
if REPORT_GENERATION_MAX_WORKERS < 1:
    REPORT_GENERATION_MAX_WORKERS = 2

REPORT_GENERATION_MAX_PENDING = _cfg_int("REPORT_GENERATION_MAX_PENDING", 16)
if REPORT_GENERATION_MAX_PENDING < REPORT_GENERATION_MAX_WORKERS:
    REPORT_GENERATION_MAX_PENDING = REPORT_GENERATION_MAX_WORKERS

REPORT_GENERATION_QUEUE_RETRY_AFTER_SECONDS = _cfg_int("REPORT_GENERATION_QUEUE_RETRY_AFTER_SECONDS", 3)
if REPORT_GENERATION_QUEUE_RETRY_AFTER_SECONDS < 1:
    REPORT_GENERATION_QUEUE_RETRY_AFTER_SECONDS = 3

# 模型路由配置：支持问题/报告分离，未配置时向后兼容 MODEL_NAME
_base_model_name = _cfg_text("MODEL_NAME", str(MODEL_NAME or "").strip())
QUESTION_MODEL_NAME = _cfg_text("QUESTION_MODEL_NAME", _base_model_name) or _base_model_name
REPORT_MODEL_NAME = _cfg_text("REPORT_MODEL_NAME", QUESTION_MODEL_NAME) or QUESTION_MODEL_NAME
SUMMARY_MODEL_NAME = _cfg_text("SUMMARY_MODEL_NAME", QUESTION_MODEL_NAME) or QUESTION_MODEL_NAME
SEARCH_DECISION_MODEL_NAME = _cfg_text("SEARCH_DECISION_MODEL_NAME", SUMMARY_MODEL_NAME) or SUMMARY_MODEL_NAME

# 鉴权路由配置：兼容 Anthropic x-api-key 与 Bearer Authorization 两种网关模式
# 未显式配置时，按网关地址自动推断（aicodemirror 默认 Bearer）。
_auto_use_bearer_auth = _guess_bearer_auth_default()
_global_use_bearer_auth = _cfg_bool("ANTHROPIC_USE_BEARER_AUTH", _auto_use_bearer_auth)
QUESTION_USE_BEARER_AUTH = _cfg_bool("QUESTION_USE_BEARER_AUTH", _global_use_bearer_auth)
REPORT_USE_BEARER_AUTH = _cfg_bool("REPORT_USE_BEARER_AUTH", QUESTION_USE_BEARER_AUTH)

# 网关路由配置：支持问题/报告分别使用不同 API Key 和 Base URL
_cfg_question_api_key = _first_non_empty(
    _cfg_text("QUESTION_API_KEY", ""),
    _cfg_text("QUESTION_ANTHROPIC_API_KEY", ""),
)
_cfg_question_base_url = _first_non_empty(
    _cfg_text("QUESTION_BASE_URL", ""),
    _cfg_text("QUESTION_ANTHROPIC_BASE_URL", ""),
)
_cfg_report_api_key = _first_non_empty(
    _cfg_text("REPORT_API_KEY", ""),
    _cfg_text("REPORT_ANTHROPIC_API_KEY", ""),
)
_cfg_report_base_url = _first_non_empty(
    _cfg_text("REPORT_BASE_URL", ""),
    _cfg_text("REPORT_ANTHROPIC_BASE_URL", ""),
)
_cfg_summary_api_key = _first_non_empty(
    _cfg_text("SUMMARY_API_KEY", ""),
    _cfg_text("SUMMARY_ANTHROPIC_API_KEY", ""),
)
_cfg_summary_base_url = _first_non_empty(
    _cfg_text("SUMMARY_BASE_URL", ""),
    _cfg_text("SUMMARY_ANTHROPIC_BASE_URL", ""),
)
_cfg_search_decision_api_key = _first_non_empty(
    _cfg_text("SEARCH_DECISION_API_KEY", ""),
    _cfg_text("SEARCH_DECISION_ANTHROPIC_API_KEY", ""),
)
_cfg_search_decision_base_url = _first_non_empty(
    _cfg_text("SEARCH_DECISION_BASE_URL", ""),
    _cfg_text("SEARCH_DECISION_ANTHROPIC_BASE_URL", ""),
)

QUESTION_API_KEY = _cfg_question_api_key or _cfg_text("ANTHROPIC_API_KEY", str(ANTHROPIC_API_KEY or "").strip())
QUESTION_BASE_URL = _cfg_question_base_url or _cfg_text("ANTHROPIC_BASE_URL", str(ANTHROPIC_BASE_URL or "").strip())
REPORT_API_KEY = _cfg_report_api_key or QUESTION_API_KEY
REPORT_BASE_URL = _cfg_report_base_url or QUESTION_BASE_URL
SUMMARY_API_KEY = _cfg_summary_api_key or REPORT_API_KEY
SUMMARY_BASE_URL = _cfg_summary_base_url or REPORT_BASE_URL
SEARCH_DECISION_API_KEY = _cfg_search_decision_api_key or SUMMARY_API_KEY
SEARCH_DECISION_BASE_URL = _cfg_search_decision_base_url or SUMMARY_BASE_URL

SUMMARY_USE_BEARER_AUTH = _cfg_bool("SUMMARY_USE_BEARER_AUTH", REPORT_USE_BEARER_AUTH)
SEARCH_DECISION_USE_BEARER_AUTH = _cfg_bool("SEARCH_DECISION_USE_BEARER_AUTH", SUMMARY_USE_BEARER_AUTH)

# 兼容历史代码中直接引用 MODEL_NAME 的位置：默认指向问题模型
MODEL_NAME = QUESTION_MODEL_NAME

# 访谈深度增强 V2 已升级为正式版（全模式固定启用）
DEEP_MODE_SKIP_FOLLOWUP_CONFIRM = _cfg_bool("DEEP_MODE_SKIP_FOLLOWUP_CONFIRM", True)

# 运行策略配置
CONTEXT_WINDOW_SIZE = _cfg_int("CONTEXT_WINDOW_SIZE", 5)  # 保留最近N条完整问答
SUMMARY_THRESHOLD = _cfg_int("SUMMARY_THRESHOLD", 8)      # 超过此数量时触发摘要生成
SUMMARY_UPDATE_DEBOUNCE_SECONDS = _cfg_int("SUMMARY_UPDATE_DEBOUNCE_SECONDS", 60)  # 摘要异步更新最小间隔（秒）
if SUMMARY_UPDATE_DEBOUNCE_SECONDS < 5:
    SUMMARY_UPDATE_DEBOUNCE_SECONDS = 5
SEARCH_DECISION_CACHE_TTL_SECONDS = _cfg_int("SEARCH_DECISION_CACHE_TTL_SECONDS", 600)  # 搜索决策缓存时间（秒）
if SEARCH_DECISION_CACHE_TTL_SECONDS < 0:
    SEARCH_DECISION_CACHE_TTL_SECONDS = 0
SEARCH_DECISION_CACHE_MAX_ENTRIES = _cfg_int("SEARCH_DECISION_CACHE_MAX_ENTRIES", 256)
if SEARCH_DECISION_CACHE_MAX_ENTRIES < 32:
    SEARCH_DECISION_CACHE_MAX_ENTRIES = 32
SEARCH_DECISION_INFLIGHT_WAIT_SECONDS = _cfg_float("SEARCH_DECISION_INFLIGHT_WAIT_SECONDS", 10.0)
if SEARCH_DECISION_INFLIGHT_WAIT_SECONDS < 1.0:
    SEARCH_DECISION_INFLIGHT_WAIT_SECONDS = 1.0
SEARCH_RESULT_CACHE_TTL_SECONDS = _cfg_int("SEARCH_RESULT_CACHE_TTL_SECONDS", 300)
if SEARCH_RESULT_CACHE_TTL_SECONDS < 0:
    SEARCH_RESULT_CACHE_TTL_SECONDS = 0
SEARCH_RESULT_CACHE_MAX_ENTRIES = _cfg_int("SEARCH_RESULT_CACHE_MAX_ENTRIES", 128)
if SEARCH_RESULT_CACHE_MAX_ENTRIES < 32:
    SEARCH_RESULT_CACHE_MAX_ENTRIES = 32
SEARCH_RESULT_INFLIGHT_WAIT_SECONDS = _cfg_float("SEARCH_RESULT_INFLIGHT_WAIT_SECONDS", 12.0)
if SEARCH_RESULT_INFLIGHT_WAIT_SECONDS < 1.0:
    SEARCH_RESULT_INFLIGHT_WAIT_SECONDS = 1.0
PREFETCH_IDLE_ONLY = _cfg_bool("PREFETCH_IDLE_ONLY", True)
PREFETCH_IDLE_MAX_LOW_RUNNING = _cfg_int("PREFETCH_IDLE_MAX_LOW_RUNNING", 0)
if PREFETCH_IDLE_MAX_LOW_RUNNING < 0:
    PREFETCH_IDLE_MAX_LOW_RUNNING = 0
PREFETCH_IDLE_WAIT_SECONDS = _cfg_float("PREFETCH_IDLE_WAIT_SECONDS", 8.0)
if PREFETCH_IDLE_WAIT_SECONDS < 0.0:
    PREFETCH_IDLE_WAIT_SECONDS = 0.0
FIRST_QUESTION_PREFETCH_PRIORITY_ENABLED = _cfg_bool("FIRST_QUESTION_PREFETCH_PRIORITY_ENABLED", True)
FIRST_QUESTION_PREFETCH_PRIORITY_WINDOW_SECONDS = _cfg_float("FIRST_QUESTION_PREFETCH_PRIORITY_WINDOW_SECONDS", 120.0)
if FIRST_QUESTION_PREFETCH_PRIORITY_WINDOW_SECONDS < 10.0:
    FIRST_QUESTION_PREFETCH_PRIORITY_WINDOW_SECONDS = 10.0
QUESTION_FAST_PATH_ENABLED = _cfg_bool("QUESTION_FAST_PATH_ENABLED", True)
QUESTION_FAST_TIMEOUT = _cfg_float("QUESTION_FAST_TIMEOUT", 12.0)
if QUESTION_FAST_TIMEOUT < 5.0:
    QUESTION_FAST_TIMEOUT = 5.0
QUESTION_FAST_MAX_TOKENS = _cfg_int("QUESTION_FAST_MAX_TOKENS", 1000)
QUESTION_FAST_MAX_TOKENS = max(600, min(QUESTION_FAST_MAX_TOKENS, MAX_TOKENS_QUESTION))
QUESTION_FAST_LIGHT_PROMPT_MAX_CHARS = _cfg_int("QUESTION_FAST_LIGHT_PROMPT_MAX_CHARS", 1800)
if QUESTION_FAST_LIGHT_PROMPT_MAX_CHARS < 0:
    QUESTION_FAST_LIGHT_PROMPT_MAX_CHARS = 0
QUESTION_FAST_SKIP_WHEN_TRUNCATED_DOCS = _cfg_bool("QUESTION_FAST_SKIP_WHEN_TRUNCATED_DOCS", True)
QUESTION_FAST_ADAPTIVE_ENABLED = _cfg_bool("QUESTION_FAST_ADAPTIVE_ENABLED", True)
QUESTION_FAST_ADAPTIVE_WINDOW_SIZE = _cfg_int("QUESTION_FAST_ADAPTIVE_WINDOW_SIZE", 20)
if QUESTION_FAST_ADAPTIVE_WINDOW_SIZE < 4:
    QUESTION_FAST_ADAPTIVE_WINDOW_SIZE = 4
QUESTION_FAST_ADAPTIVE_MIN_SAMPLES = _cfg_int("QUESTION_FAST_ADAPTIVE_MIN_SAMPLES", 8)
if QUESTION_FAST_ADAPTIVE_MIN_SAMPLES < 4:
    QUESTION_FAST_ADAPTIVE_MIN_SAMPLES = 4
if QUESTION_FAST_ADAPTIVE_MIN_SAMPLES > QUESTION_FAST_ADAPTIVE_WINDOW_SIZE:
    QUESTION_FAST_ADAPTIVE_MIN_SAMPLES = QUESTION_FAST_ADAPTIVE_WINDOW_SIZE
QUESTION_FAST_ADAPTIVE_MIN_HIT_RATE = _cfg_float("QUESTION_FAST_ADAPTIVE_MIN_HIT_RATE", 0.35)
QUESTION_FAST_ADAPTIVE_MIN_HIT_RATE = max(0.0, min(QUESTION_FAST_ADAPTIVE_MIN_HIT_RATE, 1.0))
QUESTION_FAST_ADAPTIVE_COOLDOWN_SECONDS = _cfg_float("QUESTION_FAST_ADAPTIVE_COOLDOWN_SECONDS", 900.0)
if QUESTION_FAST_ADAPTIVE_COOLDOWN_SECONDS < 0.0:
    QUESTION_FAST_ADAPTIVE_COOLDOWN_SECONDS = 0.0
QUESTION_HEDGED_ENABLED = _cfg_bool("QUESTION_HEDGED_ENABLED", True)
QUESTION_HEDGED_DELAY_SECONDS = _cfg_float("QUESTION_HEDGED_DELAY_SECONDS", 1.5)
if QUESTION_HEDGED_DELAY_SECONDS < 0.5:
    QUESTION_HEDGED_DELAY_SECONDS = 0.5
QUESTION_HEDGED_SECONDARY_LANE = _cfg_text("QUESTION_HEDGED_SECONDARY_LANE", "summary").strip().lower()
if QUESTION_HEDGED_SECONDARY_LANE not in {"report", "summary", "search_decision"}:
    QUESTION_HEDGED_SECONDARY_LANE = "summary"
QUESTION_HEDGED_ONLY_WHEN_DISTINCT_CLIENT = _cfg_bool("QUESTION_HEDGED_ONLY_WHEN_DISTINCT_CLIENT", True)
QUESTION_RESULT_CACHE_TTL_SECONDS = _cfg_int("QUESTION_RESULT_CACHE_TTL_SECONDS", 120)
if QUESTION_RESULT_CACHE_TTL_SECONDS < 0:
    QUESTION_RESULT_CACHE_TTL_SECONDS = 0
QUESTION_RESULT_CACHE_MAX_ENTRIES = _cfg_int("QUESTION_RESULT_CACHE_MAX_ENTRIES", 512)
if QUESTION_RESULT_CACHE_MAX_ENTRIES < 64:
    QUESTION_RESULT_CACHE_MAX_ENTRIES = 64
METRICS_ASYNC_FLUSH_INTERVAL_SECONDS = _cfg_float("METRICS_ASYNC_FLUSH_INTERVAL_SECONDS", 1.5)
if METRICS_ASYNC_FLUSH_INTERVAL_SECONDS < 0.2:
    METRICS_ASYNC_FLUSH_INTERVAL_SECONDS = 0.2
METRICS_ASYNC_BATCH_SIZE = _cfg_int("METRICS_ASYNC_BATCH_SIZE", 20)
if METRICS_ASYNC_BATCH_SIZE < 1:
    METRICS_ASYNC_BATCH_SIZE = 1
METRICS_ASYNC_MAX_PENDING = _cfg_int("METRICS_ASYNC_MAX_PENDING", 5000)
if METRICS_ASYNC_MAX_PENDING < 100:
    METRICS_ASYNC_MAX_PENDING = 100
INTERVIEW_PROMPT_CACHE_TTL_SECONDS = _cfg_int("INTERVIEW_PROMPT_CACHE_TTL_SECONDS", 45)
if INTERVIEW_PROMPT_CACHE_TTL_SECONDS < 0:
    INTERVIEW_PROMPT_CACHE_TTL_SECONDS = 0
INTERVIEW_PROMPT_CACHE_MAX_ENTRIES = _cfg_int("INTERVIEW_PROMPT_CACHE_MAX_ENTRIES", 256)
if INTERVIEW_PROMPT_CACHE_MAX_ENTRIES < 32:
    INTERVIEW_PROMPT_CACHE_MAX_ENTRIES = 32
MAX_DOC_LENGTH = _cfg_int("MAX_DOC_LENGTH", 2000)         # 单个文档最大长度（字符）
MAX_TOTAL_DOCS = _cfg_int("MAX_TOTAL_DOCS", 5000)         # 所有文档总长度限制（字符）
API_TIMEOUT = _cfg_float("API_TIMEOUT", 90.0)             # 通用 API 超时时间（秒）
REPORT_API_TIMEOUT = _cfg_float("REPORT_API_TIMEOUT", 210.0)  # 报告生成专用超时（秒）
if REPORT_API_TIMEOUT < API_TIMEOUT:
    REPORT_API_TIMEOUT = API_TIMEOUT
REPORT_V3_PROFILE = _cfg_text("REPORT_V3_PROFILE", "balanced").strip().lower()
if REPORT_V3_PROFILE not in {"balanced", "quality"}:
    REPORT_V3_PROFILE = "balanced"
report_default_draft_timeout = min(REPORT_API_TIMEOUT, 140.0 if REPORT_V3_PROFILE == "balanced" else 180.0)
REPORT_DRAFT_API_TIMEOUT = _cfg_float("REPORT_DRAFT_API_TIMEOUT", report_default_draft_timeout)
REPORT_DRAFT_API_TIMEOUT = max(30.0, min(REPORT_DRAFT_API_TIMEOUT, REPORT_API_TIMEOUT))
report_default_draft_tokens = 4200 if REPORT_V3_PROFILE == "balanced" else 5500
REPORT_V3_DRAFT_MAX_TOKENS = _cfg_int("REPORT_V3_DRAFT_MAX_TOKENS", report_default_draft_tokens)
REPORT_V3_DRAFT_MAX_TOKENS = max(2500, REPORT_V3_DRAFT_MAX_TOKENS)
report_default_facts_limit = 34 if REPORT_V3_PROFILE == "balanced" else 48
REPORT_V3_DRAFT_FACTS_LIMIT = _cfg_int("REPORT_V3_DRAFT_FACTS_LIMIT", report_default_facts_limit)
REPORT_V3_DRAFT_FACTS_LIMIT = max(20, REPORT_V3_DRAFT_FACTS_LIMIT)
report_default_min_facts_limit = 18 if REPORT_V3_PROFILE == "balanced" else 24
REPORT_V3_DRAFT_MIN_FACTS_LIMIT = _cfg_int("REPORT_V3_DRAFT_MIN_FACTS_LIMIT", report_default_min_facts_limit)
REPORT_V3_DRAFT_MIN_FACTS_LIMIT = max(10, min(REPORT_V3_DRAFT_MIN_FACTS_LIMIT, REPORT_V3_DRAFT_FACTS_LIMIT))
report_default_retry_count = 1 if REPORT_V3_PROFILE == "balanced" else 2
REPORT_V3_DRAFT_RETRY_COUNT = _cfg_int("REPORT_V3_DRAFT_RETRY_COUNT", report_default_retry_count)
REPORT_V3_DRAFT_RETRY_COUNT = max(0, REPORT_V3_DRAFT_RETRY_COUNT)
report_default_backoff = 0.8 if REPORT_V3_PROFILE == "balanced" else 1.5
REPORT_V3_DRAFT_RETRY_BACKOFF_SECONDS = _cfg_float("REPORT_V3_DRAFT_RETRY_BACKOFF_SECONDS", report_default_backoff)
REPORT_V3_DRAFT_RETRY_BACKOFF_SECONDS = max(0.0, REPORT_V3_DRAFT_RETRY_BACKOFF_SECONDS)
REPORT_V3_FAST_FAIL_ON_DRAFT_EMPTY = _cfg_bool(
    "REPORT_V3_FAST_FAIL_ON_DRAFT_EMPTY",
    REPORT_V3_PROFILE == "balanced",
)
report_default_review_max_tokens = 5200 if REPORT_V3_PROFILE == "balanced" else 6000
REPORT_V3_REVIEW_MAX_TOKENS = _cfg_int("REPORT_V3_REVIEW_MAX_TOKENS", report_default_review_max_tokens)
REPORT_V3_REVIEW_MAX_TOKENS = max(2600, REPORT_V3_REVIEW_MAX_TOKENS)
report_default_review_rounds = 2 if REPORT_V3_PROFILE == "balanced" else 3
REPORT_V3_REVIEW_BASE_ROUNDS = _cfg_int("REPORT_V3_REVIEW_BASE_ROUNDS", report_default_review_rounds)
REPORT_V3_REVIEW_BASE_ROUNDS = max(1, min(REPORT_V3_REVIEW_BASE_ROUNDS, 4))
REPORT_V3_QUALITY_FIX_ROUNDS = _cfg_int("REPORT_V3_QUALITY_FIX_ROUNDS", 1)
REPORT_V3_QUALITY_FIX_ROUNDS = max(0, min(REPORT_V3_QUALITY_FIX_ROUNDS, 2))
REPORT_V3_FAILOVER_ENABLED = _cfg_bool("REPORT_V3_FAILOVER_ENABLED", True)
REPORT_V3_FAILOVER_LANE = _cfg_text("REPORT_V3_FAILOVER_LANE", "question").lower()
if REPORT_V3_FAILOVER_LANE not in {"question", "report"}:
    REPORT_V3_FAILOVER_LANE = "question"
REPORT_V3_DUAL_STAGE_ENABLED = _cfg_bool("REPORT_V3_DUAL_STAGE_ENABLED", True)
REPORT_V3_DRAFT_PRIMARY_LANE = _cfg_text("REPORT_V3_DRAFT_PRIMARY_LANE", "question").strip().lower()
if REPORT_V3_DRAFT_PRIMARY_LANE not in {"question", "report"}:
    REPORT_V3_DRAFT_PRIMARY_LANE = "question"
REPORT_V3_REVIEW_PRIMARY_LANE = _cfg_text("REPORT_V3_REVIEW_PRIMARY_LANE", "report").strip().lower()
if REPORT_V3_REVIEW_PRIMARY_LANE not in {"question", "report"}:
    REPORT_V3_REVIEW_PRIMARY_LANE = "report"
REPORT_V3_FAILOVER_FORCE_SINGLE_LANE = _cfg_bool("REPORT_V3_FAILOVER_FORCE_SINGLE_LANE", True)
REPORT_V3_QUALITY_FORCE_SINGLE_LANE = _cfg_bool("REPORT_V3_QUALITY_FORCE_SINGLE_LANE", True)
REPORT_V3_QUALITY_PRIMARY_LANE = _cfg_text("REPORT_V3_QUALITY_PRIMARY_LANE", "report").strip().lower()
if REPORT_V3_QUALITY_PRIMARY_LANE not in {"question", "report"}:
    REPORT_V3_QUALITY_PRIMARY_LANE = "report"
REPORT_V3_RENDER_MERMAID_FROM_DATA = _cfg_bool("REPORT_V3_RENDER_MERMAID_FROM_DATA", True)
REPORT_V3_WEAK_BINDING_ENABLED = _cfg_bool("REPORT_V3_WEAK_BINDING_ENABLED", True)
REPORT_V3_WEAK_BINDING_MIN_SCORE = _cfg_float("REPORT_V3_WEAK_BINDING_MIN_SCORE", 0.46)
REPORT_V3_WEAK_BINDING_MIN_SCORE = max(0.2, min(REPORT_V3_WEAK_BINDING_MIN_SCORE, 0.9))
REPORT_V3_SALVAGE_ON_QUALITY_GATE_FAILURE = _cfg_bool("REPORT_V3_SALVAGE_ON_QUALITY_GATE_FAILURE", True)
REPORT_V3_FAILOVER_ON_SINGLE_ISSUE = _cfg_bool("REPORT_V3_FAILOVER_ON_SINGLE_ISSUE", True)
REPORT_V3_BLINDSPOT_ACTION_REQUIRED_BALANCED = _cfg_bool("REPORT_V3_BLINDSPOT_ACTION_REQUIRED_BALANCED", False)
REPORT_V3_BLINDSPOT_ACTION_REQUIRED_QUALITY = _cfg_bool("REPORT_V3_BLINDSPOT_ACTION_REQUIRED_QUALITY", True)
REPORT_V3_UNKNOWNS_TO_OPEN_QUESTIONS_ENABLED = _cfg_bool("REPORT_V3_UNKNOWNS_TO_OPEN_QUESTIONS_ENABLED", True)
REPORT_V3_UNKNOWNS_TO_OPEN_QUESTIONS_MAX_ITEMS = _cfg_int("REPORT_V3_UNKNOWNS_TO_OPEN_QUESTIONS_MAX_ITEMS", 3)
REPORT_V3_UNKNOWNS_TO_OPEN_QUESTIONS_MAX_ITEMS = max(1, min(REPORT_V3_UNKNOWNS_TO_OPEN_QUESTIONS_MAX_ITEMS, 8))
REPORT_V3_UNKNOWN_RATIO_TRIGGER = _cfg_float("REPORT_V3_UNKNOWN_RATIO_TRIGGER", 0.65)
REPORT_V3_UNKNOWN_RATIO_TRIGGER = max(0.2, min(REPORT_V3_UNKNOWN_RATIO_TRIGGER, 1.0))
REPORT_V3_EVIDENCE_SLIM_ENABLED = _cfg_bool("REPORT_V3_EVIDENCE_SLIM_ENABLED", True)
REPORT_V3_EVIDENCE_DIM_QUOTA = _cfg_int("REPORT_V3_EVIDENCE_DIM_QUOTA", 6)
REPORT_V3_EVIDENCE_DIM_QUOTA = max(1, min(REPORT_V3_EVIDENCE_DIM_QUOTA, 20))
REPORT_V3_EVIDENCE_DEDUP_ENABLED = _cfg_bool("REPORT_V3_EVIDENCE_DEDUP_ENABLED", True)
REPORT_V3_EVIDENCE_MIN_QUALITY = _cfg_float("REPORT_V3_EVIDENCE_MIN_QUALITY", 0.2)
REPORT_V3_EVIDENCE_MIN_QUALITY = max(0.0, min(REPORT_V3_EVIDENCE_MIN_QUALITY, 0.9))
REPORT_V3_EVIDENCE_KEEP_HARD_TRIGGERED = _cfg_bool("REPORT_V3_EVIDENCE_KEEP_HARD_TRIGGERED", True)
GATEWAY_CIRCUIT_BREAKER_ENABLED = _cfg_bool("GATEWAY_CIRCUIT_BREAKER_ENABLED", True)
GATEWAY_CIRCUIT_FAIL_THRESHOLD = _cfg_int("GATEWAY_CIRCUIT_FAIL_THRESHOLD", 2)
GATEWAY_CIRCUIT_FAIL_THRESHOLD = max(1, min(GATEWAY_CIRCUIT_FAIL_THRESHOLD, 8))
GATEWAY_CIRCUIT_COOLDOWN_SECONDS = _cfg_float("GATEWAY_CIRCUIT_COOLDOWN_SECONDS", 120.0)
GATEWAY_CIRCUIT_COOLDOWN_SECONDS = max(30.0, min(GATEWAY_CIRCUIT_COOLDOWN_SECONDS, 900.0))
GATEWAY_CIRCUIT_FAILURE_WINDOW_SECONDS = _cfg_float("GATEWAY_CIRCUIT_FAILURE_WINDOW_SECONDS", 180.0)
GATEWAY_CIRCUIT_FAILURE_WINDOW_SECONDS = max(30.0, min(GATEWAY_CIRCUIT_FAILURE_WINDOW_SECONDS, 1200.0))


def normalize_report_profile_choice(raw_profile: str, fallback: str = "") -> str:
    profile = str(raw_profile or "").strip().lower()
    if profile in {"balanced", "quality"}:
        return profile
    fallback_profile = str(fallback or "").strip().lower()
    if fallback_profile in {"balanced", "quality"}:
        return fallback_profile
    return REPORT_V3_PROFILE


def get_report_v3_runtime_config(profile_choice: str = "") -> dict:
    profile = normalize_report_profile_choice(profile_choice, fallback=REPORT_V3_PROFILE)

    draft_timeout_default = min(REPORT_API_TIMEOUT, 140.0 if profile == "balanced" else 180.0)
    draft_timeout = _cfg_float("REPORT_DRAFT_API_TIMEOUT", draft_timeout_default)
    draft_timeout = max(30.0, min(draft_timeout, REPORT_API_TIMEOUT))

    draft_tokens_default = 4200 if profile == "balanced" else 5500
    draft_max_tokens = _cfg_int("REPORT_V3_DRAFT_MAX_TOKENS", draft_tokens_default)
    draft_max_tokens = max(2500, draft_max_tokens)

    facts_limit_default = 34 if profile == "balanced" else 48
    draft_facts_limit = _cfg_int("REPORT_V3_DRAFT_FACTS_LIMIT", facts_limit_default)
    draft_facts_limit = max(20, draft_facts_limit)

    min_facts_limit_default = 18 if profile == "balanced" else 24
    draft_min_facts_limit = _cfg_int("REPORT_V3_DRAFT_MIN_FACTS_LIMIT", min_facts_limit_default)
    draft_min_facts_limit = max(10, min(draft_min_facts_limit, draft_facts_limit))

    retry_count_default = 1 if profile == "balanced" else 2
    draft_retry_count = _cfg_int("REPORT_V3_DRAFT_RETRY_COUNT", retry_count_default)
    draft_retry_count = max(0, draft_retry_count)

    backoff_default = 0.8 if profile == "balanced" else 1.5
    draft_retry_backoff_seconds = _cfg_float("REPORT_V3_DRAFT_RETRY_BACKOFF_SECONDS", backoff_default)
    draft_retry_backoff_seconds = max(0.0, draft_retry_backoff_seconds)

    fast_fail_on_draft_empty = _cfg_bool("REPORT_V3_FAST_FAIL_ON_DRAFT_EMPTY", profile == "balanced")

    review_tokens_default = 5200 if profile == "balanced" else 6000
    review_max_tokens = _cfg_int("REPORT_V3_REVIEW_MAX_TOKENS", review_tokens_default)
    review_max_tokens = max(2600, review_max_tokens)

    review_rounds_default = 2 if profile == "balanced" else 3
    review_base_rounds = _cfg_int("REPORT_V3_REVIEW_BASE_ROUNDS", review_rounds_default)
    review_base_rounds = max(1, min(review_base_rounds, 4))

    quality_fix_rounds = _cfg_int("REPORT_V3_QUALITY_FIX_ROUNDS", 1)
    quality_fix_rounds = max(0, min(quality_fix_rounds, 2))

    min_review_rounds_default = 1 if profile == "balanced" else 2
    configured_min_required_review_rounds = _cfg_int("REPORT_V3_MIN_REVIEW_ROUNDS", min_review_rounds_default)
    if configured_min_required_review_rounds <= 0:
        min_required_review_rounds = min_review_rounds_default
    else:
        min_required_review_rounds = max(1, min(configured_min_required_review_rounds, 4))

    quality_force_single_lane = _cfg_bool("REPORT_V3_QUALITY_FORCE_SINGLE_LANE", True)
    quality_primary_lane = _cfg_text("REPORT_V3_QUALITY_PRIMARY_LANE", "report").strip().lower()
    if quality_primary_lane not in {"question", "report"}:
        quality_primary_lane = "report"

    render_mermaid_from_data = _cfg_bool("REPORT_V3_RENDER_MERMAID_FROM_DATA", True)
    weak_binding_enabled = _cfg_bool("REPORT_V3_WEAK_BINDING_ENABLED", True)
    weak_binding_min_score = _cfg_float("REPORT_V3_WEAK_BINDING_MIN_SCORE", 0.46)
    weak_binding_min_score = max(0.2, min(weak_binding_min_score, 0.9))
    salvage_on_quality_gate_failure = _cfg_bool("REPORT_V3_SALVAGE_ON_QUALITY_GATE_FAILURE", True)
    failover_on_single_issue = _cfg_bool("REPORT_V3_FAILOVER_ON_SINGLE_ISSUE", True)
    blindspot_action_required_balanced = _cfg_bool("REPORT_V3_BLINDSPOT_ACTION_REQUIRED_BALANCED", False)
    blindspot_action_required_quality = _cfg_bool("REPORT_V3_BLINDSPOT_ACTION_REQUIRED_QUALITY", True)
    unknown_followup_enabled = _cfg_bool("REPORT_V3_UNKNOWNS_TO_OPEN_QUESTIONS_ENABLED", True)
    unknown_followup_max_items = _cfg_int("REPORT_V3_UNKNOWNS_TO_OPEN_QUESTIONS_MAX_ITEMS", 3)
    unknown_followup_max_items = max(1, min(unknown_followup_max_items, 8))
    unknown_ratio_trigger = _cfg_float("REPORT_V3_UNKNOWN_RATIO_TRIGGER", 0.65)
    unknown_ratio_trigger = max(0.2, min(unknown_ratio_trigger, 1.0))

    return {
        "profile": profile,
        "draft_timeout": float(draft_timeout),
        "draft_max_tokens": int(draft_max_tokens),
        "draft_facts_limit": int(draft_facts_limit),
        "draft_min_facts_limit": int(draft_min_facts_limit),
        "draft_retry_count": int(draft_retry_count),
        "draft_retry_backoff_seconds": float(draft_retry_backoff_seconds),
        "fast_fail_on_draft_empty": bool(fast_fail_on_draft_empty),
        "review_max_tokens": int(review_max_tokens),
        "review_base_rounds": int(review_base_rounds),
        "quality_fix_rounds": int(quality_fix_rounds),
        "min_required_review_rounds": int(min_required_review_rounds),
        "quality_force_single_lane": bool(quality_force_single_lane),
        "quality_primary_lane": quality_primary_lane,
        "render_mermaid_from_data": bool(render_mermaid_from_data),
        "weak_binding_enabled": bool(weak_binding_enabled),
        "weak_binding_min_score": float(weak_binding_min_score),
        "salvage_on_quality_gate_failure": bool(salvage_on_quality_gate_failure),
        "failover_on_single_issue": bool(failover_on_single_issue),
        "blindspot_action_required_balanced": bool(blindspot_action_required_balanced),
        "blindspot_action_required_quality": bool(blindspot_action_required_quality),
        "unknown_followup_enabled": bool(unknown_followup_enabled),
        "unknown_followup_max_items": int(unknown_followup_max_items),
        "unknown_ratio_trigger": float(unknown_ratio_trigger),
    }


REPORT_TEMPLATE_STANDARD_V1 = "standard_v1"
REPORT_TEMPLATE_ASSESSMENT_V1 = "assessment_v1"
REPORT_TEMPLATE_CUSTOM_V1 = "custom_v1"
REPORT_TEMPLATE_ALLOWED = {
    REPORT_TEMPLATE_STANDARD_V1,
    REPORT_TEMPLATE_ASSESSMENT_V1,
    REPORT_TEMPLATE_CUSTOM_V1,
}
REPORT_TEMPLATE_ALIAS = {
    "": REPORT_TEMPLATE_STANDARD_V1,
    "default": REPORT_TEMPLATE_STANDARD_V1,
    "standard": REPORT_TEMPLATE_STANDARD_V1,
    "standard_v1": REPORT_TEMPLATE_STANDARD_V1,
    "assessment": REPORT_TEMPLATE_ASSESSMENT_V1,
    "assessment_v1": REPORT_TEMPLATE_ASSESSMENT_V1,
    "custom": REPORT_TEMPLATE_CUSTOM_V1,
    "custom_v1": REPORT_TEMPLATE_CUSTOM_V1,
}
CUSTOM_REPORT_COMPONENTS = {"paragraph", "table", "mermaid", "list"}
CUSTOM_REPORT_ALLOWED_SOURCES = {
    "overview",
    "needs",
    "priority_matrix",
    "priority_list",
    "solutions",
    "risks",
    "actions",
    "open_questions",
    "evidence_index",
    "analysis.customer_needs",
    "analysis.business_flow",
    "analysis.tech_constraints",
    "analysis.project_constraints",
    "visualizations.priority_quadrant_mermaid",
    "visualizations.business_flow_mermaid",
    "visualizations.demand_pie_mermaid",
    "visualizations.architecture_mermaid",
}
CUSTOM_SECTION_SOURCE_HINTS = {
    "overview": ("paragraph", "overview"),
    "requirements_summary": ("table", "needs"),
    "detailed_analysis": ("paragraph", "analysis.customer_needs"),
    "visualizations": ("mermaid", "visualizations.business_flow_mermaid"),
    "recommendations": ("table", "solutions"),
    "risks": ("table", "risks"),
    "next_steps": ("table", "actions"),
    "appendix": ("list", "open_questions"),
    "candidate_overview": ("paragraph", "overview"),
    "ability_scores": ("table", "needs"),
    "radar_chart": ("mermaid", "visualizations.priority_quadrant_mermaid"),
    "dimension_analysis": ("paragraph", "analysis.customer_needs"),
    "strengths": ("list", "solutions"),
    "weaknesses": ("list", "risks"),
    "recommendation_level": ("paragraph", "analysis.project_constraints"),
    "hiring_suggestion": ("table", "actions"),
    "follow_up_questions": ("table", "open_questions"),
}


def normalize_report_template_name(raw_template: str, report_type: str = "") -> str:
    template = str(raw_template or "").strip().lower()
    normalized_type = str(report_type or "").strip().lower()

    mapped = REPORT_TEMPLATE_ALIAS.get(template, "")
    if mapped:
        return mapped

    if normalized_type == "assessment":
        return REPORT_TEMPLATE_ASSESSMENT_V1
    return REPORT_TEMPLATE_STANDARD_V1


def _build_default_custom_report_schema() -> dict:
    return {
        "version": "v1",
        "sections": [
            {
                "section_id": "summary",
                "title": "执行摘要",
                "component": "paragraph",
                "source": "overview",
                "required": True,
            },
            {
                "section_id": "needs",
                "title": "核心需求",
                "component": "table",
                "source": "needs",
                "required": True,
            },
            {
                "section_id": "solutions",
                "title": "方案建议",
                "component": "table",
                "source": "solutions",
                "required": True,
            },
            {
                "section_id": "risks",
                "title": "风险评估",
                "component": "table",
                "source": "risks",
                "required": True,
            },
            {
                "section_id": "actions",
                "title": "行动计划",
                "component": "table",
                "source": "actions",
                "required": True,
            },
            {
                "section_id": "open_questions",
                "title": "未决问题",
                "component": "table",
                "source": "open_questions",
                "required": False,
            },
        ],
    }


def _infer_custom_section_config(raw_item, index: int) -> Optional[dict]:
    if isinstance(raw_item, str):
        key = str(raw_item or "").strip().lower()
        component, source = CUSTOM_SECTION_SOURCE_HINTS.get(key, ("paragraph", "overview"))
        return {
            "section_id": key or f"section_{index}",
            "title": str(raw_item or f"章节{index}").strip() or f"章节{index}",
            "component": component,
            "source": source,
            "required": False,
        }

    if not isinstance(raw_item, dict):
        return None

    section_id = str(raw_item.get("section_id") or raw_item.get("id") or f"section_{index}").strip()
    title = str(raw_item.get("title") or section_id or f"章节{index}").strip()
    component = str(raw_item.get("component") or "paragraph").strip().lower()
    source = str(raw_item.get("source") or "overview").strip()
    required = bool(raw_item.get("required", False))

    return {
        "section_id": section_id or f"section_{index}",
        "title": title or f"章节{index}",
        "component": component or "paragraph",
        "source": source or "overview",
        "required": required,
    }


def normalize_custom_report_schema(raw_schema, fallback_sections=None) -> tuple[dict, list]:
    """
    规范化并校验用户自定义报告结构。
    仅支持声明式组件，禁止执行模板语法。
    """
    schema = raw_schema if isinstance(raw_schema, dict) else {}
    sections_raw = schema.get("sections")
    if not isinstance(sections_raw, list) or not sections_raw:
        sections_raw = fallback_sections if isinstance(fallback_sections, list) else []

    normalized_sections = []
    issues = []
    seen_ids = set()

    for idx, raw_item in enumerate(sections_raw[:24], 1):
        section = _infer_custom_section_config(raw_item, idx)
        if not section:
            issues.append(f"第 {idx} 个章节配置格式无效")
            continue

        section_id = str(section.get("section_id", "")).strip()
        if not section_id:
            section_id = f"section_{idx}"
            section["section_id"] = section_id
        if section_id in seen_ids:
            issues.append(f"章节标识重复：{section_id}")
            continue
        seen_ids.add(section_id)

        component = str(section.get("component", "")).strip().lower()
        if component not in CUSTOM_REPORT_COMPONENTS:
            issues.append(f"章节 {section_id} 的 component 不支持：{component}")
            continue

        source = str(section.get("source", "")).strip()
        if source not in CUSTOM_REPORT_ALLOWED_SOURCES:
            issues.append(f"章节 {section_id} 的 source 不支持：{source}")
            continue

        section["component"] = component
        section["source"] = source
        section["title"] = str(section.get("title", "")).strip() or section_id
        section["required"] = bool(section.get("required", False))
        normalized_sections.append(section)

    if not normalized_sections:
        normalized_sections = _build_default_custom_report_schema()["sections"]

    return {
        "version": str(schema.get("version") or "v1"),
        "sections": normalized_sections,
    }, issues


def summarize_custom_report_schema_for_prompt(schema: dict) -> str:
    if not isinstance(schema, dict):
        return "- 未提供章节配置"
    sections = schema.get("sections", [])
    if not isinstance(sections, list) or not sections:
        return "- 未提供章节配置"

    lines = []
    for idx, item in enumerate(sections[:20], 1):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "") or item.get("section_id", f"章节{idx}")).strip()
        component = str(item.get("component", "paragraph")).strip().lower()
        source = str(item.get("source", "overview")).strip()
        required = "必填" if bool(item.get("required", False)) else "可选"
        lines.append(f"- {idx}. {title}（{component} / {source} / {required}）")

    return "\n".join(lines) if lines else "- 未提供章节配置"


def resolve_report_template_for_session(session: dict, evidence_pack: Optional[dict] = None) -> str:
    report_cfg = (session or {}).get("scenario_config", {}).get("report", {})
    if not isinstance(report_cfg, dict):
        report_cfg = {}

    report_type = str((evidence_pack or {}).get("report_type") or report_cfg.get("type") or "standard").strip().lower()
    template_raw = report_cfg.get("template")
    normalized = normalize_report_template_name(template_raw, report_type=report_type)

    if normalized == REPORT_TEMPLATE_STANDARD_V1 and isinstance(report_cfg.get("schema"), dict):
        # 兼容老数据：若提供了 schema 但未显式声明 template，则自动走 custom 模板。
        return REPORT_TEMPLATE_CUSTOM_V1
    return normalized

# 手机验证码登录配置
SMS_PROVIDER = _cfg_text("SMS_PROVIDER", "mock").lower()
if SMS_PROVIDER not in {"mock", "jdcloud"}:
    SMS_PROVIDER = "mock"
SMS_CODE_LENGTH = _cfg_int("SMS_CODE_LENGTH", 6)
SMS_CODE_LENGTH = max(4, min(SMS_CODE_LENGTH, 8))
SMS_CODE_TTL_SECONDS = _cfg_int("SMS_CODE_TTL_SECONDS", 300)
SMS_CODE_TTL_SECONDS = max(60, min(SMS_CODE_TTL_SECONDS, 1800))
SMS_SEND_COOLDOWN_SECONDS = _cfg_int("SMS_SEND_COOLDOWN_SECONDS", 60)
SMS_SEND_COOLDOWN_SECONDS = max(10, min(SMS_SEND_COOLDOWN_SECONDS, 600))
SMS_MAX_SEND_PER_PHONE_PER_DAY = _cfg_int("SMS_MAX_SEND_PER_PHONE_PER_DAY", 10)
SMS_MAX_SEND_PER_PHONE_PER_DAY = max(1, min(SMS_MAX_SEND_PER_PHONE_PER_DAY, 200))
SMS_MAX_VERIFY_ATTEMPTS = _cfg_int("SMS_MAX_VERIFY_ATTEMPTS", 5)
SMS_MAX_VERIFY_ATTEMPTS = max(1, min(SMS_MAX_VERIFY_ATTEMPTS, 20))
SMS_TEST_CODE = _cfg_text("SMS_TEST_CODE", "")

JD_SMS_ACCESS_KEY_ID = _cfg_text("JD_SMS_ACCESS_KEY_ID", "")
JD_SMS_ACCESS_KEY_SECRET = _cfg_text("JD_SMS_ACCESS_KEY_SECRET", "")
JD_SMS_REGION_ID = _cfg_text("JD_SMS_REGION_ID", "cn-north-1") or "cn-north-1"
JD_SMS_SIGN_ID = _cfg_text("JD_SMS_SIGN_ID", "")
JD_SMS_TEMPLATE_ID_LOGIN = _cfg_text("JD_SMS_TEMPLATE_ID_LOGIN", "")
JD_SMS_TEMPLATE_ID_BIND = _cfg_text("JD_SMS_TEMPLATE_ID_BIND", JD_SMS_TEMPLATE_ID_LOGIN)
JD_SMS_TEMPLATE_ID_RECOVER = _cfg_text("JD_SMS_TEMPLATE_ID_RECOVER", JD_SMS_TEMPLATE_ID_LOGIN)
JD_SMS_TIMEOUT = _cfg_float("JD_SMS_TIMEOUT", 8.0)
JD_SMS_TIMEOUT = max(3.0, min(JD_SMS_TIMEOUT, 30.0))

# 第三方登录配置（微信扫码登录）
WECHAT_LOGIN_ENABLED = _cfg_bool("WECHAT_LOGIN_ENABLED", False)
WECHAT_APP_ID = _cfg_text("WECHAT_APP_ID", "")
WECHAT_APP_SECRET = _cfg_text("WECHAT_APP_SECRET", "")
WECHAT_REDIRECT_URI = _cfg_text("WECHAT_REDIRECT_URI", "")
INSTANCE_SCOPE_KEY = _cfg_text("INSTANCE_SCOPE_KEY", "")
WECHAT_OAUTH_SCOPE = _cfg_text("WECHAT_OAUTH_SCOPE", "snsapi_login")
if not WECHAT_OAUTH_SCOPE:
    WECHAT_OAUTH_SCOPE = "snsapi_login"
WECHAT_OAUTH_TIMEOUT = _cfg_float("WECHAT_OAUTH_TIMEOUT", 8.0)
WECHAT_OAUTH_TIMEOUT = max(3.0, min(WECHAT_OAUTH_TIMEOUT, 30.0))
WECHAT_OAUTH_STATE_TTL_SECONDS = _cfg_int("WECHAT_OAUTH_STATE_TTL_SECONDS", 300)
WECHAT_OAUTH_STATE_TTL_SECONDS = max(60, min(WECHAT_OAUTH_STATE_TTL_SECONDS, 1800))

# 智能文档摘要配置
ENABLE_SMART_SUMMARY = _cfg_bool("ENABLE_SMART_SUMMARY", True)
SMART_SUMMARY_THRESHOLD = _cfg_int("SMART_SUMMARY_THRESHOLD", 1500)
SMART_SUMMARY_TARGET = _cfg_int("SMART_SUMMARY_TARGET", 800)
SUMMARY_CACHE_ENABLED = _cfg_bool("SUMMARY_CACHE_ENABLED", True)
MAX_TOKENS_SUMMARY = _cfg_int("MAX_TOKENS_SUMMARY", 500)

# 集中读取后复用
CONFIG_SECRET_KEY = _cfg_text("SECRET_KEY", "")
CONFIG_AUTH_DB_PATH = _cfg_text("AUTH_DB_PATH", "")
CONFIG_SCENARIOS_DIR = _cfg_text("SCENARIOS_DIR", "")
CONFIG_BUILTIN_SCENARIOS_DIR = _cfg_text("BUILTIN_SCENARIOS_DIR", "")
CONFIG_CUSTOM_SCENARIOS_DIR = _cfg_text("CUSTOM_SCENARIOS_DIR", "")


def _build_lane_signature(api_key: str, base_url: str, use_bearer_auth: bool) -> tuple[str, str, bool]:
    return (str(api_key or "").strip(), str(base_url or "").strip(), bool(use_bearer_auth))


def _resolve_lane_model_name(lane: str) -> str:
    """根据 lane 的实际网关签名选择模型，避免模型与网关供应商不匹配。"""
    normalized_lane = str(lane or "").strip().lower()

    if normalized_lane == "report":
        return REPORT_MODEL_NAME or QUESTION_MODEL_NAME

    if normalized_lane == "summary":
        default_model = SUMMARY_MODEL_NAME or QUESTION_MODEL_NAME
        summary_signature = _build_lane_signature(SUMMARY_API_KEY, SUMMARY_BASE_URL, SUMMARY_USE_BEARER_AUTH)
        report_signature = _build_lane_signature(REPORT_API_KEY, REPORT_BASE_URL, REPORT_USE_BEARER_AUTH)
        if (
            summary_signature == report_signature
            and default_model == QUESTION_MODEL_NAME
            and REPORT_MODEL_NAME
            and REPORT_MODEL_NAME != default_model
        ):
            return REPORT_MODEL_NAME
        return default_model

    if normalized_lane == "search_decision":
        default_model = SEARCH_DECISION_MODEL_NAME or SUMMARY_MODEL_NAME or QUESTION_MODEL_NAME
        search_signature = _build_lane_signature(
            SEARCH_DECISION_API_KEY,
            SEARCH_DECISION_BASE_URL,
            SEARCH_DECISION_USE_BEARER_AUTH,
        )
        report_signature = _build_lane_signature(REPORT_API_KEY, REPORT_BASE_URL, REPORT_USE_BEARER_AUTH)
        if (
            search_signature == report_signature
            and default_model in {QUESTION_MODEL_NAME, SUMMARY_MODEL_NAME}
            and REPORT_MODEL_NAME
            and REPORT_MODEL_NAME != default_model
        ):
            return REPORT_MODEL_NAME
        summary_signature = _build_lane_signature(SUMMARY_API_KEY, SUMMARY_BASE_URL, SUMMARY_USE_BEARER_AUTH)
        if search_signature == summary_signature:
            return _resolve_lane_model_name("summary")
        return default_model

    return QUESTION_MODEL_NAME


def resolve_model_name(call_type: str = "", model_name: str = "") -> str:
    """根据调用类型选择模型；显式传入 model_name 时优先使用。"""
    explicit = str(model_name or "").strip()
    if explicit:
        return explicit

    lowered = (call_type or "").lower()
    if "search_decision" in lowered:
        return _resolve_lane_model_name("search_decision")
    if "summary" in lowered:
        return _resolve_lane_model_name("summary")
    if "report" in lowered:
        return _resolve_lane_model_name("report")
    return QUESTION_MODEL_NAME


def resolve_model_name_for_lane(call_type: str = "", model_name: str = "", selected_lane: str = "") -> str:
    """根据实际选中的 lane 选择模型，避免 fallback 时模型和网关不匹配。"""
    explicit = str(model_name or "").strip()
    if explicit:
        return explicit

    lane = str(selected_lane or "").strip().lower()
    if lane in {"question", "report", "summary", "search_decision"}:
        lane_model = _resolve_lane_model_name(lane)
        if lane_model:
            return lane_model

    return resolve_model_name(call_type=call_type, model_name=model_name)


def resolve_call_lane(call_type: str = "", model_name: str = "") -> str:
    """根据调用类型判断应该优先使用的问题/报告网关。"""
    lowered = (call_type or "").lower()
    if "search_decision" in lowered:
        return "search_decision"
    if "summary" in lowered:
        return "summary"
    if "report" in lowered:
        return "report"

    explicit = str(model_name or "").strip()
    if explicit and explicit == REPORT_MODEL_NAME and explicit != QUESTION_MODEL_NAME:
        return "report"

    return "question"


def resolve_report_v3_phase_lane(phase: str, pipeline_lane: str = "") -> str:
    """为 V3 不同阶段选择 lane；支持草案与审稿分离。"""
    normalized_phase = str(phase or "").strip().lower()
    if normalized_phase not in {"draft", "review"}:
        normalized_phase = "draft"

    normalized_pipeline_lane = str(pipeline_lane or "").strip().lower()
    if normalized_pipeline_lane not in {"question", "report"}:
        normalized_pipeline_lane = "report"

    if not REPORT_V3_DUAL_STAGE_ENABLED:
        return normalized_pipeline_lane

    # 备用网关重试时优先单 lane，避免跨网关抖动导致不稳定。
    if REPORT_V3_FAILOVER_FORCE_SINGLE_LANE and normalized_pipeline_lane != "report":
        return normalized_pipeline_lane

    if normalized_phase == "review":
        return REPORT_V3_REVIEW_PRIMARY_LANE
    return REPORT_V3_DRAFT_PRIMARY_LANE


app = Flask(__name__, static_folder='.')
CORS(app)

# Session 配置
config_secret_key = CONFIG_SECRET_KEY
env_secret_key = os.environ.get("DEEPVISION_SECRET_KEY", "") or os.environ.get("SECRET_KEY", "")
if config_secret_key or env_secret_key:
    app_secret_key = config_secret_key or env_secret_key
elif DEBUG_MODE:
    # 开发模式使用固定默认密钥，避免每次重启后登录态全部失效
    app_secret_key = os.environ.get("DEEPVISION_DEV_SECRET_KEY", "deepvision-dev-secret-key")
    print("⚠️  未配置 SECRET_KEY，开发模式使用固定默认会话密钥")
else:
    app_secret_key = secrets.token_hex(32)
    print("⚠️  未配置 SECRET_KEY，当前使用临时会话密钥（重启后登录态会失效）")

app.config["SECRET_KEY"] = app_secret_key
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = not DEBUG_MODE
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)

# 路径配置
SKILL_DIR = Path(__file__).parent.parent.resolve()
WEB_DIR = Path(__file__).parent.resolve()
RESOURCES_DIR = SKILL_DIR / "resources"
DATA_DIR = SKILL_DIR / "data"
SESSIONS_DIR = DATA_DIR / "sessions"
REPORTS_DIR = DATA_DIR / "reports"
CONVERTED_DIR = DATA_DIR / "converted"
TEMP_DIR = DATA_DIR / "temp"
METRICS_DIR = DATA_DIR / "metrics"
SUMMARIES_DIR = DATA_DIR / "summaries"  # 文档摘要缓存目录
PRESENTATIONS_DIR = DATA_DIR / "presentations"
AUTH_DIR = DATA_DIR / "auth"
PRESENTATION_MAP_FILE = PRESENTATIONS_DIR / ".presentation_map.json"
PRESENTATION_MAP_LOCK = threading.Lock()
DELETED_REPORTS_FILE = REPORTS_DIR / ".deleted_reports.json"
DELETED_DOCS_FILE = DATA_DIR / ".deleted_docs.json"  # 软删除记录文件
REPORT_OWNERS_FILE = REPORTS_DIR / ".owners.json"
REPORT_SCOPES_FILE = REPORTS_DIR / ".scopes.json"
REPORT_OWNERS_LOCK = threading.RLock()
REPORT_SCOPES_LOCK = threading.RLock()
SESSIONS_LIST_SEMAPHORE = threading.BoundedSemaphore(SESSIONS_LIST_MAX_INFLIGHT)
REPORTS_LIST_SEMAPHORE = threading.BoundedSemaphore(REPORTS_LIST_MAX_INFLIGHT)
ALLOWED_STATIC_EXTENSIONS = {
    ".html", ".css", ".js", ".map", ".json",
    ".ico", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg",
    ".woff", ".woff2", ".ttf", ".eot",
}


def _resolve_runtime_path(raw_path: str, default_path: Path) -> Path:
    text = str(raw_path or "").strip()
    if not text:
        return default_path

    parsed = Path(text).expanduser()
    if parsed.is_absolute():
        return parsed
    return (SKILL_DIR / parsed).resolve()


LEGACY_SCENARIOS_DIR = DATA_DIR / "scenarios"
LEGACY_SCENARIOS_BUILTIN_DIR = LEGACY_SCENARIOS_DIR / "builtin"
LEGACY_SCENARIOS_CUSTOM_DIR = LEGACY_SCENARIOS_DIR / "custom"
configured_scenarios_root = (
    _resolve_runtime_path(CONFIG_SCENARIOS_DIR, LEGACY_SCENARIOS_DIR)
    if CONFIG_SCENARIOS_DIR
    else None
)

default_builtin_scenarios_dir = RESOURCES_DIR / "scenarios" / "builtin"
if not default_builtin_scenarios_dir.exists() and LEGACY_SCENARIOS_BUILTIN_DIR.exists():
    default_builtin_scenarios_dir = LEGACY_SCENARIOS_BUILTIN_DIR

if CONFIG_BUILTIN_SCENARIOS_DIR:
    BUILTIN_SCENARIOS_DIR = _resolve_runtime_path(CONFIG_BUILTIN_SCENARIOS_DIR, default_builtin_scenarios_dir)
elif configured_scenarios_root is not None:
    BUILTIN_SCENARIOS_DIR = configured_scenarios_root / "builtin"
else:
    BUILTIN_SCENARIOS_DIR = default_builtin_scenarios_dir

default_custom_scenarios_dir = Path.home() / ".deepvision" / "scenarios" / "custom"
if CONFIG_CUSTOM_SCENARIOS_DIR:
    CUSTOM_SCENARIOS_DIR = _resolve_runtime_path(CONFIG_CUSTOM_SCENARIOS_DIR, default_custom_scenarios_dir)
elif configured_scenarios_root is not None:
    CUSTOM_SCENARIOS_DIR = configured_scenarios_root / "custom"
else:
    CUSTOM_SCENARIOS_DIR = default_custom_scenarios_dir

auth_db_from_config = CONFIG_AUTH_DB_PATH
auth_db_from_env = os.environ.get("DEEPVISION_AUTH_DB_PATH", "")
raw_auth_db_path = auth_db_from_env or auth_db_from_config
if raw_auth_db_path:
    AUTH_DB_PATH = Path(raw_auth_db_path).expanduser()
    if not AUTH_DB_PATH.is_absolute():
        AUTH_DB_PATH = (SKILL_DIR / AUTH_DB_PATH).resolve()
else:
    AUTH_DB_PATH = AUTH_DIR / "users.db"

for d in [SESSIONS_DIR, REPORTS_DIR, CONVERTED_DIR, TEMP_DIR, METRICS_DIR, SUMMARIES_DIR, PRESENTATIONS_DIR, AUTH_DIR]:
    d.mkdir(parents=True, exist_ok=True)

if WECHAT_LOGIN_ENABLED and not INSTANCE_SCOPE_KEY:
    print("⚠️  未配置 INSTANCE_SCOPE_KEY，不同深瞳链接若共享同一数据目录，可能互相看到会话/报告")

AUTH_PHONE_PATTERN = re.compile(r"^1\d{10}$")

# ============ 场景配置加载器 ============
import sys
sys.path.insert(0, str(SKILL_DIR))
from scripts.scenario_loader import get_scenario_loader
scenario_loader = get_scenario_loader(
    builtin_dir=BUILTIN_SCENARIOS_DIR,
    custom_dir=CUSTOM_SCENARIOS_DIR,
    migrate_legacy_custom_dir=LEGACY_SCENARIOS_CUSTOM_DIR,
)

# Web Search 状态追踪（用于前端呼吸灯效果）
web_search_active = False

# ============ 思考进度状态追踪（方案B）============
thinking_status = {}           # { session_id: { stage, stage_index, total_stages, message } }
thinking_status_lock = threading.Lock()

# ============ AI 调度优先级控制 ============
# 目标：问题/报告优先，摘要/搜索决策后台降级，减少主链路尾延迟。
ai_priority_state = {
    "high_waiting": 0,
    "high_running": 0,
    "low_running": 0,
}
ai_priority_condition = threading.Condition()
ai_priority_local = threading.local()

# ============ 异步摘要调度控制 ============
summary_update_schedule_lock = threading.Lock()
summary_update_schedule_state = {}  # { session_id: { inflight: bool, last_trigger_ts: float } }

# ============ 搜索决策缓存 ============
search_decision_cache_lock = threading.Lock()
search_decision_cache = {}  # { cache_key: { value: dict, expire_at: float } }
search_decision_inflight = {}  # { cache_key: { event: threading.Event, started_at: float } }

# ============ 搜索结果缓存与并发去重 ============
search_result_cache_lock = threading.Lock()
search_result_cache = {}  # { cache_key: { value: list, expire_at: float } }
search_result_inflight = {}  # { cache_key: { event: threading.Event, started_at: float } }

# ============ 问题结果幂等缓存 ============
question_result_cache_lock = threading.Lock()
question_result_cache = {}  # { cache_key: { value: dict, expire_at: float } }

# ============ 问题快档自适应控制 ============
question_fast_strategy_lock = threading.Lock()
question_fast_strategy_state = {
    "recent": deque(maxlen=max(QUESTION_FAST_ADAPTIVE_WINDOW_SIZE, QUESTION_FAST_ADAPTIVE_MIN_SAMPLES, 4)),
    "cooldown_until": 0.0,
    "last_reason": "",
    "last_hit_rate": 0.0,
    "last_sample_size": 0,
    "last_opened_at": 0.0,
}

# ============ 访谈 Prompt 构建缓存 ============
interview_prompt_cache_lock = threading.Lock()
interview_prompt_cache = {}  # { cache_key: { value: tuple[prompt, truncated_docs, decision_meta], expire_at: float } }

# ============ 首题预生成优先窗口 ============
first_question_prefetch_priority_lock = threading.Lock()
first_question_prefetch_priority = {}  # { session_id: deadline_ts }

THINKING_STAGES = {
    "analyzing": {"index": 0, "message": "正在分析您的回答..."},
    "searching": {"index": 1, "message": "正在检索相关资料..."},
    "generating": {"index": 2, "message": "正在生成下一个问题..."},
}

# ============ 报告生成进度状态追踪 ============
report_generation_status = {}   # { session_id: { state, stage_index, total_stages, progress, message, updated_at, active } }
report_generation_status_lock = threading.Lock()
report_generation_workers = {}  # { session_id: Future }
report_generation_workers_lock = threading.Lock()
report_generation_queue_stats_lock = threading.Lock()
report_generation_queue_stats = {
    "submitted": 0,
    "rejected": 0,
    "completed": 0,
    "failed": 0,
}
report_generation_slots = threading.BoundedSemaphore(REPORT_GENERATION_MAX_PENDING)
report_generation_executor = ThreadPoolExecutor(
    max_workers=REPORT_GENERATION_MAX_WORKERS,
    thread_name_prefix="report-generator",
)

REPORT_GENERATION_STAGES = {
    "queued": {"index": 0, "progress": 5, "message": "已提交请求，准备生成报告..."},
    "building_prompt": {"index": 1, "progress": 20, "message": "正在整理访谈与资料上下文..."},
    "generating": {"index": 2, "progress": 65, "message": "正在调用 AI 生成报告正文..."},
    "fallback": {"index": 3, "progress": 78, "message": "AI 响应较慢，正在切换模板生成..."},
    "saving": {"index": 4, "progress": 90, "message": "正在保存报告并更新会话状态..."},
    "completed": {"index": 5, "progress": 100, "message": "报告生成完成"},
    "failed": {"index": 5, "progress": 100, "message": "报告生成失败"},
}

# ============ 预生成缓存（智能预生成）============
prefetch_cache = {}            # { session_id: { dimension: { question_data, created_at, valid } } }
prefetch_cache_lock = threading.Lock()
PREFETCH_TTL = 300             # 预生成缓存有效期（秒）
report_owners_cache = {"signature": None, "data": {}}
report_scopes_cache = {"signature": None, "data": {}}
session_list_cache = {}        # { filename: { signature, payload } }
session_list_cache_lock = threading.Lock()
list_overload_stats = {
    "sessions_list": {"rejected": 0},
    "reports_list": {"rejected": 0},
}
list_overload_stats_lock = threading.Lock()
list_api_metrics_lock = threading.Lock()
list_api_metrics = {
    "sessions_list": {
        "calls": 0,
        "success": 0,
        "status_429": 0,
        "status_5xx": 0,
        "total_latency_ms": 0.0,
        "latency_samples": deque(maxlen=500),
        "source_sqlite": 0,
        "source_file_scan": 0,
        "source_overload": 0,
        "source_unknown": 0,
        "total_returned_items": 0,
        "total_available_items": 0,
        "total_page_size": 0,
        "scan_calls": 0,
        "total_scan_ms": 0.0,
        "error_reasons": {},
    },
    "reports_list": {
        "calls": 0,
        "success": 0,
        "status_429": 0,
        "status_5xx": 0,
        "total_latency_ms": 0.0,
        "latency_samples": deque(maxlen=500),
        "source_sqlite": 0,
        "source_file_scan": 0,
        "source_overload": 0,
        "source_unknown": 0,
        "total_returned_items": 0,
        "total_available_items": 0,
        "total_page_size": 0,
        "scan_calls": 0,
        "total_scan_ms": 0.0,
        "error_reasons": {},
    },
}
list_cache_metrics = {
    "session_meta": {"hit": 0, "miss": 0},
    "report_owner": {"hit": 0, "miss": 0},
}
meta_index_state = {
    "db_path": "",
    "schema_ready": False,
    "sessions_bootstrapped": False,
    "reports_bootstrapped": False,
}
meta_index_state_lock = threading.Lock()


def _safe_log(text: str) -> None:
    try:
        print(text)
    except UnicodeEncodeError:
        fallback = str(text).encode("ascii", errors="backslashreplace").decode("ascii")
        print(fallback)


def _is_low_priority_ai_call(call_type: str) -> bool:
    lowered = str(call_type or "").strip().lower()
    if not lowered:
        return False
    low_prefixes = ("summary", "doc_summary", "search_decision", "prefetch")
    return any(lowered == prefix or lowered.startswith(f"{prefix}_") for prefix in low_prefixes)


def _get_ai_call_priority_lane(call_type: str) -> str:
    return "low" if _is_low_priority_ai_call(call_type) else "high"


@contextmanager
def ai_call_priority_slot(call_type: str):
    """AI 调度闸门：优先保障问题/报告调用，低优先级调用在高优先级活跃时暂停。"""
    current_depth = int(getattr(ai_priority_local, "depth", 0) or 0)
    lane = _get_ai_call_priority_lane(call_type)
    if current_depth > 0:
        ai_priority_local.depth = current_depth + 1
        try:
            yield {
                "lane": lane,
                "queue_wait_ms": 0.0,
                "nested": True,
            }
        finally:
            ai_priority_local.depth = max(0, int(getattr(ai_priority_local, "depth", 1) or 1) - 1)
        return

    wait_started_at = _time.perf_counter()
    queue_wait_ms = 0.0
    with ai_priority_condition:
        if lane == "high":
            ai_priority_state["high_waiting"] += 1
            ai_priority_state["high_waiting"] = max(0, ai_priority_state["high_waiting"] - 1)
            ai_priority_state["high_running"] += 1
        else:
            while ai_priority_state["high_waiting"] > 0 or ai_priority_state["high_running"] > 0:
                ai_priority_condition.wait(timeout=0.2)
            ai_priority_state["low_running"] += 1
        queue_wait_ms = max(0.0, (_time.perf_counter() - wait_started_at) * 1000.0)

    ai_priority_local.depth = 1
    try:
        yield {
            "lane": lane,
            "queue_wait_ms": round(queue_wait_ms, 2),
            "nested": False,
        }
    finally:
        ai_priority_local.depth = 0
        with ai_priority_condition:
            if lane == "high":
                ai_priority_state["high_running"] = max(0, ai_priority_state["high_running"] - 1)
            else:
                ai_priority_state["low_running"] = max(0, ai_priority_state["low_running"] - 1)
            ai_priority_condition.notify_all()


def _wait_for_prefetch_idle(wait_seconds: float = 0.0) -> bool:
    """预生成仅在主链路空闲时触发，避免与实时出题抢资源。"""
    if not PREFETCH_IDLE_ONLY:
        return True

    deadline = _time.time() + max(0.0, float(wait_seconds or 0.0))
    while True:
        with ai_priority_condition:
            high_waiting = int(ai_priority_state.get("high_waiting", 0) or 0)
            high_running = int(ai_priority_state.get("high_running", 0) or 0)
            low_running = int(ai_priority_state.get("low_running", 0) or 0)
            if (
                high_waiting <= 0
                and high_running <= 0
                and low_running <= PREFETCH_IDLE_MAX_LOW_RUNNING
            ):
                return True

        if _time.time() >= deadline:
            return False
        _time.sleep(0.2)


def _set_first_question_prefetch_priority(session_id: str) -> None:
    if not FIRST_QUESTION_PREFETCH_PRIORITY_ENABLED:
        return
    sid = str(session_id or "").strip()
    if not sid:
        return
    deadline_ts = _time.time() + float(FIRST_QUESTION_PREFETCH_PRIORITY_WINDOW_SECONDS)
    with first_question_prefetch_priority_lock:
        first_question_prefetch_priority[sid] = deadline_ts


def _is_first_question_prefetch_priority_active(session_id: str) -> bool:
    if not FIRST_QUESTION_PREFETCH_PRIORITY_ENABLED:
        return False
    sid = str(session_id or "").strip()
    if not sid:
        return False
    now_ts = _time.time()
    with first_question_prefetch_priority_lock:
        expired_keys = [
            key
            for key, deadline_ts in first_question_prefetch_priority.items()
            if float(deadline_ts or 0.0) <= now_ts
        ]
        for key in expired_keys:
            first_question_prefetch_priority.pop(key, None)
        deadline = float(first_question_prefetch_priority.get(sid, 0.0) or 0.0)
        return deadline > now_ts


def _clear_first_question_prefetch_priority(session_id: str) -> None:
    sid = str(session_id or "").strip()
    if not sid:
        return
    with first_question_prefetch_priority_lock:
        first_question_prefetch_priority.pop(sid, None)


def _try_begin_summary_update(session_id: str) -> bool:
    if not session_id:
        return False
    now_ts = _time.time()
    with summary_update_schedule_lock:
        state = summary_update_schedule_state.get(session_id, {})
        if bool(state.get("inflight")):
            return False
        last_trigger_ts = float(state.get("last_trigger_ts", 0.0) or 0.0)
        if (now_ts - last_trigger_ts) < float(SUMMARY_UPDATE_DEBOUNCE_SECONDS):
            return False
        summary_update_schedule_state[session_id] = {
            "inflight": True,
            "last_trigger_ts": now_ts,
        }
        return True


def _end_summary_update(session_id: str) -> None:
    if not session_id:
        return
    with summary_update_schedule_lock:
        state = summary_update_schedule_state.get(session_id, {})
        state["inflight"] = False
        state["last_trigger_ts"] = _time.time()
        summary_update_schedule_state[session_id] = state


def schedule_context_summary_update_async(session_id: str) -> bool:
    """按节流策略异步更新会话摘要，返回是否成功触发后台任务。"""
    if not _try_begin_summary_update(session_id):
        return False

    def async_update_summary():
        try:
            update_context_summary(session_id)
        except Exception as exc:
            print(f"⚠️ 异步更新摘要失败: {exc}")
        finally:
            _end_summary_update(session_id)

    threading.Thread(target=async_update_summary, daemon=True).start()
    return True


def _build_search_decision_cache_key(topic: str, dimension: str, recent_qa: list) -> str:
    normalized_recent = []
    for item in (recent_qa or [])[-3:]:
        if not isinstance(item, dict):
            continue
        normalized_recent.append({
            "q": str(item.get("question", "") or "").strip(),
            "a": str(item.get("answer", "") or "").strip(),
        })
    payload = {
        "topic": str(topic or "").strip(),
        "dimension": str(dimension or "").strip(),
        "recent_qa": normalized_recent,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _get_search_decision_cache(cache_key: str) -> Optional[dict]:
    if SEARCH_DECISION_CACHE_TTL_SECONDS <= 0:
        return None
    key = str(cache_key or "").strip()
    if not key:
        return None
    now_ts = _time.time()
    with search_decision_cache_lock:
        cached = search_decision_cache.get(key)
        if not isinstance(cached, dict):
            return None
        expire_at = float(cached.get("expire_at", 0.0) or 0.0)
        if expire_at <= now_ts:
            search_decision_cache.pop(key, None)
            return None
        value = cached.get("value")
        if isinstance(value, dict):
            return dict(value)
        return None


def _set_search_decision_cache(cache_key: str, value: dict) -> None:
    if SEARCH_DECISION_CACHE_TTL_SECONDS <= 0:
        return
    key = str(cache_key or "").strip()
    if not key or not isinstance(value, dict):
        return
    now_ts = _time.time()
    expire_at = now_ts + float(SEARCH_DECISION_CACHE_TTL_SECONDS)
    with search_decision_cache_lock:
        # 清理过期项，避免缓存无限增长
        expired_keys = [
            item_key
            for item_key, cached in search_decision_cache.items()
            if float((cached or {}).get("expire_at", 0.0) or 0.0) <= now_ts
        ]
        for item_key in expired_keys:
            search_decision_cache.pop(item_key, None)

        while len(search_decision_cache) >= SEARCH_DECISION_CACHE_MAX_ENTRIES:
            oldest_key = next(iter(search_decision_cache), None)
            if oldest_key is None:
                break
            search_decision_cache.pop(oldest_key, None)

        search_decision_cache[key] = {
            "value": dict(value),
            "expire_at": expire_at,
        }


def _begin_search_decision_inflight(cache_key: str) -> tuple[Optional[threading.Event], bool]:
    key = str(cache_key or "").strip()
    if not key:
        return None, False
    with search_decision_cache_lock:
        inflight = search_decision_inflight.get(key)
        event = inflight.get("event") if isinstance(inflight, dict) else None
        if isinstance(event, threading.Event):
            return event, False

        owner_event = threading.Event()
        search_decision_inflight[key] = {
            "event": owner_event,
            "started_at": _time.time(),
        }
        return owner_event, True


def _end_search_decision_inflight(cache_key: str, owner_event: Optional[threading.Event]) -> None:
    key = str(cache_key or "").strip()
    if not key or not isinstance(owner_event, threading.Event):
        return
    with search_decision_cache_lock:
        inflight = search_decision_inflight.get(key)
        if isinstance(inflight, dict) and inflight.get("event") is owner_event:
            search_decision_inflight.pop(key, None)
    owner_event.set()


def _build_search_result_cache_key(query: str) -> str:
    normalized_query = re.sub(r"\s+", " ", str(query or "").strip()).lower()
    if not normalized_query:
        return ""
    return hashlib.sha1(normalized_query.encode("utf-8")).hexdigest()


def _get_search_result_cache(cache_key: str) -> Optional[list]:
    if SEARCH_RESULT_CACHE_TTL_SECONDS <= 0:
        return None
    key = str(cache_key or "").strip()
    if not key:
        return None
    now_ts = _time.time()
    with search_result_cache_lock:
        cached = search_result_cache.get(key)
        if not isinstance(cached, dict):
            return None
        expire_at = float(cached.get("expire_at", 0.0) or 0.0)
        if expire_at <= now_ts:
            search_result_cache.pop(key, None)
            return None
        value = cached.get("value")
        if isinstance(value, list):
            return [dict(item) for item in value if isinstance(item, dict)]
        return None


def _set_search_result_cache(cache_key: str, value: list) -> None:
    if SEARCH_RESULT_CACHE_TTL_SECONDS <= 0:
        return
    key = str(cache_key or "").strip()
    if not key or not isinstance(value, list):
        return
    normalized = [dict(item) for item in value if isinstance(item, dict)]
    now_ts = _time.time()
    expire_at = now_ts + float(SEARCH_RESULT_CACHE_TTL_SECONDS)
    with search_result_cache_lock:
        expired_keys = [
            item_key
            for item_key, cached in search_result_cache.items()
            if float((cached or {}).get("expire_at", 0.0) or 0.0) <= now_ts
        ]
        for item_key in expired_keys:
            search_result_cache.pop(item_key, None)

        while len(search_result_cache) >= SEARCH_RESULT_CACHE_MAX_ENTRIES:
            oldest_key = next(iter(search_result_cache), None)
            if oldest_key is None:
                break
            search_result_cache.pop(oldest_key, None)

        search_result_cache[key] = {
            "value": normalized,
            "expire_at": expire_at,
        }


def _begin_search_inflight(cache_key: str) -> tuple[Optional[threading.Event], bool]:
    key = str(cache_key or "").strip()
    if not key:
        return None, False
    with search_result_cache_lock:
        inflight = search_result_inflight.get(key)
        event = inflight.get("event") if isinstance(inflight, dict) else None
        if isinstance(event, threading.Event):
            return event, False

        owner_event = threading.Event()
        search_result_inflight[key] = {
            "event": owner_event,
            "started_at": _time.time(),
        }
        return owner_event, True


def _end_search_inflight(cache_key: str, owner_event: Optional[threading.Event]) -> None:
    key = str(cache_key or "").strip()
    if not key or not isinstance(owner_event, threading.Event):
        return
    with search_result_cache_lock:
        inflight = search_result_inflight.get(key)
        if isinstance(inflight, dict) and inflight.get("event") is owner_event:
            search_result_inflight.pop(key, None)
    owner_event.set()


def _build_question_result_cache_key(session_id: str, dimension: str, session_signature: Optional[tuple[int, int]]) -> str:
    signature = session_signature if isinstance(session_signature, tuple) else None
    payload = {
        "session_id": str(session_id or "").strip(),
        "dimension": str(dimension or "").strip(),
        "signature": signature,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _get_question_result_cache(cache_key: str) -> Optional[dict]:
    if QUESTION_RESULT_CACHE_TTL_SECONDS <= 0:
        return None
    key = str(cache_key or "").strip()
    if not key:
        return None
    now_ts = _time.time()
    with question_result_cache_lock:
        cached = question_result_cache.get(key)
        if not isinstance(cached, dict):
            return None
        expire_at = float(cached.get("expire_at", 0.0) or 0.0)
        if expire_at <= now_ts:
            question_result_cache.pop(key, None)
            return None
        value = cached.get("value")
        if isinstance(value, dict):
            return copy.deepcopy(value)
        return None


def _set_question_result_cache(cache_key: str, value: dict) -> None:
    if QUESTION_RESULT_CACHE_TTL_SECONDS <= 0:
        return
    key = str(cache_key or "").strip()
    if not key or not isinstance(value, dict):
        return
    now_ts = _time.time()
    expire_at = now_ts + float(QUESTION_RESULT_CACHE_TTL_SECONDS)
    with question_result_cache_lock:
        expired_keys = [
            item_key
            for item_key, cached in question_result_cache.items()
            if float((cached or {}).get("expire_at", 0.0) or 0.0) <= now_ts
        ]
        for item_key in expired_keys:
            question_result_cache.pop(item_key, None)

        while len(question_result_cache) >= QUESTION_RESULT_CACHE_MAX_ENTRIES:
            oldest_key = next(iter(question_result_cache), None)
            if oldest_key is None:
                break
            question_result_cache.pop(oldest_key, None)

        question_result_cache[key] = {
            "value": copy.deepcopy(value),
            "expire_at": expire_at,
        }


def _build_interview_prompt_cache_key(
    session_signature: Optional[tuple[int, int]],
    dimension: str,
    session_id: str = "",
) -> str:
    if not isinstance(session_signature, tuple) or len(session_signature) != 2:
        return ""
    payload = {
        "session_id": str(session_id or "").strip(),
        "signature": session_signature,
        "dimension": str(dimension or "").strip(),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _get_interview_prompt_cache(cache_key: str) -> Optional[tuple[str, list, dict]]:
    if INTERVIEW_PROMPT_CACHE_TTL_SECONDS <= 0:
        return None
    key = str(cache_key or "").strip()
    if not key:
        return None
    now_ts = _time.time()
    with interview_prompt_cache_lock:
        cached = interview_prompt_cache.get(key)
        if not isinstance(cached, dict):
            return None
        expire_at = float(cached.get("expire_at", 0.0) or 0.0)
        if expire_at <= now_ts:
            interview_prompt_cache.pop(key, None)
            return None
        value = cached.get("value")
        if not isinstance(value, dict):
            return None
        prompt = value.get("prompt")
        truncated_docs = value.get("truncated_docs")
        decision_meta = value.get("decision_meta")
        if not isinstance(prompt, str):
            return None
        if not isinstance(truncated_docs, list):
            truncated_docs = []
        if not isinstance(decision_meta, dict):
            decision_meta = {}
        return prompt, copy.deepcopy(truncated_docs), copy.deepcopy(decision_meta)


def _set_interview_prompt_cache(
    cache_key: str,
    prompt: str,
    truncated_docs: list,
    decision_meta: dict,
) -> None:
    if INTERVIEW_PROMPT_CACHE_TTL_SECONDS <= 0:
        return
    key = str(cache_key or "").strip()
    if not key or not isinstance(prompt, str):
        return
    safe_truncated_docs = list(truncated_docs or [])
    safe_decision_meta = copy.deepcopy(decision_meta) if isinstance(decision_meta, dict) else {}

    now_ts = _time.time()
    expire_at = now_ts + float(INTERVIEW_PROMPT_CACHE_TTL_SECONDS)
    with interview_prompt_cache_lock:
        expired_keys = [
            item_key
            for item_key, cached in interview_prompt_cache.items()
            if float((cached or {}).get("expire_at", 0.0) or 0.0) <= now_ts
        ]
        for item_key in expired_keys:
            interview_prompt_cache.pop(item_key, None)

        while len(interview_prompt_cache) >= INTERVIEW_PROMPT_CACHE_MAX_ENTRIES:
            oldest_key = next(iter(interview_prompt_cache), None)
            if oldest_key is None:
                break
            interview_prompt_cache.pop(oldest_key, None)

        interview_prompt_cache[key] = {
            "value": {
                "prompt": prompt,
                "truncated_docs": copy.deepcopy(safe_truncated_docs),
                "decision_meta": safe_decision_meta,
            },
            "expire_at": expire_at,
        }


def safe_load_session(session_file: Path) -> dict:
    """安全加载会话文件，处理 JSON 解析错误"""
    try:
        return json.loads(session_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        _safe_log(f"⚠️ 会话文件损坏: {session_file}, 错误: {e}")
        return None
    except Exception as e:
        _safe_log(f"⚠️ 读取会话文件失败: {session_file}, 错误: {e}")
        return None


def get_file_signature(file_path: Path) -> Optional[tuple[int, int]]:
    try:
        stat = file_path.stat()
        return (int(stat.st_mtime_ns), int(stat.st_size))
    except (FileNotFoundError, OSError):
        return None


def parse_list_pagination_params() -> tuple[int, int, int]:
    page_raw = str(request.args.get("page", "1") or "1").strip()
    page_size_raw = str(request.args.get("page_size", str(LIST_API_DEFAULT_PAGE_SIZE)) or str(LIST_API_DEFAULT_PAGE_SIZE)).strip()

    try:
        page = int(page_raw)
    except Exception:
        page = 1
    if page < 1:
        page = 1

    try:
        page_size = int(page_size_raw)
    except Exception:
        page_size = LIST_API_DEFAULT_PAGE_SIZE
    if page_size < 1:
        page_size = LIST_API_DEFAULT_PAGE_SIZE
    if page_size > LIST_API_MAX_PAGE_SIZE:
        page_size = LIST_API_MAX_PAGE_SIZE

    offset = (page - 1) * page_size
    return page, page_size, offset


def apply_pagination_headers(response, page: int, page_size: int, total: int):
    total_pages = 0 if total <= 0 else ((total - 1) // page_size + 1)
    response.headers["X-Page"] = str(page)
    response.headers["X-Page-Size"] = str(page_size)
    response.headers["X-Total-Count"] = str(total)
    response.headers["X-Total-Pages"] = str(total_pages)
    return response


def build_list_etag(endpoint: str, page: int, page_size: int, total: int, items: list) -> str:
    payload = {
        "endpoint": str(endpoint or ""),
        "page": int(page or 1),
        "page_size": int(page_size or 0),
        "total": int(total or 0),
        "items": items,
    }
    digest = hashlib.md5(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return f'W/"{digest}"'


def build_not_modified_response(etag: str, page: int, page_size: int, total: int):
    response = make_response("", 304)
    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = "private, max-age=2"
    apply_pagination_headers(response, page=page, page_size=page_size, total=total)
    return response


def parse_if_none_match_values() -> set[str]:
    raw = str(request.headers.get("If-None-Match", "") or "").strip()
    if not raw:
        return set()
    return {token.strip() for token in raw.split(",") if token.strip()}


def build_overload_response(endpoint_key: str):
    response = jsonify({
        "error": "请求过于繁忙，请稍后重试",
        "code": "overloaded",
        "endpoint": endpoint_key,
    })
    response.status_code = 429
    response.headers["Retry-After"] = str(LIST_API_RETRY_AFTER_SECONDS)
    return response


def try_acquire_list_semaphore(endpoint_key: str, semaphore: threading.BoundedSemaphore) -> bool:
    acquired = semaphore.acquire(blocking=False)
    if acquired:
        return True

    with list_overload_stats_lock:
        stats = list_overload_stats.setdefault(endpoint_key, {"rejected": 0})
        stats["rejected"] = int(stats.get("rejected", 0)) + 1
        rejected = stats["rejected"]

    if ENABLE_DEBUG_LOG and (rejected == 1 or rejected % 20 == 0):
        _safe_log(f"⚠️ {endpoint_key} 触发过载保护，累计拒绝 {rejected} 次")
    return False


def build_compact_dimensions(dimensions: dict) -> dict:
    if not isinstance(dimensions, dict):
        return {}

    compact = {}
    for key, value in dimensions.items():
        if not isinstance(key, str):
            continue
        if not isinstance(value, dict):
            compact[key] = {"coverage": 0, "score": None}
            continue
        coverage = value.get("coverage", 0)
        try:
            coverage_value = int(coverage)
        except Exception:
            coverage_value = 0
        compact[key] = {
            "coverage": max(0, min(100, coverage_value)),
            "score": value.get("score"),
        }
    return compact


def record_list_cache_metric(cache_name: str, hit: bool) -> None:
    name = str(cache_name or "").strip()
    if not name:
        return
    with list_api_metrics_lock:
        target = list_cache_metrics.setdefault(name, {"hit": 0, "miss": 0})
        key = "hit" if hit else "miss"
        target[key] = int(target.get(key, 0) or 0) + 1


def record_list_request_metric(
    endpoint: str,
    status_code: int,
    latency_ms: float,
    source: str = "unknown",
    page_size: int = 0,
    returned_count: int = 0,
    total_count: int = 0,
    scan_ms: float = 0.0,
    error_reason: str = "",
) -> None:
    ep = str(endpoint or "").strip()
    if ep not in {"sessions_list", "reports_list"}:
        return

    src = str(source or "unknown").strip()
    if src not in {"sqlite", "file_scan", "overload", "unknown"}:
        src = "unknown"

    safe_status = int(status_code or 0)
    safe_latency = float(latency_ms or 0.0)
    safe_scan_ms = float(scan_ms or 0.0)
    safe_page_size = max(0, int(page_size or 0))
    safe_returned = max(0, int(returned_count or 0))
    safe_total = max(0, int(total_count or 0))
    safe_reason = str(error_reason or "").strip()

    with list_api_metrics_lock:
        stat = list_api_metrics.setdefault(ep, {
            "calls": 0,
            "success": 0,
            "status_429": 0,
            "status_5xx": 0,
            "total_latency_ms": 0.0,
            "latency_samples": deque(maxlen=500),
            "source_sqlite": 0,
            "source_file_scan": 0,
            "source_overload": 0,
            "source_unknown": 0,
            "total_returned_items": 0,
            "total_available_items": 0,
            "total_page_size": 0,
            "scan_calls": 0,
            "total_scan_ms": 0.0,
            "error_reasons": {},
        })

        stat["calls"] = int(stat.get("calls", 0) or 0) + 1
        if 200 <= safe_status < 400:
            stat["success"] = int(stat.get("success", 0) or 0) + 1
        if safe_status == 429:
            stat["status_429"] = int(stat.get("status_429", 0) or 0) + 1
        if safe_status >= 500:
            stat["status_5xx"] = int(stat.get("status_5xx", 0) or 0) + 1

        stat["total_latency_ms"] = float(stat.get("total_latency_ms", 0.0) or 0.0) + safe_latency
        samples = stat.get("latency_samples")
        if not isinstance(samples, deque):
            samples = deque(maxlen=500)
            stat["latency_samples"] = samples
        samples.append(safe_latency)

        source_key = f"source_{src}"
        stat[source_key] = int(stat.get(source_key, 0) or 0) + 1
        stat["total_page_size"] = int(stat.get("total_page_size", 0) or 0) + safe_page_size
        stat["total_returned_items"] = int(stat.get("total_returned_items", 0) or 0) + safe_returned
        stat["total_available_items"] = int(stat.get("total_available_items", 0) or 0) + safe_total

        if safe_scan_ms > 0:
            stat["scan_calls"] = int(stat.get("scan_calls", 0) or 0) + 1
            stat["total_scan_ms"] = float(stat.get("total_scan_ms", 0.0) or 0.0) + safe_scan_ms

        if safe_reason:
            reasons = stat.get("error_reasons")
            if not isinstance(reasons, dict):
                reasons = {}
                stat["error_reasons"] = reasons
            reasons[safe_reason] = int(reasons.get(safe_reason, 0) or 0) + 1


def _compute_percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = int((len(ordered) - 1) * percentile)
    idx = max(0, min(len(ordered) - 1, idx))
    return float(ordered[idx])


def _build_stage_latency_profiles(calls: list[dict]) -> dict:
    """按 stage/lane/model 统计时延分位与成功率。"""
    if not isinstance(calls, list):
        return {"sample_count": 0, "groups": [], "stages": {}}

    grouped = {}
    stage_grouped = {}
    sample_count = 0

    for item in calls:
        if not isinstance(item, dict):
            continue
        stage = str(item.get("stage", "") or "").strip().lower()
        if not stage:
            continue

        latency_ms = _safe_float(item.get("response_time_ms", 0.0), 0.0)
        latency_ms = max(0.0, latency_ms)
        lane = str(item.get("lane", "") or "").strip().lower() or "unknown"
        model = str(item.get("model", "") or "").strip() or "unknown"
        success = bool(item.get("success", False))

        sample_count += 1
        key = (stage, lane, model)
        group = grouped.setdefault(key, {"latencies": [], "count": 0, "success": 0})
        group["latencies"].append(latency_ms)
        group["count"] += 1
        if success:
            group["success"] += 1

        stage_group = stage_grouped.setdefault(stage, {"latencies": [], "count": 0, "success": 0})
        stage_group["latencies"].append(latency_ms)
        stage_group["count"] += 1
        if success:
            stage_group["success"] += 1

    groups = []
    for (stage, lane, model), bucket in grouped.items():
        latencies = bucket["latencies"]
        count = int(bucket["count"])
        success = int(bucket["success"])
        groups.append({
            "stage": stage,
            "lane": lane,
            "model": model,
            "count": count,
            "success_rate": round(success / count * 100, 2) if count > 0 else 0.0,
            "p50_ms": round(_compute_percentile(latencies, 0.50), 2),
            "p95_ms": round(_compute_percentile(latencies, 0.95), 2),
            "max_ms": round(max(latencies), 2) if latencies else 0.0,
        })

    groups.sort(key=lambda item: (item.get("stage", ""), item.get("lane", ""), item.get("model", "")))

    stage_summary = {}
    for stage, bucket in stage_grouped.items():
        latencies = bucket["latencies"]
        count = int(bucket["count"])
        success = int(bucket["success"])
        stage_summary[stage] = {
            "count": count,
            "success_rate": round(success / count * 100, 2) if count > 0 else 0.0,
            "p50_ms": round(_compute_percentile(latencies, 0.50), 2),
            "p95_ms": round(_compute_percentile(latencies, 0.95), 2),
        }

    return {
        "sample_count": sample_count,
        "groups": groups,
        "stages": stage_summary,
    }


def get_list_metrics_snapshot() -> dict:
    with list_api_metrics_lock:
        cache_snapshot = {}
        for cache_name, metric in list_cache_metrics.items():
            hit = int(metric.get("hit", 0) or 0)
            miss = int(metric.get("miss", 0) or 0)
            total = hit + miss
            cache_snapshot[cache_name] = {
                "hit": hit,
                "miss": miss,
                "hit_rate": round(hit / total * 100, 2) if total > 0 else 0.0,
            }

        endpoint_snapshot = {}
        for endpoint, stat in list_api_metrics.items():
            calls = int(stat.get("calls", 0) or 0)
            success = int(stat.get("success", 0) or 0)
            latencies = list(stat.get("latency_samples") or [])
            total_latency = float(stat.get("total_latency_ms", 0.0) or 0.0)
            scan_calls = int(stat.get("scan_calls", 0) or 0)
            total_scan_ms = float(stat.get("total_scan_ms", 0.0) or 0.0)
            total_page_size = int(stat.get("total_page_size", 0) or 0)
            total_returned = int(stat.get("total_returned_items", 0) or 0)
            total_available = int(stat.get("total_available_items", 0) or 0)

            endpoint_snapshot[endpoint] = {
                "calls": calls,
                "success": success,
                "status_429": int(stat.get("status_429", 0) or 0),
                "status_5xx": int(stat.get("status_5xx", 0) or 0),
                "avg_latency_ms": round(total_latency / calls, 2) if calls > 0 else 0.0,
                "p95_latency_ms": round(_compute_percentile(latencies, 0.95), 2),
                "p99_latency_ms": round(_compute_percentile(latencies, 0.99), 2),
                "source_sqlite": int(stat.get("source_sqlite", 0) or 0),
                "source_file_scan": int(stat.get("source_file_scan", 0) or 0),
                "source_overload": int(stat.get("source_overload", 0) or 0),
                "source_unknown": int(stat.get("source_unknown", 0) or 0),
                "avg_page_size": round(total_page_size / calls, 2) if calls > 0 else 0.0,
                "avg_returned_items": round(total_returned / calls, 2) if calls > 0 else 0.0,
                "avg_total_items": round(total_available / calls, 2) if calls > 0 else 0.0,
                "scan_calls": scan_calls,
                "avg_scan_ms": round(total_scan_ms / scan_calls, 2) if scan_calls > 0 else 0.0,
                "error_reasons": dict(stat.get("error_reasons") or {}),
            }

    return {
        "endpoints": endpoint_snapshot,
        "cache": cache_snapshot,
    }


def reset_list_metrics() -> None:
    with list_api_metrics_lock:
        for endpoint in ("sessions_list", "reports_list"):
            stat = list_api_metrics.setdefault(endpoint, {})
            stat.clear()
            stat.update({
                "calls": 0,
                "success": 0,
                "status_429": 0,
                "status_5xx": 0,
                "total_latency_ms": 0.0,
                "latency_samples": deque(maxlen=500),
                "source_sqlite": 0,
                "source_file_scan": 0,
                "source_overload": 0,
                "source_unknown": 0,
                "total_returned_items": 0,
                "total_available_items": 0,
                "total_page_size": 0,
                "scan_calls": 0,
                "total_scan_ms": 0.0,
                "error_reasons": {},
            })

        for cache_name in ("session_meta", "report_owner", "report_scope"):
            metric = list_cache_metrics.setdefault(cache_name, {"hit": 0, "miss": 0})
            metric["hit"] = 0
            metric["miss"] = 0


def get_meta_index_db_path() -> Path:
    return DATA_DIR / "meta_index.db"


def ensure_meta_index_schema() -> None:
    db_path = get_meta_index_db_path().resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path_text = str(db_path)

    with meta_index_state_lock:
        if meta_index_state.get("db_path") != db_path_text:
            meta_index_state["db_path"] = db_path_text
            meta_index_state["schema_ready"] = False
            meta_index_state["sessions_bootstrapped"] = False
            meta_index_state["reports_bootstrapped"] = False

        if meta_index_state.get("schema_ready"):
            return

        with sqlite3.connect(db_path, timeout=5) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS session_index (
                    session_id TEXT PRIMARY KEY,
                    file_name TEXT NOT NULL UNIQUE,
                    owner_user_id INTEGER NOT NULL,
                    instance_scope_key TEXT NOT NULL DEFAULT '',
                    topic TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'in_progress',
                    created_at TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL DEFAULT '',
                    interview_count INTEGER NOT NULL DEFAULT 0,
                    scenario_id TEXT NOT NULL DEFAULT '',
                    scenario_config_json TEXT NOT NULL DEFAULT '{}',
                    dimensions_json TEXT NOT NULL DEFAULT '{}',
                    file_mtime_ns INTEGER NOT NULL DEFAULT 0,
                    file_size INTEGER NOT NULL DEFAULT 0,
                    indexed_at TEXT NOT NULL
                )
                """
            )
            session_columns = {
                str(row[1]): True
                for row in conn.execute("PRAGMA table_info(session_index)").fetchall()
            }
            if "instance_scope_key" not in session_columns:
                conn.execute("ALTER TABLE session_index ADD COLUMN instance_scope_key TEXT NOT NULL DEFAULT ''")

            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_session_index_owner_scope_updated ON session_index(owner_user_id, instance_scope_key, updated_at DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_session_index_owner_scope_created ON session_index(owner_user_id, instance_scope_key, created_at DESC)"
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS report_index (
                    file_name TEXT PRIMARY KEY,
                    owner_user_id INTEGER NOT NULL,
                    instance_scope_key TEXT NOT NULL DEFAULT '',
                    deleted INTEGER NOT NULL DEFAULT 0,
                    size INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT '',
                    file_mtime_ns INTEGER NOT NULL DEFAULT 0,
                    file_size INTEGER NOT NULL DEFAULT 0,
                    indexed_at TEXT NOT NULL
                )
                """
            )

            report_columns = {
                str(row[1]): True
                for row in conn.execute("PRAGMA table_info(report_index)").fetchall()
            }
            if "instance_scope_key" not in report_columns:
                conn.execute("ALTER TABLE report_index ADD COLUMN instance_scope_key TEXT NOT NULL DEFAULT ''")

            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_report_index_owner_scope_deleted_created ON report_index(owner_user_id, instance_scope_key, deleted, created_at DESC)"
            )

        meta_index_state["schema_ready"] = True


def get_meta_index_connection() -> sqlite3.Connection:
    ensure_meta_index_schema()
    conn = sqlite3.connect(get_meta_index_db_path().resolve(), timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def _decode_index_json(raw_text: str, default):
    text = str(raw_text or "").strip()
    if not text:
        return default
    try:
        parsed = json.loads(text)
        return parsed
    except Exception:
        return default


def _build_session_index_record(session_file: Path, session_data: dict) -> Optional[dict]:
    if not isinstance(session_data, dict):
        return None

    session_id = str(session_data.get("session_id") or "").strip()
    if not session_id:
        return None

    try:
        owner_user_id = int(session_data.get("owner_user_id"))
    except (TypeError, ValueError):
        return None
    if owner_user_id <= 0:
        return None

    signature = get_file_signature(session_file) or (0, 0)
    interview_log = session_data.get("interview_log", [])
    interview_count = len(interview_log) if isinstance(interview_log, list) else 0

    scenario_config = session_data.get("scenario_config")
    if isinstance(scenario_config, (dict, list)):
        scenario_config_json = json.dumps(scenario_config, ensure_ascii=False)
    else:
        scenario_config_json = "{}"

    dimensions_json = json.dumps(
        build_compact_dimensions(session_data.get("dimensions", {})),
        ensure_ascii=False,
    )

    return {
        "session_id": session_id,
        "file_name": session_file.name,
        "owner_user_id": owner_user_id,
        "instance_scope_key": get_session_instance_scope_key(session_data),
        "topic": str(session_data.get("topic") or ""),
        "status": str(session_data.get("status") or "in_progress"),
        "created_at": str(session_data.get("created_at") or ""),
        "updated_at": str(session_data.get("updated_at") or ""),
        "interview_count": int(interview_count),
        "scenario_id": str(session_data.get("scenario_id") or ""),
        "scenario_config_json": scenario_config_json,
        "dimensions_json": dimensions_json,
        "file_mtime_ns": int(signature[0]),
        "file_size": int(signature[1]),
        "indexed_at": get_utc_now(),
    }


def _upsert_session_index_record(record: dict) -> None:
    if not isinstance(record, dict):
        return

    with get_meta_index_connection() as conn:
        conn.execute(
            "DELETE FROM session_index WHERE file_name = ? AND session_id <> ?",
            (record["file_name"], record["session_id"]),
        )
        conn.execute(
            """
            INSERT INTO session_index (
                session_id, file_name, owner_user_id, instance_scope_key, topic, status,
                created_at, updated_at, interview_count, scenario_id,
                scenario_config_json, dimensions_json, file_mtime_ns,
                file_size, indexed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                file_name=excluded.file_name,
                owner_user_id=excluded.owner_user_id,
                instance_scope_key=excluded.instance_scope_key,
                topic=excluded.topic,
                status=excluded.status,
                created_at=excluded.created_at,
                updated_at=excluded.updated_at,
                interview_count=excluded.interview_count,
                scenario_id=excluded.scenario_id,
                scenario_config_json=excluded.scenario_config_json,
                dimensions_json=excluded.dimensions_json,
                file_mtime_ns=excluded.file_mtime_ns,
                file_size=excluded.file_size,
                indexed_at=excluded.indexed_at
            """,
            (
                record["session_id"],
                record["file_name"],
                record["owner_user_id"],
                record["instance_scope_key"],
                record["topic"],
                record["status"],
                record["created_at"],
                record["updated_at"],
                record["interview_count"],
                record["scenario_id"],
                record["scenario_config_json"],
                record["dimensions_json"],
                record["file_mtime_ns"],
                record["file_size"],
                record["indexed_at"],
            ),
        )


def save_session_json_and_sync(session_file: Path, session_data: dict) -> None:
    session_file.write_text(
        json.dumps(session_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    try:
        record = _build_session_index_record(session_file, session_data)
        if record:
            _upsert_session_index_record(record)
    except Exception as exc:
        if ENABLE_DEBUG_LOG:
            _safe_log(f"⚠️ 同步 session_index 失败: {session_file.name}, 错误: {exc}")


def remove_session_index_record(session_id: str = "", file_name: str = "") -> None:
    sid = str(session_id or "").strip()
    fname = str(file_name or "").strip()
    if not sid and not fname:
        return

    with get_meta_index_connection() as conn:
        if sid and fname:
            conn.execute(
                "DELETE FROM session_index WHERE session_id = ? OR file_name = ?",
                (sid, fname),
            )
        elif sid:
            conn.execute("DELETE FROM session_index WHERE session_id = ?", (sid,))
        else:
            conn.execute("DELETE FROM session_index WHERE file_name = ?", (fname,))


def rebuild_session_index_from_disk() -> None:
    records = []
    for session_file in SESSIONS_DIR.glob("*.json"):
        session_data = safe_load_session(session_file)
        record = _build_session_index_record(session_file, session_data)
        if record:
            records.append(record)

    with get_meta_index_connection() as conn:
        conn.execute("DELETE FROM session_index")
        if records:
            conn.executemany(
                """
                INSERT INTO session_index (
                    session_id, file_name, owner_user_id, instance_scope_key, topic, status,
                    created_at, updated_at, interview_count, scenario_id,
                    scenario_config_json, dimensions_json, file_mtime_ns,
                    file_size, indexed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        record["session_id"],
                        record["file_name"],
                        record["owner_user_id"],
                        record["instance_scope_key"],
                        record["topic"],
                        record["status"],
                        record["created_at"],
                        record["updated_at"],
                        record["interview_count"],
                        record["scenario_id"],
                        record["scenario_config_json"],
                        record["dimensions_json"],
                        record["file_mtime_ns"],
                        record["file_size"],
                        record["indexed_at"],
                    )
                    for record in records
                ],
            )


def ensure_session_index_bootstrapped() -> None:
    ensure_meta_index_schema()

    with meta_index_state_lock:
        if meta_index_state.get("sessions_bootstrapped"):
            return
        meta_index_state["sessions_bootstrapped"] = True

    try:
        rebuild_session_index_from_disk()
    except Exception as exc:
        with meta_index_state_lock:
            meta_index_state["sessions_bootstrapped"] = False
        raise RuntimeError(f"初始化 session_index 失败: {exc}") from exc


def query_session_index_for_user(owner_user_id: int, page: int, page_size: int) -> tuple[list[dict], int]:
    offset = (page - 1) * page_size
    scope_key = get_active_instance_scope_key()
    with get_meta_index_connection() as conn:
        total_row = conn.execute(
            "SELECT COUNT(1) AS total FROM session_index WHERE owner_user_id = ? AND instance_scope_key = ?",
            (int(owner_user_id), scope_key),
        ).fetchone()
        total = int((total_row["total"] if total_row else 0) or 0)

        rows = conn.execute(
            """
            SELECT
                session_id, topic, status, created_at, updated_at,
                interview_count, scenario_id, scenario_config_json, dimensions_json
            FROM session_index
            WHERE owner_user_id = ? AND instance_scope_key = ?
            ORDER BY updated_at DESC
            LIMIT ? OFFSET ?
            """,
            (int(owner_user_id), scope_key, int(page_size), int(offset)),
        ).fetchall()

    result = []
    for row in rows:
        result.append({
            "session_id": row["session_id"],
            "topic": row["topic"],
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "interview_count": int(row["interview_count"] or 0),
            "scenario_id": row["scenario_id"],
            "scenario_config": _decode_index_json(row["scenario_config_json"], {}),
            "dimensions": _decode_index_json(row["dimensions_json"], {}),
        })
    return result, total


def _build_report_index_record(
    file_name: str,
    owner_user_id: int,
    deleted: bool,
    instance_scope_key: object = "",
) -> Optional[dict]:
    name = str(file_name or "").strip()
    if not name or not name.endswith(".md"):
        return None
    if int(owner_user_id) <= 0:
        return None

    reports_root = REPORTS_DIR.resolve()
    report_path = (REPORTS_DIR / name).resolve()
    if report_path.parent != reports_root:
        return None

    signature = get_file_signature(report_path)
    if signature is None:
        return None

    stat = report_path.stat()
    return {
        "file_name": name,
        "owner_user_id": int(owner_user_id),
        "instance_scope_key": get_record_instance_scope_key(instance_scope_key),
        "deleted": 1 if deleted else 0,
        "size": int(stat.st_size),
        "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        "file_mtime_ns": int(signature[0]),
        "file_size": int(signature[1]),
        "indexed_at": get_utc_now(),
    }


def _upsert_report_index_record(record: dict) -> None:
    if not isinstance(record, dict):
        return

    with get_meta_index_connection() as conn:
        conn.execute(
            """
            INSERT INTO report_index (
                file_name, owner_user_id, instance_scope_key, deleted, size, created_at,
                file_mtime_ns, file_size, indexed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(file_name) DO UPDATE SET
                owner_user_id=excluded.owner_user_id,
                instance_scope_key=excluded.instance_scope_key,
                deleted=excluded.deleted,
                size=excluded.size,
                created_at=excluded.created_at,
                file_mtime_ns=excluded.file_mtime_ns,
                file_size=excluded.file_size,
                indexed_at=excluded.indexed_at
            """,
            (
                record["file_name"],
                record["owner_user_id"],
                record["instance_scope_key"],
                record["deleted"],
                record["size"],
                record["created_at"],
                record["file_mtime_ns"],
                record["file_size"],
                record["indexed_at"],
            ),
        )


def remove_report_index_record(file_name: str) -> None:
    name = str(file_name or "").strip()
    if not name:
        return
    with get_meta_index_connection() as conn:
        conn.execute("DELETE FROM report_index WHERE file_name = ?", (name,))


def sync_report_index_for_filename(
    file_name: str,
    owner_user_id: Optional[int] = None,
    deleted: Optional[bool] = None,
    instance_scope_key: Optional[object] = None,
) -> None:
    name = str(file_name or "").strip()
    if not name:
        return

    if owner_user_id is None:
        owner_user_id = get_report_owner_id(name)
    owner_id = int(owner_user_id or 0)
    if owner_id <= 0:
        remove_report_index_record(name)
        return

    scope_key = get_report_scope_key(name) if instance_scope_key is None else get_record_instance_scope_key(instance_scope_key)
    is_deleted = bool(deleted) if deleted is not None else (name in get_deleted_reports())
    record = _build_report_index_record(name, owner_id, is_deleted, scope_key)
    if not record:
        remove_report_index_record(name)
        return
    _upsert_report_index_record(record)


def rebuild_report_index_from_sources() -> None:
    owner_map = load_report_owners()
    scope_map = load_report_scopes()
    deleted_set = get_deleted_reports()
    records = []
    for report_name, owner_id in owner_map.items():
        record = _build_report_index_record(
            report_name,
            int(owner_id),
            report_name in deleted_set,
            scope_map.get(report_name, ""),
        )
        if record:
            records.append(record)

    with get_meta_index_connection() as conn:
        conn.execute("DELETE FROM report_index")
        if records:
            conn.executemany(
                """
                INSERT INTO report_index (
                    file_name, owner_user_id, instance_scope_key, deleted, size, created_at,
                    file_mtime_ns, file_size, indexed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        record["file_name"],
                        record["owner_user_id"],
                        record["instance_scope_key"],
                        record["deleted"],
                        record["size"],
                        record["created_at"],
                        record["file_mtime_ns"],
                        record["file_size"],
                        record["indexed_at"],
                    )
                    for record in records
                ],
            )


def ensure_report_index_bootstrapped() -> None:
    ensure_meta_index_schema()

    with meta_index_state_lock:
        if meta_index_state.get("reports_bootstrapped"):
            return
        meta_index_state["reports_bootstrapped"] = True

    try:
        rebuild_report_index_from_sources()
    except Exception as exc:
        with meta_index_state_lock:
            meta_index_state["reports_bootstrapped"] = False
        raise RuntimeError(f"初始化 report_index 失败: {exc}") from exc


def query_report_index_for_user(owner_user_id: int, page: int, page_size: int) -> tuple[list[dict], int]:
    offset = (page - 1) * page_size
    scope_key = get_active_instance_scope_key()
    with get_meta_index_connection() as conn:
        total_row = conn.execute(
            "SELECT COUNT(1) AS total FROM report_index WHERE owner_user_id = ? AND instance_scope_key = ? AND deleted = 0",
            (int(owner_user_id), scope_key),
        ).fetchone()
        total = int((total_row["total"] if total_row else 0) or 0)

        rows = conn.execute(
            """
            SELECT file_name, size, created_at
            FROM report_index
            WHERE owner_user_id = ? AND instance_scope_key = ? AND deleted = 0
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (int(owner_user_id), scope_key, int(page_size), int(offset)),
        ).fetchall()

    return ([
        {
            "name": row["file_name"],
            "path": str((REPORTS_DIR / row["file_name"]).resolve()),
            "size": int(row["size"] or 0),
            "created_at": str(row["created_at"] or ""),
        }
        for row in rows
    ], total)


def get_auth_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(AUTH_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


AUTH_META_INSTANCE_KEY = "auth_instance_id"
auth_instance_cache = {
    "db_path": "",
    "value": "",
}
auth_instance_cache_lock = threading.Lock()


def get_auth_instance_id(force_refresh: bool = False) -> str:
    """返回当前鉴权库实例标识，用于拦截跨实例会话串号。"""
    db_path = str(AUTH_DB_PATH.resolve())
    if not force_refresh:
        with auth_instance_cache_lock:
            if auth_instance_cache.get("db_path") == db_path and auth_instance_cache.get("value"):
                return str(auth_instance_cache.get("value"))

    with get_auth_db_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS auth_meta (
                meta_key TEXT PRIMARY KEY,
                meta_value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        row = conn.execute(
            "SELECT meta_value FROM auth_meta WHERE meta_key = ? LIMIT 1",
            (AUTH_META_INSTANCE_KEY,),
        ).fetchone()
        value = str((row["meta_value"] if row else "") or "").strip()
        if not value:
            value = secrets.token_hex(16)
            now_iso = datetime.now(timezone.utc).isoformat()
            conn.execute(
                """
                INSERT INTO auth_meta (meta_key, meta_value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(meta_key) DO UPDATE SET
                    meta_value = excluded.meta_value,
                    updated_at = excluded.updated_at
                """,
                (AUTH_META_INSTANCE_KEY, value, now_iso),
            )
            conn.commit()

    with auth_instance_cache_lock:
        auth_instance_cache["db_path"] = db_path
        auth_instance_cache["value"] = value
    return value


def init_auth_db() -> None:
    with get_auth_db_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE,
                phone TEXT UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                CHECK (email IS NOT NULL OR phone IS NOT NULL)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_users_phone ON users(phone)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS wechat_identities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                app_id TEXT NOT NULL,
                openid TEXT NOT NULL,
                unionid TEXT,
                nickname TEXT NOT NULL DEFAULT '',
                avatar_url TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE (app_id, openid),
                UNIQUE (unionid),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_wechat_identities_user_id ON wechat_identities(user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_wechat_identities_unionid ON wechat_identities(unionid)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS auth_sms_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone TEXT NOT NULL,
                scene TEXT NOT NULL,
                code_hash TEXT NOT NULL,
                request_ip TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                consumed_at TEXT,
                attempts INTEGER NOT NULL DEFAULT 0,
                max_attempts INTEGER NOT NULL DEFAULT 5
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_auth_sms_codes_phone_scene ON auth_sms_codes(phone, scene)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_auth_sms_codes_created_at ON auth_sms_codes(created_at)")
        conn.commit()
    # 初始化并缓存鉴权库实例标识（多实例时用于识别“错库会话”）。
    get_auth_instance_id(force_refresh=True)


def normalize_phone_number(raw_phone: str) -> str:
    normalized = re.sub(r"[\s-]", "", raw_phone or "")
    if normalized.startswith("+86"):
        normalized = normalized[3:]
    elif normalized.startswith("86") and len(normalized) == 13:
        normalized = normalized[2:]
    return normalized


def normalize_account(account: str) -> tuple[str, str]:
    account_text = str(account or "").strip()
    if not account_text:
        return "", "手机号不能为空"

    phone = normalize_phone_number(account_text)
    if not AUTH_PHONE_PATTERN.match(phone):
        return "", "请输入有效的手机号（中国大陆 11 位）"
    return phone, ""


AUTH_SMS_SCENES = {"login", "bind", "recover"}


def normalize_sms_scene(scene: str) -> str:
    value = str(scene or "").strip().lower()
    if value not in AUTH_SMS_SCENES:
        return "login"
    return value


def get_request_ip() -> str:
    forwarded_for = str(request.headers.get("X-Forwarded-For", "")).strip()
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return str(request.remote_addr or "").strip()


def _parse_iso_datetime(text: str) -> Optional[datetime]:
    value = str(text or "").strip()
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except Exception:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _sms_signing_secret() -> str:
    configured = _first_non_empty(
        _cfg_text("SMS_CODE_SIGNING_SECRET", ""),
        CONFIG_SECRET_KEY,
        str(app.secret_key or ""),
        "deepvision-dev-sms-secret",
    )
    return configured


def hash_sms_code(phone: str, scene: str, code: str) -> str:
    payload = f"{normalize_phone_number(phone)}|{normalize_sms_scene(scene)}|{str(code or '').strip()}|{_sms_signing_secret()}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def generate_sms_code() -> str:
    lower = 10 ** (SMS_CODE_LENGTH - 1)
    upper = (10 ** SMS_CODE_LENGTH) - 1
    return str(secrets.randbelow(upper - lower + 1) + lower)


def resolve_sms_code_for_issue() -> str:
    configured = str(SMS_TEST_CODE or "").strip()
    if configured and re.fullmatch(rf"\d{{{SMS_CODE_LENGTH}}}", configured):
        return configured
    return generate_sms_code()


def resolve_sms_template_id(scene: str) -> str:
    scene_value = normalize_sms_scene(scene)
    if scene_value == "bind":
        return JD_SMS_TEMPLATE_ID_BIND or JD_SMS_TEMPLATE_ID_LOGIN
    if scene_value == "recover":
        return JD_SMS_TEMPLATE_ID_RECOVER or JD_SMS_TEMPLATE_ID_LOGIN
    return JD_SMS_TEMPLATE_ID_LOGIN


def is_jd_sms_configured(scene: str = "login") -> tuple[bool, str]:
    if SMS_PROVIDER != "jdcloud":
        return False, "短信服务未配置为京东云"
    if not JD_SMS_ACCESS_KEY_ID or not JD_SMS_ACCESS_KEY_SECRET:
        return False, "京东云短信 AK/SK 未配置"
    if not JD_SMS_SIGN_ID:
        return False, "京东云短信 signId 未配置"
    if not resolve_sms_template_id(scene):
        return False, "京东云短信模板未配置"
    if not JD_SMS_SDK_AVAILABLE:
        return False, "未安装 jdcloud-sdk，请先安装后再启用京东云发码"
    return True, ""


def send_sms_code_via_jdcloud(phone: str, code: str, scene: str) -> tuple[bool, str]:
    configured, reason = is_jd_sms_configured(scene)
    if not configured:
        return False, reason

    template_id = resolve_sms_template_id(scene)
    try:
        credential = JdCredential(JD_SMS_ACCESS_KEY_ID, JD_SMS_ACCESS_KEY_SECRET)
        config = JdConfig({"timeout": JD_SMS_TIMEOUT})
        sms_client = JdSmsClient(credential=credential, config=config)
        request_params = {
            "regionId": JD_SMS_REGION_ID,
            "signId": JD_SMS_SIGN_ID,
            "templateId": template_id,
            "phoneList": [phone],
            "params": [code],
        }
        response = sms_client.batchSend(JdBatchSendRequest(request_params, JD_SMS_REGION_ID))
        if getattr(response, "error", None):
            error_obj = getattr(response, "error")
            message = str(getattr(error_obj, "message", "") or "京东云短信发送失败")
            return False, message
        return True, ""
    except Exception as exc:
        return False, f"京东云短信发送异常: {exc}"


def dispatch_sms_code(phone: str, code: str, scene: str) -> tuple[bool, str]:
    if SMS_PROVIDER == "mock":
        if ENABLE_DEBUG_LOG or app.config.get("TESTING"):
            print(f"[SMS][mock] scene={scene} phone={phone} code={code}")
        return True, ""
    if SMS_PROVIDER == "jdcloud":
        return send_sms_code_via_jdcloud(phone, code, scene)
    return False, "未支持的短信服务提供商"


def _count_sms_sent_today(conn: sqlite3.Connection, phone: str, scene: str) -> int:
    now = datetime.now(timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    row = conn.execute(
        """
        SELECT COUNT(1) AS total
        FROM auth_sms_codes
        WHERE phone = ? AND scene = ? AND created_at >= ?
        """,
        (phone, scene, day_start),
    ).fetchone()
    return int(row["total"]) if row else 0


def _latest_sms_record(conn: sqlite3.Connection, phone: str, scene: str) -> Optional[sqlite3.Row]:
    return conn.execute(
        """
        SELECT id, created_at, expires_at, consumed_at, attempts, max_attempts
        FROM auth_sms_codes
        WHERE phone = ? AND scene = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (phone, scene),
    ).fetchone()


def issue_sms_code(phone: str, scene: str, request_ip: str = "") -> tuple[bool, str, Optional[dict]]:
    normalized_phone = normalize_phone_number(phone)
    if not AUTH_PHONE_PATTERN.match(normalized_phone):
        return False, "请输入有效的手机号（中国大陆 11 位）", None

    scene_value = normalize_sms_scene(scene)
    now = datetime.now(timezone.utc)

    with get_auth_db_connection() as conn:
        latest = _latest_sms_record(conn, normalized_phone, scene_value)
        if latest:
            latest_created_at = _parse_iso_datetime(latest["created_at"])
            if latest_created_at:
                elapsed = (now - latest_created_at).total_seconds()
                if elapsed < SMS_SEND_COOLDOWN_SECONDS:
                    retry_after = int(max(1, SMS_SEND_COOLDOWN_SECONDS - elapsed))
                    return False, f"请求过于频繁，请 {retry_after}s 后重试", {
                        "retry_after": retry_after,
                        "cooldown_seconds": SMS_SEND_COOLDOWN_SECONDS,
                    }

        sent_today = _count_sms_sent_today(conn, normalized_phone, scene_value)
        if sent_today >= SMS_MAX_SEND_PER_PHONE_PER_DAY:
            return False, "今日验证码发送次数已达上限，请明日再试", {
                "retry_after": 86400,
                "cooldown_seconds": SMS_SEND_COOLDOWN_SECONDS,
            }

    code = resolve_sms_code_for_issue()
    sent_ok, send_error = dispatch_sms_code(normalized_phone, code, scene_value)
    if not sent_ok:
        return False, send_error or "验证码发送失败，请稍后重试", None

    created_at = now.isoformat()
    expires_at = (now + timedelta(seconds=SMS_CODE_TTL_SECONDS)).isoformat()
    with get_auth_db_connection() as conn:
        conn.execute(
            """
            INSERT INTO auth_sms_codes
            (phone, scene, code_hash, request_ip, created_at, expires_at, consumed_at, attempts, max_attempts)
            VALUES (?, ?, ?, ?, ?, ?, NULL, 0, ?)
            """,
            (
                normalized_phone,
                scene_value,
                hash_sms_code(normalized_phone, scene_value, code),
                str(request_ip or "").strip(),
                created_at,
                expires_at,
                SMS_MAX_VERIFY_ATTEMPTS,
            ),
        )
        conn.commit()

    payload = {
        "cooldown_seconds": SMS_SEND_COOLDOWN_SECONDS,
        "retry_after": SMS_SEND_COOLDOWN_SECONDS,
        "expires_in": SMS_CODE_TTL_SECONDS,
        "scene": scene_value,
    }
    if app.config.get("TESTING"):
        payload["test_code"] = code
    return True, "", payload


def verify_sms_code(phone: str, scene: str, code: str, consume: bool = True) -> tuple[bool, str]:
    normalized_phone = normalize_phone_number(phone)
    if not AUTH_PHONE_PATTERN.match(normalized_phone):
        return False, "请输入有效的手机号（中国大陆 11 位）"

    scene_value = normalize_sms_scene(scene)
    code_text = str(code or "").strip()
    if not re.fullmatch(r"\d{4,8}", code_text):
        return False, "请输入有效验证码"

    now = datetime.now(timezone.utc)
    with get_auth_db_connection() as conn:
        row = conn.execute(
            """
            SELECT id, code_hash, expires_at, consumed_at, attempts, max_attempts
            FROM auth_sms_codes
            WHERE phone = ? AND scene = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (normalized_phone, scene_value),
        ).fetchone()
        if not row:
            return False, "请先获取验证码"

        expires_at = _parse_iso_datetime(row["expires_at"])
        if not expires_at or now > expires_at:
            return False, "验证码已过期，请重新获取"

        if row["consumed_at"]:
            return False, "验证码已失效，请重新获取"

        attempts = int(row["attempts"] or 0)
        max_attempts = int(row["max_attempts"] or SMS_MAX_VERIFY_ATTEMPTS)
        if attempts >= max_attempts:
            return False, "验证码错误次数过多，请重新获取"

        expected_hash = str(row["code_hash"] or "")
        provided_hash = hash_sms_code(normalized_phone, scene_value, code_text)
        if expected_hash != provided_hash:
            conn.execute(
                "UPDATE auth_sms_codes SET attempts = attempts + 1 WHERE id = ?",
                (int(row["id"]),),
            )
            conn.commit()
            return False, "验证码错误"

        if consume:
            conn.execute(
                "UPDATE auth_sms_codes SET consumed_at = ? WHERE id = ?",
                (now.isoformat(), int(row["id"])),
            )
            conn.commit()
    return True, ""


def build_user_payload(row: sqlite3.Row) -> dict:
    user_id = int(row["id"])
    wechat_identity = query_wechat_identity_by_user_id(user_id)
    email = row["email"] or ""
    phone = row["phone"] or ""
    return {
        "id": user_id,
        "email": email,
        "phone": phone,
        "account": phone or "",
        "created_at": row["created_at"],
        "wechat_bound": bool(wechat_identity),
        "wechat_nickname": str((wechat_identity or {}).get("nickname") or "").strip(),
        "wechat_avatar_url": str((wechat_identity or {}).get("avatar_url") or "").strip(),
        "is_wechat_shadow_account": bool(email.endswith("@wechat.local") and not phone),
    }


def query_user_by_id(user_id: int) -> Optional[sqlite3.Row]:
    with get_auth_db_connection() as conn:
        return conn.execute(
            "SELECT id, email, phone, password_hash, created_at, updated_at FROM users WHERE id = ? LIMIT 1",
            (user_id,)
        ).fetchone()


def query_user_by_account(phone: str) -> Optional[sqlite3.Row]:
    with get_auth_db_connection() as conn:
        if phone:
            return conn.execute(
                "SELECT id, email, phone, password_hash, created_at, updated_at FROM users WHERE phone = ? LIMIT 1",
                (phone,)
            ).fetchone()
    return None


def query_wechat_identity_by_user_id(user_id: int) -> Optional[dict]:
    with get_auth_db_connection() as conn:
        row = conn.execute(
            """
            SELECT id, user_id, app_id, openid, unionid, nickname, avatar_url, created_at, updated_at
            FROM wechat_identities
            WHERE user_id = ?
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            (int(user_id),)
        ).fetchone()
        return dict(row) if row else None


def sanitize_return_to_path(raw_return_to: str) -> str:
    value = str(raw_return_to or "").strip()
    if not value:
        return "/index.html"
    if any(ch in value for ch in ("\r", "\n")):
        return "/index.html"

    parsed = urlparse(value)
    if parsed.scheme or parsed.netloc:
        return "/index.html"
    if not value.startswith("/") or value.startswith("//"):
        return "/index.html"
    return value


def extract_return_to_from_oauth_state(raw_state: str) -> str:
    state_text = str(raw_state or "").strip()
    if not state_text:
        return ""
    if "." not in state_text:
        return ""

    encoded_part = state_text.split(".", 1)[1].strip()
    if not encoded_part:
        return ""

    try:
        padding = "=" * ((4 - len(encoded_part) % 4) % 4)
        decoded = base64.urlsafe_b64decode((encoded_part + padding).encode("ascii")).decode("utf-8")
    except Exception:
        return ""
    return sanitize_return_to_path(decoded)


def append_auth_query_params(url: str, extra: dict[str, str]) -> str:
    safe_url = sanitize_return_to_path(url)
    parsed = urlparse(safe_url)
    query_dict = dict(parse_qsl(parsed.query, keep_blank_values=True))

    for key, value in extra.items():
        if value is None:
            query_dict.pop(key, None)
        else:
            query_dict[key] = str(value)

    return urlunparse((
        "",
        "",
        parsed.path or "/",
        parsed.params,
        urlencode(query_dict, doseq=True),
        parsed.fragment,
    ))


def build_auth_redirect_url(return_to: str, result: str, message: str = "") -> str:
    query_payload = {"auth_result": result}
    if message:
        query_payload["auth_message"] = message
    return append_auth_query_params(return_to, query_payload)


def get_wechat_oauth_callback_url() -> str:
    configured = str(WECHAT_REDIRECT_URI or "").strip()
    if configured:
        return configured
    root_url = (request.url_root or "").strip().rstrip("/")
    if not root_url:
        return ""
    return f"{root_url}/api/auth/wechat/callback"


def get_wechat_login_unavailable_reason() -> str:
    if not WECHAT_LOGIN_ENABLED:
        return "微信登录未启用"
    if not WECHAT_APP_ID or not WECHAT_APP_SECRET:
        return "微信登录配置不完整"

    callback_url = get_wechat_oauth_callback_url()
    if not callback_url.startswith("http://") and not callback_url.startswith("https://"):
        return "微信登录回调地址无效"
    return ""


def is_wechat_login_available() -> bool:
    return get_wechat_login_unavailable_reason() == ""


def exchange_wechat_code_for_token(code: str) -> tuple[Optional[dict], str]:
    code_value = str(code or "").strip()
    if not code_value:
        return None, "缺少微信授权 code"

    params = {
        "appid": WECHAT_APP_ID,
        "secret": WECHAT_APP_SECRET,
        "code": code_value,
        "grant_type": "authorization_code",
    }
    try:
        response = requests.get(
            "https://api.weixin.qq.com/sns/oauth2/access_token",
            params=params,
            timeout=WECHAT_OAUTH_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception:
        return None, "微信授权服务异常"

    if not isinstance(payload, dict):
        return None, "微信授权响应格式异常"

    errcode = payload.get("errcode")
    if errcode:
        errmsg = str(payload.get("errmsg") or "").strip()
        detail = f"（{errcode}）"
        if errmsg:
            detail = f"{detail}{errmsg}"
        return None, f"微信授权失败{detail}"

    return payload, ""


def fetch_wechat_user_profile(access_token: str, openid: str) -> tuple[Optional[dict], str]:
    token_value = str(access_token or "").strip()
    openid_value = str(openid or "").strip()
    if not token_value or not openid_value:
        return None, "微信用户信息参数不完整"

    params = {
        "access_token": token_value,
        "openid": openid_value,
        "lang": "zh_CN",
    }
    try:
        response = requests.get(
            "https://api.weixin.qq.com/sns/userinfo",
            params=params,
            timeout=WECHAT_OAUTH_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception:
        return None, "微信用户信息服务异常"

    if not isinstance(payload, dict):
        return None, "微信用户信息响应格式异常"

    errcode = payload.get("errcode")
    if errcode:
        errmsg = str(payload.get("errmsg") or "").strip()
        detail = f"（{errcode}）"
        if errmsg:
            detail = f"{detail}{errmsg}"
        return None, f"拉取微信用户信息失败{detail}"

    return payload, ""


def resolve_user_for_wechat_identity(
    app_id: str,
    openid: str,
    unionid: str = "",
    nickname: str = "",
    avatar_url: str = "",
) -> Optional[sqlite3.Row]:
    app_id_value = str(app_id or "").strip()
    openid_value = str(openid or "").strip()
    unionid_value = str(unionid or "").strip()
    nickname_value = str(nickname or "").strip()
    avatar_url_value = str(avatar_url or "").strip()
    if not app_id_value or not openid_value:
        return None

    now_iso = datetime.now(timezone.utc).isoformat()
    user_id: Optional[int] = None

    with get_auth_db_connection() as conn:
        identity_row = None
        if unionid_value:
            identity_row = conn.execute(
                """
                SELECT id, user_id
                FROM wechat_identities
                WHERE unionid = ?
                LIMIT 1
                """,
                (unionid_value,)
            ).fetchone()

        if not identity_row:
            identity_row = conn.execute(
                """
                SELECT id, user_id
                FROM wechat_identities
                WHERE app_id = ? AND openid = ?
                LIMIT 1
                """,
                (app_id_value, openid_value)
            ).fetchone()

        if identity_row:
            candidate_user_id = int(identity_row["user_id"])
            candidate_user = conn.execute(
                """
                SELECT id
                FROM users
                WHERE id = ?
                LIMIT 1
                """,
                (candidate_user_id,)
            ).fetchone()
            if candidate_user:
                user_id = candidate_user_id
            else:
                conn.execute("DELETE FROM wechat_identities WHERE id = ?", (int(identity_row["id"]),))
                identity_row = None

        if user_id is None:
            import hashlib

            identity_seed = f"{app_id_value}:{unionid_value or openid_value}"
            identity_hash = hashlib.sha256(identity_seed.encode("utf-8")).hexdigest()[:24]
            shadow_email = f"wx_{identity_hash}@wechat.local"

            existing_shadow_user = conn.execute(
                """
                SELECT id
                FROM users
                WHERE email = ?
                LIMIT 1
                """,
                (shadow_email,)
            ).fetchone()
            if existing_shadow_user:
                user_id = int(existing_shadow_user["id"])
            else:
                random_password_hash = generate_password_hash(secrets.token_urlsafe(32), method="pbkdf2:sha256")
                created = conn.execute(
                    """
                    INSERT INTO users (email, phone, password_hash, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (shadow_email, None, random_password_hash, now_iso, now_iso)
                )
                user_id = int(created.lastrowid)

        if identity_row:
            conn.execute(
                """
                UPDATE wechat_identities
                SET user_id = ?, app_id = ?, openid = ?, unionid = ?, nickname = ?, avatar_url = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    user_id,
                    app_id_value,
                    openid_value,
                    unionid_value or None,
                    nickname_value,
                    avatar_url_value,
                    now_iso,
                    int(identity_row["id"]),
                )
            )
        else:
            try:
                conn.execute(
                    """
                    INSERT INTO wechat_identities
                    (user_id, app_id, openid, unionid, nickname, avatar_url, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        app_id_value,
                        openid_value,
                        unionid_value or None,
                        nickname_value,
                        avatar_url_value,
                        now_iso,
                        now_iso,
                    )
                )
            except sqlite3.IntegrityError:
                recovered = None
                if unionid_value:
                    recovered = conn.execute(
                        "SELECT id, user_id FROM wechat_identities WHERE unionid = ? LIMIT 1",
                        (unionid_value,)
                    ).fetchone()
                if not recovered:
                    recovered = conn.execute(
                        "SELECT id, user_id FROM wechat_identities WHERE app_id = ? AND openid = ? LIMIT 1",
                        (app_id_value, openid_value)
                    ).fetchone()
                if not recovered:
                    raise
                user_id = int(recovered["user_id"])
                conn.execute(
                    """
                    UPDATE wechat_identities
                    SET nickname = ?, avatar_url = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (nickname_value, avatar_url_value, now_iso, int(recovered["id"]))
                )

        conn.commit()

    return query_user_by_id(user_id)


def bind_phone_to_user(user_id: int, phone: str) -> tuple[Optional[sqlite3.Row], str]:
    target_user_id = int(user_id)
    normalized_phone = normalize_phone_number(phone)
    if not AUTH_PHONE_PATTERN.match(normalized_phone):
        return None, "请输入有效的手机号（中国大陆 11 位）"

    now_iso = datetime.now(timezone.utc).isoformat()
    with get_auth_db_connection() as conn:
        current_user = conn.execute(
            """
            SELECT id, email, phone, password_hash, created_at, updated_at
            FROM users
            WHERE id = ?
            LIMIT 1
            """,
            (target_user_id,)
        ).fetchone()
        if not current_user:
            return None, "当前登录用户不存在"

        current_phone = str(current_user["phone"] or "").strip()
        if current_phone and current_phone == normalized_phone:
            return current_user, ""
        if current_phone and current_phone != normalized_phone:
            return None, "当前账号已绑定其他手机号，暂不支持直接更换"

        conflict_user = conn.execute(
            """
            SELECT id
            FROM users
            WHERE phone = ?
            LIMIT 1
            """,
            (normalized_phone,)
        ).fetchone()
        if conflict_user and int(conflict_user["id"]) != target_user_id:
            return None, "该手机号已绑定到其他账号"

        conn.execute(
            """
            UPDATE users
            SET phone = ?, updated_at = ?
            WHERE id = ?
            """,
            (normalized_phone, now_iso, target_user_id)
        )
        conn.commit()

    updated_user = query_user_by_id(target_user_id)
    if not updated_user:
        return None, "绑定手机号失败，请稍后重试"
    return updated_user, ""


def bind_wechat_identity_to_user(
    user_id: int,
    app_id: str,
    openid: str,
    unionid: str = "",
    nickname: str = "",
    avatar_url: str = "",
) -> tuple[Optional[sqlite3.Row], str]:
    target_user_id = int(user_id)
    app_id_value = str(app_id or "").strip()
    openid_value = str(openid or "").strip()
    unionid_value = str(unionid or "").strip()
    nickname_value = str(nickname or "").strip()
    avatar_url_value = str(avatar_url or "").strip()

    if not app_id_value or not openid_value:
        return None, "微信身份信息不完整"

    now_iso = datetime.now(timezone.utc).isoformat()
    with get_auth_db_connection() as conn:
        current_user = conn.execute(
            "SELECT id FROM users WHERE id = ? LIMIT 1",
            (target_user_id,)
        ).fetchone()
        if not current_user:
            return None, "当前登录用户不存在"

        bound_for_user = conn.execute(
            """
            SELECT id, app_id, openid, unionid
            FROM wechat_identities
            WHERE user_id = ?
            LIMIT 1
            """,
            (target_user_id,)
        ).fetchone()
        if bound_for_user:
            same_openid = (
                str(bound_for_user["app_id"] or "") == app_id_value
                and str(bound_for_user["openid"] or "") == openid_value
            )
            same_unionid = (
                unionid_value
                and str(bound_for_user["unionid"] or "").strip()
                and str(bound_for_user["unionid"] or "").strip() == unionid_value
            )
            if not (same_openid or same_unionid):
                return None, "当前账号已绑定其他微信，请先解绑后再绑定"

        identity_row = None
        if unionid_value:
            identity_row = conn.execute(
                """
                SELECT id, user_id
                FROM wechat_identities
                WHERE unionid = ?
                LIMIT 1
                """,
                (unionid_value,)
            ).fetchone()
        if not identity_row:
            identity_row = conn.execute(
                """
                SELECT id, user_id
                FROM wechat_identities
                WHERE app_id = ? AND openid = ?
                LIMIT 1
                """,
                (app_id_value, openid_value)
            ).fetchone()

        if identity_row and int(identity_row["user_id"]) != target_user_id:
            return None, "该微信已绑定到其他账号"

        if identity_row:
            conn.execute(
                """
                UPDATE wechat_identities
                SET nickname = ?, avatar_url = ?, updated_at = ?, unionid = ?
                WHERE id = ?
                """,
                (
                    nickname_value,
                    avatar_url_value,
                    now_iso,
                    unionid_value or None,
                    int(identity_row["id"]),
                )
            )
            conn.commit()
        else:
            try:
                conn.execute(
                    """
                    INSERT INTO wechat_identities
                    (user_id, app_id, openid, unionid, nickname, avatar_url, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        target_user_id,
                        app_id_value,
                        openid_value,
                        unionid_value or None,
                        nickname_value,
                        avatar_url_value,
                        now_iso,
                        now_iso,
                    )
                )
                conn.commit()
            except sqlite3.IntegrityError:
                return None, "该微信已绑定到其他账号"

    updated_user = query_user_by_id(target_user_id)
    if not updated_user:
        return None, "绑定微信失败，请稍后重试"
    return updated_user, ""


def get_current_user() -> Optional[sqlite3.Row]:
    user_id = session.get("user_id")
    if not user_id:
        return None

    current_instance_id = str(get_auth_instance_id() or "").strip()
    session_instance_id = str(session.get("auth_instance_id", "") or "").strip()
    if current_instance_id:
        if not session_instance_id:
            session["auth_instance_id"] = current_instance_id
        elif session_instance_id != current_instance_id:
            if ENABLE_DEBUG_LOG:
                _safe_log(
                    f"⚠️ 检测到跨实例登录态，已清理会话: session_instance={session_instance_id}, current_instance={current_instance_id}"
                )
            session.clear()
            return None

    try:
        user_id_int = int(user_id)
    except (TypeError, ValueError):
        session.clear()
        return None

    user_row = query_user_by_id(user_id_int)
    if not user_row:
        session.clear()
        return None

    return user_row


def login_user(user_row: sqlite3.Row) -> None:
    session.clear()
    session.permanent = True
    session["user_id"] = int(user_row["id"])
    session["auth_instance_id"] = str(get_auth_instance_id() or "")


def require_login(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({"error": "请先登录"}), 401
        return func(*args, **kwargs)

    return wrapper


PUBLIC_API_EXACT_PATHS = {
    "/api/auth/sms/send-code",
    "/api/auth/login/code",
    "/api/auth/recover/send-code",
    "/api/auth/recover/login",
    "/api/auth/register",
    "/api/auth/login",
    "/api/auth/logout",
    "/api/auth/wechat/start",
    "/api/auth/wechat/callback",
    "/api/status",
    "/api/status/web-search",
}


@app.before_request
def enforce_auth_for_protected_routes():
    if request.method == "OPTIONS":
        return None

    path = request.path or ""
    if not path.startswith("/api/"):
        return None

    if path in PUBLIC_API_EXACT_PATHS:
        return None

    # 场景列表与详情允许匿名读取；写接口需登录。
    if request.method == "GET" and path.startswith("/api/scenarios"):
        return None

    if not get_current_user():
        return jsonify({"error": "请先登录"}), 401

    return None


init_auth_db()


def load_presentation_map() -> dict:
    if not PRESENTATION_MAP_FILE.exists():
        return {}
    try:
        payload = json.loads(PRESENTATION_MAP_FILE.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return {}
        normalized = {}
        mutated = False
        for raw_name, record in payload.items():
            name = normalize_presentation_report_filename(raw_name)
            if not name:
                mutated = True
                continue
            if not isinstance(record, dict):
                mutated = True
                continue
            if name in normalized:
                previous = normalized.get(name, {})
                previous_ts = datetime.fromisoformat(previous.get("created_at", "1970-01-01T00:00:00")) if previous.get("created_at") else datetime.min
                current_ts = datetime.fromisoformat(record.get("created_at", "1970-01-01T00:00:00")) if record.get("created_at") else datetime.min
                if current_ts >= previous_ts:
                    normalized[name] = record
                mutated = True
            else:
                normalized[name] = record
            if name != raw_name:
                mutated = True
        if mutated:
            save_presentation_map(normalized)
        return normalized
    except Exception:
        return {}


def save_presentation_map(data: dict) -> None:
    try:
        PRESENTATION_MAP_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
    except Exception:
        pass


def normalize_presentation_report_filename(report_filename: Optional[str]) -> str:
    if not isinstance(report_filename, str):
        return ""
    cleaned = report_filename.strip()
    if not cleaned:
        return ""
    if cleaned.lower() in {"null", "undefined", "none"}:
        return ""
    return cleaned


def find_execution_owner_in_map(data: dict, execution_id: str) -> str:
    if not execution_id or not isinstance(data, dict):
        return ""
    for raw_name, record in data.items():
        if not isinstance(record, dict):
            continue
        if record.get("execution_id") != execution_id:
            continue
        normalized_name = normalize_presentation_report_filename(raw_name)
        if normalized_name:
            return normalized_name
    return ""


def get_execution_owner_report(execution_id: str) -> str:
    if not execution_id:
        return ""
    with PRESENTATION_MAP_LOCK:
        data = load_presentation_map()
    return find_execution_owner_in_map(data, execution_id)


def record_presentation_file(report_filename: str, download_info: Optional[dict] = None, pdf_url: Optional[str] = None) -> Optional[dict]:
    report_filename = normalize_presentation_report_filename(report_filename)
    if not report_filename:
        return None
    record = {
        "created_at": datetime.now().isoformat()
    }
    if download_info and download_info.get("path"):
        record.update({
            "path": download_info.get("path"),
            "filename": download_info.get("filename")
        })
    if pdf_url:
        record["pdf_url"] = pdf_url
    if "path" not in record and "pdf_url" not in record:
        return None
    with PRESENTATION_MAP_LOCK:
        data = load_presentation_map()
        data[report_filename] = record
        save_presentation_map(data)
    return record


def record_presentation_execution(report_filename: str, execution_id: str) -> None:
    report_filename = normalize_presentation_report_filename(report_filename)
    if not execution_id or not report_filename:
        return
    with PRESENTATION_MAP_LOCK:
        data = load_presentation_map()
        owner = find_execution_owner_in_map(data, execution_id)
        if owner and owner != report_filename:
            if ENABLE_DEBUG_LOG:
                print(f"⚠️ 忽略跨报告 execution_id 绑定: {execution_id} 已属于 {owner}, 当前={report_filename}")
            return
        record = data.get(report_filename) if isinstance(data.get(report_filename), dict) else {}
        record = record or {}
        stopped_at = record.get("stopped_at")
        stopped_execution_id = str(record.get("stopped_execution_id") or "").strip()
        if stopped_at and (not stopped_execution_id or stopped_execution_id == execution_id):
            if ENABLE_DEBUG_LOG:
                print(f"⚠️ 忽略已停止任务的 execution_id 回写: execution_id={execution_id}, report={report_filename}")
            return
        record["execution_id"] = execution_id
        record.pop("stopped_at", None)
        record.pop("stopped_execution_id", None)
        if "created_at" not in record:
            record["created_at"] = datetime.now().isoformat()
        data[report_filename] = record
        save_presentation_map(data)


def clear_presentation_execution(report_filename: str) -> None:
    report_filename = normalize_presentation_report_filename(report_filename)
    if not report_filename:
        return
    with PRESENTATION_MAP_LOCK:
        data = load_presentation_map()
        record = data.get(report_filename) if isinstance(data.get(report_filename), dict) else {}
        record = record or {}
        if "execution_id" not in record:
            return
        record.pop("execution_id", None)
        data[report_filename] = record
        save_presentation_map(data)


def mark_presentation_stopped(report_filename: str, execution_id: str = "") -> None:
    report_filename = normalize_presentation_report_filename(report_filename)
    if not report_filename:
        return
    with PRESENTATION_MAP_LOCK:
        data = load_presentation_map()
        record = data.get(report_filename) if isinstance(data.get(report_filename), dict) else {}
        record = record or {}
        stopped_execution_id = str(execution_id or "").strip()
        if not stopped_execution_id:
            stopped_execution_id = str(record.get("execution_id") or "").strip()
        record.pop("execution_id", None)
        if stopped_execution_id:
            record["stopped_execution_id"] = stopped_execution_id
        else:
            record.pop("stopped_execution_id", None)
        record["stopped_at"] = datetime.now().isoformat()
        if "created_at" not in record:
            record["created_at"] = datetime.now().isoformat()
        data[report_filename] = record
        save_presentation_map(data)


def clear_presentation_stopped(report_filename: str) -> None:
    report_filename = normalize_presentation_report_filename(report_filename)
    if not report_filename:
        return
    with PRESENTATION_MAP_LOCK:
        data = load_presentation_map()
        record = data.get(report_filename) if isinstance(data.get(report_filename), dict) else {}
        record = record or {}
        if "stopped_at" in record or "stopped_execution_id" in record:
            record.pop("stopped_at", None)
            record.pop("stopped_execution_id", None)
            data[report_filename] = record
            save_presentation_map(data)


def get_presentation_record(report_filename: str) -> Optional[dict]:
    report_filename = normalize_presentation_report_filename(report_filename)
    if not report_filename:
        return None
    with PRESENTATION_MAP_LOCK:
        data = load_presentation_map()
    record = data.get(report_filename)
    return record if isinstance(record, dict) else None


def is_presentation_execution_stopped(report_filename: str, execution_id: str = "") -> bool:
    report_filename = normalize_presentation_report_filename(report_filename)
    if not report_filename:
        return False
    record = get_presentation_record(report_filename) or {}
    stopped_at = record.get("stopped_at")
    if not stopped_at:
        return False
    stopped_execution_id = str(record.get("stopped_execution_id") or "").strip()
    current_execution_id = str(execution_id or "").strip()
    if stopped_execution_id and current_execution_id and stopped_execution_id != current_execution_id:
        return False
    return True


def is_path_under(path: Path, directory: Path) -> bool:
    try:
        resolved_path = path.resolve()
        resolved_dir = directory.resolve()
        return resolved_path == resolved_dir or resolved_dir in resolved_path.parents
    except Exception:
        return False


def update_thinking_status(session_id: str, stage: str, has_search: bool = True):
    """更新思考进度状态（线程安全）"""
    stage_info = THINKING_STAGES.get(stage)
    if not stage_info:
        return

    # 始终使用原始的 stage_index，确保 index 和 message 一致
    # - 有搜索时：分析(0) -> 检索(1) -> 生成(2)
    # - 无搜索时：分析(0) -> 生成(2)，检索阶段被跳过
    index = stage_info["index"]

    with thinking_status_lock:
        thinking_status[session_id] = {
            "stage": stage,
            "stage_index": index,
            "total_stages": 3,  # 总是3个阶段，无搜索时检索会被快速跳过
            "message": stage_info["message"],
        }


def clear_thinking_status(session_id: str):
    """清除思考进度状态"""
    with thinking_status_lock:
        thinking_status.pop(session_id, None)


def update_report_generation_status(session_id: str, stage: str, message: Optional[str] = None, active: bool = True):
    """更新报告生成进度状态（线程安全）"""
    stage_info = REPORT_GENERATION_STAGES.get(stage)
    if not stage_info:
        return

    with report_generation_status_lock:
        existing = report_generation_status.get(session_id)
        merged = dict(existing) if isinstance(existing, dict) else {}
        merged.update({
            "active": active,
            "state": stage,
            "stage_index": stage_info["index"],
            "total_stages": 6,
            "progress": stage_info["progress"],
            "message": message or stage_info["message"],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
        report_generation_status[session_id] = merged


def set_report_generation_metadata(session_id: str, updates: Optional[dict] = None):
    """写入报告生成的扩展元信息（线程安全）。"""
    if not session_id or not isinstance(updates, dict):
        return

    with report_generation_status_lock:
        existing = report_generation_status.get(session_id)
        merged = dict(existing) if isinstance(existing, dict) else {}
        merged.update(updates)
        merged["updated_at"] = datetime.now(timezone.utc).isoformat()
        report_generation_status[session_id] = merged


def get_report_generation_record(session_id: str) -> Optional[dict]:
    if not session_id:
        return None
    with report_generation_status_lock:
        status = report_generation_status.get(session_id)
        if not isinstance(status, dict):
            return None
        return dict(status)


def build_report_generation_payload(record: Optional[dict]) -> dict:
    if not isinstance(record, dict):
        return {"active": False}

    def _safe_int(value, default):
        try:
            return int(value)
        except Exception:
            return default

    payload = {
        "active": bool(record.get("active", False)),
        "processing": bool(record.get("active", False)),
        "state": record.get("state", "queued"),
        "stage_index": _safe_int(record.get("stage_index", 0), 0),
        "total_stages": _safe_int(record.get("total_stages", 6), 6),
        "progress": _safe_int(record.get("progress", 0), 0),
        "message": record.get("message", "正在生成报告..."),
        "updated_at": record.get("updated_at"),
        "request_id": record.get("request_id", ""),
        "action": record.get("action", "generate"),
        "started_at": record.get("started_at", ""),
        "completed_at": record.get("completed_at", ""),
        "report_name": record.get("report_name", ""),
        "report_path": record.get("report_path", ""),
        "ai_generated": record.get("ai_generated"),
        "v3_enabled": record.get("v3_enabled"),
        "report_profile": normalize_report_profile_choice(record.get("report_profile", ""), fallback=REPORT_V3_PROFILE),
        "error": record.get("error", ""),
        "queue_position": _safe_int(record.get("queue_position", 0), 0),
        "queue_pending": _safe_int(record.get("queue_pending", 0), 0),
        "queue_running": _safe_int(record.get("queue_running", 0), 0),
    }

    quality_meta = record.get("report_quality_meta")
    if isinstance(quality_meta, dict):
        payload["report_quality_meta"] = quality_meta

    return payload


def record_report_generation_queue_event(event: str, delta: int = 1) -> None:
    if event not in report_generation_queue_stats:
        return
    try:
        step = int(delta)
    except Exception:
        step = 1
    if step <= 0:
        return
    with report_generation_queue_stats_lock:
        report_generation_queue_stats[event] = int(report_generation_queue_stats.get(event, 0) or 0) + step


def release_report_generation_slot() -> None:
    try:
        report_generation_slots.release()
    except ValueError:
        # 兜底：避免异常场景重复释放导致线程报错
        pass


def get_report_generation_worker_snapshot(include_positions: bool = False) -> dict:
    running = 0
    pending_sessions = []
    stale_sessions = []

    with report_generation_workers_lock:
        for sid, future in list(report_generation_workers.items()):
            if not isinstance(future, Future):
                stale_sessions.append(sid)
                continue
            if future.done():
                stale_sessions.append(sid)
                continue
            if future.running():
                running += 1
            else:
                pending_sessions.append(sid)

        for sid in stale_sessions:
            report_generation_workers.pop(sid, None)

    in_flight = running + len(pending_sessions)

    with report_generation_queue_stats_lock:
        stats = dict(report_generation_queue_stats)

    snapshot = {
        "max_workers": int(REPORT_GENERATION_MAX_WORKERS),
        "max_pending": int(REPORT_GENERATION_MAX_PENDING),
        "in_flight": int(in_flight),
        "running": int(running),
        "pending": int(len(pending_sessions)),
        "available_slots": max(0, int(REPORT_GENERATION_MAX_PENDING) - int(in_flight)),
        "submitted": int(stats.get("submitted", 0) or 0),
        "rejected": int(stats.get("rejected", 0) or 0),
        "completed": int(stats.get("completed", 0) or 0),
        "failed": int(stats.get("failed", 0) or 0),
    }
    if include_positions:
        snapshot["queue_positions"] = {
            sid: idx + 1
            for idx, sid in enumerate(pending_sessions)
        }
    return snapshot


def sync_report_generation_queue_metadata(session_id: str, snapshot: Optional[dict] = None) -> dict:
    queue_snapshot = snapshot if isinstance(snapshot, dict) else get_report_generation_worker_snapshot(include_positions=True)
    if not session_id:
        return queue_snapshot

    with report_generation_status_lock:
        existing = report_generation_status.get(session_id)
        if not isinstance(existing, dict):
            return queue_snapshot

    queue_positions = queue_snapshot.get("queue_positions", {}) if isinstance(queue_snapshot, dict) else {}
    queue_position = 0
    if isinstance(queue_positions, dict):
        try:
            queue_position = int(queue_positions.get(session_id, 0) or 0)
        except Exception:
            queue_position = 0

    set_report_generation_metadata(session_id, {
        "queue_position": queue_position,
        "queue_pending": int(queue_snapshot.get("pending", 0) or 0),
        "queue_running": int(queue_snapshot.get("running", 0) or 0),
    })
    return queue_snapshot


def is_report_generation_worker_alive(session_id: str) -> bool:
    if not session_id:
        return False
    with report_generation_workers_lock:
        worker = report_generation_workers.get(session_id)
        if isinstance(worker, Future) and not worker.done():
            return True
        if worker is not None:
            report_generation_workers.pop(session_id, None)
    return False


def register_report_generation_worker(session_id: str, worker: Future) -> None:
    if not session_id or worker is None:
        return
    with report_generation_workers_lock:
        report_generation_workers[session_id] = worker


def cleanup_report_generation_worker(session_id: str, worker: Optional[Future] = None) -> None:
    if not session_id:
        return
    with report_generation_workers_lock:
        current = report_generation_workers.get(session_id)
        if worker is not None and current is not worker:
            return
        report_generation_workers.pop(session_id, None)


def clear_report_generation_status(session_id: str):
    """清除报告生成进度状态"""
    with report_generation_status_lock:
        report_generation_status.pop(session_id, None)
    cleanup_report_generation_worker(session_id)


# ============ 预生成缓存函数 ============

def get_prefetch_result(session_id: str, dimension: str) -> Optional[dict]:
    """获取预生成结果（线程安全），命中则消费（删除缓存）

    Args:
        session_id: 会话ID
        dimension: 维度名称

    Returns:
        命中则返回问题数据dict，否则返回None
    """
    with prefetch_cache_lock:
        session_cache = prefetch_cache.get(session_id, {})
        cached = session_cache.get(dimension)
        if cached and cached.get("valid"):
            # 检查TTL
            if _time.time() - cached["created_at"] < PREFETCH_TTL:
                # 消费缓存（删除）
                session_cache.pop(dimension, None)
                if ENABLE_DEBUG_LOG:
                    print(f"🚀 预生成缓存命中: session={session_id}, dim={dimension}")
                return cached["question_data"]
            else:
                # 过期，清除
                session_cache.pop(dimension, None)
                if ENABLE_DEBUG_LOG:
                    print(f"⏰ 预生成缓存过期: session={session_id}, dim={dimension}")
    return None


def invalidate_prefetch(session_id: str, dimension: str = None):
    """使预生成缓存失效

    Args:
        session_id: 会话ID
        dimension: 维度名称，如果为None则清除整个会话的缓存
    """
    with prefetch_cache_lock:
        if dimension:
            prefetch_cache.get(session_id, {}).pop(dimension, None)
        else:
            prefetch_cache.pop(session_id, None)


def trigger_prefetch_if_needed(session: dict, current_dimension: str):
    """判断是否需要预生成下一维度首题，如果需要则启动后台线程

    预生成触发条件：当前维度正式问题数 >= 2

    Args:
        session: 会话数据
        current_dimension: 当前维度
    """
    session_id = session.get("session_id")
    interview_log = session.get("interview_log", [])

    # 计算当前维度的正式问题数
    dim_logs = [l for l in interview_log if l.get("dimension") == current_dimension]
    formal_count = len([l for l in dim_logs if not l.get("is_follow_up", False)])

    current_mode_config = get_interview_mode_config(session)
    current_min_formal = current_mode_config.get("formal_questions_per_dim", 2)

    # 当前维度达到最低正式题后，预生成下一维度首题
    if formal_count < current_min_formal:
        return

    # 维度顺序
    dimension_order = ['customer_needs', 'business_process', 'tech_constraints', 'project_constraints']
    current_idx = dimension_order.index(current_dimension) if current_dimension in dimension_order else -1

    # 找下一个未完成的维度
    next_dimension = None
    for i in range(1, len(dimension_order)):
        candidate = dimension_order[(current_idx + i) % len(dimension_order)]
        cand_logs = [l for l in interview_log if l.get("dimension") == candidate]
        cand_formal = len([l for l in cand_logs if not l.get("is_follow_up", False)])

        # 兼容动态场景：构造轻量 session 以读取该会话模式配置
        candidate_min_formal = get_interview_mode_config(session).get("formal_questions_per_dim", 3)
        if cand_formal < candidate_min_formal:
            next_dimension = candidate
            break

    if not next_dimension:
        return

    # 检查缓存中是否已有
    with prefetch_cache_lock:
        existing = prefetch_cache.get(session_id, {}).get(next_dimension)
        if existing and existing.get("valid"):
            return  # 已有有效缓存，不重复生成

    # 启动后台预生成线程
    def do_prefetch():
        try:
            if ENABLE_DEBUG_LOG:
                print(f"🔮 开始预生成: session={session_id}, next_dim={next_dimension}")

            if not _wait_for_prefetch_idle(PREFETCH_IDLE_WAIT_SECONDS):
                if ENABLE_DEBUG_LOG:
                    print(f"⏭️  跳过预生成（主链路繁忙）: session={session_id}, dim={next_dimension}")
                return

            # 重新读取会话数据（可能已更新）
            session_file = SESSIONS_DIR / f"{session_id}.json"
            if not session_file.exists():
                return

            session_data = json.loads(session_file.read_text(encoding="utf-8"))
            session_signature = get_file_signature(session_file)
            next_dim_logs = [l for l in session_data.get("interview_log", [])
                           if l.get("dimension") == next_dimension]

            # 构建预生成的 prompt
            prompt, truncated_docs, _decision_meta = build_interview_prompt(
                session_data, next_dimension, next_dim_logs,
                session_signature=session_signature,
            )

            # 调用 Claude API
            response = call_claude(
                prompt,
                max_tokens=MAX_TOKENS_QUESTION,
                call_type="prefetch",
                truncated_docs=truncated_docs
            )

            if response:
                # 解析响应
                result = parse_question_response(response, debug=False)
                if result:
                    result["dimension"] = next_dimension
                    result["ai_generated"] = True

                    with prefetch_cache_lock:
                        if session_id not in prefetch_cache:
                            prefetch_cache[session_id] = {}
                        prefetch_cache[session_id][next_dimension] = {
                            "question_data": result,
                            "created_at": _time.time(),
                            "topic": session_data.get("topic"),
                            "valid": True,
                        }
                    if ENABLE_DEBUG_LOG:
                        print(f"✅ 预生成完成: session={session_id}, dim={next_dimension}")
                else:
                    if ENABLE_DEBUG_LOG:
                        print(f"⚠️ 预生成解析失败: session={session_id}, dim={next_dimension}")
        except Exception as e:
            print(f"⚠️ 预生成失败: {e}")

    threading.Thread(target=do_prefetch, daemon=True).start()


def prefetch_first_question(session_id: str):
    """后台预生成会话的第一个问题

    在会话创建后调用，异步生成 customer_needs 维度的首题。

    Args:
        session_id: 会话ID
    """
    def do_prefetch():
        try:
            if ENABLE_DEBUG_LOG:
                print(f"🔮 开始预生成首题: session={session_id}")

            priority_active = _is_first_question_prefetch_priority_active(session_id)
            if priority_active:
                if ENABLE_DEBUG_LOG:
                    print(f"⚡ 首题预生成优先窗口生效: session={session_id}")
            elif not _wait_for_prefetch_idle(PREFETCH_IDLE_WAIT_SECONDS):
                if ENABLE_DEBUG_LOG:
                    print(f"⏭️  跳过首题预生成（主链路繁忙）: session={session_id}")
                return

            session_file = SESSIONS_DIR / f"{session_id}.json"
            if not session_file.exists():
                return

            session_data = json.loads(session_file.read_text(encoding="utf-8"))
            session_signature = get_file_signature(session_file)

            # 获取第一个维度（动态场景支持）
            first_dim = get_dimension_order_for_session(session_data)[0] if get_dimension_order_for_session(session_data) else "customer_needs"

            # 首题不依赖任何历史记录
            prompt, truncated_docs, _decision_meta = build_interview_prompt(
                session_data, first_dim, [],
                session_signature=session_signature,
            )

            response, result, tier_used = generate_question_with_tiered_strategy(
                prompt,
                truncated_docs=truncated_docs,
                debug=ENABLE_DEBUG_LOG,
                base_call_type="prefetch_first",
                allow_fast_path=True,
            )
            if ENABLE_DEBUG_LOG:
                print(f"⚙️ 首题预生成通道: {tier_used}")

            if response and result:
                result["dimension"] = first_dim
                result["ai_generated"] = True

                with prefetch_cache_lock:
                    if session_id not in prefetch_cache:
                        prefetch_cache[session_id] = {}
                    prefetch_cache[session_id][first_dim] = {
                        "question_data": result,
                        "created_at": _time.time(),
                        "topic": session_data.get("topic"),
                        "valid": True,
                    }
                if ENABLE_DEBUG_LOG:
                    print(f"✅ 首题预生成完成: session={session_id}")
        except Exception as e:
            print(f"⚠️ 首题预生成失败: {e}")
        finally:
            _clear_first_question_prefetch_priority(session_id)

    threading.Thread(target=do_prefetch, daemon=True).start()


# ============ 性能监控系统 ============

class MetricsCollector:
    """API 性能指标收集器"""

    def __init__(self, metrics_file: Path):
        self.metrics_file = metrics_file
        self._pending_records = deque()
        self._pending_lock = threading.Lock()
        self._file_lock = threading.Lock()
        self._flush_event = threading.Event()
        self._stop_event = threading.Event()
        self._closed = False
        self._flush_interval = float(METRICS_ASYNC_FLUSH_INTERVAL_SECONDS)
        self._flush_batch_size = int(METRICS_ASYNC_BATCH_SIZE)
        self._max_pending = int(METRICS_ASYNC_MAX_PENDING)
        self._ensure_metrics_file()
        self._flush_worker = threading.Thread(
            target=self._flush_loop,
            daemon=True,
            name="metrics-flush-worker",
        )
        self._flush_worker.start()
        try:
            atexit.register(self.close)
        except Exception:
            pass

    def _ensure_metrics_file(self):
        """确保指标文件存在"""
        payload = self._empty_payload()
        with self._file_lock:
            self.metrics_file.parent.mkdir(parents=True, exist_ok=True)
            if not self.metrics_file.exists():
                self.metrics_file.write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

    def _empty_payload(self) -> dict:
        return {
            "calls": [],
            "summary": {
                "total_calls": 0,
                "total_timeouts": 0,
                "total_truncations": 0,
                "total_cache_hits": 0,
                "total_hedge_triggered": 0,
                "avg_response_time": 0,
                "avg_prompt_length": 0,
                "avg_queue_wait_ms": 0,
            },
        }

    def _load_metrics_data(self) -> dict:
        payload = self._empty_payload()
        try:
            if not self.metrics_file.exists():
                return payload
            data = json.loads(self.metrics_file.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return payload

            calls_raw = data.get("calls", [])
            calls = [item for item in calls_raw if isinstance(item, dict)] if isinstance(calls_raw, list) else []
            summary_raw = data.get("summary", {})
            summary = summary_raw if isinstance(summary_raw, dict) else {}
            merged_summary = {
                "total_calls": int(summary.get("total_calls", 0) or 0),
                "total_timeouts": int(summary.get("total_timeouts", 0) or 0),
                "total_truncations": int(summary.get("total_truncations", 0) or 0),
                "total_cache_hits": int(summary.get("total_cache_hits", 0) or 0),
                "total_hedge_triggered": int(summary.get("total_hedge_triggered", 0) or 0),
                "avg_response_time": float(summary.get("avg_response_time", 0) or 0),
                "avg_prompt_length": float(summary.get("avg_prompt_length", 0) or 0),
                "avg_queue_wait_ms": float(summary.get("avg_queue_wait_ms", 0) or 0),
            }
            return {"calls": calls, "summary": merged_summary}
        except Exception:
            return payload

    def _write_metrics_data(self, data: dict) -> None:
        self.metrics_file.parent.mkdir(parents=True, exist_ok=True)
        self.metrics_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _apply_records_to_data(self, data: dict, records: list[dict]) -> dict:
        if not isinstance(data, dict):
            data = self._empty_payload()

        calls = data.get("calls", [])
        if not isinstance(calls, list):
            calls = []
        summary = data.get("summary", {})
        if not isinstance(summary, dict):
            summary = {}
        total_calls = int(summary.get("total_calls", 0) or 0)
        total_timeouts = int(summary.get("total_timeouts", 0) or 0)
        total_truncations = int(summary.get("total_truncations", 0) or 0)
        total_cache_hits = int(summary.get("total_cache_hits", 0) or 0)
        total_hedge_triggered = int(summary.get("total_hedge_triggered", 0) or 0)

        for record in records:
            if not isinstance(record, dict):
                continue
            calls.append(record)
            event_kind = str(record.get("event_kind", "api_call") or "api_call").strip().lower()
            if event_kind != "api_call":
                continue
            total_calls += 1
            if bool(record.get("timeout", False)):
                total_timeouts += 1
            total_truncations += len(record.get("truncated_docs", []) or [])
            if bool(record.get("cache_hit", False)):
                total_cache_hits += 1
            if bool(record.get("hedge_triggered", False)):
                total_hedge_triggered += 1

        if len(calls) > 1000:
            calls = calls[-1000:]

        api_calls = [
            item for item in calls
            if isinstance(item, dict) and str(item.get("event_kind", "api_call") or "api_call").strip().lower() == "api_call"
        ]

        avg_response_time = 0.0
        avg_prompt_length = 0.0
        avg_queue_wait_ms = 0.0
        if api_calls:
            avg_response_time = round(
                sum(float(c.get("response_time_ms", 0) or 0) for c in api_calls) / len(api_calls), 2
            )
            avg_prompt_length = round(
                sum(float(c.get("prompt_length", 0) or 0) for c in api_calls) / len(api_calls), 2
            )
            queue_wait_values = [
                float(c.get("queue_wait_ms", 0) or 0)
                for c in api_calls
                if isinstance(c.get("queue_wait_ms", 0), (int, float))
            ]
            if queue_wait_values:
                avg_queue_wait_ms = round(sum(queue_wait_values) / len(queue_wait_values), 2)

        data["calls"] = calls
        data["summary"] = {
            "total_calls": total_calls,
            "total_timeouts": total_timeouts,
            "total_truncations": total_truncations,
            "total_cache_hits": total_cache_hits,
            "total_hedge_triggered": total_hedge_triggered,
            "avg_response_time": avg_response_time,
            "avg_prompt_length": avg_prompt_length,
            "avg_queue_wait_ms": avg_queue_wait_ms,
        }
        return data

    def _drain_pending_records(self, max_items: Optional[int] = None) -> list[dict]:
        drained = []
        with self._pending_lock:
            if not self._pending_records:
                return drained
            if max_items is None or max_items >= len(self._pending_records):
                while self._pending_records:
                    drained.append(self._pending_records.popleft())
            else:
                for _ in range(max_items):
                    if not self._pending_records:
                        break
                    drained.append(self._pending_records.popleft())
        return drained

    def _flush_pending_records(self, force: bool = False) -> int:
        flushed = 0
        while True:
            batch_size = None if force else self._flush_batch_size
            records = self._drain_pending_records(max_items=batch_size)
            if not records:
                break
            try:
                with self._file_lock:
                    data = self._load_metrics_data()
                    data = self._apply_records_to_data(data, records)
                    self._write_metrics_data(data)
                flushed += len(records)
            except Exception as exc:
                print(f"⚠️  刷新指标失败: {exc}")
                with self._pending_lock:
                    for record in reversed(records):
                        self._pending_records.appendleft(record)
                    while len(self._pending_records) > self._max_pending:
                        self._pending_records.popleft()
                break

            if not force:
                break

        if not force:
            with self._pending_lock:
                has_more = bool(self._pending_records)
            if has_more:
                self._flush_event.set()
        return flushed

    def _flush_loop(self) -> None:
        while not self._stop_event.is_set():
            self._flush_event.wait(timeout=self._flush_interval)
            self._flush_event.clear()
            self._flush_pending_records(force=False)

        # 退出前确保尽量落盘
        self._flush_pending_records(force=True)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._stop_event.set()
        self._flush_event.set()
        try:
            if self._flush_worker.is_alive():
                self._flush_worker.join(timeout=2.0)
        except Exception:
            pass
        self._flush_pending_records(force=True)

    def reset(self) -> None:
        with self._pending_lock:
            self._pending_records.clear()
        with self._file_lock:
            self._write_metrics_data(self._empty_payload())

    def record_api_call(self, call_type: str, prompt_length: int, response_time: float,
                       success: bool, timeout: bool = False, error_msg: str = None,
                       truncated_docs: list = None, max_tokens: int = None,
                       queue_wait_ms: float = 0.0, hedge_triggered: bool = False,
                       cache_hit: bool = False, lane: str = "", model: str = "",
                       stage: str = "", event_kind: str = "api_call"):
        """记录 API 调用指标"""
        try:
            try:
                normalized_queue_wait_ms = max(0.0, float(queue_wait_ms or 0.0))
            except Exception:
                normalized_queue_wait_ms = 0.0
            normalized_lane = str(lane or "").strip().lower()
            normalized_model = str(model or "").strip()
            normalized_stage = str(stage or "").strip().lower()
            normalized_event_kind = str(event_kind or "api_call").strip().lower() or "api_call"
            call_record = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "type": call_type,  # "question" or "report"
                "event_kind": normalized_event_kind,
                "prompt_length": prompt_length,
                "response_time_ms": round(response_time * 1000, 2),
                "max_tokens": max_tokens,
                "success": success,
                "timeout": timeout,
                "error": error_msg,
                "truncated_docs": truncated_docs or [],
                "queue_wait_ms": round(normalized_queue_wait_ms, 2),
                "hedge_triggered": bool(hedge_triggered),
                "cache_hit": bool(cache_hit),
                "lane": normalized_lane,
                "model": normalized_model,
                "stage": normalized_stage,
            }

            with self._pending_lock:
                self._pending_records.append(call_record)
                while len(self._pending_records) > self._max_pending:
                    self._pending_records.popleft()
                pending_count = len(self._pending_records)

            if pending_count >= self._flush_batch_size:
                self._flush_event.set()

        except Exception as e:
            print(f"⚠️  记录指标失败: {e}")

    def get_statistics(self, last_n: int = None) -> dict:
        """获取统计信息"""
        empty_summary = {
            "total_calls": 0,
            "total_timeouts": 0,
            "total_truncations": 0,
            "total_cache_hits": 0,
            "total_hedge_triggered": 0,
            "avg_response_time": 0,
            "avg_prompt_length": 0,
            "avg_queue_wait_ms": 0,
        }
        try:
            self._flush_pending_records(force=True)
            with self._file_lock:
                data = self._load_metrics_data()
            summary_data = data.get("summary", empty_summary)
            if not isinstance(summary_data, dict):
                summary_data = empty_summary
            calls_raw = data.get("calls", [])
            if not isinstance(calls_raw, list):
                calls_raw = []
            calls = [c for c in calls_raw if isinstance(c, dict)]

            if last_n:
                calls = calls[-last_n:]

            api_calls = [
                c for c in calls
                if str(c.get("event_kind", "api_call") or "api_call").strip().lower() == "api_call"
            ]
            stage_samples = [
                c for c in calls
                if str(c.get("stage", "") or "").strip()
            ]
            stage_profiles = _build_stage_latency_profiles(stage_samples)

            if not api_calls:
                return {
                    "period": f"最近 {last_n} 次调用" if last_n else "全部调用",
                    "total_calls": 0,
                    "successful_calls": 0,
                    "failed_calls": 0,
                    "timeout_calls": 0,
                    "timeout_rate": 0,
                    "truncation_events": 0,
                    "truncation_rate": 0,
                    "avg_response_time_ms": 0,
                    "max_response_time_ms": 0,
                    "min_response_time_ms": 0,
                    "avg_prompt_length": 0,
                    "max_prompt_length": 0,
                    "cache_hit_calls": 0,
                    "cache_hit_rate": 0,
                    "hedge_triggered_calls": 0,
                    "hedge_trigger_rate": 0,
                    "avg_queue_wait_ms": 0,
                    "max_queue_wait_ms": 0,
                    "recommendations": [{
                        "level": "info",
                        "message": "暂无数据"
                    }],
                    "summary": {
                        "total_calls": int(summary_data.get("total_calls", 0) or 0),
                        "total_timeouts": int(summary_data.get("total_timeouts", 0) or 0),
                        "total_truncations": int(summary_data.get("total_truncations", 0) or 0),
                        "total_cache_hits": int(summary_data.get("total_cache_hits", 0) or 0),
                        "total_hedge_triggered": int(summary_data.get("total_hedge_triggered", 0) or 0),
                        "avg_response_time": float(summary_data.get("avg_response_time", 0) or 0),
                        "avg_prompt_length": float(summary_data.get("avg_prompt_length", 0) or 0),
                        "avg_queue_wait_ms": float(summary_data.get("avg_queue_wait_ms", 0) or 0),
                    },
                    "stage_profiles": stage_profiles,
                    "calls": [],
                    "message": "暂无数据"
                }

            # 计算统计信息
            total_calls = len(api_calls)
            successful_calls = sum(1 for c in api_calls if bool(c.get("success")))
            timeout_calls = sum(1 for c in api_calls if c.get("timeout", False))
            truncation_events = sum(len(c.get("truncated_docs", [])) for c in api_calls)
            cache_hit_calls = sum(1 for c in api_calls if bool(c.get("cache_hit", False)))
            hedge_triggered_calls = sum(1 for c in api_calls if bool(c.get("hedge_triggered", False)))

            response_times = [
                float(c.get("response_time_ms", 0))
                for c in api_calls
                if bool(c.get("success")) and isinstance(c.get("response_time_ms", 0), (int, float))
            ]
            prompt_lengths = [
                float(c.get("prompt_length", 0))
                for c in api_calls
                if isinstance(c.get("prompt_length", 0), (int, float))
            ]
            queue_wait_values = [
                float(c.get("queue_wait_ms", 0))
                for c in api_calls
                if isinstance(c.get("queue_wait_ms", 0), (int, float))
            ]

            stats = {
                "period": f"最近 {last_n} 次调用" if last_n else "全部调用",
                "total_calls": total_calls,
                "successful_calls": successful_calls,
                "failed_calls": total_calls - successful_calls,
                "timeout_calls": timeout_calls,
                "timeout_rate": round(timeout_calls / total_calls * 100, 2) if total_calls > 0 else 0,
                "truncation_events": truncation_events,
                "truncation_rate": round(truncation_events / total_calls * 100, 2) if total_calls > 0 else 0,
                "avg_response_time_ms": round(sum(response_times) / len(response_times), 2) if response_times else 0,
                "max_response_time_ms": round(max(response_times), 2) if response_times else 0,
                "min_response_time_ms": round(min(response_times), 2) if response_times else 0,
                "avg_prompt_length": round(sum(prompt_lengths) / len(prompt_lengths), 2) if prompt_lengths else 0,
                "max_prompt_length": max(prompt_lengths) if prompt_lengths else 0,
                "cache_hit_calls": cache_hit_calls,
                "cache_hit_rate": round(cache_hit_calls / total_calls * 100, 2) if total_calls > 0 else 0,
                "hedge_triggered_calls": hedge_triggered_calls,
                "hedge_trigger_rate": round(hedge_triggered_calls / total_calls * 100, 2) if total_calls > 0 else 0,
                "avg_queue_wait_ms": round(sum(queue_wait_values) / len(queue_wait_values), 2) if queue_wait_values else 0,
                "max_queue_wait_ms": round(max(queue_wait_values), 2) if queue_wait_values else 0,
            }

            # 生成优化建议
            stats["recommendations"] = self._generate_recommendations(stats)
            stats["summary"] = {
                "total_calls": int(summary_data.get("total_calls", 0) or 0),
                "total_timeouts": int(summary_data.get("total_timeouts", 0) or 0),
                "total_truncations": int(summary_data.get("total_truncations", 0) or 0),
                "total_cache_hits": int(summary_data.get("total_cache_hits", 0) or 0),
                "total_hedge_triggered": int(summary_data.get("total_hedge_triggered", 0) or 0),
                "avg_response_time": float(summary_data.get("avg_response_time", 0) or 0),
                "avg_prompt_length": float(summary_data.get("avg_prompt_length", 0) or 0),
                "avg_queue_wait_ms": float(summary_data.get("avg_queue_wait_ms", 0) or 0),
            }
            stats["stage_profiles"] = stage_profiles
            stats["calls"] = api_calls

            return stats

        except Exception as e:
            return {
                "period": f"最近 {last_n} 次调用" if last_n else "全部调用",
                "total_calls": 0,
                "successful_calls": 0,
                "failed_calls": 0,
                "timeout_calls": 0,
                "timeout_rate": 0,
                "truncation_events": 0,
                "truncation_rate": 0,
                "avg_response_time_ms": 0,
                "max_response_time_ms": 0,
                "min_response_time_ms": 0,
                "avg_prompt_length": 0,
                "max_prompt_length": 0,
                "cache_hit_calls": 0,
                "cache_hit_rate": 0,
                "hedge_triggered_calls": 0,
                "hedge_trigger_rate": 0,
                "avg_queue_wait_ms": 0,
                "max_queue_wait_ms": 0,
                "recommendations": [{
                    "level": "warning",
                    "message": "指标文件异常，已返回空统计"
                }],
                "summary": empty_summary,
                "calls": [],
                "message": f"获取统计信息失败: {e}",
            }

    def _generate_recommendations(self, stats: dict) -> list:
        """基于统计数据生成优化建议"""
        recommendations = []

        # 超时率过高
        if stats["timeout_rate"] > 10:
            recommendations.append({
                "level": "critical",
                "message": f"超时率过高 ({stats['timeout_rate']}%)，建议减少文档长度限制或实施智能摘要"
            })
        elif stats["timeout_rate"] > 5:
            recommendations.append({
                "level": "warning",
                "message": f"超时率偏高 ({stats['timeout_rate']}%)，需要关注"
            })

        # 截断率过高
        if stats["truncation_rate"] > 50:
            recommendations.append({
                "level": "warning",
                "message": f"文档截断频繁 ({stats['truncation_rate']}%)，建议实施智能摘要功能"
            })

        # Prompt 过长
        if stats["avg_prompt_length"] > 8000:
            recommendations.append({
                "level": "warning",
                "message": f"平均 Prompt 长度较大 ({stats['avg_prompt_length']} 字符)，可能影响响应速度"
            })

        # 响应时间过长
        if stats["avg_response_time_ms"] > 60000:
            recommendations.append({
                "level": "warning",
                "message": f"平均响应时间较长 ({stats['avg_response_time_ms']/1000:.1f} 秒)，建议优化 Prompt 长度"
            })
        if float(stats.get("avg_queue_wait_ms", 0) or 0) > 1200:
            recommendations.append({
                "level": "warning",
                "message": f"调度排队时间偏高 ({stats['avg_queue_wait_ms']:.0f} ms)，建议提升高优先级并发资源"
            })

        # 一切正常
        if not recommendations:
            if stats["timeout_rate"] < 5 and stats["truncation_rate"] < 30:
                recommendations.append({
                    "level": "info",
                    "message": "系统运行正常，可考虑适度增加文档长度限制以提升质量"
                })

        return recommendations


# 初始化指标收集器
metrics_collector = MetricsCollector(METRICS_DIR / "api_metrics.json")


def _record_cache_hit_metric(call_type: str) -> None:
    safe_call_type = str(call_type or "").strip() or "cache_hit"
    try:
        metrics_collector.record_api_call(
            call_type=safe_call_type,
            prompt_length=0,
            response_time=0.0,
            success=True,
            cache_hit=True,
        )
    except Exception:
        pass


def resolve_generation_stage(call_type: str = "") -> str:
    lowered = str(call_type or "").strip().lower()
    if not lowered:
        return ""
    if "report_v3_draft" in lowered:
        return "draft_gen"
    if "report_v3_review_round" in lowered:
        return "review_gen"
    if lowered.startswith(("question", "prefetch")):
        return "question_fast" if "_fast" in lowered else "question_full"
    return ""


def record_pipeline_stage_metric(
    stage: str,
    success: bool,
    elapsed_seconds: float,
    lane: str = "",
    model: str = "",
    error_msg: str = "",
) -> None:
    normalized_stage = str(stage or "").strip().lower()
    if not normalized_stage:
        return

    safe_elapsed_seconds = max(0.0, float(elapsed_seconds or 0.0))
    safe_lane = str(lane or "").strip().lower()
    safe_model = str(model or "").strip()
    safe_error = summarize_error_for_log(error_msg, limit=160) if error_msg else None

    try:
        metrics_collector.record_api_call(
            call_type=f"report_v3_stage_{normalized_stage}",
            prompt_length=0,
            response_time=safe_elapsed_seconds,
            success=bool(success),
            timeout=False,
            error_msg=safe_error if not success else None,
            truncated_docs=[],
            max_tokens=0,
            queue_wait_ms=0.0,
            hedge_triggered=False,
            cache_hit=False,
            lane=safe_lane,
            model=safe_model,
            stage=normalized_stage,
            event_kind="pipeline_stage",
        )
    except Exception:
        pass


# AI 客户端初始化（支持问题/报告分网关）
claude_client = None  # 历史兼容：默认指向可用的主客户端
question_ai_client = None
report_ai_client = None
summary_ai_client = None
search_decision_ai_client = None
GATEWAY_CIRCUIT_LANES = ("question", "report", "summary", "search_decision")
gateway_circuit_lock = threading.RLock()


def _new_gateway_circuit_entry() -> dict:
    return {
        "fail_count": 0,
        "first_fail_at": 0.0,
        "cooldown_until": 0.0,
        "last_error_type": "",
    }


gateway_circuit_state = {lane: _new_gateway_circuit_entry() for lane in GATEWAY_CIRCUIT_LANES}


def _normalize_gateway_lane(lane: str) -> str:
    normalized = str(lane or "").strip().lower()
    if normalized in GATEWAY_CIRCUIT_LANES:
        return normalized
    return ""


def _cleanup_gateway_circuit_entry_locked(entry: dict, now_ts: float) -> None:
    cooldown_until = float(entry.get("cooldown_until", 0.0) or 0.0)
    first_fail_at = float(entry.get("first_fail_at", 0.0) or 0.0)
    if cooldown_until > 0 and now_ts >= cooldown_until:
        entry.update(_new_gateway_circuit_entry())
        return

    if first_fail_at > 0 and (now_ts - first_fail_at) > GATEWAY_CIRCUIT_FAILURE_WINDOW_SECONDS and cooldown_until <= 0:
        entry.update(_new_gateway_circuit_entry())


def reset_gateway_circuit_state(lanes: Optional[list[str]] = None) -> None:
    """重置网关熔断状态（测试与运维排障使用）。"""
    if lanes is None:
        normalized_lanes = list(GATEWAY_CIRCUIT_LANES)
    else:
        normalized_lanes = [
            lane_name
            for lane_name in (_normalize_gateway_lane(item) for item in lanes)
            if lane_name
        ]

    with gateway_circuit_lock:
        for lane_name in normalized_lanes:
            gateway_circuit_state[lane_name] = _new_gateway_circuit_entry()


def get_gateway_circuit_snapshot(lane: str) -> dict:
    lane_name = _normalize_gateway_lane(lane)
    if not lane_name:
        return {}

    now_ts = _time.time()
    with gateway_circuit_lock:
        entry = gateway_circuit_state.setdefault(lane_name, _new_gateway_circuit_entry())
        _cleanup_gateway_circuit_entry_locked(entry, now_ts)
        return {
            "fail_count": int(entry.get("fail_count", 0) or 0),
            "first_fail_at": float(entry.get("first_fail_at", 0.0) or 0.0),
            "cooldown_until": float(entry.get("cooldown_until", 0.0) or 0.0),
            "last_error_type": str(entry.get("last_error_type", "") or ""),
            "cooldown_remaining_seconds": max(0.0, float(entry.get("cooldown_until", 0.0) or 0.0) - now_ts),
        }


def is_gateway_lane_in_cooldown(lane: str, now_ts: float = None) -> bool:
    lane_name = _normalize_gateway_lane(lane)
    if not lane_name or not GATEWAY_CIRCUIT_BREAKER_ENABLED:
        return False

    current_ts = float(now_ts) if now_ts is not None else _time.time()
    with gateway_circuit_lock:
        entry = gateway_circuit_state.setdefault(lane_name, _new_gateway_circuit_entry())
        _cleanup_gateway_circuit_entry_locked(entry, current_ts)
        return float(entry.get("cooldown_until", 0.0) or 0.0) > current_ts


def classify_gateway_failure_kind(raw_error_message: str) -> str:
    lowered = str(raw_error_message or "").strip().lower()
    if not lowered:
        return "unknown"
    if "timeout" in lowered or "timed out" in lowered:
        return "timeout"
    if "<html" in lowered or "<!doctype html" in lowered:
        return "html_payload"
    if re.search(r"\b5\d{2}\b", lowered) or "gateway time-out" in lowered or "gateway timeout" in lowered:
        return "http_5xx"
    return "other"


def _should_count_circuit_failure(error_kind: str) -> bool:
    return str(error_kind or "").strip().lower() in {"timeout", "http_5xx", "html_payload"}


def record_gateway_lane_failure(lane: str, error_kind: str, now_ts: float = None) -> dict:
    lane_name = _normalize_gateway_lane(lane)
    normalized_error = str(error_kind or "").strip().lower() or "unknown"
    if not lane_name:
        return {"counted": False, "lane": "", "error_kind": normalized_error}
    if not GATEWAY_CIRCUIT_BREAKER_ENABLED:
        return {"counted": False, "lane": lane_name, "error_kind": normalized_error}
    if not _should_count_circuit_failure(normalized_error):
        return {"counted": False, "lane": lane_name, "error_kind": normalized_error}

    current_ts = float(now_ts) if now_ts is not None else _time.time()
    with gateway_circuit_lock:
        entry = gateway_circuit_state.setdefault(lane_name, _new_gateway_circuit_entry())
        _cleanup_gateway_circuit_entry_locked(entry, current_ts)

        first_fail_at = float(entry.get("first_fail_at", 0.0) or 0.0)
        if first_fail_at <= 0 or (current_ts - first_fail_at) > GATEWAY_CIRCUIT_FAILURE_WINDOW_SECONDS:
            entry["first_fail_at"] = current_ts
            entry["fail_count"] = 0

        entry["fail_count"] = int(entry.get("fail_count", 0) or 0) + 1
        entry["last_error_type"] = normalized_error

        circuit_opened = False
        if entry["fail_count"] >= GATEWAY_CIRCUIT_FAIL_THRESHOLD:
            entry["cooldown_until"] = max(
                float(entry.get("cooldown_until", 0.0) or 0.0),
                current_ts + GATEWAY_CIRCUIT_COOLDOWN_SECONDS,
            )
            circuit_opened = True

        cooldown_until = float(entry.get("cooldown_until", 0.0) or 0.0)
        return {
            "counted": True,
            "lane": lane_name,
            "error_kind": normalized_error,
            "fail_count": int(entry.get("fail_count", 0) or 0),
            "cooldown_until": cooldown_until,
            "cooldown_remaining_seconds": max(0.0, cooldown_until - current_ts),
            "circuit_opened": circuit_opened,
        }


def record_gateway_lane_success(lane: str) -> None:
    lane_name = _normalize_gateway_lane(lane)
    if not lane_name:
        return
    with gateway_circuit_lock:
        gateway_circuit_state[lane_name] = _new_gateway_circuit_entry()

# 检查 API Key 是否有效
def is_valid_api_key(api_key: str) -> bool:
    """检查 API Key 是否有效（不是默认占位符）"""
    if not api_key:
        return False
    placeholder_patterns = [
        "your-", "your_", "example", "test", "placeholder",
        "api-key", "apikey", "YOUR-", "YOUR_"
    ]
    api_key_lower = api_key.lower()
    for pattern in placeholder_patterns:
        if pattern in api_key_lower:
            return False
    return True


def _create_anthropic_client(api_key: str, base_url: str, use_bearer_auth: bool = False):
    kwargs = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    if use_bearer_auth:
        kwargs["default_headers"] = {"Authorization": f"Bearer {api_key}"}
    return anthropic.Anthropic(**kwargs)


def _init_lane_client(lane_name: str, api_key: str, base_url: str, test_model: str, use_bearer_auth: bool = False):
    if not is_valid_api_key(api_key):
        print(f"⚠️  {lane_name} 网关 API Key 未配置或为占位值，跳过初始化")
        return None

    try:
        client = _create_anthropic_client(
            api_key=api_key,
            base_url=base_url,
            use_bearer_auth=use_bearer_auth,
        )
        endpoint = base_url or "(Anthropic 官方默认地址)"
        print(f"✅ {lane_name} 网关客户端已初始化")
        print(f"   模型: {test_model}")
        print(f"   Base URL: {endpoint}")
        print(f"   鉴权模式: {'Bearer Authorization' if use_bearer_auth else 'Anthropic x-api-key'}")

        # 连接测试失败不阻断服务，保留客户端以便后续重试
        try:
            client.messages.create(
                model=test_model,
                max_tokens=5,
                messages=[{"role": "user", "content": "Hi"}]
            )
            print(f"✅ {lane_name} 网关连接测试成功")
        except Exception as e:
            print(f"⚠️  {lane_name} 网关连接测试失败: {e}")
            print("   客户端已保留，运行时会继续尝试请求")

        return client
    except Exception as e:
        print(f"❌ {lane_name} 网关客户端初始化失败: {e}")
        return None


def _pick_reused_client(signature: tuple, lane_signatures: list[tuple]) -> tuple[Optional[object], str]:
    for lane_name, lane_signature, lane_client in lane_signatures:
        if signature == lane_signature and lane_client:
            return lane_client, lane_name
    return None, ""


if ENABLE_AI and HAS_ANTHROPIC:
    question_signature = (QUESTION_API_KEY, QUESTION_BASE_URL, QUESTION_USE_BEARER_AUTH)
    report_signature = (REPORT_API_KEY, REPORT_BASE_URL, REPORT_USE_BEARER_AUTH)
    summary_signature = (SUMMARY_API_KEY, SUMMARY_BASE_URL, SUMMARY_USE_BEARER_AUTH)
    search_decision_signature = (
        SEARCH_DECISION_API_KEY,
        SEARCH_DECISION_BASE_URL,
        SEARCH_DECISION_USE_BEARER_AUTH,
    )

    question_ai_client = _init_lane_client(
        lane_name="问题",
        api_key=QUESTION_API_KEY,
        base_url=QUESTION_BASE_URL,
        test_model=QUESTION_MODEL_NAME,
        use_bearer_auth=QUESTION_USE_BEARER_AUTH,
    )

    if report_signature == question_signature:
        report_ai_client = question_ai_client
        if report_ai_client:
            print("ℹ️  报告网关复用问题网关客户端（相同 Key/Base URL）")
    else:
        report_ai_client = _init_lane_client(
            lane_name="报告",
            api_key=REPORT_API_KEY,
            base_url=REPORT_BASE_URL,
            test_model=REPORT_MODEL_NAME,
            use_bearer_auth=REPORT_USE_BEARER_AUTH,
        )

    reusable_lanes = [
        ("问题", question_signature, question_ai_client),
        ("报告", report_signature, report_ai_client),
    ]

    summary_ai_client, summary_reuse_lane = _pick_reused_client(summary_signature, reusable_lanes)
    if summary_ai_client and summary_reuse_lane:
        print(f"ℹ️  摘要网关复用{summary_reuse_lane}网关客户端（相同 Key/Base URL）")
    else:
        summary_ai_client = _init_lane_client(
            lane_name="摘要",
            api_key=SUMMARY_API_KEY,
            base_url=SUMMARY_BASE_URL,
            test_model=SUMMARY_MODEL_NAME,
            use_bearer_auth=SUMMARY_USE_BEARER_AUTH,
        )

    reusable_lanes.append(("摘要", summary_signature, summary_ai_client))
    search_decision_ai_client, search_reuse_lane = _pick_reused_client(search_decision_signature, reusable_lanes)
    if search_decision_ai_client and search_reuse_lane:
        print(f"ℹ️  搜索决策网关复用{search_reuse_lane}网关客户端（相同 Key/Base URL）")
    else:
        search_decision_ai_client = _init_lane_client(
            lane_name="搜索决策",
            api_key=SEARCH_DECISION_API_KEY,
            base_url=SEARCH_DECISION_BASE_URL,
            test_model=SEARCH_DECISION_MODEL_NAME,
            use_bearer_auth=SEARCH_DECISION_USE_BEARER_AUTH,
        )

    claude_client = question_ai_client or report_ai_client or summary_ai_client or search_decision_ai_client
    if not claude_client:
        print("❌ AI 客户端初始化失败：所有网关均不可用")
else:
    if not ENABLE_AI:
        print("ℹ️  AI 功能已禁用（ENABLE_AI=False）")
    elif not HAS_ANTHROPIC:
        print("❌ anthropic 库未安装")
    else:
        print("❌ AI 客户端初始化前置条件不满足")


def _lane_client_by_name(lane: str):
    lane_name = str(lane or "").strip().lower()
    if lane_name == "question":
        return question_ai_client
    if lane_name == "report":
        return report_ai_client
    if lane_name == "summary":
        return summary_ai_client
    if lane_name == "search_decision":
        return search_decision_ai_client
    return None


def _lane_candidates_for_client_resolution(call_type: str = "", model_name: str = "", preferred_lane: str = "") -> list[str]:
    forced_lane = str(preferred_lane or "").strip().lower()
    if forced_lane == "search_decision":
        return ["search_decision", "summary", "question", "report"]
    if forced_lane == "summary":
        return ["summary", "report", "question", "search_decision"]
    if forced_lane == "report":
        return ["report", "question"]
    if forced_lane == "question":
        return ["question", "report"]

    lane = resolve_call_lane(call_type=call_type, model_name=model_name)
    if lane == "search_decision":
        return ["search_decision", "summary", "question", "report"]
    if lane == "summary":
        return ["summary", "report", "question", "search_decision"]
    if lane == "report":
        return ["report", "question"]
    return ["question", "report", "summary", "search_decision"]


def resolve_ai_client_with_lane(
    call_type: str = "",
    model_name: str = "",
    preferred_lane: str = "",
    respect_circuit_breaker: bool = True,
) -> tuple[Optional[object], str, dict]:
    """按调用类型选择客户端，并返回命中的 lane 与熔断元信息。"""
    candidates = _lane_candidates_for_client_resolution(
        call_type=call_type,
        model_name=model_name,
        preferred_lane=preferred_lane,
    )
    requested_lane = candidates[0] if candidates else ""
    skip_open = bool(respect_circuit_breaker and GATEWAY_CIRCUIT_BREAKER_ENABLED)
    skipped_open_lanes = []
    fallback_pool = []

    for lane_name in candidates:
        client = _lane_client_by_name(lane_name)
        if not client:
            continue
        fallback_pool.append((lane_name, client))
        if skip_open and is_gateway_lane_in_cooldown(lane_name):
            skipped_open_lanes.append(lane_name)
            continue
        return client, lane_name, {
            "requested_lane": requested_lane,
            "skipped_open_lanes": skipped_open_lanes,
            "forced_open_lane": "",
        }

    if fallback_pool:
        # 所有候选 lane 均处于冷却时，选择第一个可用客户端避免彻底不可用。
        lane_name, client = fallback_pool[0]
        return client, lane_name, {
            "requested_lane": requested_lane,
            "skipped_open_lanes": skipped_open_lanes,
            "forced_open_lane": lane_name if skipped_open_lanes else "",
        }

    return None, "", {
        "requested_lane": requested_lane,
        "skipped_open_lanes": skipped_open_lanes,
        "forced_open_lane": "",
    }


def resolve_ai_client(call_type: str = "", model_name: str = "", preferred_lane: str = ""):
    """兼容历史接口，仅返回客户端对象。"""
    client, _, _ = resolve_ai_client_with_lane(
        call_type=call_type,
        model_name=model_name,
        preferred_lane=preferred_lane,
    )
    return client


def _content_block_field(block, field: str):
    """兼容对象/字典两种内容块结构读取字段。"""
    if isinstance(block, dict):
        return block.get(field)
    return getattr(block, field, None)


def extract_message_text(message, allow_non_text_fallback: bool = False) -> str:
    """从模型响应中提取文本内容，优先提取 type=text。"""
    content = getattr(message, "content", None) or []
    if not content:
        return ""

    # 优先提取 type=text 的内容块，避免拿到 thinking 块导致空文本
    text_parts = []
    for block in content:
        if _content_block_field(block, "type") != "text":
            continue
        block_text = _content_block_field(block, "text")
        if isinstance(block_text, str) and block_text.strip():
            text_parts.append(block_text.strip())

    if text_parts:
        return "\n".join(text_parts).strip()

    # 默认不回退到非 text 块，避免把 thinking 当作最终输出
    if not allow_non_text_fallback:
        return ""

    # 兜底：极少数兼容实现可能未标记 type，但有 text 字段
    fallback_parts = []
    for block in content:
        block_text = _content_block_field(block, "text")
        if isinstance(block_text, str) and block_text.strip():
            fallback_parts.append(block_text.strip())

    return "\n".join(fallback_parts).strip()


def _collect_json_candidates(raw_text: str) -> list:
    """提取可能的 JSON 候选字符串（直出、代码块、花括号配对）。"""
    candidates = []
    text = (raw_text or "").strip()
    if not text:
        return candidates

    candidates.append(text)

    # 代码块候选
    for match in re.finditer(r"```(?:json)?\s*([\s\S]*?)```", text, re.IGNORECASE):
        block = (match.group(1) or "").strip()
        if block:
            candidates.append(block)

    # 花括号配对提取第一个完整 JSON 对象
    json_start = text.find("{")
    if json_start >= 0:
        brace_count = 0
        in_string = False
        escape_next = False
        json_end = -1

        for idx in range(json_start, len(text)):
            char = text[idx]
            if escape_next:
                escape_next = False
                continue
            if char == "\\":
                escape_next = True
                continue
            if char == "\"":
                in_string = not in_string
                continue
            if in_string:
                continue
            if char == "{":
                brace_count += 1
            elif char == "}":
                brace_count -= 1
                if brace_count == 0:
                    json_end = idx + 1
                    break

        if json_end > json_start:
            candidates.append(text[json_start:json_end].strip())

    # 去重（保序）+ 处理 ```json 提取后残留的 json 前缀
    normalized = []
    seen = set()
    for candidate in candidates:
        item = candidate.strip()
        if item.lower().startswith("json"):
            item = item[4:].strip()
        if not item or item in seen:
            continue
        seen.add(item)
        normalized.append(item)
    return normalized


def parse_json_object_response(raw_text: str, required_keys: list = None) -> Optional[dict]:
    """从模型文本中容错解析 JSON 对象。"""
    required_keys = required_keys or []
    last_error = None

    for candidate in _collect_json_candidates(raw_text):
        try:
            parsed = json.loads(candidate)
        except Exception as exc:
            last_error = exc
            continue

        if not isinstance(parsed, dict):
            last_error = ValueError("JSON 不是对象")
            continue

        if any(key not in parsed for key in required_keys):
            last_error = ValueError(f"JSON 缺少必要字段: {required_keys}")
            continue

        return parsed

    if last_error:
        raise ValueError(f"JSON解析失败: {last_error}")
    raise ValueError("未找到可解析的 JSON 对象")


def parse_scenario_recognition_response(raw_text: str, valid_scenario_ids: set) -> Optional[dict]:
    """解析场景识别结果，支持 JSON 与半结构化兜底提取。"""
    try:
        parsed = parse_json_object_response(raw_text, required_keys=["scenario_id"])
        scenario_id = str(parsed.get("scenario_id", "")).strip()
        if scenario_id not in valid_scenario_ids:
            return None
        confidence = parsed.get("confidence", 0.8)
        try:
            confidence = float(confidence)
        except Exception:
            confidence = 0.8
        confidence = min(1.0, max(0.0, confidence))
        reason = str(parsed.get("reason", "") or "").strip()
        return {
            "scenario_id": scenario_id,
            "confidence": confidence,
            "reason": reason
        }
    except Exception:
        pass

    # 兜底：常见截断场景（如 reason 未闭合）时，尽量提取 scenario_id/confidence
    sid_match = re.search(r'"scenario_id"\s*:\s*"([^"]+)"', raw_text or "")
    if not sid_match:
        return None

    scenario_id = sid_match.group(1).strip()
    if scenario_id not in valid_scenario_ids:
        return None

    confidence = 0.8
    conf_match = re.search(r'"confidence"\s*:\s*([0-9]+(?:\.[0-9]+)?)', raw_text or "")
    if conf_match:
        try:
            confidence = float(conf_match.group(1))
        except Exception:
            confidence = 0.8
    confidence = min(1.0, max(0.0, confidence))

    reason = ""
    reason_match = re.search(r'"reason"\s*:\s*"([^"]*)"', raw_text or "")
    if reason_match:
        reason = reason_match.group(1).strip()

    return {
        "scenario_id": scenario_id,
        "confidence": confidence,
        "reason": reason
    }


def get_utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def generate_session_id() -> str:
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    random_suffix = secrets.token_hex(4)
    return f"dv-{timestamp}-{random_suffix}"


INSTANCE_SCOPE_FIELD = "instance_scope_key"


def normalize_instance_scope_key(raw_scope: object) -> str:
    value = str(raw_scope or "").strip().lower()
    if not value:
        return ""
    value = re.sub(r"[^a-z0-9._/-]+", "-", value)
    value = value.strip("-._/")
    value = value.replace("/", "--")
    return value[:96]


def get_active_instance_scope_key() -> str:
    return normalize_instance_scope_key(INSTANCE_SCOPE_KEY)


def get_instance_scope_short_tag() -> str:
    scope_key = get_active_instance_scope_key()
    if not scope_key:
        return ""
    return hashlib.sha1(scope_key.encode("utf-8")).hexdigest()[:8]


def get_record_instance_scope_key(raw_scope: object) -> str:
    return normalize_instance_scope_key(raw_scope)


def is_instance_scope_visible(record_scope: object, expected_scope: Optional[str] = None) -> bool:
    current_scope = normalize_instance_scope_key(
        get_active_instance_scope_key() if expected_scope is None else expected_scope
    )
    normalized_record_scope = get_record_instance_scope_key(record_scope)
    if current_scope:
        return normalized_record_scope == current_scope
    return normalized_record_scope == ""


def get_session_instance_scope_key(session: dict) -> str:
    if not isinstance(session, dict):
        return ""
    return get_record_instance_scope_key(session.get(INSTANCE_SCOPE_FIELD))


def load_report_scopes() -> dict:
    with REPORT_SCOPES_LOCK:
        signature = get_file_signature(REPORT_SCOPES_FILE)
        cached_signature = report_scopes_cache.get("signature")
        cached_data = report_scopes_cache.get("data")
        if signature == cached_signature and isinstance(cached_data, dict):
            record_list_cache_metric("report_scope", hit=True)
            return dict(cached_data)

        record_list_cache_metric("report_scope", hit=False)
        if signature is None:
            report_scopes_cache["signature"] = None
            report_scopes_cache["data"] = {}
            return {}

        normalized = {}
        try:
            payload = json.loads(REPORT_SCOPES_FILE.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                for name, scope_key in payload.items():
                    if not isinstance(name, str):
                        continue
                    normalized_scope = normalize_instance_scope_key(scope_key)
                    if not normalized_scope:
                        continue
                    normalized[name] = normalized_scope
        except Exception:
            normalized = {}

        report_scopes_cache["signature"] = signature
        report_scopes_cache["data"] = dict(normalized)
        return dict(normalized)


def save_report_scopes(data: dict) -> None:
    normalized = {}
    if isinstance(data, dict):
        for name, scope_key in data.items():
            if not isinstance(name, str):
                continue
            normalized_scope = normalize_instance_scope_key(scope_key)
            if not normalized_scope:
                continue
            normalized[name] = normalized_scope

    with REPORT_SCOPES_LOCK:
        REPORT_SCOPES_FILE.write_text(
            json.dumps(normalized, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        report_scopes_cache["signature"] = get_file_signature(REPORT_SCOPES_FILE)
        report_scopes_cache["data"] = dict(normalized)


def get_report_scope_key(filename: str) -> str:
    scopes = load_report_scopes()
    return get_record_instance_scope_key(scopes.get(filename, ""))


def set_report_scope_key(filename: str, scope_key: object) -> None:
    name = str(filename or "").strip()
    if not name:
        return

    normalized_scope = normalize_instance_scope_key(scope_key)
    with REPORT_SCOPES_LOCK:
        scopes = load_report_scopes()
        if normalized_scope:
            scopes[name] = normalized_scope
        else:
            scopes.pop(name, None)
        save_report_scopes(scopes)


def get_deleted_reports() -> set:
    """获取已删除报告的列表"""
    if not DELETED_REPORTS_FILE.exists():
        return set()
    try:
        data = json.loads(DELETED_REPORTS_FILE.read_text(encoding="utf-8"))
        return set(data.get("deleted", []))
    except Exception:
        return set()


def load_report_owners() -> dict:
    with REPORT_OWNERS_LOCK:
        signature = get_file_signature(REPORT_OWNERS_FILE)
        cached_signature = report_owners_cache.get("signature")
        cached_data = report_owners_cache.get("data")
        if signature == cached_signature and isinstance(cached_data, dict):
            record_list_cache_metric("report_owner", hit=True)
            return dict(cached_data)

        record_list_cache_metric("report_owner", hit=False)
        if signature is None:
            report_owners_cache["signature"] = None
            report_owners_cache["data"] = {}
            return {}

        normalized = {}
        try:
            payload = json.loads(REPORT_OWNERS_FILE.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                for name, owner in payload.items():
                    if not isinstance(name, str):
                        continue
                    try:
                        owner_id = int(owner)
                    except (TypeError, ValueError):
                        continue
                    if owner_id <= 0:
                        continue
                    normalized[name] = owner_id
        except Exception:
            normalized = {}

        report_owners_cache["signature"] = signature
        report_owners_cache["data"] = dict(normalized)
        return dict(normalized)


def save_report_owners(data: dict) -> None:
    normalized = {}
    if isinstance(data, dict):
        for name, owner in data.items():
            if not isinstance(name, str):
                continue
            try:
                owner_id = int(owner)
            except (TypeError, ValueError):
                continue
            if owner_id <= 0:
                continue
            normalized[name] = owner_id

    with REPORT_OWNERS_LOCK:
        REPORT_OWNERS_FILE.write_text(
            json.dumps(normalized, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        report_owners_cache["signature"] = get_file_signature(REPORT_OWNERS_FILE)
        report_owners_cache["data"] = dict(normalized)


def get_report_owner_id(filename: str) -> int:
    owners = load_report_owners()
    try:
        return int(owners.get(filename, 0))
    except (TypeError, ValueError):
        return 0


def set_report_owner_id(filename: str, owner_user_id: int) -> None:
    owner_id = int(owner_user_id)
    with REPORT_OWNERS_LOCK:
        owners = load_report_owners()
        owners[filename] = owner_id
        save_report_owners(owners)
    set_report_scope_key(filename, get_active_instance_scope_key())
    try:
        sync_report_index_for_filename(filename, owner_user_id=owner_id)
    except Exception as exc:
        if ENABLE_DEBUG_LOG:
            _safe_log(f"⚠️ 同步 report_index 失败: {filename}, 错误: {exc}")


def ensure_report_owner(filename: str, owner_user_id: int) -> bool:
    owner = get_report_owner_id(filename)
    owner_id = int(owner_user_id)
    # 禁止自动认领无归属历史数据，需通过迁移脚本显式迁移
    if owner <= 0:
        return False
    if owner != owner_id:
        return False
    return is_instance_scope_visible(get_report_scope_key(filename))


def is_session_owned_by_user(session: dict, user_id: int) -> bool:
    if not isinstance(session, dict):
        return False
    owner = session.get("owner_user_id")
    try:
        owner_id = int(owner)
    except (TypeError, ValueError):
        return False
    return owner_id == int(user_id)


def ensure_session_owner(session: dict, user_id: int) -> bool:
    if not isinstance(session, dict):
        return False

    current_owner = session.get("owner_user_id")
    try:
        owner_id = int(current_owner)
    except (TypeError, ValueError):
        owner_id = 0

    # 禁止自动认领无归属历史数据，需通过迁移脚本显式迁移
    if owner_id <= 0:
        return False
    if owner_id != int(user_id):
        return False
    return is_instance_scope_visible(get_session_instance_scope_key(session))


def get_current_user_id_or_none() -> Optional[int]:
    user = get_current_user()
    if not user:
        return None
    try:
        return int(user["id"])
    except (TypeError, ValueError, KeyError):
        return None


def load_session_for_user(session_id: str, user_id: int, include_missing: bool = False):
    session_file = SESSIONS_DIR / f"{session_id}.json"
    if not session_file.exists():
        if include_missing:
            return None, None, "not_found"
        return None, "会话不存在", 404

    session_data = safe_load_session(session_file)
    if session_data is None:
        return None, "会话数据损坏", 500

    if not ensure_session_owner(session_data, user_id):
        return None, "会话不存在", 404

    if include_missing:
        return session_file, session_data, "ok"
    return session_file, session_data


def enforce_report_owner_or_404(filename: str, user_id: int) -> tuple[Optional[Path], Optional[tuple]]:
    report_file = REPORTS_DIR / filename
    if not report_file.exists():
        return None, (jsonify({"error": "报告不存在"}), 404)

    if not ensure_report_owner(filename, user_id):
        return None, (jsonify({"error": "报告不存在"}), 404)

    return report_file, None


def mark_report_as_deleted(filename: str):
    """标记报告为已删除（不真正删除文件）"""
    deleted = get_deleted_reports()
    deleted.add(filename)
    DELETED_REPORTS_FILE.write_text(
        json.dumps({"deleted": list(deleted)}, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    try:
        sync_report_index_for_filename(filename, deleted=True)
    except Exception as exc:
        if ENABLE_DEBUG_LOG:
            _safe_log(f"⚠️ 标记 report_index 删除失败: {filename}, 错误: {exc}")


def normalize_topic_slug(topic: str) -> str:
    """按报告命名规则生成主题 slug。"""
    if not isinstance(topic, str):
        return ""
    topic = topic.strip()
    if not topic:
        return ""
    return re.sub(r"\s+", "-", topic)[:30]


def get_session_total_progress(session: dict) -> int:
    """计算会话总进度（各维度覆盖率平均值）。"""
    dimensions = session.get("dimensions")
    if not isinstance(dimensions, dict) or not dimensions:
        return 0

    values = []
    for value in dimensions.values():
        if not isinstance(value, dict):
            continue
        coverage = value.get("coverage", 0)
        try:
            coverage_value = int(coverage)
        except Exception:
            coverage_value = 0
        values.append(max(0, min(100, coverage_value)))

    if not values:
        return 0
    return round(sum(values) / len(values))


def get_effective_session_status(session: dict) -> str:
    """统一会话状态口径（与前端保持一致）。"""
    raw = session.get("status") or "in_progress"
    progress = get_session_total_progress(session)
    if raw == "in_progress" and progress >= 100:
        return "pending_review"
    return raw


def find_reports_by_session_topic(session: dict) -> list:
    """根据会话主题匹配同归属、同实例的关联报告文件。"""
    if not isinstance(session, dict):
        return []

    topic_slug = normalize_topic_slug(session.get("topic", ""))
    if not topic_slug:
        return []

    try:
        owner_user_id = int(session.get("owner_user_id"))
    except (TypeError, ValueError):
        return []
    if owner_user_id <= 0:
        return []

    session_scope_key = get_session_instance_scope_key(session)
    suffix = f"-{topic_slug}.md"
    matched = []
    for report_file in REPORTS_DIR.glob("deep-vision-*.md"):
        report_name = report_file.name
        if not report_name.endswith(suffix):
            continue
        if get_report_owner_id(report_name) != owner_user_id:
            continue
        if get_report_scope_key(report_name) != session_scope_key:
            continue
        matched.append(report_name)
    return matched


def unique_non_empty_strings(items) -> list:
    """去重并过滤空字符串。"""
    if not isinstance(items, list):
        return []

    result = []
    seen = set()
    for item in items:
        if not isinstance(item, str):
            continue
        value = item.strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def get_deleted_docs() -> dict:
    """获取已删除文档的记录"""
    if not DELETED_DOCS_FILE.exists():
        return {"reference_materials": []}
    try:
        data = json.loads(DELETED_DOCS_FILE.read_text(encoding="utf-8"))
        # 兼容旧格式
        materials = data.get("reference_materials", [])
        materials.extend(data.get("reference_docs", []))
        materials.extend(data.get("research_docs", []))
        return {"reference_materials": materials}
    except Exception:
        return {"reference_materials": []}


def mark_doc_as_deleted(session_id: str, doc_name: str, doc_type: str = "reference_materials"):
    """标记文档为已删除（软删除）

    Args:
        session_id: 会话 ID
        doc_name: 文档名称
        doc_type: 文档类型（默认 'reference_materials'）
    """
    deleted = get_deleted_docs()
    record = {
        "session_id": session_id,
        "doc_name": doc_name,
        "deleted_at": get_utc_now()
    }
    if "reference_materials" not in deleted:
        deleted["reference_materials"] = []
    deleted["reference_materials"].append(record)
    DELETED_DOCS_FILE.write_text(
        json.dumps(deleted, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def migrate_session_docs(session: dict) -> dict:
    """迁移旧会话数据：将 reference_docs + research_docs 合并为 reference_materials

    Args:
        session: 会话数据字典

    Returns:
        迁移后的会话数据
    """
    # 如果已经有 reference_materials，检查是否还有旧字段需要迁移
    if "reference_materials" not in session:
        session["reference_materials"] = []

    # 迁移 reference_docs
    if "reference_docs" in session:
        for doc in session["reference_docs"]:
            if "source" not in doc:
                doc["source"] = "upload"
            session["reference_materials"].append(doc)
        del session["reference_docs"]

    # 迁移 research_docs
    if "research_docs" in session:
        for doc in session["research_docs"]:
            if "source" not in doc:
                doc["source"] = "auto"
            session["reference_materials"].append(doc)
        del session["research_docs"]

    return session


# ============ 联网搜索功能 ============

class MCPClient:
    """智谱AI MCP客户端"""

    def __init__(self, api_key: str, base_url: str):
        self.api_key = api_key
        self.base_url = base_url
        self.session_id = None
        self.message_id = 0

    def _get_next_id(self):
        """获取下一个消息ID"""
        self.message_id += 1
        return self.message_id

    def _make_request(self, method: str, params: dict = None):
        """发送MCP JSON-RPC请求"""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream"
        }

        # 如果有session_id，添加到header
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id

        # 在URL中添加Authorization参数
        url = f"{self.base_url}?Authorization={self.api_key}"

        request_data = {
            "jsonrpc": "2.0",
            "id": self._get_next_id(),
            "method": method,
            "params": params or {}
        }

        if ENABLE_DEBUG_LOG:
            print(f"📤 MCP请求: {method}")
            print(f"   参数: {params}")

        response = requests.post(url, json=request_data, headers=headers, timeout=SEARCH_TIMEOUT)
        response.raise_for_status()

        # 检查响应头中的Session ID
        if "Mcp-Session-Id" in response.headers:
            self.session_id = response.headers["Mcp-Session-Id"]
            if ENABLE_DEBUG_LOG:
                print(f"   📝 获得Session ID: {self.session_id}")

        # 解析SSE格式的响应
        response_text = response.text.strip()

        # SSE格式: id:1\nevent:message\ndata:{json}\n\n
        result_data = None
        for line in response_text.split('\n'):
            line = line.strip()
            if line.startswith('data:'):
                json_str = line[5:].strip()  # 去掉 "data:" 前缀
                try:
                    result_data = json.loads(json_str)
                    break
                except:
                    continue

        if not result_data:
            raise Exception(f"无法解析SSE响应: {response_text[:200]}")

        # 检查是否有错误
        if "error" in result_data:
            raise Exception(f"MCP错误: {result_data['error']}")

        return result_data.get("result", {})

    def initialize(self):
        """初始化MCP连接"""
        try:
            result = self._make_request("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "deep-vision",
                    "version": "1.0.0"
                }
            })
            if ENABLE_DEBUG_LOG:
                print(f"✅ MCP初始化成功")
            return result
        except Exception as e:
            if ENABLE_DEBUG_LOG:
                print(f"❌ MCP初始化失败: {e}")
            raise

    def call_tool(self, tool_name: str, arguments: dict):
        """调用MCP工具"""
        try:
            # 确保已初始化
            if not self.session_id:
                self.initialize()

            result = self._make_request("tools/call", {
                "name": tool_name,
                "arguments": arguments
            })

            return result
        except Exception as e:
            if ENABLE_DEBUG_LOG:
                print(f"❌ 工具调用失败: {e}")
            raise


def web_search(query: str) -> list:
    """使用智谱AI MCP web_search_prime 进行联网搜索"""
    global web_search_active

    if not ENABLE_WEB_SEARCH or not ZHIPU_API_KEY or ZHIPU_API_KEY == "your-zhipu-api-key-here":
        if ENABLE_DEBUG_LOG:
            print(f"⚠️  搜索功能未启用或 API Key 未配置，跳过搜索: {query}")
        return []

    normalized_query = re.sub(r"\s+", " ", str(query or "").strip())
    if not normalized_query:
        return []
    cache_key = _build_search_result_cache_key(normalized_query)

    cached_results = _get_search_result_cache(cache_key)
    if cached_results is not None:
        if ENABLE_DEBUG_LOG:
            print(f"📦 命中搜索结果缓存，跳过 MCP 调用: {normalized_query}")
        _record_cache_hit_metric("web_search_cache_hit")
        return cached_results

    owner_event, is_owner = _begin_search_inflight(cache_key)
    if not is_owner and isinstance(owner_event, threading.Event):
        wait_seconds = float(SEARCH_RESULT_INFLIGHT_WAIT_SECONDS)
        if ENABLE_DEBUG_LOG:
            print(f"⏳ 搜索请求去重生效，等待同查询结果: {normalized_query}")
        owner_event.wait(timeout=wait_seconds)
        cached_after_wait = _get_search_result_cache(cache_key)
        if cached_after_wait is not None:
            if ENABLE_DEBUG_LOG:
                print(f"✅ 复用并发搜索结果: {normalized_query}")
            _record_cache_hit_metric("web_search_cache_hit")
            return cached_after_wait

    is_owner_search = bool(is_owner)
    if not is_owner_search:
        owner_event, is_owner_search = _begin_search_inflight(cache_key)

    try:
        web_search_active = True
        mcp_url = "https://open.bigmodel.cn/api/mcp/web_search_prime/mcp"

        if ENABLE_DEBUG_LOG:
            print(f"🔍 开始MCP搜索: {normalized_query}")

        client = MCPClient(ZHIPU_API_KEY, mcp_url)
        result = client.call_tool("webSearchPrime", {
            "search_query": normalized_query,
            "search_recency_filter": "noLimit",
            "content_size": "medium"
        })

        results = []
        content_list = result.get("content", [])
        for item in content_list:
            if item.get("type") != "text":
                continue
            text = item.get("text", "")
            try:
                import json as json_module
                if text.startswith('"') and text.endswith('"'):
                    text = json_module.loads(text)
                search_data = json_module.loads(text)

                if isinstance(search_data, list):
                    for entry in search_data[:SEARCH_MAX_RESULTS]:
                        title = entry.get("title", "")
                        content = entry.get("content", "")
                        url = entry.get("link", entry.get("url", ""))
                        if title or content:
                            results.append({
                                "type": "result",
                                "title": title[:100] if title else "搜索结果",
                                "content": content[:300],
                                "url": url
                            })
                elif isinstance(search_data, dict):
                    title = search_data.get("title", "")
                    content = search_data.get("content", text[:300])
                    url = search_data.get("link", search_data.get("url", ""))
                    results.append({
                        "type": "result",
                        "title": title[:100] if title else "搜索结果",
                        "content": content[:300],
                        "url": url
                    })
            except Exception as parse_error:
                if ENABLE_DEBUG_LOG:
                    print(f"⚠️  解析搜索结果失败: {parse_error}")
                    print(f"   原始文本前200字符: {text[:200]}")
                results.append({
                    "type": "result",
                    "title": "搜索结果",
                    "content": text[:300],
                    "url": ""
                })

        if ENABLE_DEBUG_LOG:
            print(f"✅ MCP搜索成功，找到 {len(results)} 条结果")

        _set_search_result_cache(cache_key, results)
        return results
    except requests.exceptions.Timeout:
        print(f"⏱️  搜索超时: {normalized_query}")
        return []
    except Exception as e:
        print(f"❌ MCP搜索失败: {e}")
        if ENABLE_DEBUG_LOG:
            import traceback
            traceback.print_exc()
        return []
    finally:
        web_search_active = False
        _end_search_inflight(cache_key, owner_event if is_owner_search else None)


def should_search(topic: str, dimension: str, context: dict) -> bool:
    """
    规则预判：快速判断是否可能需要联网搜索（兜底规则）
    返回 True 表示"可能需要"，后续会交给 AI 做最终判断
    """
    if not ENABLE_WEB_SEARCH:
        return False

    # ========== 扩展的关键词库 ==========

    # 技术关键词
    tech_keywords = [
        "技术", "系统", "平台", "框架", "工具", "软件", "应用", "架构",
        "AI", "人工智能", "机器学习", "深度学习", "大模型", "LLM", "GPT",
        "云", "SaaS", "PaaS", "IaaS", "微服务", "容器", "Docker", "K8s", "Kubernetes",
        "数据库", "中间件", "API", "集成", "部署", "运维", "DevOps",
        "前端", "后端", "全栈", "移动端", "App", "小程序"
    ]

    # 垂直行业关键词（新增）
    industry_keywords = [
        # 医疗健康
        "医院", "医疗", "HIS", "LIS", "PACS", "EMR", "电子病历", "DRG", "医保",
        "诊所", "药房", "处方", "挂号", "门诊", "住院", "护理", "CDSS",
        # 金融
        "银行", "保险", "证券", "基金", "信托", "支付", "清算", "风控",
        "反洗钱", "征信", "资管", "理财", "贷款", "信用卡",
        # 教育
        "学校", "教育", "培训", "课程", "教学", "学生", "考试", "招生",
        "在线教育", "网课", "双减", "新课标",
        # 制造
        "工厂", "制造", "生产", "车间", "MES", "ERP", "PLM", "SCM", "WMS",
        "工业互联网", "智能制造", "数字孪生", "质检", "设备", "产线",
        # 零售电商
        "零售", "电商", "门店", "商城", "订单", "库存", "物流", "配送",
        "会员", "营销", "促销", "CRM", "POS",
        # 政务
        "政府", "政务", "审批", "办事", "公共服务", "智慧城市", "数字政府",
        # 能源
        "电力", "能源", "电网", "新能源", "光伏", "风电", "储能", "充电桩",
        # 交通物流
        "交通", "物流", "运输", "仓储", "TMS", "调度", "车队"
    ]

    # 合规政策关键词（新增）
    compliance_keywords = [
        "合规", "标准", "规范", "认证", "等保", "ISO", "GDPR", "隐私",
        "安全", "审计", "法规", "政策", "监管", "资质", "许可证"
    ]

    # 时效性关键词
    time_sensitive_keywords = [
        "最新", "当前", "现在", "近期", "今年", "明年",
        "2024", "2025", "2026", "2027",
        "趋势", "未来", "发展", "动态", "变化", "更新",
        "市场", "行情", "竞品", "对手", "现状"
    ]

    # 不确定性/专业性关键词（新增）
    uncertainty_keywords = [
        "怎么选", "如何选择", "哪个好", "推荐", "建议", "比较",
        "最佳实践", "业界", "头部", "领先", "主流", "标杆"
    ]

    all_keywords = (tech_keywords + industry_keywords + compliance_keywords +
                   time_sensitive_keywords + uncertainty_keywords)

    # 如果主题包含任何关键词，标记为"可能需要搜索"
    for keyword in all_keywords:
        if keyword.lower() in topic.lower():
            return True

    # 技术约束维度通常需要搜索
    if dimension == "tech_constraints":
        return True

    return False


def ai_evaluate_search_need(topic: str, dimension: str, context: dict, recent_qa: list) -> dict:
    """
    AI 自主判断：让 AI 评估是否需要联网搜索
    返回: { "need_search": bool, "reason": str, "search_query": str }
    """
    ai_client = resolve_ai_client(call_type="search_decision")
    if not ENABLE_WEB_SEARCH or not ai_client:
        return {"need_search": False, "reason": "搜索功能未启用", "search_query": ""}

    cache_key = _build_search_decision_cache_key(topic, dimension, recent_qa or [])
    cached = _get_search_decision_cache(cache_key)
    if isinstance(cached, dict):
        if ENABLE_DEBUG_LOG:
            print("📦 命中搜索决策缓存，跳过 AI 决策调用")
        _record_cache_hit_metric("search_decision_cache_hit")
        return cached

    owner_event = None
    owner_mode = False
    if cache_key:
        owner_event, owner_mode = _begin_search_decision_inflight(cache_key)
        if not owner_mode and isinstance(owner_event, threading.Event):
            wait_seconds = float(SEARCH_DECISION_INFLIGHT_WAIT_SECONDS)
            if ENABLE_DEBUG_LOG:
                print(f"⏳ 搜索决策去重生效，等待首个结果: dim={dimension}")
            owner_event.wait(timeout=wait_seconds)
            cached_after_wait = _get_search_decision_cache(cache_key)
            if isinstance(cached_after_wait, dict):
                if ENABLE_DEBUG_LOG:
                    print("✅ 复用并发搜索决策结果")
                _record_cache_hit_metric("search_decision_cache_hit")
                return cached_after_wait

    try:
        search_dim_info = get_dimension_info_for_session(context) if context else DIMENSION_INFO
        dim_info = search_dim_info.get(dimension, {})
        dim_name = dim_info.get("name", dimension)

        # 构建最近的问答上下文
        recent_context = ""
        if recent_qa:
            recent_context = "\n".join([
                f"Q: {qa.get('question', '')}\nA: {qa.get('answer', '')}"
                for qa in recent_qa[-3:]  # 只取最近3条
            ])

        prompt = f"""你是一个智能搜索决策助手。请判断在当前访谈场景下，是否需要联网搜索来获取更准确、更专业的信息。

## 当前访谈信息
- 访谈主题：{topic}
- 当前维度：{dim_name}
- 最近问答：
{recent_context if recent_context else "（尚未开始问答）"}

## 判断标准
请评估以下几个方面，判断是否需要联网搜索：

1. **知识时效性**：是否涉及近1-2年的政策、市场、技术变化？
2. **专业领域深度**：是否涉及你可能不够熟悉的垂直行业细节（如医疗编码规则、金融监管要求、行业标准参数等）？
3. **竞品/市场信息**：是否需要了解市场现状、竞争对手、行业头部产品？
4. **最佳实践参考**：是否需要了解业界的最新做法、成功案例？
5. **数据/指标参考**：是否需要了解行业基准数据、常见参数范围？

## 输出格式
请严格按以下JSON格式输出，不要有其他内容：
{{
    "need_search": true或false,
    "reason": "简要说明判断理由（20字以内）",
    "search_query": "如果需要搜索，给出最佳搜索词（要精准、具体，15字以内）；不需要搜索则留空"
}}"""

        result = None
        attempts = [
            {
                "max_tokens": 220,
                "timeout": 10.0,
                "extra_instruction": "",
            },
            {
                "max_tokens": 420,
                "timeout": 18.0,
                "extra_instruction": "只输出一行 JSON，不要 markdown 代码块，不要额外解释，不要换行。",
            },
        ]

        for idx, attempt in enumerate(attempts, start=1):
            try:
                attempt_prompt = prompt
                if attempt["extra_instruction"]:
                    attempt_prompt = f"{prompt}\n\n【额外要求】{attempt['extra_instruction']}"

                with ai_call_priority_slot("search_decision"):
                    response = ai_client.messages.create(
                        model=resolve_model_name(call_type="search_decision"),
                        max_tokens=attempt["max_tokens"],
                        timeout=attempt["timeout"],
                        messages=[{"role": "user", "content": attempt_prompt}]
                    )

                result_text = extract_message_text(response)
                if not result_text:
                    raise ValueError("模型响应中未包含可用文本内容")

                result = parse_json_object_response(
                    result_text,
                    required_keys=["need_search", "reason", "search_query"]
                )
                break
            except Exception as retry_error:
                if ENABLE_DEBUG_LOG:
                    print(f"⚠️  AI搜索决策第{idx}次解析失败: {retry_error}")

        if result is None:
            raise ValueError("AI 搜索决策结果解析失败")

        if ENABLE_DEBUG_LOG:
            print(f"🤖 AI搜索决策: need_search={result.get('need_search')}, reason={result.get('reason')}")

        need_search = result.get("need_search", False)
        if isinstance(need_search, str):
            need_search = need_search.strip().lower() in ["true", "1", "yes", "y"]

        normalized_result = {
            "need_search": bool(need_search),
            "reason": str(result.get("reason", "") or ""),
            "search_query": str(result.get("search_query", "") or "")
        }
        _set_search_decision_cache(cache_key, normalized_result)
        return normalized_result

    except Exception as e:
        if ENABLE_DEBUG_LOG:
            print(f"⚠️  AI搜索决策失败: {e}")
        # 失败时返回不搜索，避免阻塞流程
        return {"need_search": False, "reason": f"决策失败: {e}", "search_query": ""}
    finally:
        if owner_mode:
            _end_search_decision_inflight(cache_key, owner_event)


def smart_search_decision(topic: str, dimension: str, context: dict, recent_qa: list = None) -> tuple:
    """
    智能搜索决策：规则预判 + AI 最终判断
    返回: (need_search: bool, search_query: str, reason: str)
    """
    if not ENABLE_WEB_SEARCH:
        return (False, "", "搜索功能未启用")

    # 第一步：规则预判
    rule_suggests_search = should_search(topic, dimension, context)

    if not rule_suggests_search:
        # 规则判断不需要搜索，但让 AI 做二次确认（可能漏掉的场景）
        ai_result = ai_evaluate_search_need(topic, dimension, context, recent_qa or [])
        if ai_result["need_search"]:
            if ENABLE_DEBUG_LOG:
                print(f"🔍 规则未触发，但AI建议搜索: {ai_result['reason']}")
            return (True, ai_result["search_query"], f"AI建议: {ai_result['reason']}")
        else:
            return (False, "", "规则和AI均判断不需要搜索")

    # 第二步：规则建议搜索，让 AI 生成精准搜索词
    ai_result = ai_evaluate_search_need(topic, dimension, context, recent_qa or [])

    if ai_result["need_search"] and ai_result["search_query"]:
        # AI 确认需要搜索，使用 AI 生成的搜索词
        return (True, ai_result["search_query"], ai_result["reason"])
    elif ai_result["need_search"]:
        # AI 确认需要但没给搜索词，使用兜底模板
        fallback_query = generate_search_query(topic, dimension, context)
        return (True, fallback_query, "AI确认需要，使用模板搜索词")
    else:
        # AI 判断实际不需要搜索（规则误触发）
        if ENABLE_DEBUG_LOG:
            print(f"🔍 规则触发但AI判断不需要: {ai_result['reason']}")
        return (False, "", f"AI判断不需要: {ai_result['reason']}")


def generate_search_query(topic: str, dimension: str, context: dict) -> str:
    """生成搜索查询（兜底模板，当 AI 未生成搜索词时使用）"""
    gen_query_dim_info = get_dimension_info_for_session(context) if context else DIMENSION_INFO
    dim_info = gen_query_dim_info.get(dimension, {})
    dim_name = dim_info.get("name", dimension)

    # 构建搜索查询 - 对于非默认维度使用通用模板
    if dimension == "tech_constraints":
        return f"{topic} 技术选型 最佳实践 2026"
    elif dimension == "customer_needs":
        return f"{topic} 用户需求 行业痛点 2026"
    elif dimension == "business_process":
        return f"{topic} 业务流程 最佳实践"
    elif dimension == "project_constraints":
        return f"{topic} 项目实施 成本预算 周期"
    else:
        # 非默认维度，使用维度名称构建通用搜索词
        return f"{topic} {dim_name}"


# ============ Deep Vision AI 核心逻辑 ============

DIMENSION_INFO = {
    "customer_needs": {
        "name": "客户需求",
        "description": "核心痛点、期望价值、使用场景、用户角色",
        "key_aspects": ["核心痛点", "期望价值", "使用场景", "用户角色"]
    },
    "business_process": {
        "name": "业务流程",
        "description": "关键流程节点、角色分工、触发事件、异常处理",
        "key_aspects": ["关键流程", "角色分工", "触发事件", "异常处理"]
    },
    "tech_constraints": {
        "name": "技术约束",
        "description": "现有技术栈、集成接口要求、性能指标、安全合规",
        "key_aspects": ["部署方式", "系统集成", "性能要求", "安全合规"]
    },
    "project_constraints": {
        "name": "项目约束",
        "description": "预算范围、时间节点、资源限制、其他约束",
        "key_aspects": ["预算范围", "时间节点", "资源限制", "优先级"]
    }
}


def normalize_scenario_dimensions(raw_dimensions) -> list[dict]:
    """规范化场景维度，过滤无效项，避免历史脏数据导致接口 500。"""
    normalized: list[dict] = []
    seen_ids: set[str] = set()

    if not isinstance(raw_dimensions, list):
        return normalized

    for dim in raw_dimensions:
        if not isinstance(dim, dict):
            continue

        dim_id = str(dim.get("id") or "").strip()
        if not dim_id or dim_id in seen_ids:
            continue

        safe_dim = dict(dim)
        safe_dim["id"] = dim_id

        dim_name = safe_dim.get("name")
        if not isinstance(dim_name, str) or not dim_name.strip():
            safe_dim["name"] = dim_id

        key_aspects = safe_dim.get("key_aspects")
        if isinstance(key_aspects, list):
            safe_dim["key_aspects"] = [str(item).strip() for item in key_aspects if str(item).strip()]
        else:
            safe_dim["key_aspects"] = []

        seen_ids.add(dim_id)
        normalized.append(safe_dim)

    return normalized


def build_default_dimension_entries() -> list[dict]:
    """构造可用的默认维度配置（最终兜底）。"""
    entries: list[dict] = []
    for dim_id, dim_info in DIMENSION_INFO.items():
        key_aspects = dim_info.get("key_aspects", [])
        entries.append({
            "id": dim_id,
            "name": dim_info.get("name", dim_id),
            "description": dim_info.get("description", ""),
            "key_aspects": key_aspects if isinstance(key_aspects, list) else [],
            "min_questions": 2,
            "max_questions": 4,
        })
    return entries


def get_dimension_info_for_session(session: dict) -> dict:
    """
    获取会话的维度信息（支持动态场景）

    优先从会话的 scenario_config 中获取，
    如果不存在则使用默认的 DIMENSION_INFO。

    Args:
        session: 会话数据

    Returns:
        维度信息字典 {dim_id: {name, description, key_aspects}}
    """
    scenario_config = session.get("scenario_config")
    if isinstance(scenario_config, dict):
        scenario_dimensions = normalize_scenario_dimensions(scenario_config.get("dimensions", []))
    else:
        scenario_dimensions = []

    if scenario_dimensions:
        return {
            dim["id"]: {
                "name": dim.get("name", dim["id"]),
                "description": dim.get("description", ""),
                "key_aspects": dim.get("key_aspects", []),
                "weight": dim.get("weight"),
                "scoring_criteria": dim.get("scoring_criteria")
            }
            for dim in scenario_dimensions
        }

    # 向后兼容：返回默认维度
    return DIMENSION_INFO


def get_dimension_order_for_session(session: dict) -> list:
    """
    获取会话的维度顺序列表

    Args:
        session: 会话数据

    Returns:
        维度 ID 列表
    """
    scenario_config = session.get("scenario_config")
    if isinstance(scenario_config, dict):
        scenario_dimensions = normalize_scenario_dimensions(scenario_config.get("dimensions", []))
    else:
        scenario_dimensions = []

    if scenario_dimensions:
        return [dim["id"] for dim in scenario_dimensions]

    # 向后兼容：返回默认顺序
    return list(DIMENSION_INFO.keys())


# ============ 滑动窗口上下文管理 ============
# 运行策略配置已在文件顶部「配置中心（集中管理）」统一定义


# ============ 智能文档摘要实现 ============

def get_document_hash(content: str) -> str:
    """计算文档内容的hash值，用于摘要缓存"""
    import hashlib
    return hashlib.md5(content.encode('utf-8')).hexdigest()[:16]


def get_cached_summary(doc_hash: str) -> Optional[str]:
    """获取缓存的文档摘要"""
    if not SUMMARY_CACHE_ENABLED:
        return None

    cache_file = SUMMARIES_DIR / f"{doc_hash}.txt"
    if cache_file.exists():
        try:
            summary = cache_file.read_text(encoding='utf-8')
            if ENABLE_DEBUG_LOG:
                print(f"📋 使用缓存的文档摘要: {doc_hash}")
            return summary
        except Exception as e:
            if ENABLE_DEBUG_LOG:
                print(f"⚠️  读取摘要缓存失败: {e}")
    return None


def save_summary_cache(doc_hash: str, summary: str) -> None:
    """保存文档摘要到缓存"""
    if not SUMMARY_CACHE_ENABLED:
        return

    cache_file = SUMMARIES_DIR / f"{doc_hash}.txt"
    try:
        cache_file.write_text(summary, encoding='utf-8')
        if ENABLE_DEBUG_LOG:
            print(f"💾 摘要已缓存: {doc_hash}")
    except Exception as e:
        if ENABLE_DEBUG_LOG:
            print(f"⚠️  保存摘要缓存失败: {e}")


def summarize_document(content: str, doc_name: str = "文档", topic: str = "") -> tuple[str, bool]:
    """
    智能文档摘要生成（第三阶段优化核心功能）

    当文档过长时，使用AI生成保留关键信息的摘要，而非简单截断。

    Args:
        content: 文档原始内容
        doc_name: 文档名称（用于提示）
        topic: 访谈主题（用于生成更相关的摘要）

    Returns:
        tuple[str, bool]: (处理后的内容, 是否生成了摘要)
    """
    original_length = len(content)

    # 如果文档长度未超过阈值，直接返回原文
    if original_length <= SMART_SUMMARY_THRESHOLD:
        return content, False

    summary_client = resolve_ai_client(call_type="summary")

    # 如果未启用智能摘要或没有AI客户端，使用简单截断
    if not ENABLE_SMART_SUMMARY or not summary_client:
        truncated = content[:MAX_DOC_LENGTH]
        if ENABLE_DEBUG_LOG:
            print(f"📄 文档 {doc_name} 使用简单截断: {original_length} -> {MAX_DOC_LENGTH} 字符")
        return truncated, False

    # 检查缓存
    doc_hash = get_document_hash(content)
    cached = get_cached_summary(doc_hash)
    if cached:
        return cached, True

    # 生成智能摘要
    if ENABLE_DEBUG_LOG:
        print(f"🤖 为文档 {doc_name} 生成智能摘要: {original_length} -> ~{SMART_SUMMARY_TARGET} 字符")

    # 构建摘要生成prompt
    summary_prompt = f"""请为以下文档生成一个精炼的摘要。

## 要求
1. 摘要长度控制在 {SMART_SUMMARY_TARGET} 字符以内
2. 保留文档中的关键信息、核心观点和重要数据
3. 如果文档与"{topic}"主题相关，优先保留与主题相关的内容
4. 使用简洁清晰的语言，避免冗余
5. 保持信息的准确性，不要添加文档中没有的内容

## 文档名称
{doc_name}

## 文档内容
{content[:8000]}

## 输出格式
直接输出摘要内容，不要添加"摘要："等前缀。"""

    try:
        import time
        start_time = time.time()

        with ai_call_priority_slot("doc_summary"):
            response = summary_client.messages.create(
                model=resolve_model_name(call_type="summary"),
                max_tokens=MAX_TOKENS_SUMMARY,
                timeout=60.0,  # 摘要生成用较短超时
                messages=[{"role": "user", "content": summary_prompt}]
            )

        response_time = time.time() - start_time
        summary = extract_message_text(response)
        if not summary:
            raise ValueError("模型响应中未包含摘要文本")

        # 记录metrics
        metrics_collector.record_api_call(
            call_type="doc_summary",
            prompt_length=len(summary_prompt),
            response_time=response_time,
            success=True,
            timeout=False,
            max_tokens=MAX_TOKENS_SUMMARY
        )

        # 保存到缓存
        save_summary_cache(doc_hash, summary)

        if ENABLE_DEBUG_LOG:
            print(f"✅ 摘要生成成功: {original_length} -> {len(summary)} 字符 ({response_time:.1f}s)")

        return summary, True

    except Exception as e:
        if ENABLE_DEBUG_LOG:
            print(f"⚠️  摘要生成失败，回退到简单截断: {e}")

        # 记录失败的metrics
        metrics_collector.record_api_call(
            call_type="doc_summary",
            prompt_length=len(summary_prompt) if 'summary_prompt' in locals() else 0,
            response_time=0,
            success=False,
            timeout="timeout" in str(e).lower(),
            error_msg=str(e),
            max_tokens=MAX_TOKENS_SUMMARY
        )

        # 回退到简单截断
        return content[:MAX_DOC_LENGTH], False


def process_document_for_context(doc: dict, remaining_length: int, topic: str = "") -> tuple[str, str, int, bool]:
    """
    处理文档以用于上下文（统一的文档处理入口）

    Args:
        doc: 文档字典，包含 name 和 content
        remaining_length: 剩余可用长度
        topic: 访谈主题

    Returns:
        tuple[str, str, int, bool]: (文档名, 处理后的内容, 使用的长度, 是否被摘要/截断)
    """
    doc_name = doc.get('name', '文档')
    content = doc.get('content', '')

    if not content:
        return doc_name, '', 0, False

    original_length = len(content)
    max_allowed = min(MAX_DOC_LENGTH, remaining_length)

    # 如果文档很短（不超过摘要阈值），直接使用
    if original_length <= SMART_SUMMARY_THRESHOLD:
        # 但如果超过max_allowed，仍需截断
        if original_length > max_allowed:
            return doc_name, content[:max_allowed], max_allowed, True
        return doc_name, content, original_length, False

    # 文档超过摘要阈值，尝试智能摘要
    if ENABLE_SMART_SUMMARY:
        processed_content, is_summarized = summarize_document(content, doc_name, topic)

        # 如果摘要后仍然过长，再截断
        if len(processed_content) > max_allowed:
            processed_content = processed_content[:max_allowed]

        return doc_name, processed_content, len(processed_content), True

    # 未启用智能摘要，简单截断
    truncated = content[:max_allowed]
    return doc_name, truncated, len(truncated), True


def generate_history_summary(session: dict, exclude_recent: int = 5, allow_ai_generation: bool = True) -> Optional[str]:
    """
    生成历史访谈记录的摘要

    Args:
        session: 会话数据
        exclude_recent: 排除最近N条记录（这些会保留完整内容）
        allow_ai_generation: 是否允许同步触发 AI 摘要生成

    Returns:
        摘要文本，如果无需摘要则返回 None
    """
    interview_log = session.get("interview_log", [])

    # 如果记录太少，不需要摘要
    if len(interview_log) <= exclude_recent:
        return None

    # 获取需要摘要的历史记录
    history_logs = interview_log[:-exclude_recent] if exclude_recent > 0 else interview_log

    if not history_logs:
        return None

    # 检查是否有缓存的摘要
    cached_summary = session.get("context_summary", {})
    cached_count = cached_summary.get("log_count", 0)

    # 如果缓存的摘要覆盖了相同数量的记录，直接使用缓存
    if cached_count == len(history_logs) and cached_summary.get("text"):
        if ENABLE_DEBUG_LOG:
            print(f"📋 使用缓存的历史摘要（覆盖 {cached_count} 条记录）")
        return cached_summary["text"]

    # 问题主链路优先：若禁用同步 AI 摘要，则先走轻量本地摘要并异步补全缓存
    if not allow_ai_generation:
        if ENABLE_DEBUG_LOG:
            print(f"📋 历史摘要缓存未命中，先使用轻量摘要（覆盖 {len(history_logs)} 条记录）")
        return _generate_simple_summary(history_logs, session)

    # 需要生成新摘要
    if not resolve_ai_client(call_type="summary"):
        # 无 AI 时使用简单摘要
        return _generate_simple_summary(history_logs, session)

    # 构建摘要生成 prompt
    summary_prompt = _build_summary_prompt(session.get("topic", ""), history_logs, session)

    try:
        if ENABLE_DEBUG_LOG:
            print(f"🗜️ 正在生成历史摘要（{len(history_logs)} 条记录）...")

        summary_text = call_claude(summary_prompt, max_tokens=300, call_type="summary")

        if summary_text:
            if ENABLE_DEBUG_LOG:
                print(f"✅ 历史摘要生成成功，长度: {len(summary_text)} 字符")
            return summary_text
    except Exception as e:
        print(f"⚠️ 生成历史摘要失败: {e}")

    # 失败时回退到简单摘要
    return _generate_simple_summary(history_logs, session)


def _build_summary_prompt(topic: str, logs: list, session: dict = None) -> str:
    """构建摘要生成的 prompt"""
    # 获取维度信息
    summary_dim_info = get_dimension_info_for_session(session) if session else DIMENSION_INFO

    # 按维度整理
    by_dim = {}
    for log in logs:
        dim = log.get("dimension", "other")
        if dim not in by_dim:
            by_dim[dim] = []
        by_dim[dim].append(log)

    logs_text = ""
    for dim, dim_logs in by_dim.items():
        dim_name = summary_dim_info.get(dim, {}).get("name", dim)
        logs_text += f"\n【{dim_name}】\n"
        for log in dim_logs:
            logs_text += f"Q: {log['question'][:80]}\nA: {log['answer'][:100]}\n"

    return f"""请将以下访谈记录压缩为简洁的摘要，保留关键信息点。

访谈主题：{topic}

访谈记录：
{logs_text}

要求：
1. 按维度整理关键信息
2. 每个维度用1-2句话概括核心要点
3. 保留具体的数据、指标、选择
4. 总长度控制在200字以内
5. 直接输出摘要内容，不要添加其他说明

摘要："""


def _generate_simple_summary(logs: list, session: dict = None) -> str:
    """生成简单摘要（无 AI 时使用）"""
    simple_sum_dim_info = get_dimension_info_for_session(session) if session else DIMENSION_INFO
    by_dim = {}
    for log in logs:
        dim = log.get("dimension", "other")
        dim_name = simple_sum_dim_info.get(dim, {}).get("name", dim)
        if dim_name not in by_dim:
            by_dim[dim_name] = []
        # 只保留答案的关键部分
        answer = log.get("answer", "")[:50]
        by_dim[dim_name].append(answer)

    parts = []
    for dim_name, answers in by_dim.items():
        parts.append(f"【{dim_name}】: {'; '.join(answers[:3])}")

    return " | ".join(parts)


def update_context_summary(session_id: str) -> None:
    """
    更新会话的上下文摘要（在提交回答后调用）

    只有当历史记录超过阈值时才生成摘要
    """
    if not session_id:
        return

    session_file = SESSIONS_DIR / f"{session_id}.json"
    if not session_file.exists():
        return

    session = safe_load_session(session_file)
    if not isinstance(session, dict):
        return

    interview_log = session.get("interview_log", [])

    # 未超过阈值，不需要摘要
    if len(interview_log) < SUMMARY_THRESHOLD:
        return

    # 计算需要摘要的记录数
    history_count = len(interview_log) - CONTEXT_WINDOW_SIZE
    if history_count <= 0:
        return

    # 检查是否需要更新摘要
    cached_summary = session.get("context_summary", {})
    if cached_summary.get("log_count", 0) >= history_count:
        return  # 缓存仍然有效

    # 生成新摘要
    history_logs = interview_log[:history_count]
    summary_text = ""

    if resolve_ai_client(call_type="summary"):
        summary_prompt = _build_summary_prompt(session.get("topic", ""), history_logs, session)
        try:
            summary_text = call_claude(summary_prompt, max_tokens=300, call_type="summary") or ""
        except Exception as e:
            print(f"⚠️ 更新上下文摘要失败: {e}")

    if not summary_text:
        summary_text = _generate_simple_summary(history_logs, session)
    if not summary_text:
        return

    # 写回前重新读取最新会话，避免异步线程覆盖新回答
    latest_session = safe_load_session(session_file)
    if not isinstance(latest_session, dict):
        return

    latest_logs = latest_session.get("interview_log", [])
    latest_history_count = len(latest_logs) - CONTEXT_WINDOW_SIZE
    if latest_history_count <= 0:
        return

    # 生成期间若有新回答，改用最新快照做本地摘要，避免写入过期内容
    if len(latest_logs) != len(interview_log):
        summary_text = _generate_simple_summary(latest_logs[:latest_history_count], latest_session)
        history_count = latest_history_count
    else:
        history_count = min(history_count, latest_history_count)

    latest_cached = latest_session.get("context_summary", {})
    if latest_cached.get("log_count", 0) >= history_count:
        return

    latest_session["context_summary"] = {
        "text": summary_text,
        "log_count": history_count,
        "updated_at": get_utc_now()
    }
    save_session_json_and_sync(session_file, latest_session)
    if ENABLE_DEBUG_LOG:
        print(f"📝 已更新上下文摘要: session={session_id}, 覆盖={history_count}条")


# ============ 智能追问评估 ============

# 维度追问敏感度（越高越容易触发追问）
DIMENSION_FOLLOW_UP_SENSITIVITY = {
    "customer_needs": 0.8,       # 客户需求最需要深挖
    "business_process": 0.6,     # 业务流程需要一定深度
    "tech_constraints": 0.5,     # 技术约束相对明确
    "project_constraints": 0.4,  # 项目约束通常较直接
}

# ============ 追问优化系统配置 ============

# 访谈模式配置
INTERVIEW_MODES = {
    "quick": {
        "name": "快速模式",
        "formal_questions_per_dim": 2,
        "max_formal_questions_per_dim": 2,
        "follow_up_budget_per_dim": 2,
        "total_follow_up_budget": 8,
        "max_questions_per_formal": 1,  # 每个正式问题最多追问次数
        "estimated_questions": "12-16"
    },
    "standard": {
        "name": "标准模式",
        "formal_questions_per_dim": 3,
        "max_formal_questions_per_dim": 3,
        "follow_up_budget_per_dim": 4,
        "total_follow_up_budget": 16,
        "max_questions_per_formal": 2,
        "estimated_questions": "20-28"
    },
    "deep": {
        "name": "深度模式",
        "formal_questions_per_dim": 4,
        "max_formal_questions_per_dim": 4,
        "follow_up_budget_per_dim": 6,
        "total_follow_up_budget": 24,
        "max_questions_per_formal": 3,
        "estimated_questions": "28-40"
    }
}

# 访谈模式 V2 配置（深度增强）
INTERVIEW_MODES_V2 = {
    "quick": {
        "formal_questions_per_dim": 2,
        "max_formal_questions_per_dim": 3,
        "follow_up_budget_per_dim": 3,
        "total_follow_up_budget": 10,
        "max_questions_per_formal": 1,
        "estimated_questions": "14-20",
        "quality_thresholds": {
            "coverage": 0.65,
            "depth": 0.45,
            "volume": 0.35,
            "high": 0.65,
            "medium": 0.5,
            "low": 0.35,
        },
    },
    "standard": {
        "formal_questions_per_dim": 3,
        "max_formal_questions_per_dim": 4,
        "follow_up_budget_per_dim": 5,
        "total_follow_up_budget": 18,
        "max_questions_per_formal": 2,
        "estimated_questions": "24-34",
        "quality_thresholds": {
            "coverage": 0.8,
            "depth": 0.6,
            "volume": 0.45,
            "high": 0.8,
            "medium": 0.65,
            "low": 0.45,
        },
    },
    "deep": {
        "formal_questions_per_dim": 4,
        "max_formal_questions_per_dim": 6,
        "follow_up_budget_per_dim": 8,
        "total_follow_up_budget": 30,
        "max_questions_per_formal": 3,
        "estimated_questions": "34-52",
        "quality_thresholds": {
            "coverage": 0.9,
            "depth": 0.72,
            "volume": 0.6,
            "high": 0.9,
            "medium": 0.75,
            "low": 0.6,
        },
    },
}

# 默认模式
DEFAULT_INTERVIEW_MODE = "standard"

# 追问硬触发信号（V2）
HARD_FOLLOW_UP_SIGNALS = {
    "vague_expression",
    "generic_answer",
    "option_only",
    "contradiction_detected",
}

# 疲劳度信号权重
FATIGUE_SIGNALS = {
    "consecutive_short": {
        "description": "连续 3 个回答少于 30 字符",
        "threshold": 3,
        "weight": 0.3
    },
    "option_only_streak": {
        "description": "连续 3 次只选选项不补充",
        "threshold": 3,
        "weight": 0.25
    },
    "same_dimension_too_long": {
        "description": "同一维度已问 8+ 问题",
        "threshold": 8,
        "weight": 0.25
    },
    "total_questions_high": {
        "description": "总问题数超过 25",
        "threshold": 25,
        "weight": 0.2
    }
}

# 信息饱和度阈值
SATURATION_THRESHOLDS = {
    "high": 0.8,       # 高饱和度，停止追问
    "medium": 0.6,     # 中等饱和度，最多再追问1次
    "low": 0.4         # 低饱和度，正常追问
}


def get_mode_identifier(session: dict) -> str:
    """获取会话模式ID（做容错）。"""
    if not isinstance(session, dict):
        return DEFAULT_INTERVIEW_MODE
    mode = session.get("interview_mode", DEFAULT_INTERVIEW_MODE)
    if mode not in INTERVIEW_MODES:
        return DEFAULT_INTERVIEW_MODE
    return mode


def get_mode_saturation_thresholds(session: dict) -> dict:
    """获取当前模式的饱和度阈值。"""
    mode_config = get_interview_mode_config(session)
    quality = mode_config.get("quality_thresholds") or {}
    return {
        "high": quality.get("high", SATURATION_THRESHOLDS["high"]),
        "medium": quality.get("medium", SATURATION_THRESHOLDS["medium"]),
        "low": quality.get("low", SATURATION_THRESHOLDS["low"]),
    }


def get_interview_mode_config(session: dict) -> dict:
    """获取会话的访谈模式配置"""
    mode = get_mode_identifier(session)
    base_config = dict(INTERVIEW_MODES.get(mode, INTERVIEW_MODES[DEFAULT_INTERVIEW_MODE]))
    v2_override = INTERVIEW_MODES_V2.get(mode, {})
    return {**base_config, **v2_override}


def get_interview_mode_display_config(mode: str) -> dict:
    """获取某个模式的展示配置（用于前端UI渲染）。"""
    base = dict(INTERVIEW_MODES.get(mode, INTERVIEW_MODES[DEFAULT_INTERVIEW_MODE]))
    v2_override = INTERVIEW_MODES_V2.get(mode, {})
    return {**base, **v2_override}


def calculate_dimension_coverage(session: dict, dimension: str) -> int:
    """计算维度覆盖度（只统计正式问题）"""
    formal_count = len([log for log in session.get("interview_log", [])
                       if log.get("dimension") == dimension and not log.get("is_follow_up", False)])
    mode_config = get_interview_mode_config(session)
    required_questions = mode_config.get("max_formal_questions_per_dim", mode_config.get("formal_questions_per_dim", 3))
    if required_questions <= 0:
        return 100
    return min(100, int(formal_count / required_questions * 100))


def get_follow_up_budget_status(session: dict, dimension: str) -> dict:
    """
    计算追问预算使用情况

    Returns:
        {
            "total_used": int,           # 已使用的总追问次数
            "total_budget": int,         # 总预算
            "dimension_used": int,       # 当前维度已使用追问次数
            "dimension_budget": int,     # 当前维度预算
            "current_question_used": int, # 当前正式问题已追问次数
            "current_question_budget": int, # 当前正式问题追问预算
            "can_follow_up": bool,       # 是否还能追问
            "budget_exhausted_reason": str or None  # 预算耗尽原因
        }
    """
    mode_config = get_interview_mode_config(session)
    interview_log = session.get("interview_log", [])

    # 计算总追问次数
    total_follow_ups = len([log for log in interview_log if log.get("is_follow_up", False)])
    total_budget = mode_config["total_follow_up_budget"]

    # 计算当前维度的追问次数
    dim_logs = [log for log in interview_log if log.get("dimension") == dimension]
    dim_follow_ups = len([log for log in dim_logs if log.get("is_follow_up", False)])
    dim_budget = mode_config["follow_up_budget_per_dim"]

    # 计算当前正式问题的追问次数
    # 找到最后一个正式问题的索引
    formal_indices = [i for i, log in enumerate(dim_logs) if not log.get("is_follow_up", False)]
    if formal_indices:
        last_formal_idx = formal_indices[-1]
        # 统计这个正式问题之后的追问数
        current_question_follow_ups = len([
            log for log in dim_logs[last_formal_idx + 1:]
            if log.get("is_follow_up", False)
        ])
    else:
        current_question_follow_ups = 0
    current_question_budget = mode_config["max_questions_per_formal"]

    # 判断是否能继续追问
    can_follow_up = True
    budget_exhausted_reason = None

    if total_follow_ups >= total_budget:
        can_follow_up = False
        budget_exhausted_reason = "total_budget_exhausted"
    elif dim_follow_ups >= dim_budget:
        can_follow_up = False
        budget_exhausted_reason = "dimension_budget_exhausted"
    elif current_question_follow_ups >= current_question_budget:
        can_follow_up = False
        budget_exhausted_reason = "question_budget_exhausted"

    return {
        "total_used": total_follow_ups,
        "total_budget": total_budget,
        "dimension_used": dim_follow_ups,
        "dimension_budget": dim_budget,
        "current_question_used": current_question_follow_ups,
        "current_question_budget": current_question_budget,
        "can_follow_up": can_follow_up,
        "budget_exhausted_reason": budget_exhausted_reason
    }


def calculate_dimension_saturation(session: dict, dimension: str) -> dict:
    """
    计算维度的信息饱和度

    Returns:
        {
            "saturation_score": float,   # 0-1 饱和度分数
            "coverage_score": float,     # 关键方面覆盖度
            "depth_score": float,        # 信息深度
            "volume_score": float,       # 信息量
            "covered_aspects": list,     # 已覆盖的关键方面
            "level": str                 # "high", "medium", "low"
        }
    """
    interview_log = session.get("interview_log", [])
    dim_logs = [log for log in interview_log if log.get("dimension") == dimension]

    if not dim_logs:
        return {
            "saturation_score": 0,
            "coverage_score": 0,
            "depth_score": 0,
            "volume_score": 0,
            "covered_aspects": [],
            "level": "low"
        }

    session_dim_info = get_dimension_info_for_session(session)
    dim_info = session_dim_info.get(dimension, {})
    key_aspects = dim_info.get("key_aspects", [])

    # 1. 信息覆盖度：检查关键方面是否被提及
    all_answers = " ".join([log.get("answer", "") for log in dim_logs])
    all_questions = " ".join([log.get("question", "") for log in dim_logs])
    combined_text = all_answers + all_questions

    covered_aspects = []
    for aspect in key_aspects:
        # 检查关键词是否出现在问答中
        if aspect in combined_text:
            covered_aspects.append(aspect)
        else:
            # 检查相关词
            aspect_keywords = {
                "核心痛点": ["痛点", "问题", "困难", "挑战", "困扰"],
                "期望价值": ["价值", "收益", "效果", "目标", "期望"],
                "使用场景": ["场景", "情况", "使用", "应用", "何时"],
                "用户角色": ["用户", "角色", "人员", "谁", "使用者"],
                "关键流程": ["流程", "步骤", "环节", "过程"],
                "角色分工": ["分工", "职责", "负责", "部门"],
                "触发事件": ["触发", "开始", "启动", "何时"],
                "异常处理": ["异常", "错误", "失败", "例外"],
                "部署方式": ["部署", "云", "本地", "服务器"],
                "系统集成": ["集成", "对接", "接口", "系统"],
                "性能要求": ["性能", "响应", "并发", "速度"],
                "安全合规": ["安全", "合规", "权限", "加密"],
                "预算范围": ["预算", "费用", "成本", "价格"],
                "时间节点": ["时间", "期限", "周期", "何时"],
                "资源限制": ["资源", "人力", "团队", "限制"],
                "优先级": ["优先", "重要", "紧急", "先后"]
            }
            for keyword in aspect_keywords.get(aspect, []):
                if keyword in combined_text:
                    covered_aspects.append(aspect)
                    break

    coverage_score = len(covered_aspects) / len(key_aspects) if key_aspects else 0

    # 2. 信息深度：检查是否有量化、具体场景、对比等深度信号
    depth_signals = 0
    # 检查数字（量化信息）
    if any(c.isdigit() for c in all_answers):
        depth_signals += 1
    # 检查具体场景描述（包含"比如"、"例如"、"当...时"等）
    scenario_keywords = ["比如", "例如", "当", "如果", "场景", "情况下"]
    if any(kw in all_answers for kw in scenario_keywords):
        depth_signals += 1
    # 检查对比或选择（"而不是"、"优先"、"相比"）
    comparison_keywords = ["而不是", "优先", "相比", "更重要", "首先"]
    if any(kw in all_answers for kw in comparison_keywords):
        depth_signals += 1
    # 检查原因说明（"因为"、"由于"、"所以"）
    reason_keywords = ["因为", "由于", "所以", "原因是"]
    if any(kw in all_answers for kw in reason_keywords):
        depth_signals += 1
    # 检查多点回答
    if "；" in all_answers or "、" in all_answers:
        depth_signals += 1

    depth_score = min(1.0, depth_signals / 5)

    # 3. 信息量：基于总字符数
    total_chars = sum(len(log.get("answer", "")) for log in dim_logs)
    # 期望每个维度至少收集 300 字符的有效信息
    volume_score = min(1.0, total_chars / 300)

    # 综合饱和度
    saturation_score = coverage_score * 0.4 + depth_score * 0.3 + volume_score * 0.3

    thresholds = get_mode_saturation_thresholds(session)

    # 确定饱和度级别
    if saturation_score >= thresholds["high"]:
        level = "high"
    elif saturation_score >= thresholds["medium"]:
        level = "medium"
    else:
        level = "low"

    return {
        "saturation_score": round(saturation_score, 2),
        "coverage_score": round(coverage_score, 2),
        "depth_score": round(depth_score, 2),
        "volume_score": round(volume_score, 2),
        "covered_aspects": covered_aspects,
        "level": level
    }


def calculate_user_fatigue(session: dict, dimension: str) -> dict:
    """
    计算用户疲劳度

    Returns:
        {
            "fatigue_score": float,      # 0-1 疲劳度分数
            "detected_signals": list,    # 检测到的疲劳信号
            "sensitivity_modifier": float, # 追问敏感度调整系数 (0.5-1.0)
            "should_force_progress": bool  # 是否应该强制推进
        }
    """
    interview_log = session.get("interview_log", [])
    dim_logs = [log for log in interview_log if log.get("dimension") == dimension]

    detected_signals = []
    fatigue_score = 0

    # 1. 检查连续简短回答
    recent_answers = [log.get("answer", "") for log in interview_log[-5:]]
    short_count = sum(1 for ans in recent_answers if len(ans.strip()) < 30)
    if short_count >= FATIGUE_SIGNALS["consecutive_short"]["threshold"]:
        detected_signals.append("consecutive_short")
        fatigue_score += FATIGUE_SIGNALS["consecutive_short"]["weight"]

    # 2. 检查连续只选选项
    recent_logs = interview_log[-5:]
    option_only_count = 0
    for log in recent_logs:
        options = log.get("options", [])
        answer = log.get("answer", "")
        if options and answer in options and len(answer) < 40:
            option_only_count += 1
    if option_only_count >= FATIGUE_SIGNALS["option_only_streak"]["threshold"]:
        detected_signals.append("option_only_streak")
        fatigue_score += FATIGUE_SIGNALS["option_only_streak"]["weight"]

    # 3. 检查同一维度问题过多
    if len(dim_logs) >= FATIGUE_SIGNALS["same_dimension_too_long"]["threshold"]:
        detected_signals.append("same_dimension_too_long")
        fatigue_score += FATIGUE_SIGNALS["same_dimension_too_long"]["weight"]

    # 4. 检查总问题数
    if len(interview_log) >= FATIGUE_SIGNALS["total_questions_high"]["threshold"]:
        detected_signals.append("total_questions_high")
        fatigue_score += FATIGUE_SIGNALS["total_questions_high"]["weight"]

    fatigue_score = min(1.0, fatigue_score)

    # 计算敏感度调整系数（疲劳度越高，追问敏感度越低）
    # 当 fatigue_score = 0 时，modifier = 1.0
    # 当 fatigue_score = 1 时，modifier = 0.5
    sensitivity_modifier = 1.0 - (fatigue_score * 0.5)

    # 判断是否应该强制推进
    should_force_progress = fatigue_score >= 0.8

    return {
        "fatigue_score": round(fatigue_score, 2),
        "detected_signals": detected_signals,
        "sensitivity_modifier": round(sensitivity_modifier, 2),
        "should_force_progress": should_force_progress
    }


def get_dimension_missing_aspects(session: dict, dimension: str) -> list:
    """获取当前维度尚未覆盖的关键方面。"""
    saturation = calculate_dimension_saturation(session, dimension)
    covered = set(saturation.get("covered_aspects", []))
    dim_info = get_dimension_info_for_session(session).get(dimension, {})
    key_aspects = dim_info.get("key_aspects", [])
    return [aspect for aspect in key_aspects if aspect and aspect not in covered]


def get_follow_up_round_for_dimension_logs(dim_logs: list) -> int:
    """计算当前维度最后一个正式问题的追问轮次。"""
    formal_indices = [i for i, log in enumerate(dim_logs) if not log.get("is_follow_up", False)]
    if not formal_indices:
        return 0

    last_formal_idx = formal_indices[-1]
    chained = 0
    for log in dim_logs[last_formal_idx + 1:]:
        if log.get("is_follow_up", False):
            chained += 1
        else:
            break
    return chained


def has_pending_forced_follow_up(session: dict, dimension: str) -> bool:
    """判断当前维度是否存在待执行的强制追问。"""
    dim_logs = [log for log in session.get("interview_log", []) if log.get("dimension") == dimension]
    if not dim_logs:
        return False

    last_log = dim_logs[-1]
    if last_log.get("is_follow_up", False):
        return False

    if last_log.get("hard_triggered") and not last_log.get("user_skip_follow_up", False):
        return True

    return False


def evaluate_answer_quality(eval_result: dict, answer: str, is_follow_up: bool, follow_up_round: int) -> dict:
    """将回答评估结果映射为质量分数与标签。"""
    signals = eval_result.get("signals", [])
    hard_triggered = eval_result.get("hard_triggered", False)

    quality_score = 0.5
    answer_len = len((answer or "").strip())

    if answer_len >= 120:
        quality_score += 0.2
    elif answer_len >= 80:
        quality_score += 0.1

    if eval_result.get("has_numbers"):
        quality_score += 0.1

    scenario_keywords = ["比如", "例如", "当", "如果", "场景", "案例"]
    if any(keyword in (answer or "") for keyword in scenario_keywords):
        quality_score += 0.1

    negative_penalty = {
        "too_short": 0.2,
        "vague_expression": 0.25,
        "generic_answer": 0.3,
        "option_only": 0.2,
        "no_quantification": 0.1,
        "single_selection": 0.1,
        "contradiction_detected": 0.25,
    }
    quality_score -= sum(negative_penalty.get(signal, 0.05) for signal in signals)

    if is_follow_up and follow_up_round >= 1 and not hard_triggered:
        quality_score += 0.05

    quality_score = max(0.0, min(1.0, quality_score))

    quality_signals = []
    if quality_score >= 0.75:
        quality_signals.append("high_quality")
    if eval_result.get("has_numbers"):
        quality_signals.append("quantified")
    if answer_len >= 80:
        quality_signals.append("detailed")

    for signal in signals:
        if signal not in quality_signals:
            quality_signals.append(signal)

    return {
        "quality_score": round(quality_score, 2),
        "quality_signals": quality_signals,
        "hard_triggered": bool(hard_triggered),
    }


def evaluate_dimension_completion_v2(session: dict, dimension: str) -> dict:
    """维度完成门禁（V2）：题量 + 质量 + 强制追问。"""
    mode_config = get_interview_mode_config(session)
    dim_logs = [log for log in session.get("interview_log", []) if log.get("dimension") == dimension]
    formal_count = len([log for log in dim_logs if not log.get("is_follow_up", False)])
    min_formal = mode_config.get("formal_questions_per_dim", 3)
    max_formal = mode_config.get("max_formal_questions_per_dim", min_formal)

    budget_status = get_follow_up_budget_status(session, dimension)
    saturation = calculate_dimension_saturation(session, dimension)
    fatigue = calculate_user_fatigue(session, dimension)

    quality_thresholds = mode_config.get("quality_thresholds") or {}
    coverage_threshold = quality_thresholds.get("coverage", 0.8)
    depth_threshold = quality_thresholds.get("depth", 0.6)
    volume_threshold = quality_thresholds.get("volume", 0.45)

    missing_aspects = get_dimension_missing_aspects(session, dimension)
    follow_up_round = get_follow_up_round_for_dimension_logs(dim_logs)
    pending_forced_follow_up = has_pending_forced_follow_up(session, dimension)

    snapshot = {
        "formal_count": formal_count,
        "min_formal": min_formal,
        "max_formal": max_formal,
        "coverage": saturation.get("coverage_score", 0),
        "depth": saturation.get("depth_score", 0),
        "volume": saturation.get("volume_score", 0),
        "saturation": saturation.get("saturation_score", 0),
        "missing_aspects": missing_aspects,
        "follow_up_round": follow_up_round,
        "pending_forced_follow_up": pending_forced_follow_up,
        "budget_status": budget_status,
        "fatigue": fatigue,
    }

    # 1. 待执行强制追问
    if pending_forced_follow_up and follow_up_round < 1:
        return {
            "can_complete": False,
            "reason": "存在待执行的关键追问，需要至少追问1次",
            "action": "continue",
            "quality_warning": False,
            "snapshot": snapshot,
        }

    # 2. 最低正式题未达标
    if formal_count < min_formal:
        return {
            "can_complete": False,
            "reason": f"正式问题数量不足（{formal_count}/{min_formal}）",
            "action": "continue",
            "quality_warning": False,
            "snapshot": snapshot,
        }

    meets_quality = (
        saturation.get("coverage_score", 0) >= coverage_threshold
        and saturation.get("depth_score", 0) >= depth_threshold
        and saturation.get("volume_score", 0) >= volume_threshold
        and not missing_aspects
    )

    # 3. 达到质量门槛可完成
    if meets_quality and not pending_forced_follow_up:
        return {
            "can_complete": True,
            "reason": "达到维度质量门槛",
            "action": "complete",
            "quality_warning": False,
            "snapshot": snapshot,
        }

    # 4. 达到上限保护或预算耗尽，强制完成
    budget_exhausted = not budget_status.get("can_follow_up", True)
    reached_upper_bound = formal_count >= max_formal
    if reached_upper_bound or budget_exhausted:
        return {
            "can_complete": True,
            "reason": "达到上限保护，允许强制完成",
            "action": "force_complete",
            "quality_warning": not meets_quality,
            "snapshot": snapshot,
        }

    # 5. 继续提问
    return {
        "can_complete": False,
        "reason": "质量门槛未达成，继续提问",
        "action": "continue",
        "quality_warning": False,
        "snapshot": snapshot,
    }


def should_follow_up_comprehensive(session: dict, dimension: str,
                                    rule_based_result: dict) -> dict:
    """
    综合决策是否应该追问

    整合：规则评估 + 预算检查 + 饱和度 + 疲劳度

    Returns:
        {
            "should_follow_up": bool,
            "reason": str,
            "budget_status": dict,
            "saturation": dict,
            "fatigue": dict,
            "decision_factors": list  # 影响决策的因素
        }
    """
    decision_factors = []

    # 1. 检查预算
    budget_status = get_follow_up_budget_status(session, dimension)
    if not budget_status["can_follow_up"]:
        reason_map = {
            "total_budget_exhausted": "会话追问预算已用完",
            "dimension_budget_exhausted": "当前维度追问预算已用完",
            "question_budget_exhausted": "当前问题追问次数已达上限"
        }
        return {
            "should_follow_up": False,
            "reason": reason_map.get(budget_status["budget_exhausted_reason"], "预算已用完"),
            "budget_status": budget_status,
            "saturation": {},
            "fatigue": {},
            "decision_factors": ["budget_exhausted"]
        }

    fatigue = calculate_user_fatigue(session, dimension)

    # V2: 硬触发信号优先（在疲劳保护之外）
    hard_triggered = bool(rule_based_result.get("hard_triggered", False))
    if hard_triggered and fatigue.get("fatigue_score", 0) < 0.9:
        return {
            "should_follow_up": True,
            "reason": rule_based_result.get("reason") or "检测到关键模糊/冲突，需要至少追问一次",
            "budget_status": budget_status,
            "saturation": calculate_dimension_saturation(session, dimension),
            "fatigue": fatigue,
            "decision_factors": ["hard_signal_forced_follow_up"]
        }

    # 2. 检查饱和度
    saturation = calculate_dimension_saturation(session, dimension)
    if saturation["level"] == "high":
        decision_factors.append("high_saturation")
        return {
            "should_follow_up": False,
            "reason": f"信息已充分（饱和度 {saturation['saturation_score']:.0%}）",
            "budget_status": budget_status,
            "saturation": saturation,
            "fatigue": None,
            "decision_factors": decision_factors
        }

    # 3. 检查疲劳度
    if fatigue["should_force_progress"]:
        decision_factors.append("user_fatigue")
        return {
            "should_follow_up": False,
            "reason": "检测到用户疲劳，暂停追问",
            "budget_status": budget_status,
            "saturation": saturation,
            "fatigue": fatigue,
            "decision_factors": decision_factors
        }

    # 4. 基于规则评估结果，但应用疲劳度调整
    original_needs_follow_up = rule_based_result.get("needs_follow_up", False)

    if not original_needs_follow_up:
        return {
            "should_follow_up": False,
            "reason": "回答已充分",
            "budget_status": budget_status,
            "saturation": saturation,
            "fatigue": fatigue,
            "decision_factors": ["sufficient_answer"]
        }

    # 中等饱和度时限制追问
    if saturation["level"] == "medium":
        # 检查是否已经追问过
        if budget_status["current_question_used"] >= 1:
            decision_factors.append("medium_saturation_limit")
            return {
                "should_follow_up": False,
                "reason": "信息接近充分，不再追问",
                "budget_status": budget_status,
                "saturation": saturation,
                "fatigue": fatigue,
                "decision_factors": decision_factors
            }

    # 疲劳度较高时，提高追问门槛
    if fatigue["fatigue_score"] >= 0.5:
        decision_factors.append("elevated_threshold")
        # 只有非常明显需要追问的情况才追问
        if len(rule_based_result.get("signals", [])) < 2:
            return {
                "should_follow_up": False,
                "reason": "用户可能疲劳，跳过非关键追问",
                "budget_status": budget_status,
                "saturation": saturation,
                "fatigue": fatigue,
                "decision_factors": decision_factors
            }

    # 通过所有检查，可以追问
    decision_factors.append("rule_based_follow_up")
    return {
        "should_follow_up": True,
        "reason": rule_based_result.get("reason", "需要进一步了解"),
        "budget_status": budget_status,
        "saturation": saturation,
        "fatigue": fatigue,
        "decision_factors": decision_factors
    }


def score_assessment_answer(session: dict, dimension: str, question: str, answer: str) -> Optional[float]:
    """
    为评估场景的回答打分（1-5分）

    Args:
        session: 会话数据
        dimension: 维度ID
        question: 问题
        answer: 回答

    Returns:
        float: 1.0-5.0 的分数，失败返回 None
    """
    ai_client = resolve_ai_client(call_type="assessment_score")
    if not ai_client:
        return None

    # 获取维度配置
    scenario_config = session.get("scenario_config", {})
    dim_config = None
    for dim in scenario_config.get("dimensions", []):
        if dim.get("id") == dimension:
            dim_config = dim
            break

    if not dim_config:
        return None

    # 构建评分标准文本
    scoring_criteria = dim_config.get("scoring_criteria", {})
    criteria_text = "\n".join(
        f"  {score}分: {desc}"
        for score, desc in sorted(scoring_criteria.items(), key=lambda x: int(x[0]), reverse=True)
    )

    if not criteria_text:
        criteria_text = """  5分: 回答非常优秀，展现深厚专业能力
  4分: 回答良好，有清晰的思路和见解
  3分: 回答基本合格，但缺乏深度
  2分: 回答有明显不足或偏差
  1分: 回答很差，无法展现相关能力"""

    prompt = f"""你是一位专业面试官。请根据以下评分标准，对候选人的回答进行评分。

【评估维度】{dim_config.get("name", dimension)}
【维度说明】{dim_config.get("description", "")}

【评分标准】
{criteria_text}

【面试问题】
{question}

【候选人回答】
{answer}

请严格按照评分标准打分，只返回一个数字（1-5之间的整数或小数，如 3.5），不要有任何其他文字："""

    try:
        with ai_call_priority_slot("assessment_score"):
            response = ai_client.messages.create(
                model=resolve_model_name(call_type="assessment_score"),
                max_tokens=96,  # MiniMax 在低 token 下容易只返回 thinking，适当提高稳定性
                timeout=15.0,
                messages=[{"role": "user", "content": prompt}]
            )
        raw = extract_message_text(response)
        if not raw:
            raise ValueError("模型响应中未包含评分文本")
        # 提取数字
        import re
        match = re.search(r'(\d+\.?\d*)', raw)
        if match:
            score = float(match.group(1))
            return max(1.0, min(5.0, score))  # 限制在 1-5 范围
    except Exception as e:
        if ENABLE_DEBUG_LOG:
            print(f"⚠️ 评分失败: {e}")

    return None


def evaluate_answer_depth(question: str, answer: str, dimension: str,
                          options: list = None, is_follow_up: bool = False) -> dict:
    """
    评估回答深度，判断是否需要追问

    三层判断：
    1. 明确需要追问（回答太弱）
    2. 明确不需要追问（回答已充分）
    3. 建议AI评估（交给AI在生成下一题时判断）

    Returns:
        {
            "needs_follow_up": bool,       # 规则层判断结果
            "suggest_ai_eval": bool,       # 是否建议AI再次评估
            "reason": str or None,         # 追问原因
            "signals": list                # 检测到的信号
        }
    """
    signals = []
    answer_stripped = answer.strip()
    answer_len = len(answer_stripped)
    sensitivity = DIMENSION_FOLLOW_UP_SENSITIVITY.get(dimension, 0.5)

    # ---- 第一层：明确需要追问的情况 ----

    # 1. 回答过短（根据维度敏感度调整阈值）
    short_threshold = int(20 + sensitivity * 20)  # 客户需求36字符，项目约束28字符
    if answer_len < short_threshold:
        signals.append("too_short")

    # 2. 模糊表达检测（扩展词库）
    vague_indicators = [
        # 不确定类
        "看情况", "不一定", "可能", "或许", "大概", "差不多", "到时候",
        "再说", "还没想好", "不确定", "看具体", "根据情况", "待定",
        "以后再说", "暂时不清楚", "目前还不好说",
        # 笼统类
        "都可以", "都行", "随便", "无所谓", "差不多", "一般",
        # 回避类
        "不太了解", "没想过", "不知道", "说不好", "很难说",
    ]
    matched_vague = [v for v in vague_indicators if v in answer_stripped]
    if matched_vague:
        signals.append("vague_expression")

    # 3. 完全匹配泛泛回答
    generic_answers = [
        "好的", "是的", "可以", "没问题", "需要", "应该要",
        "对", "嗯", "行", "同意", "没有", "不需要",
    ]
    if answer_stripped in generic_answers:
        signals.append("generic_answer")

    # 4. 仅选择了预设选项没有补充（答案等于某个选项原文）
    if options:
        is_exact_option = answer_stripped in options
        # 单选且答案就是选项原文，缺乏自己的思考
        if is_exact_option and answer_len < 40:
            signals.append("option_only")

    # 5. 缺乏量化信息（对某些维度重要）
    has_numbers = any(c.isdigit() for c in answer_stripped)
    quantitative_dimensions = ["tech_constraints", "project_constraints"]
    if dimension in quantitative_dimensions and not has_numbers and answer_len < 60:
        signals.append("no_quantification")

    # 6. 多选但只选了一个（可能需要补充）
    if options and "；" not in answer_stripped and len(options) >= 3:
        # 检查是否是多选题但只选了一个
        selected_count = sum(1 for opt in options if opt in answer_stripped)
        if selected_count <= 1 and answer_len < 30:
            signals.append("single_selection")

    # 7. 轻量矛盾检测
    contradiction_pairs = [
        ("需要", "不需要"),
        ("可以", "不可以"),
        ("支持", "不支持"),
        ("已经", "还没"),
        ("有", "没有"),
        ("必须", "可选"),
    ]
    contradiction_detected = any(
        left in answer_stripped and right in answer_stripped
        for left, right in contradiction_pairs
    )
    if contradiction_detected:
        signals.append("contradiction_detected")

    # ---- 第二层：判断是否明确不需要追问 ----

    # 回答足够详细，不需要追问
    sufficient_signals = []
    if answer_len > 80:
        sufficient_signals.append("detailed_answer")
    if "；" in answer_stripped and answer_len > 40:
        sufficient_signals.append("multi_point_answer")
    if has_numbers and answer_len > 30:
        sufficient_signals.append("quantified_answer")

    # ---- 第三层：综合判断 ----

    # 计算追问得分（信号越多越需要追问）
    signal_weights = {
        "too_short": 0.4,
        "vague_expression": 0.5,
        "generic_answer": 0.8,
        "option_only": 0.3,
        "no_quantification": 0.2,
        "single_selection": 0.2,
        "contradiction_detected": 0.6,
    }
    follow_up_score = sum(signal_weights.get(s, 0.1) for s in signals)
    follow_up_score *= sensitivity  # 应用维度敏感度

    # 减去充分度信号
    sufficient_weights = {
        "detailed_answer": 0.5,
        "multi_point_answer": 0.3,
        "quantified_answer": 0.2,
    }
    sufficient_score = sum(sufficient_weights.get(s, 0) for s in sufficient_signals)
    follow_up_score -= sufficient_score

    hard_triggered = any(signal in HARD_FOLLOW_UP_SIGNALS for signal in signals)

    # 判断结果
    if follow_up_score >= 0.4:
        # 明确需要追问
        reason = _build_follow_up_reason(signals)
        return {"needs_follow_up": True, "suggest_ai_eval": False,
                "reason": reason, "signals": signals,
                "hard_triggered": hard_triggered,
                "has_numbers": has_numbers,
                "follow_up_score": round(follow_up_score, 2)}
    elif follow_up_score >= 0.15 and not sufficient_signals:
        # 边界情况，建议让AI评估
        reason = _build_follow_up_reason(signals)
        return {"needs_follow_up": False, "suggest_ai_eval": True,
                "reason": reason, "signals": signals,
                "hard_triggered": hard_triggered,
                "has_numbers": has_numbers,
                "follow_up_score": round(follow_up_score, 2)}
    else:
        # 不需要追问
        return {"needs_follow_up": False, "suggest_ai_eval": False,
                "reason": None, "signals": signals,
                "hard_triggered": hard_triggered,
                "has_numbers": has_numbers,
                "follow_up_score": round(follow_up_score, 2)}


def _build_follow_up_reason(signals: list) -> str:
    """根据检测到的信号构建追问原因"""
    reason_map = {
        "too_short": "回答过于简短，需要补充具体细节",
        "vague_expression": "回答包含模糊表述，需要明确具体要求",
        "generic_answer": "回答过于笼统，需要深入了解具体需求",
        "option_only": "仅选择了预设选项，需要了解具体场景和考量",
        "no_quantification": "缺少量化指标，需要明确具体数据要求",
        "single_selection": "只选择了单一选项，需要了解是否还有其他需求",
        "contradiction_detected": "回答中存在前后冲突，需要澄清真实约束",
    }
    reasons = [reason_map.get(s, "") for s in signals if s in reason_map]
    return reasons[0] if reasons else "需要进一步了解详细需求"


def build_interview_prompt(session: dict, dimension: str, all_dim_logs: list,
                           session_id: str = None,
                           session_signature: Optional[tuple[int, int]] = None) -> tuple[str, list, dict]:
    """构建访谈 prompt（使用滑动窗口 + 摘要压缩 + 智能追问）

    Args:
        session: 会话数据
        dimension: 当前维度
        all_dim_logs: 当前维度的所有访谈记录
        session_id: 会话ID（可选，用于更新思考进度状态）
        session_signature: 会话文件签名（可选，用于 prompt 构建缓存）

    Returns:
        tuple[str, list, dict]: (prompt字符串, 被截断的文档列表, 决策元数据)
    """
    topic = session.get("topic", "未知项目")
    description = session.get("description")
    # 兼容旧数据：优先使用 reference_materials，否则合并旧字段
    reference_materials = session.get("reference_materials", [])
    if not reference_materials:
        reference_materials = session.get("reference_docs", []) + session.get("research_docs", [])
    interview_log = session.get("interview_log", [])
    session_dim_info = get_dimension_info_for_session(session)
    dim_info = session_dim_info.get(dimension, {})
    cache_session_id = str(session.get("session_id", "") or "").strip()
    prompt_cache_key = _build_interview_prompt_cache_key(session_signature, dimension, cache_session_id)
    if prompt_cache_key:
        cached_prompt = _get_interview_prompt_cache(prompt_cache_key)
        if isinstance(cached_prompt, tuple) and len(cached_prompt) == 3:
            if ENABLE_DEBUG_LOG:
                print(f"📦 命中访谈 Prompt 缓存: dim={dimension}")
            return cached_prompt

    # 构建上下文
    context_parts = [f"当前访谈主题：{topic}"]

    # 如果有主题描述，添加到上下文中（限制长度）
    if description:
        context_parts.append(f"\n主题描述：{description[:500]}")

    # 添加参考资料内容（使用总长度限制 + 智能摘要）
    total_doc_length = 0
    truncated_docs = []  # 记录被处理的文档（摘要或截断）
    summarized_docs = []  # 记录使用智能摘要的文档
    if reference_materials:
        context_parts.append("\n## 参考资料：")
        for doc in reference_materials:
            if doc.get("content") and total_doc_length < MAX_TOTAL_DOCS:
                remaining = MAX_TOTAL_DOCS - total_doc_length
                original_length = len(doc["content"])

                # 使用智能摘要处理文档
                doc_name, processed_content, used_length, was_processed = process_document_for_context(
                    doc, remaining, topic
                )

                if processed_content:
                    # 根据 source 添加标记
                    source_marker = "🔄 " if doc.get("source") == "auto" else ""
                    context_parts.append(f"### {source_marker}{doc_name}")
                    context_parts.append(processed_content)
                    total_doc_length += used_length

                    # 记录处理情况
                    if was_processed:
                        if used_length < original_length * 0.6:  # 如果内容减少超过40%，可能是摘要
                            summarized_docs.append(f"{doc_name}（原{original_length}字符，摘要至{used_length}字符）")
                        else:
                            truncated_docs.append(f"{doc_name}（原{original_length}字符，截取{used_length}字符）")

    # 添加处理提示（让 AI 知道文档信息经过处理）
    if summarized_docs:
        context_parts.append(f"\n📝 注意：以下文档已通过AI生成摘要以保留关键信息：{', '.join(summarized_docs)}")
    if truncated_docs:
        context_parts.append(f"\n⚠️ 注意：以下文档因长度限制已被截断，请基于已有信息进行提问：{', '.join(truncated_docs)}")

    # ========== 智能联网搜索（规则预判 + AI决策） ==========
    # 获取最近的问答记录用于 AI 判断
    recent_qa = interview_log[-3:] if interview_log else []
    will_search, search_query, search_reason = smart_search_decision(topic, dimension, session, recent_qa)

    if will_search and search_query:
        # 更新思考状态到"搜索"阶段
        if session_id:
            update_thinking_status(session_id, "searching", has_search=True)

        if ENABLE_DEBUG_LOG:
            print(f"🔍 执行搜索: {search_query} (原因: {search_reason})")

        search_results = web_search(search_query)

        if search_results:
            context_parts.append("\n## 行业知识参考（联网搜索）：")
            for idx, result in enumerate(search_results[:2], 1):
                if result["type"] == "intent":
                    context_parts.append(f"**{result['content'][:150]}**")
                else:
                    context_parts.append(f"{idx}. **{result.get('title', '参考信息')[:40]}**")
                    context_parts.append(f"   {result['content'][:150]}")

    # ========== 滑动窗口 + 摘要压缩 ==========
    if interview_log:
        context_parts.append("\n## 已收集的信息：")

        # 判断是否需要使用摘要
        if len(interview_log) > CONTEXT_WINDOW_SIZE:
            history_count = len(interview_log) - CONTEXT_WINDOW_SIZE
            cached_summary = session.get("context_summary", {}) if isinstance(session.get("context_summary", {}), dict) else {}
            cached_count = int(cached_summary.get("log_count", 0) or 0)
            if cached_count < history_count:
                target_session_id = str(session_id or session.get("session_id", "") or "").strip()
                if target_session_id:
                    schedule_context_summary_update_async(target_session_id)

            # 问题生成主链路优先：仅使用缓存/轻量摘要，不在此处阻塞等待 AI 摘要。
            history_summary = generate_history_summary(
                session,
                exclude_recent=CONTEXT_WINDOW_SIZE,
                allow_ai_generation=False,
            )
            if history_summary:
                context_parts.append(f"\n### 历史访谈摘要（共{len(interview_log) - CONTEXT_WINDOW_SIZE}条）：")
                context_parts.append(history_summary)
                context_parts.append("\n### 最近问答记录：")

            # 只保留最近的完整记录
            recent_logs = interview_log[-CONTEXT_WINDOW_SIZE:]
        else:
            recent_logs = interview_log

        # 添加完整的最近问答记录
        base_index = len(interview_log) - len(recent_logs)
        for offset, log in enumerate(recent_logs, 1):
            follow_up_mark = " [追问]" if log.get("is_follow_up") else ""
            q_number = base_index + offset
            context_parts.append(f"- Q{q_number}: {log['question']}{follow_up_mark}")
            context_parts.append(f"  A: {log['answer']}")
            dim_name = session_dim_info.get(log.get("dimension", ""), {}).get("name", "")
            if dim_name:
                context_parts.append(f"  (维度: {dim_name})")

    # 计算正式问题数量（排除追问）
    formal_questions_count = len([log for log in all_dim_logs if not log.get("is_follow_up", False)])
    mode_config = get_interview_mode_config(session)

    # ========== 智能追问判断（综合预算+饱和度+疲劳度+规则评估） ==========
    last_log = None
    should_follow_up = False
    suggest_ai_eval = False
    follow_up_reason = ""
    eval_signals = []
    comprehensive_decision = None
    hard_triggered = False
    missing_aspects = []
    follow_up_round = get_follow_up_round_for_dimension_logs(all_dim_logs)
    remaining_question_follow_up_budget = max(0, mode_config.get("max_questions_per_formal", 1) - follow_up_round)

    if all_dim_logs:
        last_log = all_dim_logs[-1]
        last_answer = last_log.get("answer", "")
        last_question = last_log.get("question", "")
        last_options = last_log.get("options", [])
        last_is_follow_up = last_log.get("is_follow_up", False)

        # 使用增强版评估函数（规则层）
        eval_result = evaluate_answer_depth(
            question=last_question,
            answer=last_answer,
            dimension=dimension,
            options=last_options,
            is_follow_up=last_is_follow_up,
        )

        eval_signals = eval_result["signals"]
        hard_triggered = bool(eval_result.get("hard_triggered", False))

        # 使用综合决策函数（整合预算、饱和度、疲劳度）
        comprehensive_decision = should_follow_up_comprehensive(
            session=session,
            dimension=dimension,
            rule_based_result=eval_result
        )

        should_follow_up = comprehensive_decision["should_follow_up"]
        follow_up_reason = comprehensive_decision["reason"] or ""

        # 只有在规则层建议 AI 评估且综合决策允许追问时，才建议 AI 评估
        suggest_ai_eval = eval_result["suggest_ai_eval"] and comprehensive_decision["should_follow_up"]

        missing_aspects = get_dimension_missing_aspects(session, dimension)

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

    # 构建 AI 评估提示（当规则未明确触发但建议AI判断时）
    ai_eval_guidance = ""
    if suggest_ai_eval and last_log:
        ai_eval_guidance = f"""
## 回答深度评估

请先评估用户的上一个回答是否需要追问：

**上一个问题**: {last_log.get('question', '')[:100]}
**用户回答**: {last_log.get('answer', '')}
**检测信号**: {', '.join(eval_signals) if eval_signals else '无明显问题'}

判断标准（满足任一条即应追问）：
1. 回答只是选择了选项，没有说明具体场景或原因
2. 缺少量化指标（如时间、数量、频率等）
3. 回答比较笼统，没有针对性细节
4. 可能隐藏了更深层的需求或顾虑

如果判断需要追问，请：
- 设置 is_follow_up: true
- 针对上一个回答进行深入提问
- 问题要更具体，引导用户给出明确答案

如果判断不需要追问，请生成新问题继续访谈。
"""

    blindspot_guidance = ""
    if not should_follow_up:
        min_formal = mode_config.get("formal_questions_per_dim", 3)
        if formal_questions_count >= min_formal and missing_aspects:
            blindspot_guidance = f"""
## 盲区补问优先（必须执行）

当前维度仍有未覆盖关键方面：{', '.join(missing_aspects)}

生成新问题时请满足：
1. 问题必须直接点名至少 1 个未覆盖方面
2. 不要重复已充分覆盖的信息
3. 若有多个盲区，优先提问影响决策最大的方面
"""

    # 构建追问模式的提示
    follow_up_section = ""
    if should_follow_up:
        follow_up_section = f"""## 追问模式（必须执行）

上一个用户回答需要追问。原因：{follow_up_reason}

**上一个问题**: {last_log.get('question', '')[:100] if last_log else ''}
**用户回答**: {last_log.get('answer', '') if last_log else ''}

追问要求：
1. 必须设置 is_follow_up: true
2. 针对上一个回答进行深入提问，不要跳到新话题
3. 追问问题要更具体、更有针对性
4. 引导用户给出具体的场景、数据、或明确的选择
5. 可以使用"您提到的XXX，能否具体说明..."这样的句式
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
5. 如果用户的回答与参考文档内容有冲突，要在问题中指出并请求澄清
"""

    prompt = f"""**严格输出要求：你的回复必须是纯 JSON 对象，不要添加任何解释、markdown 代码块或其他文本。第一个字符必须是 {{，最后一个字符必须是 }}**

你是一个专业的访谈师，正在进行"{topic}"的访谈。
你的核心职责是**深度挖掘用户的真实需求**，不满足于表面回答。

{chr(10).join(context_parts)}

## 当前任务

你现在需要针对「{dim_info.get('name', dimension)}」维度收集信息。
这个维度关注：{dim_info.get('description', '')}

该维度已收集了 {formal_questions_count} 个正式问题的回答，关键方面包括：{', '.join(dim_info.get('key_aspects', []))}
{ai_eval_guidance}
{blindspot_guidance}
{follow_up_section}

如果信息足够，请基于已收集的回答给出对当前选项的 AI 推荐，用于辅助用户决策。若无法推荐，请将 ai_recommendation 设为 null。

## 输出格式（必须严格遵守）

你的回复必须是一个纯 JSON 对象，格式如下：

    {{
        "question": "你的问题",
        "options": ["选项1", "选项2", "选项3", "选项4"],
        "multi_select": false,
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
        "mode": get_mode_identifier(session),
        "follow_up_round": follow_up_round,
        "remaining_question_follow_up_budget": remaining_question_follow_up_budget,
        "hard_triggered": hard_triggered,
        "missing_aspects": missing_aspects,
    }

    if prompt_cache_key:
        _set_interview_prompt_cache(
            prompt_cache_key,
            prompt,
            truncated_docs,
            decision_meta,
        )

    return prompt, truncated_docs, decision_meta


def build_assessment_report_prompt(session: dict) -> str:
    """构建面试评估报告 prompt"""
    topic = session.get("topic", "候选人评估")
    description = session.get("description", "")
    interview_log = session.get("interview_log", [])
    dimensions = session.get("dimensions", {})
    scenario_config = session.get("scenario_config", {})
    assessment_config = scenario_config.get("assessment", {})

    # 获取维度配置
    dim_configs = {d["id"]: d for d in scenario_config.get("dimensions", [])}

    # 计算综合评分
    total_score = 0.0
    total_weight = 0.0
    dim_scores_info = []
    for dim_id, dim_data in dimensions.items():
        dim_config = dim_configs.get(dim_id, {})
        weight = dim_config.get("weight", 0.25)
        score = dim_data.get("score")
        if score is not None:
            total_score += score * weight
            total_weight += weight
            dim_scores_info.append({
                "id": dim_id,
                "name": dim_config.get("name", dim_id),
                "score": score,
                "weight": weight,
                "criteria": dim_config.get("scoring_criteria", {})
            })

    final_score = round(total_score / total_weight, 2) if total_weight > 0 else 0

    # 确定推荐等级
    recommendation_levels = assessment_config.get("recommendation_levels", [])
    recommendation = {"level": "D", "name": "不推荐", "color": "#ef4444"}
    for level in sorted(recommendation_levels, key=lambda x: x.get("threshold", 0), reverse=True):
        if final_score >= level.get("threshold", 0):
            recommendation = level
            break

    # 构建评分表格文本
    score_table = "| 维度 | 得分 | 权重 | 加权得分 |\n|:---|:---:|:---:|:---:|\n"
    for info in dim_scores_info:
        weighted = round(info["score"] * info["weight"], 2)
        score_table += f"| {info['name']} | {info['score']:.1f} | {info['weight']*100:.0f}% | {weighted:.2f} |\n"
    score_table += f"| **综合得分** | **{final_score:.2f}** | 100% | **{final_score:.2f}** |"

    # 按维度整理问答和评分
    qa_sections = ""
    for dim_info in dim_scores_info:
        dim_id = dim_info["id"]
        qa_list = [log for log in interview_log if log.get("dimension") == dim_id]
        qa_sections += f"\n### {dim_info['name']}（得分: {dim_info['score']:.1f}/5.0）\n"
        for qa in qa_list:
            qa_sections += f"**Q**: {qa['question']}\n"
            qa_sections += f"**A**: {qa['answer']}\n"
            if qa.get("score"):
                qa_sections += f"*单题评分: {qa['score']:.1f}*\n"
            qa_sections += "\n"

    prompt = f"""你是一位资深的面试官和人才评估专家，需要基于以下访谈记录生成一份专业的面试评估报告。

## 评估主题
{topic}
"""

    if description:
        prompt += f"""
## 背景说明
{description}
"""

    prompt += f"""
## 各维度得分

{score_table}

## 访谈记录与评分
{qa_sections}

## 报告要求

请生成一份专业的面试评估报告，包含以下章节：

### 1. 候选人概览
- 评估主题
- 评估时间
- 综合得分：**{final_score:.2f}/5.0**
- 推荐等级：**{recommendation.get('name', '待定')}** ({recommendation.get('level', 'C')})

### 2. 能力雷达图
使用 Mermaid 雷达图展示各维度得分（如果 Mermaid 不支持雷达图，可用其他可视化方式替代）：

**注意**：由于 Mermaid 不原生支持雷达图，请使用以下替代方案：

```mermaid
xychart-beta
    title "能力评估雷达"
    x-axis [{', '.join([f'"{d["name"]}"' for d in dim_scores_info])}]
    y-axis "得分" 0 --> 5
    bar [{', '.join([str(d["score"]) for d in dim_scores_info])}]
```

### 3. 各维度详细分析
对每个评估维度进行详细分析：
- 该维度的得分和表现
- 具体的优势体现
- 存在的不足或待提升点
- 关键证据（引用访谈内容）

### 4. 核心优势
总结候选人的 2-3 个核心优势，用具体事例支撑

### 5. 待提升领域
指出 1-2 个需要提升的方面，给出具体建议

### 6. 推荐意见
基于综合评分 **{final_score:.2f}** 给出：
- 推荐等级：**{recommendation.get('name', '待定')}**
- 等级说明：{recommendation.get('description', '')}
- 录用建议（详细说明录用/不录用的理由，以及如果录用的注意事项）

### 7. 后续建议
- 如需进一步评估的问题
- 入职后的培养建议（如果推荐录用）

## 重要提醒
- 所有分析必须严格基于访谈记录中的实际内容
- 评分已由 AI 在访谈过程中逐题打分，请基于这些评分进行分析
- 客观公正，既要指出优势也要指出不足
- 报告要专业、结构清晰、有理有据
- 使用 Markdown 格式
- 报告末尾使用署名：*此报告由 Deep Vision 深瞳生成*

请生成完整的评估报告："""

    return prompt


def build_report_prompt(session: dict) -> str:
    """构建报告生成 prompt"""
    scenario_config = session.get("scenario_config", {}) if isinstance(session.get("scenario_config", {}), dict) else {}
    report_cfg = scenario_config.get("report", {}) if isinstance(scenario_config.get("report", {}), dict) else {}
    template_name = resolve_report_template_for_session(session)

    if template_name == REPORT_TEMPLATE_ASSESSMENT_V1:
        return build_assessment_report_prompt(session)

    topic = session.get("topic", "未知项目")
    description = session.get("description")  # 获取主题描述
    interview_log = session.get("interview_log", [])
    dimensions = session.get("dimensions", {})
    # 兼容旧数据：优先使用 reference_materials，否则合并旧字段
    reference_materials = session.get("reference_materials", [])
    if not reference_materials:
        reference_materials = session.get("reference_docs", []) + session.get("research_docs", [])

    # 获取会话的动态维度信息
    report_dim_info = get_dimension_info_for_session(session)

    # 按维度整理问答
    qa_by_dim = {}
    for dim_key in report_dim_info:
        qa_by_dim[dim_key] = [log for log in interview_log if log.get("dimension") == dim_key]

    prompt = f"""你是一个专业的需求分析师，需要基于以下访谈记录生成一份专业的访谈报告。

## 访谈主题
{topic}
"""

    # 如果有主题描述，添加到 prompt 中
    if description:
        prompt += f"""
## 主题描述
{description}
"""

    prompt += """
## 参考资料
"""

    if reference_materials:
        prompt += "以下是用户提供的参考资料，请在生成报告时参考这些内容：\n\n"
        for doc in reference_materials:
            doc_name = doc.get('name', '文档')
            # 根据 source 添加标记
            source_marker = "🔄 " if doc.get("source") == "auto" else ""
            prompt += f"### {source_marker}{doc_name}\n"
            if doc.get("content"):
                content = doc["content"]
                original_length = len(content)

                # 使用智能摘要处理长文档
                if original_length > SMART_SUMMARY_THRESHOLD and ENABLE_SMART_SUMMARY:
                    processed_content, is_summarized = summarize_document(content, doc_name, topic)
                    if is_summarized:
                        prompt += f"{processed_content}\n"
                        prompt += f"*[原文档 {original_length} 字符，已通过AI生成摘要保留关键信息]*\n\n"
                    elif len(processed_content) > MAX_DOC_LENGTH:
                        prompt += f"{processed_content[:MAX_DOC_LENGTH]}\n"
                        prompt += f"*[文档内容过长，已截取前 {MAX_DOC_LENGTH} 字符]*\n\n"
                    else:
                        prompt += f"{processed_content}\n\n"
                elif original_length > MAX_DOC_LENGTH:
                    prompt += f"{content[:MAX_DOC_LENGTH]}\n"
                    prompt += f"*[文档内容过长，已截取前 {MAX_DOC_LENGTH} 字符]*\n\n"
                else:
                    prompt += f"{content}\n\n"
            else:
                prompt += "*[文档内容为空]*\n\n"
    else:
        prompt += "无参考资料\n"

    prompt += "\n## 访谈记录\n"

    for dim_key, dim_info in report_dim_info.items():
        prompt += f"\n### {dim_info['name']}\n"
        qa_list = qa_by_dim.get(dim_key, [])
        if qa_list:
            for qa in qa_list:
                prompt += f"**Q**: {qa['question']}\n"
                prompt += f"**A**: {qa['answer']}\n\n"
        else:
            prompt += "*该维度暂无收集数据*\n"

    if template_name == REPORT_TEMPLATE_CUSTOM_V1:
        normalized_schema, schema_issues = normalize_custom_report_schema(
            report_cfg.get("schema"),
            fallback_sections=report_cfg.get("sections"),
        )
        section_blueprint = summarize_custom_report_schema_for_prompt(normalized_schema)
        schema_issue_notice = ""
        if schema_issues:
            schema_issue_notice = "\n- 原始模板存在异常配置，已自动回退为可解析章节。"

        prompt += f"""
## 报告要求

请根据用户的自定义模板输出完整 Markdown 报告（不包含附录，附录会由系统自动追加）。

### 用户自定义章节蓝图（必须按顺序输出）
{section_blueprint}

### 输出约束
1. 必须按蓝图顺序输出章节，不新增或省略章节标题。
2. component 为 `paragraph` 时输出结构化段落；为 `table` 时输出 Markdown 表格；为 `list` 时输出列表；为 `mermaid` 时输出 ```mermaid 代码块。
3. 关键结论优先引用问答证据（Q数字），不得编造访谈事实。
4. 若某章节信息不足，明确写出“暂无数据”或“待补充”，不得空章节。
5. flowchart 连接线标签必须使用 `A -->|标签| B` 语法。
6. 报告末尾使用署名：*此报告由 Deep Vision 深瞳生成*{schema_issue_notice}

请生成完整的报告："""
    else:
        prompt += """
## 报告要求

请生成一份专业的访谈报告，包含以下章节：

1. **访谈概述** - 基本信息、访谈背景
2. **需求摘要** - 核心需求列表、优先级矩阵
3. **详细需求分析**
   - 客户/用户需求（痛点、期望、场景、角色）
   - 业务流程（关键流程、决策节点）
   - 技术约束（部署、集成、安全）
   - 项目约束（预算、时间、资源）
4. **可视化分析** - 使用 Mermaid 图表展示关键信息
5. **方案建议** - 基于需求的可行建议
6. **风险评估** - 潜在风险和应对策略
7. **下一步行动** - 具体的行动项

**注意**：不需要包含"附录"章节，完整的访谈记录会在报告生成后自动追加。

## Mermaid 图表规范

请在报告中包含以下类型的 Mermaid 图表。**除 quadrantChart 外，所有图表都应使用中文标签**。

### 1. 优先级矩阵（必须，两种形式都要）

#### 1.1 象限图（Mermaid）
使用 quadrantChart 展示需求在重要性-紧急性坐标中的位置：

```mermaid
quadrantChart
    title Priority Matrix
    x-axis Low Urgency --> High Urgency
    y-axis Low Importance --> High Importance
    quadrant-1 Do First
    quadrant-2 Schedule
    quadrant-3 Delegate
    quadrant-4 Eliminate

    Requirement1: [0.8, 0.9]
    Requirement2: [0.3, 0.7]
```

**象限图中文图例说明**（必须在象限图下方添加）：
- **横轴**：紧急程度（左低右高）
- **纵轴**：重要程度（下低上高）
- **Do First（立即执行）**：右上象限，重要且紧急
- **Schedule（计划执行）**：左上象限，重要但不紧急
- **Delegate（可委派）**：右下象限，紧急但不重要
- **Eliminate（低优先级）**：左下象限，不重要不紧急
- 然后列出每个数据点对应的中文需求名称，如：`Requirement1 = 需求名称1`

**quadrantChart 规则（必须遵守）：**
- title、x-axis、y-axis、quadrant 标签**必须用英文**（技术限制）
- 数据点名称用英文或拼音，格式：`Name: [x, y]`，x和y范围0-1
- 不要使用特殊符号
- **必须在图表下方添加中文图例说明**

#### 1.2 优先级清单（Markdown表格）
紧接着图例说明，用中文表格详细说明每个需求的优先级：

| 优先级 | 需求项 | 说明 |
|:---:|:---|:---|
| 🔴 P0 立即执行 | 需求1、需求2 | 重要且紧急，必须优先处理 |
| 🟡 P1 计划执行 | 需求3 | 重要但不紧急，需要规划 |
| 🟢 P2 可委派 | 需求4 | 紧急但不重要，可分配他人 |
| ⚪ P3 低优先级 | 需求5 | 不重要不紧急，可延后 |

**两种形式配合使用**：象限图直观展示位置分布，中文图例解释英文标签，表格详细说明优先级和理由。

### 2. 业务流程图（推荐）
使用 flowchart 展示关键业务流程，**使用中文标签**：

```mermaid
flowchart TD
    A[开始] --> B{判断条件}
    B -->|条件满足| C[处理流程1]
    B -->|条件不满足| D[处理流程2]
    C --> E[结束]
    D --> E
```

**注意**：带标签的连接线格式为 `-->|标签|`，标签写在箭头后面的竖线之间。

**flowchart 规则（必须遵守）：**
- 节点ID使用英文字母（如 A、B、C），节点标签使用中文（如 `A[中文标签]`）
- subgraph 标题使用中文（如 `subgraph 子流程名称`）
- **每个 subgraph 必须有对应的 end 关闭**
- 节点标签中**严禁使用以下特殊字符**：
  - 半角冒号 `:` - 用短横线 `-` 或空格替代
  - 半角引号 `"` - 用全角引号 "" 或书名号 《》 替代
  - 半角括号 `()` - 用全角括号 （） 替代
  - HTML 标签如 `<br>` - 用空格或换行替代
- 菱形判断节点使用 `{中文}` 格式
- **不要在同一个 flowchart 中嵌套过多层级（最多2层 subgraph）**
- **连接线语法规则（严格遵守）**：
  - 无标签连接：`A --> B`
  - 带标签连接：`A -->|标签文字| B`（标签在箭头后面，竖线包围）
  - **禁止使用**：`A --|标签|--> B`（这是错误语法）
  - **禁止使用**：`A -->|标签|--> B`（不能有双箭头）
  - **禁止使用**：`A --- B`（虚线无箭头）

### 3. 需求分类饼图（可选）
使用中文标签：
```mermaid
pie title 需求分布
    "功能需求" : 45
    "性能需求" : 25
    "安全需求" : 20
    "易用性" : 10
```

### 4. 部署架构图（如涉及技术约束）
如果访谈中涉及部署模式、系统架构等技术话题，可使用 flowchart 展示部署架构：

```mermaid
flowchart LR
    subgraph 前端
        A[客户端]
    end
    subgraph 后端
        B[负载均衡]
        C[应用服务器]
    end
    subgraph 存储
        D[(数据库)]
    end
    A -->|请求| B
    B --> C
    C -->|读写数据| D
```

**部署架构图规则：**
- 使用 flowchart LR（从左到右）或 flowchart TD（从上到下）
- 节点ID使用英文字母，标签使用中文
- 保持结构简洁，避免过度复杂的嵌套
- 带标签的连接线使用 `-->|标签文字|` 格式（标签在箭头后面）

### 5. 图表配色与视觉层次（必须）
- 禁止整张图仅使用单一颜色或同色浅深渐变，至少使用 3 种语义色。
- flowchart/架构图必须包含 `classDef` + `class`，并按语义分层：
  - `核心链路`：蓝色系（如 `#2563EB`）
  - `决策节点`：橙色系（如 `#D97706`）
  - `风险/异常`：红色系（如 `#DC2626`）
  - `支撑/辅助`：绿色系（如 `#16A34A`）
- 可直接参考以下写法（示例）：
```mermaid
flowchart TD
    A[核心入口] --> B{决策判断}
    B -->|通过| C[核心流程]
    B -->|阻塞| D[风险处理]
    classDef dvCore fill:#DBEAFE,stroke:#2563EB,color:#1E3A8A,stroke-width:1.4px
    classDef dvDecision fill:#FEF3C7,stroke:#D97706,color:#7C2D12,stroke-width:1.4px
    classDef dvRisk fill:#FEE2E2,stroke:#DC2626,color:#7F1D1D,stroke-width:1.4px
    classDef dvSupport fill:#DCFCE7,stroke:#16A34A,color:#14532D,stroke-width:1.4px
    class A,C dvCore
    class B dvDecision
    class D dvRisk
```

## 重要提醒
- 所有内容必须严格基于访谈记录，不得编造
- 使用 Markdown 格式，Mermaid 代码块使用 ```mermaid 标记
- **优先级矩阵必须同时包含：quadrantChart象限图 + Markdown表格**
- **flowchart、pie 等图表使用中文标签**，quadrantChart 因技术限制必须用英文
- 报告要专业、结构清晰、可操作
- **Mermaid 语法要求严格，请仔细检查每个图表的语法正确性**
- **flowchart 连接线带标签语法必须是 `A -->|标签| B`，禁止使用 `A --|标签|--> B`**
- 报告末尾使用署名：*此报告由 Deep Vision 深瞳生成*

请生成完整的报告："""

    return prompt


def _extract_first_json_object(raw_text: str) -> Optional[str]:
    """从文本中提取第一个完整 JSON 对象。"""
    if not raw_text:
        return None

    json_start = raw_text.find('{')
    if json_start < 0:
        return None

    brace_count = 0
    in_string = False
    escape_next = False

    for i in range(json_start, len(raw_text)):
        char = raw_text[i]

        if escape_next:
            escape_next = False
            continue
        if char == '\\':
            escape_next = True
            continue
        if char == '"' and not escape_next:
            in_string = not in_string
            continue

        if in_string:
            continue

        if char == '{':
            brace_count += 1
        elif char == '}':
            brace_count -= 1
            if brace_count == 0:
                return raw_text[json_start:i + 1]

    return None


def _repair_json_candidate(candidate: str) -> tuple[str, bool]:
    """尝试修复常见 JSON 格式问题，返回 (修复后文本, 是否应用修复)。"""
    text = str(candidate or "").strip()
    if not text:
        return "", False

    repaired = False
    normalized = text.replace("\ufeff", "").strip()
    quote_fixed = (
        normalized
        .replace("“", "\"")
        .replace("”", "\"")
        .replace("‘", "'")
        .replace("’", "'")
    )
    if quote_fixed != normalized:
        normalized = quote_fixed
        repaired = True

    # 移除 markdown 代码块包裹残留
    fenced = re.sub(r"^\s*```(?:json)?\s*", "", normalized, flags=re.IGNORECASE).strip()
    fenced = re.sub(r"\s*```\s*$", "", fenced).strip()
    if fenced != normalized:
        normalized = fenced
        repaired = True

    # 删除常见尾逗号
    trailing_fixed = re.sub(r",\s*([}\]])", r"\1", normalized)
    if trailing_fixed != normalized:
        normalized = trailing_fixed
        repaired = True

    # 修复字符串内部未转义控制字符（常见于模型直接输出多行文本字段）
    control_fixed_parts = []
    in_string = False
    escape_next = False
    control_fixed = False
    for ch in normalized:
        if escape_next:
            control_fixed_parts.append(ch)
            escape_next = False
            continue

        if ch == "\\":
            control_fixed_parts.append(ch)
            escape_next = True
            continue

        if ch == "\"":
            control_fixed_parts.append(ch)
            in_string = not in_string
            continue

        if in_string and ord(ch) < 0x20:
            control_fixed = True
            if ch == "\n":
                control_fixed_parts.append("\\n")
            elif ch == "\r":
                control_fixed_parts.append("\\r")
            elif ch == "\t":
                control_fixed_parts.append("\\t")
            else:
                # 其它控制字符统一替换为空格，避免破坏 JSON 语法
                control_fixed_parts.append(" ")
            continue

        control_fixed_parts.append(ch)

    if control_fixed:
        normalized = "".join(control_fixed_parts)
        repaired = True

    # 兜底修复：截断响应常见于长 JSON，尝试补齐字符串与括号闭合。
    if normalized.startswith("{"):
        stack = []
        in_string = False
        escape_next = False
        for ch in normalized:
            if escape_next:
                escape_next = False
                continue
            if ch == "\\":
                escape_next = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch in "[{":
                stack.append(ch)
            elif ch == "]" and stack and stack[-1] == "[":
                stack.pop()
            elif ch == "}" and stack and stack[-1] == "{":
                stack.pop()

        suffix = []
        if in_string:
            suffix.append('"')
        while stack:
            opener = stack.pop()
            suffix.append('}' if opener == '{' else ']')
        if suffix:
            normalized = normalized + "".join(suffix)
            normalized = re.sub(r",\s*([}\]])", r"\1", normalized)
            repaired = True

    # 若候选中仍混有额外文本，尝试提取首个 JSON 对象
    if not (normalized.startswith("{") and normalized.endswith("}")):
        extracted = _extract_first_json_object(normalized)
        if extracted:
            normalized = extracted.strip()
            repaired = True

    return normalized, repaired


def parse_structured_json_response(
    raw_text: str,
    required_keys: Optional[list] = None,
    require_all_keys: bool = True,
    parse_meta: Optional[dict] = None,
) -> Optional[dict]:
    """解析结构化 JSON 响应（兼容代码块与混杂文本，并支持修复常见格式问题）。"""
    if not raw_text:
        return None

    if isinstance(parse_meta, dict):
        parse_meta.clear()
        parse_meta.update({
            "candidate_count": 0,
            "parse_attempts": 0,
            "repair_applied": False,
            "selected_source": "",
            "missing_keys": [],
            "last_error": "",
        })

    text = raw_text.strip()
    candidates = []
    seen_candidates = set()

    def _append_candidate(value: str, source: str) -> None:
        candidate = str(value or "").strip()
        if not candidate:
            return
        dedup_key = candidate[:4096]
        if dedup_key in seen_candidates:
            return
        seen_candidates.add(dedup_key)
        candidates.append((candidate, source))

    if text.startswith('{'):
        _append_candidate(text, "raw_text")

    if "```json" in text:
        try:
            json_start = text.find("```json") + 7
            json_end = text.find("```", json_start)
            if json_end > json_start:
                _append_candidate(text[json_start:json_end].strip(), "json_fence")
        except Exception:
            pass

    if "```" in text:
        try:
            blocks = re.findall(r"```(?:json)?\s*([\s\S]*?)```", text)
            for block in blocks:
                _append_candidate(block.strip(), "generic_fence")
        except Exception:
            pass

    extracted = _extract_first_json_object(text)
    if extracted:
        _append_candidate(extracted, "extract_first_object")

    if isinstance(parse_meta, dict):
        parse_meta["candidate_count"] = len(candidates)

    for candidate, source in candidates:
        attempts = [(candidate, False, source)]
        repaired_candidate, repaired = _repair_json_candidate(candidate)
        if repaired and repaired_candidate and repaired_candidate != candidate:
            attempts.append((repaired_candidate, True, f"{source}:repaired"))

        for attempt_text, repaired_flag, attempt_source in attempts:
            if isinstance(parse_meta, dict):
                parse_meta["parse_attempts"] = int(parse_meta.get("parse_attempts", 0) or 0) + 1

            try:
                parsed = json.loads(attempt_text)
                if not isinstance(parsed, dict):
                    continue

                if required_keys:
                    if require_all_keys:
                        missing_keys = [key for key in required_keys if key not in parsed]
                        if missing_keys:
                            if isinstance(parse_meta, dict):
                                parse_meta["missing_keys"] = missing_keys
                            continue
                    elif not any(key in parsed for key in required_keys):
                        if isinstance(parse_meta, dict):
                            parse_meta["missing_keys"] = list(required_keys)
                        continue

                if isinstance(parse_meta, dict):
                    parse_meta["repair_applied"] = bool(repaired_flag)
                    parse_meta["selected_source"] = attempt_source
                    parse_meta["missing_keys"] = []
                    parse_meta["last_error"] = ""
                return parsed
            except Exception as parse_error:
                if isinstance(parse_meta, dict):
                    parse_meta["last_error"] = str(parse_error)[:200]
                continue

    return None


def _normalize_evidence_refs(raw_refs) -> list:
    """标准化证据引用，统一为 Q数字 格式。"""
    refs = []
    if isinstance(raw_refs, str):
        refs.extend(re.findall(r"Q\d+", raw_refs.upper()))
    elif isinstance(raw_refs, list):
        for item in raw_refs:
            if isinstance(item, str):
                refs.extend(re.findall(r"Q\d+", item.upper()))

    dedup = sorted(set(refs), key=lambda ref: int(ref[1:]) if ref[1:].isdigit() else 10**9)
    return dedup


_INLINE_EVIDENCE_MARKER_PATTERN = re.compile(
    r"(?:\[\s*证据\s*[：:][^\]\n]*\]|[（(]\s*证据\s*[：:][^）)\n]*[）)])"
)
_PAREN_Q_REF_LIST_PATTERN = re.compile(
    r"[（(]\s*Q\d+(?:\s*[,，、/]\s*Q\d+)*\s*[）)]",
    flags=re.IGNORECASE,
)
_BRACKET_Q_REF_LIST_PATTERN = re.compile(
    r"\[\s*Q\d+(?:\s*[,，、/]\s*Q\d+)*\s*\]",
    flags=re.IGNORECASE,
)


def strip_inline_evidence_markers(text: str) -> str:
    """移除正文中的行内证据编号标记（如 [证据:Q1,Q2]、（证据:Q3）、(Q1,Q2)）。"""
    value = str(text or "")
    if not value:
        return ""

    cleaned = _INLINE_EVIDENCE_MARKER_PATTERN.sub("", value)
    cleaned = _PAREN_Q_REF_LIST_PATTERN.sub("", cleaned)
    cleaned = _BRACKET_Q_REF_LIST_PATTERN.sub("", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+([，。！？；：,.!?;:])", r"\1", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def build_report_evidence_pack(session: dict) -> dict:
    """构建报告 V3 证据包。"""
    interview_log = session.get("interview_log", [])
    dim_info = get_dimension_info_for_session(session)
    mode_config = get_interview_mode_config(session)

    vague_terms = ["看情况", "不确定", "都可以", "不知道", "可能", "暂时不清楚", "以后再说", "差不多"]
    unknown_signals = {"vague_expression", "generic_answer", "option_only"}

    contradiction_patterns = [
        ("need", "需要", "不需要", "需求取向冲突"),
        ("support", "支持", "不支持", "支持立场冲突"),
        ("available", "有", "没有", "资源现状冲突"),
        ("must", "必须", "可选", "约束优先级冲突"),
        ("ready", "已经", "还没", "准备状态冲突"),
    ]

    facts = []
    unknowns = []
    contradictions = []
    blindspots = []
    contradiction_state = {}
    contradiction_keys = set()
    unknown_keys = set()

    for idx, log in enumerate(interview_log, 1):
        q_id = f"Q{idx}"
        dimension_key = log.get("dimension", "")
        dim_name = dim_info.get(dimension_key, {}).get("name", dimension_key or "未分类")
        question = str(log.get("question", "")).strip()
        answer = str(log.get("answer", "")).strip()
        signals = log.get("follow_up_signals") if isinstance(log.get("follow_up_signals"), list) else []
        try:
            quality_score = float(log.get("quality_score", 0) or 0)
        except Exception:
            quality_score = 0.0
        quality_score = max(0.0, min(1.0, quality_score))

        fact = {
            "q_id": q_id,
            "dimension": dimension_key,
            "dimension_name": dim_name,
            "question": question,
            "answer": answer,
            "is_follow_up": bool(log.get("is_follow_up", False)),
            "follow_up_round": int(log.get("follow_up_round", 0) or 0),
            "quality_score": quality_score,
            "quality_signals": log.get("quality_signals", []) if isinstance(log.get("quality_signals"), list) else [],
            "follow_up_signals": signals,
            "hard_triggered": bool(log.get("hard_triggered", False)),
        }
        facts.append(fact)

        unknown_reasons = []
        if any(signal in unknown_signals for signal in signals):
            unknown_reasons.append("命中模糊回答信号")
        if any(term in answer for term in vague_terms):
            unknown_reasons.append("回答存在模糊表述")
        if quality_score > 0 and quality_score < 0.45:
            unknown_reasons.append("回答质量偏低")
        if unknown_reasons:
            unknown_key = f"{q_id}:{'|'.join(sorted(set(unknown_reasons)))}"
            if unknown_key not in unknown_keys:
                unknown_keys.add(unknown_key)
                unknowns.append({
                    "q_id": q_id,
                    "dimension": dim_name,
                    "reason": "；".join(sorted(set(unknown_reasons))),
                    "answer_excerpt": answer[:120],
                })

        for pair_id, positive, negative, description in contradiction_patterns:
            has_positive = positive in answer
            has_negative = negative in answer

            if has_positive and has_negative:
                key = f"self:{pair_id}:{q_id}"
                if key not in contradiction_keys:
                    contradiction_keys.add(key)
                    contradictions.append({
                        "type": "same_answer_conflict",
                        "pair_id": pair_id,
                        "description": description,
                        "dimension": dim_name,
                        "evidence_refs": [q_id],
                        "detail": f"{q_id} 同时出现「{positive}」与「{negative}」",
                    })

            if not (has_positive or has_negative):
                continue

            state = "positive" if has_positive else "negative"
            state_key = (dimension_key, pair_id)
            previous = contradiction_state.get(state_key)
            if previous and previous.get("state") != state:
                key = f"cross:{pair_id}:{previous.get('q_id')}:{q_id}:{dimension_key}"
                if key not in contradiction_keys:
                    contradiction_keys.add(key)
                    contradictions.append({
                        "type": "cross_answer_conflict",
                        "pair_id": pair_id,
                        "description": description,
                        "dimension": dim_name,
                        "evidence_refs": [previous.get("q_id"), q_id],
                        "detail": f"{previous.get('q_id')} 与 {q_id} 对「{positive}/{negative}」存在冲突",
                    })
            contradiction_state[state_key] = {"state": state, "q_id": q_id}

    dimension_coverage = {}
    coverage_values = []
    for dim_key, info in dim_info.items():
        dim_logs = [log for log in interview_log if log.get("dimension") == dim_key]
        formal_count = len([log for log in dim_logs if not log.get("is_follow_up", False)])
        follow_up_count = len([log for log in dim_logs if log.get("is_follow_up", False)])
        dim_state = session.get("dimensions", {}).get(dim_key, {})
        coverage_percent = int(dim_state.get("coverage", 0) or 0)
        coverage_values.append(max(0, min(100, coverage_percent)) / 100.0)
        missing_aspects = get_dimension_missing_aspects(session, dim_key)

        for aspect in missing_aspects:
            blindspots.append({
                "dimension": info.get("name", dim_key),
                "aspect": aspect,
            })

        dimension_coverage[dim_key] = {
            "name": info.get("name", dim_key),
            "coverage_percent": max(0, min(100, coverage_percent)),
            "coverage_ratio": round(max(0, min(100, coverage_percent)) / 100.0, 2),
            "formal_count": formal_count,
            "follow_up_count": follow_up_count,
            "minimum_formal": mode_config.get("formal_questions_per_dim", 3),
            "maximum_formal": mode_config.get("max_formal_questions_per_dim", mode_config.get("formal_questions_per_dim", 3)),
            "missing_aspects": missing_aspects,
            "key_aspects": info.get("key_aspects", []),
        }

    valid_quality_scores = [fact["quality_score"] for fact in facts if fact.get("quality_score", 0) > 0]
    average_quality = sum(valid_quality_scores) / len(valid_quality_scores) if valid_quality_scores else 0.0
    overall_coverage = sum(coverage_values) / len(coverage_values) if coverage_values else 0.0

    total_formal = len([fact for fact in facts if not fact.get("is_follow_up", False)])
    total_follow_up = len([fact for fact in facts if fact.get("is_follow_up", False)])

    report_template = resolve_report_template_for_session(session)
    report_cfg = (session.get("scenario_config", {}) or {}).get("report", {})
    if not isinstance(report_cfg, dict):
        report_cfg = {}
    report_schema = {}
    if report_template == REPORT_TEMPLATE_CUSTOM_V1:
        normalized_schema, _schema_issues = normalize_custom_report_schema(
            report_cfg.get("schema"),
            fallback_sections=report_cfg.get("sections"),
        )
        report_schema = normalized_schema

    return {
        "topic": session.get("topic", "未知主题"),
        "report_type": session.get("scenario_config", {}).get("report", {}).get("type", "standard"),
        "report_template": report_template,
        "report_schema": report_schema,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "facts": facts,
        "contradictions": contradictions,
        "unknowns": unknowns,
        "blindspots": blindspots,
        "dimension_coverage": dimension_coverage,
        "overall_coverage": round(overall_coverage, 3),
        "quality_snapshot": {
            "average_quality_score": round(average_quality, 3),
            "hard_triggered_count": len([fact for fact in facts if fact.get("hard_triggered")]),
            "total_questions": len(facts),
            "total_formal_questions": total_formal,
            "total_follow_up_questions": total_follow_up,
            "follow_up_ratio": round(total_follow_up / len(facts), 3) if facts else 0.0,
        },
    }


def summarize_evidence_pack_for_debug(evidence_pack: dict) -> dict:
    """提炼证据包摘要，用于会话内调试留痕。"""
    if not isinstance(evidence_pack, dict):
        return {}

    facts = evidence_pack.get("facts", [])
    contradictions = evidence_pack.get("contradictions", [])
    unknowns = evidence_pack.get("unknowns", [])
    blindspots = evidence_pack.get("blindspots", [])

    dimension_summary = {}
    raw_dimension_coverage = evidence_pack.get("dimension_coverage", {})
    if isinstance(raw_dimension_coverage, dict):
        for dim_key, dim_meta in raw_dimension_coverage.items():
            if not isinstance(dim_meta, dict):
                continue
            dimension_summary[dim_key] = {
                "name": dim_meta.get("name", dim_key),
                "coverage_percent": int(dim_meta.get("coverage_percent", 0) or 0),
                "formal_count": int(dim_meta.get("formal_count", 0) or 0),
                "follow_up_count": int(dim_meta.get("follow_up_count", 0) or 0),
                "missing_aspects": (dim_meta.get("missing_aspects", []) if isinstance(dim_meta.get("missing_aspects", []), list) else [])[:8],
            }

    quality_snapshot = evidence_pack.get("quality_snapshot", {})
    if not isinstance(quality_snapshot, dict):
        quality_snapshot = {}

    return {
        "overall_coverage": float(evidence_pack.get("overall_coverage", 0) or 0),
        "facts_count": len(facts) if isinstance(facts, list) else 0,
        "contradictions_count": len(contradictions) if isinstance(contradictions, list) else 0,
        "unknowns_count": len(unknowns) if isinstance(unknowns, list) else 0,
        "blindspots_count": len(blindspots) if isinstance(blindspots, list) else 0,
        "quality_snapshot": {
            "average_quality_score": float(quality_snapshot.get("average_quality_score", 0) or 0),
            "hard_triggered_count": int(quality_snapshot.get("hard_triggered_count", 0) or 0),
            "total_questions": int(quality_snapshot.get("total_questions", 0) or 0),
            "total_formal_questions": int(quality_snapshot.get("total_formal_questions", 0) or 0),
            "total_follow_up_questions": int(quality_snapshot.get("total_follow_up_questions", 0) or 0),
            "follow_up_ratio": float(quality_snapshot.get("follow_up_ratio", 0) or 0),
        },
        "dimension_coverage": dimension_summary,
    }


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _fact_sort_key_for_prompt(fact: dict) -> int:
    q_id = str(fact.get("q_id", "")).upper().strip()
    if re.fullmatch(r"Q\d+", q_id):
        try:
            return int(q_id[1:])
        except Exception:
            pass
    return 10 ** 9


def _fact_signature_for_prompt(fact: dict) -> str:
    dimension = str(fact.get("dimension", "")).strip().lower()
    question = re.sub(r"\s+", " ", str(fact.get("question", "")).strip().lower())
    answer = re.sub(r"\s+", " ", str(fact.get("answer", "")).strip().lower())
    question = question[:80]
    answer = answer[:120]
    return f"{dimension}|{question}|{answer}"


def select_slimmed_facts_for_prompt(evidence_pack: dict, facts_limit: int) -> list[dict]:
    """按质量和信息密度选择证据，减少冗余输入。"""
    raw_facts = evidence_pack.get("facts", [])
    if not isinstance(raw_facts, list):
        return []

    normalized_limit = max(1, int(facts_limit or 1))
    normalized_facts = [item for item in raw_facts if isinstance(item, dict)]
    if not normalized_facts:
        return []

    if not REPORT_V3_EVIDENCE_SLIM_ENABLED:
        return normalized_facts[:normalized_limit]

    contradiction_refs = set()
    for item in evidence_pack.get("contradictions", []):
        if not isinstance(item, dict):
            continue
        contradiction_refs.update(_normalize_evidence_refs(item.get("evidence_refs", [])))

    unknown_refs = set()
    for item in evidence_pack.get("unknowns", []):
        if not isinstance(item, dict):
            continue
        q_id = str(item.get("q_id", "")).upper().strip()
        if re.fullmatch(r"Q\d+", q_id):
            unknown_refs.add(q_id)

    score_items = []
    for idx, fact in enumerate(normalized_facts):
        quality = max(0.0, min(1.0, _safe_float(fact.get("quality_score", 0.0), 0.0)))
        q_id = str(fact.get("q_id", "")).upper().strip()
        is_contradiction_ref = q_id in contradiction_refs
        is_unknown_ref = q_id in unknown_refs
        is_hard_triggered = bool(fact.get("hard_triggered", False))
        is_follow_up = bool(fact.get("is_follow_up", False))

        score = quality * 100.0
        if is_hard_triggered:
            score += 24.0
        if is_contradiction_ref:
            score += 22.0
        if is_unknown_ref:
            score += 12.0
        if is_follow_up:
            score += 8.0

        score_items.append({
            "idx": idx,
            "fact": fact,
            "q_id": q_id,
            "score": score,
            "quality": quality,
            "is_mandatory": is_contradiction_ref or (REPORT_V3_EVIDENCE_KEEP_HARD_TRIGGERED and is_hard_triggered),
            "signature": _fact_signature_for_prompt(fact),
            "dimension": str(fact.get("dimension", "") or "__unknown__").strip().lower() or "__unknown__",
        })

    score_items.sort(key=lambda item: (-item["score"], item["idx"]))

    selected = []
    selected_signatures = set()
    dimension_counter = {}
    dim_quota = max(1, int(REPORT_V3_EVIDENCE_DIM_QUOTA))

    def try_take(item: dict, bypass_quota: bool = False, bypass_quality: bool = False) -> bool:
        if len(selected) >= normalized_limit:
            return False
        if REPORT_V3_EVIDENCE_DEDUP_ENABLED and item["signature"] in selected_signatures:
            return False
        if not bypass_quality and not item.get("is_mandatory", False):
            if float(item.get("quality", 0.0) or 0.0) < REPORT_V3_EVIDENCE_MIN_QUALITY:
                return False

        dim_key = item.get("dimension", "__unknown__")
        if not bypass_quota:
            if int(dimension_counter.get(dim_key, 0) or 0) >= dim_quota:
                return False

        selected.append(item)
        selected_signatures.add(item["signature"])
        dimension_counter[dim_key] = int(dimension_counter.get(dim_key, 0) or 0) + 1
        return True

    # 第一轮：保留强信号事实（冲突/硬触发）
    for item in score_items:
        if not item.get("is_mandatory", False):
            continue
        if len(selected) >= normalized_limit:
            break
        try_take(item, bypass_quota=True, bypass_quality=True)

    # 第二轮：按分数补齐，兼顾维度配额与最小质量。
    for item in score_items:
        if len(selected) >= normalized_limit:
            break
        try_take(item, bypass_quota=False, bypass_quality=False)

    # 第三轮：若仍不足，放宽配额与质量门槛兜底补齐。
    if len(selected) < normalized_limit:
        for item in score_items:
            if len(selected) >= normalized_limit:
                break
            try_take(item, bypass_quota=True, bypass_quality=True)

    selected_facts = [item["fact"] for item in selected]
    selected_facts.sort(key=_fact_sort_key_for_prompt)
    return selected_facts


def build_report_draft_prompt_assessment_v1(
    session: dict,
    evidence_pack: dict,
    facts_limit: int = 48,
    contradiction_limit: int = 12,
    unknown_limit: int = 12,
    blindspot_limit: int = 12,
) -> str:
    """assessment_v1 草案提示词：强调候选人能力评估与录用建议。"""
    topic = session.get("topic", "候选人评估")
    description = session.get("description", "")
    selected_facts = select_slimmed_facts_for_prompt(evidence_pack, facts_limit=max(8, int(facts_limit or 8)))
    facts_lines = []
    for fact in selected_facts:
        question_text = (fact.get("question", "") or "").replace("\n", " ").strip()[:90]
        answer_text = (fact.get("answer", "") or "").replace("\n", " ").strip()[:150]
        facts_lines.append(
            f"- {fact.get('q_id')} [{fact.get('dimension_name', '未分类')}] "
            f"Q: {question_text} | A: {answer_text} | quality={fact.get('quality_score', 0):.2f}"
        )
    facts_text = "\n".join(facts_lines) if facts_lines else "- 无有效问答证据"

    dimension_lines = []
    for dim_key, dim_meta in (evidence_pack.get("dimension_coverage", {}) or {}).items():
        missing = "、".join(dim_meta.get("missing_aspects", [])[:4]) if dim_meta.get("missing_aspects") else "无"
        dimension_lines.append(
            f"- {dim_meta.get('name', dim_key)}: 覆盖{dim_meta.get('coverage_percent', 0)}%，"
            f"正式题 {dim_meta.get('formal_count', 0)}，追问 {dim_meta.get('follow_up_count', 0)}，未覆盖方面：{missing}"
        )
    dimension_text = "\n".join(dimension_lines) if dimension_lines else "- 暂无维度覆盖数据"

    contradictions = evidence_pack.get("contradictions", [])
    contradiction_lines = [
        f"- {item.get('detail')}（证据: {', '.join(item.get('evidence_refs', []))}）"
        for item in contradictions[:max(5, int(contradiction_limit or 5))]
    ]
    contradiction_text = "\n".join(contradiction_lines) if contradiction_lines else "- 未发现明显冲突"

    unknowns = evidence_pack.get("unknowns", [])
    unknown_lines = [
        f"- {item.get('q_id')} [{item.get('dimension')}] {item.get('reason')}"
        for item in unknowns[:max(5, int(unknown_limit or 5))]
    ]
    unknown_text = "\n".join(unknown_lines) if unknown_lines else "- 未发现明显模糊回答"

    blindspots = evidence_pack.get("blindspots", [])
    blindspot_lines = [
        f"- {item.get('dimension')}: {item.get('aspect')}"
        for item in blindspots[:max(5, int(blindspot_limit or 5))]
    ]
    blindspot_text = "\n".join(blindspot_lines) if blindspot_lines else "- 暂无盲区"

    schema_example = {
        "overview": "候选人概览（1-2段）",
        "needs": [
            {
                "name": "能力项结论（如问题拆解能力）",
                "priority": "P0",
                "description": "该能力项的表现结论与证据摘要",
                "evidence_refs": ["Q1", "Q3"]
            }
        ],
        "analysis": {
            "customer_needs": "能力优势分析",
            "business_flow": "思维结构与推理链分析",
            "tech_constraints": "经验边界与风险意识分析",
            "project_constraints": "录用约束、岗位匹配与团队协作分析"
        },
        "visualizations": {
            "priority_quadrant_mermaid": "可选，能力优先矩阵",
            "business_flow_mermaid": "可选，思维流程图",
            "demand_pie_mermaid": "可选，能力分布图",
            "architecture_mermaid": "可选，胜任力结构图"
        },
        "solutions": [
            {
                "title": "录用/培养建议",
                "description": "建议说明",
                "owner": "用人经理",
                "timeline": "试用期1个月/3个月",
                "metric": "阶段性能力达成指标",
                "evidence_refs": ["Q2", "Q8"]
            }
        ],
        "risks": [
            {
                "risk": "录用风险项",
                "impact": "风险影响",
                "mitigation": "缓解措施",
                "evidence_refs": ["Q6"]
            }
        ],
        "actions": [
            {
                "action": "后续评估/培养行动",
                "owner": "面试官/导师",
                "timeline": "短期+中期里程碑",
                "metric": "可量化验收标准",
                "evidence_refs": ["Q4"]
            }
        ],
        "open_questions": [
            {
                "question": "需补充验证的问题",
                "reason": "为何未决",
                "impact": "影响范围",
                "suggested_follow_up": "建议补充追问",
                "evidence_refs": ["Q7"]
            }
        ],
        "evidence_index": [
            {
                "claim": "关键评估结论",
                "confidence": "high",
                "evidence_refs": ["Q1", "Q5"]
            }
        ]
    }

    return f"""你是一名资深面试评估顾问。请基于证据包输出结构化草案 JSON，不要输出 JSON 之外任何文字。

## 任务类型
- 报告类型：面试评估
- 主题：{topic}
{f"- 背景：{description}" if description else ""}

## 维度覆盖快照
{dimension_text}

## 关键证据（问答编号）
{facts_text}

## 冲突信号
{contradiction_text}

## 模糊与不确定信号
{unknown_text}

## 盲区清单
{blindspot_text}

## 输出要求
1. 顶层字段必须严格为：overview/needs/analysis/visualizations/solutions/risks/actions/open_questions/evidence_index。
2. 关键结论必须绑定 evidence_refs（Q数字）。
3. solutions/actions 必须包含 owner、timeline、metric。
4. actions 至少 2 条，且覆盖短期与中期里程碑。
5. 内容风格偏“评估结论+培养建议”，避免需求文案口吻。
6. 禁止输出工具执行话术、markdown代码块与额外前后缀文本。

## JSON 模板（字段必须完整）
{json.dumps(schema_example, ensure_ascii=False, indent=2)}
"""


def build_report_draft_prompt_custom_v1(
    session: dict,
    evidence_pack: dict,
    facts_limit: int = 56,
    contradiction_limit: int = 16,
    unknown_limit: int = 16,
    blindspot_limit: int = 16,
) -> str:
    """custom_v1 草案提示词：按用户章节蓝图约束表达焦点。"""
    report_cfg = (session.get("scenario_config", {}) or {}).get("report", {})
    schema_raw = report_cfg.get("schema") if isinstance(report_cfg, dict) else {}
    normalized_schema, _issues = normalize_custom_report_schema(schema_raw, fallback_sections=report_cfg.get("sections") if isinstance(report_cfg, dict) else None)
    section_blueprint = summarize_custom_report_schema_for_prompt(normalized_schema)

    topic = session.get("topic", "未知主题")
    description = session.get("description", "")
    selected_facts = select_slimmed_facts_for_prompt(evidence_pack, facts_limit=max(10, int(facts_limit or 10)))
    facts_lines = []
    for fact in selected_facts:
        question_text = (fact.get("question", "") or "").replace("\n", " ").strip()[:90]
        answer_text = (fact.get("answer", "") or "").replace("\n", " ").strip()[:150]
        facts_lines.append(
            f"- {fact.get('q_id')} [{fact.get('dimension_name', '未分类')}] "
            f"Q: {question_text} | A: {answer_text} | quality={fact.get('quality_score', 0):.2f}"
        )
    facts_text = "\n".join(facts_lines) if facts_lines else "- 无有效问答证据"

    contradictions = evidence_pack.get("contradictions", [])
    contradiction_lines = [
        f"- {item.get('detail')}（证据: {', '.join(item.get('evidence_refs', []))}）"
        for item in contradictions[:max(5, int(contradiction_limit or 5))]
    ]
    contradiction_text = "\n".join(contradiction_lines) if contradiction_lines else "- 未发现明显冲突"

    unknowns = evidence_pack.get("unknowns", [])
    unknown_lines = [
        f"- {item.get('q_id')} [{item.get('dimension')}] {item.get('reason')}"
        for item in unknowns[:max(5, int(unknown_limit or 5))]
    ]
    unknown_text = "\n".join(unknown_lines) if unknown_lines else "- 未发现明显模糊回答"

    blindspots = evidence_pack.get("blindspots", [])
    blindspot_lines = [
        f"- {item.get('dimension')}: {item.get('aspect')}"
        for item in blindspots[:max(5, int(blindspot_limit or 5))]
    ]
    blindspot_text = "\n".join(blindspot_lines) if blindspot_lines else "- 暂无盲区"

    schema_example = {
        "overview": "执行摘要",
        "needs": [],
        "analysis": {
            "customer_needs": "",
            "business_flow": "",
            "tech_constraints": "",
            "project_constraints": ""
        },
        "visualizations": {
            "priority_quadrant_mermaid": "",
            "business_flow_mermaid": "",
            "demand_pie_mermaid": "",
            "architecture_mermaid": ""
        },
        "solutions": [],
        "risks": [],
        "actions": [],
        "open_questions": [],
        "evidence_index": []
    }

    return f"""你是一名企业咨询顾问，需要基于证据包输出结构化草案 JSON。

## 任务类型
- 报告类型：用户自定义模板
- 主题：{topic}
{f"- 背景：{description}" if description else ""}

## 用户定义章节蓝图（渲染时会按此输出）
{section_blueprint}

## 关键证据（问答编号）
{facts_text}

## 冲突信号
{contradiction_text}

## 模糊与不确定信号
{unknown_text}

## 盲区清单
{blindspot_text}

## 输出要求
1. 只输出合法 JSON，禁止任何前后缀文本。
2. 顶层字段必须严格为：overview/needs/analysis/visualizations/solutions/risks/actions/open_questions/evidence_index。
3. 关键结论必须绑定 evidence_refs（Q数字）。
4. solutions/actions 必须包含 owner、timeline、metric。
5. open_questions 要优先覆盖盲区与冲突。
6. 文案需简洁可交付，避免口语化、避免空泛叙述。

## JSON 模板（字段必须完整）
{json.dumps(schema_example, ensure_ascii=False, indent=2)}
"""


def build_report_draft_prompt_v3(
    session: dict,
    evidence_pack: dict,
    facts_limit: int = 60,
    contradiction_limit: int = 20,
    unknown_limit: int = 20,
    blindspot_limit: int = 20,
) -> str:
    """构建 V3 报告草案生成 Prompt（结构化 JSON）。"""
    template_name = resolve_report_template_for_session(session, evidence_pack=evidence_pack)
    if template_name == REPORT_TEMPLATE_ASSESSMENT_V1:
        return build_report_draft_prompt_assessment_v1(
            session,
            evidence_pack,
            facts_limit=facts_limit,
            contradiction_limit=contradiction_limit,
            unknown_limit=unknown_limit,
            blindspot_limit=blindspot_limit,
        )
    if template_name == REPORT_TEMPLATE_CUSTOM_V1:
        return build_report_draft_prompt_custom_v1(
            session,
            evidence_pack,
            facts_limit=facts_limit,
            contradiction_limit=contradiction_limit,
            unknown_limit=unknown_limit,
            blindspot_limit=blindspot_limit,
        )

    topic = session.get("topic", "未知主题")
    description = session.get("description", "")
    report_type = evidence_pack.get("report_type", "standard")
    report_type_label = "面试评估" if report_type == "assessment" else "需求访谈"

    dimension_lines = []
    for dim_key, dim_meta in evidence_pack.get("dimension_coverage", {}).items():
        missing = "、".join(dim_meta.get("missing_aspects", [])[:4]) if dim_meta.get("missing_aspects") else "无"
        dimension_lines.append(
            f"- {dim_meta.get('name', dim_key)}: 覆盖{dim_meta.get('coverage_percent', 0)}%，"
            f"正式题 {dim_meta.get('formal_count', 0)}，追问 {dim_meta.get('follow_up_count', 0)}，未覆盖方面：{missing}"
        )
    dimension_text = "\n".join(dimension_lines) if dimension_lines else "- 暂无维度覆盖数据"

    facts_limit = max(10, int(facts_limit or 10))
    contradiction_limit = max(5, int(contradiction_limit or 5))
    unknown_limit = max(5, int(unknown_limit or 5))
    blindspot_limit = max(5, int(blindspot_limit or 5))

    selected_facts = select_slimmed_facts_for_prompt(evidence_pack, facts_limit=facts_limit)
    facts_lines = []
    for fact in selected_facts:
        question_text = (fact.get("question", "") or "").replace("\n", " ").strip()[:90]
        answer_text = (fact.get("answer", "") or "").replace("\n", " ").strip()[:150]
        facts_lines.append(
            f"- {fact.get('q_id')} [{fact.get('dimension_name', '未分类')}] "
            f"Q: {question_text} | A: {answer_text} | quality={fact.get('quality_score', 0):.2f}"
        )
    facts_text = "\n".join(facts_lines) if facts_lines else "- 无有效问答证据"
    facts_source_count = len(evidence_pack.get("facts", [])) if isinstance(evidence_pack.get("facts", []), list) else 0

    contradictions = evidence_pack.get("contradictions", [])
    contradiction_lines = [
        f"- {item.get('detail')}（证据: {', '.join(item.get('evidence_refs', []))}）"
        for item in contradictions[:contradiction_limit]
    ]
    contradiction_text = "\n".join(contradiction_lines) if contradiction_lines else "- 未发现明显冲突"

    unknowns = evidence_pack.get("unknowns", [])
    unknown_lines = [
        f"- {item.get('q_id')} [{item.get('dimension')}] {item.get('reason')}"
        for item in unknowns[:unknown_limit]
    ]
    unknown_text = "\n".join(unknown_lines) if unknown_lines else "- 未发现明显模糊回答"

    blindspots = evidence_pack.get("blindspots", [])
    blindspot_lines = [
        f"- {item.get('dimension')}: {item.get('aspect')}"
        for item in blindspots[:blindspot_limit]
    ]
    blindspot_text = "\n".join(blindspot_lines) if blindspot_lines else "- 暂无盲区"

    schema_example = {
        "overview": "访谈概述（2-4段）",
        "needs": [
            {
                "name": "核心需求名称",
                "priority": "P0",
                "description": "需求描述",
                "evidence_refs": ["Q1", "Q3"]
            }
        ],
        "analysis": {
            "customer_needs": "客户/用户需求分析",
            "business_flow": "业务流程分析",
            "tech_constraints": "技术约束分析",
            "project_constraints": "项目约束分析"
        },
        "visualizations": {
            "priority_quadrant_mermaid": "可选，quadrantChart ...",
            "business_flow_mermaid": "可选，flowchart TD ...",
            "demand_pie_mermaid": "可选，pie title ...",
            "architecture_mermaid": "可选，flowchart LR ..."
        },
        "solutions": [
            {
                "title": "方案建议标题",
                "description": "方案说明",
                "owner": "负责角色",
                "timeline": "时间计划",
                "metric": "验收指标",
                "evidence_refs": ["Q2", "Q8"]
            }
        ],
        "risks": [
            {
                "risk": "风险项",
                "impact": "影响",
                "mitigation": "缓解措施",
                "evidence_refs": ["Q6"]
            }
        ],
        "actions": [
            {
                "action": "下一步行动",
                "owner": "负责人角色",
                "timeline": "预计时间",
                "metric": "完成标准",
                "evidence_refs": ["Q4"]
            }
        ],
        "open_questions": [
            {
                "question": "未决问题",
                "reason": "为何未决",
                "impact": "影响范围",
                "suggested_follow_up": "建议补充追问",
                "evidence_refs": ["Q7"]
            }
        ],
        "evidence_index": [
            {
                "claim": "关键结论",
                "confidence": "high",
                "evidence_refs": ["Q1", "Q5"]
            }
        ]
    }

    return f"""你是一名资深分析顾问。请基于给定证据包生成一份结构化报告草案 JSON，禁止输出任何 JSON 之外的文字。

## 任务类型
- 报告类型：{report_type_label}
- 主题：{topic}
{f"- 主题描述：{description}" if description else ""}

## 维度覆盖快照
{dimension_text}

## 关键证据（按问答编号）
（原始 {facts_source_count} 条，已筛选 {len(selected_facts)} 条高价值证据）
{facts_text}

## 冲突信号
{contradiction_text}

## 模糊与不确定信号
{unknown_text}

## 盲区清单（必须优先补齐）
{blindspot_text}

## 输出硬性约束
1. 输出必须是合法 JSON 对象，首字符是 {{，末字符是 }}。
2. 所有关键结论都要携带 evidence_refs（格式必须是 Q数字）。
3. solutions/actions 每一项必须包含 owner、timeline、metric。
4. 若存在冲突信号，必须在 risks 或 open_questions 中显式处理。
5. 若存在盲区，必须在 open_questions 中体现对应补问。
6. visualizations 字段可选；即使填写也仅作为补充参考，最终图表由后端按结构化数据渲染。
7. 不得编造证据编号，不得引用不存在的 Q 编号。
8. 禁止输出任何工具流程话术：如“请确认是否继续”“需要先征得同意”“我会创建文件”等。
9. 禁止输出 markdown 代码块、注释、额外解释或前后缀文本。
10. 顶层字段必须仅包含：overview/needs/analysis/visualizations/solutions/risks/actions/open_questions/evidence_index。
11. 草案采用“咨询交付风格”：描述简洁、结论先行、避免口语与空泛表述。
12. actions 至少 3 条（证据不足时至少 2 条），且 timeline 需覆盖短期与中期里程碑。
13. needs/solutions/risks/actions 要满足表格化呈现：每项字段完整，单项表达尽量控制在 70 字内。

## 风格锁定模板（审稿会按此门禁）
- 2.需求摘要：needs 必须可直接渲染为表格（优先级/需求项/描述/证据）。
- 5.方案建议：solutions 必须可直接渲染为表格（标题/说明/owner/timeline/metric/证据）。
- 6.风险评估：risks 必须可直接渲染为表格（风险/影响/缓解/证据）。
- 7.下一步行动：actions 必须可直接渲染为表格（行动/owner/timeline/metric/证据），并体现里程碑层次。
- open_questions 必须对齐盲区或冲突，避免泛化问题。

## JSON 模板（字段必须完整）
{json.dumps(schema_example, ensure_ascii=False, indent=2)}
"""


def resolve_custom_report_source_value_v3(draft: dict, source: str) -> object:
    source_key = str(source or "").strip()
    if not source_key:
        return ""

    if source_key == "overview":
        return draft.get("overview", "")
    if source_key in {"needs", "solutions", "risks", "actions", "open_questions", "evidence_index"}:
        value = draft.get(source_key, [])
        return value if isinstance(value, list) else []
    if source_key == "priority_list":
        value = draft.get("needs", [])
        return value if isinstance(value, list) else []
    if source_key == "priority_matrix":
        visuals = draft.get("visualizations", {})
        if isinstance(visuals, dict):
            return str(visuals.get("priority_quadrant_mermaid", "") or "").strip()
        return ""

    if source_key.startswith("analysis."):
        _, _, field = source_key.partition(".")
        analysis = draft.get("analysis", {})
        if isinstance(analysis, dict):
            return analysis.get(field, "")
        return ""

    if source_key.startswith("visualizations."):
        _, _, field = source_key.partition(".")
        visuals = draft.get("visualizations", {})
        if isinstance(visuals, dict):
            return visuals.get(field, "")
        return ""

    return ""


def is_custom_report_source_empty_v3(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not str(value or "").strip()
    if isinstance(value, list):
        return len(value) == 0
    if isinstance(value, dict):
        return len(value) == 0
    return False


def validate_report_draft_v3(draft: dict, evidence_pack: dict) -> tuple[dict, list]:
    """校验并标准化 V3 报告草案。"""
    issues = []
    template_name = normalize_report_template_name(
        (evidence_pack or {}).get("report_template", ""),
        report_type=(evidence_pack or {}).get("report_type", "standard"),
    )

    def sanitize_text(value) -> str:
        return strip_inline_evidence_markers(str(value or "").strip())

    def add_issue(issue_type: str, severity: str, message: str, target: str):
        issues.append({
            "type": issue_type,
            "severity": severity,
            "message": message,
            "target": target,
        })

    if not isinstance(draft, dict):
        add_issue("structure_error", "high", "草案不是 JSON 对象", "root")
        return {}, issues

    normalized = {
        "overview": sanitize_text(draft.get("overview", "")),
        "needs": [],
        "analysis": {
            "customer_needs": "",
            "business_flow": "",
            "tech_constraints": "",
            "project_constraints": "",
        },
        "visualizations": {
            "priority_quadrant_mermaid": "",
            "business_flow_mermaid": "",
            "demand_pie_mermaid": "",
            "architecture_mermaid": "",
        },
        "solutions": [],
        "risks": [],
        "actions": [],
        "open_questions": [],
        "evidence_index": [],
    }

    valid_q_refs = {
        str(item.get("q_id", "")).upper().strip()
        for item in evidence_pack.get("facts", [])
        if isinstance(item, dict) and re.fullmatch(r"Q\d+", str(item.get("q_id", "")).upper().strip())
    }

    def normalize_evidence_refs_for_target(raw_refs, target: str) -> list:
        refs = _normalize_evidence_refs(raw_refs)
        if not refs:
            return []
        if not valid_q_refs:
            add_issue("invalid_evidence_ref", "high", "证据包缺少可用问答编号，无法验证证据引用", target)
            return []

        invalid_refs = [ref for ref in refs if ref not in valid_q_refs]
        if invalid_refs:
            add_issue(
                "invalid_evidence_ref",
                "high",
                f"包含无效证据引用：{', '.join(invalid_refs)}",
                target
            )

        return [ref for ref in refs if ref in valid_q_refs]

    analysis = draft.get("analysis", {})
    if isinstance(analysis, dict):
        for key in normalized["analysis"]:
            normalized["analysis"][key] = sanitize_text(analysis.get(key, ""))

    visualizations = draft.get("visualizations", {})
    if isinstance(visualizations, dict):
        for key in normalized["visualizations"]:
            normalized["visualizations"][key] = str(visualizations.get(key, "")).strip()

    if not normalized["overview"]:
        add_issue("structure_error", "high", "overview 不能为空", "overview")

    needs = draft.get("needs", [])
    if isinstance(needs, list):
        for idx, item in enumerate(needs):
            if not isinstance(item, dict):
                add_issue("structure_error", "medium", "needs 项必须是对象", f"needs[{idx}]")
                continue
            refs = normalize_evidence_refs_for_target(item.get("evidence_refs", []), f"needs[{idx}].evidence_refs")
            normalized_item = {
                "name": sanitize_text(item.get("name", "")),
                "priority": str(item.get("priority", "P1")).strip().upper() or "P1",
                "description": sanitize_text(item.get("description", "")),
                "evidence_refs": refs,
                "evidence_binding_mode": str(item.get("evidence_binding_mode", "") or "").strip().lower(),
            }
            if not normalized_item["name"]:
                add_issue("structure_error", "medium", "needs.name 不能为空", f"needs[{idx}].name")
            if not refs:
                add_issue("no_evidence", "high", "核心需求缺少证据引用", f"needs[{idx}]")
            normalized["needs"].append(normalized_item)

    for field, id_field in [("solutions", "title"), ("risks", "risk"), ("actions", "action"), ("open_questions", "question"), ("evidence_index", "claim")]:
        values = draft.get(field, [])
        if not isinstance(values, list):
            add_issue("structure_error", "medium", f"{field} 必须是数组", field)
            continue
        for idx, item in enumerate(values):
            if not isinstance(item, dict):
                add_issue("structure_error", "medium", f"{field} 项必须是对象", f"{field}[{idx}]")
                continue
            refs = normalize_evidence_refs_for_target(item.get("evidence_refs", []), f"{field}[{idx}].evidence_refs")
            normalized_item = dict(item)
            normalized_item[id_field] = sanitize_text(item.get(id_field, ""))
            normalized_item["evidence_refs"] = refs
            normalized_item["evidence_binding_mode"] = str(item.get("evidence_binding_mode", "") or "").strip().lower()

            if field in {"solutions", "actions"}:
                normalized_item["owner"] = sanitize_text(item.get("owner", ""))
                normalized_item["timeline"] = sanitize_text(item.get("timeline", ""))
                normalized_item["metric"] = sanitize_text(item.get("metric", ""))
                if not (normalized_item["owner"] and normalized_item["timeline"] and normalized_item["metric"]):
                    add_issue("not_actionable", "medium", f"{field} 缺少 owner/timeline/metric", f"{field}[{idx}]")

            if field == "risks":
                normalized_item["impact"] = sanitize_text(item.get("impact", ""))
                normalized_item["mitigation"] = sanitize_text(item.get("mitigation", ""))

            if field == "open_questions":
                normalized_item["reason"] = sanitize_text(item.get("reason", ""))
                normalized_item["impact"] = sanitize_text(item.get("impact", ""))
                normalized_item["suggested_follow_up"] = sanitize_text(item.get("suggested_follow_up", ""))

            if field == "evidence_index":
                confidence = str(item.get("confidence", "medium")).strip().lower()
                if confidence not in {"high", "medium", "low"}:
                    confidence = "medium"
                normalized_item["confidence"] = confidence

            if not normalized_item.get(id_field):
                add_issue("structure_error", "medium", f"{field}.{id_field} 不能为空", f"{field}[{idx}].{id_field}")
            if field == "open_questions" and not refs:
                if normalized_item.get("evidence_binding_mode") != "weak_inferred":
                    normalized_item["evidence_binding_mode"] = "pending_follow_up"
            elif not refs:
                add_issue("no_evidence", "high", f"{field} 缺少证据引用", f"{field}[{idx}]")

            normalized[field].append(normalized_item)

    contradictions = evidence_pack.get("contradictions", [])
    contradiction_ref_pool = set()
    for field in ["risks", "open_questions", "actions", "solutions", "evidence_index"]:
        values = normalized.get(field, [])
        if not isinstance(values, list):
            continue
        for item in values:
            if not isinstance(item, dict):
                continue
            contradiction_ref_pool.update(_normalize_evidence_refs(item.get("evidence_refs", [])))

    unresolved_conflicts = 0
    for item in contradictions:
        refs = _normalize_evidence_refs(item.get("evidence_refs", []))
        if refs and not any(ref in contradiction_ref_pool for ref in refs):
            unresolved_conflicts += 1
    if unresolved_conflicts > 0:
        add_issue(
            "unresolved_contradiction",
            "high",
            f"存在 {unresolved_conflicts} 条冲突证据未在草案中处理",
            "risks/open_questions"
        )

    blindspot_text_segments = []
    blindspot_text_segments.extend(str(value or "") for value in normalized.get("analysis", {}).values())
    for field in ["open_questions", "actions", "solutions", "risks"]:
        values = normalized.get(field, [])
        if not isinstance(values, list):
            continue
        for item in values:
            if not isinstance(item, dict):
                continue
            blindspot_text_segments.extend([
                str(item.get("question", "") or ""),
                str(item.get("reason", "") or ""),
                str(item.get("impact", "") or ""),
                str(item.get("suggested_follow_up", "") or ""),
                str(item.get("action", "") or ""),
                str(item.get("description", "") or ""),
                str(item.get("risk", "") or ""),
                str(item.get("mitigation", "") or ""),
            ])
    blindspot_corpus = " ".join(blindspot_text_segments).lower()

    blindspots = evidence_pack.get("blindspots", [])
    unresolved_blindspots = []
    for item in blindspots:
        aspect = str(item.get("aspect", "")).strip()
        if aspect and aspect.lower() not in blindspot_corpus:
            unresolved_blindspots.append(aspect)
    if unresolved_blindspots:
        sample = "、".join(unresolved_blindspots[:5])
        add_issue(
            "blindspot",
            "medium",
            f"仍有未覆盖盲区未进入草案：{sample}",
            "open_questions"
        )

    if template_name == REPORT_TEMPLATE_CUSTOM_V1:
        report_schema = (evidence_pack or {}).get("report_schema", {})
        normalized_schema, schema_issues = normalize_custom_report_schema(report_schema)
        for item in schema_issues:
            add_issue("custom_schema_error", "high", str(item), "report_schema")
        for section in normalized_schema.get("sections", []):
            if not isinstance(section, dict):
                continue
            if not bool(section.get("required", False)):
                continue
            source = str(section.get("source", "")).strip()
            section_id = str(section.get("section_id", "") or source).strip() or "unknown"
            value = resolve_custom_report_source_value_v3(normalized, source)
            if is_custom_report_source_empty_v3(value):
                add_issue(
                    "custom_required_section_empty",
                    "high",
                    f"自定义模板必填章节缺少内容：{section.get('title', section_id)}",
                    f"custom_sections[{section_id}]",
                )

    return normalized, issues


def build_report_review_prompt_v3(session: dict, evidence_pack: dict, draft: dict, issues: list) -> str:
    """构建 V3 审稿与修复 Prompt。"""
    topic = session.get("topic", "未知主题")
    contradiction_text = "\n".join(
        [f"- {item.get('detail')}（证据: {', '.join(item.get('evidence_refs', []))}）" for item in evidence_pack.get("contradictions", [])[:20]]
    ) or "- 无"
    blindspot_text = "\n".join(
        [f"- {item.get('dimension')}: {item.get('aspect')}" for item in evidence_pack.get("blindspots", [])[:20]]
    ) or "- 无"

    issue_text = "\n".join(
        [f"- [{item.get('severity', 'medium')}] {item.get('type')}: {item.get('message')} @ {item.get('target', 'unknown')}" for item in issues[:30]]
    ) or "- 无已知问题"

    response_schema = {
        "passed": True,
        "issues": [
            {
                "type": "no_evidence",
                "severity": "high",
                "message": "问题描述",
                "target": "字段路径"
            }
        ],
        "revised_draft": {
            "overview": "修订后的 overview",
            "needs": [],
            "analysis": {},
            "visualizations": {},
            "solutions": [],
            "risks": [],
            "actions": [],
            "open_questions": [],
            "evidence_index": []
        }
    }

    return f"""你是报告质量审稿专家。请对草案执行一致性审稿并直接修复，输出 JSON。

## 访谈主题
{topic}

## 重点核查规则
1. no_evidence：关键结论或行动缺少 evidence_refs。
2. unresolved_contradiction：冲突证据没有被解释或处理。
3. not_actionable：行动建议缺少 owner/timeline/metric。
4. blindspot：盲区至少进入 open_questions；仅在证据充分时再进入 actions。
5. style_template_violation：章节模板偏离（数量不足、字段缺失、难以表格化）。
6. quality_gate_expression：表达结构不完整（概述、分析、建议、行动衔接弱）。
7. quality_gate_table：needs/solutions/risks/actions 的表格化可读性不足。
8. quality_gate_milestone：行动缺少短中期里程碑覆盖。

## 冲突证据
{contradiction_text}

## 盲区证据
{blindspot_text}

## 当前已知问题
{issue_text}

## 待审稿草案 JSON
{json.dumps(draft, ensure_ascii=False)}

## 输出要求
- 仅输出合法 JSON，禁止附加解释文字。
- 必须包含 passed、issues、revised_draft 三个字段。
- revised_draft 允许采用“增量修订”模式：
  - 未修改的顶层字段可以省略。
  - 若修改 needs/solutions/risks/actions/open_questions/evidence_index 任一数组字段，需返回该字段的完整数组。
  - analysis / visualizations 只返回被修改的子字段即可。
- 只有在多数顶层字段都被改动时，才返回完整 revised_draft。
- 若仍有问题，issues 需完整列出。
- 优先修复风格锁定问题：补齐可表格化字段，避免段落堆叠和口语化表述。
- actions 至少 3 条（证据不足可 2 条），timeline 需覆盖短期和中期。
- 对盲区项优先补齐 open_questions；若证据仍不足，可先以 pending_follow_up 标记并给出补采动作。
- 不要引入模板外新字段作为硬门槛（例如 needs.acceptance_criteria 不是必填）。
- 禁止输出“请确认是否继续”“我会创建文件”等工具执行话术。
- 禁止输出 markdown 代码块与额外说明，禁止前后缀文本。

## 输出模板
{json.dumps(response_schema, ensure_ascii=False, indent=2)}
"""


def parse_report_review_response_v3(raw_text: str, parse_meta: Optional[dict] = None) -> Optional[dict]:
    """解析 V3 审稿响应。"""
    parsed = parse_structured_json_response(
        raw_text,
        required_keys=["passed", "issues", "revised_draft"],
        require_all_keys=True,
        parse_meta=parse_meta,
    )
    if not parsed:
        return None

    issues = []
    raw_issues = parsed.get("issues", [])
    if isinstance(raw_issues, list):
        for item in raw_issues:
            if not isinstance(item, dict):
                continue
            issues.append({
                "type": str(item.get("type", "unknown")).strip(),
                "severity": str(item.get("severity", "medium")).strip().lower() or "medium",
                "message": str(item.get("message", "")).strip(),
                "target": str(item.get("target", "unknown")).strip(),
            })

    revised_draft = parsed.get("revised_draft", {})
    if not isinstance(revised_draft, dict):
        revised_draft = {}

    return {
        "passed": bool(parsed.get("passed", False)),
        "issues": issues,
        "revised_draft": revised_draft,
    }


def merge_report_draft_patch_v3(base_draft: dict, revised_patch: dict) -> dict:
    """将审稿阶段的增量 patch 合并回完整草案，减少长 JSON 输出压力。"""
    base = copy.deepcopy(base_draft) if isinstance(base_draft, dict) else {}
    patch = revised_patch if isinstance(revised_patch, dict) else {}
    if not patch:
        return base

    merged = copy.deepcopy(base)

    if "overview" in patch:
        merged["overview"] = patch.get("overview", "")

    for field in ("analysis", "visualizations"):
        if field in patch and isinstance(patch.get(field), dict):
            current_value = merged.get(field, {})
            if not isinstance(current_value, dict):
                current_value = {}
            current_value = dict(current_value)
            current_value.update(patch.get(field, {}))
            merged[field] = current_value

    for field in ("needs", "solutions", "risks", "actions", "open_questions", "evidence_index"):
        if field in patch and isinstance(patch.get(field), list):
            merged[field] = patch.get(field, [])

    return merged


def resolve_report_v3_alternate_lane(primary_lane: str) -> str:
    """为 V3 阶段选择可用且独立的备用 lane。"""
    primary = str(primary_lane or "").strip().lower()
    if primary not in {"question", "report"}:
        return ""
    alternate = "question" if primary == "report" else "report"
    primary_client = resolve_ai_client(preferred_lane=primary)
    alternate_client = resolve_ai_client(preferred_lane=alternate)
    if not primary_client or not alternate_client or primary_client is alternate_client:
        return ""
    return alternate


REVIEW_BLOCKING_ISSUE_TYPES_V3 = {
    "no_evidence",
    "unresolved_contradiction",
    "not_actionable",
    "blindspot",
    "structure_error",
    "invalid_evidence_ref",
}
REVIEW_GATE_MANAGED_ISSUE_PREFIXES_V3 = ("quality_gate_",)
REVIEW_GATE_MANAGED_ISSUE_TYPES_V3 = {"style_template_violation"}


def summarize_issue_types_v3(issues: list) -> list[str]:
    """提取问题类型列表并去重，保持原始顺序。"""
    if not isinstance(issues, list):
        return []
    output = []
    seen = set()
    for item in issues:
        if not isinstance(item, dict):
            continue
        issue_type = str(item.get("type", "") or "").strip().lower()
        if not issue_type or issue_type in seen:
            continue
        seen.add(issue_type)
        output.append(issue_type)
    return output


def _is_quality_gate_issue_type_v3(issue_type: str) -> bool:
    normalized = str(issue_type or "").strip().lower()
    return normalized.startswith(REVIEW_GATE_MANAGED_ISSUE_PREFIXES_V3) or normalized in REVIEW_GATE_MANAGED_ISSUE_TYPES_V3


def _extract_blindspot_aspect_from_text_v3(text: str) -> str:
    source = str(text or "").strip()
    if not source:
        return ""

    quoted = re.findall(r"[\"'“‘](.+?)[\"'”’]", source)
    if quoted:
        candidate = quoted[0]
        if ":" in candidate:
            candidate = candidate.split(":", 1)[1]
        if "：" in candidate:
            candidate = candidate.split("：", 1)[1]
        candidate = candidate.strip()
        if candidate:
            return candidate

    if "未覆盖盲区未进入草案" in source:
        tail = source.split("未覆盖盲区未进入草案", 1)[-1]
        tail = tail.lstrip("：: ").strip()
        if tail:
            return tail.split("、")[0].strip()
    return ""


def _collect_text_corpus_for_items_v3(items: list, keys: list[str]) -> str:
    if not isinstance(items, list):
        return ""
    seg = []
    for item in items:
        if not isinstance(item, dict):
            continue
        for key in keys:
            text = str(item.get(key, "") or "").strip()
            if text:
                seg.append(text.lower())
    return " ".join(seg)


def _is_evidence_sparse_v3(evidence_pack: Optional[dict]) -> bool:
    if not isinstance(evidence_pack, dict):
        return False
    facts = evidence_pack.get("facts", [])
    unknowns = evidence_pack.get("unknowns", [])
    quality_snapshot = evidence_pack.get("quality_snapshot", {})
    facts_count = len(facts) if isinstance(facts, list) else 0
    unknown_count = len(unknowns) if isinstance(unknowns, list) else 0
    unknown_ratio = (unknown_count / facts_count) if facts_count > 0 else 0.0
    avg_quality = _safe_float((quality_snapshot or {}).get("average_quality_score", 0.0), default=0.0)
    return unknown_ratio >= REPORT_V3_UNKNOWN_RATIO_TRIGGER or avg_quality <= 0.32


def _pick_evidence_refs_for_dimension_v3(evidence_pack: dict, dimension_hint: str = "", limit: int = 1) -> list[str]:
    if not isinstance(evidence_pack, dict):
        return []
    facts = evidence_pack.get("facts", [])
    if not isinstance(facts, list):
        return []

    normalized_hint = str(dimension_hint or "").strip().lower()
    picked = []
    for fact in facts:
        if not isinstance(fact, dict):
            continue
        q_id = str(fact.get("q_id", "") or "").upper().strip()
        if not re.fullmatch(r"Q\d+", q_id):
            continue
        if normalized_hint:
            fact_dim = str(fact.get("dimension", "") or "").strip().lower()
            fact_dim_name = str(fact.get("dimension_name", "") or "").strip().lower()
            if normalized_hint not in {fact_dim, fact_dim_name} and normalized_hint not in fact_dim_name and normalized_hint not in fact_dim:
                continue
        picked.append(q_id)
        if len(picked) >= max(1, int(limit or 1)):
            break
    return _normalize_evidence_refs(picked)


def _build_blindspot_open_question_v3(dimension: str, aspect: str, evidence_pack: dict) -> dict:
    dim_text = str(dimension or "相关维度").strip()
    aspect_text = str(aspect or "关键未覆盖点").strip()
    refs = _pick_evidence_refs_for_dimension_v3(evidence_pack, dimension_hint=dim_text, limit=1)
    return {
        "question": f"{dim_text}中的“{aspect_text}”缺少直接证据，是否需要补采访谈？",
        "reason": "该盲区会影响结论可信度，先记录为待验证问题并补采证据",
        "impact": f"{aspect_text}未澄清会影响行动优先级与方案可行性判断",
        "suggested_follow_up": f"围绕“{aspect_text}”补充角色、场景与量化口径，并确认责任边界",
        "evidence_refs": refs,
        "evidence_binding_mode": "pending_follow_up" if not refs else "weak_inferred",
    }


def _build_blindspot_pending_action_v3(dimension: str, aspect: str, evidence_pack: dict) -> dict:
    dim_text = str(dimension or "相关维度").strip()
    aspect_text = str(aspect or "关键未覆盖点").strip()
    refs = _pick_evidence_refs_for_dimension_v3(evidence_pack, dimension_hint=dim_text, limit=1)
    if not refs:
        refs = _pick_evidence_refs_for_dimension_v3(evidence_pack, dimension_hint="", limit=1)
    if not refs:
        return {}

    return {
        "action": f"补采并确认“{aspect_text}”的责任分工与执行边界",
        "owner": "产品经理",
        "timeline": "1-2周内",
        "metric": "完成至少3位相关角色访谈并输出分工决策记录",
        "evidence_refs": refs,
        "evidence_binding_mode": "weak_inferred",
        "inference_origin_field": "blindspot",
    }


def _should_soft_pass_blindspot_issue_v3(
    issue: dict,
    draft: dict,
    evidence_pack: Optional[dict] = None,
    runtime_profile: str = "",
) -> bool:
    if not isinstance(issue, dict) or not isinstance(draft, dict):
        return False

    issue_type = str(issue.get("type", "") or "").strip().lower()
    if issue_type != "blindspot":
        return False

    profile = normalize_report_profile_choice(runtime_profile, fallback=REPORT_V3_PROFILE)
    if profile == "quality" and REPORT_V3_BLINDSPOT_ACTION_REQUIRED_QUALITY:
        # quality 档保持更严格，但当证据明显稀疏时允许从“阻断”降级为“补采建议”。
        if not _is_evidence_sparse_v3(evidence_pack):
            return False
    elif profile == "balanced" and REPORT_V3_BLINDSPOT_ACTION_REQUIRED_BALANCED:
        return False

    message = str(issue.get("message", "") or "").lower()
    target = str(issue.get("target", "") or "").lower()
    mentions_action_gap = ("action" in message or "行动" in message or "行动计划" in message or "actions" in target)
    if not mentions_action_gap:
        return False

    open_questions = draft.get("open_questions", [])
    oq_corpus = _collect_text_corpus_for_items_v3(open_questions if isinstance(open_questions, list) else [], ["question", "reason", "impact", "suggested_follow_up"])
    if not oq_corpus:
        return False

    aspect = _extract_blindspot_aspect_from_text_v3(issue.get("message", ""))
    if aspect:
        return aspect.lower() in oq_corpus

    # 无法提取具体 aspect 时，至少保证存在盲区补问并且证据稀疏。
    return _is_evidence_sparse_v3(evidence_pack)


def _extract_issue_field_index_v3(target: str) -> tuple[str, int]:
    text = str(target or "").strip()
    match = re.match(r"^(needs|solutions|risks|actions|open_questions|evidence_index)\[(\d+)\]", text)
    if not match:
        return "", -1
    return match.group(1), int(match.group(2))


def _issue_target_exists_v3(target: str, draft: dict) -> bool:
    field, index = _extract_issue_field_index_v3(target)
    if not field:
        return True
    values = draft.get(field, []) if isinstance(draft, dict) else []
    if not isinstance(values, list):
        return False
    return 0 <= index < len(values)


def _normalize_review_issue_payload_v3(item: dict) -> dict:
    return {
        "type": str(item.get("type", "unknown")).strip().lower() or "unknown",
        "severity": str(item.get("severity", "medium")).strip().lower() or "medium",
        "message": str(item.get("message", "")).strip(),
        "target": str(item.get("target", "unknown")).strip(),
    }


def filter_model_review_issues_v3(
    model_issues: list,
    draft: dict,
    evidence_pack: Optional[dict] = None,
    runtime_profile: str = "",
) -> list:
    """过滤模型审稿问题：仅保留阻断型结构问题，避免模板幻觉导致误拦截。"""
    if not isinstance(model_issues, list):
        return []

    filtered = []
    for raw_item in model_issues:
        if not isinstance(raw_item, dict):
            continue
        issue = _normalize_review_issue_payload_v3(raw_item)
        issue_type = issue.get("type", "")
        message_lower = issue.get("message", "").lower()
        target = issue.get("target", "")

        if issue_type.startswith(REVIEW_GATE_MANAGED_ISSUE_PREFIXES_V3) or issue_type in REVIEW_GATE_MANAGED_ISSUE_TYPES_V3:
            continue
        if "acceptance_criteria" in message_lower:
            continue
        if issue_type == "blindspot" and _should_soft_pass_blindspot_issue_v3(
            issue,
            draft,
            evidence_pack=evidence_pack,
            runtime_profile=runtime_profile,
        ):
            continue
        if issue_type not in REVIEW_BLOCKING_ISSUE_TYPES_V3:
            continue
        if issue_type == "no_evidence" and str(target).startswith("open_questions"):
            continue
        if not _issue_target_exists_v3(target, draft):
            continue
        filtered.append(issue)
    return filtered


def merge_review_and_local_issues_v3(
    model_issues: list,
    local_issues: list,
    draft: dict,
    evidence_pack: Optional[dict] = None,
    runtime_profile: str = "",
) -> tuple[list, list]:
    """合并模型问题与本地校验问题，并去重。"""
    filtered_model_issues = filter_model_review_issues_v3(
        model_issues,
        draft,
        evidence_pack=evidence_pack,
        runtime_profile=runtime_profile,
    )

    merged = []
    seen_keys = set()
    for item in filtered_model_issues + (local_issues if isinstance(local_issues, list) else []):
        if not isinstance(item, dict):
            continue
        normalized = _normalize_review_issue_payload_v3(item)
        key = f"{normalized.get('type')}|{normalized.get('target')}|{normalized.get('message')}"
        if key in seen_keys:
            continue
        seen_keys.add(key)
        merged.append(normalized)
    return merged, filtered_model_issues


def _tokenize_similarity_text_v3(text: str) -> set[str]:
    source = str(text or "").strip().lower()
    if not source:
        return set()

    tokens = set(re.findall(r"[a-z0-9_]{2,}", source))
    for chunk in re.findall(r"[\u4e00-\u9fff]{2,12}", source):
        tokens.add(chunk)
        for idx in range(len(chunk) - 1):
            tokens.add(chunk[idx: idx + 2])
    return {token for token in tokens if token}


def _infer_item_dimension_key_v3(field: str, item: dict, evidence_pack: dict) -> str:
    if not isinstance(item, dict) or not isinstance(evidence_pack, dict):
        return ""

    dimension_coverage = evidence_pack.get("dimension_coverage", {})
    if not isinstance(dimension_coverage, dict):
        return ""

    explicit = str(item.get("dimension", "") or "").strip()
    if explicit in dimension_coverage:
        return explicit

    text_corpus = " ".join([
        str(item.get("title", "") or ""),
        str(item.get("description", "") or ""),
        str(item.get("risk", "") or ""),
        str(item.get("action", "") or ""),
        str(item.get("question", "") or ""),
        str(item.get("reason", "") or ""),
        str(item.get("impact", "") or ""),
    ]).lower()
    if not text_corpus:
        return ""

    best_key = ""
    best_hits = 0
    for dim_key, dim_meta in dimension_coverage.items():
        if not isinstance(dim_meta, dict):
            continue
        vocab = [
            dim_key,
            str(dim_meta.get("name", "") or ""),
            *(dim_meta.get("missing_aspects", []) if isinstance(dim_meta.get("missing_aspects", []), list) else []),
        ]
        hits = 0
        for token in vocab:
            token_text = str(token or "").strip().lower()
            if token_text and token_text in text_corpus:
                hits += 1
        if hits > best_hits:
            best_hits = hits
            best_key = dim_key
    return best_key


def infer_weak_evidence_refs_v3(
    field: str,
    item: dict,
    evidence_pack: dict,
    min_score: float = REPORT_V3_WEAK_BINDING_MIN_SCORE,
) -> dict:
    """仅对风险/行动/未决问题执行保守弱绑定，避免无证据硬结论。"""
    if not REPORT_V3_WEAK_BINDING_ENABLED:
        return {"refs": [], "score": 0.0}
    if field not in {"risks", "actions", "open_questions"}:
        return {"refs": [], "score": 0.0}
    if not isinstance(item, dict) or not isinstance(evidence_pack, dict):
        return {"refs": [], "score": 0.0}

    facts = evidence_pack.get("facts", [])
    if not isinstance(facts, list) or not facts:
        return {"refs": [], "score": 0.0}

    text_fields = {
        "risks": ["risk", "impact", "mitigation"],
        "actions": ["action", "owner", "timeline", "metric"],
        "open_questions": ["question", "reason", "impact", "suggested_follow_up"],
    }
    item_text = " ".join(str(item.get(key, "") or "") for key in text_fields.get(field, []))
    item_tokens = _tokenize_similarity_text_v3(item_text)
    if not item_tokens:
        return {"refs": [], "score": 0.0}

    preferred_dimension = _infer_item_dimension_key_v3(field, item, evidence_pack)
    quality_snapshot = evidence_pack.get("quality_snapshot", {})
    avg_quality = _safe_float((quality_snapshot or {}).get("average_quality_score", 0.0), default=0.0)

    best = None
    for fact in facts:
        if not isinstance(fact, dict):
            continue
        q_id = str(fact.get("q_id", "") or "").upper().strip()
        if not re.fullmatch(r"Q\d+", q_id):
            continue

        fact_text = " ".join([
            str(fact.get("question", "") or ""),
            str(fact.get("answer", "") or ""),
            str(fact.get("dimension_name", "") or ""),
            str(fact.get("dimension", "") or ""),
        ])
        fact_tokens = _tokenize_similarity_text_v3(fact_text)
        if not fact_tokens:
            continue

        overlap = len(item_tokens & fact_tokens)
        if overlap <= 0:
            continue

        coverage = overlap / max(3, min(len(item_tokens), 14))
        precision = overlap / max(4, min(len(fact_tokens), 18))
        quality_score = max(0.0, min(1.0, _safe_float(fact.get("quality_score", 0.0), default=0.0)))
        dim_bonus = 0.12 if preferred_dimension and str(fact.get("dimension", "") or "") == preferred_dimension else 0.0
        hard_bonus = 0.04 if bool(fact.get("hard_triggered", False)) else 0.0
        score = 0.62 * coverage + 0.18 * precision + 0.16 * quality_score + dim_bonus + hard_bonus

        if best is None or score > best["score"]:
            best = {"score": score, "q_id": q_id}

    if not best:
        return {"refs": [], "score": 0.0}

    threshold = float(min_score or REPORT_V3_WEAK_BINDING_MIN_SCORE)
    if field == "actions":
        threshold += 0.04
    if preferred_dimension:
        threshold -= 0.03
    if avg_quality <= 0.30:
        threshold += 0.02
    threshold = max(0.25, min(threshold, 0.92))

    if best["score"] + 1e-9 < threshold:
        return {"refs": [], "score": round(best["score"], 3)}

    return {"refs": [best["q_id"]], "score": round(best["score"], 3)}


def _demote_item_to_open_question_v3(field: str, item: dict) -> dict:
    title_map = {
        "risks": str(item.get("risk", "") or "").strip() or "该风险项",
        "actions": str(item.get("action", "") or "").strip() or "该行动项",
    }
    title = title_map.get(field, "该结论项")
    impact_text = str(item.get("impact", "") or item.get("description", "") or "").strip()
    follow_up = (
        f"请补充“{title}”对应的直接访谈证据（原话、场景、量化口径）"
        if title
        else "请补充对应的直接访谈证据（原话、场景、量化口径）"
    )
    return {
        "question": f"“{title}”当前缺少可追溯证据，是否应作为待验证假设？",
        "reason": "该项为推断结论，当前没有可靠 evidence_refs，已自动降级为待补问问题",
        "impact": impact_text or "可能影响结论可信度与行动优先级",
        "suggested_follow_up": follow_up,
        "evidence_refs": [],
        "evidence_binding_mode": "pending_follow_up",
        "inference_origin_field": field,
    }


def _deduplicate_structured_list_v3(items: list, id_fields: list[str]) -> list:
    if not isinstance(items, list):
        return []

    deduped = []
    seen = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        signature_parts = []
        for key in id_fields:
            signature_parts.append(re.sub(r"\s+", " ", str(item.get(key, "") or "").strip().lower()))
        signature = "|".join(signature_parts)
        if not signature or signature in seen:
            continue
        seen.add(signature)
        deduped.append(item)
    return deduped


def apply_deterministic_report_repairs_v3(
    draft: dict,
    evidence_pack: dict,
    issues: list,
    runtime_profile: str = "",
) -> dict:
    """
    规则化修复器（确定性）：
    1) 对 risks/actions/open_questions 的 no_evidence 尝试保守弱绑定
    2) 无法绑定的 risks/actions 自动降级为 open_questions
    3) evidence_index 中无证据条目直接清理
    4) 对盲区项做保守补全（先补 open_questions，必要时补 pending action）
    5) 在 unknown_ratio 过高时，自动补充待补采 open_questions，降低遗漏
    6) 去重，减少模型重复条目导致的误拦截
    """
    if not isinstance(draft, dict):
        return {"draft": {}, "changed": False, "notes": []}

    working = copy.deepcopy(draft)
    notes = []
    changed = False
    remove_index_map = {"risks": set(), "actions": set(), "open_questions": set(), "evidence_index": set()}

    runtime_profile = normalize_report_profile_choice(runtime_profile, fallback=REPORT_V3_PROFILE)
    weak_binding_floor = REPORT_V3_WEAK_BINDING_MIN_SCORE
    if runtime_profile == "quality":
        weak_binding_floor = max(weak_binding_floor, 0.48)

    for issue in (issues if isinstance(issues, list) else []):
        if not isinstance(issue, dict):
            continue
        issue_type = str(issue.get("type", "") or "").strip().lower()
        if issue_type != "no_evidence":
            continue

        field, index = _extract_issue_field_index_v3(str(issue.get("target", "") or ""))
        if field not in {"risks", "actions", "open_questions", "evidence_index"} or index < 0:
            continue

        values = working.get(field, [])
        if not isinstance(values, list) or index >= len(values):
            continue
        item = values[index]
        if not isinstance(item, dict):
            continue

        refs = _normalize_evidence_refs(item.get("evidence_refs", []))
        if refs:
            continue

        if field == "evidence_index":
            remove_index_map[field].add(index)
            changed = True
            notes.append(f"移除无证据索引项 {field}[{index}]")
            continue

        weak_bind = infer_weak_evidence_refs_v3(
            field,
            item,
            evidence_pack,
            min_score=weak_binding_floor,
        )
        weak_refs = _normalize_evidence_refs(weak_bind.get("refs", []))
        if weak_refs:
            item["evidence_refs"] = weak_refs
            item["evidence_binding_mode"] = "weak_inferred"
            item["evidence_binding_score"] = float(weak_bind.get("score", 0.0) or 0.0)
            changed = True
            notes.append(f"{field}[{index}] 弱绑定证据 {','.join(weak_refs)}")
            continue

        if field in {"risks", "actions"}:
            open_questions = working.get("open_questions", [])
            if not isinstance(open_questions, list):
                open_questions = []
            open_questions.append(_demote_item_to_open_question_v3(field, item))
            working["open_questions"] = open_questions
            remove_index_map[field].add(index)
            changed = True
            notes.append(f"{field}[{index}] 降级为 open_questions")

    # 盲区规则补全：优先进入 open_questions；质量档可按配置补一条待验证行动项。
    blindspot_candidates = []
    for blindspot in (evidence_pack.get("blindspots", []) if isinstance(evidence_pack, dict) else []):
        if not isinstance(blindspot, dict):
            continue
        dimension = str(blindspot.get("dimension", "") or "").strip()
        aspect = str(blindspot.get("aspect", "") or "").strip()
        if not aspect:
            continue
        blindspot_candidates.append((dimension, aspect))

    for issue in (issues if isinstance(issues, list) else []):
        if not isinstance(issue, dict):
            continue
        if str(issue.get("type", "") or "").strip().lower() != "blindspot":
            continue
        raw_message = str(issue.get("message", "") or "").strip()
        aspect = _extract_blindspot_aspect_from_text_v3(raw_message)
        if not aspect:
            continue
        blindspot_candidates.append(("", aspect))

    blindspot_dedup = []
    blindspot_seen = set()
    for dimension, aspect in blindspot_candidates:
        sig = f"{str(dimension or '').strip().lower()}|{str(aspect or '').strip().lower()}"
        if not aspect or sig in blindspot_seen:
            continue
        blindspot_seen.add(sig)
        blindspot_dedup.append((str(dimension or "").strip(), str(aspect or "").strip()))

    if blindspot_dedup:
        open_questions = working.get("open_questions", [])
        if not isinstance(open_questions, list):
            open_questions = []
        actions = working.get("actions", [])
        if not isinstance(actions, list):
            actions = []

        action_required_for_blindspot = (
            REPORT_V3_BLINDSPOT_ACTION_REQUIRED_QUALITY
            if runtime_profile == "quality"
            else REPORT_V3_BLINDSPOT_ACTION_REQUIRED_BALANCED
        )
        for dimension, aspect in blindspot_dedup:
            oq_corpus = _collect_text_corpus_for_items_v3(open_questions, ["question", "reason", "impact", "suggested_follow_up"])
            action_corpus = _collect_text_corpus_for_items_v3(actions, ["action", "owner", "timeline", "metric"])
            aspect_token = aspect.lower()

            if aspect_token and aspect_token not in oq_corpus:
                open_questions.append(_build_blindspot_open_question_v3(dimension, aspect, evidence_pack))
                changed = True
                notes.append(f"盲区补齐 open_questions: {aspect}")

            if action_required_for_blindspot and aspect_token and aspect_token not in action_corpus:
                action_item = _build_blindspot_pending_action_v3(dimension, aspect, evidence_pack)
                if action_item:
                    actions.append(action_item)
                    changed = True
                    notes.append(f"盲区补齐 pending action: {aspect}")

        working["open_questions"] = open_questions
        working["actions"] = actions

    # unknown 过高时自动补采待问，减少“信息缺口直接进结论”的风险。
    if REPORT_V3_UNKNOWNS_TO_OPEN_QUESTIONS_ENABLED and isinstance(evidence_pack, dict):
        raw_facts = evidence_pack.get("facts", [])
        raw_unknowns = evidence_pack.get("unknowns", [])
        facts_count = len(raw_facts) if isinstance(raw_facts, list) else 0
        unknown_count = len(raw_unknowns) if isinstance(raw_unknowns, list) else 0
        unknown_ratio = (unknown_count / facts_count) if facts_count > 0 else 0.0
        if unknown_ratio >= REPORT_V3_UNKNOWN_RATIO_TRIGGER and isinstance(raw_unknowns, list) and raw_unknowns:
            open_questions = working.get("open_questions", [])
            if not isinstance(open_questions, list):
                open_questions = []
            oq_corpus = _collect_text_corpus_for_items_v3(open_questions, ["question", "reason", "impact", "suggested_follow_up"])
            appended = 0
            for item in raw_unknowns:
                if appended >= REPORT_V3_UNKNOWNS_TO_OPEN_QUESTIONS_MAX_ITEMS:
                    break
                if not isinstance(item, dict):
                    continue
                q_id = str(item.get("q_id", "") or "").upper().strip()
                if not re.fullmatch(r"Q\d+", q_id):
                    continue
                reason = str(item.get("reason", "") or "").strip() or "回答存在不确定信息"
                dimension = str(item.get("dimension", "") or "").strip() or "相关维度"
                signature = f"{q_id.lower()} {reason.lower()}"
                if signature in oq_corpus:
                    continue
                open_questions.append({
                    "question": f"{dimension}在{q_id}呈现不确定信号，是否需要补采访谈以确认真实约束？",
                    "reason": reason,
                    "impact": "若不补采，报告中的优先级和行动口径可能偏离实际",
                    "suggested_follow_up": f"围绕 {q_id} 对应场景补充可量化事实（角色、频次、影响范围）",
                    "evidence_refs": [q_id],
                    "evidence_binding_mode": "pending_follow_up",
                })
                appended += 1
                changed = True
                notes.append(f"unknown补采 open_questions: {q_id}")
            working["open_questions"] = open_questions

    for field, index_set in remove_index_map.items():
        if not index_set:
            continue
        values = working.get(field, [])
        if not isinstance(values, list):
            continue
        filtered = [item for idx, item in enumerate(values) if idx not in index_set]
        if len(filtered) != len(values):
            working[field] = filtered
            changed = True

    # 统一清洗 evidence_refs：去重 + 移除无效 Q 编号。
    valid_q_refs = {
        str(fact.get("q_id", "")).upper().strip()
        for fact in (evidence_pack.get("facts", []) if isinstance(evidence_pack.get("facts", []), list) else [])
        if isinstance(fact, dict) and re.fullmatch(r"Q\d+", str(fact.get("q_id", "")).upper().strip())
    }
    for field in ["needs", "solutions", "risks", "actions", "open_questions", "evidence_index"]:
        values = working.get(field, [])
        if not isinstance(values, list):
            continue
        for item in values:
            if not isinstance(item, dict):
                continue
            refs = _normalize_evidence_refs(item.get("evidence_refs", []))
            if valid_q_refs:
                refs = [ref for ref in refs if ref in valid_q_refs]
            if refs != _normalize_evidence_refs(item.get("evidence_refs", [])):
                item["evidence_refs"] = refs
                changed = True

    # 统一去重，降低重复条目带来的伪问题。
    dedup_rules = {
        "needs": ["name", "description"],
        "solutions": ["title", "description"],
        "risks": ["risk", "impact"],
        "actions": ["action", "timeline"],
        "open_questions": ["question", "reason"],
        "evidence_index": ["claim"],
    }
    for field, keys in dedup_rules.items():
        values = working.get(field, [])
        if not isinstance(values, list):
            continue
        deduped = _deduplicate_structured_list_v3(values, keys)
        if len(deduped) != len(values):
            working[field] = deduped
            changed = True
            notes.append(f"{field} 去重 {len(values) - len(deduped)} 项")

    return {"draft": working, "changed": changed, "notes": notes[:30]}


def _collect_claim_entries_for_quality(draft: dict) -> list:
    """收集草案中的可计量结论条目。"""
    claim_entries = []
    for field in ["needs", "solutions", "risks", "actions", "open_questions", "evidence_index"]:
        values = draft.get(field, [])
        if not isinstance(values, list):
            continue
        for item in values:
            if not isinstance(item, dict):
                continue
            claim_entries.append({
                "field": field,
                "evidence_refs": _normalize_evidence_refs(item.get("evidence_refs", [])),
                "evidence_binding_mode": str(item.get("evidence_binding_mode", "") or "").strip().lower(),
                "owner": str(item.get("owner", "")).strip(),
                "timeline": str(item.get("timeline", "")).strip(),
                "metric": str(item.get("metric", "")).strip(),
            })
    return claim_entries


REPORT_V3_QUALITY_THRESHOLDS = {
    "evidence_coverage": 0.9,
    "consistency": 0.8,
    "actionability": 0.8,
    "expression_structure": 0.82,
    "table_readiness": 0.78,
    "action_acceptance": 0.75,
    "milestone_coverage": 0.65,
    "max_weak_binding_ratio": 0.35,
}


def _profile_quality_gate_thresholds_v3(profile: str, base_thresholds: Optional[dict] = None) -> dict:
    """按档位返回质量门禁阈值。quality 更严格，balanced 适度放宽。"""
    thresholds = dict(REPORT_V3_QUALITY_THRESHOLDS)
    if isinstance(base_thresholds, dict):
        thresholds.update(base_thresholds)

    normalized_profile = normalize_report_profile_choice(profile, fallback="balanced")
    if normalized_profile == "quality":
        return thresholds

    # balanced 档适度放宽表达与模板门禁，避免小样本访谈被过度拦截。
    relaxed = dict(thresholds)
    relaxed["expression_structure"] = min(float(relaxed.get("expression_structure", 0.82) or 0.82), 0.72)
    relaxed["table_readiness"] = min(float(relaxed.get("table_readiness", 0.78) or 0.78), 0.68)
    relaxed["action_acceptance"] = min(float(relaxed.get("action_acceptance", 0.75) or 0.75), 0.65)
    relaxed["milestone_coverage"] = min(float(relaxed.get("milestone_coverage", 0.65) or 0.65), 0.45)
    relaxed["max_weak_binding_ratio"] = max(float(relaxed.get("max_weak_binding_ratio", 0.35) or 0.35), 0.45)
    return relaxed


def _adapt_quality_gate_thresholds_by_evidence_v3(limit: dict, quality_meta: dict) -> dict:
    """根据证据可靠性动态收敛/放宽部分表达类门禁。"""
    adapted = dict(limit)
    evidence_context = quality_meta.get("evidence_context", {}) if isinstance(quality_meta, dict) else {}
    if not isinstance(evidence_context, dict):
        return adapted

    unknown_ratio = max(0.0, min(1.0, _safe_float(evidence_context.get("unknown_ratio", 0.0), default=0.0)))
    avg_quality = max(0.0, min(1.0, _safe_float(evidence_context.get("average_quality_score", 0.0), default=0.0)))
    facts_count = max(0, int(evidence_context.get("facts_count", 0) or 0))

    if facts_count <= 0:
        return adapted

    # 仅对表达/模板类门禁做有限放宽，证据覆盖与一致性门禁保持刚性。
    tension = 0.0
    if unknown_ratio > 0.60:
        tension += min(0.12, (unknown_ratio - 0.60) * 0.30)
    if avg_quality < 0.32:
        tension += min(0.08, (0.32 - avg_quality) * 0.45)
    tension = max(0.0, min(tension, 0.18))
    if tension <= 0.0:
        return adapted

    for key in ("actionability", "expression_structure", "table_readiness", "action_acceptance", "milestone_coverage"):
        current = float(adapted.get(key, 0.0) or 0.0)
        adapted[key] = max(0.45, current - tension)
    adapted["max_weak_binding_ratio"] = min(0.60, max(float(adapted.get("max_weak_binding_ratio", 0.35) or 0.35), 0.35 + tension))
    return adapted


def build_quality_gate_issues_v3(quality_meta: dict, thresholds: Optional[dict] = None) -> list:
    """根据质量阈值构建门禁问题列表。"""
    if not isinstance(quality_meta, dict):
        return [{
            "type": "quality_gate_missing",
            "severity": "high",
            "message": "缺少质量评分结果，无法通过质量门禁",
            "target": "quality_meta",
        }]

    runtime_profile = normalize_report_profile_choice(
        str(quality_meta.get("runtime_profile", "") or ""),
        fallback="balanced",
    )
    limit = _profile_quality_gate_thresholds_v3(runtime_profile, base_thresholds=thresholds)
    limit = _adapt_quality_gate_thresholds_by_evidence_v3(limit, quality_meta)

    checks = [
        ("evidence_coverage", "quality_gate_evidence", "证据覆盖率", "needs/solutions/actions/risks/open_questions/evidence_index"),
        ("consistency", "quality_gate_consistency", "冲突解释完成度", "risks/open_questions"),
        ("actionability", "quality_gate_actionability", "可执行建议占比", "solutions/actions"),
        ("expression_structure", "quality_gate_expression", "表达结构完整度", "overview/analysis/needs/solutions/risks/actions"),
        ("table_readiness", "quality_gate_table", "表格化可读性", "needs/solutions/risks/actions"),
        ("action_acceptance", "quality_gate_acceptance", "行动验收口径完备度", "actions.metric"),
        ("milestone_coverage", "quality_gate_milestone", "行动里程碑覆盖度", "actions.timeline"),
    ]

    issues = []
    for key, issue_type, label, target in checks:
        current = float(quality_meta.get(key, 0) or 0)
        required = float(limit.get(key, 0) or 0)
        if current + 1e-9 < required:
            issues.append({
                "type": issue_type,
                "severity": "high",
                "message": f"{label}低于门槛（当前{current:.1%}，要求≥{required:.1%}）",
                "target": target,
            })

    weak_binding_ratio = max(0.0, min(1.0, _safe_float(quality_meta.get("weak_binding_ratio", 0.0), default=0.0)))
    weak_binding_limit = max(0.0, min(1.0, _safe_float(limit.get("max_weak_binding_ratio", 0.35), default=0.35)))
    if weak_binding_ratio > weak_binding_limit + 1e-9:
        issues.append({
            "type": "quality_gate_weak_binding",
            "severity": "high" if runtime_profile == "quality" else "medium",
            "message": f"弱证据绑定占比过高（当前{weak_binding_ratio:.1%}，允许≤{weak_binding_limit:.1%}）",
            "target": "risks/actions/open_questions",
        })

    template_minimums = quality_meta.get("template_minimums", {})
    list_counts = quality_meta.get("list_counts", {})
    if isinstance(template_minimums, dict) and isinstance(list_counts, dict):
        display_names = {
            "needs": "核心需求",
            "solutions": "方案建议",
            "risks": "风险项",
            "actions": "行动项",
            "open_questions": "未决问题",
        }
        deficits = []
        for key, label in display_names.items():
            required = int(template_minimums.get(key, 0) or 0)
            current = int(list_counts.get(key, 0) or 0)
            if required > 0 and current < required:
                deficits.append(f"{label}≥{required}（当前{current}）")

        if deficits:
            severity = "high" if runtime_profile == "quality" else "medium"
            issues.append({
                "type": "style_template_violation",
                "severity": severity,
                "message": "风格模板未达标：" + "，".join(deficits),
                "target": "needs/solutions/risks/actions/open_questions",
            })
    return issues


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
    for entry in claim_entries:
        refs = entry.get("evidence_refs", [])
        if not refs:
            continue
        evidence_covered += 1
        binding_mode = str(entry.get("evidence_binding_mode", "") or "").strip().lower()
        if binding_mode == "weak_inferred":
            weak_binding_count += 1
            weighted_evidence_score += 0.45
        elif binding_mode == "pending_follow_up":
            weighted_evidence_score += 0.0
        else:
            weighted_evidence_score += 1.0
    evidence_coverage = (weighted_evidence_score / claim_total) if claim_total > 0 else 0.0
    weak_binding_ratio = (weak_binding_count / evidence_covered) if evidence_covered > 0 else 0.0

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

    template_minimums = {
        "needs": 2 if facts_count >= 8 else 1,
        "solutions": 2 if facts_count >= 8 else 1,
        "risks": 1,
        "actions": 3 if facts_count >= 10 else 2,
        "open_questions": 1 if (blindspot_count > 0 or unknown_count > 0) else 0,
    }
    if unknown_ratio >= 0.65 or avg_quality_score <= 0.30:
        template_minimums["actions"] = min(template_minimums["actions"], 2)
        template_minimums["solutions"] = min(template_minimums["solutions"], 1 if facts_count < 14 else 2)
        if unknown_count > 0:
            template_minimums["open_questions"] = max(template_minimums["open_questions"], 2 if facts_count >= 10 else 1)

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
        "weak_binding_ratio": round(weak_binding_ratio, 3),
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
        },
        "timeline_buckets": sorted(timeline_buckets),
        "measurable_actions": measurable_actions,
        "review_issue_count": len(issues),
    }


def build_report_quality_meta_fallback(session: dict, mode: str) -> dict:
    """回退流程的质量元数据估算。"""
    evidence_pack = build_report_evidence_pack(session)
    evidence_coverage = float(evidence_pack.get("overall_coverage", 0.0))
    contradiction_total = len(evidence_pack.get("contradictions", []))
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
            "facts_count": len(evidence_pack.get("facts", [])) if isinstance(evidence_pack.get("facts", []), list) else 0,
            "unknown_count": len(evidence_pack.get("unknowns", [])) if isinstance(evidence_pack.get("unknowns", []), list) else 0,
            "blindspots_count": len(evidence_pack.get("blindspots", [])) if isinstance(evidence_pack.get("blindspots", []), list) else 0,
            "unknown_ratio": 0.0,
            "average_quality_score": 0.0,
        },
        "timeline_buckets": [],
        "measurable_actions": 0,
        "review_issue_count": 0,
    }


def ensure_flowchart_semantic_styles(mermaid_text: str) -> str:
    """为 flowchart/graph 自动补充语义配色，避免单色图。"""
    source = str(mermaid_text or "").strip()
    if not source:
        return source

    if not re.match(r"(?is)^\s*(flowchart|graph)\b", source):
        return source

    if re.search(r"(?im)^\s*classDef\s+", source):
        return source

    node_ids: list[str] = []
    for match in re.finditer(r"\b([A-Za-z][A-Za-z0-9_]*)\s*(?=[\[\(\{])", source):
        node_id = match.group(1)
        if node_id not in node_ids:
            node_ids.append(node_id)

    if not node_ids:
        return source

    core_keywords = ("核心", "关键", "主流程", "目标", "里程碑", "方案", "主链路")
    decision_keywords = ("判断", "决策", "分流", "校验", "审核", "网关", "验证")
    risk_keywords = ("风险", "阻塞", "失败", "告警", "异常", "流失", "中断", "问题")

    class_buckets: dict[str, list[str]] = {
        "dvCore": [],
        "dvDecision": [],
        "dvRisk": [],
        "dvSupport": [],
    }

    for idx, node_id in enumerate(node_ids):
        label_match = re.search(rf"(?m)^\s*{re.escape(node_id)}\s*[\[\(\{{]([^\]\)\}}]+)", source)
        label = str(label_match.group(1) if label_match else node_id)
        if any(keyword in label for keyword in risk_keywords):
            class_buckets["dvRisk"].append(node_id)
            continue
        if any(keyword in label for keyword in decision_keywords):
            class_buckets["dvDecision"].append(node_id)
            continue
        if any(keyword in label for keyword in core_keywords):
            class_buckets["dvCore"].append(node_id)
            continue

        # 无明显语义标签时按顺序分散到不同语义色，避免单色图。
        slot = idx % 3
        if slot == 0:
            class_buckets["dvCore"].append(node_id)
        elif slot == 1:
            class_buckets["dvDecision"].append(node_id)
        else:
            class_buckets["dvSupport"].append(node_id)

    style_lines = [
        "classDef dvCore fill:#DBEAFE,stroke:#2563EB,color:#1E3A8A,stroke-width:1.4px",
        "classDef dvDecision fill:#FEF3C7,stroke:#D97706,color:#7C2D12,stroke-width:1.4px",
        "classDef dvRisk fill:#FEE2E2,stroke:#DC2626,color:#7F1D1D,stroke-width:1.4px",
        "classDef dvSupport fill:#DCFCE7,stroke:#16A34A,color:#14532D,stroke-width:1.4px",
    ]
    class_lines = [
        f"class {','.join(nodes)} {class_name}"
        for class_name, nodes in class_buckets.items()
        if nodes
    ]

    return source + "\n" + "\n".join(style_lines + class_lines)


def build_report_temporal_fields(generated_at: Optional[datetime] = None) -> dict:
    """统一构建报告时间与编号字段，避免多处格式不一致。"""
    current = generated_at if isinstance(generated_at, datetime) else datetime.now()
    if current.tzinfo is not None:
        local_now = current.astimezone()
    else:
        local_now = current

    return {
        "interview_date": local_now.strftime("%Y-%m-%d"),
        "generated_datetime_cn": local_now.strftime("%Y年%m月%d日 %H:%M"),
        "generated_datetime_iso_minute": local_now.strftime("%Y-%m-%d %H:%M"),
        "report_id": f"deep-vision-{local_now.strftime('%Y%m%d-%H%M')}",
    }


def _normalize_markdown_cell_v3(value: object, fallback: str = "-", max_len: int = 88) -> str:
    text = str(value or "").replace("\n", " ").strip()
    text = re.sub(r"\s+", " ", text)
    text = text.replace("|", "/").replace("`", "'")
    if not text:
        return fallback
    if len(text) > max_len:
        return text[: max_len - 3] + "..."
    return text


def _normalize_mermaid_label_v3(value: object, fallback: str, max_len: int = 16) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[<>{}\[\]\"`|]", "", text)
    text = text.replace(":", "-")
    if not text:
        text = fallback
    if len(text) > max_len:
        text = text[: max_len - 3] + "..."
    return text


def _build_business_flow_mermaid_from_data_v3(needs: list, actions: list, risks: list) -> str:
    lead_need = _normalize_mermaid_label_v3(
        (needs[0].get("name", "") if needs and isinstance(needs[0], dict) else ""),
        "核心需求",
    )
    lead_action = _normalize_mermaid_label_v3(
        (actions[0].get("action", "") if actions and isinstance(actions[0], dict) else ""),
        "行动落地",
    )
    lead_risk = _normalize_mermaid_label_v3(
        (risks[0].get("risk", "") if risks and isinstance(risks[0], dict) else ""),
        "风险治理",
    )

    return f"""flowchart TD
    A[访谈输入] --> B{{需求是否明确}}
    B -->|明确| C[梳理 {lead_need}]
    B -->|不明确| D[补充追问取证]
    D --> C
    C --> E[形成方案建议]
    E --> F[执行 {lead_action}]
    E --> G[治理 {lead_risk}]
    F --> H[结果复盘]
    G --> H
    classDef dvCore fill:#DBEAFE,stroke:#2563EB,color:#1E3A8A,stroke-width:1.4px
    classDef dvDecision fill:#FEF3C7,stroke:#D97706,color:#7C2D12,stroke-width:1.4px
    classDef dvRisk fill:#FEE2E2,stroke:#DC2626,color:#7F1D1D,stroke-width:1.4px
    classDef dvSupport fill:#DCFCE7,stroke:#16A34A,color:#14532D,stroke-width:1.4px
    class A,C,E,F,H dvCore
    class B dvDecision
    class G dvRisk
    class D dvSupport"""


def _build_demand_pie_mermaid_from_data_v3(needs: list) -> str:
    priority_counts = {"P0": 0, "P1": 0, "P2": 0, "P3": 0}
    for item in needs:
        if not isinstance(item, dict):
            continue
        priority = str(item.get("priority", "P1")).strip().upper()
        if priority not in priority_counts:
            priority = "P1"
        priority_counts[priority] += 1

    total = sum(priority_counts.values())
    if total <= 0:
        return """pie title 需求优先级分布
    "P0 立即执行" : 35
    "P1 计划执行" : 30
    "P2 可委派" : 20
    "P3 低优先级" : 15"""

    return "\n".join([
        "pie title 需求优先级分布",
        f'    "P0 立即执行" : {max(1, priority_counts["P0"])}',
        f'    "P1 计划执行" : {max(1, priority_counts["P1"])}',
        f'    "P2 可委派" : {max(1, priority_counts["P2"])}',
        f'    "P3 低优先级" : {max(1, priority_counts["P3"])}',
    ])


def _build_architecture_mermaid_from_data_v3(analysis: dict, actions: list, risks: list) -> str:
    tech_focus = _normalize_mermaid_label_v3(analysis.get("tech_constraints", ""), "技术约束")
    action_focus = _normalize_mermaid_label_v3(
        (actions[0].get("owner", "") if actions and isinstance(actions[0], dict) else ""),
        "执行协同",
    )
    risk_focus = _normalize_mermaid_label_v3(
        (risks[0].get("risk", "") if risks and isinstance(risks[0], dict) else ""),
        "风险控制",
    )

    return f"""flowchart LR
    A[访谈输入层] --> B[结构化分析引擎]
    B --> C[需求证据池]
    C --> D[方案策略层]
    D --> E[执行编排-{action_focus}]
    D --> F[风险治理-{risk_focus}]
    B --> G[约束校验-{tech_focus}]
    E --> H[(指标看板)]
    F --> H
    G --> H
    classDef dvCore fill:#DBEAFE,stroke:#2563EB,color:#1E3A8A,stroke-width:1.4px
    classDef dvDecision fill:#FEF3C7,stroke:#D97706,color:#7C2D12,stroke-width:1.4px
    classDef dvRisk fill:#FEE2E2,stroke:#DC2626,color:#7F1D1D,stroke-width:1.4px
    classDef dvSupport fill:#DCFCE7,stroke:#16A34A,color:#14532D,stroke-width:1.4px
    class A,C,D,E,H dvCore
    class B dvDecision
    class F dvRisk
    class G dvSupport"""


def _format_report_item_refs_v3(item: dict, limit: int = 6) -> str:
    refs = _normalize_evidence_refs((item or {}).get("evidence_refs", []))
    if not refs:
        return "-"
    return "、".join(refs[:max(1, int(limit or 1))])


def _build_priority_matrix_mermaid_for_custom_v3(needs: list) -> str:
    if not isinstance(needs, list) or not needs:
        return """quadrantChart
    title 优先级矩阵
    x-axis 紧急程度（左低） --> 紧急程度（右高）
    y-axis 重要程度（下低） --> 重要程度（上高）
    quadrant-1 立即执行
    quadrant-2 计划执行
    quadrant-3 低优先级
    quadrant-4 可委派
    Req1: [0.78, 0.82]
    Req2: [0.62, 0.72]"""

    anchor = {
        "P0": (0.85, 0.88),
        "P1": (0.68, 0.73),
        "P2": (0.72, 0.42),
        "P3": (0.35, 0.30),
    }
    lines = [
        "quadrantChart",
        "    title 优先级矩阵",
        "    x-axis 紧急程度（左低） --> 紧急程度（右高）",
        "    y-axis 重要程度（下低） --> 重要程度（上高）",
        "    quadrant-1 立即执行",
        "    quadrant-2 计划执行",
        "    quadrant-3 低优先级",
        "    quadrant-4 可委派",
    ]
    for idx, item in enumerate(needs[:12], 1):
        priority = str((item or {}).get("priority", "P1")).strip().upper()
        if priority not in anchor:
            priority = "P1"
        base_x, base_y = anchor[priority]
        offset = ((idx % 4) - 1.5) * 0.03
        x = max(0.05, min(0.95, base_x + offset))
        y = max(0.05, min(0.95, base_y - offset * 0.7))
        lines.append(f"    Req{idx}: [{x:.2f}, {y:.2f}]")
    return "\n".join(lines)


def _render_priority_table_from_needs_v3(needs: list) -> list[str]:
    groups = {"P0": [], "P1": [], "P2": [], "P3": []}
    for item in needs if isinstance(needs, list) else []:
        if not isinstance(item, dict):
            continue
        p = str(item.get("priority", "P1")).strip().upper()
        if p not in groups:
            p = "P1"
        groups[p].append(_normalize_markdown_cell_v3(item.get("name", "未命名需求"), max_len=30))
    return [
        "| 优先级 | 需求项 | 说明 |",
        "|:---:|:---|:---|",
        f"| 🔴 P0 立即执行 | {'、'.join(groups['P0']) if groups['P0'] else '-'} | 重要且紧急，需优先投入 |",
        f"| 🟡 P1 计划执行 | {'、'.join(groups['P1']) if groups['P1'] else '-'} | 重要但可分阶段推进 |",
        f"| 🟢 P2 可委派 | {'、'.join(groups['P2']) if groups['P2'] else '-'} | 影响有限，可并行安排 |",
        f"| ⚪ P3 低优先级 | {'、'.join(groups['P3']) if groups['P3'] else '-'} | 可延后处理并持续观察 |",
    ]


def _render_custom_table_from_source_v3(source: str, draft: dict) -> list[str]:
    source_key = str(source or "").strip()
    if source_key == "needs":
        rows = draft.get("needs", []) if isinstance(draft.get("needs", []), list) else []
        lines = ["| 编号 | 优先级 | 需求项 | 描述 | 证据 |", "|:---:|:---:|:---|:---|:---|"]
        for idx, item in enumerate(rows, 1):
            if not isinstance(item, dict):
                continue
            lines.append(
                "| "
                f"{idx} | "
                f"{_normalize_markdown_cell_v3(item.get('priority', 'P1'), fallback='P1', max_len=8)} | "
                f"{_normalize_markdown_cell_v3(item.get('name', ''), fallback='-')} | "
                f"{_normalize_markdown_cell_v3(item.get('description', ''), fallback='-')} | "
                f"{_normalize_markdown_cell_v3(_format_report_item_refs_v3(item), max_len=30)} |"
            )
        if len(lines) == 2:
            lines.append("| - | - | 暂无结构化核心需求 | - | - |")
        return lines

    if source_key == "priority_list":
        return _render_priority_table_from_needs_v3(draft.get("needs", []))

    if source_key == "solutions":
        rows = draft.get("solutions", []) if isinstance(draft.get("solutions", []), list) else []
        lines = ["| 编号 | 方案建议 | 说明 | Owner | 时间计划 | 验收指标 | 证据 |", "|:---:|:---|:---|:---|:---|:---|:---|"]
        for idx, item in enumerate(rows, 1):
            if not isinstance(item, dict):
                continue
            lines.append(
                "| "
                f"{idx} | "
                f"{_normalize_markdown_cell_v3(item.get('title', ''), fallback='-')} | "
                f"{_normalize_markdown_cell_v3(item.get('description', ''), fallback='-')} | "
                f"{_normalize_markdown_cell_v3(item.get('owner', '待定'), max_len=20)} | "
                f"{_normalize_markdown_cell_v3(item.get('timeline', '待定'), max_len=24)} | "
                f"{_normalize_markdown_cell_v3(item.get('metric', '待定'), max_len=30)} | "
                f"{_normalize_markdown_cell_v3(_format_report_item_refs_v3(item), max_len=30)} |"
            )
        if len(lines) == 2:
            lines.append("| - | 暂无结构化方案建议 | - | - | - | - | - |")
        return lines

    if source_key == "risks":
        rows = draft.get("risks", []) if isinstance(draft.get("risks", []), list) else []
        lines = ["| 编号 | 风险项 | 影响 | 缓解措施 | 证据 |", "|:---:|:---|:---|:---|:---|"]
        for idx, item in enumerate(rows, 1):
            if not isinstance(item, dict):
                continue
            lines.append(
                "| "
                f"{idx} | "
                f"{_normalize_markdown_cell_v3(item.get('risk', ''), fallback='-')} | "
                f"{_normalize_markdown_cell_v3(item.get('impact', ''), fallback='-')} | "
                f"{_normalize_markdown_cell_v3(item.get('mitigation', ''), fallback='-')} | "
                f"{_normalize_markdown_cell_v3(_format_report_item_refs_v3(item), max_len=30)} |"
            )
        if len(lines) == 2:
            lines.append("| - | 暂无结构化风险项 | - | - | - |")
        return lines

    if source_key == "actions":
        rows = draft.get("actions", []) if isinstance(draft.get("actions", []), list) else []
        lines = ["| 编号 | 行动项 | Owner | 时间计划 | 验收指标 | 证据 |", "|:---:|:---|:---|:---|:---|:---|"]
        for idx, item in enumerate(rows, 1):
            if not isinstance(item, dict):
                continue
            lines.append(
                "| "
                f"{idx} | "
                f"{_normalize_markdown_cell_v3(item.get('action', ''), fallback='-')} | "
                f"{_normalize_markdown_cell_v3(item.get('owner', '待定'), max_len=20)} | "
                f"{_normalize_markdown_cell_v3(item.get('timeline', '待定'), max_len=24)} | "
                f"{_normalize_markdown_cell_v3(item.get('metric', '待定'), max_len=30)} | "
                f"{_normalize_markdown_cell_v3(_format_report_item_refs_v3(item), max_len=30)} |"
            )
        if len(lines) == 2:
            lines.append("| - | 暂无结构化下一步行动 | - | - | - | - |")
        return lines

    if source_key == "open_questions":
        rows = draft.get("open_questions", []) if isinstance(draft.get("open_questions", []), list) else []
        lines = ["| 编号 | 未决问题 | 原因 | 影响 | 建议补问 | 证据 |", "|:---:|:---|:---|:---|:---|:---|"]
        for idx, item in enumerate(rows, 1):
            if not isinstance(item, dict):
                continue
            lines.append(
                "| "
                f"{idx} | "
                f"{_normalize_markdown_cell_v3(item.get('question', ''), fallback='-')} | "
                f"{_normalize_markdown_cell_v3(item.get('reason', ''), fallback='-')} | "
                f"{_normalize_markdown_cell_v3(item.get('impact', ''), fallback='-')} | "
                f"{_normalize_markdown_cell_v3(item.get('suggested_follow_up', ''), fallback='-')} | "
                f"{_normalize_markdown_cell_v3(_format_report_item_refs_v3(item), max_len=30)} |"
            )
        if len(lines) == 2:
            lines.append("| - | 暂无未决问题 | - | - | - | - |")
        return lines

    if source_key == "evidence_index":
        rows = draft.get("evidence_index", []) if isinstance(draft.get("evidence_index", []), list) else []
        lines = ["| 编号 | 关键结论 | 置信度 | 证据 |", "|:---:|:---|:---:|:---|"]
        for idx, item in enumerate(rows, 1):
            if not isinstance(item, dict):
                continue
            lines.append(
                "| "
                f"{idx} | "
                f"{_normalize_markdown_cell_v3(item.get('claim', ''), fallback='-')} | "
                f"{_normalize_markdown_cell_v3(item.get('confidence', 'medium'), max_len=8)} | "
                f"{_normalize_markdown_cell_v3(_format_report_item_refs_v3(item), max_len=30)} |"
            )
        if len(lines) == 2:
            lines.append("| - | 暂无证据索引 | - | - |")
        return lines

    # 未识别 source 时回退成文本占位。
    return ["暂无可渲染表格数据。"]


def _render_custom_list_from_source_v3(source: str, draft: dict) -> list[str]:
    source_key = str(source or "").strip()
    value = resolve_custom_report_source_value_v3(draft, source_key)
    items = value if isinstance(value, list) else []
    if not items:
        return ["- 暂无数据"]

    label_field = {
        "needs": "name",
        "solutions": "title",
        "risks": "risk",
        "actions": "action",
        "open_questions": "question",
        "evidence_index": "claim",
    }.get(source_key, "")

    lines = []
    for item in items[:20]:
        if isinstance(item, dict):
            if label_field:
                label = _normalize_markdown_cell_v3(item.get(label_field, ""), fallback="-", max_len=80)
            else:
                label = _normalize_markdown_cell_v3(json.dumps(item, ensure_ascii=False), fallback="-", max_len=120)
        else:
            label = _normalize_markdown_cell_v3(item, fallback="-", max_len=120)
        lines.append(f"- {label}")
    return lines if lines else ["- 暂无数据"]


def render_report_from_draft_custom_v1(session: dict, draft: dict, quality_meta: dict) -> str:
    topic = session.get("topic", "未命名项目")
    temporal_fields = build_report_temporal_fields(datetime.now())
    report_cfg = (session.get("scenario_config", {}) or {}).get("report", {})
    if not isinstance(report_cfg, dict):
        report_cfg = {}
    custom_schema, _schema_issues = normalize_custom_report_schema(
        report_cfg.get("schema"),
        fallback_sections=report_cfg.get("sections"),
    )

    needs = draft.get("needs", []) if isinstance(draft.get("needs", []), list) else []
    actions = draft.get("actions", []) if isinstance(draft.get("actions", []), list) else []
    risks = draft.get("risks", []) if isinstance(draft.get("risks", []), list) else []
    analysis = draft.get("analysis", {}) if isinstance(draft.get("analysis", {}), dict) else {}
    visuals = draft.get("visualizations", {}) if isinstance(draft.get("visualizations", {}), dict) else {}

    generated_visuals = {
        "visualizations.priority_quadrant_mermaid": _build_priority_matrix_mermaid_for_custom_v3(needs),
        "visualizations.business_flow_mermaid": _build_business_flow_mermaid_from_data_v3(needs, actions, risks),
        "visualizations.demand_pie_mermaid": _build_demand_pie_mermaid_from_data_v3(needs),
        "visualizations.architecture_mermaid": _build_architecture_mermaid_from_data_v3(analysis, actions, risks),
    }

    lines = [
        f"# {topic} 访谈报告",
        "",
        f"**访谈日期**: {temporal_fields['interview_date']}",
        f"**生成日期**: {temporal_fields['generated_datetime_cn']}",
        f"**报告编号**: {temporal_fields['report_id']}",
        "",
        "---",
        "",
    ]

    for idx, section in enumerate(custom_schema.get("sections", []), 1):
        if not isinstance(section, dict):
            continue
        title = str(section.get("title", "") or section.get("section_id", f"章节{idx}")).strip()
        source = str(section.get("source", "overview")).strip()
        component = str(section.get("component", "paragraph")).strip().lower()
        if not title:
            title = f"章节 {idx}"

        lines.append(f"## {idx}. {title}")
        lines.append("")

        if component == "paragraph":
            if source == "priority_list":
                lines.extend(_render_priority_table_from_needs_v3(needs))
            elif source == "priority_matrix":
                lines.append("```mermaid")
                lines.append(generated_visuals["visualizations.priority_quadrant_mermaid"])
                lines.append("```")
            else:
                value = resolve_custom_report_source_value_v3(draft, source)
                if isinstance(value, list):
                    if value and isinstance(value[0], dict):
                        excerpt = "；".join(
                            _normalize_markdown_cell_v3(
                                item.get("name") or item.get("title") or item.get("risk") or item.get("action") or item.get("question") or item.get("claim") or "",
                                fallback="-",
                                max_len=50,
                            )
                            for item in value[:4] if isinstance(item, dict)
                        )
                        lines.append(excerpt or "暂无数据。")
                    else:
                        lines.append("；".join(_normalize_markdown_cell_v3(item, fallback="-", max_len=50) for item in value[:6]) or "暂无数据。")
                else:
                    lines.append(_normalize_markdown_cell_v3(value, fallback="暂无数据。", max_len=3000))
        elif component == "table":
            lines.extend(_render_custom_table_from_source_v3(source, draft))
        elif component == "mermaid":
            mermaid_value = ""
            if source == "priority_matrix":
                mermaid_value = generated_visuals["visualizations.priority_quadrant_mermaid"]
            elif source.startswith("visualizations."):
                mermaid_value = str(resolve_custom_report_source_value_v3(draft, source) or "").strip()
                if not mermaid_value:
                    mermaid_value = generated_visuals.get(source, "")
            else:
                mermaid_value = str(resolve_custom_report_source_value_v3(draft, source) or "").strip()
            mermaid_value = mermaid_value or generated_visuals.get("visualizations.business_flow_mermaid", "")
            if source in {"visualizations.business_flow_mermaid", "visualizations.architecture_mermaid"}:
                mermaid_value = ensure_flowchart_semantic_styles(mermaid_value)
            lines.append("```mermaid")
            lines.append(mermaid_value)
            lines.append("```")
        else:
            lines.extend(_render_custom_list_from_source_v3(source, draft))

        lines.append("")

    lines.extend([
        "*此报告由 Deep Vision 深瞳生成*",
        "",
    ])
    return "\n".join(lines)


def render_report_from_draft_assessment_v1(session: dict, draft: dict, quality_meta: dict) -> str:
    topic = session.get("topic", "候选人评估")
    temporal_fields = build_report_temporal_fields(datetime.now())
    scenario_cfg = session.get("scenario_config", {}) if isinstance(session.get("scenario_config", {}), dict) else {}
    assessment_cfg = scenario_cfg.get("assessment", {}) if isinstance(scenario_cfg.get("assessment", {}), dict) else {}
    dim_cfgs = scenario_cfg.get("dimensions", []) if isinstance(scenario_cfg.get("dimensions", []), list) else []
    dim_states = session.get("dimensions", {}) if isinstance(session.get("dimensions", {}), dict) else {}

    score_rows = []
    total_weighted = 0.0
    total_weight = 0.0
    for dim in dim_cfgs:
        if not isinstance(dim, dict):
            continue
        dim_id = str(dim.get("id", "")).strip()
        dim_name = str(dim.get("name", dim_id)).strip() or dim_id
        weight = _safe_float(dim.get("weight", 0.25), 0.25)
        state = dim_states.get(dim_id, {}) if isinstance(dim_states.get(dim_id, {}), dict) else {}
        score = _safe_float(state.get("score"), 0.0)
        if score <= 0:
            # 兼容未打分场景：给出中性分，避免整页空白。
            score = 3.0
        total_weighted += score * weight
        total_weight += weight
        score_rows.append({
            "id": dim_id,
            "name": dim_name,
            "weight": max(0.0, weight),
            "score": max(0.0, min(5.0, score)),
        })

    if not score_rows:
        score_rows = [
            {"id": "overall", "name": "综合表现", "weight": 1.0, "score": 3.0},
        ]
        total_weighted = 3.0
        total_weight = 1.0

    final_score = round(total_weighted / total_weight, 2) if total_weight > 0 else 0.0
    levels = assessment_cfg.get("recommendation_levels", []) if isinstance(assessment_cfg.get("recommendation_levels", []), list) else []
    levels_sorted = sorted([item for item in levels if isinstance(item, dict)], key=lambda item: _safe_float(item.get("threshold", 0), 0), reverse=True)
    recommendation = {"level": "C", "name": "待定", "description": "建议补充评估后决策"}
    for level in levels_sorted:
        if final_score >= _safe_float(level.get("threshold", 0), 0):
            recommendation = {
                "level": str(level.get("level", "C")),
                "name": str(level.get("name", "待定")),
                "description": str(level.get("description", "")).strip(),
            }
            break

    score_table = [
        "| 维度 | 得分 | 权重 | 加权得分 |",
        "|:---|:---:|:---:|:---:|",
    ]
    for row in score_rows:
        weighted = round(row["score"] * row["weight"], 2)
        score_table.append(
            f"| {_normalize_markdown_cell_v3(row['name'], fallback='维度')} | "
            f"{row['score']:.2f} | {row['weight']*100:.0f}% | {weighted:.2f} |"
        )
    score_table.append(f"| **综合得分** | **{final_score:.2f}** | 100% | **{final_score:.2f}** |")

    radar_labels = ", ".join(f'"{_normalize_mermaid_label_v3(row["name"], fallback=f"维度{idx+1}", max_len=12)}"' for idx, row in enumerate(score_rows))
    radar_values = ", ".join(f"{row['score']:.2f}" for row in score_rows)
    radar_mermaid = "\n".join([
        "xychart-beta",
        '    title "能力评分分布"',
        f"    x-axis [{radar_labels}]",
        '    y-axis "得分" 0 --> 5',
        f"    bar [{radar_values}]",
    ])

    needs = draft.get("needs", []) if isinstance(draft.get("needs", []), list) else []
    risks = draft.get("risks", []) if isinstance(draft.get("risks", []), list) else []
    actions = draft.get("actions", []) if isinstance(draft.get("actions", []), list) else []
    open_questions = draft.get("open_questions", []) if isinstance(draft.get("open_questions", []), list) else []
    analysis = draft.get("analysis", {}) if isinstance(draft.get("analysis", {}), dict) else {}

    strengths = []
    for item in needs[:3]:
        if isinstance(item, dict):
            strengths.append(f"- {_normalize_markdown_cell_v3(item.get('name', ''), fallback='能力亮点')}：{_normalize_markdown_cell_v3(item.get('description', ''), fallback='-')}")
    if not strengths:
        strengths = ["- 暂无显著优势提炼，请补充评估证据。"]

    weaknesses = []
    for item in risks[:3]:
        if isinstance(item, dict):
            weaknesses.append(f"- {_normalize_markdown_cell_v3(item.get('risk', ''), fallback='待提升项')}：{_normalize_markdown_cell_v3(item.get('impact', ''), fallback='-')}")
    if not weaknesses:
        weaknesses = ["- 暂无明确风险项，建议补充压力场景追问。"]

    actions_table = _render_custom_table_from_source_v3("actions", {"actions": actions})
    open_questions_table = _render_custom_table_from_source_v3("open_questions", {"open_questions": open_questions})

    lines = [
        f"# {topic} 面试评估报告",
        "",
        f"**评估日期**: {temporal_fields['interview_date']}",
        f"**生成日期**: {temporal_fields['generated_datetime_cn']}",
        f"**报告编号**: {temporal_fields['report_id']}",
        "",
        "---",
        "",
        "## 1. 候选人概览",
        "",
        _normalize_markdown_cell_v3(draft.get("overview", "暂无候选人概览。"), fallback="暂无候选人概览。", max_len=3000),
        "",
        f"- 综合得分：**{final_score:.2f}/5.00**",
        f"- 推荐等级：**{recommendation.get('name', '待定')}（{recommendation.get('level', 'C')}）**",
        "",
        "## 2. 能力得分总览",
        "",
        *score_table,
        "",
        "## 3. 能力分布图",
        "",
        "```mermaid",
        radar_mermaid,
        "```",
        "",
        "## 4. 维度分析",
        "",
        "### 4.1 优势能力分析",
        _normalize_markdown_cell_v3(analysis.get("customer_needs", "暂无分析。"), fallback="暂无分析。", max_len=2000),
        "",
        "### 4.2 思维与结构分析",
        _normalize_markdown_cell_v3(analysis.get("business_flow", "暂无分析。"), fallback="暂无分析。", max_len=2000),
        "",
        "### 4.3 经验边界与风险意识",
        _normalize_markdown_cell_v3(analysis.get("tech_constraints", "暂无分析。"), fallback="暂无分析。", max_len=2000),
        "",
        "### 4.4 岗位匹配与协作约束",
        _normalize_markdown_cell_v3(analysis.get("project_constraints", "暂无分析。"), fallback="暂无分析。", max_len=2000),
        "",
        "## 5. 核心优势",
        "",
        *strengths,
        "",
        "## 6. 待提升领域",
        "",
        *weaknesses,
        "",
        "## 7. 推荐意见",
        "",
        f"- 推荐等级：**{recommendation.get('name', '待定')}（{recommendation.get('level', 'C')}）**",
        f"- 结论说明：{_normalize_markdown_cell_v3(recommendation.get('description', '') or '建议结合后续补面结果进行决策。', fallback='建议结合后续补面结果进行决策。', max_len=800)}",
        "",
        "## 8. 后续跟进计划",
        "",
        "### 8.1 行动计划",
        "",
        *actions_table,
        "",
        "### 8.2 补充评估问题",
        "",
        *open_questions_table,
        "",
        "*此报告由 Deep Vision 深瞳生成*",
        "",
    ]
    return "\n".join(lines)


def render_report_from_draft_v3(session: dict, draft: dict, quality_meta: dict) -> str:
    """将 V3 结构化草案渲染为 Markdown 报告。"""
    template_name = resolve_report_template_for_session(session)
    if template_name == REPORT_TEMPLATE_ASSESSMENT_V1:
        return render_report_from_draft_assessment_v1(session, draft, quality_meta)
    if template_name == REPORT_TEMPLATE_CUSTOM_V1:
        return render_report_from_draft_custom_v1(session, draft, quality_meta)

    topic = session.get("topic", "未命名项目")
    now = datetime.now()
    temporal_fields = build_report_temporal_fields(now)
    report_id = temporal_fields["report_id"]

    needs = draft.get("needs", []) if isinstance(draft.get("needs", []), list) else []
    solutions = draft.get("solutions", []) if isinstance(draft.get("solutions", []), list) else []
    risks = draft.get("risks", []) if isinstance(draft.get("risks", []), list) else []
    actions = draft.get("actions", []) if isinstance(draft.get("actions", []), list) else []
    open_questions = draft.get("open_questions", []) if isinstance(draft.get("open_questions", []), list) else []
    analysis = draft.get("analysis", {}) if isinstance(draft.get("analysis", {}), dict) else {}
    visuals = draft.get("visualizations", {}) if isinstance(draft.get("visualizations", {}), dict) else {}

    def clean_mermaid(raw_value: str, fallback: str) -> str:
        value = str(raw_value or "").replace("```mermaid", "").replace("```", "").strip()
        return value or fallback

    def clamp_score(value: float) -> float:
        return max(0.05, min(0.95, value))

    def format_refs(item: dict) -> str:
        refs = _normalize_evidence_refs(item.get("evidence_refs", []))
        if not refs:
            return "-"
        return "、".join(refs[:6])

    def build_priority_matrix_for_needs(needs_items: list) -> tuple[str, list]:
        """构建优先级矩阵 Mermaid 及图例中的数据点说明。"""
        if not needs_items:
            fallback_matrix = """quadrantChart
    title 优先级矩阵
    x-axis 紧急程度（左低） --> 紧急程度（右高）
    y-axis 重要程度（下低） --> 重要程度（上高）
    quadrant-1 立即执行
    quadrant-2 计划执行
    quadrant-3 低优先级
    quadrant-4 可委派
    Req1: [0.78, 0.82]
    Req2: [0.62, 0.72]
    Req3: [0.36, 0.32]"""
            return fallback_matrix, []

        priority_anchor = {
            "P0": (0.84, 0.88),  # 右上：立即执行
            "P1": (0.66, 0.74),  # 偏上：计划执行
            "P2": (0.72, 0.40),  # 右下：可委派
            "P3": (0.34, 0.30),  # 左下：低优先级
        }

        point_lines = []
        point_legend = []
        for index, item in enumerate(needs_items[:10], 1):
            priority = str(item.get("priority", "P1")).upper()
            if priority not in priority_anchor:
                priority = "P1"
            base_x, base_y = priority_anchor[priority]
            spread = ((index % 4) - 1.5) * 0.03
            x = clamp_score(base_x + spread)
            y = clamp_score(base_y - spread * 0.7)
            point_lines.append(f"    Req{index}: [{x:.2f}, {y:.2f}]")

            name = _normalize_markdown_cell_v3(item.get("name", ""), fallback=f"需求{index}", max_len=28)
            point_legend.append(f"- `Req{index}` = {name}")

        matrix = "\n".join([
            "quadrantChart",
            "    title 优先级矩阵",
            "    x-axis 紧急程度（左低） --> 紧急程度（右高）",
            "    y-axis 重要程度（下低） --> 重要程度（上高）",
            "    quadrant-1 立即执行",
            "    quadrant-2 计划执行",
            "    quadrant-3 低优先级",
            "    quadrant-4 可委派",
            *point_lines,
        ])
        return matrix, point_legend

    generated_priority_quadrant_mermaid, priority_point_legend = build_priority_matrix_for_needs(needs)

    if REPORT_V3_RENDER_MERMAID_FROM_DATA:
        priority_quadrant_mermaid = generated_priority_quadrant_mermaid
        flow_mermaid = _build_business_flow_mermaid_from_data_v3(needs, actions, risks)
        pie_mermaid = _build_demand_pie_mermaid_from_data_v3(needs)
        architecture_mermaid = _build_architecture_mermaid_from_data_v3(analysis, actions, risks)
    else:
        priority_quadrant_mermaid = clean_mermaid(visuals.get("priority_quadrant_mermaid", ""), "") or generated_priority_quadrant_mermaid
        flow_mermaid = clean_mermaid(
            visuals.get("business_flow_mermaid", ""),
            _build_business_flow_mermaid_from_data_v3(needs, actions, risks),
        )
        pie_mermaid = clean_mermaid(
            visuals.get("demand_pie_mermaid", ""),
            _build_demand_pie_mermaid_from_data_v3(needs),
        )
        architecture_mermaid = clean_mermaid(
            visuals.get("architecture_mermaid", ""),
            _build_architecture_mermaid_from_data_v3(analysis, actions, risks),
        )

    flow_mermaid = ensure_flowchart_semantic_styles(flow_mermaid)
    architecture_mermaid = ensure_flowchart_semantic_styles(architecture_mermaid)

    needs_table = [
        "| 编号 | 优先级 | 需求项 | 描述 | 证据 |",
        "|:---:|:---:|:---|:---|:---|",
    ]
    if needs:
        for idx, item in enumerate(needs, 1):
            needs_table.append(
                "| "
                f"{idx} | "
                f"{_normalize_markdown_cell_v3(item.get('priority', 'P1'), fallback='P1', max_len=8)} | "
                f"{_normalize_markdown_cell_v3(item.get('name', ''))} | "
                f"{_normalize_markdown_cell_v3(item.get('description', ''))} | "
                f"{_normalize_markdown_cell_v3(format_refs(item), max_len=30)} |"
            )
    else:
        needs_table.append("| - | - | 暂无结构化核心需求 | - | - |")

    priority_group = {"P0": [], "P1": [], "P2": [], "P3": []}
    for item in needs:
        if not isinstance(item, dict):
            continue
        priority = str(item.get("priority", "P1")).upper()
        priority = priority if priority in priority_group else "P1"
        priority_group[priority].append(_normalize_markdown_cell_v3(item.get("name", "未命名需求"), max_len=28))

    priority_table = [
        "| 优先级 | 需求项 | 说明 |",
        "|:---:|:---|:---|",
        f"| 🔴 P0 立即执行 | {'、'.join(priority_group['P0']) if priority_group['P0'] else '-'} | 重要且紧急，需优先投入 |",
        f"| 🟡 P1 计划执行 | {'、'.join(priority_group['P1']) if priority_group['P1'] else '-'} | 重要但可分阶段推进 |",
        f"| 🟢 P2 可委派 | {'、'.join(priority_group['P2']) if priority_group['P2'] else '-'} | 影响有限，可并行安排 |",
        f"| ⚪ P3 低优先级 | {'、'.join(priority_group['P3']) if priority_group['P3'] else '-'} | 可延后处理并持续观察 |",
    ]

    solutions_table = [
        "| 编号 | 方案建议 | 说明 | Owner | 时间计划 | 验收指标 | 证据 |",
        "|:---:|:---|:---|:---|:---|:---|:---|",
    ]
    if solutions:
        for idx, item in enumerate(solutions, 1):
            solutions_table.append(
                "| "
                f"{idx} | "
                f"{_normalize_markdown_cell_v3(item.get('title', ''))} | "
                f"{_normalize_markdown_cell_v3(item.get('description', ''))} | "
                f"{_normalize_markdown_cell_v3(item.get('owner', '待定'), max_len=20)} | "
                f"{_normalize_markdown_cell_v3(item.get('timeline', '待定'), max_len=24)} | "
                f"{_normalize_markdown_cell_v3(item.get('metric', '待定'), max_len=30)} | "
                f"{_normalize_markdown_cell_v3(format_refs(item), max_len=30)} |"
            )
    else:
        solutions_table.append("| - | 暂无结构化方案建议 | - | - | - | - | - |")

    risks_table = [
        "| 编号 | 风险项 | 影响 | 缓解措施 | 证据 |",
        "|:---:|:---|:---|:---|:---|",
    ]
    if risks:
        for idx, item in enumerate(risks, 1):
            risks_table.append(
                "| "
                f"{idx} | "
                f"{_normalize_markdown_cell_v3(item.get('risk', ''))} | "
                f"{_normalize_markdown_cell_v3(item.get('impact', ''), max_len=40)} | "
                f"{_normalize_markdown_cell_v3(item.get('mitigation', ''), max_len=48)} | "
                f"{_normalize_markdown_cell_v3(format_refs(item), max_len=30)} |"
            )
    else:
        risks_table.append("| - | 暂无结构化风险项 | - | - | - |")

    actions_table = [
        "| 编号 | 行动项 | Owner | 时间计划 | 验收指标 | 证据 |",
        "|:---:|:---|:---|:---|:---|:---|",
    ]
    if actions:
        for idx, item in enumerate(actions, 1):
            actions_table.append(
                "| "
                f"{idx} | "
                f"{_normalize_markdown_cell_v3(item.get('action', ''))} | "
                f"{_normalize_markdown_cell_v3(item.get('owner', '待定'), max_len=20)} | "
                f"{_normalize_markdown_cell_v3(item.get('timeline', '待定'), max_len=24)} | "
                f"{_normalize_markdown_cell_v3(item.get('metric', '待定'), max_len=30)} | "
                f"{_normalize_markdown_cell_v3(format_refs(item), max_len=30)} |"
            )
    else:
        actions_table.append("| - | 暂无结构化下一步行动 | - | - | - | - |")

    open_questions_table = [
        "| 编号 | 未决问题 | 原因 | 影响 | 建议补问 | 证据 |",
        "|:---:|:---|:---|:---|:---|:---|",
    ]
    if open_questions:
        for idx, item in enumerate(open_questions, 1):
            open_questions_table.append(
                "| "
                f"{idx} | "
                f"{_normalize_markdown_cell_v3(item.get('question', ''))} | "
                f"{_normalize_markdown_cell_v3(item.get('reason', ''), max_len=36)} | "
                f"{_normalize_markdown_cell_v3(item.get('impact', ''), max_len=36)} | "
                f"{_normalize_markdown_cell_v3(item.get('suggested_follow_up', ''), max_len=42)} | "
                f"{_normalize_markdown_cell_v3(format_refs(item), max_len=30)} |"
            )
    else:
        open_questions_table.append("| - | 暂无未决问题 | - | - | - | - |")

    lines = [
        f"# {topic} 访谈报告",
        "",
        f"**访谈日期**: {temporal_fields['interview_date']}",
        f"**生成日期**: {temporal_fields['generated_datetime_cn']}",
        f"**报告编号**: {report_id}",
        "",
        "---",
        "",
        "## 1. 访谈概述",
        "",
        "### 1.1 执行摘要",
        _normalize_markdown_cell_v3(draft.get("overview", "暂无概述信息。"), fallback="暂无概述信息。", max_len=3000),
        "",
        "## 2. 需求摘要",
        "",
        "### 2.1 核心需求列表（表格）",
        "",
        *needs_table,
        "",
        "### 2.2 优先级矩阵（Mermaid）",
        "",
        "```mermaid",
        priority_quadrant_mermaid,
        "```",
        "",
        "### 2.3 图例说明",
        "",
        "- 横轴：紧急程度（左低右高）",
        "- 纵轴：重要程度（下低上高）",
        "- 右上：立即执行（重要且紧急）",
        "- 左上：计划执行（重要但不紧急）",
        "- 右下：可委派（紧急但不重要）",
        "- 左下：低优先级（不重要不紧急）",
        "- 数据点对应关系：",
        *(priority_point_legend if priority_point_legend else ["- 本次无可映射的需求点"]),
        "",
        "### 2.4 优先级清单（表格）",
        "",
        *priority_table,
        "",
        "## 3. 详细需求分析",
        "",
        "### 3.1 客户/用户需求",
        _normalize_markdown_cell_v3(analysis.get("customer_needs", "暂无分析。"), fallback="暂无分析。", max_len=2000),
        "",
        "### 3.2 业务流程",
        _normalize_markdown_cell_v3(analysis.get("business_flow", "暂无分析。"), fallback="暂无分析。", max_len=2000),
        "",
        "### 3.3 技术约束",
        _normalize_markdown_cell_v3(analysis.get("tech_constraints", "暂无分析。"), fallback="暂无分析。", max_len=2000),
        "",
        "### 3.4 项目约束",
        _normalize_markdown_cell_v3(analysis.get("project_constraints", "暂无分析。"), fallback="暂无分析。", max_len=2000),
        "",
        "## 4. 可视化分析",
        "",
        "### 4.1 业务流程图",
        "```mermaid",
        flow_mermaid,
        "```",
        "",
        "### 4.2 需求分类饼图",
        "```mermaid",
        pie_mermaid,
        "```",
        "",
        "### 4.3 部署架构图",
        "```mermaid",
        architecture_mermaid,
        "```",
        "",
        "## 5. 方案建议",
        "",
        "### 5.1 建议清单（表格）",
        "",
        *solutions_table,
        "",
        "## 6. 风险评估",
        "",
        "### 6.1 风险清单（表格）",
        "",
        *risks_table,
        "",
        "## 7. 下一步行动",
        "",
        "### 7.1 行动计划（表格）",
        "",
        *actions_table,
        "",
        "### 7.2 未决问题（表格）",
        "",
        *open_questions_table,
        "",
        "*此报告由 Deep Vision 深瞳生成*",
        "",
    ]

    return "\n".join(lines)


def compute_adaptive_report_timeout(base_timeout: float, prompt_length: int, timeout_cap: Optional[float] = None) -> float:
    """按 Prompt 长度动态调整报告调用超时，长上下文适当放宽，短上下文保持收敛。"""
    normalized_base = max(30.0, float(base_timeout or REPORT_API_TIMEOUT))
    length = max(0, int(prompt_length or 0))

    extra = 0.0
    if length >= 12000:
        extra = 45.0
    elif length >= 9000:
        extra = 30.0
    elif length >= 7000:
        extra = 18.0
    elif length >= 5000:
        extra = 10.0

    cap = float(timeout_cap if timeout_cap is not None else max(REPORT_API_TIMEOUT, normalized_base))
    cap = max(normalized_base, cap)
    return max(30.0, min(cap, normalized_base + extra))


def compute_adaptive_report_tokens(base_tokens: int, prompt_length: int, floor_tokens: int = 2200) -> int:
    """按 Prompt 长度动态收敛草案 token 上限，降低长上下文的超时风险。"""
    normalized_base = max(int(floor_tokens), int(base_tokens or floor_tokens))
    length = max(0, int(prompt_length or 0))

    ratio = 1.0
    if length >= 12000:
        ratio = 0.78
    elif length >= 9000:
        ratio = 0.86
    elif length >= 7000:
        ratio = 0.92

    adjusted = int(normalized_base * ratio)
    return max(int(floor_tokens), min(int(MAX_TOKENS_REPORT), adjusted))


def generate_report_v3_pipeline(
    session: dict,
    session_id: Optional[str] = None,
    preferred_lane: str = "",
    call_type_suffix: str = "",
    report_profile: str = "",
    ) -> Optional[dict]:
    """执行 V3 报告生成流水线。失败时返回包含 reason 的调试结构。"""
    try:
        runtime_cfg = get_report_v3_runtime_config(report_profile)
        runtime_profile = runtime_cfg["profile"]
        pipeline_lane = str(preferred_lane or "report").strip().lower() or "report"
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

        evidence_pack = build_report_evidence_pack(session)

        if session_id:
            update_report_generation_status(session_id, "building_prompt", message="正在构建证据包并生成结构化草案...")

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
            current_max_tokens = max(2800, int(report_draft_max_tokens * (0.82 ** attempt_index)))
            current_call_type = "report_v3_draft" if is_first_attempt else f"report_v3_draft_retry_{round_no}"
            current_call_type = f"{current_call_type}{call_type_suffix}"

            if session_id and not is_first_attempt:
                update_report_generation_status(
                    session_id,
                    "generating",
                    message=f"草案生成失败，正在降载重试（第{round_no}/{draft_attempt_total}轮）...",
                )

            draft_prompt = build_report_draft_prompt_v3(
                session,
                evidence_pack,
                facts_limit=current_facts_limit,
                contradiction_limit=current_contradiction_limit,
                unknown_limit=current_unknown_limit,
                blindspot_limit=current_blindspot_limit,
            )
            current_prompt_length = len(draft_prompt)
            current_max_tokens = compute_adaptive_report_tokens(current_max_tokens, current_prompt_length, floor_tokens=2200)
            current_timeout = compute_adaptive_report_timeout(
                runtime_cfg["draft_timeout"],
                current_prompt_length,
                timeout_cap=max(REPORT_API_TIMEOUT, runtime_cfg["draft_timeout"] + 45),
            )
            draft_lane_candidates = [draft_phase_lane]
            alternate_draft_lane = resolve_report_v3_alternate_lane(draft_phase_lane)
            if alternate_draft_lane:
                draft_lane_candidates.append(alternate_draft_lane)

            for lane_index, candidate_lane in enumerate(draft_lane_candidates):
                lane_call_type = current_call_type if lane_index == 0 else f"{current_call_type}_fallback_{candidate_lane}"
                lane_model = resolve_model_name_for_lane(call_type="report_v3_draft", selected_lane=candidate_lane)
                draft_raw = call_claude(
                    draft_prompt,
                    max_tokens=current_max_tokens,
                    call_type=lane_call_type,
                    timeout=current_timeout,
                    preferred_lane=candidate_lane,
                )

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
            }

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

        for review_round in range(total_round_budget):
            review_round_no = review_round + 1
            last_review_round_no = review_round_no
            if session_id:
                update_report_generation_status(
                    session_id,
                    "generating",
                    message=f"正在执行报告一致性审稿（第{review_round_no}/{total_round_budget}轮）..."
                )

            review_prompt = build_report_review_prompt_v3(session, evidence_pack, current_draft, review_issues)
            review_prompt_length = len(review_prompt)
            review_max_tokens = compute_adaptive_report_tokens(
                report_review_max_tokens,
                review_prompt_length,
                floor_tokens=2400,
            )
            review_timeout = compute_adaptive_report_timeout(
                REPORT_API_TIMEOUT,
                review_prompt_length,
                timeout_cap=max(REPORT_API_TIMEOUT, runtime_cfg["draft_timeout"] + 60),
            )
            review_raw = call_claude(
                review_prompt,
                max_tokens=review_max_tokens,
                call_type=f"report_v3_review_round_{review_round + 1}{call_type_suffix}",
                timeout=review_timeout,
                preferred_lane=review_phase_lane,
            )
            if not review_raw:
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
                }

            review_parse_meta = {}
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
            if not review_parsed:
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
                    "raw_excerpt": str(review_raw or "")[:360],
                    "repair_applied": bool(review_parse_meta.get("repair_applied", False)),
                    "draft_snapshot": current_draft if isinstance(current_draft, dict) else {},
                    "parse_meta": {
                        "candidate_count": int(review_parse_meta.get("candidate_count", 0) or 0),
                        "parse_attempts": int(review_parse_meta.get("parse_attempts", 0) or 0),
                        "selected_source": str(review_parse_meta.get("selected_source", "") or ""),
                        "missing_keys": list(review_parse_meta.get("missing_keys", []) or []),
                        "last_error": str(review_parse_meta.get("last_error", "") or ""),
                    },
                    "evidence_pack": evidence_pack,
                    "review_issues": final_issues,
                }

            if isinstance(review_parsed.get("revised_draft"), dict):
                current_draft = merge_report_draft_patch_v3(current_draft, review_parsed["revised_draft"])

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
                quality_gate_start = _time.perf_counter()
                quality_meta = compute_report_quality_meta_v3(current_draft, evidence_pack, final_issues)
                if isinstance(quality_meta, dict):
                    quality_meta["runtime_profile"] = runtime_profile
                quality_gate_issues = build_quality_gate_issues_v3(quality_meta)
                quality_gate_elapsed = _time.perf_counter() - quality_gate_start
                if quality_gate_issues:
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
                        break
                    remaining_quality_fix_rounds -= 1
                    review_issues = quality_gate_issues
                    continue
                record_pipeline_stage_metric(
                    stage="quality_gate",
                    success=True,
                    elapsed_seconds=quality_gate_elapsed,
                    lane=review_phase_lane,
                    model=review_phase_model,
                    error_msg="",
                )

                # quality 档可配置要求至少执行 N 轮审稿，避免“一轮即停”导致表述粗糙。
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
                    continue

                report_content = render_report_from_draft_v3(session, current_draft, quality_meta)
                return {
                    "status": "success",
                    "profile": runtime_profile,
                    "report_content": report_content,
                    "quality_meta": quality_meta,
                    "evidence_pack": evidence_pack,
                    "review_issues": final_issues,
                    "phase_lanes": phase_lanes,
                    "review_rounds_executed": review_round_no,
                    "min_required_review_rounds": min_required_review_rounds,
                }

            review_issues = merged_issues
            last_failed_stage = "review_gate"

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
        }
    except Exception as e:
        if ENABLE_DEBUG_LOG:
            print(f"⚠️ V3 报告流程失败: {summarize_error_for_log(e, limit=260)}")
        return {
            "status": "failed",
            "reason": "exception",
            "error": summarize_error_for_log(e, limit=200),
            "parse_stage": "exception",
            "profile": normalize_report_profile_choice(report_profile, fallback=REPORT_V3_PROFILE),
            "lane": str(preferred_lane or "report").strip().lower() or "report",
            "phase_lanes": {
                "draft": resolve_report_v3_phase_lane("draft", pipeline_lane=str(preferred_lane or "report").strip().lower() or "report"),
                "review": resolve_report_v3_phase_lane("review", pipeline_lane=str(preferred_lane or "report").strip().lower() or "report"),
            },
            "raw_excerpt": "",
            "repair_applied": False,
            "evidence_pack": {},
            "review_issues": [],
        }


async def call_claude_async(prompt: str, max_tokens: int = None,
                            call_type: str = "async", model_name: str = "",
                            preferred_lane: str = "") -> Optional[str]:
    """异步调用 Claude API，带超时控制"""
    client = resolve_ai_client(call_type=call_type, model_name=model_name, preferred_lane=preferred_lane)
    if not client:
        return None

    if max_tokens is None:
        max_tokens = MAX_TOKENS_DEFAULT
    effective_model = resolve_model_name(call_type=call_type, model_name=model_name)

    try:
        if ENABLE_DEBUG_LOG:
            print(f"🤖 异步调用 Claude API，model={effective_model}，max_tokens={max_tokens}，timeout={API_TIMEOUT}s")

        # 使用配置的超时时间
        with ai_call_priority_slot(call_type):
            message = client.messages.create(
                model=effective_model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
                timeout=API_TIMEOUT
            )

        response_text = extract_message_text(message)
        if not response_text:
            raise ValueError("模型响应中未包含可用文本内容")

        if ENABLE_DEBUG_LOG:
            print(f"✅ API 异步响应成功，长度: {len(response_text)} 字符")

        return response_text
    except Exception as e:
        raw_error_msg = str(e)
        error_msg = summarize_error_for_log(raw_error_msg, limit=280)
        print(f"❌ Claude API 异步调用失败: {error_msg}")

        lower_error = raw_error_msg.lower()
        if "timeout" in lower_error:
            print(f"   原因: API 调用超时（超过{API_TIMEOUT}秒）")
        elif "rate" in lower_error:
            print(f"   原因: API 请求频率限制")
        elif "authentication" in lower_error or "api key" in lower_error:
            print(f"   原因: API Key 认证失败")

        return None


def describe_image_with_vision(image_path: Path, filename: str) -> str:
    """
    使用智谱视觉模型描述图片内容

    Args:
        image_path: 图片文件路径
        filename: 原始文件名

    Returns:
        str: 图片描述文本
    """
    if not ENABLE_VISION:
        return f"[图片: {filename}] (视觉功能已禁用)"

    if not ZHIPU_API_KEY or ZHIPU_API_KEY == "your-zhipu-api-key-here":
        return f"[图片: {filename}] (视觉 API 未配置)"

    try:
        # 读取图片并转换为 base64
        with open(image_path, "rb") as f:
            image_data = f.read()

        # 检查文件大小
        size_mb = len(image_data) / (1024 * 1024)
        if size_mb > MAX_IMAGE_SIZE_MB:
            return f"[图片: {filename}] (文件过大: {size_mb:.1f}MB > {MAX_IMAGE_SIZE_MB}MB)"

        # 确定 MIME 类型
        ext = Path(filename).suffix.lower()
        mime_types = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.webp': 'image/webp'
        }
        mime_type = mime_types.get(ext, 'image/jpeg')

        base64_image = base64.b64encode(image_data).decode('utf-8')

        # 构建请求
        headers = {
            "Authorization": f"Bearer {ZHIPU_API_KEY}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": VISION_MODEL_NAME,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": """请详细描述这张图片的内容，包括：
1. 图片的主要内容和主题
2. 图片中的关键元素（人物、物体、文字等）
3. 如果是流程图/架构图/图表，请解读其含义
4. 如果有文字，请提取主要文字内容

请用中文回答，内容尽量完整准确。"""
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            "max_tokens": 1000
        }

        if ENABLE_DEBUG_LOG:
            print(f"🖼️ 调用视觉 API 描述图片: {filename}")

        response = requests.post(
            VISION_API_URL,
            headers=headers,
            json=payload,
            timeout=60
        )

        if response.status_code == 200:
            result = response.json()
            description = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            if description:
                if ENABLE_DEBUG_LOG:
                    print(f"✅ 图片描述生成成功: {len(description)} 字符")
                return f"[图片: {filename}]\n\n**AI 图片描述:**\n{description}"
            else:
                return f"[图片: {filename}] (描述生成失败: 空响应)"
        else:
            try:
                error_msg = response.json().get("error", {}).get("message", response.text[:200])
            except Exception:
                error_msg = response.text[:200]
            compact_error_msg = summarize_error_for_log(error_msg, limit=160)
            if ENABLE_DEBUG_LOG:
                print(f"❌ 视觉 API 调用失败: {compact_error_msg}")
            return f"[图片: {filename}] (API 错误: {compact_error_msg[:100]})"

    except requests.exceptions.Timeout:
        return f"[图片: {filename}] (API 超时)"
    except Exception as e:
        if ENABLE_DEBUG_LOG:
            print(f"❌ 图片描述生成失败: {e}")
        return f"[图片: {filename}] (处理失败: {str(e)[:100]})"


def _build_ai_call_meta(selected_lane: str, effective_model: str, effective_timeout: float, max_tokens: int) -> dict:
    """构造统一的 AI 调用元信息，便于上层记录更细粒度失败原因。"""
    try:
        normalized_timeout = float(effective_timeout)
    except Exception:
        normalized_timeout = float(API_TIMEOUT)
    try:
        normalized_max_tokens = int(max_tokens)
    except Exception:
        normalized_max_tokens = int(MAX_TOKENS_DEFAULT)

    return {
        "success": False,
        "selected_lane": str(selected_lane or ""),
        "model": str(effective_model or ""),
        "timeout_seconds": normalized_timeout,
        "max_tokens": normalized_max_tokens,
        "queue_wait_ms": 0.0,
        "timeout_occurred": False,
        "failure_reason": "",
        "error_kind": "",
        "error_message": "",
        "response_length": 0,
        "empty_text": False,
    }


def _call_claude_internal(prompt: str, max_tokens: int = None, retry_on_timeout: bool = True,
                         call_type: str = "unknown", truncated_docs: list = None,
                         timeout: float = None, model_name: str = "", preferred_lane: str = "",
                         hedge_triggered: bool = False, cache_hit: bool = False) -> tuple[Optional[str], dict]:
    """同步调用 AI 网关，返回文本与执行元信息。"""
    import time

    effective_client, selected_lane, lane_meta = resolve_ai_client_with_lane(
        call_type=call_type,
        model_name=model_name,
        preferred_lane=preferred_lane,
    )

    if max_tokens is None:
        max_tokens = MAX_TOKENS_DEFAULT

    effective_timeout = timeout if timeout is not None else API_TIMEOUT
    effective_model = resolve_model_name_for_lane(
        call_type=call_type,
        model_name=model_name,
        selected_lane=selected_lane,
    )
    call_meta = _build_ai_call_meta(selected_lane, effective_model, effective_timeout, max_tokens)
    if not effective_client:
        call_meta["failure_reason"] = "no_client"
        call_meta["error_kind"] = "no_client"
        call_meta["error_message"] = "未找到可用 AI 客户端"
        return None, call_meta

    generation_stage = resolve_generation_stage(call_type=call_type)
    start_time = time.time()
    success = False
    timeout_occurred = False
    error_message = None
    response_text = None
    queue_wait_ms = 0.0
    skipped_open_lanes = []
    forced_open_lane = ""
    if isinstance(lane_meta, dict):
        skipped_open_lanes = list(lane_meta.get("skipped_open_lanes", []) or [])
        forced_open_lane = str(lane_meta.get("forced_open_lane", "") or "")

    try:
        if ENABLE_DEBUG_LOG:
            print(
                f"🤖 调用 Claude API，lane={selected_lane or 'unknown'}，"
                f"model={effective_model}，max_tokens={max_tokens}，timeout={effective_timeout}s"
            )
            if skipped_open_lanes:
                if forced_open_lane:
                    print(f"⚠️ 熔断告警：候选 lane 处于冷却，临时继续使用 {forced_open_lane}")
                else:
                    print(f"ℹ️ 熔断切换：跳过冷却 lane={','.join(skipped_open_lanes)}")

        with ai_call_priority_slot(call_type) as priority_meta:
            if isinstance(priority_meta, dict):
                try:
                    queue_wait_ms = max(0.0, float(priority_meta.get("queue_wait_ms", 0.0) or 0.0))
                except Exception:
                    queue_wait_ms = 0.0
            message = effective_client.messages.create(
                model=effective_model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
                timeout=effective_timeout
            )

        response_text = extract_message_text(message)
        if not response_text:
            call_meta["empty_text"] = True
            raise ValueError("模型响应中未包含可用文本内容")
        success = True
        record_gateway_lane_success(selected_lane)

        if ENABLE_DEBUG_LOG:
            print(f"✅ API 响应成功，长度: {len(response_text)} 字符")

    except Exception as e:
        raw_error_message = str(e)
        error_message = summarize_error_for_log(raw_error_message, limit=320)
        print(f"❌ Claude API 调用失败: {error_message}")
        error_kind = classify_gateway_failure_kind(raw_error_message)
        lower_error = raw_error_message.lower()
        call_type_lower = str(call_type or "").lower()
        is_report_call = call_type_lower.startswith("report")

        if raw_error_message == "模型响应中未包含可用文本内容":
            call_meta["empty_text"] = True
            call_meta["failure_reason"] = "empty_text"
            if error_kind in {"", "unknown"}:
                error_kind = "empty_text"
        elif "timeout" in lower_error:
            timeout_occurred = True
            call_meta["failure_reason"] = "timeout"
        elif "rate" in lower_error:
            call_meta["failure_reason"] = "rate_limited"
        elif "authentication" in lower_error or "api key" in lower_error:
            call_meta["failure_reason"] = "auth_error"
        else:
            call_meta["failure_reason"] = "gateway_error"

        call_meta["error_kind"] = str(error_kind or "")
        call_meta["error_message"] = str(error_message or "")

        circuit_meta = record_gateway_lane_failure(selected_lane, error_kind)
        if circuit_meta.get("circuit_opened"):
            cooldown_seconds = int(round(float(circuit_meta.get("cooldown_remaining_seconds", 0.0) or 0.0)))
            cooldown_seconds = max(1, cooldown_seconds)
            print(
                f"⚠️ 网关熔断触发: lane={selected_lane}, "
                f"error={error_kind}, cooldown={cooldown_seconds}s"
            )

        if "timeout" in lower_error:
            timeout_occurred = True
            print(f"   原因: API 调用超时（超过{effective_timeout}秒）")

            should_retry_with_shrink = retry_on_timeout and len(prompt) > 5000 and not is_report_call
            if should_retry_with_shrink:
                print(f"   🔄 尝试容错重试：截断 prompt 后重试...")
                truncated_prompt = prompt[:int(len(prompt) * 0.7)]
                truncated_prompt += "\n\n[注意：由于内容过长，部分上下文已被截断，请基于已有信息进行回答]"

                retry_max_tokens = max_tokens
                retry_timeout = effective_timeout
                if is_report_call:
                    retry_max_tokens = max(3000, int(max_tokens * 0.65))
                    retry_timeout = max(effective_timeout, REPORT_API_TIMEOUT)
                else:
                    retry_max_tokens = max(1000, int(max_tokens * 0.8))

                response_text = call_claude(
                    truncated_prompt, retry_max_tokens,
                    retry_on_timeout=False,
                    call_type=call_type + "_retry",
                    truncated_docs=truncated_docs,
                    timeout=retry_timeout,
                    model_name=effective_model,
                    preferred_lane=preferred_lane,
                    hedge_triggered=hedge_triggered,
                    cache_hit=cache_hit,
                )

                if response_text:
                    success = True

        elif raw_error_message == "模型响应中未包含可用文本内容":
            print("   原因: 模型返回空文本，或仅返回了非 text 内容块")
        elif "rate" in lower_error:
            print(f"   原因: API 请求频率限制")
        elif "authentication" in lower_error or "api key" in lower_error:
            print(f"   原因: API Key 认证失败")

    finally:
        call_meta["success"] = bool(success and response_text)
        call_meta["timeout_occurred"] = bool(timeout_occurred)
        call_meta["queue_wait_ms"] = round(queue_wait_ms, 2)
        if response_text:
            call_meta["response_length"] = len(response_text)
        if call_meta["success"]:
            call_meta["failure_reason"] = ""
            call_meta["error_kind"] = ""
            call_meta["error_message"] = ""
            call_meta["empty_text"] = False

        response_time = time.time() - start_time
        metrics_collector.record_api_call(
            call_type=call_type,
            prompt_length=len(prompt),
            response_time=response_time,
            success=success,
            timeout=timeout_occurred,
            error_msg=error_message if not success else None,
            truncated_docs=truncated_docs,
            max_tokens=max_tokens,
            queue_wait_ms=queue_wait_ms,
            hedge_triggered=hedge_triggered,
            cache_hit=cache_hit,
            lane=selected_lane,
            model=effective_model,
            stage=generation_stage,
        )

    return (response_text or None), call_meta


def call_claude(prompt: str, max_tokens: int = None, retry_on_timeout: bool = True,
                call_type: str = "unknown", truncated_docs: list = None,
                timeout: float = None, model_name: str = "", preferred_lane: str = "",
                hedge_triggered: bool = False, cache_hit: bool = False,
                return_meta: bool = False):
    """同步调用 Claude 兼容 API，按需返回文本或文本+元信息。"""
    response_text, call_meta = _call_claude_internal(
        prompt,
        max_tokens=max_tokens,
        retry_on_timeout=retry_on_timeout,
        call_type=call_type,
        truncated_docs=truncated_docs,
        timeout=timeout,
        model_name=model_name,
        preferred_lane=preferred_lane,
        hedge_triggered=hedge_triggered,
        cache_hit=cache_hit,
    )
    if return_meta:
        return response_text, call_meta
    return response_text


# ============ 静态文件 ============

@app.route('/')
def index():
    return send_from_directory(str(WEB_DIR), 'index.html')


@app.route('/<path:filename>')
def static_files(filename):
    safe_name = str(filename or "").strip()
    if not safe_name:
        return "", 404

    path_obj = Path(safe_name)
    if path_obj.is_absolute() or ".." in path_obj.parts:
        return "", 404
    if any(part.startswith(".") for part in path_obj.parts):
        return "", 404

    requested = (WEB_DIR / path_obj).resolve()
    if not is_path_under(requested, WEB_DIR):
        return "", 404
    if not requested.is_file():
        return "", 404
    if requested.suffix.lower() not in ALLOWED_STATIC_EXTENSIONS:
        return "", 404

    relative_path = str(requested.relative_to(WEB_DIR))
    return send_from_directory(str(WEB_DIR), relative_path)


# ============ 报告模板 API ============

def build_custom_template_preview_draft() -> dict:
    return {
        "overview": "本次访谈聚焦可疑通知触发后的核实体验，目标是识别误拦导致的信任流失路径。",
        "needs": [
            {
                "name": "误拦用户心理归因还原",
                "priority": "P0",
                "description": "构建可解释的放弃支付/申诉因果链路，减少误判体验损耗。",
                "evidence_refs": ["Q1", "Q4"],
            },
            {
                "name": "核实流程可读性优化",
                "priority": "P1",
                "description": "降低核实步骤理解门槛，减少用户操作中断。",
                "evidence_refs": ["Q6", "Q8"],
            },
        ],
        "analysis": {
            "customer_needs": "用户希望核实流程中提示语更具体、风险等级更明确。",
            "business_flow": "从通知到核实再到恢复支付的链路存在 2 处高摩擦节点。",
            "tech_constraints": "需兼容现有风控引擎与多端展示规范，避免高风险操作降级。",
            "project_constraints": "需在 2 个迭代内上线首版，并控制新增埋点成本。",
        },
        "visualizations": {
            "priority_quadrant_mermaid": "",
            "business_flow_mermaid": "",
            "demand_pie_mermaid": "",
            "architecture_mermaid": "",
        },
        "solutions": [
            {
                "title": "核实入口分层提示",
                "description": "按风险等级动态调整提示语与操作路径。",
                "owner": "产品经理",
                "timeline": "2周内完成方案并联调",
                "metric": "核实放弃率下降 15%",
                "evidence_refs": ["Q3", "Q9"],
            }
        ],
        "risks": [
            {
                "risk": "提示语过度简化导致误解",
                "impact": "高风险用户可能误判安全状态",
                "mitigation": "关键路径保留二次确认并提供解释弹层",
                "evidence_refs": ["Q10"],
            }
        ],
        "actions": [
            {
                "action": "补充核实链路埋点与漏斗看板",
                "owner": "数据分析",
                "timeline": "本周完成埋点设计，下周上线",
                "metric": "埋点完整率 > 95%",
                "evidence_refs": ["Q12", "Q13"],
            },
            {
                "action": "灰度上线核实文案 A/B 方案",
                "owner": "增长运营",
                "timeline": "2-4周灰度验证",
                "metric": "核实完成率提升 10%",
                "evidence_refs": ["Q14"],
            },
        ],
        "open_questions": [
            {
                "question": "不同年龄段用户对风险文案的理解差异",
                "reason": "现有样本主要集中在中青年",
                "impact": "可能影响文案泛化效果",
                "suggested_follow_up": "增加高龄样本并拆分渠道分析",
                "evidence_refs": ["Q15"],
            }
        ],
        "evidence_index": [
            {
                "claim": "当前核实流程存在高摩擦节点",
                "confidence": "high",
                "evidence_refs": ["Q6", "Q8", "Q10"],
            }
        ],
    }


@app.route('/api/report-templates/validate', methods=['POST'])
def validate_report_template_schema():
    data = request.get_json() or {}
    schema_input = data.get("schema")
    sections_input = data.get("sections")
    normalized_schema, issues = normalize_custom_report_schema(schema_input, fallback_sections=sections_input)
    if issues:
        return jsonify({
            "success": False,
            "error": "模板结构校验失败",
            "details": issues,
            "schema": normalized_schema,
        }), 400
    return jsonify({"success": True, "schema": normalized_schema})


@app.route('/api/report-templates/preview', methods=['POST'])
def preview_report_template_schema():
    data = request.get_json() or {}
    schema_input = data.get("schema")
    sections_input = data.get("sections")
    normalized_schema, issues = normalize_custom_report_schema(schema_input, fallback_sections=sections_input)
    if issues:
        return jsonify({
            "success": False,
            "error": "模板结构校验失败",
            "details": issues,
            "schema": normalized_schema,
        }), 400

    draft = data.get("draft")
    if not isinstance(draft, dict):
        draft = build_custom_template_preview_draft()
    quality_meta = data.get("quality_meta")
    if not isinstance(quality_meta, dict):
        quality_meta = {}

    session_stub = {
        "topic": str(data.get("topic") or "自定义模板预览"),
        "scenario_config": {
            "report": {
                "type": "standard",
                "template": REPORT_TEMPLATE_CUSTOM_V1,
                "schema": normalized_schema,
            }
        },
        "dimensions": {},
        "interview_log": [],
    }
    markdown = render_report_from_draft_custom_v1(session_stub, draft, quality_meta)

    return jsonify({
        "success": True,
        "schema": normalized_schema,
        "preview_markdown": markdown,
    })


# ============ 场景 API ============

@app.route('/api/scenarios', methods=['GET'])
def list_scenarios():
    """获取所有场景列表"""
    scenarios = scenario_loader.get_all_scenarios()
    # 返回简化的场景信息
    return jsonify([
        {
            "id": s.get("id"),
            "name": s.get("name"),
            "name_en": s.get("name_en"),
            "description": s.get("description"),
            "icon": s.get("icon"),
            "builtin": s.get("builtin", True),
            "custom": s.get("custom", False),
            "dimensions": [
                {
                    "id": d.get("id"),
                    "name": d.get("name"),
                    "description": d.get("description")
                }
                for d in s.get("dimensions", [])
            ],
            "report_type": s.get("report", {}).get("type", "standard"),
            "report_template": normalize_report_template_name(
                s.get("report", {}).get("template", ""),
                report_type=s.get("report", {}).get("type", "standard"),
            ),
            "has_custom_report_schema": isinstance(s.get("report", {}).get("schema"), dict),
        }
        for s in scenarios
    ])


@app.route('/api/scenarios/<scenario_id>', methods=['GET'])
def get_scenario(scenario_id):
    """获取场景详情"""
    scenario = scenario_loader.get_scenario(scenario_id)
    if not scenario:
        return jsonify({"error": "场景不存在"}), 404
    return jsonify(scenario)


@app.route('/api/scenarios/generate', methods=['POST'])
def generate_scenario_with_ai():
    """AI 自动生成场景配置"""
    ai_client = resolve_ai_client(call_type="scenario_generate")
    if not ai_client:
        return jsonify({"error": "AI 服务不可用"}), 503

    data = request.get_json()
    if not data:
        return jsonify({"error": "无效的请求数据"}), 400

    user_description = data.get("user_description", "").strip()
    if not user_description:
        return jsonify({"error": "请输入场景描述"}), 400

    if len(user_description) < 10:
        return jsonify({"error": "描述太短，请至少输入10个字"}), 400

    if len(user_description) > 500:
        return jsonify({"error": "描述不能超过500字"}), 400

    # 构建 Prompt
    prompt = f'''你是一个专业的访谈场景设计师。用户将描述他们想要进行的访谈或调研目标，你需要设计一个完整的访谈场景配置。

## 用户描述
{user_description}

## 设计要求
1. 场景名称：简洁明了，4-10个字
2. 场景描述：说明场景适用范围，20-50字
3. 关键词：5-10个用于自动匹配的关键词
4. 维度设计：3-5个维度（根据访谈复杂度调整）
   - 每个维度需要有清晰的名称（2-6字）
   - 维度描述说明该维度关注的内容（10-30字）
   - 每个维度包含3-5个关键点（key_aspects）
   - min_questions 固定为 2，max_questions 固定为 4

## 设计原则
- 维度之间应该互补，共同覆盖用户关心的所有方面
- 维度顺序应该符合认知逻辑（如从具体到抽象，从核心到外围）
- 关键点应该具体可问，便于AI生成访谈问题
- 如果用户描述涉及评估/评分类场景，可考虑在维度中加入评分相关的关键点

## 参考：现有场景示例
- 产品需求：客户需求、业务流程、技术约束、项目约束
- 用户研究：用户背景、使用场景、痛点期望、行为模式
- 竞品分析：市场定位、功能对比、用户评价、差异化机会

## 输出格式
请严格按照以下JSON格式输出，不要包含其他文字：
```json
{{
  "name": "场景名称",
  "description": "场景描述",
  "dimensions": [
    {{
      "id": "dim_1",
      "name": "维度名称",
      "description": "维度描述",
      "key_aspects": ["关键点1", "关键点2", "关键点3", "关键点4"],
      "min_questions": 2,
      "max_questions": 4
    }}
  ],
  "explanation": "设计思路说明（1-2句话，解释为什么这样设计维度）"
}}
```'''

    try:
        response = ai_client.messages.create(
            model=resolve_model_name(call_type="scenario_generate"),
            max_tokens=1500,
            timeout=30.0,
            messages=[{"role": "user", "content": prompt}]
        )

        raw_text = extract_message_text(response)
        if not raw_text:
            raise ValueError("模型响应中未包含场景配置文本")

        # 提取 JSON（兼容模型返回 markdown 代码块）
        if "```json" in raw_text:
            raw_text = raw_text.split("```json")[1].split("```")[0].strip()
        elif "```" in raw_text:
            raw_text = raw_text.split("```")[1].split("```")[0].strip()

        generated = json.loads(raw_text)

        # 验证必要字段
        if not generated.get("name"):
            return jsonify({"error": "生成的场景缺少名称"}), 500

        if not generated.get("dimensions") or len(generated["dimensions"]) < 1:
            return jsonify({"error": "生成的场景缺少维度"}), 500

        # 提取 explanation 并移除（不存入场景配置）
        ai_explanation = generated.pop("explanation", "")

        # 确保维度格式正确
        for i, dim in enumerate(generated["dimensions"]):
            dim["id"] = f"dim_{i + 1}"
            dim.setdefault("min_questions", 2)
            dim.setdefault("max_questions", 4)
            if not isinstance(dim.get("key_aspects"), list):
                dim["key_aspects"] = []

        # 添加默认的 report 配置
        generated["report"] = {"type": "standard", "template": "default"}

        return jsonify({
            "success": True,
            "generated_scenario": generated,
            "ai_explanation": ai_explanation
        })

    except json.JSONDecodeError as e:
        print(f"⚠️ AI 生成场景 JSON 解析失败: {e}")
        return jsonify({"error": "AI 返回格式异常，请重试"}), 500
    except Exception as e:
        print(f"⚠️ AI 生成场景失败: {e}")
        return jsonify({"error": f"生成失败: {str(e)[:100]}"}), 500


@app.route('/api/scenarios/custom', methods=['POST'])
def create_custom_scenario():
    """创建自定义场景"""
    data = request.get_json()
    if not data:
        return jsonify({"error": "无效的请求数据"}), 400

    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "场景名称不能为空"}), 400

    dimensions = data.get("dimensions", [])
    if not dimensions or len(dimensions) < 1:
        return jsonify({"error": "至少需要 1 个维度"}), 400
    if len(dimensions) > 8:
        return jsonify({"error": "最多支持 8 个维度"}), 400

    # 验证维度数据
    for i, dim in enumerate(dimensions):
        if not dim.get("name", "").strip():
            return jsonify({"error": f"第 {i+1} 个维度名称不能为空"}), 400
        # 自动生成维度 ID
        if not dim.get("id"):
            dim["id"] = f"dim_{i+1}"
        # 确保有必要字段
        dim.setdefault("description", "")
        dim.setdefault("key_aspects", [])
        dim.setdefault("min_questions", 2)
        dim.setdefault("max_questions", 4)

    report_payload = data.get("report", {"type": "standard", "template": "default"})
    if not isinstance(report_payload, dict):
        return jsonify({"error": "report 配置格式无效"}), 400

    report_type = str(report_payload.get("type") or "standard").strip().lower()
    if report_type not in {"standard", "assessment"}:
        report_type = "standard"
    report_template = normalize_report_template_name(report_payload.get("template", ""), report_type=report_type)
    if report_template not in REPORT_TEMPLATE_ALLOWED:
        return jsonify({"error": "report.template 不支持"}), 400

    normalized_report = {"type": report_type}
    if report_template == REPORT_TEMPLATE_STANDARD_V1:
        normalized_report["template"] = "default"
    elif report_template == REPORT_TEMPLATE_ASSESSMENT_V1:
        normalized_report["template"] = "assessment"
    else:
        normalized_report["template"] = REPORT_TEMPLATE_CUSTOM_V1
        schema_input = report_payload.get("schema")
        normalized_schema, schema_issues = normalize_custom_report_schema(
            schema_input,
            fallback_sections=report_payload.get("sections"),
        )
        if schema_issues:
            return jsonify({"error": "report.schema 校验失败", "details": schema_issues}), 400
        normalized_report["schema"] = normalized_schema

    scenario = {
        "name": name,
        "description": data.get("description", "").strip(),
        "icon": data.get("icon", "clipboard-list"),
        "dimensions": dimensions,
        "report": normalized_report,
    }

    scenario_id = scenario_loader.save_custom_scenario(scenario)

    return jsonify({
        "success": True,
        "scenario_id": scenario_id,
        "scenario": scenario_loader.get_scenario(scenario_id)
    })


@app.route('/api/scenarios/custom/<scenario_id>', methods=['DELETE'])
def delete_custom_scenario(scenario_id):
    """删除自定义场景"""
    if not scenario_id.startswith("custom-"):
        return jsonify({"error": "只能删除自定义场景"}), 400

    success = scenario_loader.delete_custom_scenario(scenario_id)
    if not success:
        return jsonify({"error": "场景不存在或无法删除"}), 404

    return jsonify({"success": True})


@app.route('/api/scenarios/recognize', methods=['POST'])
def recognize_scenario():
    """根据主题和描述智能识别最匹配的访谈场景"""
    data = request.get_json()
    if not data:
        return jsonify({"error": "无效的请求数据"}), 400

    topic = data.get("topic", "")
    description = data.get("description", "")
    if not topic:
        return jsonify({"error": "主题不能为空"}), 400

    # 构建场景摘要供 AI 判断
    all_scenarios = scenario_loader.get_all_scenarios()
    scenario_list_text = "\n".join(
        f"- id: {s['id']}, 名称: {s['name']}, 说明: {s.get('description', '')}"
        for s in all_scenarios
    )

    user_input = f"访谈主题：{topic}"
    if description:
        user_input += f"\n主题描述：{description}"

    prompt = f"""你是一个访谈场景分类器。根据用户的访谈主题和描述，从以下场景中选择最匹配的一个。

可选场景：
{scenario_list_text}

{user_input}

请严格按照以下 JSON 格式返回（不要包含其他文字）：
{{"scenario_id": "最匹配的场景id", "confidence": 0.0到1.0的置信度, "reason": "一句话理由"}}"""

    valid_scenario_ids = {s["id"] for s in all_scenarios}

    # 优先使用 AI 识别，失败时回退到关键词匹配
    ai_result = None
    ai_last_error = None
    scenario_client = resolve_ai_client(call_type="scenario_recognize")
    if scenario_client:
        attempts = [
            {
                "max_tokens": 220,
                "timeout": 10.0,
                "extra_instruction": "",
            },
            {
                "max_tokens": 480,
                "timeout": 18.0,
                "extra_instruction": "只输出一行 JSON，不要 markdown 代码块，不要额外解释，不要换行。",
            },
        ]

        for idx, attempt in enumerate(attempts, start=1):
            try:
                attempt_prompt = prompt
                if attempt["extra_instruction"]:
                    attempt_prompt = f"{prompt}\n\n【额外要求】{attempt['extra_instruction']}"

                response = scenario_client.messages.create(
                    model=resolve_model_name(call_type="scenario_recognize"),
                    max_tokens=attempt["max_tokens"],
                    timeout=attempt["timeout"],
                    messages=[{"role": "user", "content": attempt_prompt}]
                )

                raw = extract_message_text(response)
                if not raw:
                    raise ValueError("模型响应中未包含场景识别文本")

                parsed = parse_scenario_recognition_response(raw, valid_scenario_ids)
                if parsed:
                    ai_result = parsed
                    break

                raise ValueError(f"无法从响应提取有效场景结果，响应前120字: {raw[:120]}")
            except Exception as e:
                ai_last_error = e
                if ENABLE_DEBUG_LOG:
                    print(f"⚠️  AI 场景识别第{idx}次失败: {e}")

        if not ai_result and ai_last_error:
            print(f"⚠️  AI 场景识别失败，回退到关键词匹配: {ai_last_error}")

    if ai_result and ai_result.get("scenario_id") in valid_scenario_ids:
        best_id = ai_result["scenario_id"]
        confidence = min(1.0, max(0.0, float(ai_result.get("confidence", 0.8))))
        reason = ai_result.get("reason", "")
    else:
        # 回退：关键词匹配
        kw_result = scenario_loader.match_by_keywords(topic)
        best_id = kw_result["scenario_id"]
        confidence = kw_result["confidence"]
        reason = ""

    recommended_scenario = scenario_loader.get_scenario(best_id)

    return jsonify({
        "recommended": {
            "id": best_id,
            "name": recommended_scenario.get("name") if recommended_scenario else best_id,
            "description": recommended_scenario.get("description") if recommended_scenario else "",
            "icon": recommended_scenario.get("icon") if recommended_scenario else "clipboard-list",
            "dimensions_count": len(recommended_scenario.get("dimensions", [])) if recommended_scenario else 4
        },
        "confidence": confidence,
        "reason": reason
    })


# ============ 认证 API ============

def ensure_user_for_phone(phone: str) -> tuple[Optional[sqlite3.Row], bool]:
    normalized_phone = normalize_phone_number(phone)
    existing = query_user_by_account(normalized_phone)
    if existing:
        return existing, False

    now_iso = datetime.now(timezone.utc).isoformat()
    random_password_hash = generate_password_hash(secrets.token_urlsafe(32), method="pbkdf2:sha256")
    try:
        with get_auth_db_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO users (email, phone, password_hash, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (None, normalized_phone, random_password_hash, now_iso, now_iso),
            )
            conn.commit()
            user_id = int(cursor.lastrowid)
    except sqlite3.IntegrityError:
        existing_after_conflict = query_user_by_account(normalized_phone)
        return existing_after_conflict, False

    return query_user_by_id(user_id), True


@app.route('/api/auth/sms/send-code', methods=['POST'])
def auth_send_sms_code():
    data = request.get_json() or {}
    raw_phone = str(data.get("phone") or data.get("account") or "").strip()
    scene = normalize_sms_scene(data.get("scene") or "login")

    phone, phone_error = normalize_account(raw_phone)
    if phone_error:
        return jsonify({"error": phone_error}), 400

    if scene == "bind":
        current_user = get_current_user()
        if not current_user:
            return jsonify({"error": "请先登录"}), 401

    ok, error_message, payload = issue_sms_code(phone, scene, request_ip=get_request_ip())
    if not ok:
        status_code = 429 if (payload and payload.get("retry_after")) else 400
        response_body = {"error": error_message or "验证码发送失败"}
        if payload:
            response_body.update(payload)
        return jsonify(response_body), status_code

    response_body = {
        "success": True,
        "message": "验证码已发送",
    }
    if payload:
        response_body.update(payload)
    return jsonify(response_body)


@app.route('/api/auth/login/code', methods=['POST'])
@app.route('/api/auth/recover/login', methods=['POST'])
def auth_login_with_code():
    data = request.get_json() or {}
    raw_phone = str(data.get("phone") or data.get("account") or "").strip()
    code = str(data.get("code") or data.get("sms_code") or "").strip()
    scene = normalize_sms_scene(data.get("scene") or "login")
    if scene not in {"login", "recover"}:
        scene = "login"

    phone, phone_error = normalize_account(raw_phone)
    if phone_error:
        return jsonify({"error": phone_error}), 400
    if not code:
        return jsonify({"error": "请输入验证码"}), 400

    verified, verify_error = verify_sms_code(phone, scene, code, consume=True)
    if not verified:
        status_code = 401 if "错误" in verify_error else 400
        if "次数过多" in verify_error:
            status_code = 429
        return jsonify({"error": verify_error or "验证码校验失败"}), status_code

    user_row, created = ensure_user_for_phone(phone)
    if not user_row:
        return jsonify({"error": "登录失败，请稍后重试"}), 500

    login_user(user_row)
    return jsonify({
        "success": True,
        "created": bool(created),
        "user": build_user_payload(user_row),
    })


@app.route('/api/auth/recover/send-code', methods=['POST'])
def auth_recover_send_code():
    data = request.get_json() or {}
    raw_phone = str(data.get("phone") or data.get("account") or "").strip()
    phone, phone_error = normalize_account(raw_phone)
    if phone_error:
        return jsonify({"error": phone_error}), 400

    ok, error_message, payload = issue_sms_code(phone, "recover", request_ip=get_request_ip())
    if not ok:
        status_code = 429 if (payload and payload.get("retry_after")) else 400
        response_body = {"error": error_message or "验证码发送失败"}
        if payload:
            response_body.update(payload)
        return jsonify(response_body), status_code

    response_body = {
        "success": True,
        "message": "验证码已发送",
    }
    if payload:
        response_body.update(payload)
    return jsonify(response_body)


@app.route('/api/auth/register', methods=['POST'])
def auth_register_legacy():
    return jsonify({"error": "手机号+密码注册已下线，请使用手机号验证码登录"}), 410


@app.route('/api/auth/login', methods=['POST'])
def auth_login_legacy():
    return jsonify({"error": "手机号+密码登录已下线，请使用手机号验证码登录"}), 410


@app.route('/api/auth/wechat/start', methods=['GET'])
def auth_wechat_start():
    unavailable_reason = get_wechat_login_unavailable_reason()
    if unavailable_reason:
        return jsonify({"error": unavailable_reason}), 503

    return_to = sanitize_return_to_path(request.args.get("return_to", "/index.html"))
    encoded_return_to = base64.urlsafe_b64encode(return_to.encode("utf-8")).decode("ascii").rstrip("=")
    oauth_state = f"{secrets.token_urlsafe(20)}.{encoded_return_to}"

    session["wechat_oauth_state"] = oauth_state
    session["wechat_oauth_state_expires_at"] = int(_time.time()) + int(WECHAT_OAUTH_STATE_TTL_SECONDS)
    session["wechat_oauth_return_to"] = return_to

    callback_url = get_wechat_oauth_callback_url()
    auth_url = (
        "https://open.weixin.qq.com/connect/qrconnect"
        f"?appid={quote(WECHAT_APP_ID)}"
        f"&redirect_uri={quote(callback_url, safe='')}"
        "&response_type=code"
        f"&scope={quote(WECHAT_OAUTH_SCOPE)}"
        f"&state={quote(oauth_state)}"
        "#wechat_redirect"
    )
    return redirect(auth_url, code=302)


@app.route('/api/auth/bind/wechat/start', methods=['GET'])
@require_login
def auth_bind_wechat_start():
    unavailable_reason = get_wechat_login_unavailable_reason()
    if unavailable_reason:
        return jsonify({"error": unavailable_reason}), 503

    current_user = get_current_user()
    if not current_user:
        return jsonify({"error": "请先登录"}), 401

    return_to = sanitize_return_to_path(request.args.get("return_to", "/index.html"))
    encoded_return_to = base64.urlsafe_b64encode(return_to.encode("utf-8")).decode("ascii").rstrip("=")
    bind_state = f"{secrets.token_urlsafe(20)}.{encoded_return_to}"

    session["wechat_bind_state"] = bind_state
    session["wechat_bind_state_expires_at"] = int(_time.time()) + int(WECHAT_OAUTH_STATE_TTL_SECONDS)
    session["wechat_bind_return_to"] = return_to
    session["wechat_bind_user_id"] = int(current_user["id"])

    callback_url = get_wechat_oauth_callback_url()
    auth_url = (
        "https://open.weixin.qq.com/connect/qrconnect"
        f"?appid={quote(WECHAT_APP_ID)}"
        f"&redirect_uri={quote(callback_url, safe='')}"
        "&response_type=code"
        f"&scope={quote(WECHAT_OAUTH_SCOPE)}"
        f"&state={quote(bind_state)}"
        "#wechat_redirect"
    )
    return redirect(auth_url, code=302)


@app.route('/api/auth/wechat/callback', methods=['GET'])
def auth_wechat_callback():
    state_from_query = str(request.args.get("state", "")).strip()
    return_to_from_state = extract_return_to_from_oauth_state(state_from_query)
    is_bind_flow = bool(str(session.get("wechat_bind_state", "")).strip())
    fallback_return_to = sanitize_return_to_path(
        session.get(
            "wechat_bind_return_to" if is_bind_flow else "wechat_oauth_return_to",
            return_to_from_state or "/index.html"
        )
    )

    unavailable_reason = get_wechat_login_unavailable_reason()
    if unavailable_reason:
        return redirect(
            build_auth_redirect_url(
                fallback_return_to,
                "wechat_bind_error" if is_bind_flow else "wechat_error",
                unavailable_reason
            ),
            code=302,
        )

    code = str(request.args.get("code", "")).strip()
    state = state_from_query

    if is_bind_flow:
        expected_state = str(session.pop("wechat_bind_state", "")).strip()
        expires_at_raw = session.pop("wechat_bind_state_expires_at", 0)
        return_to = sanitize_return_to_path(session.pop("wechat_bind_return_to", return_to_from_state or fallback_return_to))
        bind_user_id_raw = session.pop("wechat_bind_user_id", 0)
        try:
            bind_user_id = int(bind_user_id_raw or 0)
        except Exception:
            bind_user_id = 0
        bind_user_row = query_user_by_id(bind_user_id) if bind_user_id > 0 else None
    else:
        expected_state = str(session.pop("wechat_oauth_state", "")).strip()
        expires_at_raw = session.pop("wechat_oauth_state_expires_at", 0)
        return_to = sanitize_return_to_path(session.pop("wechat_oauth_return_to", return_to_from_state or fallback_return_to))
        bind_user_row = None

    try:
        expires_at = int(expires_at_raw or 0)
    except Exception:
        expires_at = 0

    if not expected_state or not state or state != expected_state:
        return redirect(
            build_auth_redirect_url(
                return_to,
                "wechat_bind_error" if is_bind_flow else "wechat_error",
                "微信登录状态校验失败，请重试",
            ),
            code=302,
        )

    if expires_at <= int(_time.time()):
        return redirect(
            build_auth_redirect_url(
                return_to,
                "wechat_bind_error" if is_bind_flow else "wechat_error",
                "微信登录已过期，请重新扫码",
            ),
            code=302,
        )

    if is_bind_flow and not bind_user_row:
        return redirect(
            build_auth_redirect_url(return_to, "wechat_bind_error", "绑定已失效，请登录后重试"),
            code=302,
        )
    if is_bind_flow:
        active_user = get_current_user()
        if not active_user or int(active_user["id"]) != int(bind_user_row["id"]):
            return redirect(
                build_auth_redirect_url(return_to, "wechat_bind_error", "绑定已失效，请登录后重试"),
                code=302,
            )

    if not code:
        return redirect(
            build_auth_redirect_url(
                return_to,
                "wechat_bind_error" if is_bind_flow else "wechat_cancel",
                "已取消微信登录",
            ),
            code=302,
        )

    token_payload, token_error = exchange_wechat_code_for_token(code)
    if token_error or not token_payload:
        return redirect(
            build_auth_redirect_url(
                return_to,
                "wechat_bind_error" if is_bind_flow else "wechat_error",
                token_error or "微信授权失败",
            ),
            code=302,
        )

    openid = str(token_payload.get("openid", "")).strip()
    access_token = str(token_payload.get("access_token", "")).strip()
    unionid = str(token_payload.get("unionid", "")).strip()
    if not openid or not access_token:
        return redirect(
            build_auth_redirect_url(
                return_to,
                "wechat_bind_error" if is_bind_flow else "wechat_error",
                "微信授权响应不完整",
            ),
            code=302,
        )

    profile_payload, profile_error = fetch_wechat_user_profile(access_token, openid)
    if profile_error or not profile_payload:
        return redirect(
            build_auth_redirect_url(
                return_to,
                "wechat_bind_error" if is_bind_flow else "wechat_error",
                profile_error or "拉取微信用户信息失败",
            ),
            code=302,
        )

    profile_unionid = str(profile_payload.get("unionid", "")).strip()
    if profile_unionid:
        unionid = profile_unionid

    nickname = str(profile_payload.get("nickname", "")).strip()
    avatar_url = str(profile_payload.get("headimgurl", "")).strip()

    if is_bind_flow:
        user_row, bind_error = bind_wechat_identity_to_user(
            user_id=int(bind_user_row["id"]),
            app_id=WECHAT_APP_ID,
            openid=openid,
            unionid=unionid,
            nickname=nickname,
            avatar_url=avatar_url,
        )
        if bind_error or not user_row:
            return redirect(
                build_auth_redirect_url(return_to, "wechat_bind_error", bind_error or "微信绑定失败，请稍后重试"),
                code=302,
            )

        login_user(user_row)
        return redirect(build_auth_redirect_url(return_to, "wechat_bind_success", "微信绑定成功"), code=302)

    user_row = resolve_user_for_wechat_identity(
        app_id=WECHAT_APP_ID,
        openid=openid,
        unionid=unionid,
        nickname=nickname,
        avatar_url=avatar_url,
    )
    if not user_row:
        return redirect(
            build_auth_redirect_url(return_to, "wechat_error", "微信登录失败，请稍后再试"),
            code=302,
        )

    login_user(user_row)
    return redirect(build_auth_redirect_url(return_to, "wechat_success", "微信登录成功"), code=302)


@app.route('/api/auth/logout', methods=['POST'])
def auth_logout():
    session.clear()
    return jsonify({"success": True})


@app.route('/api/auth/me', methods=['GET'])
def auth_me():
    user_row = get_current_user()
    if not user_row:
        return jsonify({"error": "请先登录"}), 401
    return jsonify({"user": build_user_payload(user_row)})


@app.route('/api/auth/bind/status', methods=['GET'])
@require_login
def auth_bind_status():
    user_row = get_current_user()
    if not user_row:
        return jsonify({"error": "请先登录"}), 401
    return jsonify({"user": build_user_payload(user_row)})


@app.route('/api/auth/bind/phone', methods=['POST'])
@require_login
def auth_bind_phone():
    user_row = get_current_user()
    if not user_row:
        return jsonify({"error": "请先登录"}), 401

    data = request.get_json() or {}
    phone = str(data.get("phone") or data.get("account") or "").strip()
    sms_code = str(data.get("code") or data.get("sms_code") or "").strip()
    if not phone:
        return jsonify({"error": "请输入要绑定的手机号"}), 400
    if not sms_code:
        return jsonify({"error": "请输入验证码"}), 400

    verified, verify_error = verify_sms_code(phone, "bind", sms_code, consume=True)
    if not verified:
        status_code = 401 if "错误" in verify_error else 400
        if "次数过多" in verify_error:
            status_code = 429
        return jsonify({"error": verify_error or "验证码校验失败"}), status_code

    updated_user, bind_error = bind_phone_to_user(int(user_row["id"]), phone)
    if bind_error or not updated_user:
        status_code = 409 if "已绑定" in (bind_error or "") else 400
        return jsonify({"error": bind_error or "绑定手机号失败"}), status_code

    login_user(updated_user)
    return jsonify({"success": True, "user": build_user_payload(updated_user)})


# ============ 会话 API ============


def build_session_list_cache_payload(session_data: dict) -> Optional[dict]:
    if not isinstance(session_data, dict):
        return None

    interview_log = session_data.get("interview_log", [])
    interview_count = len(interview_log) if isinstance(interview_log, list) else 0
    try:
        owner_user_id = int(session_data.get("owner_user_id"))
    except (TypeError, ValueError):
        owner_user_id = 0

    return {
        "owner_user_id": owner_user_id,
        "instance_scope_key": get_session_instance_scope_key(session_data),
        "session_id": session_data.get("session_id"),
        "topic": session_data.get("topic"),
        "status": session_data.get("status"),
        "created_at": session_data.get("created_at"),
        "updated_at": session_data.get("updated_at"),
        "dimensions": build_compact_dimensions(session_data.get("dimensions", {})),
        "interview_count": interview_count,
        "scenario_id": session_data.get("scenario_id"),
        "scenario_config": session_data.get("scenario_config"),
    }


def get_cached_session_list_payload(session_file: Path) -> Optional[dict]:
    signature = get_file_signature(session_file)
    if signature is None:
        return None

    cache_key = session_file.name
    with session_list_cache_lock:
        cached = session_list_cache.get(cache_key)
        if cached and cached.get("signature") == signature:
            record_list_cache_metric("session_meta", hit=True)
            payload = cached.get("payload")
            if isinstance(payload, dict):
                return dict(payload)

    record_list_cache_metric("session_meta", hit=False)
    session_data = safe_load_session(session_file)
    if not isinstance(session_data, dict):
        return None

    payload = build_session_list_cache_payload(session_data)
    if not isinstance(payload, dict):
        return None

    with session_list_cache_lock:
        session_list_cache[cache_key] = {
            "signature": signature,
            "payload": dict(payload),
        }
    return dict(payload)


def cleanup_session_list_cache(active_filenames: set[str]) -> None:
    with session_list_cache_lock:
        stale_names = [name for name in session_list_cache.keys() if name not in active_filenames]
        for name in stale_names:
            session_list_cache.pop(name, None)


def load_sessions_for_user_from_files(user_id_int: int) -> list[dict]:
    sessions = []
    active_files = set()
    expected_scope = get_active_instance_scope_key()
    for session_file in SESSIONS_DIR.glob("*.json"):
        active_files.add(session_file.name)
        data = get_cached_session_list_payload(session_file)
        if not isinstance(data, dict):
            continue
        if int(data.get("owner_user_id", 0)) != int(user_id_int):
            continue
        if not is_instance_scope_visible(data.get("instance_scope_key"), expected_scope=expected_scope):
            continue

        sessions.append({
            "session_id": data.get("session_id"),
            "topic": data.get("topic"),
            "status": data.get("status"),
            "created_at": data.get("created_at"),
            "updated_at": data.get("updated_at"),
            "dimensions": data.get("dimensions", {}),
            "interview_count": data.get("interview_count", 0),
            "scenario_id": data.get("scenario_id"),
            "scenario_config": data.get("scenario_config"),
        })

    cleanup_session_list_cache(active_files)
    sessions.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return sessions


def attach_report_generation_status(session_item: dict) -> dict:
    item = dict(session_item or {})
    session_id = item.get("session_id")
    report_generation = None
    if session_id:
        status_record = get_report_generation_record(session_id)
        if status_record and not bool(status_record.get("active")) and is_report_generation_worker_alive(session_id):
            status_state = str(status_record.get("state") or "").strip()
            if status_state not in {"completed", "failed", "cancelled"}:
                update_report_generation_status(session_id, "queued", message="报告任务正在处理中...")
                status_record = get_report_generation_record(session_id)
        if status_record and bool(status_record.get("active")):
            queue_snapshot = get_report_generation_worker_snapshot(include_positions=True)
            sync_report_generation_queue_metadata(session_id, snapshot=queue_snapshot)
            status_record = get_report_generation_record(session_id) or status_record
        payload = build_report_generation_payload(status_record)
        if payload.get("active"):
            report_generation = {
                "active": True,
                "state": payload.get("state", "queued"),
                "progress": payload.get("progress", 0),
                "message": payload.get("message", ""),
                "updated_at": payload.get("updated_at"),
                "action": payload.get("action", "generate"),
                "queue_position": payload.get("queue_position", 0),
                "queue_pending": payload.get("queue_pending", 0),
                "queue_running": payload.get("queue_running", 0),
            }
    item["report_generation"] = report_generation
    return item


@app.route('/api/sessions', methods=['GET'])
def list_sessions():
    """获取所有会话"""
    user_id = get_current_user_id_or_none()
    if not user_id:
        return jsonify({"error": "请先登录"}), 401

    page, page_size, offset = parse_list_pagination_params()
    started_at = _time.perf_counter()
    if not try_acquire_list_semaphore("sessions_list", SESSIONS_LIST_SEMAPHORE):
        response = build_overload_response("sessions_list")
        latency_ms = (_time.perf_counter() - started_at) * 1000
        record_list_request_metric(
            endpoint="sessions_list",
            status_code=429,
            latency_ms=latency_ms,
            source="overload",
            page_size=page_size,
            returned_count=0,
            total_count=0,
            error_reason="overload",
        )
        return response

    try:
        user_id_int = int(user_id)
        data_source = "sqlite"
        scan_ms = 0.0

        try:
            ensure_session_index_bootstrapped()
            sessions, total = query_session_index_for_user(user_id_int, page, page_size)
        except Exception as exc:
            data_source = "file_scan"
            if ENABLE_DEBUG_LOG:
                _safe_log(f"⚠️ session_index 查询失败，回退文件扫描: {exc}")
            scan_started_at = _time.perf_counter()
            all_sessions = load_sessions_for_user_from_files(user_id_int)
            scan_ms = (_time.perf_counter() - scan_started_at) * 1000
            total = len(all_sessions)
            sessions = all_sessions[offset: offset + page_size]

        sessions = [attach_report_generation_status(item) for item in sessions]
        etag = build_list_etag(
            endpoint="sessions_list",
            page=page,
            page_size=page_size,
            total=total,
            items=sessions,
        )
        if_none_match_values = parse_if_none_match_values()
        if etag in if_none_match_values or "*" in if_none_match_values:
            response = build_not_modified_response(etag, page=page, page_size=page_size, total=total)
            latency_ms = (_time.perf_counter() - started_at) * 1000
            record_list_request_metric(
                endpoint="sessions_list",
                status_code=304,
                latency_ms=latency_ms,
                source=data_source,
                page_size=page_size,
                returned_count=0,
                total_count=total,
                scan_ms=scan_ms,
            )
            return response

        response = jsonify(sessions)
        response.headers["ETag"] = etag
        response.headers["Cache-Control"] = "private, max-age=2"
        latency_ms = (_time.perf_counter() - started_at) * 1000
        record_list_request_metric(
            endpoint="sessions_list",
            status_code=200,
            latency_ms=latency_ms,
            source=data_source,
            page_size=page_size,
            returned_count=len(sessions),
            total_count=total,
            scan_ms=scan_ms,
        )
        return apply_pagination_headers(response, page=page, page_size=page_size, total=total)
    except Exception as exc:
        latency_ms = (_time.perf_counter() - started_at) * 1000
        record_list_request_metric(
            endpoint="sessions_list",
            status_code=500,
            latency_ms=latency_ms,
            source="unknown",
            page_size=page_size,
            returned_count=0,
            total_count=0,
            error_reason=type(exc).__name__,
        )
        raise
    finally:
        SESSIONS_LIST_SEMAPHORE.release()


@app.route('/api/sessions', methods=['POST'])
def create_session():
    """创建新会话"""
    user_id = get_current_user_id_or_none()
    if not user_id:
        return jsonify({"error": "请先登录"}), 401

    data = request.get_json()
    if not data:
        return jsonify({"error": "无效的请求数据"}), 400

    topic = data.get("topic", "未命名访谈")
    description = data.get("description")  # 获取可选的主题描述
    interview_mode = data.get("interview_mode", DEFAULT_INTERVIEW_MODE)  # 获取访谈模式
    scenario_id = data.get("scenario_id")  # 获取场景ID

    # 验证 topic
    if not isinstance(topic, str) or not topic.strip():
        return jsonify({"error": "主题不能为空"}), 400
    if len(topic) > 200:
        return jsonify({"error": "主题长度不能超过200字符"}), 400

    # 验证 description
    if description and (not isinstance(description, str) or len(description) > 2000):
        return jsonify({"error": "描述长度不能超过2000字符"}), 400

    # 验证访谈模式
    if interview_mode not in INTERVIEW_MODES:
        interview_mode = DEFAULT_INTERVIEW_MODE

    # 加载场景配置（如果未指定，使用默认场景）
    if not scenario_id:
        scenario_id = "product-requirement"

    scenario_config = scenario_loader.get_scenario(scenario_id)
    if not isinstance(scenario_config, dict):
        scenario_config = scenario_loader.get_default_scenario()

    scenario_config = dict(scenario_config or {})
    scenario_id = str(scenario_config.get("id") or "product-requirement")

    scenario_dimensions = normalize_scenario_dimensions(scenario_config.get("dimensions", []))

    # 兼容历史脏数据：维度异常时自动回退默认场景，避免 500
    if not scenario_dimensions:
        fallback_config = scenario_loader.get_default_scenario()
        if isinstance(fallback_config, dict):
            fallback_config = dict(fallback_config)
            fallback_dimensions = normalize_scenario_dimensions(fallback_config.get("dimensions", []))
            if fallback_dimensions:
                scenario_config = fallback_config
                scenario_dimensions = fallback_dimensions
                scenario_id = str(scenario_config.get("id") or "product-requirement")

    # 双重兜底：默认场景也不可用时，使用内置四维度
    if not scenario_dimensions:
        scenario_id = "product-requirement"
        scenario_dimensions = build_default_dimension_entries()
        scenario_config = {
            "id": scenario_id,
            "name": "产品需求",
            "description": "适用于产品需求访谈、功能规划、PRD编写",
            "dimensions": scenario_dimensions,
        }
    else:
        scenario_config["dimensions"] = scenario_dimensions

    # 根据场景配置创建动态维度
    dimensions = {}
    for dim in scenario_dimensions:
        dim_id = str(dim.get("id") or "").strip()
        if not dim_id:
            continue
        dimensions[dim_id] = {
            "coverage": 0,
            "items": [],
            "score": None  # 用于评估型场景
        }

    session_id = generate_session_id()
    now = get_utc_now()

    session = {
        "session_id": session_id,
        "owner_user_id": user_id,
        INSTANCE_SCOPE_FIELD: get_active_instance_scope_key(),
        "topic": topic,
        "description": description,  # 存储主题描述
        "interview_mode": interview_mode,  # 存储访谈模式
        "created_at": now,
        "updated_at": now,
        "status": "in_progress",
        "scenario_id": scenario_id,  # 存储场景ID
        "scenario_config": scenario_config,  # 存储场景完整配置
        "dimensions": dimensions,  # 动态维度
        "reference_materials": [],  # 参考资料（合并原 reference_docs 和 research_docs）
        "interview_log": [],
        "requirements": [],
        "summary": None
    }

    session["depth_v2"] = {
        "enabled": True,
        "mode": interview_mode,
        "skip_followup_confirm": DEEP_MODE_SKIP_FOLLOWUP_CONFIRM,
    }

    session_file = SESSIONS_DIR / f"{session_id}.json"
    save_session_json_and_sync(session_file, session)
    _set_first_question_prefetch_priority(session_id)

    # ========== 步骤6: 预生成首题 ==========
    try:
        prefetch_first_question(session_id)
    except Exception as e:
        # 预生成失败不影响会话创建
        print(f"⚠️ 预生成首题失败: {e}")

    return jsonify(session)


@app.route('/api/sessions/<session_id>', methods=['GET'])
def get_session(session_id):
    """获取会话详情"""
    user_id = get_current_user_id_or_none()
    if not user_id:
        return jsonify({"error": "请先登录"}), 401

    loaded = load_session_for_user(session_id, user_id)
    if len(loaded) == 3:
        _file, error_msg, status_code = loaded
        return jsonify({"error": error_msg}), status_code

    session_file, session = loaded

    # 数据迁移：兼容旧会话格式
    session = migrate_session_docs(session)
    return jsonify(session)


@app.route('/api/sessions/<session_id>', methods=['PUT'])
def update_session(session_id):
    """更新会话"""
    user_id = get_current_user_id_or_none()
    if not user_id:
        return jsonify({"error": "请先登录"}), 401

    loaded = load_session_for_user(session_id, user_id)
    if len(loaded) == 3:
        _file, error_msg, status_code = loaded
        return jsonify({"error": error_msg}), status_code

    updates = request.get_json()
    session_file, session = loaded

    if not isinstance(updates, dict):
        return jsonify({"error": "无效的请求数据"}), 400

    # 定义允许更新的字段白名单
    UPDATABLE_FIELDS = {"description", "topic", "status"}

    for key, value in updates.items():
        if key != "session_id" and key in UPDATABLE_FIELDS:
            session[key] = value

    session["updated_at"] = get_utc_now()
    save_session_json_and_sync(session_file, session)

    return jsonify(session)


@app.route('/api/sessions/<session_id>', methods=['DELETE'])
def delete_session(session_id):
    """删除会话"""
    user_id = get_current_user_id_or_none()
    if not user_id:
        return jsonify({"error": "请先登录"}), 401

    loaded = load_session_for_user(session_id, user_id, include_missing=True)
    session_file, _session, state = loaded

    if state != "ok" or session_file is None:
        return jsonify({"error": "会话不存在"}), 404

    session_file_name = session_file.name
    session_file.unlink()
    remove_session_index_record(session_id=session_id, file_name=session_file_name)

    # ========== 步骤7: 清理缓存和状态 ==========
    invalidate_prefetch(session_id)
    _clear_first_question_prefetch_priority(session_id)
    clear_thinking_status(session_id)
    clear_report_generation_status(session_id)

    return jsonify({"success": True})


@app.route('/api/sessions/batch-delete', methods=['POST'])
def batch_delete_sessions():
    """批量删除会话（默认允许删除进行中的会话）。"""
    user_id = get_current_user_id_or_none()
    if not user_id:
        return jsonify({"error": "请先登录"}), 401

    data = request.get_json(silent=True) or {}
    session_ids = unique_non_empty_strings(data.get("session_ids", []))
    delete_reports = bool(data.get("delete_reports", False))
    skip_in_progress = bool(data.get("skip_in_progress", False))

    if not session_ids:
        return jsonify({"error": "session_ids 不能为空"}), 400

    deleted_sessions = []
    skipped_sessions = []
    missing_sessions = []
    deleted_reports = set()

    for session_id in session_ids:
        session_file = SESSIONS_DIR / f"{session_id}.json"
        if not session_file.exists():
            missing_sessions.append(session_id)
            continue

        session = safe_load_session(session_file)
        if session is None:
            skipped_sessions.append({"session_id": session_id, "reason": "会话数据损坏"})
            continue

        if not ensure_session_owner(session, user_id):
            missing_sessions.append(session_id)
            continue

        if skip_in_progress:
            effective_status = get_effective_session_status(session)
            if effective_status == "in_progress":
                skipped_sessions.append({"session_id": session_id, "reason": "会话进行中，已按设置跳过"})
                continue

        if delete_reports:
            linked_reports = find_reports_by_session_topic(session)
            for report_name in linked_reports:
                report_file = REPORTS_DIR / report_name
                if report_file.exists():
                    mark_report_as_deleted(report_name)
                    deleted_reports.add(report_name)

        try:
            session_file_name = session_file.name
            session_file.unlink()
            remove_session_index_record(session_id=session_id, file_name=session_file_name)
            invalidate_prefetch(session_id)
            _clear_first_question_prefetch_priority(session_id)
            clear_thinking_status(session_id)
            deleted_sessions.append(session_id)
        except Exception as exc:
            skipped_sessions.append({"session_id": session_id, "reason": f"删除失败: {str(exc)}"})

    return jsonify({
        "success": True,
        "requested": len(session_ids),
        "deleted_sessions": deleted_sessions,
        "deleted_reports": sorted(deleted_reports),
        "skipped_sessions": skipped_sessions,
        "missing_sessions": missing_sessions
    })


# ============ AI 驱动的访谈 API ============

def parse_question_response(response: str, debug: bool = False) -> Optional[dict]:
    """解析 AI 返回的问题 JSON 响应

    使用5种递进式解析策略，确保最大程度提取有效JSON。

    Args:
        response: AI 返回的原始响应文本
        debug: 是否输出调试日志

    Returns:
        解析后的 dict（包含 question 和 options），失败返回 None
    """
    import re

    result = None
    parse_error = None

    if debug:
        print(f"📝 AI 原始响应 (前500字): {response[:500]}")

    # 方法1: 直接尝试解析（如果AI严格遵守指令）
    try:
        cleaned = response.strip()
        if cleaned.startswith('{') and cleaned.endswith('}'):
            result = json.loads(cleaned)
            if debug:
                print(f"✅ 方法1成功: 直接解析")
    except json.JSONDecodeError as e:
        parse_error = e
        if debug:
            print(f"⚠️ 方法1失败: {e}")

    # 方法2: 尝试提取 ```json 代码块
    if result is None and "```json" in response:
        try:
            json_start = response.find("```json") + 7
            json_end = response.find("```", json_start)
            if json_end > json_start:
                json_str = response[json_start:json_end].strip()
                result = json.loads(json_str)
                if debug:
                    print(f"✅ 方法2成功: 从代码块提取")
        except json.JSONDecodeError as e:
            parse_error = e
            if debug:
                print(f"⚠️ 方法2失败 (JSON错误): {e}")
        except Exception as e:
            parse_error = e
            if debug:
                print(f"⚠️ 方法2失败 (其他错误): {e}")

    # 方法3: 查找第一个完整的 JSON 对象（花括号配对）
    if result is None:
        try:
            json_start = response.find('{')
            if json_start >= 0:
                brace_count = 0
                json_end = -1
                in_string = False
                escape_next = False

                for i in range(json_start, len(response)):
                    char = response[i]

                    if escape_next:
                        escape_next = False
                        continue

                    if char == '\\':
                        escape_next = True
                        continue

                    if char == '"' and not escape_next:
                        in_string = not in_string
                        continue

                    if not in_string:
                        if char == '{':
                            brace_count += 1
                        elif char == '}':
                            brace_count -= 1
                            if brace_count == 0:
                                json_end = i + 1
                                break

                if json_end > json_start:
                    try:
                        json_str = response[json_start:json_end]
                        result = json.loads(json_str)
                        if debug:
                            print(f"✅ 方法3成功: 花括号配对提取")
                    except json.JSONDecodeError as e:
                        parse_error = e
                        if debug:
                            print(f"⚠️ 方法3失败 (JSON错误): {e}")
        except Exception as e:
            parse_error = e
            if debug:
                print(f"⚠️ 方法3失败 (其他错误): {e}")

    # 方法4: 使用正则表达式提取 JSON 对象
    if result is None:
        try:
            json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
            matches = re.findall(json_pattern, response, re.DOTALL)
            for match in matches:
                try:
                    candidate = json.loads(match)
                    # 验证必须有 question 字段
                    if isinstance(candidate, dict) and "question" in candidate:
                        result = candidate
                        if debug:
                            print(f"✅ 方法4成功: 正则表达式提取")
                        break
                except json.JSONDecodeError:
                    continue
        except Exception as e:
            parse_error = e
            if debug:
                print(f"⚠️ 方法4失败 (其他错误): {e}")

    # 方法5: 尝试修复不完整的JSON（补全缺失字段）
    if result is None and '{' in response and '"question"' in response:
        try:
            if debug:
                print(f"🔧 尝试修复不完整的JSON...")

            # 找到JSON对象的开始位置
            json_start = response.find('{')
            json_content = response[json_start:]

            # 尝试补全缺失的结尾部分
            if '"options"' in json_content and '"question"' in json_content:
                # 如果有options数组但没有正确结束，尝试补全
                if json_content.count('[') > json_content.count(']'):
                    json_content += ']'
                if json_content.count('{') > json_content.count('}'):
                    # 添加缺失的字段
                    if '"multi_select"' not in json_content:
                        json_content += ', "multi_select": false'
                    if '"is_follow_up"' not in json_content:
                        json_content += ', "is_follow_up": false'
                    json_content += '}'

                # 尝试解析修复后的JSON
                try:
                    result = json.loads(json_content)
                    if isinstance(result, dict) and "question" in result:
                        if debug:
                            print(f"✅ 方法5成功: JSON修复完成")
                except json.JSONDecodeError as e:
                    if debug:
                        print(f"⚠️ 方法5失败: 修复后仍无法解析 - {e}")
        except Exception as e:
            parse_error = e
            if debug:
                print(f"⚠️ 方法5失败 (其他错误): {e}")

    # 验证结果
    if result is not None and isinstance(result, dict):
        if "question" in result and "options" in result:
            # 补全可能缺失的字段
            if "multi_select" not in result:
                result["multi_select"] = False
            if "is_follow_up" not in result:
                result["is_follow_up"] = False
            return result

    # 所有解析方法都失败了
    if debug:
        print(f"❌ 所有解析方法都失败")
        print(f"📄 AI 响应前500字符:\n{response[:500] if response else 'None'}")
        print(f"📄 最后解析错误: {str(parse_error) if parse_error else '未知'}")

    return None


def _normalize_question_call_result(raw_result, lane: str, max_tokens: int, timeout: Optional[float]) -> tuple[Optional[str], dict]:
    """兼容 call_claude 返回文本或 (文本, meta) 两种形态。"""
    response_text = None
    call_meta = {}
    if isinstance(raw_result, tuple) and len(raw_result) == 2 and isinstance(raw_result[1], dict):
        response_text, call_meta = raw_result
    else:
        response_text = raw_result

    if response_text is not None and not isinstance(response_text, str):
        response_text = str(response_text)
    response_text = (response_text or "").strip() or None

    normalized_meta = dict(call_meta or {})
    normalized_meta.setdefault("selected_lane", str(lane or ""))
    normalized_meta.setdefault("model", "")
    normalized_meta.setdefault("timeout_seconds", float(timeout if timeout is not None else API_TIMEOUT))
    normalized_meta.setdefault("max_tokens", int(max_tokens))
    normalized_meta.setdefault("queue_wait_ms", 0.0)
    normalized_meta.setdefault("timeout_occurred", False)
    normalized_meta.setdefault("failure_reason", "" if response_text else "unknown")
    normalized_meta.setdefault("error_kind", "")
    normalized_meta.setdefault("error_message", "")
    normalized_meta.setdefault("response_length", len(response_text or ""))
    normalized_meta.setdefault("empty_text", False)
    normalized_meta["success"] = bool(response_text)
    if response_text:
        normalized_meta["response_length"] = len(response_text)
        normalized_meta["failure_reason"] = ""
    return response_text, normalized_meta


def _build_question_attempt_summary(lane: str, response_text: Optional[str], call_meta: Optional[dict]) -> dict:
    normalized_meta = dict(call_meta or {})
    failure_reason = str(normalized_meta.get("failure_reason", "") or "")
    success = bool(response_text)
    if success and not failure_reason:
        failure_reason = "ok"
    elif not failure_reason:
        failure_reason = "unknown"

    try:
        queue_wait_ms = round(float(normalized_meta.get("queue_wait_ms", 0.0) or 0.0), 2)
    except Exception:
        queue_wait_ms = 0.0
    try:
        timeout_seconds = float(normalized_meta.get("timeout_seconds", API_TIMEOUT) or API_TIMEOUT)
    except Exception:
        timeout_seconds = float(API_TIMEOUT)
    try:
        max_tokens_value = int(normalized_meta.get("max_tokens", 0) or 0)
    except Exception:
        max_tokens_value = 0

    response_length = int(normalized_meta.get("response_length", len(response_text or "")) or 0)
    return {
        "lane": str(lane or normalized_meta.get("selected_lane", "") or "unknown"),
        "success": success,
        "failure_reason": failure_reason,
        "timeout_occurred": bool(normalized_meta.get("timeout_occurred", False)),
        "error_kind": str(normalized_meta.get("error_kind", "") or ""),
        "error_message": str(normalized_meta.get("error_message", "") or ""),
        "queue_wait_ms": queue_wait_ms,
        "timeout_seconds": timeout_seconds,
        "max_tokens": max_tokens_value,
        "response_length": response_length,
    }


def _question_failure_reason_label(reason: str) -> str:
    mapping = {
        "ok": "成功",
        "timeout": "超时",
        "empty_text": "空文本",
        "parse_failed": "解析失败",
        "gateway_error": "网关异常",
        "rate_limited": "限流",
        "auth_error": "鉴权失败",
        "no_client": "无可用客户端",
        "no_result": "未产出结果",
        "unknown": "未知",
    }
    return mapping.get(str(reason or "").strip(), str(reason or "未知").strip() or "未知")


def _format_question_tier_attempts_for_log(call_meta: Optional[dict]) -> str:
    attempts = list(call_meta.get("attempts", []) or []) if isinstance(call_meta, dict) else []
    if not attempts:
        return "未知"

    segments = []
    for attempt in attempts:
        if not isinstance(attempt, dict):
            continue
        lane = str(attempt.get("lane", "unknown") or "unknown")
        reason = _question_failure_reason_label(attempt.get("failure_reason", "unknown"))
        extras = []
        if bool(attempt.get("timeout_occurred", False)):
            timeout_seconds = float(attempt.get("timeout_seconds", API_TIMEOUT) or API_TIMEOUT)
            extras.append(f"timeout>{timeout_seconds:g}s")
        queue_wait_ms = float(attempt.get("queue_wait_ms", 0.0) or 0.0)
        if queue_wait_ms >= 1.0:
            extras.append(f"queue={queue_wait_ms:.0f}ms")
        response_length = int(attempt.get("response_length", 0) or 0)
        if response_length > 0:
            extras.append(f"len={response_length}")
        error_kind = str(attempt.get("error_kind", "") or "")
        if error_kind and attempt.get("failure_reason") not in {"timeout", "empty_text", "ok"}:
            extras.append(f"kind={error_kind}")
        detail_suffix = f" ({', '.join(extras)})" if extras else ""
        segments.append(f"{lane}:{reason}{detail_suffix}")
    return "；".join(segments) if segments else "未知"


def reset_question_fast_strategy_state() -> None:
    with question_fast_strategy_lock:
        question_fast_strategy_state["recent"] = deque(
            maxlen=max(QUESTION_FAST_ADAPTIVE_WINDOW_SIZE, QUESTION_FAST_ADAPTIVE_MIN_SAMPLES, 4)
        )
        question_fast_strategy_state["cooldown_until"] = 0.0
        question_fast_strategy_state["last_reason"] = ""
        question_fast_strategy_state["last_hit_rate"] = 0.0
        question_fast_strategy_state["last_sample_size"] = 0
        question_fast_strategy_state["last_opened_at"] = 0.0


def get_question_fast_strategy_snapshot(now_ts: Optional[float] = None) -> dict:
    now_value = _time.time() if now_ts is None else float(now_ts)
    with question_fast_strategy_lock:
        recent = list(question_fast_strategy_state.get("recent", []) or [])
        cooldown_until = float(question_fast_strategy_state.get("cooldown_until", 0.0) or 0.0)
        cooldown_remaining = max(0.0, cooldown_until - now_value)
        sample = recent[-QUESTION_FAST_ADAPTIVE_WINDOW_SIZE:] if QUESTION_FAST_ADAPTIVE_WINDOW_SIZE > 0 else recent
        sample_size = len(sample)
        hit_count = sum(1 for item in sample if isinstance(item, dict) and bool(item.get("success", False)))
        hit_rate = (hit_count / sample_size) if sample_size > 0 else 0.0
        return {
            "cooldown_remaining_seconds": cooldown_remaining,
            "cooldown_active": cooldown_remaining > 0.0,
            "hit_rate": hit_rate,
            "sample_size": sample_size,
            "last_reason": str(question_fast_strategy_state.get("last_reason", "") or ""),
            "last_hit_rate": float(question_fast_strategy_state.get("last_hit_rate", 0.0) or 0.0),
            "last_sample_size": int(question_fast_strategy_state.get("last_sample_size", 0) or 0),
        }


def _record_question_fast_outcome(success: bool, lane: str = "", reason: str = "") -> None:
    if not QUESTION_FAST_ADAPTIVE_ENABLED:
        return

    now_ts = _time.time()
    opened_reason = ""
    with question_fast_strategy_lock:
        recent = question_fast_strategy_state.get("recent")
        if not isinstance(recent, deque):
            recent = deque(maxlen=max(QUESTION_FAST_ADAPTIVE_WINDOW_SIZE, QUESTION_FAST_ADAPTIVE_MIN_SAMPLES, 4))
            question_fast_strategy_state["recent"] = recent

        recent.append({
            "success": bool(success),
            "lane": str(lane or ""),
            "reason": str(reason or ""),
            "timestamp": now_ts,
        })

        if QUESTION_FAST_ADAPTIVE_COOLDOWN_SECONDS <= 0.0:
            return

        cooldown_until = float(question_fast_strategy_state.get("cooldown_until", 0.0) or 0.0)
        if cooldown_until > now_ts:
            return

        sample = list(recent)[-QUESTION_FAST_ADAPTIVE_WINDOW_SIZE:]
        sample_size = len(sample)
        if sample_size < QUESTION_FAST_ADAPTIVE_MIN_SAMPLES:
            return

        hit_count = sum(1 for item in sample if isinstance(item, dict) and bool(item.get("success", False)))
        hit_rate = hit_count / sample_size if sample_size > 0 else 0.0
        question_fast_strategy_state["last_hit_rate"] = hit_rate
        question_fast_strategy_state["last_sample_size"] = sample_size

        if hit_rate < QUESTION_FAST_ADAPTIVE_MIN_HIT_RATE:
            question_fast_strategy_state["cooldown_until"] = now_ts + QUESTION_FAST_ADAPTIVE_COOLDOWN_SECONDS
            opened_reason = (
                f"近{sample_size}次快档命中率{hit_rate:.0%}"
                f"低于阈值{QUESTION_FAST_ADAPTIVE_MIN_HIT_RATE:.0%}"
            )
            question_fast_strategy_state["last_reason"] = opened_reason
            question_fast_strategy_state["last_opened_at"] = now_ts
            recent.clear()

    if opened_reason:
        print(
            f"⚠️ 问题快档自适应停用：{opened_reason}，"
            f"冷却{int(round(QUESTION_FAST_ADAPTIVE_COOLDOWN_SECONDS))}s"
        )


def _get_question_fast_skip_reason(prompt: str, truncated_docs: Optional[list] = None) -> str:
    if not QUESTION_FAST_PATH_ENABLED:
        return "config_disabled"

    prompt_length = len(prompt or "")
    if QUESTION_FAST_LIGHT_PROMPT_MAX_CHARS > 0 and prompt_length > QUESTION_FAST_LIGHT_PROMPT_MAX_CHARS:
        return f"prompt_too_long:{prompt_length}>{QUESTION_FAST_LIGHT_PROMPT_MAX_CHARS}"

    if QUESTION_FAST_SKIP_WHEN_TRUNCATED_DOCS and truncated_docs:
        return f"truncated_docs:{len(truncated_docs)}"

    if QUESTION_FAST_ADAPTIVE_ENABLED:
        snapshot = get_question_fast_strategy_snapshot()
        cooldown_remaining = float(snapshot.get("cooldown_remaining_seconds", 0.0) or 0.0)
        if cooldown_remaining > 0.0:
            return f"adaptive_cooldown:{int(round(cooldown_remaining))}s"

    return ""


def _describe_question_fast_skip_reason(reason: str) -> str:
    text = str(reason or "").strip()
    if not text:
        return "未知原因"
    if text == "config_disabled":
        return "配置关闭"
    if text.startswith("prompt_too_long:"):
        payload = text.split(":", 1)[1]
        return f"prompt 过长（{payload}）"
    if text.startswith("truncated_docs:"):
        payload = text.split(":", 1)[1]
        return f"存在截断文档（{payload}个）"
    if text.startswith("adaptive_cooldown:"):
        payload = text.split(":", 1)[1]
        return f"命中率过低，快档冷却中（剩余{payload}）"
    return text


def _call_question_with_optional_hedge(
    prompt: str,
    max_tokens: int,
    call_type: str,
    truncated_docs: Optional[list] = None,
    timeout: Optional[float] = None,
    retry_on_timeout: bool = False,
    debug: bool = False,
) -> tuple[Optional[str], str, dict]:
    """问题生成可选竞速：主通道先发，延迟触发备用通道，谁先返回可用结果用谁。"""
    primary_lane = "question"
    secondary_lane = QUESTION_HEDGED_SECONDARY_LANE

    def _run_single(lane: str, lane_call_type: str, hedge_flag: bool = False) -> tuple[Optional[str], dict]:
        raw_result = call_claude(
            prompt,
            max_tokens=max_tokens,
            retry_on_timeout=retry_on_timeout,
            call_type=lane_call_type,
            truncated_docs=truncated_docs,
            timeout=timeout,
            preferred_lane=lane,
            hedge_triggered=hedge_flag,
            return_meta=True,
        )
        return _normalize_question_call_result(raw_result, lane=lane, max_tokens=max_tokens, timeout=timeout)

    def _build_attempts_summary(responses: list[tuple[str, Optional[str], dict]], started_lanes: list[str]) -> list[dict]:
        attempt_map = {}
        for resp_lane, resp_text, resp_meta in responses:
            attempt_map[resp_lane] = _build_question_attempt_summary(resp_lane, resp_text, resp_meta)
        for lane_name in started_lanes:
            attempt_map.setdefault(
                lane_name,
                _build_question_attempt_summary(
                    lane_name,
                    None,
                    {
                        "selected_lane": lane_name,
                        "timeout_seconds": float(timeout if timeout is not None else API_TIMEOUT),
                        "max_tokens": int(max_tokens),
                        "failure_reason": "no_result",
                    },
                ),
            )
        return [attempt_map[lane_name] for lane_name in started_lanes if lane_name in attempt_map]

    if not QUESTION_HEDGED_ENABLED or secondary_lane == primary_lane:
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
    delay_deadline = _time.time() + float(QUESTION_HEDGED_DELAY_SECONDS)
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
    finish_deadline = _time.time() + max(2.0, float(timeout if timeout is not None else API_TIMEOUT) + 2.0)
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
    debug: bool = False,
    base_call_type: str = "question",
    allow_fast_path: bool = True,
) -> tuple[Optional[str], Optional[dict], str]:
    """问题生成双档策略：轻量 prompt 才尝试快档，失败时回退全量竞速。"""
    fast_skip_reason = ""
    if allow_fast_path:
        fast_skip_reason = _get_question_fast_skip_reason(prompt, truncated_docs=truncated_docs)

    if allow_fast_path and not fast_skip_reason:
        fast_timeout = min(float(API_TIMEOUT), float(QUESTION_FAST_TIMEOUT))
        fast_response, fast_lane, fast_meta = _call_question_with_optional_hedge(
            prompt,
            max_tokens=QUESTION_FAST_MAX_TOKENS,
            call_type=f"{base_call_type}_fast",
            truncated_docs=truncated_docs,
            timeout=fast_timeout,
            retry_on_timeout=False,
            debug=debug,
        )
        if fast_response:
            fast_result = parse_question_response(fast_response, debug=debug)
            if fast_result:
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
    elif debug and allow_fast_path:
        print(f"ℹ️ 跳过快档：{_describe_question_fast_skip_reason(fast_skip_reason)}，直接走全量竞速")

    full_response, full_lane, full_meta = _call_question_with_optional_hedge(
        prompt,
        max_tokens=MAX_TOKENS_QUESTION,
        call_type=base_call_type,
        truncated_docs=truncated_docs,
        retry_on_timeout=True,
        debug=debug,
    )
    full_result = parse_question_response(full_response, debug=debug) if full_response else None
    if debug and not full_response:
        print(f"⚠️ 全量档未命中，原因: {_format_question_tier_attempts_for_log(full_meta)}")
    elif debug and full_response and not full_result:
        response_length = int(full_meta.get("response_length", len(full_response)) or len(full_response))
        print(f"⚠️ 全量档响应解析失败: lane={full_lane}, len={response_length}")
    return full_response, full_result, f"full:{full_lane}"


@app.route('/api/sessions/<session_id>/next-question', methods=['POST'])
def get_next_question(session_id):
    """获取下一个问题（AI 生成）"""
    user_id = get_current_user_id_or_none()
    if not user_id:
        return jsonify({"error": "请先登录"}), 401

    loaded = load_session_for_user(session_id, user_id)
    if len(loaded) == 3:
        _file, error_msg, status_code = loaded
        return jsonify({"error": error_msg}), status_code

    session_file, session = loaded
    data = request.get_json() or {}
    default_dim = get_dimension_order_for_session(session)[0] if get_dimension_order_for_session(session) else "customer_needs"
    dimension = data.get("dimension", default_dim)
    session_signature = get_file_signature(session_file)
    question_cache_key = _build_question_result_cache_key(session_id, dimension, session_signature)

    cached_question_payload = _get_question_result_cache(question_cache_key)
    if isinstance(cached_question_payload, dict):
        if ENABLE_DEBUG_LOG:
            print(f"📦 命中问题结果缓存: session={session_id}, dimension={dimension}")
        _record_cache_hit_metric("question_result_cache_hit")
        cached_question_payload["cached"] = True
        return jsonify(cached_question_payload)

    # ========== 步骤5: 检查预生成缓存 ==========
    prefetched = get_prefetch_result(session_id, dimension)
    if prefetched:
        if ENABLE_DEBUG_LOG:
            print(f"🎯 预生成缓存命中: session={session_id}, dimension={dimension}")
        _record_cache_hit_metric("question_prefetch_cache_hit")

        # 先检查维度是否已完成（即使有缓存也要检查）
        dim_data = session.get("dimensions", {}).get(dimension, {})
        dim_coverage = dim_data.get("coverage", 0)
        user_completed = dim_data.get("user_completed", False)
        if dim_coverage >= 100 or user_completed:
            # 维度已完成，忽略缓存，返回完成状态
            all_dim_logs = [log for log in session.get("interview_log", []) if log.get("dimension") == dimension]
            formal_questions_count = len([log for log in all_dim_logs if not log.get("is_follow_up", False)])
            dim_follow_ups = len([log for log in all_dim_logs if log.get("is_follow_up", False)])
            completion_reason = dim_data.get("completion_reason") or ("user_completed" if user_completed else "auto_completed")
            quality_warning = bool(dim_data.get("quality_warning", False))
            return jsonify({
                "dimension": dimension,
                "completed": True,
                "completion_reason": completion_reason,
                "quality_warning": quality_warning,
                "decision_meta": {
                    "mode": get_mode_identifier(session),
                    "follow_up_round": get_follow_up_round_for_dimension_logs(all_dim_logs),
                    "remaining_question_follow_up_budget": max(
                        0,
                        get_interview_mode_config(session).get("max_questions_per_formal", 1)
                        - get_follow_up_round_for_dimension_logs(all_dim_logs)
                    ),
                    "hard_triggered": False,
                    "missing_aspects": get_dimension_missing_aspects(session, dimension),
                },
                "stats": {
                    "formal_questions": formal_questions_count,
                    "follow_ups": dim_follow_ups,
                    "saturation": 1.0
                }
            })

        # 对预生成结果也做 is_follow_up 校验
        all_dim_logs = [log for log in session.get("interview_log", []) if log.get("dimension") == dimension]
        if prefetched.get("is_follow_up", False) and all_dim_logs:
            last_log = all_dim_logs[-1]
            eval_result = evaluate_answer_depth(
                question=last_log.get("question", ""),
                answer=last_log.get("answer", ""),
                dimension=dimension,
                options=last_log.get("options", []),
                is_follow_up=last_log.get("is_follow_up", False),
            )
            comprehensive_check = should_follow_up_comprehensive(
                session=session,
                dimension=dimension,
                rule_based_result=eval_result
            )
            if not comprehensive_check["should_follow_up"]:
                if ENABLE_DEBUG_LOG:
                    print(f"⚠️ 预生成缓存 is_follow_up=true 但后端决策不允许，强制覆盖为 false")
                prefetched["is_follow_up"] = False
                prefetched["follow_up_reason"] = None

        prefetched["decision_meta"] = {
            "mode": get_mode_identifier(session),
            "follow_up_round": get_follow_up_round_for_dimension_logs(all_dim_logs),
            "remaining_question_follow_up_budget": max(
                0,
                get_interview_mode_config(session).get("max_questions_per_formal", 1)
                - get_follow_up_round_for_dimension_logs(all_dim_logs)
            ),
            "hard_triggered": False,
            "missing_aspects": get_dimension_missing_aspects(session, dimension),
        }

        prefetched["prefetched"] = True
        _set_question_result_cache(question_cache_key, prefetched)
        return jsonify(prefetched)

    # 检查是否有 Claude API
    if not resolve_ai_client(call_type="question"):
        if ENABLE_DEBUG_LOG:
            print(f"ℹ️ AI 未启用，使用 fallback 题库: session={session_id}, dimension={dimension}")
        fallback = get_fallback_question(session, dimension)
        return jsonify(fallback)

    # 获取当前维度的所有记录
    all_dim_logs = [log for log in session.get("interview_log", []) if log.get("dimension") == dimension]

    # 计算正式问题数量（排除追问）
    formal_questions_count = len([log for log in all_dim_logs if not log.get("is_follow_up", False)])

    # 获取访谈模式配置
    mode_config = get_interview_mode_config(session)

    # 获取当前维度状态
    dim_data = session.get("dimensions", {}).get(dimension, {})
    dim_coverage = dim_data.get("coverage", 0)
    user_completed = dim_data.get("user_completed", False)

    # 维度已完成（用户手动完成或自动完成）
    if dim_coverage >= 100 or user_completed:
        dim_follow_ups = len([log for log in all_dim_logs if log.get("is_follow_up", False)])
        completion_reason = dim_data.get("completion_reason") or ("user_completed" if user_completed else "auto_completed")
        quality_warning = bool(dim_data.get("quality_warning", False))
        return jsonify({
            "dimension": dimension,
            "completed": True,
            "completion_reason": completion_reason,
            "quality_warning": quality_warning,
            "decision_meta": {
                "mode": get_mode_identifier(session),
                "follow_up_round": get_follow_up_round_for_dimension_logs(all_dim_logs),
                "remaining_question_follow_up_budget": max(0, mode_config.get("max_questions_per_formal", 1) - get_follow_up_round_for_dimension_logs(all_dim_logs)),
                "hard_triggered": False,
                "missing_aspects": get_dimension_missing_aspects(session, dimension),
            },
            "stats": {
                "formal_questions": formal_questions_count,
                "follow_ups": dim_follow_ups,
                "saturation": 1.0
            }
        })

    completion = evaluate_dimension_completion_v2(session, dimension)
    if completion.get("can_complete"):
        # 自动完成需持久化，否则后续读取会出现覆盖率回退
        dim_state = session.setdefault("dimensions", {}).setdefault(dimension, {})
        dim_state["coverage"] = 100
        dim_state["auto_completed"] = True
        dim_state["completion_reason"] = completion.get("reason") or "quality_gate_passed"
        dim_state["quality_warning"] = bool(completion.get("quality_warning", False))

        session["updated_at"] = get_utc_now()
        save_session_json_and_sync(session_file, session)

        dim_follow_ups = len([log for log in all_dim_logs if log.get("is_follow_up", False)])
        snapshot = completion.get("snapshot", {})
        return jsonify({
            "dimension": dimension,
            "completed": True,
            "completion_reason": dim_state.get("completion_reason"),
            "quality_warning": bool(dim_state.get("quality_warning", False)),
            "decision_meta": {
                "mode": get_mode_identifier(session),
                "follow_up_round": snapshot.get("follow_up_round", get_follow_up_round_for_dimension_logs(all_dim_logs)),
                "remaining_question_follow_up_budget": max(0, mode_config.get("max_questions_per_formal", 1) - snapshot.get("follow_up_round", 0)),
                "hard_triggered": bool(snapshot.get("pending_forced_follow_up", False)),
                "missing_aspects": snapshot.get("missing_aspects", []),
            },
            "stats": {
                "formal_questions": formal_questions_count,
                "follow_ups": dim_follow_ups,
                "saturation": snapshot.get("saturation", 0)
            }
        })

    # 调用 Claude 生成问题
    # 判断是否会有搜索（用于设置正确的阶段数）
    has_search = should_search(session.get("topic", ""), dimension, session)

    try:
        # 阶段1: 分析回答
        update_thinking_status(session_id, "analyzing", has_search)

        prompt, truncated_docs, decision_meta = build_interview_prompt(
            session,
            dimension,
            all_dim_logs,
            session_id=session_id,
            session_signature=session_signature,
        )

        # 日志：记录 prompt 长度（便于监控和调优）
        if ENABLE_DEBUG_LOG:
            ref_docs_count = len(session.get("reference_materials", session.get("reference_docs", []) + session.get("research_docs", [])))
            print(f"📊 访谈 Prompt 统计：总长度={len(prompt)}字符，参考资料={ref_docs_count}个")
            if truncated_docs:
                print(f"⚠️  文档截断：{len(truncated_docs)}个文档被截断")

        # 阶段3: 生成问题
        update_thinking_status(session_id, "generating", has_search)

        response, result, tier_used = generate_question_with_tiered_strategy(
            prompt,
            truncated_docs=truncated_docs,
            debug=ENABLE_DEBUG_LOG,
            base_call_type="question",
            allow_fast_path=True,
        )
        if ENABLE_DEBUG_LOG:
            print(f"⚙️ 问题生成通道: {tier_used}")

        if not response:
            # 清除思考状态
            clear_thinking_status(session_id)
            return jsonify({
                "error": "AI 响应失败",
                "detail": "未能从 AI 服务获取响应，请检查网络连接或稍后重试"
            }), 503

        if result:
            result["dimension"] = dimension
            result["ai_generated"] = True
            result["decision_meta"] = decision_meta
            # 兜底：避免连续重复问题（最多自动重试一次）
            last_log = all_dim_logs[-1] if all_dim_logs else None
            if last_log and last_log.get("question") == result.get("question"):
                if ENABLE_DEBUG_LOG:
                    print("⚠️ 检测到重复问题，自动重试一次")
                retry_response, retry_result, retry_tier = generate_question_with_tiered_strategy(
                    prompt,
                    truncated_docs=truncated_docs,
                    debug=ENABLE_DEBUG_LOG,
                    base_call_type="question_retry",
                    allow_fast_path=False,
                )
                if ENABLE_DEBUG_LOG:
                    print(f"⚙️ 重复问题重试通道: {retry_tier}")
                if retry_result and retry_result.get("question") != last_log.get("question"):
                    retry_result["dimension"] = dimension
                    retry_result["ai_generated"] = True
                    retry_result["decision_meta"] = decision_meta
                    result = retry_result
                else:
                    # 清除思考状态
                    clear_thinking_status(session_id)
                    return jsonify({
                        "error": "生成重复问题",
                        "detail": "检测到重复问题，请重试"
                    }), 503

            # ========== 后端强制校验 is_follow_up ==========
            # 防止 AI 绕过追问预算控制，自行将问题标记为追问
            if result.get("is_follow_up", False):
                # 重新计算追问决策
                last_log = all_dim_logs[-1] if all_dim_logs else None
                if last_log:
                    eval_result = evaluate_answer_depth(
                        question=last_log.get("question", ""),
                        answer=last_log.get("answer", ""),
                        dimension=dimension,
                        options=last_log.get("options", []),
                        is_follow_up=last_log.get("is_follow_up", False),
                    )
                    comprehensive_check = should_follow_up_comprehensive(
                        session=session,
                        dimension=dimension,
                        rule_based_result=eval_result
                    )
                    if not comprehensive_check["should_follow_up"]:
                        if ENABLE_DEBUG_LOG:
                            print(f"⚠️ AI 返回 is_follow_up=true 但后端决策不允许追问，强制覆盖为 false (原因: {comprehensive_check['reason']})")
                        result["is_follow_up"] = False
                        result["follow_up_reason"] = None

            # 清除思考状态
            clear_thinking_status(session_id)
            # ========== 步骤5: 触发预生成（如果需要）==========
            trigger_prefetch_if_needed(session, dimension)
            _set_question_result_cache(question_cache_key, result)
            return jsonify(result)

        # 解析失败
        # 清除思考状态
        clear_thinking_status(session_id)
        return jsonify({
            "error": "AI 响应格式错误",
            "detail": "AI 返回的内容无法解析为有效的 JSON 格式。请点击「重试」按钮重新生成问题。"
        }), 503

    except Exception as e:
        # 清除思考状态
        clear_thinking_status(session_id)
        print(f"生成问题时发生异常: {e}")
        error_msg = str(e)

        # 根据异常类型提供更具体的错误信息
        if "connection" in error_msg.lower() or "network" in error_msg.lower():
            return jsonify({
                "error": "网络连接失败",
                "detail": "无法连接到 AI 服务，请检查网络连接"
            }), 503
        elif "timeout" in error_msg.lower():
            return jsonify({
                "error": "请求超时",
                "detail": "AI 服务响应超时，请稍后重试"
            }), 503
        elif "authentication" in error_msg.lower() or "api key" in error_msg.lower():
            return jsonify({
                "error": "API 认证失败",
                "detail": "API Key 无效或已过期，请联系管理员"
            }), 503
        elif "rate limit" in error_msg.lower():
            return jsonify({
                "error": "请求频率超限",
                "detail": "AI 服务请求过于频繁，请稍后再试"
            }), 503
        else:
            return jsonify({
                "error": "生成问题失败",
                "detail": f"发生未知错误: {error_msg}"
            }), 503


def get_fallback_question(session: dict, dimension: str) -> dict:
    """获取备用问题（无 AI 时使用）"""
    fallback_questions = {
        "customer_needs": [
            {"question": "您希望通过这个项目解决哪些核心问题？", "options": ["提升工作效率", "降低运营成本", "改善用户体验", "增强数据分析能力"], "multi_select": True},
            {"question": "主要的用户群体有哪些？", "options": ["内部员工", "外部客户", "合作伙伴", "管理层"], "multi_select": True},
            {"question": "用户最期望获得的核心价值是什么？", "options": ["节省时间", "减少错误", "获取洞察", "提升协作"], "multi_select": False},
        ],
        "business_process": [
            {"question": "当前业务流程中需要优化的环节有哪些？", "options": ["数据录入", "审批流程", "报表生成", "跨部门协作"], "multi_select": True},
            {"question": "关键业务流程涉及哪些部门？", "options": ["销售部门", "技术部门", "财务部门", "运营部门"], "multi_select": True},
            {"question": "流程中最关键的决策节点是什么？", "options": ["审批节点", "分配节点", "验收节点", "结算节点"], "multi_select": False},
        ],
        "tech_constraints": [
            {"question": "期望的系统部署方式是？", "options": ["公有云部署", "私有云部署", "混合云部署", "本地部署"], "multi_select": False},
            {"question": "需要与哪些现有系统集成？", "options": ["ERP系统", "CRM系统", "OA办公系统", "财务系统"], "multi_select": True},
            {"question": "对系统安全性的要求是？", "options": ["等保二级", "等保三级", "基础安全即可", "需要详细评估"], "multi_select": False},
        ],
        "project_constraints": [
            {"question": "项目的预期预算范围是？", "options": ["10万以内", "10-50万", "50-100万", "100万以上"], "multi_select": False},
            {"question": "期望的上线时间是？", "options": ["1个月内", "1-3个月", "3-6个月", "6个月以上"], "multi_select": False},
            {"question": "项目团队的资源情况如何？", "options": ["有专职团队", "兼职参与", "完全外包", "需要评估"], "multi_select": False},
        ]
    }

    # 获取该维度已回答的问题数
    answered = len([log for log in session.get("interview_log", []) if log.get("dimension") == dimension])
    questions = fallback_questions.get(dimension, [])

    if answered < len(questions):
        q = questions[answered]
        return {
            "question": q["question"],
            "options": q["options"],
            "multi_select": q.get("multi_select", False),
            "dimension": dimension,
            "ai_generated": False,
            "is_follow_up": False,
            "ai_recommendation": None
        }

    # 维度已完成
    return {
        "question": None,
        "dimension": dimension,
        "completed": True,
        "ai_recommendation": None
    }


@app.route('/api/sessions/<session_id>/submit-answer', methods=['POST'])
def submit_answer(session_id):
    """提交回答"""
    user_id = get_current_user_id_or_none()
    if not user_id:
        return jsonify({"error": "请先登录"}), 401

    loaded = load_session_for_user(session_id, user_id)
    if len(loaded) == 3:
        _file, error_msg, status_code = loaded
        return jsonify({"error": error_msg}), status_code

    session_file, session = loaded

    # 验证请求数据
    data = request.get_json()
    if not data:
        return jsonify({"error": "无效的请求数据"}), 400

    question = data.get("question")
    answer = data.get("answer")
    dimension = data.get("dimension")
    options = data.get("options", [])
    other_selected = data.get("other_selected", False)
    other_answer_text = data.get("other_answer_text", "")
    is_follow_up = data.get("is_follow_up", False)

    # 验证必需参数
    if not question or not isinstance(question, str):
        return jsonify({"error": "问题不能为空"}), 400
    if not answer or not isinstance(answer, str):
        return jsonify({"error": "答案不能为空"}), 400
    if len(answer) > 5000:
        return jsonify({"error": "答案长度不能超过5000字符"}), 400
    if not dimension or dimension not in session.get("dimensions", {}):
        return jsonify({"error": "无效的维度"}), 400
    if not isinstance(options, list):
        return jsonify({"error": "选项必须是列表"}), 400
    if not isinstance(other_selected, bool):
        return jsonify({"error": "other_selected必须是布尔值"}), 400
    if other_answer_text is None:
        other_answer_text = ""
    if not isinstance(other_answer_text, str):
        return jsonify({"error": "other_answer_text必须是字符串"}), 400
    if len(other_answer_text) > 2000:
        return jsonify({"error": "自定义答案长度不能超过2000字符"}), 400
    if not isinstance(is_follow_up, bool):
        return jsonify({"error": "is_follow_up必须是布尔值"}), 400

    # 使用增强版评估函数判断回答是否需要追问
    eval_result = evaluate_answer_depth(
        question=question,
        answer=answer,
        dimension=dimension,
        options=options,
        is_follow_up=is_follow_up,
    )
    needs_follow_up = eval_result["needs_follow_up"]
    follow_up_signals = eval_result["signals"]

    dim_logs_before = [log for log in session.get("interview_log", []) if log.get("dimension") == dimension]
    follow_up_round = get_follow_up_round_for_dimension_logs(dim_logs_before)
    if not is_follow_up:
        follow_up_round = 0
    else:
        follow_up_round += 1

    quality_result = evaluate_answer_quality(
        eval_result=eval_result,
        answer=answer,
        is_follow_up=is_follow_up,
        follow_up_round=follow_up_round,
    )

    if ENABLE_DEBUG_LOG and (needs_follow_up or eval_result["suggest_ai_eval"]):
        print(f"📝 回答评估: signals={follow_up_signals}, needs_follow_up={needs_follow_up}")

    # 添加到访谈记录
    log_entry = {
        "timestamp": get_utc_now(),
        "question": question,
        "answer": answer,
        "dimension": dimension,
        "options": options,
        "other_selected": other_selected,
        "other_answer_text": other_answer_text,
        "is_follow_up": is_follow_up,
        "needs_follow_up": needs_follow_up,
        "follow_up_signals": follow_up_signals,  # 记录检测到的信号
        "quality_score": quality_result["quality_score"],
        "quality_signals": quality_result["quality_signals"],
        "hard_triggered": quality_result["hard_triggered"],
        "follow_up_round": follow_up_round,
    }
    session["interview_log"].append(log_entry)

    # 更新维度数据（只有正式问题才添加到维度需求列表）
    if dimension and dimension in session["dimensions"] and not is_follow_up:
        session["dimensions"][dimension]["items"].append({
            "name": answer,
            "description": question,
            "priority": "中"
        })

    # 计算覆盖度（只统计正式问题，追问不计入）
    if dimension and dimension in session["dimensions"]:
        session["dimensions"][dimension]["coverage"] = calculate_dimension_coverage(session, dimension)

    # 评估场景：为每次回答进行 AI 评分
    is_assessment = session.get("scenario_config", {}).get("report", {}).get("type") == "assessment"
    if is_assessment and dimension and dimension in session["dimensions"]:
        score = score_assessment_answer(session, dimension, question, answer)
        if score is not None:
            # 记录本次回答的评分
            log_entry["score"] = score
            # 更新维度的综合评分（取该维度所有评分的平均值）
            dim_scores = [
                log.get("score") for log in session["interview_log"]
                if log.get("dimension") == dimension and log.get("score") is not None
            ]
            if dim_scores:
                session["dimensions"][dimension]["score"] = round(sum(dim_scores) / len(dim_scores), 2)
            if ENABLE_DEBUG_LOG:
                print(f"📊 评估评分: {dimension} = {score}分，维度均分 = {session['dimensions'][dimension].get('score')}")

    session["updated_at"] = get_utc_now()
    save_session_json_and_sync(session_file, session)

    # 异步更新上下文摘要（超过阈值且满足节流时触发）
    if len(session.get("interview_log", [])) >= SUMMARY_THRESHOLD:
        schedule_context_summary_update_async(session_id)

    return jsonify(session)


@app.route('/api/sessions/<session_id>/undo-answer', methods=['POST'])
def undo_answer(session_id):
    """撤销最后一个回答"""
    user_id = get_current_user_id_or_none()
    if not user_id:
        return jsonify({"error": "请先登录"}), 401

    loaded = load_session_for_user(session_id, user_id)
    if len(loaded) == 3:
        _file, error_msg, status_code = loaded
        return jsonify({"error": error_msg}), status_code

    session_file, session = loaded

    # 检查是否有回答可以撤销
    if not session.get("interview_log") or len(session["interview_log"]) == 0:
        return jsonify({"error": "没有可撤销的回答"}), 400

    # 删除最后一个回答
    last_log = session["interview_log"].pop()
    dimension = last_log.get("dimension")
    was_follow_up = last_log.get("is_follow_up", False)

    # 更新维度数据（只有正式问题才影响维度 items）
    if dimension and dimension in session["dimensions"]:
        # 只有删除的是正式问题时，才从 items 中删除
        if not was_follow_up and session["dimensions"][dimension]["items"]:
            session["dimensions"][dimension]["items"].pop()

        # 重新计算覆盖度（只统计正式问题）
        session["dimensions"][dimension]["coverage"] = calculate_dimension_coverage(session, dimension)

    session["updated_at"] = get_utc_now()
    save_session_json_and_sync(session_file, session)

    return jsonify(session)


@app.route('/api/sessions/<session_id>/skip-follow-up', methods=['POST'])
def skip_follow_up(session_id):
    """
    用户主动跳过当前问题的追问
    标记最后一个正式问题的回答为"不需要追问"
    """
    user_id = get_current_user_id_or_none()
    if not user_id:
        return jsonify({"error": "请先登录"}), 401

    loaded = load_session_for_user(session_id, user_id)
    if len(loaded) == 3:
        _file, error_msg, status_code = loaded
        return jsonify({"error": error_msg}), status_code

    session_file, session = loaded
    data = request.get_json() or {}
    dimension = data.get("dimension")

    # 验证 dimension
    if not dimension or dimension not in session.get("dimensions", {}):
        return jsonify({"error": "无效的维度"}), 400

    interview_log = session.get("interview_log", [])
    if not interview_log:
        return jsonify({"error": "没有可跳过的问题"}), 400

    # 找到当前维度的最后一个正式问题
    dim_logs = [log for log in interview_log if log.get("dimension") == dimension]
    formal_logs = [log for log in dim_logs if not log.get("is_follow_up", False)]

    if not formal_logs:
        return jsonify({"error": "没有可跳过的正式问题"}), 400

    # 标记最后一个正式问题不需要追问
    last_formal = formal_logs[-1]
    last_formal["needs_follow_up"] = False
    last_formal["user_skip_follow_up"] = True  # 标记为用户主动跳过

    session["updated_at"] = get_utc_now()
    save_session_json_and_sync(session_file, session)

    if ENABLE_DEBUG_LOG:
        print(f"⏭️ 用户跳过追问: dimension={dimension}")

    return jsonify({"success": True, "message": "已跳过追问"})


@app.route('/api/sessions/<session_id>/complete-dimension', methods=['POST'])
def complete_dimension(session_id):
    """
    用户主动完成当前维度
    将当前维度标记为已完成（覆盖度设为100%）
    """
    user_id = get_current_user_id_or_none()
    if not user_id:
        return jsonify({"error": "请先登录"}), 401

    loaded = load_session_for_user(session_id, user_id)
    if len(loaded) == 3:
        _file, error_msg, status_code = loaded
        return jsonify({"error": error_msg}), status_code

    session_file, session = loaded
    data = request.get_json() or {}
    dimension = data.get("dimension")

    # 验证维度有效性
    if not dimension or dimension not in session.get("dimensions", {}):
        return jsonify({"error": "无效的维度"}), 400

    # 检查覆盖度是否已达到至少 50%
    current_coverage = session["dimensions"][dimension]["coverage"]
    if current_coverage < 50:
        return jsonify({
            "error": "无法完成维度",
            "detail": "当前维度覆盖度不足50%，建议至少回答一半问题后再跳过"
        }), 400

    # 标记所有该维度的回答为不需要追问
    for log in session.get("interview_log", []):
        if log.get("dimension") == dimension and not log.get("is_follow_up", False):
            log["needs_follow_up"] = False

    # 将维度覆盖度设为 100%
    session["dimensions"][dimension]["coverage"] = 100
    session["dimensions"][dimension]["user_completed"] = True  # 标记为用户主动完成
    session["dimensions"][dimension]["auto_completed"] = False
    session["dimensions"][dimension]["completion_reason"] = "user_completed"
    session["dimensions"][dimension]["quality_warning"] = False

    session["updated_at"] = get_utc_now()
    save_session_json_and_sync(session_file, session)

    if ENABLE_DEBUG_LOG:
        print(f"⏭️ 用户完成维度: dimension={dimension}, coverage={current_coverage}%")

    session_dim_info = get_dimension_info_for_session(session)
    dim_name = session_dim_info.get(dimension, {}).get('name', dimension)
    return jsonify({"success": True, "message": f"{dim_name}维度已完成"})


# ============ 文档上传 API ============

@app.route('/api/sessions/<session_id>/documents', methods=['POST'])
def upload_document(session_id):
    """上传参考文档"""
    user_id = get_current_user_id_or_none()
    if not user_id:
        return jsonify({"error": "请先登录"}), 401

    loaded = load_session_for_user(session_id, user_id)
    if len(loaded) == 3:
        _file, error_msg, status_code = loaded
        return jsonify({"error": error_msg}), status_code

    session_file, session = loaded

    if 'file' not in request.files:
        return jsonify({"error": "未找到文件"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "文件名为空"}), 400

    # 验证文件大小（最大10MB）
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    file.seek(0, 2)  # 移动到文件末尾
    file_size = file.tell()
    file.seek(0)  # 重置文件指针
    if file_size > MAX_FILE_SIZE:
        return jsonify({"error": f"文件大小超过限制（最大{MAX_FILE_SIZE // 1024 // 1024}MB）"}), 400

    original_filename = Path(file.filename or "").name.strip()
    if not original_filename:
        return jsonify({"error": "文件名无效"}), 400

    display_filename = sanitize_filename(original_filename)
    if not display_filename:
        return jsonify({"error": "文件名无效"}), 400

    safe_filename = secure_filename(display_filename)
    if not safe_filename:
        fallback_ext = Path(display_filename).suffix.lower()
        safe_filename = f"upload{fallback_ext or '.txt'}"

    ext = Path(display_filename).suffix.lower()
    supported_image_types = {str(item).lower() for item in SUPPORTED_IMAGE_TYPES}
    allowed_upload_types = supported_image_types | {'.md', '.txt', '.pdf', '.docx', '.xlsx', '.pptx'}
    if ext not in allowed_upload_types:
        return jsonify({"error": f"不支持的文件类型: {ext or '未知'}"}), 400

    temp_stem = secure_filename(Path(safe_filename).stem)[:80] or "upload"
    temp_filename = f"{temp_stem}-{secrets.token_hex(8)}{ext}"
    filepath = (TEMP_DIR / temp_filename).resolve()
    if not is_path_under(filepath, TEMP_DIR):
        return jsonify({"error": "文件保存路径无效"}), 400

    file.save(str(filepath))
    filename = display_filename

    # 读取文件内容
    content = ""

    try:
        # 图片处理
        if ext in supported_image_types:
            content = describe_image_with_vision(filepath, filename)
        elif ext in ['.md', '.txt']:
            content = filepath.read_text(encoding="utf-8")
            if not content or not content.strip():
                return jsonify({"error": "文件内容为空"}), 400
        elif ext in ['.pdf', '.docx', '.xlsx', '.pptx']:
            # 调用转换脚本
            import subprocess
            convert_script = SKILL_DIR / "scripts" / "convert_doc.py"
            if convert_script.exists():
                try:
                    result = subprocess.run(
                        ["uv", "run", str(convert_script), "convert", str(filepath)],
                        capture_output=True, text=True, cwd=str(SKILL_DIR)
                    )
                    if result.returncode == 0:
                        converted_file = CONVERTED_DIR / f"{filepath.stem}.md"
                        if converted_file.exists():
                            content = converted_file.read_text(encoding="utf-8")
                        else:
                            content = f"[{ext.upper()[1:]} 解析失败: 未找到转换后的文件]"
                    else:
                        error_msg = result.stderr[:200] if result.stderr else "未知错误"
                        content = f"[{ext.upper()[1:]} 解析失败: {error_msg}]"
                except Exception as e:
                    print(f"转换文档失败: {e}")
                    content = f"[{ext.upper()[1:]} 解析失败: {str(e)[:200]}]"
            else:
                content = f"[{ext.upper()[1:]} 文件: {filename}] (转换脚本不存在)"
    except UnicodeDecodeError as e:
        return jsonify({"error": f"文件编码错误: {str(e)}"}), 400
    except Exception as e:
        return jsonify({"error": f"文件处理失败: {str(e)}"}), 500

    if not content or not content.strip():
        return jsonify({"error": "文件解析后内容为空"}), 400

    # 更新会话
    # 数据迁移：兼容旧会话
    session = migrate_session_docs(session)
    session["reference_materials"].append({
        "name": filename,
        "type": ext,
        "content": content[:10000],  # 限制长度
        "source": "upload",  # 用户上传
        "uploaded_at": get_utc_now()
    })
    session["updated_at"] = get_utc_now()
    save_session_json_and_sync(session_file, session)

    return jsonify({
        "success": True,
        "filename": filename,
        "content_length": len(content)
    })


@app.route('/api/sessions/<session_id>/documents/<path:doc_name>', methods=['DELETE'])
def delete_document(session_id, doc_name):
    """删除参考资料（软删除）"""
    # 路径遍历防护
    if '..' in doc_name or doc_name.startswith('/'):
        return jsonify({"error": "无效的文档名"}), 400

    user_id = get_current_user_id_or_none()
    if not user_id:
        return jsonify({"error": "请先登录"}), 401

    loaded = load_session_for_user(session_id, user_id)
    if len(loaded) == 3:
        _file, error_msg, status_code = loaded
        return jsonify({"error": error_msg}), status_code

    session_file, session = loaded
    # 数据迁移：兼容旧会话
    session = migrate_session_docs(session)

    # 查找并删除文档
    original_count = len(session["reference_materials"])
    session["reference_materials"] = [
        doc for doc in session["reference_materials"]
        if doc["name"] != doc_name
    ]

    if len(session["reference_materials"]) == original_count:
        return jsonify({"error": "文档不存在"}), 404

    session["updated_at"] = get_utc_now()
    save_session_json_and_sync(session_file, session)

    # 软删除：记录到删除日志，文件保留在 temp/converted 目录
    mark_doc_as_deleted(session_id, doc_name)

    return jsonify({
        "success": True,
        "deleted": doc_name,
        "message": "文档已从列表中移除（文件已存档）"
    })


# ============ 重新访谈 API ============

@app.route('/api/sessions/<session_id>/restart-interview', methods=['POST'])
def restart_interview(session_id):
    """重新访谈：将当前访谈记录保存为参考资料，然后重置访谈状态"""
    user_id = get_current_user_id_or_none()
    if not user_id:
        return jsonify({"error": "请先登录"}), 401

    loaded = load_session_for_user(session_id, user_id)
    if len(loaded) == 3:
        _file, error_msg, status_code = loaded
        return jsonify({"error": error_msg}), status_code

    session_file, session = loaded
    # 数据迁移：兼容旧会话
    session = migrate_session_docs(session)

    # 整理当前访谈记录为 markdown 格式
    interview_log = session.get("interview_log", [])
    if not interview_log:
        return jsonify({"error": "没有访谈记录可以保存"}), 400

    # 生成访谈记录文档内容
    research_content = f"""# 访谈记录 - {session.get('topic', '未命名访谈')}

生成时间: {get_utc_now()}

"""

    if session.get("description"):
        # 清理描述中的特殊字符
        desc = session['description'].replace('\n', ' ').replace('\r', '')
        research_content += f"主题描述: {desc}\n\n"

    research_content += "## 访谈记录\n\n"

    # 按维度整理访谈记录
    restart_dim_info = get_dimension_info_for_session(session)
    for dim_key, dim_info in restart_dim_info.items():
        dim_logs = [log for log in interview_log if log.get("dimension") == dim_key]
        if dim_logs:
            research_content += f"### {dim_info['name']}\n\n"
            for log in dim_logs:
                # 清理文本中的特殊字符，避免影响 JSON 解析
                question = log.get('question', '').replace('**', '').replace('`', '')
                answer = log.get('answer', '').replace('**', '').replace('`', '')

                research_content += f"问题：{question}\n\n"
                research_content += f"回答：{answer}\n\n"

                if log.get('follow_up_question'):
                    follow_q = log['follow_up_question'].replace('**', '').replace('`', '')
                    follow_a = log.get('follow_up_answer', '').replace('**', '').replace('`', '')
                    research_content += f"追问: {follow_q}\n\n"
                    research_content += f"回答: {follow_a}\n\n"
                research_content += "---\n\n"

    # 添加到参考资料列表
    doc_name = f"访谈记录-{get_utc_now().replace(':', '-').replace(' ', '_')}.md"

    # 限制内容长度，避免过长导致 AI prompt 问题
    max_length = 2000
    if len(research_content) > max_length:
        research_content = research_content[:max_length] + "\n\n...(内容过长已截断)"

    session["reference_materials"].append({
        "name": doc_name,
        "type": ".md",
        "content": research_content,
        "source": "auto",  # 系统自动生成
        "uploaded_at": get_utc_now()
    })

    # 重置访谈状态 - 从场景配置动态创建维度
    session["interview_log"] = []
    reset_dim_info = get_dimension_info_for_session(session)
    session["dimensions"] = {
        dim_key: {"coverage": 0, "items": [], "score": None}
        for dim_key in reset_dim_info
    }
    session["status"] = "in_progress"  # 重置状态为进行中
    session["updated_at"] = get_utc_now()

    # 保存会话
    save_session_json_and_sync(session_file, session)

    return jsonify({
        "success": True,
        "message": "已保存当前访谈内容并重置访谈",
        "research_doc_name": doc_name
    })


# ============ 报告生成 API ============

V3_FAILOVER_FIXABLE_SINGLE_ISSUE_TYPES = {
    "blindspot",
    "style_template_violation",
    "quality_gate_expression",
    "quality_gate_table",
    "quality_gate_milestone",
    "quality_gate_actionability",
    "quality_gate_acceptance",
}


def should_retry_v3_with_failover(v3_result: Optional[dict]) -> bool:
    """判断 V3 失败后是否值得切备用网关再试一次。"""
    if not isinstance(v3_result, dict):
        return True

    reason = str(v3_result.get("reason", "") or "").strip().lower()
    error = str(v3_result.get("error", "") or "").strip().lower()
    issue_types = summarize_issue_types_v3(v3_result.get("review_issues", []))
    try:
        final_issue_count = int(v3_result.get("final_issue_count", len(v3_result.get("review_issues", []) or [])) or 0)
    except Exception:
        final_issue_count = len(v3_result.get("review_issues", []) or [])

    if reason in {"review_gate_failed", "quality_gate_failed", "review_not_passed_or_quality_gate_failed"}:
        if not REPORT_V3_FAILOVER_ON_SINGLE_ISSUE:
            return False
        if final_issue_count != 1 or len(issue_types) != 1:
            return False
        return issue_types[0] in V3_FAILOVER_FIXABLE_SINGLE_ISSUE_TYPES

    # 质量门禁未通过属于内容质量问题，切网关通常无收益
    if reason in {"draft_generation_failed", "review_generation_failed", "exception", "v3_pipeline_returned_empty"}:
        return True

    network_hints = (
        "timeout",
        "timed out",
        "connection",
        "gateway",
        "504",
        "502",
        "503",
        "429",
        "rate limit",
    )
    if any(hint in error for hint in network_hints):
        return True

    # 解析失败通常与网关输出风格相关（例如返回额外说明/包装文本），
    # 在备用网关上重试一次通常有收益。
    if reason in {"draft_parse_failed", "review_parse_failed"}:
        return True

    return False


def describe_v3_failure_reason(reason: str) -> str:
    """将 V3 失败原因转换为更可读的中文标签。"""
    normalized = str(reason or "").strip().lower()
    reason_text_map = {
        "draft_generation_failed": "草案生成超时/空响应",
        "draft_parse_failed": "草案结构化解析失败",
        "review_generation_failed": "审稿生成超时/空响应",
        "review_parse_failed": "审稿结构化解析失败",
        "review_gate_failed": "审稿门禁未通过",
        "quality_gate_failed": "质量门禁未通过",
        "review_not_passed_or_quality_gate_failed": "审稿或质量门禁未通过",
        "exception": "流水线异常",
        "v3_pipeline_returned_empty": "流水线返回为空",
    }
    return reason_text_map.get(normalized, "流水线未通过")


def choose_v3_failure_log_icon(reason: str) -> str:
    """按失败类型选择日志级别图标，避免将可预期回退全部标成告警。"""
    normalized = str(reason or "").strip().lower()
    if normalized in {
        "draft_parse_failed",
        "review_parse_failed",
        "review_gate_failed",
        "quality_gate_failed",
        "review_not_passed_or_quality_gate_failed",
    }:
        return "ℹ️"
    return "⚠️"


def format_v3_phase_lanes_for_log(phase_lanes: Optional[dict]) -> str:
    if not isinstance(phase_lanes, dict):
        return "-"
    draft_lane = str(phase_lanes.get("draft", "") or "").strip() or "-"
    review_lane = str(phase_lanes.get("review", "") or "").strip() or "-"
    return f"draft={draft_lane},review={review_lane}"


def build_v3_failure_log_context(v3_failure: Optional[dict]) -> str:
    if not isinstance(v3_failure, dict):
        return "reason=v3_pipeline_returned_empty,profile=-,parse_stage=-,lane=-,phase_lanes=-,error=-"

    reason = str(v3_failure.get("reason", "v3_pipeline_returned_empty") or "v3_pipeline_returned_empty").strip()
    profile = str(v3_failure.get("profile", "") or "").strip() or "-"
    parse_stage = str(v3_failure.get("parse_stage", "") or "").strip() or "-"
    lane = str(v3_failure.get("lane", "") or "").strip() or "-"
    phase_lanes = format_v3_phase_lanes_for_log(v3_failure.get("phase_lanes", {}))
    raw_error = str(v3_failure.get("error", "") or "").strip()
    error = summarize_error_for_log(raw_error, limit=160) if raw_error else "-"
    salvage_attempted = bool(v3_failure.get("salvage_attempted", False))
    salvage_success = bool(v3_failure.get("salvage_success", False))
    salvage_note = str(v3_failure.get("salvage_note", "") or "").strip()
    salvage_error = str(v3_failure.get("salvage_error", "") or "").strip()
    final_issue_types = summarize_issue_types_v3(v3_failure.get("review_issues", []))
    if not final_issue_types:
        final_issue_types = [str(item).strip().lower() for item in (v3_failure.get("final_issue_types", []) or []) if str(item).strip()]
    salvage_issue_types = [str(item).strip().lower() for item in (v3_failure.get("salvage_issue_types", []) or []) if str(item).strip()]
    final_issue_types_text = "|".join(final_issue_types[:8]) if final_issue_types else "-"
    salvage_issue_types_text = "|".join(salvage_issue_types[:8]) if salvage_issue_types else "-"
    try:
        final_issue_count = int(v3_failure.get("final_issue_count", len(v3_failure.get("review_issues", []) or [])) or 0)
    except Exception:
        final_issue_count = len(v3_failure.get("review_issues", []) or [])
    try:
        salvage_quality_issue_count = int(v3_failure.get("salvage_quality_issue_count", 0) or 0)
    except Exception:
        salvage_quality_issue_count = 0

    if salvage_note:
        salvage_note = summarize_error_for_log(salvage_note, limit=120)
    if salvage_error:
        salvage_error = summarize_error_for_log(salvage_error, limit=120)

    return (
        f"reason={reason},profile={profile},parse_stage={parse_stage},lane={lane},phase_lanes={phase_lanes},"
        f"error={error},final_issue_count={final_issue_count},final_issue_types={final_issue_types_text},"
        f"salvage_attempted={salvage_attempted},salvage_success={salvage_success},"
        f"salvage_quality_issue_count={salvage_quality_issue_count},"
        f"salvage_issue_types={salvage_issue_types_text},"
        f"salvage_note={salvage_note or '-'},salvage_error={salvage_error or '-'}"
    )


def attempt_salvage_v3_review_failure(session: dict, v3_result: Optional[dict]) -> dict:
    """
    在审稿阶段失败时尝试直接复用现有草案：
    - 针对 review_generation_failed / review_parse_failed
    - 可选覆盖 review_gate_failed / quality_gate_failed（启用保守规则修复）
    - 若草案通过质量门禁，则直接产出，减少不必要回退和告警
    """
    outcome = {
        "attempted": False,
        "success": False,
        "reason": str((v3_result or {}).get("reason", "") or "").strip().lower() if isinstance(v3_result, dict) else "",
        "note": "",
        "error": "",
        "quality_gate_issue_count": 0,
        "review_issues": [],
        "quality_gate_issues": [],
        "quality_gate_issue_types": [],
        "profile": str((v3_result or {}).get("profile", "") or "").strip() if isinstance(v3_result, dict) else "",
        "phase_lanes": (v3_result.get("phase_lanes", {}) if isinstance(v3_result, dict) and isinstance(v3_result.get("phase_lanes", {}), dict) else {}),
        "evidence_pack": (v3_result.get("evidence_pack", {}) if isinstance(v3_result, dict) and isinstance(v3_result.get("evidence_pack", {}), dict) else {}),
    }

    if not isinstance(session, dict) or not isinstance(v3_result, dict):
        return outcome

    salvage_reasons = {"review_generation_failed", "review_parse_failed"}
    if REPORT_V3_SALVAGE_ON_QUALITY_GATE_FAILURE:
        salvage_reasons.update({
            "review_gate_failed",
            "quality_gate_failed",
            "review_not_passed_or_quality_gate_failed",
        })

    if outcome["reason"] not in salvage_reasons:
        return outcome

    outcome["attempted"] = True
    draft_snapshot = v3_result.get("draft_snapshot", {})
    evidence_pack = outcome["evidence_pack"]
    if not isinstance(draft_snapshot, dict) or not draft_snapshot:
        outcome["note"] = "missing_draft_snapshot"
        return outcome
    if not isinstance(evidence_pack, dict) or not evidence_pack:
        outcome["note"] = "missing_evidence_pack"
        return outcome

    try:
        sanitized_draft, local_issues = validate_report_draft_v3(draft_snapshot, evidence_pack)
        review_issues_raw = v3_result.get("review_issues", []) if isinstance(v3_result.get("review_issues", []), list) else []
        repair_seed_issues = list(review_issues_raw) + list(local_issues)
        salvage_repair = apply_deterministic_report_repairs_v3(
            sanitized_draft,
            evidence_pack,
            repair_seed_issues,
            runtime_profile=outcome.get("profile", REPORT_V3_PROFILE),
        )
        if salvage_repair.get("changed"):
            sanitized_draft, local_issues = validate_report_draft_v3(
                salvage_repair.get("draft", sanitized_draft),
                evidence_pack,
            )

        merged_issues, _filtered_model_issues = merge_review_and_local_issues_v3(
            review_issues_raw,
            local_issues,
            sanitized_draft,
            evidence_pack=evidence_pack,
            runtime_profile=outcome.get("profile", REPORT_V3_PROFILE),
        )

        quality_meta = compute_report_quality_meta_v3(sanitized_draft, evidence_pack, merged_issues)
        if isinstance(quality_meta, dict):
            quality_meta["runtime_profile"] = normalize_report_profile_choice(outcome.get("profile", ""), fallback=REPORT_V3_PROFILE)
        quality_gate_issues = build_quality_gate_issues_v3(quality_meta)
        outcome["quality_gate_issue_count"] = len(quality_gate_issues)
        outcome["quality_gate_issue_types"] = summarize_issue_types_v3(quality_gate_issues)
        if quality_gate_issues:
            outcome["note"] = "quality_gate_blocked"
            outcome["quality_gate_issues"] = quality_gate_issues[:60]
            outcome["review_issues"] = quality_gate_issues[:60]
            return outcome

        report_content = render_report_from_draft_v3(session, sanitized_draft, quality_meta)
        if not report_content:
            outcome["note"] = "render_empty"
            return outcome

        outcome["success"] = True
        outcome["note"] = "quality_gate_passed"
        outcome["quality_meta"] = quality_meta if isinstance(quality_meta, dict) else {}
        outcome["report_content"] = report_content
        outcome["review_issues"] = merged_issues[:60]
        outcome["quality_gate_issues"] = []
        outcome["quality_gate_issue_types"] = []
        return outcome
    except Exception as exc:
        outcome["error"] = summarize_error_for_log(exc, limit=200)
        return outcome


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

    # 最小章节完整性：至少要有 4 个二级标题，且具备基本分析语义。
    section_count = len(re.findall(r"(?m)^##\s+", text))
    numbered_section_count = len(re.findall(r"(?m)^##\s*[1-9][\\.、]", text))
    quality_keywords = ["访谈概述", "需求摘要", "分析", "风险", "行动", "建议"]
    keyword_hits = sum(1 for item in quality_keywords if item in text)
    if section_count < 4 and numbered_section_count < 3 and keyword_hits < 3:
        return True

    return False


def normalize_report_time_fields(content: str, generated_at: Optional[datetime] = None) -> str:
    """标准化报告中的时间字段，避免模型产出过期/幻觉时间。"""
    text = str(content or "")
    if not text.strip():
        return text

    temporal_fields = build_report_temporal_fields(generated_at=generated_at)
    interview_date = temporal_fields["interview_date"]
    generated_datetime_cn = temporal_fields["generated_datetime_cn"]
    report_id = temporal_fields["report_id"]

    lines = text.splitlines()
    if not lines:
        return text
    # 仅处理报告头部，避免误改正文提及的历史时间。
    head_limit = min(len(lines), 80)
    head_text = "\n".join(lines[:head_limit])
    tail_text = "\n".join(lines[head_limit:])

    normalized_head = head_text

    # 表格字段统一
    normalized_head = re.sub(
        r"(?im)^(\|\s*报告生成时间\s*\|)\s*[^|\n]*\|",
        rf"\g<1> {generated_datetime_cn} |",
        normalized_head,
    )
    normalized_head = re.sub(
        r"(?im)^(\|\s*生成日期\s*\|)\s*[^|\n]*\|",
        rf"\g<1> {generated_datetime_cn} |",
        normalized_head,
    )
    normalized_head = re.sub(
        r"(?im)^(\|\s*访谈日期\s*\|)\s*[^|\n]*\|",
        rf"\g<1> {interview_date} |",
        normalized_head,
    )
    normalized_head = re.sub(
        r"(?im)^(\|\s*访谈时间\s*\|)\s*[^|\n]*\|",
        rf"\g<1> {interview_date} |",
        normalized_head,
    )
    normalized_head = re.sub(
        r"(?im)^(\|\s*报告编号\s*\|)\s*[^|\n]*\|",
        rf"\g<1> {report_id} |",
        normalized_head,
    )

    # 独立行字段统一
    normalized_head = re.sub(
        r"(?im)^(\*\*报告生成时间\*\*\s*[:：]\s*)[^\n]+$",
        rf"\g<1>{generated_datetime_cn}",
        normalized_head,
    )
    normalized_head = re.sub(
        r"(?im)^(\s*报告生成时间\s*[:：]\s*)[^\n]+$",
        rf"\g<1>{generated_datetime_cn}",
        normalized_head,
    )
    normalized_head = re.sub(
        r"(?im)^(\*\*生成日期\*\*\s*[:：]\s*)[^\n]+$",
        rf"\g<1>{generated_datetime_cn}",
        normalized_head,
    )
    normalized_head = re.sub(
        r"(?im)^(\s*生成日期\s*[:：]\s*)[^\n]+$",
        rf"\g<1>{generated_datetime_cn}",
        normalized_head,
    )
    normalized_head = re.sub(
        r"(?im)^(\*\*访谈日期\*\*\s*[:：]\s*)[^\n]+$",
        rf"\g<1>{interview_date}",
        normalized_head,
    )
    normalized_head = re.sub(
        r"(?im)^(\s*访谈日期\s*[:：]\s*)[^\n]+$",
        rf"\g<1>{interview_date}",
        normalized_head,
    )
    normalized_head = re.sub(
        r"(?im)^(\s*访谈时间\s*[:：]\s*)[^\n]+$",
        rf"\g<1>{interview_date}",
        normalized_head,
    )
    normalized_head = re.sub(
        r"(?im)^(\*\*报告编号\*\*\s*[:：]\s*)[^\n]+$",
        rf"\g<1>{report_id}",
        normalized_head,
    )

    # 兼容 Markdown 列表项（-/*/+）和可选加粗标签字段，防止模型输出年份幻觉值残留。
    line_field_rules = [
        ("报告生成时间", generated_datetime_cn),
        ("生成日期", generated_datetime_cn),
        ("访谈日期", interview_date),
        ("访谈时间", interview_date),
        ("报告编号", report_id),
    ]
    for label, target_value in line_field_rules:
        normalized_head = re.sub(
            rf"(?im)^(\s*(?:[-*+•·]\s+)(?:\*\*)?{label}(?:\*\*)?\s*[:：]\s*)[^\n]+$",
            rf"\g<1>{target_value}",
            normalized_head,
        )

    # 行内复合字段（如：报告编号：xxx 访谈主题：yyy 生成日期：zzz）统一
    normalized_head = re.sub(
        r"(?im)(报告编号\s*[:：]\s*)([A-Za-z0-9][A-Za-z0-9_\-]*)",
        rf"\g<1>{report_id}",
        normalized_head,
    )
    normalized_head = re.sub(
        r"(?im)(生成日期\s*[:：]\s*)([^\n]*)$",
        rf"\g<1>{generated_datetime_cn}",
        normalized_head,
    )
    normalized_head = re.sub(
        r"(?im)(报告生成时间\s*[:：]\s*)([^\n]*)$",
        rf"\g<1>{generated_datetime_cn}",
        normalized_head,
    )
    normalized_head = re.sub(
        r"(?im)(访谈时间\s*[:：]\s*)([^\n]*)$",
        rf"\g<1>{interview_date}",
        normalized_head,
    )

    if tail_text:
        return f"{normalized_head}\n{tail_text}"
    return normalized_head


def can_use_v3_failover_lane() -> bool:
    """是否具备可用且独立的备用网关 lane。"""
    if REPORT_V3_FAILOVER_LANE == "question":
        target_client = question_ai_client
    else:
        target_client = report_ai_client

    primary_client = report_ai_client or question_ai_client
    if not target_client or not primary_client:
        return False

    # 两侧复用同一客户端时，切换 lane 没有意义
    return target_client is not primary_client


def run_report_generation_job(session_id: str, user_id: int, request_id: str, report_profile: str = "") -> None:
    """后台生成报告任务。"""
    try:
        selected_report_profile = normalize_report_profile_choice(report_profile, fallback=REPORT_V3_PROFILE)
        set_report_generation_metadata(session_id, {"report_profile": selected_report_profile})
        loaded = load_session_for_user(session_id, user_id, include_missing=True)
        session_file, session, state = loaded
        if state != "ok" or session_file is None or session is None:
            error_msg = "会话不存在或无权限"
            update_report_generation_status(session_id, "failed", message=f"报告生成失败：{error_msg}", active=False)
            set_report_generation_metadata(session_id, {
                "request_id": request_id,
                "error": error_msg,
                "completed_at": get_utc_now(),
            })
            return

        # 数据迁移：兼容旧会话
        session = migrate_session_docs(session)

        def persist_report(content: str, quality_meta: Optional[dict] = None) -> tuple[Path, str]:
            """保存报告并更新会话状态。"""
            topic_slug = session.get("topic", "report").replace(" ", "-")[:30]
            date_str = datetime.now().strftime("%Y%m%d")
            scope_tag = get_instance_scope_short_tag()
            if scope_tag:
                filename = f"deep-vision-{date_str}-{scope_tag}-{topic_slug}.md"
            else:
                filename = f"deep-vision-{date_str}-{topic_slug}.md"
            report_file = REPORTS_DIR / filename
            normalized_content = normalize_report_time_fields(content)
            report_file.write_text(normalized_content, encoding="utf-8")
            set_report_owner_id(filename, user_id)

            latest_session = safe_load_session(session_file)
            if isinstance(latest_session, dict) and ensure_session_owner(latest_session, user_id):
                latest_session["status"] = "completed"
                latest_session["updated_at"] = get_utc_now()
                if isinstance(quality_meta, dict):
                    latest_session["last_report_quality_meta"] = quality_meta
                if isinstance(session.get("last_report_v3_debug"), dict):
                    latest_session["last_report_v3_debug"] = session["last_report_v3_debug"]
                save_session_json_and_sync(session_file, latest_session)

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
                    "evidence_pack_summary": summarize_evidence_pack_for_debug(result.get("evidence_pack", {})),
                    "salvage_attempted": bool(result.get("salvage_attempted", False)),
                    "salvage_success": bool(result.get("salvage_success", False)),
                    "salvage_note": str(result.get("salvage_note", "") or ""),
                    "salvage_error": str(result.get("salvage_error", "") or ""),
                    "salvage_quality_issue_count": int(result.get("salvage_quality_issue_count", 0) or 0),
                    "salvage_issue_types": list(result.get("salvage_issue_types", []) or []),
                    "salvage_issues": (result.get("salvage_issues", []) if isinstance(result.get("salvage_issues", []), list) else [])[:60],
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
                "evidence_pack_summary": {},
                "salvage_attempted": False,
                "salvage_success": False,
                "salvage_note": "",
                "salvage_error": "",
                "salvage_quality_issue_count": 0,
                "salvage_issue_types": [],
                "salvage_issues": [],
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

            update_report_generation_status(session_id, "saving", message=saving_message)
            report_file, filename = persist_report(report_content, quality_meta=quality_meta)
            update_report_generation_status(session_id, "completed", active=False)
            set_report_generation_metadata(session_id, {
                "request_id": request_id,
                "report_name": filename,
                "report_path": str(report_file),
                "ai_generated": True,
                "v3_enabled": True,
                "report_quality_meta": quality_meta,
                "error": "",
                "completed_at": get_utc_now(),
            })
            return True

        # 检查是否有 Claude API
        if resolve_ai_client(call_type="report"):
            update_report_generation_status(session_id, "building_prompt", message="正在执行 V3 证据包构建与结构化草案...")
            v3_result = generate_report_v3_pipeline(
                session,
                session_id=session_id,
                preferred_lane="report",
                report_profile=selected_report_profile,
            )

            if v3_result and v3_result.get("report_content"):
                if persist_v3_success_result(
                    v3_result,
                    status_reason="v3_pipeline_passed",
                    saving_message="正在保存 V3 审稿增强报告...",
                ):
                    return

            primary_salvage = attempt_salvage_v3_review_failure(session, v3_result)
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

            if REPORT_V3_FAILOVER_ENABLED and can_use_v3_failover_lane() and should_retry_v3_with_failover(v3_result):
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
                )
                failover_suffix = f"_failover_{REPORT_V3_FAILOVER_LANE}"
                failover_result = generate_report_v3_pipeline(
                    session,
                    session_id=session_id,
                    preferred_lane=REPORT_V3_FAILOVER_LANE,
                    call_type_suffix=failover_suffix,
                    report_profile=selected_report_profile,
                )
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

                failover_salvage = attempt_salvage_v3_review_failure(session, failover_result)
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
                "evidence_pack_summary": primary_failure.get("evidence_pack_summary", {}),
                "salvage_attempted": primary_failure.get("salvage_attempted", False),
                "salvage_success": primary_failure.get("salvage_success", False),
                "salvage_note": primary_failure.get("salvage_note", ""),
                "salvage_error": primary_failure.get("salvage_error", ""),
                "salvage_quality_issue_count": primary_failure.get("salvage_quality_issue_count", 0),
                "salvage_issue_types": primary_failure.get("salvage_issue_types", []),
                "salvage_issues": primary_failure.get("salvage_issues", []),
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
                message=f"V3 {describe_v3_failure_reason(primary_failure.get('reason', ''))}，正在回退标准报告生成...",
            )
            prompt = build_report_prompt(session)

            if ENABLE_DEBUG_LOG:
                ref_docs_count = len(session.get("reference_materials", session.get("reference_docs", []) + session.get("research_docs", [])))
                interview_count = len(session.get("interview_log", []))
                print(f"📊 回退报告 Prompt 统计：总长度={len(prompt)}字符，参考资料={ref_docs_count}个，访谈记录={interview_count}条")

            legacy_timeout = compute_adaptive_report_timeout(
                REPORT_API_TIMEOUT,
                len(prompt),
                timeout_cap=max(REPORT_API_TIMEOUT, REPORT_DRAFT_API_TIMEOUT + 60),
            )
            report_content = call_claude(
                prompt,
                max_tokens=min(MAX_TOKENS_REPORT, 7000),
                call_type="report_legacy_fallback",
                timeout=legacy_timeout,
            )

            if is_unusable_legacy_report_content(report_content):
                fallback_primary_lane = resolve_call_lane(call_type="report_legacy_fallback")
                fallback_primary_model = resolve_model_name_for_lane(
                    call_type="report_legacy_fallback",
                    selected_lane=fallback_primary_lane,
                )
                retry_lane = ""
                if REPORT_V3_FAILOVER_ENABLED and can_use_v3_failover_lane():
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
                        max_tokens=min(MAX_TOKENS_REPORT, 7000),
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
                quality_meta = build_report_quality_meta_fallback(session, mode="legacy_ai_fallback")
                session["last_report_quality_meta"] = quality_meta

                update_report_generation_status(session_id, "saving", message="正在保存回退生成报告...")
                report_file, filename = persist_report(report_content, quality_meta=quality_meta)
                update_report_generation_status(session_id, "completed", active=False)
                set_report_generation_metadata(session_id, {
                    "request_id": request_id,
                    "report_name": filename,
                    "report_path": str(report_file),
                    "ai_generated": True,
                    "v3_enabled": False,
                    "report_quality_meta": quality_meta if isinstance(quality_meta, dict) else {},
                    "error": "",
                    "completed_at": get_utc_now(),
                })
                return

        # 回退到简单报告生成
        update_report_generation_status(session_id, "fallback", message="AI 回退失败，正在使用模板报告兜底...")
        report_content = generate_simple_report(session)
        quality_meta = build_report_quality_meta_fallback(session, mode="simple_template_fallback")
        session["last_report_quality_meta"] = quality_meta
        update_report_generation_status(session_id, "saving")
        report_file, filename = persist_report(report_content, quality_meta=quality_meta)

        update_report_generation_status(session_id, "completed", active=False)
        set_report_generation_metadata(session_id, {
            "request_id": request_id,
            "report_name": filename,
            "report_path": str(report_file),
            "ai_generated": False,
            "v3_enabled": False,
            "report_quality_meta": quality_meta if isinstance(quality_meta, dict) else {},
            "error": "",
            "completed_at": get_utc_now(),
        })
    except Exception as exc:
        error_detail = str(exc)[:200] or "未知错误"
        update_report_generation_status(session_id, "failed", message=f"报告生成失败：{error_detail}", active=False)
        set_report_generation_metadata(session_id, {
            "request_id": request_id,
            "error": error_detail,
            "completed_at": get_utc_now(),
        })
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


@app.route('/api/sessions/<session_id>/generate-report', methods=['POST'])
def generate_report(session_id):
    """异步生成访谈报告。"""
    user_id = get_current_user_id_or_none()
    if not user_id:
        return jsonify({"error": "请先登录"}), 401

    loaded = load_session_for_user(session_id, user_id)
    if len(loaded) == 3:
        _file, error_msg, status_code = loaded
        return jsonify({"error": error_msg}), status_code

    data = request.get_json(silent=True) or {}
    action = "regenerate" if data.get("action") == "regenerate" else "generate"
    raw_report_profile = str(data.get("report_profile", "") or "").strip().lower()
    if raw_report_profile and raw_report_profile not in {"balanced", "quality"}:
        return jsonify({"error": "report_profile 仅支持 balanced 或 quality"}), 400
    report_profile = normalize_report_profile_choice(raw_report_profile, fallback=REPORT_V3_PROFILE)

    current_record = get_report_generation_record(session_id) or {}
    worker_alive = is_report_generation_worker_alive(session_id)
    if bool(current_record.get("active")) or worker_alive:
        if worker_alive and not bool(current_record.get("active")):
            current_state = str(current_record.get("state") or "").strip()
            if current_state not in {"completed", "failed", "cancelled"}:
                update_report_generation_status(session_id, "queued", message="报告任务正在处理中...")
        queue_snapshot = get_report_generation_worker_snapshot(include_positions=True)
        sync_report_generation_queue_metadata(session_id, snapshot=queue_snapshot)
        current_record = get_report_generation_record(session_id) or current_record
        payload = build_report_generation_payload(current_record)
        payload.update({
            "success": True,
            "already_running": True,
            "action": current_record.get("action", action),
            "report_profile": normalize_report_profile_choice(current_record.get("report_profile", ""), fallback=report_profile),
            "queue": {
                "running": int(queue_snapshot.get("running", 0) or 0),
                "pending": int(queue_snapshot.get("pending", 0) or 0),
                "max_workers": int(queue_snapshot.get("max_workers", REPORT_GENERATION_MAX_WORKERS) or REPORT_GENERATION_MAX_WORKERS),
                "max_pending": int(queue_snapshot.get("max_pending", REPORT_GENERATION_MAX_PENDING) or REPORT_GENERATION_MAX_PENDING),
            },
        })
        return jsonify(payload), 202

    if not report_generation_slots.acquire(blocking=False):
        record_report_generation_queue_event("rejected")
        queue_snapshot = get_report_generation_worker_snapshot(include_positions=False)
        response = jsonify({
            "error": "报告生成队列繁忙，请稍后重试",
            "retry_after_seconds": REPORT_GENERATION_QUEUE_RETRY_AFTER_SECONDS,
            "queue": {
                "running": int(queue_snapshot.get("running", 0) or 0),
                "pending": int(queue_snapshot.get("pending", 0) or 0),
                "max_workers": int(queue_snapshot.get("max_workers", REPORT_GENERATION_MAX_WORKERS) or REPORT_GENERATION_MAX_WORKERS),
                "max_pending": int(queue_snapshot.get("max_pending", REPORT_GENERATION_MAX_PENDING) or REPORT_GENERATION_MAX_PENDING),
            },
        })
        response.status_code = 429
        response.headers["Retry-After"] = str(REPORT_GENERATION_QUEUE_RETRY_AFTER_SECONDS)
        return response

    request_id = secrets.token_hex(12)
    set_report_generation_metadata(session_id, {
        "request_id": request_id,
        "action": action,
        "started_at": get_utc_now(),
        "completed_at": "",
        "report_name": "",
        "report_path": "",
        "ai_generated": None,
        "v3_enabled": None,
        "report_profile": report_profile,
        "report_quality_meta": {},
        "error": "",
        "queue_position": 0,
        "queue_pending": 0,
        "queue_running": 0,
    })
    update_report_generation_status(session_id, "queued")

    try:
        worker = report_generation_executor.submit(
            run_report_generation_job,
            session_id,
            user_id,
            request_id,
            report_profile,
        )
    except Exception as exc:
        release_report_generation_slot()
        error_detail = str(exc)[:200] or "未知错误"
        update_report_generation_status(session_id, "failed", message=f"报告任务提交失败：{error_detail}", active=False)
        set_report_generation_metadata(session_id, {
            "request_id": request_id,
            "error": error_detail,
            "completed_at": get_utc_now(),
        })
        return jsonify({"error": f"报告任务提交失败：{error_detail}"}), 500

    register_report_generation_worker(session_id, worker)
    record_report_generation_queue_event("submitted")
    queue_snapshot = get_report_generation_worker_snapshot(include_positions=True)
    sync_report_generation_queue_metadata(session_id, snapshot=queue_snapshot)

    payload = build_report_generation_payload(get_report_generation_record(session_id))
    payload.update({
        "success": True,
        "already_running": False,
        "action": action,
        "report_profile": report_profile,
        "queue": {
            "running": int(queue_snapshot.get("running", 0) or 0),
            "pending": int(queue_snapshot.get("pending", 0) or 0),
            "max_workers": int(queue_snapshot.get("max_workers", REPORT_GENERATION_MAX_WORKERS) or REPORT_GENERATION_MAX_WORKERS),
            "max_pending": int(queue_snapshot.get("max_pending", REPORT_GENERATION_MAX_PENDING) or REPORT_GENERATION_MAX_PENDING),
        },
    })
    return jsonify(payload), 202


def resolve_selected_options(log: dict, option_list: list[str]) -> set[str]:
    """解析用户实际勾选的选项（兼容单选、多选、其他输入引用选项）。"""
    if not isinstance(log, dict) or not option_list:
        return set()

    answer_text = str(log.get("answer", "") or "").strip()
    if not answer_text:
        return set()

    answer_tokens = {
        token.strip()
        for token in re.split(r"[；;]\s*", answer_text)
        if token and token.strip()
    }
    if not answer_tokens and answer_text:
        answer_tokens.add(answer_text)

    return {option for option in option_list if option in answer_tokens}


def render_appendix_answer_block(log: dict) -> str:
    """将附录回答渲染为“全选项 + 勾选态 + 其他输入”格式。"""
    if not isinstance(log, dict):
        text = str(log or "").strip()
        safe_text = html.escape(text or "（未填写）")
        return f"<div><strong>回答：</strong></div>\n<div>☑ {safe_text}</div>"

    answer_text = str(log.get("answer", "") or "").strip()
    option_list = []
    options = log.get("options")
    if isinstance(options, list):
        option_list = [str(item or "").strip() for item in options if str(item or "").strip()]

    selected_options = resolve_selected_options(log, option_list)

    answer_lines = []
    if option_list:
        for option in option_list:
            mark = "☑" if option in selected_options else "☐"
            answer_lines.append(f"{mark} {option}")
    else:
        answer_lines.append(f"☑ {answer_text or '（未填写）'}")

    other_selected = bool(log.get("other_selected"))
    other_input = str(log.get("other_answer_text", "") or "").strip()
    if other_selected and other_input:
        answer_lines.append(f"☑ 其他（自由输入）：{other_input}")

    # 附录位于 <details> HTML 区块内，Markdown 换行在部分渲染器中会失效。
    # 这里直接输出块级 HTML，确保选项稳定按“自上而下”逐行展示。
    if answer_lines:
        rendered_lines = "\n".join(f"<div>{html.escape(line)}</div>" for line in answer_lines)
        return f"<div><strong>回答：</strong></div>\n{rendered_lines}"

    return "<div><strong>回答：</strong></div>\n<div>☑ （未填写）</div>"


def generate_interview_appendix(session: dict) -> str:
    """生成完整的访谈记录附录"""
    interview_log = session.get("interview_log", [])
    if not interview_log:
        return ""

    appendix = "\n\n---\n\n## 附录：完整访谈记录\n\n"
    appendix += "<details>\n"
    appendix += f"<summary>本次访谈共收集了 {len(interview_log)} 个问题的回答</summary>\n\n"

    appendix_dim_info = get_dimension_info_for_session(session)
    total_questions = len(interview_log)
    for i, log in enumerate(interview_log, 1):
        dim_name = appendix_dim_info.get(log.get('dimension', ''), {}).get('name', '未分类')
        question = str(log.get('question', '') or '').strip() or '（未记录问题）'
        answer_block = render_appendix_answer_block(log)
        appendix += f"**【{dim_name}】问题 {i}：{question}**\n\n"
        appendix += f"{answer_block}\n\n"
        if i < total_questions:
            appendix += "---\n\n"

    appendix += "</details>\n\n"

    return appendix


def generate_simple_report(session: dict) -> str:
    """生成简单报告（无 AI 时使用）"""
    topic = session.get("topic", "未命名项目")
    interview_log = session.get("interview_log", [])
    now = datetime.now()
    temporal_fields = build_report_temporal_fields(now)

    content = f"""# {topic} 访谈报告

**访谈日期**: {temporal_fields['interview_date']}
**生成日期**: {temporal_fields['generated_datetime_cn']}
**报告编号**: {temporal_fields['report_id']}

---

## 1. 访谈概述

本次访谈主题为「{topic}」，共收集了 {len(interview_log)} 个问题的回答。

## 2. 需求摘要

"""

    simple_dim_info = get_dimension_info_for_session(session)
    for dim_key, dim_info in simple_dim_info.items():
        content += f"### {dim_info['name']}\n\n"
        logs = [log for log in interview_log if log.get("dimension") == dim_key]
        if logs:
            for log in logs:
                content += f"- **{log['answer']}** - {log['question']}\n"
        else:
            content += "*暂无数据*\n"
        content += "\n"

    # 使用统一的附录生成函数，确保格式一致
    content += generate_interview_appendix(session)

    content += """
*此报告由 Deep Vision 深瞳生成*
"""

    return content


# ============ Refly 集成 ============

def is_refly_configured() -> bool:
    return bool(REFLY_API_URL and REFLY_API_KEY and REFLY_WORKFLOW_ID and REFLY_INPUT_FIELD)


def build_refly_payload(report_content: str, file_keys: Optional[list] = None) -> dict:
    variables = {REFLY_INPUT_FIELD: report_content}
    if file_keys:
        variables[REFLY_FILES_FIELD] = file_keys
    return {"variables": variables}


def get_refly_base_url() -> str:
    return (REFLY_API_URL or "").rstrip("/")


def get_refly_run_url() -> str:
    base = get_refly_base_url()
    if not base:
        return base
    return f"{base}/openapi/workflow/{REFLY_WORKFLOW_ID}/run"


def get_refly_upload_url() -> str:
    base = get_refly_base_url()
    if not base:
        return base
    return f"{base}/openapi/files/upload"


def get_refly_status_url(execution_id: str) -> str:
    base = get_refly_base_url()
    if not base:
        return base
    return f"{base}/openapi/workflow/{execution_id}/status"


def get_refly_output_url(execution_id: str) -> str:
    base = get_refly_base_url()
    if not base:
        return base
    return f"{base}/openapi/workflow/{execution_id}/output"


def get_refly_execution_status(status_response: dict) -> str:
    if not isinstance(status_response, dict):
        return ""
    payload = status_response.get("payload") or status_response.get("data") or status_response
    data = payload.get("data") if isinstance(payload, dict) else {}
    status = ""
    if isinstance(data, dict):
        status = data.get("status") or ""
    return status or ""


def get_refly_abort_url(execution_id: str) -> str:
    base = get_refly_base_url()
    if not base:
        return base
    return f"{base}/openapi/workflow/{execution_id}/abort"


def upload_refly_file(file_path: Path) -> dict:
    url = get_refly_upload_url()
    headers = {
        "Authorization": f"Bearer {REFLY_API_KEY}"
    }
    if ENABLE_DEBUG_LOG:
        print(f"📤 Refly 上传文件: {url}")
    with open(file_path, "rb") as file_handle:
        files = {"files": (file_path.name, file_handle)}
        response = requests.post(url, headers=headers, files=files, timeout=REFLY_TIMEOUT)
    response.raise_for_status()
    try:
        return response.json()
    except ValueError:
        return {"raw": response.text}


def extract_refly_file_keys(upload_response: dict) -> list:
    if not isinstance(upload_response, dict):
        return []
    files = (
        upload_response.get("data", {}).get("files")
        or upload_response.get("files")
        or []
    )
    keys = []
    if isinstance(files, list):
        for item in files:
            if isinstance(item, dict):
                key = item.get("fileKey") or item.get("file_key") or item.get("key")
                if key:
                    keys.append(key)
    return keys


def run_refly_workflow(report_content: str, file_keys: Optional[list] = None) -> dict:
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {REFLY_API_KEY}"
    }
    url = get_refly_run_url()
    payload = build_refly_payload(report_content, file_keys=file_keys)

    if ENABLE_DEBUG_LOG:
        print(f"📤 Refly 运行工作流: {url}")

    response = requests.post(url, json=payload, headers=headers, timeout=REFLY_TIMEOUT)
    response.raise_for_status()
    try:
        return response.json()
    except ValueError:
        return {"raw": response.text}


def poll_refly_execution(execution_id: str) -> dict:
    headers = {
        "Authorization": f"Bearer {REFLY_API_KEY}"
    }
    status_url = get_refly_status_url(execution_id)
    deadline = _time.time() + REFLY_POLL_TIMEOUT
    last_payload = {}
    status = "executing"

    if ENABLE_DEBUG_LOG:
        print(f"🔁 Refly 轮询状态: {status_url}")

    while _time.time() < deadline and status == "executing":
        _time.sleep(REFLY_POLL_INTERVAL)
        response = requests.get(status_url, headers=headers, timeout=REFLY_TIMEOUT)
        response.raise_for_status()
        try:
            last_payload = response.json()
        except ValueError:
            last_payload = {"raw": response.text}
        status = (
            last_payload.get("data", {}).get("status")
            or last_payload.get("status")
            or status
        )

    return {
        "status": status,
        "payload": last_payload
    }


def fetch_refly_status_once(execution_id: str) -> dict:
    headers = {
        "Authorization": f"Bearer {REFLY_API_KEY}"
    }
    status_url = get_refly_status_url(execution_id)
    response = requests.get(status_url, headers=headers, timeout=REFLY_TIMEOUT)
    response.raise_for_status()
    try:
        payload = response.json()
    except ValueError:
        payload = {"raw": response.text}
    status = payload.get("data", {}).get("status") or payload.get("status") or "executing"
    return {
        "status": status,
        "payload": payload
    }


def fetch_refly_output(execution_id: str) -> dict:
    headers = {
        "Authorization": f"Bearer {REFLY_API_KEY}"
    }
    output_url = get_refly_output_url(execution_id)

    if ENABLE_DEBUG_LOG:
        print(f"📥 Refly 获取结果: {output_url}")

    response = requests.get(output_url, headers=headers, timeout=REFLY_TIMEOUT)
    response.raise_for_status()
    try:
        return response.json()
    except ValueError:
        return {"raw": response.text}


def has_pdf_or_result_file(payload) -> bool:
    if not isinstance(payload, dict):
        return False
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    files = data.get("files") if isinstance(data.get("files"), list) else []
    for item in files:
        if not isinstance(item, dict):
            continue
        name = (item.get("name") or "").lower()
        file_type = (item.get("type") or "").lower()
        url = (item.get("url") or "").lower()
        if name.endswith(".pdf") or name.endswith("result_info.json"):
            return True
        if url.endswith(".pdf") or url.endswith("result_info.json"):
            return True
        if "pdf" in file_type:
            return True
    return False


def wait_for_refly_output_ready(execution_id: str) -> dict:
    deadline = _time.time() + REFLY_POLL_TIMEOUT
    last_output = {}
    last_status = "executing"
    while _time.time() < deadline:
        try:
            status_payload = fetch_refly_status_once(execution_id)
            last_status = status_payload.get("status") or last_status
        except Exception:
            pass
        if last_status != "executing":
            break
        _time.sleep(REFLY_POLL_INTERVAL)
    try:
        last_output = fetch_refly_output(execution_id)
    except Exception:
        last_output = last_output or {}
    if has_pdf_or_result_file(last_output):
        return last_output
    return last_output


def extract_refly_url(payload) -> Optional[str]:
    if isinstance(payload, dict):
        for key in ("presentation_url", "url", "share_url", "shareUrl", "preview_url", "previewUrl"):
            value = payload.get(key)
            if isinstance(value, str) and value.startswith("http"):
                return value
        for value in payload.values():
            found = extract_refly_url(value)
            if found:
                return found
    elif isinstance(payload, list):
        for value in payload:
            found = extract_refly_url(value)
            if found:
                return found
    elif isinstance(payload, str) and payload.startswith("http"):
        return payload
    return None


def extract_pdf_filename(payload) -> Optional[str]:
    if isinstance(payload, dict):
        if isinstance(payload.get("pdf_filename"), str):
            return payload.get("pdf_filename")
        for value in payload.values():
            found = extract_pdf_filename(value)
            if found:
                return found
    elif isinstance(payload, list):
        for value in payload:
            found = extract_pdf_filename(value)
            if found:
                return found
    return None


def extract_refly_file_id(payload) -> Optional[str]:
    urls = collect_refly_urls(payload, [])
    for url in urls:
        match = re.search(r"/drive/file/(?:content|public)/([^/]+)/", url)
        if match:
            return match.group(1)
    return None


def build_pdf_url_from_result_info(payload) -> Optional[str]:
    pdf_filename = extract_pdf_filename(payload)
    file_id = extract_refly_file_id(payload)
    if not pdf_filename or not file_id:
        return None
    base = get_refly_base_url()
    if not base:
        return None
    return f"{base}/drive/file/content/{file_id}/{quote(pdf_filename)}"


def collect_refly_urls(payload, urls: Optional[list] = None) -> list:
    if urls is None:
        urls = []
    if not payload:
        return urls
    if isinstance(payload, str):
        if payload.startswith("http"):
            urls.append(payload)
        return urls
    if isinstance(payload, list):
        for item in payload:
            collect_refly_urls(item, urls)
        return urls
    if isinstance(payload, dict):
        for value in payload.values():
            collect_refly_urls(value, urls)
    return urls


def extract_pdf_url_from_output(payload) -> Optional[str]:
    if not isinstance(payload, dict):
        return None
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    files = data.get("files") if isinstance(data.get("files"), list) else []
    for item in files:
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        name = (item.get("name") or "").lower()
        file_type = (item.get("type") or "").lower()
        if isinstance(url, str) and url.startswith("http"):
            if url.lower().endswith(".pdf") or name.endswith(".pdf") or "pdf" in file_type:
                return url

    outputs = data.get("output") if isinstance(data.get("output"), list) else []
    for node in outputs:
        if not isinstance(node, dict):
            continue
        messages = node.get("messages") if isinstance(node.get("messages"), list) else []
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            content = msg.get("content")
            if isinstance(content, str):
                match = re.search(r"https?://\\S+?\\.pdf", content)
                if match:
                    return match.group(0)

    for url in collect_refly_urls(payload, []):
        if isinstance(url, str) and url.lower().endswith(".pdf"):
            return url
    return None


def fetch_result_info_json(payload) -> Optional[dict]:
    if not isinstance(payload, dict):
        return None
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    files = data.get("files") if isinstance(data.get("files"), list) else []
    result_url = None
    for item in files:
        if not isinstance(item, dict):
            continue
        name = (item.get("name") or "").lower()
        url = item.get("url")
        if name.endswith("result_info.json") and isinstance(url, str) and url.startswith("http"):
            result_url = url
            break
    if not result_url:
        return None

    headers = {}
    try:
        base_host = urlparse(get_refly_base_url()).netloc
        url_host = urlparse(result_url).netloc
        if base_host and url_host.endswith(base_host):
            headers["Authorization"] = f"Bearer {REFLY_API_KEY}"
    except Exception:
        headers = {}

    try:
        response = requests.get(result_url, headers=headers, timeout=REFLY_TIMEOUT)
        response.raise_for_status()
        return response.json()
    except Exception:
        return None


def build_pdf_url_from_result_info_file(payload) -> Optional[str]:
    result_info = fetch_result_info_json(payload)
    if not isinstance(result_info, dict):
        return None
    pdf_filename = result_info.get("pdf_filename")
    if not isinstance(pdf_filename, str) or not pdf_filename:
        return None
    file_id = extract_refly_file_id(payload)
    if not file_id:
        return None
    base = get_refly_base_url()
    if not base:
        return None
    return f"{base}/drive/file/content/{file_id}/{quote(pdf_filename)}"


def get_refly_file_candidates(output_response: dict) -> list:
    files = []
    if isinstance(output_response, dict):
        files = (
            output_response.get("data", {}).get("files")
            or output_response.get("files")
            or []
        )
    if not isinstance(files, list):
        return []
    candidates = []
    for item in files:
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        name = item.get("name") or item.get("fileName") or item.get("filename") or ""
        if isinstance(url, str) and url.startswith("http"):
            candidates.append({"url": url, "name": name})
    return candidates


def score_refly_url(url: str, name: str = "") -> int:
    lower_url = (url or "").lower()
    lower_name = (name or "").lower()
    target = lower_name or lower_url
    match = re.search(r"\.[a-z0-9]+(?=$|\?)", target)
    ext = match.group(0) if match else ""
    score = 0

    if any(key in lower_url for key in ("share", "preview", "presentation")):
        score += 80
    if "slide" in lower_url:
        score += 10

    if ext == ".pptx":
        score += 100
    elif ext == ".pdf":
        score += 90
    elif ext in (".ppt", ".key"):
        score += 80
    elif ext in (".html", ".htm"):
        score += 70
    elif ext in (".png", ".jpg", ".jpeg"):
        score += 50
    elif ext == ".json":
        score -= 10

    return score


def select_best_refly_candidate(output_response: dict, presentation_url: Optional[str]) -> Optional[dict]:
    candidates = []

    def add_candidate(url: Optional[str], name: str = ""):
        if not isinstance(url, str) or not url.startswith("http"):
            return
        candidates.append({"url": url, "name": name or ""})

    if isinstance(presentation_url, str) and presentation_url.startswith("http"):
        if not presentation_url.lower().endswith(".json"):
            return {"url": presentation_url, "name": "presentation_url"}
        add_candidate(presentation_url, "presentation_url")

    for item in get_refly_file_candidates(output_response):
        add_candidate(item.get("url"), item.get("name", ""))

    for url in collect_refly_urls(output_response, []):
        add_candidate(url, "")

    if not candidates:
        return None

    deduped = {}
    for item in candidates:
        deduped.setdefault(item["url"], item)

    sorted_candidates = sorted(
        deduped.values(),
        key=lambda item: score_refly_url(item.get("url", ""), item.get("name", "")),
        reverse=True,
    )
    return sorted_candidates[0] if sorted_candidates else None


def get_downloads_dir() -> Path:
    env_dir = os.environ.get("DOWNLOADS_DIR", "").strip()
    if env_dir:
        return Path(env_dir).expanduser().resolve()
    home = Path.home()
    candidates = [home / "Downloads", home / "下载"]
    for candidate in candidates:
        if candidate.exists() and candidate.is_dir():
            return candidate
    return candidates[0]


def sanitize_filename(name: str) -> str:
    safe = Path(name).name if name else ""
    safe = safe.strip().strip(".")
    if not safe:
        return "presentation"
    for ch in ('/', '\\', ':', '*', '?', '"', '<', '>', '|'):
        safe = safe.replace(ch, "_")
    return safe


def ensure_unique_path(directory: Path, filename: str) -> Path:
    path = directory / filename
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    counter = 1
    while True:
        candidate = directory / f"{stem}-{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def infer_extension(content_type: str) -> str:
    if not content_type:
        return ""
    lower = content_type.lower()
    if "presentationml" in lower or "pptx" in lower:
        return ".pptx"
    if "ms-powerpoint" in lower:
        return ".ppt"
    if "pdf" in lower:
        return ".pdf"
    if "html" in lower:
        return ".html"
    if "json" in lower:
        return ".json"
    if "png" in lower:
        return ".png"
    if "jpeg" in lower or "jpg" in lower:
        return ".jpg"
    return ""


def build_download_filename(url: str, name: str, content_type: str) -> str:
    raw_name = name or ""
    if raw_name:
        raw_name = sanitize_filename(raw_name)
    if not raw_name:
        parsed = urlparse(url)
        raw_name = sanitize_filename(unquote(Path(parsed.path).name))

    ext = ""
    if raw_name:
        ext_match = re.search(r"\.[a-z0-9]+$", raw_name.lower())
        ext = ext_match.group(0) if ext_match else ""
    if not ext:
        ext = infer_extension(content_type)
    if not raw_name:
        raw_name = "presentation"
    if ext and not raw_name.lower().endswith(ext):
        raw_name = f"{raw_name}{ext}"
    return raw_name


def download_presentation_file(url: str, name: str = "") -> Optional[dict]:
    downloads_dir = get_downloads_dir()
    downloads_dir.mkdir(parents=True, exist_ok=True)

    headers = {}
    try:
        base_host = urlparse(get_refly_base_url()).netloc
        url_host = urlparse(url).netloc
        if base_host and url_host.endswith(base_host):
            headers["Authorization"] = f"Bearer {REFLY_API_KEY}"
    except Exception:
        headers = {}

    response = requests.get(url, headers=headers, stream=True, timeout=REFLY_TIMEOUT)
    response.raise_for_status()
    content_type = response.headers.get("Content-Type", "")
    filename = build_download_filename(url, name, content_type)
    file_path = ensure_unique_path(downloads_dir, filename)

    size = 0
    with open(file_path, "wb") as file_handle:
        for chunk in response.iter_content(chunk_size=1024 * 256):
            if not chunk:
                continue
            file_handle.write(chunk)
            size += len(chunk)
    response.close()

    return {
        "url": url,
        "path": str(file_path),
        "filename": file_path.name,
        "size": size
    }


@app.route('/api/reports/<path:filename>/presentation', methods=['GET'])
def get_report_presentation(filename):
    user_id = get_current_user_id_or_none()
    if not user_id:
        return jsonify({"error": "请先登录"}), 401

    filename = normalize_presentation_report_filename(filename)
    if not filename:
        return jsonify({"error": "演示文稿不存在"}), 404

    _report_file, owner_error = enforce_report_owner_or_404(filename, user_id)
    if owner_error:
        response, status_code = owner_error
        return response, status_code

    record = get_presentation_record(filename)
    if not record:
        return jsonify({"error": "演示文稿不存在"}), 404
    path_str = record.get("path")
    if not path_str:
        return jsonify({"error": "演示文稿不存在"}), 404
    file_path = Path(path_str)
    if not file_path.exists():
        return jsonify({"error": "演示文稿不存在"}), 404
    downloads_dir = get_downloads_dir()
    if not is_path_under(file_path, downloads_dir):
        return jsonify({"error": "演示文稿位置无效"}), 403
    return send_from_directory(
        directory=file_path.parent,
        path=file_path.name,
        as_attachment=False,
        download_name=record.get("filename") or file_path.name
    )


@app.route('/api/reports/<path:filename>/presentation/status', methods=['GET'])
def get_report_presentation_status(filename):
    user_id = get_current_user_id_or_none()
    if not user_id:
        return jsonify({"error": "请先登录"}), 401

    filename = normalize_presentation_report_filename(filename)
    if not filename:
        return jsonify({"exists": False})

    _report_file, owner_error = enforce_report_owner_or_404(filename, user_id)
    if owner_error:
        return jsonify({"exists": False})

    record = get_presentation_record(filename)
    if not record:
        return jsonify({"exists": False})

    pdf_url = record.get("pdf_url")
    execution_id = record.get("execution_id")
    stopped_at = record.get("stopped_at")

    if execution_id:
        owner = get_execution_owner_report(execution_id)
        if owner and owner != filename:
            if ENABLE_DEBUG_LOG:
                print(f"⚠️ 清理跨报告 execution_id: execution_id={execution_id}, owner={owner}, filename={filename}")
            clear_presentation_execution(filename)
            execution_id = ""

    if execution_id and stopped_at:
        clear_presentation_execution(filename)
        execution_id = ""

    path_str = record.get("path")
    file_exists = False
    if path_str:
        file_path = Path(path_str)
        downloads_dir = get_downloads_dir()
        if file_path.exists() and is_path_under(file_path, downloads_dir):
            file_exists = True

    processing = bool(execution_id and not pdf_url and not stopped_at)
    if processing:
        try:
            output_response = fetch_refly_output(execution_id)
            pdf_url = (
                extract_pdf_url_from_output(output_response)
                or build_pdf_url_from_result_info_file(output_response)
                or build_pdf_url_from_result_info(output_response)
            )
            if pdf_url:
                record_presentation_file(filename, None, pdf_url=pdf_url)
                processing = False
        except Exception:
            pass

    return jsonify({
        "exists": bool(pdf_url or file_exists),
        "pdf_url": pdf_url,
        "presentation_local_url": f"/api/reports/{quote(filename)}/presentation" if file_exists else "",
        "execution_id": execution_id,
        "processing": processing,
        "stopped": bool(stopped_at)
    })


@app.route('/api/reports/<path:filename>/presentation/link', methods=['GET'])
def get_report_presentation_link(filename):
    user_id = get_current_user_id_or_none()
    if not user_id:
        return jsonify({"error": "请先登录"}), 401

    filename = normalize_presentation_report_filename(filename)
    if not filename:
        return jsonify({"error": "演示文稿不存在"}), 404

    _report_file, owner_error = enforce_report_owner_or_404(filename, user_id)
    if owner_error:
        response, status_code = owner_error
        return response, status_code

    record = get_presentation_record(filename)
    if not record:
        return jsonify({"error": "演示文稿不存在"}), 404
    pdf_url = record.get("pdf_url")
    if not pdf_url:
        return jsonify({"error": "演示文稿不存在"}), 404
    return redirect(pdf_url, code=302)


# ============ 报告 API ============

def extract_appendix_markdown_from_report(content: str) -> str:
    report_text = str(content or "")
    marker = "## 附录：完整访谈记录"
    appendix_index = report_text.find(marker)
    if appendix_index < 0:
        return ""

    appendix = report_text[appendix_index:].strip()
    appendix = re.sub(r"^\s*\*\*生成方式\*\*:[^\n]*\n?", "", appendix, flags=re.MULTILINE)
    return appendix.strip()


def normalize_appendix_line_for_pdf(raw_line: str) -> str:
    line = html.unescape(str(raw_line or ""))
    if not line:
        return ""

    summary_match = re.match(r"^\s*<summary[^>]*>\s*(.*?)\s*</summary>\s*$", line, flags=re.IGNORECASE)
    if summary_match:
        line = f"### {summary_match.group(1).strip()}"

    line = re.sub(r"</?details[^>]*>", "", line, flags=re.IGNORECASE)
    line = re.sub(r"<br\s*/?>", " ", line, flags=re.IGNORECASE)
    line = re.sub(r"<[^>]+>", "", line)
    line = re.sub(r"\s+", " ", line).strip()
    line = line.replace("☑", "[√]").replace("☐", "[ ]")
    return line


def wrap_pdf_text(text: str, font_name: str, font_size: float, max_width: float) -> list[str]:
    content = str(text or "")
    if not content:
        return [""]

    wrapped: list[str] = []
    current = ""
    for ch in content:
        candidate = f"{current}{ch}"
        if current and pdfmetrics.stringWidth(candidate, font_name, font_size) > max_width:
            wrapped.append(current)
            current = ch
        else:
            current = candidate

    if current:
        wrapped.append(current)

    return wrapped or [""]


def resolve_appendix_cjk_font_path() -> str:
    candidates = [
        # macOS
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
        # Linux
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJKSC-Regular.otf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        # Windows
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
    ]
    for path in candidates:
        try:
            if Path(path).is_file():
                return path
        except Exception:
            continue
    return ""


def wrap_pil_text(draw: "ImageDraw.ImageDraw", text: str, font: "ImageFont.FreeTypeFont", max_width: int) -> list[str]:
    content = str(text or "")
    if not content:
        return [""]

    lines: list[str] = []
    current = ""
    for ch in content:
        candidate = f"{current}{ch}"
        width = draw.textlength(candidate, font=font)
        if current and width > max_width:
            lines.append(current)
            current = ch
        else:
            current = candidate

    if current:
        lines.append(current)
    return lines or [""]


def render_appendix_pages_as_images(appendix_markdown: str) -> list["Image.Image"]:
    if not PIL_AVAILABLE:
        return []

    page_width = 1240
    page_height = 1754
    margin_x = 86
    margin_y = 92
    max_width = page_width - margin_x * 2

    font_path = resolve_appendix_cjk_font_path()

    def load_font(size: int) -> "ImageFont.ImageFont":
        if font_path:
            try:
                return ImageFont.truetype(font_path, size=size)
            except Exception:
                pass
        return ImageFont.load_default()

    font_body = load_font(25)
    font_h3 = load_font(26)
    font_h2 = load_font(28)
    font_h1 = load_font(32)

    pages: list[Image.Image] = []
    image = Image.new("RGB", (page_width, page_height), "#FFFFFF")
    draw = ImageDraw.Draw(image)
    y = margin_y

    def new_page() -> None:
        nonlocal image, draw, y
        pages.append(image)
        image = Image.new("RGB", (page_width, page_height), "#FFFFFF")
        draw = ImageDraw.Draw(image)
        y = margin_y

    def ensure_space(height_needed: int) -> None:
        nonlocal y
        if y + height_needed <= page_height - margin_y:
            return
        new_page()

    for raw_line in str(appendix_markdown or "").splitlines():
        line = normalize_appendix_line_for_pdf(raw_line)
        if not line:
            y += 18
            continue

        text = line
        font = font_body
        line_height = 37
        spacing_after = 8

        if line.startswith("# "):
            text = line[2:].strip()
            font = font_h1
            line_height = 46
            spacing_after = 18
        elif line.startswith("## "):
            text = line[3:].strip()
            font = font_h2
            line_height = 40
            spacing_after = 16
        elif line.startswith("### "):
            text = line[4:].strip()
            font = font_h3
            line_height = 38
            spacing_after = 14
        elif line.startswith("- "):
            text = f"• {line[2:].strip()}"
            font = font_body
            line_height = 37
            spacing_after = 6

        wrapped_lines = wrap_pil_text(draw, text, font, max_width)
        ensure_space(len(wrapped_lines) * line_height + spacing_after)

        for segment in wrapped_lines:
            draw.text((margin_x, y), segment, fill="#111827", font=font)
            y += line_height
        y += spacing_after

    pages.append(image)
    return pages


def build_appendix_pdf_bytes_via_images(appendix_markdown: str) -> bytes:
    if not (REPORTLAB_AVAILABLE and PIL_AVAILABLE):
        raise RuntimeError("图像渲染依赖不可用")

    pages = render_appendix_pages_as_images(appendix_markdown)
    if not pages:
        raise RuntimeError("未生成有效图像页")

    buffer = BytesIO()
    pdf = report_canvas.Canvas(buffer, pagesize=A4, pageCompression=1)
    pdf_page_width, pdf_page_height = A4

    for page in pages:
        img_buffer = BytesIO()
        page.save(img_buffer, format="PNG")
        img_buffer.seek(0)
        pdf.drawImage(ImageReader(img_buffer), 0, 0, width=pdf_page_width, height=pdf_page_height, preserveAspectRatio=False, mask="auto")
        pdf.showPage()

    pdf.save()
    buffer.seek(0)
    return buffer.read()


def build_appendix_pdf_bytes(appendix_markdown: str) -> bytes:
    if not REPORTLAB_AVAILABLE:
        raise RuntimeError("reportlab 不可用")

    font_name = "STSong-Light"
    if font_name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(UnicodeCIDFont(font_name))

    buffer = BytesIO()
    pdf = report_canvas.Canvas(buffer, pagesize=A4, pageCompression=1)

    page_width, page_height = A4
    margin_x = 18 * mm
    margin_top = 18 * mm
    margin_bottom = 16 * mm
    max_width = page_width - margin_x * 2
    y = page_height - margin_top

    def ensure_space(height_needed: float) -> None:
        nonlocal y
        if y - height_needed < margin_bottom:
            pdf.showPage()
            y = page_height - margin_top

    for raw_line in str(appendix_markdown or "").splitlines():
        line = normalize_appendix_line_for_pdf(raw_line)
        if not line:
            ensure_space(8)
            y -= 8
            continue

        text = line
        font_size = 10.5
        line_height = 16
        spacing_after = 2

        if line.startswith("# "):
            text = line[2:].strip()
            font_size = 16
            line_height = 23
            spacing_after = 7
        elif line.startswith("## "):
            text = line[3:].strip()
            font_size = 14
            line_height = 21
            spacing_after = 6
        elif line.startswith("### "):
            text = line[4:].strip()
            font_size = 12.5
            line_height = 19
            spacing_after = 4
        elif line.startswith("- "):
            text = f"• {line[2:].strip()}"
            font_size = 10.5
            line_height = 16
            spacing_after = 2

        wrapped_lines = wrap_pdf_text(text, font_name, font_size, max_width)
        ensure_space(len(wrapped_lines) * line_height + spacing_after)

        pdf.setFont(font_name, font_size)
        for segment in wrapped_lines:
            pdf.drawString(margin_x, y, segment)
            y -= line_height
        y -= spacing_after

    pdf.save()
    buffer.seek(0)
    return buffer.read()


def load_reports_for_user_from_files(user_id_int: int) -> list[dict]:
    deleted = get_deleted_reports()
    owner_map = load_report_owners()
    expected_scope = get_active_instance_scope_key()
    reports_root = REPORTS_DIR.resolve()
    reports = []
    for report_name, owner_id in owner_map.items():
        if owner_id != int(user_id_int):
            continue
        if not is_instance_scope_visible(get_report_scope_key(report_name), expected_scope=expected_scope):
            continue
        if report_name in deleted:
            continue
        if not isinstance(report_name, str) or not report_name.endswith(".md"):
            continue

        report_path = (REPORTS_DIR / report_name).resolve()
        if report_path.parent != reports_root:
            continue
        if not report_path.exists() or not report_path.is_file():
            continue

        stat = report_path.stat()
        reports.append({
            "name": report_name,
            "path": str(report_path),
            "size": stat.st_size,
            "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat()
        })

    reports.sort(key=lambda x: x["created_at"], reverse=True)
    return reports


SOLUTION_DIMENSION_META = {
    "客户需求": {"badge": "需求聚焦", "summary": "围绕真实痛点定义目标、样本与优先级。"},
    "业务流程": {"badge": "关键触点", "summary": "锁定用户触达路径、界面节点与干预时机。"},
    "技术约束": {"badge": "技术底线", "summary": "明确合规、脱敏、性能与集成边界。"},
    "项目约束": {"badge": "交付边界", "summary": "平衡周期、预算、样本与落地节奏。"},
}


def normalize_solution_report_filename(report_filename: Optional[str]) -> str:
    return normalize_presentation_report_filename(report_filename)


def clean_solution_text(value: object, max_len: int = 0) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
    text = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", "", text)
    text = re.sub(r"(?m)^\s*[-*+]\s+", "", text)
    text = text.replace("**", "").replace("__", "").replace("`", "")
    text = re.sub(r"\s+", " ", text).strip(" \t\r\n-—|:：；;，。,.")
    if max_len and len(text) > max_len:
        text = text[:max_len].rstrip("，。,.;；：:!?？！ ") + "..."
    return text


def split_markdown_sections(content: str, heading_prefix: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    current_title = ""
    current_lines: list[str] = []
    for raw_line in str(content or "").splitlines():
        line = raw_line.rstrip("\n")
        if line.startswith(heading_prefix):
            if current_title:
                sections.append((clean_solution_text(current_title), "\n".join(current_lines).strip()))
            current_title = line[len(heading_prefix):].strip()
            current_lines = []
            continue
        if current_title:
            current_lines.append(line)
    if current_title:
        sections.append((clean_solution_text(current_title), "\n".join(current_lines).strip()))
    return sections


def parse_solution_bullet_item(raw_line: str) -> dict:
    text = str(raw_line or "").strip()
    if text.startswith("- "):
        text = text[2:].strip()
    match = re.match(r"^\*\*(.+?)\*\*\s*-\s*(.+)$", text)
    if match:
        return {
            "answer": clean_solution_text(match.group(1), max_len=88),
            "detail": clean_solution_text(match.group(2), max_len=180),
        }
    return {
        "answer": clean_solution_text(text, max_len=88),
        "detail": "",
    }


def dedupe_solution_items(items: list[dict], max_items: int = 8) -> list[dict]:
    seen = set()
    results = []
    for item in items:
        if not isinstance(item, dict):
            continue
        answer = clean_solution_text(item.get("answer", ""), max_len=88)
        detail = clean_solution_text(item.get("detail", ""), max_len=180)
        if not answer:
            continue
        key = answer.lower()
        if key in seen:
            continue
        seen.add(key)
        results.append({"answer": answer, "detail": detail})
        if len(results) >= max_items:
            break
    return results


def dedupe_solution_texts(values: list[object], max_items: int = 6, max_len: int = 24) -> list[str]:
    seen = set()
    results: list[str] = []
    for value in values:
        text = clean_solution_text(value, max_len=max_len)
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        results.append(text)
        if len(results) >= max_items:
            break
    return results


def get_solution_item_answer(items: list[dict], index: int, fallback: str = "") -> str:
    if 0 <= index < len(items):
        return clean_solution_text(items[index].get("answer", ""), max_len=88)
    return clean_solution_text(fallback, max_len=88)


def get_solution_item_detail(items: list[dict], index: int, fallback: str = "") -> str:
    if 0 <= index < len(items):
        return clean_solution_text(items[index].get("detail", ""), max_len=180)
    return clean_solution_text(fallback, max_len=180)


def compact_solution_term(value: object, max_len: int = 0) -> str:
    text = clean_solution_text(value)
    text = re.sub(r"（[^）]*）", "", text)
    text = re.sub(r"\([^\)]*\)", "", text)
    text = re.split(r"[：:]", text, maxsplit=1)[0]
    text = re.sub(r"\s+", " ", text).strip(" \t\r\n-—|:：；;，。,.")

    if max_len and len(text) > max_len and "后的" in text:
        tail = text.rsplit("后的", 1)[-1].strip()
        if 1 < len(tail) < len(text):
            text = tail

    if max_len and len(text) > max_len and "的" in text:
        tail = text.rsplit("的", 1)[-1].strip()
        if 1 < len(tail) <= max_len:
            text = tail

    if max_len and len(text) > max_len:
        text = text[:max_len].rstrip("，。,.;；：:!?？！ ") + "..."
    return text or clean_solution_text(value, max_len=max_len)


def normalize_solution_meta_label(value: object, fallback: str = "访谈信息") -> str:
    text = clean_solution_text(value, max_len=28)
    text = re.sub(r"^\d+(?:\.\d+)*\s*", "", text)
    return text or fallback


def build_solution_overview_meta(
    overview_section: str,
    scene: str,
    pain_point: str,
    entry_point: str,
    tech_constraint: str,
    project_constraint: str,
) -> list[dict]:
    _ = overview_section
    candidates = [
        ("聚焦场景", scene or "待明确", 18),
        ("核心目标", pain_point or "待明确", 16),
        ("推进切口", entry_point or "待明确", 14),
        ("交付边界", project_constraint or tech_constraint or "待明确", 16),
    ]
    items: list[dict] = []
    for label, value, limit in candidates:
        normalized = compact_solution_term(value, max_len=limit)
        if not normalized:
            continue
        items.append({"label": label, "value": normalized})
    return items


def build_solution_overview_text(
    report_title: str,
    scene: str,
    pain_point: str,
    entry_point: str,
    tech_constraint: str,
    project_constraint: str,
    overview_meta: list[dict],
) -> str:
    _ = tech_constraint
    _ = project_constraint
    _ = overview_meta
    scene_brief = compact_solution_term(scene or report_title, max_len=16)
    pain_brief = compact_solution_term(pain_point or "核心问题", max_len=14)
    entry_brief = compact_solution_term(entry_point or "关键触点", max_len=12)
    return f"聚焦「{scene_brief}」，先解决「{pain_brief}」，从「{entry_brief}」启动首轮试点。"


def extract_solution_requirements(summary_content: str) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {}
    for title, body in split_markdown_sections(summary_content, "### "):
        parsed_items = []
        for raw_line in body.splitlines():
            line = raw_line.strip()
            if not line.startswith("- "):
                continue
            parsed_items.append(parse_solution_bullet_item(line))
        if parsed_items:
            groups[clean_solution_text(title, max_len=32)] = dedupe_solution_items(parsed_items, max_items=10)
    return groups


def extract_solution_overview_facts(overview_content: str) -> dict[str, str]:
    facts: dict[str, str] = {}
    for raw_line in str(overview_content or "").splitlines():
        line = raw_line.strip()
        if not line.startswith("- "):
            continue

        match = re.match(r"^- \*\*(.+?)\*\*\s*-\s*(.+)$", line)
        if match:
            label = normalize_solution_meta_label(match.group(1))
            value = clean_solution_text(match.group(2), max_len=180)
        else:
            body = line[2:].strip()
            parts = re.split(r"\s*[：:-]\s*", body, maxsplit=1)
            if len(parts) != 2:
                continue
            label = normalize_solution_meta_label(parts[0])
            value = clean_solution_text(parts[1], max_len=180)

        if label and value and label not in facts:
            facts[label] = value
    return facts


def extract_solution_overview_topic(overview_content: str) -> str:
    text = clean_solution_text(overview_content, max_len=180)
    match = re.search(r'本次访谈主题为[「"]?(.+?)[」"]?[，。,]', text)
    if match:
        return clean_solution_text(match.group(1), max_len=60)
    return ""


def simplify_solution_subject(value: object, max_len: int = 0) -> str:
    text = clean_solution_text(value)
    if not text:
        return ""

    text = text.replace("DeepVision", "").replace("深瞳", "").strip()
    original = text
    patterns = [
        r"(产品)?需求调研报告$",
        r"需求调研报告$",
        r"调研报告$",
        r"访谈报告$",
        r"报告$",
        r"(产品)?需求调研$",
        r"需求调研$",
        r"专题调研$",
        r"调研$",
    ]

    for pattern in patterns:
        candidate = re.sub(pattern, "", text).strip(" \t\r\n-—|:：；;，。,.《》「」")
        if len(candidate) >= 2:
            text = candidate
            break

    return compact_solution_term(text or original, max_len=max_len)


def is_solution_generic_subject(value: object) -> bool:
    text = clean_solution_text(value)
    if not text:
        return True
    if "报告" in text or "调研" in text:
        return True
    if "访谈" in text and len(text) >= 8:
        return True
    return False


def infer_solution_metrics(report_title: str, report_text: str) -> list[dict]:
    combined = f"{report_title}\n{report_text}"

    def contains_any(keywords: list[str]) -> bool:
        return any(keyword in combined for keyword in keywords)

    metrics = [
        {
            "label": "调研效率",
            "value": "65-80%" if contains_any(["效率", "自动化", "人工", "回收", "耗时"]) else "35-50%",
            "note": "用于衡量访谈组织与整理效率的预估改善幅度",
        },
        {
            "label": "有效洞察率",
            "value": "40-60%" if contains_any(["洞察", "归因", "真实痛点", "敷衍", "无效"]) else "25-40%",
            "note": "用于衡量高价值回答与根因识别的预估提升",
        },
        {
            "label": "风险识别",
            "value": "20-35%" if contains_any(["风控", "安全", "误拦截", "合规", "隐私", "脱敏"]) else "15-25%",
            "note": "用于衡量高风险场景识别与拦截误伤校准",
        },
        {
            "label": "试点周期",
            "value": "4-8周" if contains_any(["2-3个月", "短周期", "试点", "投放"]) else "3-6周",
            "note": "从方案对齐到首轮验证的建议节奏",
        },
    ]
    return metrics


def infer_solution_risk_guardrail(answer: str) -> str:
    text = str(answer or "")
    if any(keyword in text for keyword in ["隐私", "合规", "脱敏", "加密"]):
        return "先冻结脱敏规则、留痕范围与本地处理边界，再推进采集。"
    if any(keyword in text for keyword in ["招募", "投放", "样本", "触发"]):
        return "先验证样本获取路径，再扩大投放，避免低质样本稀释结论。"
    if any(keyword in text for keyword in ["复现", "模拟器", "录屏", "UI"]):
        return "采用分层复现策略，优先低保真验证，再投入高仿真开发。"
    if any(keyword in text for keyword in ["周期", "预算", "资源"]):
        return "把试点范围、验收口径和资源上限前置锁定，避免中途扩张。"
    return "通过试点范围、验收门槛和里程碑复盘控制执行风险。"


def build_solution_focus_cards(
    customer_items: list[dict],
    process_items: list[dict],
    scene: str,
    entry_point: str,
) -> list[dict]:
    return [
        {
            "title": "场景切口",
            "summary": get_solution_item_answer(customer_items, 5, fallback=scene or "围绕高价值场景优先切入"),
            "detail": get_solution_item_detail(customer_items, 5, fallback="把业务场景进一步收窄到可验证切口。"),
        },
        {
            "title": "用户心理",
            "summary": get_solution_item_answer(
                customer_items,
                8,
                fallback=get_solution_item_answer(customer_items, 7, fallback="补齐用户心理与替代方案决策链路"),
            ),
            "detail": get_solution_item_detail(customer_items, 8, fallback="优先还原用户在关键触点的决策与情绪机制。"),
        },
        {
            "title": "流程触点",
            "summary": get_solution_item_answer(process_items, 2, fallback=entry_point or "补齐触发节点与操作路径"),
            "detail": get_solution_item_detail(process_items, 2, fallback="把触点、时机和交互阻塞点映射到方案动作。"),
        },
    ]


def build_solution_dimension_cards(requirement_groups: dict[str, list[dict]]) -> list[dict]:
    cards: list[dict] = []
    for name in ["客户需求", "业务流程", "技术约束", "项目约束"]:
        items = requirement_groups.get(name, [])
        meta = SOLUTION_DIMENSION_META.get(name, {"badge": "业务板块", "summary": "结合访谈内容补齐该板块。"})
        points = dedupe_solution_texts([item.get("answer", "") for item in items] or [meta["summary"]], max_items=4, max_len=44)
        cards.append({
            "name": name,
            "badge": meta["badge"],
            "summary": get_solution_item_answer(items, 0, fallback=meta["summary"]),
            "points": points,
        })
    return cards


def build_solution_roadmap(
    report_title: str,
    scene: str,
    pain_point: str,
    entry_point: str,
    tech_constraint: str,
    project_constraint: str,
    process_items: list[dict],
    project_items: list[dict],
) -> list[dict]:
    return [
        {
            "phase": "阶段一 · 场景对齐",
            "timeline": "第1-2周",
            "goal": f"围绕「{scene or report_title}」统一试点范围、问题树与成功指标。",
            "tasks": [
                f"把「{pain_point or '核心问题'}」拆成首轮方案目标与验证假设。",
                f"明确「{scene or '业务场景'}」下的样本分层、样本量与回收标准。",
                "沉淀首版方案目录、指标口径与试点验收门槛。",
            ],
        },
        {
            "phase": "阶段二 · 方案设计",
            "timeline": "第3-5周",
            "goal": f"围绕「{entry_point or '关键触点'}」形成可试跑的业务流程与交互方案。",
            "tasks": [
                f"把「{get_solution_item_answer(process_items, 0, fallback='关键流程')}」映射为关键触点与交互节点。",
                f"将「{tech_constraint or '技术约束'}」纳入采集、脱敏和性能设计边界。",
                "输出触点原型、访谈脚本和业务协同清单，小范围试跑验证。",
            ],
        },
        {
            "phase": "阶段三 · 试点验证",
            "timeline": "第6-8周",
            "goal": f"在「{project_constraint or '交付约束'}」下完成试点验证、收益复盘与迭代。",
            "tasks": [
                f"按「{get_solution_item_answer(project_items, 1, fallback='试点投放策略')}」安排样本触达与回收节奏。",
                "追踪调研效率、有效洞察率与业务反馈，校准方案优先级。",
                "形成二期扩展建议，确定正式推广范围与资源投入。",
            ],
        },
    ]


def build_solution_value_cards(metrics: list[dict], entry_point: str, scene: str, report_title: str) -> list[dict]:
    return [
        {"title": metrics[0]["label"], "value": metrics[0]["value"], "description": metrics[0]["note"]},
        {"title": metrics[1]["label"], "value": metrics[1]["value"], "description": metrics[1]["note"]},
        {
            "title": "场景复盘速度",
            "value": "2-3倍",
            "description": f"针对「{entry_point or scene or report_title}」建立从触点到结论的闭环节奏。",
        },
        {
            "title": metrics[2]["label"],
            "value": metrics[2]["value"],
            "description": metrics[2]["note"],
        },
    ]


def build_solution_risk_cards(tech_items: list[dict], project_items: list[dict]) -> list[dict]:
    risk_source_items = tech_items[:2] + project_items[:2]
    risk_cards = []
    for item in risk_source_items:
        risk_cards.append({
            "title": item["answer"],
            "description": item["detail"] or "该约束会直接影响方案范围、样本质量或技术实现。",
            "guardrail": infer_solution_risk_guardrail(item["answer"]),
        })
    if not risk_cards:
        risk_cards.append({
            "title": "样本与资源边界待确认",
            "description": "建议先锁定试点范围、样本口径和验收标准。",
            "guardrail": "先做小规模试点，再扩展正式落地范围。",
        })
    return risk_cards


def build_solution_action_items(
    scene: str,
    pain_point: str,
    entry_point: str,
    tech_constraint: str,
    project_constraint: str,
) -> list[dict]:
    return [
        {"owner": "产品", "title": f"把「{pain_point or '核心问题'}」拆成一级目标", "detail": "输出方案目标、成功指标和验收口径。"},
        {"owner": "研究", "title": f"围绕「{scene or '业务场景'}」补齐样本招募规则", "detail": "明确访谈对象、触发时机与样本筛选条件。"},
        {"owner": "设计", "title": f"针对「{entry_point or '关键触点'}」制作单页原型", "detail": "把用户路径、关键文案和交互状态沉淀成可试跑原型。"},
        {"owner": "研发", "title": f"落实「{tech_constraint or '技术约束'}」边界", "detail": "优先处理脱敏、性能和埋点实现边界。"},
        {"owner": "运营", "title": f"按「{project_constraint or '项目约束'}」组织试点节奏", "detail": "制定触达方案、回收节奏与复盘机制。"},
    ]


def build_solution_decision_summary(
    scene_brief: str,
    pain_brief: str,
    entry_brief: str,
    constraint_brief: str,
) -> str:
    return clean_solution_text(
        f"建议围绕「{scene_brief or '当前场景'}」启动首轮试点，优先从「{entry_brief or '关键触点'}」切入验证「{pain_brief or '核心问题'}」的改善空间，并在「{constraint_brief or '既定边界'}」范围内形成可复盘的执行闭环。",
        max_len=120,
    )


def build_solution_decision_cards(
    pain_point: str,
    entry_point: str,
    tech_constraint: str,
    project_constraint: str,
    focus_cards: list[dict],
    roadmap: list[dict],
    metrics: list[dict],
) -> list[dict]:
    constraint = project_constraint or tech_constraint or "既定交付边界"
    first_phase = roadmap[0]["phase"] if roadmap else "首轮试点"
    return [
        {
            "title": "推进时机已经成熟",
            "summary": clean_solution_text(
                focus_cards[0].get("summary") if focus_cards else f"当前报告已把「{pain_point or '核心问题'}」收敛成可验证的试点主题。",
                max_len=80,
            ),
            "detail": clean_solution_text(
                f"围绕「{pain_point or '核心问题'}」的目标、问题树与验收方向已经清楚，可直接进入「{first_phase}」统一评审口径。",
                max_len=180,
            ),
        },
        {
            "title": "首轮切口足够聚焦",
            "summary": clean_solution_text(
                f"优先从「{entry_point or '关键触点'}」切入，更容易在短周期内验证用户反馈和组织协同。",
                max_len=80,
            ),
            "detail": clean_solution_text(
                f"结合流程触点与用户心理信息，先观察{metrics[0]['label']}和{metrics[1]['label']}两项改善，再决定是否扩展范围。",
                max_len=180,
            ),
        },
        {
            "title": "执行边界可提前锁定",
            "summary": clean_solution_text(
                f"在「{constraint}」范围内小步试点，能把投入、风险和协同复杂度控制在可管理区间。",
                max_len=80,
            ),
            "detail": clean_solution_text(
                f"将「{tech_constraint or '技术约束'}」前置为设计与评审边界，可降低试点中途因为合规、性能或资源问题返工的概率。",
                max_len=180,
            ),
        },
    ]


def build_solution_comparison_items(
    scene: str,
    pain_point: str,
    entry_point: str,
    project_constraint: str,
) -> list[dict]:
    scene_text = scene or "当前场景"
    pain_text = pain_point or "核心问题"
    entry_text = entry_point or "关键触点"
    constraint_text = project_constraint or "既定交付边界"
    return [
        {
            "label": "问题识别",
            "traditional": "传统推进往往先收集纪要，再由不同角色各自解读问题，根因判断容易分散。",
            "proposed": f"DeepVision 先围绕「{scene_text}」提炼问题树，把「{pain_text}」明确为首轮验证主题。",
            "effect": "让问题定义、验证目标和优先级在同一份方案里达成统一。",
        },
        {
            "label": "推进路径",
            "traditional": "通常需要多轮会议逐步收敛范围，方案与试点入口经常在沟通里反复摇摆。",
            "proposed": f"直接以「{entry_text}」作为首轮切口，同时把模块、里程碑和动作清单一次成型。",
            "effect": "缩短从报告生成到进入试点评审的准备链路。",
        },
        {
            "label": "协同方式",
            "traditional": "产品、设计、研发与运营分别维护各自文档，边界条件往往在执行中途才暴露。",
            "proposed": f"在方案阶段就把约束写进结构化章节，按「{constraint_text}」提前锁定试点边界。",
            "effect": "减少返工、口径不一致和责任不清的协同损耗。",
        },
        {
            "label": "价值沉淀",
            "traditional": "单次调研结论很难继续复用，经验沉淀容易停留在个人或项目群聊里。",
            "proposed": "将访谈结论沉淀为提案式方案页，统一保存对比、路径、风险与价值论证。",
            "effect": "首轮试点的成功经验可以更顺畅地复制到后续场景。",
        },
    ]


def build_solution_architecture_nodes(
    report_title: str,
    scene: str,
    pain_point: str,
    entry_point: str,
    tech_constraint: str,
    project_constraint: str,
    customer_items: list[dict],
    process_items: list[dict],
    tech_items: list[dict],
    project_items: list[dict],
    metrics: list[dict],
) -> list[dict]:
    customer_terms = dedupe_solution_texts([scene, pain_point] + [item.get("answer", "") for item in customer_items], max_items=4, max_len=22)
    process_terms = dedupe_solution_texts([entry_point] + [item.get("answer", "") for item in process_items], max_items=4, max_len=22)
    tech_terms = dedupe_solution_texts([tech_constraint] + [item.get("answer", "") for item in tech_items], max_items=3, max_len=22)
    project_terms = dedupe_solution_texts([project_constraint] + [item.get("answer", "") for item in project_items], max_items=3, max_len=22)
    metric_terms = dedupe_solution_texts([item.get("label", "") for item in metrics], max_items=3, max_len=18)

    return [
        {
            "stage": "输入层",
            "title": "访谈输入",
            "summary": clean_solution_text(f"围绕「{scene or report_title}」组织样本、问题与原始回答，形成首轮输入池。", max_len=120),
            "inputs": customer_terms[:3] or [compact_solution_term(scene or report_title, max_len=20)],
            "outputs": dedupe_solution_texts(["原始回答", entry_point or "关键触点", "试点范围"], max_items=3, max_len=18),
        },
        {
            "stage": "识别层",
            "title": "问题诊断",
            "summary": clean_solution_text(f"把「{pain_point or '核心问题'}」拆成问题树、优先级与成功指标，避免停留在表层反馈。", max_len=120),
            "inputs": (customer_terms[:2] + process_terms[:1]) or [compact_solution_term(pain_point or "核心问题", max_len=20)],
            "outputs": ["问题树", "优先级", "成功指标"],
        },
        {
            "stage": "编排层",
            "title": "方案编排",
            "summary": clean_solution_text(f"将「{entry_point or '关键触点'}」相关问题映射成模块方案、协同动作与边界控制。", max_len=120),
            "inputs": (process_terms[:2] + tech_terms[:1]) or [compact_solution_term(entry_point or "关键触点", max_len=20)],
            "outputs": ["模块清单", "协作动作", "控制边界"],
        },
        {
            "stage": "执行层",
            "title": "试点推进",
            "summary": clean_solution_text(f"在「{project_constraint or '交付边界'}」内，把方案转成原型、任务清单和试点节奏。", max_len=120),
            "inputs": (project_terms[:2] + tech_terms[:1]) or [compact_solution_term(project_constraint or "交付边界", max_len=20)],
            "outputs": ["试点原型", "任务清单", "评审口径"],
        },
        {
            "stage": "回流层",
            "title": "价值复盘",
            "summary": clean_solution_text("通过指标回收与业务反馈复盘，决定是否进入二期扩展和规模化推广。", max_len=120),
            "inputs": metric_terms or ["调研效率", "有效洞察率"],
            "outputs": ["价值测算", "二期建议", "推广条件"],
        },
    ]


def build_solution_dataflow_steps(
    scene: str,
    pain_point: str,
    entry_point: str,
    tech_constraint: str,
    roadmap: list[dict],
    metrics: list[dict],
) -> list[dict]:
    phase_goal = roadmap[1]["goal"] if len(roadmap) > 1 else "形成可试跑的方案与原型"
    metric_names = "、".join(item["label"] for item in metrics[:2]) or "关键指标"
    return [
        {
            "stage": "01",
            "title": "锁定试点范围",
            "detail": clean_solution_text(f"围绕「{scene or '当前场景'}」明确样本范围、触发时机和验收门槛。", max_len=120),
            "owner": "产品 / 研究",
        },
        {
            "stage": "02",
            "title": "提炼问题树",
            "detail": clean_solution_text(f"把「{pain_point or '核心问题'}」拆成一级问题、假设和优先级，统一评审口径。", max_len=120),
            "owner": "研究 / 产品",
        },
        {
            "stage": "03",
            "title": "组装模块方案",
            "detail": clean_solution_text(f"围绕「{entry_point or '关键触点'}」输出模块划分、原型方向和协作清单。", max_len=120),
            "owner": "产品 / 设计",
        },
        {
            "stage": "04",
            "title": "搭建试点与验证",
            "detail": clean_solution_text(f"{phase_goal}，并把「{tech_constraint or '技术约束'}」前置到采集、脱敏和埋点设计中。", max_len=120),
            "owner": "设计 / 研发",
        },
        {
            "stage": "05",
            "title": "回收指标并扩展",
            "detail": clean_solution_text(f"持续跟踪{metric_names}，基于业务反馈决定是否进入二期扩展。", max_len=120),
            "owner": "运营 / 管理",
        },
    ]


def build_solution_value_table(
    scene_brief: str,
    entry_brief: str,
    constraint_brief: str,
    metrics: list[dict],
) -> list[dict]:
    scene_text = scene_brief or "当前场景"
    entry_text = entry_brief or "关键触点"
    constraint_text = constraint_brief or "试点边界"
    return [
        {
            "domain": scene_text,
            "metric": metrics[0]["label"],
            "baseline": "依赖人工整理纪要，访谈结论分散在多个文档里",
            "target": metrics[0]["value"],
            "effect": "缩短从访谈结束到进入评审的整理与对齐周期。",
        },
        {
            "domain": scene_text,
            "metric": metrics[1]["label"],
            "baseline": "高价值问题识别依赖个人经验，方案动作难以统一",
            "target": metrics[1]["value"],
            "effect": "提升高价值洞察与落地动作之间的匹配度。",
        },
        {
            "domain": entry_text,
            "metric": "方案启动速度",
            "baseline": "方案需要多轮串行沟通后才能进入试点",
            "target": metrics[3]["value"],
            "effect": "让关键触点在固定周期内形成可试跑方案与验收口径。",
        },
        {
            "domain": entry_text,
            "metric": "场景复盘速度",
            "baseline": "项目结束后经验难以抽取，后续团队复用成本高",
            "target": "2-3倍",
            "effect": "把试点结论沉淀为可复用的提案结构和推进模板。",
        },
        {
            "domain": constraint_text,
            "metric": metrics[2]["label"],
            "baseline": "风险往往在执行后期才暴露，返工成本高",
            "target": metrics[2]["value"],
            "effect": "将合规、脱敏和资源边界前置到方案评审阶段。",
        },
    ]


def build_solution_payload_from_report(report_name: str, report_content: str) -> dict:
    normalized_content = normalize_report_time_fields(str(report_content or ""))
    report_text = strip_inline_evidence_markers(normalized_content)
    main_report_text = report_text.split("## 附录：完整访谈记录", 1)[0].strip()
    report_title = "访谈报告"
    for raw_line in main_report_text.splitlines():
        line = raw_line.strip()
        if line.startswith("# "):
            report_title = clean_solution_text(line[2:].replace("访谈报告", ""), max_len=60) or "访谈报告"
            break

    sections_level2 = split_markdown_sections(main_report_text, "## ")
    overview_section = ""
    summary_section = ""
    for title, body in sections_level2:
        if "访谈概述" in title and not overview_section:
            overview_section = body
        if "需求摘要" in title and not summary_section:
            summary_section = body

    overview_facts = extract_solution_overview_facts(overview_section)
    overview_topic = extract_solution_overview_topic(overview_section)
    requirement_groups = extract_solution_requirements(summary_section)
    customer_items = requirement_groups.get("客户需求", [])
    process_items = requirement_groups.get("业务流程", [])
    tech_items = requirement_groups.get("技术约束", [])
    project_items = requirement_groups.get("项目约束", [])

    fallback_subject = simplify_solution_subject(overview_topic or report_title, max_len=24) or compact_solution_term(report_title, max_len=24)
    scene = overview_facts.get("访谈场景") or get_solution_item_answer(customer_items, 1, fallback=get_solution_item_answer(process_items, 0, fallback=fallback_subject or report_title))
    pain_point = overview_facts.get("核心问题") or get_solution_item_answer(customer_items, 3, fallback=get_solution_item_answer(customer_items, 2, fallback="需要进一步明确核心痛点"))
    entry_point = overview_facts.get("关键触点") or get_solution_item_answer(process_items, 1, fallback=get_solution_item_answer(customer_items, 5, fallback="关键业务触点"))
    tech_constraint = overview_facts.get("技术约束") or get_solution_item_answer(tech_items, 0, fallback="技术与合规边界待进一步确认")
    project_constraint = overview_facts.get("项目约束") or get_solution_item_answer(project_items, 0, fallback="交付边界与资源约束待进一步确认")

    scene_brief = compact_solution_term(scene or fallback_subject or report_title, max_len=18)
    if is_solution_generic_subject(scene_brief):
        scene_brief = simplify_solution_subject(scene or overview_topic or report_title, max_len=18) or scene_brief
    pain_brief = compact_solution_term(pain_point or "核心问题", max_len=16)
    entry_brief = compact_solution_term(entry_point or "关键触点", max_len=14)
    constraint_brief = compact_solution_term(project_constraint or tech_constraint or "待明确", max_len=16)
    display_subject = scene_brief
    if is_solution_generic_subject(display_subject):
        display_subject = simplify_solution_subject(entry_point, max_len=18) or simplify_solution_subject(pain_point, max_len=18) or "访谈结论"

    overview_meta = build_solution_overview_meta(
        overview_section,
        scene,
        pain_point,
        entry_point,
        tech_constraint,
        project_constraint,
    )
    overview_text = build_solution_overview_text(
        report_title,
        scene,
        pain_point,
        entry_point,
        tech_constraint,
        project_constraint,
        overview_meta,
    )
    metrics = infer_solution_metrics(report_title, main_report_text)
    focus_cards = build_solution_focus_cards(customer_items, process_items, scene, entry_point)
    dimension_cards = build_solution_dimension_cards(requirement_groups)
    roadmap = build_solution_roadmap(
        report_title,
        scene,
        pain_point,
        entry_point,
        tech_constraint,
        project_constraint,
        process_items,
        project_items,
    )
    value_cards = build_solution_value_cards(metrics, entry_point, scene, report_title)
    risk_cards = build_solution_risk_cards(tech_items, project_items)
    action_items = build_solution_action_items(scene, pain_point, entry_point, tech_constraint, project_constraint)
    decision_summary = build_solution_decision_summary(scene_brief, pain_brief, entry_brief, constraint_brief)
    decision_cards = build_solution_decision_cards(
        pain_point,
        entry_point,
        tech_constraint,
        project_constraint,
        focus_cards,
        roadmap,
        metrics,
    )
    comparison_items = build_solution_comparison_items(scene, pain_point, entry_point, project_constraint)
    architecture_nodes = build_solution_architecture_nodes(
        report_title,
        scene,
        pain_point,
        entry_point,
        tech_constraint,
        project_constraint,
        customer_items,
        process_items,
        tech_items,
        project_items,
        metrics,
    )
    dataflow_steps = build_solution_dataflow_steps(scene, pain_point, entry_point, tech_constraint, roadmap, metrics)
    value_table = build_solution_value_table(scene_brief, entry_brief, constraint_brief, metrics)

    headline_cards = [
        {"label": "业务场景", "value": scene_brief or display_subject or "待明确", "detail": "当前最优先推进的访谈应用场景"},
        {"label": "核心问题", "value": pain_brief or "待明确", "detail": "首轮试点需要验证并改善的核心问题"},
        {"label": "优先触点", "value": entry_brief or "待明确", "detail": "建议先落地验证的业务切入口"},
        {"label": "落地约束", "value": constraint_brief or "待明确", "detail": "推进前必须先确认的交付边界"},
    ]

    solution_title = clean_solution_text(
        f"{display_subject or scene_brief or compact_solution_term(report_title, max_len=18) or report_title}落地方案",
        max_len=40,
    )
    subtitle = clean_solution_text(
        f"聚焦「{scene_brief or display_subject or report_title}」，优先验证「{pain_brief or '核心问题'}」，从「{entry_brief or '关键触点'}」切入形成首轮执行闭环。",
        max_len=72,
    )

    return {
        "report_name": report_name,
        "title": solution_title,
        "subtitle": subtitle,
        "overview": overview_text,
        "overview_meta": overview_meta,
        "metrics": metrics,
        "nav_items": [
            {"id": "decision", "label": "方案判断"},
            {"id": "comparison", "label": "方案对比"},
            {"id": "modules", "label": "落地模块"},
            {"id": "architecture", "label": "能力架构"},
            {"id": "dataflow", "label": "闭环机制"},
            {"id": "value", "label": "价值测算"},
            {"id": "roadmap", "label": "实施路径"},
            {"id": "risks", "label": "风险边界"},
            {"id": "actions", "label": "下一步推进"},
        ],
        "headline_cards": headline_cards,
        "focus_cards": focus_cards,
        "dimension_cards": dimension_cards,
        "roadmap": roadmap,
        "value_cards": value_cards,
        "risk_cards": risk_cards,
        "action_items": action_items,
        "decision_summary": decision_summary,
        "decision_cards": decision_cards,
        "comparison_items": comparison_items,
        "architecture_nodes": architecture_nodes,
        "dataflow_steps": dataflow_steps,
        "value_table": value_table,
    }


@app.route('/api/reports', methods=['GET'])
def list_reports():
    """获取所有报告（排除已删除的）"""
    user_id = get_current_user_id_or_none()
    if not user_id:
        return jsonify({"error": "请先登录"}), 401

    page, page_size, offset = parse_list_pagination_params()
    started_at = _time.perf_counter()
    if not try_acquire_list_semaphore("reports_list", REPORTS_LIST_SEMAPHORE):
        response = build_overload_response("reports_list")
        latency_ms = (_time.perf_counter() - started_at) * 1000
        record_list_request_metric(
            endpoint="reports_list",
            status_code=429,
            latency_ms=latency_ms,
            source="overload",
            page_size=page_size,
            returned_count=0,
            total_count=0,
            error_reason="overload",
        )
        return response

    try:
        user_id_int = int(user_id)
        data_source = "sqlite"
        scan_ms = 0.0

        try:
            ensure_report_index_bootstrapped()
            reports, total = query_report_index_for_user(user_id_int, page, page_size)
        except Exception as exc:
            data_source = "file_scan"
            if ENABLE_DEBUG_LOG:
                _safe_log(f"⚠️ report_index 查询失败，回退文件扫描: {exc}")
            scan_started_at = _time.perf_counter()
            all_reports = load_reports_for_user_from_files(user_id_int)
            scan_ms = (_time.perf_counter() - scan_started_at) * 1000
            total = len(all_reports)
            reports = all_reports[offset: offset + page_size]

        etag = build_list_etag(
            endpoint="reports_list",
            page=page,
            page_size=page_size,
            total=total,
            items=reports,
        )
        if_none_match_values = parse_if_none_match_values()
        if etag in if_none_match_values or "*" in if_none_match_values:
            response = build_not_modified_response(etag, page=page, page_size=page_size, total=total)
            latency_ms = (_time.perf_counter() - started_at) * 1000
            record_list_request_metric(
                endpoint="reports_list",
                status_code=304,
                latency_ms=latency_ms,
                source=data_source,
                page_size=page_size,
                returned_count=0,
                total_count=total,
                scan_ms=scan_ms,
            )
            return response

        response = jsonify(reports)
        response.headers["ETag"] = etag
        response.headers["Cache-Control"] = "private, max-age=2"
        latency_ms = (_time.perf_counter() - started_at) * 1000
        record_list_request_metric(
            endpoint="reports_list",
            status_code=200,
            latency_ms=latency_ms,
            source=data_source,
            page_size=page_size,
            returned_count=len(reports),
            total_count=total,
            scan_ms=scan_ms,
        )
        return apply_pagination_headers(response, page=page, page_size=page_size, total=total)
    except Exception as exc:
        latency_ms = (_time.perf_counter() - started_at) * 1000
        record_list_request_metric(
            endpoint="reports_list",
            status_code=500,
            latency_ms=latency_ms,
            source="unknown",
            page_size=page_size,
            returned_count=0,
            total_count=0,
            error_reason=type(exc).__name__,
        )
        raise
    finally:
        REPORTS_LIST_SEMAPHORE.release()


@app.route('/api/reports/<path:filename>', methods=['GET'])
def get_report(filename):
    """获取报告内容"""
    user_id = get_current_user_id_or_none()
    if not user_id:
        return jsonify({"error": "请先登录"}), 401

    report_file, owner_error = enforce_report_owner_or_404(filename, user_id)
    if owner_error:
        response, status_code = owner_error
        return response, status_code

    content = report_file.read_text(encoding="utf-8")
    try:
        generated_at = datetime.fromtimestamp(report_file.stat().st_mtime)
    except Exception:
        generated_at = None
    content = normalize_report_time_fields(content, generated_at=generated_at)
    return jsonify({"name": filename, "content": content})


@app.route('/api/reports/<path:filename>/solution', methods=['GET'])
def get_report_solution(filename):
    user_id = get_current_user_id_or_none()
    if not user_id:
        return jsonify({"error": "请先登录"}), 401

    normalized = normalize_solution_report_filename(filename)
    if not normalized:
        return jsonify({"error": "报告文件名无效"}), 400

    report_file, owner_error = enforce_report_owner_or_404(normalized, user_id)
    if owner_error:
        response, status_code = owner_error
        return response, status_code

    content = report_file.read_text(encoding="utf-8")
    try:
        generated_at = datetime.fromtimestamp(report_file.stat().st_mtime)
    except Exception:
        generated_at = None
    content = normalize_report_time_fields(content, generated_at=generated_at)
    payload = build_solution_payload_from_report(normalized, content)
    return jsonify(payload)


@app.route('/api/reports/<path:filename>/appendix/pdf', methods=['GET'])
def export_report_appendix_pdf(filename):
    user_id = get_current_user_id_or_none()
    if not user_id:
        return jsonify({"error": "请先登录"}), 401

    report_file, owner_error = enforce_report_owner_or_404(filename, user_id)
    if owner_error:
        response, status_code = owner_error
        return response, status_code

    if not REPORTLAB_AVAILABLE:
        return jsonify({"error": "服务端 PDF 导出能力不可用"}), 503

    report_content = report_file.read_text(encoding="utf-8")
    appendix_markdown = extract_appendix_markdown_from_report(report_content)
    if not appendix_markdown:
        return jsonify({"error": "未找到附录内容"}), 404

    try:
        # 优先走图像渲染，规避部分 PDF 阅读器对 CJK 字体兼容导致的空白问题
        if PIL_AVAILABLE:
            pdf_bytes = build_appendix_pdf_bytes_via_images(appendix_markdown)
        else:
            pdf_bytes = build_appendix_pdf_bytes(appendix_markdown)
    except Exception as exc:
        print(f"⚠️ 附录 PDF 图像渲染失败，回退文本渲染: {exc}")
        try:
            pdf_bytes = build_appendix_pdf_bytes(appendix_markdown)
        except Exception as text_exc:
            print(f"⚠️ 附录 PDF 生成失败: {text_exc}")
            return jsonify({"error": "附录 PDF 生成失败"}), 500

    download_name = f"{Path(filename).stem}-完整访谈记录.pdf"
    return send_file(
        BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=download_name,
    )


@app.route('/api/reports/<path:filename>/refly', methods=['POST'])
def send_report_to_refly(filename):
    """将报告发送到演示文稿服务生成演示文稿"""
    user_id = get_current_user_id_or_none()
    if not user_id:
        return jsonify({"error": "请先登录"}), 401

    filename = normalize_presentation_report_filename(filename)
    if not filename:
        return jsonify({"error": "报告文件名无效"}), 400

    report_file, owner_error = enforce_report_owner_or_404(filename, user_id)
    if owner_error:
        response, status_code = owner_error
        return response, status_code

    if not is_refly_configured():
        return jsonify({"error": "演示文稿服务未配置"}), 400

    clear_presentation_stopped(filename)
    execution_id = ""

    try:
        report_content = report_file.read_text(encoding="utf-8")
        report_title = report_content.strip().splitlines()[0].lstrip("#").strip() if report_content else ""
        upload_response = upload_refly_file(report_file)
        file_keys = extract_refly_file_keys(upload_response)
        run_response = run_refly_workflow(report_content, file_keys=file_keys)
        execution_id = (
            run_response.get("data", {}).get("executionId")
            or run_response.get("executionId")
        )
        if not execution_id:
            return jsonify({
                "error": "服务未返回 executionId",
                "refly_upload": upload_response,
                "refly_response": run_response
            }), 502

        owner = get_execution_owner_report(execution_id)
        if owner and owner != filename:
            if ENABLE_DEBUG_LOG:
                print(f"⚠️ 拦截跨报告 execution_id 复用: execution_id={execution_id}, owner={owner}, filename={filename}")
            return jsonify({
                "error": "生成任务归属冲突，请重试",
                "mismatch": True,
                "owner_report": owner,
                "execution_id": execution_id
            }), 409

        if is_presentation_execution_stopped(filename, execution_id):
            try:
                url = get_refly_abort_url(execution_id)
                headers = {"Authorization": f"Bearer {REFLY_API_KEY}"}
                requests.post(url, headers=headers, timeout=REFLY_TIMEOUT)
            except Exception:
                pass
            return jsonify({
                "processing": False,
                "execution_id": "",
                "stopped": True,
                "message": "演示文稿生成已停止"
            })

        record_presentation_execution(filename, execution_id)

        status_response = poll_refly_execution(execution_id)
        output_response = wait_for_refly_output_ready(execution_id)
        pdf_url = (
            extract_pdf_url_from_output(output_response)
            or build_pdf_url_from_result_info_file(output_response)
            or build_pdf_url_from_result_info(output_response)
        )
        if not pdf_url:
            if is_presentation_execution_stopped(filename, execution_id):
                return jsonify({
                    "processing": False,
                    "execution_id": "",
                    "stopped": True,
                    "message": "演示文稿生成已停止"
                })
            record_presentation_execution(filename, execution_id)
            return jsonify({
                "message": "演示文稿仍在生成中，请稍后重试",
                "execution_id": execution_id,
                "refly_status": status_response,
                "refly_response": output_response,
                "processing": True
            })

        if is_presentation_execution_stopped(filename, execution_id):
            return jsonify({
                "processing": False,
                "execution_id": "",
                "stopped": True,
                "message": "演示文稿生成已停止"
            })

        presentation_url = pdf_url
        download_info = None
        presentation_local_url = None
        try:
            candidate = select_best_refly_candidate(output_response, presentation_url)
            if candidate:
                download_info = download_presentation_file(candidate["url"], candidate.get("name", ""))
        except Exception as download_exc:
            if ENABLE_DEBUG_LOG:
                print(f"⚠️ 下载演示文稿失败: {download_exc}")

        if download_info or pdf_url:
            record_presentation_file(filename, download_info, pdf_url=pdf_url)
            if download_info:
                presentation_local_url = f"/api/reports/{quote(filename)}/presentation"

        response_payload = {
            "message": "已提交生成任务",
            "report_filename": filename,
            "report_title": report_title,
            "execution_id": execution_id,
            "refly_upload": upload_response,
            "refly_status": status_response,
            "refly_response": output_response,
            "presentation_url": presentation_url
        }
        if pdf_url:
            response_payload["pdf_url"] = pdf_url
        if download_info:
            response_payload.update({
                "download_url": download_info.get("url"),
                "download_path": download_info.get("path"),
                "download_filename": download_info.get("filename"),
                "download_size": download_info.get("size"),
                "presentation_local_url": presentation_local_url
            })

        return jsonify(response_payload)
    except requests.HTTPError as exc:
        if ENABLE_DEBUG_LOG:
            try:
                detail = exc.response.text
            except Exception:
                detail = str(exc)
            print(f"⚠️ 演示文稿服务 HTTP 错误: {detail}")
        return jsonify({"error": "演示文稿服务请求失败"}), 502
    except requests.exceptions.Timeout:
        stopped = is_presentation_execution_stopped(filename, execution_id)
        if execution_id and not stopped:
            record_presentation_execution(filename, execution_id)
        return jsonify({
            "processing": not stopped,
            "execution_id": "" if stopped else execution_id,
            "stopped": stopped,
            "message": "演示文稿生成已停止" if stopped else "演示文稿仍在生成中，请稍后重试"
        }), 202
    except requests.exceptions.SSLError:
        stopped = is_presentation_execution_stopped(filename, execution_id)
        if execution_id and not stopped:
            record_presentation_execution(filename, execution_id)
        return jsonify({
            "processing": not stopped,
            "execution_id": "" if stopped else execution_id,
            "stopped": stopped,
            "message": "演示文稿生成已停止" if stopped else "演示文稿仍在生成中，请稍后重试"
        }), 202
    except requests.RequestException as exc:
        if ENABLE_DEBUG_LOG:
            print(f"⚠️ 演示文稿服务请求异常: {exc}")
        stopped = is_presentation_execution_stopped(filename, execution_id)
        if execution_id and not stopped:
            record_presentation_execution(filename, execution_id)
        return jsonify({
            "processing": not stopped,
            "execution_id": "" if stopped else execution_id,
            "stopped": stopped,
            "message": "演示文稿生成已停止" if stopped else "演示文稿仍在生成中，请稍后重试"
        }), 202
    except Exception as exc:
        return jsonify({"error": f"提交生成任务失败: {str(exc)}"}), 500


@app.route('/api/reports/<path:filename>/refly/status', methods=['GET'])
def check_refly_status(filename):
    user_id = get_current_user_id_or_none()
    if not user_id:
        return jsonify({"error": "请先登录"}), 401

    filename = normalize_presentation_report_filename(filename)
    if not filename:
        return jsonify({"error": "filename 缺失"}), 400

    _report_file, owner_error = enforce_report_owner_or_404(filename, user_id)
    if owner_error:
        response, status_code = owner_error
        return response, status_code

    execution_id = request.args.get("execution_id", "").strip()
    if not execution_id:
        return jsonify({"error": "execution_id 缺失"}), 400

    current_record = get_presentation_record(filename) or {}
    stopped_at = current_record.get("stopped_at")
    stopped_execution_id = str(current_record.get("stopped_execution_id") or "").strip()
    if stopped_at and (not stopped_execution_id or stopped_execution_id == execution_id):
        return jsonify({
            "processing": False,
            "execution_id": "",
            "stopped": True,
            "message": "演示文稿生成已停止"
        })

    owner = get_execution_owner_report(execution_id)
    if owner and owner != filename:
        if ENABLE_DEBUG_LOG:
            print(f"⚠️ 拦截跨报告状态查询: execution_id={execution_id}, owner={owner}, filename={filename}")
        return jsonify({
            "processing": False,
            "execution_id": execution_id,
            "mismatch": True,
            "owner_report": owner,
            "message": "execution_id 与报告不匹配"
        }), 409
    try:
        status_response = fetch_refly_status_once(execution_id)
        output_response = fetch_refly_output(execution_id)
        pdf_url = (
            extract_pdf_url_from_output(output_response)
            or build_pdf_url_from_result_info_file(output_response)
            or build_pdf_url_from_result_info(output_response)
        )
        if not pdf_url:
            latest_record = get_presentation_record(filename) or {}
            latest_stopped_at = latest_record.get("stopped_at")
            latest_stopped_execution_id = str(latest_record.get("stopped_execution_id") or "").strip()
            if latest_stopped_at and (not latest_stopped_execution_id or latest_stopped_execution_id == execution_id):
                return jsonify({
                    "processing": False,
                    "execution_id": "",
                    "stopped": True,
                    "message": "演示文稿生成已停止"
                })
            record_presentation_execution(filename, execution_id)
            return jsonify({
                "processing": True,
                "execution_id": execution_id,
                "refly_status": status_response,
                "refly_response": output_response
            })
        record_presentation_file(filename, None, pdf_url=pdf_url)
        return jsonify({
            "execution_id": execution_id,
            "pdf_url": pdf_url
        })
    except requests.exceptions.Timeout:
        stopped = is_presentation_execution_stopped(filename, execution_id)
        return jsonify({
            "processing": not stopped,
            "execution_id": "" if stopped else execution_id,
            "stopped": stopped,
            "message": "演示文稿生成已停止" if stopped else "演示文稿仍在生成中，请稍后重试"
        })
    except requests.exceptions.SSLError:
        stopped = is_presentation_execution_stopped(filename, execution_id)
        return jsonify({
            "processing": not stopped,
            "execution_id": "" if stopped else execution_id,
            "stopped": stopped,
            "message": "演示文稿生成已停止" if stopped else "演示文稿仍在生成中，请稍后重试"
        })
    except requests.RequestException as exc:
        if ENABLE_DEBUG_LOG:
            print(f"⚠️ 演示文稿服务请求异常: {exc}")
        stopped = is_presentation_execution_stopped(filename, execution_id)
        return jsonify({
            "processing": not stopped,
            "execution_id": "" if stopped else execution_id,
            "stopped": stopped,
            "message": "演示文稿生成已停止" if stopped else "演示文稿仍在生成中，请稍后重试"
        })
    except Exception as exc:
        return jsonify({"error": f"查询生成状态失败: {str(exc)}"}), 500


@app.route('/api/reports/<path:filename>/presentation/abort', methods=['POST'])
def abort_report_presentation(filename):
    user_id = get_current_user_id_or_none()
    if not user_id:
        return jsonify({"error": "请先登录"}), 401

    filename = normalize_presentation_report_filename(filename)
    if not filename:
        return jsonify({"error": "filename 缺失"}), 400

    _report_file, owner_error = enforce_report_owner_or_404(filename, user_id)
    if owner_error:
        response, status_code = owner_error
        return response, status_code

    execution_id = request.args.get("execution_id", "").strip()
    if not execution_id:
        record = get_presentation_record(filename) or {}
        execution_id = str(record.get("execution_id") or "").strip()
    if not execution_id:
        mark_presentation_stopped(filename)
        return jsonify({"success": True, "execution_id": ""})
    try:
        url = get_refly_abort_url(execution_id)
        headers = {"Authorization": f"Bearer {REFLY_API_KEY}"}
        response = requests.post(url, headers=headers, timeout=REFLY_TIMEOUT)
        response.raise_for_status()
        mark_presentation_stopped(filename, execution_id=execution_id)
        return jsonify({"success": True, "execution_id": execution_id})
    except requests.RequestException as exc:
        if ENABLE_DEBUG_LOG:
            print(f"⚠️ 演示文稿中止失败: {exc}")
        mark_presentation_stopped(filename, execution_id=execution_id)
        return jsonify({"success": True, "execution_id": execution_id, "warning": "中止请求失败，已本地标记停止"})


@app.route('/api/reports/<path:filename>', methods=['DELETE'])
def delete_report(filename):
    """删除报告（仅标记为已删除，保留文件存档）"""
    user_id = get_current_user_id_or_none()
    if not user_id:
        return jsonify({"error": "请先登录"}), 401

    report_file, owner_error = enforce_report_owner_or_404(filename, user_id)
    if owner_error:
        response, status_code = owner_error
        return response, status_code

    try:
        # 只标记为已删除，不真正删除文件
        mark_report_as_deleted(filename)
        return jsonify({
            "message": "报告已从列表中移除（文件已存档）",
            "name": filename
        })
    except Exception as e:
        return jsonify({"error": f"标记删除失败: {str(e)}"}), 500


@app.route('/api/reports/batch-delete', methods=['POST'])
def batch_delete_reports():
    """批量删除报告（软删除）。"""
    user_id = get_current_user_id_or_none()
    if not user_id:
        return jsonify({"error": "请先登录"}), 401

    data = request.get_json(silent=True) or {}
    report_names = unique_non_empty_strings(data.get("report_names", []))

    if not report_names:
        return jsonify({"error": "report_names 不能为空"}), 400

    deleted_reports = []
    skipped_reports = []
    missing_reports = []

    for report_name in report_names:
        report_file, owner_error = enforce_report_owner_or_404(report_name, user_id)
        if owner_error:
            if report_file is None and not (REPORTS_DIR / report_name).exists():
                missing_reports.append(report_name)
            else:
                skipped_reports.append({"name": report_name, "reason": "无权限或报告不存在"})
            continue

        try:
            mark_report_as_deleted(report_name)
            deleted_reports.append(report_name)
        except Exception as exc:
            skipped_reports.append({"name": report_name, "reason": f"标记删除失败: {str(exc)}"})

    return jsonify({
        "success": True,
        "requested": len(report_names),
        "deleted_reports": deleted_reports,
        "skipped_reports": skipped_reports,
        "missing_reports": missing_reports
    })


# ============ 状态 API ============

@app.route('/api/status', methods=['GET'])
def get_status():
    """获取服务状态"""
    wechat_enabled = bool(WECHAT_LOGIN_ENABLED and WECHAT_APP_ID and WECHAT_APP_SECRET)
    sms_enabled = bool(SMS_PROVIDER in {"mock", "jdcloud"})
    if not get_current_user():
        return jsonify({
            "status": "running",
            "authenticated": False,
            "wechat_login_enabled": wechat_enabled,
            "sms_login_enabled": sms_enabled,
            "sms_provider": SMS_PROVIDER,
            "sms_code_length": SMS_CODE_LENGTH,
            "sms_cooldown_seconds": SMS_SEND_COOLDOWN_SECONDS,
            "report_profile_default": REPORT_V3_PROFILE,
            "report_profile_options": ["balanced", "quality"],
        })

    question_available = resolve_ai_client(call_type="question") is not None
    report_available = resolve_ai_client(call_type="report") is not None
    ai_available = question_available or report_available
    mode_names = ["quick", "standard", "deep"]
    mode_configs_effective = {
        mode: get_interview_mode_display_config(mode)
        for mode in mode_names
    }
    return jsonify({
        "status": "running",
        "authenticated": True,
        "wechat_login_enabled": wechat_enabled,
        "sms_login_enabled": sms_enabled,
        "sms_provider": SMS_PROVIDER,
        "sms_code_length": SMS_CODE_LENGTH,
        "sms_cooldown_seconds": SMS_SEND_COOLDOWN_SECONDS,
        "ai_available": ai_available,
        "question_ai_available": question_ai_client is not None,
        "report_ai_available": report_ai_client is not None,
        "report_profile_default": REPORT_V3_PROFILE,
        "report_profile_options": ["balanced", "quality"],
        "interview_depth_v2": {
            "enabled": True,
            "modes": mode_names,
            "deep_mode_skip_followup_confirm": DEEP_MODE_SKIP_FOLLOWUP_CONFIRM,
            "mode_configs": mode_configs_effective,
        }
    })


@app.route('/api/status/web-search', methods=['GET'])
def get_web_search_status():
    """获取 Web Search API 调用状态（用于前端呼吸灯效果）"""
    return jsonify({
        "active": web_search_active
    })


@app.route('/api/status/thinking/<session_id>', methods=['GET'])
def get_thinking_status(session_id):
    """获取 AI 思考进度状态（用于前端分阶段进度展示）"""
    user_id = get_current_user_id_or_none()
    if not user_id:
        return jsonify({"error": "请先登录"}), 401

    loaded = load_session_for_user(session_id, user_id)
    if len(loaded) == 3:
        return jsonify({"active": False})

    with thinking_status_lock:
        status = thinking_status.get(session_id)

    if status:
        return jsonify({
            "active": True,
            "stage": status["stage"],
            "stage_index": status["stage_index"],
            "total_stages": status["total_stages"],
            "message": status["message"],
        })
    else:
        return jsonify({"active": False})


@app.route('/api/status/report-generation/<session_id>', methods=['GET'])
def get_report_generation_status(session_id):
    """获取报告生成进度状态"""
    user_id = get_current_user_id_or_none()
    if not user_id:
        return jsonify({"error": "请先登录"}), 401

    loaded = load_session_for_user(session_id, user_id)
    if len(loaded) == 3:
        return jsonify({"active": False})

    status = get_report_generation_record(session_id)
    if status and not bool(status.get("active")) and is_report_generation_worker_alive(session_id):
        state = str(status.get("state") or "").strip()
        if state not in {"completed", "failed", "cancelled"}:
            update_report_generation_status(session_id, "queued", message="报告任务正在处理中...")
            status = get_report_generation_record(session_id)
    if status and bool(status.get("active")):
        queue_snapshot = get_report_generation_worker_snapshot(include_positions=True)
        sync_report_generation_queue_metadata(session_id, snapshot=queue_snapshot)
        status = get_report_generation_record(session_id) or status

    if status:
        return jsonify(build_report_generation_payload(status))

    return jsonify({"active": False, "processing": False})


@app.route('/api/metrics', methods=['GET'])
def get_metrics():
    """获取 API 性能指标和统计信息"""
    last_n = request.args.get('last_n', type=int)
    stats = metrics_collector.get_statistics(last_n=last_n)
    stats["list_endpoints"] = get_list_metrics_snapshot()
    stats["report_generation_queue"] = get_report_generation_worker_snapshot(include_positions=False)
    with list_overload_stats_lock:
        stats["list_overload"] = {
            "sessions_list_rejected": int(list_overload_stats.get("sessions_list", {}).get("rejected", 0) or 0),
            "reports_list_rejected": int(list_overload_stats.get("reports_list", {}).get("rejected", 0) or 0),
        }
    return jsonify(stats)


@app.route('/api/metrics/reset', methods=['POST'])
def reset_metrics():
    """重置性能指标（清空历史数据）"""
    try:
        metrics_collector.reset()
        reset_list_metrics()
        with list_overload_stats_lock:
            for endpoint_key in list_overload_stats.keys():
                list_overload_stats[endpoint_key]["rejected"] = 0
        with report_generation_queue_stats_lock:
            for key in report_generation_queue_stats.keys():
                report_generation_queue_stats[key] = 0
        return jsonify({"success": True, "message": "性能指标已重置"})
    except Exception as e:
        return jsonify({"error": f"重置失败: {e}"}), 500


@app.route('/api/summaries', methods=['GET'])
def get_summaries_info():
    """获取智能摘要缓存信息"""
    try:
        cache_files = list(SUMMARIES_DIR.glob("*.txt"))
        total_size = sum(f.stat().st_size for f in cache_files)

        return jsonify({
            "enabled": ENABLE_SMART_SUMMARY,
            "cache_enabled": SUMMARY_CACHE_ENABLED,
            "threshold": SMART_SUMMARY_THRESHOLD,
            "target_length": SMART_SUMMARY_TARGET,
            "cached_count": len(cache_files),
            "cache_size_bytes": total_size,
            "cache_size_kb": round(total_size / 1024, 2),
        })
    except Exception as e:
        return jsonify({"error": f"获取摘要信息失败: {e}"}), 500


@app.route('/api/summaries/clear', methods=['POST'])
def clear_summaries_cache():
    """清空智能摘要缓存"""
    try:
        cache_files = list(SUMMARIES_DIR.glob("*.txt"))
        deleted_count = 0
        for f in cache_files:
            try:
                f.unlink()
                deleted_count += 1
            except Exception:
                pass

        return jsonify({
            "success": True,
            "message": f"已清空 {deleted_count} 个摘要缓存",
            "deleted_count": deleted_count
        })
    except Exception as e:
        return jsonify({"error": f"清空缓存失败: {e}"}), 500


def is_generation_relevant_access_log(path: str, method: str = "GET") -> bool:
    """访问日志白名单：仅保留问题生成/回答提交/报告生成相关关键接口。"""
    normalized = str(path or "").strip()
    verb = str(method or "GET").upper()
    if not normalized:
        return False

    if verb == "POST" and normalized == "/api/sessions":
        return True

    return bool(re.match(
        r"^/api/sessions/[^/]+/(next-question|submit-answer|generate-report|undo-answer|skip-follow-up|complete-dimension|restart-interview|documents)$",
        normalized,
    ))


def should_suppress_access_log(path: str, method: str = "GET", code='-') -> bool:
    normalized = str(path or "").strip()
    if not normalized:
        return False

    # 错误请求始终保留，便于排障。
    try:
        status_code = int(str(code))
    except Exception:
        status_code = 0
    if status_code >= 400:
        return False

    # 聚焦模式：仅保留问题/报告生成关键路径访问日志，其余静默。
    if FOCUS_GENERATION_ACCESS_LOG:
        return not is_generation_relevant_access_log(normalized, method)

    if not SUPPRESS_STATUS_POLL_ACCESS_LOG:
        return False

    suppress_prefixes = (
        "/api/status/thinking/",
        "/api/status/web-search",
        "/api/status/report-generation/",
    )
    return any(normalized.startswith(prefix) for prefix in suppress_prefixes)


class SelectiveAccessLogRequestHandler(WSGIRequestHandler):
    """按路径过滤开发服务器访问日志，降低高频轮询噪音。"""

    def log_request(self, code='-', size='-'):
        try:
            parsed_path = urlparse(str(getattr(self, "path", "") or "")).path
            method = str(getattr(self, "command", "GET") or "GET").upper()
            if should_suppress_access_log(parsed_path, method=method, code=code):
                return
        except Exception:
            pass
        return super().log_request(code, size)


if __name__ == '__main__':
    print("=" * 60)
    print("Deep Vision Web Server - AI 驱动版本")
    print("=" * 60)
    print(f"Sessions: {SESSIONS_DIR}")
    print(f"Reports: {REPORTS_DIR}")
    print(f"AI 状态: {'已启用' if claude_client else '未启用'}")
    if claude_client:
        question_endpoint = QUESTION_BASE_URL or "(Anthropic 官方默认地址)"
        report_endpoint = REPORT_BASE_URL or "(Anthropic 官方默认地址)"
        summary_endpoint = SUMMARY_BASE_URL or "(Anthropic 官方默认地址)"
        search_decision_endpoint = SEARCH_DECISION_BASE_URL or "(Anthropic 官方默认地址)"
        print(f"问题模型: {QUESTION_MODEL_NAME}")
        print(f"问题网关: {'可用' if question_ai_client else '不可用'} @ {question_endpoint}")
        print(f"报告模型: {REPORT_MODEL_NAME}")
        print(f"报告网关: {'可用' if report_ai_client else '不可用'} @ {report_endpoint}")
        print(f"摘要模型: {SUMMARY_MODEL_NAME}")
        print(f"摘要网关: {'可用' if summary_ai_client else '不可用'} @ {summary_endpoint}")
        print(f"搜索决策模型: {SEARCH_DECISION_MODEL_NAME}")
        print(f"搜索决策网关: {'可用' if search_decision_ai_client else '不可用'} @ {search_decision_endpoint}")
        print(f"搜索决策缓存: TTL={SEARCH_DECISION_CACHE_TTL_SECONDS}s, MAX={SEARCH_DECISION_CACHE_MAX_ENTRIES}")
        print(
            "问题策略: "
            f"fast={'on' if QUESTION_FAST_PATH_ENABLED else 'off'}"
            f"(timeout={QUESTION_FAST_TIMEOUT}s,tokens={QUESTION_FAST_MAX_TOKENS},"
            f"prompt<={QUESTION_FAST_LIGHT_PROMPT_MAX_CHARS},adaptive={'on' if QUESTION_FAST_ADAPTIVE_ENABLED else 'off'}), "
            f"hedge={'on' if QUESTION_HEDGED_ENABLED else 'off'}"
            f"(delay={QUESTION_HEDGED_DELAY_SECONDS}s,lane={QUESTION_HEDGED_SECONDARY_LANE})"
        )
        print(
            "V3 配置: "
            f"profile={REPORT_V3_PROFILE}, "
            f"draft_timeout={REPORT_DRAFT_API_TIMEOUT}s, "
            f"draft_tokens={REPORT_V3_DRAFT_MAX_TOKENS}, "
            f"facts_limit={REPORT_V3_DRAFT_FACTS_LIMIT}, "
            f"draft_retries={REPORT_V3_DRAFT_RETRY_COUNT}, "
            f"review_tokens={REPORT_V3_REVIEW_MAX_TOKENS}, "
            f"review_rounds={REPORT_V3_REVIEW_BASE_ROUNDS}+{REPORT_V3_QUALITY_FIX_ROUNDS}, "
            f"dual_stage={'on' if REPORT_V3_DUAL_STAGE_ENABLED else 'off'}"
            f"(draft_lane={REPORT_V3_DRAFT_PRIMARY_LANE},review_lane={REPORT_V3_REVIEW_PRIMARY_LANE}), "
            f"circuit={'on' if GATEWAY_CIRCUIT_BREAKER_ENABLED else 'off'}"
            f"(threshold={GATEWAY_CIRCUIT_FAIL_THRESHOLD},"
            f"cooldown={int(GATEWAY_CIRCUIT_COOLDOWN_SECONDS)}s,"
            f"window={int(GATEWAY_CIRCUIT_FAILURE_WINDOW_SECONDS)}s)"
        )

    # 搜索功能状态
    search_enabled = ENABLE_WEB_SEARCH and ZHIPU_API_KEY and ZHIPU_API_KEY != "your-zhipu-api-key-here"
    print(f"联网搜索: {'✅ 已启用 (智谱AI MCP)' if search_enabled else '⚠️  未启用'}")
    if not search_enabled and ENABLE_WEB_SEARCH:
        print("   提示: 配置 ZHIPU_API_KEY 以启用联网搜索功能")

    if not DEBUG_MODE:
        print("⚠️  生产环境建议使用 Gunicorn 启动：")
        print("   uv run --with gunicorn gunicorn -c web/gunicorn.conf.py web.wsgi:app")

    print()
    print(f"访问: http://localhost:{SERVER_PORT}")
    if FOCUS_GENERATION_ACCESS_LOG:
        print("访问日志过滤: 已启用（仅保留问题/报告生成关键接口）")
    elif SUPPRESS_STATUS_POLL_ACCESS_LOG:
        print("访问日志过滤: 已启用（状态轮询接口静默）")
    print("=" * 60)
    app.run(
        host=SERVER_HOST,
        port=SERVER_PORT,
        debug=DEBUG_MODE,
        request_handler=SelectiveAccessLogRequestHandler,
    )
