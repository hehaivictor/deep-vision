# Evaluator Progress

- 生成时间: 2026-05-18T03:20:13Z
- 总体状态: HEALTHY
- 重复次数: 1
- Git 分支: main
- Git 提交: a44920b

## 过滤条件

- scenario_names: -
- categories: -
- tags: stability-local

## 摘要

- PASS=6
- FLAKY=0
- FAIL=0
- budget_exceeded=0

## 场景结果

- `browser/browser-smoke-extended`: PASS | attempts=1 pass=1 fail=0 suite=extended max_ms=11729.83 | calibration=1
- `ops/stability-failure-degrade`: PASS | attempts=1 pass=1 fail=0 cases=8 max_ms=1135.50
- `ops/stability-idempotency`: PASS | attempts=1 pass=1 fail=0 cases=5 max_ms=1273.51
- `report-solution/report-solution-core`: PASS | attempts=1 pass=1 fail=0 cases=3 max_ms=723.97 | calibration=1
- `security/access-boundaries`: PASS | attempts=1 pass=1 fail=0 cases=3 max_ms=757.80 | calibration=1
- `tenant/asset-ownership-boundaries`: PASS | attempts=1 pass=1 fail=0 cases=3 max_ms=1188.86 | calibration=1

## 下一步建议

- 当前 nightly 场景健康，可继续补充新的事故场景或扩大覆盖面。
- 如需交接，优先附带 `summary.json`、`progress.md`、`failure-summary.md` 和 `handoff.json`。
