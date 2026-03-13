# V3 报告链路完整整改方案

## 目标
提升问题生成质量、证据密度、V3 报告通过率与整体时延稳定性，避免通过“更快但更浅”的问题链路换来后续报告失败。

## 总体策略
1. 先止血：去掉误伤规则和错误 lane 选择。
2. 再校准：修正 coverage、quality、weak binding 等指标口径。
3. 后重构：把问题生成从“统一问法”升级为“探索型 vs 取证型”双模式。
4. 最后闭环：用新的线上指标和回放机制验证收益。

## 分层整改

### 一、架构层
- 引入问题类型分层:
  - 探索型问题：快速收敛方向，允许短选项回答。
  - 取证型问题：为报告服务，要求“选项 + 原因/场景/量化”。
- 给问题 schema 增加:
  - `answer_mode`
  - `requires_rationale`
  - `evidence_intent`
- 取证型问题禁用 `summary` lane 竞速，并禁止 `summary` 动态晋升为 primary。

### 二、规则层
- 覆盖率从“题数覆盖”升级为“关键方面覆盖 + 质量加权覆盖”。
- `average_quality_score` 同时输出:
  - `raw_average_quality_score`
  - `positive_only_average_quality_score`
- `weak_binding_ratio` 分字段计算:
  - `actions` 严格
  - `solutions` 中等
  - `risks/open_questions` 宽松
- 增加 deterministic fix bucket:
  - `evidence_binding_mode` 缺省
  - 去重类 blindspot
  - 可本地补齐的轻量结构问题

### 三、参数层
- 问题链路:
  - 取证场景关闭 `summary` hedge
  - 适当延长 `question` 的 hedge grace period
  - 不再优先通过缩短 token/timeout 换取更高命中率
- 报告链路:
  - 保持当前 failover 单 lane 关闭
  - 弱绑定阈值改成按字段或按 evidence context 自适应
- 不建议继续盲目增加 report review round 或 review token

### 四、观测层
- 新增指标:
  - `question_answer_mode_distribution`
  - `question_lane_win_rate_by_phase`
  - `quality_adjusted_coverage`
  - `raw_unknown_ratio`
  - `weak_binding_ratio_by_field`
  - `v3_pass_rate_by_question_profile`
- 新增回放:
  - 固定会话集端到端回放
  - 问题链路 A/B 对比回放
  - failover 命中与收益统计

## 实施优先级

### P0
- 禁用取证型问题的 `summary` 竞速与动态晋升
- 引入 `answer_mode/requires_rationale`
- coverage 指标改造
- 质量均值口径改造

### P1
- `weak_binding_ratio` 字段感知化
- deterministic fix bucket
- failover 触发策略升级

### P2
- 基于真实数据重新回调 token、timeout、hedge delay
- 补充线上观测面板和失败诊断看板

## 验证标准
- V3 通过率提升
- 平均报告生成时长不显著恶化
- `unknown_ratio` 明显下降
- `hard_triggered_count` 与 `follow_up_ratio` 从异常高位回落
- 取证阶段 `summary` lane 参与率显著下降
