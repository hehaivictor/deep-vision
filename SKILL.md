---
name: deep-vision
description: 智能访谈技能，通过选择式交互深度挖掘被访谈人的真实需求，生成专业访谈报告。当用户需要进行需求访谈、客户访谈或产品规划时使用。
argument-hint: [主题/项目名称]
model: opus
---

# Deep-Vision 智能访谈技能

## 技能概述

Deep-Vision 是一个基于选择式交互的智能访谈技能。核心设计理念是**让被访谈者只需做选择**，通过多轮对话访谈深度挖掘真实需求，最终生成图文并茂的专业需求文档。

## 适用场景

- **主要场景**: 客户需求访谈、产品需求规划、售前方案沟通
- **次要场景**: 技术访谈、项目申报、招投标方案、内部需求收集
- **排除条件**: 简单的单问题咨询、已有完整需求文档的情况、非访谈类任务

## 核心能力

### 选择式交互
- 所有问题以选择题形式呈现（2-4个选项 + "其他"）
- 动态生成选项，基于上下文和行业知识
- 降低用户认知负担，提升访谈效率

### 智能追问
- 识别表面需求，通过追问挖掘本质需求
- 检测回答与参考文档的冲突并立即澄清
- 根据用户回答详细程度自适应调整

### 知识增强
- 遇到专业领域问题时联网搜索最新信息
- 无感融入选项生成，不打断访谈节奏

### 报告生成
- 覆盖4大维度的结构化报告
- 自动生成Mermaid可视化图表
- 支持会话暂存和续约

---

## 执行流程（必须严格遵循）

### 阶段0: 会话初始化（必须执行）

**步骤0.1: 检查未完成会话**

首先读取 sessions 目录下的所有会话文件，查找 status 为 "in_progress" 或 "paused" 的会话：

```bash
# 列出会话目录
ls -la /Users/hehai/.claude/skills/deep-vision/data/sessions/
```

如果有未完成会话，使用 AskUserQuestion 询问用户：
- 继续上次的会话：[主题名称]
- 开始新的访谈会话

**步骤0.2: 创建或恢复会话**

**如果开始新会话**：
1. 生成会话ID：`dv-{YYYYMMDDHHMMSS}-{8位随机hex}`
2. 使用 Write 工具创建会话文件 `/Users/hehai/.claude/skills/deep-vision/data/sessions/{session_id}.json`

初始会话数据结构：
```json
{
  "session_id": "dv-20260122100000-abcd1234",
  "topic": "访谈主题",
  "created_at": "2026-01-22T10:00:00Z",
  "updated_at": "2026-01-22T10:00:00Z",
  "status": "in_progress",
  "scenario": null,
  "dimensions": {
    "customer_needs": {"coverage": 0, "items": []},
    "business_process": {"coverage": 0, "items": []},
    "tech_constraints": {"coverage": 0, "items": []},
    "project_constraints": {"coverage": 0, "items": []}
  },
  "reference_docs": [],
  "interview_log": [],
  "requirements": [],
  "summary": null
}
```

**如果恢复会话**：
1. 使用 Read 工具读取会话文件
2. 更新 status 为 "in_progress"
3. 更新 updated_at 时间戳
4. 使用 Write 工具保存

**关键**: 必须记住当前会话ID，后续所有操作都需要更新这个会话文件。

### 阶段1: 确定访谈主题

如果用户提供了参数，将其作为访谈主题；否则使用 AskUserQuestion 询问。

确定主题后，**立即更新会话文件**的 topic 字段。

### 阶段2: 文档准备（可选）

询问用户是否有参考文档：
- 有，我来上传文档
- 没有，直接开始访谈

**文档处理**：
- md/txt/pdf 格式：直接使用 Read 工具读取
- docx/xlsx/pptx 格式：执行转换脚本后读取

```bash
uv run /Users/hehai/.claude/skills/deep-vision/scripts/convert_doc.py convert <文件路径>
```

处理文档后，**更新会话文件**的 reference_docs 字段，添加文档信息。

### 阶段3: 选择式访谈（核心阶段）

使用 AskUserQuestion 工具进行访谈，需覆盖4大维度：

**维度1: 客户/用户需求 (customer_needs)**
- 核心痛点、期望价值、使用场景、用户角色

**维度2: 业务流程 (business_process)**
- 关键流程节点、角色分工、触发事件、异常处理

**维度3: 技术约束 (tech_constraints)**
- 现有技术栈、集成接口要求、性能指标、安全合规

**维度4: 项目约束 (project_constraints)**
- 预算范围、时间节点、资源限制、其他约束

#### 访谈规则

1. 每个问题动态生成2-4个选项，始终包含"其他"选项
2. 当识别到表面需求时生成追问选项挖掘本质需求
3. 如果用户回答与文档内容冲突，立即指出要求澄清
4. 遇到专业领域问题时使用 WebSearch 搜索信息融入选项
5. 根据对话内容识别访谈场景调整问题侧重点

#### 数据保存规则（强制执行）

**每次用户回答后，必须立即执行以下保存操作：**

1. **添加访谈记录**到 interview_log 数组：
```json
{
  "timestamp": "2026-01-22T10:05:00Z",
  "question": "您的核心痛点是什么？",
  "answer": "效率低下、成本过高",
  "dimension": "customer_needs"
}
```

2. **更新维度覆盖度**：
   - 每个维度至少需要2-3个问题
   - 每回答完一个问题，根据当前维度的问题数量计算 coverage 百分比
   - 例如：维度有3个问题计划，完成1个则coverage=33，完成2个则coverage=67，完成3个则coverage=100

3. **更新 items 数组**：将用户的关键回答提取为结构化数据
```json
{
  "name": "效率低下",
  "description": "当前流程需要多次手动操作，耗时较长",
  "priority": "高"
}
```

4. **更新 updated_at 时间戳**

5. **使用 Write 工具保存完整会话文件**

**示例保存操作**：
```
每次用户回答后，必须：
1. 读取当前会话文件（如果内存中没有最新版本）
2. 添加新的 interview_log 条目
3. 更新对应维度的 coverage 和 items
4. 更新 updated_at
5. 使用 Write 工具写入完整的 JSON 到会话文件
```

#### 进度展示（每3-5个问题展示一次）

```
📊 访谈进度
 ✅ 客户需求    [████████████] 100%
 🔄 业务流程    [████████░░░░]  67%
 ⬜ 技术约束    [░░░░░░░░░░░░]   0%
 ⬜ 项目约束    [░░░░░░░░░░░░]   0%
```

### 阶段4: 需求确认

当4大维度都有覆盖（每个维度 coverage >= 50%）后，展示需求摘要。

**摘要必须严格基于 interview_log 中的实际回答生成**，不得编造任何内容。

```markdown
## 需求摘要确认

基于我们的访谈，以下是您的核心需求：

### 客户需求
- [从 interview_log 中提取的实际回答]

### 业务流程
- [从 interview_log 中提取的实际回答]

### 技术约束
- [从 interview_log 中提取的实际回答]

### 项目约束
- [从 interview_log 中提取的实际回答]

请确认以上内容是否准确？
```

使用 AskUserQuestion 提供选项：
- 确认无误，生成报告
- 需要修正部分内容
- 继续补充更多信息

确认后，**更新会话文件**的 summary 字段。

### 阶段5: 报告生成

**报告生成必须由 Claude 直接完成**，不使用外部脚本。这样可以确保报告质量。

#### 报告生成步骤

1. **读取完整会话数据**：使用 Read 工具读取会话文件，确保获取所有 interview_log

2. **生成报告内容**：严格按照下方的报告模板和质量标准生成

3. **保存报告文件**：使用 Write 工具保存到 `/Users/hehai/.claude/skills/deep-vision/data/reports/deep-vision-{YYYYMMDD}-{主题}.md`

4. **更新会话状态**：
   - 设置 status 为 "completed"
   - 更新 updated_at
   - 使用 Write 工具保存会话文件

---

## 报告模板与质量标准

### 报告结构（必须包含）

```markdown
# {主题} 需求访谈报告

**访谈日期**: {YYYY-MM-DD}
**访谈场景**: {场景描述}
**报告编号**: deep-vision-{YYYYMMDD}-{主题slug}

---

## 1. 访谈概述

### 1.1 基本信息

| 项目 | 内容 |
|-----|------|
| 访谈主题 | {主题} |
| 访谈场景 | {场景} |
| 完成维度 | {已完成数}/4 ({维度列表}) |

### 1.2 参考文档

{如有参考文档，列出文档名称、类型、关键信息}
{如无，写"本次访谈未使用参考文档"}

---

## 2. 需求摘要

### 2.1 核心需求列表

{从 interview_log 中提取的核心需求，使用表格格式：}

| 序号 | 需求类别 | 需求描述 | 优先级 |
|-----|---------|---------|-------|
| 1 | {类别} | {描述} | {高/中/低} |

### 2.2 优先级矩阵

```mermaid
graph LR
    subgraph 高优先级
        {需求节点}
    end
    subgraph 中优先级
        {需求节点}
    end

    style {高优先级节点} fill:#ff6b6b,color:#fff
    style {中优先级节点} fill:#ffd93d,color:#333
```

**优先级说明**：

| 需求 | 业务价值 | 实现成本 | 优先级 |
|-----|---------|---------|-------|
| {需求} | {高/中/低} | {高/中/低} | P0/P1/P2 |

---

## 3. 详细需求分析

### 3.1 客户/用户需求

#### 核心痛点
{严格基于用户回答，列出具体痛点}

#### 期望价值
{严格基于用户回答，列出期望}

#### 使用场景
{严格基于用户回答，描述场景}

#### 用户角色

| 角色 | 人数/比例 | 主要使用场景 |
|-----|----------|-------------|
| {角色} | {数量} | {场景} |

### 3.2 业务流程

#### 关键流程
{严格基于用户回答，描述流程}

#### 流程图

```mermaid
flowchart TD
    {基于用户描述的流程生成}
```

### 3.3 技术约束

#### 部署方式
{严格基于用户回答}

#### 系统集成
{严格基于用户回答}

#### 安全合规
{严格基于用户回答}

### 3.4 项目约束

#### 预算范围
{严格基于用户回答}

#### 时间节点
{严格基于用户回答}

#### 资源限制
{严格基于用户回答}

---

## 4. 可视化分析

{根据访谈内容生成2-3个相关的 Mermaid 图表}

### 4.1 {图表标题}

```mermaid
{使用兼容性好的图表类型：graph/flowchart/pie/gantt}
```

---

## 5. 方案建议

{基于收集的需求，给出具体可行的建议}

### 5.1 推荐方案
{方案描述和理由}

### 5.2 注意事项
{基于用户约束的提醒}

---

## 6. 风险评估

| 风险项 | 可能性 | 影响程度 | 应对策略 |
|-------|-------|---------|---------|
| {风险} | 高/中/低 | 高/中/低 | {策略} |

---

## 7. 下一步行动

| 序号 | 行动项 | 负责方 | 时间节点 |
|-----|-------|-------|---------|
| 1 | {行动} | {负责方} | {时间} |

---

## 8. 附录

### 8.1 完整访谈记录

<details>
<summary>点击展开完整访谈记录</summary>

{遍历 interview_log，格式化输出所有问答}

**Q1**: {问题}
**A1**: {回答}
*维度: {dimension}*

...

</details>

### 8.2 术语表

| 术语 | 定义 |
|-----|-----|
| {术语} | {定义} |

---

## 文档信息

- **生成工具**: Deep-Vision 智能访谈技能
- **生成日期**: {YYYY-MM-DD}
- **会话ID**: {session_id}
- **版本**: v1.0

---

*此报告由 Deep-Vision 智能访谈技能自动生成，内容严格基于访谈收集的信息*
```

### 报告质量标准（必须满足）

1. **内容真实性**: 所有内容必须严格基于 interview_log 中的用户回答，不得编造
2. **结构完整性**: 必须包含以上模板中的所有章节
3. **数据一致性**: 报告中的数据必须与会话文件中的数据一致
4. **可视化要求**: 至少包含3个 Mermaid 图表（优先级矩阵、流程图、其他分析图）
5. **可操作性**: 必须包含具体的下一步行动建议
6. **Mermaid兼容性**: 只使用高兼容性图表类型（graph/flowchart/sequenceDiagram/journey/pie/gantt/classDiagram），避免使用 quadrantChart/xychart/sankey/mindmap/timeline

---

## 会话管理命令（辅助工具）

这些脚本可以作为辅助工具使用，但**核心数据保存必须由 Claude 直接使用 Write 工具完成**。

**查看所有会话**：
```bash
uv run /Users/hehai/.claude/skills/deep-vision/scripts/session_manager.py list
```

**查看会话详情**：
```bash
uv run /Users/hehai/.claude/skills/deep-vision/scripts/session_manager.py get <会话ID>
```

**暂停/恢复会话**：
```bash
uv run /Users/hehai/.claude/skills/deep-vision/scripts/session_manager.py pause <会话ID>
uv run /Users/hehai/.claude/skills/deep-vision/scripts/session_manager.py resume <会话ID>
```

---

## 重要提醒

### 数据保存检查清单（每次访谈回答后）

- [ ] 是否已将问答添加到 interview_log？
- [ ] 是否已更新对应维度的 coverage？
- [ ] 是否已更新对应维度的 items？
- [ ] 是否已更新 updated_at 时间戳？
- [ ] 是否已使用 Write 工具保存会话文件？

### 会话完成检查清单（生成报告前）

- [ ] interview_log 是否包含所有访谈记录？
- [ ] 每个维度的 coverage 是否 >= 50%？
- [ ] 用户是否已确认需求摘要？

### 报告生成检查清单

- [ ] 报告是否包含所有必需章节？
- [ ] 所有内容是否基于 interview_log 生成？
- [ ] 是否包含至少3个 Mermaid 图表？
- [ ] 是否包含完整的访谈记录附录？
- [ ] 会话状态是否已更新为 "completed"？

### 其他规则

- **严格基于访谈内容生成报告**: 不得编造用户未提及的需求
- **保持选择式交互**: 除非用户选择"其他"，否则不要求用户输入文字
- **专业但友好**: 保持专业访谈的严谨性，同时语气友好易懂
- **维度平衡**: 确保4大维度都有覆盖，不要过度深入某一维度

---

## 目录结构

```
deep-vision/
├── SKILL.md              # 技能定义文件
├── scripts/
│   ├── convert_doc.py    # 文档转换脚本
│   ├── session_manager.py # 会话管理脚本（辅助）
│   └── report_generator.py # 报告生成脚本（辅助）
├── templates/
│   └── report-template.md # 报告模板参考
├── data/                 # 数据目录
│   ├── sessions/         # 会话状态存储
│   ├── reports/          # 生成的报告
│   ├── converted/        # 转换后的文档
│   └── temp/             # 临时文件
└── docs/
    └── deep-vision-prd.md # 需求文档
```

---

## 开始执行

现在开始访谈会话：

1. 首先检查 `/Users/hehai/.claude/skills/deep-vision/data/sessions/` 目录是否有未完成的会话
2. 如有未完成会话，询问用户是否继续
3. 如果有参数则以此为主题创建新会话
4. 否则询问用户想访谈什么项目/产品
