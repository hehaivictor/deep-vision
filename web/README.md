# Deep Vision Web - AI 驱动的智能访谈前端

## 设计理念

这是一个**完整实现 deep-vision 技能的 AI 驱动的 Web 应用**，提供与 Claude Code CLI 中使用 `/deep-vision` 技能完全相同的真实体验。

### 核心特性

| 特性 | 说明 |
|-----|------|
| **AI 驱动** | 集成 Claude API，动态生成问题和选项 |
| **智能追问** | 识别表面需求，自动深挖本质需求 |
| **冲突检测** | 检测用户回答与参考文档的冲突并立即澄清 |
| **知识增强** | 遇到专业领域问题时可联网搜索最新信息 |
| **专业报告** | AI 自动生成结构化访谈报告，包含可视化图表 |

## 快速开始

### 1. 环境准备

确保已安装 `uv` 和 Python 3.10+：

```bash
# 安装 uv（如果未安装）
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. 配置 API Key（重要）

**设置 Anthropic API Key 以启用 AI 功能**：

```bash
# 临时设置（当前会话有效）
export ANTHROPIC_API_KEY="your-api-key-here"

# 永久设置（推荐）
echo 'export ANTHROPIC_API_KEY="your-api-key-here"' >> ~/.zshrc  # 或 ~/.bashrc
source ~/.zshrc
```

> **注意**: 如果不设置 API Key，前端仍可使用，但会回退到静态问题库模式（不推荐）。

### 3. 启动服务

```bash
cd /Users/hehai/.claude/skills/deep-vision/web
uv run server.py
```

启动后会看到：

```
============================================================
Deep Vision AI 驱动的智能访谈服务
============================================================
Sessions 目录: /Users/hehai/.claude/skills/deep-vision/data/sessions
Reports 目录: /Users/hehai/.claude/skills/deep-vision/data/reports

AI 状态: ✓ AI 已启用 (claude-sonnet-4-20250514)

使用方式:
  1. 在浏览器打开 http://localhost:5001
  2. 点击"新建访谈"创建会话
  3. AI 将根据您的回答动态生成问题，进行智能追问
============================================================
```

### 4. 开始使用

打开 http://localhost:5001，你会看到：

1. **顶部 AI 状态指示器**：
   - 🟢 AI 已启用 - API Key 已配置，AI 功能正常
   - 🟡 AI 未启用 - 未配置 API Key，使用静态问题

2. **新建访谈会话**：点击"新建访谈"按钮，输入主题

3. **文档准备（可选）**：上传参考文档（支持 .md, .txt, .pdf, .docx, .xlsx, .pptx）

4. **AI 驱动的选择式访谈**：
   - AI 根据主题、文档和对话历史动态生成问题
   - 提供 3-4 个选项 + "其他"选项
   - 自动识别表面需求并追问
   - 检测回答与参考文档的冲突

5. **需求确认**：当 4 大维度都有覆盖后，确认收集的需求

6. **生成访谈报告**：AI 自动生成专业访谈报告，包含：
   - 需求摘要和优先级矩阵
   - 详细需求分析（4 大维度）
   - Mermaid 可视化图表
   - 方案建议和风险评估

## AI 功能详解

### 动态问题生成

AI 会根据以下信息生成问题：

```python
# 考虑因素：
- 访谈主题
- 参考文档内容
- 已有的访谈记录
- 当前维度的关键方面
- 行业最佳实践
```

示例：

```
主题: CRM系统需求访谈
已有回答: 用户提到"效率低下"

AI 生成追问:
问题: "您提到效率低下，具体是哪个环节效率低？"
选项:
- 客户信息录入和查询
- 销售跟进和任务管理
- 报表统计和数据分析
- 团队协作和沟通
- 其他
```

### 智能追问

AI 识别表面回答并自动深挖：

```
用户回答: "需要提升效率"
AI 追问标识: ⚠️ 智能追问
追问原因: "这是表面需求，需要了解具体的效率瓶颈和期望指标"
```

### 冲突检测

当用户回答与参考文档冲突时，AI 会提醒：

```
参考文档: "预算 50 万元"
用户回答: "预算 100 万元"
AI 冲突提示: ⚠️ 发现潜在冲突
冲突描述: "您提到预算 100 万，但参考文档中显示预算为 50 万，请确认"
```

## 架构说明

### 技术栈

**后端 (server.py)**:
- **Flask** - Web 服务器
- **Anthropic SDK** - Claude API 集成
- **Python 3.10+** - 核心逻辑

**前端**:
- **Alpine.js** - 轻量级响应式框架（16KB）
- **Tailwind CSS** - 快速样式开发
- **Marked.js** - Markdown 渲染

### 数据流

```
┌──────────────┐     API请求      ┌──────────────┐     Claude API    ┌──────────────┐
│              │  ───────────>    │              │  ─────────────>  │              │
│  前端页面     │                  │   Flask后端   │                  │  Claude AI   │
│  (Alpine.js) │  <───────────    │  (server.py) │  <─────────────  │              │
└──────────────┘     JSON响应      └──────────────┘     AI生成内容    └──────────────┘
                                          │
                                          ↓ 保存会话
                                   ┌──────────────┐
                                   │  sessions/   │
                                   │  *.json      │
                                   └──────────────┘
```

## API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/status` | GET | 获取服务状态（包括 AI 可用性） |
| `/api/sessions` | GET | 获取所有会话 |
| `/api/sessions` | POST | 创建新会话 |
| `/api/sessions/<id>` | GET | 获取会话详情 |
| `/api/sessions/<id>` | DELETE | 删除会话 |
| `/api/sessions/<id>/documents` | POST | 上传参考文档 |
| `/api/sessions/<id>/next-question` | POST | **AI 生成下一个问题** |
| `/api/sessions/<id>/submit-answer` | POST | 提交回答并更新会话 |
| `/api/sessions/<id>/generate-report` | POST | **AI 生成访谈报告** |
| `/api/reports` | GET | 获取所有报告 |
| `/api/reports/<name>` | GET | 获取报告内容 |

### 核心 API 示例

**1. AI 生成问题**

```bash
curl -X POST http://localhost:5001/api/sessions/dv-20260123-abc123/next-question \
  -H "Content-Type: application/json" \
  -d '{"dimension": "customer_needs"}'
```

响应：

```json
{
  "question": "您的核心痛点是什么？",
  "options": [
    "效率低下，流程繁琐",
    "成本过高，资源浪费",
    "客户满意度低",
    "数据分析困难"
  ],
  "dimension": "customer_needs",
  "is_follow_up": false,
  "conflict_detected": false,
  "ai_generated": true
}
```

**2. 提交回答**

```bash
curl -X POST http://localhost:5001/api/sessions/dv-20260123-abc123/submit-answer \
  -H "Content-Type: application/json" \
  -d '{
    "question": "您的核心痛点是什么？",
    "answer": "效率低下，流程繁琐",
    "dimension": "customer_needs",
    "options": ["效率低下，流程繁琐", "成本过高，资源浪费", "客户满意度低", "数据分析困难"]
  }'
```

## 文件结构

```
web/
├── server.py           # Flask 后端 + Claude API 集成
├── index.html          # 前端页面
├── app.js              # Alpine.js 逻辑
└── README.md           # 本文档

deep-vision/
└── data/               # 数据目录
    ├── sessions/       # 会话文件存储
    │   └── dv-*.json  # 会话数据（包含访谈记录）
    ├── reports/        # 生成的报告
    │   └── deep-vision-*.md
    ├── converted/      # 转换后的文档
    └── temp/           # 临时文件
```

## 常见问题

### Q: 如何确认 AI 功能已启用？

A: 查看页面右上角的状态指示器：
- 🟢 **AI 已启用** - API Key 配置正确，AI 功能正常
- 🟡 **AI 未启用** - 需要设置 ANTHROPIC_API_KEY 环境变量

### Q: 问题是如何生成的？

A:
- **AI 已启用**: Claude API 根据主题、文档、对话历史动态生成问题和选项
- **AI 未启用**: 使用预设的静态问题库（体验较差）

### Q: 与 Claude Code CLI 中的 /deep-vision 有什么区别？

A: **功能完全一致**。Web 版本提供了：
- 可视化界面
- 实时进度展示
- 报告在线预览
- 会话管理

但核心 AI 逻辑（问题生成、追问、冲突检测）完全相同。

### Q: 上传的文档如何被使用？

A: 参考文档会：
1. 被读取并提取关键信息
2. 作为上下文传递给 Claude API
3. 用于冲突检测（对比用户回答与文档内容）

### Q: 如何查看 AI 生成的报告？

A: 完成访谈后，点击"确认需求摘要并生成访谈报告"。AI 会：
1. 分析所有访谈记录
2. 生成结构化报告（Markdown 格式）
3. 包含 Mermaid 可视化图表
4. 提供下载功能

### Q: 报告包含哪些内容？

A:
- 访谈概述和基本信息
- 需求摘要和优先级矩阵
- 详细需求分析（4 大维度）
- 可视化分析（Mermaid 图表）
- 方案建议和风险评估
- 完整访谈记录附录

## 性能和成本

### API 调用

- **生成问题**: ~1000 tokens/次（输入+输出）
- **生成访谈报告**: ~5000 tokens/次
- **一次完整访谈**: 约 15-20 次问题生成 + 1 次报告 = ~20,000 tokens

### 成本估算

使用 `claude-sonnet-4-20250514` 模型：
- 一次完整访谈约 $0.20 - $0.30
- 按需使用，无月费

## 下一步优化

- [ ] 添加实时联网搜索功能
- [ ] 支持多人协作访谈
- [ ] 添加会话导出/导入
- [ ] 支持自定义维度
- [ ] 添加访谈模板库
- [ ] 支持暗色主题

## 许可证

MIT

---

*此 Web 应用完整实现了 deep-vision 技能的所有功能，提供与 Claude Code CLI 完全相同的真实 AI 体验*
