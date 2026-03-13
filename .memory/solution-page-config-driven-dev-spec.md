# 开发规格: 方案页场景配置驱动化

## 1. 目标

### 1.1 业务目标
- 方案页目录、展示内容、提炼重点由场景配置驱动
- 内置场景与用户自定义场景走同一条运行链路
- 新增场景时主要通过配置完成，不再新增场景专属后端分支

### 1.2 工程目标
- 删除方案页对 `infer_solution_profile()` 的核心依赖
- 引入统一的 `solution schema`
- 引入 `solution DSL -> schema` 编译层，支持普通用户自定义场景
- 引入 `solution_snapshot`，避免直接复用 `draft_snapshot`

## 2. 当前基线

### 2.1 当前已有能力
- 自定义场景创建接口：`POST /api/scenarios/custom`
- 自定义报告 schema 校验：`normalize_custom_report_schema()`
- 方案页 sidecar：`build_solution_sidecar_snapshot()`
- 方案页渲染接口：`GET /api/reports/<filename>/solution`

### 2.2 当前问题
- 自定义场景只支持 `report`，不支持 `solution`
- 方案页靠关键词和少量 profile 决定目录
- 大部分场景会落到 generic 目录
- 报告结构和方案结构混在一起

## 3. 统一配置协议

### 3.1 目标场景对象结构
所有场景统一标准化为：

```json
{
  "id": "custom-xxx",
  "name": "场景名称",
  "description": "场景描述",
  "icon": "clipboard-list",
  "dimensions": [],
  "report": {},
  "solution": {},
  "meta": {
    "source": "builtin"
  }
}
```

### 3.2 `solution` 配置协议

```json
{
  "version": "v1",
  "mode": "schema",
  "schema": {
    "hero": {
      "title_source": "context.subject",
      "summary_source": "derived.executive_summary",
      "highlight_sources": [
        "derived.primary_decision",
        "derived.primary_workstream",
        "quality.evidence_binding_ratio"
      ]
    },
    "sections": [
      {
        "section_id": "current-state",
        "nav_label": "现状诊断",
        "title": "现状诊断",
        "description": "明确现状问题与约束边界",
        "layout": "cards",
        "source": "derived.current_state_cards",
        "transform": "identity",
        "required": true,
        "max_items": 6,
        "empty_policy": "omit",
        "priority": 10
      }
    ]
  }
}
```

### 3.3 `solution` 简化 DSL 协议
给用户自定义场景的增强档输入使用：

```json
{
  "version": "v1",
  "mode": "dsl",
  "dsl": {
    "hero_focus": "核心判断",
    "solution_outline": [
      "现状问题",
      "目标蓝图",
      "候选方案对比",
      "实施计划",
      "风险与边界"
    ],
    "emphasis": [
      "取舍依据",
      "时间里程碑",
      "责任边界"
    ]
  }
}
```

### 3.4 `solution` 自动推导
当 `solution` 缺失时，系统使用：
- `report.schema`
- `report.sections`
- `dimensions`
- `draft`
自动推导出一份标准 `solution.schema`

## 4. 后端核心模块设计

### 4.1 新增模块/函数

#### A. 配置标准化
- `normalize_solution_schema(raw_schema, fallback_sections=None) -> tuple[dict, list]`
- `normalize_solution_config(raw_solution: dict, scenario: dict) -> tuple[dict, list]`

#### B. DSL 编译
- `compile_solution_dsl_to_schema(solution_dsl: dict, scenario: dict) -> tuple[dict, list]`

#### C. 自动推导
- `infer_solution_schema_from_scenario(scenario: dict) -> dict`

#### D. 统一解析入口
- `build_solution_schema_for_session(session: dict, evidence_pack: dict = None) -> dict`

优先级：
1. `scenario.solution.schema`
2. `scenario.solution.dsl`
3. `scenario.report.schema`
4. `scenario.report.sections + dimensions`
5. generic fallback

#### E. 数据抽取与渲染
- `build_solution_snapshot_v2(session, draft_snapshot, evidence_pack, solution_schema) -> dict`
- `resolve_solution_source(snapshot: dict, source: str) -> object`
- `apply_solution_transform(name: str, value: object, snapshot: dict, section: dict) -> object`
- `render_solution_sections_from_schema(snapshot: dict, schema: dict) -> list[dict]`

### 4.2 `solution_snapshot` 协议

```json
{
  "version": "v2",
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
    "primary_decision": "",
    "primary_workstream": "",
    "current_state_cards": [],
    "target_blueprint_cards": [],
    "option_comparison_rows": [],
    "workstreams": [],
    "milestones": [],
    "risk_register": []
  },
  "raw": {
    "draft": {},
    "quality": {},
    "evidence_summary": {}
  }
}
```

### 4.3 Transform 白名单
第一期先支持：
- `identity`
- `summary_to_cards`
- `needs_to_problem_cards`
- `needs_to_priority_table`
- `solutions_to_module_cards`
- `solutions_to_compare_table`
- `actions_to_timeline`
- `actions_to_milestones`
- `actions_to_checklist`
- `risks_to_cards`
- `analysis_to_text_blocks`
- `mixed_items_to_checklist`
- `needs_solutions_actions_to_workstreams`

禁止：
- 任意 Python 表达式
- Jinja/模板执行
- 未注册 transform

## 5. 场景接口改造

### 5.1 现有接口兼容
保留：
- `GET /api/scenarios`
- `GET /api/scenarios/<scenario_id>`
- `POST /api/scenarios/custom`
- `DELETE /api/scenarios/custom/<scenario_id>`

### 5.2 `POST /api/scenarios/custom` 新协议

#### 请求体

```json
{
  "name": "技术迁移方案",
  "description": "适用于系统迁移与重构规划",
  "icon": "cpu",
  "dimensions": [
    {
      "name": "现状评估",
      "description": "当前系统问题",
      "key_aspects": ["架构", "性能", "债务"]
    }
  ],
  "report": {
    "type": "standard",
    "template": "default",
    "sections": ["overview", "current_state_analysis", "implementation_roadmap"]
  },
  "solution": {
    "mode": "dsl",
    "dsl": {
      "solution_outline": [
        "现状问题",
        "目标蓝图",
        "实施计划",
        "风险与边界"
      ]
    }
  }
}
```

#### 服务端处理规则
1. 校验 `dimensions`
2. 标准化 `report`
3. 标准化 `solution`
4. 若 `solution.mode=dsl`，执行编译
5. 若 `solution` 缺失，自动推导
6. 保存时同时落库：
   - `solution` 原始配置
   - `compiled_solution_schema`
   - `config_meta`

#### 响应体新增字段
- `has_solution_schema`
- `solution_mode`
- `solution_schema_version`

### 5.3 `GET /api/scenarios`
返回摘要时新增：
- `has_solution_schema`
- `solution_mode`
- `solution_sections_count`
- `scenario_source`

### 5.4 `GET /api/scenarios/<scenario_id>`
详情返回中新增：
- `solution`
- `compiled_solution_schema`
- `config_meta`

### 5.5 可选新增接口
如果前端需要预览和调试，建议增加：

#### `POST /api/scenarios/custom/preview-solution-schema`
用途：
- 用户创建场景时实时预览方案页目录
- 不落盘，只返回编译结果

请求：
- 与 `POST /api/scenarios/custom` 基本一致

响应：

```json
{
  "success": true,
  "solution_mode": "dsl",
  "compiled_solution_schema": {},
  "issues": []
}
```

## 6. 方案页接口改造

### 6.1 Sidecar 扩展
在现有 sidecar 中新增：
- `solution_schema`
- `solution_snapshot`
- `solution_generation_meta`

保留：
- `draft`
- `quality_meta`
- `quality_snapshot`
- `overall_coverage`

### 6.2 `GET /api/reports/<filename>/solution`
输出协议统一为：

```json
{
  "report_name": "xxx.md",
  "title": "xxx落地方案",
  "subtitle": "xxx",
  "overview": "xxx",
  "source_mode": "structured_sidecar",
  "report_template": "standard_v1",
  "report_type": "standard",
  "fingerprint": {},
  "quality_signals": {},
  "solution_schema_meta": {
    "mode": "dsl",
    "sections_count": 6,
    "compiled_from": "scenario.solution.dsl"
  },
  "hero": {},
  "nav_items": [],
  "sections": []
}
```

### 6.3 后端切换逻辑
新增：
- `build_solution_payload_v2_from_schema(report_name, report_content)`

流程：
1. 读 sidecar
2. 取 `solution_schema`
3. 取或构建 `solution_snapshot`
4. 渲染 `sections`
5. 输出 payload

旧逻辑保留为 fallback：
- sidecar 缺失或 schema 非法时再回退旧 builder

## 7. 迁移步骤

### 阶段 1: 基础设施
任务：
- 新增 `normalize_solution_schema`
- 新增 `compile_solution_dsl_to_schema`
- 新增 `infer_solution_schema_from_scenario`
- 改造自定义场景保存接口，支持 `solution`

交付物：
- 场景对象支持 `solution`
- 自定义场景可保存 DSL 或 schema

### 阶段 2: Sidecar 扩展
任务：
- `build_solution_sidecar_snapshot()` 增加 `solution_schema`
- 新增 `solution_snapshot`
- 加上版本标识 `solution_version=v2`

交付物：
- 新生成报告都带 `solution_schema`
- 老报告兼容旧逻辑

### 阶段 3: 通用方案页渲染引擎
任务：
- 替换 `_build_solution_sections_from_snapshot`
- 落地 resolver + transform registry
- 落地 schema renderer

交付物：
- 方案页目录完全按 schema 驱动
- 旧的 profile 分支只作 fallback

### 阶段 4: 自定义场景三档支持
任务：
- 基础档：无 solution，自动推导
- 增强档：DSL 编译
- 专家档：直接 schema

交付物：
- 普通用户创建自定义场景时不需要理解 schema
- 高级用户可显式控制方案页

### 阶段 5: 质量门禁
新增指标：
- `schema_match_rate`
- `decision_density`
- `workstream_completeness`
- `evidence_span`
- `repeat_phrase_rate`
- `section_uniqueness`

门禁策略：
- 太空 -> degraded
- 太雷同 -> degraded
- 决策密度过低 -> degraded

## 8. 开发任务拆分

### 后端任务
1. 实现 `normalize_solution_schema`
2. 实现 `compile_solution_dsl_to_schema`
3. 实现 `build_solution_schema_for_session`
4. 扩展 `create_custom_scenario`
5. 扩展场景列表/详情返回字段
6. 扩展 sidecar snapshot
7. 实现 `solution_snapshot v2`
8. 实现 resolver / transform registry
9. 实现 `build_solution_payload_v2_from_schema`
10. 接入质量门禁

### 测试任务
1. 自定义场景基础档创建成功
2. 自定义场景 DSL 编译成功
3. 自定义场景 schema 校验失败用例
4. 报告生成后 sidecar 带 `solution_schema`
5. 方案页 payload 按 schema 输出 nav 和 section
6. 无显式 solution 的场景自动推导成功
7. degraded 策略在新链路下仍生效

### 前端任务
1. 场景创建页支持 `solution` 输入
2. 提供基础档 / 增强档 / 专家档 UI
3. 可选支持“预览目录”
4. 方案页消费 `solution_schema_meta`

## 9. 验收标准

### 功能验收
- 内置场景不再依赖 profile 猜测目录
- 自定义场景创建时可选择：
  - 自动推导
  - DSL
  - 专家 schema
- 同一套方案页接口能输出内置和自定义场景

### 工程验收
- 新增场景时无需新增后端场景分支
- transform 全部注册化、白名单化
- schema 不合法时有明确错误信息

### 内容验收
- 方案页 section 顺序与 schema 一致
- 关键场景目录不再回退 generic
- 页面重复短语比例下降
- 决策信息、里程碑和风险边界不再缺失

## 10. 推荐实施顺序
1. 先做后端 schema 和自定义场景接口扩展
2. 再做 sidecar 和方案页新渲染链路
3. 然后补场景创建 UI
4. 最后切默认流量并清理旧 profile 逻辑
