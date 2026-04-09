# 场景 Evaluator

## 适用范围

当任务需要回答下面这些问题时，不要只跑 `smoke` 或 `guardrails`：

- 最近哪些高价值业务场景最慢、最容易失败
- 某条链路是否出现了波动，而不是稳定失败
- 哪类回归应该纳入 nightly，而不是只在 PR 时触发
- 新增线上事故后，应该把它沉淀成什么固定场景

## 固定入口

- 列出场景：`python3 scripts/agent_eval.py --list`
- 执行全部 nightly 场景：`python3 scripts/agent_eval.py --tag nightly`
- 重跑两次识别波动：`python3 scripts/agent_eval.py --tag nightly --repeat 2`
- 落盘 evaluator 工件：`python3 scripts/agent_eval.py --tag nightly --artifact-dir artifacts/harness-eval`
- 只跑某一类：`python3 scripts/agent_eval.py --category ops`
- 只跑单个场景：`python3 scripts/agent_eval.py --scenario observability-and-config`
- 从最新 artifact 生成新场景模板：`python3 scripts/agent_scenario_scaffold.py --source latest --dry-run`
- 只从 evaluator 指定场景生成模板：`python3 scripts/agent_scenario_scaffold.py --source eval --scenario access-boundaries --dry-run`
- 查看评分校准样本：`sed -n '1,240p' docs/agent/evaluator-calibration.md`

## 当前场景库

场景文件位于 `tests/harness_scenarios/**/*.json`，每个场景至少包含：

- `name`：稳定场景名
- `category`：业务分类，例如 `report-solution`、`migration`、`security`、`ops`
- `tags`：用于 nightly / 手动筛选
- `budgets.max_duration_ms`：当前场景允许的最大耗时预算
- `cases`：`unittest` 场景复用已有测试用例，不在场景文件里写业务逻辑
- `executor`：可选执行器描述；当前支持 `unittest`、`browser_smoke`、`workflow`、`harness`

执行器约定：

- `unittest`：默认模式，直接消费 `cases`
- `browser_smoke`：通过 `executor.suite` 执行 `scripts/agent_browser_smoke.py`
- `workflow`：通过 `executor.task` 与 `executor.execute_mode` 执行 `scripts/agent_workflow.py`
- `harness`：通过 `executor.args` 调用 `scripts/agent_harness.py --json`

tag 约定：

- `nightly`：进入 GitHub Actions 的 `harness-nightly`
- `browser`：浏览器级场景，nightly 会自动准备 Node / Playwright
- `workflow`：任务工作流场景，用来验证 task profile 的真实执行面
- `manual`：保留给人工深回归，不默认进入 nightly
- `live`：需要真实后端或 seeded runtime 的场景，通常与 `manual` 组合使用

当前仓库里，`browser-smoke-live-minimal` 和 `browser-smoke-live-extended` 都属于 `manual + live` 浏览器场景：前者验证验证码登录与 License 绑定，后者继续覆盖真实报告详情、方案页和公开分享只读链路。

三阶段开始新增了 `tenant` 主题场景，用来单独跟踪 `INSTANCE_SCOPE_KEY`、资产归属、分享 owner 和对象存储元数据边界；其中 `instance-scope-boundaries` 已进入 nightly，`asset-ownership-boundaries` 先作为 manual 深回归保留。

当前场景库已扩到 16 条，除原有的核心链路外，还新增了：

- `browser-smoke-extended`：更完整的 UI 状态机浏览器回归
- `browser-smoke-live-extended`：真实后端下的报告详情、方案页与公开分享真链路
- `account-merge-rollback`：账号合并与管理员回滚链路
- `license-admin-preview`：License 管理 workflow 预演
- `env-overlay-resolution`：运行时环境文件叠加解析
- `instance-scope-boundaries` / `asset-ownership-boundaries`：实例隔离、分享 owner 与资产归属边界
- `presentation-map-concurrency`：演示稿 sidecar 并发完整性

## 校准样本

校准样本位于 `tests/harness_calibration/*.json`，用于记录“哪些应该判 FAIL，哪些只是 WARN”的真实尺度。

当前第一条样本是 [`report-solution-wording-drift.json`](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/tests/harness_calibration/report-solution-wording-drift.json)，对应 `report-solution-preview` 的真实误判案例：方案页标题文案轻微变化时，不应继续使用逐字比较导致 nightly 误红。

当前约定：

- 语义、权限边界、内部实现词泄露属于硬失败
- 轻微措辞变化但稳定语义成立，优先判 `WARN`
- evaluator 工件命中校准样本后，`progress.md`、`failure-summary.md` 与 `handoff.json` 都会直接带出样本引用

## 当前输出

`agent_eval` 会汇总：

- 每个场景的 `PASS / FLAKY / FAIL`
- 每个场景对应的执行器与目标，例如 `suite=minimal`、`task=report-solution execute=preview`
- 每个场景的最大耗时、平均耗时和预算是否超标
- 失败热点 test id 统计
- 慢场景 Top N
- 波动场景列表
- evaluator 工件目录与 `latest.json` 指针
- 每次运行的 `progress.md`、`failure-summary.md` 与 `handoff.json`

## 推荐用法

1. PR 仍然以 `pr-harness.yml` 内的 `pr-smoke / agent-smoke / guardrails` 为主
2. 需要做较深重构或排查跨模块回归时，先跑 `python3 scripts/agent_eval.py --tag nightly`
3. 如果某条链路疑似波动，追加 `--repeat 2` 或 `--repeat 3`
4. 新增线上事故后，优先判断它更适合挂成 `unittest`、`browser_smoke` 还是 `workflow` 场景，再补进 `tests/harness_scenarios/`
5. 如果已经有失败 artifact，不要手工复制 test id，优先用 `agent_scenario_scaffold.py` 生成模板
6. `failure-summary.md` 和 `handoff.json` 里的回灌建议现在会直接带上 `name / category / tag / budget / output`；如果失败来源是 `browser_smoke`、`workflow` 或 `harness`，也会直接推荐对应 executor 模板
