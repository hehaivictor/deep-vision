# Notes: V3 报告链路问题复盘

## 复盘对象

### 会话 1: dv-20260305004312-de77f5e0
- 来源: `/Users/hehai/Documents/开目软件/Agents/project/DeepVision/data/sessions/dv-20260305004312-de77f5e0.json`
- 关键信号:
  - `reason=review_gate_failed`
  - `final_issue_types=['no_evidence']`
  - `salvage_issue_types=['quality_gate_evidence', 'quality_gate_weak_binding']`
  - `evidence_pack_summary`: `facts_count=31`, `unknowns_count=30`, `average_quality_score=0.238`, `follow_up_ratio=0.613`, `hard_triggered_count=27`
- 审稿问题实质:
  - `solutions[0].evidence_binding_mode` 被判空
  - `risks[0].evidence_binding_mode` 被判空

## 核心发现

### 1. 问题生成与报告取证目标冲突
- 问题生成 prompt 鼓励“3-4 个简洁选项、便于快速选择”。
- 质量评估和证据包构建此前会把“选项型回答”判成 `option_only`、`single_selection`、`too_short`。
- 结果是系统鼓励用户用最短路径回答，再把这些回答认定为低质量证据。

### 2. 竞速机制会把深挖问题推向 summary lane
- 轻量档会把 `summary` 作为备用 lane。
- 动态 lane 排序会按历史成功率和时延提升更优 lane。
- 在跟进提问、盲区补问、正式题较多时，系统更容易使用 `summary` 生成问题。
- 这会提升速度，但会降低问题的取证密度。

### 3. 覆盖率指标失真
- 当前维度 coverage 基于正式问题数量，不基于关键方面是否真实覆盖。
- 因此可能出现 `coverage=100%`，同时仍存在 `missing_aspects`。

### 4. 平均质量指标存在乐观偏差
- `average_quality_score` 只统计大于 0 的项。
- 这会掩盖一批 0 分回答，使稀疏证据场景看起来比真实情况更健康。

### 5. weak binding 门禁仍偏硬
- `weak_inferred` 统一按固定权重扣分。
- `open_questions` 与 `risks` 的天然弱绑定特征没有被充分区别对待。

## 已落地修复
- failover 不再默认强制单 lane。
- `option_only` 不再进入 hard trigger 和 unknown 识别主链。
- 单选题不再被误判为 `single_selection`。
- `evidence_binding_mode` 缺省时自动补 `strong_explicit`。
- 忽略模型将 `*.evidence_binding_mode` 误报为 `no_evidence` 的幻觉问题。
- `pending_follow_up` 的 `open_questions` 不再拉低硬性 evidence coverage。
- 稀疏证据场景下适度放宽 evidence/weak binding 门禁。
- 问题链路新增 `answer_mode / requires_rationale / evidence_intent`，前后端已完成透传。
- 高取证问题固定走 `question -> report`，禁用 `summary` 竞速和动态晋升。
- 证据包已切换为“方面覆盖 + 质量加权覆盖”，并输出 raw/positive-only 质量均值。
- `weak_binding_ratio` 已拆成字段感知版，`open_questions` 不再混入弱绑定比率。
- failover 已支持 deterministic bucket，不再只认单个可修复问题。

## 仍待改造的重点
- 基于真实失败会话做端到端重放，对比新旧 `unknown_ratio`、V3 通过率与时延。
- 决定是否继续把 `question_selected_lane / runtime_profile` 接入管理页诊断面板。
- 根据新指标结果再微调 `hedge delay / timeout / token`，不建议先盲调。
