# Evaluator Progress

- 生成时间: 2026-05-18T03:08:09Z
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

- `browser/browser-smoke-extended`: PASS | attempts=1 pass=1 fail=0 suite=extended max_ms=13792.06 | calibration=1
- `ops/stability-failure-degrade`: PASS | attempts=1 pass=1 fail=0 cases=8 max_ms=1479.61
- `ops/stability-idempotency`: PASS | attempts=1 pass=1 fail=0 cases=5 max_ms=1116.75
- `report-solution/report-solution-core`: PASS | attempts=1 pass=1 fail=0 cases=3 max_ms=854.16 | calibration=1
- `security/access-boundaries`: PASS | attempts=1 pass=1 fail=0 cases=3 max_ms=796.32 | calibration=1
- `tenant/asset-ownership-boundaries`: PASS | attempts=1 pass=1 fail=0 cases=3 max_ms=1211.68 | calibration=1

## 下一步建议

- 当前 nightly 场景健康，可继续补充新的事故场景或扩大覆盖面。
- 如需交接，优先附带 `summary.json`、`progress.md`、`failure-summary.md` 和 `handoff.json`。
