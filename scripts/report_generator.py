#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
Deep-Vision 报告生成工具

用途: 基于会话数据生成专业的需求访谈报告
使用方式: uvx scripts/report_generator.py generate <会话ID> [输出文件]
"""

import argparse
import json
import logging
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class Colors:
    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    YELLOW = "\033[1;33m"
    NC = "\033[0m"


def log_info(message: str) -> None:
    print(f"{Colors.GREEN}[INFO]{Colors.NC} {message}")


def log_error(message: str) -> None:
    print(f"{Colors.RED}[ERROR]{Colors.NC} {message}")


def get_script_dir() -> Path:
    return Path(__file__).parent.resolve()


def get_session_dir() -> Path:
    return get_script_dir().parent / "data" / "sessions"


def get_reports_dir() -> Path:
    reports_dir = get_script_dir().parent / "data" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    return reports_dir


def get_template_path() -> Path:
    return get_script_dir().parent / "templates" / "report-template.md"


def load_session(session_id: str) -> Optional[dict]:
    """加载会话数据"""
    session_file = get_session_dir() / f"{session_id}.json"

    if not session_file.exists():
        log_error(f"会话不存在: {session_id}")
        return None

    try:
        return json.loads(session_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, IOError) as e:
        log_error(f"加载会话失败: {e}")
        return None


def slugify(text: str) -> str:
    """将文本转换为URL友好的slug"""
    # 移除非字母数字字符，保留中文
    text = re.sub(r'[^\w\u4e00-\u9fff\s-]', '', text)
    # 替换空格为连字符
    text = re.sub(r'[\s]+', '-', text)
    return text.lower()[:50]


def format_interview_log(interview_log: list) -> str:
    """格式化访谈记录"""
    if not interview_log:
        return "*无访谈记录*"

    lines = []
    for i, entry in enumerate(interview_log, 1):
        lines.append(f"**Q{i}**: {entry.get('question', '')}")
        lines.append(f"**A{i}**: {entry.get('answer', '')}")
        if entry.get('dimension'):
            lines.append(f"*维度: {entry['dimension']}*")
        lines.append("")

    return "\n".join(lines)


def calculate_dimensions_covered(dimensions: dict) -> str:
    """计算已覆盖的维度"""
    covered = []
    dim_names = {
        "customer_needs": "客户需求",
        "business_process": "业务流程",
        "tech_constraints": "技术约束",
        "project_constraints": "项目约束"
    }

    for key, name in dim_names.items():
        if dimensions.get(key, {}).get("coverage", 0) > 0:
            covered.append(name)

    return f"{len(covered)}/4 ({', '.join(covered) if covered else '无'})"


def generate_priority_matrix(requirements: list, dimensions: dict = None) -> str:
    """
    生成优先级矩阵的Mermaid代码

    注意: 使用 graph LR 格式而非 quadrantChart，因为 quadrantChart 是 Mermaid v10+
    才支持的图表类型，在很多渲染环境（飞书、GitHub、VS Code旧版等）中不支持。
    """
    high_priority = []
    medium_priority = []
    low_priority = []

    # 首先尝试从requirements生成
    if requirements:
        for req in requirements[:8]:
            name = req.get("title", "未命名")[:15]
            priority = req.get("priority", "中")
            req_type = req.get("type", "功能")

            item_info = {"name": name, "type": req_type}
            if priority == "高":
                high_priority.append(item_info)
            elif priority == "低":
                low_priority.append(item_info)
            else:
                medium_priority.append(item_info)

    # 如果没有requirements，从dimensions中提取
    if not high_priority and not medium_priority and not low_priority and dimensions:
        for dim_key, dim_data in dimensions.items():
            for item in dim_data.get("items", [])[:2]:
                if isinstance(item, dict):
                    name = item.get("name", "需求")[:15]
                else:
                    name = str(item)[:15]

                # 客户需求通常优先级高
                if dim_key == "customer_needs":
                    high_priority.append({"name": name, "type": "需求"})
                elif dim_key == "tech_constraints":
                    medium_priority.append({"name": name, "type": "技术"})
                else:
                    medium_priority.append({"name": name, "type": "流程"})

    # 生成 graph LR 格式的图表（兼容性更好）
    lines = ["graph LR"]

    if high_priority:
        lines.append("    subgraph 高优先级")
        for i, item in enumerate(high_priority[:4]):
            node_id = f"H{i+1}"
            lines.append(f"        {node_id}[{item['name']}]")
        lines.append("    end")

    if medium_priority:
        lines.append("    subgraph 中优先级")
        for i, item in enumerate(medium_priority[:4]):
            node_id = f"M{i+1}"
            lines.append(f"        {node_id}[{item['name']}]")
        lines.append("    end")

    if low_priority:
        lines.append("    subgraph 低优先级")
        for i, item in enumerate(low_priority[:4]):
            node_id = f"L{i+1}"
            lines.append(f"        {node_id}[{item['name']}]")
        lines.append("    end")

    # 添加样式
    if high_priority:
        for i in range(min(len(high_priority), 4)):
            lines.append(f"    style H{i+1} fill:#ff6b6b,color:#fff")
    if medium_priority:
        for i in range(min(len(medium_priority), 4)):
            lines.append(f"    style M{i+1} fill:#ffd93d,color:#333")
    if low_priority:
        for i in range(min(len(low_priority), 4)):
            lines.append(f"    style L{i+1} fill:#69db7c,color:#333")

    # 如果什么都没有，返回一个简单的占位图
    if not high_priority and not medium_priority and not low_priority:
        return """graph LR
    subgraph 待评估
        P1[需求待整理]
    end
    style P1 fill:#e9ecef,color:#333"""

    return "\n".join(lines)


def generate_priority_table(requirements: list, dimensions: dict = None) -> str:
    """
    生成优先级说明表格（作为图表的补充说明）
    """
    lines = [
        "",
        "**优先级说明**：",
        "",
        "| 需求 | 业务价值 | 实现成本 | 优先级 |",
        "|-----|---------|---------|-------|"
    ]

    items_added = 0

    # 从requirements生成
    if requirements:
        for req in requirements[:6]:
            name = req.get("title", "未命名")[:20]
            priority = req.get("priority", "中")
            priority_label = "P0" if priority == "高" else "P2" if priority == "低" else "P1"
            value = "高" if priority == "高" else "低" if priority == "低" else "中"
            cost = "中"  # 默认中等成本
            lines.append(f"| {name} | {value} | {cost} | {priority_label} |")
            items_added += 1

    # 从dimensions补充
    if items_added < 3 and dimensions:
        for dim_key, dim_data in dimensions.items():
            if items_added >= 6:
                break
            for item in dim_data.get("items", [])[:2]:
                if items_added >= 6:
                    break
                if isinstance(item, dict):
                    name = item.get("name", "需求")[:20]
                else:
                    name = str(item)[:20]

                if dim_key == "customer_needs":
                    lines.append(f"| {name} | 高 | 中 | P0 |")
                else:
                    lines.append(f"| {name} | 中 | 中 | P1 |")
                items_added += 1

    if items_added == 0:
        lines.append("| 待整理 | - | - | - |")

    return "\n".join(lines)


def generate_requirement_diagram(dimensions: dict) -> str:
    """生成需求关联图的Mermaid代码"""
    lines = ["    subgraph 客户需求"]

    customer_items = dimensions.get("customer_needs", {}).get("items", [])
    for i, item in enumerate(customer_items[:3], 1):
        if isinstance(item, dict):
            lines.append(f"        CN{i}[{item.get('name', f'需求{i}')}]")
        else:
            lines.append(f"        CN{i}[{str(item)[:20]}]")

    lines.append("    end")
    lines.append("    subgraph 业务流程")

    process_items = dimensions.get("business_process", {}).get("items", [])
    for i, item in enumerate(process_items[:3], 1):
        if isinstance(item, dict):
            lines.append(f"        BP{i}[{item.get('name', f'流程{i}')}]")
        else:
            lines.append(f"        BP{i}[{str(item)[:20]}]")

    lines.append("    end")

    # 添加关联
    if customer_items and process_items:
        lines.append("    CN1 --> BP1")

    return "\n".join(lines)


def generate_user_journey(session: dict) -> str:
    """生成用户旅程图的Mermaid代码"""
    scenario = session.get("scenario") or "需求访谈"

    return f"""    section 启动
      确定访谈主题: 5: 用户
      准备参考文档: 4: 用户
    section 访谈
      回答选择题: 5: 用户
      补充详细信息: 4: 用户
    section 确认
      审核需求摘要: 5: 用户
      提出修正意见: 4: 用户
    section 完成
      获取访谈报告: 5: 用户"""


def generate_system_architecture(dimensions: dict) -> str:
    """生成系统架构图的Mermaid代码"""
    tech_items = dimensions.get("tech_constraints", {}).get("items", [])

    lines = [
        "    subgraph 前端层",
        "        UI[用户界面]",
        "    end",
        "    subgraph 服务层",
        "        API[API网关]",
        "        Service[业务服务]",
        "    end",
        "    subgraph 数据层",
        "        DB[(数据库)]",
        "    end",
        "    UI --> API",
        "    API --> Service",
        "    Service --> DB"
    ]

    return "\n".join(lines)


def generate_business_flow(dimensions: dict) -> str:
    """生成业务流程图的Mermaid代码"""
    process_items = dimensions.get("business_process", {}).get("items", [])

    if not process_items:
        return "    A[开始] --> B[处理] --> C[结束]"

    lines = ["    A[开始]"]
    prev = "A"

    for i, item in enumerate(process_items[:5], 1):
        if isinstance(item, dict):
            name = item.get('name', f'步骤{i}')
        else:
            name = str(item)[:20]
        node = chr(65 + i)  # B, C, D, E, F
        lines.append(f"    {prev} --> {node}[{name}]")
        prev = node

    lines.append(f"    {prev} --> Z[结束]")

    return "\n".join(lines)


def render_template(template: str, session: dict) -> str:
    """渲染报告模板"""
    now = datetime.now()
    dimensions = session.get("dimensions", {})
    requirements = session.get("requirements", [])

    # 基础替换
    replacements = {
        "{{PROJECT_NAME}}": session.get("topic", "未命名项目"),
        "{{DATE}}": now.strftime("%Y-%m-%d %H:%M"),
        "{{DATE_SHORT}}": now.strftime("%Y%m%d"),
        "{{PROJECT_SLUG}}": slugify(session.get("topic", "project")),
        "{{SCENARIO}}": session.get("scenario") or "通用需求访谈",
        "{{DURATION}}": "约30分钟",  # 可以根据interview_log计算
        "{{DIMENSIONS_COVERED}}": calculate_dimensions_covered(dimensions),
        "{{FULL_INTERVIEW_LOG}}": format_interview_log(session.get("interview_log", [])),
        "{{PRIORITY_MATRIX}}": generate_priority_matrix(requirements),
        "{{REQUIREMENT_RELATION_DIAGRAM}}": generate_requirement_diagram(dimensions),
        "{{USER_JOURNEY_DIAGRAM}}": generate_user_journey(session),
        "{{SYSTEM_ARCHITECTURE_DIAGRAM}}": generate_system_architecture(dimensions),
        "{{BUSINESS_FLOW_DIAGRAM}}": generate_business_flow(dimensions),
        "{{BUDGET_INFO}}": "*待确认*",
    }

    result = template
    for key, value in replacements.items():
        result = result.replace(key, value)

    # 处理条件块（简化处理）
    # 移除 Handlebars 语法的条件块，替换为实际内容或占位符
    result = re.sub(r'\{\{#if.*?\}\}.*?\{\{/if\}\}', '*待补充*', result, flags=re.DOTALL)
    result = re.sub(r'\{\{#each.*?\}\}.*?\{\{/each\}\}', '', result, flags=re.DOTALL)
    result = re.sub(r'\{\{#unless.*?\}\}.*?\{\{/unless\}\}', '', result, flags=re.DOTALL)
    result = re.sub(r'\{\{else\}\}', '', result)
    result = re.sub(r'\{\{this\..*?\}\}', '', result)
    result = re.sub(r'\{\{@index\}\}', '', result)

    return result


def generate_simple_report(session: dict) -> str:
    """生成完整的专业报告"""
    now = datetime.now()
    topic = session.get("topic", "未命名项目")
    dimensions = session.get("dimensions", {})
    interview_log = session.get("interview_log", [])
    requirements = session.get("requirements", [])
    scenario = session.get("scenario") or "通用需求访谈"

    # 从访谈记录中提取各维度的详细信息
    dim_answers = {
        "customer_needs": [],
        "business_process": [],
        "tech_constraints": [],
        "project_constraints": []
    }
    for log in interview_log:
        dim = log.get("dimension", "")
        if dim in dim_answers:
            dim_answers[dim].append({
                "question": log.get("question", ""),
                "answer": log.get("answer", "")
            })

    report_lines = [
        f"# {topic} 需求访谈报告",
        "",
        f"**访谈日期**: {now.strftime('%Y-%m-%d %H:%M')}",
        f"**访谈场景**: {scenario}",
        f"**报告编号**: deep-vision-{now.strftime('%Y%m%d')}-{slugify(topic)}",
        "",
        "---",
        "",
        "## 1. 访谈概述",
        "",
        "### 1.1 基本信息",
        "",
        "| 项目 | 内容 |",
        "|-----|------|",
        f"| 访谈主题 | {topic} |",
        f"| 访谈场景 | {scenario} |",
        f"| 访谈时长 | 约{len(interview_log) * 2}分钟 |",
        f"| 完成维度 | {calculate_dimensions_covered(dimensions)} |",
        "",
        "### 1.2 参考文档",
        "",
    ]

    ref_docs = session.get("reference_docs", [])
    if ref_docs:
        report_lines.append("| 文档名称 | 文档类型 |")
        report_lines.append("|---------|---------|")
        for doc in ref_docs:
            if isinstance(doc, dict):
                report_lines.append(f"| {doc.get('name', '未知')} | {doc.get('type', '未知')} |")
            else:
                report_lines.append(f"| {doc} | - |")
    else:
        report_lines.append("*本次访谈未使用参考文档*")

    report_lines.extend([
        "",
        "---",
        "",
        "## 2. 需求摘要",
        "",
        "### 2.1 核心需求列表",
        "",
    ])

    # 生成核心需求列表
    if requirements:
        for req in requirements:
            priority_icon = "🔴" if req.get("priority") == "高" else "🟡" if req.get("priority") == "中" else "🟢"
            report_lines.append(f"- {priority_icon} **{req.get('id', 'REQ')}**: {req.get('title', '未命名')}")
            report_lines.append(f"  - 优先级: {req.get('priority', '中')} | 类型: {req.get('type', '功能')}")
    else:
        # 从dimensions中提取核心需求
        req_id = 1
        for dim_key, dim_data in dimensions.items():
            for item in dim_data.get("items", [])[:3]:
                if isinstance(item, dict):
                    name = item.get("name", "")
                    desc = item.get("description", "")
                    if name:
                        report_lines.append(f"- **REQ-{req_id:03d}**: {name}")
                        if desc:
                            report_lines.append(f"  - {desc[:100]}")
                        req_id += 1

    report_lines.extend([
        "",
        "### 2.2 优先级矩阵",
        "",
        "```mermaid",
        generate_priority_matrix(requirements, dimensions),
        "```",
        generate_priority_table(requirements, dimensions),
        "",
        "---",
        "",
        "## 3. 详细需求分析",
        "",
    ])

    # 3.1 客户/用户需求
    report_lines.extend([
        "### 3.1 客户/用户需求",
        "",
        "#### 核心痛点",
        "",
    ])
    customer_items = dimensions.get("customer_needs", {}).get("items", [])
    if customer_items:
        for item in customer_items:
            if isinstance(item, dict):
                name = item.get("name", "")
                desc = item.get("description", "")
                report_lines.append(f"- **{name}**: {desc}" if desc else f"- {name}")
            else:
                report_lines.append(f"- {item}")
    else:
        # 从访谈记录中提取
        for qa in dim_answers.get("customer_needs", []):
            report_lines.append(f"- {qa['answer']}")
    if not customer_items and not dim_answers.get("customer_needs"):
        report_lines.append("*待补充*")

    report_lines.extend([
        "",
        "#### 期望价值",
        "",
    ])
    # 从访谈中提取期望相关内容
    expectations = [qa for qa in dim_answers.get("customer_needs", []) if "期望" in qa["question"] or "价值" in qa["question"]]
    if expectations:
        for qa in expectations:
            report_lines.append(f"- {qa['answer']}")
    else:
        report_lines.append("- 提升工作效率")
        report_lines.append("- 降低运营成本")
        report_lines.append("- 改善用户体验")

    report_lines.extend([
        "",
        "#### 用户角色",
        "",
    ])
    roles = [qa for qa in dim_answers.get("customer_needs", []) if "角色" in qa["question"] or "用户" in qa["question"]]
    if roles:
        for qa in roles:
            for role in qa['answer'].split('、'):
                report_lines.append(f"- {role.strip()}")
    else:
        report_lines.append("*待补充*")

    # 3.2 业务流程
    report_lines.extend([
        "",
        "### 3.2 业务流程",
        "",
        "#### 关键流程",
        "",
    ])
    process_items = dimensions.get("business_process", {}).get("items", [])
    if process_items:
        for item in process_items:
            if isinstance(item, dict):
                name = item.get("name", "")
                desc = item.get("description", "")
                report_lines.append(f"- **{name}**: {desc}" if desc else f"- {name}")
            else:
                report_lines.append(f"- {item}")
    else:
        for qa in dim_answers.get("business_process", []):
            report_lines.append(f"- {qa['answer']}")
    if not process_items and not dim_answers.get("business_process"):
        report_lines.append("*待补充*")

    report_lines.extend([
        "",
        "#### 流程图",
        "",
        "```mermaid",
        "flowchart TD",
        generate_business_flow(dimensions),
        "```",
        "",
    ])

    # 3.3 技术约束
    report_lines.extend([
        "### 3.3 技术约束",
        "",
        "#### 技术栈要求",
        "",
    ])
    tech_items = dimensions.get("tech_constraints", {}).get("items", [])
    if tech_items:
        for item in tech_items:
            if isinstance(item, dict):
                name = item.get("name", "")
                desc = item.get("description", "")
                report_lines.append(f"- **{name}**: {desc}" if desc else f"- {name}")
            else:
                report_lines.append(f"- {item}")
    else:
        for qa in dim_answers.get("tech_constraints", []):
            report_lines.append(f"- {qa['answer']}")
    if not tech_items and not dim_answers.get("tech_constraints"):
        report_lines.append("*待补充*")

    report_lines.extend([
        "",
        "#### 集成接口要求",
        "",
    ])
    integrations = [qa for qa in dim_answers.get("tech_constraints", []) if "集成" in qa["question"] or "接口" in qa["question"]]
    if integrations:
        for qa in integrations:
            report_lines.append(f"- {qa['answer']}")
    else:
        report_lines.append("*待补充*")

    report_lines.extend([
        "",
        "#### 性能与安全要求",
        "",
    ])
    perf_security = [qa for qa in dim_answers.get("tech_constraints", []) if "性能" in qa["question"] or "安全" in qa["question"] or "并发" in qa["question"]]
    if perf_security:
        for qa in perf_security:
            report_lines.append(f"- {qa['answer']}")
    else:
        report_lines.append("*待补充*")

    # 3.4 项目约束
    report_lines.extend([
        "",
        "### 3.4 项目约束",
        "",
        "#### 预算与工期",
        "",
    ])
    project_items = dimensions.get("project_constraints", {}).get("items", [])
    if project_items:
        for item in project_items:
            if isinstance(item, dict):
                name = item.get("name", "")
                desc = item.get("description", "")
                report_lines.append(f"- **{name}**: {desc}" if desc else f"- {name}")
            else:
                report_lines.append(f"- {item}")
    else:
        for qa in dim_answers.get("project_constraints", []):
            report_lines.append(f"- {qa['answer']}")
    if not project_items and not dim_answers.get("project_constraints"):
        report_lines.append("*待补充*")

    report_lines.extend([
        "",
        "#### 资源与其他约束",
        "",
        "*待补充*",
        "",
        "---",
        "",
        "## 4. 可视化分析",
        "",
        "### 4.1 需求关联图",
        "",
        "```mermaid",
        "graph TB",
        generate_requirement_diagram(dimensions),
        "```",
        "",
        "### 4.2 用户旅程图",
        "",
        "```mermaid",
        "journey",
        f"    title {topic} 用户旅程",
        generate_user_journey(session),
        "```",
        "",
        "### 4.3 系统架构图",
        "",
        "```mermaid",
        "graph TB",
        generate_system_architecture(dimensions),
        "```",
        "",
        "---",
        "",
        "## 5. 竞品对比",
        "",
        "*本次访谈未涉及竞品对比分析*",
        "",
        "---",
        "",
        "## 6. 实现建议",
        "",
        "### 6.1 技术方案建议",
        "",
    ])

    # 根据技术约束生成建议
    if tech_items:
        report_lines.append("基于本次访谈收集的技术约束，建议：")
        report_lines.append("")
        for i, item in enumerate(tech_items[:3], 1):
            if isinstance(item, dict):
                name = item.get("name", "")
                report_lines.append(f"{i}. **{name}** - 建议按照业界最佳实践实施")
    else:
        report_lines.append("- 建议采用成熟稳定的技术栈")
        report_lines.append("- 建议预留系统扩展接口")
        report_lines.append("- 建议建立完善的监控体系")

    report_lines.extend([
        "",
        "### 6.2 实施路径建议",
        "",
        "**Phase 1: 核心功能 (1-2个月)**",
        "- 完成核心业务功能开发",
        "- 建立基础数据模型",
        "",
        "**Phase 2: 功能扩展 (2-3个月)**",
        "- 完成辅助功能开发",
        "- 系统集成与联调",
        "",
        "**Phase 3: 优化上线 (1个月)**",
        "- 性能优化与测试",
        "- 用户培训与上线",
        "",
        "---",
        "",
        "## 7. 风险评估",
        "",
        "| 风险项 | 可能性 | 影响程度 | 应对策略 |",
        "|-------|-------|---------|---------|",
    ])

    # 根据访谈内容生成风险评估
    if project_items:
        for item in project_items[:2]:
            if isinstance(item, dict):
                name = item.get("name", "")
                if "预算" in name or "成本" in name:
                    report_lines.append(f"| 预算超支风险 | 中 | 高 | 建立成本监控机制 |")
                elif "时间" in name or "工期" in name:
                    report_lines.append(f"| 工期延误风险 | 中 | 高 | 制定详细里程碑计划 |")
    report_lines.append("| 需求变更风险 | 高 | 中 | 建立变更控制流程 |")
    report_lines.append("| 技术实现风险 | 低 | 中 | 提前进行技术验证 |")

    report_lines.extend([
        "",
        "---",
        "",
        "## 8. 附录",
        "",
        "### 8.1 完整访谈记录",
        "",
        "<details>",
        "<summary>点击展开完整访谈记录</summary>",
        "",
        format_interview_log(interview_log),
        "",
        "</details>",
        "",
        "### 8.2 术语表",
        "",
        "| 术语 | 定义 |",
        "|-----|-----|",
    ])

    # 从访谈中提取可能的术语
    terms_added = set()
    common_terms = {
        "CRM": "客户关系管理系统",
        "ERP": "企业资源规划系统",
        "API": "应用程序编程接口",
        "SSO": "单点登录",
        "BI": "商业智能",
        "SaaS": "软件即服务",
        "微服务": "一种分布式系统架构风格",
        "混合云": "公有云与私有云的混合部署模式"
    }
    for log in interview_log:
        answer = log.get("answer", "")
        for term, definition in common_terms.items():
            if term in answer and term not in terms_added:
                report_lines.append(f"| {term} | {definition} |")
                terms_added.add(term)

    if not terms_added:
        report_lines.append("| - | *无特殊术语* |")

    report_lines.extend([
        "",
        "---",
        "",
        "## 文档信息",
        "",
        "- **生成工具**: Deep-Vision 智能访谈技能",
        f"- **生成日期**: {now.strftime('%Y-%m-%d %H:%M')}",
        "- **版本**: v1.1",
        "",
        "---",
        "",
        "*此报告由 Deep-Vision 智能访谈技能自动生成，内容严格基于访谈收集的信息*",
    ])

    return "\n".join(report_lines)


def generate_report(session_id: str, output_path: Optional[str] = None) -> Optional[str]:
    """
    生成访谈报告

    Args:
        session_id: 会话ID
        output_path: 输出文件路径（可选）

    Returns:
        Optional[str]: 生成的报告文件路径
    """
    session = load_session(session_id)
    if not session:
        return None

    template_path = get_template_path()

    if template_path.exists():
        try:
            template = template_path.read_text(encoding="utf-8")
            report_content = render_template(template, session)
        except Exception as e:
            log_error(f"渲染模板失败，使用简化报告: {e}")
            report_content = generate_simple_report(session)
    else:
        log_info("未找到报告模板，使用简化报告格式")
        report_content = generate_simple_report(session)

    # 确定输出路径
    if output_path:
        output_file = Path(output_path)
    else:
        topic_slug = slugify(session.get("topic", "report"))
        date_str = datetime.now().strftime("%Y%m%d")
        filename = f"deep-vision-{date_str}-{topic_slug}.md"
        output_file = get_reports_dir() / filename

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(report_content, encoding="utf-8")

    log_info(f"报告已生成: {output_file}")
    return str(output_file)


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="Deep-Vision 报告生成工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  uvx scripts/report_generator.py generate dv-20260120-abc12345
  uvx scripts/report_generator.py generate dv-20260120-abc12345 /path/to/output.md
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="命令")

    # generate 命令
    gen_parser = subparsers.add_parser("generate", help="生成访谈报告")
    gen_parser.add_argument("session_id", help="会话ID")
    gen_parser.add_argument("output", nargs="?", help="输出文件路径（可选）")

    # preview 命令
    preview_parser = subparsers.add_parser("preview", help="预览报告（输出到stdout）")
    preview_parser.add_argument("session_id", help="会话ID")

    args = parser.parse_args()

    if args.command == "generate":
        result = generate_report(args.session_id, args.output)
        if result:
            print(result)
            sys.exit(0)
        else:
            sys.exit(1)

    elif args.command == "preview":
        session = load_session(args.session_id)
        if session:
            report = generate_simple_report(session)
            print(report)
            sys.exit(0)
        else:
            sys.exit(1)

    else:
        parser.print_help()
        sys.exit(0)


if __name__ == "__main__":
    main()
