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
- 生成专业调研报告
"""

import json
import os
import secrets
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
        SEARCH_TIMEOUT
    )
    print("✅ 配置文件加载成功")
except ImportError:
    print("⚠️  未找到 config.py，使用默认配置")
    print("   请复制 config.example.py 为 config.py 并填入实际配置")
    # 默认配置（从环境变量获取）
    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
    ANTHROPIC_BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
    MODEL_NAME = "claude-sonnet-4-20250514"
    MAX_TOKENS_DEFAULT = 2000
    MAX_TOKENS_QUESTION = 500
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
DELETED_REPORTS_FILE = REPORTS_DIR / ".deleted_reports.json"

for d in [SESSIONS_DIR, REPORTS_DIR, CONVERTED_DIR, TEMP_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# Web Search 状态追踪（用于前端呼吸灯效果）
web_search_active = False

# Claude 客户端初始化
claude_client = None

if ENABLE_AI and HAS_ANTHROPIC and ANTHROPIC_API_KEY:
    try:
        claude_client = anthropic.Anthropic(
            api_key=ANTHROPIC_API_KEY,
            base_url=ANTHROPIC_BASE_URL
        )
        print(f"✅ Claude 客户端已初始化")
        print(f"   模型: {MODEL_NAME}")
        print(f"   Base URL: {ANTHROPIC_BASE_URL}")
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
    """判断是否需要进行联网搜索"""
    if not ENABLE_WEB_SEARCH:
        return False

    # 技术关键词
    tech_keywords = [
        "技术", "系统", "平台", "框架", "工具", "软件", "应用",
        "AI", "人工智能", "机器学习", "深度学习", "大模型",
        "云", "SaaS", "PaaS", "微服务", "容器", "Docker", "K8s",
        "数据库", "中间件", "API", "集成", "部署"
    ]

    # 行业关键词
    industry_keywords = [
        "行业", "标准", "规范", "合规", "认证", "等保",
        "市场", "趋势", "最新", "现状", "发展"
    ]

    # 时间敏感关键词
    time_keywords = [
        "最新", "当前", "现在", "2024", "2025", "2026",
        "趋势", "未来", "发展"
    ]

    topic_lower = topic.lower()
    all_keywords = tech_keywords + industry_keywords + time_keywords

    # 如果主题包含关键词，可能需要搜索
    for keyword in all_keywords:
        if keyword in topic:
            return True

    # 技术约束维度更可能需要搜索
    if dimension == "tech_constraints":
        return True

    return False


def generate_search_query(topic: str, dimension: str, context: dict) -> str:
    """生成搜索查询"""
    dim_info = DIMENSION_INFO.get(dimension, {})
    dim_name = dim_info.get("name", dimension)

    # 构建搜索查询
    if dimension == "tech_constraints":
        return f"{topic} 技术选型 最佳实践 2026"
    elif dimension == "customer_needs":
        return f"{topic} 用户需求 行业痛点 2026"
    elif dimension == "business_process":
        return f"{topic} 业务流程 最佳实践"
    elif dimension == "project_constraints":
        return f"{topic} 项目实施 成本预算 周期"
    else:
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


def build_interview_prompt(session: dict, dimension: str, all_dim_logs: list) -> str:
    """构建访谈 prompt"""
    topic = session.get("topic", "未知项目")
    reference_docs = session.get("reference_docs", [])
    interview_log = session.get("interview_log", [])
    dim_info = DIMENSION_INFO.get(dimension, {})

    # 构建上下文
    context_parts = [f"当前调研主题：{topic}"]

    # 添加参考文档内容
    if reference_docs:
        context_parts.append("\n## 参考文档内容：")
        for doc in reference_docs:
            if doc.get("content"):
                context_parts.append(f"### {doc.get('name', '文档')}")
                context_parts.append(doc["content"][:2000])  # 限制长度

    # 联网搜索增强（如果需要）
    if should_search(topic, dimension, session):
        search_query = generate_search_query(topic, dimension, session)
        search_results = web_search(search_query)

        if search_results:
            context_parts.append("\n## 行业知识参考（联网搜索）：")
            for idx, result in enumerate(search_results[:2], 1):  # 只取前2个结果，避免过长
                if result["type"] == "intent":
                    context_parts.append(f"**{result['content'][:200]}**")  # 搜索意图
                else:
                    context_parts.append(f"{idx}. **{result.get('title', '参考信息')[:50]}**")
                    context_parts.append(f"   {result['content'][:200]}")  # 限制长度

    # 添加已有问答记录
    if interview_log:
        context_parts.append("\n## 已收集的信息：")
        for log in interview_log:
            follow_up_mark = " [追问]" if log.get("is_follow_up") else ""
            context_parts.append(f"- Q: {log['question']}{follow_up_mark}")
            context_parts.append(f"  A: {log['answer']}")
            if log.get("dimension"):
                context_parts.append(f"  (维度: {DIMENSION_INFO.get(log['dimension'], {}).get('name', log['dimension'])})")

    # 计算正式问题数量（排除追问）
    formal_questions_count = len([log for log in all_dim_logs if not log.get("is_follow_up", False)])

    # 判断是否需要对上一个回答进行追问
    last_log = None
    should_follow_up = False
    follow_up_reason = ""

    if all_dim_logs and not all_dim_logs[-1].get("is_follow_up", False):
        # 上一个是正式问题，判断回答是否清晰
        last_log = all_dim_logs[-1]
        last_answer = last_log.get("answer", "")
        last_question = last_log.get("question", "")

        # 简单判断规则：如果回答很短、很泛泛、或包含"看情况"、"不一定"等模糊词
        vague_indicators = ["看情况", "不一定", "可能", "或许", "大概", "差不多", "到时候", "再说", "还没想好", "不确定", "看具体", "根据情况"]
        is_short = len(last_answer) < 15  # 回答太短
        has_vague = any(indicator in last_answer for indicator in vague_indicators)
        is_generic = last_answer in ["好的", "是的", "可以", "没问题", "需要", "应该要"]

        if is_short or has_vague or is_generic:
            should_follow_up = True
            if is_short:
                follow_up_reason = "回答过于简短，需要补充细节"
            elif has_vague:
                follow_up_reason = "回答包含模糊表述，需要明确具体要求"
            else:
                follow_up_reason = "回答过于笼统，需要深入了解具体需求"

    # 如果上一个回答已经标记为需要追问，则继续追问
    elif all_dim_logs and all_dim_logs[-1].get("needs_follow_up", False):
        last_log = all_dim_logs[-1]
        should_follow_up = True
        follow_up_reason = "继续深入了解上一个问题"

    prompt = f"""你是一个专业的需求调研访谈师，正在进行"{topic}"的需求调研。

{chr(10).join(context_parts)}

## 当前任务

你现在需要针对「{dim_info.get('name', dimension)}」维度收集信息。
这个维度关注：{dim_info.get('description', '')}

该维度已收集了 {formal_questions_count} 个正式问题的回答，关键方面包括：{', '.join(dim_info.get('key_aspects', []))}

{'## 追问模式' if should_follow_up else '## 要求'}

{'上一个用户回答需要追问：' + follow_up_reason if should_follow_up else '''1. 生成 1 个针对性的问题，用于收集该维度的关键信息
2. 为这个问题提供 3-4 个具体的选项
3. 选项要基于：
   - 调研主题的行业特点
   - 参考文档中的信息（如有）
   - 联网搜索的行业知识（如有）
   - 已收集的上下文信息'''}

4. {'追问是对上一个问题的深入了解，' if should_follow_up else '''根据问题性质判断是单选还是多选：'''}
   {'- 追问问题要更具体、更深入，引导用户给出明确答案' if should_follow_up else '''- 单选场景：互斥选项（是/否）、优先级选择（最重要的）、唯一选择（首选方案）
   - 多选场景：可并存的功能需求、多个痛点、多种用户角色、多个系统集成'''}

5. 如果用户的回答与参考文档内容有冲突，要在问题中指出并请求澄清。

## 输出格式

请以 JSON 格式返回：
```json
{{
    "question": "你的问题",
    "options": ["选项1", "选项2", "选项3", "选项4"],
    "multi_select": false,
    "is_follow_up": {str(should_follow_up).lower()},
    "follow_up_reason": {json.dumps(follow_up_reason) if should_follow_up else "null"},
    "conflict_detected": false,
    "conflict_description": null
}}
```

字段说明：
- multi_select: 布尔值，true 表示可多选，false 表示单选
- is_follow_up: 布尔值，true 表示这是追问，false 表示是正式问题
- follow_up_reason: 如果是追问，说明追问的原因；否则为 null

**追问不计入 3 个正式问题的限制**。

**重要警告**：
- 你的回复必须是且只能是一个有效的 JSON 对象
- 禁止在 JSON 前后添加任何文字、解释或说明
- 禁止使用 markdown 代码块（不要使用 ```json）
- 第一个字符必须是 {{，最后一个字符必须是 }}
- 严格遵守 JSON 语法，所有字符串使用双引号
- 布尔值用 true/false，字符串用 null 表示空值"""

    return prompt


def build_report_prompt(session: dict) -> str:
    """构建报告生成 prompt"""
    topic = session.get("topic", "未知项目")
    interview_log = session.get("interview_log", [])
    dimensions = session.get("dimensions", {})
    reference_docs = session.get("reference_docs", [])

    # 按维度整理问答
    qa_by_dim = {}
    for dim_key in DIMENSION_INFO:
        qa_by_dim[dim_key] = [log for log in interview_log if log.get("dimension") == dim_key]

    prompt = f"""你是一个专业的需求分析师，需要基于以下访谈记录生成一份专业的需求调研报告。

## 调研主题
{topic}

## 参考文档
"""

    if reference_docs:
        for doc in reference_docs:
            prompt += f"- {doc.get('name', '文档')}\n"
    else:
        prompt += "无参考文档\n"

    prompt += "\n## 访谈记录\n"

    for dim_key, dim_info in DIMENSION_INFO.items():
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

请生成一份专业的需求调研报告，包含以下章节：

1. **调研概述** - 基本信息、调研背景
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

请在报告中包含以下类型的 Mermaid 图表：

### 1. 优先级矩阵（必须）
使用象限图展示需求优先级，**严格按照以下格式**：

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
    Requirement3: [0.6, 0.5]
```

**严格规则（必须遵守）：**
- title、x-axis、y-axis、quadrant 标签**必须用英文**
- 数据点名称**必须用英文或拼音**，不能用中文
- 数据点格式：`Name: [x, y]`，x和y范围0-1
- 不要在标签中使用括号、冒号等特殊符号

### 2. 业务流程图（推荐）
使用 flowchart 展示关键业务流程：

```mermaid
flowchart TD
    A[Start] --> B{Decision}
    B -->|Yes| C[Process1]
    B -->|No| D[Process2]
    C --> E[End]
    D --> E
```

**规则：节点标签建议用英文，中文可能导致渲染问题**

### 3. 需求分类饼图（可选）
```mermaid
pie title Requirements Distribution
    "Functional" : 45
    "Performance" : 25
    "Security" : 20
    "Usability" : 10
```

## 重要提醒
- 所有内容必须严格基于访谈记录，不得编造
- 使用 Markdown 格式，Mermaid 代码块使用 ```mermaid 标记
- **Mermaid 图表的标签和数据点名称必须用英文**，可在图表下方用中文说明
- 优先级矩阵中的坐标值请根据实际需求评估
- 报告要专业、结构清晰、可操作
- 报告末尾使用署名：*此报告由 Deep Vision 深瞳-智能需求调研助手生成*

请生成完整的报告："""

    return prompt


async def call_claude_async(prompt: str, max_tokens: int = None) -> Optional[str]:
    """异步调用 Claude API"""
    if not claude_client:
        return None

    if max_tokens is None:
        max_tokens = MAX_TOKENS_DEFAULT

    try:
        message = claude_client.messages.create(
            model=MODEL_NAME,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}]
        )
        return message.content[0].text
    except Exception as e:
        print(f"Claude API 调用失败: {e}")
        return None


def call_claude(prompt: str, max_tokens: int = None) -> Optional[str]:
    """同步调用 Claude API"""
    if not claude_client:
        return None

    if max_tokens is None:
        max_tokens = MAX_TOKENS_DEFAULT

    try:
        message = claude_client.messages.create(
            model=MODEL_NAME,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}]
        )
        return message.content[0].text
    except Exception as e:
        print(f"Claude API 调用失败: {e}")
        return None


# ============ 静态文件 ============

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')


@app.route('/<path:filename>')
def static_files(filename):
    return send_from_directory('.', filename)


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
                "interview_count": len(data.get("interview_log", []))
            })
        except Exception as e:
            print(f"读取会话失败 {f}: {e}")

    sessions.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return jsonify(sessions)


@app.route('/api/sessions', methods=['POST'])
def create_session():
    """创建新会话"""
    data = request.get_json()
    topic = data.get("topic", "未命名调研")

    session_id = generate_session_id()
    now = get_utc_now()

    session = {
        "session_id": session_id,
        "topic": topic,
        "created_at": now,
        "updated_at": now,
        "status": "in_progress",
        "scenario": None,
        "dimensions": {
            "customer_needs": {"coverage": 0, "items": []},
            "business_process": {"coverage": 0, "items": []},
            "tech_constraints": {"coverage": 0, "items": []},
            "project_constraints": {"coverage": 0, "items": []}
        },
        "reference_docs": [],
        "interview_log": [],
        "requirements": [],
        "summary": None
    }

    session_file = SESSIONS_DIR / f"{session_id}.json"
    session_file.write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")

    return jsonify(session)


@app.route('/api/sessions/<session_id>', methods=['GET'])
def get_session(session_id):
    """获取会话详情"""
    session_file = SESSIONS_DIR / f"{session_id}.json"
    if not session_file.exists():
        return jsonify({"error": "会话不存在"}), 404

    session = json.loads(session_file.read_text(encoding="utf-8"))
    return jsonify(session)


@app.route('/api/sessions/<session_id>', methods=['PUT'])
def update_session(session_id):
    """更新会话"""
    session_file = SESSIONS_DIR / f"{session_id}.json"
    if not session_file.exists():
        return jsonify({"error": "会话不存在"}), 404

    updates = request.get_json()
    session = json.loads(session_file.read_text(encoding="utf-8"))

    for key, value in updates.items():
        if key != "session_id":
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
    return jsonify({"success": True})


# ============ AI 驱动的访谈 API ============

@app.route('/api/sessions/<session_id>/next-question', methods=['POST'])
def get_next_question(session_id):
    """获取下一个问题（AI 生成）"""
    session_file = SESSIONS_DIR / f"{session_id}.json"
    if not session_file.exists():
        return jsonify({"error": "会话不存在"}), 404

    session = json.loads(session_file.read_text(encoding="utf-8"))
    data = request.get_json() or {}
    dimension = data.get("dimension", "customer_needs")

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

    # 检查维度是否已完成（正式问题达到 3 个且没有需要追问的回答）
    if formal_questions_count >= 3:
        # 检查是否还有需要追问的回答
        needs_follow_up = any(log.get("needs_follow_up", False) for log in all_dim_logs if not log.get("is_follow_up", False))
        if not needs_follow_up:
            return jsonify({
                "dimension": dimension,
                "completed": True
            })

    # 调用 Claude 生成问题
    try:
        prompt = build_interview_prompt(session, dimension, all_dim_logs)
        response = call_claude(prompt, max_tokens=MAX_TOKENS_QUESTION)

        if not response:
            return jsonify({
                "error": "AI 响应失败",
                "detail": "未能从 AI 服务获取响应，请检查网络连接或稍后重试"
            }), 503

        # 解析 JSON 响应
        result = None
        parse_error = None

        if ENABLE_DEBUG_LOG:
            print(f"📝 AI 原始响应 (前500字): {response[:500]}")

        # 方法1: 直接尝试解析（如果AI严格遵守指令）
        try:
            cleaned = response.strip()
            if cleaned.startswith('{') and cleaned.endswith('}'):
                result = json.loads(cleaned)
                if ENABLE_DEBUG_LOG:
                    print(f"✅ 方法1成功: 直接解析")
        except json.JSONDecodeError as e:
            parse_error = e
            if ENABLE_DEBUG_LOG:
                print(f"⚠️ 方法1失败: {e}")

        # 方法2: 尝试提取 ```json 代码块
        if result is None and "```json" in response:
            try:
                json_start = response.find("```json") + 7
                json_end = response.find("```", json_start)
                if json_end > json_start:
                    json_str = response[json_start:json_end].strip()
                    result = json.loads(json_str)
                    if ENABLE_DEBUG_LOG:
                        print(f"✅ 方法2成功: 从代码块提取")
            except json.JSONDecodeError as e:
                parse_error = e
                if ENABLE_DEBUG_LOG:
                    print(f"⚠️ 方法2失败 (JSON错误): {e}")
            except Exception as e:
                parse_error = e
                if ENABLE_DEBUG_LOG:
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
                            if ENABLE_DEBUG_LOG:
                                print(f"✅ 方法3成功: 花括号配对提取")
                        except json.JSONDecodeError as e:
                            parse_error = e
                            if ENABLE_DEBUG_LOG:
                                print(f"⚠️ 方法3失败 (JSON错误): {e}")
            except Exception as e:
                parse_error = e
                if ENABLE_DEBUG_LOG:
                    print(f"⚠️ 方法3失败 (其他错误): {e}")

        # 方法4: 使用正则表达式提取 JSON 对象
        if result is None:
            try:
                import re
                json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
                matches = re.findall(json_pattern, response, re.DOTALL)
                for match in matches:
                    try:
                        candidate = json.loads(match)
                        # 验证必须有 question 字段
                        if isinstance(candidate, dict) and "question" in candidate:
                            result = candidate
                            if ENABLE_DEBUG_LOG:
                                print(f"✅ 方法4成功: 正则表达式提取")
                            break
                    except json.JSONDecodeError:
                        continue
            except Exception as e:
                parse_error = e
                if ENABLE_DEBUG_LOG:
                    print(f"⚠️ 方法4失败 (其他错误): {e}")

        # 方法5: 尝试修复不完整的JSON（补全缺失字段）
        if result is None and '{' in response and '"question"' in response:
            try:
                if ENABLE_DEBUG_LOG:
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
                            if ENABLE_DEBUG_LOG:
                                print(f"✅ 方法5成功: JSON修复完成")
                    except json.JSONDecodeError as e:
                        if ENABLE_DEBUG_LOG:
                            print(f"⚠️ 方法5失败: 修复后仍无法解析 - {e}")
            except Exception as e:
                parse_error = e
                if ENABLE_DEBUG_LOG:
                    print(f"⚠️ 方法5失败 (其他错误): {e}")

        # 成功解析
        if result is not None and isinstance(result, dict):
            # 确保必需字段存在
            if "question" in result and "options" in result:
                result["dimension"] = dimension
                result["ai_generated"] = True
                # 补全可能缺失的字段
                if "multi_select" not in result:
                    result["multi_select"] = False
                if "is_follow_up" not in result:
                    result["is_follow_up"] = False
                return jsonify(result)

        # 所有方法都失败了
        if ENABLE_DEBUG_LOG:
            print(f"❌ 所有解析方法都失败")
            print(f"📄 完整响应内容:\n{response}")

        return jsonify({
            "error": "AI 响应格式错误",
            "detail": f"AI 返回的内容中未找到有效的 JSON 格式数据。最后错误: {str(parse_error) if parse_error else '未知'}"
        }), 503

    except Exception as e:
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
    data = request.get_json()

    question = data.get("question")
    answer = data.get("answer")
    dimension = data.get("dimension")
    options = data.get("options", [])
    is_follow_up = data.get("is_follow_up", False)

    # 判断回答是否需要追问
    needs_follow_up = False
    if not is_follow_up:  # 只有正式问题才判断是否需要追问
        # 简单判断规则
        vague_indicators = ["看情况", "不一定", "可能", "或许", "大概", "差不多", "到时候", "再说", "还没想好", "不确定", "看具体", "根据情况"]
        is_short = len(answer) < 15
        has_vague = any(indicator in answer for indicator in vague_indicators)
        is_generic = answer in ["好的", "是的", "可以", "没问题", "需要", "应该要"]

        needs_follow_up = is_short or has_vague or is_generic

    # 添加到访谈记录
    log_entry = {
        "timestamp": get_utc_now(),
        "question": question,
        "answer": answer,
        "dimension": dimension,
        "options": options,
        "is_follow_up": is_follow_up,
        "needs_follow_up": needs_follow_up
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
        formal_count = len([log for log in session["interview_log"]
                           if log.get("dimension") == dimension and not log.get("is_follow_up", False)])
        session["dimensions"][dimension]["coverage"] = min(100, int(formal_count / 3 * 100))

    session["updated_at"] = get_utc_now()
    session_file.write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")

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
        formal_count = len([log for log in session["interview_log"]
                           if log.get("dimension") == dimension and not log.get("is_follow_up", False)])
        session["dimensions"][dimension]["coverage"] = min(100, int(formal_count / 3 * 100))

    session["updated_at"] = get_utc_now()
    session_file.write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")

    return jsonify(session)


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

    filename = file.filename
    filepath = TEMP_DIR / filename
    file.save(filepath)

    # 读取文件内容
    ext = Path(filename).suffix.lower()
    content = ""

    if ext in ['.md', '.txt']:
        content = filepath.read_text(encoding="utf-8")
    elif ext == '.pdf':
        content = f"[PDF 文件: {filename}]"  # 简化处理
    elif ext in ['.docx', '.xlsx', '.pptx']:
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
            except Exception as e:
                print(f"转换文档失败: {e}")

    # 更新会话
    session = json.loads(session_file.read_text(encoding="utf-8"))
    session["reference_docs"].append({
        "name": filename,
        "type": ext,
        "content": content[:10000],  # 限制长度
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
    """删除参考文档"""
    session_file = SESSIONS_DIR / f"{session_id}.json"
    if not session_file.exists():
        return jsonify({"error": "会话不存在"}), 404

    session = json.loads(session_file.read_text(encoding="utf-8"))

    # 查找并删除文档
    original_count = len(session["reference_docs"])
    session["reference_docs"] = [
        doc for doc in session["reference_docs"]
        if doc["name"] != doc_name
    ]

    if len(session["reference_docs"]) == original_count:
        return jsonify({"error": "文档不存在"}), 404

    session["updated_at"] = get_utc_now()
    session_file.write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")

    # 注意：不删除后台文件存档，仅从会话中移除引用
    # 这样文件仍保留在 temp/ 和 converted/ 目录中供后续使用

    return jsonify({
        "success": True,
        "deleted": doc_name
    })


# ============ 报告生成 API ============

@app.route('/api/sessions/<session_id>/generate-report', methods=['POST'])
def generate_report(session_id):
    """生成调研报告（AI 生成）"""
    session_file = SESSIONS_DIR / f"{session_id}.json"
    if not session_file.exists():
        return jsonify({"error": "会话不存在"}), 404

    session = json.loads(session_file.read_text(encoding="utf-8"))

    # 检查是否有 Claude API
    if claude_client:
        prompt = build_report_prompt(session)
        report_content = call_claude(prompt, max_tokens=MAX_TOKENS_REPORT)

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
    appendix += f"> 本次调研共收集了 {len(interview_log)} 个问题的回答\n\n"

    for i, log in enumerate(interview_log, 1):
        dim_name = DIMENSION_INFO.get(log.get('dimension', ''), {}).get('name', '未分类')
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

    content = f"""# {topic} 需求调研报告

**调研日期**: {now.strftime('%Y-%m-%d')}
**报告编号**: deep-vision-{now.strftime('%Y%m%d')}

---

## 1. 调研概述

本次调研主题为「{topic}」，共收集了 {len(interview_log)} 个问题的回答。

## 2. 需求摘要

"""

    for dim_key, dim_info in DIMENSION_INFO.items():
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
*此报告由 Deep Vision 深瞳-智能需求调研助手生成*
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
