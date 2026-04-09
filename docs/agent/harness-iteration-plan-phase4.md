# DeepVision Harness 四阶段迭代计划

这份计划承接三阶段结果，聚焦“显式规划、契约驱动、评估校准、架构固化”四条主线，不重复记录已经落地的统一入口、task workflow、artifact/handoff、browser smoke、multi-executor evaluator 与 CI 收口能力。

## 目标

- 为 DeepVision 增加显式的 `Planner artifact` 层，把简短需求扩成结构化计划工件
- 让高风险 task 从“有 workflow”进一步升级到“有可共享的 Sprint Contract”
- 为 Evaluator 建立持续校准机制，减少评分漂移与误放行
- 把已经证明有效的架构与品味约束继续固化成机械规则，而不是只停留在文档里
- 让 `planner / generator / evaluator` 之间形成可回放、可交接、可追责的闭环

## 当前基线

- 统一入口：`scripts/agent_harness.py`
- 受控任务执行：`scripts/agent_workflow.py`
- 只读观察与历史对比：`scripts/agent_observe.py`、`scripts/agent_history.py`
- 场景 evaluator：`scripts/agent_eval.py`
- 浏览器 UI smoke：`scripts/agent_browser_smoke.py`
- task-backed playbook：`scripts/agent_playbook_sync.py`
- 任务画像：8 个
- evaluator 场景：16 个
- 三阶段计划与台账：已完成，见 [harness-iteration-plan-phase3.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/harness-iteration-plan-phase3.md) 与 [harness-progress-phase3.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/harness-progress-phase3.md)

## 状态约定

- `planned`：已排期，尚未开始
- `active`：正在执行
- `done`：已完成并验证
- `blocked`：有明确阻塞，需要先处理依赖

## 四阶段清单

| 编号 | 状态 | 主题 | 目标 | 主要交付物 | 验收标准 |
| --- | --- | --- | --- | --- | --- |
| H4-1 | done | Planner Artifact | 把用户简短需求收口成结构化计划工件，而不是直接跳进 task workflow | `docs/agent/plans/**/*.md` 或 `artifacts/planner/**/*.json`、规划入口脚本或模板、导航文档 | 至少有 1 条高频任务支持先生成 Planner 工件，再进入后续 workflow |
| H4-2 | done | Sprint Contract | 为高风险 task 增加共享的“what done looks like”契约文件，供 workflow 与 evaluator 同时引用 | `resources/harness/contracts/*.json`、`scripts/agent_workflow.py`、`scripts/agent_eval.py`、task 文档 | 至少 2 个高风险 task 接入 contract，并在运行工件中能看到契约引用 |
| H4-3 | done | Evaluator Calibration | 建立 evaluator 校准样本与评分标尺，持续修正“过宽/过松/误放行”问题 | `docs/agent/evaluator-calibration.md` 或 `tests/harness_calibration/**`、失败回灌入口 | 至少沉淀 1 组真实误判案例，并让 Evaluator 文档/工件能引用校准样本 |
| H4-4 | done | Architecture Rule Hardening | 把已验证有效的架构边界继续转成静态规则或 linter，而不是只靠人工记忆 | `scripts/agent_static_guardrails.py`、新增规则文件或测试、相关文档 | 至少新增 1 条机器可判定的架构边界规则，并进入 PR 基础检查 |
| H4-5 | done | Planner-Contract 闭环整合 | 让 Planner、Contract、Workflow、Evaluator、Handoff 之间形成固定信息流 | `scripts/agent_artifacts.py`、`scripts/agent_harness.py`、相关文档与 artifact 模板 | Handoff / Failure Summary 能明确指向对应 plan 与 contract，不再只给命令入口 |

## 推荐执行顺序

1. H4-1 Planner Artifact
2. H4-2 Sprint Contract
3. H4-3 Evaluator Calibration
4. H4-4 Architecture Rule Hardening
5. H4-5 Planner-Contract 闭环整合

## 每项执行要求

每完成一个编号，必须同步更新 [harness-progress-phase4.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/harness-progress-phase4.md)，至少记录：

- 完成日期
- 对应编号
- 实际改动范围
- 已执行的验证命令
- 关键 artifact / 文档入口
- 剩余风险和下一步

如果某项只完成一部分，也要先登记 `active` 或 `blocked`，不要等全部做完再补记。

## 第一批建议直接启动的事项

- H4-1：先为 `report-solution` 或 `license-admin` 增加 Planner 工件模板，验证“需求 -> 计划 -> workflow”的最短闭环
- H4-2：优先把 `ownership-migration`、`license-admin` 这类高风险 task 收口到 Sprint Contract
- H4-3：先沉淀 1 组真实误判案例，覆盖“CI 偶发误红”或“Evaluator 放过回归”的校准样本
