# 交付件: 方案页场景配置驱动化完整实施路径

## 1. 目标定义

### 1.1 要解决的问题
当前方案页的问题不是“样式不够好”，而是“结构表达能力太弱”：
- 目录不是场景声明出来的，而是后端猜出来的
- 报告草案与方案页复用同一份结构化数据，导致内容天然偏浅
- 不同场景最终被压缩成相似的 `needs/solutions/actions` 拼装页
- 质量门禁只防空、防假、不防“浅”和“不像该场景”

### 1.2 最终目标
把方案页升级为三层架构：
1. `scenario.solution`：场景声明目录、布局、提炼规则
2. `solution_snapshot`：面向方案页的独立结构化数据
3. `solution_renderer`：基于 schema 的通用渲染引擎

新增场景时：
- 主要新增或修改 JSON 配置
- 最多补少量通用 transform
- 不再新增场景专属 Python 分支

## 2. 目标架构

### 2.1 新的数据流
当前链路：
`session -> evidence_pack -> draft_snapshot -> sidecar -> solution payload`

目标链路：
`session -> evidence_pack -> reviewed_report_draft -> solution_snapshot -> solution payload`

其中：
- `reviewed_report_draft` 继续服务 Markdown 报告生成
- `solution_snapshot` 专门服务方案页
- 两者共享事实源，但不共享最终表达结构

### 2.2 新的配置层级
建议在每个场景配置中新增：

```json
{
  "solution": {
    "version": "v1",
    "profile": "config_driven",
    "schema": {
      "hero": {
        "title_source": "context.subject",
        "summary_source": "derived.executive_summary",
        "highlight_sources": ["derived.primary_decision", "derived.primary_workstream", "quality.evidence_binding_ratio"]
      },
      "sections": [
        {
          "section_id": "current-state",
          "nav_label": "现状诊断",
          "title": "现状诊断",
          "layout": "cards",
          "source": "derived.current_state_cards",
          "required": true
        }
      ]
    }
  }
}
```

### 2.3 设计要求
- `report` 和 `solution` 分离
- `solution.schema` 只描述“怎么展示什么内容”
- `solution_snapshot` 负责“把哪些内容准备好”
- `renderer` 不再理解具体业务场景，只理解 schema
- 同一套机制同时支持内置场景与用户自定义场景

### 2.4 内置场景与自定义场景的统一模型
不要把“用户自定义场景”当成特例，而要把它视为配置来源不同的同类对象。

统一的数据入口建议为：
- `scenario.id`
- `scenario.name`
- `scenario.description`
- `scenario.dimensions`
- `scenario.report`
- `scenario.solution`
- `scenario.meta.source`，取值如 `builtin` / `user_defined`

运行时统一走：
`raw scenario config -> normalized scenario config -> compiled solution schema -> solution payload`

这样：
- 内置场景只是“平台预置配置”
- 用户自定义场景只是“用户写入配置”
- 渲染链路完全一致

## 3. 核心设计

### 3.1 新增 `solution schema`
新增一套独立于 `custom_report_schema` 的方案页 schema。

建议支持字段：
- `section_id`
- `nav_label`
- `title`
- `description`
- `layout`
- `source`
- `sources`
- `transform`
- `required`
- `max_items`
- `empty_policy`
- `priority`

`layout` 第一阶段只支持现有可落地组件：
- `cards`
- `table`
- `steps`
- `timeline`
- `checklist`
- `text`

这样可以先复用前端能力，不先扩前端复杂组件。

对于用户自定义场景，`solution schema` 需要支持两种输入方式：

1. 专家模式
- 用户或管理员直接写标准 `solution.schema`
- 适合高级用户、模板市场、运营配置

2. 普通模式
- 用户只写简化 DSL，例如“我想展示现状、目标、风险、路线图”
- 系统编译为标准 `solution.schema`
- 适合大多数自定义场景创建者

### 3.2 新增 `source resolver`
把所有可取值来源统一抽象成 resolver，而不是在 section builder 里手写字段映射。

建议支持三类 source：

1. 原始 source
- `draft.overview`
- `draft.needs`
- `draft.solutions`
- `draft.actions`
- `draft.risks`
- `draft.open_questions`
- `draft.analysis.customer_needs`
- `evidence.dimension_coverage`
- `quality.*`

2. 上下文 source
- `context.subject`
- `context.pain_point`
- `context.entry_point`
- `context.constraint`

3. 派生 source
- `derived.executive_summary`
- `derived.decision_cards`
- `derived.current_state_cards`
- `derived.target_architecture_cards`
- `derived.option_comparison_rows`
- `derived.workstreams`
- `derived.milestones`
- `derived.risk_register`
- `derived.dependencies`

原则：
- 场景差异通过选择不同 source/transform 组合体现
- 不是为每个场景新写一个 `build_xxx_solution_sections()`

### 3.3 新增 `transform` 机制
`transform` 负责把原始数据变成 layout 需要的结构。

建议内置一组通用 transform：
- `summary_to_cards`
- `needs_to_priority_table`
- `solutions_to_module_cards`
- `actions_to_timeline`
- `risks_to_cards`
- `analysis_to_text_blocks`
- `needs_solutions_actions_to_workstreams`
- `options_to_compare_table`
- `actions_to_milestones`
- `mixed_items_to_checklist`

关键点：
- transform 是通用能力，不是场景私有函数
- 场景只在配置里声明“哪个 section 用哪个 transform”
- 用户自定义场景只能使用注册过的 transform 白名单

### 3.5 新增“场景 DSL 编译器”
这是支持用户自定义场景时最关键的一层。

原因：
- 直接让用户写 `solution.schema` 成本太高
- 直接让用户写 Python/模板表达式不可控
- 因此需要在用户输入和标准 schema 之间增加一个编译层

建议 DSL 只暴露业务语义，不暴露实现细节。

例如用户定义：

```json
{
  "solution_outline": [
    "现状问题",
    "目标蓝图",
    "候选方案对比",
    "实施计划",
    "风险与边界"
  ]
}
```

系统编译后得到：
- `current-state` -> `layout=cards` -> `transform=needs_to_problem_cards`
- `target-blueprint` -> `layout=text/cards` -> `transform=analysis_to_target_cards`
- `option-compare` -> `layout=table` -> `transform=options_to_compare_table`
- `roadmap` -> `layout=timeline` -> `transform=actions_to_milestones`
- `risks` -> `layout=cards` -> `transform=risks_to_cards`

这层的价值是：
- 对用户友好
- 对系统安全
- 对工程可维护

### 3.4 新增 `solution_snapshot`
`solution_snapshot` 不再只是 `draft_snapshot` 的镜像，而是单独的数据模型。

建议结构：

```json
{
  "context": {
    "subject": "",
    "scene": "",
    "pain_point": "",
    "entry_point": "",
    "constraint": ""
  },
  "decision_frame": {
    "why_now": "",
    "why_this_path": "",
    "must_lock": ""
  },
  "derived": {
    "executive_summary": "",
    "decision_cards": [],
    "workstreams": [],
    "milestones": [],
    "dependencies": [],
    "option_comparison_rows": [],
    "risk_register": []
  },
  "raw": {
    "draft": {},
    "quality": {},
    "evidence_summary": {}
  }
}
```

这里的重点是：
- `raw` 保留可追溯事实
- `derived` 承载方案页真正消费的数据
- 后续 section schema 只消费 `context` / `decision_frame` / `derived`

## 4. 一次性改造的实施阶段

### 阶段 A: 打基础设施
目标：让方案页具备“由配置驱动”的运行骨架。

改造项：
1. 新增 `normalize_solution_schema()`
2. 新增 `summarize_solution_schema_for_prompt()` 或 debug 展示
3. 新增 `build_solution_schema_for_session()`，优先级如下：
   - `scenario.solution.schema`
   - `scenario.solution.dsl` 编译后的 schema
   - 从 `scenario.report.schema` 推导
   - 从 `scenario.report.sections + dimensions` 推导默认方案 schema
   - 最终兜底 generic schema
4. sidecar 中新增：
   - `solution_schema`
   - `solution_snapshot`
   - `solution_version`

完成标志：
- 所有场景都能拿到一份合法的 `solution_schema`
- 删除或弃用 `infer_solution_profile()` 的场景判断职责
- 用户自定义场景即使未显式编写 schema，也能通过 DSL 或默认推导进入新体系

### 阶段 B: 抽象通用 resolver + transform
目标：后端不再按场景 if/else 组装章节。

改造项：
1. 把 `_build_solution_sections_from_snapshot()` 拆成：
   - `resolve_solution_source()`
   - `apply_solution_transform()`
   - `render_solution_sections_from_schema()`
2. 现有 `needs/solutions/actions/risks` 的映射逻辑下沉为通用 transform
3. 保留现有 layout：`cards/table/steps/timeline/checklist/text`
4. `section` 输出统一数据协议，前端无需感知场景

完成标志：
- 新增一个场景时，目录差异只改配置
- 旧的 `feedback_loop / interactive_interview / structured_default` 可以退化为内置预设 schema

### 阶段 C: 建立方案专用的内容生成层
目标：不再把报告摘要硬塞进方案页。

有两种做法：

做法 1，推荐：
- 新增一个轻量 `solution synthesis` 步骤
- 输入：`reviewed_report_draft + evidence_pack + solution_schema`
- 输出：`solution_snapshot.derived`

做法 2，过渡方案：
- 先用 deterministic derivation 从 `draft_snapshot` 推导 `derived`
- 等稳定后再补一层 LLM 生成

建议一次性设计时采用“支持双模式”：
- `mode=deterministic`
- `mode=ai_assisted`

这样先不阻塞上线。

### 阶段 D: 默认推导所有场景，避免逐个适配
目标：让“没有写 `solution` 配置”的场景也能自动进入新体系。

默认推导规则建议：
1. 根据 `scenario.dimensions` 生成诊断型章节
2. 根据 `report.sections` 生成导航顺序
3. 根据 `draft` 中是否存在 `needs/solutions/actions/risks/open_questions` 自动挂接通用 transform
4. 根据关键词只做轻量命名优化，不再决定整体目录

例如：
- 有 `current_state/target_architecture/tech_selection/implementation_path`
  自动生成：现状诊断/目标架构/方案对比/实施路径
- 有 `customer_needs/business_process/tech_constraints/project_constraints`
  自动生成：需求判断/流程闭环/约束边界/推进路径

这样可以一次性覆盖所有内置场景，后续只有高价值场景才需要精调配置。

### 阶段 D2: 支持用户自定义场景
目标：让用户创建场景时，不需要理解底层实现，也能产出高质量方案页。

建议分三档：

1. 基础档
- 用户只填写名称、描述、访谈维度
- 系统自动推导 `report` 与 `solution` schema

2. 增强档
- 用户额外填写“方案页想呈现哪些章节”
- 系统用 DSL 编译为标准 `solution.schema`

3. 专家档
- 用户直接上传完整 `report.schema` / `solution.schema`
- 系统只做校验、标准化和安全收敛

这三档共享同一条运行链路，不引入新的渲染分支。

### 阶段 E: 质量门禁升级
目标：让系统拦住“结构正确但仍然空洞”的方案页。

新增质量指标：
- `schema_match_rate`
- `decision_density`
- `workstream_completeness`
- `evidence_span`
- `repeat_phrase_rate`
- `section_uniqueness`

门禁策略：
- `schema_match_rate` 太低：降级到真实信息视图
- `decision_density` 太低：提示“判断信息不足，不生成提案式方案”
- `repeat_phrase_rate` 太高：视为模板化

## 5. 推荐的数据与接口改造

### 5.1 sidecar 扩展
新增字段：
- `solution_schema`
- `solution_snapshot`
- `solution_generation_meta`

保留字段：
- `draft`
- `quality_meta`
- `quality_snapshot`
- `overall_coverage`

这样旧接口不破，新能力可渐进启用。

### 5.2 API 输出
`/api/reports/<filename>/solution` 输出建议改为：
- `hero`
- `nav_items`
- `sections`
- `quality_signals`
- `source_mode`
- `solution_schema_meta`

其中 `sections` 全部来自通用 schema renderer。

### 5.3 场景创建接口建议
如果支持用户自定义场景，建议把场景保存分为两层：
- 用户提交层：允许 `dimensions`、`report.sections`、`solution_outline`、可选 `solution.schema`
- 系统编译层：输出标准 `scenario_config`

不要把用户原始输入直接当成最终运行配置。

## 6. 前后端改造边界

### 后端
主要工作量在后端：
- schema 规范化
- source resolver
- transform registry
- solution snapshot 生成
- 质量门禁

### 前端
前端应尽量少改：
- 保持现有 layout renderer
- 可新增少量展示能力，例如 compare table、section badges、evidence chips
- 不承担场景判断职责

原则是：
- 场景差异由后端 schema 决定
- 前端只消费统一协议

## 7. 测试策略

### 7.1 单元测试
新增测试组：
- `test_solution_schema_normalization`
- `test_solution_source_resolution`
- `test_solution_transform_registry`
- `test_solution_schema_rendering`

### 7.2 场景回归测试
选 5 类代表场景：
- 技术方案
- 用户研究
- 产品规划
- 招投标
- 面试评估
- 用户自定义场景（基础档）
- 用户自定义场景（增强档 DSL）
- 用户自定义场景（专家档 schema）

每类校验：
- nav 顺序命中配置
- section 数量与必填 section 命中
- 关键 section 使用预期 layout
- 不进入 generic fallback

### 7.3 内容质量测试
不要只断言 section id，要断言：
- 技术方案必须出现现状/目标/选型/路径
- 用户研究必须出现问题/机会/验证/行动
- 页面中重复短语比例低于阈值
- decision/workstream/milestone 不是空字段

## 8. 发布与迁移策略

### 8.1 双轨期
第一阶段双轨输出：
- 旧 `build_solution_payload_from_report()`
- 新 `build_solution_payload_v2_from_schema()`

用 feature flag 控制：
- `SOLUTION_SCHEMA_ENABLED`
- `SOLUTION_AI_SYNTHESIS_ENABLED`

### 8.2 迁移顺序
1. sidecar 先增加新字段，不切流
2. 新 API payload 在影子模式生成，对比结果
3. 测试覆盖稳定后，切默认新逻辑
4. 最后删除 `infer_solution_profile()` 和旧分支 builder

对于用户自定义场景：
5. 先只开放基础档和增强档
6. 专家档 schema 编辑能力在后台或灰度用户中放开

## 9. 具体落地建议

### 第一批必须做
1. 引入 `solution` 配置块
2. 新增 `normalize_solution_schema()`
3. 新增 `compile_solution_dsl_to_schema()`
4. 用 `scenario.report.sections + dimensions` 自动推导默认 schema
5. 替换 `_build_solution_sections_from_snapshot()` 为 schema renderer
6. sidecar 增加 `solution_schema`

### 第二批应该做
1. 引入 `solution_snapshot.derived`
2. 补 `workstream` / `milestone` / `dependency` 级别 transform
3. 新增内容质量指标
4. 场景创建流程支持基础档/增强档 DSL

### 第三批优化项
1. AI 辅助生成 `solution_snapshot`
2. 新增 compare/matrix 等更高级 layout
3. 前端增加证据引用交互和决策图表

## 10. 最终判断
这件事可以一次性做成“配置驱动体系”，但前提是你不要继续沿着“多加几个 profile 分支”的方向演进。

正确路径是：
- 把“场景差异”从代码分支搬到 schema
- 把“用户自定义输入”先编译成 schema，再进入统一运行链路
- 把“报告结构”和“方案结构”彻底分层
- 把“组装章节”改造成 resolver + transform registry
- 用默认推导覆盖所有场景，再允许少数场景做显式精调

如果按这个路径推进，后续新增场景的成本会从“改 Python 逻辑 + 补测试”降到“加/调配置 + 跑回归”。
