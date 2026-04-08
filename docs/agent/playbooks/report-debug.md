# 报告与方案页问题排查

> 本文件由 `python3 scripts/agent_playbook_sync.py` 基于 task 画像自动生成。
> 关联任务画像：`report-solution` | 来源：`resources/harness/tasks/report-solution.json`

把报告生成、方案页渲染与分享问题收口到固定诊断顺序，先看运行态与 task harness，再决定是否下钻专项回归。

## 什么时候用

- 报告生成失败、卡住或状态异常
- 方案页渲染错误、分享链路异常、旧报告 fallback 可疑
- 想确认问题在后端 payload、分享边界，还是前端渲染

## 先跑哪些命令

```bash
python3 scripts/agent_observe.py --profile auto
python3 scripts/agent_harness.py --task report-solution --observe --profile auto --artifact-dir artifacts/harness-runs
python3 scripts/agent_eval.py --scenario report-solution-core --artifact-dir artifacts/harness-eval
```

如怀疑只读分享或权限边界问题，再补：

```bash
python3 -m unittest tests.test_security_regression
```

## 看哪些 artifact

- `artifacts/harness-runs/latest.json`
- `对应 run 目录下的 observe.json`
- `对应 run 目录下的 smoke.json`
- `artifacts/harness-eval/latest.json`
- `对应 evaluator run 目录下的 report-solution-core.json`

重点看：

- startup_snapshot、metrics、harness_runs 是否已有告警
- report-solution-core 场景里失败的是报告生成、分享边界，还是旧报告兼容
- smoke / security_regression 里是否直接出现权限拒绝、结构断言失败、payload 回退

## 哪些操作必须人工确认

- 修改报告模板、结构化 sidecar、方案页 payload 字段
- 修改公开分享行为、token 暴露字段、导出下载权限
- 删除或弱化旧报告 Markdown fallback

## 相关文档

- `docs/agent/report-solution.md`
