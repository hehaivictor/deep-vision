# Harness Failure Summary

- 生成时间: 2026-05-18T03:18:56Z
- 总体状态: READY_WITH_WARNINGS

## doctor

- 状态: WARN
- 详情: profile=auto env=/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/.env.local PASS=11 WARN=2 FAIL=0
- 复跑命令: `python3 scripts/agent_doctor.py --profile auto`
- 关键信号:
  - SMS_PROVIDER: 当前使用 mock 短信，仅适合本地调试或演示环境。
  - License 开关: 当前未启用登录后 License 强制校验。

## observe

- 状态: WARN
- 详情: recent=5 overall=DEGRADED
- 复跑命令: `python3 scripts/agent_observe.py --profile auto --recent 5`
- 关键信号:
  - source=runtime_metrics_store total=504 avg_ms=15853.9 recent_failures=5
  - items=0 latest=none
  - runs=20 latest=none blocked=3 latest_ms=44506.25
  - latest=7 problem=0 warning=3 harness_diff=UNCHANGED evaluator_diff=CHANGED task=none blocker=browser_smoke: suite=extended scena… slow=browser-smoke-live-minimal streak=none blocker_repeat=browser_smoke: suite=ex…x2 regression=none release_gate=PASS:44506.25
  - task=none blocker=browser_smoke: suite=extended scena… slow=browser-smoke-live-minimal problem_kinds=0 warning_kinds=3 streak=none blocker_repeat=browser_smoke: suite=ex…x2 regression=none release_gate=PASS:44506.25 replay=python3 scripts/agent_browser_smoke.py --suite extended
  - source=runtime_metrics_store initialized=yes total_ms=10.00 completed_at=2026-05-13T02:23:06Z

## 回灌建议

- 推荐分类: `ops`
- 推荐标签: `incident, manual, ops, harness`
- 推荐预算: `120000` ms
- 推荐输出: `tests/harness_scenarios/ops/ops-incident-20260518.json`
- 来源摘要: `harness:20260518T031856Z-pid7094 stages=doctor/observe`
- 预览模板: `python3 scripts/agent_scenario_scaffold.py --source harness --run-dir '/Users/hehai/Documents/开目软件/Agents/project/DeepVision/artifacts/release-confidence/20260518-standard-local/core/20260518T031856Z-pid7094' --name ops-incident-20260518 --category ops --budget-ms 120000 --output tests/harness_scenarios/ops/ops-incident-20260518.json --tag incident --tag manual --tag ops --tag harness --dry-run`
- 直接写入: `python3 scripts/agent_scenario_scaffold.py --source harness --run-dir '/Users/hehai/Documents/开目软件/Agents/project/DeepVision/artifacts/release-confidence/20260518-standard-local/core/20260518T031856Z-pid7094' --name ops-incident-20260518 --category ops --budget-ms 120000 --output tests/harness_scenarios/ops/ops-incident-20260518.json --tag incident --tag manual --tag ops --tag harness`
