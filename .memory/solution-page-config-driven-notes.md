# Notes: 方案页场景配置驱动化

## 现状结论

### 1. 场景配置定义了报告章节，但方案页没有真正消费
- `resources/scenarios/builtin/tech-solution.json` 已有 `report.sections`
- 但方案页渲染主要走 `infer_solution_profile()`，只识别 `custom / feedback_loop / interactive_interview / structured_default`
- 结果是大多数场景落入默认模板

### 2. 方案页当前数据源是 `draft_snapshot`
- 报告成功后，服务端会把 `draft_snapshot` + `evidence_pack` 写入 sidecar
- 方案页读取 sidecar，再按固定 layout 拼装 section
- 问题不在前端模板，而在 sidecar 结构和 section 组装逻辑都过于通用

### 3. 报告 prompt 追求“结构统一”，不是“方案表达个性化”
- 普通 V3 prompt 顶层字段固定为 `overview/needs/analysis/visualizations/solutions/risks/actions/open_questions/evidence_index`
- 该结构适合报告归档，不适合直接表达技术方案、产品方案、招投标方案等不同提案形态

### 4. 现有 custom schema 能力可复用
- 已有 `normalize_custom_report_schema()` 和 `summarize_custom_report_schema_for_prompt()`
- 说明项目已经具备“声明式章节配置”的基础设施
- 方案页可沿用同一思路，新增 `normalize_solution_schema()`

## 关键代码位置
- `web/server.py:1135` `normalize_custom_report_schema`
- `web/server.py:11113` `build_report_draft_prompt_v3`
- `web/server.py:22049` `build_solution_sidecar_snapshot`
- `web/server.py:22337` `infer_solution_profile`
- `web/server.py:22717` `_build_solution_sections_from_snapshot`
- `resources/scenarios/builtin/tech-solution.json:42` 场景配置里的章节定义

## 设计原则
- 配置驱动优先：场景差异应尽量体现在配置，不体现在 Python 分支
- 数据分层：报告结构和方案结构分开，不再复用一套 JSON 承载两种用途
- 渐进迁移：保留旧 sidecar 和旧 API，允许双轨运行
- 内容可验证：新增“方案判断深度、结构命中率、重复率”指标，而不是只校验 section 数量

## 目标能力
- 新场景新增时，只需要补 `scenario.solution` 配置
- 不需要新增 `infer_solution_profile()` 分支
- 方案页目录、导航、布局、提炼重点都由 schema 决定
- 同一套 engine 支持技术方案、用户研究、产品规划、招投标、评估类方案

## 用户自定义场景补充结论

### 1. 必须区分“内置场景”和“用户自定义场景”的来源差异
- 内置场景可以预置 `dimensions`、`report.sections`、`solution.schema`
- 用户自定义场景通常只有部分输入，可能只有名称、描述、问题维度或报告章节
- 因此不能要求所有自定义场景都手写完整 `solution.schema`

### 2. 用户自定义场景应该走“三层降级”
- 第一层：显式提供 `solution.schema`，完全按用户配置渲染
- 第二层：未提供 `solution.schema`，但提供 `report.schema` / `report.sections` / `dimensions`，系统自动推导方案 schema
- 第三层：仅提供主题和少量描述，系统回退到领域无关的 `generic solution schema`

### 3. 自定义场景的关键不是“允许自定义”，而是“限制自定义边界”
- 只允许声明式 schema，不允许执行模板、脚本或任意表达式
- 只允许引用白名单 source 与 transform
- 只允许使用系统支持的 layout 组件
- 这样才能保证安全、可测试、可迁移

### 4. 更好的方案是“场景 DSL + 推导器”
- 不要求用户理解底层 `source/transform`
- 用户侧只配置场景目标、维度、章节意图
- 系统将其编译为标准 `solution.schema`
- 这样既保留灵活性，也避免把配置复杂度直接暴露给终端用户
