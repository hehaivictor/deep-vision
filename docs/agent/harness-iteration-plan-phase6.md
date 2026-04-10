# DeepVision Harness 六阶段迭代计划

这份计划承接五阶段结果，聚焦“分层 AGENTS、任务契约全覆盖、校准扩容、轻量自愈、依赖链硬化、薄运营面”六条主线，不重复记录已经落地的统一入口、planner / mission / contract、heartbeat、doc gardener、browser smoke、multi-executor evaluator 与 CI 收口能力。

## 目标

- 为 DeepVision 增加目录级 `AGENTS.md`，把高频目录的局部约束和复跑入口前移
- 把 8 个内置 task 继续收口到更完整的 `mission / planner / contract` 契约链，而不是只覆盖少数高风险链路
- 扩 evaluator 校准样本，把真实误判与放水案例沉淀成长期稳定标尺
- 为 heartbeat / doc gardener 增加轻量“自愈巡检”能力，先做保守版后台刷新与汇总
- 把当前静态 guardrail 从“单条硬规则”继续推进成更完整的单向依赖链
- 提供一个更薄的 harness 运营面，统一看当前阶段、覆盖率、热点与稳定入口

## 当前基线

- 根入口与导航：`AGENTS.md`、`ARCHITECTURE.md`、`docs/agent/README.md`
- 全局短记忆：`docs/agent/heartbeat.md`、`artifacts/memory/latest.json`
- 单入口与执行层：`scripts/agent_harness.py`、`scripts/agent_workflow.py`
- 规则与验证层：`scripts/agent_static_guardrails.py`、`scripts/agent_guardrails.py`、`scripts/agent_smoke.py`、`scripts/agent_browser_smoke.py`
- 评估层：`scripts/agent_eval.py`、`tests/harness_scenarios/**/*.json`
- 计划 / 使命 / 契约 / 校准：`scripts/agent_planner.py`、`scripts/agent_missions.py`、`scripts/agent_contracts.py`、`scripts/agent_calibration.py`
- 园丁与一致性检查：`scripts/agent_doc_gardener.py`
- 当前 task：8 个
- 当前 evaluator 场景：17 个
- 当前校准样本：1 个
- 当前目录级 `AGENTS.md`：仅根目录 1 个
- 五阶段计划与台账：已完成，见 [harness-iteration-plan-phase5.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/harness-iteration-plan-phase5.md) 与 [harness-progress-phase5.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/harness-progress-phase5.md)

## 状态约定

- `planned`：已排期，尚未开始
- `active`：正在执行
- `done`：已完成并验证
- `blocked`：有明确阻塞，需要先处理依赖

## 六阶段清单

| 编号 | 状态 | 主题 | 目标 | 主要交付物 | 验收标准 |
| --- | --- | --- | --- | --- | --- |
| H6-1 | done | Hierarchical AGENTS | 为高频目录补局部 `AGENTS.md`，降低新 agent 的上下文加载成本 | `web/AGENTS.md`、`web/server_modules/AGENTS.md`、`web/app_modules/AGENTS.md`、`scripts/AGENTS.md`、`tests/AGENTS.md` | 新 agent 进入局部目录时，不必先吞完整根入口；每个局部 `AGENTS.md` 都带职责边界和复跑命令 |
| H6-2 | done | Full Mission / Contract Coverage | 把内置 task 继续补齐 `mission / planner / contract`，收口“一句话需求 -> done 定义 -> 验证证据” | `resources/harness/tasks/*.json`、`resources/harness/contracts/*.json`、planner / mission latest 指针 | 8 个 task 都有明确 planner / mission 入口；高风险 task 的 contract 覆盖率保持 100%，园丁报告对 planner / mission 覆盖率保持零告警 |
| H6-3 | done | Calibration Expansion | 扩 evaluator 校准语料，沉淀租户隔离、分享边界、License 门禁和 workflow 治理的硬性标尺 | `tests/harness_calibration/*.json`、`docs/agent/evaluator-calibration.md`、failure-summary/handoff 引用 | 校准样本已从 1 条扩到 6 条；evaluator 工件能稳定引用命中的样本与期望判定 |
| H6-4 | done | AutoDream Lite | 做一个保守版后台自愈巡检器，先刷新 heartbeat / gardening / best-practice 摘要，不自动改业务代码 | `scripts/agent_autodream.py`、只读报告 artifact、`docs/agent/memory-notes.md` | 已能一键刷新 heartbeat、园丁报告和“最近稳定经验”摘要；默认不自动提交 PR |
| H6-5 | done | Dependency Chain Hardening | 把当前静态 guardrail 继续推进成更完整的依赖链硬规则 | `scripts/agent_static_guardrails.py`、新增规则测试、文档 | 已新增 3 条机器可判定的方向规则，并都带 `Action for Agent` |
| H6-6 | done | Harness Ops Surface | 提供一个更薄的运营入口，统一看 phase、覆盖率、latest 指针、blocker 和 doc gardener 状态 | `scripts/agent_ops.py`、概览文档、可选 ops artifact | 单命令可查看当前阶段、task 覆盖、校准规模、最新 harness/eval/CI 状态与推荐入口 |

## 推荐执行顺序

1. H6-1 Hierarchical AGENTS
2. H6-2 Full Mission / Contract Coverage
3. H6-3 Calibration Expansion
4. H6-4 AutoDream Lite
5. H6-5 Dependency Chain Hardening
6. H6-6 Harness Ops Surface

## 每项执行要求

每完成一个编号，必须同步更新 [harness-progress-phase6.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/harness-progress-phase6.md)，至少记录：

- 完成日期
- 对应编号
- 实际改动范围
- 已执行的验证命令
- 关键 artifact / 文档入口
- 剩余风险和下一步

如果某项只完成一部分，也要先登记 `active` 或 `blocked`，不要等全部做完再补记。

## 第一批建议直接启动的事项

- H6-1：优先为 `web/server_modules`、`web/app_modules`、`scripts`、`tests` 补局部 `AGENTS.md`
- H6-2：先补齐 `presentation-export`、`license-audit`、`cloud-import`、`config-center`、`account-merge` 的 mission / contract 覆盖
- H6-3：优先沉淀 `tenant leak must fail`、`share readonly regression must fail`、`license gate wording drift should warn` 三类校准样本
