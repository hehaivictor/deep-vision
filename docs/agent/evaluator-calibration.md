# Evaluator 校准样本

这份文档记录 DeepVision evaluator 的评分标尺与真实误判案例。目标不是增加更多场景，而是让 `PASS / WARN / FAIL` 的尺度有可回溯依据，避免 nightly 因断言过硬或过松而漂移。

## 固定入口

- 查看校准样本目录：`ls tests/harness_calibration`
- 列出 evaluator 场景：`python3 scripts/agent_eval.py --list`
- 执行单个校准相关场景：`python3 scripts/agent_eval.py --scenario report-solution-preview --artifact-dir artifacts/harness-eval`
- 从失败 artifact 生成场景模板：`python3 scripts/agent_scenario_scaffold.py --source eval --dry-run`

## 当前校准样本

### report-solution-wording-drift

- 样本文件：[`tests/harness_calibration/report-solution-wording-drift.json`](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/tests/harness_calibration/report-solution-wording-drift.json)
- 适用场景：`report-solution-preview`、`report-solution-core`
- 目标：防止方案页标题、卡片或指标文案发生轻微措辞变化时，被 evaluator 因逐字比较误判为 `FAIL`
- 期望判定：`WARN`

### 当前标尺

- 应判 `FAIL`：
  - 公开分享不再保持匿名只读
  - owner 校验、token 边界或旧报告 fallback 被破坏
  - 方案页回流 `MLOps`、`LLMOps`、`proposal_brief`、`结构化素材` 等内部实现词
- 应判 `WARN`：
  - 标题或文案有轻微措辞调整，但稳定语义仍成立
  - 卡片标题、指标名称有同义替换，但用户可见含义未变
- 应判 `PASS`：
  - 稳定语义、权限边界和内部词清洗都符合要求

## 使用约定

- 新增真实误判案例时，优先在 `tests/harness_calibration/*.json` 补样本，再决定是否新增场景
- 样本要写清 `incident`、`expected_decision`、`rule`、`source_refs`
- 如果 nightly 或 PR 工件命中了校准样本，`failure-summary.md` 和 `handoff.json` 应直接带出样本引用

## 后续方向

- 补 UI 视觉类校准样本，区分“轻微文案漂移”和“真实交互退化”
- 为 `tenant` 主题场景增加“必须 FAIL”的跨租户泄露样本
- 把历史误判与修复 PR 链接进一步沉淀到样本元数据
