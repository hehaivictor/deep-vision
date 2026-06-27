# Intus 优化回迁 DeepVision 差异审计

## 已确认 DeepVision 已具备

- 报告 V3 质量门禁：`web/server.py` 已有 `build_quality_gate_issues_v3`、`resolve_quality_gate_soft_pass_v3` 等报告质量门禁函数；对应回归集中在 `tests/test_security_regression.py`。
- Mermaid 前端渲染容错：`web/app.js` 已有 `normalizeMermaidDefinition`、`normalizeMermaidPieDefinition`、`normalizeMermaidQuadrantDefinition`、`normalizeMermaidFlowchartLabels` 等渲染前规范化函数。
- 附录导出基础：`web/app_modules/report_detail_runtime.js` 与 `web/app.js` 已有完整访谈记录附录导出菜单、附录 PDF/Word/Markdown 导出和权限能力字段。
- 管理配置中心委托：`web/server.py` 已通过 `build_admin_config_center_payload` / `save_admin_config_group` 委托配置中心服务。

## 已确认 DeepVision 缺失或不完整

- 用户可见问题质量闸门：DeepVision 未检出 `evaluate_visible_question_quality_gate`、`clean_visible_question_text`、`should_reject_visible_question`；Intus 已在 `web/server.py` 和 `tests/test_question_fast_strategy.py` 中覆盖。
- 深度访谈质量 evaluator 场景：DeepVision 未检出 `tests/harness_scenarios/report-solution/deep-interview-question-quality.json`；Intus 已登记该场景。
- 主备模型降级：DeepVision 未检出 `MODEL_FALLBACK_ENABLED`、`QUESTION_FALLBACK_MODEL_NAME`、`REPORT_DRAFT_FALLBACK_MODEL_NAME`；Intus 已在 `web/config.py`、`web/server.py` 和 `tests/test_runtime_token_config.py` 中覆盖。
- 报告失败诊断命名：DeepVision 未检出 `persist_report_failure_diagnostics`；现有报告失败链路需要逐文件确认是否仍存在模板兜底伪成功。
- 报告导出规范化入口：DeepVision 未检出 `normalizeMermaidBlocksForExport`、`getProgressAlignedRemainingQuestions`、`viewReportEvidenceAppendix`；但已存在相近的 Mermaid 渲染、附录导出和剩余题数估算能力。
- `product-ui-flow` 任务画像：DeepVision 未检出 `resources/harness/tasks/product-ui-flow.json` 和对应 playbook；Intus 已登记。

## 需要逐文件 diff 后确认

- 多 worker 问题生成误中断：DeepVision 已有 `prefetch_inflight`、`prefetch_cache` 和 `_prepare_question_generation_runtime`，但未检出 `pending_question_generation` 或显式 stale recover helper，需要在实施任务 4 时对照 Intus `cc1a497`。
- 报告生成模板兜底：DeepVision 已有 `simple_template_fallback` 和 `REPORT_V3_RELEASE_CONSERVATIVE_MODE`，但是否在模型失败时保存正式报告，需要以新增测试锁定。
- Dockerfile Node runtime：需直接读取 `deploy/Dockerfile.production` 后决定是否修改。

## 建议进入实施的任务

- `任务 1`：访谈问题质量闸门。
- `任务 2`：报告生成失败态收紧。
- `任务 3`：主备模型降级。
- `任务 4`：生产发布稳定性核对。
- `任务 5`：报告导出与前端体验增强。
- `任务 6`：`product-ui-flow` 发布准入画像。
