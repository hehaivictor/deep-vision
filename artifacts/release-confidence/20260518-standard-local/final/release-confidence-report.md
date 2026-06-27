# DeepVision 标准发布准入测试报告

生成时间：2026-05-18 11:09 CST

## 结论

可发布但需记录 WARN。

本轮未发现业务主链路阻断。首次执行时核心 unittest 聚合命令返回非零，根因是测试模块动态加载的 `web.server` 后台 metrics flush 线程未在 teardown 关闭，污染后续 `sys.stdout` 捕获；已在测试侧修复。修复后原始核心聚合命令、stability-local-core、stability-local evaluator、stability-local-release 与 live-minimal 真链路均通过。release/core harness 的整体结果仍为 READY_WITH_WARNINGS，WARN 属于本地环境或历史观察类。

## Artifact 索引

- 基线目录：`artifacts/release-confidence/20260518-standard-local/baseline/`
- Core harness：`artifacts/release-confidence/20260518-standard-local/core/latest.json`
- Core run：`artifacts/release-confidence/20260518-standard-local/core/20260518T031856Z-pid7094/`
- Evaluator：`artifacts/release-confidence/20260518-standard-local/eval/latest.json`
- Evaluator run：`artifacts/release-confidence/20260518-standard-local/eval/20260518T032013Z-pid8470/`
- Release harness：`artifacts/release-confidence/20260518-standard-local/release/latest.json`
- Release run：`artifacts/release-confidence/20260518-standard-local/release/20260518T031945Z-pid7705/`
- 最终观察：`artifacts/release-confidence/20260518-standard-local/final/`

## 执行结果

- `python3 scripts/agent_ops.py status`：完成，baseline/final 均显示 `ATTENTION_REQUIRED`，原因是历史稳定性 WARN 指针，不是本轮失败。
- `python3 scripts/agent_doc_gardener.py`：`HEALTHY`，PASS=6 WARN=0 FAIL=0。
- `python3 scripts/agent_history.py --kind harness-stability-release --limit 5`：历史 latest 为 2026-04-10 `READY_WITH_WARNINGS`。
- `python3 scripts/agent_static_guardrails.py`：`READY`，PASS=13 FAIL=0。
- 核心 unittest：修复后原始聚合命令通过，380 tests OK，见 `artifacts/release-confidence/20260518-standard-local/fix-verify-core-unittest.txt`。拆分模块也均通过。
  - `tests.test_api_comprehensive`：120 tests OK。
  - `tests.test_security_regression`：134 tests OK。
  - `tests.test_solution_payload`：32 tests OK。
  - `tests.test_scripts_comprehensive`：83 tests OK。
  - `tests.test_version_manager`：11 tests OK。
- 聚合 unittest：首次 `core-unittest.txt` 中同进程聚合执行出现 4 个 `tests.test_scripts_comprehensive` JSONDecodeError；修复后原始聚合命令已转绿。
- `python3 scripts/agent_harness.py --profile stability-local-core`：`READY_WITH_WARNINGS`，PASS=4 WARN=2 FAIL=0。
- `python3 scripts/agent_eval.py --tag stability-local`：`HEALTHY`，PASS=6 FLAKY=0 FAIL=0。
- `python3 scripts/agent_harness.py --profile stability-local-release`：`READY_WITH_WARNINGS`，PASS=4 WARN=2 FAIL=0。

## 前端体验专项

- 复用了现有 `extended` browser smoke，未新增第三套框架。
- `extended` browser smoke：16 个场景全部 PASS，覆盖帮助页、方案页分享、公开分享只读、公开分享刷新保持只读、登录 provider 视图、License gate、License 绑定成功与刷新恢复、报告详情与刷新恢复、访谈刷新恢复、报告生成刷新恢复、管理员配置中心页签。
- `live-minimal` browser smoke：真实隔离后端下完成验证码登录与 License 绑定，手机号 `13800138000`，PASS。
- 本轮自动覆盖了关键路径是否可渲染、主操作入口是否可达、只读态边界、刷新恢复、页签切换与 License 门禁状态切换。
- 未执行完整视觉回归、跨浏览器矩阵、无障碍专项、逐页桌面/移动截图人工审查；这些按计划属于手工轻量检查或后续专项，不作为本轮阻断。

## 已修复阻断项

- 核心 unittest 聚合命令失败：原始失败见 `artifacts/release-confidence/20260518-standard-local/baseline/core-unittest.txt`。
- 失败表现：380 个测试中 4 个 `tests.test_scripts_comprehensive.ComprehensiveScriptTests` 用例在同进程聚合执行时发生 `JSONDecodeError`，原因是用例未读取到可解析的 harness JSON stdout。
- 根因：`tests.test_api_comprehensive`、`tests.test_security_regression`、`tests.test_solution_payload` 动态加载 `web.server` 后会启动 `MetricsCollector` 后台线程，teardown 未关闭线程；多个模块串跑时旧线程继续打印 metrics flush 失败日志，污染后续 harness JSON stdout 捕获。
- 修复：三个测试类 `tearDownClass()` 中显式调用 `cls.server.metrics_collector.close()`。
- 复核证据：最小复现组合修复后通过，见 `fix-verify-api-solution-plus-one.txt`；原始核心聚合命令修复后通过，见 `fix-verify-core-unittest.txt`。

## WARN 分类

- 本地环境 WARN：`SMS_PROVIDER=mock`，仅适合本地调试或演示；符合计划中的可放行 WARN。
- 本地配置 WARN：当前未启用登录后 License 强制校验；本轮 release 的 live-minimal 已验证 License 绑定链路，但生产发布前仍需按目标环境确认开关。
- 历史观察 WARN：`agent_observe.py --profile auto` 显示历史 `DEGRADED`，包含旧 browser_smoke blocker 记录与历史运行趋势；本轮 core/eval/release 复跑没有复现阻断。

## 剩余风险

- 未做云端联调，不验证真实短信、真实微信 OAuth、真实生产数据库迁移。
- 未做完整视觉回归、跨浏览器矩阵、无障碍专项和 10 轮长稳压测。
- 最终 `git status` 显示 3 个测试文件有修复改动，并新增本轮测试 artifact；未修改业务代码。
