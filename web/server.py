#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["flask", "flask-cors", "anthropic", "requests"]
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
import json
import os
import secrets
import threading
import time as _time
import requests
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

# 加载配置文件
try:
    from config import (
        ANTHROPIC_API_KEY,
        ANTHROPIC_BASE_URL,
        MODEL_NAME,
        MAX_TOKENS_DEFAULT,
        MAX_TOKENS_QUESTION,
        MAX_TOKENS_REPORT,
        SERVER_HOST,
        SERVER_PORT,
        DEBUG_MODE,
        ENABLE_AI,
        ENABLE_DEBUG_LOG,
        ENABLE_WEB_SEARCH,
        ZHIPU_API_KEY,
        ZHIPU_SEARCH_ENGINE,
        SEARCH_MAX_RESULTS,
        SEARCH_TIMEOUT,
        VISION_MODEL_NAME,
        VISION_API_URL,
        ENABLE_VISION,
        MAX_IMAGE_SIZE_MB,
        SUPPORTED_IMAGE_TYPES,
    )
    print("✅ 配置文件加载成功")
except ImportError:
    print("⚠️  未找到 config.py，使用默认配置")
    print("   请复制 config.example.py 为 config.py 并填入实际配置")
    # 默认配置（从环境变量获取）
    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
    ANTHROPIC_BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "")
    ZHIPU_API_KEY = os.environ.get("ZHIPU_API_KEY", "")
    MODEL_NAME = os.environ.get("MODEL_NAME", "")
    MAX_TOKENS_DEFAULT = 2000
    MAX_TOKENS_QUESTION = 800
    MAX_TOKENS_REPORT = 4000
    SERVER_HOST = "0.0.0.0"
    SERVER_PORT = 5001
    DEBUG_MODE = True
    ENABLE_AI = True
    ENABLE_DEBUG_LOG = True
    ENABLE_WEB_SEARCH = False
    ZHIPU_API_KEY = ""
    ZHIPU_SEARCH_ENGINE = "search_pro"
    SEARCH_MAX_RESULTS = 3
    SEARCH_TIMEOUT = 10
    # Vision 默认配置
    VISION_MODEL_NAME = os.environ.get("VISION_MODEL_NAME", "")
    VISION_API_URL = os.environ.get("VISION_API_URL", "")
    ENABLE_VISION = True
    MAX_IMAGE_SIZE_MB = 10
    SUPPORTED_IMAGE_TYPES = ['.jpg', '.jpeg', '.png', '.gif', '.webp']

try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False
    print("警告: anthropic 库未安装，将无法使用 AI 功能")

app = Flask(__name__, static_folder='.')
CORS(app)

# 路径配置
SKILL_DIR = Path(__file__).parent.parent.resolve()
DATA_DIR = SKILL_DIR / "data"
SESSIONS_DIR = DATA_DIR / "sessions"
REPORTS_DIR = DATA_DIR / "reports"
CONVERTED_DIR = DATA_DIR / "converted"
TEMP_DIR = DATA_DIR / "temp"
METRICS_DIR = DATA_DIR / "metrics"
SUMMARIES_DIR = DATA_DIR / "summaries"  # 文档摘要缓存目录
DELETED_REPORTS_FILE = REPORTS_DIR / ".deleted_reports.json"
DELETED_DOCS_FILE = DATA_DIR / ".deleted_docs.json"  # 软删除记录文件

for d in [SESSIONS_DIR, REPORTS_DIR, CONVERTED_DIR, TEMP_DIR, METRICS_DIR, SUMMARIES_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ============ 场景配置加载器 ============
import sys
sys.path.insert(0, str(SKILL_DIR))
from scripts.scenario_loader import get_scenario_loader
scenario_loader = get_scenario_loader(DATA_DIR / "scenarios")

# Web Search 状态追踪（用于前端呼吸灯效果）
web_search_active = False

# ============ 思考进度状态追踪（方案B）============
thinking_status = {}           # { session_id: { stage, stage_index, total_stages, message } }
thinking_status_lock = threading.Lock()

THINKING_STAGES = {
    "analyzing": {"index": 0, "message": "正在分析您的回答..."},
    "searching": {"index": 1, "message": "正在检索相关资料..."},
    "generating": {"index": 2, "message": "正在生成下一个问题..."},
}

# ============ 预生成缓存（智能预生成）============
prefetch_cache = {}            # { session_id: { dimension: { question_data, created_at, valid } } }
prefetch_cache_lock = threading.Lock()
PREFETCH_TTL = 300             # 预生成缓存有效期（秒）


def safe_load_session(session_file: Path) -> dict:
    """安全加载会话文件，处理 JSON 解析错误"""
    try:
        return json.loads(session_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"⚠️ 会话文件损坏: {session_file}, 错误: {e}")
        return None
    except Exception as e:
        print(f"⚠️ 读取会话文件失败: {session_file}, 错误: {e}")
        return None


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

    # 当前维度第2题已回答（即将进入第3题），预生成下一维度首题
    if formal_count < 2:
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
        if cand_formal < 3:
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

            # 重新读取会话数据（可能已更新）
            session_file = SESSIONS_DIR / f"{session_id}.json"
            if not session_file.exists():
                return

            session_data = json.loads(session_file.read_text(encoding="utf-8"))
            next_dim_logs = [l for l in session_data.get("interview_log", [])
                           if l.get("dimension") == next_dimension]

            # 构建预生成的 prompt
            prompt, truncated_docs = build_interview_prompt(
                session_data, next_dimension, next_dim_logs
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

            session_file = SESSIONS_DIR / f"{session_id}.json"
            if not session_file.exists():
                return

            session_data = json.loads(session_file.read_text(encoding="utf-8"))

            # 获取第一个维度（动态场景支持）
            first_dim = get_dimension_order_for_session(session_data)[0] if get_dimension_order_for_session(session_data) else "customer_needs"

            # 首题不依赖任何历史记录
            prompt, truncated_docs = build_interview_prompt(
                session_data, first_dim, []
            )

            response = call_claude(
                prompt,
                max_tokens=MAX_TOKENS_QUESTION,
                call_type="prefetch_first",
                truncated_docs=truncated_docs
            )

            if response:
                result = parse_question_response(response, debug=False)
                if result:
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

    threading.Thread(target=do_prefetch, daemon=True).start()


# ============ 性能监控系统 ============

class MetricsCollector:
    """API 性能指标收集器"""

    def __init__(self, metrics_file: Path):
        self.metrics_file = metrics_file
        self._ensure_metrics_file()

    def _ensure_metrics_file(self):
        """确保指标文件存在"""
        if not self.metrics_file.exists():
            self.metrics_file.write_text(json.dumps({
                "calls": [],
                "summary": {
                    "total_calls": 0,
                    "total_timeouts": 0,
                    "total_truncations": 0,
                    "avg_response_time": 0,
                    "avg_prompt_length": 0
                }
            }, ensure_ascii=False, indent=2), encoding="utf-8")

    def record_api_call(self, call_type: str, prompt_length: int, response_time: float,
                       success: bool, timeout: bool = False, error_msg: str = None,
                       truncated_docs: list = None, max_tokens: int = None):
        """记录 API 调用指标"""
        try:
            # 读取现有数据
            data = json.loads(self.metrics_file.read_text(encoding="utf-8"))

            # 添加新记录
            call_record = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "type": call_type,  # "question" or "report"
                "prompt_length": prompt_length,
                "response_time_ms": round(response_time * 1000, 2),
                "max_tokens": max_tokens,
                "success": success,
                "timeout": timeout,
                "error": error_msg,
                "truncated_docs": truncated_docs or []
            }

            data["calls"].append(call_record)

            # 更新汇总统计
            summary = data["summary"]
            summary["total_calls"] = summary.get("total_calls", 0) + 1
            if timeout:
                summary["total_timeouts"] = summary.get("total_timeouts", 0) + 1
            if truncated_docs:
                summary["total_truncations"] = summary.get("total_truncations", 0) + len(truncated_docs)

            # 计算平均值
            all_calls = data["calls"]
            if all_calls:
                summary["avg_response_time"] = round(
                    sum(c["response_time_ms"] for c in all_calls) / len(all_calls), 2
                )
                summary["avg_prompt_length"] = round(
                    sum(c["prompt_length"] for c in all_calls) / len(all_calls), 2
                )

            # 保存（只保留最近 1000 条记录）
            if len(data["calls"]) > 1000:
                data["calls"] = data["calls"][-1000:]

            self.metrics_file.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )

        except Exception as e:
            print(f"⚠️  记录指标失败: {e}")

    def get_statistics(self, last_n: int = None) -> dict:
        """获取统计信息"""
        try:
            data = json.loads(self.metrics_file.read_text(encoding="utf-8"))
            calls = data["calls"]

            if last_n:
                calls = calls[-last_n:]

            if not calls:
                return {
                    "total_calls": 0,
                    "message": "暂无数据"
                }

            # 计算统计信息
            total_calls = len(calls)
            successful_calls = sum(1 for c in calls if c["success"])
            timeout_calls = sum(1 for c in calls if c.get("timeout", False))
            truncation_events = sum(len(c.get("truncated_docs", [])) for c in calls)

            response_times = [c["response_time_ms"] for c in calls if c["success"]]
            prompt_lengths = [c["prompt_length"] for c in calls]

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
            }

            # 生成优化建议
            stats["recommendations"] = self._generate_recommendations(stats)

            return stats

        except Exception as e:
            return {"error": f"获取统计信息失败: {e}"}

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

# Claude 客户端初始化
claude_client = None

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

# 检查配置
api_key_valid = is_valid_api_key(ANTHROPIC_API_KEY)
base_url_valid = ANTHROPIC_BASE_URL and ANTHROPIC_BASE_URL != "https://api.anthropic.com" or api_key_valid

if not api_key_valid:
    print("⚠️  ANTHROPIC_API_KEY 未配置或使用默认值")
    print("   请在 config.py 中填入有效的 API Key")
    ENABLE_AI = False

if not base_url_valid and not ANTHROPIC_BASE_URL:
    print("⚠️  ANTHROPIC_BASE_URL 未配置")
    print("   请在 config.py 中填入有效的 Base URL")

if ENABLE_AI and HAS_ANTHROPIC and api_key_valid:
    try:
        claude_client = anthropic.Anthropic(
            api_key=ANTHROPIC_API_KEY,
            base_url=ANTHROPIC_BASE_URL
        )
        print(f"✅ Claude 客户端已初始化")
        print(f"   模型: {MODEL_NAME}")
        print(f"   Base URL: {ANTHROPIC_BASE_URL}")

        # 测试 API 连接
        try:
            test_response = claude_client.messages.create(
                model=MODEL_NAME,
                max_tokens=5,
                messages=[{"role": "user", "content": "Hi"}]
            )
            print(f"✅ API 连接测试成功")
        except Exception as e:
            print(f"⚠️  API 连接测试失败: {e}")
            print("   请检查 API Key 和 Base URL 是否正确")
            claude_client = None
    except Exception as e:
        print(f"❌ Claude 客户端初始化失败: {e}")
        claude_client = None
    except Exception as e:
        print(f"❌ Claude 客户端初始化失败: {e}")
else:
    if not ENABLE_AI:
        print("ℹ️  AI 功能已禁用（ENABLE_AI=False）")
    elif not HAS_ANTHROPIC:
        print("❌ anthropic 库未安装")
    elif not ANTHROPIC_API_KEY:
        print("❌ 未配置 ANTHROPIC_API_KEY")


def get_utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def generate_session_id() -> str:
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    random_suffix = secrets.token_hex(4)
    return f"dv-{timestamp}-{random_suffix}"


def get_deleted_reports() -> set:
    """获取已删除报告的列表"""
    if not DELETED_REPORTS_FILE.exists():
        return set()
    try:
        data = json.loads(DELETED_REPORTS_FILE.read_text(encoding="utf-8"))
        return set(data.get("deleted", []))
    except Exception:
        return set()


def mark_report_as_deleted(filename: str):
    """标记报告为已删除（不真正删除文件）"""
    deleted = get_deleted_reports()
    deleted.add(filename)
    DELETED_REPORTS_FILE.write_text(
        json.dumps({"deleted": list(deleted)}, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


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

    try:
        # 设置搜索状态为活动
        web_search_active = True

        mcp_url = "https://open.bigmodel.cn/api/mcp/web_search_prime/mcp"

        if ENABLE_DEBUG_LOG:
            print(f"🔍 开始MCP搜索: {query}")

        # 创建MCP客户端
        client = MCPClient(ZHIPU_API_KEY, mcp_url)

        # 调用webSearchPrime工具（注意：工具名是驼峰命名）
        result = client.call_tool("webSearchPrime", {
            "search_query": query,
            "search_recency_filter": "noLimit",
            "content_size": "medium"
        })

        # 解析结果
        results = []

        # MCP返回的content是一个列表
        content_list = result.get("content", [])

        for item in content_list:
            if item.get("type") == "text":
                # 文本内容
                text = item.get("text", "")

                # 尝试解析JSON格式的搜索结果
                try:
                    import json as json_module

                    # 第一次解析：去掉外层引号和转义
                    if text.startswith('"') and text.endswith('"'):
                        text = json_module.loads(text)

                    # 第二次解析：获取实际的搜索结果数组
                    search_data = json_module.loads(text)

                    # 如果是列表形式的搜索结果
                    if isinstance(search_data, list):
                        for entry in search_data[:SEARCH_MAX_RESULTS]:
                            title = entry.get("title", "")
                            content = entry.get("content", "")
                            url = entry.get("link", entry.get("url", ""))

                            if title or content:  # 确保有实际内容
                                results.append({
                                    "type": "result",
                                    "title": title[:100] if title else "搜索结果",
                                    "content": content[:300],
                                    "url": url
                                })
                    # 如果是单个结果
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
                    # 如果解析失败，直接作为文本结果
                    results.append({
                        "type": "result",
                        "title": "搜索结果",
                        "content": text[:300],
                        "url": ""
                    })

        if ENABLE_DEBUG_LOG:
            print(f"✅ MCP搜索成功，找到 {len(results)} 条结果")

        # 搜索完成，重置状态
        web_search_active = False
        return results

    except requests.exceptions.Timeout:
        print(f"⏱️  搜索超时: {query}")
        web_search_active = False
        return []
    except Exception as e:
        print(f"❌ MCP搜索失败: {e}")
        if ENABLE_DEBUG_LOG:
            import traceback
            traceback.print_exc()
        web_search_active = False
        return []


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
    global claude_client

    if not ENABLE_WEB_SEARCH or not claude_client:
        return {"need_search": False, "reason": "搜索功能未启用", "search_query": ""}

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

    try:
        response = claude_client.messages.create(
            model=MODEL_NAME,
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}]
        )

        result_text = response.content[0].text.strip()

        # 尝试解析 JSON
        import json
        # 处理可能的 markdown 代码块
        if "```json" in result_text:
            result_text = result_text.split("```json")[1].split("```")[0].strip()
        elif "```" in result_text:
            result_text = result_text.split("```")[1].split("```")[0].strip()

        result = json.loads(result_text)

        if ENABLE_DEBUG_LOG:
            print(f"🤖 AI搜索决策: need_search={result.get('need_search')}, reason={result.get('reason')}")

        return {
            "need_search": result.get("need_search", False),
            "reason": result.get("reason", ""),
            "search_query": result.get("search_query", "")
        }

    except Exception as e:
        if ENABLE_DEBUG_LOG:
            print(f"⚠️  AI搜索决策失败: {e}")
        # 失败时返回不搜索，避免阻塞流程
        return {"need_search": False, "reason": f"决策失败: {e}", "search_query": ""}


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

    if scenario_config and "dimensions" in scenario_config:
        return {
            dim["id"]: {
                "name": dim.get("name", dim["id"]),
                "description": dim.get("description", ""),
                "key_aspects": dim.get("key_aspects", []),
                "weight": dim.get("weight"),
                "scoring_criteria": dim.get("scoring_criteria")
            }
            for dim in scenario_config["dimensions"]
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

    if scenario_config and "dimensions" in scenario_config:
        return [dim["id"] for dim in scenario_config["dimensions"]]

    # 向后兼容：返回默认顺序
    return list(DIMENSION_INFO.keys())


# ============ 滑动窗口上下文管理 ============

# 配置参数
CONTEXT_WINDOW_SIZE = 5  # 保留最近N条完整问答
SUMMARY_THRESHOLD = 8    # 超过此数量时触发摘要生成
MAX_DOC_LENGTH = 2000    # 单个文档最大长度（约650汉字，增加33%）
MAX_TOTAL_DOCS = 5000    # 所有文档总长度限制（约1600汉字，增加67%）
API_TIMEOUT = 90.0       # API 调用超时时间（秒），从60秒增加到90秒

# ============ 智能文档摘要配置（第三阶段优化） ============
ENABLE_SMART_SUMMARY = True       # 启用智能文档摘要（替代简单截断）
SMART_SUMMARY_THRESHOLD = 1500    # 触发智能摘要的文档长度阈值（字符）
SMART_SUMMARY_TARGET = 800        # 摘要目标长度（字符）
SUMMARY_CACHE_ENABLED = True      # 启用摘要缓存（避免重复生成）
MAX_TOKENS_SUMMARY = 500          # 摘要生成的最大token数


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

    # 如果未启用智能摘要或没有AI客户端，使用简单截断
    if not ENABLE_SMART_SUMMARY or not claude_client:
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

        response = claude_client.messages.create(
            model=MODEL_NAME,
            max_tokens=MAX_TOKENS_SUMMARY,
            timeout=60.0,  # 摘要生成用较短超时
            messages=[{"role": "user", "content": summary_prompt}]
        )

        response_time = time.time() - start_time
        summary = response.content[0].text.strip()

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


def generate_history_summary(session: dict, exclude_recent: int = 5) -> Optional[str]:
    """
    生成历史访谈记录的摘要

    Args:
        session: 会话数据
        exclude_recent: 排除最近N条记录（这些会保留完整内容）

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

    # 需要生成新摘要
    if not claude_client:
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


def update_context_summary(session: dict, session_file) -> None:
    """
    更新会话的上下文摘要（在提交回答后调用）

    只有当历史记录超过阈值时才生成摘要
    """
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

    if claude_client:
        summary_prompt = _build_summary_prompt(session.get("topic", ""), history_logs, session)
        try:
            summary_text = call_claude(summary_prompt, max_tokens=300, call_type="summary")
            if summary_text:
                session["context_summary"] = {
                    "text": summary_text,
                    "log_count": history_count,
                    "updated_at": get_utc_now()
                }
                # 保存更新
                session_file.write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")
                if ENABLE_DEBUG_LOG:
                    print(f"📝 已更新上下文摘要（覆盖 {history_count} 条历史记录）")
        except Exception as e:
            print(f"⚠️ 更新上下文摘要失败: {e}")
    else:
        # 无 AI 时使用简单摘要
        session["context_summary"] = {
            "text": _generate_simple_summary(history_logs, session),
            "log_count": history_count,
            "updated_at": get_utc_now()
        }
        session_file.write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")


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
        "follow_up_budget_per_dim": 2,
        "total_follow_up_budget": 8,
        "max_questions_per_formal": 1,  # 每个正式问题最多追问次数
        "estimated_questions": "12-16"
    },
    "standard": {
        "name": "标准模式",
        "formal_questions_per_dim": 3,
        "follow_up_budget_per_dim": 4,
        "total_follow_up_budget": 16,
        "max_questions_per_formal": 2,
        "estimated_questions": "20-28"
    },
    "deep": {
        "name": "深度模式",
        "formal_questions_per_dim": 4,
        "follow_up_budget_per_dim": 6,
        "total_follow_up_budget": 24,
        "max_questions_per_formal": 3,
        "estimated_questions": "28-40"
    }
}

# 默认模式
DEFAULT_INTERVIEW_MODE = "standard"

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


def get_interview_mode_config(session: dict) -> dict:
    """获取会话的访谈模式配置"""
    mode = session.get("interview_mode", DEFAULT_INTERVIEW_MODE)
    return INTERVIEW_MODES.get(mode, INTERVIEW_MODES[DEFAULT_INTERVIEW_MODE])


def calculate_dimension_coverage(session: dict, dimension: str) -> int:
    """计算维度覆盖度（只统计正式问题）"""
    formal_count = len([log for log in session.get("interview_log", [])
                       if log.get("dimension") == dimension and not log.get("is_follow_up", False)])
    mode_config = get_interview_mode_config(session)
    required_questions = mode_config.get("formal_questions_per_dim", 3)
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

    # 确定饱和度级别
    if saturation_score >= SATURATION_THRESHOLDS["high"]:
        level = "high"
    elif saturation_score >= SATURATION_THRESHOLDS["medium"]:
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
    fatigue = calculate_user_fatigue(session, dimension)
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
    if not claude_client:
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
        response = claude_client.messages.create(
            model=MODEL_NAME,
            max_tokens=10,
            timeout=15.0,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = response.content[0].text.strip()
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
    # 追问的回答不再追问（避免无限追问）
    if is_follow_up:
        return {"needs_follow_up": False, "suggest_ai_eval": False,
                "reason": None, "signals": []}

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

    # 判断结果
    if follow_up_score >= 0.4:
        # 明确需要追问
        reason = _build_follow_up_reason(signals)
        return {"needs_follow_up": True, "suggest_ai_eval": False,
                "reason": reason, "signals": signals}
    elif follow_up_score >= 0.15 and not sufficient_signals:
        # 边界情况，建议让AI评估
        reason = _build_follow_up_reason(signals)
        return {"needs_follow_up": False, "suggest_ai_eval": True,
                "reason": reason, "signals": signals}
    else:
        # 不需要追问
        return {"needs_follow_up": False, "suggest_ai_eval": False,
                "reason": None, "signals": signals}


def _build_follow_up_reason(signals: list) -> str:
    """根据检测到的信号构建追问原因"""
    reason_map = {
        "too_short": "回答过于简短，需要补充具体细节",
        "vague_expression": "回答包含模糊表述，需要明确具体要求",
        "generic_answer": "回答过于笼统，需要深入了解具体需求",
        "option_only": "仅选择了预设选项，需要了解具体场景和考量",
        "no_quantification": "缺少量化指标，需要明确具体数据要求",
        "single_selection": "只选择了单一选项，需要了解是否还有其他需求",
    }
    reasons = [reason_map.get(s, "") for s in signals if s in reason_map]
    return reasons[0] if reasons else "需要进一步了解详细需求"


def build_interview_prompt(session: dict, dimension: str, all_dim_logs: list,
                           session_id: str = None) -> tuple[str, list]:
    """构建访谈 prompt（使用滑动窗口 + 摘要压缩 + 智能追问）

    Args:
        session: 会话数据
        dimension: 当前维度
        all_dim_logs: 当前维度的所有访谈记录
        session_id: 会话ID（可选，用于更新思考进度状态）

    Returns:
        tuple[str, list]: (prompt字符串, 被截断的文档列表)
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
            # 获取或生成历史摘要
            history_summary = generate_history_summary(session, exclude_recent=CONTEXT_WINDOW_SIZE)
            if history_summary:
                context_parts.append(f"\n### 历史访谈摘要（共{len(interview_log) - CONTEXT_WINDOW_SIZE}条）：")
                context_parts.append(history_summary)
                context_parts.append("\n### 最近问答记录：")

            # 只保留最近的完整记录
            recent_logs = interview_log[-CONTEXT_WINDOW_SIZE:]
        else:
            recent_logs = interview_log

        # 添加完整的最近问答记录
        for log in recent_logs:
            follow_up_mark = " [追问]" if log.get("is_follow_up") else ""
            context_parts.append(f"- Q: {log['question']}{follow_up_mark}")
            context_parts.append(f"  A: {log['answer']}")
            dim_name = session_dim_info.get(log.get("dimension", ""), {}).get("name", "")
            if dim_name:
                context_parts.append(f"  (维度: {dim_name})")

    # 计算正式问题数量（排除追问）
    formal_questions_count = len([log for log in all_dim_logs if not log.get("is_follow_up", False)])

    # ========== 智能追问判断（综合预算+饱和度+疲劳度+规则评估） ==========
    last_log = None
    should_follow_up = False
    suggest_ai_eval = False
    follow_up_reason = ""
    eval_signals = []
    comprehensive_decision = None

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
            is_follow_up=last_is_follow_up
        )

        eval_signals = eval_result["signals"]

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
{follow_up_section}

## 输出格式（必须严格遵守）

你的回复必须是一个纯 JSON 对象，格式如下：

{{
    "question": "你的问题",
    "options": ["选项1", "选项2", "选项3", "选项4"],
    "multi_select": false,
    "is_follow_up": {'true' if should_follow_up else 'false'},
    "follow_up_reason": {json.dumps(follow_up_reason, ensure_ascii=False) if should_follow_up else 'null'},
    "conflict_detected": false,
    "conflict_description": null
}}

字段说明：
- question: 字符串，你要问的问题
- options: 字符串数组，3-4 个选项
- multi_select: 布尔值，true=可多选，false=单选
- is_follow_up: 布尔值，true=追问（针对上一回答深入），false=新问题
- follow_up_reason: 字符串或 null，追问时说明原因
- conflict_detected: 布尔值
- conflict_description: 字符串或 null

**关键提醒：**
- 不要使用 ```json 代码块标记
- 不要在 JSON 前后添加任何说明文字
- 确保 JSON 语法完全正确（所有字符串用双引号，布尔值用 true/false，空值用 null）
- 你的整个回复就是这个 JSON 对象，没有其他内容
- **重要**：is_follow_up 的值已由系统根据预算和饱和度预先决定，请严格按照上述模板设置"""

    return prompt, truncated_docs


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
- 报告末尾使用署名：*此报告由 Deep Vision 深瞳-智能访谈助手生成*

请生成完整的评估报告："""

    return prompt


def build_report_prompt(session: dict) -> str:
    """构建报告生成 prompt"""
    # 检查是否为评估类型报告
    report_type = session.get("scenario_config", {}).get("report", {}).get("type", "standard")
    if report_type == "assessment":
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

## 重要提醒
- 所有内容必须严格基于访谈记录，不得编造
- 使用 Markdown 格式，Mermaid 代码块使用 ```mermaid 标记
- **优先级矩阵必须同时包含：quadrantChart象限图 + Markdown表格**
- **flowchart、pie 等图表使用中文标签**，quadrantChart 因技术限制必须用英文
- 报告要专业、结构清晰、可操作
- **Mermaid 语法要求严格，请仔细检查每个图表的语法正确性**
- **flowchart 连接线带标签语法必须是 `A -->|标签| B`，禁止使用 `A --|标签|--> B`**
- 报告末尾使用署名：*此报告由 Deep Vision 深瞳-智能访谈助手生成*

请生成完整的报告："""

    return prompt


async def call_claude_async(prompt: str, max_tokens: int = None) -> Optional[str]:
    """异步调用 Claude API，带超时控制"""
    if not claude_client:
        return None

    if max_tokens is None:
        max_tokens = MAX_TOKENS_DEFAULT

    try:
        if ENABLE_DEBUG_LOG:
            print(f"🤖 异步调用 Claude API，max_tokens={max_tokens}，timeout={API_TIMEOUT}s")

        # 使用配置的超时时间
        message = claude_client.messages.create(
            model=MODEL_NAME,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
            timeout=API_TIMEOUT
        )

        response_text = message.content[0].text

        if ENABLE_DEBUG_LOG:
            print(f"✅ API 异步响应成功，长度: {len(response_text)} 字符")

        return response_text
    except Exception as e:
        error_msg = str(e)
        print(f"❌ Claude API 异步调用失败: {error_msg}")

        if "timeout" in error_msg.lower():
            print(f"   原因: API 调用超时（超过{API_TIMEOUT}秒）")
        elif "rate" in error_msg.lower():
            print(f"   原因: API 请求频率限制")
        elif "authentication" in error_msg.lower() or "api key" in error_msg.lower():
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
            error_msg = response.json().get("error", {}).get("message", response.text[:200])
            if ENABLE_DEBUG_LOG:
                print(f"❌ 视觉 API 调用失败: {error_msg}")
            return f"[图片: {filename}] (API 错误: {error_msg[:100]})"

    except requests.exceptions.Timeout:
        return f"[图片: {filename}] (API 超时)"
    except Exception as e:
        if ENABLE_DEBUG_LOG:
            print(f"❌ 图片描述生成失败: {e}")
        return f"[图片: {filename}] (处理失败: {str(e)[:100]})"


def call_claude(prompt: str, max_tokens: int = None, retry_on_timeout: bool = True,
                call_type: str = "unknown", truncated_docs: list = None) -> Optional[str]:
    """同步调用 Claude API，带超时控制和容错机制"""
    import time

    if not claude_client:
        return None

    if max_tokens is None:
        max_tokens = MAX_TOKENS_DEFAULT

    start_time = time.time()
    success = False
    timeout_occurred = False
    error_message = None
    response_text = None

    try:
        if ENABLE_DEBUG_LOG:
            print(f"🤖 调用 Claude API，max_tokens={max_tokens}，timeout={API_TIMEOUT}s")

        # 使用配置的超时时间
        message = claude_client.messages.create(
            model=MODEL_NAME,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
            timeout=API_TIMEOUT
        )

        response_text = message.content[0].text
        success = True

        if ENABLE_DEBUG_LOG:
            print(f"✅ API 响应成功，长度: {len(response_text)} 字符")

    except Exception as e:
        error_message = str(e)
        print(f"❌ Claude API 调用失败: {error_message}")

        # 详细的错误分类和容错处理
        if "timeout" in error_message.lower():
            timeout_occurred = True
            print(f"   原因: API 调用超时（超过{API_TIMEOUT}秒）")

            # 超时容错：如果允许重试，尝试减少 prompt 长度
            if retry_on_timeout and len(prompt) > 5000:
                print(f"   🔄 尝试容错重试：截断 prompt 后重试...")
                # 截断 prompt 到原来的 70%
                truncated_prompt = prompt[:int(len(prompt) * 0.7)]
                truncated_prompt += "\n\n[注意：由于内容过长，部分上下文已被截断，请基于已有信息进行回答]"

                # 递归重试（禁止再次重试）
                response_text = call_claude(
                    truncated_prompt, max_tokens,
                    retry_on_timeout=False,
                    call_type=call_type + "_retry",
                    truncated_docs=truncated_docs
                )

                if response_text:
                    success = True

        elif "rate" in error_message.lower():
            print(f"   原因: API 请求频率限制")
        elif "authentication" in error_message.lower() or "api key" in error_message.lower():
            print(f"   原因: API Key 认证失败")

    finally:
        # 记录指标
        response_time = time.time() - start_time
        metrics_collector.record_api_call(
            call_type=call_type,
            prompt_length=len(prompt),
            response_time=response_time,
            success=success,
            timeout=timeout_occurred,
            error_msg=error_message if not success else None,
            truncated_docs=truncated_docs,
            max_tokens=max_tokens
        )

    return response_text


# ============ 静态文件 ============

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')


@app.route('/<path:filename>')
def static_files(filename):
    return send_from_directory('.', filename)


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
            "keywords": s.get("keywords", []),
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
            "report_type": s.get("report", {}).get("type", "standard")
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
    if not claude_client:
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
  "keywords": ["关键词1", "关键词2"],
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
        response = claude_client.messages.create(
            model=MODEL_NAME,
            max_tokens=1500,
            timeout=30.0,
            messages=[{"role": "user", "content": prompt}]
        )

        raw_text = response.content[0].text.strip()

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
        generated["report"] = {"type": "standard"}

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

    scenario = {
        "name": name,
        "description": data.get("description", "").strip(),
        "icon": data.get("icon", "clipboard-list"),
        "keywords": data.get("keywords", []),
        "dimensions": dimensions,
        "report": data.get("report", {"type": "standard"}),
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

    # 优先使用 AI 识别，失败时回退到关键词匹配
    ai_result = None
    if claude_client:
        try:
            response = claude_client.messages.create(
                model=MODEL_NAME,
                max_tokens=200,
                timeout=10.0,
                messages=[{"role": "user", "content": prompt}]
            )
            raw = response.content[0].text.strip()
            # 提取 JSON（兼容模型返回 markdown 代码块）
            if "```" in raw:
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.strip()
            ai_result = json.loads(raw)
        except Exception as e:
            print(f"⚠️  AI 场景识别失败，回退到关键词匹配: {e}")

    if ai_result and ai_result.get("scenario_id") in [s["id"] for s in all_scenarios]:
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


# ============ 会话 API ============

@app.route('/api/sessions', methods=['GET'])
def list_sessions():
    """获取所有会话"""
    sessions = []
    for f in SESSIONS_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            sessions.append({
                "session_id": data.get("session_id"),
                "topic": data.get("topic"),
                "status": data.get("status"),
                "created_at": data.get("created_at"),
                "updated_at": data.get("updated_at"),
                "dimensions": data.get("dimensions", {}),
                "interview_count": len(data.get("interview_log", [])),
                "scenario_id": data.get("scenario_id"),
                "scenario_config": data.get("scenario_config")
            })
        except Exception as e:
            print(f"读取会话失败 {f}: {e}")

    sessions.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return jsonify(sessions)


@app.route('/api/sessions', methods=['POST'])
def create_session():
    """创建新会话"""
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
    if not scenario_config:
        scenario_config = scenario_loader.get_default_scenario()
        scenario_id = scenario_config.get("id", "product-requirement")

    # 根据场景配置创建动态维度
    dimensions = {}
    for dim in scenario_config.get("dimensions", []):
        dimensions[dim["id"]] = {
            "coverage": 0,
            "items": [],
            "score": None  # 用于评估型场景
        }

    session_id = generate_session_id()
    now = get_utc_now()

    session = {
        "session_id": session_id,
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

    session_file = SESSIONS_DIR / f"{session_id}.json"
    session_file.write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")

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
    session_file = SESSIONS_DIR / f"{session_id}.json"
    if not session_file.exists():
        return jsonify({"error": "会话不存在"}), 404

    session = safe_load_session(session_file)
    if session is None:
        return jsonify({"error": "会话数据损坏"}), 500

    # 数据迁移：兼容旧会话格式
    session = migrate_session_docs(session)
    return jsonify(session)


@app.route('/api/sessions/<session_id>', methods=['PUT'])
def update_session(session_id):
    """更新会话"""
    session_file = SESSIONS_DIR / f"{session_id}.json"
    if not session_file.exists():
        return jsonify({"error": "会话不存在"}), 404

    updates = request.get_json()
    session = safe_load_session(session_file)
    if session is None:
        return jsonify({"error": "会话数据损坏"}), 500

    # 定义允许更新的字段白名单
    UPDATABLE_FIELDS = {"description", "topic", "status"}

    for key, value in updates.items():
        if key != "session_id" and key in UPDATABLE_FIELDS:
            session[key] = value

    session["updated_at"] = get_utc_now()
    session_file.write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")

    return jsonify(session)


@app.route('/api/sessions/<session_id>', methods=['DELETE'])
def delete_session(session_id):
    """删除会话"""
    session_file = SESSIONS_DIR / f"{session_id}.json"
    if session_file.exists():
        session_file.unlink()

    # ========== 步骤7: 清理缓存和状态 ==========
    invalidate_prefetch(session_id)
    clear_thinking_status(session_id)

    return jsonify({"success": True})


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

@app.route('/api/sessions/<session_id>/next-question', methods=['POST'])
def get_next_question(session_id):
    """获取下一个问题（AI 生成）"""
    session_file = SESSIONS_DIR / f"{session_id}.json"
    if not session_file.exists():
        return jsonify({"error": "会话不存在"}), 404

    session = json.loads(session_file.read_text(encoding="utf-8"))
    data = request.get_json() or {}
    default_dim = get_dimension_order_for_session(session)[0] if get_dimension_order_for_session(session) else "customer_needs"
    dimension = data.get("dimension", default_dim)

    # ========== 步骤5: 检查预生成缓存 ==========
    prefetched = get_prefetch_result(session_id, dimension)
    if prefetched:
        if ENABLE_DEBUG_LOG:
            print(f"🎯 预生成缓存命中: session={session_id}, dimension={dimension}")

        # 先检查维度是否已完成（即使有缓存也要检查）
        dim_data = session.get("dimensions", {}).get(dimension, {})
        dim_coverage = dim_data.get("coverage", 0)
        user_completed = dim_data.get("user_completed", False)
        if dim_coverage >= 100 or user_completed:
            # 维度已完成，忽略缓存，返回完成状态
            all_dim_logs = [log for log in session.get("interview_log", []) if log.get("dimension") == dimension]
            formal_questions_count = len([log for log in all_dim_logs if not log.get("is_follow_up", False)])
            dim_follow_ups = len([log for log in all_dim_logs if log.get("is_follow_up", False)])
            return jsonify({
                "dimension": dimension,
                "completed": True,
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
                is_follow_up=last_log.get("is_follow_up", False)
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

        prefetched["prefetched"] = True
        return jsonify(prefetched)

    # 检查是否有 Claude API
    if not claude_client:
        return jsonify({
            "error": "AI 服务未启用",
            "detail": "请联系管理员配置 ANTHROPIC_API_KEY 环境变量"
        }), 503

    # 获取当前维度的所有记录
    all_dim_logs = [log for log in session.get("interview_log", []) if log.get("dimension") == dimension]

    # 计算正式问题数量（排除追问）
    formal_questions_count = len([log for log in all_dim_logs if not log.get("is_follow_up", False)])

    # 获取访谈模式配置
    mode_config = get_interview_mode_config(session)
    required_formal_questions = mode_config["formal_questions_per_dim"]

    # 获取当前维度状态
    dim_data = session.get("dimensions", {}).get(dimension, {})
    dim_coverage = dim_data.get("coverage", 0)
    user_completed = dim_data.get("user_completed", False)

    # 检查维度是否已完成：
    # 1. 正式问题达到配置数量
    # 2. 或者 coverage 已经 >= 100%（可能是用户手动完成）
    # 3. 或者用户标记了 user_completed
    if formal_questions_count >= required_formal_questions or dim_coverage >= 100 or user_completed:
        # 使用综合决策检查是否还需要追问
        # 创建一个虚拟的规则评估结果来触发综合检查
        comprehensive_check = should_follow_up_comprehensive(
            session=session,
            dimension=dimension,
            rule_based_result={"needs_follow_up": False, "signals": []}
        )

        # 如果预算已用完或饱和度足够高，直接完成维度
        budget_status = comprehensive_check.get("budget_status", {})
        saturation = comprehensive_check.get("saturation", {})

        should_complete = (
            not budget_status.get("can_follow_up", True) or
            saturation.get("level") == "high" or
            formal_questions_count >= required_formal_questions
        )

        if should_complete:
            # 计算维度完成的统计信息
            dim_follow_ups = len([log for log in all_dim_logs if log.get("is_follow_up", False)])
            return jsonify({
                "dimension": dimension,
                "completed": True,
                "stats": {
                    "formal_questions": formal_questions_count,
                    "follow_ups": dim_follow_ups,
                    "saturation": saturation.get("saturation_score", 0) if saturation else 0
                }
            })

    # 调用 Claude 生成问题
    # 判断是否会有搜索（用于设置正确的阶段数）
    has_search = should_search(session.get("topic", ""), dimension, session)

    try:
        # 阶段1: 分析回答
        update_thinking_status(session_id, "analyzing", has_search)

        prompt, truncated_docs = build_interview_prompt(session, dimension, all_dim_logs, session_id=session_id)

        # 日志：记录 prompt 长度（便于监控和调优）
        if ENABLE_DEBUG_LOG:
            ref_docs_count = len(session.get("reference_materials", session.get("reference_docs", []) + session.get("research_docs", [])))
            print(f"📊 访谈 Prompt 统计：总长度={len(prompt)}字符，参考资料={ref_docs_count}个")
            if truncated_docs:
                print(f"⚠️  文档截断：{len(truncated_docs)}个文档被截断")

        # 阶段3: 生成问题
        update_thinking_status(session_id, "generating", has_search)

        response = call_claude(
            prompt,
            max_tokens=MAX_TOKENS_QUESTION,
            call_type="question",
            truncated_docs=truncated_docs
        )

        if not response:
            # 清除思考状态
            clear_thinking_status(session_id)
            return jsonify({
                "error": "AI 响应失败",
                "detail": "未能从 AI 服务获取响应，请检查网络连接或稍后重试"
            }), 503

        # 使用抽取的解析函数解析 JSON 响应
        result = parse_question_response(response, debug=ENABLE_DEBUG_LOG)

        if result:
            result["dimension"] = dimension
            result["ai_generated"] = True

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
                        is_follow_up=last_log.get("is_follow_up", False)
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
            "is_follow_up": False
        }

    # 维度已完成
    return {
        "question": None,
        "dimension": dimension,
        "completed": True
    }


@app.route('/api/sessions/<session_id>/submit-answer', methods=['POST'])
def submit_answer(session_id):
    """提交回答"""
    session_file = SESSIONS_DIR / f"{session_id}.json"
    if not session_file.exists():
        return jsonify({"error": "会话不存在"}), 404

    session = json.loads(session_file.read_text(encoding="utf-8"))

    # 验证请求数据
    data = request.get_json()
    if not data:
        return jsonify({"error": "无效的请求数据"}), 400

    question = data.get("question")
    answer = data.get("answer")
    dimension = data.get("dimension")
    options = data.get("options", [])
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
    if not isinstance(is_follow_up, bool):
        return jsonify({"error": "is_follow_up必须是布尔值"}), 400

    # 使用增强版评估函数判断回答是否需要追问
    eval_result = evaluate_answer_depth(
        question=question,
        answer=answer,
        dimension=dimension,
        options=options,
        is_follow_up=is_follow_up
    )
    needs_follow_up = eval_result["needs_follow_up"]
    follow_up_signals = eval_result["signals"]

    if ENABLE_DEBUG_LOG and (needs_follow_up or eval_result["suggest_ai_eval"]):
        print(f"📝 回答评估: signals={follow_up_signals}, needs_follow_up={needs_follow_up}")

    # 添加到访谈记录
    log_entry = {
        "timestamp": get_utc_now(),
        "question": question,
        "answer": answer,
        "dimension": dimension,
        "options": options,
        "is_follow_up": is_follow_up,
        "needs_follow_up": needs_follow_up,
        "follow_up_signals": follow_up_signals  # 记录检测到的信号
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
    session_file.write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")

    # 异步更新上下文摘要（超过阈值时触发）
    # 注意：这里在后台线程中执行，不阻塞响应
    import threading
    def async_update_summary():
        try:
            update_context_summary(session, session_file)
        except Exception as e:
            print(f"⚠️ 异步更新摘要失败: {e}")
    threading.Thread(target=async_update_summary, daemon=True).start()

    return jsonify(session)


@app.route('/api/sessions/<session_id>/undo-answer', methods=['POST'])
def undo_answer(session_id):
    """撤销最后一个回答"""
    session_file = SESSIONS_DIR / f"{session_id}.json"
    if not session_file.exists():
        return jsonify({"error": "会话不存在"}), 404

    session = json.loads(session_file.read_text(encoding="utf-8"))

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
    session_file.write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")

    return jsonify(session)


@app.route('/api/sessions/<session_id>/skip-follow-up', methods=['POST'])
def skip_follow_up(session_id):
    """
    用户主动跳过当前问题的追问
    标记最后一个正式问题的回答为"不需要追问"
    """
    session_file = SESSIONS_DIR / f"{session_id}.json"
    if not session_file.exists():
        return jsonify({"error": "会话不存在"}), 404

    session = json.loads(session_file.read_text(encoding="utf-8"))
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
    session_file.write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")

    if ENABLE_DEBUG_LOG:
        print(f"⏭️ 用户跳过追问: dimension={dimension}")

    return jsonify({"success": True, "message": "已跳过追问"})


@app.route('/api/sessions/<session_id>/complete-dimension', methods=['POST'])
def complete_dimension(session_id):
    """
    用户主动完成当前维度
    将当前维度标记为已完成（覆盖度设为100%）
    """
    session_file = SESSIONS_DIR / f"{session_id}.json"
    if not session_file.exists():
        return jsonify({"error": "会话不存在"}), 404

    session = json.loads(session_file.read_text(encoding="utf-8"))
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

    session["updated_at"] = get_utc_now()
    session_file.write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")

    if ENABLE_DEBUG_LOG:
        print(f"⏭️ 用户完成维度: dimension={dimension}, coverage={current_coverage}%")

    session_dim_info = get_dimension_info_for_session(session)
    dim_name = session_dim_info.get(dimension, {}).get('name', dimension)
    return jsonify({"success": True, "message": f"{dim_name}维度已完成"})


# ============ 文档上传 API ============

@app.route('/api/sessions/<session_id>/documents', methods=['POST'])
def upload_document(session_id):
    """上传参考文档"""
    session_file = SESSIONS_DIR / f"{session_id}.json"
    if not session_file.exists():
        return jsonify({"error": "会话不存在"}), 404

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

    filename = file.filename
    filepath = TEMP_DIR / filename
    file.save(filepath)

    # 读取文件内容
    ext = Path(filename).suffix.lower()
    content = ""

    try:
        # 图片处理
        if ext in SUPPORTED_IMAGE_TYPES:
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
                        converted_file = CONVERTED_DIR / f"{Path(filename).stem}.md"
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
    session = json.loads(session_file.read_text(encoding="utf-8"))
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
    session_file.write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")

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

    session_file = SESSIONS_DIR / f"{session_id}.json"
    if not session_file.exists():
        return jsonify({"error": "会话不存在"}), 404

    session = json.loads(session_file.read_text(encoding="utf-8"))
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
    session_file.write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")

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
    session_file = SESSIONS_DIR / f"{session_id}.json"
    if not session_file.exists():
        return jsonify({"error": "会话不存在"}), 404

    session = json.loads(session_file.read_text(encoding="utf-8"))
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

                research_content += f"Q: {question}\n\n"
                research_content += f"A: {answer}\n\n"

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
    session_file.write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")

    return jsonify({
        "success": True,
        "message": "已保存当前访谈内容并重置访谈",
        "research_doc_name": doc_name
    })


# ============ 报告生成 API ============

@app.route('/api/sessions/<session_id>/generate-report', methods=['POST'])
def generate_report(session_id):
    """生成访谈报告（AI 生成）"""
    session_file = SESSIONS_DIR / f"{session_id}.json"
    if not session_file.exists():
        return jsonify({"error": "会话不存在"}), 404

    session = json.loads(session_file.read_text(encoding="utf-8"))

    # 检查是否有 Claude API
    if claude_client:
        prompt = build_report_prompt(session)

        # 日志：记录报告生成 prompt 统计
        if ENABLE_DEBUG_LOG:
            ref_docs_count = len(session.get("reference_materials", session.get("reference_docs", []) + session.get("research_docs", [])))
            interview_count = len(session.get("interview_log", []))
            print(f"📊 报告生成 Prompt 统计：总长度={len(prompt)}字符，参考资料={ref_docs_count}个，访谈记录={interview_count}条")

        report_content = call_claude(
            prompt,
            max_tokens=MAX_TOKENS_REPORT,
            call_type="report"
        )

        if report_content:
            # 追加完整的访谈记录附录（确保附录完整）
            appendix = generate_interview_appendix(session)
            report_content = report_content + appendix

            # 保存报告
            topic_slug = session.get("topic", "report").replace(" ", "-")[:30]
            date_str = datetime.now().strftime("%Y%m%d")
            filename = f"deep-vision-{date_str}-{topic_slug}.md"
            report_file = REPORTS_DIR / filename
            report_file.write_text(report_content, encoding="utf-8")

            # 更新会话状态
            session["status"] = "completed"
            session["updated_at"] = get_utc_now()
            session_file.write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")

            return jsonify({
                "success": True,
                "report_path": str(report_file),
                "report_name": filename,
                "ai_generated": True
            })

    # 回退到简单报告生成
    report_content = generate_simple_report(session)
    topic_slug = session.get("topic", "report").replace(" ", "-")[:30]
    date_str = datetime.now().strftime("%Y%m%d")
    filename = f"deep-vision-{date_str}-{topic_slug}.md"
    report_file = REPORTS_DIR / filename
    report_file.write_text(report_content, encoding="utf-8")

    session["status"] = "completed"
    session["updated_at"] = get_utc_now()
    session_file.write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")

    return jsonify({
        "success": True,
        "report_path": str(report_file),
        "report_name": filename,
        "ai_generated": False
    })


def generate_interview_appendix(session: dict) -> str:
    """生成完整的访谈记录附录"""
    interview_log = session.get("interview_log", [])
    if not interview_log:
        return ""

    appendix = "\n\n---\n\n## 附录：完整访谈记录\n\n"
    appendix += f"> 本次访谈共收集了 {len(interview_log)} 个问题的回答\n\n"

    appendix_dim_info = get_dimension_info_for_session(session)
    for i, log in enumerate(interview_log, 1):
        dim_name = appendix_dim_info.get(log.get('dimension', ''), {}).get('name', '未分类')
        appendix += f"### Q{i}: {log['question']}\n\n"
        appendix += f"**回答**: {log['answer']}\n\n"
        appendix += f"**维度**: {dim_name}\n\n"
        if log.get('timestamp'):
            appendix += f"*记录时间: {log['timestamp']}*\n\n"
        appendix += "---\n\n"

    return appendix


def generate_simple_report(session: dict) -> str:
    """生成简单报告（无 AI 时使用）"""
    topic = session.get("topic", "未命名项目")
    interview_log = session.get("interview_log", [])
    now = datetime.now()

    content = f"""# {topic} 访谈报告

**访谈日期**: {now.strftime('%Y-%m-%d')}
**报告编号**: deep-vision-{now.strftime('%Y%m%d')}

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
*此报告由 Deep Vision 深瞳-智能访谈助手生成*
"""

    return content


# ============ 报告 API ============

@app.route('/api/reports', methods=['GET'])
def list_reports():
    """获取所有报告（排除已删除的）"""
    deleted = get_deleted_reports()
    reports = []
    for f in REPORTS_DIR.glob("*.md"):
        # 跳过已标记为删除的报告
        if f.name in deleted:
            continue
        stat = f.stat()
        reports.append({
            "name": f.name,
            "path": str(f),
            "size": stat.st_size,
            "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat()
        })

    reports.sort(key=lambda x: x["created_at"], reverse=True)
    return jsonify(reports)


@app.route('/api/reports/<path:filename>', methods=['GET'])
def get_report(filename):
    """获取报告内容"""
    report_file = REPORTS_DIR / filename
    if not report_file.exists():
        return jsonify({"error": "报告不存在"}), 404

    content = report_file.read_text(encoding="utf-8")
    return jsonify({"name": filename, "content": content})


@app.route('/api/reports/<path:filename>', methods=['DELETE'])
def delete_report(filename):
    """删除报告（仅标记为已删除，保留文件存档）"""
    report_file = REPORTS_DIR / filename
    if not report_file.exists():
        return jsonify({"error": "报告不存在"}), 404

    try:
        # 只标记为已删除，不真正删除文件
        mark_report_as_deleted(filename)
        return jsonify({
            "message": "报告已从列表中移除（文件已存档）",
            "name": filename
        })
    except Exception as e:
        return jsonify({"error": f"标记删除失败: {str(e)}"}), 500


# ============ 状态 API ============

@app.route('/api/status', methods=['GET'])
def get_status():
    """获取服务状态"""
    return jsonify({
        "status": "running",
        "ai_available": claude_client is not None,
        "model": MODEL_NAME if claude_client else None,
        "sessions_dir": str(SESSIONS_DIR),
        "reports_dir": str(REPORTS_DIR)
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


@app.route('/api/metrics', methods=['GET'])
def get_metrics():
    """获取 API 性能指标和统计信息"""
    last_n = request.args.get('last_n', type=int)
    stats = metrics_collector.get_statistics(last_n=last_n)
    return jsonify(stats)


@app.route('/api/metrics/reset', methods=['POST'])
def reset_metrics():
    """重置性能指标（清空历史数据）"""
    try:
        metrics_collector.metrics_file.write_text(json.dumps({
            "calls": [],
            "summary": {
                "total_calls": 0,
                "total_timeouts": 0,
                "total_truncations": 0,
                "avg_response_time": 0,
                "avg_prompt_length": 0
            }
        }, ensure_ascii=False, indent=2), encoding="utf-8")
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
            "cache_directory": str(SUMMARIES_DIR)
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


if __name__ == '__main__':
    print("=" * 60)
    print("Deep Vision Web Server - AI 驱动版本")
    print("=" * 60)
    print(f"Sessions: {SESSIONS_DIR}")
    print(f"Reports: {REPORTS_DIR}")
    print(f"AI 状态: {'已启用' if claude_client else '未启用'}")
    if claude_client:
        print(f"模型: {MODEL_NAME}")

    # 搜索功能状态
    search_enabled = ENABLE_WEB_SEARCH and ZHIPU_API_KEY and ZHIPU_API_KEY != "your-zhipu-api-key-here"
    print(f"联网搜索: {'✅ 已启用 (智谱AI MCP)' if search_enabled else '⚠️  未启用'}")
    if not search_enabled and ENABLE_WEB_SEARCH:
        print("   提示: 配置 ZHIPU_API_KEY 以启用联网搜索功能")

    print()
    print(f"访问: http://localhost:{SERVER_PORT}")
    print("=" * 60)
    app.run(host=SERVER_HOST, port=SERVER_PORT, debug=DEBUG_MODE)
