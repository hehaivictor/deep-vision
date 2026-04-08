# DeepVision Harness 三阶段进度台账

这份台账用于记录三阶段 harness 优化的执行痕迹。后续每做完一项，或出现阻塞，都在这里追加一条记录。

## 当前执行面

- 当前阶段：`active`
- 当前优先项：`H3-6 CI 成本优化`
- 对应计划：[harness-iteration-plan-phase3.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/harness-iteration-plan-phase3.md)

## 进度记录

| 日期 | 编号 | 状态 | 事项 | 证据 | 下一步 |
| --- | --- | --- | --- | --- | --- |
| 2026-04-08 | PLAN-3 | done | 建立三阶段 harness 迭代计划与独立进度台账，承接二阶段完成后的后续优化方向 | [harness-iteration-plan-phase3.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/harness-iteration-plan-phase3.md) | 启动 H3-1，扩容真实后端浏览器链路 |
| 2026-04-08 | H3-1 | done | 新增 `live-extended` browser smoke，覆盖真实报告详情、方案页与公开分享只读链路，并补 live evaluator 场景 | [agent_browser_smoke.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/scripts/agent_browser_smoke.py)、[agent_browser_smoke_runner.mjs](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/scripts/agent_browser_smoke_runner.mjs)、[browser-smoke-live-extended.json](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/tests/harness_scenarios/browser/browser-smoke-live-extended.json)、[latest.json](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/artifacts/harness-eval/latest.json) | 启动 H3-2，整理实例隔离与资产归属场景 |
| 2026-04-08 | H3-2 | done | 新增 `tenant` 主题 evaluator 场景，并把实例隔离/导出资产专项用例修成自包含，tenant 验证改为专属 artifact 目录 | [instance-scope-boundaries.json](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/tests/harness_scenarios/tenant/instance-scope-boundaries.json)、[asset-ownership-boundaries.json](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/tests/harness_scenarios/tenant/asset-ownership-boundaries.json)、[latest.json](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/artifacts/harness-eval/h3-2-tenant/latest.json) | 启动 H3-3，给 observe 增加连续失败和阈值化告警 |
| 2026-04-08 | H3-3 | done | `observe` 新增连续失败、重复 blocker、慢场景回归三类阈值告警，并把推荐复跑命令接入诊断面板与 history 摘要 | [agent_observe.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/scripts/agent_observe.py)、[observability.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/observability.md)、[latest.json](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/artifacts/harness-runs/h3-3-observe/latest.json) | 启动 H3-4，为高风险 workflow 增加治理字段 |
| 2026-04-08 | H3-4 | done | 高风险 workflow 新增治理字段声明与强制校验，`license-admin` 实跑 artifact/handoff 已带出变更原因、操作者、审批人和工单信息 | [agent_workflow.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/scripts/agent_workflow.py)、[agent_artifacts.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/scripts/agent_artifacts.py)、[latest.json](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/artifacts/harness-runs/h3-4-license-admin/latest.json) | 启动 H3-5，继续把失败 run 自动沉淀成 evaluator 场景 |
| 2026-04-08 | H3-5 | done | `agent_scenario_scaffold` 现在会自动推荐 `category / tags / budget / output`，并支持从 `browser_smoke`、`workflow`、`harness` 失败直接生成 executor 模板；`failure-summary` / `handoff` 已切换到 richer scaffold 建议 | [agent_scenario_scaffold.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/scripts/agent_scenario_scaffold.py)、[agent_artifacts.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/scripts/agent_artifacts.py)、[evaluator.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/evaluator.md)、[latest.json](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/artifacts/harness-runs/h3-5-workflow/latest.json) | 启动 H3-6，继续优化 PR / nightly 的运行成本与触发策略 |

## 记录模板

复制以下模板追加到表格末尾：

```text
| YYYY-MM-DD | H3-x | planned/active/done/blocked | 简述本次推进内容 | 关键文件或 artifact 链接 | 明确下一步 |
```

## 补充说明

- 如果本次执行修改了 workflow、task profile、browser smoke、observe 或 evaluator，优先同时补链接到对应文件。
- 如果执行了验证命令，但没有新增 artifact，也要在“证据”里写明命令。
- 如果出现阻塞，必须写出阻塞点，不要只写“待继续”。
