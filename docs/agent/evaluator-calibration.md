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

### tenant-leak-must-fail

- 样本文件：[`tests/harness_calibration/tenant-leak-must-fail.json`](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/tests/harness_calibration/tenant-leak-must-fail.json)
- 适用场景：`instance-scope-boundaries`
- 目标：把跨 `INSTANCE_SCOPE_KEY` 的会话、报告或批量删除泄露固定为硬失败
- 期望判定：`FAIL`

### share-readonly-regression-must-fail

- 样本文件：[`tests/harness_calibration/share-readonly-regression-must-fail.json`](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/tests/harness_calibration/share-readonly-regression-must-fail.json)
- 适用场景：`access-boundaries`、`asset-ownership-boundaries`
- 目标：把 owner 校验、公开只读和匿名写拦截边界回退固定为硬失败
- 期望判定：`FAIL`

### license-gate-ui-wording-drift-should-warn

- 样本文件：[`tests/harness_calibration/license-gate-ui-wording-drift-should-warn.json`](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/tests/harness_calibration/license-gate-ui-wording-drift-should-warn.json)
- 适用场景：`browser-smoke-extended`
- 目标：区分“License 门禁仍有效但前端文案轻微变化”和“门禁失效”的不同风险等级
- 期望判定：`WARN`

### workflow-governance-missing-must-fail

- 样本文件：[`tests/harness_calibration/workflow-governance-missing-must-fail.json`](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/tests/harness_calibration/workflow-governance-missing-must-fail.json)
- 适用场景：`ownership-migration-governance`、`license-admin-preview`
- 目标：把治理字段、确认词、备份目录或管理员前置条件的缺失固定为硬失败
- 期望判定：`FAIL`

### presentation-sidecar-integrity-must-fail

- 样本文件：[`tests/harness_calibration/presentation-sidecar-integrity-must-fail.json`](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/tests/harness_calibration/presentation-sidecar-integrity-must-fail.json)
- 适用场景：`presentation-map-concurrency`
- 目标：把 sidecar 映射完整性和导出资产元数据回退固定为硬失败
- 期望判定：`FAIL`

### 当前标尺

- 应判 `FAIL`：
  - 跨租户 `INSTANCE_SCOPE_KEY` 的会话、报告或批量删除发生泄露
  - 公开分享不再保持匿名只读
  - 演示稿 sidecar 映射在并发更新下丢失或导出资产元数据错绑
  - 高风险 workflow 缺少治理字段、确认词、备份目录或管理员前置条件
  - owner 校验、token 边界或旧报告 fallback 被破坏
  - 方案页回流 `MLOps`、`LLMOps`、`proposal_brief`、`结构化素材` 等内部实现词
- 应判 `WARN`：
  - 标题或文案有轻微措辞调整，但稳定语义仍成立
  - License 门禁前端标题、说明或按钮措辞轻微变化，但门禁阻断与绑定入口仍正常
  - 卡片标题、指标名称有同义替换，但用户可见含义未变
- 应判 `PASS`：
  - 稳定语义、权限边界、治理链路和内部词清洗都符合要求

## 使用约定

- 新增真实误判案例时，优先在 `tests/harness_calibration/*.json` 补样本，再决定是否新增场景
- 样本要写清 `incident`、`expected_decision`、`rule`、`source_refs`
- 如果 nightly 或 PR 工件命中了校准样本，`failure-summary.md` 和 `handoff.json` 应直接带出样本引用

## 后续方向

- 继续补浏览器真链路校准样本，区分“轻微 UI 漂移”和“真实交互失效”
- 为 `tenant` 主题补更多资产 owner / 对象存储元数据边界样本
- 把历史误判与修复 PR 链接进一步沉淀到样本元数据
